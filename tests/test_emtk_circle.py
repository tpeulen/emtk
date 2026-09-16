"""``CirclePlot``: the Circos layout, ported from pyCirclize.

The port keeps the reference's arithmetic and drops its canvas: pyCirclize
builds matplotlib `Patch` objects on a `PolarAxes`, and there is no polar axis
in emtk, so every shape is projected here and emitted as triangles. What is
worth pinning is therefore the arithmetic -- sectors sharing the circle in
proportion to their sizes with a gap between them, the data-to-angle mapping,
north at the top with angles running clockwise, and the Bezier control point
that gives a chord its shape -- plus the two things the projection has to get
right that the reference never had to: a ring segment and a ribbon are not
convex, so neither may be filled as a fan.
"""
from __future__ import annotations

import math

import pytest

from emtk.testing import RecordingPainter
from emtk.widgets.circle import MAX_R, CirclePlot, begin_circle


def _plot(**kwargs) -> CirclePlot:
    return CirclePlot(0.0, 0.0, 400.0, 400.0, **kwargs)


def test_sectors_share_the_circle_in_proportion_to_their_sizes():
    """``Circos.__init__``: size ratio of the degrees left after the gaps."""
    circle = _plot(space=0.0)
    circle.sector("a", 30)
    circle.sector("b", 10)
    circle._lay_out()
    first, second = circle.sectors
    span = lambda s: s.rad_end - s.rad_start          # noqa: E731
    assert span(first) == pytest.approx(2 * math.pi * 0.75)
    assert span(second) == pytest.approx(2 * math.pi * 0.25)
    assert first.rad_start == pytest.approx(0.0)
    assert second.rad_start == pytest.approx(first.rad_end)


def test_the_gap_between_sectors_comes_out_of_the_circle():
    circle = _plot(space=10.0)
    circle.sector("a", 1)
    circle.sector("b", 1)
    circle._lay_out()
    first, second = circle.sectors
    gap = second.rad_start - first.rad_end
    assert gap == pytest.approx(math.radians(10.0))
    drawn = sum(s.rad_end - s.rad_start for s in circle.sectors)
    assert drawn == pytest.approx(math.radians(360.0 - 2 * 10.0))


def test_endspace_false_closes_the_ring():
    circle = _plot(space=10.0, endspace=False)
    circle.sector("a", 1)
    circle.sector("b", 1)
    circle._lay_out()
    assert circle.sectors[-1].rad_end == pytest.approx(math.radians(360.0))


def test_a_coordinate_maps_along_its_sector():
    """``Sector.x_to_rad``."""
    circle = _plot(space=0.0)
    circle.sector("chain", (10, 20))
    sector = circle.get_sector("chain")
    assert sector.x_to_rad(10) == pytest.approx(sector.rad_start)
    assert sector.x_to_rad(20) == pytest.approx(sector.rad_end)
    assert sector.x_to_rad(15) == pytest.approx((sector.rad_start + sector.rad_end) / 2)


def test_an_anticlockwise_sector_runs_the_other_way():
    circle = _plot(space=0.0)
    circle.sector("chain", (10, 20), clockwise=False)
    sector = circle.get_sector("chain")
    assert sector.x_to_rad(10) == pytest.approx(sector.rad_end)
    assert sector.x_to_rad(20) == pytest.approx(sector.rad_start)


def test_a_coordinate_outside_the_sector_is_clamped_not_raised_over():
    """The reference raises; this draws a document somebody is editing."""
    circle = _plot()
    circle.sector("chain", (10, 20))
    sector = circle.get_sector("chain")
    assert sector.x_to_rad(-5) == pytest.approx(sector.rad_start)
    assert sector.x_to_rad(999) == pytest.approx(sector.rad_end)


def test_zero_is_north_and_angles_run_clockwise():
    """``set_theta_zero_location("N")`` + ``set_theta_direction(-1)``."""
    circle = _plot()
    cx, cy = circle.centre
    top = circle.to_pixels(0.0, MAX_R)
    right = circle.to_pixels(math.pi / 2, MAX_R)
    bottom = circle.to_pixels(math.pi, MAX_R)
    assert top[0] == pytest.approx(cx) and top[1] < cy
    assert right[1] == pytest.approx(cy) and right[0] > cx
    assert bottom[0] == pytest.approx(cx) and bottom[1] > cy


def test_the_radius_space_is_the_references():
    """0 at the centre, 100 at the edge of the box's shorter side."""
    circle = CirclePlot(0.0, 0.0, 400.0, 300.0)
    cx, cy = circle.centre
    assert circle.to_pixels(0.0, 0.0) == pytest.approx((cx, cy))
    assert circle.to_pixels(0.0, MAX_R)[1] == pytest.approx(cy - 150.0)


def test_a_ring_segment_is_not_filled_as_a_fan():
    """A fan from one vertex paints across the hole; a strip does not.

    Checked where it shows: no triangle of a band drawn on the far side of the
    circle may touch the centre.
    """
    circle = _plot(space=0.0)
    circle.sector("a", 1)
    p = RecordingPainter()
    circle.draw(p)
    cx, cy = circle.centre
    triangles = [call for call in p.calls if call[0] == "fill_triangle"]
    assert triangles
    for _kind, p0, p1, p2, _colour in triangles:
        for point in (p0, p1, p2):
            distance = math.hypot(point[0] - cx, point[1] - cy)
            assert distance > 10.0, "a band's triangle reaches the centre"


def test_a_point_to_point_link_is_a_line_and_a_region_link_is_a_ribbon():
    circle = _plot()
    circle.sector("a", 100)
    circle.link(("a", 10, 10), ("a", 90, 90))
    assert circle._links[0].width > 0.0, "a zero-width chord should draw as a line"
    circle.link(("a", 10, 30), ("a", 60, 90))
    assert circle._links[1].width == 0.0, "a chord with feet should draw as a ribbon"


def test_the_bezier_control_point_follows_the_height_ratio():
    """``BezierCurveLink``: 0.5 through the centre, less hugs the near side."""
    circle = _plot()
    circle.sector("a", 100)
    start, end = circle.to_pixels(0.0, 80.0), circle.to_pixels(math.pi, 80.0)
    middle = circle._bezier(start, end, 0.0, math.pi, 0.5)[len(circle._bezier(start, end, 0.0, math.pi, 0.5)) // 2]
    cx, cy = circle.centre
    assert math.hypot(middle[0] - cx, middle[1] - cy) < 5.0

    hugging = circle._bezier(start, end, 0.0, math.pi, 0.0)
    apex = hugging[len(hugging) // 2]
    assert math.hypot(apex[0] - cx, apex[1] - cy) > 20.0


def test_a_link_to_a_sector_that_is_not_there_is_ignored():
    circle = _plot()
    circle.sector("a", 10)
    circle.link(("a", 1, 1), ("nope", 1, 1))
    assert circle._links == []


def test_sectors_with_no_size_still_get_a_share_of_the_circle():
    """One position per chain: the labels are the point, and they need room."""
    circle = _plot()
    circle.sector("a", (5, 5))
    circle.sector("b", (7, 7))
    circle._lay_out()
    assert all(s.rad_end > s.rad_start for s in circle.sectors)


def test_the_context_manager_draws_on_exit():
    p = RecordingPainter()
    with begin_circle(p, 0, 0, 200, 200) as circle:
        circle.sector("a", 10)
        assert not p.calls, "nothing may be drawn before the block ends"
    assert p.calls, "the block ended and nothing was drawn"


def test_labels_go_to_the_side_of_the_circle_they_are_on():
    """No rotated text in the painter, so the alignment carries it."""
    from emtk.painter import ALIGN_LEFT, ALIGN_RIGHT

    circle = _plot(space=0.0)
    circle.sector("right", 1)
    circle.sector("left", 1)
    p = RecordingPainter()
    circle.draw(p)
    texts = {call[6]: call[5] for call in p.calls if call[0] == "text"}
    assert texts["right"] & ALIGN_LEFT, "a label on the right should read outward"
    assert texts["left"] & ALIGN_RIGHT, "a label on the left should read outward"
