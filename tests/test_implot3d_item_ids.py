"""An ImPlot3D item is identified by its whole label, as in the reference.

``"Intensity 0##psf"`` and ``"Intensity 1##psf"`` are two items in ImPlot3D:
``##`` only hides the rest from the legend, and only ``###`` makes the suffix
the id. emtk read them as one item (the id after ``##``), so a plot drawing
twelve bands under one suffix got one automatic colour and one legend entry.
"""

from __future__ import annotations

import collections

import numpy as np

from emtk import im
from emtk import implot3d as p3
from emtk.app import ImApp
from emtk.testing import RecordingPainter


def _colours(items):
    def gui():
        im.begin("W", (0, 0, 400, 400), flags=im.WindowFlags.NO_TITLE_BAR)
        if p3.begin_plot("P", (-1, -1)):
            items()
            p3.end_plot()
        im.end()

    app = ImApp(gui)
    p = RecordingPainter()
    app.draw(p, 0, 0, 400, 400)
    p = RecordingPainter()
    app.draw(p, 0, 0, 400, 400)
    return collections.Counter(tuple(int(c) for c in t[3][:3]) for t in p.triangles)


def _point(k):
    v = np.array([0.1 * k])
    return v, v, v


def _marker_colours(items):
    background = _colours(lambda: None)
    return {c for c in _colours(items) if c not in background}


def test_labels_sharing_a_hidden_suffix_are_separate_items():
    colours = _marker_colours(lambda: [p3.plot_scatter(f"S {k}##g", *_point(k)) for k in range(3)])
    assert len(colours) == 3, colours


def test_a_triple_hash_suffix_is_the_id():
    # "###" makes the suffix the id: one item, whatever the visible text says.
    colours = _marker_colours(lambda: [p3.plot_scatter(f"S {k}###same", *_point(k)) for k in range(3)])
    assert len(colours) == 1, colours
