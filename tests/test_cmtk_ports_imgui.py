"""A Dear ImGui program ports to cmtk line for line.

The requirement, plainly: someone with ImGui code should be able to bring it
here by transliterating it, not by redesigning it. So this file takes the
canonical Dear ImGui program -- the "Hello, world!" block from
``examples/example_glfw_opengl3/main.cpp:161-176``, quoted verbatim below --
and runs the Python transliteration of it against a recording painter.

    ImGui::Begin("Hello, world!");
    ImGui::Text("This is some useful text.");
    ImGui::Checkbox("Demo Window", &show_demo_window);
    ImGui::Checkbox("Another Window", &show_another_window);
    ImGui::SliderFloat("float", &f, 0.0f, 1.0f);
    if (ImGui::Button("Button"))
        counter++;
    ImGui::SameLine();
    ImGui::Text("counter = %d", counter);
    ImGui::End();

Line for line, that is::

    cmtk.begin("Hello, world!")
    cmtk.text("This is some useful text.")
    _, show_demo_window = cmtk.checkbox("Demo Window", show_demo_window)
    _, show_another_window = cmtk.checkbox("Another Window", show_another_window)
    _, f = cmtk.slider_float("float", f, 0.0, 1.0)
    if cmtk.button("Button"):
        counter += 1
    cmtk.same_line()
    cmtk.text("counter = %d" % counter)
    cmtk.end()

The only difference is the one Python forces: C++ writes results through
``bool*`` and ``float*``, so the value comes back instead -- which is what
pyimgui and imgui-bundle do, and therefore what a Python ImGui user already
writes.

What the tests below check is not that it *renders* prettily but that the
semantics are ImGui's: a button reports the click on release, a checkbox
toggles the value it was handed, the pointer rules come from ``ItemAdd``, and
overlapping items resolve the way ``ItemHoverable`` says they do.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk.testing import RecordingPainter


def _hello_world(state: dict) -> RecordingPainter:
    """The transliteration above, run once against a fresh painter."""
    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=state["io"],
                  storage=state["storage"]):
        cmtk.begin("Hello, world!")
        cmtk.text("This is some useful text.")
        _, state["show_demo_window"] = cmtk.checkbox(
            "Demo Window", state["show_demo_window"])
        _, state["show_another_window"] = cmtk.checkbox(
            "Another Window", state["show_another_window"])
        _, state["f"] = cmtk.slider_float("float", state["f"], 0.0, 1.0)
        if cmtk.button("Button"):
            state["counter"] += 1
        cmtk.same_line()
        cmtk.text("counter = %d" % state["counter"])
        cmtk.end()
    return painter


@pytest.fixture
def state():
    return {
        "io": cmtk.IO(),
        "storage": {},
        "show_demo_window": True,
        "show_another_window": False,
        "f": 0.0,
        "counter": 0,
    }


def _at(io, x, y):
    io.mouse_pos = (x, y)


def _click(io, x, y):
    """A press and a release at the same place, as a mouse does it."""
    io.mouse_pos = (x, y)
    io.mouse_down[0] = True
    io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = (x, y)


def _release(io):
    io.mouse_down[0] = False
    io.mouse_released[0] = True


# --------------------------------------------------------------------------- #
# It runs, and it draws
# --------------------------------------------------------------------------- #
def test_the_canonical_imgui_program_runs(state):
    painter = _hello_world(state)
    assert painter.strings, "nothing was drawn"
    assert "This is some useful text." in painter.strings
    assert "Button" in painter.strings
    assert "counter = 0" in painter.strings


def test_the_cursor_advances_and_same_line_holds_it(state):
    """`ItemSize` moves down a row; `SameLine` puts the next item beside.

    Read off the item rectangles rather than the glyph positions: a button
    centres its label in its box, so where the *text* landed is not where the
    *item* is.
    """
    painter = RecordingPainter()
    boxes = []
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=state["io"],
                  storage=state["storage"]) as ctx:
        cmtk.begin("Hello, world!")
        cmtk.text("This is some useful text.")
        boxes.append(("text", ctx.get_item_rect()))
        cmtk.checkbox("Demo Window", True)
        boxes.append(("checkbox", ctx.get_item_rect()))
        cmtk.slider_float("float", 0.0, 0.0, 1.0)
        boxes.append(("slider", ctx.get_item_rect()))
        cmtk.button("Button")
        boxes.append(("button", ctx.get_item_rect()))
        cmtk.same_line()
        cmtk.text("counter = 0")
        boxes.append(("counter", ctx.get_item_rect()))
        cmtk.end()

    named = dict(boxes)
    ys = [named[k][1] for k in ("text", "checkbox", "slider", "button")]
    assert ys == sorted(ys) and len(set(ys)) == 4, boxes
    # `same_line()` holds the line, so the counter sits beside the button...
    assert named["counter"][1] == named["button"][1], boxes
    # ...and to its right.
    assert named["counter"][0] > named["button"][0], boxes


# --------------------------------------------------------------------------- #
# ...with ImGui's semantics, not merely its spelling
# --------------------------------------------------------------------------- #
def test_a_button_reports_the_click_on_release(state):
    """`ButtonBehavior` with the default flags: pressed on the up edge.

    The down edge makes it *active*, which is what lets a press that wanders
    off the button be cancelled by releasing elsewhere.
    """
    _hello_world(state)                      # a first frame, to place the items
    box = _find(state, "Button")
    io = state["io"]

    _click(io, box[0] + 2, box[1] + 2)
    _hello_world(state)
    assert state["counter"] == 0, "fired on the down edge"

    _release(io)
    _hello_world(state)
    assert state["counter"] == 1


def test_a_press_that_leaves_the_button_does_not_fire(state):
    _hello_world(state)
    box = _find(state, "Button")
    io = state["io"]
    _click(io, box[0] + 2, box[1] + 2)
    _hello_world(state)
    _at(io, box[0] + 2, box[1] + 400)        # dragged away
    _release(io)
    _hello_world(state)
    assert state["counter"] == 0


def test_a_checkbox_toggles_the_value_it_was_given(state):
    _hello_world(state)
    box = _find(state, "Demo Window")
    io = state["io"]
    assert state["show_demo_window"] is True
    _click(io, box[0] + 2, box[1] + 2)
    _hello_world(state)
    _release(io)
    _hello_world(state)
    assert state["show_demo_window"] is False


def test_a_slider_reports_where_it_was_grabbed(state):
    _hello_world(state)
    box = _find(state, "float")
    io = state["io"]
    _click(io, box[0] + box[2] * 0.5, box[1] + 2)
    _hello_world(state)
    assert 0.2 < state["f"] < 0.8, state["f"]


def test_the_item_under_the_pointer_is_the_one_that_was_drawn_there(state):
    """`ItemAdd` registers the box being drawn, so hovering needs no second list."""
    _hello_world(state)
    button = _find(state, "Button")
    io = state["io"]
    _at(io, button[0] + 2, button[1] + 2)

    painter = RecordingPainter()
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=io,
                  storage=state["storage"]) as ctx:
        cmtk.begin("Hello, world!")
        cmtk.text("This is some useful text.")
        cmtk.checkbox("Demo Window", state["show_demo_window"])
        cmtk.checkbox("Another Window", state["show_another_window"])
        cmtk.slider_float("float", state["f"], 0.0, 1.0)
        cmtk.button("Button")
        hovered_the_button = cmtk.is_item_hovered()
        cmtk.end()
        assert ctx.hovered_id == ctx.get_id("Button"), ctx.hovered_id
    assert hovered_the_button


def test_only_one_item_claims_the_pointer(state):
    """ImGui's rule: the first to claim it keeps it unless overlap is allowed.

    > if (g.HoveredId != 0 && g.HoveredId != id && !g.HoveredIdAllowOverlap)
    >     return false;
    """
    painter = RecordingPainter()
    io = cmtk.IO()
    io.mouse_pos = (10.0, 10.0)
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0), io=io) as ctx:
        first = ctx.item_add((0.0, 0.0, 100.0, 100.0), "first")
        second = ctx.item_add((0.0, 0.0, 100.0, 100.0), "second")
    assert first is True
    assert second is False, "two items both claimed the same pointer"


def test_an_item_may_opt_into_overlapping(state):
    painter = RecordingPainter()
    io = cmtk.IO()
    io.mouse_pos = (10.0, 10.0)
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0), io=io) as ctx:
        ctx.item_add((0.0, 0.0, 100.0, 100.0), "first")
        ctx.set_next_item_allow_overlap()
        second = ctx.item_add((0.0, 0.0, 100.0, 100.0), "second")
    assert second is True


def test_a_window_that_takes_no_input_is_still_drawn(state):
    """`ImGuiWindowFlags_NoMouseInputs`: a flag on the entry, not a second list."""
    painter = RecordingPainter()
    io = cmtk.IO()
    io.mouse_pos = (10.0, 10.0)
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 100.0), io=io) as ctx:
        ctx.begin("ghost", (0.0, 0.0, 100.0, 100.0), no_mouse_inputs=True)
        cmtk.text("drawn all the same")
        ctx.end()
        assert ctx.find_hovered_window(10.0, 10.0) is None
    assert "drawn all the same" in painter.strings


def test_the_window_list_is_walked_backwards_to_find_the_hovered_one(state):
    """One list, both directions -- `FindHoveredWindowEx` in the reference."""
    painter = RecordingPainter()
    io = cmtk.IO()
    with cmtk.frame(painter, (0.0, 0.0, 200.0, 200.0), io=io) as ctx:
        ctx.begin("under", (0.0, 0.0, 100.0, 100.0))
        ctx.end()
        ctx.begin("over", (0.0, 0.0, 100.0, 100.0))
        ctx.end()
        assert [w.name for w in ctx.windows] == ["under", "over"]
        assert ctx.find_hovered_window(10.0, 10.0).name == "over"
        ctx.set_window_focus("under")
        assert ctx.find_hovered_window(10.0, 10.0).name == "under"


# --------------------------------------------------------------------------- #
def _find(state, label: str):
    """The box a labelled widget last occupied."""
    boxes = state["storage"].setdefault("__boxes__", {})
    if label in boxes:
        return boxes[label]
    painter = RecordingPainter()
    io = state["io"]
    seen = {}
    with cmtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=io,
                  storage=state["storage"]) as ctx:
        cmtk.begin("Hello, world!")
        cmtk.text("This is some useful text.")
        for name, value in (("Demo Window", state["show_demo_window"]),
                            ("Another Window", state["show_another_window"])):
            cmtk.checkbox(name, value)
            seen[name] = ctx.get_item_rect()
        cmtk.slider_float("float", state["f"], 0.0, 1.0)
        seen["float"] = ctx.get_item_rect()
        cmtk.button("Button")
        seen["Button"] = ctx.get_item_rect()
        cmtk.end()
    boxes.update(seen)
    return boxes[label]
