"""Dense marker acceleration preserves primitive geometry, alpha and source data."""
from types import SimpleNamespace

import pytest
from emtk import implot_internal as I
from emtk import implot_items as items
from emtk.offset_painter import OffsetPainter
from emtk.painter import line
from emtk.testing import PixelPainter


def render(monkeypatch, painter, points, *, fill=(30, 160, 220, 255),
           outline=(240, 60, 80, 255), size=1.5, weight=1.0, clip=(0, 0, 50, 50)):
    """Use the actual renderer with a known coordinate transform and plot cull box."""
    monkeypatch.setattr(items, "_dl", lambda: SimpleNamespace(p=painter))
    monkeypatch.setattr(items, "_transformer", lambda: lambda x, y: (x, y))
    monkeypatch.setattr(items, "_cull_rect", lambda: clip)
    items.render_markers(points, I.MARKER_CIRCLE, fill is not None, fill,
                         outline is not None, outline, size, weight)


def reference(painter, points, *, fill, outline, size, weight, clip=(0, 0, 50, 50)):
    """Frozen pre-acceleration circle fan/segment path, retaining every draw order."""
    for index, (x, y) in enumerate(points):
        if not (clip[0] <= x <= clip[2] and clip[1] <= y <= clip[3]):
            continue
        radius = size[index] if isinstance(size, (list, tuple)) else size
        if fill is not None:
            colour = fill[index] if isinstance(fill, list) else fill
            vertices = [(x + mx * radius, y + my * radius) for mx, my in items._MARKER_FILL[I.MARKER_CIRCLE]]
            # Deliberately use the minimal operations, not optional acceleration.
            for j in range(1, len(vertices) - 1):
                painter.fill_triangle(vertices[0], vertices[j], vertices[j + 1], colour)
        if outline is not None:
            colour = outline[index] if isinstance(outline, list) else outline
            shape = items._MARKER_LINE[I.MARKER_CIRCLE]
            for j in range(0, len(shape), 2):
                a, b = shape[j], shape[j + 1]
                line(painter, x + a[0] * radius, y + a[1] * radius,
                     x + b[0] * radius, y + b[1] * radius, max(1.0, weight), colour)


def test_optional_marker_glyph_receives_full_ordered_source_and_styles(monkeypatch):
    class GlyphPainter:
        def __init__(self):
            self.glyphs = []

        def marker(self, *args):
            self.glyphs.append(args)

        def fill_triangle(self, *args):
            raise AssertionError("the renderer ignored the optional cached marker path")

    painter = GlyphPainter()
    points = [(10.25, 8.5), (10.25, 8.5), (12.75, 8.5), (-1, 3)]
    colours = [(1, 2, 3, 255), (6, 7, 8, 80), (9, 10, 11, 255), (0, 0, 0, 255)]
    original = list(points)
    render(monkeypatch, painter, points, fill=colours, outline=None, size=[1, 2, 3, 4])
    assert len(painter.glyphs) == 3
    assert [entry[:2] for entry in painter.glyphs] == points[:3]
    assert points == original


@pytest.mark.parametrize("alpha", [80, 255])
@pytest.mark.parametrize("size", [0.7, 1.5, 3.25])
def test_pixel_markers_match_original_fractional_geometry_overlap_and_clipping(monkeypatch, alpha, size):
    points = [(0.5, 0.5), (5.25, 5.75), (5.75, 5.25), (24.2, 24.8), (49.5, 49.5), (51, 20)]
    fill, outline = (40, 90, 180, alpha), (190, 60, 30, alpha)
    actual, old = PixelPainter(50, 50), PixelPainter(50, 50)
    actual.push_clip(2, 2, 45, 45)
    old.push_clip(2, 2, 45, 45)
    reference(old, points, fill=fill, outline=outline, size=size, weight=1.0)
    render(monkeypatch, actual, points, fill=fill, outline=outline, size=size)
    assert actual.px == old.px


def test_opaque_covered_box_skips_only_ineffective_geometry(monkeypatch):
    class Covered(PixelPainter):
        def fill_triangle(self, *args):
            raise AssertionError("fully covered opaque geometry should need no raster work")

    painter = Covered(50, 50, background=(40, 90, 180, 255))
    points = [(15.125, 20.875)] * 1000
    render(monkeypatch, painter, points, fill=(40, 90, 180, 255), outline=None)
    assert painter.px[0:4] == bytes((40, 90, 180, 255))


def test_marker_and_coverage_optional_capabilities_translate_with_child_offset(monkeypatch):
    class GlyphPainter:
        def __init__(self):
            self.glyphs = []

        def marker(self, *args):
            self.glyphs.append(args)

        def box_has_colour(self, *args):
            return False

    target = GlyphPainter()
    render(monkeypatch, OffsetPainter(target, 7, 11), [(12.25, 18.75)], outline=None)
    assert target.glyphs[0][:2] == (19.25, 29.75)


@pytest.mark.parametrize("alpha", [80, 255])
@pytest.mark.parametrize("antialias", [False, True])
def test_qt_cached_glyph_is_byte_identical_to_original_marker_operations(qt_app, monkeypatch, alpha, antialias):
    from emtk.qt_painter import QtPainter, image_bytes
    from qtpy import QtCore, QtGui

    pictures = []
    points = [(4.25, 5.75), (6.75, 5.25), (16.125, 18.875), (24.5, 26.5)]
    sizes = [0.7, 1.5, 3.25, 5.0]
    fill, outline = (40, 90, 180, alpha), (190, 60, 30, alpha)
    for accelerated in (False, True):
        image = QtGui.QImage(50, 50, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.transparent)
        qp = QtGui.QPainter(image)
        qp.setRenderHint(QtGui.QPainter.Antialiasing, antialias)
        painter = QtPainter(qp)
        painter.push_clip(2, 2, 45, 45)
        if accelerated:
            render(monkeypatch, painter, points, fill=fill, outline=outline, size=sizes)
        else:
            reference(painter, points, fill=fill, outline=outline, size=sizes, weight=1.0)
        qp.end()
        pictures.append(image_bytes(image))
    assert pictures[0] == pictures[1]


def test_zero_legacy_marker_outline_keeps_the_plot_line_weight():
    from emtk import implot

    spec = I.PlotSpec()
    implot.set_next_marker_style(I.MARKER_CIRCLE, 1.5, (10, 20, 30, 255), 0.0, (40, 50, 60, 255))
    implot._apply_legacy_styles(spec)
    assert spec.marker_line_color[3] == 0
    assert spec.line_weight == 1.0


@pytest.mark.parametrize("fill,visible", [((10, 180, 220, 255), True), (None, True), ((10, 180, 220, 0), False)])
def test_zero_outline_preserves_real_scatter_legend_and_default_fill(fill, visible):
    from emtk import im, implot
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 220)):
        im.begin("Marker style")
        implot.begin_plot("Scatter", (280, 180))
        implot.set_next_marker_style(I.MARKER_CIRCLE, 1.5, fill, 0.0, (0, 0, 0, 0))
        implot.plot_scatter("Full series", [0, 1, 2], [1, 2, 1])
        item = items.get_item("Full series")
        spec = implot._cur.plot.records[0]["spec"]
        colour = item.color
        implot.end_plot()
        im.end()
    assert spec.marker_line_color[3] == 0
    assert (colour[3] > 0) is visible
    assert (spec.marker_fill_color[3] > 0) is visible


@pytest.mark.parametrize("weight,expected", [(I.IMPLOT_AUTO, 1.0), (None, 1.0), (2.5, 2.5)])
def test_default_and_positive_legacy_marker_weights_remain_unchanged(weight, expected):
    from emtk import implot

    spec = I.PlotSpec()
    implot.set_next_marker_style(I.MARKER_CIRCLE, 1.5, (10, 20, 30, 255), weight, (40, 50, 60, 255))
    implot._apply_legacy_styles(spec)
    assert spec.marker_line_color == (40, 50, 60, 255)
    assert spec.line_weight == expected


@pytest.mark.parametrize("device_ratio,dpi", [(1.0, 96), (2.0, 192)])
def test_qt_marker_cache_respects_device_scale_transform_and_outer_opacity(qt_app, monkeypatch, device_ratio, dpi):
    from emtk.qt_painter import QtPainter, image_bytes
    from qtpy import QtCore, QtGui

    buffers = []
    for accelerated in (False, True):
        image = QtGui.QImage(100, 100, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(device_ratio)
        image.setDotsPerMeterX(round(dpi / 0.0254))
        image.setDotsPerMeterY(round(dpi / 0.0254))
        image.fill(QtCore.Qt.transparent)
        qp = QtGui.QPainter(image)
        qp.setRenderHint(QtGui.QPainter.Antialiasing, True)
        qp.setOpacity(0.45)
        qp.translate(0.25, 0.75)
        qp.scale(1.15, 1.15)
        painter = QtPainter(qp)
        painter.push_clip(2, 2, 35, 35)
        points = [(12.25, 14.75), (14.75, 14.25), (36, 36)]
        fill, outline = (40, 90, 180, 180), (190, 60, 30, 120)
        if accelerated:
            render(monkeypatch, painter, points, fill=fill, outline=outline, size=3.25)
        else:
            reference(painter, points, fill=fill, outline=outline, size=3.25, weight=1.0)
        qp.end()
        buffers.append(image_bytes(image))
    assert buffers[0] == buffers[1]


def test_zero_radius_and_degenerate_opaque_polygons_remain_empty(monkeypatch):
    painter = PixelPainter(30, 30)
    original = bytes(painter.px)
    render(monkeypatch, painter, [(10.5, 10.5)], outline=None, size=0.0)
    painter.fill_convex([(2, 5.5), (15, 5.5), (25, 5.5)], (255, 0, 0, 255))
    assert bytes(painter.px) == original


def test_marker_rendering_retains_every_registered_source_point_for_fit_and_hover():
    from emtk import im, implot

    points = [(float(index), float(index % 17 + 1)) for index in range(4096)]
    painter = PixelPainter(300, 220)
    with im.frame(painter, (0, 0, 300, 220)):
        im.begin("Complete source")
        implot.begin_plot("Dense points", (280, 180))
        implot.set_next_marker_style(I.MARKER_CIRCLE, 1.5, (40, 90, 180, 255), 0)
        implot.plot_scatter("All samples", [p[0] for p in points], [p[1] for p in points])
        record = implot._cur.plot.records[0]
        implot.end_plot()
        im.end()
    assert record["pts"] == points
    assert len(record["pts"]) == 4096
