"""A disabled slider must not open the Ctrl+Click type-in."""
import emtk
from emtk import im


def test_a_disabled_slider_refuses_the_type_in():
    out: dict = {}

    def gui():
        im.begin_disabled(True)
        out["c"], out["v"] = emtk.slider_float("k", 0.25, 0.0, 1.0)
        im.end_disabled()

    io, storage = emtk.IO(), {}
    boxes: dict = {}

    def gui_box():
        im.begin_disabled(True)
        out["c"], out["v"] = emtk.slider_float("k", 0.25, 0.0, 1.0)
        boxes["r"] = emtk.get_item_rect()
        im.end_disabled()

    with emtk.frame(_Painter(), (0, 0, 400, 300), io=io, storage=storage):
        gui_box()
    r = boxes["r"]
    io.mouse_pos = (r[0] + 10, r[1] + 2)
    io.mouse_clicked[0] = True
    io.key_ctrl = True
    with emtk.frame(_Painter(), (0, 0, 400, 300), io=io, storage=storage):
        gui_box()
    with emtk.frame(_Painter(), (0, 0, 400, 300), io=io, storage=storage):
        gui_box()
    # still closed: no bare typed text, no change
    assert out["c"] is False and out["v"] == 0.25


class _Painter:
    def __init__(self):
        self.strings = []

    def fill_rect(self, *a):
        pass

    def stroke_rect(self, *a):
        pass

    def gradient_rect(self, *a):
        pass

    def fill_triangle(self, *a):
        pass

    def text(self, x, y, w, h, align, string, colour, bold=False):
        self.strings.append(string)

    def text_rotated(self, *a):
        pass

    def image(self, *a):
        pass

    def push_clip(self, *a):
        pass

    def pop_clip(self):
        pass

    def text_width(self, s):
        return len(s) * 7.0

    def line_height(self):
        return 12.0
