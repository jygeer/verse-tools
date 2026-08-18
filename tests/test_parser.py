import pytest

from versetools import ast_nodes as A
from versetools.errors import VerseSyntaxError
from versetools.lexer import tokenize
from versetools.parser import parse


def parse_src(src: str) -> A.Program:
    return parse(tokenize(src))


def test_function_decl_shape():
    prog = parse_src("Add(X : int, Y : int) : int =\n    return X + Y\n")
    fn = prog.body[0]
    assert isinstance(fn, A.FuncDecl)
    assert fn.name == "Add"
    assert [p.name for p in fn.params] == ["X", "Y"]
    assert fn.return_type == "int"
    assert isinstance(fn.body.statements[0], A.Return)


def test_effect_specifiers():
    prog = parse_src("F()<decides><transacts> : int =\n    return 1\n")
    fn = prog.body[0]
    assert fn.effects == ["decides", "transacts"]


def test_const_and_var_decl():
    prog = parse_src("X := 1\nvar Y : int = 2\n")
    assert isinstance(prog.body[0], A.VarDecl) and prog.body[0].mutable is False
    assert isinstance(prog.body[1], A.VarDecl) and prog.body[1].mutable is True


def test_if_block_form_with_else_if_chain():
    src = (
        "if (X > 0):\n"
        "    Y := 1\n"
        "else if (X < 0):\n"
        "    Y := 2\n"
        "else:\n"
        "    Y := 3\n"
    )
    stmt = parse_src(src).body[0]
    assert isinstance(stmt, A.If)
    assert isinstance(stmt.else_branch.statements[0], A.If)


def test_if_binding_clause():
    prog = parse_src("if (Y := F()):\n    Print(Y)\n")
    stmt = prog.body[0]
    assert stmt.clauses[0].name == "Y"


def test_inline_if_expr_requires_then():
    with pytest.raises(VerseSyntaxError):
        parse_src("X := if (true) 1 else 2\n")


def test_array_map_struct_literals():
    prog = parse_src(
        'A := array{1, 2, 3}\n'
        'M := map{1 => "one"}\n'
        'S := Point{X := 1, Y := 2}\n'
    )
    assert isinstance(prog.body[0].value, A.ArrayLiteral)
    assert isinstance(prog.body[1].value, A.MapLiteral)
    assert isinstance(prog.body[2].value, A.StructLiteral)
    assert prog.body[2].value.type_name == "Point"


def test_class_decl_with_base_and_method():
    src = "shape := class:\n    Name : string = \"s\"\nchild := class(shape):\n    Area() : int =\n        return 1\n"
    prog = parse_src(src)
    base = prog.body[0]
    child = prog.body[1]
    assert isinstance(base, A.ClassDecl) and base.base is None
    assert isinstance(child, A.ClassDecl) and child.base == "shape"
    assert child.methods[0].name == "Area"


def test_class_decl_with_interfaces_access_and_abstract():
    src = (
        "iface := class<abstract>:\n"
        "    Run<abstract>() : int =\n"
        "worker := class(iface) : Tickable, Runnable:\n"
        "    Secret<private> : int = 1\n"
        "    Run<protected>() : int =\n"
        "        return self.Secret\n"
    )
    prog = parse_src(src)
    iface = prog.body[0]
    worker = prog.body[1]
    assert isinstance(iface, A.ClassDecl)
    assert iface.is_abstract is True
    assert iface.methods[0].is_abstract is True
    assert isinstance(worker, A.ClassDecl)
    assert worker.interfaces == ["Tickable", "Runnable"]
    assert worker.fields[0].access == "private"
    assert worker.methods[0].access == "protected"


def test_for_with_filter():
    prog = parse_src("for (N : 0..9, N > 2):\n    Print(N)\n")
    stmt = prog.body[0]
    assert isinstance(stmt, A.For)
    assert len(stmt.filters) == 1


def test_postfix_chain_call_index_member_unwrap():
    prog = parse_src("X := A.B[0](1)?\n")
    expr = prog.body[0].value
    assert isinstance(expr, A.FailableUnwrap)
    assert isinstance(expr.operand, A.Call)


def test_spawn_sync_race_parse():
    prog = parse_src(
        "Main() : void =\n"
        "    T := spawn:\n"
        "        F()\n"
        "    R := sync:\n"
        "        F()\n"
        "        G()\n"
        "    W := race:\n"
        "        F()\n"
        "        G()\n"
    )
    body = prog.body[0].body.statements
    assert isinstance(body[0].value, A.SpawnExpr)
    assert isinstance(body[1].value, A.SyncExpr) and len(body[1].value.items) == 2
    assert isinstance(body[2].value, A.RaceExpr) and len(body[2].value.items) == 2


def test_missing_dedent_raises_syntax_error():
    with pytest.raises(VerseSyntaxError):
        parse_src("if (true):\nPrint(1)\n")
