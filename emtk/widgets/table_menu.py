"""The popup context menu of a declarative ``data_table``.

A table section declares it with ``context_menu``::

    "context_menu": [
        {"label": "Copy row", "call": "copy_row", "description": "...",
         "enabled_when": "has_rows"},
        {"separator": true},
        ...
    ]

It opens on a right click of a row (at the pointer) or on Shift+F10 / the Menu
key (at the selected row), is drawn as an emtk popup that closes on Escape, a
pick or a press outside, and each item calls the model method ``call`` with the
row it was opened on. A method that takes a second positional argument is also
handed the key of the column under the pointer (``None`` from the keyboard).
``enabled_when`` names a model attribute or method (called with the row) that
says whether the item can run; a disabled item is still shown, dimmed.

An item with ``items_source`` instead of ``call`` is filled from the model when
the menu opens: the method (called with the row) returns a list of
``{"label", "call", "description", "enabled"}`` dicts whose ``call`` is a
callable taking the row -- the items a menu cannot know beforehand ("Open in
<tool>" for the tools that take this row). A dict with a ``group`` lands in a submenu of that
name. An empty list draws the item's own
``label`` dimmed, so the menu says the action exists but has nothing to offer.
Labels and descriptions go through ``tr()``; a description is the item's tooltip.
"""
from __future__ import annotations

import inspect
from typing import Any

from ..keys import KEY_F10

#: Qt's ``Key_Menu``, the context-menu key.
KEY_MENU = 0x01000055


def request(binding: Any, record: Any, column: Any, x: float, y: float) -> None:
    """Ask for the menu to open at ``(x, y)`` on *record* (called on a right click)."""
    if getattr(binding, "context_menu", None):
        binding.menu_request = (record, column, float(x), float(y))


def _entries(binding: Any, record: Any):
    """Build ``(entries, calls)`` for the declared items; *calls* is parallel to entries.

    An ``items_source`` item may carry ``group``: those items go into a submenu of that name
    (their calls are found by item through ``binding._menu_picks``)."""
    from .menus import Menu, MenuItem

    entries, calls, picks = [], [], {}
    for spec in binding.context_menu:
        if spec.get("items_source"):
            source = binding._lookup(str(spec["items_source"]))
            items = []
            if callable(source):
                items = list((source(record) if _accepts(source, 1) else source()) or [])
            if not items and spec.get("label"):
                entries.append(MenuItem(str(spec["label"]), enabled=False,
                                        tooltip=spec.get("description") or None))
                calls.append(None)
            submenus: dict[str, list] = {}
            loose: list = []
            for item in items:
                call = item.get("call")
                entry = MenuItem(str(item.get("label", "")),
                                 enabled=bool(item.get("enabled", True)) and callable(call),
                                 tooltip=item.get("description") or None)
                bound = _RowCall(call) if callable(call) else None
                group = str(item.get("group") or "")
                if group:
                    submenus.setdefault(group, []).append(entry)
                else:
                    loose.append((entry, bound))
                picks[id(entry)] = bound
            if submenus:
                # the grouped items hang under the item's own label: Open in… > group > tool
                entries.append(Menu(str(spec.get("label") or ""),
                                    [e for e, _ in loose] + [Menu(g, m) for g, m in submenus.items()]))
                calls.append(None)
            else:
                for entry, bound in loose:
                    entries.append(entry)
                    calls.append(bound)
            continue
        if spec.get("separator") or not spec.get("label"):
            entries.append(None)
            calls.append(None)
            continue
        enabled = True
        gate = spec.get("enabled_when")
        if gate:
            fn = binding._lookup(str(gate))
            enabled = bool(fn(record) if callable(fn) and _accepts(fn, 1) else
                           fn() if callable(fn) else fn)
        call = binding._lookup(str(spec.get("call", "")))
        entries.append(MenuItem(str(spec["label"]), enabled=enabled and callable(call),
                                tooltip=spec.get("description") or None))
        calls.append(call)
    binding._menu_picks = picks
    return entries, calls


class _RowCall:
    """An ``items_source`` entry's call: it takes the row only, whatever else its signature allows."""

    def __init__(self, call: Any) -> None:
        self.call = call

    def __call__(self, record: Any) -> Any:
        return self.call(record)


def _accepts(fn: Any, n: int) -> bool:
    """Whether *fn* takes at least *n* positional arguments."""
    try:
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if any(p.kind is p.VAR_POSITIONAL for p in inspect.signature(fn).parameters.values()):
            return True
        return len(params) >= n
    except (TypeError, ValueError):
        return False


def _keyboard_request(binding: Any, control: Any) -> None:
    """Open the menu at the selected row (Shift+F10 / Menu key)."""
    indices = control.selected_indices()
    if not indices or control._body_box is None:
        return
    index = indices[0]
    order = control.order()
    position = next((p for p, i in enumerate(order) if i == index), None)
    if position is None:
        return
    bx, by, bw, _bh = control._body_box
    row = control._row_h
    y = by + (position - control.bar.top) * row + row
    x = bx + min(24.0, bw / 2)
    request(binding, binding.record(index), None, x, y)


def draw(binding: Any, name: str, hovered: bool) -> None:
    """Keep the table's context menu up while it is open; run what is picked."""
    if not getattr(binding, "context_menu", None):
        return
    from .. import im_core as core
    from .. import overlays
    from .menus import Popup

    io = core.get_current_context().io
    control = binding.control
    if hovered and (io.key == KEY_MENU or (io.key == KEY_F10 and io.key_shift)):
        _keyboard_request(binding, control)
    asked = getattr(binding, "menu_request", None)
    if asked is not None:
        binding.menu_request = None
        record, column, x, y = asked
        entries, calls = _entries(binding, record)
        panel = Popup(entries)
        panel.open_at(x, y)
        binding.menu_panel, binding._menu_calls = panel, calls
        binding._menu_target = (record, column)
    panel = getattr(binding, "menu_panel", None)
    if panel is None:
        return

    def close() -> None:
        binding.menu_panel = None

    def picked(item: Any) -> None:
        index = next((i for i, row in enumerate(panel.entries) if row is item), None)
        calls = binding._menu_calls
        record, column = binding._menu_target
        fn = calls[index] if index is not None and index < len(calls) else None
        if not callable(fn):
            fn = getattr(binding, "_menu_picks", {}).get(id(item))
        close()
        if callable(fn):
            fn(record, column) if _accepts(fn, 2) else fn(record)

    overlays.popup(("table-menu", name), panel, on_close=close, on_pick=picked)
