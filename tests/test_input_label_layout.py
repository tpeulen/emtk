import pytest

from emtk import im
from emtk.im_core import get_current_context
from emtk.testing import RecordingPainter


@pytest.mark.parametrize("kind", ["float", "combo", "text"])
@pytest.mark.parametrize("width", [400, -1])
def test_filling_input_keeps_its_label_inside_the_content_width(kind, width):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 400, 200)):
        im.set_next_item_width(width)
        label = "Lifetime [ns]"
        if kind == "float":
            im.input_float(label, 4.0)
        elif kind == "combo":
            im.combo(label, 0, ["A", "B"])
        else:
            im.input_text(label, "4.0")
        field = get_current_context().get_item_rect()
    caption = next(text for text in painter.texts if text[5] == label)
    assert caption[0] + caption[2] <= 400
    assert field[2] > 200
