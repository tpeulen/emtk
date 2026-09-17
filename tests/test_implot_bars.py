"""``implot.plot_bars`` -- the two overloads, told apart by argument type.

The reference puts ``count`` *before* the sizing argument in both overloads,
so a port that calls it positionally -- which is what this module exists for
-- either crashes (the count lands where an array is expected) or, far worse,
draws confidently wrong bars (the count lands in ``bar_size`` and the bar size
in ``shift``). The tests below are mostly about the second case: it has no
symptom other than the picture.

What a call plotted is read back off the plot's record of it (``Plot.records``):
each bar's ``(position, value)`` point, its base, the bar size and whether it
is horizontal.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import implot
from emtk.testing import PixelPainter


@pytest.fixture(autouse=True)
def _no_plot_left_open():
    """A test that fails between begin_plot and end_plot leaves the module
    state set, and every later test then fails for the wrong reason."""
    yield
    implot._cur.plot = None


def _bars(*args, **kw):
    """Draw one ``plot_bars`` call and hand back its step series."""
    seen = {}
    p = PixelPainter(400, 260, background=(30, 32, 38, 255))
    with emtk.frame(p, (8, 8, 384, 244), io=emtk.IO(), storage={}):
        emtk.begin("w")
        implot.begin_plot("##t", (-1, 160))
        implot.plot_bars(*args, **kw)
        seen["series"] = implot._cur.plot.records[0]
        implot.end_plot()
        emtk.end()
    return seen["series"]


def _first_bar(series):
    """``(centre, size, value)`` of the first bar."""
    (x, y) = series["pts1"][0]
    if series["horizontal"]:
        return y, series["size"], x
    return x, series["size"], y


def test_the_values_overload_takes_its_count_before_the_bar_size():
    """``PlotBars("Bursts", values, count, bar_size)`` -- the ported call from
    cmc's burst window. Read as ``(xs, ys, bar_size)`` the count lands in
    ``ys`` and the call raises "'int' object is not iterable"."""
    hist = [3.0, 7.0, 2.0]
    centre, size, height = _first_bar(_bars("Bursts", hist, len(hist), 1.0))
    assert size == pytest.approx(1.0), "the bar size was read from the wrong slot"
    assert centre == pytest.approx(0.0), "bar zero is not at index zero"
    assert height == pytest.approx(3.0)


def test_the_xy_overload_reads_bar_size_where_the_reference_puts_it():
    """``PlotBars("PR", xs, ys, count, bar_size)``. Read against the old
    signature the count becomes the bar size and the bar size becomes a
    shift: bars 4 units wide, all of them sitting 0.01 to the right of the
    data. Nothing raises -- this is the failure that only the picture shows.
    """
    xs = [0.0, 0.02, 0.04, 0.06]
    ys = [1.0, 5.0, 3.0, 2.0]
    series = _bars("PR", xs, ys, len(ys), 0.01)
    centre, size, height = _first_bar(series)
    assert size == pytest.approx(0.01), f"bar size read as {size}"
    assert centre == pytest.approx(0.0), "the bar size was applied as a shift"
    assert height == pytest.approx(1.0)
    assert len(series["pts1"]) == len(xs), "the count truncated the series"


def test_the_xy_overload_has_flags_where_the_values_overload_has_shift():
    """The reference's xy overload takes no ``shift``: the slot after
    ``bar_size`` is ``flags``. Read as a shift, ``Horizontal`` (1) moves every
    bar a whole unit sideways and still draws them upright."""
    values = [1.0, 4.0, 2.0]
    positions = [0.1, 0.2, 0.3]
    series = _bars("##PRBars", values, positions, len(values), 0.05,
                   implot.BARS_HORIZONTAL)
    # horizontal bars: the value is the x extent, the position the y band
    assert series["horizontal"], "the bars were drawn upright"
    centre, size, value = _first_bar(series)
    assert value == pytest.approx(1.0)
    assert centre == pytest.approx(0.1), "flags read as a shift"
    assert size == pytest.approx(0.05)


def test_the_values_overload_still_takes_a_shift_after_the_bar_size():
    """It is the overload that has one, and a port passing all five
    positional arguments must land on it."""
    centre, size, _h = _first_bar(_bars("a", [1.0, 2.0], 2, 0.5, 10.0))
    assert size == pytest.approx(0.5)
    assert centre == pytest.approx(10.0), "the shift was dropped"


def test_a_scalar_third_argument_never_reads_as_a_series():
    """The overloads are told apart by type, as in C++. An ``int`` where the
    ys would be is a count, and a list is ys -- decided here rather than by
    argument position, which is the whole bug."""
    values = [1.0, 2.0, 3.0, 4.0]
    truncated = _bars("a", values, 2)                 # count, not ys
    assert len(truncated["pts1"]) == 2
    paired = _bars("a", [10.0, 20.0], values[:2])     # ys, not a count
    assert _first_bar(paired)[0] == pytest.approx(10.0)


def test_the_keyword_spellings_survive():
    """``plot_histogram`` and any emtk caller that named its arguments must
    keep working: the dispatch is for positional calls, not a rename."""
    centre, size, _h = _first_bar(
        _bars("a", [0.0, 1.0], ys=[4.0, 5.0], bar_size=0.25, shift=1.0))
    assert size == pytest.approx(0.25)
    assert centre == pytest.approx(1.0)


def test_the_values_overload_puts_horizontal_bars_along_x():
    """With ``Horizontal`` the values are the bar *lengths* on x and the
    index is the position on y. Kept in the vertical arrangement they are a
    transposed picture of the same numbers."""
    series = _bars("a", [5.0, 9.0], 2, 0.5, 0.0, implot.BARS_HORIZONTAL)
    centre, _size, value = _first_bar(series)
    assert series["horizontal"]
    assert value == pytest.approx(5.0)
    assert centre == pytest.approx(0.0)   # index zero
