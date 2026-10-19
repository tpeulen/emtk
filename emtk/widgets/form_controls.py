"""Form controls a Qt port expects and Dear ImGui lacks.

* :func:`checkbox_tristate` -- ``QCheckBox`` with ``setTristate``: checked,
  unchecked, or *partially* checked (``None``), the state a "select all" box
  over a half-selected list is in.
* :func:`input_text_completer` -- ``QLineEdit`` with a ``QCompleter``: a text
  field that offers the known values matching what is typed, in a list under
  it, without fencing the field in (anything may still be typed).
* :func:`key_sequence_input` -- ``QKeySequenceEdit``: press a shortcut to
  record it; :func:`chord_name` spells one (``"Ctrl+Shift+K"``). The value is
  an ``im`` key chord (key | ``MOD_*``), what :func:`emtk.im.shortcut` and
  :func:`emtk.im.is_key_chord_pressed` take.
* :func:`begin_tool_box` / :func:`tool_box_item` / :func:`end_tool_box` --
  ``QToolBox``: a column of pages under headers, exactly one open at a time.

What is deliberately *not* here, and why, is in the widget inventory of the
documentation (``docs/qt_widgets.rst``): ``QStackedWidget`` is an ``if`` in
immediate mode, ``QSpinBox`` is ``im.input_int`` with a step, and so on.
"""
from __future__ import annotations

from collections.abc import Sequence

from .. import im_widgets as _w
from .. import keys as _keys
from .. import style as _style
from ..events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from ..i18n import tr
from ..im_core import Col, ItemFlags, get_current_context

__all__ = [
    "begin_tool_box",
    "checkbox_tristate",
    "chord_from_event",
    "chord_name",
    "completions",
    "end_tool_box",
    "input_text_completer",
    "key_sequence_input",
    "tool_box_item",
]


# --------------------------------------------------------------------------- #
# Tristate checkbox
# --------------------------------------------------------------------------- #
def checkbox_tristate(label: str, value: bool | None,
                      user_tristate: bool = False) -> tuple[bool, bool | None]:
    """A checkbox with a third, *partial* state (``None``): ``(changed, value)``.

    The partial state is drawn as a bar across the box. A click on a partial
    box checks it and a click on a checked one clears it -- the partial state
    is usually *computed* (some of the rows below are selected), so the user
    does not click their way into it. ``user_tristate=True`` lets them:
    unchecked, partial, checked, as Qt cycles a user-tristate box.
    """
    if value is not None:
        value = bool(value)
    ctx = get_current_context()
    height = _w._frame_height(ctx)
    shown = _w._visible_label(label)
    box, lines, line_h = _w._labelled_row(ctx, height, shown)
    item_id = ctx.get_id(label)
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    mark = (box[0], box[1], height, height)
    ctx.draw.add_rect_filled((mark[0], mark[1]), (mark[0] + height, mark[1] + height),
                             _w._col(Col.BUTTON_HOVERED) if hovered else _w._col(Col.FRAME_BG),
                             ctx.style.frame_rounding)
    _w._frame_border(ctx, mark)
    _w._nav_ring(ctx, box, item_id)
    new = value
    if pressed:
        if user_tristate:
            new = None if value is False else value is None
        else:
            new = not bool(value) if value is not None else True
    pad = height * 0.28
    if new is None:
        ctx.draw.add_rect_filled((mark[0] + pad, mark[1] + height * 0.42),
                                 (mark[0] + height - pad, mark[1] + height * 0.58), _w._col(Col.CHECK_MARK))
    elif new:
        ctx.draw.add_line((mark[0] + pad, mark[1] + height * 0.5),
                          (mark[0] + height * 0.45, mark[1] + height - pad), _w._col(Col.CHECK_MARK), 2.0)
        ctx.draw.add_line((mark[0] + height * 0.45, mark[1] + height - pad),
                          (mark[0] + height - pad, mark[1] + pad), _w._col(Col.CHECK_MARK), 2.0)
    _w._draw_label_lines(ctx, box, height, lines, line_h)
    return (pressed and new != value), new


# --------------------------------------------------------------------------- #
# Text field with completions
# --------------------------------------------------------------------------- #
def completions(text: str, candidates: Sequence[str], limit: int = 8) -> list[str]:
    """The *candidates* offered for *text*: prefix matches first, then the others containing it.

    Case does not matter; a candidate equal to the text is not offered (there
    is nothing left to complete). An empty text offers nothing.
    """
    needle = str(text or "").strip().lower()
    if not needle:
        return []
    prefix, inner = [], []
    for candidate in candidates:
        low = str(candidate).lower()
        if low == needle:
            continue
        if low.startswith(needle):
            prefix.append(str(candidate))
        elif needle in low:
            inner.append(str(candidate))
    return (prefix + inner)[: max(0, int(limit))]


def input_text_completer(label: str, value: str, candidates: Sequence[str], hint: str = "",
                         max_items: int = 8) -> tuple[bool, str]:
    """A text field that offers matching *candidates* while typing (``QCompleter``): ``(changed, text)``.

    The list opens under the field as soon as the text matches something; Down
    / Up move through it, Enter (or a click) takes the highlighted entry, and
    Escape closes it until the text changes. The field keeps the keyboard all
    the while -- typing goes on narrowing the list -- which is why the list is
    drawn over the frame without taking its input, unlike a combo's: the
    pointer over it is claimed for the list so nothing under it hovers or
    takes the click.
    """
    ctx = get_current_context()
    item_id = ctx.get_id(label)
    store = ctx.get_storage(("completer", item_id))
    list_rect = store.get("rect")
    list_id = (*item_id, "list")
    io = ctx.io
    # The list from last frame sits over whatever is drawn after this field: claim the pointer
    # over it first, so the controls under it neither hover nor take the click meant for a row.
    over_list = (list_rect is not None and io.mouse_pos != (-1.0, -1.0)
                 and _style.hit(*io.mouse_pos, *list_rect))
    if over_list:
        ctx.hovered_id = list_id
        if io.mouse_clicked[0]:
            ctx.set_active_id(list_id)
            store["pressed"] = True
    focused_before = ctx.is_nav_focused(item_id) or ctx.state(("focus",)).get("id") == item_id
    offered = completions(value, candidates, max_items) if store.get("dismissed") != value else []
    highlight = int(store.get("highlight", -1))
    if highlight >= len(offered):
        highlight = -1
    accepted: str | None = None
    if focused_before and offered:
        for key, _mods in _w_take(ctx, (_keys.KEY_DOWN, _keys.KEY_UP, _keys.KEY_ESCAPE)
                                  + ((_keys.KEY_RETURN, _keys.KEY_ENTER) if highlight >= 0 else ())):
            if key == _keys.KEY_DOWN:
                highlight = min(len(offered) - 1, highlight + 1)
            elif key == _keys.KEY_UP:
                highlight = max(-1, highlight - 1)
            elif key == _keys.KEY_ESCAPE:
                store["dismissed"] = value
                offered, highlight = [], -1
            elif highlight >= 0:
                accepted = offered[highlight]
    changed = False
    if accepted is not None:
        value, changed = accepted, True
        store["dismissed"] = value
        offered, highlight = [], -1
    # A press on a row is not a press "elsewhere": the field keeps the keyboard (and the list).
    clicked = io.mouse_clicked[0]
    if over_list:
        io.mouse_clicked[0] = False
    try:
        _edited, text = _w.input_text(label, value, hint)
    finally:
        io.mouse_clicked[0] = clicked
    field_box = ctx._last_item
    if text != value:
        value, changed = text, True
        store.pop("dismissed", None)
        offered = completions(value, candidates, max_items)
        highlight = -1
    focused = ctx.is_nav_focused(item_id) or ctx.state(("focus",)).get("id") == item_id
    picked = store.pop("picked", None)
    if picked is not None:
        value, changed = picked, True
        store["dismissed"] = value
        offered = []
    store["highlight"] = highlight
    if not (focused and offered):
        store["rect"] = None
        store.pop("pressed", None)
        if ctx.active_id == list_id:
            ctx.clear_active_id()
        return changed, value
    # The list: under the field (above it when there is no room), as wide as the field's frame.
    pad_x, pad_y = ctx.style.frame_padding
    row_h = ctx.p.line_height() + pad_y
    label_w = (ctx.draw.calc_text_size(_w._visible_label(label))[0] + ctx.style.item_inner_spacing[0]
               if _w._visible_label(label) else 0.0)
    width = max(60.0, field_box[2] - label_w)
    height = row_h * len(offered) + 2.0
    x, y = field_box[0], field_box[1] + field_box[3] + 1.0
    _fx, fy, _fw, fh = ctx.box
    if y + height > fy + fh and field_box[1] - height - 1.0 >= fy:
        y = field_box[1] - height - 1.0
    rect = (x, y, width, height)
    store["rect"] = rect

    def draw(octx) -> bool:
        oio = octx.io
        octx.draw.add_rect_filled((x, y), (x + width, y + height), _w._col(Col.POPUP_BG))
        octx.draw.add_rect((x, y), (x + width, y + height), _w._col(Col.BORDER))
        hot = -1
        if oio.mouse_pos != (-1.0, -1.0) and _style.hit(*oio.mouse_pos, *rect):
            hot = int((oio.mouse_pos[1] - y - 1.0) // row_h)
        for index, entry in enumerate(offered):
            ry = y + 1.0 + index * row_h
            if index == highlight or index == hot:
                octx.draw.add_rect_filled((x + 1.0, ry), (x + width - 1.0, ry + row_h),
                                          _w._col(Col.HEADER_HOVERED if index == hot else Col.HEADER))
            shown = _w._elided(octx, entry, width - 2.0 * pad_x)
            octx.draw.add_text((x + pad_x, ry + pad_y / 2.0), _w._col(Col.TEXT), shown)
        if oio.mouse_released[0] and store.pop("pressed", False):
            if 0 <= hot < len(offered):
                store["picked"] = offered[hot]
            if octx.active_id == list_id:
                octx.clear_active_id()
            octx.request_frame()
        return False        # drawn this frame only; the field puts it up again while it is wanted

    ctx.add_overlay(("completer", item_id), draw)
    ctx._last_item, ctx._last_id = field_box, item_id
    return changed, value


def _w_take(ctx, wanted):
    from .calendar import (
        _take_keys,
    )

    return _take_keys(ctx, wanted)


# --------------------------------------------------------------------------- #
# Key sequence
# --------------------------------------------------------------------------- #
#: Qt's modifier key codes: pressing one alone is not a shortcut, it is the start of one.
_MODIFIER_KEYS = frozenset({0x01000020, 0x01000021, 0x01000022, 0x01000023, 0x01001103})

_KEY_NAMES = {
    _keys.KEY_ESCAPE: "Esc", _keys.KEY_TAB: "Tab", _keys.KEY_BACKSPACE: "Backspace",
    _keys.KEY_RETURN: "Return", _keys.KEY_ENTER: "Enter", _keys.KEY_DELETE: "Del",
    _keys.KEY_INSERT: "Ins", _keys.KEY_HOME: "Home", _keys.KEY_END: "End",
    _keys.KEY_LEFT: "Left", _keys.KEY_UP: "Up", _keys.KEY_RIGHT: "Right", _keys.KEY_DOWN: "Down",
    _keys.KEY_PAGE_UP: "PgUp", _keys.KEY_PAGE_DOWN: "PgDown", _keys.KEY_SPACE: "Space",
    **{getattr(_keys, f"KEY_F{n}"): f"F{n}" for n in range(1, 13)},
}


def chord_from_event(key: int, modifiers: int) -> int:
    """An ``im`` chord (key | ``MOD_*``) from a host key event (key, ``*_MODIFIER`` bits).

    A letter is folded to the lower-case ordinal :mod:`emtk.keys` uses, so
    ``Qt.Key_K`` and ``ord("k")`` are the same chord.
    """
    key = int(key)
    if 65 <= key <= 90:
        key += 32
    mods = ((_keys.MOD_CTRL if modifiers & CONTROL_MODIFIER else 0)
            | (_keys.MOD_SHIFT if modifiers & SHIFT_MODIFIER else 0)
            | (_keys.MOD_ALT if modifiers & ALT_MODIFIER else 0)
            | (_keys.MOD_SUPER if modifiers & META_MODIFIER else 0))
    return key | mods


def chord_name(chord: int) -> str:
    """``"Ctrl+Shift+K"`` for a chord; ``""`` for none (0)."""
    chord = int(chord or 0)
    key = chord & ~_keys.MOD_MASK
    if not key:
        return ""
    parts = [name for bit, name in ((_keys.MOD_CTRL, "Ctrl"), (_keys.MOD_ALT, "Alt"),
                                    (_keys.MOD_SHIFT, "Shift"), (_keys.MOD_SUPER, "Meta"))
             if chord & bit]
    if key in _KEY_NAMES:
        parts.append(_KEY_NAMES[key])
    elif 32 < key < 0x110000:
        parts.append(chr(key).upper())
    else:
        parts.append("0x%X" % key)
    return "+".join(parts)


def key_sequence_input(label: str, chord: int) -> tuple[bool, int]:
    """Record a keyboard shortcut (``QKeySequenceEdit``): ``(changed, chord)``.

    A click (or Enter with the keyboard focus on it) starts recording; the next
    key pressed with its modifiers is the shortcut. Escape cancels the
    recording and keeps the old one; Backspace or Delete with no modifier
    clears it (0). Pressing only a modifier waits for the key that completes it.
    """
    ctx = get_current_context()
    item_id = ctx.get_id(label)
    store = ctx.get_storage(("key_sequence", item_id))
    shown = _w._visible_label(label)
    label_w = (ctx.draw.calc_text_size(shown)[0] + ctx.style.item_inner_spacing[0]) if shown else 0.0
    total = ctx.layout.row(height=_w._frame_height(ctx),
                           width=_w._labelled_item_width(ctx, ctx.take_next_item_width(None), label_w))
    box = (total[0], total[1], max(1.0, total[2] - label_w), total[3])
    hovered, _held, pressed = ctx.button_behavior(box, item_id)
    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    io = ctx.io
    changed = False
    recording = bool(store.get("recording")) and not disabled
    if pressed and not disabled:
        _w.set_nav_id(item_id)
        recording = not recording               # a second click cancels
    elif recording and io.mouse_clicked[0] and not hovered:
        recording = False                       # a click elsewhere cancels
    if recording and not ctx.is_nav_focused(item_id):
        recording = False
    if recording and not pressed:
        events = [event for event in io.key_events if event[0] not in _MODIFIER_KEYS and event[0]]
        if not events and io.key and io.key not in _MODIFIER_KEYS:
            events = [(io.key, io.text, _w._current_modifiers(io))]
        if events:
            key, _text, mods = events[0]
            io.key_events[:] = []
            io.key, io.text = 0, ""
            ctx.request_frame()
            recording = False
            if key == _keys.KEY_ESCAPE and not mods:
                pass
            elif key in (_keys.KEY_BACKSPACE, _keys.KEY_DELETE) and not mods:
                changed, chord = chord != 0, 0
            else:
                new = chord_from_event(key, mods)
                changed, chord = new != chord, new
        else:
            ctx._want_text_input = True
    store["recording"] = recording
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _w._col(Col.FRAME_BG_ACTIVE) if recording
                             else (_w._col(Col.FRAME_BG_HOVERED) if hovered else _w._col(Col.FRAME_BG)),
                             ctx.style.frame_rounding)
    _w._frame_border(ctx, box)
    if recording:
        text, colour = tr("Press a shortcut…", domain="emtk"), _w._col(Col.TEXT_DISABLED)
    elif chord:
        text, colour = chord_name(chord), _w._col(Col.TEXT)
    else:
        text, colour = tr("None", domain="emtk"), _w._col(Col.TEXT_DISABLED)
    text = _w._elided(ctx, text, box[2] - 2.0 * ctx.style.frame_padding[0])
    ctx.draw.add_text((box[0] + ctx.style.frame_padding[0], box[1] + ctx.style.frame_padding[1]), colour, text)
    _w._nav_ring(ctx, box, item_id)
    if shown:
        ctx.draw.add_text((box[0] + box[2] + ctx.style.item_inner_spacing[0], box[1] + ctx.style.frame_padding[1]),
                          _w._col(Col.TEXT), shown)
    ctx._last_item, ctx._last_id = box, item_id
    return changed, chord


# --------------------------------------------------------------------------- #
# Tool box
# --------------------------------------------------------------------------- #
def begin_tool_box(str_id: str, current: int | None = None) -> bool:
    """Start a ``QToolBox``: headers of which exactly one is open. Always pair with :func:`end_tool_box`.

    *current* forces the open page (a caller that owns it); ``None`` leaves it
    to the user, starting with the first.
    """
    ctx = get_current_context()
    ctx.push_id(("tool_box", str_id))
    state = ctx.get_storage("__tool_box__")
    if current is not None:
        state["current"] = int(current)
    state.setdefault("current", 0)
    state["index"] = 0
    return True


def tool_box_item(label: str) -> bool:
    """The next page's header; ``True`` when it is the open page and its body should be drawn.

    A click on a closed header opens it and closes the open one; a click on the
    open one keeps it open -- a tool box always shows one page.
    """
    ctx = get_current_context()
    state = ctx.get_storage("__tool_box__")
    index = state.get("index", 0)
    state["index"] = index + 1
    was_open = state.get("current", 0) == index
    now_open = _w.collapsing_header(label, was_open)
    if now_open and not was_open:
        state["current"] = index
        ctx.request_frame()
    return was_open or (now_open and not was_open)


def end_tool_box() -> int:
    """End the tool box; returns the open page's index."""
    ctx = get_current_context()
    state = ctx.get_storage("__tool_box__")
    current = int(state.get("current", 0))
    count = int(state.get("index", 0))
    if count and current >= count:
        state["current"] = count - 1
    ctx.pop_id()
    return current
