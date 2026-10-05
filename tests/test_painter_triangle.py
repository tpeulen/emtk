"""``fill_triangle`` and the ``line`` helper it was added for.

Three things are asserted: the ``Painter`` protocol's one new operation draws
the right pixels through the Qt reference, the free ``line`` function turns
into exactly two triangles rather than growing every backend an eighth method,
and a degenerate segment is dropped instead of producing a triangle with no
area (which would silently disappear from a rasteriser but not from a vertex
count).
"""
from __future__ import annotations

import math

import pytest

from emtk import painter as painter_mod
from emtk.testing import RecordingPainter


def test_line_is_exactly_two_triangles():
    """A segment becomes two ``fill_triangle`` calls, not a new primitive."""
    p = RecordingPainter()
    painter_mod.line(p, 0.0, 0.0, 10.0, 0.0, 2.0, (255, 0, 0))
    assert len(p.triangles) == 2


def test_line_is_centred_on_the_segment_and_perpendicular_to_it():
    """A horizontal segment offsets vertically; the quad it forms has the
    requested width and spans the requested length."""
    p = RecordingPainter()
    painter_mod.line(p, 0.0, 0.0, 10.0, 0.0, 4.0, (255, 0, 0))
    xs = [pt[0] for tri in p.triangles for pt in tri[:3]]
    ys = [pt[1] for tri in p.triangles for pt in tri[:3]]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(10.0)
    assert min(ys) == pytest.approx(-2.0)
    assert max(ys) == pytest.approx(2.0)


def test_a_degenerate_line_draws_nothing():
    """A zero-length segment has no direction to offset perpendicular to."""
    p = RecordingPainter()
    painter_mod.line(p, 5.0, 5.0, 5.0, 5.0, 3.0, (255, 0, 0))
    assert p.triangles == []


def test_a_diagonal_line_offsets_perpendicular_to_its_own_direction():
    """A 45-degree segment's quad corners sit off-axis, not axis-aligned."""
    p = RecordingPainter()
    painter_mod.line(p, 0.0, 0.0, 10.0, 10.0, 2.0 * math.sqrt(2.0), (0, 0, 0))
    corners = {pt for tri in p.triangles for pt in tri[:3]}
    # The perpendicular to a 45-degree line is also 45 degrees; offsetting by
    # width/2 along it moves x and y by equal, opposite amounts.
    for x, y in corners:
        on_start = pytest.approx(x + y, abs=1e-9) == 0.0
        on_end = pytest.approx(x + y, abs=1e-9) == 20.0
        assert on_start or on_end


def test_qt_painter_fills_a_triangle_at_its_three_corners(qt_app):
    """The Qt backend draws the same shape it is asked for, pixel-checked.

    ``qt_app`` is emtk's own fixture (``tests/conftest.py``), not pytest-qt's
    ``qapp``: asking for a fixture a plugin supplies makes the whole suite
    depend on that plugin, and without it this was a collection error rather
    than the skip an optional backend deserves.
    """
    qtgui = pytest.importorskip("qtpy.QtGui", exc_type=ImportError)
    from qtpy import QtCore

    from emtk.qt_painter import QtPainter

    image = qtgui.QImage(20, 20, qtgui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    qp = qtgui.QPainter(image)
    try:
        p = QtPainter(qp)
        p.fill_triangle((2.0, 2.0), (18.0, 2.0), (10.0, 18.0), (255, 0, 0))
    finally:
        qp.end()

    # Well inside the triangle: red. Well outside: still transparent.
    inside = image.pixelColor(10, 10)
    outside = image.pixelColor(1, 1)
    assert (inside.red(), inside.green(), inside.blue()) == (255, 0, 0)
    assert outside.alpha() == 0


def test_a_translucent_line_is_drawn_once_not_three_times(qt_app):
    """The seam-closing hairline is for opaque fills only.

    ``fill_triangle`` strokes each triangle with a hairline of its own colour so
    two triangles sharing an edge leave no seam. On a translucent colour that
    stroke is extra coverage: a 1 px white line at alpha 20 came out at 71 --
    the fill plus two hairlines -- so a grid meant to be barely there was
    three and a half times as bright as asked.
    """
    from qtpy import QtGui

    from emtk.qt_painter import QtPainter

    image = QtGui.QImage(40, 40, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor(0, 0, 0))
    qp = QtGui.QPainter(image)
    painter_mod.line(QtPainter(qp), 20.5, 2.0, 20.5, 38.0, 1.0, (255, 255, 255, 20))
    qp.end()
    peak = max(QtGui.QColor(image.pixel(x, 20)).red() for x in range(15, 26))
    assert 12 <= peak <= 30, f"alpha-20 line drawn at {peak}"


def test_an_opaque_line_still_has_no_seam(qt_app):
    from qtpy import QtGui

    from emtk.qt_painter import QtPainter

    image = QtGui.QImage(60, 60, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor(0, 0, 0))
    qp = QtGui.QPainter(image)
    painter_mod.line(QtPainter(qp), 5.0, 5.0, 55.0, 55.0, 8.0, (255, 255, 255))
    qp.end()
    # the shared diagonal runs through the middle of the stroke
    assert all(QtGui.QColor(image.pixel(i, i)).red() == 255 for i in range(15, 45))
