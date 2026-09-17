"""Building emtk's painted forms from ChiSurf's ``view.json`` specs.

ChiSurf tools declare their user interface as data: a ``*.view.json`` file of
nested sections, each naming the model attribute it edits, its label, its range
and its one-line description. AutoForm turns that into Qt widgets.

A painted application has no Qt -- its chrome goes into the viewport so that the
desktop app and the browser run one code path -- and emtk already owns a form
renderer (:mod:`.settings_editor`: rows, groups, sliders, combos, checkboxes, a
filter box, per-row descriptions). So supporting AutoForm here is
**not** a second renderer. It is an adapter: the view spec becomes
:class:`~.settings_editor.Setting` rows over a
:class:`~.settings_editor.SettingsModel` bound to the model object, and the
existing editor draws them.

That is the whole design, and it is worth stating because the alternative --
teaching the painted chrome to build Qt-shaped widgets, or teaching AutoForm to
paint -- is what a "port" would have meant.

Tables
------
``table`` sections and ``custom`` ``data_table`` sections are not rows of a
settings list, so they are not turned into :class:`Setting` rows. They are
bound to the model by :class:`~.data_table.TableBinding` -- records or arrays,
column specs, sorting, selection into ``selected_call``, and a refresh that
notices a source growing while a computation streams -- and drawn by
:class:`~.data_table.DataTable`. :func:`table_bindings` returns them for a
spec, and :class:`ViewSpecPanel` draws a spec's settings and its tables in one
box.

What is deliberately *not* supported
------------------------------------
The spec vocabulary is larger than a painted panel can honour. A
``parameter_group_table``, a ``plot``, an embedded widget or an ``image``
section describes something with no painted equivalent yet. Those sections are
**reported**, not silently dropped: :func:`unsupported_sections` lists what a
spec asked for and did not get, so a caller can say so rather than showing a
form that is quietly missing half its controls -- which is the failure mode of
every "best effort" spec reader.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Callable, Iterable

from .data_table import TableBinding, is_table_section
from .settings_editor import (
    ACTION,
    BOOL,
    CHOICE,
    COLOUR,
    FLOAT,
    INT,
    TEXT,
    Setting,
    SettingsModel,
)

__all__ = [
    "CONTAINER_TYPES",
    "FIELD_KINDS",
    "ViewSpecPanel",
    "load_view_spec",
    "model_from_view_spec",
    "settings_from_view_spec",
    "table_bindings",
    "unsupported_sections",
]

#: Section types that hold other sections rather than editing anything. Their
#: ``title`` becomes the group a nested field is filed under, which is how a
#: spec's panels turn into the editor's group selector.
CONTAINER_TYPES = frozenset({"panel", "group", "box", "tab", "tabs", "row", "column"})

#: Section types that edit something, and what they edit with. This is the
#: real dialect, not a convenient one: a scalar field is ``{"type": "value",
#: "kind": "float"}``, a checkbox is ``{"type": "toggle"}``. Inventing
#: ``{"type": "float"}`` would read here and be rejected by AutoForm and by the
#: scheme -- one dialect, or the shared format is not shared.
SECTION_KINDS: dict[str, str] = {
    "value": FLOAT,      # refined by the section's own `kind`
    "toggle": BOOL,
    "choice": CHOICE,
    "button_row": ACTION,
}

#: A ``value`` section's ``kind``, as
#: :mod:`chisurf.gui.autoform.sections.builtin` implements it, mapped onto the
#: painted editor's row kinds. The spec distinguishes more than the painter
#: does on purpose -- an ``expression`` and a ``str`` are different things to
#: validate and the same thing to type into.
FIELD_KINDS: dict[str, str] = {
    "int": INT,
    "float": FLOAT,
    "str": TEXT,
    "text": TEXT,
    "expression": TEXT,
    "date": TEXT,
    "password": TEXT,
    "secret": TEXT,
    "file": TEXT,
    "directory": TEXT,
}

#: Where a section's edited attribute is named. ``attr`` is the usual spelling;
#: ``target`` is what a ``custom`` section uses, and ``key`` what a few others
#: do. Checked in this order, so a spec carrying both is read the way AutoForm
#: reads it.
_ATTR_KEYS = ("attr", "target", "key")


def load_view_spec(path) -> dict:
    """Read a ``*.view.json`` file.

    Raises
    ------
    FileNotFoundError, ValueError
        Refused rather than defaulted to an empty form: a form with no controls
        looks like a tool with no settings.
    """
    file = pathlib.Path(path)
    if not file.exists():
        raise FileNotFoundError(f"no view spec at {file}")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{file.name} is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{file.name} must be a JSON object")
    return data


def _attr_of(section: dict) -> str:
    for key in _ATTR_KEYS:
        value = section.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _label_of(section: dict, attr: str) -> str:
    label = section.get("label") or section.get("title") or ""
    if label:
        return str(label)
    # Fall back to the attribute, humanised. A row with no label at all is a
    # control nobody can identify, which is worse than an imperfect guess.
    return attr.replace("_", " ").strip().capitalize()


def _kind_of(section: dict, value: Any) -> str:
    """The painted row kind for a section, from its type, its kind, or its value."""
    section_type = str(section.get("type", "") or "").strip().lower()
    if section_type == "value":
        mapped = FIELD_KINDS.get(str(section.get("kind", "") or "").strip().lower())
        if mapped is not None:
            return mapped
    elif section_type in SECTION_KINDS:
        return SECTION_KINDS[section_type]
    # Nothing declared: read the value. A spec that says only `{"attr": "x"}`
    # is common and perfectly clear once the model is in hand.
    if isinstance(value, bool):
        return BOOL
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return FLOAT
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        if all(isinstance(v, (int, float)) for v in value):
            return COLOUR
    return TEXT


def _options_of(section: dict, model: Any) -> list[str]:
    """The choices for a ``choice`` row.

    ``options`` is a literal list; ``options_source`` names a **method or
    property on the model** that produces one. The indirection is the whole
    point for a catalogue that is not known until the model exists.
    """
    literal = section.get("options") or section.get("choices")
    if isinstance(literal, (list, tuple)):
        return [str(v) for v in literal]

    source = section.get("options_source") or section.get("source")
    if isinstance(source, str) and source:
        produced = getattr(model, source, None)
        if callable(produced):
            try:
                produced = produced()
            except Exception:  # noqa: BLE001 - a bad source must not kill the form
                produced = None
        if isinstance(produced, (list, tuple)):
            return [str(v) for v in produced]
    return []


def _iter_sections(spec: dict) -> Iterable[tuple[dict, str]]:
    """Walk the spec, yielding ``(section, group)`` for every leaf.

    A container contributes its title as the group for everything under it, and
    the *outermost* titled container wins -- the editor has one level of
    grouping, and filing a row under the innermost box would scatter one panel's
    controls across several groups named after its sub-boxes.
    """
    def walk(sections, group):
        for section in sections or ():
            if not isinstance(section, dict):
                continue
            kind = str(section.get("type", "")).strip().lower()
            children = section.get("sections")
            if kind in CONTAINER_TYPES or isinstance(children, list):
                title = str(section.get("title") or "").strip()
                yield from walk(children, group or title)
                continue
            yield section, group

    yield from walk(spec.get("sections"), "")


def settings_from_view_spec(spec: dict, model: Any) -> list[Setting]:
    """The editable rows a view spec describes, in spec order."""
    rows: list[Setting] = []
    for section, group in _iter_sections(spec):
        if is_table_section(section):
            continue  # a table is not a row; see `table_bindings`
        attr = _attr_of(section)
        if not attr:
            continue
        if not hasattr(model, attr):
            # A spec naming an attribute the model does not have is a spec that
            # has drifted from its model. Skipped here and reported by
            # `unsupported_sections`, so it is visible without being fatal.
            continue
        value = getattr(model, attr, None)
        kind = _kind_of(section, value)
        # `minimum`/`maximum` are the spec's own spelling. Accepting `min`/`max`
        # as well would be a second dialect that validates here and nowhere
        # else, which is the thing the shared scheme exists to stop.
        limits = (section.get("minimum"), section.get("maximum"))
        rows.append(
            Setting(
                key=attr,
                kind=kind,
                label=_label_of(section, attr),
                default=value,
                v_min=None if limits[0] is None else float(limits[0]),
                v_max=None if limits[1] is None else float(limits[1]),
                step=None if section.get("step") is None else float(section["step"]),
                options=tuple(_options_of(section, model)) if kind == CHOICE else (),
                description=str(section.get("description", "")),
                group=group or "settings",
            )
        )
    return rows


def unsupported_sections(spec: dict, model: Any) -> list[str]:
    """What the spec asked for that a painted form cannot give it.

    Returned rather than logged, and never raised. A caller that shows a form
    built from a spec should say what is missing from it -- a form quietly
    lacking half its controls is indistinguishable from a tool that has none.
    """
    missing: list[str] = []
    for section, _group in _iter_sections(spec):
        kind = str(section.get("type", "")).strip().lower()
        if is_table_section(section):
            options = dict(section.get("options") or {})
            source = options.get("source") or section.get("source") or ""
            if not source:
                missing.append(f"{kind}: no source to read rows from")
            elif not hasattr(model, source):
                missing.append(f"{kind} '{source}': the model has no such source")
            continue
        attr = _attr_of(section)
        if not attr:
            missing.append(f"{kind or 'section'}: no attribute to edit")
            continue
        if not hasattr(model, attr):
            missing.append(f"{kind or 'section'} '{attr}': the model has no such attribute")
            continue
        if kind not in SECTION_KINDS:
            missing.append(f"'{attr}': section type '{kind}' has no painted equivalent")
    return missing


def model_from_view_spec(
    spec: dict,
    model: Any,
    on_change: Callable[[str, Any], None] | None = None,
) -> SettingsModel:
    """A painted form over *model*, laid out by *spec*.

    Parameters
    ----------
    spec : dict
        A parsed ``view.json``.
    model : object
        The thing being edited. Rows read and write its attributes directly,
        which is what AutoForm does too -- so a model already driving a Qt form
        drives this one with no changes.
    on_change : callable, optional
        ``on_change(attr, value)`` after each write, for whatever the change
        implies: a redraw, a recompute, a save.

    Returns
    -------
    SettingsModel
        Hand it to :class:`~.settings_editor.SettingsEditor`, or to
        ``GuiWindow`` through the form panel.
    """
    rows = settings_from_view_spec(spec, model)

    def getter(key: str) -> Any:
        return getattr(model, key, None)

    def setter(key: str, value: Any) -> None:
        setattr(model, key, value)
        if on_change is not None:
            on_change(key, value)

    return SettingsModel(rows, getter, setter)


def table_bindings(spec: dict, model: Any) -> list[TableBinding]:
    """The tables a view spec declares, bound to *model*, in spec order.

    Both dialects: ``{"type": "table", "source": ...}`` and
    ``{"type": "custom", "key": "data_table", "options": {"source": ...}}``.
    """
    return [TableBinding(section, model)
            for section, _group in _iter_sections(spec) if is_table_section(section)]


class ViewSpecPanel:
    """A whole view spec in one box: its settings above, its tables below.

    Parameters
    ----------
    spec : dict
        A parsed ``view.json``.
    model : object
        What the settings edit and the tables read.
    on_change : callable, optional
        ``on_change(attr, value)`` after a setting is written.
    visible_rows : int
        Setting rows shown before the list scrolls.

    Notes
    -----
    Each table gets its section's ``height``; a table that asks to ``expand``
    (or the last one, when none does) takes what is left. The control follows
    the host contract, so a ``ControlHost`` or a ``PixelPainter`` drives it.
    """

    def __init__(self, spec: dict, model: Any,
                 on_change: Callable[[str, Any], None] | None = None,
                 visible_rows: int = 6) -> None:
        from .settings_editor import SettingsEditor

        self.spec = spec
        self.model = model
        self.settings = model_from_view_spec(spec, model, on_change)
        self.editor = SettingsEditor(self.settings, visible_rows=visible_rows) \
            if self.settings.settings else None
        self.tables = table_bindings(spec, model)
        self._boxes: list[tuple[Any, tuple]] = []
        self._pressed: Any = None

    def draw(self, p, x: float, y: float, w: float, h: float) -> None:
        """Lay the settings and the tables out top to bottom and draw them."""
        line = p.line_height()
        self._boxes = []
        cursor = y
        if self.editor is not None:
            rows = min(len(self.settings.settings), self.editor.visible_rows)
            editor_h = min(line * 1.6 * (rows + 2.2), h * 0.6 if self.tables else h)
            self.editor.visible_rows = max(rows, 1)
            self.editor.draw(p, x, cursor, w, editor_h)
            self._boxes.append((self.editor, (x, cursor, w, editor_h)))
            cursor += editor_h + 6.0
        if not self.tables:
            return
        remaining = max(y + h - cursor, line * 4)
        stretch = [t for t in self.tables if t.expand] or [self.tables[-1]]
        fixed = sum(t.height for t in self.tables if t not in stretch)
        spare = max(remaining - fixed - 6.0 * (len(self.tables) - 1), line * 4)
        for binding in self.tables:
            binding.refresh()
            box_h = spare / len(stretch) if binding in stretch else binding.height
            binding.control.draw(p, x, cursor, w, box_h)
            self._boxes.append((binding.control, (x, cursor, w, box_h)))
            cursor += box_h + 6.0

    def _target(self, px: float, py: float):
        for control, (bx, by, bw, bh) in self._boxes:
            if bx <= px <= bx + bw and by <= py <= by + bh:
                return control
        return None

    def press(self, px: float, py: float, *box: Any, **kw: Any) -> bool:
        """Route a press to the settings or the table under it."""
        target = self._pressed = self._target(px, py)
        for binding in self.tables:
            if binding.control is not target:
                binding.control.filter_focused = False
        if target is None:
            return False
        if target is self.editor:
            return self.editor.press(px, py) is not None
        return target.press(px, py, *box, **kw)

    def drag(self, px: float, py: float, *box: Any) -> bool:
        """Continue a drag on whatever the press landed on."""
        target = self._pressed
        if target is None:
            return False
        if target is self.editor:
            return self.editor.drag(px, py)
        return target.drag(px, py, *box)

    def release(self, *args: Any, **kw: Any) -> None:
        """End a drag."""
        if self._pressed is not None:
            self._pressed.release()
        self._pressed = None

    def hover(self, px: float, py: float, *box: Any) -> None:
        """Track the row under the pointer in the table there."""
        target = self._target(px, py)
        for binding in self.tables:
            if binding.control is target:
                binding.control.hover(px, py)
            else:
                binding.control.hovered = None

    def scroll(self, rows: int) -> None:
        """Scroll the hovered table, else the settings list."""
        for binding in self.tables:
            if binding.control.hovered is not None:
                binding.control.scroll(rows)
                return
        if self.editor is not None:
            self.editor.scroll(rows)

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Keys go to a table whose filter has focus, else the selected table."""
        for binding in self.tables:
            if binding.control.filter_focused:
                return binding.control.key(key, text, modifiers)
        for binding in self.tables:
            if binding.control.selected_key is not None:
                return binding.control.key(key, text, modifiers)
        return False
