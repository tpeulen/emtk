"""A spec ``value`` of ``kind: "text"`` is a multi-line field, committed on a click elsewhere.

AutoForm draws ``kind: "text"`` as a multi-line editor (notes, an address, a JSON
blob). ``emtk.view_form`` drew it as a single-line field, which also dropped every
newline of a value the user edited -- a port editing a stored multi-line record
corrupted it on the first keystroke.
"""

from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


class _Model:
    def __init__(self):
        self.notes = "first line\nsecond line"
        self.name = "probe"
        self.locked = "line a\nline b"
        self.writes = []

    def __setattr__(self, key, value):
        if key != "writes" and hasattr(self, "writes"):
            self.writes.append(key)
        object.__setattr__(self, key, value)


SPEC = {"sections": [
    {"type": "value", "attr": "notes", "label": "Notes", "kind": "text", "lines": 4,
     "description": "Free text"},
    {"type": "value", "attr": "name", "label": "Name", "kind": "str", "description": "A name"},
    {"type": "value", "attr": "locked", "label": "Locked", "kind": "text", "read_only": True,
     "description": "Read only"},
]}


class _Driver:
    def __init__(self, model):
        self.model = model
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0, 0, 500, 400), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 500, 400))
            draw_form(SPEC, self.model, self.state)
            emtk.end()

    def click(self, name):
        self.frame()
        x, y, w, h = self.state.rects[name]
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = (x + 5, y + h / 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        self.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        self.frame()


def test_a_text_field_is_taller_than_a_line_and_shows_every_line():
    driver = _Driver(_Model())
    driver.frame()
    notes = driver.state.rects["notes"]
    name = driver.state.rects["name"]
    assert notes[3] > 2.5 * name[3]
    strings = " ".join(driver.painter.strings)
    assert "first line" in strings and "second line" in strings


def test_typing_is_held_until_a_click_elsewhere_then_written_with_its_newlines():
    model = _Model()
    driver = _Driver(model)
    driver.click("notes")
    driver.io.text = "X"
    driver.frame()
    assert model.notes == "first line\nsecond line"  # not written while typing
    assert "notes" in driver.state.buffers
    driver.click("name")  # a click elsewhere commits
    assert "X" in model.notes
    assert "\n" in model.notes
    assert model.writes.count("notes") == 1


def test_a_read_only_text_field_takes_no_typing():
    model = _Model()
    driver = _Driver(model)
    driver.click("locked")
    driver.io.text = "Z"
    driver.frame()
    driver.click("name")
    assert model.locked == "line a\nline b"
    assert "locked" not in model.writes
