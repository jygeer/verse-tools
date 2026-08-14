"""Token types for the versetools lexer.

The token set covers the practical core subset of Verse documented in
docs/language-reference.md. See that document for the full grammar; this
module only defines the vocabulary the lexer produces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # Literals
    NUMBER_INT = auto()
    NUMBER_FLOAT = auto()
    STRING = auto()
    IDENT = auto()

    # Keywords
    VAR = auto()
    SET = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    FOR = auto()
    DO = auto()
    LOOP = auto()
    BREAK = auto()
    CONTINUE = auto()
    RETURN = auto()
    CLASS = auto()
    TRUE = auto()
    FALSE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    IN = auto()
    SPAWN = auto()
    SYNC = auto()
    RACE = auto()
    SELF = auto()

    # Punctuation
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    COLON = auto()
    DOT = auto()
    DOTDOT = auto()
    QUESTION = auto()
    FATARROW = auto()  # =>

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    ASSIGN = auto()  # =
    DEFINE = auto()  # :=
    NE = auto()  # <>
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()

    # Structure
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


KEYWORDS = {
    "var": TokenType.VAR,
    "set": TokenType.SET,
    "if": TokenType.IF,
    "then": TokenType.THEN,
    "else": TokenType.ELSE,
    "for": TokenType.FOR,
    "do": TokenType.DO,
    "loop": TokenType.LOOP,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "return": TokenType.RETURN,
    "class": TokenType.CLASS,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "in": TokenType.IN,
    "spawn": TokenType.SPAWN,
    "sync": TokenType.SYNC,
    "race": TokenType.RACE,
    "self": TokenType.SELF,
}


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    value: object
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Token({self.type.name}, {self.lexeme!r}, line={self.line})"
