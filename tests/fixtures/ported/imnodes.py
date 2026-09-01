"""imnodes: auto-ported from imnodes.h, imnodes.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

MINIMUM_COMPATIBLE_IMGUI_VERSION = 17400

from enum import IntFlag

class ImNodesCol_(IntFlag):
    """ImNodesCol_, from imnodes.h."""
    im_nodes_col_node_background = 0
    im_nodes_col_node_background_hovered = 1
    im_nodes_col_node_background_selected = 2
    im_nodes_col_node_outline = 3
    im_nodes_col_title_bar = 4
    im_nodes_col_title_bar_hovered = 5
    im_nodes_col_title_bar_selected = 6
    im_nodes_col_link = 7
    im_nodes_col_link_hovered = 8
    im_nodes_col_link_selected = 9
    im_nodes_col_pin = 10
    im_nodes_col_pin_hovered = 11
    im_nodes_col_box_selector = 12
    im_nodes_col_box_selector_outline = 13
    im_nodes_col_grid_background = 14
    im_nodes_col_grid_line = 15
    im_nodes_col_grid_line_primary = 16
    im_nodes_col_mini_map_background = 17
    im_nodes_col_mini_map_background_hovered = 18
    im_nodes_col_mini_map_outline = 19
    im_nodes_col_mini_map_outline_hovered = 20
    im_nodes_col_mini_map_node_background = 21
    im_nodes_col_mini_map_node_background_hovered = 22
    im_nodes_col_mini_map_node_background_selected = 23
    im_nodes_col_mini_map_node_outline = 24
    im_nodes_col_mini_map_link = 25
    im_nodes_col_mini_map_link_selected = 26
    im_nodes_col_mini_map_canvas = 27
    im_nodes_col_mini_map_canvas_outline = 28
    im_nodes_col_count = 29

class ImNodesStyleVar_(IntFlag):
    """ImNodesStyleVar_, from imnodes.h."""
    im_nodes_style_var_grid_spacing = 0
    im_nodes_style_var_node_corner_rounding = 1
    im_nodes_style_var_node_padding = 2
    im_nodes_style_var_node_border_thickness = 3
    im_nodes_style_var_link_thickness = 4
    im_nodes_style_var_link_line_segments_per_length = 5
    im_nodes_style_var_link_hover_distance = 6
    im_nodes_style_var_pin_circle_radius = 7
    im_nodes_style_var_pin_quad_side_length = 8
    im_nodes_style_var_pin_triangle_side_length = 9
    im_nodes_style_var_pin_line_thickness = 10
    im_nodes_style_var_pin_hover_radius = 11
    im_nodes_style_var_pin_offset = 12
    im_nodes_style_var_mini_map_padding = 13
    im_nodes_style_var_mini_map_offset = 14
    im_nodes_style_var_count = 15

class ImNodesStyleFlags_(IntFlag):
    """ImNodesStyleFlags_, from imnodes.h."""
    im_nodes_style_flags_none = 0
    im_nodes_style_flags_node_outline = 1
    im_nodes_style_flags_grid_lines = 2
    im_nodes_style_flags_grid_lines_primary = 3
    im_nodes_style_flags_grid_snapping = 4

class ImNodesPinShape_(IntFlag):
    """ImNodesPinShape_, from imnodes.h."""
    im_nodes_pin_shape_circle = 0
    im_nodes_pin_shape_circle_filled = 1
    im_nodes_pin_shape_triangle = 2
    im_nodes_pin_shape_triangle_filled = 3
    im_nodes_pin_shape_quad = 4
    im_nodes_pin_shape_quad_filled = 5

class ImNodesAttributeFlags_(IntFlag):
    """ImNodesAttributeFlags_, from imnodes.h."""
    im_nodes_attribute_flags_none = 0
    im_nodes_attribute_flags_enable_link_detach_with_drag_click = 1
    im_nodes_attribute_flags_enable_link_creation_on_snap = 2

class ImNodesMiniMapLocation_(IntFlag):
    """ImNodesMiniMapLocation_, from imnodes.h."""
    im_nodes_mini_map_location_bottom_left = 0
    im_nodes_mini_map_location_bottom_right = 1
    im_nodes_mini_map_location_top_left = 2
    im_nodes_mini_map_location_top_right = 3

class ImRect:
    """ImRect: axis-aligned rectangle, as the ImGuizmo family
    expects it. Corners are ``(x, y)`` tuples; min is inclusive,
    max exclusive -- the same convention as a clip rect."""
    def __init__(self, a=(0.0, 0.0), b=(0.0, 0.0)):
        self.min = a
        self.max = b

    def contains(self, p):
        return (self.min[0] <= p[0] < self.max[0]
                and self.min[1] <= p[1] < self.max[1])

    def get_center(self):
        return ((self.min[0] + self.max[0]) * 0.5,
                (self.min[1] + self.max[1]) * 0.5)

    def expand(self, amount):
        return ImRect((self.min[0] - amount, self.min[1] - amount),
                      (self.max[0] + amount, self.max[1] + amount))

def im_lerp(a, b, t):
    """ImLerp: blend a toward b by t. C++ overloads this for
    scalars and ImVec2/4; a tuple is blended component-wise."""
    if isinstance(a, tuple):
        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t

class ImNodesIO:
    """ImNodesIO, from imnodes.h."""

    def __init__(self):
        """ImNodesIO::ImNodesIO()."""
        self.AltMouseButton = None
        self.AutoPanningSpeed = None
# TODO(autoport): hand-translate (the rules mangled this line):         EmulateThreeButtonMouse =
        pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         LinkDetachWithModifierClick =
        pass  # TODO(autoport): body of the line above
        self.alt_mouse_button = im.MouseButton.MIDDLE
        self.auto_panning_speed = 1000.0

class ImNodesStyle:
    """ImNodesStyle, from imnodes.h."""

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def __init__(self):
    pass
class ImNodesStyleVarInfo:
    """ImNodesStyleVarInfo, from imnodes.h."""

    def get_var_ptr(self, style):
        """GetVarPtr()."""
# TODO(autoport): hand-translate (the rules mangled this line):         return ((unsigned char*)style + self.offset)
        pass  # TODO(autoport): body of the line above

def eval_cubic_bezier(t, P0, P1, P2, P3):
    """EvalCubicBezier()."""
    u = 1.0 - t
    b0 = u * u * u
    b1 = 3 * u * u * t
    b2 = 3 * u * t * t
    b3 = t * t * t
    return (b0 * P0[0] + b1 * P1[0] + b2 * P2[0] + b3 * P3[0], b0 * P0[1] + b1 * P1[1] + b2 * P2[1] + b3 * P3[1])

def get_closest_point_on_cubic_bezier(num_segments, p, cb):
    """GetClosestPointOnCubicBezier()."""
    assert(num_segments > 0)
    p_last = cb.P0
    p_closest = (0.0, 0.0)
    p_closest_dist = FLT_MAX
    t_step = 1.0 / float(num_segments)
    for i in range(int(1), int(num_segments) + 1):
        p_current = eval_cubic_bezier(t_step * i, cb.P0, cb.P1, cb.P2, cb.P3)
        p_line = im_line_closest_point(p_last, p_current, p)
        dist = im_length_sqr(p - p_line)
        if dist < p_closest_dist:
            p_closest = p_line
            p_closest_dist = dist
        p_last = p_current
    return p_closest

def get_distance_to_cubic_bezier(pos, cubic_bezier, num_segments):
    """GetDistanceToCubicBezier()."""
    point_on_curve = get_closest_point_on_cubic_bezier(num_segments, pos, cubic_bezier)
    to_curve = point_on_curve - pos
    return math.sqrt(im_length_sqr(to_curve))

def get_containing_rect_for_cubic_bezier(cb):
    """GetContainingRectForCubicBezier()."""
    min = (min(cb.P0[0], cb.P3[0]), min(cb.P0[1], cb.P3[1]))
    max = (max(cb.P0[0], cb.P3[0]), max(cb.P0[1], cb.P3[1]))
    hover_distance = GImNodes.style.link_hover_distance
    rect = ImRect(min, max)
    rect.add(cb.P1)
    rect.add(cb.P2)
    rect.expand((hover_distance, hover_distance))
    return rect

def get_cubic_bezier(start, end, start_type, line_segments_per_length):
    """GetCubicBezier()."""
    assert((start_type == ImNodesAttributeType_Input)  or  (start_type == ImNodesAttributeType_Output))
    if start_type == ImNodesAttributeType_Input:
        im_swap(start, end)
    link_length = math.sqrt(im_length_sqr((end[0] - start[0], end[1] - start[1])))
    offset = (0.25 * link_length, 0.)
    cubic_bezier = None  # TODO(autoport): CubicBezier -- construct this state
    cubic_bezier.P0 = start
    cubic_bezier.P1 = (start[0] + offset[0], start[1] + offset[1])
    cubic_bezier.P2 = (end[0] - offset[0], end[1] - offset[1])
    cubic_bezier.P3 = end
    cubic_bezier.num_segments = max(static_cast(link_length * line_segments_per_length), 1)
    return cubic_bezier

def eval_implicit_line_eq(p1, p2, p):
    """EvalImplicitLineEq()."""
    return (p2[1] - p1[1]) * p[0] + (p1[0] - p2[0]) * p[1] + (p2[0] * p1[1] - p1[0] * p2[1])

def sign(val):
    """Sign()."""
    return int(val > 0.0) - int(val < 0.0)

def rectangle_overlaps_line_segment(rect, p1, p2):
    """RectangleOverlapsLineSegment()."""
    if rect.contains(p1)  or  rect.contains(p2):
        return True
    flip_rect = rect
    if flip_rect.min[0] > flip_rect.max[0]:
        im_swap(flip_rect.min[0], flip_rect.max[0])
    if flip_rect.min[1] > flip_rect.max[1]:
        im_swap(flip_rect.min[1], flip_rect.max[1])
    if (p1[0] < flip_rect.min[0]  and  p2[0] < flip_rect.min[0])  or  (p1[0] > flip_rect.max[0]  and  p2[0] > flip_rect.max[0])  or  (p1[1] < flip_rect.min[1]  and  p2[1] < flip_rect.min[1])  or  (p1[1] > flip_rect.max[1]  and  p2[1] > flip_rect.max[1]):
        return False
    corner_signs = [sign(eval_implicit_line_eq(p1, p2, flip_rect.min)), sign(eval_implicit_line_eq(p1, p2, (flip_rect.max[0], flip_rect.min[1]))), sign(eval_implicit_line_eq(p1, p2, (flip_rect.min[0], flip_rect.max[1]))), sign(eval_implicit_line_eq(p1, p2, flip_rect.max))]
    sum = 0
    sum_abs = 0
    for i in range(int(0), int(4)):
        sum = sum + corner_signs[i]
        sum_abs = sum_abs + abs(corner_signs[i])
    return abs(sum) != sum_abs

def rectangle_overlaps_bezier(rectangle, cubic_bezier):
    """RectangleOverlapsBezier()."""
    current = eval_cubic_bezier(0., cubic_bezier.P0, cubic_bezier.P1, cubic_bezier.P2, cubic_bezier.P3)
    dt = 1.0 / cubic_bezier.num_segments
    for s in range(int(0), int(cubic_bezier.num_segments)):
        next = eval_cubic_bezier(static_cast((s + 1) * dt), cubic_bezier.P0, cubic_bezier.P1, cubic_bezier.P2, cubic_bezier.P3)
        if rectangle_overlaps_line_segment(rectangle, current, next):
            return True
        current = next
    return False

def rectangle_overlaps_link(rectangle, start, end, start_type):
    """RectangleOverlapsLink()."""
    lrect = ImRect(start, end)
    if lrect.min[0] > lrect.max[0]:
        im_swap(lrect.min[0], lrect.max[0])
    if lrect.min[1] > lrect.max[1]:
        im_swap(lrect.min[1], lrect.max[1])
    if rectangle.overlaps(lrect):
        if rectangle.contains(start)  or  rectangle.contains(end):
            return True
# TODO(autoport): hand-translate (the rules mangled this line):         const CubicBezier cubic_bezier = get_cubic_bezier(start, end, start_type, GImNodes.style.link_line_segments_per_length)
        pass  # TODO(autoport): body of the line above
        return rectangle_overlaps_bezier(rectangle, cubic_bezier)
    return False

def screen_space_to_grid_space(editor, v):
    """ScreenSpaceToGridSpace()."""
    return v - GImNodes.canvas_origin_screen_space - editor.panning

def screen_space_to_grid_space(editor, r):
    """ScreenSpaceToGridSpace()."""
    return ImRect(screen_space_to_grid_space(editor, r.min), screen_space_to_grid_space(editor, r.max))

def grid_space_to_screen_space(editor, v):
    """GridSpaceToScreenSpace()."""
    return v + GImNodes.canvas_origin_screen_space + editor.panning

def grid_space_to_editor_space(editor, v):
    """GridSpaceToEditorSpace()."""
    return v + editor.panning

def editor_space_to_grid_space(editor, v):
    """EditorSpaceToGridSpace()."""
    return v - editor.panning

def editor_space_to_screen_space(v):
    """EditorSpaceToScreenSpace()."""
    return GImNodes.canvas_origin_screen_space + v

def mini_map_space_to_grid_space(editor, v):
    """MiniMapSpaceToGridSpace()."""
    return (v - editor.mini_map_content_screen_space.min) / editor.mini_map_scaling + editor.grid_content_bounds.min

def screen_space_to_mini_map_space(editor, v):
    """ScreenSpaceToMiniMapSpace()."""
    return (screen_space_to_grid_space(editor, v) - editor.grid_content_bounds.min) * editor.mini_map_scaling + editor.mini_map_content_screen_space.min

def screen_space_to_mini_map_space(editor, r):
    """ScreenSpaceToMiniMapSpace()."""
    return ImRect(screen_space_to_mini_map_space(editor, r.min), screen_space_to_mini_map_space(editor, r.max))

def im_draw_list_grow_channels(draw_list, num_channels):
    """ImDrawListGrowChannels()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImDrawListSplitter& splitter = draw_list._Splitter
    pass  # TODO(autoport): body of the line above
    if splitter._Count == 1:
        splitter.split(draw_list, num_channels + 1)
        return
    old_channel_capacity = splitter._Channels.size
    old_channel_count = splitter._Count
    requested_channel_count = old_channel_count + num_channels
    if old_channel_capacity < old_channel_count + num_channels:
        splitter._Channels.resize(requested_channel_count)
    splitter._Count = requested_channel_count
    for i in range(int(old_channel_count), int(requested_channel_count)):
# TODO(autoport): hand-translate (the rules mangled this line):         ImDrawChannel& channel = splitter._Channels[i]
        pass  # TODO(autoport): body of the line above
        if i < old_channel_capacity:
            channel._CmdBuffer.resize(0)
            channel._IdxBuffer.resize(0)
        else:
            im_placement_newim_draw_channel()
        draw_cmd = None  # TODO(autoport): ImDrawCmd -- construct this state
        draw_cmd.clip_rect = draw_list._ClipRectStack.back()
        draw_cmd.texture_id = draw_list._TextureIdStack.back()
        channel._CmdBuffer.push_back(draw_cmd)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def im_draw_list_splitter_swap_channels(splitter, lhs_idx, rhs_idx):
pass
def draw_list_set(window_draw_list):
    """DrawListSet()."""
    GImNodes.canvas_draw_list = window_draw_list
    GImNodes.node_idx_to_submission_idx.clear()
    GImNodes.node_idx_submission_order.clear()

def draw_list_add_node(node_idx):
    """DrawListAddNode()."""
    GImNodes.node_idx_to_submission_idx.set_int(static_cast(node_idx), GImNodes.node_idx_submission_order.size)
    GImNodes.node_idx_submission_order.push_back(node_idx)
    im_draw_list_grow_channels(GImNodes.canvas_draw_list, 2)

def draw_list_append_click_interaction_channel():
    """DrawListAppendClickInteractionChannel()."""
    im_draw_list_grow_channels(GImNodes.canvas_draw_list, 1)

def draw_list_submission_idx_to_background_channel_idx(submission_idx):
    """DrawListSubmissionIdxToBackgroundChannelIdx()."""
    return 1 + 2 * submission_idx

def draw_list_submission_idx_to_foreground_channel_idx(submission_idx):
    """DrawListSubmissionIdxToForegroundChannelIdx()."""
    return draw_list_submission_idx_to_background_channel_idx(submission_idx) + 1

def draw_list_activate_click_interaction_channel():
    """DrawListActivateClickInteractionChannel()."""
    GImNodes.canvas_draw_list._Splitter.set_current_channel(GImNodes.canvas_draw_list, GImNodes.canvas_draw_list._Splitter._Count - 1)

def draw_list_activate_current_node_foreground():
    """DrawListActivateCurrentNodeForeground()."""
    foreground_channel_idx = draw_list_submission_idx_to_foreground_channel_idx(GImNodes.node_idx_submission_order.size - 1)
    GImNodes.canvas_draw_list._Splitter.set_current_channel(GImNodes.canvas_draw_list, foreground_channel_idx)

def draw_list_activate_node_background(node_idx):
    """DrawListActivateNodeBackground()."""
    submission_idx = GImNodes.node_idx_to_submission_idx.get_int(static_cast(node_idx), -1)
    assert(submission_idx != -1)
    background_channel_idx = draw_list_submission_idx_to_background_channel_idx(submission_idx)
    GImNodes.canvas_draw_list._Splitter.set_current_channel(GImNodes.canvas_draw_list, background_channel_idx)

def draw_list_swap_submission_indices(lhs_idx, rhs_idx):
    """DrawListSwapSubmissionIndices()."""
    assert(lhs_idx != rhs_idx)
    lhs_foreground_channel_idx = draw_list_submission_idx_to_foreground_channel_idx(lhs_idx)
    lhs_background_channel_idx = draw_list_submission_idx_to_background_channel_idx(lhs_idx)
    rhs_foreground_channel_idx = draw_list_submission_idx_to_foreground_channel_idx(rhs_idx)
    rhs_background_channel_idx = draw_list_submission_idx_to_background_channel_idx(rhs_idx)
    im_draw_list_splitter_swap_channels(GImNodes.canvas_draw_list._Splitter, lhs_background_channel_idx, rhs_background_channel_idx)
    im_draw_list_splitter_swap_channels(GImNodes.canvas_draw_list._Splitter, lhs_foreground_channel_idx, rhs_foreground_channel_idx)

def draw_list_sort_channels_by_depth(node_idx_depth_order):
    """DrawListSortChannelsByDepth()."""
    if GImNodes.node_idx_to_submission_idx.data.size < 2:
        return
# TODO(autoport): hand-translate (the rules mangled this line):     assert(node_idx_depth_order.siz) = = GImNodes.node_idx_submission_order.size)
    pass  # TODO(autoport): body of the line above
    start_idx = node_idx_depth_order.size - 1
    while node_idx_depth_order[start_idx] == GImNodes.node_idx_submission_order[start_idx]:
        if --start_idx == 0:
            return
    for depth_idx in range(int(start_idx), int(0), -1):
        node_idx = node_idx_depth_order[depth_idx]
        submission_idx = -1
        for i in range(int(0), int(GImNodes.node_idx_submission_order.size)):
            if GImNodes.node_idx_submission_order[i] == node_idx:
                submission_idx = i
                break
        assert(submission_idx >= 0)
        if submission_idx == depth_idx:
            continue
        for j in range(int(submission_idx), int(depth_idx)):
            draw_list_swap_submission_indices(j, j + 1)
            im_swap(GImNodes.node_idx_submission_order[j], GImNodes.node_idx_submission_order[j + 1])

def get_screen_space_pin_coordinates(node_rect, attribute_rect, type):
    """GetScreenSpacePinCoordinates()."""
# TODO(autoport): hand-translate (the rules mangled this line):     assert(typ) = = ImNodesAttributeType_Input  or  type == ImNodesAttributeType_Output)
    pass  # TODO(autoport): body of the line above
    x = ((node_rect.min[0] - GImNodes.style.pin_offset) if type == ImNodesAttributeType_Input else (node_rect.max[0] + GImNodes.style.pin_offset))
    return (x, 0.5 * (attribute_rect.min[1] + attribute_rect.max[1]))

def get_screen_space_pin_coordinates(editor, pin):
    """GetScreenSpacePinCoordinates()."""
    parent_node_rect = editor.nodes.pool[pin.parent_node_idx].rect
    return get_screen_space_pin_coordinates(parent_node_rect, pin.attribute_rect, pin.type)

def mouse_in_canvas():
    """MouseInCanvas()."""
    is_window_hovered_or_focused = im.is_window_hovered()  or  im.is_window_focused()
    return is_window_hovered_or_focused  and  GImNodes.canvas_rect_screen_space.contains(im.get_mouse_pos())

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_node_selection(editor, node_idx):
pass
def begin_link_selection(editor, link_idx):
    """BeginLinkSelection()."""
    editor.click_interaction.type = ImNodesClickInteractionType_Link
    editor.selected_node_indices.clear()
    editor.selected_link_indices.clear()
    editor.selected_link_indices.push_back(link_idx)

def begin_link_detach(editor, link_idx, detach_pin_idx):
    """BeginLinkDetach()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImLinkData&        link = editor.links.pool[link_idx]
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     ImClickInteractionState& state = editor.click_interaction
    pass  # TODO(autoport): body of the line above
    state.type = ImNodesClickInteractionType_LinkCreation
    state.link_creation.end_pin_idx.reset()
    state.link_creation.start_pin_idx = (link.end_pin_idx if detach_pin_idx == link.start_pin_idx else link.start_pin_idx)
    GImNodes.deleted_link_idx = link_idx

def begin_link_creation(editor, hovered_pin_idx):
    """BeginLinkCreation()."""
    editor.click_interaction.type = ImNodesClickInteractionType_LinkCreation
    editor.click_interaction.link_creation.start_pin_idx = hovered_pin_idx
    editor.click_interaction.link_creation.end_pin_idx.reset()
    editor.click_interaction.link_creation.type = ImNodesLinkCreationType_Standard
    GImNodes.im_nodes_ui_state |= ImNodesUIState_LinkStarted

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_link_interaction(editor, link_idx, pin_idx=im_optional_index
pass
def begin_canvas_interaction(editor):
    """BeginCanvasInteraction()."""
    any_ui_element_hovered = GImNodes.hovered_node_idx.has_value()  or  GImNodes.hovered_link_idx.has_value()  or  GImNodes.hovered_pin_idx.has_value()  or  im.is_any_item_hovered()
    mouse_not_in_canvas = not mouse_in_canvas()
    if editor.click_interaction.type != ImNodesClickInteractionType_None  or  any_ui_element_hovered  or  mouse_not_in_canvas  or  not im.is_window_hovered():
        return
    started_panning = GImNodes.alt_mouse_clicked
    if started_panning:
        editor.click_interaction.type = ImNodesClickInteractionType_Panning
    elif GImNodes.left_mouse_clicked:
        editor.click_interaction.type = ImNodesClickInteractionType_BoxSelection
        editor.click_interaction.box_selector.rect.min = screen_space_to_grid_space(editor, GImNodes.mouse_pos)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def box_selector_update_selection(editor, box_rect):
pass
def snap_origin_to_grid(origin):
    """SnapOriginToGrid()."""
    if GImNodes.style.flags & ImNodesStyleFlags_GridSnapping:
        spacing = GImNodes.style.grid_spacing
        spacing2 = spacing * 0.5
        modx = math.fmod(abs(origin[0]) + spacing2, spacing) - spacing2
        mody = math.fmod(abs(origin[1]) + spacing2, spacing) - spacing2
        origin[0] = origin[0] + (modx if (origin[0] < 0.) else -modx)
        origin[1] = origin[1] + (mody if (origin[1] < 0.) else -mody)
    return origin

def translate_selected_nodes(editor):
    """TranslateSelectedNodes()."""
    if GImNodes.left_mouse_dragging:
        shouldTranslate = (im.get_io().mouse_drag_max_distance_sqr[0] > 5.0 if (GImNodes.style.flags & ImNodesStyleFlags_GridSnapping) else True)
        origin = snap_origin_to_grid(GImNodes.mouse_pos - GImNodes.canvas_origin_screen_space - editor.panning + editor.primary_node_offset)
        for i in range(int(0), int(editor.selected_node_indices.size())):
            node_rel = editor.selected_node_offsets[i]
            node_idx = editor.selected_node_indices[i]
# TODO(autoport): hand-translate (the rules mangled this line):             ImNodeData&  node = editor.nodes.pool[node_idx]
            pass  # TODO(autoport): body of the line above
            if node.draggable  and  shouldTranslate:
                node.origin = origin + node_rel + editor.auto_panning_delta

def find_duplicate_link(editor, start_pin_idx, end_pin_idx):
    """FindDuplicateLink()."""
    test_link = im_link_data(0)
    test_link.start_pin_idx = start_pin_idx
    test_link.end_pin_idx = end_pin_idx
    for link_idx in range(int(0), int(editor.links.pool.size())):
# TODO(autoport): hand-translate (the rules mangled this line):         const ImLinkData& link = editor.links.pool[link_idx]
        pass  # TODO(autoport): body of the line above
        if link_predicate()(test_link, link)  and  editor.links.in_use[link_idx]:
            return im_optional_index(link_idx)
    return im_optional_index()

def should_link_snap_to_pin(editor, start_pin, hovered_pin_idx, duplicate_link):
    """ShouldLinkSnapToPin()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImPinData& end_pin = editor.pins.pool[hovered_pin_idx]
    pass  # TODO(autoport): body of the line above
    if start_pin.parent_node_idx == end_pin.parent_node_idx:
        return False
    if start_pin.type == end_pin.type:
        return False
    if duplicate_link.has_value()  and  not (duplicate_link == GImNodes.snap_link_idx):
        return False
    return True

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def click_interaction_update(editor):
pass
def resolve_occluded_pins(editor, occluded_pin_indices):
    """ResolveOccludedPins()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImVector& depth_stack = editor.node_depth_order
    pass  # TODO(autoport): body of the line above
    occluded_pin_indices.resize(0)
    if depth_stack.size < 2:
        return
    for depth_idx in range(int(0), int((depth_stack.size - 1))):
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodeData& node_below = editor.nodes.pool[depth_stack[depth_idx]]
        pass  # TODO(autoport): body of the line above
        for next_depth_idx in range(int(depth_idx + 1), int(depth_stack.size)):
            rect_above = editor.nodes.pool[depth_stack[next_depth_idx]].rect
            for idx in range(int(0), int(node_below.pin_indices.size)):
                pin_idx = node_below.pin_indices[idx]
                pin_pos = editor.pins.pool[pin_idx].pos
                if rect_above.contains(pin_pos):
                    occluded_pin_indices.push_back(pin_idx)

def resolve_hovered_pin(pins, occluded_pin_indices):
    """ResolveHoveredPin()."""
    smallest_distance = FLT_MAX
    pin_idx_with_smallest_distance = None  # TODO(autoport): ImOptionalIndex -- construct this state
    hover_radius_sqr = GImNodes.style.pin_hover_radius * GImNodes.style.pin_hover_radius
    for idx in range(int(0), int(pins.pool.size)):
        if not pins.in_use[idx]:
            continue
        if occluded_pin_indices.contains(idx):
            continue
        pin_pos = pins.pool[idx].pos
        distance_sqr = im_length_sqr(pin_pos - GImNodes.mouse_pos)
        if distance_sqr < hover_radius_sqr  and  distance_sqr < smallest_distance:
            smallest_distance = distance_sqr
            pin_idx_with_smallest_distance = idx
    return pin_idx_with_smallest_distance

def resolve_hovered_node(depth_stack):
    """ResolveHoveredNode()."""
    if GImNodes.node_indices_overlapping_with_mouse.size() == 0:
        return im_optional_index()
    if GImNodes.node_indices_overlapping_with_mouse.size() == 1:
        return im_optional_index(GImNodes.node_indices_overlapping_with_mouse[0])
    largest_depth_idx = -1
    node_idx_on_top = -1
    for i in range(int(0), int(GImNodes.node_indices_overlapping_with_mouse.size())):
        node_idx = GImNodes.node_indices_overlapping_with_mouse[i]
        for depth_idx in range(int(0), int(depth_stack.size())):
            if depth_stack[depth_idx] == node_idx  and  (depth_idx > largest_depth_idx):
                largest_depth_idx = depth_idx
                node_idx_on_top = node_idx
    assert(node_idx_on_top != -1)
    return im_optional_index(node_idx_on_top)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def resolve_hovered_link(links, pins):
pass
def get_item_rect():
    """GetItemRect()."""
    return ImRect(im.get_item_rect_min(), im.get_item_rect_max())

def get_node_title_bar_origin(node):
    """GetNodeTitleBarOrigin()."""
    return node.origin + node.layout_style.padding

def get_node_content_origin(node):
    """GetNodeContentOrigin()."""
    title_bar_height = (0., node.title_bar_content_rect.get_height() + 2.0 * node.layout_style.padding[1])
    return node.origin + title_bar_height + node.layout_style.padding

def get_node_title_rect(node):
    """GetNodeTitleRect()."""
    expanded_title_rect = node.title_bar_content_rect
    expanded_title_rect.expand(node.layout_style.padding)
    return ImRect(expanded_title_rect.min, expanded_title_rect.min + (node.rect.get_width(), 0.) + (0., expanded_title_rect.get_height()))

def draw_grid(editor, canvas_size):
    """DrawGrid()."""
    offset = editor.panning
    line_color = GImNodes.style.colors[ImNodesCol_GridLine]
    line_color_prim = GImNodes.style.colors[ImNodesCol_GridLinePrimary]
    draw_primary = GImNodes.style.flags & ImNodesStyleFlags_GridLinesPrimary
    for x in range(int(math.fmod(offset[0], GImNodes.style.grid_spacing)), int(canvas_size[0]), GImNodes):
        GImNodes.canvas_draw_list.add_line(editor_space_to_screen_space((x, 0.0)), editor_space_to_screen_space((x, canvas_size[1])), (line_color_prim if offset[0] - x == 0.  and  draw_primary else line_color))
    for y in range(int(math.fmod(offset[1], GImNodes.style.grid_spacing)), int(canvas_size[1]), GImNodes):
        GImNodes.canvas_draw_list.add_line(editor_space_to_screen_space((0.0, y)), editor_space_to_screen_space((canvas_size[0], y)), (line_color_prim if offset[1] - y == 0.  and  draw_primary else line_color))

def calculate_quad_offsets(side_length):
    """CalculateQuadOffsets()."""
    half_side = 0.5 * side_length
    offset = None  # TODO(autoport): QuadOffsets -- construct this state
    offset.top_left = (-half_side, half_side)
    offset.bottom_left = (-half_side, -half_side)
    offset.bottom_right = (half_side, -half_side)
    offset.top_right = (half_side, half_side)
    return offset

def calculate_triangle_offsets(side_length):
    """CalculateTriangleOffsets()."""
    sqrt_3 = math.sqrt(3.0)
    left_offset = -0.1666666666667 * sqrt_3 * side_length
    right_offset = 0.333333333333 * sqrt_3 * side_length
    vertical_offset = 0.5 * side_length
    offset = None  # TODO(autoport): TriangleOffsets -- construct this state
    offset.top_left = (left_offset, vertical_offset)
    offset.bottom_left = (left_offset, -vertical_offset)
    offset.right = (right_offset, 0.)
    return offset

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def draw_pin_shape(pin_pos, pin, pin_color):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def draw_pin(editor, pin_idx):
pass
def draw_node(editor, node_idx):
    """DrawNode()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodeData& node = editor.nodes.pool[node_idx]
    pass  # TODO(autoport): body of the line above
    im.set_cursor_pos(node.origin + editor.panning)
    node_hovered = GImNodes.hovered_node_idx == node_idx  and  editor.click_interaction.type != ImNodesClickInteractionType_BoxSelection
    node_background = node.color_style.background
    titlebar_background = node.color_style.titlebar
    if editor.selected_node_indices.contains(node_idx):
        node_background = node.color_style.background_selected
        titlebar_background = node.color_style.titlebar_selected
    elif node_hovered:
        node_background = node.color_style.background_hovered
        titlebar_background = node.color_style.titlebar_hovered
    GImNodes.canvas_draw_list.add_rect_filled(node.rect.min, node.rect.max, node_background, node.layout_style.corner_rounding)
    if node.title_bar_content_rect.get_height() > 0.:
        title_bar_rect = get_node_title_rect(node)
        GImNodes.canvas_draw_list.add_rect_filled(title_bar_rect.min, title_bar_rect.max, titlebar_background, node.layout_style.corner_rounding, im.DrawFlags.TOP)
    if (GImNodes.style.flags & ImNodesStyleFlags_NodeOutline) != 0:
        GImNodes.canvas_draw_list.add_rect(node.rect.min, node.rect.max, node.color_style.outline, node.layout_style.corner_rounding, im.DrawFlags.ALL, node.layout_style.border_thickness)
    for i in range(int(0), int(node.pin_indices.size())):
        draw_pin(editor, node.pin_indices[i])
    if node_hovered:
        GImNodes.hovered_node_idx = node_idx

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def draw_link(editor, link_idx):
pass
def begin_pin_attribute(id, type, shape, node_idx):
    """BeginPinAttribute()."""
    assert(GImNodes.current_scope == ImNodesScope_Node)
    GImNodes.current_scope = ImNodesScope_Attribute
    im.begin_group()
    im.push_id(id)
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    GImNodes.current_attribute_id = id
    pin_idx = object_pool_find_or_create_index(editor.pins, id)
    GImNodes.current_pin_idx = pin_idx
# TODO(autoport): hand-translate (the rules mangled this line):     ImPinData& pin = editor.pins.pool[pin_idx]
    pass  # TODO(autoport): body of the line above
    pin.id = id
    pin.parent_node_idx = node_idx
    pin.type = type
    pin.shape = shape
    pin.flags = GImNodes.current_attribute_flags
    pin.color_style.background = GImNodes.style.colors[ImNodesCol_Pin]
    pin.color_style.hovered = GImNodes.style.colors[ImNodesCol_PinHovered]

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def end_pin_attribute():
pass
def initialize(context):
    """Initialize()."""
    context.canvas_origin_screen_space = (0.0, 0.0)
    context.canvas_rect_screen_space = ImRect((0., 0.), (0., 0.))
    context.current_scope = ImNodesScope_None
    context.current_pin_idx = INT_MAX
    context.current_node_idx = INT_MAX
    context.default_editor_ctx = editor_context_create()
    context.editor_ctx = context.default_editor_ctx
    context.current_attribute_flags = ImNodesAttributeFlags_None
    context.attribute_flag_stack.push_back(GImNodes.current_attribute_flags)
    style_colors_dark(context.style)

def shutdown(ctx):
    """Shutdown()."""
    editor_context_free(ctx.default_editor_ctx)

def is_mini_map_active():
    """IsMiniMapActive()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    return editor.mini_map_enabled  and  editor.mini_map_size_fraction > 0.0

def is_mini_map_hovered():
    """IsMiniMapHovered()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    return is_mini_map_active()  and  im.is_mouse_hovering_rect(editor.mini_map_rect_screen_space.min, editor.mini_map_rect_screen_space.max)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def calc_mini_map_layout():
pass
def mini_map_draw_node(editor, node_idx):
    """MiniMapDrawNode()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodeData& node = editor.nodes.pool[node_idx]
    pass  # TODO(autoport): body of the line above
    node_rect = screen_space_to_mini_map_space(editor, node.rect)
    mini_map_node_rounding = math.floor(node.layout_style.corner_rounding * editor.mini_map_scaling)
    mini_map_node_background = None  # TODO(autoport): uninitialized ImU32
    if editor.click_interaction.type == ImNodesClickInteractionType_None  and  im.is_mouse_hovering_rect(node_rect.min, node_rect.max):
        mini_map_node_background = GImNodes.style.colors[ImNodesCol_MiniMapNodeBackgroundHovered]
        if editor.mini_map_node_hovering_callback:
            editor.mini_map_node_hovering_callback(node.id, editor.mini_map_node_hovering_callback_user_data)
    elif editor.selected_node_indices.contains(node_idx):
        mini_map_node_background = GImNodes.style.colors[ImNodesCol_MiniMapNodeBackgroundSelected]
    else:
        mini_map_node_background = GImNodes.style.colors[ImNodesCol_MiniMapNodeBackground]
    mini_map_node_outline = GImNodes.style.colors[ImNodesCol_MiniMapNodeOutline]
    GImNodes.canvas_draw_list.add_rect_filled(node_rect.min, node_rect.max, mini_map_node_background, mini_map_node_rounding)
    GImNodes.canvas_draw_list.add_rect(node_rect.min, node_rect.max, mini_map_node_outline, mini_map_node_rounding)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def mini_map_draw_link(editor, link_idx):
pass
def mini_map_update():
    """MiniMapUpdate()."""
    # TODO(autoport): BeginChild: cmtk takes a box anchored at the cursor; the id/border/flags are dropped
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    mini_map_background = None  # TODO(autoport): uninitialized ImU32
    if is_mini_map_hovered():
        mini_map_background = GImNodes.style.colors[ImNodesCol_MiniMapBackgroundHovered]
    else:
        mini_map_background = GImNodes.style.colors[ImNodesCol_MiniMapBackground]
    flags = im.WindowFlags.NO_BACKGROUND
    im.set_cursor_screen_pos(editor.mini_map_rect_screen_space.min)
    im.begin_child((*im.get_cursor_screen_pos(), editor.mini_map_rect_screen_space.get_size()[0], editor.mini_map_rect_screen_space.get_size()[1]))
    mini_map_rect = editor.mini_map_rect_screen_space
    GImNodes.canvas_draw_list.add_rect_filled(mini_map_rect.min, mini_map_rect.max, mini_map_background)
    GImNodes.canvas_draw_list.add_rect(mini_map_rect.min, mini_map_rect.max, GImNodes.style.colors[ImNodesCol_MiniMapOutline])
    GImNodes.canvas_draw_list.push_clip_rect(mini_map_rect.min, mini_map_rect.max, True)
    for link_idx in range(int(0), int(editor.links.pool.size())):
        if editor.links.in_use[link_idx]:
            mini_map_draw_link(editor, link_idx)
    for node_idx in range(int(0), int(editor.nodes.pool.size())):
        if editor.nodes.in_use[node_idx]:
            mini_map_draw_node(editor, node_idx)
    canvas_color = GImNodes.style.colors[ImNodesCol_MiniMapCanvas]
    outline_color = GImNodes.style.colors[ImNodesCol_MiniMapCanvasOutline]
    rect = screen_space_to_mini_map_space(editor, GImNodes.canvas_rect_screen_space)
    GImNodes.canvas_draw_list.add_rect_filled(rect.min, rect.max, canvas_color)
    GImNodes.canvas_draw_list.add_rect(rect.min, rect.max, outline_color)
    GImNodes.canvas_draw_list.pop_clip_rect()
    mini_map_is_hovered = im.is_window_hovered()
    im.end_child()
    center_on_click = mini_map_is_hovered  and  im.is_mouse_down(im.MouseButton.LEFT)  and  editor.click_interaction.type == ImNodesClickInteractionType_None  and  not GImNodes.node_idx_submission_order.empty()
    if center_on_click:
        target = mini_map_space_to_grid_space(editor, im.get_mouse_pos())
        center = GImNodes.canvas_rect_screen_space.get_size() * 0.5
        editor.panning = math.floor(center - target)
    editor.mini_map_node_hovering_callback = None
    editor.mini_map_node_hovering_callback_user_data = None

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def select_object(objects, selected_indices, id):
pass
def clear_object_selection(objects, selected_indices, id):
    """ClearObjectSelection()."""
    idx = object_pool_find(objects, id)
    assert(idx >= 0)
    assert(selected_indices.find(idx) != selected_indices.end())
    selected_indices.find_erase_unsorted(idx)

def is_object_selected(objects, selected_indices, id):
    """IsObjectSelected()."""
    idx = object_pool_find(objects, id)
    return selected_indices.find(idx) != selected_indices.end()

def emulate_three_button_mouse():
    """ImNodesIO::EmulateThreeButtonMouse::EmulateThreeButtonMouse()."""
    Modifier = None

def link_detach_with_modifier_click():
    """ImNodesIO::LinkDetachWithModifierClick::LinkDetachWithModifierClick()."""
    Modifier = None

def multiple_select_modifier():
    """ImNodesIO::MultipleSelectModifier::MultipleSelectModifier()."""
    Modifier = None

def create_context():
    """CreateContext()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesContext* ctx = im_new(ImNodesContext)()
    pass  # TODO(autoport): body of the line above
    if GImNodes == None:
        set_current_context(ctx)
    initialize(ctx)
    return ctx

def destroy_context(ctx):
    """DestroyContext()."""
    if ctx == None:
        ctx = GImNodes
    shutdown(ctx)
    if GImNodes == ctx:
        set_current_context(None)
    im_delete(ctx)

def get_current_context():
    """GetCurrentContext()."""
    return GImNodes

def set_current_context(ctx):
    """SetCurrentContext()."""
    GImNodes = ctx

def editor_context_create():
    """EditorContextCreate()."""
    mem = im.mem_alloc(sizeof(ImNodesEditorContext))
# TODO(autoport): hand-translate (the rules mangled this line):     new im_nodes_editor_context()
    pass  # TODO(autoport): body of the line above
    return mem

def editor_context_free(ctx):
    """EditorContextFree()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ctx.~im_nodes_editor_context()
    pass  # TODO(autoport): body of the line above
    im.mem_free(ctx)

def editor_context_set(ctx):
    """EditorContextSet()."""
    GImNodes.editor_ctx = ctx

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def editor_context_get_panning():
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def editor_context_reset_panning(pos):
pass
def editor_context_move_to_node(node_id):
    """EditorContextMoveToNode()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData&           node = object_pool_find_or_create_object(editor.nodes, node_id)
    pass  # TODO(autoport): body of the line above
    editor.panning[0] = -node.origin[0]
    editor.panning[1] = -node.origin[1]

def set_im_gui_context(ctx):
    """SetImGuiContext()."""
    im.set_current_context(ctx)

def style_colors_dark(dest):
    """StyleColorsDark()."""
    if dest == None:
# TODO(autoport): hand-translate (the rules mangled this line):         dest = &GImNodes.style
        pass  # TODO(autoport): body of the line above
    dest.colors[ImNodesCol_NodeBackground] = im.col32(50, 50, 50, 255)
    dest.colors[ImNodesCol_NodeBackgroundHovered] = im.col32(75, 75, 75, 255)
    dest.colors[ImNodesCol_NodeBackgroundSelected] = im.col32(75, 75, 75, 255)
    dest.colors[ImNodesCol_NodeOutline] = im.col32(100, 100, 100, 255)
    dest.colors[ImNodesCol_TitleBar] = im.col32(41, 74, 122, 255)
    dest.colors[ImNodesCol_TitleBarHovered] = im.col32(66, 150, 250, 255)
    dest.colors[ImNodesCol_TitleBarSelected] = im.col32(66, 150, 250, 255)
    dest.colors[ImNodesCol_Link] = im.col32(61, 133, 224, 200)
    dest.colors[ImNodesCol_LinkHovered] = im.col32(66, 150, 250, 255)
    dest.colors[ImNodesCol_LinkSelected] = im.col32(66, 150, 250, 255)
    dest.colors[ImNodesCol_Pin] = im.col32(53, 150, 250, 180)
    dest.colors[ImNodesCol_PinHovered] = im.col32(53, 150, 250, 255)
    dest.colors[ImNodesCol_BoxSelector] = im.col32(61, 133, 224, 30)
    dest.colors[ImNodesCol_BoxSelectorOutline] = im.col32(61, 133, 224, 150)
    dest.colors[ImNodesCol_GridBackground] = im.col32(40, 40, 50, 200)
    dest.colors[ImNodesCol_GridLine] = im.col32(200, 200, 200, 40)
    dest.colors[ImNodesCol_GridLinePrimary] = im.col32(240, 240, 240, 60)
    dest.colors[ImNodesCol_MiniMapBackground] = im.col32(25, 25, 25, 150)
    dest.colors[ImNodesCol_MiniMapBackgroundHovered] = im.col32(25, 25, 25, 200)
    dest.colors[ImNodesCol_MiniMapOutline] = im.col32(150, 150, 150, 100)
    dest.colors[ImNodesCol_MiniMapOutlineHovered] = im.col32(150, 150, 150, 200)
    dest.colors[ImNodesCol_MiniMapNodeBackground] = im.col32(200, 200, 200, 100)
    dest.colors[ImNodesCol_MiniMapNodeBackgroundHovered] = im.col32(200, 200, 200, 255)
    dest.colors[ImNodesCol_MiniMapNodeBackgroundSelected] = dest.colors[ImNodesCol_MiniMapNodeBackgroundHovered]
    dest.colors[ImNodesCol_MiniMapNodeOutline] = im.col32(200, 200, 200, 100)
    dest.colors[ImNodesCol_MiniMapLink] = dest.colors[ImNodesCol_Link]
    dest.colors[ImNodesCol_MiniMapLinkSelected] = dest.colors[ImNodesCol_LinkSelected]
    dest.colors[ImNodesCol_MiniMapCanvas] = im.col32(200, 200, 200, 25)
    dest.colors[ImNodesCol_MiniMapCanvasOutline] = im.col32(200, 200, 200, 200)

def style_colors_classic(dest):
    """StyleColorsClassic()."""
    if dest == None:
# TODO(autoport): hand-translate (the rules mangled this line):         dest = &GImNodes.style
        pass  # TODO(autoport): body of the line above
    dest.colors[ImNodesCol_NodeBackground] = im.col32(50, 50, 50, 255)
    dest.colors[ImNodesCol_NodeBackgroundHovered] = im.col32(75, 75, 75, 255)
    dest.colors[ImNodesCol_NodeBackgroundSelected] = im.col32(75, 75, 75, 255)
    dest.colors[ImNodesCol_NodeOutline] = im.col32(100, 100, 100, 255)
    dest.colors[ImNodesCol_TitleBar] = im.col32(69, 69, 138, 255)
    dest.colors[ImNodesCol_TitleBarHovered] = im.col32(82, 82, 161, 255)
    dest.colors[ImNodesCol_TitleBarSelected] = im.col32(82, 82, 161, 255)
    dest.colors[ImNodesCol_Link] = im.col32(255, 255, 255, 100)
    dest.colors[ImNodesCol_LinkHovered] = im.col32(105, 99, 204, 153)
    dest.colors[ImNodesCol_LinkSelected] = im.col32(105, 99, 204, 153)
    dest.colors[ImNodesCol_Pin] = im.col32(89, 102, 156, 170)
    dest.colors[ImNodesCol_PinHovered] = im.col32(102, 122, 179, 200)
    dest.colors[ImNodesCol_BoxSelector] = im.col32(82, 82, 161, 100)
    dest.colors[ImNodesCol_BoxSelectorOutline] = im.col32(82, 82, 161, 255)
    dest.colors[ImNodesCol_GridBackground] = im.col32(40, 40, 50, 200)
    dest.colors[ImNodesCol_GridLine] = im.col32(200, 200, 200, 40)
    dest.colors[ImNodesCol_GridLinePrimary] = im.col32(240, 240, 240, 60)
    dest.colors[ImNodesCol_MiniMapBackground] = im.col32(25, 25, 25, 100)
    dest.colors[ImNodesCol_MiniMapBackgroundHovered] = im.col32(25, 25, 25, 200)
    dest.colors[ImNodesCol_MiniMapOutline] = im.col32(150, 150, 150, 100)
    dest.colors[ImNodesCol_MiniMapOutlineHovered] = im.col32(150, 150, 150, 200)
    dest.colors[ImNodesCol_MiniMapNodeBackground] = im.col32(200, 200, 200, 100)
    dest.colors[ImNodesCol_MiniMapNodeBackgroundSelected] = dest.colors[ImNodesCol_MiniMapNodeBackgroundHovered]
    dest.colors[ImNodesCol_MiniMapNodeBackgroundSelected] = im.col32(200, 200, 240, 255)
    dest.colors[ImNodesCol_MiniMapNodeOutline] = im.col32(200, 200, 200, 100)
    dest.colors[ImNodesCol_MiniMapLink] = dest.colors[ImNodesCol_Link]
    dest.colors[ImNodesCol_MiniMapLinkSelected] = dest.colors[ImNodesCol_LinkSelected]
    dest.colors[ImNodesCol_MiniMapCanvas] = im.col32(200, 200, 200, 25)
    dest.colors[ImNodesCol_MiniMapCanvasOutline] = im.col32(200, 200, 200, 200)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def style_colors_light(dest):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_node_editor():
pass
def end_node_editor():
    """EndNodeEditor()."""
    assert(GImNodes.current_scope == ImNodesScope_Editor)
    GImNodes.current_scope = ImNodesScope_None
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    no_grid_content = editor.grid_content_bounds.is_inverted()
    if no_grid_content:
        editor.grid_content_bounds = screen_space_to_grid_space(editor, GImNodes.canvas_rect_screen_space)
    if GImNodes.left_mouse_clicked  and  im.is_any_item_active():
        editor.click_interaction.type = ImNodesClickInteractionType_ImGuiItem
    if (editor.click_interaction.type == ImNodesClickInteractionType_None  or  editor.click_interaction.type == ImNodesClickInteractionType_LinkCreation)  and  mouse_in_canvas()  and  not is_mini_map_hovered():
        resolve_occluded_pins(editor, GImNodes.occluded_pin_indices)
        GImNodes.hovered_pin_idx = resolve_hovered_pin(editor.pins, GImNodes.occluded_pin_indices)
        if not GImNodes.hovered_pin_idx.has_value():
            GImNodes.hovered_node_idx = resolve_hovered_node(editor.node_depth_order)
        if not GImNodes.hovered_node_idx.has_value():
            GImNodes.hovered_link_idx = resolve_hovered_link(editor.links, editor.pins)
    for node_idx in range(int(0), int(editor.nodes.pool.size())):
        if editor.nodes.in_use[node_idx]:
            draw_list_activate_node_background(node_idx)
            draw_node(editor, node_idx)
    GImNodes.canvas_draw_list.channels_set_current(0)
    for link_idx in range(int(0), int(editor.links.pool.size())):
        if editor.links.in_use[link_idx]:
            draw_link(editor, link_idx)
    draw_list_append_click_interaction_channel()
    draw_list_activate_click_interaction_channel()
    if is_mini_map_active():
        calc_mini_map_layout()
        mini_map_update()
    if not is_mini_map_hovered():
        if GImNodes.left_mouse_clicked  and  GImNodes.hovered_link_idx.has_value():
            begin_link_interaction(editor, GImNodes.hovered_link_idx.value(), GImNodes.hovered_pin_idx)
        elif GImNodes.left_mouse_clicked  and  GImNodes.hovered_pin_idx.has_value():
            begin_link_creation(editor, GImNodes.hovered_pin_idx.value())
        elif GImNodes.left_mouse_clicked  and  GImNodes.hovered_node_idx.has_value():
            begin_node_selection(editor, GImNodes.hovered_node_idx.value())
        elif GImNodes.left_mouse_clicked  or  GImNodes.left_mouse_released  or  GImNodes.alt_mouse_clicked  or  GImNodes.alt_mouse_scroll_delta != 0.:
            begin_canvas_interaction(editor)
        should_auto_pan = editor.click_interaction.type == ImNodesClickInteractionType_BoxSelection  or  editor.click_interaction.type == ImNodesClickInteractionType_LinkCreation  or  editor.click_interaction.type == ImNodesClickInteractionType_Node
        if should_auto_pan  and  not mouse_in_canvas():
            mouse = im.get_mouse_pos()
            center = GImNodes.canvas_rect_screen_space.get_center()
            direction = (center - mouse)
            direction = direction * im_inv_length(direction, 0.0)
            editor.auto_panning_delta = direction * im.get_io().delta_time * GImNodes.io.auto_panning_speed
            editor.panning = editor.panning + editor.auto_panning_delta
    click_interaction_update(editor)
    object_pool_update(editor.nodes)
    object_pool_update(editor.pins)
    draw_list_sort_channels_by_depth(editor.node_depth_order)
    object_pool_update(editor.links)
    GImNodes.canvas_draw_list.channels_merge()
    im.end_child()
    im.pop_style_color()
    im.pop_style_var()
    im.pop_style_var()
    im.end_group()

def mini_map(minimap_size_fraction, location, node_hovering_callback, node_hovering_callback_data):
    """MiniMap()."""
    assert(minimap_size_fraction > 0.  and  minimap_size_fraction <= 1.)
    assert(GImNodes.current_scope == ImNodesScope_Editor)
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    editor.mini_map_enabled = True
    editor.mini_map_size_fraction = minimap_size_fraction
    editor.mini_map_location = location
    editor.mini_map_node_hovering_callback = node_hovering_callback
    editor.mini_map_node_hovering_callback_user_data = node_hovering_callback_data

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_node(node_id):
pass
def end_node():
    """EndNode()."""
    assert(GImNodes.current_scope == ImNodesScope_Node)
    GImNodes.current_scope = ImNodesScope_Editor
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    im.end_group()
    im.pop_id()
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData& node = editor.nodes.pool[GImNodes.current_node_idx]
    pass  # TODO(autoport): body of the line above
    node.rect = get_item_rect()
    node.rect.expand(node.layout_style.padding)
    editor.grid_content_bounds.add(node.origin)
    editor.grid_content_bounds.add(node.origin + node.rect.get_size())
    if node.rect.contains(GImNodes.mouse_pos):
        GImNodes.node_indices_overlapping_with_mouse.push_back(GImNodes.current_node_idx)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def get_node_dimensions(node_id):
pass
def begin_node_title_bar():
    """BeginNodeTitleBar()."""
    assert(GImNodes.current_scope == ImNodesScope_Node)
    im.begin_group()

def end_node_title_bar():
    """EndNodeTitleBar()."""
    assert(GImNodes.current_scope == ImNodesScope_Node)
    im.end_group()
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData&           node = editor.nodes.pool[GImNodes.current_node_idx]
    pass  # TODO(autoport): body of the line above
    node.title_bar_content_rect = get_item_rect()
    im.item_add(get_node_title_rect(node), im.get_id("title_bar"))
    im.set_cursor_pos(grid_space_to_editor_space(editor, get_node_content_origin(node)))

def begin_input_attribute(id, shape):
    """BeginInputAttribute()."""
    begin_pin_attribute(id, ImNodesAttributeType_Input, shape, GImNodes.current_node_idx)

def end_input_attribute():
    """EndInputAttribute()."""
    end_pin_attribute()

def begin_output_attribute(id, shape):
    """BeginOutputAttribute()."""
    begin_pin_attribute(id, ImNodesAttributeType_Output, shape, GImNodes.current_node_idx)

def end_output_attribute():
    """EndOutputAttribute()."""
    end_pin_attribute()

def begin_static_attribute(id):
    """BeginStaticAttribute()."""
    assert(GImNodes.current_scope == ImNodesScope_Node)
    GImNodes.current_scope = ImNodesScope_Attribute
    GImNodes.current_attribute_id = id
    im.begin_group()
    im.push_id(id)

def end_static_attribute():
    """EndStaticAttribute()."""
    assert(GImNodes.current_scope == ImNodesScope_Attribute)
    GImNodes.current_scope = ImNodesScope_Node
    im.pop_id()
    im.end_group()
    if im.is_item_active():
        GImNodes.active_attribute = True
        GImNodes.active_attribute_id = GImNodes.current_attribute_id

def push_attribute_flag(flag):
    """PushAttributeFlag()."""
    GImNodes.current_attribute_flags |= flag
    GImNodes.attribute_flag_stack.push_back(GImNodes.current_attribute_flags)

def pop_attribute_flag():
    """PopAttributeFlag()."""
    assert(GImNodes.attribute_flag_stack.size() > 1)
    GImNodes.attribute_flag_stack.pop_back()
    GImNodes.current_attribute_flags = GImNodes.attribute_flag_stack.back()

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def link(id, start_attr_id, end_attr_id):
pass
def push_color_style(item, color):
    """PushColorStyle()."""
    GImNodes.color_modifier_stack.push_back(im_nodes_col_element(GImNodes.style.colors[item], item))
    GImNodes.style.colors[item] = color

def pop_color_style():
    """PopColorStyle()."""
    assert(GImNodes.color_modifier_stack.size() > 0)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodesColElement elem = GImNodes.color_modifier_stack.back()
    pass  # TODO(autoport): body of the line above
    GImNodes.style.colors[elem.item] = elem.color
    GImNodes.color_modifier_stack.pop_back()

def push_style_var(item, value):
    """PushStyleVar()."""
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodesStyleVarInfo* var_info = get_style_var_info(item)
    pass  # TODO(autoport): body of the line above
    if var_info.type == im.DataType.FLOAT  and  var_info.count == 1:
# TODO(autoport): hand-translate (the rules mangled this line):         style_var = *var_info.get_var_ptr(GImNodes.style)
        pass  # TODO(autoport): body of the line above
        GImNodes.style_modifier_stack.push_back(im_nodes_style_var_element(item, style_var))
        style_var = value
        return
    assert(0  and  "Called push_style_var() float variant but variable is not a float!")

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def push_style_var(item, value):
pass
def pop_style_var(count):
    """PopStyleVar()."""
    while count > 0:
        assert(GImNodes.style_modifier_stack.size() > 0)
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodesStyleVarElement style_backup = GImNodes.style_modifier_stack.back()
        pass  # TODO(autoport): body of the line above
        GImNodes.style_modifier_stack.pop_back()
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodesStyleVarInfo* var_info = get_style_var_info(style_backup.item)
        pass  # TODO(autoport): body of the line above
        style_var = var_info.get_var_ptr(GImNodes.style)
        if var_info.type == im.DataType.FLOAT  and  var_info.count == 1:
            (style_var)[0] = style_backup.float_value[0]
        elif var_info.type == im.DataType.FLOAT  and  var_info.count == 2:
            (style_var)[0] = style_backup.float_value[0]
            (style_var)[1] = style_backup.float_value[1]
        count -= 1

def set_node_screen_space_pos(node_id, screen_space_pos):
    """SetNodeScreenSpacePos()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData&           node = object_pool_find_or_create_object(editor.nodes, node_id)
    pass  # TODO(autoport): body of the line above
    node.origin = screen_space_to_grid_space(editor, screen_space_pos)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def set_node_editor_space_pos(node_id, editor_space_pos):
pass
def set_node_grid_space_pos(node_id, grid_pos):
    """SetNodeGridSpacePos()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData&           node = object_pool_find_or_create_object(editor.nodes, node_id)
    pass  # TODO(autoport): body of the line above
    node.origin = grid_pos

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def set_node_draggable(node_id, draggable):
pass
def get_node_screen_space_pos(node_id):
    """GetNodeScreenSpacePos()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    node_idx = object_pool_find(editor.nodes, node_id)
    assert(node_idx != -1)
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData& node = editor.nodes.pool[node_idx]
    pass  # TODO(autoport): body of the line above
    return grid_space_to_screen_space(editor, node.origin)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def get_node_editor_space_pos(node_id):
pass
def get_node_grid_space_pos(node_id):
    """GetNodeGridSpacePos()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    node_idx = object_pool_find(editor.nodes, node_id)
    assert(node_idx != -1)
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodeData& node = editor.nodes.pool[node_idx]
    pass  # TODO(autoport): body of the line above
    return node.origin

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def snap_node_to_grid(node_id):
pass
def is_editor_hovered():
    """IsEditorHovered()."""
    return mouse_in_canvas()

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def is_node_hovered(node_id):
pass
def is_link_hovered(link_id):
    """IsLinkHovered()."""
    assert(GImNodes.current_scope == ImNodesScope_None)
    assert(link_id != None)
    is_hovered = GImNodes.hovered_link_idx.has_value()
    if is_hovered:
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodesEditorContext& editor = editor_context_get()
        pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         *link_id = editor.links.pool[GImNodes.hovered_link_idx.value()].id
        pass  # TODO(autoport): body of the line above
    return is_hovered

def is_pin_hovered(attr):
    """IsPinHovered()."""
    assert(GImNodes.current_scope == ImNodesScope_None)
    assert(attr != None)
    is_hovered = GImNodes.hovered_pin_idx.has_value()
    if is_hovered:
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodesEditorContext& editor = editor_context_get()
        pass  # TODO(autoport): body of the line above
# TODO(autoport): hand-translate (the rules mangled this line):         *attr = editor.pins.pool[GImNodes.hovered_pin_idx.value()].id
        pass  # TODO(autoport): body of the line above
    return is_hovered

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def num_selected_nodes():
pass
def num_selected_links():
    """NumSelectedLinks()."""
    assert(GImNodes.current_scope == ImNodesScope_None)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    return editor.selected_link_indices.size()

def get_selected_nodes(node_ids):
    """GetSelectedNodes()."""
    assert(node_ids != None)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    for i in range(int(0), int(editor.selected_node_indices.size())):
        node_idx = editor.selected_node_indices[i]
        node_ids[i] = editor.nodes.pool[node_idx].id

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def get_selected_links(link_ids):
pass
def clear_node_selection():
    """ClearNodeSelection()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    editor.selected_node_indices.clear()

def clear_node_selection(node_id):
    """ClearNodeSelection()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    clear_object_selection(editor.nodes, editor.selected_node_indices, node_id)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def clear_link_selection():
pass
def clear_link_selection(link_id):
    """ClearLinkSelection()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    clear_object_selection(editor.links, editor.selected_link_indices, link_id)

def select_node(node_id):
    """SelectNode()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    select_object(editor.nodes, editor.selected_node_indices, node_id)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def select_link(link_id):
pass
def is_node_selected(node_id):
    """IsNodeSelected()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    return is_object_selected(editor.nodes, editor.selected_node_indices, node_id)

def is_link_selected(link_id):
    """IsLinkSelected()."""
# TODO(autoport): hand-translate (the rules mangled this line):     ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    return is_object_selected(editor.links, editor.selected_link_indices, link_id)

def is_attribute_active():
    """IsAttributeActive()."""
    assert((GImNodes.current_scope & ImNodesScope_Node) != 0)
    if not GImNodes.active_attribute:
        return False
    return GImNodes.active_attribute_id == GImNodes.current_attribute_id

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def is_any_attribute_active(attribute_id):
pass
def is_link_started(started_at_id):
    """IsLinkStarted()."""
    assert(GImNodes.current_scope == ImNodesScope_None)
    assert(started_at_id != None)
    is_started = (GImNodes.im_nodes_ui_state & ImNodesUIState_LinkStarted) != 0
    if is_started:
# TODO(autoport): hand-translate (the rules mangled this line):         const ImNodesEditorContext& editor = editor_context_get()
        pass  # TODO(autoport): body of the line above
        pin_idx = editor.click_interaction.link_creation.start_pin_idx
# TODO(autoport): hand-translate (the rules mangled this line):         *started_at_id = editor.pins.pool[pin_idx].id
        pass  # TODO(autoport): body of the line above
    return is_started

def is_link_dropped(started_at_id, including_detached_links):
    """IsLinkDropped()."""
    assert(GImNodes.current_scope == ImNodesScope_None)
# TODO(autoport): hand-translate (the rules mangled this line):     const ImNodesEditorContext& editor = editor_context_get()
    pass  # TODO(autoport): body of the line above
    link_dropped = (GImNodes.im_nodes_ui_state & ImNodesUIState_LinkDropped) != 0  and  (including_detached_links  or  editor.click_interaction.link_creation.type != ImNodesLinkCreationType_FromDetach)
    if link_dropped  and  started_at_id:
        pin_idx = editor.click_interaction.link_creation.start_pin_idx
# TODO(autoport): hand-translate (the rules mangled this line):         *started_at_id = editor.pins.pool[pin_idx].id
        pass  # TODO(autoport): body of the line above
    return link_dropped

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def is_link_created(started_at_pin_id, ended_at_pin_id, created_from_s
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def is_link_created(started_at_node_id, started_at_pin_id, ended_at_no
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def is_link_destroyed(link_id):
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def node_line_handler(editor, line):
pass
def editor_line_handler(editor, line):
    """EditorLineHandler()."""
    sscanf(line, "panning=%f,%f", editor.panning[0], editor.panning[1])

def load_current_editor_state_from_ini_string(data, data_size):
    """LoadCurrentEditorStateFromIniString()."""
    load_editor_state_from_ini_string(editor_context_get(), data, data_size)

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def load_editor_state_from_ini_string(editor_ptr, data, data_size):
pass
def save_current_editor_state_to_ini_file(file_name):
    """SaveCurrentEditorStateToIniFile()."""
    save_editor_state_to_ini_file(editor_context_get(), file_name)

def save_editor_state_to_ini_file(editor, file_name):
    """SaveEditorStateToIniFile()."""
    data_size = 0
    data = save_editor_state_to_ini_string(editor, data_size)
# TODO(autoport): hand-translate (the rules mangled this line):     FILE*       file = im_file_open(file_name, "wt")
    pass  # TODO(autoport): body of the line above
    if not file:
        return
    fwrite(data, sizeof(char), data_size, file)
    fclose(file)

def load_current_editor_state_from_ini_file(file_name):
    """LoadCurrentEditorStateFromIniFile()."""
    load_editor_state_from_ini_file(editor_context_get(), file_name)

def load_editor_state_from_ini_file(editor, file_name):
    """LoadEditorStateFromIniFile()."""
    data_size = 0
    file_data = im_file_load_to_memory(file_name, "rb", data_size)
    if not file_data:
        return
    load_editor_state_from_ini_string(editor, file_data, data_size)
    im.mem_free(file_data)