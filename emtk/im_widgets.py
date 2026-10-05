"""``emtk.im_widgets``: Dear ImGui's widget set, spelled for Python.

The split mirrors the reference: ``imgui.cpp`` is the context, the window stack
and ``ItemAdd``/``ButtonBehavior``; ``imgui_widgets.cpp`` is everything built on
top of them. :mod:`emtk.im` (the facade) re-exports these, so a port reads the way the
original does::

    if im.button("Save"):                       // if (ImGui::Button("Save"))
        save()
    im.same_line()                              // ImGui::SameLine();
    im.text("%d atoms" % n)                     // ImGui::Text("%d atoms", n);
    changed, alpha = im.slider_float(           // ImGui::SliderFloat(
        "alpha", alpha, 0.0, 1.0)               //   "alpha", &alpha, 0.0f, 1.0f);

**The one deliberate difference.** C++ writes results through pointers
(``bool*``, ``float*``, ``char*``); Python has none, so the value comes back
alongside the changed flag -- ``changed, value = im.slider_float(...)``. That is
what pyimgui and imgui-bundle do, so a port from C++ *or* from either Python
binding lands unchanged. Everything else keeps the reference's name, argument
order and return meaning.

Each widget is the same three steps as the original: measure the item and
advance the cursor (``ItemSize``), register the box it is about to draw
(``ItemAdd``), ask ``ButtonBehavior`` what the pointer did to it, and then draw
through the :class:`~emtk.drawlist.DrawList`. Because the box registered
is the box drawn, a widget cannot be clickable where it is not visible.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from .flags import Axis, MouseCursor, SliderFlags
from .im_core import (BackendFlags, ButtonFlags, Col, ConfigFlags,
                      ItemFlags, get_current_context)
from .painter import Colour, colour_bytes, ALIGN_LEFT, ALIGN_VCENTER
from .i18n import tr


def _frame_border(ctx, box) -> None:
    """``RenderFrameBorder``: the outline ``style.frame_border_size`` asks for."""
    size = ctx.style.frame_border_size
    if size > 0.0:
        ctx.draw.add_rect((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                          _col(Col.BORDER), ctx.style.frame_rounding, 0, size)


def _col(which):
    """The style colour, read *now* so ``push_style_color`` reaches it.

    Dimmed inside a ``BeginDisabled`` block, by ``style.disabled_alpha`` --
    the reference does the same with its global alpha, and a disabled control
    that looks exactly like a live one is worse than none.
    """
    ctx = get_current_context()
    colour = ctx.style.color(which)
    if not (ctx.item_flags & ItemFlags.DISABLED):
        return colour
    rgba = tuple(colour) if len(colour) == 4 else (*colour, 255)
    return (*rgba[:3], int(rgba[3] * ctx.style.disabled_alpha))

__all__ = [
    "begin", "end", "begin_child", "end_child",
    "text", "text_colored", "text_disabled", "text_wrapped", "bullet_text",
    "label_text", "math", "math_text", "calc_math_size",
    "button", "small_button", "action_button", "invisible_button", "checkbox",
    "radio_button", "slider_float", "slider_int", "drag_float", "drag_int",
    "progress_bar", "selectable", "combo", "separator", "same_line", "spacing",
    "splitter", "splitter_behavior",
    "dummy", "indent", "unindent", "begin_group", "end_group", "columns",
    "next_column", "new_line", "push_id", "pop_id", "get_id",
    "is_item_hovered", "is_item_active", "is_item_clicked", "get_item_rect",
    "calc_text_size", "set_tooltip", "get_cursor_screen_pos",
    "set_cursor_screen_pos", "collapsing_header", "tree_node", "tree_pop",
    "set_next_item_allow_overlap", "bullet",
]



# --------------------------------------------------------------------------- #
# Windows and layout -- thin passes through to the context
class _BeginResult(int):
    """A boolean result that can also be unpacked as (expanded, opened) for pyimgui compatibility."""

    def __iter__(self):
        yield bool(self)
        yield bool(self)

    def __repr__(self) -> str:
        return str(bool(self))


def begin(name: str, box=None, flags: int = 0, **kwargs) -> _BeginResult:
    """``ImGui::Begin``.

    The reference's second argument is ``bool *p_open`` and emtk's is the
    window's *box* -- emtk windows are placed by the caller, and there is no
    close button to write through. A port therefore drops the ``p_open`` and
    keeps the flags, which is what ``tools/autoport`` rewrites it to.
    """
    res = get_current_context().begin(name, box, flags, **kwargs)
    return _BeginResult(1 if res else 0)


def set_next_window_auto_resize(auto: bool = True) -> None:
    """``ImGuiWindowFlags_AlwaysAutoResize``, as a next-window hint."""
    get_current_context().state(("next_window",))["auto_resize"] = bool(auto)


def end() -> None:
    get_current_context().end()


def begin_child(
    id_or_box: Any,
    size_or_clip: Any = None,
    clip: bool = True,
    child_id: Any = None,
    scrollable: bool = True,
):
    """``ImGui::BeginChild``: Push a scrollable child layout region."""
    ctx = get_current_context()
    if isinstance(id_or_box, str):
        cid = id_or_box
        if isinstance(size_or_clip, (tuple, list)):
            if len(size_or_clip) == 2:
                box = (*ctx.layout.cursor, float(size_or_clip[0]), float(size_or_clip[1]))
            else:
                box = tuple(size_or_clip)
        else:
            avail = ctx.layout.avail()
            box = (*ctx.layout.cursor, avail[0], avail[1])
        c = clip if size_or_clip is None or isinstance(size_or_clip, (tuple, list)) else bool(size_or_clip)
        return ctx.begin_child(box, clip=c, child_id=cid, scrollable=scrollable)
    else:
        box = id_or_box
        c = clip if size_or_clip is None else bool(size_or_clip)
        return ctx.begin_child(box, clip=c, child_id=child_id, scrollable=scrollable)


def end_child(clip: bool = True):
    return get_current_context().end_child(clip=clip)


def same_line(offset: float = 0.0, spacing: float = -1.0) -> None:
    get_current_context().layout.same_line(offset, None if spacing < 0 else spacing)


def new_line() -> None:
    get_current_context().layout.new_line()


def spacing() -> None:
    get_current_context().layout.spacing()


def dummy(w, h: Optional[float] = None):
    """``ImGui::Dummy``: reserve space without drawing in it.

    The reference takes one ``ImVec2``; emtk spells sizes as two scalars.
    Both work here, because a port arrives holding whichever its source had
    -- ``Dummy(ImVec2(w, h))`` and ``Dummy(bb.GetSize())`` are the same call
    in C++, and only the first survives being flattened into two arguments.
    """
    if h is None:
        w, h = w
    return get_current_context().layout.dummy(w, h)


def indent(width: float = 0.0) -> None:
    get_current_context().layout.indent(width or None)


def unindent(width: float = 0.0) -> None:
    get_current_context().layout.unindent(width or None)


def begin_group() -> None:
    """``ImGui::BeginGroup``: measure a run of items as one."""
    get_current_context().layout.begin_group()


def end_group():
    """``ImGui::EndGroup``: close the group and make it *the* last item.

    Returns
    -------
    tuple of float
        The group's bounding box, ``(x, y, w, h)``.

    Notes
    -----
    The second line is the one that matters. `ImGui::EndGroup` writes the
    group's bounding box into ``g.LastItemData``, which is what makes
    ``GetItemRectMin``/``GetItemRectMax``/``IsItemHovered`` describe *the
    group* after it closes -- the whole reason to draw a frame around one.
    emtk recorded it only on the layout, so those three kept answering about
    the last widget inside the group instead, and a caller measuring a group
    got the size of whatever it happened to end with. Nothing raised; the box
    just came out too small.
    """
    ctx = get_current_context()
    box = ctx.layout.end_group()
    ctx._last_item = box
    return box


def columns(count: int = 1, id: str | None = None, border: bool = True) -> None:
    """``ImGui::Columns(count, id, border)``.

    The trailing two are the reference's, and a port passes all three. ``id``
    scopes the stored widths in C++; emtk's layout keys them off the window
    already. ``border`` is the divider, which this layout does not draw.
    Both are accepted so the call resolves -- a TypeError here took the
    whole panel down before its first column.
    """
    del id, border
    get_current_context().layout.columns(count)


def next_column() -> None:
    get_current_context().layout.next_column()


def separator() -> None:
    ctx = get_current_context()
    box = ctx.layout.separator()
    x, y, w, h = box
    ctx.draw.add_line((x, y + h * 0.5), (x + w, y + h * 0.5), _col(Col.TEXT_DISABLED), 1.0)


def _has_alpha(colour) -> bool:
    """Is *colour* something to paint, or the reference's "nothing"?

    ``None``, and the packed ``0`` that C++ writes for a transparent
    ``ImU32``, both mean draw nothing. A tuple means draw it, unless it
    carries an explicit zero alpha.
    """
    if colour is None:
        return False
    if isinstance(colour, int):
        return bool(colour >> 24)        # IM_COL32_A_MASK
    return len(colour) < 4 or colour[3] > 0


def _as_box(box) -> tuple[float, float, float, float]:
    """``(x, y, w, h)`` from either emtk's box or the reference's ``ImRect``.

    emtk spells a rectangle as position-and-size everywhere; Dear ImGui's
    internal signatures -- and ``SplitterBehavior`` is one of them -- take an
    ``ImRect``, which is two corners. A port therefore arrives holding the
    other spelling, and it is one line to accept it rather than make every
    such call site convert. Duck-typed on ``min``/``max`` so emtk needs no
    opinion about whose ``ImRect`` class it is.
    """
    lo = getattr(box, "min", None)
    if lo is not None:
        hi = box.max
        return (float(lo[0]), float(lo[1]),
                float(hi[0]) - float(lo[0]), float(hi[1]) - float(lo[1]))
    x, y, w, h = box
    return (float(x), float(y), float(w), float(h))


def splitter_behavior(box, item_id, axis, size1: float, size2: float,
                      min_size1: float = 0.0, min_size2: float = 0.0,
                      hover_extend: float = 0.0,
                      hover_visibility_delay: float = 0.0,
                      bg_col=None) -> tuple[bool, float, float]:
    """``ImGui::SplitterBehavior``: drag *box* to move space between two panes.

    The *interaction*, with no bar drawn -- :func:`splitter` is the whole
    control. Split out because that is the seam the reference has, and a
    window that draws its own divider (an inset line, a grip, a gradient)
    wants the dragging without the drawing.

    C++ writes the new sizes through ``float *size1, float *size2``; there is
    no such thing here, so they come back:

        changed, left_w, right_w = im.splitter_behavior(
            bar_box, im.get_id("##split"), im.Axis.X,
            left_w, right_w, 120.0, 200.0)

    Parameters
    ----------
    box : tuple of float
        ``(x, y, w, h)`` of the divider, in screen coordinates. The
        reference's two-corner ``ImRect`` is accepted too, since that is
        what its own signature takes and what a port arrives holding.
    item_id
        The interaction id, from :func:`get_id`. Two splitters in one window
        that share an id share their drag.
    axis : int
        :data:`~emtk.flags.Axis.X` for a vertical bar between two columns,
        :data:`~emtk.flags.Axis.Y` for a horizontal one between two rows.
        This is the axis the *sizes* run along, not the bar.
    size1, size2 : float
        The two panes' current sizes along *axis*.
    min_size1, min_size2 : float
        How small each may get. The drag stops rather than swapping them.
    hover_extend : float
        Grow the hit box by this much on each side, along *axis* only. A
        4-pixel divider is hard to hit and easy to overshoot; the reference's
        own docking splitters extend theirs, and so should any bar thin
        enough to look tidy.
    hover_visibility_delay : float
        Seconds the pointer must rest on the bar before :func:`is_item_hovered`
        reports it. Stops a bar between two panes flashing every time the
        pointer crosses it on the way somewhere else. The drag itself is
        never delayed -- a press is a press.
    bg_col
        Fill the hit box with this colour first, as the reference's
        ``bg_col`` does. ``None`` -- or a zero alpha, which is how C++
        spells it -- draws nothing.

    Returns
    -------
    tuple
        ``(changed, size1, size2)``. *changed* is true on the frames the
        drag actually moved the boundary, so a caller can save its layout
        without writing a settings file sixty times a second.

    Notes
    -----
    The delta is measured from where in the bar the press landed, and applied
    to the *current* box each frame -- so a caller that re-lays-out from the
    returned sizes tracks the pointer exactly, with no drift and no need to
    remember anything itself.
    """
    ctx = get_current_context()
    a = 1 if axis == 1 else 0
    x, y, w, h = _as_box(box)
    if hover_extend:
        if a == 0:
            x, w = x - hover_extend, w + hover_extend * 2.0
        else:
            y, h = y - hover_extend, h + hover_extend * 2.0
    interact = (x, y, w, h)
    # The reference draws the fill only `if (bg_col & IM_COL32_A_MASK)` -- a
    # zero alpha means no fill, and its callers spell "none" as the literal
    # `0`. So does a port of one, which is why this tests the alpha rather
    # than `is not None`: given `0` it would otherwise try to paint with an
    # integer and fail inside the draw list, three frames from the call.
    if _has_alpha(bg_col):
        ctx.draw.add_rect_filled((x, y), (x + w, y + h), bg_col)

    hovered, held, _pressed = ctx.button_behavior(
        interact, item_id, ButtonFlags.ALLOW_OVERLAP)

    store = ctx.get_storage(item_id)
    if hovered and hover_visibility_delay > 0.0 and not held:
        store["hover_t"] = store.get("hover_t", 0.0) + ctx.io.delta_time
        if store["hover_t"] < hover_visibility_delay:
            hovered = False
    elif not hovered:
        store.pop("hover_t", None)

    if hovered or held:
        set_mouse_cursor(MouseCursor.RESIZE_EW if a == 0 else MouseCursor.RESIZE_NS)
    # What the bar should *look* like, which is not what `is_item_hovered`
    # says: that is the raw hit, and it is deliberately not delayed. Kept
    # here so :func:`splitter` draws the state this function decided on --
    # reading the raw hit instead made `hover_visibility_delay` change the
    # cursor and not the colour, which is half a feature.
    store["hovered"] = bool(hovered)
    store["held"] = bool(held)

    changed = False
    if held:
        # Where in the bar the press landed. Kept, so the boundary follows
        # the point the pointer grabbed rather than jumping it to the centre.
        if "click_offset" not in store:
            store["click_offset"] = ctx.io.mouse_pos[a] - interact[a]
        delta = ctx.io.mouse_pos[a] - store["click_offset"] - interact[a]
        # Clamp before applying, not after: clamping the *sizes* afterwards
        # lets the pointer run far past the limit and the bar then lags all
        # the way back on the return journey.
        delta = max(delta, min_size1 - size1)
        delta = min(delta, size2 - min_size2)
        if delta != 0.0:
            size1 += delta
            size2 -= delta
            changed = True
    else:
        store.pop("click_offset", None)
    return (changed, float(size1), float(size2))


def splitter(str_id: str, axis, thickness: float, long_axis_size: float,
             size1: float, size2: float, min_size1: float = 0.0,
             min_size2: float = 0.0, hover_extend: float = 8.0,
             bar_margin: float = 4.0,
             hover_visibility_delay: float = 0.0) -> tuple[bool, float, float]:
    """A draggable divider between two panes: behaviour, cursor, bar, layout.

    Placed at the cursor, like any other item, and it reserves its own space
    -- so the pane after it starts where the bar ends instead of underneath
    it. Between two children that is::

        im.begin_child((*im.get_cursor_screen_pos(), left_w, 0))
        ...
        im.end_child()
        im.same_line(0.0, 0.0)
        moved, left_w, right_w = im.splitter(
            "##vsplit", im.Axis.X, 12.0, full_h, left_w, right_w, 260.0, 360.0)
        im.same_line(0.0, 0.0)
        im.begin_child((*im.get_cursor_screen_pos(), right_w, 0))

    Parameters
    ----------
    str_id : str
        Label-style id for the drag; never drawn.
    axis : int
        :data:`~emtk.flags.Axis.X` for a vertical bar (side-by-side panes),
        :data:`~emtk.flags.Axis.Y` for a horizontal one (stacked panes).
    thickness : float
        The space the divider occupies -- the *hit* target and the layout
        cost, not the visible line.
    long_axis_size : float
        How far it runs across the panes it divides.
    size1, size2, min_size1, min_size2, hover_extend, hover_visibility_delay
        As :func:`splitter_behavior`. The delay gates the bar's colour and
        the cursor, never the drag.
    bar_margin : float
        Inset the drawn bar by this much on each side, so a comfortable
        grab target does not look like a slab. The line is never thinner
        than two pixels however wide the margin asks to be.

    Returns
    -------
    tuple
        ``(changed, size1, size2)``.

    Notes
    -----
    A splitter is what every application with two resizable panes writes for
    itself, and it is not a natural thing to get right: the hit box wants to
    be bigger than the bar, the cursor has to change, the delta has to be
    taken from the grab point, and both minimums have to hold at once. cmc
    had four copies of it in four files.
    """
    ctx = get_current_context()
    a = 1 if axis == 1 else 0
    x, y = ctx.layout.cursor
    box = ((x, y, thickness, long_axis_size) if a == 0
           else (x, y, long_axis_size, thickness))
    item_id = ctx.get_id(str_id)
    changed, size1, size2 = splitter_behavior(
        box, item_id, a, size1, size2, min_size1, min_size2,
        hover_extend, hover_visibility_delay)
    state = ctx.get_storage(item_id)
    held = state.get("held", False)
    hovered = state.get("hovered", False)
    # Reserve the space *after* the behaviour: the hit box may be wider than
    # the bar, but what the layout owes the next item is the bar's own room.
    ctx.layout.dummy(box[2], box[3])

    bar = max(2.0, thickness - bar_margin * 2.0)
    inset = (thickness - bar) * 0.5
    bx, by, bw, bh = box
    if a == 0:
        bx, bw = bx + inset, bar
    else:
        by, bh = by + inset, bar
    colour = (_col(Col.SEPARATOR_ACTIVE) if held
              else _col(Col.SEPARATOR_HOVERED) if hovered
              else _col(Col.SEPARATOR))
    ctx.draw.add_rect_filled((bx, by), (bx + bw, by + bh), colour)
    return (changed, size1, size2)


def push_id(key: Any) -> None:
    get_current_context().push_id(key)


def pop_id() -> None:
    get_current_context().pop_id()


def get_id(label: str):
    return get_current_context().get_id(label)


def set_next_item_allow_overlap() -> None:
    get_current_context().set_next_item_allow_overlap()


def is_item_hovered(allow_when_disabled: bool = False) -> bool:
    """``IsItemHovered``; a disabled item only with *allow_when_disabled*."""
    return get_current_context().is_item_hovered(allow_when_disabled)


def is_item_active() -> bool:
    return get_current_context().is_item_active()


def is_item_clicked(button: int = 0) -> bool:
    return get_current_context().is_item_clicked(button)


def get_item_rect():
    return get_current_context().get_item_rect()


def calc_text_size(text_: str, text_end=None, hide_double_hash: bool = False,
                   wrap_width: float = -1.0):
    """Measure multiline text, optionally wrapping to a positive width."""
    if text_end is not None:
        try:
            text_ = text_[:int(text_end)]
        except (TypeError, ValueError):
            pass
    if hide_double_hash and "##" in text_:
        text_ = text_.split("##", 1)[0]
    ctx = get_current_context()
    lines = (_wrapped_lines(ctx, text_, float(wrap_width)) if wrap_width > 0
             else str(text_).split("\n"))
    return (max((ctx.p.text_width(line) for line in lines), default=0.0),
            ctx.p.line_height() * len(lines))


def set_tooltip(text_: str) -> None:
    get_current_context().set_tooltip(tr(text_))


def get_cursor_screen_pos():
    return get_current_context().layout.cursor


def set_cursor_screen_pos(pos) -> None:
    """``ImGui::SetCursorScreenPos``: move the cursor, and nothing else.

    Parameters
    ----------
    pos : tuple
        ``(x, y)`` in screen space.

    Notes
    -----
    This used to call :meth:`Layout.reset`, which is the *frame* reset: it puts
    the cursor back **and** throws away the extents laid out so far. The
    reference does neither -- ``SetCursorScreenPos`` writes
    ``window->DC.CursorPos`` and leaves ``CurrLineSize`` and the group stack
    alone.

    The difference is invisible until something measures a group that contains
    a cursor move. Then the group's bounding box starts at the move rather than
    at the group, so it comes back too small -- and a caller drawing a frame
    around that box draws a frame around the tail of its own content. That is
    how a node whose title bar repositions the cursor for its body ended up
    narrower than its own title.
    """
    get_current_context().layout.move_cursor_to(pos[0], pos[1])


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def _line(ctx, height: Optional[float] = None):
    return ctx.layout.row(height=height)


def text(s: str) -> None:
    """``ImGui::Text``. Formatting is Python's, so ``im.text(f"...")``."""
    text_colored(_col(Col.TEXT), s)


def _active_wrap_width(ctx, box_x: float) -> float | None:
    """The wrap width :func:`push_text_wrap_pos` set, or ``None`` for no wrap.

    ``0.0`` wraps at the remaining content width (the window edge, ImGui's
    default when pushed bare); a positive value is a window-relative x; a
    negative value disables wrapping for the text below it.
    """
    stack = ctx.state(("wrap",)).get("stack") or []
    if not stack:
        return None
    wrap = float(stack[-1])
    if wrap < 0.0:
        return None
    if wrap == 0.0:
        return max(1.0, ctx.layout.avail()[0])
    return max(1.0, wrap - box_x)


def text_colored(col, s: str) -> None:
    """``ImGui::TextColored``.

    The item is the size of the **text**, not of the line. `ImGui::TextEx`
    calls ``ItemSize(text_size)``, and the difference is not cosmetic: a
    full-width text item covers everything a following ``SameLine`` puts beside
    it, claims the pointer first (``ItemHoverable`` gives it to whoever asks
    first), and the widget next to it goes dead. The demo's
    ``Text("Hold to repeat:"); SameLine(); ArrowButton(...)`` is exactly that
    shape, and the arrows did not respond.

    Honours :func:`push_text_wrap_pos`: with a wrap width active the text
    wraps like ``TextWrapped`` (muted captions and disabled text included),
    because that is what the reference does.
    """
    if isinstance(col, str) and not isinstance(s, str):
        col, s = s, col
    col = colour_bytes(col)
    ctx = get_current_context()
    lines = [tr(line) for line in str(s).split("\n")]
    wrap_width = _active_wrap_width(ctx, ctx.layout.cursor[0])
    if wrap_width is not None:
        lines = [wrapped for line in lines for wrapped in _wrapped_lines(ctx, line, wrap_width)]
    width = max((ctx.p.text_width(line) for line in lines), default=0.0)
    height = ctx.p.line_height() * len(lines)
    box = ctx.layout.row(height=max(height, ctx.p.line_height()), width=width)
    ctx.item_add(box)
    for index, line in enumerate(lines):
        ctx.draw.add_text((box[0], box[1] + index * ctx.p.line_height()), col, line)


def text_disabled(s: str) -> None:
    text_colored(_col(Col.TEXT_DISABLED), s)


def _wrapped_lines(ctx, s, width):
    """The shared wrapping rules for text measurement and drawing."""
    lines = []
    for paragraph in str(s).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip() if line else word
            if line and ctx.p.text_width(candidate) > width:
                lines.append(line)
                line = ""
            if ctx.p.text_width(word) > width:
                for character in word:
                    if line and ctx.p.text_width(line + character) > width:
                        lines.append(line)
                        line = ""
                    line += character
            else:
                line = f"{line} {word}".strip() if line else word
        if line:
            lines.append(line)
    return lines


def text_wrapped(s: str) -> None:
    """Draw one measured text block, wrapping to the remaining content width."""
    ctx = get_current_context()
    source = "\n".join(tr(line) for line in str(s).split("\n"))
    lines = _wrapped_lines(ctx, source, max(1.0, ctx.layout.avail()[0]))
    width = max((ctx.p.text_width(line) for line in lines), default=0.0)
    box = ctx.layout.row(height=len(lines) * ctx.p.line_height(), width=width)
    ctx.item_add(box)
    for index, line in enumerate(lines):
        ctx.draw.add_text((box[0], box[1] + index * ctx.p.line_height()), _col(Col.TEXT), line)



def bullet() -> None:
    ctx = get_current_context()
    box = ctx.layout.row(width=ctx.draw.calc_text_size("M")[0])
    cx = box[0] + box[2] * 0.5
    cy = box[1] + box[3] * 0.5
    ctx.draw.add_circle_filled((cx, cy), max(box[3] * 0.12, 1.5), _col(Col.TEXT))
    ctx.layout.same_line()


def bullet_text(s: str) -> None:
    bullet()
    text(s)


def label_text(label: str, s: str) -> None:
    """``ImGui::LabelText``: value on the left, label on the right."""
    ctx = get_current_context()
    box = _line(ctx)
    ctx.item_add(box)
    ctx.draw.add_text((box[0], box[1]), _col(Col.TEXT), str(s))
    width = ctx.draw.calc_text_size(label)[0]
    ctx.draw.add_text((box[0] + box[2] - width, box[1]), _col(Col.TEXT_DISABLED), label)


def math(
    formula: str,
    font_size: float = 14.0,
    colour: Optional[Any] = None,
    scale: float = 0.5,
    align_center: bool = False,
    max_width: Optional[float] = None,
) -> tuple[float, float]:
    """Render a LaTeX mathematical expression into the current layout.

    Uses matplotlib's mathtext parser when available to produce crisp,
    antialiased, transparent math textures cached on the GPU/painter,
    with automatic fallback to Unicode symbols.

    Parameters
    ----------
    formula : str
        LaTeX mathematical formula, e.g. ``r"\\frac{a}{b}"`` or ``"E = mc^2"``.
    font_size : float
        Nominal font size in points.
    colour : tuple or str, optional
        Foreground colour. If omitted, uses ``Col.TEXT``.
    scale : float
        Rendering display scale factor (default 0.5 for retina oversampling).
    align_center : bool
        If True, horizontally centers the formula in the available content region.
    max_width : float, optional
        Maximum width to constrain the formula to. If rendered width exceeds this
        (or the available layout width), the formula is proportionally scaled down.

    Returns
    -------
    tuple[float, float]
        The (width, height) of the rendered item in points/pixels.
    """
    ctx = get_current_context()
    if colour is None:
        draw_colour = _col(Col.TEXT)
    else:
        from .mathtext import _color_to_rgba_tuple
        draw_colour = _color_to_rgba_tuple(colour)

    avail_w = max(0.0, ctx.layout.w - ctx.layout.indent_x)
    limit_w = float(max_width) if max_width is not None and max_width > 0 else (avail_w if avail_w > 20.0 else float("inf"))

    from .mathtext import render_math_to_texture, latex_to_unicode

    tex = render_math_to_texture(formula, colour=draw_colour, font_size=font_size)
    if tex is not None:
        width = tex.width * scale
        height = tex.height * scale
        if width > limit_w:
            ratio = limit_w / width
            width = limit_w
            height = height * ratio

        pad = (avail_w - width) * 0.5 if (align_center and avail_w > width) else 0.0
        row_w = None if align_center else width
        box = ctx.layout.row(height=height, width=row_w)
        ctx.item_add(box)
        x0 = box[0] + pad
        ctx.draw.add_image(tex, (x0, box[1]), (x0 + width, box[1] + height))
        return (width, height)

    # Fallback to Unicode formatted text
    u_text = latex_to_unicode(formula)
    w, h = ctx.draw.calc_text_size(u_text)
    pad = (avail_w - w) * 0.5 if (align_center and avail_w > w) else 0.0
    row_w = None if align_center else w
    box = ctx.layout.row(height=max(h, ctx.p.line_height()), width=row_w)
    ctx.item_add(box)
    x0 = box[0] + pad
    ctx.draw.add_text((x0, box[1]), draw_colour, u_text)
    return (w, max(h, ctx.p.line_height()))



math_text = math


def calc_math_size(
    formula: str,
    font_size: float = 14.0,
    scale: float = 0.5,
) -> tuple[float, float]:
    """Calculate the layout bounds of a LaTeX formula without drawing it."""
    from .mathtext import calc_math_size as _calc
    return _calc(formula, font_size=font_size, scale=scale)


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
def _frame_height(ctx) -> float:
    return ctx.p.line_height() + ctx.style.frame_padding[1] * 2.0


def _calc_item_size(size, default_w, default_h) -> tuple[float, float]:
    """``CalcItemSize``: a zero component means "the default".

        if (size.x == 0.0f) size.x = default_w;

    `ImVec2(120, 0)` is the demo's ordinary way of saying "this wide, normal
    height" -- taken literally it makes a button zero pixels tall, which draws
    nothing and cannot be clicked. The demo's modal OK button is exactly that.
    """
    if size is None:
        return (float(default_w), float(default_h))
    width = float(size[0]) or float(default_w)
    height = float(size[1]) or float(default_h)
    return (width, height)


def _visible_label(label: str) -> str:
    """``"Save##id"`` shows "Save"; ``"##id"`` shows nothing."""
    return tr(label.split("##", 1)[0])


def _labelled_item_width(ctx, wanted, label_width):
    """Keep filling fields and their captions inside the available row."""
    if wanted is None:
        return None
    available = ctx.layout.avail()[0]
    if wanted < 0:
        return max(1.0, available + wanted)
    return min(wanted + label_width, available) if label_width else wanted


def button(label: str, size=None) -> bool:
    """``ImGui::Button``: True on the frame the click completes."""
    ctx = get_current_context()
    shown = _visible_label(label)
    width, height = _calc_item_size(
        size,
        ctx.draw.calc_text_size(shown)[0] + ctx.style.frame_padding[0] * 2.0,
        _frame_height(ctx))
    box = ctx.layout.row(height=height, width=width)
    hovered, held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    colour = _col(Col.BUTTON_ACTIVE) if held else (_col(Col.BUTTON_HOVERED) if hovered else _col(Col.BUTTON))
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             colour, ctx.style.frame_rounding)
    _frame_border(ctx, box)
    if shown:
        tw, th = ctx.draw.calc_text_size(shown)
        ctx.draw.add_text((box[0] + (box[2] - tw) * 0.5,
                           box[1] + (box[3] - th) * 0.5), _col(Col.TEXT), shown)
    return pressed


def small_button(label: str) -> bool:
    ctx = get_current_context()
    shown = _visible_label(label)
    width = ctx.draw.calc_text_size(shown)[0] + ctx.style.frame_padding[0]
    return button(label, (width, ctx.p.line_height()))


def action_button(label: str, tooltip: str, callback, accent: bool = False) -> bool:
    """A button that carries its tooltip and fires *callback* when pressed.

    The shape every tool window reaches for: a labelled button that explains
    itself on hover and runs an action when clicked, with the optional accent
    style for the one headline action a panel leads with. Returns whether the
    click completed, so a caller can chain a same-line sibling after it.
    """
    if accent:
        from .im_core import Col  # noqa: PLC0415

        push_style_color(Col.BUTTON, ACCENT_GREEN_BUTTON)
        push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
    pressed = button(label)
    if accent:
        pop_style_color(3)
    set_item_tooltip(tooltip)
    if pressed and callback is not None:
        callback()
    return pressed


#: The green every tool's headline action uses, so the accent reads as one voice.
ACCENT_GREEN_BUTTON = (46, 160, 67, 255)


def invisible_button(label: str, size) -> bool:
    """``ImGui::InvisibleButton``: behaviour without paint.

    The one widget that is *meant* to be clickable without drawing -- and it
    still registers the box it occupies, so the pointer rules are the same.
    """
    ctx = get_current_context()
    width, height = _calc_item_size(size, _frame_height(ctx), _frame_height(ctx))
    box = ctx.layout.row(height=height, width=width)
    _hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    return pressed


def checkbox(label: str, value: bool) -> tuple[bool, bool]:
    """``ImGui::Checkbox``. Returns ``(changed, value)``."""
    ctx = get_current_context()
    height = _frame_height(ctx)
    shown = _visible_label(label)
    width = height + ctx.style.item_inner_spacing[0] + ctx.draw.calc_text_size(shown)[0]
    box = ctx.layout.row(height=height, width=width)
    hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    mark = (box[0], box[1], height, height)
    ctx.draw.add_rect_filled((mark[0], mark[1]), (mark[0] + height, mark[1] + height),
                             _col(Col.BUTTON_HOVERED) if hovered else _col(Col.FRAME_BG),
                             ctx.style.frame_rounding)
    _frame_border(ctx, mark)
    if value:
        pad = height * 0.28
        ctx.draw.add_line((mark[0] + pad, mark[1] + height * 0.5),
                          (mark[0] + height * 0.45, mark[1] + height - pad), _col(Col.CHECK_MARK), 2.0)
        ctx.draw.add_line((mark[0] + height * 0.45, mark[1] + height - pad),
                          (mark[0] + height - pad, mark[1] + pad), _col(Col.CHECK_MARK), 2.0)
    if shown:
        ctx.draw.add_text((mark[0] + height + ctx.style.item_inner_spacing[0], box[1] + ctx.style.frame_padding[1]),
                          _col(Col.TEXT), shown)
    return (pressed, (not value) if pressed else value)


def radio_button(label: str, active, value=None):
    """``ImGui::RadioButton``, both overloads.

    C++ has two: ``RadioButton(label, bool active)`` returning whether it was
    clicked, and ``RadioButton(label, int* v, int v_button)`` which selects.
    Python cannot overload on a pointer, so the second is the three-argument
    call and returns ``(changed, v)`` -- the same shape every other
    pointer-taking widget has here. The *name* stays the reference's, so
    ``ImGui::RadioButton`` -> ``im.radio_button`` needs no thought.
    """
    if value is not None:
        if radio_button(label, active == value):
            return (True, value)
        return (False, active)
    ctx = get_current_context()
    height = _frame_height(ctx)
    shown = _visible_label(label)
    width = height + ctx.style.item_inner_spacing[0] + ctx.draw.calc_text_size(shown)[0]
    box = ctx.layout.row(height=height, width=width)
    hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    centre = (box[0] + height * 0.5, box[1] + height * 0.5)
    ctx.draw.add_circle_filled(centre, height * 0.42,
                               _col(Col.BUTTON_HOVERED) if hovered else _col(Col.FRAME_BG))
    if active:
        ctx.draw.add_circle_filled(centre, height * 0.22, _col(Col.CHECK_MARK))
    if shown:
        ctx.draw.add_text((box[0] + height + ctx.style.item_inner_spacing[0], box[1]),
                          _col(Col.TEXT), shown)
    return pressed


# --------------------------------------------------------------------------- #
# Sliders and drags
# --------------------------------------------------------------------------- #
def _log_epsilon(fmt: str, integral: bool) -> float:
    """How near zero a logarithmic slider's bounds may be taken.

    The same derivation :attr:`emtk.widgets.sliders.SliderScalar.log_epsilon`
    makes: whole numbers can always take a bound of ``1``, anything else takes
    the bound its own format could still *display* -- a ``%.2f`` slider cannot
    hold ``0.001``, so ``0.01`` is near enough to zero to be the fudge.
    """
    from .widgets.sliders import parse_precision  # noqa: PLC0415

    if integral:
        return 1.0
    precision = parse_precision(fmt, 3)
    return pow(0.1, float(precision if precision >= 0 else 3))


def _slider_text_edit(ctx, track, item_id, value: float, v_lo: float, v_hi: float,
                      fmt: str, integral: bool, always_clamp: bool,
                      no_input: bool):
    """The Ctrl+Click (or double-click) type-in, the reference's slider text editing.

    A double click opens the field as well: Ctrl+Click is the reference's
    gesture and nothing on screen says so, while a double click is what a
    person tries on a number they want to type.

    Returns ``(changed, value, editing)``. *editing* is true from the
    Ctrl+Click that opens the field until the edit ends; while it is open the
    caller draws the typed text instead of the value and leaves its model
    alone. The edit *commits* on Enter or on a click anywhere else, and the
    commit frame is the only one that reports a change -- one edit, one
    handler run, the contract every other field here keeps. Escape cancels
    back to the value the field was opened with. Without ``ALWAYS_CLAMP`` a
    committed value may sit outside the bounds (the grab pins at the end
    until a drag brings it back), with it the commit is clamped, as the
    reference's flag does. ``NO_INPUT`` refuses to open at all.
    """
    from .keys import KEY_ESCAPE  # noqa: PLC0415
    from .widgets.text_field import TextField  # noqa: PLC0415

    io = ctx.io
    st = ctx.state(("slider_text_edit", item_id))

    from .im_core import ItemFlags  # noqa: PLC0415

    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    ctrl_click = (not disabled and not no_input and io.mouse_clicked[0]
                  and (io.key_ctrl or io.mouse_double_clicked[0])
                  and track[0] <= io.mouse_pos[0] <= track[0] + track[2]
                  and track[1] <= io.mouse_pos[1] <= track[1] + track[3])
    if ctrl_click and not st.get("open"):
        field = st["field"] = TextField()
        field.set_text(fmt % value)
        field.select_all()
        st["open"] = True
        ctx._want_text_input = True
        return (False, value, True)

    if not st.get("open"):
        return (False, value, False)

    ctx._want_text_input = True
    field = st["field"]
    clicked_elsewhere = io.mouse_clicked[0] and not io.key_ctrl
    commit = clicked_elsewhere
    cancel = False
    events = list(io.key_events)
    if not events and (io.key or io.text):
        events = [(io.key, io.text, _current_modifiers(io))]
    for key, text, mods in events:
        if key in _ENTER_KEYS:
            commit = True
        elif key == KEY_ESCAPE:
            cancel = True
        elif key or text:
            field.key(key, "".join(c for c in text if c in "-+.eE0123456789"), mods)

    if cancel:
        st.pop("open", None)
        return (False, value, False)

    if not commit:
        return (False, value, True)

    st.pop("open", None)
    try:
        new = float(field.text)
    except ValueError:
        return (False, value, False)    # unparseable text: keep the old value
    if integral:
        new = int(round(new))
    if always_clamp:
        new = max(v_lo, min(v_hi, new))
    return (new != value, new, False)


def _slider(label, value, v_min, v_max, fmt, integral: bool, flags: int = 0):
    ctx = get_current_context()
    height = _frame_height(ctx)
    shown = _visible_label(label) if isinstance(label, str) else ""
    label_w = (ctx.draw.calc_text_size(shown)[0] + ctx.style.item_inner_spacing[0]
               if shown else 0.0)
    # `SetNextItemWidth` sizes the *widget*, and the label sits outside it --
    # so the row is that much wider, and the track ends up exactly as asked.
    # Without this the call was silently ignored by every slider and drag,
    # which is most of what anyone sets a width on.
    wanted = ctx.take_next_item_width()
    box = ctx.layout.row(height=height,
                         width=_labelled_item_width(ctx, wanted, label_w))
    track = (box[0], box[1], max(box[2] - label_w, 1.0), box[3])
    item_id = ctx.get_id(label)

    from .widgets.sliders import (  # noqa: PLC0415
        LOG_SLIDER_DEADZONE, GRAB_PADDING, ratio_from_value, round_to_format,
        value_from_ratio,
    )

    logarithmic = bool(flags & SliderFlags.LOGARITHMIC)
    no_round = bool(flags & SliderFlags.NO_ROUND_TO_FORMAT)
    always_clamp = bool(flags & SliderFlags.ALWAYS_CLAMP)
    no_input = bool(flags & SliderFlags.NO_INPUT)
    epsilon = _log_epsilon(fmt, integral) if logarithmic else 0.0
    lo, hi = float(v_min), float(v_max)
    value = float(value)

    # The dead-zone is what keeps exactly zero reachable on a log track whose
    # range crosses it; it is a fraction of the *usable* track, and the usable
    # track is the box less one grab, so the grab's width is wanted first.
    grab_w = max(ctx.style.grab_min_size, track[2] * 0.06)
    usable_px = max(track[2] - grab_w - 2.0 * GRAB_PADDING, 1.0)
    deadzone = ((LOG_SLIDER_DEADZONE * 0.5) / usable_px) if logarithmic else 0.0

    changed = False
    hovered = held = False
    edit_changed, new_value, editing = _slider_text_edit(
        ctx, track, item_id, value, lo, hi, fmt, integral, always_clamp, no_input)
    if editing:
        pass
    elif edit_changed:
        # A committed type-in may leave the bounds on purpose (that is what
        # life without ALWAYS_CLAMP means); the grab is drawn pinned at the
        # end, because the scale clamps whatever it is asked about.
        value = new_value
        changed = True
    else:
        hovered, held, _pressed = ctx.button_behavior(track, item_id)
        if held:
            t = (ctx.io.mouse_pos[0] - track[0]) / max(track[2], 1.0)
            raw = value_from_ratio(t, lo, hi, epsilon, deadzone, integral)
            if not integral and not no_round:
                raw = round_to_format(fmt, raw)
            value = raw
            changed = True

    value = int(value) if integral else float(value)
    if not (edit_changed or held):
        # Idle: the slider answers with the value in range, as it always did
        # and the reference's demo relies on. A commit frame keeps the typed
        # value as it was (that is what life without ALWAYS_CLAMP means), and
        # the next idle frame pulls it back in; the grab is drawn pinned at
        # the end either way, because the scale clamps what it is asked about.
        value = max(lo, min(hi, value))
    fraction = ratio_from_value(value, lo, hi, epsilon, deadzone)
    grab_x = track[0] + fraction * max(track[2] - grab_w, 0.0)
    ctx.draw.add_rect_filled((track[0], track[1]), (track[0] + track[2], track[1] + track[3]),
                             _col(Col.FRAME_BG_ACTIVE) if editing
                             else (_col(Col.BUTTON_HOVERED) if hovered else _col(Col.FRAME_BG)),
                             ctx.style.frame_rounding)
    ctx.draw.add_rect_filled((grab_x, track[1]), (grab_x + grab_w, track[1] + track[3]),
                             _col(Col.SLIDER_GRAB_ACTIVE) if held else _col(Col.SLIDER_GRAB),
                             ctx.style.grab_rounding)

    ctx.draw.push_clip_rect((track[0], track[1]),
                            (track[0] + track[2], track[1] + track[3]))
    if editing:
        field = ctx.state(("slider_text_edit", item_id))["field"]
        shown_value = field.text
        pad = ctx.style.frame_padding[0]
        tw = ctx.draw.calc_text_size(shown_value)[0]
        origin = track[0] + pad - max(tw - (track[2] - 2.0 * pad), 0.0)
        ctx.draw.add_text((origin, track[1] + ctx.style.frame_padding[1]),
                          _col(Col.TEXT), shown_value)
        caret = origin + ctx.draw.calc_text_size(shown_value[:field.cursor])[0]
        ctx.draw.add_line((caret, track[1] + 2.0), (caret, track[1] + track[3] - 2.0),
                          _col(Col.TEXT), 1.0)
    else:
        shown_value = fmt % value
        tw, th = ctx.draw.calc_text_size(shown_value)
        ctx.draw.add_text((track[0] + (track[2] - tw) * 0.5,
                           track[1] + (track[3] - th) * 0.5), _col(Col.TEXT), shown_value)
    ctx.draw.pop_clip_rect()
    if shown:
        ctx.draw.add_text((track[0] + track[2] + ctx.style.item_inner_spacing[0], box[1]),
                          _col(Col.TEXT), shown)
    # `held` keeps the old contract -- true on every frame the pointer is
    # actively working the control -- for callers that treat "released" as
    # "finished"; `changed` says the value actually moved.
    return (bool(changed or held), value)


def slider_float(label: str, v: float, v_min: float, v_max: float,
                 fmt: str = "%.3f", flags: int = 0) -> tuple[bool, float]:
    """``ImGui::SliderFloat``: the track, the grab, and the value on it.

    Drag to set; the change is reported on every frame the pointer moves the
    grab (live), as the reference's sliders do. Ctrl+Click opens a text field
    over the track — the reference's slider text editing — which reports one
    change on Enter or on a click elsewhere, and cancels on Escape.

    *flags* takes the reference's ``ImGuiSliderFlags`` bits emtk implements:
    ``LOGARITHMIC`` (the track interpolates in log space, per
    :func:`emtk.widgets.sliders.value_from_ratio`, with the reference's
    dead-zone keeping exactly zero reachable across a sign change),
    ``NO_ROUND_TO_FORMAT`` (store the drag's full precision rather than what
    the format shows), ``ALWAYS_CLAMP`` (a Ctrl+Click commit is clamped to the
    bounds) and ``NO_INPUT`` (no Ctrl+Click field). The remaining bits are
    accepted and ignored.

    A drag's stored value passes through :func:`emtk.widgets.sliders.
    round_to_format`, so a ``%.2f`` slider stores ``0.25`` rather than
    ``0.2500000037`` — what the user sees and what the model carries are the
    same number, and typing the number back changes nothing.
    """
    return _slider(label, float(v), float(v_min), float(v_max), fmt,
                   integral=False, flags=flags)


def slider_int(label: str, v: int, v_min: int, v_max: int,
               fmt: str = "%d", flags: int = 0) -> tuple[bool, int]:
    """``ImGui::SliderInt``: the whole-number slider.

    The integer value is exact at both ends and never carries a fraction;
    otherwise the float slider's behaviour, Ctrl+Click type-in included.
    """
    changed, value = _slider(label, float(v), float(v_min), float(v_max), fmt,
                             integral=True, flags=flags)
    return (changed, int(round(value)))


def _drag(label, value, speed, v_min, v_max, fmt, integral: bool):
    ctx = get_current_context()
    height = _frame_height(ctx)
    shown = _visible_label(label) if isinstance(label, str) else ""
    label_w = (ctx.draw.calc_text_size(shown)[0] + ctx.style.item_inner_spacing[0]
               if shown else 0.0)
    # `SetNextItemWidth` sizes the *widget*, and the label sits outside it --
    # the same contract the sliders honour (see `_slider`): without the
    # reservation the row is the widget alone and the label never fits.
    wanted = ctx.take_next_item_width()
    box = ctx.layout.row(height=height,
                         width=_labelled_item_width(ctx, wanted, label_w))
    field = (box[0], box[1], max(box[2] - label_w, 1.0), box[3])
    item_id = ctx.get_id(label)
    hovered, held, _pressed = ctx.button_behavior(field, item_id)
    store = ctx.get_storage(item_id)
    if held:
        last = store.get("x", ctx.io.mouse_pos[0])
        value = value + (ctx.io.mouse_pos[0] - last) * speed
        store["x"] = ctx.io.mouse_pos[0]
    else:
        store.pop("x", None)
    if v_min is not None:
        value = max(v_min, value)
    if v_max is not None:
        value = min(v_max, value)
    if integral:
        value = int(round(value))
    # `ImGuiItemFlags_LiveEditOnInput*`: with it a drag reports every step;
    # without it, only the one that finishes it -- which is what an expensive
    # recompute wants. "Finishes it" is deactivation, not release: on the
    # release frame the item is already inactive, so asking `held` there
    # reports nothing at all.
    live = bool(ctx.item_flags & (ItemFlags.LIVE_EDIT_ON_INPUT
                                  | ItemFlags.LIVE_EDIT_ON_INPUT_SCALAR))
    if not live:
        if held:
            store["edited"] = True
            held = False
        elif (ctx.active_id_previous_frame == item_id
              and ctx.active_id != item_id and store.pop("edited", False)):
            held = True
    ctx.draw.add_rect_filled((field[0], field[1]), (field[0] + field[2], field[1] + field[3]),
                             _col(Col.BUTTON_HOVERED) if hovered else _col(Col.FRAME_BG),
                             ctx.style.frame_rounding)
    shown_value = fmt % value
    tw, th = ctx.draw.calc_text_size(shown_value)
    ctx.draw.add_text((field[0] + (field[2] - tw) * 0.5, field[1] + (field[3] - th) * 0.5),
                      _col(Col.TEXT), shown_value)
    if shown:
        ctx.draw.add_text((field[0] + field[2] + ctx.style.item_inner_spacing[0], box[1]),
                          _col(Col.TEXT), shown)
    return (bool(held), value)


def drag_float(label: str, v: float, speed: float = 1.0, v_min=None, v_max=None,
               fmt: str = "%.3f") -> tuple[bool, float]:
    return _drag(label, float(v), speed, v_min, v_max, fmt, integral=False)


def drag_int(label: str, v: int, speed: float = 1.0, v_min=None, v_max=None,
             fmt: str = "%d") -> tuple[bool, int]:
    return _drag(label, int(v), speed, v_min, v_max, fmt, integral=True)


def progress_bar(fraction: float, size=None, overlay: str = "") -> None:
    ctx = get_current_context()
    width, height = _calc_item_size(size, ctx.layout.avail()[0], _frame_height(ctx))
    box = ctx.layout.row(height=height, width=width)
    ctx.item_add(box)
    fraction = max(0.0, min(1.0, float(fraction)))
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.FRAME_BG), ctx.style.frame_rounding)
    if fraction > 0.0:
        ctx.draw.add_rect_filled((box[0], box[1]),
                                 (box[0] + box[2] * fraction, box[1] + box[3]),
                                 _col(Col.SLIDER_GRAB), ctx.style.frame_rounding)
    overlay = tr(overlay) if overlay else ""
    if overlay:
        tw, th = ctx.draw.calc_text_size(overlay)
        ctx.draw.add_text((box[0] + (box[2] - tw) * 0.5, box[1] + (box[3] - th) * 0.5),
                          _col(Col.TEXT), overlay)


# --------------------------------------------------------------------------- #
# Lists and trees
# --------------------------------------------------------------------------- #
def selectable(label: str, selected: bool = False, size=None) -> bool:
    ctx = get_current_context()
    if ctx._context_popup_stack:
        return ctx.context_menu_item(label, selected=selected)
    width, height = _calc_item_size(size, ctx.layout.avail()[0], _frame_height(ctx))
    box = ctx.layout.row(height=height, width=width)
    hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    if selected or hovered:
        ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                 _col(Col.HEADER) if selected else _col(Col.HEADER_HOVERED), 0.0)
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), _col(Col.TEXT),
                      _visible_label(label))
    return pressed


def combo(label: str, current: int, items: Sequence[str],
          items_count: int = -1,
          popup_max_height_in_items: int = -1) -> tuple[bool, int]:
    """``ImGui::Combo``: a click opens the list; a pick from it is the change.

    The list is an overlay (:mod:`emtk.overlays`), drawn over everything at
    the end of the frame: below the field or flipped above it, as wide as its
    longest item, inside the frame, scrolled when it is long, with the keyboard
    and -- for a long list -- a filter field typed into. The pick is returned
    on the frame after it was made.

    ``items_count`` and ``popup_max_height_in_items`` are the reference's
    trailing parameters. C++ has no length on an array of pointers, so the
    count has to be passed; a Python sequence carries its own, but a port
    passes it positionally all the same -- and without somewhere for it to
    land the call was a TypeError that took the panel with it.
    """
    if items_count is not None and 0 <= items_count < len(items):
        items = list(items)[:items_count]
    del popup_max_height_in_items        # the list is as tall as the frame allows
    from . import overlays as _overlays

    ctx = get_current_context()
    height = _frame_height(ctx)
    # `SetNextItemWidth` applies to a combo in the reference, as it does to
    # every framed input. Ignoring it made the box span the row, so a
    # `SameLine()` after one put the next widget off the right edge -- the
    # toolbar shape every settings panel starts with.
    # The label sits *beside* the frame in the reference, and the item's width
    # covers both -- which is what makes `SameLine()` after a combo clear the
    # label instead of drawing the next widget on top of it.
    visible = _visible_label(label)
    label_w = ((ctx.style.item_inner_spacing[0] + ctx.draw.calc_text_size(visible)[0])
               if visible else 0.0)
    wanted = ctx.take_next_item_width(None)
    box = ctx.layout.row(height=height, width=_labelled_item_width(ctx, wanted, label_w))
    frame_w = max(box[2] - label_w, 1.0)
    frame = (box[0], box[1], frame_w, height)
    item_id = ctx.get_id(label)
    changed = False
    picked = _overlays.take_choice(item_id)
    if picked is not None and 0 <= picked < len(items) and picked != current:
        current, changed = picked, True
    hovered, _held, pressed = ctx.button_behavior(frame, item_id)
    ctx.draw.add_rect_filled((frame[0], frame[1]), (frame[0] + frame_w, frame[1] + height),
                             _col(Col.FRAME_BG_HOVERED) if hovered else _col(Col.FRAME_BG),
                             ctx.style.frame_rounding)
    shown = items[current] if 0 <= current < len(items) else ""
    # The caption stops short of the arrow, clipped to the frame.
    arrow = height * 0.32
    ax = frame[0] + frame_w - ctx.style.frame_padding[0] - arrow * 1.2
    ctx.draw.push_clip_rect((frame[0], frame[1]), (ax - 2.0, frame[1] + height))
    ctx.draw.add_text((frame[0] + ctx.style.frame_padding[0], frame[1]), _col(Col.TEXT), str(shown))
    ctx.draw.pop_clip_rect()
    cy = frame[1] + height / 2.0
    ctx.draw.add_triangle_filled((ax, cy - arrow * 0.45), (ax + arrow * 1.2, cy - arrow * 0.45),
                                 (ax + arrow * 0.6, cy + arrow * 0.45), _col(Col.TEXT))
    if visible:
        ctx.draw.add_text((frame[0] + frame_w + ctx.style.item_inner_spacing[0], box[1]),
                          _col(Col.TEXT), visible)
    _overlays.combo_list(item_id, [str(item) for item in items], current,
                         below=frame if pressed and items else None)
    return (changed, current)


def collapsing_header(label: str, open_: "Optional[bool | int]" = None) -> bool:
    """``ImGui::CollapsingHeader``: returns whether the body should be drawn.

    Parameters
    ----------
    label : str
    open_ : bool, int or None
        A ``bool`` *forces* the state on every call (a caller that owns the state, for
        instance to open a header from outside). An ``int`` is ImGui's ``flags`` word:
        ``TreeNodeFlags.DEFAULT_OPEN`` makes the header start open, and that is **all** it
        does -- after the first frame the user's clicks own the state. (Reading a flags
        word as a bool forced ``flags=0`` closed and ``DEFAULT_OPEN`` open on every frame,
        so such a header could never be toggled.) The literal ``1`` that older callers pass
        for "open" is accepted as ``DEFAULT_OPEN``. ``None`` leaves the state alone; a header
        nobody opened starts closed.
    """
    ctx = get_current_context()
    item_id = ctx.get_id(label)
    store = ctx.get_storage(item_id)
    if isinstance(open_, bool):
        store["open"] = open_
    elif open_ is not None and "open" not in store:
        store["open"] = bool(int(open_) & 32) or int(open_) == 1    # DEFAULT_OPEN (32), or legacy 1
    is_open = bool(store.get("open", False))
    height = _frame_height(ctx)
    box = ctx.layout.row(height=height)
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    if pressed:
        is_open = not is_open
        store["open"] = is_open
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.BUTTON_HOVERED) if hovered else _col(Col.BUTTON),
                             ctx.style.frame_rounding)
    arrow = "v" if is_open else ">"
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), _col(Col.TEXT),
                      f"{arrow} {_visible_label(label)}")
    return is_open


def tree_node(label: str) -> bool:
    """``ImGui::TreeNode``: indent on the way in, :func:`tree_pop` on the way out."""
    is_open = collapsing_header(label)
    if is_open:
        indent()
    return is_open


def tree_pop() -> None:
    unindent()


# --------------------------------------------------------------------------- #
# What porting the demo turned out to need
# --------------------------------------------------------------------------- #
#
# Everything below exists because a faithful transliteration of
# `imgui_demo.cpp`'s "Widgets/Basic" section asked for it and emtk had no
# answer. That is the point of porting the demo: the gaps are found by the
# reference's own code rather than by guessing what a port might want.


class Dir:
    """``ImGuiDir_``."""

    NONE = -1
    LEFT = 0
    RIGHT = 1
    UP = 2
    DOWN = 3


def align_text_to_frame_padding() -> None:
    """``ImGui::AlignTextToFramePadding``."""
    get_current_context().align_text_to_frame_padding()


def set_next_item_width(width: float) -> None:
    """``ImGui::SetNextItemWidth``."""
    get_current_context().set_next_item_width(width)


def push_style_color(which, colour) -> None:
    get_current_context().push_style_color(which, colour)


def pop_style_color(count: int = 1) -> None:
    get_current_context().pop_style_color(count)


def push_item_flag(flag: int, enabled: bool) -> None:
    get_current_context().push_item_flag(flag, enabled)


def pop_item_flag() -> None:
    get_current_context().pop_item_flag()


def separator_text(label: str) -> None:
    """``ImGui::SeparatorText``: a rule with a caption in it."""
    ctx = get_current_context()
    box = ctx.layout.row()
    ctx.item_add(box)
    tw, th = ctx.draw.calc_text_size(label)
    mid = box[1] + box[3] * 0.5
    ctx.draw.add_text((box[0], box[1] + (box[3] - th) * 0.5), _col(Col.TEXT), label)
    left = box[0] + tw + ctx.style.item_inner_spacing[0]
    if box[0] + box[2] > left:
        ctx.draw.add_line((left, mid), (box[0] + box[2], mid), _col(Col.SEPARATOR), 1.0)


def arrow_button(str_id: str, direction: int) -> bool:
    """``ImGui::ArrowButton``: a square button with a triangle in it."""
    ctx = get_current_context()
    size = _frame_height(ctx)
    box = ctx.layout.row(height=size, width=size)
    hovered, held, pressed = ctx.button_behavior(box, ctx.get_id(str_id))
    colour = (_col(Col.BUTTON_ACTIVE) if held
              else _col(Col.BUTTON_HOVERED) if hovered else _col(Col.BUTTON))
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             colour, ctx.style.frame_rounding)
    cx, cy = box[0] + box[2] * 0.5, box[1] + box[3] * 0.5
    r = size * 0.25
    points = {
        Dir.LEFT: ((cx + r, cy - r), (cx + r, cy + r), (cx - r, cy)),
        Dir.RIGHT: ((cx - r, cy - r), (cx - r, cy + r), (cx + r, cy)),
        Dir.UP: ((cx - r, cy + r), (cx + r, cy + r), (cx, cy - r)),
        Dir.DOWN: ((cx - r, cy - r), (cx + r, cy - r), (cx, cy + r)),
    }.get(direction)
    if points:
        ctx.draw.add_triangle_filled(*points, _col(Col.TEXT))
    return pressed


def checkbox_flags(label: str, flags: int, flags_value: int) -> tuple[bool, int]:
    """``ImGui::CheckboxFlags``: a checkbox over one bit of an int."""
    checked = (flags & flags_value) == flags_value and flags_value != 0
    changed, now = checkbox(label, checked)
    if changed:
        flags = (flags | flags_value) if now else (flags & ~flags_value)
    return (changed, flags)


def set_item_tooltip(s: str) -> None:
    """``ImGui::SetItemTooltip``: a tooltip, if the last item is hovered --
    disabled or not (ImGui's tooltip hover flags allow disabled items, so a
    disabled control can say why it is disabled)."""
    ctx = get_current_context()
    if ctx._context_popup_last_item is not None:
        ctx._context_popup_last_item.tooltip = str(s) if s else None
        ctx._context_popup_last_item = None
        return
    if is_item_hovered(allow_when_disabled=True):
        set_tooltip(s)


def slider_angle(label: str, rad: float, degrees_min: float = -360.0,
                 degrees_max: float = 360.0) -> tuple[bool, float]:
    """``ImGui::SliderAngle``: radians in, degrees on the slider."""
    import math

    changed, degrees = slider_float(label, math.degrees(rad), degrees_min,
                                    degrees_max, "%.0f deg")
    return (changed, math.radians(degrees))


def input_float(label: str, v: float, step: float = 0.0,
                step_fast: float = 0.0, fmt: str = "%.3f",
                flags: int = 0) -> tuple[bool, float]:
    """``ImGui::InputFloat``: the field, plus -/+ when a step is given.

    *step_fast* is the reference's larger step, taken when Ctrl is held --
    the demo's own line is ``InputFloat("input float", &f0, 0.01f, 1.0f,
    "%.3f")``, a hundred-to-one ratio between the two. It sits fourth
    because that is where the reference puts it, and a port hands its
    arguments over positionally.
    """
    ctx = get_current_context()
    changed = False
    if step or step_fast:
        by = step_fast if (step_fast and ctx.io.key_ctrl) else step
        ctx.push_id(label)
        if arrow_button("##-", Dir.LEFT):
            v, changed = v - by, True
        set_item_tooltip(f"Decrease the value by {by:g}; hold the primary modifier for the larger step.")
        same_line(0.0, ctx.style.item_inner_spacing[0])
        if arrow_button("##+", Dir.RIGHT):
            v, changed = v + by, True
        set_item_tooltip(f"Increase the value by {by:g}; hold the primary modifier for the larger step.")
        same_line(0.0, ctx.style.item_inner_spacing[0])
        ctx.pop_id()
    edited, v = drag_float(label, v, max(step, 0.01) or 0.01, fmt=fmt)
    return (changed or edited, v)


def input_int(label: str, v: int, step: int = 1, step_fast: int = 100,
              flags: int = 0) -> tuple[bool, int]:
    """``ImGui::InputInt``. The reference's defaults are 1 and 100 -- the
    fast step is a hundred times the slow one, taken with Ctrl held."""
    changed, value = input_float(label, float(v), float(step),
                                 float(step_fast), fmt="%.0f", flags=flags)
    return (changed, int(round(value)))


def input_text(label: str, value: str, hint: str = "", flags: int = 0,
               elide_start: bool = False) -> tuple[bool, str]:
    """``ImGui::InputText``: the field, edited by the keys in ``io``.

    A port gets the box, the caret, a selection and the text; the *keys* come
    from ``io.key_events`` (else ``io.key`` and ``io.text``), which is where
    the host puts them. The editing is :class:`emtk.widgets.text_field.
    TextField`'s, so the platform's shortcuts (select all, copy/cut/paste
    through :mod:`emtk.clipboard`, undo/redo, word and line movement) work
    here as in every emtk field; the mouse places the caret, drags a
    selection, and a double / triple click selects a word / everything.

    ``flags`` accepts ``im.InputTextFlags`` bits: ``CHARS_HEXADECIMAL`` and
    ``CHARS_DECIMAL`` filter what is typed, ``READ_ONLY`` forbids editing,
    ``AUTO_SELECT_ALL`` selects the whole value when a click focuses it,
    ``ALWAYS_OVERWRITE`` types over the character at the caret, and
    ``ENTER_RETURNS_TRUE`` makes the changed flag report the Enter key.

    *value* may also be a C ``char`` buffer -- a list, NUL-terminated --
    because that is what the reference's signature takes and what a port
    therefore fills in the two lines above the call. It is read to its first
    NUL and the edited **string** is what comes back, which is what the C++
    assigns out of the buffer on the next line anyway.

    A value wider than the field shows its end while the field has the
    keyboard, so the caret stays in sight. *elide_start* (an emtk extension)
    shows the end at rest too, after a "…" -- a path, whose file name is the
    part worth seeing.
    """
    from .cpp_compat import String
    from .flags import InputTextFlags as _ITF

    if isinstance(value, (list, tuple, bytearray, bytes)):
        value = str(String(value))
    hint = tr(hint)

    read_only = bool(flags & _ITF.READ_ONLY)
    enter_returns = bool(flags & _ITF.ENTER_RETURNS_TRUE)
    ctx = get_current_context()
    label_shown = _visible_label(label)
    label_width = (ctx.draw.calc_text_size(label_shown)[0] + ctx.style.item_inner_spacing[0]
                   if label_shown else 0.0)
    total = ctx.layout.row(height=_frame_height(ctx),
        width=_labelled_item_width(ctx, ctx.take_next_item_width(None), label_width))
    box = (total[0], total[1], max(1.0, total[2] - label_width), total[3])
    item_id = ctx.get_id(label)
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    focus = ctx.state(("focus",))
    # Focused on the *down* edge, so the same press places the caret (or
    # starts a drag-select) -- ButtonBehavior's press fires on the release.
    if pressed or (hovered and ctx.io.mouse_clicked[0]):
        focus["id"] = item_id
        set_nav_id(item_id)
    elif ctx.io.mouse_clicked[0] and not hovered and focus.get("id") == item_id:
        focus.pop("id", None)
    # ...or the keyboard put the focus here, which is what Tab is for.
    focused = not bool(ctx.item_flags & ItemFlags.DISABLED) and (
        focus.get("id") == item_id or ctx.is_nav_focused(item_id))

    field, st = _field_state(ctx, item_id, value, focused)
    pad = ctx.style.frame_padding[0]
    room = box[2] - 2.0 * pad
    width = lambda s_: ctx.draw.calc_text_size(s_)[0]  # noqa: E731
    password = bool(flags & _ITF.PASSWORD)
    field_width = (lambda text_: width("*" * len(text_))) if password else width
    origin = box[0] + pad - (st["scroll"] if focused else 0.0)
    if focused:
        _field_mouse(ctx, field, st, hovered, origin, field_width,
                     bool(flags & _ITF.AUTO_SELECT_ALL))
        entered = _field_keys(ctx, field, flags, read_only)
        ctx._want_text_input = True
    else:
        entered = False
    changed = field.text != value
    value = field.text
    if enter_returns:
        changed = focused and entered and bool(value)
    st["seen"] = value

    ctx.draw.add_rect_filled(
        (box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
        _col(Col.FRAME_BG_ACTIVE) if focused
        else (_col(Col.FRAME_BG_HOVERED) if hovered else _col(Col.FRAME_BG)),
        ctx.style.frame_rounding)
    _frame_border(ctx, box)
    display_value = "*" * len(value) if password else value
    shown = display_value if (value or not hint) else hint
    text_w = width(shown)
    if focused:             # scrolled so the caret stays in the field
        caret_px = width(display_value[:field.cursor])
        scroll = min(st["scroll"], max(text_w - room, 0.0))
        scroll = min(max(scroll, caret_px - room), caret_px)
        st["scroll"] = max(scroll, 0.0)
    else:
        st["scroll"] = 0.0
    origin = box[0] + pad - st["scroll"]
    if value and elide_start and not focused and text_w > room:
        shown = _elide_start(ctx, display_value, room)
    elif not value and hint and text_w > room and not focused:
        # An over-wide hint ends in an ellipsis rather than a hard clip --
        # the placeholder is the only thing telling the user what to type,
        # and a cut-off sentence reads as one.
        shown = _elide_end(ctx, hint, room)
    # Clipped to the field, as the reference's InputText is: a value longer
    # than its box used to run over whatever stood beside it.
    ctx.draw.push_clip_rect((box[0], box[1]), (box[0] + box[2], box[1] + box[3]))
    if focused and field.has_selection():
        lo, hi = field.selection()
        from .style import TEXT_SELECTED_BG  # noqa: PLC0415
        ctx.draw.add_rect_filled((origin + width(display_value[:lo]), box[1] + 2.0),
                                 (origin + width(display_value[:hi]), box[1] + box[3] - 2.0),
                                 TEXT_SELECTED_BG)
    ctx.draw.add_text((origin, box[1] + ctx.style.frame_padding[1]),
                      _col(Col.TEXT) if value else _col(Col.TEXT_DISABLED), shown)
    if focused:
        caret = origin + width(display_value[:field.cursor])
        ctx.draw.add_line((caret, box[1] + 2.0), (caret, box[1] + box[3] - 2.0),
                          _col(Col.TEXT), 1.0)
    ctx.draw.pop_clip_rect()
    label_shown = _visible_label(label)
    if label_shown:
        ctx.draw.add_text((box[0] + box[2] + ctx.style.item_inner_spacing[0], box[1]),
                          _col(Col.TEXT), label_shown)
    return (changed, value)


#: Seconds within which a second press counts toward a double or triple click.
_MULTI_CLICK_S = 0.4


def _field_state(ctx, item_id, value: str, focused: bool):
    """The :class:`TextField` behind an ``input_text``, kept in step with *value*.

    Unfocused, the field is whatever the caller passes. Focused, it is what
    was typed -- unless the caller changed the value since the last frame
    (a Reset button), which is taken as it is.
    """
    from .widgets.text_field import TextField  # noqa: PLC0415

    st = ctx.state(("input_text_field", item_id))
    field = st.get("field")
    if field is None:
        field = st["field"] = TextField()
        st.update(scroll=0.0, clicks=0, click_t=-1.0, drag=False, seen=None, had=False,
                  had_before=False)
    if not focused or st.get("seen") != value:
        if field.text != value:
            field.set_text(value)
    if focused and not st["had"] and not ctx.io.mouse_clicked[0]:
        field.select_all()          # Tab into a field selects it, as ImGui does
    st["had_before"], st["had"] = st["had"], focused
    return field, st


def _field_mouse(ctx, field, st, hovered: bool, origin: float, width,
                 auto_select_all: bool = False) -> None:
    """Click places the caret, shift-click extends, drag selects, a double
    click selects a word and a triple click everything. With
    *auto_select_all* (``AUTO_SELECT_ALL``) the click that focuses the field
    selects it whole, so typing replaces a number rather than extending it."""
    io = ctx.io
    if auto_select_all and not st["had_before"] and io.mouse_clicked[0]:
        field.select_all()
        st.update(clicks=1, click_t=io.now, drag=False)
        return

    def index_at(x: float) -> int:
        if x < origin:
            return len(field.text)
        best, best_d = 0, abs(x - origin)
        for i in range(1, len(field.text) + 1):
            d = abs(x - (origin + width(field.text[:i])))
            if d < best_d:
                best, best_d = i, d
        return best

    if hovered and io.mouse_clicked[0]:
        at = index_at(io.mouse_pos[0])
        quick = io.now - st["click_t"] <= _MULTI_CLICK_S
        st["clicks"] = st["clicks"] + 1 if quick else 1
        if io.mouse_double_clicked[0]:
            st["clicks"] = max(st["clicks"], 2)
        st["click_t"] = io.now
        st["drag"] = st["clicks"] == 1
        if st["clicks"] >= 3:
            field.select_all()
        elif st["clicks"] == 2:
            field.select_word_at(at)
        else:
            field.move(at, extend=io.key_shift)
    elif st["drag"] and io.mouse_down[0]:
        field.move(index_at(io.mouse_pos[0]), extend=True)
    if not io.mouse_down[0]:
        st["drag"] = False


def _field_keys(ctx, field, flags: int, read_only: bool) -> bool:
    """Feed this frame's keys to *field*; returns whether Enter was among them."""
    from .flags import InputTextFlags as _ITF  # noqa: PLC0415

    io = ctx.io
    events = list(io.key_events)
    if not events and (io.key or io.text):
        mods = _current_modifiers(io)
        events = [(io.key, io.text, mods)]
    entered = False
    for key, text, mods in events:
        if key in _ENTER_KEYS:
            entered = True
            continue
        if flags & _ITF.CHARS_HEXADECIMAL:
            text = "".join(c for c in text if c in "0123456789abcdefABCDEF")
        elif flags & _ITF.CHARS_DECIMAL:
            text = "".join(c for c in text if c in "-+.0123456789eE")
        if not key and not text:
            continue
        if flags & _ITF.ALWAYS_OVERWRITE and text and not field.has_selection():
            field.move(field.cursor + len(text), extend=True)
        before = (field.text, field.cursor, field.anchor)
        field.key(key, text, mods)
        if read_only and field.text != before[0]:
            field.text = before[0]
            field.cursor = min(before[1], len(field.text))
    return entered


def _current_modifiers(io) -> int:
    from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER  # noqa: PLC0415

    return ((CONTROL_MODIFIER if io.key_ctrl else 0) | (SHIFT_MODIFIER if io.key_shift else 0)
            | (ALT_MODIFIER if io.key_alt else 0) | (META_MODIFIER if io.key_super else 0))


def _elide_end(ctx, text: str, room: float) -> str:
    """"…" and the longest start of *text* that fits in *room* with it."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ctx.draw.calc_text_size(text[:mid] + "…")[0] <= room:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"


def _elide_start(ctx, text: str, room: float) -> str:
    """"…" and the longest end of *text* that fits in *room* with it."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ctx.draw.calc_text_size("…" + text[len(text) - mid:])[0] <= room:
            lo = mid
        else:
            hi = mid - 1
    return "…" + text[len(text) - lo:] if lo else "…"


#: What Enter arrives as. A host that forwards Qt's key codes delivers
#: ``KEY_RETURN`` / ``KEY_ENTER`` (0x01000004/5), one that forwards characters
#: delivers 13; checking only 13 meant ``ENTER_RETURNS_TRUE`` never fired under
#: ``qt_host``, so a field could be typed into and never committed.
_ENTER_KEYS = (13, 0x01000004, 0x01000005)


def input_text_with_hint(label: str, value: str, hint: str = "") -> tuple[bool, str]:
    """``InputTextWithHint``: an input whose empty state shows *hint*.

    The argument order matches :func:`input_text` — ``(label, value, hint)`` —
    so moving between the two is mechanical. (The reference C++ API puts the
    hint before the buffer; a value-based Python API that did the same made
    every ported call a silent hint/value swap.)
    """
    return input_text(label, value, hint)


def color_button(desc_id: str, col, flags: int = 0, size=None) -> bool:
    """``ImGui::ColorButton``: a swatch that behaves like a button.

    The reference's signature is ``(desc_id, col, flags, size)``, and a port
    passes all four positionally. Without ``flags`` in the middle the call
    was a TypeError -- and a swatch is the one widget a settings panel puts
    in every row of a channel table, so one missing parameter cost the whole
    panel. The bits are accepted; what this draws is the swatch, which is
    what the caller wanted from it.
    """
    del flags                      # accepted, and this swatch has no options
    ctx = get_current_context()
    width, side = _calc_item_size(size, _frame_height(ctx), _frame_height(ctx))
    box = ctx.layout.row(height=side, width=width)
    _hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(desc_id))
    rgba = tuple(col) if len(col) == 4 else (*col, 255)
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             rgba, ctx.style.frame_rounding)
    ctx.draw.add_rect((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                      _col(Col.BORDER), ctx.style.frame_rounding)
    return pressed


def color_edit3(label: str, col) -> tuple[bool, tuple]:
    """Three bounded channel drags, a swatch and a label that can wrap."""
    ctx = get_current_context()
    ctx.push_id(label)
    values, changed = list(col[:3]), False
    visible = _visible_label(label)
    available = max(1.0, ctx.layout.avail()[0] - ctx.style.frame_padding[0])
    spacing = ctx.style.item_inner_spacing[0]
    side = min(_frame_height(ctx), available / 4)
    label_width = ctx.draw.calc_text_size(visible)[0] if visible else 0.0
    label_above = bool(visible and available < label_width + side + 3 * 32 + 4 * spacing)
    if label_above:
        text_wrapped(visible)
        label_width = 0.0
    remaining = available - side - 3 * spacing - (label_width + spacing if label_width else 0.0)
    channel_width = max(1.0, remaining / 3)
    for index, channel in enumerate("RGB"):
        if index:
            same_line(0.0, spacing)
        set_next_item_width(channel_width)
        edited, values[index] = drag_float(f"##{channel}", float(values[index]),
                                           1.0, 0.0, 255.0, "%.0f")
        set_item_tooltip(f"{visible or 'Color'}: {channel} channel (0–255)")
        changed = changed or edited
    same_line(0.0, spacing)
    color_button("##swatch", tuple(int(v) for v in values), size=(side, _frame_height(ctx)))
    set_item_tooltip(f"{visible or 'Color'} preview")
    if visible and not label_above:
        same_line(0.0, spacing)
        box = ctx.layout.row(height=_frame_height(ctx), width=label_width)
        ctx.item_add(box)
        label_height = ctx.draw.calc_text_size(visible)[1]
        from .mathtext import convert_script_markup

        ctx.p.text(box[0], box[1] + max(0.0, (box[3] - label_height) / 2),
                   box[2], label_height, ALIGN_LEFT | ALIGN_VCENTER,
                   convert_script_markup(visible), _col(Col.TEXT))
    ctx.pop_id()
    return (changed, tuple(values))


def color_edit4(label: str, col) -> tuple[bool, tuple]:
    changed, rgb = color_edit3(label, col[:3])
    alpha = col[3] if len(col) > 3 else 255
    return (changed, (*rgb, alpha))


# `emtk.keys` spellings, imported here so the module keeps its own dependency.
from .keys import KEY_BACKSPACE as _BACKSPACE, KEY_DELETE as _DELETE  # noqa: E402

__all__ += [
    "Dir", "align_text_to_frame_padding", "set_next_item_width",
    "push_style_color", "pop_style_color", "push_item_flag", "pop_item_flag",
    "separator_text", "arrow_button", "checkbox_flags",
    "set_item_tooltip", "slider_angle", "input_float", "input_int",
    "input_text", "input_text_with_hint", "color_button", "color_edit3",
    "color_edit4",
]


# --------------------------------------------------------------------------- #
# Queries, stacks and containers -- the rest of what a port reaches for
# --------------------------------------------------------------------------- #
def _ctx():
    return get_current_context()


# -- where things are ------------------------------------------------------- #
def get_content_region_avail() -> tuple:
    return _ctx().layout.avail()


def get_line_avail() -> float:
    """Room left on the *current line*, beside the last item — or 0.0 on an
    empty line.

    ``GetContentRegionAvail`` measures from the cursor, and after any item the
    cursor is back at the row start, so mid-row it always reads the full width.
    This is the measurement "does the next control still fit?" wants: see
    :meth:`emtk.layout.Layout.line_avail` for the trap this exists to close.
    """
    return _ctx().layout.line_avail()


def get_cursor_pos() -> tuple:
    return _ctx().layout.cursor


def get_cursor_pos_x() -> float:
    return _ctx().layout.cursor[0]


def get_cursor_pos_y() -> float:
    return _ctx().layout.cursor[1]


def set_cursor_pos(pos) -> None:
    set_cursor_screen_pos(pos)


def get_item_rect_min() -> tuple:
    box = _ctx().get_item_rect() or (0.0, 0.0, 0.0, 0.0)
    return (box[0], box[1])


def get_item_rect_max() -> tuple:
    box = _ctx().get_item_rect() or (0.0, 0.0, 0.0, 0.0)
    return (box[0] + box[2], box[1] + box[3])


def get_item_rect_size() -> tuple:
    box = _ctx().get_item_rect() or (0.0, 0.0, 0.0, 0.0)
    return (box[2], box[3])


def get_window_pos() -> tuple:
    window = _ctx().current_window
    box = window.box if window else _ctx().box
    return (box[0], box[1])


def get_window_size() -> tuple:
    window = _ctx().current_window
    box = window.box if window else _ctx().box
    return (box[2], box[3])


def get_window_width() -> float:
    return get_window_size()[0]


def get_window_height() -> float:
    return get_window_size()[1]


def get_color_u32(which, alpha_mul: float = 1.0):
    """``ImGui::GetColorU32``: a style index, or a colour, as emtk paints it.

    The reference's colour overload takes an ``ImVec4`` -- **floats 0..1** --
    while emtk paints in bytes 0..255, so a ported
    ``GetColorU32(ImVec4(0.05f, 0.05f, 0.05f, 0.85f))`` handed the painter
    four floats. Under the headless painter that is arithmetic and draws
    something near black; under Qt it is a ``TypeError`` from ``QColor``.
    Neither is what the C++ asked for, and the first is worse because it
    looks like it worked.

    Floats are converted. The test is the *values*, not the type: a colour
    whose components are all within 0..1 is the reference's ImVec4 -- bytes
    in that range are a black so nearly transparent that no interface asks
    for it on purpose -- and anything above 1 is already bytes.
    """
    colour = _col(which) if isinstance(which, int) else tuple(which)
    if colour and all(isinstance(c, float) and 0.0 <= c <= 1.0 for c in colour):
        from .widgets.color import floats_to_rgba

        colour = floats_to_rgba(colour)
    if alpha_mul == 1.0 or len(colour) < 4:
        return colour
    return (*colour[:3], int(colour[3] * alpha_mul))


def get_mouse_pos() -> tuple:
    return _ctx().io.mouse_pos


def get_mouse_drag_delta(button: int = 0) -> tuple:
    return _ctx().io.mouse_drag_delta(button)


# -- what the pointer is doing ---------------------------------------------- #
def is_mouse_down(button: int = 0) -> bool:
    return bool(_ctx().io.mouse_down[button])


def is_mouse_clicked(button: int = 0) -> bool:
    return bool(_ctx().io.mouse_clicked[button])


def is_mouse_released(button: int = 0) -> bool:
    return bool(_ctx().io.mouse_released[button])


def is_mouse_double_clicked(button: int = 0) -> bool:
    return bool(_ctx().io.mouse_double_clicked[button])


def is_mouse_dragging(button: int = 0, lock_threshold: float = 6.0) -> bool:
    io = _ctx().io
    if not io.mouse_down[button]:
        return False
    dx, dy = io.mouse_drag_delta(button)
    return (dx * dx + dy * dy) ** 0.5 >= lock_threshold


def is_mouse_hovering_rect(r_min, r_max) -> bool:
    x, y = _ctx().io.mouse_pos
    return r_min[0] <= x < r_max[0] and r_min[1] <= y < r_max[1]


def is_any_mouse_down() -> bool:
    return any(_ctx().io.mouse_down)


# -- what the last item is doing -------------------------------------------- #
def is_item_activated() -> bool:
    """``IsItemActivated``: the frame it *became* active, and only that one.

        if (g.ActiveId == g.LastItemData.ID && g.ActiveIdPreviousFrame != ...)
    """
    ctx = _ctx()
    return (ctx.active_id is not None
            and ctx.active_id == ctx._last_id
            and ctx.active_id_previous_frame != ctx._last_id)


def is_item_deactivated() -> bool:
    """``IsItemDeactivated``: the frame it *stopped* being active.

    Not "is not active" -- that is true of every item on screen, and reporting
    it would fire the caller's on-edit-finished handler for widgets nobody
    has ever touched.
    """
    ctx = _ctx()
    return (ctx._last_id is not None
            and ctx.active_id_previous_frame == ctx._last_id
            and ctx.active_id != ctx._last_id)


def is_item_visible() -> bool:
    box = _ctx().get_item_rect()
    return box is not None and _ctx()._overlaps_clip(box)


def is_item_focused() -> bool:
    return is_item_active()


def is_any_item_hovered() -> bool:
    return _ctx().hovered_id is not None


def is_any_item_active() -> bool:
    return _ctx().active_id is not None


def is_window_hovered() -> bool:
    ctx = _ctx()
    return ctx.hovered_window is not None and ctx.hovered_window is ctx.current_window


def is_window_focused() -> bool:
    ctx = _ctx()
    return bool(ctx.windows) and ctx.current_window is ctx.windows[-1]


# -- stacks ------------------------------------------------------------------ #
def push_item_width(width: float) -> None:
    ctx = _ctx()
    ctx.state(("item_width",)).setdefault("stack", []).append(width)
    ctx.set_next_item_width(width)


def pop_item_width() -> None:
    stack = _ctx().state(("item_width",)).get("stack") or []
    if stack:
        stack.pop()


def push_style_var(which: str, value) -> None:
    """``PushStyleVar``: a metric, by attribute name (``"frame_rounding"``)."""
    ctx = _ctx()
    ctx.state(("style_var",)).setdefault("stack", []).append(
        (which, getattr(ctx.style, which, None)))
    setattr(ctx.style, which, value)


def pop_style_var(count: int = 1) -> None:
    ctx = _ctx()
    stack = ctx.state(("style_var",)).get("stack") or []
    for _ in range(max(int(count), 0)):
        if not stack:
            return
        which, previous = stack.pop()
        setattr(ctx.style, which, previous)


def push_clip_rect(r_min, r_max, intersect: bool = True) -> None:
    _ctx().draw.push_clip_rect(r_min, r_max, intersect)


def pop_clip_rect() -> None:
    _ctx().draw.pop_clip_rect()


def begin_disabled(disabled: bool = True) -> None:
    """``BeginDisabled``: the items inside draw dim and cannot be used."""
    _ctx().push_item_flag(ItemFlags.DISABLED, disabled)


def end_disabled() -> None:
    _ctx().pop_item_flag()


# -- text ------------------------------------------------------------------- #
def text_unformatted(s: str) -> None:
    text(s)


def align_text_to_frame_padding_() -> None:      # kept for symmetry in ports
    align_text_to_frame_padding()


# -- trees ------------------------------------------------------------------ #
def set_next_item_open(is_open: bool, cond: int = 0) -> None:
    """``ImGui::SetNextItemOpen``.

    *cond* is accepted for signature parity. emtk keeps no ``.ini``, so
    there is no stored state for ``Once``/``FirstUseEver`` to defer to and
    every condition reduces to "set it": honouring them would mean
    remembering what a *previous run* did, which is exactly the thing emtk
    does not do.
    """
    _ctx().state(("next_open",))["open"] = bool(is_open)


def tree_node_ex(label: str, flags: int = 0) -> bool:
    forced = _ctx().state(("next_open",)).pop("open", None)
    is_open = collapsing_header(label, forced)
    if is_open:
        indent()
    return is_open


def tree_push(label: str = "") -> None:
    indent()


# -- tooltips and popups ---------------------------------------------------- #
def begin_tooltip() -> bool:
    return True


def end_tooltip() -> None:
    pass


def begin_item_tooltip() -> bool:
    return is_item_hovered()


def open_popup(name: str) -> None:
    _ctx().open_popup(name)


def begin_popup(name: str) -> bool:
    """Begin an open popup; a context popup's menu rows render as an overlay."""
    return _ctx().begin_popup(name)


def end_popup() -> None:
    _ctx().end_popup()


def close_current_popup() -> None:
    ctx = _ctx()
    for name, is_open in list(ctx._popups.items()):
        if is_open:
            ctx.close_current_popup(name)


def is_popup_open(name: str) -> bool:
    return _ctx().is_popup_open(name)


# -- menus ------------------------------------------------------------------ #
def begin_menu_bar() -> bool:
    """Start a horizontal menu bar: titles lay out left-to-right on one row.

    Menus opened inside the bar drop their items down as a floating popup,
    like the reference, instead of indenting them into the layout. The bar
    ends with a separator rule hard against its bottom edge, so the content
    below starts tight under it.
    """
    ctx = _ctx()
    ctx.push_id("##menubar")
    cursor = ctx.layout.cursor
    ctx._menu_bar_rect = [cursor[0], cursor[1], 0.0]
    ctx._menu_bar_first = True
    #: Where this frame's menu titles sit, by popup name: the overlay closing
    #: a menu needs the title of *its own* menu to know a press there is a
    #: toggle-off, not a click meant for whatever is behind it.
    ctx._menu_title_rects = {}
    return True


def end_menu_bar() -> None:
    ctx = _ctx()
    rect = getattr(ctx, "_menu_bar_rect", None)
    if rect is not None:
        # Separator rule hard against the bar's bottom edge: it marks the bar
        # without spending a blank line the way a bare new_line would.
        bar_height = max(ctx.layout.cursor[1] - rect[1], _frame_height(ctx))
        y = rect[1] + bar_height
        ctx.draw.add_line((rect[0], y), (rect[0] + ctx.layout.avail()[0] + (ctx.layout.cursor[0] - rect[0]), y),
                          _col(Col.BORDER), 1.0)
        ctx.layout.new_line()
    ctx._menu_bar_first = True
    ctx.pop_id()


def begin_main_menu_bar() -> bool:
    return begin_menu_bar()


def end_main_menu_bar() -> None:
    end_menu_bar()


def begin_menu(label: str, enabled: bool = True) -> bool:
    """``BeginMenu``: the title; True while its items should be submitted.

    Inside a menu bar the titles sit side by side on the bar's row, and an
    open menu submits its items into a floating popup below the title —
    the same shape as the reference's menu bars.
    """
    ctx = _ctx()
    in_bar = getattr(ctx, "_menu_bar_first", None) is not None
    if in_bar and not ctx._menu_bar_first:
        same_line()
    if in_bar:
        ctx._menu_bar_first = False
    item_id = ctx.get_id(label)
    store = ctx.get_storage(item_id)
    shown = _visible_label(label)
    width = ctx.draw.calc_text_size(shown)[0] + ctx.style.frame_padding[0] * 2.0
    box = ctx.layout.row(height=_frame_height(ctx), width=width)
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    if pressed and enabled:
        store["open"] = not store.get("open", False)
    is_open = bool(store.get("open", False)) and enabled
    if hovered or is_open:
        ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                 _col(Col.HEADER_HOVERED if hovered else Col.HEADER), 0.0)
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]),
                      _col(Col.TEXT if enabled else Col.TEXT_DISABLED), shown)
    # Popup state sync, in order:
    # 1. A selection made by the overlay last frame re-opens the popup state
    #    for exactly one frame so menu_item can report the deferred pick.
    # 2. A popup the overlay dismissed (outside click, Escape, item chosen)
    #    closes the title too — otherwise the store kept "open" and re-opened
    #    the popup every frame, swallowing every click on the window.
    popup_name = "##menu_items_" + label
    if in_bar:
        ctx._menu_title_rects[popup_name] = box
    popup_state = ctx.state(("context_popup", popup_name))
    pending = (popup_state.get("selected") is not None
               and not popup_state.get("open"))
    # The title learns the popup is gone two ways: an outside press (the
    # stored position is still set), or a pick (the "closed" mark the popup
    # leaves). Either closes the title too -- otherwise the store kept
    # "open" and re-opened the popup every frame, swallowing every click on
    # the window. Not on the frame the title itself was pressed: that press
    # toggled the store on purpose, and the sync must not undo it.
    dismissed = (store.get("open") and not pressed and not pending
                 and not popup_state.get("open")
                 and (popup_state.get("position") is not None
                      or popup_state.pop("closed", False)))
    if pending:
        store["open"] = True
        popup_state.update(open=True, just_opened=False,
                           dispatched=popup_state.get("dispatched", False))
    elif dismissed:
        store["open"] = False
        # The dismissal is consumed here. The position it was recognised by
        # has to go with it: left in place, every later open of this menu
        # looked like another dismissal -- the title toggled open and the
        # same frame's sync closed it again, so a menu reopened by a click
        # never stayed open. It is set again while the menu is open.
        popup_state.pop("position", None)

    is_open = bool(store.get("open", False)) and enabled
    if is_open:
        just_opened = (not bool(popup_state.get("open"))) and not pending
        popup_state.update(open=True,
                           selected=popup_state.get("selected"),
                           position=(box[0], box[1] + box[3]),
                           just_opened=just_opened, dispatched=False)
        ctx._popups[popup_name] = True
        if begin_popup(popup_name):
            ctx._menu_popup_open = True
        ctx.push_id(label)
        indent()
    return is_open


def end_menu() -> None:
    if getattr(_ctx(), "_menu_popup_open", False):
        _ctx()._menu_popup_open = False
        end_popup()
    unindent()
    _ctx().pop_id()


def menu_item(label: str, shortcut: str = "", selected: bool = False,
              enabled: bool = True) -> bool:
    """``MenuItem``: label on the left, shortcut on the right.

    Within a context popup, this records a floating menu row and yields its
    activation to the same ``if menu_item(...)`` block on the next frame.
    """
    ctx = _ctx()
    if ctx._context_popup_stack:
        return ctx.context_menu_item(label, shortcut, selected, enabled)
    box = ctx.layout.row(height=_frame_height(ctx))
    hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    if hovered and enabled:
        ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                 _col(Col.HEADER_HOVERED), 0.0)
    colour = _col(Col.TEXT if enabled else Col.TEXT_DISABLED)
    mark = "* " if selected else "  "
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), colour,
                      mark + _visible_label(label))
    if shortcut:
        width = ctx.draw.calc_text_size(shortcut)[0]
        ctx.draw.add_text((box[0] + box[2] - width - ctx.style.frame_padding[0],
                           box[1]), _col(Col.TEXT_DISABLED), shortcut)
    return bool(pressed and enabled)


# -- tab bars --------------------------------------------------------------- #
def begin_tab_bar(str_id: str) -> bool:
    ctx = _ctx()
    from .layout import Layout

    parent = ctx.layout
    x, y = parent.cursor
    width, height = parent.avail()
    header_height = _frame_height(ctx)
    ctx.push_id(str_id)
    # The bar's own state dict goes on a stack, because tab *items* below need
    # the bar they belong to: state keyed without the str_id made every tab
    # bar in a frame share one "selected" -- so a second bar's first tab was
    # never the selected one and its body never rendered.
    stack = getattr(ctx, "_tabbar_stack", None)
    if stack is None:
        stack = []
        ctx._tabbar_stack = stack
    store = ctx.state(("tabbar", str_id))
    if ctx.io.mouse_clicked[0] and ctx.hovered_window in (None, ctx.current_window):
        mx, my = ctx.io.mouse_pos
        for item_id, box in store.get("rects", {}).items():
            if box[0] <= mx < box[0] + box[2] and box[1] <= my < box[1] + box[3]:
                store["selected"] = item_id
                break
    store["rects"] = {}
    stack.append(store)
    layouts = getattr(ctx, "_tabbar_layouts", None)
    if layouts is None:
        layouts = []
        ctx._tabbar_layouts = layouts
    gap = ctx.style.item_spacing[1]
    header = Layout(ctx.p, x, y, width, header_height, style=parent.style)
    body = Layout(ctx.p, x, y + header_height + gap, width,
                  max(0.0, height - header_height - gap), style=parent.style)
    layouts.append({"parent": parent, "header": header, "body": body,
                    "width": width, "height": header_height, "gap": gap})
    ctx.layout = header
    return True


def end_tab_bar() -> None:
    ctx = _ctx()
    stack = getattr(ctx, "_tabbar_stack", None)
    if stack:
        stack.pop()
    layouts = getattr(ctx, "_tabbar_layouts", None)
    if layouts:
        layout = layouts.pop()
        ctx.layout = layout["parent"]
        body_height = layout["body"].content_height()
        height = layout["height"] + (layout["gap"] + body_height if body_height else 0.0)
        ctx.layout.row(height=height, width=layout["width"])
    ctx.pop_id()


def begin_tab_item(label: str, flags: int = 0, *, on_close=None) -> bool:
    """``BeginTabItem``: True while the tab's body should be submitted."""
    ctx = _ctx()
    layouts = getattr(ctx, "_tabbar_layouts", None)
    if layouts:
        ctx.layout = layouts[-1]["header"]
    stack = getattr(ctx, "_tabbar_stack", None)
    store = stack[-1] if stack else ctx.state(("tabbar",))
    shown = _visible_label(label) if isinstance(label, str) else ""
    width = ctx.draw.calc_text_size(shown)[0] + ctx.style.frame_padding[0] * 2.0
    close_width = _frame_height(ctx) if on_close is not None else 0.0
    width += close_width
    box = ctx.layout.row(height=_frame_height(ctx), width=width)
    from .flags import TabItemFlags

    item_id = ctx.get_id(label)
    if stack:
        store["rects"][item_id] = (box[0], box[1], box[2] - close_width, box[3])
    close_pressed = False
    if on_close is not None:
        close_box = (box[0] + box[2] - close_width, box[1], close_width, box[3])
        close_hovered, _held, close_pressed = ctx.button_behavior(close_box, (*item_id, "close"))
    hovered, _held, pressed = ctx.button_behavior(
        (box[0], box[1], box[2] - close_width, box[3]), item_id)
    if pressed or flags & TabItemFlags.SET_SELECTED:
        store["selected"] = item_id
    selected = store.setdefault("selected", item_id) == item_id
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.TAB_SELECTED if selected else Col.TAB), 0.0)
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), _col(Col.TEXT),
                      shown)
    if on_close is not None:
        if close_hovered:
            ctx.draw.add_rect_filled((close_box[0], close_box[1]),
                (close_box[0] + close_box[2], close_box[1] + close_box[3]), _col(Col.BUTTON_HOVERED))
        ctx.draw.add_text((close_box[0] + ctx.style.frame_padding[0],
                          close_box[1] + ctx.style.frame_padding[1]), _col(Col.TEXT), "×")
        if close_pressed:
            on_close()
    same_line()
    if selected and layouts:
        ctx.layout = layouts[-1]["body"]
    return selected


def end_tab_item() -> None:
    ctx = _ctx()
    layouts = getattr(ctx, "_tabbar_layouts", None)
    if layouts:
        ctx.layout = layouts[-1]["header"]


# -- combos and list boxes --------------------------------------------------- #
def begin_combo(label: str, preview: str) -> bool:
    ctx = _ctx()
    item_id = ctx.get_id(label)
    store = ctx.get_storage(item_id)
    box = ctx.layout.row(height=_frame_height(ctx),
                         width=ctx.take_next_item_width(None))
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    if pressed:
        store["open"] = not store.get("open", False)
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.FRAME_BG_HOVERED if hovered else Col.FRAME_BG),
                             ctx.style.frame_rounding)
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), _col(Col.TEXT),
                      str(preview))
    if store.get("open"):
        ctx.push_id(label)
        indent()
        return True
    return False


def end_combo() -> None:
    unindent()
    _ctx().pop_id()


def begin_list_box(label: str, size=None) -> bool:
    ctx = _ctx()
    ctx.push_id(label)
    indent()
    return True


def end_list_box() -> None:
    unindent()
    _ctx().pop_id()


def list_box(label: str, current: int, items) -> tuple[bool, int]:
    changed = False
    begin_list_box(label)
    for index, item in enumerate(items):
        if selectable(f"{item}##{index}", index == current):
            current, changed = index, True
    end_list_box()
    return (changed, current)


# -- tables ------------------------------------------------------------------ #
class TableFlags:
    """``ImGuiTableFlags_``: the subset that changes geometry or behaviour."""

    NONE = 0
    RESIZABLE = 1 << 0
    REORDERABLE = 1 << 1
    HIDEABLE = 1 << 2
    SORTABLE = 1 << 3
    ROW_BG = 1 << 6
    BORDERS_INNER_V = 1 << 8
    BORDERS_OUTER_V = 1 << 9
    BORDERS_INNER_H = 1 << 10
    BORDERS_OUTER_H = 1 << 11
    BORDERS_V = BORDERS_INNER_V | BORDERS_OUTER_V
    BORDERS_H = BORDERS_INNER_H | BORDERS_OUTER_H
    BORDERS = BORDERS_V | BORDERS_H
    SIZING_FIXED_FIT = 1 << 13
    SIZING_FIXED_SAME = 2 << 13
    SIZING_STRETCH_PROP = 3 << 13
    SIZING_STRETCH_SAME = 4 << 13
    SIZING_MASK = 7 << 13
    SCROLL_X = 1 << 16
    SCROLL_Y = 1 << 17
    # The reference's bit. emtk has no .ini to save to, so it changes
    # nothing here -- but a port that ORs it in must still resolve the name,
    # and an AttributeError in a flag expression takes the whole table with
    # it before a single row is drawn.
    NO_SAVED_SETTINGS = 1 << 4
    CONTEXT_MENU_IN_BODY = 1 << 5
    NO_PAD_INNER_X = 1 << 22
    NO_HOST_EXTEND_X = 1 << 24
    NO_HOST_EXTEND_Y = 1 << 25
    HIGHLIGHT_HOVERED_COLUMN = 1 << 26


class TableColumnFlags:
    """``ImGuiTableColumnFlags_``."""

    NONE = 0
    DEFAULT_HIDE = 1 << 1
    DEFAULT_SORT = 1 << 2
    WIDTH_STRETCH = 1 << 3
    WIDTH_FIXED = 1 << 4
    NO_RESIZE = 1 << 5
    NO_REORDER = 1 << 6
    NO_HIDE = 1 << 7
    NO_SORT = 1 << 9
    IS_ENABLED = 1 << 24
    IS_VISIBLE = 1 << 25
    IS_SORTED = 1 << 26
    IS_HOVERED = 1 << 27


class TableBgTarget:
    """``ImGuiTableBgTarget_``."""

    NONE = 0
    ROW_BG0 = 1
    ROW_BG1 = 2
    CELL_BG = 3


class SortSpec:
    """One entry of ``ImGuiTableSortSpecs``."""

    def __init__(self, column_index: int, ascending: bool) -> None:
        self.column_index = int(column_index)
        self.column_user_id = int(column_index)
        self.sort_direction = 1 if ascending else 2
        self.ascending = bool(ascending)


class SortSpecs:
    """``ImGuiTableSortSpecs``: what a header click asked for."""

    def __init__(self, specs, dirty: bool) -> None:
        self.specs = list(specs)
        self.specs_count = len(self.specs)
        self.specs_dirty = bool(dirty)


class _Column:
    """One column's geometry and state, which the reference calls ImGuiTableColumn."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.name = ""
        self.flags = 0
        self.init_width = 0.0        # fixed width, or a stretch weight
        self.width = 0.0             # resolved this frame
        self.offset = 0.0            # from the table's left edge
        self.enabled = True
        self.display_order = index
        self.user_width: float | None = None   # set by dragging a border


class _Table:
    """One open table.

    emtk's tables used to be the layout's equal columns with a stack on top,
    which is why a third of the reference's Tables sections had nothing to port
    on to. This is the geometry the rest of them need: a width per column --
    fixed, or a share of what is left -- an order that can be changed, columns
    that can be switched off, padding, borders, an outer box, and a header row
    that can be clicked to sort or dragged to resize.
    """

    def __init__(self, name: str, count: int, flags: int, box) -> None:
        self.name = name
        self.flags = int(flags)
        self.columns = [_Column(i) for i in range(int(count))]
        self.box = box
        self.setup_done = False
        self.started = False          # a cell has been placed in this row
        self.row = -1
        self.row_top = box[1]
        self.row_height = 0.0
        self.current = -1
        self.cell_padding = (4.0, 2.0)
        self.freeze = (0, 0)
        self.bg: dict = {}
        self.sort: SortSpecs | None = None
        self.header_boxes: list = []
        #: The layout box in force when the table opened. Placing a cell
        #: narrows the layout to that column, so `EndTable` has to put the
        #: whole box back -- restoring only the cursor left everything after a
        #: table as wide as its last cell, and a *nested* table left the outer
        #: one narrowed too.
        self.saved_layout: tuple | None = None

    # -- geometry ---------------------------------------------------------- #
    def visible_columns(self) -> list:
        return [c for c in sorted(self.columns, key=lambda c: c.display_order)
                if c.enabled]

    def resolve(self) -> None:
        """Work out each column's width and offset. ``ImGui::TableUpdateLayout``."""
        self.setup_done = True
        columns = self.visible_columns()
        if not columns:
            return
        sizing = self.flags & TableFlags.SIZING_MASK
        available = max(self.box[2], 1.0)
        fixed, stretch = [], []
        for column in columns:
            if column.user_width is not None:
                fixed.append(column)
            elif column.flags & TableColumnFlags.WIDTH_FIXED:
                fixed.append(column)
            elif column.flags & TableColumnFlags.WIDTH_STRETCH:
                stretch.append(column)
            elif sizing in (TableFlags.SIZING_FIXED_FIT, TableFlags.SIZING_FIXED_SAME):
                fixed.append(column)
            else:
                stretch.append(column)

        used = 0.0
        for column in fixed:
            column.width = float(
                column.user_width if column.user_width is not None
                else (column.init_width or available / len(columns)))
            used += column.width
        if stretch:
            weights = [c.init_width or 1.0 for c in stretch]
            total = sum(weights) or 1.0
            room = max(available - used, len(stretch) * 8.0)
            for column, weight in zip(stretch, weights):
                column.width = room * weight / total
        offset = 0.0
        for column in columns:
            column.offset = offset
            offset += column.width


def _tables() -> list:
    """The open tables, innermost last.

    A stack, because the demo nests one table inside a cell of another
    (``table_nested1`` / ``table_nested2``). Held in a single bucket, the inner
    table's column count and headers overwrote the outer's, and the outer came
    back from `EndTable` believing it had the inner one's shape.
    """
    return get_current_context().state(("table",)).setdefault("stack", [])


def _table():
    stack = _tables()
    return stack[-1] if stack else None


def _table_shared(name: str) -> dict:
    """State two tables with the same id share (``Synced instances``)."""
    return get_current_context().state(("table_shared", name))


def begin_table(str_id: str, column_count: int, flags: int = 0, size=None) -> bool:
    """``BeginTable``."""
    ctx = get_current_context()
    ctx.push_id(str_id)
    x, y = ctx.layout.cursor
    width = (size[0] if size and size[0] else ctx.layout.avail()[0])
    height = (size[1] if size and len(size) > 1 and size[1] else 0.0)
    table = _Table(str_id, column_count, flags, (x, y, width, height))
    lay = ctx.layout
    # The box *and* its origin and extents: after a cursor move (any item
    # placed by ``set_cursor_screen_pos``, a previous table) ``lay.y`` is the
    # moved line start, not the box top, and restoring it as the origin made
    # every following ``avail()`` report room below the box's real bottom.
    table.saved_layout = (lay.x, lay.y, lay.w, lay.h,
                          lay._origin_x, lay._origin_y, lay._max_x, lay._max_y)
    shared = _table_shared(str_id)
    for column in table.columns:
        stored = shared.get(("width", column.index))
        if stored is not None:
            column.user_width = stored
        order = shared.get(("order", column.index))
        if order is not None:
            column.display_order = order
        enabled = shared.get(("enabled", column.index))
        if enabled is not None:
            column.enabled = enabled
    table.sort = shared.get("sort")
    _tables().append(table)
    return True


def end_table() -> None:
    """``EndTable``: leave the cursor below the whole table."""
    ctx = get_current_context()
    stack = _tables()
    if not stack:
        ctx.pop_id()
        return
    table = stack.pop()
    if table.started:
        table.row_top += table.row_height + table.cell_padding[1] * 2.0
    if table.flags & (TableFlags.BORDERS_OUTER_V | TableFlags.BORDERS_INNER_V):
        _table_borders(table)
    if table.saved_layout is not None:
        x, y, w, h, origin_x, origin_y, max_x, max_y = table.saved_layout
        lay = ctx.layout
        lay.reset(x, y, w, h)
        lay._origin_x, lay._origin_y = origin_x, origin_y
        lay._max_x, lay._max_y = max(lay._max_x, max_x), max(lay._max_y, max_y)
    set_cursor_screen_pos((table.box[0], max(table.row_top, table.box[1])))
    ctx.pop_id()


def _table_borders(table: _Table) -> None:
    ctx = get_current_context()
    top, bottom = table.box[1], max(table.row_top, table.box[1])
    colour = _col(Col.BORDER)
    columns = table.visible_columns()
    height = max(bottom - top, 1.0)
    # `add_line_v`, not `add_line`: a rule between columns is axis-aligned by
    # construction, so it is one rectangle rather than two triangles.
    for index, column in enumerate(columns):
        if index == 0 and not (table.flags & TableFlags.BORDERS_OUTER_V):
            continue
        ctx.draw.add_line_v((table.box[0] + column.offset, top), height, colour, 1.0)
    if table.flags & TableFlags.BORDERS_OUTER_V and columns:
        right = table.box[0] + columns[-1].offset + columns[-1].width
        ctx.draw.add_line_v((right, top), height, colour, 1.0)


def table_setup_column(label: str, flags: int = 0,
                       init_width_or_weight: float = 0.0) -> None:
    """``TableSetupColumn``."""
    table = _table()
    if table is None:
        return
    for column in table.columns:
        if not column.name:
            column.name = label
            column.flags = int(flags)
            column.init_width = float(init_width_or_weight)
            if flags & TableColumnFlags.DEFAULT_HIDE:
                shared = _table_shared(table.name)
                if shared.get(("enabled", column.index)) is None:
                    column.enabled = False
            return


def table_setup_scroll_freeze(cols: int, rows: int) -> None:
    table = _table()
    if table is not None:
        table.freeze = (int(cols), int(rows))


def _place(table: _Table, index: int) -> None:
    """Put the cursor in column *index* of the current row."""
    if not table.setup_done:
        table.resolve()
    columns = table.visible_columns()
    if not columns:
        return
    index = max(0, min(index, len(columns) - 1))
    column = columns[index]
    table.current = index
    padding = table.cell_padding
    set_cursor_screen_pos((table.box[0] + column.offset + padding[0],
                           table.row_top + padding[1]))
    layout = get_current_context().layout
    layout.reset(table.box[0] + column.offset + padding[0],
                 table.row_top + padding[1],
                 max(column.width - padding[0] * 2.0, 1.0),
                 max(layout.h, 1.0))


def _close_cell(table: _Table) -> None:
    """Remember how tall the cell that was just filled turned out."""
    layout = get_current_context().layout
    table.row_height = max(table.row_height,
                           layout.cursor[1] - table.row_top - table.cell_padding[1])


def table_next_row(row_flags: int = 0, min_height: float = 0.0) -> None:
    """``TableNextRow``: finish this row and open the next."""
    table = _table()
    if table is None:
        return
    if table.started:
        _close_cell(table)
        table.row_top += table.row_height + table.cell_padding[1] * 2.0
    table.row_height = max(float(min_height), 0.0)
    table.row = table.row + 1
    table.started = False
    table.current = -1


def table_next_column() -> bool:
    """``TableNextColumn``: the next cell, starting the row if none is open."""
    table = _table()
    if table is None:
        return False
    if not table.started:
        table.started = True
        if table.row < 0:
            table.row = 0
        _place(table, 0)
        return _column_visible(table, 0)
    _close_cell(table)
    nxt = table.current + 1
    if nxt >= len(table.visible_columns()):
        table_next_row()
        table.started = True
        _place(table, 0)
        return _column_visible(table, 0)
    _place(table, nxt)
    return _column_visible(table, nxt)


def _column_visible(table: _Table, index: int) -> bool:
    columns = table.visible_columns()
    return 0 <= index < len(columns) and columns[index].enabled


def table_set_column_index(index: int) -> bool:
    """``TableSetColumnIndex``."""
    table = _table()
    if table is None:
        return False
    if table.started:
        _close_cell(table)
    else:
        table.started = True
        if table.row < 0:
            table.row = 0
    _place(table, int(index))
    return _column_visible(table, int(index))


def table_headers_row() -> None:
    """``TableHeadersRow``: a header per column, clickable and draggable."""
    table = _table()
    if table is None:
        return
    table.header_boxes = []
    table_next_row()
    for index, column in enumerate(table.visible_columns()):
        table_set_column_index(index)
        table_header(column.name)


def table_header(label: str) -> None:
    """``TableHeader``: the name, plus sorting and resizing behaviour."""
    ctx = get_current_context()
    label = tr(label)
    table = _table()
    if table is None:
        text_colored(_col(Col.TEXT_DISABLED), label)
        return
    columns = table.visible_columns()
    column = columns[table.current] if 0 <= table.current < len(columns) else None
    height = _frame_height(ctx)
    box = ctx.layout.row(height=height)
    hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id("##hdr" + label))
    if column is not None:
        table.header_boxes.append((column, box))
    if hovered:
        ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                 _col(Col.HEADER_HOVERED), 0.0)
    mark = ""
    if table.sort and table.sort.specs and column is not None:
        spec = table.sort.specs[0]
        if spec.column_index == column.index:
            mark = " ^" if spec.ascending else " v"
    ctx.draw.add_text((box[0], box[1]), _col(Col.TEXT), label + mark)

    if pressed and column is not None and (table.flags & TableFlags.SORTABLE) \
            and not (column.flags & TableColumnFlags.NO_SORT):
        ascending = True
        if table.sort and table.sort.specs and \
                table.sort.specs[0].column_index == column.index:
            ascending = not table.sort.specs[0].ascending
        table.sort = SortSpecs([SortSpec(column.index, ascending)], True)
        _table_shared(table.name)["sort"] = table.sort

    # The border between this column and the next is the resize grip.
    if column is not None and (table.flags & TableFlags.RESIZABLE) \
            and not (column.flags & TableColumnFlags.NO_RESIZE):
        _resize_grip(table, column, box)


def _resize_grip(table: _Table, column: _Column, header_box) -> None:
    """A few pixels on the column's right edge, dragged to set its width."""
    ctx = get_current_context()
    edge = table.box[0] + column.offset + column.width
    grip = (edge - 3.0, header_box[1], 6.0, header_box[3])
    ctx.set_next_item_allow_overlap()
    _hovered, held, _pressed = ctx.button_behavior(
        grip, ctx.get_id("##resize%d" % column.index))
    if held:
        width = max(ctx.io.mouse_pos[0] - (table.box[0] + column.offset), 12.0)
        column.user_width = width
        _table_shared(table.name)[("width", column.index)] = width
        table.resolve()


def table_angled_headers_row() -> None:
    """``TableAngledHeadersRow``: the same names, drawn at an angle.

    The Painter grew an optional ``text_rotated``; one that has none draws them
    flat, which is the reference's own fallback when the font atlas cannot
    rotate.
    """
    table = _table()
    if table is None:
        return
    ctx = get_current_context()
    table_next_row()
    for index, column in enumerate(table.visible_columns()):
        table_set_column_index(index)
        box = ctx.layout.row(height=_frame_height(ctx))
        ctx.item_add(box)
        _rotated_text(ctx, (box[0], box[1]), column.name, -0.6, _col(Col.TEXT))


def _rotated_text(ctx, pos, string, radians, colour) -> None:
    """Through the protocol's ``text_rotated(x, y, w, h, align, string,
    colour, degrees)``. This called it as ``(x, y, string, radians, colour)``,
    a spelling no shipped painter had, so a painter that *could* rotate text
    raised here instead."""
    import math

    from .painter import ALIGN_LEFT, ALIGN_VCENTER
    op = getattr(ctx.p, "text_rotated", None)
    if callable(op):
        w, h = ctx.draw.calc_text_size(string)
        op(pos[0], pos[1], w, h, ALIGN_LEFT | ALIGN_VCENTER, string, colour,
           math.degrees(radians))
        return
    ctx.draw.add_text(pos, colour, string)


def table_set_bg_color(target: int, colour, column: int = -1) -> None:
    """``TableSetBgColor``: paint a row or a cell behind its contents."""
    ctx = get_current_context()
    table = _table()
    if table is None:
        return
    columns = table.visible_columns()
    if target == TableBgTarget.CELL_BG and 0 <= table.current < len(columns):
        which = columns[table.current]
        x = table.box[0] + which.offset
        ctx.draw.add_rect_filled(
            (x, table.row_top),
            (x + which.width, table.row_top + max(table.row_height,
                                                  _frame_height(ctx))),
            colour, 0.0)
        return
    right = table.box[0] + (columns[-1].offset + columns[-1].width if columns
                            else table.box[2])
    ctx.draw.add_rect_filled(
        (table.box[0], table.row_top),
        (right, table.row_top + max(table.row_height, _frame_height(ctx))),
        colour, 0.0)


def table_set_column_enabled(index: int, enabled: bool) -> None:
    """``TableSetColumnEnabled``: hide a column, or bring it back."""
    table = _table()
    if table is None:
        return
    if 0 <= int(index) < len(table.columns):
        table.columns[int(index)].enabled = bool(enabled)
        _table_shared(table.name)[("enabled", int(index))] = bool(enabled)
        table.resolve()


def table_set_column_order(index: int, position: int) -> None:
    """Reorder a column. The reference does it by dragging a header."""
    table = _table()
    if table is None:
        return
    table.columns[int(index)].display_order = int(position)
    _table_shared(table.name)[("order", int(index))] = int(position)
    table.resolve()


def table_get_sort_specs():
    """``TableGetSortSpecs``: what the last header click asked for, or None."""
    table = _table()
    return None if table is None else table.sort


def table_get_column_flags(index: int = -1) -> int:
    """``TableGetColumnFlags``."""
    table = _table()
    if table is None:
        return 0
    columns = table.visible_columns()
    which = table.current if index < 0 else int(index)
    if not (0 <= which < len(columns)):
        return 0
    column = columns[which]
    flags = column.flags
    if column.enabled:
        flags |= TableColumnFlags.IS_ENABLED | TableColumnFlags.IS_VISIBLE
    if table.sort and table.sort.specs and \
            table.sort.specs[0].column_index == column.index:
        flags |= TableColumnFlags.IS_SORTED
    return flags


def table_get_hovered_column() -> int:
    """``TableGetHoveredColumn``: which column the pointer is over, or -1."""
    ctx = get_current_context()
    table = _table()
    if table is None:
        return -1
    x, y = ctx.io.mouse_pos
    if not (table.box[0] <= x < table.box[0] + table.box[2]):
        return -1
    for index, column in enumerate(table.visible_columns()):
        left = table.box[0] + column.offset
        if left <= x < left + column.width:
            return index
    return -1


def table_get_row_index() -> int:
    table = _table()
    return 0 if table is None else max(table.row, 0)


def table_get_column_name(index: int = -1) -> str:
    table = _table()
    if table is None:
        return ""
    columns = table.visible_columns()
    which = table.current if index < 0 else int(index)
    return columns[which].name if 0 <= which < len(columns) else ""


def table_get_column_count() -> int:
    """``TableGetColumnCount``."""
    table = _table()
    if table is None:
        return _ctx().layout.column_count
    return len(table.visible_columns())


def table_get_column_index() -> int:
    """``TableGetColumnIndex``."""
    table = _table()
    if table is None:
        return _ctx().layout.column_index
    return max(table.current, 0)


__all__ += [
    "get_content_region_avail", "get_line_avail", "get_cursor_pos", "get_cursor_pos_x",
    "get_cursor_pos_y", "set_cursor_pos", "get_item_rect_min",
    "get_item_rect_max", "get_item_rect_size", "get_window_pos",
    "get_window_size", "get_window_width", "get_window_height",
    "get_color_u32", "get_mouse_pos", "get_mouse_drag_delta", "is_mouse_down",
    "is_mouse_clicked", "is_mouse_released", "is_mouse_double_clicked",
    "is_mouse_dragging", "is_mouse_hovering_rect", "is_any_mouse_down",
    "is_item_activated", "is_item_deactivated", "is_item_visible",
    "is_item_focused", "is_any_item_hovered", "is_any_item_active",
    "is_window_hovered", "is_window_focused", "push_item_width",
    "pop_item_width", "push_style_var", "pop_style_var", "push_clip_rect",
    "pop_clip_rect", "begin_disabled", "end_disabled", "text_unformatted",
    "set_next_item_open", "tree_node_ex", "tree_push", "begin_tooltip",
    "end_tooltip", "begin_item_tooltip", "open_popup", "begin_popup",
    "end_popup", "close_current_popup", "is_popup_open", "begin_menu_bar",
    "end_menu_bar", "begin_main_menu_bar", "end_main_menu_bar", "begin_menu",
    "end_menu", "menu_item", "begin_tab_bar", "end_tab_bar", "begin_tab_item",
    "end_tab_item", "begin_combo", "end_combo", "begin_list_box",
    "end_list_box", "list_box", "begin_table", "end_table",
    "table_setup_column", "table_headers_row", "table_next_row",
    "table_next_column", "table_set_column_index", "table_get_column_count",
    "table_get_column_index",
]


# --------------------------------------------------------------------------- #
# The N-component variants
# --------------------------------------------------------------------------- #
#
# `DragFloat3`, `SliderInt2`, `InputFloat4`... In C++ these take a pointer to
# an array; here they take and return a sequence. They are all the scalar
# widget in a `PushID` loop, which is what they are in `imgui_widgets.cpp` too
# (`DragScalarN`), so they are written once and named the reference's way.


def _componentwise(widget, label, values, *args, **kwargs):
    ctx = get_current_context()
    ctx.push_id(label)
    out, changed = list(values), False
    inner = ctx.style.item_inner_spacing[0]
    for index in range(len(out)):
        edited, out[index] = widget(f"##{index}", out[index], *args, **kwargs)
        changed = changed or edited
        same_line(0.0, inner)
    ctx.pop_id()
    shown = _visible_label(label)
    if shown:
        text(shown)
    else:
        new_line()
    return (changed, tuple(out))


def drag_float2(label, v, speed=1.0, v_min=None, v_max=None, fmt="%.3f"):
    return _componentwise(drag_float, label, v[:2], speed, v_min, v_max, fmt)


def drag_float3(label, v, speed=1.0, v_min=None, v_max=None, fmt="%.3f"):
    return _componentwise(drag_float, label, v[:3], speed, v_min, v_max, fmt)


def drag_float4(label, v, speed=1.0, v_min=None, v_max=None, fmt="%.3f"):
    return _componentwise(drag_float, label, v[:4], speed, v_min, v_max, fmt)


def drag_int2(label, v, speed=1.0, v_min=None, v_max=None, fmt="%d"):
    return _componentwise(drag_int, label, v[:2], speed, v_min, v_max, fmt)


def drag_int3(label, v, speed=1.0, v_min=None, v_max=None, fmt="%d"):
    return _componentwise(drag_int, label, v[:3], speed, v_min, v_max, fmt)


def drag_int4(label, v, speed=1.0, v_min=None, v_max=None, fmt="%d"):
    return _componentwise(drag_int, label, v[:4], speed, v_min, v_max, fmt)


def slider_float2(label, v, v_min, v_max, fmt="%.3f"):
    return _componentwise(slider_float, label, v[:2], v_min, v_max, fmt)


def slider_float3(label, v, v_min, v_max, fmt="%.3f"):
    return _componentwise(slider_float, label, v[:3], v_min, v_max, fmt)


def slider_float4(label, v, v_min, v_max, fmt="%.3f"):
    return _componentwise(slider_float, label, v[:4], v_min, v_max, fmt)


def slider_int2(label, v, v_min, v_max, fmt="%d"):
    return _componentwise(slider_int, label, v[:2], v_min, v_max, fmt)


def slider_int3(label, v, v_min, v_max, fmt="%d"):
    return _componentwise(slider_int, label, v[:3], v_min, v_max, fmt)


def slider_int4(label, v, v_min, v_max, fmt="%d"):
    return _componentwise(slider_int, label, v[:4], v_min, v_max, fmt)


def input_float2(label, v, fmt="%.3f"):
    return _componentwise(input_float, label, v[:2], 0.0, fmt)


def input_float3(label, v, fmt="%.3f"):
    return _componentwise(input_float, label, v[:3], 0.0, fmt)


def input_float4(label, v, fmt="%.3f"):
    return _componentwise(input_float, label, v[:4], 0.0, fmt)


def input_int2(label, v):
    return _componentwise(input_int, label, v[:2], 0)


def input_int3(label, v):
    return _componentwise(input_int, label, v[:3], 0)


def input_int4(label, v):
    return _componentwise(input_int, label, v[:4], 0)


def input_double(label, v, step=0.0, step_fast=0.0, fmt="%.6f"):
    return input_float(label, v, step, step_fast, fmt)


def drag_float_range2(label, v_min, v_max, speed=1.0, low=None, high=None,
                      fmt="%.3f"):
    """``DragFloatRange2``: two drags that cannot cross."""
    ctx = get_current_context()
    ctx.push_id(label)
    a_changed, v_min = drag_float("##min", v_min, speed, low, high, fmt)
    same_line(0.0, ctx.style.item_inner_spacing[0])
    b_changed, v_max = drag_float("##max", v_max, speed, low, high, fmt)
    ctx.pop_id()
    same_line(0.0, ctx.style.item_inner_spacing[0])
    text(_visible_label(label))
    v_min = min(v_min, v_max)
    v_max = max(v_min, v_max)
    return (a_changed or b_changed, v_min, v_max)


def drag_int_range2(label, v_min, v_max, speed=1.0, low=None, high=None,
                    fmt="%d"):
    changed, a, b = drag_float_range2(label, float(v_min), float(v_max), speed,
                                      low, high, fmt)
    return (changed, int(round(a)), int(round(b)))


#: `*Scalar` in C++ is the type-erased form the typed ones call. Python is
#: already type-erased, so these dispatch on the value handed in.
#: The reference's scalar widgets take an ``ImGuiDataType`` *second*, before
#: the value: ``SliderScalar(label, data_type, p_data, p_min, p_max, ...)``.
#: emtk infers the type from the value instead, which is the right instinct
#: in Python and the wrong *signature* -- a port hands its arguments over
#: positionally, so the data type landed in the value and the value in the
#: minimum. Both spellings are accepted: ``im.DataType`` members are strings
#: and a slider's value never is, so which was passed is unambiguous.
def _without_data_type(args: tuple) -> tuple:
    return args[1:] if args and isinstance(args[0], str) else args


def _arg(args: tuple, i: int, kw: dict, name: str, default=None):
    if len(args) > i:
        return args[i]
    return kw.get(name, default)


def drag_scalar(label, *args, **kw):
    """``ImGui::DragScalar``, with or without the leading data type.

    Trailing ``ImGuiSliderFlags`` are accepted and ignored: emtk's drags are
    linear, so ``LOGARITHMIC`` would change the picture and there is nothing
    here to change it with. Said out loud rather than left as a silent
    difference from the C++.
    """
    args = _without_data_type(args)
    v = _arg(args, 0, kw, "v")
    speed = _arg(args, 1, kw, "speed", 1.0)
    v_min = _arg(args, 2, kw, "v_min")
    v_max = _arg(args, 3, kw, "v_max")
    fmt = _arg(args, 4, kw, "fmt")
    if isinstance(v, int):
        return drag_int(label, v, speed, v_min, v_max, fmt or "%d")
    return drag_float(label, v, speed, v_min, v_max, fmt or "%.3f")


def slider_scalar(label, *args, **kw):
    """``ImGui::SliderScalar``, with or without the leading data type.

    Trailing ``ImGuiSliderFlags`` are forwarded: ``LOGARITHMIC``,
    ``NO_ROUND_TO_FORMAT``, ``ALWAYS_CLAMP`` and ``NO_INPUT`` change the
    behaviour (see :func:`slider_float`), the rest are accepted and ignored --
    said out loud rather than left as a silent difference from the C++.
    """
    args = _without_data_type(args)
    v = _arg(args, 0, kw, "v")
    v_min = _arg(args, 1, kw, "v_min")
    v_max = _arg(args, 2, kw, "v_max")
    fmt = _arg(args, 3, kw, "fmt")
    flags = _arg(args, 4, kw, "flags", 0)
    if isinstance(v, int):
        return slider_int(label, v, int(v_min), int(v_max), fmt or "%d", flags)
    return slider_float(label, v, v_min, v_max, fmt or "%.3f", flags)


def input_scalar(label, *args, **kw):
    """``ImGui::InputScalar``, with or without the leading data type."""
    args = _without_data_type(args)
    v = _arg(args, 0, kw, "v")
    step = _arg(args, 1, kw, "step")
    step_fast = _arg(args, 2, kw, "step_fast")
    fmt = _arg(args, 3, kw, "fmt")
    if isinstance(v, int):
        return input_int(label, v, int(step or 1), int(step_fast or 100))
    return input_float(label, v, float(step or 0.0), float(step_fast or 0.0),
                       fmt or "%.3f")


def drag_scalar_n(label, values, speed=1.0, v_min=None, v_max=None, fmt=None):
    return _componentwise(drag_scalar, label, values, speed, v_min, v_max, fmt)


def slider_scalar_n(label, values, v_min, v_max, fmt=None):
    return _componentwise(slider_scalar, label, values, v_min, v_max, fmt)


def input_scalar_n(label, values, step=None):
    return _componentwise(input_scalar, label, values, step)


def v_slider_float(label, size, v, v_min, v_max, fmt="%.3f"):
    """``VSliderFloat``: the same slider, stood on end."""
    ctx = get_current_context()
    box = ctx.layout.row(height=size[1], width=size[0])
    item_id = ctx.get_id(label)
    hovered, held, _pressed = ctx.button_behavior(box, item_id)
    span = float(v_max) - float(v_min)
    if held and span:
        t = 1.0 - (ctx.io.mouse_pos[1] - box[1]) / max(box[3], 1.0)
        v = float(v_min) + max(0.0, min(1.0, t)) * span
    v = max(v_min, min(v_max, v))
    fraction = 0.0 if not span else (float(v) - float(v_min)) / span
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.FRAME_BG_HOVERED if hovered else Col.FRAME_BG),
                             ctx.style.frame_rounding)
    grab_h = max(ctx.style.grab_min_size, box[3] * 0.06)
    grab_y = box[1] + (1.0 - fraction) * max(box[3] - grab_h, 0.0)
    ctx.draw.add_rect_filled((box[0], grab_y), (box[0] + box[2], grab_y + grab_h),
                             _col(Col.SLIDER_GRAB_ACTIVE if held else Col.SLIDER_GRAB),
                             ctx.style.grab_rounding)
    return (bool(held), v)


def v_slider_int(label, size, v, v_min, v_max, fmt="%d"):
    changed, value = v_slider_float(label, size, float(v), float(v_min),
                                    float(v_max), fmt)
    return (changed, int(round(value)))


def v_slider_scalar(label, size, v, v_min, v_max, fmt=None):
    if isinstance(v, int):
        return v_slider_int(label, size, v, int(v_min), int(v_max), fmt or "%d")
    return v_slider_float(label, size, v, v_min, v_max, fmt or "%.3f")


# --------------------------------------------------------------------------- #
# Colour conversion -- plain arithmetic, and the reference's exactly
# --------------------------------------------------------------------------- #
def color_convert_rgb_to_hsv(r: float, g: float, b: float) -> tuple:
    """``ColorConvertRGBtoHSV``. Channels in 0..1, as in C++."""
    k = 0.0
    if g < b:
        g, b, k = b, g, -1.0
    if r < g:
        r, g, k = g, r, -2.0 / 6.0 - k
    chroma = r - min(g, b)
    h = abs(k + (g - b) / (6.0 * chroma + 1e-20))
    s = chroma / (r + 1e-20)
    return (h, s, r)


def color_convert_hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """``ColorConvertHSVtoRGB``."""
    if s == 0.0:
        return (v, v, v)
    h = (h % 1.0) * 6.0
    i = int(h)
    f = h - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return [(v, t, p), (q, v, p), (p, v, t),
            (p, q, v), (t, p, v), (v, p, q)][i % 6]


def color_convert_u32_to_float4(colour) -> tuple:
    rgba = tuple(colour) if len(colour) == 4 else (*colour, 255)
    return tuple(c / 255.0 for c in rgba)


def color_convert_float4_to_u32(rgba) -> tuple:
    values = list(rgba) + [1.0] * (4 - len(rgba))
    return tuple(int(max(0.0, min(1.0, c)) * 255.0 + 0.5) for c in values[:4])


def color_picker3(label: str, col) -> tuple[bool, tuple]:
    """``ColorPicker3``: hue, saturation and value, as three sliders.

    Not the reference's square-and-wheel picker -- that needs a per-pixel
    gradient the painter has no operation for. It edits the same colour in the
    same space, and says so rather than pretending.
    """
    ctx = get_current_context()
    ctx.push_id(label)
    r, g, b = (c / 255.0 for c in col[:3])
    h, s, v = color_convert_rgb_to_hsv(r, g, b)
    changed = False
    for name, value, setter in (("H", h, 0), ("S", s, 1), ("V", v, 2)):
        edited, new = slider_float(f"{name}##{name}", value, 0.0, 1.0, "%.2f")
        changed = changed or edited
        h, s, v = [new if i == setter else old
                   for i, old in enumerate((h, s, v))]
    ctx.pop_id()
    out = tuple(int(c * 255 + 0.5) for c in color_convert_hsv_to_rgb(h, s, v))
    color_button(f"##{label}-preview", out)
    same_line(0.0, ctx.style.item_inner_spacing[0])
    text(_visible_label(label))
    return (changed, out)


def color_picker4(label: str, col) -> tuple[bool, tuple]:
    changed, rgb = color_picker3(label, col[:3])
    return (changed, (*rgb, col[3] if len(col) > 3 else 255))


# --------------------------------------------------------------------------- #
# Scrolling, cursor, windows
# --------------------------------------------------------------------------- #
def _window():
    ctx = get_current_context()
    return ctx.current_window


def get_scroll_x() -> float:
    window = _window()
    return window.scroll[0] if window else 0.0


def get_scroll_y() -> float:
    ctx = get_current_context()
    if ctx._child:
        entry = ctx._child[-1]
        if len(entry) >= 3 and isinstance(entry[2], dict):
            return float(entry[2].get("scroll_y", 0.0))
    window = _window()
    return window.scroll[1] if window else 0.0


def set_scroll_x(value: float) -> None:
    window = _window()
    if window:
        window.scroll = (float(value), window.scroll[1])


def set_scroll_y(value: float) -> None:
    ctx = get_current_context()
    if ctx._child:
        entry = ctx._child[-1]
        if len(entry) >= 3 and isinstance(entry[2], dict):
            entry[2]["scroll_y"] = float(value)
            return
    window = _window()
    if window:
        window.scroll = (window.scroll[0], float(value))


def set_child_scroll_y(child_id: str, value: float) -> None:
    """Explicitly set scroll_y on a child container by ID."""
    ctx = get_current_context()
    state = ctx.storage.setdefault(child_id, {})
    state["scroll_y"] = float(value)


def get_scroll_max_x() -> float:
    window = _window()
    return max(window.content_size[0] - window.box[2], 0.0) if window else 0.0


def get_scroll_max_y() -> float:
    ctx = get_current_context()
    if ctx._child:
        entry = ctx._child[-1]
        if len(entry) >= 3 and isinstance(entry[2], dict):
            box = entry[1]
            state = entry[2]
            content_h = state.get("content_height", box[3])
            return max(content_h - box[3], 0.0)
    window = _window()
    return max(window.content_size[1] - window.box[3], 0.0) if window else 0.0


def set_scroll_here_x(centre: float = 0.5) -> None:
    set_scroll_x(get_scroll_max_x() * centre)


def set_scroll_here_y(centre: float = 0.5) -> None:
    set_scroll_y(get_scroll_max_y() * centre)



def set_scroll_from_pos_x(local_x: float, centre: float = 0.5) -> None:
    set_scroll_x(max(local_x - get_window_size()[0] * centre, 0.0))


def set_scroll_from_pos_y(local_y: float, centre: float = 0.5) -> None:
    set_scroll_y(max(local_y - get_window_size()[1] * centre, 0.0))


def set_cursor_pos_x(x: float) -> None:
    layout = get_current_context().layout
    set_cursor_screen_pos((x, layout.cursor[1]))


def set_cursor_pos_y(y: float) -> None:
    layout = get_current_context().layout
    set_cursor_screen_pos((layout.cursor[0], y))


def get_cursor_start_pos() -> tuple:
    box = get_current_context().box
    return (box[0], box[1])


def calc_item_width() -> float:
    """``CalcItemWidth``: how wide the next framed widget will be."""
    ctx = get_current_context()
    width = ctx.take_next_item_width(ctx.layout.avail()[0])
    return float(ctx.layout.avail()[0] if width is None else width)


def is_window_appearing() -> bool:
    window = _window()
    return bool(window and not window.was_active)


def is_window_collapsed() -> bool:
    return False


def set_next_window_pos(pos, cond: int = 0, *_args) -> None:
    """``SetNextWindowPos``: place the next ``begin`` at *pos*.

    Parameters
    ----------
    pos : tuple
        ``(x, y)`` in the frame's units.
    cond : int, optional
        A ``Cond``: ``ALWAYS`` (the default) re-places every frame, ``ONCE``
        and ``FIRST_USE_EVER`` place the window when it is created, and
        ``APPEARING`` places it whenever it was absent last frame.

    Notes
    -----
    Under any condition but ``ALWAYS`` the window becomes *sticky*: it keeps
    the box across frames instead of taking the frame's, which is what a
    floating sub-window is asking for. See
    :meth:`emtk.im_core.Context.set_window_placement` for the same thing
    said once for a whole application.

    The pivot argument of ImGui's third parameter is accepted and ignored:
    emtk windows have no title bar to pivot about.
    """
    state = get_current_context().state(("next_window",))
    state["pos"] = tuple(pos)
    state["pos_cond"] = int(cond)


def set_next_window_size(size, cond: int = 0, *_args) -> None:
    """``SetNextWindowSize``: size the next ``begin`` to *size*.

    Parameters
    ----------
    size : tuple
        ``(width, height)``.
    cond : int, optional
        As :func:`set_next_window_pos`.
    """
    state = get_current_context().state(("next_window",))
    state["size"] = tuple(size)
    state["size_cond"] = int(cond)


def set_window_placement(placement: str) -> None:
    """Choose how a window opened with **no box** is first placed.

    Parameters
    ----------
    placement : str
        ``emtk.PLACE_FRAME`` (the default: the window is the frame and
        follows it) or ``emtk.PLACE_CASCADE`` (placed once, at a stepped
        offset, then sticky).

    Notes
    -----
    Not part of Dear ImGui's API -- ImGui always cascades, and emtk's
    default does not, because emtk's first callers were single full-window
    interfaces. An application with floating sub-windows wants
    ``PLACE_CASCADE`` and would otherwise draw every one of them over the
    whole frame and over each other.

    See :meth:`emtk.im_core.Context.set_window_placement`, which this calls.
    """
    get_current_context().set_window_placement(placement)


def set_next_window_collapsed(collapsed: bool, *_args) -> None:
    get_current_context().state(("next_window",))["collapsed"] = bool(collapsed)


def set_next_window_focus() -> None:
    get_current_context().state(("next_window",))["focus"] = True


def set_next_window_bg_alpha(alpha: float) -> None:
    get_current_context().state(("next_window",))["bg_alpha"] = float(alpha)


def set_window_pos(pos, *_args) -> None:
    window = _window()
    if window:
        window.box = (float(pos[0]), float(pos[1]), window.box[2], window.box[3])


def set_window_size(size, *_args) -> None:
    window = _window()
    if window:
        window.box = (window.box[0], window.box[1], float(size[0]), float(size[1]))


def set_window_focus(name: str = "") -> None:
    ctx = get_current_context()
    ctx.set_window_focus(name or (ctx.current_window.name if ctx.current_window else ""))


def set_window_collapsed(collapsed: bool, *_args) -> None:
    return None


# --------------------------------------------------------------------------- #
# Keys and the mouse
# --------------------------------------------------------------------------- #
def is_key_down(key: int) -> bool:
    return get_current_context().io.key == key


def is_key_pressed(key: int, repeat: bool = True) -> bool:
    return get_current_context().io.key == key


def is_key_released(key: int) -> bool:
    return False


def get_key_name(key: int) -> str:
    from . import keys as _keys

    for name, value in vars(_keys).items():
        if name.startswith("KEY_") and value == key:
            return name[4:].lower()
    return str(key)


def get_key_pressed_amount(key: int, repeat_delay: float = 0.0,
                           rate: float = 0.0) -> int:
    return 1 if is_key_pressed(key) else 0


def is_mouse_pos_valid(pos=None) -> bool:
    x, y = pos if pos is not None else get_current_context().io.mouse_pos
    return x > -256000.0 and y > -256000.0 and (x, y) != (-1.0, -1.0)


def reset_mouse_drag_delta(button: int = 0) -> None:
    io = get_current_context().io
    io.mouse_clicked_pos[button] = io.mouse_pos


def get_mouse_clicked_count(button: int = 0) -> int:
    io = get_current_context().io
    if io.mouse_double_clicked[button]:
        return 2
    return 1 if io.mouse_clicked[button] else 0


def get_mouse_cursor() -> int:
    return get_current_context().state(("cursor",)).get("shape", 0)


def set_mouse_cursor(shape: int) -> None:
    get_current_context().state(("cursor",))["shape"] = int(shape)


# --------------------------------------------------------------------------- #
# Items, popups, misc
# --------------------------------------------------------------------------- #
def get_item_id():
    return get_current_context()._last_id


def get_item_flags() -> int:
    return get_current_context().item_flags


def is_item_edited() -> bool:
    return is_item_active()


def is_item_deactivated_after_edit() -> bool:
    return is_item_deactivated()


def is_item_toggled_open() -> bool:
    return False


def is_any_item_focused() -> bool:
    return is_any_item_active()


def set_item_default_focus() -> None:
    return None


def set_keyboard_focus_here(offset: int = 0) -> None:
    """``SetKeyboardFocusHere``: 0 the next item, -1 the one just submitted."""
    ctx = get_current_context()
    ctx.set_keyboard_focus_here(offset)
    if offset < 0:
        ctx.state(("focus",))["id"] = ctx._last_id


def is_rect_visible(size_or_min, r_max=None) -> bool:
    ctx = get_current_context()
    if r_max is None:
        x, y = ctx.layout.cursor
        box = (x, y, size_or_min[0], size_or_min[1])
    else:
        box = (size_or_min[0], size_or_min[1],
               r_max[0] - size_or_min[0], r_max[1] - size_or_min[1])
    return ctx._overlaps_clip(box)


def begin_popup_modal(name: str, *_args) -> bool:
    return begin_popup(name)


def begin_popup_context_item(name: str = "", button: int = 1) -> bool:
    """Open a floating menu at a click on the last item.

    Inside the returned block, submit :func:`menu_item` or :func:`selectable`
    rows. They are drawn above the parent window, and a chosen row returns
    ``True`` to its caller on the following frame.
    """
    ctx = get_current_context()
    key = name or str(ctx._last_id)
    if is_item_hovered() and ctx.io.mouse_clicked[button]:
        ctx.open_context_popup(key, ctx.io.mouse_pos)
    return ctx.begin_popup(key)


def begin_popup_context_window(name: str = "", button: int = 1) -> bool:
    ctx = get_current_context()
    key = name or "##window_context"
    if is_window_hovered() and ctx.io.mouse_clicked[button]:
        ctx.open_context_popup(key, ctx.io.mouse_pos)
    return ctx.begin_popup(key)


def begin_popup_context_void(name: str = "", button: int = 1) -> bool:
    ctx = get_current_context()
    key = name or "##void_context"
    if ctx.current_window is None and ctx.io.mouse_clicked[1]:
        ctx.open_context_popup(key, ctx.io.mouse_pos)
    return ctx.begin_popup(key)


def open_popup_on_item_click(name: str = "", button: int = 1) -> None:
    ctx = get_current_context()
    if is_item_hovered() and ctx.io.mouse_clicked[button]:
        ctx.open_context_popup(name or str(ctx._last_id), ctx.io.mouse_pos)


def push_text_wrap_pos(x: float = 0.0) -> None:
    get_current_context().state(("wrap",)).setdefault("stack", []).append(x)


def pop_text_wrap_pos() -> None:
    stack = get_current_context().state(("wrap",)).get("stack") or []
    if stack:
        stack.pop()


def text_link(label: str) -> bool:
    """``TextLink``: text that behaves like a button."""
    ctx = get_current_context()
    width, height = ctx.draw.calc_text_size(_visible_label(label))
    box = ctx.layout.row(height=max(height, ctx.p.line_height()), width=width)
    _hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id(label))
    colour = _col(Col.CHECK_MARK)
    ctx.draw.add_text((box[0], box[1]), colour, _visible_label(label))
    ctx.draw.add_line((box[0], box[1] + box[3] - 1.0),
                      (box[0] + width, box[1] + box[3] - 1.0), colour, 1.0)
    return pressed


def text_link_open_url(label: str, url: str = "") -> None:
    """``TextLinkOpenURL``. Opening it is the *host's* business.

    emtk draws and reports; it does not reach for a browser. The click is
    published through the context so a host can act on it.
    """
    if text_link(label):
        get_current_context().state(("links",))["clicked"] = url or label


def value(label: str, v) -> None:
    """``ImGui::Value``: the label and the value, on one line."""
    if isinstance(v, bool):
        text("%s: %s" % (label, "true" if v else "false"))
    elif isinstance(v, float):
        text("%s: %.3f" % (label, v))
    else:
        text("%s: %s" % (label, v))


def plot_lines(label: str, values, overlay: str = "", size=None) -> None:
    """``PlotLines``: a polyline over the values, scaled to fit."""
    ctx = get_current_context()
    height = size[1] if size else _frame_height(ctx) * 3.0
    box = ctx.layout.row(height=height, width=size[0] if size else None)
    ctx.item_add(box)
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.FRAME_BG), ctx.style.frame_rounding)
    points = list(values)
    if len(points) >= 2:
        low, high = min(points), max(points)
        span = (high - low) or 1.0
        step = box[2] / (len(points) - 1)
        xy = [(box[0] + i * step,
               box[1] + box[3] - (v - low) / span * box[3])
              for i, v in enumerate(points)]
        ctx.draw.add_polyline(xy, _col(Col.PLOT_LINES), 0, 1.0)
    if overlay:
        ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]),
                          _col(Col.TEXT), overlay)
    # Drawn, not submitted. A label added with `text()` becomes an item of its
    # own, and then `is_item_hovered()` after a plot asks about the *label* --
    # the reference renders it and leaves the plot as the last item.
    shown = _visible_label(label)
    if shown:
        ctx.draw.add_text(
            (box[0] + box[2] + ctx.style.item_inner_spacing[0], box[1]),
            _col(Col.TEXT), shown)
    ctx.item_add(box)


def plot_histogram(label: str, values, overlay: str = "", size=None) -> None:
    ctx = get_current_context()
    width, height = _calc_item_size(size, ctx.layout.avail()[0],
                                    _frame_height(ctx) * 3.0)
    box = ctx.layout.row(height=height, width=width)
    ctx.item_add(box)
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _col(Col.FRAME_BG), ctx.style.frame_rounding)
    points = list(values)
    if points:
        low, high = min(min(points), 0.0), max(points)
        span = (high - low) or 1.0
        width = box[2] / len(points)
        for index, v in enumerate(points):
            top = box[1] + box[3] - (v - low) / span * box[3]
            ctx.draw.add_rect_filled(
                (box[0] + index * width, top),
                (box[0] + (index + 1) * width - 1.0, box[1] + box[3]),
                _col(Col.PLOT_HISTOGRAM), 0.0)
    if overlay:
        ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]),
                          _col(Col.TEXT), overlay)


def get_version() -> str:
    """``ImGui::GetVersion``: emtk's, since that is what is running."""
    from . import __version__ as _v  # noqa: PLC0415

    return str(_v)


def get_style_color_name(which: int) -> str:
    for name, value_ in vars(Col).items():
        if not name.startswith("_") and value_ == which:
            return name.title().replace("_", "")
    return str(which)


def get_style_color_vec4(which: int) -> tuple:
    return color_convert_u32_to_float4(_col(which))


def style_colors_dark(style=None) -> None:
    from .im_core import _default_colors

    (style or get_current_context().style).colors.update(_default_colors())


def style_colors_classic(style=None) -> None:
    style_colors_dark(style)


def style_colors_light(style=None) -> None:
    """The dark palette, inverted. Not the reference's hand-tuned light theme."""
    target = style or get_current_context().style
    for key, colour in list(target.colors.items()):
        rgba = tuple(colour) if len(colour) == 4 else (*colour, 255)
        target.colors[key] = (255 - rgba[0], 255 - rgba[1], 255 - rgba[2], rgba[3])


def get_state_storage() -> dict:
    return get_current_context().storage


def set_state_storage(storage: dict) -> None:
    get_current_context().storage = storage


def get_tree_node_to_label_spacing() -> float:
    ctx = get_current_context()
    return ctx.p.line_height() + ctx.style.frame_padding[0] * 2.0


def tree_node_get_open(label: str) -> bool:
    ctx = get_current_context()
    return bool(ctx.get_storage(ctx.get_id(label)).get("open", False))


def tab_item_button(label: str) -> bool:
    return small_button(label)


def set_tab_item_closed(label: str) -> None:
    return None


def get_column_index() -> int:
    return get_current_context().layout.column_index


def get_columns_count() -> int:
    return get_current_context().layout.column_count


def get_column_width(index: int = -1) -> float:
    """``GetColumnWidth``: how wide the column is, from the layout that made it."""
    ctx = get_current_context()
    if ctx.layout.column_count <= 1:
        return ctx.layout.avail()[0]
    return ctx.layout._column_offset(1) - ctx.layout._column_offset(0)


def get_column_offset(index: int = -1) -> float:
    """``GetColumnOffset``: the column's left edge, from the box's left edge."""
    ctx = get_current_context()
    which = ctx.layout.column_index if index < 0 else int(index)
    if ctx.layout.column_count <= 1:
        return 0.0
    # Relative to the first column, so column 0 is at 0. The layout's own
    # offsets start one item-spacing *left* of the indent -- that is what makes
    # the last column stop short of the right edge -- and reporting that as the
    # first column's offset would answer -8.
    return ctx.layout._column_offset(which) - ctx.layout._column_offset(0)


def destroy_context(ctx=None) -> None:
    from .im_core import set_current_context

    set_current_context(None)


__all__ += [
    "drag_float2", "drag_float3", "drag_float4", "drag_int2", "drag_int3",
    "drag_int4", "slider_float2", "slider_float3", "slider_float4",
    "slider_int2", "slider_int3", "slider_int4", "input_float2",
    "input_float3", "input_float4", "input_int2", "input_int3", "input_int4",
    "input_double", "drag_float_range2", "drag_int_range2", "drag_scalar",
    "slider_scalar", "input_scalar", "drag_scalar_n", "slider_scalar_n",
    "input_scalar_n", "v_slider_float", "v_slider_int", "v_slider_scalar",
    "color_convert_rgb_to_hsv", "color_convert_hsv_to_rgb",
    "color_convert_u32_to_float4", "color_convert_float4_to_u32",
    "color_picker3", "color_picker4", "get_scroll_x", "get_scroll_y",
    "set_scroll_x", "set_scroll_y", "set_child_scroll_y", "get_scroll_max_x", "get_scroll_max_y",
    "set_scroll_here_x", "set_scroll_here_y", "set_scroll_from_pos_x",
    "set_scroll_from_pos_y", "set_cursor_pos_x", "set_cursor_pos_y",
    "get_cursor_start_pos", "calc_item_width", "is_window_appearing",
    "is_window_collapsed", "set_next_window_pos", "set_next_window_size",
    "set_next_window_collapsed", "set_next_window_focus",
    "set_next_window_auto_resize", "set_window_placement",
    "set_next_window_bg_alpha", "set_window_pos", "set_window_size",
    "set_window_focus", "set_window_collapsed", "is_key_down",
    "is_key_pressed", "is_key_released", "get_key_name",
    "get_key_pressed_amount", "is_mouse_pos_valid", "reset_mouse_drag_delta",
    "get_mouse_clicked_count", "get_mouse_cursor", "set_mouse_cursor",
    "get_item_id", "get_item_flags", "is_item_edited",
    "is_item_deactivated_after_edit", "is_item_toggled_open",
    "is_any_item_focused", "set_item_default_focus", "set_keyboard_focus_here",
    "is_rect_visible", "begin_popup_modal", "begin_popup_context_item",
    "begin_popup_context_window", "begin_popup_context_void",
    "open_popup_on_item_click", "push_text_wrap_pos", "pop_text_wrap_pos",
    "text_link", "text_link_open_url", "value", "plot_lines",
    "plot_histogram", "get_version", "get_style_color_name",
    "get_style_color_vec4", "style_colors_dark", "style_colors_classic",
    "style_colors_light", "get_state_storage", "set_state_storage",
    "get_tree_node_to_label_spacing", "tree_node_get_open", "tab_item_button",
    "set_tab_item_closed", "get_column_index", "get_columns_count",
    "get_column_width", "get_column_offset", "table_get_row_index",
    "table_get_column_name", "table_header", "destroy_context",
    "TableFlags", "TableColumnFlags", "TableBgTarget", "SortSpec", "SortSpecs",
    "table_set_column_order",
]


# --------------------------------------------------------------------------- #
# Images, fonts, the platform, drag and drop, settings, logging
# --------------------------------------------------------------------------- #
#
# The last of the published API. Each is implemented in emtk's terms rather
# than declared impossible: an image goes to the painter's optional `image`
# operation (a tinted box when it has none), a font is a value the painter is
# asked to adopt, a "viewport" is the box the context was given, and the
# settings, the log and the clipboard are things emtk can hold perfectly well
# on its own.


def calc_image_size(
    handle: Any,
    size: tuple[float, float] | None = None,
    max_size: tuple[float, float] | None = None,
    scale: float = 1.0,
) -> tuple[float, float]:
    """Calculate the layout dimensions for an image item.

    Parameters
    ----------
    handle : Texture, str, Path, PIL Image, or numpy array
        The image item or source.
    size : tuple[float, float], optional
        Explicit (w, h) in pixels. If omitted, uses native dimensions.
    max_size : tuple[float, float], optional
        Maximum bounding box. If the image exceeds this, it is proportionally scaled down.
    scale : float
        Uniform scale factor applied to the native size (default 1.0).

    Returns
    -------
    tuple[float, float]
        The resolved (width, height) in points/pixels.
    """
    from .texture import Texture, get_texture

    tex = handle if isinstance(handle, Texture) else get_texture(handle)
    if size is not None and (size[0] > 0 or size[1] > 0):
        w, h = float(size[0]), float(size[1])
    elif tex is not None:
        w, h = float(tex.width) * scale, float(tex.height) * scale
    else:
        w, h = 32.0 * scale, 32.0 * scale

    if max_size is not None and (max_size[0] > 0 or max_size[1] > 0):
        max_w = float(max_size[0]) if max_size[0] > 0 else float("inf")
        max_h = float(max_size[1]) if max_size[1] > 0 else float("inf")
        if w > max_w:
            h = h * (max_w / w)
            w = max_w
        if h > max_h:
            w = w * (max_h / h)
            h = max_h
    return (w, h)


def image(
    handle: Any,
    size: tuple[float, float] | None = None,
    uv0: tuple[float, float] = (0.0, 0.0),
    uv1: tuple[float, float] = (1.0, 1.0),
    tint: Colour = (255, 255, 255, 255),
    border: Colour = (0, 0, 0, 0),
    max_size: tuple[float, float] | None = None,
    scale: float = 1.0,
    align_center: bool = False,
) -> tuple[float, float]:
    """``ImGui::Image``: Draw an image in the current layout.

    Accepts an EMTK :class:`~emtk.texture.Texture`, a file path (string or
    ``pathlib.Path``), a PIL ``Image``, or a numpy array. Image files are
    automatically cached in an internal LRU cache.

    Parameters
    ----------
    handle : Texture, str, Path, PIL Image, or numpy array
        The image item or source.
    size : tuple[float, float], optional
        Explicit (w, h) in pixels. If omitted or (0, 0), native dimensions are used.
    uv0, uv1 : tuple[float, float]
        UV coordinates windowing into the texture (0.0 to 1.0).
    tint : Colour
        Tint colour applied to the blit (default opaque white).
    border : Colour
        Border colour (default transparent).
    max_size : tuple[float, float], optional
        Maximum bounding box. If image exceeds this, it is proportionally scaled down.
    scale : float
        Uniform scale factor applied to native dimensions (default 1.0).
    align_center : bool
        If True, horizontally centers the image in the available content region.

    Returns
    -------
    tuple[float, float]
        The resolved (width, height) of the rendered item.
    """
    from .texture import Texture, get_texture

    tex = handle if isinstance(handle, Texture) else get_texture(handle)
    w, h = calc_image_size(tex or handle, size=size, max_size=max_size, scale=scale)

    ctx = get_current_context()
    avail_w = max(0.0, ctx.layout.w - ctx.layout.indent_x)
    pad = (avail_w - w) * 0.5 if (align_center and avail_w > w) else 0.0
    row_w = None if align_center else w
    box = ctx.layout.row(height=h, width=row_w)
    ctx.item_add(box)
    target = tex if tex is not None else handle
    x0 = box[0] + pad
    ctx.draw.add_image(target, (x0, box[1]), (x0 + w, box[1] + h), uv0, uv1, tint)
    if border and len(border) > 3 and border[3]:
        ctx.draw.add_rect((x0, box[1]), (x0 + w, box[1] + h), border)
    return (w, h)


def image_with_bg(
    handle: Any,
    size: tuple[float, float] | None = None,
    uv0: tuple[float, float] = (0.0, 0.0),
    uv1: tuple[float, float] = (1.0, 1.0),
    bg: Colour = (0, 0, 0, 0),
    tint: Colour = (255, 255, 255, 255),
    border: Colour = (0, 0, 0, 0),
    max_size: tuple[float, float] | None = None,
    scale: float = 1.0,
    align_center: bool = False,
) -> tuple[float, float]:
    """``ImGui::ImageWithBg``: Draw an image with a filled background rectangle."""
    ctx = get_current_context()
    from .texture import Texture, get_texture

    tex = handle if isinstance(handle, Texture) else get_texture(handle)
    w, h = calc_image_size(tex or handle, size=size, max_size=max_size, scale=scale)
    avail_w = max(0.0, ctx.layout.w - ctx.layout.indent_x)
    pad = (avail_w - w) * 0.5 if (align_center and avail_w > w) else 0.0
    row_w = None if align_center else w
    box = ctx.layout.row(height=h, width=row_w)
    ctx.item_add(box)
    x0 = box[0] + pad
    if bg and len(bg) > 3 and bg[3]:
        ctx.draw.add_rect_filled((x0, box[1]), (x0 + w, box[1] + h), bg)
    target = tex if tex is not None else handle
    ctx.draw.add_image(target, (x0, box[1]), (x0 + w, box[1] + h), uv0, uv1, tint)
    if border and len(border) > 3 and border[3]:
        ctx.draw.add_rect((x0, box[1]), (x0 + w, box[1] + h), border)
    return (w, h)


def image_button(
    str_id: str,
    handle: Any,
    size: tuple[float, float] | None = None,
    uv0: tuple[float, float] = (0.0, 0.0),
    uv1: tuple[float, float] = (1.0, 1.0),
    bg: Colour = (0, 0, 0, 0),
    tint: Colour = (255, 255, 255, 255),
    max_size: tuple[float, float] | None = None,
    scale: float = 1.0,
) -> bool:
    """``ImGui::ImageButton``: A button with an image on it."""
    from .texture import Texture, get_texture

    tex = handle if isinstance(handle, Texture) else get_texture(handle)
    w, h = calc_image_size(tex or handle, size=size, max_size=max_size, scale=scale)

    ctx = get_current_context()
    pad = ctx.style.frame_padding
    box = ctx.layout.row(height=h + pad[1] * 2.0, width=w + pad[0] * 2.0)
    hovered, held, pressed = ctx.button_behavior(box, ctx.get_id(str_id))
    ctx.draw.add_rect_filled(
        (box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
        _col(Col.BUTTON_ACTIVE) if held
        else (_col(Col.BUTTON_HOVERED) if hovered else _col(Col.BUTTON)),
        ctx.style.frame_rounding)
    target = tex if tex is not None else handle
    ctx.draw.add_image(target, (box[0] + pad[0], box[1] + pad[1]),
                       (box[0] + pad[0] + w, box[1] + pad[1] + h),
                       uv0, uv1, tint)
    return pressed



# -- fonts: a stack, and the painter adopts them if it can ------------------ #
def push_font(font: Any, size: float = 0.0) -> None:
    """``ImGui::PushFont``.

    The painter is asked to adopt it (``painter.set_font``); one that cannot
    keeps drawing in its own, and the metrics stay whatever the painter
    reports, so layout follows the font either way.
    """
    from .painter import set_font as _set_font

    ctx = get_current_context()
    store = ctx.state(("font",))
    stack = store.setdefault("stack", [])
    stack.append((store.get("current"), store.get("current_size", 0.0)))
    store["current"] = font
    store["current_size"] = size
    _set_font(ctx.p, font, size)


def pop_font() -> None:
    """``ImGui::PopFont``."""
    from .painter import set_font as _set_font

    ctx = get_current_context()
    store = ctx.state(("font",))
    stack = store.setdefault("stack", [])
    previous_font, previous_size = stack.pop() if stack else (None, 0.0)
    store["current"] = previous_font
    store["current_size"] = previous_size
    _set_font(ctx.p, previous_font, previous_size)


def push_font_scale(scale: float) -> None:
    """Push a font scaling multiplier on text rendering and metrics."""
    from .painter import set_font_scale as _set_font_scale

    ctx = get_current_context()
    store = ctx.state(("font_scale",))
    stack = store.setdefault("stack", [])
    curr = store.get("current", 1.0)
    stack.append(curr)
    store["current"] = float(scale)
    _set_font_scale(ctx.p, float(scale))


def pop_font_scale() -> None:
    """Pop the font scaling multiplier."""
    from .painter import set_font_scale as _set_font_scale

    ctx = get_current_context()
    store = ctx.state(("font_scale",))
    stack = store.setdefault("stack", [])
    prev = stack.pop() if stack else 1.0
    store["current"] = prev
    _set_font_scale(ctx.p, prev)


def set_window_font_scale(scale: float) -> None:
    """``ImGui::SetWindowFontScale``."""
    from .painter import set_font_scale as _set_font_scale

    ctx = get_current_context()
    ctx.state(("font_scale",))["current"] = float(scale)
    _set_font_scale(ctx.p, float(scale))


def heading(
    label: str,
    level: int = 1,
    colour: Any = None,
) -> None:
    """Render a styled typographical heading with appropriate font scaling."""
    scales = {1: 1.5, 2: 1.3, 3: 1.15, 4: 1.05}
    scale = scales.get(level, 1.0)

    push_font({"family": "sans-serif", "bold": True})
    push_font_scale(scale)
    if colour is not None:
        text_colored(colour, label)
    else:
        text(label)
    pop_font_scale()
    pop_font()
    if level == 1:
        separator()


def get_font():
    """``ImGui::GetFont``: whatever was pushed, or ``None`` for the painter's own."""
    return get_current_context().state(("font",)).get("current")



def get_font_baked(size: float = 0.0):
    """``ImGui::GetFontBaked``. emtk bakes nothing; the font is the font."""
    return get_font()


def get_font_tex_uv_white_pixel() -> tuple:
    """``GetFontTexUvWhitePixel``: the atlas corner solid shapes sample."""
    return (0.0, 0.0)


def show_font_selector(label: str = "Fonts") -> None:
    """``ShowFontSelector``: the fonts a host registered, as a combo."""
    ctx = get_current_context()
    fonts = list(ctx.state(("font",)).get("available") or [])
    if not fonts:
        text_disabled(f"{label}: the host has registered none")
        return
    current = fonts.index(get_font()) if get_font() in fonts else 0
    changed, current = combo(label, current, [str(f) for f in fonts])
    if changed:
        ctx.state(("font",))["current"] = fonts[current]


# -- the platform: the box emtk was handed ---------------------------------- #
class Viewport:
    """``ImGuiViewport``: where the whole thing is, in host coordinates."""

    def __init__(self, box) -> None:
        self.pos = (box[0], box[1])
        self.size = (box[2], box[3])
        self.work_pos = self.pos
        self.work_size = self.size

    def get_center(self) -> tuple:
        return (self.pos[0] + self.size[0] * 0.5, self.pos[1] + self.size[1] * 0.5)

    def get_work_center(self) -> tuple:
        return self.get_center()


def get_main_viewport() -> Viewport:
    """``ImGui::GetMainViewport``."""
    return Viewport(get_current_context().box)


class PlatformIO:
    """``ImGuiPlatformIO``: the host hooks emtk actually has."""

    def __init__(self, ctx) -> None:
        self._ctx = ctx

    @property
    def viewports(self):
        return [get_main_viewport()]

    @property
    def clipboard(self) -> str:
        return get_clipboard_text()


def get_platform_io() -> PlatformIO:
    return PlatformIO(get_current_context())


def mem_alloc(size: int):
    """``ImGui::MemAlloc``. Python's own allocator, spelled the reference's way."""
    return bytearray(int(size))


def mem_free(block) -> None:
    """``ImGui::MemFree``: the collector's job; this drops the reference."""
    del block


def set_allocator_functions(alloc_fn, free_fn, user_data=None) -> None:
    get_current_context().state(("alloc",))["fns"] = (alloc_fn, free_fn,
                                                            user_data)


def get_allocator_functions():
    return get_current_context().state(("alloc",)).get(
        "fns", (mem_alloc, mem_free, None))


def debug_check_version_and_data_layout(*_args) -> bool:
    """``DebugCheckVersionAndDataLayout``: a C ABI check, always true here."""
    return True


# -- the clipboard ----------------------------------------------------------- #
def get_clipboard_text() -> str:
    """``GetClipboardText``. The host may hook it; emtk keeps one otherwise."""
    ctx = get_current_context()
    hook = ctx.state(("clipboard",)).get("get")
    return str(hook()) if callable(hook) else str(
        ctx.state(("clipboard",)).get("text", ""))


def set_clipboard_text(text_: str) -> None:
    ctx = get_current_context()
    hook = ctx.state(("clipboard",)).get("set")
    if callable(hook):
        hook(str(text_))
    ctx.state(("clipboard",))["text"] = str(text_)


# -- drag and drop ----------------------------------------------------------- #
def begin_drag_drop_source(flags: int = 0) -> bool:
    """``BeginDragDropSource``: the last item, once dragged."""
    ctx = get_current_context()
    if not (is_item_active() and is_mouse_dragging(0)):
        return False
    ctx.state(("dnd",))["source"] = ctx._last_id
    return True


def set_drag_drop_payload(kind: str, data, cond: int = 0) -> bool:
    """``SetDragDropPayload``: any Python object; emtk does not copy bytes."""
    get_current_context().state(("dnd",))["payload"] = (str(kind), data)
    return True


def end_drag_drop_source() -> None:
    return None


def begin_drag_drop_target() -> bool:
    """``BeginDragDropTarget``: is a drag in flight over the last item?

    The rectangle, not the hovered id. While a drag is in flight the *source*
    holds the active id, and `ItemHoverable` refuses the pointer to anything
    else -- so a target asked through the normal path can never be hovered and
    a drop can never land. The reference has the same problem and the same
    answer: drag-drop targets hover with
    ``ImGuiHoveredFlags_AllowWhenBlockedByActiveItem``.
    """
    ctx = get_current_context()
    if not ctx.state(("dnd",)).get("payload"):
        return False
    box = ctx.get_item_rect()
    if box is None:
        return False
    return is_mouse_hovering_rect((box[0], box[1]),
                                  (box[0] + box[2], box[1] + box[3]))


def accept_drag_drop_payload(kind: str, flags: int = 0):
    """``AcceptDragDropPayload``: the payload, once the button comes up."""
    ctx = get_current_context()
    store = ctx.state(("dnd",))
    payload = store.get("payload")
    if not payload or payload[0] != str(kind):
        return None
    if not ctx.io.mouse_released[0]:
        return None
    store.pop("payload", None)
    store.pop("source", None)
    return payload[1]


def get_drag_drop_payload():
    payload = get_current_context().state(("dnd",)).get("payload")
    return payload[1] if payload else None


def end_drag_drop_target() -> None:
    return None


# -- multi-select ------------------------------------------------------------ #
class MultiSelectIO:
    """``ImGuiMultiSelectIO``: what the caller applies to its own selection."""

    def __init__(self) -> None:
        self.requests: list = []
        self.range_src_item = None
        self.nav_id_item = None


def begin_multi_select(flags: int = 0, selection_size: int = -1,
                       items_count: int = -1) -> MultiSelectIO:
    """``BeginMultiSelect``: collects what the user asked for this frame."""
    ctx = get_current_context()
    io_ = MultiSelectIO()
    ctx.state(("multiselect",))["io"] = io_
    if ctx.io.key_ctrl is False and ctx.io.mouse_clicked[0]:
        io_.requests.append(("clear", None))
    return io_


def end_multi_select() -> MultiSelectIO:
    ctx = get_current_context()
    return ctx.state(("multiselect",)).get("io") or MultiSelectIO()


def set_next_item_selection_user_data(user_data) -> None:
    get_current_context().state(("multiselect",))["next"] = user_data


def is_item_toggled_selection() -> bool:
    ctx = get_current_context()
    return bool(is_item_clicked() and ctx.io.key_ctrl)


# -- settings ---------------------------------------------------------------- #
def save_ini_settings_to_memory() -> str:
    """``SaveIniSettingsToMemory``: the windows' places, in ini form."""
    ctx = get_current_context()
    lines = []
    for window in ctx.windows:
        lines.append(f"[Window][{window.name}]")
        lines.append("Pos=%d,%d" % (int(window.box[0]), int(window.box[1])))
        lines.append("Size=%d,%d" % (int(window.box[2]), int(window.box[3])))
        lines.append("")
    return "\n".join(lines)


def load_ini_settings_from_memory(data: str) -> None:
    """``LoadIniSettingsFromMemory``."""
    from .im_core import _Window

    def _pair(text_: str):
        """Exactly two numbers, or nothing.

        A line like ``Pos=1,2,3`` would otherwise be splatted into the box and
        make it five long -- an ini file edited by hand is the normal case, so
        a malformed line has to be skipped rather than half-read.
        """
        parts = text_.split(",")
        if len(parts) != 2:
            return None
        try:
            return (float(parts[0]), float(parts[1]))
        except ValueError:
            return None

    ctx = get_current_context()
    name, pos, size = None, None, None
    for line in str(data).splitlines():
        line = line.strip()
        if line.startswith("[Window][") and line.endswith("]"):
            name = line[len("[Window]["):-1]
            pos = size = None
        elif line.startswith("Pos=") and name:
            pos = _pair(line[4:])
        elif line.startswith("Size=") and name:
            size = _pair(line[5:])
        if name and pos and size:
            window = next((w for w in ctx.windows if w.name == name), None)
            if window is None:
                # Remembered, not shown: inactive until a begin() submits it,
                # so it neither takes presses nor skips appearing.
                window = _Window(name=name, box=(pos[0], pos[1], size[0], size[1]), active=False)
                ctx.windows.append(window)
            else:
                window.box = (pos[0], pos[1], size[0], size[1])
            name = pos = size = None


def save_ini_settings_to_disk(path: str) -> None:
    import pathlib

    pathlib.Path(path).write_text(save_ini_settings_to_memory())


def load_ini_settings_from_disk(path: str) -> None:
    import pathlib

    file = pathlib.Path(path)
    if file.exists():
        load_ini_settings_from_memory(file.read_text())


# -- logging ----------------------------------------------------------------- #
def _log():
    return get_current_context().state(("log",))


def log_to_tty(auto_open_depth: int = -1) -> None:
    """``LogToTTY``: subsequent ``log_text`` goes to stdout."""
    _log().update(active=True, sink="tty", buffer=[])


def log_to_file(auto_open_depth: int = -1, path: str = "imgui_log.txt") -> None:
    _log().update(active=True, sink="file", path=path, buffer=[])


def log_to_clipboard(auto_open_depth: int = -1) -> None:
    _log().update(active=True, sink="clipboard", buffer=[])


def log_text(s: str) -> None:
    """``LogText``: into whichever sink is open."""
    store = _log()
    if not store.get("active"):
        return
    store.setdefault("buffer", []).append(str(s))


def log_finish() -> None:
    """``LogFinish``: flush and close the sink."""
    import pathlib

    store = _log()
    if not store.get("active"):
        return
    text_ = "".join(store.get("buffer", []))
    sink = store.get("sink")
    if sink == "tty":
        print(text_, end="")
    elif sink == "file":
        pathlib.Path(store.get("path", "imgui_log.txt")).write_text(text_)
    elif sink == "clipboard":
        set_clipboard_text(text_)
    store.update(active=False, buffer=[], last=text_)


def log_buttons() -> None:
    """``LogButtons``: the three sinks, as buttons."""
    if small_button("Log to TTY"):
        log_to_tty()
    same_line()
    if small_button("Log to File"):
        log_to_file()
    same_line()
    if small_button("Log to Clipboard"):
        log_to_clipboard()


def debug_log(s: str) -> None:
    """``DebugLog``: emtk's own log, shown by `show_debug_log_window`."""
    get_current_context().state(("debuglog",)).setdefault(
        "lines", []).append(str(s))


def debug_text_encoding(s: str) -> None:
    for index, char in enumerate(str(s)):
        text("%d: U+%04X %s" % (index, ord(char), char))


def debug_start_item_picker() -> None:
    get_current_context().state(("debuglog",))["picking"] = True


def debug_flash_style_color(which: int) -> None:
    get_current_context().state(("debuglog",))["flash"] = which


# -- the rest ---------------------------------------------------------------- #
def input_text_multiline(label: str, value: str, size=None) -> tuple[bool, str]:
    """A multiline buffer with cursor, selection, clipboard and undo editing."""
    from .widgets.text_editor import TextEditor

    ctx = get_current_context()
    value = str(value)
    store = ctx.get_storage(ctx.get_id(label))
    editor = store.get("multiline_editor")
    if editor is None:
        editor = TextEditor(value)
        editor.config.show_line_numbers = False
        store["multiline_editor"] = editor
    elif editor.text != value:
        editor.set_text(value)
    editor.config.read_only = bool(ctx.item_flags & ItemFlags.DISABLED)
    if size is None:
        size = (0, _frame_height(ctx) * max(len(value.split("\n")), 3))
    text_editor(label, editor, size)
    return (editor.text != value, editor.text)


def text_editor(label: str, editor: Any, size: tuple[float, float] | None = None) -> bool:
    """``text_editor``: embed and interact with a :class:`~emtk.widgets.text_editor.TextEditor`.

    Draws the editor in the immediate-mode layout, routes mouse clicks, drags,
    wheel scrolling, and keyboard events, and adapts palette to the active theme.

    Parameters
    ----------
    label : str
        Unique widget label or ID (e.g. ``"##editor"``).
    editor : TextEditor
        The editor instance to draw.
    size : tuple of float, optional
        (width, height). If width <= 0 or None, spans available content width.
        If height <= 0 or None, spans available content height (minimum 120px).

    Returns
    -------
    bool
        True if the editor text was modified during this frame.
    """
    ctx = get_current_context()
    avail_w, avail_h = get_content_region_avail()[:2]
    w = float(size[0]) if size and len(size) > 0 and size[0] > 0.0 else max(100.0, float(avail_w))
    h = float(size[1]) if size and len(size) > 1 and size[1] > 0.0 else max(120.0, float(avail_h))

    box = ctx.layout.row(height=h, width=w)
    item_id = ctx.get_id(label)
    hovered = ctx.item_add(box, item_id)
    focus = ctx.state(("focus",))
    io = ctx.io
    px, py = io.mouse_pos

    if io.mouse_clicked[0]:
        if hovered:
            focus["id"] = item_id
            set_nav_id(item_id)
            clicks = 2 if io.mouse_double_clicked[0] else 1
            editor.press(px, py, *box, 0, clicks)
        elif focus.get("id") == item_id:
            focus.pop("id", None)

    focused = not bool(ctx.item_flags & ItemFlags.DISABLED) and (
        focus.get("id") == item_id or ctx.is_nav_focused(item_id))

    if hovered and io.mouse_wheel:
        editor.scroll(-3 if io.mouse_wheel > 0 else 3)
    if io.mouse_down[0] and focused and not io.mouse_clicked[0]:
        editor.drag(px, py, *box)
    if io.mouse_released[0] and focused:
        editor.release()

    was_modified = getattr(editor, "modified", False)
    revision = getattr(editor, "revision", None)

    if focused:
        events = list(io.key_events)
        if not events and (io.key or io.text):
            mods = _current_modifiers(io)
            events = [(io.key, io.text, mods)]
        for key, text, mods in events:
            editor.key(int(key), text, mods)

    window_bg = ctx.style.color(Col.WINDOW_BG)
    from .widgets.text_editor import DARK_PALETTE, LIGHT_PALETTE
    if sum(window_bg[:3]) > 3 * 128:
        editor.palette = LIGHT_PALETTE
    else:
        editor.palette = DARK_PALETTE

    editor.draw(ctx.p, *box)
    if revision is not None:
        return editor.revision != revision
    return bool(getattr(editor, "modified", False) and not was_modified)


_RICH_HOOKS = ("pointer_press", "pointer_move", "pointer_release", "wheel")
_BUTTONS = (1, 2, 4)            # emtk.events LEFT/RIGHT/MIDDLE_BUTTON, by io index


def host_control(label: str, control: Any, size: tuple[float, float] | None = None) -> bool:
    """Host a retained control as one item of the immediate-mode layout.

    The control is anything with emtk's control contract (:class:`emtk.control.Control`
    spells it out): it draws into a box and is handed the input that concerns it,
    the same calls :func:`emtk.qt_host.ControlHost` makes, so a control written for
    a window of its own runs unchanged inside a dock window, a child, a table cell.

    * A press inside the box captures the pointer: the drags that follow, and the
      release, reach the control wherever the pointer goes, as a host's grab does.
    * Hover arrives while the pointer is over the box and nothing is held.
    * The wheel scrolls the hovered control, three rows a notch, and is consumed.
    * Keys go to the control that was clicked last, and only while it is: a click
      elsewhere ends that (``focus_lost``), so typing never lands in a control the
      user is not looking at.

    A control that speaks the rich hooks (``pointer_press``/``pointer_move``/
    ``pointer_release``/``wheel``, as :class:`emtk.app.ImApp` does) is given every
    button and the wheel in notches instead of the classic ``press``/``drag``/
    ``release``/``hover``/``scroll``.

    Parameters
    ----------
    label : str
        Unique widget label or ID (e.g. ``"##plot"``).
    control : object
        The retained control.
    size : tuple of float, optional
        ``(width, height)``. A missing or non-positive extent takes what is left
        of the content region in that direction.

    Returns
    -------
    bool
        True if the control was handed a press, a release, the wheel or a key
        this frame -- the frames after which a caller re-reads its state.
    """
    ctx = get_current_context()
    avail_w, avail_h = get_content_region_avail()[:2]
    w = float(size[0]) if size and size[0] and size[0] > 0.0 else max(1.0, float(avail_w))
    h = float(size[1]) if size and len(size) > 1 and size[1] and size[1] > 0.0 else max(
        1.0, float(avail_h))
    box = ctx.layout.row(height=h, width=w)
    item_id = ctx.get_id(label)
    hovered = ctx.item_add(box, item_id)
    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    io = ctx.io
    px, py = io.mouse_pos
    mods = _current_modifiers(io)
    store = ctx.get_storage(item_id)
    focus = ctx.state(("focus",))
    rich = all(callable(getattr(control, hook, None)) for hook in _RICH_HOOKS)
    took = False

    if not disabled:
        clicked = [i for i, c in enumerate(io.mouse_clicked) if c]
        if clicked and hovered:
            focus["id"] = item_id
            set_nav_id(item_id)
            for i in clicked:
                clicks = 2 if io.mouse_double_clicked[i] else 1
                if rich:
                    control.pointer_press(px, py, _BUTTONS[i], mods, clicks)
                elif i == 0:
                    control.press(px, py, *box, mods, clicks)
                store.setdefault("held", set()).add(i)
            took = True
        elif clicked and focus.get("id") == item_id:
            focus.pop("id", None)
            lost = getattr(control, "focus_lost", None)
            if callable(lost):
                lost()

        held = store.get("held") or set()
        if held:
            if rich:
                buttons = sum(_BUTTONS[i] for i in held if io.mouse_down[i])
                control.pointer_move(px, py, buttons, mods)
            elif 0 in held and io.mouse_down[0]:
                drag = getattr(control, "drag", None)
                if callable(drag):
                    drag(px, py, *box)
            for i in [i for i in held if io.mouse_released[i] or not io.mouse_down[i]]:
                held.discard(i)
                if rich:
                    control.pointer_release(px, py, _BUTTONS[i], mods)
                elif i == 0:
                    release = getattr(control, "release", None)
                    if callable(release):
                        release()
                took = True
        elif hovered:
            if rich:
                control.pointer_move(px, py, 0, mods)
            else:
                hover = getattr(control, "hover", None)
                if callable(hover):
                    hover(px, py, *box)

        if hovered and io.mouse_wheel:
            if rich:
                control.wheel(px, py, float(io.mouse_wheel), mods)
            else:
                scroll = getattr(control, "scroll", None)
                if callable(scroll):
                    scroll(-3 if io.mouse_wheel > 0 else 3)
            io.mouse_wheel = 0.0
            took = True

        key = getattr(control, "key", None)
        if focus.get("id") == item_id and callable(key):
            events = list(io.key_events)
            if not events and (io.key or io.text):
                events = [(io.key, io.text, mods)]
            for code, text, modifiers in events:
                key(int(code), text, modifiers)
                took = True

    control.draw(ctx.p, *box)
    return took



def is_key_chord_pressed(chord: int) -> bool:
    """``IsKeyChordPressed``: the key, and exactly the modifiers asked for.

    Exactly: a chord with no ``MOD_CTRL`` does not match a press with Ctrl
    held, or every plain shortcut would fire under every modified one.
    """
    from . import keys as _keys

    ctx = get_current_context()
    key = int(chord) & ~_keys.MOD_MASK
    if not is_key_pressed(key):
        return False
    return (ctx.io.key_ctrl == bool(chord & _keys.MOD_CTRL)
            and ctx.io.key_shift == bool(chord & _keys.MOD_SHIFT)
            and ctx.io.key_alt == bool(chord & _keys.MOD_ALT)
            and ctx.io.key_super == bool(chord & _keys.MOD_SUPER))


def shortcut(chord: int, flags: int = 0) -> bool:
    """``ImGui::Shortcut``."""
    return is_key_chord_pressed(chord)


def set_next_item_shortcut(chord: int, flags: int = 0) -> None:
    get_current_context().state(("shortcut",))["next"] = chord


def set_item_key_owner(key: int, flags: int = 0) -> None:
    get_current_context().state(("shortcut",))["owner"] = key


def set_next_item_storage_id(storage_id) -> None:
    get_current_context().state(("storage_id",))["next"] = storage_id


def set_nav_cursor_visible(visible: bool) -> None:
    get_current_context().state(("nav",))["visible"] = bool(visible)


def set_next_frame_want_capture_mouse(want: bool) -> None:
    get_current_context().state(("capture",))["mouse"] = bool(want)


def set_next_frame_want_capture_keyboard(want: bool) -> None:
    get_current_context().state(("capture",))["keyboard"] = bool(want)


def get_mouse_pos_on_opening_current_popup() -> tuple:
    ctx = get_current_context()
    return ctx.state(("popup",)).get("open_pos", ctx.io.mouse_pos)


def get_item_clicked_count_with_single_click_delay() -> int:
    return get_mouse_clicked_count(0)


def is_mouse_released_with_delay(button: int = 0, delay: float = 0.0) -> bool:
    return is_mouse_released(button)


def set_next_window_content_size(size) -> None:
    get_current_context().state(("next_window",))["content"] = tuple(size)


def set_next_window_scroll(scroll) -> None:
    get_current_context().state(("next_window",))["scroll"] = tuple(scroll)


def set_next_window_size_constraints(size_min, size_max, *_args) -> None:
    get_current_context().state(("next_window",))["constraints"] = (
        tuple(size_min), tuple(size_max))


def set_column_width(index: int, width: float) -> None:
    get_current_context().state(("columns",))[int(index)] = float(width)


def set_column_offset(index: int, offset: float) -> None:
    get_current_context().state(("columns",))[("offset", int(index))] = float(offset)


# -- the built-in windows ----------------------------------------------------- #
def show_about_window(open_: bool = True) -> None:
    """``ShowAboutWindow``."""
    if not open_:
        return
    text("emtk -- Dear ImGui, in Python, on any painter")
    text(f"version {get_version()}")
    separator()
    text_disabled("ImGui:: becomes im.  CamelCase becomes snake_case.")


def show_user_guide() -> None:
    """``ShowUserGuide``: the reference's own text, for the same controls."""
    bullet_text("Double-click on title bar to collapse window.")
    bullet_text("Click and drag on lower corner to resize window.")
    bullet_text("Click and drag on any empty space to move window.")
    bullet_text("CTRL+Click on a slider or drag box to input value as text.")
    bullet_text("While inputing text: CTRL+A or double-click to select all.")


def show_style_selector(label: str = "Style") -> bool:
    """``ShowStyleSelector``."""
    ctx = get_current_context()
    store = ctx.state(("style_selector",))
    changed, index = combo(label, store.get("index", 0),
                           ["Dark", "Light", "Classic"])
    if changed:
        store["index"] = index
        (style_colors_dark, style_colors_light, style_colors_classic)[index]()
    return changed


def show_style_editor(style=None) -> None:
    """``ShowStyleEditor``: the metrics and the palette, editable."""
    ctx = get_current_context()
    target = style or ctx.style
    show_style_selector()
    separator_text("Metrics")
    for name in ("frame_rounding", "grab_min_size", "grab_rounding"):
        changed, value_ = slider_float(name, float(getattr(target, name)),
                                       0.0, 20.0, "%.1f")
        if changed:
            setattr(target, name, value_)
    separator_text("Colors")
    for which in sorted(target.colors):
        color_button(f"##col{which}", target.colors[which])
        same_line(0.0, ctx.style.item_inner_spacing[0])
        text(get_style_color_name(which))


def show_metrics_window(open_: bool = True) -> None:
    """``ShowMetricsWindow``: what the context is actually doing."""
    if not open_:
        return
    ctx = get_current_context()
    text("frame %d  %.1f ms" % (ctx.io.frame_count, ctx.io.delta_time * 1000.0))
    text("windows: %d" % len(ctx.windows))
    text("hovered window: %s" % (ctx.hovered_window.name if ctx.hovered_window
                                 else "none"))
    text("hovered id: %s" % (ctx.hovered_id,))
    text("active id: %s" % (ctx.active_id,))
    text("mouse: %.0f, %.0f" % ctx.io.mouse_pos)


def show_debug_log_window(open_: bool = True) -> None:
    """``ShowDebugLogWindow``.

    Drawn even when the log is empty: a window that puts nothing on screen
    reads as broken, and "nothing has been logged" is itself the answer
    somebody opened it for.
    """
    if not open_:
        return
    lines = get_current_context().state(("debuglog",)).get("lines", [])
    separator_text("Debug log")
    if not lines:
        text_disabled("(nothing logged)")
        return
    for line in lines:
        text_unformatted(line)


def show_id_stack_tool_window(open_: bool = True) -> None:
    """``ShowIDStackToolWindow``: the id stack, and what the last item hashed to."""
    if not open_:
        return
    ctx = get_current_context()
    text("id stack: %s" % (tuple(ctx._ids),))
    text("last item: %s" % (ctx._last_id,))
    text("hovered:   %s" % (ctx.hovered_id,))


def show_demo_window(open_: bool = True) -> None:
    """``ShowDemoWindow``: the reference's demo, in the widgets emtk has.

    Not all sixty of its sections -- it is the Basic set, which is what a port
    reaches for first and what the tests drive.
    """
    if not open_:
        return
    ctx = get_current_context()
    store = ctx.state(("demo",))
    text("emtk %s -- Dear ImGui in Python" % get_version())
    separator_text("Basic")
    if button("Button"):
        store["clicked"] = store.get("clicked", 0) + 1
    if store.get("clicked", 0) & 1:
        same_line()
        text("Thanks for clicking me!")
    _c, store["check"] = checkbox("checkbox", store.get("check", True))
    for index, name in enumerate(("radio a", "radio b", "radio c")):
        _c, store["radio"] = radio_button(name, store.get("radio", 0), index)
        if index < 2:
            same_line()
    _c, store["f"] = slider_float("float", store.get("f", 0.5), 0.0, 1.0)
    _c, store["col"] = color_edit3("color", store.get("col", (255, 128, 0)))
    separator_text("Trees")
    if tree_node("Node"):
        text("a leaf")
        tree_pop()
    separator_text("Plots")
    plot_lines("##lines", [0.0, 0.6, 0.2, 0.9, 0.4], size=(180.0, 40.0))


def markdown(
    content: Any,
    on_link: Optional[Any] = None,
    max_width: Optional[float] = None,
) -> None:
    """``ImGui::Markdown``: Render a formatted Markdown document into the layout."""
    from .widgets.markdown import render_markdown

    render_markdown(content, on_link=on_link, max_width=max_width)


__all__ += [
    "image", "image_with_bg", "image_button", "calc_image_size", "push_font", "pop_font",
    "push_font_scale", "pop_font_scale", "set_window_font_scale", "heading", "markdown",
    "get_font", "get_font_baked", "get_font_tex_uv_white_pixel",
    "show_font_selector", "Viewport", "get_main_viewport", "PlatformIO",
    "get_platform_io", "mem_alloc", "mem_free", "set_allocator_functions",
    "get_allocator_functions", "debug_check_version_and_data_layout",
    "get_clipboard_text", "set_clipboard_text", "begin_drag_drop_source",
    "set_drag_drop_payload", "end_drag_drop_source", "begin_drag_drop_target",
    "accept_drag_drop_payload", "get_drag_drop_payload",
    "end_drag_drop_target", "MultiSelectIO", "begin_multi_select",
    "end_multi_select", "set_next_item_selection_user_data",
    "is_item_toggled_selection", "save_ini_settings_to_memory",
    "load_ini_settings_from_memory", "save_ini_settings_to_disk",
    "load_ini_settings_from_disk", "log_to_tty", "log_to_file",
    "log_to_clipboard", "log_text", "log_finish", "log_buttons", "debug_log",
    "debug_text_encoding", "debug_start_item_picker", "debug_flash_style_color",
    "input_text_multiline", "text_editor", "host_control", "is_key_chord_pressed", "shortcut",
    "set_next_item_shortcut", "set_item_key_owner", "set_next_item_storage_id",
    "set_nav_cursor_visible", "set_next_frame_want_capture_mouse",
    "set_next_frame_want_capture_keyboard",
    "get_mouse_pos_on_opening_current_popup",
    "get_item_clicked_count_with_single_click_delay",
    "is_mouse_released_with_delay", "set_next_window_content_size",
    "set_next_window_scroll", "set_next_window_size_constraints",
    "set_column_width", "set_column_offset", "table_get_column_flags",
    "table_get_hovered_column", "table_get_sort_specs", "table_set_bg_color",
    "table_set_column_enabled", "table_setup_scroll_freeze",
    "table_angled_headers_row", "show_about_window", "show_user_guide",
    "show_style_selector", "show_style_editor", "show_metrics_window",
    "show_debug_log_window", "show_id_stack_tool_window", "show_demo_window",
]


def get_draw_data():
    """``ImGui::GetDrawData``: what this frame recorded, ready to hand on."""
    return get_current_context().draw.get_draw_data()


def get_draw_list_shared_data():
    """``GetDrawListSharedData``: the settings every draw list shares.

    In the reference this carries the circle-segment table, the curve
    tessellation tolerance and the font atlas; here it is the draw list's own
    tessellation settings, which are the same two numbers.
    """
    draw = get_current_context().draw
    return {"circle_segments": draw.circle_segments,
            "curve_segments": draw.curve_segments}


def push_style_var_x(which: str, x: float) -> None:
    """``PushStyleVarX``: one axis of a two-component style metric."""
    current = getattr(get_current_context().style, which)
    push_style_var(which, (float(x), current[1]))


def push_style_var_y(which: str, y: float) -> None:
    """``PushStyleVarY``."""
    current = getattr(get_current_context().style, which)
    push_style_var(which, (current[0], float(y)))


__all__ += ["get_draw_data", "get_draw_list_shared_data", "push_style_var_x",
            "push_style_var_y"]


# --------------------------------------------------------------------------- #
# ListClipper
# --------------------------------------------------------------------------- #
class ListClipper:
    """``ImGuiListClipper``: submit only the rows that can be seen.

    A hundred thousand rows cost a hundred thousand widget submissions unless
    something works out which of them are on screen. The reference's clipper
    does that by measuring one row, skipping the cursor past the ones above the
    view, letting the caller submit the visible run, and then skipping past the
    rest so the scrollbar still knows how tall the whole list is.

    The same three steps here, and the same shape of loop::

        clipper = emtk.ListClipper()
        clipper.begin(10000)
        while clipper.step():
            for row in range(clipper.display_start, clipper.display_end):
                emtk.text("row %d" % row)

    Attributes are the reference's, in Python spelling: ``display_start``,
    ``display_end``, ``items_count``, ``items_height``.
    """

    def __init__(self) -> None:
        self.display_start = 0
        self.display_end = 0
        self.items_count = 0
        self.items_height = 0.0
        self.user_index = 0
        self._step = 0
        self._forced: list[tuple[int, int]] = []
        self._start_y = 0.0

    def begin(self, items_count: int, items_height: float = -1.0) -> None:
        """``Begin``. A negative height means "measure the first row"."""
        ctx = get_current_context()
        self.items_count = int(items_count)
        from .im_core import get_text_line_height_with_spacing

        self.items_height = (float(items_height) if items_height > 0.0
                             else get_text_line_height_with_spacing())
        self.display_start = self.display_end = 0
        self._step = 0
        self._start_y = ctx.layout.cursor[1]

    def include_items_by_index(self, item_begin: int, item_end: int) -> None:
        """``IncludeItemsByIndex``: never clip this run (a selected row)."""
        self._forced.append((int(item_begin), int(item_end)))

    def include_item_by_index(self, item_index: int) -> None:
        self.include_items_by_index(item_index, item_index + 1)

    def step(self) -> bool:
        """``Step``. True while there is a run to submit."""
        ctx = get_current_context()
        if self._step == 0:
            self._step = 1
            window = ctx.current_window
            scroll = window.scroll[1] if window else 0.0
            height = (window.box[3] if window else ctx.box[3])
            first = max(int(scroll / max(self.items_height, 1e-6)) - 1, 0)
            visible = int(height / max(self.items_height, 1e-6)) + 2
            self.display_start = min(first, self.items_count)
            self.display_end = min(first + visible, self.items_count)
            for begin, end in self._forced:
                self.display_start = min(self.display_start, max(begin, 0))
                self.display_end = max(self.display_end, min(end, self.items_count))
            # Skip the cursor past the rows above the view, so what is
            # submitted lands where it would have.
            if self.display_start:
                set_cursor_pos_y(self._start_y
                                 + self.display_start * self.items_height)
            return self.display_start < self.display_end
        if self._step == 1:
            self._step = 2
            self.end()
            return False
        return False

    def end(self) -> None:
        """``End``: leave the cursor below *all* the rows, seen or not."""
        if self.items_count > 0:
            set_cursor_pos_y(self._start_y + self.items_count * self.items_height)
        self.display_start = self.display_end = self.items_count


__all__ += ["ListClipper"]


def get_column_width_of(index: int) -> float:
    """The width of table column *index*, or of a legacy column set's column.

    ``GetColumnWidth`` takes the current column; a table's columns each have
    their own width now, so this is the indexed form the sizing sections need.
    """
    table = _table()
    if table is None:
        return get_column_width(index)
    columns = table.visible_columns()
    which = table.current if index < 0 else int(index)
    return columns[which].width if 0 <= which < len(columns) else 0.0


__all__ += ["get_column_width_of"]


# --------------------------------------------------------------------------- #
# Keyboard navigation
# --------------------------------------------------------------------------- #
#
# The tab ring is the order items were submitted in -- `ItemAdd` puts each one
# in it -- so there is no second list to keep in step, which is the same reason
# hit-testing is a by-product of drawing.


def nav_tab(shift: bool = False) -> None:
    """Move the focus one item. What ``Tab`` and ``Shift+Tab`` do."""
    get_current_context().nav_move(-1 if shift else 1)


def process_nav_keys() -> None:
    """Read Tab out of ``io`` and move the focus. Call once a frame.

    Only when ``ConfigFlags.NAV_ENABLE_KEYBOARD`` is on, as the reference
    gates it -- an application that wants the Tab key for itself keeps it.
    """
    from . import keys as _keys

    ctx = get_current_context()
    if not (ctx.io.config_flags & ConfigFlags.NAV_ENABLE_KEYBOARD):
        return
    if ctx.io.key == _keys.KEY_TAB:
        ctx.nav_move(-1 if ctx.io.key_shift else 1)


def get_nav_id():
    """Which item has the keyboard focus, or ``None``."""
    return get_current_context().nav_id


def set_nav_id(item_id) -> None:
    ctx = get_current_context()
    ctx.nav_id = item_id
    ctx.storage["__nav_id__"] = item_id


def is_item_nav_focused() -> bool:
    ctx = get_current_context()
    return ctx.is_nav_focused(ctx._last_id)


def get_nav_ring() -> list:
    """The tab order this frame: the items, in submission order."""
    return list(get_current_context().nav_ring)


# --------------------------------------------------------------------------- #
# Docking
# --------------------------------------------------------------------------- #
#
# The half of docking that is emtk's: a node is a box that windows share, and
# windows sharing one are its tabs. The other half -- dragging a window by its
# title bar to make a node -- belongs to the host's window frame, so a host
# that drags calls `set_next_window_dock_id` and emtk does the rest.


def dock_space(dock_id: int, size=None) -> int:
    """``ImGui::DockSpace``: a region windows may dock into."""
    ctx = get_current_context()
    node = ctx.dock_node(dock_id)
    x, y = ctx.layout.cursor
    width = size[0] if size and size[0] else ctx.layout.avail()[0]
    height = size[1] if size and len(size) > 1 and size[1] else ctx.layout.avail()[1]
    node["box"] = (x, y, width, height)
    node["windows"] = []
    return int(dock_id)


def dock_space_over_viewport(dock_id: int = 1) -> int:
    """``DockSpaceOverViewport``: a dock space filling the whole box."""
    ctx = get_current_context()
    node = ctx.dock_node(dock_id)
    node["box"] = ctx.box
    node["windows"] = []
    return int(dock_id)


def set_next_window_dock_id(dock_id: int) -> None:
    """``SetNextWindowDockID``."""
    get_current_context().state(("next_window",))["dock_id"] = int(dock_id)


def get_window_dock_id() -> int:
    window = get_current_context().current_window
    return window.dock_id if window else 0


def is_window_docked() -> bool:
    """``IsWindowDocked``."""
    return get_window_dock_id() != 0


def dock_builder_split_node(dock_id: int, direction: int, ratio: float):
    """``DockBuilderSplitNode``: cut a node in two.

    Returns ``(this_side, other_side)`` -- two node ids, as the reference's
    out-parameters give back.
    """
    ctx = get_current_context()
    node = ctx.dock_node(dock_id)
    x, y, w, h = node["box"]
    ratio = max(0.05, min(0.95, float(ratio)))
    first = ctx.dock_node(dock_id * 10 + 1)
    second = ctx.dock_node(dock_id * 10 + 2)
    if direction in (Dir.LEFT, Dir.RIGHT):
        cut = w * ratio
        first["box"] = (x, y, cut, h) if direction == Dir.LEFT else \
            (x + w - cut, y, cut, h)
        second["box"] = (x + cut, y, w - cut, h) if direction == Dir.LEFT else \
            (x, y, w - cut, h)
    else:
        cut = h * ratio
        first["box"] = (x, y, w, cut) if direction == Dir.UP else \
            (x, y + h - cut, w, cut)
        second["box"] = (x, y + cut, w, h - cut) if direction == Dir.UP else \
            (x, y, w, h - cut)
    node["split"] = (first["id"], second["id"], direction, ratio)
    return (first["id"], second["id"])


def dock_builder_dock_window(name: str, dock_id: int) -> None:
    """``DockBuilderDockWindow``: put a window in a node up front."""
    from .im_core import split_label

    _title, key = split_label(name)
    get_current_context().state(("dock",)).setdefault(
        "assign", {})[key] = int(dock_id)


def begin_docked(name: str, dock_id: int = 0) -> bool:
    """``Begin`` for a window that lives in a dock node.

    Windows sharing a node are its tabs: each gets a header on the node's top
    edge, and the one selected gets the body. Returns whether *this* window is
    the one on top -- so a port writes the same ``if Begin(...): ... End()``
    it writes anywhere else.
    """
    from .im_core import split_label

    ctx = get_current_context()
    title, key = split_label(name)
    assigned = ctx.state(("dock",)).get("assign", {}).get(key)
    dock_id = int(dock_id or assigned or 0)
    if not dock_id:
        return begin(name)

    node = ctx.dock_node(dock_id)
    if key not in node["windows"]:
        node["windows"].append(key)
    if node["selected"] is None:
        node["selected"] = key

    x, y, w, h = node["box"]
    tab_h = _frame_height(ctx)
    set_cursor_screen_pos((x, y))
    ctx.layout.reset(x, y, w, tab_h)
    for index, other in enumerate(node["windows"]):
        if index:
            same_line(0.0, 2.0)
        shown = split_label(other)[0]
        width = ctx.draw.calc_text_size(shown)[0] + ctx.style.frame_padding[0] * 2.0
        box = ctx.layout.row(height=tab_h, width=width)
        hovered, _held, pressed = ctx.button_behavior(box, ctx.get_id("##dock" + other))
        if pressed:
            node["selected"] = other
        selected = node["selected"] == other
        ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                                 _col(Col.TAB_SELECTED if selected
                                      else (Col.HEADER_HOVERED if hovered else Col.TAB)),
                                 0.0)
        ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]),
                          _col(Col.TEXT), shown)

    on_top = node["selected"] == key
    body = (x, y + tab_h, w, max(h - tab_h, 1.0))
    ctx.begin(name, body)
    window = ctx.current_window
    if window is not None:
        window.dock_id = dock_id
        window.dock_tab_active = on_top
    return on_top


def end_docked() -> None:
    """``End`` for :func:`begin_docked`."""
    get_current_context().end()


__all__ += [
    "ConfigFlags", "BackendFlags", "nav_tab", "process_nav_keys", "get_nav_id",
    "set_nav_id", "is_item_nav_focused", "get_nav_ring", "dock_space",
    "dock_space_over_viewport", "set_next_window_dock_id", "get_window_dock_id",
    "is_window_docked", "dock_builder_split_node", "dock_builder_dock_window",
    "begin_docked", "end_docked",
]
