"""Static type values for the opt-in Verse-core type checker."""

from __future__ import annotations

from dataclasses import dataclass


class Type:
    pass


@dataclass(frozen=True)
class UnknownType(Type):
    pass


@dataclass(frozen=True)
class IntType(Type):
    pass


@dataclass(frozen=True)
class FloatType(Type):
    pass


@dataclass(frozen=True)
class StringType(Type):
    pass


@dataclass(frozen=True)
class LogicType(Type):
    pass


@dataclass(frozen=True)
class VoidType(Type):
    pass


@dataclass(frozen=True)
class RangeType(Type):
    pass


@dataclass(frozen=True)
class TaskType(Type):
    pass


@dataclass(frozen=True)
class ArrayType(Type):
    element_type: Type


@dataclass(frozen=True)
class MapType(Type):
    key_type: Type
    value_type: Type


@dataclass(frozen=True)
class OptionType(Type):
    value_type: Type


@dataclass(frozen=True)
class ClassType(Type):
    name: str


@dataclass(frozen=True)
class FunctionType(Type):
    param_types: tuple[Type, ...]
    return_type: Type
    required_params: int | None = None


@dataclass(frozen=True)
class FunctionAnyType(Type):
    pass


@dataclass(frozen=True)
class BuiltinType(Type):
    name: str


UNKNOWN = UnknownType()
INT = IntType()
FLOAT = FloatType()
STRING = StringType()
LOGIC = LogicType()
VOID = VoidType()
RANGE = RangeType()
TASK = TaskType()
FUNCTION = FunctionAnyType()


def parse_type_ann(text: str) -> Type:
    i = 0

    def parse_one() -> Type:
        nonlocal i
        if i >= len(text):
            raise ValueError("unexpected end of type")
        if text[i] == "?":
            i += 1
            return OptionType(parse_one())
        if text[i] == "[":
            i += 1
            if i < len(text) and text[i] == "]":
                i += 1
                return ArrayType(parse_one())
            key = parse_one()
            if i >= len(text) or text[i] != "]":
                raise ValueError("expected ']'")
            i += 1
            return MapType(key, parse_one())

        start = i
        while i < len(text) and text[i] not in "?[]":
            i += 1
        name = text[start:i]
        if not name:
            raise ValueError("expected type name")
        return {
            "int": INT,
            "float": FLOAT,
            "string": STRING,
            "logic": LOGIC,
            "void": VOID,
            "range": RANGE,
            "task": TASK,
            "function": FUNCTION,
        }.get(name, ClassType(name))

    typ = parse_one()
    if i != len(text):
        raise ValueError(f"unexpected trailing type text {text[i:]!r}")
    return typ


def format_type(typ: Type) -> str:
    if typ == UNKNOWN:
        return "unknown"
    if typ == INT:
        return "int"
    if typ == FLOAT:
        return "float"
    if typ == STRING:
        return "string"
    if typ == LOGIC:
        return "logic"
    if typ == VOID:
        return "void"
    if typ == RANGE:
        return "range"
    if typ == TASK:
        return "task"
    if typ == FUNCTION:
        return "function"
    if isinstance(typ, ArrayType):
        return f"[]{format_type(typ.element_type)}"
    if isinstance(typ, MapType):
        return f"[{format_type(typ.key_type)}]{format_type(typ.value_type)}"
    if isinstance(typ, OptionType):
        return f"?{format_type(typ.value_type)}"
    if isinstance(typ, ClassType):
        return typ.name
    if isinstance(typ, FunctionType):
        params = ", ".join(format_type(t) for t in typ.param_types)
        return f"function({params}) -> {format_type(typ.return_type)}"
    if isinstance(typ, BuiltinType):
        return typ.name
    return type(typ).__name__
