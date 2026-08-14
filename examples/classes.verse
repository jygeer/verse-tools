# Classes: fields with defaults, methods, `self`, and single inheritance.

shape := class:
    Name : string = "shape"
    Area()<transacts> : float =
        return 0.0
    Describe()<transacts> : string =
        return self.Name + " has area " + ToString(self.Area())

circle := class(shape):
    Radius : float = 1.0
    Area() : float =
        return 3.14159 * self.Radius * self.Radius

rectangle := class(shape):
    Width : float = 1.0
    Height : float = 1.0
    Area() : float =
        return self.Width * self.Height

Main() : void =
    C := circle{Name := "circle", Radius := 2.0}
    R := rectangle{Name := "rectangle", Width := 3.0, Height := 4.0}
    Print(C.Describe())
    Print(R.Describe())
