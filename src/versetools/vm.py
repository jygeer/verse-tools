"""The versetools virtual machine: a stack-based bytecode interpreter.

Design summary (full rationale in docs/architecture.md):

- One `Frame` per function activation: an operand stack, a program
  counter into its `Chunk`, and an `Environment` for name lookups.
- `_exec_frame` is a *generator* that yields once after each instruction.
  Ordinary calls drive their callee with `yield from`, so a normal call
  stack is just nested generator delegation - cheap, and it means a
  `spawn`ed task's call stack cooperatively interleaves with everything
  else for free. `spawn`/`sync`/`race` instead register a callee's
  generator with the VM-wide scheduler and step it with explicit
  `next()` calls, which is what actually produces concurrency (see
  `_tick_all`).
- Verse's decides/failure effect is implemented with a real exception,
  `VerseFailure` (errors.py), caught by a per-frame handler stack that
  `PUSH_HANDLER`/`POP_HANDLER`/`CLAUSE_CHECK` maintain. This is not
  backtracking - once a handler jump is taken, any stack mutations the
  failing clause performed before failing are simply discarded by
  truncating the operand stack back to the recorded depth, and the active
  environment scope is restored to what it was when the handler was pushed.
"""

from __future__ import annotations

from .bytecode import Chunk, Op
from .errors import VerseFailure, VerseRuntimeError
from .stdlib import install_builtins
from .values import (
    VArray,
    VBoundMethod,
    VClass,
    VFunction,
    VInstance,
    VMap,
    VNative,
    VOption,
    VRange,
    VTask,
    VOID,
    Environment,
    type_name,
)


class Frame:
    __slots__ = ("chunk", "env", "stack", "pc", "handlers")

    def __init__(self, chunk: Chunk, env: Environment):
        self.chunk = chunk
        self.env = env
        self.stack: list = []
        self.pc = 0
        self.handlers: list[tuple[int, int, Environment]] = []  # (target_pc, stack_depth, env)


class VM:
    def __init__(self, output=None):
        self.globals = Environment(parent=None)
        install_builtins(self.globals)
        self.scheduler_tasks: list[VTask] = []
        self.output = output  # a callable str->None; stdlib defaults to print()

    # ==================================================================
    # Public entry points
    # ==================================================================
    def run_chunk(self, chunk: Chunk):
        """Execute a top-level (script or REPL-statement) chunk directly
        in the persistent global environment, then let any `spawn`ed
        background tasks finish before returning."""
        frame = Frame(chunk, self.globals)
        result = self._drain(self._exec_frame(frame))
        self._drain_background_tasks()
        return result

    def call_function(self, fn: VFunction, args: list):
        gen = self._call(fn, args, 0)
        result = self._drain(gen)
        self._drain_background_tasks()
        return result

    # ==================================================================
    # Driving generators
    # ==================================================================
    def _drain(self, gen):
        try:
            while True:
                next(gen)
        except StopIteration as e:
            return e.value if e.value is not None else VOID

    def _drain_background_tasks(self):
        while any(not t.done for t in self.scheduler_tasks):
            self._tick_all()

    def _tick_all(self):
        still_running = []
        for t in self.scheduler_tasks:
            if t.done:
                continue
            try:
                next(t.generator)
                still_running.append(t)
            except StopIteration as e:
                t.done = True
                t.result = e.value if e.value is not None else VOID
            except VerseFailure:
                t.done = True
                t.failed = True
        self.scheduler_tasks = still_running

    # ==================================================================
    # Calling
    # ==================================================================
    def _bind_params(self, proto, closure_env, args, line, env=None) -> Environment:
        if env is None:
            env = Environment(parent=closure_env)
        params = proto.params
        if len(args) > len(params):
            raise VerseRuntimeError(
                f"'{proto.name}' takes at most {len(params)} argument(s), got {len(args)}", line
            )
        for i, pspec in enumerate(params):
            if i < len(args):
                value = args[i]
            elif pspec.default_chunk is not None:
                value = self._drain(self._exec_frame(Frame(pspec.default_chunk, env)))
            else:
                raise VerseRuntimeError(
                    f"'{proto.name}' missing required argument '{pspec.name}'", line
                )
            env.define(pspec.name, value)
        return env

    def _call(self, callee, args: list, line: int):
        """A generator: yields through nested calls, returns the result."""
        if isinstance(callee, VNative):
            return callee.fn(self, args)
        if isinstance(callee, VFunction):
            env = self._bind_params(callee.proto, callee.closure_env, args, line)
            result = yield from self._exec_frame(Frame(callee.proto.chunk, env))
            return result
        if isinstance(callee, VBoundMethod):
            fn = callee.function
            env = Environment(parent=fn.closure_env)
            env.define("self", callee.instance)
            self._bind_params(fn.proto, fn.closure_env, args, line, env=env)
            result = yield from self._exec_frame(Frame(fn.proto.chunk, env))
            return result
        if isinstance(callee, VClass):
            raise VerseRuntimeError(
                f"'{callee.name}' is a class - construct it with {callee.name}{{...}}, "
                "it isn't called like a function",
                line,
            )
        raise VerseRuntimeError(f"value of type {type_name(callee)} is not callable", line)

    def _spawn_function(self, fn: VFunction, label: str) -> VTask:
        env = Environment(parent=fn.closure_env)
        frame = Frame(fn.proto.chunk, env)
        task = VTask(label, self._exec_frame(frame))
        self.scheduler_tasks.append(task)
        return task

    # ==================================================================
    # The dispatch loop
    # ==================================================================
    def _exec_frame(self, frame: Frame):
        chunk = frame.chunk
        code = chunk.code
        consts = chunk.consts
        stack = frame.stack

        while True:
            if frame.pc >= len(code):
                return VOID
            instr = code[frame.pc]
            op = instr.op
            try:
                if op == Op.LOAD_CONST:
                    stack.append(consts[instr.arg])
                    frame.pc += 1
                elif op == Op.LOAD_NAME:
                    stack.append(frame.env.get(instr.arg))
                    frame.pc += 1
                elif op == Op.STORE_NAME:
                    frame.env.define(instr.arg, stack.pop())
                    frame.pc += 1
                elif op == Op.SET_NAME:
                    frame.env.set(instr.arg, stack.pop())
                    frame.pc += 1
                elif op == Op.PUSH_SCOPE:
                    frame.env = Environment(parent=frame.env)
                    frame.pc += 1
                elif op == Op.POP_SCOPE:
                    if frame.env.parent is None:
                        raise VerseRuntimeError("cannot pop root scope", instr.line)
                    frame.env = frame.env.parent
                    frame.pc += 1
                elif op == Op.POP:
                    stack.pop()
                    frame.pc += 1
                elif op == Op.POP_CHECKED:
                    ok, _bound = _clause_result(stack.pop())
                    if not ok:
                        raise VerseFailure()
                    frame.pc += 1
                elif op == Op.BINARY_OP:
                    b = stack.pop()
                    a = stack.pop()
                    stack.append(_binary_op(instr.arg, a, b, instr.line))
                    frame.pc += 1
                elif op == Op.UNARY_OP:
                    stack.append(_unary_op(instr.arg, stack.pop(), instr.line))
                    frame.pc += 1
                elif op == Op.JUMP:
                    frame.pc = instr.arg
                elif op == Op.JUMP_IF_FALSE:
                    frame.pc = instr.arg if stack[-1] is False else frame.pc + 1
                elif op == Op.JUMP_IF_TRUE:
                    frame.pc = instr.arg if stack[-1] is True else frame.pc + 1
                elif op == Op.PUSH_HANDLER:
                    frame.handlers.append((instr.arg, len(stack), frame.env))
                    frame.pc += 1
                elif op == Op.POP_HANDLER:
                    frame.handlers.pop()
                    frame.pc += 1
                elif op == Op.CLAUSE_CHECK:
                    ok, bound = _clause_result(stack.pop())
                    if ok:
                        stack.append(bound)
                        frame.pc += 1
                    else:
                        frame.pc = instr.arg
                elif op == Op.CALL:
                    argc = instr.arg
                    args = [stack.pop() for _ in range(argc)][::-1]
                    callee = stack.pop()
                    result = yield from self._call(callee, args, instr.line)
                    stack.append(result)
                    frame.pc += 1
                elif op == Op.RETURN:
                    return stack.pop()
                elif op == Op.GET_INDEX:
                    index = stack.pop()
                    obj = stack.pop()
                    stack.append(_get_index(obj, index, instr.line))
                    frame.pc += 1
                elif op == Op.SET_INDEX:
                    value = stack.pop()
                    index = stack.pop()
                    obj = stack.pop()
                    _set_index(obj, index, value, instr.line)
                    frame.pc += 1
                elif op == Op.GET_MEMBER:
                    obj = stack.pop()
                    stack.append(_get_member(obj, instr.arg, instr.line))
                    frame.pc += 1
                elif op == Op.SET_MEMBER:
                    value = stack.pop()
                    obj = stack.pop()
                    _set_member(obj, instr.arg, value, instr.line)
                    frame.pc += 1
                elif op == Op.FAILABLE_UNWRAP:
                    value = stack.pop()
                    ok, bound = _clause_result(value)
                    if not ok:
                        raise VerseFailure()
                    stack.append(bound)
                    frame.pc += 1
                elif op == Op.ARRAY_LITERAL:
                    n = instr.arg
                    elements = [stack.pop() for _ in range(n)][::-1]
                    stack.append(VArray(elements))
                    frame.pc += 1
                elif op == Op.MAP_LITERAL:
                    n = instr.arg
                    flat = [stack.pop() for _ in range(2 * n)][::-1]
                    pairs = {}
                    for i in range(0, len(flat), 2):
                        key, value = flat[i], flat[i + 1]
                        _check_map_key(key, instr.line)
                        pairs[key] = value
                    stack.append(VMap(pairs))
                    frame.pc += 1
                elif op == Op.STRUCT_LITERAL:
                    type_name_, field_names = instr.arg
                    n = len(field_names)
                    values = [stack.pop() for _ in range(n)][::-1]
                    stack.append(
                        self._build_instance(frame.env, type_name_, field_names, values, instr.line)
                    )
                    frame.pc += 1
                elif op == Op.RANGE:
                    end = stack.pop()
                    start = stack.pop()
                    stack.append(_make_range(start, end, instr.line))
                    frame.pc += 1
                elif op == Op.GET_ITER:
                    stack.append(_get_iter(stack.pop(), instr.line))
                    frame.pc += 1
                elif op == Op.FOR_ITER:
                    it = stack[-1]
                    try:
                        stack.append(next(it))
                        frame.pc += 1
                    except StopIteration:
                        stack.pop()
                        frame.pc = instr.arg
                elif op == Op.MAKE_FUNCTION:
                    stack.append(VFunction(instr.arg, frame.env))
                    frame.pc += 1
                elif op == Op.MAKE_CLASS:
                    stack.append(self._make_class(frame.env, instr.arg, instr.line))
                    frame.pc += 1
                elif op == Op.SPAWN:
                    fn = stack.pop()
                    stack.append(self._spawn_function(fn, "spawn"))
                    frame.pc += 1
                elif op == Op.SYNC:
                    n = instr.arg
                    fns = [stack.pop() for _ in range(n)][::-1]
                    tasks = [self._spawn_function(fn, "sync-branch") for fn in fns]
                    while any(not t.done for t in tasks):
                        self._tick_all()
                        yield
                    if any(t.failed for t in tasks):
                        raise VerseFailure()
                    stack.append(VArray([t.result for t in tasks]))
                    frame.pc += 1
                elif op == Op.RACE:
                    n = instr.arg
                    fns = [stack.pop() for _ in range(n)][::-1]
                    tasks = [self._spawn_function(fn, "race-branch") for fn in fns]
                    while not any(t.done for t in tasks):
                        self._tick_all()
                        yield
                    winner = next(t for t in tasks if t.done)
                    losers = {id(t) for t in tasks if t is not winner}
                    self.scheduler_tasks = [
                        t for t in self.scheduler_tasks if id(t) not in losers
                    ]
                    if winner.failed:
                        raise VerseFailure()
                    stack.append(winner.result)
                    frame.pc += 1
                else:
                    raise VerseRuntimeError(f"unimplemented opcode {op}", instr.line)
            except VerseFailure:
                if frame.handlers:
                    target, depth, env = frame.handlers.pop()
                    del stack[depth:]
                    frame.env = env
                    frame.pc = target
                else:
                    raise
            yield

    # ==================================================================
    # Struct / class construction
    # ==================================================================
    def _make_class(self, env: Environment, spec, line: int) -> VClass:
        base = None
        if spec.base is not None:
            base = env.get(spec.base)
            if not isinstance(base, VClass):
                raise VerseRuntimeError(f"'{spec.base}' is not a class", line)
        methods = {m.name: VFunction(m, env) for m in spec.methods}
        field_specs = [(f.name, f.default_chunk) for f in spec.fields]
        return VClass(spec.name, base, field_specs, methods)

    def _build_instance(self, env: Environment, type_name_: str, field_names, values, line: int):
        cls = env.get(type_name_)
        if not isinstance(cls, VClass):
            raise VerseRuntimeError(f"'{type_name_}' is not a class", line)
        fields = {}
        for name, default_chunk in cls.all_field_specs():
            fields[name] = self._drain(
                self._exec_frame(Frame(default_chunk, Environment(parent=self.globals)))
            )
        for name, value in zip(field_names, values):
            if name not in fields:
                raise VerseRuntimeError(f"class '{cls.name}' has no field '{name}'", line)
            fields[name] = value
        return VInstance(cls, fields)


# ---------------------------------------------------------------------
# Free helper functions (no VM state needed)
# ---------------------------------------------------------------------


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _clause_result(value):
    """Implements the shared decides-effect success/failure rule used by
    if-clauses, for-filters, and `?`. Returns (succeeded, bound_value)."""
    if isinstance(value, VOption):
        return (value.has_value, value.value)
    if isinstance(value, bool):
        return (value, value)
    return (True, value)


def _values_equal(a, b) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b


def _binary_op(op: str, a, b, line: int):
    if op == "+":
        if _is_number(a) and _is_number(b):
            return a + b
        if isinstance(a, str) and isinstance(b, str):
            return a + b
        if isinstance(a, VArray) and isinstance(b, VArray):
            return VArray(a.items + b.items)
        raise VerseRuntimeError(f"cannot add {type_name(a)} and {type_name(b)}", line)
    if op == "-":
        if _is_number(a) and _is_number(b):
            return a - b
        raise VerseRuntimeError(f"cannot subtract {type_name(b)} from {type_name(a)}", line)
    if op == "*":
        if _is_number(a) and _is_number(b):
            return a * b
        raise VerseRuntimeError(f"cannot multiply {type_name(a)} and {type_name(b)}", line)
    if op == "/":
        if _is_number(a) and _is_number(b):
            if b == 0:
                raise VerseRuntimeError("division by zero", line)
            return a / b
        raise VerseRuntimeError(f"cannot divide {type_name(a)} by {type_name(b)}", line)
    if op == "%":
        if _is_number(a) and _is_number(b):
            if b == 0:
                raise VerseRuntimeError("division by zero", line)
            if isinstance(a, int) and isinstance(b, int):
                return a - b * int(a / b)
            import math

            return math.fmod(a, b)
        raise VerseRuntimeError(f"cannot compute {type_name(a)} % {type_name(b)}", line)
    if op == "=":
        return _values_equal(a, b)
    if op == "<>":
        return not _values_equal(a, b)
    if op in ("<", "<=", ">", ">="):
        comparable = (_is_number(a) and _is_number(b)) or (isinstance(a, str) and isinstance(b, str))
        if not comparable:
            raise VerseRuntimeError(
                f"cannot compare {type_name(a)} and {type_name(b)} with '{op}'", line
            )
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a >= b
    raise VerseRuntimeError(f"unknown operator '{op}'", line)


def _unary_op(op: str, a, line: int):
    if op == "-":
        if not _is_number(a):
            raise VerseRuntimeError(f"cannot negate {type_name(a)}", line)
        return -a
    if op == "not":
        if not isinstance(a, bool):
            raise VerseRuntimeError(f"'not' requires a logic value, got {type_name(a)}", line)
        return not a
    raise VerseRuntimeError(f"unknown unary operator '{op}'", line)


def _get_index(obj, index, line: int):
    if isinstance(obj, VArray):
        return obj.get(index)
    if isinstance(obj, VMap):
        return obj.get(index)
    if isinstance(obj, str):
        if not isinstance(index, int) or isinstance(index, bool):
            raise VerseRuntimeError(f"string index must be an int, got {type_name(index)}", line)
        if index < 0 or index >= len(obj):
            raise VerseRuntimeError(f"string index {index} out of range", line)
        return obj[index]
    raise VerseRuntimeError(f"type {type_name(obj)} does not support indexing", line)


def _set_index(obj, index, value, line: int):
    if isinstance(obj, VArray):
        obj.set(index, value)
        return
    if isinstance(obj, VMap):
        obj.set(index, value)
        return
    raise VerseRuntimeError(f"type {type_name(obj)} does not support index assignment", line)


def _get_member(obj, name: str, line: int):
    if isinstance(obj, VInstance):
        if name in obj.fields:
            return obj.fields[name]
        method = obj.cls.find_method(name)
        if method is not None:
            return VBoundMethod(obj, method)
        raise VerseRuntimeError(f"'{obj.cls.name}' has no field or method '{name}'", line)
    if isinstance(obj, VTask):
        if name == "Done":
            return obj.done
        if name == "Failed":
            return obj.failed
        if name == "Result":
            return obj.result
        raise VerseRuntimeError(f"task has no member '{name}'", line)
    raise VerseRuntimeError(f"type {type_name(obj)} has no member '{name}'", line)


def _set_member(obj, name: str, value, line: int):
    if isinstance(obj, VInstance):
        if name not in obj.fields:
            raise VerseRuntimeError(f"class '{obj.cls.name}' has no field '{name}'", line)
        obj.fields[name] = value
        return
    raise VerseRuntimeError(f"type {type_name(obj)} has no assignable member '{name}'", line)


def _check_map_key(key, line: int):
    if isinstance(key, (VArray, VMap, VInstance)):
        raise VerseRuntimeError(f"type {type_name(key)} cannot be used as a map key", line)


def _make_range(start, end, line: int):
    if not (isinstance(start, int) and not isinstance(start, bool)):
        raise VerseRuntimeError(f"range start must be an int, got {type_name(start)}", line)
    if not (isinstance(end, int) and not isinstance(end, bool)):
        raise VerseRuntimeError(f"range end must be an int, got {type_name(end)}", line)
    return VRange(start, end)


def _get_iter(obj, line: int):
    if isinstance(obj, VArray):
        return iter(list(obj.items))
    if isinstance(obj, VRange):
        return iter(obj)
    if isinstance(obj, VMap):
        return iter([VArray([k, v]) for k, v in obj.pairs.items()])
    raise VerseRuntimeError(f"cannot iterate over {type_name(obj)}", line)
