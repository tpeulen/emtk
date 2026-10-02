"""A scrolling child with nothing to scroll must not swallow the wheel.

A dock window wraps its content in a scrollable child. The child zeroed ``io.mouse_wheel`` even
when its content fitted, so a node editor, plot or spin field inside never saw the wheel (the
lightpath node editor could not zoom). Only a child that can actually scroll takes the wheel.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter


def _run(rows):
    seen = {"wheel": 0.0, "scroll": None}

    def gui():
        im.begin("W", (0, 0, 300, 300))
        im.begin_child("c", (280, 200))
        for i in range(rows):
            im.text(f"row {i}")
        seen["wheel"] = im.get_io().mouse_wheel if hasattr(im, "get_io") else seen["wheel"]
        im.end_child()
        im.end()

    app = ImApp(gui)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 300, 300)
    app.hover(50, 50)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    app.wheel(50, 50, 1.0)
    return app, seen


def test_a_child_that_fits_leaves_the_wheel_to_its_content():
    app, seen = _run(rows=3)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    assert seen["wheel"] != 0.0, "a non-scrolling child swallowed the wheel"


def test_a_child_that_overflows_still_takes_the_wheel():
    app, seen = _run(rows=60)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    assert seen["wheel"] == 0.0
