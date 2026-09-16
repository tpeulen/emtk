"""``imgui_demo.cpp``'s Examples sections, ported.

The Examples are whole small applications rather than single widgets -- a
console, a log, a property editor, a canvas that draws with the draw list
directly. They are the closest thing the reference has to "what a real port
looks like", so they exercise the parts a widget test never reaches: a scrolling
region that grows, a two-pane layout, a canvas driven by ``GetWindowDrawList``.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import RecordingPainter


def _run(gui, size=(0.0, 0.0, 500.0, 400.0), io=None, storage=None):
    painter = RecordingPainter()
    with emtk.frame(painter, size, io=io or emtk.IO(),
                    storage=storage if storage is not None else {}):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Examples/Console  (imgui_demo.cpp: ExampleAppConsole)
# --------------------------------------------------------------------------- #
#   ImGui::BeginChild("ScrollingRegion", ..., ImGuiChildFlags_NavFlattened, ...);
#   for (const char* item : Items) { ... ImGui::TextUnformatted(item); ... }
#   ImGui::EndChild();
#   ImGui::Separator();
#   if (ImGui::InputText("Input", InputBuf, ..., ImGuiInputTextFlags_EnterReturnsTrue)) { ExecCommand(...); }
class Console:
    """The demo's console, cut to what emtk has."""

    def __init__(self) -> None:
        self.items: list[str] = ["Welcome to Dear ImGui!"]
        self.input = ""
        self.input_box = None

    def exec(self, line: str) -> None:
        self.items.append("# %s" % line)
        if line == "CLEAR":
            self.items = []
        elif line == "HELP":
            self.items.append("Commands: HELP, HISTORY, CLEAR")

    def draw(self) -> None:
        emtk.text_wrapped("Enter 'HELP' for help.")
        if emtk.small_button("Clear"):
            self.items = []
        emtk.separator()
        emtk.begin_child((0.0, 60.0, 400.0, 200.0))
        for item in self.items:
            emtk.text_unformatted(item)
        emtk.end_child()
        emtk.separator()
        _changed, self.input = emtk.input_text("Input", self.input)
        self.input_box = emtk.get_item_rect()


def test_the_console_draws_its_backlog():
    console = Console()
    console.items += ["one", "two", "three"]
    painter = _run(console.draw)
    for line in ("Welcome to Dear ImGui!", "one", "two", "three"):
        assert line in painter.strings, line


def test_the_console_clear_button_empties_it():
    console = Console()
    console.items += ["one", "two"]
    io, storage = emtk.IO(), {}

    box = {}

    def gui():
        emtk.text_wrapped("Enter 'HELP' for help.")
        if emtk.small_button("Clear"):
            console.items = []
        box["clear"] = emtk.get_item_rect()
        for item in console.items:
            emtk.text_unformatted(item)

    _run(gui, io=io, storage=storage)
    io.mouse_pos = (box["clear"][0] + 2, box["clear"][1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    _run(gui, io=io, storage=storage)
    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    _run(gui, io=io, storage=storage)
    assert console.items == []


def test_a_console_command_appends_to_the_backlog():
    console = Console()
    console.exec("HELP")
    assert console.items[-2:] == ["# HELP", "Commands: HELP, HISTORY, CLEAR"]
    console.exec("CLEAR")
    assert console.items == []


# --------------------------------------------------------------------------- #
# Examples/Log  (imgui_demo.cpp: ExampleAppLog)
# --------------------------------------------------------------------------- #
#   if (ImGui::Button("Clear")) Clear();
#   ImGui::SameLine(); bool copy = ImGui::Button("Copy");
#   ImGui::BeginChild("scrolling", ...); ImGui::TextUnformatted(buf_begin, buf_end); ImGui::EndChild();
def test_the_log_example_lays_out_its_toolbar_on_one_line():
    boxes: dict = {}
    lines = ["[%05d] Hello, current time is %.1f" % (n, n * 0.1) for n in range(5)]

    def gui():
        if emtk.button("Clear"):
            lines.clear()
        boxes["clear"] = emtk.get_item_rect()
        emtk.same_line()
        emtk.button("Copy")
        boxes["copy"] = emtk.get_item_rect()
        emtk.separator()
        emtk.begin_child((0.0, 40.0, 400.0, 200.0))
        for line in lines:
            emtk.text_unformatted(line)
        emtk.end_child()

    painter = _run(gui)
    assert boxes["clear"][1] == boxes["copy"][1]
    assert boxes["copy"][0] > boxes["clear"][0]
    assert sum(1 for s in painter.strings if s.startswith("[")) == 5


def test_the_log_can_be_captured_to_the_clipboard():
    """`LogToClipboard` / `LogText` / `LogFinish` -- the demo's Copy button."""
    def gui():
        emtk.log_to_clipboard()
        for n in range(3):
            emtk.log_text("line %d\n" % n)
        emtk.log_finish()
        assert emtk.get_clipboard_text() == "line 0\nline 1\nline 2\n"

    _run(gui)


# --------------------------------------------------------------------------- #
# Examples/Simple layout  (imgui_demo.cpp: ExampleAppLayout)
# --------------------------------------------------------------------------- #
#   { ImGui::BeginChild("left pane", ImVec2(150, 0), ImGuiChildFlags_Borders | ...);
#     for (int i = 0; i < 100; i++) if (ImGui::Selectable(label, selected == i)) selected = i;
#     ImGui::EndChild(); }
#   ImGui::SameLine();
#   { ImGui::BeginGroup(); ImGui::BeginChild("item view", ...); ... ImGui::EndGroup(); }
def test_the_two_pane_layout_puts_the_panes_side_by_side():
    state = {"selected": 0, "boxes": {}}

    def gui():
        emtk.begin_child((0.0, 0.0, 150.0, 300.0))
        for index in range(5):
            if emtk.selectable("MyObject %d" % index, state["selected"] == index):
                state["selected"] = index
            state["boxes"][index] = emtk.get_item_rect()
        emtk.end_child()
        emtk.same_line()
        emtk.begin_group()
        emtk.begin_child((160.0, 0.0, 300.0, 300.0))
        emtk.text("MyObject: %d" % state["selected"])
        state["boxes"]["detail"] = emtk.get_item_rect()
        emtk.end_child()
        emtk.end_group()

    _run(gui)
    left = state["boxes"][0]
    right = state["boxes"]["detail"]
    assert right[0] > left[0] + 100.0, "the right pane did not sit beside the left"


# --------------------------------------------------------------------------- #
# Examples/Property editor
# --------------------------------------------------------------------------- #
#   ImGui::PushID(uid); ImGui::TableNextRow(); ImGui::TableSetColumnIndex(0);
#   ImGui::AlignTextToFramePadding(); ... ImGui::TableSetColumnIndex(1);
#   ImGui::SetNextItemWidth(-FLT_MIN); ImGui::DragFloat("##value", &placeholder);
#   ImGui::PopID();
def test_the_property_editor_puts_a_field_beside_each_name():
    rows: dict = {}
    fields = {"Position": 1.0, "Rotation": 2.0, "Scale": 3.0}

    def gui():
        if emtk.begin_table("split", 2):
            for uid, (name, value) in enumerate(fields.items()):
                emtk.push_id(uid)
                emtk.table_next_row()
                emtk.table_set_column_index(0)
                emtk.align_text_to_frame_padding()
                emtk.text(name)
                rows[(name, "label")] = emtk.get_item_rect()
                emtk.table_set_column_index(1)
                emtk.set_next_item_width(80.0)
                _changed, fields[name] = emtk.drag_float("##value", value)
                rows[(name, "field")] = emtk.get_item_rect()
                emtk.pop_id()
            emtk.end_table()

    _run(gui)
    for name in fields:
        label, field = rows[(name, "label")], rows[(name, "field")]
        assert field[0] > label[0], (name, label, field)
        assert abs(field[1] - label[1]) < 4.0, (name, label, field)
    # Each row is below the last.
    ys = [rows[(n, "label")][1] for n in fields]
    assert ys == sorted(ys) and len(set(ys)) == 3


# --------------------------------------------------------------------------- #
# Examples/Custom rendering/Primitives  (imgui_demo.cpp:10268)
# --------------------------------------------------------------------------- #
#   ImDrawList* draw_list = ImGui::GetWindowDrawList();
#   ImVec2 p0 = ImGui::GetCursorScreenPos();
#   draw_list->AddRectFilledMultiColor(p0, p1, col_a, col_b, col_b, col_a);
#   ImGui::InvisibleButton("##gradient1", gradient_size);
def test_a_gradient_drawn_by_hand_lands_where_the_cursor_is():
    boxes: dict = {}

    def gui():
        emtk.text("Gradients")
        draw = emtk.get_window_draw_list()
        size = (emtk.calc_item_width(), emtk.get_frame_height())
        p0 = emtk.get_cursor_screen_pos()
        p1 = (p0[0] + size[0], p0[1] + size[1])
        draw.add_rect_filled_multi_color(p0, p1, (0, 0, 0, 255),
                                         (255, 255, 255, 255),
                                         (255, 255, 255, 255), (0, 0, 0, 255))
        emtk.invisible_button("##gradient1", size)
        boxes["button"] = emtk.get_item_rect()
        boxes["p0"] = p0

    painter = _run(gui)
    assert boxes["button"][:2] == pytest.approx(boxes["p0"])
    assert any(c[0] in ("gradient_rect", "fill_rect") for c in painter.calls)


def test_the_primitives_the_custom_rendering_section_draws():
    """One of each, on the window's own draw list."""
    def gui():
        draw = emtk.get_window_draw_list()
        white = (255, 255, 255, 255)
        draw.add_line((0.0, 0.0), (50.0, 50.0), white, 1.0)
        draw.add_rect((0.0, 0.0), (50.0, 50.0), white, 4.0)
        draw.add_rect_filled((0.0, 0.0), (50.0, 50.0), white, 4.0)
        draw.add_rect_filled((0.0, 0.0), (50.0, 50.0), white, 0.0)   # square
        draw.add_circle((25.0, 25.0), 20.0, white, 0, 1.0)
        draw.add_circle_filled((25.0, 25.0), 20.0, white, 0)
        draw.add_ngon((25.0, 25.0), 20.0, white, 5, 1.0)
        draw.add_ngon_filled((25.0, 25.0), 20.0, white, 5)
        draw.add_triangle((0.0, 0.0), (25.0, 50.0), (50.0, 0.0), white, 1.0)
        draw.add_triangle_filled((0.0, 0.0), (25.0, 50.0), (50.0, 0.0), white)
        draw.add_bezier_cubic((0.0, 0.0), (10.0, 40.0), (40.0, 10.0),
                              (50.0, 50.0), white, 1.0, 0)
        draw.add_bezier_quadratic((0.0, 0.0), (25.0, 50.0), (50.0, 0.0), white, 1.0, 0)
        draw.add_ellipse((25.0, 25.0), (20.0, 10.0), white)
        draw.add_ellipse_filled((25.0, 25.0), (20.0, 10.0), white)
        draw.add_text((0.0, 60.0), white, "hello")
        draw.add_polyline([(0.0, 0.0), (25.0, 25.0), (50.0, 0.0)], white, 0, 2.0)
        draw.add_convex_poly_filled([(0.0, 0.0), (25.0, 25.0), (50.0, 0.0)], white)
        draw.add_concave_poly_filled(
            [(0.0, 0.0), (50.0, 25.0), (0.0, 50.0), (15.0, 25.0)], white)

    painter = _run(gui)
    kinds = {call[0] for call in painter.calls}
    assert {"fill_rect", "fill_triangle", "text"} <= kinds, kinds
    assert "hello" in painter.strings


# --------------------------------------------------------------------------- #
# Examples/Custom rendering/Draw Channels
# --------------------------------------------------------------------------- #
#   draw_list->ChannelsSplit(2); draw_list->ChannelsSetCurrent(1); ...
#   draw_list->ChannelsSetCurrent(0); ... draw_list->ChannelsMerge();
def test_the_draw_channels_example_puts_the_background_behind():
    """The demo draws the *foreground* first, on channel 1, then the
    background on channel 0 -- and merging puts them back in the right order,
    which is the whole reason the splitter exists."""
    def gui():
        draw = emtk.get_window_draw_list()
        draw.channels_split(2)
        draw.channels_set_current(1)
        draw.add_rect_filled((25.0, 25.0), (75.0, 75.0), (255, 0, 0, 255))
        draw.channels_set_current(0)
        draw.add_rect_filled((0.0, 0.0), (100.0, 100.0), (0, 255, 0, 255))
        draw.channels_merge()

    painter = _run(gui)
    order = [c[5] for c in painter.calls if c[0] == "fill_rect"]
    assert order == [(0, 255, 0, 255), (255, 0, 0, 255)], order


# --------------------------------------------------------------------------- #
# Examples/Auto-resizing and Simple overlay
# --------------------------------------------------------------------------- #
def test_a_window_reports_where_it_is_so_an_overlay_can_be_placed():
    #   const ImGuiViewport* viewport = ImGui::GetMainViewport();
    #   ImVec2 work_pos = viewport->WorkPos; ... ImGui::SetNextWindowPos(window_pos, ...);
    answers: dict = {}

    def gui():
        viewport = emtk.get_main_viewport()
        answers["work_pos"] = viewport.work_pos
        answers["work_size"] = viewport.work_size
        emtk.set_next_window_pos((viewport.work_pos[0] + 10.0,
                                  viewport.work_pos[1] + 10.0))
        emtk.set_next_window_bg_alpha(0.35)
        emtk.begin("Example: Simple overlay", (10.0, 10.0, 200.0, 60.0))
        emtk.text("Simple overlay")
        answers["pos"] = emtk.get_window_pos()
        emtk.end()

    _run(gui)
    assert answers["work_pos"] == (0.0, 0.0)
    assert answers["work_size"] == (500.0, 400.0)
    assert answers["pos"] == (10.0, 10.0)

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Examples/Simple overlay
