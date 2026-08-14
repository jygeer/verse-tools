"""Recursive-descent parser for the versetools Verse-core dialect.

Grammar overview (see docs/language-reference.md for the full spec):

    program     := statement*
    statement   := var_decl | assign | if_stmt | for_stmt | loop_stmt
                 | break_stmt | continue_stmt | return_stmt
                 | func_decl | class_decl | const_decl | expr_stmt
    expression  := or_expr
    or_expr     := and_expr ("or" and_expr)*
    and_expr    := not_expr ("and" not_expr)*
    not_expr    := "not" not_expr | comparison
    comparison  := range (("=" | "<>" | "<" | "<=" | ">" | ">=") range)?
    range       := additive (".." additive)?
    additive    := multiplicative (("+" | "-") multiplicative)*
    multiplicative := unary (("*" | "/" | "%") unary)*
    unary       := "-" unary | postfix
    postfix     := primary ( call | index | member | "?" )*
    primary     := literals | identifier | "(" expression ")"
                 | array/map/struct literal | if_expr
                 | spawn_expr | sync_expr | race_expr | "self"

A statement that begins with an identifier is ambiguous between a
function declaration, a constant/const declaration, a class declaration
and a plain expression statement; `_parse_ident_led_statement` resolves
that with small bounded lookahead/backtracking rather than a separate
grammar production, mirroring how the token stream actually disambiguates
in practice.
"""

from __future__ import annotations

from . import ast_nodes as A
from .errors import VerseSyntaxError
from .tokens import Token, TokenType as T

_COMPARISON_OPS = {T.ASSIGN: "=", T.NE: "<>", T.LT: "<", T.LE: "<=", T.GT: ">", T.GE: ">="}
_ADDITIVE_OPS = {T.PLUS: "+", T.MINUS: "-"}
_MULT_OPS = {T.STAR: "*", T.SLASH: "/", T.PERCENT: "%"}


class _Backtrack(Exception):
    """Internal signal used to abandon a speculative parse attempt."""


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # -- token stream helpers ----------------------------------------
    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _check(self, type_: T) -> bool:
        return self._peek().type == type_

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != T.EOF:
            self.pos += 1
        return tok

    def _match(self, type_: T) -> Token | None:
        if self._check(type_):
            return self._advance()
        return None

    def _expect(self, type_: T, msg: str | None = None) -> Token:
        if not self._check(type_):
            tok = self._peek()
            raise VerseSyntaxError(
                msg or f"expected {type_.name} but found {tok.type.name} ({tok.lexeme!r})",
                tok.line,
            )
        return self._advance()

    def _skip_newlines(self):
        while self._check(T.NEWLINE):
            self._advance()

    def _expect_stmt_end(self):
        """Consume the NEWLINE that ends a statement - unless the
        statement's own value already ended in an indented block (e.g. a
        `spawn:`/`sync:`/`race:` expression), which self-terminates with
        a DEDENT and leaves no separate trailing NEWLINE token."""
        if self._match(T.NEWLINE):
            return
        if self.pos > 0 and self.tokens[self.pos - 1].type == T.DEDENT:
            return
        tok = self._peek()
        raise VerseSyntaxError(
            f"expected end of statement but found {tok.type.name} ({tok.lexeme!r})", tok.line
        )

    def _at_end(self) -> bool:
        return self._check(T.EOF)

    # -- entry point ----------------------------------------------------
    def parse_program(self) -> A.Program:
        body = []
        self._skip_newlines()
        while not self._at_end():
            body.append(self.parse_statement())
            self._skip_newlines()
        return A.Program(body=body)

    # ==================================================================
    # Statements
    # ==================================================================
    def parse_statement(self) -> A.Stmt:
        tok = self._peek()
        if tok.type == T.VAR:
            return self._parse_var_decl()
        if tok.type == T.SET:
            return self._parse_assign()
        if tok.type == T.IF:
            return self._parse_if_stmt()
        if tok.type == T.FOR:
            return self._parse_for_stmt()
        if tok.type == T.LOOP:
            return self._parse_loop_stmt()
        if tok.type == T.BREAK:
            self._advance()
            self._expect_stmt_end()
            return A.Break(line=tok.line)
        if tok.type == T.CONTINUE:
            self._advance()
            self._expect_stmt_end()
            return A.Continue(line=tok.line)
        if tok.type == T.RETURN:
            self._advance()
            value = None
            if not self._check(T.NEWLINE):
                value = self.parse_expression()
            self._expect_stmt_end()
            return A.Return(value=value, line=tok.line)
        if tok.type == T.IDENT:
            return self._parse_ident_led_statement()
        expr = self.parse_expression()
        self._expect_stmt_end()
        return A.ExprStmt(expr=expr, line=tok.line)

    def _parse_block(self) -> A.Block:
        line = self._peek().line
        if self._match(T.NEWLINE):
            self._expect(T.INDENT)
            stmts = []
            self._skip_newlines()
            while not self._check(T.DEDENT):
                stmts.append(self.parse_statement())
                self._skip_newlines()
            self._expect(T.DEDENT)
            return A.Block(statements=stmts, line=line)
        # inline single statement body (e.g. `Foo() : int = X + 1`)
        stmt = self.parse_statement()
        return A.Block(statements=[stmt], line=line)

    # -- var / assignment ----------------------------------------------------
    def _parse_var_decl(self) -> A.VarDecl:
        line = self._advance().line  # 'var'
        name = self._expect(T.IDENT).value
        type_ann = None
        if self._match(T.COLON):
            type_ann = self._parse_type()
        value = None
        if self._match(T.ASSIGN):
            value = self.parse_expression()
        self._expect_stmt_end()
        return A.VarDecl(name=name, type_ann=type_ann, value=value, mutable=True, line=line)

    def _parse_assign(self) -> A.Assign:
        line = self._advance().line  # 'set'
        target = self.parse_postfix()
        self._expect(T.ASSIGN)
        value = self.parse_expression()
        self._expect_stmt_end()
        return A.Assign(target=target, value=value, line=line)

    # -- if / for / loop ----------------------------------------------------
    def _parse_if_clauses(self) -> list[A.IfClause]:
        self._expect(T.LPAREN)
        clauses = []
        while True:
            if self._check(T.IDENT) and self._peek(1).type == T.DEFINE:
                name_tok = self._advance()
                self._advance()  # ':='
                expr = self.parse_expression()
                clauses.append(A.IfClause(name=name_tok.value, expr=expr, line=name_tok.line))
            else:
                expr = self.parse_expression()
                clauses.append(A.IfClause(name=None, expr=expr, line=expr.line))
            if not self._match(T.COMMA):
                break
        self._expect(T.RPAREN)
        return clauses

    def _parse_if_stmt(self) -> A.If:
        line = self._advance().line  # 'if'
        clauses = self._parse_if_clauses()
        if self._match(T.COLON):
            then_b = self._parse_block()
            else_b = None
            if self._match(T.ELSE):
                if self._check(T.IF):
                    else_b = A.Block(statements=[self._parse_if_stmt()], line=self._peek().line)
                else:
                    self._expect(T.COLON)
                    else_b = self._parse_block()
            return A.If(clauses=clauses, then_branch=then_b, else_branch=else_b, line=line)
        if self._match(T.THEN):
            then_expr = self.parse_expression()
            else_b = None
            if self._match(T.ELSE):
                else_expr = self.parse_expression()
                else_b = A.Block(statements=[A.ExprStmt(expr=else_expr, line=line)], line=line)
            self._expect_stmt_end()
            then_b = A.Block(statements=[A.ExprStmt(expr=then_expr, line=line)], line=line)
            return A.If(clauses=clauses, then_branch=then_b, else_branch=else_b, line=line)
        raise VerseSyntaxError("expected ':' or 'then' after if-condition", line)

    def parse_if_expr(self) -> A.IfExpr:
        line = self._advance().line  # 'if'
        clauses = self._parse_if_clauses()
        self._expect(T.THEN, "an 'if' used inside an expression needs 'then ... else ...'")
        then_expr = self.parse_expression()
        else_b = None
        if self._match(T.ELSE):
            else_expr = self.parse_expression()
            else_b = A.Block(statements=[A.ExprStmt(expr=else_expr, line=line)], line=line)
        then_b = A.Block(statements=[A.ExprStmt(expr=then_expr, line=line)], line=line)
        return A.IfExpr(clauses=clauses, then_branch=then_b, else_branch=else_b, line=line)

    def _parse_for_stmt(self) -> A.For:
        line = self._advance().line  # 'for'
        self._expect(T.LPAREN)
        var_name = self._expect(T.IDENT).value
        self._expect(T.COLON)
        iterable = self.parse_expression()
        filters = []
        while self._match(T.COMMA):
            filters.append(self.parse_expression())
        self._expect(T.RPAREN)
        if self._match(T.COLON):
            body = self._parse_block()
        elif self._match(T.DO):
            body_expr = self.parse_expression()
            self._expect_stmt_end()
            body = A.Block(statements=[A.ExprStmt(expr=body_expr, line=line)], line=line)
        else:
            raise VerseSyntaxError("expected ':' or 'do' after for-header", line)
        return A.For(var_name=var_name, iterable=iterable, filters=filters, body=body, line=line)

    def _parse_loop_stmt(self) -> A.Loop:
        line = self._advance().line  # 'loop'
        self._expect(T.COLON)
        body = self._parse_block()
        return A.Loop(body=body, line=line)

    # -- functions / classes ----------------------------------------------------
    def _parse_ident_led_statement(self) -> A.Stmt:
        start = self.pos
        name_tok = self._advance()  # IDENT
        if self._match(T.DEFINE):
            if self._check(T.CLASS):
                return self._parse_class_decl(name_tok.value, name_tok.line)
            value = self.parse_expression()
            self._expect_stmt_end()
            return A.VarDecl(
                name=name_tok.value, type_ann=None, value=value, mutable=False, line=name_tok.line
            )
        if self._check(T.LPAREN):
            self.pos = start
            saved = self.pos
            fn = self._try_parse_func_decl()
            if fn is not None:
                return fn
            self.pos = saved
            expr = self.parse_expression()
            self._expect_stmt_end()
            return A.ExprStmt(expr=expr, line=name_tok.line)
        if self._check(T.COLON):
            self._advance()
            type_ann = self._parse_type()
            self._expect(T.ASSIGN)
            value = self.parse_expression()
            self._expect_stmt_end()
            return A.VarDecl(
                name=name_tok.value,
                type_ann=type_ann,
                value=value,
                mutable=False,
                line=name_tok.line,
            )
        self.pos = start
        expr = self.parse_expression()
        self._expect_stmt_end()
        return A.ExprStmt(expr=expr, line=name_tok.line)

    def _try_parse_func_decl(self) -> A.FuncDecl | None:
        """Speculatively parse `Name(params) <effects> : type = body`.

        Returns None (without raising) if the prefix cannot possibly be a
        function declaration, so the caller can fall back to parsing an
        ordinary expression statement instead.
        """
        try:
            name_tok = self._advance()  # IDENT
            if not self._match(T.LPAREN):
                return None
            params = self._parse_param_list()
            if not self._match(T.RPAREN):
                return None
            effects = self._parse_effect_list()
            return_type = None
            if self._match(T.COLON):
                return_type = self._parse_type()
            if not self._match(T.ASSIGN):
                return None
        except VerseSyntaxError:
            return None
        # Signature matched unambiguously - from here on this can only be a
        # function declaration, so let any syntax error in the body surface
        # as a real error instead of triggering a confusing fallback.
        body = self._parse_block()
        return A.FuncDecl(
            name=name_tok.value,
            params=params,
            effects=effects,
            return_type=return_type,
            body=body,
            line=name_tok.line,
        )

    def _parse_param_list(self) -> list[A.Param]:
        params = []
        if self._check(T.RPAREN):
            return params
        while True:
            tok = self._expect(T.IDENT)
            type_ann = None
            if self._match(T.COLON):
                type_ann = self._parse_type()
            default = None
            if self._match(T.ASSIGN):
                default = self.parse_expression()
            params.append(A.Param(name=tok.value, type_ann=type_ann, default=default, line=tok.line))
            if not self._match(T.COMMA):
                break
        return params

    def _parse_effect_list(self) -> list[str]:
        effects = []
        while self._check(T.LT):
            self._advance()
            while True:
                effects.append(self._expect(T.IDENT).value)
                if not self._match(T.COMMA):
                    break
            self._expect(T.GT)
        return effects

    def _parse_class_decl(self, name: str, line: int) -> A.ClassDecl:
        self._advance()  # 'class'
        base = None
        if self._match(T.LPAREN):
            base = self._expect(T.IDENT).value
            self._expect(T.RPAREN)
        self._expect(T.COLON)
        self._expect_stmt_end()
        self._expect(T.INDENT)
        fields: list[A.FieldDecl] = []
        methods: list[A.FuncDecl] = []
        self._skip_newlines()
        while not self._check(T.DEDENT):
            member_start = self.pos
            fn = self._try_parse_func_decl()
            if fn is not None:
                methods.append(fn)
            else:
                self.pos = member_start
                fname_tok = self._expect(T.IDENT)
                type_ann = None
                if self._match(T.COLON):
                    type_ann = self._parse_type()
                default = None
                if self._match(T.ASSIGN):
                    default = self.parse_expression()
                self._expect_stmt_end()
                fields.append(
                    A.FieldDecl(
                        name=fname_tok.value,
                        type_ann=type_ann,
                        default=default,
                        line=fname_tok.line,
                    )
                )
            self._skip_newlines()
        self._expect(T.DEDENT)
        return A.ClassDecl(name=name, base=base, fields=fields, methods=methods, line=line)

    # -- types ----------------------------------------------------
    def _parse_type(self) -> str:
        if self._match(T.QUESTION):
            return "?" + self._parse_type()
        if self._match(T.LBRACKET):
            if self._match(T.RBRACKET):
                return "[]" + self._parse_type()
            key = self._parse_type()
            self._expect(T.RBRACKET)
            val = self._parse_type()
            return f"[{key}]{val}"
        return self._expect(T.IDENT).value

    # ==================================================================
    # Expressions
    # ==================================================================
    def parse_expression(self) -> A.Expr:
        return self._parse_or()

    def _parse_or(self) -> A.Expr:
        left = self._parse_and()
        while self._check(T.OR):
            line = self._advance().line
            right = self._parse_and()
            left = A.Logical(op="or", left=left, right=right, line=line)
        return left

    def _parse_and(self) -> A.Expr:
        left = self._parse_not()
        while self._check(T.AND):
            line = self._advance().line
            right = self._parse_not()
            left = A.Logical(op="and", left=left, right=right, line=line)
        return left

    def _parse_not(self) -> A.Expr:
        if self._check(T.NOT):
            line = self._advance().line
            operand = self._parse_not()
            return A.Unary(op="not", operand=operand, line=line)
        return self._parse_comparison()

    def _parse_comparison(self) -> A.Expr:
        left = self._parse_range()
        if self._peek().type in _COMPARISON_OPS:
            tok = self._advance()
            right = self._parse_range()
            return A.Binary(op=_COMPARISON_OPS[tok.type], left=left, right=right, line=tok.line)
        return left

    def _parse_range(self) -> A.Expr:
        left = self._parse_additive()
        if self._check(T.DOTDOT):
            line = self._advance().line
            right = self._parse_additive()
            return A.Range(start=left, end=right, line=line)
        return left

    def _parse_additive(self) -> A.Expr:
        left = self._parse_multiplicative()
        while self._peek().type in _ADDITIVE_OPS:
            tok = self._advance()
            right = self._parse_multiplicative()
            left = A.Binary(op=_ADDITIVE_OPS[tok.type], left=left, right=right, line=tok.line)
        return left

    def _parse_multiplicative(self) -> A.Expr:
        left = self._parse_unary()
        while self._peek().type in _MULT_OPS:
            tok = self._advance()
            right = self._parse_unary()
            left = A.Binary(op=_MULT_OPS[tok.type], left=left, right=right, line=tok.line)
        return left

    def _parse_unary(self) -> A.Expr:
        if self._check(T.MINUS):
            line = self._advance().line
            operand = self._parse_unary()
            return A.Unary(op="-", operand=operand, line=line)
        return self.parse_postfix()

    def parse_postfix(self) -> A.Expr:
        expr = self._parse_primary()
        while True:
            if self._check(T.LPAREN):
                self._advance()
                args = self._parse_arg_list()
                self._expect(T.RPAREN)
                expr = A.Call(callee=expr, args=args, line=expr.line)
            elif self._check(T.LBRACKET):
                self._advance()
                idx = self.parse_expression()
                self._expect(T.RBRACKET)
                expr = A.Index(obj=expr, index=idx, line=expr.line)
            elif self._check(T.DOT):
                self._advance()
                name = self._expect(T.IDENT).value
                expr = A.Member(obj=expr, name=name, line=expr.line)
            elif self._check(T.QUESTION):
                self._advance()
                expr = A.FailableUnwrap(operand=expr, line=expr.line)
            else:
                break
        return expr

    def _parse_arg_list(self) -> list[A.Expr]:
        args = []
        if self._check(T.RPAREN):
            return args
        while True:
            args.append(self.parse_expression())
            if not self._match(T.COMMA):
                break
        return args

    def _parse_primary(self) -> A.Expr:
        tok = self._peek()

        if tok.type == T.NUMBER_INT:
            self._advance()
            return A.IntLiteral(value=tok.value, line=tok.line)
        if tok.type == T.NUMBER_FLOAT:
            self._advance()
            return A.FloatLiteral(value=tok.value, line=tok.line)
        if tok.type == T.STRING:
            self._advance()
            return A.StringLiteral(value=tok.value, line=tok.line)
        if tok.type == T.TRUE:
            self._advance()
            return A.LogicLiteral(value=True, line=tok.line)
        if tok.type == T.FALSE:
            self._advance()
            return A.LogicLiteral(value=False, line=tok.line)
        if tok.type == T.SELF:
            self._advance()
            return A.SelfExpr(line=tok.line)
        if tok.type == T.LPAREN:
            self._advance()
            expr = self.parse_expression()
            self._expect(T.RPAREN)
            return expr
        if tok.type == T.IF:
            return self.parse_if_expr()
        if tok.type == T.SPAWN:
            self._advance()
            self._expect(T.COLON)
            body = self._parse_block()
            return A.SpawnExpr(body=body, line=tok.line)
        if tok.type == T.SYNC:
            self._advance()
            self._expect(T.COLON)
            body = self._parse_block()
            return A.SyncExpr(items=[s.expr for s in body.statements if isinstance(s, A.ExprStmt)], line=tok.line)
        if tok.type == T.RACE:
            self._advance()
            self._expect(T.COLON)
            body = self._parse_block()
            return A.RaceExpr(items=[s.expr for s in body.statements if isinstance(s, A.ExprStmt)], line=tok.line)
        if tok.type == T.IDENT:
            self._advance()
            if self._check(T.LBRACE):
                return self._parse_brace_literal(tok.value, tok.line)
            return A.Identifier(name=tok.value, line=tok.line)

        raise VerseSyntaxError(f"unexpected token {tok.type.name} ({tok.lexeme!r})", tok.line)

    def _parse_brace_literal(self, name: str, line: int) -> A.Expr:
        self._advance()  # '{'
        if name == "array":
            elements = []
            while not self._check(T.RBRACE):
                elements.append(self.parse_expression())
                if not self._match(T.COMMA):
                    break
            self._expect(T.RBRACE)
            return A.ArrayLiteral(elements=elements, line=line)
        if name == "map":
            pairs = []
            while not self._check(T.RBRACE):
                k = self.parse_expression()
                self._expect(T.FATARROW)
                v = self.parse_expression()
                pairs.append((k, v))
                if not self._match(T.COMMA):
                    break
            self._expect(T.RBRACE)
            return A.MapLiteral(pairs=pairs, line=line)
        fields = []
        while not self._check(T.RBRACE):
            fname = self._expect(T.IDENT).value
            self._expect(T.DEFINE)
            fval = self.parse_expression()
            fields.append((fname, fval))
            if not self._match(T.COMMA):
                break
        self._expect(T.RBRACE)
        return A.StructLiteral(type_name=name, fields=fields, line=line)


def parse(tokens: list[Token]) -> A.Program:
    return Parser(tokens).parse_program()
