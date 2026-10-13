"""A ``value`` field's ``enter_call`` runs the form's action when Enter is pressed in it.

A login box logs in on Enter in its password field; a search box searches on Enter. ``call``
cannot say that: it runs on every commit, and a click elsewhere commits too, so a ``call``
of ``login`` would log in whenever the pointer left the field. ``enter_call`` runs only on
Enter, after the commit, and also when the text did not change.
"""

from __future__ import annotations

import emtk
from emtk import keys
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import SECTION_KEYS, FormState, draw_form


class _Model:
    def __init__(self):
        self.password = ""
        self.actions = []

    def login(self):
        self.actions.append(("login", self.password))


def _driver(read_only=False):
    model = _Model()
    form = FormState()
    spec = {"sections": [
        {"type": "value", "attr": "password", "label": "Password", "kind": "password",
         "enter_call": "login", "read_only": read_only},
        {"type": "info", "text": "Outside field"},
    ]}

    def gui():
        emtk.begin("form", (0, 0, 500, 250))
        draw_form(spec, model, form)
        emtk.end()

    app = ImApp(gui)
    app.form = form
    driver = Driver(app, (500, 250))
    driver.draw(2)
    return driver, model


def test_enter_commits_then_runs_the_action():
    driver, model = _driver()
    driver.click("password")
    driver.type("s3cret")
    driver.press(keys.KEY_RETURN)
    driver.draw(2)
    assert model.actions == [("login", "s3cret")]


def test_enter_on_unchanged_text_still_runs_the_action():
    driver, model = _driver()
    driver.click("password")
    driver.press(keys.KEY_RETURN)
    driver.draw(2)
    assert model.actions == [("login", "")]


def test_a_click_elsewhere_commits_without_the_action():
    driver, model = _driver()
    driver.click("password")
    driver.type("typed")
    driver.click("Outside field")
    driver.draw(2)
    assert model.password == "typed"
    assert model.actions == []


def test_a_read_only_field_runs_nothing():
    driver, model = _driver(read_only=True)
    driver.click("password")
    driver.press(keys.KEY_RETURN)
    driver.draw(2)
    assert model.actions == []


def test_enter_call_is_a_declared_value_key():
    assert {"enter_call", "live"} <= SECTION_KEYS["value"]


class _Search:
    def __init__(self):
        self.query = ""
        self.seen = []

    def typed(self, value):
        self.seen.append(value)


def _search_driver(live):
    model = _Search()
    form = FormState()
    spec = {"sections": [
        {"type": "value", "attr": "query", "label": "Search", "kind": "str", "call": "typed",
         "live": live},
        {"type": "info", "text": "Outside field"},
    ]}

    def gui():
        emtk.begin("form", (0, 0, 500, 250))
        draw_form(spec, model, form)
        emtk.end()

    app = ImApp(gui)
    app.form = form
    driver = Driver(app, (500, 250))
    driver.draw(2)
    return driver, model


def test_a_live_field_commits_while_typing():
    driver, model = _search_driver(live=True)
    driver.click("query")
    driver.type("ab")
    driver.draw(2)
    assert model.query == "ab"
    assert model.seen and model.seen[-1] == "ab"


def test_an_ordinary_field_waits_for_enter():
    driver, model = _search_driver(live=False)
    driver.click("query")
    driver.type("ab")
    driver.draw(2)
    assert model.query == "" and model.seen == []
