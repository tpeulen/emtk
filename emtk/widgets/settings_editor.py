"""A settings editor drawn against the painter, in the ImGui manner.

Why a *model* and not a hand-built panel
----------------------------------------
A panel with one hand-written row per setting is a panel that shows the
settings somebody remembered. The display configuration has hundreds of keys
across two dozen sections and grows every time a renderer learns a trick, so a
hand-written panel is out of date the moment it ships -- and the settings that
go missing are exactly the new ones nobody has a control for yet.

So the editor takes a **model** instead: a flat list of
:class:`Setting` records built *from the configuration itself*
(:meth:`SettingsModel.from_mapping`). Every key in the mapping is a row, the
control is chosen from the value's own type, and a key added tomorrow appears
without anybody touching this file. :data:`Meta` is the optional overlay that
turns a bare number into a slider with real bounds, or a string into a choice.

Reading and writing go through the model's ``getter``/``setter``, so the editor
never owns the values: the host writes them wherever they live (a live config
dict, a game's settings object) and decides what a change means.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Painter
from .basic import (
    _BORDER,
    _DIM,
    _GOLD,
    _ROW_EVEN,
    _ROW_ODD,
    _ROW_SEL,
    _TEXT,
    Button,
    ColorEdit4,
    Combo,
    InputInt,
    ScrollBar,
    Separator,
    SliderFloat,
    TextInput,
    Toggle,
    fit_text,
)

__all__ = [
    "BOOL",
    "CHOICE",
    "COLOUR",
    "FLOAT",
    "INT",
    "TEXT",
    "ACTION",
    "Setting",
    "SettingsModel",
    "SettingsEditor",
]

#: The kinds a setting can be. Each maps to exactly one control, which is what
#: keeps the editor from growing a branch per setting.
BOOL = "bool"
INT = "int"
FLOAT = "float"
CHOICE = "choice"
COLOUR = "colour"
TEXT = "text"
ACTION = "action"


@dataclasses.dataclass
class Setting:
    """One editable setting.

    Parameters
    ----------
    key : str
        Dotted path into the configuration, e.g. ``"surface.alpha"``. The part
        before the first dot is the group; the rest is the label unless one is
        given.
    kind : str
        One of :data:`BOOL`, :data:`INT`, :data:`FLOAT`, :data:`CHOICE`,
        :data:`COLOUR`, :data:`TEXT`, :data:`ACTION`.
    label : str, optional
        What the row is called. Defaults to the key without its group.
    v_min, v_max : float, optional
        Bounds for a number. A float without bounds gets a guess (see
        :meth:`SettingsModel.from_mapping`) -- a slider has to have *some*
        track, and a guessed one that can be corrected in :data:`Meta` beats no
        control at all.
    step : float, optional
        How much one key press moves the value.
    options : sequence of str, optional
        The choices, for :data:`CHOICE`.
    fmt : str, optional
        Format for the value's text.
    description : str, optional
        One line, shown for the selected row.
    group : str, optional
        Which tab it lives under. Defaults to the key's first component.
    """

    key: str
    kind: str
    label: str = ""
    default: Any = None
    """What the setting starts as, and what a reset puts back. Kept on the row
    rather than only in whatever built it, because "put this one back" is a
    question asked of a *row* -- the panel has no other way to answer it."""
    v_min: float | None = None
    v_max: float | None = None
    step: float | None = None
    options: Sequence[str] | None = None
    fmt: str = ""
    description: str = ""
    group: str = ""
    source: str = ""
    """Where the value lives, when that is not the key -- a registered setting
    is addressed by its own name and stored somewhere else entirely, and the
    place it is stored is what somebody reading the configuration file will
    search for."""

    def __post_init__(self) -> None:
        head, _, tail = self.key.partition(".")
        if not self.group:
            self.group = head if tail else "general"
        if not self.label:
            self.label = (tail or head).replace("_", " ")


#: The overlay that turns inferred settings into good ones:
#: ``{"surface.alpha": {"min": 0.0, "max": 1.0, "description": "..."}}``.
#: Keys are the same dotted paths; every field is optional.
Meta = Mapping[str, Mapping[str, Any]]


def _is_colour(value: Any) -> bool:
    """Whether a value looks like an RGB(A) triple or quadruple."""
    return (
        isinstance(value, (list, tuple))
        and len(value) in (3, 4)
        and all(isinstance(one, (int, float)) and not isinstance(one, bool) for one in value)
    )


class SettingsModel:
    """The settings an editor shows, and how to read and write them.

    Parameters
    ----------
    settings : iterable of Setting
        The rows, in the order they should appear.
    getter : callable
        ``getter(key)`` returns the current value.
    setter : callable
        ``setter(key, value)`` stores a new one. Anything the change implies --
        redrawing, saving, telling the renderer -- happens in there.
    """

    def __init__(
        self,
        settings: Iterable[Setting],
        getter: Callable[[str], Any],
        setter: Callable[[str, Any], None],
    ) -> None:
        self.settings = list(settings)
        self.getter = getter
        self.setter = setter

    # ------------------------------------------------------------------ #
    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, Any],
        meta: Meta | None = None,
        setter: Callable[[str, Any], None] | None = None,
        skip: Sequence[str] = (),
    ) -> "SettingsModel":
        """Build a model from a nested configuration mapping.

        Parameters
        ----------
        mapping : mapping
            Nested ``{section: {key: value}}``, to any depth. Leaves become
            settings keyed by their dotted path; the first component is the
            group.
        meta : mapping, optional
            Per-key overrides -- ``kind``, ``label``, ``min``, ``max``,
            ``step``, ``options``, ``fmt``, ``description``, ``group``.
        setter : callable, optional
            ``setter(key, value)``. Omitted writes straight back into
            ``mapping``, which is what a live configuration dict wants.
        skip : sequence of str, optional
            Dotted prefixes to leave out -- internal bookkeeping such as a
            schema version is a value, not a setting.

        Returns
        -------
        SettingsModel
            One setting per leaf, in the mapping's own order.
        """
        meta = meta or {}
        found: list[Setting] = []

        def walk(node: Mapping[str, Any], prefix: str) -> None:
            for name, value in node.items():
                key = f"{prefix}.{name}" if prefix else str(name)
                if any(key == one or key.startswith(one + ".") for one in skip):
                    continue
                if isinstance(value, Mapping):
                    walk(value, key)
                    continue
                found.append(cls._infer(key, value, meta.get(key, {})))

        walk(mapping, "")

        def read(key: str) -> Any:
            node: Any = mapping
            for part in key.split("."):
                node = node[part]
            return node

        def write(key: str, value: Any) -> None:
            parts = key.split(".")
            node: Any = mapping
            for part in parts[:-1]:
                node = node[part]
            node[parts[-1]] = value

        return cls(found, read, setter if setter is not None else write)

    @staticmethod
    def _infer(key: str, value: Any, over: Mapping[str, Any]) -> Setting:
        """One setting for one value, from its type and any overrides."""
        if "options" in over:
            kind = CHOICE
        elif isinstance(value, bool):
            kind = BOOL
        elif _is_colour(value):
            kind = COLOUR
        elif isinstance(value, int):
            kind = INT
        elif isinstance(value, float):
            kind = FLOAT
        else:
            kind = TEXT
        kind = over.get("kind", kind)

        v_min, v_max = over.get("min"), over.get("max")
        if kind in (FLOAT, INT) and v_min is None and v_max is None:
            # A guessed track, so an unannotated number is still draggable.
            # Zero to one for what is already a fraction, otherwise zero to
            # twice the current value -- which puts the thumb in the middle
            # and says plainly that the bound is not knowledge.
            number = float(value)
            v_min = 0.0 if number >= 0.0 else number * 2.0
            v_max = 1.0 if 0.0 <= number <= 1.0 else max(abs(number) * 2.0, 1.0)

        return Setting(
            key=key,
            kind=kind,
            label=over.get("label", ""),
            v_min=v_min,
            v_max=v_max,
            step=over.get("step"),
            options=over.get("options"),
            fmt=over.get("fmt", ""),
            description=over.get("description", ""),
            group=over.get("group", ""),
        )

    # ------------------------------------------------------------------ #
    def groups(self) -> list[str]:
        """The groups, in first-appearance order."""
        seen: list[str] = []
        for one in self.settings:
            if one.group not in seen:
                seen.append(one.group)
        return seen

    def rows(self, group: str = "", search: str = "") -> list[Setting]:
        """The settings of one group, optionally filtered by a substring."""
        needle = search.strip().lower()
        return [
            one for one in self.settings
            if (not group or one.group == group)
            and (not needle
                 or needle in one.key.lower()
                 or needle in one.label.lower()
                 or needle in one.source.lower())
        ]

    def get(self, key: str) -> Any:
        """Read one value."""
        return self.getter(key)

    def set(self, key: str, value: Any) -> None:
        """Write one value."""
        self.setter(key, value)

    # ------------------------------------------------------------------ #
    def control(self, setting: Setting):
        """The control that edits one setting, holding its current value.

        Controls are built per draw rather than kept: a settings panel shows
        values something *else* owns -- a command, a script, another panel --
        and a control that cached them would show what was true when the panel
        opened.
        """
        value = self.get(setting.key)
        if setting.kind == BOOL:
            return Toggle(setting.label, on=bool(value))
        if setting.kind == COLOUR:
            return ColorEdit4(f"{setting.label}", color=tuple(value))
        if setting.kind == CHOICE:
            options = [str(one) for one in (setting.options or [])]
            index = options.index(str(value)) if str(value) in options else 0
            return Combo(setting.label, options, index=index)
        if setting.kind == INT:
            return InputInt(
                setting.label, int(value),
                v_min=int(setting.v_min if setting.v_min is not None else 0),
                v_max=int(setting.v_max if setting.v_max is not None else 100),
                step=int(setting.step or 1),
            )
        if setting.kind == FLOAT:
            return SliderFloat(
                setting.label,
                float(setting.v_min if setting.v_min is not None else 0.0),
                float(setting.v_max if setting.v_max is not None else 1.0),
                float(value),
                fmt=setting.fmt or "%.3f",
            )
        if setting.kind == ACTION:
            return Button(setting.label)
        return TextInput(setting.label, str(value))

    def adjust(self, setting: Setting, direction: int) -> Any:
        """Move one setting by one step, and store the result.

        Parameters
        ----------
        setting : Setting
            What to change.
        direction : int
            ``+1`` or ``-1``. Zero means "activate": a switch flips, a choice
            advances, an action fires.

        Returns
        -------
        object
            The new value, or ``None`` for an action.
        """
        value = self.get(setting.key)
        if setting.kind == ACTION:
            self.set(setting.key, True)
            return None
        if setting.kind == BOOL:
            new: Any = not bool(value)
        elif setting.kind == CHOICE:
            options = [str(one) for one in (setting.options or [])]
            if not options:
                return value
            at = options.index(str(value)) if str(value) in options else 0
            new = options[(at + (direction or 1)) % len(options)]
        elif setting.kind in (INT, FLOAT):
            low = float(setting.v_min if setting.v_min is not None else 0.0)
            high = float(setting.v_max if setting.v_max is not None else 1.0)
            step = float(setting.step or ((high - low) / 20.0) or 1.0)
            moved = float(value) + step * (direction or 1)
            moved = min(max(moved, low), high)
            new = int(round(moved)) if setting.kind == INT else moved
        elif setting.kind == COLOUR:
            # A colour is not a scalar and has no "next" -- stepping one is a
            # brightness change, which is the only thing a keyboard can
            # sensibly do to it without a picker.
            factor = 1.1 if (direction or 1) > 0 else 1.0 / 1.1
            channels = list(value)
            top = 255.0 if any(one > 1.0 for one in channels[:3]) else 1.0
            new = [min(max(one * factor, 0.0), top) for one in channels[:3]] + list(channels[3:])
        else:
            return value
        self.set(setting.key, new)
        return new


class SettingsEditor:
    """An ImGui-style panel over a :class:`SettingsModel`.

    A tab strip for the groups, a filter box, a scrolling list of rows -- label
    on the left, control on the right -- and the selected row's description at
    the foot.

    Parameters
    ----------
    model : SettingsModel
        What to show.
    visible_rows : int, optional
        How many rows fit; the window follows the selection.
    """

    #: Fraction of the row's width the control gets. The label takes the rest.
    CONTROL_SHARE = 0.55

    #: The pseudo-group that shows every section at once, so the filter box can
    #: search the whole configuration rather than one section of it.
    ALL = "all"

    def __init__(self, model: SettingsModel, visible_rows: int = 12) -> None:
        self.model = model
        self.visible_rows = max(1, int(visible_rows))
        #: The group selector. A tab strip is the ImGui spelling and it is the
        #: wrong one here: the display configuration has twenty-eight sections,
        #: and twenty-eight pills across a panel leaves each of them too narrow
        #: for a single letter -- the first screenshot of this panel was a row
        #: of empty boxes. One selector that names the group it is on, with the
        #: count beside it, survives any number of sections.
        self.groups = Combo("", [self.ALL, *model.groups()])
        self.filter = TextInput("", "", placeholder="filter")
        self.row = 0
        self._boxes: list[tuple[Setting, tuple[float, float, float, float]]] = []
        self._filter_box: tuple[float, float, float, float] | None = None
        self._tab_box: tuple[float, float, float, float] | None = None
        self.bar = ScrollBar()

    # ------------------------------------------------------------------ #
    @property
    def top(self) -> int:
        """First listed row on screen."""
        return self.bar.top

    @top.setter
    def top(self, value: int) -> None:
        self.bar.top = int(value)
        self._clamp()

    @property
    def group(self) -> str:
        """The group being shown, or ``""`` when showing all of them."""
        value = self.groups.value
        return "" if value == self.ALL else value

    def rows(self) -> list[Setting]:
        """The settings currently listed."""
        return self.model.rows(self.group, self.filter.text)

    def selected(self) -> Setting | None:
        """The setting under the cursor, if any."""
        rows = self.rows()
        return rows[self.row] if 0 <= self.row < len(rows) else None

    def move(self, delta: int) -> None:
        """Move the cursor, wrapping, and scroll so it stays on screen."""
        rows = self.rows()
        if not rows:
            return
        self.row = (self.row + delta) % len(rows)
        self.top = min(max(self.top, self.row - self.visible_rows + 1), self.row)
        self._clamp()

    def move_group(self, delta: int) -> None:
        """Change group, and put the cursor back at the top."""
        self.groups.cycle(delta)
        self.row = 0
        self.top = 0

    def scroll(self, rows: int) -> None:
        """Scroll the window without moving the cursor."""
        self._clamp()
        self.bar.scroll(rows)

    def _clamp(self) -> None:
        """Keep the window inside the list."""
        self.bar.clamp(len(self.rows()), self.visible_rows)

    def adjust(self, direction: int) -> Any:
        """Change the selected setting."""
        setting = self.selected()
        return None if setting is None else self.model.adjust(setting, direction)

    def first_visible(self) -> int:
        """Index of the top row of the scrolled window."""
        self._clamp()
        return self.top

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the whole panel into a box."""
        line = p.line_height()
        head_h = line * 1.6
        foot_h = line * 1.4

        current = self.groups.value
        self.groups.options = [self.ALL, *self.model.groups()]
        self.groups.index = (self.groups.options.index(current)
                             if current in self.groups.options else 0)
        self._tab_box = (x, y, w * 0.52, head_h)
        self._filter_box = (x + w * 0.54, y, w * 0.46, head_h)
        shown = len(self.rows())
        self.groups.label = ""
        self.groups.draw(p, *self._tab_box)
        p.text(self._tab_box[0], y, self._tab_box[2] - 6.0, head_h,
               ALIGN_VCENTER | ALIGN_RIGHT, f"{shown}", _DIM)
        self.filter.draw(p, *self._filter_box)

        body_y = y + head_h + 4.0
        body_h = max(h - head_h - foot_h - 8.0, line)
        list_w = max(w - self.bar.width, 1.0)
        p.stroke_rect(x, body_y, list_w, body_h, _BORDER, _ROW_EVEN)

        rows = self.rows()
        row_h = body_h / self.visible_rows
        start = self.first_visible()
        self._boxes = []
        p.push_clip(x, body_y, list_w, body_h)
        for offset in range(self.visible_rows):
            index = start + offset
            if index >= len(rows):
                break
            setting = rows[index]
            row_y = body_y + offset * row_h
            if index == self.row:
                p.fill_rect(x, row_y, list_w, row_h, _ROW_SEL)
            elif index % 2:
                p.fill_rect(x, row_y, list_w, row_h, _ROW_ODD)

            label_w = list_w * (1.0 - self.CONTROL_SHARE)
            p.text(x + 6.0, row_y, max(label_w - 12.0, 1.0), row_h,
                   ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, setting.label, label_w - 12.0),
                   _GOLD if index == self.row else _TEXT)
            box = (x + label_w, row_y + row_h * 0.15,
                   list_w * self.CONTROL_SHARE - 8.0, row_h * 0.7)
            control = self.model.control(setting)
            # A control carrying its own label would print it twice: the row
            # already has one, on the left, in the column that lines up.
            control.label = ""
            control.draw(p, *box)
            self._boxes.append((setting, box))
        p.pop_clip()

        self.bar.clamp(len(rows), self.visible_rows)
        self.bar.draw(p, x + list_w, body_y, body_h)

        Separator().draw(p, x, y + h - foot_h - 2.0, w, 4.0)
        p.text(x + 6.0, y + h - foot_h, max(w - 12.0, 1.0), foot_h,
               ALIGN_VCENTER | ALIGN_LEFT, self._note(p, max(w - 12.0, 1.0)), _DIM)

    def _note(self, p: Painter, room: float) -> str:
        """The footer line for the selected row, shortened to fit ``room``.

        Where the value lives and what it is, then the documentation if there
        is any -- in that order, because the path is what somebody types into
        the command line next and it must not be the half that gets cut.
        """
        chosen = self.selected()
        if chosen is None:
            return ""
        where = chosen.source or chosen.key
        note = f"{where} = {self.model.get(chosen.key)!r}"
        if chosen.description:
            note = f"{note}  --  {chosen.description}"
        return fit_text(p, note, room)

    # ------------------------------------------------------------------ #
    def press(self, x: float, y: float) -> Setting | None:
        """Route a press to whatever it landed on.

        The boxes come from the last :meth:`draw`, so the panel hit-tests
        against what is actually on screen rather than against a layout
        computed twice and drifting apart.

        Parameters
        ----------
        x, y : float
            Where the press landed, in the painter's coordinates.

        Returns
        -------
        Setting or None
            The setting that changed, if any. A press on the tab strip, the
            filter box or the scrollbar returns ``None`` -- it changed the
            *view*, not a value.
        """
        if self._inside(self._tab_box, x, y):
            # The left fifth steps back. A selector that can only go forwards
            # is twenty-seven clicks from the section before this one.
            self.move_group(-1 if x < self._tab_box[0] + self._tab_box[2] * 0.2 else 1)
            return None
        if self._inside(self._filter_box, x, y):
            return None
        if self.bar.press(x, y):
            return None

        for setting, box in self._boxes:
            box_x, box_y, box_w, box_h = box
            if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
                continue
            rows = self.rows()
            self.row = rows.index(setting) if setting in rows else self.row
            if setting.kind == FLOAT:
                fraction = (x - box_x) / max(box_w, 1e-6)
                low = float(setting.v_min if setting.v_min is not None else 0.0)
                high = float(setting.v_max if setting.v_max is not None else 1.0)
                self.model.set(setting.key, low + min(max(fraction, 0.0), 1.0) * (high - low))
            elif setting.kind == INT:
                # The stepper's own hit test: right box up, the one two boxes
                # left of it down.
                right = box_x + box_w
                self.model.adjust(setting, 1 if x >= right - box_h else -1)
            else:
                self.model.adjust(setting, 0)
            return setting
        return None

    def drag(self, x: float, y: float) -> bool:
        """Continue a scrollbar drag. Returns whether anything moved."""
        return self.bar.drag(y)

    def release(self) -> None:
        """End a scrollbar drag."""
        self.bar.release()

    @staticmethod
    def _inside(box, x: float, y: float) -> bool:
        """Whether ``(x, y)`` is inside a ``(x, y, w, h)`` box."""
        if box is None:
            return False
        box_x, box_y, box_w, box_h = box
        return box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h

