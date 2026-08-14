# Arrays and maps: literals, indexing, concatenation, and helpers.

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
