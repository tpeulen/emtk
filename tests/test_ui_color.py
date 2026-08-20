"""Painter-level tests for the colour family.

No GUI toolkit is involved -- the controls are drawn through the six painter
operations and nothing else, and a control that quietly grows a Qt dependency
fails here first.

The interesting tests are the ones about *state that RGB cannot carry*: hue is
undefined for a grey and saturation is undefined for black, so a picker that
round-trips through bytes on every event snaps to red the moment a drag reaches
an edge. That is the classic colour-picker bug, and it has its own test below.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import color


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
    lambda: color.ColorButton((200, 40, 40, 128), "swatch"),
    lambda: color.ColorEditRGB("c", (200, 40, 40)),
    lambda: color.ColorEditRGBA("c", (200, 40, 40, 128)),
    lambda: color.ColorPicker3((0, 128, 255, 255), "pick"),
    lambda: color.ColorPicker4((0, 128, 255, 128), True, "pick"),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 120.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# Conversions
# --------------------------------------------------------------------------
SPREAD = [
    (1.0, 0.0, 0.0),      # full saturation, each primary
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (0.0, 1.0, 1.0),      # and each secondary
    (1.0, 0.0, 1.0),
    (1.0, 1.0, 0.0),
    (0.0, 0.0, 0.0),      # pure black: saturation is undefined
    (1.0, 1.0, 1.0),      # pure white: hue is undefined
    (0.5, 0.5, 0.5),      # pure grey: hue is undefined
    (0.2, 0.6, 0.4),
    (0.78, 0.16, 0.44),
    (0.05, 0.05, 0.9),
]


@pytest.mark.parametrize("rgb", SPREAD, ids=lambda c: "-".join(f"{v:.2f}" for v in c))
def test_hsv_round_trips_for_every_colour_including_the_grey_edges(rgb):
    """RGB to HSV and back is the identity, greys and black included."""
    h, s, v = color.rgb_to_hsv(*rgb)
    assert 0.0 <= h <= 1.0 and 0.0 <= s <= 1.0 and 0.0 <= v <= 1.0
    back = color.hsv_to_rgb(h, s, v)
    assert back == pytest.approx(rgb, abs=1e-6)


def test_the_undefined_components_come_out_zero_like_the_reference():
    """Grey has no hue and black has no saturation; both read as zero."""
    assert color.rgb_to_hsv(0.5, 0.5, 0.5) == pytest.approx((0.0, 0.0, 0.5))
    assert color.rgb_to_hsv(0.0, 0.0, 0.0) == pytest.approx((0.0, 0.0, 0.0))
    # A zero saturation is a grey whatever the hue claims -- the reference
    # returns early rather than trusting its sector arithmetic to agree.
    assert color.hsv_to_rgb(0.77, 0.0, 0.3) == pytest.approx((0.3, 0.3, 0.3))
    # Hue wraps: 1.0 is red again.
    assert color.hsv_to_rgb(1.0, 1.0, 1.0) == pytest.approx((1.0, 0.0, 0.0))


def test_byte_packing_saturates_and_rounds_the_way_the_reference_does():
    """``IM_F32_TO_INT8_SAT``: clamp, scale, add a half, truncate."""
    assert color.floats_to_rgba((1.0, 0.0, 0.5)) == (255, 0, 128, 255)
    assert color.floats_to_rgba((2.0, -1.0, 0.0, 0.5)) == (255, 0, 0, 128)
    assert color.rgba_to_floats((255, 0, 128)) == pytest.approx((1.0, 0.0, 128 / 255, 1.0))


# --------------------------------------------------------------------------
# The state that RGB cannot carry
# --------------------------------------------------------------------------
def test_setting_a_grey_keeps_the_hue_the_state_already_had():
    """A grey has no hue of its own, so the one already held survives."""
    state = color.ColorState((0, 0, 255, 255))
    assert state.hsv[0] == pytest.approx(2.0 / 3.0)
    state.set_rgba((128, 128, 128, 255))
    assert state.hsv[0] == pytest.approx(2.0 / 3.0)
    assert state.hsv[1] == 0.0


def test_setting_black_keeps_the_saturation_the_state_already_had():
    """Black has no saturation of its own, so the one already held survives."""
    state = color.ColorState((0, 128, 0, 255))
    saturation = state.hsv[1]
    assert saturation == pytest.approx(1.0)
    state.set_rgba((0, 0, 0, 255))
    assert state.hsv == pytest.approx((1.0 / 3.0, 1.0, 0.0))


# --------------------------------------------------------------------------
# ColorPicker
# --------------------------------------------------------------------------
BOX = (0.0, 0.0, 200.0, 120.0)


def test_the_sv_square_corners_give_the_saturation_and_value_they_look_like():
    """Top-left is white, top-right the pure hue, bottom anything is black."""
    picker = color.ColorPicker4((255, 0, 0, 255))
    assert picker.press(0.0, 0.0, *BOX) == "sv"
    assert picker.hsv[1] == pytest.approx(0.0)
    assert picker.hsv[2] == pytest.approx(1.0)
    assert picker.color == (255, 255, 255, 255)

    picker.press(119.0, 0.0, *BOX)
    assert picker.hsv[1] == pytest.approx(1.0)
    assert picker.hsv[2] == pytest.approx(1.0)
    assert picker.color == (255, 0, 0, 255)

    picker.press(119.0, 119.0, *BOX)
    assert picker.hsv[1] == pytest.approx(1.0)
    assert picker.hsv[2] == pytest.approx(0.0)
    assert picker.color == (0, 0, 0, 255)


def test_dragging_the_hue_bar_at_zero_value_keeps_saturation_and_hue_state():
    """The classic bug: hue must not snap to red when the colour is black.

    Drag the square to the black bottom -- value zero, so the bytes are
    ``(0, 0, 0)`` and carry neither hue nor saturation -- then drag the hue
    bar. A picker that recovers H and S from RGB per event loses both here;
    the colour then jumps to red as soon as value comes back up.
    """
    picker = color.ColorPicker4((0, 255, 0, 255))
    picker.press(119.0, 119.0, *BOX)       # bottom-right of the square
    picker.release()
    assert picker.color == (0, 0, 0, 255)
    assert picker.hsv[1] == pytest.approx(1.0)

    # Now the hue bar, two thirds down: blue.
    assert picker.press(130.0, 119.0 * (2.0 / 3.0), *BOX) == "hue"
    assert picker.hsv[0] == pytest.approx(2.0 / 3.0)
    assert picker.hsv[1] == pytest.approx(1.0), "saturation was lost by the hue drag"
    assert picker.hsv[2] == pytest.approx(0.0), "the hue drag moved value"
    picker.drag(130.0, 119.0, *BOX)
    assert picker.hsv[0] == pytest.approx(1.0)
    assert picker.hsv[1] == pytest.approx(1.0)
    picker.release()

    # Bringing value back up returns the hue that was chosen, not red.
    picker.press(119.0, 0.0, *BOX)
    picker.drag(119.0, 119.0 * (2.0 / 3.0), *BOX)
    picker.press(119.0, 0.0, *BOX)
    assert picker.color == (255, 0, 0, 255)  # hue 1.0 is red again, by wrap


def test_dragging_the_hue_bar_at_zero_saturation_keeps_the_value():
    """The other half of the same bug: a white colour still has a hue bar."""
    picker = color.ColorPicker4((255, 0, 0, 255))
    picker.press(0.0, 0.0, *BOX)           # top-left: white, saturation zero
    picker.release()
    assert picker.color == (255, 255, 255, 255)
    picker.press(130.0, 119.0 / 3.0, *BOX)
    assert picker.hsv[0] == pytest.approx(1.0 / 3.0)
    assert picker.hsv[1] == pytest.approx(0.0)
    assert picker.color == (255, 255, 255, 255), "the hue drag recoloured a white"
    # And the hue is there when saturation comes back.
    picker.release()
    picker.press(119.0, 0.0, *BOX)
    assert picker.color == (0, 255, 0, 255)


def test_the_alpha_bar_moves_alpha_and_nothing_else():
    """Alpha is a fourth channel, not a fourth way to change the colour."""
    picker = color.ColorPicker4((0, 128, 255, 255))
    before_rgb, before_hsv = picker.state.rgb, picker.state.hsv
    assert picker.press(150.0, 59.5, *BOX) == "alpha"
    assert picker.state.alpha == 128
    assert picker.state.rgb == before_rgb
    assert picker.state.hsv == pytest.approx(before_hsv)
    # Top of the bar is opaque, bottom is transparent.
    picker.drag(150.0, 0.0, *BOX)
    assert picker.state.alpha == 255
    picker.drag(150.0, 200.0, *BOX)
    assert picker.state.alpha == 0
    assert picker.state.rgb == before_rgb


def test_a_drag_that_leaves_the_square_clamps_instead_of_letting_go():
    """Overshooting a drag must not drop the grab; the reference holds too."""
    picker = color.ColorPicker4((255, 0, 0, 255))
    assert picker.press(60.0, 60.0, *BOX) == "sv"
    picker.drag(-500.0, -500.0, *BOX)
    assert picker.zone == "sv"
    assert picker.hsv[1] == pytest.approx(0.0)
    assert picker.hsv[2] == pytest.approx(1.0)
    picker.release()
    assert picker.zone is None
    assert picker.drag(60.0, 60.0, *BOX) is False


def test_the_three_component_picker_has_no_alpha_bar_to_press():
    """``ColorPicker3`` is the reference's ``NoAlpha``: the bar is gone."""
    picker = color.ColorPicker3((255, 0, 0, 200))
    # Where picker4 would put its alpha bar there is now nothing.
    assert picker.press(150.0, 40.0, *BOX) is None
    assert picker.state.alpha == 200
    assert picker.press(130.0, 40.0, *BOX) == "hue"


def test_the_picker_draws_the_square_as_a_stack_of_gradients():
    """The square is strips, because the painter interpolates one way only."""
    painter = RecordingPainter()
    color.ColorPicker4((255, 0, 0, 255)).draw(painter, 0.0, 0.0, 200.0, 120.0)
    square_rows = [f for f in painter.fills if f[0] == 0.0 and f[2] == 120.0]
    assert len(square_rows) >= 8
    # Top row starts near white, bottom row near black: value falls downward.
    assert square_rows[0][4][0] > square_rows[-1][4][0]


# --------------------------------------------------------------------------
# ColorButton
# --------------------------------------------------------------------------
def test_a_translucent_swatch_gets_a_checkerboard_and_an_opaque_one_does_not():
    """Transparency is shown, not implied."""
    clear, solid = RecordingPainter(), RecordingPainter()
    color.ColorButton((200, 40, 40, 100)).draw(clear, 0.0, 0.0, 40.0, 18.0)
    color.ColorButton((200, 40, 40, 255)).draw(solid, 0.0, 0.0, 40.0, 18.0)
    assert len(clear.fills) > len(solid.fills)
    assert len(solid.fills) == 1
    assert solid.fills[0][4] == (200, 40, 40, 255)


def test_a_swatch_reports_its_clicks():
    """The reference's "returns true when clicked"."""
    button = color.ColorButton((10, 20, 30, 255))
    assert button.press(5.0, 5.0, 0.0, 0.0, 18.0, 18.0) is True
    assert button.press(50.0, 5.0, 0.0, 0.0, 18.0, 18.0) is False
    button.release()


# --------------------------------------------------------------------------
# ColorEdit
# --------------------------------------------------------------------------
EDIT_BOX = (0.0, 0.0, 200.0, 18.0)


def test_the_editor_cycles_its_display_mode_from_the_tag():
    """No right-click here, so the reference's options popup is a visible tag."""
    editor = color.ColorEditRGBA("c", (16, 32, 48, 255))
    painter = RecordingPainter()
    editor.draw(painter, *EDIT_BOX)          # measures the tag
    assert editor.press(195.0, 9.0, *EDIT_BOX) == "mode"
    assert editor.mode == "HSV"
    assert editor.press(195.0, 9.0, *EDIT_BOX) == "mode"
    assert editor.mode == "HEX"
    assert editor.press(195.0, 9.0, *EDIT_BOX) == "mode"
    assert editor.mode == "RGB"


def test_pressing_the_swatch_asks_the_host_for_a_picker():
    """That is what the reference's small preview does when clicked."""
    editor = color.ColorEditRGBA("c", (16, 32, 48, 255))
    painter = RecordingPainter()
    editor.draw(painter, *EDIT_BOX)
    assert "c" in painter.strings, "the caption was never painted"
    assert editor.press(20.0, 9.0, *EDIT_BOX) == "swatch"
    assert editor.press(2.0, 9.0, *EDIT_BOX) is None, "the caption is not a control"
    assert editor.press(500.0, 9.0, *EDIT_BOX) is None


def test_dragging_a_field_moves_one_unit_per_pixel():
    """The reference's ``DragInt`` at its default speed."""
    editor = color.ColorEditRGBA("c", (100, 32, 48, 255))
    editor.draw(RecordingPainter(), *EDIT_BOX)
    assert editor.press(40.0, 9.0, *EDIT_BOX) == "field"
    assert editor.drag(55.0, 9.0, *EDIT_BOX) is True
    assert editor.color == (115, 32, 48, 255)
    editor.drag(-500.0, 9.0, *EDIT_BOX)
    assert editor.color == (0, 32, 48, 255)
    editor.release()
    assert editor.drag(45.0, 9.0, *EDIT_BOX) is False


def test_the_hsv_fields_keep_a_hue_the_bytes_cannot_hold():
    """Desaturating to white in the HSV fields must not forget the hue."""
    editor = color.ColorEditRGBA("c", (255, 0, 0, 255), mode="HSV")
    assert editor.values() == (0, 255, 255, 255)
    editor.set_value(0, 128)                  # hue two thirds of the way round
    assert editor.set_value(1, 0) == (255, 255, 255, 255)
    assert editor.values()[0] == 128, "the hue was lost when saturation hit zero"


def test_hex_is_written_and_parsed_the_way_the_reference_writes_it():
    """``#RRGGBBAA``, upper case, alpha optional on the way in."""
    editor = color.ColorEditRGBA("c", (16, 32, 48, 255))
    assert editor.state.hex() == "#102030FF"
    assert editor.state.hex(alpha=False) == "#102030"
    assert editor.set_hex("  #a0B0C0 ") is True
    assert editor.color == (160, 176, 192, 255)
    assert editor.set_hex("#zzz") is False
    assert editor.set_hex("#12345") is False
    assert editor.color == (160, 176, 192, 255)


def test_the_three_component_editor_never_shows_or_edits_alpha():
    """``ColorEditRGB`` is the reference's ``ColorEdit3``."""
    editor = color.ColorEditRGB("c", (10, 20, 30, 128))
    assert editor.components == 3
    assert editor.values() == (10, 20, 30)
    assert editor.set_value(3, 0) == (10, 20, 30, 128)
    assert editor.state.alpha == 128
