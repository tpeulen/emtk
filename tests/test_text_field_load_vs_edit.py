"""A field tells its owner about *edits*, never about *loads*.

``TextField.on_change`` is "called with the new text after every edit".
``set_text`` replaces the contents and forgets the undo history -- it is how an
owner loads a value it read from a document, not something the user did. Firing
``on_change`` for it made every owner that persists edits write back what it had
just read, and fire during its own construction, before the rest of it existed
(ChiSurf's fit Info page called its save handler before its metadata editor was
built). Qt draws the same line: ``textEdited`` for the user, ``setText`` silent.
"""

from __future__ import annotations

from emtk import widgets
from emtk.keys import KEY_BACKSPACE
from emtk.testing import RecordingPainter
from emtk.widgets.text_field import TextField


def test_set_text_is_a_load_and_does_not_fire_on_change():
    seen = []
    field = TextField(on_change=seen.append)
    field.set_text("loaded")
    assert field.text == "loaded"
    assert seen == []


def test_user_edits_still_fire_on_change():
    seen = []
    field = TextField(on_change=seen.append)
    field.set_text("ab")
    field.insert("c")
    assert seen == ["abc"]
    field.key(KEY_BACKSPACE)
    assert seen == ["abc", "ab"]


def test_editable_combo_construction_and_set_text_are_silent():
    seen = []
    combo = widgets.EditableComboBox("", ["S1", "S2"], index=1, on_change=seen.append)
    assert combo.text == "S2"
    combo.set_text("S7")
    assert combo.text == "S7"
    assert seen == [], "a document load is not the user typing"


def test_editable_combo_pick_reports_once():
    seen = []
    combo = widgets.EditableComboBox("", ["S1", "S2"], on_change=seen.append)
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    combo.press(195.0, 9.0, 0.0, 0.0, 200.0, 18.0)
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    geo_x, top, list_w, row_h, _visible = combo._geometry
    combo.press(geo_x + list_w * 0.5, top + row_h * 1.5, 0.0, 0.0, 200.0, 18.0)
    assert seen == ["S2"]


def test_editable_combo_typing_reports_each_edit():
    seen = []
    combo = widgets.EditableComboBox("", ["S1"], on_change=seen.append)
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    combo.press(60.0, 9.0, 0.0, 0.0, 200.0, 18.0)
    combo.set_text("")
    combo.key(0, "x", 0)
    combo.key(KEY_BACKSPACE, "", 0)
    assert seen == ["x", ""]
