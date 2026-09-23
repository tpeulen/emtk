"""Bake emtk's interface font into a glyph atlas.

Why an atlas at all
-------------------
The in-viewport chrome -- the object panel, the sequence strip, the menus, the
mouse-mode block -- is moving off ``QPainter`` and onto GPU quads, because
rasterising it on the CPU costs `9.6 ms of a 21 ms frame` and forces a staleness
timer to hide the cost. Quads can draw rectangles without help; text needs
glyphs, and a glyph is a textured quad. So the font is rasterised **once, at
build time**, into one image with a table of where each character sits.

That is also what makes the chrome run where Qt does not. Baking needs a font
engine; *drawing* needs a texture and a lookup, which any target has.

What is baked
-------------
``QFont("Menlo")`` at :data:`FONT_PT`, in a regular and a **bold** face -- the
bold has exactly one caller, a menu's title row, and a face that is not baked is
a face that silently renders as the regular one.

The character set is printable ASCII plus the seven symbols the chrome actually
uses: ``▾ ▸ ▴`` for menus and disclosure markers, ``─`` for separators, and
``◀ ■ ▶ ▼`` for the movie transport. Enumerated rather than "some Unicode
range", because an atlas is a fixed-size image and a missing glyph is an empty
box at runtime rather than an error at build time.

Supersampling
-------------
Baked at :data:`SCALE`× the point size and sampled down, rather than once per
device pixel ratio. A 1× atlas is visibly soft on a HiDPI screen and a per-ratio
atlas means baking on a machine that has the ratio you are baking for -- which
CI does not. The cost is one image, and text metrics still come from the atlas
so layout does not depend on the scale.

Use
---
    QT_QPA_PLATFORM=offscreen python tools/bake_chrome_atlas.py

writes ``emtk/atlas/chrome.png`` and ``chrome.json``. Both ship --
``pyproject.toml``'s package data names ``atlas/*`` -- and both are committed,
so nobody needs Qt to *use* emtk. Baking is the one step that does.
"""
from __future__ import annotations

import json
import pathlib
import string
from collections import Counter

__all__ = ["CHARSET", "FONT_PT", "SCALE", "OUT_DIR", "bake"]

#: Point size of the chrome font. The size an application's chrome asks for; a mismatch
#: shows up as text that does not fit the rows it is laid out into.
FONT_PT = 8

#: Supersampling factor. See the module docstring.
SCALE = 4

#: Extra blank texels added to whatever the ink actually overhangs by.
#:
#: The padding itself is **measured**, not chosen -- see :func:`_padding`. This
#: is only the antialiasing margin on top of it, because a tight bounding box
#: describes the glyph's outline and the rasteriser puts partial coverage just
#: outside it.
AA_MARGIN = 2

#: Every character the chrome can draw.
#:
#: Printable ASCII, the symbols the chrome draws with, and **the accented
#: Latin letters**. The last of those is not decoration: the command line is a
#: text field, people type into it in their own language, and a character with
#: no glyph draws as *nothing at all* -- so typing "Zelldichte für Fläche"
#: produced "Zelldichte f r Fl che" with no error anywhere. That was reported
#: as "special chars like aou do not land visible in the cli".
#:
#: Latin-1 Supplement and Latin Extended-A between them cover the languages
#: this application is used in -- German, French, Spanish, the Nordic
#: languages, Polish, Czech, Hungarian, Turkish -- at about 250 extra cells,
#: which is a few kilobytes of atlas.
#:
#: Enumerated rather than "some Unicode range", still: an atlas is a
#: fixed-size image, and what is *not* in it has to be a decision someone made
#: rather than a discovery someone makes. Anything outside this set now draws a
#: visible placeholder instead of vanishing -- see `Atlas.cell`.
_SYMBOLS = "─▴▸▾◀■▶▼…"

#: What a scientific table writes: an unbounded side (``−∞``, ``∞``), a
#: comparison, an arrow, a sub/superscript index (``R₀``, ``τ²``). Greek is
#: added below: a FRET factor is γ, β, α or δ, and a missing glyph turns the
#: name into ``¤``.
_MATH = "∞−≤≥≈≠√∑∫∂∆→←↑↓⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉"

#: The placeholder for a character with no glyph. In the set by construction,
#: because a missing glyph that renders as another missing glyph is the bug
#: twice.
MISSING_GLYPH = "\u00a4"  # ¤, which no keyboard produces by accident

CHARSET: str = "".join(
    sorted(
        set(string.printable[:95])
        | set(_SYMBOLS)
        | {chr(c) for c in range(0x00A0, 0x0100)}   # Latin-1 Supplement
        | {chr(c) for c in range(0x0100, 0x0180)}   # Latin Extended-A
        | {"\u20ac", "\u2013", "\u2014", "\u2018", "\u2019", "\u201c", "\u201d"}
        | {chr(c) for c in range(0x0391, 0x03AA) if c != 0x03A2}   # Greek capitals
        | {chr(c) for c in range(0x03B1, 0x03CA)}                   # Greek small
        | set(_MATH)
    )
)

#: Where the atlas lands, inside the package so it ships.
OUT_DIR = pathlib.Path(__file__).resolve().parents[1] / "emtk" / "atlas"


def _face(bold: bool, scale: int | None = None):
    """Return the chrome font, at :data:`SCALE`× size.

    Parameters
    ----------
    bold : bool
        Whether to return the bold face.

    Returns
    -------
    QtGui.QFont
    """
    from qtpy import QtGui

    font = QtGui.QFont("Menlo")
    font.setStyleHint(QtGui.QFont.Monospace)
    font.setPointSize(FONT_PT * (SCALE if scale is None else scale))
    font.setBold(bold)
    return font


def _padding(metrics: dict, advance: int, charset: str) -> int:
    """Return the blank margin each cell needs, in texels.

    Parameters
    ----------
    metrics : dict
        ``{face name: QFontMetrics}``.
    advance : int
        The monospaced advance every cell is sized from.
    charset : str
        The characters actually being baked. **Not** the module's `CHARSET`:
        that is what was asked for, and a character the font does not cover
        can report an ink box of any size at all. Measuring the wanted set
        rather than the covered one sized one cell at 199978 texels, which
        fails as a painter error three steps later.

    Returns
    -------
    int
        Half-width of the blank border, including :data:`AA_MARGIN`.

    Notes
    -----
    A monospaced font's *ink* is not bounded by its advance. ``─`` -- the
    separator -- starts a texel to the **left** of the pen and ends past it,
    because a box-drawing character is meant to join the one beside it; ``#``
    overhangs too, and both overhang further in the bold face than the regular
    one. Packed flush, that ink lands in the neighbouring cell, and at runtime
    a glyph quad samples a sliver of the wrong glyph along its edge.

    Measured across **both** faces rather than assumed, because sizing the
    padding from the regular face is exactly the mistake that left bold ``#``
    and ``─`` still touching their borders.
    """
    overhang = 0
    for face_metrics in metrics.values():
        height = face_metrics.height()
        ascent = face_metrics.ascent()
        for char in charset:
            ink = face_metrics.tightBoundingRect(char)
            overhang = max(overhang, -ink.x(), ink.x() + ink.width() - advance)
            # Vertically too. Measuring only the horizontal overhang was
            # enough for ASCII and is not for accented capitals: `Ş` hangs
            # its cedilla below the line box and `Ů` puts a ring above the
            # ascent, and both landed on the cell border -- where a glyph
            # quad samples a sliver of its neighbour.
            overhang = max(
                overhang,
                -(ascent + ink.y()),
                (ink.y() + ink.height()) - (height - ascent) - ascent,
            )
    return int(max(overhang, 0)) + AA_MARGIN


def bake(out_dir: pathlib.Path | None = None) -> dict:
    """Rasterise both faces into one atlas and write it out.

    Parameters
    ----------
    out_dir : pathlib.Path, optional
        Where to write. Defaults to :data:`OUT_DIR`.

    Returns
    -------
    dict
        The metrics written as ``chrome.json``: ``scale``, ``font_pt``,
        ``cell``, ``glyphs`` (per face, per character, its cell and advance)
        and the shared ``ascent`` / ``descent`` / ``line_height``.

    Notes
    -----
    A fixed grid rather than a tight pack. There are fewer than 210 cells and
    the font is monospaced, so the wasted texels are not worth a packer -- and a
    grid means a glyph's cell can be computed from its index, which keeps the
    runtime lookup a multiply rather than a table read.
    """
    from qtpy import QtCore, QtGui, QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert app is not None  # a collected QApplication aborts the next QImage

    out_dir = pathlib.Path(out_dir or OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    faces = {"regular": _face(False), "bold": _face(True)}
    metrics = {name: QtGui.QFontMetrics(font) for name, font in faces.items()}

    # One cell size for every glyph of both faces: the widest advance and the
    # tallest line. Bold is a little wider than regular, so taking the max of
    # the two is what stops a bold glyph being clipped by a cell sized for the
    # regular face.
    # The charset is what we *want*; this is what the font actually has. A
    # character the font does not cover measures zero and would bake an empty
    # cell -- indistinguishable at runtime from the invisible-glyph bug this
    # charset was widened to fix. So they are dropped here, and **named**: a
    # dropped character is a decision, and one nobody is told about is how the
    # gap gets rediscovered by a user typing their own language.
    counted = Counter(
        m.horizontalAdvance(c) for m in metrics.values() for c in CHARSET
    )
    advance = counted.most_common(1)[0][0]
    dropped = sorted(
        c for c in CHARSET
        if any(m.horizontalAdvance(c) != advance for m in metrics.values())
    )
    charset = "".join(c for c in CHARSET if c not in set(dropped))
    if dropped:
        names = " ".join(f"U+{ord(c):04X}" for c in dropped)
        print(f"  {len(dropped)} character(s) the font does not cover, dropped: {names}")
    if len(charset) < 95:
        # Losing ASCII means the font is wrong, not the charset.
        raise RuntimeError(
            f"only {len(charset)} characters survived the advance check; "
            "the chrome font is not monospaced at all"
        )
    pad = _padding(metrics, advance, charset)
    cell_w = advance + 2 * pad
    cell_h = max(m.height() for m in metrics.values()) + 2 * pad
    ascent = max(m.ascent() for m in metrics.values())

    columns = 16
    rows_per_face = (len(charset) + columns - 1) // columns
    # One extra row for the solid block; see below.
    total_rows = rows_per_face * len(faces) + 1

    image = QtGui.QImage(
        cell_w * columns, cell_h * total_rows, QtGui.QImage.Format_ARGB32
    )
    image.fill(QtCore.Qt.transparent)

    # A fully opaque block, so a plain rectangle is a textured quad that happens
    # to sample white. Without it the chrome needs two pipelines -- one for
    # rectangles and one for glyphs -- or a per-vertex "is this text" flag and a
    # branch in the fragment shader. With it there is one pipeline, one vertex
    # format and one draw call for the whole panel.
    solid_y = rows_per_face * len(faces) * cell_h
    solid = [0, solid_y, cell_w, cell_h]

    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
    painter.fillRect(
        solid[0], solid[1], solid[2], solid[3], QtGui.QColor(255, 255, 255, 255)
    )
    painter.setPen(QtGui.QColor(255, 255, 255, 255))

    glyphs: dict[str, dict] = {}
    try:
        for face_index, (name, font) in enumerate(faces.items()):
            painter.setFont(font)
            face_metrics = metrics[name]
            row_offset = face_index * rows_per_face
            table: dict[str, list] = {}
            for index, char in enumerate(charset):
                column, row = index % columns, index // columns
                x = column * cell_w
                y = (row_offset + row) * cell_h
                # The pen sits at (pad, pad + ascent) inside the cell, the same
                # for every glyph -- so a caller places a quad at
                # ``(pen_x - pad, baseline - ascent - pad)`` with the cell's
                # size, and needs no per-glyph bearing.
                painter.drawText(x + pad, y + pad + ascent, char)
                table[char] = [x, y, cell_w, cell_h,
                               face_metrics.horizontalAdvance(char)]
            glyphs[name] = table
    finally:
        painter.end()

    image.save(str(out_dir / "chrome.png"))

    # Metrics at the size the panel is *laid out* in, not the size it was baked
    # at. Font metrics do not scale linearly -- hinting and rounding make Menlo
    # advance 8 px at 10 pt and 34 at 40 pt, so dividing the baked metric by the
    # supersample gives 8.5 and every string in the panel runs 6% wide. The
    # layout has to agree with the toolkit it shares a window with.
    one_x = QtGui.QFontMetrics(_face(False, scale=1))
    record = {
        "font_pt": FONT_PT,
        "scale": SCALE,
        "pad": pad,
        "cell": [cell_w, cell_h],
        "advance": advance,
        "advance_1x": one_x.horizontalAdvance("M"),
        "line_height_1x": one_x.height(),
        "ascent_1x": one_x.ascent(),
        "ascent": ascent,
        "descent": max(m.descent() for m in metrics.values()),
        "line_height": cell_h,
        "columns": columns,
        "charset": charset,
        "glyphs": glyphs,
        "solid": solid,
        "size": [image.width(), image.height()],
    }
    (out_dir / "chrome.json").write_text(
        json.dumps(record, indent=1, sort_keys=True), encoding="utf-8"
    )
    return record


if __name__ == "__main__":  # pragma: no cover - a build step
    _record = bake()
    print(
        f"{len(_record['charset'])} glyphs x {len(_record['glyphs'])} faces, "
        f"cell {_record['cell'][0]}x{_record['cell'][1]} at {SCALE}x -> {OUT_DIR}"
    )
