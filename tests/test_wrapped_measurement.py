from emtk import im
from emtk.im_core import get_current_context
from emtk.testing import RecordingPainter


def test_wrapped_measurement_matches_the_rendered_text_block():
    with im.frame(RecordingPainter(), (0, 0, 100, 300)):
        width, height = im.calc_text_size("some useful text", wrap_width=100)
        im.text_wrapped("some useful text")
        box = get_current_context().get_item_rect()
    assert width <= 100
    assert height == box[3] == 32


def test_unbroken_word_wraps_inside_available_width():
    with im.frame(RecordingPainter(), (0, 0, 70, 300)):
        width, height = im.calc_text_size("abcdefghijklmnopqrst", wrap_width=70)
    assert width <= 70
    assert height == 32
