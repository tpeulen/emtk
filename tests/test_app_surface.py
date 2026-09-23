"""The app contract the GPU hosts drive: controls lifted to surfaces, ImApp.

:class:`emtk.app.ControlSurface` must hand a control exactly what the classic
hosts (:mod:`emtk.qt_host`, :mod:`emtk.tk_host`) hand it, so a control moves
between a Tk window, a desktop GPU window and a browser tab unchanged.
"""
from __future__ import annotations

import sys
import types

import pytest

from emtk.app import ControlSurface, ImApp, Surface, as_surface, load_app
from emtk.events import LEFT_BUTTON, RIGHT_BUTTON, SHIFT_MODIFIER
from emtk.testing import PixelPainter


class _Control:
    def __init__(self):
        self.calls = []

    def draw(self, painter, x, y, w, h):
        self.calls.append(("draw", (x, y, w, h)))

    def press(self, px, py, x, y, w, h, modifiers=0, clicks=1):
        self.calls.append(("press", (px, py, x, y, w, h, modifiers, clicks)))

    def drag(self, px, py, x, y, w, h):
        self.calls.append(("drag", (px, py)))

    def hover(self, px, py, x, y, w, h):
        self.calls.append(("hover", (px, py)))

    def release(self):
        self.calls.append(("release", ()))

    def scroll(self, rows):
        self.calls.append(("scroll", (rows,)))
        return 0

    def key(self, key, text="", modifiers=0):
        self.calls.append(("key", (key, text, modifiers)))
        return text == "q"


@pytest.fixture
def lifted():
    control = _Control()
    surface = ControlSurface(control)
    surface.on_resize(800, 600, 2.0)
    return control, surface


def test_the_box_is_the_whole_surface_in_logical_pixels(lifted):
    control, surface = lifted
    surface.on_pointer_press(10, 20, LEFT_BUTTON, SHIFT_MODIFIER, double=True)
    assert control.calls == [("press", (10.0, 20.0, 0.0, 0.0, 400.0, 300.0, SHIFT_MODIFIER, 2))]


def test_a_move_is_a_drag_only_while_the_left_button_is_held(lifted):
    control, surface = lifted
    surface.on_pointer_move(1, 1, 0, 0)
    surface.on_pointer_press(1, 1, LEFT_BUTTON, 0)
    surface.on_pointer_move(2, 2, LEFT_BUTTON, 0)
    surface.on_pointer_release(2, 2, LEFT_BUTTON, 0)
    surface.on_pointer_move(3, 3, 0, 0)
    assert [c[0] for c in control.calls] == ["hover", "press", "drag", "release", "hover"]


def test_other_buttons_do_not_reach_a_classic_control(lifted):
    """The classic contract has no button argument; a right press is not a click."""
    control, surface = lifted
    assert surface.on_pointer_press(1, 1, RIGHT_BUTTON, 0) is False
    assert control.calls == []


def test_a_wheel_notch_scrolls_three_rows_the_qt_way(lifted):
    control, surface = lifted
    surface.on_wheel(0, 0, 1, 0)      # away from the user
    surface.on_wheel(0, 0, -2, 0)
    assert control.calls == [("scroll", (-3,)), ("scroll", (6,))]


def test_key_consumption_is_the_control_s_answer(lifted):
    control, surface = lifted
    assert surface.on_key_press(0, "q", 0) is True
    assert surface.on_key_press(0, "w", 0) is False


def test_rich_hooks_win_when_a_control_has_them():
    seen = []

    class _Rich(_Control):
        def pointer_press(self, x, y, button, modifiers, clicks):
            seen.append(("pp", button, clicks))

        def wheel(self, x, y, steps, modifiers):
            seen.append(("wheel", x, y, steps))

        def files_dropped(self, paths):
            seen.append(("drop", paths))

        def animating(self):
            return True

    surface = ControlSurface(_Rich())
    surface.on_pointer_press(1, 2, RIGHT_BUTTON, 0)
    surface.on_wheel(5, 6, 2, 0)
    surface.on_files_dropped(["/mnt/dropped/a.txt"])
    assert seen == [("pp", RIGHT_BUTTON, 1), ("wheel", 5.0, 6.0, 2),
                    ("drop", ["/mnt/dropped/a.txt"])]
    assert surface.animating() is True


def test_as_surface_and_load_app(monkeypatch):
    class _S(Surface):
        def render(self, view):
            pass

    s = _S()
    assert as_surface(s) is s
    assert isinstance(as_surface(_Control()), ControlSurface)
    with pytest.raises(TypeError):
        as_surface(object())

    module = types.ModuleType("_emtk_test_app")
    module.factories = types.SimpleNamespace(make=_Control)
    monkeypatch.setitem(sys.modules, "_emtk_test_app", module)
    assert isinstance(load_app("_emtk_test_app:factories.make"), _Control)
    with pytest.raises(ValueError):
        load_app("_emtk_test_app")


# ------------------------------------------------------------------ ImApp
def _frame(app, w=320, h=200):
    painter = PixelPainter(w, h)
    app.draw(painter, 0.0, 0.0, float(w), float(h))
    return painter


def test_imapp_runs_the_gui_and_feeds_it_a_click():
    import emtk

    clicks = []

    def gui():
        emtk.begin("w", (0.0, 0.0, 300.0, 180.0))
        if emtk.button("Press me"):
            clicks.append(1)
        emtk.end()

    app = ImApp(gui)
    _frame(app)                        # lays the button out
    # Find it: the first button sits at the window's top-left content area.
    for y in range(4, 60, 4):
        app.pointer_move(30, y)
        app.pointer_press(30, y, LEFT_BUTTON)
        app.pointer_release(30, y, LEFT_BUTTON)
        _frame(app)
        if clicks:
            break
    assert clicks, "a press and release between two frames never clicked the button"
    assert app.animating() is False, "an idle gui asked for continuous frames"
    assert ImApp(gui, continuous=True).animating() is True


def test_imapp_is_also_a_classic_control():
    """So a ``gui()`` runs under TkHost and the Qt hosts as well."""
    app = ImApp(lambda: None)
    app.press(5, 6, 0, 0, 10, 10, 0, 2)
    assert app.io.mouse_down[0] and app.io.mouse_double_clicked[0]
    app.release()
    assert not app.io.mouse_down[0] and app.io.mouse_released[0]
    app.scroll(-3)
    assert app.io.mouse_wheel == 1.0
    app.key(0, "a", SHIFT_MODIFIER)
    assert app.io.text == "a" and app.io.key_shift


def test_the_implot_demo_is_an_app():
    from emtk.implot_demo import make_app

    app = make_app()
    painter = _frame(app, 640, 480)
    assert app.animating() is True
    assert any(px for px in painter.px[:4000]), "the demo drew nothing"
