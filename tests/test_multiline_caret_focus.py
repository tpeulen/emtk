"""A multi-line form field draws its caret only while it has the focus.

Without this every unfocused (and every read-only) multi-line box showed a
caret at its first character, as if typing would land there.
"""
from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def _carets(painter):
    # The caret is a 1 px wide bar 0.8 lines high (TextEditor._draw_carets).
    line = RecordingPainter.LINE_H
    return [f for f in painter.fills if f[2] <= 1.5 and abs(f[3] - 0.8 * line) < 0.5]


def _frame(storage, io=None, disabled=False):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 400, 250), storage=storage, io=io):
        if disabled:
            im.begin_disabled(True)
        im.input_text_multiline("##notes", "first\nsecond", (0, 120))
        if disabled:
            im.end_disabled()
        im.button("elsewhere")
    return painter


def test_no_caret_until_clicked_and_no_caret_or_typing_after_clicking_away():
    storage = {}
    assert not _carets(_frame(storage))
    _frame(storage, IO(mouse_pos=(30, 20), mouse_clicked=[True, False, False]))
    assert _carets(_frame(storage))
    # A click anywhere else ends the editing: no caret, and typing goes nowhere.
    _frame(storage, IO(mouse_pos=(300, 200), mouse_clicked=[True, False, False]))
    painter = _frame(storage, IO(text="typed"))
    assert not _carets(painter)
    assert "typed" not in "".join(painter.strings)


def test_a_read_only_box_never_shows_a_caret():
    storage = {}
    _frame(storage, IO(mouse_pos=(30, 20), mouse_clicked=[True, False, False]), disabled=True)
    assert not _carets(_frame(storage, disabled=True))
