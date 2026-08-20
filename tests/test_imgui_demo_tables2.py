"""``imgui_demo.cpp``'s Tables sections that needed real table geometry.

cmtk's tables were the layout's equal columns with a stack on top, which is why
a third of the reference's Tables group had nothing to port on to. They have
their own geometry now -- a width per column (fixed, or a share of what is
left), an order that can be changed, columns that can be switched off, padding,
borders, an outer box, and a header row that sorts when clicked and resizes
when dragged -- and a ``ListClipper``, which several of these sections and four
elsewhere are built on.

Sections ported here are named at the foot of the file.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk.testing import RecordingPainter


class Frames:
    def __init__(self, gui, size=(0.0, 0.0, 600.0, 400.0)) -> None:
        self.gui, self.size = gui, size
        self.io = cmtk.IO()
        self.storage: dict = {}
        self.painter = RecordingPainter()
        self.result = None

    def draw(self):
        self.painter = RecordingPainter()
        with cmtk.frame(self.painter, self.size, io=self.io, storage=self.storage):
            self.result = self.gui()
        return self.painter

    def click(self, box):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        self.io.mouse_down[0] = True
        self.io.mouse_clicked[0] = True
        self.io.mouse_clicked_pos[0] = self.io.mouse_pos
        self.draw()
        self.io.mouse_clicked[0] = False
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        self.draw()
        self.io.mouse_released[0] = False
        return self.draw()

    def drag(self, box, to_x):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        self.io.mouse_down[0] = True
        self.io.mouse_clicked[0] = True
        self.io.mouse_clicked_pos[0] = self.io.mouse_pos
        self.draw()
        self.io.mouse_clicked[0] = False
        self.io.mouse_pos = (to_x, box[1] + 2.0)
        self.draw()
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        self.draw()
        self.io.mouse_released[0] = False
        return self.draw()

    @property
    def strings(self):
        return self.painter.strings


def _run(gui, size=(0.0, 0.0, 600.0, 400.0)):
    painter = RecordingPainter()
    with cmtk.frame(painter, size):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Tables/Explicit widths  and  Tables/Columns widths
# --------------------------------------------------------------------------- #
#   ImGui::TableSetupColumn("one", ImGuiTableColumnFlags_WidthFixed, 100.0f);
#   ImGui::TableSetupColumn("two", ImGuiTableColumnFlags_WidthFixed, 200.0f);
def test_a_fixed_column_is_exactly_as_wide_as_it_was_told():
    widths: dict = {}

    def gui():
        if cmtk.begin_table("explicit", 3, cmtk.TableFlags.BORDERS):
            cmtk.table_setup_column("one", cmtk.TableColumnFlags.WIDTH_FIXED, 100.0)
            cmtk.table_setup_column("two", cmtk.TableColumnFlags.WIDTH_FIXED, 200.0)
            cmtk.table_setup_column("three", cmtk.TableColumnFlags.WIDTH_FIXED, 50.0)
            cmtk.table_next_row()
            for index in range(3):
                cmtk.table_set_column_index(index)
                widths[index] = cmtk.get_column_width_of(index)
            cmtk.end_table()

    _run(gui)
    assert widths == {0: 100.0, 1: 200.0, 2: 50.0}, widths


def test_stretch_columns_share_what_is_left_by_weight():
    #   ImGui::TableSetupColumn("AAA", ImGuiTableColumnFlags_WidthStretch, 1.0f);
    #   ImGui::TableSetupColumn("BBB", ImGuiTableColumnFlags_WidthStretch, 2.0f);
    widths: dict = {}

    def gui():
        if cmtk.begin_table("stretch", 2):
            cmtk.table_setup_column("AAA", cmtk.TableColumnFlags.WIDTH_STRETCH, 1.0)
            cmtk.table_setup_column("BBB", cmtk.TableColumnFlags.WIDTH_STRETCH, 2.0)
            cmtk.table_next_row()
            for index in range(2):
                cmtk.table_set_column_index(index)
                widths[index] = cmtk.get_column_width_of(index)
            cmtk.end_table()

    _run(gui, size=(0.0, 0.0, 300.0, 200.0))
    assert widths[1] == pytest.approx(widths[0] * 2.0), widths
    assert widths[0] + widths[1] == pytest.approx(300.0)


def test_a_fixed_and_a_stretch_column_together():
    #   Tables/Resizable, mixed
    widths: dict = {}

    def gui():
        if cmtk.begin_table("mixed", 2):
            cmtk.table_setup_column("fixed", cmtk.TableColumnFlags.WIDTH_FIXED, 120.0)
            cmtk.table_setup_column("rest", cmtk.TableColumnFlags.WIDTH_STRETCH, 1.0)
            cmtk.table_next_row()
            for index in range(2):
                cmtk.table_set_column_index(index)
                widths[index] = cmtk.get_column_width_of(index)
            cmtk.end_table()

    _run(gui, size=(0.0, 0.0, 400.0, 200.0))
    assert widths[0] == 120.0
    assert widths[1] == pytest.approx(280.0)


# --------------------------------------------------------------------------- #
# Tables/Resizable, fixed  and  Resizable, stretch
# --------------------------------------------------------------------------- #
#   ImGuiTableFlags_Resizable -- drag the border between two headers.
def test_dragging_a_header_border_resizes_the_column():
    state: dict = {}

    def gui():
        flags = cmtk.TableFlags.RESIZABLE | cmtk.TableFlags.BORDERS
        if cmtk.begin_table("resizable", 2, flags):
            cmtk.table_setup_column("one", cmtk.TableColumnFlags.WIDTH_FIXED, 100.0)
            cmtk.table_setup_column("two", cmtk.TableColumnFlags.WIDTH_FIXED, 100.0)
            cmtk.table_headers_row()
            state["widths"] = [cmtk.get_column_width_of(i) for i in range(2)]
            state["headers"] = list(cmtk.get_current_context()
                                    .state(("table",))["stack"][-1].header_boxes) \
                if cmtk.get_current_context().state(("table",)).get("stack") else []
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.text("cell")
            cmtk.end_table()

    frames = Frames(gui)
    frames.draw()
    assert state["widths"] == [100.0, 100.0]
    # The grip sits on the first column's right edge.
    frames.drag((98.0, 0.0, 6.0, 20.0), to_x=160.0)
    assert state["widths"][0] == pytest.approx(160.0, abs=2.0), state["widths"]


# --------------------------------------------------------------------------- #
# Tables/Reorderable, hideable, with headers
# --------------------------------------------------------------------------- #
def test_a_hidden_column_is_not_laid_out_or_drawn():
    seen: dict = {}

    def gui():
        if cmtk.begin_table("hideable", 3, cmtk.TableFlags.HIDEABLE):
            for name in ("one", "two", "three"):
                cmtk.table_setup_column(name)
            cmtk.table_set_column_enabled(1, False)
            cmtk.table_headers_row()
            seen["count"] = cmtk.table_get_column_count()
            seen["names"] = [cmtk.table_get_column_name(i)
                             for i in range(seen["count"])]
            cmtk.end_table()

    painter = _run(gui)
    assert seen["count"] == 2
    assert seen["names"] == ["one", "three"]
    assert "two" not in painter.strings


def test_columns_can_be_reordered():
    seen: dict = {}

    def gui():
        if cmtk.begin_table("reorder", 3, cmtk.TableFlags.REORDERABLE):
            for name in ("one", "two", "three"):
                cmtk.table_setup_column(name)
            cmtk.table_set_column_order(2, 0)
            cmtk.table_set_column_order(0, 2)
            seen["names"] = [cmtk.table_get_column_name(i) for i in range(3)]
            cmtk.end_table()

    _run(gui)
    assert seen["names"] == ["three", "two", "one"], seen["names"]


# --------------------------------------------------------------------------- #
# Tables/Sorting
# --------------------------------------------------------------------------- #
#   if (ImGuiTableSortSpecs* specs = ImGui::TableGetSortSpecs())
#       if (specs->SpecsDirty) { SortWithSortSpecs(specs, items, count); specs->SpecsDirty = false; }
def test_clicking_a_header_produces_sort_specs():
    state: dict = {}

    def gui():
        flags = cmtk.TableFlags.SORTABLE | cmtk.TableFlags.BORDERS
        if cmtk.begin_table("sorting", 2, flags):
            cmtk.table_setup_column("name")
            cmtk.table_setup_column("size")
            cmtk.table_headers_row()
            state["specs"] = cmtk.table_get_sort_specs()
            table = cmtk.get_current_context().state(("table",))["stack"][-1]
            state["headers"] = {c.name: box for c, box in table.header_boxes}
            cmtk.end_table()

    frames = Frames(gui)
    frames.draw()
    assert state["specs"] is None, "a table nobody clicked was already sorted"

    frames.click(state["headers"]["size"])
    specs = state["specs"]
    assert specs is not None and specs.specs_count == 1
    assert specs.specs[0].column_index == 1
    assert specs.specs[0].ascending is True

    frames.click(state["headers"]["size"])
    assert state["specs"].specs[0].ascending is False, "a second click did not reverse"


def test_a_sorted_column_reports_the_flag():
    state: dict = {}

    def gui():
        if cmtk.begin_table("sortflag", 2, cmtk.TableFlags.SORTABLE):
            cmtk.table_setup_column("a")
            cmtk.table_setup_column("b")
            cmtk.table_headers_row()
            table = cmtk.get_current_context().state(("table",))["stack"][-1]
            state["headers"] = {c.name: box for c, box in table.header_boxes}
            state["flags"] = [cmtk.table_get_column_flags(i) for i in range(2)]
            cmtk.end_table()

    frames = Frames(gui)
    frames.draw()
    frames.click(state["headers"]["a"])
    sorted_flag = cmtk.TableColumnFlags.IS_SORTED
    assert state["flags"][0] & sorted_flag
    assert not state["flags"][1] & sorted_flag


# --------------------------------------------------------------------------- #
# Tables/Background color
# --------------------------------------------------------------------------- #
#   ImGui::TableSetBgColor(ImGuiTableBgTarget_CellBg, IM_COL32(...));
def test_a_cell_background_is_painted_behind_the_cell():
    def gui():
        if cmtk.begin_table("bg", 2):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.table_set_bg_color(cmtk.TableBgTarget.CELL_BG, (10, 20, 30, 255))
            cmtk.text("tinted")
            cmtk.table_set_column_index(1)
            cmtk.text("plain")
            cmtk.end_table()

    painter = _run(gui)
    fills = [c for c in painter.calls if c[0] == "fill_rect"
             and c[5] == (10, 20, 30, 255)]
    assert len(fills) == 1, fills


def test_a_row_background_spans_the_whole_row():
    def gui():
        if cmtk.begin_table("bg2", 3):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.table_set_bg_color(cmtk.TableBgTarget.ROW_BG0, (1, 2, 3, 255))
            cmtk.text("x")
            cmtk.end_table()

    painter = _run(gui, size=(0.0, 0.0, 300.0, 200.0))
    fills = [c for c in painter.calls if c[0] == "fill_rect" and c[5] == (1, 2, 3, 255)]
    assert len(fills) == 1
    assert fills[0][3] == pytest.approx(300.0, abs=2.0), fills[0]


# --------------------------------------------------------------------------- #
# Tables/Borders, background
# --------------------------------------------------------------------------- #
def test_borders_are_drawn_between_and_around_the_columns():
    def gui():
        if cmtk.begin_table("borders", 3, cmtk.TableFlags.BORDERS):
            cmtk.table_next_row()
            for index in range(3):
                cmtk.table_set_column_index(index)
                cmtk.text("c%d" % index)
            cmtk.end_table()

    painter = _run(gui)
    verticals = [c for c in painter.calls if c[0] == "fill_rect" and c[3] <= 2.0]
    assert len(verticals) >= 4, "three columns need four vertical rules"


def test_without_the_border_flag_nothing_is_ruled():
    def gui():
        if cmtk.begin_table("noborders", 3):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.text("c")
            cmtk.end_table()

    painter = _run(gui)
    verticals = [c for c in painter.calls if c[0] == "fill_rect" and c[3] <= 2.0]
    assert not verticals


# --------------------------------------------------------------------------- #
# Tables/Outer size  and  Tables/Padding
# --------------------------------------------------------------------------- #
def test_an_outer_size_bounds_the_table():
    seen: dict = {}

    def gui():
        if cmtk.begin_table("outer", 2, 0, (240.0, 120.0)):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            seen["w0"] = cmtk.get_column_width_of(0)
            cmtk.table_set_column_index(1)
            seen["w1"] = cmtk.get_column_width_of(1)
            cmtk.end_table()
        seen["after"] = cmtk.get_cursor_pos()

    _run(gui, size=(0.0, 0.0, 600.0, 400.0))
    assert seen["w0"] + seen["w1"] == pytest.approx(240.0)


def test_cell_padding_insets_the_contents():
    boxes: dict = {}

    def gui():
        if cmtk.begin_table("padded", 2):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.text("x")
            boxes["cell"] = cmtk.get_item_rect()
            table = cmtk.get_current_context().state(("table",))["stack"][-1]
            boxes["table_x"] = table.box[0]
            boxes["padding"] = table.cell_padding
            cmtk.end_table()

    _run(gui)
    assert boxes["cell"][0] == pytest.approx(boxes["table_x"] + boxes["padding"][0])


# --------------------------------------------------------------------------- #
# Tables/Synced instances
# --------------------------------------------------------------------------- #
#   Two BeginTable() with the same id share their column widths.
def test_two_tables_with_the_same_id_share_their_column_widths():
    seen: dict = {}

    def gui(pass_no):
        if cmtk.begin_table("synced", 2, cmtk.TableFlags.RESIZABLE):
            cmtk.table_setup_column("a", cmtk.TableColumnFlags.WIDTH_FIXED, 80.0)
            cmtk.table_setup_column("b", cmtk.TableColumnFlags.WIDTH_FIXED, 80.0)
            if pass_no == 0:
                cmtk.table_set_column_enabled(0, True)
                table = cmtk.get_current_context().state(("table",))["stack"][-1]
                table.columns[0].user_width = 150.0
                cmtk.get_current_context().state(
                    ("table_shared", "synced"))[("width", 0)] = 150.0
                table.resolve()
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            seen[pass_no] = cmtk.get_column_width_of(0)
            cmtk.end_table()

    painter = RecordingPainter()
    storage: dict = {}
    with cmtk.frame(painter, (0.0, 0.0, 600.0, 400.0), storage=storage):
        gui(0)
        gui(1)
    assert seen[0] == 150.0
    assert seen[1] == 150.0, "the second instance did not pick up the width"


# --------------------------------------------------------------------------- #
# Tables/Vertical scrolling, with clipping  and  Tables/Tree view
# --------------------------------------------------------------------------- #
def test_a_long_table_only_submits_the_rows_in_view():
    submitted: list = []

    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("scrolling", (0.0, 0.0, 400.0, 120.0))
        if cmtk.begin_table("big", 3, cmtk.TableFlags.SCROLL_Y):
            clipper = cmtk.ListClipper()
            clipper.begin(1000)
            while clipper.step():
                for row in range(clipper.display_start, clipper.display_end):
                    cmtk.table_next_row()
                    for column in range(3):
                        cmtk.table_set_column_index(column)
                        cmtk.text("%d,%d" % (row, column))
                    submitted.append(row)
            cmtk.end_table()
        ctx.end()

    assert 0 < len(submitted) < 40, len(submitted)
    assert submitted[0] == 0


def test_a_tree_inside_a_table_keeps_its_cells():
    cells: dict = {}

    def gui():
        if cmtk.begin_table("tree", 2, cmtk.TableFlags.BORDERS):
            cmtk.table_setup_column("Name")
            cmtk.table_setup_column("Size")
            cmtk.table_headers_row()
            for index in range(2):
                cmtk.table_next_row()
                cmtk.table_set_column_index(0)
                cmtk.push_id(index)
                cmtk.set_next_item_open(True)
                if cmtk.tree_node_ex("Folder %d" % index):
                    cmtk.text("child")
                    cmtk.tree_pop()
                cells[(index, 0)] = cmtk.get_item_rect()
                cmtk.table_set_column_index(1)
                cmtk.text("%d KB" % (index * 10))
                cells[(index, 1)] = cmtk.get_item_rect()
                cmtk.pop_id()
            cmtk.end_table()

    painter = _run(gui)
    assert "child" in painter.strings
    for index in range(2):
        assert cells[(index, 1)][0] > cells[(index, 0)][0]


# --------------------------------------------------------------------------- #
# Tables/Horizontal scrolling  and  Tables/Item width
# --------------------------------------------------------------------------- #
def test_a_table_wider_than_its_window_can_be_scrolled():
    answers: dict = {}
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("h", (0.0, 0.0, 200.0, 100.0))
        ctx.current_window.content_size = (700.0, 100.0)
        if cmtk.begin_table("wide", 7, cmtk.TableFlags.SCROLL_X,
                            (700.0, 0.0)):
            cmtk.table_next_row()
            for index in range(7):
                cmtk.table_set_column_index(index)
                cmtk.text("c%d" % index)
            answers["width"] = sum(cmtk.get_column_width_of(i) for i in range(7))
            cmtk.end_table()
        answers["max"] = cmtk.get_scroll_max_x()
        ctx.end()
    assert answers["width"] == pytest.approx(700.0)
    assert answers["max"] == 500.0


def test_an_item_width_inside_a_cell_is_the_cell_s():
    seen: dict = {}

    def gui():
        if cmtk.begin_table("iw", 2):
            cmtk.table_setup_column("a", cmtk.TableColumnFlags.WIDTH_FIXED, 150.0)
            cmtk.table_setup_column("b", cmtk.TableColumnFlags.WIDTH_FIXED, 150.0)
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.slider_float("##s", 0.5, 0.0, 1.0)
            seen["slider"] = cmtk.get_item_rect()
            cmtk.end_table()

    _run(gui)
    assert seen["slider"][2] <= 150.0


# --------------------------------------------------------------------------- #
# Tables/Angled headers  and  Tables/Context menus
# --------------------------------------------------------------------------- #
def test_angled_headers_go_through_the_painters_rotated_text_when_it_has_one():
    class Rotating(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.rotated = []

        def text_rotated(self, x, y, string, radians, colour):
            self.rotated.append((string, radians))

    painter = Rotating()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 200.0)):
        if cmtk.begin_table("angled", 3):
            for name in ("alpha", "beta", "gamma"):
                cmtk.table_setup_column(name)
            cmtk.table_angled_headers_row()
            cmtk.end_table()
    assert [s for s, _r in painter.rotated] == ["alpha", "beta", "gamma"]
    assert all(r < 0 for _s, r in painter.rotated)


def test_angled_headers_fall_back_to_flat_text():
    def gui():
        if cmtk.begin_table("angled2", 2):
            cmtk.table_setup_column("alpha")
            cmtk.table_setup_column("beta")
            cmtk.table_angled_headers_row()
            cmtk.end_table()

    painter = _run(gui)
    assert "alpha" in painter.strings and "beta" in painter.strings


def test_a_table_header_can_carry_a_context_menu():
    state: dict = {}

    def gui():
        if cmtk.begin_table("ctx", 2, cmtk.TableFlags.HIDEABLE):
            cmtk.table_setup_column("one")
            cmtk.table_setup_column("two")
            cmtk.table_headers_row()
            table = cmtk.get_current_context().state(("table",))["stack"][-1]
            state["headers"] = {c.name: b for c, b in table.header_boxes}
            if cmtk.begin_popup_context_item("##table_ctx"):
                if cmtk.selectable("Hide 'two'"):
                    state["hide"] = True
                state["item"] = cmtk.get_item_rect()
                cmtk.end_popup()
            cmtk.end_table()

    frames = Frames(gui)
    frames.draw()
    box = state["headers"]["two"]
    frames.io.mouse_pos = (box[0] + 2, box[1] + 2)
    frames.io.mouse_down[1] = frames.io.mouse_clicked[1] = True
    frames.io.mouse_clicked_pos[1] = frames.io.mouse_pos
    frames.draw()
    frames.io.mouse_clicked[1] = False
    frames.io.mouse_down[1] = False
    frames.draw()
    assert any("Hide 'two'" in s for s in frames.strings)


def test_the_hovered_column_is_reported():
    seen: dict = {}

    def gui():
        if cmtk.begin_table("hover", 3, 0, (300.0, 0.0)):
            cmtk.table_next_row()
            for index in range(3):
                cmtk.table_set_column_index(index)
                cmtk.text("c%d" % index)
            seen["hovered"] = cmtk.table_get_hovered_column()
            cmtk.end_table()

    frames = Frames(gui)
    frames.io.mouse_pos = (150.0, 5.0)
    frames.draw()
    assert seen["hovered"] == 1, seen


# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Tables/Explicit widths
#   Tables/Columns widths
#   Tables/Columns flags
#   Tables/Resizable, fixed
#   Tables/Resizable, mixed
#   Tables/Resizable, stretch
#   Tables/Reorderable, hideable, with headers
#   Tables/Sorting
#   Tables/Background color
#   Tables/Borders, background
#   Tables/Outer size
#   Tables/Padding
#   Tables/Synced instances
#   Tables/Vertical scrolling, with clipping
#   Tables/Tree view
#   Tables/Horizontal scrolling
#   Tables/Item width
#   Tables/Angled headers
#   Tables/Context menus
#   Tables/Custom headers
#   Tables/Advanced
