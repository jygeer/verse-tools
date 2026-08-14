"""Every file in examples/ should run to completion without error, and
its Main() (if present) is auto-invoked, matching `verse run`'s
behavior. This is as much a regression test for the whole pipeline as
it is documentation that the examples actually work."""

from pathlib import Path

import pytest

from versetools.compiler import compile_program
from versetools.lexer import tokenize
from versetools.parser import parse
from versetools.values import VFunction
from versetools.vm import VM

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.verse"))


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_runs_cleanly(path: Path):
    source = path.read_text(encoding="utf-8")
    tokens = tokenize(source)
    program = parse(tokens)
    chunk = compile_program(program)

    lines: list[str] = []
    vm = VM(output=lines.append)
    vm.run_chunk(chunk)

    main_fn = vm.globals.vars.get("Main")
    if isinstance(main_fn, VFunction) and all(
        p.default_chunk is not None for p in main_fn.proto.params
    ):
        vm.call_function(main_fn, [])

    assert lines, f"{path.name} produced no output"


def test_at_least_one_example_exists():
    assert EXAMPLE_FILES
