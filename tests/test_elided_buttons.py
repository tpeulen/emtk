"""A button sized by its label that does not fit its line ends in an ellipsis and stays whole.

A docked panel or a window magnified by the font settings is narrower than "Select / configure
detector setup"; the clip used to cut the caption mid-letter and the button ran past the panel
(its right part unreachable). It now takes the room that is left.
"""

from __future__ import annotations

from emtk import im
from emtk.testing import Driver

LONG = "Select / configure detector setup"


def _gui():
    im.begin("narrow")
    im.button(LONG)
    im.button("OK")
    im.end()


def test_a_button_wider_than_its_line_is_elided_and_inside_the_window():
    painter = Driver(_gui, size=(160, 200)).frame(2)
    shown = [t for t in painter.texts if t[5].startswith("Select")]
    assert len(shown) == 1 and shown[0][5].endswith("…")
    assert shown[0][0] + painter.text_width(shown[0][5]) <= 160.0
    assert any(t[5] == "OK" for t in painter.texts)


def test_a_wide_window_shows_the_whole_caption():
    painter = Driver(_gui, size=(600, 200)).frame(2)
    assert any(t[5] == LONG for t in painter.texts)


def test_a_button_given_a_width_narrower_than_its_label_is_elided_too():
    def gui():
        im.begin("fixed")
        im.button(LONG, (120.0, 0.0))
        im.end()

    painter = Driver(gui, size=(300, 100)).frame(2)
    shown = [t for t in painter.texts if t[5].startswith("Select")]
    assert len(shown) == 1 and shown[0][5].endswith("\u2026")
    assert painter.text_width(shown[0][5]) <= 120.0
