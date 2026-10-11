"""A y-axis label longer than its plot is tall is elided and kept inside the frame.

Found in ChiSurf's filter calculator (2026-10-11): a short residual panel centred the rotated
label "Weighted residuals σ" on its plot area, and the label ran off the top and the bottom.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import implot
from emtk.implot_internal import calc_text_size
from emtk.testing import RecordingPainter

LONG = "Weighted residuals of the fit in units of sigma"


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []


def _draw(size, label, frames=2):
    io = emtk.IO()
    storage = {}
    seen = {}
    rec = None
    for _ in range(frames):
        rec = RecordingPainter()
        with emtk.frame(rec, (0, 0, 800, 600), io=io, storage=storage):
            emtk.begin("w")
            if implot.begin_plot("##p", size):
                implot.setup_axes("x", label)
                implot.plot_line("a", [0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
                seen["frame"] = implot._cur.plot.frame_rect
                implot.end_plot()
            emtk.end()
    return rec, seen


def test_a_label_taller_than_a_short_plot_is_elided_to_the_frame():
    rec, seen = _draw((600, 120), LONG)
    frame = seen["frame"]
    shown = [s for s in rec.strings if s.startswith("Weighted")]
    assert shown and shown[0] != LONG and shown[0].endswith("…")
    with emtk.frame(RecordingPainter(), (0, 0, 800, 600)):
        width = calc_text_size(shown[0])[0]
    assert width <= frame[3] - frame[1]


def test_a_label_that_fits_is_drawn_whole():
    rec, _seen = _draw((600, 400), "Counts")
    assert "Counts" in rec.strings


def test_the_rotated_label_stays_inside_the_frame():
    """With a painter that turns text: the label's box lies within the plot frame vertically."""
    boxes = []

    class Rotating(RecordingPainter):
        def text_rotated(self, x, y, w, h, align, string, colour, degrees=0.0):
            boxes.append((x, y, w, h, string))

    io, storage = emtk.IO(), {}
    for _ in range(2):
        boxes.clear()
        with emtk.frame(Rotating(), (0, 0, 800, 600), io=io, storage=storage):
            emtk.begin("w")
            if implot.begin_plot("##p", (600, 120)):
                implot.setup_axes("x", LONG)
                frame = implot._cur.plot.frame_rect
                implot.end_plot()
            emtk.end()
    (x, y, w, h, string), = [b for b in boxes if b[4].startswith("Weighted")]
    cy = y + h * 0.5  # turned by -90° about its centre: it spans cy ± w/2
    assert frame[1] - 0.5 <= cy - w * 0.5 and cy + w * 0.5 <= frame[3] + 0.5
