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

import math
from collections.abc import Sequence
from contextlib import contextmanager

from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from ..painter import line as _painter_line
from ..painter import polyline as _painter_polyline
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
_MINOR_GRID_COLOUR = (255, 255, 255, 9)
_TICK_TEXT = (160, 165, 175)
_AXIS_LINE = (110, 115, 125)


def column_extremes_index(px, py, run_id=None):
    """Which samples of a pixel path draw the same pixels: sorted indices into it.

    A trace far denser than the screen -- a 4096-channel decay in a plot 700 px
    wide -- puts many samples in each pixel column, and stroking every one of
    them is most of a frame. Where x runs left to right and a column holds two
    samples or more, each column of each run (*run_id*: equal for samples
    joined by a line) keeps its lowest and highest sample, in sample order, and
    every run keeps its two ends: the stroke spans each column's full vertical
    extent and stays within a pixel of the original path. A path that doubles
    back in x, or is sparser than that, is kept whole.
    """
    import numpy as np  # noqa: PLC0415

    px = np.asarray(px, dtype=float)
    py = np.asarray(py, dtype=float)
    count = px.size
    everything = np.arange(count)
    if count < 8:
        return everything
    columns = np.floor(px).astype(np.int64)
    if np.any(np.diff(columns) < 0):
        return everything
    runs = np.zeros(count, dtype=np.int64) if run_id is None else np.asarray(run_id, np.int64)
    key = runs * (int(columns.max() - columns.min()) + 2) + (columns - columns.min())
    starts = np.concatenate(([0], np.flatnonzero(np.diff(key)) + 1))
    if starts.size * 2 >= count:
        return everything  # under two samples a column: nothing to gain
    ends = np.concatenate((starts[1:], [count])) - 1
    order = np.lexsort((py, key))  # by group, then y: each group stays contiguous
    # A column's lowest and highest sample, in sample order; a run's first and
    # last sample, so it still starts and ends where it did.
    run_edges = np.flatnonzero(np.diff(runs)) if run_id is not None else np.zeros(0, int)
    edges = np.concatenate(([0, count - 1], run_edges, run_edges + 1))
    return np.unique(np.concatenate((order[starts], order[ends], edges)))


def column_extremes(px, py):
    """:func:`column_extremes_index` applied: the kept vertices as an ``(n, 2)`` array."""
    import numpy as np  # noqa: PLC0415

    px = np.asarray(px, dtype=float)
    py = np.asarray(py, dtype=float)
    keep = column_extremes_index(px, py)
    return np.column_stack((px[keep], py[keep]))


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
        #: Draw the y tick *numbers* (the gridlines stay). ImPlot's
        #: ``ImPlotAxisFlags_NoTickLabels``: a density plot whose height is
        #: only meaningful relative to its neighbours reads cleaner without them.
        self.show_y_tick_labels = True
        #: Roughly how many ticks (and gridlines) each axis gets. Four suits a
        #: caption-sized plot; an analysis panel scales it with its size.
        self.x_tick_target = 4
        self.y_tick_target = 4
        #: ``callable(painter, plot)`` drawn after the gridlines and before the
        #: series, inside the clip, with both axes already mapped onto the box:
        #: what shades a span of the data (a fit range) belongs *under* the
        #: curves it marks, not over them.
        self.underlays: list = []
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
        dash: tuple[float, float] | None = None,
    ) -> None:
        """Add a polyline series. Extends both axes' auto-fit range.

        ``dash`` is an ``(on, off)`` pattern in pixels. ImPlot has no dashed
        lines; a plot that has to tell a *prior* from a *posterior* of the same
        colour, or an excluded stretch of a trace from the included one, needs
        one, and a second colour would claim a second quantity.
        """
        colour = colour or self._auto_colour()
        self._x_axis.fit(xs)
        self._y_axis.fit(ys)
        self._lines.append({"label": label, "xs": xs, "ys": ys, "colour": colour,
                            "width": width, "dash": dash})

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
            for underlay in self.underlays:
                underlay(p, self)
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
        # A log axis also gets its 2..9 lines per decade, fainter: without
        # them a decade is an empty band and a value in it cannot be read.
        for v in self._y_axis.minor_ticks():
            p.fill_rect(x, self._y_axis.to_pixels(v), w, 1.0, _MINOR_GRID_COLOUR)
        for v in self._x_axis.minor_ticks():
            p.fill_rect(self._x_axis.to_pixels(v), y, 1.0, h, _MINOR_GRID_COLOUR)
        for v in self._y_axis.ticks(self.y_tick_target):
            py = self._y_axis.to_pixels(v)
            p.fill_rect(x, py, w, 1.0, _GRID_COLOUR)
        for v in self._x_axis.ticks(self.x_tick_target):
            px = self._x_axis.to_pixels(v)
            p.fill_rect(px, y, 1.0, h, _GRID_COLOUR)

    def _draw_tick_labels(self, p) -> None:
        """The y ticks' numbers, in the margin left of the box. Callers that
        draw a plot flush to a window edge get nothing -- reserve the margin,
        as :mod:`emtk.implot` does."""
        if not self.show_y_tick_labels:
            return
        x = self.x
        for v in self._y_axis.ticks(self.y_tick_target):
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
        dash = series.get("dash")
        if not dash:
            # Complete finite runs go to the painter's batch seam, mapped to
            # pixels in one array operation. A missing sample breaks a run
            # instead of inventing a connecting line.
            import numpy as np  # noqa: PLC0415

            px = self._x_axis.to_pixels_array(np.asarray(xs[:n], dtype=float))
            py = self._y_axis.to_pixels_array(np.asarray(ys[:n], dtype=float))
            keep = np.flatnonzero(np.isfinite(px) & np.isfinite(py))
            if keep.size < 2:
                return
            # A run is a stretch without a missing sample; a trace on a log axis
            # that touches zero (a prompt's background) breaks into many.
            run_id = np.concatenate(([0], np.cumsum(np.diff(keep) != 1)))
            chosen = column_extremes_index(px[keep], py[keep], run_id)
            keep, run_id = keep[chosen], run_id[chosen]
            runs = [np.column_stack((px[part], py[part]))
                    for part in np.split(keep, np.flatnonzero(np.diff(run_id)) + 1)
                    if part.size > 1]
            batch = getattr(p, "polylines", None)
            if callable(batch):
                batch(runs, width, colour)
            else:
                for points in runs:
                    _painter_polyline(p, points, width, colour)
            return
        # The dash phase carries across vertices, so a pattern reads as one
        # pattern along the curve rather than restarting at every sample --
        # which on a densely sampled curve would draw it solid.
        phase = 0.0
        # A non-finite sample is a gap: the segments either side of it are not
        # drawn, rather than joining its neighbours across data that is not there.
        prev = None
        for i in range(n):
            if not (math.isfinite(xs[i]) and math.isfinite(ys[i])):
                prev = None
                continue
            cur = (self._x_axis.to_pixels(xs[i]), self._y_axis.to_pixels(ys[i]))
            if prev is not None:
                if dash:
                    phase = _dashed_segment(p, prev, cur, width, colour, dash, phase)
                else:
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
        # One row per name: a line drawn with markers is a line series and a
        # scatter series under the same label, and is one thing to the reader.
        seen: set[str] = set()
        entries = [(label, colour) for label, colour in entries
                   if not (label in seen or seen.add(label))]
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


def _dashed_segment(p, a, b, width, colour, dash, phase) -> float:
    """Draw ``a -> b`` as dashes and return the pattern phase at ``b``.

    Parameters
    ----------
    p : Painter
        Target.
    a, b : tuple of float
        Segment end points, in pixels.
    width : float
        Line width.
    colour : tuple
        RGBA.
    dash : tuple of float
        ``(on, off)`` lengths in pixels.
    phase : float
        Distance already travelled into the pattern at ``a``.

    Returns
    -------
    float
        The phase at ``b``, to continue the pattern on the next segment.
    """
    on, off = max(float(dash[0]), 0.5), max(float(dash[1]), 0.0)
    period = on + off
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 0.0:
        return phase
    ux, uy = dx / length, dy / length
    t = 0.0
    while t < length:
        pos = (phase + t) % period
        if pos < on:
            run = min(on - pos, length - t)
            _painter_line(p, a[0] + ux * t, a[1] + uy * t,
                          a[0] + ux * (t + run), a[1] + uy * (t + run), width, colour)
        else:
            run = min(period - pos, length - t)
        t += run
    return (phase + length) % period


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
