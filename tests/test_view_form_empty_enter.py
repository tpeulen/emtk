"""Keyboard commits include the empty string and preserve value semantics."""

from __future__ import annotations

import emtk
import pytest
from emtk import keys
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER
from emtk.flags import InputTextFlags
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form


class _Model:
    """Track callbacks independently of the editable attribute."""

    def __init__(self, value):
        self.value = value
        self.calls = []

    def changed(self, value):
        """Record each successful value commit."""
        self.calls.append(value)


def _driver(value="fraction", *, kind="str", read_only=False):
    """Build a real Driver over the single-line AutoForm field."""
    model = _Model(value)
    used = []
    form = FormState(on_used=used.append)
    spec = {"sections": [{"type": "value", "key": "filter.alias", "attr": "value",
                           "label": "Filter", "kind": kind, "call": "changed",
                           "read_only": read_only},
                          {"type": "info", "text": "Outside field"}]}

    def gui():
        """Draw the declarative field inside an immediate-mode window."""
        emtk.begin("form", (0, 0, 500, 250))
        draw_form(spec, model, form)
        emtk.end()

    app = ImApp(gui)
    app.form = form
    driver = Driver(app, (500, 250))
    driver.draw(2)
    return driver, model, form, used


def _empty(driver):
    """Select and delete the field through host keyboard events."""
    driver.click("value")
    driver.press(ord("A"), CONTROL_MODIFIER)
    driver.press(keys.KEY_BACKSPACE)


@pytest.mark.parametrize("key", [keys.KEY_RETURN, keys.KEY_ENTER, 13])
def test_empty_string_enter_commits_once_with_binding_alias(key):
    """Enter writes an intentional empty string and calls both hooks once."""
    driver, model, form, used = _driver()
    _empty(driver)
    assert model.value == "fraction"
    assert form.buffers["value"] == ""
    driver.press(key)
    assert model.value == "" and model.calls == [""] and used == ["value"]
    driver.draw(3)
    driver.click("Outside field")
    assert model.value == ""
    assert model.calls == [""]
    assert used == ["value"]
    assert "value" not in form.buffers


@pytest.mark.parametrize("value", ["fraction", ""])
def test_unchanged_enter_does_not_call_hooks(value):
    """Pressing Enter without an edit is not a value change."""
    driver, model, form, used = _driver(value)
    driver.click("value")
    driver.press(keys.KEY_RETURN)
    driver.draw(2)
    assert model.value == value and model.calls == [] and used == []
    assert form.buffers == {}


def test_escape_restores_original_and_cancels_empty_buffer():
    """Escape cancels the edit before later Enter or click-away can commit it."""
    driver, model, form, used = _driver()
    _empty(driver)
    driver.escape()
    driver.press(keys.KEY_RETURN)
    assert form.buffers == {}
    driver.click("Outside field")
    driver.draw(2)
    assert model.value == "fraction" and model.calls == [] and used == []
    assert form.buffers == {}
    assert "fraction" in driver.painter.strings


def test_read_only_cannot_be_emptied_or_committed():
    """Keyboard input leaves a read-only field and its callbacks unchanged."""
    driver, model, form, used = _driver(read_only=True)
    _empty(driver)
    driver.press(keys.KEY_RETURN)
    driver.click("Outside field")
    assert model.value == "fraction" and model.calls == [] and used == []
    assert form.buffers == {}


@pytest.mark.parametrize("kind,value", [("int", 23), ("float", 2.5)])
def test_empty_numeric_enter_rejects_edit_and_retains_original(kind, value):
    """An empty number remains invalid rather than becoming zero or a string."""
    driver, model, form, used = _driver(value, kind=kind)
    _empty(driver)
    driver.press(keys.KEY_RETURN)
    assert form.buffers == {}
    assert model.value == value and model.calls == [] and used == []
    driver.click("Outside field")
    assert model.value == value and model.calls == [] and used == []
    assert form.buffers == {}


@pytest.mark.parametrize("key", [keys.KEY_RETURN, keys.KEY_ENTER, 13])
def test_input_text_enter_reports_submission_even_when_empty(key):
    """The widget submission flag describes Enter rather than text truthiness."""
    events = []

    def gui():
        """Draw an initially empty raw widget using its hidden identifier."""
        emtk.begin("widget", (0, 0, 500, 250))
        entered, text = emtk.input_text("Filter##hidden", "", flags=InputTextFlags.ENTER_RETURNS_TRUE)
        app.remember("field")
        events.append((entered, text))
        emtk.end()

    app = ImApp(gui)
    driver = Driver(app, (500, 250))
    driver.draw(2)
    driver.click("field")
    driver.key(key)
    assert events[-1] == (True, "")
    driver.frame()
    assert events[-1] == (False, "")
