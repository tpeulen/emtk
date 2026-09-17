"""``emtk.implot_items`` -- ImPlot's ``implot_items.cpp``: every plot item.

Ported from epezent/implot at 7eeb916 (``junk/implot``, MIT). The structure
follows the reference: ``BeginItem``/``EndItem`` register the item, pick its
colour and marker and fit the axes; a renderer turns data into primitives.
The reference's templated getters/indexers/renderers collapse into plain
Python -- a getter is a list of points -- and its vertex-level ``Prim*``
writers become the painter operations they stand for (a line is two
triangles, a filled rectangle is ``fill_rect``, a marker is a convex fan).

What changes is *when* a renderer runs. ImPlot draws an item the moment it is
called, against axes that were fit on the previous frame. emtk queues the
renderer on the plot (``Plot.queue``) and runs it from ``EndPlot``, after the
fit, so a plot shown for the first time -- which is every headless
screenshot and every test -- is drawn against the range of its own data.
Registration, colour, legend entry and fitting still happen at call time,
exactly where the reference does them.
"""
from __future__ import annotations

import math

from . import implot_internal as I
from . import im_core as _core
from .implot_internal import gp, has_flag
from .painter import fill_convex as _fill_convex
from .painter import line as _line
from .painter import polyline as _polyline

__all__ = [
    "plot_line", "plot_line_g", "plot_scatter", "plot_scatter_g", "plot_bubbles",
    "plot_polygon", "plot_stairs", "plot_stairs_g", "plot_shaded", "plot_shaded_g",
    "plot_bars", "plot_bars_g", "plot_bar_groups", "plot_error_bars", "plot_stems",
    "plot_inf_lines", "plot_pie_chart", "plot_heatmap", "plot_histogram",
    "plot_histogram_2d", "plot_digital", "plot_digital_g", "plot_image", "plot_text",
    "plot_dummy", "begin_item", "end_item", "get_item", "get_current_item",
    "fit_this_frame", "fit_point", "fit_point_x", "fit_point_y", "is_item_hidden",
    "bust_item_cache", "bust_color_cache", "render_markers",
]

SQRT_1_2 = 0.70710678118
SQRT_3_2 = 0.86602540378
ITEM_HIGHLIGHT_LINE_SCALE = 2.0
ITEM_HIGHLIGHT_MARK_SCALE = 1.25


def _api():
    from . import implot
    return implot


def _dl():
    return _core.get_current_context().draw


# --------------------------------------------------------------------------- #
# [SECTION] Data access (Indexers and Getters)
# --------------------------------------------------------------------------- #
def _is_series(v) -> bool:
    """An array of samples, or a scalar? ImPlot tells its overloads apart by
    the C++ type; Python asks at run time. A string is never a series."""
    return v is not None and not isinstance(v, (str, bytes)) and hasattr(v, "__len__")


def _values(data, count=None, offset: int = 0, stride: int = I.IMPLOT_AUTO) -> list:
    """``IndexerIdx``: ``count`` samples starting at ``offset`` (wrapping), taking
    every ``stride``-th element. ``stride`` is in *elements* here -- Python
    has no bytes to stride over."""
    if data is None:
        return []
    if not _is_series(data):
        data = [data]
    step = 1 if stride in (I.IMPLOT_AUTO, None, 0) else int(stride)
    n = len(data) // step if step > 1 else len(data)
    count = n if count is None else min(int(count), n)
    if count <= 0:
        return []
    off = int(offset) % count if count else 0
    if off == 0 and step == 1:
        return [float(data[i]) for i in range(count)]
    return [float(data[((off + i) % count) * step]) for i in range(count)]


def _lin(count: int, scale: float, start: float) -> list:
    """``IndexerLin``."""
    return [scale * i + start for i in range(count)]


def _getter_points(getter, data, count: int) -> list:
    """``GetterFuncPtr``: a ``(idx, data) -> (x, y)`` function."""
    out = []
    for i in range(int(count)):
        p = getter(i, data)
        out.append((float(p[0]), float(p[1])))
    return out


def _colors(arr, count: int, alpha: float = 1.0):
    """``GetterIdxColor``: per-index colours, alpha applied."""
    if arr is None:
        return None
    out = []
    for i in range(count):
        c = I.rgba(arr[i]) or (0, 0, 0, 0)
        if alpha < 1.0:
            c = (c[0], c[1], c[2], int(c[3] * alpha))
        out.append(c)
    return out


def _const(col, alpha: float = 1.0):
    """``GetterConstColor``."""
    if alpha < 1.0:
        return (col[0], col[1], col[2], int(col[3] * alpha))
    return col


# --------------------------------------------------------------------------- #
# [SECTION] Item utils
# --------------------------------------------------------------------------- #
def _item_id(label_id: str):
    """The item's id, as ``PushOverrideID(items.ID)`` makes it: relative to its
    item group, so subplots sharing items share them, but still under any id
    the caller pushed inside the plot (the markers demo pushes one per row)."""
    ctx = _core.get_current_context()
    depth = getattr(gp, "item_id_depth", 0)
    group = gp.current_items.id if gp.current_items is not None else None
    return (group, *ctx._ids[depth:], str(label_id))


def register_or_get_item(label_id: str, flags: int):
    """``RegisterOrGetItem``: ``(item, just_created)``."""
    items = gp.current_items
    item_id = _item_id(label_id)
    just_created = items.get_item(item_id) is None
    item = items.get_or_add_item(item_id)
    if item.seen_this_frame:
        return item, just_created
    item.seen_this_frame = True
    idx = items.get_item_index(item)
    shown = I.split_label(label_id)
    if not has_flag(flags, I.ITEM_FLAGS_NO_LEGEND) and shown:
        items.legend.indices.append(idx)
        item.label = shown
    else:
        item.show = True
    return item, just_created


def get_item(label_id: str):
    """``GetItem``."""
    if gp.current_items is None:
        return None
    return gp.current_items.get_item(_item_id(label_id))


def is_item_hidden(label_id: str) -> bool:
    item = get_item(label_id)
    return item is not None and not item.show


def get_current_item():
    return gp.current_item


def bust_item_cache() -> None:
    """``BustItemCache``: forget every item of every plot."""
    for plot in I.pools()["plots"].values():
        plot.items.reset()
    for subplot in I.pools()["subplots"].values():
        subplot.items.reset()


def bust_color_cache(plot_title_id=None) -> None:
    """``BustColorCache``."""
    if plot_title_id is None:
        bust_item_cache()
        return
    ctx = _core.get_current_context()
    key = ctx.get_id(plot_title_id)
    plot = I.pools()["plots"].get(key)
    if plot is not None:
        plot.items.reset()
        return
    subplot = I.pools()["subplots"].get(key)
    if subplot is not None:
        subplot.items.reset()


def _next_marker() -> int:
    items = gp.current_items
    idx = items.marker_idx % I.MARKER_COUNT
    items.marker_idx += 1
    return idx


def begin_item(label_id: str, spec=None, item_col=None, item_mkr: int = I.MARKER_INVALID) -> bool:
    """``BeginItem``. Returns False when the item is hidden."""
    api = _api()
    if gp.current_plot is None:
        raise RuntimeError("PlotX() needs to be called between begin_plot() and end_plot()")
    api.setup_lock()
    spec = I.as_spec(spec) if not isinstance(spec, I.PlotSpec) else spec
    item, just_created = register_or_get_item(label_id, spec.flags)
    gp.current_item = item
    s = gp.next_item_data
    item_col = I.rgba(item_col)
    if item_col is not None:
        item.color = item_col
    elif just_created:
        item.color = I.next_colormap_color_u32()
    if s.has_hidden:
        if just_created or s.hidden_cond == I.COND_ALWAYS:
            item.show = not s.hidden
    if item_mkr != I.MARKER_INVALID:
        if item_mkr != I.MARKER_AUTO:
            item.marker = item_mkr
        elif just_created:
            item.marker = _next_marker()
        elif item.marker == I.MARKER_NONE:
            item.marker = _next_marker()
    if not item.show:
        s.reset()
        gp.previous_item = item
        gp.current_item = None
        return False
    color = item.color
    out = spec.copy()
    out.line_color = I.rgba(out.line_color) or color
    fill = I.rgba(out.fill_color) or color
    out.fill_color = (fill[0], fill[1], fill[2], int(fill[3] * max(0.0, min(1.0, out.fill_alpha))))
    out.marker = item.marker
    out.marker_line_color = I.rgba(out.marker_line_color) or out.line_color
    mfill = I.rgba(out.marker_fill_color) or out.line_color
    out.marker_fill_color = (mfill[0], mfill[1], mfill[2],
                             int(mfill[3] * max(0.0, min(1.0, out.fill_alpha))))
    if item.legend_hovered:
        if not has_flag(gp.current_items.legend.flags, I.LEGEND_FLAGS_NO_HIGHLIGHT_ITEM):
            out.line_weight *= ITEM_HIGHLIGHT_LINE_SCALE
            out.marker_size *= ITEM_HIGHLIGHT_MARK_SCALE
            out.size *= ITEM_HIGHLIGHT_MARK_SCALE
        if not has_flag(gp.current_items.legend.flags, I.LEGEND_FLAGS_NO_HIGHLIGHT_AXIS):
            plot = gp.current_plot
            if plot.enabled_axes_x() > 1:
                plot.axes[plot.current_x].color_hili = item.color
            if plot.enabled_axes_y() > 1:
                plot.axes[plot.current_y].color_hili = item.color
    s.spec = out
    s.render_line = out.line_color[3] > 0 and out.line_weight > 0
    s.render_fill = out.fill_color[3] > 0
    s.render_marker_line = out.marker_line_color[3] > 0 and out.line_weight > 0
    s.render_marker_fill = out.marker_fill_color[3] > 0
    s.render_markers = out.marker >= 0 and (s.render_marker_fill or s.render_marker_line)
    return True


def begin_item_ex(label_id: str, fitter, spec, item_col=None, item_mkr: int = I.MARKER_INVALID) -> bool:
    """``BeginItemEx``: ``BeginItem`` plus the fit, when this frame fits."""
    if begin_item(label_id, spec, item_col, item_mkr):
        plot = gp.current_plot
        if plot.fit_this_frame and not has_flag(spec.flags, I.ITEM_FLAGS_NO_FIT):
            fitter(plot.axes[plot.current_x], plot.axes[plot.current_y])
        return True
    return False


def end_item() -> None:
    """``EndItem``."""
    gp.next_item_data.reset()
    gp.previous_item = gp.current_item
    gp.current_item = None


def fit_this_frame() -> bool:
    return gp.current_plot.fit_this_frame


def fit_point_x(x: float) -> None:
    plot = gp.current_plot
    plot.axes[plot.current_x].extend_fit(x)


def fit_point_y(y: float) -> None:
    plot = gp.current_plot
    plot.axes[plot.current_y].extend_fit(y)


def fit_point(p) -> None:
    plot = gp.current_plot
    xa, ya = plot.axes[plot.current_x], plot.axes[plot.current_y]
    xa.extend_fit_with(ya, p[0], p[1])
    ya.extend_fit_with(xa, p[1], p[0])


def _fitter1(points):
    def fit(xa, ya):
        for x, y in points:
            xa.extend_fit_with(ya, x, y)
            ya.extend_fit_with(xa, y, x)
    return fit


def _fitter2(points1, points2):
    def fit(xa, ya):
        for pts in (points1, points2):
            for x, y in pts:
                xa.extend_fit_with(ya, x, y)
                ya.extend_fit_with(xa, y, x)
    return fit


def _fitter_rect(pmin, pmax):
    def fit(xa, ya):
        xa.extend_fit_with(ya, pmin[0], pmin[1])
        ya.extend_fit_with(xa, pmin[1], pmin[0])
        xa.extend_fit_with(ya, pmax[0], pmax[1])
        ya.extend_fit_with(xa, pmax[1], pmax[0])
    return fit


def _snapshot():
    """The item data a queued renderer needs: the spec and render flags."""
    s = gp.next_item_data
    snap = I.NextItemData()
    snap.spec = s.spec.copy()
    snap.render_line, snap.render_fill = s.render_line, s.render_fill
    snap.render_marker_line, snap.render_marker_fill = s.render_marker_line, s.render_marker_fill
    snap.render_markers = s.render_markers
    return snap


def _queue(render, expand: float = 0.0, clip: bool = True, record=None) -> None:
    """Queue a renderer on the current plot, on the current axes.

    *record* -- what was plotted, in plot units -- is kept on the plot for
    the frame (``Plot.records``): the reference has nothing to read back, but
    a test of what a call *plotted* should not have to scrape pixels for it.
    """
    plot = gp.current_plot
    plot.queue.append((plot.current_x, plot.current_y, render, expand, clip))
    if record is not None:
        plot.records.append(record)


# --------------------------------------------------------------------------- #
# [SECTION] Transformer and primitives
# --------------------------------------------------------------------------- #
def _transformer():
    """``Transformer2`` for the plot's current axes."""
    plot = gp.current_plot
    fx = plot.axes[plot.current_x].plot_to_pixels
    fy = plot.axes[plot.current_y].plot_to_pixels

    def t(x, y):
        return fx(x), fy(y)
    return t


def _cull_rect():
    return gp.current_plot.plot_rect


def _overlaps(cull, x0, y0, x1, y1) -> bool:
    """``ImRect::Overlaps`` against the segment's bounding box. NaNs never
    overlap, which is what makes a NaN sample a gap."""
    if x0 != x0 or x1 != x1 or y0 != y0 or y1 != y1:
        return False
    return (min(y0, y1) < cull[3] and max(y0, y1) > cull[1]
            and min(x0, x1) < cull[2] and max(x0, x1) > cull[0])


def _weight(w: float) -> float:
    return max(1.0, float(w))


def _render_line_strip(pts, col, colors, weight: float, skip_nan: bool, dash=None) -> None:
    """``RendererLineStrip``/``RendererLineStripSkip``."""
    if len(pts) < 2:
        return
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    w = _weight(weight)
    run = []
    phase = [0.0]

    def flush():
        if len(run) >= 2:
            if dash:
                for a, b in zip(run, run[1:]):
                    phase[0] = _dashed_segment(p, a, b, w, col, dash, phase[0])
            else:
                _polyline(p, run, w, col)
        run.clear()

    p1 = t(*pts[0])
    for prim in range(len(pts) - 1):
        p2 = t(*pts[prim + 1])
        nan2 = p2[0] != p2[0] or p2[1] != p2[1]
        if not _overlaps(cull, p1[0], p1[1], p2[0], p2[1]):
            flush()
            if not (skip_nan and nan2):
                p1 = p2
            continue
        if colors is not None:
            flush()
            _line(p, p1[0], p1[1], p2[0], p2[1], w, colors[prim])
        else:
            if not run:
                run.append(p1)
            run.append(p2)
        if not (skip_nan and nan2):
            p1 = p2
    flush()


def _dashed_segment(p, a, b, width, colour, dash, phase) -> float:
    """emtk's dashed line: ``a -> b`` as dashes, returning the phase at ``b``
    so the pattern runs on across vertices rather than restarting at each."""
    on, off = max(float(dash[0]), 0.5), max(float(dash[1]), 0.0)
    period = on + off
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length <= 0.0 or not math.isfinite(length):
        return phase
    ux, uy = dx / length, dy / length
    s = 0.0
    while s < length:
        pos = (phase + s) % period
        if pos < on:
            run = min(on - pos, length - s)
            _line(p, a[0] + ux * s, a[1] + uy * s, a[0] + ux * (s + run), a[1] + uy * (s + run),
                  width, colour)
        else:
            run = min(period - pos, length - s)
        s += run
    return (phase + length) % period


def _render_line_segments1(pts, col, colors, weight) -> None:
    """``RendererLineSegments1``: a segment from every two points."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    w = _weight(weight)
    for prim in range(len(pts) // 2):
        a = t(*pts[prim * 2])
        b = t(*pts[prim * 2 + 1])
        if not _overlaps(cull, a[0], a[1], b[0], b[1]):
            continue
        _line(p, a[0], a[1], b[0], b[1], w, colors[prim * 2] if colors is not None else col)


def _render_line_segments2(pts1, pts2, col, colors, weight) -> None:
    """``RendererLineSegments2``."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    w = _weight(weight)
    for prim in range(min(len(pts1), len(pts2))):
        a = t(*pts1[prim])
        b = t(*pts2[prim])
        if not _overlaps(cull, a[0], a[1], b[0], b[1]):
            continue
        _line(p, a[0], a[1], b[0], b[1], w, colors[prim] if colors is not None else col)


def _fill_rect_pts(p, a, b, col) -> None:
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    if x1 > x0 and y1 > y0:
        p.fill_rect(x0, y0, x1 - x0, y1 - y0, col)


def _render_bars(pts1, pts2, half, horizontal: bool, fill_col, fill_colors, line_col,
                 line_colors, weight, rend_fill: bool, rend_line: bool) -> None:
    """``RendererBarsFillV/H`` and ``RendererBarsLineV/H``."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    for prim in range(min(len(pts1), len(pts2))):
        (x1, y1), (x2, y2) = pts1[prim], pts2[prim]
        if horizontal:
            y1 += half
            y2 -= half
        else:
            x1 += half
            x2 -= half
        P1 = list(t(x1, y1))
        P2 = list(t(x2, y2))
        k = 1 if horizontal else 0
        size_px = abs(P1[k] - P2[k])
        if size_px < 1.0:
            P1[k] += (1 - size_px) / 2 if P1[k] > P2[k] else (size_px - 1) / 2
            P2[k] += (1 - size_px) / 2 if P2[k] > P1[k] else (size_px - 1) / 2
        xmin, xmax = min(P1[0], P2[0]), max(P1[0], P2[0])
        ymin, ymax = min(P1[1], P2[1]), max(P1[1], P2[1])
        if not (ymin < cull[3] and ymax > cull[1] and xmin < cull[2] and xmax > cull[0]):
            continue
        if xmin != xmin or ymin != ymin:
            continue
        if rend_fill:
            c = fill_colors[prim] if fill_colors is not None else fill_col
            p.fill_rect(xmin, ymin, xmax - xmin, ymax - ymin, c)
        if rend_line:
            c = line_colors[prim] if line_colors is not None else line_col
            _rect_line(p, xmin, ymin, xmax, ymax, weight, c)


def _rect_line(p, x0, y0, x1, y1, weight, col) -> None:
    """``PrimRectLine``: a rectangle outline *inside* the rect, ``weight`` thick."""
    w = max(float(weight), 0.0)
    if w <= 0:
        return
    if x1 - x0 <= 2 * w or y1 - y0 <= 2 * w:
        p.fill_rect(x0, y0, x1 - x0, y1 - y0, col)
        return
    p.fill_rect(x0, y0, x1 - x0, w, col)
    p.fill_rect(x0, y1 - w, x1 - x0, w, col)
    p.fill_rect(x0, y0 + w, w, y1 - y0 - 2 * w, col)
    p.fill_rect(x1 - w, y0 + w, w, y1 - y0 - 2 * w, col)


def _render_stairs(pts, pre: bool, col, colors, weight) -> None:
    """``RendererStairsPre``/``RendererStairsPost``."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    hw = _weight(weight) * 0.5
    P1 = t(*pts[0])
    for prim in range(len(pts) - 1):
        P2 = t(*pts[prim + 1])
        if not _overlaps(cull, P1[0], P1[1], P2[0], P2[1]):
            P1 = P2
            continue
        c = colors[prim] if colors is not None else col
        if pre:
            _fill_rect_pts(p, (P1[0] - hw, P1[1]), (P1[0] + hw, P2[1]), c)
            _fill_rect_pts(p, (P1[0], P2[1] + hw), (P2[0], P2[1] - hw), c)
        else:
            _fill_rect_pts(p, (P1[0], P1[1] + hw), (P2[0], P1[1] - hw), c)
            _fill_rect_pts(p, (P2[0] - hw, P2[1]), (P2[0] + hw, P1[1]), c)
        P1 = P2


def _render_stairs_shaded(pts, pre: bool, col, colors) -> None:
    """``RendererStairsPreShaded``/``RendererStairsPostShaded``."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    P1 = t(*pts[0])
    Y0 = t(0.0, 0.0)[1]
    for prim in range(len(pts) - 1):
        P2 = t(*pts[prim + 1])
        if pre:
            pmin = (min(P1[0], P2[0]), min(Y0, P2[1]))
            pmax = (max(P1[0], P2[0]), max(Y0, P2[1]))
        else:
            pmin = (min(P1[0], P2[0]), min(P1[1], Y0))
            pmax = (max(P1[0], P2[0]), max(P1[1], Y0))
        if not (pmin[1] < cull[3] and pmax[1] > cull[1] and pmin[0] < cull[2] and pmax[0] > cull[0]):
            P1 = P2
            continue
        _fill_rect_pts(p, pmin, pmax, colors[prim] if colors is not None else col)
        P1 = P2


def _render_shaded(pts1, pts2, col, colors) -> None:
    """``RendererShaded``: the band between two polylines, crossing handled."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    n = min(len(pts1), len(pts2))
    if n < 2:
        return
    P11 = t(*pts1[0])
    P12 = t(*pts2[0])
    for prim in range(n - 1):
        P21 = t(*pts1[prim + 1])
        P22 = t(*pts2[prim + 1])
        xs = (P11[0], P12[0], P21[0], P22[0])
        ys = (P11[1], P12[1], P21[1], P22[1])
        if not (min(ys) < cull[3] and max(ys) > cull[1] and min(xs) < cull[2] and max(xs) > cull[0]):
            P11, P12 = P21, P22
            continue
        c = colors[prim] if colors is not None else col
        intersect = (P11[1] > P12[1] and P22[1] > P21[1]) or (P12[1] > P11[1] and P21[1] > P22[1])
        if intersect:
            X = I.intersection(P11, P21, P12, P22)
            p.fill_triangle(P11, X, P12, c)
            p.fill_triangle(X, P21, P22, c)
        else:
            p.fill_triangle(P11, P21, P12, c)
            p.fill_triangle(P21, P22, P12, c)
        P11, P12 = P21, P22


# --------------------------------------------------------------------------- #
# [SECTION] Markers
# --------------------------------------------------------------------------- #
_MARKER_FILL = {
    I.MARKER_CIRCLE: [(1.0, 0.0), (0.809017, 0.58778524), (0.30901697, 0.95105654), (-0.30901703, 0.9510565),
                      (-0.80901706, 0.5877852), (-1.0, 0.0), (-0.80901694, -0.58778536),
                      (-0.3090171, -0.9510565), (0.30901712, -0.9510565), (0.80901694, -0.5877853)],
    I.MARKER_SQUARE: [(SQRT_1_2, SQRT_1_2), (SQRT_1_2, -SQRT_1_2), (-SQRT_1_2, -SQRT_1_2), (-SQRT_1_2, SQRT_1_2)],
    I.MARKER_DIAMOND: [(1, 0), (0, -1), (-1, 0), (0, 1)],
    I.MARKER_UP: [(SQRT_3_2, 0.5), (0, -1), (-SQRT_3_2, 0.5)],
    I.MARKER_DOWN: [(SQRT_3_2, -0.5), (0, 1), (-SQRT_3_2, -0.5)],
    I.MARKER_LEFT: [(-1, 0), (0.5, SQRT_3_2), (0.5, -SQRT_3_2)],
    I.MARKER_RIGHT: [(1, 0), (-0.5, SQRT_3_2), (-0.5, -SQRT_3_2)],
}


def _closed(pts):
    out = []
    for i in range(len(pts)):
        out.append(pts[i])
        out.append(pts[(i + 1) % len(pts)])
    return out


_MARKER_LINE = {
    I.MARKER_CIRCLE: _closed(_MARKER_FILL[I.MARKER_CIRCLE]),
    I.MARKER_SQUARE: _closed(_MARKER_FILL[I.MARKER_SQUARE]),
    I.MARKER_DIAMOND: _closed(_MARKER_FILL[I.MARKER_DIAMOND]),
    I.MARKER_UP: _closed(_MARKER_FILL[I.MARKER_UP]),
    I.MARKER_DOWN: _closed(_MARKER_FILL[I.MARKER_DOWN]),
    I.MARKER_LEFT: _closed(_MARKER_FILL[I.MARKER_LEFT]),
    I.MARKER_RIGHT: _closed(_MARKER_FILL[I.MARKER_RIGHT]),
    I.MARKER_ASTERISK: [(-SQRT_3_2, -0.5), (SQRT_3_2, 0.5), (-SQRT_3_2, 0.5), (SQRT_3_2, -0.5), (0, -1), (0, 1)],
    I.MARKER_PLUS: [(-1, 0), (1, 0), (0, -1), (0, 1)],
    I.MARKER_CROSS: [(-SQRT_1_2, -SQRT_1_2), (SQRT_1_2, SQRT_1_2), (SQRT_1_2, -SQRT_1_2), (-SQRT_1_2, SQRT_1_2)],
    I.MARKER_VERTICAL: [(0, -1), (0, 1)],
    I.MARKER_HORIZONTAL: [(-1, 0), (1, 0)],
}


def render_markers(pts, marker: int, rend_fill: bool, fill, rend_line: bool, line, size,
                   weight: float) -> None:
    """``RenderMarkers``. *fill*/*line* are a colour or a per-point list;
    *size* is a radius or a per-point list."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    fill_shape = _MARKER_FILL.get(marker) if rend_fill else None
    line_shape = _MARKER_LINE.get(marker) if rend_line else None
    if fill_shape is None and line_shape is None:
        return
    fill_list = isinstance(fill, list)
    line_list = isinstance(line, list)
    size_list = isinstance(size, (list, tuple))
    hw = _weight(weight)
    for i, (x, y) in enumerate(pts):
        px, py = t(x, y)
        if not (px >= cull[0] and py >= cull[1] and px <= cull[2] and py <= cull[3]):
            continue
        r = float(size[i]) if size_list else float(size)
        if fill_shape is not None:
            _fill_convex(p, [(px + mx * r, py + my * r) for mx, my in fill_shape],
                         fill[i] if fill_list else fill)
        if line_shape is not None:
            c = line[i] if line_list else line
            for k in range(0, len(line_shape), 2):
                ax, ay = line_shape[k]
                bx, by = line_shape[k + 1]
                _line(p, px + ax * r, py + ay * r, px + bx * r, py + by * r, hw, c)


def _render_colored_markers(pts, s) -> None:
    """``RenderColoredMarkers``."""
    spec = s.spec
    n = len(pts)
    size = [float(v) for v in spec.marker_sizes[:n]] if spec.marker_sizes is not None else spec.marker_size
    fill = _colors(spec.marker_fill_colors, n, spec.fill_alpha) if spec.marker_fill_colors is not None \
        else spec.marker_fill_color
    line = _colors(spec.marker_line_colors, n) if spec.marker_line_colors is not None \
        else spec.marker_line_color
    render_markers(pts, spec.marker, s.render_marker_fill, fill, s.render_marker_line, line, size,
                   spec.line_weight)


# --------------------------------------------------------------------------- #
# Overload dispatch
# --------------------------------------------------------------------------- #
def _tail(args, slots, kw, defaults):
    """Bind a positional tail onto named slots, keywords winning."""
    out = dict(defaults)
    for name, value in zip(slots, args):
        out[name] = value
    for name in slots:
        if name in kw:
            out[name] = kw.pop(name)
    return out


def _spec_from(tail: dict, kw: dict) -> I.PlotSpec:
    """The item's spec: ``spec=``, then a ``flags=`` shorthand, then the
    obsolete ``SetNext*Style`` values emtk still honours."""
    spec = I.as_spec(tail.get("spec"))
    flags = kw.pop("flags", tail.get("flags"))
    if flags is not None:
        spec.flags = int(spec.flags) | int(flags)
    for key in list(kw):
        if hasattr(spec, key):
            setattr(spec, key, kw.pop(key))
    if kw:
        raise TypeError(f"unexpected arguments: {sorted(kw)}")
    _api()._apply_legacy_styles(spec)
    return spec


def _xy_or_values(label_id, xs, ys, args, kw, values_slots, xy_slots, values_defaults, xy_defaults):
    """Tell ``(label, values, count, ...)`` from ``(label, xs, ys, count, ...)``."""
    if ys is not None and _is_series(ys):
        tail = _tail(args, xy_slots, kw, xy_defaults)
        return False, tail
    if ys is not None:
        args = (ys,) + tuple(args)
    tail = _tail(args, values_slots, kw, values_defaults)
    return True, tail


# --------------------------------------------------------------------------- #
# [SECTION] PlotLine
# --------------------------------------------------------------------------- #
def _plot_line_ex(label_id, pts, spec) -> None:
    if begin_item_ex(label_id, _fitter1(pts), spec, spec.line_color, spec.marker):
        if len(pts) <= 0:
            end_item()
            return
        s = _snapshot()
        flags = spec.flags

        def render():
            sp = s.spec
            if len(pts) > 1:
                if has_flag(flags, I.LINE_FLAGS_SHADED) and s.render_fill:
                    pts2 = [(x, 0.0) for x, _y in pts]
                    fills = _colors(sp.fill_colors, len(pts), sp.fill_alpha)
                    _render_shaded(pts, pts2, sp.fill_color, fills)
                if s.render_line:
                    colors = _colors(sp.line_colors, len(pts))
                    if has_flag(flags, I.LINE_FLAGS_SEGMENTS):
                        _render_line_segments1(pts, sp.line_color, colors, sp.line_weight)
                    elif has_flag(flags, I.LINE_FLAGS_LOOP):
                        loop = pts + [pts[0]]
                        loop_colors = colors + [colors[0]] if colors is not None else None
                        _render_line_strip(loop, sp.line_color, loop_colors, sp.line_weight,
                                           has_flag(flags, I.LINE_FLAGS_SKIP_NAN), sp.dash)
                    else:
                        _render_line_strip(pts, sp.line_color, colors, sp.line_weight,
                                           has_flag(flags, I.LINE_FLAGS_SKIP_NAN), sp.dash)
            if s.render_markers:
                _render_colored_markers(pts, s)

        expand = s.spec.marker_size if (s.render_markers and has_flag(flags, I.LINE_FLAGS_NO_CLIP)) else 0.0
        _queue(render, expand, record={"kind": "line", "label": label_id, "pts": pts, "spec": s.spec})
        end_item()


def plot_line(label_id: str, xs, ys=None, *args, **kw) -> None:
    """``PlotLine``, both overloads::

        plot_line(label, values, count=None, xscale=1, xstart=0, spec=None)
        plot_line(label, xs, ys, count=None, spec=None)

    ``ys=None`` (or a number where the ys would be) is the values overload,
    as the C++ types tell them apart.
    """
    values, tail = _xy_or_values(label_id, xs, ys, args, kw,
                                 ("count", "xscale", "xstart", "spec"), ("count", "spec"),
                                 {"count": None, "xscale": 1.0, "xstart": 0.0, "spec": None},
                                 {"count": None, "spec": None})
    spec = _spec_from(tail, kw)
    count = tail["count"]
    if values:
        ys_ = _values(xs, count, spec.offset, spec.stride)
        pts = list(zip(_lin(len(ys_), float(tail["xscale"]), float(tail["xstart"])), ys_))
    else:
        xs_ = _values(xs, count, spec.offset, spec.stride)
        ys_ = _values(ys, count, spec.offset, spec.stride)
        pts = list(zip(xs_, ys_))
    _plot_line_ex(label_id, pts, spec)


def plot_line_g(label_id: str, getter, data, count: int, spec=None, **kw) -> None:
    """``PlotLineG``: ``getter(idx, data) -> (x, y)``."""
    spec = _spec_from({"spec": spec}, kw)
    _plot_line_ex(label_id, _getter_points(getter, data, count), spec)


# --------------------------------------------------------------------------- #
# [SECTION] PlotScatter
# --------------------------------------------------------------------------- #
def _plot_scatter_ex(label_id, pts, spec) -> None:
    marker = I.MARKER_AUTO if spec.marker == I.MARKER_NONE else spec.marker
    if begin_item_ex(label_id, _fitter1(pts), spec, spec.marker_line_color, marker):
        if len(pts) <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            if s.render_markers:
                _render_colored_markers(pts, s)

        expand = s.spec.marker_size if has_flag(spec.flags, I.SCATTER_FLAGS_NO_CLIP) else 0.0
        _queue(render, expand, record={"kind": "scatter", "label": label_id, "pts": pts, "spec": s.spec})
        end_item()


def plot_scatter(label_id: str, xs, ys=None, *args, **kw) -> None:
    """``PlotScatter``, both overloads (see :func:`plot_line`)."""
    values, tail = _xy_or_values(label_id, xs, ys, args, kw,
                                 ("count", "xscale", "xstart", "spec"), ("count", "spec"),
                                 {"count": None, "xscale": 1.0, "xstart": 0.0, "spec": None},
                                 {"count": None, "spec": None})
    spec = _spec_from(tail, kw)
    count = tail["count"]
    if values:
        ys_ = _values(xs, count, spec.offset, spec.stride)
        pts = list(zip(_lin(len(ys_), float(tail["xscale"]), float(tail["xstart"])), ys_))
    else:
        pts = list(zip(_values(xs, count, spec.offset, spec.stride),
                       _values(ys, count, spec.offset, spec.stride)))
    _plot_scatter_ex(label_id, pts, spec)


def plot_scatter_g(label_id: str, getter, data, count: int, spec=None, **kw) -> None:
    spec = _spec_from({"spec": spec}, kw)
    _plot_scatter_ex(label_id, _getter_points(getter, data, count), spec)


# --------------------------------------------------------------------------- #
# [SECTION] PlotBubbles
# --------------------------------------------------------------------------- #
def plot_bubbles(label_id: str, xs, ys, szs=None, *args, **kw) -> None:
    """``PlotBubbles``::

        plot_bubbles(label, values, szs, count=None, xscale=1, xstart=0, spec=None)
        plot_bubbles(label, xs, ys, szs, count=None, spec=None)

    ``szs`` are radii in plot units.
    """
    if szs is not None and _is_series(szs):
        tail = _tail(args, ("count", "spec"), kw, {"count": None, "spec": None})
        spec = _spec_from(tail, kw)
        count = tail["count"]
        xs_ = _values(xs, count, spec.offset, spec.stride)
        ys_ = _values(ys, count, spec.offset, spec.stride)
        ss = _values(szs, count, spec.offset, spec.stride)
    else:
        args = ((szs,) if szs is not None else ()) + tuple(args)
        tail = _tail(args, ("count", "xscale", "xstart", "spec"), kw,
                     {"count": None, "xscale": 1.0, "xstart": 0.0, "spec": None})
        spec = _spec_from(tail, kw)
        count = tail["count"]
        ys_ = _values(xs, count, spec.offset, spec.stride)
        ss = _values(ys, count, spec.offset, spec.stride)
        xs_ = _lin(len(ys_), float(tail["xscale"]), float(tail["xstart"]))
    n = min(len(xs_), len(ys_), len(ss))
    pts3 = [(xs_[i], ys_[i], ss[i]) for i in range(n)]

    def fitter(xa, ya):
        for x, y, r in pts3:
            xa.extend_fit_with(ya, x - r, y)
            xa.extend_fit_with(ya, x + r, y)
            ya.extend_fit_with(xa, y - r, x)
            ya.extend_fit_with(xa, y + r, x)

    if begin_item_ex(label_id, fitter, spec, spec.fill_color, spec.marker):
        if n <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            sp = s.spec
            p = _dl().p
            plot = gp.current_plot
            t = _transformer()
            cull = _cull_rect()
            mx = abs(plot.axes[plot.current_x].scale_to_pixel)
            fills = _colors(sp.fill_colors, n, sp.fill_alpha)
            lines = _colors(sp.line_colors, n)
            for i, (x, y, r) in enumerate(pts3):
                segs = min(max(int(abs(r * mx)), 10), 64)
                a, b = t(x - r, y - r), t(x + r, y + r)
                if not (min(a[1], b[1]) < cull[3] and max(a[1], b[1]) > cull[1]
                        and min(a[0], b[0]) < cull[2] and max(a[0], b[0]) > cull[0]):
                    continue
                ring = [t(x + math.cos(2 * math.pi * k / segs) * r, y + math.sin(2 * math.pi * k / segs) * r)
                        for k in range(segs)]
                if s.render_fill:
                    _fill_convex(p, ring, fills[i] if fills is not None else sp.fill_color)
                if s.render_line:
                    c = lines[i] if lines is not None else sp.line_color
                    _polyline(p, ring, _weight(sp.line_weight), c, closed=True)

        _queue(render)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotPolygon
# --------------------------------------------------------------------------- #
def plot_polygon(label_id: str, xs, ys, count=None, spec=None, **kw) -> None:
    """``PlotPolygon``: counter-clockwise points; ``POLYGON_FLAGS_CONCAVE`` for
    concave shapes."""
    spec = _spec_from({"spec": spec}, kw)
    pts = list(zip(_values(xs, count, spec.offset, spec.stride),
                   _values(ys, count, spec.offset, spec.stride)))
    if begin_item_ex(label_id, _fitter1(pts), spec, spec.fill_color, spec.marker):
        if len(pts) < 2:
            end_item()
            return
        s = _snapshot()
        concave = has_flag(spec.flags, I.POLYGON_FLAGS_CONCAVE)

        def render():
            sp = s.spec
            plot = gp.current_plot
            xa, ya = plot.axes[plot.current_x], plot.axes[plot.current_y]
            t = _transformer()
            flip = not (xa.is_inverted() ^ ya.is_inverted())
            ordered = list(reversed(pts)) if flip else pts
            points = [t(x, y) for x, y in ordered]
            dl = _dl()
            if s.render_fill and len(points) >= 3:
                if concave:
                    dl.add_concave_poly_filled(points, sp.fill_color)
                else:
                    dl.add_convex_poly_filled(points, sp.fill_color)
            if s.render_line and len(points) >= 2:
                _polyline(dl.p, points, _weight(sp.line_weight), sp.line_color, closed=True)

        _queue(render)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotStairs
# --------------------------------------------------------------------------- #
def _plot_stairs_ex(label_id, pts, spec) -> None:
    if begin_item_ex(label_id, _fitter1(pts), spec, spec.line_color, spec.marker):
        if len(pts) <= 0:
            end_item()
            return
        s = _snapshot()
        flags = spec.flags

        def render():
            sp = s.spec
            pre = has_flag(flags, I.STAIRS_FLAGS_PRE_STEP)
            if len(pts) > 1:
                if s.render_fill and has_flag(flags, I.STAIRS_FLAGS_SHADED):
                    fills = _colors(sp.fill_colors, len(pts), sp.fill_alpha)
                    _render_stairs_shaded(pts, pre, _const(sp.fill_color, 1.0), fills)
                if s.render_line:
                    _render_stairs(pts, pre, sp.line_color, _colors(sp.line_colors, len(pts)),
                                   sp.line_weight)
            if s.render_markers:
                _render_colored_markers(pts, s)

        _queue(render, s.spec.marker_size if s.render_markers else 0.0)
        end_item()


def plot_stairs(label_id: str, xs, ys=None, *args, **kw) -> None:
    """``PlotStairs``, both overloads (see :func:`plot_line`)."""
    values, tail = _xy_or_values(label_id, xs, ys, args, kw,
                                 ("count", "xscale", "xstart", "spec"), ("count", "spec"),
                                 {"count": None, "xscale": 1.0, "xstart": 0.0, "spec": None},
                                 {"count": None, "spec": None})
    spec = _spec_from(tail, kw)
    count = tail["count"]
    if values:
        ys_ = _values(xs, count, spec.offset, spec.stride)
        pts = list(zip(_lin(len(ys_), float(tail["xscale"]), float(tail["xstart"])), ys_))
    else:
        pts = list(zip(_values(xs, count, spec.offset, spec.stride),
                       _values(ys, count, spec.offset, spec.stride)))
    _plot_stairs_ex(label_id, pts, spec)


def plot_stairs_g(label_id: str, getter, data, count: int, spec=None, **kw) -> None:
    spec = _spec_from({"spec": spec}, kw)
    _plot_stairs_ex(label_id, _getter_points(getter, data, count), spec)


# --------------------------------------------------------------------------- #
# [SECTION] PlotShaded
# --------------------------------------------------------------------------- #
def _plot_shaded_ex(label_id, pts1, pts2_fn, spec, fit_pts2=None) -> None:
    """*pts2_fn* is called at draw time: a reference of ``+/-inf`` is the plot
    limits, and emtk knows those only once the plot is fit."""
    fit2 = fit_pts2 if fit_pts2 is not None else []
    if begin_item_ex(label_id, _fitter2(pts1, fit2), spec, spec.fill_color):
        if len(pts1) <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            if s.render_fill:
                sp = s.spec
                fills = _colors(sp.fill_colors, len(pts1), sp.fill_alpha)
                _render_shaded(pts1, pts2_fn(), sp.fill_color, fills)

        _queue(render)
        end_item()


def _ref_points(xs, yref):
    def pts():
        ref = yref
        if ref == -math.inf or ref == math.inf:
            plot = gp.current_plot
            ya = plot.axes[plot.current_y]
            ref = ya.range_min if ref == -math.inf else ya.range_max
        return [(x, ref) for x in xs]
    return pts


def plot_shaded(label_id: str, xs, ys=None, *args, **kw) -> None:
    """``PlotShaded``, all three overloads::

        plot_shaded(label, values, count=None, yref=0, xscale=1, xstart=0, spec=None)
        plot_shaded(label, xs, ys, count=None, yref=0, spec=None)
        plot_shaded(label, xs, ys1, ys2, count=None, spec=None)

    ``yref`` of ``+/-inf`` shades to the edge of the plot.
    """
    args = list(args)
    if ys is not None and _is_series(ys):
        if (args and _is_series(args[0])) or _is_series(kw.get("ys2")):
            ys2 = args.pop(0) if args and _is_series(args[0]) else kw.pop("ys2")
            tail = _tail(args, ("count", "spec"), kw, {"count": None, "spec": None})
            spec = _spec_from(tail, kw)
            count = tail["count"]
            xs_ = _values(xs, count, spec.offset, spec.stride)
            pts1 = list(zip(xs_, _values(ys, count, spec.offset, spec.stride)))
            pts2 = list(zip(xs_, _values(ys2, count, spec.offset, spec.stride)))
            _plot_shaded_ex(label_id, pts1, lambda: pts2, spec, pts2)
            return
        kw.pop("ys2", None)
        tail = _tail(args, ("count", "yref", "spec"), kw, {"count": None, "yref": 0.0, "spec": None})
        spec = _spec_from(tail, kw)
        count = tail["count"]
        xs_ = _values(xs, count, spec.offset, spec.stride)
        pts1 = list(zip(xs_, _values(ys, count, spec.offset, spec.stride)))
        yref = float(tail["yref"])
    else:
        if ys is not None:
            args.insert(0, ys)
        tail = _tail(args, ("count", "yref", "xscale", "xstart", "spec"), kw,
                     {"count": None, "yref": 0.0, "xscale": 1.0, "xstart": 0.0, "spec": None})
        spec = _spec_from(tail, kw)
        count = tail["count"]
        ys_ = _values(xs, count, spec.offset, spec.stride)
        xs_ = _lin(len(ys_), float(tail["xscale"]), float(tail["xstart"]))
        pts1 = list(zip(xs_, ys_))
        yref = float(tail["yref"])
    fit2 = [] if math.isinf(yref) else [(x, yref) for x in xs_]
    _plot_shaded_ex(label_id, pts1, _ref_points(xs_, yref), spec, fit2)


def plot_shaded_g(label_id: str, getter1, data1, getter2, data2, count: int, spec=None, **kw) -> None:
    spec = _spec_from({"spec": spec}, kw)
    pts1 = _getter_points(getter1, data1, count)
    pts2 = _getter_points(getter2, data2, count)
    _plot_shaded_ex(label_id, pts1, lambda: pts2, spec, pts2)


# --------------------------------------------------------------------------- #
# [SECTION] PlotBars
# --------------------------------------------------------------------------- #
def _plot_bars_ex(label_id, pts1, pts2, size, horizontal, spec) -> None:
    half = size * 0.5

    def fitter(xa, ya):
        for i in range(min(len(pts1), len(pts2))):
            (x1, y1), (x2, y2) = pts1[i], pts2[i]
            if horizontal:
                y1 -= half
                y2 += half
            else:
                x1 -= half
                x2 += half
            xa.extend_fit_with(ya, x1, y1)
            ya.extend_fit_with(xa, y1, x1)
            xa.extend_fit_with(ya, x2, y2)
            ya.extend_fit_with(xa, y2, x2)

    if begin_item_ex(label_id, fitter, spec, spec.fill_color):
        if len(pts1) <= 0 or len(pts2) <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            sp = s.spec
            n = len(pts1)
            fills = _colors(sp.fill_colors, n, sp.fill_alpha)
            lines = _colors(sp.line_colors, n)
            rend_line = s.render_line
            fill_col = _const(sp.fill_color, 1.0)
            if s.render_fill and rend_line and fill_col == sp.line_color and fills is None and lines is None:
                rend_line = False
            _render_bars(pts1, pts2, half, horizontal, fill_col, fills, sp.line_color, lines,
                         sp.line_weight, s.render_fill, rend_line)

        _queue(render, record={"kind": "bars", "label": label_id, "pts1": pts1, "pts2": pts2,
                               "size": size, "horizontal": horizontal, "spec": s.spec})
        end_item()


def plot_bars(label_id: str, xs, *args, ys=None, count=None, bar_size=None, shift=None,
              flags=None, spec=None, **kw) -> None:
    """Bars, in either of the reference's two overloads::

        plot_bars(label, values, count=None, bar_size=0.67, shift=0, spec=None)
        plot_bars(label, xs, ys, count=None, bar_size=0.67, spec=None)

    ``count`` comes *before* the sizing argument in both, so a positional port
    is told apart the way C++ tells it apart: by whether the third argument is
    an array or a number. An ``int`` flags value in the ``spec`` slot is taken
    as flags, as the obsolete ``flags`` argument was.
    """
    rest = list(args)
    if ys is None and rest and _is_series(rest[0]):
        ys = rest.pop(0)
    slots = ("count", "bar_size", "spec") if ys is not None else ("count", "bar_size", "shift", "spec")
    tail = dict(zip(slots, rest))
    count = tail.get("count", count)
    bar_size = tail.get("bar_size", bar_size)
    shift = tail.get("shift", shift)
    spec_arg = tail.get("spec", spec)
    if isinstance(spec_arg, int):
        flags = int(spec_arg) | int(flags or 0)
        spec_arg = spec
    bar_size = 0.67 if bar_size is None else float(bar_size)
    shift = 0.0 if shift is None else float(shift)
    spec = _spec_from({"spec": spec_arg, "flags": flags}, kw)
    horizontal = has_flag(spec.flags, I.BARS_FLAGS_HORIZONTAL)
    if ys is None:
        vals = _values(xs, count, spec.offset, spec.stride)
        pos = _lin(len(vals), 1.0, shift)
        if horizontal:
            pts1 = list(zip(vals, pos))
            pts2 = [(0.0, y) for y in pos]
        else:
            pts1 = list(zip(pos, vals))
            pts2 = [(x, 0.0) for x in pos]
    else:
        xs_ = _values(xs, count, spec.offset, spec.stride)
        ys_ = _values(ys, count, spec.offset, spec.stride)
        if shift:
            # the reference's xy overload has no shift; emtk's keyword one did
            if horizontal:
                ys_ = [y + shift for y in ys_]
            else:
                xs_ = [x + shift for x in xs_]
        pts1 = list(zip(xs_, ys_))
        pts2 = [(0.0, y) for y in ys_] if horizontal else [(x, 0.0) for x in xs_]
    _plot_bars_ex(label_id, pts1, pts2, bar_size, horizontal, spec)


def plot_bars_g(label_id: str, getter, data, count: int, bar_size: float, spec=None, **kw) -> None:
    spec = _spec_from({"spec": spec}, kw)
    pts1 = _getter_points(getter, data, count)
    horizontal = has_flag(spec.flags, I.BARS_FLAGS_HORIZONTAL)
    pts2 = [(0.0, y) for _x, y in pts1] if horizontal else [(x, 0.0) for x, _y in pts1]
    _plot_bars_ex(label_id, pts1, pts2, float(bar_size), horizontal, spec)


# --------------------------------------------------------------------------- #
# [SECTION] PlotBarGroups
# --------------------------------------------------------------------------- #
def plot_bar_groups(label_ids, values, item_count: int, group_count: int, group_size: float = 0.67,
                    shift: float = 0.0, spec=None, **kw) -> None:
    """``PlotBarGroups``: *values* is row-major, ``item_count`` rows by
    ``group_count`` columns (a list of rows works too)."""
    spec = _spec_from({"spec": spec}, kw)
    flat = [float(v) for row in values for v in row] if (len(values) and _is_series(values[0])) \
        else _values(values, item_count * group_count, spec.offset, spec.stride)
    horz = has_flag(spec.flags, I.BAR_GROUPS_FLAGS_HORIZONTAL)
    stack = has_flag(spec.flags, I.BAR_GROUPS_FLAGS_STACKED)
    spec_bars = spec.copy()
    spec_bars.flags = 0
    spec_bars.offset = 0
    spec_bars.stride = I.IMPLOT_AUTO
    if stack:
        _api().setup_lock()
        neg = [0.0] * group_count
        pos = [0.0] * group_count
        curr_min = [0.0] * group_count
        curr_max = [0.0] * group_count
        for i in range(item_count):
            if not is_item_hidden(label_ids[i]):
                for g in range(group_count):
                    v = flat[i * group_count + g]
                    if v > 0:
                        curr_min[g] = pos[g]
                        curr_max[g] = curr_min[g] + v
                        pos[g] += v
                    else:
                        curr_max[g] = neg[g]
                        curr_min[g] = curr_max[g] + v
                        neg[g] += v
            lin = _lin(group_count, 1.0, shift)
            if horz:
                pts1 = list(zip(list(curr_min), lin))
                pts2 = list(zip(list(curr_max), lin))
            else:
                pts1 = list(zip(lin, list(curr_min)))
                pts2 = list(zip(lin, list(curr_max)))
            _plot_bars_ex(label_ids[i], pts1, pts2, group_size, horz, spec_bars.copy())
    else:
        subsize = group_size / item_count
        for i in range(item_count):
            subshift = (i + 0.5) * subsize - group_size / 2
            row = flat[i * group_count:(i + 1) * group_count]
            sb = spec_bars.copy()
            if horz:
                sb.flags = I.BARS_FLAGS_HORIZONTAL
            plot_bars(label_ids[i], row, group_count, subsize, subshift + shift, spec=sb)


# --------------------------------------------------------------------------- #
# [SECTION] PlotErrorBars
# --------------------------------------------------------------------------- #
def plot_error_bars(label_id: str, xs, ys, err, *args, **kw) -> None:
    """``PlotErrorBars``::

        plot_error_bars(label, xs, ys, err, count=None, spec=None)
        plot_error_bars(label, xs, ys, neg, pos, count=None, spec=None)

    ``ERROR_BARS_FLAGS_HORIZONTAL`` puts them along x.
    """
    args = list(args)
    if args and _is_series(args[0]):
        pos = args.pop(0)
        neg = err
    else:
        neg = pos = err
    tail = _tail(args, ("count", "spec"), kw, {"count": None, "spec": None})
    spec = _spec_from(tail, kw)
    count = tail["count"]
    xs_ = _values(xs, count, spec.offset, spec.stride)
    ys_ = _values(ys, count, spec.offset, spec.stride)
    ns = _values(neg, count, spec.offset, spec.stride)
    ps = _values(pos, count, spec.offset, spec.stride)
    n = min(len(xs_), len(ys_), len(ns), len(ps))
    horizontal = has_flag(spec.flags, I.ERROR_BARS_FLAGS_HORIZONTAL)
    if horizontal:
        p_pos = [(xs_[i] + ps[i], ys_[i]) for i in range(n)]
        p_neg = [(xs_[i] - ns[i], ys_[i]) for i in range(n)]
    else:
        p_pos = [(xs_[i], ys_[i] + ps[i]) for i in range(n)]
        p_neg = [(xs_[i], ys_[i] - ns[i]) for i in range(n)]
    auto_line = spec.line_color is None
    if begin_item_ex(label_id, _fitter2(p_pos, p_neg), spec, None):
        if n <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            sp = s.spec
            p = _dl().p
            t = _transformer()
            col = I.rgba(_core.get_current_context().style.color(_core.Col.TEXT)) if auto_line \
                else sp.line_color
            half = sp.size * 0.5
            rend_whisker = sp.size > 0
            w = sp.line_weight
            for i in range(n):
                p1 = t(*p_neg[i])
                p2 = t(*p_pos[i])
                _line(p, p1[0], p1[1], p2[0], p2[1], w, col)
                if rend_whisker:
                    if horizontal:
                        p.fill_rect(p1[0] - w * 0.5, p1[1] - half, w, 2 * half, col)
                        p.fill_rect(p2[0] - w * 0.5, p2[1] - half, w, 2 * half, col)
                    else:
                        p.fill_rect(p1[0] - half, p1[1] - w * 0.5, 2 * half, w, col)
                        p.fill_rect(p2[0] - half, p2[1] - w * 0.5, 2 * half, w, col)

        _queue(render)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotStems
# --------------------------------------------------------------------------- #
def plot_stems(label_id: str, xs, ys=None, *args, **kw) -> None:
    """``PlotStems``::

        plot_stems(label, values, count=None, ref=0, scale=1, start=0, spec=None)
        plot_stems(label, xs, ys, count=None, ref=0, spec=None)
    """
    values, tail = _xy_or_values(label_id, xs, ys, args, kw,
                                 ("count", "ref", "scale", "start", "spec"), ("count", "ref", "spec"),
                                 {"count": None, "ref": 0.0, "scale": 1.0, "start": 0.0, "spec": None},
                                 {"count": None, "ref": 0.0, "spec": None})
    spec = _spec_from(tail, kw)
    count = tail["count"]
    ref = float(tail["ref"])
    horizontal = has_flag(spec.flags, I.STEMS_FLAGS_HORIZONTAL)
    if values:
        vals = _values(xs, count, spec.offset, spec.stride)
        lin = _lin(len(vals), float(tail["scale"]), float(tail["start"]))
        if horizontal:
            mark = list(zip(vals, lin))
            base = [(ref, y) for y in lin]
        else:
            mark = list(zip(lin, vals))
            base = [(x, ref) for x in lin]
    else:
        xs_ = _values(xs, count, spec.offset, spec.stride)
        ys_ = _values(ys, count, spec.offset, spec.stride)
        mark = list(zip(xs_, ys_))
        base = [(ref, y) for y in ys_] if horizontal else [(x, ref) for x in xs_]
    if begin_item_ex(label_id, _fitter2(mark, base), spec, spec.line_color, spec.marker):
        if len(mark) <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            sp = s.spec
            if s.render_line:
                _render_line_segments2(mark, base, sp.line_color, _colors(sp.line_colors, len(mark)),
                                       sp.line_weight)
            if s.render_markers:
                _render_colored_markers(mark, s)

        _queue(render, s.spec.marker_size if s.render_markers else 0.0)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotInfLines
# --------------------------------------------------------------------------- #
def plot_inf_lines(label_id: str, values, count=None, spec=None, **kw) -> None:
    """``PlotInfLines``: vertical lines at *values*, horizontal with
    ``INF_LINES_FLAGS_HORIZONTAL``. An ``int`` in the ``spec`` slot is flags,
    as the obsolete signature had it."""
    flags = kw.pop("flags", None)
    if isinstance(spec, int):
        flags, spec = int(spec) | int(flags or 0), None
    spec = _spec_from({"spec": spec, "flags": flags}, kw)
    vals = _values(values, count, spec.offset, spec.stride)
    horizontal = has_flag(spec.flags, I.INF_LINES_FLAGS_HORIZONTAL)

    def fitter(xa, ya):
        for v in vals:
            (ya if horizontal else xa).extend_fit(v)

    if begin_item_ex(label_id, fitter, spec, spec.line_color):
        if len(vals) <= 0:
            end_item()
            return
        s = _snapshot()

        def render():
            sp = s.spec
            if not s.render_line:
                return
            plot = gp.current_plot
            xa, ya = plot.axes[plot.current_x], plot.axes[plot.current_y]
            if horizontal:
                pmin = [(xa.range_min, v) for v in vals]
                pmax = [(xa.range_max, v) for v in vals]
            else:
                pmin = [(v, ya.range_min) for v in vals]
                pmax = [(v, ya.range_max) for v in vals]
            _render_line_segments2(pmin, pmax, sp.line_color, _colors(sp.line_colors, len(vals)),
                                   sp.line_weight)

        _queue(render)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotPieChart
# --------------------------------------------------------------------------- #
def _render_pie_slice(center, radius, a0, a1, col, flags, detached=False) -> None:
    """``RenderPieSlice``."""
    resolution = 50 / (2 * math.pi)
    n = max(3, int((a1 - a0) * resolution))
    t = _transformer()
    buf = []
    if detached:
        offset = 0.08
        width_scale = 0.95
        a_mid = (a0 + a1) / 2
        new_a0 = a_mid - (a1 - a0) * width_scale / 2
        new_a1 = a_mid + (a1 - a0) * width_scale / 2
        new_da = (new_a1 - new_a0) / (n - 1)
        oc = (center[0] + offset * math.cos(a_mid), center[1] + offset * math.sin(a_mid))
        buf.append(t(*oc))
        for i in range(n):
            a = new_a0 + i * new_da
            buf.append(t(oc[0] + (radius + offset / 2) * math.cos(a),
                         oc[1] + (radius + offset / 2) * math.sin(a)))
    else:
        da = (a1 - a0) / (n - 1)
        buf.append(t(*center))
        for i in range(n):
            a = a0 + i * da
            buf.append(t(center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))
    p = _dl().p
    _fill_convex(p, buf, col)
    if not has_flag(flags, I.PIE_CHART_FLAGS_NO_SLICE_BORDER):
        _polyline(p, buf + [buf[0]], 2.0, col)


def plot_pie_chart(label_ids, values, count=None, x: float = 0.5, y: float = 0.5,
                   radius: float = 0.4, label_fmt="%.1f", angle0: float = 90.0, spec=None,
                   fmt_data=None, **kw) -> None:
    """``PlotPieChart``: one slice (and legend entry) per label. *label_fmt* is
    printf, a formatter ``(value, data) -> str``, or ``None`` for no labels."""
    if gp.current_plot is None:
        raise RuntimeError("plot_pie_chart() needs to be called between begin_plot() and end_plot()")
    spec = _spec_from({"spec": spec}, kw)
    vals = _values(values, count, spec.offset, spec.stride)
    n = len(vals)
    ignore_hidden = has_flag(spec.flags, I.PIE_CHART_FLAGS_IGNORE_HIDDEN)
    items = gp.current_items

    def pie_sum():
        total = 0.0
        if ignore_hidden:
            for i in range(n):
                if i >= items.get_item_count():
                    break
                if items.get_item_by_index(i).show:
                    total += vals[i]
        else:
            total = sum(vals)
        return total

    total = pie_sum()
    normalize = has_flag(spec.flags, I.PIE_CHART_FLAGS_NORMALIZE) or total > 1.0
    center = (float(x), float(y))
    a0 = a1 = math.radians(angle0)
    pmin = (center[0] - radius, center[1] - radius)
    pmax = (center[0] + radius, center[1] + radius)
    slices = []
    for i in range(n):
        item = get_item(label_ids[i])
        percent = vals[i] / total if (normalize and total) else vals[i]
        skip = total <= 0.0 or (ignore_hidden and item is not None and not item.show)
        if not skip:
            a1 = a0 + 2 * math.pi * percent
        if begin_item_ex(label_ids[i], _fitter_rect(pmin, pmax), spec):
            if total > 0.0:
                col = gp.current_item.color
                slices.append((label_ids[i], a0, a1, percent, col))
            end_item()
        if not skip:
            a0 = a1
    # labels: every shown item, in order
    labels = []
    if label_fmt is not None:
        b0 = math.radians(angle0)
        for i in range(n):
            item = get_item(label_ids[i])
            if item is None:
                continue
            percent = vals[i] / total if (normalize and total) else vals[i]
            skip = ignore_hidden and not item.show
            if not skip:
                b1 = b0 + 2 * math.pi * percent
                if item.show:
                    text = (I.call_formatter(label_fmt, vals[i], fmt_data) if callable(label_fmt)
                            else I.format_printf(label_fmt, vals[i]))
                    labels.append((label_ids[i], b0, b1, text, item.color))
                b0 = b1
    flags = spec.flags
    exploding = has_flag(flags, I.PIE_CHART_FLAGS_EXPLODING)

    def render():
        api = _api()
        for label, s0, s1, percent, col in slices:
            hovered = exploding and api.is_legend_entry_hovered(label)
            if percent < 0.5:
                _render_pie_slice(center, radius, s0, s1, col, flags, hovered)
            else:
                mid = s0 + (s1 - s0) * 0.5
                _render_pie_slice(center, radius, s0, mid, col, flags, hovered)
                _render_pie_slice(center, radius, mid, s1, col, flags, hovered)
        t = _transformer()
        dl = _dl()
        for label, s0, s1, text, col in labels:
            size = I.calc_text_size(text)
            angle = s0 + (s1 - s0) * 0.5
            hovered = exploding and api.is_legend_entry_hovered(label)
            off = (0.6 if hovered else 0.5) * radius
            px, py = t(center[0] + off * math.cos(angle), center[1] + off * math.sin(angle))
            dl.add_text((px - size[0] * 0.5, py - size[1] * 0.5), I.calc_text_color(col), text)

    _queue(render)


# --------------------------------------------------------------------------- #
# [SECTION] PlotHeatmap
# --------------------------------------------------------------------------- #
def _render_heatmap(vals, rows, cols, scale_min, scale_max, fmt, bmin, bmax, reverse_y, col_maj,
                    cmap_colour) -> None:
    """``RenderHeatmap``. Cells are rounded onto one pixel grid, both edges, so
    neighbours leave no seam."""
    p = _dl().p
    t = _transformer()
    cull = _cull_rect()
    if scale_min == 0 and scale_max == 0:
        scale_min, scale_max = min(vals[:rows * cols]), max(vals[:rows * cols])
    if scale_min == scale_max:
        a = t(*bmin)
        b = t(*bmax)
        _fill_rect_pts(p, a, b, cmap_colour(None))
        return
    yref = bmax[1] if reverse_y else bmin[1]
    ydir = -1.0 if reverse_y else 1.0
    w = (bmax[0] - bmin[0]) / cols
    h = (bmax[1] - bmin[1]) / rows
    xe = [t(bmin[0] + c * w, 0.0)[0] for c in range(cols + 1)]
    ye = [t(0.0, yref + ydir * r * h)[1] for r in range(rows + 1)]
    labels = []
    for idx in range(rows * cols):
        if col_maj:
            r, c = idx % rows, idx // rows
        else:
            r, c = idx // cols, idx % cols
        v = vals[idx]
        tt = (v - scale_min) / (scale_max - scale_min)
        tt = min(max(tt, 0.0), 1.0) if tt == tt else 0.0
        col = cmap_colour(tt)
        x0, x1 = round(xe[c]), round(xe[c + 1])
        y0, y1 = round(ye[r]), round(ye[r + 1])
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if col[3] == 0 or not (y0 < cull[3] and y1 > cull[1] and x0 < cull[2] and x1 > cull[0]):
            continue
        p.fill_rect(x0, y0, max(x1 - x0, 1), max(y1 - y0, 1), col)
        if fmt:
            labels.append((((x0 + x1) * 0.5, (y0 + y1) * 0.5), v, col))
    if fmt:
        dl = _dl()
        for (cx, cy), v, col in labels:
            text = I.format_printf(fmt, v)
            size = I.calc_text_size(text)
            dl.add_text((cx - size[0] * 0.5, cy - size[1] * 0.5), I.calc_text_color(col), text)


def _flat(values) -> list:
    if len(values) and _is_series(values[0]):
        return [float(v) for row in values for v in row]
    return [float(v) for v in values]


def _heatmap_colour_fn():
    """What a cell samples: the current colormap -- emtk's pushed list, or
    Viridis when nothing was pushed (see :func:`plot_heatmap`)."""
    api = _api()
    stops = gp.anon_colormaps.get(gp.style.colormap) if gp.colormap_modifiers else None
    cmap = gp.style.colormap if gp.colormap_modifiers else I.COLORMAP_VIRIDIS
    if stops is None and not gp.colormap_modifiers and not api._heatmap_uses_style_colormap():
        cmap = I.COLORMAP_VIRIDIS

    def colour(tt):
        if tt is None:
            return I.get_colormap_color_u32(0, cmap)
        return gp.colormap_data.lerp_table(cmap, tt)
    return colour


def plot_heatmap(label_id: str, values, rows: int, cols: int, scale_min: float = 0.0,
                 scale_max: float = 0.0, label_fmt="%.1f", bounds_min=(0.0, 0.0),
                 bounds_max=(1.0, 1.0), flags=None, spec=None, **kw) -> None:
    """``PlotHeatmap``: a ``rows`` x ``cols`` grid over the bounds, row zero at
    the top. ``scale_min == scale_max == 0`` autoscales. *label_fmt* ``None``
    or ``""`` draws no labels.

    One deliberate difference: with no colormap pushed, the cells sample
    **Viridis**, not the style's colormap. The default style colormap is
    ``Deep`` -- ten categorical colours -- and a heatmap in categorical colours
    cannot say whether a value is big or small, which is all a heatmap is for.
    ``push_colormap`` (or ``style.colormap`` set to a continuous map) wins.
    """
    if gp.current_plot is None:
        raise RuntimeError("implot.plot_heatmap() outside a begin_plot()/end_plot() pair")
    if isinstance(flags, I.PlotSpec) or isinstance(flags, dict):
        spec, flags = flags, None
    spec = _spec_from({"spec": spec, "flags": flags}, kw)
    rows, cols = int(rows), int(cols)
    vals = _flat(values)
    bmin = (float(bounds_min[0]), float(bounds_min[1]))
    bmax = (float(bounds_max[0]), float(bounds_max[1]))
    if rows <= 0 or cols <= 0 or len(vals) < rows * cols:
        # a live window sizes its grid before the data behind it exists; the
        # reference reads past the end, here the item is skipped
        return
    if begin_item_ex(label_id, _fitter_rect(bmin, bmax), spec):
        col_maj = has_flag(spec.flags, I.HEATMAP_FLAGS_COL_MAJOR)
        colour = _heatmap_colour_fn()
        smin, smax = float(scale_min), float(scale_max)
        fmt = label_fmt or None

        def render():
            _render_heatmap(vals, rows, cols, smin, smax, fmt, bmin, bmax, True, col_maj, colour)

        _queue(render, record={"kind": "heatmap", "label": label_id, "rows": rows, "cols": cols})
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotHistogram
# --------------------------------------------------------------------------- #
def plot_histogram(label_id: str, values, count=None, bins: int = I.BIN_STURGES,
                   bar_scale: float = 1.0, range=None, spec=None, **kw) -> float:
    """``PlotHistogram``: bins raw samples. Returns the largest bin count (or
    density). *range* ``(min, max)``; ``None`` is the data's extent."""
    spec = _spec_from({"spec": spec}, kw)
    cumulative = has_flag(spec.flags, I.HISTOGRAM_FLAGS_CUMULATIVE)
    density = has_flag(spec.flags, I.HISTOGRAM_FLAGS_DENSITY)
    outliers = not has_flag(spec.flags, I.HISTOGRAM_FLAGS_NO_OUTLIERS)
    vals = [v for v in _values(values, count, spec.offset, spec.stride)]
    count = len(vals)
    if count <= 0 or bins == 0:
        return 0.0
    if range is None or (range[0] == 0 and range[1] == 0):
        finite = [v for v in vals if math.isfinite(v)]
        if not finite:
            return 0.0
        rng = (min(finite), max(finite))
    else:
        rng = (float(range[0]), float(range[1]))
    if bins < 0:
        bins, width = I.calc_bins(vals, count, bins, rng)
    else:
        width = (rng[1] - rng[0]) / bins
    if width <= 0:
        width = 1.0
    centers = [rng[0] + b * width + width * 0.5 for b in _range(bins)]
    counts = [0.0] * bins
    below = 0
    counted = 0
    max_count = 0.0
    for v in vals:
        if rng[0] <= v <= rng[1]:
            b = min(max(int((v - rng[0]) / width), 0), bins - 1)
            counts[b] += 1.0
            max_count = max(max_count, counts[b])
            counted += 1
        elif v < rng[0]:
            below += 1
    if cumulative and density:
        if outliers:
            counts[0] += below
        for b in _range(1, bins):
            counts[b] += counts[b - 1]
        scale = 1.0 / (count if outliers else max(counted, 1))
        counts = [c * scale for c in counts]
        max_count = counts[-1]
    elif cumulative:
        if outliers:
            counts[0] += below
        for b in _range(1, bins):
            counts[b] += counts[b - 1]
        max_count = counts[-1]
    elif density:
        scale = 1.0 / ((count if outliers else max(counted, 1)) * width)
        counts = [c * scale for c in counts]
        max_count *= scale
    spec_bars = spec.copy()
    spec_bars.offset, spec_bars.stride = 0, I.IMPLOT_AUTO
    if has_flag(spec.flags, I.HISTOGRAM_FLAGS_HORIZONTAL):
        spec_bars.flags = I.BARS_FLAGS_HORIZONTAL
        plot_bars(label_id, counts, centers, bins, bar_scale * width, spec=spec_bars)
    else:
        spec_bars.flags = 0
        plot_bars(label_id, centers, counts, bins, bar_scale * width, spec=spec_bars)
    return max_count


_range = range


def plot_histogram_2d(label_id: str, xs, ys, count=None, x_bins: int = I.BIN_STURGES,
                      y_bins: int = I.BIN_STURGES, range=None, spec=None, **kw) -> float:
    """``PlotHistogram2D``: a bivariate histogram drawn as a heatmap. *range*
    is ``(x_min, x_max, y_min, y_max)``."""
    spec = _spec_from({"spec": spec}, kw)
    density = has_flag(spec.flags, I.HISTOGRAM_FLAGS_DENSITY)
    outliers = not has_flag(spec.flags, I.HISTOGRAM_FLAGS_NO_OUTLIERS)
    col_maj = has_flag(spec.flags, I.HISTOGRAM_FLAGS_COL_MAJOR)
    xv = _values(xs, count, spec.offset, spec.stride)
    yv = _values(ys, count, spec.offset, spec.stride)
    count = min(len(xv), len(yv))
    if count <= 0 or x_bins == 0 or y_bins == 0:
        return 0.0
    rx = (0.0, 0.0) if range is None else (float(range[0]), float(range[1]))
    ry = (0.0, 0.0) if range is None else (float(range[2]), float(range[3]))
    if rx == (0.0, 0.0):
        rx = (min(xv), max(xv))
    if ry == (0.0, 0.0):
        ry = (min(yv), max(yv))
    if x_bins < 0:
        x_bins, width = I.calc_bins(xv, count, x_bins, rx)
    else:
        width = (rx[1] - rx[0]) / x_bins
    if y_bins < 0:
        y_bins, height = I.calc_bins(yv, count, y_bins, ry)
    else:
        height = (ry[1] - ry[0]) / y_bins
    width = width or 1.0
    height = height or 1.0
    counts = [0.0] * (x_bins * y_bins)
    counted = 0
    max_count = 0.0
    for i in _range(count):
        x, y = xv[i], yv[i]
        if rx[0] <= x <= rx[1] and ry[0] <= y <= ry[1]:
            xb = min(max(int((x - rx[0]) / width), 0), x_bins - 1)
            yb = min(max(int((y - ry[0]) / height), 0), y_bins - 1)
            b = yb * x_bins + xb
            counts[b] += 1.0
            max_count = max(max_count, counts[b])
            counted += 1
    if density:
        scale = 1.0 / ((count if outliers else max(counted, 1)) * width * height)
        counts = [c * scale for c in counts]
        max_count *= scale
    bmin, bmax = (rx[0], ry[0]), (rx[1], ry[1])
    if begin_item_ex(label_id, _fitter_rect(bmin, bmax), spec):
        cmap = gp.style.colormap

        def colour(tt):
            if tt is None:
                return I.get_colormap_color_u32(0, cmap)
            return gp.colormap_data.lerp_table(cmap, tt)

        mc = max_count

        def render():
            _render_heatmap(counts, y_bins, x_bins, 0.0, mc, None, bmin, bmax, False, col_maj, colour)

        _queue(render)
        end_item()
    return max_count


# --------------------------------------------------------------------------- #
# [SECTION] PlotDigital
# --------------------------------------------------------------------------- #
def _plot_digital_ex(label_id, pts, spec) -> None:
    if begin_item(label_id, spec, spec.fill_color):
        s = _snapshot()

        def render():
            sp = s.spec
            if len(pts) <= 1 or not s.render_fill:
                return
            plot = gp.current_plot
            xa, ya = plot.axes[plot.current_x], plot.axes[plot.current_y]
            t = _transformer()
            p = _dl().p
            pix_y_max = 0
            d1 = list(pts[0])
            i = 0
            n = len(pts)
            while i < n:
                d2 = list(pts[i])
                if I.nan_or_inf(d1[1]):
                    d1 = d2
                    i += 1
                    continue
                if I.nan_or_inf(d2[1]):
                    d2[1] = I.constrain_nan(I.constrain_inf(d2[1]))
                pix_y_0 = int(sp.line_weight)
                d1[1] = max(0.0, d1[1])
                pix_y_1 = sp.size * d1[1]
                pix_y_ch = int(max(sp.size, pix_y_1) + gp.style.digital_spacing)
                pix_y_max = max(pix_y_max, pix_y_ch)
                pmin = list(t(d1[0], d1[1]))
                pmax = list(t(d2[0], d2[1]))
                pix_y_offset = int(gp.style.digital_padding)
                y_ref = ya.pixel_max if ya.is_inverted() else ya.pixel_min
                pmin[1] = y_ref - (gp.digital_plot_offset + pix_y_offset)
                pmax[1] = y_ref - (gp.digital_plot_offset + pix_y_0 + int(pix_y_1) + pix_y_offset)
                while i + 2 < n and d1[1] == d2[1]:
                    d2 = list(pts[i + 1])
                    if I.nan_or_inf(d2[1]):
                        break
                    pmax[0] = t(d2[0], d2[1])[0]
                    i += 1
                lo = xa.pixel_min if not xa.is_inverted() else xa.pixel_max
                hi = (xa.pixel_max - 1) if not xa.is_inverted() else (xa.pixel_min - 1)
                pmin[0] = min(max(pmin[0], lo), hi)
                pmax[0] = min(max(pmax[0], lo), hi)
                r = plot.plot_rect
                if I.rect_contains(r, pmin) or I.rect_contains(r, pmax):
                    _fill_rect_pts(p, pmin, pmax, sp.fill_color)
                d1 = d2
                i += 1
            gp.digital_plot_item_cnt += 1
            gp.digital_plot_offset += pix_y_max

        _queue(render)
        end_item()


def plot_digital(label_id: str, xs, ys, count=None, spec=None, **kw) -> None:
    """``PlotDigital``: states stacked from the bottom of the plot, deaf to y
    zoom and pan."""
    spec = _spec_from({"spec": spec}, kw)
    pts = list(zip(_values(xs, count, spec.offset, spec.stride),
                   _values(ys, count, spec.offset, spec.stride)))
    _plot_digital_ex(label_id, pts, spec)


def plot_digital_g(label_id: str, getter, data, count: int, spec=None, **kw) -> None:
    spec = _spec_from({"spec": spec}, kw)
    _plot_digital_ex(label_id, _getter_points(getter, data, count), spec)


# --------------------------------------------------------------------------- #
# [SECTION] PlotImage
# --------------------------------------------------------------------------- #
def plot_image(label_id: str, texture, bounds_min, bounds_max, uv0=(0.0, 0.0), uv1=(1.0, 1.0),
               tint_col=(1.0, 1.0, 1.0, 1.0), spec=None, **kw) -> None:
    """``PlotImage``: *texture* is whatever the painter's ``image`` takes (an
    :class:`emtk.texture.Texture` on the pixel painter)."""
    spec = _spec_from({"spec": spec}, kw)
    bmin = (float(bounds_min[0]), float(bounds_min[1]))
    bmax = (float(bounds_max[0]), float(bounds_max[1]))
    if begin_item_ex(label_id, _fitter_rect(bmin, bmax), spec):
        tint = I.rgba(tint_col) or (255, 255, 255, 255)
        gp.current_item.color = tint

        def render():
            t = _transformer()
            p1 = t(bmin[0], bmax[1])
            p2 = t(bmax[0], bmin[1])
            u0, v0 = uv0
            u1, v1 = uv1
            x0, x1 = p1[0], p2[0]
            y0, y1 = p1[1], p2[1]
            if x1 < x0:
                x0, x1, u0, u1 = x1, x0, u1, u0
            if y1 < y0:
                y0, y1, v0, v1 = y1, y0, v1, v0
            _dl().add_image(texture, (x0, y0), (x1, y1), (u0, v0), (u1, v1), tint)

        _queue(render)
        end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotText
# --------------------------------------------------------------------------- #
def plot_text(text: str, x: float, y: float, pix_offset=(0.0, 0.0), spec=None, **kw) -> None:
    """``PlotText``: text centred on ``(x, y)``, vertical with
    ``TEXT_FLAGS_VERTICAL``."""
    if gp.current_plot is None:
        raise RuntimeError("plot_text() needs to be called between begin_plot() and end_plot()")
    api = _api()
    api.setup_lock()
    spec = _spec_from({"spec": spec}, kw)
    vertical = has_flag(spec.flags, I.TEXT_FLAGS_VERTICAL)
    col = I.get_style_color_u32(I.COL_INLAY_TEXT)
    siz = I.calc_text_size(text)
    if fit_this_frame() and not has_flag(spec.flags, I.ITEM_FLAGS_NO_FIT):
        pos = api.plot_to_pixels(x, y)
        if vertical:
            vs = (siz[1] * 0.5, siz[0] * 0.5)
            p0 = (pos[0] - vs[0] * 0.5 + pix_offset[0], pos[1] + vs[1] * 0.5 + pix_offset[1])
            fit_point(api.pixels_to_plot(*p0))
            fit_point(api.pixels_to_plot(p0[0] + vs[0], p0[1] - vs[1]))
        else:
            p0 = (pos[0] - siz[0] * 0.5 + pix_offset[0], pos[1] - siz[1] * 0.5 + pix_offset[1])
            fit_point(api.pixels_to_plot(*p0))
            fit_point(api.pixels_to_plot(p0[0] + siz[0], p0[1] + siz[1]))

    def render():
        t = _transformer()
        px, py = t(float(x), float(y))
        if vertical:
            # the text's own box, turned: centred on the point
            w, h = siz[1], siz[0]
            api._add_text_vertical((px - w * 0.5 + pix_offset[0], py + h * 0.5 + pix_offset[1]), col, text)
        else:
            _dl().add_text((px - siz[0] * 0.5 + pix_offset[0], py - siz[1] * 0.5 + pix_offset[1]), col, text)

    _queue(render)


# --------------------------------------------------------------------------- #
# [SECTION] PlotDummy
# --------------------------------------------------------------------------- #
def plot_dummy(label_id: str, spec=None, **kw) -> None:
    """``PlotDummy``: a legend entry and nothing else."""
    spec = _spec_from({"spec": spec}, kw)
    item_col = spec.line_color
    if item_col is None:
        item_col = spec.fill_color
    if item_col is None:
        item_col = spec.marker_line_color
    if item_col is None:
        item_col = spec.marker_fill_color
    if begin_item(label_id, spec, item_col, spec.marker):
        end_item()
