"""``emtk.implot`` -- ImPlot's call shape over :class:`emtk.widgets.plot.Plot`.

The tests are about the *shape* and about the traps: a plot that reserves no
room for its own tick labels draws them into the clip and loses them, and a
log axis that shows the exponent rather than the sample is worse than no
axis at all.
"""
from __future__ import annotations

import math

import pytest

import emtk
from emtk import implot
from emtk.testing import PixelPainter


@pytest.fixture(autouse=True)
def _no_plot_left_open():
    """A test that fails between begin_plot and end_plot leaves the module
    state set, and every later test then fails for the wrong reason."""
    yield
    implot._cur.plot = None


def _frame(fn, w=400, h=260):
    io, storage = emtk.IO(), {}
    p = PixelPainter(w, h, background=(30, 32, 38, 255))
    with emtk.frame(p, (8, 8, w - 16, h - 16), io=io, storage=storage):
        emtk.begin("w")
        fn()
        emtk.end()
    return p


def test_the_call_shape_is_implots():
    """begin/setup/plot/end, as free functions -- what ported C++ reads as."""
    drawn = {}

    def gui():
        drawn["opened"] = implot.begin_plot("t", (-1, 120))
        implot.setup_axes("x", "y")
        implot.plot_line("a", [0, 1, 2], [1.0, 2.0, 1.5])
        implot.end_plot()

    _frame(gui)
    assert drawn["opened"] is True


def test_a_plot_reserves_its_own_space():
    """``dummy()`` on end_plot, so the next widget lands below it and
    ``same_line()`` after a plot works like it does after a button."""
    seen = {}

    def gui():
        seen["before"] = emtk.get_cursor_screen_pos()[1]
        implot.begin_plot("t", (-1, 120))
        implot.plot_line("a", [0, 1], [0.0, 1.0])
        implot.end_plot()
        seen["after"] = emtk.get_cursor_screen_pos()[1]

    _frame(gui)
    assert seen["after"] - seen["before"] >= 120


def test_the_tick_labels_survive_the_clip():
    """Plot draws its y tick labels in the margin *left* of its box, so the
    shim has to reserve that margin -- and Plot has to draw them outside the
    clip that bounds the box. Both were wrong, and the symptom was gridlines
    with no numbers against them."""
    def gui():
        implot.begin_plot("t", (-1, 150))
        implot.setup_axes("time / s", "rate")
        implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 100.0, implot.COND_ALWAYS)
        implot.plot_line("a", [0, 1, 2], [10.0, 50.0, 90.0])
        implot.end_plot()

    p = _frame(gui)
    # the leftmost gutter must contain lit pixels: that is the tick text
    lit = sum(1 for y in range(p.height) for x in range(8, 44)
              if p.px[(y * p.width + x) * 4] > 90)
    assert lit > 0, "no tick labels drawn in the reserved gutter"


def test_a_log_axis_reads_in_the_units_the_caller_plotted():
    """The samples are mapped through log10 on the way in, so the stored tick
    value is an exponent. A tick reading '2' where the datum was 100 is a
    plot that lies."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        implot.plot_line("a", [0, 1, 2], [1.0, 100.0, 10.0])
        assert implot._cur.plot.format_tick(2.0) == "100"
        implot.end_plot()

    _frame(gui)


def test_a_log_axis_drops_what_it_cannot_show():
    """A zero is a real sample -- a dark count, a subtracted background --
    and log10(0) is not a number. ImPlot drops it from the line; so does
    this, rather than raising or plotting -inf."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        implot.plot_line("a", [0, 1, 2], [1.0, 0.0, 10.0])
        assert len(implot._cur.plot._lines[0]["xs"]) == 2
        implot.end_plot()

    _frame(gui)


def test_a_degenerate_axis_range_is_refused():
    """``SetupAxisLimits(axis, v, v)`` collapses the axis and every sample
    lands on one pixel. Ignored, so the auto-fit range stands."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.plot_line("a", [0, 1, 2], [1.0, 2.0, 3.0])
        implot.setup_axis_limits(implot.AXIS_Y1, 5.0, 5.0, implot.COND_ALWAYS)
        lo, hi = implot._cur.plot._y_axis.range
        assert not (lo == 5.0 and hi == 5.0)
        implot.end_plot()

    _frame(gui)


def test_a_nested_plot_is_refused_rather_than_drawn_wrong():
    def gui():
        implot.begin_plot("outer", (-1, 100))
        with pytest.raises(RuntimeError, match="inside a plot"):
            implot.begin_plot("inner", (-1, 50))
        implot.end_plot()

    _frame(gui)


def test_end_without_begin_is_refused():
    def gui():
        with pytest.raises(RuntimeError, match="without a matching"):
            implot.end_plot()

    _frame(gui)


def test_the_mouse_maps_into_the_data_units():
    """A click on the picture has to mean something in the units the data is
    in, and screen y grows downward while data y grows up."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.setup_axes("x", "y")
        implot.plot_line("a", [0.0, 10.0], [0.0, 100.0])
        implot.setup_axis_limits(implot.AXIS_X1, 0.0, 10.0, implot.COND_ALWAYS)
        implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 100.0, implot.COND_ALWAYS)
        x, y, w, h = implot._cur.box
        emtk.get_io().mouse_pos = (x + w / 2.0, y + h / 2.0)
        px, py = implot.get_plot_mouse_pos()
        assert px == pytest.approx(5.0, abs=0.2)
        assert py == pytest.approx(50.0, abs=1.0)
        implot.end_plot()

    _frame(gui)


def test_a_float_style_colour_is_accepted_like_implots():
    """ImPlot styles in floats 0..1; emtk paints in bytes."""
    def gui():
        implot.begin_plot("t", (-1, 100))
        implot.set_next_line_style((1.0, 0.0, 0.0, 1.0), 2.0)
        implot.plot_line("a", [0, 1], [0.0, 1.0])
        assert implot._cur.plot._lines[0]["colour"] == (255, 0, 0, 255)
        implot.end_plot()

    _frame(gui)


def test_the_one_array_overload_indexes_by_position():
    """``PlotLine(label, ys, n)`` -- x is the sample index, as in ImPlot."""
    def gui():
        implot.begin_plot("t", (-1, 100))
        implot.plot_line("a", [3.0, 1.0, 2.0])
        assert list(implot._cur.plot._lines[0]["xs"]) == [0, 1, 2]
        implot.end_plot()

    _frame(gui)


def test_a_plot_with_no_series_still_draws():
    """The first frame of a live trace has no data yet, and a plot that
    raised then would take the whole interface with it."""
    def gui():
        implot.begin_plot("empty", (-1, 100))
        implot.setup_axes("t", "v")
        implot.end_plot()

    _frame(gui)


def test_inf_lines_only_draws_the_direction_it_can():
    """Plot has ``hline`` and no vertical twin. A vertical request is
    skipped, not silently drawn the wrong way round."""
    def gui():
        implot.begin_plot("t", (-1, 100))
        implot.plot_line("a", [0, 1], [0.0, 10.0])
        implot.plot_inf_lines("v", [5.0], 1, 0)                    # vertical
        assert not implot._cur.plot._hlines
        implot.plot_inf_lines("h", [5.0], 1, implot.INF_LINES_HORIZONTAL)
        assert len(implot._cur.plot._hlines) == 1
        implot.end_plot()

    _frame(gui)


def test_a_histogram_bins_raw_samples():
    def gui():
        implot.begin_plot("t", (-1, 100))
        implot.plot_histogram("h", [1.0, 1.1, 5.0, 5.1, 5.2], bins=4)
        assert implot._cur.plot._lines, "histogram drew nothing"
        implot.end_plot()

    _frame(gui)


def _lit_in(p, box, threshold=90):
    """Count pixels brighter than *threshold* (red channel) inside *box*."""
    x0, y0, x1, y1 = box
    return sum(1 for y in range(y0, y1) for x in range(x0, x1)
               if p.px[(y * p.width + x) * 4] > threshold)


def test_a_dashed_line_leaves_gaps_a_solid_one_does_not():
    """A prior drawn dashed beside its solid posterior is the only thing that
    tells the two apart when they share a colour -- so the dash has to be
    visible as gaps along the line, not averaged back into a solid stroke."""
    def draw(dash):
        def gui():
            implot.begin_plot("t", (-1, 120), implot.FLAGS_NO_LEGEND)
            implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 2.0)
            implot.set_next_line_style((250, 250, 250), 2.0, dash=dash)
            implot.plot_line("a", [0.0, 10.0], [1.0, 1.0])
            implot.end_plot()
        return _frame(gui)

    solid, dashed = draw(None), draw((6.0, 6.0))
    row = [y for y in range(solid.height)
           if _lit_in(solid, (60, y, 300, y + 1), 200) > 200]
    assert row, "the solid line was not drawn"
    y = row[0]
    assert _lit_in(dashed, (60, y, 300, y + 1), 200) < 0.7 * _lit_in(solid, (60, y, 300, y + 1), 200)
    assert _lit_in(dashed, (60, y, 300, y + 1), 200) > 0.3 * _lit_in(solid, (60, y, 300, y + 1), 200)


def test_the_dash_pattern_continues_across_samples():
    """On a densely sampled curve every segment is shorter than a dash; a
    pattern that restarted at each vertex would draw the curve solid."""
    xs = [i * 0.05 for i in range(201)]

    def gui():
        implot.begin_plot("t", (-1, 120), implot.FLAGS_NO_LEGEND)
        implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 2.0)
        implot.set_next_line_style((250, 250, 250), 2.0, dash=(8.0, 8.0))
        implot.plot_line("a", xs, [1.0] * len(xs))
        implot.end_plot()

    p = _frame(gui)
    lit_rows = [y for y in range(p.height) if _lit_in(p, (60, y, 300, y + 1), 200) > 20]
    assert lit_rows
    y = lit_rows[0]
    assert _lit_in(p, (60, y, 300, y + 1), 200) < 0.75 * 240


def test_set_next_marker_style_sizes_and_colours_the_scatter():
    """``SetNextMarkerStyle`` is consumed by the next item: its radius and fill
    reach the scatter, and the item after it is back to the default."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.set_next_marker_style(implot.MARKER_SQUARE, 4.0, (255, 0, 0))
        implot.plot_scatter("a", [0, 1], [0.0, 1.0])
        implot.plot_scatter("b", [0, 1], [1.0, 0.0])
        scatters = implot._cur.plot._scatters
        assert scatters[0]["radius"] == 4.0
        assert scatters[0]["marker"] == "square"
        assert scatters[0]["colour"][:3] == (255, 0, 0)
        assert scatters[1]["radius"] == 2.5
        implot.end_plot()

    _frame(gui)


def test_a_marker_style_on_a_line_marks_its_samples():
    """ImPlot draws markers on a line's samples when one is set."""
    def gui():
        implot.begin_plot("t", (-1, 120))
        implot.set_next_marker_style(implot.MARKER_CIRCLE, 3.0)
        implot.plot_line("a", [0, 1, 2], [0.0, 1.0, 0.5])
        assert len(implot._cur.plot._lines) == 1
        assert len(implot._cur.plot._scatters) == 1
        assert implot._cur.plot._scatters[0]["xs"] == [0, 1, 2]
        implot.end_plot()

    _frame(gui)


def test_no_tick_labels_hides_the_numbers_not_the_plot():
    """``AXIS_FLAGS_NO_TICK_LABELS`` on y leaves the gutter dark where the
    numbers would be, while the curve is still drawn."""
    def draw(flags):
        def gui():
            implot.begin_plot("t", (-1, 150), implot.FLAGS_NO_LEGEND)
            implot.setup_axes("", "", 0, flags)
            implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 100.0)
            implot.plot_line("a", [0, 1, 2], [10.0, 50.0, 90.0])
            implot.end_plot()
        return _frame(gui)

    shown, hidden = draw(0), draw(implot.AXIS_FLAGS_NO_TICK_LABELS)
    gutter = (8, 20, 44, 150)
    assert _lit_in(shown, gutter) > 0
    assert _lit_in(hidden, gutter) == 0


def test_a_log_axis_ticks_on_whole_decades():
    """A log tick at 10**0.5 would read '3.16228'. ImPlot's log ticker puts
    them on decades; so does this, once the range spans more than one."""
    seen = {}

    def gui_and_capture():
        implot.begin_plot("t", (-1, 120))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        implot.plot_line("a", [1.0, 10.0, 1000.0], [0.0, 1.0, 0.5])
        plot = implot._cur.plot
        implot.end_plot()
        seen["ticks"] = plot._x_axis.ticks()

    _frame(gui_and_capture)
    assert seen["ticks"] and all(float(t).is_integer() for t in seen["ticks"])
    assert [implot._tick_text(t, True) for t in seen["ticks"]][:2] == ["1", "10"]
