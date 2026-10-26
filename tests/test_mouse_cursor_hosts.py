"""``emtk.app.mouse_cursor``: the pointer shape a frame asks for reaches every host."""
from __future__ import annotations

import emtk
from emtk.app import mouse_cursor
from emtk.flags import MouseCursor
from emtk.testing import RecordingPainter


class _App:
    def __init__(self, shape):
        self.mouse_cursor = shape


def test_shapes_become_css_names_and_an_app_without_one_gets_the_arrow():
    assert mouse_cursor(_App(MouseCursor.RESIZE_NWSE)) == "nwse-resize"
    assert mouse_cursor(_App(lambda: MouseCursor.RESIZE_EW)) == "ew-resize"
    assert mouse_cursor(object()) == "default"


def test_a_frame_starts_with_the_arrow_and_keeps_what_a_widget_asked_for():
    io = emtk.IO()
    with emtk.frame(RecordingPainter(), (0, 0, 100, 100), io=io):
        emtk.set_mouse_cursor(MouseCursor.RESIZE_NS)
    assert io.mouse_cursor == MouseCursor.RESIZE_NS
    with emtk.frame(RecordingPainter(), (0, 0, 100, 100), io=io):
        pass
    assert io.mouse_cursor == MouseCursor.ARROW


def test_the_native_host_sets_the_cursor_once_per_change_and_falls_back():
    from emtk.native import NativeHost

    shown = []

    class Canvas:
        def set_cursor(self, name):
            if name == "nwse-resize":            # GLFW < 3.4: no diagonal shapes
                raise ValueError(name)
            shown.append(name)

    host = NativeHost.__new__(NativeHost)
    host.app, host.canvas = _App(MouseCursor.RESIZE_EW), Canvas()
    host._recursor()
    host._recursor()
    host.app.mouse_cursor = MouseCursor.RESIZE_NWSE
    host._recursor()
    host.app.mouse_cursor = MouseCursor.ARROW
    host._recursor()
    assert shown == ["ew-resize", "crosshair", "default"]


def test_the_web_page_reports_the_cursor_for_the_canvas():
    from emtk.web.page import WebPage

    page = WebPage.__new__(WebPage)
    page.app = _App(MouseCursor.RESIZE_NESW)
    assert page.cursor() == "nesw-resize"
    page.app = object()
    assert page.cursor() == "default"
