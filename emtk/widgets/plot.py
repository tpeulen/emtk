"""``Plot`` -- a plot area with axes, gridlines, a legend, and the item types.

The call shape tracks ``implot.h``'s ``BeginPlot``/``PlotLine``/``EndPlot``
(``junk/implot``), adapted to a context manager since Python has no
destructor to lean on for the implicit ``EndPlot``:

>>> with begin_plot(painter, x, y, w, h) as plot:
...     plot.line("fps", xs, ys)
...     plot.hline(60.0, colour=(150, 240, 175))

Unlike the reference, an item does not draw itself the moment it is called --
:meth:`Plot.line`/:meth:`Plot.scatter` record the series and extend the
auto-fit axes; the frame, gridlines, items and legend are all drawn together
when the ``with`` block exits (:meth:`Plot.draw`, called from
:meth:`Plot.__exit__`). ImPlot can draw incrementally because its axes are
already fit from the *previous* frame; emtk's plots are rebuilt from
scratch each time they are drawn, so there is no previous frame's range to
draw against and every item must be known before the range is.
"""
from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager

from ..painter import line as _painter_line
from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from .axis import Axis
from .markers import draw_marker

__all__ = ["Plot", "begin_plot"]

#: ImPlot's default categorical palette ("Deep", `implot.cpp:509`) -- ten
#: colours, distinguishable and not primary-saturated, so plotted series read
#: as data rather than as a traffic light.
DEEP_PALETTE: tuple[tuple[int, int, int], ...] = (
    (76, 114, 176), (221, 132, 82), (85, 168, 104), (196, 78, 82),
    (129, 114, 179), (147, 120, 96), (218, 139, 195), (140, 140, 140),
    (204, 185, 116), (100, 181, 205),
)

_FRAME_BG = (0, 0, 0, 60)
_GRID_COLOUR = (255, 255, 255, 20)
_TICK_TEXT = (160, 165, 175)
_AXIS_LINE = (110, 115, 125)


class Plot:
    """A plot area, built up by :meth:`line`/:meth:`scatter`/:meth:`hline`
    then drawn once by :meth:`draw` (or on exit, if used as a context
    manager -- see :func:`begin_plot`).

    Parameters
    ----------
    x, y, w, h : float
        The plot's box, in the same painter-pixel coordinates as every other
        emtk control.
    x_range, y_range : (float, float), optional
        Fixed axis ranges. Omitted axes auto-fit to whatever data is added.
    show_ticks : bool, optional
        Draw tick labels and gridlines. Off by default for the small,
        caption-sized plots the chrome mostly wants (matching how the nerd
        graphs looked before this port); a larger analysis plot turns it on.
    """

    def __init__(
        self,
        x: float, y: float, w: float, h: float,
        x_range: tuple[float, float] | None = None,
        y_range: tuple[float, float] | None = None,
        show_ticks: bool = False,
        show_legend: bool = True,
    ) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h
        self.show_ticks = show_ticks
        #: Draw the key for the labelled series. On by default, because a plot
        #: with several series and no key is unreadable -- but a plot two
        #: inches wide has no room for one, and the key then covers the curves
        #: it is naming. Callers that small turn it off.
        self.show_legend = show_legend
        #: Run the y-axis downwards: its minimum at the top, as an image's
        #: row index does. Everything placed through the axis follows.
        self.y_inverted = False
        self._x_axis = Axis(*(x_range or (None, None)))
        self._y_axis = Axis(*(y_range or (None, None)))
        self._lines: list[dict] = []
        self._scatters: list[dict] = []
        self._hlines: list[tuple[float, tuple, str | None]] = []
        self._next_colour = 0

    def _auto_colour(self) -> tuple[int, int, int]:
        colour = DEEP_PALETTE[self._next_colour % len(DEEP_PALETTE)]
        self._next_colour += 1
        return colour

    def line(
        self,
        label: str,
        xs: Sequence[float],
        ys: Sequence[float],
        colour: tuple | None = None,
        width: float = 1.5,
    ) -> None:
        """Add a polyline series. Extends both axes' auto-fit range."""
        colour = colour or self._auto_colour()
        self._x_axis.fit(xs)
        self._y_axis.fit(ys)
        self._lines.append({"label": label, "xs": xs, "ys": ys, "colour": colour, "width": width})

    def scatter(
        self,
        label: str,
        xs: Sequence[float],
        ys: Sequence[float],
        colour: tuple | None = None,
        marker: str = "circle",
        radius: float = 2.5,
    ) -> None:
        """Add a scatter series. Extends both axes' auto-fit range."""
        colour = colour or self._auto_colour()
        self._x_axis.fit(xs)
        self._y_axis.fit(ys)
        self._scatters.append({
            "label": label, "xs": xs, "ys": ys,
            "colour": colour, "marker": marker, "radius": radius,
        })

    def hline(self, value: float, colour: tuple, label: str | None = None) -> None:
        """A horizontal reference line at *value* in plot (not pixel) units.

        Drawn last, over the series -- the same ordering
        ``_paint_nerd_guides`` used and for the same reason: drawn underneath,
        a guide is hidden by the very data it exists to be read against.
        Does **not** extend the Y auto-fit range; a guide line at 60 fps
        should not stretch an otherwise-quiet graph up to 60 by itself.
        """
        self._hlines.append((value, colour, label))

    def draw(self, p) -> None:
        """Render the frame, gridlines, items, guides and legend."""
        x, y, w, h = self.x, self.y, self.w, self.h
        self._x_axis.set_pixels(x, x + w)
        if self.y_inverted:
            self._y_axis.set_pixels(y, y + h)  # top -> Min, as screen rows run.
        else:
            self._y_axis.set_pixels(y + h, y)  # bottom -> Min, top -> Max: inverts Y.

        p.fill_rect(x, y, w, h, _FRAME_BG)
        # The tick *labels* sit in the margin to the left of the box, so they
        # have to be drawn before the clip that bounds the box -- inside it
        # they are clipped away and the plot draws gridlines with nothing to
        # read them by.
        if self.show_ticks:
            self._draw_tick_labels(p)
        p.push_clip(x, y, w, h)
        try:
            if self.show_ticks:
                self._draw_gridlines(p)
            for series in self._lines:
                self._draw_line(p, series)
            for series in self._scatters:
                self._draw_scatter(p, series)
            for value, colour, _label in self._hlines:
                py = self._y_axis.to_pixels(value)
                p.fill_rect(x, py, w, 1.0, colour)
        finally:
            p.pop_clip()
        p.stroke_rect(x, y, w, h, _AXIS_LINE)
        self._draw_legend(p)

    def _draw_gridlines(self, p) -> None:
        x, y, w, h = self.x, self.y, self.w, self.h
        for v in self._y_axis.ticks():
            py = self._y_axis.to_pixels(v)
            p.fill_rect(x, py, w, 1.0, _GRID_COLOUR)
        for v in self._x_axis.ticks():
            px = self._x_axis.to_pixels(v)
            p.fill_rect(px, y, 1.0, h, _GRID_COLOUR)

    def _draw_tick_labels(self, p) -> None:
        """The y ticks' numbers, in the margin left of the box. Callers that
        draw a plot flush to a window edge get nothing -- reserve the margin,
        as :mod:`emtk.implot` does."""
        x = self.x
        for v in self._y_axis.ticks():
            py = self._y_axis.to_pixels(v)
            p.text(x - 34.0, py - 6.0, 30.0, 12.0, ALIGN_RIGHT | ALIGN_VCENTER,
                   self.format_tick(v), _TICK_TEXT)

    def format_tick(self, v: float) -> str:
        """How a tick value is spelled. Overridden by a log axis, where the
        stored value is the exponent and the reader wants the sample."""
        return f"{v:g}"

    def _draw_line(self, p, series: dict) -> None:
        xs, ys, colour, width = series["xs"], series["ys"], series["colour"], series["width"]
        n = min(len(xs), len(ys))
        if n < 2:
            if n == 1:
                px, py = self._x_axis.to_pixels(xs[0]), self._y_axis.to_pixels(ys[0])
                draw_marker(p, "circle", px, py, width, colour)
            return
        prev = (self._x_axis.to_pixels(xs[0]), self._y_axis.to_pixels(ys[0]))
        for i in range(1, n):
            cur = (self._x_axis.to_pixels(xs[i]), self._y_axis.to_pixels(ys[i]))
            _painter_line(p, prev[0], prev[1], cur[0], cur[1], width, colour)
            prev = cur

    def _draw_scatter(self, p, series: dict) -> None:
        xs, ys = series["xs"], series["ys"]
        colour, marker, radius = series["colour"], series["marker"], series["radius"]
        for i in range(min(len(xs), len(ys))):
            px, py = self._x_axis.to_pixels(xs[i]), self._y_axis.to_pixels(ys[i])
            draw_marker(p, marker, px, py, radius, colour)

    def _draw_legend(self, p) -> None:
        """Draw the key, unless this plot was asked not to have one."""
        if not self.show_legend:
            return
        entries = [(s["label"], s["colour"]) for s in self._lines if s["label"]]
        entries += [(s["label"], s["colour"]) for s in self._scatters if s["label"]]
        if not entries:
            return
        swatch = 8.0
        row_h = p.line_height()
        pad = 3.0
        width = max(p.text_width(label) for label, _c in entries) + swatch + pad * 3.0
        height = row_h * len(entries) + pad * 2.0
        lx = self.x + self.w - width - pad
        ly = self.y + pad
        p.fill_rect(lx, ly, width, height, (20, 22, 26, 200))
        for i, (label, colour) in enumerate(entries):
            row_y = ly + pad + i * row_h
            p.fill_rect(lx + pad, row_y + (row_h - swatch) * 0.5, swatch, swatch, colour)
            p.text(lx + pad * 2.0 + swatch, row_y, width - swatch - pad * 3.0, row_h,
                   ALIGN_LEFT | ALIGN_VCENTER, label, _TICK_TEXT)

    # -- context manager -----------------------------------------------

    def __enter__(self) -> "Plot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.draw(self._painter)


def begin_plot(
    p,
    x: float, y: float, w: float, h: float,
    x_range: tuple[float, float] | None = None,
    y_range: tuple[float, float] | None = None,
    show_ticks: bool = False,
) -> Plot:
    """Return a :class:`Plot` that draws itself against *p* on ``__exit__``.

    >>> with begin_plot(painter, 10, 10, 200, 60) as plot:
    ...     plot.line("frame time", xs, ys)
    """
    plot = Plot(x, y, w, h, x_range=x_range, y_range=y_range, show_ticks=show_ticks)
    plot._painter = p
    return plot
