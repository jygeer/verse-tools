import pytest

from versetools.errors import VerseCompileError
from versetools.lexer import tokenize
from versetools.parser import parse
from versetools.type_checker import check_program


def check_src(src: str) -> None:
    check_program(parse(tokenize(src)))


def test_type_checker_rejects_mixed_addition():
    with pytest.raises(VerseCompileError, match="cannot add int and string"):
        check_src('Main() : void =\n    X := 1 + "x"\n')


def test_type_checker_rejects_bad_function_argument_type():
    with pytest.raises(VerseCompileError, match="argument 1"):
        check_src('AddOne(X : int) : int =\n    return X + 1\nPrint(ToString(AddOne("x")))\n')


def test_type_checker_rejects_assignment_type_mismatch():
    with pytest.raises(VerseCompileError, match="cannot assign string to int"):
        check_src('var Count : int = 0\nset Count = "x"\n')


def test_type_checker_rejects_return_type_mismatch():
    with pytest.raises(VerseCompileError, match="cannot return string from int function"):
        check_src('Describe() : int =\n    return "x"\n')


def test_type_checker_allows_decides_false_return():
    check_src(
        "SafeDivide(A : int, B : int)<decides> : float =\n"
        "    if (B <> 0):\n"
        "        return A / B\n"
        "    else:\n"
        "        return false\n"
    )
