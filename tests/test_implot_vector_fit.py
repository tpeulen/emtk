"""Axis fitting over arrays equals the per-point rule it replaced.

A live view refits every frame; walking tens of thousands of points one by one in Python made it
stutter, so ``_fit_points`` fits a whole series in one NumPy pass. It must keep every rule of
``Axis.extend_fit_with``: non-finite values skipped, the constraint range, positive values only on
a log axis, and -- for an axis that fits to the other's range -- only points inside that range.
"""

from __future__ import annotations

import math
import random

import pytest

np = pytest.importorskip("numpy")

from emtk import implot_internal as I  # noqa: E402
from emtk import implot_items as items  # noqa: E402


def _axis(scale=I.SCALE_LINEAR, flags=0, rng=(0.0, 10.0), constraint=(-1e9, 1e9)):
    a = I.Axis()
    a.scale, a.flags = scale, flags
    a.range_min, a.range_max = rng
    a.constraint_range = list(constraint)
    a.fit_min, a.fit_max = math.inf, -math.inf
    return a


def _loop(xa, ya, pts):
    for x, y in pts:
        xa.extend_fit_with(ya, x, y)
        ya.extend_fit_with(xa, y, x)


@pytest.mark.parametrize("xscale,yscale,xflags", [
    (I.SCALE_LINEAR, I.SCALE_LINEAR, 0),
    (I.SCALE_LINEAR, I.SCALE_LOG10, 0),
    (I.SCALE_LINEAR, I.SCALE_LINEAR, I.AXIS_FLAGS_RANGE_FIT),
])
def test_the_vectorised_fit_equals_the_per_point_one(xscale, yscale, xflags):
    rnd = random.Random(3)
    pts = [(rnd.uniform(-20, 20), rnd.uniform(-5, 50)) for _ in range(2000)]
    pts += [(math.nan, 1.0), (2.0, math.inf), (3.0, 0.0), (1e12, 1.0)]
    ref = (_axis(xscale, xflags, constraint=(-1e9, 1e9)), _axis(yscale, rng=(-1.0, 20.0)))
    vec = (_axis(xscale, xflags, constraint=(-1e9, 1e9)), _axis(yscale, rng=(-1.0, 20.0)))
    _loop(*ref, pts)
    items._fit_points(*vec, pts)
    for a, b in zip(ref, vec):
        assert (a.fit_min, a.fit_max) == (b.fit_min, b.fit_max)


def test_an_iterable_that_is_not_pairs_falls_back_to_the_loop():
    xa, ya = _axis(), _axis()
    items._fit_points(xa, ya, ((x, x * 2.0) for x in range(5)))
    assert (xa.fit_min, xa.fit_max, ya.fit_max) == (0.0, 4.0, 8.0)
