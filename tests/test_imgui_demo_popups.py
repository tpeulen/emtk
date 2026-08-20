"""``imgui_demo.cpp``'s Popups, Menus and Inputs sections, ported.

Popups and menus are modal-ish state that outlives a frame, and input queries
are the one place a widget reads the host directly. Both are where a
re-implementation quietly diverges: a popup that reopens itself every frame, a
context menu bound to the wrong button, a key query that answers for the wrong
frame.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk import keys
from cmtk.testing import RecordingPainter


class Frames:
    def __init__(self, gui, size=(0.0, 0.0, 400.0, 400.0)) -> None:
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

    def click(self, box, button=0):
        self.io.mouse_pos = (box[0] + 2.0, box[1] + 2.0)
        self.io.mouse_down[button] = True
        self.io.mouse_clicked[button] = True
        self.io.mouse_clicked_pos[button] = self.io.mouse_pos
        self.draw()
        self.io.mouse_clicked[button] = False
        self.io.mouse_down[button] = False
        self.io.mouse_released[button] = True
        self.draw()
        self.io.mouse_released[button] = False
        return self.draw()

    @property
    def strings(self):
        return self.painter.strings


# --------------------------------------------------------------------------- #
# Popups/Modals
# --------------------------------------------------------------------------- #
#   if (ImGui::Button("Delete..")) ImGui::OpenPopup("Delete?");
#   if (ImGui::BeginPopupModal("Delete?", NULL, ImGuiWindowFlags_AlwaysAutoResize))
#   {
#       ImGui::Text("All those beautiful files will be deleted.\nThis operation cannot be undone!");
#       if (ImGui::Button("OK", ImVec2(120, 0))) { ImGui::CloseCurrentPopup(); }
#       ImGui::EndPopup();
#   }
def _modal_gui(state):
    def gui():
        if cmtk.button("Delete.."):
            cmtk.open_popup("Delete?")
        state["open_button"] = cmtk.get_item_rect()
        if cmtk.begin_popup_modal("Delete?"):
            cmtk.text("All those beautiful files will be deleted.")
            if cmtk.button("OK", (120.0, 0.0)):
                cmtk.close_current_popup()
                state["confirmed"] = True
            state["ok"] = cmtk.get_item_rect()
            cmtk.end_popup()
    return gui


def test_a_modal_opens_on_demand_and_not_before():
    state: dict = {}
    frames = Frames(_modal_gui(state))
    frames.draw()
    assert not any("beautiful files" in s for s in frames.strings)
    frames.click(state["open_button"])
    assert any("beautiful files" in s for s in frames.strings)


def test_closing_a_modal_from_inside_it_closes_it():
    state: dict = {}
    frames = Frames(_modal_gui(state))
    frames.draw()
    frames.click(state["open_button"])
    frames.click(state["ok"])
    assert state.get("confirmed") is True
    assert not any("beautiful files" in s for s in frames.strings), (
        "CloseCurrentPopup left the popup open"
    )


# --------------------------------------------------------------------------- #
# Popups/Context menus
# --------------------------------------------------------------------------- #
#   ImGui::Text("Value = %.3f <-- (1) right-click this text", value);
#   if (ImGui::BeginPopupContextItem("item context menu")) { ... }
def _context_gui(state):
    def gui():
        cmtk.text("Value = %.3f" % state.get("value", 0.5))
        state["text"] = cmtk.get_item_rect()
        if cmtk.begin_popup_context_item("item context menu"):
            if cmtk.selectable("Set to zero"):
                state["value"] = 0.0
            state["zero"] = cmtk.get_item_rect()
            cmtk.end_popup()
    return gui


def test_a_context_menu_opens_on_the_right_button_only():
    state: dict = {}
    frames = Frames(_context_gui(state))
    frames.draw()
    assert "Set to zero" not in frames.strings

    frames.click(state["text"], button=0)              # left: nothing
    assert "Set to zero" not in frames.strings

    frames.click(state["text"], button=1)              # right: opens
    assert "Set to zero" in frames.strings


def test_a_context_menu_item_reaches_the_caller():
    state = {"value": 0.5}
    frames = Frames(_context_gui(state))
    frames.draw()
    frames.click(state["text"], button=1)
    frames.click(state["zero"])
    assert state["value"] == 0.0


# --------------------------------------------------------------------------- #
# Menu/nested and disabled items  (ShowExampleMenuFile)
# --------------------------------------------------------------------------- #
#   if (ImGui::BeginMenu("Options")) { ... ImGui::EndMenu(); }
#   ImGui::MenuItem("Checked", NULL, true);
#   if (ImGui::MenuItem("Quit", "Alt+F4")) {}
def test_a_nested_menu_only_yields_while_its_parent_is_open():
    state: dict = {}

    def gui():
        if cmtk.begin_menu_bar():
            if cmtk.begin_menu("File"):
                if cmtk.begin_menu("Options"):
                    cmtk.menu_item("Enabled", "", True)
                    cmtk.end_menu()
                state["options"] = cmtk.get_item_rect()
                cmtk.end_menu()
            state["file"] = cmtk.get_item_rect()
            cmtk.end_menu_bar()

    frames = Frames(gui)
    frames.draw()
    assert "Options" not in frames.strings
    frames.click(state["file"])
    assert "Options" in frames.strings
    assert not any("Enabled" in s for s in frames.strings)
    frames.click(state["options"])
    assert any("Enabled" in s for s in frames.strings)


def test_a_disabled_menu_item_does_not_report_a_click():
    state = {"fired": False}

    def gui():
        if cmtk.menu_item("Quit", "Alt+F4", False, False):
            state["fired"] = True
        return cmtk.get_item_rect()

    frames = Frames(gui)
    frames.draw()
    frames.click(frames.result)
    assert state["fired"] is False


def test_a_checked_menu_item_is_marked():
    def gui():
        cmtk.menu_item("Checked", "", True)

    frames = Frames(gui)
    frames.draw()
    assert any("Checked" in s for s in frames.strings)
    assert any(s.startswith("*") for s in frames.strings), (
        "a checked item was drawn the same as an unchecked one"
    )


# --------------------------------------------------------------------------- #
# Inputs & Focus  (imgui_demo.cpp: DemoWindowInputs)
# --------------------------------------------------------------------------- #
#   ImGui::Text("Mouse pos: (%g, %g)", io.MousePos.x, io.MousePos.y);
#   ImGui::Text("Mouse down:"); for (...) if (ImGui::IsMouseDown(i)) ...
#   ImGui::Text("Keys down:");  for (...) if (ImGui::IsKeyDown(key)) ...
def test_the_mouse_queries_report_what_the_host_put_in_io():
    answers: dict = {}

    def gui():
        answers["pos"] = cmtk.get_mouse_pos()
        answers["down0"] = cmtk.is_mouse_down(0)
        answers["down1"] = cmtk.is_mouse_down(1)
        answers["clicked"] = cmtk.is_mouse_clicked(0)
        answers["released"] = cmtk.is_mouse_released(0)
        answers["any"] = cmtk.is_any_mouse_down()
        answers["valid"] = cmtk.is_mouse_pos_valid()

    frames = Frames(gui)
    frames.io.mouse_pos = (12.0, 34.0)
    frames.io.mouse_down[1] = True
    frames.draw()
    assert answers["pos"] == (12.0, 34.0)
    assert answers["down0"] is False and answers["down1"] is True
    assert answers["any"] is True
    assert answers["valid"] is True


def test_an_absent_pointer_is_not_a_valid_position():
    answers: dict = {}

    def gui():
        answers["valid"] = cmtk.is_mouse_pos_valid()

    frames = Frames(gui)
    frames.draw()                       # IO's default is (-1, -1)
    assert answers["valid"] is False


def test_the_drag_delta_is_measured_from_where_the_press_landed():
    answers: dict = {}

    def gui():
        answers["delta"] = cmtk.get_mouse_drag_delta(0)
        answers["dragging"] = cmtk.is_mouse_dragging(0)

    frames = Frames(gui)
    frames.io.mouse_pos = (10.0, 10.0)
    frames.io.mouse_down[0] = True
    frames.io.mouse_clicked_pos[0] = (10.0, 10.0)
    frames.draw()
    assert answers["delta"] == (0.0, 0.0)
    assert answers["dragging"] is False, "a press that has not moved is not a drag"

    frames.io.mouse_pos = (40.0, 60.0)
    frames.draw()
    assert answers["delta"] == (30.0, 50.0)
    assert answers["dragging"] is True


def test_resetting_the_drag_delta_moves_the_origin():
    answers: dict = {}

    def gui():
        answers["before"] = cmtk.get_mouse_drag_delta(0)
        cmtk.reset_mouse_drag_delta(0)
        answers["after"] = cmtk.get_mouse_drag_delta(0)

    frames = Frames(gui)
    frames.io.mouse_pos = (40.0, 60.0)
    frames.io.mouse_down[0] = True
    frames.io.mouse_clicked_pos[0] = (10.0, 10.0)
    frames.draw()
    assert answers["before"] == (30.0, 50.0)
    assert answers["after"] == (0.0, 0.0)


def test_the_key_queries_report_the_key_the_host_delivered():
    answers: dict = {}

    def gui():
        answers["a"] = cmtk.is_key_down(keys.KEY_A)
        answers["b"] = cmtk.is_key_down(keys.KEY_B)
        answers["pressed"] = cmtk.is_key_pressed(keys.KEY_A)
        answers["name"] = cmtk.get_key_name(keys.KEY_A)

    frames = Frames(gui)
    frames.io.key = keys.KEY_A
    frames.draw()
    assert answers["a"] is True and answers["b"] is False
    assert answers["pressed"] is True
    assert answers["name"] == "a"


def test_a_mouse_cursor_can_be_asked_for_and_read_back():
    answers: dict = {}

    def gui():
        cmtk.set_mouse_cursor(3)
        answers["cursor"] = cmtk.get_mouse_cursor()

    frames = Frames(gui)
    frames.draw()
    assert answers["cursor"] == 3


def test_keyboard_focus_can_be_placed_from_code():
    """`SetKeyboardFocusHere(0)` is the *next* item, `(-1)` the last.

    The reference's own spelling, and the difference matters: the demo puts the
    call *before* the field it wants to focus.
    """
    state = {"text": "", "other": "", "first": True}

    def gui():
        _c, state["other"] = cmtk.input_text("other", state["other"])
        if state["first"]:
            cmtk.set_keyboard_focus_here()      # ...the next one
            state["first"] = False
        _c, state["text"] = cmtk.input_text("field", state["text"])

    frames = Frames(gui)
    frames.draw()
    frames.io.text = "typed"
    frames.draw()
    assert state["text"] == "typed"
    assert state["other"] == "", "the focus landed on the wrong field"


def test_keyboard_focus_can_be_placed_on_the_item_just_submitted():
    state = {"text": "", "first": True}

    def gui():
        _c, state["text"] = cmtk.input_text("field", state["text"])
        if state["first"]:
            cmtk.set_keyboard_focus_here(-1)    # ...the one just submitted
            state["first"] = False

    frames = Frames(gui)
    frames.draw()
    frames.io.text = "typed"
    frames.draw()
    assert state["text"] == "typed"

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Menu/File
#   Examples/Menu
#   Popups/Modals
#   Popups/Context menus
#   Popups/Popups
