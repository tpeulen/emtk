"""``imgui_demo.cpp``, ported. What the port cannot express is a cmtk defect.

cmtk exists so that Dear ImGui code can be brought to Python and drawn on GL.
The way to find out whether it can is to take the reference's own demo and
transliterate it -- not a sketch of it, the actual sequence of calls from
``imgui_demo.cpp`` -- and see what has no answer here. Every function this file
needed and cmtk lacked was added because *this* asked for it, which is a better
list than one guessed in advance.

Ported below: the "Widgets/Basic" section (``imgui_demo.cpp`` around line 929
onward). The C++ is quoted beside each block so the two can be read together.

What the port needed and cmtk did not have, all now present:

* ``ImGui::RadioButton(label, &v, v_button)`` -- the int overload, which is
  the three-argument call and returns ``(changed, v)``.
* ``ImGui::PushStyleColor`` / ``PopStyleColor`` -- and behind it a real
  ``ImGuiStyle`` colour *stack*: the widgets read
  ``style.color(Col.BUTTON)`` per call instead of importing a constant, or
  the demo's row of seven coloured buttons cannot be coloured at all.
* ``ImGui::PushItemFlag(ImGuiItemFlags_ButtonRepeat)`` and the repeat
  behaviour inside ``ButtonBehavior`` -- a held arrow that fires again after a
  delay, at a rate.
* ``ImGui::ArrowButton``, ``ImGui::SeparatorText``,
  ``ImGui::AlignTextToFramePadding``, ``ImGui::SetItemTooltip``,
  ``ImGui::SetNextItemWidth``, ``ImGui::CheckboxFlags``,
  ``ImGui::SliderAngle``, ``ImGui::InputFloat``/``InputInt``/``InputText``,
  ``ImGui::ColorButton``/``ColorEdit3``.
"""
from __future__ import annotations

import math

import pytest

import cmtk
from cmtk.testing import RecordingPainter


class DemoState:
    """The demo's ``static`` variables, which Python must hold somewhere."""

    def __init__(self) -> None:
        self.clicked = 0
        self.check = True
        self.e = 0
        self.counter = 0
        self.text = "Hello, world!"
        self.f = 0.001
        self.i = 123
        self.angle = 0.0
        self.col = (102, 25, 25)
        self.flags = 0
        #: Where a widget landed, so a test can click it without replaying a
        #: different sequence and guessing.
        self.boxes: dict = {}


def widgets_basic(state: DemoState, io: cmtk.IO, storage: dict) -> RecordingPainter:
    """``ShowDemoWindowWidgets``'s "Basic" section, line for line."""
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 420.0, 700.0), io=io, storage=storage) as ctx:
        cmtk.begin("Dear ImGui Demo")

        # if (ImGui::Button("Button")) { clicked++; }
        # if (clicked & 1) { ImGui::SameLine(); ImGui::Text("Thanks for clicking me!"); }
        if cmtk.button("Button"):
            state.clicked += 1
        if state.clicked & 1:
            cmtk.same_line()
            cmtk.text("Thanks for clicking me!")

        # ImGui::Checkbox("checkbox", &check);
        _, state.check = cmtk.checkbox("checkbox", state.check)

        # ImGui::RadioButton("radio a", &e, 0); ImGui::SameLine();
        # ImGui::RadioButton("radio b", &e, 1); ImGui::SameLine();
        # ImGui::RadioButton("radio c", &e, 2);
        _, state.e = cmtk.radio_button("radio a", state.e, 0)
        cmtk.same_line()
        _, state.e = cmtk.radio_button("radio b", state.e, 1)
        cmtk.same_line()
        _, state.e = cmtk.radio_button("radio c", state.e, 2)

        # for (int i = 0; i < 7; i++) { PushID(i); PushStyleColor(...); Button("Click"); ... }
        for i in range(7):
            if i > 0:
                cmtk.same_line()
            cmtk.push_id(i)
            cmtk.push_style_color(cmtk.Col.BUTTON, _hsv(i / 7.0, 0.6, 0.6))
            cmtk.push_style_color(cmtk.Col.BUTTON_HOVERED, _hsv(i / 7.0, 0.7, 0.7))
            cmtk.push_style_color(cmtk.Col.BUTTON_ACTIVE, _hsv(i / 7.0, 0.8, 0.8))
            cmtk.button("Click")
            cmtk.pop_style_color(3)
            cmtk.pop_id()

        # ImGui::AlignTextToFramePadding();
        # ImGui::Text("Hold to repeat:"); ImGui::SameLine();
        cmtk.align_text_to_frame_padding()
        cmtk.text("Hold to repeat:")
        cmtk.same_line()

        # PushItemFlag(ImGuiItemFlags_ButtonRepeat, true);
        # if (ArrowButton("##left", ImGuiDir_Left)) { counter--; } SameLine(0, spacing);
        # if (ArrowButton("##right", ImGuiDir_Right)) { counter++; } PopItemFlag();
        spacing = cmtk.get_style().item_inner_spacing[0]
        cmtk.push_item_flag(cmtk.ItemFlags.BUTTON_REPEAT, True)
        if cmtk.arrow_button("##left", cmtk.Dir.LEFT):
            state.counter -= 1
        state.boxes["##left"] = ctx.get_item_rect()   # for the test below
        cmtk.same_line(0.0, spacing)
        if cmtk.arrow_button("##right", cmtk.Dir.RIGHT):
            state.counter += 1
        cmtk.pop_item_flag()
        cmtk.same_line()
        cmtk.text("%d" % state.counter)

        # ImGui::Button("Tooltip"); ImGui::SetItemTooltip("I am a tooltip");
        cmtk.button("Tooltip")
        cmtk.set_item_tooltip("I am a tooltip")

        # ImGui::LabelText("label", "Value");
        cmtk.label_text("label", "Value")

        # ImGui::SeparatorText("Inputs");
        cmtk.separator_text("Inputs")

        # ImGui::InputText("input text", str0, IM_ARRAYSIZE(str0));
        _, state.text = cmtk.input_text("input text", state.text)
        # ImGui::InputTextWithHint("input text (w/ hint)", "enter text here", ...);
        cmtk.input_text_with_hint("input text (w/ hint)", "enter text here", "")
        # ImGui::InputFloat("input float", &f0, 0.01f, 1.0f, "%.3f");
        _, state.f = cmtk.input_float("input float", state.f, 0.01, 1.0, "%.3f")
        # ImGui::InputInt("input int", &i0);
        _, state.i = cmtk.input_int("input int", state.i)

        cmtk.separator_text("Drags")
        # ImGui::DragFloat("drag float", &f1, 0.005f);
        _, state.f = cmtk.drag_float("drag float", state.f, 0.005)
        # ImGui::DragInt("drag int", &i1, 1);
        _, state.i = cmtk.drag_int("drag int", state.i, 1)

        cmtk.separator_text("Sliders")
        # ImGui::SliderInt("slider int", &i1, -1, 3);
        _, state.i = cmtk.slider_int("slider int", state.i, -1, 3)
        # ImGui::SliderFloat("slider float", &f1, 0.0f, 1.0f, "ratio = %.3f");
        _, state.f = cmtk.slider_float("slider float", state.f, 0.0, 1.0, "ratio = %.3f")
        # ImGui::SliderAngle("slider angle", &angle);
        _, state.angle = cmtk.slider_angle("slider angle", state.angle)

        cmtk.separator_text("Selectors/Pickers")
        # ImGui::ColorEdit3("color 1", (float*)&color);
        _, state.col = cmtk.color_edit3("color 1", state.col)
        # ImGui::CheckboxFlags("flag", &flags, 1 << 0);
        _, state.flags = cmtk.checkbox_flags("flag", state.flags, 1 << 0)

        cmtk.end()
    return painter


def _hsv(h: float, s: float, v: float) -> tuple:
    """``ImColor::HSV``, which the demo colours its buttons with."""
    i = int(h * 6.0)
    f = h * 6.0 - i
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i % 6]
    return (int(r * 255), int(g * 255), int(b * 255), 255)


@pytest.fixture
def demo():
    return DemoState(), cmtk.IO(), {}


# --------------------------------------------------------------------------- #
def test_the_demo_section_runs_at_all(demo):
    """The blunt one: a faithful transliteration must not raise."""
    state, io, storage = demo
    painter = widgets_basic(state, io, storage)
    assert painter.calls, "the demo drew nothing"


def test_every_widget_in_the_section_drew_something(demo):
    state, io, storage = demo
    painter = widgets_basic(state, io, storage)
    for label in ("Button", "checkbox", "radio a", "Click", "Hold to repeat:",
                  "Tooltip", "label", "Inputs", "Drags", "Sliders",
                  "input text", "slider angle", "flag"):
        assert any(label in s for s in painter.strings), f"{label!r} was not drawn"


def test_pushing_a_style_colour_reaches_the_widget(demo):
    """The demo's seven buttons are seven colours, or `PushStyleColor` is a no-op."""
    state, io, storage = demo
    painter = widgets_basic(state, io, storage)
    fills = {call[5] for call in painter.calls if call[0] == "fill_rect"}
    wanted = {_hsv(i / 7.0, 0.6, 0.6) for i in range(7)}
    assert wanted <= fills, sorted(wanted - fills)


def test_the_style_colour_stack_unwinds(demo):
    """`PopStyleColor(3)` puts back what was there, or every later widget is dyed."""
    state, io, storage = demo
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0)) as ctx:
        before = ctx.style.color(cmtk.Col.BUTTON)
        cmtk.push_style_color(cmtk.Col.BUTTON, (1, 2, 3, 255))
        cmtk.push_style_color(cmtk.Col.BUTTON_HOVERED, (4, 5, 6, 255))
        cmtk.push_style_color(cmtk.Col.BUTTON_ACTIVE, (7, 8, 9, 255))
        assert ctx.style.color(cmtk.Col.BUTTON) == (1, 2, 3, 255)
        cmtk.pop_style_color(3)
        assert ctx.style.color(cmtk.Col.BUTTON) == before


def test_push_id_keeps_the_seven_buttons_apart(demo):
    """Without `PushID`, seven buttons labelled "Click" are one button.

    They would share an id, so the first would claim the pointer and the other
    six would be dead -- which is the bug `PushID` exists to prevent and the
    reason the demo shows it here.
    """
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 400.0, 100.0)) as ctx:
        ids = []
        for i in range(7):
            cmtk.push_id(i)
            ids.append(ctx.get_id("Click"))
            cmtk.pop_id()
    assert len(set(ids)) == 7, ids


def test_a_repeating_button_fires_again_while_held(demo):
    """`ImGuiItemFlags_ButtonRepeat`: after a delay, at a rate."""
    state, io, storage = demo
    widgets_basic(state, io, storage)                 # place the items

    box = state.boxes["##left"]
    io.mouse_pos = (box[0] + 2, box[1] + 2)
    io.mouse_down[0] = True
    io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    widgets_basic(state, io, storage)
    first = state.counter

    # The backend owns the clock, as an ImGui backend does: it sets
    # `io.DeltaTime` and the context accumulates it.
    io.wall_clock = False
    io.delta_time = 0.05
    io.mouse_clicked[0] = False
    for _tick in range(40):                            # hold it down
        widgets_basic(state, io, storage)
    # `##left` is the *decrement* arrow in the demo, so repeating drives the
    # counter down.
    assert state.counter < first, "a held repeat button never repeated"
    assert state.counter < -5, f"it repeated only {first - state.counter} times"


def test_a_tooltip_only_appears_over_its_item(demo):
    """`SetItemTooltip` asks `IsItemHovered`, which asks `ItemAdd`."""
    state, io, storage = demo
    widgets_basic(state, io, storage)
    io.mouse_pos = (-1.0, -1.0)
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 420.0, 700.0), io=io, storage=storage) as ctx:
        cmtk.begin("Dear ImGui Demo")
        cmtk.button("Tooltip")
        cmtk.set_item_tooltip("I am a tooltip")
        cmtk.end()
        assert ctx.tooltip is None

    io.mouse_pos = (4.0, 4.0)                          # over the button
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 420.0, 700.0), io=io, storage=storage) as ctx:
        cmtk.begin("Dear ImGui Demo")
        cmtk.button("Tooltip")
        cmtk.set_item_tooltip("I am a tooltip")
        cmtk.end()
        assert ctx.tooltip == "I am a tooltip"


def test_checkbox_flags_sets_one_bit(demo):
    changed, flags = im_flags(0, 1 << 2)
    assert changed and flags == 1 << 2
    changed, flags = im_flags(flags, 1 << 2)
    assert changed and flags == 0


def im_flags(flags: int, bit: int) -> tuple[bool, int]:
    """One `CheckboxFlags`, clicked once."""
    io = cmtk.IO()
    storage: dict = {}
    for phase in ("place", "press", "release"):
        painter = RecordingPainter()
        with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0), io=io, storage=storage) as ctx:
            changed, flags = cmtk.checkbox_flags("flag", flags, bit)
            box = ctx.get_item_rect()
        if phase == "place":
            io.mouse_pos = (box[0] + 2, box[1] + 2)
            io.mouse_down[0] = True
            io.mouse_clicked[0] = True
            io.mouse_clicked_pos[0] = io.mouse_pos
        elif phase == "press":
            io.mouse_down[0] = False
            io.mouse_released[0] = True
    return changed, flags

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Widgets/Basic
#   Widgets/Basic/Button
#   Widgets/Basic/Buttons (Colored)
#   Widgets/Basic/Buttons (Repeating)
#   Widgets/Basic/Checkbox
#   Widgets/Basic/ColorEdit3, ColorEdit4
#   Widgets/Basic/DragInt, DragFloat
#   Widgets/Basic/InputInt, InputFloat
#   Widgets/Basic/InputText
#   Widgets/Basic/RadioButton
#   Widgets/Basic/SliderAngle
#   Widgets/Basic/SliderInt, SliderFloat
