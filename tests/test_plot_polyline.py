"""Solid plot traces use optional native strokes without losing samples/gaps."""
from __future__ import annotations

import math

from emtk.testing import RecordingPainter
from emtk.widgets.plot import Plot


class StrokeRecorder(RecordingPainter):
    def __init__(self):
        super().__init__()
        self.paths = []

    def polyline(self, points, width, colour, closed=False):
        self.paths.append((list(points), width, colour, closed))


def test_solid_trace_batches_every_sample_into_one_native_stroke():
    painter = StrokeRecorder()
    plot = Plot(0.0, 0.0, 100.0, 50.0, x_range=(0.0, 3.0), y_range=(0.0, 10.0))
    colour = (180, 200, 220, 255)
    plot.line("", [0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 2.0, 8.0], colour=colour, width=2.0)
    plot.draw(painter)
    expected = [(plot._x_axis.to_pixels(x), plot._y_axis.to_pixels(y))
                for x, y in zip([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 2.0, 8.0])]
    assert painter.paths == [(expected, 2.0, colour, False)]
    assert painter.triangles == []


def test_native_strokes_never_bridge_nonfinite_samples():
    painter = StrokeRecorder()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    xs = [0.0, 1.0, 2.0, 3.0, 4.0, math.inf, 6.0, 7.0]
    ys = [0.0, 1.0, math.nan, 3.0, 4.0, 5.0, 6.0, 7.0]
    plot.line("", xs, ys)
    plot.draw(painter)
    assert [len(path[0]) for path in painter.paths] == [2, 2, 2]
    assert sum(len(path[0]) for path in painter.paths) == 6
    assert all(math.isfinite(v) for path in painter.paths for point in path[0] for v in point)
    assert painter.triangles == []


def test_scalar_painter_retains_identical_triangle_fallback():
    painter = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("", [0.0, 1.0, 2.0, 3.0, 4.0], [1.0, 2.0, math.nan, 4.0, 5.0])
    plot.draw(painter)
    assert len(painter.triangles) == 4


def test_dashed_traces_keep_scalar_phase_path():
    painter = StrokeRecorder()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("", [0.0, 1.0, 2.0], [1.0, 2.0, 3.0], dash=(4.0, 3.0))
    plot.draw(painter)
    assert not painter.paths
    assert painter.triangles


def test_qt_native_stroke_preserves_state_clipping_and_open_path(qt_app):
    from qtpy import QtCore, QtGui

    from emtk.qt_painter import QtPainter

    image = QtGui.QImage(64, 48, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    native = QtGui.QPainter(image)
    try:
        painter = QtPainter(native)
        native.setPen(QtGui.QPen(QtGui.QColor("blue"), 7.0))
        native.setBrush(QtGui.QColor("green"))
        pen, brush = native.pen(), native.brush()
        assert callable(getattr(painter, "polyline", None)), "Qt painter needs a native stroke"
        painter.push_clip(10.0, 0.0, 40.0, 48.0)
        painter.polyline([(2.0, 10.0), (40.0, 10.0), (40.0, 40.0)], 3.0, (255, 0, 0, 255))
        painter.pop_clip()
        assert native.pen() == pen
        assert native.brush() == brush
    finally:
        native.end()
    assert image.pixelColor(20, 10).red() == 255
    assert image.pixelColor(40, 30).red() == 255
    assert image.pixelColor(5, 10).alpha() == 0  # obey the clip
    assert image.pixelColor(20, 20).alpha() == 0  # no fill/closing diagonal


def test_qt_native_stroke_retains_legacy_line_thickness(qt_app):
    from qtpy import QtCore, QtGui

    from emtk.painter import line
    from emtk.qt_painter import QtPainter

    def render(native_stroke):
        image = QtGui.QImage(64, 48, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.transparent)
        native = QtGui.QPainter(image)
        try:
            painter = QtPainter(native)
            if native_stroke:
                painter.polyline([(8.0, 20.0), (56.0, 20.0)], 2.0, (255, 0, 0, 255))
            else:
                line(painter, 8.0, 20.0, 56.0, 20.0, 2.0, (255, 0, 0, 255))
        finally:
            native.end()
        return [image.pixelColor(30, y).alpha() for y in range(48)]

    assert render(True) == render(False)


def test_qt_native_closed_stroke_does_not_fill_interior(qt_app):
    from qtpy import QtCore, QtGui

    from emtk.qt_painter import QtPainter

    image = QtGui.QImage(48, 48, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    native = QtGui.QPainter(image)
    try:
        painter = QtPainter(native)
        assert callable(getattr(painter, "polyline", None)), "Qt painter needs a native stroke"
        painter.polyline([(8.0, 8.0), (40.0, 8.0), (40.0, 40.0), (8.0, 40.0)],
                         2.0, (255, 0, 0, 255), closed=True)
        painter.polyline([], 2.0, (255, 0, 0, 255))
        painter.polyline([(25.0, 25.0)], 2.0, (255, 0, 0, 255))
    finally:
        native.end()
    assert image.pixelColor(8, 25).red() == 255
    assert image.pixelColor(25, 8).red() == 255
    assert image.pixelColor(25, 25).alpha() == 0
