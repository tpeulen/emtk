"""The plot's "A" button: fit the view to the data again.

Every emtk plot keeps an *auto-range* flag per axis. It is on until the user
pans, zooms or wheels the view; while any axis is off, a small boxed **A**
sits in the lower-left corner of the plot area, and clicking it turns
auto-range back on for every axis and refits -- the button pyqtgraph's plots
carry, which users reach for without being told. Once the view follows its
data again the button goes away.

Both plot stacks draw it through this module, so it looks and sits the same
everywhere: :mod:`emtk.implot` (immediate mode, flag
``FLAGS_NO_AUTO_RANGE_BUTTON`` to opt out) and any retained canvas built on
:class:`emtk.widgets.plot.Plot` (an application's own retained plot panel,
which calls :func:`button_rect`, :func:`draw` and :func:`contains`). The module knows
nothing about axes; it only places, draws and hit-tests the button and owns
its tooltip.

Differences from pyqtgraph, deliberately: the button shows whenever the view is
not auto-ranged, not only while the pointer is over the plot (a hidden button
is one nobody finds), and it sits *inside* the plot area, so it is never cut
off by a narrow axis gutter.
"""

from __future__ import annotations

from ..i18n import mark, tr
from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER

__all__ = [
    "INSET",
    "SIZE",
    "TOOLTIP",
    "button_rect",
    "contains",
    "draw",
    "draw_tooltip",
    "tooltip",
]

#: Side of the square button, in logical pixels (pyqtgraph's is 14).
SIZE = 15.0
#: Gap between the button and the plot area's left and bottom edges.
INSET = 3.0
#: The tooltip's source string (translated by :func:`tooltip`).
TOOLTIP = mark("Auto-range: fit the view to the data", domain="emtk")

_FILL = (20, 22, 28, 200)
_FILL_HOVERED = (66, 150, 250, 230)
_EDGE = (150, 150, 160, 230)
_TEXT = (235, 235, 240)


def tooltip() -> str:
    """The button's tooltip in the current language."""
    return tr(TOOLTIP, domain="emtk")


def button_rect(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    """``(x, y, w, h)`` of the button inside a plot area at ``(x, y, w, h)``.

    Lower-left, inset from both edges; shrunk (never below 8 px) when the plot
    area is too small to hold the full size, so it never pokes outside.
    """
    side = max(min(SIZE, w - 2.0 * INSET, h - 2.0 * INSET), 8.0)
    return (x + INSET, y + h - INSET - side, side, side)


def contains(rect, px: float, py: float) -> bool:
    """Whether the point ``(px, py)`` is on the button at *rect*."""
    if rect is None:
        return False
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h


def draw(painter, rect, hovered: bool = False) -> None:
    """Draw the boxed "A" at *rect*; lit while *hovered*."""
    x, y, w, h = rect
    painter.stroke_rect(x, y, w, h, _EDGE, _FILL_HOVERED if hovered else _FILL)
    painter.text(x, y, w, h, ALIGN_CENTER, "A", _TEXT)


def draw_tooltip(painter, rect, bounds) -> None:
    """Draw the tooltip beside the button at *rect*, kept inside *bounds*.

    For hosts with no frame-level tooltip (a retained canvas in a Qt widget);
    an immediate-mode plot hands the text to its context instead.
    """
    text = tooltip()
    pad = 5.0
    row = float(painter.line_height())
    width = painter.text_width(text) + 2.0 * pad
    height = row + 2.0 * pad
    bx, by, bw, bh = bounds
    x = min(rect[0] + rect[2] + 4.0, bx + bw - width)
    y = rect[1] + rect[3] - height
    x = max(x, bx)
    y = max(min(y, by + bh - height), by)
    painter.stroke_rect(x, y, width, height, _EDGE, (20, 20, 20, 240))
    painter.text(x + pad, y + pad, width - 2.0 * pad, row, ALIGN_LEFT | ALIGN_VCENTER, text, _TEXT)
