# Type annotations: Verse-core supports explicit type annotations on
# variables, parameters, and return types.  Run `verse check <file>` or
# `verse run --strict <file>` to catch type mismatches at compile time.

# Function with annotated parameters and return type.
Add(A : int, B : int) : int =
    return A + B

# String concatenation helper.
Greet(Name : string) : string =
    return "Hello, " + Name

# Annotated variable binding (immutable).
Clamp(Value : int, Lo : int, Hi : int) : int =
    if (Value < Lo):
        return Lo
    if (Value > Hi):
        return Hi
    return Value

Main() : void =
    # Explicit type annotations on immutable bindings; the compiler
    # rejects a non-int RHS for Sum or a non-string RHS for Greeting.
    Sum : int = Add(10, 32)
    Greeting : string = Greet("Verse")
    Print(Greeting)
    Print("10 + 32 = " + ToString(Sum))

    # Annotated mutable variable.
    var Counter : int = 0
    for (I : 1..5):
        set Counter = Counter + I
    Print("1+2+3+4+5 = " + ToString(Counter))

    # Type annotations work with option types.
    MaybeName : ?string = option("Verse-core")
    if (Name := MaybeName?):
        Len : int = Length(Name)
        Print("name length = " + ToString(Len))
