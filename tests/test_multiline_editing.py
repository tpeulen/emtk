from emtk import im
from emtk.events import CONTROL_MODIFIER
from emtk.im_core import IO, get_current_context
from emtk.keys import KEY_BACKSPACE
from emtk.testing import RecordingPainter


def test_multiline_fills_width_and_supports_selection_replacement():
    storage = {}
    value = "first\nsecond"

    def draw(io=None):
        nonlocal value
        with im.frame(RecordingPainter(), (0, 0, 400, 250), storage=storage, io=io):
            _, value = im.input_text_multiline("##notes", value, (0, 140))
            return get_current_context().get_item_rect()

    box = draw()
    assert box[2] >= 390
    draw(IO(mouse_pos=(30, 20), mouse_clicked=[True, False, False]))
    draw(IO(key_events=[(ord("a"), "", CONTROL_MODIFIER)]))
    draw(IO(text="replacement"))
    assert value == "replacement"
    draw(IO(key=KEY_BACKSPACE))
    assert value == "replacemen"
