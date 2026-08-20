"""The slider family, ported from the reference implementation's sliders.

What is here
------------
:mod:`.widgets` already carries a horizontal float slider. This module carries
the rest of the family the reference implementation ships:

* :class:`SliderScalar` -- the general horizontal slider every other one is
  built from, integer or floating point, linear or logarithmic;
* :class:`SliderInt` -- the integer one, whose grab is sized to represent one
  unit and whose ends land on the bounds *exactly*;
* :class:`VSliderFloat` / :class:`VSliderInt` -- the vertical pair, minimum at
  the **bottom**;
* :class:`SliderAngle` -- radians stored, degrees shown;
* :class:`SliderScalarN` and its :class:`SliderFloatN` / :class:`SliderIntN`
  spellings -- two to four components across one box with the caption after
  them.

The part worth reading
----------------------
The reference's ``ScaleRatioFromValueT`` / ``ScaleValueFromRatioT`` pair is
what turns a position on a track into a value and back, and it is where a
slider family is either faithful or merely plausible. Both are ported here as
:func:`ratio_from_value` and :func:`value_from_ratio`, including the awkward
half: a logarithmic slider cannot take ``log(0)``, so the bounds are *fudged*
away from zero by an epsilon derived from the format string's precision, and a
range that **crosses** zero is split into two logarithmic halves with a
dead-zone in the middle so that exactly zero stays reachable. Drop that and a
range of ``-100 .. +100`` either never reaches zero or snaps through it.

Two divergences from the C++ are deliberate and both are about arithmetic that
C tolerates and Python does not: a zero denominator inside the logarithmic
branches yields ``inf``/``nan`` there and a ``ZeroDivisionError`` here, so the
ratios are taken through :func:`_ratio` which answers ``0`` instead; and the
C casts that truncate a floating result into an integer slider's type are
written as :func:`int`, which truncates towards zero the same way.

Geometry, and why it is not just ``value / range``
--------------------------------------------------
The track a value maps onto is **not** the box: the grab has a width, and the
usable travel is the box less that width and less the frame padding, so that
the grab's *centre* -- not its left edge -- tracks the value. An integer
slider additionally sizes its grab so one unit is one grab, which is what makes
a five-step slider read as five steps. Getting this wrong is invisible until
the ends: a slider whose travel is the full box can never put its grab against
the right edge without also reading past its maximum.

Everything draws through the six painter operations and nothing else, and the
palette is :mod:`.style`'s.
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter
from ..style import (
    BORDER,
    DIM,
    FRAME_BG,
    FRAME_BG_ACTIVE,
    SLIDER_GRAB,
    SLIDER_GRAB_ACTIVE,
    TEXT,
    clamp,
    fit_text,
    format_value,
    hit,
    lerp,
)

__all__ = [
    "GRAB_MIN_SIZE",
    "GRAB_PADDING",
    "LOG_SLIDER_DEADZONE",
    "INNER_SPACING",
    "ratio_from_value",
    "value_from_ratio",
    "SliderScalar",
    "SliderInt",
    "VSliderFloat",
    "VSliderInt",
    "SliderAngle",
    "SliderScalarN",
    "SliderFloatN",
    "SliderIntN",
]

#: Smallest grab a slider draws, in pixels. The reference's ``GrabMinSize``.
GRAB_MIN_SIZE = 12.0

#: Space between the frame edge and the grab. The reference's ``grab_padding``,
#: which it flags as "should be part of style" and which is a literal there too.
GRAB_PADDING = 2.0

#: Width in pixels of the dead-zone around zero on a logarithmic slider that
#: crosses it. The reference's ``LogSliderDeadzone``.
LOG_SLIDER_DEADZONE = 4.0

#: Gap between a slider and its caption, and between the components of an N.
#: The reference's ``ItemInnerSpacing.x``.
INNER_SPACING = 4.0

#: The reference's default print formats for the two types this module serves.
_FMT_FLOAT = "%.3f"
_FMT_INT = "%d"

#: A printf conversion, as much of one as this module needs to read.
_SPEC = re.compile(r"%[-+ #0]*\d*(?:\.(\d+))?([diufFeEgG])")

#: ``%.0%`` and friends -- :func:`~.style.format_value`'s percentage spec, which
#: is not a printf conversion and so needs its own precision.
_PERCENT_SPEC = re.compile(r"%\.(\d+)%")


# --------------------------------------------------------------------------
# Format-string arithmetic (the reference's data-type helpers)
# --------------------------------------------------------------------------
def _format_start(fmt: str) -> str:
    """``fmt`` from its conversion onwards, ``%%`` skipped.

    Parameters
    ----------
    fmt : str
        A printf-style format string.

    Returns
    -------
    str
        The tail beginning at the first ``%`` that starts a conversion, or the
        empty string when there is none.
    """
    i = 0
    while i < len(fmt):
        if fmt[i] == "%":
            if i + 1 < len(fmt) and fmt[i + 1] == "%":
                i += 2
                continue
            return fmt[i:]
        i += 1
    return ""


def _parse_precision(fmt: str, default_precision: int = 3) -> int:
    """How many decimals ``fmt`` shows.

    A port of the reference's ``ImParseFormatPrecision``: the digits after the
    dot, with scientific and shortest-form conversions reporting ``-1`` for
    "as much as it takes".

    Parameters
    ----------
    fmt : str
        The format string.
    default_precision : int, optional
        Answer when the format carries no precision of its own.

    Returns
    -------
    int
        The precision, or ``-1`` for the open-ended conversions.
    """
    percent = _PERCENT_SPEC.search(fmt)
    if percent:
        # A percentage spec shows its digits on a value already multiplied by a
        # hundred, so the underlying value carries two more.
        return int(percent.group(1)) + 2
    start = _format_start(fmt)
    if not start.startswith("%"):
        return default_precision
    i = 1
    while i < len(start) and start[i].isdigit():
        i += 1
    precision: int | None = None
    if i < len(start) and start[i] == ".":
        j = i + 1
        digits = ""
        while j < len(start) and start[j].isdigit():
            digits += start[j]
            j += 1
        precision = int(digits) if digits else 0
        if precision > 99:
            precision = default_precision
        i = j
    conv = start[i] if i < len(start) else ""
    if conv in ("e", "E"):
        precision = -1
    elif conv in ("g", "G") and precision is None:
        precision = -1
    return default_precision if precision is None else precision


def _round_to_format(fmt: str, value: float) -> float:
    """``value`` as it would read once written through ``fmt``, back as a number.

    The reference's ``RoundScalarWithFormatT``, and the reason a ``%.2f``
    slider stores ``0.25`` rather than ``0.2500000037``: a value that displays
    rounded but stores unrounded is a value that changes the moment anybody
    types the number they can see.

    Parameters
    ----------
    fmt : str
        The control's format string. One that does not show the value at all
        leaves it untouched, as in the reference.
    value : float
        The number.

    Returns
    -------
    float
        The rounded number.
    """
    percent = _PERCENT_SPEC.search(fmt)
    if percent:
        digits = int(percent.group(1))
        return round(value * 100.0, digits) / 100.0
    match = _SPEC.search(fmt)
    if match is None:
        return float(value)
    try:
        text = match.group(0) % value
    except (TypeError, ValueError):
        return float(value)
    number = re.search(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", text)
    return float(number.group(0)) if number else float(value)


# --------------------------------------------------------------------------
# The scale (the reference's ScaleRatioFromValueT / ScaleValueFromRatioT)
# --------------------------------------------------------------------------
def _ratio(numerator: float, denominator: float) -> float:
    """``numerator / denominator``, answering ``0`` where C would answer ``nan``.

    The logarithmic branches divide by ``log(a / epsilon)``, which is zero when
    a bound sits exactly on the epsilon the bounds were fudged to. C produces
    an infinity there and carries on; Python raises, which would take the frame
    down over a slider whose minimum happens to be ``-0.001``.

    Parameters
    ----------
    numerator, denominator : float
        The division.

    Returns
    -------
    float
        The quotient, or ``0.0``.
    """
    return numerator / denominator if denominator else 0.0


def _fudge(bound: float, epsilon: float) -> float:
    """A bound pushed away from zero so its logarithm exists.

    Parameters
    ----------
    bound : float
        The bound.
    epsilon : float
        How far from zero is close enough to be a problem.

    Returns
    -------
    float
        The bound, or the epsilon carrying the bound's sign.
    """
    if abs(bound) < epsilon:
        return -epsilon if bound < 0.0 else epsilon
    return bound


def ratio_from_value(
    value: float,
    v_min: float,
    v_max: float,
    log_epsilon: float = 0.0,
    deadzone: float = 0.0,
) -> float:
    """Where ``value`` sits along the track, as ``0..1``.

    A port of the reference's ``ScaleRatioFromValueT``. ``log_epsilon`` above
    zero *is* the reference's ``is_logarithmic``: it both selects the branch
    and says how near zero the bounds may be taken.

    Parameters
    ----------
    value : float
        The value; clamped into the range before it is scaled.
    v_min, v_max : float
        The bounds. ``v_min > v_max`` is a backwards slider and is supported.
    log_epsilon : float, optional
        Zero for a linear slider; otherwise the distance from zero the bounds
        are fudged to.
    deadzone : float, optional
        Half-width, in track fractions, of the region around zero that reads as
        exactly zero. Only used when the range crosses zero.

    Returns
    -------
    float
        The parametric position, ``0`` at ``v_min`` and ``1`` at ``v_max``.
    """
    if v_min == v_max:
        return 0.0
    low, high = (v_min, v_max) if v_min < v_max else (v_max, v_min)
    v_clamped = clamp(float(value), float(low), float(high))
    if log_epsilon <= 0.0:
        return float(v_clamped - v_min) / float(v_max - v_min)

    flipped = v_max < v_min
    a, b = (float(high), float(low)) if flipped else (float(low), float(high))
    a_fudged = _fudge(a, log_epsilon)
    b_fudged = _fudge(b, log_epsilon)
    # Ranges of the form (-100 .. 0) must become (-100 .. -epsilon), not
    # (-100 .. +epsilon) -- otherwise the top of the track crosses zero.
    if a == 0.0 and b < 0.0:
        a_fudged = -log_epsilon
    elif b == 0.0 and a < 0.0:
        b_fudged = -log_epsilon

    if v_clamped <= a_fudged:
        result = 0.0
    elif v_clamped >= b_fudged:
        result = 1.0
    elif a * b < 0.0:
        zero_centre = -a / (b - a)
        snap_l = zero_centre - deadzone
        snap_r = zero_centre + deadzone
        if value == 0.0:
            result = zero_centre
        elif value < 0.0:
            result = (1.0 - _ratio(math.log(-v_clamped / log_epsilon),
                                   math.log(-a_fudged / log_epsilon))) * snap_l
        else:
            result = snap_r + _ratio(math.log(v_clamped / log_epsilon),
                                     math.log(b_fudged / log_epsilon)) * (1.0 - snap_r)
    elif a < 0.0 or b < 0.0:
        result = 1.0 - _ratio(math.log(-v_clamped / -b_fudged),
                              math.log(-a_fudged / -b_fudged))
    else:
        result = _ratio(math.log(v_clamped / a_fudged), math.log(b_fudged / a_fudged))
    return (1.0 - result) if flipped else result


def value_from_ratio(
    t: float,
    v_min: float,
    v_max: float,
    log_epsilon: float = 0.0,
    deadzone: float = 0.0,
    is_int: bool = False,
) -> float:
    """The value ``t`` of the way along the track.

    A port of the reference's ``ScaleValueFromRatioT``. The extents are
    special-cased before any scaling, exactly as the reference does and for the
    reason it gives: the logarithmic fudging is otherwise "mathematically
    correct" and yet leaves a slider pushed fully left short of its minimum.
    That special case is also what makes :class:`SliderInt` land on both
    endpoints.

    Parameters
    ----------
    t : float
        Parametric position, ``0..1``.
    v_min, v_max : float
        The bounds.
    log_epsilon : float, optional
        Zero for a linear slider; see :func:`ratio_from_value`.
    deadzone : float, optional
        Half-width of the zero dead-zone, in track fractions.
    is_int : bool, optional
        Whether the slider steps in whole numbers. The rounding is the
        reference's: the click position is made to match the grab box by
        rounding *up* through a half-unit bias.

    Returns
    -------
    float or int
        The value; an :class:`int` when ``is_int``.
    """
    if t <= 0.0 or v_min == v_max:
        return int(v_min) if is_int else float(v_min)
    if t >= 1.0:
        return int(v_max) if is_int else float(v_max)

    if log_epsilon > 0.0:
        a_fudged = _fudge(float(v_min), log_epsilon)
        b_fudged = _fudge(float(v_max), log_epsilon)
        flipped = v_max < v_min
        if flipped:
            a_fudged, b_fudged = b_fudged, a_fudged
        if v_max == 0.0 and v_min < 0.0:
            b_fudged = -log_epsilon
        t_flipped = (1.0 - t) if flipped else t

        if v_min * v_max < 0.0:
            zero_centre = -min(v_min, v_max) / abs(float(v_max) - float(v_min))
            snap_l = zero_centre - deadzone
            snap_r = zero_centre + deadzone
            if snap_l <= t_flipped <= snap_r:
                result = 0.0
            elif t_flipped < zero_centre:
                result = -(log_epsilon * pow(-a_fudged / log_epsilon,
                                             1.0 - _ratio(t_flipped, snap_l)))
            else:
                result = log_epsilon * pow(b_fudged / log_epsilon,
                                           _ratio(t_flipped - snap_r, 1.0 - snap_r))
        elif v_min < 0.0 or v_max < 0.0:
            result = -(-b_fudged * pow(-a_fudged / -b_fudged, 1.0 - t_flipped))
        else:
            result = a_fudged * pow(b_fudged / a_fudged, t_flipped)
        return int(result) if is_int else float(result)

    if not is_int:
        return lerp(float(v_min), float(v_max), t)
    offset = (float(v_max) - float(v_min)) * t
    return int(v_min) + int(offset + (-0.5 if v_min > v_max else 0.5))


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------
class SliderScalar:
    """A slider over one number: the family's general case.

    Every other control here is this one with something fixed -- the type, the
    axis, a unit conversion, or a row of them.

    Parameters
    ----------
    label : str
        Caption, drawn *after* the frame as the reference draws it. An empty
        caption gives the whole box to the track.
    v_min, v_max : float
        Inclusive bounds. ``v_min > v_max`` runs the slider backwards.
    value : float, optional
        Initial value, clamped into the range.
    fmt : str, optional
        How the value is written in the middle of the track. Defaults to the
        reference's print format for the type (``"%.3f"`` or ``"%d"``), and it
        is also what decides a logarithmic slider's precision near zero.
    is_int : bool, optional
        Whether the value steps in whole numbers.
    logarithmic : bool, optional
        The reference's ``ImGuiSliderFlags_Logarithmic``.
    round_to_format : bool, optional
        Whether a floating value is rounded to the precision it is shown at.
        The reference's ``ImGuiSliderFlags_NoRoundToFormat``, inverted -- a
        double negative reads badly at a call site.
    vertical : bool, optional
        Whether the track runs up the box. The minimum is at the **bottom**,
        which is the reference's convention and is not the direction the
        arithmetic falls out in: the position is measured downwards and the
        fraction is flipped.

    Notes
    -----
    ``press`` needs the same frame the last ``draw`` used, and only ``draw``
    holds a painter to measure the caption with, so the room the caption takes
    -- width beside a horizontal track, height below a vertical one -- is
    recorded there. Before the first draw the whole box is the frame, which is
    what a caller who never draws would expect anyway.
    """

    def __init__(
        self,
        label: str,
        v_min: float,
        v_max: float,
        value: float = 0.0,
        fmt: str | None = None,
        is_int: bool = False,
        logarithmic: bool = False,
        round_to_format: bool = True,
        vertical: bool = False,
    ) -> None:
        self.label = label
        self.is_int = bool(is_int)
        self.v_min = int(v_min) if self.is_int else float(v_min)
        self.v_max = int(v_max) if self.is_int else float(v_max)
        self.fmt = fmt if fmt is not None else (_FMT_INT if self.is_int else _FMT_FLOAT)
        self.logarithmic = bool(logarithmic)
        self.round_to_format = bool(round_to_format)
        self.vertical = bool(vertical)
        self.value = self._coerce(value)
        self._held = False
        self._grab_offset = 0.0
        self._label_w = 0.0
        self._label_h = 0.0
        self._usable_sz = 0.0

    # -- the value ------------------------------------------------------- #
    def _coerce(self, value: float) -> float:
        """``value`` as this slider's type, inside this slider's bounds."""
        low = min(self.v_min, self.v_max)
        high = max(self.v_min, self.v_max)
        held = clamp(float(value), float(low), float(high))
        return int(round(held)) if self.is_int else float(held)

    def set_value(self, value: float) -> float:
        """Set the value, clamped to the bounds.

        Parameters
        ----------
        value : float
            The new value.

        Returns
        -------
        float
            The value actually stored.
        """
        self.value = self._coerce(value)
        return self.value

    def step(self, delta: float) -> float:
        """Move the value by ``delta``, clamped to the bounds.

        Parameters
        ----------
        delta : float
            How far to move.

        Returns
        -------
        float
            The new value.
        """
        return self.set_value(self.value + delta)

    @property
    def log_epsilon(self) -> float:
        """How near zero a logarithmic slider's bounds may be taken.

        Zero for a linear slider, which is also how the scale functions are
        told which branch to run.
        """
        if not self.logarithmic:
            return 0.0
        precision = 1 if self.is_int else _parse_precision(self.fmt, 3)
        return pow(0.1, float(precision))

    @property
    def deadzone(self) -> float:
        """Half-width of the zero dead-zone, in fractions of the usable track.

        Zero until the control has been drawn or pressed once: the reference
        derives it from the track length, and this one has not got one yet.
        """
        if not self.logarithmic or self._usable_sz <= 0.0:
            return 0.0
        return (LOG_SLIDER_DEADZONE * 0.5) / max(self._usable_sz, 1.0)

    @property
    def fraction(self) -> float:
        """Where the value sits along the track, ``0..1``."""
        return ratio_from_value(self.value, self.v_min, self.v_max,
                                self.log_epsilon, self.deadzone)

    def set_fraction(self, fraction: float) -> float:
        """Set the value from a ``0..1`` position along the track.

        Parameters
        ----------
        fraction : float
            The position; clamped.

        Returns
        -------
        float
            The resulting value.
        """
        t = clamp(float(fraction), 0.0, 1.0)
        raw = value_from_ratio(t, self.v_min, self.v_max, self.log_epsilon,
                               self.deadzone, self.is_int)
        if not self.is_int and self.round_to_format:
            raw = _round_to_format(self.fmt, raw)
        self.value = self._coerce(raw)
        return self.value

    @property
    def text(self) -> str:
        """The value as it is written on the track."""
        return format_value(self.fmt, self.value)

    # -- the geometry ---------------------------------------------------- #
    def _metrics(self, box_len: float) -> tuple[float, float]:
        """Grab size and usable travel for a track of ``box_len`` pixels.

        Parameters
        ----------
        box_len : float
            The frame's length along the slider's axis.

        Returns
        -------
        tuple of float
            ``(grab_sz, usable_sz)``, both never negative.
        """
        slider_sz = max(box_len - GRAB_PADDING * 2.0, 0.0)
        grab_sz = GRAB_MIN_SIZE
        v_range = abs(float(self.v_max) - float(self.v_min))
        if self.is_int:
            # One unit, one grab -- which is what makes a five-step slider
            # read as five steps rather than as a continuous one.
            grab_sz = max(slider_sz / (v_range + 1.0), GRAB_MIN_SIZE)
        grab_sz = min(grab_sz, slider_sz)
        return grab_sz, max(slider_sz - grab_sz, 0.0)

    def _frame(
        self,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> tuple[float, float, float, float]:
        """The track's own box inside the box the caller gave.

        Parameters
        ----------
        box_x, box_y, box_w, box_h : float
            The whole control, caption included.

        Returns
        -------
        tuple of float
            ``(x, y, w, h)`` of the frame.
        """
        if self.vertical:
            return (box_x, box_y, box_w, max(box_h - self._label_h, 1.0))
        if self._label_w <= 0.0:
            return (box_x, box_y, box_w, box_h)
        return (box_x, box_y, max(box_w - self._label_w, 1.0), box_h)

    def _track(self, frame: tuple[float, float, float, float]) -> tuple[float, float, float]:
        """Where the grab's centre may travel, along the slider's axis.

        Parameters
        ----------
        frame : tuple of float
            ``(x, y, w, h)`` of the frame.

        Returns
        -------
        tuple of float
            ``(pos_min, pos_max, grab_sz)``.
        """
        f_x, f_y, f_w, f_h = frame
        start = f_y if self.vertical else f_x
        length = f_h if self.vertical else f_w
        grab_sz, _usable = self._metrics(length)
        self._usable_sz = _usable
        return (start + GRAB_PADDING + grab_sz * 0.5,
                start + length - GRAB_PADDING - grab_sz * 0.5,
                grab_sz)

    def _grab_t(self) -> float:
        """The grab's position along the drawn axis, ``0`` at the box's start.

        Vertical sliders run bottom-to-top, so the value's fraction and the
        grab's position down the box are opposites.
        """
        t = self.fraction
        return (1.0 - t) if self.vertical else t

    # -- drawing --------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, the grab, the value and the caption.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box, caption included.
        """
        self._label_w = 0.0
        self._label_h = 0.0
        if self.label:
            if self.vertical:
                # A caption strip below the track, rather than the caption the
                # reference puts beside it: the box a vertical slider is given
                # is narrow, and a caption drawn *over* the track is unreadable
                # exactly when the grab is at the end it sits at.
                self._label_h = p.line_height() + GRAB_PADDING
            else:
                self._label_w = min(p.text_width(self.label) + INNER_SPACING, w * 0.5)
        frame = self._frame(x, y, w, h)
        f_x, f_y, f_w, f_h = frame
        p.stroke_rect(f_x, f_y, f_w, f_h, BORDER,
                      FRAME_BG_ACTIVE if self._held else FRAME_BG)

        pos_min, pos_max, grab_sz = self._track(frame)
        grab_pos = lerp(pos_min, pos_max, self._grab_t())
        grab_colour = SLIDER_GRAB_ACTIVE if self._held else SLIDER_GRAB
        if grab_sz > 0.0:
            if self.vertical:
                p.fill_rect(f_x + GRAB_PADDING, grab_pos - grab_sz * 0.5,
                            max(f_w - GRAB_PADDING * 2.0, 1.0), grab_sz, grab_colour)
            else:
                p.fill_rect(grab_pos - grab_sz * 0.5, f_y + GRAB_PADDING,
                            grab_sz, max(f_h - GRAB_PADDING * 2.0, 1.0), grab_colour)

        p.push_clip(f_x, f_y, f_w, f_h)
        if self.vertical:
            # The value rides at the top of the track, over the frame padding,
            # as the reference draws it.
            p.text(f_x, f_y + GRAB_PADDING, f_w, p.line_height(),
                   ALIGN_CENTER, fit_text(p, self.text, f_w), TEXT)
        else:
            p.text(f_x, f_y, f_w, f_h, ALIGN_CENTER, fit_text(p, self.text, f_w), TEXT)
        p.pop_clip()

        if self.vertical and self._label_h > 0.0:
            p.text(f_x, f_y + f_h, f_w, self._label_h,
                   ALIGN_CENTER, fit_text(p, self.label, f_w), DIM)
        elif self._label_w > 0.0:
            room = max(self._label_w - INNER_SPACING, 1.0)
            p.text(f_x + f_w + INNER_SPACING, y, room, h,
                   ALIGN_VCENTER | ALIGN_LEFT, fit_text(p, self.label, room), TEXT)

    # -- interaction ----------------------------------------------------- #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Take a mouse press.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the control was drawn into.

        Returns
        -------
        bool
            Whether the press hit the track.
        """
        frame = self._frame(box_x, box_y, box_w, box_h)
        if not hit(x, y, *frame):
            self._held = False
            return False
        self._held = True
        pos = y if self.vertical else x
        pos_min, pos_max, grab_sz = self._track(frame)
        grab_pos = lerp(pos_min, pos_max, self._grab_t())
        near_grab = (grab_pos - grab_sz * 0.5 - 1.0) <= pos <= (grab_pos + grab_sz * 0.5 + 1.0)
        # An integer slider snaps anyway, so keeping an offset would only let
        # the grab sit a fraction of a step away from where it is drawn.
        self._grab_offset = (pos - grab_pos) if (near_grab and not self.is_int) else 0.0
        self._apply(pos, frame)
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
        """Continue a drag.

        Parameters
        ----------
        x, y : float
            Where the pointer is now; not required to be inside the box.
        box_x, box_y, box_w, box_h : float
            The box the control was drawn into.

        Returns
        -------
        bool
            Whether the value changed, which is what the reference returns.
        """
        if not self._held:
            return False
        before = self.value
        self._apply(y if self.vertical else x, self._frame(box_x, box_y, box_w, box_h))
        return self.value != before

    def release(self) -> None:
        """Let go of the grab."""
        self._held = False
        self._grab_offset = 0.0

    def _apply(self, pos: float, frame: tuple[float, float, float, float]) -> None:
        """Put the value where a pointer at ``pos`` says it should be.

        Parameters
        ----------
        pos : float
            The pointer, along the slider's axis.
        frame : tuple of float
            ``(x, y, w, h)`` of the frame.
        """
        pos_min, pos_max, _grab = self._track(frame)
        usable = max(pos_max - pos_min, 0.0)
        t = clamp((pos - self._grab_offset - pos_min) / usable, 0.0, 1.0) if usable > 0.0 else 0.0
        if self.vertical:
            t = 1.0 - t
        self.set_fraction(t)


class SliderInt(SliderScalar):
    """A slider over whole numbers.

    The endpoints are exact: :func:`value_from_ratio` returns the bounds
    themselves at ``t <= 0`` and ``t >= 1`` rather than scaling into them, so a
    slider pushed fully left reads ``v_min`` and not ``v_min`` plus whatever
    the rounding left behind. Between them the grab is one unit wide, so it
    steps rather than slides.

    Parameters
    ----------
    label : str
        Caption.
    v_min, v_max : int
        Inclusive bounds.
    value : int, optional
        Initial value.
    fmt : str, optional
        Display format; defaults to ``"%d"``.
    logarithmic : bool, optional
        Whether the track is logarithmic.
    """

    def __init__(
        self,
        label: str,
        v_min: int,
        v_max: int,
        value: int = 0,
        fmt: str | None = None,
        logarithmic: bool = False,
    ) -> None:
        super().__init__(label, v_min, v_max, value, fmt, is_int=True,
                         logarithmic=logarithmic)


class VSliderFloat(SliderScalar):
    """A vertical floating-point slider, minimum at the bottom.

    Parameters
    ----------
    label : str
        Caption, drawn in a strip below the track rather than beside it: the
        box a vertical slider is given is narrow and tall, and a caption to its
        right would be most of the control.
    v_min, v_max : float
        Inclusive bounds; ``v_min`` sits at the bottom edge.
    value : float, optional
        Initial value.
    fmt : str, optional
        Display format.
    logarithmic : bool, optional
        Whether the track is logarithmic.
    """

    def __init__(
        self,
        label: str,
        v_min: float,
        v_max: float,
        value: float = 0.0,
        fmt: str | None = None,
        logarithmic: bool = False,
    ) -> None:
        super().__init__(label, v_min, v_max, value, fmt, is_int=False,
                         logarithmic=logarithmic, vertical=True)


class VSliderInt(SliderScalar):
    """A vertical whole-number slider, minimum at the bottom.

    Parameters
    ----------
    label : str
        Caption, drawn in a strip below the track.
    v_min, v_max : int
        Inclusive bounds; ``v_min`` sits at the bottom edge.
    value : int, optional
        Initial value.
    fmt : str, optional
        Display format.
    logarithmic : bool, optional
        Whether the track is logarithmic.
    """

    def __init__(
        self,
        label: str,
        v_min: int,
        v_max: int,
        value: int = 0,
        fmt: str | None = None,
        logarithmic: bool = False,
    ) -> None:
        super().__init__(label, v_min, v_max, value, fmt, is_int=True,
                         logarithmic=logarithmic, vertical=True)


class SliderAngle(SliderScalar):
    """An angle: radians stored, degrees shown.

    The reference's ``SliderAngle`` keeps the caller's number in radians and
    slides over degrees, defaulting to a full turn either way. Storing the
    degrees and converting on the way out -- rather than the reverse -- keeps
    every one of the base class's arithmetic paths working on the number that
    is actually displayed, which is the one the format string describes.

    Parameters
    ----------
    label : str
        Caption.
    radians : float, optional
        Initial angle, in radians.
    v_degrees_min, v_degrees_max : float, optional
        Bounds in degrees. The reference's defaults are a full turn each way.
    fmt : str, optional
        Display format; the reference's default is ``"%.0f deg"``.
    """

    def __init__(
        self,
        label: str,
        radians: float = 0.0,
        v_degrees_min: float = -360.0,
        v_degrees_max: float = +360.0,
        fmt: str = "%.0f deg",
    ) -> None:
        super().__init__(label, v_degrees_min, v_degrees_max,
                         math.degrees(radians), fmt)

    @property
    def radians(self) -> float:
        """The angle in radians."""
        return math.radians(self.value)

    @radians.setter
    def radians(self, value: float) -> None:
        """Set the angle from radians.

        Parameters
        ----------
        value : float
            The angle, in radians.
        """
        self.set_value(math.degrees(value))

    @property
    def degrees(self) -> float:
        """The angle in degrees, which is what the slider slides over."""
        return self.value


class SliderScalarN:
    """Two to four sliders across one box, with the caption after them.

    A port of the reference's ``SliderScalarN``, which is how it spells
    ``SliderFloat3`` and friends: the width is split between the components and
    the caption follows the last of them.

    Each component drags on its own, so the press remembers *which* one is
    held; without that, a drag that wanders out of its own cell would start
    steering whichever component it wandered into.

    Parameters
    ----------
    label : str
        Caption, drawn after the last component.
    values : sequence of float
        The components. Two to four of them, in the reference's spirit; more
        are accepted and simply laid out.
    v_min, v_max : float
        Bounds shared by every component, as the reference shares them.
    fmt : str, optional
        Display format for every component.
    is_int : bool, optional
        Whether the components step in whole numbers.
    logarithmic : bool, optional
        Whether the tracks are logarithmic.
    """

    def __init__(
        self,
        label: str,
        values: Sequence[float],
        v_min: float,
        v_max: float,
        fmt: str | None = None,
        is_int: bool = False,
        logarithmic: bool = False,
    ) -> None:
        self.label = label
        self.components: list[SliderScalar] = [
            SliderScalar("", v_min, v_max, value, fmt, is_int=is_int,
                         logarithmic=logarithmic)
            for value in values
        ]
        self._active: int | None = None
        self._label_w = 0.0

    # -- the values ------------------------------------------------------ #
    @property
    def values(self) -> list[float]:
        """The components' values, in order."""
        return [one.value for one in self.components]

    def set_values(self, values: Sequence[float]) -> list[float]:
        """Set every component, each clamped to the shared bounds.

        Parameters
        ----------
        values : sequence of float
            As many values as there are components; extras are ignored.

        Returns
        -------
        list of float
            The values actually stored.
        """
        for slider, value in zip(self.components, values):
            slider.set_value(value)
        return self.values

    @property
    def held(self) -> int | None:
        """Index of the component currently being dragged, or ``None``."""
        return self._active

    # -- the geometry ---------------------------------------------------- #
    def _cells(self, box_x: float, box_w: float) -> list[tuple[float, float]]:
        """Each component's ``(x, width)`` across the row.

        The caption's width comes from the last :meth:`draw`, because that is
        the only call that holds a painter to measure it with.

        Parameters
        ----------
        box_x, box_w : float
            The row.

        Returns
        -------
        list of tuple of float
            One ``(x, width)`` per component.
        """
        count = len(self.components)
        if count == 0:
            return []
        row_w = max(box_w - self._label_w, 1.0)
        cell = max((row_w - INNER_SPACING * (count - 1)) / count, 1.0)
        return [(box_x + i * (cell + INNER_SPACING), cell) for i in range(count)]

    # -- drawing --------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint every component and then the caption.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box, caption included.
        """
        self._label_w = (min(p.text_width(self.label) + INNER_SPACING, w * 0.5)
                         if self.label else 0.0)
        cells = self._cells(x, w)
        for slider, (cell_x, cell_w) in zip(self.components, cells):
            slider.draw(p, cell_x, y, cell_w, h)
        if self.label and cells:
            last_x, last_w = cells[-1]
            left = last_x + last_w + INNER_SPACING
            room = max(x + w - left, 1.0)
            p.text(left, y, room, h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, room), TEXT)

    # -- interaction ----------------------------------------------------- #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> int | None:
        """Take a mouse press.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the row was drawn into.

        Returns
        -------
        int or None
            The component the press grabbed, or ``None``.
        """
        self._active = None
        for index, (cell_x, cell_w) in enumerate(self._cells(box_x, box_w)):
            slider = self.components[index]
            if slider.press(x, y, cell_x, box_y, cell_w, box_h):
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
        """Continue the held component's drag, and only that one's.

        Parameters
        ----------
        x, y : float
            Where the pointer is now.
        box_x, box_y, box_w, box_h : float
            The box the row was drawn into.

        Returns
        -------
        bool
            Whether the held component's value changed.
        """
        if self._active is None:
            return False
        cells = self._cells(box_x, box_w)
        if self._active >= len(cells):
            return False
        cell_x, cell_w = cells[self._active]
        return self.components[self._active].drag(x, y, cell_x, box_y, cell_w, box_h)

    def release(self) -> None:
        """Let go of whichever component was held."""
        for slider in self.components:
            slider.release()
        self._active = None


class SliderFloatN(SliderScalarN):
    """The floating-point row: the reference's ``SliderFloat2/3/4``.

    Parameters
    ----------
    label : str
        Caption, drawn after the last component.
    values : sequence of float
        The components.
    v_min, v_max : float
        Bounds shared by every component.
    fmt : str, optional
        Display format.
    logarithmic : bool, optional
        Whether the tracks are logarithmic.
    """

    def __init__(
        self,
        label: str,
        values: Sequence[float],
        v_min: float,
        v_max: float,
        fmt: str | None = None,
        logarithmic: bool = False,
    ) -> None:
        super().__init__(label, values, v_min, v_max, fmt, is_int=False,
                         logarithmic=logarithmic)


class SliderIntN(SliderScalarN):
    """The whole-number row: the reference's ``SliderInt2/3/4``.

    Parameters
    ----------
    label : str
        Caption, drawn after the last component.
    values : sequence of int
        The components.
    v_min, v_max : int
        Bounds shared by every component.
    fmt : str, optional
        Display format.
    logarithmic : bool, optional
        Whether the tracks are logarithmic.
    """

    def __init__(
        self,
        label: str,
        values: Sequence[int],
        v_min: int,
        v_max: int,
        fmt: str | None = None,
        logarithmic: bool = False,
    ) -> None:
        super().__init__(label, values, v_min, v_max, fmt, is_int=True,
                         logarithmic=logarithmic)
