"""``emtk.implot3d_items`` -- ImPlot3D's plot items (``implot3d_items.cpp``).

Every item is projected here into screen triangles with a depth each and
queued on the plot's :class:`~emtk.implot3d.DrawList3D`; nothing reaches the
painter until ``end_plot`` sorts them. The renderer structs of the reference
(``RendererMarkersFill``, ``RendererLineStrip``, ``RendererSurfaceFill`` ...)
are functions with the same bodies, and its getters (``GetterXYZ``,
``GetterLoop``, ``GetterTriangleLines`` ...) are the index arithmetic they
carry, applied to a list of points materialised once per item.

Import these from :mod:`emtk.implot3d`, which re-exports them.
"""
from __future__ import annotations

import math

from . import implot3d as _p
from .implot3d import (
    FLAGS_NO_CLIP, IMPLOT3D_AUTO, IM_COL32_A_MASK, ITEM_FLAGS_NO_FIT, ITEM_FLAGS_NO_LEGEND,
    LEGEND_FLAGS_NO_HIGHLIGHT_ITEM, LINE_FLAGS_LOOP, LINE_FLAGS_SEGMENTS, LINE_FLAGS_SKIP_NAN,
    MARKER_ASTERISK, MARKER_AUTO, MARKER_CIRCLE, MARKER_CROSS, MARKER_DIAMOND, MARKER_DOWN,
    MARKER_INVALID, MARKER_LEFT, MARKER_NONE, MARKER_PLUS, MARKER_RIGHT, MARKER_SQUARE,
    MARKER_UP, MESH_FLAGS_NO_FILL, MESH_FLAGS_NO_LINES, MESH_FLAGS_NO_MARKERS,
    QUAD_FLAGS_NO_FILL, QUAD_FLAGS_NO_LINES, QUAD_FLAGS_NO_MARKERS, SURFACE_FLAGS_NO_FILL,
    SURFACE_FLAGS_NO_LINES, SURFACE_FLAGS_NO_MARKERS, TRIANGLE_FLAGS_NO_FILL,
    TRIANGLE_FLAGS_NO_LINES, TRIANGLE_FLAGS_NO_MARKERS, COL_INLAY_TEXT, IMPLOT3D_AUTO_COL,
    Point, as_spec, color_convert_float4_to_u32, color_convert_u32_to_float4, im_has_flag,
    to_u32, to_vec4,
)

__all__ = ["begin_item", "end_item", "register_or_get_item", "get_current_item",
           "plot_scatter", "plot_line", "plot_triangle", "plot_quad", "plot_surface",
           "plot_mesh", "plot_image", "plot_text", "plot_dummy"]

ITEM_HIGHLIGHT_LINE_SCALE = 2.0
ITEM_HIGHLIGHT_MARK_SCALE = 1.25
SQRT_1_2 = 0.70710678118
SQRT_3_2 = 0.86602540378


# --------------------------------------------------------------------------- #
# [SECTION] Item Utils
# --------------------------------------------------------------------------- #
def begin_item(label_id: str, spec=None, item_col=IMPLOT3D_AUTO_COL,
               item_mkr: int = MARKER_INVALID) -> bool:
    """``BeginItem``: register, resolve the style, and say whether to draw."""
    gp = _p._gp()
    if gp.current_plot is None:
        raise RuntimeError("PlotX() needs to be called between BeginPlot() and EndPlot()!")
    _p.setup_lock()
    spec = as_spec(spec)
    style = gp.style
    n = gp.next_item_data
    s = n.spec = spec.copy()
    item, just_created = register_or_get_item(label_id, spec.flags)
    gp.current_item = item
    item_col = to_vec4(item_col)
    if not _p.is_color_auto(item_col):
        item.color = color_convert_float4_to_u32(item_col)
    elif just_created:
        item.color = _p.next_colormap_color_u32()
    if item_mkr != MARKER_INVALID:
        if item_mkr != MARKER_AUTO:
            item.marker = item_mkr
        elif just_created or item.marker == MARKER_NONE:
            item.marker = _p.next_marker()
    item_color = color_convert_u32_to_float4(item.color)
    n.is_auto_line = _p.is_color_auto(s.line_color)
    n.is_auto_fill = _p.is_color_auto(s.fill_color)
    s.line_color = item_color if n.is_auto_line else s.line_color
    s.fill_color = item_color if n.is_auto_fill else s.fill_color
    if _p.is_color_auto(s.marker_line_color):
        s.marker_line_color = s.line_color
    if _p.is_color_auto(s.marker_fill_color):
        s.marker_fill_color = s.line_color
    s.line_weight = style.line_weight if s.line_weight < 0.0 else s.line_weight
    s.marker = style.marker if s.marker < 0 else s.marker
    s.marker_size = style.marker_size if s.marker_size < 0.0 else s.marker_size
    s.fill_alpha = style.fill_alpha if s.fill_alpha < 0 else s.fill_alpha
    fc, mfc = s.fill_color, s.marker_fill_color
    s.fill_color = (fc[0], fc[1], fc[2], fc[3] * s.fill_alpha)
    s.marker_fill_color = (mfc[0], mfc[1], mfc[2], mfc[3] * s.fill_alpha)
    n.render_line = s.line_color[3] > 0 and s.line_weight > 0
    n.render_fill = s.fill_color[3] > 0
    n.render_marker_line = s.line_color[3] > 0 and s.line_weight > 0
    n.render_marker_fill = s.fill_color[3] > 0
    if not item.show:
        end_item()
        return False
    if item.legend_hovered and not im_has_flag(gp.current_items.legend.flags,
                                               LEGEND_FLAGS_NO_HIGHLIGHT_ITEM):
        s.line_weight *= ITEM_HIGHLIGHT_LINE_SCALE
        s.marker_size *= ITEM_HIGHLIGHT_MARK_SCALE
    return True


def _begin_item_ex(label_id, points, spec, item_col=IMPLOT3D_AUTO_COL,
                   item_mkr=MARKER_INVALID) -> bool:
    if begin_item(label_id, spec, item_col, item_mkr):
        plot = _p._gp().current_plot
        if plot.fit_this_frame and not im_has_flag(as_spec(spec).flags, ITEM_FLAGS_NO_FIT):
            for pt in points:
                plot.extend_fit(pt)
        return True
    return False


def end_item() -> None:
    gp = _p._gp()
    gp.next_item_data.reset()
    gp.current_item = None


def register_or_get_item(label_id: str, flags: int):
    """``RegisterOrGetItem``: ``(item, just_created)``."""
    gp = _p._gp()
    items = gp.current_items
    item_id = _p._im().get_id(label_id)
    just_created = items.get_item(item_id) is None
    item = items.get_or_add_item(item_id)
    if item.seen_this_frame:
        return item, just_created
    item.seen_this_frame = True
    idx = items.get_item_index(item)
    item.id = item_id
    if not im_has_flag(flags, ITEM_FLAGS_NO_LEGEND) and _p._display_text(label_id):
        items.legend.indices.append(idx)
        item.name = label_id
    return item, just_created


def get_current_item():
    return _p._gp().current_item


# --------------------------------------------------------------------------- #
# [SECTION] Indexers and getters
# --------------------------------------------------------------------------- #
def _index_data(data, count: int, offset: int, stride: int):
    """``IndexerIdx``: ``data[(offset + i) % count * stride]``, as a list."""
    stride = 1 if stride == IMPLOT3D_AUTO else int(stride)
    offset = _p.im_pos_mod(offset, count) if count else 0
    if offset == 0 and stride == 1:
        return [float(data[i]) for i in range(count)]
    if offset == 0:
        return [float(data[i * stride]) for i in range(count)]
    return [float(data[((offset + i) % count) * stride]) for i in range(count)]


def _points(xs, ys, zs, count: int, spec):
    s = as_spec(spec)
    return list(zip(_index_data(xs, count, s.offset, s.stride),
                    _index_data(ys, count, s.offset, s.stride),
                    _index_data(zs, count, s.offset, s.stride)))


def _count(count, *arrays) -> int:
    return int(count) if count is not None else min(len(a) for a in arrays)


def _loop(points):
    """``GetterLoop``: the first point again at the end."""
    return list(points) + [points[0]]


def _triangle_lines(points):
    """``GetterTriangleLines``: each triangle's three edges as segment pairs."""
    out = []
    for idx in range(len(points) * 2):
        out.append(points[((idx % 6 + 1) // 2) % 3 + idx // 6 * 3])
    return out


def _quad_lines(points):
    """``GetterQuadLines``: each quad's four edges as segment pairs."""
    out = []
    for idx in range(len(points) * 2):
        out.append(points[((idx % 8 + 1) // 2) % 4 + idx // 8 * 4])
    return out


def _surface_lines(points, x_count: int, y_count: int):
    """``GetterSurfaceLines``: every grid edge, horizontal then vertical."""
    out = []
    horizontal = (x_count - 1) * y_count
    vertical = (y_count - 1) * x_count
    for idx in range((horizontal + vertical) * 2):
        endpoint, segment = idx % 2, idx // 2
        if segment < horizontal:
            row, col = segment // (x_count - 1), segment % (x_count - 1)
            px, py = (col if endpoint == 0 else col + 1), row
        else:
            seg_v = segment - horizontal
            px, py = seg_v // (y_count - 1), seg_v % (y_count - 1) + endpoint
        out.append(points[py * x_count + px])
    return out


def _color_getter(colors, count: int, alpha: float = 1.0):
    """``GetterIdxColor``: a per-index colour list, alpha-scaled."""
    out = []
    for i in range(count):
        col = to_u32(colors[i])
        if alpha < 1.0:
            c = color_convert_u32_to_float4(col)
            col = color_convert_float4_to_u32((c[0], c[1], c[2], c[3] * alpha))
        out.append(col)
    return out


# --------------------------------------------------------------------------- #
# [SECTION] Renderers
# --------------------------------------------------------------------------- #
class _Ctx:
    """What ``RenderPrimitivesEx`` sets up: the plot, the cull box, the projector."""

    __slots__ = ("plot", "dl", "proj", "cull")

    def __init__(self) -> None:
        plot = _p._gp().current_plot
        self.plot = plot
        self.dl = plot.draw_list
        self.proj = _p._Projector(plot)
        if im_has_flag(plot.flags, FLAGS_NO_CLIP):
            inf = math.inf
            self.cull = (-inf, -inf, -inf, inf, inf, inf)
        else:
            lo, hi = plot.range_min(), plot.range_max()
            self.cull = (lo.x, lo.y, lo.z, hi.x, hi.y, hi.z)

    def contains(self, p) -> bool:
        c = self.cull
        return c[0] <= p[0] <= c[3] and c[1] <= p[1] <= c[4] and c[2] <= p[2] <= c[5]


def _is_nan(p) -> bool:
    return p[0] != p[0] or p[1] != p[1] or p[2] != p[2]


def render_markers_fill(points, col_getter, size_getter, marker) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    for prim, pt in enumerate(points):
        if not rc.contains(pt):
            continue
        px, py = to_pixels(*pt)
        col, size = col_getter(prim), size_getter(prim)
        verts = [(px + mx * size, py + my * size) for mx, my in marker]
        z = depth(*pt)
        for i in range(2, len(marker)):
            dl.add(verts[0], verts[i - 1], verts[i], col, col, col, z)


def render_markers_line(points, col_getter, size_getter, marker, weight: float) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    half = max(1.0, weight) * 0.5
    for prim, pt in enumerate(points):
        if not rc.contains(pt):
            continue
        px, py = to_pixels(*pt)
        col, size = col_getter(prim), size_getter(prim)
        z = depth(*pt)
        for i in range(0, len(marker), 2):
            dl.prim_line(px + marker[i][0] * size, py + marker[i][1] * size,
                         px + marker[i + 1][0] * size, py + marker[i + 1][1] * size, half, col, z)


def _render_segment(rc, p1, p2, half, col) -> bool:
    c = rc.cull
    visible, a, b = _p._clip_segment(c[0], c[1], c[2], c[3], c[4], c[5], p1, p2)
    if visible:
        x1, y1 = rc.proj.to_pixels(*a)
        x2, y2 = rc.proj.to_pixels(*b)
        rc.dl.prim_line(x1, y1, x2, y2, half, col,
                        rc.proj.depth((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5,
                                      (p1[2] + p2[2]) * 0.5))
    return visible


def render_line_strip(points, col_getter, weight: float) -> None:
    """``RendererLineStrip``: a NaN is not skipped -- it breaks the segment."""
    rc = _Ctx()
    half = max(1.0, weight) * 0.5
    for prim in range(len(points) - 1):
        _render_segment(rc, points[prim], points[prim + 1], half, col_getter(prim))


def render_line_strip_skip(points, col_getter, weight: float) -> None:
    """``RendererLineStripSkip``: NaN points are stepped over."""
    rc = _Ctx()
    half = max(1.0, weight) * 0.5
    p1 = points[0]
    for prim in range(len(points) - 1):
        p2 = points[prim + 1]
        if not _is_nan(p1) and not _is_nan(p2):
            _render_segment(rc, p1, p2, half, col_getter(prim))
        if not _is_nan(p2):
            p1 = p2


def render_line_segments(points, col_getter, weight: float) -> None:
    rc = _Ctx()
    half = max(1.0, weight) * 0.5
    for prim in range(len(points) // 2):
        p1, p2 = points[prim * 2], points[prim * 2 + 1]
        if not _is_nan(p1) and not _is_nan(p2):
            _render_segment(rc, p1, p2, half, col_getter(prim))


def render_triangle_fill(points, col_getter) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    for prim in range(len(points) // 3):
        a, b, c = points[3 * prim], points[3 * prim + 1], points[3 * prim + 2]
        if not rc.contains(a) and not rc.contains(b) and not rc.contains(c):
            continue
        dl.add(to_pixels(*a), to_pixels(*b), to_pixels(*c), col_getter(3 * prim),
               col_getter(3 * prim + 1), col_getter(3 * prim + 2),
               depth((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3,
                     (a[2] + b[2] + c[2]) / 3))


def render_quad_fill(points, col_getter) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    for prim in range(len(points) // 4):
        q = points[4 * prim:4 * prim + 4]
        if not any(rc.contains(v) for v in q):
            continue
        p = [to_pixels(*v) for v in q]
        cols = [col_getter(4 * prim + k) for k in range(4)]
        z = depth(sum(v[0] for v in q) / 4.0, sum(v[1] for v in q) / 4.0,
                  sum(v[2] for v in q) / 4.0)
        dl.add(p[0], p[1], p[2], cols[0], cols[1], cols[2], z)
        dl.add(p[0], p[2], p[3], cols[0], cols[2], cols[3], z)


def render_quad_image(points, tex, uv0, uv1, uv2, uv3, col: int) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    for prim in range(len(points) // 4):
        q = points[4 * prim:4 * prim + 4]
        if not any(rc.contains(v) for v in q):
            continue
        p = [to_pixels(*v) for v in q]
        z = depth(sum(v[0] for v in q) / 4.0, sum(v[1] for v in q) / 4.0,
                  sum(v[2] for v in q) / 4.0)
        dl.add(p[0], p[1], p[2], col, col, col, z, tex, uv0, uv1, uv2)
        dl.add(p[0], p[2], p[3], col, col, col, z, tex, uv0, uv2, uv3)


def render_surface_fill(points, x_count: int, y_count: int, col: int,
                        scale_min: float, scale_max: float) -> None:
    rc = _Ctx()
    to_pixels, depth, dl = rc.proj.to_pixels, rc.proj.depth, rc.dl
    n = _p.get_item_data()
    s = n.spec
    vmin = vmax = 0.0
    if n.is_auto_fill:
        zs = [p[2] for p in points]
        vmin, vmax = min(zs), max(zs)
    if scale_min != 0.0 or scale_max != 0.0:
        vmin, vmax = scale_min, scale_max
    fill_colors = s.fill_colors
    alpha = s.fill_alpha
    cache: dict = {}
    for prim in range((x_count - 1) * (y_count - 1)):
        x = prim % (x_count - 1)
        y = prim // (x_count - 1)
        idx = (x + y * x_count, x + 1 + y * x_count, x + 1 + (y + 1) * x_count,
               x + (y + 1) * x_count)
        q = [points[i] for i in idx]
        if not any(rc.contains(v) for v in q):
            continue
        cols = [col, col, col, col]
        if fill_colors is not None:
            for k in range(4):
                c = color_convert_u32_to_float4(to_u32(fill_colors[idx[k]]))
                cols[k] = color_convert_float4_to_u32((c[0], c[1], c[2], c[3] * alpha))
        elif n.is_auto_fill:
            for k in range(4):
                t = min(max(_p.im_remap01(q[k][2], vmin, vmax), 0.0), 1.0)
                got = cache.get(t)
                if got is None:
                    c = _p.sample_colormap(t)
                    got = cache[t] = color_convert_float4_to_u32((c[0], c[1], c[2], c[3] * alpha))
                cols[k] = got
        p = [to_pixels(*v) for v in q]
        dl.add(p[0], p[1], p[2], cols[0], cols[1], cols[2],
               depth((q[0][0] + q[1][0] + q[2][0]) / 3.0, (q[0][1] + q[1][1] + q[2][1]) / 3.0,
                     (q[0][2] + q[1][2] + q[2][2]) / 3.0))
        dl.add(p[0], p[2], p[3], cols[0], cols[2], cols[3],
               depth((q[0][0] + q[2][0] + q[3][0]) / 3.0, (q[0][1] + q[2][1] + q[3][1]) / 3.0,
                     (q[0][2] + q[2][2] + q[3][2]) / 3.0))


# --------------------------------------------------------------------------- #
# [SECTION] Markers
# --------------------------------------------------------------------------- #
_CIRCLE = ((1.0, 0.0), (0.809017, 0.58778524), (0.30901697, 0.95105654),
           (-0.30901703, 0.9510565), (-0.80901706, 0.5877852), (-1.0, 0.0),
           (-0.80901694, -0.58778536), (-0.3090171, -0.9510565), (0.30901712, -0.9510565),
           (0.80901694, -0.5877853))
MARKER_FILL_CIRCLE = _CIRCLE
MARKER_FILL_SQUARE = ((SQRT_1_2, SQRT_1_2), (SQRT_1_2, -SQRT_1_2), (-SQRT_1_2, -SQRT_1_2),
                      (-SQRT_1_2, SQRT_1_2))
MARKER_FILL_DIAMOND = ((1, 0), (0, -1), (-1, 0), (0, 1))
MARKER_FILL_UP = ((SQRT_3_2, 0.5), (0, -1), (-SQRT_3_2, 0.5))
MARKER_FILL_DOWN = ((SQRT_3_2, -0.5), (0, 1), (-SQRT_3_2, -0.5))
MARKER_FILL_LEFT = ((-1, 0), (0.5, SQRT_3_2), (0.5, -SQRT_3_2))
MARKER_FILL_RIGHT = ((1, 0), (-0.5, SQRT_3_2), (-0.5, -SQRT_3_2))


def _closed_outline(fill):
    out = []
    for i in range(len(fill)):
        out += [fill[i], fill[(i + 1) % len(fill)]]
    return tuple(out)


MARKER_LINE_CIRCLE = _closed_outline(_CIRCLE)
MARKER_LINE_SQUARE = _closed_outline(MARKER_FILL_SQUARE)
MARKER_LINE_DIAMOND = _closed_outline(MARKER_FILL_DIAMOND)
MARKER_LINE_UP = _closed_outline(MARKER_FILL_UP)
MARKER_LINE_DOWN = _closed_outline(MARKER_FILL_DOWN)
MARKER_LINE_LEFT = _closed_outline(MARKER_FILL_LEFT)
MARKER_LINE_RIGHT = _closed_outline(MARKER_FILL_RIGHT)
MARKER_LINE_ASTERISK = ((-SQRT_3_2, -0.5), (SQRT_3_2, 0.5), (-SQRT_3_2, 0.5), (SQRT_3_2, -0.5),
                        (0, -1), (0, 1))
MARKER_LINE_PLUS = ((-1, 0), (1, 0), (0, -1), (0, 1))
MARKER_LINE_CROSS = ((-SQRT_1_2, -SQRT_1_2), (SQRT_1_2, SQRT_1_2), (SQRT_1_2, -SQRT_1_2),
                     (-SQRT_1_2, SQRT_1_2))

_FILL_SHAPES = {MARKER_CIRCLE: MARKER_FILL_CIRCLE, MARKER_SQUARE: MARKER_FILL_SQUARE,
                MARKER_DIAMOND: MARKER_FILL_DIAMOND, MARKER_UP: MARKER_FILL_UP,
                MARKER_DOWN: MARKER_FILL_DOWN, MARKER_LEFT: MARKER_FILL_LEFT,
                MARKER_RIGHT: MARKER_FILL_RIGHT}
_LINE_SHAPES = {MARKER_CIRCLE: MARKER_LINE_CIRCLE, MARKER_SQUARE: MARKER_LINE_SQUARE,
                MARKER_DIAMOND: MARKER_LINE_DIAMOND, MARKER_UP: MARKER_LINE_UP,
                MARKER_DOWN: MARKER_LINE_DOWN, MARKER_LEFT: MARKER_LINE_LEFT,
                MARKER_RIGHT: MARKER_LINE_RIGHT, MARKER_ASTERISK: MARKER_LINE_ASTERISK,
                MARKER_PLUS: MARKER_LINE_PLUS, MARKER_CROSS: MARKER_LINE_CROSS}


def render_markers(points, marker: int, rend_fill: bool, col_fill, rend_line: bool,
                   col_line, size, weight: float) -> None:
    if rend_fill and marker in _FILL_SHAPES:
        render_markers_fill(points, col_fill, size, _FILL_SHAPES[marker])
    if rend_line and marker in _LINE_SHAPES:
        render_markers_line(points, col_line, size, _LINE_SHAPES[marker], weight)


def render_colored_markers(points, n) -> None:
    s = n.spec
    count = len(points)
    line_u32 = color_convert_float4_to_u32(s.marker_line_color)
    fill_u32 = color_convert_float4_to_u32(s.marker_fill_color)
    if s.marker_sizes is not None:
        sizes = s.marker_sizes
        size = sizes.__getitem__
    else:
        size = (lambda _i, v=s.marker_size: v)
    if s.marker_fill_colors is not None:
        fill = _color_getter(s.marker_fill_colors, count, s.fill_alpha).__getitem__
    else:
        fill = (lambda _i, v=fill_u32: v)
    if s.marker_line_colors is not None:
        line = _color_getter(s.marker_line_colors, count).__getitem__
    else:
        line = (lambda _i, v=line_u32: v)
    render_markers(points, s.marker, n.render_marker_fill, fill, n.render_marker_line, line,
                   size, s.line_weight)


def _const(u32):
    return lambda _i: u32


# --------------------------------------------------------------------------- #
# [SECTION] PlotScatter / PlotLine / PlotTriangle / PlotQuad
# --------------------------------------------------------------------------- #
def plot_scatter(label_id: str, xs, ys, zs, count: int | None = None, spec=None) -> None:
    """``PlotScatter``: a marker at every point (a circle unless told otherwise)."""
    count = _count(count, xs, ys, zs)
    if count < 1:
        return
    spec = as_spec(spec)
    points = _points(xs, ys, zs, count, spec)
    if _begin_item_ex(label_id, points, spec, spec.marker_line_color, spec.marker):
        n = _p._gp().next_item_data
        if n.spec.marker == MARKER_NONE:
            n.spec.marker = MARKER_CIRCLE
        if n.spec.marker != MARKER_NONE:
            render_colored_markers(points, n)
        end_item()


def plot_line(label_id: str, xs, ys, zs, count: int | None = None, spec=None) -> None:
    """``PlotLine``: a strip; ``LINE_FLAGS_SEGMENTS`` pairs, ``_LOOP`` closes it."""
    count = _count(count, xs, ys, zs)
    if count < 2:
        return
    spec = as_spec(spec)
    points = _points(xs, ys, zs, count, spec)
    if not _begin_item_ex(label_id, points, spec, spec.line_color, spec.marker):
        return
    n = _p.get_item_data()
    s = n.spec
    if count >= 2 and n.render_line:
        if s.line_colors is not None:
            col = _color_getter(s.line_colors, count).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.line_color))
        skip = im_has_flag(spec.flags, LINE_FLAGS_SKIP_NAN)
        if im_has_flag(spec.flags, LINE_FLAGS_SEGMENTS):
            render_line_segments(points, col, s.line_weight)
        elif im_has_flag(spec.flags, LINE_FLAGS_LOOP):
            loop = _loop(points)
            if s.line_colors is not None:
                base = col
                col = lambda i: base(i % count)  # noqa: E731
            (render_line_strip_skip if skip else render_line_strip)(loop, col, s.line_weight)
        else:
            (render_line_strip_skip if skip else render_line_strip)(points, col, s.line_weight)
    if s.marker != MARKER_NONE:
        render_colored_markers(points, n)
    end_item()


def plot_triangle(label_id: str, xs, ys, zs, count: int | None = None, spec=None) -> None:
    """``PlotTriangle``: every three points a triangle."""
    count = _count(count, xs, ys, zs)
    if count < 3:
        return
    spec = as_spec(spec)
    points = _points(xs, ys, zs, count, spec)
    _plot_filled(label_id, points, spec, render_triangle_fill, _triangle_lines,
                 TRIANGLE_FLAGS_NO_FILL, TRIANGLE_FLAGS_NO_LINES, TRIANGLE_FLAGS_NO_MARKERS, 3)


def plot_quad(label_id: str, xs, ys, zs, count: int | None = None, spec=None) -> None:
    """``PlotQuad``: every four points a quad (two triangles, one depth)."""
    count = _count(count, xs, ys, zs)
    if count < 3:
        return
    spec = as_spec(spec)
    points = _points(xs, ys, zs, count, spec)
    _plot_filled(label_id, points, spec, render_quad_fill, _quad_lines,
                 QUAD_FLAGS_NO_FILL, QUAD_FLAGS_NO_LINES, QUAD_FLAGS_NO_MARKERS, 4)


def _plot_filled(label_id, points, spec, fill_renderer, lines_of, no_fill, no_lines,
                 no_markers, min_count) -> None:
    if not _begin_item_ex(label_id, points, spec, spec.fill_color, spec.marker):
        return
    n = _p.get_item_data()
    s = n.spec
    count = len(points)
    if count >= min_count and n.render_fill and not im_has_flag(spec.flags, no_fill):
        if s.fill_colors is not None:
            col = _color_getter(s.fill_colors, count, s.fill_alpha).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.fill_color))
        fill_renderer(points, col)
    if count >= 2 and n.render_line and not im_has_flag(spec.flags, no_lines):
        if s.line_colors is not None:
            col = _color_getter(s.line_colors, count).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.line_color))
        render_line_segments(lines_of(points), col, s.line_weight)
    if s.marker != MARKER_NONE and not im_has_flag(spec.flags, no_markers):
        render_colored_markers(points, n)
    end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotSurface
# --------------------------------------------------------------------------- #
def plot_surface(label_id: str, xs, ys, zs, x_count: int, y_count: int,
                 scale_min: float = 0.0, scale_max: float = 0.0, spec=None) -> None:
    """``PlotSurface``: a ``x_count * y_count`` grid, row-major.

    With an automatic fill the colour at each vertex samples the current
    colormap by z over ``[scale_min, scale_max]`` (both 0 means the data's
    range), and is interpolated across each cell.
    """
    count = x_count * y_count
    if count < 4:
        return
    spec = as_spec(spec)
    points = _points(xs, ys, zs, count, spec)
    if not _begin_item_ex(label_id, points, spec, spec.fill_color, spec.marker):
        return
    n = _p.get_item_data()
    s = n.spec
    if count >= 4 and n.render_fill and not im_has_flag(spec.flags, SURFACE_FLAGS_NO_FILL):
        render_surface_fill(points, x_count, y_count, color_convert_float4_to_u32(s.fill_color),
                            scale_min, scale_max)
    if count >= 2 and n.render_line and not im_has_flag(spec.flags, SURFACE_FLAGS_NO_LINES):
        if s.line_colors is not None:
            col = _color_getter(s.line_colors, count).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.line_color))
        render_line_segments(_surface_lines(points, x_count, y_count), col, s.line_weight)
    if s.marker != MARKER_NONE and not im_has_flag(spec.flags, SURFACE_FLAGS_NO_MARKERS):
        render_colored_markers(points, n)
    end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotMesh
# --------------------------------------------------------------------------- #
def plot_mesh(label_id: str, *args, spec=None) -> None:
    """``PlotMesh``, both overloads::

        plot_mesh(label, vtx_xs, vtx_ys, vtx_zs, idxs[, vtx_count, idx_count][, spec])
        plot_mesh(label, vtx, idxs[, vtx_count, idx_count][, spec])   # (x, y, z) points

    ``fill_colors`` / ``line_colors`` have one entry per *index* (per triangle
    corner -- different corners of one triangle give Gouraud shading);
    ``marker_*_colors`` one per vertex. Mesh lines are drawn only when the
    line colour is set explicitly.
    """
    args = list(args)
    if args and not isinstance(args[-1], (int, float)) and not (
            hasattr(args[-1], "__len__") and len(args) in (2, 4)):
        spec = args.pop()
    if len(args) >= 4 and hasattr(args[2], "__len__"):
        vx, vy, vz, idxs = args[:4]
        rest = args[4:]
        vtx_count = int(rest[0]) if rest else min(len(vx), len(vy), len(vz))
    else:
        vtx, idxs = args[:2]
        rest = args[2:]
        vx = [v[0] for v in vtx]
        vy = [v[1] for v in vtx]
        vz = [v[2] for v in vtx]
        vtx_count = int(rest[0]) if rest else len(vtx)
    idx_count = int(rest[1]) if len(rest) > 1 else len(idxs)
    if vtx_count < 3 or idx_count < 3:
        return
    spec = as_spec(spec)
    points = _points(vx, vy, vz, vtx_count, spec)
    triangles = [points[int(idxs[i])] for i in range(idx_count)]
    if not _begin_item_ex(label_id, points, spec, spec.fill_color, spec.marker):
        return
    n = _p.get_item_data()
    s = n.spec
    if vtx_count >= 3 and n.render_fill and not im_has_flag(spec.flags, MESH_FLAGS_NO_FILL):
        if s.fill_colors is not None:
            col = _color_getter(s.fill_colors, idx_count, s.fill_alpha).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.fill_color))
        render_triangle_fill(triangles, col)
    if (vtx_count >= 2 and n.render_line and not n.is_auto_line
            and not im_has_flag(spec.flags, MESH_FLAGS_NO_LINES)):
        if s.line_colors is not None:
            col = _color_getter(s.line_colors, idx_count).__getitem__
        else:
            col = _const(color_convert_float4_to_u32(s.line_color))
        render_line_segments(_triangle_lines(triangles), col, s.line_weight)
    if s.marker != MARKER_NONE and not im_has_flag(spec.flags, MESH_FLAGS_NO_MARKERS):
        render_colored_markers(points, n)
    end_item()


# --------------------------------------------------------------------------- #
# [SECTION] PlotImage
# --------------------------------------------------------------------------- #
def plot_image(label_id: str, tex_ref, *args, spec=None) -> None:
    """``PlotImage``, both overloads::

        plot_image(label, tex, center, axis_u, axis_v[, uv0, uv1][, tint][, spec])
        plot_image(label, tex, p0, p1, p2, p3[, uv0, uv1, uv2, uv3][, tint][, spec])

    Told apart by whether the fourth positional point is 3-D. ``tex_ref`` is
    whatever the painter's ``image_triangle`` reads -- an
    :class:`emtk.texture.Texture` on the shipped painters.
    """
    args = list(args)
    if args and isinstance(args[-1], (Spec_, dict)):
        spec = args.pop()
    three_d = [a for a in args if hasattr(a, "__len__") and len(a) == 3]
    if len(args) >= 4 and hasattr(args[3], "__len__") and len(args[3]) == 3 and len(three_d) >= 4:
        p0, p1, p2, p3 = (Point(*a) for a in args[:4])
        rest = args[4:]
        uv0 = tuple(rest[0]) if len(rest) > 0 else (0.0, 0.0)
        uv1 = tuple(rest[1]) if len(rest) > 1 else (1.0, 0.0)
        uv2 = tuple(rest[2]) if len(rest) > 2 else (1.0, 1.0)
        uv3 = tuple(rest[3]) if len(rest) > 3 else (0.0, 1.0)
        tint = rest[4] if len(rest) > 4 else (1.0, 1.0, 1.0, 1.0)
    else:
        center, axis_u, axis_v = (Point(*a) for a in args[:3])
        rest = args[3:]
        a0 = tuple(rest[0]) if len(rest) > 0 else (0.0, 0.0)
        a1 = tuple(rest[1]) if len(rest) > 1 else (1.0, 1.0)
        tint = rest[2] if len(rest) > 2 else (1.0, 1.0, 1.0, 1.0)
        p0 = center - axis_u - axis_v
        p1 = center + axis_u - axis_v
        p2 = center + axis_u + axis_v
        p3 = center - axis_u + axis_v
        uv0, uv1, uv2, uv3 = a0, (a1[0], a0[1]), a1, (a0[0], a1[1])
    gp = _p._gp()
    if gp.current_plot is None:
        raise RuntimeError("PlotImage() needs to be called between BeginPlot() and EndPlot()!")
    _p.setup_lock()
    corners = [tuple(p0), tuple(p1), tuple(p2), tuple(p3)]
    flip = [(uv[0], 1.0 - uv[1]) for uv in (uv0, uv1, uv2, uv3)]
    spec = as_spec(spec)
    tint = to_vec4(tint)
    if _begin_item_ex(label_id, corners, spec, tint, spec.marker):
        tint32 = color_convert_float4_to_u32(tint)
        get_current_item().color = tint32
        if tint32 & IM_COL32_A_MASK:
            render_quad_image(corners, tex_ref, *flip, tint32)
        end_item()


Spec_ = _p.Spec


# --------------------------------------------------------------------------- #
# [SECTION] PlotText
# --------------------------------------------------------------------------- #
def plot_text(text: str, x: float, y: float, z: float, angle: float = 0.0,
              pix_offset=(0.0, 0.0)) -> None:
    """``PlotText``: centred on ``(x, y, z)``, turned by *angle* radians.

    Drawn straight away, over the box and under the sorted items, as the
    reference draws it into the window's draw list.
    """
    gp = _p._gp()
    plot = gp.current_plot
    if plot is None:
        raise RuntimeError("PlotText() needs to be called between BeginPlot() and EndPlot()!")
    _p.setup_lock()
    if not im_has_flag(plot.flags, FLAGS_NO_CLIP):
        lo, hi = plot.range_min(), plot.range_max()
        if not (lo.x <= x <= hi.x and lo.y <= y <= hi.y and lo.z <= z <= hi.z):
            return
    px, py = _p.plot_to_pixels(x, y, z)
    _p.add_text_rotated(_p.get_plot_draw_list(), (px + pix_offset[0], py + pix_offset[1]),
                        float(angle), _p.get_style_color_u32(COL_INLAY_TEXT), text)


def plot_dummy(label_id: str, spec=None) -> None:
    """``PlotDummy``: a legend entry with no geometry, coloured by the spec."""
    spec = as_spec(spec)
    item_col = spec.line_color
    for candidate in (spec.fill_color, spec.marker_line_color, spec.marker_fill_color):
        if _p.is_color_auto(item_col):
            item_col = candidate
    if begin_item(label_id, spec, item_col, spec.marker):
        end_item()
