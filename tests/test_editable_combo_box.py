"""The editable combo box: a :class:`ComboBox` whose preview is a text field.

The fit Info page's *Sample* row is an editable combo in the Qt page: pick an
existing sample from the database or type a new sample id. emtk's
:class:`~emtk.widgets.combo.ComboBox` only selects. This control keeps the
popup for picking and swaps the preview for a
:class:`~emtk.widgets.text_field.TextField`, so typing works exactly as it
does in every other field here.
"""

from __future__ import annotations

from emtk import widgets
from emtk.testing import RecordingPainter


def test_typing_replaces_the_preview_and_fires_on_change():
    seen = []
    combo = widgets.EditableComboBox("", ["S1", "S2"], on_change=seen.append)
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    combo.press(60.0, 9.0, 0.0, 0.0, 200.0, 18.0)  # click the preview
    combo.key(0, "S", 0)
    combo.key(0, "9", 0)
    assert combo.text == "S9"
    assert combo.value == "S9", "the typed text is the current value"
    assert seen[-1] == "S9"


def test_picking_a_row_still_works_and_fills_the_field():
    seen = []
    combo = widgets.EditableComboBox("", ["S1", "S2"], on_change=seen.append)
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    press = combo.press(195.0, 9.0, 0.0, 0.0, 200.0, 18.0)  # the arrow half
    assert combo.open, "a press on the frame opens the list"
    assert press.consumed
    # The popup hangs below the frame; its geometry is recorded at *draw*
    # time, so draw again before hitting a row.
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    geo_x, top, list_w, row_h, _visible = combo._geometry
    result = combo.press(geo_x + list_w * 0.5, top + row_h * 1.5, 0.0, 0.0, 200.0, 18.0)
    assert result.index == 1
    assert result.changed
    assert not combo.open
    assert combo.text == "S2", "picking fills the field"
    assert combo.value == "S2"
    assert seen[-1] == "S2"


def test_backspace_edits_the_typed_text():
    combo = widgets.EditableComboBox("", ["S1"])
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    combo.press(60.0, 9.0, 0.0, 0.0, 200.0, 18.0)  # click the preview
    for ch in "abc":
        combo.key(0, ch, 0)
    from emtk.keys import KEY_BACKSPACE

    combo.key(KEY_BACKSPACE, "", 0)
    assert combo.text == "ab"


def test_paint_balances_its_clips_with_and_without_the_popup():
    combo = widgets.EditableComboBox("", ["S1", "S2", "S3"])
    painter = RecordingPainter()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.clips == []
    combo.open_popup()
    combo.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.clips == [], "an open popup must not leak clips"
