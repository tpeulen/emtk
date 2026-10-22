"""The pictographs the interface spells its icons with are baked, not placeholder.

The web release has no font engine: Pyodide ships no system fonts, so the
runtime glyph cache (:mod:`emtk.dynamic_font`) has nothing to load and every
codepoint outside the baked rows draws the atlas placeholder. A plugin menu
whose manifest says ``icon = "🧵"`` came out as a ``¤`` -- reported as "all
emoticons and icons are missing" on the web page. The fix is bake-time: the
pictographs the interface actually draws ride in the committed atlas like
every other glyph, so a host that can only read the PNG draws them too.

The canonical list lives in the baker (``tools/bake_chrome_atlas.py``); this
file loads it from there, because a list duplicated here is a list that drifts.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

from emtk import font
from emtk.testing import PixelPainter


def _baker():
    """The bake script, imported from the checkout it lives in."""
    root = pathlib.Path(font.__file__).resolve().parents[1]
    path = root / "tools" / "bake_chrome_atlas.py"
    if not path.is_file():  # an installed emtk without its checkout
        pytest.skip("no tools/bake_chrome_atlas.py beside this checkout")
    spec = importlib.util.spec_from_file_location("bake_chrome_atlas", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BAKER = _baker()
EMOJI = BAKER.EMOJI_CHARS


@pytest.fixture(scope="module")
def atlas_alpha():
    """``(alpha, meta)``: the atlas's alpha channel and its JSON."""
    image = pytest.importorskip("PIL.Image", reason="Pillow reads the atlas")
    alpha = np.array(image.open(font.ATLAS_DIR / "chrome.png").convert("RGBA"))[..., 3]
    meta = json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))
    return alpha, meta


def test_every_needed_pictograph_is_in_the_charset_and_both_faces(atlas_alpha):
    """A face without the entry draws the placeholder for bold labels only."""
    _alpha, meta = atlas_alpha
    atlas = font.load_atlas()
    for char in EMOJI:
        assert char in meta["charset"], f"{char!r} is not in the baked charset"
        assert atlas.covers(char), f"{char!r} has no regular-face cell"
        x, y, w, h = atlas.cell_of(char, bold=True)
        assert (x, y, w, h) == atlas.cell_of(char), f"{char!r} differs between faces"


@pytest.mark.parametrize("char", EMOJI)
def test_a_baked_pictograph_is_a_shape_not_a_block_or_blank(char, atlas_alpha):
    """Real ink in the cell, shaped like a pictogram: not empty, not solid.

    The ink floor is an absolute pixel count, not a fraction: a one-stroke
    mark (✓, ↩, ⟵) covers under 2% of the 74x99 cell even before
    antialiasing thins it further, and a fraction floor would call a drawn
    checkmark blank. Thirty lit texels is visible ink at the bake's size and
    cannot come from a neighbour -- every cell around a pictograph is
    transparent.
    """
    alpha, meta = atlas_alpha
    atlas = font.load_atlas()
    x, y, w, h = atlas.cell_of(char)
    cell = alpha[y:y + h, x:x + w]
    assert np.count_nonzero(cell) >= 30, f"{char!r} baked blank"
    solid = float(np.count_nonzero(cell > 200)) / cell.size
    assert solid <= 0.85, f"{char!r} baked as a solid block"
    assert cell[0].max() == 0 and cell[-1].max() == 0, f"{char!r} reaches its cell edge"


def _draw(text: str) -> PixelPainter:
    p = PixelPainter(420, 60, background=(0, 0, 0, 255))
    p.text(2.0, 2.0, 416.0, 30.0, 0, text, (255, 255, 255, 255))
    return p


def _px(painter: PixelPainter) -> "np.ndarray":
    return np.array(painter.px, dtype=np.uint8)


@pytest.mark.parametrize("char", ["🧵", "⚙", "📊"])
def test_the_painter_draws_the_pictograph_not_the_placeholder(char):
    """``PixelPainter`` reproduces the web host's read-only-atlas text path.

    Before the bake, ``cell_of`` fell through to ``MISSING_GLYPH`` for every
    one of these, so the mask drawn for ``char`` was pixel-identical to the
    mask drawn for ``¤`` -- the report's "missing" icons. It must differ now.
    """
    pictograph = _px(_draw(char))
    placeholder = _px(_draw(font.MISSING_GLYPH))
    assert pictograph.tobytes() != placeholder.tobytes(), (
        f"{char!r} draws exactly the placeholder mask: not baked"
    )
    plain = _px(_draw("A"))
    assert pictograph.tobytes() != plain.tobytes(), f"{char!r} draws as 'A'"


def test_the_needs_of_the_apps_are_covered():
    """The manifest icons of every shipped chisurf plugin are in the bake list.

    The web release packs this atlas; a plugin icon missing here is missing on
    the page. Read straight from the checkout's plugin manifests, not copied.
    """
    manifests = (
        pathlib.Path(font.__file__).resolve().parents[1].parent
        / "chisurf" / "chisurf" / "plugins"
    )
    if not manifests.is_dir():
        pytest.skip("no chisurf checkout beside this one")
    from emtk.grapheme import glyph_of

    missing = []
    for manifest in sorted(manifests.glob("*/manifest.json")):
        icon = json.loads(manifest.read_text(encoding="utf-8")).get("icon", "")
        if not icon:
            continue
        base = glyph_of(icon[0])
        if base not in EMOJI:
            missing.append(f"{manifest.parent.name}: {icon!r} ({base!r})")
    assert not missing, f"manifest icons outside the baked pictographs: {missing}"
