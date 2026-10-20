"""A filter stays at the top of the list it narrows while the list scrolls.

A filter typed into the first row *inside* a scrolling region scrolls away with
the first rows (the ChiSurf Tools panel did); :func:`emtk.im.begin_filtered_list`
lays the field out above the region instead, and a data table pins its filter
and header to the top of a scrolled parent. These tests scroll by wheel and
check that the field did not move, still takes clicks and keys, and that the
rows scrolled under it are clipped rather than painted over it.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_ESCAPE, KEY_UP
from emtk.testing import RecordingPainter
from emtk.widgets.data_table import TableBinding, draw_table

W, H = 260, 200
ROWS = [f"row {i:02d}" for i in range(40)]


class _List:
    """A filtered list of 40 selectables in a window, recording what it drew."""

    def __init__(self):
        self.query = ""
        self.clicked: list[str] = []
        self.rects: dict = {}
        self.app = ImApp(self.gui)
        self.painter = RecordingPainter()

    def gui(self):
        im.begin("W", (0, 0, W, H))
        _changed, self.query = im.begin_filtered_list("rows", self.query, "Filter rows")
        self.rects["filter"] = im.get_item_rect()
        self.rects["list"] = None
        for name in ROWS:
            if self.query in name:
                if im.selectable(name):
                    self.clicked.append(name)
                self.rects[name] = im.get_item_rect()
        self.rects["list"] = im.end_filtered_list()
        im.end()

    def frame(self, n=1):
        for _ in range(n):
            self.painter = RecordingPainter()
            self.app.draw(self.painter, 0, 0, W, H)

    def centre(self, key):
        x, y, w, h = self.rects[key]
        return x + w / 2, y + h / 2

    def click(self, key):
        x, y = self.centre(key)
        self.app.hover(x, y)
        self.frame()
        self.app.press(x, y)
        self.frame()
        self.app.release()
        self.frame()

    def key(self, key, text=""):
        self.app.key(key, text)
        self.frame(2)

    def visible(self, text):
        """The bounds *text* was visibly drawn at (zero height when clipped away), or None."""
        for entry in self.painter.visible_texts:
            if entry[5] == text:
                return entry[:4]
        return None


def _scrolled():
    ui = _List()
    ui.frame(3)
    filter_before = ui.rects["filter"]
    row0_before = ui.rects["row 00"]
    x, y = ui.centre("row 05")
    ui.app.hover(x, y)
    ui.frame()
    ui.app.wheel(x, y, -3)
    ui.frame(2)
    return ui, filter_before, row0_before


def test_the_filter_does_not_move_when_the_list_scrolls():
    ui, filter_before, row0_before = _scrolled()
    assert ui.rects["row 00"][1] < row0_before[1], "the wheel did not scroll the list"
    assert ui.rects["filter"] == filter_before


def test_rows_scrolled_under_the_filter_are_clipped_not_drawn_over_it():
    ui, filter_before, _ = _scrolled()
    list_top = ui.rects["list"][1]
    assert list_top >= filter_before[1] + filter_before[3]
    for name in ROWS:
        bounds = ui.visible(name)
        if bounds is None or bounds[3] <= 0:
            continue
        assert bounds[1] >= list_top - 0.5, f"{name} was drawn over the filter"
    assert ui.visible("row 00") is None or ui.visible("row 00")[3] <= 0


def test_the_filter_still_takes_clicks_and_keys_after_scrolling():
    ui, _, _ = _scrolled()
    ui.click("filter")
    ui.key(0, "1")
    assert ui.query == "1"
    assert "row 10" in ui.rects and ui.rects["row 10"][1] >= ui.rects["list"][1]


def test_typing_puts_the_list_back_at_the_top():
    ui, _, _ = _scrolled()
    ui.click("filter")
    ui.key(0, "3")
    first = next(name for name in ROWS if "3" in name)
    assert abs(ui.rects[first][1] - ui.rects["list"][1]) < 1.0


def test_escape_clears_the_filter_then_lets_go():
    ui = _List()
    ui.frame(2)
    ui.click("filter")
    ui.key(0, "2")
    assert ui.query == "2"
    ui.key(KEY_ESCAPE)
    assert ui.query == ""
    assert ui.app.io.want_text_input
    ui.key(KEY_ESCAPE)
    assert not ui.app.io.want_text_input, "a second Escape keeps the keyboard"


def test_down_walks_into_the_list_and_enter_activates():
    ui = _List()
    ui.frame(2)
    ui.click("filter")
    ui.key(0, "1")                        # row 01, row 10 .. row 19, row 21, row 31
    ui.key(KEY_DOWN)
    ui.key(KEY_DOWN)
    ui.key(KEY_ENTER)
    assert ui.clicked == ["row 10"]
    ui.key(KEY_UP)
    ui.key(KEY_UP)                        # off the first entry: back to the field, selected
    ui.key(0, "9")
    assert ui.query == "9"


def test_the_focused_entry_is_scrolled_into_view():
    ui = _List()
    ui.frame(2)
    ui.click("filter")
    ui.key(KEY_DOWN)
    for _ in range(25):
        ui.key(KEY_DOWN)
    ui.key(KEY_ENTER)
    assert ui.clicked == ["row 25"]
    top = ui.rects["list"][1]
    bottom = top + ui.rects["list"][3]
    rect = ui.rects["row 25"]
    assert rect[1] >= top - 0.5 and rect[1] + rect[3] <= bottom + 0.5


# -- a data table that shows every row, in a form the user scrolls ---------------------------- #

class _Model:
    def __init__(self):
        self.rows = [{"name": f"item {i:02d}", "value": i} for i in range(30)]

    def sheet(self):
        return self.rows


def _table_ui():
    binding = TableBinding({"type": "custom", "key": "data_table",
                            "options": {"source": "sheet", "fit_rows": True, "filter": True,
                                        "columns": [{"key": "name", "title": "Name"},
                                                    {"key": "value", "title": "Value"}]}},
                           _Model())
    state = {}

    def gui():
        im.begin("F", (0, 0, W, H))
        state["form"] = (*im.get_cursor_screen_pos(), W - 10, H - 10)
        im.begin_child("form", (W - 10, H - 10))
        im.text("A caption above the table")
        draw_table(binding, "sheet")
        state["child"] = im.get_item_rect()
        im.text("A line after it")
        im.end_child()
        im.end()

    return ImApp(gui), binding.control, state


def _draw(app, n=1):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, W, H)
    return painter


def test_a_table_inside_a_scrolled_form_keeps_its_filter_and_header_in_sight():
    app, table, state = _table_ui()
    _draw(app, 3)
    assert table.natural_height(RecordingPainter.LINE_H) > H, "the table must be taller than the form"
    top = state["form"][1]
    app.hover(40, 120)
    _draw(app)
    app.wheel(40, 120, -4)
    painter = _draw(app, 2)
    _fx, fy, _fw, fh = table._filter_box
    _hx, hy, _hw, hh = table._header_box
    assert abs(fy - top) < 1.0, "the filter scrolled away with the rows"
    assert hy >= fy + fh
    body_top = table._body_box[1]
    assert body_top >= hy + hh - 0.5
    for entry in painter.visible_texts:
        if entry[5].startswith("item ") and entry[3] > 0:
            assert entry[1] >= body_top - 0.5, f"{entry[5]} was drawn over the pinned header"


def test_the_pinned_filter_takes_a_click_and_typing():
    app, table, _state = _table_ui()
    _draw(app, 3)
    app.hover(40, 120)
    _draw(app)
    app.wheel(40, 120, -4)
    _draw(app, 2)
    fx, fy, _fw, fh = table._filter_box
    app.hover(fx + 20, fy + fh / 2)
    _draw(app)
    app.press(fx + 20, fy + fh / 2)
    _draw(app)
    app.release()
    _draw(app)
    assert table.filter_focused
    app.key(0, "7")
    _draw(app, 2)
    assert table.filter.field.text == "7"
    assert len(table.order()) == 3                # item 07, 17, 27


def test_a_table_with_its_own_scrollbar_keeps_the_filter_above_its_rows():
    binding = TableBinding({"type": "custom", "key": "data_table",
                            "options": {"source": "sheet", "height": 150, "filter": True,
                                        "columns": [{"key": "name", "title": "Name"}]}},
                           _Model())

    def gui():
        im.begin("F", (0, 0, W, H))
        draw_table(binding, "sheet")
        im.end()

    app = ImApp(gui)
    _draw(app, 2)
    table = binding.control
    before = table._filter_box
    app.hover(40, 100)
    _draw(app)
    app.wheel(40, 100, -2)
    _draw(app, 2)
    assert table.bar.top > 0, "the wheel did not scroll the rows"
    assert table._filter_box == before


def test_a_view_spec_panel_keeps_its_group_and_filter_fields_above_the_settings():
    """The settings scroll; the group selector and the filter of the panel stay put."""
    from types import SimpleNamespace

    from emtk.widgets.view_spec import ViewSpecPanel

    names = [f"setting_{i:02d}" for i in range(40)]
    model = SimpleNamespace(**{name: False for name in names})
    panel = ViewSpecPanel({"sections": [
        {"type": "toggle", "attr": name, "label": name, "description": name} for name in names
    ]}, model)
    for _ in range(3):
        panel.draw(RecordingPainter(), 0, 0, W, H)
    before = panel.item_rects["view_spec.filter"]
    first = panel.item_rects["setting_00"]
    panel.hover(W / 2, H / 2)
    panel.draw(RecordingPainter(), 0, 0, W, H)
    panel._app.wheel(W / 2, H / 2, -3)
    for _ in range(2):
        panel.draw(RecordingPainter(), 0, 0, W, H)
    assert panel.item_rects["setting_00"][1] < first[1], "the wheel did not scroll the settings"
    assert panel.item_rects["view_spec.filter"] == before


def test_a_stretched_list_leaves_room_for_the_buttons_after_it():
    rects = {}

    def gui():
        im.begin("W", (0, 0, W, H))
        im.begin_filtered_list("rows", "", "Filter rows", stretch=True)
        for name in ROWS:
            im.selectable(name)
        rects["list"] = im.end_filtered_list()
        im.button("Back")
        im.button("Next")
        rects["next"] = im.get_item_rect()
        im.end()

    app = ImApp(gui)
    for _ in range(4):
        app.draw(RecordingPainter(), 0, 0, W, H)
    _x, y, _w, h = rects["next"]
    assert y + h <= H + 0.5, "the buttons after the list ran off the window"
    assert rects["list"][3] > 60
