"""AST -> bytecode compiler.

The compiler is a single recursive-descent tree walk that emits into a
`Chunk` per function (see bytecode.py). Two design choices shape almost
everything here and are explained at length in docs/architecture.md:

1. Variables are name-based, not stack-slot based - `STORE_NAME` /
   `LOAD_NAME` / `SET_NAME` walk a runtime environment chain. This trades
   a little execution speed for a much simpler compiler (no slot
   allocation, no upvalue capture-by-index bookkeeping).

2. Verse's "decides" failure effect is compiled using an explicit
   handler stack (`PUSH_HANDLER` / `POP_HANDLER` / `CLAUSE_CHECK`)
   rather than modeled as backtracking. A failure inside a clause raises
   the host exception `VerseFailure`; the nearest enclosing handler
   catches it and jumps to the failure-continuation address instead of
   propagating further. If no handler is active, it propagates out of
   the current function call entirely (so calling a failing function
   makes the *call* fail).
"""

from __future__ import annotations

from . import ast_nodes as A
from .bytecode import Chunk, ClassSpec, FieldSpec, FunctionProto, Op, ParamSpec
from .errors import VerseCompileError
from .values import VOID

_TYPE_DEFAULTS = {
    "int": 0,
    "float": 0.0,
    "string": "",
    "logic": False,
}


def _default_for_type(type_ann: str | None):
    if type_ann is None:
        return VOID
    return _TYPE_DEFAULTS.get(type_ann, VOID)


class _FuncCtx:
    """Per-function compilation state: the chunk being built plus the
    stack of enclosing loops (for break/continue jump patching)."""

    def __init__(self, chunk: Chunk):
        self.chunk = chunk
        self.loop_stack: list[dict] = []
        self.scope_depth = 0

    def emit(self, op: Op, arg=None, line: int = 0) -> int:
        return self.chunk.emit(op, arg, line)

    def add_const(self, value) -> int:
        return self.chunk.add_const(value)

    def patch(self, index: int, target: int):
        self.chunk.patch(index, target)

    def here(self) -> int:
        return self.chunk.here()


class Compiler:
    def _enter_scope(self, ctx: _FuncCtx, line: int = 0):
        ctx.emit(Op.PUSH_SCOPE, None, line)
        ctx.scope_depth += 1

    def _exit_scope(self, ctx: _FuncCtx, line: int = 0):
        ctx.emit(Op.POP_SCOPE, None, line)
        ctx.scope_depth -= 1

    def _emit_scope_unwind(self, ctx: _FuncCtx, target_depth: int, line: int):
        for _ in range(max(0, ctx.scope_depth - target_depth)):
            ctx.emit(Op.POP_SCOPE, None, line)

    def compile_program(self, program: A.Program) -> Chunk:
        chunk = Chunk(name="<script>")
        ctx = _FuncCtx(chunk)
        for stmt in program.body:
            self._compile_stmt(stmt, ctx)
        ctx.emit(Op.LOAD_CONST, ctx.add_const(VOID))
        ctx.emit(Op.RETURN)
        return chunk

    # ==================================================================
    # Functions
    # ==================================================================
    def _compile_function_proto(
        self, name: str, params: list[A.Param], effects: list[str], body: A.Block
    ) -> FunctionProto:
        chunk = Chunk(name=name)
        ctx = _FuncCtx(chunk)
        self._compile_function_body(body, ctx)
        param_specs = [
            ParamSpec(
                name=p.name,
                default_chunk=self._compile_expr_as_chunk(p.default) if p.default else None,
            )
            for p in params
        ]
        return FunctionProto(name=name, params=param_specs, effects=list(effects), chunk=chunk)

    def _compile_function_body(self, block: A.Block, ctx: _FuncCtx):
        """Compile a function body so that the value of a trailing bare
        expression (or explicit `return`) becomes the function's result -
        Verse functions are expression-oriented. Any other final
        statement shape falls through to an implicit `return void`; see
        docs/differences-from-verse.md for why this doesn't do full
        tail-expression propagation through `if`/`for`."""
        stmts = block.statements
        if not stmts:
            ctx.emit(Op.LOAD_CONST, ctx.add_const(VOID))
            ctx.emit(Op.RETURN)
            return
        for stmt in stmts[:-1]:
            self._compile_stmt(stmt, ctx)
        last = stmts[-1]
        if isinstance(last, A.ExprStmt):
            self._compile_expr(last.expr, ctx)
            ctx.emit(Op.RETURN, line=last.line)
        elif isinstance(last, A.Return):
            self._compile_stmt(last, ctx)
        else:
            self._compile_stmt(last, ctx)
            ctx.emit(Op.LOAD_CONST, ctx.add_const(VOID))
            ctx.emit(Op.RETURN)

    def _compile_expr_as_chunk(self, expr: A.Expr) -> Chunk:
        chunk = Chunk(name="<expr>")
        ctx = _FuncCtx(chunk)
        self._compile_expr(expr, ctx)
        ctx.emit(Op.RETURN)
        return chunk

    def _const_chunk(self, value) -> Chunk:
        chunk = Chunk(name="<default>")
        chunk.emit(Op.LOAD_CONST, chunk.add_const(value))
        chunk.emit(Op.RETURN)
        return chunk

    # ==================================================================
    # Statements
    # ==================================================================
    def _compile_stmt(self, stmt: A.Stmt, ctx: _FuncCtx):
        if isinstance(stmt, A.ExprStmt):
            self._compile_expr(stmt.expr, ctx)
            ctx.emit(Op.POP, line=stmt.line)
        elif isinstance(stmt, A.VarDecl):
            self._compile_var_decl(stmt, ctx)
        elif isinstance(stmt, A.Assign):
            self._compile_assign(stmt, ctx)
        elif isinstance(stmt, A.If):
            self._compile_if(stmt, ctx)
        elif isinstance(stmt, A.For):
            self._compile_for(stmt, ctx)
        elif isinstance(stmt, A.Loop):
            self._compile_loop(stmt, ctx)
        elif isinstance(stmt, A.Break):
            if not ctx.loop_stack:
                raise VerseCompileError("'break' used outside of a loop", stmt.line)
            self._emit_scope_unwind(ctx, ctx.loop_stack[-1]["scope_depth"], stmt.line)
            idx = ctx.emit(Op.JUMP, None, stmt.line)
            ctx.loop_stack[-1]["break_jumps"].append(idx)
        elif isinstance(stmt, A.Continue):
            if not ctx.loop_stack:
                raise VerseCompileError("'continue' used outside of a loop", stmt.line)
            self._emit_scope_unwind(ctx, ctx.loop_stack[-1]["scope_depth"], stmt.line)
            ctx.emit(Op.JUMP, ctx.loop_stack[-1]["continue_target"], stmt.line)
        elif isinstance(stmt, A.Return):
            if stmt.value is not None:
                self._compile_expr(stmt.value, ctx)
            else:
                ctx.emit(Op.LOAD_CONST, ctx.add_const(VOID), stmt.line)
            ctx.emit(Op.RETURN, line=stmt.line)
        elif isinstance(stmt, A.FuncDecl):
            proto = self._compile_function_proto(stmt.name, stmt.params, stmt.effects, stmt.body)
            ctx.emit(Op.MAKE_FUNCTION, proto, stmt.line)
            ctx.emit(Op.STORE_NAME, stmt.name, stmt.line)
        elif isinstance(stmt, A.ClassDecl):
            self._compile_class_decl(stmt, ctx)
        elif isinstance(stmt, A.Block):
            for s in stmt.statements:
                self._compile_stmt(s, ctx)
        else:
            raise VerseCompileError(f"cannot compile statement {type(stmt).__name__}", stmt.line)

    def _compile_var_decl(self, stmt: A.VarDecl, ctx: _FuncCtx):
        if stmt.value is not None:
            self._compile_expr(stmt.value, ctx)
        else:
            ctx.emit(Op.LOAD_CONST, ctx.add_const(_default_for_type(stmt.type_ann)), stmt.line)
        ctx.emit(Op.STORE_NAME, stmt.name, stmt.line)

    def _compile_assign(self, stmt: A.Assign, ctx: _FuncCtx):
        target = stmt.target
        if isinstance(target, A.Identifier):
            self._compile_expr(stmt.value, ctx)
            ctx.emit(Op.SET_NAME, target.name, stmt.line)
        elif isinstance(target, A.Member):
            self._compile_expr(target.obj, ctx)
            self._compile_expr(stmt.value, ctx)
            ctx.emit(Op.SET_MEMBER, target.name, stmt.line)
        elif isinstance(target, A.Index):
            self._compile_expr(target.obj, ctx)
            self._compile_expr(target.index, ctx)
            self._compile_expr(stmt.value, ctx)
            ctx.emit(Op.SET_INDEX, None, stmt.line)
        else:
            raise VerseCompileError("invalid assignment target", stmt.line)

    # -- if / for / loop ----------------------------------------------------
    def _compile_clauses(self, clauses: list[A.IfClause], ctx: _FuncCtx) -> int:
        """Emit code for a list of ANDed decides-clauses. Returns the
        index of the (unpatched) final PUSH_HANDLER/CLAUSE_CHECK targets'
        shared failure address - caller must patch all returned indices."""
        handler_indices = []
        for clause in clauses:
            h_idx = ctx.emit(Op.PUSH_HANDLER, None, clause.line)
            handler_indices.append(h_idx)
            self._compile_expr(clause.expr, ctx)
            ctx.emit(Op.POP_HANDLER, None, clause.line)
            c_idx = ctx.emit(Op.CLAUSE_CHECK, None, clause.line)
            handler_indices.append(c_idx)
            if clause.name:
                ctx.emit(Op.STORE_NAME, clause.name, clause.line)
            else:
                ctx.emit(Op.POP, None, clause.line)
        return handler_indices

    def _compile_if(self, node: A.If, ctx: _FuncCtx):
        self._enter_scope(ctx, node.line)
        scope_depth = ctx.scope_depth
        patch_indices = self._compile_clauses(node.clauses, ctx)
        for s in node.then_branch.statements:
            self._compile_stmt(s, ctx)
        ctx.emit(Op.POP_SCOPE, None, node.line)
        end_jump = ctx.emit(Op.JUMP, None, node.line)
        fail_target = ctx.here()
        for idx in patch_indices:
            ctx.patch(idx, fail_target)
        if node.else_branch is not None:
            for s in node.else_branch.statements:
                self._compile_stmt(s, ctx)
        ctx.emit(Op.POP_SCOPE, None, node.line)
        ctx.scope_depth = scope_depth - 1
        ctx.patch(end_jump, ctx.here())

    def _compile_if_expr(self, node: A.IfExpr, ctx: _FuncCtx):
        self._enter_scope(ctx, node.line)
        scope_depth = ctx.scope_depth
        patch_indices = self._compile_clauses(node.clauses, ctx)
        then_expr = node.then_branch.statements[0].expr
        self._compile_expr(then_expr, ctx)
        ctx.emit(Op.POP_SCOPE, None, node.line)
        end_jump = ctx.emit(Op.JUMP, None, node.line)
        fail_target = ctx.here()
        for idx in patch_indices:
            ctx.patch(idx, fail_target)
        if node.else_branch is not None:
            else_expr = node.else_branch.statements[0].expr
            self._compile_expr(else_expr, ctx)
        else:
            ctx.emit(Op.LOAD_CONST, ctx.add_const(VOID), node.line)
        ctx.emit(Op.POP_SCOPE, None, node.line)
        ctx.scope_depth = scope_depth - 1
        ctx.patch(end_jump, ctx.here())

    def _compile_for(self, node: A.For, ctx: _FuncCtx):
        self._enter_scope(ctx, node.line)
        self._compile_expr(node.iterable, ctx)
        ctx.emit(Op.GET_ITER, None, node.line)
        for_start = ctx.here()
        exhausted_jump = ctx.emit(Op.FOR_ITER, None, node.line)
        ctx.emit(Op.STORE_NAME, node.var_name, node.line)
        for filt in node.filters:
            h_idx = ctx.emit(Op.PUSH_HANDLER, for_start, filt.line)
            self._compile_expr(filt, ctx)
            ctx.emit(Op.POP_HANDLER, None, filt.line)
            ctx.emit(Op.CLAUSE_CHECK, for_start, filt.line)
            ctx.emit(Op.POP, None, filt.line)
        ctx.loop_stack.append(
            {"continue_target": for_start, "break_jumps": [], "scope_depth": ctx.scope_depth}
        )
        for s in node.body.statements:
            self._compile_stmt(s, ctx)
        ctx.emit(Op.JUMP, for_start, node.line)
        for_end = ctx.here()
        ctx.patch(exhausted_jump, for_end)
        loop_ctx = ctx.loop_stack.pop()
        for idx in loop_ctx["break_jumps"]:
            ctx.patch(idx, for_end)
        self._exit_scope(ctx, node.line)

    def _compile_loop(self, node: A.Loop, ctx: _FuncCtx):
        self._enter_scope(ctx, node.line)
        loop_start = ctx.here()
        ctx.loop_stack.append(
            {"continue_target": loop_start, "break_jumps": [], "scope_depth": ctx.scope_depth}
        )
        for s in node.body.statements:
            self._compile_stmt(s, ctx)
        ctx.emit(Op.JUMP, loop_start, node.line)
        loop_end = ctx.here()
        loop_ctx = ctx.loop_stack.pop()
        for idx in loop_ctx["break_jumps"]:
            ctx.patch(idx, loop_end)
        self._exit_scope(ctx, node.line)

    # -- classes ----------------------------------------------------
    def _compile_class_decl(self, node: A.ClassDecl, ctx: _FuncCtx):
        field_specs = []
        for f in node.fields:
            if f.default is not None:
                default_chunk = self._compile_expr_as_chunk(f.default)
            else:
                default_chunk = self._const_chunk(_default_for_type(f.type_ann))
            field_specs.append(FieldSpec(name=f.name, default_chunk=default_chunk))
        methods = [
            self._compile_function_proto(m.name, m.params, m.effects, m.body)
            for m in node.methods
        ]
        spec = ClassSpec(name=node.name, base=node.base, fields=field_specs, methods=methods)
        ctx.emit(Op.MAKE_CLASS, spec, node.line)
        ctx.emit(Op.STORE_NAME, node.name, node.line)

    # ==================================================================
    # Expressions
    # ==================================================================
    def _compile_expr(self, expr: A.Expr, ctx: _FuncCtx):
        if isinstance(expr, A.IntLiteral):
            ctx.emit(Op.LOAD_CONST, ctx.add_const(expr.value), expr.line)
        elif isinstance(expr, A.FloatLiteral):
            ctx.emit(Op.LOAD_CONST, ctx.add_const(expr.value), expr.line)
        elif isinstance(expr, A.StringLiteral):
            ctx.emit(Op.LOAD_CONST, ctx.add_const(expr.value), expr.line)
        elif isinstance(expr, A.LogicLiteral):
            ctx.emit(Op.LOAD_CONST, ctx.add_const(bool(expr.value)), expr.line)
        elif isinstance(expr, A.Identifier):
            ctx.emit(Op.LOAD_NAME, expr.name, expr.line)
        elif isinstance(expr, A.SelfExpr):
            ctx.emit(Op.LOAD_NAME, "self", expr.line)
        elif isinstance(expr, A.Unary):
            self._compile_expr(expr.operand, ctx)
            ctx.emit(Op.UNARY_OP, expr.op, expr.line)
        elif isinstance(expr, A.Binary):
            self._compile_expr(expr.left, ctx)
            self._compile_expr(expr.right, ctx)
            ctx.emit(Op.BINARY_OP, expr.op, expr.line)
        elif isinstance(expr, A.Logical):
            self._compile_logical(expr, ctx)
        elif isinstance(expr, A.Range):
            self._compile_expr(expr.start, ctx)
            self._compile_expr(expr.end, ctx)
            ctx.emit(Op.RANGE, None, expr.line)
        elif isinstance(expr, A.Call):
            self._compile_expr(expr.callee, ctx)
            for a in expr.args:
                self._compile_expr(a, ctx)
            ctx.emit(Op.CALL, len(expr.args), expr.line)
        elif isinstance(expr, A.Index):
            self._compile_expr(expr.obj, ctx)
            self._compile_expr(expr.index, ctx)
            ctx.emit(Op.GET_INDEX, None, expr.line)
        elif isinstance(expr, A.Member):
            self._compile_expr(expr.obj, ctx)
            ctx.emit(Op.GET_MEMBER, expr.name, expr.line)
        elif isinstance(expr, A.FailableUnwrap):
            self._compile_expr(expr.operand, ctx)
            ctx.emit(Op.FAILABLE_UNWRAP, None, expr.line)
        elif isinstance(expr, A.ArrayLiteral):
            for e in expr.elements:
                self._compile_expr(e, ctx)
            ctx.emit(Op.ARRAY_LITERAL, len(expr.elements), expr.line)
        elif isinstance(expr, A.MapLiteral):
            for k, v in expr.pairs:
                self._compile_expr(k, ctx)
                self._compile_expr(v, ctx)
            ctx.emit(Op.MAP_LITERAL, len(expr.pairs), expr.line)
        elif isinstance(expr, A.StructLiteral):
            names = []
            for name, val in expr.fields:
                names.append(name)
                self._compile_expr(val, ctx)
            ctx.emit(Op.STRUCT_LITERAL, (expr.type_name, names), expr.line)
        elif isinstance(expr, A.IfExpr):
            self._compile_if_expr(expr, ctx)
        elif isinstance(expr, A.SpawnExpr):
            proto = self._compile_function_proto("<spawn>", [], [], expr.body)
            ctx.emit(Op.MAKE_FUNCTION, proto, expr.line)
            ctx.emit(Op.SPAWN, None, expr.line)
        elif isinstance(expr, A.SyncExpr):
            self._compile_branches(expr.items, "<sync-branch>", ctx)
            ctx.emit(Op.SYNC, len(expr.items), expr.line)
        elif isinstance(expr, A.RaceExpr):
            self._compile_branches(expr.items, "<race-branch>", ctx)
            ctx.emit(Op.RACE, len(expr.items), expr.line)
        else:
            raise VerseCompileError(f"cannot compile expression {type(expr).__name__}", expr.line)

    def _compile_branches(self, items: list[A.Expr], label: str, ctx: _FuncCtx):
        for item in items:
            body = A.Block(statements=[A.ExprStmt(expr=item, line=item.line)], line=item.line)
            proto = self._compile_function_proto(label, [], [], body)
            ctx.emit(Op.MAKE_FUNCTION, proto, item.line)

    def _compile_logical(self, expr: A.Logical, ctx: _FuncCtx):
        self._compile_expr(expr.left, ctx)
        if expr.op == "and":
            j = ctx.emit(Op.JUMP_IF_FALSE, None, expr.line)
        else:
            j = ctx.emit(Op.JUMP_IF_TRUE, None, expr.line)
        ctx.emit(Op.POP, None, expr.line)
        self._compile_expr(expr.right, ctx)
        ctx.patch(j, ctx.here())


def compile_program(program: A.Program) -> Chunk:
    return Compiler().compile_program(program)


def compile_expr(expr: A.Expr) -> Chunk:
    """Compile a single expression into a zero-argument chunk that
    returns its value - used by the REPL to evaluate-and-print."""
    return Compiler()._compile_expr_as_chunk(expr)
