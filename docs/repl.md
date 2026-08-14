# The REPL

```sh
verse repl
```

```
versetools REPL - an unofficial Verse-core toolchain (type :help for help, :exit to quit)
verse> X := 5
verse> X + 10
15
verse> Print("hi")
hi
verse>
```

## Bare expressions echo their value

Unlike running a script, a lone expression's value is printed (using
Verse-shaped syntax - strings quoted, `true`/`false` for logic, etc.),
similar to `>>>` in Python's REPL. A statement that isn't a single bare
expression (a `var` decl, an `if`, a function definition, ...) just runs
normally with no extra echo.

## Session state persists

All top-level `:=`/`var` bindings and function/class definitions stay
live for the rest of the session - the REPL runs every input against
the same `VM` instance, so later lines can reference earlier ones.

## Multi-line input

Verse-core's blocks are indentation-based, so the REPL has to decide
when you're "still typing a block" versus done. The rule: if the first
line you type ends in `:` or `=`, or has an unclosed bracket, the REPL
switches to a continuation prompt (`...>`) and keeps reading lines
(indented as you'd write them in a file) until you enter a **blank
line**, which submits everything you typed:

```
verse> Greet(Name : string) : string =
  ...>     return "Hello, " + Name
  ...>
verse> Greet("Verse")
"Hello, Verse!"
```

The bracket/`:`/`=` check is a simple heuristic (string-aware bracket
counting, not a real parse) - it's meant to feel right for typical
input, not to be bulletproof for adversarial input.

## Meta-commands

| Command | Effect |
|---|---|
| `:help` | show a short help message |
| `:exit`, `:quit` | leave the REPL (same as Ctrl-D) |
| `:reset` | discard all session state and start a fresh VM |
| `:vars` | list every currently-defined global name |
| `:load <path>` | execute a `.verse` file into the current session |

`Ctrl-C` cancels whatever multi-line input you're in the middle of
(without exiting); `Ctrl-D` exits.

## Errors don't kill the session

A syntax, compile, or runtime error prints a message and returns you to
the `verse>` prompt with all prior state intact - only the input that
caused the error is discarded.
