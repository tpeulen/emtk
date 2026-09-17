"""The ImPlot items ported in PRD Phase 2 breadth: each draws what it plots.

Pixel assertions read a :class:`PixelPainter`; call assertions read a
:class:`RecordingPainter`. Positions are computed through the plot's own
axes, so a test says "the stem reaches y = 1" rather than a magic pixel.
"""
from __future__ import annotations

import math

import pytest

import emtk
from emtk import implot
from emtk.testing import PixelPainter, RecordingPainter


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []
    while implot._cur.colormap_modifiers:
        implot.pop_colormap()


def _draw(gui, painter=None, w=520, h=360, frames=1):
    storage, io = {}, emtk.IO()
    seen = {}
    p = None
    for _ in range(frames):
        p = painter or PixelPainter(w, h, background=(0, 0, 0, 255))
        with emtk.frame(p, (0, 0, w, h), io=io, storage=storage):
            emtk.begin("w")
            gui(seen)
            emtk.end()
    return p, seen


def _begin(seen, limits=(0, 10, 0, 10), flags=implot.FLAGS_NO_LEGEND | implot.FLAGS_NO_TITLE):
    implot.begin_plot("##t", (500, 340), flags)
    implot.setup_axes(None, None, implot.AXIS_FLAGS_NO_DECORATIONS, implot.AXIS_FLAGS_NO_DECORATIONS)
    if limits is not None:
        implot.setup_axes_limits(*limits, implot.COND_ALWAYS)


def _end(seen):
    seen["to_px"] = [(ax.pixel_min, ax.pixel_max, ax.range_min, ax.range_max)
                     for ax in implot._cur.plot.axes]
    implot.end_plot()
    seen["plot"] = implot._cur.last_plot


def _px(seen, x, y):
    plot = seen["plot"]
    return (plot.axes[implot.AXIS_X1].plot_to_pixels(x), plot.axes[implot.AXIS_Y1].plot_to_pixels(y))


def _rgb(p, x, y):
    i = (int(y) * p.width + int(x)) * 4
    return tuple(p.px[i:i + 3])


RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)


def test_stems_run_from_the_reference_to_the_value():
    def gui(seen):
        _begin(seen)
        implot.plot_stems("s", [2.0, 5.0], [8.0, 4.0], 2, 1.0, implot.PlotSpec(line_color=RED, line_weight=3))
        _end(seen)

    p, seen = _draw(gui)
    x, y_top = _px(seen, 2.0, 8.0)
    _x, y_ref = _px(seen, 2.0, 1.0)
    assert _rgb(p, x, (y_top + y_ref) / 2) == (255, 0, 0)
    assert _rgb(p, x, y_ref + 10) == (0, 0, 0) or _rgb(p, x, y_ref + 10) != (255, 0, 0)
    assert _rgb(p, x, y_top - 10) != (255, 0, 0)


def test_horizontal_stems_run_along_x():
    def gui(seen):
        _begin(seen)
        implot.plot_stems("s", [6.0], 1, 0.0, 1.0, 5.0,
                          implot.PlotSpec(line_color=RED, line_weight=3, flags=implot.STEMS_FLAGS_HORIZONTAL))
        _end(seen)

    p, seen = _draw(gui)
    x0, y = _px(seen, 0.0, 5.0)
    x1, _ = _px(seen, 6.0, 5.0)
    assert _rgb(p, (x0 + x1) / 2, y) == (255, 0, 0)
    assert _rgb(p, x1 + 20, y) != (255, 0, 0)


@pytest.mark.parametrize("pre", [False, True])
def test_stairs_step_after_or_before_each_sample(pre):
    flags = implot.STAIRS_FLAGS_PRE_STEP if pre else 0

    def gui(seen):
        _begin(seen)
        implot.plot_stairs("s", [2.0, 6.0], [2.0, 8.0], 2, implot.PlotSpec(line_color=RED, line_weight=3,
                                                                            flags=flags))
        _end(seen)

    p, seen = _draw(gui)
    xm, _ = _px(seen, 4.0, 0.0)
    _, y_low = _px(seen, 0.0, 2.0)
    _, y_high = _px(seen, 0.0, 8.0)
    # post-step holds y = 2 until x = 6; pre-step already holds y = 8
    assert _rgb(p, xm, y_high if pre else y_low) == (255, 0, 0)
    assert _rgb(p, xm, y_low if pre else y_high) != (255, 0, 0)


def test_shaded_stairs_fill_down_to_zero():
    def gui(seen):
        _begin(seen, limits=(0, 10, -2, 10))
        implot.plot_stairs("s", [2.0, 6.0], [5.0, 5.0], 2, implot.PlotSpec(
            line_color=(0, 0, 0, 0), fill_color=GREEN, flags=implot.STAIRS_FLAGS_SHADED))
        _end(seen)

    p, seen = _draw(gui)
    x, y = _px(seen, 4.0, 2.5)
    assert _rgb(p, x, y) == (0, 255, 0)
    x, y = _px(seen, 4.0, -1.0)
    assert _rgb(p, x, y) != (0, 255, 0)


def test_vertical_error_bars_have_whiskers_of_size():
    rec = RecordingPainter()

    def gui(seen):
        _begin(seen)
        implot.plot_error_bars("e", [5.0], [5.0], [2.0], 1, implot.PlotSpec(line_color=RED, size=10))
        _end(seen)

    _p, seen = _draw(gui, painter=rec)
    x, y_hi = _px(seen, 5.0, 7.0)
    whiskers = [f for f in rec.fills if f[4][:3] == (255, 0, 0) and abs(f[2] - 10) < 1e-6]
    assert len(whiskers) == 2
    assert any(abs(f[1] + 0.5 - y_hi) < 1.0 for f in whiskers)


def test_horizontal_error_bars_with_asymmetric_errors():
    def gui(seen):
        _begin(seen)
        implot.plot_error_bars("e", [5.0], [5.0], [1.0], [3.0], 1, implot.PlotSpec(
            line_color=RED, line_weight=3, flags=implot.ERROR_BARS_FLAGS_HORIZONTAL))
        _end(seen)

    p, seen = _draw(gui)
    _, y = _px(seen, 0, 5.0)
    assert _rgb(p, _px(seen, 7.5, 5.0)[0], y) == (255, 0, 0)
    assert _rgb(p, _px(seen, 3.5, 5.0)[0], y) != (255, 0, 0)


def test_bar_groups_side_by_side_and_stacked():
    def gui_groups(seen):
        _begin(seen, limits=(-1, 3, 0, 10))
        implot.push_colormap([RED, GREEN])
        implot.plot_bar_groups(["a", "b"], [[4, 4, 4], [8, 8, 8]], 2, 3, 0.8, 0,
                               implot.PlotSpec(fill_alpha=1.0))
        implot.pop_colormap()
        _end(seen)

    p, seen = _draw(gui_groups)
    # item a on the left half of group 0, item b on the right half
    assert _rgb(p, *_px(seen, -0.2, 2.0)) == (255, 0, 0)
    assert _rgb(p, *_px(seen, 0.2, 6.0)) == (0, 255, 0)
    assert _rgb(p, *_px(seen, -0.2, 6.0)) != (255, 0, 0)

    def gui_stacked(seen):
        _begin(seen, limits=(-1, 3, 0, 14))
        implot.push_colormap([RED, GREEN])
        implot.plot_bar_groups(["a", "b"], [[4, 4, 4], [8, 8, 8]], 2, 3, 0.8, 0,
                               implot.PlotSpec(flags=implot.BAR_GROUPS_FLAGS_STACKED))
        implot.pop_colormap()
        _end(seen)

    p, seen = _draw(gui_stacked)
    assert _rgb(p, *_px(seen, 0.0, 2.0)) == (255, 0, 0)
    assert _rgb(p, *_px(seen, 0.0, 10.0)) == (0, 255, 0)     # stacked on top: 4..12
    assert _rgb(p, *_px(seen, 0.0, 13.0)) not in ((255, 0, 0), (0, 255, 0))


def test_filled_bars_and_the_horizontal_overload():
    def gui(seen):
        _begin(seen, limits=(-1, 10, -1, 10))
        implot.plot_bars("v", [5.0], 1, 1.0, 0, implot.PlotSpec(fill_color=RED))
        implot.plot_bars("h", [7.0], 1, 1.0, 8, implot.PlotSpec(fill_color=GREEN,
                                                                 flags=implot.BARS_FLAGS_HORIZONTAL))
        _end(seen)

    p, seen = _draw(gui)
    assert _rgb(p, *_px(seen, 0.2, 2.5)) == (255, 0, 0)
    assert _rgb(p, *_px(seen, 3.5, 8.2)) == (0, 255, 0)


def test_digital_signals_stack_from_the_bottom_ignoring_y():
    rec = RecordingPainter()

    def gui(seen):
        _begin(seen, limits=(0, 10, 100, 200))
        implot.plot_digital("d0", [0, 5, 10], [1, 0, 1], 3, implot.PlotSpec(fill_color=RED, size=8))
        implot.plot_digital("d1", [0, 5, 10], [1, 1, 1], 3, implot.PlotSpec(fill_color=GREEN, size=8))
        _end(seen)

    _p, seen = _draw(gui, painter=rec)
    red = [f for f in rec.fills if f[4][:3] == (255, 0, 0)]
    green = [f for f in rec.fills if f[4][:3] == (0, 255, 0)]
    bottom = seen["plot"].plot_rect[3]
    assert red and green
    assert max(f[1] + f[3] for f in red) == pytest.approx(bottom - 20, abs=1)   # DigitalPadding
    assert max(f[1] + f[3] for f in green) < min(f[1] for f in red) + 1, "d1 did not stack above d0"


def test_pie_chart_slices_and_labels():
    rec = RecordingPainter()

    def gui(seen):
        implot.begin_plot("##pie", (300, 300), implot.FLAGS_EQUAL | implot.FLAGS_NO_MOUSE_TEXT)
        implot.setup_axes(None, None, implot.AXIS_FLAGS_NO_DECORATIONS, implot.AXIS_FLAGS_NO_DECORATIONS)
        implot.setup_axes_limits(0, 1, 0, 1)
        implot.plot_pie_chart(["A", "B", "C"], [1, 1, 2], 3, 0.5, 0.5, 0.4, "%.0f", 90)
        seen["legend"] = [i.label for i in implot._cur.plot.items.items]
        implot.end_plot()

    _p, seen = _draw(gui, painter=rec)
    assert seen["legend"] == ["A", "B", "C"]
    assert sum(1 for s in rec.strings if s in ("1", "2")) == 3
    assert len(rec.triangles) > 30


def test_pie_chart_normalizes_only_when_the_sum_exceeds_one():
    def bottom_of_pie(values):
        def gui(seen):
            _begin(seen, limits=(0, 1, 0, 1))
            implot.plot_pie_chart(["A", "B"], values, 2, 0.5, 0.5, 0.4, None, 0)
            _end(seen)

        p, seen = _draw(gui)
        return _rgb(p, *_px(seen, 0.5, 0.2))

    # 0.25 + 0.25 draws a half pie (0..180 degrees): the bottom stays empty;
    # 1 + 1 sums past one and is normalized into a whole pie
    assert bottom_of_pie([0.25, 0.25]) == (0, 0, 0) or sum(bottom_of_pie([0.25, 0.25])) < 60
    assert sum(bottom_of_pie([1, 1])) > 100


def test_text_is_centred_on_its_point_and_can_be_vertical():
    rec = RecordingPainter()

    def gui(seen):
        _begin(seen)
        implot.plot_text("hello", 5.0, 5.0)
        implot.plot_text("up", 2.0, 2.0, (0, 0), implot.PlotSpec(flags=implot.TEXT_FLAGS_VERTICAL))
        _end(seen)

    _p, seen = _draw(gui, painter=rec)
    hello = [t for t in rec.texts if t[5] == "hello"][0]
    cx, cy = _px(seen, 5.0, 5.0)
    assert hello[0] + hello[2] / 2 == pytest.approx(cx, abs=1.0)
    assert hello[1] + hello[3] / 2 == pytest.approx(cy, abs=1.0)
    assert "up" in rec.strings


def test_vertical_text_is_turned_on_the_pixel_painter():
    def gui(seen):
        _begin(seen)
        implot.plot_text("VERTICAL", 5.0, 5.0, (0, 0), implot.PlotSpec(flags=implot.TEXT_FLAGS_VERTICAL))
        _end(seen)

    p, seen = _draw(gui)
    cx, cy = _px(seen, 5.0, 5.0)
    lit = [(x, y) for y in range(int(cy) - 60, int(cy) + 60) for x in range(int(cx) - 60, int(cx) + 60)
           if p.px[(y * p.width + x) * 4] > 128]
    assert lit
    xs, ys = [x for x, _ in lit], [y for _, y in lit]
    assert max(ys) - min(ys) > 2 * (max(xs) - min(xs)), "the text was not turned"


def test_image_fills_its_bounds():
    from emtk.texture import Texture
    tex = Texture(2, 2, bytes([255, 0, 0, 255] * 4))

    def gui(seen):
        _begin(seen)
        implot.plot_image("img", tex, (2, 2), (4, 6))
        _end(seen)

    p, seen = _draw(gui)
    assert _rgb(p, *_px(seen, 3.0, 4.0)) == (255, 0, 0)
    assert _rgb(p, *_px(seen, 5.0, 4.0)) != (255, 0, 0)


def test_dummy_adds_a_legend_entry_and_draws_nothing():
    rec = RecordingPainter()

    def gui(seen):
        implot.begin_plot("##d", (400, 300))
        implot.setup_axes_limits(0, 1, 0, 1)
        implot.plot_dummy("only in the legend", implot.PlotSpec(line_color=RED))
        seen["records"] = list(implot._cur.plot.records)
        implot.end_plot()

    _p, seen = _draw(gui, painter=rec)
    assert "only in the legend" in rec.strings
    assert seen["records"] == []
    assert any(f[4][:3] == (255, 0, 0) for f in rec.fills), "no red legend icon"


def test_every_marker_shape_draws():
    rec = RecordingPainter()

    def gui(seen):
        _begin(seen)
        for m in range(implot.MARKER_COUNT):
            implot.plot_scatter(f"##{m}", [1.0 + m * 0.7], [5.0], 1, implot.PlotSpec(marker=m, marker_size=6))
        _end(seen)

    _p, seen = _draw(gui, painter=rec)
    for m in range(implot.MARKER_COUNT):
        cx, cy = _px(seen, 1.0 + m * 0.7, 5.0)
        near = [t for t in rec.triangles if all(abs(pt[0] - cx) < 9 and abs(pt[1] - cy) < 9 for pt in t[:3])]
        assert near, f"marker {implot.get_marker_name(m)} drew nothing"


def test_line_flags_segments_loop_and_skip_nan():
    rec_seg, rec_loop, rec_skip, rec_gap = (RecordingPainter() for _ in range(4))

    def gui_for(xs, ys, flags):
        def gui(seen):
            _begin(seen)
            implot.plot_line("l", xs, ys, len(xs), implot.PlotSpec(flags=flags))
            _end(seen)
        return gui

    xs, ys = [1, 3, 5, 7], [1, 3, 1, 3]
    _draw(gui_for(xs, ys, implot.LINE_FLAGS_SEGMENTS), painter=rec_seg)
    _draw(gui_for(xs, ys, implot.LINE_FLAGS_LOOP), painter=rec_loop)
    assert len(rec_seg.triangles) == 4       # two segments, two triangles each
    assert len(rec_loop.triangles) == 8      # three segments plus the closing one
    ys_nan = [1, math.nan, 1, 3]
    _draw(gui_for(xs, ys_nan, implot.LINE_FLAGS_SKIP_NAN), painter=rec_skip)
    _draw(gui_for(xs, ys_nan, 0), painter=rec_gap)
    assert len(rec_gap.triangles) == 2       # only 5 -> 7 survives the gap
    assert len(rec_skip.triangles) == 4      # 1 -> 5 is joined across the NaN


def test_line_shaded_flag_fills_to_zero():
    def gui(seen):
        _begin(seen, limits=(0, 10, -5, 10))
        implot.plot_line("l", [0, 10], [5, 5], 2, implot.PlotSpec(
            line_color=RED, fill_color=GREEN, flags=implot.LINE_FLAGS_SHADED))
        _end(seen)

    p, seen = _draw(gui)
    assert _rgb(p, *_px(seen, 5.0, 2.5)) == (0, 255, 0)
    assert _rgb(p, *_px(seen, 5.0, -2.5)) != (0, 255, 0)


def test_per_index_line_colours():
    rec = RecordingPainter()

    def gui(seen):
        _begin(seen)
        implot.plot_line("l", [1, 5, 9], [5, 5, 5], 3, implot.PlotSpec(line_colors=[RED, GREEN, RED]))
        _end(seen)

    _draw(gui, painter=rec)
    colours = [t[3][:3] for t in rec.triangles]
    assert (255, 0, 0) in colours and (0, 255, 0) in colours


def test_hidden_items_are_neither_drawn_nor_fit():
    def gui(seen):
        implot.begin_plot("##h", (400, 300), implot.FLAGS_NO_LEGEND)
        implot.hide_next_item(True, implot.COND_ALWAYS)
        implot.plot_line("big", [0, 100], [0, 100])
        implot.plot_line("small", [0, 1], [0, 1])
        seen["records"] = [r["label"] for r in implot._cur.plot.records]
        implot.end_plot()
        seen["limits"] = implot.get_plot_limits()

    _p, seen = _draw(gui, painter=RecordingPainter())
    assert seen["records"] == ["small"]
    assert seen["limits"].x_max == pytest.approx(1.0)


def test_histogram_bins_methods_density_and_cumulative():
    values = [float(i % 10) for i in range(1000)]
    seen_max = {}

    def gui(seen):
        implot.begin_plot("##h", (400, 300))
        seen_max["counts"] = implot.plot_histogram("h", values, 1000, 10)
        seen_max["sturges"] = implot._cur.plot.records[-1]["pts1"]
        implot.plot_histogram("d", values, 1000, 10, 1.0, None,
                              implot.PlotSpec(flags=implot.HISTOGRAM_FLAGS_DENSITY))
        seen_max["cum"] = implot.plot_histogram("c", values, 1000, 10, 1.0, None,
                                                implot.PlotSpec(flags=implot.HISTOGRAM_FLAGS_CUMULATIVE))
        seen_max["bins_sqrt"] = len(implot._cur.plot.records[-1]["pts1"])
        implot.plot_histogram("s", values, 1000, implot.BIN_SQRT)
        seen_max["sqrt"] = len(implot._cur.plot.records[-1]["pts1"])
        implot.end_plot()

    _draw(gui, painter=RecordingPainter())
    assert seen_max["counts"] == pytest.approx(100.0)
    assert seen_max["cum"] == pytest.approx(1000.0)
    assert seen_max["sqrt"] == math.ceil(math.sqrt(1000))


def test_histogram_2d_returns_the_largest_bin():
    xs = [0.5] * 30 + [1.5] * 10
    ys = [0.5] * 30 + [1.5] * 10
    out = {}

    def gui(seen):
        implot.begin_plot("##h2", (400, 300))
        out["max"] = implot.plot_histogram_2d("h", xs, ys, 40, 2, 2, (0, 2, 0, 2))
        implot.end_plot()

    _draw(gui, painter=RecordingPainter())
    assert out["max"] == pytest.approx(30.0)


def test_bubbles_have_radius_in_plot_units():
    def gui(seen):
        _begin(seen)
        implot.plot_bubbles("b", [5.0], [5.0], [2.0], 1, implot.PlotSpec(fill_color=RED, line_color=RED))
        _end(seen)

    p, seen = _draw(gui)
    assert _rgb(p, *_px(seen, 6.5, 5.0)) == (255, 0, 0)
    assert _rgb(p, *_px(seen, 7.6, 5.0)) != (255, 0, 0)


def test_polygon_concave_fill():
    star = [(5 + (4 if i % 2 == 0 else 1.5) * math.cos(i * math.pi / 5 - math.pi / 2),
             5 + (4 if i % 2 == 0 else 1.5) * math.sin(i * math.pi / 5 - math.pi / 2)) for i in range(10)]

    def gui(seen):
        _begin(seen)
        implot.plot_polygon("star", [p[0] for p in star], [p[1] for p in star], 10,
                            implot.PlotSpec(fill_color=GREEN, line_color=(0, 0, 0, 0),
                                            flags=implot.POLYGON_FLAGS_CONCAVE))
        _end(seen)

    p, seen = _draw(gui)
    assert _rgb(p, *_px(seen, 5.0, 5.0)) == (0, 255, 0)
    # between two spikes, inside the convex hull but outside the star
    between = (5 + 3.0 * math.cos(math.pi / 5 - math.pi / 2), 5 + 3.0 * math.sin(math.pi / 5 - math.pi / 2))
    assert _rgb(p, *_px(seen, *between)) != (0, 255, 0)


def test_annotations_and_tags_draw_their_text():
    rec = RecordingPainter()

    def gui(seen):
        implot.begin_plot("##a", (400, 300), implot.FLAGS_NO_LEGEND)
        implot.setup_axes_limits(0, 1, 0, 1, implot.COND_ALWAYS)
        implot.annotation(0.5, 0.5, (1.0, 0.0, 0.0, 1.0), (10, 10), False, "note %d", 7)
        implot.annotation(0.25, 0.25, (1.0, 0.0, 0.0, 1.0), (0, 0), True)
        implot.tag_x(0.5, (0.0, 1.0, 0.0, 1.0), "X!")
        implot.tag_y(0.5, (0.0, 1.0, 0.0, 1.0))
        implot.end_plot()

    _draw(gui, painter=rec)
    assert {"note 7", "X!"} <= set(rec.strings)
    assert "0.25, 0.25" in rec.strings
    assert "0.5" in rec.strings


def test_colormaps_are_all_there_and_sample_like_the_reference():
    rec = RecordingPainter()
    names = []

    def gui(seen):
        for i in range(16):
            names.append(implot.get_colormap_name(i))
        seen["jet0"] = implot.sample_colormap(0.0, implot.COLORMAP_JET)
        seen["jet1"] = implot.sample_colormap(1.0, "Jet")
        seen["deep1"] = implot.get_colormap_color(1, implot.COLORMAP_DEEP)
        implot.colormap_scale("scale", 0, 10, (0, 200))
        seen["btn"] = implot.colormap_button("Hot", (100, 0), implot.COLORMAP_HOT)
        seen["slider"] = implot.colormap_slider("t", 0.5, "", implot.COLORMAP_GREYS)

    _p, seen = _draw(gui, painter=rec)
    assert names == ["Deep", "Dark", "Pastel", "Paired", "Viridis", "Plasma", "Hot", "Cool", "Pink", "Jet",
                     "Twilight", "RdBu", "BrBG", "PiYG", "Spectral", "Greys"]
    assert seen["jet0"] == pytest.approx((0.0, 0.0, 170 / 255, 1.0))
    assert seen["jet1"] == pytest.approx((1.0, 0.0, 0.0, 1.0))
    assert seen["deep1"] == pytest.approx((221 / 255, 132 / 255, 82 / 255, 1.0))
    assert "scale" in rec.strings or any(t[5] == "10" for t in rec.texts)
    changed, t, col = seen["slider"]
    assert t == 0.5 and col[0] == pytest.approx(0.5, abs=0.01)
    idx = implot.add_colormap("mine", [RED, GREEN], qual=False)
    assert implot.get_colormap_index("mine") == idx and implot.get_colormap_size(idx) == 2
