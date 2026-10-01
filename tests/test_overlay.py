"""OverlaySurface: an ImApp over another surface, events by capture."""
from __future__ import annotations

from emtk import im
from emtk.app import ImApp, Surface
from emtk.events import LEFT_BUTTON
from emtk.overlay import OverlaySurface


class _Base(Surface):
    def __init__(self):
        self.events = []

    def on_pointer_press(self, x, y, button, modifiers, double=False):
        self.events.append(("press", x, y))
        return True

    def on_pointer_move(self, x, y, buttons, modifiers):
        self.events.append(("move", x, y))
        return True

    def on_pointer_release(self, x, y, button, modifiers):
        self.events.append(("release", x, y))
        return True

    def on_wheel(self, x, y, steps, modifiers):
        self.events.append(("wheel", x, y))
        return True

    def on_key_press(self, key, text, modifiers):
        self.events.append(("key", text))
        return True


def _surface(capture_mouse=False, capture_keys=False):
    app = ImApp(lambda: None)
    app.io.want_capture_mouse = capture_mouse
    app.io.want_capture_keyboard = capture_keys
    base = _Base()
    return OverlaySurface(base, app), base, app


def test_pointer_goes_to_the_base_when_the_app_does_not_want_it():
    s, base, _ = _surface()
    s.on_pointer_press(500, 300, LEFT_BUTTON, 0)
    s.on_pointer_move(510, 300, LEFT_BUTTON, 0)
    s.on_pointer_release(510, 300, LEFT_BUTTON, 0)
    s.on_wheel(510, 300, 1, 0)
    assert [e[0] for e in base.events] == ["press", "move", "release", "wheel"]


def test_pointer_goes_to_the_app_over_its_windows():
    s, base, _ = _surface(capture_mouse=True)
    s.on_pointer_press(50, 50, LEFT_BUTTON, 0)
    s.on_wheel(50, 50, 1, 0)
    assert base.events == []


def test_a_drag_stays_with_whoever_got_the_press():
    s, base, app = _surface(capture_mouse=False)
    s.on_pointer_press(500, 300, LEFT_BUTTON, 0)
    app.io.want_capture_mouse = True  # the drag crosses into a window
    s.on_pointer_move(50, 50, LEFT_BUTTON, 0)
    s.on_pointer_release(50, 50, LEFT_BUTTON, 0)
    assert [e[0] for e in base.events] == ["press", "move", "release"]


def test_keys_go_to_the_app_only_while_it_holds_the_keyboard():
    s, base, app = _surface()
    s.on_key_press(0, "a", 0)
    app.io.want_text_input = True
    s.on_key_press(0, "b", 0)
    assert base.events == [("key", "a")]


def test_typing_reaches_a_focused_input_text():
    """End to end through the real app: click the field, type, read it back."""
    state = {"text": "", "rect": None}

    def gui():
        im.begin("form", (0.0, 0.0, 300.0, 200.0))
        _, state["text"] = im.input_text("pdb", state["text"])
        state["rect"] = im.get_item_rect_min() + im.get_item_rect_max()
        im.end()

    app = ImApp(gui)
    base = _Base()
    s = OverlaySurface(base, app)

    from emtk.quad_painter import QuadPainter

    def frame():
        app.draw(QuadPainter(), 0.0, 0.0, 800.0, 600.0)

    frame()
    x0, y0, x1, y1 = state["rect"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    s.on_pointer_move(cx, cy, 0, 0)  # hover: the app now claims the pointer
    frame()
    s.on_pointer_press(cx, cy, LEFT_BUTTON, 0)
    frame()
    s.on_pointer_release(cx, cy, LEFT_BUTTON, 0)
    frame()
    for ch in "1omp":
        s.on_key_press(0, ch, 0)
        frame()
    assert state["text"] == "1omp", (state, base.events)
    assert not any(e[0] == "key" for e in base.events)
