"""``DrawList``: Dear ImGui's ``ImDrawList`` names over any :class:`~.painter.Painter`.

The point is porting. A widget from the ImGui ecosystem (implot, imspinner,
imnodes...) is written against ``draw_list->AddLine / AddRectFilled /
PathArcTo / PathStroke``; transliterated line by line it wants those names.
This class has them, in snake_case, and decomposes each into the Painter's
primitives -- so a port runs on *any* Painter today (the Qt one, the quad
one, the recording one in the tests) and gets faster where a Painter grows
the native op (:meth:`QuadPainter.polyline`, :meth:`fill_convex`).

Coordinates are pixels; colours are the toolkit's ``(r, g, b[, a])`` 0-255
tuples (an ``ImU32`` in a port becomes one of those). Angles are radians.
Rounded corners are corner fans; a Bezier is flattened to a polyline. Nothing
here keeps state beyond the path buffer and the clip stack it delegates.
"""
from __future__ import annotations

import math
from typing import Sequence

from .painter import (
    ALIGN_LEFT,
    ALIGN_VCENTER,
    Colour,
    Painter,
    fill_circle,
    fill_convex,
    line,
    polyline,
    stroke_circle,
)

__all__ = ["DrawList", "DRAW_FLAGS_CLOSED", "DRAW_FLAGS_ROUND_CORNERS_ALL", "DRAW_FLAGS_ROUND_CORNERS_NONE"]

DRAW_FLAGS_CLOSED = 1 << 0
DRAW_FLAGS_ROUND_CORNERS_TOP_LEFT = 1 << 4
DRAW_FLAGS_ROUND_CORNERS_TOP_RIGHT = 1 << 5
DRAW_FLAGS_ROUND_CORNERS_BOTTOM_LEFT = 1 << 6
DRAW_FLAGS_ROUND_CORNERS_BOTTOM_RIGHT = 1 << 7
DRAW_FLAGS_ROUND_CORNERS_NONE = 1 << 8
DRAW_FLAGS_ROUND_CORNERS_ALL = (
    DRAW_FLAGS_ROUND_CORNERS_TOP_LEFT | DRAW_FLAGS_ROUND_CORNERS_TOP_RIGHT
    | DRAW_FLAGS_ROUND_CORNERS_BOTTOM_LEFT | DRAW_FLAGS_ROUND_CORNERS_BOTTOM_RIGHT
)

Point = tuple[float, float]


def _rounded_rect_points(x0, y0, x1, y1, rounding, flags, segments) -> list[Point]:
    """The outline of a rectangle with rounded corners, clockwise from the top-left arc."""
    r = max(0.0, min(float(rounding), (x1 - x0) * 0.5, (y1 - y0) * 0.5))
    if r <= 0.0 or (flags & DRAW_FLAGS_ROUND_CORNERS_NONE):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if not (flags & DRAW_FLAGS_ROUND_CORNERS_ALL):
        flags |= DRAW_FLAGS_ROUND_CORNERS_ALL
    n = max(int(segments), 3)

    def arc(cx, cy, a0, a1):
        return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

    pts: list[Point] = []
    if flags & DRAW_FLAGS_ROUND_CORNERS_TOP_LEFT:
        pts += arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
    else:
        pts.append((x0, y0))
    if flags & DRAW_FLAGS_ROUND_CORNERS_TOP_RIGHT:
        pts += arc(x1 - r, y0 + r, 1.5 * math.pi, 2.0 * math.pi)
    else:
        pts.append((x1, y0))
    if flags & DRAW_FLAGS_ROUND_CORNERS_BOTTOM_RIGHT:
        pts += arc(x1 - r, y1 - r, 0.0, 0.5 * math.pi)
    else:
        pts.append((x1, y1))
    if flags & DRAW_FLAGS_ROUND_CORNERS_BOTTOM_LEFT:
        pts += arc(x0 + r, y1 - r, 0.5 * math.pi, math.pi)
    else:
        pts.append((x0, y1))
    return pts


def _bezier_cubic(p1, p2, p3, p4, segments) -> list[Point]:
    n = max(int(segments), 1)
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        w1, w2, w3, w4 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append((w1 * p1[0] + w2 * p2[0] + w3 * p3[0] + w4 * p4[0],
                    w1 * p1[1] + w2 * p2[1] + w3 * p3[1] + w4 * p4[1]))
    return out


def _bezier_quadratic(p1, p2, p3, segments) -> list[Point]:
    n = max(int(segments), 1)
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        w1, w2, w3 = u * u, 2 * u * t, t * t
        out.append((w1 * p1[0] + w2 * p2[0] + w3 * p3[0], w1 * p1[1] + w2 * p2[1] + w3 * p3[1]))
    return out


class DrawList:
    """``ImDrawList`` over a Painter. Create one per draw call: ``dl = DrawList(p)``."""

    def __init__(self, painter: Painter) -> None:
        self.p = painter
        self._path: list[Point] = []
        self._clip_depth = 0
        #: Segments per rounded corner / per circle when the caller passes 0.
        self.circle_segments = 24
        self.curve_segments = 16
        # Images, channels, callbacks and the vertex level -- see the block
        # below the class.
        self._textures: list = []
        self._channels: list = []
        self._channel_index = 0
        self._channel_target = painter
        self._commands: list = []
        self._vtx: list = []
        self._idx: list = []
        self._idx_wanted = 0

    # -- primitives -------------------------------------------------------- #
    def add_line(self, p1: Point, p2: Point, col: Colour, thickness: float = 1.0) -> None:
        line(self.p, p1[0], p1[1], p2[0], p2[1], thickness, col)

    def add_rect(self, p_min: Point, p_max: Point, col: Colour, rounding: float = 0.0,
                 flags: int = 0, thickness: float = 1.0) -> None:
        x0, y0 = p_min
        x1, y1 = p_max
        if rounding <= 0.0 and thickness <= 1.0:
            self.p.stroke_rect(x0, y0, x1 - x0, y1 - y0, col)
            return
        pts = _rounded_rect_points(x0, y0, x1, y1, rounding, flags, self.circle_segments // 4)
        polyline(self.p, pts, thickness, col, closed=True)

    def add_rect_filled(self, p_min: Point, p_max: Point, col: Colour, rounding: float = 0.0,
                        flags: int = 0) -> None:
        x0, y0 = p_min
        x1, y1 = p_max
        if rounding <= 0.0:
            self.p.fill_rect(x0, y0, x1 - x0, y1 - y0, col)
            return
        fill_convex(self.p, _rounded_rect_points(x0, y0, x1, y1, rounding, flags, self.circle_segments // 4), col)

    def add_rect_filled_multi_color(self, p_min: Point, p_max: Point, col_upr_left: Colour,
                                    col_upr_right: Colour, col_bot_right: Colour, col_bot_left: Colour) -> None:
        # The painter's gradient runs left to right; the vertical pair is folded in.
        x0, y0 = p_min
        x1, y1 = p_max
        self.p.gradient_rect(x0, y0, x1 - x0, y1 - y0, [col_upr_left, col_upr_right])

    def add_quad(self, p1, p2, p3, p4, col: Colour, thickness: float = 1.0) -> None:
        polyline(self.p, [p1, p2, p3, p4], thickness, col, closed=True)

    def add_quad_filled(self, p1, p2, p3, p4, col: Colour) -> None:
        fill_convex(self.p, [p1, p2, p3, p4], col)

    def add_triangle(self, p1, p2, p3, col: Colour, thickness: float = 1.0) -> None:
        polyline(self.p, [p1, p2, p3], thickness, col, closed=True)

    def add_triangle_filled(self, p1, p2, p3, col: Colour) -> None:
        self.p.fill_triangle(p1, p2, p3, col)

    def add_circle(self, center: Point, radius: float, col: Colour, num_segments: int = 0,
                   thickness: float = 1.0) -> None:
        stroke_circle(self.p, center[0], center[1], radius, thickness, col, num_segments or self.circle_segments)

    def add_circle_filled(self, center: Point, radius: float, col: Colour, num_segments: int = 0) -> None:
        fill_circle(self.p, center[0], center[1], radius, col, num_segments or self.circle_segments)

    def add_ngon(self, center: Point, radius: float, col: Colour, num_segments: int, thickness: float = 1.0) -> None:
        stroke_circle(self.p, center[0], center[1], radius, thickness, col, num_segments)

    def add_ngon_filled(self, center: Point, radius: float, col: Colour, num_segments: int) -> None:
        fill_circle(self.p, center[0], center[1], radius, col, num_segments)

    def add_polyline(self, points: Sequence[Point], col: Colour, flags: int = 0, thickness: float = 1.0) -> None:
        polyline(self.p, points, thickness, col, closed=bool(flags & DRAW_FLAGS_CLOSED))

    def add_convex_poly_filled(self, points: Sequence[Point], col: Colour) -> None:
        fill_convex(self.p, points, col)

    def add_bezier_cubic(self, p1, p2, p3, p4, col: Colour, thickness: float = 1.0, num_segments: int = 0) -> None:
        polyline(self.p, _bezier_cubic(p1, p2, p3, p4, num_segments or self.curve_segments), thickness, col)

    def add_bezier_quadratic(self, p1, p2, p3, col: Colour, thickness: float = 1.0, num_segments: int = 0) -> None:
        polyline(self.p, _bezier_quadratic(p1, p2, p3, num_segments or self.curve_segments), thickness, col)

    def add_text(self, pos: Point, col: Colour, text: str, bold: bool = False) -> None:
        w = self.p.text_width(text)
        h = self.p.line_height()
        self.p.text(pos[0], pos[1], w, h, ALIGN_LEFT | ALIGN_VCENTER, text, col, bold)

    def calc_text_size(self, text: str) -> Point:
        return (self.p.text_width(text), self.p.line_height())

    # -- path API ----------------------------------------------------------- #
    def path_clear(self) -> None:
        self._path.clear()

    def path_line_to(self, pos: Point) -> None:
        self._path.append((float(pos[0]), float(pos[1])))

    def path_arc_to(self, center: Point, radius: float, a_min: float, a_max: float, num_segments: int = 0) -> None:
        n = max(int(num_segments or self.circle_segments), 1)
        for i in range(n + 1):
            a = a_min + (a_max - a_min) * i / n
            self._path.append((center[0] + radius * math.cos(a), center[1] + radius * math.sin(a)))

    def path_bezier_cubic_curve_to(self, p2, p3, p4, num_segments: int = 0) -> None:
        start = self._path[-1] if self._path else p2
        self._path.extend(_bezier_cubic(start, p2, p3, p4, num_segments or self.curve_segments)[1:])

    def path_bezier_quadratic_curve_to(self, p2, p3, num_segments: int = 0) -> None:
        start = self._path[-1] if self._path else p2
        self._path.extend(_bezier_quadratic(start, p2, p3, num_segments or self.curve_segments)[1:])

    def path_rect(self, rect_min: Point, rect_max: Point, rounding: float = 0.0, flags: int = 0) -> None:
        self._path.extend(_rounded_rect_points(rect_min[0], rect_min[1], rect_max[0], rect_max[1],
                                               rounding, flags, self.circle_segments // 4))

    def path_stroke(self, col: Colour, flags: int = 0, thickness: float = 1.0) -> None:
        polyline(self.p, self._path, thickness, col, closed=bool(flags & DRAW_FLAGS_CLOSED))
        self._path.clear()

    def path_fill_convex(self, col: Colour) -> None:
        fill_convex(self.p, self._path, col)
        self._path.clear()

    # -- clipping ----------------------------------------------------------- #
    def push_clip_rect(self, clip_min: Point, clip_max: Point, intersect_with_current: bool = False) -> None:
        self.p.push_clip(clip_min[0], clip_min[1], clip_max[0] - clip_min[0], clip_max[1] - clip_min[1])
        self._clip_depth += 1

    def pop_clip_rect(self) -> None:
        if self._clip_depth > 0:
            self.p.pop_clip()
            self._clip_depth -= 1

    def add_ellipse(self, centre, radius, col, rot=0.0, num_segments=0,
                     thickness=1.0):
        """``AddEllipse``."""
        import math

        segments = num_segments or self.circle_segments
        points = _ellipse_points(centre, radius, rot, 0.0, 2.0 * math.pi, segments)
        self.add_polyline(points, col, 0, thickness)

    def add_ellipse_filled(self, centre, radius, col, rot=0.0, num_segments=0):
        """``AddEllipseFilled``."""
        import math

        segments = num_segments or self.circle_segments
        points = _ellipse_points(centre, radius, rot, 0.0, 2.0 * math.pi, segments)
        self.add_convex_poly_filled(points, col)

    def path_arc_to_fast(self, centre, radius, a_min_of_12, a_max_of_12):
        """``PathArcToFast``: twelfths of a turn, as the reference indexes them."""
        import math

        self.path_arc_to(centre, radius,
                         a_min_of_12 * math.pi / 6.0, a_max_of_12 * math.pi / 6.0)

    def path_elliptical_arc_to(self, centre, radius, rot, a_min, a_max,
                                num_segments=0):
        """``PathEllipticalArcTo``."""
        segments = num_segments or self.circle_segments
        self._path.extend(_ellipse_points(centre, radius, rot, a_min, a_max, segments))

    def path_line_to_merge_duplicate(self, pos):
        """``PathLineToMergeDuplicate``: skip a point identical to the last."""
        if self._path and self._path[-1] == tuple(pos):
            return
        self.path_line_to(pos)

    def add_concave_poly_filled(self, points, col):
        """``AddConcavePolyFilled``, by ear clipping.

        The reference has a dedicated path; this is the same result by the
        textbook method, which a painter with only triangles can do.
        """
        poly = [tuple(p) for p in points]
        if len(poly) < 3:
            return

        def area(p):
            return sum((p[i][0] * p[(i + 1) % len(p)][1]
                        - p[(i + 1) % len(p)][0] * p[i][1]) for i in range(len(p))) * 0.5

        def inside(a, b, c, p):
            d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
            d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
            d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
            return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

        if area(poly) < 0:
            poly.reverse()
        guard = 0
        while len(poly) > 3 and guard < 10000:
            guard += 1
            for i in range(len(poly)):
                a, b, c = poly[i - 2], poly[i - 1], poly[i]
                cross = ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
                if cross <= 0:
                    continue
                if any(inside(a, b, c, p) for p in poly if p not in (a, b, c)):
                    continue
                self.p.fill_triangle(a, b, c, col)
                poly.pop(i - 1)
                break
            else:
                break
        if len(poly) == 3:
            self.p.fill_triangle(poly[0], poly[1], poly[2], col)

    def path_fill_concave(self, col):
        """``PathFillConcave``."""
        points, self._path = self._path, []
        self.add_concave_poly_filled(points, col)

    def add_line_h(self, p, width, col, thickness=1.0):
        """``AddLineH``: a horizontal run, which needs no general line."""
        self.p.fill_rect(p[0], p[1] - thickness * 0.5, width, thickness, col)

    def add_line_v(self, p, height, col, thickness=1.0):
        """``AddLineV``."""
        self.p.fill_rect(p[0] - thickness * 0.5, p[1], thickness, height, col)

    def push_clip_rect_full_screen(self):
        """``PushClipRectFullScreen``."""
        self.push_clip_rect((-8192.0, -8192.0), (8192.0, 8192.0), False)

    def get_clip_rect_min(self):
        return getattr(self, "_clip_min", (-8192.0, -8192.0))

    def get_clip_rect_max(self):
        return getattr(self, "_clip_max", (8192.0, 8192.0))

# --------------------------------------------------------------------------- #
#
# What is *not* here is what a painter has no operation for: images and
# textures (`AddImage`, `PushTexture`), the vertex-level `Prim*` writers, the
# channel splitter and `AddCallback`. Those are a renderer's business, and a
# name that exists but does nothing is worse for a port than one that is
# missing -- the port compiles and the picture is wrong.


    def add_image(self, handle, p_min, p_max, uv_min=(0.0, 0.0),
                      uv_max=(1.0, 1.0), col=(255, 255, 255, 255)) -> None:
        """``AddImage``."""
        from .painter import image as _image

        _image(self.p, p_min[0], p_min[1], p_max[0] - p_min[0], p_max[1] - p_min[1],
               handle, uv_min, uv_max, col)

    def add_image_quad(self, handle, p1, p2, p3, p4, uv1=(0.0, 0.0),
                           uv2=(1.0, 0.0), uv3=(1.0, 1.0), uv4=(0.0, 1.0),
                           col=(255, 255, 255, 255)) -> None:
        """``AddImageQuad``: the quad's bounding box, which is all a painter has."""
        xs = [p1[0], p2[0], p3[0], p4[0]]
        ys = [p1[1], p2[1], p3[1], p4[1]]
        self.add_image(handle, (min(xs), min(ys)), (max(xs), max(ys)), uv1, uv3, col)

    def add_image_rounded(self, handle, p_min, p_max, uv_min=(0.0, 0.0),
                              uv_max=(1.0, 1.0), col=(255, 255, 255, 255),
                              rounding: float = 0.0, flags: int = 0) -> None:
        """``AddImageRounded``."""
        self.add_image(handle, p_min, p_max, uv_min, uv_max, col)

    def push_texture(self, texture) -> None:
        """``PushTexture``: what later image calls default to."""
        self._textures.append(texture)

    def pop_texture(self) -> None:
        if self._textures:
            self._textures.pop()

    def push_texture_id(self, texture) -> None:
        self.push_texture(texture)

    def pop_texture_id(self) -> None:
        self.pop_texture()

    def channels_split(self, count: int) -> None:
        """``ChannelsSplit``: draw out of order, merge back in order."""
        self._channel_target = self.p
        self._channels = [_Deferred(self.p) for _ in range(max(int(count), 1))]
        self.channels_set_current(0)

    def channels_set_current(self, index: int) -> None:
        """``ChannelsSetCurrent``."""
        if not self._channels:
            return
        self._channel_index = max(0, min(int(index), len(self._channels) - 1))
        self.p = self._channels[self._channel_index]

    def channels_merge(self) -> None:
        """``ChannelsMerge``: replay the channels in order, on to the painter."""
        if not self._channels:
            return
        self.p = self._channel_target
        for channel in self._channels:
            channel.replay(self.p)
        self._channels = []
        self._channel_index = 0

    def add_callback(self, callback, user_data=None) -> None:
        """``AddCallback``: run it in draw order, with the painter to hand."""
        self._commands.append(("callback", callback, user_data))
        callback(self, user_data)

    def add_draw_cmd(self) -> None:
        """``AddDrawCmd``: a boundary in the command list."""
        self._commands.append(("cmd", None, None))

    def clone_output(self):
        """``CloneOutput``: the commands recorded so far, detached."""
        clone = DrawList(self.p)
        clone._commands = list(self._commands)
        return clone

    def get_draw_data(self):
        """The commands this list has recorded. ``ImGui::GetDrawData``'s content."""
        return list(self._commands)

    def prim_reserve(self, idx_count: int, vtx_count: int) -> None:
        """``PrimReserve``: room for a run of hand-written geometry."""
        self._vtx = []
        self._idx = []
        self._idx_wanted = int(idx_count)

    def prim_unreserve(self, idx_count: int, vtx_count: int) -> None:
        self._vtx, self._idx, self._idx_wanted = [], [], 0

    def prim_write_vtx(self, pos, uv=(0.0, 0.0), col=(255, 255, 255, 255)) -> None:
        """``PrimWriteVtx``."""
        self._vtx.append((tuple(pos), tuple(uv), tuple(col)))

    def prim_write_idx(self, index: int) -> None:
        """``PrimWriteIdx``: every third index completes a triangle, and draws it."""
        self._idx.append(int(index))
        if len(self._idx) % 3:
            return
        a, b, c = self._idx[-3:]
        if max(a, b, c) < len(self._vtx):
            colour = self._vtx[a][2]
            self.p.fill_triangle(self._vtx[a][0], self._vtx[b][0], self._vtx[c][0],
                                 colour)

    def prim_vtx(self, pos, uv=(0.0, 0.0), col=(255, 255, 255, 255)) -> None:
        """``PrimVtx``: a vertex and its index, as the reference pairs them.

        The vertex first: the index refers to it, and a triangle completed by an
        index whose vertex has not been written yet draws nothing.
        """
        self.prim_write_vtx(pos, uv, col)
        self.prim_write_idx(len(self._vtx) - 1)

    def prim_rect(self, a, c, col) -> None:
        """``PrimRect``."""
        self.add_rect_filled(a, c, col)

    def prim_rect_uv(self, a, c, uv_a, uv_c, col) -> None:
        self.add_rect_filled(a, c, col)

    def prim_quad_uv(self, a, b, c, d, uv_a, uv_b, uv_c, uv_d, col) -> None:
        self.add_quad_filled(a, b, c, d, col)


def _ellipse_points(centre, radius, rot, a_min, a_max, segments):
    import math

    out = []
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    for index in range(segments + 1):
        a = a_min + (a_max - a_min) * index / max(segments, 1)
        x, y = math.cos(a) * radius[0], math.sin(a) * radius[1]
        out.append((centre[0] + x * cos_r - y * sin_r,
                    centre[1] + x * sin_r + y * cos_r))
    return out

# --------------------------------------------------------------------------- #
# Images, channels, callbacks and the vertex level
# --------------------------------------------------------------------------- #
#
# The parts of `ImDrawList` that are about *how* drawing reaches the screen
# rather than what is drawn. cmtk emits painter calls instead of vertices, so
# each is implemented in those terms:
#
# * images go to the painter's optional `image` operation (`painter.image`),
#   which falls back to a tinted rectangle so a port still runs;
# * channels are deferral -- calls made on a channel are recorded and replayed
#   in channel order on merge, which is exactly what the reference's splitter
#   does to its command buffer;
# * `Prim*` fills a small vertex buffer and emits the triangles when the
#   indices arrive, so a port that writes vertices by hand still draws;
# * `AddCallback` keeps the callback and runs it in order with the rest.


class _Deferred:
    """A painter that writes calls down instead of making them.

    Two of the painter's operations are **questions**, not commands:
    ``text_width`` and ``line_height`` return a measurement the caller lays out
    with. Recording those the way the drawing calls are recorded returns
    ``None``, and ``None`` does not raise where it is produced -- it raises
    further along, inside whatever arithmetic the layout was doing, or worse it
    is compared and silently makes every row zero-height. So they are forwarded
    to the real painter and answered now.

    Parameters
    ----------
    painter : object
        The painter the channel will eventually replay onto, and the one that
        answers measurements in the meantime.
    """

    #: Painter operations that return an answer rather than drawing something.
    #: :data:`cmtk.painter.REQUIRED_OPERATIONS` lists them last for the same
    #: reason. ``set_font`` is here too: it is a command, but a channel that
    #: swallowed it would measure the following text in the wrong font.
    _QUERIES: frozenset = frozenset({"text_width", "line_height", "set_font"})

    def __init__(self, painter=None) -> None:
        self.calls: list[tuple] = []
        self._painter = painter

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if self._painter is not None:
            if name in self._QUERIES:
                return getattr(self._painter, name)
            # Only claim what the real painter has. A bare "record anything"
            # __getattr__ makes ``hasattr`` answer True for every name, and the
            # helpers in painter.py ask exactly that to decide whether to use a
            # host's fast path (``polyline``, ``fill_convex``, ``fill_triangles``)
            # or decompose into the required operations. Claiming a fast path the
            # host does not have records a call that cannot be replayed, and the
            # AttributeError surfaces at *merge* time -- nowhere near the widget
            # that drew it.
            getattr(self._painter, name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record

    def replay(self, painter) -> None:
        """Make every recorded call, in order, on `painter`.

        Parameters
        ----------
        painter : object
            The painter to draw onto.
        """
        for name, args, kwargs in self.calls:
            getattr(painter, name)(*args, **kwargs)
