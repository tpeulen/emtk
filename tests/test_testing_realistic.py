"""emtk.testing_realistic: input delivered the way a person and a platform deliver it.

Each test pins one way the realistic drivers differ from :class:`emtk.testing.Driver` --
and therefore one class of bug that the synthetic driver cannot see.
"""
from __future__ import annotations

import sys

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.keys import KEY_BACKSPACE
from emtk.testing import MetricPainter
from emtk.testing_realistic import (HostedDriver, HostPainter, RealisticDriver, VirtualLoop,
                                    clipped_texts)


class _Panel(ImApp):
    """A full-viewport window: a spacer, a button at the bottom, a text field."""

    def __init__(self, label: str = "Ping") -> None:
        self.label = label
        self.pressed = 0
        self.text = "abcdefghijklmnopqrstuvwxyz"
        self.item_rects: dict = {}
        self.wheel_seen: list = []
        super().__init__(self.gui)

    def gui(self) -> None:
        size = im.get_main_viewport().size
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size(size, im.Cond.ALWAYS)
        if im.begin("panel", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            _changed, self.text = im.input_text("##field", self.text)
            self.item_rects["field"] = im.get_item_rect()
            # Anchored to the bottom: a resize moves the button.
            im.dummy((10.0, max(size[1] - 90.0, 1.0)))
            if im.button(self.label):
                self.pressed += 1
            self.item_rects["button"] = im.get_item_rect()
        im.end()

    def wheel(self, x, y, steps, modifiers=0):
        self.wheel_seen.append(steps)
        return super().wheel(x, y, steps, modifiers)


def test_virtual_loop_fires_callbacks_in_time_order():
    loop, fired = VirtualLoop(), []
    loop.call_later(0.2, fired.append, "b")
    loop.call_later(0.1, fired.append, "a")
    assert loop.advance(0.15) == 1 and fired == ["a"]
    loop.advance(1.0)
    assert fired == ["a", "b"]


def test_press_and_release_land_in_different_frames_and_still_click():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300), hold_frames=3, jitter=1.5)
    before = app.io.frame_count if hasattr(app.io, "frame_count") else None
    driver.click("button")
    assert app.pressed == 1
    if before is not None:
        # travel (4) + press (1) + hold (3) + release (1)
        assert app.io.frame_count - before >= 9


def test_a_click_after_a_resize_hits_the_moved_control():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300))
    driver.frame(2)
    first = driver.rect("button")
    driver.resize((640, 520))
    moved = driver.rect("button")
    assert moved[1] > first[1] + 100, "the button is anchored to the bottom"
    driver.click("button")
    assert app.pressed == 1
    # ... and the old position is now empty: a stale hit test would count it.
    driver.click((first[0] + first[2] / 2, first[1] + first[3] / 2))
    assert app.pressed == 1


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_content_scale_keeps_logical_hit_targets(scale):
    app = _Panel()
    driver = RealisticDriver(app, (400, 300), scale=scale)
    driver.frame(2)
    assert driver.surface.size == (round(400 * scale), round(300 * scale))
    assert driver.surface._box()[2:] == pytest.approx((400.0, 300.0), abs=1.0)
    driver.click("button")
    assert app.pressed == 1


def test_frames_are_measured_by_the_painter_that_draws():
    driver = RealisticDriver(_Panel(), (400, 300))
    driver.frame()
    assert isinstance(driver.painter, HostPainter)
    real = driver.painter._real
    assert driver.painter.text_width("Ping") == real.text_width("Ping")
    synthetic = RealisticDriver(_Panel(), (400, 300), real_painter=False)
    synthetic.frame()
    assert isinstance(synthetic.painter, MetricPainter)


def test_quick_second_click_is_a_double_click_and_slow_one_is_not():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300))
    seen = []
    original = app.pointer_press

    def press(x, y, button, modifiers=0, clicks=1):
        seen.append(clicks)
        return original(x, y, button, modifiers, clicks)

    app.pointer_press = press
    driver.double_click("button")
    assert seen[-2:] == [1, 2]
    driver.frame(30)                 # half a second: the next press starts over
    driver.click("button")
    assert seen[-1] == 1


def test_held_backspace_repeats_on_the_platform_clock():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300))
    driver.click("field")
    start = len(app.text)
    driver.hold_key(KEY_BACKSPACE, 1.0)
    # one press, then repeats after 0.40 s every 0.035 s: ~17 more in a second
    deleted = start - len(app.text)
    assert 10 <= deleted <= 20, deleted


def test_wheel_notches_arrive_one_per_frame():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300))
    driver.wheel(-3, at="button")
    assert app.wheel_seen == [-1, -1, -1]


def test_losing_focus_releases_a_held_key():
    app = _Panel()
    driver = RealisticDriver(app, (400, 300))
    driver.click("field")
    start = len(app.text)
    driver.key(KEY_BACKSPACE)
    driver.blur()
    driver.frame(60)                 # a second later: no repeat ran on
    assert start - len(app.text) == 1


def test_clipped_texts_reports_a_squeezed_label_not_a_fitting_one():
    driver = RealisticDriver(lambda: None, (200, 100))
    painter = driver._painter_for_frame()
    painter.push_clip(0, 0, 40, 20)
    painter.text(0, 0, 200, 20, 0, "A label far too long for its box", (0, 0, 0, 255))
    painter.text(0, 0, 40, 20, 0, "ok", (0, 0, 0, 255))
    painter.pop_clip()
    found = [row["text"] for row in clipped_texts(painter)]
    assert found == ["A label far too long for its box"]


# --------------------------------------------------------------------------- #
# real hosts
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not HostedDriver.available("offscreen"), reason="no GPU adapter")
@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_offscreen_host_clicks_and_resizes(scale):
    app = _Panel()
    driver = HostedDriver(app, (400, 300), backend="offscreen", scale=scale)
    try:
        driver.frame(2)
        assert driver.scale == scale
        driver.click("button")
        driver.resize((600, 480))
        driver.click("button")
        assert app.pressed == 2
        png = driver.screenshot()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        driver.close()


def _glfw_usable() -> bool:
    return sys.platform == "darwin" and HostedDriver.available("glfw")


@pytest.mark.skipif(not _glfw_usable(), reason="needs a macOS display session and glfw")
def test_hidden_glfw_window_click_after_a_window_manager_resize():
    app = _Panel()
    driver = HostedDriver(app, (400, 300), backend="glfw")
    try:
        driver.frame(2)
        # The display's own content scale and framebuffer, not a test's choice.
        width, height = driver.canvas.get_physical_size()
        assert (width, height) == (round(400 * driver.scale), round(300 * driver.scale))
        driver.click("button")
        driver.resize((640, 520))
        assert driver.size == (640, 520)
        driver.click("button")
        assert app.pressed == 2
    finally:
        driver.close()


@pytest.mark.skipif(not _glfw_usable(), reason="needs a macOS display session and glfw")
def test_hidden_glfw_window_press_after_the_window_moved_under_a_still_hand():
    """rendercanvas stamps a press with the last *move*; the live cursor must win."""
    app = _Panel()
    driver = HostedDriver(app, (400, 300), backend="glfw")
    try:
        driver.frame(2)
        x, y, w, h = driver.rect("button")
        # Hover 60 px right of the button, then the window slides right by 60 px.
        driver.hover((x + w / 2 + 60, y + h / 2))
        driver.move_window(60, 0)
        driver.press_here()
        assert app.pressed == 1
    finally:
        driver.close()
