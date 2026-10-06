"""Window border widths and shadows are real painter operations."""

import pytest
from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.testing import Driver, PixelPainter, RecordingPainter


def test_border_width_and_shadow_are_drawn_in_order():
    style = im.Style()
    style.window_border_size = 2.5
    style.window_shadow_size = 3.0
    style.window_shadow_color = (0, 0, 0, 72)
    p = RecordingPainter()
    with im.frame(p, (0, 0, 320, 240), style=style):
        im.begin("Analysis", (25, 25, 200, 140))
        im.end()
    shadow = ("fill_rect", 28, 28, 200, 140, (0, 0, 0, 72))
    assert shadow in p.calls
    assert p.calls.index(shadow) < next(
        i for i, c in enumerate(p.calls) if c[0] == "fill_rect" and c[1:5] == (25, 25, 200, 140)
    )
    assert p.stroke_widths[-1] == 2.5


def test_shadow_is_visible_outside_window_clip_and_no_background_opts_out():
    style = im.Style()
    style.window_border_size = 0
    style.window_shadow_size = 4
    p = PixelPainter(80, 60, background=(255, 255, 255, 255))
    with im.frame(p, (0, 0, 80, 60), style=style):
        im.begin("One", (10, 10, 40, 30))
        im.end()
    assert tuple(p.px[(35 * 80 + 51) * 4 : (35 * 80 + 51) * 4 + 3]) != (255, 255, 255)
    p = RecordingPainter()
    with im.frame(p, (0, 0, 80, 60), style=style):
        im.begin("Transparent", (10, 10, 40, 30), flags=im.WindowFlags.NO_BACKGROUND)
        im.end()
    assert not p.fills and not p.strokes


@pytest.mark.parametrize("width", [0, 1, 3])
def test_pixel_and_pil_borders_agree(width):
    from emtk.pil_painter import PilPainter

    a, b = PixelPainter(40, 30), PilPainter(40, 30)
    for p in (a, b):
        p.stroke_rect(5, 5, 20, 15, (240, 100, 50, 255), width=width)
    assert a.px == b.px
    if width:
        assert tuple(a.px[(7 * 40 + 7) * 4 : (7 * 40 + 7) * 4 + 3]) == (
            (240, 100, 50) if width == 3 else (0, 0, 0)
        )


def test_docked_panes_share_window_border_tokens():
    style = im.Style()
    style.window_border_size = 3.5
    docks = DockManager(Region("body"))
    docks.add_window("analysis", "Analysis", lambda: im.text("Measured sample"), dock="body")
    drv = Driver(ImApp(lambda: docks.draw((0, 0, 320, 200)), style=style), (320, 200))
    painter = drv.frame(2)
    assert 3.5 in painter.stroke_widths


def test_scaled_painter_scales_border_width_with_geometry():
    from emtk.scaled_painter import ScaledPainter

    painter = RecordingPainter()
    ScaledPainter(painter, 3).stroke_rect(5, 5, 20, 10, (255, 255, 255), width=1.5)
    assert painter.strokes[0][:4] == (15, 15, 60, 30)
    assert painter.stroke_widths == [4.5]
