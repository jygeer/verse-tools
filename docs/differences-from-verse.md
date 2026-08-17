# Differences from real Verse

`versetools` implements **Verse-core**, a deliberately smaller language
that looks like Epic's Verse and runs Verse-shaped programs, but is not
a compliant Verse implementation and never talks to UEFN or Fortnite.
This page is the authoritative list of where and why it diverges, so
nobody is surprised when a real-Verse idiom doesn't work here. If
something isn't mentioned below or in
[`language-reference.md`](language-reference.md), assume it's not
supported.

## Static type checking is opt-in; effect checking is now implemented for `decides`

Real Verse is statically typed with a real effect system (`decides`,
`transacts`, `varies`, `suspends`, ...) checked at compile time - you
cannot call a `<decides>` function without acknowledging it might fail,
and the compiler proves it.

Verse-core now has an **opt-in** static type checker (`verse check
<file>` or `verse run --strict <file>`) that catches many first-order
type mistakes - arithmetic on incompatible types, wrong argument types,
bad assignments into annotated variables, mismatched return types, and
class field/constructor mismatches - before the VM runs.

The type checker now also enforces the **`decides` effect** statically:
calling a `<decides>` function outside a guarded `if`/`for` clause, or
using `Expr?` failable-unwrap, from a function that does not itself
declare `<decides>` is a compile error under strict mode.  Effect
inference is bottom-up: when a nested function is declared `<decides>`,
its callers must either guard the call in an `if`/`for` clause or
themselves declare `<decides>`.

What it still does **not** have is a full effect checker for
`transacts`, `varies`, and `suspends` (those specifiers are still parsed
but not validated), generic types, or always-on static typing. Plain
`verse run <file>` keeps the old dynamic-only behavior for backward
compatibility while this first cut is still opt-in.

## Statement-level failure checks in `<decides>` functions

Verse-core now treats bare expression-statements inside `<decides>`
functions as failure checks too: if an expression statement evaluates to
`false` or an absent option, it raises `VerseFailure` just like
`if`/`for` clauses and `Expr?`.

## No backtracking, no multiple solutions

Real Verse's `decides` effect has roots in logic programming - a
`decides` expression can conceptually be retried with different
bindings, and constructs like `for` combined with failure can enumerate
multiple solutions. Verse-core's failure model is exception-based:
first failure wins, there is no retry/enumeration machinery. What you
get is "try once, fail fast, catch with `if`" - which covers the
overwhelmingly common use of `decides` (optional lookups, validated
input) but not its full logic-programming generality.

## No tail-expression propagation through control flow

Real Verse: the last expression of *any* block - including inside an
`if`/`for` - is that block's value, and this composes through nested
control flow to become a function's return value.

Verse-core only treats a function body's **literal final statement** as
its return value, and only if that statement is a bare expression (or
`return`). If the last statement is an `if`, `for`, `loop`, etc., the
function falls through to `void` unless it hits an explicit `return`.
Always use `return` for values produced conditionally - see the
[Functions](language-reference.md#functions) section for a worked
example. (Rationale: full tail-expression propagation requires the
compiler to recursively rewrite every block's exit points, which
interacts non-trivially with the failure-handler jump targets described
in the architecture doc; out of scope for this subset.)

## Classes are simpler

- Single inheritance only - `class(Base)`, no multiple base
  classes/mixins/interfaces.
- No access specifiers (`<public>`/`<private>`/...) - everything is
  accessible from anywhere.
- No abstract methods/classes.
- The base class must be declared textually earlier in the same file
  (no forward references, no multi-file resolution - see below).
- Class instance equality is Python object identity (`VInstance` doesn't
  define value equality) - two separately-constructed instances with
  identical fields are **not** `=`-equal in Verse-core, whereas real
  Verse structs typically compare by value.

## No modules

There is one flat namespace per VM (per script, or per REPL session).
There's no `using`, no multi-file projects, no package system.

## No UEFN/Fortnite APIs

No devices, triggers, players, HUD, persistence, or any other
Fortnite-Creative-specific API. Verse-core is the general-purpose core
of the language only.

## Concurrency is simulated, not real, and coarser-grained than real time

- Single OS thread; `spawn`/`sync`/`race` are a cooperative scheduler
  that switches after every VM instruction (see
  [`architecture.md`](architecture.md#vm-one-generator-cooperative-concurrency-for-free)),
  not real parallel execution and not real-time preemption.
- `spawn` returns a `task` value exposing only read-only `.Done`,
  `.Failed`, `.Result` fields - there's no `await`-style blocking API on
  a task handle beyond composing it into a `sync`/`race`.
- `race`'s "losing" branches are cancelled by simply no longer being
  scheduled - there's no `finally`/cleanup semantics, and any output or
  state mutation a losing branch performed before losing stands
  permanently.
- Any `spawn`ed task not yet joined by a `sync`/`race` is drained to
  completion before the program/REPL statement that spawned it returns
  control - true "runs forever in the background past program exit"
  fire-and-forget isn't implemented.
- No `<varies>`/randomness effect tracking, and no random-number builtin
  at all (kept the standard library deterministic).

## Numbers

- `int` is arbitrary precision (backed by Python's `int`), not a fixed
  64-bit integer.
- `/` always performs floating-point division regardless of operand
  types; there's no attempt to replicate whatever exact integer-division
  behavior real Verse's numeric tower defines.
- No fixed-width overflow behavior of any kind.

## Strings

- No multi-line string literals.
- No string interpolation syntax - build strings with `+` and
  `ToString`.
- Indexing (`S[i]`) returns a single-character string; there's no slice
  syntax (`S[a..b]`).

## Miscellaneous smaller omissions

- No `char` type as a concept distinct from length-1 `string`.
- No pattern-matching/destructuring beyond a `for` loop's single element
  binding (map iteration binds a synthetic `array{Key, Value}` pair
  rather than true destructuring syntax).
- No compound assignment operators (`+=`, etc.) - reassign with `set X
  = X + ...`.
- Comparison operators don't chain (`a < b < c` is a parse error; write
  `a < b and b < c`).
- `if`/`for` clause success-checking and `Expr?` are more permissive
  than real Verse's static failure typing: **any** value that isn't
  literally `false` or an absent option is treated as "succeeded",
  including e.g. `0` or `""`. Real Verse requires the expression to
  actually be decides-typed; Verse-core can't check that statically, so
  it falls back to a runtime rule instead.

## Tooling that doesn't exist in real Verse at all

The REPL, `verse tokens`/`verse ast`/`verse dis` debugging commands, and
the bytecode VM itself are entirely inventions of this project for
learning/experimentation - UEFN compiles and runs Verse differently
(and doesn't expose an interactive shell). Don't read anything in this
tool's CLI surface as evidence of how Epic's real toolchain works.
