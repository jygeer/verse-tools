# Verse-core language reference

This document specifies **Verse-core**, the subset of Verse that
`versetools` lexes, parses, compiles, and runs. It aims to read close
enough to real Verse that programs *look* right, while staying small
enough to implement (and read the implementation of) in an afternoon.
Every deliberate simplification versus Epic's actual language is called
out inline and collected in
[`differences-from-verse.md`](differences-from-verse.md).

## Contents

- [Lexical structure](#lexical-structure)
- [Types and literals](#types-and-literals)
- [Operators](#operators)
- [Variables: `:=`, `var`, `set`](#variables--var-set)
- [Functions](#functions)
- [Control flow](#control-flow)
- [Classes](#classes)
- [Failure and options](#failure-and-options)
- [Concurrency: spawn / sync / race](#concurrency-spawn--sync--race)
- [Standard library](#standard-library)
- [Grammar summary](#grammar-summary)

## Lexical structure

**Indentation, not braces.** Blocks are introduced by a header ending in
`:` (for `if`/`for`/`loop`/`class`/`spawn`/`sync`/`race`) or `=` (for a
function body), followed by a newline and one indentation level of
statements - exactly like Python. Use spaces only; a tab in leading
whitespace is a lexer error. Dedenting back to (or below) the enclosing
level ends the block.

```verse
if (X > 0):
    Print("positive")
else:
    Print("non-positive")
```

A block can also be written inline, without indentation, for `if` and
`for`:

```verse
if (X > 0) then Print("positive") else Print("non-positive")
for (N : 1..3) do Print(ToString(N))
```

**Comments.** `# to end of line`, and `<# block comments #>` (which may
span multiple lines but do not nest).

**Identifiers.** ASCII letters, digits, underscore, not starting with a
digit. By convention (not enforced) types/functions/classes are
`PascalCase` and locals are too - Verse doesn't case-distinguish
identifier roles the way some languages do.

**Line joining.** Inside `(...)`, `[...]`, `{...}`, newlines don't end a
statement, so literals and argument lists can wrap freely:

```verse
Nums := array{
    1, 2, 3,
    4, 5,
}
```

## Types and literals

| Type | Example literal | Notes |
|---|---|---|
| `int` | `42`, `-7` | arbitrary-precision (backed by Python `int`) |
| `float` | `3.14`, `1e-3` | backed by Python `float` |
| `string` | `"hello\n"` | escapes: `\n \t \r \\ \" \0` |
| `logic` | `true`, `false` | **not** interchangeable with `int` - see below |
| `void` | *(no literal)* | the value a function returns when it has nothing meaningful to return |
| `[]T` (array) | `array{1, 2, 3}` | homogeneous in spirit, not enforced at runtime |
| `[K]V` (map) | `map{"a" => 1, "b" => 2}` | keys must be a primitive (int/float/string/logic) |
| `a..b` (range) | `0..9` | inclusive of both ends; only over `int` |
| `?T` (option) | `option(X)` for present, `false` for absent | see [Failure and options](#failure-and-options) |
| a class type | `Point{X := 1, Y := 2}` | see [Classes](#classes) |

`logic` is a distinct type from `int` - `true = 1` is `false`, and
arithmetic on `true`/`false` is an error. In Verse-core this is enforced
dynamically by default, or ahead of time with the opt-in checker
(`verse check <file>` / `verse run --strict`; see differences doc).

## Operators

From lowest to highest precedence:

| Precedence | Operators | Associativity |
|---|---|---|
| 1 (lowest) | `or` | left, short-circuit |
| 2 | `and` | left, short-circuit |
| 3 | `not` (prefix) | - |
| 4 | `=` `<>` `<` `<=` `>` `>=` | non-chaining |
| 5 | `..` (range) | - |
| 6 | `+` `-` | left |
| 7 | `*` `/` `%` | left |
| 8 | unary `-` | prefix |
| 9 (highest) | call `()`, index `[]`, member `.`, unwrap `?` | left |

`=` is equality *comparison* (not assignment - assignment is the
statement-level `set`, see below); `<>` is not-equal. `/` always
performs floating-point division; `%` is modulo (sign follows the
dividend for ints, `math.fmod` for floats). `+` also concatenates
strings (`"a" + "b"`) and arrays (`array{1} + array{2}`).

## Variables: `:=`, `var`, `set`

```verse
Pi := 3.14159          # constant binding, cannot be reassigned
X : int = 3            # typed constant binding

var Count : int = 0    # mutable binding
set Count = Count + 1  # assignment - only valid on a `var` binding
```

Type annotations participate in the opt-in static checker: `verse check`
and `verse run --strict` reject assigning an incompatible value into an
annotated binding (for example `set Count = "x"` when `Count : int`).

Assigning with `set` to a name that was never declared is a runtime
error (`RuntimeError: cannot assign to undefined name ...`) - `set`
can't implicitly create a binding.

`set` also targets fields and container elements:

```verse
set Player.Health = 100
set Scores[0] = 10
```

**Scoping note:** bindings are block-scoped. A name introduced with `:=`
inside an `if`/`for`/`loop` body is visible only inside that block and is
out of scope after the block ends.

## Functions

```verse
Add(X : int, Y : int) : int =
    return X + Y

# a trailing bare expression is the implicit return value - no `return`
# needed:
Square(X : int) : int =
    X * X

# parameters can have defaults:
Greet(Name : string, Greeting : string = "Hello") : string =
    return Greeting + ", " + Name + "!"
```

Only a **literal trailing expression** (or an explicit `return`) is
treated as the function's result. If the body's last statement is
anything else (an `if`, a `for`, a `var` declaration, ...), the function
implicitly returns `void` unless it hits an explicit `return` along the
way. Always use `return` for conditional results:

```verse
# WRONG in this subset: the `if` here does NOT make the function return
# A or B - falls through to `void`.
Bad(X : int) : int =
    if (X > 0):
        1
    else:
        2

# RIGHT:
Good(X : int) : int =
    if (X > 0):
        return 1
    else:
        return 2
```

**Effect specifiers** (`<decides>`, `<transacts>`, ...) are still parsed
and attached to the function for documentation/introspection, but are not
statically enforced yet - any function may fail, whether or not it
declares `<decides>`. See [Failure and options](#failure-and-options).

## Control flow

### `if`

```verse
if (Cond):
    ...
else if (OtherCond):
    ...
else:
    ...
```

An `if`'s condition is a comma-separated list of **clauses**, ANDed
together, each either a plain boolean expression or a `Name := Expr`
*binding clause* that makes `Name` available (as the unwrapped success
value) in the `then` branch and everything after it in the function:

```verse
if (Player := FindPlayer(Id), Player.Health > 0):
    Print("alive: " + Player.Name)
```

`if` is also an **expression** (inline form only):

```verse
Label := if (X > 0) then "positive" else "non-positive"
```

### `for`

```verse
for (X : Collection):
    ...

# with a filter clause - skips elements that don't match, doesn't fail
# the loop:
for (X : Collection, X > 0):
    ...
```

Iterates arrays (elements), ranges (`a..b`, inclusive ints), and maps
(each iteration binds a 2-element `array{Key, Value}`).

### `loop`, `break`, `continue`

```verse
loop:
    ...
    if (Done):
        break
    continue
```

`loop` is unconditional; combine with `break`/`if` for early exit.

## Classes

```verse
shape := class:
    Name : string = "shape"
    Area()<transacts> : float =
        return 0.0
    Describe()<transacts> : string =
        return self.Name + " area=" + ToString(self.Area())

circle := class(shape):
    Radius : float = 1.0
    Area() : float =                # overrides shape.Area
        return 3.14159 * self.Radius * self.Radius

C := circle{Name := "c1", Radius := 2.0}
Print(C.Describe())    # dynamic dispatch calls circle's Area()
```

- `ClassName := class:` / `ClassName := class(BaseName):` declares a
  class (single inheritance only). The base class must already be
  declared above it in the file.
- Fields declare a name, a type annotation, and/or a default value
  expression (evaluated fresh per instance).
- `ClassName{Field := Value, ...}` constructs an instance; omitted
  fields take their declared default.
- Methods are ordinary function declarations inside the class body;
  `self` refers to the receiving instance and is resolved dynamically
  (so overriding works as shown above).
- `set Instance.Field = Value` assigns a field; assigning to an
  undeclared field name is a runtime error.

## Failure and options

Real Verse models "this might not produce a value" as a first-class
*effect* (`decides`) rather than exceptions: any expression in a
decides context can *fail*, and failure propagates outward until
something handles it. Verse-core keeps the shape of this without a
static effect checker:

- **`option(X)`** builds a present option; the literal **`false`** doubles
  as both the logic value and the canonical "absent/failed" value -
  exactly as in real Verse.
- **`Expr?`** unwraps an option (or passes through a non-option value
  unchanged) - if the value is absent (or is the logic `false`), it
  raises a failure that propagates out of the *current function call*
  to its caller.
- **`if (Name := Expr):`** is the normal way to *handle* a failure: if
  `Expr` fails (or evaluates to `false`), the whole clause is treated as
  failed and the `else` branch runs instead - `Name` is only bound in
  the success path.
- **`for (X : Xs, Filter):`** treats a failing filter clause as "skip
  this element", not "fail the loop".
- A function conventionally signals its own failure to callers by
  **`return false`** - since `false` triggers the same handling as an
  unwrap failure at the call site:

```verse
SafeDivide(A : int, B : int)<decides> : float =
    if (B <> 0):
        return A / B
    else:
        return false

Main() : void =
    if (R := SafeDivide(10, 0)):
        Print(ToString(R))
    else:
        Print("cannot divide by zero")
```

See [`differences-from-verse.md`](differences-from-verse.md) for the
precise (and narrower-than-real-Verse) set of places failure actually
propagates in this subset - notably, a bare failing expression
mid-function body does **not** automatically fail the function here;
use `return false` explicitly.

## Concurrency: spawn / sync / race

Verse-core runs on a single-threaded **cooperative** scheduler that
switches tasks after every bytecode instruction - real parallelism
isn't the point, interleaving semantics are. Full design in
[`architecture.md`](architecture.md#concurrency-model).

```verse
spawn:                 # start a background task, don't wait for it
    DoSomethingSlow()

Results := sync:       # run every top-level statement as a concurrent
    TaskA()             # branch, wait for ALL of them, collect an
    TaskB()              # array of their results (in branch order)

Winner := race:        # run every branch concurrently, take the FIRST
    TaskA()              # one to finish, cancel the rest (their partial
    TaskB()              # side effects up to that point still happened)
```

## Standard library

| Function | Signature | Description |
|---|---|---|
| `Print(X)` | `(any) -> void` | print `X` (unquoted for strings) |
| `Log(X)` | `(any) -> void` | like `Print`, prefixed `[Log]` |
| `ToString(X)` | `(any) -> string` | string representation of any value |
| `option(X)` | `(any) -> ?any` | wrap `X` as a present option |
| `Abs(X)` | `(int\|float) -> same` | absolute value |
| `Min(A, B)` / `Max(A, B)` | `(int\|float, int\|float) -> same` | |
| `Floor(X)` / `Ceil(X)` | `(float) -> int` | |
| `Sqrt(X)` | `(int\|float) -> float` | error on negative input |
| `Length(X)` | `(array\|map\|string) -> int` | |
| `Contains(C, X)` | `(array\|map\|string, any) -> logic` | membership test |
| `Keys(M)` / `Values(M)` | `(map) -> array` | |

## Grammar summary

```
program     := statement*
statement   := var_decl | assign | if_stmt | for_stmt | loop_stmt
             | break_stmt | continue_stmt | return_stmt
             | func_decl | class_decl | const_decl | expr_stmt

var_decl    := "var" IDENT (":" type)? ("=" expression)? NEWLINE
const_decl  := IDENT ":=" expression NEWLINE
             | IDENT ":" type "=" expression NEWLINE
assign      := "set" postfix "=" expression NEWLINE

func_decl   := IDENT "(" params? ")" effects? (":" type)? "=" block
params      := param ("," param)*
param       := IDENT (":" type)? ("=" expression)?
effects     := ("<" IDENT ("," IDENT)* ">")+

class_decl  := IDENT ":=" "class" ("(" IDENT ")")? ":" NEWLINE INDENT
                   (field_decl | func_decl)+
               DEDENT
field_decl  := IDENT (":" type)? ("=" expression)? NEWLINE

if_stmt     := "if" "(" clauses ")" ":" block ("else" (if_stmt | ":" block))?
             | "if" "(" clauses ")" "then" expression ("else" expression)? NEWLINE
clauses     := clause ("," clause)*
clause      := (IDENT ":=")? expression

for_stmt    := "for" "(" IDENT ":" expression ("," expression)* ")"
                   (":" block | "do" expression NEWLINE)

loop_stmt   := "loop" ":" block
break_stmt  := "break" NEWLINE
continue_stmt := "continue" NEWLINE
return_stmt := "return" expression? NEWLINE

block       := NEWLINE INDENT statement+ DEDENT | statement

expression  := or_expr
or_expr     := and_expr ("or" and_expr)*
and_expr    := not_expr ("and" not_expr)*
not_expr    := "not" not_expr | comparison
comparison  := range (("=" | "<>" | "<" | "<=" | ">" | ">=") range)?
range       := additive (".." additive)?
additive    := multiplicative (("+" | "-") multiplicative)*
multiplicative := unary (("*" | "/" | "%") unary)*
unary       := "-" unary | postfix
postfix     := primary ( "(" args ")" | "[" expression "]"
                        | "." IDENT | "?" )*
primary     := INT | FLOAT | STRING | "true" | "false" | "self"
             | IDENT | "(" expression ")"
             | IDENT "{" array_items | map_items | struct_fields "}"
             | if_expr | spawn_expr | sync_expr | race_expr

if_expr     := "if" "(" clauses ")" "then" expression ("else" expression)?
spawn_expr  := "spawn" ":" block
sync_expr   := "sync" ":" block
race_expr   := "race" ":" block

type        := "?" type | "[" "]" type | "[" type "]" type | IDENT
```
