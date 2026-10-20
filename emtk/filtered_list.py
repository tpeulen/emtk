"""A filter field that stays put above the list it narrows.

A filter typed at the top of a list is only useful while it can be seen. Drawn
as the first item *inside* the list's scrolling region, it scrolls away with
the first rows, and the user who scrolled down to look at the matches has to
scroll back up to change what they match. The supported pattern is therefore
two regions: the field (and any toolbar row above it) is laid out in the
parent, and the list scrolls in the height that is left::

    changed, query = im.begin_filtered_list("tools", query, "Filter tools")
    for name in names:
        if query.casefold() in name.casefold():
            im.selectable(name)
    im.end_filtered_list()

The list is an ordinary :func:`emtk.im.begin_child`, so its rows are clipped to
it and never drawn over the field, and the wheel scrolls it and not the parent.
Anything drawn *before* :func:`begin_filtered_list` (a toolbar, a caption) is
fixed too; :func:`filter_field` alone draws the field when the list is not one
child (a table, a tree drawn by someone else).

The field speaks the keyboard of a search box:

* **Escape** clears the text; pressed again on an empty field, it lets go of
  the keyboard.
* **Down** moves the focus to the first entry of the list; **Up** and **Down**
  then walk the entries, the list scrolling to keep the focused one in view,
  **Enter** activates it, and **Up** on the first entry (or **Escape** on any) goes back to the
  field with its text selected, so typing starts a new filter.

A data table needs none of this: :class:`emtk.widgets.data_table.DataTable`
keeps its own filter and header above its rows, and pins them to the top of a
scrolled parent as well.
"""
from __future__ import annotations

from typing import Any

from . import im_core as _core
from . import im_widgets as _w
from .keys import KEY_DOWN, KEY_ESCAPE, KEY_UP

__all__ = ["begin_filtered_list", "end_filtered_list", "filter_field"]


def _pressed(io, key: int) -> bool:
    """Whether *key* went down this frame (as an event, or as the frame's one key)."""
    return io.key == key or any(event[0] == key for event in io.key_events)


def _spend(ctx, key: int) -> None:
    """Take *key* out of this frame's input, so nothing after the caller acts on it too."""
    io = ctx.io
    if io.key == key:
        io.key = 0
    io.key_events[:] = [event for event in io.key_events if event[0] != key]
    ctx.request_frame()


def _list_state(ctx, list_id: Any) -> dict:
    return ctx.state(("filtered_list", list_id))


def _focus_field(ctx, item_id: Any) -> None:
    ctx.state(("focus",))["id"] = item_id
    _w.set_nav_id(item_id)


def filter_field(label: str, value: str, hint: str = "", *, list_id: Any = None,
                 tooltip: str = "") -> tuple[bool, str]:
    """A full-width filter field: :func:`emtk.im.input_text_with_hint` with search-box keys.

    Parameters
    ----------
    label : str
        The field's id (``"##tool filter"``); a visible label is drawn after it as for any input.
    value : str
        The text typed so far.
    hint : str
        Shown while the field is empty ("Filter tools").
    list_id : hashable, optional
        The list the Down key moves into (what :func:`begin_filtered_list` was given). Without
        one, Down is left to the field.
    tooltip : str
        What hovering the field explains ("Find tools by name or description.").

    Returns
    -------
    (bool, str)
        Whether the text changed this frame, and the text.

    Notes
    -----
    The width is the region's unless :func:`emtk.im.set_next_item_width` said otherwise, so a
    button can share the row.
    """
    ctx = _core.get_current_context()
    item_id = ctx.get_id(label)
    focus = ctx.state(("focus",))
    focused = focus.get("id") == item_id or ctx.is_nav_focused(item_id)
    cleared = False
    if focused and _pressed(ctx.io, KEY_ESCAPE):
        _spend(ctx, KEY_ESCAPE)
        if value:
            value, cleared = "", True
        else:
            focus.pop("id", None)
            _w.set_nav_id(None)
    elif focused and list_id is not None and _pressed(ctx.io, KEY_DOWN):
        _spend(ctx, KEY_DOWN)
        focus.pop("id", None)
        _w.set_nav_id(None)
        _list_state(ctx, list_id)["enter"] = True
    changed, value = _w.input_text_with_hint(label, value, hint)
    if tooltip:
        _w.set_item_tooltip(tooltip)
    return (changed or cleared, value)


def begin_filtered_list(str_id: str, value: str, hint: str = "", *,
                        height: float | None = None, stretch: bool = False,
                        min_height: float = 40.0, tooltip: str = "") -> tuple[bool, str]:
    """Draw a filter field, then open the scrolling list below it.

    Always pair with :func:`end_filtered_list`, whatever this returns.

    Parameters
    ----------
    str_id : str
        Identifies the field and the list (their scroll and focus outlive the frame).
    value, hint, tooltip : str
        As for :func:`filter_field`.
    height : float, optional
        The list's height. ``None`` takes the height left in the region; a negative value
        leaves that much below the list (a status line drawn after it).
    stretch : bool
        Take the height left *less what is drawn after the list* in the region (a button row),
        measured as :func:`emtk.im.stretch_height` does; overrides *height*.
    min_height : float
        The least a stretched list is given; what follows then scrolls with the region.

    Returns
    -------
    (bool, str)
        Whether the filter text changed this frame, and the text.
    """
    ctx = _core.get_current_context()
    ctx.push_id(str_id)
    changed, value = filter_field("##filter", value, hint, list_id=str_id, tooltip=tooltip)
    state = _list_state(ctx, str_id)
    entering = bool(state.pop("enter", False))
    if changed:
        # New matches start at the top: an old scroll can hide every one of them.
        _w.set_child_scroll_y(_child_key(ctx), 0.0)
    if stretch:
        list_h = _w.stretch_height("##list-fill", minimum=float(min_height))
    else:
        list_h = float(height) if height is not None else 0.0
    _w.begin_child("##list", (0.0, list_h))
    if entering:
        _w.set_scroll_y(0.0)
        ctx.nav_focus_next = True
    ctx.push_id("##rows")
    _open_lists(ctx).append(len(ctx.nav_ring))
    return (changed, value)


def _open_lists(ctx) -> list:
    """The lists begun and not yet ended in this frame: where each one's entries start in the ring."""
    stack = getattr(ctx, "_filtered_lists", None)
    if stack is None:
        stack = ctx._filtered_lists = []
    return stack


def _child_key(ctx) -> tuple:
    """The storage key :meth:`emtk.im_core.Context.begin_child` gives the list."""
    return ("__child__", *ctx._ids, "##list")


def end_filtered_list() -> tuple:
    """Close the list :func:`begin_filtered_list` opened.

    Walks the focus with Up and Down among the entries submitted in it, keeps the focused one in
    view, and outlines it.

    Returns
    -------
    tuple of float
        The list's box, ``(x, y, w, h)``.
    """
    ctx = _core.get_current_context()
    start = _open_lists(ctx).pop()
    ctx.pop_id()                                     # "##rows"
    entries = ctx.nav_ring[start:]
    io = ctx.io
    if ctx.nav_id in entries:
        at = entries.index(ctx.nav_id)
        if _pressed(io, KEY_ESCAPE):
            _spend(ctx, KEY_ESCAPE)
            _focus_field(ctx, ctx.get_id("##filter"))
        elif _pressed(io, KEY_DOWN):
            _spend(ctx, KEY_DOWN)
            _w.set_nav_id(entries[min(at + 1, len(entries) - 1)])
        elif _pressed(io, KEY_UP):
            _spend(ctx, KEY_UP)
            if at == 0:
                _focus_field(ctx, ctx.get_id("##filter"))
            else:
                _w.set_nav_id(entries[at - 1])
        rect = ctx.nav_rect
        child = ctx._child[-1] if ctx._child else None
        if rect is not None and child is not None and ctx.nav_id in entries:
            box, scroll = child[1], float(child[2].get("scroll_y", 0.0))
            top, bottom = rect[1], rect[1] + rect[3]
            if top < box[1]:
                _w.set_scroll_y(max(scroll - (box[1] - top), 0.0))
                ctx.request_frame()
            elif bottom > box[1] + box[3]:
                _w.set_scroll_y(scroll + bottom - (box[1] + box[3]))
                ctx.request_frame()
            if ctx.nav_visible:
                x, y, w, h = rect
                ctx.draw.add_rect((x + 1, y + 1), (x + w - 1, y + h - 1),
                                  _w._col(_core.Col.NAV_HIGHLIGHT), ctx.style.frame_rounding,
                                  thickness=1.0)
    box = _w.end_child()
    ctx.pop_id()                                     # str_id
    return box
