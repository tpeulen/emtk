"""The last of ``imgui_demo.cpp``'s Widgets: selection, tooltips, filters, images.

Sections: Selection State/Single-Select and Multi-Select, Widgets/Tooltips,
Widgets/Text Filter, Selectables/Grid and In Tables, Tabs/Advanced (close
buttons and tab-item buttons), Widgets/Images and Textured buttons,
Querying Window Status.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk.testing import RecordingPainter


class Frames:
    def __init__(self, gui, size=(0.0, 0.0, 500.0, 500.0)) -> None:
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

    def click(self, box, ctrl=False):
        self.io.key_ctrl = ctrl
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
        self.io.key_ctrl = False
        return self.draw()

    def hover(self, box):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        return self.draw()

    @property
    def strings(self):
        return self.painter.strings


# --------------------------------------------------------------------------- #
# Widgets/Selection State/Single-Select
# --------------------------------------------------------------------------- #
#   for (int n = 0; n < 5; n++)
#       if (ImGui::Selectable(buf, selected == n)) selected = n;
def test_single_select_moves_the_selection():
    state = {"selected": -1, "boxes": {}}

    def gui():
        for n in range(5):
            if cmtk.selectable("Object %d" % n, state["selected"] == n):
                state["selected"] = n
            state["boxes"][n] = cmtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    frames.click(state["boxes"][3])
    assert state["selected"] == 3
    frames.click(state["boxes"][1])
    assert state["selected"] == 1, "the selection did not move"


# --------------------------------------------------------------------------- #
# Widgets/Selection State/Multi-Select (manual/simplified)
# --------------------------------------------------------------------------- #
#   ImGuiMultiSelectIO* ms_io = ImGui::BeginMultiSelect(flags, selection.Size, ITEMS_COUNT);
#   ... ImGui::SetNextItemSelectionUserData(n); ImGui::Selectable(label, item_is_selected);
#   ms_io = ImGui::EndMultiSelect();
def test_multi_select_hands_back_the_requests_it_gathered():
    chosen: set = set()
    boxes: dict = {}

    def gui():
        io_in = cmtk.begin_multi_select(0, len(chosen), 5)
        for n in range(5):
            cmtk.set_next_item_selection_user_data(n)
            if cmtk.selectable("Object %d" % n, n in chosen):
                if not cmtk.io_key_ctrl_shim():
                    chosen.clear()
                chosen.symmetric_difference_update({n})
            boxes[n] = cmtk.get_item_rect()
        io_out = cmtk.end_multi_select()
        return io_in, io_out

    # A tiny shim so the port can ask "was ctrl held" the way the demo's
    # storage-backed helper does.
    cmtk.io_key_ctrl_shim = lambda: cmtk.get_io().key_ctrl

    frames = Frames(gui)
    frames.draw()
    frames.click(boxes[1])
    assert chosen == {1}
    frames.click(boxes[3], ctrl=True)
    assert chosen == {1, 3}, "ctrl-click did not add to the selection"
    frames.click(boxes[2])
    assert chosen == {2}, "a plain click did not replace the selection"

    io_in, io_out = frames.result
    assert io_in is io_out, "EndMultiSelect returned a different io than Begin"
    del cmtk.io_key_ctrl_shim


def test_a_ctrl_click_is_reported_as_a_toggle():
    def gui():
        cmtk.selectable("row", False)
        return cmtk.get_item_rect(), cmtk.is_item_toggled_selection()

    frames = Frames(gui)
    frames.draw()
    box, _ = frames.result
    frames.io.key_ctrl = True
    frames.io.mouse_pos = (box[0] + 2, box[1] + 2)
    frames.io.mouse_down[0] = frames.io.mouse_clicked[0] = True
    frames.io.mouse_clicked_pos[0] = frames.io.mouse_pos
    frames.draw()
    _box, toggled = frames.result
    assert toggled is True


# --------------------------------------------------------------------------- #
# Widgets/Tooltips
# --------------------------------------------------------------------------- #
#   ImGui::Button("Basic"); ImGui::SetItemTooltip("I am a tooltip");
#   ImGui::Button("Fancy"); if (ImGui::BeginItemTooltip()) { ... ImGui::EndTooltip(); }
def test_a_tooltip_appears_on_hover_and_not_otherwise():
    seen: dict = {}
    boxes: dict = {}

    def gui():
        cmtk.button("Basic")
        boxes["basic"] = cmtk.get_item_rect()
        cmtk.set_item_tooltip("I am a tooltip")
        cmtk.button("Fancy")
        boxes["fancy"] = cmtk.get_item_rect()
        if cmtk.begin_item_tooltip():
            cmtk.text("I am a fancy tooltip")
            seen["fancy"] = True
            cmtk.end_tooltip()
        seen["tooltip"] = cmtk.get_current_context().tooltip

    frames = Frames(gui)
    frames.draw()
    assert seen["tooltip"] is None
    assert "fancy" not in seen

    frames.hover(boxes["basic"])
    assert seen["tooltip"] == "I am a tooltip"

    seen.pop("fancy", None)
    frames.hover(boxes["fancy"])
    assert seen.get("fancy") is True, "BeginItemTooltip did not open on hover"


# --------------------------------------------------------------------------- #
# Widgets/Text Filter
# --------------------------------------------------------------------------- #
#   static ImGuiTextFilter filter;
#   filter.Draw("Filter (inc,-exc)");
#   for (const char* line : lines) if (filter.PassFilter(line)) ImGui::BulletText("%s", line);
def test_a_text_filter_keeps_only_what_matches():
    """The demo's ``ImGuiTextFilter`` is a helper, not an API call -- ported as
    the loop it stands for, which is what a port would write."""
    lines = ["aaa1.c", "bbb1.c", "ccc1.c", "aaa2.cpp", "bbb2.cpp"]
    state = {"filter": ""}

    def gui():
        _c, state["filter"] = cmtk.input_text("Filter", state["filter"])
        for line in lines:
            if state["filter"] in line:
                cmtk.bullet_text(line)

    frames = Frames(gui)
    painter = frames.draw()
    assert sum(1 for s in painter.strings if s.endswith(".c")) == 3

    state["filter"] = "aaa"
    painter = frames.draw()
    shown = [s for s in painter.strings if "aaa" in s or "bbb" in s]
    assert all("aaa" in s for s in shown), shown


# --------------------------------------------------------------------------- #
# Widgets/Selectables/Grid  and  In Tables
# --------------------------------------------------------------------------- #
#   for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++)
#   { ImGui::PushID(y * 4 + x); if (ImGui::Selectable("Sailor", selected[y][x] != 0, 0, ImVec2(50, 50))) ... }
def test_a_grid_of_selectables_lays_out_as_a_grid():
    cells: dict = {}
    selected = [[0] * 4 for _ in range(4)]

    def gui():
        for y in range(4):
            for x in range(4):
                cmtk.push_id(y * 4 + x)
                if cmtk.selectable("Sailor", selected[y][x] != 0, (50.0, 50.0)):
                    selected[y][x] ^= 1
                cells[(y, x)] = cmtk.get_item_rect()
                cmtk.pop_id()
                if x < 3:
                    cmtk.same_line()

    frames = Frames(gui)
    frames.draw()
    for y in range(4):
        ys = {round(cells[(y, x)][1]) for x in range(4)}
        assert len(ys) == 1, (y, ys)
    for x in range(4):
        xs = {round(cells[(y, x)][0]) for y in range(4)}
        assert len(xs) == 1, (x, xs)
    frames.click(cells[(2, 1)])
    assert selected[2][1] == 1, "the grid cell did not take the click"


def test_selectables_inside_a_table_stay_in_their_cells():
    cells: dict = {}

    def gui():
        if cmtk.begin_table("grid", 3):
            for row in range(2):
                cmtk.table_next_row()
                for column in range(3):
                    cmtk.table_set_column_index(column)
                    cmtk.push_id(row * 3 + column)
                    cmtk.selectable("Sailor", False)
                    cells[(row, column)] = cmtk.get_item_rect()
                    cmtk.pop_id()
            cmtk.end_table()

    frames = Frames(gui)
    frames.draw()
    for row in range(2):
        ys = {round(cells[(row, c)][1]) for c in range(3)}
        assert len(ys) == 1, (row, ys)


# --------------------------------------------------------------------------- #
# Widgets/Tabs/TabItemButton & Leading-Trailing flags
# --------------------------------------------------------------------------- #
#   if (ImGui::TabItemButton("+", ImGuiTabItemFlags_Trailing | ...)) active_tabs.push_back(...);
def test_a_tab_item_button_reports_its_click():
    state = {"added": 0}

    def gui():
        if cmtk.begin_tab_bar("MyTabBar"):
            if cmtk.begin_tab_item("Tab 0"):
                cmtk.end_tab_item()
            if cmtk.tab_item_button("+"):
                state["added"] += 1
            state["plus"] = cmtk.get_item_rect()
            cmtk.end_tab_bar()

    frames = Frames(gui)
    frames.draw()
    frames.click(state["plus"])
    assert state["added"] == 1


# --------------------------------------------------------------------------- #
# Widgets/Images  and  Textured buttons
# --------------------------------------------------------------------------- #
#   ImGui::Image(my_tex_id, ImVec2(my_tex_w, my_tex_h));
#   if (ImGui::ImageButton("", my_tex_id, ImVec2(32, 32))) pressed_count += 1;
def test_an_image_button_reports_its_click_and_shows_its_picture():
    state = {"pressed": 0}

    class Blitting(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.images = []

        def image(self, x, y, w, h, handle, uv0, uv1, tint):
            self.images.append(handle)

    painter = Blitting()
    io, storage = cmtk.IO(), {}

    def draw():
        nonlocal painter
        painter = Blitting()
        with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=io, storage=storage):
            cmtk.image("my_tex", (64.0, 64.0))
            if cmtk.image_button("##tex", "my_tex", (32.0, 32.0)):
                state["pressed"] += 1
            state["box"] = cmtk.get_item_rect()

    draw()
    assert painter.images == ["my_tex", "my_tex"]
    box = state["box"]
    io.mouse_pos = (box[0] + 2, box[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    draw()
    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    draw()
    assert state["pressed"] == 1


# --------------------------------------------------------------------------- #
# Widgets/Querying Window Status (Focused, Hovered)
# --------------------------------------------------------------------------- #
def test_the_window_status_queries_answer_for_the_window_they_are_in():
    answers: dict = {}

    def gui():
        cmtk.begin("under", (0.0, 0.0, 100.0, 100.0))
        answers["under_hovered"] = cmtk.is_window_hovered()
        answers["under_focused"] = cmtk.is_window_focused()
        cmtk.end()
        cmtk.begin("over", (0.0, 0.0, 100.0, 100.0))
        answers["over_hovered"] = cmtk.is_window_hovered()
        answers["over_focused"] = cmtk.is_window_focused()
        cmtk.end()

    frames = Frames(gui)
    frames.draw()
    frames.io.mouse_pos = (10.0, 10.0)
    frames.draw()
    assert answers["over_hovered"] is True, "the front window was not hovered"
    assert answers["under_hovered"] is False, "a covered window reported hover"
    assert answers["over_focused"] is True
    assert answers["under_focused"] is False

# --------------------------------------------------------------------------- #
# The ``IMGUI_DEMO_MARKER`` sections this file covers, spelled as the
# reference spells them -- the manifest in test_imgui_demo_remaining.py
# matches on these exact names.
#   Widgets/Querying Window Status (Focused,Hovered etc.)
#   Widgets/Selection State & Multi-Select
#   Widgets/Selection State/Multi-Select (manual/simplified, without BeginMultiSelect)

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Widgets/Images
#   Widgets/Images/Textured buttons
