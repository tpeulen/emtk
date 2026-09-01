"""arc_progress_bar: auto-ported from arc_progress_bar.hpp, arc_progress_bar.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im
def _get_style_color(color_id):
    """_GetStyleColor()."""
    assert(color_id >= 0  and  color_id < im.Col.COUNT)
    if color_id < 0  or  color_id >= im.Col.COUNT:
        return DEFAULT_FOREGROUND_COLOR
    return im.get_style().colors[color_id]

def _draw_arc(size, max_angle_factor, percentage, thickness, pos):
    """_DrawArc()."""
    draw_list = im.get_window_draw_list()
    x = pos[0]
    y = pos[1]
    ONE_DIV_360f = 1.0 / 360.0
    a_min_factor = 0.0
    a_max_factor = 0.0
    a_max_factor_100percentage = 0.0
    a_min_factor = -1.5 + ((360 - max_angle_factor) * ONE_DIV_360f)
    a_max_factor_100percentage = (a_min_factor + 1.0) * -1.0
    a_factor_delta = (a_max_factor_100percentage - a_min_factor) * (percentage * 0.01)
    a_max_factor = a_min_factor + a_factor_delta
    draw_list.path_arc_to((x + size * 0.5, y + size * 0.5), size * 0.5, 3.141592 * a_min_factor, 3.141592 * a_max_factor_100percentage)
    draw_list.path_stroke(_get_style_color(im.Col.BUTTON), im.DrawFlags.NONE, thickness)
    draw_list.path_arc_to((x + size * 0.5, y + size * 0.5), size * 0.5, 3.141592 * a_min_factor, 3.141592 * a_max_factor)
    draw_list.path_stroke(_get_style_color(im.Col.BUTTON_ACTIVE), im.DrawFlags.NONE, thickness)

def progress_bar_arc(size, max_angle_factor, percentage, pos, thickness):
    """ImGuiExt::ProgressBarArc()."""
    window_pos = im.get_window_pos()
    _draw_arc(size, max_angle_factor, percentage, thickness, (pos[0] + window_pos[0], pos[1] + window_pos[1]))

def progress_bar_arc(size, max_angle_factor, percentage, thickness):
    """ImGuiExt::ProgressBarArc()."""
    pos = im.get_cursor_screen_pos()
    im.dummy(size, size)
    _draw_arc(size, max_angle_factor, percentage, thickness, pos)
