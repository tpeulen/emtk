"""``emtk.view_form`` -- an AutoForm ``view.json`` drawn as an immediate-mode form.

:mod:`emtk.widgets.view_spec` turns a view spec into rows of the retained
:class:`~emtk.widgets.settings_editor.SettingsEditor`: a searchable list of
settings, one per row, with a group selector and a description footer. That is
the right shape for a configuration panel and the wrong one for a *form* -- a
dialog whose fields sit label-beside-field, several to a line, with *Ok* and
*Cancel* under them, or a strip of controls under a plot. Those are what an
application declares in the same ``view.json`` dialect and needs drawn inside
its own windows, between its own plots.

So this module draws a spec **in place**, with ``im`` widgets, in the current
window:

.. code-block:: python

    spec = load_view_spec("remove_bleaching.view.json")
    state = FormState()
    ...
    im.begin("Remove Photo-bleaching", box)
    draw_form(spec, model, state)
    im.end()

It reads the same dialect AutoForm reads -- ``panel`` (``title``, ``n_col``,
``hidden_when``), ``value`` (``kind`` int/float/str, ``minimum``, ``maximum``,
``decimals``, ``style`` ``"slider"``/``"scientific"``, ``read_only``,
``call``), ``choice`` (``options``, ``labels``, ``options_source``,
``style`` ``"radio"``, ``call``), ``toggle``, ``toggle_row``, ``button_row``,
``info``, and the two table dialects -- ``table`` and ``custom``
``data_table`` (:mod:`emtk.widgets.data_table`), one full-width row each --
and no key of its own. Two things a form needs that the dialect
does not say are asked of the **model**, so the spec stays shared:

``model.enabled(name) -> bool``
    whether the field or action ``name`` is usable right now (an edit box that
    only counts while its checkbox is ticked, *Stop* only while running);
``model.bounds(name) -> (lo, hi)``
    limits that move at run time (a slider over however many series are
    loaded), overriding the spec's ``minimum``/``maximum``.

Typing follows the edit-box convention of the desktop toolkits a port comes
from: the text is edited freely and **committed** on Enter or when the pointer
goes down elsewhere, then parsed, clamped and written. A choice opens a list the
host draws above everything (:attr:`FormState.dropdown_request`), because an
immediate-mode frame has no overlay of its own.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from . import im_core as _core
from . import im_widgets as _w
from .flags import InputTextFlags

__all__ = ["FormState", "draw_form", "draw_sections", "find_section", "section_name",
           "format_value", "parse_value"]

#: Label colour; the style's text colour in the default theme.
_LABEL_COLOUR = (225, 228, 235, 255)

#: Section types that hold other sections.
_CONTAINERS = frozenset({"panel", "group", "box", "tab", "tabs", "row", "column"})


class FormState:
    """What a form remembers between frames.

    Attributes
    ----------
    buffers : dict
        Text being typed into a field, by field name, until it is committed.
    rects : dict
        Screen rectangle of every drawn field or action, by name -- what a
        guided tour spotlights and what a test clicks.
    dropdown_request : tuple or None
        ``(name, rect, labels, index)`` of a choice whose list should open; the
        host draws the list and puts the picked index in
        :attr:`dropdown_result`.
    dropdown_result : dict
        Picked index per choice name, consumed on the next frame.
    on_used : callable or None
        ``on_used(name)`` after a field is committed or an action pressed.
    tables : dict
        The bound table of every table section drawn, by name (its ``source``),
        so its sort, filter, scroll and selection outlive the frame.
    """

    def __init__(self, on_used: Callable[[str], None] | None = None) -> None:
        self.tables: dict[str, Any] = {}
        self.buffers: dict[str, str] = {}
        self.rects: dict[str, tuple] = {}
        self.dropdown_request: tuple | None = None
        self.dropdown_result: dict[str, int] = {}
        self.on_used = on_used

    def used(self, name: str) -> None:
        """Report that the user used *name*."""
        if self.on_used is not None:
            self.on_used(name)


def section_name(section: dict) -> str:
    """The name a section is known by: its ``attr``, ``key`` or ``target``."""
    for key in ("attr", "key", "target"):
        value = section.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def find_section(spec: dict | Sequence, title: str) -> dict | None:
    """The first container whose ``title`` is *title*, searched depth first.

    Parameters
    ----------
    spec : dict or sequence
        A view spec, or a list of sections.
    title : str
        Panel title.

    Returns
    -------
    dict or None
    """
    sections = spec.get("sections", []) if isinstance(spec, dict) else spec
    for section in sections or ():
        if not isinstance(section, dict):
            continue
        if section.get("title") == title:
            return section
        found = find_section(section.get("sections") or [], title)
        if found is not None:
            return found
    return None


def format_value(value: Any, section: dict) -> str:
    """How a ``value`` section shows its number.

    ``decimals`` fixes the digits; ``style: "scientific"`` writes an exponent;
    neither gives the shortest faithful spelling (``0.05``, ``100``).

    Parameters
    ----------
    value : object
        The model's value.
    section : dict
        The section.

    Returns
    -------
    str
    """
    kind = str(section.get("kind", "str")).lower()
    if value is None:
        return ""
    if kind == "int":
        try:
            return str(int(round(float(value))))
        except (TypeError, ValueError):
            return str(value)
    if kind == "float":
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        decimals = section.get("decimals")
        if str(section.get("style", "")).lower() == "scientific":
            return f"{number:.{int(decimals if decimals is not None else 1)}e}"
        if decimals is not None:
            return f"{number:.{int(decimals)}f}"
        return f"{number:g}"
    return str(value)


def parse_value(text: str, section: dict, bounds: tuple | None = None) -> Any:
    """Parse and clamp what was typed into a ``value`` section.

    Parameters
    ----------
    text : str
        Field contents.
    section : dict
        The section.
    bounds : tuple, optional
        Run-time ``(lo, hi)``; the spec's ``minimum``/``maximum`` otherwise.

    Returns
    -------
    object
        The value, or ``None`` when it does not parse -- a typo leaves the
        model as it was rather than writing zero into it.
    """
    kind = str(section.get("kind", "str")).lower()
    if kind not in ("int", "float"):
        return text
    try:
        number = float(str(text).strip())
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    lo, hi = bounds if bounds is not None else (section.get("minimum"), section.get("maximum"))
    if lo is not None:
        number = max(number, float(lo))
    if hi is not None:
        number = min(number, float(hi))
    return int(round(number)) if kind == "int" else number


def _hidden(section: dict, model: Any) -> bool:
    """AutoForm's ``hidden_when`` / ``visible`` on a section."""
    if section.get("visible") is False:
        return True
    cond = section.get("hidden_when")
    if not cond:
        return False
    try:
        owner = getattr(model, cond["target"]) if cond.get("target") else model
        value = getattr(owner, cond["attr"])
    except (AttributeError, KeyError):
        return False
    if "equals" in cond:
        return str(value).lower() == str(cond["equals"]).lower()
    if "not_equals" in cond:
        return str(value).lower() != str(cond["not_equals"]).lower()
    return False


def _enabled(model: Any, name: str) -> bool:
    hook = getattr(model, "enabled", None)
    if callable(hook) and name:
        try:
            return bool(hook(name))
        except Exception:  # noqa: BLE001 - a bad hook must not blank the form
            return True
    return True


def _bounds(model: Any, section: dict) -> tuple:
    hook = getattr(model, "bounds", None)
    if callable(hook):
        try:
            got = hook(section_name(section))
        except Exception:  # noqa: BLE001
            got = None
        if got is not None:
            return tuple(got)
    return (section.get("minimum"), section.get("maximum"))


def _options(section: dict, model: Any) -> tuple[list, list[str]]:
    """``(values, labels)`` of a choice; labels default to the values."""
    values = section.get("options") or section.get("choices")
    if not values and section.get("options_source"):
        produced = getattr(model, section["options_source"], None)
        if callable(produced):
            produced = produced()
        values = list(produced or [])
    values = list(values or [])
    if values and all(isinstance(v, (list, tuple)) and len(v) == 2 for v in values):
        return [v[0] for v in values], [str(v[1]) for v in values]
    labels = section.get("labels") or [str(v) for v in values]
    return values, [str(label) for label in labels]


def _commit(model: Any, section: dict, value: Any, state: FormState) -> None:
    """Write a value the way AutoForm does: ``setattr`` then the ``call``."""
    attr = section.get("attr")
    if attr:
        setattr(model, attr, value)
    call = section.get("call")
    if call:
        fn = getattr(model, call, None)
        if callable(fn):
            fn(value)
    state.used(section_name(section) or str(call))


def _label(text: str, width: float = 0.0) -> None:
    """A label centred on a field row, reserving at least *width*."""
    x, y = _w.get_cursor_screen_pos()
    tw, th = _w.calc_text_size(text)[:2]
    fh = _core.get_frame_height()
    if text:
        _core.get_window_draw_list().add_text((x, y + max(0.0, (fh - th) / 2.0)),
                                              _LABEL_COLOUR, text)
    _w.dummy(max(width, tw), fh)


def _remember(state: FormState, name: str) -> None:
    rect = _core.get_current_context().get_item_rect()
    if name and rect is not None:
        state.rects[name] = tuple(rect)


def _tooltip(section: dict) -> None:
    description = section.get("description")
    if description:
        _w.set_item_tooltip(str(description))


def _draw_value(section: dict, model: Any, state: FormState, width: float) -> None:
    name = section_name(section)
    value = getattr(model, section.get("attr", ""), None) if section.get("attr") else None
    shown_value = format_value(value, section)
    bounds = _bounds(model, section)
    read_only = bool(section.get("read_only"))
    slider = str(section.get("style", "")).lower() == "slider"
    kind = str(section.get("kind", "str")).lower()

    field_w = width
    if slider:
        field_w = max(40.0, min(90.0, 0.12 * width))
    shown = state.buffers.get(name, shown_value)
    _w.set_next_item_width(field_w)
    flags = InputTextFlags.ENTER_RETURNS_TRUE | (InputTextFlags.READ_ONLY if read_only else 0)
    entered, text = _w.input_text(f"##{name}", shown, str(section.get("placeholder", "")), flags)
    _remember(state, f"{name}.edit" if slider else name)
    _tooltip(section)
    text = text.replace("\r", "").replace("\n", "")
    if text != shown:
        state.buffers[name] = text
    io = _core.get_io()
    clicked_away = io.mouse_clicked[0] and not _w.is_item_hovered()
    if name in state.buffers and (entered or clicked_away):
        typed = state.buffers.pop(name)
        if typed != shown_value:
            parsed = parse_value(typed, section, bounds)
            if parsed is not None:
                _commit(model, section, parsed, state)

    if slider and kind in ("int", "float"):
        lo, hi = bounds
        lo = 0.0 if lo is None else float(lo)
        hi = lo if hi is None else max(float(hi), lo)
        _w.same_line()
        _w.set_next_item_width(max(width - field_w - 8.0, 20.0))
        current = value if value is not None else lo
        if kind == "int":
            changed, new = _w.slider_int(f"##{name}.slider", int(current), int(lo), int(hi))
        else:
            changed, new = _w.slider_float(f"##{name}.slider", float(current), lo, hi)
        _remember(state, f"{name}.slider")
        _tooltip(section)
        if changed and new != current and not read_only:
            _commit(model, section, new, state)


def _draw_choice(section: dict, model: Any, state: FormState, width: float) -> None:
    name = section_name(section)
    values, labels = _options(section, model)
    current = getattr(model, section.get("attr", ""), None) if section.get("attr") else None
    index = next((i for i, v in enumerate(values) if str(v) == str(current)), 0)
    if name in state.dropdown_result:
        picked = state.dropdown_result.pop(name)
        if 0 <= picked < len(values) and picked != index:
            _commit(model, section, values[picked], state)
            index = picked
    if str(section.get("style", "")).lower() == "radio":
        for i, label in enumerate(labels):
            if i:
                _w.same_line()
            if _w.radio_button(f"{label}##{name}{i}", i == index) and i != index:
                _commit(model, section, values[i], state)
        _remember(state, name)
        return
    caption = labels[index] if labels else ""
    if _w.button(f"{caption}  v##{name}", (width, 0.0)) and labels:
        state.dropdown_request = (name, tuple(_core.get_current_context().get_item_rect()),
                                  list(labels), index)
    _remember(state, name)
    _tooltip(section)


def _draw_toggle(section: dict, model: Any, state: FormState, label: str) -> None:
    name = section_name(section)
    value = bool(getattr(model, section.get("attr", ""), False)) if section.get("attr") else False
    changed, new = _w.checkbox(f"{label}##{name}", value)
    _remember(state, name)
    _tooltip(section)
    if changed:
        _commit(model, section, bool(new), state)


def _draw_buttons(section: dict, model: Any, state: FormState, width: float) -> None:
    buttons = list(section.get("buttons") or [])
    if not buttons:
        return
    spacing = 8.0
    button_w = max(30.0, (width - spacing * (len(buttons) - 1)) / len(buttons))
    for i, item in enumerate(buttons):
        if i:
            _w.same_line()
        action = str(item.get("action", ""))
        _w.begin_disabled(not _enabled(model, action))
        pressed = _w.button(f"{item.get('label', action)}##{action}", (button_w, 0.0))
        _remember(state, action)
        if item.get("description"):
            _w.set_item_tooltip(str(item["description"]))
        _w.end_disabled()
        if pressed:
            state.used(action)
            fn = getattr(model, action, None)
            if callable(fn):
                fn()


def _label_of(section: dict) -> str:
    kind = str(section.get("type", "")).lower()
    if kind in ("button_row", "toggle", "toggle_row", "info"):
        return ""
    return str(section.get("label", ""))


def _weight(section: dict) -> float:
    kind = str(section.get("type", "")).lower()
    if kind == "button_row":
        return 0.8 * len(section.get("buttons") or [])
    if kind in ("toggle", "toggle_row"):
        return 0.0
    if kind == "value" and str(section.get("style", "")).lower() == "slider":
        return 4.0
    return 1.0


def _fixed_width(section: dict) -> float:
    """Width a checkbox row takes regardless of the space there is."""
    kind = str(section.get("type", "")).lower()
    box = _core.get_frame_height() + 6.0
    if kind == "toggle":
        return box + _w.calc_text_size(str(section.get("label", "")))[0] + 8.0
    if kind == "toggle_row":
        return sum(box + _w.calc_text_size(str(item.get("label", "")))[0] + 12.0
                   for item in section.get("items") or [])
    return 0.0


def _draw_control(section: dict, model: Any, state: FormState, width: float) -> None:
    """The control of a leaf section, without its label."""
    kind = str(section.get("type", "")).lower()
    if kind == "value":
        _draw_value(section, model, state, width)
    elif kind == "choice":
        _draw_choice(section, model, state, width)
    elif kind == "toggle":
        _draw_toggle(section, model, state, str(section.get("label", "")))
    elif kind == "toggle_row":
        for i, item in enumerate(section.get("items") or []):
            if i:
                _w.same_line()
            _draw_toggle(dict(item, type="toggle"), model, state, str(item.get("label", "")))
    elif kind == "button_row":
        _draw_buttons(section, model, state, width)
    elif kind == "info":
        source = section.get("source")
        text = section.get("text", "")
        if source and callable(getattr(model, source, None)):
            text = getattr(model, source)()
        _w.text_wrapped(str(text))


def _draw_grid(leaves: list, model: Any, state: FormState, n_col: int) -> None:
    """Lay leaf sections out ``n_col`` to a line, **aligned in columns**.

    Every label of a column is as wide as the column's widest, and every control
    starts at the same x -- the label/field grid a form reads down, rather than
    fields that start wherever their own label happens to end.
    """
    n_col = max(1, int(n_col))
    rows = [leaves[i:i + n_col] for i in range(0, len(leaves), n_col)]
    spacing = 8.0
    label_w = [0.0] * n_col
    fixed_w = [0.0] * n_col
    weight = [0.0] * n_col
    for row in rows:
        for c, section in enumerate(row):
            text = _label_of(section)
            if text:
                label_w[c] = max(label_w[c], _w.calc_text_size(text)[0] + spacing)
            fixed_w[c] = max(fixed_w[c], _fixed_width(section))
            weight[c] = max(weight[c], _weight(section))
    avail = _w.get_content_region_avail()[0]
    free = max(avail - sum(label_w) - sum(fixed_w) - spacing * (n_col - 1), 30.0)
    unit = free / sum(weight) if sum(weight) > 0 else 0.0
    control_w = [fixed_w[c] + unit * weight[c] for c in range(n_col)]
    column_x = [0.0] * n_col
    for c in range(1, n_col):
        column_x[c] = column_x[c - 1] + label_w[c - 1] + control_w[c - 1] + spacing
    for row in rows:
        for c, section in enumerate(row):
            name = section_name(section)
            _w.begin_disabled(not (_enabled(model, name) if name else True))
            if c:
                _w.same_line(column_x[c])
            if label_w[c] > 0:
                _label(_label_of(section), label_w[c])
                _w.same_line(column_x[c] + label_w[c])
            _draw_control(section, model, state, max(control_w[c], 30.0))
            _w.end_disabled()


def _is_table(section: dict) -> bool:
    from .widgets.data_table import is_table_section

    return is_table_section(section)


def _draw_table_section(section: dict, model: Any, state: FormState) -> None:
    """A table section as one full-width item, bound once and kept in *state*."""
    from .widgets.data_table import TableBinding, draw_table

    options = dict(section.get("options") or {})
    name = str(options.get("source") or section.get("source") or section_name(section))
    binding = state.tables.get(name)
    if binding is None or binding.model is not model:
        binding = state.tables[name] = TableBinding(section, model)
    if section.get("title") and str(section.get("type", "")).lower() == "custom":
        _w.text(str(section["title"]))
    draw_table(binding, name)
    _remember(state, name)


def draw_sections(sections: Sequence, model: Any, state: FormState, n_col: int = 1,
                  titles: bool = True) -> None:
    """Draw a list of sections into the current window.

    Parameters
    ----------
    sections : sequence of dict
        Sections, as in a spec's ``"sections"``.
    model : object
        The object the fields read and write.
    state : FormState
        What the form keeps between frames.
    n_col : int
        Fields per line for the simple sections (AutoForm's ``n_col``).
    titles : bool
        Draw a nested panel's title as a caption line.
    """
    leaves: list = []

    def flush() -> None:
        if leaves:
            _draw_grid(list(leaves), model, state, n_col)
            leaves.clear()

    for section in sections or ():
        if not isinstance(section, dict) or _hidden(section, model):
            continue
        kind = str(section.get("type", "")).lower()
        if _is_table(section):
            flush()
            _draw_table_section(section, model, state)
            continue
        if kind in _CONTAINERS or isinstance(section.get("sections"), list):
            flush()
            if titles and section.get("title"):
                _w.text(str(section["title"]))
            draw_sections(section.get("sections") or [], model, state,
                          int(section.get("n_col") or 1), titles)
            continue
        leaves.append(section)
    flush()


def draw_form(spec: dict, model: Any, state: FormState, titles: bool = True) -> None:
    """Draw a whole view spec into the current window.

    Parameters
    ----------
    spec : dict
        A parsed ``view.json`` (or a single panel section).
    model : object
        The object the fields read and write.
    state : FormState
        What the form keeps between frames.
    titles : bool
        Draw panel titles as caption lines. A host that frames each panel
        itself -- a titled box around it -- passes ``False``.
    """
    if _hidden(spec, model):
        return
    draw_sections(spec.get("sections") or [], model, state, int(spec.get("n_col") or 1), titles)
