from versetools.errors import VerseSyntaxError
from versetools.lexer import tokenize
from versetools.tokens import TokenType as T


def types(src: str) -> list[T]:
    return [t.type for t in tokenize(src)]


def test_indentation_produces_indent_dedent():
    src = "if (true):\n    X := 1\nY := 2\n"
    toks = tokenize(src)
    ts = [t.type for t in toks]
    assert T.INDENT in ts
    assert T.DEDENT in ts
    # DEDENT must occur before the 'Y' identifier of the second statement
    dedent_idx = ts.index(T.DEDENT)
    y_idx = next(i for i, t in enumerate(toks) if t.lexeme == "Y")
    assert dedent_idx < y_idx


def test_blank_and_comment_lines_do_not_affect_indentation():
    src = "X := 1\n\n# a comment\n\nY := 2\n"
    ts = types(src)
    assert T.INDENT not in ts
    assert T.DEDENT not in ts


def test_two_char_operators():
    ts = types("X := 1\nY <> 2\nZ <= 3\nW >= 4\nM => N\n")
    assert T.DEFINE in ts
    assert T.NE in ts
    assert T.LE in ts
    assert T.GE in ts
    assert T.FATARROW in ts


def test_string_escapes():
    tok = tokenize('"a\\nb\\t\\"c\\""')[0]
    assert tok.value == 'a\nb\t"c"'


def test_number_literals():
    toks = tokenize("1 2.5 3e2 4.5e-1\n")
    assert [t.type for t in toks[:4]] == [
        T.NUMBER_INT,
        T.NUMBER_FLOAT,
        T.NUMBER_FLOAT,
        T.NUMBER_FLOAT,
    ]
    assert toks[0].value == 1
    assert toks[1].value == 2.5


def test_tabs_rejected():
    try:
        tokenize("if (true):\n\tX := 1\n")
        assert False, "expected VerseSyntaxError"
    except VerseSyntaxError:
        pass


def test_bracket_suppresses_newline():
    ts = types("X := array{1,\n2,\n3}\n")
    assert ts.count(T.NEWLINE) == 1  # only the final line-ending newline
