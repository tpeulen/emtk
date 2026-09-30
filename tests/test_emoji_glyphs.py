"""A colour emoji is drawn as a one-colour pictogram, never as a solid block.

Apple Color Emoji loads only at a fixed 160 px bitmap strike. The glyph cache
used to draw that strike into a cell-sized canvas and keep the alpha channel,
which cropped it to the strike's top-left corner and produced an opaque
rectangle: every ``"📁 Open"`` button in an app began with a white box.
"""

from __future__ import annotations

import numpy as np
import pytest

from emtk.font import load_atlas

EMOJI = ["🚀", "📁", "🗑", "💾", "🎯"]


def _cache_or_skip():
    cache = load_atlas().cache
    if cache is None:
        pytest.skip("no glyph rasteriser on this machine")
    return cache


@pytest.mark.parametrize("char", EMOJI)
def test_an_emoji_is_a_shape_not_a_filled_cell(char):
    cache = _cache_or_skip()
    if cache._font_for(char) is None:
        pytest.skip("no font on this machine covers this emoji")
    cell = cache.cell_of(char)
    assert cell is not None
    x, y, w, h = cell
    alpha = cache.image[y:y + h, x:x + w, 3]
    lit = float(np.count_nonzero(alpha > 32)) / alpha.size
    assert 0.05 < lit < 0.85, f"{char!r} covers {lit:.0%} of its cell"
    assert alpha[0].max() == 0 and alpha[-1].max() == 0, "glyph reaches the cell edge"
