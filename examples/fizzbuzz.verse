# The classic FizzBuzz, showing if/else-if chains and for-loops.

FizzBuzz(N : int) : string =
    if (N % 15 = 0):
        return "FizzBuzz"
    else if (N % 3 = 0):
        return "Fizz"
    else if (N % 5 = 0):
        return "Buzz"
    else:
        return ToString(N)

Main() : void =
    for (N : 1..20):
        Print(FizzBuzz(N))
