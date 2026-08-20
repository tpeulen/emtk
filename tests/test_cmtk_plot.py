"""``cmtk``'s axis transform and ``Plot`` item recording.

No GUI toolkit needed: everything draws through ``RecordingPainter``, the same
shared no-op painter every other control test in this package uses.
"""
from __future__ import annotations

import pytest

from cmtk.widgets.axis import Axis, nice_ticks
from cmtk.widgets.plot import Plot, begin_plot
from cmtk.testing import RecordingPainter


# -- Axis -----------------------------------------------------------------

def test_axis_auto_fits_from_data():
    axis = Axis()
    axis.fit([3.0, 1.0, 7.0, -2.0])
    assert axis.range == (-2.0, 7.0)


def test_axis_with_a_fixed_bound_ignores_fit_on_that_side():
    axis = Axis(v_min=0.0)
    axis.fit([3.0, 1.0, 7.0])
    assert axis.range == (0.0, 7.0)


def test_an_empty_axis_falls_back_to_zero_one():
    assert Axis().range == (0.0, 1.0)


def test_to_pixels_is_linear_and_endpoints_land_exactly():
    axis = Axis(0.0, 10.0)
    axis.set_pixels(100.0, 200.0)
    assert axis.to_pixels(0.0) == pytest.approx(100.0)
    assert axis.to_pixels(10.0) == pytest.approx(200.0)
    assert axis.to_pixels(5.0) == pytest.approx(150.0)


def test_a_y_axis_inverts_by_swapping_which_pixel_is_min():
    """Handing pixel_min the *bottom* is what makes a Y axis invert -- see
    the axis module docstring. No separate code path for X vs Y."""
    axis = Axis(0.0, 10.0)
    axis.set_pixels(200.0, 100.0)  # bottom=200 -> value 0; top=100 -> value 10
    assert axis.to_pixels(0.0) == pytest.approx(200.0)
    assert axis.to_pixels(10.0) == pytest.approx(100.0)


def test_to_plot_inverts_to_pixels():
    axis = Axis(0.0, 10.0)
    axis.set_pixels(100.0, 200.0)
    for v in (0.0, 3.3, 10.0):
        assert axis.to_plot(axis.to_pixels(v)) == pytest.approx(v)


def test_nice_ticks_are_within_range_and_evenly_spaced():
    ticks = nice_ticks(0.0, 97.0, target_count=4)
    assert len(ticks) >= 2
    assert all(0.0 <= t <= 97.0 for t in ticks)
    steps = {round(b - a, 9) for a, b in zip(ticks, ticks[1:])}
    assert len(steps) == 1  # one consistent step


def test_nice_ticks_on_a_degenerate_range_is_empty():
    assert nice_ticks(5.0, 5.0) == []
    assert nice_ticks(5.0, 3.0) == []


# -- Plot -------------------------------------------------------------------

def test_a_line_series_draws_one_segment_per_gap():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("fps", [0.0, 1.0, 2.0, 3.0], [10.0, 20.0, 15.0, 30.0])
    plot.draw(p)
    # 3 segments * 2 triangles each = 6.
    assert len(p.triangles) == 6


def test_a_single_point_line_draws_a_marker_not_a_segment():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("one point", [1.0], [1.0])
    plot.draw(p)
    # The default marker is a circle, scan-converted into fill_rect bands by
    # style.disc -- no triangle, and no line() segment for a lone point.
    assert not p.triangles
    assert len(p.fills) > 1  # background rect + the circle's bands


def test_an_empty_plot_still_draws_its_frame():
    p = RecordingPainter()
    plot = Plot(5.0, 5.0, 40.0, 20.0)
    plot.draw(p)
    assert p.strokes  # stroke_rect frame
    assert p.fills  # background fill_rect


def test_hline_does_not_extend_the_auto_fit_range():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("quiet", [0.0, 1.0], [1.0, 1.2])
    plot.hline(60.0, colour=(255, 0, 0))
    plot.draw(p)
    lo, hi = plot._y_axis.range
    assert hi < 60.0


def test_scatter_markers_are_drawn_per_point():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.scatter("pts", [0.0, 1.0, 2.0], [0.0, 1.0, 0.0], marker="diamond")
    plot.draw(p)
    # A diamond is 2 triangles; 3 points -> 6.
    assert len(p.triangles) == 6


def test_context_manager_draws_on_clean_exit():
    p = RecordingPainter()
    with begin_plot(p, 0.0, 0.0, 100.0, 50.0) as plot:
        plot.line("x", [0.0, 1.0], [0.0, 1.0])
    assert p.triangles  # the line was drawn: __exit__ called .draw


def test_context_manager_does_not_draw_when_the_block_raises():
    p = RecordingPainter()
    with pytest.raises(ValueError):
        with begin_plot(p, 0.0, 0.0, 100.0, 50.0) as plot:
            plot.line("x", [0.0, 1.0], [0.0, 1.0])
            raise ValueError("boom")
    assert not p.triangles and not p.fills and not p.strokes


def test_series_without_an_explicit_colour_cycle_through_the_palette():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("a", [0.0, 1.0], [0.0, 1.0])
    plot.line("b", [0.0, 1.0], [1.0, 0.0])
    colours = {s["colour"] for s in plot._lines}
    assert len(colours) == 2
    plot.draw(p)
