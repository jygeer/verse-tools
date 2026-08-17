# effect_decides.verse - demonstrates the <decides> effect and guarded calls.
#
# Functions annotated <decides> may fail at runtime.  The type checker
# (verse run --strict / verse check) enforces that:
#   - a <decides> call must be guarded inside an if/for clause, OR
#   - the calling function must itself be declared <decides>.
#   - the ? failable-unwrap operator follows the same rule.

# A <decides> function: returns the value or fails explicitly.
SafeDiv(A : int, B : int)<decides> : int =
    if (B <> 0):
        return A / B
    else:
        return false

# Guarded call in an if clause - fine even in a non-decides caller.
Main() : void =
    if (Result := SafeDiv(10, 2)):
        Print(ToString(Result))
    else:
        Print("division failed")

    # Chaining: if the divisor is 0 the else branch runs.
    if (V := SafeDiv(7, 0)):
        Print(ToString(V))
    else:
        Print("caught failure")

    # Failable unwrap ? inside an if clause is also guarded.
    Opt := option(99)
    if (X := Opt?):
        Print(ToString(X))
