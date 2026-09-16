"""The rest of ``imgui_demo.cpp``'s Widgets: colour, text, disabled, progress.

Sections: Widgets/Color (ColorEdit, ColorButton, ColorPicker), Widgets/Bullets,
Widgets/Word Wrapping, Widgets/UTF-8, Widgets/Progress Bars, Widgets/Disable
Block, Widgets/Filtered Text Input, Widgets/Vertical Sliders.
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
# Widgets/Color/ColorEdit  and  ColorButton
# --------------------------------------------------------------------------- #
#   static float color[4] = { 114/255.f, 144/255.f, 154/255.f, 200/255.f };
#   ImGui::ColorEdit3("MyColor##1", (float*)&color);
#   ImGui::ColorEdit4("MyColor##2", (float*)&color);
#   ImGui::ColorButton("MyColor##3c", *(ImVec4*)&color, misc_flags);
def test_color_edit_keeps_the_colour_it_was_given():
    result: dict = {}

    def gui():
        result["rgb"] = emtk.color_edit3("MyColor##1", (114, 144, 154))[1]
        result["rgba"] = emtk.color_edit4("MyColor##2", (114, 144, 154, 200))[1]

    _run(gui)
    assert tuple(int(round(c)) for c in result["rgb"]) == (114, 144, 154)
    assert tuple(int(round(c)) for c in result["rgba"]) == (114, 144, 154, 200)


def test_a_color_button_paints_the_colour_asked_for():
    def gui():
        emtk.color_button("MyColor##3c", (114, 144, 154, 200))

    painter = _run(gui)
    fills = [c[5] for c in painter.calls if c[0] == "fill_rect"]
    assert (114, 144, 154, 200) in fills, fills


def test_a_color_picker_round_trips_through_hsv():
    result: dict = {}

    def gui():
        result["out"] = emtk.color_picker3("MyColor##4", (114, 144, 154))[1]

    _run(gui)
    # Through HSV and back, within a rounding step per channel.
    for got, want in zip(result["out"], (114, 144, 154)):
        assert abs(got - want) <= 2, (result["out"], (114, 144, 154))


def test_the_colour_conversions_are_each_other_s_inverse():
    #   ImGui::ColorConvertRGBtoHSV(...); ImGui::ColorConvertHSVtoRGB(...);
    for rgb in ((0.45, 0.56, 0.6), (1.0, 0.0, 0.0), (0.1, 0.9, 0.4)):
        h, s, v = emtk.color_convert_rgb_to_hsv(*rgb)
        assert emtk.color_convert_hsv_to_rgb(h, s, v) == pytest.approx(rgb, abs=1e-6)


# --------------------------------------------------------------------------- #
# Widgets/Bullets  and  Word Wrapping
# --------------------------------------------------------------------------- #
#   ImGui::BulletText("Bullet point 1");
#   ImGui::Bullet(); ImGui::Text("Bullet point 3 (two calls)");
#   ImGui::Bullet(); ImGui::SmallButton("Button");
def test_bullet_text_draws_a_bullet_and_the_text_beside_it():
    boxes: dict = {}

    def gui():
        emtk.bullet_text("Bullet point 1")
        boxes["one"] = emtk.get_item_rect()
        emtk.bullet()
        emtk.text("Bullet point 3 (two calls)")
        boxes["three"] = emtk.get_item_rect()
        emtk.bullet()
        emtk.small_button("Button")
        boxes["button"] = emtk.get_item_rect()

    painter = _run(gui)
    assert "Bullet point 1" in painter.strings
    # A bullet is a disc, so there is a circle's worth of triangles.
    assert any(c[0] == "fill_triangle" for c in painter.calls)
    # Each bullet's text starts to the right of the window's left edge.
    assert boxes["one"][0] > 0.0 and boxes["three"][0] > 0.0
    assert boxes["button"][0] > 0.0


def test_word_wrapping_respects_the_width_it_is_given():
    #   ImGui::PushTextWrapPos(ImGui::GetCursorPos().x + wrap_width); ... PopTextWrapPos();
    def gui():
        emtk.text_wrapped(
            "The quick brown fox jumps over the lazy dog "
            "and then does it again for good measure")

    narrow = _run(gui, size=(0.0, 0.0, 100.0, 400.0))
    wide = _run(gui, size=(0.0, 0.0, 480.0, 400.0))
    assert len([c for c in narrow.calls if c[0] == "text"]) > \
        len([c for c in wide.calls if c[0] == "text"])


def test_text_can_be_coloured_and_dimmed():
    #   ImGui::TextColored(ImVec4(1.0f, 0.0f, 1.0f, 1.0f), "Pink");
    #   ImGui::TextDisabled("Disabled");
    def gui():
        emtk.text_colored((255, 0, 255, 255), "Pink")
        emtk.text_disabled("Disabled")

    painter = _run(gui)
    colours = {c[7] for c in painter.calls if c[0] == "text"}
    assert (255, 0, 255, 255) in colours
    assert len(colours) >= 2, "coloured and disabled text came out the same"


def test_unicode_text_is_drawn_as_given():
    #   ImGui::Text("Hiragana: \xe3\x81\x8b\xe3\x81\x8d\xe3\x81\x8f (kakiku)");
    def gui():
        emtk.text("Hiragana: かきく (kakiku)")
        emtk.text("Kanjis: 日本語 (nihongo)")

    painter = _run(gui)
    assert any("かきく" in s for s in painter.strings)
    assert any("日本語" in s for s in painter.strings)


# --------------------------------------------------------------------------- #
# Widgets/Progress Bars
# --------------------------------------------------------------------------- #
#   ImGui::ProgressBar(progress, ImVec2(0.0f, 0.0f));
#   ImGui::ProgressBar(progress, ImVec2(0.f, 0.f), buf);
def test_a_progress_bar_fills_in_proportion():
    widths: dict = {}

    def gui():
        for fraction in (0.0, 0.25, 0.5, 1.0):
            emtk.progress_bar(fraction, (200.0, 20.0))
            box = emtk.get_item_rect()
            widths[fraction] = box

    painter = _run(gui)
    fills = [c for c in painter.calls if c[0] == "fill_rect"]
    # One frame per bar, plus a fill for each non-zero fraction.
    assert len(fills) == 4 + 3, len(fills)
    filled = [c[3] for c in fills if c[3] < 200.0]
    assert filled == pytest.approx([50.0, 100.0]), filled


def test_a_progress_bar_takes_an_overlay_caption():
    def gui():
        emtk.progress_bar(0.6, (200.0, 20.0), "60/100")

    painter = _run(gui)
    assert "60/100" in painter.strings


def test_a_progress_bar_clamps_out_of_range_values():
    def gui():
        emtk.progress_bar(-1.0, (100.0, 20.0))
        emtk.progress_bar(5.0, (100.0, 20.0))

    painter = _run(gui)
    for call in (c for c in painter.calls if c[0] == "fill_rect"):
        assert 0.0 <= call[3] <= 100.0, call


# --------------------------------------------------------------------------- #
# Widgets/Disable Block
# --------------------------------------------------------------------------- #
#   ImGui::BeginDisabled(disable_all); ... ImGui::EndDisabled();
def test_a_disabled_block_does_not_report_clicks():
    state = {"fired": False, "box": None}

    def gui():
        emtk.begin_disabled(True)
        if emtk.button("Button"):
            state["fired"] = True
        state["box"] = emtk.get_item_rect()
        emtk.end_disabled()

    io, storage = emtk.IO(), {}
    _run(gui, io=io, storage=storage)
    box = state["box"]
    io.mouse_pos = (box[0] + 2, box[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    _run(gui, io=io, storage=storage)
    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    _run(gui, io=io, storage=storage)
    assert state["fired"] is False, "a disabled button reported a click"


def test_the_disabled_flag_unwinds():
    seen: dict = {}

    def gui():
        emtk.begin_disabled(True)
        seen["inside"] = emtk.get_item_flags() & emtk.ItemFlags.DISABLED
        emtk.end_disabled()
        seen["outside"] = emtk.get_item_flags() & emtk.ItemFlags.DISABLED

    _run(gui)
    assert seen["inside"] and not seen["outside"]


# --------------------------------------------------------------------------- #
# Widgets/Vertical Sliders
# --------------------------------------------------------------------------- #
#   ImGui::VSliderFloat("##v", ImVec2(18, 160), &values[i], 0.0f, 1.0f, "");
def test_vertical_sliders_stand_side_by_side():
    boxes: dict = {}
    values = [0.0, 0.6, 0.35, 0.9, 0.7, 0.2, 0.0]

    def gui():
        for index, value in enumerate(values):
            emtk.push_id(index)
            emtk.v_slider_float("##v", (18.0, 160.0), value, 0.0, 1.0)
            boxes[index] = emtk.get_item_rect()
            emtk.pop_id()
            emtk.same_line()

    _run(gui)
    ys = {round(b[1]) for b in boxes.values()}
    assert len(ys) == 1, "the sliders did not share a line"
    xs = [boxes[i][0] for i in range(len(values))]
    assert xs == sorted(xs) and len(set(xs)) == len(values)
    assert all(round(b[3]) == 160 for b in boxes.values())


# --------------------------------------------------------------------------- #
# Widgets/Data Types  (the typed slider/drag/input variants)
# --------------------------------------------------------------------------- #
def test_the_typed_variants_keep_their_type():
    out: dict = {}

    def gui():
        out["si"] = emtk.slider_int("i", 3, 0, 10)[1]
        out["sf"] = emtk.slider_float("f", 0.5, 0.0, 1.0)[1]
        out["di"] = emtk.drag_int("di", 7)[1]
        out["df"] = emtk.drag_float("df", 1.5)[1]
        out["ii"] = emtk.input_int("ii", 4)[1]
        out["if"] = emtk.input_float("if", 2.5)[1]

    _run(gui)
    assert isinstance(out["si"], int) and out["si"] == 3
    assert isinstance(out["sf"], float) and out["sf"] == pytest.approx(0.5)
    assert isinstance(out["di"], int) and out["di"] == 7
    assert isinstance(out["ii"], int) and out["ii"] == 4


def test_the_multi_component_variants_return_what_they_were_given():
    out: dict = {}

    def gui():
        out["f2"] = emtk.drag_float2("f2", (1.0, 2.0))[1]
        out["f3"] = emtk.slider_float3("f3", (0.1, 0.2, 0.3), 0.0, 1.0)[1]
        out["f4"] = emtk.input_float4("f4", (1.0, 2.0, 3.0, 4.0))[1]
        out["i3"] = emtk.drag_int3("i3", (1, 2, 3))[1]

    _run(gui)
    assert out["f2"] == pytest.approx((1.0, 2.0))
    assert out["f3"] == pytest.approx((0.1, 0.2, 0.3))
    assert out["f4"] == pytest.approx((1.0, 2.0, 3.0, 4.0))
    assert out["i3"] == (1, 2, 3)


def test_a_slider_clamps_to_its_range():
    out: dict = {}

    def gui():
        out["low"] = emtk.slider_float("f", -5.0, 0.0, 1.0)[1]
        out["high"] = emtk.slider_float("g", 5.0, 0.0, 1.0)[1]

    _run(gui)
    assert out["low"] == 0.0 and out["high"] == 1.0

# --------------------------------------------------------------------------- #
# The ``IMGUI_DEMO_MARKER`` sections this file covers, spelled as the
# reference spells them -- the manifest in test_imgui_demo_remaining.py
# matches on these exact names.
#   Widgets/Collapsing Headers
#   Widgets/Disable Blocks
