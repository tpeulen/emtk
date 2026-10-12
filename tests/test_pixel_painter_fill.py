"""PixelPainter fills: the opaque fast path writes exactly what the per-pixel blend wrote."""

import time

from emtk.testing import PixelPainter


def _blend(px, width, x0, y0, x1, y1, colour):
    """The per-pixel source-over blend ``PixelPainter._fill`` used for every fill."""
    r, g, b, a = colour
    sa = a / 255.0
    for yy in range(y0, y1):
        for i in range(x0, x1):
            o = (yy * width + i) * 4
            px[o] = int(r * sa + px[o] * (1 - sa))
            px[o + 1] = int(g * sa + px[o + 1] * (1 - sa))
            px[o + 2] = int(b * sa + px[o + 2] * (1 - sa))
            px[o + 3] = max(px[o + 3], a)


def test_opaque_transparent_and_translucent_fills_match_the_blend():
    painter = PixelPainter(40, 30, background=(10, 20, 30, 200))
    expected = bytearray(painter.px)
    for rect, colour in (
        ((5, 4, 20, 10), (200, 100, 50, 255)),  # opaque: the fast path
        ((8, 6, 30, 30), (1, 2, 3, 0)),  # transparent: no change
        ((0, 0, 12, 12), (90, 180, 45, 128)),  # translucent: blended
        ((3.6, 2.2, 7.9, 5.5), (17.0, 33.0, 99.0, 255)),  # float boxes and channels
    ):
        painter.fill_rect(*rect, colour)
        x, y, w, h = rect
        x0, y0 = max(int(x), 0), max(int(y), 0)
        x1, y1 = min(int(x + w), 40), min(int(y + h), 30)
        _blend(expected, 40, x0, y0, x1, y1, colour)
    assert painter.px == expected


def test_the_opaque_fill_respects_the_clip():
    painter = PixelPainter(20, 20)
    painter.push_clip(5, 5, 4, 4)
    painter.fill_rect(0, 0, 20, 20, (255, 0, 0, 255))
    reds = {
        (i // 4 % 20, i // 4 // 20) for i in range(0, len(painter.px), 4) if painter.px[i] == 255
    }
    assert reds == {(x, y) for x in range(5, 9) for y in range(5, 9)}


def test_a_window_background_on_a_tall_canvas_is_cheap():
    # A docked window's opaque background over a 1500 x 4000 screenshot took ~0.1 s per fill.
    painter = PixelPainter(1500, 4000, background=(0, 0, 0, 255))
    start = time.perf_counter()
    for _ in range(20):
        painter.fill_rect(0, 0, 1500, 4000, (30, 30, 30, 255))
    assert time.perf_counter() - start < 1.0
