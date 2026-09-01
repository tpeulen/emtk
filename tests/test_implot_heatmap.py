"""``implot.plot_heatmap`` -- the cells, where they land, and what they say.

A heatmap is the one plot type whose whole content is colour and position, so
the tests here read pixels rather than call counts: a cell drawn in the wrong
place, the wrong way up, or the wrong colour is a picture of data that does
not exist, and nothing about the call would have raised.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk import implot
from cmtk.testing import PixelPainter, RecordingPainter


@pytest.fixture(autouse=True)
def _no_module_state_left_over():
    """A test that fails between begin_plot and end_plot -- or after a
    push_colormap -- leaves the module state set, and every later test then
    fails for the wrong reason."""
    yield
    implot._cur.plot = None
    implot._cur.colormap = None


def _frame(fn, painter=None, w=400, h=300):
    p = painter or PixelPainter(w, h, background=(30, 32, 38, 255))
    with cmtk.frame(p, (8, 8, w - 16, h - 16), io=cmtk.IO(), storage={}):
        cmtk.begin("w")
        fn()
        cmtk.end()
    return p


def _px(p, x, y):
    i = (int(y) * p.width + int(x)) * 4
    return tuple(p.px[i:i + 4])


def _luma(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _cell_centre(box, rows, cols, i, j):
    """The pixel at the middle of cell (row ``i``, column ``j``), for a
    heatmap whose bounds fill the auto-fitted axes exactly."""
    x, y, w, h = box
    return x + w * (j + 0.5) / cols, y + h * (i + 0.5) / rows


def _draw(values, rows, cols, *args, size=(360, 240), **kw):
    """Draw one heatmap and hand back the painter and the plot box."""
    seen = {}

    def gui():
        implot.begin_plot("##t", size)
        implot.plot_heatmap("##h", values, rows, cols, *args, **kw)
        seen["box"] = implot._cur.box
        implot.end_plot()

    return _frame(gui), seen["box"]


def test_a_high_cell_is_not_the_colour_of_a_low_one():
    """The whole content of a heatmap is that colour tracks value. Map every
    cell to the same colour -- an unscaled ramp, a division by a zero span --
    and the picture is a flat rectangle that still passes any "did it draw"
    check."""
    p, box = _draw([0.0, 1.0, 2.0, 3.0], 2, 2, 0, 0, None)
    low = _px(p, *_cell_centre(box, 2, 2, 0, 0))
    high = _px(p, *_cell_centre(box, 2, 2, 1, 1))
    assert low != high
    # ...and in the direction the ramp promises: dark for small, bright for
    # large. A reversed ramp reads every heatmap backwards.
    assert _luma(low) < _luma(high)


def test_the_first_row_is_drawn_at_the_top():
    """The reference lays row zero against ``bounds_max``'s y and works
    downward. Indexed the other way the picture is flipped -- a plot of
    different data, drawn with total confidence."""
    p, box = _draw([0.0, 0.0, 9.0, 9.0], 2, 2, 0, 0, None)
    top = _px(p, *_cell_centre(box, 2, 2, 0, 0))
    bottom = _px(p, *_cell_centre(box, 2, 2, 1, 0))
    assert _luma(top) < _luma(bottom), "row zero did not land at the top"


def test_the_cells_land_where_the_bounds_say():
    """``bounds_min``/``bounds_max`` are in plot coordinates, so a grid that
    covers half the axis range must cover half the box. Drawn in pixels
    instead -- box divided by cols -- it would fill the whole plot and no
    single-heatmap test would notice."""
    seen = {}

    def gui():
        implot.begin_plot("##t", (360, 240))
        # axes twice the size of the grid, so the grid must fill a quarter
        implot.setup_axes_limits(0.0, 2.0, 0.0, 2.0, implot.COND_ALWAYS)
        implot.plot_heatmap("##h", [5.0], 1, 1, 0, 10.0, None, (0.0, 0.0), (1.0, 1.0))
        seen["box"] = implot._cur.box
        implot.end_plot()

    p = _frame(gui)
    x, y, w, h = seen["box"]
    inside = _px(p, x + w * 0.25, y + h * 0.75)      # inside (0,0)-(1,1)
    outside = _px(p, x + w * 0.75, y + h * 0.25)     # beyond it
    assert inside != outside, "the cell was not confined to its bounds"
    assert _luma(inside) > _luma(outside)


def test_autoscale_is_not_the_same_picture_as_an_explicit_range():
    """``scale_min == scale_max == 0`` is the reference's sentinel for "fit
    the ramp to the data". Ignore it and every heatmap of small numbers is a
    single dark rectangle; honour it always and an explicit range asked for
    to compare two frames is thrown away."""
    values = [0.0, 1.0, 2.0, 3.0]
    auto, box = _draw(values, 2, 2, 0, 0, None)
    fixed, _ = _draw(values, 2, 2, 0.0, 300.0, None)
    at = _cell_centre(box, 2, 2, 1, 1)
    assert _px(auto, *at) != _px(fixed, *at)
    # autoscale puts the largest sample at the top of the ramp; a range ten
    # times too wide leaves it in the dark half
    assert _luma(_px(auto, *at)) > _luma(_px(fixed, *at))


def test_a_flat_range_does_not_divide_by_zero():
    """``scale_min == scale_max`` (or every cell equal) has no gradient to
    show. The reference divides by the span; here it would raise mid-frame
    and take the window with it."""
    p, box = _draw([4.0, 4.0], 1, 2, 4.0, 4.0, None)
    a = _px(p, *_cell_centre(box, 1, 2, 0, 0))
    b = _px(p, *_cell_centre(box, 1, 2, 0, 1))
    assert a == b and a[3] == 255


def test_neighbouring_cells_leave_no_seam():
    """Both edges of a cell are rounded onto the same pixel grid. Round the
    origin only and keep a fractional width and a one-pixel background seam
    shows between neighbours -- which reads as a grid the data does not
    have."""
    p, box = _draw([0.0, 1.0], 1, 2, 0, 0, None)
    x, y, w, h = box
    row = y + h * 0.5
    colours = {_px(p, px, row) for px in range(int(x) + 2, int(x + w) - 2)}
    assert len(colours) == 2, f"a seam or a gap between the cells: {colours}"


def test_a_cell_outside_the_axis_limits_is_clipped():
    """Cells are drawn inside the clip ``Plot`` pushes around its box, as the
    line series are. Drawn outside it, a grid whose bounds run past pinned
    axis limits paints over the tick labels and the neighbouring widgets."""
    seen = {}

    def gui():
        implot.begin_plot("##t", (360, 240))
        implot.setup_axes_limits(0.0, 1.0, 0.0, 1.0, implot.COND_ALWAYS)
        implot.plot_heatmap("##h", [0.0, 1.0, 2.0, 3.0], 2, 2, 0, 0, None,
                            (0.0, 0.0), (10.0, 10.0))
        seen["box"] = implot._cur.box
        implot.end_plot()

    p = _frame(gui)
    x, y, w, h = seen["box"]
    cell_colours = {implot._ramp_colour(implot.VIRIDIS_COLORMAP, t)
                    for t in (0.0, 1 / 3, 2 / 3, 1.0)}
    assert _px(p, x + w * 0.5, y + h * 0.5) in cell_colours, "nothing drawn"
    escaped = [(px, py) for py in range(p.height) for px in range(p.width)
               if not (x <= px < x + w and y <= py < y + h)
               and _px(p, px, py) in cell_colours]
    assert not escaped, f"{len(escaped)} cell pixels outside the plot box"


def test_the_labels_are_drawn_only_when_a_format_is_given():
    """``label_fmt`` is ``None`` for the fine grids that have no room for a
    number in a cell -- ImPlot's own default of "%.1f" would paint mush over
    a 64x64 histogram -- and a format string when the caller wants to read
    the values off."""
    def gui(fmt):
        def inner():
            implot.begin_plot("##t", (360, 240))
            implot.plot_heatmap("##h", [7.0, 13.0, 21.0, 42.0], 2, 2, 0, 0, fmt)
            implot.end_plot()
        return inner

    with_labels = _frame(gui("%.0f"), painter=RecordingPainter())
    assert "42" in with_labels.strings
    without = _frame(gui(None), painter=RecordingPainter())
    assert "42" not in without.strings
    assert "" not in without.strings, "an empty label was drawn per cell"


def test_a_label_stays_legible_on_a_bright_cell():
    """The reference paints inlay text in one fixed colour; on the bright end
    of a perceptual ramp that is white on pale yellow. Read off the cell
    colour instead, or the labels the caller asked for cannot be read."""
    rec = RecordingPainter()

    def gui():
        implot.begin_plot("##t", (360, 240))
        implot.plot_heatmap("##h", [0.0, 100.0], 1, 2, 0, 0, "%.0f")
        implot.end_plot()

    _frame(gui, painter=rec)
    said = {t[5]: t[6] for t in rec.texts if t[5] in ("0", "100")}
    assert _luma(said["0"]) > 128, "dark text on the dark end of the ramp"
    assert _luma(said["100"]) < 128, "light text on the bright end of the ramp"


def test_a_pushed_colormap_wins_over_the_default():
    """``push_colormap`` is a port saying "these colours". The built-in ramp
    is only the default the reference's categorical one cannot sensibly
    be."""
    seen = {}

    def gui():
        implot.push_colormap([(255, 0, 0), (0, 0, 255)])
        implot.begin_plot("##t", (360, 240))
        implot.plot_heatmap("##h", [0.0, 1.0], 1, 2, 0, 0, None)
        seen["box"] = implot._cur.box
        implot.end_plot()
        implot.pop_colormap()

    p = _frame(gui)
    assert _px(p, *_cell_centre(seen["box"], 1, 2, 0, 0)) == (255, 0, 0, 255)
    assert _px(p, *_cell_centre(seen["box"], 1, 2, 0, 1)) == (0, 0, 255, 255)


def test_col_major_reads_the_same_block_the_other_way():
    """``ImPlotHeatmapFlags_ColMajor`` is a storage order, not a hint: read
    row-major anyway and the picture is the transpose of the data."""
    values = [0.0, 1.0, 2.0, 3.0]
    row_major, box = _draw(values, 2, 2, 0, 0, None)
    col_major, _ = _draw(values, 2, 2, 0, 0, None, (0.0, 0.0), (1.0, 1.0),
                         implot.HEATMAP_COL_MAJOR)
    top_right = _cell_centre(box, 2, 2, 0, 1)
    assert _px(row_major, *top_right) != _px(col_major, *top_right)
    # row-major puts values[1] there, col-major values[2]
    assert _luma(_px(col_major, *top_right)) > _luma(_px(row_major, *top_right))


def test_a_grid_larger_than_its_data_draws_nothing():
    """A live window sizes its grid before the histogram behind it is filled.
    The reference reads past the end of the block; here that is an
    IndexError mid-frame, so the frame is skipped instead."""
    def gui():
        implot.begin_plot("##t", (360, 240))
        implot.plot_heatmap("##h", [1.0, 2.0], 4, 4, 0, 0, None)
        assert implot._cur.plot._lines == []
        implot.end_plot()

    _frame(gui)


def test_it_is_refused_outside_a_plot():
    """``PlotHeatmap`` before ``BeginPlot`` has nothing to draw into. Said
    plainly, as ``end_plot`` says it, rather than left to whatever attribute
    error falls out of the module state."""
    def gui():
        with pytest.raises(RuntimeError, match="plot_heatmap"):
            implot.plot_heatmap("##h", [1.0], 1, 1)

    _frame(gui)


def test_the_plot_limits_answer_to_both_spellings():
    """The window this heatmap exists for reads ``limits.X.min`` -- the
    ``ImPlotRect`` shape -- in the line above the ``PlotHeatmap`` call, to
    decide whether the view moved. A flat tuple raised ``'tuple' object has no
    attribute 'X'`` there, and the heatmap under it never drew."""
    def gui():
        implot.begin_plot("##t", (360, 240))
        implot.setup_axes_limits(1.0, 4.0, 0.0, 1.0, implot.COND_ALWAYS)
        implot.plot_heatmap("##h", [1.0], 1, 1, 0, 0, None)
        limits = implot.get_plot_limits()
        assert (limits.X.min, limits.X.max) == (1.0, 4.0)
        assert (limits.Y.min, limits.Y.max) == (0.0, 1.0)
        x_min, x_max, y_min, y_max = limits          # still unpacks as four
        assert (x_min, x_max, y_min, y_max) == (1.0, 4.0, 0.0, 1.0)
        implot.end_plot()

    _frame(gui)


def test_the_ported_burst_mle_call_draws_its_histogram():
    """The call this exists for, spelled as the port spells it: a flat list,
    an explicit maximum, no cell labels, and plain ``(x, y)`` tuples for the
    bounds in the units the axes are in."""
    n = 8
    hist = [float((r * n + c) % 17) for r in range(n) for c in range(n)]
    seen = {}

    def gui():
        implot.begin_plot("##Heatmap", (300, 200))
        implot.plot_heatmap("##Heatmap", hist, n, n, 0, max(1.0, max(hist)),
                            None, (0.5, 0.0), (4.0, 1.0))
        seen["box"] = implot._cur.box
        implot.end_plot()

    p = _frame(gui)
    x, y, w, h = seen["box"]
    seen_colours = {_px(p, x + w * (j + 0.5) / n, y + h * (i + 0.5) / n)
                    for i in range(n) for j in range(n)}
    assert len(seen_colours) == 17, (
        f"17 distinct values, {len(seen_colours)} distinct cell colours")
