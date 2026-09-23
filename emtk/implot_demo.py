"""``emtk.implot_demo`` -- ImPlot's ``implot_demo.cpp``, on emtk.

Ported from epezent/implot at 7eeb916 (``junk/implot``, MIT). Every demo is a
function of no arguments drawn inside an emtk window, as in the reference;
the C++ ``static`` locals live in :data:`STATE`. :func:`show_demo_window`
lays them out under the reference's tabs and tree nodes, and
:data:`DEMOS` lists them by section for a gallery or a test to walk.

``PlotCandlestick`` -- the demo's custom item, written against
``implot_internal.h`` -- is ported as the demo writes it, on
:func:`emtk.implot_items.begin_item` and friends. One upstream slip is not
copied: its wicks pass *plot* coordinates to ``AddLineV`` where pixels belong.

Not ported: the drag-and-drop demos (emtk's drag-and-drop is its own), the
ImGui table sparklines' table chrome, the metrics and style-editor windows,
and the "Huge Data" button of the time-scale demo (500 MB of samples).
"""
from __future__ import annotations

import math
import random

from . import im_core as _core
from . import im_widgets as im
from . import implot as ImPlot
from . import implot_items as _items
from .implot_internal import gp

__all__ = ["show_demo_window", "DEMOS", "STATE", "plot_candlestick", "make_app"]

#: The demos' ``static`` locals, by demo.
STATE: dict = {}


def _s(name: str, **defaults) -> dict:
    st = STATE.setdefault(name, {})
    for k, v in defaults.items():
        st.setdefault(k, v)
    return st


def _rand(seed: int = 0) -> random.Random:
    return random.Random(seed)


def _time() -> float:
    try:
        return _core.get_time()
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #
# Plots
# --------------------------------------------------------------------------- #
def demo_line_plots() -> None:
    t = _time()
    xs1 = [i * 0.001 for i in range(1001)]
    ys1 = [0.5 + 0.5 * math.sin(50 * (x + t / 10)) for x in xs1]
    xs2 = [i * 1 / 19.0 for i in range(20)]
    ys2 = [x * x for x in xs2]
    if ImPlot.begin_plot("Line Plots"):
        ImPlot.setup_axes("x", "y")
        ImPlot.plot_line("f(x)", xs1, ys1, 1001)
        ImPlot.plot_line("g(x)", xs2, ys2, 20, spec=ImPlot.PlotSpec(
            marker=ImPlot.MARKER_CIRCLE, flags=ImPlot.LINE_FLAGS_SEGMENTS))
        ImPlot.end_plot()


def demo_filled_line_plots() -> None:
    st = _s("filled", show_lines=True, show_fills=True, fill_ref=0.0, shade_mode=0)
    r = _rand(0)
    xs1 = [float(i) for i in range(101)]
    ys1 = [r.uniform(400.0, 450.0) for _ in range(101)]
    ys2 = [r.uniform(275.0, 350.0) for _ in range(101)]
    ys3 = [r.uniform(150.0, 225.0) for _ in range(101)]
    _c, st["show_lines"] = im.checkbox("Lines", st["show_lines"])
    im.same_line()
    _c, st["show_fills"] = im.checkbox("Fills", st["show_fills"])
    if ImPlot.begin_plot("Stock Prices"):
        ImPlot.setup_axes("Days", "Price")
        ImPlot.setup_axes_limits(0, 100, 0, 500)
        if st["show_fills"]:
            ref = -math.inf if st["shade_mode"] == 0 else (math.inf if st["shade_mode"] == 1 else st["fill_ref"])
            spec = ImPlot.PlotSpec(fill_alpha=0.25)
            ImPlot.plot_shaded("Stock 1", xs1, ys1, 101, ref, spec)
            ImPlot.plot_shaded("Stock 2", xs1, ys2, 101, ref, spec)
            ImPlot.plot_shaded("Stock 3", xs1, ys3, 101, ref, spec)
        if st["show_lines"]:
            ImPlot.plot_line("Stock 1", xs1, ys1, 101)
            ImPlot.plot_line("Stock 2", xs1, ys2, 101)
            ImPlot.plot_line("Stock 3", xs1, ys3, 101)
        ImPlot.end_plot()


def demo_shaded_plots() -> None:
    r = _rand(0)
    xs = [i * 0.001 for i in range(1001)]
    ys = [0.25 + 0.25 * math.sin(25 * x) * math.sin(5 * x) + r.uniform(-0.01, 0.01) for x in xs]
    ys1 = [y + r.uniform(0.1, 0.12) for y in ys]
    ys2 = [y - r.uniform(0.1, 0.12) for y in ys]
    ys3 = [0.75 + 0.2 * math.sin(25 * x) for x in xs]
    ys4 = [0.75 + 0.1 * math.cos(25 * x) for x in xs]
    spec = ImPlot.PlotSpec(fill_alpha=0.25)
    if ImPlot.begin_plot("Shaded Plots"):
        ImPlot.setup_legend(ImPlot.LOCATION_NORTH_WEST, ImPlot.LEGEND_FLAGS_REVERSE)
        ImPlot.plot_shaded("Uncertain Data", xs, ys1, ys2, 1001, spec)
        ImPlot.plot_line("Uncertain Data", xs, ys, 1001, spec)
        ImPlot.plot_shaded("Overlapping", xs, ys3, ys4, 1001, spec)
        ImPlot.plot_line("Overlapping", xs, ys3, 1001, spec)
        ImPlot.plot_line("Overlapping", xs, ys4, 1001, spec)
        ImPlot.end_plot()


def demo_scatter_plots() -> None:
    r = _rand(0)
    xs1 = [i * 0.01 for i in range(100)]
    ys1 = [x + 0.1 * r.random() for x in xs1]
    xs2 = [0.25 + 0.2 * r.random() for _ in range(50)]
    ys2 = [0.75 + 0.2 * r.random() for _ in range(50)]
    if ImPlot.begin_plot("Scatter Plot"):
        ImPlot.plot_scatter("Data 1", xs1, ys1, 100)
        c = ImPlot.get_colormap_color(1)
        ImPlot.plot_scatter("Data 2", xs2, ys2, 50, spec=ImPlot.PlotSpec(
            marker=ImPlot.MARKER_SQUARE, marker_size=6, line_color=c, fill_color=c, fill_alpha=0.25))
        ImPlot.end_plot()


def demo_bubble_plots() -> None:
    r = _rand(0)
    xs = [i * 0.1 for i in range(20)]
    ys1 = [r.random() for _ in range(20)]
    ys2 = [r.random() for _ in range(20)]
    szs1 = [0.02 + 0.08 * r.random() for _ in range(20)]
    szs2 = [0.02 + 0.08 * r.random() for _ in range(20)]
    if ImPlot.begin_plot("Bubble Plot", (-1, 0), ImPlot.FLAGS_EQUAL):
        ImPlot.plot_bubbles("Data 1", xs, ys1, szs1, 20, spec=ImPlot.PlotSpec(fill_alpha=0.5))
        ImPlot.plot_bubbles("Data 2", xs, ys2, szs2, 20,
                            spec=ImPlot.PlotSpec(fill_alpha=0.5, line_color=(0.0, 0.0, 0.0, 0.0)))
        ImPlot.end_plot()


def demo_polygon_plots() -> None:
    tri_xs, tri_ys = [0.5, 1.0, 0.0], [1.0, 0.0, 0.0]
    pent = [(3.0 + 0.8 * math.cos(i * 2 * math.pi / 5 - math.pi / 2),
             0.5 + 0.8 * math.sin(i * 2 * math.pi / 5 - math.pi / 2)) for i in range(5)]
    star = [(5.5 + (0.8 if i % 2 == 0 else 0.3) * math.cos(i * 2 * math.pi / 10 - math.pi / 2),
             0.5 + (0.8 if i % 2 == 0 else 0.3) * math.sin(i * 2 * math.pi / 10 - math.pi / 2)) for i in range(10)]
    if ImPlot.begin_plot("Polygon Plot", (-1, 0), ImPlot.FLAGS_EQUAL):
        ImPlot.plot_polygon("Triangle", tri_xs, tri_ys, 3, ImPlot.PlotSpec(fill_alpha=0.5))
        ImPlot.plot_polygon("Pentagon", [p[0] for p in pent], [p[1] for p in pent], 5,
                            ImPlot.PlotSpec(fill_alpha=0.5, fill_color=(0.0, 1.0, 0.0, 1.0)))
        ImPlot.plot_polygon("Star (Concave)", [p[0] for p in star], [p[1] for p in star], 10,
                            ImPlot.PlotSpec(fill_alpha=0.5, fill_color=(1.0, 1.0, 0.0, 1.0),
                                            flags=ImPlot.POLYGON_FLAGS_CONCAVE))
        ImPlot.end_plot()


def demo_stairstep_plots() -> None:
    st = _s("stairs", flags=ImPlot.STAIRS_FLAGS_SHADED)
    ys1 = [0.75 + 0.2 * math.sin(10 * i * 0.05) for i in range(21)]
    ys2 = [0.25 + 0.2 * math.sin(10 * i * 0.05) for i in range(21)]
    _c, st["flags"] = im.checkbox_flags("ImPlotStairsFlags_Shaded", st["flags"], ImPlot.STAIRS_FLAGS_SHADED)
    if ImPlot.begin_plot("Stairstep Plot"):
        ImPlot.setup_axes("x", "f(x)")
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        grey = (0.5, 0.5, 0.5, 1.0)
        ImPlot.plot_line("##1", ys1, 21, 0.05, 0, ImPlot.PlotSpec(line_color=grey))
        ImPlot.plot_line("##2", ys2, 21, 0.05, 0, ImPlot.PlotSpec(line_color=grey))
        spec = ImPlot.PlotSpec(flags=st["flags"], fill_alpha=0.25, marker=ImPlot.MARKER_AUTO)
        ImPlot.plot_stairs("Post Step (default)", ys1, 21, 0.05, 0, spec)
        spec = ImPlot.PlotSpec(flags=st["flags"] | ImPlot.STAIRS_FLAGS_PRE_STEP, fill_alpha=0.25,
                               marker=ImPlot.MARKER_AUTO)
        ImPlot.plot_stairs("Pre Step", ys2, 21, 0.05, 0, spec)
        ImPlot.end_plot()


def demo_bar_plots() -> None:
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    if ImPlot.begin_plot("Bar Plot"):
        ImPlot.plot_bars("Vertical", data, 10, 0.7, 1)
        ImPlot.plot_bars("Horizontal", data, 10, 0.4, 1, spec=ImPlot.PlotSpec(flags=ImPlot.BARS_FLAGS_HORIZONTAL))
        ImPlot.end_plot()


def demo_bar_groups() -> None:
    st = _s("bar_groups", items=3, size=0.67, flags=0, horz=False)
    data = [83, 67, 23, 89, 83, 78, 91, 82, 85, 90,
            80, 62, 56, 99, 55, 78, 88, 78, 90, 100,
            80, 69, 52, 92, 72, 78, 75, 76, 89, 95]
    ilabels = ["Midterm Exam", "Final Exam", "Course Grade"]
    glabels = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]
    positions = [float(i) for i in range(10)]
    _c, st["flags"] = im.checkbox_flags("Stacked", st["flags"], ImPlot.BAR_GROUPS_FLAGS_STACKED)
    im.same_line()
    _c, st["horz"] = im.checkbox("Horizontal", st["horz"])
    if ImPlot.begin_plot("Bar Group"):
        ImPlot.setup_legend(ImPlot.LOCATION_EAST, ImPlot.LEGEND_FLAGS_OUTSIDE)
        if st["horz"]:
            ImPlot.setup_axes("Score", "Student", ImPlot.AXIS_FLAGS_AUTO_FIT, ImPlot.AXIS_FLAGS_AUTO_FIT)
            ImPlot.setup_axis_ticks(ImPlot.AXIS_Y1, positions, 10, glabels)
            ImPlot.plot_bar_groups(ilabels, data, st["items"], 10, st["size"], 0,
                                   ImPlot.PlotSpec(flags=st["flags"] | ImPlot.BAR_GROUPS_FLAGS_HORIZONTAL))
        else:
            ImPlot.setup_axes("Student", "Score", ImPlot.AXIS_FLAGS_AUTO_FIT, ImPlot.AXIS_FLAGS_AUTO_FIT)
            ImPlot.setup_axis_ticks(ImPlot.AXIS_X1, positions, 10, glabels)
            ImPlot.plot_bar_groups(ilabels, data, st["items"], 10, st["size"], 0,
                                   ImPlot.PlotSpec(flags=st["flags"]))
        ImPlot.end_plot()


_LIARS = [4282515870, 4282609140, 4287357182, 4294630301, 4294945280, 4294921472]


def demo_bar_stacks() -> None:
    st = _s("bar_stacks", diverging=True)
    liars = ImPlot.get_colormap_index("Liars")
    if liars < 0:
        liars = ImPlot.add_colormap("Liars", _LIARS, 6)
    politicians = ["Trump", "Bachman", "Cruz", "Gingrich", "Palin", "Santorum", "Walker", "Perry", "Ryan",
                   "McCain", "Rubio", "Romney", "Rand Paul", "Christie", "Biden", "Kasich", "Sanders", "J Bush",
                   "H Clinton", "Obama"]
    data_reg = [18, 26, 7, 14, 10, 8, 6, 11, 4, 4, 3, 8, 6, 8, 6, 5, 0, 3, 1, 2,
                43, 36, 30, 21, 30, 27, 25, 17, 11, 22, 15, 16, 16, 17, 12, 12, 14, 6, 13, 12,
                16, 13, 28, 22, 15, 21, 15, 18, 30, 17, 24, 18, 13, 10, 14, 15, 17, 22, 14, 12,
                17, 10, 13, 25, 12, 22, 19, 26, 23, 17, 22, 27, 20, 26, 29, 17, 18, 22, 21, 27,
                5, 7, 16, 10, 10, 12, 23, 13, 17, 20, 22, 16, 23, 19, 20, 26, 36, 29, 27, 26,
                1, 8, 6, 8, 23, 10, 12, 15, 15, 20, 14, 15, 22, 20, 19, 25, 15, 18, 24, 21]
    labels_reg = ["Pants on Fire", "False", "Mostly False", "Half True", "Mostly True", "True"]
    data_div = [0] * 60 + [-v for v in data_reg[40:60]] + [-v for v in data_reg[20:40]] \
        + [-v for v in data_reg[0:20]] + data_reg[60:120]
    labels_div = ["Pants on Fire", "False", "Mostly False", "Mostly False", "False", "Pants on Fire",
                  "Half True", "Mostly True", "True"]
    _c, st["diverging"] = im.checkbox("Diverging", st["diverging"])
    ImPlot.push_colormap(liars)
    if ImPlot.begin_plot("PolitiFact: Who Lies More?", (-1, _core.get_text_line_height() * 25),
                         ImPlot.FLAGS_NO_MOUSE_TEXT):
        ImPlot.setup_legend(ImPlot.LOCATION_SOUTH, ImPlot.LEGEND_FLAGS_OUTSIDE | ImPlot.LEGEND_FLAGS_HORIZONTAL)
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_AUTO_FIT | ImPlot.AXIS_FLAGS_NO_DECORATIONS,
                          ImPlot.AXIS_FLAGS_AUTO_FIT | ImPlot.AXIS_FLAGS_INVERT)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_Y1, 0, 19, 20, politicians, False)
        spec = ImPlot.PlotSpec(flags=ImPlot.BAR_GROUPS_FLAGS_STACKED | ImPlot.BAR_GROUPS_FLAGS_HORIZONTAL)
        if st["diverging"]:
            ImPlot.plot_bar_groups(labels_div, data_div, 9, 20, 0.75, 0, spec)
        else:
            ImPlot.plot_bar_groups(labels_reg, data_reg, 6, 20, 0.75, 0, spec)
        ImPlot.end_plot()
    ImPlot.pop_colormap()


def demo_error_bars() -> None:
    xs = [1, 2, 3, 4, 5]
    bar = [1, 2, 5, 3, 4]
    lin1 = [8, 8, 9, 7, 8]
    lin2 = [6, 7, 6, 9, 6]
    err1 = [0.2, 0.4, 0.2, 0.6, 0.4]
    err2 = [0.4, 0.2, 0.4, 0.8, 0.6]
    err3 = [0.09, 0.14, 0.09, 0.12, 0.16]
    err4 = [0.02, 0.08, 0.15, 0.05, 0.2]
    if ImPlot.begin_plot("##ErrorBars"):
        ImPlot.setup_axes_limits(0, 6, 0, 10)
        ImPlot.plot_bars("Bar", xs, bar, 5, 0.5)
        ImPlot.plot_error_bars("Bar", xs, bar, err1, 5)
        ImPlot.plot_error_bars("Line", xs, lin1, err1, err2, 5,
                               ImPlot.PlotSpec(line_color=ImPlot.get_colormap_color(1), size=0))
        ImPlot.plot_line("Line", xs, lin1, 5, ImPlot.PlotSpec(marker=ImPlot.MARKER_SQUARE))
        spec = ImPlot.PlotSpec(line_color=ImPlot.get_colormap_color(2), size=6, line_weight=1.5)
        ImPlot.plot_error_bars("Scatter", xs, lin2, err2, 5, spec)
        spec.flags = ImPlot.ERROR_BARS_FLAGS_HORIZONTAL
        ImPlot.plot_error_bars("Scatter", xs, lin2, err3, err4, 5, spec)
        ImPlot.plot_scatter("Scatter", xs, lin2, 5)
        ImPlot.end_plot()


def demo_stem_plots() -> None:
    xs = [i * 0.02 for i in range(51)]
    ys1 = [1.0 + 0.5 * math.sin(25 * x) * math.cos(2 * x) for x in xs]
    ys2 = [0.5 + 0.25 * math.sin(10 * x) * math.sin(x) for x in xs]
    if ImPlot.begin_plot("Stem Plots"):
        ImPlot.setup_axis_limits(ImPlot.AXIS_X1, 0, 1.0)
        ImPlot.setup_axis_limits(ImPlot.AXIS_Y1, 0, 1.6)
        ImPlot.plot_stems("Stems 1", xs, ys1, 51)
        ImPlot.plot_stems("Stems 2", xs, ys2, 51, 0, ImPlot.PlotSpec(marker=ImPlot.MARKER_CIRCLE))
        ImPlot.end_plot()


def demo_infinite_lines() -> None:
    vals = [0.25, 0.5, 0.75]
    if ImPlot.begin_plot("##Infinite"):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_INITIAL_FIT, ImPlot.AXIS_FLAGS_NO_INITIAL_FIT)
        ImPlot.plot_inf_lines("Vertical", vals, 3)
        ImPlot.plot_inf_lines("Horizontal", vals, 3, ImPlot.PlotSpec(flags=ImPlot.INF_LINES_FLAGS_HORIZONTAL))
        ImPlot.end_plot()


def demo_pie_charts() -> None:
    st = _s("pie", data1=[0.15, 0.30, 0.2, 0.05], flags=0)
    labels1 = ["Frogs", "Hogs", "Dogs", "Logs"]
    lh = _core.get_text_line_height()
    if ImPlot.begin_plot("##Pie1", (lh * 16, lh * 16), ImPlot.FLAGS_EQUAL | ImPlot.FLAGS_NO_MOUSE_TEXT):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        ImPlot.plot_pie_chart(labels1, st["data1"], 4, 0.5, 0.5, 0.4, "%.2f", 90,
                              ImPlot.PlotSpec(flags=st["flags"]))
        ImPlot.end_plot()
    im.same_line()
    labels2 = ["A", "B", "C", "D", "E"]
    data2 = [1, 1, 2, 3, 5]
    ImPlot.push_colormap(ImPlot.COLORMAP_PASTEL)
    if ImPlot.begin_plot("##Pie2", (lh * 16, lh * 16), ImPlot.FLAGS_EQUAL | ImPlot.FLAGS_NO_MOUSE_TEXT):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        ImPlot.plot_pie_chart(labels2, data2, 5, 0.5, 0.5, 0.4, "%.0f", 180, ImPlot.PlotSpec(flags=st["flags"]))
        ImPlot.end_plot()
    ImPlot.pop_colormap()


def demo_heatmaps() -> None:
    st = _s("heatmaps", scale_min=0.0, scale_max=6.3, map=ImPlot.COLORMAP_VIRIDIS, hm_flags=0)
    values1 = [[0.8, 2.4, 2.5, 3.9, 0.0, 4.0, 0.0],
               [2.4, 0.0, 4.0, 1.0, 2.7, 0.0, 0.0],
               [1.1, 2.4, 0.8, 4.3, 1.9, 4.4, 0.0],
               [0.6, 0.0, 0.3, 0.0, 3.1, 0.0, 0.0],
               [0.7, 1.7, 0.6, 2.6, 2.2, 6.2, 0.0],
               [1.3, 1.2, 0.0, 0.0, 0.0, 3.2, 5.1],
               [0.1, 2.0, 0.0, 1.4, 0.0, 1.9, 6.3]]
    xlabels = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    ylabels = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    if ImPlot.colormap_button(ImPlot.get_colormap_name(st["map"]), (225, 0), st["map"]):
        st["map"] = (st["map"] + 1) % ImPlot.get_colormap_count()
        ImPlot.bust_color_cache("##Heatmap1")
        ImPlot.bust_color_cache("##Heatmap2")
    axes_flags = ImPlot.AXIS_FLAGS_LOCK | ImPlot.AXIS_FLAGS_NO_GRID_LINES | ImPlot.AXIS_FLAGS_NO_TICK_MARKS
    ImPlot.push_colormap(st["map"])
    lh = _core.get_text_line_height()
    if ImPlot.begin_plot("##Heatmap1", (lh * 14, lh * 14), ImPlot.FLAGS_NO_LEGEND | ImPlot.FLAGS_NO_MOUSE_TEXT):
        ImPlot.setup_axes(None, None, axes_flags, axes_flags)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_X1, 0 + 1.0 / 14.0, 1 - 1.0 / 14.0, 7, xlabels)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_Y1, 1 - 1.0 / 14.0, 0 + 1.0 / 14.0, 7, ylabels)
        ImPlot.plot_heatmap("heat", values1, 7, 7, st["scale_min"], st["scale_max"], "%g", (0, 0), (1, 1),
                            spec=ImPlot.PlotSpec(flags=st["hm_flags"]))
        ImPlot.end_plot()
    im.same_line()
    ImPlot.colormap_scale("##HeatScale", st["scale_min"], st["scale_max"], (60, 225))
    im.same_line()
    size = 80
    r = _rand(1)
    values2 = [r.random() for _ in range(size * size)]
    if ImPlot.begin_plot("##Heatmap2", (lh * 14, lh * 14)):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(-1, 1, -1, 1)
        ImPlot.plot_heatmap("heat1", values2, size, size, 0, 1, None)
        ImPlot.plot_heatmap("heat2", values2, size, size, 0, 1, None, (-1, -1), (0, 0))
        ImPlot.end_plot()
    ImPlot.pop_colormap()


def _normal(n: int, mu: float, sigma: float, seed: int) -> list:
    r = _rand(seed)
    return [r.gauss(mu, sigma) for _ in range(n)]


def demo_histogram() -> None:
    st = _s("histogram", flags=ImPlot.HISTOGRAM_FLAGS_DENSITY, bins=50, mu=5.0, sigma=2.0)
    dist = STATE.setdefault("_hist_dist", _normal(10000, st["mu"], st["sigma"], 3))
    x = [-3 + 16 * i / 99.0 for i in range(100)]
    y = [math.exp(-(v - st["mu"]) ** 2 / (2 * st["sigma"] ** 2)) / (st["sigma"] * math.sqrt(2 * math.pi)) for v in x]
    if ImPlot.begin_plot("##Histograms"):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_AUTO_FIT, ImPlot.AXIS_FLAGS_AUTO_FIT)
        ImPlot.plot_histogram("Empirical", dist, 10000, st["bins"], 1.0, None,
                              ImPlot.PlotSpec(fill_alpha=0.5, flags=st["flags"]))
        ImPlot.plot_line("Theoretical", x, y, 100)
        ImPlot.end_plot()


def demo_histogram_2d() -> None:
    st = _s("hist2d", count=20000, bins=(60, 60), flags=0)
    d1 = STATE.setdefault("_h2_d1", _normal(20000, 1, 2, 4))
    d2 = STATE.setdefault("_h2_d2", _normal(20000, 1, 1, 5))
    flags = ImPlot.AXIS_FLAGS_AUTO_FIT | ImPlot.AXIS_FLAGS_FOREGROUND
    ImPlot.push_colormap("Hot")
    max_count = 0.0
    avail = im.get_content_region_avail()[0]
    if ImPlot.begin_plot("##Hist2D", (avail - 100 - 8, 0)):
        ImPlot.setup_axes(None, None, flags, flags)
        ImPlot.setup_axes_limits(-6, 6, -6, 6)
        max_count = ImPlot.plot_histogram_2d("Hist2D", d1, d2, st["count"], st["bins"][0], st["bins"][1],
                                             (-6, 6, -6, 6), ImPlot.PlotSpec(flags=st["flags"]))
        ImPlot.end_plot()
    im.same_line()
    ImPlot.colormap_scale("Count", 0, max_count, (100, 0))
    ImPlot.pop_colormap()


def demo_digital_plots() -> None:
    t = [i * 0.01 for i in range(1000)]
    if ImPlot.begin_plot("##Digital"):
        ImPlot.setup_axis_limits(ImPlot.AXIS_X1, 0.0, 10.0, ImPlot.COND_ALWAYS)
        ImPlot.setup_axis_limits(ImPlot.AXIS_Y1, -1, 1)
        for i in range(3):
            ys = [float(math.sin(2 * v) > 0.45) if i == 0 else
                  float(math.sin(2 * v) < 0.45) if i == 1 else float(math.sin(50 * v) > 0.5) for v in t]
            ImPlot.plot_digital(f"digital_{i}", t, ys, len(t), ImPlot.PlotSpec(size=(i + 1) * 4))
        ImPlot.plot_line("analog_0", t, [math.sin(2 * v) for v in t], len(t))
        ImPlot.end_plot()


def _checker_texture():
    from .texture import Texture
    w = h = 16
    px = bytearray(w * h * 4)
    for yy in range(h):
        for xx in range(w):
            on = ((xx // 4) + (yy // 4)) % 2
            o = (yy * w + xx) * 4
            px[o:o + 4] = bytes((230, 120 + 8 * xx, 40 + 12 * yy, 255) if on else (40, 60, 90, 255))
    return Texture(w, h, bytes(px))


def demo_images() -> None:
    st = _s("images", bmin=(0.0, 0.0), bmax=(1.0, 1.0), uv0=(0.0, 0.0), uv1=(1.0, 1.0), tint=(1.0, 1.0, 1.0, 1.0))
    tex = STATE.setdefault("_texture", _checker_texture())
    if ImPlot.begin_plot("##image"):
        ImPlot.plot_image("my image", tex, st["bmin"], st["bmax"], st["uv0"], st["uv1"], st["tint"])
        ImPlot.end_plot()


def demo_realtime_plots() -> None:
    t = 10.0
    history = 10.0
    flags = ImPlot.AXIS_FLAGS_NO_TICK_LABELS
    xs = [i * 0.02 for i in range(501)]
    lh = _core.get_text_line_height()
    if ImPlot.begin_plot("##Scrolling", (-1, lh * 10)):
        ImPlot.setup_axes(None, None, flags, flags)
        ImPlot.setup_axis_limits(ImPlot.AXIS_X1, t - history, t, ImPlot.COND_ALWAYS)
        ImPlot.setup_axis_limits(ImPlot.AXIS_Y1, 0, 1)
        ImPlot.plot_shaded("Mouse X", xs, [0.5 + 0.3 * math.sin(x) for x in xs], len(xs), -math.inf,
                           ImPlot.PlotSpec(fill_alpha=0.5))
        ImPlot.plot_line("Mouse Y", xs, [0.5 + 0.3 * math.cos(1.3 * x) for x in xs], len(xs))
        ImPlot.end_plot()


def demo_markers_and_text() -> None:
    spec = ImPlot.PlotSpec(marker=ImPlot.MARKER_AUTO)
    if ImPlot.begin_plot("##MarkerStyles", (-1, 0), ImPlot.FLAGS_CANVAS_ONLY):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(0, 10, -2, 12)
        xs, ys = [1, 4], [10, 11]
        for m in range(ImPlot.MARKER_COUNT):
            im.push_id(m)
            spec.fill_alpha = 1.0
            ImPlot.plot_line("##Filled", xs, ys, 2, spec)
            im.pop_id()
            ys = [ys[0] - 1, ys[1] - 1]
        xs, ys = [6, 9], [10, 11]
        for m in range(ImPlot.MARKER_COUNT):
            im.push_id(m)
            spec.fill_alpha = 0.0
            ImPlot.plot_line("##Open", xs, ys, 2, spec)
            im.pop_id()
            ys = [ys[0] - 1, ys[1] - 1]
        ImPlot.plot_text("Filled Markers", 2.5, 5.0)
        ImPlot.plot_text("Open Markers", 7.5, 5.0)
        ImPlot.push_style_color(ImPlot.COL_INLAY_TEXT, (1.0, 0.0, 1.0, 1.0))
        ImPlot.plot_text("Vertical Text", 5.0, 5.0, (0, 0), ImPlot.PlotSpec(flags=ImPlot.TEXT_FLAGS_VERTICAL))
        ImPlot.pop_style_color()
        ImPlot.end_plot()


def demo_nan_values() -> None:
    data1 = [0.0, 0.25, math.nan, 0.75, 1.0]
    data2 = [0.0, 0.25, 0.5, 0.75, 1.0]
    if ImPlot.begin_plot("##NaNValues"):
        ImPlot.plot_line("line", data1, data2, 5, ImPlot.PlotSpec(marker=ImPlot.MARKER_SQUARE))
        ImPlot.plot_bars("bars", data1, 5)
        ImPlot.end_plot()


def _hsv(h, s, v):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255), 255)


def demo_per_index_colors() -> None:
    xs1 = [i * 0.001 for i in range(1001)]
    ys1 = [0.5 + 0.5 * math.sin(50 * x) for x in xs1]
    colors1 = [_hsv(i / 1000.0, 0.8, 0.9) for i in range(1001)]
    xs2 = [i / 19.0 for i in range(20)]
    ys2 = [x * x for x in xs2]
    colors2 = [ImPlot.sample_colormap(i / 19.0, ImPlot.COLORMAP_VIRIDIS) for i in range(20)]
    if ImPlot.begin_plot("Colorful Lines"):
        ImPlot.setup_axes("x", "y")
        ImPlot.plot_line("f(x)", xs1, ys1, 1001, ImPlot.PlotSpec(line_colors=colors1))
        ImPlot.plot_line("g(x)", xs2, ys2, 20, ImPlot.PlotSpec(
            marker=ImPlot.MARKER_CIRCLE, flags=ImPlot.LINE_FLAGS_SEGMENTS, line_colors=colors2,
            marker_fill_colors=colors2, marker_line_colors=colors2))
        ImPlot.end_plot()


# --------------------------------------------------------------------------- #
# Subplots
# --------------------------------------------------------------------------- #
def _sinewave_getter(i, data):
    return (float(i), math.sin(data * i))


def demo_subplots_sizing() -> None:
    st = _s("sub_sizing", flags=ImPlot.SUBPLOT_FLAGS_SHARE_ITEMS | ImPlot.SUBPLOT_FLAGS_NO_LEGEND,
            rows=3, cols=3, rratios=[5, 1, 1, 1, 1, 1], cratios=[5, 1, 1, 1, 1, 1])
    rows, cols = st["rows"], st["cols"]
    if ImPlot.begin_subplots("My Subplots", rows, cols, (-1, 400), st["flags"], st["rratios"], st["cratios"]):
        for i in range(rows * cols):
            if ImPlot.begin_plot("", (0, 0), ImPlot.FLAGS_NO_LEGEND):
                ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
                fi = 0.01 * (i + 1)
                col = ImPlot.sample_colormap(i / (rows * cols - 1), ImPlot.COLORMAP_JET)
                ImPlot.plot_line_g(f"data{i}", _sinewave_getter, fi, 1000, ImPlot.PlotSpec(line_color=col))
                ImPlot.end_plot()
        ImPlot.end_subplots()


def demo_subplot_item_sharing() -> None:
    st = _s("sub_sharing", flags=ImPlot.SUBPLOT_FLAGS_SHARE_ITEMS, id=[0, 1, 2, 3, 4, 5])
    rows, cols = 2, 3
    if ImPlot.begin_subplots("##ItemSharing", rows, cols, (-1, 400), st["flags"]):
        ImPlot.setup_legend(ImPlot.LOCATION_SOUTH, ImPlot.LEGEND_FLAGS_SORT | ImPlot.LEGEND_FLAGS_HORIZONTAL)
        for i in range(rows * cols):
            if ImPlot.begin_plot(""):
                ImPlot.plot_line_g("common", _sinewave_getter, 0.01, 1000)
                for j in range(6):
                    if st["id"][j] == i:
                        ImPlot.plot_line_g(f"data{j}", _sinewave_getter, 0.01 * (j + 2), 1000)
                ImPlot.end_plot()
        ImPlot.end_subplots()


def demo_subplot_axis_linking() -> None:
    st = _s("sub_linking", flags=ImPlot.SUBPLOT_FLAGS_LINK_ROWS | ImPlot.SUBPLOT_FLAGS_LINK_COLS)
    if ImPlot.begin_subplots("##AxisLinking", 2, 2, (-1, 400), st["flags"]):
        for i in range(4):
            if ImPlot.begin_plot(""):
                ImPlot.setup_axes_limits(0, 1000, -1, 1)
                ImPlot.plot_line_g("common", _sinewave_getter, 0.01, 1000)
                ImPlot.end_plot()
        ImPlot.end_subplots()


def _sparkline(id_, values, count, min_v, max_v, offset, col, size) -> None:
    ImPlot.push_style_var(ImPlot.STYLE_VAR_PLOT_PADDING, (0, 0))
    if ImPlot.begin_plot(id_, size, ImPlot.FLAGS_CANVAS_ONLY):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(0, count - 1, min_v, max_v, ImPlot.COND_ALWAYS)
        ImPlot.plot_line(id_, values, count, 1, 0, ImPlot.PlotSpec(
            line_color=col, fill_color=col, fill_alpha=0.25, offset=offset, flags=ImPlot.LINE_FLAGS_SHADED))
        ImPlot.end_plot()
    ImPlot.pop_style_var()


def demo_tables() -> None:
    ImPlot.push_colormap(ImPlot.COLORMAP_COOL)
    for row in range(4):
        r = _rand(row)
        data = [r.uniform(0.0, 10.0) for _ in range(100)]
        im.text(f"EMG {row}  {data[0]:.3f} V")
        im.same_line()
        im.push_id(row)
        _sparkline("##spark", data, 100, 0, 11.0, 0, ImPlot.get_colormap_color(row), (-1, 35))
        im.pop_id()
    ImPlot.pop_colormap()


# --------------------------------------------------------------------------- #
# Axes
# --------------------------------------------------------------------------- #
def demo_log_scale() -> None:
    xs = [i * 0.1 for i in range(1001)]
    ys1 = [math.sin(x) + 1 for x in xs]
    ys2 = [math.log(x) if x > 0 else -math.inf for x in xs]
    ys3 = [10.0 ** x for x in xs[:21]]
    if ImPlot.begin_plot("Log Plot", (-1, 0)):
        ImPlot.setup_axis_scale(ImPlot.AXIS_X1, ImPlot.SCALE_LOG10)
        ImPlot.setup_axes_limits(0.1, 100, 0, 10)
        ImPlot.plot_line("f(x) = x", xs, xs, 1001)
        ImPlot.plot_line("f(x) = sin(x)+1", xs, ys1, 1001)
        ImPlot.plot_line("f(x) = log(x)", xs, ys2, 1001)
        ImPlot.plot_line("f(x) = 10^x", xs[:21], ys3, 21)
        ImPlot.end_plot()


def demo_symmetric_log_scale() -> None:
    xs = [i * 0.1 - 50 for i in range(1001)]
    ys1 = [math.sin(x) for x in xs]
    ys2 = [i * 0.002 - 1 for i in range(1001)]
    if ImPlot.begin_plot("SymLog Plot", (-1, 0)):
        ImPlot.setup_axis_scale(ImPlot.AXIS_X1, ImPlot.SCALE_SYMLOG)
        ImPlot.plot_line("f(x) = a*x+b", xs, ys2, 1001)
        ImPlot.plot_line("f(x) = sin(x)", xs, ys1, 1001)
        ImPlot.end_plot()


def demo_time_scale() -> None:
    t_min, t_max = 1609459200.0, 1640995200.0
    if ImPlot.begin_plot("##Time", (-1, 0)):
        ImPlot.setup_axis_scale(ImPlot.AXIS_X1, ImPlot.SCALE_TIME)
        ImPlot.setup_axes_limits(t_min, t_max, 0, 1)
        ts = [t_min + i * 86400.0 for i in range(366)]
        ImPlot.plot_line("Time Series", ts, [0.5 + 0.25 * math.sin(i / 20.0) for i in range(366)], 366)
        t_now, y_now = t_min + 200 * 86400.0, 0.5 + 0.25 * math.sin(10.0)
        ImPlot.plot_scatter("Now", [t_now], [y_now], 1)
        ImPlot.annotation(t_now, y_now, ImPlot.get_last_item_color(), (10, 10), False, "Now")
        ImPlot.end_plot()


def demo_custom_scale() -> None:
    v = [i * 0.01 for i in range(100)]
    if ImPlot.begin_plot("Sqrt"):
        ImPlot.setup_axis(ImPlot.AXIS_X1, "Linear")
        ImPlot.setup_axis(ImPlot.AXIS_Y1, "Sqrt")
        ImPlot.setup_axis_scale(ImPlot.AXIS_Y1, math.sqrt, lambda s: s * s)
        ImPlot.setup_axis_limits_constraints(ImPlot.AXIS_Y1, 0, math.inf)
        ImPlot.plot_line("##data", v, v, 100)
        ImPlot.end_plot()


def demo_multiple_axes() -> None:
    xs = [i * 0.1 for i in range(1001)]
    xs2 = [x + 10.0 for x in xs]
    ys1 = [math.sin(x) * 3 + 1 for x in xs]
    ys2 = [math.cos(x) * 0.2 + 0.5 for x in xs]
    ys3 = [math.sin(x + 0.5) * 100 + 200 for x in xs]
    if ImPlot.begin_plot("Multi-Axis Plot", (-1, 0)):
        ImPlot.setup_axes("X-Axis 1", "Y-Axis 1")
        ImPlot.setup_axes_limits(0, 100, 0, 10)
        ImPlot.setup_axis(ImPlot.AXIS_X2, "X-Axis 2", ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis_limits(ImPlot.AXIS_X2, 0, 100)
        ImPlot.setup_axis(ImPlot.AXIS_Y2, "Y-Axis 2", ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis_limits(ImPlot.AXIS_Y2, 0, 1)
        ImPlot.setup_axis(ImPlot.AXIS_Y3, "Y-Axis 3", ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis_limits(ImPlot.AXIS_Y3, 0, 300)
        ImPlot.plot_line("f(x) = x", xs, xs, 1001)
        ImPlot.set_axes(ImPlot.AXIS_X2, ImPlot.AXIS_Y1)
        ImPlot.plot_line("f(x) = sin(x)*3+1", xs2, ys1, 1001)
        ImPlot.set_axes(ImPlot.AXIS_X1, ImPlot.AXIS_Y2)
        ImPlot.plot_line("f(x) = cos(x)*.2+.5", xs, ys2, 1001)
        ImPlot.set_axes(ImPlot.AXIS_X2, ImPlot.AXIS_Y3)
        ImPlot.plot_line("f(x) = sin(x+.5)*100+200 ", xs2, ys3, 1001)
        ImPlot.end_plot()


def _metric_formatter(value, unit):
    v = (1e9, 1e6, 1e3, 1, 1e-3, 1e-6, 1e-9)
    p = ("G", "M", "k", "", "m", "u", "n")
    if value == 0:
        return f"0 {unit}"
    for i in range(7):
        if abs(value) >= v[i]:
            return f"{value / v[i]:g} {p[i]}{unit}"
    return f"{value / v[6]:g} {p[6]}{unit}"


def demo_tick_labels() -> None:
    if ImPlot.begin_plot("##Ticks"):
        ImPlot.setup_axes_limits(2.5, 5, 0, 1000)
        ImPlot.setup_axis(ImPlot.AXIS_Y2, None, ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis(ImPlot.AXIS_Y3, None, ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis_format(ImPlot.AXIS_X1, "%g ms")
        ImPlot.setup_axis_format(ImPlot.AXIS_Y1, _metric_formatter, "Hz")
        ImPlot.setup_axis_format(ImPlot.AXIS_Y2, "%g dB")
        ImPlot.setup_axis_format(ImPlot.AXIS_Y3, _metric_formatter, "m")
        ImPlot.setup_axis_ticks(ImPlot.AXIS_X1, [3.14], 1, ["PI"], True)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_Y1, [100, 300, 700, 900], 4, ["One", "Three", "Seven", "Nine"], False)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_Y2, [0.2, 0.4, 0.6], 3, ["A", "B", "C"], False)
        ImPlot.setup_axis_ticks(ImPlot.AXIS_Y3, 0, 1, 6, ["A", "B", "C", "D", "E", "F"], False)
        ImPlot.end_plot()


def demo_linked_axes() -> None:
    lims = STATE.setdefault("_linked", {"x": [0.0, 1.0], "y": [0.0, 1.0]})
    data = [0, 1]
    if ImPlot.begin_aligned_plots("AlignedGroup"):
        for name in ("Plot A", "Plot B"):
            if ImPlot.begin_plot(name, (-1, 150)):
                ImPlot.setup_axis_links(ImPlot.AXIS_X1, lims["x"])
                ImPlot.setup_axis_links(ImPlot.AXIS_Y1, lims["y"])
                ImPlot.plot_line("Line", data, 2)
                ImPlot.end_plot()
        ImPlot.end_aligned_plots()


def demo_axis_constraints() -> None:
    if ImPlot.begin_plot("##AxisConstraints", (-1, 0)):
        ImPlot.setup_axes("X", "Y")
        ImPlot.setup_axes_limits(-1, 1, -1, 1)
        ImPlot.setup_axis_limits_constraints(ImPlot.AXIS_X1, -10, 10)
        ImPlot.setup_axis_zoom_constraints(ImPlot.AXIS_X1, 1, 20)
        ImPlot.setup_axis_limits_constraints(ImPlot.AXIS_Y1, -10, 10)
        ImPlot.setup_axis_zoom_constraints(ImPlot.AXIS_Y1, 1, 20)
        ImPlot.end_plot()


def demo_equal_axes() -> None:
    xs1 = [math.cos(i * 2 * math.pi / 359.0) for i in range(360)]
    ys1 = [math.sin(i * 2 * math.pi / 359.0) for i in range(360)]
    xs2 = [-1, 0, 1, 0, -1]
    ys2 = [0, 1, 0, -1, 0]
    if ImPlot.begin_plot("##EqualAxes", (-1, 0), ImPlot.FLAGS_EQUAL):
        ImPlot.setup_axis(ImPlot.AXIS_X2, None, ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.setup_axis(ImPlot.AXIS_Y2, None, ImPlot.AXIS_FLAGS_AUX_DEFAULT)
        ImPlot.plot_line("Circle", xs1, ys1, 360)
        ImPlot.set_axes(ImPlot.AXIS_X2, ImPlot.AXIS_Y2)
        ImPlot.plot_line("Diamond", xs2, ys2, 5)
        ImPlot.end_plot()


def demo_auto_fitting_data() -> None:
    data = [1 + math.sin(i / 10.0) for i in range(101)]
    if ImPlot.begin_plot("##DataFitting"):
        ImPlot.setup_axes("X", "Y", 0, ImPlot.AXIS_FLAGS_AUTO_FIT | ImPlot.AXIS_FLAGS_RANGE_FIT)
        ImPlot.plot_line("Line", data, 101)
        ImPlot.plot_stems("Stems", data, 101)
        ImPlot.end_plot()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
def demo_item_styling_and_spec() -> None:
    xs1 = [i / 19.0 for i in range(20)]
    if ImPlot.begin_plot("##SpecStyling"):
        ImPlot.setup_axes("x", "y")
        spec = ImPlot.PlotSpec(line_color=(1.0, 1.0, 0.0, 1.0), line_weight=1.0, fill_color=(1.0, 0.5, 0.0, 1.0),
                               fill_alpha=0.5, marker=ImPlot.MARKER_SQUARE, marker_size=6,
                               flags=ImPlot.ITEM_FLAGS_NO_LEGEND | ImPlot.LINE_FLAGS_SHADED)
        ImPlot.plot_line("Line 1", xs1, [x * x for x in xs1], 20, spec)
        ImPlot.plot_line("Line 2", xs1, [x * x * x for x in xs1], 20, ImPlot.PlotSpec(
            ImPlot.PROP_LINE_COLOR, (0.0, 1.0, 1.0, 1.0), ImPlot.PROP_LINE_WEIGHT, 1.0,
            ImPlot.PROP_FILL_COLOR, (0.0, 0.0, 1.0, 1.0), ImPlot.PROP_FILL_ALPHA, 0.5,
            ImPlot.PROP_MARKER, ImPlot.MARKER_DIAMOND, ImPlot.PROP_SIZE, 6,
            ImPlot.PROP_FLAGS, ImPlot.ITEM_FLAGS_NO_LEGEND | ImPlot.LINE_FLAGS_SHADED))
        ImPlot.end_plot()


def demo_offset_and_stride() -> None:
    k_circles, k_points = 11, 50
    st = _s("stride", offset=0)
    data = [0.0] * (2 * k_points * k_circles)
    for p in range(k_points):
        for c in range(k_circles):
            r = c / (k_circles - 1) * 0.2 + 0.2
            data[p * 2 * k_circles + 2 * c] = 0.5 + r * math.cos(p / k_points * 6.28)
            data[p * 2 * k_circles + 2 * c + 1] = 0.5 + r * math.sin(p / k_points * 6.28)
    if ImPlot.begin_plot("##strideoffset", (-1, 0), ImPlot.FLAGS_EQUAL):
        ImPlot.push_colormap(ImPlot.COLORMAP_JET)
        for c in range(k_circles):
            ImPlot.plot_line(f"Circle {c}", data[c * 2:], data[c * 2 + 1:], k_points,
                             ImPlot.PlotSpec(offset=st["offset"], stride=2 * k_circles))
        ImPlot.end_plot()
        ImPlot.pop_colormap()


def demo_drag_points() -> None:
    st = _s("drag_points", P=[[0.05, 0.05], [0.2, 0.4], [0.8, 0.6], [0.95, 0.95]], flags=0)
    ax_flags = ImPlot.AXIS_FLAGS_NO_TICK_LABELS | ImPlot.AXIS_FLAGS_NO_TICK_MARKS
    if ImPlot.begin_plot("##Bezier", (-1, 0), ImPlot.FLAGS_CANVAS_ONLY):
        ImPlot.setup_axes(None, None, ax_flags, ax_flags)
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        P = st["P"]
        cols = [(0.0, 0.9, 0.0, 1.0), (1.0, 0.5, 1.0, 1.0), (0.0, 0.5, 1.0, 1.0), (0.0, 0.9, 0.0, 1.0)]
        res = []
        for i in range(4):
            r = ImPlot.drag_point(i, P[i][0], P[i][1], cols[i], 4, st["flags"])
            P[i][0], P[i][1] = r.x, r.y
            res.append(r)
        B = []
        for i in range(100):
            t = i / 99.0
            u = 1 - t
            w1, w2, w3, w4 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
            B.append((w1 * P[0][0] + w2 * P[1][0] + w3 * P[2][0] + w4 * P[3][0],
                      w1 * P[0][1] + w2 * P[1][1] + w3 * P[2][1] + w4 * P[3][1]))
        ImPlot.plot_line("##h1", [P[0][0], P[1][0]], [P[0][1], P[1][1]], 2, ImPlot.PlotSpec(
            line_color=cols[1], line_weight=2.0 if res[1].hovered or res[1].held else 1.0))
        ImPlot.plot_line("##h2", [P[2][0], P[3][0]], [P[2][1], P[3][1]], 2, ImPlot.PlotSpec(
            line_color=cols[2], line_weight=2.0 if res[2].hovered or res[2].held else 1.0))
        ImPlot.plot_line("##bez", [b[0] for b in B], [b[1] for b in B], 100, ImPlot.PlotSpec(
            line_color=cols[0], line_weight=3.0 if (res[0].hovered or res[3].held) else 2.0))
        ImPlot.end_plot()


def demo_drag_lines() -> None:
    st = _s("drag_lines", x1=0.2, x2=0.8, y1=0.25, y2=0.75, f=0.1, flags=0)
    if ImPlot.begin_plot("##lines", (-1, 0)):
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        white = (1.0, 1.0, 1.0, 1.0)
        st["x1"] = ImPlot.drag_line_x(0, st["x1"], white, 1, st["flags"]).value
        st["x2"] = ImPlot.drag_line_x(1, st["x2"], white, 1, st["flags"]).value
        st["y1"] = ImPlot.drag_line_y(2, st["y1"], white, 1, st["flags"]).value
        st["y2"] = ImPlot.drag_line_y(3, st["y2"], white, 1, st["flags"]).value
        x1, x2, y1, y2 = st["x1"], st["x2"], st["y1"], st["y2"]
        xs = [(x2 + x1) / 2 + abs(x2 - x1) * (i / 1000.0 - 0.5) for i in range(1000)]
        r = ImPlot.drag_line_y(120482, st["f"], (1.0, 0.5, 1.0, 1.0), 1, st["flags"])
        st["f"] = r.value
        ys = [(y1 + y2) / 2 + abs(y2 - y1) / 2 * math.sin(st["f"] * i / 10) for i in range(1000)]
        ImPlot.plot_line("Interactive Data", xs, ys, 1000,
                         ImPlot.PlotSpec(line_weight=2.0 if r.hovered or r.held else 1.0))
        ImPlot.end_plot()


def demo_drag_rects() -> None:
    st = _s("drag_rects", rect=[0.0025, 0.0045, 0.0, 0.5], flags=0)
    x_data = [i / 44100.0 for i in range(512)]
    y1 = [math.sin(2 * 3.14 * 500 * t) for t in x_data]
    y2 = [a * -0.6 + math.sin(2 * 2 * 3.14 * 500 * t) * 0.4 for a, t in zip(y1, x_data)]
    y3 = [a * -0.6 + math.sin(3 * 2 * 3.14 * 500 * t) * 0.4 for a, t in zip(y2, x_data)]
    rect = st["rect"]
    lh = _core.get_text_line_height()
    res = None
    if ImPlot.begin_plot("##Main", (-1, lh * 10)):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_TICK_LABELS, ImPlot.AXIS_FLAGS_NO_TICK_LABELS)
        ImPlot.setup_axes_limits(0, 0.01, -1, 1)
        ImPlot.plot_line("Signal 1", x_data, y1, 512)
        ImPlot.plot_line("Signal 2", x_data, y2, 512)
        ImPlot.plot_line("Signal 3", x_data, y3, 512)
        res = ImPlot.drag_rect(0, rect[0], rect[2], rect[1], rect[3], (1.0, 0.0, 1.0, 1.0), st["flags"])
        rect[0], rect[2], rect[1], rect[3] = res.x_min, res.y_min, res.x_max, res.y_max
        ImPlot.end_plot()
    if ImPlot.begin_plot("##rect", (-1, lh * 10), ImPlot.FLAGS_CANVAS_ONLY):
        ImPlot.setup_axes(None, None, ImPlot.AXIS_FLAGS_NO_DECORATIONS, ImPlot.AXIS_FLAGS_NO_DECORATIONS)
        ImPlot.setup_axes_limits(rect[0], rect[1], rect[2], rect[3], ImPlot.COND_ALWAYS)
        ImPlot.plot_line("Signal 1", x_data, y1, 512)
        ImPlot.plot_line("Signal 2", x_data, y2, 512)
        ImPlot.plot_line("Signal 3", x_data, y3, 512)
        ImPlot.end_plot()


def demo_querying() -> None:
    st = _s("querying", rects=[(0.2, 0.45, 0.2, 0.45)])
    r = _rand(7)
    data = STATE.setdefault("_query_data", [(r.uniform(0.1, 0.9), r.uniform(0.1, 0.9)) for _ in range(50)])
    if ImPlot.begin_plot("##Centroid"):
        ImPlot.setup_axes_limits(0, 1, 0, 1)
        ImPlot.plot_scatter("Points", [p[0] for p in data], [p[1] for p in data], len(data))
        if ImPlot.is_plot_selected():
            sel = ImPlot.get_plot_selection()
            inside = [p for p in data if sel.contains(*p)]
            if inside:
                ImPlot.plot_scatter("Centroid", [sum(p[0] for p in inside) / len(inside)],
                                    [sum(p[1] for p in inside) / len(inside)], 1,
                                    ImPlot.PlotSpec(marker=ImPlot.MARKER_SQUARE, marker_size=6))
        for i, (x0, x1, y0, y1) in enumerate(st["rects"]):
            inside = [p for p in data if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
            if inside:
                ImPlot.plot_scatter("Centroid", [sum(p[0] for p in inside) / len(inside)],
                                    [sum(p[1] for p in inside) / len(inside)], 1,
                                    ImPlot.PlotSpec(marker=ImPlot.MARKER_SQUARE, marker_size=6))
            res = ImPlot.drag_rect(i, x0, y0, x1, y1, (1.0, 0.0, 1.0, 1.0))
            st["rects"][i] = (res.x_min, res.x_max, res.y_min, res.y_max)
        ImPlot.end_plot()


def demo_annotations() -> None:
    st = _s("annotations", clamp=False)
    clamp = st["clamp"]
    if ImPlot.begin_plot("##Annotations"):
        ImPlot.setup_axes_limits(0, 2, 0, 1)
        p = [0.25, 0.25, 0.75, 0.75, 0.25]
        ImPlot.plot_scatter("##Points", p[0:4], p[1:5], 4)
        col = ImPlot.get_last_item_color()
        ImPlot.annotation(0.25, 0.25, col, (-15, 15), clamp, "BL")
        ImPlot.annotation(0.75, 0.25, col, (15, 15), clamp, "BR")
        ImPlot.annotation(0.75, 0.75, col, (15, -15), clamp, "TR")
        ImPlot.annotation(0.25, 0.75, col, (-15, -15), clamp, "TL")
        ImPlot.annotation(0.5, 0.5, col, (0, 0), clamp, "Center")
        ImPlot.annotation(1.25, 0.75, (0.0, 1.0, 0.0, 1.0), (0, 0), clamp)
        bx = [1.2, 1.5, 1.8]
        by = [0.25, 0.5, 0.75]
        ImPlot.plot_bars("##Bars", bx, by, 3, 0.2)
        for i in range(3):
            ImPlot.annotation(bx[i], by[i], (0.0, 0.0, 0.0, 0.0), (0, -5), clamp, "B[%d]=%.2f", i, by[i])
        ImPlot.end_plot()


def demo_tags() -> None:
    st = _s("tags", drag_tag=0.25)
    if ImPlot.begin_plot("##Tags"):
        ImPlot.setup_axis(ImPlot.AXIS_X2)
        ImPlot.setup_axis(ImPlot.AXIS_Y2)
        ImPlot.tag_x(0.25, (1.0, 1.0, 0.0, 1.0))
        ImPlot.tag_y(0.75, (1.0, 1.0, 0.0, 1.0))
        st["drag_tag"] = ImPlot.drag_line_y(0, st["drag_tag"], (1.0, 0.0, 0.0, 1.0), 1,
                                            ImPlot.DRAG_TOOL_FLAGS_NO_FIT).value
        ImPlot.tag_y(st["drag_tag"], (1.0, 0.0, 0.0, 1.0), "Drag")
        ImPlot.set_axes(ImPlot.AXIS_X2, ImPlot.AXIS_Y2)
        ImPlot.tag_x(0.5, (0.0, 1.0, 1.0, 1.0), "%s", "MyTag")
        ImPlot.tag_y(0.5, (0.0, 1.0, 1.0, 1.0), "Tag: %d", 42)
        ImPlot.end_plot()


def _saw_wave(idx, data):
    x_step, amp, freq, offset = data
    x = idx * x_step
    s = math.sin(3.14 * freq * x)
    return (x, offset + amp * (-2 / 3.14 * math.atan(math.cos(3.14 * freq * x) / s))) if s else (x, offset)


def demo_legend_options() -> None:
    st = _s("legend_options", loc=ImPlot.LOCATION_EAST, flags=0, dummies=5)
    if ImPlot.begin_plot("##Legend", (-1, 0)):
        ImPlot.setup_legend(st["loc"], st["flags"])
        ImPlot.plot_line_g("Item 002", _saw_wave, (0.001, 0.2, 4, 0.2), 1000)
        ImPlot.plot_line_g("Item 001##IDText", _saw_wave, (0.001, 0.2, 4, 0.4), 1000)
        ImPlot.plot_line_g("##NotListed", _saw_wave, (0.001, 0.2, 4, 0.6), 1000)
        ImPlot.plot_line_g("Item 003", _saw_wave, (0.001, 0.2, 4, 0.8), 1000)
        ImPlot.plot_line_g("Item 003", _saw_wave, (0.001, 0.2, 4, 1.0), 1000)
        for i in range(st["dummies"]):
            ImPlot.plot_dummy("Item %03d" % (i + 4))
        ImPlot.end_plot()


def demo_legend_popups() -> None:
    st = _s("legend_popups", frequency=0.1, amplitude=0.5, color=(1.0, 1.0, 0.0, 1.0), alpha=1.0, line=False,
            thickness=1.0, markers=False, shaded=False)
    vals = [st["amplitude"] * math.sin(st["frequency"] * i) for i in range(101)]
    if ImPlot.begin_plot("Right Click the Legend"):
        ImPlot.setup_axes_limits(0, 100, -1, 1)
        if not st["line"]:
            ImPlot.plot_bars("Right Click Me", vals, 101, 0.67, 0,
                             spec=ImPlot.PlotSpec(fill_alpha=st["alpha"], fill_color=st["color"]))
        else:
            ImPlot.plot_line("Right Click Me", vals, 101, 1, 0,
                             ImPlot.PlotSpec(line_color=st["color"], line_weight=st["thickness"]))
        if ImPlot.begin_legend_popup("Right Click Me"):
            _c, st["frequency"] = im.slider_float("Frequency", st["frequency"], 0, 1, "%0.2f")
            _c, st["amplitude"] = im.slider_float("Amplitude", st["amplitude"], 0, 1, "%0.2f")
            im.separator()
            _c, st["alpha"] = im.slider_float("Transparency", st["alpha"], 0, 1, "%.2f")
            _c, st["line"] = im.checkbox("Line Plot", st["line"])
            ImPlot.end_legend_popup()
        ImPlot.end_plot()


def demo_colormap_widgets() -> None:
    st = _s("colormap_widgets", cmap=ImPlot.COLORMAP_VIRIDIS, t=0.5, flags=0, scale=[0.0, 100.0])
    if ImPlot.colormap_button("Button", (0, 0), st["cmap"]):
        st["cmap"] = (st["cmap"] + 1) % ImPlot.get_colormap_count()
    _c, st["t"], _col = ImPlot.colormap_slider("Slider", st["t"], "%.3f", st["cmap"])
    ImPlot.colormap_icon(st["cmap"])
    im.same_line()
    im.text("Icon")
    ImPlot.colormap_scale("Scale", st["scale"][0], st["scale"][1], (0, 0), "%g dB", st["flags"], st["cmap"])


# --------------------------------------------------------------------------- #
# Custom
# --------------------------------------------------------------------------- #
def demo_custom_styles() -> None:
    ImPlot.push_colormap(ImPlot.COLORMAP_DEEP)
    style = ImPlot.get_style()
    backup = style.copy()
    _style_seaborn(style)
    if ImPlot.begin_plot("seaborn style"):
        ImPlot.setup_axes("x-axis", "y-axis")
        ImPlot.setup_axes_limits(-0.5, 9.5, 0, 10)
        lin = [8, 8, 9, 7, 8, 8, 8, 9, 7, 8]
        bar = [1, 2, 5, 3, 4, 1, 2, 5, 3, 4]
        dot = [7, 6, 6, 7, 8, 5, 6, 5, 8, 7]
        ImPlot.plot_bars("Bars", bar, 10, 0.5)
        ImPlot.plot_line("Line", lin, 10)
        ImPlot.next_colormap_color()
        ImPlot.plot_scatter("Scatter", dot, 10)
        ImPlot.end_plot()
    gp.style = backup
    ImPlot.pop_colormap()


def _style_seaborn(style) -> None:
    c = style.colors
    rg = ImPlot.I.rgba
    c[ImPlot.COL_FRAME_BG] = rg((1.0, 1.0, 1.0, 1.0))
    c[ImPlot.COL_PLOT_BG] = rg((0.92, 0.92, 0.95, 1.0))
    c[ImPlot.COL_PLOT_BORDER] = rg((0.0, 0.0, 0.0, 0.0))
    c[ImPlot.COL_LEGEND_BG] = rg((0.92, 0.92, 0.95, 1.0))
    c[ImPlot.COL_LEGEND_BORDER] = rg((0.80, 0.81, 0.85, 1.0))
    c[ImPlot.COL_LEGEND_TEXT] = rg((0.0, 0.0, 0.0, 1.0))
    c[ImPlot.COL_TITLE_TEXT] = rg((0.0, 0.0, 0.0, 1.0))
    c[ImPlot.COL_INLAY_TEXT] = rg((0.0, 0.0, 0.0, 1.0))
    c[ImPlot.COL_AXIS_TEXT] = rg((0.0, 0.0, 0.0, 1.0))
    c[ImPlot.COL_AXIS_GRID] = rg((1.0, 1.0, 1.0, 1.0))
    c[ImPlot.COL_AXIS_BG_HOVERED] = rg((0.92, 0.92, 0.95, 1.0))
    c[ImPlot.COL_AXIS_BG_ACTIVE] = rg((0.92, 0.92, 0.95, 0.75))
    c[ImPlot.COL_SELECTION] = rg((1.0, 0.65, 0.0, 1.0))
    c[ImPlot.COL_CROSSHAIRS] = rg((0.23, 0.10, 0.64, 0.50))
    style.mouse_pos_padding = (5.0, 5.0)
    style.plot_min_size = (300.0, 225.0)
    style.plot_border_size = 0.0
    style.minor_alpha = 1.0
    style.major_tick_len = (0.0, 0.0)
    style.minor_tick_len = (0.0, 0.0)
    style.major_tick_size = (0.0, 0.0)
    style.minor_tick_size = (0.0, 0.0)
    style.major_grid_size = (1.2, 1.2)
    style.minor_grid_size = (1.2, 1.2)
    style.plot_padding = (12.0, 12.0)
    style.label_padding = (5.0, 5.0)
    style.legend_padding = (5.0, 5.0)


def demo_custom_rendering() -> None:
    if ImPlot.begin_plot("##CustomRend"):
        cntr = ImPlot.plot_to_pixels(0.5, 0.5)
        rmin = ImPlot.plot_to_pixels(0.25, 0.75)
        rmax = ImPlot.plot_to_pixels(0.75, 0.25)
        ImPlot.push_plot_clip_rect()
        ImPlot.get_plot_draw_list().add_circle_filled(cntr, 20, (255, 255, 0, 255), 20)
        ImPlot.get_plot_draw_list().add_rect(rmin, rmax, (128, 0, 255, 255))
        ImPlot.pop_plot_clip_rect()
        ImPlot.end_plot()


def plot_candlestick(label_id, xs, opens, closes, lows, highs, count, tooltip=True, width_percent=0.25,
                     bull_col=(0.0, 1.0, 0.441, 1.0), bear_col=(0.853, 0.050, 0.310, 1.0)) -> None:
    """``MyImPlot::PlotCandlestick``, the demo's custom plotter, on emtk's
    ``begin_item``/``fit_point``/``get_plot_draw_list``."""
    draw_list = ImPlot.get_plot_draw_list()
    half_width = (xs[1] - xs[0]) * width_percent if count > 1 else width_percent
    if ImPlot.is_plot_hovered() and tooltip:
        mouse = ImPlot.get_plot_mouse_pos()
        mx = ImPlot.round_time(ImPlot.PlotTime.from_double(mouse.x), ImPlot.TIME_UNIT_DAY).to_double()
        tool_l = ImPlot.plot_to_pixels(mx - half_width * 1.5, mouse.y)[0]
        tool_r = ImPlot.plot_to_pixels(mx + half_width * 1.5, mouse.y)[0]
        tool_t = ImPlot.get_plot_pos()[1]
        tool_b = tool_t + ImPlot.get_plot_size()[1]
        ImPlot.push_plot_clip_rect()
        draw_list.add_rect_filled((tool_l, tool_t), (tool_r, tool_b), (128, 128, 128, 64))
        ImPlot.pop_plot_clip_rect()
    if _items.begin_item(label_id):
        gp.current_item.color = (64, 64, 64, 255)
        if _items.fit_this_frame():
            for i in range(count):
                _items.fit_point((xs[i], lows[i]))
                _items.fit_point((xs[i], highs[i]))
        bull, bear = ImPlot.I.rgba(bull_col), ImPlot.I.rgba(bear_col)
        for i in range(count):
            open_pos = ImPlot.plot_to_pixels(xs[i] - half_width, opens[i])
            close_pos = ImPlot.plot_to_pixels(xs[i] + half_width, closes[i])
            low_pos = ImPlot.plot_to_pixels(xs[i], lows[i])
            high_pos = ImPlot.plot_to_pixels(xs[i], highs[i])
            color = bear if opens[i] > closes[i] else bull
            draw_list.add_line(low_pos, high_pos, color)
            draw_list.add_rect_filled((min(open_pos[0], close_pos[0]), min(open_pos[1], close_pos[1])),
                                      (max(open_pos[0], close_pos[0]), max(open_pos[1], close_pos[1])), color)
        _items.end_item()


def demo_custom_plotters_and_tooltips() -> None:
    r = _rand(11)
    n = 218
    dates = []
    t = 1546300800.0
    while len(dates) < n:
        if _core_weekday(t) < 5:
            dates.append(t)
        t += 86400.0
    opens, closes, lows, highs = [], [], [], []
    price = 1284.7
    for _ in range(n):
        o = price
        c = o + r.gauss(0.5, 12.0)
        opens.append(o)
        closes.append(c)
        highs.append(max(o, c) + abs(r.gauss(0, 6)))
        lows.append(min(o, c) - abs(r.gauss(0, 6)))
        price = c
    if ImPlot.begin_plot("Candlestick Chart", (-1, 0)):
        ImPlot.setup_axes(None, None, 0, ImPlot.AXIS_FLAGS_AUTO_FIT | ImPlot.AXIS_FLAGS_RANGE_FIT)
        ImPlot.setup_axes_limits(1546300800, 1571961600, 1250, 1600)
        ImPlot.setup_axis_scale(ImPlot.AXIS_X1, ImPlot.SCALE_TIME)
        ImPlot.setup_axis_limits_constraints(ImPlot.AXIS_X1, 1546300800, 1571961600)
        ImPlot.setup_axis_zoom_constraints(ImPlot.AXIS_X1, 60 * 60 * 24 * 14, 1571961600 - 1546300800)
        ImPlot.setup_axis_format(ImPlot.AXIS_Y1, "$%.0f")
        plot_candlestick("GOOGL", dates, opens, closes, lows, highs, n, True, 0.25)
        ImPlot.end_plot()


def _core_weekday(t: float) -> int:
    import time
    return time.gmtime(t).tm_wday


# --------------------------------------------------------------------------- #
# The demo window
# --------------------------------------------------------------------------- #
DEMOS = {
    "Plots": [("Line Plots", demo_line_plots), ("Filled Line Plots", demo_filled_line_plots),
              ("Shaded Plots", demo_shaded_plots), ("Scatter Plots", demo_scatter_plots),
              ("Bubble Plots", demo_bubble_plots), ("Polygon Plots", demo_polygon_plots),
              ("Realtime Plots", demo_realtime_plots), ("Stairstep Plots", demo_stairstep_plots),
              ("Bar Plots", demo_bar_plots), ("Bar Groups", demo_bar_groups), ("Bar Stacks", demo_bar_stacks),
              ("Error Bars", demo_error_bars), ("Stem Plots", demo_stem_plots),
              ("Infinite Lines", demo_infinite_lines), ("Pie Charts", demo_pie_charts),
              ("Heatmaps", demo_heatmaps), ("Histogram", demo_histogram), ("Histogram 2D", demo_histogram_2d),
              ("Digital Plots", demo_digital_plots), ("Images", demo_images),
              ("Markers and Text", demo_markers_and_text), ("NaN Values", demo_nan_values),
              ("Per-Index Colors", demo_per_index_colors)],
    "Subplots": [("Sizing", demo_subplots_sizing), ("Item Sharing", demo_subplot_item_sharing),
                 ("Axis Linking", demo_subplot_axis_linking), ("Tables", demo_tables)],
    "Axes": [("Log Scale", demo_log_scale), ("Symmetric Log Scale", demo_symmetric_log_scale),
             ("Time Scale", demo_time_scale), ("Custom Scale", demo_custom_scale),
             ("Multiple Axes", demo_multiple_axes), ("Tick Labels", demo_tick_labels),
             ("Linked Axes", demo_linked_axes), ("Axis Constraints", demo_axis_constraints),
             ("Equal Axes", demo_equal_axes), ("Auto-Fitting Data", demo_auto_fitting_data)],
    "Tools": [("Item Styling and Spec", demo_item_styling_and_spec), ("Offset and Stride", demo_offset_and_stride),
              ("Drag Points", demo_drag_points), ("Drag Lines", demo_drag_lines),
              ("Drag Rects", demo_drag_rects), ("Querying", demo_querying), ("Annotations", demo_annotations),
              ("Tags", demo_tags), ("Legend Options", demo_legend_options),
              ("Legend Popups", demo_legend_popups), ("Colormap Widgets", demo_colormap_widgets)],
    "Custom": [("Custom Styles", demo_custom_styles), ("Custom Rendering", demo_custom_rendering),
               ("Custom Plotters and Tooltips", demo_custom_plotters_and_tooltips)],
}


def show_demo_window() -> None:
    """``ShowDemoWindow``: the sections as tree nodes, one tab bar per group."""
    im.text("ImPlot says hello! (emtk port of 1.1 WIP)")
    for tab, demos in DEMOS.items():
        if im.collapsing_header(tab):
            for label, demo in demos:
                if im.tree_node(label):
                    demo()
                    im.tree_pop()


def _demo_gui() -> None:
    """The demo window, filling the host's surface -- the gui of :func:`make_app`."""
    from .im_core import get_current_context  # noqa: PLC0415

    x, y, w, h = get_current_context().box
    im.begin("ImPlot Demo", (x + 8.0, y + 8.0, max(w - 16.0, 100.0), max(h - 16.0, 100.0)))
    # One live plot up front, so the page shows a plot before any click; the
    # reference's sections follow, as its ShowDemoWindow lays them out.
    demo_line_plots()
    show_demo_window()
    im.end()


def make_app():
    """ImPlot's demo as an emtk app, for any GPU host.

    ::

        python -m emtk.web.serve --app emtk.implot_demo:make_app
        python -m emtk.native --app emtk.implot_demo:make_app

    Continuous frames, because several demos animate with the clock.
    """
    from .app import ImApp  # noqa: PLC0415

    return ImApp(_demo_gui, continuous=True)
