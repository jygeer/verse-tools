# if/else, loop/break/continue, and for with a filter clause.

ClassifyNumber(N : int) : string =
    if (N < 0):
        return "negative"
    else if (N = 0):
        return "zero"
    else:
        return "positive"

Main() : void =
    for (N : array{-2, -1, 0, 1, 2}):
        Print(ClassifyNumber(N))

    # `loop` is an unconditional loop; you exit it with `break`.
    var Count : int = 0
    loop:
        set Count = Count + 1
        if (Count = 3):
            continue
        if (Count > 5):
            break
        Print("Count is " + ToString(Count))

    # A for-loop filter clause skips elements that don't match.
    for (N : 0..9, N % 2 = 0):
        Print("Even: " + ToString(N))
