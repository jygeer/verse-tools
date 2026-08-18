"""AST node definitions for the versetools Verse-core dialect.

Every node is a plain dataclass carrying a `line` number for diagnostics.
`Expr` and `Stmt` are marker base classes; `If` intentionally appears in
both positions because Verse's `if` is a decides-effect *expression* that
can also be used as a statement, exactly like in the real language.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Node:
    line: int = 0


class Expr(Node):
    pass


class Stmt(Node):
    pass


# ---------------------------------------------------------------- literals

@dataclass
class IntLiteral(Expr):
    value: int
    line: int = 0


@dataclass
class FloatLiteral(Expr):
    value: float
    line: int = 0


@dataclass
class StringLiteral(Expr):
    value: str
    line: int = 0


@dataclass
class LogicLiteral(Expr):
    value: bool
    line: int = 0


@dataclass
class ArrayLiteral(Expr):
    elements: list[Expr]
    line: int = 0


@dataclass
class MapLiteral(Expr):
    pairs: list[tuple[Expr, Expr]]
    line: int = 0


@dataclass
class StructLiteral(Expr):
    type_name: str
    fields: list[tuple[str, Expr]]
    line: int = 0


# --------------------------------------------------------------- expressions

@dataclass
class Identifier(Expr):
    name: str
    line: int = 0


@dataclass
class SelfExpr(Expr):
    line: int = 0


@dataclass
class Unary(Expr):
    op: str
    operand: Expr
    line: int = 0


@dataclass
class Binary(Expr):
    op: str
    left: Expr
    right: Expr
    line: int = 0


@dataclass
class Logical(Expr):
    op: str  # "and" | "or"
    left: Expr
    right: Expr
    line: int = 0


@dataclass
class Range(Expr):
    start: Expr
    end: Expr
    line: int = 0


@dataclass
class Call(Expr):
    callee: Expr
    args: list[Expr]
    line: int = 0


@dataclass
class Index(Expr):
    obj: Expr
    index: Expr
    line: int = 0


@dataclass
class Member(Expr):
    obj: Expr
    name: str
    line: int = 0


@dataclass
class FailableUnwrap(Expr):
    """`Expr?` - unwrap an option or propagate failure to the enclosing
    <decides> context."""

    operand: Expr
    line: int = 0


@dataclass
class IfClause:
    """One clause of an if-header: either a plain boolean expression, or
    a `Name := FailableExpr` binding clause whose unwrapped value becomes
    visible (as `Name`) in the then-branch. Clauses are ANDed together
    with decides-effect short-circuiting, exactly like real Verse."""

    name: str | None
    expr: Expr
    line: int = 0


@dataclass
class IfExpr(Expr):
    clauses: list[IfClause]
    then_branch: "Block"
    else_branch: "Block | None"
    line: int = 0


@dataclass
class SpawnExpr(Expr):
    body: Expr
    line: int = 0


@dataclass
class SyncExpr(Expr):
    items: list[Expr]
    line: int = 0


@dataclass
class RaceExpr(Expr):
    items: list[Expr]
    line: int = 0


# ---------------------------------------------------------------- patterns

@dataclass
class Param:
    name: str
    type_ann: str | None
    default: Expr | None = None
    line: int = 0


# --------------------------------------------------------------- statements

@dataclass
class Block(Stmt):
    statements: list[Stmt] = field(default_factory=list)
    line: int = 0


@dataclass
class ExprStmt(Stmt):
    expr: Expr
    line: int = 0


@dataclass
class VarDecl(Stmt):
    name: str
    type_ann: str | None
    value: Expr | None
    mutable: bool
    line: int = 0


@dataclass
class Assign(Stmt):
    target: Expr  # Identifier | Member | Index
    value: Expr
    line: int = 0


@dataclass
class FuncDecl(Stmt):
    name: str
    params: list[Param]
    effects: list[str]
    return_type: str | None
    body: Block
    access: str = "public"
    is_abstract: bool = False
    line: int = 0


@dataclass
class FieldDecl:
    name: str
    type_ann: str | None
    default: Expr | None
    access: str = "public"
    line: int = 0


@dataclass
class ClassDecl(Stmt):
    name: str
    base: str | None
    interfaces: list[str]
    fields: list[FieldDecl]
    methods: list[FuncDecl]
    is_abstract: bool = False
    line: int = 0


@dataclass
class If(Stmt):
    clauses: list[IfClause]
    then_branch: Block
    else_branch: "Block | If | None"
    line: int = 0


@dataclass
class For(Stmt):
    var_name: str
    iterable: Expr
    filters: list[Expr]
    body: Block
    line: int = 0


@dataclass
class Loop(Stmt):
    body: Block
    line: int = 0


@dataclass
class Break(Stmt):
    line: int = 0


@dataclass
class Continue(Stmt):
    line: int = 0


@dataclass
class Return(Stmt):
    value: Expr | None
    line: int = 0


@dataclass
class Program(Node):
    body: list[Stmt] = field(default_factory=list)
    line: int = 0
