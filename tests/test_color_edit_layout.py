"""RGB edits remain inside their available row and keep labels clickable."""
from emtk import im
from emtk.testing import RecordingPainter


def test_rgb_channels_and_label_fit_wide_row():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 320, 100)):
        changed, values = im.color_edit3("Tint", (10, 20, 30))
    assert not changed
    assert values == (10, 20, 30)
    labels = [text for text in painter.texts if text[5] in {"10", "20", "30", "Tint"}]
    assert len(labels) == 4
    assert all(text[0] >= 0 and text[0] + text[2] <= 320 for text in labels)
    assert len({text[1] for text in labels}) == 1


def test_rgb_long_label_wraps_before_narrow_channels():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 180, 150)):
        im.color_edit3("Selection and marker background", (10, 20, 30))
    channels = [text for text in painter.texts if text[5] in {"10", "20", "30"}]
    assert len(channels) == 3
    assert all(text[0] >= 0 and text[0] + text[2] <= 180 for text in channels)
    label = next(text for text in painter.texts if "Selection" in text[5])
    assert channels[0][1] >= label[1] + label[3]


def test_consecutive_rgb_rows_keep_panel_origin():
    painter = RecordingPainter()
    with im.frame(painter, (20, 10, 700, 300)):
        for name in ("Paper", "Text", "Margins", "Selection / marker", "Current line"):
            im.color_edit3(name, (10, 20, 30))
    assert all(20 <= text[0] and text[0] + text[2] <= 720 for text in painter.texts)
    channel_rows = [text[1] for text in painter.texts if text[5] == "10"]
    assert len(channel_rows) == 5
    assert channel_rows == sorted(set(channel_rows))
