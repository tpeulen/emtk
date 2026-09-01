"""im_gradient: auto-ported from ImGradient.h, ImGradient.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

def im_clamp(v, mn, mx):
    """ImClamp."""
    return max(mn, min(mx, v))

def im_lerp(a, b, t):
    """ImLerp: blend a toward b by t. C++ overloads this for
    scalars and ImVec2/4; a tuple is blended component-wise."""
    if isinstance(a, tuple):
        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t

def draw_point(draw_list, color, size, editing, pos):
    """DrawPoint()."""
    io = im.get_io()
    p1 = im_lerp(pos, ((pos[0] + size[0] - size[1], pos[1] + 0.), 0.0), color[3]) + (3, 3)
    p2 = im_lerp((pos[0] + size[1], pos[1] + size[1]), ((pos[0] + size[0], pos[1] + size[1]), 0.0), color[3]) - (3, 3)
    rc = ImRect(p1, p2)
    color = (color[0], 1.)
    draw_list.add_rect_filled(p1, p2, color)
    if editing:
        draw_list.add_rect(p1, p2, 0xFFFFFFFF, 2., 15, 2.5)
    else:
        if rc.contains(io.mouse_pos):
            if io.mouse_clicked[0]:
                return 2
            return 1
    return 0

def edit(delegate, size, value):
    """Edit()."""
    # TODO(autoport): BeginChild: cmtk takes a box anchored at the cursor; the id/border/flags are dropped
    ret = False
    io = im.get_io()
    im.push_style_var(im.StyleVar.FRAME_PADDING, (0, 0))
    im.begin_child((*im.get_cursor_screen_pos(), size[0], size[1]))
    draw_list = im.get_window_draw_list()
    offset = im.get_cursor_screen_pos()
    pts = delegate.get_points()
    currentSelection = -1
    movingPt = -1
    if currentSelection >= int(delegate.get_point_count()):
        currentSelection = -1
    if movingPt != -1:
        current = pts[movingPt]
        current[3] = current[3] + io.mouse_delta[0] / size[0]
        current[3] = im_clamp(current[3], 0., 1.)
        delegate.edit_point(movingPt, current)
        ret = True
        if not io.mouse_down[0]:
            movingPt = -1
    for i in range(int(0), int(delegate.get_point_count())):
        ptSel = draw_point(draw_list, pts[i], size, i == currentSelection, offset)
        if ptSel == 2:
            currentSelection = int(i)
            ret = True
        if ptSel == 1  and  io.mouse_down[0]  and  movingPt == -1:
            movingPt = int(i)
    rc = ImRect(offset, offset + size)
    if rc.contains(io.mouse_pos)  and  io.mouse_double_clicked[0]:
        t = (io.mouse_pos[0] - offset[0]) / size[0]
        delegate.add_point(delegate.get_point(t))
        ret = True
    im.end_child()
    im.pop_style_var()
    value = currentSelection
    return ret, value
