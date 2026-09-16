"""Painter-level tests for the drag family.

The tests that matter here are the ones that separate a drag from a slider.
A slider reads the pointer's *position* against its track; a drag reads the
*delta* since the last event and has no track at all -- so the same gesture
started anywhere on screen must produce the same change, and a gesture that
runs off the end of the box must keep working. Everything else (the
accumulator that lets a sub-unit-per-pixel integer drag move at all, the
range pair that cannot cross, the unbounded drag that never clamps) is a
behaviour with a classic bug attached, and each one has a test naming it.
"""

from __future__ import annotations

import pytest

from emtk.widgets import drag


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


BOX = (0.0, 0.0, 200.0, 18.0)

ALL = [
    lambda: drag.DragFloat("v", 0.5, v_speed=0.01, v_min=0.0, v_max=1.0),
    lambda: drag.DragInt("n", 3, v_min=0, v_max=10),
    lambda: drag.DragFloatN("pos", (1.0, 2.0, 3.0)),
    lambda: drag.DragIntN("cell", (1, 2)),
    lambda: drag.DragFloatRange2("span", 0.2, 0.8, v_min=0.0, v_max=1.0),
    lambda: drag.DragIntRange2("bins", 2, 8, v_min=0, v_max=10),
]


def _scrub(widget, start_x, distance, steps=1, box=BOX):
    """Press at *start_x* and drag *distance* pixels in *steps* events."""
    box_x, box_y, box_w, box_h = box
    y = box_y + box_h * 0.5
    widget.press(start_x, y, box_x, box_y, box_w, box_h)
    changed = False
    for step in range(1, steps + 1):
        here = start_x + distance * step / steps
        changed = widget.drag(here, y, box_x, box_y, box_w, box_h) or changed
    return changed


# --------------------------------------------------------------------------
# Smoke
# --------------------------------------------------------------------------
@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_drag_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# The one that proves it is not a slider
# --------------------------------------------------------------------------
def test_the_value_follows_the_delta_not_the_position():
    """The same distance dragged from two different places moves it equally.

    A slider would put the first one near its left end and the second one off
    the right; a drag does not know where its box is once the gesture starts.
    """
    near = drag.DragFloat("v", 10.0, v_speed=1.0)
    far = drag.DragFloat("v", 10.0, v_speed=1.0)
    _scrub(near, 5.0, 40.0)
    _scrub(far, 190.0, 40.0)
    assert near.value == far.value
    assert near.value > 10.0


def test_a_drag_keeps_working_outside_its_box():
    """Leaving the box does not end the gesture, and does not clamp the value."""
    widget = drag.DragFloat("v", 0.0, v_speed=1.0)
    _scrub(widget, 100.0, 400.0, steps=4)
    assert widget.value > 200.0


def test_a_click_that_does_not_travel_changes_nothing():
    """Under the drag threshold there is no drag -- there is a click."""
    widget = drag.DragFloat("v", 4.0, v_speed=1.0)
    assert _scrub(widget, 100.0, 2.0, steps=2) is False
    assert widget.value == 4.0


def test_release_ends_the_gesture():
    """After a release the pointer is just a pointer again."""
    widget = drag.DragFloat("v", 0.0, v_speed=1.0)
    _scrub(widget, 50.0, 30.0)
    moved = widget.value
    widget.release()
    assert widget.drag(500.0, 9.0, *BOX) is False
    assert widget.value == moved


def test_a_press_on_the_caption_does_not_grab():
    """Only the frame is interactive; the label beside it is not."""
    painter = RecordingPainter()
    widget = drag.DragFloat("a long caption", 1.0, v_speed=1.0)
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert widget.press(198.0, 9.0, *BOX) is False
    assert widget.drag(240.0, 9.0, *BOX) is False
    assert widget.value == 1.0


# --------------------------------------------------------------------------
# Speed
# --------------------------------------------------------------------------
def test_v_speed_scales_the_delta():
    """Four times the speed over the same distance is four times the change."""
    slow = drag.DragFloat("v", 0.0, v_speed=0.5)
    fast = drag.DragFloat("v", 0.0, v_speed=2.0)
    _scrub(slow, 20.0, 40.0)
    _scrub(fast, 20.0, 40.0)
    assert fast.value == pytest.approx(slow.value * 4.0)


def test_zero_speed_is_derived_from_the_range():
    """A speed of zero asks for one hundredth of the range -- if there is one."""
    bounded = drag.DragFloat("v", 0.0, v_speed=0.0, v_min=0.0, v_max=100.0)
    assert bounded.effective_speed == pytest.approx(1.0)
    # Unbounded, the derivation has no range to work from and nothing moves.
    unbounded = drag.DragFloat("v", 0.0, v_speed=0.0)
    assert unbounded.effective_speed == 0.0
    _scrub(unbounded, 20.0, 60.0)
    assert unbounded.value == 0.0


# --------------------------------------------------------------------------
# The accumulator
# --------------------------------------------------------------------------
def test_a_slow_integer_drag_eventually_moves_by_one():
    """The classic bug: rounding each event on its own never moves at all.

    At a twentieth of a unit per pixel every single event is worth 0.05, which
    truncates to zero. Only the carried remainder makes the value move.
    """
    widget = drag.DragInt("n", 0, v_speed=0.05)
    widget.press(50.0, 9.0, *BOX)
    for step in range(1, 9):  # 8 px past the anchor: 5 of them count
        widget.drag(50.0 + step, 9.0, *BOX)
    assert widget.value == 0
    for step in range(9, 121):
        widget.drag(50.0 + step, 9.0, *BOX)
    assert widget.value >= 1
    assert widget.value == int((120.0 - widget.drag_threshold) * 0.05)


def test_the_accumulator_is_per_component():
    """A row's remainder must not leak from one component into the next."""
    row = drag.DragIntN("v", (0, 0), v_speed=0.05)
    painter = RecordingPainter()
    row.draw(painter, 0.0, 0.0, 200.0, 18.0)
    row.press(10.0, 9.0, *BOX)
    for step in range(1, 61):
        row.drag(10.0 + step, 9.0, *BOX)
    row.release()
    assert row.values[0] >= 1
    assert row.values[1] == 0


def test_an_integer_drag_stays_an_integer():
    """Nothing in the accumulator leaks a float into the value."""
    widget = drag.DragInt("n", 0, v_speed=0.37)
    _scrub(widget, 10.0, 90.0, steps=90)
    assert isinstance(widget.value, int)


# --------------------------------------------------------------------------
# Bounds
# --------------------------------------------------------------------------
def test_an_unbounded_drag_has_no_clamp():
    """``v_min >= v_max`` means no bound, which is what the defaults are."""
    widget = drag.DragFloat("v", 0.0, v_speed=1.0)
    assert widget.is_bounded is False
    _scrub(widget, 10.0, 5000.0, steps=10)
    assert widget.value > 4000.0
    _scrub(widget, 10.0, -9000.0, steps=10)
    assert widget.value < -3000.0


def test_a_bounded_drag_stops_at_its_ends():
    """And a bounded one is confined to both."""
    widget = drag.DragFloat("v", 5.0, v_speed=1.0, v_min=0.0, v_max=10.0)
    _scrub(widget, 10.0, 500.0, steps=5)
    assert widget.value == pytest.approx(10.0)
    _scrub(widget, 10.0, -500.0, steps=5)
    assert widget.value == pytest.approx(0.0)


def test_a_value_already_past_the_limit_is_not_yanked_back():
    """Pushing further out from outside leaves the value where it is.

    The reference refuses to clamp in that case so that a value of 300 in a
    0..255 control survives a drag to the right.
    """
    widget = drag.DragFloat("v", 5.0, v_speed=1.0, v_min=0.0, v_max=10.0)
    widget.value = 300.0
    _scrub(widget, 10.0, 50.0)
    assert widget.value == 300.0
    # Dragging back inward does clamp it, because now it is heading in.
    _scrub(widget, 10.0, -50.0)
    assert widget.value == pytest.approx(10.0)


def test_wrap_around_comes_out_the_other_end():
    """With wrap on, past the top is back at the bottom and keeps going."""
    widget = drag.DragInt("n", 9, v_speed=1.0, v_min=0, v_max=9, wrap=True)
    widget.press(10.0, 9.0, *BOX)
    for step in range(1, 4):  # inside the threshold: nothing yet
        widget.drag(10.0 + step, 9.0, *BOX)
    assert widget.value == 9
    widget.drag(14.0, 9.0, *BOX)
    assert widget.value == 0
    widget.drag(15.0, 9.0, *BOX)
    assert widget.value == 1


# --------------------------------------------------------------------------
# Rounding and formatting
# --------------------------------------------------------------------------
def test_the_value_is_rounded_to_what_the_format_shows():
    """A control that displays one decimal holds one decimal."""
    widget = drag.DragFloat("v", 0.0, v_speed=0.01, fmt="%.1f")
    _scrub(widget, 10.0, 100.0, steps=20)
    assert widget.value == pytest.approx(round(widget.value, 1))


def test_rounding_does_not_swallow_the_remainder():
    """Rounding pays its change back to the accumulator, so slow drags move.

    At a hundredth of a unit per pixel with one decimal shown, every event
    rounds away -- unless what rounding removed is carried forward.
    """
    widget = drag.DragFloat("v", 0.0, v_speed=0.01, fmt="%.1f")
    _scrub(widget, 10.0, 200.0, steps=200)
    assert widget.value == pytest.approx(round((200.0 - widget.drag_threshold) * 0.01, 1),
                                         abs=0.11)


def test_a_decorated_format_still_rounds():
    """Prose around the spec is display only; it must not defeat the rounding."""
    widget = drag.DragFloat("v", 0.0, v_speed=0.01, fmt="%.1f nm")
    _scrub(widget, 10.0, 100.0, steps=20)
    assert widget.value == pytest.approx(round(widget.value, 1))
    painter = RecordingPainter()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert any("nm" in one for one in painter.strings)


# --------------------------------------------------------------------------
# Logarithmic
# --------------------------------------------------------------------------
def test_a_logarithmic_drag_multiplies_rather_than_adds():
    """Equal distances give equal *ratios*, which is the point of the flag."""
    widget = drag.DragFloat(
        "v", 1.0, v_speed=1.0, v_min=0.01, v_max=1000.0, fmt="%.4f", logarithmic=True
    )
    seen = [widget.value]
    for _ in range(3):
        _scrub(widget, 10.0, 40.0)
        widget.release()
        seen.append(widget.value)
    ratios = [seen[i + 1] / seen[i] for i in range(len(seen) - 1)]
    assert min(ratios) > 1.0
    assert max(ratios) == pytest.approx(min(ratios), rel=0.05)


def test_a_logarithmic_range_can_cross_zero():
    """A range spanning zero is scaled in two halves and stays inside itself."""
    widget = drag.DragFloat(
        "v", -1.0, v_speed=1.0, v_min=-100.0, v_max=100.0, fmt="%.3f", logarithmic=True
    )
    _scrub(widget, 10.0, 400.0, steps=8)
    assert -100.0 <= widget.value <= 100.0
    assert widget.value > -1.0


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------
def test_a_row_scrubs_only_the_component_it_was_grabbed_by():
    """The press picks a component; the drag never wanders to its neighbour."""
    painter = RecordingPainter()
    row = drag.DragFloatN("pos", (0.0, 0.0, 0.0), v_speed=1.0)
    row.draw(painter, 0.0, 0.0, 200.0, 18.0)
    _body, cell = drag._split_cells(200.0, row._label_w, 3)
    middle = cell + drag._INNER_SPACING + cell * 0.5
    assert row.press(middle, 9.0, *BOX) == 1
    row.drag(middle + 30.0, 9.0, *BOX)
    assert row.values[0] == 0.0
    assert row.values[1] > 0.0
    assert row.values[2] == 0.0


def test_a_row_reports_which_component_is_held():
    """And forgets it on release."""
    painter = RecordingPainter()
    row = drag.DragIntN("v", (0, 0, 0, 0))
    row.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert row.press(5.0, 9.0, *BOX) == 0
    assert row.active == 0
    row.release()
    assert row.active is None
    assert row.drag(80.0, 9.0, *BOX) is False


# --------------------------------------------------------------------------
# Ranges
# --------------------------------------------------------------------------
def test_a_range_low_can_never_exceed_its_high():
    """Dragged as far right as it goes, the low half stops at the high one."""
    painter = RecordingPainter()
    pair = drag.DragFloatRange2("span", 0.2, 0.8, v_speed=0.1, v_min=0.0, v_max=10.0)
    pair.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert pair.press(5.0, 9.0, *BOX) == 0
    for step in range(1, 40):
        pair.drag(5.0 + step * 10.0, 9.0, *BOX)
        assert pair.low <= pair.high
    assert pair.low == pytest.approx(pair.high)


def test_a_range_high_can_never_fall_below_its_low():
    """And the other way round, which is a separate bound and a separate bug."""
    painter = RecordingPainter()
    pair = drag.DragIntRange2("bins", 3, 9, v_speed=1.0, v_min=0, v_max=20)
    pair.draw(painter, 0.0, 0.0, 200.0, 18.0)
    _body, cell = drag._split_cells(200.0, pair._label_w, 2)
    grab = cell + drag._INNER_SPACING + 2.0
    assert pair.press(grab, 9.0, *BOX) == 1
    for step in range(1, 40):
        pair.drag(grab - step * 5.0, 9.0, *BOX)
        assert pair.low <= pair.high
    assert pair.high == pair.low == 3


def test_a_range_half_with_nowhere_to_go_is_read_only():
    """Bounds that have met make the half inert rather than jittery."""
    pair = drag.DragIntRange2("bins", 0, 0, v_speed=1.0, v_min=0, v_max=20)
    assert pair.low_drag.read_only is True
    painter = RecordingPainter()
    pair.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert pair.press(5.0, 9.0, *BOX) is None


def test_an_unbounded_range_is_still_bounded_by_itself():
    """With no outer range the pair keeps its own order and nothing else."""
    painter = RecordingPainter()
    pair = drag.DragFloatRange2("span", -50.0, 50.0, v_speed=1.0)
    pair.draw(painter, 0.0, 0.0, 200.0, 18.0)
    _body, cell = drag._split_cells(200.0, pair._label_w, 2)
    grab = cell + drag._INNER_SPACING + 2.0
    pair.press(grab, 9.0, *BOX)
    for step in range(1, 20):
        pair.drag(grab + step * 50.0, 9.0, *BOX)
    assert pair.high > 500.0
    assert pair.low == -50.0


def test_setting_a_range_half_across_the_other_is_corrected():
    """Assignment goes through the same bounds a drag does."""
    pair = drag.DragFloatRange2("span", 0.2, 0.8, v_min=0.0, v_max=1.0)
    pair.low = 5.0
    assert pair.low == pytest.approx(0.8)
    pair.high = -5.0
    assert pair.high == pytest.approx(0.8)


# --------------------------------------------------------------------------
# Typing a value
# --------------------------------------------------------------------------
def test_typing_a_value_replaces_it():
    """The explicit stand-in for the reference's ctrl-click."""
    widget = drag.DragFloat("v", 1.25, v_speed=1.0, fmt="%.2f nm")
    assert widget.begin_text_edit() == "1.25"
    assert widget.editing is True
    widget.set_text_buffer("42.5")
    assert widget.commit_text_edit() is True
    assert widget.value == pytest.approx(42.5)
    assert widget.editing is False


def test_a_field_that_holds_no_number_leaves_the_value_alone():
    """An emptied field must not silently mean zero."""
    widget = drag.DragFloat("v", 7.0, v_speed=1.0)
    widget.begin_text_edit()
    widget.set_text_buffer("   ")
    assert widget.commit_text_edit() is False
    assert widget.value == pytest.approx(7.0)


def test_a_cancelled_edit_keeps_the_value_and_the_field_is_drawn():
    """Cancelling reverts, and while editing the frame shows the buffer."""
    painter = RecordingPainter()
    widget = drag.DragFloat("v", 3.0, v_speed=1.0)
    widget.begin_text_edit()
    widget.set_text_buffer("99")
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert "99" in painter.strings
    assert painter.clips == []
    widget.cancel_text_edit()
    assert widget.value == pytest.approx(3.0)
    assert widget.editing is False


def test_typed_input_is_clamped_only_when_asked():
    """The reference lets typing exceed a range that dragging cannot."""
    loose = drag.DragInt("n", 5, v_min=0, v_max=10)
    loose.begin_text_edit()
    loose.set_text_buffer("500")
    loose.commit_text_edit()
    assert loose.value == 500

    strict = drag.DragInt("n", 5, v_min=0, v_max=10, clamp_on_input=True)
    strict.begin_text_edit()
    strict.set_text_buffer("500")
    strict.commit_text_edit()
    assert strict.value == 10


# --------------------------------------------------------------------------
# The format helpers, which the rounding rests on
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fmt, precision",
    [("%.3f", 3), ("%d", 1), ("hello %.1f", 1), ("%.2e", -1), ("no spec", 7), ("%%", 7)],
)
def test_format_precision_reads_the_spec(fmt, precision):
    """Ported from the reference's format parser, defaults included."""
    assert drag._format_precision(fmt, 7 if precision == 7 else precision) == precision


@pytest.mark.parametrize(
    "fmt, spec",
    [("%.3f", "%.3f"), ("radius %.2f nm", "%.2f"), ("100%%", ""), ("%d px", "%d")],
)
def test_decorations_are_trimmed_before_a_value_is_parsed_back(fmt, spec):
    """A field has to offer something that parses, not a sentence."""
    assert drag._trim_decorations(fmt) == spec
