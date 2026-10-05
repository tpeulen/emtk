"""PaneStack: panes divided by weight, bars that move weight, input routed to panes."""

from __future__ import annotations

from emtk.flags import Axis
from emtk.testing import RecordingPainter
from emtk.widgets.pane_stack import PaneStack


class Pane:
    def __init__(self):
        self.box = None
        self.calls = []

    def draw(self, p, x, y, w, h):
        self.box = (x, y, w, h)

    def press(self, px, py, x, y, w, h, modifiers=0, clicks=1):
        self.calls.append(("press", px, py, (x, y, w, h)))

    def drag(self, px, py, *box):
        self.calls.append(("drag", px, py))

    def release(self):
        self.calls.append(("release",))

    def hover(self, px, py, *box):
        self.calls.append(("hover", px, py))

    def scroll(self, rows):
        self.calls.append(("scroll", rows))

    def key(self, key, text="", modifiers=0):
        self.calls.append(("key", key))
        return True

    def focus_lost(self):
        self.calls.append(("focus_lost",))


def _stack(n=3, weights=None, **kw):
    panes = [Pane() for _ in range(n)]
    stack = PaneStack(panes, weights, **kw)
    stack.draw(RecordingPainter(), 0, 0, 400, 605)
    return stack, panes


def test_the_boxes_tile_the_region_by_weight():
    stack, panes = _stack(3, [1, 1, 2], thickness=5.0)
    heights = [p.box[3] for p in panes]
    assert abs(sum(heights) + 10.0 - 605.0) < 1e-6
    assert abs(heights[2] - 2 * heights[0]) < 1e-6
    assert panes[1].box[1] == panes[0].box[1] + panes[0].box[3] + 5.0


def test_the_proportion_survives_a_resize():
    stack, panes = _stack(2, [1, 3])
    stack.draw(RecordingPainter(), 0, 0, 400, 1205)
    assert abs(panes[1].box[3] / panes[0].box[3] - 3.0) < 1e-6


def test_side_by_side():
    stack, panes = _stack(2, axis=Axis.X)
    assert panes[0].box[1] == panes[1].box[1] == 0
    assert panes[1].box[0] > panes[0].box[0] + panes[0].box[2]


def test_dragging_a_bar_moves_weight_between_its_two_panes_only():
    stack, panes = _stack(3, [1, 1, 1], thickness=5.0)
    third = stack.weights[2]
    bx, by, bw, bh = stack._bar_boxes[0]
    assert stack.press(bx + 10, by + 2, 0, 0, 400, 605) is stack
    stack.drag(bx + 10, by + 52)
    stack.release()
    stack.draw(RecordingPainter(), 0, 0, 400, 605)
    assert panes[0].box[3] > 200 + 40
    assert abs(stack.weights[2] - third) < 1e-9
    assert stack.user_sized
    assert not any(c[0] == "press" for p in panes for c in p.calls)


def test_a_collapsible_pane_goes_to_zero_and_its_bar_stays():
    stack, panes = _stack(2, thickness=5.0)
    bx, by, *_ = stack._bar_boxes[0]
    stack.press(bx + 1, by + 2, 0, 0, 400, 605)
    stack.drag(bx + 1, -100)
    stack.release()
    stack.draw(RecordingPainter(), 0, 0, 400, 605)
    assert stack._pane_boxes[0][3] == 0.0
    assert stack._bar_boxes[0][1] == 0.0


def test_a_non_collapsible_pane_keeps_its_minimum():
    stack, panes = _stack(2, thickness=5.0, collapsible=False, min_size=30.0)
    bx, by, *_ = stack._bar_boxes[0]
    stack.press(bx + 1, by + 2, 0, 0, 400, 605)
    stack.drag(bx + 1, -100)
    stack.release()
    stack.draw(RecordingPainter(), 0, 0, 400, 605)
    assert abs(panes[0].box[3] - 30.0) < 1e-6


def test_a_press_goes_to_the_pane_under_it_with_that_panes_box():
    stack, panes = _stack(3)
    x, y, w, h = panes[2].box
    stack.press(x + 5, y + 5, 0, 0, 400, 605)
    assert panes[2].calls[-1] == ("press", x + 5, y + 5, (x, y, w, h))
    # captured: the drag follows even when the pointer leaves the pane
    stack.drag(x + 5, 1.0)
    stack.release()
    assert ("drag", x + 5, 1.0) in panes[2].calls
    assert panes[2].calls[-1] == ("release",)
    assert not panes[0].calls


def test_hover_wheel_and_keys_reach_the_right_pane():
    stack, panes = _stack(2)
    x0, y0, *_ = panes[0].box
    x1, y1, *_ = panes[1].box
    stack.hover(x1 + 3, y1 + 3)
    stack.scroll(3)
    assert ("scroll", 3) in panes[1].calls
    stack.press(x0 + 3, y0 + 3, 0, 0, 400, 605)
    stack.release()
    assert stack.key(65, "a") is True
    assert ("key", 65) in panes[0].calls
    stack.press(x1 + 3, y1 + 3, 0, 0, 400, 605)
    assert ("focus_lost",) in panes[0].calls


def test_a_bar_lights_when_hovered():
    stack, _ = _stack(2)
    bx, by, *_ = stack._bar_boxes[0]
    stack.hover(bx + 5, by + 2)
    assert stack.hovered_bar == 0


def test_a_panes_tooltip_is_the_stacks():
    class Tipped(Pane):
        def tooltip_at(self, px, py):
            return "bottom pane"

    panes = [Pane(), Tipped()]
    stack = PaneStack(panes)
    stack.draw(RecordingPainter(), 0, 0, 400, 605)
    x, y, *_ = panes[1].box
    assert stack.tooltip_at(x + 3, y + 3) == "bottom pane"
    x, y, *_ = panes[0].box
    assert stack.tooltip_at(x + 3, y + 3) == ""
