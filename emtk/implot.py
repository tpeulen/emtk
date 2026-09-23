"""``emtk.implot`` -- ImPlot, the plotting library, on emtk.

Ported from epezent/implot at 7eeb916 (``junk/implot``, MIT; licence in
``licenses/``): ``implot.h``/``implot.cpp`` here, the internal header in
:mod:`emtk.implot_internal`, the items in :mod:`emtk.implot_items`. ImPlot C++
ports one line at a time::

    if (ImPlot::BeginPlot("##IntensityTrace", size, ImPlotFlags_NoTitle)) {
        ImPlot::SetupAxes("time / s", "rate / kHz");
        ImPlot::SetupAxisLimits(ImAxis_X1, t0, t1, ImPlotCond_Always);
        ImPlot::PlotLine("ch0", xs.data(), ys.data(), n);
        ImPlot::EndPlot();
    }

becomes::

    if implot.begin_plot("##IntensityTrace", size, implot.FLAGS_NO_TITLE):
        implot.setup_axes("time / s", "rate / kHz")
        implot.setup_axis_limits(implot.AXIS_X1, t0, t1, implot.COND_ALWAYS)
        implot.plot_line("ch0", xs, ys)
        implot.end_plot()

What is ImPlot's
----------------
The whole 2-D library: six axes with linear/time/log10/symlog/custom scales,
limits, links, constraints, formats and custom ticks; every item; subplots
with linked axes and shared legends; aligned plots; the interaction (pan,
wheel zoom about the cursor, box select, double-click fit, axis-only
drag/zoom, axis side switch, legend toggles and highlights, the plot/axis/
legend context menus, crosshairs and mouse text); the drag tools, annotations
and tags; styles, colormaps and the colormap widgets. The state that must
outlive ``EndPlot`` is kept in the frame's ``storage`` (see
:mod:`emtk.implot_internal`), so a plot remembers its axes the way any emtk
widget remembers itself.

What emtk does differently, and why
-----------------------------------
* **Items are drawn in** ``end_plot``, after the fit. ImPlot draws an item when
  it is called, against limits fit on the *previous* frame, so its first
  frame is wrong; emtk draws screenshots and tests from a single frame. Input
  and hit-testing still happen where the reference does them (at the first
  setup-locking call), and ``plot_to_pixels`` answers with those axes;
  drawing through :func:`get_plot_draw_list` is replayed and remapped onto the
  fitted axes.
* **An axis nobody has touched follows its data.** ImPlot fits once, on the
  first frame. emtk's plots were always rebuilt to fit their data, and live
  readouts rely on it, so an axis keeps fitting until the user pans, zooms,
  box-selects or edits it; a double-click fits it and makes it follow again.
* **A changed ``COND_ONCE`` request is a new request**, as a changed flag set
  is in ``SetupAxis``: a caller whose limits move with its data gets them.
* With no colormap pushed, a heatmap samples Viridis rather than ``Deep``.
* Pointer arguments come back as return values (``drag_line_x`` returns
  ``(modified, x, clicked, hovered, held)``), as pyimgui/imgui_bundle do.
* Popups (context menus, legend popups) are emtk windows drawn at the end of
  the plot -- or of the subplot grid -- so a widget submitted after the plot in
  the same window can paint over one.
"""
from __future__ import annotations

import copy as _copy
import inspect as _inspect
import math
from typing import NamedTuple

from . import im_core as _core
from . import im_widgets as _w
from . import implot_internal as I
from . import implot_items as _items
from .implot_internal import *  # noqa: F401,F403  (the enumerations)
from .implot_internal import gp, has_flag, rgba as _rgba
from .implot_items import *  # noqa: F401,F403  (the items)
from .painter import line as _line

#: The spelling this module used before the port. ``_cur.plot`` is the plot
#: between ``begin_plot`` and ``end_plot``.
_cur = gp

DEEP_PALETTE = tuple(tuple(c[:3]) for c in gp.colormap_data.get_keys(I.COLORMAP_DEEP))
VIRIDIS_COLORMAP = tuple(tuple(c[:3]) for c in gp.colormap_data.get_keys(I.COLORMAP_VIRIDIS))

__all__ = [n for n in dir(I) if n.isupper() and not n.startswith("_")]
__all__ += list(_items.__all__)
__all__ += ["PlotSpec", "PlotStyle", "InputMap", "PlotTime", "PlotRange", "PlotRect", "PlotPoint",
            "DEEP_PALETTE", "VIRIDIS_COLORMAP"]


class PlotPoint(NamedTuple):
    """``ImPlotPoint``."""

    x: float
    y: float


class PlotRange(NamedTuple):
    """``ImPlotRange``: ``.min`` and ``.max``."""

    min: float
    max: float

    def size(self) -> float:
        return self.max - self.min

    def contains(self, v: float) -> bool:
        return self.min <= v <= self.max


class PlotRect(NamedTuple):
    """``ImPlotRect``: unpacks as ``(x_min, x_max, y_min, y_max)`` and answers
    ``.X.min`` as the C++ struct does."""

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

    def contains(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max


PlotSpec = I.PlotSpec
PlotStyle = I.PlotStyle
InputMap = I.InputMap
PlotTime = I.PlotTime


def _ctx():
    return _core.get_current_context()


def _io():
    return _ctx().io


def _require_plot(name: str):
    if gp.current_plot is None:
        raise RuntimeError(f"{name}() needs to be called between begin_plot() and end_plot()")
    return gp.current_plot


# --------------------------------------------------------------------------- #
# [SECTION] Begin/End Plot
# --------------------------------------------------------------------------- #
def _calc_item_size(size, default_w: float, default_h: float):
    """``ImGui::CalcItemSize``."""
    avail_w, avail_h = _w.get_content_region_avail()
    w, h = float(size[0]), float(size[1])
    if w == 0.0:
        w = default_w
    elif w < 0.0:
        w = max(4.0, avail_w + w)
    if h == 0.0:
        h = default_h
    elif h < 0.0:
        h = max(4.0, avail_h + h)
    return w, h


def _apply_next_plot_data(idx: int) -> None:
    """``ApplyNextPlotData``."""
    plot = gp.current_plot
    axis = plot.axes[idx]
    if not axis.enabled:
        return
    npd = gp.next_plot_data
    axis.linked_min = npd.linked_min[idx]
    axis.linked_max = npd.linked_max[idx]
    axis.pull_links()
    if npd.has_range[idx]:
        if not plot.initialized or npd.range_cond[idx] == I.COND_ALWAYS:
            axis.set_range(*npd.range[idx])
    axis.has_range = npd.has_range[idx]
    axis.range_cond = npd.range_cond[idx]


def begin_plot(title_id: str, size=(-1.0, 0.0), flags: int = 0) -> bool:
    """``BeginPlot``. Returns True; call :func:`end_plot` after it."""
    ctx = _ctx()
    frame = _core.get_frame_count()
    owner = id(ctx)
    if gp.current_plot is not None:
        if gp.frame == frame and gp.owner == owner:
            raise RuntimeError("implot.begin_plot() inside a plot: call end_plot() first")
        # a plot abandoned by an exception, in an earlier frame or another
        # context: carrying it forward would make every later plot raise
        gp.current_plot = None
        gp.current_items = None
    if gp.current_subplot is not None and gp.owner != owner:
        I.reset_ctx_for_next_subplot()
        gp.current_items = None
    gp.frame, gp.owner = frame, owner
    subplot = gp.current_subplot
    if subplot is not None:
        ctx.push_id(("##subplot_cell", subplot.current_idx))
    plot_id = ctx.get_id(title_id)
    plots = I.pools()["plots"]
    just_created = plot_id not in plots
    plot = plots.get(plot_id)
    if plot is None:
        plot = plots[plot_id] = I.Plot()
    gp.current_plot = plot
    plot.id = plot_id
    plot.items.id = ("##items", plot_id)
    plot.just_created = just_created
    plot.setup_locked = False
    plot.queue = []
    plot.records = []
    plot.setup_dirty = False
    if just_created or flags != plot.previous_flags:
        plot.flags = int(flags)
    plot.previous_flags = int(flags)
    if just_created:
        setup_axis(I.AXIS_X1)
        setup_axis(I.AXIS_Y1)
    for axis in plot.axes:
        axis.reset()
        axis.custom_ticks = None
        I.update_axis_colors(axis)
    plot.axes[I.AXIS_X1].enabled = True
    plot.axes[I.AXIS_Y1].enabled = True
    plot.current_x, plot.current_y = I.AXIS_X1, I.AXIS_Y1
    for i in range(I.AXIS_COUNT):
        _apply_next_plot_data(i)
    plot.set_title(title_id)
    style = gp.style
    if subplot is not None:
        fw, fh = subplot.cell_size
        x, y = subplot.cell_pos
    else:
        fw, fh = _calc_item_size(size, *style.plot_default_size)
        x, y = _w.get_cursor_screen_pos()
    if fw < style.plot_min_size[0] and (float(size[0]) < 0.0 or subplot is not None):
        fw = style.plot_min_size[0]
    if fh < style.plot_min_size[1] and (float(size[1]) < 0.0 or subplot is not None):
        fh = style.plot_min_size[1]
    plot.frame_rect = (x, y, x + fw, y + fh)
    if subplot is None:
        _w.dummy(fw, fh)
    if gp.current_items is None:
        gp.current_items = plot.items
    gp.item_id_depth = len(ctx._ids)
    gp.legacy_line = gp.legacy_fill = gp.legacy_marker = None
    return True


# --------------------------------------------------------------------------- #
# [SECTION] Setup
# --------------------------------------------------------------------------- #
def _setup_plot(name: str):
    plot = _require_plot(name)
    if plot.setup_locked:
        # ImPlot asserts; emtk takes it and lays out again in end_plot, since
        # nothing has been drawn yet.
        plot.setup_dirty = True
    return plot


def setup_axis(axis: int, label=None, flags: int = 0) -> None:
    """``SetupAxis``: enable an axis, name it, flag it."""
    plot = _setup_plot("setup_axis")
    ax = plot.axes[axis]
    ax.id = (plot.id, "##axis", axis)
    if plot.just_created or flags != ax.previous_flags:
        ax.flags = int(flags)
    ax.previous_flags = int(flags)
    ax.enabled = True
    shown = I.split_label(label) if label else ""
    ax.label = shown or None
    I.update_axis_colors(ax)


def setup_axis_limits(axis: int, v_min: float, v_max: float, cond: int = I.COND_ONCE) -> None:
    """``SetupAxisLimits``. See the module docstring for ``COND_ONCE``."""
    plot = _setup_plot("setup_axis_limits")
    ax = plot.axes[axis]
    if not ax.enabled:
        setup_axis(axis)
    request = (float(v_min), float(v_max))
    new_request = cond != I.COND_ALWAYS and ax.once_request is not None and ax.once_request != request
    if not plot.initialized or cond == I.COND_ALWAYS or new_request:
        ax.set_range(*request)
        ax.follow = True
        if plot.setup_locked:
            ax.fit_this_frame = False
    ax.once_request = request if cond != I.COND_ALWAYS else None
    ax.has_range = True
    ax.range_cond = cond


def setup_axis_format(axis: int, fmt, data=None) -> None:
    """``SetupAxisFormat``: a printf string, or a formatter
    ``(value, data) -> str``."""
    plot = _setup_plot("setup_axis_format")
    ax = plot.axes[axis]
    if callable(fmt):
        ax.formatter, ax.formatter_data = fmt, data
    else:
        ax.has_format_spec = fmt is not None
        if fmt is not None:
            ax.format_spec = str(fmt)


def setup_axis_links(axis: int, link_min, link_max=None) -> None:
    """``SetupAxisLinks``. Python has no ``double*``: pass a mutable
    ``[min, max]`` list (both ends), or ``(owner, key)`` pairs, or ``None``."""
    plot = _setup_plot("setup_axis_links")
    ax = plot.axes[axis]
    ax.linked_min, ax.linked_max = _links(link_min, link_max)
    ax.pull_links()


def _links(link_min, link_max):
    if link_max is None and isinstance(link_min, list) and len(link_min) == 2:
        return (link_min, 0), (link_min, 1)
    return link_min, link_max


def setup_axis_ticks(axis: int, values, n_ticks=None, labels=None, keep_default: bool = False,
                     *more) -> None:
    """``SetupAxisTicks``, both overloads::

        setup_axis_ticks(axis, values, n_ticks=None, labels=None, keep_default=False)
        setup_axis_ticks(axis, v_min, v_max, n_ticks, labels=None, keep_default=False)
    """
    plot = _setup_plot("setup_axis_ticks")
    ax = plot.axes[axis]
    if not _items._is_series(values):
        v_min, v_max = float(values), float(n_ticks)
        n = int(labels) if labels is not None else 2
        labels = keep_default if not isinstance(keep_default, bool) else None
        keep_default = bool(more[0]) if more else False
        n = max(n, 2)
        values = [v_min + i * (v_max - v_min) / (n - 1) for i in range(n)]
    else:
        values = list(values)[:n_ticks] if n_ticks is not None else list(values)
    ax.show_default_ticks = bool(keep_default)
    ax.custom_ticks = (values, list(labels) if labels is not None else None)


def setup_axis_scale(axis: int, scale, inverse=None, data=None) -> None:
    """``SetupAxisScale``: a built-in scale, or ``(forward, inverse)``."""
    plot = _setup_plot("setup_axis_scale")
    ax = plot.axes[axis]
    if not ax.enabled:
        setup_axis(axis)
    if callable(scale):
        ax.scale = I.IMPLOT_AUTO
        ax.transform_forward = lambda v, d=None, f=scale: f(v)
        ax.transform_inverse = lambda v, d=None, f=inverse: f(v)
        ax.transform_data = data
        return
    ax.scale = scale
    if scale == I.SCALE_TIME:
        ax.transform_forward = ax.transform_inverse = None
        ax.locator = I.locator_time
        ax.constraint_range = (I.IMPLOT_MIN_TIME, I.IMPLOT_MAX_TIME)
        ax.ticker.levels = 2
    elif scale == I.SCALE_LOG10:
        ax.transform_forward = I.transform_forward_log10
        ax.transform_inverse = I.transform_inverse_log10
        ax.locator = I.locator_log10
        ax.constraint_range = (I.DBL_MIN, I.INF)
    elif scale == I.SCALE_SYMLOG:
        ax.transform_forward = I.transform_forward_symlog
        ax.transform_inverse = I.transform_inverse_symlog
        ax.locator = I.locator_symlog
        ax.constraint_range = (-I.INF, I.INF)
    else:
        ax.transform_forward = ax.transform_inverse = None
        ax.locator = None
        ax.constraint_range = (-I.INF, I.INF)
    ax.transform_data = None


def setup_axis_limits_constraints(axis: int, v_min: float, v_max: float) -> None:
    plot = _setup_plot("setup_axis_limits_constraints")
    plot.axes[axis].constraint_range = (float(v_min), float(v_max))


def setup_axis_zoom_constraints(axis: int, z_min: float, z_max: float) -> None:
    plot = _setup_plot("setup_axis_zoom_constraints")
    plot.axes[axis].constraint_zoom = (float(z_min), float(z_max))


def setup_axes(x_label=None, y_label=None, x_flags: int = 0, y_flags: int = 0) -> None:
    setup_axis(I.AXIS_X1, x_label, x_flags)
    setup_axis(I.AXIS_Y1, y_label, y_flags)


def setup_axes_limits(x_min, x_max, y_min, y_max, cond: int = I.COND_ONCE) -> None:
    setup_axis_limits(I.AXIS_X1, x_min, x_max, cond)
    setup_axis_limits(I.AXIS_Y1, y_min, y_max, cond)


def setup_legend(location: int = I.LOCATION_NORTH_WEST, flags: int = 0) -> None:
    """``SetupLegend``; also right after ``begin_subplots`` with shared items."""
    if gp.current_items is None:
        return
    legend = gp.current_items.legend
    if location != legend.previous_location:
        legend.location = location
    legend.previous_location = location
    if flags != legend.previous_flags:
        legend.flags = flags
    legend.previous_flags = flags


def setup_mouse_text(location: int, flags: int = 0) -> None:
    plot = _setup_plot("setup_mouse_text")
    plot.mouse_text_location = location
    plot.mouse_text_flags = flags


# --------------------------------------------------------------------------- #
# [SECTION] SetNext
# --------------------------------------------------------------------------- #
def set_next_axis_limits(axis: int, v_min: float, v_max: float, cond: int = I.COND_ONCE) -> None:
    npd = gp.next_plot_data
    npd.has_range[axis] = True
    npd.range_cond[axis] = cond
    npd.range[axis] = (float(v_min), float(v_max))


def set_next_axis_links(axis: int, link_min, link_max=None) -> None:
    lo, hi = _links(link_min, link_max)
    gp.next_plot_data.linked_min[axis] = lo
    gp.next_plot_data.linked_max[axis] = hi


def set_next_axis_to_fit(axis: int) -> None:
    gp.next_plot_data.fit[axis] = True


def set_next_axes_limits(x_min, x_max, y_min, y_max, cond: int = I.COND_ONCE) -> None:
    set_next_axis_limits(I.AXIS_X1, x_min, x_max, cond)
    set_next_axis_limits(I.AXIS_Y1, y_min, y_max, cond)


def set_next_axes_to_fit() -> None:
    for i in range(I.AXIS_COUNT):
        set_next_axis_to_fit(i)


# --------------------------------------------------------------------------- #
# [SECTION] SetupFinish: layout and input
# --------------------------------------------------------------------------- #
def setup_lock() -> None:
    """``SetupLock``: finish the setup if nothing has yet."""
    plot = _require_plot("setup_lock")
    if not plot.setup_locked:
        setup_finish()
    plot.setup_locked = True


def _pad_and_datum_axes_x(plot, pad_t: float, pad_b: float, align):
    """``PadAndDatumAxesX``."""
    T = I.text_line_height()
    P = gp.style.label_padding[1]
    K = gp.style.minor_tick_len[0]
    count_t = count_b = 0
    last_t = plot.axes_rect[1]
    last_b = plot.axes_rect[3]
    for i in reversed(range(I.NUM_X_AXES)):
        axis = plot.x_axis(i)
        if not axis.enabled:
            continue
        label, ticks, opp = axis.has_label(), axis.has_tick_labels(), axis.is_opposite()
        time = axis.scale == I.SCALE_TIME
        if opp:
            if count_t > 0:
                pad_t += K + P
            count_t += 1
            if label:
                pad_t += I.calc_text_size(axis.label)[1] + P
            if ticks:
                pad_t += max(T, axis.ticker.max_size[1]) + P + (T + P if time else 0)
            axis.datum1 = plot.canvas_rect[1] + pad_t
            axis.datum2 = last_t
            last_t = axis.datum1
        else:
            if count_b > 0:
                pad_b += K + P
            count_b += 1
            if label:
                pad_b += I.calc_text_size(axis.label)[1] + P
            if ticks:
                pad_b += max(T, axis.ticker.max_size[1]) + P + (T + P if time else 0)
            axis.datum1 = plot.canvas_rect[3] - pad_b
            axis.datum2 = last_b
            last_b = axis.datum1
    if align is not None:
        count_t = count_b = 0
        pad_t, pad_b, delta_t, delta_b = align.update(pad_t, pad_b)
        for i in reversed(range(I.NUM_X_AXES)):
            axis = plot.x_axis(i)
            if not axis.enabled:
                continue
            if axis.is_opposite():
                axis.datum1 += delta_t
                axis.datum2 += delta_t if count_t > 1 else 0
                count_t += 1
            else:
                axis.datum1 -= delta_b
                axis.datum2 -= delta_b if count_b > 1 else 0
                count_b += 1
    return pad_t, pad_b


def _pad_and_datum_axes_y(plot, pad_l: float, pad_r: float, align):
    """``PadAndDatumAxesY``."""
    T = I.text_line_height()
    P = gp.style.label_padding[0]
    K = gp.style.minor_tick_len[1]
    count_l = count_r = 0
    last_l = plot.axes_rect[0]
    last_r = plot.axes_rect[2]
    for i in reversed(range(I.NUM_Y_AXES)):
        axis = plot.y_axis(i)
        if not axis.enabled:
            continue
        label, ticks, opp = axis.has_label(), axis.has_tick_labels(), axis.is_opposite()
        if opp:
            if count_r > 0:
                pad_r += K + P
            count_r += 1
            if label:
                pad_r += T + P
            if ticks:
                pad_r += axis.ticker.max_size[0] + P
            axis.datum1 = plot.canvas_rect[2] - pad_r
            axis.datum2 = last_r
            last_r = axis.datum1
        else:
            if count_l > 0:
                pad_l += K + P
            count_l += 1
            if label:
                pad_l += T + P
            if ticks:
                pad_l += axis.ticker.max_size[0] + P
            axis.datum1 = plot.canvas_rect[0] + pad_l
            axis.datum2 = last_l
            last_l = axis.datum1
    if align is not None:
        count_l = count_r = 0
        pad_l, pad_r, delta_l, delta_r = align.update(pad_l, pad_r)
        for i in reversed(range(I.NUM_Y_AXES)):
            axis = plot.y_axis(i)
            if not axis.enabled:
                continue
            if axis.is_opposite():
                axis.datum1 -= delta_r
                axis.datum2 -= delta_r if count_r > 1 else 0
                count_r += 1
            else:
                axis.datum1 += delta_l
                axis.datum2 += delta_l if count_l > 1 else 0
                count_l += 1
    return pad_l, pad_r


def _locate_ticks(axis, pixels: float, vertical: bool, first_pass: bool) -> None:
    """Fill an axis' ticker: its custom ticks, then the locator's."""
    ticker = axis.ticker
    if first_pass:
        # begin_plot's Axis.reset already reset the ticker (and took the tags'
        # late sizes); reset again and those sizes are lost
        ticker.ticks = []
        ticker.reset_max_size = ticker.max_size
    else:
        ticker.ticks = []
        ticker.max_size = getattr(ticker, "reset_max_size", (0.0, 0.0))
    if axis.scale == I.SCALE_TIME:
        ticker.levels = 2
    custom = getattr(axis, "custom_ticks", None)
    if custom is not None:
        I.add_ticks_custom(custom[0], custom[1], ticker, axis.formatter, axis.formatter_data)
    if axis.will_render() and axis.show_default_ticks and pixels > 0:
        axis.locator(ticker, axis.range, pixels, vertical, axis.formatter, axis.formatter_data)


def _layout(plot, first_pass: bool) -> None:
    """The layout half of ``SetupFinish``: rects, tickers, pixel spans."""
    style = gp.style
    fr = plot.frame_rect
    plot.canvas_rect = (fr[0] + style.plot_padding[0], fr[1] + style.plot_padding[1],
                        fr[2] - style.plot_padding[0], fr[3] - style.plot_padding[1])
    plot.axes_rect = fr
    legend = plot.items.legend
    if (not has_flag(plot.flags, I.FLAGS_NO_LEGEND) and plot.items.get_legend_count() > 0
            and has_flag(legend.flags, I.LEGEND_FLAGS_OUTSIDE)):
        horz = has_flag(legend.flags, I.LEGEND_FLAGS_HORIZONTAL)
        lsize = I.calc_legend_size(plot.items, style.legend_inner_padding, style.legend_spacing, not horz)
        loc = legend.location
        west = has_flag(loc, I.LOCATION_WEST) and not has_flag(loc, I.LOCATION_EAST)
        east = has_flag(loc, I.LOCATION_EAST) and not has_flag(loc, I.LOCATION_WEST)
        north = has_flag(loc, I.LOCATION_NORTH) and not has_flag(loc, I.LOCATION_SOUTH)
        south = has_flag(loc, I.LOCATION_SOUTH) and not has_flag(loc, I.LOCATION_NORTH)
        c, a = list(plot.canvas_rect), list(plot.axes_rect)
        if (west and not horz) or (west and horz and not north and not south):
            c[0] += lsize[0] + style.legend_padding[0]
            a[0] += lsize[0] + style.plot_padding[0]
        if (east and not horz) or (east and horz and not north and not south):
            c[2] -= lsize[0] + style.legend_padding[0]
            a[2] -= lsize[0] + style.plot_padding[0]
        if (north and horz) or (north and not horz and not west and not east):
            c[1] += lsize[1] + style.legend_padding[1]
            a[1] += lsize[1] + style.plot_padding[1]
        if (south and horz) or (south and not horz and not west and not east):
            c[3] -= lsize[1] + style.legend_padding[1]
            a[3] -= lsize[1] + style.plot_padding[1]
        plot.canvas_rect, plot.axes_rect = tuple(c), tuple(a)
    pad_top = pad_bot = pad_left = pad_right = 0.0
    title_size = I.calc_text_size(plot.title) if plot.has_title() else (0.0, 0.0)
    if title_size[0] > 0:
        pad_top += title_size[1] + style.label_padding[1]
        a = list(plot.axes_rect)
        a[1] += style.plot_padding[1] + pad_top
        plot.axes_rect = tuple(a)
    pad_top, pad_bot = _pad_and_datum_axes_x(plot, pad_top, pad_bot, gp.current_alignment_h)
    plot_height = (plot.canvas_rect[3] - plot.canvas_rect[1]) - pad_top - pad_bot
    for i in range(I.NUM_Y_AXES):
        axis = plot.y_axis(i)
        if axis.enabled:
            _locate_ticks(axis, plot_height, True, first_pass)
    pad_left, pad_right = _pad_and_datum_axes_y(plot, pad_left, pad_right, gp.current_alignment_v)
    plot_width = (plot.canvas_rect[2] - plot.canvas_rect[0]) - pad_left - pad_right
    for i in range(I.NUM_X_AXES):
        axis = plot.x_axis(i)
        if axis.enabled:
            _locate_ticks(axis, plot_width, False, first_pass)
    title_pad = title_size[1] + style.label_padding[1] if title_size[0] > 0 else 0.0
    pad_top, pad_bot = _pad_and_datum_axes_x(plot, title_pad, 0.0, gp.current_alignment_h)
    if title_size[0] > 0:
        a = list(plot.axes_rect)
        a[1] = fr[1] + style.plot_padding[1] + title_pad
        plot.axes_rect = tuple(a)
    cr = plot.canvas_rect
    plot.plot_rect = (cr[0] + pad_left, cr[1] + pad_top, cr[2] - pad_right, cr[3] - pad_bot)
    pr = plot.plot_rect
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        ax.hover_rect = (pr[0], min(ax.datum1, ax.datum2), pr[2], max(ax.datum1, ax.datum2))
        ax.pixel_min = pr[2] if ax.is_inverted() else pr[0]
        ax.pixel_max = pr[0] if ax.is_inverted() else pr[2]
        ax.update_transform_cache()
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        ax.hover_rect = (min(ax.datum1, ax.datum2), pr[1], max(ax.datum1, ax.datum2), pr[3])
        ax.pixel_min = pr[1] if ax.is_inverted() else pr[3]
        ax.pixel_max = pr[3] if ax.is_inverted() else pr[1]
        ax.update_transform_cache()
    if has_flag(plot.flags, I.FLAGS_EQUAL):
        for i in range(I.NUM_X_AXES):
            x_axis = plot.x_axis(i)
            if x_axis.ortho_axis is None:
                continue
            xar, yar = x_axis.get_aspect(), x_axis.ortho_axis.get_aspect()
            if x_axis.has_range:
                x_axis.ortho_axis.set_aspect(xar)
            elif not I.almost_equal(xar, yar) and not x_axis.ortho_axis.is_input_locked():
                x_axis.set_aspect(yar)


def setup_finish() -> None:
    """``SetupFinish``: lock the setup, lay the plot out, take the input."""
    plot = _require_plot("setup_finish")
    plot.setup_locked = True
    for axis in plot.axes:
        if axis.enabled:
            axis.constrain()
            if axis.can_init_fit() and (not plot.initialized or axis.follow):
                plot.fit_this_frame = axis.fit_this_frame = True
        if axis.formatter is None:
            axis.formatter = I.formatter_default
            axis.formatter_data = axis.format_spec if axis.has_format_spec else I.IMPLOT_LABEL_FORMAT
        if axis.locator is None:
            axis.locator = I.locator_default
    equal = has_flag(plot.flags, I.FLAGS_EQUAL)
    for ix, iy in zip(range(I.AXIS_X1, I.AXIS_Y1), range(I.AXIS_Y1, I.AXIS_COUNT)):
        xa, ya = plot.axes[ix], plot.axes[iy]
        if xa.enabled and ya.enabled:
            if xa.ortho_axis is None:
                xa.ortho_axis = ya
            if ya.ortho_axis is None:
                ya.ortho_axis = xa
        elif xa.enabled:
            if xa.ortho_axis is None and not equal:
                xa.ortho_axis = plot.axes[I.AXIS_Y1]
        elif ya.enabled:
            if ya.ortho_axis is None and not equal:
                ya.ortho_axis = plot.axes[I.AXIS_X1]
    _layout(plot, first_pass=True)
    if not has_flag(plot.flags, I.FLAGS_NO_INPUTS):
        _update_input(plot)
    for i, axis in enumerate(plot.axes):
        if gp.next_plot_data.fit[i] or axis.is_auto_fitting():
            plot.fit_this_frame = axis.fit_this_frame = True
    plot.snapshot = [_copy.copy(ax) for ax in plot.axes]
    plot.items.legend.reset()


# --------------------------------------------------------------------------- #
# [SECTION] Input
# --------------------------------------------------------------------------- #
MOUSE_CURSOR_DRAG_THRESHOLD = 5.0
BOX_SELECT_DRAG_THRESHOLD = 4.0
_BUTTONS = (0, 1, 2)


def _drag_delta(io, button: int):
    """``GetMouseDragDelta`` with the default lock threshold."""
    if io.mouse_down[button] or io.mouse_released[button]:
        dx, dy = io.mouse_drag_delta(button)
        if dx * dx + dy * dy >= 36.0:
            return dx, dy
    return 0.0, 0.0


def _plot_button_behavior(rect, item_id, buttons=_BUTTONS):
    """``ButtonBehavior`` with ``AllowOverlap | PressedOnClick |
    PressedOnDoubleClick`` over several mouse buttons: ``(pressed, hovered, held)``."""
    ctx = _ctx()
    io = ctx.io
    box = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
    hovered = box[2] > 0 and box[3] > 0 and ctx.item_hoverable(box, item_id)
    pressed = False
    if hovered:
        for b in buttons:
            if io.mouse_clicked[b] or io.mouse_double_clicked[b]:
                ctx.set_active_id(item_id)
                pressed = True
    held = ctx.active_id == item_id and any(io.mouse_down[b] for b in buttons)
    if ctx.active_id == item_id and not any(io.mouse_down[b] for b in buttons) and not pressed:
        ctx.clear_active_id()
    if hovered or held:
        ctx.hovered_id_allow_overlap = True
        ctx.active_id_allow_overlap = True
    return pressed, hovered, held


def _interacted(axis) -> None:
    """emtk: the user moved this axis -- it stops following its data."""
    axis.follow = False
    axis.fit_this_frame = False


def _update_input(plot) -> bool:
    """``UpdateInput``."""
    changed = False
    io = _io()
    imap = gp.input_map
    mods = I.key_mods(io)
    pressed, plot.hovered, plot.held = _plot_button_behavior(plot.plot_rect, plot.id)
    if pressed:
        if (not has_flag(plot.flags, I.FLAGS_NO_BOX_SELECT) and io.mouse_clicked[imap.select]
                and has_flag(mods, imap.select_mod)):
            plot.selecting = True
            plot.select_start = tuple(io.mouse_pos)
            plot.select_rect = (0.0, 0.0, 0.0, 0.0)
        if io.mouse_double_clicked[imap.fit]:
            plot.fit_this_frame = True
            for ax in plot.axes:
                ax.fit_this_frame = True
                ax.follow = True
    can_pan = io.mouse_down[imap.pan] and has_flag(mods, imap.pan_mod)
    plot.held = plot.held and can_pan
    x_hov = [False] * I.NUM_X_AXES
    x_held = [False] * I.NUM_X_AXES
    y_hov = [False] * I.NUM_Y_AXES
    y_held = [False] * I.NUM_Y_AXES
    for i in range(I.NUM_X_AXES):
        xax = plot.x_axis(i)
        if xax.enabled:
            clk, xax.hovered, xax.held = _plot_button_behavior(xax.hover_rect, xax.id)
            if clk and io.mouse_double_clicked[imap.fit]:
                plot.fit_this_frame = xax.fit_this_frame = True
                xax.follow = True
            xax.held = xax.held and can_pan
            x_hov[i] = xax.hovered or plot.hovered
            x_held[i] = xax.held or plot.held
    for i in range(I.NUM_Y_AXES):
        yax = plot.y_axis(i)
        if yax.enabled:
            clk, yax.hovered, yax.held = _plot_button_behavior(yax.hover_rect, yax.id)
            if clk and io.mouse_double_clicked[imap.fit]:
                plot.fit_this_frame = yax.fit_this_frame = True
                yax.follow = True
            yax.held = yax.held and can_pan
            y_hov[i] = yax.hovered or plot.hovered
            y_held[i] = yax.held or plot.held
    if imap.override_mod != 0 and mods == imap.override_mod:
        return False
    axis_equal = has_flag(plot.flags, I.FLAGS_EQUAL)
    xs_ = [plot.x_axis(i) for i in range(I.NUM_X_AXES)]
    ys_ = [plot.y_axis(i) for i in range(I.NUM_Y_AXES)]
    any_x_hov = plot.hovered or any(a.enabled and a.hovered for a in xs_)
    any_x_held = plot.held or any(a.enabled and a.held for a in xs_)
    any_y_hov = plot.hovered or any(a.enabled and a.hovered for a in ys_)
    any_y_held = plot.held or any(a.enabled and a.held for a in ys_)
    any_hov = any_x_hov or any_y_hov
    any_held = any_x_held or any_y_held
    sd = _drag_delta(io, imap.select)
    pd = _drag_delta(io, imap.pan)
    selecting = plot.selecting and sd[0] ** 2 + sd[1] ** 2 > MOUSE_CURSOR_DRAG_THRESHOLD
    panning = any_held and pd[0] ** 2 + pd[1] ** 2 > MOUSE_CURSOR_DRAG_THRESHOLD
    if io.mouse_released[imap.menu] and not plot.context_locked:
        gp.open_context_this_frame = True
    if selecting or panning:
        plot.context_locked = True
    elif not (io.mouse_down[imap.menu] or io.mouse_released[imap.menu]):
        plot.context_locked = False
    dx, dy = io.mouse_delta
    pr = plot.plot_rect
    if any_held and not plot.selecting:
        for i, x_axis in enumerate(xs_):
            if x_held[i] and not x_axis.is_input_locked():
                increasing = dx > 0 if x_axis.is_inverted() else dx < 0
                if dx != 0 and not x_axis.is_pan_locked(increasing):
                    plot_l = x_axis.pixels_to_plot(pr[0] - dx)
                    plot_r = x_axis.pixels_to_plot(pr[2] - dx)
                    x_axis.set_min(plot_r if x_axis.is_inverted() else plot_l)
                    x_axis.set_max(plot_l if x_axis.is_inverted() else plot_r)
                    if axis_equal and x_axis.ortho_axis is not None:
                        x_axis.ortho_axis.set_aspect(x_axis.get_aspect())
                    _interacted(x_axis)
                    changed = True
        for i, y_axis in enumerate(ys_):
            if y_held[i] and not y_axis.is_input_locked():
                increasing = dy < 0 if y_axis.is_inverted() else dy > 0
                if dy != 0 and not y_axis.is_pan_locked(increasing):
                    plot_t = y_axis.pixels_to_plot(pr[1] - dy)
                    plot_b = y_axis.pixels_to_plot(pr[3] - dy)
                    y_axis.set_min(plot_t if y_axis.is_inverted() else plot_b)
                    y_axis.set_max(plot_b if y_axis.is_inverted() else plot_t)
                    if axis_equal and y_axis.ortho_axis is not None:
                        y_axis.ortho_axis.set_aspect(y_axis.get_aspect())
                    _interacted(y_axis)
                    changed = True
    if any_hov and has_flag(mods, imap.zoom_mod):
        zoom_rate = imap.zoom_rate
        if io.mouse_wheel == 0.0:
            zoom_rate = 0.0
        elif io.mouse_wheel > 0:
            zoom_rate = (-zoom_rate) / (1.0 + (2.0 * zoom_rate))
        rw, rh = pr[2] - pr[0], pr[3] - pr[1]
        tx = I.remap(io.mouse_pos[0], pr[0], pr[2], 0.0, 1.0)
        ty = I.remap(io.mouse_pos[1], pr[1], pr[3], 0.0, 1.0)
        equal_ref = None
        for i, x_axis in enumerate(xs_):
            equal_zoom = axis_equal and x_axis.ortho_axis is not None
            equal_locked = equal_zoom and x_axis.ortho_axis.is_input_locked()
            if x_hov[i] and not x_axis.is_input_locked() and not equal_locked and zoom_rate != 0.0:
                plot_l = x_axis.pixels_to_plot(pr[0] - rw * tx * zoom_rate)
                plot_r = x_axis.pixels_to_plot(pr[2] + rw * (1 - tx) * zoom_rate)
                x_axis.set_min(plot_r if x_axis.is_inverted() else plot_l)
                x_axis.set_max(plot_l if x_axis.is_inverted() else plot_r)
                if equal_zoom:
                    equal_ref = x_axis
                _interacted(x_axis)
                changed = True
        for i, y_axis in enumerate(ys_):
            equal_zoom = axis_equal and y_axis.ortho_axis is not None
            equal_locked = equal_zoom and y_axis.ortho_axis.is_input_locked()
            if y_hov[i] and not y_axis.is_input_locked() and not equal_locked and zoom_rate != 0.0:
                plot_t = y_axis.pixels_to_plot(pr[1] - rh * ty * zoom_rate)
                plot_b = y_axis.pixels_to_plot(pr[3] + rh * (1 - ty) * zoom_rate)
                y_axis.set_min(plot_t if y_axis.is_inverted() else plot_b)
                y_axis.set_max(plot_b if y_axis.is_inverted() else plot_t)
                if equal_zoom:
                    equal_ref = y_axis
                _interacted(y_axis)
                changed = True
        if equal_ref is not None and equal_ref.ortho_axis is not None:
            equal_ref.ortho_axis.set_aspect(equal_ref.get_aspect())
    if plot.selecting:
        mx, my = io.mouse_pos
        d = (plot.select_start[0] - mx, plot.select_start[1] - my)
        x_can_change = not has_flag(mods, imap.select_horz_mod) and abs(d[0]) > 2
        y_can_change = not has_flag(mods, imap.select_vert_mod) and abs(d[1]) > 2
        if io.mouse_released[imap.select]:
            for x_axis in xs_:
                if not x_axis.is_input_locked() and x_can_change:
                    p1 = x_axis.pixels_to_plot(plot.select_start[0])
                    p2 = x_axis.pixels_to_plot(mx)
                    x_axis.set_min(min(p1, p2))
                    x_axis.set_max(max(p1, p2))
                    _interacted(x_axis)
                    changed = True
            for y_axis in ys_:
                if not y_axis.is_input_locked() and y_can_change:
                    p1 = y_axis.pixels_to_plot(plot.select_start[1])
                    p2 = y_axis.pixels_to_plot(my)
                    y_axis.set_min(min(p1, p2))
                    y_axis.set_max(max(p1, p2))
                    _interacted(y_axis)
                    changed = True
            if x_can_change or y_can_change or (has_flag(mods, imap.select_horz_mod)
                                                and has_flag(mods, imap.select_vert_mod)):
                gp.open_context_this_frame = False
            plot.selected = plot.selecting = False
        elif io.mouse_released[imap.select_cancel]:
            plot.selected = plot.selecting = False
            gp.open_context_this_frame = False
        elif d[0] ** 2 + d[1] ** 2 > BOX_SELECT_DRAG_THRESHOLD:
            if plot.is_input_locked():
                gp.open_context_this_frame = False
                plot.selected = False
            else:
                full_w = has_flag(mods, imap.select_horz_mod) or all(
                    a.is_input_locked() for a in xs_ if a.enabled)
                full_h = has_flag(mods, imap.select_vert_mod) or all(
                    a.is_input_locked() for a in ys_ if a.enabled)
                sx0 = pr[0] if full_w else min(plot.select_start[0], mx)
                sx1 = pr[2] if full_w else max(plot.select_start[0], mx)
                sy0 = pr[1] if full_h else min(plot.select_start[1], my)
                sy1 = pr[3] if full_h else max(plot.select_start[1], my)
                plot.select_rect = (sx0 - pr[0], sy0 - pr[1], sx1 - pr[0], sy1 - pr[1])
                plot.selected = True
        else:
            plot.selected = False
    return changed


# --------------------------------------------------------------------------- #
# [SECTION] Rendering helpers
# --------------------------------------------------------------------------- #
def _dl():
    return _ctx().draw


def _fill(r, col) -> None:
    """``AddRectFilled`` for an ``(x0, y0, x1, y1)`` rect."""
    if col is None or col[3] == 0:
        return
    x0, y0, x1, y1 = r
    if x1 > x0 and y1 > y0:
        _dl().p.fill_rect(x0, y0, x1 - x0, y1 - y0, col)


def _stroke(r, col, thickness: float = 1.0) -> None:
    """``AddRect``: a one-pixel-per-``thickness`` outline on the rect's edge."""
    if col is None or col[3] == 0:
        return
    x0, y0, x1, y1 = r
    p = _dl().p
    t = max(float(thickness), 1.0)
    p.fill_rect(x0, y0, x1 - x0, t, col)
    p.fill_rect(x0, y1 - t, x1 - x0, t, col)
    p.fill_rect(x0, y0 + t, t, y1 - y0 - 2 * t, col)
    p.fill_rect(x1 - t, y0 + t, t, y1 - y0 - 2 * t, col)


def _line_h(x1, x2, y, col, thickness: float = 1.0) -> None:
    """``AddLineH``."""
    if x2 < x1:
        x1, x2 = x2, x1
    _dl().p.fill_rect(x1, y - thickness * 0.5, x2 - x1, thickness, col)


def _line_v(x, y1, y2, col, thickness: float = 1.0) -> None:
    """``AddLineV``."""
    if y2 < y1:
        y1, y2 = y2, y1
    _dl().p.fill_rect(x - thickness * 0.5, y1, thickness, y2 - y1, col)


def _add_text(pos, col, text: str) -> None:
    """``AddText``, one line per ``\\n``."""
    lh = I.text_line_height()
    for k, line in enumerate(str(text).split("\n")):
        if line:
            _dl().add_text((pos[0], pos[1] + k * lh), col, line)


def _add_text_centered(top_center, col, text: str) -> None:
    """``AddTextCentered``."""
    lh = I.text_line_height()
    for k, line in enumerate(I.split_label(text).split("\n")):
        w = I.calc_text_size(line)[0]
        _dl().add_text((top_center[0] - w * 0.5, top_center[1] + k * lh), col, line)


_ROTATION_SIGNATURE: dict = {}


def _add_text_vertical(pos, col, text: str) -> None:
    """``AddTextVertical``: text running bottom to top, *pos* its bottom-left.

    A painter with the protocol's ``text_rotated`` turns it; one without
    draws the text flat, which is still readable.
    """
    text = I.split_label(text)
    if not text:
        return
    p = _dl().p
    tw, th = I.calc_text_size(text)
    op = getattr(p, "text_rotated", None)
    kind = _ROTATION_SIGNATURE.get(type(p))
    if kind is None:
        kind = "flat"
        if callable(op):
            try:
                if len(_inspect.signature(op).parameters) >= 8:
                    kind = "protocol"
            except (TypeError, ValueError):
                pass
        _ROTATION_SIGNATURE[type(p)] = kind
    if kind == "protocol":
        cx, cy = pos[0] + th * 0.5, pos[1] - tw * 0.5
        from .painter import ALIGN_LEFT, ALIGN_VCENTER
        op(cx - tw * 0.5, cy - th * 0.5, tw, th, ALIGN_LEFT | ALIGN_VCENTER, text, col, -90.0)
        return
    _dl().add_text((pos[0], pos[1] - th), col, text)


def _render_grid_lines_x(ticker, rect, col_maj, col_min, size_maj, size_min) -> None:
    """``RenderGridLinesX``."""
    width = rect[2] - rect[0]
    density = ticker.tick_count() / width if width > 0 else 1.0
    fade = min(max(I.remap(density, 0.1, 0.2, 1.0, 0.0), 0.0), 1.0)
    col_min = (col_min[0], col_min[1], col_min[2], int(col_min[3] * fade))
    for tk in ticker.ticks:
        if tk.pixel_pos < rect[0] or tk.pixel_pos > rect[2]:
            continue
        if tk.level == 0:
            if tk.major:
                _line_v(tk.pixel_pos, rect[1], rect[3], col_maj, size_maj)
            elif density < 0.2:
                _line_v(tk.pixel_pos, rect[1], rect[3], col_min, size_min)


def _render_grid_lines_y(ticker, rect, col_maj, col_min, size_maj, size_min) -> None:
    """``RenderGridLinesY``."""
    height = rect[3] - rect[1]
    density = ticker.tick_count() / height if height > 0 else 1.0
    fade = min(max(I.remap(density, 0.1, 0.2, 1.0, 0.0), 0.0), 1.0)
    col_min = (col_min[0], col_min[1], col_min[2], int(col_min[3] * fade))
    for tk in ticker.ticks:
        if tk.pixel_pos < rect[1] or tk.pixel_pos > rect[3]:
            continue
        if tk.major:
            _line_h(rect[0], rect[2], tk.pixel_pos, col_maj, size_maj)
        elif density < 0.2:
            _line_h(rect[0], rect[2], tk.pixel_pos, col_min, size_min)


def _label_axis_value(axis, value: float, round_: bool = False) -> str:
    """``LabelAxisValue``."""
    if axis.locator is I.locator_time:
        pr = gp.current_plot.plot_rect
        span = (pr[3] - pr[1]) if axis.vertical else (pr[2] - pr[0])
        unit = I.get_unit_for_range(axis.range_size() / (span / 100.0) if span else 1.0)
        return I.format_date_time(I.PlotTime.from_double(value),
                                  I.get_date_time_fmt(I.TIME_FORMAT_MOUSE_CURSOR, unit))
    if round_:
        ticks = axis.ticker.ticks
        rng = (ticks[1].plot_pos - ticks[0].plot_pos) if len(ticks) > 1 else axis.range_size()
        value = I.round_to(value, I.precision(rng))
    return I.call_formatter(axis.formatter or I.formatter_default, value,
                            axis.formatter_data if axis.formatter else I.IMPLOT_LABEL_FORMAT)


def _show_legend_entries(items, legend_bb, hovered: bool, pad, spacing, vertical: bool) -> bool:
    """``ShowLegendEntries``: draw the entries; a click toggles an item."""
    ctx = _ctx()
    txt_ht = I.text_line_height()
    icon_size = txt_ht
    icon_shrink = 2.0
    col_txt = I.get_style_color_u32(I.COL_LEGEND_TEXT)
    col_txt_dis = I.alpha_u32(col_txt, 0.25)
    n = items.get_legend_count()
    if n < 1:
        return hovered
    indices = list(range(n))
    if has_flag(items.legend.flags, I.LEGEND_FLAGS_SORT) and n > 1:
        indices.sort(key=lambda i: items.get_legend_label(i))
    any_item_hovered = False
    sum_label_width = 0.0
    disabled = _rgba(ctx.style.color(_core.Col.TEXT_DISABLED))
    for i in range(n):
        idx = indices[n - 1 - i] if has_flag(items.legend.flags, I.LEGEND_FLAGS_REVERSE) else indices[i]
        item = items.get_legend_item(idx)
        label = item.label
        label_width = I.calc_text_size(label)[0]
        if vertical:
            top_left = (legend_bb[0] + pad[0], legend_bb[1] + pad[1] + i * (txt_ht + spacing[1]))
        else:
            top_left = (legend_bb[0] + pad[0] + i * (icon_size + spacing[0]) + sum_label_width,
                        legend_bb[1] + pad[1])
        sum_label_width += label_width
        icon_bb = (top_left[0] + icon_shrink, top_left[1] + icon_shrink,
                   top_left[0] + icon_size - icon_shrink, top_left[1] + icon_size - icon_shrink)
        label_bb = (top_left[0], top_left[1], top_left[0] + label_width + icon_size, top_left[1] + icon_size)
        col_item = I.alpha_u32(item.color, 1.0)
        button = (icon_bb[0], icon_bb[1], label_bb[2] - icon_bb[0], label_bb[3] - icon_bb[1])
        item_hov = item_hld = item_clk = False
        if not has_flag(items.legend.flags, I.LEGEND_FLAGS_NO_BUTTONS):
            ctx.set_next_item_allow_overlap()
            item_hov, item_hld, item_clk = ctx.button_behavior(button, ("##legend", item.id))
        if item_clk:
            item.show = not item.show
        can_hover = item_hov and (not has_flag(items.legend.flags, I.LEGEND_FLAGS_NO_HIGHLIGHT_ITEM)
                                  or not has_flag(items.legend.flags, I.LEGEND_FLAGS_NO_HIGHLIGHT_AXIS))
        if can_hover:
            item.legend_hover_rect = (icon_bb[0], icon_bb[1], label_bb[2], label_bb[3])
            item.legend_hovered = True
            col_txt_hl = I.mix_u32(col_txt, col_item, 64)
            any_item_hovered = True
        else:
            col_txt_hl = col_txt
        if item_hld:
            col_icon = I.alpha_u32(col_item, 0.5) if item.show else I.alpha_u32(disabled, 0.5)
        elif item_hov:
            col_icon = I.alpha_u32(col_item, 0.75) if item.show else I.alpha_u32(disabled, 0.75)
        else:
            col_icon = col_item if item.show else col_txt_dis
        _fill(icon_bb, col_icon)
        if label:
            _dl().add_text((top_left[0] + icon_size, top_left[1]), col_txt_hl if item.show else col_txt_dis,
                           label)
    return hovered and not any_item_hovered


def _render_legend(items, outer, pad, flags_owner_no_legend: bool, menus_allowed: bool, owner_hovered):
    """The legend section of ``EndPlot``/``EndSubplots``. Returns whether a
    right-click on it may open the legend's context menu."""
    style = gp.style
    ctx = _ctx()
    io = ctx.io
    legend = items.legend
    horz = has_flag(legend.flags, I.LEGEND_FLAGS_HORIZONTAL)
    size = I.calc_legend_size(items, style.legend_inner_padding, style.legend_spacing, not horz)
    pos = I.get_location_pos(outer, size, legend.location, pad)
    legend.rect = (pos[0], pos[1], pos[0] + size[0], pos[1] + size[1])
    legend.rect_clamped, scrollable = I.clamp_legend_rect(legend.rect, outer, pad)
    rc = legend.rect_clamped
    _press, legend.hovered, legend.held = _plot_button_behavior(rc, items.id)
    legend.hovered = legend.hovered or (owner_hovered and I.rect_contains(rc, io.mouse_pos))
    if scrollable:
        sx, sy = legend.scroll
        if legend.hovered and io.mouse_wheel != 0.0:
            step = min(2 * I.text_line_height(), (legend.rect[2] - legend.rect[0]) * 0.67)
            sx += step * io.mouse_wheel
            sy += step * io.mouse_wheel
        min_x = (rc[2] - rc[0]) - (legend.rect[2] - legend.rect[0])
        min_y = (rc[3] - rc[1]) - (legend.rect[3] - legend.rect[1])
        sx = min(max(sx, min_x), 0.0)
        sy = min(max(sy, min_y), 0.0)
        legend.scroll = (sx, sy)
        off = (sx, 0.0) if horz else (0.0, sy)
        dx, dy = rc[0] - legend.rect[0] + off[0], rc[1] - legend.rect[1] + off[1]
        legend.rect = (legend.rect[0] + dx, legend.rect[1] + dy, legend.rect[2] + dx, legend.rect[3] + dy)
    else:
        legend.scroll = (0.0, 0.0)
    dl = _dl()
    dl.push_clip_rect((rc[0], rc[1]), (rc[2], rc[3]))
    _fill(rc, I.get_style_color_u32(I.COL_LEGEND_BG))
    contextable = _show_legend_entries(items, legend.rect, legend.hovered, style.legend_inner_padding,
                                       style.legend_spacing, not horz) \
        and not has_flag(legend.flags, I.LEGEND_FLAGS_NO_MENUS)
    _stroke(rc, I.get_style_color_u32(I.COL_LEGEND_BORDER))
    dl.pop_clip_rect()
    return contextable and menus_allowed


# --------------------------------------------------------------------------- #
# [SECTION] EndPlot
# --------------------------------------------------------------------------- #
def _axes_moved(plot) -> bool:
    snap = getattr(plot, "snapshot", None)
    if not snap:
        return True
    for a, b in zip(plot.axes, snap):
        if (a.range_min, a.range_max, a.pixel_min, a.pixel_max) != (b.range_min, b.range_max,
                                                                    b.pixel_min, b.pixel_max):
            return True
    return False


def _apply_fits(plot) -> None:
    """The ``FIT DATA`` section of ``EndPlot`` -- run before drawing here."""
    if not plot.fit_this_frame:
        return
    style = gp.style
    equal = has_flag(plot.flags, I.FLAGS_EQUAL)
    for i in range(I.NUM_X_AXES):
        x_axis = plot.x_axis(i)
        if x_axis.fit_this_frame:
            x_axis.apply_fit(style.fit_padding[0])
            if equal and x_axis.ortho_axis is not None:
                aspect = x_axis.get_aspect()
                y_axis = x_axis.ortho_axis
                if y_axis.fit_this_frame:
                    y_axis.apply_fit(style.fit_padding[1])
                    y_axis.fit_this_frame = False
                    aspect = max(aspect, y_axis.get_aspect())
                x_axis.set_aspect(aspect)
                y_axis.set_aspect(aspect)
    for i in range(I.NUM_Y_AXES):
        y_axis = plot.y_axis(i)
        if y_axis.fit_this_frame:
            y_axis.apply_fit(style.fit_padding[1])
            if equal and y_axis.ortho_axis is not None:
                aspect = y_axis.get_aspect()
                x_axis = y_axis.ortho_axis
                if x_axis.fit_this_frame:
                    x_axis.apply_fit(style.fit_padding[0])
                    x_axis.fit_this_frame = False
                    aspect = max(x_axis.get_aspect(), aspect)
                x_axis.set_aspect(aspect)
                y_axis.set_aspect(aspect)
    for ax in plot.axes:
        ax.fit_this_frame = False
    plot.fit_this_frame = False


def _render_background(plot) -> None:
    """The ``RENDER`` section of ``SetupFinish``."""
    style = gp.style
    txt_height = I.text_line_height()
    if not has_flag(plot.flags, I.FLAGS_NO_FRAME):
        _fill(plot.frame_rect, I.get_style_color_u32(I.COL_FRAME_BG))
    _fill(plot.plot_rect, I.get_style_color_u32(I.COL_PLOT_BG))
    for axis in plot.axes:
        if axis.will_render():
            for tk in axis.ticker.ticks:
                tk.pixel_pos = float(round(axis.plot_to_pixels(tk.plot_pos))) \
                    if math.isfinite(axis.plot_to_pixels(tk.plot_pos)) else -1e9
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        if ax.enabled and ax.has_grid_lines() and not ax.is_foreground():
            _render_grid_lines_x(ax.ticker, plot.plot_rect, ax.color_maj, ax.color_min,
                                 style.major_grid_size[0], style.minor_grid_size[0])
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        if ax.enabled and ax.has_grid_lines() and not ax.is_foreground():
            _render_grid_lines_y(ax.ticker, plot.plot_rect, ax.color_maj, ax.color_min,
                                 style.major_grid_size[1], style.minor_grid_size[1])
    pr = plot.plot_rect
    fr = plot.frame_rect
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        if not ax.enabled:
            continue
        _axis_background(plot, ax)
        tkr = ax.ticker
        opp = ax.is_opposite()
        if ax.has_label():
            lsize = I.calc_text_size(ax.label)
            off = ((tkr.max_size[1] + style.label_padding[1] if ax.has_tick_labels() else 0.0)
                   + (tkr.levels - 1) * (txt_height + style.label_padding[1]) + style.label_padding[1])
            _add_text(((pr[0] + pr[2]) * 0.5 - lsize[0] * 0.5,
                       ax.datum1 - off - lsize[1] if opp else ax.datum1 + off), ax.color_txt, ax.label)
        if ax.has_tick_labels():
            for tk in tkr.ticks:
                datum = ax.datum1 + ((-style.label_padding[1] - txt_height
                                      - tk.level * (txt_height + style.label_padding[1])) if opp
                                     else style.label_padding[1] + tk.level * (txt_height + style.label_padding[1]))
                if tk.show_label and tk.text and pr[0] - 1 <= tk.pixel_pos <= pr[2] + 1:
                    _add_text((_inside(tk.pixel_pos - 0.5 * tk.label_size[0], tk.label_size[0],
                                       fr[0], fr[2]), datum), ax.color_txt, tk.text)
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        if not ax.enabled:
            continue
        _axis_background(plot, ax)
        tkr = ax.ticker
        opp = ax.is_opposite()
        if ax.has_label():
            tw, th = I.calc_text_size(ax.label)
            off = (tkr.max_size[0] + style.label_padding[0] if ax.has_tick_labels() else 0.0) \
                + style.label_padding[0]
            _add_text_vertical((ax.datum1 + off if opp else ax.datum1 - off - th,
                                (pr[1] + pr[3]) * 0.5 + tw * 0.5), ax.color_txt, ax.label)
        if ax.has_tick_labels():
            for tk in tkr.ticks:
                datum = ax.datum1 + (style.label_padding[0] if opp
                                     else -style.label_padding[0] - tk.label_size[0])
                if tk.show_label and tk.text and pr[1] - 1 <= tk.pixel_pos <= pr[3] + 1:
                    _add_text((datum, _inside(tk.pixel_pos - 0.5 * tk.label_size[1],
                                              tk.label_size[1], fr[1], fr[3])),
                              ax.color_txt, tk.text)


def _inside(start: float, size: float, lo: float, hi: float) -> float:
    """A tick label's start, moved inside ``[lo, hi]`` when it would stick out.

    emtk's own: a label centred on the first or last tick of a plot with no
    padding overhangs the frame by half its width and is cut by whatever is
    drawn beside the plot. Shifted in, it stays whole and stays next to its
    tick. A label wider than the frame keeps its centred place.
    """
    if size >= hi - lo:
        return start
    return min(max(start, lo), hi - size)


def _axis_background(plot, ax) -> None:
    if (ax.hovered or ax.held) and not plot.held and not has_flag(ax.flags, I.AXIS_FLAGS_NO_HIGHLIGHT):
        _fill(ax.hover_rect, ax.color_act if ax.held else ax.color_hov)
    elif ax.color_hili[3] != 0:
        _fill(ax.hover_rect, ax.color_hili)
        ax.color_hili = (0, 0, 0, 0)
    elif ax.color_bg[3] != 0:
        _fill(ax.hover_rect, ax.color_bg)


def _replay_queue(plot) -> None:
    """Run the queued renderers, each on its axes, inside the plot clip."""
    dl = _dl()
    gp.digital_plot_item_cnt = 0
    gp.digital_plot_offset = 0
    saved = (plot.current_x, plot.current_y)
    pr = plot.plot_rect
    for xi, yi, render, expand, clip in plot.queue:
        plot.current_x, plot.current_y = xi, yi
        if clip:
            dl.push_clip_rect((pr[0] - expand, pr[1] - expand), (pr[2] + expand, pr[3] + expand))
        try:
            render()
        finally:
            if clip:
                dl.pop_clip_rect()
    plot.current_x, plot.current_y = saved
    plot.queue = []


def end_plot() -> None:
    """``EndPlot``: fit, draw, show the legend and menus, remember."""
    if gp.current_plot is None:
        raise RuntimeError("implot.end_plot() without a matching begin_plot()")
    setup_lock()
    plot = gp.current_plot
    ctx = _ctx()
    io = ctx.io
    style = gp.style
    dl = _dl()
    try:
        _apply_fits(plot)
        if plot.setup_dirty or _axes_moved(plot):
            _layout(plot, first_pass=False)
        _render_background(plot)
        _replay_queue(plot)
        _end_plot_render(plot, ctx, io, style, dl)
    finally:
        for axis in plot.axes:
            axis.push_links()
        if gp.current_items is plot.items:
            gp.current_items = None
        for item in plot.items.items:
            item.seen_this_frame = False
        plot.initialized = True
        gp.last_plot_rect = plot.plot_rect
        gp.last_plot = plot
        subplot = gp.current_subplot
        I.reset_ctx_for_next_plot()
        if subplot is not None:
            ctx.pop_id()
            _subplot_next_cell()


def _end_plot_render(plot, ctx, io, style, dl) -> None:
    render_border = style.plot_border_size > 0 and I.get_style_color_u32(I.COL_PLOT_BORDER)[3] > 0
    any_x_held = plot.held or any(plot.x_axis(i).held for i in range(I.NUM_X_AXES))
    any_y_held = plot.held or any(plot.y_axis(i).held for i in range(I.NUM_Y_AXES))
    fr, pr = plot.frame_rect, plot.plot_rect
    dl.push_clip_rect((fr[0], fr[1]), (fr[2], fr[3]))
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        if ax.enabled and ax.has_grid_lines() and ax.is_foreground():
            _render_grid_lines_x(ax.ticker, pr, ax.color_maj, ax.color_min,
                                 style.major_grid_size[0], style.minor_grid_size[0])
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        if ax.enabled and ax.has_grid_lines() and ax.is_foreground():
            _render_grid_lines_y(ax.ticker, pr, ax.color_maj, ax.color_min,
                                 style.major_grid_size[1], style.minor_grid_size[1])
    if plot.has_title():
        _add_text_centered(((pr[0] + pr[2]) * 0.5, plot.canvas_rect[1]),
                           I.get_style_color_u32(I.COL_TITLE_TEXT), plot.title)
    count_b = count_t = 0
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        if not ax.enabled:
            continue
        opp = ax.is_opposite()
        aux = (opp and count_t > 0) or (not opp and count_b > 0)
        if ax.has_tick_marks():
            direction = 1.0 if opp else -1.0
            for tk in ax.ticker.ticks:
                if tk.level != 0 or tk.pixel_pos < pr[0] or tk.pixel_pos > pr[2]:
                    continue
                length = style.major_tick_len[0] if (not aux and tk.major) else style.minor_tick_len[0]
                thk = style.major_tick_size[0] if (not aux and tk.major) else style.minor_tick_size[0]
                _line_v(tk.pixel_pos, ax.datum1, ax.datum1 + direction * length, ax.color_tick, thk)
            if aux or not render_border:
                _line_h(pr[0], pr[2], ax.datum1, ax.color_tick, style.minor_tick_size[0])
        count_b += not opp
        count_t += opp
    count_l = count_r = 0
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        if not ax.enabled:
            continue
        opp = ax.is_opposite()
        aux = (opp and count_r > 0) or (not opp and count_l > 0)
        if ax.has_tick_marks():
            direction = -1.0 if opp else 1.0
            for tk in ax.ticker.ticks:
                if tk.level != 0 or tk.pixel_pos < pr[1] or tk.pixel_pos > pr[3]:
                    continue
                length = style.major_tick_len[1] if (not aux and tk.major) else style.minor_tick_len[1]
                thk = style.major_tick_size[1] if (not aux and tk.major) else style.minor_tick_size[1]
                _line_h(ax.datum1, ax.datum1 + direction * length, tk.pixel_pos, ax.color_tick, thk)
            if aux or not render_border:
                _line_v(ax.datum1, pr[1], pr[3], ax.color_tick, style.minor_tick_size[1])
        count_l += not opp
        count_r += opp
    dl.pop_clip_rect()

    # annotations
    dl.push_clip_rect((pr[0], pr[1]), (pr[2], pr[3]))
    for xi, yi, x, y, off, bg, fg, clamp, txt in gp.annotations:
        xa, ya = plot.axes[xi], plot.axes[yi]
        anchor = (xa.plot_to_pixels(x), ya.plot_to_pixels(y))
        tsize = I.calc_text_size(txt)
        size = (tsize[0] + style.annotation_padding[0] * 2, tsize[1] + style.annotation_padding[1] * 2)
        px, py = anchor
        if off[0] == 0:
            px -= size[0] / 2
        elif off[0] > 0:
            px += off[0]
        else:
            px -= size[0] - off[0]
        if off[1] == 0:
            py -= size[1] / 2
        elif off[1] > 0:
            py += off[1]
        else:
            py -= size[1] - off[1]
        if clamp:
            px = min(max(px, pr[0]), pr[2] - size[0])
            py = min(max(py, pr[1]), pr[3] - size[1])
        rect = (px, py, px + size[0], py + size[1])
        if off[0] != 0 or off[1] != 0:
            corners = ((rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]), (rect[0], rect[3]))
            best = min(corners, key=lambda c: (anchor[0] - c[0]) ** 2 + (anchor[1] - c[1]) ** 2)
            _line(dl.p, anchor[0], anchor[1], best[0], best[1], 1.0, bg)
        _fill(rect, bg)
        _add_text((px + style.annotation_padding[0], py + style.annotation_padding[1]), fg, txt)
    if plot.selected:
        sr = plot.select_rect
        rect = (sr[0] + pr[0], sr[1] + pr[1], sr[2] + pr[0], sr[3] + pr[1])
        col = I.get_style_color_u32(I.COL_SELECTION)
        _fill(rect, (col[0], col[1], col[2], int(col[3] * 0.25)))
        _stroke(rect, col)
    legend_hovered_prev = plot.items.legend.hovered
    if (has_flag(plot.flags, I.FLAGS_CROSSHAIRS) and plot.hovered and not (any_x_held or any_y_held)
            and not plot.selecting and not legend_hovered_prev):
        mx, my = io.mouse_pos
        col = I.get_style_color_u32(I.COL_CROSSHAIRS)
        _line_h(pr[0], mx - 5, my, col)
        _line_h(mx + 5, pr[2], my, col)
        _line_v(mx, pr[1], my - 5, col)
        _line_v(mx, my + 5, pr[3], col)
    if not has_flag(plot.flags, I.FLAGS_NO_MOUSE_TEXT) and (
            plot.hovered or has_flag(plot.mouse_text_flags, I.MOUSE_TEXT_FLAGS_SHOW_ALWAYS)):
        no_aux = has_flag(plot.mouse_text_flags, I.MOUSE_TEXT_FLAGS_NO_AUX_AXES)
        no_fmt = has_flag(plot.mouse_text_flags, I.MOUSE_TEXT_FLAGS_NO_FORMAT)
        out = ""
        for i in range(1 if no_aux else I.NUM_X_AXES):
            ax = plot.x_axis(i)
            if not ax.enabled:
                continue
            v = ax.pixels_to_plot(io.mouse_pos[0])
            s = I.formatter_default(v) if no_fmt else _label_axis_value(ax, v, True)
            out += (", (" + s + ")") if i > 0 else s
        out += ", "
        for i in range(1 if no_aux else I.NUM_Y_AXES):
            ax = plot.y_axis(i)
            if not ax.enabled:
                continue
            v = ax.pixels_to_plot(io.mouse_pos[1])
            s = I.formatter_default(v) if no_fmt else _label_axis_value(ax, v, True)
            out += (", (" + s + ")") if i > 0 else s
        size = I.calc_text_size(out)
        pos = I.get_location_pos(pr, size, plot.mouse_text_location, style.mouse_pos_padding)
        _add_text(pos, I.get_style_color_u32(I.COL_INLAY_TEXT), out)
    dl.pop_clip_rect()

    # axis side switch
    if not plot.held:
        mouse = io.mouse_pos
        for i in range(I.NUM_X_AXES):
            ax = plot.x_axis(i)
            if has_flag(ax.flags, I.AXIS_FLAGS_NO_SIDE_SWITCH):
                continue
            if ax.held and I.rect_contains(pr, mouse):
                if not ax.is_opposite():
                    rect = (pr[0] - 5, pr[1] - 5, pr[2] + 5, pr[1] + 5)
                    if mouse[1] < pr[3] - 10:
                        _fill(rect, ax.color_hov)
                    if I.rect_contains(rect, mouse):
                        ax.flags |= I.AXIS_FLAGS_OPPOSITE
                else:
                    rect = (pr[0] - 5, pr[3] - 5, pr[2] + 5, pr[3] + 5)
                    if mouse[1] > pr[1] + 10:
                        _fill(rect, ax.color_hov)
                    if I.rect_contains(rect, mouse):
                        ax.flags &= ~I.AXIS_FLAGS_OPPOSITE
        for i in range(I.NUM_Y_AXES):
            ax = plot.y_axis(i)
            if has_flag(ax.flags, I.AXIS_FLAGS_NO_SIDE_SWITCH):
                continue
            if ax.held and I.rect_contains(pr, mouse):
                if not ax.is_opposite():
                    rect = (pr[2] - 5, pr[1] - 5, pr[2] + 5, pr[3] + 5)
                    if mouse[0] > pr[0] + 10:
                        _fill(rect, ax.color_hov)
                    if I.rect_contains(rect, mouse):
                        ax.flags |= I.AXIS_FLAGS_OPPOSITE
                else:
                    rect = (pr[0] - 5, pr[1] - 5, pr[0] + 5, pr[3] + 5)
                    if mouse[0] < pr[2] - 10:
                        _fill(rect, ax.color_hov)
                    if I.rect_contains(rect, mouse):
                        ax.flags &= ~I.AXIS_FLAGS_OPPOSITE

    # legend
    plot.items.legend.hovered = False
    for item in plot.items.items:
        item.legend_hovered = False
    legend_contextable = False
    if not has_flag(plot.flags, I.FLAGS_NO_LEGEND) and plot.items.get_legend_count() > 0:
        out = has_flag(plot.items.legend.flags, I.LEGEND_FLAGS_OUTSIDE)
        legend_contextable = _render_legend(
            plot.items, fr if out else pr, style.plot_padding if out else style.legend_padding,
            False, not has_flag(plot.flags, I.FLAGS_NO_MENUS), plot.hovered)
    else:
        plot.items.legend.rect = (0.0, 0.0, 0.0, 0.0)
    if render_border:
        _stroke(pr, I.get_style_color_u32(I.COL_PLOT_BORDER), style.plot_border_size)

    # tags
    for axis_idx, value, bg, fg, txt in gp.tags:
        axis = plot.axes[axis_idx]
        if not axis.enabled or not axis.range_contains(value):
            continue
        tsize = I.calc_text_size(txt)
        size = (tsize[0] + style.annotation_padding[0] * 2, tsize[1] + style.annotation_padding[1] * 2)
        axis.ticker.override_size_late(size)
        pix = float(round(axis.plot_to_pixels(value)))
        p = dl.p
        if axis.vertical:
            if axis.is_opposite():
                pos = (axis.datum1 + style.label_padding[0], pix - size[1] * 0.5)
                p.fill_triangle((axis.datum1, pix), pos, (pos[0], pos[1] + size[1]), bg)
            else:
                pos = (axis.datum1 - size[0] - style.label_padding[0], pix - size[1] * 0.5)
                p.fill_triangle((pos[0] + size[0], pos[1]), (axis.datum1, pix),
                                (pos[0] + size[0], pos[1] + size[1]), bg)
        else:
            if axis.is_opposite():
                pos = (pix - size[0] * 0.5, axis.datum1 - size[1] - style.label_padding[1])
                p.fill_triangle((pos[0], pos[1] + size[1]), (pos[0] + size[0], pos[1] + size[1]),
                                (pix, axis.datum1), bg)
            else:
                pos = (pix - size[0] * 0.5, axis.datum1 + style.label_padding[1])
                p.fill_triangle(pos, (pix, axis.datum1), (pos[0] + size[0], pos[1]), bg)
        _fill((pos[0], pos[1], pos[0] + size[0], pos[1] + size[1]), bg)
        _add_text((pos[0] + style.annotation_padding[0], pos[1] + style.annotation_padding[1]), fg, txt)

    # context menus
    if gp.open_context_this_frame and legend_contextable:
        _open_menu(plot, "legend", 0)
    can_ctx = (gp.open_context_this_frame and not has_flag(plot.flags, I.FLAGS_NO_MENUS)
               and not plot.items.legend.hovered)
    if can_ctx and plot.hovered:
        _open_menu(plot, "plot", 0)
    for i in range(I.NUM_X_AXES):
        if can_ctx and plot.x_axis(i).hovered and plot.x_axis(i).has_menus():
            _open_menu(plot, "x", i)
    for i in range(I.NUM_Y_AXES):
        if can_ctx and plot.y_axis(i).hovered and plot.y_axis(i).has_menus():
            _open_menu(plot, "y", i)
    if plot.context_menu is not None:
        gp.pending_popups.append(("menu", plot, gp.current_subplot))
    if gp.current_subplot is None:
        _flush_popups()


# --------------------------------------------------------------------------- #
# [SECTION] Context menus and popups
# --------------------------------------------------------------------------- #
_MENU_WIDTH = 190.0


def _open_menu(plot, kind: str, index: int) -> None:
    """``OpenPopup``: a menu at the pointer, replacing any other."""
    plot.context_menu = {"kind": kind, "index": index, "pos": tuple(_io().mouse_pos),
                         "size": (_MENU_WIDTH, 60.0), "just_opened": True}


def _flush_popups() -> None:
    """Draw the popups the plot (or the subplot grid) opened, on top of it."""
    pending, gp.pending_popups = gp.pending_popups, []
    for entry in pending:
        if entry[0] == "menu":
            _show_menu_window(entry[1], entry[2])
        elif entry[0] == "replay":
            entry[1].replay(_dl().p)


def _menu_closed_by_click(menu) -> bool:
    io = _io()
    if menu.get("just_opened"):
        return False
    x, y = menu["pos"]
    w, h = menu["size"]
    mx, my = io.mouse_pos
    inside = x <= mx < x + w and y <= my < y + h
    return any(io.mouse_clicked) and not inside


def _show_menu_window(plot, subplot) -> None:
    menu = plot.context_menu
    if menu is None:
        return
    if _menu_closed_by_click(menu):
        plot.context_menu = None
        return
    ctx = _ctx()
    x, y = menu["pos"]
    w, h = menu["size"]
    name = f"##implot_menu_{id(plot)}"
    _fill((x, y, x + w, y + h), _rgba(ctx.style.color(_core.Col.POPUP_BG)))
    _stroke((x, y, x + w, y + h), _rgba(ctx.style.color(_core.Col.BORDER)))
    from .flags import WindowFlags
    ctx.begin(name, (x + 4, y + 4, w - 8, max(h - 8, 20.0)), WindowFlags.ALWAYS_AUTO_RESIZE)
    ctx.push_id(name)
    close = False
    was_plot = gp.current_plot
    gp.current_plot = plot
    try:
        kind = menu["kind"]
        if kind == "plot":
            close = show_plot_context_menu(plot, subplot)
        elif kind == "legend":
            _w.text("Legend")
            _w.separator()
            if show_legend_context_menu(plot.items.legend, not has_flag(plot.flags, I.FLAGS_NO_LEGEND)):
                plot.flags ^= I.FLAGS_NO_LEGEND
        elif kind == "subplot_legend":
            _w.text("Legend")
            _w.separator()
            if show_legend_context_menu(subplot.items.legend,
                                        not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_LEGEND)):
                subplot.flags ^= I.SUBPLOT_FLAGS_NO_LEGEND
        else:
            i = menu["index"]
            axis = plot.x_axis(i) if kind == "x" else plot.y_axis(i)
            default = ("X-Axis" if kind == "x" else "Y-Axis") + ("" if i == 0 else f" {i + 1}")
            _w.text(axis.label if axis.has_label() else default)
            _w.separator()
            equal = has_flag(plot.flags, I.FLAGS_EQUAL)
            show_axis_context_menu(axis, axis.ortho_axis if equal else None)
    finally:
        gp.current_plot = was_plot
        ctx.pop_id()
        window = ctx.current_window
        ctx.end()
    box = window.box if window is not None else (x, y, w, h)
    menu["size"] = (max(_MENU_WIDTH, box[2] + 8), box[3] + 8)
    menu["just_opened"] = False
    if close:
        plot.context_menu = None


def show_axis_context_menu(axis, equal_axis=None, time_allowed: bool = False) -> None:
    """``ShowAxisContextMenu``: locks, limits, fit, invert, side, decorations.

    The time scale's date and time pickers are not ported; a time axis edits
    its limits as the plain numbers they are.
    """
    _w.push_item_width(75)
    always_locked = axis.is_range_locked() or axis.is_auto_fitting()
    label, grid = axis.has_label(), axis.has_grid_lines()
    ticks, labels = axis.has_tick_marks(), axis.has_tick_labels()
    drag_speed = I.DBL_EPSILON * 1.0e13 if axis.range_size() <= I.DBL_EPSILON else 0.01 * axis.range_size()
    for which in ("Min", "Max"):
        flag = I.AXIS_FLAGS_LOCK_MIN if which == "Min" else I.AXIS_FLAGS_LOCK_MAX
        _w.begin_disabled(always_locked)
        _changed, axis.flags = _w.checkbox_flags("##Lock" + which, axis.flags, flag)
        _w.end_disabled()
        _w.same_line()
        locked = (axis.is_locked_min() if which == "Min" else axis.is_locked_max()) or always_locked
        _w.begin_disabled(locked)
        value = axis.range_min if which == "Min" else axis.range_max
        changed, value = _w.drag_float(which, value, drag_speed, None, None, "%.3g")
        if changed and not locked:
            if which == "Min":
                axis.set_min(min(value, axis.range_max - I.DBL_EPSILON), True)
            else:
                axis.set_max(max(value, axis.range_min + I.DBL_EPSILON), True)
            axis.follow = False
            if equal_axis is not None:
                equal_axis.set_aspect(axis.get_aspect())
        _w.end_disabled()
    _w.separator()
    _changed, axis.flags = _w.checkbox_flags("Auto-Fit", axis.flags, I.AXIS_FLAGS_AUTO_FIT)
    _w.separator()
    _changed, axis.flags = _w.checkbox_flags("Invert", axis.flags, I.AXIS_FLAGS_INVERT)
    _changed, axis.flags = _w.checkbox_flags("Opposite", axis.flags, I.AXIS_FLAGS_OPPOSITE)
    _w.separator()
    _w.begin_disabled(not axis.label)
    if _w.checkbox("Label", label)[0]:
        axis.flags ^= I.AXIS_FLAGS_NO_LABEL
    _w.end_disabled()
    if _w.checkbox("Grid Lines", grid)[0]:
        axis.flags ^= I.AXIS_FLAGS_NO_GRID_LINES
    if _w.checkbox("Tick Marks", ticks)[0]:
        axis.flags ^= I.AXIS_FLAGS_NO_TICK_MARKS
    if _w.checkbox("Tick Labels", labels)[0]:
        axis.flags ^= I.AXIS_FLAGS_NO_TICK_LABELS
    _w.pop_item_width()


def show_legend_context_menu(legend, visible: bool) -> bool:
    """``ShowLegendContextMenu``: returns True when "Show" was toggled."""
    s = _core.get_frame_height()
    ret = False
    if _w.checkbox("Show", visible)[0]:
        ret = True
    if legend.can_go_inside:
        _changed, legend.flags = _w.checkbox_flags("Outside", legend.flags, I.LEGEND_FLAGS_OUTSIDE)
    if _w.radio_button("H", has_flag(legend.flags, I.LEGEND_FLAGS_HORIZONTAL)):
        legend.flags |= I.LEGEND_FLAGS_HORIZONTAL
    _w.same_line()
    if _w.radio_button("V", not has_flag(legend.flags, I.LEGEND_FLAGS_HORIZONTAL)):
        legend.flags &= ~I.LEGEND_FLAGS_HORIZONTAL
    grid = (("NW", I.LOCATION_NORTH_WEST), ("N", I.LOCATION_NORTH), ("NE", I.LOCATION_NORTH_EAST),
            ("W", I.LOCATION_WEST), ("C", None), ("E", I.LOCATION_EAST),
            ("SW", I.LOCATION_SOUTH_WEST), ("S", I.LOCATION_SOUTH), ("SE", I.LOCATION_SOUTH_EAST))
    for k, (name, loc) in enumerate(grid):
        if k % 3:
            _w.same_line(0.0, 2.0)
        if loc is None:
            _w.invisible_button(name, (1.5 * s, s))
        elif _w.button(name, (1.5 * s, s)):
            legend.location = loc
    return ret


def show_subplots_context_menu(subplot) -> None:
    """``ShowSubplotsContextMenu``."""
    if _w.begin_menu("Linking"):
        for name, flag in (("Link Rows", I.SUBPLOT_FLAGS_LINK_ROWS), ("Link Cols", I.SUBPLOT_FLAGS_LINK_COLS),
                           ("Link All X", I.SUBPLOT_FLAGS_LINK_ALL_X), ("Link All Y", I.SUBPLOT_FLAGS_LINK_ALL_Y)):
            if _w.menu_item(name, "", has_flag(subplot.flags, flag)):
                subplot.flags ^= flag
        _w.end_menu()
    if _w.begin_menu("Settings"):
        if _w.menu_item("Title", "", subplot.has_title and not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_TITLE),
                        subplot.has_title):
            subplot.flags ^= I.SUBPLOT_FLAGS_NO_TITLE
        if _w.menu_item("Resizable", "", not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_RESIZE)):
            subplot.flags ^= I.SUBPLOT_FLAGS_NO_RESIZE
        if _w.menu_item("Align", "", not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_ALIGN)):
            subplot.flags ^= I.SUBPLOT_FLAGS_NO_ALIGN
        if _w.menu_item("Share Items", "", has_flag(subplot.flags, I.SUBPLOT_FLAGS_SHARE_ITEMS)):
            subplot.flags ^= I.SUBPLOT_FLAGS_SHARE_ITEMS
        _w.end_menu()


def show_plot_context_menu(plot, subplot=None) -> bool:
    """``ShowPlotContextMenu``. Returns True when a menu item closed it."""
    close = False
    equal = has_flag(plot.flags, I.FLAGS_EQUAL)
    for i in range(I.NUM_X_AXES):
        ax = plot.x_axis(i)
        if not ax.enabled or not ax.has_menus():
            continue
        _w.push_id(("x", i))
        if _w.begin_menu(ax.label if ax.has_label() else ("X-Axis" if i == 0 else f"X-Axis {i + 1}")):
            show_axis_context_menu(ax, ax.ortho_axis if equal else None)
            _w.end_menu()
        _w.pop_id()
    for i in range(I.NUM_Y_AXES):
        ax = plot.y_axis(i)
        if not ax.enabled or not ax.has_menus():
            continue
        _w.push_id(("y", i))
        if _w.begin_menu(ax.label if ax.has_label() else ("Y-Axis" if i == 0 else f"Y-Axis {i + 1}")):
            show_axis_context_menu(ax, ax.ortho_axis if equal else None)
            _w.end_menu()
        _w.pop_id()
    _w.separator()
    if not has_flag(plot.items.legend.flags, I.LEGEND_FLAGS_NO_MENUS):
        if _w.begin_menu("Legend"):
            if subplot is not None and has_flag(subplot.flags, I.SUBPLOT_FLAGS_SHARE_ITEMS):
                if show_legend_context_menu(subplot.items.legend,
                                            not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_LEGEND)):
                    subplot.flags ^= I.SUBPLOT_FLAGS_NO_LEGEND
            elif show_legend_context_menu(plot.items.legend, not has_flag(plot.flags, I.FLAGS_NO_LEGEND)):
                plot.flags ^= I.FLAGS_NO_LEGEND
            _w.end_menu()
    if _w.begin_menu("Settings"):
        for name, flag, on in (("Equal", I.FLAGS_EQUAL, True), ("Box Select", I.FLAGS_NO_BOX_SELECT, False),
                               ("Title", I.FLAGS_NO_TITLE, False),
                               ("Mouse Position", I.FLAGS_NO_MOUSE_TEXT, False),
                               ("Crosshairs", I.FLAGS_CROSSHAIRS, True)):
            state = has_flag(plot.flags, flag) if on else not has_flag(plot.flags, flag)
            enabled = plot.title is not None if name == "Title" else True
            if _w.menu_item(name, "", state if name != "Title" else plot.has_title(), enabled):
                plot.flags ^= flag
                close = True
        _w.end_menu()
    if subplot is not None and not has_flag(subplot.flags, I.SUBPLOT_FLAGS_NO_MENUS):
        _w.separator()
        if _w.begin_menu("Subplots"):
            show_subplots_context_menu(subplot)
            _w.end_menu()
    return close


# --------------------------------------------------------------------------- #
# [SECTION] Subplots
# --------------------------------------------------------------------------- #
SUBPLOT_BORDER_SIZE = 1.0
SUBPLOT_SPLITTER_HALF_THICKNESS = 4.0


def _subplot_set_cell(row: int, col: int) -> None:
    """``SubplotSetCell``."""
    sp = gp.current_subplot
    if row >= sp.rows or col >= sp.cols:
        return
    xoff = sum(sp.col_ratios[:col])
    yoff = sum(sp.row_ratios[:row])
    gr = sp.grid_rect
    gw, gh = gr[2] - gr[0], gr[3] - gr[1]
    sp.cell_pos = (float(round(gr[0] + xoff * gw)), float(round(gr[1] + yoff * gh)))
    sp.cell_size = (float(round(gw * sp.col_ratios[col])), float(round(gh * sp.row_ratios[row])))
    lx = has_flag(sp.flags, I.SUBPLOT_FLAGS_LINK_ALL_X)
    ly = has_flag(sp.flags, I.SUBPLOT_FLAGS_LINK_ALL_Y)
    lr = has_flag(sp.flags, I.SUBPLOT_FLAGS_LINK_ROWS)
    lc = has_flag(sp.flags, I.SUBPLOT_FLAGS_LINK_COLS)
    xl = sp.col_link_data[0] if lx else (sp.col_link_data[col] if lc else None)
    yl = sp.row_link_data[0] if ly else (sp.row_link_data[row] if lr else None)
    set_next_axis_links(I.AXIS_X1, (xl, 0) if xl is not None else None, (xl, 1) if xl is not None else None)
    set_next_axis_links(I.AXIS_Y1, (yl, 0) if yl is not None else None, (yl, 1) if yl is not None else None)
    if not has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_ALIGN):
        gp.current_alignment_h = sp.row_alignment_data[row]
        gp.current_alignment_v = sp.col_alignment_data[col]
    sp.current_idx = col * sp.rows + row if has_flag(sp.flags, I.SUBPLOT_FLAGS_COL_MAJOR) \
        else row * sp.cols + col


def _subplot_set_cell_idx(idx: int) -> None:
    sp = gp.current_subplot
    if idx >= sp.rows * sp.cols:
        return
    if has_flag(sp.flags, I.SUBPLOT_FLAGS_COL_MAJOR):
        row, col = idx % sp.rows, idx // sp.rows
    else:
        row, col = idx // sp.cols, idx % sp.cols
    _subplot_set_cell(row, col)


def _subplot_next_cell() -> None:
    sp = gp.current_subplot
    if sp is None:
        return
    sp.current_idx += 1
    _subplot_set_cell_idx(sp.current_idx)


def begin_subplots(title_id: str, rows: int, cols: int, size, flags: int = 0,
                   row_ratios=None, col_ratios=None) -> bool:
    """``BeginSubplots``: a grid of plots; call ``begin_plot`` for each cell.

    *row_ratios*/*col_ratios* are lists, updated in place when the user drags
    a splitter, as the reference's ``float*`` are.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError("begin_subplots: rows and cols must be positive")
    ctx = _ctx()
    if gp.current_subplot is not None and gp.owner == id(ctx):
        raise RuntimeError("Mismatched begin_subplots()/end_subplots()")
    gp.frame, gp.owner = _core.get_frame_count(), id(ctx)
    sp_id = ctx.get_id(title_id)
    subplots = I.pools()["subplots"]
    just_created = sp_id not in subplots
    sp = subplots.setdefault(sp_id, I.Subplot())
    gp.current_subplot = sp
    sp.id = sp_id
    sp.items.id = ("##subplot_items", sp_id)
    sp.has_title = bool(I.split_label(title_id))
    ctx.push_id(("##subplots", sp_id))
    if just_created or flags != sp.previous_flags:
        sp.flags = int(flags)
    sp.previous_flags = int(flags)
    if sp.rows != rows or sp.cols != cols:
        sp.row_alignment_data = [I.AlignmentData() for _ in range(rows)]
        sp.row_link_data = [[0.0, 1.0] for _ in range(rows)]
        sp.row_ratios = [1.0 / rows] * rows
        sp.col_alignment_data = [I.AlignmentData() for _ in range(cols)]
        sp.col_link_data = [[0.0, 1.0] for _ in range(cols)]
        sp.col_ratios = [1.0 / cols] * cols
    row_sum = col_sum = 0.0
    if row_ratios is not None:
        row_sum = sum(row_ratios[:rows])
        sp.row_ratios = [row_ratios[r] / row_sum for r in range(rows)]
    if col_ratios is not None:
        col_sum = sum(col_ratios[:cols])
        sp.col_ratios = [col_ratios[c] / col_sum for c in range(cols)]
    sp.rows, sp.cols = rows, cols
    style = gp.style
    title_size = (0.0, 0.0) if has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_TITLE) else I.calc_text_size(title_id, True)
    pad_top = title_size[1] + style.label_padding[1] if title_size[0] > 0 else 0.0
    half_pad = (style.plot_padding[0] / 2, style.plot_padding[1] / 2)
    fw, fh = _calc_item_size(size, *style.plot_default_size)
    x, y = _w.get_cursor_screen_pos()
    sp.frame_rect = (x, y, x + fw, y + fh)
    _w.dummy(fw, fh)
    sp.grid_rect = (x + half_pad[0], y + half_pad[1] + pad_top, x + fw - half_pad[0], y + fh - half_pad[1])
    sp.frame_hovered = I.rect_contains(sp.frame_rect, ctx.io.mouse_pos)
    share = has_flag(sp.flags, I.SUBPLOT_FLAGS_SHARE_ITEMS)
    if share:
        gp.current_items = sp.items
    if share and not has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_LEGEND) and sp.items.get_legend_count() > 0:
        legend = sp.items.legend
        horz = has_flag(legend.flags, I.LEGEND_FLAGS_HORIZONTAL)
        ls = I.calc_legend_size(sp.items, style.legend_inner_padding, style.legend_spacing, not horz)
        loc = legend.location
        west = has_flag(loc, I.LOCATION_WEST) and not has_flag(loc, I.LOCATION_EAST)
        east = has_flag(loc, I.LOCATION_EAST) and not has_flag(loc, I.LOCATION_WEST)
        north = has_flag(loc, I.LOCATION_NORTH) and not has_flag(loc, I.LOCATION_SOUTH)
        south = has_flag(loc, I.LOCATION_SOUTH) and not has_flag(loc, I.LOCATION_NORTH)
        g = list(sp.grid_rect)
        if (west and not horz) or (west and horz and not north and not south):
            g[0] += ls[0] + style.legend_padding[0]
        if (east and not horz) or (east and horz and not north and not south):
            g[2] -= ls[0] + style.legend_padding[0]
        if (north and horz) or (north and not horz and not west and not east):
            g[1] += ls[1] + style.legend_padding[1]
        if (south and horz) or (south and not horz and not west and not east):
            g[3] -= ls[1] + style.legend_padding[1]
        sp.grid_rect = tuple(g)
    _fill(sp.frame_rect, I.get_style_color_u32(I.COL_FRAME_BG))
    if title_size[0] > 0:
        gr = sp.grid_rect
        _add_text_centered(((gr[0] + gr[2]) * 0.5, gr[1] - pad_top + half_pad[1]),
                           I.get_style_color_u32(I.COL_TITLE_TEXT), title_id)
    if not has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_RESIZE):
        _subplot_splitters(sp, row_ratios, col_ratios)
    if row_ratios is not None:
        for r in range(rows):
            row_ratios[r] = sp.row_ratios[r] * row_sum
    if col_ratios is not None:
        for c in range(cols):
            col_ratios[c] = sp.col_ratios[c] * col_sum
    push_style_color(I.COL_FRAME_BG, (0, 0, 0, 0))
    push_style_var(I.STYLE_VAR_PLOT_PADDING, half_pad)
    push_style_var(I.STYLE_VAR_PLOT_MIN_SIZE, (0.0, 0.0))
    for a in sp.row_alignment_data + sp.col_alignment_data:
        a.begin()
    sp.items.legend.reset()
    _subplot_set_cell(0, 0)
    return True


def _subplot_splitters(sp, row_ratios, col_ratios) -> None:
    ctx = _ctx()
    io = ctx.io
    hov_col = _rgba(ctx.style.color(_core.Col.SEPARATOR_HOVERED))
    act_col = _rgba(ctx.style.color(_core.Col.SEPARATOR_ACTIVE))
    gr = sp.grid_rect
    gw, gh = gr[2] - gr[0], gr[3] - gr[1]
    ypos, xpos = gr[1], gr[0]
    separator = 1
    for r in range(sp.rows - 1):
        ypos += sp.row_ratios[r] * gh
        sep_id = (sp.id, "##sep", separator)
        bb = (gr[0], ypos - SUBPLOT_SPLITTER_HALF_THICKNESS, gr[2], ypos + SUBPLOT_SPLITTER_HALF_THICKNESS)
        clk, hov, hld = _plot_button_behavior(bb, sep_id, (0,))
        if hov or hld:
            if clk and io.mouse_double_clicked[0]:
                p = (sp.row_ratios[r] + sp.row_ratios[r + 1]) / 2
                sp.row_ratios[r] = sp.row_ratios[r + 1] = p
            if clk:
                sp.temp_sizes = [sp.row_ratios[r], sp.row_ratios[r + 1]]
            if hld:
                dp = io.mouse_drag_delta(0)[1] / gh
                if sp.temp_sizes[0] + dp > 0.1 and sp.temp_sizes[1] - dp > 0.1:
                    sp.row_ratios[r] = sp.temp_sizes[0] + dp
                    sp.row_ratios[r + 1] = sp.temp_sizes[1] - dp
            _line_h(round(gr[0]), round(gr[2]), round(ypos), act_col if hld else hov_col, SUBPLOT_BORDER_SIZE)
        separator += 1
    for c in range(sp.cols - 1):
        xpos += sp.col_ratios[c] * gw
        sep_id = (sp.id, "##sep", separator)
        bb = (xpos - SUBPLOT_SPLITTER_HALF_THICKNESS, gr[1], xpos + SUBPLOT_SPLITTER_HALF_THICKNESS, gr[3])
        clk, hov, hld = _plot_button_behavior(bb, sep_id, (0,))
        if hov or hld:
            if clk and io.mouse_double_clicked[0]:
                p = (sp.col_ratios[c] + sp.col_ratios[c + 1]) / 2
                sp.col_ratios[c] = sp.col_ratios[c + 1] = p
            if clk:
                sp.temp_sizes = [sp.col_ratios[c], sp.col_ratios[c + 1]]
            if hld:
                dp = io.mouse_drag_delta(0)[0] / gw
                if sp.temp_sizes[0] + dp > 0.1 and sp.temp_sizes[1] - dp > 0.1:
                    sp.col_ratios[c] = sp.temp_sizes[0] + dp
                    sp.col_ratios[c + 1] = sp.temp_sizes[1] - dp
            _line_v(round(xpos), round(gr[1]), round(gr[3]), act_col if hld else hov_col, SUBPLOT_BORDER_SIZE)
        separator += 1


def end_subplots() -> None:
    """``EndSubplots``: the shared legend, and the popups of every cell."""
    sp = gp.current_subplot
    if sp is None:
        raise RuntimeError("Mismatched begin_subplots()/end_subplots()")
    ctx = _ctx()
    io = ctx.io
    for a in sp.row_alignment_data + sp.col_alignment_data:
        a.end()
    pop_style_color()
    pop_style_var(2)
    sp.items.legend.hovered = False
    for item in sp.items.items:
        item.legend_hovered = False
    share = has_flag(sp.flags, I.SUBPLOT_FLAGS_SHARE_ITEMS)
    style = gp.style
    if share and not has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_LEGEND) and sp.items.get_legend_count() > 0:
        contextable = _render_legend(sp.items, sp.frame_rect, style.plot_padding, False,
                                     not has_flag(sp.flags, I.SUBPLOT_FLAGS_NO_MENUS), sp.frame_hovered)
        if contextable and io.mouse_released[gp.input_map.menu] and gp.last_plot is not None \
                and sp.items.legend.hovered:
            _open_menu(gp.last_plot, "subplot_legend", 0)
            gp.pending_popups.append(("menu", gp.last_plot, sp))
    else:
        sp.items.legend.rect = (0.0, 0.0, 0.0, 0.0)
    if gp.current_items is sp.items:
        gp.current_items = None
    for item in sp.items.items:
        item.seen_this_frame = False
    ctx.pop_id()
    _flush_popups()
    I.reset_ctx_for_next_subplot()


def is_subplots_hovered() -> bool:
    if gp.current_subplot is None:
        raise RuntimeError("is_subplots_hovered() needs to be called between begin_subplots() and end_subplots()")
    return gp.current_subplot.frame_hovered


def begin_aligned_plots(group_id: str, vertical: bool = True) -> bool:
    """``BeginAlignedPlots``."""
    ctx = _ctx()
    key = ctx.get_id(group_id)
    alignment = I.pools()["alignment"].setdefault(key, I.AlignmentData())
    if vertical:
        gp.current_alignment_v = alignment
    else:
        gp.current_alignment_h = alignment
    if alignment.vertical != vertical:
        alignment.reset()
    alignment.vertical = vertical
    alignment.begin()
    return True


def end_aligned_plots() -> None:
    alignment = gp.current_alignment_h or gp.current_alignment_v
    if alignment is not None:
        alignment.end()
    I.reset_ctx_for_next_aligned_plots()


# --------------------------------------------------------------------------- #
# [SECTION] Plot utils
# --------------------------------------------------------------------------- #
def set_axis(axis: int) -> None:
    plot = _require_plot("set_axis")
    setup_lock()
    if axis < I.AXIS_Y1:
        plot.current_x = axis
    else:
        plot.current_y = axis


def set_axes(x_axis: int, y_axis: int) -> None:
    plot = _require_plot("set_axes")
    setup_lock()
    plot.current_x, plot.current_y = x_axis, y_axis


def _axes(x_idx, y_idx):
    plot = gp.current_plot
    xa = plot.axes[plot.current_x if x_idx == I.IMPLOT_AUTO else x_idx]
    ya = plot.axes[plot.current_y if y_idx == I.IMPLOT_AUTO else y_idx]
    return xa, ya


def pixels_to_plot(x, y=None, x_axis: int = I.IMPLOT_AUTO, y_axis: int = I.IMPLOT_AUTO) -> PlotPoint:
    """``PixelsToPlot``: ``(x, y)`` or a point."""
    if y is None or _items._is_series(x):
        if y is not None:
            x_axis, y_axis = y, x_axis
        x, y = x
    _require_plot("pixels_to_plot")
    setup_lock()
    xa, ya = _axes(x_axis, y_axis)
    return PlotPoint(xa.pixels_to_plot(x), ya.pixels_to_plot(y))


def plot_to_pixels(x, y=None, x_axis: int = I.IMPLOT_AUTO, y_axis: int = I.IMPLOT_AUTO) -> tuple:
    """``PlotToPixels``: ``(x, y)`` or a point."""
    if y is None or _items._is_series(x):
        if y is not None:
            x_axis, y_axis = y, x_axis
        x, y = x
    _require_plot("plot_to_pixels")
    setup_lock()
    xa, ya = _axes(x_axis, y_axis)
    return (xa.plot_to_pixels(x), ya.plot_to_pixels(y))


def get_plot_pos() -> tuple:
    plot = _require_plot("get_plot_pos")
    setup_lock()
    return (plot.plot_rect[0], plot.plot_rect[1])


def get_plot_size() -> tuple:
    plot = _require_plot("get_plot_size")
    setup_lock()
    return (plot.plot_rect[2] - plot.plot_rect[0], plot.plot_rect[3] - plot.plot_rect[1])


def get_plot_mouse_pos(x_axis: int = I.IMPLOT_AUTO, y_axis: int = I.IMPLOT_AUTO) -> PlotPoint:
    return pixels_to_plot(*_io().mouse_pos, x_axis, y_axis)


def get_plot_limits(x_axis: int = I.IMPLOT_AUTO, y_axis: int = I.IMPLOT_AUTO) -> PlotRect:
    """``GetPlotLimits``. Outside a plot: the last plot's, else ``(0, 1, 0, 1)``."""
    if gp.current_plot is None:
        plot = gp.last_plot
        if plot is None:
            return PlotRect(0.0, 1.0, 0.0, 1.0)
        xa = plot.axes[I.AXIS_X1 if x_axis == I.IMPLOT_AUTO else x_axis]
        ya = plot.axes[I.AXIS_Y1 if y_axis == I.IMPLOT_AUTO else y_axis]
    else:
        setup_lock()
        xa, ya = _axes(x_axis, y_axis)
    return PlotRect(xa.range_min, xa.range_max, ya.range_min, ya.range_max)


def is_plot_hovered() -> bool:
    plot = _require_plot("is_plot_hovered")
    setup_lock()
    return plot.hovered


def is_axis_hovered(axis: int) -> bool:
    plot = _require_plot("is_axis_hovered")
    setup_lock()
    return plot.axes[axis].hovered


def is_plot_selected() -> bool:
    plot = _require_plot("is_plot_selected")
    setup_lock()
    return plot.selected


def get_plot_selection(x_axis: int = I.IMPLOT_AUTO, y_axis: int = I.IMPLOT_AUTO) -> PlotRect:
    """``GetPlotSelection``: the box being selected, in plot units."""
    plot = _require_plot("get_plot_selection")
    setup_lock()
    if not plot.selected:
        return PlotRect(0.0, 0.0, 0.0, 0.0)
    sr, pr = plot.select_rect, plot.plot_rect
    p1 = pixels_to_plot(sr[0] + pr[0], sr[1] + pr[1], x_axis, y_axis)
    p2 = pixels_to_plot(sr[2] + pr[0], sr[3] + pr[1], x_axis, y_axis)
    return PlotRect(min(p1.x, p2.x), max(p1.x, p2.x), min(p1.y, p2.y), max(p1.y, p2.y))


def cancel_plot_selection() -> None:
    plot = _require_plot("cancel_plot_selection")
    setup_lock()
    if plot.selected:
        plot.selected = plot.selecting = False


def hide_next_item(hidden: bool = True, cond: int = I.COND_ONCE) -> None:
    """``HideNextItem``."""
    gp.next_item_data.has_hidden = True
    gp.next_item_data.hidden = bool(hidden)
    gp.next_item_data.hidden_cond = cond


# --------------------------------------------------------------------------- #
# [SECTION] Plot tools
# --------------------------------------------------------------------------- #
DRAG_GRAB_HALF_SIZE = 4.0


class DragPointResult(NamedTuple):
    modified: bool
    x: float
    y: float
    clicked: bool
    hovered: bool
    held: bool


class DragLineResult(NamedTuple):
    modified: bool
    value: float
    clicked: bool
    hovered: bool
    held: bool


class DragRectResult(NamedTuple):
    modified: bool
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    clicked: bool
    hovered: bool
    held: bool


def _tool_colour(col):
    c = _rgba(col)
    return c if c is not None else _rgba(_ctx().style.color(_core.Col.TEXT))


def annotation(x: float, y: float, col, pix_offset=(0.0, 0.0), clamp: bool = False, fmt=None, *args,
               round: bool = False) -> None:
    """``Annotation``: a callout at ``(x, y)``. Without *fmt* it prints the
    point's coordinates."""
    plot = _require_plot("annotation")
    setup_lock()
    if fmt is None or isinstance(fmt, bool):
        if isinstance(fmt, bool):
            round = fmt
        xa, ya = _axes(I.IMPLOT_AUTO, I.IMPLOT_AUTO)
        text = f"{_label_axis_value(xa, x, round)}, {_label_axis_value(ya, y, round)}"
    else:
        text = (fmt % args) if args else str(fmt)
    bg = _rgba(col) or (0, 0, 0, 0)
    fg = I.get_style_color_u32(I.COL_INLAY_TEXT) if bg[3] == 0 else I.calc_text_color(bg)
    gp.annotations.append((plot.current_x, plot.current_y, float(x), float(y),
                           (float(pix_offset[0]), float(pix_offset[1])), bg, fg, bool(clamp), text))


def _tag(axis: int, v: float, col, fmt=None, *args, round: bool = False) -> None:
    plot = gp.current_plot
    setup_lock()
    if fmt is None or isinstance(fmt, bool):
        if isinstance(fmt, bool):
            round = fmt
        text = _label_axis_value(plot.axes[axis], v, round)
    else:
        text = (fmt % args) if args else str(fmt)
    bg = _rgba(col) or (0, 0, 0, 0)
    fg = I.get_style_color_u32(I.COL_AXIS_TEXT) if bg[3] == 0 else I.calc_text_color(bg)
    gp.tags.append((axis, float(v), bg, fg, text))


def tag_x(x: float, col, fmt=None, *args, round: bool = False) -> None:
    """``TagX``: a label on the x axis at *x*."""
    plot = _require_plot("tag_x")
    _tag(plot.current_x, x, col, fmt, *args, round=round)


def tag_y(y: float, col, fmt=None, *args, round: bool = False) -> None:
    """``TagY``: a label on the y axis at *y*."""
    plot = _require_plot("tag_y")
    _tag(plot.current_y, y, col, fmt, *args, round=round)


def _mouse_dragging() -> bool:
    return _w.is_mouse_dragging(0)


def drag_point(n_id: int, x: float, y: float, col=None, size: float = 4.0, flags: int = 0) -> DragPointResult:
    """``DragPoint``: returns ``(modified, x, y, clicked, hovered, held)``."""
    plot = _require_plot("drag_point")
    ctx = _ctx()
    setup_lock()
    x, y = float(x), float(y)
    if not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_FIT) and plot.fit_this_frame:
        _items.fit_point((x, y))
    use_input = not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_INPUTS)
    grab = max(DRAG_GRAB_HALF_SIZE, size)
    col32 = _tool_colour(col)
    pos = plot_to_pixels(x, y)
    item_id = (*ctx._ids, "#IMPLOT_DRAG_POINT", n_id)
    clicked = hovered = held = False
    if use_input:
        ctx.set_next_item_allow_overlap()
        hovered, held, clicked = ctx.button_behavior((pos[0] - grab, pos[1] - grab, 2 * grab, 2 * grab), item_id)
    modified = False
    if held and _mouse_dragging():
        x, y = get_plot_mouse_pos()
        modified = True
    fx, fy = x, y

    def render():
        t = _items._transformer()
        px, py = t(fx, fy)
        from .painter import fill_circle
        fill_circle(_dl().p, px, py, size, col32)

    _items._queue(render)
    return DragPointResult(modified, x, y, clicked, hovered, held)


def drag_line_x(n_id: int, x: float, col=None, thickness: float = 1.0, flags: int = 0) -> DragLineResult:
    """``DragLineX``: returns ``(modified, x, clicked, hovered, held)``."""
    return _drag_line(n_id, x, col, thickness, flags, vertical=True)


def drag_line_y(n_id: int, y: float, col=None, thickness: float = 1.0, flags: int = 0) -> DragLineResult:
    """``DragLineY``: returns ``(modified, y, clicked, hovered, held)``."""
    return _drag_line(n_id, y, col, thickness, flags, vertical=False)


def _drag_line(n_id, value, col, thickness, flags, vertical: bool) -> DragLineResult:
    plot = _require_plot("drag_line_x" if vertical else "drag_line_y")
    ctx = _ctx()
    setup_lock()
    value = float(value)
    if not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_FIT) and plot.fit_this_frame:
        (_items.fit_point_x if vertical else _items.fit_point_y)(value)
    use_input = not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_INPUTS)
    grab = max(DRAG_GRAB_HALF_SIZE, thickness / 2)
    pr = plot.plot_rect
    if vertical:
        px = float(round(plot_to_pixels(value, 0.0)[0]))
        box = (px - grab, pr[1], 2 * grab, pr[3] - pr[1])
        item_id = (*ctx._ids, n_id)
    else:
        py = float(round(plot_to_pixels(0.0, value)[1]))
        box = (pr[0], py - grab, pr[2] - pr[0], 2 * grab)
        item_id = (*ctx._ids, "#IMPLOT_DRAG_LINE_Y", n_id)
    clicked = hovered = held = False
    if use_input:
        ctx.set_next_item_allow_overlap()
        hovered, held, clicked = ctx.button_behavior(box, item_id)
    col32 = _tool_colour(col)
    modified = False
    if held and _mouse_dragging():
        m = get_plot_mouse_pos()
        value = m.x if vertical else m.y
        modified = True
    v = value
    length = gp.style.major_tick_len[0 if vertical else 1]

    def render():
        t = _items._transformer()
        r = gp.current_plot.plot_rect
        if vertical:
            px_ = float(round(t(v, 0.0)[0]))
            _line_v(px_, r[1], r[3], col32, thickness)
            _line_v(px_, r[1], r[1] + length, col32, 3 * thickness)
            _line_v(px_, r[3], r[3] - length, col32, 3 * thickness)
        else:
            py_ = float(round(t(0.0, v)[1]))
            _line_h(r[0], r[2], py_, col32, thickness)
            _line_h(r[0], r[0] + length, py_, col32, 3 * thickness)
            _line_h(r[2], r[2] - length, py_, col32, 3 * thickness)

    _items._queue(render)
    return DragLineResult(modified, value, clicked, hovered, held)


def drag_rect(n_id: int, x_min: float, y_min: float, x_max: float, y_max: float, col=None,
              flags: int = 0) -> DragRectResult:
    """``DragRect``: drag the centre, a corner or an edge; double-click an edge
    to push it to the plot limit. Returns
    ``(modified, x_min, y_min, x_max, y_max, clicked, hovered, held)``."""
    plot = _require_plot("drag_rect")
    ctx = _ctx()
    io = ctx.io
    setup_lock()
    v = {"x_min": float(x_min), "y_min": float(y_min), "x_max": float(x_max), "y_max": float(y_max)}
    if not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_FIT) and plot.fit_this_frame:
        _items.fit_point((v["x_min"], v["y_min"]))
        _items.fit_point((v["x_max"], v["y_max"]))
    use_input = not has_flag(flags, I.DRAG_TOOL_FLAGS_NO_INPUTS)
    h = (True, False, True, False)
    xk = ("x_min", "x_max", "x_max", "x_min")
    yk = ("y_min", "y_min", "y_max", "y_max")
    p = [plot_to_pixels(v[xk[i]], v[yk[i]]) for i in range(4)]
    pc = plot_to_pixels((v["x_min"] + v["x_max"]) / 2, (v["y_min"] + v["y_max"]) / 2)
    rect = (min(p[0][0], p[2][0]), min(p[0][1], p[2][1]), max(p[0][0], p[2][0]), max(p[0][1], p[2][1]))
    rect_grab = I.rect_expand(rect, DRAG_GRAB_HALF_SIZE)
    col32 = _tool_colour(col)
    col32_a = (col32[0], col32[1], col32[2], int(col32[3] * 0.25))
    base_id = (*ctx._ids, "#IMPLOT_DRAG_RECT", n_id)
    G = DRAG_GRAB_HALF_SIZE
    modified = False
    out_clicked = out_hovered = out_held = False
    if v["x_min"] != v["x_max"] or v["y_min"] != v["y_max"]:
        if use_input:
            ctx.set_next_item_allow_overlap()
            hov, hld, clk = ctx.button_behavior((pc[0] - G, pc[1] - G, 2 * G, 2 * G), base_id)
            out_clicked, out_hovered, out_held = clk, hov, hld
            if hld and _mouse_dragging():
                dx, dy = io.mouse_delta
                for i in range(4):
                    pp = pixels_to_plot(p[i][0] + dx, p[i][1] + dy)
                    v[yk[i]] = pp.y
                    v[xk[i]] = pp.x
                modified = True
    for i in range(4):
        hov = hld = clk = False
        if use_input:
            ctx.set_next_item_allow_overlap()
            hov, hld, clk = ctx.button_behavior((p[i][0] - G, p[i][1] - G, 2 * G, 2 * G), (base_id, "pt", i))
            out_clicked, out_hovered, out_held = out_clicked or clk, out_hovered or hov, out_held or hld
        if hld and _mouse_dragging():
            m = get_plot_mouse_pos()
            v[xk[i]], v[yk[i]] = m.x, m.y
            modified = True
        a, b = p[i], p[(i + 1) % 4]
        e_min = (min(a[0], b[0]), min(a[1], b[1]))
        e_max = (max(a[0], b[0]), max(a[1], b[1]))
        if h[i]:
            eb = (e_min[0] + G, e_min[1] - G, e_max[0] - G, e_max[1] + G)
        else:
            eb = (e_min[0] - G, e_min[1] + G, e_max[0] + G, e_max[1] - G)
        hov = hld = clk = False
        if use_input and eb[2] > eb[0] and eb[3] > eb[1]:
            ctx.set_next_item_allow_overlap()
            hov, hld, clk = ctx.button_behavior((eb[0], eb[1], eb[2] - eb[0], eb[3] - eb[1]), (base_id, "edge", i))
            out_clicked, out_hovered, out_held = out_clicked or clk, out_hovered or hov, out_held or hld
        if hld and _mouse_dragging():
            m = get_plot_mouse_pos()
            if h[i]:
                v[yk[i]] = m.y
            else:
                v[xk[i]] = m.x
            modified = True
        if hov and io.mouse_double_clicked[0]:
            lim = get_plot_limits()
            if h[i]:
                lo = (yk[i] == "y_min" and v["y_min"] < v["y_max"]) or (yk[i] == "y_max" and v["y_max"] < v["y_min"])
                v[yk[i]] = lim.y_min if lo else lim.y_max
            else:
                lo = (xk[i] == "x_min" and v["x_min"] < v["x_max"]) or (xk[i] == "x_max" and v["x_max"] < v["x_min"])
                v[xk[i]] = lim.x_min if lo else lim.x_max
            modified = True
    mouse_inside = I.rect_contains(rect_grab, io.mouse_pos)
    if use_input and mouse_inside:
        out_clicked = out_clicked or bool(io.mouse_clicked[0])
        out_hovered = True
        out_held = out_held or bool(io.mouse_down[0])
    fv = dict(v)
    show_grabs = use_input and (modified or mouse_inside)

    def render():
        t = _items._transformer()
        q = [t(fv[xk[i]], fv[yk[i]]) for i in range(4)]
        qc = t((fv["x_min"] + fv["x_max"]) / 2, (fv["y_min"] + fv["y_max"]) / 2)
        r = (min(q[0][0], q[2][0]), min(q[0][1], q[2][1]), max(q[0][0], q[2][0]), max(q[0][1], q[2][1]))
        _fill(r, col32_a)
        _stroke(r, col32)
        if show_grabs:
            from .painter import fill_circle
            fill_circle(_dl().p, qc[0], qc[1], G, col32)
            for pt in q:
                fill_circle(_dl().p, pt[0], pt[1], G, col32)

    _items._queue(render)
    return DragRectResult(modified, v["x_min"], v["y_min"], v["x_max"], v["y_max"],
                          out_clicked, out_hovered, out_held)


# --------------------------------------------------------------------------- #
# [SECTION] Legend utils
# --------------------------------------------------------------------------- #
def is_legend_entry_hovered(label_id: str) -> bool:
    """``IsLegendEntryHovered``."""
    if gp.current_items is None:
        return False
    item = _items.get_item(label_id)
    return item is not None and item.legend_hovered


def begin_legend_popup(label_id: str, mouse_button: int = 1) -> bool:
    """``BeginLegendPopup``: a popup for one legend entry; submit widgets and
    call :func:`end_legend_popup` when it returns True."""
    plot = _require_plot("begin_legend_popup")
    setup_lock()
    ctx = _ctx()
    io = ctx.io
    popups = plot.__dict__.setdefault("legend_popups", {})
    item = _items.get_item(label_id)
    key = _items._item_id(label_id)
    state = popups.get(key)
    if io.mouse_released[mouse_button] and item is not None and item.legend_hovered:
        state = popups[key] = {"pos": tuple(io.mouse_pos), "size": (220.0, 80.0), "just_opened": True}
    if state is None:
        return False
    if _menu_closed_by_click(state):
        popups.pop(key, None)
        return False
    from .drawlist import _Deferred
    from .flags import WindowFlags
    recorder = _Deferred(ctx.draw.p)
    state["saved"] = (ctx.p, ctx.draw.p)
    ctx.p = ctx.draw.p = recorder
    x, y = state["pos"]
    w, hgt = state["size"]
    _fill((x, y, x + w, y + hgt), _rgba(ctx.style.color(_core.Col.POPUP_BG)))
    _stroke((x, y, x + w, y + hgt), _rgba(ctx.style.color(_core.Col.BORDER)))
    ctx.begin(f"##legend_popup_{id(plot)}_{label_id}", (x + 4, y + 4, w - 8, max(hgt - 8, 20.0)),
              WindowFlags.ALWAYS_AUTO_RESIZE)
    ctx.push_id(("##legend_popup", key))
    state["recorder"] = recorder
    gp.open_legend_popup = state
    return True


def end_legend_popup() -> None:
    """``EndLegendPopup``."""
    state = getattr(gp, "open_legend_popup", None)
    if state is None:
        return
    ctx = _ctx()
    ctx.pop_id()
    window = ctx.current_window
    ctx.end()
    if window is not None:
        state["size"] = (max(220.0, window.box[2] + 8), window.box[3] + 8)
    state["just_opened"] = False
    ctx.p, ctx.draw.p = state.pop("saved")
    gp.pending_popups.append(("replay", state.pop("recorder")))
    gp.open_legend_popup = None


def show_alt_legend(title_id: str, vertical: bool = True, size=(0.0, 0.0), interactable: bool = True) -> None:
    """``ShowAltLegend``: the legend of plot *title_id*, as its own widget."""
    ctx = _ctx()
    plot = I.pools()["plots"].get(ctx.get_id(title_id))
    style = gp.style
    default = (style.legend_padding[0] * 2, style.legend_padding[1] * 2)
    legend_size = (0.0, 0.0)
    if plot is not None:
        legend_size = I.calc_legend_size(plot.items, style.legend_inner_padding, style.legend_spacing, vertical)
        default = (legend_size[0] + style.legend_padding[0] * 2, legend_size[1] + style.legend_padding[1] * 2)
    fw, fh = _calc_item_size(size, *default)
    x, y = _w.get_cursor_screen_pos()
    _w.dummy(fw, fh)
    frame = (x, y, x + fw, y + fh)
    _fill(frame, I.get_style_color_u32(I.COL_FRAME_BG))
    if plot is None:
        return
    dl = _dl()
    dl.push_clip_rect((frame[0], frame[1]), (frame[2], frame[3]))
    pos = I.get_location_pos(frame, legend_size, 0, style.legend_padding)
    bb = (pos[0], pos[1], pos[0] + legend_size[0], pos[1] + legend_size[1])
    _fill(bb, I.get_style_color_u32(I.COL_LEGEND_BG))
    _stroke(bb, I.get_style_color_u32(I.COL_LEGEND_BORDER))
    saved = gp.current_items
    gp.current_items = plot.items
    _show_legend_entries(plot.items, bb, interactable and I.rect_contains(frame, ctx.io.mouse_pos),
                         style.legend_inner_padding, style.legend_spacing, vertical)
    gp.current_items = saved
    dl.pop_clip_rect()


# --------------------------------------------------------------------------- #
# [SECTION] Custom rendering
# --------------------------------------------------------------------------- #
class _PlotDrawList:
    """``GetPlotDrawList``: a draw list whose calls are replayed in ``end_plot``.

    Coordinates were computed by the caller with the axes of the moment
    (``plot_to_pixels``); if the fit moves the axes before drawing, every
    point argument is carried through plot units onto the fitted axes.
    """

    def __init__(self, plot) -> None:
        self._plot = plot

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        plot = self._plot

        def record(*args, **kwargs):
            snap = getattr(plot, "snapshot", None)
            xi, yi = plot.current_x, plot.current_y

            def render():
                if snap:
                    sx, sy = snap[xi], snap[yi]
                    fx, fy = plot.axes[xi], plot.axes[yi]

                    def remap(pt):
                        return (fx.plot_to_pixels(sx.pixels_to_plot(pt[0])),
                                fy.plot_to_pixels(sy.pixels_to_plot(pt[1])))
                    new_args = [_remap_arg(a, remap) for a in args]
                else:
                    new_args = list(args)
                getattr(_dl(), name)(*new_args, **kwargs)

            plot.queue.append((xi, yi, render, 0.0, False))
        return record


def _is_point(a) -> bool:
    return (isinstance(a, (tuple, list)) and len(a) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in a))


def _remap_arg(a, remap):
    if _is_point(a):
        return remap(a)
    if isinstance(a, (list, tuple)) and a and all(_is_point(v) for v in a):
        return [remap(v) for v in a]
    return a


def get_plot_draw_list() -> _PlotDrawList:
    plot = _require_plot("get_plot_draw_list")
    setup_lock()
    return _PlotDrawList(plot)


def push_plot_clip_rect(expand: float = 0.0) -> None:
    """``PushPlotClipRect``: queued, and resolved against the final plot rect."""
    plot = _require_plot("push_plot_clip_rect")
    setup_lock()

    def render():
        r = gp.current_plot.plot_rect
        _dl().push_clip_rect((r[0] - expand, r[1] - expand), (r[2] + expand, r[3] + expand))

    plot.queue.append((plot.current_x, plot.current_y, render, 0.0, False))


def pop_plot_clip_rect() -> None:
    plot = _require_plot("pop_plot_clip_rect")
    plot.queue.append((plot.current_x, plot.current_y, lambda: _dl().pop_clip_rect(), 0.0, False))


# --------------------------------------------------------------------------- #
# [SECTION] Styling
# --------------------------------------------------------------------------- #
def get_style() -> I.PlotStyle:
    return gp.style


def push_style_color(idx: int, col) -> None:
    gp.color_modifiers.append((idx, gp.style.colors[idx]))
    gp.style.colors[idx] = _rgba(col)


def pop_style_color(count: int = 1) -> None:
    for _ in range(count):
        if not gp.color_modifiers:
            break
        idx, backup = gp.color_modifiers.pop()
        gp.style.colors[idx] = backup


def push_style_var(idx: int, val) -> None:
    attr = I.STYLE_VAR_ATTRS[idx]
    gp.style_modifiers.append((attr, getattr(gp.style, attr)))
    setattr(gp.style, attr, tuple(float(v) for v in val) if _items._is_series(val) else float(val))


def pop_style_var(count: int = 1) -> None:
    for _ in range(count):
        if not gp.style_modifiers:
            break
        attr, backup = gp.style_modifiers.pop()
        setattr(gp.style, attr, backup)


def get_last_item_color() -> tuple:
    """``GetLastItemColor``, as ``ImVec4`` floats."""
    if gp.previous_item is not None:
        return I.col_u32_to_float4(gp.previous_item.color)
    return (0.0, 0.0, 0.0, 0.0)


def get_style_color_name(idx: int) -> str:
    return I.COL_NAMES[idx]


def get_marker_name(idx: int) -> str:
    if idx == I.MARKER_NONE:
        return "None"
    if idx == I.MARKER_AUTO:
        return "Auto"
    return I.MARKER_NAMES[idx] if 0 <= idx < I.MARKER_COUNT else ""


def next_marker() -> int:
    if gp.current_items is None:
        raise RuntimeError("next_marker() needs to be called between begin_plot() and end_plot()")
    return _items._next_marker()


def style_colors_auto(dst: I.PlotStyle = None) -> None:
    style = dst or gp.style
    style.minor_alpha = 0.25
    style.colors = [None] * I.COL_COUNT


def _style_colors(dst, table: dict, minor_alpha: float) -> None:
    style = dst or gp.style
    style.minor_alpha = minor_alpha
    for idx, col in table.items():
        style.colors[idx] = _rgba(col)


def style_colors_classic(dst: I.PlotStyle = None) -> None:
    """``StyleColorsClassic``."""
    _style_colors(dst, {
        I.COL_FRAME_BG: (0.43, 0.43, 0.43, 0.39), I.COL_PLOT_BG: (0.0, 0.0, 0.0, 0.35),
        I.COL_PLOT_BORDER: (0.50, 0.50, 0.50, 0.50), I.COL_LEGEND_BG: (0.11, 0.11, 0.14, 0.92),
        I.COL_LEGEND_BORDER: (0.50, 0.50, 0.50, 0.50), I.COL_LEGEND_TEXT: (0.90, 0.90, 0.90, 1.00),
        I.COL_TITLE_TEXT: (0.90, 0.90, 0.90, 1.00), I.COL_INLAY_TEXT: (0.90, 0.90, 0.90, 1.00),
        I.COL_AXIS_TEXT: (0.90, 0.90, 0.90, 1.00), I.COL_AXIS_GRID: (0.90, 0.90, 0.90, 0.25),
        I.COL_AXIS_TICK: None, I.COL_AXIS_BG: None, I.COL_AXIS_BG_HOVERED: None,
        I.COL_AXIS_BG_ACTIVE: None, I.COL_SELECTION: (0.97, 0.97, 0.39, 1.00),
        I.COL_CROSSHAIRS: (0.50, 0.50, 0.50, 0.75)}, 0.5)


def style_colors_dark(dst: I.PlotStyle = None) -> None:
    """``StyleColorsDark``."""
    _style_colors(dst, {
        I.COL_FRAME_BG: (1.0, 1.0, 1.0, 0.07), I.COL_PLOT_BG: (0.0, 0.0, 0.0, 0.50),
        I.COL_PLOT_BORDER: (0.43, 0.43, 0.50, 0.50), I.COL_LEGEND_BG: (0.08, 0.08, 0.08, 0.94),
        I.COL_LEGEND_BORDER: (0.43, 0.43, 0.50, 0.50), I.COL_LEGEND_TEXT: (1.0, 1.0, 1.0, 1.0),
        I.COL_TITLE_TEXT: (1.0, 1.0, 1.0, 1.0), I.COL_INLAY_TEXT: (1.0, 1.0, 1.0, 1.0),
        I.COL_AXIS_TEXT: (1.0, 1.0, 1.0, 1.0), I.COL_AXIS_GRID: (1.0, 1.0, 1.0, 0.25),
        I.COL_AXIS_TICK: None, I.COL_AXIS_BG: None, I.COL_AXIS_BG_HOVERED: None,
        I.COL_AXIS_BG_ACTIVE: None, I.COL_SELECTION: (1.0, 0.60, 0.0, 1.0),
        I.COL_CROSSHAIRS: (0.43, 0.43, 0.50, 0.50)}, 0.25)


def style_colors_light(dst: I.PlotStyle = None) -> None:
    """``StyleColorsLight``."""
    _style_colors(dst, {
        I.COL_FRAME_BG: (1.0, 1.0, 1.0, 1.0), I.COL_PLOT_BG: (0.42, 0.57, 1.0, 0.13),
        I.COL_PLOT_BORDER: (0.0, 0.0, 0.0, 0.0), I.COL_LEGEND_BG: (1.0, 1.0, 1.0, 0.98),
        I.COL_LEGEND_BORDER: (0.82, 0.82, 0.82, 0.80), I.COL_LEGEND_TEXT: (0.0, 0.0, 0.0, 1.0),
        I.COL_TITLE_TEXT: (0.0, 0.0, 0.0, 1.0), I.COL_INLAY_TEXT: (0.0, 0.0, 0.0, 1.0),
        I.COL_AXIS_TEXT: (0.0, 0.0, 0.0, 1.0), I.COL_AXIS_GRID: (1.0, 1.0, 1.0, 1.0),
        I.COL_AXIS_TICK: (0.0, 0.0, 0.0, 0.25), I.COL_AXIS_BG: None, I.COL_AXIS_BG_HOVERED: None,
        I.COL_AXIS_BG_ACTIVE: None, I.COL_SELECTION: (0.82, 0.64, 0.03, 1.0),
        I.COL_CROSSHAIRS: (0.0, 0.0, 0.0, 0.5)}, 1.0)


# --------------------------------------------------------------------------- #
# [SECTION] Colormaps
# --------------------------------------------------------------------------- #
def add_colormap(name: str, colors, size=None, qual: bool = True) -> int:
    """``AddColormap``: returns the new index (``-1`` if the name is taken)."""
    cols = list(colors)[:size] if size is not None else list(colors)
    if len(cols) <= 1:
        raise ValueError("The colormap size must be greater than 1")
    return gp.colormap_data.append(name, cols, qual)


def get_colormap_count() -> int:
    return gp.colormap_data.count


def get_colormap_name(cmap: int):
    return gp.colormap_data.get_name(cmap)


def get_colormap_index(name: str) -> int:
    return gp.colormap_data.get_index(name)


def _resolve_cmap(cmap) -> int:
    if cmap is None or cmap == I.IMPLOT_AUTO:
        return gp.style.colormap
    if isinstance(cmap, str):
        idx = gp.colormap_data.get_index(cmap)
        if idx < 0:
            raise ValueError(f"The colormap name is invalid: {cmap!r}")
        return idx
    if _items._is_series(cmap):
        keys = tuple(tuple(_rgba(c)) for c in cmap)
        name = "##emtk_anon_" + "_".join("%d.%d.%d.%d" % c for c in keys)
        idx = gp.colormap_data.get_index(name)
        if idx < 0:
            idx = gp.colormap_data.append(name, keys, len(keys) < 2)
            gp.anon_colormaps[idx] = keys
        return idx
    return int(cmap)


def push_colormap(cmap) -> None:
    """``PushColormap``: an index, a name -- or, emtk's convenience, a list of
    colours (a continuous map through them)."""
    idx = _resolve_cmap(cmap)
    gp.colormap_modifiers.append(gp.style.colormap)
    gp.style.colormap = idx


def pop_colormap(count: int = 1) -> None:
    for _ in range(count):
        if not gp.colormap_modifiers:
            break
        gp.style.colormap = gp.colormap_modifiers.pop()


def _heatmap_uses_style_colormap() -> bool:
    """A continuous style colormap is honoured by heatmaps without a push."""
    return not gp.colormap_data.is_qual(gp.style.colormap)


def next_colormap_color() -> tuple:
    if gp.current_items is None:
        raise RuntimeError("next_colormap_color() needs to be called between begin_plot() and end_plot()")
    return I.col_u32_to_float4(I.next_colormap_color_u32())


def get_colormap_size(cmap=I.IMPLOT_AUTO) -> int:
    return gp.colormap_data.get_key_count(_resolve_cmap(cmap))


def get_colormap_color(idx: int, cmap=I.IMPLOT_AUTO) -> tuple:
    """``GetColormapColor``, as ``ImVec4`` floats."""
    return I.col_u32_to_float4(I.get_colormap_color_u32(idx, _resolve_cmap(cmap)))


def sample_colormap(t: float, cmap=I.IMPLOT_AUTO) -> tuple:
    """``SampleColormap``, as ``ImVec4`` floats."""
    return I.col_u32_to_float4(I.sample_colormap_u32(t, _resolve_cmap(cmap)))


def _ramp_colour(stops, t: float) -> tuple:
    """The colour a continuous map through *stops* gives at ``t`` -- the byte
    ``LerpTable`` lands on."""
    idx = _resolve_cmap(stops)
    return gp.colormap_data.lerp_table(idx, min(max(t, 0.0), 1.0))


def render_color_bar(colors, rect, vertical: bool, reversed_: bool, continuous: bool) -> None:
    """``RenderColorBar``: *rect* is ``(x0, y0, x1, y1)``."""
    size = len(colors)
    n = size - 1 if continuous else size
    if n <= 0:
        return
    p = _dl().p
    x0, y0, x1, y1 = rect
    span = (y1 - y0) if vertical else (x1 - x0)
    step = span / n
    for i in range(n):
        if reversed_:
            c1 = colors[size - i - 1]
            c2 = colors[size - i - 2] if continuous else c1
        else:
            c1 = colors[i]
            c2 = colors[i + 1] if continuous else c1
        a = (y0 if vertical else x0) + i * step
        b = a + step
        if c1 == c2:
            if vertical:
                p.fill_rect(x0, a, x1 - x0, step, c1)
            else:
                p.fill_rect(a, y0, step, y1 - y0, c1)
            continue
        lo, hi = int(math.floor(a)), int(math.ceil(b))
        for k in range(lo, hi):
            f = min(max((k + 0.5 - a) / step, 0.0), 1.0)
            c = tuple(int(round(c1[j] + (c2[j] - c1[j]) * f)) for j in range(4))
            s0, s1 = max(k, a), min(k + 1, b)
            if s1 <= s0:
                continue
            if vertical:
                p.fill_rect(x0, s0, x1 - x0, s1 - s0, c)
            else:
                p.fill_rect(s0, y0, s1 - s0, y1 - y0, c)


def colormap_scale(label: str, scale_min: float, scale_max: float, size=(0.0, 0.0), fmt: str = "%g",
                   flags: int = 0, cmap=I.IMPLOT_AUTO) -> None:
    """``ColormapScale``: a vertical colour bar with ticks and a label."""
    style = gp.style
    cmap = _resolve_cmap(cmap)
    label_size = (0.0, 0.0)
    if not has_flag(flags, I.COLORMAP_SCALE_FLAGS_NO_LABEL):
        label_size = I.calc_text_size(label, True)
    fw, fh = _calc_item_size(size, 0.0, style.plot_default_size[1])
    if fh < style.plot_min_size[1] and float(size[1]) < 0.0:
        fh = style.plot_min_size[1]
    rng = (min(scale_min, scale_max), max(scale_min, scale_max))
    ticker = gp.c_ticker
    ticker.reset()
    I.locator_default(ticker, rng, fh, True, I.formatter_default, fmt)
    rend_label = label_size[0] > 0
    txt_off = style.label_padding[0]
    pad = txt_off + ticker.max_size[0] + (txt_off + label_size[1] if rend_label else 0)
    bar_w = 20.0
    if fw == 0:
        fw = bar_w + pad + 2 * style.plot_padding[0]
    else:
        bar_w = max(fw - (pad + 2 * style.plot_padding[0]), style.major_tick_len[1])
    x, y = _w.get_cursor_screen_pos()
    _w.dummy(fw, fh)
    frame = (x, y, x + fw, y + fh)
    _fill(frame, I.get_style_color_u32(I.COL_FRAME_BG))
    opposite = has_flag(flags, I.COLORMAP_SCALE_FLAGS_OPPOSITE)
    inverted = has_flag(flags, I.COLORMAP_SCALE_FLAGS_INVERT)
    reversed_ = scale_min > scale_max
    shift = pad if opposite else 0.0
    grad = (x + style.plot_padding[0] + shift, y + style.plot_padding[1],
            x + bar_w + style.plot_padding[0] + shift, y + fh - style.plot_padding[1])
    dl = _dl()
    dl.push_clip_rect((frame[0], frame[1]), (frame[2], frame[3]))
    col_text = _rgba(_ctx().style.color(_core.Col.TEXT))
    invert_scale = (not reversed_) if inverted else reversed_
    y_min = grad[3] if invert_scale else grad[1]
    y_max = grad[1] if invert_scale else grad[3]
    render_color_bar(gp.colormap_data.get_keys(cmap), grad, True, not inverted,
                     not gp.colormap_data.is_qual(cmap))
    for tk in ticker.ticks:
        y_pos = I.remap(tk.plot_pos, rng[1], rng[0], y_min, y_max)
        tick_w = style.major_tick_len[1] if tk.major else style.minor_tick_len[1]
        tick_t = style.major_tick_size[1] if tk.major else style.minor_tick_size[1]
        den = scale_max - scale_min
        tick_col = I.calc_text_color(gp.colormap_data.lerp_table(cmap, (tk.plot_pos - scale_min) / den if den else 0))
        if grad[1] + 2 < y_pos < grad[3] - 2:
            if opposite:
                _line_h(grad[0] + 1, grad[0] + tick_w, y_pos, tick_col, tick_t)
            else:
                _line_h(grad[2] - 1, grad[2] - tick_w, y_pos, tick_col, tick_t)
        tx = grad[0] - txt_off - tk.label_size[0] if opposite else grad[2] + txt_off
        if tk.show_label and tk.text:
            _add_text((tx, y_pos - tk.label_size[1] * 0.5), col_text, tk.text)
    if rend_label:
        pos_x = x + style.plot_padding[0] if opposite else grad[2] + 2 * txt_off + ticker.max_size[0]
        pos_y = (grad[1] + grad[3]) * 0.5 + label_size[0] * 0.5
        _add_text_vertical((pos_x, pos_y), col_text, label)
    _stroke(grad, I.get_style_color_u32(I.COL_PLOT_BORDER))
    dl.pop_clip_rect()


def colormap_slider(label: str, t: float, fmt: str = "", cmap=I.IMPLOT_AUTO):
    """``ColormapSlider``: returns ``(changed, t, colour)``, the colour as floats."""
    cmap = _resolve_cmap(cmap)
    t = min(max(float(t), 0.0), 1.0)
    x, y = _w.get_cursor_screen_pos()
    w = _w.calc_item_width()
    h = _core.get_frame_height()
    render_color_bar(gp.colormap_data.get_keys(cmap), (x, y, x + w, y + h), False, False,
                     not gp.colormap_data.is_qual(cmap))
    grab = I.calc_text_color(gp.colormap_data.lerp_table(cmap, t))
    Col = _core.Col
    _w.push_style_color(Col.FRAME_BG, (0, 0, 0, 0))
    _w.push_style_color(Col.FRAME_BG_ACTIVE, (0, 0, 0, 0))
    _w.push_style_color(Col.FRAME_BG_HOVERED, (255, 255, 255, 25))
    _w.push_style_color(Col.SLIDER_GRAB, grab)
    _w.push_style_color(Col.SLIDER_GRAB_ACTIVE, grab)
    _w.set_next_item_width(w)
    changed, t = _w.slider_float(label, t, 0.0, 1.0, fmt or "%.3f")
    _w.pop_style_color(5)
    return changed, t, I.col_u32_to_float4(gp.colormap_data.lerp_table(cmap, t))


def colormap_button(label: str, size=(0.0, 0.0), cmap=I.IMPLOT_AUTO) -> bool:
    """``ColormapButton``."""
    cmap = _resolve_cmap(cmap)
    ctx = _ctx()
    tw, th = I.calc_text_size(label, True)
    fp = ctx.style.frame_padding
    w, h = _calc_item_size(size, tw + fp[0] * 2, th + fp[1] * 2)
    x, y = _w.get_cursor_screen_pos()
    render_color_bar(gp.colormap_data.get_keys(cmap), (x, y, x + w, y + h), False, False,
                     not gp.colormap_data.is_qual(cmap))
    text = I.calc_text_color(gp.colormap_data.lerp_table(cmap, 0.5))
    Col = _core.Col
    _w.push_style_color(Col.BUTTON, (0, 0, 0, 0))
    _w.push_style_color(Col.BUTTON_HOVERED, (255, 255, 255, 25))
    _w.push_style_color(Col.BUTTON_ACTIVE, (255, 255, 255, 51))
    _w.push_style_color(Col.TEXT, text)
    pressed = _w.button(label, (w, h))
    _w.pop_style_color(4)
    return pressed


def bust_plot_cache() -> None:
    """``BustPlotCache``: forget every plot and subplot."""
    I.pools()["plots"].clear()
    I.pools()["subplots"].clear()


# --------------------------------------------------------------------------- #
# [SECTION] Input mapping and miscellaneous
# --------------------------------------------------------------------------- #
def get_input_map() -> I.InputMap:
    return gp.input_map


def map_input_default(dst: I.InputMap = None) -> None:
    I.map_input_default(dst or gp.input_map)


def map_input_reverse(dst: I.InputMap = None) -> None:
    I.map_input_reverse(dst or gp.input_map)


def item_icon(col) -> None:
    """``ItemIcon``: a legend-style swatch as a widget."""
    s = I.text_line_height()
    x, y = _w.get_cursor_screen_pos()
    _fill((x, y + 2, x + s - 4, y + s - 2), _rgba(col))
    _w.dummy(s - 4, s)


def colormap_icon(cmap) -> None:
    """``ColormapIcon``."""
    cmap = _resolve_cmap(cmap)
    s = I.text_line_height()
    x, y = _w.get_cursor_screen_pos()
    render_color_bar(gp.colormap_data.get_keys(cmap), (x, y + 2, x + s - 4, y + s - 2), False, False,
                     not gp.colormap_data.is_qual(cmap))
    _w.dummy(s - 4, s)


# --------------------------------------------------------------------------- #
# The obsolete SetNext*Style calls emtk callers still make
# --------------------------------------------------------------------------- #
def set_next_line_style(colour=None, weight: float = I.IMPLOT_AUTO, dash=None) -> None:
    """``SetNextLineStyle`` (obsolete in ImPlot 1.0, kept): the next item's
    line colour and weight. ``dash`` -- ``(on, off)`` pixels -- is emtk's."""
    gp.legacy_line = (_rgba(colour), weight, dash)


def set_next_fill_style(colour=None, alpha: float = I.IMPLOT_AUTO) -> None:
    """``SetNextFillStyle`` (obsolete, kept)."""
    gp.legacy_fill = (_rgba(colour), alpha)


def set_next_marker_style(marker: int = I.IMPLOT_AUTO, size: float = I.IMPLOT_AUTO, fill=None,
                          weight: float = I.IMPLOT_AUTO, outline=None) -> None:
    """``SetNextMarkerStyle`` (obsolete, kept). A fill given without an outline
    fills the whole marker, as emtk's markers always did."""
    gp.legacy_marker = (marker, size, _rgba(fill), weight, _rgba(outline))


def set_next_error_bar_style(colour=None, size: float = I.IMPLOT_AUTO, weight: float = I.IMPLOT_AUTO) -> None:
    gp.legacy_line = (_rgba(colour), weight, None)
    gp.legacy_errsize = size


def _apply_legacy_styles(spec: I.PlotSpec) -> None:
    line, gp.legacy_line = gp.legacy_line, None
    fill, gp.legacy_fill = gp.legacy_fill, None
    marker, gp.legacy_marker = gp.legacy_marker, None
    errsize = getattr(gp, "legacy_errsize", None)
    gp.legacy_errsize = None
    if line is not None:
        col, weight, dash = line
        if col is not None and spec.line_color is None:
            spec.line_color = col
        if weight is not None and weight != I.IMPLOT_AUTO:
            spec.line_weight = float(weight)
        if dash is not None:
            spec.dash = dash
    if errsize is not None and errsize != I.IMPLOT_AUTO:
        spec.size = float(errsize)
    if fill is not None:
        col, alpha = fill
        if col is not None and spec.fill_color is None:
            spec.fill_color = col
        if alpha is not None and alpha != I.IMPLOT_AUTO:
            spec.fill_alpha = float(alpha)
    if marker is not None:
        mk, size, mfill, weight, outline = marker
        if mk is not None and mk != I.IMPLOT_AUTO:
            spec.marker = int(mk)
        elif spec.marker == I.MARKER_NONE:
            spec.marker = I.MARKER_AUTO
        if size is not None and size != I.IMPLOT_AUTO and size > 0:
            spec.marker_size = float(size)
        if mfill is not None:
            spec.marker_fill_color = mfill
            if outline is None:
                spec.marker_line_color = mfill
        if outline is not None:
            spec.marker_line_color = outline
        if weight is not None and weight != I.IMPLOT_AUTO and weight > 0:
            spec.line_weight = float(weight)


# --------------------------------------------------------------------------- #
# The C++ spellings
#
# A mechanically ported source names the constants as implot.h does; binding
# them here means a ported line is the C++ line.
# --------------------------------------------------------------------------- #
def _camel(name: str) -> str:
    return "".join(part.capitalize() for part in name.lower().split("_"))


_SPECIAL = {"RDBU": "RdBu", "BRBG": "BrBG", "PIYG": "PiYG", "SYMLOG": "SymLog", "LOG10": "Log10",
            "ISO8601": "ISO8601"}


def _cpp_names() -> dict:
    out = {}
    prefixes = (
        ("AXIS_FLAGS_", "ImPlotAxisFlags_"), ("SUBPLOT_FLAGS_", "ImPlotSubplotFlags_"),
        ("LEGEND_FLAGS_", "ImPlotLegendFlags_"), ("MOUSE_TEXT_FLAGS_", "ImPlotMouseTextFlags_"),
        ("DRAG_TOOL_FLAGS_", "ImPlotDragToolFlags_"), ("COLORMAP_SCALE_FLAGS_", "ImPlotColormapScaleFlags_"),
        ("ITEM_FLAGS_", "ImPlotItemFlags_"), ("LINE_FLAGS_", "ImPlotLineFlags_"),
        ("SCATTER_FLAGS_", "ImPlotScatterFlags_"), ("BUBBLES_FLAGS_", "ImPlotBubblesFlags_"),
        ("POLYGON_FLAGS_", "ImPlotPolygonFlags_"), ("STAIRS_FLAGS_", "ImPlotStairsFlags_"),
        ("SHADED_FLAGS_", "ImPlotShadedFlags_"), ("BARS_FLAGS_", "ImPlotBarsFlags_"),
        ("BAR_GROUPS_FLAGS_", "ImPlotBarGroupsFlags_"), ("ERROR_BARS_FLAGS_", "ImPlotErrorBarsFlags_"),
        ("STEMS_FLAGS_", "ImPlotStemsFlags_"), ("INF_LINES_FLAGS_", "ImPlotInfLinesFlags_"),
        ("PIE_CHART_FLAGS_", "ImPlotPieChartFlags_"), ("HEATMAP_FLAGS_", "ImPlotHeatmapFlags_"),
        ("HISTOGRAM_FLAGS_", "ImPlotHistogramFlags_"), ("DIGITAL_FLAGS_", "ImPlotDigitalFlags_"),
        ("IMAGE_FLAGS_", "ImPlotImageFlags_"), ("TEXT_FLAGS_", "ImPlotTextFlags_"),
        ("DUMMY_FLAGS_", "ImPlotDummyFlags_"), ("FLAGS_", "ImPlotFlags_"), ("COND_", "ImPlotCond_"),
        ("COL_", "ImPlotCol_"), ("STYLE_VAR_", "ImPlotStyleVar_"), ("SCALE_", "ImPlotScale_"),
        ("MARKER_", "ImPlotMarker_"), ("COLORMAP_", "ImPlotColormap_"), ("LOCATION_", "ImPlotLocation_"),
        ("BIN_", "ImPlotBin_"), ("PROP_", "ImPlotProp_"), ("AXIS_", "ImAxis_"),
    )
    for name in dir(I):
        if not name.isupper():
            continue
        for prefix, cpp in prefixes:
            if name.startswith(prefix):
                rest = name[len(prefix):]
                if cpp == "ImAxis_":
                    if rest in ("X1", "X2", "X3", "Y1", "Y2", "Y3", "COUNT"):
                        out[cpp + rest] = getattr(I, name)
                    break
                if rest in ("COUNT",):
                    out[cpp + "COUNT"] = getattr(I, name)
                    break
                out[cpp + _SPECIAL.get(rest, _camel(rest))] = getattr(I, name)
                break
    out["ImPlotBarsFlags_Horizontal"] = I.BARS_FLAGS_HORIZONTAL
    out["ImPlotInfLinesFlags_Horizontal"] = I.INF_LINES_FLAGS_HORIZONTAL
    out["ImPlotHeatmapFlags_ColMajor"] = I.HEATMAP_FLAGS_COL_MAJOR
    out["ImPlotFlags_CanvasOnly"] = I.FLAGS_CANVAS_ONLY
    out["ImPlotAxisFlags_AuxDefault"] = I.AXIS_FLAGS_AUX_DEFAULT
    out["ImPlotAxisFlags_NoDecorations"] = I.AXIS_FLAGS_NO_DECORATIONS
    out["IMPLOT_AUTO"] = I.IMPLOT_AUTO
    out["IMPLOT_AUTO_COL"] = None
    return out


globals().update(_cpp_names())
#: A ported ``ImPlotColormap_Jet`` passed to ``push_colormap`` is an index, as in C++.
__all__ += [n for n in _cpp_names()]
__all__ += [
    "begin_plot", "end_plot", "begin_subplots", "end_subplots", "setup_axis", "setup_axis_limits",
    "setup_axis_format", "setup_axis_links", "setup_axis_ticks", "setup_axis_scale",
    "setup_axis_limits_constraints", "setup_axis_zoom_constraints", "setup_axes", "setup_axes_limits",
    "setup_legend", "setup_mouse_text", "setup_finish", "set_next_axis_limits", "set_next_axis_links",
    "set_next_axis_to_fit", "set_next_axes_limits", "set_next_axes_to_fit", "set_axis", "set_axes",
    "pixels_to_plot", "plot_to_pixels", "get_plot_pos", "get_plot_size", "get_plot_mouse_pos",
    "get_plot_limits", "is_plot_hovered", "is_axis_hovered", "is_subplots_hovered", "is_plot_selected",
    "get_plot_selection", "cancel_plot_selection", "hide_next_item", "begin_aligned_plots",
    "end_aligned_plots", "annotation", "tag_x", "tag_y", "drag_point", "drag_line_x", "drag_line_y",
    "drag_rect", "is_legend_entry_hovered", "begin_legend_popup", "end_legend_popup", "show_alt_legend",
    "get_style", "push_style_color", "pop_style_color", "push_style_var", "pop_style_var",
    "get_last_item_color", "get_style_color_name", "get_marker_name", "next_marker",
    "style_colors_auto", "style_colors_classic", "style_colors_dark", "style_colors_light",
    "add_colormap", "get_colormap_count", "get_colormap_name", "get_colormap_index", "push_colormap",
    "pop_colormap", "next_colormap_color", "get_colormap_size", "get_colormap_color", "sample_colormap",
    "colormap_scale", "colormap_slider", "colormap_button", "bust_plot_cache", "get_input_map",
    "map_input_default", "map_input_reverse", "item_icon", "colormap_icon", "get_plot_draw_list",
    "push_plot_clip_rect", "pop_plot_clip_rect", "set_next_line_style", "set_next_fill_style",
    "set_next_marker_style", "set_next_error_bar_style", "show_plot_context_menu",
    "show_axis_context_menu", "show_legend_context_menu", "show_subplots_context_menu",
]

# the time utilities a custom plotter reaches for (``ImPlot::RoundTime`` ...)
make_time = I.make_time
add_time = I.add_time
floor_time = I.floor_time
ceil_time = I.ceil_time
round_time = I.round_time
combine_date_time = I.combine_date_time
format_date = I.format_date
format_time = I.format_time
format_date_time = I.format_date_time
__all__ += ["make_time", "add_time", "floor_time", "ceil_time", "round_time", "combine_date_time",
            "format_date", "format_time", "format_date_time"]
