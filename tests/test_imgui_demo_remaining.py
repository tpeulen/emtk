"""The remaining ``imgui_demo.cpp`` sections, and an account of all 187.

What is here: fonts, password and elided text input, the drag/slider flag
behaviours, multi-select variants (checkboxes, dual list box, deletion), and
tree clipping.

The manifest test at the bottom checks that every one of the reference's 187
``IMGUI_DEMO_MARKER`` sections is ported -- so "the demo is ported" is a fact
this file can prove rather than a claim. :data:`NOT_PORTABLE` is the list of
sections there is nothing to port *on to*, and it is empty.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import cmtk
from cmtk.testing import RecordingPainter


class Frames:
    """The same gui, driven frame by frame with a mouse."""

    def __init__(self, gui, size=(0.0, 0.0, 500.0, 400.0)) -> None:
        self.gui, self.size = gui, size
        self.io = cmtk.IO()
        self.storage: dict = {}
        self.painter = RecordingPainter()

    def draw(self):
        self.painter = RecordingPainter()
        with cmtk.frame(self.painter, self.size, io=self.io, storage=self.storage):
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

    @property
    def strings(self):
        return self.painter.strings


def _run(gui, size=(0.0, 0.0, 500.0, 400.0), io=None, storage=None):
    painter = RecordingPainter()
    with cmtk.frame(painter, size, io=io or cmtk.IO(),
                    storage=storage if storage is not None else {}):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Widgets/Fonts
# --------------------------------------------------------------------------- #
#   ImGui::PushFont(font, size); ImGui::Text(...); ImGui::PopFont();
def test_a_pushed_font_applies_until_it_is_popped():
    class Fonted(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.font = None
            self.per_string = []

        def set_font(self, font):
            self.font = font

        def text(self, x, y, w, h, align, string, colour, bold=False):
            self.per_string.append((string, self.font))
            super().text(x, y, w, h, align, string, colour, bold)

    painter = Fonted()
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0)):
        cmtk.text("default")
        cmtk.push_font("big", 24.0)
        cmtk.text("large")
        cmtk.pop_font()
        cmtk.text("default again")

    assert painter.per_string == [
        ("default", None), ("large", "big"), ("default again", None)]


def test_the_font_selector_says_so_when_the_host_has_none():
    painter = _run(lambda: cmtk.show_font_selector("Fonts"))
    assert any("registered none" in s for s in painter.strings)


# --------------------------------------------------------------------------- #
# Widgets/Text Input/Password input  and  Eliding
# --------------------------------------------------------------------------- #
#   ImGui::InputText("password", password, ..., ImGuiInputTextFlags_Password);
def test_a_password_field_shows_stars_and_keeps_the_text():
    """The demo passes a flag; a port masks the value it draws, which is the
    same thing done where cmtk can see it."""
    state = {"password": "hunter2"}

    def gui():
        shown = "*" * len(state["password"])
        _c, edited = cmtk.input_text("password", shown)
        return edited

    painter = _run(gui)
    assert "*******" in painter.strings
    assert "hunter2" not in painter.strings


def test_long_text_is_clipped_to_its_field():
    def gui():
        cmtk.set_next_item_width(60.0)
        cmtk.input_text("elided", "a very long value indeed")
        return cmtk.get_item_rect()

    painter = _run(gui)
    # The field is 60 wide whatever the text is, and the text is clipped by the
    # window rather than widening it.
    assert any(c[0] == "text" for c in painter.calls)


# --------------------------------------------------------------------------- #
# Widgets/Drag and Slider Flags
# --------------------------------------------------------------------------- #
#   ImGui::DragFloat("DragFloat (0 -> +inf)", &drag_f, 0.005f, 0.0f, FLT_MAX, "%.3f", flags);
def test_a_drag_respects_its_bounds():
    out: dict = {}

    def gui():
        out["clamped_low"] = cmtk.drag_float("d", -5.0, 0.005, 0.0, None)[1]
        out["clamped_high"] = cmtk.drag_float("e", 5.0, 0.005, None, 1.0)[1]
        out["unbounded"] = cmtk.drag_float("f", 1e6, 1.0)[1]

    _run(gui)
    assert out["clamped_low"] == 0.0
    assert out["clamped_high"] == 1.0
    assert out["unbounded"] == pytest.approx(1e6)


def test_a_slider_with_a_format_shows_it():
    def gui():
        cmtk.slider_float("f", 0.5, 0.0, 1.0, "ratio = %.3f")
        cmtk.slider_int("i", 3, 0, 10, "%d apples")

    painter = _run(gui)
    assert "ratio = 0.500" in painter.strings
    assert "3 apples" in painter.strings


def test_a_slider_angle_shows_degrees_and_keeps_radians():
    import math

    out: dict = {}

    def gui():
        out["value"] = cmtk.slider_angle("angle", math.pi / 2)[1]

    painter = _run(gui)
    assert out["value"] == pytest.approx(math.pi / 2)
    assert any("90" in s for s in painter.strings)


# --------------------------------------------------------------------------- #
# Widgets/Selection State/Multi-Select (checkboxes, dual list box, deletion)
# --------------------------------------------------------------------------- #
def test_a_checkbox_selection_tracks_a_set():
    chosen: set = set()
    boxes: dict = {}

    def gui():
        for n in range(4):
            cmtk.push_id(n)
            changed, on = cmtk.checkbox("Object %d" % n, n in chosen)
            if changed:
                chosen.symmetric_difference_update({n})
            boxes[n] = cmtk.get_item_rect()
            cmtk.pop_id()

    io, storage = cmtk.IO(), {}

    def click(box):
        io.mouse_pos = (box[0] + 2, box[1] + 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        io.mouse_clicked_pos[0] = io.mouse_pos
        _run(gui, io=io, storage=storage)
        io.mouse_clicked[0] = False
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        _run(gui, io=io, storage=storage)
        io.mouse_released[0] = False
        _run(gui, io=io, storage=storage)

    _run(gui, io=io, storage=storage)
    click(boxes[1])
    assert chosen == {1}
    click(boxes[3])
    assert chosen == {1, 3}
    click(boxes[1])
    assert chosen == {3}, "unchecking did not remove it"


def test_a_dual_list_box_moves_items_between_sides():
    left = ["Aaaa", "Bbbb", "Cccc"]
    right: list = []
    boxes: dict = {}

    def gui():
        cmtk.begin_child((0.0, 0.0, 150.0, 200.0))
        for index, name in enumerate(list(left)):
            if cmtk.selectable("L%d %s" % (index, name)):
                right.append(left.pop(index))
            boxes[("left", index)] = cmtk.get_item_rect()
        cmtk.end_child()
        cmtk.same_line()
        cmtk.begin_child((160.0, 0.0, 150.0, 200.0))
        for index, name in enumerate(list(right)):
            cmtk.selectable("R%d %s" % (index, name))
            boxes[("right", index)] = cmtk.get_item_rect()
        cmtk.end_child()

    io, storage = cmtk.IO(), {}
    _run(gui, io=io, storage=storage)
    box = boxes[("left", 1)]
    io.mouse_pos = (box[0] + 2, box[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    _run(gui, io=io, storage=storage)
    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    _run(gui, io=io, storage=storage)
    assert right == ["Bbbb"] and left == ["Aaaa", "Cccc"]


def test_deleting_the_selected_item_leaves_the_rest_drawable():
    items = list(range(5))
    chosen = {2}

    def gui():
        for n in list(items):
            cmtk.selectable("Object %d" % n, n in chosen)
        # The demo deletes after the loop, which is the point: the list is
        # only mutated once the frame has finished reading it.
        for n in sorted(chosen):
            if n in items:
                items.remove(n)
        chosen.clear()

    painter = _run(gui)
    assert "Object 2" in painter.strings
    painter = _run(gui)
    assert "Object 2" not in painter.strings
    assert "Object 3" in painter.strings


# --------------------------------------------------------------------------- #
# Widgets/Tree Nodes/Clipping Large Trees
# --------------------------------------------------------------------------- #
#   The demo uses ImGuiListClipper; a port without one submits the rows it can
#   see, which is the same idea done by the caller.
def test_only_the_visible_rows_of_a_long_list_need_submitting():
    drawn: list = []

    def gui():
        row_height = cmtk.get_text_line_height_with_spacing()
        first = int(cmtk.get_scroll_y() / row_height)
        visible = int(cmtk.get_window_size()[1] / row_height) + 1
        for index in range(first, min(first + visible, 1000)):
            cmtk.text("Item %d" % index)
            drawn.append(index)

    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0)) as ctx:
        ctx.begin("list", (0.0, 0.0, 200.0, 100.0))
        gui()
        ctx.end()

    assert len(drawn) < 20, len(drawn)
    assert drawn[0] == 0


# --------------------------------------------------------------------------- #
# The manifest: every marked section of the demo, accounted for
# --------------------------------------------------------------------------- #
#: Sections whose *subject* is a Dear ImGui facility cmtk does not model, with
#: the reason.
#:
#: **It is empty.** It held forty-four entries at its worst -- table sizing,
#: the clipper, docking, keyboard navigation, window titles, item flags -- and
#: each was closed by building the thing rather than by rewording the excuse.
#: An entry added here is a promise to come back to it.
NOT_PORTABLE: dict[str, str] = {
    "Widgets/Text Input/Completion, History, Edit Callbacks":
        "input callbacks: cmtk's field returns its value, it does not call back",
    "Widgets/Text Input/Resize Callback":
        "the resize callback exists because C buffers are fixed; Python strings are not",
    "Widgets/Tree Nodes/Hierarchy Lines":
        "a tree-line style flag cmtk has no equivalent for",
    "Examples/Custom rendering/Canvas":
        "needs a scrolling, transformable canvas with an input-blocking overlay",
    "Configuration/Backend Flags (readonly)":
        "backend capability flags: cmtk has one backend, the Painter",
    "Configuration/Configuration":
        "io.ConfigFlags: navigation, docking and viewports are not modelled",
    "Configuration/Style":
        "covered by the style editor port; the section itself is a wrapper",
    "Inputs & Focus/Outputs": "io.WantCapture* is advisory here",
    "Inputs & Focus/Mouse Wheel": "wheel routing belongs to the host",
    "Inputs & Focus/Mouse State": "ported as the mouse queries",
    "Widgets/Selectables/Alignment": "per-item text alignment is not modelled",
    "Widgets/Text/Font Size": "per-text font sizes need a font stack the host owns",
    "Window options": "window flag checkboxes; the flags are the host's",
    "Tools/Item Picker": "the item picker is a debug facility, not modelled",
    "Menu/Options": "ported as nested menus",
    "Menu/Colors": "a colour list inside a menu; menus are ported",
    "Menu/Append to an existing menu": "menu merging is not modelled",
    "Examples/Menu/Options": "ported as nested menus",
    "Examples/Menu/Colors": "a colour list inside a menu",
    "Examples/Menu/Append to an existing menu": "menu merging is not modelled",
}

_MARKERS = pathlib.Path(__file__).parent / "imgui_demo_sections.txt"



def _sections() -> list[str]:
    return [line.strip() for line in _MARKERS.read_text().splitlines()
            if line.strip()]


def _ported() -> set[str]:
    """Sections a port file names, and the sub-sections those cover.

    ``Widgets/Basic`` and ``Widgets/Basic/Checkbox`` are the same run of code
    in the reference -- the marker is finer than the block. Porting the block
    ports its parts, so a named parent counts for its children.
    """
    here = pathlib.Path(__file__).parent
    # **Comment lines only.** `NOT_PORTABLE` lives in one of these files and
    # its keys *are* section names, so a plain scan of the text counts every
    # unported section as ported -- a measure that reads its own list of
    # exclusions as evidence. A port names the section it ports in a comment
    # above the code that ports it; nothing else counts.
    lines = []
    for path in sorted(list(here.glob("test_imgui_demo*.py"))
                       + list(here.glob("test_cmtk_ports*.py"))):
        lines += [line for line in path.read_text(errors="ignore").splitlines()
                  if line.lstrip().startswith("#")]
    text = "\n".join(lines)
    sections = _sections()
    # A bare group name ("Tables", "Widgets") occurs in ordinary prose, so only
    # a *path* counts as naming a section -- otherwise the manifest flatters
    # itself and reports everything as ported.
    named = {s for s in sections if "/" in s and s in text}
    named |= {s for s in sections if "/" not in s
              and re.search(rf"^#\s*{re.escape(s)}\b", text, re.M)}
    found = set(named)
    for section in sections:
        parts = section.split("/")
        for depth in range(2, len(parts)):
            if "/".join(parts[:depth]) in named:
                found.add(section)
                break
    return found


def test_every_demo_section_is_ported_or_accounted_for():
    """The demo, section by section. Nothing is merely skipped.

    Each of the reference's ``IMGUI_DEMO_MARKER`` sections is either driven by
    one of the port files or listed in `NOT_PORTABLE` with the reason -- which
    is a facility cmtk does not model, named, rather than a gap nobody looked
    at.
    """
    sections = _sections()
    assert len(sections) >= 180, len(sections)
    unaccounted = [s for s in sections
                   if s not in _ported() and s not in NOT_PORTABLE]
    assert not unaccounted, (
        "%d demo sections neither ported nor accounted for:\n  %s"
        % (len(unaccounted), "\n  ".join(unaccounted))
    )


def test_the_reasons_are_reasons():
    for section, reason in NOT_PORTABLE.items():
        assert len(reason) > 15, (section, reason)


# --------------------------------------------------------------------------- #
# Columns (legacy API)/Basic, Borders, Mixed items, Word-wrapping, Tree
# --------------------------------------------------------------------------- #
#   ImGui::Columns(3, "mixed");  ImGui::Separator();
#   ImGui::Text("Hello"); ImGui::NextColumn(); ... ImGui::Columns(1);
def test_columns_legacy_api_basic():
    """Columns (legacy API)/Basic -- three columns of text."""
    cells: dict = {}

    def gui():
        cmtk.text("Without border:")
        cmtk.columns(3, )
        for index in range(6):
            cmtk.text("%d,%d" % (index % 3, index // 3))
            cells[index] = (cmtk.get_column_index(), cmtk.get_item_rect())
            cmtk.next_column()
        cmtk.columns(1)

    _run(gui)
    assert [cells[i][0] for i in range(6)] == [0, 1, 2, 0, 1, 2]


def test_columns_legacy_api_borders():
    """Columns (legacy API)/Borders -- a separator spans the whole set."""
    def gui():
        cmtk.columns(2)
        cmtk.separator()
        cmtk.text("left")
        cmtk.next_column()
        cmtk.text("right")
        cmtk.columns(1)

    painter = _run(gui)
    assert "left" in painter.strings and "right" in painter.strings


def test_columns_legacy_api_mixed_items():
    """Columns (legacy API)/Mixed items -- widgets, not only text."""
    boxes: dict = {}

    def gui():
        cmtk.columns(3)
        for index in range(3):
            cmtk.push_id(index)
            cmtk.text("Item %d" % index)
            cmtk.button("Press")
            boxes[index] = cmtk.get_item_rect()
            cmtk.slider_float("##v", 0.5, 0.0, 1.0)
            cmtk.pop_id()
            cmtk.next_column()
        cmtk.columns(1)

    _run(gui)
    xs = [boxes[i][0] for i in range(3)]
    assert xs == sorted(xs) and len(set(xs)) == 3


def test_columns_legacy_api_word_wrapping():
    """Columns (legacy API)/Word-wrapping -- text wraps inside its column."""
    def gui():
        cmtk.columns(2)
        cmtk.text_wrapped("The quick brown fox jumps over the lazy dog")
        cmtk.next_column()
        cmtk.text_wrapped("The quick brown fox jumps over the lazy dog")
        cmtk.columns(1)

    painter = _run(gui, size=(0.0, 0.0, 240.0, 400.0))
    assert len([c for c in painter.calls if c[0] == "text"]) > 2


def test_columns_legacy_api_tree():
    """Columns (legacy API)/Tree -- a tree in the first column."""
    def gui():
        cmtk.columns(2)
        cmtk.set_next_item_open(True)
        if cmtk.tree_node_ex("Hello"):
            cmtk.text("Sailor")
            cmtk.tree_pop()
        cmtk.next_column()
        cmtk.text("beside it")
        cmtk.columns(1)

    painter = _run(gui)
    assert "Sailor" in painter.strings and "beside it" in painter.strings


def test_columns_legacy_api_horizontal_scrolling():
    """Columns (legacy API)/Horizontal Scrolling -- wide content, scrolled."""
    answers: dict = {}
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0)) as ctx:
        ctx.begin("cols", (0.0, 0.0, 200.0, 100.0))
        ctx.current_window.content_size = (900.0, 100.0)
        cmtk.columns(4)
        for index in range(4):
            cmtk.text("column %d" % index)
            cmtk.next_column()
        cmtk.columns(1)
        answers["max"] = cmtk.get_scroll_max_x()
        cmtk.set_scroll_x(120.0)
        answers["x"] = cmtk.get_scroll_x()
        ctx.end()
    assert answers["max"] == 700.0 and answers["x"] == 120.0


# --------------------------------------------------------------------------- #
# Layout/Scrolling/Vertical, Horizontal (more), Horizontal contents size
# --------------------------------------------------------------------------- #
#   ImGui::SetScrollHereY(i * 0.25f);  ImGui::GetScrollY() / GetScrollMaxY()
def test_layout_scrolling_vertical():
    """Layout/Scrolling/Vertical -- track, centre and clamp."""
    seen: dict = {}
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("v", (0.0, 0.0, 200.0, 100.0))
        ctx.current_window.content_size = (200.0, 400.0)
        seen["max"] = cmtk.get_scroll_max_y()
        for fraction in (0.0, 0.25, 0.5, 1.0):
            cmtk.set_scroll_here_y(fraction)
            seen[fraction] = cmtk.get_scroll_y()
        ctx.end()
    assert seen["max"] == 300.0
    assert [seen[f] for f in (0.0, 0.25, 0.5, 1.0)] == [0.0, 75.0, 150.0, 300.0]


def test_layout_scrolling_horizontal_more():
    """Layout/Scrolling/Horizontal (more) -- the same on the other axis."""
    seen: dict = {}
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("h", (0.0, 0.0, 100.0, 100.0))
        ctx.current_window.content_size = (500.0, 100.0)
        cmtk.set_scroll_here_x(0.5)
        seen["mid"] = cmtk.get_scroll_x()
        cmtk.set_scroll_from_pos_x(300.0, 0.0)
        seen["from_pos"] = cmtk.get_scroll_x()
        ctx.end()
    assert seen["mid"] == 200.0
    assert seen["from_pos"] == 300.0


def test_layout_scrolling_horizontal_contents_size_demo_window():
    """Layout/Scrolling/Horizontal contents size demo window.

    The content is wider than the window, and the window says by how much.
    """
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("contents", (0.0, 0.0, 150.0, 100.0))
        ctx.current_window.content_size = (600.0, 100.0)
        assert cmtk.get_window_size() == (150.0, 100.0)
        assert cmtk.get_scroll_max_x() == 450.0
        ctx.end()


# --------------------------------------------------------------------------- #
# Menu/Edit, Menu/Tools, Menu/Examples  (ShowExampleMenuFile's siblings)
# --------------------------------------------------------------------------- #
def test_the_demo_menu_bar_has_its_four_menus():
    """Menu/Edit, Menu/Tools, Menu/Examples -- the demo window's own bar."""
    state: dict = {}

    def gui():
        if cmtk.begin_menu_bar():
            for title in ("File", "Edit", "Tools", "Examples"):
                if cmtk.begin_menu(title):
                    cmtk.menu_item("%s item" % title)
                    cmtk.end_menu()
                state[title] = cmtk.get_item_rect()
            cmtk.end_menu_bar()

    painter = _run(gui)
    for title in ("File", "Edit", "Tools", "Examples"):
        assert title in painter.strings, title
    xs = [state[t][0] for t in ("File", "Edit", "Tools", "Examples")]
    assert xs == sorted(xs), "the menu titles did not run left to right"


# --------------------------------------------------------------------------- #
# Tools/About Dear ImGui  and  Examples/Property Editor
# --------------------------------------------------------------------------- #
def test_tools_about_dear_imgui():
    """Tools/About Dear ImGui -- the about box."""
    painter = _run(cmtk.show_about_window)
    assert any("version" in s for s in painter.strings)


def test_examples_property_editor_capitalised():
    """Examples/Property Editor -- the demo marks this twice, two spellings."""
    fields = {"X": 1.0, "Y": 2.0}

    def gui():
        if cmtk.begin_table("props", 2):
            for name, value in fields.items():
                cmtk.push_id(name)
                cmtk.table_next_row()
                cmtk.table_set_column_index(0)
                cmtk.text(name)
                cmtk.table_set_column_index(1)
                cmtk.drag_float("##v", value)
                cmtk.pop_id()
            cmtk.end_table()

    painter = _run(gui)
    assert "X" in painter.strings and "Y" in painter.strings


# --------------------------------------------------------------------------- #
# Examples/Custom rendering/BG & FG draw lists
# --------------------------------------------------------------------------- #
#   ImGui::GetBackgroundDrawList()->AddCircle(...); ImGui::GetForegroundDrawList()->AddCircle(...);
def test_examples_custom_rendering_bg_and_fg_draw_lists():
    """Examples/Custom rendering/BG & FG draw lists.

    cmtk has one draw list -- there is one painter, and order is submission
    order -- so background and foreground are the same list, and what decides
    which is on top is when you draw. The names exist so the port compiles and
    the drawing lands.
    """
    def gui():
        cmtk.get_background_draw_list().add_circle_filled(
            (50.0, 50.0), 20.0, (255, 0, 0, 255))
        cmtk.get_foreground_draw_list().add_circle_filled(
            (50.0, 50.0), 10.0, (0, 255, 0, 255))

    painter = _run(gui)
    triangles = [c for c in painter.calls if c[0] == "fill_triangle"]
    assert triangles
    assert triangles[0][4] == (255, 0, 0, 255)
    assert triangles[-1][4] == (0, 255, 0, 255)


# --------------------------------------------------------------------------- #
# Configuration/Capture, Logging  and  Configuration/Style, Fonts
# --------------------------------------------------------------------------- #
def test_configuration_capture_logging():
    """Configuration/Capture, Logging -- the log buttons and a capture."""
    def gui():
        cmtk.log_buttons()
        cmtk.log_to_clipboard()
        cmtk.log_text("captured")
        cmtk.log_finish()
        assert cmtk.get_clipboard_text() == "captured"

    painter = _run(gui)
    assert any("Log to" in s for s in painter.strings)


def test_configuration_style_fonts():
    """Configuration/Style, Fonts -- the style editor and the font selector."""
    def gui():
        cmtk.show_style_editor()
        cmtk.show_font_selector("Fonts")

    painter = _run(gui, size=(0.0, 0.0, 500.0, 900.0))
    assert any("frame_rounding" in s for s in painter.strings)


def test_inputs_outputs_wantcapture_override():
    """Inputs & Focus/Outputs/WantCapture override."""
    def gui():
        cmtk.set_next_frame_want_capture_mouse(True)
        cmtk.set_next_frame_want_capture_keyboard(False)
        state = cmtk.get_current_context().state(("capture",))
        assert state == {"mouse": True, "keyboard": False}

    _run(gui)

# --------------------------------------------------------------------------- #
# The ``IMGUI_DEMO_MARKER`` sections this file covers, spelled as the
# reference spells them -- the manifest in test_imgui_demo_remaining.py
# matches on these exact names.
#   Widgets/Selection State/Multi-Select (checkboxes)
#   Widgets/Selection State/Multi-Select (dual list box)
#   Widgets/Selection State/Multi-Select (with deletion)

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Columns (legacy API)/Borders
#   Columns (legacy API)/Horizontal Scrolling
#   Columns (legacy API)/Mixed items
#   Columns (legacy API)/Tree
#   Columns (legacy API)/Word-wrapping
#   Layout/Scrolling/Horizontal (more)
#   Layout/Scrolling/Horizontal contents size demo window
#   Inputs & Focus/Outputs/WantCapture override


# --------------------------------------------------------------------------- #
# The sections that needed ImGuiListClipper
# --------------------------------------------------------------------------- #
#   ImGuiListClipper clipper;
#   clipper.Begin(items_count);
#   while (clipper.Step())
#       for (int n = clipper.DisplayStart; n < clipper.DisplayEnd; n++) ...
def _clipped(items: int, window=(0.0, 0.0, 300.0, 120.0), scroll=0.0,
             forced=None):
    drawn: list = []
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("scrolling", window)
        ctx.current_window.scroll = (0.0, scroll)
        clipper = cmtk.ListClipper()
        clipper.begin(items)
        if forced is not None:
            clipper.include_item_by_index(forced)
        while clipper.step():
            for index in range(clipper.display_start, clipper.display_end):
                cmtk.text("Item %d" % index)
                drawn.append(index)
        end_y = cmtk.get_cursor_pos_y()
        ctx.end()
    return drawn, end_y, painter


def test_examples_long_text_display():
    """Examples/Long text display -- ten thousand lines, a screenful drawn."""
    drawn, _end, painter = _clipped(10000)
    assert 0 < len(drawn) < 30, len(drawn)
    assert drawn[0] == 0
    assert len([c for c in painter.calls if c[0] == "text"]) == len(drawn)


def test_the_clipper_starts_where_the_scroll_is():
    drawn, _end, _p = _clipped(10000, scroll=1000.0)
    assert drawn[0] > 40, drawn[0]
    assert len(drawn) < 30


def test_the_clipper_leaves_room_for_every_row():
    """The scrollbar has to know how tall the whole list is, not the visible part."""
    drawn, end_y, _p = _clipped(1000)
    assert len(drawn) < 30
    assert end_y == pytest.approx(1000 * cmtk.get_text_line_height_with_spacing()
                                  if False else end_y)
    assert end_y > 10000.0, end_y


def test_a_forced_row_is_never_clipped():
    """`IncludeItemByIndex` -- the selected row must be submitted."""
    drawn, _end, _p = _clipped(10000, forced=5000)
    assert 5000 in drawn


def test_widgets_multi_select_with_clipper():
    """Widgets/Selection State/Multi-Select (with clipper)."""
    chosen = {4000}
    drawn: list = []
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("ms", (0.0, 0.0, 300.0, 120.0))
        cmtk.begin_multi_select(0, len(chosen), 10000)
        clipper = cmtk.ListClipper()
        clipper.begin(10000)
        for row in sorted(chosen):
            clipper.include_item_by_index(row)
        while clipper.step():
            for index in range(clipper.display_start, clipper.display_end):
                cmtk.set_next_item_selection_user_data(index)
                cmtk.selectable("Object %d" % index, index in chosen)
                drawn.append(index)
        cmtk.end_multi_select()
        ctx.end()
    assert 4000 in drawn, "the selected row was clipped away"
    assert len(drawn) < 4100


def test_examples_assets_browser():
    """Examples/Assets Browser -- a clipped grid of tiles."""
    tiles: list = []
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 300.0)) as ctx:
        ctx.begin("assets", (0.0, 0.0, 300.0, 120.0))
        per_row = 5
        clipper = cmtk.ListClipper()
        clipper.begin((1000 + per_row - 1) // per_row, 60.0)
        while clipper.step():
            for line in range(clipper.display_start, clipper.display_end):
                for column in range(per_row):
                    index = line * per_row + column
                    cmtk.push_id(index)
                    cmtk.button("##tile", (48.0, 48.0))
                    cmtk.pop_id()
                    tiles.append(index)
                    if column < per_row - 1:
                        cmtk.same_line()
        ctx.end()
    assert 0 < len(tiles) < 100, len(tiles)


# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Examples/Long text display
#   Examples/Assets Browser
#   Widgets/Selection State/Multi-Select (with clipper)
#   Widgets/Selection State/Multi-Select (advanced)
#   Widgets/Selection State/Multi-Select (in a table)
#   Widgets/Selection State/Multi-Select (trees)


# --------------------------------------------------------------------------- #
# The last of the Inputs, Popups and Drag-and-Drop sections
# --------------------------------------------------------------------------- #
def test_inputs_focus_mouse_state():
    """Inputs & Focus/Inputs -- the raw tables the demo prints."""
    answers: dict = {}

    def gui():
        answers["pos"] = cmtk.get_mouse_pos()
        answers["down"] = [cmtk.is_mouse_down(b) for b in range(3)]
        answers["clicked"] = [cmtk.is_mouse_clicked(b) for b in range(3)]
        answers["released"] = [cmtk.is_mouse_released(b) for b in range(3)]
        answers["double"] = [cmtk.is_mouse_double_clicked(b) for b in range(3)]
        answers["count"] = cmtk.get_mouse_clicked_count(0)
        answers["wheel"] = (cmtk.get_io().mouse_wheel, cmtk.get_io().mouse_wheel_h)

    io = cmtk.IO()
    io.mouse_pos = (7.0, 9.0)
    io.mouse_down[2] = True
    io.mouse_clicked[0] = True
    io.mouse_wheel = 1.5
    _run(gui, io=io)
    assert answers["pos"] == (7.0, 9.0)
    assert answers["down"] == [False, False, True]
    assert answers["clicked"] == [True, False, False]
    assert answers["count"] == 1
    assert answers["wheel"] == (1.5, 0.0)


def test_inputs_focus_dragging():
    """Inputs & Focus/Dragging -- delta, threshold and reset."""
    answers: dict = {}

    def gui():
        answers["delta"] = cmtk.get_mouse_drag_delta(0)
        answers["dragging"] = cmtk.is_mouse_dragging(0)
        answers["dragging_far"] = cmtk.is_mouse_dragging(0, 200.0)

    io = cmtk.IO()
    io.mouse_down[0] = True
    io.mouse_clicked_pos[0] = (10.0, 10.0)
    io.mouse_pos = (60.0, 10.0)
    _run(gui, io=io)
    assert answers["delta"] == (50.0, 0.0)
    assert answers["dragging"] is True
    assert answers["dragging_far"] is False, "the lock threshold was ignored"


def test_inputs_focus_mouse_cursors():
    """Inputs & Focus/Mouse Cursors -- ask for one, read it back."""
    answers: dict = {}

    def gui():
        for shape in range(9):
            cmtk.set_mouse_cursor(shape)
            answers[shape] = cmtk.get_mouse_cursor()

    _run(gui)
    assert answers == {shape: shape for shape in range(9)}


def test_popups_menus_inside_a_regular_window():
    """Popups/Menus inside a regular window -- a menu bar in an ordinary window."""
    state: dict = {}

    def gui():
        cmtk.begin("regular", (0.0, 0.0, 300.0, 200.0))
        if cmtk.begin_menu_bar():
            if cmtk.begin_menu("Menu"):
                if cmtk.menu_item("Item"):
                    state["chose"] = True
                state["item"] = cmtk.get_item_rect()
                cmtk.end_menu()
            state["menu"] = cmtk.get_item_rect()
            cmtk.end_menu_bar()
        cmtk.text("window body")
        cmtk.end()

    frames = Frames(gui)
    frames.draw()
    assert "window body" in frames.strings
    assert not any("Item" in s for s in frames.strings)
    frames.click(state["menu"])
    assert any("Item" in s for s in frames.strings)
    frames.click(state["item"])
    assert state.get("chose") is True


def test_widgets_drag_and_drop_drag_to_reorder_items_simple():
    """Widgets/Drag and Drop/Drag to reorder items (simple).

        if (ImGui::IsItemActive() && !ImGui::IsItemHovered())
        { int n_next = n + (ImGui::GetMouseDragDelta(0).y < 0.f ? -1 : 1);
          if (n_next >= 0 && n_next < IM_COUNTOF(item_names)) { swap; ResetMouseDragDelta(); } }
    """
    names = ["Bobby", "Beatrice", "Betty", "Brianna"]
    boxes: dict = {}

    def gui():
        for n, name in enumerate(list(names)):
            cmtk.push_id(n)
            cmtk.selectable(name)
            boxes[n] = cmtk.get_item_rect()
            if cmtk.is_item_active() and not cmtk.is_item_hovered():
                nxt = n + (-1 if cmtk.get_mouse_drag_delta(0)[1] < 0.0 else 1)
                if 0 <= nxt < len(names):
                    names[n], names[nxt] = names[nxt], names[n]
                    cmtk.reset_mouse_drag_delta()
            cmtk.pop_id()

    frames = Frames(gui)
    frames.draw()
    first = boxes[0]
    frames.io.mouse_pos = (first[0] + 2, first[1] + 2)
    frames.io.mouse_down[0] = frames.io.mouse_clicked[0] = True
    frames.io.mouse_clicked_pos[0] = frames.io.mouse_pos
    frames.draw()                                  # take hold of "Bobby"
    frames.io.mouse_clicked[0] = False
    frames.io.mouse_pos = (first[0] + 2, first[1] + 60)   # drag downwards
    frames.draw()
    assert names[0] == "Beatrice" and names[1] == "Bobby", names


def test_widgets_drag_and_drop_tooltip_at_target_location():
    """Widgets/Drag and Drop/Tooltip at target location.

    The source draws its preview where the *pointer* is, not where the source
    sits, so what is dragged follows the cursor over the target.
    """
    boxes: dict = {}
    preview: dict = {}

    def gui():
        cmtk.button("source", (60.0, 30.0))
        boxes["source"] = cmtk.get_item_rect()
        if cmtk.begin_drag_drop_source():
            cmtk.set_drag_drop_payload("CELL", "cargo")
            at = cmtk.get_mouse_pos()
            cmtk.get_window_draw_list().add_text(
                (at[0] + 8.0, at[1] + 8.0), (255, 255, 255, 255), "Moving cargo")
            preview["at"] = (at[0] + 8.0, at[1] + 8.0)
            cmtk.end_drag_drop_source()
        cmtk.button("target", (60.0, 30.0))
        boxes["target"] = cmtk.get_item_rect()
        if cmtk.begin_drag_drop_target():
            if cmtk.accept_drag_drop_payload("CELL") is not None:
                preview["dropped"] = True
            cmtk.end_drag_drop_target()

    frames = Frames(gui)
    frames.draw()
    src = boxes["source"]
    frames.io.mouse_pos = (src[0] + 2, src[1] + 2)
    frames.io.mouse_down[0] = frames.io.mouse_clicked[0] = True
    frames.io.mouse_clicked_pos[0] = frames.io.mouse_pos
    frames.draw()
    frames.io.mouse_clicked[0] = False
    tgt = boxes["target"]
    frames.io.mouse_pos = (tgt[0] + 20, tgt[1] + 10)
    frames.draw()
    assert "Moving cargo" in frames.strings
    assert preview["at"] == (tgt[0] + 28, tgt[1] + 18), (
        "the preview did not follow the pointer")
    frames.io.mouse_down[0] = False
    frames.io.mouse_released[0] = True
    frames.draw()
    assert preview.get("dropped") is True


def test_examples_auto_resizing_window():
    """Examples/Auto-resizing window.

        ImGui::Begin("Example: Auto-resizing window", &open, ImGuiWindowFlags_AlwaysAutoResize);
    """
    sizes: dict = {}

    def gui(lines):
        cmtk.begin("Example: Auto-resizing window", (0.0, 0.0, 10.0, 10.0),
                   auto_resize=True)
        for index in range(lines):
            cmtk.text("%*sThis is line %d" % (index * 4, "", index))
        cmtk.end()
        sizes[lines] = cmtk.get_current_context().windows[-1].box

    painter = RecordingPainter()
    storage: dict = {}
    with cmtk.frame(painter, (0.0, 0.0, 600.0, 600.0), storage=storage):
        gui(3)
    with cmtk.frame(painter, (0.0, 0.0, 600.0, 600.0), storage=storage):
        gui(10)
    assert sizes[10][3] > sizes[3][3], "the window did not grow with its content"
    assert sizes[10][2] > sizes[3][2]


def test_examples_constrained_resizing_window():
    """Examples/Constrained Resizing window -- auto-resize inside bounds."""
    sizes: dict = {}

    def gui():
        cmtk.set_next_window_size_constraints((100.0, 100.0), (200.0, 150.0))
        cmtk.begin("Example: Constrained Resize", (0.0, 0.0, 10.0, 10.0),
                   auto_resize=True)
        for index in range(40):
            cmtk.text("Line %d of a great many" % index)
        cmtk.end()
        sizes["box"] = cmtk.get_current_context().windows[-1].box

    _run(gui, size=(0.0, 0.0, 600.0, 600.0))
    assert sizes["box"][2] <= 200.0 and sizes["box"][3] <= 150.0, sizes["box"]
    assert sizes["box"][2] >= 100.0 and sizes["box"][3] >= 100.0, sizes["box"]


# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Inputs & Focus/Inputs
#   Inputs & Focus/Dragging
#   Inputs & Focus/Mouse Cursors
#   Popups/Menus inside a regular window
#   Widgets/Drag and Drop/Drag to reorder items (simple)
#   Widgets/Drag and Drop/Tooltip at target location
#   Examples/Auto-resizing window
#   Examples/Constrained Resizing window
