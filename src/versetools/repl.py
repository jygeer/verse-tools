"""The versetools interactive REPL.

Indentation-sensitive syntax makes a REPL slightly more involved than
usual: a line ending in `:` or `=` (an if/for/loop/class/function header)
or with unbalanced brackets needs more input before it can run at all,
and once that's true the natural terminator is a blank line - exactly
like Python's own REPL. See `_needs_more_input` for the (deliberately
simple, string-level) heuristic used to detect that state.

A lone expression is evaluated and its value echoed (like `>>>` in
Python), rather than silently discarded, which is the main ergonomic
difference from just piping lines into `verse run`.
"""

from __future__ import annotations

import sys

from . import ast_nodes as A
from .compiler import compile_expr, compile_program
from .errors import VerseCompileError, VerseFailure, VerseRuntimeError, VerseSyntaxError
from .lexer import tokenize
from .parser import parse
from .values import VOID, verse_repr
from .vm import VM

BANNER = """\
versetools REPL - an unofficial Verse-core toolchain (type :help for help, :exit to quit)"""

HELP = """\
:help            show this message
:exit, :quit     exit the REPL
:reset           clear all REPL-defined names and start fresh
:vars            list currently defined global names
:load <path>     execute a .verse file into the current session
Ctrl-D           exit
Ctrl-C           cancel the current (possibly multi-line) input

Multi-line input: a line ending in ':' or '=', or with an unbalanced
bracket, starts a block - keep typing and finish with a blank line.
"""


def _bracket_depth(text: str) -> int:
    depth = 0
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth


def _needs_more_input(first_line: str) -> bool:
    stripped = first_line.rstrip()
    if not stripped:
        return False
    if _bracket_depth(stripped) > 0:
        return True
    return stripped.endswith(":") or stripped.endswith("=")


class Repl:
    def __init__(self, vm: VM | None = None):
        self.vm = vm or VM()

    def run(self):
        print(BANNER)
        buffer: list[str] = []
        while True:
            try:
                prompt = "verse> " if not buffer else "  ...> "
                line = input(prompt)
            except EOFError:
                print()
                return
            except KeyboardInterrupt:
                print("^C")
                buffer = []
                continue

            if not buffer:
                stripped = line.strip()
                if stripped == "":
                    continue
                if stripped.startswith(":"):
                    if self._handle_meta(stripped) == "exit":
                        return
                    continue
                buffer.append(line)
                if _needs_more_input(line):
                    continue
                self._execute("\n".join(buffer))
                buffer = []
            else:
                if line.strip() == "":
                    self._execute("\n".join(buffer))
                    buffer = []
                else:
                    buffer.append(line)

    # -- meta commands ----------------------------------------------------
    def _handle_meta(self, command: str) -> str | None:
        parts = command[1:].split(None, 1)
        name = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""
        if name in ("exit", "quit"):
            return "exit"
        if name == "help":
            print(HELP)
        elif name == "reset":
            self.vm = VM()
            print("(session reset)")
        elif name == "vars":
            names = sorted(self.vm.globals.vars.keys())
            print(", ".join(names) if names else "(no names defined yet)")
        elif name == "load":
            self._load_file(rest.strip())
        else:
            print(f"unknown command ':{name}' - try :help")
        return None

    def _load_file(self, path: str):
        if not path:
            print("usage: :load <path>")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            print(f"could not read {path!r}: {e}")
            return
        self._execute(source)

    # -- execution ----------------------------------------------------
    def _execute(self, source: str):
        try:
            tokens = tokenize(source + "\n")
            program = parse(tokens)
        except VerseSyntaxError as e:
            print(f"SyntaxError: {e.message} (line {e.line})", file=sys.stderr)
            return

        try:
            if len(program.body) == 1 and isinstance(program.body[0], A.ExprStmt):
                chunk = compile_expr(program.body[0].expr)
                result = self.vm.run_chunk(chunk)
                if result is not VOID:
                    print(verse_repr(result))
            else:
                chunk = compile_program(program)
                self.vm.run_chunk(chunk)
        except VerseCompileError as e:
            print(f"CompileError: {e.message}", file=sys.stderr)
        except VerseFailure:
            print("(expression failed)", file=sys.stderr)
        except VerseRuntimeError as e:
            suffix = f" (line {e.line})" if e.line else ""
            print(f"RuntimeError: {e.message}{suffix}", file=sys.stderr)


def main():
    Repl().run()


if __name__ == "__main__":
    main()
