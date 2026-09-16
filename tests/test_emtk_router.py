"""emtk's Router: one capture slot, the release always reaches the presser, wheels never fall through a window."""
from __future__ import annotations

from emtk.router import Capture, Consumed, Event, OverlayStack, Pass, Router


class _Layer:
    def __init__(self, box, name, capture_on_press=False):
        self.box = box
        self.name = name
        self.capture_on_press = capture_on_press
        self.seen: list[str] = []
        self.visible = True

    def bounds(self):
        return self.box

    def event(self, ev: Event):
        self.seen.append(ev.kind)
        if ev.kind == "press" and self.capture_on_press:
            return Capture(self)
        if ev.kind == "wheel":
            return Pass                     # even a Pass on a wheel must not reach the camera
        return Consumed


def _setup():
    stack = OverlayStack()
    a = _Layer((0, 0, 100, 100), "a", capture_on_press=True)
    b = _Layer((50, 50, 100, 100), "b")
    stack.add(a)
    stack.add(b)                            # b on top of a where they overlap
    fell: list[str] = []
    router = Router(stack, fallthrough=lambda ev: fell.append(ev.kind) or Consumed)
    return stack, a, b, router, fell


def test_top_layer_wins_and_press_raises_it():
    stack, a, b, router, fell = _setup()
    router.dispatch(Event("press", 75, 75, button=1))
    assert b.seen == ["press"] and a.seen == []
    stack.add(a)                            # a to the top now
    router.dispatch(Event("press", 75, 75, button=1))
    assert a.seen == ["press"]
    assert stack.layers()[-1] is a


def test_the_release_reaches_the_capturer_wherever_it_lands():
    stack, a, b, router, fell = _setup()
    router.dispatch(Event("press", 10, 10, button=1))    # a captures
    assert router.capturer is a
    router.dispatch(Event("move", 500, 500))             # far outside: still a's
    router.dispatch(Event("release", 500, 500, button=1))
    assert a.seen == ["press", "move", "release"]
    assert router.capturer is None
    assert fell == []


def test_a_foreign_press_cancels_the_capture():
    stack, a, b, router, fell = _setup()
    router.dispatch(Event("press", 10, 10, button=1))    # a captures
    router.dispatch(Event("press", 120, 120, button=1))  # on b, not a
    assert a.seen == ["press", "cancel"]
    assert b.seen == ["press"]
    assert router.capturer is None


def test_enter_and_leave_are_computed_from_moves():
    stack, a, b, router, fell = _setup()
    router.dispatch(Event("move", 10, 10))
    router.dispatch(Event("move", 20, 20))
    router.dispatch(Event("move", 120, 120))
    router.dispatch(Event("move", 300, 300))
    assert a.seen == ["enter", "move", "move", "leave"]
    assert b.seen == ["enter", "move", "leave"]
    assert fell == ["move"]


def test_a_wheel_over_a_layer_never_reaches_the_camera():
    stack, a, b, router, fell = _setup()
    assert router.dispatch(Event("wheel", 10, 10, wheel_dy=1)) is Consumed
    assert a.seen == ["wheel"] and fell == []
    router.dispatch(Event("wheel", 300, 300, wheel_dy=1))
    assert fell == ["wheel"]


def test_keys_go_to_the_capturer_then_the_focus_then_the_camera():
    stack, a, b, router, fell = _setup()
    router.dispatch(Event("key_press", key=65))
    assert fell == ["key_press"]
    router.dispatch(Event("press", 120, 120, button=1))  # focus b
    router.dispatch(Event("release", 120, 120, button=1))
    router.dispatch(Event("key_press", key=65))
    assert b.seen[-1] == "key_press"


def test_invisible_layers_are_skipped():
    stack, a, b, router, fell = _setup()
    b.visible = False
    router.dispatch(Event("press", 75, 75, button=1))
    assert a.seen == ["press"] and b.seen == []
