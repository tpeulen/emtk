"""The Input family: a number typed into a box, and text with more than one line.

What is here and why it is not in :mod:`.widgets`
-------------------------------------------------
:mod:`.widgets` already carries a stepper (``InputInt``) and a one-line text box
(``TextInput``). The reference implementation's Input section is much larger
than those two: it is a *scalar* editor -- a field you type a number into, with
optional ``-``/``+`` buttons and a printf format that decides both how the value
is shown and how the typed string is read back -- plus the two- to four-component
rows built out of it, a hint that shows only while the buffer is empty, and a
multi-line editor.

The half that is easy to get wrong is the round trip. A field shows ``4.5 tiles``
because its format is ``"%.1f tiles"``, but the string the user edits must be
``4.5``: the decorations are stripped for editing (the reference's
``ImParseFormatTrimDecorations``) and put back for display. And what a field does
with ``"twelve"`` is a decision, not an accident -- the reference's
``DataTypeApplyFromText`` returns *false* and leaves the value alone, so a typo
costs the edit rather than the value. Zeroing it would be the silent version of
the same bug, which is why :func:`apply_from_text` returns the caller's current
value rather than a sentinel.

The multi-line editor's own trap is the cursor column. Moving down onto a short
line and back up must land where it started; the reference keeps a *preferred*
position (``stb_textedit``'s ``preferred_x``) that survives a run of up/down
moves and is dropped by anything else. Storing the clamped column instead is the
classic truncation bug, and it is invisible until a short line sits between two
long ones.

Everything draws through the six :class:`~emtk.painter.Painter`
operations, holds its own state, and hit-tests with :func:`.style.hit`.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter
from ..style import (
    BORDER,
    BUTTON,
    FRAME_BG,
    FRAME_BG_ACTIVE,
    GOLD,
    TEXT,
    TEXT_DISABLED,
    clamp,
    fit_text,
    format_value,
    hit,
)
from .text_field import TextField, paint as paint_field

__all__ = [
    "trim_decorations",
    "format_precision",
    "apply_from_text",
    "InputScalar",
    "InputFloat",
    "InputDouble",
    "InputScalarN",
    "InputFloat2",
    "InputFloat3",
    "InputFloat4",
    "InputInt2",
    "InputInt3",
    "InputInt4",
    "InputTextWithHint",
    "InputTextMultiline",
]


# --------------------------------------------------------------------------
# Format parsing -- the reference's ImParseFormat* helpers
# --------------------------------------------------------------------------
#: Type modifiers that do *not* end a printf conversion: the reference's
#: ``I``/``L`` and ``h``/``j``/``l``/``t``/``w``/``z``. Case matters -- ``%I64d``
#: ends at the ``d``, not at the ``I``.
_MODIFIERS = frozenset("ILhjltwz")

#: Conversions that mean "this is a whole number".
_INTEGER_CONVERSIONS = frozenset("diuoxX")

_FLOAT_TEXT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_INTEGER_TEXT = re.compile(r"[+-]?\d+")
_HEX_TEXT = re.compile(r"[+-]?(?:0[xX])?[0-9a-fA-F]+")

#: What the reference's ``ImCharIsBlankA`` calls blank.
_BLANK = " \t"


def _find_start(fmt: str) -> int:
    """Index of the first real conversion in *fmt*.

    Parameters
    ----------
    fmt : str
        A printf format, possibly with decorations around the conversion.

    Returns
    -------
    int
        Where the ``%`` of the conversion is, or ``len(fmt)`` if there is
        none. ``%%`` is an escaped percent sign and is skipped, which is the
        reason this is not ``fmt.index("%")``.
    """
    index, size = 0, len(fmt)
    while index < size:
        if fmt[index] == "%":
            if index + 1 >= size or fmt[index + 1] != "%":
                return index
            index += 1
        index += 1
    return size


def _find_end(fmt: str, start: int) -> int:
    """Index one past the conversion that begins at *start*.

    Parameters
    ----------
    fmt : str
        The format.
    start : int
        Index of the conversion's ``%``.

    Returns
    -------
    int
        One past the conversion character, or ``len(fmt)`` if the format runs
        out first.
    """
    if start >= len(fmt) or fmt[start] != "%":
        return start
    index = start
    while index < len(fmt):
        char = fmt[index]
        if char.isascii() and char.isalpha() and char not in _MODIFIERS:
            return index + 1
        index += 1
    return index


def trim_decorations(fmt: str) -> str:
    """The bare conversion out of a decorated format string.

    ``"%.3f"`` is itself, ``"hello %.3f"`` and ``"%.3f tiles"`` are both
    ``"%.3f"``, and ``"blah"`` -- a format that shows no number at all -- is
    the empty string. This is what a field puts in front of the user when it
    becomes editable: the decorations belong to the *display*, and leaving them
    in would make the user delete them before typing.

    Parameters
    ----------
    fmt : str
        The display format.

    Returns
    -------
    str
        The conversion, or ``""`` when the format contains none.
    """
    start = _find_start(fmt)
    if start >= len(fmt) or fmt[start] != "%":
        return ""
    return fmt[start:_find_end(fmt, start)]


def format_precision(fmt: str, default: int = 3) -> int:
    """The number of decimals *fmt* asks for.

    Parameters
    ----------
    fmt : str
        The display format.
    default : int, optional
        Used when the format states no precision.

    Returns
    -------
    int
        The precision. Scientific and shortest-form conversions (``e``, ``g``)
        report ``-1``, meaning "as many as it takes", exactly as the reference
        does.
    """
    start = _find_start(fmt)
    if start >= len(fmt) or fmt[start] != "%":
        return default
    index = start + 1
    while index < len(fmt) and fmt[index].isdigit():
        index += 1
    precision: int | None = None
    if index < len(fmt) and fmt[index] == ".":
        index += 1
        digits = index
        while index < len(fmt) and fmt[index].isdigit():
            index += 1
        precision = int(fmt[digits:index] or "0")
        if precision < 0 or precision > 99:
            precision = default
    tail = fmt[index] if index < len(fmt) else ""
    if tail in ("e", "E"):
        return -1
    if tail in ("g", "G") and precision is None:
        return -1
    return default if precision is None else precision


def _conversion(fmt: str) -> str:
    """The conversion character of *fmt* (``f``, ``d``, ``x`` ...), or ``""``."""
    spec = trim_decorations(fmt)
    return spec[-1] if spec else ""


def apply_from_text(
    text: str,
    current: float,
    fmt: str = "%f",
    when_empty: float | None = None,
) -> float:
    """Read a typed string back into a number.

    The reference (``DataTypeApplyFromText``) leaves the value **untouched**
    when the string does not parse, and reports that nothing changed. Nothing
    here raises and nothing here zeroes: a field whose contents are ``"twelve"``
    keeps the number it had, because the alternative -- silently substituting
    zero -- is a data-loss bug that looks like a working widget.

    Leading blanks are skipped, and parsing stops at the first character that
    does not belong, so ``"12abc"`` reads as ``12`` just as ``sscanf`` does.

    Parameters
    ----------
    text : str
        What the user typed.
    current : float
        The value to keep when the string is empty or unparseable.
    fmt : str, optional
        The field's format. Only its conversion matters: ``d``/``i``/``u``/``o``
        mean a whole number, ``x``/``X`` a hexadecimal one, anything else a
        float. Width and precision are ignored, which is the reference's
        ``ImParseFormatSanitizeForScanning``.
    when_empty : float, optional
        What an empty string means. ``None`` -- the default -- means "leave the
        value alone", the reference's behaviour without
        ``ImGuiInputTextFlags_ParseEmptyRefVal``.

    Returns
    -------
    float
        The parsed value, or *current*.
    """
    body = str(text).lstrip(_BLANK)
    conversion = _conversion(fmt)
    integer = conversion in _INTEGER_CONVERSIONS
    if not body:
        if when_empty is None:
            return current
        return int(when_empty) if integer else float(when_empty)
    if conversion in ("x", "X"):
        match = _HEX_TEXT.match(body)
        if match is None:
            return current
        digits = match.group(0)
        sign = -1 if digits.startswith("-") else 1
        return sign * int(digits.lstrip("+-"), 16)
    pattern = _INTEGER_TEXT if integer else _FLOAT_TEXT
    match = pattern.match(body)
    if match is None:
        return current
    return int(match.group(0)) if integer else float(match.group(0))


# --------------------------------------------------------------------------
# The scalar field
# --------------------------------------------------------------------------
class InputScalar:
    """A number in a box, optionally with ``-`` and ``+`` beside it.

    The box is not editable until it is pressed -- that press is what the
    reference calls activation, and it is when the displayed number becomes an
    editable string. :meth:`commit` turns the string back into a number;
    :meth:`cancel` throws it away. A press *outside* the box commits, because
    that is what losing focus means.

    The editing itself is :class:`~emtk.widgets.text_field.TextField`, the
    same one-line editor :class:`~emtk.widgets.basic.TextInput` uses, so
    a host that already routes keys into a field keeps doing exactly that.

    Parameters
    ----------
    label : str, optional
        Caption drawn before the box.
    value : float, optional
        Initial value.
    step : float, optional
        How much one press of ``-``/``+`` moves it. Zero -- the default, and the
        reference's -- means the buttons are not drawn at all.
    step_fast : float, optional
        The larger step, used when the press comes in with ``fast=True`` (the
        reference reads that off Ctrl).
    fmt : str, optional
        printf format for display. Decorations around the conversion are shown
        but not edited: see :func:`trim_decorations`.
    v_min, v_max : float, optional
        Bounds, each independently optional. Reversed bounds are swapped rather
        than trapping every value between them, as the reference's
        ``DataTypeClamp`` call site does.
    integer : bool, optional
        Hold and parse whole numbers.

    Notes
    -----
    The reference activates the field with the whole buffer selected
    (``ImGuiInputTextFlags_AutoSelectAll``), so the first keystroke *replaces*
    the number rather than appending to it -- typing ``7`` into a field showing
    ``1.000`` must not produce ``1.0007``. The field's own selection does it:
    :attr:`select_all` says whether the whole buffer is selected, and every
    shortcut of :class:`~emtk.widgets.text_field.TextField` works here too.
    """

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        step: float = 0.0,
        step_fast: float = 0.0,
        fmt: str = "%.3f",
        v_min: float | None = None,
        v_max: float | None = None,
        integer: bool = False,
    ) -> None:
        self.label = label
        self.fmt = fmt
        self.integer = bool(integer)
        self.step = step
        self.step_fast = step_fast
        self.v_min = v_min
        self.v_max = v_max
        self.field = TextField()
        self.editing = False
        self.value = self._bounded(value)
        #: ``(field_x, field_w, button_size)`` from the last :meth:`draw`.
        self._box: tuple[float, float, float] | None = None

    @property
    def select_all(self) -> bool:
        """Whether the whole (non-empty) buffer is selected; see the class notes."""
        f = self.field
        return bool(f.text) and f.selection() == (0, len(f.text))

    @select_all.setter
    def select_all(self, on: bool) -> None:
        if on:
            self.field.select_all()
        else:
            self.field.move(self.field.cursor)

    # ------------------------------------------------------------------ #
    def _cast(self, value: float) -> float:
        """*value* as this field's number type."""
        return int(value) if self.integer else float(value)

    def _bounded(self, value: float) -> float:
        """*value* cast and confined to the bounds, which may be reversed."""
        low, high = self.v_min, self.v_max
        if low is not None and high is not None and low > high:
            low, high = high, low
        number = self._cast(value)
        if low is not None and number < low:
            number = self._cast(low)
        if high is not None and number > high:
            number = self._cast(high)
        return number

    def set_value(self, value: float) -> float:
        """Set the value, cast and clamped.

        Parameters
        ----------
        value : float
            The new number.

        Returns
        -------
        float
            What it became.
        """
        self.value = self._bounded(value)
        return self.value

    def display_text(self) -> str:
        """The value as the box shows it -- decorations and all."""
        return format_value(self.fmt, self.value)

    def edit_text(self) -> str:
        """The value as the box lets it be *edited* -- the bare number."""
        spec = trim_decorations(self.fmt) or ("%d" if self.integer else "%f")
        return format_value(spec, self.value).strip()

    # ------------------------------------------------------------------ #
    def begin_edit(self) -> str:
        """Make the box editable, seeded with the current value, wholly selected."""
        self.editing = True
        self.field.set_text(self.edit_text())
        self.select_all = True
        return self.field.text

    def commit(self) -> float:
        """Read the typed string back into the value and stop editing.

        Returns
        -------
        float
            The value -- unchanged if what was typed does not parse.
        """
        if not self.editing:
            return self.value
        self.value = self._bounded(apply_from_text(self.field.text, self.value, self.fmt))
        self.editing = False
        return self.value

    def cancel(self) -> float:
        """Stop editing and throw the typed string away."""
        self.editing = False
        return self.value

    def insert(self, text: str) -> str:
        """Type printable characters into the box, activating it if needed.

        The first characters typed into a freshly activated box replace what was
        in it, because that box was handed over selected.
        """
        if not self.editing:
            self.begin_edit()
        self.field.insert(str(text), typing=True)
        return self.field.text

    def backspace(self) -> str:
        """Delete the character before the caret, or the whole selection."""
        if not self.editing:
            return ""
        from ..keys import KEY_BACKSPACE

        self.field.key(KEY_BACKSPACE)
        return self.field.text

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press while the box is editable.

        Parameters
        ----------
        key : int
            A ``emtk.keys`` code.
        text : str, optional
            The printable text the key carries.
        modifiers : int, optional
            Passed through to the field.

        Returns
        -------
        bool
            Whether the key was consumed. A key arriving at a box that is not
            editing is *not* consumed -- it belongs to whatever else is on
            screen.
        """
        if not self.editing:
            return False
        from ..keys import KEY_ENTER, KEY_ESCAPE, KEY_RETURN

        if key in (KEY_RETURN, KEY_ENTER):
            self.commit()
            return True
        if key == KEY_ESCAPE:
            self.cancel()
            return True
        return self.field.key(key, text, modifiers)

    # ------------------------------------------------------------------ #
    def _delta(self, fast: bool) -> float:
        """How far one stepper press moves the value."""
        if fast and self.step_fast:
            return self.step_fast
        return self.step

    def increment(self, fast: bool = False) -> float:
        """Step up by ``step``, or by ``step_fast`` when *fast*."""
        return self.set_value(self.value + self._delta(fast))

    def decrement(self, fast: bool = False) -> float:
        """Step down by ``step``, or by ``step_fast`` when *fast*."""
        return self.set_value(self.value - self._delta(fast))

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the box, its contents and the two steppers.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        button = h if self.step else 0.0
        left, box_w = x, w
        if self.label:
            label_w = min(p.text_width(self.label) + 8.0, w * 0.5)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, label_w), TEXT)
            left = x + label_w
            box_w = max(w - label_w, 1.0)
        field_w = max(box_w - button * 2.0, 1.0)
        self._box = (left, field_w, button)

        p.stroke_rect(left, y, field_w, h, BORDER,
                      FRAME_BG_ACTIVE if self.editing else FRAME_BG)
        p.push_clip(left, y, field_w, h)
        if self.editing:
            paint_field(p, self.field, left, y, field_w, h, TEXT, GOLD)
        else:
            p.text(left + 4.0, y, max(field_w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
                   self.display_text(), GOLD)
        p.pop_clip()

        if button:
            minus_x = left + field_w
            p.stroke_rect(minus_x, y, button, h, BORDER, BUTTON)
            p.text(minus_x, y, button, h, ALIGN_CENTER, "-", TEXT)
            p.stroke_rect(minus_x + button, y, button, h, BORDER, BUTTON)
            p.text(minus_x + button, y, button, h, ALIGN_CENTER, "+", TEXT)

    def _geometry(self, box_x: float, box_w: float, box_h: float) -> tuple[float, float, float]:
        """``(field_x, field_w, button)`` -- from the last draw when there is one."""
        if self._box is not None:
            return self._box
        button = box_h if self.step else 0.0
        return (box_x, max(box_w - button * 2.0, 1.0), button)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        fast: bool = False,
    ) -> float:
        """Process a mouse press.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box this control was drawn in.
        fast : bool, optional
            Whether the modifier that means "the larger step" was down. The
            reference reads Ctrl; which key that is belongs to the host.

        Returns
        -------
        float
            The value after the press. A press that misses the control commits
            an edit in progress -- losing focus is what applies a typed number.
        """
        if not hit(x, y, box_x, box_y, box_w, box_h):
            return self.commit()
        left, field_w, button = self._geometry(box_x, box_w, box_h)
        if button:
            if x >= left + field_w + button:
                return self.increment(fast)
            if x >= left + field_w:
                return self.decrement(fast)
        if x >= left and not self.editing:
            self.begin_edit()
        return self.value


class InputFloat(InputScalar):
    """A single-precision number in a box.

    Parameters
    ----------
    label : str, optional
        Caption.
    value : float, optional
        Initial value.
    step, step_fast : float, optional
        Stepper amounts; zero means no steppers.
    fmt : str, optional
        Display format. ``"%.3f"`` is the reference's default for this one.
    v_min, v_max : float, optional
        Optional bounds.

    Notes
    -----
    The reference stores this as a 32-bit float and :class:`InputDouble` as a
    64-bit one; Python has a single float type, so the two differ here only in
    their default format. Rounding every value through single precision was
    deliberately skipped -- it would make ``0.1`` display and read back as
    ``0.100000001`` for no gain outside a C struct.
    """

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        step: float = 0.0,
        step_fast: float = 0.0,
        fmt: str = "%.3f",
        v_min: float | None = None,
        v_max: float | None = None,
    ) -> None:
        super().__init__(label, value, step, step_fast, fmt, v_min, v_max, integer=False)


class InputDouble(InputScalar):
    """A double-precision number in a box.

    Parameters
    ----------
    label : str, optional
        Caption.
    value : float, optional
        Initial value.
    step, step_fast : float, optional
        Stepper amounts; zero means no steppers.
    fmt : str, optional
        Display format. ``"%.6f"`` is the reference's default for this one, and
        the extra decimals are the whole visible difference from
        :class:`InputFloat`.
    v_min, v_max : float, optional
        Optional bounds.
    """

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        step: float = 0.0,
        step_fast: float = 0.0,
        fmt: str = "%.6f",
        v_min: float | None = None,
        v_max: float | None = None,
    ) -> None:
        super().__init__(label, value, step, step_fast, fmt, v_min, v_max, integer=False)


class InputScalarN:
    r"""A row of two to four scalar fields sharing one caption.

    A vector is one *thing* with several numbers, and a row of separate fields
    each with its own label reads as several things. The reference builds this
    out of N ``InputScalar``\\ s with the label drawn once for the group, and so
    does this: :attr:`inputs` are real :class:`InputScalar` objects, so anything
    that works on one works on a component.

    Parameters
    ----------
    label : str, optional
        Caption drawn before the row.
    values : sequence of float, optional
        The components; their count is the row's width.
    step, step_fast : float, optional
        Stepper amounts for every component. The reference's ``InputFloat2/3/4``
        pass no step at all, which is why the default is no buttons: four fields
        each with two buttons is eight buttons in a row nobody can hit.
    fmt : str, optional
        Display format, shared.
    v_min, v_max : float, optional
        Bounds, shared.
    integer : bool, optional
        Hold whole numbers.
    """

    def __init__(
        self,
        label: str = "",
        values: Sequence[float] = (0.0, 0.0),
        step: float = 0.0,
        step_fast: float = 0.0,
        fmt: str = "%.3f",
        v_min: float | None = None,
        v_max: float | None = None,
        integer: bool = False,
    ) -> None:
        self.label = label
        self.inputs = [
            InputScalar("", value, step, step_fast, fmt, v_min, v_max, integer)
            for value in values
        ]
        #: ``(x, w)`` per component, from the last :meth:`draw`.
        self._cells: list[tuple[float, float]] = []

    # ------------------------------------------------------------------ #
    @property
    def values(self) -> list[float]:
        """The components, in order."""
        return [one.value for one in self.inputs]

    def set_values(self, values: Sequence[float]) -> list[float]:
        """Set as many components as there are numbers, clamped each.

        Parameters
        ----------
        values : sequence of float
            The new numbers. Extra ones are ignored rather than growing the row:
            the component count is the control's shape, not its contents.

        Returns
        -------
        list of float
            What the components became.
        """
        for one, value in zip(self.inputs, values):
            one.set_value(value)
        return self.values

    @property
    def editing(self) -> int | None:
        """Index of the component being typed into, or ``None``."""
        for index, one in enumerate(self.inputs):
            if one.editing:
                return index
        return None

    def commit(self) -> list[float]:
        """Apply whichever component is being typed into."""
        for one in self.inputs:
            one.commit()
        return self.values

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Route one key press to the component being typed into."""
        index = self.editing
        if index is None:
            return False
        return self.inputs[index].key(key, text, modifiers)

    # ------------------------------------------------------------------ #
    def _layout(self, p: Painter | None, x: float, w: float) -> tuple[float, float]:
        """``(row_x, cell_w)``: where the components start and how wide each is."""
        left = x
        if self.label and p is not None:
            left = x + min(p.text_width(self.label) + 8.0, w * 0.5)
        count = max(len(self.inputs), 1)
        gap = 4.0
        cell = max((x + w - left - gap * (count - 1)) / count, 1.0)
        return (left, cell)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption and one field per component.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row to draw in.
        """
        if self.label:
            label_w = min(p.text_width(self.label) + 8.0, w * 0.5)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, label_w), TEXT)
        left, cell = self._layout(p, x, w)
        self._cells = []
        for index, one in enumerate(self.inputs):
            cell_x = left + index * (cell + 4.0)
            self._cells.append((cell_x, cell))
            one.draw(p, cell_x, y, cell, h)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        fast: bool = False,
    ) -> list[float]:
        """Process a mouse press by handing it to every component.

        Each component is given its own cell, so exactly one can be hit and the
        rest see a press that missed them -- which is how an edit in a
        neighbouring field gets applied when the user moves on.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The row's box.
        fast : bool, optional
            Whether the larger-step modifier was down.

        Returns
        -------
        list of float
            The components after the press.
        """
        cells = self._cells
        if not cells:
            left, cell = self._layout(None, box_x, box_w)
            cells = [(left + index * (cell + 4.0), cell) for index in range(len(self.inputs))]
        for one, (cell_x, cell_w) in zip(self.inputs, cells):
            one.press(x, y, cell_x, box_y, cell_w, box_h, fast)
        return self.values


def InputFloat2(label: str = "", values: Sequence[float] = (0.0, 0.0), fmt: str = "%.3f") -> InputScalarN:  # noqa: N802
    """A two-component float row, as the reference spells it.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of float, optional
        The two components.
    fmt : str, optional
        Shared display format.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:2] or [0.0, 0.0], fmt=fmt)


def InputFloat3(label: str = "", values: Sequence[float] = (0.0, 0.0, 0.0), fmt: str = "%.3f") -> InputScalarN:  # noqa: N802
    """A three-component float row -- a position, a colour, an angle triple.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of float, optional
        The three components.
    fmt : str, optional
        Shared display format.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:3], fmt=fmt)


def InputFloat4(label: str = "", values: Sequence[float] = (0.0, 0.0, 0.0, 0.0), fmt: str = "%.3f") -> InputScalarN:  # noqa: N802
    """A four-component float row.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of float, optional
        The four components.
    fmt : str, optional
        Shared display format.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:4], fmt=fmt)


def InputInt2(label: str = "", values: Sequence[int] = (0, 0)) -> InputScalarN:  # noqa: N802
    """A two-component whole-number row.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of int, optional
        The two components.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:2], fmt="%d", integer=True)


def InputInt3(label: str = "", values: Sequence[int] = (0, 0, 0)) -> InputScalarN:  # noqa: N802
    """A three-component whole-number row.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of int, optional
        The three components.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:3], fmt="%d", integer=True)


def InputInt4(label: str = "", values: Sequence[int] = (0, 0, 0, 0)) -> InputScalarN:  # noqa: N802
    """A four-component whole-number row.

    Parameters
    ----------
    label : str, optional
        Caption.
    values : sequence of int, optional
        The four components.

    Returns
    -------
    InputScalarN
        The row.
    """
    return InputScalarN(label, list(values)[:4], fmt="%d", integer=True)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
class InputTextWithHint:
    """A one-line field that says what it wants while it is empty.

    The hint is *not* a value. It is drawn in the disabled colour when the
    buffer is empty, it vanishes the moment a character arrives, and
    :attr:`text` never returns it -- an empty field reads as ``""``. Getting
    that wrong turns a placeholder into a default that the user never typed and
    cannot see the difference from.

    Parameters
    ----------
    label : str, optional
        Caption drawn before the box.
    hint : str, optional
        What to show while the buffer is empty.
    text : str, optional
        Initial contents.
    """

    def __init__(self, label: str = "", hint: str = "", text: str = "") -> None:
        self.label = label
        self.field = TextField(placeholder=hint)
        if text:
            self.field.set_text(text)

    # ------------------------------------------------------------------ #
    @property
    def hint(self) -> str:
        """The placeholder."""
        return self.field.placeholder

    @property
    def text(self) -> str:
        """The contents -- never the hint."""
        return self.field.text

    @property
    def cursor(self) -> int:
        """Caret position, in characters from the start."""
        return self.field.cursor

    @property
    def showing_hint(self) -> bool:
        """Whether the hint is what is on screen right now."""
        return not self.field.text and bool(self.field.placeholder)

    def set_text(self, text: str) -> None:
        """Replace the contents, caret at the end."""
        self.field.set_text(text)

    def insert(self, text: str) -> str:
        """Type printable characters at the caret."""
        self.field.key(0, str(text))
        return self.field.text

    def backspace(self) -> str:
        """Delete the character before the caret."""
        from ..keys import KEY_BACKSPACE

        self.field.key(KEY_BACKSPACE)
        return self.field.text

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press; every key is consumed while the field is focused."""
        return self.field.key(key, text, modifiers)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the box, the contents or the hint, and the caret.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        left, box_w = x, w
        if self.label:
            label_w = min(p.text_width(self.label) + 8.0, w * 0.5)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, label_w), TEXT)
            left = x + label_w
            box_w = max(w - label_w, 1.0)
        p.stroke_rect(left, y, box_w, h, BORDER, FRAME_BG)
        p.push_clip(left, y, box_w, h)
        showing = self.showing_hint
        p.text(left + 4.0, y, max(box_w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
               self.hint if showing else self.field.text,
               TEXT_DISABLED if showing else TEXT)
        caret_x = left + 4.0 + p.text_width(self.field.text[: self.field.cursor])
        p.fill_rect(caret_x, y + h * 0.15, max(1.0, h * 0.08), h * 0.7, GOLD)
        p.pop_clip()

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Process a mouse press. Returns whether it landed in the field."""
        return hit(x, y, box_x, box_y, box_w, box_h)


class InputTextMultiline:
    """A text editor with a caret at a row and a column.

    Each line is its own
    :class:`~emtk.widgets.text_field.TextField`, so everything that
    happens *within* a line -- typing, backspace, delete, left, right, home,
    end -- is the one-line editor that already exists. Only the four things that
    cross a line boundary are new: Enter splitting one line into two, backspace
    at column zero joining two into one, and left/right walking off an end.

    The cursor column survives a trip down onto a short line and back up,
    because the *preferred* column is remembered rather than the clamped one --
    the reference's ``preferred_x``. It is dropped by any key that is not up or
    down, which is why typing at the end of a short line and then pressing up
    goes where you just typed rather than where you were three moves ago.

    Parameters
    ----------
    label : str, optional
        Caption drawn above the box.
    text : str, optional
        Initial contents; newlines split it into lines.
    visible_rows : int, optional
        How many rows the box shows before it scrolls. Recomputed from the box's
        height on every :meth:`draw`; this is what it uses until then.
    """

    def __init__(self, label: str = "", text: str = "", visible_rows: int = 4) -> None:
        self.label = label
        self.visible_rows = max(1, int(visible_rows))
        self.row = 0
        self.top = 0
        self._lines: list[TextField] = [TextField()]
        self._preferred_col: int | None = None
        #: ``(box_x, body_y, box_w, body_h, line_h)`` from the last draw.
        self._geometry: tuple[float, float, float, float, float] | None = None
        self._measure: Callable[[str], float] | None = None
        if text:
            self.set_text(text)

    # ------------------------------------------------------------------ #
    @property
    def lines(self) -> list[str]:
        """The contents, one string per line."""
        return [one.text for one in self._lines]

    @property
    def text(self) -> str:
        """The contents as one string, lines joined by newlines."""
        return "\n".join(one.text for one in self._lines)

    @property
    def column(self) -> int:
        """The caret's column within its line."""
        return self._lines[self.row].cursor

    @property
    def cursor(self) -> tuple[int, int]:
        """The caret, as ``(row, column)``."""
        return (self.row, self.column)

    def set_text(self, text: str) -> None:
        r"""Replace the contents; the caret lands at the very end.

        Parameters
        ----------
        text : str
            The new contents. ``\r\n`` and ``\n`` both split a line; a lone
            ``\r`` does too, because a file written on a third platform is not
            the user's mistake.
        """
        body = str(text).replace("\r\n", "\n").replace("\r", "\n")
        self._lines = [TextField() for _ in body.split("\n")]
        for field, line in zip(self._lines, body.split("\n")):
            field.set_text(line)
        self.row = len(self._lines) - 1
        self._lines[self.row].cursor = len(self._lines[self.row].text)
        self._preferred_col = None
        self.top = 0

    def set_cursor(self, row: int, column: int) -> tuple[int, int]:
        """Put the caret somewhere, clamped to the text.

        Parameters
        ----------
        row : int
            Line index.
        column : int
            Character index within that line.

        Returns
        -------
        tuple of int
            Where the caret actually went.
        """
        self.row = int(clamp(int(row), 0, len(self._lines) - 1))
        line = self._lines[self.row]
        line.cursor = int(clamp(int(column), 0, len(line.text)))
        self._preferred_col = None
        return self.cursor

    # ------------------------------------------------------------------ #
    def insert(self, text: str) -> str:
        """Type text at the caret; embedded newlines split lines.

        Parameters
        ----------
        text : str
            What was typed or pasted. Control characters other than newline are
            dropped, as the one-line editor drops them.

        Returns
        -------
        str
            The whole contents afterwards.
        """
        body = str(text).replace("\r\n", "\n").replace("\r", "\n")
        parts = body.split("\n")
        for index, part in enumerate(parts):
            if index:
                self.newline()
            if part:
                self._lines[self.row].key(0, part)
        self._preferred_col = None
        return self.text

    def newline(self) -> str:
        """Split the current line at the caret.

        Returns
        -------
        str
            The whole contents afterwards.
        """
        line = self._lines[self.row]
        head, tail = line.text[: line.cursor], line.text[line.cursor:]
        line.text = head
        line.cursor = len(head)
        following = TextField()
        following.text = tail
        following.cursor = 0
        self._lines.insert(self.row + 1, following)
        self.row += 1
        self._preferred_col = None
        return self.text

    def backspace(self) -> str:
        """Delete backwards, joining this line onto the one above at column zero.

        Returns
        -------
        str
            The whole contents afterwards.
        """
        from ..keys import KEY_BACKSPACE

        self._preferred_col = None
        line = self._lines[self.row]
        if line.cursor > 0:
            line.key(KEY_BACKSPACE)
            return self.text
        if self.row == 0:
            return self.text
        above = self._lines[self.row - 1]
        join_at = len(above.text)
        above.text = above.text + line.text
        above.cursor = join_at
        del self._lines[self.row]
        self.row -= 1
        return self.text

    def delete(self) -> str:
        """Delete forwards, pulling the next line up when at the end of one.

        Returns
        -------
        str
            The whole contents afterwards.
        """
        from ..keys import KEY_DELETE

        self._preferred_col = None
        line = self._lines[self.row]
        if line.cursor < len(line.text):
            line.key(KEY_DELETE)
            return self.text
        if self.row + 1 >= len(self._lines):
            return self.text
        below = self._lines[self.row + 1]
        line.text = line.text + below.text
        del self._lines[self.row + 1]
        return self.text

    # ------------------------------------------------------------------ #
    def move_left(self) -> tuple[int, int]:
        """Caret one character left, wrapping onto the end of the line above."""
        self._preferred_col = None
        line = self._lines[self.row]
        if line.cursor > 0:
            line.cursor -= 1
        elif self.row > 0:
            self.row -= 1
            self._lines[self.row].cursor = len(self._lines[self.row].text)
        return self.cursor

    def move_right(self) -> tuple[int, int]:
        """Caret one character right, wrapping onto the start of the line below."""
        self._preferred_col = None
        line = self._lines[self.row]
        if line.cursor < len(line.text):
            line.cursor += 1
        elif self.row + 1 < len(self._lines):
            self.row += 1
            self._lines[self.row].cursor = 0
        return self.cursor

    def move_up(self) -> tuple[int, int]:
        """Caret one row up, at the column it would prefer.

        On the first row nothing happens at all -- not even a move to the start
        of the text. That is the reference's behaviour (``stb_textedit`` breaks
        out when there is no previous row), and it is why the preferred column
        is left alone here too.
        """
        if self.row == 0:
            return self.cursor
        goal = self.column if self._preferred_col is None else self._preferred_col
        self.row -= 1
        line = self._lines[self.row]
        line.cursor = min(goal, len(line.text))
        self._preferred_col = goal
        return self.cursor

    def move_down(self) -> tuple[int, int]:
        """Caret one row down, at the column it would prefer.

        On the last row the caret goes to the **end of that row** rather than
        staying put: the reference walks to the position one row down, which on
        the last row is the end of the text.
        """
        goal = self.column if self._preferred_col is None else self._preferred_col
        if self.row + 1 >= len(self._lines):
            line = self._lines[self.row]
            line.cursor = len(line.text)
            self._preferred_col = goal
            return self.cursor
        self.row += 1
        line = self._lines[self.row]
        line.cursor = min(goal, len(line.text))
        self._preferred_col = goal
        return self.cursor

    def home(self) -> tuple[int, int]:
        """Caret to the start of its line."""
        self._preferred_col = None
        self._lines[self.row].cursor = 0
        return self.cursor

    def end(self) -> tuple[int, int]:
        """Caret to the end of its line."""
        self._preferred_col = None
        line = self._lines[self.row]
        line.cursor = len(line.text)
        return self.cursor

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press.

        Parameters
        ----------
        key : int
            A ``emtk.keys`` code.
        text : str, optional
            The printable text the key carries.
        modifiers : int, optional
            Unused; accepted so hosts can route keys uniformly.

        Returns
        -------
        bool
            Always ``True``: an editor with the caret consumes everything,
            including the keys it does nothing with.
        """
        from ..keys import (
            KEY_BACKSPACE,
            KEY_DELETE,
            KEY_DOWN,
            KEY_END,
            KEY_ENTER,
            KEY_HOME,
            KEY_LEFT,
            KEY_RETURN,
            KEY_RIGHT,
            KEY_UP,
        )

        if key in (KEY_RETURN, KEY_ENTER):
            self.newline()
        elif key == KEY_BACKSPACE:
            self.backspace()
        elif key == KEY_DELETE:
            self.delete()
        elif key == KEY_LEFT:
            self.move_left()
        elif key == KEY_RIGHT:
            self.move_right()
        elif key == KEY_UP:
            self.move_up()
        elif key == KEY_DOWN:
            self.move_down()
        elif key == KEY_HOME:
            self.home()
        elif key == KEY_END:
            self.end()
        else:
            clean = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
            if clean:
                self.insert(clean)
        return True

    # ------------------------------------------------------------------ #
    def scroll(self, rows: int) -> int:
        """Move the visible window by whole rows, without moving the caret."""
        self.top = int(clamp(self.top + int(rows), 0,
                             max(len(self._lines) - self.visible_rows, 0)))
        return self.top

    def _follow_cursor(self, rows: int) -> int:
        """Scroll the window the least amount that puts the caret's row in it."""
        if self.row < self.top:
            self.top = self.row
        elif self.row >= self.top + rows:
            self.top = self.row - rows + 1
        self.top = int(clamp(self.top, 0, max(len(self._lines) - rows, 0)))
        return self.top

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the frame, the visible rows and the caret.

        The window scrolls here rather than in the movement methods, because how
        many rows fit is a fact about the box and the box is only known at draw
        time. The caret is therefore on screen whenever the editor is drawn.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        line_h = p.line_height() * 1.2
        top_y = y
        if self.label:
            p.text(x, y, w, line_h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, w), TEXT)
            top_y = y + line_h
        body_h = max(y + h - top_y, line_h)
        rows = max(int(body_h / max(line_h, 1e-6)), 1)
        self.visible_rows = rows
        self._follow_cursor(rows)
        self._geometry = (x, top_y, w, body_h, line_h)
        self._measure = p.text_width

        p.stroke_rect(x, top_y, w, body_h, BORDER, FRAME_BG)
        p.push_clip(x, top_y, w, body_h)
        for offset in range(rows):
            index = self.top + offset
            if index >= len(self._lines):
                break
            p.text(x + 4.0, top_y + offset * line_h, max(w - 8.0, 1.0), line_h,
                   ALIGN_VCENTER | ALIGN_LEFT, self._lines[index].text, TEXT)
        if self.top <= self.row < self.top + rows:
            line = self._lines[self.row]
            caret_x = x + 4.0 + p.text_width(line.text[: line.cursor])
            caret_y = top_y + (self.row - self.top) * line_h
            p.fill_rect(caret_x, caret_y + line_h * 0.15,
                        max(1.0, line_h * 0.08), line_h * 0.7, GOLD)
        p.pop_clip()

    def _column_at(self, line: str, offset: float) -> int:
        """Which column a press *offset* pixels into a line lands on."""
        measure = self._measure
        if measure is None:
            return len(line)
        best, best_gap = 0, abs(offset)
        for column in range(1, len(line) + 1):
            gap = abs(measure(line[:column]) - offset)
            if gap <= best_gap:
                best, best_gap = column, gap
        return best

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> tuple[int, int] | None:
        """Process a mouse press by putting the caret where it landed.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box this editor was drawn in.

        Returns
        -------
        tuple of int or None
            The caret as ``(row, column)``, or ``None`` when the press missed.
            Without a previous :meth:`draw` there is nothing to measure text
            with, so the caret goes to the end of the row that was hit.
        """
        if not hit(x, y, box_x, box_y, box_w, box_h):
            return None
        if self._geometry is None:
            return self.set_cursor(self.row, len(self._lines[self.row].text))
        geo_x, body_y, _geo_w, _body_h, line_h = self._geometry
        offset = int(clamp((y - body_y) / max(line_h, 1e-6), 0.0, float(self.visible_rows - 1)))
        row = int(clamp(self.top + offset, 0, len(self._lines) - 1))
        column = self._column_at(self._lines[row].text, x - (geo_x + 4.0))
        return self.set_cursor(row, column)
