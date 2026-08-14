# spawn/sync/race: cooperative concurrency over a single-threaded
# scheduler. See docs/architecture.md#concurrency-model for how
# interleaving actually works (it's per-bytecode-instruction, not
# per-line), and why `spawn` is fire-and-forget in this subset.

BrewCoffee() : string =
    Print("start brewing coffee")
    Print("done brewing coffee")
    return "coffee"

ToastBread() : string =
    Print("start toasting bread")
    Print("done toasting bread")
    return "toast"

Main() : void =
    # sync waits for every branch; Print calls from both branches
    # interleave because the scheduler steps one instruction at a time.
    Breakfast := sync:
        BrewCoffee()
        ToastBread()
    Print("breakfast is ready: " + ToString(Breakfast))

    # race returns as soon as the first branch finishes; the other is
    # cancelled (any output it already produced still happened, though).
    Winner := race:
        BrewCoffee()
        ToastBread()
    Print("first ready: " + Winner)

    # spawn starts a background task without waiting for it.
    spawn:
        Print("background task running")
    Print("main goes on immediately")
