from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter
from emtk.widgets.text_editor import TextEditor


def test_a_previously_focused_editor_does_not_edit_while_disabled():
    editor = TextEditor("locked")
    storage = {}
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage,
                  io=IO(mouse_pos=(40, 10), mouse_clicked=[True, False, False])):
        im.text_editor("##source", editor, (300, 200))
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage, io=IO(text="x")):
        im.begin_disabled()
        im.text_editor("##source", editor, (300, 200))
        im.end_disabled()
    assert editor.text == "locked"
