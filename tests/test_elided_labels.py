"""A tree row, header or selectable narrower than its label shows "…", never a label cut mid-letter.

A docked navigation pane (the documentation's table of contents) or a window magnified by the
font settings makes rows narrower than their labels; the clip used to cut the text at the edge,
so "Fundamentals - photophysics" read as "Fundamentals - p" with no hint there was more.
"""

from __future__ import annotations

from emtk import im
from emtk.testing import Driver

LONG = "Fundamentals - photophysics of the excited state"


def _gui():
    im.begin("narrow")
    im.collapsing_header(LONG)
    if im.tree_node(LONG + "##tree"):
        im.tree_pop()
    im.selectable(LONG + "##row")
    im.selectable("Short##row2")
    im.end()


def _texts(size):
    drv = Driver(_gui, size=size)
    painter = drv.frame(2)
    return [t for t in painter.texts if "Fundamentals" in t[5] or t[5] == "Short"], painter


def test_rows_wider_than_the_window_end_in_an_ellipsis_and_fit():
    texts, painter = _texts((160, 200))
    shown = [t[5] for t in texts]
    assert len(shown) == 4
    assert "Short" in shown  # a label that fits is untouched
    for entry in texts:
        x, text = entry[0], entry[5]
        if text == "Short":
            continue
        assert text.endswith("…"), text
        assert x + painter.text_width(text) <= 160.0


def test_a_wide_window_shows_the_whole_label():
    texts, _ = _texts((900, 200))
    assert sum(LONG in t[5] for t in texts) == 3
    assert all(not t[5].endswith("\u2026") for t in texts)
