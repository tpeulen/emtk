"""``value`` sections of ``kind`` date / time / datetime in an immediate-mode form."""
from __future__ import annotations

import datetime as dt

from emtk import im, keys, view_form
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form

SPEC = {"sections": [
    {"type": "value", "attr": "day", "label": "Acquired", "kind": "date",
     "minimum": "2026-10-05", "maximum": "2026-10-31", "description": "acquisition day"},
    {"type": "value", "attr": "start", "label": "Start", "kind": "time", "seconds": False,
     "description": "start time"},
    {"type": "value", "attr": "when", "label": "Scheduled", "kind": "datetime", "description": "run at"},
    {"type": "value", "attr": "iso", "label": "ISO day", "kind": "date", "description": "a string attr"},
]}


class Model:
    def __init__(self):
        self.day = dt.date(2026, 10, 19)
        self.start = dt.time(8, 30)
        self.when = dt.datetime(2026, 10, 19, 9, 15)
        self.iso = "2026-10-10"
        self.calls = []


class FormApp(ImApp):
    def __init__(self, model):
        super().__init__(self.gui)
        self.model = model
        self.form = FormState()

    def gui(self):
        im.begin("Form", (0, 0, 520, 420))
        draw_form(SPEC, self.model, self.form)
        im.end()


def _driven():
    model = Model()
    app = FormApp(model)
    driver = Driver(app, (520, 420))
    driver.draw(3)
    return model, app, driver


def test_the_dialect_declares_the_temporal_keys():
    for key in ("seconds", "first_weekday", "week_numbers", "date_format"):
        assert key in view_form.SECTION_KEYS["value"]


def test_format_and_parse_values_of_temporal_kinds():
    date_section = SPEC["sections"][0]
    assert view_form.format_value(dt.date(2026, 1, 2), date_section) == "2026-01-02"
    assert view_form.format_value(dt.time(8, 30, 15), SPEC["sections"][1]) == "08:30"
    assert view_form.format_value(dt.datetime(2026, 1, 2, 3, 4, 5), SPEC["sections"][2]) == "2026-01-02T03:04:05"
    assert view_form.parse_value("2026-10-01", date_section) == dt.date(2026, 10, 5)       # clamped
    assert view_form.parse_value("2026-11-30", date_section) == dt.date(2026, 10, 31)
    assert view_form.parse_value("nope", date_section) is None
    assert view_form.parse_value("07:45", SPEC["sections"][1]) == dt.time(7, 45)


def test_fields_show_the_model_values():
    _model, _app, driver = _driven()
    text = " ".join(driver.frame().strings)
    assert "2026-10-19" in text and "2026-10-10" in text
    assert "08" in text and "30" in text and "Acquired" in text


def test_picking_from_the_popup_calendar_writes_a_date():
    model, _app, driver = _driven()
    x, y, w, h = driver.rect("day")
    driver.click((x + w - 4, y + h / 2))
    driver.frame()
    driver.click("24")
    driver.frame()
    assert model.day == dt.date(2026, 10, 24)


def test_a_string_attribute_stays_a_string():
    model, _app, driver = _driven()
    x, y, w, h = driver.rect("iso")
    driver.click((x + w - 4, y + h / 2))
    driver.frame()
    driver.click("24")
    driver.frame()
    assert model.iso == "2026-10-24"


def test_time_field_steps_and_writes_back():
    model, _app, driver = _driven()
    x, y, _w, h = driver.rect("start")
    driver.click((x + 6, y + h / 2))
    driver.press(keys.KEY_UP)
    assert model.start == dt.time(9, 30)


def test_read_only_temporal_field_is_inert():
    spec = {"sections": [{"type": "value", "attr": "day", "label": "Day", "kind": "date", "read_only": True}]}
    model = Model()

    class App(ImApp):
        def __init__(self):
            super().__init__(self.gui)
            self.form = FormState()

        def gui(self):
            im.begin("Form", (0, 0, 400, 300))
            draw_form(spec, model, self.form)
            im.end()

    driver = Driver(App(), (400, 300))
    driver.draw(3)
    x, y, w, h = driver.rect("day")
    driver.click((x + w - 4, y + h / 2))
    driver.frame()
    assert "October 2026" not in driver.frame().strings
    assert model.day == dt.date(2026, 10, 19)
