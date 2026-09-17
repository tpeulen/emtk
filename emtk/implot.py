"""``emtk.implot`` -- ImPlot's call shape, over :class:`emtk.widgets.plot.Plot`.

:mod:`emtk.widgets.plot` already draws the picture: axes that auto-fit, ticks,
gridlines, a legend and ImPlot's own Deep palette. What it does not have is
ImPlot's *shape*. It is a control -- it takes a painter and a box -- while
application code inside an immediate-mode frame has neither in hand, and is
written like this:

.. code-block:: c++

    if (ImPlot::BeginPlot("##IntensityTrace", size, ImPlotFlags_NoTitle)) {
        ImPlot::SetupAxes("time / s", "rate / kHz");
        ImPlot::SetupAxisLimits(ImAxis_X1, t0, t1, ImPlotCond_Always);
        ImPlot::PlotLine("ch0", xs.data(), ys.data(), n);
        ImPlot::EndPlot();
    }

which ports, one line at a time, to:

.. code-block:: python

    if implot.begin_plot("##IntensityTrace", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes("time / s", "rate / kHz")
        implot.setup_axis_limits(implot.AXIS_X1, t0, t1, implot.COND_ALWAYS)
        implot.plot_line("ch0", xs, ys)
        implot.end_plot()

The box comes from the cursor and the content region, and the space is
reserved with ``dummy()`` on ``end_plot`` -- so a plot participates in layout
like any other widget, and ``same_line()`` after one works.

Like the reference, this module keeps the current plot in module state rather
than handing back an object: that is what lets ``PlotLine`` be a free function
between ``BeginPlot`` and ``EndPlot``, and what lets ported code read as the
C++ did. Unlike the reference, nothing is drawn until ``end_plot`` -- emtk's
plots are rebuilt from scratch each frame, so there is no previous frame's
range to draw against and every series must be known before the range is.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import NamedTuple

from . import im_core as _core
from . import im_widgets as _w
from .painter import ALIGN_CENTER as _PAINT_CENTRE
from .painter import ALIGN_LEFT as _PAINT_LEFT
from .widgets.plot import DEEP_PALETTE, Plot

__all__ = [
    "AXIS_X1", "AXIS_X2", "AXIS_X3", "AXIS_Y1", "AXIS_Y2", "AXIS_Y3",
    "COND_NONE", "COND_ALWAYS", "COND_ONCE",
    "FLAGS_NONE", "FLAGS_NO_TITLE", "FLAGS_NO_LEGEND", "FLAGS_NO_MOUSE_TEXT",
    "FLAGS_NO_INPUTS", "FLAGS_NO_MENUS", "FLAGS_NO_BOX_SELECT",
    "FLAGS_CANVAS_ONLY", "FLAGS_EQUAL",
    "SCALE_LINEAR", "SCALE_LOG10", "SCALE_SYMLOG",
    "AXIS_FLAGS_NONE", "AXIS_FLAGS_NO_LABEL", "AXIS_FLAGS_NO_TICK_LABELS",
    "MARKER_NONE", "MARKER_CIRCLE", "MARKER_SQUARE", "MARKER_DIAMOND", "MARKER_CROSS",
    "INF_LINES_HORIZONTAL", "BARS_HORIZONTAL",
    "HEATMAP_NONE", "HEATMAP_COL_MAJOR",
    "DEEP_PALETTE", "VIRIDIS_COLORMAP",
    "begin_plot", "end_plot", "setup_axes", "setup_axis_limits",
    "setup_axes_limits", "setup_axis_scale", "setup_legend",
    "plot_line", "plot_scatter", "plot_bars", "plot_shaded",
    "plot_inf_lines", "plot_histogram", "plot_heatmap",
    "set_next_line_style", "set_next_fill_style", "set_next_marker_style",
    "push_colormap", "pop_colormap",
    "is_plot_hovered", "get_plot_pos", "get_plot_size",
    "get_plot_mouse_pos", "get_plot_limits", "PlotRect", "PlotRange",
]

# -- the enumerations, spelled the way autoport renames them --------------- #
AXIS_X1, AXIS_X2, AXIS_X3 = 0, 1, 2
AXIS_Y1, AXIS_Y2, AXIS_Y3 = 3, 4, 5

COND_NONE, COND_ALWAYS, COND_ONCE = 0, 1, 2

FLAGS_NONE = 0
FLAGS_NO_TITLE = 1 << 0
FLAGS_NO_LEGEND = 1 << 1
FLAGS_NO_MOUSE_TEXT = 1 << 2
FLAGS_NO_INPUTS = 1 << 3
FLAGS_NO_MENUS = 1 << 4
FLAGS_NO_BOX_SELECT = 1 << 5
FLAGS_EQUAL = 1 << 6
#: ImPlot's own shorthand: no title, no legend, no menus, no mouse readout.
FLAGS_CANVAS_ONLY = (FLAGS_NO_TITLE | FLAGS_NO_LEGEND
                     | FLAGS_NO_MENUS | FLAGS_NO_MOUSE_TEXT)

SCALE_LINEAR, SCALE_LOG10, SCALE_SYMLOG = 0, 1, 2

#: ``ImPlotAxisFlags``, the two that change what an axis *says*. The bit values
#: are ImPlot's, so a port passing the C++ constants through lands on them.
AXIS_FLAGS_NONE = 0
AXIS_FLAGS_NO_LABEL = 1 << 0
AXIS_FLAGS_NO_TICK_LABELS = 1 << 2

#: ``ImPlotMarker``, the shapes :mod:`emtk.widgets.markers` draws. The values
#: are ImPlot's enum values (``Cross`` is 7 there, after the four triangles).
MARKER_NONE, MARKER_CIRCLE, MARKER_SQUARE, MARKER_DIAMOND = -1, 0, 1, 2
MARKER_CROSS = 7
_MARKER_NAMES = {MARKER_CIRCLE: "circle", MARKER_SQUARE: "square",
                 MARKER_DIAMOND: "diamond", MARKER_CROSS: "cross"}

INF_LINES_HORIZONTAL = 1 << 0
BARS_HORIZONTAL = 1 << 0

HEATMAP_NONE = 0
#: ``values`` is stored column by column instead of row by row. The bit is
#: ImPlot's own (``1 << 10``); a port that passes the C++ constant through
#: must land on the same meaning.
HEATMAP_COL_MAJOR = 1 << 10

#: A viridis-like perceptual ramp, eleven stops sampled at 0.0, 0.1, ... 1.0.
#:
#: *Not* what the reference uses by default: ``PlotHeatmap`` samples ImPlot's
#: *current* colormap, and that is ``Deep`` -- ten categorical colours meant
#: for telling series apart. Sampled continuously it runs blue, orange, green,
#: red, purple, and a reader cannot tell a big value from a small one, which
#: is the only thing a heatmap exists to say. So the default here is a
#: monotone-luminance ramp instead; ``push_colormap`` still overrides it, so a
#: port that pushed a colormap gets exactly what it asked for.
VIRIDIS_COLORMAP: tuple[tuple[int, int, int], ...] = (
    (68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142),
    (38, 130, 142), (31, 158, 137), (53, 183, 121), (109, 205, 89),
    (180, 222, 44), (221, 227, 24), (253, 231, 37),
)

#: Gutters around the plot area, in pixels: room for the y tick labels (which
#: Plot draws 34px left of its own box), the x tick labels, and the axis
#: titles. ImPlot measures these from the text; fixed values are enough here
#: and keep a plot the same size frame to frame, which a live trace wants.
_GUTTER_L, _GUTTER_R, _GUTTER_B = 40.0, 6.0, 4.0

_ALIGN_CENTRE, _ALIGN_LEFT = _PAINT_CENTRE, _PAINT_LEFT
_TITLE_TEXT = (215, 220, 230)
_AXIS_TEXT = (170, 176, 188)
_TICK_TEXT = (160, 165, 175)


def _inner(x, y, w, h, gutter):
    """The plot area inside the widget rect, once the gutters are taken."""
    gl, gt, gr, gb = gutter
    return (x + gl, y + gt,
            max(w - gl - gr, _MIN_W_INNER), max(h - gt - gb, _MIN_H_INNER))


def _tick_text(v: float, is_log: bool) -> str:
    """A log axis holds log10 of the sample, so its ticks must read as the
    value the caller plotted, not as the exponent."""
    # Three significant digits on a log axis: a range narrower than a decade
    # gets ticks between decades, and 10**1.6 printed in full is "39.8107".
    return f"{10.0 ** v:.3g}" if is_log else f"{v:g}"


_MIN_W_INNER = _MIN_H_INNER = 4.0

#: Minimum plot box. A zero- or negative-sized plot is what a collapsed
#: window hands you, and drawing into it divides by the width.
_MIN_W, _MIN_H = 8.0, 8.0
_DEFAULT_H = 200.0          # ImPlot's own default when the height is 0


class _CellPlot(Plot):
    """:class:`Plot` plus the one item type it has no name for: a grid of
    filled cells, which is all a heatmap is.

    A cell is recorded as a series in ``_lines`` and painted from the
    per-series hook rather than by :func:`end_plot` after ``Plot.draw`` has
    returned. That is what keeps the cells in call order with the line series,
    inside the clip ``Plot.draw`` pushes around the plot box, and after the
    axes have been handed their pixel span. Painted after ``draw`` instead,
    they would cover every series unconditionally, the frame background would
    already have been washed over them, and a cell whose bounds run past the
    axis limits would paint over the tick labels rather than being clipped.
    """

    def _draw_line(self, p, series: dict) -> None:
        cells = series.get("cells")
        if cells is None:
            super()._draw_line(p, series)
            return
        ax, ay = self._x_axis, self._y_axis
        for x0, y0, x1, y1, colour, text, text_colour in cells:
            # Both edges are rounded onto the same integer grid. Rounding the
            # origin but keeping a fractional width leaves a background-
            # coloured seam between neighbouring cells, which reads as a grid
            # the data does not have.
            left, right = round(ax.to_pixels(x0)), round(ax.to_pixels(x1))
            top, bottom = round(ay.to_pixels(y1)), round(ay.to_pixels(y0))
            if right < left:                 # an inverted axis, or bounds
                left, right = right, left    # handed to us the other way up
            if bottom < top:
                top, bottom = bottom, top
            w, h = max(right - left, 1.0), max(bottom - top, 1.0)
            p.fill_rect(left, top, w, h, colour)
            if text:
                p.text(left, top, w, h, _ALIGN_CENTRE, text, text_colour)


class _Current:
    """The plot between ``begin_plot`` and ``end_plot``.

    One module-level instance, because ImPlot's free functions have no other
    way to find the plot they belong to. Nested plots are not a thing in
    ImPlot either -- ``BeginPlot`` inside a plot is an error there too.
    """

    def __init__(self) -> None:
        self.plot: Plot | None = None
        #: Which context and frame left a plot open. The frame number alone
        #: is not enough to tell "still inside that plot" from "a different
        #: run that happens to be on the same frame": a fresh Context starts
        #: counting at one, so a plot abandoned by an exception in one made
        #: every plot in the *next* one raise, and the first bad panel took
        #: every later panel with it.
        self.owner: int | None = None
        self.title: str = ""
        self.flags: int = 0
        self.box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.outer: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.gutter: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self.x_label: str | None = None
        self.y_label: str | None = None
        self.y_log: bool = False
        self.x_log: bool = False
        self.next_line: tuple | None = None
        self.next_fill: tuple | None = None
        self.next_marker: tuple | None = None
        self.x_flags: int = 0
        self.y_flags: int = 0
        self.colormap: Sequence[tuple] | None = None
        self.frame: int = -1


_cur = _Current()


def _fmt_label(label: str) -> str:
    """ImGui's ``##`` convention: everything after it is id, not text."""
    return label.split("##", 1)[0]


def _log10_guard(values):
    """Log axes cannot show a non-positive sample, and real data has them --
    a dark count of zero, a subtracted background. ImPlot drops them from the
    line; so does this, rather than raising or plotting ``-inf``."""
    return [(v if v > 0.0 else None) for v in values]


def begin_plot(title: str, size=(-1.0, -1.0), flags: int = 0) -> bool:
    """Open a plot at the cursor. Returns True, and the caller must then call
    :func:`end_plot` -- the shape ImPlot uses so a skipped plot can be cheap.

    ``size`` follows ImPlot: a non-positive component means *fill the
    available content region*, and a zero height falls back to 200px when the
    region is unbounded.
    """
    frame = _core.get_frame_count()
    owner = id(_core.get_current_context())
    if _cur.plot is not None:
        if _cur.frame == frame and _cur.owner == owner:
            raise RuntimeError(
                "implot.begin_plot() inside a plot: call end_plot() first")
        # a plot left open by an exception in a previous frame, or in another
        # context entirely. Carrying it forward would make every later plot
        # raise, turning one bad frame into a dead interface.
        _cur.plot = None
    _cur.frame = frame
    _cur.owner = owner

    x, y = _w.get_cursor_screen_pos()
    avail_w, avail_h = _w.get_content_region_avail()

    w, h = float(size[0]), float(size[1])
    if w <= 0.0:
        w = avail_w + w            # ImPlot reads -1 as "all but one pixel"
    if h <= 0.0:
        h = (avail_h + h) if avail_h > _MIN_H else _DEFAULT_H
    w = max(w, _MIN_W)
    h = max(h, _MIN_H)

    # ImPlot reserves gutters around the plot area for the decorations; so
    # must this, because Plot draws its y tick labels 34px to the *left* of
    # its own box. Given the whole widget rect they land outside the window
    # and are clipped away -- which is why the first version drew gridlines
    # with nothing to read them by.
    ctx = _core.get_current_context()
    row = ctx.p.line_height()
    top = row if (title and not (flags & FLAGS_NO_TITLE)) else 0.0
    # two rows at the bottom: one for the tick numbers, one for the axis
    # title beneath them. Reserved unconditionally, because setup_axes()
    # runs *after* this and the box cannot be resized once series are in.
    _cur.gutter = (_GUTTER_L, top, _GUTTER_R, _GUTTER_B + row * 2.0)

    _cur.title = title
    _cur.flags = flags
    _cur.outer = (x, y, w, h)
    _cur.box = _inner(x, y, w, h, _cur.gutter)
    _cur.plot = _CellPlot(*_cur.box, show_ticks=True,
                          # FLAGS_NO_LEGEND was accepted and ignored: Plot drew
                          # a key whenever any series had a label, so a caller
                          # that asked for a bare canvas got a key over its
                          # curves anyway. A flag that is taken and does nothing
                          # is worse than one that is refused.
                          show_legend=not (_cur.flags & FLAGS_NO_LEGEND))
    _cur.plot.format_tick = lambda v: _tick_text(v, _cur.y_log)
    _cur.x_label = _cur.y_label = None
    _cur.x_log = _cur.y_log = False
    _cur.x_flags = _cur.y_flags = AXIS_FLAGS_NONE
    _cur.next_line = _cur.next_fill = _cur.next_marker = None
    return True


def end_plot() -> None:
    """Draw the plot built since :func:`begin_plot`, and reserve its space."""
    if _cur.plot is None:
        raise RuntimeError("implot.end_plot() without a matching begin_plot()")
    ctx = _core.get_current_context()
    # The drawlist's current target, **not** ``ctx.p``. The two are the same
    # object right up until something splits the drawlist into channels to
    # draw out of order -- and then ``ctx.p`` is the real painter, which paints
    # *now*, while every other widget is queueing into a channel that is
    # replayed later. A plot drawn to ``ctx.p`` therefore lands underneath
    # everything the channels replay on top of it: inside a node editor it is
    # painted first and the node's own body is then painted over it, so the
    # plot is simply absent and nothing reports a problem.
    #
    # Going through the drawlist puts the plot wherever its caller is drawing.
    # With no split in force ``draw.p`` *is* ``ctx.p``, so this changes nothing
    # for every existing caller.
    p = ctx.draw.p
    x, y, w, h = _cur.box
    ox, oy, ow, oh = _cur.outer
    row = p.line_height()

    title = _fmt_label(_cur.title)
    if title and not (_cur.flags & FLAGS_NO_TITLE):
        p.text(ox, oy, ow, row, _ALIGN_CENTRE, title, _TITLE_TEXT)

    _cur.plot._x_axis.log_decades = _cur.x_log
    _cur.plot._y_axis.log_decades = _cur.y_log
    _cur.plot.show_y_tick_labels = not (_cur.y_flags & AXIS_FLAGS_NO_TICK_LABELS)
    _cur.plot.draw(p)

    # Plot draws the y tick labels itself, into the gutter reserved for them,
    # but has no x tick labels and no axis titles -- ImPlot's SetupAxes says
    # what the numbers *are*, so a plot without them is a picture, not data.
    if not (_cur.x_flags & AXIS_FLAGS_NO_TICK_LABELS):
        for v in _cur.plot._x_axis.ticks():
            px = _cur.plot._x_axis.to_pixels(v)
            p.text(px - 24.0, y + h + 2.0, 48.0, row, _ALIGN_CENTRE,
                   _tick_text(v, _cur.x_log), _TICK_TEXT)
    if _cur.x_label:
        p.text(x, oy + oh - row, w, row, _ALIGN_CENTRE, _cur.x_label, _AXIS_TEXT)
    if _cur.y_label:
        # ImPlot rotates this up the left edge; not every emtk painter can
        # rotate text, so it shares the reserved top row with the title --
        # left-aligned, above the axis it names. Drawing it a row *above* the
        # plot area put it over whatever the caller drew before the plot.
        p.text(ox, oy, w + _GUTTER_L, row, _ALIGN_LEFT, _cur.y_label, _AXIS_TEXT)

    _cur.plot = None
    _w.dummy(ow, oh)


# -- setup ----------------------------------------------------------------- #
def setup_axes(x_label: str = "", y_label: str = "",
               x_flags: int = 0, y_flags: int = 0) -> None:
    """Name the axes. Of ``ImPlotAxisFlags``, ``AXIS_FLAGS_NO_LABEL`` and
    ``AXIS_FLAGS_NO_TICK_LABELS`` are honoured; the others are accepted and
    ignored, as they only change interaction this shim does not have."""
    _cur.x_label = None if x_flags & AXIS_FLAGS_NO_LABEL else (x_label or None)
    _cur.y_label = None if y_flags & AXIS_FLAGS_NO_LABEL else (y_label or None)
    _cur.x_flags, _cur.y_flags = int(x_flags), int(y_flags)


def setup_axis_limits(axis: int, vmin: float, vmax: float,
                      cond: int = COND_ONCE) -> None:
    """Pin an axis. emtk rebuilds the plot every frame, so there is no
    "once" to honour -- ``ImPlotCond_Once`` and ``ImPlotCond_Always`` do the
    same thing here, which is what the caller wanted either way."""
    if _cur.plot is None:
        return
    if vmax <= vmin:                       # a degenerate range hides the data
        return
    is_x = axis < AXIS_Y1
    if (_cur.x_log if is_x else _cur.y_log):
        # the samples were mapped through log10 on the way in, so the bounds
        # must be too, or the range and the data are in different units
        if vmin <= 0.0 or vmax <= 0.0:
            return
        vmin, vmax = math.log10(vmin), math.log10(vmax)
    ax = _cur.plot._x_axis if axis < AXIS_Y1 else _cur.plot._y_axis
    # `_fixed_min`/`_fixed_max` are the fields Axis.range actually reads.
    # Assigning `lo`/`hi` created two attributes nothing consulted, so every
    # SetupAxisLimits was silently a no-op and the plot auto-fitted instead.
    ax._fixed_min, ax._fixed_max = float(vmin), float(vmax)


def setup_axes_limits(x_min: float, x_max: float, y_min: float, y_max: float,
                      cond: int = COND_ONCE) -> None:
    setup_axis_limits(AXIS_X1, x_min, x_max, cond)
    setup_axis_limits(AXIS_Y1, y_min, y_max, cond)


def setup_axis_scale(axis: int, scale: int) -> None:
    """Only the log scale changes anything: the samples are mapped through
    log10 on the way in, and the axis range with them."""
    if axis < AXIS_Y1:
        _cur.x_log = scale == SCALE_LOG10
    else:
        _cur.y_log = scale == SCALE_LOG10


def setup_legend(loc: int = 0, flags: int = 0) -> None:
    """Accepted and ignored: emtk's Plot places its legend itself."""


# -- style ----------------------------------------------------------------- #
def _rgba(colour) -> tuple:
    """ImPlot styles in floats 0..1; emtk paints in bytes 0..255."""
    if colour is None:
        return None
    vals = list(colour)
    if all(isinstance(v, float) and -0.001 <= v <= 1.001 for v in vals):
        vals = [int(round(v * 255)) for v in vals]
    return tuple(int(v) for v in vals[:4])


def set_next_line_style(colour=None, weight: float = 1.5, dash=None) -> None:
    """Style the next item's line. ``dash`` -- an ``(on, off)`` pixel pattern
    -- is emtk's, not ImPlot's: ImPlot draws every line solid, which leaves a
    port no way to draw a prior dashed beside its solid posterior."""
    _cur.next_line = (_rgba(colour), weight, dash)


def set_next_marker_style(marker: int = MARKER_CIRCLE, size: float = -1.0,
                          fill=None, weight: float = -1.0, outline=None) -> None:
    """``ImPlot::SetNextMarkerStyle``: the next scatter's marker shape, radius
    in pixels (``-1`` keeps the default) and colour. Given to a line, the
    markers are drawn at its samples as well, as ImPlot does. ``weight`` and a
    distinct ``outline`` are accepted; markers are drawn filled in ``fill``
    (else ``outline``, else the line colour)."""
    _cur.next_marker = (int(marker), float(size), _rgba(fill), _rgba(outline))


def set_next_fill_style(colour=None, alpha: float = 1.0) -> None:
    _cur.next_fill = (_rgba(colour), alpha)


def push_colormap(colours) -> None:
    _cur.colormap = [_rgba(c) for c in colours] if colours else None


def pop_colormap() -> None:
    _cur.colormap = None


def _take_line_style():
    style, _cur.next_line = _cur.next_line, None
    return (style or (None, 1.5))[:2]


def _take_dash():
    """The dash of the pending line style, read before it is consumed."""
    style = _cur.next_line
    return style[2] if style is not None and len(style) > 2 else None


def _take_marker_style():
    style, _cur.next_marker = _cur.next_marker, None
    return style


def _is_series(v) -> bool:
    """Is this argument an array of samples, or a scalar?

    ImPlot tells its overloads apart by the C++ type of the argument; Python
    has to ask at run time. A string is iterable and is never an array of
    samples, so it is excluded by name rather than by accident.
    """
    return v is not None and not isinstance(v, (str, bytes)) and hasattr(v, "__len__")


def _xs_ys(xs, ys=None):
    """``PlotLine(label, ys, n)`` -- the one-array overload indexes by
    position, exactly as ImPlot does."""
    if ys is None:
        ys = list(xs)
        return list(range(len(ys))), ys
    return list(xs), list(ys)


def _mapped(xs, ys):
    """Apply the log scales, dropping the samples a log axis cannot show."""
    if _cur.x_log:
        xs = [math.log10(v) if v > 0 else None for v in xs]
    if _cur.y_log:
        ys = [math.log10(v) if v > 0 else None for v in ys]
    if _cur.x_log or _cur.y_log:
        keep = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
        return [a for a, _ in keep], [b for _, b in keep]
    return xs, ys


# -- items ----------------------------------------------------------------- #
def plot_line(label: str, xs, ys=None, count: int | None = None) -> None:
    xs, ys = _xs_ys(xs, ys)
    if count is not None:
        xs, ys = xs[:count], ys[:count]
    xs, ys = _mapped(xs, ys)
    if not xs:
        return
    dash = _take_dash()
    colour, weight = _take_line_style()
    marker = _take_marker_style()
    _cur.plot.line(_fmt_label(label), xs, ys, colour=colour, width=weight, dash=dash)
    if marker is not None and marker[0] != MARKER_NONE:
        _add_markers("", xs, ys, marker, colour or _cur.plot._lines[-1]["colour"])


def _add_markers(label, xs, ys, marker, colour) -> None:
    """Record a scatter series drawn with a ``set_next_marker_style`` style."""
    shape, size, fill, outline = marker
    _cur.plot.scatter(label, xs, ys, colour=fill or outline or colour,
                      marker=_MARKER_NAMES.get(shape, "circle"),
                      radius=size if size > 0 else 2.5)


def plot_scatter(label: str, xs, ys=None, count: int | None = None) -> None:
    xs, ys = _xs_ys(xs, ys)
    if count is not None:
        xs, ys = xs[:count], ys[:count]
    xs, ys = _mapped(xs, ys)
    if not xs:
        return
    colour, _ = _take_line_style()
    marker = _take_marker_style()
    if marker is not None and marker[0] != MARKER_NONE:
        _add_markers(_fmt_label(label), xs, ys, marker, colour)
        return
    _cur.plot.scatter(_fmt_label(label), xs, ys, colour=colour)


def plot_bars(label: str, xs, *args, ys=None, count: int | None = None,
              bar_size: float | None = None, shift: float | None = None,
              flags: int = 0) -> None:
    """Bars, in either of the reference's two overloads:

    .. code-block:: c++

        PlotBars(label, values, count, bar_size=0.67, shift=0, flags=0)
        PlotBars(label, xs, ys, count, bar_size, flags=0)

    ``count`` comes *before* the sizing argument in both, so a port that calls
    this positionally -- which is the whole point of the module -- lands in
    the wrong parameter unless the two shapes are told apart here. They are
    told apart the way C++ tells them apart: by whether the third argument is
    an array or a number. Getting that wrong is not a crash but a lie -- the
    count reads as a bar size and the bar size as a shift, and the picture is
    drawn confidently wrong -- which is why the positional tail is re-read per
    overload rather than trusted to line up.

    Note the xy overload has no ``shift``: the slot after ``bar_size`` there
    is ``flags``.

    Bars are drawn as a step outline. emtk's Plot has no filled-rectangle
    series, and a step is the honest reading of the same numbers -- said here
    rather than left as a silent difference from the C++ picture.
    """
    rest = list(args)
    if ys is None and rest and _is_series(rest[0]):
        ys = rest.pop(0)
    slots = (("count", "bar_size", "flags") if ys is not None
             else ("count", "bar_size", "shift", "flags"))
    tail = dict(zip(slots, rest))
    count = tail.get("count", count)
    bar_size = tail.get("bar_size", bar_size)
    shift = tail.get("shift", shift)
    flags = tail.get("flags", flags)
    # The defaults are applied after the dispatch, not in the signature: a
    # parameter that carries a different argument per overload cannot also
    # carry that argument's default.
    bar_size = 0.67 if bar_size is None else float(bar_size)
    shift = 0.0 if shift is None else float(shift)

    horizontal = bool(flags & BARS_HORIZONTAL)
    if ys is None:
        # The values overload: a bar's position is its index. Horizontal bars
        # grow along x, so it is the *index* that goes on y there -- drawn the
        # other way round they are a transposed picture of the same numbers,
        # which is exactly the kind of wrong nobody spots.
        vals = list(xs)
        idx = [float(k) for k in range(len(vals))]
        xs, ys = (vals, idx) if horizontal else (idx, vals)
    else:
        xs, ys = list(xs), list(ys)
    if count is not None:
        xs, ys = xs[:count], ys[:count]
    xs, ys = _mapped(xs, ys)
    if not xs:
        return
    colour, weight = _take_line_style()
    step_x: list[float] = []
    step_y: list[float] = []
    half = bar_size / 2.0
    for x, y in zip(xs, ys):
        if horizontal:
            step_x += [x, x]
            step_y += [y - half + shift, y + half + shift]
        else:
            step_x += [x - half + shift, x + half + shift]
            step_y += [y, y]
    _cur.plot.line(_fmt_label(label), step_x, step_y, colour=colour, width=weight)


#: ``PlotHistogram`` in ImPlot bins raw samples itself; the same here, so the
#: caller passes values rather than counts.
def plot_histogram(label: str, values, bins: int = 32) -> None:
    vals = [v for v in values if v is not None]
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        hi = lo + 1.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        k = min(int((v - lo) / width), bins - 1)
        counts[k] += 1
    centres = [lo + (k + 0.5) * width for k in range(bins)]
    plot_bars(label, centres, counts, bar_size=width)


# -- the heatmap ----------------------------------------------------------- #
def _ramp_colour(stops, t: float) -> tuple:
    """The colour at ``t`` in 0..1, interpolated between colormap stops.

    ImPlot's ``SampleColormap`` does the same for a continuous map. A
    qualitative map is interpolated too rather than snapped to its nearest
    stop: a pushed colormap is the caller saying "these colours", and a
    heatmap needs a continuum out of whatever it is given.

    Alpha is forced opaque. A translucent cell lets the gridlines and the
    frame background through, and a value then reads as a different value
    depending on whether a gridline happens to cross it.
    """
    n = len(stops)
    if n == 1:
        return tuple(stops[0][:3]) + (255,)
    pos = min(max(t, 0.0), 1.0) * (n - 1)
    i = min(int(pos), n - 2)
    f = pos - i
    a, b = stops[i], stops[i + 1]
    return tuple(int(round(a[k] + (b[k] - a[k]) * f)) for k in range(3)) + (255,)


def _inlay_text_colour(colour) -> tuple:
    """Black on a light cell, white on a dark one.

    The reference paints cell labels in one fixed colour
    (``ImPlotCol_InlayText``, white). On the bright end of any perceptual ramp
    that is white on pale yellow -- illegible, and legibility is the only
    reason to ask for labels at all.
    """
    luma = 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2]
    return (16, 16, 20, 255) if luma > 140.0 else (240, 242, 245, 255)


def _cell_label(label_fmt: str, value: float) -> str:
    """``label_fmt`` is printf, as in the reference. A hand-ported call site
    often carries a Python format string instead, and printing a literal
    ``{:.1f}`` into every cell is a worse failure than accepting both."""
    return (label_fmt % value) if "%" in label_fmt else label_fmt.format(value)


def _flat(values) -> list:
    """The reference takes one flat, row-major block (``const T*``). A Python
    caller often has a list of rows instead, and indexing that as if it were
    flat draws row zero's numbers across the whole grid, so it is flattened
    here rather than silently mis-read."""
    if len(values) and hasattr(values[0], "__len__"):
        return [v for row in values for v in row]
    return list(values)


def _edges(values, is_log: bool):
    """Cell edges in axis units, ``None`` for an edge a log axis cannot show.

    The cells are uniform in *data* space, so each edge is mapped
    individually: mapping only the outer bounds and subdividing in pixels
    would put the cell boundaries somewhere the data is not.
    """
    if not is_log:
        return list(values)
    return [math.log10(v) if v > 0.0 else None for v in values]


def plot_heatmap(label: str, values, rows: int, cols: int,
                 scale_min: float = 0.0, scale_max: float = 0.0,
                 label_fmt: str | None = "%.1f",
                 bounds_min=(0.0, 0.0), bounds_max=(1.0, 1.0),
                 flags: int = 0) -> None:
    """A ``rows`` x ``cols`` grid of coloured cells over the given bounds.

    .. code-block:: c++

        ImPlot::PlotHeatmap("##Heatmap", h.data(), n, n, 0, max_h, nullptr,
                            ImPlotPoint(x0, y0), ImPlotPoint(x1, y1));

    ports to::

        implot.plot_heatmap("##Heatmap", h, n, n, 0, max_h, None,
                            (x0, y0), (x1, y1))

    ``values`` is one flat, row-major block of ``rows * cols`` numbers, and
    row zero is drawn at the *top* -- at ``bounds_max``'s y -- exactly as the
    reference lays it out; a heatmap flipped top to bottom is a picture of
    different data. Pass :data:`HEATMAP_COL_MAJOR` for the other storage
    order. ``scale_min == scale_max == 0`` is the reference's own sentinel for
    "autoscale to the data".

    ``label_fmt`` is printf and may be ``None`` or ``""`` for no labels, which
    is what a fine grid wants: at a few pixels a cell there is no room for a
    number, and the reference's own default of ``"%.1f"`` would paint mush.

    Two deliberate differences from the reference, both about being read
    rather than about being ImPlot:

    * The default colormap is :data:`VIRIDIS_COLORMAP`, not ImPlot's current
      colormap (``Deep``, a categorical palette -- see the note there).
      :func:`push_colormap` still overrides it.
    * Cell labels are drawn black or white per cell by luminance, where the
      reference uses one fixed colour.

    Cells are plain filled rectangles through the painter every other item
    uses -- no texture, no image upload -- so a heatmap draws on any host that
    can draw a button.
    """
    if _cur.plot is None:
        raise RuntimeError(
            "implot.plot_heatmap() outside a begin_plot()/end_plot() pair")
    rows, cols = int(rows), int(cols)
    if rows <= 0 or cols <= 0:
        return
    vals = _flat(values)
    if len(vals) < rows * cols:
        # A live window sizes its grid before the histogram behind it is
        # filled. Drawing the cells that happen to exist would show a shape
        # that is not the data; the reference would read past the end.
        return

    lo, hi = float(scale_min), float(scale_max)
    if lo == 0.0 and hi == 0.0:
        lo, hi = min(vals[:rows * cols]), max(vals[:rows * cols])
    span = hi - lo

    x0, y0 = float(bounds_min[0]), float(bounds_min[1])
    x1, y1 = float(bounds_max[0]), float(bounds_max[1])
    cell_w, cell_h = (x1 - x0) / cols, (y1 - y0) / rows
    xe = _edges([x0 + j * cell_w for j in range(cols + 1)], _cur.x_log)
    # Top edge first: row zero sits against bounds_max's y and each later row
    # is one cell lower, which is what makes the first row draw at the top.
    ye = _edges([y1 - i * cell_h for i in range(rows + 1)], _cur.y_log)
    finite_x = [v for v in xe if v is not None]
    finite_y = [v for v in ye if v is not None]
    if not finite_x or not finite_y:
        return
    # ImPlot fits the axes to the bounds, so an unpinned plot frames the grid
    # exactly; setup_axis_limits still wins, since Axis.fit leaves a fixed
    # bound alone.
    _cur.plot._x_axis.fit(finite_x)
    _cur.plot._y_axis.fit(finite_y)

    stops = _cur.colormap or VIRIDIS_COLORMAP
    col_major = bool(flags & HEATMAP_COL_MAJOR)
    cells = []
    for i in range(rows):
        top, bottom = ye[i], ye[i + 1]
        if top is None or bottom is None:
            continue
        for j in range(cols):
            left, right = xe[j], xe[j + 1]
            if left is None or right is None:
                continue
            v = vals[j * rows + i] if col_major else vals[i * cols + j]
            # A flat range (every cell equal, or an explicit scale_min ==
            # scale_max) has no gradient to show and would divide by zero;
            # the bottom of the ramp is the one answer that is not a lie.
            t = (v - lo) / span if span > 0.0 else 0.0
            colour = _ramp_colour(stops, t)
            text = _cell_label(label_fmt, v) if label_fmt else ""
            cells.append((left, bottom, right, top, colour,
                          text, _inlay_text_colour(colour) if text else None))
    if not cells:
        return
    _cur.plot._lines.append({
        "label": _fmt_label(label),
        "cells": cells,
        # Plot's legend reads "colour" off every series it has a label for,
        # so a heatmap called with a visible label needs one: the middle of
        # the ramp, which is the swatch a reader would draw for it.
        "colour": _ramp_colour(stops, 0.5),
    })


def plot_shaded(label: str, xs, ys1, ys2=None, count: int | None = None) -> None:
    """The band's two edges, as lines. emtk's Plot has no filled area; the
    edges carry the same information and are not mistakable for one."""
    xs = list(xs)
    ys1 = list(ys1)
    ys2 = [0.0] * len(xs) if ys2 is None else list(ys2)
    if count is not None:
        xs, ys1, ys2 = xs[:count], ys1[:count], ys2[:count]
    colour, weight = _take_line_style()
    if _cur.next_fill:
        colour = _cur.next_fill[0] or colour
        _cur.next_fill = None
    ax, ay = _mapped(xs, ys1)
    bx, by = _mapped(list(xs), ys2)
    if ax:
        _cur.plot.line(_fmt_label(label), ax, ay, colour=colour, width=weight)
    if bx:
        _cur.plot.line(_fmt_label(label) + " ", bx, by, colour=colour, width=weight)


def plot_inf_lines(label: str, values, count: int | None = None,
                   flags: int = 0) -> None:
    """An infinite line at each value. Only the horizontal form is drawn --
    :class:`Plot` has ``hline`` and no vertical twin, so a vertical request
    is skipped rather than silently drawn the wrong way round."""
    vals = list(values)[:count] if count is not None else list(values)
    if not (flags & INF_LINES_HORIZONTAL):
        return
    colour, _ = _take_line_style()
    for v in vals:
        if _cur.y_log:
            if v <= 0:
                continue
            v = math.log10(v)
        _cur.plot.hline(v, colour or DEEP_PALETTE[0], _fmt_label(label) or None)


# -- queries --------------------------------------------------------------- #
def get_plot_pos() -> tuple:
    return _cur.box[0], _cur.box[1]


def get_plot_size() -> tuple:
    return _cur.box[2], _cur.box[3]


def is_plot_hovered() -> bool:
    x, y, w, h = _cur.box
    mx, my = _core.get_io().mouse_pos
    return x <= mx < x + w and y <= my < y + h


class PlotRange(NamedTuple):
    """One axis's range, spelled as ``ImPlotRange``: ``.min`` and ``.max``."""

    min: float
    max: float


class PlotRect(NamedTuple):
    """What :func:`get_plot_limits` returns: the four numbers, and the two
    spellings a caller reaches for.

    ``x_min, x_max, y_min, y_max = get_plot_limits()`` is what a Python caller
    writes, and a tuple is what that needs. A *ported* caller writes
    ``limits.X.min``, because that is ``ImPlotRect``'s shape -- and a flat
    tuple gives it ``AttributeError: 'tuple' object has no attribute 'X'``
    halfway through a frame. Being both costs one class.
    """

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    @property
    def X(self) -> PlotRange:                                    # noqa: N802
        return PlotRange(self.x_min, self.x_max)

    @property
    def Y(self) -> PlotRange:                                    # noqa: N802
        return PlotRange(self.y_min, self.y_max)


def get_plot_limits() -> PlotRect:
    """The axis ranges as ``(x_min, x_max, y_min, y_max)`` -- see
    :class:`PlotRect` for why it also answers ``.X.min``."""
    if _cur.plot is None:
        return PlotRect(0.0, 1.0, 0.0, 1.0)
    x0, x1 = _cur.plot._x_axis.range
    y0, y1 = _cur.plot._y_axis.range
    return PlotRect(x0, x1, y0, y1)


def get_plot_mouse_pos() -> tuple:
    """The cursor in plot coordinates -- what a click on the picture means
    in the units the data is in."""
    x, y, w, h = _cur.box
    mx, my = _core.get_io().mouse_pos
    x0, x1, y0, y1 = get_plot_limits()
    u = (mx - x) / w if w else 0.0
    v = (my - y) / h if h else 0.0
    px = x0 + u * (x1 - x0)
    py = y1 - v * (y1 - y0)            # screen y grows downward, data up
    if _cur.x_log:
        px = 10.0 ** px
    if _cur.y_log:
        py = 10.0 ** py
    return px, py


# --------------------------------------------------------------------------- #
# The C++ spellings
#
# A mechanically ported source names these constants exactly as implot.h does.
# Renaming them at the port site would be one more rule to get right and one
# more thing to check against the C++; binding them here costs nothing and
# means a ported line is the C++ line.
# --------------------------------------------------------------------------- #
ImAxis_X1, ImAxis_X2, ImAxis_X3 = AXIS_X1, AXIS_X2, AXIS_X3
ImAxis_Y1, ImAxis_Y2, ImAxis_Y3 = AXIS_Y1, AXIS_Y2, AXIS_Y3

ImPlotCond_None, ImPlotCond_Always, ImPlotCond_Once = COND_NONE, COND_ALWAYS, COND_ONCE

ImPlotFlags_None = FLAGS_NONE
ImPlotFlags_NoTitle = FLAGS_NO_TITLE
ImPlotFlags_NoLegend = FLAGS_NO_LEGEND
ImPlotFlags_NoMouseText = FLAGS_NO_MOUSE_TEXT
ImPlotFlags_NoInputs = FLAGS_NO_INPUTS
ImPlotFlags_NoMenus = FLAGS_NO_MENUS
ImPlotFlags_NoBoxSelect = FLAGS_NO_BOX_SELECT
ImPlotFlags_Equal = FLAGS_EQUAL
ImPlotFlags_CanvasOnly = FLAGS_CANVAS_ONLY

ImPlotScale_Linear, ImPlotScale_Log10, ImPlotScale_SymLog = (
    SCALE_LINEAR, SCALE_LOG10, SCALE_SYMLOG)

ImPlotInfLinesFlags_None = 0
ImPlotInfLinesFlags_Horizontal = INF_LINES_HORIZONTAL
ImPlotBarsFlags_None = 0
ImPlotBarsFlags_Horizontal = BARS_HORIZONTAL

ImPlotHeatmapFlags_None = HEATMAP_NONE
ImPlotHeatmapFlags_ColMajor = HEATMAP_COL_MAJOR

#: Axis flags. Only ``AutoFit`` changes anything: an axis with no fixed range
#: already fits its data, so the flag is the default and the others are
#: accepted and ignored rather than refused -- a port that passes them should
#: draw, not raise.
ImPlotAxisFlags_None = 0
ImPlotAxisFlags_NoLabel = 1 << 0
ImPlotAxisFlags_NoGridLines = 1 << 1
ImPlotAxisFlags_NoTickMarks = 1 << 2
ImPlotAxisFlags_NoTickLabels = 1 << 3
ImPlotAxisFlags_AutoFit = 1 << 4
ImPlotAxisFlags_Invert = 1 << 5
ImPlotAxisFlags_LockMin = 1 << 6
ImPlotAxisFlags_LockMax = 1 << 7

#: Legend placement, accepted and ignored: Plot places its own legend.
(ImPlotLocation_Center, ImPlotLocation_North, ImPlotLocation_South,
 ImPlotLocation_West, ImPlotLocation_East, ImPlotLocation_NorthWest,
 ImPlotLocation_NorthEast, ImPlotLocation_SouthWest,
 ImPlotLocation_SouthEast) = range(9)

#: Colormaps. Only the palette is honoured -- `push_colormap` takes colours.
ImPlotColormap_Deep = DEEP_PALETTE
ImPlotColormap_Viridis = VIRIDIS_COLORMAP
ImPlotColormap_Jet = (
    (0, 0, 128), (0, 0, 255), (0, 128, 255), (0, 255, 255), (128, 255, 128),
    (255, 255, 0), (255, 128, 0), (255, 0, 0), (128, 0, 0),
)

__all__ += [n for n in dir() if n.startswith(("ImPlot", "ImAxis"))]
