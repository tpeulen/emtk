"""``emtk.view_form`` -- an AutoForm view spec drawn as an immediate-mode form.

Driven the way a user drives a form: by clicking what was drawn and typing into
it. No window, no toolkit.
"""
from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form, find_section, format_value, parse_value


class Model:
    """A dialog's model: plain attributes, one action, the two hooks."""

    def __init__(self):
        self.method = "Manual"
        self.don = False
        self.don_value = 0.0
        self.restarts = 2
        self.series = 1
        self.pressed = []
        self.series_max = 10

    def ok(self):
        self.pressed.append("ok")

    def cancel(self):
        self.pressed.append("cancel")

    def enabled(self, name):
        if name == "don_value":
            return self.don
        return True

    def bounds(self, name):
        if name == "series":
            return (1, self.series_max)
        return None


SPEC = {
    "sections": [
        {"type": "panel", "title": "Thresholds", "sections": [
            {"type": "choice", "attr": "method", "label": "Threshold",
             "options": ["Manual", "Auto"], "description": "How to find the bleach"},
            {"type": "toggle", "attr": "don", "label": "Donor"},
            {"type": "value", "attr": "don_value", "label": "", "kind": "float"},
        ]},
        {"type": "panel", "title": "Run", "n_col": 2, "sections": [
            {"type": "value", "attr": "restarts", "label": "Restarts", "kind": "int",
             "minimum": 0, "maximum": 10},
            {"type": "value", "attr": "series", "label": "Series", "kind": "int",
             "style": "slider"},
        ]},
        {"type": "panel", "title": "Hidden", "hidden_when": {"attr": "method", "equals": "Auto"},
         "sections": [{"type": "info", "text": "only in manual mode"}]},
        {"type": "button_row", "buttons": [{"label": "Ok", "action": "ok"},
                                           {"label": "Cancel", "action": "cancel"}]},
    ]
}


class Driver:
    def __init__(self, spec, model):
        self.spec, self.model = spec, model
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0, 0, 500, 400), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 500, 400))
            draw_form(self.spec, self.model, self.state)
            emtk.end()

    def click(self, name):
        self.frame()
        x, y, w, h = self.state.rects[name]
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = (x + 3, y + h / 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        self.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        self.frame()

    def type(self, name, text, enter=True):
        self.click(name)
        self.io.text = text
        self.frame()
        if enter:
            self.io.key = 0x01000004
            self.frame()


def test_numbers_are_spelled_the_way_the_spec_asks():
    assert format_value(0.05, {"kind": "float"}) == "0.05"
    assert format_value(1e-3, {"kind": "float", "style": "scientific", "decimals": 1}) == "1.0e-03"
    assert format_value(2.0, {"kind": "int"}) == "2"
    assert format_value(0.5, {"kind": "float", "decimals": 3}) == "0.500"


def test_what_was_typed_is_parsed_and_clamped_or_refused():
    section = {"kind": "int", "minimum": 0, "maximum": 10}
    assert parse_value("12", section) == 10
    assert parse_value("3.6", section) == 4
    assert parse_value("abc", section) is None
    assert parse_value("5", {"kind": "float"}, bounds=(0, 1)) == 1.0


def test_every_control_is_drawn_with_its_label():
    driver = Driver(SPEC, Model())
    driver.frame()
    for text in ("Thresholds", "Threshold", "Donor", "Restarts", "Series", "Ok", "Cancel",
                 "only in manual mode"):
        assert text in driver.painter.strings, text
    for name in ("method", "don", "don_value", "restarts", "series.edit", "series.slider",
                 "ok", "cancel"):
        assert name in driver.state.rects, name


def test_fields_packed_by_n_col_share_a_line():
    driver = Driver(SPEC, Model())
    driver.frame()
    restarts, series = driver.state.rects["restarts"], driver.state.rects["series.edit"]
    assert abs(restarts[1] - series[1]) < 1.0
    assert series[0] > restarts[0] + restarts[2]


def test_typing_commits_on_enter_and_clamps():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("restarts", "0")  # typed after the existing "2" -> "20", clamped to 10
    assert model.restarts == 10


def test_nothing_is_written_until_the_edit_is_committed():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("restarts", "5", enter=False)
    assert model.restarts == 2
    driver.click("don")          # the pointer goes down elsewhere: commit
    assert model.restarts == 10  # "25" clamped


def test_a_toggle_writes_its_attribute_and_enables_what_depends_on_it():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("don_value", "5")
    assert model.don_value == 0.0, "a disabled field must not accept typing"
    driver.click("don")
    assert model.don is True
    driver.type("don_value", "5")
    assert model.don_value == 5.0


def test_a_choice_asks_the_host_for_its_list_and_takes_the_pick():
    model = Model()
    driver = Driver(SPEC, model)
    driver.click("method")
    name, _rect, labels, index = driver.state.dropdown_request
    assert (name, labels, index) == ("method", ["Manual", "Auto"], 0)
    driver.state.dropdown_result["method"] = 1
    driver.frame()
    assert model.method == "Auto"
    driver.frame()
    assert "only in manual mode" not in driver.painter.strings, "hidden_when must hide it"


def test_buttons_call_their_action_and_report_use():
    model = Model()
    driver = Driver(SPEC, model)
    used = []
    driver.state.on_used = used.append
    driver.click("ok")
    assert model.pressed == ["ok"]
    assert "ok" in used


def test_a_slider_takes_its_range_from_the_model():
    model = Model()
    model.series_max = 3
    driver = Driver(SPEC, model)
    driver.type("series.edit", "9")  # "19" clamped to the run-time maximum
    assert model.series == 3


def test_find_section_finds_a_panel_by_title():
    assert find_section(SPEC, "Run")["n_col"] == 2
    assert find_section(SPEC, "missing") is None


def test_fields_of_a_panel_line_up_in_columns():
    """Labels of different lengths must not push their fields to different x."""
    spec = {"sections": [{"type": "panel", "n_col": 1, "sections": [
        {"type": "value", "attr": "restarts", "label": "Min Center", "kind": "int"},
        {"type": "value", "attr": "series", "label": "Dwell", "kind": "int"},
    ]}]}
    driver = Driver(spec, Model())
    driver.frame()
    first, second = driver.state.rects["restarts"], driver.state.rects["series"]
    assert abs(first[0] - second[0]) < 0.5
    assert second[1] > first[1]
