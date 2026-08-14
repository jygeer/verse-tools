# Block scoping: variables declared with := inside if/for/loop bodies
# are block-local and visible within that block.

CountPositives(Values : []int) : int =
    var Total : int = 0
    for (V : Values):
        if (V > 0):
            var Contribution : int = V * 2  # block-local; not visible outside this if body
            set Total = Total + Contribution
    return Total

Main() : void =
    # Variable declared inside a for loop body is block-local.
    for (I : 1..3):
        var Squared : int = I * I
        Print(ToString(I) + " squared = " + ToString(Squared))

    # Variable declared inside a loop body is block-local.
    var Count : int = 0
    loop:
        set Count = Count + 1
        var Msg : string = "iteration " + ToString(Count)
        Print(Msg)
        if (Count >= 3):
            break

    # Variables in nested ifs are scoped to their block.
    X : int = 7
    if (X > 0):
        var Label : string = "positive"
        if (X > 5):
            var Detail : string = "large positive"
            Print(Detail)
        Print(Label)

    Result : int = CountPositives(array{-3, 1, -1, 4, 2})
    Print("doubled positives sum = " + ToString(Result))
