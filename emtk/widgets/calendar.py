"""Dates and times: a month calendar, and the date, time and date-time fields that use it.

Qt has ``QCalendarWidget``, ``QDateEdit``, ``QTimeEdit`` and ``QDateTimeEdit``;
Dear ImGui has none of them, and a scientific desktop tool reaches for one the
moment it filters measurements by acquisition day or schedules a run. These are
the four, spelled the immediate-mode way -- the value goes in, ``(changed,
value)`` comes out, and the widget remembers nothing the caller owns::

    changed, day = im.calendar("##day", day, min_date=first, max_date=today)
    changed, day = im.date_input("Acquired", day)          # a field + popup calendar
    changed, at = im.time_input("Start", at)               # HH:MM:SS segments
    changed, when = im.datetime_input("Scheduled", when)   # both, one row

The values are the standard library's :class:`datetime.date`,
:class:`datetime.time` and :class:`datetime.datetime`, never a toolkit type, so
nothing converts at the boundary to the model.

The calendar
------------
A month grid of six week rows (always six, so the widget does not change height
between months), the weekdays over it from *first_weekday* (Monday, as ISO 8601
counts, unless the caller says otherwise), optionally ISO week numbers in a
column on the left. Above it, the month and year between previous / next
buttons: a single arrow moves a month, a double arrow a year, and the wheel
over the grid moves a month too. Today is outlined, the selected day filled,
days of the neighbouring months shown dimmed (a click on one goes there), and
days outside ``min_date`` / ``max_date`` dimmed further and inert.

The keyboard follows emtk's navigation model: Tab puts the focus on the grid
(the nav ring around it, and a ring around the *cursor* day), and then

=====================  ==========================================
Left / Right           one day back / forward
Up / Down              one week back / forward
Page Up / Page Down    one month back / forward (Shift: a year)
Home / End             first / last day of the month
Enter / Space          select the cursor day (the change)
=====================  ==========================================

The cursor never leaves the bounds. Arrows only *move* the cursor; Enter is
what changes the value, as in Qt's ``activated``: walking across the month to
the wanted day must not fire a query for every day on the way.

Month and weekday names are English source strings translated through
:func:`emtk.i18n.tr` in the ``emtk`` domain, so the calendar is as multilingual
as the rest of the toolkit; the title is ``"{month} {year}"`` for the same
reason (a language that puts the year first reorders the placeholders).

Colours and the style sheet
---------------------------
Everything is drawn in the current style's colours -- the header colours for
hover and selection, the check-mark accent for today, ``TEXT_DISABLED`` for
other months -- so the calendar follows the dark and light themes with no
palette of its own. A style sheet may still single it out: :mod:`emtk.stylesheet`
hands the ``calendar`` selectors (``calendar``, ``calendar::header``,
``calendar::weekday``, ``calendar::day``, ``calendar::day:hover``,
``calendar::day:selected``, ``calendar::day:today``, ``calendar::day:weekend``,
``calendar::day:other-month``, ``calendar::day:disabled``) to
:func:`use_stylesheet`. Those colours belong to the style sheet's theme and
stop applying when another theme is put up.
"""
from __future__ import annotations

import calendar as _cal
import datetime as _dt
from typing import Any

from .. import im_core as _core
from .. import im_widgets as _w
from .. import style as _style
from ..events import ALT_MODIFIER, SHIFT_MODIFIER
from ..flags import InputTextFlags
from ..i18n import mark, tr
from ..im_core import ButtonFlags, Col, ConfigFlags, ItemFlags, get_current_context
from ..keys import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_F4,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
    KEY_RIGHT,
    KEY_SPACE,
    KEY_UP,
)
from ..layout import Layout

__all__ = [
    "CALENDAR_PARTS",
    "STYLESHEET_SELECTORS",
    "add_months",
    "calendar",
    "calendar_size",
    "clamp_date",
    "date_input",
    "datetime_input",
    "format_date",
    "format_time",
    "month_grid",
    "month_name",
    "parse_date",
    "parse_time",
    "stylesheet_part",
    "time_input",
    "use_stylesheet",
    "weekday_name",
]

#: Month names, translated where they are shown (``tr(..., domain="emtk")``).
MONTH_NAMES = (
    mark("January", domain="emtk"), mark("February", domain="emtk"),
    mark("March", domain="emtk"), mark("April", domain="emtk"),
    mark("May", domain="emtk"), mark("June", domain="emtk"),
    mark("July", domain="emtk"), mark("August", domain="emtk"),
    mark("September", domain="emtk"), mark("October", domain="emtk"),
    mark("November", domain="emtk"), mark("December", domain="emtk"),
)
#: Weekday abbreviations, Monday first (``date.weekday()`` order).
WEEKDAY_NAMES = (
    mark("Mon", domain="emtk"), mark("Tue", domain="emtk"), mark("Wed", domain="emtk"),
    mark("Thu", domain="emtk"), mark("Fri", domain="emtk"), mark("Sat", domain="emtk"),
    mark("Sun", domain="emtk"),
)

#: The parts a style sheet can colour, and the property each one takes.
CALENDAR_PARTS = (
    "background", "border", "header", "header_text", "weekday", "day", "day_hover",
    "day_selected", "day_selected_text", "today", "weekend", "other_month", "disabled",
)

#: ``(selector, property) -> part``. ``color`` is a text colour, ``background`` a fill,
#: ``border-color`` an outline -- the CSS meanings, so a rule reads the way it draws.
STYLESHEET_SELECTORS: dict[tuple[str, str], str] = {
    ("calendar", "background"): "background",
    ("calendar", "background-color"): "background",
    ("calendar", "border-color"): "border",
    ("calendar", "color"): "day",
    ("calendar::header", "background"): "header",
    ("calendar::header", "background-color"): "header",
    ("calendar::header", "color"): "header_text",
    ("calendar::weekday", "color"): "weekday",
    ("calendar::day", "color"): "day",
    ("calendar::day:hover", "background"): "day_hover",
    ("calendar::day:hover", "background-color"): "day_hover",
    ("calendar::day:selected", "background"): "day_selected",
    ("calendar::day:selected", "background-color"): "day_selected",
    ("calendar::day:selected", "color"): "day_selected_text",
    ("calendar::day:today", "border-color"): "today",
    ("calendar::day:today", "color"): "today",
    ("calendar::day:weekend", "color"): "weekend",
    ("calendar::day:other-month", "color"): "other_month",
    ("calendar::day:disabled", "color"): "disabled",
}

#: ``(theme name, {part: rgba})`` installed by a style sheet; see :func:`use_stylesheet`.
_SHEET: tuple[str | None, dict] = (None, {})


def stylesheet_part(selector: str, prop: str) -> str | None:
    """The calendar part a style-sheet rule colours, or ``None`` if it is not a calendar rule.

    Parameters
    ----------
    selector : str
        A selector such as ``"calendar::day:selected"`` (``:`` and ``::`` both
        accepted between the parts, ``QCalendarWidget`` as a synonym of
        ``calendar``).
    prop : str
        The property name, lower case (``"background-color"``).

    Returns
    -------
    str or None
        One of :data:`CALENDAR_PARTS`.
    """
    s = selector.strip().replace("QCalendarWidget", "calendar")
    if not s.startswith("calendar"):
        return None
    # `calendar:day:selected` and `calendar::day::selected` are the same rule written loosely.
    head, _, rest = s.partition(":")
    parts = [part for part in rest.split(":") if part]
    canonical = head + ("::" + parts[0] if parts else "") + "".join(":" + p for p in parts[1:])
    return STYLESHEET_SELECTORS.get((canonical, prop.strip().lower()))


def use_stylesheet(theme: str | None, colours: dict | None) -> None:
    """Install the calendar colours a style sheet named *theme* declared.

    Called by :func:`emtk.stylesheet.apply_stylesheet`. The colours apply while
    *theme* is the current theme (:func:`emtk.theme.current_theme`), so putting
    up the plain dark or light theme afterwards gives the calendar back its
    style colours without anyone having to clear them.

    Parameters
    ----------
    theme : str or None
        The theme the style sheet registered.
    colours : dict or None
        ``{part: (r, g, b, a)}``, parts from :data:`CALENDAR_PARTS`.
    """
    global _SHEET
    unknown = set(colours or ()) - set(CALENDAR_PARTS)
    if unknown:
        raise KeyError(f"not calendar parts: {sorted(unknown)}")
    _SHEET = (theme, dict(colours or {}))


def _sheet_colour(part: str, default):
    theme, colours = _SHEET
    if colours and part in colours:
        from .. import theme as _theme

        if _theme.current_theme() == theme:
            colour = colours[part]
            if _core.get_current_context().item_flags & ItemFlags.DISABLED:
                return (*colour[:3], int(colour[3] * _core.get_style().disabled_alpha))
            return colour
    return default


# --------------------------------------------------------------------------- #
# Date arithmetic -- pure, and tested on its own
# --------------------------------------------------------------------------- #
def _as_date(value: Any) -> _dt.date | None:
    """A :class:`datetime.date` from a date or a datetime (whose date part it is)."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    raise TypeError(f"expected a datetime.date, got {type(value).__name__}")


def clamp_date(day: _dt.date, min_date: _dt.date | None = None,
               max_date: _dt.date | None = None) -> _dt.date:
    """*day* moved inside ``[min_date, max_date]`` (either bound may be ``None``)."""
    if min_date is not None and day < min_date:
        day = min_date
    if max_date is not None and day > max_date:
        day = max_date
    return day


def add_months(day: _dt.date, months: int) -> _dt.date:
    """*day* moved by *months* calendar months, the day of month clamped to the new month.

    31 January plus one month is the last day of February, as every calendar
    widget does it; the result stays inside the representable years.
    """
    index = day.year * 12 + (day.month - 1) + int(months)
    year, month0 = divmod(index, 12)
    year = min(max(year, _dt.MINYEAR), _dt.MAXYEAR)
    if index < _dt.MINYEAR * 12:
        month0 = 0
    elif index > _dt.MAXYEAR * 12 + 11:
        month0 = 11
    last = _cal.monthrange(year, month0 + 1)[1]
    return _dt.date(year, month0 + 1, min(day.day, last))


def month_grid(year: int, month: int, first_weekday: int = 0) -> list[_dt.date | None]:
    """The 42 days a month view shows, row by row, starting on *first_weekday*.

    Parameters
    ----------
    year, month : int
        The month.
    first_weekday : int
        0 = Monday ... 6 = Sunday, as :meth:`datetime.date.weekday`.

    Returns
    -------
    list of datetime.date or None
        Six weeks; the first row holds the 1st. A cell before 1 January of year
        1 or after 31 December 9999 is ``None`` -- it cannot be represented.
    """
    first = _dt.date(year, month, 1)
    lead = (first.weekday() - int(first_weekday)) % 7
    out: list[_dt.date | None] = []
    for offset in range(-lead, 42 - lead):
        try:
            out.append(first + _dt.timedelta(days=offset))
        except OverflowError:
            out.append(None)
    return out


def month_name(month: int) -> str:
    """The translated name of *month* (1-12)."""
    return tr(MONTH_NAMES[int(month) - 1], domain="emtk")


def weekday_name(weekday: int) -> str:
    """The translated abbreviation of *weekday* (0 = Monday)."""
    return tr(WEEKDAY_NAMES[int(weekday) % 7], domain="emtk")


#: What a date field accepts, tried in order. ISO first: it is what the field shows.
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y%m%d")


def parse_date(text: str, fmt: str | None = None) -> _dt.date | None:
    """The date typed into a field, or ``None`` when it is not one.

    *fmt* (a :meth:`~datetime.datetime.strptime` format) is tried first, then
    ISO ``2026-10-19``, ``2026/10/19``, ``19.10.2026`` and ``20261019``.
    """
    text = str(text or "").strip()
    if not text:
        return None
    for candidate in ((fmt,) if fmt else ()) + _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, candidate).date()
        except ValueError:
            continue
    return None


def format_date(day: _dt.date | None, fmt: str | None = None) -> str:
    """*day* as a field shows it: ISO 8601 unless *fmt* says otherwise; ``""`` for ``None``."""
    if day is None:
        return ""
    return day.strftime(fmt) if fmt else day.isoformat()


def parse_time(text: str) -> _dt.time | None:
    """``"14:30"``, ``"14:30:05"`` or ``"1430"`` as a :class:`datetime.time`; ``None`` if not one."""
    text = str(text or "").strip()
    for candidate in ("%H:%M:%S", "%H:%M", "%H%M%S", "%H%M"):
        try:
            return _dt.datetime.strptime(text, candidate).time()
        except ValueError:
            continue
    return None


def format_time(value: _dt.time | None, seconds: bool = True) -> str:
    """``"HH:MM:SS"`` (or ``"HH:MM"``); ``""`` for ``None``."""
    if value is None:
        return ""
    return value.strftime("%H:%M:%S" if seconds else "%H:%M")


# --------------------------------------------------------------------------- #
# Measuring and colours
# --------------------------------------------------------------------------- #
def _metrics(ctx, week_numbers: bool) -> dict:
    """Cell and row sizes, from the font and the frame padding -- never fixed pixels."""
    pad_x, pad_y = ctx.style.frame_padding
    line = ctx.p.line_height()
    widest_day = ctx.draw.calc_text_size("28")[0]
    widest_name = max(ctx.draw.calc_text_size(weekday_name(i))[0] for i in range(7))
    cell_w = max(widest_day + 2.0 * pad_x + 4.0, widest_name + 2.0 * pad_x, line * 1.9)
    cell_h = line + 2.0 * pad_y
    week_w = (max(ctx.draw.calc_text_size("53")[0], ctx.draw.calc_text_size(tr("Wk", domain="emtk"))[0])
              + 2.0 * pad_x) if week_numbers else 0.0
    header_h = cell_h + 2.0
    weekday_h = line + pad_y
    width = week_w + 7.0 * cell_w
    # The title must fit between the four arrows: a long month in a wide font widens the grid.
    title_w = max(ctx.draw.calc_text_size(f"{month_name(m)} 2000")[0] for m in range(1, 13))
    width = max(width, title_w + 4.0 * cell_h + 4.0 * pad_x)
    cell_w = (width - week_w) / 7.0
    return {"cell_w": cell_w, "cell_h": cell_h, "week_w": week_w, "header_h": header_h,
            "weekday_h": weekday_h, "width": width,
            "height": header_h + weekday_h + 6.0 * cell_h + pad_y}


def calendar_size(show_week_numbers: bool = False) -> tuple[float, float]:
    """The ``(width, height)`` :func:`calendar` occupies in the current style and font."""
    m = _metrics(get_current_context(), show_week_numbers)
    return (m["width"], m["height"])


def _dim(colour, alpha_scale: float):
    rgba = tuple(colour) if len(colour) == 4 else (*colour, 255)
    return (*rgba[:3], int(rgba[3] * alpha_scale))


def _arrow(ctx, box, direction: int, double: bool, colour) -> None:
    """A filled left (*direction* < 0) or right triangle -- two side by side for *double* -- in *box*."""
    x, y, w, h = box
    size = h * 0.2
    cy = y + h / 2.0
    sign = 1.0 if direction > 0 else -1.0
    centres = (x + w / 2.0 - size * 0.55, x + w / 2.0 + size * 0.55) if double else (x + w / 2.0,)
    for cx in centres:
        ctx.draw.add_triangle_filled((cx - sign * size * 0.6, cy - size), (cx - sign * size * 0.6, cy + size),
                                     (cx + sign * size * 0.6, cy), colour)


# --------------------------------------------------------------------------- #
# The calendar
# --------------------------------------------------------------------------- #
_CAL_KEYS = (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_PAGE_UP, KEY_PAGE_DOWN, KEY_HOME,
             KEY_END, KEY_RETURN, KEY_ENTER, KEY_SPACE)


def _take_keys(ctx, wanted) -> list[tuple[int, int]]:
    """The presses of *wanted* keys this frame, as ``(key, modifiers)``, spent so nothing else sees them."""
    io = ctx.io
    taken = [(key, mods) for key, _text, mods in io.key_events if key in wanted]
    if not taken and io.key in wanted:
        from .. import im_widgets

        taken = [(io.key, im_widgets._current_modifiers(io))]
    if taken:
        io.key_events[:] = [event for event in io.key_events if event[0] not in wanted]
        if io.key in wanted:
            io.key = 0
        io.text = ""
        ctx.request_frame()
    return taken


def _move_cursor(cursor: _dt.date, key: int, mods: int) -> _dt.date:
    """Where one key press takes the cursor (bounds are applied by the caller)."""
    try:
        if key == KEY_LEFT:
            return cursor - _dt.timedelta(days=1)
        if key == KEY_RIGHT:
            return cursor + _dt.timedelta(days=1)
        if key == KEY_UP:
            return cursor - _dt.timedelta(days=7)
        if key == KEY_DOWN:
            return cursor + _dt.timedelta(days=7)
    except OverflowError:
        return cursor
    step = 12 if mods & SHIFT_MODIFIER else 1
    if key == KEY_PAGE_UP:
        return add_months(cursor, -step)
    if key == KEY_PAGE_DOWN:
        return add_months(cursor, step)
    if key == KEY_HOME:
        return cursor.replace(day=1)
    if key == KEY_END:
        return cursor.replace(day=_cal.monthrange(cursor.year, cursor.month)[1])
    return cursor


def _calendar(ctx, item_id, value: _dt.date | None, min_date, max_date, first_weekday: int,
              week_numbers: bool, today: _dt.date, keys_active: bool) -> tuple[bool, _dt.date | None]:
    """Draw the calendar at the layout cursor; ``(changed, value)``. *keys_active* forces keyboard focus."""
    m = _metrics(ctx, week_numbers)
    store = ctx.get_storage(("calendar", item_id))
    box = ctx.layout.row(height=m["height"], width=m["width"])
    x0, y0 = box[0], box[1]

    # The cursor (the keyboard's day) and the shown month follow the value when the caller changes it.
    if store.get("seen", "unset") != value:
        store["seen"] = value
        start = clamp_date(value or today, min_date, max_date)
        store["cursor"] = start
        store["view"] = (start.year, start.month)
    cursor = clamp_date(store.get("cursor") or clamp_date(today, min_date, max_date), min_date, max_date)
    view_year, view_month = store.get("view", (cursor.year, cursor.month))
    changed = False

    def in_bounds(day):
        return day is not None and (min_date is None or day >= min_date) \
            and (max_date is None or day <= max_date)

    def month_reachable(year, month):
        first = _dt.date(year, month, 1)
        last = first.replace(day=_cal.monthrange(year, month)[1])
        return (min_date is None or last >= min_date) and (max_date is None or first <= max_date)

    def shift_view(months):
        nonlocal view_year, view_month, cursor
        target = add_months(_dt.date(view_year, view_month, 1), months)
        if (target.year, target.month) == (view_year, view_month) \
                or not month_reachable(target.year, target.month):
            return
        view_year, view_month = target.year, target.month
        cursor = clamp_date(add_months(cursor, (target.year - cursor.year) * 12
                                       + target.month - cursor.month), min_date, max_date)

    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    # -- background and header ------------------------------------------------ #
    ctx.draw.add_rect_filled((x0, y0), (x0 + box[2], y0 + box[3]),
                             _sheet_colour("background", _w._col(Col.FRAME_BG)), ctx.style.frame_rounding)
    ctx.draw.add_rect((x0, y0), (x0 + box[2], y0 + box[3]),
                      _sheet_colour("border", _w._col(Col.BORDER)), ctx.style.frame_rounding)
    header = (x0, y0, box[2], m["header_h"])
    ctx.draw.add_rect_filled((header[0], header[1]), (header[0] + header[2], header[1] + header[3]),
                             _sheet_colour("header", _w._col(Col.HEADER)), ctx.style.frame_rounding)
    side = m["cell_h"]
    arrows = (
        (-12, True, (x0 + 1.0, y0 + 1.0, side, side), tr("Previous year", domain="emtk")),
        (-1, False, (x0 + 1.0 + side, y0 + 1.0, side, side), tr("Previous month", domain="emtk")),
        (1, False, (x0 + box[2] - 1.0 - 2.0 * side, y0 + 1.0, side, side), tr("Next month", domain="emtk")),
        (12, True, (x0 + box[2] - 1.0 - side, y0 + 1.0, side, side), tr("Next year", domain="emtk")),
    )
    text_colour = _sheet_colour("header_text", _w._col(Col.TEXT))
    ctx.push_item_flag(ItemFlags.NO_NAV, True)
    for months, double, arrow_box, tip in arrows:
        target = add_months(_dt.date(view_year, view_month, 1), months)
        possible = ((target.year, target.month) != (view_year, view_month)
                    and month_reachable(target.year, target.month))
        arrow_id = (*item_id, "nav", months)
        if possible and not disabled:
            hovered, held, pressed = ctx.button_behavior(arrow_box, arrow_id)
        else:
            ctx.item_add(arrow_box, arrow_id)
            hovered = held = pressed = False
        if hovered or held:
            ctx.draw.add_rect_filled((arrow_box[0], arrow_box[1]),
                                     (arrow_box[0] + arrow_box[2], arrow_box[1] + arrow_box[3]),
                                     _w._col(Col.BUTTON_ACTIVE if held else Col.BUTTON_HOVERED),
                                     ctx.style.frame_rounding)
        _arrow(ctx, arrow_box, months, double, text_colour if possible else _w._col(Col.TEXT_DISABLED))
        if _w.is_item_hovered(allow_when_disabled=True):
            _w.set_tooltip(tip)
        if pressed:
            shift_view(months)
    ctx.pop_item_flag()
    title = tr("{month} {year}", domain="emtk").format(month=month_name(view_month), year=view_year)
    tw, th = ctx.draw.calc_text_size(title)
    ctx.draw.add_text((x0 + (box[2] - tw) / 2.0, y0 + (m["header_h"] - th) / 2.0), text_colour, title)

    # -- weekday header ------------------------------------------------------- #
    grid_x = x0 + m["week_w"]
    names_y = y0 + m["header_h"]
    weekday_colour = _sheet_colour("weekday", _w._col(Col.TEXT_DISABLED))
    for column in range(7):
        name = weekday_name(first_weekday + column)
        nw, nh = ctx.draw.calc_text_size(name)
        ctx.draw.add_text((grid_x + column * m["cell_w"] + (m["cell_w"] - nw) / 2.0,
                           names_y + (m["weekday_h"] - nh) / 2.0), weekday_colour, name)
    if week_numbers:
        label = tr("Wk", domain="emtk")
        lw, lh = ctx.draw.calc_text_size(label)
        ctx.draw.add_text((x0 + (m["week_w"] - lw) / 2.0, names_y + (m["weekday_h"] - lh) / 2.0),
                          weekday_colour, label)

    # -- the grid: one item, the day under the pointer is arithmetic ---------- #
    grid_y = names_y + m["weekday_h"]
    grid = (grid_x, grid_y, 7.0 * m["cell_w"], 6.0 * m["cell_h"])
    days = month_grid(view_year, view_month, first_weekday)
    hovered, _held, pressed = ctx.button_behavior(grid, item_id, ButtonFlags.NO_NAV_ACTIVATE)
    mx, my = ctx.io.mouse_pos
    under: _dt.date | None = None
    if hovered:
        column = int((mx - grid_x) // m["cell_w"])
        row = int((my - grid_y) // m["cell_h"])
        if 0 <= column < 7 and 0 <= row < 6:
            under = days[row * 7 + column]
        if ctx.io.mouse_wheel and not disabled:
            # One month a notch, as Qt's calendar does; the wheel is spent here.
            shift_view(-1 if ctx.io.mouse_wheel > 0 else 1)
            days = month_grid(view_year, view_month, first_weekday)
            ctx.io.mouse_wheel = 0.0
            ctx.request_frame()
    if pressed and under is not None and in_bounds(under):
        cursor = under
        if under != value:
            value, changed = under, True
        view_year, view_month = under.year, under.month
        days = month_grid(view_year, view_month, first_weekday)

    focused = not disabled and (keys_active or ctx.is_nav_focused(item_id)) \
        and bool(ctx.io.config_flags & ConfigFlags.NAV_ENABLE_KEYBOARD)
    if focused:
        for key, mods in _take_keys(ctx, _CAL_KEYS):
            if key in (KEY_RETURN, KEY_ENTER, KEY_SPACE):
                if in_bounds(cursor) and cursor != value:
                    value, changed = cursor, True
                elif in_bounds(cursor):
                    # Enter on the selected day is still "this one" -- a popup closes on it.
                    store["confirmed"] = True
                continue
            cursor = clamp_date(_move_cursor(cursor, key, mods), min_date, max_date)
        if (cursor.year, cursor.month) != (view_year, view_month):
            view_year, view_month = cursor.year, cursor.month
            days = month_grid(view_year, view_month, first_weekday)

    # -- paint the days ------------------------------------------------------- #
    day_colour = _sheet_colour("day", _w._col(Col.TEXT))
    other_colour = _sheet_colour("other_month", _w._col(Col.TEXT_DISABLED))
    out_colour = _sheet_colour("disabled", _dim(_w._col(Col.TEXT_DISABLED), 0.45))
    weekend_colour = _sheet_colour("weekend", _style.lerp_colour(_w._col(Col.TEXT), _style.TEXT_DANGER, 0.55))
    selected_fill = _sheet_colour("day_selected", _w._col(Col.HEADER_ACTIVE))
    selected_text = _sheet_colour("day_selected_text",
                                  _style.most_readable(selected_fill, _w._col(Col.TEXT), (255, 255, 255), (0, 0, 0)))
    hover_fill = _sheet_colour("day_hover", _w._col(Col.HEADER_HOVERED))
    today_colour = _sheet_colour("today", _w._col(Col.CHECK_MARK))
    week_colour = _w._col(Col.TEXT_DISABLED)
    show_cursor = focused and ctx.nav_visible and (keys_active or ctx.state(("nav",)).get("visible", True))
    for index, day in enumerate(days):
        row, column = divmod(index, 7)
        cx = grid_x + column * m["cell_w"]
        cy = grid_y + row * m["cell_h"]
        cell = (cx + 1.0, cy + 1.0, m["cell_w"] - 2.0, m["cell_h"] - 2.0)
        if week_numbers and column == 0:
            anchor = next((d for d in days[row * 7:row * 7 + 7] if d is not None), None)
            if anchor is not None:
                text = str(anchor.isocalendar()[1])
                ww, wh = ctx.draw.calc_text_size(text)
                ctx.draw.add_text((x0 + (m["week_w"] - ww) / 2.0, cy + (m["cell_h"] - wh) / 2.0),
                                  week_colour, text)
        if day is None:
            continue
        reachable = in_bounds(day)
        is_selected = value is not None and day == value
        if is_selected:
            ctx.draw.add_rect_filled((cell[0], cell[1]), (cell[0] + cell[2], cell[1] + cell[3]),
                                     selected_fill, ctx.style.frame_rounding)
        elif under == day and reachable and not disabled:
            ctx.draw.add_rect_filled((cell[0], cell[1]), (cell[0] + cell[2], cell[1] + cell[3]),
                                     hover_fill, ctx.style.frame_rounding)
        if day == today:
            ctx.draw.add_rect((cell[0], cell[1]), (cell[0] + cell[2], cell[1] + cell[3]),
                              today_colour, ctx.style.frame_rounding, thickness=1.5)
        if show_cursor and day == cursor:
            ctx.draw.add_rect((cell[0] + 2.0, cell[1] + 2.0),
                              (cell[0] + cell[2] - 2.0, cell[1] + cell[3] - 2.0),
                              _w._col(Col.NAV_HIGHLIGHT), ctx.style.frame_rounding, thickness=1.0)
        if not reachable:
            colour = out_colour
        elif is_selected:
            colour = selected_text
        elif day.month != view_month:
            colour = other_colour
        elif day.weekday() >= 5:
            colour = weekend_colour
        else:
            colour = day_colour
        text = str(day.day)
        dw, dh = ctx.draw.calc_text_size(text)
        ctx.draw.add_text((cx + (m["cell_w"] - dw) / 2.0, cy + (m["cell_h"] - dh) / 2.0),
                          colour, text, bold=day == today)

    if under is not None and not disabled:
        # The whole date, in words, for the day under the pointer.
        _w.set_tooltip(tr("{weekday}, {day} {month} {year}", domain="emtk").format(
            weekday=weekday_name(under.weekday()), day=under.day, month=month_name(under.month),
            year=under.year))
    if focused or ctx.is_nav_focused(item_id):
        _w._nav_ring(ctx, box, item_id)
    store["cursor"] = cursor
    store["view"] = (view_year, view_month)
    store["seen"] = value
    # The item a following `set_item_tooltip` / `is_item_hovered` speaks of is the calendar.
    ctx._last_item = box
    ctx._last_id = item_id
    return changed, value


def calendar(label: str, value: _dt.date | None, min_date: _dt.date | None = None,
             max_date: _dt.date | None = None, first_weekday: int = 0,
             show_week_numbers: bool = False,
             today: _dt.date | None = None) -> tuple[bool, _dt.date | None]:
    """A month calendar (``QCalendarWidget``): ``(changed, date)``.

    Parameters
    ----------
    label : str
        Its id (``"##day"``); the visible part, if any, is drawn above it.
    value : datetime.date or None
        The selected day; ``None`` selects nothing and shows today's month.
        A :class:`~datetime.datetime` is read for its date.
    min_date, max_date : datetime.date, optional
        The days that can be chosen; the others are shown but inert, and the
        month arrows stop at the bounds.
    first_weekday : int
        The first column: 0 = Monday (ISO 8601, the default) ... 6 = Sunday.
    show_week_numbers : bool
        A column of ISO week numbers on the left.
    today : datetime.date, optional
        The day outlined as today; the system date unless given (a test, a
        replay of a recorded session).

    Returns
    -------
    tuple of (bool, datetime.date or None)
        Changed on the frame a day is clicked or Enter selects the cursor day.
    """
    ctx = get_current_context()
    shown = _w._visible_label(label)
    if shown:
        _w.text(shown)
    return _calendar(ctx, ctx.get_id(label), _as_date(value), _as_date(min_date), _as_date(max_date),
                     int(first_weekday) % 7, bool(show_week_numbers),
                     _as_date(today) or _dt.date.today(), keys_active=False)


# --------------------------------------------------------------------------- #
# The date field and its popup
# --------------------------------------------------------------------------- #
def _calendar_icon(ctx, box, colour) -> None:
    """A small page-of-a-calendar glyph, drawn (not a font glyph, which a font may lack)."""
    x, y, w, h = box
    side = min(w, h) * 0.56
    left, top = x + (w - side) / 2.0, y + (h - side) / 2.0
    ctx.draw.add_rect((left, top), (left + side, top + side), colour, 1.0, thickness=1.2)
    ctx.draw.add_rect_filled((left, top), (left + side, top + side * 0.28), colour)
    dot = max(1.0, side * 0.14)
    for row in range(2):
        for column in range(3):
            dx = left + side * (0.2 + 0.3 * column)
            dy = top + side * (0.48 + 0.26 * row)
            ctx.draw.add_rect_filled((dx, dy), (dx + dot, dy + dot), colour)


def _popup_overlay(item_id, anchor, value, min_date, max_date, first_weekday, week_numbers, today):
    """The calendar under (or over) the field, as an overlay that owns the input while it is up."""
    def draw(ctx) -> bool:
        state = ctx.state(("date_popup", item_id))
        if not state.get("open"):
            return False
        pad = ctx.style.frame_padding[0]
        m = _metrics(ctx, week_numbers)
        w, h = m["width"] + 2.0 * pad, m["height"] + 2.0 * pad
        fx, fy, fw, fh = ctx.box
        x = min(max(anchor[0], fx), max(fx, fx + fw - w))
        y = anchor[1] + anchor[3] + 2.0
        if y + h > fy + fh and anchor[1] - h - 2.0 >= fy:
            y = anchor[1] - h - 2.0          # no room below: flip above the field
        popup = (x, y, w, h)
        io = ctx.io
        if io.key == KEY_ESCAPE or any(event[0] == KEY_ESCAPE for event in io.key_events):
            _take_keys(ctx, (KEY_ESCAPE,))
            state["open"] = False
            return False
        if io.mouse_clicked[0] and not _style.hit(*io.mouse_pos, *popup):
            state["open"] = False
            if not _style.hit(*io.mouse_pos, *anchor):
                # The press that closed the popup still reaches what is under it.
                ctx.storage["__replay_click__"] = (0, *io.mouse_pos)
            ctx.request_frame()
            return False
        shadow = ctx.style.window_shadow_size
        if shadow > 0:
            ctx.draw.add_rect_filled((x + shadow, y + shadow), (x + w + shadow, y + h + shadow),
                                     ctx.style.window_shadow_color, ctx.style.frame_rounding)
        ctx.draw.add_rect_filled((x, y), (x + w, y + h), _w._col(Col.POPUP_BG), ctx.style.frame_rounding)
        ctx.draw.add_rect((x, y), (x + w, y + h), _w._col(Col.BORDER), ctx.style.frame_rounding)
        saved = ctx.layout
        ctx.layout = Layout(ctx.p, x + pad, y + pad, w - 2.0 * pad, h - 2.0 * pad, style=saved.style)
        try:
            store = ctx.get_storage(("calendar", (*item_id, "popup")))
            store.pop("confirmed", None)
            changed, picked = _calendar(ctx, (*item_id, "popup"), value, min_date, max_date,
                                        first_weekday, week_numbers, today, keys_active=True)
        finally:
            ctx.layout = saved
        if changed or store.pop("confirmed", False):
            state["picked"] = picked
            state["open"] = False
            ctx.request_frame()
            return False
        return True
    return draw


def _date_field(ctx, label: str, item_id, value: _dt.date | None, width: float,
                min_date, max_date, fmt, first_weekday, week_numbers, today) -> tuple[bool, _dt.date | None]:
    """The text field and calendar button of a date input, *width* wide; ``(changed, date)``."""
    state = ctx.state(("date_popup", item_id))
    store = ctx.get_storage(("date_field", item_id))
    changed = False
    if "picked" in state:
        picked = state.pop("picked")
        if picked is not None and picked != value:
            value, changed = picked, True
        store.pop("buffer", None)
    button_w = _w._frame_height(ctx)
    shown = format_date(value, fmt)
    text_now = store.get("buffer", shown)
    ctx.push_id(item_id[-1])
    _w.set_next_item_width(max(width - button_w, 24.0))
    entered, text = _w.input_text("##text", text_now, fmt or "YYYY-MM-DD",
                                  InputTextFlags.ENTER_RETURNS_TRUE)
    field_box = ctx._last_item
    field_id = ctx._last_id
    field_hovered = _w.is_item_hovered()
    if text != text_now:
        store["buffer"] = text
    io = ctx.io
    if io.key == KEY_ESCAPE and "buffer" in store and ctx.is_nav_focused(field_id):
        store.pop("buffer", None)
    elif "buffer" in store and (entered or (io.mouse_clicked[0] and not field_hovered)):
        typed = store.pop("buffer")
        if typed.strip() == "":
            pass                               # an emptied field keeps the value it had
        else:
            parsed = parse_date(typed, fmt)
            if parsed is not None:
                parsed = clamp_date(parsed, min_date, max_date)
                if parsed != value:
                    value, changed = parsed, True
    open_by_key = False
    if ctx.is_nav_focused(field_id):
        # Qt's QDateEdit opens its calendar on Alt+Down and F4.
        for key, mods in _take_keys(ctx, (KEY_DOWN, KEY_F4)):
            if key == KEY_F4 or mods & ALT_MODIFIER:
                open_by_key = True
    _w.same_line(0.0, 0.0)
    ctx.push_item_flag(ItemFlags.NO_NAV, True)
    button_box = ctx.layout.row(height=_w._frame_height(ctx), width=button_w)
    hovered, held, pressed = ctx.button_behavior(button_box, (*item_id, "button"))
    ctx.pop_item_flag()
    ctx.draw.add_rect_filled((button_box[0], button_box[1]),
                             (button_box[0] + button_box[2], button_box[1] + button_box[3]),
                             _w._col(Col.BUTTON_ACTIVE if held else (Col.BUTTON_HOVERED if hovered else Col.BUTTON)),
                             ctx.style.frame_rounding)
    _calendar_icon(ctx, button_box, _w._col(Col.TEXT))
    if _w.is_item_hovered(allow_when_disabled=True):
        _w.set_tooltip(tr("Choose a date", domain="emtk"))
    ctx.pop_id()
    if pressed or open_by_key:
        state["open"] = not state.get("open", False) if pressed else True
        ctx.request_frame()
    if state.get("open"):
        anchor = (field_box[0], field_box[1], button_box[0] + button_box[2] - field_box[0], field_box[3])
        ctx.add_overlay(("date_popup", item_id),
                        _popup_overlay(item_id, anchor, value, min_date, max_date, first_weekday,
                                       week_numbers, today))
    # A following `set_item_tooltip` speaks of the field.
    ctx._last_item = (field_box[0], field_box[1], button_box[0] + button_box[2] - field_box[0], field_box[3])
    ctx._last_id = field_id
    return changed, value


def _labelled(ctx, label: str):
    """``(total_box_width, label_text, label_width)`` for a framed input with its caption at the right."""
    shown = _w._visible_label(label)
    label_w = (ctx.draw.calc_text_size(shown)[0] + ctx.style.item_inner_spacing[0]) if shown else 0.0
    wanted = ctx.take_next_item_width(None)
    if wanted is None:
        wanted = max(1.0, ctx.layout.avail()[0])
    else:
        wanted = _w._labelled_item_width(ctx, wanted, label_w)
    return wanted, shown, label_w


def _draw_caption(ctx, shown: str) -> None:
    """The caption to the right of a framed input, as ``im`` fields draw their label."""
    if shown:
        _w.same_line(0.0, ctx.style.item_inner_spacing[0])
        box = ctx.layout.row(height=_w._frame_height(ctx), width=ctx.draw.calc_text_size(shown)[0])
        ctx.item_add(box)
        ctx.draw.add_text((box[0], box[1] + ctx.style.frame_padding[1]), _w._col(Col.TEXT), shown)


def date_input(label: str, value: _dt.date | None, min_date: _dt.date | None = None,
               max_date: _dt.date | None = None, fmt: str | None = None,
               first_weekday: int = 0, show_week_numbers: bool = False,
               today: _dt.date | None = None) -> tuple[bool, _dt.date | None]:
    """A date field with a popup calendar (``QDateEdit``): ``(changed, date)``.

    The day is typed (ISO ``2026-10-19`` is what the field shows; ``19.10.2026``
    and ``2026/10/19`` parse too) and committed on Enter or a click elsewhere --
    clamped into the bounds, a typo leaving the value as it was -- or picked
    from the calendar the button beside it opens (Alt+Down or F4 open it from
    the keyboard; Escape or a click outside close it). The caption is drawn at
    the right, as every ``im`` field draws its label.

    Parameters
    ----------
    label : str
        Caption and id (``"Acquired##day"``).
    value : datetime.date or None
    min_date, max_date : datetime.date, optional
    fmt : str, optional
        A :meth:`~datetime.date.strftime` format for the field (``"%d.%m.%Y"``);
        ISO 8601 by default.
    first_weekday, show_week_numbers, today
        As :func:`calendar`.
    """
    ctx = get_current_context()
    total, shown, label_w = _labelled(ctx, label)
    item_id = ctx.get_id(label)
    changed, value = _date_field(ctx, label, item_id, _as_date(value), max(total - label_w, 40.0),
                                 _as_date(min_date), _as_date(max_date), fmt, int(first_weekday) % 7,
                                 bool(show_week_numbers), _as_date(today) or _dt.date.today())
    last = (ctx._last_item, ctx._last_id)
    _draw_caption(ctx, shown)
    ctx._last_item, ctx._last_id = last
    return changed, value


# --------------------------------------------------------------------------- #
# The time field
# --------------------------------------------------------------------------- #
_TIME_KEYS = (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_PAGE_UP, KEY_PAGE_DOWN, KEY_BACKSPACE,
              KEY_HOME, KEY_END)


def _time_segments(ctx, item_id, value: _dt.time, width: float, seconds: bool,
                   min_time, max_time) -> tuple[bool, _dt.time]:
    """The ``HH : MM : SS`` frame of a time input, *width* wide; ``(changed, time)``."""
    store = ctx.get_storage(("time_field", item_id))
    count = 3 if seconds else 2
    limits = (23, 59, 59)
    box = ctx.layout.row(height=_w._frame_height(ctx), width=width)
    hovered, _held, _pressed = ctx.button_behavior(box, item_id, ButtonFlags.NO_NAV_ACTIVATE)
    pad_x, pad_y = ctx.style.frame_padding
    digit_w = ctx.draw.calc_text_size("00")[0]
    colon_w = ctx.draw.calc_text_size(":")[0] + 2.0
    seg_boxes = []
    x = box[0] + pad_x
    for index in range(count):
        seg_boxes.append((x - 1.0, box[1] + 1.0, digit_w + 2.0, box[3] - 2.0))
        x += digit_w + 2.0 + (colon_w if index < count - 1 else 0.0)
    parts = [value.hour, value.minute, value.second]
    original = list(parts)
    io = ctx.io
    disabled = bool(ctx.item_flags & ItemFlags.DISABLED)
    if hovered and io.mouse_clicked[0]:
        _w.set_nav_id(item_id)
        # The segment under the press, or the nearest one to its left.
        mx = io.mouse_pos[0]
        store["segment"] = max([i for i, seg in enumerate(seg_boxes) if mx >= seg[0]] or [0])
        store["typed"] = ""
    focused = not disabled and ctx.is_nav_focused(item_id)
    segment = min(int(store.get("segment", 0)), count - 1)
    if hovered and io.mouse_wheel and not disabled:
        mx = io.mouse_pos[0]
        under = max([i for i, seg in enumerate(seg_boxes) if mx >= seg[0]] or [0])
        step = 1 if io.mouse_wheel > 0 else -1
        parts[under] = (parts[under] + step) % (limits[under] + 1)
        io.mouse_wheel = 0.0
        ctx.request_frame()
    if focused:
        for key, _mods in _take_keys(ctx, _TIME_KEYS):
            if key == KEY_LEFT:
                segment = max(0, segment - 1)
                store["typed"] = ""
            elif key == KEY_RIGHT:
                segment = min(count - 1, segment + 1)
                store["typed"] = ""
            elif key == KEY_HOME:
                segment, store["typed"] = 0, ""
            elif key == KEY_END:
                segment, store["typed"] = count - 1, ""
            elif key in (KEY_UP, KEY_DOWN, KEY_PAGE_UP, KEY_PAGE_DOWN):
                step = {KEY_UP: 1, KEY_DOWN: -1, KEY_PAGE_UP: 10, KEY_PAGE_DOWN: -10}[key]
                parts[segment] = (parts[segment] + step) % (limits[segment] + 1)
                store["typed"] = ""
            elif key == KEY_BACKSPACE:
                store["typed"] = ""
                parts[segment] = 0
        digits = "".join(ch for _key, text, _mods in io.key_events for ch in text if ch.isdigit())
        if not digits and io.text and io.text.isdigit():
            digits = io.text
        if digits:
            io.key_events[:] = [e for e in io.key_events if not (e[1] and e[1].isdigit())]
            io.text = ""
            io.key = 0
            for ch in digits:
                typed = store.get("typed", "") + ch
                number = int(typed)
                if number > limits[segment]:
                    typed, number = ch, int(ch)
                parts[segment] = number
                store["typed"] = typed
                # Two digits, or a first digit no second one could follow, finish the segment.
                if len(typed) == 2 or number * 10 > limits[segment]:
                    store["typed"] = ""
                    segment = min(count - 1, segment + 1) if segment < count - 1 else segment
            ctx.request_frame()
        ctx._want_text_input = True
    store["segment"] = segment
    new = _dt.time(parts[0], parts[1], parts[2] if seconds else 0, value.microsecond, value.tzinfo)
    if min_time is not None and new < min_time:
        new = min_time
    if max_time is not None and new > max_time:
        new = max_time
    changed = parts != original and new != value

    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]),
                             _w._col(Col.FRAME_BG_ACTIVE) if focused
                             else (_w._col(Col.FRAME_BG_HOVERED) if hovered else _w._col(Col.FRAME_BG)),
                             ctx.style.frame_rounding)
    _w._frame_border(ctx, box)
    shown = [new.hour, new.minute, new.second]
    text_y = box[1] + pad_y
    for index, seg in enumerate(seg_boxes):
        if focused and index == segment:
            ctx.draw.add_rect_filled((seg[0], seg[1]), (seg[0] + seg[2], seg[1] + seg[3]),
                                     _style.TEXT_SELECTED_BG)
        ctx.draw.add_text((seg[0] + 1.0, text_y), _w._col(Col.TEXT), "%02d" % shown[index])
        if index < count - 1:
            ctx.draw.add_text((seg[0] + seg[2] + 1.0, text_y), _w._col(Col.TEXT_DISABLED), ":")
    _w._nav_ring(ctx, box, item_id)
    ctx._last_item, ctx._last_id = box, item_id
    return changed, new


def _time_width(ctx, seconds: bool) -> float:
    count = 3 if seconds else 2
    return (2.0 * ctx.style.frame_padding[0] + count * (ctx.draw.calc_text_size("00")[0] + 2.0)
            + (count - 1) * (ctx.draw.calc_text_size(":")[0] + 2.0) + 2.0)


def time_input(label: str, value: _dt.time | None, seconds: bool = True,
               min_time: _dt.time | None = None,
               max_time: _dt.time | None = None) -> tuple[bool, _dt.time]:
    """A time field of hour / minute / second segments (``QTimeEdit``): ``(changed, time)``.

    A click picks the segment under it; with the keyboard focus, Left / Right
    (Home / End) move between segments, Up / Down step the segment by one and
    Page Up / Page Down by ten (wrapping, as a clock does), digits type it --
    two digits, or one no second could follow, move on to the next -- and
    Backspace zeroes it. The wheel steps the segment under the pointer. The
    result is clamped to ``[min_time, max_time]``.

    Parameters
    ----------
    label : str
        Caption and id.
    value : datetime.time or None
        ``None`` is midnight.
    seconds : bool
        Show and edit seconds (``HH:MM:SS``); ``False`` is ``HH:MM`` and zeroes them.
    min_time, max_time : datetime.time, optional
    """
    ctx = get_current_context()
    value = value if value is not None else _dt.time(0, 0, 0)
    if isinstance(value, _dt.datetime):
        value = value.time()
    shown = _w._visible_label(label)
    label_w = (ctx.draw.calc_text_size(shown)[0] + ctx.style.item_inner_spacing[0]) if shown else 0.0
    wanted = ctx.take_next_item_width(None)
    natural = _time_width(ctx, seconds)
    width = natural if wanted is None else max(natural, _w._labelled_item_width(ctx, wanted, label_w) - label_w)
    changed, value = _time_segments(ctx, ctx.get_id(label), value, width, seconds, min_time, max_time)
    last = (ctx._last_item, ctx._last_id)
    _draw_caption(ctx, shown)
    ctx._last_item, ctx._last_id = last
    return changed, value


def datetime_input(label: str, value: _dt.datetime | None, min_value: _dt.datetime | None = None,
                   max_value: _dt.datetime | None = None, seconds: bool = True, fmt: str | None = None,
                   first_weekday: int = 0,
                   today: _dt.date | None = None) -> tuple[bool, _dt.datetime | None]:
    """A date field and a time field on one row (``QDateTimeEdit``): ``(changed, datetime)``.

    The date half is :func:`date_input` (with its popup calendar), the time half
    :func:`time_input`; the combination is clamped to ``[min_value, max_value]``.
    ``None`` shows an empty date and midnight; picking a date makes it a value.
    The time zone of *value*, if it has one, is kept.
    """
    ctx = get_current_context()
    total, shown, label_w = _labelled(ctx, label)
    item_id = ctx.get_id(label)
    time_w = _time_width(ctx, seconds)
    spacing = ctx.style.item_inner_spacing[0]
    date_w = max(total - label_w - time_w - spacing, 40.0)
    day = value.date() if value is not None else None
    at = value.timetz() if value is not None else _dt.time(0, 0, 0)
    lo_day = min_value.date() if min_value is not None else None
    hi_day = max_value.date() if max_value is not None else None
    changed_day, day = _date_field(ctx, label, item_id, day, date_w, lo_day, hi_day, fmt,
                                   int(first_weekday) % 7, False, _as_date(today) or _dt.date.today())
    field = ctx._last_item
    _w.same_line(0.0, spacing)
    changed_time, at = _time_segments(ctx, (*item_id, "time"), at, time_w, seconds, None, None)
    if day is None:
        new = None
    else:
        new = _dt.datetime.combine(day, at)
        if min_value is not None and new < min_value:
            new = min_value
        if max_value is not None and new > max_value:
            new = max_value
    changed = (changed_day or changed_time) and new != value
    _draw_caption(ctx, shown)
    ctx._last_item = (field[0], field[1], ctx._last_item[0] - field[0], field[3]) if field else ctx._last_item
    ctx._last_id = item_id
    return changed, (new if changed else value)
