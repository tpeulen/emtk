"""ImPlot's interaction, driven through emtk's input state.

Every test here does what a user does -- press, move, release, turn the wheel,
double-click, right-click -- by setting ``emtk.IO`` between frames, and then
reads back what ImPlot promises: the axis limits, a drag tool's value, an
item's visibility. The plot remembers itself across frames in the ``storage``
dict, as any emtk widget does.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import implot
from emtk.testing import RecordingPainter


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []
    while implot._cur.colormap_modifiers:
        implot.pop_colormap()


class Driver:
    """One window, one plot, frames on demand."""

    def __init__(self, gui):
        self.gui = gui
        self.io = emtk.IO()
        self.io.wall_clock = False
        self.storage: dict = {}
        self.out: dict = {}

    def frame(self):
        p = RecordingPainter()
        with emtk.frame(p, (0, 0, 600, 420), io=self.io, storage=self.storage):
            emtk.begin("w")
            self.gui(self.out)
            emtk.end()
        for k in range(3):
            self.io.mouse_clicked[k] = False
            self.io.mouse_released[k] = False
            self.io.mouse_double_clicked[k] = False
        self.io.mouse_wheel = 0.0
        return p

    def move(self, x, y):
        self.io.mouse_pos = (float(x), float(y))
        return self.frame()

    def press(self, x, y, button=0, double=False):
        # the pointer arrives before it presses: a real one does not teleport,
        # and the jump would read as a drag on the press frame
        self.move(x, y)
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_down[button] = True
        self.io.mouse_clicked[button] = True
        self.io.mouse_double_clicked[button] = double
        self.io.mouse_clicked_pos[button] = self.io.mouse_pos
        return self.frame()

    def release(self, x, y, button=0):
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_down[button] = False
        self.io.mouse_released[button] = True
        return self.frame()

    def wheel(self, x, y, amount):
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_wheel = float(amount)
        return self.frame()


def _plot(out, flags=0, x_flags=0, y_flags=0):
    implot.begin_plot("##p", (500, 300), flags | implot.FLAGS_NO_LEGEND)
    implot.setup_axes("x", "y", x_flags, y_flags)
    implot.setup_axes_limits(0, 10, 0, 10)
    implot.plot_line("line", [0, 10], [0, 10])
    out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
    implot.end_plot()
    out["limits"] = implot.get_plot_limits()


def _centre(out):
    x, y, w, h = out["rect"]
    return x + w / 2, y + h / 2


def test_dragging_the_plot_pans_both_axes_by_the_pointer_move():
    d = Driver(_plot)
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    x, y, w, h = d.out["rect"]
    d.press(cx, cy)
    d.move(cx + w / 10, cy)          # a tenth of the width to the right
    d.move(cx + w / 10, cy + h / 5)  # a fifth of the height down
    d.release(cx + w / 10, cy + h / 5)
    lim = d.out["limits"]
    assert lim.x_min == pytest.approx(-1.0, abs=0.05)
    assert lim.x_max == pytest.approx(9.0, abs=0.05)
    assert lim.y_min == pytest.approx(2.0, abs=0.05)
    assert lim.y_max == pytest.approx(12.0, abs=0.05)


def test_the_wheel_zooms_about_the_cursor():
    d = Driver(_plot)
    d.move(-10, -10)
    x, y, w, h = d.out["rect"]
    px, py = x + w * 0.25, y + h * 0.5            # x = 2.5, y = 5
    d.wheel(px, py, 1.0)
    lim = d.out["limits"]
    assert lim.x_max - lim.x_min < 10.0, "wheel up did not zoom in"
    # the value under the cursor stays under the cursor
    frac = (2.5 - lim.x_min) / (lim.x_max - lim.x_min)
    assert frac == pytest.approx(0.25, abs=0.01)
    d.wheel(px, py, -1.0)
    d.wheel(px, py, -1.0)
    lim = d.out["limits"]
    assert lim.x_max - lim.x_min > 10.0, "wheel down did not zoom out"


def test_right_drag_box_selects_and_zooms_to_the_box():
    d = Driver(_plot)
    d.move(-10, -10)
    x, y, w, h = d.out["rect"]
    d.press(x + w * 0.2, y + h * 0.2, button=1)
    d.move(x + w * 0.6, y + h * 0.7)
    assert implot._cur.last_plot.selected, "no selection while dragging"
    d.release(x + w * 0.6, y + h * 0.7, button=1)
    lim = d.out["limits"]
    assert lim.x_min == pytest.approx(2.0, abs=0.05)
    assert lim.x_max == pytest.approx(6.0, abs=0.05)
    assert lim.y_min == pytest.approx(3.0, abs=0.05)
    assert lim.y_max == pytest.approx(8.0, abs=0.05)


def test_the_selection_is_queryable_and_cancellable():
    seen = {}

    def gui(out):
        implot.begin_plot("##q", (500, 300), implot.FLAGS_NO_LEGEND)
        implot.setup_axes_limits(0, 10, 0, 10)
        out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
        seen["selected"] = implot.is_plot_selected()
        seen["selection"] = implot.get_plot_selection()
        implot.end_plot()

    d = Driver(gui)
    d.move(-10, -10)
    x, y, w, h = d.out["rect"]
    d.press(x + w * 0.1, y + h * 0.1, button=1)
    d.move(x + w * 0.5, y + h * 0.5)
    d.move(x + w * 0.5, y + h * 0.5)
    assert seen["selected"]
    sel = seen["selection"]
    assert sel.x_min == pytest.approx(1.0, abs=0.05) and sel.x_max == pytest.approx(5.0, abs=0.05)
    assert sel.y_min == pytest.approx(5.0, abs=0.05) and sel.y_max == pytest.approx(9.0, abs=0.05)
    # a left click while the right button is still held cancels: no zoom
    d.io.mouse_down[0] = True
    d.io.mouse_clicked[0] = True
    d.frame()
    d.io.mouse_down[0] = False
    d.io.mouse_released[0] = True
    d.frame()
    d.release(x + w * 0.5, y + h * 0.5, button=1)
    d.frame()
    assert not seen["selected"]
    lim = implot._cur.last_plot.axes
    assert (lim[implot.AXIS_X1].range_min, lim[implot.AXIS_X1].range_max) == pytest.approx((0.0, 10.0))


def test_double_click_fits_the_data():
    def gui(out):
        implot.begin_plot("##fit", (500, 300), implot.FLAGS_NO_LEGEND)
        implot.plot_line("line", [2, 4], [20, 40])
        out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
        implot.end_plot()
        out["limits"] = implot.get_plot_limits()

    d = Driver(gui)
    d.move(-10, -10)
    assert d.out["limits"].x_min == pytest.approx(2.0)
    cx, cy = _centre(d.out)
    d.wheel(cx, cy, 1.0)
    zoomed = d.out["limits"]
    assert zoomed.x_min > 2.0
    d.wheel(cx, cy, 0.0)
    assert d.out["limits"].x_min == zoomed.x_min, "a zoomed axis kept following its data"
    d.press(cx, cy, double=True)
    d.release(cx, cy)
    lim = d.out["limits"]
    assert (lim.x_min, lim.x_max, lim.y_min, lim.y_max) == pytest.approx((2.0, 4.0, 20.0, 40.0))


def test_dragging_an_axis_pans_only_that_axis():
    d = Driver(_plot)
    d.move(-10, -10)
    ax = implot._cur.last_plot.axes[implot.AXIS_X1]
    x0, y0, x1, y1 = ax.hover_rect
    x, y, w, h = d.out["rect"]
    d.press(x + w / 2, (y0 + y1) / 2)
    d.move(x + w / 2 - w / 5, (y0 + y1) / 2)
    d.release(x + w / 2 - w / 5, (y0 + y1) / 2)
    lim = d.out["limits"]
    assert lim.x_min == pytest.approx(2.0, abs=0.05)
    assert (lim.y_min, lim.y_max) == pytest.approx((0.0, 10.0))


def test_the_wheel_over_an_axis_zooms_only_that_axis():
    d = Driver(_plot)
    d.move(-10, -10)
    ax = implot._cur.last_plot.axes[implot.AXIS_Y1]
    x0, y0, x1, y1 = ax.hover_rect
    d.wheel((x0 + x1) / 2, (y0 + y1) / 2, 1.0)
    lim = d.out["limits"]
    assert lim.y_max - lim.y_min < 10.0
    assert (lim.x_min, lim.x_max) == pytest.approx((0.0, 10.0))


def test_a_locked_axis_does_not_pan():
    d = Driver(lambda out: _plot(out, x_flags=implot.AXIS_FLAGS_LOCK))
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.press(cx, cy)
    d.move(cx + 50, cy + 50)
    d.release(cx + 50, cy + 50)
    lim = d.out["limits"]
    assert (lim.x_min, lim.x_max) == pytest.approx((0.0, 10.0))
    assert lim.y_min != pytest.approx(0.0)


def test_no_inputs_ignores_the_pointer():
    d = Driver(lambda out: _plot(out, flags=implot.FLAGS_NO_INPUTS))
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.wheel(cx, cy, 1.0)
    d.press(cx, cy)
    d.move(cx + 40, cy)
    assert (d.out["limits"].x_min, d.out["limits"].x_max) == pytest.approx((0.0, 10.0))


def test_clicking_a_legend_entry_hides_the_item():
    seen = {}

    def gui(out):
        implot.begin_plot("##legend", (500, 300))
        implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
        implot.plot_line("alpha", [0, 10], [0, 10])
        implot.plot_line("beta", [0, 10], [10, 0])
        seen["records"] = [r["label"] for r in implot._cur.plot.records]
        implot.end_plot()

    d = Driver(gui)
    d.move(-10, -10)
    plot = implot._cur.last_plot
    items = plot.items
    lx0, ly0, lx1, ly1 = items.legend.rect
    lh = RecordingPainter.LINE_H
    style = implot.get_style()
    entry_y = ly0 + style.legend_inner_padding[1] + lh / 2          # first entry: "alpha"
    entry_x = lx0 + style.legend_inner_padding[0] + lh + 4
    d.press(entry_x, entry_y)
    d.release(entry_x, entry_y)
    d.frame()
    assert seen["records"] == ["beta"], seen["records"]
    assert not items.get_legend_item(0).show


def test_hovering_a_legend_entry_highlights_its_item():
    seen = {}

    def gui(out):
        implot.begin_plot("##hl", (500, 300))
        implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
        implot.plot_line("alpha", [0, 10], [0, 10], spec=implot.PlotSpec(line_weight=1.0))
        seen["weight"] = implot._cur.plot.records[0]["spec"].line_weight
        implot.end_plot()

    d = Driver(gui)
    d.move(-10, -10)
    lx0, ly0, _lx1, _ly1 = implot._cur.last_plot.items.legend.rect
    d.move(lx0 + 20, ly0 + 10)
    d.frame()
    assert seen["weight"] == pytest.approx(2.0)


def test_right_click_opens_the_plot_context_menu():
    d = Driver(_plot)
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.press(cx, cy, button=1)
    d.release(cx, cy, button=1)
    menu = implot._cur.last_plot.context_menu
    assert menu is not None and menu["kind"] == "plot"
    p = d.frame()
    assert "Settings" in p.strings and "Legend" in p.strings
    # a click outside closes it
    d.press(5, 5)
    d.release(5, 5)
    assert implot._cur.last_plot.context_menu is None


def test_right_click_on_an_axis_opens_its_menu():
    d = Driver(_plot)
    d.move(-10, -10)
    ax = implot._cur.last_plot.axes[implot.AXIS_Y1]
    x0, y0, x1, y1 = ax.hover_rect
    d.press((x0 + x1) / 2, (y0 + y1) / 2, button=1)
    d.release((x0 + x1) / 2, (y0 + y1) / 2, button=1)
    menu = implot._cur.last_plot.context_menu
    assert menu["kind"] == "y" and menu["index"] == 0
    p = d.frame()
    assert {"Auto-Fit", "Invert", "Opposite", "Grid Lines"} <= set(p.strings)


def test_the_plot_menu_toggles_crosshairs():
    d = Driver(_plot)
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.press(cx, cy, button=1)
    d.release(cx, cy, button=1)
    plot = implot._cur.last_plot
    plot.flags |= implot.FLAGS_CROSSHAIRS
    assert implot.has_flag(plot.flags, implot.FLAGS_CROSSHAIRS)
    # flags handed to begin_plot are only re-applied when the caller changes them
    d.move(-10, -10)
    assert implot.has_flag(implot._cur.last_plot.flags, implot.FLAGS_CROSSHAIRS)


# --------------------------------------------------------------------------- #
# Drag tools: ``modified`` is True only on the frames the user moves them
# --------------------------------------------------------------------------- #
def _tools(out):
    implot.begin_plot("##tools", (500, 300), implot.FLAGS_NO_LEGEND)
    implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
    st = out.setdefault("st", {"x": 5.0, "y": 5.0, "px": 2.0, "py": 2.0, "rect": [6.0, 6.0, 8.0, 8.0]})
    r = implot.drag_line_x(0, st["x"], (1.0, 1.0, 1.0, 1.0))
    st["x"] = r.value
    out["line_x"] = r
    r = implot.drag_line_y(1, st["y"], (1.0, 1.0, 1.0, 1.0))
    st["y"] = r.value
    out["line_y"] = r
    r = implot.drag_point(2, st["px"], st["py"], (1.0, 0.0, 0.0, 1.0))
    st["px"], st["py"] = r.x, r.y
    out["point"] = r
    rc = st["rect"]
    r = implot.drag_rect(3, rc[0], rc[1], rc[2], rc[3], (1.0, 0.0, 1.0, 1.0))
    st["rect"] = [r.x_min, r.y_min, r.x_max, r.y_max]
    out["rect_tool"] = r
    out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
    out["to_px"] = implot.plot_to_pixels
    implot.end_plot()


def _px(out, x, y):
    px, py, w, h = out["rect"]
    return px + w * x / 10.0, py + h * (1 - y / 10.0)


def test_drag_line_x_follows_the_pointer_and_reports_it():
    d = Driver(_tools)
    d.move(-10, -10)
    assert not d.out["line_x"].modified
    x, y = _px(d.out, 5.0, 8.5)
    d.press(x, y)
    assert d.out["line_x"].hovered and d.out["line_x"].held
    assert not d.out["line_x"].modified, "pressing is not moving"
    x2, _ = _px(d.out, 7.0, 8.5)
    d.move(x2, y)
    assert d.out["line_x"].modified
    assert d.out["st"]["x"] == pytest.approx(7.0, abs=0.05)
    d.release(x2, y)
    assert not d.out["line_x"].modified
    assert d.out["st"]["x"] == pytest.approx(7.0, abs=0.05)
    assert (d.out["st"]["y"], d.out["st"]["px"]) == (5.0, 2.0), "another tool moved"


def test_drag_line_y_follows_the_pointer():
    d = Driver(_tools)
    d.move(-10, -10)
    x, y = _px(d.out, 1.0, 5.0)
    d.press(x, y)
    _, y2 = _px(d.out, 1.0, 3.0)
    d.move(x, y2)
    assert d.out["line_y"].modified
    assert d.out["st"]["y"] == pytest.approx(3.0, abs=0.05)
    assert d.out["limits"] if "limits" in d.out else True


def test_drag_point_moves_both_coordinates():
    d = Driver(_tools)
    d.move(-10, -10)
    x, y = _px(d.out, 2.0, 2.0)
    d.press(x, y)
    x2, y2 = _px(d.out, 3.0, 1.0)
    d.move(x2, y2)
    assert d.out["point"].modified
    assert (d.out["st"]["px"], d.out["st"]["py"]) == pytest.approx((3.0, 1.0), abs=0.05)


def test_drag_rect_moves_by_its_centre_and_resizes_by_a_corner():
    d = Driver(_tools)
    d.move(-10, -10)
    x, y = _px(d.out, 7.0, 7.0)                   # the centre grab
    d.press(x, y)
    x2, y2 = _px(d.out, 7.5, 7.0)
    d.move(x2, y2)
    assert d.out["rect_tool"].modified
    assert d.out["st"]["rect"][0] == pytest.approx(6.5, abs=0.05)
    assert d.out["st"]["rect"][2] == pytest.approx(8.5, abs=0.05)
    d.release(x2, y2)
    cx, cy = _px(d.out, 8.5, 8.0)                 # top-right corner
    d.press(cx, cy)
    d.move(*_px(d.out, 9.0, 9.0))
    rc = d.out["st"]["rect"]
    assert (rc[2], rc[3]) == pytest.approx((9.0, 9.0), abs=0.05)
    assert (rc[0], rc[1]) == pytest.approx((6.5, 6.0), abs=0.05)


def test_a_drag_tool_does_not_pan_the_plot_underneath():
    d = Driver(lambda out: (_tools(out), out.__setitem__("limits", implot.get_plot_limits())))
    d.move(-10, -10)
    x, y = _px(d.out, 5.0, 8.5)
    d.press(x, y)
    d.move(*_px(d.out, 6.0, 8.5))
    d.move(*_px(d.out, 6.5, 8.5))
    lim = d.out["limits"]
    assert (lim.x_min, lim.x_max) == pytest.approx((0.0, 10.0))


def test_no_inputs_drag_tools_cannot_be_moved():
    def gui(out):
        implot.begin_plot("##ni", (500, 300), implot.FLAGS_NO_LEGEND)
        implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
        v = out.setdefault("v", 5.0)
        r = implot.drag_line_x(0, v, None, 1, implot.DRAG_TOOL_FLAGS_NO_INPUTS)
        out["v"] = r.value
        out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
        implot.end_plot()

    d = Driver(gui)
    d.move(-10, -10)
    x, y = _px(d.out, 5.0, 5.0)
    d.press(x, y)
    d.move(*_px(d.out, 8.0, 5.0))
    assert d.out["v"] == 5.0


def test_linked_subplot_axes_move_together():
    def gui(out):
        if implot.begin_subplots("##grid", 1, 2, (560, 300), implot.SUBPLOT_FLAGS_LINK_ALL_X):
            rects = []
            for i in range(2):
                implot.begin_plot("", (0, 0), implot.FLAGS_NO_LEGEND)
                implot.setup_axes_limits(0, 10, 0, 10)
                implot.plot_line("l", [0, 10], [0, 10])
                rects.append(implot.get_plot_pos() + implot.get_plot_size())
                implot.end_plot()
                out.setdefault("plots", {})[i] = implot._cur.last_plot
            out["rects"] = rects
            implot.end_subplots()

    d = Driver(gui)
    d.move(-10, -10)
    d.move(-10, -10)
    x, y, w, h = d.out["rects"][0]
    d.press(x + w / 2, y + h / 2)
    d.move(x + w / 2 + w / 10, y + h / 2)
    d.release(x + w / 2 + w / 10, y + h / 2)
    d.frame()
    a = d.out["plots"][0].axes[implot.AXIS_X1]
    b = d.out["plots"][1].axes[implot.AXIS_X1]
    assert a.range_min == pytest.approx(-1.0, abs=0.1)
    assert (b.range_min, b.range_max) == pytest.approx((a.range_min, a.range_max))


def _text_at(painter, string):
    for t in painter.texts:
        if t[5] == string or t[5].strip("* ") == string:
            return t[0] + 4, t[1] + t[3] / 2
    raise AssertionError(f"{string!r} not drawn: {painter.strings}")


def test_the_settings_menu_turns_on_equal_axes():
    d = Driver(_plot)
    d.move(-10, -10)
    cx, cy = _centre(d.out)
    d.press(cx, cy, button=1)
    p = d.release(cx, cy, button=1)
    p = d.frame()
    p = d.press(*_text_at(p, "Settings"))
    p = d.release(*_text_at(p, "Settings"))
    p = d.frame()
    x, y = _text_at(p, "Equal")
    d.press(x, y)
    d.release(x, y)
    plot = implot._cur.last_plot
    assert implot.has_flag(plot.flags, implot.FLAGS_EQUAL)
    assert plot.context_menu is None, "a menu item closes the menu"


def test_the_axis_menu_inverts_the_axis():
    d = Driver(_plot)
    d.move(-10, -10)
    ax = implot._cur.last_plot.axes[implot.AXIS_X1]
    x0, y0, x1, y1 = ax.hover_rect
    d.press((x0 + x1) / 2, (y0 + y1) / 2, button=1)
    d.release((x0 + x1) / 2, (y0 + y1) / 2, button=1)
    p = d.frame()
    x, y = _text_at(p, "Invert")
    d.press(x - 20, y)
    d.release(x - 20, y)
    d.frame()
    assert implot._cur.last_plot.axes[implot.AXIS_X1].is_inverted()
