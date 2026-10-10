"""An item that is disabled while the pointer holds it lets go, so the next click reaches another item.

A change made by a held slider can start a worker that greys the whole pane at once. The disabled
slider never sees the release, and while it stayed the active item every other item refused the next click.
"""
import emtk
from emtk import im
from emtk.testing import RecordingPainter


def test_a_slider_disabled_mid_hold_does_not_block_the_next_click():
    state = {"disabled": False, "a": 0.0, "b": 0.0}
    rects: dict = {}
    io, storage = emtk.IO(), {}

    def frame():
        with emtk.frame(RecordingPainter(), (0, 0, 400, 300), io=io, storage=storage):
            im.begin_disabled(state["disabled"])
            _, state["a"] = emtk.slider_float("a", state["a"], 0.0, 1.0)
            rects["a"] = emtk.get_item_rect()
            _, state["b"] = emtk.slider_float("b", state["b"], 0.0, 1.0)
            rects["b"] = emtk.get_item_rect()
            im.end_disabled()
        io.mouse_clicked[0] = False
        io.mouse_released[0] = False

    frame()
    ax, ay, aw, ah = rects["a"]
    io.mouse_pos = (ax + aw * 0.25, ay + ah / 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    frame()
    assert 0.0 < state["a"] < 0.5
    state["disabled"] = True  # the change started a job
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    frame()
    state["disabled"] = False
    frame()
    bx, by, bw, bh = rects["b"]
    io.mouse_pos = (bx + bw * 0.75, by + bh / 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    frame()
    assert state["b"] > 0.5
