"""A click lands after the window was resized -- on a real glfw window.

rendercanvas' glfw backend drops every pointer *move* while it believes the
pointer is outside the window, and swallows a *press* there as "the click
that focuses the window". What it believes comes only from glfw's cursor
enter/leave callbacks. On macOS those come from an ``NSTrackingArea`` that
glfw recreates on every resize with ``NSTrackingAssumeInside``: a pointer
that is outside the content view while the area is recreated -- on the
window edge it is dragging, or anywhere else while a tiling tool resizes the
window -- produces **no** enter event when it then moves in. Every click
after that was swallowed and every hover dropped, until the pointer happened
to leave the window and come back.

The test drives the callbacks glfw itself would call (whatever is installed
on the window, so chaining is exercised) and stands in for the two OS
queries a hidden window cannot answer truthfully: whether the pointer is
over the window, and where it is.
"""
from __future__ import annotations

import pytest

from emtk.events import LEFT_BUTTON
from emtk.native import CanvasEvents


class _Sink:
    def __init__(self):
        self.calls: list = []

    def __getattr__(self, name):
        if not name.startswith("on_"):
            raise AttributeError(name)

        def handler(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return False

        return handler

    def named(self, name):
        return [args for n, args, _ in self.calls if n == name]


@pytest.fixture
def glfw_canvas():
    glfw = pytest.importorskip("glfw")
    rc_glfw = pytest.importorskip("rendercanvas.glfw")
    try:
        canvas = rc_glfw.RenderCanvas(size=(400, 300), title="resize-clicks")
    except Exception as exc:  # noqa: BLE001 - no display, no window
        pytest.skip(f"no glfw window here: {exc}")
    glfw.hide_window(canvas._window)
    yield glfw, canvas
    canvas.close()


def _installed(glfw, setter, window):
    """The callback glfw would call now (read without changing it)."""
    current = setter(window, None)
    setter(window, current)
    return current


def _pump(glfw, canvas):
    for _ in range(3):
        glfw.poll_events()
    canvas._process_events()


def test_a_click_after_a_resize_lands_although_glfw_sent_no_enter(glfw_canvas, monkeypatch):
    glfw, canvas = glfw_canvas
    window = canvas._window
    sink = _Sink()
    events = CanvasEvents(canvas, sink)
    try:
        enter = _installed(glfw, glfw.set_cursor_enter_callback, window)
        button = _installed(glfw, glfw.set_mouse_button_callback, window)
        cursor = _installed(glfw, glfw.set_cursor_pos_callback, window)

        # The pointer was in the window, then left it to grab the edge.
        enter(window, 1)
        enter(window, 0)
        glfw.set_window_size(window, 640, 480)
        _pump(glfw, canvas)
        assert canvas.get_logical_size() == (640.0, 480.0)
        resized = sink.named("on_resize")
        assert resized and resized[-1][0] / resized[-1][2] == 640

        # Back inside, at a control that only exists at the new size --
        # and no enter event, as on macOS after the tracking area was rebuilt.
        hovered = {"value": 1}
        real_attrib = glfw.get_window_attrib
        monkeypatch.setattr(glfw, "get_window_attrib", lambda w, a: (
            hovered["value"] if a == glfw.HOVERED else real_attrib(w, a)))
        monkeypatch.setattr(glfw, "get_cursor_pos", lambda w: (600.0, 450.0))
        sink.calls.clear()

        cursor(window, 600.0, 450.0)
        button(window, glfw.MOUSE_BUTTON_LEFT, glfw.PRESS, 0)
        button(window, glfw.MOUSE_BUTTON_LEFT, glfw.RELEASE, 0)
        _pump(glfw, canvas)

        assert sink.named("on_pointer_move")[-1][:2] == (600.0, 450.0)
        assert [a[:3] for a in sink.named("on_pointer_press")] == [(600.0, 450.0, LEFT_BUTTON)]
        assert [a[:3] for a in sink.named("on_pointer_release")] == [(600.0, 450.0, LEFT_BUTTON)]
    finally:
        events._on_close({"event_type": "close"})


def test_a_press_while_the_pointer_really_is_outside_still_only_focuses(glfw_canvas, monkeypatch):
    """rendercanvas' focus-click rule is kept for the case it was written for."""
    glfw, canvas = glfw_canvas
    window = canvas._window
    sink = _Sink()
    events = CanvasEvents(canvas, sink)
    try:
        enter = _installed(glfw, glfw.set_cursor_enter_callback, window)
        button = _installed(glfw, glfw.set_mouse_button_callback, window)
        enter(window, 0)
        real_attrib = glfw.get_window_attrib
        monkeypatch.setattr(glfw, "get_window_attrib", lambda w, a: (
            0 if a == glfw.HOVERED else real_attrib(w, a)))
        sink.calls.clear()
        button(window, glfw.MOUSE_BUTTON_LEFT, glfw.PRESS, 0)
        button(window, glfw.MOUSE_BUTTON_LEFT, glfw.RELEASE, 0)
        _pump(glfw, canvas)
        assert sink.named("on_pointer_press") == []
    finally:
        events._on_close({"event_type": "close"})


def test_the_pointer_callbacks_are_restored_on_close(glfw_canvas):
    glfw, canvas = glfw_canvas
    window = canvas._window
    before_button = _installed(glfw, glfw.set_mouse_button_callback, window)
    before_cursor = _installed(glfw, glfw.set_cursor_pos_callback, window)
    events = CanvasEvents(canvas, _Sink())
    events._on_close({"event_type": "close"})
    assert _installed(glfw, glfw.set_mouse_button_callback, window) is before_button
    assert _installed(glfw, glfw.set_cursor_pos_callback, window) is before_cursor
