"""A button, clicked -- what an event loop has to feed emtk.

Run it::

    python examples/emtk/clicking.py

There is no window here and no toolkit. A host gives emtk three things -- where
the pointer is, which buttons went down or up, and how much time passed -- and
gets back the drawing. That is the whole contract, and it is why the same
widgets run under Qt, under a browser and under a test.
"""
import emtk
from emtk.testing import RecordingPainter


def draw(io, storage) -> tuple[RecordingPainter, bool]:
    painter = RecordingPainter()
    clicked = False
    with emtk.frame(painter, (0.0, 0.0, 200.0, 80.0), io=io, storage=storage) as ctx:
        emtk.begin("demo", (0.0, 0.0, 200.0, 80.0))
        if emtk.button("Press me"):
            clicked = True
        box = ctx.get_item_rect()
        emtk.end()
    return painter, clicked, box


def main() -> None:
    io, storage = emtk.IO(), {}

    _painter, clicked, box = draw(io, storage)          # frame 1: lay it out
    print(f"button at {tuple(round(v) for v in box)}, clicked={clicked}")

    io.mouse_pos = (box[0] + 4, box[1] + 4)             # the pointer arrives
    io.mouse_down[0] = True
    io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    _painter, clicked, _box = draw(io, storage)
    print(f"pressed: clicked={clicked}   (Dear ImGui fires on release)")

    io.mouse_down[0] = False                            # ...and lets go
    io.mouse_released[0] = True
    _painter, clicked, _box = draw(io, storage)
    print(f"released: clicked={clicked}")
    assert clicked, "a button that never reports its click is not a button"


if __name__ == "__main__":
    main()
