"""``im.begin_grid``: controls in columns that fit or stretch, aligned across rows.

A row of controls -- a toolbar, a label beside a field beside a button -- had
two ways to share the width: arithmetic with ``set_next_item_width`` at every
call site, or a table set up by hand. A grid is the table with the
bookkeeping done: each column either fits its widest content or stretches by a
weight, and the control in a stretching cell fills it.
"""

from __future__ import annotations

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter


def _run(build, width=600.0):
    rects = {}

    def gui():
        im.begin("W", (0, 0, width, 300), flags=im.WindowFlags.NO_TITLE_BAR)
        build(rects)
        im.end()

    app = ImApp(gui)
    for _ in range(3):  # a fit column is sized from the previous frame
        app.draw(RecordingPainter(), 0, 0, width, 300)
    return rects


def _toolbar(rects):
    if im.begin_grid("##bar", (0, 1, 2)):
        im.button("Save/Apply")
        rects["fit"] = im.get_item_rect()
        im.next_cell()
        im.combo("##one", 0, ["one", "two"])
        rects["one"] = im.get_item_rect()
        im.next_cell()
        im.input_text("##two", "x")
        rects["two"] = im.get_item_rect()
        im.end_grid()
    im.button("after")
    rects["after"] = im.get_item_rect()


def test_a_fit_column_is_as_wide_as_its_content():
    rects = _run(_toolbar)
    x, y, w, h = rects["fit"]
    assert rects["one"][0] - (x + w) < 20.0, "the fit column did not fit its button"


def test_stretching_cells_fill_their_share_by_weight():
    rects = _run(_toolbar)
    assert rects["two"][2] == pytest.approx(2.0 * rects["one"][2], rel=0.05)
    right = rects["two"][0] + rects["two"][2]
    assert right > 600.0 - 20.0, "the last cell does not reach the right edge"


def test_one_row_is_one_line_and_the_layout_flows_below_it():
    rects = _run(_toolbar)
    assert rects["fit"][1] == rects["one"][1] == rects["two"][1]
    assert rects["after"][1] > rects["fit"][1] + rects["fit"][3] - 1.0


def test_a_wider_window_grows_only_the_stretching_cells():
    narrow, wide = _run(_toolbar, 600.0), _run(_toolbar, 900.0)
    assert wide["fit"][2] == pytest.approx(narrow["fit"][2])
    assert wide["one"][2] > narrow["one"][2] + 50.0


def test_columns_line_up_across_rows():
    def form(rects):
        if im.begin_grid("##form", (0, 1)):
            im.text("NA")
            im.next_cell()
            im.input_text("##na", "1.4")
            rects["field0"] = im.get_item_rect()
            im.next_row()
            im.text("Lateral size (px)")
            rects["label1"] = im.get_item_rect()
            im.next_cell()
            im.input_text("##size", "48")
            rects["field1"] = im.get_item_rect()
            im.end_grid()

    rects = _run(form)
    assert rects["field0"][0] == rects["field1"][0], "fields do not start at one x"
    label = rects["label1"]
    assert rects["field1"][0] >= label[0] + label[2], "the widest label overlaps its field"
