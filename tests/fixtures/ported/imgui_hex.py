"""imgui_hex: auto-ported from imgui_hex.h, imgui_hex.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

from enum import IntFlag

class HexEditorHighlightFlags(IntFlag):
    """ImGuiHexEditorHighlightFlags, from imgui_hex.h."""
    NONE = 0

class HexEditorClipboardFlags(IntFlag):
    """ImGuiHexEditorClipboardFlags, from imgui_hex.h."""
    NONE = 0

def half_byte_to_printable(half_byte, lower):
    """HalfByteToPrintable()."""
    assert(not (half_byte & 0xf0))
    return ('0' + half_byte if half_byte <= 9 else (('a' if lower else 'A')) + half_byte - 10)

def has_ascii_representation(byte):
    """HasAsciiRepresentation()."""
    return (byte >= '!'  and  byte <= '~')

def calc_bytes_per_line(bytes_avail_x, byte_size, spacing, show_ascii, char_size, separators):
    """CalcBytesPerLine()."""
    byte_width = byte_size[0] + spacing[0] + ((char_size[0] if show_ascii else 0.))
    bytes_per_line = int(bytes_avail_x / byte_width)
    bytes_per_line = (1 if bytes_per_line <= 0 else bytes_per_line)
    actual_separators = (int(bytes_per_line / separators) if separators > 0 else 0)
    if actual_separators != 0  and  separators > 0  and  bytes_per_line > actual_separators  and  (bytes_per_line - 1) % actual_separators == 0:
        actual_separators -= 1
    return (calc_bytes_per_line(bytes_avail_x - (actual_separators * spacing[0]), byte_size, spacing, show_ascii, char_size, 0) if separators > 0 else bytes_per_line)

def calc_contrast_color(color):
    """CalcContrastColor()."""
    l = (0.299 * (color.value[2] * 255.) + 0.587 * (color.value[1] * 255.) + 0.114 * (color.value[0] * 255.)) / 255.
    c = (0 if l > 0.5 else 255)
    return im.col32(c, c, c, 255)

def range_range_intersection(a_min, a_max, b_min, b_max, value, out_max):
    """RangeRangeIntersection()."""
    # TODO(autoport): second out-parameter(s) out_max: the tuple carries only out_min
    if a_max < b_min  or  b_max < a_min:
        return False, value
    value = max(a_min, b_min)
    out_max = min(a_max, b_max)
    if value <=out_max:
        return True, value
    return False, value

def render_rect_corner_calc_rounding(ra, rb, value):
    """RenderRectCornerCalcRounding()."""
    value = min(value, abs(rb[0] - ra[0]) * 0.5)
    value = min(value, abs(rb[1] - ra[1]) * 0.5)

def render_top_left_corner_rect(draw_list, a, b, color, rounding):
    """RenderTopLeftCornerRect()."""
    ra = [a[0] + 0.5, a[1] + 0.5]
    rb = [b[0], b[1]]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(( ra[0], rb[1] ), 0, 3, 6)
    draw_list.path_arc_to_fast(( ra[0] + rounding, ra[1] + rounding ), rounding, 6, 9)
    draw_list.path_arc_to_fast(( rb[0] , ra[1] ), 0, 9, 12)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_bottom_right_corner_rect(draw_list, a, b, color, rounding):
    """RenderBottomRightCornerRect()."""
    ra = [a[0], a[1] + 0.5]
    rb = [b[0] - 0.5, b[1] + 0.5]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(( rb[0], ra[1] ), 0, 9, 12)
    draw_list.path_arc_to_fast(( rb[0] - rounding, rb[1] - rounding ), rounding, 0, 3)
    draw_list.path_arc_to_fast(( ra[0], rb[1] ), 0, 3, 6)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_top_right_corner_rect(draw_list, a, b, color, rounding):
    """RenderTopRightCornerRect()."""
    ra = [a[0] + 0.5, a[1] + 0.5]
    rb = [b[0] - 0.5, b[1]]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(ra, 0., 6, 9)
    draw_list.path_arc_to_fast(( rb[0] - rounding, ra[1] + rounding ), rounding, 9, 12)
    draw_list.path_arc_to_fast(rb, 0., 0, 3)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_bottom_left_corner_rect(draw_list, a, b, color, rounding):
    """RenderBottomLeftCornerRect()."""
    ra = [a[0] + 0.5, a[1] + 0.5]
    rb = [b[0] + 0.5, b[1] + 0.5]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(( rb[0], rb[1] ), 0., 0, 3)
    draw_list.path_arc_to_fast(( ra[0] + rounding, rb[1] - rounding ), rounding, 3, 6)
    draw_list.path_arc_to_fast(( ra[0], ra[1] ), 0., 9, 12)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_bottom_corner_rect(draw_list, a, b, color, rounding):
    """RenderBottomCornerRect()."""
    ra = [a[0] + 0.5, a[1] + 0.5]
    rb = [b[0] + 0.5, b[1] + 0.5]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(( rb[0], ra[1] ), 0., 0, 3)
    draw_list.path_arc_to_fast(( rb[0] - rounding, rb[1] - rounding ), rounding, 0, 3)
    draw_list.path_arc_to_fast(( ra[0] + rounding, rb[1] - rounding ), rounding, 3, 6)
    draw_list.path_arc_to_fast(( ra[0], ra[1] ), 0., 9, 12)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_top_corner_rect(draw_list, a, b, color, rounding):
    """RenderTopCornerRect()."""
    ra = [a[0] + 0.5, a[1] + 0.5]
    rb = [b[0] - 0.5, b[1] + 0.5]
    _ret, rounding = render_rect_corner_calc_rounding(ra, rb, rounding)
    draw_list.path_arc_to_fast(( ra[0], rb[1] ), 0., 3, 6)
    draw_list.path_arc_to_fast(( ra[0] + rounding, ra[1] + rounding ), rounding, 6, 9)
    draw_list.path_arc_to_fast(( rb[0] - rounding, ra[1] + rounding ), rounding, 9, 12)
    draw_list.path_arc_to_fast(( rb[0] , rb[1] ), 0., 0, 3)
    draw_list.path_stroke(color, im.DrawFlags.NONE, 1.)

def render_byte_decorations(draw_list, bb, bg_color, flags, border_color, rounding, offset, range_min, range_max, bytes_per_line, i, line_base):
    """RenderByteDecorations()."""
    has_border = flags & HexEditorHighlightFlags.BORDER
    if not has_border:
        draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)
        return
    if range_min == range_max:
        draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding)
        draw_list.add_rect(bb.min, bb.max, border_color, rounding)
        return
    start_line = range_min / bytes_per_line
    end_line = range_max / bytes_per_line
    current_line = line_base / bytes_per_line
    is_start_line = start_line == (line_base / bytes_per_line)
    is_end_line = end_line == (line_base / bytes_per_line)
    is_last_byte = i == (bytes_per_line - 1)
    rendered_bg = False
    if offset == range_min:
        if not is_last_byte:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_TOP_LEFT)
            render_top_left_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            if start_line == end_line:
                draw_list.add_line(( bb.min[0], bb.max[1] ), ( bb.max[0], bb.max[1] ), border_color)
        else:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_TOP)
            render_top_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
        rendered_bg = True
    elif i == 0:
        if is_end_line:
            if offset == range_max:
                draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_BOTTOM)
                render_bottom_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            else:
                draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_BOTTOM_LEFT)
                render_bottom_left_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            rendered_bg = True
        elif current_line == start_line + 1  and  (range_min % bytes_per_line) != 0:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_TOP_LEFT)
            render_top_left_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            rendered_bg = True
        else:
            if not rendered_bg:
                draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)
                rendered_bg = True
            draw_list.add_line(( bb.min[0], bb.min[1] ), ( bb.min[0], bb.max[1] ), border_color)
    if i != 0  and  offset == range_max:
        if start_line == end_line:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_TOP_RIGHT)
            render_top_right_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            draw_list.add_line(( bb.min[0], bb.max[1] ), ( bb.max[0], bb.max[1] ), border_color)
        else:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_BOTTOM_RIGHT)
            render_bottom_right_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
        rendered_bg = True
    elif is_last_byte  and  offset != range_min:
        if is_start_line:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_TOP_RIGHT)
            render_top_right_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            rendered_bg = True
        elif current_line == end_line - 1  and  (range_max % bytes_per_line) != bytes_per_line - 1:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, rounding, im.DrawFlags.ROUND_CORNERS_BOTTOM_RIGHT)
            render_bottom_right_corner_rect(draw_list, bb.min, bb.max, border_color, rounding)
            rendered_bg = True
        else:
            if not rendered_bg:
                draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)
                rendered_bg = True
            draw_list.add_line(( bb.max[0] - 1., bb.min[1] ), ( bb.max[0] - 1., bb.max[1] ), border_color)
    if (is_start_line  and  offset != range_min  and  not is_last_byte  and  offset != range_max)  or  (current_line == start_line + 1  and  (i < (range_min % bytes_per_line)  and  i != 0)):
        if not rendered_bg:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)
            rendered_bg = True
        draw_list.add_line(( bb.min[0], bb.min[1] ), ( bb.max[0], bb.min[1] ), border_color)
    if (is_end_line  and  offset != range_max  and  i != 0)  or  (current_line == end_line - 1  and  (i > (range_max % bytes_per_line)  and  not is_last_byte)):
        if not rendered_bg:
            draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)
            rendered_bg = True
        draw_list.add_line(( bb.min[0], bb.max[1] ), ( bb.max[0], bb.max[1] ), border_color)
    if not rendered_bg:
        draw_list.add_rect_filled(bb.min, bb.max, bg_color, 0.)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_hex_editor(str_id, state, size, child_flags, window_flags):
pass
def end_hex_editor():
    """ImGui::EndHexEditor()."""
    im.end_child()

def calc_hex_editor_row_range(row_offset, row_bytes_count, range_min, range_max, value, out_max):
    """ImGui::CalcHexEditorRowRange()."""
    # TODO(autoport): second out-parameter(s) out_max: the tuple carries only out_min
    abs_min = None  # TODO(autoport): uninitialized int
    abs_max = None  # TODO(autoport): uninitialized int
    if range_range_intersection(row_offset, row_offset + row_bytes_count, range_min, range_max, abs_min, abs_max):
        value = abs_min - row_offset
        out_max = abs_max - row_offset
        return True, value
    return False, value