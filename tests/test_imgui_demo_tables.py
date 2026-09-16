"""``imgui_demo.cpp``'s Tables and legacy Columns sections, ported.

Tables are the part of the reference that leans hardest on the layout stack:
a cell is a cursor position, a row is a wrap, and a *nested* table is the whole
machine pushed and popped inside one of its own cells. Anything that leaks --
a column index that is not restored, a cursor that keeps the inner table's
width -- shows up here and nowhere else.

Sections: Tables/Basic, Custom headers, Nested tables, Row height, Item width,
Sorting, and Columns (legacy API).
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import RecordingPainter


def _run(gui, size=(0.0, 0.0, 600.0, 400.0)):
    painter = RecordingPainter()
    with emtk.frame(painter, size):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Tables/Basic  (imgui_demo.cpp: BeginTable("table1", 3))
# --------------------------------------------------------------------------- #
def test_the_cells_of_a_row_share_a_top_edge():
    cells: dict = {}

    def gui():
        if emtk.begin_table("table1", 3):
            for row in range(3):
                emtk.table_next_row()
                for column in range(3):
                    emtk.table_set_column_index(column)
                    emtk.text("Row %d Column %d" % (row, column))
                    cells[(row, column)] = emtk.get_item_rect()
            emtk.end_table()

    _run(gui)
    for row in range(3):
        ys = {round(cells[(row, c)][1]) for c in range(3)}
        assert len(ys) == 1, (row, ys)


def test_the_rows_of_a_table_go_downwards():
    cells: dict = {}

    def gui():
        if emtk.begin_table("t", 2):
            for row in range(4):
                emtk.table_next_row()
                for column in range(2):
                    emtk.table_set_column_index(column)
                    emtk.text("r%dc%d" % (row, column))
                    cells[(row, column)] = emtk.get_item_rect()
            emtk.end_table()

    _run(gui)
    ys = [cells[(r, 0)][1] for r in range(4)]
    assert ys == sorted(ys) and len(set(ys)) == 4, ys


def test_table_next_column_walks_across_and_wraps():
    """``TableNextColumn`` is the form the demo uses most: no explicit index."""
    seen = []

    def gui():
        if emtk.begin_table("t", 3):
            for index in range(6):
                emtk.table_next_column()
                emtk.text("cell %d" % index)
                seen.append((emtk.table_get_column_index(), emtk.get_item_rect()))
            emtk.end_table()

    _run(gui)
    columns = [c for c, _box in seen]
    assert columns == [0, 1, 2, 0, 1, 2], columns
    # ...and wrapping moved down a row.
    assert seen[3][1][1] > seen[0][1][1]


# --------------------------------------------------------------------------- #
# Tables/Custom headers
# --------------------------------------------------------------------------- #
def test_the_headers_row_uses_the_names_that_were_set_up():
    def gui():
        if emtk.begin_table("t", 3):
            for name in ("One", "Two", "Three"):
                emtk.table_setup_column(name)
            emtk.table_headers_row()
            assert emtk.table_get_column_name(0) == "One"
            assert emtk.table_get_column_count() == 3
            emtk.end_table()

    painter = _run(gui)
    for name in ("One", "Two", "Three"):
        assert name in painter.strings


# --------------------------------------------------------------------------- #
# Tables/Nested tables  (imgui_demo.cpp:6740)
# --------------------------------------------------------------------------- #
#   BeginTable("table_nested1", 2) { ... BeginTable("table_nested2", 2) { ... } ... }
def test_a_table_nested_in_a_cell_does_not_disturb_the_outer_one():
    outer: dict = {}
    inner: dict = {}

    def gui():
        if emtk.begin_table("table_nested1", 2):
            emtk.table_setup_column("A0")
            emtk.table_setup_column("A1")
            emtk.table_headers_row()

            emtk.table_next_column()
            emtk.text("A0 Row 0")
            outer["A0R0"] = emtk.get_item_rect()

            if emtk.begin_table("table_nested2", 2):
                emtk.table_setup_column("B0")
                emtk.table_setup_column("B1")
                emtk.table_headers_row()
                for row in range(2):
                    emtk.table_next_row()
                    for column in range(2):
                        emtk.table_set_column_index(column)
                        emtk.text("B%d Row %d" % (column, row))
                        inner[(row, column)] = emtk.get_item_rect()
                emtk.end_table()

            emtk.table_next_column()
            emtk.text("A1 Row 0")
            outer["A1R0"] = emtk.get_item_rect()
            outer["columns_after"] = emtk.table_get_column_count()
            emtk.end_table()

    _run(gui)
    assert len(inner) == 4, "the inner table lost cells"
    assert outer["columns_after"] == 2, (
        "the outer table came back with the inner table's column count"
    )
    assert outer["A1R0"][0] > outer["A0R0"][0], (
        "the outer table's next column did not advance after the nested one"
    )


def test_the_cursor_comes_back_out_of_a_nested_table():
    boxes: dict = {}

    def gui():
        if emtk.begin_table("outer", 1):
            emtk.table_next_column()
            if emtk.begin_table("inner", 3):
                for _ in range(3):
                    emtk.table_next_column()
                    emtk.text("x")
                emtk.end_table()
            emtk.end_table()
        boxes["avail"] = emtk.get_content_region_avail()[0]
        emtk.text("after")
        boxes["columns"] = emtk.get_columns_count()

    _run(gui)
    assert boxes["columns"] == 1, "columns were left switched on after the tables"
    # A text item is the size of its text, so the room *left* is what says the
    # cursor came back to full width.
    assert boxes["avail"] > 500.0, boxes["avail"]


# --------------------------------------------------------------------------- #
# Tables/Row height and Item width
# --------------------------------------------------------------------------- #
def test_a_widget_in_a_cell_is_no_wider_than_its_column():
    boxes: dict = {}

    def gui():
        if emtk.begin_table("t", 3):
            emtk.table_next_column()
            emtk.slider_float("##s", 0.5, 0.0, 1.0)
            boxes["slider"] = emtk.get_item_rect()
            boxes["column"] = emtk.get_column_width()
            emtk.end_table()

    _run(gui, size=(0.0, 0.0, 600.0, 400.0))
    assert boxes["slider"][2] <= boxes["column"] + 1.0, boxes


# --------------------------------------------------------------------------- #
# Tables/Sorting and Background color -- the queries the demo drives
# --------------------------------------------------------------------------- #
def test_the_table_queries_answer_inside_a_table():
    answers: dict = {}

    def gui():
        if emtk.begin_table("t", 2):
            emtk.table_setup_column("first")
            emtk.table_setup_column("second")
            emtk.table_next_column()
            answers["index"] = emtk.table_get_column_index()
            answers["count"] = emtk.table_get_column_count()
            answers["name"] = emtk.table_get_column_name()
            answers["flags"] = emtk.table_get_column_flags()
            answers["sort"] = emtk.table_get_sort_specs()
            emtk.table_set_bg_color(0, (10, 20, 30, 255))
            emtk.table_set_column_enabled(1, False)
            emtk.table_setup_scroll_freeze(1, 1)
            emtk.end_table()

    _run(gui)
    assert answers["count"] == 2
    assert answers["index"] == 0
    assert answers["name"] == "first"


# --------------------------------------------------------------------------- #
# Columns (legacy API)  (imgui_demo.cpp: DemoWindowColumns)
# --------------------------------------------------------------------------- #
#   ImGui::Columns(4, "mycolumns");
#   ImGui::Text("..."); ImGui::NextColumn(); ...
#   ImGui::Columns(1);
def test_the_legacy_columns_api_lays_out_in_columns():
    cells: dict = {}

    def gui():
        emtk.columns(4)
        for index in range(8):
            emtk.text("cell %d" % index)
            cells[index] = (emtk.get_column_index(), emtk.get_item_rect())
            emtk.next_column()
        emtk.columns(1)
        cells["avail_after"] = emtk.get_content_region_avail()[0]

    _run(gui)
    assert [cells[i][0] for i in range(8)] == [0, 1, 2, 3, 0, 1, 2, 3]
    # The second run of four is a row below the first.
    assert cells[4][1][1] > cells[0][1][1]
    # ...and `Columns(1)` puts the full width back.
    assert cells["avail_after"] > 500.0, cells["avail_after"]


def test_columns_report_their_geometry():
    answers: dict = {}

    def gui():
        emtk.columns(3)
        answers["count"] = emtk.get_columns_count()
        answers["index"] = emtk.get_column_index()
        answers["width"] = emtk.get_column_width()
        answers["offset"] = emtk.get_column_offset()
        emtk.next_column()
        answers["index_after"] = emtk.get_column_index()
        answers["offset_after"] = emtk.get_column_offset()
        emtk.columns(1)

    _run(gui)
    assert answers["count"] == 3
    assert answers["index"] == 0 and answers["index_after"] == 1
    assert answers["width"] > 0
    assert answers["offset"] == 0.0
    assert answers["offset_after"] == pytest.approx(answers["width"])

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Tables/Nested tables
#   Tables/Basic
