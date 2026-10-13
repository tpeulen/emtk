"""A translucent fill blends every pixel exactly as the per-pixel formula does, and fast."""

from __future__ import annotations

import time

from emtk.testing import PixelPainter


def _reference(px, width, x0, y0, x1, y1, colour):
    """The per-pixel blend the table-driven fill replaced."""
    r, g, b, a = colour
    sa = a / 255.0
    out = bytearray(px)
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            o = (yy * width + xx) * 4
            out[o] = int(r * sa + out[o] * (1 - sa))
            out[o + 1] = int(g * sa + out[o + 1] * (1 - sa))
            out[o + 2] = int(b * sa + out[o + 2] * (1 - sa))
            out[o + 3] = max(out[o + 3], a)
    return out


def test_a_translucent_fill_equals_the_per_pixel_blend():
    painter = PixelPainter(40, 30)
    painter.fill_rect(0, 0, 40, 30, (10, 200, 90, 255))
    painter.fill_rect(5, 4, 12, 9, (250, 3, 120, 40))  # an earlier translucent layer
    before = bytes(painter.px)
    painter.fill_rect(3.6, 2.2, 25.9, 20.4, (17, 99, 230, 133))
    assert bytes(painter.px) == bytes(_reference(before, 40, 3, 2, 29, 22, (17, 99, 230, 133)))


def test_a_translucent_fill_respects_the_clip():
    painter = PixelPainter(20, 20)
    painter.push_clip(5, 5, 6, 6)
    before = bytes(painter.px)
    painter.fill_rect(0, 0, 20, 20, (255, 255, 255, 128))
    assert bytes(painter.px) == bytes(_reference(before, 20, 5, 5, 11, 11, (255, 255, 255, 128)))


def test_a_large_translucent_fill_is_not_per_pixel_python():
    painter = PixelPainter(1500, 4000)
    start = time.perf_counter()
    painter.fill_rect(0, 0, 1500, 4000, (0, 0, 0, 120))
    assert time.perf_counter() - start < 2.0  # per pixel this was tens of seconds
