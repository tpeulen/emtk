"""graph_editor: auto-ported from GraphEditor.h, GraphEditor.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

editingInput = False

from enum import IntFlag

class FitOnScreen(IntFlag):
    """FitOnScreen, from GraphEditor.h."""
    fit_none = 0
    fit_all_nodes = 1
    fit_selected_nodes = 2

class NodeOperation(IntFlag):
    """NodeOperation, from GraphEditor.h."""
    no_none = 0
    no_editing_link = 1
    no_quad_selecting = 2
    no_moving_nodes = 3
    no_edit_input = 4
    no_pan_view = 5

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

def im_clamp(v, mn, mx):
    """ImClamp."""
    return max(mn, min(mx, v))

def im_lerp(a, b, t):
    """ImLerp: blend a toward b by t. C++ overloads this for
    scalars and ImVec2/4; a tuple is blended component-wise."""
    if isinstance(a, tuple):
        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t

def distance(a, b):
    """Distance()."""
    return math.sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1]))

def sign(v):
    """sign()."""
    return (1. if (v >= 0.) else -1.)

def get_input_slot_pos(delegate, node, slotIndex, factor):
    """GetInputSlotPos()."""
    Size = node.m_rect.get_size() * factor
    InputsCount = delegate.get_template(node.m_template_index).m_input_count
    return (node.m_rect.min[0] * factor, node.m_rect.min[1] * factor + Size[1] * (float(slotIndex) + 1) / (float(InputsCount) + 1) + 8.)

def get_output_slot_pos(delegate, node, slotIndex, factor):
    """GetOutputSlotPos()."""
    Size = node.m_rect.get_size() * factor
    OutputsCount = delegate.get_template(node.m_template_index).m_output_count
    return (node.m_rect.min[0] * factor + Size[0], node.m_rect.min[1] * factor + Size[1] * (float(slotIndex) + 1) / (float(OutputsCount) + 1) + 8.)

def get_node_rect(node, factor):
    """GetNodeRect()."""
    Size = node.m_rect.get_size() * factor
    return ImRect(node.m_rect.min * factor, node.m_rect.min * factor + Size)

def handle_zoom_scroll(regionRect, viewState, options):
    """HandleZoomScroll()."""
    io = im.get_io()
    if regionRect.contains(io.mouse_pos):
        if io.mouse_wheel < -FLT_EPSILON:
            viewState.m_factor_target = viewState.m_factor_target * 1. - options.m_zoom_ratio
        if io.mouse_wheel > FLT_EPSILON:
            viewState.m_factor_target = viewState.m_factor_target * 1.0 + options.m_zoom_ratio
    mouseWPosPre = (io.mouse_pos - im.get_cursor_screen_pos()) / viewState.m_factor
    viewState.m_factor_target = im_clamp(viewState.m_factor_target, options.m_min_zoom, options.m_max_zoom)
    viewState.m_factor = im_lerp(viewState.m_factor, viewState.m_factor_target, options.m_zoom_lerp_factor)
    mouseWPosPost = (io.mouse_pos - im.get_cursor_screen_pos()) / viewState.m_factor
    if im.is_mouse_pos_valid():
        viewState.m_position = viewState.m_position + mouseWPosPost - mouseWPosPre

def graph_editor_clear():
    """GraphEditorClear()."""
    nodeOperation = NO_None

def fit_nodes(delegate, viewState, viewSize, selectedNodesOnly):
    """FitNodes()."""
    nodeCount = delegate.get_node_count()
    if not nodeCount:
        return
    validNode = False
    min = (FLT_MAX, FLT_MAX)
    max = (-FLT_MAX, -FLT_MAX)
    for nodeIndex in range(int(0), int(nodeCount)):
# TODO(autoport): hand-translate (the rules mangled this line):         const Node& node = delegate.get_node(nodeIndex)
        pass  # TODO(autoport): body of the line above
        if selectedNodesOnly  and  not node.m_selected:
            continue
        min = min(min, node.m_rect.min)
        min = min(min, node.m_rect.max)
        max = max(max, node.m_rect.min)
        max = max(max, node.m_rect.max)
        validNode = True
    if not validNode:
        return
    min = min - (viewSize[0] * 0.05, viewSize[1] * 0.05)
    max = max + (viewSize[0] * 0.05, viewSize[1] * 0.05)
    nodesSize = (max[0] - min[0], max[1] - min[1])
    nodeCenter = ((max[0] + min[0], max[1] + min[1])) * 0.5
    ratioY = viewSize[1] / nodesSize[1]
    ratioX = viewSize[0] / nodesSize[0]
    viewState.m_factor = viewState.m_factor_target = min(min(ratioY, ratioX), 1.)
    viewState.m_position = (-nodeCenter[0], -nodeCenter[1]) + ((viewSize[0] * 0.5, viewSize[1] * 0.5)) / viewState.m_factor_target

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def display_links(delegate, drawList, offset, factor, regionRect, hove
pass
def handle_quad_selection(delegate, drawList, offset, factor, contentRect, options):
    """HandleQuadSelection()."""
    # TODO(autoport): static quadSelectPos: C++ keeps it across calls; Python re-initializes
    if not options.m_allow_quad_selection:
        return
    io = im.get_io()
    quadSelectPos = (0.0, 0.0)
    nodeCount = delegate.get_node_count()
    if nodeOperation == NO_QuadSelecting  and  im.is_window_focused():
        bmin = min(quadSelectPos, io.mouse_pos)
        bmax = max(quadSelectPos, io.mouse_pos)
        drawList.add_rect_filled(bmin, bmax, options.m_quad_selection, 1.)
        drawList.add_rect(bmin, bmax, options.m_quad_selection_border, 1.)
        if not io.mouse_down[0]:
            if not io.key_ctrl  and  not io.key_shift:
                for nodeIndex in range(int(0), int(nodeCount)):
                    delegate.select_node(nodeIndex, False)
            nodeOperation = NO_None
            selectionRect = ImRect(bmin, bmax)
            for nodeIndex in range(int(0), int(nodeCount)):
                node = delegate.get_node(nodeIndex)
                nodeRectangleMin = offset + node.m_rect.min * factor
                nodeRectangleMax = nodeRectangleMin + node.m_rect.get_size() * factor
                if selectionRect.overlaps(ImRect(nodeRectangleMin, nodeRectangleMax)):
                    if io.key_ctrl:
                        delegate.select_node(nodeIndex, False)
                    else:
                        delegate.select_node(nodeIndex, True)
                else:
                    if not io.key_shift:
                        delegate.select_node(nodeIndex, False)
    elif nodeOperation == NO_None  and  io.mouse_down[0]  and  im.is_window_focused()  and  contentRect.contains(io.mouse_pos):
        nodeOperation = NO_QuadSelecting
        quadSelectPos = io.mouse_pos

def handle_connections(drawList, nodeIndex, offset, factor, delegate, options, bDrawOnly, inputSlotOver, outputSlotOver, inMinimap):
    """HandleConnections()."""
    editingNodeIndex = None  # TODO(autoport): static -- construct this state
    editingSlotIndex = None  # TODO(autoport): static -- construct this state
    io = im.get_io()
    node = delegate.get_node(nodeIndex)
    nodeTemplate = delegate.get_template(node.m_template_index)
    linkCount = delegate.get_link_count()
    InputsCount = nodeTemplate.m_input_count
    OutputsCount = nodeTemplate.m_output_count
    inputSlotOver = -1
    outputSlotOver = -1
    hoverSlot = False
    for i in range(int(0), int(2)):
        closestDistance = FLT_MAX
# TODO(autoport): hand-translate (the rules mangled this line):         SlotIndex closestConn = -1
        pass  # TODO(autoport): body of the line above
        closestTextPos = (0.0, 0.0)
        closestPos = (0.0, 0.0)
        slotCount = [InputsCount, OutputsCount]
        for slotIndex in range(int(0), int(slotCount[i])):
            con = (nodeTemplate.m_output_names if i else nodeTemplate.m_input_names)
            conText = (con[slotIndex] if (con  and  con[slotIndex]) else "")
            p = offset + ((get_output_slot_pos(delegate, node, slotIndex, factor) if i else get_input_slot_pos(delegate, node, slotIndex, factor)))
            distance = distance(p, io.mouse_pos)
            overCon = (nodeOperation == NO_None  or  nodeOperation == NO_EditingLink)  and  (distance < options.m_node_slot_radius * 2.)  and  (distance < closestDistance)
            textSize = (0.0, 0.0)
            textSize = im.calc_text_size(conText)
            textPos = p + (-options.m_node_slot_radius * ((-1. if i else 1.)) * ((3. if overCon else 2.)) - ((0 if i else textSize[0])), -textSize[1] / 2)
            nodeRect = get_node_rect(node, factor)
            if not inMinimap  and  (overCon  or  (nodeRect.contains(io.mouse_pos - offset)  and  closestConn == -1  and  (editingInput == (i != 0))  and  nodeOperation == NO_EditingLink)):
                closestDistance = distance
                closestConn = slotIndex
                closestTextPos = textPos
                closestPos = p
                if i:
                    outputSlotOver = slotIndex
                else:
                    inputSlotOver = slotIndex
            else:
                slotColorSource = (nodeTemplate.m_output_colors if i else nodeTemplate.m_input_colors)
                slotColor = (slotColorSource[slotIndex] if slotColorSource else options.m_default_slot_color)
                drawList.add_circle_filled(p, options.m_node_slot_radius, im.col32(0, 0, 0, 200))
                drawList.add_circle_filled(p, options.m_node_slot_radius * 0.75, slotColor)
                if not options.m_draw_io_name_on_hover:
                    drawList.add_text(io.font_default, 14, (textPos[0] + 2, textPos[1] + 2), im.col32(0, 0, 0, 255), conText)
                    drawList.add_text(io.font_default, 14, textPos, im.col32(150, 150, 150, 255), conText)
        if closestConn != -1:
            con = (nodeTemplate.m_output_names if i else nodeTemplate.m_input_names)
            conText = (con[closestConn] if (con  and  con[closestConn]) else "")
            slotColorSource = (nodeTemplate.m_output_colors if i else nodeTemplate.m_input_colors)
            slotColor = (slotColorSource[closestConn] if slotColorSource else options.m_default_slot_color)
            hoverSlot = True
            drawList.add_circle_filled(closestPos, options.m_node_slot_radius * options.m_node_slot_hover_factor * 0.75, im.col32(0, 0, 0, 200))
            drawList.add_circle_filled(closestPos, options.m_node_slot_radius * options.m_node_slot_hover_factor, slotColor)
            drawList.add_text(io.font_default, 16, (closestTextPos[0] + 1, closestTextPos[1] + 1), im.col32(0, 0, 0, 255), conText)
            drawList.add_text(io.font_default, 16, closestTextPos, im.col32(250, 250, 250, 255), conText)
            inputToOutput = (not editingInput  and  not i)  or  (editingInput  and  i)
            if nodeOperation == NO_EditingLink  and  not io.mouse_down[0]  and  not bDrawOnly:
                if inputToOutput:
                    nl = None  # TODO(autoport): Link -- construct this state
                    if editingInput:
                        nl = Link(nodeIndex, closestConn, editingNodeIndex, editingSlotIndex)
                    else:
                        if not delegate.allowed_link(nl.m_output_node_index, nl.m_input_node_index):
                            break
                    alreadyExisting = False
                    for linkIndex in range(int(0), int(linkCount)):
                        link = delegate.get_link(linkIndex)
                        if not memcmp(link, nl, sizeof(Link)):
                            alreadyExisting = True
                            break
                    if not alreadyExisting:
                        for linkIndex in range(int(0), int(linkCount)):
                            link = delegate.get_link(linkIndex)
                            if link.m_output_node_index == nl.m_output_node_index  and  link.m_output_slot_index == nl.m_output_slot_index:
                                delegate.del_link(linkIndex)
                                break
                        delegate.add_link(nl.m_input_node_index, nl.m_input_slot_index, nl.m_output_node_index, nl.m_output_slot_index)
            if nodeOperation == NO_None  and  io.mouse_clicked[0]  and  not bDrawOnly:
                nodeOperation = NO_EditingLink
                editingInput = i == 0
                editingNodeSource = closestPos
                editingNodeIndex = nodeIndex
                editingSlotIndex = closestConn
                if editingInput:
                    for linkIndex in range(int(0), int(linkCount)):
                        link = delegate.get_link(linkIndex)
                        if link.m_output_node_index == nodeIndex  and  link.m_output_slot_index == closestConn:
                            delegate.del_link(linkIndex)
                            break
    return hoverSlot

def draw_grid(drawList, windowPos, viewState, canvasSize, gridColor, gridColor2, gridSize):
    """DrawGrid()."""
    gridSpace = gridSize * viewState.m_factor
    divx = static_cast(-viewState.m_position[0] / gridSize)
    divy = static_cast(-viewState.m_position[1] / gridSize)
    for x in range(int(math.fmod(viewState.m_position[0] * viewState.m_factor, gridSpace)), int(canvasSize[0]), gridSpace):
        tenth = not (divx % 10)
        drawList.add_line((windowPos[0] + x, windowPos[1] + 0.0), (windowPos[0] + x, windowPos[1] + canvasSize[1]), (gridColor2 if tenth else gridColor))
    for y in range(int(math.fmod(viewState.m_position[1] * viewState.m_factor, gridSpace)), int(canvasSize[1]), gridSpace):
        tenth = not (divy % 10)
        drawList.add_line((windowPos[0] + 0.0, windowPos[1] + y), (windowPos[0] + canvasSize[0], windowPos[1] + y), (gridColor2 if tenth else gridColor))

def draw_node(drawList, nodeIndex, offset, factor, delegate, overInput, options, inMinimap, viewPort):
    """DrawNode()."""
    io = im.get_io()
    node = delegate.get_node(nodeIndex)
    assert((node.m_rect.get_width() != 0.)  and  (node.m_rect.get_height() != 0.)  and  "Nodes must have a non-zero rect.")
    nodeTemplate = delegate.get_template(node.m_template_index)
    nodeRectangleMin = offset + node.m_rect.min * factor
    old_any_active = im.is_any_item_active()
    im.set_cursor_screen_pos(nodeRectangleMin)
    nodeSize = node.m_rect.get_size() * factor
    drawList.channels_set_current(1)
    InputsCount = nodeTemplate.m_input_count
    OutputsCount = nodeTemplate.m_output_count
    im.set_cursor_screen_pos(nodeRectangleMin)
    maxHeight = min(viewPort.max[1], nodeRectangleMin[1] + nodeSize[1]) - nodeRectangleMin[1]
    maxWidth = min(viewPort.max[0], nodeRectangleMin[0] + nodeSize[0]) - nodeRectangleMin[0]
    im.invisible_button("node", (maxWidth, maxHeight))
    nodeMovingActive = im.is_item_active()
    nodeWidgetsActive = (not old_any_active  and  im.is_any_item_active())
    nodeRectangleMax = nodeRectangleMin + nodeSize
    nodeHovered = False
    if im.is_item_hovered()  and  nodeOperation == NO_None  and  not overInput:
        nodeHovered = True
    if im.is_window_focused():
        if (nodeWidgetsActive  or  nodeMovingActive)  and  not inMinimap:
            if not node.m_selected:
                if not io.key_shift:
                    nodeCount = delegate.get_node_count()
                    for i in range(int(0), int(nodeCount)):
                        delegate.select_node(i, False)
                delegate.select_node(nodeIndex, True)
    if nodeMovingActive  and  io.mouse_down[0]  and  nodeHovered  and  not inMinimap:
        if nodeOperation != NO_MovingNodes:
            nodeOperation = NO_MovingNodes
    currentSelectedNode = node.m_selected
    node_bg_color = (nodeTemplate.m_background_color_over if nodeHovered else nodeTemplate.m_background_color)
    drawList.add_rect(nodeRectangleMin, nodeRectangleMax, (options.m_selected_node_border_color if currentSelectedNode else options.m_node_border_color), options.m_rounding, im.DrawFlags.ROUND_CORNERS_ALL, (options.m_border_selection_thickness if currentSelectedNode else options.m_border_thickness))
    imgPos = (nodeRectangleMin[0] + 14, nodeRectangleMin[1] + 25)
    imgSize = (imgPos[0] - nodeRectangleMax[0] + -5, imgPos[1] - nodeRectangleMax[1] + -5)
    imgSizeComp = std.min(imgSize[0], imgSize[1])
    drawList.add_rect_filled(nodeRectangleMin, nodeRectangleMax, node_bg_color, options.m_rounding)
    imgPosMax = (imgPos[0] + imgSizeComp, imgPos[1] + imgSizeComp)
    drawList.add_rect_filled(nodeRectangleMin, (nodeRectangleMax[0], nodeRectangleMin[1] + 20), nodeTemplate.m_header_color, options.m_rounding)
    drawList.push_clip_rect(nodeRectangleMin, (nodeRectangleMax[0], nodeRectangleMin[1] + 20), True)
    drawList.add_text((nodeRectangleMin[0] + 2, nodeRectangleMin[1] + 2), im.col32(0, 0, 0, 255), node.m_name)
    drawList.pop_clip_rect()
    customDrawRect = ImRect((nodeRectangleMin[0] + options.m_rounding, nodeRectangleMin[1] + 20 + options.m_rounding), (nodeRectangleMax[0] - options.m_rounding, nodeRectangleMax[1] - options.m_rounding))
    if customDrawRect.max[1] > customDrawRect.min[1]  and  customDrawRect.max[0] > customDrawRect.min[0]:
        delegate.custom_draw(drawList, customDrawRect, nodeIndex)
    return nodeHovered

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def draw_mini_map(drawList, delegate, viewState, options, windowPos, c
pass
# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def show(delegate, options, viewState, enabled, fit):
pass
def edit_options(options):
    """EditOptions()."""
    updated = False
    if im.collapsing_header("Colors", None):
        backgroundColor = options.m_background_color
        gridColor = options.m_grid_color
        selectedNodeBorderColor = options.m_selected_node_border_color
        nodeBorderColor = options.m_node_border_color
        quadSelection = options.m_quad_selection
        quadSelectionBorder = options.m_quad_selection_border
        defaultSlotColor = options.m_default_slot_color
        frameFocus = options.m_frame_focus
        updated, backgroundColor = im.color_edit4("Background", backgroundColor)
        updated, gridColor = im.color_edit4("Grid", gridColor)
        updated, selectedNodeBorderColor = im.color_edit4("Selected Node Border", selectedNodeBorderColor)
        updated, nodeBorderColor = im.color_edit4("Node Border", nodeBorderColor)
        updated, quadSelection = im.color_edit4("Quad Selection", quadSelection)
        updated, quadSelectionBorder = im.color_edit4("Quad Selection Border", quadSelectionBorder)
        updated, defaultSlotColor = im.color_edit4("Default Slot", defaultSlotColor)
        updated, frameFocus = im.color_edit4("Frame when has focus", frameFocus)
        options.m_background_color = backgroundColor
        options.m_grid_color = gridColor
        options.m_selected_node_border_color = selectedNodeBorderColor
        options.m_node_border_color = nodeBorderColor
        options.m_quad_selection = quadSelection
        options.m_quad_selection_border = quadSelectionBorder
        options.m_default_slot_color = defaultSlotColor
        options.m_frame_focus = frameFocus
    if im.collapsing_header("Options", None):
        updated = updated | im.input_float4("Minimap", options.m_minimap.min[0])
        updated = updated | im.input_float("Line Thickness", options.m_line_thickness)
        updated = updated | im.input_float("Grid Size", options.m_grid_size)
        updated = updated | im.input_float("Rounding", options.m_rounding)
        updated = updated | im.input_float("Zoom Ratio", options.m_zoom_ratio)
        updated = updated | im.input_float("Zoom Lerp Factor", options.m_zoom_lerp_factor)
        updated = updated | im.input_float("Border Selection Thickness", options.m_border_selection_thickness)
        updated = updated | im.input_float("Border Thickness", options.m_border_thickness)
        updated = updated | im.input_float("Slot Radius", options.m_node_slot_radius)
        updated = updated | im.input_float("Slot Hover Factor", options.m_node_slot_hover_factor)
        updated = updated | im.input_float2("Zoom min/max", options.m_min_zoom)
        updated = updated | im.input_float("Slot Hover Factor", options.m_snap)
        if im.radio_button("Curved Links", options.m_display_links_as_curves):
            options.m_display_links_as_curves = not options.m_display_links_as_curves
            updated = True
        if im.radio_button("Straight Links", not options.m_display_links_as_curves):
            options.m_display_links_as_curves = not options.m_display_links_as_curves
            updated = True
        updated = updated | im.checkbox("Allow Quad Selection", options.m_allow_quad_selection)
        updated = updated | im.checkbox("Render Grid", options.m_render_grid)
        updated = updated | im.checkbox("Draw IO names on hover", options.m_draw_io_name_on_hover)
    return updated