"""The plot's "A" button: hidden while auto-ranged, back to the data on a click.

Driven as a user drives a plot -- wheel, drag, click -- through ``emtk.IO``
between frames, then read back from what was painted and the axis limits.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import implot
from emtk.i18n import set_language
from emtk.testing import RecordingPainter
from emtk.widgets import auto_range


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []


class Driver:
    """One window holding one plot, frames on demand."""

    def __init__(self, gui, size=(600, 420)):
        self.gui = gui
        self.size = size
        self.io = emtk.IO()
        self.io.wall_clock = False
        self.storage: dict = {}
        self.out: dict = {}
        self.painter = None

    def frame(self):
        p = RecordingPainter()
        with emtk.frame(p, (0, 0, *self.size), io=self.io, storage=self.storage):
            emtk.begin("w")
            self.gui(self.out)
            emtk.end()
        for k in range(3):
            self.io.mouse_clicked[k] = False
            self.io.mouse_released[k] = False
            self.io.mouse_double_clicked[k] = False
        self.io.mouse_wheel = 0.0
        self.painter = p
        return p

    def move(self, x, y):
        self.io.mouse_pos = (float(x), float(y))
        return self.frame()

    def press(self, x, y):
        self.move(x, y)
        self.io.mouse_down[0] = True
        self.io.mouse_clicked[0] = True
        self.io.mouse_clicked_pos[0] = self.io.mouse_pos
        return self.frame()

    def release(self, x, y):
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        return self.frame()

    def click(self, x, y):
        self.press(x, y)
        return self.release(x, y)

    def wheel(self, x, y, amount):
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_wheel = float(amount)
        return self.frame()


def _data_plot(data, flags=0):
    def gui(out):
        if implot.begin_plot("##a", (-1, -1), flags | implot.FLAGS_NO_LEGEND):
            xs, ys = data["x"], data["y"]
            implot.plot_line("line", xs, ys)
            out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
            implot.end_plot()
            out["limits"] = implot.get_plot_limits()

    return gui


def _a_boxes(p):
    return [t for t in p.texts if t[5] == "A"]


def _button(out):
    x, y, w, h = out["rect"]
    return auto_range.button_rect(x, y, w, h)


def _centre(out):
    x, y, w, h = out["rect"]
    return x + w / 2, y + h / 2


def _limits(out):
    lim = out["limits"]
    return (lim.x_min, lim.x_max, lim.y_min, lim.y_max)


def test_hidden_while_the_view_follows_its_data():
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}))
    p = d.move(-10, -10)
    assert _a_boxes(p) == []


def test_a_wheel_zoom_shows_it_inside_the_plot_area_and_a_click_refits():
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}))
    d.move(-10, -10)
    fitted = _limits(d.out)
    cx, cy = _centre(d.out)
    p = d.wheel(cx, cy, 1.0)
    p = d.move(cx, cy)
    assert _limits(d.out) != pytest.approx(fitted)
    boxes = _a_boxes(p)
    assert len(boxes) == 1
    x, y, w, h = d.out["rect"]
    bx, by, bw, bh = boxes[0][:4]
    assert x <= bx and bx + bw <= x + w and y <= by and by + bh <= y + h, "A outside the plot"
    assert bx - x < 10 and (y + h) - (by + bh) < 10, "A not in the lower-left corner"
    ax, ay, aw, ah = _button(d.out)
    d.click(ax + aw / 2, ay + ah / 2)
    p = d.move(-10, -10)
    assert _limits(d.out) == pytest.approx(fitted)
    assert _a_boxes(p) == []


def test_a_drag_pan_shows_it():
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}))
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.press(cx, cy)
    d.move(cx + 60, cy + 30)
    d.release(cx + 60, cy + 30)
    p = d.move(cx, cy)
    assert len(_a_boxes(p)) == 1


def test_a_click_on_the_button_does_not_start_a_pan():
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}))
    d.move(-10, -10)
    fitted = _limits(d.out)
    d.wheel(*_centre(d.out), 1.0)
    ax, ay, aw, ah = _button(d.out)
    d.press(ax + aw / 2, ay + ah / 2)
    d.move(ax + aw / 2 + 80, ay + ah / 2 - 40)   # still held: must not pan
    d.release(ax + aw / 2 + 80, ay + ah / 2 - 40)
    d.move(-10, -10)
    assert _limits(d.out) == pytest.approx(fitted)


def test_new_data_refits_only_while_auto_ranged():
    data = {"x": [2, 4], "y": [20, 40]}
    d = Driver(_data_plot(data))
    d.move(-10, -10)
    data["x"], data["y"] = [0, 100], [0, 1000]
    d.move(-10, -10)
    assert d.out["limits"].x_max >= 100, "an auto-ranged plot did not follow new data"
    d.wheel(*_centre(d.out), 1.0)
    zoomed = _limits(d.out)
    data["x"], data["y"] = [0, 500], [0, 9000]
    d.move(-10, -10)
    assert _limits(d.out) == pytest.approx(zoomed), "a zoomed plot jumped to new data"
    ax, ay, aw, ah = _button(d.out)
    d.click(ax + aw / 2, ay + ah / 2)
    d.move(-10, -10)
    assert d.out["limits"].x_max >= 500


def test_the_opt_out_flag_and_no_inputs_hide_it():
    for flags in (implot.FLAGS_NO_AUTO_RANGE_BUTTON, implot.FLAGS_NO_INPUTS):
        def gui(out, flags=flags):
            if implot.begin_plot("##o", (-1, -1), flags | implot.FLAGS_NO_LEGEND):
                implot.setup_axes_limits(0, 10, 0, 10)
                implot.plot_line("line", [0, 10], [0, 10])
                out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
                implot.end_plot()

        d = Driver(gui)
        d.move(-10, -10)
        p = d.wheel(*_centre(d.out), 1.0)
        assert _a_boxes(p) == []
    assert implot.ImPlotFlags_NoAutoRangeButton == implot.FLAGS_NO_AUTO_RANGE_BUTTON


def test_hovering_it_shows_the_translated_tooltip():
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}))
    d.move(-10, -10)
    d.wheel(*_centre(d.out), 1.0)
    ax, ay, aw, ah = _button(d.out)
    d.move(ax + aw / 2, ay + ah / 2)
    d.io.now += 2.0
    p = d.move(ax + aw / 2, ay + ah / 2)
    assert auto_range.TOOLTIP in " ".join(p.strings)
    set_language("de")
    try:
        assert auto_range.tooltip() != auto_range.TOOLTIP
    finally:
        set_language("en")


@pytest.mark.parametrize("size", [(800, 600), (400, 260)])
def test_it_stays_inside_small_and_large_plot_areas(size):
    d = Driver(_data_plot({"x": [2, 4], "y": [20, 40]}), size=size)
    d.move(-10, -10)
    p = d.wheel(*_centre(d.out), 1.0)
    x, y, w, h = d.out["rect"]
    bx, by, bw, bh = _button(d.out)
    assert x <= bx and bx + bw <= x + w and y <= by and by + bh <= y + h
    assert len(_a_boxes(p)) == 1


def test_button_rect_never_leaves_a_tiny_plot_area():
    bx, by, bw, bh = auto_range.button_rect(0, 0, 12, 12)
    assert bw >= 8 and bx >= 0 and by >= -1e-9
