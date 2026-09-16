"""More of ``imgui_demo.cpp``, ported. Each section is a fresh test of emtk.

The method, and it keeps paying: take a section of Dear ImGui's own demo,
transliterate it, run it, and let what breaks name the defect. The Basic
section did that once already -- it found that ``emtk.text()`` claimed a
full-width item, so the arrow buttons beside a label were unclickable.

Here: selectables, tabs, popups and menus. The C++ is quoted beside each so the
two read together, and what is checked is *behaviour* -- a tab bar that shows
one body at a time, a popup that opens and closes, a menu that only yields its
items while open.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import RecordingPainter


class Frames:
    """A little harness: the same gui, driven frame by frame with a mouse."""

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

    def click(self, box):
        """A press and a release on *box*, as a mouse does it: three frames."""
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


# --------------------------------------------------------------------------- #
# Widgets/Selectables/Basic  (imgui_demo.cpp:2456)
# --------------------------------------------------------------------------- #
#   if (ImGui::TreeNode("Basic"))
#   {
#       static bool selection[5] = { false, true, false, false };
#       ImGui::Selectable("1. I am selectable", &selection[0]);
#       ...
#       ImGui::TreePop();
#   }
def test_selectables_inside_a_tree_node():
    state = {"selection": [False, True, False, False], "boxes": {}}

    def gui():
        if emtk.tree_node("Basic"):
            for index in range(4):
                label = "%d. I am selectable" % (index + 1)
                if emtk.selectable(label, state["selection"][index]):
                    state["selection"][index] = not state["selection"][index]
                state["boxes"][index] = emtk.get_item_rect()
            emtk.tree_pop()

    frames = Frames(gui)
    frames.draw()
    assert not any("selectable" in s for s in frames.strings), (
        "a closed tree node showed its children"
    )

    # open it -- the header is the first item
    frames.draw()
    header = None

    def find_header():
        nonlocal header
        with emtk.frame(RecordingPainter(), frames.size, io=frames.io,
                      storage=frames.storage) as ctx:
            emtk.tree_node("Basic")
            header = ctx.get_item_rect()
    find_header()
    frames.click(header)
    assert sum("I am selectable" in s for s in frames.strings) == 4


def test_a_selectable_reports_its_click():
    state = {"selected": False}

    def gui():
        if emtk.selectable("row", state["selected"]):
            state["selected"] = not state["selected"]
        return emtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    frames.click(frames.result)
    assert state["selected"] is True


def test_two_selectables_on_one_line_need_allow_overlap():
    """The demo's own point: `SetNextItemAllowOverlap` then `SameLine`.

        ImGui::SetNextItemAllowOverlap(); ImGui::Selectable("main.c", &sel);
        ImGui::SameLine(); ImGui::SmallButton("Link 1");

    Without it the selectable claims the pointer for its whole row and the
    button beside it is dead -- the same fault `emtk.text()` had.
    """
    hits = {"selectable": False, "button": False}

    def gui():
        emtk.set_next_item_allow_overlap()
        if emtk.selectable("main.c", False, size=(200.0, 0.0)):
            hits["selectable"] = True
        row = emtk.get_item_rect()
        emtk.same_line()
        if emtk.small_button("Link 1"):
            hits["button"] = True
        return emtk.get_item_rect(), row

    frames = Frames(gui)
    frames.draw()
    button_box, _row = frames.result
    frames.click(button_box)
    assert hits["button"], "the button under an overlapping selectable was dead"


# --------------------------------------------------------------------------- #
# Widgets/Tabs/Basic  (imgui_demo.cpp:3599)
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginTabBar("MyTabBar", tab_bar_flags))
#   {
#       if (ImGui::BeginTabItem("Avocado")) { ImGui::Text("This is the Avocado tab!"); ImGui::EndTabItem(); }
#       ...
#       ImGui::EndTabBar();
#   }
VEGETABLES = ("Avocado", "Broccoli", "Cucumber")


def _tab_gui(boxes):
    def gui():
        if emtk.begin_tab_bar("MyTabBar"):
            for name in VEGETABLES:
                if emtk.begin_tab_item(name):
                    emtk.text("This is the %s tab!" % name)
                    emtk.end_tab_item()
                boxes[name] = emtk.get_item_rect()
            emtk.end_tab_bar()
        emtk.separator()
    return gui


def test_a_tab_bar_shows_one_body_at_a_time():
    boxes: dict = {}
    frames = Frames(_tab_gui(boxes))
    frames.draw()
    bodies = [s for s in frames.strings if s.startswith("This is the")]
    assert bodies == ["This is the Avocado tab!"], bodies


def test_every_tab_has_a_header_even_when_it_is_not_selected():
    boxes: dict = {}
    frames = Frames(_tab_gui(boxes))
    frames.draw()
    for name in VEGETABLES:
        assert name in frames.strings, name


def test_clicking_a_tab_switches_the_body():
    boxes: dict = {}
    frames = Frames(_tab_gui(boxes))
    frames.draw()
    frames.click(boxes["Cucumber"])
    bodies = [s for s in frames.strings if s.startswith("This is the")]
    assert bodies == ["This is the Cucumber tab!"], bodies


# --------------------------------------------------------------------------- #
# Popups/Popups  (imgui_demo.cpp:5446)
# --------------------------------------------------------------------------- #
#   if (ImGui::Button("Select..")) ImGui::OpenPopup("my_select_popup");
#   ImGui::SameLine();
#   ImGui::TextUnformatted(selected_fish == -1 ? "<None>" : names[selected_fish]);
#   if (ImGui::BeginPopup("my_select_popup"))
#   {
#       ImGui::SeparatorText("Aquarium");
#       for (int i = 0; i < IM_COUNTOF(names); i++)
#           if (ImGui::Selectable(names[i])) selected_fish = i;
#       ImGui::EndPopup();
#   }
FISH = ("Bream", "Haddock", "Mackerel", "Pollock", "Tilefish")


def _popup_gui(state):
    def gui():
        if emtk.button("Select.."):
            emtk.open_popup("my_select_popup")
        state["button"] = emtk.get_item_rect()
        emtk.same_line()
        emtk.text_unformatted("<None>" if state["fish"] < 0 else FISH[state["fish"]])
        if emtk.begin_popup("my_select_popup"):
            emtk.separator_text("Aquarium")
            for index, name in enumerate(FISH):
                if emtk.selectable(name):
                    state["fish"] = index
                state.setdefault("items", {})[name] = emtk.get_item_rect()
            emtk.end_popup()
    return gui


def test_a_popup_is_shut_until_it_is_opened():
    state = {"fish": -1}
    frames = Frames(_popup_gui(state))
    frames.draw()
    assert "Aquarium" not in frames.strings
    assert "<None>" in frames.strings


def test_opening_a_popup_shows_its_contents():
    state = {"fish": -1}
    frames = Frames(_popup_gui(state))
    frames.draw()
    frames.click(state["button"])
    assert "Aquarium" in frames.strings
    for name in FISH:
        assert name in frames.strings


def test_choosing_from_a_popup_reaches_the_caller():
    state = {"fish": -1}
    frames = Frames(_popup_gui(state))
    frames.draw()
    frames.click(state["button"])            # open it
    frames.click(state["items"]["Mackerel"])  # pick
    assert state["fish"] == FISH.index("Mackerel")
    assert "Mackerel" in frames.strings


# --------------------------------------------------------------------------- #
# The menu bar  (imgui_demo.cpp: ShowExampleMenuFile / DemoWindowMenuBar)
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginMenuBar())
#   {
#       if (ImGui::BeginMenu("File")) { ShowExampleMenuFile(); ImGui::EndMenu(); }
#       ImGui::EndMenuBar();
#   }
def _menu_gui(state):
    def gui():
        if emtk.begin_menu_bar():
            if emtk.begin_menu("File"):
                if emtk.menu_item("New"):
                    state["chose"] = "New"
                state.setdefault("items", {})["New"] = emtk.get_item_rect()
                if emtk.menu_item("Open", "Ctrl+O"):
                    state["chose"] = "Open"
                state["items"]["Open"] = emtk.get_item_rect()
                emtk.separator()
                if emtk.menu_item("Quit", "Alt+F4"):
                    state["chose"] = "Quit"
                emtk.end_menu()
            state["file"] = emtk.get_item_rect()
            emtk.end_menu_bar()
    return gui


def test_a_menu_is_shut_until_its_title_is_clicked():
    state: dict = {}
    frames = Frames(_menu_gui(state))
    frames.draw()
    assert "File" in frames.strings
    assert not any("New" in s for s in frames.strings)


def test_opening_a_menu_shows_its_items_and_their_shortcuts():
    state: dict = {}
    frames = Frames(_menu_gui(state))
    frames.draw()
    title = state["file"]
    frames.click(title)
    assert any("New" in s for s in frames.strings)
    assert "Ctrl+O" in frames.strings, "the shortcut column was not drawn"
    assert "Alt+F4" in frames.strings


def test_choosing_a_menu_item_reports_it():
    state: dict = {}
    frames = Frames(_menu_gui(state))
    frames.draw()
    frames.click(state["file"])
    frames.click(state["items"]["Open"])
    assert state.get("chose") == "Open"


# --------------------------------------------------------------------------- #
# Widgets/Querying Item Status  (imgui_demo.cpp:2224)
# --------------------------------------------------------------------------- #
#   ImGui::BulletText(
#       "Return value = %d\n"  "IsItemFocused() = %d\n"  "IsItemHovered() = %d\n"
#       "IsItemActive() = %d\n" "IsItemEdited() = %d\n" "IsItemActivated() = %d\n"
#       "IsItemDeactivated() = %d\n" ... "GetItemRectSize() = (%.1f, %.1f)", ...);
#
# The demo prints these for a chosen widget; here they are read as a button is
# pressed and released, because the *sequence* is what an implementation gets
# wrong -- activated on the way in, deactivated on the way out, and clicked
# exactly once.
def _status_of(kind: str):
    """Drive one widget through press and release, recording its status."""
    log = []

    def gui():
        ret = emtk.button("ITEM: Button") if kind == "button" else emtk.checkbox(
            "ITEM: Checkbox", False)[0]
        log.append({
            "ret": bool(ret),
            "hovered": emtk.is_item_hovered(),
            "active": emtk.is_item_active(),
            "activated": emtk.is_item_activated(),
            "deactivated": emtk.is_item_deactivated(),
            "clicked": emtk.is_item_clicked(),
            "visible": emtk.is_item_visible(),
            "rect_size": emtk.get_item_rect_size(),
            "rect_min": emtk.get_item_rect_min(),
            "rect_max": emtk.get_item_rect_max(),
        })
        return emtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()                                   # 0: nothing near it
    box = frames.result
    frames.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
    frames.draw()                                   # 1: hovered
    frames.io.mouse_down[0] = True
    frames.io.mouse_clicked[0] = True
    frames.io.mouse_clicked_pos[0] = frames.io.mouse_pos
    frames.draw()                                   # 2: pressed
    frames.io.mouse_clicked[0] = False
    frames.draw()                                   # 3: held
    frames.io.mouse_down[0] = False
    frames.io.mouse_released[0] = True
    frames.draw()                                   # 4: released
    frames.io.mouse_released[0] = False
    frames.draw()                                   # 5: after
    return log


def test_an_item_is_hovered_only_when_the_pointer_is_on_it():
    log = _status_of("button")
    assert log[0]["hovered"] is False
    assert log[1]["hovered"] is True


def test_the_rect_queries_agree_with_each_other():
    log = _status_of("button")
    for frame in log:
        w, h = frame["rect_size"]
        assert frame["rect_max"][0] - frame["rect_min"][0] == pytest.approx(w)
        assert frame["rect_max"][1] - frame["rect_min"][1] == pytest.approx(h)
        assert w > 0 and h > 0


def test_activation_and_deactivation_bracket_the_press():
    """Whole sequences, not one frame each.

    `IsItemActivated` is the frame an item *becomes* active and no other, and
    `IsItemDeactivated` the frame it stops -- not "is not active", which is
    true of every widget on screen and would fire an on-edit-finished handler
    for things nobody has touched. Telling those apart needs the previous
    frame's active id, which is why Dear ImGui keeps one.

    Frames: 0 idle, 1 hovered, 2 pressed, 3 held, 4 released, 5 after.
    """
    assert [f["active"] for f in _status_of("button")] == [
        False, False, True, True, False, False]
    assert [f["activated"] for f in _status_of("button")] == [
        False, False, True, False, False, False]
    assert [f["deactivated"] for f in _status_of("button")] == [
        False, False, False, False, True, False]


def test_the_click_is_reported_once_and_on_the_down_edge():
    """`IsItemClicked` is the down edge; the *return value* is the up edge."""
    log = _status_of("button")
    assert [f["clicked"] for f in log] == [False, False, True, False, False, False]
    assert [f["ret"] for f in log] == [False, False, False, False, True, False]


def test_an_item_that_was_drawn_is_visible():
    log = _status_of("button")
    assert all(f["visible"] for f in log)


# --------------------------------------------------------------------------- #
# Layout/Groups  (imgui_demo.cpp: "Basic Horizontal Layout" / groups)
# --------------------------------------------------------------------------- #
#   ImGui::BeginGroup();
#   ImGui::Button("AAA"); ImGui::SameLine(); ImGui::Button("BBB");
#   ImGui::EndGroup();
#   ImGui::SameLine();
#   ImGui::Button("CCC");
def test_a_group_is_one_item_the_next_thing_lines_up_beside():
    boxes: dict = {}

    def gui():
        emtk.begin_group()
        emtk.button("AAA")
        boxes["AAA"] = emtk.get_item_rect()
        emtk.same_line()
        emtk.button("BBB")
        boxes["BBB"] = emtk.get_item_rect()
        emtk.button("CCC")                       # a second line, inside the group
        boxes["CCC"] = emtk.get_item_rect()
        boxes["group"] = emtk.end_group()
        emtk.same_line()
        emtk.button("DDD")
        boxes["DDD"] = emtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    assert boxes["AAA"][1] == boxes["BBB"][1], "SameLine did not hold the line"
    assert boxes["CCC"][1] > boxes["AAA"][1], "the second row did not advance"
    # The group is as tall as its two rows, and DDD sits beside the whole of it.
    group = boxes["group"]
    assert group[3] >= boxes["CCC"][1] + boxes["CCC"][3] - boxes["AAA"][1] - 1.0
    assert boxes["DDD"][0] > boxes["AAA"][0]


# --------------------------------------------------------------------------- #
# Tables  (imgui_demo.cpp: DemoWindowTables, the simplest form)
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginTable("table1", 3))
#   {
#       for (int row = 0; row < 4; row++)
#       {
#           ImGui::TableNextRow();
#           for (int column = 0; column < 3; column++)
#           {
#               ImGui::TableSetColumnIndex(column);
#               ImGui::Text("Row %d Column %d", row, column);
#           }
#       }
#       ImGui::EndTable();
#   }
def test_a_table_puts_its_cells_in_a_grid():
    cells: dict = {}

    def gui():
        if emtk.begin_table("table1", 3):
            for row in range(4):
                emtk.table_next_row()
                for column in range(3):
                    emtk.table_set_column_index(column)
                    emtk.text("Row %d Column %d" % (row, column))
                    cells[(row, column)] = emtk.get_item_rect()
            emtk.end_table()

    frames = Frames(gui)
    frames.draw()
    assert len(cells) == 12
    # Columns march to the right...
    for row in range(4):
        xs = [cells[(row, c)][0] for c in range(3)]
        assert xs == sorted(xs) and len(set(xs)) == 3, (row, xs)
    # ...and every cell in a column shares its left edge.
    for column in range(3):
        xs = {cells[(r, column)][0] for r in range(4)}
        assert len(xs) == 1, (column, xs)


def test_a_table_headers_row_names_the_columns():
    def gui():
        if emtk.begin_table("table2", 3):
            for name in ("one", "two", "three"):
                emtk.table_setup_column(name)
            emtk.table_headers_row()
            emtk.table_next_column()
            emtk.text("cell")
            emtk.end_table()

    frames = Frames(gui)
    frames.draw()
    for name in ("one", "two", "three"):
        assert name in frames.strings, name

# --------------------------------------------------------------------------- #
# The ``IMGUI_DEMO_MARKER`` sections this file covers, spelled as the
# reference spells them -- the manifest in test_imgui_demo_remaining.py
# matches on these exact names.
#   Widgets/Querying Item Status (Edited,Active,Hovered etc.)
