# versetools

An unofficial toolchain for **Verse-core**, a documented, practical
subset of Epic Games' [Verse programming language](https://dev.epicgames.com/documentation/en-us/uefn/verse-language-reference)
(the language used to script UEFN/Fortnite experiences). This is not
Epic software and does not talk to UEFN, Fortnite, or any Epic service -
it's a from-scratch lexer, parser, bytecode compiler, virtual machine,
and REPL that run Verse-*shaped* programs on your machine, in Python.

If you want the real thing, see Epic's own
[Verse language reference](https://dev.epicgames.com/documentation/en-us/uefn/verse-language-reference)
and [UEFN documentation](https://dev.epicgames.com/documentation/en-us/uefn/unreal-editor-for-fortnite-documentation).
This project exists to let you read, run, and experiment with
Verse-shaped code (functions, classes, options, decides-effect failure,
spawn/sync/race concurrency) outside of UEFN, and to have a small,
readable implementation of each toolchain stage to learn from.

**Exactly what's supported, and what deliberately isn't, is documented
in [`docs/differences-from-verse.md`](docs/differences-from-verse.md).
Read that before assuming any particular real-Verse feature works here.**

> This project was built with [Claude](https://claude.com/product/claude-code),
> Anthropic's AI coding assistant.

## Install

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

This installs a `verse` command (via the `[project.scripts]` entry
point in `pyproject.toml`).

## Quickstart

```sh
# Run a script (auto-calls a zero-argument Main() if one is defined)
verse run examples/hello.verse

# Start the REPL
verse repl

# Debugging aids
verse tokens examples/hello.verse   # print the token stream
verse ast examples/hello.verse      # print the parsed AST
verse dis examples/hello.verse      # print compiled bytecode
```

A minimal program:

```verse
Greet(Name : string) : string =
    return "Hello, " + Name + "!"

Main() : void =
    Print(Greet("Verse"))
```

```sh
$ verse run hello.verse
Hello, Verse!
```

More complete examples live in [`examples/`](examples/) - fizzbuzz,
control flow, arrays/maps, options and decides-effect failure, classes
with inheritance, and spawn/sync/race concurrency.

## Documentation

- [`docs/language-reference.md`](docs/language-reference.md) - the full
  Verse-core language spec: syntax, types, operators, functions,
  classes, options/failure, concurrency, and the standard library.
- [`docs/architecture.md`](docs/architecture.md) - how the toolchain is
  built: lexer -> parser -> AST -> bytecode compiler -> VM, the bytecode
  instruction set, and the concurrency model.
- [`docs/repl.md`](docs/repl.md) - using the interactive REPL.
- [`docs/differences-from-verse.md`](docs/differences-from-verse.md) -
  every place this subset diverges from real UEFN Verse, and why.
- [`docs/roadmap.md`](docs/roadmap.md) - how this could grow closer to
  full Verse (types, effects, real backtracking, block scoping, value
  semantics) and options for a faster VM and a WebAssembly target.

## Project layout

```
src/versetools/
    tokens.py       token types
    lexer.py        source -> token stream (indentation-sensitive)
    ast_nodes.py    AST node dataclasses
    parser.py       token stream -> AST (recursive descent)
    bytecode.py     opcode set, Chunk/FunctionProto/ClassSpec containers
    compiler.py     AST -> bytecode
    values.py       runtime value types + the name-based Environment
    vm.py           the stack-based bytecode VM and task scheduler
    stdlib.py       built-in functions (Print, Length, Sqrt, ...)
    repl.py         interactive REPL
    cli.py          `verse` command-line entry point
    disasm.py       bytecode disassembler (used by `verse dis`)
examples/           runnable .verse example programs
tests/              pytest suite (lexer, parser, VM, examples)
docs/               the documents linked above
```

## Running the tests

```sh
pip install -e ".[dev]"
pytest
```
