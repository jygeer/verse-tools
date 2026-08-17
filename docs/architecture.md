# Architecture

```
source text
    |  lexer.py     (indentation-sensitive tokenizer)
    v
token stream
    |  parser.py    (recursive-descent + precedence climbing)
    v
AST                 (ast_nodes.py - plain dataclasses)
    |  compiler.py  (tree walk -> linear instructions)
    v
bytecode Chunk       (bytecode.py - Instr list + constant pool)
    |  vm.py        (stack-based dispatch loop)
    v
program output / values
```

Each stage is a separate, independently testable module with no
knowledge of the stages after it (the lexer doesn't know about the
parser's grammar; the compiler doesn't know how the VM executes an
opcode - only what each opcode *means*). `tests/` mirrors this: there's
a test file per stage plus an end-to-end test that runs every example
program.

## Lexer: indentation as tokens

`lexer.py` turns the block structure of the source into ordinary
tokens - `INDENT`, `DEDENT`, `NEWLINE` - so the parser never has to
think about whitespace. This is the same idea Python's own tokenizer
uses:

- At the start of each logical line (when not inside `(...)`/`[...]`/
  `{...}`), measure leading spaces and compare to a stack of known
  indentation widths, emitting `INDENT`/`DEDENT` as needed.
- Blank lines and comment-only lines are invisible to indentation
  tracking - they don't open or close anything.
- Bracket nesting suppresses `NEWLINE`/`INDENT`/`DEDENT` entirely, so
  multi-line literals and argument lists "just work" without special
  parser cases.
- At end of file, any still-open indentation levels are closed with
  synthetic `DEDENT`s - a program doesn't need a trailing blank line.

See `Lexer._consume_indentation` in `lexer.py` for the implementation;
it's about 40 lines and is the trickiest part of the whole lexer.

## Parser: recursive descent with one deliberate ambiguity

The grammar (full listing in
[`language-reference.md`](language-reference.md#grammar-summary)) is
parsed by straightforward recursive descent, with standard precedence
climbing for expressions (see the table in the language reference).

The one genuinely ambiguous spot: a statement starting with `IDENT` could
be a function declaration (`Foo(X : int) : int = ...`), a constant
declaration (`Foo := ...`), a class declaration (`Foo := class: ...`),
or just an expression statement (a bare call like `Print("hi")`). Rather
than restructure the grammar to avoid this, `_parse_ident_led_statement`
resolves it with small bounded lookahead, and
`_try_parse_func_decl` speculatively parses a function *signature*
inside a try/except that backtracks on failure - deliberately **only**
around the signature, not the body: once `= ` is matched unambiguously,
any further syntax error is a real error and is allowed to propagate,
rather than being swallowed into a confusing "maybe it's an expression"
fallback.

## Compiler: two design choices that shape everything

### 1. Variables are name-based, not stack-slot based

Fast bytecode VMs (CPython, Lua, clox from *Crafting Interpreters*)
resolve locals to numbered stack slots at compile time and closures to
"upvalue" indices, trading compiler complexity for speed. `versetools`
instead gives each function call one `Environment` - a name -> value
dict with a parent pointer to the lexically enclosing scope
(`values.py`). `LOAD_NAME`/`STORE_NAME`/`SET_NAME` walk this chain at
runtime.

This is slower than slot indexing, but it still keeps closure capture
simple: `MAKE_FUNCTION` just captures "whatever `Environment` is current
right now" as the new function's closure scope. Block scoping is handled
by creating and discarding child environments (`PUSH_SCOPE`/
`POP_SCOPE`) around block bodies while still using name-based lookup.

### 2. Failure is a real exception with an explicit handler stack

Verse's `decides` effect - "this expression might fail, and failure
skips to the nearest handler" - is implemented with a genuine Python
exception, `VerseFailure` (`errors.py`), rather than by threading a
success/failure value through every expression (which real
backtracking implementations, and effect-typed languages, actually do
more precisely - see the differences doc for what that costs us).

Each `Frame` (one per function call) carries a small stack of
`(target_pc, stack_depth, env)` handlers. Compiling an `if`'s clause list
(`Compiler._compile_clauses` in `compiler.py`) emits:

```
PUSH_HANDLER fail_target     ; register a catch point
<code for the clause expression>
POP_HANDLER                  ; expression didn't fail - remove it
CLAUSE_CHECK fail_target     ; but it might still be a plain `false`/
                              ; absent-option "soft" failure - check that too
STORE_NAME clause_name       ; (or POP, for an unnamed boolean clause)
```

If the clause's code raises `VerseFailure`, the VM's dispatch loop
catches it right there (`_exec_frame`'s `try`/`except VerseFailure`),
pops the matching handler, **truncates the operand stack back to the
depth it had when the handler was pushed**, restores the environment to
the saved scope, and jumps to `fail_target`.

If no handler is active when a `VerseFailure` is raised, it propagates
out of the frame's generator entirely - which, because ordinary calls
drive their callee with `yield from` (see below), simply means *the
call itself* raises `VerseFailure` to its caller. That's how failure
"propagates out of a function" without any special call-site code: it's
just what an uncaught Python exception does through nested generator
delegation.

`for`-loop filter clauses reuse the identical mechanism, with
`fail_target` pointed at the loop's re-fetch-next-element address
instead of an `else` branch. `Expr?` (`FAILABLE_UNWRAP`) uses the same
success/failure classification (`_clause_result` in `vm.py`) but always
raises on failure rather than jumping anywhere - it has no handler of
its own, so it relies on whatever handler (if any) is active further
up.

## VM: one generator, cooperative concurrency for free

`VM._exec_frame` is a generator that executes one instruction and
`yield`s, per iteration. This single choice is what makes the
concurrency model work with almost no extra machinery:

- **An ordinary call** (`CALL` opcode) drives its callee with
  `result = yield from self._call(callee, args, line)`. Generator
  delegation means every instruction the callee executes transparently
  yields *through* the caller - so if the caller's frame is itself
  being stepped one instruction at a time by something else (see next
  point), the callee's execution interleaves at the same granularity,
  for free.
- **`spawn`** wraps a zero-argument function's frame in a fresh
  `_exec_frame` generator and hands it to `VM.scheduler_tasks` as a
  `VTask`, *without* driving it at all. It only makes progress when
  something calls `_tick_all()`.
- **`sync`/`race`** create one `VTask` per branch, add them to the
  scheduler, and loop calling `_tick_all()` (which calls `next()` once
  on every not-yet-done task, main frame's dispatch loop included via
  its own generator) until (`sync`) every branch is done, or (`race`)
  the first one is - `race`'s losers are then simply dropped from
  `scheduler_tasks`, i.e. "cancelled" by no longer being stepped. Any
  output or state changes they'd already made before that point stand.
- At the very end of `run_chunk`, any tasks `spawn`ed but not yet
  awaited by a `sync`/`race` are drained to completion
  (`_drain_background_tasks`) so a script's fire-and-forget background
  work still finishes before the process exits - true "leak it forever"
  fire-and-forget isn't implemented (see differences doc).

Because scheduling is round-robin over a single Python thread with no
preemption *inside* an instruction, there's no data-race concern -
`_tick_all`'s `next()` calls are strictly sequential. The visible
concurrency is real interleaving (you can see two tasks' `Print` calls
alternate line-by-line), but it's deterministic given the same program.

### Frame layout

```
Frame
  chunk    -> the Chunk being executed
  env      -> Environment (name -> value, parent chain)
  stack    -> operand stack (list)
  pc       -> program counter (index into chunk.code)
  handlers -> [(target_pc, stack_depth_at_push), ...]
```

### Bytecode reference

See the `Op` enum in `bytecode.py` for the authoritative list (each
member has a one-line comment); the categories are:

| Category | Opcodes |
|---|---|
| Constants / names | `LOAD_CONST`, `LOAD_NAME`, `STORE_NAME`, `SET_NAME`, `PUSH_SCOPE`, `POP_SCOPE` |
| Stack shuffling | `POP`, `POP_CHECKED` |
| Arithmetic / logic | `BINARY_OP`, `UNARY_OP` |
| Control flow | `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_TRUE` |
| Failure handling | `PUSH_HANDLER`, `POP_HANDLER`, `CLAUSE_CHECK`, `FAILABLE_UNWRAP` |
| Calls | `CALL`, `RETURN` |
| Containers | `GET_INDEX`, `SET_INDEX`, `GET_MEMBER`, `SET_MEMBER`, `ARRAY_LITERAL`, `MAP_LITERAL`, `STRUCT_LITERAL`, `RANGE` |
| Iteration | `GET_ITER`, `FOR_ITER` |
| Definitions | `MAKE_FUNCTION`, `MAKE_CLASS` |
| Concurrency | `SPAWN`, `SYNC`, `RACE` |

Run `verse dis <file>` to see real output, or read `disasm.py` (short -
it just recurses into every nested `Chunk` reachable from `MAKE_FUNCTION`/
`MAKE_CLASS` operands and parameter/field default chunks).

## Why not compile straight to a tree-walking interpreter?

An AST-walking interpreter (no bytecode at all) would have been less
code. Two things earned bytecode its keep here: (1) `verse dis` as a
genuinely useful debugging/teaching artifact - seeing what an `if` or a
`for` filter clause actually compiles to makes the failure-handling
design concrete in a way prose doesn't; and (2) jumps make loop control
flow (`break`/`continue`) and the handler-stack failure model simpler to
reason about than the equivalent tree-walking code (which typically
needs its own control-flow-signal exceptions for break/continue/return,
on top of whatever it uses for failure).
