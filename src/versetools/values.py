"""Runtime value representations for the versetools VM.

Primitive Verse values map directly onto Python types:

    int    -> python int
    float  -> python float
    string -> python str
    logic  -> python bool (true/false)
    void   -> the VOID singleton

Everything with structure gets a small wrapper class below. Wrapper
classes intentionally stay thin - they exist to (a) give Verse-shaped
`__repr__`/`__eq__` output and (b) keep the "is this a Verse value or an
internal VM detail" boundary explicit.
"""

from __future__ import annotations

from .errors import VerseRuntimeError


class Void:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "void"

    def __eq__(self, other):
        return isinstance(other, Void)

    def __hash__(self):
        return hash(Void)


VOID = Void()


class VOption:
    """A Verse option value: either present (`option(x)`) or absent."""

    __slots__ = ("has_value", "value")

    def __init__(self, has_value: bool, value=None):
        self.has_value = has_value
        self.value = value if has_value else None

    @classmethod
    def some(cls, value) -> "VOption":
        return cls(True, value)

    @classmethod
    def none(cls) -> "VOption":
        return cls(False, None)

    def __repr__(self):
        return f"option({verse_repr(self.value)})" if self.has_value else "false"

    def __eq__(self, other):
        return (
            isinstance(other, VOption)
            and self.has_value == other.has_value
            and self.value == other.value
        )

    def __hash__(self):
        return hash((self.has_value, self.value))


class VArray:
    __slots__ = ("items",)

    def __init__(self, items: list | None = None):
        self.items = list(items) if items is not None else []

    def __len__(self):
        return len(self.items)

    def get(self, index: int):
        if not isinstance(index, int) or isinstance(index, bool):
            raise VerseRuntimeError(f"array index must be an int, got {type_name(index)}")
        if index < 0 or index >= len(self.items):
            raise VerseRuntimeError(f"array index {index} out of range (length {len(self.items)})")
        return self.items[index]

    def set(self, index: int, value) -> "VArray":
        if not isinstance(index, int) or isinstance(index, bool):
            raise VerseRuntimeError(f"array index must be an int, got {type_name(index)}")
        if index < 0 or index >= len(self.items):
            raise VerseRuntimeError(f"array index {index} out of range (length {len(self.items)})")
        new_items = list(self.items)
        new_items[index] = value
        return VArray(new_items)

    def __eq__(self, other):
        return isinstance(other, VArray) and self.items == other.items

    def __iter__(self):
        return iter(self.items)

    def __repr__(self):
        return "array{" + ", ".join(verse_repr(v) for v in self.items) + "}"


class VMap:
    __slots__ = ("pairs",)

    def __init__(self, pairs: dict | None = None):
        self.pairs: dict = dict(pairs) if pairs is not None else {}

    def get(self, key) -> VOption:
        if key in self.pairs:
            return VOption.some(self.pairs[key])
        return VOption.none()

    def set(self, key, value) -> "VMap":
        new_pairs = dict(self.pairs)
        new_pairs[key] = value
        return VMap(new_pairs)

    def __len__(self):
        return len(self.pairs)

    def __eq__(self, other):
        return isinstance(other, VMap) and self.pairs == other.pairs

    def __repr__(self):
        body = ", ".join(f"{verse_repr(k)} => {verse_repr(v)}" for k, v in self.pairs.items())
        return "map{" + body + "}"


class VRange:
    __slots__ = ("start", "end")

    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end

    def __iter__(self):
        return iter(range(self.start, self.end + 1))

    def __eq__(self, other):
        return isinstance(other, VRange) and (self.start, self.end) == (other.start, other.end)

    def __repr__(self):
        return f"{self.start}..{self.end}"


class VClass:
    def __init__(self, name: str, base: "VClass | None", field_specs, methods: dict, closure_env):
        self.name = name
        self.base = base
        self.field_specs = field_specs  # list[(name, default_chunk_or_None)]
        self.methods = methods  # name -> VFunction
        self.closure_env = closure_env

    def all_field_specs(self):
        specs = [] if self.base is None else self.base.all_field_specs()
        return specs + [(*field_spec, self.closure_env) for field_spec in self.field_specs]

    def find_method(self, name: str):
        if name in self.methods:
            return self.methods[name]
        if self.base is not None:
            return self.base.find_method(name)
        return None

    def is_subclass_of(self, other: "VClass") -> bool:
        c = self
        while c is not None:
            if c is other:
                return True
            c = c.base
        return False

    def __repr__(self):
        return f"<class {self.name}>"


class VInstance:
    __slots__ = ("cls", "fields")

    def __init__(self, cls: VClass, fields: dict):
        self.cls = cls
        self.fields = fields

    def __repr__(self):
        body = ", ".join(f"{k} := {verse_repr(v)}" for k, v in self.fields.items())
        return f"{self.cls.name}{{{body}}}"


class VFunction:
    __slots__ = ("proto", "closure_env")

    def __init__(self, proto, closure_env):
        self.proto = proto
        self.closure_env = closure_env

    @property
    def name(self):
        return self.proto.name

    def __repr__(self):
        params = ", ".join(p.name for p in self.proto.params)
        return f"<function {self.name}({params})>"


class VBoundMethod:
    __slots__ = ("instance", "function")

    def __init__(self, instance: VInstance, function: VFunction):
        self.instance = instance
        self.function = function

    def __repr__(self):
        return f"<bound method {self.instance.cls.name}.{self.function.name}>"


class VNative:
    __slots__ = ("name", "fn")

    def __init__(self, name: str, fn):
        self.name = name
        self.fn = fn

    def __repr__(self):
        return f"<native {self.name}>"


class VTask:
    """A handle to a cooperatively scheduled `spawn`ed task."""

    __slots__ = ("name", "generator", "done", "failed", "result")

    def __init__(self, name: str, generator):
        self.name = name
        self.generator = generator
        self.done = False
        self.failed = False
        self.result = VOID

    def __repr__(self):
        state = "done" if self.done else "running"
        return f"<task {self.name} ({state})>"


def type_name(value) -> str:
    if isinstance(value, bool):
        return "logic"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Void):
        return "void"
    if isinstance(value, VOption):
        return "option"
    if isinstance(value, VArray):
        return "array"
    if isinstance(value, VMap):
        return "map"
    if isinstance(value, VRange):
        return "range"
    if isinstance(value, VInstance):
        return value.cls.name
    if isinstance(value, VClass):
        return "class"
    if isinstance(value, (VFunction, VNative, VBoundMethod)):
        return "function"
    if isinstance(value, VTask):
        return "task"
    return type(value).__name__


def verse_repr(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, float):
        return repr(value)
    return repr(value) if not isinstance(value, (int,)) else str(value)


def verse_str(value) -> str:
    """The string produced by Print()/ToString() - unquoted for strings."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return verse_repr(value)


class Environment:
    __slots__ = ("vars", "parent")

    def __init__(self, parent: "Environment | None" = None):
        self.vars: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value):
        self.vars[name] = value

    def get(self, name: str):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise VerseRuntimeError(f"undefined name '{name}'")

    def set(self, name: str, value):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        raise VerseRuntimeError(
            f"cannot assign to undefined name '{name}' - declare it with 'var' first"
        )

    def is_defined(self, name: str) -> bool:
        env = self
        while env is not None:
            if name in env.vars:
                return True
            env = env.parent
        return False
