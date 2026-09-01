"""``Texture`` and the painter-level image path.

A program that shows a picture has pixels. Dear ImGui's answer is a GL
texture id, which puts a graphics API in the application and ends the
arrangement cmtk exists for -- the same widget code on a GPU context, in a
browser, and in a test with no window. So the pixels go in a ``Texture`` and
the painter decides what to do with them.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk import Texture
from cmtk.testing import PixelPainter


def _checker(n=4):
    tex = Texture(n, n)
    for y in range(n):
        for x in range(n):
            tex.set_pixel(x, y, (255, 0, 0, 255) if (x + y) % 2 else (0, 0, 255, 255))
    return tex


def test_a_texture_needs_a_positive_size():
    """A zero-sized texture has no pixels to draw, and every painter would
    have to special-case it."""
    with pytest.raises(ValueError, match="positive size"):
        Texture(0, 4)


def test_a_short_buffer_is_refused():
    """Drawn as-is it is a picture of whatever followed it in memory."""
    with pytest.raises(ValueError, match="needs 64 bytes"):
        Texture(4, 4, b"\x00" * 10)


def test_writing_moves_the_revision():
    """What a painter that uploads caches against."""
    tex = Texture(2, 2)
    first = tex.revision
    tex.fill((1, 2, 3, 255))
    assert tex.revision > first
    mid = tex.revision
    tex.set_pixel(0, 0, (9, 9, 9, 255))
    assert tex.revision > mid


def test_a_bulk_row_write_is_one_revision():
    """A frame arriving as one buffer must not bump once per pixel, or a
    caching painter re-uploads for every pixel in it."""
    tex = Texture(4, 2)
    before = tex.revision
    tex.set_rows(0, bytes(4 * 2 * 4))
    assert tex.revision == before + 1


def test_a_row_write_past_the_end_is_refused():
    tex = Texture(4, 2)
    with pytest.raises(ValueError, match="runs past the end"):
        tex.set_rows(1, bytes(4 * 2 * 4))


def test_the_pixel_painter_rasterises_it():
    """No upload, no graphics API: this painter owns its pixels."""
    p = PixelPainter(40, 40, background=(0, 0, 0, 255))
    p.image(0, 0, 40, 40, _checker(2))
    top_left = p.px[0:4]
    top_right = p.px[(39 * 4):(39 * 4) + 4]
    assert tuple(top_left) != tuple(top_right), "the checker drew flat"


def test_it_scales_by_nearest_neighbour():
    """A scientific image scaled up should show its pixels, not a smooth
    guess between them -- so the magnified block is exactly one colour."""
    tex = Texture(2, 2)
    tex.fill((0, 0, 0, 255))
    tex.set_pixel(0, 0, (255, 0, 0, 255))
    p = PixelPainter(40, 40, background=(0, 0, 0, 255))
    p.image(0, 0, 40, 40, tex)
    for x, y in ((2, 2), (10, 10), (17, 17)):
        assert tuple(p.px[(y * 40 + x) * 4:(y * 40 + x) * 4 + 3]) == (255, 0, 0)


def test_the_image_signature_is_the_protocol_s():
    """``cmtk.painter.image`` calls the operation positionally as
    ``(x, y, w, h, handle, ...)``. PixelPainter took ``(handle, p_min,
    p_max, ...)``, so `handle` bound to the x coordinate and every image
    drew a tinted rectangle in the wrong place."""
    from cmtk import painter as painter_mod

    p = PixelPainter(40, 40, background=(0, 0, 0, 255))
    painter_mod.image(p, 0.0, 0.0, 40.0, 40.0, _checker(2))
    assert tuple(p.px[0:4]) != (0, 0, 0, 255), "nothing was drawn"


def test_an_opaque_handle_still_degrades_to_a_tinted_box():
    """A host's own texture id means nothing to this painter, and a port
    that shows a picture must still run."""
    p = PixelPainter(20, 20, background=(0, 0, 0, 255))
    p.image(0, 0, 20, 20, object(), tint=(0, 255, 0, 255))
    assert tuple(p.px[0:4]) == (0, 255, 0, 255)


def test_uv_windows_into_the_texture():
    """Drawing a sub-rectangle without placing the image twice."""
    tex = Texture(2, 1)
    tex.set_pixel(0, 0, (255, 0, 0, 255))
    tex.set_pixel(1, 0, (0, 0, 255, 255))
    p = PixelPainter(10, 10, background=(0, 0, 0, 255))
    p.image(0, 0, 10, 10, tex, uv0=(0.5, 0.0), uv1=(1.0, 1.0))
    assert tuple(p.px[0:3]) == (0, 0, 255), "the uv window was ignored"


def test_a_transparent_pixel_leaves_the_background():
    tex = Texture(1, 1, bytes((255, 0, 0, 0)))
    p = PixelPainter(4, 4, background=(7, 8, 9, 255))
    p.image(0, 0, 4, 4, tex)
    assert tuple(p.px[0:3]) == (7, 8, 9)


def test_it_draws_through_the_immediate_mode_api():
    """The whole point: `im.image(tex, size)` in ordinary gui code."""
    io, storage = cmtk.IO(), {}
    p = PixelPainter(60, 60, background=(0, 0, 0, 255))
    with cmtk.frame(p, (0, 0, 60, 60), io=io, storage=storage):
        cmtk.begin("w")
        cmtk.image(_checker(2), (40, 40))
        cmtk.end()
    lit = sum(1 for i in range(0, len(p.px), 4) if p.px[i] > 60)
    assert lit > 0, "im.image drew nothing"
