"""Small pictograms drawn from rectangles, sized to one character cell.

Why not a character
-------------------
The obvious way to draw an eye is to type one, and Unicode does have ``U+1F441
EYE`` -- but it is an **emoji**, so the only fonts carrying it on a typical
machine are colour ones, and the atlas rasterises monochrome masks. It comes out
blank. Everything else in the block that looks close (``◉ ◎ ⊙ ⦿``) is a circle:
recognisable as a *marker*, not as an eye, which is why the object list had been
making do with the letter ``o`` and a hyphen. They are legible and they say
nothing.

So the pictogram is drawn. The painter has one primitive that matters here --
:meth:`fill_rect` -- and at the size of a character an eye is about a dozen of
them, which is cheaper than the text it replaces.

How a glyph is written
----------------------
As a picture, in the source, so that changing it is editing the picture::

    OPEN_EYE = (
        "..#####..",
        ".#.....#.",
        "#..###..#",
        ...
    )

Each row is scaled to whole pixels and drawn as horizontal runs, so a run of
``#`` costs one rectangle rather than one per cell. Whole pixels matter: at
these sizes a fractional scale puts a one-pixel outline on a half-pixel
boundary, and the anti-aliasing turns it into a grey smear that reads as
blurred rather than small.
"""
from __future__ import annotations

from typing import Protocol

__all__ = ["OPEN_EYE", "CLOSED_EYE", "draw_glyph", "draw_eye"]


class Cell(Protocol):
    """Anything with the four numbers of a rectangle.

    Structural on purpose. ``emtk.layout.Rect`` is a plain tuple alias
    while the chrome's own ``Rect`` is a class with these attributes, and this
    module is called with the latter -- importing the former would name the
    wrong type and add a dependency it does not need.
    """

    x: float
    y: float
    w: float
    h: float


#: An open eye: almond outline, iris, pupil. Nine by seven, which is the
#: smallest that holds a round pupil inside a lid that still curves.
OPEN_EYE = (
    "..#####..",
    ".#.....#.",
    "#..###..#",
    "#..###..#",
    "#..###..#",
    ".#.....#.",
    "..#####..",
)

#: A closed eye: the lid drawn as the curve it becomes, with lashes. Not a
#: hyphen -- the curve is what makes it read as the *same* eye, shut, rather
#: than as an unrelated dash.
CLOSED_EYE = (
    ".........",
    ".........",
    "#.......#",
    ".#######.",
    "..#.#.#..",
    ".........",
    ".........",
)


def draw_glyph(p, rect: Cell, rows: tuple[str, ...], colour) -> None:
    """Draw a pixel picture centred in *rect*.

    Parameters
    ----------
    p : emtk.painter.Painter
        The surface to draw on.
    rect : Cell
        The cell to centre the picture in -- normally one character wide.
    rows : tuple of str
        The picture: ``#`` is ink, anything else is transparent. Rows must be
        equal length.
    colour : tuple
        RGBA, 0-255.
    """
    if not rows:
        return
    height = len(rows)
    width = max(len(row) for row in rows)
    if width <= 0:
        return

    # Whole pixels, and at least one: a half-pixel scale blurs a one-pixel
    # outline into grey. `floor` rather than `round` so the glyph never
    # overflows the cell it was measured for.
    scale = max(int(min(rect.w / width, rect.h / height)), 1)
    left = rect.x + (rect.w - width * scale) * 0.5
    top = rect.y + (rect.h - height * scale) * 0.5

    for index, row in enumerate(rows):
        y = top + index * scale
        start = None
        # One rectangle per *run* of ink, not per cell.
        for column in range(width + 1):
            ink = column < len(row) and row[column] == "#"
            if ink and start is None:
                start = column
            elif not ink and start is not None:
                p.fill_rect(
                    left + start * scale, y, (column - start) * scale, scale,
                    colour,
                )
                start = None


def draw_eye(p, rect: Cell, colour, *, shown: bool) -> None:
    """Draw the open or closed eye centred in *rect*."""
    draw_glyph(p, rect, OPEN_EYE if shown else CLOSED_EYE, colour)
