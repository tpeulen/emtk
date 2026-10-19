"""A ``display: "button"`` column draws a button per row; a click calls the model.

A review table wants "Approve" on every row: before this a spec could only put
one button under the table, acting on the selected row -- a click to select,
a trip down the form, a click to act.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.widgets.data_table import TableBinding, draw_table


class TableApp(ImApp):
    def __init__(self):
        self.rows = [{"id": "first", "act": "Approve"}, {"id": "second", "act": ""},
                     {"id": "third", "act": "Approve"}]
        self.calls = []
        self.binding = TableBinding({
            "type": "table", "source": "rows", "row_key": "id", "height": 200,
            "columns": [{"key": "id", "label": "Item"},
                        {"key": "act", "label": "", "display": "button", "call": "act",
                         "width": 90}],
        }, self)
        super().__init__(self.gui)
        self.io.wall_clock = False

    def act(self, record):
        self.calls.append(record["id"])

    def gui(self):
        im.begin("Review", (0, 0, 400, 240))
        draw_table(self.binding, "items")
        im.end()


def test_a_click_on_a_rows_button_calls_the_model_with_that_row():
    app = TableApp()
    ui = Driver(app, (400, 240))
    ui.frame(2)
    ui.click("Approve")  # the last drawn: the third row
    assert app.calls == ["third"]
    assert app.binding.control.selected_key == "third"


def test_a_row_with_an_empty_cell_has_no_button():
    app = TableApp()
    ui = Driver(app, (400, 240))
    ui.frame(2)
    x, y, w, h = ui.rect("second")
    ui.click((x + 330, y + h / 2))
    assert app.calls == []
    assert app.binding.control.selected_key == "second"
