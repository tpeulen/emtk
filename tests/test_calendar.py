"""The calendar, and the date / time / date-time fields (``emtk.widgets.calendar``)."""
from __future__ import annotations

import datetime as dt

import pytest

from emtk import im, keys, theme
from emtk.app import ImApp
from emtk.events import ALT_MODIFIER, SHIFT_MODIFIER
from emtk.testing import Driver, render
from emtk.widgets import calendar as cal

TODAY = dt.date(2026, 10, 21)


def _has_colour(painter, box, colour) -> bool:
    """Whether any pixel inside *box* is *colour* (its RGB)."""
    x, y, w, h = (int(v) for v in box)
    want = bytes(tuple(colour)[:3])
    for yy in range(max(0, y), min(painter.height, y + h)):
        for xx in range(max(0, x), min(painter.width, x + w)):
            i = (yy * painter.width + xx) * 4
            if painter.px[i:i + 3] == want:
                return True
    return False


# --------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------- #
def test_month_grid_is_six_weeks_from_the_first_weekday():
    days = cal.month_grid(2026, 10)
    assert len(days) == 42
    assert days[0] == dt.date(2026, 9, 28) and days[0].weekday() == 0      # ISO: Monday first
    assert dt.date(2026, 10, 1) in days[:7]
    sunday_first = cal.month_grid(2026, 10, first_weekday=6)
    assert sunday_first[0] == dt.date(2026, 9, 27) and sunday_first[0].weekday() == 6


def test_month_grid_at_the_ends_of_the_representable_years():
    assert cal.month_grid(1, 1)[0] == dt.date(1, 1, 1)          # 1 January of year 1 is a Monday
    last = cal.month_grid(9999, 12)
    assert last[-1] is None and dt.date(9999, 12, 31) in last


def test_add_months_clamps_the_day_and_the_year():
    assert cal.add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)
    assert cal.add_months(dt.date(2024, 3, 31), -1) == dt.date(2024, 2, 29)
    assert cal.add_months(dt.date(2026, 11, 15), 14) == dt.date(2028, 1, 15)
    assert cal.add_months(dt.date(9999, 12, 1), 1) == dt.date(9999, 12, 1)
    assert cal.add_months(dt.date(1, 1, 1), -1) == dt.date(1, 1, 1)


def test_parse_and_format():
    assert cal.parse_date("2026-10-19") == dt.date(2026, 10, 19)
    assert cal.parse_date("19.10.2026") == dt.date(2026, 10, 19)
    assert cal.parse_date("2026/10/19") == dt.date(2026, 10, 19)
    assert cal.parse_date("10/19/26", "%m/%d/%y") == dt.date(2026, 10, 19)
    assert cal.parse_date("2026-02-30") is None and cal.parse_date("") is None
    assert cal.format_date(dt.date(2026, 1, 2)) == "2026-01-02"
    assert cal.format_date(dt.date(2026, 1, 2), "%d.%m.%Y") == "02.01.2026"
    assert cal.parse_time("14:30") == dt.time(14, 30)
    assert cal.parse_time("143005") == dt.time(14, 30, 5)
    assert cal.parse_time("25:00") is None
    assert cal.format_time(dt.time(9, 5, 7)) == "09:05:07"
    assert cal.format_time(dt.time(9, 5, 7), seconds=False) == "09:05"


def test_names_are_translated_through_the_emtk_domain():
    from emtk import i18n

    i18n.set_language("de")
    try:
        assert cal.month_name(3) == "März"
        assert cal.weekday_name(0) == "Mo"
    finally:
        i18n.set_language("en")
    assert cal.month_name(3) == "March" and cal.weekday_name(6) == "Sun"


# --------------------------------------------------------------------------- #
# The calendar, driven
# --------------------------------------------------------------------------- #
class CalendarApp(ImApp):
    def __init__(self, value=dt.date(2026, 10, 19), **kwargs):
        super().__init__(self.gui)
        self.value = value
        self.kwargs = kwargs
        self.changes = []
        self.cal_id = None

    def gui(self):
        im.begin("Cal", (0, 0, 400, 320))
        changed, self.value = im.calendar("##cal", self.value, today=TODAY, **self.kwargs)
        self.cal_id = im.get_item_id()
        self.remember("cal")
        if changed:
            self.changes.append(self.value)
        im.end()


def _driven(**kwargs):
    app = CalendarApp(**kwargs)
    driver = Driver(app, (400, 320))
    driver.draw(2)
    return app, driver


def _focus(app, driver):
    app.storage["__nav_id__"] = app.cal_id
    driver.frame()


def test_clicking_a_day_selects_it():
    app, driver = _driven()
    driver.click("24")
    assert app.value == dt.date(2026, 10, 24)
    assert app.changes == [dt.date(2026, 10, 24)]


def test_clicking_a_day_of_the_next_month_goes_there():
    app, driver = _driven()
    # The last row ends with November's first week; "8" is drawn once, as 8 November.
    driver.click("8")
    assert app.value == dt.date(2026, 11, 8)
    assert "November 2026" in driver.frame().strings


def test_month_arrows_and_wheel_move_the_view_not_the_value():
    app, driver = _driven()
    x, y, w, _h = driver.rect("cal")
    header_h = driver.rect("October 2026")[3]
    driver.click((x + w - 1.5 * header_h - 6, y + header_h / 2))  # "Next month" sits left of "Next year"
    assert "November 2026" in driver.frame().strings
    driver.wheel(1, at=(x + w / 2, y + 120))
    assert "October 2026" in driver.frame().strings
    assert app.value == dt.date(2026, 10, 19) and app.changes == []


def test_keyboard_moves_the_cursor_and_enter_selects():
    app, driver = _driven()
    _focus(app, driver)
    driver.press(keys.KEY_RIGHT)
    driver.press(keys.KEY_DOWN)
    assert app.value == dt.date(2026, 10, 19) and app.changes == []    # arrows only move
    driver.press(keys.KEY_RETURN)
    assert app.value == dt.date(2026, 10, 27)
    driver.press(keys.KEY_PAGE_DOWN)
    driver.press(keys.KEY_END)
    driver.press(keys.KEY_ENTER)
    assert app.value == dt.date(2026, 11, 30)
    driver.press(keys.KEY_HOME)
    driver.press(keys.KEY_PAGE_UP, SHIFT_MODIFIER)               # Shift: a year
    driver.press(keys.KEY_SPACE)
    assert app.value == dt.date(2025, 11, 1)
    assert "November 2025" in driver.frame().strings


def test_keys_are_spent_by_the_focused_calendar_only():
    app, driver = _driven()
    driver.press(keys.KEY_RIGHT)
    driver.press(keys.KEY_RETURN)
    assert app.changes == []


def test_bounds_make_days_inert_and_hold_the_cursor():
    lo, hi = dt.date(2026, 10, 5), dt.date(2026, 10, 25)
    app, driver = _driven(min_date=lo, max_date=hi)
    driver.click("3")                       # before min_date: shown, but inert
    assert app.value == dt.date(2026, 10, 19)
    driver.click("28")
    assert app.value == dt.date(2026, 10, 19)
    _focus(app, driver)
    for _ in range(3):
        driver.press(keys.KEY_DOWN)         # 19 -> 26 is past max: the cursor stops at the bound
    driver.press(keys.KEY_RETURN)
    assert app.value == hi
    driver.press(keys.KEY_PAGE_UP)          # September is wholly outside: the cursor clamps to min
    driver.press(keys.KEY_RETURN)
    assert app.value == lo
    assert "October 2026" in driver.frame().strings


def test_month_arrows_stop_at_the_bounds():
    _app, driver = _driven(min_date=dt.date(2026, 10, 1), max_date=dt.date(2026, 10, 31))
    x, y, w, _h = driver.rect("cal")
    header_h = driver.rect("October 2026")[3]
    for target in ((x + 4, y + header_h / 2), (x + w - 4, y + header_h / 2)):
        driver.click(target)
        assert "October 2026" in driver.frame().strings


def test_week_numbers_and_first_weekday():
    _app, driver = _driven(show_week_numbers=True, first_weekday=6)
    strings = driver.frame().strings
    assert "Wk" in strings and "43" in strings
    names = [s for s in strings if s in ("Sun", "Mon", "Sat")]
    assert names[0] == "Sun"


def test_a_tooltip_names_the_day_under_the_pointer(monkeypatch):
    said = []
    monkeypatch.setattr(cal._w, "set_tooltip", lambda text: said.append(text))
    _app, driver = _driven()
    driver.hover("24")
    assert "Sat, 24 October 2026" in said
    said.clear()
    driver.hover((5, 315))
    assert not said


def test_selected_day_and_today_take_the_theme_colours():
    for name in ("dark", "light"):
        theme.apply_theme(name)
        try:
            rects = {}

            def gui():
                im.begin("c", (0, 0, 320, 260))
                im.calendar("##c", dt.date(2026, 10, 19), today=TODAY)
                rects["c"] = im.get_item_rect()
                rects["fill"] = im.get_style().color(im.Col.HEADER_ACTIVE)
                rects["today"] = im.get_style().color(im.Col.CHECK_MARK)
                im.end()

            painter = render(gui, (0, 0, 320, 260))
            assert _has_colour(painter, rects["c"], rects["fill"])
            assert _has_colour(painter, rects["c"], rects["today"])
        finally:
            theme.apply_theme("dark")


def test_disabled_calendar_is_inert():
    state = {"value": dt.date(2026, 10, 19)}

    def gui():
        im.begin("c", (0, 0, 400, 320))
        im.begin_disabled(True)
        _c, state["value"] = im.calendar("##c", state["value"], today=TODAY)
        im.end_disabled()
        im.end()

    driver = Driver(gui, (400, 320))
    driver.draw(2)
    driver.click("24")
    assert state["value"] == dt.date(2026, 10, 19)


# --------------------------------------------------------------------------- #
# The date field
# --------------------------------------------------------------------------- #
class FieldApp(ImApp):
    def __init__(self, value=dt.date(2026, 10, 3), **kwargs):
        super().__init__(self.gui)
        self.value = value
        self.kwargs = kwargs
        self.changes = []
        self.clicked_below = 0

    def gui(self):
        im.begin("Dates", (0, 0, 420, 360))
        im.set_next_item_width(220)
        changed, self.value = im.date_input("Acquired", self.value, today=TODAY, **self.kwargs)
        self.remember("field")
        self.field_id = im.get_item_id()
        if changed:
            self.changes.append(self.value)
        if im.button("Below"):
            self.clicked_below += 1
        self.remember("below")
        im.end()


def _field(**kwargs):
    app = FieldApp(**kwargs)
    driver = Driver(app, (420, 360))
    driver.draw(2)
    return app, driver


def _open(driver):
    x, y, w, h = driver.rect("field")
    driver.click((x + w - 4, y + h / 2))        # the calendar button at the field's right end
    driver.frame()


def test_the_button_opens_a_calendar_and_a_pick_closes_it():
    app, driver = _field()
    _open(driver)
    assert "October 2026" in driver.frame().strings
    driver.click("24")
    driver.frame()
    assert app.value == dt.date(2026, 10, 24) and app.changes == [dt.date(2026, 10, 24)]
    assert "October 2026" not in driver.frame().strings


def test_the_popup_holds_the_pointer_and_escape_closes_it():
    app, driver = _field()
    _open(driver)
    driver.escape()
    driver.frame()
    assert "October 2026" not in driver.frame().strings
    assert app.value == dt.date(2026, 10, 3)


def test_a_click_outside_closes_the_popup_without_picking():
    app, driver = _field()
    _open(driver)
    driver.click((410, 350))
    driver.frame()
    assert "October 2026" not in driver.frame().strings
    assert app.changes == []


def test_keyboard_opens_the_popup_and_picks():
    app, driver = _field()
    app.storage["__nav_id__"] = app.field_id
    driver.frame()
    driver.press(keys.KEY_DOWN, ALT_MODIFIER)
    driver.frame()
    assert "October 2026" in driver.frame().strings
    driver.press(keys.KEY_RIGHT)
    driver.press(keys.KEY_RETURN)
    driver.frame()
    assert app.value == dt.date(2026, 10, 4)


def test_typing_a_date_commits_on_enter_and_a_typo_keeps_the_value():
    app, driver = _field(max_date=dt.date(2026, 12, 31))
    x, y, _w, h = driver.rect("field")
    driver.click((x + 20, y + h / 2))
    driver.press(keys.KEY_END)
    for _ in range(12):
        driver.press(keys.KEY_BACKSPACE)
    driver.type("2026-11-05")
    driver.press(keys.KEY_RETURN)
    assert app.value == dt.date(2026, 11, 5)
    for _ in range(12):
        driver.press(keys.KEY_BACKSPACE)
    driver.type("2027-01-09")                   # past max_date: clamped
    driver.press(keys.KEY_RETURN)
    assert app.value == dt.date(2026, 12, 31)
    for _ in range(12):
        driver.press(keys.KEY_BACKSPACE)
    driver.type("not a date")
    driver.press(keys.KEY_RETURN)
    assert app.value == dt.date(2026, 12, 31)


def test_set_item_tooltip_after_a_date_input_speaks_of_the_field(monkeypatch):
    said = []
    monkeypatch.setattr(im, "set_tooltip", lambda text: said.append(text))
    import emtk.im_widgets as widgets
    monkeypatch.setattr(widgets, "set_tooltip", lambda text: said.append(text))

    class App(ImApp):
        def __init__(self):
            super().__init__(self.gui)

        def gui(self):
            im.begin("w", (0, 0, 300, 100))
            im.date_input("When", dt.date(2026, 1, 1))
            self.remember("field")
            im.set_item_tooltip("the day it was measured")
            im.end()

    driver = Driver(App(), (300, 100))
    driver.draw(2)
    x, y, _w, h = driver.rect("field")
    driver.hover((x + 10, y + h / 2))
    assert "the day it was measured" in said


# --------------------------------------------------------------------------- #
# Time and date-time
# --------------------------------------------------------------------------- #
class TimeApp(ImApp):
    def __init__(self, value=dt.time(14, 30, 5), **kwargs):
        super().__init__(self.gui)
        self.value = value
        self.kwargs = kwargs

    def gui(self):
        im.begin("T", (0, 0, 300, 120))
        _c, self.value = im.time_input("Start", self.value, **self.kwargs)
        self.remember("time")
        im.end()


def test_time_segments_step_type_and_wrap():
    app = TimeApp()
    driver = Driver(app, (300, 120))
    driver.draw(2)
    x, y, _w, h = driver.rect("time")
    driver.click((x + 8, y + h / 2))              # the hour segment
    driver.press(keys.KEY_UP)
    assert app.value == dt.time(15, 30, 5)
    driver.press(keys.KEY_RIGHT)
    driver.press(keys.KEY_PAGE_UP)
    driver.press(keys.KEY_PAGE_UP)
    driver.press(keys.KEY_PAGE_UP)                 # 30 + 30 = 60 wraps to 0
    assert app.value == dt.time(15, 0, 5)
    driver.press(keys.KEY_LEFT)
    driver.type("09")                              # two digits finish the hour, focus moves on
    driver.type("7")                               # 7: no second digit could follow -> minute 07
    assert app.value == dt.time(9, 7, 5)
    driver.press(keys.KEY_DOWN)
    driver.press(keys.KEY_DOWN)                    # the seconds now: 5 -> 3
    assert app.value == dt.time(9, 7, 3)


def test_time_bounds_and_minutes_only():
    app = TimeApp(value=dt.time(8, 0), seconds=False, min_time=dt.time(8, 0), max_time=dt.time(18, 0))
    driver = Driver(app, (300, 120))
    driver.draw(2)
    x, y, _w, h = driver.rect("time")
    driver.click((x + 8, y + h / 2))
    driver.press(keys.KEY_DOWN)                    # 07:00 is before min_time
    assert app.value == dt.time(8, 0)
    driver.type("23")
    assert app.value == dt.time(18, 0)
    assert "05" not in driver.frame().strings


def test_datetime_input_combines_both_halves():
    state = {"value": dt.datetime(2026, 10, 19, 9, 15, tzinfo=dt.timezone.utc), "n": 0}

    class App(ImApp):
        def __init__(self):
            super().__init__(self.gui)

        def gui(self):
            im.begin("D", (0, 0, 420, 360))
            changed, state["value"] = im.datetime_input("Scheduled", state["value"], today=TODAY)
            state["n"] += changed
            self.remember("dt")
            im.end()

    app = App()
    driver = Driver(app, (420, 360))
    driver.draw(2)
    _x, y, _w, h = driver.rect("dt")
    strings = driver.frame().strings
    assert "2026-10-19" in "".join(strings) and "09" in strings and "15" in strings
    time_x = [t for t in driver.painter.texts if t[5] == "09"][0][0]
    driver.click((time_x - 6, y + h / 2))          # the calendar button just left of the time
    driver.frame()
    driver.click("24")
    driver.frame()
    assert state["value"] == dt.datetime(2026, 10, 24, 9, 15, tzinfo=dt.timezone.utc)
    assert state["n"] == 1


# --------------------------------------------------------------------------- #
# Style sheet
# --------------------------------------------------------------------------- #
def test_stylesheet_parts():
    assert cal.stylesheet_part("calendar::day:selected", "background-color") == "day_selected"
    assert cal.stylesheet_part("calendar:day:selected", "background") == "day_selected"
    assert cal.stylesheet_part("QCalendarWidget", "background-color") == "background"
    assert cal.stylesheet_part("calendar::day:today", "border-color") == "today"
    assert cal.stylesheet_part("button", "background") is None
    assert cal.stylesheet_part("calendar::day", "font-size") is None
    with pytest.raises(KeyError):
        cal.use_stylesheet("x", {"nonsense": (1, 2, 3, 255)})


def test_stylesheet_colours_apply_only_under_their_theme():
    rects = {}
    magenta = (250, 0, 250, 255)

    def gui():
        im.begin("c", (0, 0, 320, 260))
        im.calendar("##c", dt.date(2026, 10, 19), today=TODAY)
        rects["c"] = im.get_item_rect()
        im.end()

    current = theme.current_theme()
    try:
        cal.use_stylesheet(current, {"day_selected": magenta})
        assert _has_colour(render(gui, (0, 0, 320, 260)), rects["c"], magenta)
        cal.use_stylesheet("some other sheet", {"day_selected": magenta})
        assert not _has_colour(render(gui, (0, 0, 320, 260)), rects["c"], magenta)
    finally:
        cal.use_stylesheet(None, None)


def test_a_style_sheet_rule_reaches_the_calendar():
    """``calendar::day:selected { ... }`` in a CSS/QSS sheet colours the selected day."""
    stylesheet = pytest.importorskip("emtk.stylesheet")
    if not hasattr(stylesheet, "_calendar_rules"):
        pytest.skip("this emtk.stylesheet predates the calendar selectors")
    try:
        name = stylesheet.apply_stylesheet(
            "calendar::day:selected { background-color: #fa00fa; }\n"
            "calendar::header { background: rgb(10, 20, 30); }", name="calendar-test")
        sheet_theme, colours = cal._SHEET
        assert sheet_theme == name
        assert colours == {"day_selected": (250, 0, 250, 255), "header": (10, 20, 30, 255)}
    finally:
        theme.apply_theme("dark")
        cal.use_stylesheet(None, None)
