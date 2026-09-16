"""Scatter marker shapes, ported from ``implot_items.cpp``'s ``ImPlotMarker_*``.

Four of ImPlot's ten marker shapes -- circle, square, diamond, cross -- cover
what a emtk plot needs today and are each one shape simpler than the rest
(triangle-up/down, plus, asterisk are straightforward additions later; see
the module docstrings. Circle reuses
:func:`~emtk.style.disc` -- the same scan-converted circle every
other round control in the toolkit already draws -- rather than a second
implementation; the other three are one or two
:meth:`~emtk.painter.Painter.fill_triangle`/
:func:`~emtk.painter.line` calls each.
"""
from __future__ import annotations

from ..painter import line as _painter_line
from ..style import disc as _disc

__all__ = ["MARKERS", "draw_marker"]


def _circle(p, cx: float, cy: float, r: float, colour) -> None:
    _disc(p, cx, cy, r, colour)


def _square(p, cx: float, cy: float, r: float, colour) -> None:
    p.fill_rect(cx - r, cy - r, 2.0 * r, 2.0 * r, colour)


def _diamond(p, cx: float, cy: float, r: float, colour) -> None:
    top, bottom = (cx, cy - r), (cx, cy + r)
    left, right = (cx - r, cy), (cx + r, cy)
    p.fill_triangle(top, right, bottom, colour)
    p.fill_triangle(top, bottom, left, colour)


def _cross(p, cx: float, cy: float, r: float, colour) -> None:
    # Two diagonals rather than the axis-aligned plus, so a cross marker
    # reads as distinct from a data point drawn as a small square.
    w = max(r * 0.35, 1.0)
    _painter_line(p, cx - r, cy - r, cx + r, cy + r, w, colour)
    _painter_line(p, cx - r, cy + r, cx + r, cy - r, w, colour)


#: Name -> draw function, ``(painter, cx, cy, radius, colour) -> None``.
MARKERS = {
    "circle": _circle,
    "square": _square,
    "diamond": _diamond,
    "cross": _cross,
}


def draw_marker(p, name: str, cx: float, cy: float, r: float, colour) -> None:
    """Draw marker *name* at (*cx*, *cy*). Falls back to a circle if unknown."""
    MARKERS.get(name, _circle)(p, cx, cy, r, colour)
