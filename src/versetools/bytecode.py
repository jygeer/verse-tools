"""Bytecode instruction set and container types.

versetools compiles the AST into a flat, linear sequence of `Instr`
objects per function (a `Chunk`) executed by a stack-based dispatch loop
(see vm.py). Control flow (if/for/loop/break/continue) is expressed with
absolute jump targets patched in by the compiler; there is no nesting at
the bytecode level.

Variable storage is *not* stack-slot based: each function call owns one
flat name->value environment (see docs/architecture.md for why), so the
opcode set has no LOAD_LOCAL/LOAD_UPVALUE distinction - only LOAD_NAME /
STORE_NAME / SET_NAME, which walk a small environment chain at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Op(Enum):
    LOAD_CONST = auto()
    LOAD_NAME = auto()
    STORE_NAME = auto()   # introduce a new binding in the current frame
    SET_NAME = auto()     # assign to an existing binding (walks the chain)
    PUSH_SCOPE = auto()   # create a child environment for block-local bindings
    POP_SCOPE = auto()    # discard the current child environment

    POP = auto()
    POP_CHECKED = auto()    # pops and discards value; raises VerseFailure on false/absent option

    BINARY_OP = auto()    # arg: str operator
    UNARY_OP = auto()      # arg: str operator

    JUMP = auto()             # arg: target index
    JUMP_IF_FALSE = auto()    # peeks TOS; arg: target index
    JUMP_IF_TRUE = auto()     # peeks TOS; arg: target index

    PUSH_HANDLER = auto()  # arg: target index to jump to on VerseFailure
    POP_HANDLER = auto()
    CLAUSE_CHECK = auto()   # pops a decides-clause result; arg: target index
                            # to jump to on failure, else pushes the
                            # unwrapped/bound value back for STORE_NAME/POP

    CALL = auto()          # arg: argument count
    RETURN = auto()

    GET_INDEX = auto()
    SET_INDEX = auto()
    GET_MEMBER = auto()    # arg: str name
    SET_MEMBER = auto()    # arg: str name

    FAILABLE_UNWRAP = auto()

    ARRAY_LITERAL = auto()  # arg: element count
    MAP_LITERAL = auto()    # arg: pair count
    STRUCT_LITERAL = auto()  # arg: (type_name, [field_name, ...])
    RANGE = auto()

    GET_ITER = auto()
    FOR_ITER = auto()      # arg: target index to jump to when exhausted

    MAKE_FUNCTION = auto()  # arg: FunctionProto
    MAKE_CLASS = auto()     # arg: ClassSpec

    SPAWN = auto()
    SYNC = auto()           # arg: branch count
    RACE = auto()           # arg: branch count


@dataclass
class Instr:
    op: Op
    arg: object = None
    line: int = 0

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"{self.op.name}({self.arg!r})" if self.arg is not None else self.op.name


@dataclass
class Chunk:
    name: str = "<script>"
    code: list[Instr] = field(default_factory=list)
    consts: list[object] = field(default_factory=list)

    def emit(self, op: Op, arg: object = None, line: int = 0) -> int:
        self.code.append(Instr(op, arg, line))
        return len(self.code) - 1

    def add_const(self, value: object) -> int:
        self.consts.append(value)
        return len(self.consts) - 1

    def patch(self, index: int, target: int):
        instr = self.code[index]
        self.code[index] = Instr(instr.op, target, instr.line)

    def here(self) -> int:
        return len(self.code)


@dataclass
class ParamSpec:
    name: str
    default_chunk: "Chunk | None" = None


@dataclass
class FunctionProto:
    name: str
    params: list[ParamSpec]
    effects: list[str]
    chunk: Chunk
    is_method: bool = False
    access: str = "public"
    is_abstract: bool = False


@dataclass
class FieldSpec:
    name: str
    default_chunk: "Chunk | None"
    access: str = "public"


@dataclass
class ClassSpec:
    name: str
    base: "str | None"
    fields: list[FieldSpec]
    methods: list[FunctionProto]
    interfaces: list[str] = field(default_factory=list)
    is_abstract: bool = False
