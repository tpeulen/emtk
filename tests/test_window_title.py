"""``emtk.app.window_title``: an app retitles its window on every host."""
from __future__ import annotations

from emtk.app import window_title


class _App:
    def __init__(self, title):
        self.window_title = title


def test_an_app_names_its_title_by_attribute_or_callable():
    assert window_title(_App("ndX")) == "ndX"
    assert window_title(_App(lambda: "ndX -- a.bur")) == "ndX -- a.bur"
    assert window_title(object()) is None


def test_the_native_host_retitles_its_canvas_once_per_change():
    from emtk.native import NativeHost

    titles = []

    class Canvas:
        def set_title(self, title):
            titles.append(title)

    host = NativeHost.__new__(NativeHost)
    host.app, host.canvas = _App("ndX"), Canvas()
    host._retitle()
    host._retitle()
    host.app.window_title = "ndX -- b.bur"
    host._retitle()
    assert titles == ["ndX", "ndX -- b.bur"]


def test_the_web_page_reports_the_title_for_the_document():
    from emtk.web.page import WebPage

    page = WebPage.__new__(WebPage)
    page.app = _App("ndX -- c.bur")
    assert page.title() == "ndX -- c.bur"
    page.app = object()
    assert page.title() == ""
