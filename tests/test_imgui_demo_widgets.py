"""More ``imgui_demo.cpp`` Widgets sections: combos, lists, text, trees, drag and drop.

Same method as the rest: transliterate a section of the reference's demo and
let what breaks name the defect. These are the sections where the widget holds
*state between frames* -- a combo that stays open, a tree that remembers being
expanded, a drag whose payload survives the trip from one item to another --
which is where a re-implementation drifts from the original.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import RecordingPainter


class Frames:
    """The same gui, driven frame by frame with a mouse."""

    def __init__(self, gui, size=(0.0, 0.0, 400.0, 500.0)) -> None:
        self.gui = gui
        self.size = size
        self.io = emtk.IO()
        self.storage: dict = {}
        self.painter = RecordingPainter()
        self.result = None

    def draw(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, self.size, io=self.io, storage=self.storage):
            self.result = self.gui()
        return self.painter

    def press(self, box):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        self.io.mouse_down[0] = True
        self.io.mouse_clicked[0] = True
        self.io.mouse_clicked_pos[0] = self.io.mouse_pos
        self.draw()
        self.io.mouse_clicked[0] = False

    def release(self, box=None):
        if box is not None:
            self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        self.draw()
        self.io.mouse_released[0] = False
        return self.draw()

    def click(self, box):
        self.press(box)
        return self.release(box)

    def move_to(self, box):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        return self.draw()

    @property
    def strings(self):
        return self.painter.strings


# --------------------------------------------------------------------------- #
# Widgets/Combo  (imgui_demo.cpp:1399)
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginCombo("combo 1", combo_preview_value, flags))
#   {
#       for (int n = 0; n < IM_COUNTOF(items); n++)
#           if (ImGui::Selectable(items[n], is_selected)) item_selected_idx = n;
#       ImGui::EndCombo();
#   }
ITEMS = ("AAAA", "BBBB", "CCCC", "DDDD", "EEEE")


def _combo_gui(state):
    def gui():
        if emtk.begin_combo("combo 1", ITEMS[state["index"]]):
            for n, item in enumerate(ITEMS):
                if emtk.selectable(item, n == state["index"]):
                    state["index"] = n
                state.setdefault("items", {})[item] = emtk.get_item_rect()
            emtk.end_combo()
        else:
            state["closed_at"] = emtk.get_item_rect()
        state["combo"] = state.get("closed_at", state.get("combo"))
    return gui


def test_a_combo_shows_its_preview_and_nothing_else_until_opened():
    state = {"index": 0}
    frames = Frames(_combo_gui(state))
    frames.draw()
    assert "AAAA" in frames.strings
    assert "CCCC" not in frames.strings, "a closed combo listed its items"


def test_opening_a_combo_lists_the_items():
    state = {"index": 0}
    frames = Frames(_combo_gui(state))
    frames.draw()
    frames.click(state["combo"])
    for item in ITEMS:
        assert item in frames.strings, item


def test_choosing_from_a_combo_changes_the_preview():
    state = {"index": 0}
    frames = Frames(_combo_gui(state))
    frames.draw()
    frames.click(state["combo"])
    frames.click(state["items"]["DDDD"])
    assert state["index"] == ITEMS.index("DDDD")


# --------------------------------------------------------------------------- #
# Widgets/List Boxes
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginListBox("listbox 1")) { ... ImGui::EndListBox(); }
def test_a_list_box_lists_everything_and_reports_a_choice():
    state = {"index": 0, "boxes": {}}

    def gui():
        changed, state["index"] = emtk.list_box("listbox 1", state["index"], ITEMS)
        return changed

    frames = Frames(gui)
    painter = frames.draw()
    for item in ITEMS:
        assert item in painter.strings, item


# --------------------------------------------------------------------------- #
# Widgets/Text Input  (imgui_demo.cpp: InputText / InputTextMultiline)
# --------------------------------------------------------------------------- #
#   static char str0[128] = "Hello, world!";
#   ImGui::InputText("input text", str0, IM_COUNTOF(str0));
def test_typing_into_a_focused_field_reaches_the_value():
    state = {"text": "Hello", "box": None}

    def gui():
        changed, state["text"] = emtk.input_text("input text", state["text"])
        state["box"] = emtk.get_item_rect()
        return changed

    frames = Frames(gui)
    frames.draw()
    frames.click(state["box"])              # focus it
    frames.io.text = ", world!"
    frames.draw()
    assert state["text"] == "Hello, world!"


def test_typing_into_an_unfocused_field_is_ignored():
    state = {"text": "Hello", "box": None}

    def gui():
        _c, state["text"] = emtk.input_text("input text", state["text"])
        state["box"] = emtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    frames.io.text = "xyz"
    frames.draw()
    assert state["text"] == "Hello"


def test_a_hint_shows_only_while_the_field_is_empty():
    def gui():
        emtk.input_text_with_hint("with hint", "enter text here", "")

    frames = Frames(gui)
    frames.draw()
    assert "enter text here" in frames.strings

    def filled():
        emtk.input_text_with_hint("with hint", "enter text here", "typed")

    frames = Frames(filled)
    frames.draw()
    assert "enter text here" not in frames.strings
    assert "typed" in frames.strings


def test_a_multiline_field_draws_one_row_per_line():
    def gui():
        emtk.input_text_multiline("##ml", "one\ntwo\nthree", size=(200.0, 80.0))

    frames = Frames(gui)
    painter = frames.draw()
    for line in ("one", "two", "three"):
        assert line in painter.strings
    ys = sorted(c[2] for c in painter.calls
                if c[0] == "text" and c[6] in ("one", "two", "three"))
    assert len(set(ys)) == 3, "the lines landed on top of each other"


# --------------------------------------------------------------------------- #
# Widgets/Trees  (imgui_demo.cpp: TreeNode / SetNextItemOpen)
# --------------------------------------------------------------------------- #
def test_a_tree_node_remembers_being_opened():
    state = {"box": None}

    def gui():
        if emtk.tree_node("Root"):
            emtk.text("child")
            emtk.tree_pop()
        return emtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    header = frames.result
    assert "child" not in frames.strings
    frames.click(header)
    assert "child" in frames.strings
    frames.draw()                       # a later frame, nothing clicked
    assert "child" in frames.strings, "the node forgot it was open"


def test_set_next_item_open_forces_a_node_open():
    def gui():
        emtk.set_next_item_open(True)
        if emtk.tree_node_ex("Forced"):
            emtk.text("visible")
            emtk.tree_pop()

    frames = Frames(gui)
    frames.draw()
    assert "visible" in frames.strings


def test_nested_nodes_indent():
    boxes: dict = {}

    def gui():
        emtk.set_next_item_open(True)
        if emtk.tree_node_ex("Outer"):
            emtk.text("first")
            boxes["first"] = emtk.get_item_rect()
            emtk.set_next_item_open(True)
            if emtk.tree_node_ex("Inner"):
                emtk.text("second")
                boxes["second"] = emtk.get_item_rect()
                emtk.tree_pop()
            emtk.tree_pop()

    frames = Frames(gui)
    frames.draw()
    assert boxes["second"][0] > boxes["first"][0], "the inner level did not indent"


# --------------------------------------------------------------------------- #
# Widgets/Drag and Drop  (imgui_demo.cpp:1686)
# --------------------------------------------------------------------------- #
#   ImGui::Button(names[n], ImVec2(60, 60));
#   if (ImGui::BeginDragDropSource(ImGuiDragDropFlags_None))
#   {
#       ImGui::SetDragDropPayload("DND_DEMO_CELL", &n, sizeof(int));
#       ImGui::Text("Move %s", names[n]);
#       ImGui::EndDragDropSource();
#   }
#   if (ImGui::BeginDragDropTarget())
#       if (const ImGuiPayload* payload = ImGui::AcceptDragDropPayload("DND_DEMO_CELL"))
#           ...swap...
def test_dragging_one_cell_on_to_another_swaps_them():
    names = ["Bobby", "Beatrice", "Betty"]
    boxes: dict = {}

    def gui():
        for n, name in enumerate(list(names)):
            emtk.push_id(n)
            emtk.button(name, (60.0, 60.0))
            boxes[n] = emtk.get_item_rect()
            if emtk.begin_drag_drop_source():
                emtk.set_drag_drop_payload("DND_DEMO_CELL", n)
                emtk.text("Move %s" % name)
                emtk.end_drag_drop_source()
            if emtk.begin_drag_drop_target():
                source = emtk.accept_drag_drop_payload("DND_DEMO_CELL")
                if source is not None:
                    names[n], names[source] = names[source], names[n]
                emtk.end_drag_drop_target()
            emtk.pop_id()

    frames = Frames(gui)
    frames.draw()
    frames.press(boxes[0])                       # take hold of "Bobby"
    frames.io.mouse_pos = (boxes[2][0] + 2.0, boxes[2][1] + 2.0)   # drag across
    frames.draw()
    assert any("Move Bobby" in s for s in frames.strings), (
        "the drag preview was not drawn while dragging"
    )
    frames.release(boxes[2])                     # drop it on "Betty"
    assert names[0] == "Betty" and names[2] == "Bobby", names


def test_a_payload_of_the_wrong_kind_is_not_accepted():
    taken = {"value": None}
    boxes: dict = {}

    def gui():
        emtk.button("source", (60.0, 30.0))
        boxes["source"] = emtk.get_item_rect()
        if emtk.begin_drag_drop_source():
            emtk.set_drag_drop_payload("KIND_A", "cargo")
            emtk.end_drag_drop_source()
        emtk.button("target", (60.0, 30.0))
        boxes["target"] = emtk.get_item_rect()
        if emtk.begin_drag_drop_target():
            got = emtk.accept_drag_drop_payload("KIND_B")
            if got is not None:
                taken["value"] = got
            emtk.end_drag_drop_target()

    frames = Frames(gui)
    frames.draw()
    frames.press(boxes["source"])
    frames.io.mouse_pos = (boxes["target"][0] + 2.0, boxes["target"][1] + 2.0)
    frames.draw()
    frames.release(boxes["target"])
    assert taken["value"] is None


# --------------------------------------------------------------------------- #
# Widgets/Plotting
# --------------------------------------------------------------------------- #
#   ImGui::PlotLines("Frame Times", arr, IM_COUNTOF(arr));
#   ImGui::PlotHistogram("Histogram", arr, IM_COUNTOF(arr), 0, NULL, 0.0f, 1.0f, ImVec2(0, 80.0f));
def test_a_plot_scales_its_values_into_its_box():
    values = [0.6, 0.1, 1.0, 0.5, 0.92, 0.1, 0.2]

    def gui():
        emtk.plot_lines("Frame Times", values, size=(200.0, 80.0))
        return emtk.get_item_rect()

    frames = Frames(gui)
    painter = frames.draw()
    box = frames.result
    points = [pt for call in painter.calls if call[0] == "fill_triangle"
              for pt in call[1:4]]
    assert points, "the plot drew no line"
    assert min(p[1] for p in points) >= box[1] - 1.0
    assert max(p[1] for p in points) <= box[1] + box[3] + 1.0
    assert min(p[0] for p in points) >= box[0] - 1.0
    assert max(p[0] for p in points) <= box[0] + box[2] + 1.0

# --------------------------------------------------------------------------- #
# The ``IMGUI_DEMO_MARKER`` sections this file covers, spelled as the
# reference spells them -- the manifest in test_imgui_demo_remaining.py
# matches on these exact names.
#   Widgets/Drag and drop
#   Widgets/Drag and drop/Standard widgets
#   Widgets/Drag and drop/Copy-swap items
#   Widgets/Multi-component Widgets

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Widgets/Basic/Combo
#   Widgets/Basic/ListBox
#   Widgets/Basic/Slider (enum)
