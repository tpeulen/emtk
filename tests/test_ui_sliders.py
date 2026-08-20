"""Painter-level tests for the slider family.

No GUI toolkit, no arrays -- the controls are arithmetic plus six drawing
operations, and every claim below is about the arithmetic. The ones worth
having are the ones a smoke test cannot make: that a vertical slider's minimum
is at the *bottom*, that a logarithmic slider's midpoint is the geometric mean
rather than the arithmetic one, and that a row of components drags one
component rather than whichever the pointer wandered over.
"""

from __future__ import annotations

import math

import pytest

from cmtk.widgets import sliders


class RecordingPainter:
    """Records the six operations instead of performing them."""

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[str] = []
        self.clips: list[tuple] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.fills.append((x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        self.strokes.append((x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        self.fills.append((x, y, w, h, stops[0] if stops else None))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)

    def push_clip(self, x, y, w, h) -> None:
        self.clips.append((x, y, w, h))

    def pop_clip(self) -> None:
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


ALL = [
    lambda: sliders.SliderScalar("v", 0.0, 1.0, 0.5),
    lambda: sliders.SliderInt("n", 0, 10, 3),
    lambda: sliders.VSliderFloat("v", 0.0, 1.0, 0.25),
    lambda: sliders.VSliderInt("n", 0, 4, 1),
    lambda: sliders.SliderAngle("a", math.pi / 4.0),
    lambda: sliders.SliderFloatN("xyz", [0.1, 0.2, 0.3], 0.0, 1.0),
    lambda: sliders.SliderIntN("rgb", [1, 2, 3], 0, 255),
    lambda: sliders.SliderScalar("log", 1.0, 1000.0, 10.0, logarithmic=True),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_slider_paints_and_balances_its_clips(build):
    """Every slider draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# Vertical sliders run bottom-to-top
# --------------------------------------------------------------------------
def test_vertical_float_puts_its_minimum_at_the_bottom():
    """Pressing the foot of a vertical track selects ``v_min``, not ``v_max``.

    No caption: a captioned vertical slider keeps a strip at the foot of the
    box for it, so the box's bottom edge would not be the track's.
    """
    slider = sliders.VSliderFloat("", 0.0, 1.0, 0.5)
    box = (0.0, 0.0, 30.0, 200.0)
    slider.draw(RecordingPainter(), *box)

    slider.press(15.0, 200.0, *box)
    assert slider.value == pytest.approx(0.0)

    slider.press(15.0, 0.0, *box)
    assert slider.value == pytest.approx(1.0)

    slider.press(15.0, 100.0, *box)
    assert slider.value == pytest.approx(0.5, abs=0.02)


def test_vertical_int_puts_its_minimum_at_the_bottom():
    """The same for the whole-number vertical slider, endpoints exact."""
    slider = sliders.VSliderInt("", 0, 10, 5)
    box = (0.0, 0.0, 30.0, 200.0)
    slider.draw(RecordingPainter(), *box)

    slider.press(15.0, 199.0, *box)
    assert slider.value == 0

    slider.press(15.0, 1.0, *box)
    assert slider.value == 10


def test_a_vertical_caption_is_not_part_of_the_track():
    """The caption strip at the foot takes room rather than overlapping."""
    slider = sliders.VSliderFloat("depth", 0.0, 1.0, 0.5)
    box = (0.0, 0.0, 40.0, 200.0)
    painter = RecordingPainter()
    slider.draw(painter, *box)

    frame_h = painter.strokes[0][3]
    assert frame_h < 200.0
    assert "depth" in painter.strings
    # A press in the caption strip is not a press on the track.
    assert slider.press(20.0, 199.0, *box) is False
    assert slider.value == pytest.approx(0.5)
    # And the track's own foot still reads as the minimum.
    assert slider.press(20.0, frame_h, *box) is True
    assert slider.value == pytest.approx(0.0)


def test_vertical_grab_is_drawn_low_for_a_low_value():
    """The grab follows the value *down* the box, which is the axis flip."""
    low = sliders.VSliderFloat("", 0.0, 1.0, 0.0)
    high = sliders.VSliderFloat("", 0.0, 1.0, 1.0)
    box = (0.0, 0.0, 30.0, 200.0)

    low_paint, high_paint = RecordingPainter(), RecordingPainter()
    low.draw(low_paint, *box)
    high.draw(high_paint, *box)

    low_grab_y = low_paint.fills[0][1]
    high_grab_y = high_paint.fills[0][1]
    assert low_grab_y > high_grab_y


# --------------------------------------------------------------------------
# Logarithmic scaling
# --------------------------------------------------------------------------
def test_log_midpoint_is_the_geometric_mean():
    """Half way along a 1..1000 log track is ~31.6, not 500.5."""
    slider = sliders.SliderScalar("", 1.0, 1000.0, 1.0, logarithmic=True)
    slider.set_fraction(0.5)
    assert slider.value == pytest.approx(math.sqrt(1000.0), rel=1e-3)

    linear = sliders.SliderScalar("", 1.0, 1000.0, 1.0)
    linear.set_fraction(0.5)
    assert linear.value == pytest.approx(500.5, rel=1e-3)


def test_log_ratio_and_value_are_inverses():
    """``ratio_from_value`` undoes ``value_from_ratio`` across the track."""
    for t in (0.1, 0.25, 0.5, 0.75, 0.9):
        value = sliders.value_from_ratio(t, 0.01, 100.0, log_epsilon=0.001)
        back = sliders.ratio_from_value(value, 0.01, 100.0, log_epsilon=0.001)
        assert back == pytest.approx(t, abs=1e-6)


def test_log_range_crossing_zero_can_still_reach_exactly_zero():
    """The dead-zone is what makes zero selectable on a -100..100 log slider."""
    slider = sliders.SliderScalar("", -100.0, 100.0, 1.0, fmt="%.1f", logarithmic=True)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)

    assert slider.deadzone > 0.0
    slider.set_fraction(0.5)
    assert slider.value == 0.0

    slider.set_fraction(0.75)
    assert slider.value > 0.0
    slider.set_fraction(0.25)
    assert slider.value < 0.0

    # And the ends are still the ends.
    slider.set_fraction(0.0)
    assert slider.value == pytest.approx(-100.0)
    slider.set_fraction(1.0)
    assert slider.value == pytest.approx(100.0)


def test_log_entirely_negative_range_is_monotonic():
    """A -1000..-1 log slider rises left to right instead of folding over."""
    slider = sliders.SliderScalar("", -1000.0, -1.0, -1000.0, logarithmic=True)
    seen = []
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        slider.set_fraction(t)
        seen.append(slider.value)
    assert seen == sorted(seen)
    assert seen[0] == pytest.approx(-1000.0)
    assert seen[-1] == pytest.approx(-1.0)
    assert seen[2] == pytest.approx(-math.sqrt(1000.0), rel=1e-3)


def test_log_slider_never_divides_by_zero_at_a_bound_on_the_epsilon():
    """A bound inside the fudge epsilon answers rather than raising."""
    slider = sliders.SliderScalar("", -0.0005, 10.0, 0.0, fmt="%.3f", logarithmic=True)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)
    for t in (0.0, 0.2, 0.5, 0.8, 1.0):
        slider.set_fraction(t)
        assert math.isfinite(slider.value)


# --------------------------------------------------------------------------
# Integer stepping
# --------------------------------------------------------------------------
def test_int_slider_hits_both_endpoints_exactly():
    """Fully left is ``v_min`` and fully right is ``v_max``, with no residue.

    No caption here on purpose: a caption is drawn outside the frame and is not
    part of the track, so the box's right edge would not be the track's.
    """
    slider = sliders.SliderInt("", -7, 23, 0)
    box = (10.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)

    slider.press(10.0, 9.0, *box)
    assert slider.value == -7
    assert isinstance(slider.value, int)

    slider.press(210.0, 9.0, *box)
    assert slider.value == 23
    assert isinstance(slider.value, int)


def test_int_slider_only_ever_holds_whole_numbers():
    """Dragging across the track never leaves a fraction behind."""
    slider = sliders.SliderInt("n", 0, 10, 0)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)
    slider.press(0.0, 9.0, *box)
    for step in range(0, 201, 5):
        slider.drag(float(step), 9.0, *box)
        assert slider.value == int(slider.value)
        assert 0 <= slider.value <= 10
    slider.release()


def test_int_grab_does_not_drift_between_the_ends():
    """Every step's grab centre is one grab-width apart from the next one's."""
    slider = sliders.SliderInt("", 0, 4, 0)
    box = (0.0, 0.0, 200.0, 18.0)
    centres = []
    for value in range(5):
        slider.set_value(value)
        painter = RecordingPainter()
        slider.draw(painter, *box)
        grab_x, _y, grab_w, _h, _c = painter.fills[0]
        centres.append(grab_x + grab_w * 0.5)
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    assert all(gap == pytest.approx(gaps[0]) for gap in gaps)
    assert gaps[0] > 0.0


# --------------------------------------------------------------------------
# Clamping
# --------------------------------------------------------------------------
def test_dragging_past_either_end_clamps_rather_than_running_on():
    """A drag that leaves the box stops at the bounds."""
    slider = sliders.SliderScalar("", 0.0, 1.0, 0.5)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)
    slider.press(100.0, 9.0, *box)

    slider.drag(100000.0, 9.0, *box)
    assert slider.value == pytest.approx(1.0)
    slider.drag(-100000.0, 9.0, *box)
    assert slider.value == pytest.approx(0.0)
    slider.release()


def test_a_value_outside_the_bounds_is_clamped_on_construction():
    """Constructing out of range does not produce an out-of-range slider."""
    assert sliders.SliderScalar("", 0.0, 1.0, 9.0).value == pytest.approx(1.0)
    assert sliders.SliderScalar("", 0.0, 1.0, -9.0).value == pytest.approx(0.0)
    assert sliders.SliderInt("", 2, 5, 99).value == 5


def test_a_backwards_range_runs_backwards():
    """``v_min > v_max`` puts the maximum on the left, as the reference allows."""
    slider = sliders.SliderScalar("", 1.0, 0.0, 0.5)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)
    slider.press(0.0, 9.0, *box)
    assert slider.value == pytest.approx(1.0)
    slider.press(200.0, 9.0, *box)
    assert slider.value == pytest.approx(0.0)


# --------------------------------------------------------------------------
# The N-component row
# --------------------------------------------------------------------------
def test_dragging_one_component_leaves_its_neighbours_alone():
    """Component 2 moves; 1 and 3 do not, even as the pointer runs past them."""
    row = sliders.SliderFloatN("xyz", [0.5, 0.5, 0.5], 0.0, 1.0)
    box = (0.0, 0.0, 300.0, 18.0)
    row.draw(RecordingPainter(), *box)

    cells = row._cells(box[0], box[2])
    middle_x = cells[1][0] + cells[1][1] * 0.5
    assert row.press(middle_x, 9.0, *box) == 1
    assert row.held == 1

    row.drag(cells[1][0], 9.0, *box)
    assert row.values[1] == pytest.approx(0.0)
    row.drag(cells[2][0] + cells[2][1], 9.0, *box)
    assert row.values[1] == pytest.approx(1.0)

    assert row.values[0] == pytest.approx(0.5)
    assert row.values[2] == pytest.approx(0.5)
    row.release()
    assert row.held is None


def test_a_press_that_misses_every_component_grabs_nothing():
    """The gaps between components are not part of any of them."""
    row = sliders.SliderFloatN("xyz", [0.5, 0.5, 0.5], 0.0, 1.0)
    box = (0.0, 0.0, 300.0, 18.0)
    row.draw(RecordingPainter(), *box)
    assert row.press(150.0, 100.0, *box) is None
    assert row.held is None
    assert row.drag(150.0, 9.0, *box) is False


def test_int_row_holds_whole_numbers_only():
    """``SliderIntN`` components step like ``SliderInt``."""
    row = sliders.SliderIntN("rgb", [0, 0, 0], 0, 255)
    box = (0.0, 0.0, 400.0, 18.0)
    row.draw(RecordingPainter(), *box)
    cells = row._cells(box[0], box[2])
    row.press(cells[2][0] + cells[2][1] * 0.5, 9.0, *box)
    assert all(isinstance(v, int) for v in row.values)
    assert row.values[0] == 0 and row.values[1] == 0
    assert 0 < row.values[2] < 255


# --------------------------------------------------------------------------
# Angles
# --------------------------------------------------------------------------
def test_angle_slider_stores_radians_and_shows_degrees():
    """The reference's default range is a full turn either way."""
    angle = sliders.SliderAngle("a", math.pi / 2.0)
    assert angle.v_min == pytest.approx(-360.0)
    assert angle.v_max == pytest.approx(+360.0)
    assert angle.degrees == pytest.approx(90.0)
    assert angle.radians == pytest.approx(math.pi / 2.0)
    assert angle.text == "90 deg"

    angle.radians = -math.pi
    assert angle.degrees == pytest.approx(-180.0)
    assert angle.radians == pytest.approx(-math.pi)


def test_angle_slider_rounds_to_the_degrees_it_displays():
    """``"%.0f deg"`` means whole degrees are stored, not merely shown."""
    angle = sliders.SliderAngle("a", 0.0)
    box = (0.0, 0.0, 200.0, 18.0)
    angle.draw(RecordingPainter(), *box)
    angle.press(133.0, 9.0, *box)
    assert angle.degrees == float(int(angle.degrees))


# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------
def test_a_press_that_misses_releases_the_grab():
    """A press elsewhere ends the hold rather than leaving it armed."""
    slider = sliders.SliderScalar("", 0.0, 1.0, 0.5)
    box = (0.0, 0.0, 200.0, 18.0)
    slider.draw(RecordingPainter(), *box)
    assert slider.press(100.0, 9.0, *box) is True
    assert slider.press(100.0, 900.0, *box) is False
    assert slider.drag(50.0, 9.0, *box) is False


def test_the_caption_is_drawn_after_the_track_and_shrinks_it():
    """A caption takes room from the frame instead of overlapping it."""
    painter = RecordingPainter()
    slider = sliders.SliderScalar("gamma", 0.0, 1.0, 1.0)
    slider.draw(painter, 0.0, 0.0, 200.0, 18.0)
    frame_w = painter.strokes[0][2]
    assert frame_w < 200.0
    assert "gamma" in painter.strings
    # The grab must stay inside the shrunken frame, not the original box.
    grab_x, _y, grab_w, _h, _c = painter.fills[0]
    assert grab_x + grab_w <= frame_w + 0.001
