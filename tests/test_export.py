"""``emtk.export``: an app's window as a PNG, headless."""

from __future__ import annotations

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.export import grab, png_bytes, save_png
from emtk.testing import png_decode


def _gui():
    im.begin("Exported", (0, 0, 300, 200))
    im.text("hello export")
    im.button("Press")
    im.end()


def test_a_gui_callable_becomes_a_png_of_the_requested_size(tmp_path):
    path = save_png(_gui, tmp_path / "out.png", size=(320, 200))
    width, height, px = png_decode(path.read_bytes())
    assert (width, height) == (320, 200)
    assert any(px[i] != px[0] for i in range(0, len(px), 4)), "the picture is blank"


def test_an_imapp_is_drawn_through_its_own_draw():
    drawn = []

    class App(ImApp):
        def draw(self, painter, x, y, w, h):
            drawn.append((x, y, w, h))
            super().draw(painter, x, y, w, h)

    data = png_bytes(App(_gui), size=(240, 160))
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert drawn and drawn[-1] == (0.0, 0.0, 240.0, 160.0)


def test_fewer_than_two_frames_is_raised_to_two():
    painter = grab(_gui, (200, 120), frames=1)      # fewer than two is raised to two
    assert (painter.width, painter.height) == (200, 120)


def test_a_bad_size_is_refused():
    with pytest.raises(ValueError):
        grab(_gui, (0, 100))
