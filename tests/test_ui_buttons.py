"""Painter-level tests for the button family.

Behaviour, not absence of crash: the states the reference defines, the bitmask
cycle it produces, the arrow actually pointing where it says, and the one
control whose contract is that it draws nothing at all.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import buttons


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
    lambda: buttons.SmallButton("go"),
    lambda: buttons.InvisibleButton("drag-area"),
    lambda: buttons.ArrowButton(buttons.DIR_RIGHT),
    lambda: buttons.CheckboxFlags("bits", 0b0101, 0b0111),
    lambda: buttons.RadioButton("one", True),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control survives a draw and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    control = build()
    control.draw(painter, *BOX)
    assert painter.clips == []
    if not isinstance(control, buttons.InvisibleButton):
        assert painter.fills or painter.strokes or painter.strings


# ---------------------------------------------------------------- ButtonState
def test_press_inside_holds_and_activates():
    """A press inside takes the hold and reports itself as the activating one."""
    state = buttons.ButtonState()
    assert state.press(10.0, 9.0, *BOX) is True
    assert (state.held, state.hovered, state.activated) == (True, True, True)


def test_second_press_holds_but_does_not_re_activate():
    """Activation is the transition, not the state -- the reference's IsItemActivated."""
    state = buttons.ButtonState()
    state.press(10.0, 9.0, *BOX)
    state.press(11.0, 9.0, *BOX)
    assert state.held is True
    assert state.activated is False


def test_press_outside_clears_the_held_state():
    """A press that misses lets go of a control that was holding."""
    state = buttons.ButtonState()
    state.press(10.0, 9.0, *BOX)
    assert state.press(400.0, 400.0, *BOX) is False
    assert (state.held, state.hovered, state.activated) == (False, False, False)


def test_release_lets_go_but_leaves_hover_alone():
    """Releasing is not moving: the pointer is still where it was."""
    state = buttons.ButtonState()
    state.press(10.0, 9.0, *BOX)
    state.release()
    assert (state.held, state.activated) == (False, False)
    assert state.hovered is True


def test_hover_is_explicit_and_reversible():
    """Hovering needs telling, because there is no per-frame mouse feed."""
    state = buttons.ButtonState()
    assert state.hovered is False
    assert state.hover(10.0, 9.0, *BOX) is True
    assert state.hover(500.0, 9.0, *BOX) is False


def test_background_follows_the_reference_formula():
    """(held && hovered) -> active, hovered -> hovered, otherwise base."""
    state = buttons.ButtonState()
    assert state.background("base", "hov", "act") == "base"
    state.hover(10.0, 9.0, *BOX)
    assert state.background("base", "hov", "act") == "hov"
    state.press(10.0, 9.0, *BOX)
    assert state.background("base", "hov", "act") == "act"
    # Dragged off without releasing: held, not hovered -> back to the base
    # colour, which is the reference's way of saying "nothing happens here".
    state.hover(500.0, 9.0, *BOX)
    state.held = True
    assert state.background("base", "hov", "act") == "base"


# ------------------------------------------------------------- SmallButton
def test_small_button_frame_is_one_line_tall_and_centred():
    """No vertical padding: the frame is the text's height, not the row's."""
    painter = RecordingPainter()
    button = buttons.SmallButton("go")
    button.draw(painter, 0.0, 0.0, 200.0, 18.0)
    _x, frame_y, _w, frame_h, _edge, _fill = painter.strokes[0]
    assert frame_h == painter.line_height()
    assert frame_y == pytest.approx((18.0 - 12.0) * 0.5)


def test_small_button_size_is_caption_plus_padding():
    """The natural size a host should reserve."""
    painter = RecordingPainter()
    width, height = buttons.SmallButton("go").size(painter)
    assert width == pytest.approx(painter.text_width("go") + 8.0)
    assert height == painter.line_height()


def test_small_button_fires_only_when_hit():
    """A press elsewhere is not this button's press."""
    button = buttons.SmallButton("go")
    assert button.press(10.0, 9.0, *BOX) is True
    assert button.press(-5.0, 9.0, *BOX) is False
    assert button.state.held is False


# ---------------------------------------------------------- InvisibleButton
def test_invisible_button_paints_nothing_but_still_reports_a_hit():
    """Its whole contract: no marks, and it still answers."""
    painter = RecordingPainter()
    button = buttons.InvisibleButton("drag-area")
    button.draw(painter, *BOX)
    assert painter.fills == []
    assert painter.strokes == []
    assert painter.strings == []
    assert painter.clips == []
    assert button.press(10.0, 9.0, *BOX) is True
    assert button.state.held is True


def test_invisible_button_misses_like_any_other():
    """It hit-tests its box, not the whole surface."""
    button = buttons.InvisibleButton()
    assert button.press(10.0, 9.0, 100.0, 100.0, 20.0, 20.0) is False


# --------------------------------------------------------------- ArrowButton
def _arrow_fills(direction):
    """Rectangles the arrow glyph emitted, frame excluded."""
    painter = RecordingPainter()
    buttons.ArrowButton(direction).draw(painter, 0.0, 0.0, 20.0, 20.0)
    return painter.fills


@pytest.mark.parametrize("direction", [buttons.DIR_LEFT, buttons.DIR_RIGHT,
                                       buttons.DIR_UP, buttons.DIR_DOWN])
def test_arrow_button_draws_a_frame_and_a_glyph(direction):
    """One stroked frame plus a stack of glyph rectangles."""
    painter = RecordingPainter()
    buttons.ArrowButton(direction).draw(painter, 0.0, 0.0, 20.0, 20.0)
    assert len(painter.strokes) == 1
    assert len(painter.fills) >= 3


def test_up_and_down_arrows_taper_opposite_ways():
    """Up widens downwards to its base; down widens upwards to its."""
    up = _arrow_fills(buttons.DIR_UP)
    down = _arrow_fills(buttons.DIR_DOWN)
    widest_up = max(up, key=lambda r: r[2])
    widest_down = max(down, key=lambda r: r[2])
    assert widest_up[1] > min(r[1] for r in up)      # base at the bottom
    assert widest_down[1] == min(r[1] for r in down)  # base at the top
    assert widest_up[1] != widest_down[1]


def test_left_and_right_arrows_taper_opposite_ways():
    """Left grows in height towards its base on the right, and vice versa."""
    left = _arrow_fills(buttons.DIR_LEFT)
    right = _arrow_fills(buttons.DIR_RIGHT)
    tallest_left = max(left, key=lambda r: r[3])
    tallest_right = max(right, key=lambda r: r[3])
    assert tallest_left[0] > min(r[0] for r in left)
    assert tallest_right[0] == min(r[0] for r in right)


def test_horizontal_and_vertical_arrows_vary_different_dimensions():
    """Up/down bands differ in width; left/right bands differ in height."""
    up = _arrow_fills(buttons.DIR_UP)
    right = _arrow_fills(buttons.DIR_RIGHT)
    assert len({round(r[2], 3) for r in up}) > 1
    assert len({round(r[3], 3) for r in up}) == 1
    assert len({round(r[3], 3) for r in right}) > 1
    assert len({round(r[2], 3) for r in right}) == 1


def test_no_direction_draws_no_glyph():
    """The reference refuses to render ImGuiDir_None; so does this."""
    painter = RecordingPainter()
    buttons.ArrowButton(-1).draw(painter, 0.0, 0.0, 20.0, 20.0)
    assert painter.fills == []
    assert len(painter.strokes) == 1


# -------------------------------------------------------------- CheckboxFlags
def test_checkbox_flags_reports_the_three_states():
    """All, none, and the mixed state in between."""
    mask = 0b0110
    assert buttons.CheckboxFlags("f", 0b0110, mask).all_on is True
    assert buttons.CheckboxFlags("f", 0b0110, mask).mixed is False
    assert buttons.CheckboxFlags("f", 0b0010, mask).mixed is True
    assert buttons.CheckboxFlags("f", 0b0010, mask).all_on is False
    assert buttons.CheckboxFlags("f", 0b0001, mask).any_on is False


def test_checkbox_flags_cycles_the_bitmask_the_reference_way():
    """Mixed sets every owned bit; the next press clears them; other bits survive."""
    box = buttons.CheckboxFlags("f", flags=0b1010, flags_value=0b0110)
    assert box.mixed is True

    # Mixed -> all owned bits on. The unowned bit 3 is untouched.
    assert box.press(5.0, 9.0, *BOX) == 0b1110
    assert box.all_on is True
    assert box.mixed is False

    # All -> none. Still only the owned bits move.
    assert box.press(5.0, 9.0, *BOX) == 0b1000
    assert box.any_on is False

    # None -> all again: the cycle is two states wide, never back to mixed.
    assert box.press(5.0, 9.0, *BOX) == 0b1110


def test_checkbox_flags_press_outside_changes_nothing():
    """A missed press returns the mask unchanged rather than toggling."""
    box = buttons.CheckboxFlags("f", flags=0b0001, flags_value=0b0001)
    assert box.press(500.0, 500.0, *BOX) == 0b0001
    assert box.all_on is True
    assert box.state.held is False


def test_checkbox_flags_release_clears_the_hold_without_changing_the_mask():
    """Letting go is not another press."""
    box = buttons.CheckboxFlags("f", flags=0b0000, flags_value=0b0001)
    box.press(5.0, 9.0, *BOX)
    box.release()
    assert box.state.held is False
    assert box.flags == 0b0001


def test_checkbox_flags_draws_a_block_for_mixed_and_a_tick_for_all():
    """The mixed state is one filled square; the checked state is a staircase tick."""
    mixed_painter = RecordingPainter()
    buttons.CheckboxFlags("f", 0b0010, 0b0110).draw(mixed_painter, 0.0, 0.0, 200.0, 18.0)
    all_painter = RecordingPainter()
    buttons.CheckboxFlags("f", 0b0110, 0b0110).draw(all_painter, 0.0, 0.0, 200.0, 18.0)
    off_painter = RecordingPainter()
    buttons.CheckboxFlags("f", 0b0000, 0b0110).draw(off_painter, 0.0, 0.0, 200.0, 18.0)

    assert len(mixed_painter.fills) == 1
    assert len(all_painter.fills) > 1
    assert off_painter.fills == []


# ----------------------------------------------------------------- RadioButton
def test_radio_button_press_makes_it_active_and_never_toggles_off():
    """Radio buttons do not un-choose themselves."""
    radio = buttons.RadioButton("one")
    assert radio.active is False
    assert radio.press(5.0, 9.0, *BOX) is True
    assert radio.active is True
    assert radio.press(5.0, 9.0, *BOX) is True
    assert radio.active is True


def test_radio_button_press_outside_leaves_it_alone():
    """A press elsewhere neither selects it nor holds it."""
    radio = buttons.RadioButton("one")
    assert radio.press(500.0, 500.0, *BOX) is False
    assert radio.active is False
    assert radio.state.held is False


def test_radio_button_draws_more_bands_when_active():
    """Active adds the inner dot on top of the well."""
    off = RecordingPainter()
    buttons.RadioButton("one", False).draw(off, 0.0, 0.0, 200.0, 18.0)
    on = RecordingPainter()
    buttons.RadioButton("one", True).draw(on, 0.0, 0.0, 200.0, 18.0)
    assert len(on.fills) > len(off.fills)


def test_radio_disc_is_widest_across_its_middle():
    """The scan-converted circle is a circle: bands narrow towards the poles."""
    painter = RecordingPainter()
    buttons.RadioButton("", False).draw(painter, 0.0, 0.0, 40.0, 40.0)
    bands = painter.fills
    centre_y = 20.0
    widest = max(bands, key=lambda r: r[2])
    assert abs(widest[1] + widest[3] * 0.5 - centre_y) < abs(bands[0][1] - centre_y)
