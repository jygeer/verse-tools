import pytest

from versetools.errors import VerseFailure, VerseRuntimeError


def test_arithmetic_and_precedence(runner):
    runner.run("Print(ToString(2 + 3 * 4))\n")
    assert runner.output == "14"


def test_string_concat_and_comparison(runner):
    runner.run('Print(ToString("a" + "b" = "ab"))\n')
    assert runner.output == "true"


def test_logic_is_distinct_from_int(runner):
    runner.run("Print(ToString(true = 1))\n")
    assert runner.output == "false"


def test_and_or_short_circuit(runner):
    runner.run(
        "SideEffect() : logic =\n"
        "    Print(\"called\")\n"
        "    return true\n"
        "Main() : void =\n"
        "    X := false and SideEffect()\n"
        "    Y := true or SideEffect()\n"
        "Main()\n"
    )
    assert runner.output == ""  # SideEffect never called


def test_if_else_branching(runner):
    runner.run(
        "F(N : int) : string =\n"
        "    if (N > 0):\n"
        "        return \"pos\"\n"
        "    else:\n"
        "        return \"non-pos\"\n"
        "Print(F(5))\n"
        "Print(F(-1))\n"
    )
    assert runner.output == "pos\nnon-pos"


def test_loop_break_continue(runner):
    runner.run(
        "var I : int = 0\n"
        "loop:\n"
        "    set I = I + 1\n"
        "    if (I = 2):\n"
        "        continue\n"
        "    if (I > 4):\n"
        "        break\n"
        "    Print(ToString(I))\n"
    )
    assert runner.output == "1\n3\n4"


def test_for_over_array_and_range(runner):
    runner.run(
        'for (X : array{"a", "b"}):\n'
        "    Print(X)\n"
        "for (N : 1..3):\n"
        "    Print(ToString(N))\n"
    )
    assert runner.output == "a\nb\n1\n2\n3"


def test_for_filter_clause(runner):
    runner.run("for (N : 0..5, N % 2 = 0):\n    Print(ToString(N))\n")
    assert runner.output == "0\n2\n4"


def test_arrays_index_and_concat(runner):
    runner.run(
        "A := array{1, 2} + array{3}\n"
        "Print(ToString(A[2]))\n"
        "Print(ToString(Length(A)))\n"
    )
    assert runner.output == "3\n3"


def test_array_index_out_of_range_raises(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("A := array{1}\nX := A[5]\n")


def test_map_get_returns_option(runner):
    runner.run(
        'M := map{"a" => 1}\n'
        'if (V := M["a"]):\n'
        "    Print(ToString(V))\n"
        'if (V := M["missing"]):\n'
        "    Print(\"found\")\n"
        "else:\n"
        "    Print(\"not found\")\n"
    )
    assert runner.output == "1\nnot found"


def test_decides_function_and_if_binding(runner):
    runner.run(
        "SafeDiv(A : int, B : int)<decides> : float =\n"
        "    if (B <> 0):\n"
        "        return A / B\n"
        "    else:\n"
        "        return false\n"
        "Main() : void =\n"
        "    if (R := SafeDiv(10, 2)):\n"
        "        Print(ToString(R))\n"
        "    if (R := SafeDiv(10, 0)):\n"
        "        Print(ToString(R))\n"
        "    else:\n"
        "        Print(\"fail\")\n"
        "Main()\n"
    )
    assert runner.output == "5.0\nfail"


def test_decides_expr_statement_false_propagates_failure(runner):
    runner.run(
        "FailMid()<decides> : int =\n"
        "    false\n"
        "    return 1\n"
        "if (V := FailMid()):\n"
        "    Print(ToString(V))\n"
        "else:\n"
        "    Print(\"failed\")\n"
    )
    assert runner.output == "failed"


def test_decides_expr_statement_absent_option_propagates_failure(runner):
    runner.run(
        "FailOnMissing()<decides> : int =\n"
        "    M := map{\"ok\" => 1}\n"
        "    M[\"missing\"]\n"
        "    return 1\n"
        "if (V := FailOnMissing()):\n"
        "    Print(ToString(V))\n"
        "else:\n"
        "    Print(\"failed\")\n"
    )
    assert runner.output == "failed"


def test_failable_unwrap_propagates(runner):
    with pytest.raises(VerseFailure):
        runner.run("Opt := option(1)\nX := false?\n")


def test_option_unwrap_success(runner):
    runner.run("Opt := option(42)\nPrint(ToString(Opt?))\n")
    assert runner.output == "42"


def test_class_fields_methods_inheritance(runner):
    runner.run(
        "shape := class:\n"
        "    Name : string = \"s\"\n"
        "    Area() : float =\n"
        "        return 0.0\n"
        "circle := class(shape):\n"
        "    Radius : float = 1.0\n"
        "    Area() : float =\n"
        "        return 3.0 * self.Radius * self.Radius\n"
        "C := circle{Radius := 2.0}\n"
        "Print(ToString(C.Area()))\n"
        "Print(C.Name)\n"
    )
    assert runner.output == "12.0\ns"


def test_closure_capture_and_call(runner):
    runner.run(
        "Add5 := 0\n"
        "MakeAdder(N : int) : function =\n"
        "    Inner(X : int) : int =\n"
        "        return X + N\n"
        "    return Inner\n"
        "Main() : void =\n"
        "    set Add5 = MakeAdder(5)\n"
        "    Print(ToString(Add5(10)))\n"
        "Main()\n"
    )
    assert runner.output == "15"


def test_sync_runs_concurrently_and_collects_results(runner):
    runner.run(
        "A() : int =\n"
        "    return 1\n"
        "B() : int =\n"
        "    return 2\n"
        "Main() : void =\n"
        "    R := sync:\n"
        "        A()\n"
        "        B()\n"
        "    Print(ToString(R))\n"
        "Main()\n"
    )
    assert runner.output == "array{1, 2}"


def test_race_returns_first_result(runner):
    runner.run(
        "Main() : void =\n"
        "    R := race:\n"
        "        1 + 1\n"
        "        2 + 2\n"
        "    Print(ToString(R))\n"
        "Main()\n"
    )
    assert runner.output == "2"


def test_spawn_runs_in_background(runner):
    runner.run(
        "Main() : void =\n"
        "    spawn:\n"
        "        Print(\"bg\")\n"
        "    Print(\"fg\")\n"
        "Main()\n"
    )
    assert runner.output == "fg\nbg"


def test_undefined_name_raises(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("Print(ToString(Undefined))\n")


def test_set_requires_existing_binding(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("set NeverDeclared = 1\n")


def test_if_body_binding_is_block_scoped(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("if (true):\n    X := 1\nPrint(ToString(X))\n")


def test_if_clause_binding_is_block_scoped(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("if (X := option(1)):\n    Print(ToString(X))\nPrint(ToString(X))\n")


def test_for_body_binding_is_block_scoped(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("for (N : 1..1):\n    X := N\nPrint(ToString(X))\n")


def test_loop_body_binding_is_block_scoped(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("loop:\n    X := 1\n    break\nPrint(ToString(X))\n")


def test_division_by_zero_raises(runner):
    with pytest.raises(VerseRuntimeError):
        runner.run("X := 1 / 0\n")
