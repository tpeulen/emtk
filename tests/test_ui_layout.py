"""Painter-level tests for the layout cursor.

:class:`~emtk.layout.Layout` draws nothing, so what there is to
test is arithmetic -- and the only test worth writing about arithmetic is one
that asserts the *exact* rectangle a host would otherwise have hand-computed.
Every number below was worked out from the reference implementation's
``ItemSize`` / ``SameLine`` / ``BeginGroup`` / ``Columns`` and is written out
here rather than derived from the code under test, which is the point.

The box is ``(10, 20, 200, 300)`` throughout and the painter measures a line at
12 pixels, so with the reference's style constants:

* a default row is ``12 + 3 * 2 = 18`` tall,
* rows are ``4`` apart and items on a line ``8`` apart,
* one indent step is ``12 + 4 * 2 = 20``.

emtk's own defaults are denser (:data:`emtk.layout.FRAME_PADDING`,
:data:`~emtk.layout.ITEM_SPACING`), so these tests lay out with the
reference's constants, :data:`REFERENCE`, and one test checks the defaults.
"""

from __future__ import annotations

import pytest

from emtk.widgets import basic as widgets
from emtk.layout import Layout, LayoutStyle


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


BOX = (10.0, 20.0, 200.0, 300.0)
#: The reference's ``ItemSpacing = (8, 4)`` and ``FramePadding = (4, 3)``.
REFERENCE = LayoutStyle(item_spacing_x=8.0, item_spacing_y=4.0,
                        frame_padding_x=4.0, frame_padding_y=3.0)


def make() -> tuple[RecordingPainter, Layout]:
    """A painter and a layout over :data:`BOX`."""
    painter = RecordingPainter()
    return painter, Layout(painter, *BOX, style=REFERENCE)


# ---------------------------------------------------------------------- #
# The cursor
# ---------------------------------------------------------------------- #
def test_rows_walk_down_the_box_at_the_reference_pitch():
    """Three rows: full width, 18 tall, 22 apart (``18 + ItemSpacing.y``)."""
    _, layout = make()
    assert layout.row_height == 18.0
    assert layout.indent_step == 20.0
    assert layout.row() == (10.0, 20.0, 200.0, 18.0)
    assert layout.row() == (10.0, 42.0, 200.0, 18.0)
    assert layout.row() == (10.0, 64.0, 200.0, 18.0)


def test_a_row_takes_the_height_it_is_given():
    """An explicit height is the item height; the pitch follows it."""
    _, layout = make()
    assert layout.row(30.0) == (10.0, 20.0, 200.0, 30.0)
    assert layout.row(30.0) == (10.0, 54.0, 200.0, 30.0)


def test_the_cursor_is_snapped_to_whole_pixels():
    """The reference truncates ``CursorPos``; a fractional row must not smear."""
    _, layout = make()
    layout.row(18.5)
    # 20 + 18.5 + 4 = 42.5, truncated.
    assert layout.cursor == (10.0, 42.0)


def test_layout_draws_nothing():
    """It is a cursor, not a control: no ops, and so no clip stack to unbalance."""
    painter, layout = make()
    layout.row()
    layout.separator()
    layout.begin_group()
    layout.row()
    layout.end_group()
    layout.columns(2)
    layout.row()
    layout.next_column()
    layout.row()
    layout.end_columns()
    assert (painter.fills, painter.strokes, painter.strings, painter.clips) == ([], [], [], [])


# ---------------------------------------------------------------------- #
# same_line -- two rules, not one
# ---------------------------------------------------------------------- #
def test_same_line_puts_the_next_row_beside_the_previous_at_the_same_y():
    """Offset 0: right after the previous item, one ``ItemSpacing.x`` along."""
    _, layout = make()
    first = layout.row(width=60.0)
    assert first == (10.0, 20.0, 60.0, 18.0)
    layout.same_line()
    second = layout.row(width=40.0)
    # 10 + 60 = 70, plus the 8-pixel gap; same y as the row it sits beside.
    assert second == (78.0, 20.0, 40.0, 18.0)
    assert second[1] == first[1]
    # And the line as a whole is one row tall: the next row clears both.
    assert layout.row() == (10.0, 42.0, 200.0, 18.0)


def test_same_line_with_an_offset_is_measured_from_the_box_not_the_item():
    """Offset != 0: an absolute x from the box's left edge, and **no** default gap."""
    _, layout = make()
    layout.row(width=60.0)
    layout.same_line(100.0)
    assert layout.row(width=40.0) == (110.0, 20.0, 40.0, 18.0)


def test_the_two_same_line_forms_default_to_different_spacing():
    """Offset 0 defaults to ``ItemSpacing.x``; an explicit offset defaults to zero."""
    _, relative = make()
    relative.row(width=60.0)
    relative.same_line()
    _, absolute = make()
    absolute.row(width=60.0)
    absolute.same_line(70.0)
    # Same nominal position -- 70 is where the first row ended -- but only the
    # relative form adds a gap to it.
    assert relative.cursor[0] == 78.0
    assert absolute.cursor[0] == 80.0


def test_explicit_spacing_overrides_both_defaults():
    """``spacing`` is honoured whichever form is in use."""
    _, relative = make()
    relative.row(width=60.0)
    relative.same_line(spacing=6.0)
    assert relative.cursor[0] == 76.0

    _, absolute = make()
    absolute.row(width=60.0)
    absolute.same_line(100.0, spacing=6.0)
    assert absolute.cursor[0] == 116.0


def test_a_full_width_row_leaves_no_room_beside_it():
    """The reference behaves the same way; this is why ``row`` takes a width."""
    _, layout = make()
    layout.row()
    layout.same_line()
    assert layout.cursor[0] == 218.0
    assert layout.avail()[0] == 0.0


# ---------------------------------------------------------------------- #
# Indent
# ---------------------------------------------------------------------- #
def test_nested_indent_returns_to_the_original_x_exactly():
    """Two in, two out, back to the box's left edge -- not near it."""
    _, layout = make()
    assert layout.row()[0] == 10.0
    layout.indent()
    assert layout.row() == (30.0, 42.0, 180.0, 18.0)
    layout.indent()
    assert layout.row() == (50.0, 64.0, 160.0, 18.0)
    layout.unindent()
    assert layout.row()[0] == 30.0
    layout.unindent()
    assert layout.row()[0] == 10.0
    assert layout.indent_x == 0.0


def test_an_explicit_indent_width_is_undone_by_the_same_width():
    """Fractional steps too: the margin is stored, not re-derived per row."""
    _, layout = make()
    layout.indent(7.5)
    assert layout.row()[0] == 17.5
    layout.unindent(7.5)
    assert layout.indent_x == 0.0
    assert layout.row()[0] == 10.0


# ---------------------------------------------------------------------- #
# Groups
# ---------------------------------------------------------------------- #
def test_a_group_spans_all_of_its_items_including_a_same_line_one():
    """The bounding box reaches the right edge of the item placed beside."""
    _, layout = make()
    layout.begin_group()
    layout.row(width=50.0)
    layout.same_line()
    layout.row(width=30.0)
    layout.row(width=20.0)
    # Two lines (18 tall, 4 apart) and a widest reach of 10 + 50 + 8 + 30.
    assert layout.end_group() == (10.0, 20.0, 88.0, 40.0)


def test_a_group_advances_the_cursor_as_one_item():
    """The row after a group clears the whole group, not just its last line."""
    _, layout = make()
    layout.begin_group()
    layout.row(width=50.0)
    layout.row(width=50.0)
    assert layout.end_group() == (10.0, 20.0, 50.0, 40.0)
    # 20 + 40 + 4.
    assert layout.row() == (10.0, 64.0, 200.0, 18.0)


def test_a_group_locks_its_left_margin_where_it_started():
    """Opened after ``same_line``, a group lays out down its own edge."""
    _, layout = make()
    layout.row(width=60.0)
    layout.same_line()
    layout.begin_group()
    assert layout.row(width=40.0) == (78.0, 20.0, 40.0, 18.0)
    assert layout.row(width=40.0) == (78.0, 42.0, 40.0, 18.0)
    assert layout.end_group() == (78.0, 20.0, 40.0, 40.0)


def test_same_line_inside_a_group_is_relative_to_the_group():
    """The reference adds ``GroupOffset`` to an explicit offset; the group is the origin."""
    _, layout = make()
    layout.indent()
    layout.begin_group()
    layout.row(width=40.0)
    layout.same_line(10.0)
    # Group left is 30 (one indent), so offset 10 lands at 40 -- not at 20.
    assert layout.row(width=20.0) == (40.0, 20.0, 20.0, 18.0)


def test_a_group_restores_the_margin_it_found():
    """A group nested under an indent leaves that indent alone."""
    _, layout = make()
    layout.indent()
    layout.begin_group()
    layout.indent()
    layout.row()
    layout.end_group()
    assert layout.indent_x == 20.0
    assert layout.row()[0] == 30.0


def test_end_group_without_begin_group_is_loud():
    """An unbalanced group corrupts every row after it, silently. Not here."""
    _, layout = make()
    with pytest.raises(RuntimeError):
        layout.end_group()


# ---------------------------------------------------------------------- #
# Columns
# ---------------------------------------------------------------------- #
def test_columns_divide_the_width_the_way_the_reference_does():
    """Even split of ``[indent - padding, right edge]``, each column inset by ``2 * padding``."""
    _, layout = make()
    layout.columns(2)
    # Span is 200 - (0 - 8) = 208, so a column is 104 wide and an item in it 88.
    assert layout.row() == (10.0, 20.0, 88.0, 18.0)
    layout.next_column()
    assert layout.row() == (114.0, 20.0, 88.0, 18.0)
    assert layout.column_index == 1
    assert layout.column_count == 2


def test_three_columns_split_a_span_that_does_not_divide_evenly():
    """Left edges are snapped to whole pixels, so the widths differ by under one.

    The reference truncates ``CursorPos`` but not the column edge it measures
    against, so a span of 208 over three columns gives 53.33 / 53.67 / 54.00
    rather than three identical widths. Asserted exactly, because "roughly a
    third each" is the assertion that would hide a genuine off-by-one.
    """
    _, layout = make()
    layout.columns(3)
    boxes = []
    for _ in range(3):
        boxes.append(layout.row())
        layout.next_column()
    lefts = [box[0] for box in boxes]
    widths = [box[2] for box in boxes]
    # Span 208 / 3 = 69.333..., truncated at the cursor.
    assert lefts == [10.0, 79.0, 148.0]
    assert widths == pytest.approx([160.0 / 3.0, 161.0 / 3.0, 54.0])
    assert max(widths) - min(widths) < 1.0
    # The last column stops one padding short of the box's right edge.
    assert boxes[2][0] + boxes[2][2] == 202.0


def test_wrapping_past_the_last_column_starts_below_the_tallest():
    """Unequal columns still line up underneath -- that is what ``LineMaxY`` is for."""
    _, layout = make()
    layout.columns(2)
    layout.row()
    layout.row()          # column 0 is two rows tall, reaching y = 64
    layout.next_column()
    assert layout.row() == (114.0, 20.0, 88.0, 18.0)
    layout.next_column()  # wraps back to column 0
    assert layout.row() == (10.0, 64.0, 88.0, 18.0)


def test_ending_columns_puts_the_cursor_below_the_tallest_column():
    """And restores the full width."""
    _, layout = make()
    layout.columns(2)
    layout.row()
    layout.next_column()
    layout.row()
    layout.row()          # column 1 is the taller one, reaching y = 64
    layout.end_columns()
    assert layout.row() == (10.0, 64.0, 200.0, 18.0)


def test_columns_one_ends_the_set_and_re_declaring_is_a_no_op():
    """The reference's ``Columns(1)``; a host may call ``columns`` every frame."""
    _, layout = make()
    layout.columns(2)
    layout.row()
    layout.columns(2)
    assert layout.column_count == 2
    layout.columns(1)
    assert layout.column_count == 1
    assert layout.avail()[0] == 200.0
    with pytest.raises(ValueError):
        layout.columns(0)


# ---------------------------------------------------------------------- #
# Spacing helpers
# ---------------------------------------------------------------------- #
def test_spacing_leaves_one_gap():
    """``ItemSize(0, 0)``: no height of its own, one ``ItemSpacing.y``."""
    _, layout = make()
    layout.row()
    layout.spacing()
    assert layout.row() == (10.0, 46.0, 200.0, 18.0)


def test_dummy_reserves_a_box_and_hands_it_back():
    """Reserved, not drawn -- but a caller that changes its mind gets the rect."""
    _, layout = make()
    assert layout.dummy(30.0, 10.0) == (10.0, 20.0, 30.0, 10.0)
    assert layout.row() == (10.0, 34.0, 200.0, 18.0)


def test_new_line_costs_a_text_line_when_the_line_is_empty():
    """An empty ``new_line`` is a blank line; after a row it just ends the line."""
    _, empty = make()
    empty.new_line()
    assert empty.row() == (10.0, 36.0, 200.0, 18.0)

    _, filled = make()
    filled.row(width=60.0)
    filled.same_line()
    filled.new_line()
    assert filled.row() == (10.0, 42.0, 200.0, 18.0)


def test_separator_spans_the_width_but_does_not_widen_the_panel():
    """The reference feeds ``ItemSize(0, thickness)`` -- zero width -- on purpose."""
    _, layout = make()
    layout.row(width=60.0)
    assert layout.separator() == (10.0, 42.0, 200.0, 1.0)
    # The rule reaches 200 wide, but the content is still only the 60-wide row.
    assert layout.content_width() == 60.0
    assert layout.row() == (10.0, 47.0, 200.0, 18.0)


def test_separator_takes_a_thickness():
    """A thicker rule reserves more room."""
    _, layout = make()
    assert layout.separator(4.0) == (10.0, 20.0, 200.0, 4.0)
    assert layout.row()[1] == 28.0


# ---------------------------------------------------------------------- #
# Measurement
# ---------------------------------------------------------------------- #
def test_avail_shrinks_as_the_cursor_moves_and_never_goes_negative():
    """What a host sizes a control against."""
    _, layout = make()
    assert layout.avail() == (200.0, 300.0)
    layout.indent()
    assert layout.avail() == (180.0, 300.0)
    layout.row()
    assert layout.avail() == (180.0, 278.0)
    for _ in range(20):
        layout.row(30.0)
    assert layout.avail()[1] == 0.0


def test_content_height_is_the_sum_of_what_was_laid_out():
    """The canonical sequence: three rows, a ``same_line``, an indent, a group.

    Five lines of 18 with four 4-pixel gaps between them: ``5 * 18 + 4 * 4``.
    """
    _, layout = make()
    assert layout.row() == (10.0, 20.0, 200.0, 18.0)
    assert layout.row() == (10.0, 42.0, 200.0, 18.0)
    assert layout.row(width=60.0) == (10.0, 64.0, 60.0, 18.0)
    layout.same_line()
    assert layout.row(width=40.0) == (78.0, 64.0, 40.0, 18.0)
    layout.indent()
    assert layout.row() == (30.0, 86.0, 180.0, 18.0)
    layout.begin_group()
    assert layout.row(width=50.0) == (30.0, 108.0, 50.0, 18.0)
    layout.same_line()
    assert layout.row(width=30.0) == (88.0, 108.0, 30.0, 18.0)
    assert layout.end_group() == (30.0, 108.0, 88.0, 18.0)
    layout.unindent()
    assert layout.cursor == (10.0, 130.0)
    assert layout.content_height() == 5 * 18.0 + 4 * 4.0
    assert layout.content_height() == 106.0


def test_content_height_does_not_count_the_gap_after_the_last_row():
    """A panel its rows exactly fill must not grow a scrollbar for nothing."""
    painter = RecordingPainter()
    layout = Layout(painter, 0.0, 0.0, 100.0, 40.0, REFERENCE)
    layout.row()
    layout.row()
    assert layout.content_height() == 40.0
    assert layout.content_height() <= layout.h


def test_reset_puts_the_cursor_back():
    """A retained layout is re-boxed and re-run every frame."""
    _, layout = make()
    layout.indent()
    layout.begin_group()
    layout.row()
    layout.reset()
    assert layout.cursor == (10.0, 20.0)
    assert layout.indent_x == 0.0
    assert layout.content_height() == 0.0
    layout.reset(w=50.0)
    assert layout.row() == (10.0, 20.0, 50.0, 18.0)


def test_a_custom_style_changes_the_arithmetic_and_nothing_else():
    """The constants are data; a host that wants a tighter panel says so."""
    painter = RecordingPainter()
    tight = LayoutStyle(item_spacing_x=2.0, item_spacing_y=0.0, frame_padding_y=0.0,
                        indent_spacing=8.0)
    layout = Layout(painter, 0.0, 0.0, 100.0, 100.0, tight)
    assert layout.row() == (0.0, 0.0, 100.0, 12.0)
    assert layout.row() == (0.0, 12.0, 100.0, 12.0)
    layout.indent()
    assert layout.row()[0] == 8.0


# ---------------------------------------------------------------------- #
# The point of all of it
# ---------------------------------------------------------------------- #
def test_a_control_drawn_into_a_row_paints_inside_that_row():
    """The smoke test: hand a row straight to a control and nothing escapes it."""
    painter, layout = make()
    layout.row()                      # something above it, so y is not the box top
    box = layout.row()
    widgets.Button("go").draw(painter, *box)
    box_x, box_y, box_w, box_h = box
    assert painter.strokes
    for x, y, w, h, *_rest in painter.fills + painter.strokes:
        assert box_x <= x and x + w <= box_x + box_w
        assert box_y <= y and y + h <= box_y + box_h
    assert painter.clips == []


def test_a_column_of_controls_stays_inside_its_column():
    """Two controls, two columns, no overlap -- what the hand-computed version got wrong."""
    painter, layout = make()
    layout.columns(2)
    left = layout.row()
    widgets.Checkbox("on", True).draw(painter, *left)
    layout.next_column()
    right = layout.row()
    widgets.Button("go").draw(painter, *right)
    assert left[0] + left[2] <= right[0]
    for x, y, w, h, *_rest in painter.fills + painter.strokes:
        assert x >= left[0]
        assert x + w <= right[0] + right[2]


# --------------------------------------------------------------------------- #
# The window follows the frame
#
# A host resizes. emtk keeps windows in `storage`, which is carried across
# frames on purpose -- and a *stored* box does not follow a frame box that
# changed. Every test above builds fresh state per frame, which is exactly the
# arrangement in which this cannot be seen: the content stopped at the old
# window's edge and the rest of the widened one stayed blank.
# --------------------------------------------------------------------------- #
def _window_size_across(boxes, **begin_kw):
    """Draw one window per box, sharing io and storage as a host does."""
    import emtk
    from emtk.testing import PixelPainter

    io, storage, seen = emtk.IO(), {}, []
    for w, h in boxes:
        painter = PixelPainter(int(w), int(h), background=(0, 0, 0, 255))
        with emtk.frame(painter, (0, 0, float(w), float(h)),
                        io=io, storage=storage):
            emtk.begin("w", **begin_kw)
            seen.append((emtk.get_window_size(),
                         emtk.get_content_region_avail()))
            emtk.end()
    return seen


def test_a_window_with_no_box_of_its_own_follows_the_frame():
    """It *is* the frame, so it has to keep being the frame -- growing and
    shrinking with the host, not only on the frame that created it."""
    seen = _window_size_across([(900, 620), (1400, 900), (700, 400)])
    assert [size for size, _avail in seen] == [(900, 620), (1400, 900), (700, 400)]


def test_the_content_region_follows_it_too():
    """What a widget asking for ``-1`` width gets. A plot sized from a stale
    content region is the visible half of this bug."""
    seen = _window_size_across([(900, 620), (1400, 900)])
    assert [avail for _size, avail in seen] == [(900.0, 620.0), (1400.0, 900.0)]


def test_a_window_given_a_box_keeps_it():
    """An explicit box is the caller's decision and outranks the frame."""
    import emtk
    from emtk.testing import PixelPainter

    io, storage, seen = emtk.IO(), {}, []
    for w, h in ((900, 620), (1400, 900)):
        painter = PixelPainter(w, h, background=(0, 0, 0, 255))
        with emtk.frame(painter, (0, 0, float(w), float(h)), io=io, storage=storage):
            emtk.begin("w", box=(10.0, 10.0, 300.0, 200.0))
            seen.append(emtk.get_window_size())
            emtk.end()
    assert seen == [(300, 200), (300, 200)]


def test_an_auto_resizing_window_still_sizes_to_its_content():
    """``auto_resize`` sizes the window in ``end()``, which is the earliest
    its content is known -- so the *first* frame is still frame-sized. What
    must not happen is the second one going back: following the frame would
    overwrite the measured size every frame and the window would never
    shrink at all."""
    import emtk
    from emtk.testing import PixelPainter

    io, storage, seen = emtk.IO(), {}, []
    for w, h in ((900, 620), (1400, 900), (700, 400)):
        painter = PixelPainter(w, h, background=(0, 0, 0, 255))
        with emtk.frame(painter, (0, 0, float(w), float(h)), io=io, storage=storage):
            emtk.begin("w", auto_resize=True)
            emtk.text("short")
            seen.append(emtk.get_window_size())
            emtk.end()
    assert seen[0] == (900, 620), "the first frame cannot know the content yet"
    assert all(size[0] < 100 for size in seen[1:]), seen


def test_emtks_defaults_are_a_text_line_plus_2_px_and_3_px_apart():
    """emtk's own density: a field is its line plus 2 px above and below, and
    the next line starts 3 px under it -- the same numbers the ``Style`` has."""
    from emtk import Style
    from emtk.layout import FRAME_PADDING, ITEM_SPACING

    layout = Layout(RecordingPainter(), *BOX)
    assert layout.row() == (10.0, 20.0, 200.0, 16.0)
    assert layout.row() == (10.0, 39.0, 200.0, 16.0)
    assert Style().frame_padding == FRAME_PADDING == (4.0, 2.0)
    assert Style().item_spacing == ITEM_SPACING == (8.0, 3.0)
