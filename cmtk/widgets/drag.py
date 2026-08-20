"""Drag controls: a number you scrub rather than a slider you aim.

Why this is not a slider with a different name
----------------------------------------------
:class:`~cmtk.widgets.basic.SliderFloat` maps an *absolute* position in
its box onto its range: press at the middle of the track and the value is the
middle of the range, wherever the track happens to be on screen. A drag has no
track at all. Its box is only where the gesture *starts*; from then on the
value moves by the mouse's **delta** since the last event, scaled by
:attr:`v_speed`, and it keeps moving even after the pointer has left the box.
That is the whole widget, and it is why a drag can be unbounded -- there is no
track whose ends the range would have to fit into.

Two consequences follow, and both are the classic bugs here:

* the host hands us absolute positions, so each control remembers the last one
  and differences it itself (:meth:`_DragScalar.drag`);
* a delta small enough to round to nothing must not *be* nothing. An integer
  drag at a tenth of a unit per pixel would round every single event to zero
  and the value would never move at all, however far you dragged. The reference
  fixes this with an accumulator (``g.DragCurrentAccum``): every event adds its
  scaled delta to a float running total, the *whole* part of that total is what
  moves the value, and the remainder is carried into the next event. Ported
  faithfully in :meth:`_DragScalar._apply`.

What came from the reference
----------------------------
``DragBehaviorT`` and the ``DragScalar`` / ``DragScalarN`` /
``DragFloatRange2`` / ``DragIntRange2`` wrappers in the reference
implementation's ``imgui_widgets.cpp``, including:

* the default tweak speed when ``v_speed`` is zero -- one hundredth of the
  range (:data:`DRAG_SPEED_DEFAULT_RATIO`), and only when the control is
  actually bounded;
* the "unbounded" case: ``v_min >= v_max`` means *no bound*, so the value is
  never clamped. ``v_min == v_max`` is bounded only when that shared value is
  non-zero, which is what makes the ``0, 0`` default unbounded;
* the drag threshold: a press that does not travel is a click, not a drag, so
  nothing moves until the pointer has left a small radius around the anchor;
* the logarithmic path, in which the delta is applied in the range's
  *parametric* 0..1 space rather than to the value, so equal pixel distances
  multiply the value by a constant factor. Its zero-crossing handling is the
  reference's: a range spanning zero is split at the parametric position of
  zero and each half is scaled logarithmically away from an epsilon derived
  from the format's decimal precision, so a range like ``-100 .. 100`` can
  still reach exactly zero;
* the refusal to clamp while the value is *already* outside the range and
  being pushed further out, so a value of 300 in a ``0..255`` control is not
  yanked back by a drag to the right.

Typing a value
--------------
The reference turns a ctrl-click (or double-click) into a text field. cmtk
has no modifier feed at this seam and inventing one would be a second input
path, so the same state is reachable explicitly:
:meth:`_DragScalar.begin_text_edit`, :meth:`_DragScalar.set_text_buffer`,
:meth:`_DragScalar.commit_text_edit`, :meth:`_DragScalar.cancel_text_edit`.
The host decides what gesture opens it.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter
from ..style import (
    BORDER,
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

__all__ = [
    "DRAG_SPEED_DEFAULT_RATIO",
    "DRAG_THRESHOLD",
    "DragFloat",
    "DragInt",
    "DragFloatN",
    "DragIntN",
    "DragFloatRange2",
    "DragIntRange2",
]

#: What one hundredth of the range is worth when ``v_speed`` is left at zero.
#: The reference's ``g.DragSpeedDefaultRatio``.
DRAG_SPEED_DEFAULT_RATIO = 1.0 / 100.0

#: How far the pointer must travel from the press before anything moves. The
#: reference's ``io.MouseDragThreshold`` (6) times its ``DRAG_MOUSE_THRESHOLD_FACTOR``
#: (0.5), which exists so a drag reacts sooner than a drag-and-drop would.
DRAG_THRESHOLD = 3.0

#: Gap between a drag's frame and its caption, and between the components of a
#: multi-component row. The reference's ``style.ItemInnerSpacing.x``.
_INNER_SPACING = 4.0

#: The leading number in a formatted string. Used to read a value back out of
#: its own format, which is how the reference rounds to display precision.
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

#: *Detects* -- does not interpret -- the percentage spec that
#: :func:`~cmtk.style.format_value` understands. A value shown
#: through ``"%.0%"`` is displayed multiplied by a hundred, so reading it back
#: has to undo that; the formatting itself stays in ``style``.
_PERCENT_SPEC = re.compile(r"%\.(\d+)%")


# --------------------------------------------------------------------------
# Format-string arithmetic, ported from the reference's helpers
# --------------------------------------------------------------------------
def _format_start(fmt: str) -> int:
    """Where the printf spec begins inside a decorated format string.

    The reference's ``ImParseFormatFindStart``: ``"hello %.3f"`` starts at 6,
    ``"blah"`` has no spec, and ``"%%"`` is a literal percent rather than one.

    Parameters
    ----------
    fmt : str
        The format string.

    Returns
    -------
    int
        Index of the ``%`` that opens the spec, or ``len(fmt)`` if there is
        none.
    """
    index = 0
    while index < len(fmt):
        if fmt[index] == "%":
            if index + 1 >= len(fmt) or fmt[index + 1] != "%":
                return index
            index += 1
        index += 1
    return len(fmt)


def _format_end(fmt: str, start: int) -> int:
    """Where the printf spec that begins at *start* ends.

    The reference's ``ImParseFormatFindEnd``: the spec runs to the first
    letter that is a *type* rather than a size modifier (``I``, ``L``, ``h``,
    ``j``, ``l``, ``t``, ``w``, ``z``).

    Parameters
    ----------
    fmt : str
        The format string.
    start : int
        Index of the opening ``%``.

    Returns
    -------
    int
        Index one past the spec's last character.
    """
    if start >= len(fmt) or fmt[start] != "%":
        return start
    ignored = set("ILhjltwz")
    for index in range(start, len(fmt)):
        char = fmt[index]
        if char.isalpha() and char not in ignored:
            return index + 1
    return len(fmt)


def _format_precision(fmt: str, default: int) -> int:
    """The number of decimals a format string asks for.

    The reference's ``ImParseFormatPrecision``. Scientific and general
    notation report ``-1`` -- "as many as it takes" -- which the callers here
    read as the smallest epsilon they are willing to use.

    Parameters
    ----------
    fmt : str
        The format string.
    default : int
        Reported when the spec carries no precision.

    Returns
    -------
    int
        The precision.
    """
    start = _format_start(fmt)
    if start >= len(fmt) or fmt[start] != "%":
        return default
    index = start + 1
    while index < len(fmt) and fmt[index].isdigit():
        index += 1
    precision: int | None = None
    if index < len(fmt) and fmt[index] == ".":
        index += 1
        digits = ""
        while index < len(fmt) and fmt[index].isdigit():
            digits += fmt[index]
            index += 1
        precision = int(digits) if digits else 0
        if precision < 0 or precision > 99:
            precision = default
    if index < len(fmt) and fmt[index] in "eE":
        return -1
    if index < len(fmt) and fmt[index] in "gG" and precision is None:
        return -1
    return default if precision is None else precision


def _trim_decorations(fmt: str) -> str:
    """The bare printf spec, with any prose around it removed.

    The reference's ``ImParseFormatTrimDecorations``, used when a drag turns
    into a text field: the field should offer ``3.140``, not ``radius 3.140 nm``.

    Parameters
    ----------
    fmt : str
        The format string.

    Returns
    -------
    str
        The spec alone, or ``""`` when the string contains none.
    """
    start = _format_start(fmt)
    if start >= len(fmt) or fmt[start] != "%":
        return ""
    return fmt[start:_format_end(fmt, start)]


def _round_to_format(fmt: str, value: float) -> float:
    """*value* as its own display would read it back.

    The reference's ``RoundScalarWithFormatT``: a control formatted ``"%.1f"``
    holds 3.1 after a drag rather than 3.14159, so that what the user sees and
    what the model carries are the same number. Doing it by formatting and
    parsing rather than by rounding is deliberate -- the format string is the
    single authority on precision, and it may say ``%.2e`` or ``%.0%`` as
    easily as ``%.3f``.

    Parameters
    ----------
    fmt : str
        The control's format string.
    value : float
        The number.

    Returns
    -------
    float
        The rounded number, or *value* unchanged when the format shows no
        number at all.
    """
    spec = _trim_decorations(fmt)
    if not spec:
        return value
    match = _NUMBER.match(format_value(spec, value).lstrip())
    if match is None:
        return value
    parsed = float(match.group(0))
    if _PERCENT_SPEC.search(spec):
        parsed /= 100.0
    return parsed


# --------------------------------------------------------------------------
# The logarithmic parametrisation, ported from the reference's slider scaling
# --------------------------------------------------------------------------
def _log_ratio_from_value(
    value: float,
    v_min: float,
    v_max: float,
    epsilon: float,
) -> float:
    """Where *value* sits in ``0..1`` along a logarithmic range.

    The reference's ``ScaleRatioFromValueT`` with its logarithmic branch and a
    zero deadzone of nothing -- drags have no deadzone because there is no
    grab to snap.

    Parameters
    ----------
    value : float
        The number.
    v_min, v_max : float
        The range. May be given backwards, which flips the result.
    epsilon : float
        How close to zero the range is allowed to get; below it the ends are
        fudged, since ``log(0)`` has no answer.

    Returns
    -------
    float
        The parametric position, ``0..1``.
    """
    if v_min == v_max:
        return 0.0
    clamped = clamp(value, v_min, v_max) if v_min < v_max else clamp(value, v_max, v_min)
    flipped = v_max < v_min
    if flipped:
        v_min, v_max = v_max, v_min

    min_fudged = (-epsilon if v_min < 0.0 else epsilon) if abs(v_min) < epsilon else v_min
    max_fudged = (-epsilon if v_max < 0.0 else epsilon) if abs(v_max) < epsilon else v_max
    # A range of (-100 .. 0) has to become (-100 .. -epsilon), not (-100 .. epsilon).
    if v_min == 0.0 and v_max < 0.0:
        min_fudged = -epsilon
    elif v_max == 0.0 and v_min < 0.0:
        max_fudged = -epsilon

    if clamped <= min_fudged:
        result = 0.0
    elif clamped >= max_fudged:
        result = 1.0
    elif (v_min * v_max) < 0.0:
        zero_point = (-v_min) / (v_max - v_min)
        if value == 0.0:
            result = zero_point
        elif value < 0.0:
            below = math.log(-clamped / epsilon) / math.log(-min_fudged / epsilon)
            result = (1.0 - below) * zero_point
        else:
            above = math.log(clamped / epsilon) / math.log(max_fudged / epsilon)
            result = zero_point + above * (1.0 - zero_point)
    elif v_min < 0.0 or v_max < 0.0:
        result = 1.0 - (math.log(-clamped / -max_fudged) / math.log(-min_fudged / -max_fudged))
    else:
        result = math.log(clamped / min_fudged) / math.log(max_fudged / min_fudged)
    return (1.0 - result) if flipped else result


def _log_value_from_ratio(
    ratio: float,
    v_min: float,
    v_max: float,
    epsilon: float,
) -> float:
    """The value at parametric position *ratio* along a logarithmic range.

    The reference's ``ScaleValueFromRatioT``, logarithmic branch. The extremes
    are special-cased before any of the fudging, because otherwise a drag
    pinned at one end lands *near* the bound rather than on it.

    Parameters
    ----------
    ratio : float
        The parametric position.
    v_min, v_max : float
        The range; may be given backwards.
    epsilon : float
        The zero-avoidance fudge, as in :func:`_log_ratio_from_value`.

    Returns
    -------
    float
        The value.
    """
    if ratio <= 0.0 or v_min == v_max:
        return v_min
    if ratio >= 1.0:
        return v_max

    min_fudged = (-epsilon if v_min < 0.0 else epsilon) if abs(v_min) < epsilon else v_min
    max_fudged = (-epsilon if v_max < 0.0 else epsilon) if abs(v_max) < epsilon else v_max
    flipped = v_max < v_min
    if flipped:
        min_fudged, max_fudged = max_fudged, min_fudged
    if v_max == 0.0 and v_min < 0.0:
        max_fudged = -epsilon

    flip_ratio = (1.0 - ratio) if flipped else ratio
    if (v_min * v_max) < 0.0:
        zero_point = (-min(v_min, v_max)) / abs(v_max - v_min)
        if flip_ratio == zero_point:
            return 0.0
        if flip_ratio < zero_point:
            return -(epsilon * math.pow(-min_fudged / epsilon, 1.0 - (flip_ratio / zero_point)))
        above = (flip_ratio - zero_point) / (1.0 - zero_point)
        return epsilon * math.pow(max_fudged / epsilon, above)
    if v_min < 0.0 or v_max < 0.0:
        return -(-max_fudged * math.pow(-min_fudged / -max_fudged, 1.0 - flip_ratio))
    return min_fudged * math.pow(max_fudged / min_fudged, flip_ratio)


# --------------------------------------------------------------------------
# The control
# --------------------------------------------------------------------------
class _DragScalar:
    """A number scrubbed by the mouse's delta. The behaviour, once.

    :class:`DragFloat` and :class:`DragInt` are this class with a type: what
    differs between them is whether the accumulator's whole part or its whole
    *and* fractional part reaches the value, whether the result is rounded to
    the display format, and the reference's integer-overflow guard on the
    clamp. Everything else -- the accumulator, the threshold, the default
    speed, the bounds, the logarithmic path, the text field -- is shared,
    because two copies of an accumulator are two chances to get the remainder
    wrong.

    Parameters
    ----------
    label : str, optional
        Caption, drawn to the right of the frame as the reference does. Only
        the frame is interactive.
    value : float, optional
        Initial value.
    v_speed : float, optional
        Units per pixel of drag. Zero means "one hundredth of the range", and
        only has that meaning when the control is bounded.
    v_min, v_max : float, optional
        The bounds. ``v_min >= v_max`` means unbounded -- which the ``0, 0``
        default therefore is.
    fmt : str, optional
        How the value is displayed, and (for floats) the precision it is
        rounded to.
    logarithmic : bool, optional
        Scrub in the range's parametric space rather than in the value, so
        equal distances multiply rather than add. Needs a bounded range; an
        unbounded logarithmic drag falls back to linear.
    wrap : bool, optional
        Pass out of one end and in at the other, instead of clamping. The
        reference's ``ImGuiSliderFlags_WrapAround``.
    round_to_format : bool, optional
        Round the value to the format's precision after every event. The
        reference does this unless told not to.
    clamp_on_input : bool, optional
        Whether a *typed* value is confined to the bounds. The reference
        leaves this off, so typing can exceed a range that dragging cannot.
    """

    #: Whether the value is continuous. Set by the subclasses.
    _is_float = True

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        v_speed: float = 1.0,
        v_min: float = 0.0,
        v_max: float = 0.0,
        fmt: str = "%.3f",
        logarithmic: bool = False,
        wrap: bool = False,
        round_to_format: bool = True,
        clamp_on_input: bool = False,
    ) -> None:
        self.label = label
        self.v_speed = float(v_speed)
        self.v_min = self._cast(v_min)
        self.v_max = self._cast(v_max)
        self.fmt = fmt
        self.logarithmic = bool(logarithmic)
        self.wrap = bool(wrap)
        self.round_to_format = bool(round_to_format)
        self.clamp_on_input = bool(clamp_on_input)
        #: Set by a host that wants the control shown but not scrubbed. The
        #: reference's ``ImGuiSliderFlags_ReadOnly``; the range controls set it
        #: themselves when one half has nowhere left to go.
        self.read_only = False
        #: How far the pointer must travel before the drag starts.
        self.drag_threshold = DRAG_THRESHOLD
        self.value = self._cast(value)
        if self.is_bounded:
            self.value = self._cast(clamp(self.value, self.v_min, self.v_max))

        self._held = False
        self._accum = 0.0
        self._accum_dirty = False
        self._last_x = 0.0
        self._anchor: tuple[float, float] = (0.0, 0.0)
        self._travel = 0.0
        self._label_w = 0.0
        self._editing = False
        self._buffer = ""

    # -- typing --------------------------------------------------------- #
    def _cast(self, value: float) -> float:
        """The value as this control's type.

        Parameters
        ----------
        value : float
            The number.

        Returns
        -------
        float
            *value* as a float, or truncated to an int by :class:`DragInt`.
        """
        return float(value)

    # -- what the range means ------------------------------------------- #
    @property
    def is_bounded(self) -> bool:
        """Whether the value is confined at all.

        ``v_min >= v_max`` is the reference's way of spelling "no bound", with
        one exception: a range whose ends are equal *and non-zero* pins the
        value to that number. The default ``0, 0`` is therefore unbounded
        rather than pinned to zero, which is what makes a bare
        :class:`DragFloat` scrub freely.
        """
        return (self.v_min < self.v_max) or (self.v_min == self.v_max and self.v_min != 0)

    @property
    def effective_speed(self) -> float:
        """Units per pixel actually used.

        A ``v_speed`` of zero asks for the reference's default: one hundredth
        of the range. That only has a meaning for a bounded, finite range, so
        an unbounded control keeps the literal zero and does not move -- which
        is the reference's behaviour and is why ``v_speed`` defaults to one.
        """
        speed = self.v_speed
        if speed == 0.0 and self.is_bounded:
            span = self.v_max - self.v_min
            if math.isfinite(span):
                speed = span * DRAG_SPEED_DEFAULT_RATIO
        return speed

    @property
    def held(self) -> bool:
        """Whether a drag gesture is in progress."""
        return self._held

    @property
    def editing(self) -> bool:
        """Whether the control is currently a text field."""
        return self._editing

    @property
    def text_buffer(self) -> str:
        """What the text field currently holds."""
        return self._buffer

    # -- the gesture ----------------------------------------------------- #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Begin a gesture and remember the anchor.

        Nothing moves here: a drag's press only says *where from*. The
        accumulator is cleared, which is the reference's
        ``ActiveIdIsJustActivated`` branch -- a new gesture must not inherit
        the leftovers of the last one.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the control was drawn into. Only the frame part of it is
            interactive; the caption is not.

        Returns
        -------
        bool
            Whether the gesture started.
        """
        frame_w = max(box_w - self._label_w, 1.0)
        if self.read_only or self._editing or not hit(x, y, box_x, box_y, frame_w, box_h):
            self._held = False
            return False
        self._held = True
        self._anchor = (x, y)
        self._last_x = x
        self._travel = 0.0
        self._accum = 0.0
        self._accum_dirty = False
        return True

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Apply the movement since the last event.

        The box is ignored on purpose. A drag that has started keeps running
        wherever the pointer goes -- that is the difference from a slider,
        which would re-read the pointer against its track and jump.

        Parameters
        ----------
        x, y : float
            Where the pointer is now.
        box_x, box_y, box_w, box_h : float
            The box; unused, and present so the control matches the family's
            signature.

        Returns
        -------
        bool
            Whether the value changed.
        """
        if not self._held or self.read_only:
            return False
        delta = x - self._last_x
        self._last_x = x
        self._travel = max(self._travel, math.hypot(x - self._anchor[0], y - self._anchor[1]))
        if self._travel <= self.drag_threshold:
            return False
        return self._apply(delta)

    def release(self) -> None:
        """End the gesture. The carried remainder goes with it."""
        self._held = False
        self._accum = 0.0
        self._accum_dirty = False

    def _apply(self, delta_px: float) -> bool:
        """Move the value by *delta_px* pixels of drag.

        This is ``DragBehaviorT``. Read in order: scale the pixels into value
        space; drop the accumulator when we are already outside the range and
        being pushed further out; add to the accumulator; take what the
        accumulator can pay for; round; **give the change back to the
        accumulator** so nothing is lost to rounding; clamp or wrap.

        Parameters
        ----------
        delta_px : float
            Pixels moved since the last event.

        Returns
        -------
        bool
            Whether the value changed.
        """
        bounded = self.is_bounded
        use_log = self.logarithmic and bounded
        adjust = delta_px * self.effective_speed
        span = self.v_max - self.v_min
        if use_log and math.isfinite(span) and span > 0.000001:
            adjust /= span

        v_old = self.value
        past_and_pushing = bounded and not self.wrap and (
            (v_old >= self.v_max and adjust > 0.0) or (v_old <= self.v_min and adjust < 0.0)
        )
        if past_and_pushing:
            self._accum = 0.0
            self._accum_dirty = False
        elif adjust != 0.0:
            self._accum += adjust
            self._accum_dirty = True
        if not self._accum_dirty:
            return False

        epsilon = 0.0
        old_parametric = 0.0
        if use_log:
            precision = _format_precision(self.fmt, 3 if self._is_float else 1)
            epsilon = math.pow(0.1, float(precision))
            old_parametric = _log_ratio_from_value(v_old, self.v_min, self.v_max, epsilon)
            v_cur = _log_value_from_ratio(
                old_parametric + self._accum, self.v_min, self.v_max, epsilon
            )
            v_cur = self._cast(v_cur)
        elif self._is_float:
            v_cur = v_old + self._accum
        else:
            # Truncation, not rounding: the fraction is owed to the next event.
            v_cur = v_old + math.trunc(self._accum)

        if self._is_float and self.round_to_format:
            v_cur = _round_to_format(self.fmt, v_cur)

        self._accum_dirty = False
        if use_log:
            new_parametric = _log_ratio_from_value(v_cur, self.v_min, self.v_max, epsilon)
            self._accum -= new_parametric - old_parametric
        else:
            self._accum -= v_cur - v_old
        if v_cur == 0:
            v_cur = abs(v_cur)  # a drag through zero must not leave a signed zero behind

        if v_cur != v_old and bounded:
            if self.wrap:
                width = self.v_max - self.v_min + (0 if self._is_float else 1)
                if v_cur < self.v_min:
                    v_cur += width
                if v_cur > self.v_max:
                    v_cur -= width
            else:
                # The second half of each test is the reference's integer
                # overflow guard: a wrapped int has landed on the wrong side.
                if v_cur < self.v_min or (v_cur > v_old and adjust < 0.0 and not self._is_float):
                    v_cur = self.v_min
                if v_cur > self.v_max or (v_cur < v_old and adjust > 0.0 and not self._is_float):
                    v_cur = self.v_max

        if v_cur == v_old:
            return False
        self.value = self._cast(v_cur)
        return True

    def set_value(self, value: float) -> float:
        """Put the value somewhere directly, clamped when bounded.

        Parameters
        ----------
        value : float
            The new value.

        Returns
        -------
        float
            What it ended up as.
        """
        new = self._cast(value)
        if self.is_bounded:
            new = self._cast(clamp(new, self.v_min, self.v_max))
        self.value = new
        return self.value

    # -- typing a value -------------------------------------------------- #
    def begin_text_edit(self) -> str:
        """Turn the control into a text field and hand back its contents.

        The reference reaches this state with ctrl-click or a double click.
        cmtk's painter seam carries no modifiers and no click counts, so the
        gesture is the host's to choose and this is the state change itself.

        Returns
        -------
        str
            The value rendered through the format with its prose stripped --
            ``"3.140"`` rather than ``"radius 3.140 nm"``, because what comes
            back has to parse.
        """
        self._held = False
        self._editing = True
        spec = _trim_decorations(self.fmt) or ("%.3f" if self._is_float else "%d")
        self._buffer = format_value(spec, self.value)
        return self._buffer

    def set_text_buffer(self, text: str) -> str:
        """Replace what the text field holds.

        Parameters
        ----------
        text : str
            The new contents.

        Returns
        -------
        str
            The contents, unchanged, for chaining.
        """
        self._buffer = str(text)
        return self._buffer

    def commit_text_edit(self) -> bool:
        """Parse the field and leave edit mode.

        Text that holds no number leaves the value alone rather than zeroing
        it -- the reference's ``DataTypeApplyFromText`` returns false on a
        failed scan, and a field cleared by accident must not silently mean
        zero.

        Returns
        -------
        bool
            Whether the value changed.
        """
        self._editing = False
        match = _NUMBER.match(self._buffer.strip())
        if match is None:
            return False
        parsed = self._cast(float(match.group(0)))
        if self.clamp_on_input and self.is_bounded:
            parsed = self._cast(clamp(parsed, self.v_min, self.v_max))
        if parsed == self.value:
            return False
        self.value = parsed
        return True

    def cancel_text_edit(self) -> None:
        """Leave edit mode and throw the field away."""
        self._editing = False
        self._buffer = ""

    # -- drawing --------------------------------------------------------- #
    def display_text(self) -> str:
        """What the frame reads, value and decorations together."""
        return format_value(self.fmt, self.value)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, the value inside it and the caption beside it.

        There is no track and no grab, which is the point: a drag that drew a
        filled bar would be read as a slider and aimed at rather than scrubbed.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        self._label_w = (p.text_width(self.label) + _INNER_SPACING) if self.label else 0.0
        frame_w = max(w - self._label_w, 1.0)
        frame = FRAME_BG_ACTIVE if (self._held or self._editing) else FRAME_BG
        p.stroke_rect(x, y, frame_w, h, BORDER, frame)

        p.push_clip(x, y, frame_w, h)
        if self._editing:
            p.text(x + 4.0, y, max(frame_w - 8.0, 1.0), h,
                   ALIGN_VCENTER | ALIGN_LEFT, self._buffer, TEXT)
            caret_x = x + 4.0 + p.text_width(self._buffer)
            p.fill_rect(caret_x, y + h * 0.15, max(1.0, h * 0.08), h * 0.7, GOLD)
        else:
            colour = TEXT_DISABLED if self.read_only else TEXT
            p.text(x, y, frame_w, h, ALIGN_CENTER,
                   fit_text(p, self.display_text(), frame_w - 6.0), colour)
        p.pop_clip()

        if self.label:
            p.text(x + frame_w + _INNER_SPACING, y, self._label_w, h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, TEXT)


class DragFloat(_DragScalar):
    """A floating-point number scrubbed by dragging.

    See :class:`_DragScalar` for the parameters; this is that behaviour with a
    continuous value, so the whole accumulator reaches the value on every
    event and the result is rounded to the format's precision.
    """

    _is_float = True


class DragInt(_DragScalar):
    """A whole number scrubbed by dragging.

    The interesting half of the family. Only the *whole* part of the
    accumulator reaches the value, and the fraction is carried, so a speed of
    a twentieth of a unit per pixel moves the value by one every twenty
    pixels -- rather than by zero, forever, which is what rounding each event
    on its own would give.

    Parameters
    ----------
    label : str, optional
        Caption.
    value : int, optional
        Initial value.
    v_speed : float, optional
        Units per pixel; a float on purpose, so speeds below one unit per
        pixel can be asked for.
    v_min, v_max : int, optional
        The bounds; ``v_min >= v_max`` is unbounded.
    fmt : str, optional
        Display format.
    logarithmic, wrap, clamp_on_input : bool, optional
        As :class:`_DragScalar`.
    """

    _is_float = False

    def __init__(
        self,
        label: str = "",
        value: int = 0,
        v_speed: float = 1.0,
        v_min: int = 0,
        v_max: int = 0,
        fmt: str = "%d",
        logarithmic: bool = False,
        wrap: bool = False,
        clamp_on_input: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            value=value,
            v_speed=v_speed,
            v_min=v_min,
            v_max=v_max,
            fmt=fmt,
            logarithmic=logarithmic,
            wrap=wrap,
            round_to_format=False,
            clamp_on_input=clamp_on_input,
        )

    def _cast(self, value: float) -> int:
        """*value* truncated to a whole number, the way a C cast would."""
        return int(value)


# --------------------------------------------------------------------------
# Multi-component rows
# --------------------------------------------------------------------------
def _split_cells(w: float, label_w: float, count: int) -> tuple[float, float]:
    """How a row of *count* components divides a box.

    The reference's ``PushMultiItemsWidths``: equal widths, one inner spacing
    between each pair, the caption taking what it needs at the right.

    Parameters
    ----------
    w : float
        The whole box's width.
    label_w : float
        What the caption occupies, spacing included.
    count : int
        How many components.

    Returns
    -------
    tuple of float
        ``(body_width, cell_width)``.
    """
    body = max(w - label_w, 1.0)
    count = max(int(count), 1)
    cell = max((body - _INNER_SPACING * (count - 1)) / count, 1.0)
    return (body, cell)


class _DragScalarN:
    r"""A row of drags over one vector: 2, 3 or 4 of them side by side.

    The reference builds this from *n* independent ``DragScalar``\\ s rather
    than from one control with *n* values, and so does this: each component
    keeps its own accumulator, because a shared one would leak the remainder
    of the X drag into Y the moment the gesture moved between them.

    Parameters
    ----------
    label : str, optional
        Caption for the whole row, drawn once at the right.
    values : sequence of float, optional
        The components. Their count is the row's width.
    v_speed : float, optional
        Units per pixel, shared by every component.
    v_min, v_max : float, optional
        Bounds, shared by every component.
    fmt : str, optional
        Display format, shared.
    logarithmic, wrap, clamp_on_input : bool, optional
        As :class:`_DragScalar`.
    """

    #: Which control the row is made of. Set by the subclasses.
    _component = DragFloat

    def __init__(
        self,
        label: str = "",
        values: Sequence[float] = (0.0, 0.0, 0.0),
        v_speed: float = 1.0,
        v_min: float = 0.0,
        v_max: float = 0.0,
        fmt: str = "%.3f",
        logarithmic: bool = False,
        wrap: bool = False,
        clamp_on_input: bool = False,
    ) -> None:
        self.label = label
        self.components: list[_DragScalar] = [
            self._component(
                "", value, v_speed=v_speed, v_min=v_min, v_max=v_max, fmt=fmt,
                logarithmic=logarithmic, wrap=wrap, clamp_on_input=clamp_on_input,
            )
            for value in values
        ]
        self._label_w = 0.0
        self._active: int | None = None

    @property
    def values(self) -> list[float]:
        """The components' values, in order."""
        return [component.value for component in self.components]

    @values.setter
    def values(self, values: Sequence[float]) -> None:
        for component, value in zip(self.components, values):
            component.set_value(value)

    @property
    def active(self) -> int | None:
        """Which component the current gesture is scrubbing, if any."""
        return self._active

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint each component in its cell, then the row's caption.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        self._label_w = (p.text_width(self.label) + _INNER_SPACING) if self.label else 0.0
        body, cell = _split_cells(w, self._label_w, len(self.components))
        for index, component in enumerate(self.components):
            component.draw(p, x + index * (cell + _INNER_SPACING), y, cell, h)
        if self.label:
            p.text(x + body + _INNER_SPACING, y, self._label_w, h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, TEXT)

    def _cell_box(
        self, index: int, box_x: float, box_w: float, box_h: float
    ) -> tuple[float, float, float]:
        """The box a component occupies inside the row's box.

        Parameters
        ----------
        index : int
            Which component.
        box_x, box_w, box_h : float
            The row's box.

        Returns
        -------
        tuple of float
            ``(x, w, h)`` for that component.
        """
        _body, cell = _split_cells(box_w, self._label_w, len(self.components))
        return (box_x + index * (cell + _INNER_SPACING), cell, box_h)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> int | None:
        """Begin a gesture on whichever component the press landed on.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The row's box.

        Returns
        -------
        int or None
            The component index, or ``None`` if the press missed them all.
        """
        self._active = None
        for index in range(len(self.components)):
            cell_x, cell_w, cell_h = self._cell_box(index, box_x, box_w, box_h)
            if self.components[index].press(x, y, cell_x, box_y, cell_w, cell_h):
                self._active = index
                return index
        return None

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Continue the gesture on the component it started on.

        Parameters
        ----------
        x, y : float
            Where the pointer is now.
        box_x, box_y, box_w, box_h : float
            The row's box.

        Returns
        -------
        bool
            Whether that component's value changed.
        """
        if self._active is None:
            return False
        cell_x, cell_w, cell_h = self._cell_box(self._active, box_x, box_w, box_h)
        return self.components[self._active].drag(x, y, cell_x, box_y, cell_w, cell_h)

    def release(self) -> None:
        """End the gesture."""
        for component in self.components:
            component.release()
        self._active = None


class DragFloatN(_DragScalarN):
    """Two, three or four floats on one row -- a position, a colour, a size."""

    _component = DragFloat


class DragIntN(_DragScalarN):
    """Two, three or four whole numbers on one row."""

    _component = DragInt

    def __init__(
        self,
        label: str = "",
        values: Sequence[int] = (0, 0, 0),
        v_speed: float = 1.0,
        v_min: int = 0,
        v_max: int = 0,
        fmt: str = "%d",
        logarithmic: bool = False,
        wrap: bool = False,
        clamp_on_input: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            values=values,
            v_speed=v_speed,
            v_min=v_min,
            v_max=v_max,
            fmt=fmt,
            logarithmic=logarithmic,
            wrap=wrap,
            clamp_on_input=clamp_on_input,
        )


class _DragRange2:
    """A low and a high that cannot cross.

    The crossing is prevented where the reference prevents it -- in the
    *bounds*, not with an ``if`` after the fact. Before every gesture the low
    half's maximum is set to the high half's current value and the high half's
    minimum to the low half's, so the ordinary drag clamp is what stops them:
    there is no state in which the pair is inverted, not even for the duration
    of one event.

    A half with nowhere left to go (its bounds having met) is marked read-only,
    again as the reference does, so it does not swallow presses.

    Parameters
    ----------
    label : str, optional
        Caption for the pair.
    low, high : float, optional
        The two values. A pair given the wrong way round is corrected.
    v_speed : float, optional
        Units per pixel, shared.
    v_min, v_max : float, optional
        The outer bounds. ``v_min >= v_max`` leaves the pair unbounded except
        by each other.
    fmt : str, optional
        Display format for the low half.
    fmt_max : str, optional
        Display format for the high half; defaults to *fmt*.
    logarithmic, clamp_on_input : bool, optional
        As :class:`_DragScalar`. There is no wrap: a wrapping range would
        cross itself, which is the one thing this control exists to prevent.
    """

    #: Which control each half is. Set by the subclasses.
    _component = DragFloat

    def __init__(
        self,
        label: str = "",
        low: float = 0.0,
        high: float = 1.0,
        v_speed: float = 1.0,
        v_min: float = 0.0,
        v_max: float = 0.0,
        fmt: str = "%.3f",
        fmt_max: str | None = None,
        logarithmic: bool = False,
        clamp_on_input: bool = False,
    ) -> None:
        self.label = label
        self.v_min = v_min
        self.v_max = v_max
        self.low_drag = self._component(
            "", low, v_speed=v_speed, fmt=fmt,
            logarithmic=logarithmic, clamp_on_input=clamp_on_input,
        )
        self.high_drag = self._component(
            "", high, v_speed=v_speed, fmt=fmt_max if fmt_max else fmt,
            logarithmic=logarithmic, clamp_on_input=clamp_on_input,
        )
        if self.low_drag.value > self.high_drag.value:
            self.low_drag.value = self.high_drag.value
        self._label_w = 0.0
        self._active: int | None = None
        self._rebind()

    # ------------------------------------------------------------------- #
    @property
    def low(self) -> float:
        """The lower value."""
        return self.low_drag.value

    @low.setter
    def low(self, value: float) -> None:
        self._rebind()
        self.low_drag.set_value(value)
        self._rebind()

    @property
    def high(self) -> float:
        """The upper value."""
        return self.high_drag.value

    @high.setter
    def high(self, value: float) -> None:
        self._rebind()
        self.high_drag.set_value(value)
        self._rebind()

    @property
    def active(self) -> int | None:
        """Which half the current gesture holds: 0 for low, 1 for high."""
        return self._active

    def _rebind(self) -> None:
        """Point each half's bounds at the other, as the reference does."""
        unbounded = self.v_min >= self.v_max
        low, high = self.low_drag, self.high_drag

        low.v_min = -math.inf if unbounded else self.v_min
        low.v_max = high.value if unbounded else min(self.v_max, high.value)
        low.read_only = low.v_min == low.v_max

        high.v_min = low.value if unbounded else max(self.v_min, low.value)
        high.v_max = math.inf if unbounded else self.v_max
        high.read_only = high.v_min == high.v_max

    # ------------------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the two halves side by side and the caption after them.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        self._rebind()
        self._label_w = (p.text_width(self.label) + _INNER_SPACING) if self.label else 0.0
        body, cell = _split_cells(w, self._label_w, 2)
        self.low_drag.draw(p, x, y, cell, h)
        self.high_drag.draw(p, x + cell + _INNER_SPACING, y, cell, h)
        if self.label:
            p.text(x + body + _INNER_SPACING, y, self._label_w, h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, TEXT)

    def _cell_box(
        self, index: int, box_x: float, box_w: float, box_h: float
    ) -> tuple[float, float, float]:
        """The box one half occupies inside the pair's box.

        Parameters
        ----------
        index : int
            0 for the low half, 1 for the high one.
        box_x, box_w, box_h : float
            The pair's box.

        Returns
        -------
        tuple of float
            ``(x, w, h)`` for that half.
        """
        _body, cell = _split_cells(box_w, self._label_w, 2)
        return (box_x + index * (cell + _INNER_SPACING), cell, box_h)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> int | None:
        """Begin a gesture on whichever half the press landed on.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The pair's box.

        Returns
        -------
        int or None
            0 for the low half, 1 for the high one, ``None`` for neither.
        """
        self._rebind()
        self._active = None
        for index, half in enumerate((self.low_drag, self.high_drag)):
            cell_x, cell_w, cell_h = self._cell_box(index, box_x, box_w, box_h)
            if half.press(x, y, cell_x, box_y, cell_w, cell_h):
                self._active = index
                return index
        return None

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Continue the gesture, with the bounds re-pointed first.

        Parameters
        ----------
        x, y : float
            Where the pointer is now.
        box_x, box_y, box_w, box_h : float
            The pair's box.

        Returns
        -------
        bool
            Whether that half's value changed.
        """
        if self._active is None:
            return False
        self._rebind()
        cell_x, cell_w, cell_h = self._cell_box(self._active, box_x, box_w, box_h)
        half = self.low_drag if self._active == 0 else self.high_drag
        changed = half.drag(x, y, cell_x, box_y, cell_w, cell_h)
        if changed:
            self._rebind()
        return changed

    def release(self) -> None:
        """End the gesture."""
        self.low_drag.release()
        self.high_drag.release()
        self._active = None
        self._rebind()


class DragFloatRange2(_DragRange2):
    """A floating-point low and high that cannot cross."""

    _component = DragFloat


class DragIntRange2(_DragRange2):
    """A whole-number low and high that cannot cross."""

    _component = DragInt

    def __init__(
        self,
        label: str = "",
        low: int = 0,
        high: int = 1,
        v_speed: float = 1.0,
        v_min: int = 0,
        v_max: int = 0,
        fmt: str = "%d",
        fmt_max: str | None = None,
        logarithmic: bool = False,
        clamp_on_input: bool = False,
    ) -> None:
        super().__init__(
            label=label,
            low=low,
            high=high,
            v_speed=v_speed,
            v_min=v_min,
            v_max=v_max,
            fmt=fmt,
            fmt_max=fmt_max,
            logarithmic=logarithmic,
            clamp_on_input=clamp_on_input,
        )
