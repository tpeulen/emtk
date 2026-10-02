from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter
from emtk.widgets.text_editor import TextEditor


def test_each_edit_reports_a_change_even_when_buffer_already_modified():
    editor = TextEditor("")
    storage = {}
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage,
                  io=IO(mouse_pos=(40, 10), mouse_clicked=[True, False, False])):
        im.text_editor("##source", editor, (300, 200))
    for character in ("a", "b"):
        with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage, io=IO(text=character)):
            assert im.text_editor("##source", editor, (300, 200))
    assert editor.text == "ab"
