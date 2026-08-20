"""Painter-level tests for the Input family.

No GUI toolkit, no window: the controls are drawn into a recorder and driven
with the key codes a host would send. What is checked is *behaviour* -- a hint
that is never a value, a two-line buffer that comes back to one line, a cursor
column that survives a trip past a short line -- rather than the rectangles,
which are the part that is allowed to change.
"""

from __future__ import annotations

import pytest

from cmtk import keys
from cmtk.widgets import inputs


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
    lambda: inputs.InputFloat("f", 1.5, step=0.1, step_fast=1.0),
    lambda: inputs.InputDouble("d", 1.5, step=0.1),
    lambda: inputs.InputScalarN("n", [1.0, 2.0, 3.0]),
    lambda: inputs.InputFloat3("pos", (1.0, 2.0, 3.0)),
    lambda: inputs.InputInt4("box", (1, 2, 3, 4)),
    lambda: inputs.InputTextWithHint("q", "search...", ""),
    lambda: inputs.InputTextMultiline("notes", "one\ntwo\nthree"),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Smoke test: each control draws something and leaves the clip stack empty."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 240.0, 60.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# Format parsing and the text -> number round trip
# --------------------------------------------------------------------------
def test_decorations_are_stripped_for_editing_but_shown_for_display():
    """``"%.1f tiles"`` shows the units and edits the bare number."""
    field = inputs.InputFloat("size", 4.5, fmt="%.1f tiles")
    assert field.display_text() == "4.5 tiles"
    assert field.edit_text() == "4.5"
    assert inputs.trim_decorations("hello %.3f") == "%.3f"
    assert inputs.trim_decorations("%08I64d") == "%08I64d"
    assert inputs.trim_decorations("no number here") == ""


def test_format_precision_reads_the_decimals_back():
    """The reference infers a minimum step from the format; so can we."""
    assert inputs.format_precision("%.4f") == 4
    assert inputs.format_precision("%f") == 3
    assert inputs.format_precision("%d", default=0) == 0
    # Scientific and shortest-form mean "as many as it takes".
    assert inputs.format_precision("%e") == -1
    assert inputs.format_precision("%g") == -1


def test_unparseable_text_leaves_the_value_intact():
    """A typo costs the edit, not the value -- and never silently zeroes it."""
    field = inputs.InputFloat("f", 3.25)
    field.begin_edit()
    field.field.set_text("twelve")
    assert field.commit() == 3.25
    assert field.editing is False
    # The same for an empty box: no value is not the value zero.
    field.begin_edit()
    field.field.set_text("")
    assert field.commit() == 3.25
    # And parsing stops at the first character that does not belong, as sscanf does.
    field.begin_edit()
    field.field.set_text("12abc")
    assert field.commit() == 12.0


def test_apply_from_text_handles_the_type_the_format_names():
    """``%d`` reads a whole number, ``%X`` a hexadecimal one, ``%f`` a float."""
    assert inputs.apply_from_text("42", 0, "%d") == 42
    assert inputs.apply_from_text("42.9", 0, "%d") == 42
    assert inputs.apply_from_text("ff", 0, "%X") == 255
    assert inputs.apply_from_text("0x1f", 0, "%08X") == 31
    assert inputs.apply_from_text("-1.5e2", 0.0, "%.3f") == -150.0
    # Empty means "leave it" unless the caller says what empty means.
    assert inputs.apply_from_text("", 7.0, "%.3f") == 7.0
    assert inputs.apply_from_text("", 7.0, "%.3f", when_empty=0.0) == 0.0


def test_typed_value_is_clamped_to_the_bounds():
    """Bounds are applied on commit, and reversed bounds are swapped."""
    field = inputs.InputFloat("f", 1.0, v_min=10.0, v_max=0.0)
    field.begin_edit()
    field.field.set_text("99")
    assert field.commit() == 10.0


# --------------------------------------------------------------------------
# Steppers
# --------------------------------------------------------------------------
def test_step_and_step_fast_move_by_the_right_amounts():
    """``+`` moves by ``step``; the fast modifier moves by ``step_fast``."""
    field = inputs.InputFloat("f", 1.0, step=0.25, step_fast=2.0)
    painter = RecordingPainter()
    field.draw(painter, 0.0, 0.0, 200.0, 20.0)
    # The two buttons are the rightmost two squares of the box.
    plus_x, minus_x = 195.0, 175.0
    assert field.press(plus_x, 10.0, 0.0, 0.0, 200.0, 20.0) == pytest.approx(1.25)
    assert field.press(minus_x, 10.0, 0.0, 0.0, 200.0, 20.0) == pytest.approx(1.0)
    assert field.press(plus_x, 10.0, 0.0, 0.0, 200.0, 20.0, fast=True) == pytest.approx(3.0)
    assert field.press(minus_x, 10.0, 0.0, 0.0, 200.0, 20.0, fast=True) == pytest.approx(1.0)


def test_a_field_without_a_step_draws_no_buttons():
    """The reference hides the steppers when ``step`` is zero, and so do we."""
    plain = inputs.InputFloat("f", 1.0)
    painter = RecordingPainter()
    plain.draw(painter, 0.0, 0.0, 200.0, 20.0)
    assert "+" not in painter.strings and "-" not in painter.strings
    # A press on the right-hand edge therefore starts an edit rather than stepping.
    plain.press(195.0, 10.0, 0.0, 0.0, 200.0, 20.0)
    assert plain.editing is True
    assert plain.value == 1.0


def test_a_press_elsewhere_commits_the_edit():
    """Losing focus applies the number: that is what deactivation means."""
    field = inputs.InputFloat("f", 1.0)
    field.press(50.0, 10.0, 0.0, 0.0, 200.0, 20.0)
    field.insert("7.5")
    assert field.value == 1.0  # not applied while typing
    assert field.press(400.0, 400.0, 0.0, 0.0, 200.0, 20.0) == pytest.approx(7.5)


def test_return_commits_and_escape_throws_the_edit_away():
    """Two ways out of an edit, with different meanings."""
    field = inputs.InputDouble("d", 2.0)
    field.begin_edit()
    field.insert("5")
    assert field.key(keys.KEY_RETURN) is True
    assert field.value == 5.0
    field.begin_edit()
    field.insert("9")
    assert field.key(keys.KEY_ESCAPE) is True
    assert field.value == 5.0
    # A key arriving at a field that is not editing belongs to somebody else.
    assert field.key(keys.KEY_RETURN) is False


def test_activating_a_field_hands_it_over_selected():
    """Typing into a box showing ``1.000`` must give ``7``, never ``1.0007``."""
    field = inputs.InputFloat("f", 1.0)
    field.begin_edit()
    assert field.field.text == "1.000"
    assert field.select_all is True
    field.insert("7")
    assert field.field.text == "7"
    assert field.commit() == 7.0
    # Backspace on the handed-over selection empties it rather than nibbling it.
    field.begin_edit()
    field.key(keys.KEY_BACKSPACE)
    assert field.field.text == ""
    # ...and the empty box commits to the value it had, not to zero.
    assert field.commit() == 7.0
    # A movement key collapses the caret to the end it points at.
    field.begin_edit()
    field.key(keys.KEY_LEFT)
    assert field.field.cursor == 0
    field.insert("2")
    assert field.field.text == "27.000"


def test_input_double_only_differs_in_its_default_format():
    """Python has one float type; the reference's two differ here by decimals."""
    assert inputs.InputFloat("f", 1.0).display_text() == "1.000"
    assert inputs.InputDouble("d", 1.0).display_text() == "1.000000"


# --------------------------------------------------------------------------
# The N-component rows
# --------------------------------------------------------------------------
def test_scalar_n_edits_one_component_and_leaves_the_others():
    """A press picks the cell it landed in; the rest see a press that missed."""
    row = inputs.InputFloat3("pos", (1.0, 2.0, 3.0))
    painter = RecordingPainter()
    row.draw(painter, 0.0, 0.0, 300.0, 20.0)
    cells = row._cells
    middle_x = cells[1][0] + cells[1][1] * 0.5
    row.press(middle_x, 10.0, 0.0, 0.0, 300.0, 20.0)
    assert row.editing == 1
    row.key(0, "9")
    row.key(keys.KEY_RETURN)
    assert row.values == pytest.approx([1.0, 9.0, 3.0])


def test_int_rows_hold_whole_numbers():
    """``InputInt2/3/4`` parse and store integers, not floats."""
    row = inputs.InputInt4("box", (1, 2, 3, 4))
    assert row.values == [1, 2, 3, 4]
    row.inputs[0].begin_edit()
    row.inputs[0].field.set_text("7.9")
    assert row.commit()[0] == 7
    assert isinstance(row.values[0], int)


def test_scalar_n_set_values_ignores_extras():
    """The component count is the row's shape, not its contents."""
    row = inputs.InputFloat2("uv", (0.0, 0.0))
    assert row.set_values([1.0, 2.0, 3.0]) == pytest.approx([1.0, 2.0])


# --------------------------------------------------------------------------
# The hint
# --------------------------------------------------------------------------
def test_hint_shows_only_while_empty_and_is_never_the_text():
    """A placeholder is not a value: it vanishes on the first character."""
    box = inputs.InputTextWithHint("q", "type a residue")
    assert box.text == ""
    assert box.showing_hint is True

    painter = RecordingPainter()
    box.draw(painter, 0.0, 0.0, 200.0, 20.0)
    assert "type a residue" in painter.strings

    box.insert("A")
    assert box.showing_hint is False
    assert box.text == "A"
    painter = RecordingPainter()
    box.draw(painter, 0.0, 0.0, 200.0, 20.0)
    assert "type a residue" not in painter.strings
    assert "A" in painter.strings

    # Deleting the last character brings the hint back -- and the text is still "".
    box.backspace()
    assert box.text == ""
    assert box.showing_hint is True


def test_a_field_with_no_hint_never_claims_to_show_one():
    """``showing_hint`` is about what is on screen, not about being empty."""
    box = inputs.InputTextWithHint("q")
    assert box.showing_hint is False


# --------------------------------------------------------------------------
# The multi-line editor
# --------------------------------------------------------------------------
def test_enter_then_backspace_round_trips_a_two_line_buffer():
    """Splitting a line and joining it back is the identity."""
    editor = inputs.InputTextMultiline("notes", "hello world")
    editor.set_cursor(0, 5)
    editor.key(keys.KEY_RETURN)
    assert editor.lines == ["hello", " world"]
    assert editor.cursor == (1, 0)
    editor.key(keys.KEY_BACKSPACE)
    assert editor.lines == ["hello world"]
    assert editor.cursor == (0, 5)
    assert editor.text == "hello world"


def test_delete_at_the_end_of_a_line_pulls_the_next_one_up():
    """Forward delete crosses the boundary the other way."""
    editor = inputs.InputTextMultiline(text="ab\ncd")
    editor.set_cursor(0, 2)
    editor.key(keys.KEY_DELETE)
    assert editor.lines == ["abcd"]
    assert editor.cursor == (0, 2)


def test_the_cursor_column_survives_a_trip_past_a_short_line():
    """Down onto a short line and back up must not truncate the column.

    The reference remembers a *preferred* position across a run of up/down
    moves; storing the clamped column instead is the classic bug, and it only
    shows when a short line sits between two long ones.
    """
    editor = inputs.InputTextMultiline(text="0123456789\nab\n0123456789")
    editor.set_cursor(0, 8)
    assert editor.move_down() == (1, 2)   # clamped onto the short line
    assert editor.move_down() == (2, 8)   # ...but the preference is remembered
    assert editor.move_up() == (1, 2)
    assert editor.move_up() == (0, 8)


def test_any_other_key_drops_the_preferred_column():
    """Type on a short line, press up, and you go where you just typed."""
    editor = inputs.InputTextMultiline(text="0123456789\nab\n0123456789")
    editor.set_cursor(2, 9)
    editor.move_up()                      # (1, 2), preferring column 9
    editor.key(keys.KEY_LEFT)             # any other key clears the preference
    assert editor.cursor == (1, 1)
    assert editor.move_up() == (0, 1)


def test_up_on_the_first_row_does_nothing_and_down_on_the_last_goes_to_its_end():
    """Both asymmetries are the reference's, not an oversight."""
    editor = inputs.InputTextMultiline(text="abcd\nef")
    editor.set_cursor(0, 2)
    assert editor.move_up() == (0, 2)
    editor.set_cursor(1, 0)
    assert editor.move_down() == (1, 2)


def test_left_and_right_wrap_across_the_line_boundary():
    """Walking off an end is the fourth thing a line editor cannot do alone."""
    editor = inputs.InputTextMultiline(text="ab\ncd")
    editor.set_cursor(1, 0)
    assert editor.move_left() == (0, 2)
    assert editor.move_right() == (1, 0)
    # ...and neither wraps off the ends of the buffer.
    editor.set_cursor(0, 0)
    assert editor.move_left() == (0, 0)
    editor.set_cursor(1, 2)
    assert editor.move_right() == (1, 2)


def test_typing_a_pasted_block_keeps_its_newlines():
    """A one-line field drops newlines; this one is the reason they exist."""
    editor = inputs.InputTextMultiline()
    editor.insert("one\r\ntwo\nthree")
    assert editor.lines == ["one", "two", "three"]
    assert editor.cursor == (2, 5)


def test_the_window_scrolls_to_keep_the_caret_visible():
    """Rows that fit come from the box, so following happens at draw time."""
    editor = inputs.InputTextMultiline(text="\n".join(str(n) for n in range(20)))
    painter = RecordingPainter()
    # 12 px lines * 1.2 = 14.4 px a row; a 60 px body shows four of them.
    editor.set_cursor(0, 0)
    editor.draw(painter, 0.0, 0.0, 200.0, 60.0 + 14.4)
    assert editor.top == 0
    assert painter.strings[0] == "0"

    editor.set_cursor(15, 0)
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, 200.0, 60.0 + 14.4)
    assert editor.top == 15 - editor.visible_rows + 1
    assert str(15) in painter.strings
    assert painter.clips == []


def test_a_press_puts_the_caret_where_it_landed():
    """Columns are measured with the painter the editor was last drawn with."""
    editor = inputs.InputTextMultiline(text="abcdef\nghij")
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, 200.0, 60.0)
    # Row 1, three characters in: 4 px of padding plus 3 * 7 px per character.
    assert editor.press(4.0 + 21.0, 20.0, 0.0, 0.0, 200.0, 60.0) == (1, 3)
    # A press outside is not this control's.
    assert editor.press(400.0, 400.0, 0.0, 0.0, 200.0, 60.0) is None
