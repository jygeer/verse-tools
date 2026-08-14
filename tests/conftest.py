import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from versetools.compiler import compile_program
from versetools.lexer import tokenize
from versetools.parser import parse
from versetools.vm import VM


class Runner:
    def __init__(self):
        self.lines: list[str] = []
        self.vm = VM(output=self.lines.append)

    def run(self, source: str):
        tokens = tokenize(source)
        program = parse(tokens)
        chunk = compile_program(program)
        return self.vm.run_chunk(chunk)

    @property
    def output(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture
def runner():
    return Runner()
