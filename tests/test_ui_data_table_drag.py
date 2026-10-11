"""A row pulled out of a data table: ``drag_call(record, x, y, dropped)``.

The emtk shell's Datasets panel lets a dataset be dragged onto a fit window; the
table only reports the row, where it is and where it was let go -- the host
decides what lies under that point. Recording painter, no window.
"""

from __future__ import annotations

from emtk.testing import RecordingPainter
from emtk.widgets.data_table import TableBinding


class _Datasets:
    def __init__(self):
        self.rows = [{"uid": "a", "name": "first"}, {"uid": "b", "name": "second"}]
        self.dragged: list[tuple] = []

    def records(self):
        return self.rows

    def dragging(self, record, x, y, dropped):
        self.dragged.append((record["uid"], round(x), round(y), dropped))


def _drag_section():
    return {
        "type": "table",
        "source": "records",
        "row_key": "uid",
        "drag_call": "dragging",
        "columns": [{"key": "name", "label": "Name"}],
    }


def _row_point(control, position):
    bx, by, bw, _bh = control._body_box
    return bx + bw / 2, by + control._row_h * (position + 0.5)


def test_a_row_dragged_out_of_the_table_reports_its_moves_and_its_drop():
    model = _Datasets()
    control = TableBinding(_drag_section(), model).control
    control.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    x, y = _row_point(control, 1)
    control.press(x, y, 0.0, 0.0, 300.0, 200.0, 0, 1)
    control.drag(x + 2.0, y + 1.0)
    assert model.dragged == [], "a press that hardly moves is a click"
    control.drag(x + 200.0, y + 40.0)
    control.drag(x + 400.0, y + 60.0)
    control.release()
    assert [d[0] for d in model.dragged] == ["b", "b", "b"]
    assert [d[3] for d in model.dragged] == [False, False, True]
    assert model.dragged[-1][1:3] == (round(x + 400.0), round(y + 60.0)), "dropped where it ended"
    assert control.selected_key == "b"


def test_without_a_drag_call_rows_stay_put():
    model = _Datasets()
    section = dict(_drag_section())
    section.pop("drag_call")
    control = TableBinding(section, model).control
    control.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    x, y = _row_point(control, 0)
    control.press(x, y, 0.0, 0.0, 300.0, 200.0, 0, 1)
    control.drag(x + 200.0, y + 40.0)
    control.release()
    assert model.dragged == [] and control._row_press is None
