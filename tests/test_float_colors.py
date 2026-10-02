from emtk import im
from emtk.pil_painter import PilPainter


def test_normalized_text_color_draws_visible_numeric_results():
    painter = PilPainter(200, 60)
    with im.frame(painter, (0, 0, 200, 60)):
        im.text_colored((0.55, 0.8, 1.0, 1.0), "0.667")
    assert max(painter.frame.tobytes()) > 100
