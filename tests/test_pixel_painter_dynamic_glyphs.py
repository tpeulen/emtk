"""``PixelPainter`` draws glyphs from *both* halves of the atlas.

The atlas is one texture in two halves: the rows baked at build time on top,
and under them the runtime cache that rasterises whatever the baker never saw
-- accents, Greek, Cyrillic, CJK. ``Atlas.cell_of`` returns coordinates in
that combined space.

``PixelPainter`` decoded only the baked PNG, so a cell from the lower half
indexed past the end of the buffer: an ``IndexError`` where it ran off, and
silently the *wrong glyph* where it merely landed somewhere else. Headless is
where documentation screenshots and golden images come from, so "wrong glyph,
no error" is the failure that ships.
"""

from __future__ import annotations

import pytest

from emtk.font import load_atlas
from emtk.testing import PixelPainter

#: Characters no reasonable build bakes, one per script.
BEYOND_THE_BAKED = ["ü", "Δ", "λ", "≈", "Ж", "日"]


def _ink(painter: PixelPainter) -> int:
    """How many pixels the text actually lit."""
    px = painter.px
    return sum(1 for i in range(0, len(px), 4) if px[i] > 40)


needs_cache = pytest.mark.skipif(
    load_atlas().cache is None,
    reason="no glyph rasteriser on this machine; the atlas draws its "
           "placeholder instead, which is the documented fallback")


def _draw(text: str) -> PixelPainter:
    p = PixelPainter(420, 60, background=(0, 0, 0, 255))
    p.text(2.0, 2.0, 416.0, 30.0, 0, text, (255, 255, 255, 255))
    return p


def test_a_baked_character_still_draws():
    assert _ink(_draw("plain ASCII")) > 0


@needs_cache
@pytest.mark.parametrize("char", BEYOND_THE_BAKED)
def test_a_character_from_the_cache_half_draws_rather_than_raising(char):
    """This raised IndexError before: the cell's row is below the baked
    image, and only the baked image was being decoded."""
    assert _ink(_draw(char)) > 0, f"{char!r} drew nothing"


@needs_cache
def test_the_cache_half_is_not_sampled_as_if_it_were_the_baked_half():
    """Ink alone would pass if the wrong glyph were drawn, so compare a
    string with accents against the same string without: the accents are
    extra marks, so they must add ink."""
    assert _ink(_draw("Zelldichte für Fläche")) > _ink(_draw("Zelldichte fur Flache"))


@needs_cache
def test_glyphs_from_both_halves_in_one_string():
    """The source is chosen per glyph, not once per call -- a mixed string is
    the case a per-call choice gets wrong."""
    assert _ink(_draw("Delta = Δ, tau = τ")) > 0


@needs_cache
def test_a_rasterised_glyph_is_still_right_after_the_cache_grows():
    """The flattened copy is keyed on the cache's ``version``, which it bumps
    for every glyph it stores. Keyed on anything staler, the second character
    would sample a buffer taken before it existed."""
    first = _ink(_draw("Δ"))
    _draw("日本語한국어")                      # several more cache entries
    assert _ink(_draw("Δ")) == first
