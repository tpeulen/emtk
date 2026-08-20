"""Painter-level tests for drag-and-drop and the hover-delayed tooltip.

No GUI toolkit, no clock and no frame loop -- the drag is an object that is
handed presses, positions and a time, which is the whole reason the port does
not carry the reference implementation's per-frame global with it.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import dragdrop
from cmtk.widgets.dragdrop import (
    DELAY_NONE,
    DELAY_NORMAL,
    STATIONARY_DELAY,
    AcceptFlags,
    DelayedTooltip,
    DragDropContext,
    DragDropSource,
    DragDropTarget,
)


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


# The control box a drag starts from, and a target box well away from it.
SOURCE_BOX = (0.0, 0.0, 60.0, 20.0)
TARGET_BOX = (200.0, 100.0, 80.0, 40.0)


def start_drag(source: DragDropSource, ctx: DragDropContext) -> bool:
    """Press the source's box and pull the pointer past the drag threshold."""
    source.press(10.0, 10.0, *SOURCE_BOX)
    return source.drag(ctx, 90.0, 10.0)


def over_target(ctx: DragDropContext) -> None:
    """Put the cursor in the middle of :data:`TARGET_BOX`."""
    ctx.move(TARGET_BOX[0] + TARGET_BOX[2] * 0.5, TARGET_BOX[1] + TARGET_BOX[3] * 0.5)


# --------------------------------------------------------------------------
# Smoke
# --------------------------------------------------------------------------
def test_preview_and_highlight_paint_and_balance_their_clips():
    """Both drawing paths put something on screen and leave the clip stack alone."""
    painter = RecordingPainter()
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", data={"serial": 7}, label="Atom 7")
    target = DragDropTarget("selection", "atom")
    target.place(*TARGET_BOX)

    assert start_drag(source, ctx)
    over_target(ctx)
    ctx.hover(target)

    target.draw(painter, *TARGET_BOX)
    source.draw_preview(painter, ctx)

    assert painter.fills or painter.strokes
    assert "Atom 7" in painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------
def test_a_target_of_the_wrong_type_never_accepts():
    """A mismatched type is refused on hover and delivers nothing on release."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", data=7)
    target = DragDropTarget("shapes", "shape", flags=AcceptFlags.ACCEPT_BEFORE_DELIVERY)
    target.place(*TARGET_BOX)

    start_drag(source, ctx)
    over_target(ctx)

    assert ctx.hover(target) is None
    assert target.previewing is False
    assert ctx.payload.is_preview() is False
    assert ctx.accepting is None
    assert ctx.drop() is None
    assert ctx.active is False


def test_a_target_listing_several_types_takes_any_of_them():
    """Listing types is a whitelist, not an ordering."""
    ctx = DragDropContext()
    target = DragDropTarget("bin", ("shape", "atom", "bond"))
    target.place(*TARGET_BOX)

    start_drag(DragDropSource("atom-7", "atom"), ctx)
    over_target(ctx)
    ctx.hover(target)

    assert ctx.accepting is target
    assert ctx.payload.is_preview() is True


# --------------------------------------------------------------------------
# Preview versus delivery -- the distinction the port exists to keep
# --------------------------------------------------------------------------
def test_hovering_previews_and_only_the_release_delivers():
    """Preview and delivery are separate flags, and they are never both up."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", data={"serial": 7})
    target = DragDropTarget("selection", "atom")
    target.place(*TARGET_BOX)

    start_drag(source, ctx)
    over_target(ctx)
    ctx.hover(target)

    carried = ctx.payload
    assert carried.is_preview() is True
    assert carried.is_delivery() is False
    assert target.previewing is True

    delivered = ctx.drop()
    source.release()

    assert delivered is carried
    assert delivered.is_delivery() is True
    assert delivered.is_preview() is False
    assert delivered.data == {"serial": 7}


def test_releasing_away_from_every_target_clears_and_delivers_nothing():
    """A drag dropped on nothing still ends -- the payload does not linger."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", data=7)
    target = DragDropTarget("selection", "atom")
    target.place(*TARGET_BOX)

    start_drag(source, ctx)
    over_target(ctx)
    ctx.hover(target)
    assert target.previewing is True

    ctx.move(5.0, 5.0)
    ctx.hover(target)

    assert target.previewing is False
    assert ctx.payload.is_preview() is False
    assert ctx.drop() is None
    assert ctx.payload is None
    assert ctx.active is False


def test_the_payload_survives_the_drag_and_dies_with_it():
    """One payload object for the whole drag, gone the moment the button lifts."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", data=[1, 2, 3])

    start_drag(source, ctx)
    first = ctx.payload
    for step in range(5):
        ctx.move(100.0 + step * 10.0, 50.0)
        assert ctx.payload is first
        assert ctx.payload.data == [1, 2, 3]
    assert source.drag(ctx, 300.0, 50.0) is True
    assert ctx.payload is first

    ctx.drop()
    assert ctx.payload is None


def test_accept_before_delivery_hands_the_payload_over_early():
    """The flag changes what ``hover`` returns, and nothing else."""
    ctx = DragDropContext()
    plain = DragDropTarget("plain", "atom")
    peeking = DragDropTarget("peeking", "atom", flags=AcceptFlags.ACCEPT_BEFORE_DELIVERY)
    plain.place(*TARGET_BOX)
    peeking.place(*TARGET_BOX)

    start_drag(DragDropSource("atom-7", "atom", data="payload"), ctx)

    over_target(ctx)
    assert ctx.hover(plain) is None
    assert ctx.payload.is_preview() is True
    assert ctx.payload.is_delivery() is False

    over_target(ctx)
    early = ctx.hover(peeking)
    assert early is ctx.payload
    assert early.is_preview() is True
    assert early.is_delivery() is False
    assert early.data == "payload"

    assert ctx.drop() is early
    assert early.is_delivery() is True


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def test_a_press_is_not_a_drag_until_the_pointer_travels():
    """Clicking a draggable control stays a click."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom")

    assert source.press(10.0, 10.0, *SOURCE_BOX) is True
    assert source.armed is True
    assert source.drag(ctx, 12.0, 11.0) is False
    assert ctx.active is False

    assert source.drag(ctx, 40.0, 10.0) is True
    assert ctx.active is True
    assert ctx.payload.source_id == "atom-7"


def test_a_press_outside_the_box_arms_nothing():
    """A press elsewhere disarms the source rather than half-arming it."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom")

    assert source.press(500.0, 500.0, *SOURCE_BOX) is False
    assert source.armed is False
    assert source.drag(ctx, 600.0, 500.0) is False
    assert ctx.active is False


def test_a_source_without_an_id_needs_the_flag_that_invents_one():
    """The reference refuses an id-less source unless told to manufacture one."""
    ctx = DragDropContext()
    anonymous = DragDropSource(0, "atom")
    assert anonymous.effective_id() is None
    assert start_drag(anonymous, ctx) is False
    assert ctx.active is False

    allowed = DragDropSource(0, "atom", flags=AcceptFlags.SOURCE_ALLOW_NULL_ID)
    assert start_drag(allowed, ctx) is True
    assert ctx.active is True
    assert ctx.payload.source_id == allowed.effective_id()


def test_a_second_source_cannot_steal_a_drag_in_flight():
    """The reference only arms drag-and-drop when none is active."""
    ctx = DragDropContext()
    first = DragDropSource("atom-7", "atom", data="first")
    second = DragDropSource("atom-9", "atom", data="second")

    start_drag(first, ctx)
    assert ctx.begin(second) is None
    assert ctx.payload.data == "first"
    assert ctx.begin(first) is ctx.payload


def test_a_target_refuses_the_source_it_is():
    """A control cannot be dropped on itself."""
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom")
    itself = DragDropTarget("atom-7", "atom")
    itself.place(*TARGET_BOX)

    start_drag(source, ctx)
    over_target(ctx)

    assert itself.over(ctx) is False
    assert ctx.hover(itself) is None
    assert ctx.drop() is None


# --------------------------------------------------------------------------
# Overlap and highlight
# --------------------------------------------------------------------------
@pytest.mark.parametrize("inner_first", [False, True])
def test_the_smaller_of_two_overlapping_targets_wins(inner_first):
    """Nested targets need no ordering rule: the smallest box takes the drop."""
    ctx = DragDropContext()
    outer = DragDropTarget("outer", "atom")
    inner = DragDropTarget("inner", "atom")
    outer.place(0.0, 0.0, 400.0, 400.0)
    inner.place(220.0, 100.0, 40.0, 40.0)

    start_drag(DragDropSource("atom-7", "atom"), ctx)
    over_target(ctx)
    for target in ((inner, outer) if inner_first else (outer, inner)):
        ctx.hover(target)

    assert ctx.accepting is inner
    assert inner.previewing is True
    assert outer.previewing is False
    assert ctx.drop().is_delivery() is True


def test_a_target_can_accept_without_drawing_the_default_highlight():
    """``AcceptNoDrawDefaultRect`` suppresses the rectangle, not the accept."""
    painter = RecordingPainter()
    ctx = DragDropContext()
    target = DragDropTarget("quiet", "atom", flags=AcceptFlags.ACCEPT_NO_DRAW_DEFAULT_RECT)
    target.place(*TARGET_BOX)

    start_drag(DragDropSource("atom-7", "atom"), ctx)
    over_target(ctx)
    ctx.hover(target)

    assert ctx.accepting is target
    assert ctx.payload.is_preview() is True
    assert target.previewing is False

    target.draw(painter, *TARGET_BOX)
    assert painter.fills == [] and painter.strokes == []
    assert ctx.drop().is_delivery() is True


@pytest.mark.parametrize(
    "source_flags,target_flags",
    [
        (AcceptFlags.SOURCE_NO_PREVIEW_TOOLTIP, AcceptFlags.NONE),
        (AcceptFlags.NONE, AcceptFlags.ACCEPT_NO_PREVIEW_TOOLTIP),
    ],
)
def test_either_end_of_the_drag_can_hide_the_preview(source_flags, target_flags):
    """The source can decline to draw one; the target can ask it not to."""
    painter = RecordingPainter()
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", label="Atom 7", flags=source_flags)
    target = DragDropTarget("selection", "atom", flags=target_flags)
    target.place(*TARGET_BOX)

    start_drag(source, ctx)
    over_target(ctx)
    ctx.hover(target)
    source.draw_preview(painter, ctx)

    assert painter.strings == []
    assert painter.clips == []


def test_nothing_is_previewed_when_nothing_is_being_dragged():
    """Every drawing path early-outs cleanly with an idle context."""
    painter = RecordingPainter()
    ctx = DragDropContext()
    source = DragDropSource("atom-7", "atom", label="Atom 7")
    target = DragDropTarget("selection", "atom")

    source.draw_preview(painter, ctx)
    target.draw(painter, *TARGET_BOX)

    assert painter.strings == []
    assert painter.fills == [] and painter.strokes == []
    assert painter.clips == []
    assert ctx.hover(target) is None


# --------------------------------------------------------------------------
# The delayed tooltip
# --------------------------------------------------------------------------
def test_a_delayed_tooltip_waits_out_its_delay():
    """Nothing before the delay, the tooltip after it."""
    tip = DelayedTooltip("Residue 42", delay=DELAY_NORMAL)

    assert tip.hover(10.0, 10.0, 0.0) is False
    assert tip.hover(10.0, 10.0, 0.2) is False
    assert tip.unlocked is True
    assert tip.hover(10.0, 10.0, 0.39) is False
    assert tip.hover(10.0, 10.0, 0.41) is True
    assert tip.visible is True


def test_a_moving_cursor_never_satisfies_the_stationary_rule():
    """Sweeping past an item shows nothing, however long the sweep lasts."""
    tip = DelayedTooltip("Residue 42", delay=DELAY_NONE)

    now = 0.0
    x = 10.0
    for _ in range(20):
        now += 0.1
        x += 30.0
        assert tip.hover(x, 10.0, now) is False
    assert tip.unlocked is False

    # The cursor stops. The stationary timer starts from the last movement.
    assert tip.hover(x, 10.0, now + 0.05) is False
    assert tip.hover(x, 10.0, now + STATIONARY_DELAY + 0.01) is True
    assert tip.unlocked is True


def test_the_stationary_rule_is_not_the_delay():
    """A zero delay still waits for the cursor to stop; the two are separate."""
    stationary = DelayedTooltip("Residue 42", delay=DELAY_NONE, stationary=True)
    immediate = DelayedTooltip("Residue 42", delay=DELAY_NONE, stationary=False)

    assert stationary.hover(10.0, 10.0, 0.0) is False
    assert immediate.hover(10.0, 10.0, 0.0) is True

    assert stationary.hover(10.0, 10.0, STATIONARY_DELAY + 0.01) is True


def test_a_tooltip_stays_up_once_the_cursor_has_stopped_once():
    """The reference unlocks the item, not the sample: a nudge does not hide it."""
    tip = DelayedTooltip("Residue 42", delay=DELAY_NONE)

    tip.hover(10.0, 10.0, 0.0)
    assert tip.hover(10.0, 10.0, 0.2) is True
    assert tip.hover(60.0, 10.0, 0.25) is True
    assert tip.unlocked is True


def test_leaving_the_item_resets_both_timers():
    """Coming back starts the wait again rather than resuming it."""
    tip = DelayedTooltip("Residue 42", delay=DELAY_NORMAL)

    tip.hover(10.0, 10.0, 0.0)
    tip.hover(10.0, 10.0, 0.5)
    assert tip.visible is True

    tip.leave()
    assert tip.visible is False
    assert tip.unlocked is False

    assert tip.hover(10.0, 10.0, 0.6) is False
    assert tip.hover(10.0, 10.0, 1.05) is True


def test_a_delayed_tooltip_draws_only_once_it_is_visible():
    """``draw_if_visible`` is the reference's ``SetItemTooltip``: one call, no drift."""
    painter = RecordingPainter()
    tip = DelayedTooltip(["Residue 42", "chain A"], delay=DELAY_NORMAL)

    tip.hover(10.0, 10.0, 0.0)
    assert tip.draw_if_visible(painter) is False
    assert painter.strings == []

    tip.hover(10.0, 10.0, 0.6)
    assert tip.draw_if_visible(painter) is True
    assert painter.strings == ["Residue 42", "chain A"]
    assert painter.clips == []


def test_the_tooltip_box_sits_off_the_cursor():
    """The box is offset so the pointer does not cover its first character."""
    painter = RecordingPainter()
    tip = DelayedTooltip("Residue 42")
    tip.draw_at(painter, 100.0, 200.0)

    assert painter.strokes, "the tooltip frame is drawn"
    box_x, box_y = painter.strokes[0][0], painter.strokes[0][1]
    assert box_x > 100.0 and box_y > 200.0
    assert (box_x, box_y) == (100.0 + dragdrop._CURSOR_OFFSET[0],
                              200.0 + dragdrop._CURSOR_OFFSET[1])
