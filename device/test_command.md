list
a r   -> reset A
c r   -> reset C
c1 r  -> reset C1

a c -> bottle.on_the_conveyor
a m -> bottle.on_the_conveyor_man
a d -> bottle.drop_one
c f1 left
c f1 right
c f2 left
c f3 right
c1 p -> pick position
c1 g -> go to printer
c1 o -> open left
c1 c -> close left
c1 or -> open right
c1 cr -> close right
ping a
ping c
ping c1
q

make f3 right
