"""``selection: "single"``: a table whose one selected row is the record a form shows.

Shift- and ctrl-clicks select the clicked row alone, Select All does nothing; without the option they extend the
selection as before. Recording painter (16 px a line), no window.
"""
from __future__ import annotations

from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.testing import RecordingPainter
from emtk.widgets.data_table import DataTable, TableBinding, TableColumn

ROWS = [{"name": n} for n in ("a.spc", "b.spc", "c.spc")]


def _y(table, row):
    return 16.0 * 1.25 + 16.0 * table.row_scale * (row + 0.5)


def _table(single):
    table = DataTable([TableColumn("name", "File")], row_key="name")
    table.single_select = single
    table.set_records(ROWS)
    table.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    return table


def _press(table, row, modifiers=0):
    table.press(100.0, _y(table, row), 0.0, 0.0, 300.0, 200.0, modifiers)


def test_single_selection_ignores_shift_ctrl_and_select_all():
    table = _table(single=True)
    _press(table, 0)
    _press(table, 2, SHIFT_MODIFIER)
    assert table.selected_key == "c.spc" and table.selected_indices() == [2]
    _press(table, 1, CONTROL_MODIFIER)
    assert table.selected_indices() == [1]
    table.select_all()
    assert table.selected_indices() == [1]


def test_without_the_option_shift_extends():
    table = _table(single=False)
    _press(table, 0)
    _press(table, 2, SHIFT_MODIFIER)
    assert table.selected_indices() == [0, 1, 2]


def test_the_spec_option_reaches_the_table():
    class Model:
        def rows(self):
            return ROWS

    section = {"type": "table", "source": "rows", "selection": "single",
               "columns": [{"key": "name", "label": "File"}]}
    assert TableBinding(section, Model()).control.single_select
    del section["selection"]
    assert not TableBinding(section, Model()).control.single_select
