"""The last twelve ``imgui_demo.cpp`` sections: docking, titles, nav, flags.

Each needed something emtk did not have, and each of those is now built:

* **docking** -- a dock node is a box windows share, and windows sharing one
  are its tabs; ``DockBuilderSplitNode`` cuts a node in two. The dragging that
  *makes* a node belongs to the host's window frame, so a host that drags calls
  ``set_next_window_dock_id`` and emtk does the rest.
* **window titles** -- ``##`` and ``###``: the first hides the rest from the
  label while keeping it in the id, the second replaces the id, so a title that
  changes every frame keeps one identity.
* **keyboard navigation** -- a tab ring, which is the order items were
  submitted in, so there is no second list to keep in step.
* **item flags** -- ``LiveEditOnInput*``: whether a drag reports every step or
  only the one that finishes it.
* **nested multi-select scopes** and **backend flags**.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import keys
from emtk.testing import RecordingPainter


class Frames:
    def __init__(self, gui, size=(0.0, 0.0, 600.0, 400.0)) -> None:
        self.gui, self.size = gui, size
        self.io = emtk.IO()
        self.storage: dict = {}
        self.painter = RecordingPainter()

    def draw(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, self.size, io=self.io, storage=self.storage):
            self.gui()
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

    def press_key(self, key, shift=False, ctrl=False):
        """A key, then a settling frame.

        The focus moves at the *end* of the frame the key arrives in -- the tab
        ring is the order items were submitted in, so it is only complete once
        they have been. The frame after is the one that draws it focused, which
        is what the reference does too.
        """
        self.io.key = key
        self.io.key_shift = shift
        self.io.key_ctrl = ctrl
        self.draw()
        self.io.key = 0
        self.io.key_shift = False
        self.io.key_ctrl = False
        return self.draw()

    @property
    def strings(self):
        return self.painter.strings


def _run(gui, size=(0.0, 0.0, 600.0, 400.0), io=None, storage=None):
    painter = RecordingPainter()
    with emtk.frame(painter, size, io=io or emtk.IO(),
                    storage=storage if storage is not None else {}):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Examples/Manipulating window titles##1 ##2 ##3
# --------------------------------------------------------------------------- #
#   ImGui::Begin("Same title as another window##1");
#   ImGui::Begin("Same title as another window##2");
#   sprintf(buf, "Animated title %c %d###AnimatedTitle", "|/-\\"[...], GetFrameCount());
#   ImGui::Begin(buf);
def test_two_windows_can_share_a_title_and_stay_apart():
    seen: dict = {}

    def gui():
        emtk.begin("Same title as another window##1", (0.0, 0.0, 100.0, 50.0))
        emtk.text("This is window 1.")
        emtk.end()
        emtk.begin("Same title as another window##2", (0.0, 60.0, 100.0, 50.0))
        emtk.text("This is window 2.")
        emtk.end()
        ctx = emtk.get_current_context()
        seen["names"] = [w.name for w in ctx.windows]
        seen["titles"] = [w.title for w in ctx.windows]
        seen["boxes"] = [w.box for w in ctx.windows]

    _run(gui)
    assert len(seen["names"]) == 2, "the two windows became one"
    assert len(set(seen["names"])) == 2, seen["names"]
    assert seen["titles"] == ["Same title as another window"] * 2
    assert seen["boxes"][0] != seen["boxes"][1]


def test_a_title_that_changes_every_frame_keeps_one_window():
    seen: list = []

    def gui():
        ctx = emtk.get_current_context()
        spinner = "|/-\\"[ctx.io.frame_count % 4]
        emtk.begin("Animated title %s %d###AnimatedTitle"
                   % (spinner, ctx.io.frame_count), (0.0, 0.0, 120.0, 40.0))
        emtk.text("This window has a changing title.")
        emtk.end()
        seen.append(([w.name for w in ctx.windows],
                     [w.title for w in ctx.windows]))

    frames = Frames(gui)
    for _ in range(4):
        frames.draw()
    names, titles = seen[-1]
    assert names == ["AnimatedTitle"], names
    assert titles[0].startswith("Animated title"), titles
    assert titles[0] != seen[0][1][0], "the title did not change"


# --------------------------------------------------------------------------- #
# Examples/Documents  and  Examples/Fullscreen window   (docking)
# --------------------------------------------------------------------------- #
#   ImGuiID dockspace_id = ImGui::DockSpaceOverViewport();
#   ImGui::SetNextWindowDockID(dockspace_id); ImGui::Begin("Document A"); ...
def test_windows_docked_into_one_node_become_its_tabs():
    seen: dict = {}

    def gui():
        dock = emtk.dock_space_over_viewport(1)
        for name in ("Lettre", "Farrago", "Abstract"):
            if emtk.begin_docked(name, dock):
                emtk.text("body of %s" % name)
            emtk.end_docked()
            seen.setdefault("tabs", {})[name] = emtk.get_item_rect()
        node = emtk.get_current_context().dock_node(1)
        seen["windows"] = list(node["windows"])
        seen["selected"] = node["selected"]

    frames = Frames(gui)
    painter = frames.draw()
    assert seen["windows"] == ["Lettre", "Farrago", "Abstract"]
    assert seen["selected"] == "Lettre"
    for name in seen["windows"]:
        assert name in painter.strings, "every docked window needs a tab"
    bodies = [s for s in painter.strings if s.startswith("body of")]
    assert bodies == ["body of Lettre"], bodies


def test_clicking_a_dock_tab_brings_that_document_forward():
    boxes: dict = {}

    def gui():
        dock = emtk.dock_space_over_viewport(1)
        for name in ("Lettre", "Farrago", "Abstract"):
            on_top = emtk.begin_docked(name, dock)
            if on_top:
                emtk.text("body of %s" % name)
            emtk.end_docked()
        ctx = emtk.get_current_context()
        boxes.update(ctx.state(("dock_tabs",)))

    # The tab boxes are the first three items of the frame; find them by
    # replaying and reading the item rect after each tab is drawn.
    frames = Frames(gui)
    frames.draw()

    tabs: dict = {}

    def probe():
        dock = emtk.dock_space_over_viewport(1)
        node = emtk.get_current_context().dock_node(1)
        x, y, _w, _h = node["box"]
        height = emtk.get_frame_height()
        offset = x
        for name in ("Lettre", "Farrago", "Abstract"):
            width = emtk.calc_text_size(name)[0] + emtk.get_style().frame_padding[0] * 2
            tabs[name] = (offset, y, width, height)
            offset += width + 2.0

    _run(probe, io=frames.io, storage=frames.storage)
    frames.click(tabs["Abstract"])
    bodies = [s for s in frames.strings if s.startswith("body of")]
    assert bodies == ["body of Abstract"], bodies


def test_a_dock_node_can_be_split_in_two():
    seen: dict = {}

    def gui():
        dock = emtk.dock_space_over_viewport(1)
        left, right = emtk.dock_builder_split_node(dock, emtk.Dir.LEFT, 0.25)
        ctx = emtk.get_current_context()
        seen["left"] = ctx.dock_node(left)["box"]
        seen["right"] = ctx.dock_node(right)["box"]
        seen["whole"] = ctx.dock_node(dock)["box"]

    _run(gui, size=(0.0, 0.0, 400.0, 300.0))
    whole, left, right = seen["whole"], seen["left"], seen["right"]
    assert left[2] == pytest.approx(whole[2] * 0.25)
    assert right[2] == pytest.approx(whole[2] * 0.75)
    assert right[0] == pytest.approx(left[0] + left[2])
    assert left[3] == right[3] == whole[3]


def test_a_window_says_whether_it_is_docked():
    seen: dict = {}

    def gui():
        dock = emtk.dock_space_over_viewport(1)
        emtk.begin_docked("Docked", dock)
        seen["docked"] = emtk.is_window_docked()
        seen["id"] = emtk.get_window_dock_id()
        emtk.end_docked()
        emtk.begin("Floating", (0.0, 200.0, 100.0, 50.0))
        seen["floating"] = emtk.is_window_docked()
        emtk.end()

    _run(gui)
    assert seen["docked"] is True and seen["id"] == 1
    assert seen["floating"] is False


def test_a_window_can_be_docked_before_it_is_drawn():
    """`DockBuilderDockWindow` -- the layout set up in advance."""
    seen: dict = {}

    def gui():
        emtk.dock_space_over_viewport(1)
        emtk.dock_builder_dock_window("Preplaced", 1)
        emtk.begin_docked("Preplaced")
        seen["id"] = emtk.get_window_dock_id()
        emtk.end_docked()

    _run(gui)
    assert seen["id"] == 1


def test_a_dock_space_fills_the_box_it_was_given():
    """Examples/Fullscreen window -- a dock space over the whole viewport."""
    seen: dict = {}

    def gui():
        emtk.dock_space_over_viewport(1)
        seen["node"] = emtk.get_current_context().dock_node(1)["box"]
        seen["viewport"] = emtk.get_main_viewport()

    _run(gui, size=(0.0, 0.0, 640.0, 480.0))
    assert seen["node"] == (0.0, 0.0, 640.0, 480.0)
    assert seen["viewport"].size == (640.0, 480.0)


# --------------------------------------------------------------------------- #
# Inputs & Focus/Tabbing  and  Focus from code
# --------------------------------------------------------------------------- #
#   ImGui::InputText("1", buf, ...); ImGui::InputText("2", buf, ...); ...
#   if (focus_1) ImGui::SetKeyboardFocusHere(); ImGui::InputText(...);
def _fields_gui(state):
    def gui():
        emtk.process_nav_keys()
        for index in range(3):
            _c, state["text%d" % index] = emtk.input_text(
                "%d" % index, state.get("text%d" % index, ""))
            state["id%d" % index] = emtk.get_item_id()
        state["nav"] = emtk.get_nav_id()
        state["ring"] = emtk.get_nav_ring()
    return gui


def test_tab_moves_the_focus_from_one_field_to_the_next():
    state: dict = {}
    frames = Frames(_fields_gui(state))
    frames.io.config_flags = emtk.ConfigFlags.NAV_ENABLE_KEYBOARD
    frames.draw()
    assert state["ring"] == [state["id%d" % i] for i in range(3)], "no tab order"
    assert state["nav"] is None

    frames.press_key(keys.KEY_TAB)
    assert state["nav"] == state["id0"], "Tab did not focus the first field"
    frames.press_key(keys.KEY_TAB)
    assert state["nav"] == state["id1"]
    frames.press_key(keys.KEY_TAB, shift=True)
    assert state["nav"] == state["id0"], "Shift+Tab did not go back"


def test_tab_wraps_around_the_ring():
    state: dict = {}
    frames = Frames(_fields_gui(state))
    frames.io.config_flags = emtk.ConfigFlags.NAV_ENABLE_KEYBOARD
    frames.draw()
    for _ in range(4):
        frames.press_key(keys.KEY_TAB)
    assert state["nav"] == state["id0"], "the ring did not wrap"


def test_tab_is_ignored_when_navigation_is_off():
    state: dict = {}
    frames = Frames(_fields_gui(state))
    frames.draw()
    frames.press_key(keys.KEY_TAB)
    assert state["nav"] is None, "Tab moved the focus with navigation disabled"


def test_typing_reaches_the_field_the_keyboard_focused():
    state: dict = {}
    frames = Frames(_fields_gui(state))
    frames.io.config_flags = emtk.ConfigFlags.NAV_ENABLE_KEYBOARD
    frames.draw()
    frames.press_key(keys.KEY_TAB)
    frames.press_key(keys.KEY_TAB)          # focus field 1
    frames.io.text = "typed"
    frames.draw()
    assert state["text1"] == "typed", state
    assert state["text0"] == ""


def test_focus_can_be_placed_from_code():
    """Inputs & Focus/Focus from code -- `SetKeyboardFocusHere` before an item."""
    state = {"want": True}

    def gui():
        emtk.text("before")
        if state["want"]:
            emtk.set_keyboard_focus_here()
            state["want"] = False
        _c, state["text"] = emtk.input_text("field", state.get("text", ""))
        state["id"] = emtk.get_item_id()
        state["nav"] = emtk.get_nav_id()

    frames = Frames(gui)
    frames.draw()
    assert state["nav"] == state["id"], "the focus was not placed on the next item"
    frames.io.text = "abc"
    frames.draw()
    assert state["text"] == "abc"


# --------------------------------------------------------------------------- #
# Inputs & Focus/Shortcuts
# --------------------------------------------------------------------------- #
#   ImGui::Shortcut(ImGuiMod_Ctrl | ImGuiKey_A, ...);
def test_a_shortcut_fires_only_on_its_own_chord():
    seen: dict = {}

    def gui():
        chord = keys.MOD_CTRL | keys.KEY_A
        seen["ctrl_a"] = emtk.shortcut(chord)
        seen["plain_a"] = emtk.shortcut(keys.KEY_A)

    io = emtk.IO()
    io.key = keys.KEY_A
    io.key_ctrl = True
    _run(gui, io=io)
    assert seen["ctrl_a"] is True
    assert seen["plain_a"] is False, "a plain key matched a chord with a modifier"

    io = emtk.IO()
    io.key = keys.KEY_A
    _run(gui, io=io)
    assert seen["ctrl_a"] is False
    assert seen["plain_a"] is True


def test_a_shortcut_can_be_claimed_for_the_next_item():
    def gui():
        emtk.set_next_item_shortcut(keys.MOD_CTRL | keys.KEY_S)
        emtk.button("Save")
        assert emtk.get_current_context().state(("shortcut",))["next"] == \
            keys.MOD_CTRL | keys.KEY_S

    _run(gui)


# --------------------------------------------------------------------------- #
# Widgets/Live Edit Flgs
# --------------------------------------------------------------------------- #
#   ImGui::PushItemFlag(ImGuiItemFlags_LiveEditOnInput, true); ... DragFloat(...);
def test_live_edit_decides_when_a_drag_reports_its_change():
    reports = {"live": [], "on_release": []}
    boxes: dict = {}

    def gui(live):
        emtk.push_item_flag(emtk.ItemFlags.LIVE_EDIT_ON_INPUT, live)
        changed, _v = emtk.drag_float("value", 1.0, 1.0)
        boxes["drag"] = emtk.get_item_rect()
        emtk.pop_item_flag()
        reports["live" if live else "on_release"].append(changed)

    for live in (True, False):
        io, storage = emtk.IO(), {}
        reports["live" if live else "on_release"].clear()
        _run(lambda: gui(live), io=io, storage=storage)
        box = boxes["drag"]
        io.mouse_pos = (box[0] + 2, box[1] + 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        io.mouse_clicked_pos[0] = io.mouse_pos
        _run(lambda: gui(live), io=io, storage=storage)     # pressed
        io.mouse_clicked[0] = False
        io.mouse_pos = (box[0] + 30, box[1] + 2)
        _run(lambda: gui(live), io=io, storage=storage)     # dragging
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        _run(lambda: gui(live), io=io, storage=storage)     # released

    assert reports["live"][2] is True, "a live-edit drag reported nothing mid-drag"
    assert reports["on_release"][2] is False, "a non-live drag reported mid-drag"
    assert reports["on_release"][3] is True, "it never reported at all"


# --------------------------------------------------------------------------- #
# Widgets/Selection State/Multi-Select (multiple scopes)
# --------------------------------------------------------------------------- #
def test_two_multi_select_scopes_keep_their_own_selections():
    left: set = set()
    right: set = set()
    boxes: dict = {}

    def gui():
        emtk.push_id("left")
        emtk.begin_multi_select(0, len(left), 3)
        for n in range(3):
            if emtk.selectable("L%d" % n, n in left):
                left.symmetric_difference_update({n})
            boxes[("left", n)] = emtk.get_item_rect()
        io_left = emtk.end_multi_select()
        emtk.pop_id()

        emtk.push_id("right")
        emtk.begin_multi_select(0, len(right), 3)
        for n in range(3):
            if emtk.selectable("R%d" % n, n in right):
                right.symmetric_difference_update({n})
            boxes[("right", n)] = emtk.get_item_rect()
        io_right = emtk.end_multi_select()
        emtk.pop_id()
        boxes["ios"] = (io_left, io_right)

    frames = Frames(gui)
    frames.draw()
    assert boxes["ios"][0] is not boxes["ios"][1], (
        "the two scopes shared one MultiSelectIO")
    frames.click(boxes[("left", 1)])
    assert left == {1} and right == set()
    frames.click(boxes[("right", 2)])
    assert left == {1} and right == {2}, (left, right)


# --------------------------------------------------------------------------- #
# Configuration/Backend Flags
# --------------------------------------------------------------------------- #
#   ImGui::CheckboxFlags("io.BackendFlags: HasMouseCursors", &backend_flags, ...);
def test_the_backend_flags_describe_the_painter_in_hand():
    plain: dict = {}
    rich: dict = {}

    def gui(into):
        into["flags"] = emtk.get_io().backend_flags

    _run(lambda: gui(plain))
    assert not plain["flags"] & emtk.BackendFlags.RENDERER_HAS_IMAGES
    assert plain["flags"] & emtk.BackendFlags.HAS_MOUSE_CURSORS

    class Capable(RecordingPainter):
        def image(self, x, y, w, h, handle, uv0, uv1, tint):
            pass

        def set_font(self, font):
            pass

        def text_rotated(self, x, y, w, h, align, string, colour, degrees=0.0):
            pass

    painter = Capable()
    with emtk.frame(painter, (0.0, 0.0, 100.0, 100.0)):
        gui(rich)
    assert rich["flags"] & emtk.BackendFlags.RENDERER_HAS_IMAGES
    assert rich["flags"] & emtk.BackendFlags.RENDERER_HAS_FONTS
    assert rich["flags"] & emtk.BackendFlags.RENDERER_HAS_ROTATED_TEXT


def test_the_config_flags_are_the_applications_to_set():
    seen: dict = {}

    def gui():
        seen["nav"] = bool(emtk.get_io().config_flags
                           & emtk.ConfigFlags.NAV_ENABLE_KEYBOARD)
        seen["capture"] = (emtk.get_io().want_capture_mouse,
                           emtk.get_io().want_capture_keyboard)

    io = emtk.IO()
    io.config_flags = emtk.ConfigFlags.NAV_ENABLE_KEYBOARD
    _run(gui, io=io)
    assert seen["nav"] is True


def test_want_capture_reports_whether_the_gui_took_the_input():
    io, storage = emtk.IO(), {}
    seen: dict = {}

    def gui():
        emtk.begin("w", (0.0, 0.0, 100.0, 100.0))
        emtk.button("b")
        emtk.end()

    _run(gui, io=io, storage=storage)
    assert io.want_capture_mouse is False, "nothing was hovered"

    io.mouse_pos = (10.0, 10.0)
    _run(gui, io=io, storage=storage)
    _run(gui, io=io, storage=storage)
    assert io.want_capture_mouse is True, "the pointer was over a window"


# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Examples/Manipulating window titles##1
#   Examples/Manipulating window titles##2
#   Examples/Manipulating window titles##3
#   Examples/Documents
#   Examples/Fullscreen window
#   Inputs & Focus/Tabbing
#   Inputs & Focus/Focus from code
#   Inputs & Focus/Shortcuts
#   Widgets/Live Edit Flgs
#   Widgets/Selection State/Multi-Select (multiple scopes)
#   Configuration/Backend Flags
#   Help
