"""Instrument-panel controls: a rotary dial and a seven-segment number display.

Qt's ``QDial`` and ``QLCDNumber``. Neither is in Dear ImGui, and both are what a
port of an acquisition or hardware-control panel brings along: a knob for a
gain or a laser power that the eye reads by its angle, and a readout of a count
rate or a temperature that is legible across the lab. Spelled the ``im`` way::

    changed, gain = im.dial("Gain", gain, 0.0, 10.0)
    im.lcd_number(count_rate, digits=7, fmt="%.0f")

The dial
--------
A knob over a 300 degree arc (the gap at the bottom, as Qt draws it), its value
in the middle. The pointer sets the value by **angle** while held -- the knob
turns to where the pointer is, which is how a dial on screen is read -- the
wheel steps it, and with the keyboard focus the arrows step it (Left / Down
down, Right / Up up), Page Up / Page Down step ten times as far, and Home / End
go to the ends. ``wrapping=True`` makes it a full circle that runs on past the
ends, for an angle or a phase. *step* defaults to a hundredth of the range,
rounded for an integer dial; *notches* draws that many tick marks round the arc.

The display
-----------
Digits drawn as segments, not as a font, so they are the same on every painter
and scale to any height. ``0-9``, ``A-F`` (a hexadecimal readout), ``-``, a
space, ``E``, ``r``, ``o``, ``H``, ``L``, ``P``, ``U``, ``°`` and the decimal
point (which takes no cell of its own, as on a real display) are drawn; any
other character is a blank. A value too long for *digits* is an overflow:
``lcd_number`` returns ``True`` and shows ``E`` in every cell, which is what a
readout that cannot show the number should do rather than show part of it.
"""
from __future__ import annotations

import math

from .. import im_widgets as _w
from .. import style as _style
from ..events import SHIFT_MODIFIER
from ..im_core import ButtonFlags, Col, ConfigFlags, ItemFlags, get_current_context
from ..keys import (
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RIGHT,
    KEY_UP,
)

__all__ = ["SEGMENTS", "dial", "lcd_number", "lcd_segments"]

#: The arc a non-wrapping dial sweeps, centred on the top, in degrees.
_ARC = 300.0


def _take_keys(ctx, wanted):
    from .calendar import (
        _take_keys as take,
    )

    return take(ctx, wanted)


def dial(label: str, value: float, v_min: float, v_max: float, step: float | None = None,
         fmt: str | None = None, size: float | None = None, wrapping: bool = False,
         notches: int = 0) -> tuple[bool, float]:
    """A rotary knob (``QDial``): ``(changed, value)``.

    Parameters
    ----------
    label : str
        Caption (drawn under the knob) and id.
    value, v_min, v_max : float or int
        An ``int`` value with ``int`` bounds makes an integer dial.
    step : float, optional
        One wheel notch or arrow key; a hundredth of the range by default.
    fmt : str, optional
        ``%``-format of the value in the middle (``"%.1f"``); ``"%d"`` for an
        integer dial, ``"%.3g"`` otherwise. ``""`` shows no value.
    size : float, optional
        The knob's diameter; three frame heights by default.
    wrapping : bool
        A full circle: past the maximum is the minimum again.
    notches : int
        Tick marks round the arc (0 for none).
    """
    ctx = get_current_context()
    integral = isinstance(value, int) and isinstance(v_min, int) and isinstance(v_max, int) \
        and not isinstance(value, bool)
    lo, hi = (float(v_min), float(v_max)) if v_min <= v_max else (float(v_max), float(v_min))
    span = hi - lo
    if step is None:
        step = max(1.0, round(span / 100.0)) if integral else (span / 100.0 or 1.0)
    step = float(step)
    if fmt is None:
        fmt = "%d" if integral else "%.3g"
    diameter = float(size) if size else 3.0 * _w._frame_height(ctx)
    shown = _w._visible_label(label)
    line = ctx.p.line_height()
    label_h = line + ctx.style.item_inner_spacing[1] if shown else 0.0
    width = max(diameter, ctx.draw.calc_text_size(shown)[0] if shown else 0.0)
    box = ctx.layout.row(height=diameter + label_h, width=width)
    knob = (box[0] + (width - diameter) / 2.0, box[1], diameter, diameter)
    item_id = ctx.get_id(label)
    hovered, held, _pressed = ctx.button_behavior(knob, item_id, ButtonFlags.NO_NAV_ACTIVATE)
    cx, cy = knob[0] + diameter / 2.0, knob[1] + diameter / 2.0
    radius = diameter / 2.0 - 1.0
    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    original = float(value)
    current = min(max(float(value), lo), hi)
    sweep = 360.0 if wrapping else _ARC

    def snap(number: float) -> float:
        if wrapping and span > 0:
            number = lo + (number - lo) % span if number not in (lo, hi) else number
        number = min(max(number, lo), hi)
        return float(round(number)) if integral else number

    if held and span > 0 and not disabled:
        if hovered or ctx.io.mouse_clicked[0]:
            _w.set_nav_id(item_id)
        mx, my = ctx.io.mouse_pos
        # Degrees clockwise from the top, -180..180.
        angle = math.degrees(math.atan2(mx - cx, cy - my))
        if not wrapping:
            angle = min(max(angle, -sweep / 2.0), sweep / 2.0)
            current = snap(lo + (angle + sweep / 2.0) / sweep * span)
        else:
            current = snap(lo + (angle % 360.0) / 360.0 * span)
    if hovered and ctx.io.mouse_wheel and not disabled:
        current = snap(current + (1 if ctx.io.mouse_wheel > 0 else -1) * step)
        ctx.io.mouse_wheel = 0.0
        ctx.request_frame()
    if (not disabled and ctx.is_nav_focused(item_id)
            and ctx.io.config_flags & ConfigFlags.NAV_ENABLE_KEYBOARD):
        for key, mods in _take_keys(ctx, (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_PAGE_UP,
                                          KEY_PAGE_DOWN, KEY_HOME, KEY_END)):
            factor = 10.0 if (key in (KEY_PAGE_UP, KEY_PAGE_DOWN) or mods & SHIFT_MODIFIER) else 1.0
            if key in (KEY_RIGHT, KEY_UP, KEY_PAGE_UP):
                current = snap(current + factor * step)
            elif key in (KEY_LEFT, KEY_DOWN, KEY_PAGE_DOWN):
                current = snap(current - factor * step)
            elif key == KEY_HOME:
                current = lo
            elif key == KEY_END:
                current = hi

    # -- paint ---------------------------------------------------------------- #
    face = _w._col(Col.FRAME_BG_ACTIVE if held else (Col.FRAME_BG_HOVERED if hovered else Col.FRAME_BG))
    ctx.draw.add_circle_filled((cx, cy), radius, face, 48)
    ctx.draw.add_circle((cx, cy), radius, _w._col(Col.BORDER), 48, 1.0)
    start = -sweep / 2.0

    def at(degrees: float, r: float) -> tuple[float, float]:
        rad = math.radians(degrees)
        return (cx + r * math.sin(rad), cy - r * math.cos(rad))

    track_r = radius - max(2.0, diameter * 0.07)
    fraction = (current - lo) / span if span > 0 else 0.0
    segments = 40
    track = [at(start + sweep * i / segments, track_r) for i in range(segments + 1)]
    ctx.draw.add_polyline(track, _w._col(Col.SCROLLBAR_GRAB), 0, max(2.0, diameter * 0.06))
    filled = [at(start + sweep * fraction * i / segments, track_r) for i in range(segments + 1)]
    if fraction > 0:
        ctx.draw.add_polyline(filled, _w._col(Col.SLIDER_GRAB_ACTIVE if held else Col.SLIDER_GRAB), 0,
                              max(2.0, diameter * 0.06))
    for index in range(max(0, int(notches))):
        t = index / max(1, notches - (0 if wrapping else 1))
        ctx.draw.add_line(at(start + sweep * t, radius - 1.0), at(start + sweep * t, radius - diameter * 0.05),
                          _w._col(Col.TEXT_DISABLED), 1.0)
    pointer = start + sweep * fraction
    ctx.draw.add_line(at(pointer, diameter * 0.12), at(pointer, track_r - diameter * 0.04),
                      _w._col(Col.TEXT), max(1.5, diameter * 0.04))
    if fmt:
        text = _style.format_value(fmt, current) if "%" in fmt else fmt
        tw, _th = ctx.draw.calc_text_size(text)
        if tw < diameter * 0.8:
            ctx.draw.add_text((cx - tw / 2.0, cy + diameter * 0.12), _w._col(Col.TEXT), text)
    if shown:
        lw, _lh = ctx.draw.calc_text_size(shown)
        ctx.draw.add_text((box[0] + (width - lw) / 2.0, knob[1] + diameter + ctx.style.item_inner_spacing[1]),
                          _w._col(Col.TEXT), shown)
    _w._nav_ring(ctx, knob, item_id)
    ctx._last_item, ctx._last_id = knob, item_id
    result = int(current) if integral else current
    return (current != original and not disabled), result


# --------------------------------------------------------------------------- #
# The seven-segment display
# --------------------------------------------------------------------------- #
#: Segments lit per character: a (top), b (top right), c (bottom right), d (bottom),
#: e (bottom left), f (top left), g (middle).
SEGMENTS: dict[str, str] = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg",
    "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg", "a": "abcefg", "b": "cdefg",
    "c": "adef", "d": "bcdeg", "e": "adefg", "f": "aefg", "-": "g", " ": "", "r": "eg",
    "o": "cdeg", "h": "bcefg", "l": "def", "p": "abefg", "u": "bcdef", "°": "abfg",
    "_": "d", "=": "dg",
}


def lcd_segments(text: str) -> list[tuple[str, bool]]:
    """*text* as display cells: ``(segments lit, decimal point lit)`` per digit.

    A ``.`` or ``,`` lights the point of the cell before it and takes no cell
    of its own; a ``:`` is a narrow cell of its own whose segments are ``":"``
    (the two dots of a clock). Upper and lower case are the same character on a
    seven-segment display.
    """
    cells: list[tuple[str, bool]] = []
    for char in str(text):
        if char == ":":
            cells.append((":", False))
            continue
        if char in ".,":
            if cells and not cells[-1][1]:
                cells[-1] = (cells[-1][0], True)
            else:
                cells.append(("", True))
            continue
        cells.append((SEGMENTS.get(char.lower(), ""), False))
    return cells


def _segment_polys(x: float, y: float, w: float, h: float, t: float) -> dict[str, list]:
    """The seven hexagonal segments of a cell at ``(x, y)``, ``w`` by ``h``, ``t`` thick."""
    g = t * 0.18          # the gap between neighbouring segments
    half = t / 2.0
    mid = y + h / 2.0

    def horizontal(yc):
        return [(x + half + g, yc), (x + t + g, yc - half), (x + w - t - g, yc - half),
                (x + w - half - g, yc), (x + w - t - g, yc + half), (x + t + g, yc + half)]

    def vertical(xc, y0, y1):
        return [(xc, y0 + half + g), (xc + half, y0 + t + g), (xc + half, y1 - t - g),
                (xc, y1 - half - g), (xc - half, y1 - t - g), (xc - half, y0 + t + g)]

    return {
        "a": horizontal(y + half), "g": horizontal(mid), "d": horizontal(y + h - half),
        "f": vertical(x + half, y, mid), "b": vertical(x + w - half, y, mid),
        "e": vertical(x + half, mid, y + h), "c": vertical(x + w - half, mid, y + h),
    }


def lcd_number(value, digits: int = 5, fmt: str | None = None, size=None,
               colour=None, label: str = "") -> bool:
    """A seven-segment readout (``QLCDNumber``). Returns whether *value* overflowed.

    Parameters
    ----------
    value : float, int or str
        A number is formatted with *fmt* (``%g``-style by default, ``"%d"`` for an
        int); a string is shown as it is (``"12:30"``, ``"Err"``, ``"0x1F"`` minus
        the prefix).
    digits : int
        How many cells; the text is right-aligned in them.
    fmt : str, optional
        ``%``-format for a number.
    size : tuple, optional
        ``(width, height)``; a zero component is the default (two frame
        heights tall, cells 0.55 of the height wide).
    colour : colour, optional
        The lit segments; the theme's accent (the check-mark colour) by default.
        Unlit segments are drawn faintly in the same colour, as on a real panel.
    label : str
        An id (``"##rate"``) for a tooltip after it; the visible part is drawn
        under the display.
    """
    ctx = get_current_context()
    digits = max(1, int(digits))
    if isinstance(value, str):
        text = value
    elif fmt:
        text = _style.format_value(fmt, value)
    elif isinstance(value, int) and not isinstance(value, bool):
        text = "%d" % value
    else:
        text = "%.*g" % (max(1, digits - (1 if float(value) < 0 else 0)), float(value))
    cells = lcd_segments(text)
    overflow = len(cells) > digits
    if overflow:
        cells = [("adefg", False)] * digits
    cells = [("", False)] * (digits - len(cells)) + cells

    height = _w._frame_height(ctx) * 2.0
    width = 0.0
    if size is not None:
        width, height = float(size[0]), float(size[1]) or height
    cell_w = height * 0.55
    gap = height * 0.14
    natural = digits * cell_w + (digits - 1) * gap + 2.0 * gap
    width = width or natural
    shown = _w._visible_label(label) if label else ""
    label_h = ctx.p.line_height() + ctx.style.item_inner_spacing[1] if shown else 0.0
    box = ctx.layout.row(height=height + label_h, width=width)
    panel = (box[0], box[1], width, height)
    ctx.item_add(panel, ctx.get_id(label) if label else None)
    ctx.draw.add_rect_filled((panel[0], panel[1]), (panel[0] + width, panel[1] + height),
                             _w._col(Col.FRAME_BG), ctx.style.frame_rounding)
    lit = _w._col(Col.CHECK_MARK) if colour is None else (tuple(colour) if len(colour) == 4 else (*colour, 255))
    unlit = (*lit[:3], max(10, int(lit[3] * 0.09)))
    # Cells shrink to the box a caller gave, keeping their proportions.
    scale = min(1.0, (width - 2.0 * gap) / max(1.0, natural - 2.0 * gap))
    cw, cg = cell_w * scale, gap * scale
    ch = min(height - 2.0 * gap, cw / 0.55 * 0.82)
    thick = max(1.5, ch * 0.11)
    x = panel[0] + width - gap - digits * cw - (digits - 1) * cg
    y = panel[1] + (height - ch) / 2.0
    slant = ch * 0.06            # a real display leans a little to the right
    for lit_segments, point in cells:
        dot = thick * 1.1
        if lit_segments == ":":
            # A clock's colon: two dots in a narrow cell, always lit.
            cx = x + cw * 0.5 - dot / 2.0
            for fy in (0.3, 0.7):
                ctx.draw.add_rect_filled((cx, y + ch * fy - dot / 2.0), (cx + dot, y + ch * fy + dot / 2.0), lit)
            x += cw + cg
            continue
        polys = _segment_polys(x, y, cw - thick * 0.6, ch, thick)
        for name, poly in polys.items():
            sheared = [(px + slant * (1.0 - (py - y) / ch) - slant / 2.0, py) for px, py in poly]
            ctx.draw.add_convex_poly_filled(sheared, lit if name in lit_segments else unlit)
        # The point sits in the gap after the digit, on the baseline.
        px = x + cw - thick * 0.6 + (cg + thick * 0.6 - dot) / 2.0
        ctx.draw.add_rect_filled((px, y + ch - dot), (px + dot, y + ch), lit if point else unlit)
        x += cw + cg
    if shown:
        lw, _lh = ctx.draw.calc_text_size(shown)
        ctx.draw.add_text((box[0] + (width - lw) / 2.0, panel[1] + height + ctx.style.item_inner_spacing[1]),
                          _w._col(Col.TEXT), shown)
    ctx._last_item = panel
    return overflow
