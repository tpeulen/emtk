"""A node editor: nodes with pins, links between them, on a pannable grid.

This is emtk's node editor. Like the rest of emtk it is immediate mode -- you
call :func:`begin_node` every frame and the editor remembers where the node was
dragged to -- and like the rest of emtk it is a **re-implementation**, written
by reading rather than by binding. What it was read from, and why that one, is
worth stating because five candidates were measured before this was written.

Which reference, and why
------------------------
Dear ImGui's *Useful Extensions* page lists five node editors. Ported through
``tools/autoport`` and measured, they separate cleanly:

======================  =====  ==========================================
extension               C++    what decided it
======================  =====  ==========================================
thedmd/imgui-node-      8.7k   the richest -- zoom, groups, node resize --
editor                         and the least portable: 96 templates, 114
                               virtuals, three files of ``imgui_internal``,
                               and its own canvas and drawlist-splitter
                               machinery. 133 flags off the porter.
rokups/ImNodes          1.0k   small and clean, but unmaintained since
                               2022 and too thin: no minimap, no box
                               select, no persisted layout.
Nelarius/imnodes        4.2k   **the one.** Dependency-free, public ImGui
                               API plus ``ImDrawList``, still maintained,
                               and the widest feature set that stays
                               small. 11 templates, no smart pointers, no
                               inheritance at all.
Fattorino/ImNodeFlow    1.6k   retained, not immediate: 85 templates and
                               71 smart pointers, with the real logic in
                               a ``.inl`` of templates. A port is a
                               rewrite.
Azzinoth/Visual-        1.9k   an application framework, not a library --
NodeSystem                     pulls in glm and jsoncpp, and its node
                               model is its own.
======================  =====  ==========================================

So the model here is Nelarius/imnodes: its API names, its layout arithmetic and
its interaction rules. The cubic-bezier control points, the pin coordinate on
the node edge, the object pools that survive a frame, and the dark palette are
all its, transliterated under the rules in ``README.md``.

What this adds that imnodes does not have
-----------------------------------------
**Zoom -- of the canvas, not of the glyphs.** imnodes has none at all, and a
graph of forty nodes is unreadable without something. The transform is
:class:`Canvas`, one scale and one translation, taken in shape from
imgui-node-editor's ``imgui_canvas.cpp`` -- the one thing worth having out of
the candidate that lost.

Be exact about what it scales, because the difference is visible and the wrong
expectation produces bug reports: **node positions, padding, pin sizes, corner
rounding, link thickness and the grid** follow the zoom; **text and the widgets
inside a node do not**. That is not a shortcut, it is what emtk can currently
do -- both shipped painters report a fixed glyph cell, so ``push_font(font,
size)`` changes no measurement, and a node's pixel size is the same at every
zoom. Zooming out therefore *spreads the nodes apart* and shrinks nothing
inside them, which is what you want for finding your way around a large graph
and is not what you want for reading a thumbnail of one. Scaling glyphs needs a
size-aware atlas in emtk, which is its own piece of work.

Everything that consumes the zoom knows this. :meth:`EditorContext.fit_to_content`
in particular solves for it rather than assuming node size scales -- assuming it
overshoots badly at small zooms and pushes half the graph off screen.

Zoom is opt-in per editor (:meth:`EditorContext.set_zoom`), and off by default,
so an editor that never sets it behaves exactly as imnodes does.

Using it
--------
::

    ctx = nodes.EditorContext()

    def gui():
        nodes.begin_node_editor(ctx)

        nodes.begin_node(1)
        nodes.begin_node_title_bar()
        im.text("Constant")
        nodes.end_node_title_bar()
        nodes.begin_output_attribute(2)
        im.text("value")
        nodes.end_output_attribute()
        nodes.end_node()

        nodes.link(100, 2, 7)
        nodes.end_node_editor()

        created = nodes.is_link_created()
        if created is not None:
            start_pin, end_pin = created

The ids are yours and must be unique within their kind -- a node id and a pin
id may collide, two node ids may not. They are the only handle the editor has
on a node, so reusing one for a different node moves the old one's position
onto the new one.
"""
from __future__ import annotations

import math
import typing

from . import im

__all__ = [
    "Canvas",
    "Col",
    "EditorContext",
    "MiniMapLocation",
    "PinShape",
    "Style",
    "StyleFlags",
    "begin_input_attribute",
    "begin_node",
    "begin_node_editor",
    "begin_node_title_bar",
    "begin_output_attribute",
    "begin_static_attribute",
    "clear_link_selection",
    "clear_node_selection",
    "editor_context",
    "end_input_attribute",
    "end_node",
    "end_node_editor",
    "end_node_title_bar",
    "end_output_attribute",
    "end_static_attribute",
    "get_node_dimensions",
    "get_node_grid_space_pos",
    "get_node_screen_space_pos",
    "get_selected_links",
    "get_selected_nodes",
    "is_any_attribute_active",
    "is_editor_hovered",
    "is_link_created",
    "is_link_destroyed",
    "is_link_dropped",
    "is_link_hovered",
    "is_link_selected",
    "is_link_started",
    "is_node_hovered",
    "is_node_selected",
    "is_pin_hovered",
    "link",
    "mini_map",
    "pop_color_style",
    "pop_style_var",
    "push_color_style",
    "push_style_var",
    "select_link",
    "select_node",
    "set_node_draggable",
    "set_node_grid_space_pos",
    "set_node_screen_space_pos",
    "snap_node_to_grid",
    "style_colors_dark",
    "style_colors_light",
]


class Col:
    """Named entries in the colour palette, for :func:`push_color_style`.

    The names are imnodes' ``ImNodesCol_`` values with the prefix dropped, so a
    C++ example translates by deleting it: ``ImNodesCol_TitleBar`` becomes
    ``Col.TITLE_BAR``.
    """

    NODE_BACKGROUND = "node_background"
    NODE_BACKGROUND_HOVERED = "node_background_hovered"
    NODE_BACKGROUND_SELECTED = "node_background_selected"
    NODE_OUTLINE = "node_outline"
    TITLE_BAR = "title_bar"
    TITLE_BAR_HOVERED = "title_bar_hovered"
    TITLE_BAR_SELECTED = "title_bar_selected"
    LINK = "link"
    LINK_HOVERED = "link_hovered"
    NODE_LABEL = "node_label"
    NODE_LABEL_PLATE = "node_label_plate"
    LINK_SELECTED = "link_selected"
    PIN = "pin"
    PIN_HOVERED = "pin_hovered"
    BOX_SELECTOR = "box_selector"
    BOX_SELECTOR_OUTLINE = "box_selector_outline"
    STICK_HINT = "stick_hint"
    GRID_BACKGROUND = "grid_background"
    GRID_LINE = "grid_line"
    GRID_LINE_PRIMARY = "grid_line_primary"
    MINI_MAP_BACKGROUND = "mini_map_background"
    MINI_MAP_OUTLINE = "mini_map_outline"
    MINI_MAP_NODE_BACKGROUND = "mini_map_node_background"
    MINI_MAP_NODE_BACKGROUND_SELECTED = "mini_map_node_background_selected"
    MINI_MAP_NODE_OUTLINE = "mini_map_node_outline"
    MINI_MAP_LINK = "mini_map_link"
    MINI_MAP_LINK_SELECTED = "mini_map_link_selected"
    MINI_MAP_CANVAS = "mini_map_canvas"
    MINI_MAP_CANVAS_OUTLINE = "mini_map_canvas_outline"


class LinkRouting:
    """How a link finds its way from one node to another.

    ``PIN`` is imnodes': the curve leaves a pin rightwards and arrives at one
    leftwards, which reads well when a graph flows left to right and every node
    is a box with its ports down the sides.

    ``ARC`` is what a diagram wants. It ignores the pins and runs **rim to
    rim** between the two nodes -- along the line joining their centres,
    stopping at each node's edge -- with a slight bow. Three things follow from
    that and each is why the pin routing looks wrong on a network:

    * no horizontal stub. A pin-routed edge always leaves sideways, so a node
      directly *above* another is joined by a curve that goes out to the right,
      turns around and comes back.
    * the arrow lands on the rim, pointing at the node's centre, wherever the
      node happens to be.
    * the bow separates edges that would otherwise be drawn on top of each
      other, and gives the eye something to follow between two distant marks.
    """

    PIN = "pin"
    ARC = "arc"


class NodeShape:
    """How a node is drawn.

    ``BOX`` is imnodes' node: a titled rectangle sized by its contents, which
    is what a dataflow graph wants -- the node *is* its controls.

    ``DISC`` is a mark: a shaded circle of a fixed radius with its label on a
    plate underneath. A graph of two hundred parameters has nothing to put
    inside a node and everything to gain from being small enough to read, and
    a box per parameter is mostly padding. Both are node-link diagrams; they
    differ in whether the node has an interior worth showing.
    """

    BOX = "box"
    DISC = "disc"


class PinShape:
    """How a pin is drawn. imnodes' ``ImNodesPinShape_``, plus one.

    ``NONE`` is the addition: the pin is still there -- it is hit-tested, links
    land on it, it reports hover -- it is simply not drawn. A graph of discs
    wants that: the mark *is* the connector, and a second dot stuck on its edge
    is clutter that says nothing. Leaving the pin out entirely instead would
    mean the node could not be linked at all.
    """

    NONE = "none"
    CIRCLE = "circle"
    CIRCLE_FILLED = "circle_filled"
    TRIANGLE = "triangle"
    TRIANGLE_FILLED = "triangle_filled"
    QUAD = "quad"
    QUAD_FILLED = "quad_filled"


class StyleFlags:
    """Which decorations the editor draws. Combined with ``|``."""

    NONE = 0
    NODE_OUTLINE = 1 << 0
    GRID_LINES = 1 << 2
    GRID_LINES_PRIMARY = 1 << 3
    GRID_SNAPPING = 1 << 4


class MiniMapLocation:
    """Which corner :func:`mini_map` sits in."""

    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"


#: imnodes' ``StyleColorsDark``, which is its default and ours. Colours are
#: ``(r, g, b, a)`` bytes -- emtk's convention, not ImGui's floats. Writing a
#: float here does not raise; it draws black.
_DARK: dict = {
    Col.NODE_BACKGROUND: (50, 50, 50, 255),
    Col.NODE_BACKGROUND_HOVERED: (75, 75, 75, 255),
    Col.NODE_BACKGROUND_SELECTED: (75, 75, 75, 255),
    Col.NODE_OUTLINE: (100, 100, 100, 255),
    Col.TITLE_BAR: (41, 74, 122, 255),
    Col.TITLE_BAR_HOVERED: (66, 150, 250, 255),
    Col.TITLE_BAR_SELECTED: (66, 150, 250, 255),
    Col.NODE_LABEL: (236, 239, 244, 255),
    # Translucent, and dark rather than tinted: in a dense graph neighbouring
    # labels overlap each other and the edges between them, and the plate is
    # what keeps the topmost one readable instead of both becoming a smear.
    Col.NODE_LABEL_PLATE: (18, 20, 24, 190),
    Col.LINK: (61, 133, 224, 200),
    Col.LINK_HOVERED: (66, 150, 250, 255),
    Col.LINK_SELECTED: (66, 150, 250, 255),
    Col.PIN: (53, 150, 250, 180),
    Col.PIN_HOVERED: (53, 150, 250, 255),
    Col.BOX_SELECTOR: (61, 133, 224, 30),
    Col.BOX_SELECTOR_OUTLINE: (61, 133, 224, 150),
    # The accent, at full strength: this is drawn for a few frames during a
    # drag and has to read instantly, not blend into the node under it.
    Col.STICK_HINT: (66, 150, 250, 220),
    Col.GRID_BACKGROUND: (40, 40, 50, 200),
    Col.GRID_LINE: (200, 200, 200, 40),
    Col.GRID_LINE_PRIMARY: (240, 240, 240, 60),
    Col.MINI_MAP_BACKGROUND: (25, 25, 25, 150),
    Col.MINI_MAP_OUTLINE: (150, 150, 150, 100),
    Col.MINI_MAP_NODE_BACKGROUND: (200, 200, 200, 100),
    Col.MINI_MAP_NODE_BACKGROUND_SELECTED: (200, 200, 200, 255),
    Col.MINI_MAP_NODE_OUTLINE: (200, 200, 200, 100),
    Col.MINI_MAP_LINK: (61, 133, 224, 200),
    Col.MINI_MAP_LINK_SELECTED: (66, 150, 250, 255),
    Col.MINI_MAP_CANVAS: (200, 200, 200, 25),
    Col.MINI_MAP_CANVAS_OUTLINE: (200, 200, 200, 200),
}

#: The same palette on a light background. imnodes' ``StyleColorsLight``.
_LIGHT: dict = dict(
    _DARK,
    **{
        Col.NODE_BACKGROUND: (240, 240, 240, 255),
        Col.NODE_BACKGROUND_HOVERED: (240, 240, 240, 255),
        Col.NODE_BACKGROUND_SELECTED: (240, 240, 240, 255),
        Col.NODE_OUTLINE: (100, 100, 100, 255),
        Col.TITLE_BAR: (248, 248, 248, 255),
        Col.TITLE_BAR_HOVERED: (209, 209, 209, 255),
        Col.TITLE_BAR_SELECTED: (209, 209, 209, 255),
        Col.LINK: (66, 150, 250, 100),
        Col.LINK_HOVERED: (66, 150, 250, 242),
        Col.LINK_SELECTED: (66, 150, 250, 242),
        Col.PIN: (66, 150, 250, 160),
        Col.PIN_HOVERED: (66, 150, 250, 255),
        Col.NODE_LABEL: (24, 26, 30, 255),
        Col.NODE_LABEL_PLATE: (250, 250, 250, 190),
        Col.GRID_BACKGROUND: (225, 225, 225, 255),
        Col.GRID_LINE: (180, 180, 180, 100),
        Col.GRID_LINE_PRIMARY: (120, 120, 120, 100),
    },
)


class Style:
    """Sizes, thicknesses and colours, all of imnodes' defaults.

    Attributes
    ----------
    grid_spacing : float
        Pixels between grid lines, in grid space.
    node_corner_rounding : float
        Corner radius of the node rectangle.
    node_padding : tuple
        ``(x, y)`` inset between the node's border and its contents.
    node_border_thickness : float
        Outline width, drawn only when :attr:`StyleFlags.NODE_OUTLINE` is set.
    link_thickness : float
        Width of a link curve.
    link_line_segments_per_length : float
        How finely a bezier is flattened: segments per pixel of chord length.
    link_hover_distance : float
        How near the pointer must come to a link to hover it.
    link_routing : str
        A :class:`LinkRouting`. ``PIN`` is the node editor's; ``ARC`` is the
        diagram's rim-to-rim curve.
    link_bow : tuple
        ``(fraction, minimum, maximum)`` for an arc's curvature: the mid-point
        is pushed off the chord by ``fraction`` of the chord's length, clamped
        into the range. A constant offset instead would make a short edge a
        semicircle and leave a long one looking straight.
    link_two_way_offset : float
        How far apart the two arcs of a mutual pair are pushed, so that A→B
        and B→A do not land on each other and read as one edge.
    pin_circle_radius, pin_quad_side_length, pin_triangle_side_length : float
        The three pin shapes' sizes.
    pin_line_thickness : float
        Outline width for the unfilled pin shapes.
    pin_hover_radius : float
        How near the pointer must come to a pin to hover it. Larger than the
        pin, deliberately -- a 4-pixel target is not clickable.
    pin_offset : float
        How far outside the node edge a pin sits.
    stick_distance : float
        How near, in screen pixels, a dragged node's edge must come to another
        node's before it sticks flush against it.
    mini_map_padding, mini_map_offset : tuple
        The minimap's inner padding and its inset from the editor corner.
    flags : int
        A combination of :class:`StyleFlags`.
    colors : dict
        The palette, keyed by :class:`Col`.
    """

    def __init__(self) -> None:
        self.grid_spacing: float = 24.0
        self.node_corner_rounding: float = 4.0
        self.node_padding: tuple = (8.0, 8.0)
        self.node_border_thickness: float = 1.0
        self.link_thickness: float = 3.0
        self.link_line_segments_per_length: float = 0.1
        self.link_hover_distance: float = 10.0
        self.link_routing: str = LinkRouting.PIN
        self.link_bow: tuple = (0.12, 10.0, 22.0)
        self.link_two_way_offset: float = 7.0
        self.pin_circle_radius: float = 4.0
        self.pin_quad_side_length: float = 7.0
        self.pin_triangle_side_length: float = 9.5
        self.pin_line_thickness: float = 1.0
        self.pin_hover_radius: float = 10.0
        self.pin_offset: float = 0.0
        self.stick_distance: float = 8.0
        self.node_disc_radius: float = 13.0
        #: Circles in a disc's shading ramp. Three reads as three hard rings.
        self.node_shade_steps: int = 16
        #: How far below a disc its label sits, and the inset of the plate
        #: drawn behind it.
        self.node_label_gap: float = 7.0
        self.node_label_padding: tuple = (4.0, 1.0)
        #: Labels longer than this are elided, so one long parameter name
        #: cannot blanket its neighbours.
        self.node_label_max_width: float = 96.0
        #: Length and half-width of a link's arrowhead, in pixels before zoom.
        self.link_arrow_size: tuple = (9.0, 4.5)
        self.mini_map_padding: tuple = (8.0, 8.0)
        self.mini_map_offset: tuple = (4.0, 4.0)
        self.flags: int = StyleFlags.NODE_OUTLINE | StyleFlags.GRID_LINES
        self.colors: dict = dict(_DARK)


def style_colors_dark(style: "Style") -> None:
    """Load the dark palette into `style`.

    Parameters
    ----------
    style : Style
        The style to overwrite. Its non-colour metrics are left alone.
    """
    style.colors = dict(_DARK)


def style_colors_light(style: "Style") -> None:
    """Load the light palette into `style`.

    Parameters
    ----------
    style : Style
        The style to overwrite. Its non-colour metrics are left alone.
    """
    style.colors = dict(_LIGHT)


class Canvas:
    """The grid-space to screen-space transform: one scale and one translation.

    imnodes has only the translation -- it pans and does not zoom. The scale is
    added here, in the shape imgui-node-editor's canvas uses, because a graph
    of any size is unreadable without it and emtk's fonts take a size at
    ``push_font`` time rather than being baked at one.

    Three spaces, and mixing them up is the bug this class exists to prevent:

    *grid space*
        where a node's position is stored. Independent of pan and zoom, so it
        is what gets serialised.
    *editor space*
        grid space after pan and zoom, relative to the editor's top-left.
    *screen space*
        editor space plus the editor's origin on screen. What the drawlist
        takes.

    Attributes
    ----------
    panning : tuple
        ``(x, y)``, in editor space, added after scaling.
    zoom : float
        The scale factor. ``1.0`` is imnodes' behaviour exactly.
    origin : tuple
        The editor's top-left in screen space, set each frame by
        :func:`begin_node_editor`.
    """

    #: Zoom is clamped to this range. Below the lower bound text stops being
    #: legible and hit targets stop being hittable; above the upper one a
    #: single node fills the viewport and panning becomes useless.
    ZOOM_RANGE: tuple = (0.15, 4.0)

    def __init__(self) -> None:
        self.panning: tuple = (0.0, 0.0)
        self.zoom: float = 1.0
        self.origin: tuple = (0.0, 0.0)

    def to_screen(self, pos: tuple) -> tuple:
        """Convert a grid-space point to screen space.

        Parameters
        ----------
        pos : tuple
            ``(x, y)`` in grid space.

        Returns
        -------
        tuple
            ``(x, y)`` in screen space.
        """
        return (
            self.origin[0] + pos[0] * self.zoom + self.panning[0],
            self.origin[1] + pos[1] * self.zoom + self.panning[1],
        )

    def to_grid(self, pos: tuple) -> tuple:
        """Convert a screen-space point back to grid space.

        Parameters
        ----------
        pos : tuple
            ``(x, y)`` in screen space.

        Returns
        -------
        tuple
            ``(x, y)`` in grid space.
        """
        return (
            (pos[0] - self.origin[0] - self.panning[0]) / self.zoom,
            (pos[1] - self.origin[1] - self.panning[1]) / self.zoom,
        )

    def zoom_at(self, screen_pos: tuple, factor: float) -> None:
        """Scale by `factor`, keeping the grid point under `screen_pos` fixed.

        Zooming about the pointer rather than about the origin is what makes a
        wheel zoom feel attached to the content; zooming about the origin walks
        the thing you were looking at off the edge of the viewport.

        Parameters
        ----------
        screen_pos : tuple
            The point to hold still, in screen space -- usually the pointer.
        factor : float
            Multiplier on the current zoom. Clamped so the result stays inside
            :data:`ZOOM_RANGE`.
        """
        before = self.to_grid(screen_pos)
        lo, hi = self.ZOOM_RANGE
        self.zoom = min(hi, max(lo, self.zoom * factor))
        after = self.to_grid(screen_pos)
        self.panning = (
            self.panning[0] + (after[0] - before[0]) * self.zoom,
            self.panning[1] + (after[1] - before[1]) * self.zoom,
        )


class _Node:
    """One node's state, carried across frames by the editor's pool."""

    def __init__(self, node_id: int) -> None:
        self.id: int = node_id
        #: Top-left in grid space. The only geometry that is serialised.
        self.origin: tuple = (0.0, 0.0)
        #: Screen-space rect ``(x0, y0, x1, y1)``, remeasured every frame.
        self.rect: tuple = (0.0, 0.0, 0.0, 0.0)
        #: Screen-space rect of whatever the title bar drew, or ``None``.
        self.title_rect: typing.Optional[tuple] = None
        self.draggable: bool = True
        #: How this node draws. See :class:`NodeShape`.
        self.shape: str = NodeShape.BOX
        self.radius: float = 0.0
        #: The text under a disc. Boxes label themselves with a title bar.
        self.label: str = ""
        #: Pin ids belonging to this node, rebuilt every frame in draw order.
        self.pins: list = []
        #: Set while the node was submitted this frame. A node that stops being
        #: submitted keeps its entry -- and therefore its position -- so a graph
        #: that hides a node and shows it again does not lose where it was.
        self.alive: bool = True


class _Pin:
    """One attribute's state: which node owns it, and where it ended up."""

    def __init__(self, pin_id: int) -> None:
        self.id: int = pin_id
        self.node_id: typing.Optional[int] = None
        #: ``"input"``, ``"output"`` or ``"static"``.
        self.kind: str = "input"
        self.shape: str = PinShape.CIRCLE_FILLED
        #: Screen-space rect of the attribute's contents.
        self.rect: tuple = (0.0, 0.0, 0.0, 0.0)
        #: Where the pin is drawn, in screen space. Derived from the node rect
        #: and the attribute rect, so it is only valid after the node ends.
        self.pos: tuple = (0.0, 0.0)


class _Link:
    """One submitted link. Links are not pooled -- they are pure per-frame."""

    def __init__(self, link_id: int, start_pin: int, end_pin: int) -> None:
        self.id: int = link_id
        self.start_pin: int = start_pin
        self.end_pin: int = end_pin
        #: Per-link overrides, or ``None`` to take the palette's.
        self.colour: typing.Optional[tuple] = None
        self.thickness: typing.Optional[float] = None
        self.arrow: bool = False


class EditorContext:
    """Everything about one editor that outlives a frame.

    An immediate-mode gui keeps nothing, which is the point -- but *where a node
    was dragged to* has to survive, or dragging does nothing. This is that
    state, and it is yours to hold: construct one, keep it beside your model,
    and hand it to :func:`begin_node_editor` each frame.

    Attributes
    ----------
    style : Style
        This editor's palette and metrics.
    canvas : Canvas
        Its pan and zoom.
    selected_nodes : set
        Node ids, in no order.
    selected_links : set
        Link ids, in no order.
    snap_to_grid : bool
        Round a dragged node's position to the grid. Off by default.
    stick_to_nodes : bool
        Let a dragged node stick flush against the nodes it is dragged near,
        the way a window sticks to another window. On by default, because the
        alternative -- a graph of nodes each two pixels out of line -- is what
        people spend their time correcting by hand.

    Notes
    -----
    The two snapping modes are separate switches rather than one setting with
    three values, because they answer different questions and a user wants
    different combinations of them: the grid is about a *tidy layout*, sticking
    is about *these two nodes touching*. Sticking wins where both would apply,
    since the grid is a background convenience and sticking is a thing the user
    aimed at.
    """

    def __init__(self, style: typing.Optional["Style"] = None) -> None:
        self.style: Style = style or Style()
        self.canvas: Canvas = Canvas()
        self.selected_nodes: set = set()
        self.selected_links: set = set()
        self.snap_to_grid: bool = False
        self.stick_to_nodes: bool = True

        #: ``node_id -> _Node``, surviving frames.
        self._nodes: dict = {}
        #: ``pin_id -> _Pin``, surviving frames.
        self._pins: dict = {}
        #: This frame's links, in submission order.
        self._links: list = []

        # --- interaction, all of it one state machine ------------------
        #: ``None``, ``"node"``, ``"link"``, ``"box"`` or ``"pan"``.
        self._interaction: typing.Optional[str] = None
        self._drag_node: typing.Optional[int] = None
        self._drag_offsets: dict = {}
        self._link_from_pin: typing.Optional[int] = None
        self._link_detached: typing.Optional[int] = None
        self._box_anchor: tuple = (0.0, 0.0)
        #: Ids the dragged node is currently stuck against, for the hint. A
        #: stick with no hint is a small unexplained jump: the user sees the
        #: node move somewhere they did not put it and has no way to tell that
        #: was the feature working.
        self._stuck_to: set = set()

        # --- what the queries below report, all cleared each frame -----
        self._hovered_node: typing.Optional[int] = None
        self._hovered_pin: typing.Optional[int] = None
        self._hovered_link: typing.Optional[int] = None
        self._editor_hovered: bool = False
        self._link_started: typing.Optional[int] = None
        self._link_created: typing.Optional[tuple] = None
        self._link_dropped: typing.Optional[int] = None
        self._link_destroyed: typing.Optional[int] = None
        self._active_attribute: typing.Optional[int] = None

        #: Grid-space bounds of everything submitted last frame, for the
        #: minimap and for "fit to content".
        self._content_bounds: typing.Optional[tuple] = None
        #: Grid-space box of the node *origins* alone, and the largest node in
        #: pixels. Fitting needs the two separately -- see
        #: :meth:`fit_to_content`.
        self._origin_bounds: typing.Optional[tuple] = None
        self._max_node_pixels: tuple = (0.0, 0.0)
        #: The editor's screen-space rect this frame, ``(x, y, w, h)``.
        self._box: tuple = (0.0, 0.0, 0.0, 0.0)
        #: The drawlist the editor is painting into, held from
        #: ``begin_node_editor`` so the channel splitter set up there is
        #: the same one every helper writes to.
        self._draw = None
        #: ``(size_fraction, location)`` when :func:`mini_map` asked for one
        #: this frame, else ``None``.
        self._minimap: typing.Optional[tuple] = None

    # -- geometry the host asks for --------------------------------------

    def node_ids(self) -> list:
        """List the node ids the editor is holding state for.

        Returns
        -------
        list
            Ids in insertion order.
        """
        return list(self._nodes)

    def content_bounds(self) -> typing.Optional[tuple]:
        """Report the grid-space box every submitted node fits in.

        Returns
        -------
        tuple or None
            ``(x0, y0, x1, y1)`` in grid space, or ``None`` when no node has
            been submitted yet.
        """
        return self._content_bounds

    def set_zoom(self, zoom: float) -> None:
        """Set the zoom directly, about the editor's centre.

        Parameters
        ----------
        zoom : float
            The new scale, clamped to :data:`Canvas.ZOOM_RANGE`.
        """
        lo, hi = Canvas.ZOOM_RANGE
        self.canvas.zoom = min(hi, max(lo, float(zoom)))

    def fit_to_content(self, box: tuple, margin: float = 24.0) -> None:
        """Pan and zoom so every node is visible inside `box`.

        Parameters
        ----------
        box : tuple
            The editor's screen-space rect, ``(x, y, w, h)``.
        margin : float
            Pixels of space left around the content.

        Notes
        -----
        Does nothing when no node has been submitted yet: the bounds come from
        the *last* frame, so calling this before the first frame has been drawn
        would fit to an empty box and zoom to the clamp. That is the failure
        that renders a graph as a four-pixel speck, so it is refused rather
        than approximated.

        The arithmetic is not the obvious one, because a node's **pixel size
        does not change with the zoom** (see the module docstring). The graph's
        screen extent is therefore

        .. code-block:: text

            extent = zoom x origin_span + node_size

        -- part scaling, part constant. Solving that for ``zoom`` is what makes
        the fit land; dividing the available width by the whole extent, as a
        fit normally would, treats the constant term as if it shrank too and
        chooses a zoom that leaves the outermost nodes hanging off the edge.
        """
        bounds = self._origin_bounds
        if bounds is None:
            return
        x0, y0, x1, y1 = bounds
        node_w, node_h = self._max_node_pixels
        span_x, span_y = x1 - x0, y1 - y0
        avail_w = max(box[2] - 2 * margin - node_w, 1.0)
        avail_h = max(box[3] - 2 * margin - node_h, 1.0)

        lo, hi = Canvas.ZOOM_RANGE
        zoom = hi
        if span_x > 1e-6:
            zoom = min(zoom, avail_w / span_x)
        if span_y > 1e-6:
            zoom = min(zoom, avail_h / span_y)
        zoom = min(hi, max(lo, zoom))
        self.canvas.zoom = zoom

        # Centre what will actually be on screen: the origins scaled by the new
        # zoom, plus the node that hangs furthest past the last origin.
        extent_x = span_x * zoom + node_w
        extent_y = span_y * zoom + node_h
        self.canvas.panning = (
            (box[2] - extent_x) * 0.5 - x0 * zoom,
            (box[3] - extent_y) * 0.5 - y0 * zoom,
        )


# --------------------------------------------------------------------------
# The current editor. Immediate mode needs one, and threading it through every
# call is what imnodes avoids with a global; the same trade is taken here, with
# the context manager below as the safe spelling.
# --------------------------------------------------------------------------

#: Drawlist channels, low to high. See :func:`begin_node_editor` for why
#: three and why in this order.
_CHANNEL_LINKS: int = 0
_CHANNEL_NODE: int = 1
_CHANNEL_CONTENT: int = 2
_CHANNEL_COUNT: int = 3

#: The editor :func:`begin_node_editor` is currently inside, or ``None``.
_current: typing.Optional[EditorContext] = None

#: Which scope the caller is in, so a mismatched begin/end is an error with a
#: name rather than an ``IndexError`` three functions away.
_scope: str = "none"

#: The node :func:`begin_node` is currently inside.
_node: typing.Optional[_Node] = None

#: The pin :func:`begin_input_attribute` and friends are currently inside.
_pin: typing.Optional[_Pin] = None

#: Colours and style vars pushed this frame, popped in reverse.
_color_stack: list = []
_style_stack: list = []


class _EditorScope:
    """Context-manager form of :func:`begin_node_editor`/:func:`end_node_editor`."""

    def __init__(self, ctx: EditorContext, box: typing.Optional[tuple]) -> None:
        self._ctx = ctx
        self._box = box

    def __enter__(self) -> EditorContext:
        """Begin the editor.

        Returns
        -------
        EditorContext
            The editor, so ``with editor_context(ctx) as ed:`` reads well.
        """
        begin_node_editor(self._ctx, self._box)
        return self._ctx

    def __exit__(self, *_exc) -> bool:
        """End the editor, even if the body raised.

        Returns
        -------
        bool
            ``False``, so an exception in the body propagates.
        """
        end_node_editor()
        return False


def editor_context(ctx: EditorContext, box: typing.Optional[tuple] = None) -> _EditorScope:
    """Scope an editor to a ``with`` block.

    Parameters
    ----------
    ctx : EditorContext
        The editor to draw.
    box : tuple, optional
        ``(x, y, w, h)`` in screen space. The available content region when
        omitted.

    Returns
    -------
    _EditorScope
        A context manager that begins and ends the editor.
    """
    return _EditorScope(ctx, box)


def _require(scope: str, who: str) -> EditorContext:
    """Assert the caller is in `scope` and return the current editor.

    Parameters
    ----------
    scope : str
        The scope `who` must be called from.
    who : str
        The calling function's name, for the message.

    Returns
    -------
    EditorContext
        The current editor.

    Raises
    ------
    RuntimeError
        When called from the wrong scope, naming both scopes. An unbalanced
        begin/end otherwise surfaces as an unrelated failure much later.
    """
    if _scope != scope or _current is None:
        raise RuntimeError(
            f"{who}() must be called inside {scope} scope; currently in {_scope!r} scope"
        )
    return _current


# --------------------------------------------------------------------------
# Style stacks
# --------------------------------------------------------------------------


def push_color_style(which: str, color: tuple) -> None:
    """Override one palette entry until the matching :func:`pop_color_style`.

    Parameters
    ----------
    which : str
        A :class:`Col` name.
    color : tuple
        ``(r, g, b, a)`` bytes.
    """
    ctx = _current
    if ctx is None:
        raise RuntimeError("push_color_style() needs an editor; call begin_node_editor() first")
    _color_stack.append((which, ctx.style.colors.get(which)))
    ctx.style.colors[which] = color


def pop_color_style(count: int = 1) -> None:
    """Undo `count` colour overrides.

    Parameters
    ----------
    count : int
        How many to pop.
    """
    ctx = _current
    if ctx is None:
        return
    for _ in range(count):
        if not _color_stack:
            return
        which, previous = _color_stack.pop()
        if previous is None:
            ctx.style.colors.pop(which, None)
        else:
            ctx.style.colors[which] = previous


def push_style_var(which: str, value) -> None:
    """Override one :class:`Style` attribute until the matching pop.

    Parameters
    ----------
    which : str
        The attribute name, e.g. ``"node_padding"``.
    value : object
        Its new value.
    """
    ctx = _current
    if ctx is None:
        raise RuntimeError("push_style_var() needs an editor; call begin_node_editor() first")
    _style_stack.append((which, getattr(ctx.style, which)))
    setattr(ctx.style, which, value)


def pop_style_var(count: int = 1) -> None:
    """Undo `count` style-var overrides.

    Parameters
    ----------
    count : int
        How many to pop.
    """
    ctx = _current
    if ctx is None:
        return
    for _ in range(count):
        if not _style_stack:
            return
        which, previous = _style_stack.pop()
        setattr(ctx.style, which, previous)


# --------------------------------------------------------------------------
# The editor
# --------------------------------------------------------------------------


def begin_node_editor(ctx: EditorContext, box: typing.Optional[tuple] = None) -> None:
    """Start drawing an editor: the grid, and the scope nodes go in.

    Parameters
    ----------
    ctx : EditorContext
        The editor state, held by the caller across frames.
    box : tuple, optional
        ``(x, y, w, h)`` in screen space. The available content region when
        omitted.
    """
    global _current, _scope, _node, _pin
    if _scope != "none":
        raise RuntimeError(f"begin_node_editor() called inside {_scope!r} scope")

    _current, _scope, _node, _pin = ctx, "editor", None, None
    _color_stack.clear()
    _style_stack.clear()

    if box is None:
        origin = im.get_cursor_screen_pos()
        avail = im.get_content_region_avail()
        box = (origin[0], origin[1], max(avail[0], 1.0), max(avail[1], 1.0))
    ctx._box = box
    ctx.canvas.origin = (box[0], box[1])

    # Everything reported by the query functions is per-frame. Clearing here
    # rather than in end_node_editor() is deliberate: a host that raises
    # mid-frame leaves the previous frame's answers in place, and a stale
    # "a link was created" fires the callback twice.
    ctx._links = []
    ctx._hovered_node = None
    ctx._hovered_pin = None
    ctx._hovered_link = None
    ctx._link_started = None
    ctx._link_created = None
    ctx._link_dropped = None
    ctx._link_destroyed = None
    ctx._active_attribute = None
    ctx._minimap = None
    ctx._stuck_to = set()
    for node in ctx._nodes.values():
        node.alive = False
        node.pins = []

    im.begin_child(box, clip=True)
    draw = im.get_window_draw_list()
    ctx._draw = draw
    style = ctx.style
    draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                         style.colors[Col.GRID_BACKGROUND])
    if style.flags & StyleFlags.GRID_LINES:
        _draw_grid(draw, ctx, box)

    # Three channels, and the order they merge in is the order things stack.
    # This is the only way to draw a node's body *behind* contents that have
    # already been submitted: the body's size is not known until the contents
    # have been laid out, so it cannot simply be drawn first.
    #
    #   0  links        under everything, so a curve passes behind a node
    #   1  node bodies  and their pins
    #   2  node contents  the text, sliders and plots a host puts in a node
    #
    # The grid above is drawn *before* the split, straight to the painter, so
    # it is under all three without needing a channel of its own.
    draw.channels_split(_CHANNEL_COUNT)
    draw.channels_set_current(_CHANNEL_CONTENT)

    ctx._editor_hovered = _pointer_over_editor(box)


def _pointer_over_editor(box: tuple) -> bool:
    """Report whether the pointer is over the editor's box, and reachable.

    Parameters
    ----------
    box : tuple
        The editor's screen-space rect, ``(x, y, w, h)``.

    Returns
    -------
    bool
        ``True`` when the pointer is inside `box` and nothing is covering it.

    Notes
    -----
    ``is_window_hovered()`` on its own is not the answer, and getting this
    wrong makes the whole editor dead to the mouse with nothing on screen
    saying why. An editor is a ``begin_child``, and in emtk a child is a
    **layout** scope rather than a window -- so the question that function
    answers is about the enclosing ``im.begin()`` window, which is ``None``
    when a host draws the editor straight into a frame. It then answers
    ``False`` forever.

    So the box is tested directly, and the window test is applied only when
    there *is* a window to test -- which is what keeps a popup drawn over the
    editor from being clicked through.
    """
    mouse = im.get_io().mouse_pos
    inside = (box[0] <= mouse[0] <= box[0] + box[2]
              and box[1] <= mouse[1] <= box[1] + box[3])
    if not inside:
        return False
    return im.get_current_context().current_window is None or im.is_window_hovered()


def _draw_grid(draw, ctx: EditorContext, box: tuple) -> None:
    """Draw the background grid, spaced in grid units and scaled by the zoom.

    Parameters
    ----------
    draw : object
        The drawlist to paint into.
    ctx : EditorContext
        The editor being drawn.
    box : tuple
        Its screen-space rect, ``(x, y, w, h)``.

    Notes
    -----
    The spacing is multiplied by the zoom, so lines stay put relative to the
    content rather than relative to the screen -- which is the difference
    between a grid that reads as graph paper the nodes sit on and one that
    reads as a fixed overlay the nodes slide under. Below a few pixels the
    lines are skipped entirely: at ``zoom = 0.15`` a 24-unit grid is 3.6 pixels
    apart and paints as a solid wash that hides the graph.
    """
    style = ctx.style
    spacing = style.grid_spacing * ctx.canvas.zoom
    if spacing < 6.0:
        return
    pan_x, pan_y = ctx.canvas.panning
    x0, y0, w, h = box
    line = style.colors[Col.GRID_LINE]
    primary = style.colors[Col.GRID_LINE_PRIMARY]
    show_primary = bool(style.flags & StyleFlags.GRID_LINES_PRIMARY)

    start = pan_x % spacing
    index = int(math.floor(-pan_x / spacing)) + 1
    x = start
    while x < w:
        colour = primary if (show_primary and index == 0) else line
        draw.add_line((x0 + x, y0), (x0 + x, y0 + h), colour, 1.0)
        x += spacing
        index += 1

    start = pan_y % spacing
    index = int(math.floor(-pan_y / spacing)) + 1
    y = start
    while y < h:
        colour = primary if (show_primary and index == 0) else line
        draw.add_line((x0, y0 + y), (x0 + w, y0 + y), colour, 1.0)
        y += spacing
        index += 1


def end_node_editor() -> None:
    """Finish the editor: draw the links, run the interactions, close the scope."""
    global _current, _scope
    ctx = _require("editor", "end_node_editor")

    draw = ctx._draw
    _resolve_pin_positions(ctx)
    _update_hover(ctx)

    draw.channels_set_current(_CHANNEL_NODE)
    _draw_pins(ctx, draw)
    draw.channels_set_current(_CHANNEL_LINKS)
    _draw_links(draw, ctx)
    draw.channels_merge()

    # After the merge, so the rubber band and the minimap sit above every node
    # rather than being stacked among them.
    _update_content_bounds(ctx)
    _draw_mini_map(ctx)
    _update_interaction(ctx, draw)
    _draw_stick_hint(ctx, draw)

    im.end_child(clip=True)
    ctx._draw = None
    _current, _scope = None, "none"


def _update_content_bounds(ctx: EditorContext) -> None:
    """Recompute the grid-space box holding every node submitted this frame.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.

    Notes
    -----
    Measured from nodes that were *submitted*, not from every node in the pool:
    a node the host stopped drawing should stop dragging the fit-to-content box
    out to wherever it used to be. The pool keeps its position anyway, so
    showing it again restores it.
    """
    boxes, origins, sizes = [], [], []
    zoom = ctx.canvas.zoom or 1.0
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        x0, y0, x1, y1 = node.rect
        origins.append(node.origin)
        sizes.append((x1 - x0, y1 - y0))
        boxes.append((node.origin[0], node.origin[1],
                      node.origin[0] + (x1 - x0) / zoom,
                      node.origin[1] + (y1 - y0) / zoom))
    if not boxes:
        ctx._content_bounds = None
        ctx._origin_bounds = None
        ctx._max_node_pixels = (0.0, 0.0)
        return
    ctx._content_bounds = (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
    # Kept apart from the box above because they answer different questions.
    # The box is "what the graph covers *at this zoom*", which is what the
    # minimap draws. Fitting needs the two terms unmixed: origins move with the
    # zoom, node sizes do not, so a fit that works from their sum solves the
    # wrong equation and lands short.
    ctx._origin_bounds = (
        min(o[0] for o in origins),
        min(o[1] for o in origins),
        max(o[0] for o in origins),
        max(o[1] for o in origins),
    )
    ctx._max_node_pixels = (max(s[0] for s in sizes), max(s[1] for s in sizes))


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


def begin_node(
    node_id: int,
    shape: str = NodeShape.BOX,
    label: str = "",
    radius: typing.Optional[float] = None,
) -> None:
    """Start a node. Everything drawn until :func:`end_node` is inside it.

    Parameters
    ----------
    node_id : int
        Unique among nodes. The editor's only handle on this node, so reusing
        one moves the old node's stored position onto the new node.
    shape : str
        A :class:`NodeShape`. ``BOX`` is sized by its contents and titles
        itself with :func:`begin_node_title_bar`; ``DISC`` is a fixed-radius
        mark that labels itself underneath.
    label : str
        The text under a disc. Ignored for a box, which has a title bar.
    radius : float, optional
        A disc's radius; the style's when omitted. Ignored for a box.

    Notes
    -----
    A disc reserves its own space with a ``dummy`` and expects **nothing**
    between begin and end -- there is no interior to draw into. Anything
    submitted anyway is measured into the node's rect, which is how a disc
    silently stops being round.
    """
    global _scope, _node
    ctx = _require("editor", "begin_node")
    _scope = "node"

    node = ctx._nodes.get(node_id)
    if node is None:
        node = _Node(node_id)
        ctx._nodes[node_id] = node
    node.alive = True
    node.pins = []
    node.title_rect = None
    node.shape = shape
    node.label = str(label)
    node.radius = float(ctx.style.node_disc_radius if radius is None else radius)
    _node = node

    if shape == NodeShape.DISC:
        # A disc's origin is its top-left, as a box's is, so a node keeps the
        # same stored position whichever shape it is drawn as. Anything else
        # would move every node the moment a view switched shape.
        im.set_cursor_screen_pos(ctx.canvas.to_screen(node.origin))
        im.push_id(str(node_id))
        im.begin_group()
        size = 2.0 * node.radius * ctx.canvas.zoom
        im.dummy(size, size)
        return

    im.set_cursor_screen_pos(_title_bar_origin(ctx, node))
    im.push_id(str(node_id))
    im.begin_group()


def _title_bar_origin(ctx: EditorContext, node: _Node) -> tuple:
    """Screen position where the node's first content goes.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node : _Node
        The node being laid out.

    Returns
    -------
    tuple
        ``(x, y)`` in screen space: the node origin plus one padding.
    """
    x, y = ctx.canvas.to_screen(node.origin)
    pad_x, pad_y = ctx.style.node_padding
    zoom = ctx.canvas.zoom
    return (x + pad_x * zoom, y + pad_y * zoom)


def end_node() -> None:
    """Finish the node, measure it, and draw its body behind its contents.

    Notes
    -----
    The body is drawn *after* the contents have been submitted, because its
    size is not known until then -- that is what ``begin_group``/``end_group``
    is measuring. Drawing it after would put it on top, so the drawlist's
    channel splitter is used to put these commands behind: the node body goes
    on the background channel and the contents on the foreground one, and the
    two are merged at the end of the frame.
    """
    global _scope, _node
    ctx = _require("node", "end_node")
    node = _node
    _scope, _node = "editor", None

    im.end_group()
    im.pop_id()

    zoom = ctx.canvas.zoom
    if node.shape == NodeShape.DISC:
        # Exactly the disc: no padding. A disc that reserved padding would
        # hit-test and stick as a square larger than the mark the user sees,
        # which reads as clicks landing on nothing.
        x, y = ctx.canvas.to_screen(node.origin)
        size = 2.0 * node.radius * zoom
        node.rect = (x, y, x + size, y + size)
    else:
        pad_x, pad_y = ctx.style.node_padding
        r_min, r_max = im.get_item_rect_min(), im.get_item_rect_max()
        node.rect = (
            r_min[0] - pad_x * zoom,
            r_min[1] - pad_y * zoom,
            r_max[0] + pad_x * zoom,
            r_max[1] + pad_y * zoom,
        )
    _draw_node_body(ctx, node)


def _node_colors(ctx: EditorContext, node: _Node) -> tuple:
    """Pick the body and title colours for a node's current state.

    Parameters
    ----------
    ctx : EditorContext
        The editor, for the palette and the selection.
    node : _Node
        The node being drawn.

    Returns
    -------
    tuple
        ``(background, title_bar)``, each ``(r, g, b, a)``.

    Notes
    -----
    Selected wins over hovered. The two are separate colours in the palette on
    purpose -- "this is under the pointer" and "this is chosen" must not look
    the same, or a selection cannot be read without moving the mouse away.
    """
    colors = ctx.style.colors
    if node.id in ctx.selected_nodes:
        return colors[Col.NODE_BACKGROUND_SELECTED], colors[Col.TITLE_BAR_SELECTED]
    if ctx._hovered_node == node.id and ctx._interaction != "box":
        return colors[Col.NODE_BACKGROUND_HOVERED], colors[Col.TITLE_BAR_HOVERED]
    return colors[Col.NODE_BACKGROUND], colors[Col.TITLE_BAR]


def _draw_node_body(ctx: EditorContext, node: _Node) -> None:
    """Paint one node's rectangle, title bar and outline behind its contents.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node : _Node
        The node whose rect has just been measured.

    Notes
    -----
    Switches to the node channel, paints, and switches back to the content
    channel. It does **not** split or merge: the split belongs to the editor,
    and splitting here would throw away every command the nodes before this one
    had already queued.
    """
    draw = ctx._draw
    style = ctx.style
    background, title_bar = _node_colors(ctx, node)
    x0, y0, x1, y1 = node.rect
    rounding = style.node_corner_rounding * ctx.canvas.zoom

    draw.channels_set_current(_CHANNEL_NODE)
    if node.shape == NodeShape.DISC:
        _draw_disc(ctx, draw, node, title_bar)
        draw.channels_set_current(_CHANNEL_CONTENT)
        return
    draw.add_rect_filled((x0, y0), (x1, y1), background, rounding)
    if node.title_rect is not None:
        # The title bar spans the node's full width and ends where the title
        # content ended, plus the padding the node rect was expanded by.
        bottom = node.title_rect[3] + style.node_padding[1] * ctx.canvas.zoom
        draw.add_rect_filled((x0, y0), (x1, bottom), title_bar, rounding)
    if style.flags & StyleFlags.NODE_OUTLINE:
        draw.add_rect((x0, y0), (x1, y1), style.colors[Col.NODE_OUTLINE], rounding,
                      0, style.node_border_thickness)

    # The pins are *not* drawn here. A pin sits on the node's edge, and the
    # edge is not known until the node's contents have been measured -- which
    # is this function -- but the pin's y comes from its attribute's rect, and
    # both are only reconciled in _resolve_pin_positions() once every node has
    # closed. Drawing them here paints last frame's positions, which on the
    # first frame is (0, 0): the pins are simply absent, and nothing says so.
    draw.channels_set_current(_CHANNEL_CONTENT)


def _shade(colour: tuple, factor: float) -> tuple:
    """Lighten or darken a colour, keeping its alpha.

    Parameters
    ----------
    colour : tuple
        ``(r, g, b, a)``.
    factor : float
        Above 1 lightens, below 1 darkens.

    Returns
    -------
    tuple
        The shaded colour, clamped to the byte range.
    """
    r, g, b = (min(255, max(0, int(round(c * factor)))) for c in colour[:3])
    return (r, g, b, colour[3] if len(colour) > 3 else 255)


def _draw_disc(ctx: EditorContext, draw, node: _Node, colour: tuple) -> None:
    """Paint a disc node: a shaded circle, a rim, and its label underneath.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    draw : object
        The drawlist, already on the node channel.
    node : _Node
        The node, with its rect measured.
    colour : tuple
        Its base colour -- the same slot a box's title bar takes, so the two
        shapes are coloured by one palette rather than two.

    Notes
    -----
    The shading is a stack of circles rather than a radial gradient, because
    the painter's only gradient runs left to right across a rectangle. How
    *many* is the whole quality question: three read as three hard rings, not
    as a sphere, which is what "the marbles look low colour resolution" is.
    See :func:`_draw_shaded_disc`.
    """
    style = ctx.style
    zoom = ctx.canvas.zoom
    x0, y0, x1, y1 = node.rect
    radius = (x1 - x0) * 0.5
    centre = (x0 + radius, y0 + radius)

    _draw_shaded_disc(draw, centre, radius, colour, style.node_shade_steps)

    rim = style.colors[Col.NODE_OUTLINE]
    width = style.node_border_thickness
    if node.id in ctx.selected_nodes:
        rim, width = style.colors[Col.TITLE_BAR_SELECTED], 3.0
    elif ctx._hovered_node == node.id:
        rim, width = style.colors[Col.TITLE_BAR_HOVERED], 2.0
    draw.add_circle(centre, radius, rim, 0, width * zoom)

    if node.label:
        _draw_node_label(ctx, draw, node, centre, radius)


def _draw_shaded_disc(draw, centre: tuple, radius: float,
                      colour: tuple, steps: int) -> None:
    """Paint a lit sphere as a stack of circles, dark rim to light highlight.

    Parameters
    ----------
    draw : object
        The drawlist.
    centre : tuple
        The disc's centre in screen space.
    radius : float
        Its radius in screen space.
    colour : tuple
        The base colour; the ramp runs either side of it.
    steps : int
        How many circles. Below about eight the steps are visible as rings.

    Notes
    -----
    Two things vary together, and doing only the first is what makes a disc
    look like a target rather than a sphere: each circle is **smaller** than
    the last *and* its centre walks toward the light. A concentric stack shades
    but does not model a highlight, so it reads as banding.

    The step count is a style var because the right number depends on the
    radius -- a 10-pixel mark needs far fewer than a 40-pixel one -- but the
    default is chosen for the large end, since over-drawing a small disc costs
    a few circles and under-drawing a large one is visible.

    The radius shrinks by a *fixed fraction per step* rather than linearly, so
    the outer band -- which is most of the visible area -- gets most of the
    steps. Linear spacing spends them in the middle where nothing changes.
    """
    steps = max(int(steps), 2)
    # Where the light comes from: up and to the left, the convention every
    # other shaded mark in the application uses.
    toward = (-radius * 0.42, -radius * 0.42)
    dark, light = _shade(colour, 0.55), _shade(colour, 1.45)

    for index in range(steps):
        fraction = index / float(steps - 1)
        # Eased so the bands bunch toward the rim, where the eye is.
        eased = fraction * fraction
        r = radius * (1.0 - 0.70 * eased)
        if r <= 0.5:
            break
        draw.add_circle_filled(
            (centre[0] + toward[0] * eased, centre[1] + toward[1] * eased),
            r,
            _lerp_colour(dark, light, fraction),
        )


def _lerp_colour(start: tuple, end: tuple, fraction: float) -> tuple:
    """Blend two colours.

    Parameters
    ----------
    start, end : tuple
        ``(r, g, b, a)``.
    fraction : float
        ``0`` gives `start`, ``1`` gives `end`.

    Returns
    -------
    tuple
        The blend, with `start`'s alpha -- the ramp shades a solid mark, and
        letting alpha ride along would make its middle translucent.
    """
    f = min(1.0, max(0.0, fraction))
    return (
        int(round(start[0] + (end[0] - start[0]) * f)),
        int(round(start[1] + (end[1] - start[1]) * f)),
        int(round(start[2] + (end[2] - start[2]) * f)),
        start[3] if len(start) > 3 else 255,
    )


def _draw_node_label(ctx: EditorContext, draw, node: _Node,
                     centre: tuple, radius: float) -> None:
    """Draw a disc's label on a plate below it.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    draw : object
        The drawlist.
    node : _Node
        The node being labelled.
    centre : tuple
        The disc's centre in screen space.
    radius : float
        Its radius in screen space.

    Notes
    -----
    Below rather than inside: a parameter name is routinely longer than a
    thirteen-pixel disc is wide, and text scaled to fit inside one is
    unreadable at any zoom. Elided past a limit so one long name cannot
    blanket its neighbours, and backed by a plate so that where two do
    overlap the top one stays readable instead of both becoming a smear.
    """
    style = ctx.style
    zoom = ctx.canvas.zoom
    text = _elide(draw, node.label, style.node_label_max_width * zoom)
    width = draw.calc_text_size(text)[0]
    height = draw.calc_text_size("X")[1]
    pad_x, pad_y = style.node_label_padding

    x = centre[0] - width * 0.5
    y = centre[1] + radius + style.node_label_gap * zoom
    draw.add_rect_filled(
        (x - pad_x, y - pad_y), (x + width + pad_x, y + height + pad_y),
        style.colors[Col.NODE_LABEL_PLATE], 2.0,
    )
    draw.add_text((x, y), style.colors[Col.NODE_LABEL], text)


def _elide(draw, text: str, limit: float) -> str:
    """Shorten `text` with an ellipsis until it fits `limit`.

    Parameters
    ----------
    draw : object
        The drawlist, for measuring.
    text : str
        The label.
    limit : float
        Maximum width in pixels.

    Returns
    -------
    str
        The text, or a prefix of it followed by an ellipsis. The character is
        the baked atlas's own -- a glyph the atlas lacks draws as nothing in
        the application while looking perfect in a screenshot.
    """
    if limit <= 0.0 or draw.calc_text_size(text)[0] <= limit:
        return text
    for cut in range(len(text) - 1, 0, -1):
        candidate = text[:cut] + "\u2026"
        if draw.calc_text_size(candidate)[0] <= limit:
            return candidate
    return "\u2026"


def begin_node_title_bar() -> None:
    """Start the node's title bar. Ends at :func:`end_node_title_bar`."""
    _require("node", "begin_node_title_bar")
    im.begin_group()


def end_node_title_bar() -> None:
    """Finish the title bar and move the cursor clear of it.

    Notes
    -----
    The move is the whole job, and leaving it out is a defect you can see: the
    title *bar* is the title text expanded by the node padding on all four
    sides, so its bottom edge sits one padding below the text. The layout
    cursor, left to itself, puts the next row one **item spacing** below the
    text instead -- and item spacing is smaller than the padding, so the first
    row of the body is drawn underneath the bar. The node still looks like a
    node; the first control in it is just half-buried.

    So the cursor is set explicitly to the content origin, which is the node's
    origin plus the title bar's full height plus one more padding. That is
    ``GetNodeContentOrigin`` in the reference, and it is called from exactly
    here for exactly this reason.
    """
    ctx = _require("node", "end_node_title_bar")
    im.end_group()
    node = _node
    r_min, r_max = im.get_item_rect_min(), im.get_item_rect_max()
    node.title_rect = (r_min[0], r_min[1], r_max[0], r_max[1])

    pad_x, pad_y = ctx.style.node_padding
    zoom = ctx.canvas.zoom
    origin_x, origin_y = ctx.canvas.to_screen(node.origin)
    title_height = (r_max[1] - r_min[1]) + 2.0 * pad_y * zoom
    im.set_cursor_screen_pos(
        (origin_x + pad_x * zoom, origin_y + title_height + pad_y * zoom)
    )


# --------------------------------------------------------------------------
# Attributes (pins)
# --------------------------------------------------------------------------


def _begin_pin(pin_id: int, kind: str, shape: str) -> None:
    """Start an attribute of `kind`, shared by the three public spellings.

    Parameters
    ----------
    pin_id : int
        Unique among pins.
    kind : str
        ``"input"``, ``"output"`` or ``"static"``.
    shape : str
        A :class:`PinShape` value. Ignored for a static attribute, which draws
        no pin at all.
    """
    global _scope, _pin
    ctx = _require("node", "_begin_pin")
    _scope = "attribute"

    im.begin_group()
    im.push_id(str(pin_id))

    pin = ctx._pins.get(pin_id)
    if pin is None:
        pin = _Pin(pin_id)
        ctx._pins[pin_id] = pin
    pin.node_id = _node.id
    pin.kind = kind
    pin.shape = shape
    _pin = pin


def _end_pin() -> None:
    """Finish an attribute and record where it landed."""
    global _scope, _pin
    ctx = _require("attribute", "_end_pin")
    _scope = "node"
    pin = _pin
    _pin = None

    im.pop_id()
    im.end_group()
    if im.is_item_active():
        ctx._active_attribute = pin.id

    r_min, r_max = im.get_item_rect_min(), im.get_item_rect_max()
    pin.rect = (r_min[0], r_min[1], r_max[0], r_max[1])
    if pin.kind != "static":
        _node.pins.append(pin.id)


def begin_input_attribute(pin_id: int, shape: str = PinShape.CIRCLE_FILLED) -> None:
    """Start an input attribute: a pin on the node's left edge.

    Parameters
    ----------
    pin_id : int
        Unique among pins.
    shape : str
        A :class:`PinShape` value.
    """
    _begin_pin(pin_id, "input", shape)


def end_input_attribute() -> None:
    """Finish an input attribute."""
    _end_pin()


def begin_output_attribute(pin_id: int, shape: str = PinShape.CIRCLE_FILLED) -> None:
    """Start an output attribute: a pin on the node's right edge.

    Parameters
    ----------
    pin_id : int
        Unique among pins.
    shape : str
        A :class:`PinShape` value.
    """
    _begin_pin(pin_id, "output", shape)


def end_output_attribute() -> None:
    """Finish an output attribute."""
    _end_pin()


def begin_static_attribute(pin_id: int) -> None:
    """Start an attribute with no pin -- a control that takes part in nothing.

    Parameters
    ----------
    pin_id : int
        Unique among pins. It still needs one: ``is_any_attribute_active``
        reports it, which is how a host tells "the user is typing in a node"
        from "the user is dragging the node".
    """
    _begin_pin(pin_id, "static", PinShape.CIRCLE_FILLED)


def end_static_attribute() -> None:
    """Finish a static attribute."""
    _end_pin()


def _resolve_pin_positions(ctx: EditorContext) -> None:
    """Place every submitted pin on its node's edge.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.

    Notes
    -----
    A pin's x is the node's edge -- not the attribute's -- so a row of pins
    lines up however wide its label is; its y is the attribute's vertical
    centre. That is imnodes' rule, and it is why a pin cannot be positioned
    until the whole node has been measured.
    """
    offset = ctx.style.pin_offset * ctx.canvas.zoom
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        x0, y0, x1, y1 = node.rect
        if node.shape == NodeShape.DISC:
            # On the circle's own left and right, at its middle. Using the
            # attribute's vertical centre -- correct for a box, where each
            # attribute is its own row -- would put every one of a disc's pins
            # at the same place *and* off the mark, because a disc has no rows.
            middle = 0.5 * (y0 + y1)
            for pin_id in node.pins:
                pin = ctx._pins[pin_id]
                x = (x0 - offset) if pin.kind == "input" else (x1 + offset)
                pin.pos = (x, middle)
            continue
        for pin_id in node.pins:
            pin = ctx._pins[pin_id]
            x = (x0 - offset) if pin.kind == "input" else (x1 + offset)
            pin.pos = (x, 0.5 * (pin.rect[1] + pin.rect[3]))


def _draw_pins(ctx: EditorContext, draw) -> None:
    """Paint every submitted pin, once their positions are known.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.
    draw : object
        The drawlist, already switched to the node channel.
    """
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        for pin_id in node.pins:
            _draw_pin(ctx, draw, ctx._pins[pin_id])


def _draw_pin(ctx: EditorContext, draw, pin: _Pin) -> None:
    """Paint one pin in its shape.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    draw : object
        The drawlist.
    pin : _Pin
        The pin, already positioned.
    """
    if pin.shape == PinShape.NONE:
        return
    style = ctx.style
    zoom = ctx.canvas.zoom
    colour = style.colors[Col.PIN_HOVERED if ctx._hovered_pin == pin.id else Col.PIN]
    x, y = pin.pos

    if pin.shape in (PinShape.CIRCLE, PinShape.CIRCLE_FILLED):
        radius = style.pin_circle_radius * zoom
        if pin.shape == PinShape.CIRCLE_FILLED:
            draw.add_circle_filled((x, y), radius, colour)
        else:
            draw.add_circle((x, y), radius, colour, 0, style.pin_line_thickness)
    elif pin.shape in (PinShape.QUAD, PinShape.QUAD_FILLED):
        half = style.pin_quad_side_length * 0.5 * zoom
        if pin.shape == PinShape.QUAD_FILLED:
            draw.add_rect_filled((x - half, y - half), (x + half, y + half), colour)
        else:
            draw.add_rect((x - half, y - half), (x + half, y + half), colour, 0.0,
                          0, style.pin_line_thickness)
    else:
        side = style.pin_triangle_side_length * zoom
        # An equilateral triangle pointing right, centred on the pin, with the
        # same area whichever way the link leaves it.
        height = side * math.sqrt(3.0) * 0.5
        p0 = (x - height * 0.5, y - side * 0.5)
        p1 = (x - height * 0.5, y + side * 0.5)
        p2 = (x + height * 0.5, y)
        if pin.shape == PinShape.TRIANGLE_FILLED:
            draw.add_triangle_filled(p0, p1, p2, colour)
        else:
            draw.add_triangle(p0, p1, p2, colour, style.pin_line_thickness)


# --------------------------------------------------------------------------
# Links
# --------------------------------------------------------------------------


def link(
    link_id: int,
    start_pin: int,
    end_pin: int,
    colour: typing.Optional[tuple] = None,
    thickness: typing.Optional[float] = None,
    arrow: bool = False,
) -> None:
    """Submit a link between two pins.

    Parameters
    ----------
    link_id : int
        Unique among links, and the id reported by
        :func:`is_link_destroyed` and :func:`is_link_selected`.
    start_pin : int
        The pin the link leaves.
    end_pin : int
        The pin it arrives at.
    colour : tuple, optional
        ``(r, g, b, a)`` for this link alone; the palette's when omitted.
    thickness : float, optional
        Width in pixels *before* the zoom is applied; the style's when omitted.
    arrow : bool
        Draw a head at the arriving end. Off by default, because in a dataflow
        graph every edge runs the same way and a head on all of them is noise;
        on where the direction is the *information*, as it is for "this
        parameter follows that one".

    Notes
    -----
    Links are pure per-frame: submit them every frame from your own model.
    There is no pool, because a link has no state a user can change -- unlike a
    node, which has a position.

    The reference has no per-link colour, and for a dataflow graph it does not
    need one: every edge means the same thing. A graph whose edges mean
    *different* things -- this parameter is owned by that fit, this one follows
    that one -- cannot say so with one colour, and drawing them alike is not a
    cosmetic loss but a claim the picture makes and the model does not. A
    hovered or selected link still takes the palette's colour, so the feedback
    that says "this is the one you are pointing at" is not overridden by a
    caller's styling.
    """
    ctx = _require("editor", "link")
    entry = _Link(link_id, start_pin, end_pin)
    entry.colour = colour
    entry.thickness = thickness
    entry.arrow = bool(arrow)
    ctx._links.append(entry)


def _cubic_bezier(start: tuple, end: tuple, start_kind: str,
                  segments_per_length: float) -> tuple:
    """Compute a link's four control points and how finely to flatten it.

    Parameters
    ----------
    start : tuple
        Screen-space position of the pin the link leaves.
    end : tuple
        Screen-space position of the pin it arrives at.
    start_kind : str
        ``"input"`` or ``"output"``. An input start is swapped with the end, so
        a curve always leaves rightwards and arrives leftwards regardless of
        which end the user dragged from -- otherwise the same link draws as two
        different shapes depending on the direction it was made in.
    segments_per_length : float
        Flattening density, segments per pixel of chord.
    Returns
    -------
    tuple
        ``(p0, p1, p2, p3, segments)``.
    """
    if start_kind == "input":
        start, end = end, start
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    offset = 0.25 * length
    return (
        start,
        (start[0] + offset, start[1]),
        (end[0] - offset, end[1]),
        end,
        max(int(length * segments_per_length), 1),
    )


def _node_anchor(ctx: EditorContext, pin: _Pin) -> typing.Optional[tuple]:
    """The centre and rim radius of the node a pin belongs to.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    pin : _Pin
        The pin whose node is wanted.

    Returns
    -------
    tuple or None
        ``(centre, radius)`` in screen space, or ``None`` when the node was not
        submitted this frame and therefore has no measured rect.

    Notes
    -----
    A disc's radius is exactly its own; a box has no single radius, so it uses
    half its *shorter* side. That keeps the anchor inside the box on every
    approach -- half the diagonal would leave the edge starting in mid-air
    beside a wide node.
    """
    node = ctx._nodes.get(pin.node_id)
    if node is None or not node.alive:
        return None
    x0, y0, x1, y1 = node.rect
    centre = (0.5 * (x0 + x1), 0.5 * (y0 + y1))
    if node.shape == NodeShape.DISC:
        return (centre, 0.5 * (x1 - x0))
    return (centre, 0.5 * min(x1 - x0, y1 - y0))


def _arc_curve(ctx: EditorContext, start: _Pin, end: _Pin,
               two_way: bool) -> typing.Optional[tuple]:
    """A rim-to-rim curve between two nodes, with a slight bow.

    Parameters
    ----------
    ctx : EditorContext
        The editor, for the style and the zoom.
    start, end : _Pin
        The pins the link was submitted between. Only their *nodes* are used --
        an arc joins marks, not ports.
    two_way : bool
        Whether the reverse link is also drawn, in which case both are pushed
        aside so they do not land on each other.

    Returns
    -------
    tuple or None
        ``(p0, p1, p2, p3, segments)``, or ``None`` when either node is absent
        or the two coincide.

    Notes
    -----
    The control points sit **60% of the way** from each end toward the bowed
    mid-point rather than on the chord. That is what makes the curve leave and
    arrive along its own tangent, so an arrowhead aimed from the last control
    point points where the curve is actually going -- and it is why the head is
    aimed at ``p2`` rather than at the other node's centre.
    """
    start_anchor = _node_anchor(ctx, start)
    end_anchor = _node_anchor(ctx, end)
    if start_anchor is None or end_anchor is None:
        return None
    (cx0, cy0), r_from = start_anchor
    (cx1, cy1), r_to = end_anchor

    dx, dy = cx1 - cx0, cy1 - cy0
    distance = math.hypot(dx, dy)
    if distance < 1e-4:
        return None
    ux, uy = dx / distance, dy / distance
    px, py = -uy, ux

    zoom = ctx.canvas.zoom
    fraction, low, high = ctx.style.link_bow
    bow = min(high, max(low, distance / max(zoom, 1e-6) * fraction)) * zoom
    aside = ctx.style.link_two_way_offset * zoom if two_way else 0.0
    if two_way:
        # A mutual pair needs a wider bow as well as the sideways offset, or
        # the two arcs stay close enough to read as one thick edge.
        bow = max(bow, min(50.0 * zoom, distance * 0.26))

    p0 = (cx0 + ux * r_from + px * aside, cy0 + uy * r_from + py * aside)
    p3 = (cx1 - ux * r_to + px * aside, cy1 - uy * r_to + py * aside)
    mid = (0.5 * (p0[0] + p3[0]) + px * bow, 0.5 * (p0[1] + p3[1]) + py * bow)
    p1 = (p0[0] + (mid[0] - p0[0]) * 0.6, p0[1] + (mid[1] - p0[1]) * 0.6)
    p2 = (p3[0] + (mid[0] - p3[0]) * 0.6, p3[1] + (mid[1] - p3[1]) * 0.6)
    segments = max(int(distance * ctx.style.link_line_segments_per_length), 8)
    return (p0, p1, p2, p3, segments)


def _link_curve(ctx: EditorContext, start: _Pin, end: _Pin,
                two_way: bool = False) -> typing.Optional[tuple]:
    """The curve for one link, by whichever routing the style asks for.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    start, end : _Pin
        The link's two pins.
    two_way : bool
        Whether the reverse link is drawn too.

    Returns
    -------
    tuple or None
        ``(p0, p1, p2, p3, segments)``.

    Notes
    -----
    One function, used by the drawing, the hover test and the arrowhead alike.
    Three descriptions of where a link is would be three things to keep in
    step, and the one that drifts makes a link hoverable somewhere it is not
    drawn.
    """
    if ctx.style.link_routing == LinkRouting.ARC:
        curve = _arc_curve(ctx, start, end, two_way)
        if curve is not None:
            return curve
    return _cubic_bezier(start.pos, end.pos, start.kind,
                         ctx.style.link_line_segments_per_length)


def _mutual_pairs(ctx: EditorContext) -> set:
    """Node-id pairs that have a link in both directions this frame.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    set
        Frozensets of two node ids.
    """
    seen = set()
    for entry in ctx._links:
        start, end = ctx._pins.get(entry.start_pin), ctx._pins.get(entry.end_pin)
        if start is not None and end is not None:
            seen.add((start.node_id, end.node_id))
    return {frozenset(pair) for pair in seen if (pair[1], pair[0]) in seen}


def _draw_links(draw, ctx: EditorContext) -> None:
    """Paint every submitted link, and the one being dragged.

    Parameters
    ----------
    draw : object
        The drawlist.
    ctx : EditorContext
        The editor being finished.
    """
    style = ctx.style
    thickness = style.link_thickness * ctx.canvas.zoom
    mutual = _mutual_pairs(ctx) if style.link_routing == LinkRouting.ARC else set()
    for entry in ctx._links:
        start = ctx._pins.get(entry.start_pin)
        end = ctx._pins.get(entry.end_pin)
        if start is None or end is None:
            # A link naming a pin nobody submitted this frame. Drawn nowhere
            # rather than drawn at the origin, which is what a (0, 0) fallback
            # would do -- a curve to the top-left corner reads as a bug in the
            # graph rather than as a node that is not on screen.
            continue
        # Selection and hover win over the caller's colour: they are feedback
        # about *this* pointer, and a caller that styled its edges must not be
        # able to make "you are pointing at this one" invisible.
        if entry.id in ctx.selected_links:
            colour = style.colors[Col.LINK_SELECTED]
        elif ctx._hovered_link == entry.id:
            colour = style.colors[Col.LINK_HOVERED]
        else:
            colour = entry.colour if entry.colour is not None else style.colors[Col.LINK]
        width = thickness if entry.thickness is None else entry.thickness * ctx.canvas.zoom
        curve = _link_curve(ctx, start, end,
                            frozenset((start.node_id, end.node_id)) in mutual)
        if curve is None:
            continue
        p0, p1, p2, p3, segments = curve
        draw.add_bezier_cubic(p0, p1, p2, p3, colour, width, segments)
        if entry.arrow:
            _draw_arrow_head(ctx, draw, p2, p3, colour, width)

    if ctx._interaction == "link" and ctx._link_from_pin is not None:
        start = ctx._pins.get(ctx._link_from_pin)
        if start is not None:
            end_pos = im.get_io().mouse_pos
            hovered = ctx._hovered_pin
            if hovered is not None and hovered != ctx._link_from_pin:
                end_pos = ctx._pins[hovered].pos
            # Always pin-routed: the loose end is the pointer, which has no
            # node to run rim to rim with.
            p0, p1, p2, p3, segments = _cubic_bezier(
                start.pos, end_pos, start.kind,
                style.link_line_segments_per_length,
            )
            draw.add_bezier_cubic(p0, p1, p2, p3, style.colors[Col.LINK_HOVERED],
                                  thickness, segments)


def _draw_arrow_head(ctx: EditorContext, draw, before: tuple, tip: tuple,
                     colour: tuple, width: float = 1.0) -> None:
    """Draw a filled head at a link's arriving end.

    Parameters
    ----------
    ctx : EditorContext
        The editor, for the zoom.
    before : tuple
        The curve's last control point. The head is aimed *from* it, so it
        follows the curve's own tangent rather than the straight line between
        the two nodes -- on a bowed link those differ by enough to look wrong,
        which is the whole reason the control point is the thing passed.
    tip : tuple
        Where the curve arrives.
    colour : tuple
        The link's colour, so a head cannot differ from its own line.
    width : float
        The line's width; a thicker line gets a slightly larger head, or the
        head disappears into the stroke.

    Notes
    -----
    A 30-degree half-angle and a length of ``10 + width/2``, both taken from
    the diagram this replaces. A narrower head reads as a kink in the line and
    a wider one as a triangle that happens to touch it.
    """
    zoom = ctx.canvas.zoom
    angle = math.atan2(tip[1] - before[1], tip[0] - before[0])
    size = (10.0 + width * 0.5) * zoom
    spread = math.pi / 6.0
    draw.add_triangle_filled(
        tip,
        (tip[0] - size * math.cos(angle - spread),
         tip[1] - size * math.sin(angle - spread)),
        (tip[0] - size * math.cos(angle + spread),
         tip[1] - size * math.sin(angle + spread)),
        colour,
    )


def _bezier_distance(point: tuple, curve: tuple) -> float:
    """Approximate the distance from `point` to a flattened bezier.

    Parameters
    ----------
    point : tuple
        ``(x, y)`` in screen space.
    curve : tuple
        ``(p0, p1, p2, p3, segments)`` as :func:`_cubic_bezier` returns.

    Returns
    -------
    float
        The smallest distance to any of the flattened segments.

    Notes
    -----
    Flattened rather than solved: the exact nearest point on a cubic is a
    quintic root-find, and the curve is *drawn* flattened, so measuring the
    flattening is measuring what the user sees. Capped at 32 segments so a link
    dragged across a large canvas does not make hover-testing quadratic.
    """
    p0, p1, p2, p3, segments = curve
    steps = max(2, min(int(segments), 32))
    best = float("inf")
    previous = p0
    for index in range(1, steps + 1):
        t = index / steps
        u = 1.0 - t
        current = (
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        )
        best = min(best, _segment_distance(point, previous, current))
        previous = current
    return best


def _segment_distance(point: tuple, a: tuple, b: tuple) -> float:
    """Distance from `point` to the segment `a`-`b`.

    Parameters
    ----------
    point : tuple
        ``(x, y)``.
    a, b : tuple
        The segment's ends.

    Returns
    -------
    float
        The perpendicular distance, or the distance to the nearer end when the
        foot of the perpendicular falls outside the segment.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(point[0] - ax, point[1] - ay)
    t = max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / length_sq))
    return math.hypot(point[0] - (ax + t * dx), point[1] - (ay + t * dy))


# --------------------------------------------------------------------------
# Hover and interaction
# --------------------------------------------------------------------------


def _update_hover(ctx: EditorContext) -> None:
    """Decide what the pointer is over, in priority order.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.

    Notes
    -----
    The order is pin, then node, then link, and it matters: a pin sits on the
    node's edge and therefore overlaps it, and a link ends at a pin. Testing
    nodes first makes the pins unclickable, which is the whole interaction.
    """
    if not ctx._editor_hovered:
        return
    mouse = im.get_io().mouse_pos
    style = ctx.style

    radius = style.pin_hover_radius * ctx.canvas.zoom
    best, best_distance = None, radius
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        for pin_id in node.pins:
            pin = ctx._pins[pin_id]
            distance = math.hypot(mouse[0] - pin.pos[0], mouse[1] - pin.pos[1])
            if distance <= best_distance:
                best, best_distance = pin_id, distance
    ctx._hovered_pin = best
    if best is not None:
        return

    # Later nodes are drawn on top, so the last one containing the pointer is
    # the one hovered -- walking forward and keeping the last match is the same
    # answer as walking backward and stopping at the first.
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        x0, y0, x1, y1 = node.rect
        if x0 <= mouse[0] <= x1 and y0 <= mouse[1] <= y1:
            ctx._hovered_node = node.id
    if ctx._hovered_node is not None:
        return

    threshold = style.link_hover_distance * ctx.canvas.zoom
    for entry in ctx._links:
        start = ctx._pins.get(entry.start_pin)
        end = ctx._pins.get(entry.end_pin)
        if start is None or end is None:
            continue
        curve = _link_curve(ctx, start, end)
        if curve is not None and _bezier_distance(mouse, curve) <= threshold:
            ctx._hovered_link = entry.id


def _update_interaction(ctx: EditorContext, draw) -> None:
    """Run the one state machine: drag, link, box-select, pan.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.
    draw : object
        The drawlist, for the box selector's rectangle.

    Notes
    -----
    One machine with one ``_interaction`` field rather than four independent
    flags. Four flags allow states that make no sense -- panning while box
    selecting while dragging a node -- and the bug that produces is a node that
    teleports, which is very hard to read back to its cause.
    """
    io = im.get_io()
    mouse = io.mouse_pos
    left_clicked = io.mouse_clicked[0]
    left_down = io.mouse_down[0]
    middle_down = io.mouse_down[2] if len(io.mouse_down) > 2 else False

    if ctx._interaction is None and ctx._editor_hovered:
        if left_clicked:
            _begin_click(ctx, mouse)
        elif middle_down:
            ctx._interaction = "pan"

    if ctx._interaction == "node":
        _drag_nodes(ctx, mouse)
        if not left_down:
            ctx._interaction, ctx._drag_node = None, None
    elif ctx._interaction == "link":
        if not left_down:
            _finish_link(ctx)
    elif ctx._interaction == "box":
        _draw_box_selector(ctx, draw, mouse)
        if not left_down:
            _apply_box_selection(ctx, mouse)
            ctx._interaction = None
    elif ctx._interaction == "pan":
        if middle_down:
            ctx.canvas.panning = (ctx.canvas.panning[0] + io.mouse_delta[0],
                                  ctx.canvas.panning[1] + io.mouse_delta[1])
        else:
            ctx._interaction = None

    if ctx._editor_hovered and io.mouse_wheel:
        ctx.canvas.zoom_at(mouse, 1.0 + 0.1 * io.mouse_wheel)


def _begin_click(ctx: EditorContext, mouse: tuple) -> None:
    """Decide what a press on the editor starts.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    mouse : tuple
        Where the press landed, in screen space.
    """
    io = im.get_io()
    additive = bool(getattr(io, "key_ctrl", False) or getattr(io, "key_shift", False))

    if ctx._hovered_pin is not None:
        pin = ctx._pins[ctx._hovered_pin]
        existing = _link_ending_at(ctx, pin.id)
        if existing is not None and pin.kind == "input":
            # Dragging off an input that already has a link detaches it, which
            # is how a wire is rerouted without deleting it first.
            ctx._link_detached = existing.id
            ctx._link_from_pin = existing.start_pin
        else:
            ctx._link_detached = None
            ctx._link_from_pin = pin.id
        ctx._interaction = "link"
        ctx._link_started = ctx._link_from_pin
        return

    if ctx._hovered_node is not None:
        node = ctx._nodes[ctx._hovered_node]
        if not additive and node.id not in ctx.selected_nodes:
            ctx.selected_nodes = {node.id}
            ctx.selected_links = set()
        elif additive:
            ctx.selected_nodes.symmetric_difference_update({node.id})
        if node.draggable:
            ctx._interaction = "node"
            ctx._drag_node = node.id
            ctx._drag_offsets = {
                nid: ctx._nodes[nid].origin
                for nid in ctx.selected_nodes
                if nid in ctx._nodes and ctx._nodes[nid].draggable
            }
            ctx._drag_offsets.setdefault(node.id, node.origin)
            ctx._box_anchor = mouse
        return

    if ctx._hovered_link is not None:
        if additive:
            ctx.selected_links.symmetric_difference_update({ctx._hovered_link})
        else:
            ctx.selected_links = {ctx._hovered_link}
            ctx.selected_nodes = set()
        return

    if not additive:
        ctx.selected_nodes = set()
        ctx.selected_links = set()
    ctx._interaction = "box"
    ctx._box_anchor = mouse


def _link_ending_at(ctx: EditorContext, pin_id: int) -> typing.Optional[_Link]:
    """Find the link arriving at `pin_id`, if any.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    pin_id : int
        The pin to look for.

    Returns
    -------
    _Link or None
        The first link whose end is that pin.
    """
    for entry in ctx._links:
        if entry.end_pin == pin_id:
            return entry
    return None


def _drag_nodes(ctx: EditorContext, mouse: tuple) -> None:
    """Move every dragged node by the pointer's travel since the press.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    mouse : tuple
        The pointer, in screen space.

    Notes
    -----
    Computed from the press position and the *original* origins, not
    accumulated frame to frame. Accumulating drifts: each frame rounds the
    delta into grid space, and the error compounds over a long drag until the
    node no longer sits under the pointer.
    """
    zoom = ctx.canvas.zoom or 1.0
    dx = (mouse[0] - ctx._box_anchor[0]) / zoom
    dy = (mouse[1] - ctx._box_anchor[1]) / zoom

    # The snap is computed for the node actually under the pointer and then
    # applied to the whole selection as one extra offset. Snapping each node
    # of a multi-node drag on its own would tear the group apart: two nodes
    # that were level would stick to different neighbours and end up at
    # different offsets, and the user's arrangement is destroyed by the
    # feature meant to preserve it.
    primary = ctx._drag_node if ctx._drag_node in ctx._drag_offsets else None
    ctx._stuck_to = set()
    if primary is not None:
        origin = ctx._drag_offsets[primary]
        want = (origin[0] + dx, origin[1] + dy)
        got = _snapped_position(ctx, primary, want)
        dx += got[0] - want[0]
        dy += got[1] - want[1]

    for node_id, origin in ctx._drag_offsets.items():
        node = ctx._nodes.get(node_id)
        if node is None:
            continue
        node.origin = (origin[0] + dx, origin[1] + dy)


def _snapped_position(ctx: EditorContext, node_id: int, want: tuple) -> tuple:
    """Adjust a dragged node's position for grid snapping and sticking.

    Parameters
    ----------
    ctx : EditorContext
        The editor. Its :attr:`~EditorContext.snap_to_grid` and
        :attr:`~EditorContext.stick_to_nodes` decide what applies, and
        :attr:`EditorContext._stuck_to` is filled with the ids stuck against.
    node_id : int
        The node under the pointer.
    want : tuple
        Where the raw drag would put it, in grid space.

    Returns
    -------
    tuple
        Where it should actually go, in grid space.

    Notes
    -----
    Sticking wins over the grid where both would apply: the grid is a
    background convenience and sticking is something the user aimed at, so a
    node dropped against its neighbour must end up *flush* rather than on the
    nearest grid line a few pixels away.
    """
    node = ctx._nodes.get(node_id)
    if node is None:
        return want

    if ctx.stick_to_nodes:
        stuck = _stick_to_neighbours(ctx, node, want)
        if stuck is not None:
            return stuck

    if ctx.snap_to_grid or (ctx.style.flags & StyleFlags.GRID_SNAPPING):
        spacing = ctx.style.grid_spacing
        return (round(want[0] / spacing) * spacing,
                round(want[1] / spacing) * spacing)
    return want


def _stick_to_neighbours(
    ctx: EditorContext, node: _Node, want: tuple
) -> typing.Optional[tuple]:
    """Stick a node's edges flush against the other nodes it is dragged near.

    Parameters
    ----------
    ctx : EditorContext
        The editor. :attr:`EditorContext._stuck_to` is filled with the ids of
        the nodes stuck against, for the hint drawn while dragging.
    node : _Node
        The node under the pointer.
    want : tuple
        Where the raw drag would put it, in grid space.

    Returns
    -------
    tuple or None
        The stuck position, or ``None`` when nothing was near enough.

    Notes
    -----
    This is a window manager's rule, not a graph's: an edge sticks to the
    facing edge of a neighbour it *overlaps along the other axis*, which is
    what stops a node in a distant row snapping to a column it is nowhere near.
    The overlap test is the whole reason it feels right rather than jumpy.

    A stick also levels the perpendicular edges when they are nearly aligned,
    because two nodes joined with a two-pixel step read as a mistake rather
    than as a pair.

    Distances are compared in **screen** pixels and the result is converted
    back to grid space: a fixed grid-space tolerance means the stick reaches
    further and further across the screen the more you zoom out, until at low
    zoom everything sticks to everything.
    """
    zoom = ctx.canvas.zoom or 1.0
    tolerance = ctx.style.stick_distance / zoom

    x0, y0, x1, y1 = node.rect
    width, height = (x1 - x0) / zoom, (y1 - y0) / zoom
    x, y = want
    stuck: set = set()

    for other in ctx._nodes.values():
        if other is node or not other.alive or other.id in ctx._drag_offsets:
            continue
        ox0, oy0, ox1, oy1 = other.rect
        ox, oy = other.origin
        ow, oh = (ox1 - ox0) / zoom, (oy1 - oy0) / zoom

        vertical_overlap = min(y + height, oy + oh) - max(y, oy)
        horizontal_overlap = min(x + width, ox + ow) - max(x, ox)
        hit = False

        if vertical_overlap > 0.0:
            if abs((x + width) - ox) <= tolerance:
                x, hit = ox - width, True
            elif abs((ox + ow) - x) <= tolerance:
                x, hit = ox + ow, True
        if horizontal_overlap > 0.0:
            if abs((y + height) - oy) <= tolerance:
                y, hit = oy - height, True
            elif abs((oy + oh) - y) <= tolerance:
                y, hit = oy + oh, True

        if hit:
            if abs(y - oy) <= tolerance:
                y = oy
            if abs(x - ox) <= tolerance:
                x = ox
            stuck.add(other.id)

    ctx._stuck_to = stuck
    return (x, y) if stuck else None


def _finish_link(ctx: EditorContext) -> None:
    """Resolve a link drag on release: created, detached-and-dropped, or dropped.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    """
    start = ctx._link_from_pin
    target = ctx._hovered_pin
    if target is not None and start is not None and target != start:
        start_pin, end_pin = ctx._pins[start], ctx._pins[target]
        # A link joins an output to an input. Two of the same kind is not a
        # link, and rejecting it here rather than in the host is what stops
        # every host having to write the same check.
        if start_pin.kind != end_pin.kind and "static" not in (start_pin.kind, end_pin.kind):
            if start_pin.kind == "output":
                ctx._link_created = (start, target)
            else:
                ctx._link_created = (target, start)
            if ctx._link_detached is not None:
                ctx._link_destroyed = ctx._link_detached
        else:
            ctx._link_dropped = start
    else:
        ctx._link_dropped = start
        if ctx._link_detached is not None:
            ctx._link_destroyed = ctx._link_detached

    ctx._interaction = None
    ctx._link_from_pin = None
    ctx._link_detached = None


def _draw_stick_hint(ctx: EditorContext, draw) -> None:
    """Outline the nodes a dragged node is currently stuck against.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.
    draw : object
        The drawlist, after the channels have merged, so the hint is on top.

    Notes
    -----
    This is the visible half of sticking, and without it the feature is a
    defect: the node lands a few pixels from where the pointer left it, and
    nothing on screen says that was deliberate. Drawn on the *neighbour*
    rather than on the dragged node, because what the user needs to know is
    which thing it caught on.
    """
    if not ctx._stuck_to or ctx._interaction != "node":
        return
    colour = ctx.style.colors[Col.STICK_HINT]
    for node_id in ctx._stuck_to:
        node = ctx._nodes.get(node_id)
        if node is None or not node.alive:
            continue
        x0, y0, x1, y1 = node.rect
        draw.add_rect((x0, y0), (x1, y1), colour, 0.0, 0, 2.0)


def _draw_box_selector(ctx: EditorContext, draw, mouse: tuple) -> None:
    """Paint the rubber-band rectangle.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    draw : object
        The drawlist.
    mouse : tuple
        The pointer, in screen space.
    """
    x0, y0 = ctx._box_anchor
    x1, y1 = mouse
    lo = (min(x0, x1), min(y0, y1))
    hi = (max(x0, x1), max(y0, y1))
    draw.add_rect_filled(lo, hi, ctx.style.colors[Col.BOX_SELECTOR])
    draw.add_rect(lo, hi, ctx.style.colors[Col.BOX_SELECTOR_OUTLINE])


def _apply_box_selection(ctx: EditorContext, mouse: tuple) -> None:
    """Select every node the rubber band touched.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    mouse : tuple
        Where the drag ended, in screen space.

    Notes
    -----
    *Touched*, not *contained*: a band has to enclose a node entirely to catch
    it under the contained rule, which makes selecting a row of wide nodes
    require a drag wider than the viewport.
    """
    x0, y0 = ctx._box_anchor
    x1, y1 = mouse
    lo = (min(x0, x1), min(y0, y1))
    hi = (max(x0, x1), max(y0, y1))
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        nx0, ny0, nx1, ny1 = node.rect
        if nx0 <= hi[0] and nx1 >= lo[0] and ny0 <= hi[1] and ny1 >= lo[1]:
            ctx.selected_nodes.add(node.id)


# --------------------------------------------------------------------------
# Queries -- what happened this frame
# --------------------------------------------------------------------------


def is_editor_hovered(ctx: EditorContext) -> bool:
    """Report whether the pointer is inside the editor.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    bool
        ``True`` when the pointer was over the editor this frame.
    """
    return ctx._editor_hovered


def is_node_hovered(ctx: EditorContext) -> typing.Optional[int]:
    """Report which node the pointer is over.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The node id, or ``None``.
    """
    return ctx._hovered_node


def is_pin_hovered(ctx: EditorContext) -> typing.Optional[int]:
    """Report which pin the pointer is over.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The pin id, or ``None``.
    """
    return ctx._hovered_pin


def is_link_hovered(ctx: EditorContext) -> typing.Optional[int]:
    """Report which link the pointer is over.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The link id, or ``None``.
    """
    return ctx._hovered_link


def is_link_started(ctx: EditorContext) -> typing.Optional[int]:
    """Report the pin a link drag started from, this frame.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The pin id, or ``None``.
    """
    return ctx._link_started


def is_link_created(ctx: EditorContext) -> typing.Optional[tuple]:
    """Report a link the user just made.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    tuple or None
        ``(output_pin_id, input_pin_id)``, always in that order however the
        user dragged it, or ``None``.
    """
    return ctx._link_created


def is_link_dropped(ctx: EditorContext) -> typing.Optional[int]:
    """Report a link drag that ended on nothing.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The pin the drag started from, or ``None``. Hosts use this to open a
        "create a node here" menu.
    """
    return ctx._link_dropped


def is_link_destroyed(ctx: EditorContext) -> typing.Optional[int]:
    """Report a link the user detached.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The link id, or ``None``.
    """
    return ctx._link_destroyed


def is_any_attribute_active(ctx: EditorContext) -> typing.Optional[int]:
    """Report the attribute the user is interacting with, if any.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    int or None
        The attribute id, or ``None``. A host that moves nodes with the arrow
        keys must check this, or typing in a text field inside a node moves the
        node.
    """
    return ctx._active_attribute


# --------------------------------------------------------------------------
# Selection and position
# --------------------------------------------------------------------------


def get_selected_nodes(ctx: EditorContext) -> list:
    """List the selected node ids.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    list
        Node ids, sorted, so the order does not vary between runs.
    """
    return sorted(ctx.selected_nodes)


def get_selected_links(ctx: EditorContext) -> list:
    """List the selected link ids.

    Parameters
    ----------
    ctx : EditorContext
        The editor.

    Returns
    -------
    list
        Link ids, sorted.
    """
    return sorted(ctx.selected_links)


def clear_node_selection(ctx: EditorContext, node_id: typing.Optional[int] = None) -> None:
    """Deselect one node, or all of them.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int, optional
        The node to deselect; every node when omitted.
    """
    if node_id is None:
        ctx.selected_nodes.clear()
    else:
        ctx.selected_nodes.discard(node_id)


def clear_link_selection(ctx: EditorContext, link_id: typing.Optional[int] = None) -> None:
    """Deselect one link, or all of them.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    link_id : int, optional
        The link to deselect; every link when omitted.
    """
    if link_id is None:
        ctx.selected_links.clear()
    else:
        ctx.selected_links.discard(link_id)


def select_node(ctx: EditorContext, node_id: int) -> None:
    """Add a node to the selection.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node to select.
    """
    ctx.selected_nodes.add(node_id)


def select_link(ctx: EditorContext, link_id: int) -> None:
    """Add a link to the selection.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    link_id : int
        The link to select.
    """
    ctx.selected_links.add(link_id)


def is_node_selected(ctx: EditorContext, node_id: int) -> bool:
    """Report whether a node is selected.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node to test.

    Returns
    -------
    bool
        ``True`` when selected.
    """
    return node_id in ctx.selected_nodes


def is_link_selected(ctx: EditorContext, link_id: int) -> bool:
    """Report whether a link is selected.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    link_id : int
        The link to test.

    Returns
    -------
    bool
        ``True`` when selected.
    """
    return link_id in ctx.selected_links


def set_node_grid_space_pos(ctx: EditorContext, node_id: int, pos: tuple) -> None:
    """Place a node in grid space.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node. Created in the pool if the editor has not seen it yet, so a
        host can lay a graph out before drawing it once.
    pos : tuple
        ``(x, y)`` in grid space.
    """
    node = ctx._nodes.get(node_id)
    if node is None:
        node = _Node(node_id)
        node.alive = False
        ctx._nodes[node_id] = node
    node.origin = (float(pos[0]), float(pos[1]))


def get_node_grid_space_pos(ctx: EditorContext, node_id: int) -> tuple:
    """Read a node's grid-space position.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.

    Returns
    -------
    tuple
        ``(x, y)`` in grid space, ``(0.0, 0.0)`` for an unknown node.
    """
    node = ctx._nodes.get(node_id)
    return node.origin if node is not None else (0.0, 0.0)


def set_node_screen_space_pos(ctx: EditorContext, node_id: int, pos: tuple) -> None:
    """Place a node by where it should appear on screen.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.
    pos : tuple
        ``(x, y)`` in screen space, converted through the current pan and zoom.
    """
    set_node_grid_space_pos(ctx, node_id, ctx.canvas.to_grid(pos))


def get_node_screen_space_pos(ctx: EditorContext, node_id: int) -> tuple:
    """Read where a node currently appears on screen.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.

    Returns
    -------
    tuple
        ``(x, y)`` in screen space.
    """
    return ctx.canvas.to_screen(get_node_grid_space_pos(ctx, node_id))


def get_node_dimensions(ctx: EditorContext, node_id: int) -> tuple:
    """Read a node's measured size.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.

    Returns
    -------
    tuple
        ``(width, height)`` in screen pixels, ``(0.0, 0.0)`` before the node
        has been drawn once -- its size comes from its contents, so it is not
        knowable earlier.
    """
    node = ctx._nodes.get(node_id)
    if node is None:
        return (0.0, 0.0)
    x0, y0, x1, y1 = node.rect
    return (x1 - x0, y1 - y0)


def set_node_draggable(ctx: EditorContext, node_id: int, draggable: bool) -> None:
    """Allow or forbid dragging a node.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.
    draggable : bool
        ``False`` pins it in place; it stays selectable and hoverable.
    """
    node = ctx._nodes.get(node_id)
    if node is None:
        node = _Node(node_id)
        node.alive = False
        ctx._nodes[node_id] = node
    node.draggable = bool(draggable)


def snap_node_to_grid(ctx: EditorContext, node_id: int) -> None:
    """Move a node to the nearest grid intersection.

    Parameters
    ----------
    ctx : EditorContext
        The editor.
    node_id : int
        The node.
    """
    node = ctx._nodes.get(node_id)
    if node is None:
        return
    spacing = ctx.style.grid_spacing
    node.origin = (round(node.origin[0] / spacing) * spacing,
                   round(node.origin[1] / spacing) * spacing)


# --------------------------------------------------------------------------
# Minimap
# --------------------------------------------------------------------------


def mini_map(
    ctx: EditorContext,
    size_fraction: float = 0.2,
    location: str = MiniMapLocation.TOP_LEFT,
) -> None:
    """Ask for a minimap of the whole graph in one corner of the editor.

    Parameters
    ----------
    ctx : EditorContext
        The editor. Must be called between :func:`begin_node_editor` and
        :func:`end_node_editor`.
    size_fraction : float
        The minimap's width as a fraction of the editor's.
    location : str
        A :class:`MiniMapLocation` corner.

    Notes
    -----
    This records the request; :func:`end_node_editor` draws it. Two reasons,
    and both are the kind of thing that only shows up on screen:

    * the map has to be **on top**, and a host calls this at the top of its
      editor block, before any node exists -- drawing here would put it under
      every node, where a large node hides it completely;
    * it is a picture of *this* frame's graph, so it cannot be drawn before
      the nodes have been submitted and measured.

    Deferring gets both without asking the caller to call it last.
    """
    _require("editor", "mini_map")
    ctx._minimap = (float(size_fraction), location)


def _draw_mini_map(ctx: EditorContext) -> None:
    """Paint the requested minimap, after the channels have merged.

    Parameters
    ----------
    ctx : EditorContext
        The editor being finished.
    """
    if ctx._minimap is None:
        return
    size_fraction, location = ctx._minimap
    bounds = ctx._content_bounds
    box = ctx._box
    draw = ctx._draw
    style = ctx.style

    width = max(box[2] * size_fraction, 40.0)
    height = max(box[3] * size_fraction, 40.0)
    off_x, off_y = style.mini_map_offset
    if location in (MiniMapLocation.TOP_LEFT, MiniMapLocation.BOTTOM_LEFT):
        x = box[0] + off_x
    else:
        x = box[0] + box[2] - width - off_x
    if location in (MiniMapLocation.TOP_LEFT, MiniMapLocation.TOP_RIGHT):
        y = box[1] + off_y
    else:
        y = box[1] + box[3] - height - off_y

    draw.add_rect_filled((x, y), (x + width, y + height),
                         style.colors[Col.MINI_MAP_BACKGROUND], 4.0)
    draw.add_rect((x, y), (x + width, y + height), style.colors[Col.MINI_MAP_OUTLINE], 4.0)
    if bounds is None:
        return

    pad_x, pad_y = style.mini_map_padding
    gx0, gy0, gx1, gy1 = bounds
    span_x, span_y = max(gx1 - gx0, 1e-6), max(gy1 - gy0, 1e-6)
    scale = min((width - 2 * pad_x) / span_x, (height - 2 * pad_y) / span_y)

    def project(point: tuple) -> tuple:
        """Map a grid-space point into the minimap's rect."""
        return (x + pad_x + (point[0] - gx0) * scale,
                y + pad_y + (point[1] - gy0) * scale)

    zoom = ctx.canvas.zoom or 1.0
    for node in ctx._nodes.values():
        if not node.alive:
            continue
        nx0, ny0, nx1, ny1 = node.rect
        p0 = project(node.origin)
        p1 = project((node.origin[0] + (nx1 - nx0) / zoom,
                      node.origin[1] + (ny1 - ny0) / zoom))
        colour = style.colors[
            Col.MINI_MAP_NODE_BACKGROUND_SELECTED
            if node.id in ctx.selected_nodes
            else Col.MINI_MAP_NODE_BACKGROUND
        ]
        # Square corners, not rounded. A minimap node is a handful of pixels
        # across, and a rounded rect is drawn as a filled convex polygon whose
        # corner arcs, at that size, cross each other -- so every node in the
        # map gets a diagonal slash through it. Rounding this small buys
        # nothing anyway.
        draw.add_rect_filled(p0, p1, colour)
        draw.add_rect(p0, p1, style.colors[Col.MINI_MAP_NODE_OUTLINE])

    # The viewport rectangle: which part of the graph the editor is showing.
    #
    # Clamped into the map, and normalised. The viewport routinely extends past
    # the graph's bounds -- that is what panning to an empty corner *is* -- and
    # projecting it unclamped puts corners outside the map, where the outline
    # is drawn over the editor. Worse, a corner far enough out swaps the two
    # points, and a rect with negative width rasterises as a diagonal streak
    # across the map rather than as nothing.
    view0 = project(ctx.canvas.to_grid((box[0], box[1])))
    view1 = project(ctx.canvas.to_grid((box[0] + box[2], box[1] + box[3])))
    lo = (min(max(min(view0[0], view1[0]), x), x + width),
          min(max(min(view0[1], view1[1]), y), y + height))
    hi = (min(max(max(view0[0], view1[0]), x), x + width),
          min(max(max(view0[1], view1[1]), y), y + height))
    if hi[0] - lo[0] >= 1.0 and hi[1] - lo[1] >= 1.0:
        draw.add_rect_filled(lo, hi, style.colors[Col.MINI_MAP_CANVAS])
        draw.add_rect(lo, hi, style.colors[Col.MINI_MAP_CANVAS_OUTLINE])
