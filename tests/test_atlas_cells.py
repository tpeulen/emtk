"""The baked glyph cells: inked, inside their borders, and bold where bold.

The atlas is a committed artefact, so it is the kind of thing that goes wrong
once and stays wrong: a glyph that baked blank draws as nothing, and a glyph
whose ink crosses its cell boundary makes the *neighbouring* character grow a
sliver of something else along one edge. Neither raises, and both are the sort
of defect that a screenshot at 10 pt does not obviously show.

Both were real. Baking with the cell sized to the font's advance left the bold
``#`` and ``─`` touching their borders -- a monospaced font's advance bounds its
*spacing*, not its ink, and ``─`` is a box-drawing character deliberately drawn
to join the one beside it. The padding is measured from both faces' ink now, and
this is what says it stayed measured.

The controls check follows: a symbol a control spells with an unbaked glyph is
rasterised on first use where a font engine exists (:mod:`emtk.dynamic_font`),
and is the atlas placeholder where none does -- so the chrome's own symbols are
spelled with baked glyphs. These tests came from chimol, where emtk started.
"""
from __future__ import annotations

import ast
import json
import pathlib

import numpy as np
import pytest

from emtk import font

_EMTK = pathlib.Path(font.__file__).resolve().parent


@pytest.fixture(scope="module")
def atlas():
    """``(alpha, metrics)``: the alpha channel and ``chrome.json``."""
    image = pytest.importorskip("PIL.Image", reason="Pillow reads the atlas")
    alpha = np.array(image.open(font.ATLAS_DIR / "chrome.png").convert("RGBA"))[..., 3]
    return alpha, json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))


def test_no_glyph_baked_blank(atlas):
    """Every character except whitespace has ink.

    Catches a font that lacks a symbol and silently substitutes nothing --
    which at run time is an empty box where a menu marker should be.
    """
    alpha, meta = atlas
    # Whitespace, not just U+0020: the charset covers Latin-1, which brings the
    # no-break space with it. A space with ink would be the bug.
    blank = [
        (face, char)
        for face, table in meta["glyphs"].items()
        for char, (x, y, w, h, _adv) in table.items()
        if not char.isspace() and alpha[y : y + h, x : x + w].max() == 0
    ]
    assert not blank, f"these glyphs baked blank: {blank}"


def test_no_glyph_touches_its_cell_border(atlas):
    """Ink stays inside its cell, so a quad cannot sample its neighbour."""
    alpha, meta = atlas
    spills = []
    for face, table in meta["glyphs"].items():
        for char, (x, y, w, h, _adv) in table.items():
            cell = alpha[y : y + h, x : x + w]
            border = np.concatenate([cell[0, :], cell[-1, :], cell[:, 0], cell[:, -1]])
            if border.max() > 0:
                spills.append((face, char, int(border.max())))
    assert not spills, "ink on the cell border -- raise the padding: " + repr(spills[:8])


def test_the_bold_face_is_actually_bolder(atlas):
    """Bold carries measurably more ink than regular, at the same advance.

    Worth asserting because it cannot be seen: the chrome font is monospaced, so
    the bold face has the *same* advance and, at a glance in an atlas, looks
    like the regular one. A ``setBold`` that silently failed would leave menu
    titles indistinguishable from their items, and nothing else would complain.
    """
    alpha, meta = atlas
    regular, bold = meta["glyphs"]["regular"], meta["glyphs"]["bold"]
    for char in "AWio":
        rx, ry, rw, rh, _ = regular[char]
        bx, by, bw, bh, _ = bold[char]
        light = float(alpha[ry : ry + rh, rx : rx + rw].sum())
        heavy = float(alpha[by : by + bh, bx : bx + bw].sum())
        assert heavy > light * 1.05, (
            f"the bold {char!r} carries {heavy / light:.3f}x the ink of the "
            "regular one; the bold face did not resolve"
        )


#: Per module, characters that appear in a string literal but are classified,
#: not drawn. Keep this as small as it can honestly be: an entry here is a
#: promise that the character never reaches ``Painter.text``.
_NOT_DRAWN = {
    # `_PUNCT_CHARS`, the set a line may break *after* -- the word-wrap rule for
    # CJK, which has no spaces to break on.
    "widgets/text.py": "　、。",
}

_CONTROL_MODULES = sorted(
    p.relative_to(_EMTK).as_posix() for p in _EMTK.rglob("*.py") if p.name != "__init__.py"
)


def _drawn_literals(tree: ast.AST) -> set[str]:
    """Non-ASCII characters in string literals, docstrings excluded.

    Literals, not the raw file: a comment that names an unbaked glyph in order
    to warn about it is not something the chrome draws.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return {
        char
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        for char in node.value
        if ord(char) > 127
    }


def test_the_control_modules_are_found():
    """An empty parameter list would pass the check below by skipping it."""
    assert "widgets/text.py" in _CONTROL_MODULES


@pytest.mark.parametrize("module", _CONTROL_MODULES)
def test_every_control_module_draws_only_baked_glyphs(atlas, module):
    """No control spells a symbol with a glyph the atlas does not hold.

    Five real cases were found by this: the tab bar drew its close button as
    ``✕`` and its scroll arrows as ``◂``, the table drew ``▲`` and ``✓``, and
    ``widgets.Table``'s ascending sort mark was ``▲`` while the descending one
    was ``▼`` -- only ``▼`` baked, so ascending showed no marker at all. Spell a
    symbol with a baked glyph (``▴``/``▾``, ``◀``/``▶``, ``■``, or ASCII)
    rather than widening the atlas: every glyph costs texture area.
    """
    _alpha, meta = atlas
    used = _drawn_literals(ast.parse((_EMTK / module).read_text(encoding="utf-8")))
    used -= set(_NOT_DRAWN.get(module, ""))
    assert used <= set(meta["charset"]), (
        f"{module} draws these but the atlas has no glyph: "
        f"{sorted(used - set(meta['charset']))}"
    )
