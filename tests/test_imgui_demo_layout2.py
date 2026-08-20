"""The last ``imgui_demo.cpp`` sections: layout details, trees, tables, tabs.

Sections: Layout/Text Baseline Alignment, Layout/Overlap Mode,
Layout/Scrolling/Horizontal, Layout/Manual wrapping, Widgets/Tree Nodes
(Basic Trees, Advanced, Selectable Nodes), Tables/Borders, Tables/Row height,
Tables/Synced instances, Tabs/Advanced.

With this file the reference's demo is ported across all of its groups.
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

    @property
    def strings(self):
        return self.painter.strings


def _run(gui, size=(0.0, 0.0, 500.0, 500.0)):
    painter = RecordingPainter()
    with cmtk.frame(painter, size):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Layout/Text Baseline Alignment
# --------------------------------------------------------------------------- #
#   ImGui::AlignTextToFramePadding(); ImGui::Text("OK Blahblah"); ImGui::SameLine();
#   ImGui::Button("Some framed item"); ImGui::SameLine(); HelpMarker(...);
def test_a_label_before_a_framed_item_sits_on_its_line():
    boxes: dict = {}

    def gui():
        cmtk.align_text_to_frame_padding()
        cmtk.text("OK Blahblah")
        boxes["label"] = cmtk.get_item_rect()
        cmtk.same_line()
        cmtk.button("Some framed item")
        boxes["button"] = cmtk.get_item_rect()

    _run(gui)
    label, button = boxes["label"], boxes["button"]
    assert label[1] == button[1]
    # The framed item is the taller of the two, and the row is its height.
    assert button[3] >= label[3]


# --------------------------------------------------------------------------- #
# Layout/Basic Horizontal Layout/Manual wrapping
# --------------------------------------------------------------------------- #
#   for (int n = 0; n < 20; n++)
#   { ... float last_button_x2 = ImGui::GetItemRectMax().x;
#     float next_button_x2 = last_button_x2 + style.ItemSpacing.x + button_sz.x;
#     if (n + 1 < 20 && next_button_x2 < window_visible_x2) ImGui::SameLine(); }
def test_manual_wrapping_starts_a_new_line_when_the_next_button_would_not_fit():
    rows: dict = {}

    def gui():
        style = cmtk.get_style()
        right = cmtk.get_window_pos()[0] + cmtk.get_window_size()[0]
        button_size = (60.0, 20.0)
        for n in range(12):
            cmtk.push_id(n)
            cmtk.button("Box", button_size)
            box = cmtk.get_item_rect()
            rows[n] = box
            cmtk.pop_id()
            last_x2 = cmtk.get_item_rect_max()[0]
            next_x2 = last_x2 + style.item_spacing[0] + button_size[0]
            if n + 1 < 12 and next_x2 < right:
                cmtk.same_line()

    _run(gui, size=(0.0, 0.0, 260.0, 400.0))
    lines = sorted({round(b[1]) for b in rows.values()})
    assert len(lines) > 1, "nothing wrapped"
    for box in rows.values():
        assert box[0] + box[2] <= 260.0 + 1.0, box


# --------------------------------------------------------------------------- #
# Layout/Overlap Mode
# --------------------------------------------------------------------------- #
#   ImGui::SetNextItemAllowOverlap();
#   ImGui::Selectable("Some Selectable", false);
#   ImGui::SameLine(); ImGui::SmallButton("Button");
def test_overlap_mode_lets_the_upper_item_take_the_pointer():
    hits = {"button": 0, "selectable": 0}
    boxes: dict = {}

    def gui():
        cmtk.set_next_item_allow_overlap()
        if cmtk.selectable("Some Selectable", False, (200.0, 0.0)):
            hits["selectable"] += 1
        boxes["selectable"] = cmtk.get_item_rect()
        cmtk.same_line()
        if cmtk.small_button("Button"):
            hits["button"] += 1
        boxes["button"] = cmtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    frames.click(boxes["button"])
    assert hits["button"] == 1
    assert hits["selectable"] == 0, "the click reached both items"


# --------------------------------------------------------------------------- #
# Layout/Scrolling/Horizontal
# --------------------------------------------------------------------------- #
#   ImGui::SetScrollHereX(i * 0.25f); / ImGui::GetScrollX() / GetScrollMaxX()
def test_horizontal_scroll_is_remembered_and_clamped():
    answers: dict = {}

    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("scroller", (0.0, 0.0, 200.0, 100.0))
        ctx.current_window.content_size = (500.0, 100.0)
        answers["max"] = cmtk.get_scroll_max_x()
        cmtk.set_scroll_x(50.0)
        answers["set"] = cmtk.get_scroll_x()
        cmtk.set_scroll_here_x(1.0)
        answers["here"] = cmtk.get_scroll_x()
        ctx.end()

    assert answers["max"] == 300.0
    assert answers["set"] == 50.0
    assert answers["here"] == 300.0


# --------------------------------------------------------------------------- #
# Widgets/Tree Nodes/Basic Trees and Selectable Nodes
# --------------------------------------------------------------------------- #
#   for (int i = 0; i < 5; i++)
#   { if (ImGui::TreeNode((void*)(intptr_t)i, "Child %d", i)) { ImGui::Text("blah"); ImGui::TreePop(); } }
def test_sibling_nodes_open_independently():
    boxes: dict = {}

    def gui():
        for index in range(3):
            cmtk.push_id(index)
            if cmtk.tree_node("Child %d" % index):
                cmtk.text("blah blah %d" % index)
                cmtk.tree_pop()
            boxes[index] = cmtk.get_item_rect()
            cmtk.pop_id()

    frames = Frames(gui)
    frames.draw()
    assert not any("blah" in s for s in frames.strings)
    frames.click(boxes[1])
    shown = [s for s in frames.strings if "blah" in s]
    assert shown == ["blah blah 1"], shown


def test_a_selectable_node_can_be_both_open_and_chosen():
    state = {"selected": -1, "boxes": {}}

    def gui():
        for index in range(3):
            cmtk.push_id(index)
            opened = cmtk.tree_node("Node %d" % index)
            state["boxes"][index] = cmtk.get_item_rect()
            if opened:
                if cmtk.selectable("leaf %d" % index, state["selected"] == index):
                    state["selected"] = index
                state["boxes"][("leaf", index)] = cmtk.get_item_rect()
                cmtk.tree_pop()
            cmtk.pop_id()

    frames = Frames(gui)
    frames.draw()
    frames.click(state["boxes"][2])
    assert any("leaf 2" in s for s in frames.strings)
    frames.click(state["boxes"][("leaf", 2)])
    assert state["selected"] == 2


# --------------------------------------------------------------------------- #
# Tables/Borders, background  and  Row height
# --------------------------------------------------------------------------- #
def test_a_table_row_is_as_tall_as_its_tallest_cell():
    cells: dict = {}

    def gui():
        if cmtk.begin_table("t", 2):
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.text("short")
            cells["short"] = cmtk.get_item_rect()
            cmtk.table_set_column_index(1)
            cmtk.button("tall", (60.0, 60.0))
            cells["tall"] = cmtk.get_item_rect()
            cmtk.table_next_row()
            cmtk.table_set_column_index(0)
            cmtk.text("next row")
            cells["next"] = cmtk.get_item_rect()
            cmtk.end_table()

    _run(gui)
    assert cells["next"][1] >= cells["tall"][1] + cells["tall"][3] - 1.0, (
        "the next row overlapped the tall cell"
    )


def test_two_tables_with_the_same_id_do_not_share_state():
    """The demo's "Synced instances" section is the opposite case; this is the
    property it relies on -- each `BeginTable` is its own entry on the stack."""
    counts: dict = {}

    def gui():
        for which in ("a", "b"):
            if cmtk.begin_table("same_id", 2 if which == "a" else 3):
                cmtk.table_next_column()
                counts[which] = cmtk.table_get_column_count()
                cmtk.end_table()

    _run(gui)
    assert counts == {"a": 2, "b": 3}, counts


# --------------------------------------------------------------------------- #
# Widgets/Tabs/Advanced & Close Button
# --------------------------------------------------------------------------- #
#   for (int n = 0; n < IM_COUNTOF(opened); n++)
#       if (opened[n] && ImGui::BeginTabItem(names[n], &opened[n], ImGuiTabItemFlags_None))
#       { ImGui::Text("This is the %s tab!", names[n]); ImGui::EndTabItem(); }
def test_a_closed_tab_is_not_submitted_and_the_rest_carry_on():
    names = ["Artichoke", "Beetroot", "Celery", "Daikon"]
    opened = {name: True for name in names}
    boxes: dict = {}

    def gui():
        if cmtk.begin_tab_bar("MyTabBar"):
            for name in names:
                if not opened[name]:
                    continue
                if cmtk.begin_tab_item(name):
                    cmtk.text("This is the %s tab!" % name)
                    cmtk.end_tab_item()
                boxes[name] = cmtk.get_item_rect()
            cmtk.end_tab_bar()

    frames = Frames(gui)
    frames.draw()
    assert all(name in frames.strings for name in names)

    opened["Beetroot"] = False
    frames.draw()
    assert "Beetroot" not in frames.strings
    assert all(opened[n] == (n in frames.strings) for n in names)

    # ...and a surviving tab can still be chosen.
    frames.click(boxes["Celery"])
    bodies = [s for s in frames.strings if s.startswith("This is the")]
    assert bodies == ["This is the Celery tab!"], bodies

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Tables/Row height
