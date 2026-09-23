"""``emtk.im_core``: the immediate-mode context -- the reference's `imgui.cpp`.

Every ImGui widget is written against a handful of ambient things: the draw
list, ``ImGuiIO`` (mouse position, buttons, clicks, modifiers, delta time), a
layout cursor (``ItemSize / SameLine / Indent``), an ID stack (``PushID``),
per-widget storage (``ImGuiStorage``), the style, popups and tooltips, and
``ButtonBehavior`` -- the one press primitive under every button, slider and
drag. emtk's controls are retained objects with explicit boxes and no ambient
state, on purpose. This module is the bridge:

* :class:`IO` -- the per-event / per-frame snapshot a port reads;
* :class:`Context` -- ``ctx.draw`` (a :class:`~.drawlist.DrawList`), ``ctx.io``,
  ``ctx.layout`` (a :class:`~.layout.Layout`), ``ctx.style``, ``ctx.storage``,
  ``push_id / pop_id / get_id``, ``item_size / item_add /
  is_item_hovered / is_item_active / is_item_clicked``, ``button_behavior``,
  ``begin_child / end_child``, ``open_popup / begin_popup / end_popup``,
  ``set_tooltip``, ``request_frame``;
* :class:`ImWidget` -- wraps ``def widget(ctx, ...)`` as a retained
  :class:`~.control.Control`: its ``draw`` fills the IO with the last known
  pointer state and replays the function; ``press / drag / release / key /
  scroll`` update the IO and replay it once more so the port sees the event
  the way ImGui would (hovered this frame, mouse down this frame...).

A port is therefore: transliterate the C++ body as ``def my_widget(ctx, label,
value)`` using ``ctx.draw.add_*``, ``ctx.io.*``, ``ctx.layout.*``, then
``MyWidget = ImWidget(my_widget)`` and use it like any emtk control. The
scaffolder ``tools/port_imgui_widget.py`` emits both shapes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any, Callable, Optional

from .control import Control
from .drawlist import DrawList
from .events import LEFT_BUTTON, MIDDLE_BUTTON, RIGHT_BUTTON
from .layout import Layout, LayoutStyle
from .painter import Painter
from .style import hit

__all__ = ["IO", "BackendFlags", "Col", "ConfigFlags", "Context", "ImWidget",
           "ItemFlags", "Style", "painter_capabilities", "split_label",
           "ButtonFlags", "create_context", "set_current_context",
           "get_current_context", "frame", "get_io", "get_style",
           "get_window_draw_list", "get_foreground_draw_list",
           "get_background_draw_list", "PLACE_FRAME", "PLACE_CASCADE",
           "CASCADE_SIZE", "CASCADE_STEP", "CASCADE_FRACTION"]

Rect = tuple[float, float, float, float]

#: Placement for a window opened with no box: it *is* the frame, and keeps
#: being the frame when the host is resized. The default, and what a single
#: full-window application wants -- one window, filling its host, following
#: it.
PLACE_FRAME = "frame"

#: Placement for a window opened with no box: it is placed **once**, at a
#: stepped offset inside the frame, and then keeps that box. What an
#: application with floating sub-windows wants: without it every one of them
#: takes the whole frame and they draw on top of each other and of the main
#: window, which is exactly one window's worth of visible interface no
#: matter how many were opened.
PLACE_CASCADE = "cascade"

#: The size a cascaded window is first given, in the frame's units. Big
#: enough to hold a handful of rows and a plot, small enough that several
#: fit on a modest frame; a window that wanted more says so with
#: ``set_next_window_size`` or ``auto_resize``.
CASCADE_SIZE = (360.0, 260.0)

#: The most of the frame a cascaded window takes on each axis.
#: :data:`CASCADE_SIZE` is a ceiling and this is the other bound: on a small
#: frame a fixed size leaves room for exactly one window, every window lands
#: in the only place that fits, and the cascade is back to the pile it
#: exists to avoid.
CASCADE_FRACTION = 0.6

#: How far each cascaded window is offset from the one before, and the
#: margin the first one starts at. Cascading rather than stacking is what
#: makes the window *underneath* reachable: identical boxes hide each other
#: completely, and a title bar's worth of offset is enough to grab.
CASCADE_STEP = 28.0


class ButtonFlags:
    NONE = 0
    MOUSE_BUTTON_LEFT = 1 << 0
    MOUSE_BUTTON_RIGHT = 1 << 1
    MOUSE_BUTTON_MIDDLE = 1 << 2
    PRESSED_ON_CLICK = 1 << 4         # return pressed on the down edge
    PRESSED_ON_RELEASE = 1 << 5       # (default) on the up edge, if still inside
    REPEAT = 1 << 6                   # pressed again while held (needs ticks)
    ALLOW_OVERLAP = 1 << 7
    NO_HOLDING_ACTIVE_ID = 1 << 8


@dataclass
class IO:
    """What a port reads about the pointer, the keys and the clock."""

    mouse_pos: tuple[float, float] = (-1.0, -1.0)
    #: Buttons currently held: index 0 left, 1 right, 2 middle.
    mouse_down: list[bool] = field(default_factory=lambda: [False, False, False])
    #: Went down / came up in *this* delivery.
    mouse_clicked: list[bool] = field(default_factory=lambda: [False, False, False])
    mouse_released: list[bool] = field(default_factory=lambda: [False, False, False])
    mouse_double_clicked: list[bool] = field(default_factory=lambda: [False, False, False])
    mouse_clicked_pos: list[tuple[float, float]] = field(default_factory=lambda: [(-1.0, -1.0)] * 3)
    #: ``io.MousePos`` last frame -- what makes ``MouseDelta`` a delta.
    mouse_pos_prev: tuple[float, float] = (-1.0, -1.0)
    #: Where the pointer was when this frame began; becomes
    #: :attr:`mouse_pos_prev` at the next :meth:`begin_frame`.
    mouse_pos_frame: tuple[float, float] = (-1.0, -1.0)
    #: ``io.FontGlobalScale``: the atlas is one bitmap face, so this stays 1.
    font_global_scale: float = 1.0
    mouse_wheel: float = 0.0
    mouse_wheel_h: float = 0.0
    key_ctrl: bool = False
    key_shift: bool = False
    key_alt: bool = False
    key_super: bool = False
    #: The key delivered this event (a ``emtk.keys`` constant or a character code), else 0.
    key: int = 0
    text: str = ""
    delta_time: float = 1.0 / 60.0
    now: float = 0.0
    frame_count: int = 0
    #: Who owns the clock. Dear ImGui does not read one: the backend sets
    #: ``io.DeltaTime`` before ``NewFrame`` and the context accumulates it into
    #: ``g.Time``. Set this ``False`` and do the same -- which is what a test,
    #: a recorded session or a fixed-step renderer needs, and what a port of a
    #: timing-dependent widget (a repeating button, an animation) needs in
    #: order to be *testable* at all.
    wall_clock: bool = True
    #: ``io.ConfigFlags`` -- what the application asked for.
    config_flags: int = 0
    #: ``io.BackendFlags`` -- what the painter in hand can do. Filled in by
    #: the context each frame, so it is never a stale promise.
    backend_flags: int = 0
    #: ``io.WantCaptureMouse`` / ``WantCaptureKeyboard``.
    want_capture_mouse: bool = False
    want_capture_keyboard: bool = False

    def begin_frame(self, now: Optional[float] = None) -> None:
        # ``NewFrame``: ``MouseDelta = MousePos - MousePosPrev``, then
        # ``MousePosPrev = MousePos``. Copying the *current* position into
        # ``mouse_pos_prev`` here -- what this did -- made the delta zero in
        # every frame whose pointer was moved by the host between frames,
        # which is every frame: a drag that pans or rotates by the delta
        # never moved. The previous frame's position is kept instead.
        self.mouse_pos_prev = tuple(self.mouse_pos_frame)
        self.mouse_pos_frame = tuple(self.mouse_pos)
        if now is not None:
            self.delta_time = max(1e-6, float(now) - self.now) if self.now else 1.0 / 60.0
            self.now = float(now)
        elif self.wall_clock:
            t = time.monotonic()
            self.delta_time = max(1e-6, t - self.now) if self.now else 1.0 / 60.0
            self.now = t
        else:
            self.now += self.delta_time
        self.frame_count += 1

    @property
    def mouse_delta(self) -> tuple[float, float]:
        """``io.MouseDelta``: this frame's pointer move, since last frame.

        Zero when either position is unknown (``(-1, -1)``), as ImGui gives
        zero for an invalid ``MousePos`` -- otherwise the first frame after
        the pointer enters would jump by its whole coordinate.
        """
        if (tuple(self.mouse_pos) == (-1.0, -1.0)
                or tuple(self.mouse_pos_prev) == (-1.0, -1.0)):
            return (0.0, 0.0)
        return (self.mouse_pos[0] - self.mouse_pos_prev[0],
                self.mouse_pos[1] - self.mouse_pos_prev[1])

    def end_event(self) -> None:
        """Clear the per-delivery edges once the widget has seen them."""
        self.mouse_clicked = [False, False, False]
        self.mouse_released = [False, False, False]
        self.mouse_double_clicked = [False, False, False]
        self.mouse_wheel = 0.0
        self.mouse_wheel_h = 0.0
        self.key = 0
        self.text = ""

    def mouse_drag_delta(self, button: int = 0) -> tuple[float, float]:
        ox, oy = self.mouse_clicked_pos[button]
        return (self.mouse_pos[0] - ox, self.mouse_pos[1] - oy)


class Col:
    """``ImGuiCol_``: the style colour a widget draws itself with.

    Indices rather than names, as in the reference, so ``push_style_color``
    takes the same first argument a C++ port passes. The defaults come from
    :mod:`emtk.style`, which already carries Dear ImGui's own palette
    (``FRAME_BG``, ``BUTTON_HOVERED``, ``CHECK_MARK`` = 66,150,250).
    """

    TEXT = 0
    TEXT_DISABLED = 1
    WINDOW_BG = 2
    POPUP_BG = 3
    BORDER = 4
    FRAME_BG = 5
    FRAME_BG_HOVERED = 6
    FRAME_BG_ACTIVE = 7
    TITLE_BG = 8
    TITLE_BG_ACTIVE = 9
    MENU_BAR_BG = 10
    SCROLLBAR_BG = 11
    SCROLLBAR_GRAB = 12
    CHECK_MARK = 13
    SLIDER_GRAB = 14
    SLIDER_GRAB_ACTIVE = 15
    BUTTON = 16
    BUTTON_HOVERED = 17
    BUTTON_ACTIVE = 18
    HEADER = 19
    HEADER_HOVERED = 20
    HEADER_ACTIVE = 21
    SEPARATOR = 22
    SEPARATOR_HOVERED = 23
    SEPARATOR_ACTIVE = 24
    TAB = 25
    TAB_SELECTED = 26
    PLOT_LINES = 27
    PLOT_HISTOGRAM = 28
    COUNT = 29


def _default_colors() -> dict[int, tuple]:
    from . import style as _style

    return {
        Col.TEXT: _style.TEXT,
        Col.TEXT_DISABLED: _style.TEXT_DISABLED,
        Col.WINDOW_BG: _style.WINDOW_BG,
        Col.POPUP_BG: _style.POPUP_BG,
        Col.BORDER: _style.BORDER,
        Col.FRAME_BG: _style.FRAME_BG,
        Col.FRAME_BG_HOVERED: _style.FRAME_BG_HOVERED,
        Col.FRAME_BG_ACTIVE: _style.FRAME_BG_ACTIVE,
        Col.TITLE_BG: _style.TITLE_BG,
        Col.TITLE_BG_ACTIVE: _style.TITLE_BG_ACTIVE,
        Col.MENU_BAR_BG: _style.MENU_BAR_BG,
        Col.SCROLLBAR_BG: _style.SCROLLBAR_BG,
        Col.SCROLLBAR_GRAB: _style.SCROLLBAR_GRAB,
        Col.CHECK_MARK: _style.CHECK_MARK,
        Col.SLIDER_GRAB: _style.SLIDER_GRAB,
        Col.SLIDER_GRAB_ACTIVE: _style.SLIDER_GRAB_ACTIVE,
        Col.BUTTON: _style.BUTTON,
        Col.BUTTON_HOVERED: _style.BUTTON_HOVERED,
        Col.BUTTON_ACTIVE: _style.BUTTON_ACTIVE,
        Col.HEADER: _style.HEADER,
        Col.HEADER_HOVERED: _style.HEADER_HOVERED,
        Col.HEADER_ACTIVE: _style.HEADER_ACTIVE,
        Col.SEPARATOR: _style.BORDER,
        Col.SEPARATOR_HOVERED: _style.SEPARATOR_HOVERED,
        Col.SEPARATOR_ACTIVE: _style.SEPARATOR_ACTIVE,
        Col.TAB: _style.TAB,
        Col.TAB_SELECTED: _style.TAB_SELECTED,
        Col.PLOT_LINES: _style.PLOT_LINES,
        Col.PLOT_HISTOGRAM: _style.PLOT_HISTOGRAM,
    }


class ConfigFlags:
    """``ImGuiConfigFlags_``: what the *application* has turned on."""

    NONE = 0
    NAV_ENABLE_KEYBOARD = 1 << 0
    NAV_ENABLE_GAMEPAD = 1 << 1
    NO_MOUSE = 1 << 4
    NO_MOUSE_CURSOR_CHANGE = 1 << 5
    DOCKING_ENABLE = 1 << 6


class BackendFlags:
    """``ImGuiBackendFlags_``: what the backend can actually do.

    emtk has one backend -- the Painter -- and its optional operations are
    exactly what these say. They are filled in from the painter in hand, so a
    port can ask "can I draw an image here?" and get a true answer instead of
    finding out by the picture being wrong.
    """

    NONE = 0
    HAS_GAMEPAD = 1 << 0
    HAS_MOUSE_CURSORS = 1 << 1
    HAS_SET_MOUSE_POS = 1 << 2
    RENDERER_HAS_VTX_OFFSET = 1 << 3
    RENDERER_HAS_TEXTURES = 1 << 4
    #: emtk's own: the Painter's optional operations.
    RENDERER_HAS_IMAGES = 1 << 8
    RENDERER_HAS_FONTS = 1 << 9
    RENDERER_HAS_ROTATED_TEXT = 1 << 10


class ItemFlags:
    """``ImGuiItemFlags_``: what the *next* items behave like."""

    NONE = 0
    BUTTON_REPEAT = 1 << 0
    DISABLED = 1 << 1
    #: ``ImGuiItemFlags_LiveEditOnInput*``: report a change while the value is
    #: being dragged or typed, rather than only when the widget is let go.
    LIVE_EDIT_ON_INPUT = 1 << 2
    LIVE_EDIT_ON_INPUT_TEXT = 1 << 3
    LIVE_EDIT_ON_INPUT_SCALAR = 1 << 4
    NO_NAV = 1 << 5
    NO_TAB_STOP = 1 << 6


@dataclass
class Style:
    """``ImGuiStyle``, in pixels and 0-255 colours.

    The colours are a stack, not constants: a widget that reads
    ``style.color(Col.BUTTON)`` can be recoloured around a call, which is what
    ``PushStyleColor``/``PopStyleColor`` are for and what the demo's row of
    seven coloured buttons needs.
    """

    frame_padding: tuple[float, float] = (4.0, 3.0)
    item_spacing: tuple[float, float] = (8.0, 4.0)
    item_inner_spacing: tuple[float, float] = (4.0, 4.0)
    frame_rounding: float = 0.0
    #: ``FrameBorderSize``: an outline in ``Col.BORDER`` around buttons, check
    #: boxes and fields. Zero (the dark theme) draws none; a light desktop
    #: theme needs it, since a white field on a pale window has no edge.
    frame_border_size: float = 0.0
    #: ``WindowBorderSize``: the outline of a window's box (1, as the reference).
    window_border_size: float = 1.0
    grab_min_size: float = 12.0
    grab_rounding: float = 0.0
    #: What ``BeginDisabled`` multiplies colours by, as ``ImGuiStyle`` does.
    disabled_alpha: float = 0.6
    colors: dict = field(default_factory=_default_colors)

    def color(self, which, default=(200, 200, 200, 255)):
        return self.colors.get(which, default)



def split_label(label: str) -> tuple[str, str]:
    """``"Title###id"`` -> ``("Title", "id")``; ``"Title##x"`` -> ``("Title", "Title##x")``.

    Dear ImGui's two markers, and they mean different things: ``##`` hides the
    rest from the *label* while keeping it in the id, so two things can be
    called the same and still be told apart; ``###`` replaces the id outright,
    so a label that changes every frame keeps one identity. Without the second,
    the demo's animated title creates a new window sixty times a second.
    """
    if "###" in label:
        shown, _, key = label.partition("###")
        return (shown, key)
    if "##" in label:
        return (label.split("##", 1)[0], label)
    return (label, label)


def painter_capabilities(painter) -> int:
    """``io.BackendFlags`` for the painter in hand."""
    flags = BackendFlags.HAS_MOUSE_CURSORS
    if callable(getattr(painter, "image", None)):
        flags |= BackendFlags.RENDERER_HAS_IMAGES | BackendFlags.RENDERER_HAS_TEXTURES
    if callable(getattr(painter, "set_font", None)):
        flags |= BackendFlags.RENDERER_HAS_FONTS
    if callable(getattr(painter, "text_rotated", None)):
        flags |= BackendFlags.RENDERER_HAS_ROTATED_TEXT
    return flags


@dataclass
class _Window:
    """``ImGuiWindow``, cut down to what ordering and hit-testing need.

    One entry in the context's display list. ``no_mouse_inputs`` is
    ``ImGuiWindowFlags_NoMouseInputs``: drawn, never hit. Saying it with a flag
    on the entry rather than by leaving the window out of a second list is the
    whole point -- a second list is the thing that drifts out of step with the
    first, and then what you see is not what you can click.
    """

    name: str
    box: Rect
    #: True when the window was never given a box of its own, and so takes
    #: the frame's. Such a window has to *keep* taking it: the box is stored
    #: across frames, and a stored box does not follow a host that resized.
    #: Without this the first frame's size is the size forever -- the content
    #: stops at the old edge and the rest of a widened window is blank.
    follows_frame: bool = False
    #: True when the box was decided **once** and is the window's to keep --
    #: by a cascade placement, or by a ``SetNextWindowPos``/``Size`` under
    #: any condition but ``Always``.
    #:
    #: This sits *beside* :attr:`follows_frame` rather than replacing it,
    #: and the two are not each other's opposite. A window handed an
    #: explicit box on every ``begin`` follows neither the frame nor its own
    #: memory: the caller drives it, and it is not sticky. A single
    #: full-window application still wants the frame-following case, which is
    #: why that is the default and this is opt-in -- see
    #: :meth:`Context.set_window_placement`.
    sticky: bool = False
    #: What is *drawn* in the title bar. ``Begin("Animated title 3###Anim")``
    #: shows the left part and keeps its identity in the right, so a title that
    #: changes every frame does not make a new window every frame; and
    #: ``Begin("Same title##1")`` shows one title under two identities.
    title: str = ""
    active: bool = True
    #: Whether it was drawn on the *previous* frame. False for a window that
    #: has just been created, which is what makes `IsWindowAppearing` answer --
    #: defaulted to True, a window could never be new.
    was_active: bool = False
    hidden: bool = False
    no_mouse_inputs: bool = False
    #: Where the next item goes, and how far the content reaches.
    scroll: tuple[float, float] = (0.0, 0.0)
    content_size: tuple[float, float] = (0.0, 0.0)
    #: ``ImGuiWindowFlags_AlwaysAutoResize``: the box follows the content.
    auto_resize: bool = False
    #: ``SetNextWindowSizeConstraints``: the bounds auto-resize stays inside.
    size_min: tuple[float, float] | None = None
    size_max: tuple[float, float] | None = None
    #: Which dock node this window is in, if any, and whether it is the tab on
    #: top of that node this frame.
    dock_id: int = 0
    dock_tab_active: bool = True


class Context:
    """The ambient state an ImGui-style function reads, made explicit and per-call.

    Parameters
    ----------
    painter : Painter
        Where to draw; ``ctx.draw`` wraps it.
    box : (x, y, w, h)
        The region the widget lays out inside (the retained control's box).
    io, style, storage
        Shared across calls by :class:`ImWidget`; a bare ``Context`` makes fresh ones.
    """

    def __init__(self, painter: Painter, box: Rect, io: Optional[IO] = None,
                 style: Optional[Style] = None, storage: Optional[dict] = None,
                 layout_style: Optional[LayoutStyle] = None) -> None:
        self.p = painter
        self.draw = DrawList(painter)
        self.io = io if io is not None else IO()
        self.style = style if style is not None else Style()
        self.storage: dict = storage if storage is not None else {}
        self.box = box
        self.layout = Layout(painter, *box, style=layout_style)
        self._ids: list[Any] = []
        self._last_item: Optional[Rect] = None
        self._last_id: Any = None
        self._child: list[tuple[Layout, Rect]] = []
        self.hovered_id: Any = None
        self.active_id: Any = self.storage.get("__active_id__")
        self.frame_requested = False
        self._popups: dict = self.storage.setdefault("__popups__", {})
        self.tooltip: Optional[str] = None
        #: `g.HoveredId` from the frame before. ImGui answers "is this item
        #: hovered" from the id claimed *this* frame, but a widget submitted
        #: before the pointer moved needs last frame's answer; ImGui keeps both
        #: (`g.HoveredIdPreviousFrame`).
        self.item_flags = ItemFlags.NONE
        #: Keyboard navigation. `nav_id` is the focused item; the ring is the
        #: order items were submitted in, which *is* the tab order -- the
        #: reference derives it the same way rather than keeping a second list.
        self.nav_id: Any = self.storage.get("__nav_id__")
        self.nav_ring: list = []
        self.nav_request = 0          # -1 back, +1 forward, 0 none
        self.nav_focus_next = False   # `SetKeyboardFocusHere`
        self.nav_visible = True
        self._style_stack: list = []
        self._item_flag_stack: list[int] = []
        self._next_item_width: Optional[float] = None
        self._align_text_to_frame = False
        #: How long a held repeating button waits, then how often it fires --
        #: ImGui's `KeyRepeatDelay` / `KeyRepeatRate`.
        self.key_repeat_delay = 0.275
        self.key_repeat_rate = 0.050
        self.hovered_id_previous_frame: Any = None
        #: `g.ActiveIdPreviousFrame`. Without it "did this item just become
        #: active" cannot be told from "is it active", and "did it just stop"
        #: cannot be told from "it is not active" -- which made
        #: `is_item_deactivated` true for every item that had never been
        #: touched.
        self.active_id_previous_frame: Any = None
        self.hovered_id_allow_overlap = False
        self.active_id_allow_overlap = False
        #: The window stack. One list in display order, exactly as ImGui's
        #: `g.Windows`: painting walks it forward and hit-testing walks it
        #: backward (`FindHoveredWindowEx`), so what is drawn last is what
        #: takes the click, and no second ordering can drift from it.
        self.windows: list[_Window] = self.storage.setdefault("__windows__", [])
        #: How a window with no box of its own is first placed -- see
        #: :meth:`set_window_placement`. In the storage rather than on the
        #: context because a context lives one frame and this has to outlive
        #: the frame that set it.
        self.storage.setdefault("__window_placement__", PLACE_FRAME)
        self.hovered_window: Optional[_Window] = None
        self._window_stack: list[_Window] = []
        self.current_window: Optional[_Window] = None
        self.clip_rect: Rect = box

    # -- the frame ------------------------------------------------------------ #
    def new_frame(self, now: Optional[float] = None) -> None:
        """``ImGui::NewFrame``: age the ids and find the hovered window."""
        self.io.begin_frame(now)
        self.io.backend_flags = painter_capabilities(self.p)
        self.hovered_id_previous_frame = self.hovered_id
        self.active_id_previous_frame = self.active_id
        self.hovered_id = None
        self.hovered_id_allow_overlap = False
        self._active_id_alive = False
        self.hovered_window = self.find_hovered_window(*self.io.mouse_pos)
        for window in self.windows:
            window.was_active, window.active = window.active, False
        self.layout.reset(*self.box)

    def end_frame(self) -> None:
        """``ImGui::EndFrame``: move the focus, then spend the edges.

        The move happens *after* submission because the ring is the order the
        items were submitted in -- Tab pressed on this frame lands on the next
        item of this frame's list, and the next frame draws it focused.
        """
        if self.nav_request and self.nav_ring:
            if self.nav_id in self.nav_ring:
                at = self.nav_ring.index(self.nav_id) + self.nav_request
            else:
                at = 0 if self.nav_request > 0 else len(self.nav_ring) - 1
            self.nav_id = self.nav_ring[at % len(self.nav_ring)]
            self.storage["__nav_id__"] = self.nav_id
        self.nav_request = 0
        # ImGui's ``ActiveIdIsAlive``: an active item that was not submitted
        # this frame is gone (a list entry that navigated away on its own
        # click). With no button held there is no drag it could be part of,
        # so it lets go -- otherwise it would hold the pointer and every other
        # item would refuse the next click.
        if (self.active_id is not None and not getattr(self, "_active_id_alive", True)
                and not any(self.io.mouse_down)):
            self.clear_active_id()
        self.io.want_capture_keyboard = self.nav_id is not None
        self.io.want_capture_mouse = self.hovered_window is not None
        self.io.end_event()

    # -- keyboard navigation --------------------------------------------- #
    def nav_add(self, item_id: Any) -> None:
        """Put an item in the tab ring, and take focus if it was asked for."""
        if self.item_flags & (ItemFlags.NO_NAV | ItemFlags.NO_TAB_STOP):
            return
        if item_id is None or item_id in self.nav_ring:
            return
        self.nav_ring.append(item_id)
        if self.nav_focus_next:
            self.nav_focus_next = False
            self.nav_id = item_id
            self.storage["__nav_id__"] = item_id

    def nav_move(self, direction: int) -> None:
        """Ask for the focus to move. ``Tab`` / ``Shift+Tab``."""
        self.nav_request = int(direction)

    def is_nav_focused(self, item_id: Any) -> bool:
        return self.nav_id is not None and self.nav_id == item_id

    def set_keyboard_focus_here(self, offset: int = 0) -> None:
        """``SetKeyboardFocusHere``: 0 = the next item, -1 = the last one."""
        if offset < 0:
            self.nav_id = self._last_id
            self.storage["__nav_id__"] = self.nav_id
        else:
            self.nav_focus_next = True

    def find_hovered_window(self, x: float, y: float) -> Optional["_Window"]:
        """``FindHoveredWindowEx``: the display list, walked backwards.

        > for (int i = g.Windows.Size - 1; i >= 0; i--)

        A window that is drawn but takes no input says so with a flag
        (`ImGuiWindowFlags_NoMouseInputs`) rather than by being absent from a
        second list, because a second list is the thing that drifts.
        """
        for window in reversed(self.windows):
            # Active now or last frame: hit-testing runs at the start of a
            # frame, before this frame's windows have been submitted, but a
            # caller asking mid-frame means the window in front of it.
            if not (window.active or window.was_active):
                continue
            if window.hidden or window.no_mouse_inputs:
                continue
            if hit(x, y, *window.box):
                return window
        return None

    # -- style, item flags and the next-item stack ----------------------------- #
    def push_style_color(self, which, colour) -> None:
        """``PushStyleColor``: this colour until the matching pop."""
        self._style_stack.append((which, self.style.colors.get(which)))
        self.style.colors[which] = colour

    def pop_style_color(self, count: int = 1) -> None:
        for _ in range(max(int(count), 0)):
            if not self._style_stack:
                return
            which, previous = self._style_stack.pop()
            if previous is None:
                self.style.colors.pop(which, None)
            else:
                self.style.colors[which] = previous

    def push_item_flag(self, flag: int, enabled: bool) -> None:
        """``PushItemFlag``: e.g. ``ItemFlags.BUTTON_REPEAT`` for a repeater."""
        self._item_flag_stack.append(self.item_flags)
        self.item_flags = (self.item_flags | flag) if enabled else (self.item_flags & ~flag)

    def pop_item_flag(self) -> None:
        if self._item_flag_stack:
            self.item_flags = self._item_flag_stack.pop()

    def set_next_item_width(self, width: float) -> None:
        """``SetNextItemWidth``: how wide the next framed widget is."""
        self._next_item_width = float(width)

    def take_next_item_width(self, default: Optional[float] = None) -> Optional[float]:
        """The width the next framed widget should get, and forget the one-shot.

        Parameters
        ----------
        default : float, optional
            What to use when nothing has asked for a width.

        Returns
        -------
        float or None
            ``None`` for either is "as wide as there is room for", which is
            what the layout means by a row with no width -- so it is a value
            here, not a missing one.

        Notes
        -----
        Two things ask, and only one of them is a one-shot.
        ``SetNextItemWidth`` applies to the **next** item and is consumed;
        ``PushItemWidth`` applies to **every** item until the matching pop.
        Treating the push as a one-shot -- which is what happened, because the
        push implemented itself by calling the setter -- means the first
        control in a group gets the width and every control after it falls back
        to "fill the row".

        In a panel that is invisible, because filling the row is what those
        controls would do anyway. In a **node**, where the row is the whole
        editor, the second control stretches the node across the viewport, the
        graph's fit-to-content then zooms out to frame it, and every node piles
        up in the corner. That is one missing fallback, and it presents as the
        editor being broken.
        """
        width = self._next_item_width
        self._next_item_width = None
        if width is None:
            stack = self.state(("item_width",)).get("stack") or []
            if stack:
                width = stack[-1]
        return default if width is None else width

    def align_text_to_frame_padding(self) -> None:
        """``AlignTextToFramePadding``: the next line is a frame tall.

        Without it a ``Text`` + ``SameLine`` + ``Button`` sequence puts the text
        a little too high, because the text row is shorter than the framed one.
        """
        self._align_text_to_frame = True

    # -- IDs and storage ----------------------------------------------------- #
    def push_id(self, key: Any) -> None:
        self._ids.append(key)

    def pop_id(self) -> None:
        if self._ids:
            self._ids.pop()

    def get_id(self, label: str) -> tuple:
        # ImGui's "label##id" and "##id" spellings: what follows ## is the id.
        key = label.split("##", 1)[1] if "##" in label else label
        return (*self._ids, key)

    def get_storage(self, key: Any = None) -> dict:
        """Per-**item** storage (``ImGuiStorage``): keyed by the id stack.

        This is what a widget remembers about *itself* -- whether a header is
        open, where a drag was last seen. Two widgets with the same label under
        different ``push_id`` scopes get different buckets, which is the whole
        point of the id stack.
        """
        k = ("__store__", *self._ids, key)
        return self.storage.setdefault(k, {})

    def state(self, key: Any) -> dict:
        """Context-wide state, keyed by *name alone*.

        The other half, and it has to be a separate door: a drag-and-drop
        payload, the clipboard, the log, which item has keyboard focus. Those
        belong to the *context*, and putting them in `get_storage` meant they
        inherited the id stack -- so a source inside ``push_id(0)`` wrote the
        payload to one bucket and a target inside ``push_id(2)`` read another,
        and a drop could never land.
        """
        return self.storage.setdefault(("__state__", key), {})

    # -- items ------------------------------------------------------------------ #
    def item_size(self, w: float, h: float) -> Rect:
        """Advance the layout by an item of ``(w, h)`` and return its box."""
        box = self.layout.row(height=h, width=w)
        return box

    def item_add(self, box: Rect, item_id: Any = None) -> bool:
        """``ItemAdd``: record the box just drawn, and say if it is hovered.

        This is the whole of ImGui's answer to "what is under the pointer", and
        the reason it needs no hit list: a widget registers the rectangle it is
        *drawing*, as it draws it, so a widget cannot be clickable somewhere it
        did not draw. Two lists -- one for painting, one for hit-testing --
        cannot say that, however carefully they are kept in step.
        """
        self._last_item = box
        self._last_id = item_id
        if item_id is not None:
            self.nav_add(item_id)
            if item_id == self.active_id:
                self._active_id_alive = True
        return self.item_hoverable(box, item_id)

    def item_hoverable(self, box: Rect, item_id: Any = None) -> bool:
        """``ItemHoverable``: is the pointer on *box*, and is *box* on top?

        The order of the tests is ImGui's (`imgui.cpp`):

        > if (g.HoveredWindow != window) return false;
        > if (!IsMouseHoveringRect(bb.Min, bb.Max)) return false;
        > if (g.HoveredId != 0 && g.HoveredId != id && !g.HoveredIdAllowOverlap) return false;

        The third line is what makes overlap deterministic: the first item to
        claim the pointer keeps it, and an item that means to sit on top of
        another says so with ``set_next_item_allow_overlap``.
        """
        if self.current_window is not None and self.hovered_window not in (
            None, self.current_window,
        ):
            return False
        if self.item_flags & ItemFlags.DISABLED:
            return False
        if self.io.mouse_pos == (-1.0, -1.0) or not hit(*self.io.mouse_pos, *box):
            return False
        if not self._overlaps_clip(box):
            return False
        key = item_id if item_id is not None else box
        if (self.hovered_id is not None and self.hovered_id != key
                and not self.hovered_id_allow_overlap):
            return False
        if (self.active_id is not None and self.active_id != key
                and not self.active_id_allow_overlap):
            return False
        self.hovered_id = key
        self.hovered_id_allow_overlap = False
        return True

    def set_next_item_allow_overlap(self) -> None:
        """``SetNextItemAllowOverlap``: this item may sit over the last one."""
        self.hovered_id_allow_overlap = True
        self.active_id_allow_overlap = True

    def _overlaps_clip(self, box: Rect) -> bool:
        """ImGui's clipping test: `bb.Overlaps(window->ClipRect)`."""
        cx, cy, cw, ch = self.clip_rect
        x, y, w, h = box
        return not (x > cx + cw or x + w < cx or y > cy + ch or y + h < cy)

    def is_item_hovered(self) -> bool:
        key = self._last_id if self._last_id is not None else self._last_item
        return key is not None and self.hovered_id == key

    def is_item_active(self) -> bool:
        return self._last_id is not None and self.active_id == self._last_id

    def is_item_clicked(self, button: int = 0) -> bool:
        return self.is_item_hovered() and bool(self.io.mouse_clicked[button])

    def get_item_rect(self) -> Optional[Rect]:
        return self._last_item

    def set_active_id(self, item_id: Any) -> None:
        self.active_id = item_id
        self.storage["__active_id__"] = item_id

    def clear_active_id(self) -> None:
        self.set_active_id(None)

    def button_behavior(self, box: Rect, item_id: Any, flags: int = 0) -> tuple[bool, bool, bool]:
        """ImGui's ``ButtonBehavior``: ``(hovered, held, pressed)`` for *box*.

        Down inside makes the item active (held); the press fires on release
        inside by default (``PRESSED_ON_RELEASE``) or on the down edge with
        ``PRESSED_ON_CLICK``. Release anywhere clears the active id.
        """
        io = self.io
        if self.item_flags & ItemFlags.DISABLED:
            # `BeginDisabled` means the item is *inert*: it still takes up its
            # space and still registers its box, so the layout and
            # `GetItemRect` are unchanged, but it neither hovers, holds nor
            # fires. Setting the flag and leaving the behaviour alone made the
            # demo's disabled block fully clickable.
            self.item_add(box, item_id)
            return (False, False, False)
        button = 0
        if flags & ButtonFlags.MOUSE_BUTTON_RIGHT:
            button = 1
        elif flags & ButtonFlags.MOUSE_BUTTON_MIDDLE:
            button = 2
        hovered = self.item_add(box, item_id)
        pressed = False
        if hovered and io.mouse_clicked[button]:
            if flags & ButtonFlags.PRESSED_ON_CLICK:
                pressed = True
            self.set_active_id(item_id)
        held = self.active_id == item_id and io.mouse_down[button]
        if held and (flags & ButtonFlags.REPEAT or self.item_flags & ItemFlags.BUTTON_REPEAT):
            # `ButtonBehavior` with `ImGuiItemFlags_ButtonRepeat`: fires again
            # while held, after a delay and then at a rate. The demo's arrow
            # buttons are the reference use.
            store = self.get_storage(item_id)
            started = store.setdefault("repeat_t0", io.now)
            elapsed = io.now - started
            if elapsed >= self.key_repeat_delay:
                ticks = int((elapsed - self.key_repeat_delay) / self.key_repeat_rate)
                if ticks > store.get("repeat_n", 0):
                    store["repeat_n"] = ticks
                    pressed = True
            self.request_frame()
        elif not held:
            self.get_storage(item_id).pop("repeat_t0", None)
            self.get_storage(item_id).pop("repeat_n", None)
        if self.active_id == item_id and io.mouse_released[button]:
            if hovered and not (flags & ButtonFlags.PRESSED_ON_CLICK):
                pressed = True
            self.clear_active_id()
        return hovered, held, pressed

    # -- windows --------------------------------------------------------------- #
    @property
    def window_placement(self) -> str:
        """Where a window opened with **no box** goes: the frame, or a cascade.

        Returns
        -------
        str
            :data:`PLACE_FRAME` (the default) or :data:`PLACE_CASCADE`.

        See Also
        --------
        set_window_placement
        """
        return self.storage.get("__window_placement__", PLACE_FRAME)

    def set_window_placement(self, placement: str) -> None:
        """Choose how a box-less window is first placed.

        Parameters
        ----------
        placement : str
            :data:`PLACE_FRAME` -- the window *is* the frame and keeps being
            the frame when the host resizes. One window filling its host.

            :data:`PLACE_CASCADE` -- the window is placed once, at a stepped
            offset inside the frame, and then keeps that box across frames.

        Raises
        ------
        ValueError
            On anything else. A misspelt mode that silently meant "frame"
            would look exactly like the bug this setting exists to fix.

        Notes
        -----
        emtk has no window manager and no ``.ini``, so nothing outside this
        remembers where a window was. With the default, an application with
        several floating sub-windows draws every one of them over the whole
        frame and over each other: what is on screen is the last one
        submitted, and the rest are invisible under it. That reads as
        "the other windows do not open".

        This is a **mode**, not a per-window flag, because it is a property
        of the application: either it is one full-window interface or it is a
        desktop of small ones. A window that wants something else still says
        so directly, with a box or with ``set_next_window_pos``.

        Set once, before the first frame or in it; it lives in the storage,
        so it outlives the context that set it.

        Examples
        --------
        >>> import emtk.im as im
        >>> from emtk.testing import PixelPainter
        >>> painter = PixelPainter(400, 300)
        >>> storage = {}
        >>> for _ in range(2):
        ...     with im.frame(painter, (0, 0, 400, 300), storage=storage) as ctx:
        ...         ctx.set_window_placement(im.PLACE_CASCADE)
        ...         _ = im.begin("first"); im.text("a"); im.end()
        ...         _ = im.begin("second"); im.text("b"); im.end()
        >>> [w.box[:2] for w in storage["__windows__"]]
        [(28.0, 28.0), (56.0, 56.0)]
        """
        if placement not in (PLACE_FRAME, PLACE_CASCADE):
            raise ValueError(
                f"window placement is {PLACE_FRAME!r} or {PLACE_CASCADE!r}, "
                f"not {placement!r}")
        self.storage["__window_placement__"] = placement

    def _first_box(self, claim: bool = True) -> Rect:
        """Where a window opened with no box of its own goes, once.

        Parameters
        ----------
        claim : bool, optional
            Whether to take the next step of the cascade. ``False`` for a
            window that is about to be placed outright anyway.

        Returns
        -------
        tuple
            The frame under :data:`PLACE_FRAME`, and a cascaded
            :data:`CASCADE_SIZE` box under :data:`PLACE_CASCADE`.

        Notes
        -----
        The cascade counts *placements*, not windows, and lives in the
        storage beside them -- so the second window of a session is offset
        from the first even though it was created a hundred frames later.
        It wraps rather than marching off the edge: past the point where a
        whole window would no longer fit, it starts again at the margin,
        which is what every window manager does and for the same reason.
        """
        x, y, width, height = self.box
        if self.window_placement == PLACE_FRAME:
            return self.box
        # :data:`CASCADE_SIZE` is a *ceiling*, and the frame is the other
        # bound. Without the fraction a small frame gets one window's worth
        # of room, every window lands in the only spot that fits, and the
        # cascade is back to the pile it exists to avoid.
        w = max(min(CASCADE_SIZE[0], width * CASCADE_FRACTION), 1.0)
        h = max(min(CASCADE_SIZE[1], height * CASCADE_FRACTION), 1.0)
        index = int(self.storage.get("__cascade__", 0))
        if claim:
            self.storage["__cascade__"] = index + 1
        # Positions are `margin + k * step` for as many k as leave the whole
        # window inside the frame -- a window placed past the edge is a
        # window the user cannot reach.
        across = int((width - w - CASCADE_STEP) // CASCADE_STEP) + 1
        down = int((height - h - CASCADE_STEP) // CASCADE_STEP) + 1
        step = index % max(min(across, down), 1)
        offset = CASCADE_STEP * (step + 1)
        return (x + offset, y + offset, w, h)

    def _place_next(self, window: _Window, pending: dict, created: bool) -> None:
        """Apply a pending ``SetNextWindowPos`` / ``SetNextWindowSize``.

        Parameters
        ----------
        window : _Window
        pending : dict
            The ``next_window`` state; the keys used here are consumed.
        created : bool
            Whether *window* was made on this call.

        Notes
        -----
        These were accepted and **discarded** before this, which is the
        quiet half of the same bug as the placement above: a port that says
        ``SetNextWindowPos`` -- the way ImGui code places a floating window
        -- had its instruction dropped and got the whole frame instead.

        The condition is ImGui's. ``Always`` (and no condition at all)
        re-places every frame; ``Once`` and ``FirstUseEver`` place on the
        frame the window is created, and are the same thing here because
        there is no ``.ini`` for "ever" to mean anything against;
        ``Appearing`` places whenever the window was absent last frame,
        which is what a window closed and reopened wants.

        A placement under any condition but ``Always`` makes the window
        :attr:`~_Window.sticky`: it was told where to go once, and keeping it
        there is the whole request.
        """
        pos = pending.pop("pos", None)
        size = pending.pop("size", None)
        pos_cond = int(pending.pop("pos_cond", 0) or 0)
        size_cond = int(pending.pop("size_cond", 0) or 0)
        if pos is None and size is None:
            return

        from .flags import Cond as _Cond  # noqa: PLC0415

        def wanted(cond: int) -> bool:
            if cond in (0, _Cond.ALWAYS):
                return True
            if cond & _Cond.APPEARING:
                return not window.was_active
            return created           # Once, FirstUseEver

        x, y, w, h = window.box
        applied: list[bool] = []          # was each applied placement one-time?
        if pos is not None and wanted(pos_cond):
            x, y = float(pos[0]), float(pos[1])
            applied.append(pos_cond not in (0, _Cond.ALWAYS))
        if size is not None and wanted(size_cond):
            w, h = float(size[0]), float(size[1])
            applied.append(size_cond not in (0, _Cond.ALWAYS))
        if applied:
            window.box = (x, y, w, h)
            # It has a box of its own now, so it must stop taking the
            # frame's -- otherwise the assignment in `begin` silently undoes
            # this.
            window.follows_frame = False
            # Sticky only if the placement was one-time. A window re-placed
            # every frame -- a main window pinned to the viewport is the
            # usual one -- is not remembering anything: its owner restates
            # it, and recording it as sticky would have a future `.ini` save
            # a box nobody asked to keep.
            window.sticky = any(applied)

    def begin(self, name: str, box: Optional[Rect] = None, flags: int = 0, *,
              no_mouse_inputs: bool = False, auto_resize: bool = False) -> bool:
        """``ImGui::Begin``: push a window and lay out inside it.

        The window keeps its place in the display list across frames, exactly
        as ImGui's ``g.Windows`` does -- creation order, moved to the end by
        focus -- and that one list is what both the drawing and the hit test
        walk.

        *flags* is an ``ImGuiWindowFlags`` mask. emtk windows have no title
        bar, no scrollbars and no chrome to suppress, so most of the mask is
        already true of every window here and is accepted and ignored -- the
        two that *say* something about behaviour, ``AlwaysAutoResize`` and
        ``NoMouseInputs``, are honoured. Accepting the whole mask is the
        point: a port writes ``Begin(name, nullptr, NoTitleBar | NoResize)``
        and it should not have to be edited to say the same thing about a
        window that never had a title bar to begin with.
        """
        from .flags import WindowFlags as _WF

        if flags & _WF.ALWAYS_AUTO_RESIZE:
            auto_resize = True
        if flags & (_WF.NO_MOUSE_INPUTS | _WF.NO_INPUTS):
            no_mouse_inputs = True
        title, key = split_label(name)
        window = next((w for w in self.windows if w.name == key), None)
        created = window is None
        pending = self.state(("next_window",))
        if created:
            # A window about to be placed outright takes no slot in the
            # cascade: a full-frame main window says `SetNextWindowPos` and
            # `SetNextWindowSize`, and letting it consume a step would leave
            # a gap in the offsets that reads as a placement bug.
            told = pending.get("pos") is not None and pending.get("size") is not None
            placed = box if box is not None else self._first_box(claim=not told)
            window = _Window(
                name=key, title=title, box=placed,
                follows_frame=box is None and self.window_placement == PLACE_FRAME,
                sticky=box is None and self.window_placement != PLACE_FRAME,
            )
            self.windows.append(window)
        window.title = title
        if box is not None:
            window.box = box
            window.follows_frame = False
            # Not sticky: the caller hands it a box every frame and so owns
            # the placement. Sticky means *emtk* is remembering one.
            window.sticky = False
        window.active = True
        window.no_mouse_inputs = no_mouse_inputs
        self._place_next(window, pending, created)
        constraints = pending.pop("constraints", None)
        if constraints is not None:
            window.size_min, window.size_max = constraints
        window.auto_resize = bool(auto_resize or pending.pop("auto_resize", False))
        # A window with no box of its own is the frame, so it follows the
        # frame -- including when the host resized between this call and the
        # last one. An auto-resizing window sizes itself in `end()` instead,
        # and must not be overwritten here.
        if window.follows_frame and not window.auto_resize:
            window.box = self.box
        dock_id = pending.pop("dock_id", None)
        if dock_id is not None:
            window.dock_id = int(dock_id)
        self._window_stack.append(window)
        self.current_window = window
        self._child.append((self.layout, self.clip_rect))
        self.clip_rect = window.box
        self.layout = Layout(self.p, *window.box, style=self.layout.style)
        self.p.push_clip(*window.box)
        if not flags & _WF.NO_BACKGROUND:
            # Dear ImGui's window: an opaque background and a border, so what
            # is drawn under a window (a plot, another window) does not show
            # through its contents. NoBackground is the way out.
            bg = self.style.color(Col.WINDOW_BG)
            self.p.fill_rect(*window.box, (*tuple(bg)[:3], 255))
            if self.style.window_border_size > 0.0:
                self.p.stroke_rect(*window.box, self.style.color(Col.BORDER))
        return True

    def end(self) -> None:
        """``ImGui::End``.

        A window marked ``auto_resize`` takes the size of what was submitted
        into it, kept inside whatever ``SetNextWindowSizeConstraints`` asked
        for -- which is the whole of the reference's auto-resizing example.
        """
        if not self._window_stack:
            return
        window = self._window_stack[-1]
        reached = (max(self.layout.content_width(), 1.0),
                   max(self.layout.content_height(), 1.0))
        window.content_size = reached
        if window.auto_resize:
            width, height = reached
            if window.size_min:
                width = max(width, window.size_min[0])
                height = max(height, window.size_min[1])
            if window.size_max:
                width = min(width, window.size_max[0])
                height = min(height, window.size_max[1])
            window.box = (window.box[0], window.box[1], width, height)
        self.p.pop_clip()
        self._window_stack.pop()
        self.layout, self.clip_rect = self._child.pop()
        self.current_window = self._window_stack[-1] if self._window_stack else None

    # -- docking ---------------------------------------------------------- #
    def dock_node(self, dock_id: int):
        """The node with this id, created on first use.

        A dock node is a box that windows share. Several windows in one node
        are tabs of it -- which is what docking *is*, once the dragging is left
        to the host: a place, a list of windows, and one of them on top.
        """
        nodes = self.state(("dock",)).setdefault("nodes", {})
        node = nodes.get(int(dock_id))
        if node is None:
            node = {"id": int(dock_id), "box": self.box, "windows": [],
                    "selected": None, "split": None}
            nodes[int(dock_id)] = node
        return node

    def dock_windows(self, dock_id: int) -> list:
        return self.dock_node(dock_id)["windows"]

    def set_window_focus(self, name: str) -> None:
        """``FocusWindow``: to the end of the list, which is the front."""
        window = next((w for w in self.windows if w.name == name), None)
        if window is not None:
            self.windows.remove(window)
            self.windows.append(window)

    # -- child regions ------------------------------------------------------------- #
    def begin_child(self, box: Rect, clip: bool = True) -> Layout:
        """Lay out inside *box* until :meth:`end_child`; the parent's cursor is
        restored after.

        A non-positive width or height means *fill the available content
        region*, as it does in the reference and as ``implot.begin_plot``
        already does for its size -- and ``-1`` means "all but one pixel".
        The reference's own idiom is ``BeginChild(id, ImVec2(w, 0))`` for a
        column that should run the full height, so reading the zero
        literally gave a child of no height: every panel inside it drew into
        nothing, the call still succeeded, and cmc's main window came out as
        a four-pixel splitter bar with the whole interface missing beside it.
        """
        x, y, w, h = box
        if w <= 0.0 or h <= 0.0:
            avail_w, avail_h = self.layout.avail()
            w = avail_w + w if w <= 0.0 else w
            h = avail_h + h if h <= 0.0 else h
            box = (x, y, max(w, 0.0), max(h, 0.0))
        self._child.append((self.layout, box))
        if clip:
            self.p.push_clip(*box)
        self.layout = Layout(self.p, *box, style=self.layout.style)
        return self.layout

    def end_child(self, clip: bool = True) -> Rect:
        """Close a child and advance the parent past it.

        ``EndChild`` is an *item* in the reference: it calls ``ItemSize`` on
        the parent, so the next thing submitted goes below (or beside, after
        ``SameLine``) the child rather than on top of it. Restoring the
        parent's layout without advancing it left every child starting at
        the same cursor -- cmc's main window drew its device panel, its
        acquisition panel, its statistics and its plots all stacked on the
        same few rows, each overwriting the last.
        """
        layout, box = self._child.pop()
        if clip:
            self.p.pop_clip()
        self.layout = layout
        self.layout.advance(box[2], box[3])
        return box

    # -- popups and tooltips ------------------------------------------------------- #
    def open_popup(self, name: str) -> None:
        self._popups[name] = True

    def is_popup_open(self, name: str) -> bool:
        return bool(self._popups.get(name))

    def close_current_popup(self, name: str) -> None:
        self._popups[name] = False

    def begin_popup(self, name: str) -> bool:
        return self.is_popup_open(name)

    def end_popup(self) -> None:
        pass

    def set_tooltip(self, text: str) -> None:
        self.tooltip = text

    def request_frame(self) -> None:
        """Ask the host for another draw soon (an animation, a held button)."""
        self.frame_requested = True


# --------------------------------------------------------------------------- #
# The current context, and the module-level API a port is written against
# --------------------------------------------------------------------------- #
#
# Dear ImGui code names no context: `ImGui::Button("Save")` reads `GImGui`, a
# file-static pointer to the one context (`imgui.cpp`: `ImGuiContext* GImGui`).
# A port that had to thread `ctx` through every call would not be a port; it
# would be a rewrite with the same words. So this module keeps the same shape:
# one current context, and free functions that read it.
#
#     if im.button("Save"):        # if (ImGui::Button("Save"))
#         save()
#
# The one place Python must differ is the pointer arguments. C++ writes through
# `bool*` and `float*`; here the value comes back, exactly as pyimgui and
# imgui-bundle do it, so a port from either lands unchanged::
#
#     changed, value = im.slider_float("alpha", value, 0.0, 1.0)

_CURRENT: Optional["Context"] = None


def create_context(painter: Painter, box: Rect, **kwargs) -> "Context":
    """A context, made current. ``ImGui::CreateContext``."""
    ctx = Context(painter, box, **kwargs)
    set_current_context(ctx)
    return ctx


def set_current_context(ctx: Optional["Context"]) -> None:
    global _CURRENT
    _CURRENT = ctx


def get_current_context() -> "Context":
    if _CURRENT is None:
        raise RuntimeError(
            "no current im context: call im.create_context(painter, box) or "
            "use `with im.frame(painter, box):`"
        )
    return _CURRENT


@contextmanager
def frame(painter: Painter, box: Rect, io: Optional[IO] = None,
          style: Optional[Style] = None, storage: Optional[dict] = None,
          now: Optional[float] = None):
    """One frame against a fresh context, made current for the block.

    ``ImGui::NewFrame() ... ImGui::Render()`` without the bookkeeping::

        with im.frame(painter, (0, 0, 300, 200)) as ctx:
            im.text("Hello, world!")
    """
    previous = _CURRENT
    ctx = Context(painter, box, io=io, style=style, storage=storage)
    set_current_context(ctx)
    ctx.new_frame(now)
    try:
        yield ctx
    finally:
        ctx.end_frame()
        set_current_context(previous)


def get_io() -> IO:
    return get_current_context().io


def get_style() -> Style:
    return get_current_context().style


def get_window_draw_list() -> DrawList:
    """``ImGui::GetWindowDrawList``."""
    return get_current_context().draw

get_foreground_draw_list = get_window_draw_list
get_background_draw_list = get_window_draw_list


class ImWidget(Control):
    """A ``def widget(ctx, *args, **kw)`` as a retained emtk control.

    Construct with the function and the arguments it should be called with;
    change them through :attr:`args` / :attr:`kwargs`. The result of the last
    call is :attr:`result`. Optional ``on_result(result)`` is called after
    every replay whose result is not ``None``.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, on_result: Optional[Callable[[Any], None]] = None,
                 style: Optional[Style] = None, **kwargs: Any) -> None:
        self.fn = fn
        self.args = list(args)
        self.kwargs = dict(kwargs)
        self.on_result = on_result
        self.io = IO()
        self.style = style if style is not None else Style()
        self.storage: dict = {}
        self.result: Any = None
        self.tooltip: Optional[str] = None
        self.wants_frame = False
        self._painter: Optional[Painter] = None
        self._last_click: tuple[float, int] = (0.0, -1)

    # -- the replay -------------------------------------------------------------- #
    def _replay(self) -> Any:
        if self._painter is None or self._box is None:
            return None
        ctx = Context(self._painter, self._box, io=self.io, style=self.style, storage=self.storage)
        result = self.fn(ctx, *self.args, **self.kwargs)
        self.result = result
        self.tooltip = ctx.tooltip
        self.wants_frame = ctx.frame_requested
        self.io.end_event()
        if result is not None and self.on_result is not None:
            self.on_result(result)
        return result

    # -- Control ------------------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        self.remember(x, y, w, h)
        self._painter = p
        self.io.begin_frame()
        self._replay()

    def _button_index(self, button: int) -> int:
        return 1 if button == RIGHT_BUTTON else 2 if button == MIDDLE_BUTTON else 0

    def press(self, px, py, x, y, w, h, modifiers=0, clicks=1, button=LEFT_BUTTON):
        self.remember(x, y, w, h)
        i = self._button_index(button)
        self.io.mouse_pos = (float(px), float(py))
        self.io.mouse_down[i] = True
        self.io.mouse_clicked[i] = True
        self.io.mouse_double_clicked[i] = clicks >= 2
        self.io.mouse_clicked_pos[i] = (float(px), float(py))
        self._modifiers(modifiers)
        return self._replay()

    def hover(self, px, py) -> Any:
        """Pointer motion with no button held (ImGui sees hover every frame)."""
        self.io.mouse_pos = (float(px), float(py))
        return self._replay()

    def drag(self, px, py, x=None, y=None, w=None, h=None, modifiers=0, button=LEFT_BUTTON):
        self.io.mouse_pos = (float(px), float(py))
        self._modifiers(modifiers)
        return self._replay()

    def release(self, px=None, py=None, x=None, y=None, w=None, h=None, modifiers=0, button=LEFT_BUTTON):
        i = self._button_index(button)
        if px is not None and py is not None:
            self.io.mouse_pos = (float(px), float(py))
        self.io.mouse_down[i] = False
        self.io.mouse_released[i] = True
        self._modifiers(modifiers)
        return self._replay()

    def key(self, key: int, text: str = "", modifiers: int = 0):
        self.io.key = int(key)
        self.io.text = text
        self._modifiers(modifiers)
        return self._replay()

    def scroll(self, px, py, dx: float, dy: float, modifiers: int = 0):
        self.io.mouse_pos = (float(px), float(py))
        self.io.mouse_wheel = float(dy)
        self.io.mouse_wheel_h = float(dx)
        self._modifiers(modifiers)
        return self._replay()

    def leave(self) -> None:
        self.io.mouse_pos = (-1.0, -1.0)

    def _modifiers(self, modifiers: int) -> None:
        from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER

        self.io.key_ctrl = bool(modifiers & CONTROL_MODIFIER)
        self.io.key_shift = bool(modifiers & SHIFT_MODIFIER)
        self.io.key_alt = bool(modifiers & ALT_MODIFIER)
        self.io.key_super = bool(modifiers & META_MODIFIER)



# --------------------------------------------------------------------------- #
# The frame, as free functions
# --------------------------------------------------------------------------- #
def new_frame(now=None) -> None:
    """``ImGui::NewFrame``."""
    get_current_context().new_frame(now)


def end_frame() -> None:
    """``ImGui::EndFrame``."""
    get_current_context().end_frame()


def render() -> None:
    """``ImGui::Render``. emtk draws as it goes, so this ends the frame."""
    get_current_context().end_frame()


def get_frame_count() -> int:
    return get_current_context().io.frame_count


def get_time() -> float:
    """``ImGui::GetTime``: seconds since the context started counting."""
    return get_current_context().io.now


def get_font_size() -> float:
    return get_current_context().p.line_height()


def get_text_line_height() -> float:
    return get_current_context().p.line_height()


def get_text_line_height_with_spacing() -> float:
    ctx = get_current_context()
    return ctx.p.line_height() + ctx.style.item_spacing[1]


def get_frame_height() -> float:
    ctx = get_current_context()
    return ctx.p.line_height() + ctx.style.frame_padding[1] * 2.0


def get_frame_height_with_spacing() -> float:
    return get_frame_height() + get_current_context().style.item_spacing[1]


__all__ += ["new_frame", "end_frame", "render", "get_frame_count", "get_time",
            "get_font_size", "get_text_line_height",
            "get_text_line_height_with_spacing", "get_frame_height",
            "get_frame_height_with_spacing"]
