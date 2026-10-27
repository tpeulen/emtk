"""A label-free heatmap fills runs of equal cells as one rectangle -- the same pixels, cell for cell.

A live 2-D histogram (mostly empty cells of one colour) is redrawn at display rate; filling every
cell separately cost a large share of each frame.
"""

from __future__ import annotations

import random

import pytest

from emtk import implot_items as items


class _Raster:
    def __init__(self, w=120, h=90):
        self.w, self.h = w, h
        self.px = {}
        self.calls = 0

    def fill_rect(self, x, y, w, h, col):
        self.calls += 1
        for yy in range(int(y), int(y + h)):
            for xx in range(int(x), int(x + w)):
                self.px[(xx, yy)] = col


def _cmap(tt):
    if tt is None:
        return (0, 0, 0, 255)
    if tt < 0.05:
        return (10, 10, 10, 255)
    if tt > 0.97:
        return (0, 0, 0, 0)  # transparent: skipped
    return (int(255 * tt), 100, 200, 255)


def _per_cell(p, vals, rows, cols, smin, smax, col_maj, xe, ye, cull):
    for idx in range(rows * cols):
        r, c = (idx % rows, idx // rows) if col_maj else (idx // cols, idx % cols)
        tt = min(max((vals[idx] - smin) / (smax - smin), 0.0), 1.0)
        col = _cmap(tt)
        x0, x1 = sorted((round(xe[c]), round(xe[c + 1])))
        y0, y1 = sorted((round(ye[r]), round(ye[r + 1])))
        if col[3] == 0 or not (y0 < cull[3] and y1 > cull[1] and x0 < cull[2] and x1 > cull[0]):
            continue
        p.fill_rect(x0, y0, max(x1 - x0, 1), max(y1 - y0, 1), col)


@pytest.mark.parametrize("col_maj", [False, True])
def test_runs_paint_the_same_pixels_with_fewer_fills(col_maj):
    rnd = random.Random(5)
    rows, cols = 17, 23
    vals = [0.0 if rnd.random() < 0.7 else rnd.uniform(0, 10) for _ in range(rows * cols)]
    xe = [3.3 + c * 4.7 for c in range(cols + 1)]
    ye = [80.0 - r * 4.3 for r in range(rows + 1)]  # y grows downward on screen
    cull = (10.0, 5.0, 100.0, 70.0)
    ref, fast = _Raster(), _Raster()
    _per_cell(ref, vals, rows, cols, 0.0, 10.0, col_maj, xe, ye, cull)
    items._render_heatmap_runs(fast, vals, rows, cols, 0.0, 10.0, col_maj, _cmap, xe, ye, cull)
    assert fast.px == ref.px
    assert fast.calls < ref.calls
