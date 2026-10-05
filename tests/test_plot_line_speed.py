"""Dense traces draw fast and look the same.

A fit window redrew a 4096-channel decay, its prompt and three residual traces
in ~51 ms a frame (60+ at 2x), which is a plot that lags the pointer. Most of it
was per-sample Python (``to_pixels``, ``isfinite``, a ``QPointF`` per vertex),
then Qt stroking every sample with a wide pen, once per run of a trace broken by
gaps. These pin down what replaced it and that it draws the same pixels.
"""

from __future__ import annotations

import numpy as np
import pytest

from emtk.testing import RecordingPainter
from emtk.widgets.axis import Axis
from emtk.widgets.plot import Plot, column_extremes, column_extremes_index


def test_the_axis_fits_an_array_and_skips_gaps():
    axis = Axis()
    axis.fit(np.array([3.0, np.nan, -2.0, np.inf, 7.5]))
    assert axis.range == (-2.0, 7.5)


def test_to_pixels_array_matches_to_pixels():
    axis = Axis(0.0, 10.0)
    axis.set_pixels(100.0, 300.0)
    values = np.linspace(-1, 11, 25)
    assert np.allclose(axis.to_pixels_array(values), [axis.to_pixels(v) for v in values])


def test_a_dense_column_keeps_its_extremes_and_the_ends():
    px = np.repeat(np.arange(100.0), 10) + np.tile(np.linspace(0, 0.9, 10), 100)
    py = np.sin(np.arange(1000) * 0.37) * 50
    keep = column_extremes_index(px, py)
    assert len(keep) <= 2 * 100 + 2
    assert keep[0] == 0 and keep[-1] == 999
    for column in range(100):
        members = np.arange(column * 10, column * 10 + 10)
        kept = [k for k in keep if k in members]
        assert py[kept].min() == py[members].min() and py[kept].max() == py[members].max()


def test_a_sparse_or_backtracking_path_is_kept_whole():
    sparse = np.arange(50.0) * 3
    assert len(column_extremes_index(sparse, sparse)) == 50
    back = np.concatenate((np.arange(500.0) / 5, np.arange(500.0)[::-1] / 5))
    assert len(column_extremes_index(back, back)) == 1000


def test_runs_keep_their_own_ends():
    px = np.repeat(np.arange(40.0), 10) / 1.0 + np.tile(np.linspace(0, 0.9, 10), 40)
    py = np.cos(np.arange(400) * 0.2)
    run_id = (np.arange(400) >= 200).astype(int)
    keep = set(column_extremes_index(px, py, run_id))
    assert {0, 199, 200, 399} <= keep


def test_column_extremes_returns_points():
    px = np.linspace(0, 10, 400)
    points = column_extremes(px, np.sin(px))
    assert points.shape[1] == 2 and len(points) < 400


def test_a_gap_breaks_the_line_into_runs():
    plot = Plot(0, 0, 200, 100)
    xs = np.linspace(0, 1, 50)
    ys = np.sin(xs * 6)
    ys[20] = np.nan
    plot.line("a", xs, ys)

    class Batch(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.batches = []

        def polylines(self, runs, width, colour):
            self.batches.append([len(r) for r in runs])

    painter = Batch()
    plot.draw(painter)
    assert painter.batches == [[20, 29]]


@pytest.fixture
def qt_image(qt_app):
    from qtpy import QtGui

    def make(ratio=1.0, w=300, h=120):
        image = QtGui.QImage(int(w * ratio), int(h * ratio), QtGui.QImage.Format_RGB32)
        image.setDevicePixelRatio(ratio)
        image.fill(QtGui.QColor(0, 0, 0))
        return image

    return make


def test_the_polygon_is_filled_from_the_array_exactly(qt_app):
    from emtk.qt_painter import _polygon

    points = np.random.default_rng(1).random((257, 2)) * 100
    polygon = _polygon(points)
    assert polygon.size() == 257
    got = np.array([(polygon.at(i).x(), polygon.at(i).y()) for i in range(257)])
    assert np.array_equal(got, points)


@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_the_hairline_sweep_covers_what_the_wide_pen_covers(qt_image, ratio):
    from qtpy import QtCore, QtGui

    from emtk.qt_painter import QtPainter, _polygon

    x = np.linspace(10, 290, 400)
    points = np.column_stack((x, 60 + 40 * np.sin(x / 15)))

    swept = qt_image(ratio)
    qp = QtGui.QPainter(swept)
    QtPainter(qp).polylines([points], 1.5, (255, 255, 255))
    qp.end()

    wide = qt_image(ratio)
    qp = QtGui.QPainter(wide)
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2.5)
    pen.setCapStyle(QtCore.Qt.FlatCap)
    pen.setJoinStyle(QtCore.Qt.BevelJoin)
    qp.setPen(pen)
    qp.drawPolyline(_polygon(points))
    qp.end()

    def mask(image):
        ptr = image.constBits()
        ptr.setsize(image.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape(image.height(), image.width(), 4)
        return arr[:, :, 0] > 128

    a, b = mask(swept), mask(wide)
    # every pixel of either is within one logical pixel of the other
    from numpy.lib.stride_tricks import sliding_window_view as win

    def grow(m):
        # within one *logical* pixel: as many device pixels as the ratio
        for _ in range(int(np.ceil(ratio))):
            m = win(np.pad(m, 1), (3, 3)).any(axis=(2, 3))
        return m

    assert not (a & ~grow(b)).any(), "the sweep paints where the wide pen does not"
    assert not (b & ~grow(a)).any(), "the sweep misses what the wide pen paints"


def test_a_translucent_stroke_keeps_the_wide_pen(qt_image):
    from qtpy import QtGui

    from emtk.qt_painter import QtPainter

    image = qt_image()
    qp = QtGui.QPainter(image)
    painter = QtPainter(qp)
    assert painter._hairline_offsets(2.5, QtGui.QColor(255, 255, 255, 100)) is None
    assert painter._hairline_offsets(2.5, QtGui.QColor(255, 255, 255)) is not None
    qp.end()
