import pytest

from versetools.errors import VerseCompileError
from versetools.lexer import tokenize
from versetools.parser import parse
from versetools.type_checker import check_program


def check_src(src: str) -> None:
    check_program(parse(tokenize(src)))


def test_type_checker_rejects_mixed_addition():
    with pytest.raises(VerseCompileError, match="cannot add int and string"):
        check_src('Main() : void =\n    X := 1 + "x"\n')


def test_type_checker_rejects_bad_function_argument_type():
    with pytest.raises(VerseCompileError, match="argument 1"):
        check_src('AddOne(X : int) : int =\n    return X + 1\nPrint(ToString(AddOne("x")))\n')


def test_type_checker_rejects_assignment_type_mismatch():
    with pytest.raises(VerseCompileError, match="cannot assign string to int"):
        check_src('var Count : int = 0\nset Count = "x"\n')


def test_type_checker_allows_typed_map_assignment():
    check_src('var Ages : [string]int = map{"alice" => 1}\nset Ages["bob"] = 2\n')


def test_type_checker_supports_task_annotation():
    check_src('UseTask(T : task) : logic =\n    return T.Done\n')


def test_type_checker_supports_range_annotation():
    check_src("First(R : range) : int =\n    for (N : R):\n        return N\n    return 0\n")


def test_type_checker_allows_nested_function_definitions():
    check_src(
        "MakeAdder(N : int) : function =\n"
        "    Inner(X : int) : int =\n"
        "        return X + N\n"
        "    return Inner\n"
    )


def test_type_checker_allows_omitted_default_arguments():
    check_src(
        'Greet(Name : string, Greeting : string = "Hello") : string =\n'
        '    return Greeting + ", " + Name\n'
        'Print(Greet("Ada"))\n'
    )


def test_type_checker_allows_dependent_if_clause_bindings():
    check_src(
        "if (X := option(1), X = 1):\n"
        '    Print("ok")\n'
    )


def test_type_checker_rejects_return_type_mismatch():
    with pytest.raises(VerseCompileError, match="cannot return string from int function"):
        check_src('Describe() : int =\n    return "x"\n')


def test_type_checker_allows_decides_false_return():
    check_src(
        "SafeDivide(A : int, B : int)<decides> : float =\n"
        "    if (B <> 0):\n"
        "        return A / B\n"
        "    else:\n"
        "        return false\n"
    )


# ---------------------------------------------------------------- effect system tests

def test_effect_decides_call_inside_if_clause_is_ok():
    """Calling a <decides> function inside an if clause is valid (guarded)."""
    check_src(
        "MayFail()<decides> : int =\n"
        "    return 1\n"
        "Main() : void =\n"
        "    if (X := MayFail()):\n"
        "        Print(ToString(X))\n"
    )


def test_effect_decides_call_in_decides_function_is_ok():
    """Calling a <decides> function from a <decides> function propagates failure."""
    check_src(
        "MayFail()<decides> : int =\n"
        "    return 1\n"
        "AlsoFails()<decides> : int =\n"
        "    return MayFail()\n"
    )


def test_effect_unguarded_decides_call_outside_decides_is_error():
    """Calling a <decides> function in a non-decides function body is a compile error."""
    with pytest.raises(VerseCompileError, match="<decides>"):
        check_src(
            "MayFail()<decides> : int =\n"
            "    return 1\n"
            "Main() : void =\n"
            "    X := MayFail()\n"
        )


def test_effect_decides_call_in_for_filter_is_ok():
    """Calling a <decides> function in a for-filter is valid (guarded)."""
    check_src(
        "IsEven(N : int)<decides> : int =\n"
        "    if (N % 2 = 0):\n"
        "        return N\n"
        "    else:\n"
        "        return false\n"
        "Main() : void =\n"
        "    for (N : 1..5, IsEven(N)):\n"
        "        Print(ToString(N))\n"
    )


def test_effect_failable_unwrap_outside_decides_is_error():
    """Using ? outside a <decides> function is a compile error."""
    with pytest.raises(VerseCompileError, match="failable unwrap"):
        check_src(
            "Main() : void =\n"
            "    V := option(42)\n"
            "    X := V?\n"
        )


def test_effect_failable_unwrap_inside_decides_is_ok():
    """Using ? inside a <decides> function is valid."""
    check_src(
        "Unwrap(V : ?int)<decides> : int =\n"
        "    return V?\n"
    )


def test_effect_failable_unwrap_in_if_clause_is_ok():
    """Using ? inside an if clause is valid (guarded)."""
    check_src(
        "TryUnwrap(V : ?int) : void =\n"
        "    if (X := V?):\n"
        "        Print(ToString(X))\n"
    )


def test_effect_nested_decides_function_propagates():
    """A nested <decides> function can be called unguarded from an outer <decides> function."""
    check_src(
        "Outer()<decides> : int =\n"
        "    Inner()<decides> : int =\n"
        "        return 1\n"
        "    return Inner()\n"
    )


def test_effect_nested_decides_call_without_decides_is_error():
    """A nested <decides> function called without <decides> context is an error."""
    with pytest.raises(VerseCompileError, match="<decides>"):
        check_src(
            "Outer() : int =\n"
            "    Inner()<decides> : int =\n"
            "        return 1\n"
            "    return Inner()\n"
        )


def test_effect_decides_call_in_if_expr_is_ok():
    """Calling a <decides> function inside an inline if-expression clause is valid (guarded)."""
    check_src(
        "MayFail()<decides> : int =\n"
        "    return 1\n"
        "Main() : void =\n"
        "    V := if (X := MayFail()) then X else 0\n"
    )


def test_effect_failable_unwrap_in_for_filter_is_ok():
    """Using ? inside a for-filter clause is valid (guarded)."""
    check_src(
        "Main() : void =\n"
        "    Items := array{option(1), option(2), option(3)}\n"
        "    for (V : Items, V?):\n"
        "        Print(\"ok\")\n"
    )


def test_effect_multiple_decides_calls_in_same_if_clause_is_ok():
    """Multiple <decides> calls inside the same if clause are all valid (guarded)."""
    check_src(
        "A()<decides> : int =\n"
        "    return 1\n"
        "B()<decides> : int =\n"
        "    return 2\n"
        "Main() : void =\n"
        "    if (X := A(), Y := B()):\n"
        "        Print(ToString(X + Y))\n"
    )


def test_effect_decides_function_calling_plain_function_is_ok():
    """A <decides> function can freely call ordinary (non-<decides>) functions."""
    check_src(
        "Helper() : int =\n"
        "    return 42\n"
        "Wrapper()<decides> : int =\n"
        "    return Helper()\n"
    )


def test_effect_failable_unwrap_outside_function_is_error():
    """Using ? at top-level (outside any function) is a compile error."""
    with pytest.raises(VerseCompileError, match="failable unwrap"):
        check_src(
            "V := option(1)\n"
            "X := V?\n"
        )


def test_type_checker_rejects_private_member_access_outside_declaring_class():
    with pytest.raises(VerseCompileError, match="private"):
        check_src(
            "SecretBox := class:\n"
            "    Value<private> : int = 1\n"
            "Read(B : SecretBox) : int =\n"
            "    return B.Value\n"
        )


def test_type_checker_allows_protected_member_access_in_subclass():
    check_src(
        "Base := class:\n"
        "    Value<protected> : int = 1\n"
        "Child := class(Base):\n"
        "    Read() : int =\n"
        "        return self.Value\n"
    )


def test_type_checker_rejects_protected_member_access_outside_subclass():
    with pytest.raises(VerseCompileError, match="protected"):
        check_src(
            "Base := class:\n"
            "    Value<protected> : int = 1\n"
            "Read(B : Base) : int =\n"
            "    return B.Value\n"
        )


def test_type_checker_rejects_concrete_subclass_missing_abstract_override():
    with pytest.raises(VerseCompileError, match="abstract method"):
        check_src(
            "Shape := class<abstract>:\n"
            "    Area<abstract>() : int =\n"
            "Square := class(Shape):\n"
            "    Side : int = 1\n"
        )


def test_type_checker_allows_concrete_subclass_overriding_abstract_method():
    check_src(
        "Shape := class<abstract>:\n"
        "    Area<abstract>() : int =\n"
        "Square := class(Shape):\n"
        "    Side : int = 2\n"
        "    Area() : int =\n"
        "        return self.Side * self.Side\n"
    )


def test_type_checker_rejects_missing_interface_method():
    with pytest.raises(VerseCompileError, match="interface"):
        check_src(
            "Renderable := class<abstract>:\n"
            "    Render<abstract>() : void =\n"
            "Sprite := class : Renderable:\n"
            "    Name : string = \"s\"\n"
        )


def test_type_checker_allows_interface_implementation_with_matching_method():
    check_src(
        "Renderable := class<abstract>:\n"
        "    Render<abstract>() : void =\n"
        "Sprite := class : Renderable:\n"
        "    Render() : void =\n"
        "        Print(\"ok\")\n"
    )
