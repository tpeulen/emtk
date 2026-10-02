from emtk import im
from emtk.testing import RecordingPainter


def test_inline_tab_body_does_not_move_later_headers_below_content():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 600, 500)):
        im.begin_tab_bar("profiles")
        if im.begin_tab_item("X profile"):
            im.dummy(400, 250)
            im.text("Plot footer")
            im.end_tab_item()
        if im.begin_tab_item("Y profile"):
            im.text("Y plot")
            im.end_tab_item()
        im.end_tab_bar()
        im.text("After tabs")
    positions = {t[5]: t for t in painter.texts}
    assert positions["X profile"][1] == positions["Y profile"][1]
    assert positions["After tabs"][1] > positions["Plot footer"][1]
