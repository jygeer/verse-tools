"""Opt-in static type checking for Verse-core ASTs."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ast_nodes as A
from .errors import VerseCompileError
from .type_system import (
    FLOAT,
    FUNCTION,
    INT,
    LOGIC,
    RANGE,
    STRING,
    TASK,
    UNKNOWN,
    VOID,
    ArrayType,
    BuiltinType,
    ClassType,
    FunctionType,
    MapType,
    OptionType,
    TaskType,
    Type,
    format_type,
    parse_type_ann,
)


@dataclass
class ClassInfo:
    name: str
    base: str | None
    fields: dict[str, Type] = field(default_factory=dict)
    methods: dict[str, FunctionType | Type] = field(default_factory=dict)


def check_program(program: A.Program) -> None:
    TypeChecker().check_program(program)


class TypeChecker:
    def __init__(self):
        self.scopes: list[dict[str, Type]] = [{}]
        self.classes: dict[str, ClassInfo] = {}
        self.current_return_type: Type = UNKNOWN
        self.current_allows_failure = False
        # Maps function name -> frozenset of declared effect strings, populated bottom-up
        # so that callers can check whether a callee is <decides> etc.
        self._func_effects: dict[str, frozenset[str]] = {}
        # Depth counter: > 0 when we are type-checking expressions inside an if/for
        # clause list or for-filter list.  Calls to <decides> functions are allowed
        # (and guarded) there even in a non-decides caller.
        self._guarded_clause_depth: int = 0
        self._install_builtins()

    def check_program(self, program: A.Program) -> None:
        self._declare_top_level(program)
        for stmt in program.body:
            self._check_stmt(stmt)

    def _install_builtins(self):
        for name in (
            "Print",
            "Log",
            "ToString",
            "option",
            "Abs",
            "Min",
            "Max",
            "Floor",
            "Ceil",
            "Sqrt",
            "Length",
            "Contains",
            "Keys",
            "Values",
        ):
            self.scopes[0][name] = BuiltinType(name)

    def _declare_top_level(self, program: A.Program):
        for stmt in program.body:
            if isinstance(stmt, A.ClassDecl):
                self.classes[stmt.name] = ClassInfo(name=stmt.name, base=stmt.base)
                self.scopes[0][stmt.name] = ClassType(stmt.name)
        for stmt in program.body:
            if isinstance(stmt, A.ClassDecl):
                self._populate_class_info(stmt)
        for stmt in program.body:
            if isinstance(stmt, A.FuncDecl):
                self.scopes[0][stmt.name] = self._function_type(stmt.params, stmt.return_type, stmt.line)
                self._func_effects[stmt.name] = frozenset(stmt.effects)

    def _populate_class_info(self, node: A.ClassDecl):
        info = self.classes[node.name]
        if info.base is not None and info.base not in self.classes:
            raise VerseCompileError(f"unknown base class '{info.base}'", node.line)
        for field in node.fields:
            field_type = self._declared_or_inferred_type(field.type_ann, field.default, field.line)
            info.fields[field.name] = field_type
        for method in node.methods:
            info.methods[method.name] = self._function_type(method.params, method.return_type, method.line)

    def _function_type(self, params: list[A.Param], return_type: str | None, line: int) -> Type:
        param_types = tuple(self._type_from_ann(p.type_ann, p.line) for p in params)
        ret_type = self._type_from_ann(return_type, line) if return_type is not None else UNKNOWN
        return FunctionType(param_types=param_types, return_type=ret_type)

    def _declared_or_inferred_type(self, type_ann: str | None, value: A.Expr | None, line: int) -> Type:
        if type_ann is not None:
            return self._type_from_ann(type_ann, line)
        if value is not None:
            return self._infer_expr_type(value)
        return UNKNOWN

    def _type_from_ann(self, text: str | None, line: int) -> Type:
        if text is None:
            return UNKNOWN
        try:
            return parse_type_ann(text)
        except ValueError as e:
            raise VerseCompileError(f"invalid type annotation '{text}': {e}", line) from e

    def _push_scope(self):
        self.scopes.append({})

    def _pop_scope(self):
        self.scopes.pop()

    def _define(self, name: str, typ: Type):
        self.scopes[-1][name] = typ

    def _lookup(self, name: str, line: int) -> Type:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise VerseCompileError(f"undefined name '{name}'", line)

    def _check_stmt(self, stmt: A.Stmt):
        if isinstance(stmt, A.ExprStmt):
            self._infer_expr_type(stmt.expr)
            return
        if isinstance(stmt, A.VarDecl):
            self._check_var_decl(stmt)
            return
        if isinstance(stmt, A.Assign):
            self._check_assign(stmt)
            return
        if isinstance(stmt, A.If):
            self._check_if(stmt)
            return
        if isinstance(stmt, A.For):
            self._check_for(stmt)
            return
        if isinstance(stmt, A.Loop):
            self._push_scope()
            for inner in stmt.body.statements:
                self._check_stmt(inner)
            self._pop_scope()
            return
        if isinstance(stmt, A.Return):
            self._check_return(stmt)
            return
        if isinstance(stmt, A.FuncDecl):
            self._define(stmt.name, self._function_type(stmt.params, stmt.return_type, stmt.line))
            self._func_effects[stmt.name] = frozenset(stmt.effects)
            self._check_function(stmt)
            return
        if isinstance(stmt, A.ClassDecl):
            self._check_class(stmt)
            return
        if isinstance(stmt, A.Block):
            self._push_scope()
            for inner in stmt.statements:
                self._check_stmt(inner)
            self._pop_scope()
            return
        if isinstance(stmt, (A.Break, A.Continue)):
            return
        raise VerseCompileError(f"cannot type-check statement {type(stmt).__name__}", stmt.line)

    def _check_var_decl(self, stmt: A.VarDecl):
        declared = self._type_from_ann(stmt.type_ann, stmt.line) if stmt.type_ann is not None else None
        inferred = self._infer_expr_type(stmt.value) if stmt.value is not None else None
        if declared is not None and inferred is not None and not self._is_assignable(inferred, declared):
            raise VerseCompileError(
                f"cannot assign {format_type(inferred)} to {format_type(declared)}",
                stmt.line,
            )
        self._define(stmt.name, declared or inferred or UNKNOWN)

    def _check_assign(self, stmt: A.Assign):
        target_type = self._infer_assignment_target_type(stmt.target)
        value_type = self._infer_expr_type(stmt.value)
        if not self._is_assignable(value_type, target_type):
            raise VerseCompileError(
                f"cannot assign {format_type(value_type)} to {format_type(target_type)}",
                stmt.line,
            )

    def _check_if(self, stmt: A.If):
        self._guarded_clause_depth += 1
        try:
            bindings = self._collect_clause_bindings(stmt.clauses)
        finally:
            self._guarded_clause_depth -= 1
        self._push_scope()
        for name, typ in bindings.items():
            self._define(name, typ)
        for inner in stmt.then_branch.statements:
            self._check_stmt(inner)
        self._pop_scope()
        if stmt.else_branch is not None:
            self._push_scope()
            for inner in stmt.else_branch.statements:
                self._check_stmt(inner)
            self._pop_scope()

    def _check_for(self, stmt: A.For):
        iterable_type = self._infer_expr_type(stmt.iterable)
        item_type = self._iterable_item_type(iterable_type, stmt.line)
        self._push_scope()
        self._define(stmt.var_name, item_type)
        self._guarded_clause_depth += 1
        try:
            for filt in stmt.filters:
                self._infer_expr_type(filt)
        finally:
            self._guarded_clause_depth -= 1
        for inner in stmt.body.statements:
            self._check_stmt(inner)
        self._pop_scope()

    def _check_return(self, stmt: A.Return):
        value = stmt.value
        value_type = VOID if value is None else self._infer_expr_type(value)
        if self.current_allows_failure and isinstance(value, A.LogicLiteral) and value.value is False:
            return
        if not self._is_assignable(value_type, self.current_return_type):
            raise VerseCompileError(
                f"cannot return {format_type(value_type)} from {format_type(self.current_return_type)} function",
                stmt.line,
            )

    def _check_function(self, node: A.FuncDecl, self_type: Type | None = None):
        previous_return_type = self.current_return_type
        previous_allows_failure = self.current_allows_failure
        fn_type = self._lookup(node.name, node.line) if self_type is None else None
        self.current_return_type = fn_type.return_type if isinstance(fn_type, FunctionType) else self._type_from_ann(node.return_type, node.line)
        self.current_allows_failure = "decides" in node.effects
        self._push_scope()
        if self_type is not None:
            self._define("self", self_type)
        for param in node.params:
            param_type = self._type_from_ann(param.type_ann, param.line)
            self._define(param.name, param_type)
            if param.default is not None:
                default_type = self._infer_expr_type(param.default)
                if not self._is_assignable(default_type, param_type):
                    raise VerseCompileError(
                        f"cannot assign {format_type(default_type)} to parameter {param.name} : {format_type(param_type)}",
                        param.line,
                    )
        # Pre-scan: register effects of all directly nested FuncDecl statements
        # before type-checking the body, so that forward-referenced <decides>
        # functions are visible when their callers are checked.
        for stmt in node.body.statements:
            if isinstance(stmt, A.FuncDecl):
                self._func_effects[stmt.name] = frozenset(stmt.effects)
        for stmt in node.body.statements:
            self._check_stmt(stmt)
        self._check_implicit_return(node)
        self._pop_scope()
        self.current_return_type = previous_return_type
        self.current_allows_failure = previous_allows_failure

    def _check_implicit_return(self, node: A.FuncDecl):
        if not node.body.statements:
            effective = VOID
        else:
            last = node.body.statements[-1]
            if self._always_returns(last):
                return
            if isinstance(last, A.ExprStmt):
                effective = self._infer_expr_type(last.expr)
            elif isinstance(last, A.Return):
                return
            else:
                effective = VOID
        if not self._is_assignable(effective, self.current_return_type):
            raise VerseCompileError(
                f"cannot return {format_type(effective)} from {format_type(self.current_return_type)} function",
                node.line,
            )

    def _always_returns(self, stmt: A.Stmt) -> bool:
        if isinstance(stmt, A.Return):
            return True
        if isinstance(stmt, A.Block):
            return bool(stmt.statements) and self._always_returns(stmt.statements[-1])
        if isinstance(stmt, A.If):
            return (
                stmt.else_branch is not None
                and self._always_returns(stmt.then_branch)
                and self._always_returns(stmt.else_branch)
            )
        return False

    def _check_class(self, node: A.ClassDecl):
        info = self.classes[node.name]
        for field in node.fields:
            field_type = info.fields[field.name]
            if field.default is not None:
                default_type = self._infer_expr_type(field.default)
                if not self._is_assignable(default_type, field_type):
                    raise VerseCompileError(
                        f"cannot assign {format_type(default_type)} to {format_type(field_type)}",
                        field.line,
                    )
        self_type = ClassType(node.name)
        for method in node.methods:
            self._check_function(method, self_type=self_type)

    def _collect_clause_bindings(self, clauses: list[A.IfClause]) -> dict[str, Type]:
        bindings = {}
        for clause in clauses:
            expr_type = self._infer_expr_type(clause.expr)
            if clause.name is not None:
                bindings[clause.name] = self._clause_binding_type(expr_type)
        return bindings

    def _clause_binding_type(self, expr_type: Type) -> Type:
        if isinstance(expr_type, OptionType):
            return expr_type.value_type
        return expr_type

    def _infer_assignment_target_type(self, expr: A.Expr) -> Type:
        if isinstance(expr, A.Identifier):
            return self._lookup(expr.name, expr.line)
        if isinstance(expr, A.Member):
            obj_type = self._infer_expr_type(expr.obj)
            return self._member_type(obj_type, expr.name, expr.line, for_assignment=True)
        if isinstance(expr, A.Index):
            obj_type = self._infer_expr_type(expr.obj)
            index_type = self._infer_expr_type(expr.index)
            if isinstance(obj_type, ArrayType):
                if index_type != UNKNOWN and index_type != INT:
                    raise VerseCompileError(f"index must be int, got {format_type(index_type)}", expr.line)
                return obj_type.element_type
            if isinstance(obj_type, MapType):
                if not self._is_assignable(index_type, obj_type.key_type):
                    raise VerseCompileError(
                        f"cannot use {format_type(index_type)} to index {format_type(obj_type)}",
                        expr.line,
                    )
                return obj_type.value_type
            if obj_type == UNKNOWN:
                return UNKNOWN
            raise VerseCompileError(f"type {format_type(obj_type)} does not support index assignment", expr.line)
        raise VerseCompileError("invalid assignment target", expr.line)

    def _infer_expr_type(self, expr: A.Expr) -> Type:
        if isinstance(expr, A.IntLiteral):
            return INT
        if isinstance(expr, A.FloatLiteral):
            return FLOAT
        if isinstance(expr, A.StringLiteral):
            return STRING
        if isinstance(expr, A.LogicLiteral):
            return LOGIC
        if isinstance(expr, A.Identifier):
            return self._lookup(expr.name, expr.line)
        if isinstance(expr, A.SelfExpr):
            return self._lookup("self", expr.line)
        if isinstance(expr, A.Unary):
            operand = self._infer_expr_type(expr.operand)
            if expr.op == "-":
                if operand in (INT, FLOAT, UNKNOWN):
                    return operand
                raise VerseCompileError(f"cannot negate {format_type(operand)}", expr.line)
            if expr.op == "not":
                if operand in (LOGIC, UNKNOWN):
                    return LOGIC
                raise VerseCompileError(f"'not' requires logic, got {format_type(operand)}", expr.line)
            raise VerseCompileError(f"unknown unary operator '{expr.op}'", expr.line)
        if isinstance(expr, A.Binary):
            return self._infer_binary_type(expr)
        if isinstance(expr, A.Logical):
            left = self._infer_expr_type(expr.left)
            right = self._infer_expr_type(expr.right)
            for side in (left, right):
                if side not in (LOGIC, UNKNOWN):
                    raise VerseCompileError(f"'{expr.op}' requires logic operands", expr.line)
            return LOGIC
        if isinstance(expr, A.Range):
            start = self._infer_expr_type(expr.start)
            end = self._infer_expr_type(expr.end)
            if start not in (INT, UNKNOWN) or end not in (INT, UNKNOWN):
                raise VerseCompileError("ranges require int endpoints", expr.line)
            return RANGE
        if isinstance(expr, A.Call):
            return self._infer_call_type(expr)
        if isinstance(expr, A.Index):
            return self._infer_index_type(expr)
        if isinstance(expr, A.Member):
            return self._member_type(self._infer_expr_type(expr.obj), expr.name, expr.line)
        if isinstance(expr, A.FailableUnwrap):
            operand = self._infer_expr_type(expr.operand)
            if self._guarded_clause_depth == 0 and not self.current_allows_failure:
                raise VerseCompileError(
                    "failable unwrap '?' used outside a <decides> function or guarded if clause",
                    expr.line,
                )
            return operand.value_type if isinstance(operand, OptionType) else operand
        if isinstance(expr, A.ArrayLiteral):
            if not expr.elements:
                return ArrayType(UNKNOWN)
            first = self._infer_expr_type(expr.elements[0])
            for element in expr.elements[1:]:
                element_type = self._infer_expr_type(element)
                if not self._is_assignable(element_type, first) or not self._is_assignable(first, element_type):
                    raise VerseCompileError(
                        f"array literal mixes {format_type(first)} and {format_type(element_type)}",
                        expr.line,
                    )
            return ArrayType(first)
        if isinstance(expr, A.MapLiteral):
            if not expr.pairs:
                return MapType(UNKNOWN, UNKNOWN)
            first_key = self._infer_expr_type(expr.pairs[0][0])
            first_value = self._infer_expr_type(expr.pairs[0][1])
            for key_expr, value_expr in expr.pairs[1:]:
                key_type = self._infer_expr_type(key_expr)
                value_type = self._infer_expr_type(value_expr)
                if not self._is_assignable(key_type, first_key) or not self._is_assignable(first_key, key_type):
                    raise VerseCompileError(
                        f"map literal mixes {format_type(first_key)} and {format_type(key_type)} keys",
                        expr.line,
                    )
                if not self._is_assignable(value_type, first_value) or not self._is_assignable(first_value, value_type):
                    raise VerseCompileError(
                        f"map literal mixes {format_type(first_value)} and {format_type(value_type)} values",
                        expr.line,
                    )
            return MapType(first_key, first_value)
        if isinstance(expr, A.StructLiteral):
            return self._infer_struct_literal_type(expr)
        if isinstance(expr, A.IfExpr):
            return self._infer_if_expr_type(expr)
        if isinstance(expr, A.SpawnExpr):
            self._check_block_expr(expr.body)
            return TASK
        if isinstance(expr, A.SyncExpr):
            item_types = [self._infer_expr_type(item) for item in expr.items]
            if not item_types:
                return ArrayType(UNKNOWN)
            first = item_types[0]
            for item in item_types[1:]:
                if not self._is_assignable(item, first) or not self._is_assignable(first, item):
                    return ArrayType(UNKNOWN)
            return ArrayType(first)
        if isinstance(expr, A.RaceExpr):
            item_types = [self._infer_expr_type(item) for item in expr.items]
            if not item_types:
                return UNKNOWN
            first = item_types[0]
            for item in item_types[1:]:
                if not self._is_assignable(item, first) or not self._is_assignable(first, item):
                    return UNKNOWN
            return first
        raise VerseCompileError(f"cannot infer type for {type(expr).__name__}", expr.line)

    def _check_block_expr(self, block: A.Block):
        self._push_scope()
        for stmt in block.statements:
            self._check_stmt(stmt)
        self._pop_scope()

    def _infer_binary_type(self, expr: A.Binary) -> Type:
        left = self._infer_expr_type(expr.left)
        right = self._infer_expr_type(expr.right)
        if expr.op == "+":
            if left in (INT, FLOAT, UNKNOWN) and right in (INT, FLOAT, UNKNOWN):
                if left == FLOAT or right == FLOAT:
                    return FLOAT
                if left == UNKNOWN or right == UNKNOWN:
                    return UNKNOWN
                return INT
            if left == STRING and right == STRING:
                return STRING
            if isinstance(left, ArrayType) and isinstance(right, ArrayType):
                if self._is_assignable(left.element_type, right.element_type):
                    return ArrayType(right.element_type)
                if self._is_assignable(right.element_type, left.element_type):
                    return ArrayType(left.element_type)
            raise VerseCompileError(f"cannot add {format_type(left)} and {format_type(right)}", expr.line)
        if expr.op in ("-", "*", "/", "%"):
            if left not in (INT, FLOAT, UNKNOWN) or right not in (INT, FLOAT, UNKNOWN):
                if expr.op == "-":
                    raise VerseCompileError(
                        f"cannot subtract {format_type(right)} from {format_type(left)}",
                        expr.line,
                    )
                if expr.op == "*":
                    raise VerseCompileError(
                        f"cannot multiply {format_type(left)} and {format_type(right)}",
                        expr.line,
                    )
                if expr.op == "/":
                    raise VerseCompileError(
                        f"cannot divide {format_type(left)} by {format_type(right)}",
                        expr.line,
                    )
                raise VerseCompileError(
                    f"cannot compute {format_type(left)} % {format_type(right)}",
                    expr.line,
                )
            if expr.op == "/":
                return FLOAT
            if expr.op == "%" and left == INT and right == INT:
                return INT
            if left == FLOAT or right == FLOAT:
                return FLOAT
            if left == UNKNOWN or right == UNKNOWN:
                return UNKNOWN
            return INT
        if expr.op in ("=", "<>"):
            return LOGIC
        if expr.op in ("<", "<=", ">", ">="):
            comparable = (
                left in (INT, FLOAT, UNKNOWN) and right in (INT, FLOAT, UNKNOWN)
            ) or (left in (STRING, UNKNOWN) and right in (STRING, UNKNOWN))
            if not comparable:
                raise VerseCompileError(
                    f"cannot compare {format_type(left)} and {format_type(right)} with '{expr.op}'",
                    expr.line,
                )
            return LOGIC
        raise VerseCompileError(f"unknown operator '{expr.op}'", expr.line)

    def _infer_call_type(self, expr: A.Call) -> Type:
        # Effect check: if the callee is a named <decides> function, calling it
        # outside a guarded if/for clause requires the current function to also
        # be <decides> (the failure propagates to the caller).
        if isinstance(expr.callee, A.Identifier):
            callee_effects = self._func_effects.get(expr.callee.name, frozenset())
            if "decides" in callee_effects and self._guarded_clause_depth == 0 and not self.current_allows_failure:
                raise VerseCompileError(
                    f"'{expr.callee.name}' is <decides> and must be called inside an if clause"
                    " or from a <decides> function",
                    expr.line,
                )
        callee_type = self._infer_expr_type(expr.callee)
        if isinstance(callee_type, BuiltinType):
            return self._infer_builtin_call(expr, callee_type.name)
        if isinstance(callee_type, FunctionType):
            if len(expr.args) != len(callee_type.param_types):
                raise VerseCompileError(
                    f"function expects {len(callee_type.param_types)} argument(s), got {len(expr.args)}",
                    expr.line,
                )
            for i, (arg, param_type) in enumerate(zip(expr.args, callee_type.param_types), start=1):
                arg_type = self._infer_expr_type(arg)
                if not self._is_assignable(arg_type, param_type):
                    raise VerseCompileError(
                        f"argument {i} expects {format_type(param_type)}, got {format_type(arg_type)}",
                        arg.line,
                    )
            return callee_type.return_type
        if callee_type in (FUNCTION, UNKNOWN):
            for arg in expr.args:
                self._infer_expr_type(arg)
            return UNKNOWN
        raise VerseCompileError(f"value of type {format_type(callee_type)} is not callable", expr.line)

    def _infer_builtin_call(self, expr: A.Call, name: str) -> Type:
        args = expr.args
        if name in {"Print", "Log"}:
            self._expect_arity(name, args, 1, expr.line)
            self._infer_expr_type(args[0])
            return VOID
        if name == "ToString":
            self._expect_arity(name, args, 1, expr.line)
            self._infer_expr_type(args[0])
            return STRING
        if name == "option":
            self._expect_arity(name, args, 1, expr.line)
            return OptionType(self._infer_expr_type(args[0]))
        if name == "Length":
            self._expect_arity(name, args, 1, expr.line)
            arg_type = self._infer_expr_type(args[0])
            if arg_type not in (STRING, UNKNOWN) and not isinstance(arg_type, (ArrayType, MapType)):
                raise VerseCompileError(f"Length() does not support {format_type(arg_type)}", args[0].line)
            return INT
        if name == "Contains":
            self._expect_arity(name, args, 2, expr.line)
            container_type = self._infer_expr_type(args[0])
            needle_type = self._infer_expr_type(args[1])
            if isinstance(container_type, ArrayType):
                if not self._is_assignable(needle_type, container_type.element_type):
                    raise VerseCompileError(
                        f"argument 2 expects {format_type(container_type.element_type)}, got {format_type(needle_type)}",
                        args[1].line,
                    )
            elif isinstance(container_type, MapType):
                if not self._is_assignable(needle_type, container_type.key_type):
                    raise VerseCompileError(
                        f"argument 2 expects {format_type(container_type.key_type)}, got {format_type(needle_type)}",
                        args[1].line,
                    )
            elif container_type == STRING and needle_type != STRING:
                raise VerseCompileError("argument 2 expects string, got " + format_type(needle_type), args[1].line)
            elif container_type not in (STRING, UNKNOWN) and not isinstance(container_type, (ArrayType, MapType)):
                raise VerseCompileError(
                    f"Contains() does not support {format_type(container_type)}",
                    args[0].line,
                )
            return LOGIC
        if name == "Keys":
            self._expect_arity(name, args, 1, expr.line)
            map_type = self._infer_expr_type(args[0])
            if isinstance(map_type, MapType):
                return ArrayType(map_type.key_type)
            if map_type != UNKNOWN:
                raise VerseCompileError(f"Keys() requires a map, got {format_type(map_type)}", args[0].line)
            return ArrayType(UNKNOWN)
        if name == "Values":
            self._expect_arity(name, args, 1, expr.line)
            map_type = self._infer_expr_type(args[0])
            if isinstance(map_type, MapType):
                return ArrayType(map_type.value_type)
            if map_type != UNKNOWN:
                raise VerseCompileError(f"Values() requires a map, got {format_type(map_type)}", args[0].line)
            return ArrayType(UNKNOWN)
        if name in {"Abs", "Floor", "Ceil", "Sqrt"}:
            self._expect_arity(name, args, 1, expr.line)
            value_type = self._infer_expr_type(args[0])
            self._require_number(value_type, name, args[0].line)
            if name in {"Floor", "Ceil"}:
                return INT
            if name == "Sqrt":
                return FLOAT
            return value_type
        if name in {"Min", "Max"}:
            self._expect_arity(name, args, 2, expr.line)
            left = self._infer_expr_type(args[0])
            right = self._infer_expr_type(args[1])
            self._require_number(left, name, args[0].line)
            self._require_number(right, name, args[1].line)
            if left == FLOAT or right == FLOAT:
                return FLOAT
            if left == UNKNOWN or right == UNKNOWN:
                return UNKNOWN
            return INT
        raise VerseCompileError(f"unsupported builtin '{name}'", expr.line)

    def _infer_index_type(self, expr: A.Index) -> Type:
        obj_type = self._infer_expr_type(expr.obj)
        index_type = self._infer_expr_type(expr.index)
        if isinstance(obj_type, ArrayType):
            if index_type not in (INT, UNKNOWN):
                raise VerseCompileError(f"array index must be int, got {format_type(index_type)}", expr.line)
            return obj_type.element_type
        if isinstance(obj_type, MapType):
            if not self._is_assignable(index_type, obj_type.key_type):
                raise VerseCompileError(
                    f"cannot use {format_type(index_type)} to index {format_type(obj_type)}",
                    expr.line,
                )
            return OptionType(obj_type.value_type)
        if obj_type == STRING:
            if index_type not in (INT, UNKNOWN):
                raise VerseCompileError(f"string index must be int, got {format_type(index_type)}", expr.line)
            return STRING
        if obj_type == UNKNOWN:
            return UNKNOWN
        raise VerseCompileError(f"type {format_type(obj_type)} does not support indexing", expr.line)

    def _infer_struct_literal_type(self, expr: A.StructLiteral) -> Type:
        if expr.type_name not in self.classes:
            raise VerseCompileError(f"unknown class '{expr.type_name}'", expr.line)
        for name, value in expr.fields:
            field_type = self._class_field_type(expr.type_name, name, expr.line)
            value_type = self._infer_expr_type(value)
            if not self._is_assignable(value_type, field_type):
                raise VerseCompileError(
                    f"cannot assign {format_type(value_type)} to {format_type(field_type)}",
                    value.line,
                )
        return ClassType(expr.type_name)

    def _infer_if_expr_type(self, expr: A.IfExpr) -> Type:
        self._guarded_clause_depth += 1
        try:
            bindings = self._collect_clause_bindings(expr.clauses)
        finally:
            self._guarded_clause_depth -= 1
        self._push_scope()
        for name, typ in bindings.items():
            self._define(name, typ)
        then_type = self._block_expr_type(expr.then_branch)
        self._pop_scope()
        else_type = VOID if expr.else_branch is None else self._block_expr_type(expr.else_branch)
        if self._is_assignable(then_type, else_type):
            return else_type
        if self._is_assignable(else_type, then_type):
            return then_type
        return UNKNOWN

    def _block_expr_type(self, block: A.Block) -> Type:
        if not block.statements:
            return VOID
        last = block.statements[-1]
        if not isinstance(last, A.ExprStmt):
            raise VerseCompileError("expected expression branch", last.line)
        return self._infer_expr_type(last.expr)

    def _member_type(self, obj_type: Type, name: str, line: int, for_assignment: bool = False) -> Type:
        if isinstance(obj_type, TaskType):
            if name in {"Done", "Failed"}:
                return LOGIC
            if name == "Result":
                return UNKNOWN
            raise VerseCompileError(f"task has no member '{name}'", line)
        if isinstance(obj_type, ClassType):
            field_type = self._class_field_type(obj_type.name, name, line, required=False)
            if field_type is not None:
                return field_type
            method_type = self._class_method_type(obj_type.name, name)
            if method_type is not None:
                if for_assignment:
                    raise VerseCompileError(f"method '{name}' is not assignable", line)
                return method_type
            raise VerseCompileError(f"'{obj_type.name}' has no field or method '{name}'", line)
        if obj_type == UNKNOWN:
            return UNKNOWN
        raise VerseCompileError(f"type {format_type(obj_type)} has no member '{name}'", line)

    def _class_field_type(self, class_name: str, field_name: str, line: int, required: bool = True) -> Type | None:
        info = self.classes[class_name]
        if field_name in info.fields:
            return info.fields[field_name]
        if info.base is not None:
            return self._class_field_type(info.base, field_name, line, required)
        if required:
            raise VerseCompileError(f"class '{class_name}' has no field '{field_name}'", line)
        return None

    def _class_method_type(self, class_name: str, method_name: str) -> FunctionType | Type | None:
        info = self.classes[class_name]
        if method_name in info.methods:
            return info.methods[method_name]
        if info.base is not None:
            return self._class_method_type(info.base, method_name)
        return None

    def _iterable_item_type(self, iterable_type: Type, line: int) -> Type:
        if isinstance(iterable_type, ArrayType):
            return iterable_type.element_type
        if isinstance(iterable_type, MapType):
            return ArrayType(UNKNOWN)
        if iterable_type in (RANGE, UNKNOWN):
            return INT if iterable_type == RANGE else UNKNOWN
        raise VerseCompileError(f"cannot iterate over {format_type(iterable_type)}", line)

    def _expect_arity(self, name: str, args: list[A.Expr], count: int, line: int):
        if len(args) != count:
            raise VerseCompileError(f"{name}() takes exactly {count} argument(s), got {len(args)}", line)

    def _require_number(self, typ: Type, name: str, line: int):
        if typ not in (INT, FLOAT, UNKNOWN):
            raise VerseCompileError(f"{name}() requires a number, got {format_type(typ)}", line)

    def _is_assignable(self, source: Type, target: Type) -> bool:
        if source == UNKNOWN or target == UNKNOWN:
            return True
        if target == FUNCTION:
            return source == FUNCTION or isinstance(source, FunctionType)
        if source == FUNCTION:
            return target == FUNCTION
        if isinstance(source, FunctionType) and isinstance(target, FunctionType):
            return (
                len(source.param_types) == len(target.param_types)
                and all(self._is_assignable(a, b) and self._is_assignable(b, a) for a, b in zip(source.param_types, target.param_types))
                and self._is_assignable(source.return_type, target.return_type)
            )
        if isinstance(source, ArrayType) and isinstance(target, ArrayType):
            return self._is_assignable(source.element_type, target.element_type)
        if isinstance(source, MapType) and isinstance(target, MapType):
            return self._is_assignable(source.key_type, target.key_type) and self._is_assignable(source.value_type, target.value_type)
        if isinstance(source, OptionType) and isinstance(target, OptionType):
            return self._is_assignable(source.value_type, target.value_type)
        if isinstance(source, ClassType) and isinstance(target, ClassType):
            return self._is_subclass(source.name, target.name)
        return source == target

    def _is_subclass(self, source: str, target: str) -> bool:
        current = source
        while True:
            if current == target:
                return True
            info = self.classes.get(current)
            if info is None or info.base is None:
                return False
            current = info.base
