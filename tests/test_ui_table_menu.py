"""The popup context menu a ``data_table`` declares with ``context_menu``."""
from __future__ import annotations

import emtk
from emtk.keys import KEY_ESCAPE, KEY_F10
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form
from emtk.widgets.table_menu import KEY_MENU


class Rows:
    def __init__(self):
        self.rows = [{"_id": i, "name": f"n{i}"} for i in range(4)]
        self.calls = []
        self.allow = True

    def listing(self):
        return self.rows

    def copy_row(self, record):
        self.calls.append(("copy", record["name"]))

    def copy_cell(self, record, key):
        self.calls.append(("cell", record["name"], key))

    def can(self, record):
        return self.allow


SPEC = {"sections": [{
    "type": "custom", "key": "data_table",
    "options": {
        "source": "listing", "row_key": "_id", "height": 200,
        "columns": [{"key": "_id", "title": "ID"}, {"key": "name", "title": "Name"}],
        "context_menu": [
            {"label": "Copy row", "call": "copy_row", "description": "Copy the row."},
            {"label": "Copy cell", "call": "copy_cell", "enabled_when": "can"},
        ],
    },
}]}


class Harness:
    def __init__(self):
        self.model = Rows()
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.frame()

    def frame(self):
        with emtk.frame(RecordingPainter(), (0, 0, 480, 360), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 480, 360))
            draw_form(SPEC, self.model, self.state)
            emtk.end()
        io = self.io
        for i in range(3):
            io.mouse_clicked[i] = io.mouse_released[i] = False
        io.key, io.text = 0, ""
        io.key_shift = False

    @property
    def binding(self):
        return next(iter(self.state.tables.values()))

    @property
    def control(self):
        return self.binding.control

    def row_xy(self, position):
        bx, by, _bw, _bh = self.control._body_box
        return bx + 300.0, by + self.control._row_h * (position + 0.5)

    def click(self, xy, button=0):
        self.io.mouse_pos = xy
        self.io.mouse_clicked[button] = self.io.mouse_down[button] = True
        self.frame()
        self.io.mouse_down[button] = False
        self.frame()

    def item_xy(self, index):
        x, y, w, h = self.binding.menu_panel.row_rect(index)
        return x + w / 2, y + h / 2


def test_right_click_opens_the_menu_at_the_pointer():
    h = Harness()
    xy = h.row_xy(2)
    h.click(xy, button=1)
    panel = h.binding.menu_panel
    assert panel is not None and panel.open
    assert panel.anchor == xy
    assert [e.label for e in panel.entries] == ["Copy row", "Copy cell"]
    assert panel.entries[0].tooltip == "Copy the row."
    assert h.control.selected_indices() == [2]


def test_picking_an_item_calls_the_method_with_the_clicked_row():
    h = Harness()
    h.click(h.row_xy(2), button=1)
    h.click(h.item_xy(0))
    assert h.model.calls == [("copy", "n2")]
    assert h.binding.menu_panel is None
    # a method that takes a second argument is told the column under the pointer
    h.click(h.row_xy(1), button=1)
    h.click(h.item_xy(1))
    assert h.model.calls[-1] == ("cell", "n1", "name")  # the right-hand column


def test_enabled_when_greys_an_item_out():
    h = Harness()
    h.model.allow = False
    h.click(h.row_xy(0), button=1)
    assert not h.binding.menu_panel.entries[1].enabled
    h.click(h.item_xy(1))
    assert h.model.calls == []


def test_escape_and_an_outside_click_close_it():
    h = Harness()
    h.click(h.row_xy(0), button=1)
    h.io.key = KEY_ESCAPE
    h.frame()
    h.frame()
    assert h.binding.menu_panel is None
    h.click(h.row_xy(0), button=1)
    assert h.binding.menu_panel is not None
    h.click((470.0, 350.0))
    assert h.binding.menu_panel is None
    assert h.model.calls == []


def test_shift_f10_and_the_menu_key_open_it_on_the_selected_row():
    h = Harness()
    h.click(h.row_xy(1))                       # select row 1 by a left click
    h.io.mouse_pos = h.row_xy(1)
    h.io.key, h.io.key_shift = KEY_F10, True
    h.frame()
    h.frame()
    assert h.binding.menu_panel is not None and h.binding.menu_panel.open
    h.click(h.item_xy(0))
    assert h.model.calls == [("copy", "n1")]
    h.io.mouse_pos = h.row_xy(1)
    h.io.key = KEY_MENU
    h.frame()
    h.frame()
    assert h.binding.menu_panel is not None



class OfferingRows(Rows):
    """A model whose menu offers per-row items (the tools that take a row)."""

    def __init__(self):
        super().__init__()
        self.offers = {"n2": ["Tool A", "Tool B"]}

    def open_in(self, record):
        return [
            {"label": f"Open in {tool}",
             "call": (lambda row, t=tool: self.calls.append((t, row["name"]))),
             "description": f"Give the row to {tool}."}
            for tool in self.offers.get(record["name"], [])
        ]


OFFERING_SPEC = {"sections": [{
    "type": "custom", "key": "data_table",
    "options": {
        "source": "listing", "row_key": "_id", "height": 200,
        "columns": [{"key": "_id", "title": "ID"}, {"key": "name", "title": "Name"}],
        "context_menu": [
            {"label": "Copy row", "call": "copy_row"},
            {"label": "Open in…", "items_source": "open_in", "description": "No tool takes it."},
        ],
    },
}]}


class OfferingHarness(Harness):
    def __init__(self):
        self.model = OfferingRows()
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.frame()

    def frame(self):
        with emtk.frame(RecordingPainter(), (0, 0, 480, 360), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 480, 360))
            draw_form(OFFERING_SPEC, self.model, self.state)
            emtk.end()
        io = self.io
        for i in range(3):
            io.mouse_clicked[i] = io.mouse_released[i] = False
        io.key, io.text = 0, ""
        io.key_shift = False


def test_items_source_fills_the_menu_from_the_model_when_it_opens():
    """An ``items_source`` item asks the model for its entries per row (Open in <tool>)."""
    h = OfferingHarness()
    h.click(h.row_xy(2), button=1)
    assert [e.label for e in h.binding.menu_panel.entries] == [
        "Copy row", "Open in Tool A", "Open in Tool B"]
    h.click(h.item_xy(2))
    assert h.model.calls[-1] == ("Tool B", "n2")
    # a row no tool takes: the item's own label, dimmed
    h.click(h.row_xy(0), button=1)
    last = h.binding.menu_panel.entries[-1]
    assert last.label == "Open in…" and not last.enabled


def test_items_source_group_nests_the_items_in_submenus():
    """Items with a ``group`` hang under the item's label as ``Open in… > group > tool``."""
    from emtk.widgets import table_menu
    from emtk.widgets.menus import Menu

    h = OfferingHarness()
    picked = []
    h.model.open_in = lambda row: [
        {"label": "Tool A", "group": "Imaging", "call": lambda r: picked.append("A")},
        {"label": "Tool B", "group": "Photon data", "call": lambda r: picked.append("B")},
    ]
    entries, _calls = table_menu._entries(h.binding, h.binding.record(2))
    menu = next(e for e in entries if isinstance(e, Menu))
    assert menu.label == "Open in…"
    assert [(m.label, [i.label for i in m.entries]) for m in menu.entries] == [
        ("Imaging", ["Tool A"]), ("Photon data", ["Tool B"])]
    item = menu.entries[1].entries[0]
    assert callable(h.binding._menu_picks[id(item)])
