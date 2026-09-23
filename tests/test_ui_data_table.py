"""Tables declared in a view spec: ``table`` and ``data_table``, painted.

The Qt renderer (chisurf's AutoForm) and these are two readers of one dialect,
so the tests are written against the spec keys, not against the control's
internals: a section goes in, rows come out sorted, selection reaches
``selected_call``, and a source that grows while a computation streams is
picked up without rebinding. Recording painter (7 px a glyph, 16 px a line),
no window, no toolkit.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.keys import KEY_BACKSPACE, KEY_DELETE, KEY_DOWN, KEY_ESCAPE, KEY_RETURN, KEY_UP
from emtk.testing import PixelPainter, RecordingPainter
from emtk.view_form import FormState, draw_form
from emtk.widgets.data_table import (
    BAR_COLOUR,
    NEGATIVE_COLOUR,
    POSITIVE_COLOUR,
    DataTable,
    TableBinding,
    TableColumn,
    is_table_section,
)
from emtk.widgets.view_spec import (
    ViewSpecPanel,
    settings_from_view_spec,
    table_bindings,
    unsupported_sections,
)


class Ranking:
    """A model whose table fills while something computes."""

    def __init__(self):
        self.rows = []
        self.picked = []
        self.activated = []
        self.method = "structure"
        self.current = {}

    def ranked_rows(self):
        return self.rows

    def ranked_columns(self):
        title, span = ("r", [-1, 1]) if self.method == "pearson" else ("Structure", [0, 1])
        return [
            {"key": "score", "title": title, "display": "bar", "range": span, "format": "%.3f"},
            {"key": "x", "title": "x"},
            {"key": "y", "title": "y"},
        ]

    def apply_row(self, record):
        self.picked.append(record)

    def open_row(self, record):
        self.activated.append(record)

    def add(self, score, x, y, note=""):
        self.rows.append({"score": score, "x": x, "y": y, "key": f"{x}|{y}", "note": note})


DATA_TABLE = {
    "type": "custom", "key": "data_table", "title": "Ranked views",
    "options": {
        "source": "ranked_rows", "columns_source": "ranked_columns",
        "selected_call": "apply_row", "activated_call": "open_row", "height": 200,
        "sort": {"key": "score", "descending": True}, "filter": True,
        "tooltip_key": "note", "row_key": "key",
    },
}


def draw(control, w=420.0, h=260.0):
    painter = RecordingPainter()
    control.draw(painter, 0.0, 0.0, w, h)
    return painter


def click_row(control, position, clicks=1):
    bx, by, _bw, _bh = control._body_box
    control.press(bx + 30.0, by + control._row_h * (position + 0.5), clicks=clicks)


# ---- the two dialects ----------------------------------------------------------------


def test_both_dialects_are_table_sections():
    assert is_table_section({"type": "table", "source": "rows"})
    assert is_table_section(DATA_TABLE)
    assert not is_table_section({"type": "custom", "key": "parameter_group_table"})
    assert not is_table_section({"type": "value", "attr": "x"})


def test_column_specs_read_both_spellings():
    builtin = TableColumn.from_spec({"key": "tau", "label": "Lifetime", "width": 80,
                                     "description": "τ of the fit"})
    custom = TableColumn.from_spec({"key": "tau", "title": "τ", "units": "ns",
                                    "tooltip": "fitted", "visible": False})
    assert (builtin.title, builtin.width, builtin.tooltip) == ("Lifetime", 80.0, "τ of the fit")
    assert (custom.title, custom.tooltip, custom.visible) == ("τ (ns)", "fitted", False)


def test_number_formats():
    column = TableColumn("score", fmt="%.3f")
    assert column.text(0.12345) == "0.123"
    assert TableColumn("n").text(12) == "12"
    assert TableColumn("r").text(0.000123456789) == "0.000123457"
    assert TableColumn("r").text(float("nan")) == "N/A"


def test_a_bar_is_a_fraction_of_its_range_and_diverges_across_zero():
    assert TableColumn("s", display="bar", range=(0.0, 2.0)).bar(0.5) == (0.0, 0.25, BAR_COLOUR)
    positive = TableColumn("r", display="bar", range=(-1.0, 1.0)).bar(0.5)
    negative = TableColumn("r", display="bar", range=(-1.0, 1.0)).bar(-0.5)
    assert positive == (0.5, 0.75, POSITIVE_COLOUR)
    assert negative == (0.25, 0.5, NEGATIVE_COLOUR)
    assert TableColumn("s").bar(0.5) is None  # not declared a bar


# ---- binding a section to a model ----------------------------------------------------


def test_rows_stream_in_and_stay_sorted_by_value_not_text():
    model = Ranking()
    binding = TableBinding(DATA_TABLE, model)
    for score, x in [(0.41, "a"), (-0.052, "b"), (0.9, "c"), (0.085, "d")]:
        model.add(score, x, "t")
    assert binding.refresh(), "an append to the same list must be noticed"
    control = binding.control
    assert [control.value(i, "x") for i in control.order()] == ["c", "a", "d", "b"]
    model.add(0.5, "e", "t")
    binding.refresh()
    assert [control.value(i, "x") for i in control.order()] == ["c", "e", "a", "d", "b"]
    assert not binding.refresh(), "nothing changed, nothing rebound"


def test_selection_reaches_selected_call_with_the_record_and_survives_streaming():
    model = Ranking()
    binding = TableBinding(DATA_TABLE, model)
    model.add(0.2, "a", "b")
    model.add(0.1, "c", "d")
    binding.refresh()
    draw(binding.control)
    click_row(binding.control, 1)
    assert model.picked[-1]["key"] == "c|d"
    model.add(0.9, "e", "f")
    model.add(0.95, "g", "h")
    binding.refresh()
    assert binding.record(binding.control.selected_index())["key"] == "c|d"
    click_row(binding.control, 0, clicks=2)
    assert model.activated[-1]["key"] == "g|h"


def test_select_key_marks_a_row_without_calling_back():
    model = Ranking()
    binding = TableBinding(DATA_TABLE, model)
    model.add(0.3, "a", "b")
    binding.refresh()
    assert binding.control.select_key("a|b")
    assert model.picked == []
    assert not binding.control.select_key("nope")


def test_columns_follow_columns_source():
    model = Ranking()
    binding = TableBinding(DATA_TABLE, model)
    assert binding.control.columns[0].title == "Structure"
    model.method = "pearson"
    assert binding.refresh()
    assert binding.control.columns[0].title == "r"
    assert binding.control.columns[0].range == (-1.0, 1.0)


def test_a_builtin_table_over_objects_with_selected_attr():
    class Row:
        def __init__(self, name, size):
            self.name, self.size = name, size

    class Model:
        rows = [Row("small", 2), Row("large", 20)]
        current = None

    section = {"type": "table", "source": "rows", "selected_attr": "current",
               "columns": [{"key": "name", "label": "Name"}, {"key": "size", "label": "Size"}]}
    model = Model()
    binding = TableBinding(section, model)
    binding.control.sort_by("size", descending=True)
    draw(binding.control)
    click_row(binding.control, 0)
    assert model.current.name == "large"


def test_named_arrays_report_the_row_index():
    picked = []

    class Model:
        def table(self):
            return {"a": [3.0, 1.0, 2.0], "b": ["x", "y", "z"]}

        def pick(self, value):
            picked.append(value)

    section = {"type": "custom", "key": "data_table",
               "options": {"source": "table", "selected_call": "pick"}}
    binding = TableBinding(section, Model())
    assert [c.key for c in binding.control.columns] == ["a", "b"]
    binding.control.sort_by("a")
    draw(binding.control)
    click_row(binding.control, 0)
    assert picked == [1]


def test_missing_values_sort_last_both_ways():
    control = DataTable([TableColumn("v")])
    control.set_records([{"v": 1.0}, {"v": None}, {"v": float("nan")}, {"v": 3.0}])
    control.sort_by("v", descending=False)
    assert control.order()[:2] == [0, 3]
    control.sort_by("v", descending=True)
    assert control.order()[:2] == [3, 0]


def test_ties_keep_the_producers_order():
    control = DataTable([TableColumn("v")])
    control.set_records([{"v": 1.0, "n": i} for i in range(4)])
    control.sort_by("v", descending=True)
    assert control.order() == [0, 1, 2, 3]


# ---- input -----------------------------------------------------------------------------


def test_header_click_sorts_and_flips():
    control = DataTable([TableColumn("name"), TableColumn("size")])
    control.set_records([{"name": n, "size": s} for n, s in [("b", 2), ("a", 3), ("c", 1)]])
    draw(control)
    hx, hy, _hw, hh = control._header_box
    control.press(hx + control._widths[0] + 5.0, hy + hh / 2)
    assert [control.value(i, "size") for i in control.order()] == [1, 2, 3]
    control.press(hx + control._widths[0] + 5.0, hy + hh / 2)
    assert [control.value(i, "size") for i in control.order()] == [3, 2, 1]


def test_filter_typing_and_arrow_keys():
    selected = []
    control = DataTable([TableColumn("x")], filter_box=True, on_select=selected.append)
    control.set_records([{"x": "Tau (green)"}, {"x": "Number of Photons"}, {"x": "r (green)"}])
    draw(control)
    fx, fy, _fw, fh = control._filter_box
    control.press(fx + 5.0, fy + fh / 2)
    for char in "green":
        control.key(0, char)
    assert [control.value(i, "x") for i in control.order()] == ["Tau (green)", "r (green)"]
    control.key(KEY_BACKSPACE)
    assert control.filter.text == "gree"
    control.press(0.0, 250.0)  # somewhere else: the filter lets go of the keys
    control.key(KEY_DOWN)
    control.key(KEY_DOWN)
    assert selected == [0, 2]
    control.key(KEY_UP)
    assert control.selected_index() == 0


def test_only_the_visible_rows_are_drawn():
    control = DataTable([TableColumn("x")])
    control.set_records([{"x": f"row{i}"} for i in range(5000)])
    painter = draw(control, h=240.0)
    shown = [s for s in painter.strings if s.startswith("row")]
    assert 0 < len(shown) <= control._visible + 1
    assert control.bar.needed()


def test_the_selected_rows_note_is_shown_under_the_rows():
    model = Ranking()
    binding = TableBinding(DATA_TABLE, model)
    model.add(0.3, "a", "b", note="k-NN: 95 % of each burst's neighbours share its class")
    binding.refresh()
    binding.control.select_key("a|b")
    painter = draw(binding.control)
    assert any("neighbours share" in s for s in painter.strings)


def test_the_bar_is_painted_under_the_value():
    control = DataTable([TableColumn("s", display="bar", range=(0.0, 1.0), width=140.0),
                         TableColumn("x")])
    control.set_records([{"s": 1.0, "x": "a"}])
    painter = PixelPainter(420, 120, background=(0, 0, 0, 255))
    control.draw(painter, 0.0, 0.0, 420.0, 120.0)
    bx, by, _bw, _bh = control._body_box
    y = int(by + control._row_h - 4)

    def pixel(x):
        offset = (y * painter.width + int(x)) * 4
        return tuple(painter.px[offset:offset + 3])

    assert tuple(BAR_COLOUR[:3]) in {pixel(bx + 4.0 + f * 132.0) for f in (0.2, 0.5, 0.8)}


# ---- the spec renderers -------------------------------------------------------------


SPEC = {"sections": [
    {"type": "panel", "title": "Ranking", "sections": [
        {"type": "choice", "attr": "method", "options": ["structure", "pearson"]},
        DATA_TABLE,
        {"type": "custom", "key": "parameter_group_table", "options": {"source": "params"}},
        {"type": "table", "columns": [{"key": "x"}]},
    ]},
]}


def test_unsupported_sections_are_honest_about_tables():
    missing = unsupported_sections(SPEC, Ranking())
    assert not any("data_table" in m or "ranked_rows" in m for m in missing)
    assert any("parameter_group_table" in m for m in missing)
    assert any("table: no source" in m for m in missing)
    broken = {"sections": [{"type": "table", "source": "not_there"}]}
    assert unsupported_sections(broken, Ranking()) == ["table 'not_there': the model has no such source"]


def test_tables_are_bound_not_turned_into_setting_rows():
    model = Ranking()
    assert [s.key for s in settings_from_view_spec(SPEC, model)] == ["method"]
    bindings = table_bindings(SPEC, model)
    assert [b.source for b in bindings] == ["ranked_rows", ""]


def test_the_retained_panel_draws_settings_and_table_and_routes_presses():
    model = Ranking()
    spec = {"sections": [SPEC["sections"][0]["sections"][0], DATA_TABLE]}
    panel = ViewSpecPanel(spec, model)
    for score, x in [(0.2, "a"), (0.7, "b")]:
        model.add(score, x, "y")
    painter = RecordingPainter()
    panel.draw(painter, 0.0, 0.0, 420.0, 400.0)
    assert "b" in painter.strings and "▾ Structure" in painter.strings
    table = panel.tables[0].control
    bx, by, _bw, _bh = table._body_box
    panel.press(bx + 30.0, by + table._row_h * 0.5)
    assert model.picked[-1]["x"] == "b"


def test_the_immediate_mode_form_draws_a_table_and_a_click_selects():
    model = Ranking()
    for score, x in [(0.2, "a"), (0.7, "b")]:
        model.add(score, x, "y")
    spec = {"sections": [DATA_TABLE]}
    io, storage, state = emtk.IO(), {}, FormState()

    def frame():
        with emtk.frame(RecordingPainter(), (0, 0, 480, 360), io=io, storage=storage):
            emtk.begin("form", (0, 0, 480, 360))
            draw_form(spec, model, state)
            emtk.end()

    frame()
    table = state.tables["ranked_rows"].control
    bx, by, _bw, _bh = table._body_box
    point = (bx + 40.0, by + table._row_h * 0.5)
    io.mouse_pos = io.mouse_clicked_pos[0] = point
    io.mouse_clicked[0] = io.mouse_down[0] = True
    frame()
    io.mouse_clicked[0] = io.mouse_down[0] = False
    assert model.picked and model.picked[-1]["x"] == "b"
    assert "ranked_rows" in state.rects


# ---- editing ----------------------------------------------------------------------------


class Gates:
    """A gate list: the ndXplorer selection table, as a model."""

    def __init__(self):
        self.rows = [{"name": "Tau", "lower": 1.0, "upper": 3.0, "invert": False,
                      "enabled": True},
                     {"name": "PR", "lower": 0.1, "upper": 0.5, "invert": False,
                      "enabled": True}]
        self.edits = []
        self.deleted = []

    def gate_rows(self):
        return self.rows

    def edit_gate(self, record, key, value):
        self.edits.append((record["name"], key, value))

    def delete_gate(self, record):
        self.deleted.append(record["name"])


GATE_TABLE = {
    "type": "custom", "key": "data_table",
    "options": {
        "source": "gate_rows", "editable": True, "edited_call": "edit_gate",
        "delete_call": "delete_gate",
        "columns": [{"key": "name", "title": "Parameter", "editable": False},
                    {"key": "lower", "title": "Min"}, {"key": "upper", "title": "Max"},
                    {"key": "invert", "title": "Invert"}, {"key": "enabled", "title": "Enable"}],
    },
}


def cell(control, position, column):
    bx, by, _bw, _bh = control._body_box
    x = bx + sum(control._widths[:column]) + control._widths[column] / 2
    return x, by + control._row_h * (position + 0.5)


def test_a_bool_cell_is_a_check_box_a_click_flips():
    model = Gates()
    binding = TableBinding(GATE_TABLE, model)
    control = binding.control
    painter = draw(control)
    assert "True" not in painter.strings and "False" not in painter.strings
    control.press(*cell(control, 1, 3))
    assert model.edits == [("PR", "invert", True)]
    assert model.rows[1]["invert"] is True          # written into the record


def test_a_double_click_opens_a_cell_and_enter_commits_a_number():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.press(*cell(control, 0, 1), clicks=2)
    assert control.editing == (0, "lower")
    for _ in range(10):
        control.key(KEY_BACKSPACE)
    for char in "0.25":
        control.key(0, char)
    painter = draw(control)
    assert "0.25" in painter.strings
    control.key(KEY_RETURN)
    assert model.edits == [("Tau", "lower", 0.25)]
    assert control.editing is None


def test_escape_or_a_typo_leaves_the_cell():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.press(*cell(control, 0, 2), clicks=2)
    control.key(0, "x")
    control.key(KEY_ESCAPE)
    control.press(*cell(control, 0, 2), clicks=2)
    control.key(0, "abc")
    control.press(0.0, 250.0)                       # a click elsewhere commits
    assert model.edits == [] and model.rows[0]["upper"] == 3.0


def test_a_read_only_column_does_not_open():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.press(*cell(control, 0, 0), clicks=2)
    assert control.editing is None


def test_delete_removes_the_selected_row_through_the_model():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.press(*cell(control, 1, 0))
    control.key(KEY_DELETE)
    assert model.deleted == ["PR"]


def test_select_all_marks_every_row_and_delete_removes_them_last_first():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.select_all()
    assert control.selected_indices() == [0, 1]
    painter = draw(control)
    assert painter is not None
    control.key(KEY_DELETE)
    assert model.deleted == ["PR", "Tau"]
    assert control.selected_indices() == []


def test_a_right_click_inside_select_all_keeps_the_selection():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.select_all()
    control.context(*cell(control, 1, 0))
    assert control.selected_indices() == [0, 1]


def test_a_click_after_select_all_selects_one_row_again():
    model = Gates()
    control = TableBinding(GATE_TABLE, model).control
    draw(control)
    control.select_all()
    control.press(*cell(control, 1, 0))
    assert control.selected_indices() == [1]


def test_the_table_draws_in_the_installed_palette():
    from emtk import style

    previous = style.use_palette({"TEXT": (1, 2, 3), "TABLE_HEADER_TEXT": (4, 5, 6)})
    try:
        control = DataTable([TableColumn("x", title="X")])
        control.set_records([{"x": "a"}])
        painter = draw(control)
        colours = {t[5]: tuple(t[6])[:3] for t in painter.texts}
        assert colours["a"] == (1, 2, 3) and colours["X"] == (4, 5, 6)
    finally:
        style.use_palette(previous)
    assert style.TEXT == previous["TEXT"]


def test_a_palette_name_must_exist():
    from emtk import style

    with pytest.raises(KeyError):
        style.use_palette({"TEXTT": (0, 0, 0)})


# -- right click, value shading, column filters, sideways scrolling ------------- #
class Sheet:
    """A wide table of numbers, with a context menu and a shading switch."""

    def __init__(self, columns=3, rows=4):
        self.arrays = {f"c{j}": [float(i * (j + 1)) for i in range(rows)] for j in range(columns)}
        self.menus = []
        self.shading = None

    def sheet(self):
        return self.arrays

    def open_menu(self, record, key, where):
        self.menus.append((record, key))

    def shade(self):
        return self.shading


def sheet_section(**options):
    return {"type": "custom", "key": "data_table",
            "options": dict({"source": "sheet", "context_call": "open_menu",
                             "colour_source": "shade"}, **options)}


def test_a_right_click_selects_the_row_and_reports_row_and_column():
    model = Sheet()
    control = TableBinding(sheet_section(), model).control
    draw(control)
    x, y = cell(control, 2, 1)
    assert control.context(x, y)
    assert model.menus == [(2, "c1")]              # arrays: the record is the index
    assert control.selected_indices() == [2]
    hx = control._header_box[0] + 3
    control.context(hx, control._header_box[1] + 3)
    assert model.menus[-1] == (None, "c0")         # the header: a column, no row


def test_numeric_cells_are_shaded_by_column_or_by_table():
    model = Sheet()
    binding = TableBinding(sheet_section(), model)
    control = binding.control
    assert control.colour_of("c0", 1.0) is None     # off until the model says
    model.shading = "column"
    binding.refresh()
    top, bottom = control.colour_of("c0", 3.0), control.colour_of("c0", 0.0)
    assert top is not None and bottom is not None and top != bottom
    assert control.colour_of("c2", 9.0) == top      # each column's own maximum
    model.shading = "table"
    binding.refresh()
    assert control.colour_of("c0", 3.0) != control.colour_of("c2", 9.0)
    assert control.colour_of("c0", "text") is None


def test_a_column_filter_narrows_the_rows():
    model = Sheet()
    control = TableBinding(sheet_section(), model).control
    control.column_filters = {"c1": "4"}
    assert control.order() == [2]                  # c1 = 0, 2, 4, 6


def test_a_table_wider_than_its_box_scrolls_sideways():
    model = Sheet(columns=12)
    control = TableBinding(sheet_section(min_column_width=80), model).control
    draw(control)
    assert control._hbar_box is not None
    first = control.column_at(control._header_box[0] + 3).key
    control.scroll_columns(3)
    draw(control)
    assert first == "c0" and control.column_at(control._header_box[0] + 3).key == "c3"
    bx, by, bw, bh = control._hbar_box
    control.press(bx + bw - 1, by + bh / 2)        # the bar's right end: the last column
    control.release()
    assert control.first_column == 11


def test_fit_columns_sizes_to_the_contents():
    control = DataTable([TableColumn("a", title="A"), TableColumn("b", title="B")])
    control.set_records([{"a": "a much longer cell than the title", "b": "x"}])
    draw(control)
    even = list(control._widths)
    control.fit_columns()
    draw(control)
    assert control._widths[0] > control._widths[1] and even[0] == even[1]


def test_an_expanding_table_leaves_its_reserve_free():
    from emtk.view_form import FormState, draw_form

    model = Sheet()
    spec = {"sections": [
        {"type": "custom", "key": "data_table",
         "options": {"source": "sheet", "expand": True, "reserve": 50}},
        {"type": "button_row", "buttons": [{"label": "OK", "action": "ok"}]}]}
    state = FormState()
    with emtk.frame(RecordingPainter(), (0, 0, 400, 300), io=emtk.IO(), storage={}):
        emtk.begin("form", (0, 0, 400, 300))
        draw_form(spec, model, state)
        emtk.end()
    table, button = state.rects["sheet"], state.rects["ok"]
    assert button[1] + button[3] <= 300 and table[3] < 300 - 50 + 1


# ---- a parameter table: per-cell rules, muted rows, the column picker -------------------


class Parameters:
    """A fit's parameter table: some values are borrowed, some bounds switched off."""

    def __init__(self):
        self.rows = [
            {"name": "a", "value": 1.0, "follower": False, "bounded": True, "lo": 0.0},
            {"name": "b", "value": 2.0, "follower": True, "bounded": True, "lo": 0.0},
            {"name": "c", "value": 3.0, "follower": False, "bounded": False, "lo": 0.0},
        ]
        self.edits = []

    def parameter_rows(self):
        return self.rows

    def edit(self, record, key, value):
        self.edits.append((record["name"], key, value))

    def may_edit(self, record, key):
        if key == "value":
            return not record["follower"]
        if key == "lo":
            return record["bounded"]
        return True


PARAMETER_TABLE = {
    "type": "custom", "key": "data_table",
    "options": {
        "source": "parameter_rows", "editable": True, "edited_call": "edit",
        "editable_call": "may_edit", "muted_key": "follower", "status": True,
        "column_picker": True, "filter": True,
        "columns": [{"key": "name", "title": "Parameter", "editable": False},
                    {"key": "value", "title": "Value"}, {"key": "lo", "title": "Lo"}],
    },
}


def test_a_cell_the_model_refuses_does_not_open():
    """A follower's value is its master's; a bound counts only while it is on."""
    model = Parameters()
    control = TableBinding(PARAMETER_TABLE, model).control
    draw(control)
    control.press(*cell(control, 1, 1), clicks=2)
    assert control.editing is None, "a borrowed value opened for typing"
    control.press(*cell(control, 2, 2), clicks=2)
    assert control.editing is None, "a switched-off bound opened for typing"
    control.press(*cell(control, 0, 1), clicks=2)
    assert control.editing == (0, "value")


def test_a_muted_row_is_drawn_dimmed():
    from emtk import style

    model = Parameters()
    control = TableBinding(PARAMETER_TABLE, model).control
    painter = draw(control)
    colour = {text[5]: text[6] for text in painter.texts}
    assert colour["b"] == style.DIM and colour["a"] == style.TEXT


def test_the_status_line_counts_rows_and_columns_and_says_when_filtered():
    model = Parameters()
    control = TableBinding(PARAMETER_TABLE, model).control
    assert "3 rows × 3 columns" in draw(control).strings
    control.filter.set_text("b")
    assert "1 of 3 rows × 3 columns" in draw(control).strings


def test_the_header_opens_a_column_picker_that_hides_and_shows():
    model = Parameters()
    spec = {"sections": [PARAMETER_TABLE]}
    io, storage, state = emtk.IO(), {}, FormState()

    def frame():
        with emtk.frame(RecordingPainter(), (0, 0, 480, 360), io=io, storage=storage):
            emtk.begin("form", (0, 0, 480, 360))
            draw_form(spec, model, state)
            emtk.end()
        for i in range(3):
            io.mouse_clicked[i] = io.mouse_released[i] = False

    frame()
    control = state.tables["parameter_rows"].control
    hx, hy, _hw, hh = control._header_box
    io.mouse_pos = io.mouse_clicked_pos[1] = (hx + 30.0, hy + hh / 2)
    io.mouse_clicked[1] = io.mouse_down[1] = True
    frame()
    io.mouse_down[1] = False
    frame()
    panel = control.picker_panel
    assert panel is not None and panel.open, "a right click on the header opened nothing"
    assert [row.checked for row in panel.entries] == [True, True, True]

    control.set_column_hidden("lo", True)
    assert [c.key for c in control.visible_columns()] == ["name", "value"]
    assert "3 rows × 2 columns" in draw(control).strings
    TableBinding.refresh(state.tables["parameter_rows"])
    assert "lo" in control.hidden, "a refresh brought a hidden column back"
    for key in ("name", "value"):
        control.set_column_hidden(key, True)
    assert len(control.visible_columns()) == 1, "the picker hid the last column"



def test_a_column_can_opt_out_of_value_shading():
    """A row number is a number with no magnitude worth a colour."""
    model = Parameters()
    for i, row in enumerate(model.rows):
        row["row"] = i + 1
    section = {"type": "custom", "key": "data_table",
               "options": {"source": "parameter_rows",
                           "columns": [{"key": "row", "shade": False}, {"key": "value"}]}}
    control = TableBinding(section, model).control
    control.colour_values = "column"
    assert control.colour_of("row", 2) is None
    assert control.colour_of("value", 2.0) is not None


def test_fitted_columns_fill_the_box_and_do_not_scroll_when_they_can_narrow():
    """Eleven columns in a 630-pixel panel: all shown, values whole, no empty half.

    Declared widths once took the room, the rest fell to the minimum, the sum
    tipped over the box and the table scrolled -- past its first three columns
    -- while half the panel stayed empty and every value lost its last digit.
    """
    class Wide:
        def rows(self):
            return [{"row": i + 1, "owner": "Lifetime (magic angle)", "local": "",
                     "parameter": name, "value": v, "fixed": False, "lo": 0.001, "hi": 2048.0,
                     "bounded": True, "error": None, "link": ""}
                    for i, (name, v) in enumerate([("timeshift", 0.0), ("n0", 2.5)])]

    titles = ("Row", "Owner", "Local", "Parameter", "Value", "Fixed", "Lo", "Hi", "Bounds",
              "Error", "Link row")
    columns = [{"key": k, "title": t} for k, t in zip(
        ("row", "owner", "local", "parameter", "value", "fixed", "lo", "hi", "bounded",
         "error", "link"), titles)]
    section = {"type": "custom", "key": "data_table",
               "options": {"source": "rows", "columns": columns, "fit_columns": True,
                           "min_column_width": 36}}
    control = TableBinding(section, Wide()).control
    painter = draw(control, w=630.0, h=300.0)
    assert control._hbar_box is None, "the table scrolled although it could narrow"
    assert control.first_column == 0
    assert abs(sum(control._widths) - (630.0 - (control.bar.width if control.bar.needed() else 0))) < 1.0
    for text in ("2048", "0.001", "2.5", "timeshift"):
        assert text in painter.strings, f"{text} was cut short"


def test_fitted_columns_share_spare_room_instead_of_leaving_it_empty():
    model = Parameters()
    section = {"type": "custom", "key": "data_table",
               "options": {"source": "parameter_rows", "fit_columns": True,
                           "columns": [{"key": "name"}, {"key": "value"}]}}
    control = TableBinding(section, model).control
    draw(control, w=600.0, h=200.0)
    assert sum(control._widths) == pytest.approx(600.0, abs=1.0)
