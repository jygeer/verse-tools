"""A human-readable bytecode disassembler, used by `verse dis` and by
anyone debugging the compiler. Recurses into every nested `Chunk`
reachable from a top-level chunk: function bodies, parameter/field
default-value chunks, and class method bodies.
"""

from __future__ import annotations

from .bytecode import Chunk, ClassSpec, FunctionProto, Op


def disassemble(chunk: Chunk, out: list[str] | None = None, seen: set | None = None) -> list[str]:
    if out is None:
        out = []
    if seen is None:
        seen = set()
    if id(chunk) in seen:
        return out
    seen.add(id(chunk))

    out.append(f"== {chunk.name} ==")
    nested: list[Chunk] = []
    for i, instr in enumerate(chunk.code):
        arg_repr = _format_arg(instr.op, instr.arg)
        out.append(f"{i:4d}  {instr.op.name:<18} {arg_repr}")
        if instr.op == Op.MAKE_FUNCTION:
            proto: FunctionProto = instr.arg
            nested.append(proto.chunk)
            for p in proto.params:
                if p.default_chunk is not None:
                    nested.append(p.default_chunk)
        elif instr.op == Op.MAKE_CLASS:
            spec: ClassSpec = instr.arg
            for m in spec.methods:
                nested.append(m.chunk)
                for p in m.params:
                    if p.default_chunk is not None:
                        nested.append(p.default_chunk)
            for f in spec.fields:
                if f.default_chunk is not None:
                    nested.append(f.default_chunk)
    out.append("")

    for sub in nested:
        disassemble(sub, out, seen)
    return out


def _format_arg(op: Op, arg) -> str:
    if arg is None:
        return ""
    if op == Op.MAKE_FUNCTION:
        proto: FunctionProto = arg
        params = ", ".join(p.name for p in proto.params)
        return f"<{proto.name}({params})>"
    if op == Op.MAKE_CLASS:
        spec: ClassSpec = arg
        return f"<class {spec.name}>"
    if op == Op.STRUCT_LITERAL:
        type_name_, field_names = arg
        return f"{type_name_}{{{', '.join(field_names)}}}"
    return repr(arg)
