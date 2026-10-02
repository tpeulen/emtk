from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def test_password_masks_display_and_retains_edited_value():
    storage = {}
    value = "secret"
    for io in (None, IO(mouse_pos=(20, 10), mouse_clicked=[True, False, False]), IO(text="x")):
        painter = RecordingPainter()
        with im.frame(painter, (0, 0, 400, 100), io=io, storage=storage):
            _, value = im.input_text("##password", value, flags=im.InputTextFlags.PASSWORD)
        assert "secret" not in "\n".join(painter.strings)
        assert any(set(text) == {"*"} for text in painter.strings if text)
    assert "x" in value
