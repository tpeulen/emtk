"""``emtk``'s axis transform and ``Plot`` item recording.

No GUI toolkit needed: everything draws through ``RecordingPainter``, the same
shared no-op painter every other control test in this package uses.
"""
from __future__ import annotations

import pytest

from emtk.widgets.axis import Axis, nice_ticks
from emtk.widgets.plot import Plot, begin_plot
from emtk.testing import RecordingPainter


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


def test_an_inverted_plot_puts_the_y_minimum_at_the_top():
    """Image rows run down the screen; a plot showing one says so with y_inverted."""
    plot = Plot(0.0, 0.0, 100.0, 50.0, x_range=(0.0, 1.0), y_range=(0.0, 10.0))
    plot.draw(RecordingPainter())
    assert plot._y_axis.to_pixels(0.0) == pytest.approx(50.0)

    plot.y_inverted = True
    plot.draw(RecordingPainter())
    assert plot._y_axis.to_pixels(0.0) == pytest.approx(0.0)
    assert plot._y_axis.to_pixels(10.0) == pytest.approx(50.0)


def test_a_non_finite_sample_breaks_the_line_and_leaves_the_range_alone():
    """Masked bins are a gap; joining their neighbours would invent data."""
    plot = Plot(0.0, 0.0, 100.0, 50.0)
    plot.line("s", [0.0, 1.0, 2.0, 3.0], [1.0, 2.0, float("nan"), 4.0])
    painter = RecordingPainter()
    plot.draw(painter)
    assert plot._y_axis.range == (1.0, 4.0)
    assert plot._x_axis.range == (0.0, 3.0)


def test_padding_widens_only_the_fitted_sides():
    axis = Axis(v_min=0.0)
    axis.fit([2.0, 12.0])
    axis.pad(0.1)
    assert axis.range == pytest.approx((0.0, 13.0))  # the fitted span (2, 12) plus 10 %


def test_an_underlay_is_drawn_after_the_gridlines_and_before_the_series():
    """A fit range shades the data it marks; drawn last it tinted every curve."""
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 200.0, 100.0, show_ticks=True)
    plot.line("decay", [0.0, 1.0, 2.0], [3.0, 2.0, 1.0], colour=(255, 0, 0))
    plot.underlays.append(lambda painter, _plot: painter.fill_rect(10.0, 0.0, 5.0, 100.0, (1, 2, 3, 40)))
    plot.draw(p)
    colours = [call[-1] for call in p.calls if call[0] in ("fill_rect", "fill_triangle")]
    underlay = colours.index((1, 2, 3, 40))
    assert (255, 0, 0) in colours[underlay:], "the series comes after the underlay"
    assert (255, 0, 0) not in colours[:underlay]


def test_the_tick_target_sets_how_many_gridlines_a_plot_gets():
    p = RecordingPainter()
    plot = Plot(0.0, 0.0, 400.0, 300.0, x_range=(0.0, 100.0), y_range=(0.0, 100.0), show_ticks=True)
    plot.x_tick_target = plot.y_tick_target = 10
    plot.show_y_tick_labels = False
    plot.draw(p)
    grid = [call for call in p.calls if call[0] == "fill_rect" and call[-1] == (255, 255, 255, 20)]
    assert len(grid) >= 18


def test_a_log_axis_ticks_on_decades_and_labels_nothing_fractional():
    axis = Axis(0.0, 4.0)
    axis.log_decades = True
    assert axis.ticks(4) == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert len(axis.minor_ticks()) == 4 * 8


def test_a_log_axis_under_two_decades_ticks_on_nice_values():
    """10**2.3 is 199.53: the ticks are nice *samples*, placed at their exponents."""
    import math

    axis = Axis(math.log10(150.0), math.log10(900.0))
    axis.log_decades = True
    values = [round(10.0 ** v, 6) for v in axis.ticks(4)]
    assert values and all(v == round(v) for v in values)
    assert all(150.0 <= v <= 900.0 for v in values)
