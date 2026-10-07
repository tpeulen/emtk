"""True textures and selected-font glyphs obey the painter's nested scissor."""

from __future__ import annotations

import pytest
from emtk import im
from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
from emtk.scaled_painter import ScaledPainter
from emtk.testing import PixelPainter
from emtk.texture import Texture

BACKGROUND = (11, 19, 27, 255)


def _pixel(painter, x, y):
    """Read a device pixel from the public raster buffer."""
    offset = (y * painter.width + x) * 4
    return tuple(painter.px[offset:offset + 4])


def _assert_crop(actual, reference, box):
    """Clipping masks the complete draw without changing visible texel sampling."""
    x0, y0, x1, y1 = box
    inside_ink = outside_ink = 0
    for y in range(actual.height):
        for x in range(actual.width):
            inside = x0 <= x < x1 and y0 <= y < y1
            expected = _pixel(reference, x, y) if inside else BACKGROUND
            assert _pixel(actual, x, y) == expected, (x, y, box)
            if _pixel(reference, x, y) != BACKGROUND:
                inside_ink += inside
                outside_ink += not inside
    assert inside_ink and outside_ink  # The fixture genuinely straddles the scissor.


@pytest.mark.parametrize("tint", [(255, 255, 255, 255), (170, 240, 110, 127)])
def test_nested_fractional_texture_clip_preserves_uvs_and_alpha(tint):
    """An intersected fractional scissor preserves texture origin, UVs and tint."""
    texture = Texture(4, 2, bytes((
        240, 10, 50, 255, 10, 220, 60, 128, 30, 40, 210, 220, 250, 210, 0, 255,
        0, 190, 210, 64, 240, 80, 130, 255, 190, 250, 30, 180, 100, 70, 10, 255,
    )))
    reference = PixelPainter(40, 25, BACKGROUND)
    actual = PixelPainter(40, 25, BACKGROUND)
    args = (-3.0, -2.0, 36.0, 24.0, texture)
    options = {"uv0": (0.25, 0.0), "uv1": (0.75, 1.0), "tint": tint}
    reference.image(*args, **options)
    actual.push_clip(3.2, 4.7, 23.5, 12.2)
    actual.push_clip(7.1, 8.6, 5.7, 3.8)
    actual.image(*args, **options)
    _assert_crop(actual, reference, (7, 8, 12, 12))


def test_texture_clip_pop_restores_parent_and_empty_clip_draws_nothing():
    """Popping a nested clip restores its parent; disjoint clips have no pixels."""
    texture = Texture(1, 1, bytes((230, 90, 40, 255)))
    actual = PixelPainter(24, 20, BACKGROUND)
    reference = PixelPainter(24, 20, BACKGROUND)
    reference.image(0, 0, 24, 20, texture)
    actual.push_clip(4, 3, 11, 10)
    actual.push_clip(20, 17, 2, 2)
    actual.image(0, 0, 24, 20, texture)
    assert all(_pixel(actual, x, y) == BACKGROUND for y in range(20) for x in range(24))
    actual.pop_clip()
    actual.image(0, 0, 24, 20, texture)
    _assert_crop(actual, reference, (4, 3, 15, 13))
    actual.pop_clip()
    actual.image(0, 0, 24, 20, texture)
    assert actual.px == reference.px


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_texture_scissor_scales_once_with_device_pixels(scale):
    """HiDPI composition clips in the same device coordinates as its texture."""
    reference = PixelPainter(60, 48, BACKGROUND)
    actual = PixelPainter(60, 48, BACKGROUND)
    texture = Texture(1, 1, bytes((230, 90, 40, 190)))
    ScaledPainter(reference, scale).image(1, 2, 24, 18, texture)
    canvas = ScaledPainter(actual, scale)
    canvas.push_clip(5, 6, 8, 7)
    canvas.image(1, 2, 24, 18, texture)
    _assert_crop(actual, reference, (int(5 * scale), int(6 * scale),
                                  int(13 * scale), int(13 * scale)))


def test_selected_font_glyph_textures_obey_child_clip():
    """The real sans-serif font used by Markdown clips like the default atlas."""
    reference = PixelPainter(180, 70, BACKGROUND)
    actual = PixelPainter(180, 70, BACKGROUND)
    for painter in (reference, actual):
        painter.set_font("sans-serif")
    actual.push_clip(10, 10, 50, 8)
    args = (0, 8, 180, 18, ALIGN_LEFT | ALIGN_VCENTER, "Help body glyphs", (240, 240, 240))
    reference.text(*args)
    actual.text(*args)
    _assert_crop(actual, reference, (10, 10, 60, 18))


def test_long_markdown_stays_inside_its_scrollable_child():
    """Help-body Markdown cannot paint over a footer or outside its modal."""
    painter = PixelPainter(220, 140, BACKGROUND)
    with im.frame(painter, (0, 0, 220, 140)):
        im.begin_child((20, 15, 180, 65), child_id="help-body")
        im.markdown("\n\n".join(["A long help paragraph with real glyphs."] * 12))
        im.end_child()
    assert any(_pixel(painter, x, y) != BACKGROUND for y in range(15, 80) for x in range(20, 200))
    assert all(_pixel(painter, x, y) == BACKGROUND for y in range(90, 140) for x in range(220))
