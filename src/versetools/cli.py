"""The `verse` command-line entry point.

Subcommands:
    verse run <file>       run a .verse script (auto-calls Main() if present)
    verse repl             start the interactive REPL
    verse tokens <file>    print the token stream (debugging aid)
    verse ast <file>       print the parsed AST (debugging aid)
    verse dis <file>       print compiled bytecode (debugging aid)
"""

from __future__ import annotations

import argparse
import sys

from .compiler import compile_program
from .disasm import disassemble
from .errors import VerseCompileError, VerseFailure, VerseRuntimeError, VerseSyntaxError
from .lexer import tokenize
from .parser import parse
from .repl import Repl
from .type_checker import check_program
from .values import VFunction
from .vm import VM


def _read_source(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"error: could not read {path!r}: {e}", file=sys.stderr)
        sys.exit(1)


def _parse_or_die(source: str, path: str):
    try:
        tokens = tokenize(source)
        return parse(tokens)
    except VerseSyntaxError as e:
        print(f"{path}:{e.line}: SyntaxError: {e.message}", file=sys.stderr)
        sys.exit(1)


def cmd_run(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    program = _parse_or_die(source, args.file)
    try:
        if args.strict:
            check_program(program)
        chunk = compile_program(program)
    except VerseCompileError as e:
        print(f"{args.file}: CompileError: {e.message}", file=sys.stderr)
        return 1

    vm = VM()
    try:
        vm.run_chunk(chunk)
        if not args.no_main:
            main_fn = vm.globals.vars.get("Main")
            if isinstance(main_fn, VFunction) and all(
                p.default_chunk is not None for p in main_fn.proto.params
            ):
                vm.call_function(main_fn, [])
    except VerseFailure:
        print(f"{args.file}: top-level expression failed", file=sys.stderr)
        return 1
    except VerseRuntimeError as e:
        suffix = f":{e.line}" if e.line else ""
        print(f"{args.file}{suffix}: RuntimeError: {e.message}", file=sys.stderr)
        return 1
    return 0


def cmd_repl(args: argparse.Namespace) -> int:
    Repl().run()
    return 0


def cmd_tokens(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    try:
        for tok in tokenize(source):
            print(tok)
    except VerseSyntaxError as e:
        print(f"{args.file}:{e.line}: SyntaxError: {e.message}", file=sys.stderr)
        return 1
    return 0


def cmd_ast(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    program = _parse_or_die(source, args.file)
    for stmt in program.body:
        print(stmt)
    return 0


def cmd_dis(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    program = _parse_or_die(source, args.file)
    try:
        chunk = compile_program(program)
    except VerseCompileError as e:
        print(f"{args.file}: CompileError: {e.message}", file=sys.stderr)
        return 1
    print("\n".join(disassemble(chunk)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    source = _read_source(args.file)
    program = _parse_or_die(source, args.file)
    try:
        check_program(program)
    except VerseCompileError as e:
        print(f"{args.file}: CompileError: {e.message}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="verse", description="An unofficial toolchain for Verse-core")
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a .verse script")
    run_p.add_argument("file")
    run_p.add_argument(
        "--no-main", action="store_true", help="don't auto-call a zero-argument Main()"
    )
    run_p.add_argument("--strict", action="store_true", help="type-check before running")
    run_p.set_defaults(func=cmd_run)

    repl_p = sub.add_parser("repl", help="start the interactive REPL")
    repl_p.set_defaults(func=cmd_repl)

    tokens_p = sub.add_parser("tokens", help="print the token stream for a file")
    tokens_p.add_argument("file")
    tokens_p.set_defaults(func=cmd_tokens)

    ast_p = sub.add_parser("ast", help="print the parsed AST for a file")
    ast_p.add_argument("file")
    ast_p.set_defaults(func=cmd_ast)

    dis_p = sub.add_parser("dis", help="print compiled bytecode for a file")
    dis_p.add_argument("file")
    dis_p.set_defaults(func=cmd_dis)

    check_p = sub.add_parser("check", help="type-check a .verse file without running it")
    check_p.add_argument("file")
    check_p.set_defaults(func=cmd_check)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
