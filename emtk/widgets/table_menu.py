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
    """Build ``(entries, calls)`` for the declared items; *calls* is parallel to entries."""
    from .menus import MenuItem

    entries, calls = [], []
    for spec in binding.context_menu:
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
    return entries, calls


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
        close()
        if index is not None and index < len(calls) and callable(calls[index]):
            fn = calls[index]
            fn(record, column) if _accepts(fn, 2) else fn(record)

    overlays.popup(("table-menu", name), panel, on_close=close, on_pick=picked)
