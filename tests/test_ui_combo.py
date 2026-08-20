"""Painter-level tests for the combo box.

Behaviour, not pixels: what a press does to the selection, where the popup goes
when there is no room below it, how many rows a height flag lets it show, and
which rows the closed frame draws at all. None of it needs a GUI toolkit --
that is the point of the painter seam.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import combo


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


#: The frame every test draws into unless it wants a different one.
BOX = (10.0, 10.0, 120.0, 18.0)


def _rows(painter):
    """Return the option rows the popup drew, minus the frame's preview of one.

    The closed frame draws the *current* option before the popup draws any of
    them, so a plain filter over the recorded strings counts the selection
    twice. The preview is always the first of them.

    Parameters
    ----------
    painter : RecordingPainter
        The painter drawn into.

    Returns
    -------
    list of str
        The rows, top to bottom.
    """
    return [one for one in painter.strings if one.startswith("opt")][1:]


def _make(options=("alpha", "beta", "gamma"), **kwargs):
    """Build a combo with a viewport big enough that nothing flips.

    Parameters
    ----------
    options : sequence of str
        The choices.
    **kwargs
        Passed to :class:`~cmtk.widgets.combo.ComboBox`.

    Returns
    -------
    ComboBox
        The control.
    """
    box = combo.ComboBox(kwargs.pop("label", ""), options, **kwargs)
    box.set_viewport(800.0, 600.0)
    return box


def _draw(box, painter=None, at=BOX):
    """Draw a combo and return the painter it drew into.

    Parameters
    ----------
    box : ComboBox
        The control.
    painter : RecordingPainter, optional
        Reused when given, so a test can accumulate two draws.
    at : tuple of float
        The box to draw into.

    Returns
    -------
    RecordingPainter
        The painter.
    """
    painter = painter or RecordingPainter()
    box.draw(painter, *at)
    return painter


# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("opened", [False, True], ids=["closed", "open"])
def test_it_paints_and_balances_its_clips(opened):
    """It draws something in both states and leaves the clip stack as it found it."""
    box = _make()
    if opened:
        box.open_popup()
    painter = _draw(box)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


def test_opening_shows_every_option_and_picking_one_sets_the_value():
    """The list is the whole point: all options at once, one press to pick."""
    box = _make()
    assert box.value == "alpha"

    result = box.press(15.0, 15.0, *BOX)
    assert box.open and result.consumed and result.index is None
    painter = _draw(box)
    assert {"alpha", "beta", "gamma"} <= set(painter.strings)

    # Second row of the popup, which starts one padding below the frame.
    pop_x, pop_y, pop_w, _pop_h = box.popup_rect
    row_h = 12.0 * combo.ROW_SCALE
    hit_y = pop_y + combo.PAD + row_h * 1.5
    result = box.press(pop_x + pop_w * 0.5, hit_y, *BOX)

    assert result.index == 1
    assert result.changed and result.closed and result.consumed
    assert box.value == "beta"
    assert not box.open


def test_repicking_the_current_option_reports_no_change():
    """The reference only reports a change when the index actually moved."""
    box = _make(index=1)
    box.open_popup()
    _draw(box)
    pop_x, pop_y, pop_w, _pop_h = box.popup_rect
    row_h = 12.0 * combo.ROW_SCALE
    result = box.press(pop_x + pop_w * 0.5, pop_y + combo.PAD + row_h * 1.5, *BOX)
    assert result.index == 1
    assert not result.changed
    assert box.value == "beta"


def test_a_press_outside_closes_without_changing_the_selection():
    """Dismissing is not picking -- and the dismissing press reaches the scene."""
    box = _make(index=2)
    box.open_popup()
    _draw(box)
    pop_x, pop_y, pop_w, pop_h = box.popup_rect

    result = box.press(pop_x + pop_w + 200.0, pop_y + pop_h + 200.0, *BOX)

    assert not box.open
    assert result.index is None and result.closed
    assert not result.changed
    # A press outside a plain popup still reaches what is behind it.
    assert not result.consumed
    assert box.value == "gamma"


def test_a_press_on_the_popups_padding_is_consumed_but_picks_nothing():
    """The panel owns its own padding: it must not rotate the scene behind."""
    box = _make()
    box.open_popup()
    _draw(box)
    pop_x, pop_y, pop_w, _pop_h = box.popup_rect

    result = box.press(pop_x + pop_w * 0.5, pop_y + combo.PAD * 0.25, *BOX)

    assert result.index is None and result.consumed
    assert not result.closed and box.open


def test_the_popup_flips_above_the_frame_near_the_bottom_of_the_viewport():
    """No room below is the classic popup bug; the placement rule answers it."""
    box = _make()
    box.set_viewport(400.0, 200.0)
    low = (10.0, 172.0, 120.0, 18.0)

    box.open_popup()
    _draw(box, at=low)
    pop_x, pop_y, pop_w, pop_h = box.popup_rect

    assert box.last_dir == "up"
    assert pop_y + pop_h <= low[1] + 0.001
    assert pop_y >= 0.0

    # Higher up the same viewport it goes below, and the earlier flip is not
    # remembered: the reference overrides the direction on every opening.
    high = (10.0, 20.0, 120.0, 18.0)
    box.open_popup()
    _draw(box, at=high)
    assert box.last_dir == "down"
    assert box.popup_rect[1] >= high[1] + high[3] - 0.001


def test_a_height_flag_caps_the_visible_rows_and_the_rest_is_scrolled_to():
    """``HeightSmall`` is four items; item five is reachable, not lost."""
    options = [f"opt{i:02d}" for i in range(12)]
    box = _make(options, flags=combo.COMBO_HEIGHT_SMALL)
    assert box.max_items == 4
    box.open_popup()

    assert _rows(_draw(box)) == ["opt00", "opt01", "opt02", "opt03"]

    box.scroll(8)
    assert _rows(_draw(box)) == ["opt08", "opt09", "opt10", "opt11"]

    # And it is pickable once scrolled to.
    pop_x, pop_y, pop_w, _pop_h = box.popup_rect
    row_h = 12.0 * combo.ROW_SCALE
    result = box.press(pop_x + pop_w * 0.5, pop_y + combo.PAD + row_h * 3.5, *BOX)
    assert result.index == 11 and box.value == "opt11"


def test_the_default_height_is_eight_items_not_all_of_them():
    """A combo with no height flag is given ``HeightRegular``."""
    options = [f"opt{i:02d}" for i in range(30)]
    box = _make(options)
    assert box.max_items == 8
    box.open_popup()
    assert len(_rows(_draw(box))) == 8
    assert box.max_items == combo.ComboBox("", [], flags=combo.COMBO_HEIGHT_REGULAR).max_items


def test_height_largest_is_capped_only_by_the_viewport():
    """The largest height is a viewport limit rather than a count of its own."""
    options = [f"opt{i:02d}" for i in range(30)]
    box = _make(options, flags=combo.COMBO_HEIGHT_LARGEST)
    assert box.max_items is None
    row_h = 12.0 * combo.ROW_SCALE
    box.set_viewport(400.0, row_h * 6 + 2 * combo.PAD)
    box.open_popup()
    assert len(_rows(_draw(box, at=(10.0, 0.0, 120.0, 18.0)))) == 6


def test_a_long_list_opens_showing_the_selected_item():
    """``SetItemDefaultFocus``: opening on the 28th of 30 does not show the 1st."""
    options = [f"opt{i:02d}" for i in range(30)]
    box = _make(options, index=27)

    box.press(15.0, 15.0, *BOX)
    shown = _rows(_draw(box))
    assert "opt27" in shown
    assert "opt00" not in shown
    assert shown[-1] == "opt27"


def test_the_popup_is_never_narrower_than_the_frame_and_widens_for_its_options():
    """The reference's ``constraint_min.x = w``, and its content-fit above it."""
    narrow = _make(["a", "b"])
    narrow.open_popup()
    _draw(narrow)
    assert narrow.popup_rect[2] == pytest.approx(BOX[2])

    wide = _make(["a" * 40, "b"])
    wide.open_popup()
    _draw(wide)
    assert wide.popup_rect[2] > BOX[2]


def test_popup_align_left_anchors_the_popups_right_edge_to_the_frames():
    """The reference's ``ImGuiDir_Left``: below, toward left."""
    options = ["a" * 30, "b"]
    at = (200.0, 20.0, 40.0, 18.0)

    default = _make(options)
    default.set_viewport(600.0, 300.0)
    default.open_popup()
    _draw(default, at=at)
    assert default.popup_rect[0] == pytest.approx(at[0])

    aligned = _make(options, flags=combo.COMBO_POPUP_ALIGN_LEFT)
    aligned.set_viewport(600.0, 300.0)
    aligned.open_popup()
    _draw(aligned, at=at)
    pop_x, _pop_y, pop_w, _pop_h = aligned.popup_rect
    assert pop_x + pop_w == pytest.approx(at[0] + at[2])
    assert pop_x < at[0]


def test_no_preview_draws_only_the_square_arrow_button():
    """The frame collapses to the button, and the current value is not drawn."""
    box = _make(flags=combo.COMBO_NO_PREVIEW)
    painter = _draw(box)
    assert box.frame_rect == (BOX[0], BOX[1], BOX[3], BOX[3])
    assert "▼" in painter.strings
    assert "alpha" not in painter.strings


def test_no_arrow_button_draws_the_preview_and_no_mark():
    """The other half of the pair: a framed value with nothing hanging off it."""
    box = _make(flags=combo.COMBO_NO_ARROW_BUTTON)
    painter = _draw(box)
    assert box.frame_rect == (BOX[0], BOX[1], BOX[2], BOX[3])
    assert "alpha" in painter.strings
    assert "▼" not in painter.strings


def test_width_fit_preview_sizes_the_frame_from_the_current_value():
    """The frame follows the value rather than the box it was given."""
    box = _make(["x", "a much longer option"], flags=combo.COMBO_WIDTH_FIT_PREVIEW)
    painter = RecordingPainter()

    box.draw(painter, *BOX)
    short = box.frame_rect[2]
    box.select(1)
    box.draw(painter, *BOX)
    long = box.frame_rect[2]

    assert short == pytest.approx(BOX[3] + painter.text_width("x") + 2 * combo.FRAME_PAD)
    assert long > short


def test_the_label_sits_outside_the_frame():
    """A press on the caption is not a press on the combo, as in the reference."""
    box = _make(label="Mode")
    painter = _draw(box)
    assert "Mode" in painter.strings
    frame_w = box.frame_rect[2]
    assert frame_w < BOX[2]
    # The caption's own room is what the frame gave up.
    assert frame_w == pytest.approx(
        BOX[2] - painter.text_width("Mode") - combo.INNER_SPACING
    )
    assert box.press(BOX[0] + BOX[2] - 2.0, 15.0, *BOX) == combo._IGNORED


def test_pressing_the_frame_while_open_puts_the_list_away():
    """The arrow is a toggle from the user's side, and picks nothing."""
    box = _make(index=1)
    box.press(15.0, 15.0, *BOX)
    assert box.open
    result = box.press(15.0, 15.0, *BOX)
    assert not box.open
    assert result.closed and result.consumed and result.index is None
    assert box.value == "beta"


def test_the_scrollbar_takes_its_own_presses_and_drags():
    """A press on the bar scrolls; it never picks the row behind it."""
    options = [f"opt{i:02d}" for i in range(30)]
    box = _make(options, flags=combo.COMBO_HEIGHT_SMALL)
    box.open_popup()
    _draw(box)
    pop_x, pop_y, pop_w, pop_h = box.popup_rect

    result = box.press(pop_x + pop_w - 1.0, pop_y + pop_h - combo.PAD - 1.0, *BOX)

    assert result.index is None and result.consumed and not result.closed
    assert box.bar.top > 0
    assert box.drag(pop_y + combo.PAD)
    assert box.bar.top == 0
    box.release()
    assert not box.bar.held


def test_an_empty_combo_draws_and_refuses_to_pick():
    """No options is a real state -- a filter that matched nothing, say."""
    box = _make([])
    assert box.value == ""
    box.open_popup()
    painter = _draw(box)
    assert painter.clips == []
    pop_x, pop_y, pop_w, pop_h = box.popup_rect
    result = box.press(pop_x + pop_w * 0.5, pop_y + pop_h * 0.5, *BOX)
    assert result.index is None
