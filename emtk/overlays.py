"""``emtk.overlays`` -- a combo's list and a context menu, over an immediate-mode frame.

A closed combo box is one row; its list is drawn **over** everything else and
takes the pointer and the keys while it is up. An immediate-mode frame draws
as it goes, so "over everything" is "after everything": the list is an
*overlay* (:meth:`emtk.im_core.Context.add_overlay`), queued while the frame is
submitted and run at its end, and while it is open the next frame's input is
held back for it -- nothing under it hovers, the wheel scrolls it, and a click
outside closes it without reaching what is behind.

What is drawn is a :class:`emtk.widgets.menus.Popup`: placed inside the frame
(below its field, flipped above it, or shifted and capped to the frame, never
outside), as wide as its widest row, scrolled with the wheel, a scrollbar or
the keyboard. A combo's list of :data:`~emtk.widgets.menus.FILTER_MIN_ITEMS`
items or more opens with a filter field at its top, which takes the keys:
typing narrows the list to the items containing every word typed. So a host
draws nothing and routes nothing:

.. code-block:: python

    key = ctx.get_id("##unit")
    picked = overlays.take_choice(key)          # picked last frame, or None
    if picked is not None:
        current = picked
    if combo_field_clicked:                     # the closed field was clicked
        overlays.combo_list(key, labels, current, below=field_rect)
    else:
        overlays.combo_list(key, labels, current)

:func:`popup` puts up any :class:`~emtk.widgets.menus.Popup` the same way --
a context menu with submenus and rules -- and returns the item picked.
Everything is in the frame's logical coordinates.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from . import im_core as _core

__all__ = ["popup", "combo_list", "take_choice", "is_open", "holding", "open_panels"]


def _state(key: Any) -> dict:
    return _core.get_current_context().state(("overlay", key))


def popup(key: Any, panel, on_close=None, on_pick=None):
    """Keep *panel* (an open :class:`~emtk.widgets.menus.Popup`) up this frame,
    over everything, and return the item picked since the last call.

    Call it every frame while the popup should exist; it is drawn at the end
    of the frame, fed the frame's pointer, wheel and keys, and closes itself on
    a pick, Escape or a press outside.

    Parameters
    ----------
    key : hashable
        Identifies the popup across frames.
    panel : emtk.widgets.menus.Popup
        Opened by the caller (``open_at`` / ``open_below``).
    on_close : callable, optional
        Called once when it closes without a pick.
    on_pick : callable, optional
        ``on_pick(item)`` at the end of the frame the item is picked in --
        after the frame drew, before the host's next event -- instead of
        returning the item on the next call. What a context menu's actions
        want: they run when the click lands, as a menu bar's do.

    Returns
    -------
    MenuItem or None
        The item picked at the end of the previous frame (never, with
        *on_pick*).
    """
    ctx = _core.get_current_context()
    state = _state(key)
    picked = state.pop("picked", None)
    if panel is None or not panel.open:
        state.pop("panel", None)
        return picked
    if state.get("panel") is not panel:
        state["panel"] = panel
        # The frame that opened it has its opening click in the io: a press
        # on the field, which is outside the list and would close it again.
        state["fresh"] = True
    state["on_close"], state["on_pick"] = on_close, on_pick
    ctx.add_overlay(("overlay", key), lambda c: _run(c, state))
    return picked


def _run(ctx, state: dict) -> bool:
    """One frame of an open popup: its input, then its drawing."""
    panel = state["panel"]
    io = ctx.io
    x, y, w, h = ctx.box
    if not state.pop("fresh", False):
        mx, my = io.mouse_pos
        pointer = (mx, my) != (-1.0, -1.0)
        if pointer:
            panel.hover(mx, my)
        if io.mouse_wheel and pointer:
            panel.wheel(mx, my, io.mouse_wheel)
        if io.mouse_down[0] and pointer:
            panel.drag(mx, my)
        if io.mouse_clicked[0]:
            result = panel.press(mx, my, x, y, w, h)
            if result.item is not None:
                state["picked"] = result.item
        elif any(io.mouse_clicked[1:]) and not panel.contains(mx, my) and not panel.modal:
            panel.close()
        if io.mouse_released[0]:
            panel.release()
        # Every key since the last frame, in order, with its modifiers: the
        # filter is a text field, and Cmd+A then "x" is not "x" then Cmd+A.
        from .im_widgets import _current_modifiers  # noqa: PLC0415

        events = list(io.key_events) or (
            [(io.key, io.text, _current_modifiers(io))] if (io.key or io.text) else [])
        for key, text, modifiers in events:
            if not panel.open:
                break
            result = panel.key(key, text, modifiers)
            if result.item is not None:
                state["picked"] = result.item
        if panel.open and panel.filterable:
            ctx._want_text_input = True
    if panel.open:
        panel.draw(ctx.p, x, y, w, h)
        return True
    ctx.request_frame()                 # the pick, or the list gone, shows next frame
    on_close, on_pick = state.get("on_close"), state.get("on_pick")
    if on_pick is not None and "picked" in state:
        on_pick(state.pop("picked"))
    elif on_close is not None and "picked" not in state:
        on_close()
    return False


def _combo(key: Any) -> dict:
    return _core.get_current_context().state(("overlay.combo", key))


def _index(state: dict, item) -> Optional[int]:
    return next((i for i, it in enumerate(state.get("items") or ()) if it is item), None)


def combo_list(key: Any, labels: Sequence[str], current: int,
               below: Optional[Sequence[float]] = None,
               filter: Optional[bool] = None) -> None:
    """The list of a combo box: opened under *below*, kept up while open.

    Call it every frame the combo is drawn, after its closed field; pass the
    field's rect as *below* on the frame the field was clicked. The pick
    arrives through :func:`take_choice` on the next frame.

    Parameters
    ----------
    key : hashable
        The combo's id (``ctx.get_id(...)``), shared with :func:`take_choice`.
    labels : sequence of str
        The options, in order.
    current : int
        The current option: ticked, highlighted, and scrolled into view.
    below : (x, y, w, h), optional
        The closed field; given, the list opens (again) under it.
    filter : bool, optional
        Whether the list has a filter field at its top. ``None`` (the
        default) gives one to a list of at least
        :data:`~emtk.widgets.menus.FILTER_MIN_ITEMS` items.
    """
    from .widgets.menus import FILTER_MIN_ITEMS, MenuItem, Popup

    state = _combo(key)
    if below is not None and labels:
        items = [MenuItem(str(label), checked=(i == current)) for i, label in enumerate(labels)]
        panel = Popup(items)
        if filter is None:
            filter = len(items) >= FILTER_MIN_ITEMS
        panel.open_below(below, current if 0 <= current < len(items) else None,
                         filter=bool(filter))
        state["panel"], state["items"] = panel, items
    panel = state.get("panel")
    if panel is None:
        return
    item = popup(("combo", key), panel)
    if item is not None:
        state["choice"] = _index(state, item)
    if not panel.open:
        state.pop("panel", None)


def take_choice(key: Any) -> Optional[int]:
    """The index picked from the list of combo *key* since the last call, or ``None``.

    The pick is made at the end of a frame, where the list is drawn; the
    combo reads it on the next, before it draws its caption.
    """
    state = _combo(key)
    if "choice" in state:
        return state.pop("choice")
    item = _state(("combo", key)).pop("picked", None)
    return None if item is None else _index(state, item)


def is_open(key: Any) -> bool:
    """Whether the list of combo *key* is up."""
    panel = _combo(key).get("panel")
    return bool(panel is not None and panel.open)


def holding(storage: dict) -> bool:
    """Whether the frames drawn with *storage* have an overlay up.

    For a host that routes presses to chrome of its own before the frame (a
    menu bar drawn with the painter): while a list is up the press belongs
    to the frame, where it picks from the list or closes it.
    """
    return bool(storage.get("__overlays_open__"))


def open_panels(storage: dict) -> list:
    """The popups up in the frames drawn with *storage*, in the order they
    were opened -- what a test or a screenshot script finds a list's rows in
    (:meth:`~emtk.widgets.menus.Popup.row_rect`)."""
    return [value["panel"] for key, value in storage.items()
            if isinstance(key, tuple) and len(key) == 2 and key[0] == "__state__"
            and isinstance(key[1], tuple) and key[1][:1] == ("overlay",)
            and isinstance(value, dict) and value.get("panel") is not None
            and value["panel"].open]
