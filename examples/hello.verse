# A first look at Verse-core: functions, string concatenation, and Print.

Greet(Name : string) : string =
    return "Hello, " + Name + "!"

Main() : void =
    Print(Greet("Verse"))
    Print(Greet("World"))
