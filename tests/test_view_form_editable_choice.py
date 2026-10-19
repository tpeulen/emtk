"""A spec ``choice`` with ``editable: true`` takes a typed value or a picked one.

A licence, a unit, an instrument name: a short list covers most answers, not all.
A plain ``choice`` cannot hold a value outside its options, and a ``value`` offers
none -- Qt's editable QComboBox is both, and so is this.
"""

from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form

SPEC = {"sections": [
    {"type": "choice", "attr": "license", "label": "License", "editable": True,
     "options": ["cc-by-4.0", "cc0-1.0", "mit"], "description": "A licence id"},
    {"type": "value", "attr": "other", "label": "Other", "kind": "str", "description": "d"},
]}


class _Model:
    license = "odbl-1.0"   # not among the options
    other = "x"


class _Driver:
    def __init__(self, model):
        self.model = model
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0, 0, 500, 300), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 500, 300))
            draw_form(SPEC, self.model, self.state)
            emtk.end()

    def click(self, name):
        self.frame()
        x, y, w, h = self.state.rects[name]
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = (x + w / 2, y + h / 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        self.frame()
        io.mouse_down[0] = io.mouse_clicked[0] = False
        io.mouse_released[0] = True
        self.frame()
        io.mouse_released[0] = False


def test_a_value_outside_the_options_is_shown_as_it_is():
    driver = _Driver(_Model())
    driver.frame()
    driver.frame()
    assert "odbl-1.0" in " ".join(driver.painter.strings)
    assert "license.arrow" in driver.state.rects


def test_typed_text_is_written_on_a_click_elsewhere():
    model = _Model()
    driver = _Driver(model)
    driver.click("license")
    driver.io.text = "X"
    driver.frame()
    driver.io.text = ""
    assert model.license == "odbl-1.0"
    driver.click("other")
    assert model.license != "odbl-1.0" and "X" in model.license


def test_the_arrow_opens_the_options_and_a_pick_is_written():
    model = _Model()
    driver = _Driver(model)
    driver.click("license.arrow")
    rows = {t[5]: t for t in driver.painter.texts}
    assert {"cc-by-4.0", "cc0-1.0", "mit"} <= set(rows), "the arrow opened no list"
    x, y, w, h = rows["mit"][:4]
    io = driver.io
    io.mouse_pos = io.mouse_clicked_pos[0] = (x + 2, y + h / 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    driver.frame()
    io.mouse_down[0] = io.mouse_clicked[0] = False
    io.mouse_released[0] = True
    driver.frame()
    io.mouse_released[0] = False
    driver.frame()
    assert model.license == "mit"
