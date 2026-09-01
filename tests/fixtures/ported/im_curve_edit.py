"""im_curve_edit: auto-ported from ImCurveEdit.h, ImCurveEdit.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

from enum import IntFlag

class CurveType(IntFlag):
    """CurveType, from ImCurveEdit.h."""
    curve_none = 0
    curve_discrete = 1
    curve_linear = 2
    curve_smooth = 3
    curve_bezier = 4

def im_clamp(v, mn, mx):
    """ImClamp."""
    return max(mn, min(mx, v))

def im_lerp(a, b, t):
    """ImLerp: blend a toward b by t. C++ overloads this for
    scalars and ImVec2/4; a tuple is blended component-wise."""
    if isinstance(a, tuple):
        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t

class Delegate:
    """Delegate, from ImCurveEdit.h."""

    def is_visible(self, _arg0):
        """IsVisible()."""
        return True

    def get_curve_type(self, _arg0):
        """GetCurveType()."""
        return CurveLinear

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_edit(self, _arg0):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def end_edit(self):
    pass
def smoothstep(edge0, edge1, x):
    """smoothstep()."""
    x = im_clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return x * x * (3 - 2 * x)

def distance(x, y, x1, y1, x2, y2):
    """distance()."""
    A = x - x1
    B = y - y1
    C = x2 - x1
    D = y2 - y1
    dot = A * C + B * D
    len_sq = C * C + D * D
    param = -1.
    if len_sq > FLT_EPSILON:
        param = dot / len_sq
    xx = 0.0
    yy = 0.0
    if param < 0.:
        xx = x1
        yy = y1
    elif param > 1.:
        xx = x2
        yy = y2
    else:
        xx = x1 + param * C
        yy = y1 + param * D
    dx = x - xx
    dy = y - yy
    return math.sqrt(dx * dx + dy * dy)

def draw_point(draw_list, pos, size, offset, edited):
    """DrawPoint()."""
    ret = 0
    io = im.get_io()
    localOffsets = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    offsets = [None] * (4)
    for i in range(int(0), int(4)):
        offsets[i] = (localOffsets[0] + pos[0] * size[0], localOffsets[1] + pos[1] * size[1])[i] * 4.5 + offset
    center = (offset[0] + pos[0] * size[0], offset[1] + pos[1] * size[1])
# TODO(autoport): hand-translate (the rules mangled this line):     const ImRect anchor((center[0] - 5, center[1] - 5), (center[0] + 5, center[1] + 5))
    pass  # TODO(autoport): body of the line above
    draw_list.add_convex_poly_filled(offsets, 4, 0xFF000000)
    if anchor.contains(io.mouse_pos):
        ret = 1
        if io.mouse_down[0]:
            ret = 2
    if edited:
        draw_list.add_polyline(offsets, 4, 0xFFFFFFFF, True, 3.0)
    elif ret:
        draw_list.add_polyline(offsets, 4, 0xFF80B0FF, True, 2.0)
    else:
        return ret

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def edit(delegate, size, id, clippingRect, selectedPoints):
pass