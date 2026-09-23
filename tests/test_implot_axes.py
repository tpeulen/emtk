"""ImPlot's axes on emtk: scales, inversion, several axes, ticks, links,
constraints, subplots and legends."""
from __future__ import annotations

import calendar
import math

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
    implot.get_style().use_24_hour_clock = False
    implot.get_style().use_iso8601 = False


def _draw(gui, frames=1, w=640, h=420, storage=None):
    storage = {} if storage is None else storage
    io = emtk.IO()
    seen = {}
    rec = None
    for _ in range(frames):
        rec = RecordingPainter()
        with emtk.frame(rec, (0, 0, w, h), io=io, storage=storage):
            emtk.begin("w")
            gui(seen)
            emtk.end()
    return rec, seen


def _labels(axis):
    return [t.text for t in axis.ticker.ticks if t.show_label and t.text]


def test_a_time_axis_labels_months_and_the_year_beneath():
    def gui(seen):
        implot.begin_plot("##time", (600, 300))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_TIME)
        implot.setup_axes_limits(1609459200, 1640995200, 0, 1)
        implot.end_plot()
        seen["x"] = implot._cur.last_plot.axes[implot.AXIS_X1]

    _rec, seen = _draw(gui)
    level0 = [t.text for t in seen["x"].ticker.ticks if t.level == 0 and t.show_label]
    level1 = [t.text for t in seen["x"].ticker.ticks if t.level == 1 and t.show_label]
    assert level0[:3] == ["Jan", "Feb", "Mar"]
    assert level1 == ["2021"]


def test_time_formats_follow_the_style():
    t = implot.PlotTime.from_double(calendar.timegm((1991, 10, 3, 19, 21, 29, 0, 0, 0)) + 0.428552)
    assert implot.format_date(t, implot.I.DATE_FMT_DAY_MO_YR, False) == "10/3/91"
    assert implot.format_date(t, implot.I.DATE_FMT_DAY_MO_YR, True) == "1991-10-03"
    assert implot.format_time(t, implot.I.TIME_FMT_HR_MIN_S_MS, False) == "7:21:29.428pm"
    assert implot.format_time(t, implot.I.TIME_FMT_HR_MIN_S_MS, True) == "19:21:29.428"
    assert implot.format_date(t, implot.I.DATE_FMT_MO_YR, False) == "Oct 1991"
    day = implot.floor_time(t, implot.I.TIME_UNIT_DAY)
    assert implot.format_time(day, implot.I.TIME_FMT_HR_MIN, True) == "00:00"
    assert implot.add_time(day, implot.I.TIME_UNIT_MO, 1).s - day.s == 31 * 86400


def test_hours_on_a_short_time_range():
    def gui(seen):
        implot.begin_plot("##hours", (600, 300))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_TIME)
        implot.setup_axes_limits(1609459200, 1609459200 + 6 * 3600, 0, 1)
        implot.get_style().use_24_hour_clock = True
        implot.end_plot()
        seen["x"] = implot._cur.last_plot.axes[implot.AXIS_X1]

    _rec, seen = _draw(gui)
    labels = _labels(seen["x"])
    assert "01:00" in labels and "1/1/21" in labels


@pytest.mark.parametrize("axis", [implot.AXIS_X1, implot.AXIS_Y1])
def test_an_inverted_axis_runs_the_other_way(axis):
    def gui(seen):
        implot.begin_plot("##inv", (400, 300))
        implot.setup_axis(axis, None, implot.AXIS_FLAGS_INVERT)
        implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
        seen["lo"] = implot.plot_to_pixels(0, 0)
        seen["hi"] = implot.plot_to_pixels(10, 10)
        implot.end_plot()

    _rec, seen = _draw(gui)
    if axis == implot.AXIS_X1:
        assert seen["lo"][0] > seen["hi"][0]
        assert seen["lo"][1] > seen["hi"][1]     # y still up
    else:
        assert seen["lo"][1] < seen["hi"][1]     # y minimum at the top
        assert seen["lo"][0] < seen["hi"][0]


def test_a_log_axis_maps_decades_evenly_and_answers_in_data_units():
    def gui(seen):
        implot.begin_plot("##log", (400, 300))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        implot.setup_axes_limits(1, 1000, 0, 1, implot.COND_ALWAYS)
        seen["px"] = [implot.plot_to_pixels(v, 0)[0] for v in (1, 10, 100, 1000)]
        seen["back"] = implot.pixels_to_plot(seen["px"][2], 0).x
        seen["limits"] = implot.get_plot_limits()
        implot.end_plot()
        seen["x"] = implot._cur.last_plot.axes[implot.AXIS_X1]

    _rec, seen = _draw(gui)
    d = [b - a for a, b in zip(seen["px"], seen["px"][1:])]
    assert d[0] == pytest.approx(d[1]) == pytest.approx(d[2])
    assert seen["back"] == pytest.approx(100.0)
    assert (seen["limits"].x_min, seen["limits"].x_max) == (1.0, 1000.0)
    majors = [t.plot_pos for t in seen["x"].ticker.ticks if t.major]
    minors = [t.plot_pos for t in seen["x"].ticker.ticks if not t.major]
    assert majors == pytest.approx([1, 10, 100, 1000])
    assert 2.0 in minors and 50.0 in minors


def test_symlog_is_linear_near_zero_and_logarithmic_far_out():
    def gui(seen):
        implot.begin_plot("##symlog", (600, 300))
        implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_SYMLOG)
        implot.setup_axes_limits(-100, 100, 0, 1, implot.COND_ALWAYS)
        seen["px"] = {v: implot.plot_to_pixels(v, 0)[0] for v in (-100, -10, 0, 10, 100)}
        implot.end_plot()
        seen["x"] = implot._cur.last_plot.axes[implot.AXIS_X1]

    _rec, seen = _draw(gui)
    px = seen["px"]
    assert px[0] == pytest.approx((px[-100] + px[100]) / 2)
    assert px[10] - px[0] > px[100] - px[10] - 1e-9 or (px[10] - px[0]) > 0.3 * (px[100] - px[0])
    assert {"0", "10", "-10"} <= set(_labels(seen["x"]))


def test_a_custom_transform_scale():
    def gui(seen):
        implot.begin_plot("##sqrt", (400, 300))
        implot.setup_axis_scale(implot.AXIS_Y1, math.sqrt, lambda s: s * s)
        implot.setup_axes_limits(0, 1, 0, 1, implot.COND_ALWAYS)
        seen["quarter"] = implot.plot_to_pixels(0, 0.25)[1]
        seen["ends"] = (implot.plot_to_pixels(0, 0)[1], implot.plot_to_pixels(0, 1)[1])
        implot.end_plot()

    _rec, seen = _draw(gui)
    lo, hi = seen["ends"]
    assert seen["quarter"] == pytest.approx((lo + hi) / 2)


def test_three_y_axes_each_map_their_own_range():
    def gui(seen):
        implot.begin_plot("##multi", (600, 300))
        implot.setup_axes("x", "y1")
        implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
        implot.setup_axis(implot.AXIS_Y2, "y2", implot.AXIS_FLAGS_AUX_DEFAULT)
        implot.setup_axis_limits(implot.AXIS_Y2, 0, 1, implot.COND_ALWAYS)
        implot.setup_axis(implot.AXIS_Y3, "y3", implot.AXIS_FLAGS_AUX_DEFAULT)
        implot.setup_axis_limits(implot.AXIS_Y3, 0, 300, implot.COND_ALWAYS)
        implot.plot_line("a", [0, 10], [0, 10])
        implot.set_axes(implot.AXIS_X1, implot.AXIS_Y2)
        implot.plot_line("b", [0, 10], [0, 1])
        implot.set_axes(implot.AXIS_X1, implot.AXIS_Y3)
        implot.plot_line("c", [0, 10], [0, 300])
        seen["y"] = [implot.plot_to_pixels(0, v, implot.AXIS_X1, ax)[1]
                     for v, ax in ((10, implot.AXIS_Y1), (1, implot.AXIS_Y2), (300, implot.AXIS_Y3))]
        implot.end_plot()
        plot = implot._cur.last_plot
        seen["datums"] = [plot.axes[i].datum1 for i in (implot.AXIS_Y1, implot.AXIS_Y2, implot.AXIS_Y3)]
        seen["rect"] = plot.plot_rect

    rec, seen = _draw(gui)
    assert seen["y"][0] == pytest.approx(seen["y"][1]) == pytest.approx(seen["y"][2])
    y1, y2, y3 = seen["datums"]
    assert y1 == pytest.approx(seen["rect"][0])       # y1 on the left
    assert y2 == pytest.approx(seen["rect"][2])       # y2 on the right (opposite)
    assert y3 > y2                                    # y3 further right
    assert {"y1", "y2", "y3"} <= set(rec.strings)


def test_axis_formats_and_custom_ticks():
    def gui(seen):
        implot.begin_plot("##ticks", (600, 300))
        implot.setup_axes_limits(2.5, 5, 0, 1000, implot.COND_ALWAYS)
        implot.setup_axis_format(implot.AXIS_X1, "%g ms")
        implot.setup_axis_format(implot.AXIS_Y1, lambda v, unit: f"{v / 1000:g} k{unit}", "Hz")
        implot.setup_axis_ticks(implot.AXIS_X1, [3.14], 1, ["PI"], True)
        implot.end_plot()
        plot = implot._cur.last_plot
        seen["x"] = _labels(plot.axes[implot.AXIS_X1])
        seen["y"] = _labels(plot.axes[implot.AXIS_Y1])

    _rec, seen = _draw(gui)
    assert "PI" in seen["x"] and "3 ms" in seen["x"]
    assert "1 kHz" in seen["y"]

    def gui2(seen):
        implot.begin_plot("##ticks2", (600, 300))
        implot.setup_axis_ticks(implot.AXIS_Y1, 0, 1, 3, ["lo", "mid", "hi"], False)
        implot.end_plot()
        seen["y"] = _labels(implot._cur.last_plot.axes[implot.AXIS_Y1])

    _rec, seen = _draw(gui2)
    assert seen["y"] == ["lo", "mid", "hi"]


def test_limits_constraints_clamp_the_range():
    def gui(seen):
        implot.begin_plot("##c", (400, 300))
        implot.setup_axes_limits(-100, 100, 0, 1, implot.COND_ALWAYS)
        implot.setup_axis_limits_constraints(implot.AXIS_X1, -10, 10)
        implot.end_plot()
        seen["lim"] = implot.get_plot_limits()

    _rec, seen = _draw(gui)
    assert (seen["lim"].x_min, seen["lim"].x_max) == (-10.0, 10.0)


def test_linked_axes_share_one_range():
    link = [0.0, 1.0]

    def gui(seen):
        for name in ("A", "B"):
            implot.begin_plot(name, (300, 200))
            implot.setup_axis_links(implot.AXIS_X1, link)
            implot.plot_line("l", [0, 1], [0, 1])
            implot.end_plot()
            seen[name] = implot.get_plot_limits()

    storage = {}
    _draw(gui, storage=storage)
    link[:] = [2.0, 5.0]
    _rec, seen = _draw(gui, storage=storage)
    assert (seen["A"].x_min, seen["A"].x_max) == (2.0, 5.0)
    assert (seen["B"].x_min, seen["B"].x_max) == (2.0, 5.0)


def test_equal_axes_have_the_same_units_per_pixel():
    def gui(seen):
        implot.begin_plot("##eq", (600, 300), implot.FLAGS_EQUAL)
        implot.plot_line("circle", [math.cos(t / 10) for t in range(64)], [math.sin(t / 10) for t in range(64)])
        implot.end_plot()
        plot = implot._cur.last_plot
        seen["aspects"] = (plot.axes[implot.AXIS_X1].get_aspect(), plot.axes[implot.AXIS_Y1].get_aspect())

    _rec, seen = _draw(gui)
    assert seen["aspects"][0] == pytest.approx(seen["aspects"][1], rel=1e-6)


def test_a_new_cond_once_request_is_honoured_but_a_repeat_is_not():
    storage = {}
    limits = [0.0, 10.0]

    def gui(seen):
        implot.begin_plot("##once", (400, 300))
        implot.setup_axis_limits(implot.AXIS_X1, limits[0], limits[1])
        implot.end_plot()
        seen["lim"] = implot.get_plot_limits()

    _draw(gui, storage=storage)
    # the user pans: the repeated request must not undo it
    _rec, seen = _draw(gui, storage=storage)
    stored = [p for p in storage[("__state__", "implot")]["plots"].values()][0]
    stored.axes[implot.AXIS_X1].set_range(3.0, 13.0)
    _rec, seen = _draw(gui, storage=storage)
    assert seen["lim"].x_min == 3.0
    limits[:] = [100.0, 200.0]
    _rec, seen = _draw(gui, storage=storage)
    assert (seen["lim"].x_min, seen["lim"].x_max) == (100.0, 200.0)


def test_an_untouched_axis_follows_its_data():
    storage = {}
    data = [[0, 1], [0, 1]]

    def gui(seen):
        implot.begin_plot("##follow", (400, 300))
        implot.plot_line("l", data[0], data[1])
        implot.end_plot()
        seen["lim"] = implot.get_plot_limits()

    _draw(gui, storage=storage)
    data[0] = [0, 50]
    _rec, seen = _draw(gui, storage=storage)
    assert seen["lim"].x_max == 50.0


def test_the_legend_location_and_orientation():
    def gui_at(loc, flags):
        def gui(seen):
            implot.begin_plot("##leg", (600, 400))
            implot.setup_legend(loc, flags)
            implot.plot_line("alpha", [0, 1], [0, 1])
            implot.plot_line("beta", [0, 1], [1, 0])
            implot.end_plot()
            plot = implot._cur.last_plot
            seen["legend"] = plot.items.legend.rect
            seen["plot"] = plot.plot_rect
            seen["frame"] = plot.frame_rect
        return gui

    _r, se = _draw(gui_at(implot.LOCATION_SOUTH_EAST, 0))
    assert se["legend"][2] == pytest.approx(se["plot"][2] - 10)
    assert se["legend"][3] == pytest.approx(se["plot"][3] - 10)
    _r, hz = _draw(gui_at(implot.LOCATION_NORTH_WEST, implot.LEGEND_FLAGS_HORIZONTAL))
    assert hz["legend"][2] - hz["legend"][0] > hz["legend"][3] - hz["legend"][1]
    _r, out = _draw(gui_at(implot.LOCATION_EAST, implot.LEGEND_FLAGS_OUTSIDE), frames=2)
    assert out["legend"][0] >= out["plot"][2]


def test_subplots_lay_out_a_grid_with_ratios_and_share_a_legend():
    def gui(seen):
        rects = []
        if implot.begin_subplots("Grid", 2, 2, (600, 400), implot.SUBPLOT_FLAGS_SHARE_ITEMS, [3, 1], [1, 1]):
            for i in range(4):
                implot.begin_plot("")
                implot.plot_line("shared", [0, 1], [0, 1])
                implot.plot_line(f"own{i}", [0, 1], [1, 0])
                implot.end_plot()
                rects.append(implot._cur.last_plot.frame_rect)
            seen["legend"] = [i.label for i in implot._cur.current_subplot.items.items]
            implot.end_subplots()
        seen["rects"] = rects

    rec, seen = _draw(gui, frames=2)
    r = seen["rects"]
    assert r[0][1] == r[1][1] and r[2][1] == r[3][1] and r[0][0] == r[2][0]
    top_h, bottom_h = r[0][3] - r[0][1], r[2][3] - r[2][1]
    assert top_h == pytest.approx(3 * bottom_h, rel=0.05)
    assert seen["legend"] == ["shared", "own0", "own1", "own2", "own3"]
    assert rec.strings.count("shared") == 1 and "Grid" in rec.strings


def test_aligned_plots_share_their_left_padding():
    def gui(seen):
        if implot.begin_aligned_plots("group"):
            implot.begin_plot("narrow", (400, 150))
            implot.setup_axes_limits(0, 1, 0, 1, implot.COND_ALWAYS)
            implot.end_plot()
            seen["a"] = implot._cur.last_plot.plot_rect
            implot.begin_plot("wide labels", (400, 150))
            implot.setup_axes_limits(0, 1, 0, 1000000, implot.COND_ALWAYS)
            implot.end_plot()
            seen["b"] = implot._cur.last_plot.plot_rect
            implot.end_aligned_plots()

    _rec, seen = _draw(gui, frames=2)
    assert seen["a"][0] == pytest.approx(seen["b"][0])


def test_mouse_text_and_crosshairs_show_while_hovered():
    storage = {}
    io = emtk.IO()

    def frame():
        rec = RecordingPainter()
        with emtk.frame(rec, (0, 0, 640, 420), io=io, storage=storage):
            emtk.begin("w")
            implot.begin_plot("##hover", (600, 400), implot.FLAGS_CROSSHAIRS)
            implot.setup_axes_limits(0, 10, 0, 10, implot.COND_ALWAYS)
            implot.end_plot()
            emtk.end()
        return rec

    frame()
    pr = implot._cur.last_plot.plot_rect
    io.mouse_pos = ((pr[0] + pr[2]) / 2, (pr[1] + pr[3]) / 2)
    rec = frame()
    assert any(s.startswith("5, 5") or s == "5, 5" for s in rec.strings), rec.strings


def test_the_cpp_spellings_are_the_reference_values():
    assert implot.ImPlotAxisFlags_NoTickLabels == 1 << 3
    assert implot.ImPlotAxisFlags_Invert == 1 << 10
    assert implot.ImPlotAxisFlags_AutoFit == 1 << 11
    assert implot.ImPlotBarsFlags_Horizontal == 1 << 10
    assert implot.ImPlotScale_Log10 == 2 and implot.ImPlotScale_Time == 1
    assert implot.ImPlotMarker_None == -2 and implot.ImPlotMarker_Cross == 7
    assert implot.ImPlotColormap_Greys == 15 and implot.ImPlotColormap_RdBu == 11
    assert implot.ImPlotLocation_NorthEast == (1 << 0) | (1 << 3)
    assert implot.ImAxis_Y3 == 5
    assert implot.ImPlotFlags_CanvasOnly == implot.FLAGS_CANVAS_ONLY


def test_the_obsolete_set_next_styles_still_style_the_next_item():
    def gui(seen):
        implot.begin_plot("##legacy", (400, 300))
        implot.set_next_line_style((1.0, 0.0, 0.0, 1.0), 3.0)
        implot.plot_line("a", [0, 1], [0, 1])
        implot.set_next_fill_style((0.0, 1.0, 0.0, 1.0), 0.5)
        implot.plot_shaded("b", [0, 1], [0, 1])
        implot.set_next_marker_style(implot.MARKER_DIAMOND, 5.0, (0, 0, 255, 255))
        implot.plot_scatter("c", [0, 1], [0, 1])
        seen["specs"] = [r["spec"] for r in implot._cur.plot.records]
        implot.end_plot()

    _rec, seen = _draw(gui)
    line, scatter = seen["specs"]
    assert line.line_color == (255, 0, 0, 255) and line.line_weight == 3.0
    assert scatter.marker == implot.MARKER_DIAMOND and scatter.marker_size == 5.0
    assert scatter.marker_fill_color[:3] == (0, 0, 255)


def test_edge_tick_labels_stay_inside_the_frame():
    """With no plot padding the first and last tick sit on the frame edge;
    their labels are moved in rather than cut."""
    import emtk
    from emtk import implot
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    frame = {}
    with emtk.frame(painter, (0, 0, 400, 200)):
        emtk.begin("w", (0, 0, 400, 200))
        implot.push_style_var(implot.STYLE_VAR_PLOT_PADDING, (0.0, 0.0))
        emtk.set_cursor_screen_pos((50.0, 20.0))
        implot.begin_plot("##p", (300.0, 150.0), implot.FLAGS_CANVAS_ONLY)
        implot.setup_axis_limits(implot.AXIS_X1, 0.0, 6.0, implot.COND_ALWAYS)
        implot.setup_axis_limits(implot.AXIS_Y1, 0.0, 1.0, implot.COND_ALWAYS)
        implot.plot_line("l", [0.0, 6.0], [0.0, 1.0])
        frame["rect"] = implot.get_plot_pos(), implot.get_plot_size()
        implot.end_plot()
        implot.pop_style_var()
        emtk.end()
    labels = {t[5]: t for t in painter.texts if t[5] in ("0", "6")}
    assert set(labels) == {"0", "6"}
    (px, _py), (pw, _ph) = frame["rect"]
    assert labels["0"][0] >= 50.0 - 0.5
    assert labels["6"][0] + labels["6"][2] <= 50.0 + 300.0 + 0.5
