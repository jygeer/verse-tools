# Verse models "this might not produce a value" with options and a
# decides-effect failure model instead of exceptions. A `<decides>`
# function signals failure by returning `false`; callers test for it
# with `if (Name := F()):` or unwrap-or-fail with the `?` operator.
# See docs/language-reference.md#failure-and-options and
# docs/differences-from-verse.md for exactly how this subset's failure
# model differs from real Verse.

SafeDivide(A : int, B : int)<decides> : float =
    if (B <> 0):
        return A / B
    else:
        return false

FindFirstEven(Numbers : []int)<decides> : int =
    for (N : Numbers, N % 2 = 0):
        return N
    return false

Main() : void =
    if (Result := SafeDivide(10, 2)):
        Print("10 / 2 = " + ToString(Result))
    else:
        Print("cannot divide")

    if (Result := SafeDivide(10, 0)):
        Print("10 / 0 = " + ToString(Result))
    else:
        Print("cannot divide by zero")

    Numbers := array{1, 3, 5, 8, 9}
    if (Even := FindFirstEven(Numbers)):
        Print("first even number: " + ToString(Even))
    else:
        Print("no even number found")

    # `option(X)` builds a present option; `Opt?` unwraps it or fails.
    MaybeName : ?string = option("Nyx")
    if (Name := MaybeName?):
        Print("name is " + Name)
