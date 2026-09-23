"""A data table whose rows form a tree, and cells whose text did not fit.

A record names its parent through ``tree_key``; a parent row draws a
disclosure triangle, a click on it (a double click, Right/Left) opens and
closes it, and its children stay under it whatever the sort. Recording painter
(7 px a glyph, 16 px a line), no window.
"""
from __future__ import annotations

from emtk.keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT
from emtk.testing import RecordingPainter
from emtk.widgets.data_table import DataTable, TableBinding, TableColumn


def _rows():
    return [
        {"name": "Bg", "value": 1.2, "parent": ""},
        {"name": "gamma", "value": "0.61, 0.83", "parent": ""},
        {"name": "gamma[HF]", "label": "HF", "value": 0.61, "parent": "gamma"},
        {"name": "gamma[LF]", "label": "LF", "value": 0.83, "parent": "gamma"},
        {"name": "alpha", "value": 0.015, "parent": ""},
    ]


def _table(**kw):
    table = DataTable([TableColumn("name", "Name"), TableColumn("value", "Value")],
                      row_key="name", tree_key="parent", **kw)
    table.set_records(_rows())
    return table


def _names(table):
    return [table.value(i, "name") for i in table.order()]


def test_children_are_hidden_until_their_parent_opens():
    table = _table()
    assert _names(table) == ["Bg", "gamma", "alpha"]
    assert table.is_parent(1) and not table.is_parent(0)
    table.set_expanded("gamma", True)
    assert _names(table) == ["Bg", "gamma", "gamma[HF]", "gamma[LF]", "alpha"]
    assert [table.depth_of(i) for i in table.order()] == [0, 0, 1, 1, 0]


def test_children_stay_under_their_parent_when_sorted():
    table = _table()
    table.expanded.add("gamma")
    table.sort_by("name", descending=True)
    assert _names(table) == ["gamma", "gamma[LF]", "gamma[HF]", "Bg", "alpha"]  # case-blind


def test_a_filter_shows_a_matching_child_with_its_parent():
    table = _table()
    table.filter.set_text("LF")
    assert _names(table) == ["gamma", "gamma[LF]"]


def test_click_on_the_triangle_and_keys_open_and_close():
    table = _table()
    painter = RecordingPainter()
    table.draw(painter, 0.0, 0.0, 300.0, 200.0)
    assert len(painter.triangles) == 1          # one parent, one triangle
    header_h = 16.0 * 1.35
    row_h = 16.0 * 1.45
    y = header_h + row_h * 1.5                  # the gamma row
    table.press(6.0, y)                         # on its triangle
    assert "gamma" in table.expanded
    table.draw(painter, 0.0, 0.0, 300.0, 200.0)
    table.press(100.0, y)                       # elsewhere on the row: selects only
    assert "gamma" in table.expanded and table.selected_key == "gamma"
    assert table.key(KEY_LEFT)
    assert "gamma" not in table.expanded
    assert table.key(KEY_RIGHT)
    assert "gamma" in table.expanded
    table.key(KEY_DOWN)
    assert table.selected_key == "gamma[HF]"
    assert not table.key(KEY_RIGHT)             # a leaf has nothing to open


def test_children_are_indented():
    table = _table()
    table.expanded.add("gamma")
    painter = RecordingPainter()
    table.draw(painter, 0.0, 0.0, 300.0, 200.0)
    x_of = {text[5]: text[0] for text in painter.texts}
    assert x_of["gamma[HF]"] - x_of["gamma"] == DataTable.TREE_INDENT


def test_fitted_first_column_has_room_for_the_indent():
    table = _table()
    table.expanded.add("gamma")
    table.auto_fit = True
    table.draw(RecordingPainter(), 0.0, 0.0, 600.0, 200.0)
    # "gamma[HF]" (9 glyphs) at level 1: indent 28 + text 63 + margins 14.
    assert table._fitted["name"] >= 2 * DataTable.TREE_INDENT + 9 * 7.0 + 14.0


def test_a_shortened_cell_shows_its_whole_text_as_tooltip():
    table = DataTable([TableColumn("name", "Name", width=40.0), TableColumn("v", "V")])
    table.set_records([{"name": "forster_radius", "v": 52.0}])
    table.draw(RecordingPainter(), 0.0, 0.0, 200.0, 100.0)
    text, part = table.tooltip_at(10.0, 16.0 * 1.35 + 5.0)
    assert text == "forster_radius" and part[0] == "cell"
    assert table.tooltip_at(150.0, 16.0 * 1.35 + 5.0) == ("", None)


class Model:
    def __init__(self):
        self.open_rows = set()

    def rows(self):
        return ROWS


ROWS = _rows()


def test_binding_shares_the_models_expanded_set():
    model = Model()
    binding = TableBinding({"type": "custom", "key": "data_table", "options": {
        "source": "rows", "row_key": "name", "tree_key": "parent",
        "expanded_attr": "open_rows",
        "columns": [{"key": "name"}, {"key": "value"}]}}, model)
    control = binding.control
    assert control.expanded is model.open_rows
    model.open_rows.add("gamma")
    assert len(control.order()) == 5
    control.set_expanded("gamma", False)
    assert model.open_rows == set()
