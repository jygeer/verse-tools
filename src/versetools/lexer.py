"""Indentation-sensitive lexer for the versetools Verse-core dialect.

Verse (like Python) uses indentation to delimit blocks instead of braces,
but unlike Python it opens a block after specific keywords/operators
(`:`, or the `=` that starts a function body) rather than after every
compound statement header. This lexer does not try to understand which
tokens are "block openers" - that is the parser's job. Its only
responsibility is the classic indentation -> INDENT/DEDENT/NEWLINE
translation, after which the token stream can be parsed with an ordinary
recursive-descent parser.

Bracket nesting - `(...)`, `[...]`, `{...}` - suppresses NEWLINE/INDENT/
DEDENT generation, so expressions may freely wrap across physical lines
while inside brackets, exactly as in Python.
"""

from __future__ import annotations

from .errors import VerseSyntaxError
from .tokens import KEYWORDS, Token, TokenType

_SIMPLE_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "0": "\0",
}

_TWO_CHAR_OPS = {
    ":=": TokenType.DEFINE,
    "<>": TokenType.NE,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
    "=>": TokenType.FATARROW,
    "..": TokenType.DOTDOT,
}

_ONE_CHAR_OPS = {
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    ".": TokenType.DOT,
    "?": TokenType.QUESTION,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
}

_OPEN_BRACKETS = {"(", "[", "{"}
_CLOSE_BRACKETS = {")", "]", "}"}


class Lexer:
    def __init__(self, source: str):
        # Normalize line endings so column/line tracking stays simple.
        self.src = source.replace("\r\n", "\n").replace("\r", "\n")
        self.pos = 0
        self.line = 1
        self.col = 1
        self.paren_depth = 0
        self.indent_stack = [0]
        self.line_start = True
        self.tokens: list[Token] = []

    # -- low level cursor helpers -----------------------------------
    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.src[idx] if idx < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _at_end(self) -> bool:
        return self.pos >= len(self.src)

    def _emit(self, type_: TokenType, lexeme: str, value=None, line=None, col=None):
        self.tokens.append(Token(type_, lexeme, value, line or self.line, col or self.col))

    # -- top level ----------------------------------------------------
    def tokenize(self) -> list[Token]:
        while not self._at_end():
            if self.line_start and self.paren_depth == 0:
                if self._consume_indentation():
                    continue  # blank/comment-only line fully consumed
            self._scan_token()

        if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
            self._emit(TokenType.NEWLINE, "\\n")
        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self._emit(TokenType.DEDENT, "")
        self._emit(TokenType.EOF, "")
        return self.tokens

    # -- indentation ----------------------------------------------------
    def _consume_indentation(self) -> bool:
        """At the start of a logical line, measure indentation and emit
        INDENT/DEDENT as needed. Returns True if the line turned out to be
        blank or comment-only (nothing more to do for this line)."""
        start_col = self.col
        indent = 0
        while self._peek() in (" ", "\t"):
            if self._peek() == "\t":
                raise VerseSyntaxError(
                    "tabs are not allowed for indentation; use spaces", self.line
                )
            indent += 1
            self._advance()

        if self._peek() == "\n":
            self._advance()
            return True
        if self._at_end():
            return True
        if self._peek() == "#":
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            if self._peek() == "\n":
                self._advance()
            return True
        if self._peek() == "<" and self._peek(1) == "#":
            self._skip_block_comment()
            if self._peek() == "\n" or self._at_end():
                if self._peek() == "\n":
                    self._advance()
                return True
            # content follows an inline block comment on the same line;
            # treat the remaining text as if it started at this column.
            return self._consume_indentation()

        self.line_start = False
        top = self.indent_stack[-1]
        if indent > top:
            self.indent_stack.append(indent)
            self._emit(TokenType.INDENT, "", line=self.line, col=start_col)
        elif indent < top:
            while indent < self.indent_stack[-1]:
                self.indent_stack.pop()
                self._emit(TokenType.DEDENT, "", line=self.line, col=start_col)
            if indent != self.indent_stack[-1]:
                raise VerseSyntaxError("inconsistent indentation", self.line)
        return False

    def _skip_block_comment(self):
        start_line = self.line
        self._advance()  # '<'
        self._advance()  # '#'
        while True:
            if self._at_end():
                raise VerseSyntaxError("unterminated block comment", start_line)
            if self._peek() == "#" and self._peek(1) == ">":
                self._advance()
                self._advance()
                return
            self._advance()

    # -- token scanning ----------------------------------------------------
    def _scan_token(self):
        ch = self._peek()

        if ch == "\n":
            self._advance()
            if self.paren_depth == 0:
                if self.tokens and self.tokens[-1].type != TokenType.NEWLINE:
                    self._emit(TokenType.NEWLINE, "\\n")
                self.line_start = True
            return

        if ch in (" ", "\t"):
            self._advance()
            return

        if ch == "#":
            while not self._at_end() and self._peek() != "\n":
                self._advance()
            return

        if ch == "<" and self._peek(1) == "#":
            self._skip_block_comment()
            return

        line, col = self.line, self.col

        if ch.isdigit():
            self._scan_number(line, col)
            return

        if ch == '"':
            self._scan_string(line, col)
            return

        if ch.isalpha() or ch == "_":
            self._scan_identifier(line, col)
            return

        two = ch + self._peek(1)
        if two in _TWO_CHAR_OPS:
            self._advance()
            self._advance()
            self._emit(_TWO_CHAR_OPS[two], two, line=line, col=col)
            return

        if ch in _OPEN_BRACKETS:
            self.paren_depth += 1
        elif ch in _CLOSE_BRACKETS:
            if self.paren_depth > 0:
                self.paren_depth -= 1

        if ch in _ONE_CHAR_OPS:
            self._advance()
            self._emit(_ONE_CHAR_OPS[ch], ch, line=line, col=col)
            return

        raise VerseSyntaxError(f"unexpected character {ch!r}", line)

    def _scan_number(self, line: int, col: int):
        start = self.pos
        while self._peek().isdigit():
            self._advance()
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._advance()
            while self._peek().isdigit():
                self._advance()
        if self._peek() in ("e", "E") and (
            self._peek(1).isdigit() or (self._peek(1) in "+-" and self._peek(2).isdigit())
        ):
            is_float = True
            self._advance()
            if self._peek() in "+-":
                self._advance()
            while self._peek().isdigit():
                self._advance()
        text = self.src[start : self.pos]
        if is_float:
            self._emit(TokenType.NUMBER_FLOAT, text, float(text), line, col)
        else:
            self._emit(TokenType.NUMBER_INT, text, int(text), line, col)

    def _scan_string(self, line: int, col: int):
        self._advance()  # opening quote
        chars: list[str] = []
        while True:
            if self._at_end():
                raise VerseSyntaxError("unterminated string literal", line)
            ch = self._peek()
            if ch == "\n":
                raise VerseSyntaxError("unterminated string literal", line)
            if ch == '"':
                self._advance()
                break
            if ch == "\\":
                self._advance()
                esc = self._peek()
                if esc not in _SIMPLE_ESCAPES:
                    raise VerseSyntaxError(f"unknown escape sequence '\\{esc}'", self.line)
                chars.append(_SIMPLE_ESCAPES[esc])
                self._advance()
                continue
            chars.append(ch)
            self._advance()
        text = "".join(chars)
        self._emit(TokenType.STRING, text, text, line, col)

    def _scan_identifier(self, line: int, col: int):
        start = self.pos
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.src[start : self.pos]
        type_ = KEYWORDS.get(text, TokenType.IDENT)
        self._emit(type_, text, text, line, col)


def tokenize(source: str) -> list[Token]:
    return Lexer(source).tokenize()
