"""Proportional text is drawn where it is measured, one texel per device pixel.

A documentation page set in Arial at the body size (10.7 px) read as words glued
together ("theyare"), spaced unevenly, on a wobbling baseline. Three causes, each
pinned here:

* the glyph was rasterised at the em **rounded to a whole pixel** (11 px for
  10.67), so every glyph was a few percent wider than the advance it sat on;
* every glyph was then **rounded to a whole pixel** on its own, so pen errors of up
  to half a pixel did not cancel -- a space shrank to nothing next to a ``t``;
* the glyph box was sized from the raster and sampled *linearly*, half a texel in
  from its edges, which squeezed a narrow letter by a fifth.

The tests composite :func:`emtk.font_render.glyphs` on the CPU exactly as the GPU
host draws it (one texel per device pixel at the snapped corner), so they run with
no adapter.
"""
from __future__ import annotations

import numpy as np
import pytest

from emtk import font_render, type_scale


def _spec():
    return font_render.font_spec(type_scale.text_font("body"))


def _composite(spec, string, device=1.0, origin=(5.0, 4.0), size=(640, 40)):
    """Glyph coverage composited at its drawn boxes, plus the boxes (device px)."""
    canvas = np.zeros((size[1], size[0]), dtype=float)
    boxes = []
    for texture, x, y, w, h in font_render.glyphs(spec, string, 1.0, device=device,
                                                  origin=origin):
        X, Y = x * device, y * device
        assert X == pytest.approx(round(X)) and Y == pytest.approx(round(Y)), \
            "a glyph box off the device grid is resampled, which blurs it"
        assert (w * device, h * device) == pytest.approx((texture.width, texture.height)), \
            "a glyph is drawn one texel per device pixel, never scaled"
        assert texture.filter == "nearest"
        X, Y = round(X), round(Y)
        alpha = np.frombuffer(bytes(texture.px), np.uint8).reshape(
            texture.height, texture.width, 4)[:, :, 3] / 255.0
        region = canvas[Y:Y + texture.height, X:X + texture.width]
        region[:] = np.maximum(region, alpha[:region.shape[0], :region.shape[1]])
        boxes.append((X, Y, texture.width, texture.height, alpha))
    return canvas, boxes


def _ink_columns(alpha, threshold=0.25):
    cols = np.flatnonzero((alpha > threshold).any(axis=0))
    return (int(cols[0]), int(cols[-1])) if cols.size else None


@pytest.mark.parametrize("device", [1.0, 2.0])
def test_the_raster_is_the_exact_em_not_a_rounded_one(device):
    spec = _spec()
    em = font_render._px(spec, 1.0) * device
    # Glyph "H" is rasterised at the fractional em: its ink is the face's own width.
    (texture, *_), = font_render.glyphs(spec, "H", 1.0, device=device, origin=(0.0, 0.0))
    face = font_render._face(spec)
    left, _top, right, _bottom = font_render._loaded(face, round(em * 8) / 8).getbbox(
        "H", anchor="ls")
    assert texture.width == right - left + 3


@pytest.mark.parametrize("device", [1.0, 2.0])
@pytest.mark.parametrize("origin_x", [5.0, 5.25, 5.5, 5.8])
def test_glyphs_sit_on_their_measured_advances(device, origin_x):
    """Every pen within 1/8 device px of the size-linear layout, wherever the line starts."""
    spec = _spec()
    string = "the dilute solution of it"
    k = font_render._px(spec, 1.0) / font_render.LAYOUT_PX
    pens = font_render._positions(spec, string)
    chars = [(i, c) for i, c in enumerate(string) if not c.isspace()]
    raster = round(font_render._px(spec, 1.0) * device * font_render.RASTER_QUANTUM) \
        / font_render.RASTER_QUANTUM
    face = font_render._face(spec)
    drawn = font_render.glyphs(spec, string, 1.0, device=device, origin=(origin_x, 0.0))
    for (index, char), (_texture, x, *_rest) in zip(chars, drawn):
        left = font_render._glyph(face, raster, char, 0.0, "nearest")[1]
        drawn_pen = x * device - left  # the whole device pixel; the phase carries the rest
        wanted = (origin_x + pens[index] * k) * device
        assert abs((wanted - drawn_pen) - round((wanted - drawn_pen) * 4) / 4) <= 0.125 + 1e-6
        assert -0.125 - 1e-6 <= wanted - drawn_pen < 1.0


@pytest.mark.parametrize("device", [1.0, 2.0])
def test_words_never_touch(device):
    """The space between two words keeps a visible gap of ink-free columns."""
    spec = _spec()
    for pair in ("the to", "of it", "they are", "dilute solution", "is a", "f j"):
        for origin_x in (5.0, 5.25, 5.5, 5.75):
            canvas, _boxes = _composite(spec, pair, device, origin=(origin_x, 4.0))
            ink = (canvas > 0.25).any(axis=0)
            cols = np.flatnonzero(ink)
            first_word = font_render.text_width(spec, pair.split()[0], 1.0)
            space_at = (origin_x + first_word) * device
            gap = ~ink[int(space_at) - 0: int(space_at + font_render.text_width(spec, " ", 1.0)
                                              * device)]
            assert cols.size and gap.any(), f"{pair!r} at x={origin_x}: the words touch"


def test_adjacent_letters_do_not_overlap_more_than_the_face_kerns():
    """Neighbouring glyph inks overlap only where the face itself overlaps them."""
    spec = _spec()
    string = "proportional to the transition"
    _canvas, boxes = _composite(spec, string, 1.0)
    for (x0, _y0, _w0, _h0, a0), (x1, _y1, _w1, _h1, a1) in zip(boxes, boxes[1:]):
        ink0, ink1 = _ink_columns(a0, 0.5), _ink_columns(a1, 0.5)
        if ink0 is None or ink1 is None:
            continue
        assert x1 + ink1[0] >= x0 + ink0[1] - 1, "solid ink of two letters collides"


@pytest.mark.parametrize("device", [1.0, 2.0])
def test_one_baseline_for_the_whole_line(device):
    """The baseline is snapped once per line, so equal-height letters share a top row."""
    spec = _spec()
    _canvas, boxes = _composite(spec, "xxoxxvxzxu", device, origin=(5.0, 4.37))
    bottoms = set()
    for X, Y, _w, _h, alpha in boxes:
        rows = np.flatnonzero((alpha > 0.5).any(axis=1))
        bottoms.add(Y + int(rows[-1]))
    assert len(bottoms) <= 2, f"x-height letters end on {sorted(bottoms)}"


def test_subscripts_and_superscripts_sit_below_and_above_the_line():
    spec = _spec()
    canvas, boxes = _composite(spec, "S₁ 10⁻⁶", 2.0)
    by_char = dict(zip("S₁10⁻⁶", boxes))

    def ink_rows(box):
        X, Y, _w, _h, alpha = box
        rows = np.flatnonzero((alpha > 0.4).any(axis=1))
        return Y + int(rows[0]), Y + int(rows[-1])

    s_top, s_bottom = ink_rows(by_char["S"])
    sub_top, sub_bottom = ink_rows(by_char["₁"])
    sup_top, sup_bottom = ink_rows(by_char["⁶"])
    assert sub_bottom > s_bottom, "a subscript descends below the baseline"
    assert sub_top > s_top, "a subscript starts below the capital's top"
    assert sup_top <= s_top + 1, "a superscript reaches the capital's top"
    assert sup_bottom < s_bottom, "a superscript ends above the baseline"


@pytest.mark.parametrize("family", ["prose", "Arial"])
def test_pen_positions_equal_the_prefix_definition(family):
    """Built from cached advances and pair kerns, identical to measuring every prefix
    (which was quadratic: a second per frame for a page of prose)."""
    try:
        spec = font_render.font_spec({"family": family, "size": 8.0})
    except ValueError:
        pytest.skip(f"{family} is not installed")
    string = "AVATAR Wave To. The quick brown fox, S₁ 10⁻⁶"
    font_render._positions.cache_clear()
    pens = font_render._positions(spec, string)
    expected, offset = [], 0.0
    for face, _, text in font_render._runs(spec, string):
        font = font_render._loaded(face, font_render.LAYOUT_PX)
        expected.extend(offset + font.getlength(text[:i + 1]) - font.getlength(c)
                        for i, c in enumerate(text))
        offset += font.getlength(text)
    assert pens == pytest.approx(expected, abs=1e-6)
