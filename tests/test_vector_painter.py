"""Vector output: emtk.figure written as SVG and PDF, and drawn at print resolution."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zlib

import pytest

from emtk import implot
from emtk.figure import Figure, colorbar_space
from emtk.painter import ALIGN_CENTER
from emtk.vector_painter import PdfPainter, SvgPainter

SVG = "{http://www.w3.org/2000/svg}"


def _figure() -> Figure:
    fig = Figure(rows=1, cols=2, size=(480, 240), title="Decay τ = 4 ns")
    ax = fig.ax(0, 0)
    ax.line([0, 1, 2, 3], [1, 3, 2, 4], label="data")
    ax.set_labels(x="t / ns", y="counts")
    ax.legend()
    fig.ax(0, 1).heatmap([[0, 1], [2, 3]], colorbar="z")
    return fig


def _pdf_streams(data: bytes) -> list[bytes]:
    out = []
    for m in re.finditer(rb"stream\n(.*?)\nendstream", data, re.S):
        out.append(zlib.decompress(m.group(1)))
    return out


def test_svg_is_well_formed_and_keeps_text_as_text():
    root = ET.fromstring(_figure().svg_bytes())
    assert root.tag == SVG + "svg"
    texts = [t.text for t in root.iter(SVG + "text")]
    assert "Decay τ = 4 ns" in texts and "t / ns" in texts and "counts" in texts
    # The trace is a stroked path, not a cloud of triangles.
    assert any(el.get("stroke") for el in root.iter(SVG + "polyline"))


def test_svg_text_is_pinned_to_the_raster_layout_width():
    painter = SvgPainter(200, 50)
    painter.text(0, 0, 200, 50, ALIGN_CENTER, "abcd", (0, 0, 0, 255))
    el = next(ET.fromstring(painter.svg_bytes()).iter(SVG + "text"))
    assert float(el.get("textLength")) == pytest.approx(painter.text_width("abcd"))
    # Centred as the raster painters centre it.
    assert float(el.get("x")) == pytest.approx((200 - painter.text_width("abcd")) / 2)


def test_rotated_text_turns_clockwise_for_positive_degrees_and_keeps_a_page_clip():
    painter = SvgPainter(100, 100)
    painter.push_clip(0, 0, 50, 100)
    painter.text_rotated(10, 40, 30, 20, ALIGN_CENTER, "y", (0, 0, 0, 255), -90.0)
    painter.pop_clip()
    svg = painter.svg_bytes().decode()
    assert 'transform="rotate(-90 25 50)"' in svg
    # The clip goes on a group: on the element it would be read in rotated space.
    assert re.search(r'<g clip-path="url\(#c0\)"><text[^>]*transform=', svg)


def test_pdf_is_one_page_with_courier_and_symbol():
    data = _figure().pdf_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert b"/BaseFont /Courier" in data and b"/BaseFont /Symbol" in data
    content = b"".join(_pdf_streams(data))
    assert b"(t / ns) Tj" in content
    # Greek goes through Symbol: tau is 't' there.
    assert b"/F2" in content


def test_pdf_xref_offsets_point_at_objects():
    data = _figure().pdf_bytes()
    start = int(data[data.rindex(b"startxref") + 9:].split()[0])
    xref = data[start:].split(b"trailer")[0].splitlines()[2:]
    for i, line in enumerate(xref[1:], start=1):
        offset = int(line.split()[0])
        assert data[offset:].startswith(f"{i} 0 obj".encode())


def test_opaque_cells_close_their_seams():
    painter = PdfPainter(20, 10)
    painter.fill_rect(0, 0, 10, 10, (255, 0, 0, 255))
    painter.fill_rect(10, 0, 10, 10, (0, 0, 255, 128))
    content = _pdf_streams(painter.pdf_bytes())[-1]
    assert b"0.35 w 0 0 10 10 re B" in content     # opaque: fill + hairline
    assert b"10 0 10 10 re f" in content           # translucent: fill only
    svg = SvgPainter(20, 10)
    svg.fill_rect(0, 0, 10, 10, (255, 0, 0, 255))
    assert b'shape-rendering="crispEdges"' in svg.svg_bytes()


def test_save_writes_by_suffix(tmp_path):
    fig = _figure()
    assert fig.save(tmp_path / "f.svg").read_bytes().startswith(b"<?xml")
    assert fig.save(tmp_path / "f.pdf").read_bytes().startswith(b"%PDF")
    assert fig.save(tmp_path / "f.png").read_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ValueError):
        fig.save(tmp_path / "f.jpg")


def test_dpi_draws_the_same_layout_larger():
    from emtk.testing import png_decode

    fig = _figure()
    w1, h1, _ = png_decode(fig.png_bytes())
    w3, h3, px = png_decode(fig.png_bytes(dpi=288))
    assert (w3, h3) == (3 * w1, 3 * h1)
    # The last row is paper, not the painter's default black.
    last = px[(h3 - 1) * w3 * 4:]
    assert min(last[0::4]) > 200


def test_a_log_mesh_leaves_non_positive_cells_empty_and_bars_on_a_log_scale():
    fig = Figure(size=(300, 250))
    ax = fig.ax()
    ax.mesh([0, 1, 2], [0, 1, 2], [[0, 10], [100, 1000]], log=True, colorbar="z")
    cells = ax._items[0][1]["cells"]
    assert len(cells) == 3                       # the zero is not drawn
    assert ax.colorbar == {"label": "z", "low": 10.0, "high": 1000.0,
                           "colormap": "viridis", "log": True}
    with pytest.raises(ValueError):
        ax.mesh([0, 1], [0, 1, 2], [[1, 2]])     # one row per y bin


def test_a_right_column_keeps_its_width_beside_a_wide_y_label():
    """Rows of a grid are aligned per column: the left column's wide y-axis
    gutter is not imposed on a narrow right column and its log colour bar."""
    rects = []
    end = implot.end_plot

    def spy():
        rects.append(tuple(implot.gp.current_plot.plot_rect))
        return end()

    fig = Figure(rows=2, cols=2, size=(576, 576), width_ratios=[343, 233],
                 height_ratios=[1, 4])
    fig.ax(0, 1).hide()
    fig.ax(0, 0).line([0, 1], [0, 1])
    density = fig.ax(1, 0)
    density.mesh([0, 1, 2], [0, 1, 2], [[1, 10], [100, 1000]], log=True)
    density.set_labels(x="tau / ns", y="a long y-axis label")
    right = fig.ax(1, 1)
    right.bars([0.5, 1.5], [3, 4], width=1.0, horizontal=True)
    right.hide_tick_labels(y=True)
    right.add_colorbar("counts", 1, 1000, log=True)
    implot.end_plot = spy
    try:
        fig.png_bytes()
    finally:
        implot.end_plot = end
    for x0, _y0, x1, _y1 in rects[len(rects) // 2:]:
        assert x1 - x0 > 20, rects
    assert colorbar_space(True) > colorbar_space(False)
