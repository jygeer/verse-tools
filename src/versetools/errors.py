"""Exception types shared across the toolchain's pipeline stages."""

from __future__ import annotations


class VerseError(Exception):
    """Base class for all versetools errors."""


class VerseSyntaxError(VerseError):
    def __init__(self, message: str, line: int, col: int = 0):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"line {line}: {message}")


class VerseCompileError(VerseError):
    def __init__(self, message: str, line: int = 0):
        self.message = message
        self.line = line
        super().__init__(f"line {line}: {message}" if line else message)


class VerseRuntimeError(VerseError):
    """A genuine host-level runtime error (e.g. divide by zero, bad index).

    This is distinct from a Verse *failure*, which is a first-class,
    catchable control-flow signal modeled by VerseFailure below.
    """

    def __init__(self, message: str, line: int = 0):
        self.message = message
        self.line = line
        super().__init__(message)


class VerseFailure(Exception):
    """Signals that a `<decides>`-effect expression failed.

    In real Verse, failure is a control-flow effect: expressions in a
    `<decides>` context can fail instead of returning, and failure
    propagates up until something catches it (an `if`, `for` filter, or
    the enclosing function itself failing). We model that propagation
    with this lightweight exception rather than true backtracking -
    see docs/differences-from-verse.md.
    """
