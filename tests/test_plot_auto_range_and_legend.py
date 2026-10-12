"""Auto-range keeps every sample on screen; the legend swatch shows the series' pen."""

import math

import numpy as np
import pytest

from emtk import im, implot
from emtk.testing import PixelPainter, RecordingPainter

SIZE = (700, 420)


def _fit(series, log, frames=2):
    """The y (and x) limits an auto-ranged plot settles on."""
    storage, io = {}, im.IO()
    limits = None
    for _ in range(frames):
        with im.frame(RecordingPainter(), (0, 0, *SIZE), io=io, storage=storage):
            im.begin("P")
            if implot.begin_plot("T", (SIZE[0] - 20, SIZE[1] - 20)):
                implot.setup_axes("x", "y")
                if log:
                    implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                for i, (xs, ys) in enumerate(series):
                    implot.plot_line(f"s{i}", xs, ys)
                implot.end_plot()
                limits = implot.get_plot_limits()
            im.end()
    return limits


@pytest.mark.parametrize("log", [False, True])
def test_every_finite_sample_is_inside_after_auto_range(log):
    rng = np.random.default_rng(7)
    for _ in range(25):
        series = []
        for _k in range(rng.integers(1, 4)):
            n = int(rng.integers(5, 400))
            xs = np.sort(rng.uniform(-5, 20, n))
            scale = 10.0 ** rng.uniform(-2, 4)
            ys = scale * np.exp(rng.normal(0.0, 1.5, n)) if log else rng.normal(0, scale, n)
            ys[rng.random(n) < 0.05] = np.nan
            if log:
                ys[rng.random(n) < 0.05] = 0.0  # undrawable on a log axis
            series.append((xs, ys))
        lim = _fit(series, log)
        for xs, ys in series:
            ok = np.isfinite(ys) & ((ys > 0) if log else True)
            assert (xs[ok] >= lim.x_min).all() and (xs[ok] <= lim.x_max).all()
            assert (ys[ok] > lim.y_min).all() and (ys[ok] < lim.y_max).all(), (lim, ys[ok].max())


def test_log_auto_range_leaves_a_margin_above_the_peak():
    xs = np.linspace(1, 12, 200)
    ys = 1700.0 * np.exp(-((xs - 2.7) ** 2) / 0.5) + 3.0
    lim = _fit([(xs, ys)], log=True)
    assert lim.y_max > ys.max() * 1.02  # not on the frame: its stroke would be half clipped
    assert lim.y_min < ys.min()
    assert lim.y_min > 0 and math.isfinite(lim.y_max)


def _runs(row):
    """Number of separate horizontal runs of True in *row*."""
    padded = np.concatenate(([False], row, [False]))
    return int(np.count_nonzero(padded[1:] & ~padded[:-1]))


def _legend_swatches(**dashed_style):
    painter = PixelPainter(*SIZE)
    storage, io = {}, im.IO()
    x = np.linspace(0, 1, 50)
    for _ in range(3):
        with im.frame(painter, (0, 0, *SIZE), io=io, storage=storage):
            im.begin("P")
            if implot.begin_plot("T", (SIZE[0] - 20, SIZE[1] - 20)):
                implot.setup_axes("x", "y")
                implot.set_next_line_style((255, 0, 0, 255), 2.0)
                implot.plot_line("solid", x, x)
                implot.set_next_line_style((0, 255, 0, 255), 2.0, dash=(6.0, 4.0))
                implot.plot_line("dashed", x, x * 0.5)  # both run bottom-left to top-right: the key corner stays clear
                implot.end_plot()
            im.end()
    img = np.frombuffer(bytes(painter.px), np.uint8).reshape(SIZE[1], SIZE[0], 4)
    return img


def test_legend_swatch_draws_line_dash_pattern():
    img = _legend_swatches()
    # The key sits in the top-left of the plot area.
    area = img[0:80, 0:260]
    red = (area[..., 0] > 200) & (area[..., 1] < 60) & (area[..., 2] < 60)
    green = (area[..., 1] > 200) & (area[..., 0] < 60) & (area[..., 2] < 60)
    # The swatch is a stroke a couple of pixels thick, not a filled square.
    red_rows = np.flatnonzero(red.any(axis=1))
    green_rows = np.flatnonzero(green.any(axis=1))
    assert red_rows.size and green_rows.size
    assert red_rows.size <= 4 and green_rows.size <= 4
    assert _runs(red.any(axis=0)) == 1
    assert _runs(green.any(axis=0)) >= 2


def test_retained_plot_legend_swatch_draws_dash_pattern():
    from emtk.widgets.plot import Plot

    painter = PixelPainter(260, 120)
    plot = Plot(0, 0, 260, 120, y_range=(0.0, 100.0), show_ticks=True)  # curves hug the bottom
    x = [0.0, 1.0]
    plot.line("solid", x, [0.0, 0.4], colour=(255, 0, 0, 255), width=2.0)
    plot.line("dashed", x, [0.0, 0.5], colour=(0, 255, 0, 255), width=2.0, dash=(6.0, 4.0))
    plot.draw(painter)
    img = np.frombuffer(bytes(painter.px), np.uint8).reshape(120, 260, 4)
    key = img[0:40, 130:260]  # the key: top-right
    red = (key[..., 0] > 200) & (key[..., 1] < 60) & (key[..., 2] < 60)
    green = (key[..., 1] > 200) & (key[..., 0] < 60) & (key[..., 2] < 60)
    assert red.any() and green.any()
    assert _runs(red.any(axis=0)) == 1
    assert _runs(green.any(axis=0)) >= 2
