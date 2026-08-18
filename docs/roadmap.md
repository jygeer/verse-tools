# Roadmap: toward full Verse alignment

This document lays out how `versetools` could grow from **Verse-core**
(the practical subset described in
[`language-reference.md`](language-reference.md), with every gap listed
in [`differences-from-verse.md`](differences-from-verse.md)) toward
something much closer to Epic's real Verse language - entirely outside
the Epic/UEFN ecosystem, with no dependency on Epic tooling, servers, or
proprietary sources. It also answers the performance question directly:
today's tree-shaped-but-flat, name-resolved, generator-per-instruction
Python VM is a deliberately simple *reference* implementation, not a
fast one, and this document lays out both an incremental path to make
it faster in place and a more radical path (a native core, shared
between a fast CLI and a WebAssembly build) to make it fast for real.

## Contents

- [Ground rules and non-goals](#ground-rules-and-non-goals)
- [How to read this document](#how-to-read-this-document)
- [Phase 1 - Language fidelity](#phase-1---language-fidelity)
- [Phase 2 - Performance-oriented VM redesign](#phase-2---performance-oriented-vm-redesign)
- [Phase 3 - WebAssembly target](#phase-3---webassembly-target)
- [Phase 4 - Tooling and ecosystem](#phase-4---tooling-and-ecosystem)
- [Sequencing and effort summary](#sequencing-and-effort-summary)
- [Risks and open questions](#risks-and-open-questions)
- [Immediate next steps](#immediate-next-steps)

## Ground rules and non-goals

- **No access to Epic's compiler source or formal spec.** Epic has not
  open-sourced the Verse compiler or published a formal grammar/type-
  system specification; everything here is bounded by what's observable
  in Epic's public documentation, published sample code, and community
  writeups. "Full alignment" therefore means *converging on documented,
  observable behavior*, not byte-for-byte compiler compatibility -
  some corners (exact numeric overflow behavior, exact effect-inference
  algorithm, exact error messages) may never be fully pinned down
  without Epic's source.
- **Never depend on UEFN/Fortnite.** This project's value is running
  Verse-shaped programs standalone. Nothing on this roadmap should
  require the Unreal Editor for Fortnite, an Epic account, or any
  network call to an Epic service. Device/creative APIs (players, HUD,
  triggers, persistence, ...) are explicitly out of scope forever, not
  just "not yet."
- **Trademark/branding care.** "Verse" and "UEFN" are Epic's names.
  Docs and code should keep saying "unofficial" and "Verse-core"
  prominently, exactly as today, however far the implementation
  progresses.
- **Backward compatibility within Verse-core.** Every Phase 1 item below
  is additive or tightens permissiveness into strictness - existing
  Verse-core programs (including everything in `examples/`) should keep
  working, or fail with a clear, actionable diagnostic pointing at the
  new rule, not a silent behavior change.

## How to read this document

Each numbered item has:

- **Goal** - what real-Verse behavior it closes the gap on.
- **Approach** - the concrete implementation strategy.
- **Effort** - rough sizing: **S** (days), **M** (1-3 weeks), **L**
  (1-2 months), **XL** (multi-month, likely needs its own design doc).
- **Depends on** - other items that should land first.

Sizes assume one experienced contributor working from this repo's
existing architecture (`docs/architecture.md`); they're for sequencing
conversations, not commitments.

## Additional reference baseline: `augustss/verse-semantics`

Alongside Epic's public docs, this roadmap now also treats
[`augustss/verse-semantics`](https://github.com/augustss/verse-semantics)
as the closest public, standalone reference implementation to compare
against when scoping Verse-core parity work. Concretely, that repo
already ships:

- a REPL and batch tester (`README.md`, `tests/tests.versetest`);
- a broader "Essential Verse" surface language in `FrontEnd/Expr.hs`,
  including anonymous functions, tuples/patterns, choice/search forms,
  and `verify`-related syntax; and
- a solver-backed verification track (`tests/verify.versetest`,
  `Core/Solver.hs`) for guard/domain reasoning that this project does
  not currently attempt.

That does **not** change the non-goals above: parity here means
"match the standalone language/runtime/tooling ideas that fit
Verse-core," not "inherit private Epic behavior" and not "grow UEFN or
Fortnite integration." The roadmap items below call out the biggest
gaps surfaced by that comparison.

## Phase 1 - Language fidelity

Goal of this phase: close the *semantic* gaps in
`differences-from-verse.md` without touching performance - i.e. make
Verse-core programs behave the way real Verse would, even if the
interpreter is still comparatively slow. This phase can proceed almost
entirely within the current architecture (lexer/parser/AST/bytecode
compiler/tree-walking-ish VM), because it's about *correctness*, not
*speed*.

### 1.1 Block scoping

- **Goal:** a `:=` inside an `if`/`for`/`loop` body is only visible
  inside that block, matching real Verse (today it leaks to the rest of
  the enclosing function - see the differences doc).
- **Approach:** give the compiler a notion of nested scopes again
  (it briefly had `PUSH_SCOPE`/`POP_SCOPE` in an earlier design pass,
  removed for simplicity). Two ways to get there:
  1. *Environment-chain scopes*: reintroduce `PUSH_SCOPE`/`POP_SCOPE`
     opcodes that create/discard a **child** `Environment` per block,
     keeping the current name-based lookup model. Minimal churn, but
     keeps the per-access dict-walk cost (see Phase 2).
  2. *Slot-based scopes* (preferred if sequenced after 2.1): resolve
     each block-local name to a numbered slot at compile time, with a
     scope-exit that just truncates the slot array. This is the
     "real" fix and should be done together with the Phase 2.1 locals
     redesign rather than twice.
- **Effort:** M (S if piggy-backed onto 2.1).
- **Depends on:** nothing strictly, but cheapest done alongside 2.1.

### 1.2 Static type system

**Status:** an initial opt-in checker has landed behind `verse check
<file>` / `verse run --strict`, covering monomorphic annotations,
assignments, calls, returns, and basic class/container checking. Effect
checking, generics, and flipping the checker on by default are still
remaining work.

- **Goal:** catch type errors (`1 + "x"`, calling a function with the
  wrong argument types, assigning a `string` into an `int` variable) at
  compile time instead of at the moment the bad value is produced (or
  never, if the branch that produces it is untested).
- **Approach:** add a **type-checking pass** between the parser and the
  compiler, operating on the AST:
  1. Start with a nominal type system covering the primitives already
     in the language (`int`, `float`, `string`, `logic`, `void`,
     `[]T`, `[K]V`, `?T`, class types) plus function signatures, all
     already parsed today as strings in `type_ann`/`return_type` and
     currently ignored - the parser work is done, only checking is
     missing.
  2. Build a symbol table pass that resolves every `type_ann` string
     into a real `Type` value (a small closed sum type: `IntType`,
     `FloatType`, `StringType`, `LogicType`, `VoidType`, `ArrayType`,
     `MapType`, `OptionType`, `ClassType`, `FunctionType`).
  3. Check expressions bottom-up (Hindley-Milner is overkill here since
     Verse is nominally, not structurally, generic-inferred at the
     surface-syntax level available to us - a straightforward
     bidirectional/"local type inference" pass is enough).
  4. Ship it as **opt-in** first (`verse check <file>` / `--strict`
     flag on `verse run`), so existing dynamically-checked behavior
     doesn't break anyone, then flip the default once the example
     corpus and test suite are clean under it.
  5. Generics (`class Box<T>`, `Add<T>(A: T, B: T): T`) come after
     monomorphic checking works - track as a follow-on, not part of the
     first cut.
- **Effort:** L for monomorphic checking, +L for generics.
- **Depends on:** nothing else on this list, but should land before
  1.3's effect checker (effects are naturally piggybacked on the same
  pass).

### 1.3 Static effect system (`decides`/`transacts`/`varies`/`suspends`)

- **Goal:** the compiler statically knows which functions can fail
  (`decides`), so calling one without handling failure (`if (X := F())`
  or being `<decides>` yourself) is a compile error - the actual
  contract real Verse enforces, which today is parsed but not checked
  at all (any function may fail, per `differences-from-verse.md`).
- **Approach:** once 1.2's type pass exists, extend its symbol table
  entries with an effect set per function, inferred bottom-up:
  a function is (at least) `decides` if it calls another `decides`
  function outside of an `if`/`for` clause or doesn't handle every
  `?`/failing call internally. Compare the *declared* effect list
  against the *inferred minimum* and error on mismatch (in either
  direction - declaring `<decides>` on something that can't fail is
  also worth a warning). `transacts`/`varies`/`suspends` follow the
  same shape: infer bottom-up, check against declarations.
- **Effort:** L.
- **Depends on:** 1.2.

### 1.4 Full decides/failure semantics (real backtracking)

- **Goal:** *any* failing sub-expression anywhere in a decides context
  fails the whole context immediately - including a bare statement
  mid-function (today only `if`/`for` clauses and `?` propagate
  failure; see `differences-from-verse.md`) - and, further out, support
  for the effect's logic-programming heritage: a `decides` expression
  conceptually enumerable for multiple solutions, not just "first
  success or total failure."
- **Approach**, incrementally:
  1. *Universal failure propagation* (closes the documented gap): make
     every expression-statement's compiled code check for
     `false`/absent-option and raise `VerseFailure` if so, the same way
     `if`/`for` clauses already do (`CLAUSE_CHECK` in `bytecode.py`) -
     mechanically, statement-level `POP` becomes a `POP_CHECKED`
     variant. This is a genuinely small change to `compiler.py`
     (`_compile_stmt`'s `ExprStmt` case) and `vm.py`, and should be
     done early - it's the highest-value, lowest-effort item in this
     whole phase.
  2. *Multiple-solution enumeration* (the deep, XL-effort part): this
     needs the VM's failure model to stop being "raise an exception on
     first failure" and become "a decides expression is a generator of
     possible (bindings, continuation) pairs," i.e. genuine
     backtracking search, closer to how Prolog-family interpreters or
     effect-handler runtimes work. This likely means compiling
     `decides` functions to CPS (continuation-passing style) or
     building the VM's `for`/`if` clause evaluation on top of Python
     generators that can be resumed for the next solution rather than
     one-shot exceptions. This is a genuine research-and-design task,
     not a refactor - write a dedicated design doc before starting.
- **Effort:** S for 1 (do it now), XL for 2.
- **Depends on:** 1 has no dependencies; 2 benefits from 1.1 (block
  scoping) being done first so undoing bindings on backtrack is
  well-defined.

### 1.5 Value semantics for arrays and maps

- **Goal:** match real Verse's copy-on-write value semantics for
  `[]T`/`[K]V` - assigning one array to another should behave like an
  independent copy, not a shared mutable reference (today's `VArray`/
  `VMap` alias, per the differences doc).
- **Approach:** switch the backing representation to a **persistent
  (structurally-shared) data structure** - a persistent vector (HAMT- or
  RRB-tree-backed, as used by Clojure/Immutable.js) for arrays and a
  persistent hash map for maps - so copies are O(1) and mutation-in-
  place (`set Arr[I] = X` when `Arr` is a `var`) still doesn't disturb
  other holders of the "old" value. A pure-Python implementation (or a
  small vendored persistent-collections library) is enough for Phase 1;
  Phase 2's native core would reimplement the same data structure for
  speed.
- **Effort:** M.
- **Depends on:** nothing.

### 1.6 Classes: interfaces, access specifiers, abstractness

- **Goal:** close the remaining class-system gaps: multiple interface
  implementation (`class(Base) : Interface1, Interface2`), `<public>`/
  `<private>`/`<protected>` access specifiers enforced at compile time
  (needs 1.2's symbol table), abstract methods/classes.
- **Approach:** extend `ast_nodes.ClassDecl`/`bytecode.ClassSpec` to
  carry an interface list and per-member access specifiers (parsing
  most of this is additive to the existing grammar); enforcement is a
  compile-time check in the same pass as 1.2/1.3; abstract methods
  compile to a body that raises a clear "abstract method not
  overridden" error if a concrete subclass doesn't provide one (checked
  statically once 1.2 exists, not just at runtime).
- **Effort:** M.
- **Depends on:** 1.2 for compile-time access-specifier enforcement
  (an unchecked/runtime-only version can ship standalone first, S
  effort).

### 1.7 Modules and multi-file projects

- **Goal:** `using { ... }`-style imports, multiple source files
  compiled as one program, forward references across files (today:
  one flat namespace per VM/session, base classes must be declared
  textually earlier in the same file).
- **Approach:** add a project-level compilation unit concept: a
  manifest (or just "every `.verse` file under a root, dependency-
  ordered by a first pass that collects top-level declarations before
  resolving bodies" - which also incidentally removes the "base class
  must come first" restriction within a file). Each module gets its own
  namespace; `using` brings names into scope with Verse's real
  path-based module syntax.
- **Effort:** L.
- **Depends on:** none strictly, but much more useful once 1.2 exists
  (cross-file type checking).

### 1.8 Standard library breadth

- **Goal:** grow `stdlib.py` from the current ~14 functions toward the
  breadth of Epic's documented non-UEFN-specific digest modules -
  string manipulation, additional math, container helpers
  (`Sort`, `Reverse`, `Map`/`Filter`/`Reduce`-style array combinators,
  since Verse supports these), and a `<varies>`-tagged random-number
  API (deliberately absent today to keep the VM deterministic by
  default - see differences doc).
- **Approach:** mostly additive work in `stdlib.py`, following the same
  `VNative` pattern already established; the random API specifically
  should be seeded/deterministic-by-default in the VM (accept an
  optional seed) so `verse run`'s output stays reproducible unless a
  program explicitly asks for real entropy.
- **Effort:** S-M, ongoing.
- **Depends on:** 1.3 if you want `<varies>` statically checked;
  otherwise none.

### 1.9 Concurrency correctness

- **Goal:** structured-concurrency guarantees and real cancellation
  semantics for `race`'s losing branches (today: losers are just
  dropped from the scheduler with no cleanup hook - see differences
  doc), plus a richer `task` API (`Await`, cancellation tokens) beyond
  the current read-only `.Done`/`.Failed`/`.Result` fields.
- **Approach:** give spawned tasks an explicit cancellation signal
  (a cooperative flag checked at safe points, since there's no
  preemption within an instruction anyway) and a `defer`/cleanup-block
  construct that runs on both normal completion and cancellation -
  this is additive to the existing scheduler design in `vm.py`
  (`_tick_all`, `SYNC`/`RACE` opcodes), not a redesign.
- **Effort:** M.
- **Depends on:** none.

### 1.10 Anonymous functions and closure syntax

- **Goal:** reach parity with the reference implementation's first-class
  function surface area (`x:int => x + 1`, nested currying, and
  function-valued expressions in `tests/tests.versetest`), instead of
  requiring every callable to be introduced by a statement-level named
  `FuncDecl`.
- **Approach:** extend the parser/AST with lambda/function-expression
  nodes, then lower them through the existing `MAKE_FUNCTION` closure
  path the compiler/VM already use for nested named functions. Start
  with expression-level lambdas and capture semantics; only then worry
  about sugar-equivalence with every function-declaration form the
  reference repo accepts.
- **Effort:** M.
- **Depends on:** none strictly, though 1.2 makes the parameter/return
  diagnostics much better.

### 1.11 Tuples, destructuring, and splice patterns

- **Goal:** close the large data-model gap visible in the reference
  tests: tuple values, tuple parameter/pattern destructuring, and
  eventually `..rest`/splice forms used in both tuple patterns and call
  sites (`tests/tests.versetest`'s `Splice*`, `Pat*`, and higher-order
  cases).
- **Approach:** add tuple expressions/patterns as first-class AST nodes
  distinct from arrays, then thread them through the type checker,
  compiler, and VM as immutable fixed-arity product values. Sequence
  the work in layers: fixed-arity tuple literals/index-free
  destructuring first, variadic/splice forms second once the binding
  rules are nailed down.
- **Effort:** L.
- **Depends on:** 1.1 for sane scope boundaries during destructuring;
  1.2 is strongly preferred before splice-heavy typing rules.

### 1.12 Choice/search surface syntax on top of real backtracking

- **Goal:** match the reference implementation's logic-programming
  surface constructs - choice (`A | B`), `one{...}`, `all{...}`,
  `exists`, and related search-oriented idioms - rather than stopping at
  a hidden backtracking engine with no first-class syntax for it.
- **Approach:** keep 1.4.2 as the semantic prerequisite, then layer the
  extra syntax on top of that engine instead of inventing a parallel
  mechanism. `all{...}` should lower to "enumerate every successful
  branch and collect the results"; `one{...}` to first-success; choice
  and existential forms become sugar over the same resumable failure
  machinery.
- **Effort:** XL.
- **Depends on:** 1.4.2; 1.11 if tuple-pattern-heavy search examples are
  expected to work out of the gate.

## Phase 2 - Performance-oriented VM redesign

The current VM (`vm.py`) optimizes for *readability and correctness of
the failure/concurrency model* over speed - see
`docs/architecture.md` for why (name-based environments instead of
slots, a generator `yield` after literally every instruction whether or
not anything is concurrent). That was the right call for a reference
implementation; it is not the right call for anything performance-
sensitive. This phase has two tracks: **2a**, incremental wins that keep
the Python implementation as the one and only implementation, and
**2b**, a native core - which is also the foundation Phase 3 (WASM)
builds on, so read them together before deciding where to invest.

### 2a. Incremental, stay-in-Python wins

| # | Change | Why it helps | Effort |
|---|---|---|---|
| 2a.1 | Resolve locals to numbered slots at compile time (a real `LOAD_LOCAL idx`/`STORE_LOCAL idx`, upvalues captured by index like clox) instead of walking an `Environment` dict chain per access | Removes per-access hashing + chain walk, the single biggest hot-path cost today | M |
| 2a.2 | Only pay the generator-`yield`-per-instruction cost when concurrency is actually in play - compile two entry points per chunk (or check `len(vm.scheduler_tasks) == 0` and run a tight non-yielding loop) | Every instruction currently yields even in fully sequential programs, which is most programs | S |
| 2a.3 | Replace the `if/elif` opcode dispatch with a dispatch table (list indexed by `Op` int value -> handler) | Modest but easy CPython win; also a prerequisite for any bytecode-format change | S |
| 2a.4 | Encode `Chunk.code` as a flat array of ints (real bytecode - opcode + operand packed, e.g. via the `array` module or a `bytes`/`struct`-packed encoding) instead of a Python list of `Instr` objects | Cuts per-instruction object overhead and improves cache locality | M |
| 2a.5 | Cache/memoize global lookups (`LOAD_NAME` for functions/builtins that never get reassigned) - an inline cache keyed by chunk+pc, invalidated on `SET_NAME`/`STORE_NAME` to that name | Avoids repeated dict lookups for the extremely common "call a global function" case | M |

None of 2a requires a design doc; they're a good "make it faster without
betting the project" first step and should land before committing to
2b. Realistic expectation: a few-times speedup, not an order of
magnitude - CPython's own per-bytecode-instruction overhead is the
floor you'll hit.

### 2b. A native core (the order-of-magnitude path)

- **Goal:** an order-of-magnitude (or more) speedup, and - see Phase 3
  - a WebAssembly target that comes essentially for free from the same
  source.
- **Recommended approach:** reimplement the **compiler backend and VM**
  (not necessarily the lexer/parser, which are already cheap and not
  the bottleneck) in **Rust**, exposed to the existing Python CLI/REPL
  via [PyO3](https://pyo3.rs/)/[maturin](https://www.maturin.rs/) as a
  native extension module (`versetools._core`). Concretely:
  1. Port `bytecode.py`'s opcode set 1:1 (it's already a clean, small,
     stack-based instruction set - the design translates directly).
  2. Port `values.py`'s value representation to a tagged-union `enum
     Value` (Rust enums are a good fit for exactly this: `Int(i64)`,
     `Float(f64)`, `Str(Rc<str>)`, `Logic(bool)`, `Array(Rc<RefCell<
     Vec<Value>>>)`, ... - or, once 1.5's persistent-collections work is
     done in Python, port *that* representation instead of the current
     mutable one, so Phase 1 and Phase 2 reinforce each other rather
     than duplicating work).
  3. Port `vm.py`'s dispatch loop as a straightforward Rust `match` over
     the opcode - this alone (native code, no per-instruction Python
     object allocation, no dict-based name lookup once combined with
     2a.1's slot resolution) is where the real speedup comes from.
  4. Concurrency: Rust's `Generator`/coroutine story is less mature than
     Python's, but the scheduler doesn't need real generators - a
     resumable-frame struct (`pc`, operand stack, handler stack, kept
     alive between `_tick_all`-equivalent steps) models the same
     cooperative round-robin explicitly, which Rust is well-suited to
     (it's exactly a small hand-rolled state machine).
  5. Keep the **lexer, parser, and any future type/effect checker in
     Python** (or port them too, later, if profiling says they matter -
     they don't today; compilation is not the hot path, execution is),
     and have the Python `Compiler` emit a serialized bytecode format
     (a small, versioned binary or even just a JSON/CBOR intermediate
     representation) that the Rust core loads and executes. This keeps
     the porting effort focused on the part that actually needs to be
     fast, and keeps the parts that benefit most from Python's
     ergonomics (tree-shaped AST manipulation, error messages) where
     they are.
- **Effort:** XL (multi-month). Needs its own design doc before
  starting, particularly for the concurrency/scheduler translation and
  the Python<->Rust value-marshaling boundary (what crosses the FFI
  boundary and when - ideally: source in, compiled bytecode in, program
  output/errors out, nothing crossing the boundary *during* execution).
- **Depends on:** 2a should land first (cheap validation that the
  bottlenecks are where you think they are, via profiling, before
  committing to a rewrite) and 1.1/1.5 (block scoping and persistent
  containers) are much cheaper to design once, in Python, than to
  redesign twice.

## Phase 3 - WebAssembly target

Three genuinely different strategies exist here, with very different
cost/benefit profiles. They are **not mutually exclusive** - Strategy A
is a legitimate "ship something this week" stopgap while B/C are being
built.

| Strategy | What it is | Effort | Runtime speed | Notes |
|---|---|---|---|---|
| **A. Ship the existing Python VM inside WASM** (via [Pyodide](https://pyodide.org/)/[RustPython](https://rustpython.github.io/)) | Run the whole current `versetools` package unmodified inside a WASM-hosted Python runtime, for an in-browser playground | S | Slow (an interpreter, hosted inside another interpreter, hosted inside WASM) | Good for "let people try Verse-core in a browser tab" *today*, bad as a long-term performance story. Ship this first if a browser playground is wanted soon; treat it as disposable once B or C exists. |
| **B. Native Rust core compiled to `wasm32`** (this is Phase 2b's payoff) | The same Rust VM crate from 2b, built for both a native target (fast CLI) *and* `wasm32-unknown-unknown`/`wasm32-wasip1` (browser via [`wasm-bindgen`](https://rustwasm.github.io/wasm-bindgen/), or server/edge via any WASI runtime) from one source tree | (incremental once 2b exists) S-M | Near-native | **Recommended long-term target.** One VM implementation, two build outputs, no semantic drift between "the fast CLI" and "the browser build" - the single biggest advantage over A and C. |
| **C. A dedicated Verse-core -> WASM compiler backend** (bypass the bytecode VM at the target end; compile straight to WASM instructions) | A new `compiler` backend alongside (not replacing) `compiler.py`'s bytecode backend, emitting WAT/WASM directly (e.g. via the [`walrus`](https://github.com/bytecodealliance/walrus) or [`wasm-encoder`](https://github.com/bytecodealliance/wasm-tools) Rust crates, or the `wasmtime`/Binaryen toolchain) | XL | Fastest possible (no interpreter loop at all - each Verse function becomes a real WASM function) | Only worth it after B ships and profiling shows the *interpreter dispatch overhead itself* (not I/O, not the concurrency scheduler) is the bottleneck for a real target workload. The hard part isn't emitting WASM instructions for arithmetic/control-flow (straightforward) - it's `decides`-effect failure/backtracking (1.4) and closures/classes, which need either the WASM GC proposal (not yet universally shipped) or a hand-rolled arena allocator + manual reference counting, i.e. reimplementing a chunk of what a language runtime normally gets for free. |

**Recommendation:** do **A now if a browser demo is wanted soon**
(it's nearly free given the existing pure-Python implementation),
invest the real effort in **B** as part of 2b (it's the natural
byproduct of building a native core for speed anyway - don't build the
Rust VM *and separately* figure out WASM, build it once with both
targets in mind from day one), and treat **C** as a possible future
optimization only if B's interpreter-loop overhead is ever actually the
measured bottleneck for a workload that matters, given how much extra
complexity it adds for `decides`/closures.

## Phase 4 - Tooling and ecosystem

Lower-risk, highly parallelizable with the phases above - none of this
blocks or is blocked by Phase 1-3, so it can be picked up opportunistically.

- **Tree-sitter grammar** for real editor syntax highlighting (today,
  anyone editing `.verse` files gets no highlighting at all) - a
  moderate-effort, high-visibility win; the existing recursive-descent
  grammar in `parser.py` translates fairly directly into tree-sitter's
  grammar DSL. **Effort: M.**
- **Language server (LSP)**: once 1.2's type checker exists, an LSP
  server that surfaces the same diagnostics inline, plus go-to-
  definition/hover using the existing AST, is a fairly mechanical
  wrapper. **Effort: L, depends on 1.2.**
- **Debug adapter (DAP)**: given the VM already has an explicit `Frame`
  with `pc`/`stack`/`env` (see `vm.py`), a debug adapter that
  single-steps the dispatch loop and inspects frame state is very
  achievable without redesigning the VM - breakpoints as "stop before
  executing instruction N," which the existing per-instruction
  generator yield (2a.2 not withstanding - keep a debug-mode code path
  that always yields) makes easy. **Effort: M.**
- **Package manager / module registry**: only meaningful once 1.7
  (modules) exists; even then, start with "a directory of `.verse`
  files plus a lockfile-free `import "./local/path"`" rather than a
  registry/versioning system - that's a Phase 5+ conversation.
- **Conformance test corpus**: an ongoing, low-effort, high-value
  practice regardless of what else ships - whenever a real-Verse
  behavior is confirmed from Epic's public docs or sample code, add a
  Verse-core program + expected output to `tests/`, tagged with which
  differences-doc item it exercises. Curate a second stream of imported
  cases from `augustss/verse-semantics` (`tests/tests.versetest` and, if
  a verifier track is pursued, `tests/verify.versetest`) so parity with
  that public reference stays measurable too. This is what keeps
  "closer alignment" honest and measurable over time, rather than
  aspirational.
- **Reference-style verifier harness**: if parity with
  `verse-semantics`'s `verify(...)` workflow becomes a priority, add it
  as a distinct command/tooling track (`verse verify` or pytest-backed
  fixtures), reusing 1.2/1.3's static analysis where possible and only
  then considering a localized constraint solver inspired by
  `Core/Solver.hs`. Keep this explicitly optional until the interpreter
  semantics themselves are closer.

## Sequencing and effort summary

Rough recommended order, front-loading small/high-value items:

1. **1.4.1** universal failure propagation (S) - closes the most
   commonly-hit semantic gap for almost no cost.
2. **2a** (S-M each) - profile-guided quick performance wins; also
   validates where time is actually going before committing to 2b.
3. **1.1** block scoping (M, ideally alongside 2a.1's slot redesign).
4. **1.5** persistent array/map value semantics (M).
5. **1.2** static type checking (L) - unlocks 1.3, 1.6's access
   specifiers, and 4's LSP.
6. **1.3** static effect checking (L, depends on 1.2).
7. **1.10** anonymous functions (M) and **1.11** tuples/destructuring
   (L) - the biggest `verse-semantics` surface-language gaps not already
   tracked above.
8. **1.6**, **1.8**, **1.9** class/stdlib/concurrency rounding-out (M
   each, mostly independent, pick up opportunistically).
9. **1.7** modules (L).
10. **2b** native Rust core (XL) - once 1.1/1.5 have settled the
   scoping/value-representation questions so they're only designed
   once.
11. **3.B** wasm32 build of the same Rust core (S-M, rides on 10).
12. **1.4.2** true backtracking/multiple-solution `decides` (XL) - the
    single hardest, most research-y item on this list; sequence it
    whenever there's appetite for a dedicated design effort, largely
    independent of everything else.
13. **1.12** choice/search syntax (XL) - only after 12 makes the
    underlying enumeration semantics real.
14. **3.C** direct-to-WASM compiler backend - only if profiling of (11)
    says it's worth it.
15. **Phase 4** items - parallelizable throughout, particularly the
    conformance corpus, which should really start on day one rather
    than waiting for this list.

## Risks and open questions

- **Spec uncertainty.** Several of the "full alignment" targets above
  (exact effect-inference rules, exact numeric semantics, exact
  backtracking/enumeration behavior) are inferred from Epic's public
  documentation and observed sample behavior, not a formal spec. Expect
  to revise 1.2-1.4 as better information surfaces; keep the
  conformance corpus (Phase 4) as the living source of truth rather
  than this document.
- **WASM GC maturity.** Strategy 3.C's viability depends partly on how
  usable the WASM GC proposal is by the time it's attempted; if it's
  still immature, budget for hand-rolled memory management, which
  meaningfully raises 3.C's effort and risk.
- **Rust rewrite risk (2b).** A native core is a second implementation
  of the same semantics - it can drift from the Python reference unless
  the conformance corpus (Phase 4) is run against *both* and kept green
  on both from the day the Rust core can execute anything at all, not
  bolted on at the end.
- **Scope discipline.** Every item here should keep the project usable
  and correct as Verse-*core*, not silently grow into "attempting all
  of Verse including UEFN-specific bits" - if a future request implies
  device/creative APIs, that's a sign to say no, not to expand scope.

## Immediate next steps

If picking just a handful of items to start with:

1. Ship **1.4.1** (universal failure propagation) - small diff, closes
   a real semantic gap, no design doc needed.
2. Add a **profiling harness** (`verse run --profile` or a `pytest-
   benchmark` suite over the `examples/` corpus) before touching
   performance at all, so 2a's wins are measured, not assumed.
3. Land **2a.1-2a.3** (slot-based locals, skip-yield-when-sequential,
   dispatch table) as a single performance pass.
4. Start the **conformance corpus** (Phase 4) now, in parallel with
   everything else - it's cheap, ongoing, and is what turns "closer
   alignment" from a vibe into a number.
5. Write the **1.2 type-checker design doc** - it's the highest-leverage
   Phase 1 item (unlocks 1.3, 1.6, and the LSP) and the one most worth
   getting review on before writing code.
6. As part of (4), port a **small curated slice of
   `verse-semantics` tests** first (`tests/tests.versetest`) so future
   roadmap work on 1.10/1.11/1.12 has executable reference cases from
   day one.
