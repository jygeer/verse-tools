"""Built-in functions available to every versetools program.

This is a deliberately small standard library - just enough to write and
inspect the example programs in examples/. See
docs/language-reference.md#standard-library for the user-facing
reference of everything defined here.
"""

from __future__ import annotations

import math

from .errors import VerseRuntimeError
from .values import (
    VArray,
    VMap,
    VNative,
    VOID,
    VOption,
    Environment,
    type_name,
    verse_str,
)


def _emit(vm, text: str):
    if vm.output is not None:
        vm.output(text)
    else:
        print(text)


def _arity(name: str, args: list, n: int):
    if len(args) != n:
        raise VerseRuntimeError(f"{name}() takes exactly {n} argument(s), got {len(args)}")


def _num(name: str, value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VerseRuntimeError(f"{name}() requires a number, got {type_name(value)}")
    return value


def _builtin_print(vm, args):
    _arity("Print", args, 1)
    _emit(vm, verse_str(args[0]))
    return VOID


def _builtin_log(vm, args):
    _arity("Log", args, 1)
    _emit(vm, f"[Log] {verse_str(args[0])}")
    return VOID


def _builtin_to_string(vm, args):
    _arity("ToString", args, 1)
    return verse_str(args[0])


def _builtin_option(vm, args):
    _arity("option", args, 1)
    return VOption.some(args[0])


def _builtin_abs(vm, args):
    _arity("Abs", args, 1)
    return abs(_num("Abs", args[0]))


def _builtin_min(vm, args):
    _arity("Min", args, 2)
    return min(_num("Min", args[0]), _num("Min", args[1]))


def _builtin_max(vm, args):
    _arity("Max", args, 2)
    return max(_num("Max", args[0]), _num("Max", args[1]))


def _builtin_floor(vm, args):
    _arity("Floor", args, 1)
    return math.floor(_num("Floor", args[0]))


def _builtin_ceil(vm, args):
    _arity("Ceil", args, 1)
    return math.ceil(_num("Ceil", args[0]))


def _builtin_sqrt(vm, args):
    _arity("Sqrt", args, 1)
    value = _num("Sqrt", args[0])
    if value < 0:
        raise VerseRuntimeError("Sqrt() of a negative number")
    return math.sqrt(value)


def _builtin_length(vm, args):
    _arity("Length", args, 1)
    value = args[0]
    if isinstance(value, (VArray, VMap, str)):
        return len(value)
    raise VerseRuntimeError(f"Length() does not support {type_name(value)}")


def _builtin_contains(vm, args):
    _arity("Contains", args, 2)
    container, needle = args
    if isinstance(container, VArray):
        return any(_verse_eq(item, needle) for item in container.items)
    if isinstance(container, VMap):
        return any(_verse_eq(key, needle) for key in container.pairs)
    if isinstance(container, str) and isinstance(needle, str):
        return needle in container
    raise VerseRuntimeError(f"Contains() does not support {type_name(container)}")


def _verse_eq(a, b) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _builtin_keys(vm, args):
    _arity("Keys", args, 1)
    if not isinstance(args[0], VMap):
        raise VerseRuntimeError(f"Keys() requires a map, got {type_name(args[0])}")
    return VArray(list(args[0].pairs.keys()))


def _builtin_values(vm, args):
    _arity("Values", args, 1)
    if not isinstance(args[0], VMap):
        raise VerseRuntimeError(f"Values() requires a map, got {type_name(args[0])}")
    return VArray(list(args[0].pairs.values()))


_BUILTINS = {
    "Print": _builtin_print,
    "Log": _builtin_log,
    "ToString": _builtin_to_string,
    "option": _builtin_option,
    "Abs": _builtin_abs,
    "Min": _builtin_min,
    "Max": _builtin_max,
    "Floor": _builtin_floor,
    "Ceil": _builtin_ceil,
    "Sqrt": _builtin_sqrt,
    "Length": _builtin_length,
    "Contains": _builtin_contains,
    "Keys": _builtin_keys,
    "Values": _builtin_values,
}


def install_builtins(env: Environment):
    for name, fn in _BUILTINS.items():
        env.define(name, VNative(name, fn))
