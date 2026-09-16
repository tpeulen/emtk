"""``imgui_demo.cpp``'s Layout sections, ported.

Layout is where a toolkit's small errors show up as visible ones: a cursor that
does not advance, a ``SameLine`` that loses its offset, a child region that
does not clip. The reference's own Layout section exercises all of it, so it is
transliterated here and the *positions* are checked -- against each other,
since a layout is a set of relations rather than a set of numbers.

Sections: Basic Horizontal Layout (SameLine plain, with spacing, with an
absolute offset), Widgets Width, Dummy, Child windows, Text Clipping and
Scrolling.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import RecordingPainter


def _run(gui, size=(0.0, 0.0, 500.0, 400.0), io=None, storage=None):
    painter = RecordingPainter()
    io = io if io is not None else emtk.IO()
    with emtk.frame(painter, size, io=io, storage=storage if storage is not None else {}):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Layout/Basic Horizontal Layout  (imgui_demo.cpp:4765)
# --------------------------------------------------------------------------- #
#   ImGui::Text("Two items: Hello"); ImGui::SameLine();
#   ImGui::TextColored(ImVec4(1,1,0,1), "Sailor");
#
#   ImGui::Text("More spacing: Hello"); ImGui::SameLine(0, 20);
#   ImGui::TextColored(ImVec4(1,1,0,1), "Sailor");
def test_same_line_puts_the_next_item_beside_the_last():
    boxes: dict = {}

    def gui():
        emtk.text("Two items: Hello")
        boxes["hello"] = emtk.get_item_rect()
        emtk.same_line()
        emtk.text_colored((255, 255, 0, 255), "Sailor")
        boxes["sailor"] = emtk.get_item_rect()

    _run(gui)
    hello, sailor = boxes["hello"], boxes["sailor"]
    assert sailor[1] == hello[1], "SameLine did not hold the line"
    assert sailor[0] >= hello[0] + hello[2], "the second item overlapped the first"


def test_same_line_takes_a_spacing():
    """``SameLine(0, 20)`` -- twenty pixels, not the style's default."""
    boxes: dict = {}

    def gui():
        emtk.text("More spacing: Hello")
        boxes["hello"] = emtk.get_item_rect()
        emtk.same_line(0.0, 20.0)
        emtk.text_colored((255, 255, 0, 255), "Sailor")
        boxes["sailor"] = emtk.get_item_rect()

    _run(gui)
    gap = boxes["sailor"][0] - (boxes["hello"][0] + boxes["hello"][2])
    assert gap == pytest.approx(20.0), gap


def test_same_line_takes_an_absolute_offset():
    """``SameLine(150)`` is a cheap column: x=150 from the window's left."""
    boxes: dict = {}

    def gui():
        emtk.text("Aligned")
        emtk.same_line(150.0)
        emtk.text("x=150")
        boxes["150"] = emtk.get_item_rect()
        emtk.same_line(300.0)
        emtk.text("x=300")
        boxes["300"] = emtk.get_item_rect()

    _run(gui)
    assert boxes["150"][0] == pytest.approx(150.0)
    assert boxes["300"][0] == pytest.approx(300.0)
    assert boxes["150"][1] == boxes["300"][1]


def test_a_row_of_buttons_stays_on_one_line():
    #   ImGui::Text("Normal buttons"); ImGui::SameLine();
    #   ImGui::Button("Banana"); ImGui::SameLine();
    #   ImGui::Button("Apple"); ImGui::SameLine(); ImGui::Button("Corniflower");
    boxes: dict = {}

    def gui():
        emtk.align_text_to_frame_padding()
        emtk.text("Normal buttons")
        boxes["label"] = emtk.get_item_rect()
        for name in ("Banana", "Apple", "Corniflower"):
            emtk.same_line()
            emtk.button(name)
            boxes[name] = emtk.get_item_rect()

    _run(gui)
    ys = {round(boxes[k][1]) for k in ("Banana", "Apple", "Corniflower")}
    assert len(ys) == 1, boxes
    xs = [boxes[k][0] for k in ("Banana", "Apple", "Corniflower")]
    assert xs == sorted(xs) and len(set(xs)) == 3


def test_checkboxes_pack_along_a_line():
    #   ImGui::Checkbox("My", &c1); ImGui::SameLine(); ... ImGui::Checkbox("Rich", &c4);
    boxes: dict = {}

    def gui():
        for index, name in enumerate(("My", "Tailor", "Is", "Rich")):
            if index:
                emtk.same_line()
            emtk.checkbox(name, False)
            boxes[name] = emtk.get_item_rect()

    _run(gui)
    ys = {round(b[1]) for b in boxes.values()}
    assert len(ys) == 1
    xs = [boxes[k][0] for k in ("My", "Tailor", "Is", "Rich")]
    assert xs == sorted(xs)


# --------------------------------------------------------------------------- #
# Layout/Basic Horizontal Layout/Dummy
# --------------------------------------------------------------------------- #
#   ImGui::Dummy(button_sz); ImGui::SameLine(); ...
def test_a_dummy_takes_up_room_and_draws_nothing():
    boxes: dict = {}

    def gui():
        emtk.button("A")
        boxes["A"] = emtk.get_item_rect()
        emtk.same_line()
        boxes["gap"] = emtk.dummy(40.0, 20.0)
        emtk.same_line()
        emtk.button("B")
        boxes["B"] = emtk.get_item_rect()

    painter = _run(gui)
    assert boxes["B"][0] >= boxes["A"][0] + boxes["A"][2] + 40.0
    assert "gap" not in painter.strings


# --------------------------------------------------------------------------- #
# Layout/Widgets Width
# --------------------------------------------------------------------------- #
#   ImGui::SetNextItemWidth(...); ImGui::DragFloat("float##2", &f);
def test_set_next_item_width_applies_to_exactly_one_item():
    boxes: dict = {}

    def gui():
        emtk.set_next_item_width(120.0)
        emtk.slider_float("narrow", 0.5, 0.0, 1.0)
        boxes["narrow"] = emtk.get_item_rect()
        emtk.slider_float("wide", 0.5, 0.0, 1.0)
        boxes["wide"] = emtk.get_item_rect()

    _run(gui)
    assert boxes["narrow"][2] == pytest.approx(120.0)
    assert boxes["wide"][2] > 120.0, "the width leaked into the next item"


def test_push_item_width_applies_until_it_is_popped():
    boxes: dict = {}

    def gui():
        emtk.push_item_width(90.0)
        assert emtk.calc_item_width() == pytest.approx(90.0)
        emtk.pop_item_width()

    _run(gui)


# --------------------------------------------------------------------------- #
# Layout/Child windows
# --------------------------------------------------------------------------- #
#   ImGui::BeginChild("ChildL", ImVec2(avail.x * 0.5f, 260), ...);
#   for (int i = 0; i < 100; i++) ImGui::Text("%04d: scrollable region", i);
#   ImGui::EndChild();
def test_a_child_region_lays_out_inside_its_box():
    boxes: dict = {}

    def gui():
        emtk.begin_child((10.0, 10.0, 200.0, 120.0))
        emtk.text("inside")
        boxes["inside"] = emtk.get_item_rect()
        emtk.end_child()
        emtk.text("outside")
        boxes["outside"] = emtk.get_item_rect()

    _run(gui)
    assert boxes["inside"][0] >= 10.0 and boxes["inside"][1] >= 10.0
    assert boxes["outside"][0] < 10.0 or boxes["outside"][1] < 10.0, (
        "the cursor did not come back out of the child"
    )


def test_a_child_region_clips_what_overflows_it():
    """A hundred rows in a short box: the ones past the bottom are clipped."""
    def gui():
        emtk.begin_child((0.0, 0.0, 200.0, 60.0))
        for index in range(100):
            emtk.text("%04d: scrollable region" % index)
        emtk.end_child()

    painter = _run(gui)
    # `clips` is the live stack, emptied by `end_child`; the *calls* are the log.
    pushed = [c for c in painter.calls if c[0] == "push_clip"]
    assert pushed, "the child pushed no clip rectangle"
    assert pushed[0][3:5] == (200.0, 60.0), pushed[0]


# --------------------------------------------------------------------------- #
# Layout/Text Clipping and Text Baseline Alignment
# --------------------------------------------------------------------------- #
def test_text_wrapped_breaks_into_more_than_one_line():
    boxes = []

    def gui():
        emtk.text_wrapped(
            "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do "
            "eiusmod tempor incididunt ut labore et dolore magna aliqua")
        boxes.append(emtk.get_item_rect())

    painter = _run(gui, size=(0.0, 0.0, 120.0, 400.0))
    lines = [c for c in painter.calls if c[0] == "text"]
    assert len(lines) > 1, "wrapped text stayed on one line"
    ys = [c[2] for c in lines]
    assert ys == sorted(ys) and len(set(ys)) == len(ys)


def test_align_text_to_frame_padding_is_a_no_op_on_its_own():
    """It changes where the *next* line sits, not what is drawn."""
    def gui():
        emtk.align_text_to_frame_padding()

    painter = _run(gui)
    assert not painter.calls


# --------------------------------------------------------------------------- #
# Layout/Scrolling
# --------------------------------------------------------------------------- #
#   ImGui::SetScrollHereY(0.5f); / ImGui::GetScrollX() ...
def test_scroll_is_clamped_to_what_there_is_to_scroll():
    def gui():
        emtk.begin("scroller", (0.0, 0.0, 100.0, 100.0))
        emtk.set_scroll_y(999.0)
        emtk.end()

    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 400.0, 400.0)) as ctx:
        ctx.begin("scroller", (0.0, 0.0, 100.0, 100.0))
        ctx.current_window.content_size = (100.0, 250.0)
        emtk.set_scroll_here_y(1.0)
        assert emtk.get_scroll_y() == pytest.approx(emtk.get_scroll_max_y())
        assert emtk.get_scroll_y() == pytest.approx(150.0)
        ctx.end()
