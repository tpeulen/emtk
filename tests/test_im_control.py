"""``im.host_control`` hosts a retained control as one item of an immediate-mode layout.

A retained control (a plot canvas, a table, an editor) draws into a box and is
handed the presses that land in it. Before this there were three hand-rolled
copies of the routing (``text_editor``, ``draw_table``, view_form's code editor),
each with its own idea of when a drag ends or keys arrive; a fourth caller -- a
dock window whose content is a plot -- had none to use.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter


class Classic:
    """The classic contract: press/drag/release/hover/scroll/key."""

    def __init__(self):
        self.calls = []
        self.box = None

    def draw(self, p, x, y, w, h):
        self.box = (x, y, w, h)
        self.calls.append(("draw",))

    def press(self, px, py, x, y, w, h, modifiers=0, clicks=1):
        self.calls.append(("press", px, py, clicks))

    def drag(self, px, py, *_):
        self.calls.append(("drag", px, py))

    def release(self, *_):
        self.calls.append(("release",))

    def hover(self, px, py, *_):
        self.calls.append(("hover", px, py))

    def scroll(self, rows, *_):
        self.calls.append(("scroll", rows))

    def key(self, key, text="", modifiers=0):
        self.calls.append(("key", key, text))
        return True

    def focus_lost(self):
        self.calls.append(("focus_lost",))


class Rich(Classic):
    """The rich contract: every button, and the wheel as notches."""

    def pointer_press(self, px, py, button, modifiers=0, clicks=1):
        self.calls.append(("pointer_press", button))

    def pointer_move(self, px, py, buttons, modifiers=0):
        self.calls.append(("pointer_move", buttons))

    def pointer_release(self, px, py, button, modifiers=0):
        self.calls.append(("pointer_release", button))

    def wheel(self, px, py, notches, modifiers=0):
        self.calls.append(("wheel", notches))


def _app(control, size=(200.0, 120.0), after=None):
    def gui():
        im.begin("W", (0, 0, 300, 300), flags=im.WindowFlags.NO_TITLE_BAR)
        im.host_control("##c", control, size)
        if after is not None:
            after()
        im.end()

    app = ImApp(gui)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    return app


def _frame(app):
    app.draw(RecordingPainter(), 0, 0, 300, 300)


def _names(control):
    return [c[0] for c in control.calls if c[0] != "draw"]


def test_it_draws_into_a_box_of_the_requested_size():
    control = Classic()
    _app(control)
    assert control.box is not None
    assert control.box[2:] == (200.0, 120.0)


def test_no_size_takes_the_space_left():
    control = Classic()
    _app(control, size=None)
    x, y, w, h = control.box
    assert w > 250 and h > 250


def test_a_press_inside_drags_and_releases_with_the_box():
    control = Classic()
    app = _app(control)
    x, y, w, h = control.box
    cx, cy = x + 20, y + 20
    app.pointer_press(cx, cy, 1)
    _frame(app)
    app.pointer_move(cx + 30, cy + 5, 1)
    _frame(app)
    # the drag continues outside the box: the press captured the pointer
    app.pointer_move(x + w + 40, cy, 1)
    _frame(app)
    app.pointer_release(x + w + 40, cy, 1)
    _frame(app)
    names = _names(control)
    assert names.index("press") < names.index("drag") < names.index("release")
    assert ("drag", x + w + 40, cy) in control.calls


def test_a_press_outside_never_reaches_it():
    control = Classic()
    app = _app(control)
    x, y, w, h = control.box
    app.pointer_press(x + w + 30, y + 10, 1)
    _frame(app)
    app.pointer_release(x + w + 30, y + 10, 1)
    _frame(app)
    assert "press" not in _names(control)
    assert "release" not in _names(control)


def test_a_double_click_arrives_as_two_clicks():
    control = Classic()
    app = _app(control)
    x, y, *_ = control.box
    app.pointer_press(x + 5, y + 5, 1, 0, 2)
    _frame(app)
    assert any(c[0] == "press" and c[3] == 2 for c in control.calls)


def test_hover_only_while_the_pointer_is_over_it():
    control = Classic()
    app = _app(control)
    x, y, w, h = control.box
    app.pointer_move(x + 10, y + 10, 0)
    _frame(app)
    assert ("hover", x + 10, y + 10) in control.calls


def test_the_wheel_scrolls_when_hovered():
    control = Classic()
    app = _app(control)
    x, y, *_ = control.box
    app.pointer_move(x + 10, y + 10, 0)
    _frame(app)
    app.wheel(x + 10, y + 10, 1.0)
    _frame(app)
    assert ("scroll", -3) in control.calls


def test_keys_go_to_the_focused_control_only():
    control = Classic()
    app = _app(control)
    x, y, *_ = control.box
    app.key(65, "a", 0)
    _frame(app)
    assert "key" not in _names(control), "keys reached a control nobody clicked"
    app.pointer_press(x + 5, y + 5, 1)
    _frame(app)
    app.pointer_release(x + 5, y + 5, 1)
    _frame(app)
    app.key(66, "b", 0)
    _frame(app)
    assert ("key", 66, "b") in control.calls


def test_a_click_elsewhere_takes_the_focus_away():
    control = Classic()
    app = _app(control)
    x, y, w, h = control.box
    app.pointer_press(x + 5, y + 5, 1)
    _frame(app)
    app.pointer_release(x + 5, y + 5, 1)
    _frame(app)
    app.pointer_press(x + w + 30, y + 5, 1)
    _frame(app)
    assert "focus_lost" in _names(control)
    app.key(67, "c", 0)
    _frame(app)
    assert ("key", 67, "c") not in control.calls


def test_a_rich_control_gets_every_button_and_the_wheel_in_notches():
    control = Rich()
    app = _app(control)
    x, y, *_ = control.box
    app.pointer_press(x + 5, y + 5, 2)
    _frame(app)
    app.pointer_release(x + 5, y + 5, 2)
    _frame(app)
    app.pointer_move(x + 6, y + 6, 0)
    _frame(app)
    app.wheel(x + 6, y + 6, 1.0)
    _frame(app)
    names = _names(control)
    assert ("pointer_press", 2) in control.calls
    assert ("pointer_release", 2) in control.calls
    assert ("wheel", 1.0) in control.calls
    assert "press" not in names and "scroll" not in names


def test_it_is_one_item_the_layout_flows_after():
    control = Classic()
    seen = {}

    def after():
        seen["y"] = im.get_cursor_screen_pos()[1]

    _app(control, after=after)
    x, y, w, h = control.box
    assert seen["y"] >= y + h


def test_it_reports_whether_it_took_input():
    control = Classic()
    taken = []

    def gui():
        im.begin("W", (0, 0, 300, 300), flags=im.WindowFlags.NO_TITLE_BAR)
        taken.append(im.host_control("##c", control, (200.0, 120.0)))
        im.end()

    app = ImApp(gui)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    assert taken[-1] is False
    x, y, *_ = control.box
    app.pointer_press(x + 5, y + 5, 1)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    assert taken[-1] is True
