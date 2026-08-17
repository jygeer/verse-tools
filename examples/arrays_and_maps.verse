# Arrays and maps: literals, indexing, concatenation, and helpers.
# Also demonstrates value (copy-on-assign) semantics: mutating one
# variable's array/map does not affect other variables that held the
# same value before the mutation.

Main() : void =
    Fruits := array{"apple", "banana", "cherry"}
    Print("There are " + ToString(Length(Fruits)) + " fruits")
    for (Fruit : Fruits):
        Print(Fruit)

    MoreFruits := Fruits + array{"date"}
    Print("First fruit: " + MoreFruits[0])
    Print("Contains banana: " + ToString(Contains(MoreFruits, "banana")))

    Ages := map{"Alice" => 30, "Bob" => 25}
    if (AliceAge := Ages["Alice"]):
        Print("Alice is " + ToString(AliceAge))
    if (Carol := Ages["Carol"]):
        Print("Carol is " + ToString(Carol))
    else:
        Print("Carol is not in the map")

    for (Name : Keys(Ages)):
        Print("Known: " + Name)

    # Value semantics: assigning an array/map to another variable gives
    # an independent copy - mutations do not alias.
    var Original : []int = array{1, 2, 3}
    var Copy : []int = Original
    set Copy[0] = 99
    Print("Original[0] = " + ToString(Original[0]))  # still 1
    Print("Copy[0] = " + ToString(Copy[0]))           # 99

    var Base : [string]int = map{"x" => 10}
    var Fork : [string]int = Base
    set Fork["x"] = 42
    if (V := Base["x"]):
        Print("Base[x] = " + ToString(V))    # still 10
    if (V := Fork["x"]):
        Print("Fork[x] = " + ToString(V))    # 42
