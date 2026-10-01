"""An item scrolled out of a child region is not hit-tested where it would be.

A scrolling ``begin_child`` keeps the boxes of the rows it clips. Hover only checked that the box
overlapped the clip rectangle, so a click on a button *below* the child toggled a hidden checkbox
whose box lay under the pointer (found when a settings panel's Apply button toggled "Grid on data
panel"). ImGui clips the rectangle by the clip rect before testing the pointer; so does this.
"""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter


def _click_below_the_child():
    state = {"presses": 0}

    def gui():
        im.begin("W", (0, 0, 300, 300))
        im.begin_child("c", (280, 60))
        for i in range(10):
            changed, value = im.checkbox(f"item{i}", state.get(i, False))
            state[i] = value if changed else state.get(i, False)
        im.end_child()
        if im.button("Below"):
            state["presses"] += 1
        state["rect"] = im.get_item_rect()
        im.end()

    app = ImApp(gui)
    for _ in range(3):
        app.draw(RecordingPainter(), 0, 0, 300, 300)
    x = state["rect"][0] + state["rect"][2] / 2
    y = state["rect"][1] + state["rect"][3] / 2
    app.hover(x, y)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    app.press(x, y)
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    app.release()
    app.draw(RecordingPainter(), 0, 0, 300, 300)
    return state


def test_a_click_below_a_scrolling_child_hits_the_button_not_a_hidden_row():
    state = _click_below_the_child()
    assert state["presses"] == 1
    assert not any(state.get(i) for i in range(10)), "a scrolled-out checkbox took the click"
