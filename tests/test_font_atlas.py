"""The baked glyph atlas: shipped, readable, and complete.

Baking needs a font engine. *Reading* needs a JSON file and a PNG, and that
asymmetry is the whole design -- text measures the same on a desktop, in a
browser and in a test, and layout never depends on a toolkit being present.

Which makes the atlas a shipped artefact, not a build product, and gives it
this file's failure mode: a package that installs without it imports perfectly
and then raises the first time anything asks how wide a label is. That happened
-- the packer copied `*.py` from installed dependencies and nothing else -- so
its presence is now asserted rather than assumed.
"""
from __future__ import annotations

import json

import pytest

from emtk import font


def test_the_atlas_ships_beside_the_code():
    """Committed, not generated at install time: baking needs Qt, using it does not."""
    assert (font.ATLAS_DIR / "chrome.json").is_file()
    assert (font.ATLAS_DIR / "chrome.png").is_file()


def test_it_loads_and_reports_metrics_a_layout_can_use():
    """A zero advance lays every string on top of itself."""
    atlas = font.load_atlas()
    assert atlas.advance() > 0
    assert atlas.line_height > 0
    assert atlas.ascent > 0


def test_loading_is_cached_because_a_frame_asks_repeatedly():
    """The panel repaints every frame; re-reading the JSON each time is the cost."""
    assert font.load_atlas() is font.load_atlas()


def test_every_character_the_charset_promises_has_a_cell():
    """A missing glyph is a blank box at run time rather than an error here.

    Both faces, because the bold one has few callers and a face that is not
    baked renders silently as the regular one -- which looks like a styling
    decision rather than a missing artefact.
    """
    atlas = font.load_atlas()
    data = json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))
    for face in ("regular", "bold"):
        assert data["glyphs"][face], f"the {face} face declares no glyphs"
    for char in data["charset"]:
        assert atlas.covers(char), f"the charset promises {char!r} and the atlas lacks it"
        x, y, w, h = atlas.cell_of(char)
        assert w > 0 and h > 0, f"{char!r} has an empty cell"
    assert not atlas.covers("\u2764"), "a character outside the charset must not claim a cell"


def test_the_metrics_read_back_are_the_ones_that_were_baked_at_1x():
    """The reader and the baker have to agree, or every string is mismeasured.

    The atlas is baked at `scale`x and the reader hands back the 1x metrics --
    `advance` in the file is the supersampled number, `advance_1x` is the one
    layout uses. Confusing the two scales the whole interface by four.
    """
    atlas = font.load_atlas()
    data = json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))
    assert atlas.advance() == pytest.approx(float(data["advance_1x"]))
    assert atlas.line_height == pytest.approx(float(data["line_height_1x"]))
    # Rounded, not divided exactly: 26 texels at 4x is 6.5 and a glyph cell is
    # whole pixels. Within one pixel is the contract; equality is not.
    assert abs(data["advance"] / data["scale"] - data["advance_1x"]) <= 1


def test_an_unbaked_name_says_what_to_run_rather_than_returning_nothing():
    """The error is the only place the baking step is documented to a caller."""
    with pytest.raises(FileNotFoundError) as caught:
        font.load_atlas("no_such_face")
    assert "bake_chrome_atlas" in str(caught.value)


def test_the_atlas_writes_greek_and_the_signs_of_a_bound():
    """A FRET factor is γ, β, α or δ, and an unbounded side is −∞ / ∞."""
    import json
    import pathlib

    import emtk

    atlas = pathlib.Path(emtk.__file__).parent / "atlas" / "chrome.json"
    charset = json.loads(atlas.read_text())["charset"]
    assert all(c in charset for c in "αβγδτΔ∞−±≤≥→₀²")
