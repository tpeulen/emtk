"""Painter-level tests for the ported Dear ImGui tables subsystem.

Everything here is arithmetic and recorded draw calls -- no Qt, no window, no
event loop. The numbers are the reference's numbers: where a test asserts an
exact width it is because ``TableUpdateLayout`` computes exactly that, and a
port that "looks right" while dividing the leftover width differently fails
here rather than in someone's eyes six months later.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import tables


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


class TracingPainter(RecordingPainter):
    """A :class:`RecordingPainter` that also keeps every clip ever pushed.

    The base class pops clips off its list, which is what makes "the stack came
    back balanced" assertable -- but it means a finished frame remembers no clip
    rectangles at all, and the cell-clipping tests need precisely those.
    """

    def __init__(self) -> None:
        super().__init__()
        self.all_clips: list[tuple] = []
        #: ``(clip_rect_at_the_time, string)`` for every string drawn.
        self.clipped_strings: list[tuple] = []

    def push_clip(self, x, y, w, h) -> None:
        super().push_clip(x, y, w, h)
        self.all_clips.append((x, y, w, h))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        super().text(x, y, w, h, align, string, colour, bold)
        self.clipped_strings.append((self.clips[-1] if self.clips else None, string))


def make_table(**kwargs):
    """A three-column stretch table with four rows of short values.

    Parameters
    ----------
    **kwargs
        Passed through to :class:`~cmtk.widgets.tables.DataTable`.

    Returns
    -------
    DataTable
        Padding is zeroed unless a test says otherwise, so the arithmetic in
        the assertions is the sizing arithmetic and nothing else.
    """
    kwargs.setdefault("cell_padding", 0.0)
    kwargs.setdefault("outer_padding", 0.0)
    rows = [["a", "1", "x"], ["b", "2", "y"], ["c", "3", "z"], ["d", "4", "w"]]
    return tables.DataTable(["A", "B", "C"], rows, **kwargs)


# --------------------------------------------------------------------------
# Smoke
# --------------------------------------------------------------------------
def test_paints_and_balances_its_clips():
    """It draws something and leaves the clip stack as it found it."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert p.fills or p.strokes or p.strings
    assert p.clips == []


def test_paints_and_balances_its_clips_with_everything_on():
    """Frozen panes, an open menu, a scrollbar and a sort still balance."""
    p = RecordingPainter()
    table = make_table(freeze_rows=1, freeze_cols=1, sort_tristate=True)
    table.rows = [[str(i), str(i * 2), str(i * 3)] for i in range(50)]
    table.click_header(1)
    table.click_header(2, append=True)
    table.open_context_menu(1, at=(20.0, 20.0))
    table.scroll(30)
    table.draw(p, 5.0, 7.0, 300.0, 120.0)
    assert p.clips == []
    assert p.strings


def test_empty_table_still_balances():
    """No columns and no rows is not a crash and not an unbalanced clip."""
    p = RecordingPainter()
    table = tables.DataTable([], [])
    table.draw(p, 0.0, 0.0, 100.0, 50.0)
    assert p.clips == []


# --------------------------------------------------------------------------
# Sizing: stretch weights
# --------------------------------------------------------------------------
def test_stretch_same_divides_the_width_equally():
    """``SizingStretchSame`` seeds every weight to 1.0, so thirds of 300."""
    p = RecordingPainter()
    table = make_table(sizing=tables.SIZING_STRETCH_SAME)
    table.update_layout(p, 0.0, 300.0)
    assert [c.width_given for c in table.columns] == [100.0, 100.0, 100.0]


def test_stretch_weights_divide_the_leftover_in_proportion():
    """Weights 1:2:3 of 300 give 50, 100, 150 -- and sum to the full width."""
    p = RecordingPainter()
    columns = [
        tables.Column("A", tables.WIDTH_STRETCH, 1.0),
        tables.Column("B", tables.WIDTH_STRETCH, 2.0),
        tables.Column("C", tables.WIDTH_STRETCH, 3.0),
    ]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.update_layout(p, 0.0, 300.0)
    assert [c.width_given for c in table.columns] == [50.0, 100.0, 150.0]
    assert sum(c.width_given for c in table.columns) == 300.0


def test_stretch_columns_divide_only_what_the_fixed_ones_leave():
    """A fixed 100 out of 300 leaves 200 to be split 1:1."""
    p = RecordingPainter()
    columns = [
        tables.Column("Fix", tables.WIDTH_FIXED, 100.0),
        tables.Column("A", tables.WIDTH_STRETCH, 1.0),
        tables.Column("B", tables.WIDTH_STRETCH, 1.0),
    ]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.update_layout(p, 0.0, 300.0)
    assert [c.width_given for c in table.columns] == [100.0, 100.0, 100.0]


def test_remainder_is_handed_back_right_to_left():
    """100 across three equal columns is 33/33/34, not 33/33/33.

    The reference truncates each share and then walks the columns *right to
    left* handing the lost pixels back, which is why the widest column is the
    last one and not the first.
    """
    p = RecordingPainter()
    table = make_table(sizing=tables.SIZING_STRETCH_SAME)
    table.update_layout(p, 0.0, 100.0)
    assert [c.width_given for c in table.columns] == [33.0, 33.0, 34.0]
    assert sum(c.width_given for c in table.columns) == 100.0


def test_precise_widths_keeps_the_remainder():
    """``PreciseWidths`` skips the handout, leaving the row a pixel short."""
    p = RecordingPainter()
    table = make_table(sizing=tables.SIZING_STRETCH_SAME, precise_widths=True)
    table.update_layout(p, 0.0, 100.0)
    assert [c.width_given for c in table.columns] == [33.0, 33.0, 33.0]


def test_stretch_prop_seeds_weights_from_measured_content():
    """``SizingStretchProp`` gives the column with wider content more room."""
    p = RecordingPainter()
    rows = [["short", "a considerably longer value"]]
    table = tables.DataTable(
        ["A", "B"], rows, sizing=tables.SIZING_STRETCH_PROP,
        cell_padding=0.0, outer_padding=0.0, sortable=False,
    )
    table.update_layout(p, 0.0, 400.0)
    wide, narrow = table.columns[1], table.columns[0]
    assert wide.width_given > narrow.width_given
    # weight = width_auto / sum(width_auto) * count_stretch
    total_auto = sum(c.width_auto for c in table.columns)
    expected = (wide.width_auto / total_auto) * 2
    assert wide.stretch_weight == pytest.approx(expected)


def test_stretch_same_ignores_content_width():
    """The same table under ``StretchSame`` splits evenly regardless."""
    p = RecordingPainter()
    rows = [["short", "a considerably longer value"]]
    table = tables.DataTable(
        ["A", "B"], rows, sizing=tables.SIZING_STRETCH_SAME,
        cell_padding=0.0, outer_padding=0.0,
    )
    table.update_layout(p, 0.0, 400.0)
    assert [c.width_given for c in table.columns] == [200.0, 200.0]


# --------------------------------------------------------------------------
# Sizing: fixed policies
# --------------------------------------------------------------------------
def test_fixed_fit_gives_each_column_its_own_ideal_width():
    """``SizingFixedFit`` latches each column's measured content width."""
    p = RecordingPainter()
    rows = [["ab", "abcdef"]]
    table = tables.DataTable(
        ["A", "B"], rows, sizing=tables.SIZING_FIXED_FIT,
        cell_padding=0.0, outer_padding=0.0, sortable=False, keep_columns_visible=False,
    )
    table.update_layout(p, 0.0, 400.0)
    # 7 px per character; the headers are one character each.
    assert [c.width_given for c in table.columns] == [14.0, 42.0]


def test_fixed_same_gives_every_column_the_widest_ideal_width():
    """``SizingFixedSame`` widens every fixed column to the widest one."""
    p = RecordingPainter()
    rows = [["ab", "abcdef"]]
    table = tables.DataTable(
        ["A", "B"], rows, sizing=tables.SIZING_FIXED_SAME,
        cell_padding=0.0, outer_padding=0.0, sortable=False, keep_columns_visible=False,
    )
    table.update_layout(p, 0.0, 400.0)
    assert [c.width_given for c in table.columns] == [42.0, 42.0]


def test_a_fixed_column_that_does_not_fit_is_shrunk_not_clipped():
    """Keep-columns-visible reserves the minimum for everything to its right.

    ``TableCalcMaxColumnWidth``: a 500-wide column in a 100-wide table with two
    more columns after it may only reach ``100 - 2 * min_column_width``.
    """
    p = RecordingPainter()
    columns = [
        tables.Column("Huge", tables.WIDTH_FIXED, 500.0),
        tables.Column("B", tables.WIDTH_FIXED, 20.0),
        tables.Column("C", tables.WIDTH_FIXED, 20.0),
    ]
    table = tables.DataTable(
        columns, [["a", "b", "c"]], sizing=tables.SIZING_FIXED_FIT,
        cell_padding=0.0, outer_padding=0.0, min_column_width=4.0,
    )
    table.update_layout(p, 0.0, 100.0)
    assert table.columns[0].width_given == 100.0 - 2 * 4.0
    assert table.columns[0].width_request == 500.0  # the request is untouched


def test_no_keep_columns_visible_lets_a_fixed_column_overflow():
    """Turn the rule off and the column keeps its full requested width."""
    p = RecordingPainter()
    columns = [tables.Column("Huge", tables.WIDTH_FIXED, 500.0), tables.Column("B")]
    table = tables.DataTable(
        columns, [["a", "b"]], sizing=tables.SIZING_FIXED_FIT,
        cell_padding=0.0, outer_padding=0.0, keep_columns_visible=False,
    )
    table.update_layout(p, 0.0, 100.0)
    assert table.columns[0].width_given == 500.0


def test_fixed_columns_are_untouched_when_the_table_is_resized():
    """Widen the table and only the stretch columns take the extra room."""
    p = RecordingPainter()
    columns = [
        tables.Column("Fix", tables.WIDTH_FIXED, 80.0),
        tables.Column("A", tables.WIDTH_STRETCH, 1.0),
        tables.Column("B", tables.WIDTH_STRETCH, 1.0),
    ]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.update_layout(p, 0.0, 280.0)
    assert [c.width_given for c in table.columns] == [80.0, 100.0, 100.0]
    table.update_layout(p, 0.0, 480.0)
    assert [c.width_given for c in table.columns] == [80.0, 200.0, 200.0]


def test_cell_padding_is_taken_out_before_the_stretch_share():
    """Padding is charged per column, not divided along with the content."""
    p = RecordingPainter()
    table = make_table(cell_padding=5.0)
    table.update_layout(p, 0.0, 330.0)
    # 330 - 3 columns * 2 * 5 = 300 to split three ways.
    assert [c.width_given for c in table.columns] == [100.0, 100.0, 100.0]
    # ... and the cell boxes include their padding again.
    assert table.columns[0].max_x == 110.0
    assert table.columns[0].work_min_x == 5.0


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------
def test_columns_are_laid_out_left_to_right_from_the_table_origin():
    """``min_x``/``max_x`` chain across the row without gaps."""
    p = RecordingPainter()
    table = make_table()
    table.update_layout(p, 30.0, 300.0)
    assert [c.min_x for c in table.columns] == [30.0, 130.0, 230.0]
    assert [c.max_x for c in table.columns] == [130.0, 230.0, 330.0]


def test_reordering_moves_the_geometry_not_the_data():
    """A moved column keeps its index; only ``display_order`` changes."""
    p = RecordingPainter()
    table = make_table()
    table.set_column_display_order(0, 2)
    table.update_layout(p, 0.0, 300.0)
    assert [c.display_order for c in table.columns] == [2, 0, 1]
    assert table.enabled_columns() == [1, 2, 0]
    assert table.columns[0].min_x == 200.0
    # The rows were not touched.
    assert table.rows[0] == ["a", "1", "x"]


# --------------------------------------------------------------------------
# Resizing
# --------------------------------------------------------------------------
def test_dragging_a_border_widens_one_column_and_narrows_its_right_neighbour():
    """Stretch columns keep their pair total, so B pays for A's gain."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert [c.width_given for c in table.columns] == [100.0, 100.0, 100.0]

    assert table.press(100.0, 5.0, 0.0, 0.0, 300.0, 120.0) == ("resize", 0)
    assert table.drag(140.0, 5.0, 0.0, 0.0, 300.0, 120.0) is True
    table.release()
    assert table.columns[0].width_request == 140.0
    assert table.columns[1].width_request == 60.0
    assert table.columns[2].width_request == 100.0  # untouched

    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert [c.width_given for c in table.columns] == [140.0, 60.0, 100.0]


def test_a_resize_survives_the_next_layout_because_weights_are_re_derived():
    """Without ``TableUpdateColumnsWeightFromWidth`` the drag would be undone."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.press(100.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    table.drag(160.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    table.release()
    weights = [c.stretch_weight for c in table.columns]
    assert weights[0] == pytest.approx(1.6)
    assert weights[1] == pytest.approx(0.4)
    # Same proportions at a different table width.
    table.draw(p, 0.0, 0.0, 600.0, 120.0)
    assert [c.width_given for c in table.columns] == [320.0, 80.0, 200.0]


def test_a_fixed_column_before_any_stretch_column_resizes_by_offsetting():
    """No neighbour pays: the fixed column takes the width, the rest slide."""
    p = RecordingPainter()
    columns = [
        tables.Column("Fix", tables.WIDTH_FIXED, 80.0),
        tables.Column("A", tables.WIDTH_STRETCH, 1.0),
        tables.Column("B", tables.WIDTH_STRETCH, 1.0),
    ]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.draw(p, 0.0, 0.0, 280.0, 120.0)
    assert table.press(80.0, 5.0, 0.0, 0.0, 280.0, 120.0) == ("resize", 0)
    table.drag(120.0, 5.0, 0.0, 0.0, 280.0, 120.0)
    table.release()
    assert table.columns[0].width_request == 120.0
    # The stretch columns kept their weights and simply got less leftover.
    assert table.columns[1].stretch_weight == 1.0
    assert table.columns[2].stretch_weight == 1.0
    table.draw(p, 0.0, 0.0, 280.0, 120.0)
    assert [c.width_given for c in table.columns] == [120.0, 80.0, 80.0]


def test_a_resize_cannot_take_a_neighbour_below_the_minimum():
    """The neighbour stops at ``min_column_width`` and the drag stops with it."""
    p = RecordingPainter()
    table = make_table(min_column_width=20.0)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.press(100.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    table.drag(1000.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    table.release()
    assert table.columns[1].width_request == 20.0
    assert table.columns[0].width_request == 180.0
    assert table.columns[0].width_request + table.columns[1].width_request == 200.0


def test_the_right_most_border_is_not_grabbable_when_a_stretch_column_exists():
    """Resize Rule 1: there is nothing to its right to take the width from."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.columns[2].no_direct_resize is True
    assert table.column_border_at(300.0) == -1
    assert table.column_border_at(100.0) == 0


def test_an_all_fixed_table_can_resize_its_right_most_column():
    """With no stretch column the rule does not apply."""
    p = RecordingPainter()
    columns = [
        tables.Column("A", tables.WIDTH_FIXED, 50.0),
        tables.Column("B", tables.WIDTH_FIXED, 50.0),
    ]
    table = tables.DataTable(
        columns, [["a", "b"]], sizing=tables.SIZING_FIXED_FIT,
        cell_padding=0.0, outer_padding=0.0, keep_columns_visible=False,
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.columns[1].no_direct_resize is False
    assert table.column_border_at(100.0) == 1


def test_a_no_resize_column_has_no_grabbable_border():
    """``NoResize`` is honoured by the hit test, not only by the setter."""
    p = RecordingPainter()
    columns = [
        tables.Column("A", tables.WIDTH_STRETCH, 1.0, no_resize=True),
        tables.Column("B", tables.WIDTH_STRETCH, 1.0),
        tables.Column("C", tables.WIDTH_STRETCH, 1.0),
    ]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.column_border_at(100.0) == -1
    assert table.column_border_at(200.0) == 1


# --------------------------------------------------------------------------
# Reordering
# --------------------------------------------------------------------------
def test_dragging_a_header_past_its_neighbour_reorders_the_columns():
    """Held header plus a drag beyond the cell edge swaps display order."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.press(50.0, 5.0, 0.0, 0.0, 300.0, 120.0) == ("header", 0)
    assert table.drag(210.0, 5.0, 0.0, 0.0, 300.0, 120.0) is True
    table.release()
    assert [c.display_order for c in table.columns] == [1, 0, 2]


def test_a_header_drag_that_stays_inside_the_cell_does_not_reorder():
    """The reference only reorders once the pointer leaves the cell."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.press(50.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    assert table.drag(70.0, 5.0, 0.0, 0.0, 300.0, 120.0) is False
    assert [c.display_order for c in table.columns] == [0, 1, 2]


def test_a_no_reorder_column_cannot_be_crossed():
    """``NoReorder`` blocks the column itself *and* everything trying to pass."""
    p = RecordingPainter()
    columns = [tables.Column("A"), tables.Column("B", no_reorder=True), tables.Column("C")]
    table = tables.DataTable(columns, [["a", "b", "c"]], cell_padding=0.0, outer_padding=0.0)
    table.update_layout(p, 0.0, 300.0)
    assert table.set_column_display_order(0, 2) is False
    assert [c.display_order for c in table.columns] == [0, 1, 2]


def test_reordering_cannot_cross_the_frozen_column_barrier():
    """A frozen column stays in the frozen pane and an unfrozen one stays out."""
    p = RecordingPainter()
    table = make_table(freeze_cols=1, scroll_x=True)
    table.update_layout(p, 0.0, 300.0)
    assert table.max_display_order_allowed(0, 2) == 0
    assert table.max_display_order_allowed(2, 0) == 1


def test_reset_order_puts_the_columns_back():
    """The context menu's reset undoes every move."""
    p = RecordingPainter()
    table = make_table()
    table.update_layout(p, 0.0, 300.0)
    table.set_column_display_order(0, 2)
    table.reset_display_order()
    assert [c.display_order for c in table.columns] == [0, 1, 2]


# --------------------------------------------------------------------------
# Sorting
# --------------------------------------------------------------------------
def test_the_click_cycle_is_ascending_then_descending_and_back():
    """Without tristate the cycle has two states and never leaves the sort."""
    table = make_table(sort_tristate=False)
    assert table.click_header(0) == tables.SORT_ASCENDING
    assert table.click_header(0) == tables.SORT_DESCENDING
    assert table.click_header(0) == tables.SORT_ASCENDING


def test_the_tristate_click_cycle_reaches_every_state_and_returns():
    """With ``SortTristate`` a third click drops the column from the sort.

    The reference gets that third state from a *count* that is one higher than
    the list of available directions: indexing past the list yields
    ``ImGuiSortDirection_None``. Read as a plain toggle, this state is missing.
    """
    table = make_table(sort_tristate=True)
    column = table.columns[0]
    assert column.sort_order == -1
    assert table.click_header(0) == tables.SORT_ASCENDING
    assert column.sort_order == 0
    assert table.click_header(0) == tables.SORT_DESCENDING
    assert table.click_header(0) == tables.SORT_NONE
    assert column.sort_order == -1
    assert table.click_header(0) == tables.SORT_ASCENDING


def test_prefer_sort_descending_starts_the_cycle_the_other_way():
    """The flag changes the first click, and the cycle then mirrors."""
    columns = [tables.Column("A", prefer_sort_descending=True), tables.Column("B")]
    table = tables.DataTable(columns, [["a", "b"]], sort_tristate=True)
    assert table.click_header(0) == tables.SORT_DESCENDING
    assert table.click_header(0) == tables.SORT_ASCENDING
    assert table.click_header(0) == tables.SORT_NONE


def test_no_sort_ascending_removes_that_state_from_the_cycle():
    """A column that refuses one direction cycles through the other only."""
    columns = [tables.Column("A", no_sort_ascending=True), tables.Column("B")]
    table = tables.DataTable(columns, [["a", "b"]])
    assert table.click_header(0) == tables.SORT_DESCENDING
    assert table.click_header(0) == tables.SORT_DESCENDING


def test_a_plain_click_replaces_the_sort_and_an_appending_click_adds_to_it():
    """Multi-sort keeps a spec *list*, in click order."""
    table = make_table()
    table.click_header(0)
    assert [(s.column_index, s.sort_order) for s in table.sort_specs()] == [(0, 0)]
    table.click_header(2, append=True)
    specs = table.sort_specs()
    assert [(s.column_index, s.sort_order) for s in specs] == [(0, 0), (2, 1)]
    # A plain click on a third column throws both away.
    table.click_header(1, append=False)
    assert [(s.column_index, s.sort_order) for s in table.sort_specs()] == [(1, 0)]


def test_sort_multi_off_keeps_a_single_key_however_it_is_asked():
    """Without ``SortMulti`` an appending click is just a click."""
    table = make_table(sort_multi=False)
    table.click_header(0)
    table.click_header(2, append=True)
    specs = table.sort_specs()
    assert len(specs) == 1
    assert specs[0].column_index == 2


def test_a_multi_sort_orders_by_the_first_key_then_the_second():
    """Both keys survive and the second breaks the first one's ties."""
    rows = [
        ["b", "2"],
        ["a", "3"],
        ["b", "1"],
        ["a", "1"],
    ]
    table = tables.DataTable(["Name", "Value"], rows)
    table.click_header(0)                  # Name ascending
    table.click_header(1, append=True)     # then Value ascending
    assert len(table.sort_specs()) == 2
    table.sort_rows()
    assert table.rows == [["a", "1"], ["a", "3"], ["b", "1"], ["b", "2"]]


def test_a_multi_sort_honours_each_key_s_own_direction():
    """Name ascending, Value descending -- not one direction for both."""
    rows = [["b", "2"], ["a", "3"], ["b", "1"], ["a", "1"]]
    table = tables.DataTable(["Name", "Value"], rows)
    table.click_header(0)
    table.click_header(1, append=True)
    table.click_header(1, append=True)  # second key flips to descending
    specs = table.sort_specs()
    assert specs[0].sort_direction == tables.SORT_ASCENDING
    assert specs[1].sort_direction == tables.SORT_DESCENDING
    table.sort_rows()
    assert table.rows == [["a", "3"], ["a", "1"], ["b", "2"], ["b", "1"]]


def test_sorting_compares_numbers_as_numbers():
    """"10" sorts after "9", which a string comparison would get wrong."""
    rows = [["9"], ["10"], ["1"]]
    table = tables.DataTable(["N"], rows)
    table.click_header(0)
    table.sort_rows()
    assert table.rows == [["1"], ["9"], ["10"]]


def test_hiding_a_sorted_column_drops_it_from_the_specs():
    """``TableSortSpecsSanitize`` clears the sort order of a hidden column."""
    p = RecordingPainter()
    table = make_table()
    table.click_header(0)
    table.click_header(2, append=True)
    table.set_column_enabled(0, False)
    table.update_layout(p, 0.0, 300.0)
    specs = table.sort_specs()
    assert [s.column_index for s in specs] == [2]
    # ... and the survivor is relinearized to be the primary key.
    assert specs[0].sort_order == 0


def test_a_non_tristate_table_always_has_a_sort():
    """The reference falls back to the first sortable column."""
    p = RecordingPainter()
    table = make_table(sort_tristate=False)
    table.update_layout(p, 0.0, 300.0)
    specs = table.sort_specs()
    assert len(specs) == 1
    assert specs[0].column_index == 0
    assert specs[0].sort_direction == tables.SORT_ASCENDING


def test_a_tristate_table_may_have_no_sort_at_all():
    """That is the whole point of the flag."""
    p = RecordingPainter()
    table = make_table(sort_tristate=True)
    table.update_layout(p, 0.0, 300.0)
    assert table.sort_specs() == []


def test_default_sort_starts_the_table_sorted():
    """``DefaultSort`` seeds order 0 and the preferred direction."""
    columns = [tables.Column("A"), tables.Column("B", default_sort=True,
                                                 prefer_sort_descending=True)]
    table = tables.DataTable(columns, [["a", "b"]])
    specs = table.sort_specs()
    assert [(s.column_index, s.sort_direction) for s in specs] == [
        (1, tables.SORT_DESCENDING)
    ]


def test_a_no_sort_column_ignores_header_clicks():
    """It is not a sort key however often it is clicked."""
    columns = [tables.Column("A"), tables.Column("B", no_sort=True)]
    table = tables.DataTable(columns, [["a", "b"]], sort_tristate=True)
    assert table.click_header(1) == tables.SORT_NONE
    assert table.click_header(1) == tables.SORT_NONE
    assert table.columns[1].sort_order == -1
    # ... while its neighbour still cycles.
    assert table.click_header(0) == tables.SORT_ASCENDING


def test_a_header_press_advances_the_sort():
    """The cycle is reachable through the press path, not only the method."""
    p = RecordingPainter()
    table = make_table(sort_tristate=True)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.press(150.0, 3.0, 0.0, 0.0, 300.0, 120.0) == ("header", 1)
    assert table.columns[1].sort_direction == tables.SORT_ASCENDING
    table.release()
    assert table.press(150.0, 3.0, 0.0, 0.0, 300.0, 120.0) == ("header", 1)
    assert table.columns[1].sort_direction == tables.SORT_DESCENDING


def test_the_sort_arrow_and_rank_are_drawn_in_the_header():
    """A secondary key shows its rank beside the arrow, as the reference does.

    The glyph is read from the module rather than written out here. It was
    spelled ``▲`` once, which is not in the baked chrome atlas and so painted
    as *nothing* on the GPU painter while looking perfect under Qt; naming the
    constant means this test asserts the behaviour (an arrow, and a rank beside
    the secondary one) instead of pinning the particular character.
    ``test_chrome_atlas.py`` is what holds the character itself to the atlas.
    """
    p = RecordingPainter()
    table = make_table()
    table.click_header(0)
    table.click_header(1, append=True)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    up = tables._ARROW[tables.SORT_ASCENDING]
    assert up in p.strings
    assert f"2{up}" in p.strings


# --------------------------------------------------------------------------
# Hiding
# --------------------------------------------------------------------------
def test_hiding_a_column_reflows_the_rest_and_stops_drawing_its_cells():
    """The width it gave up goes to the survivors; its values disappear."""
    p = TracingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert "1" in p.strings

    table.set_column_enabled(1, False)
    after = TracingPainter()
    table.draw(after, 0.0, 0.0, 300.0, 120.0)
    assert [c.width_given for c in table.columns] == [150.0, 0.0, 150.0]
    assert table.enabled_columns() == [0, 2]
    assert "1" not in after.strings
    assert "a" in after.strings and "x" in after.strings


def test_showing_a_column_again_restores_its_share():
    """Visibility is a state, not a destruction."""
    p = RecordingPainter()
    table = make_table()
    table.set_column_enabled(1, False)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.set_column_enabled(1, True)
    again = RecordingPainter()
    table.draw(again, 0.0, 0.0, 300.0, 120.0)
    assert [c.width_given for c in table.columns] == [100.0, 100.0, 100.0]
    assert "1" in again.strings


def test_a_no_hide_column_cannot_be_switched_off():
    """The layout forces it back on, the way the reference does."""
    p = RecordingPainter()
    columns = [tables.Column("A", no_hide=True), tables.Column("B")]
    table = tables.DataTable(columns, [["a", "b"]], cell_padding=0.0, outer_padding=0.0)
    table.set_column_enabled(0, False)
    table.update_layout(p, 0.0, 200.0)
    assert table.columns[0].is_enabled is True
    assert table.can_hide_column(0) is False


def test_the_last_visible_column_cannot_be_hidden_from_the_menu():
    """A table with nothing showing is a state the user cannot get out of."""
    p = RecordingPainter()
    table = make_table()
    table.set_column_enabled(1, False)
    table.set_column_enabled(2, False)
    table.update_layout(p, 0.0, 300.0)
    assert table.enabled_count == 1
    assert table.can_hide_column(0) is False


def test_a_disabled_column_is_hidden_and_absent_from_the_menu():
    """``Disabled`` is the master switch, not the user's visibility state."""
    p = RecordingPainter()
    columns = [tables.Column("A"), tables.Column("B", disabled=True)]
    table = tables.DataTable(columns, [["a", "b"]], cell_padding=0.0, outer_padding=0.0)
    table.update_layout(p, 0.0, 200.0)
    assert table.columns[1].is_enabled is False
    assert [index for _, index, _, _ in table.menu_items() if index != -1] == [0]


def test_the_context_menu_toggles_visibility():
    """Pressing a menu row hides the column and leaves the menu open."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 160.0)
    table.open_context_menu(1, at=(10.0, 10.0))
    table.draw(p, 0.0, 0.0, 300.0, 160.0)
    menu_x, menu_y, _menu_w, _menu_h, line_h = table._menu_geometry
    hit_y = menu_y + 3.0 + line_h * 1.5
    assert table.press(menu_x + 20.0, hit_y, 0.0, 0.0, 300.0, 160.0) == ("visibility", 1)
    assert table.menu_open is True
    table.draw(p, 0.0, 0.0, 300.0, 160.0)
    assert table.columns[1].is_enabled is False


def test_pressing_outside_the_menu_closes_it():
    """And the press does not also land on whatever was underneath."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 160.0)
    table.open_context_menu(-1, at=(200.0, 10.0))
    table.draw(p, 0.0, 0.0, 300.0, 160.0)
    assert table.press(5.0, 150.0, 0.0, 0.0, 300.0, 160.0) is None
    assert table.menu_open is False


# --------------------------------------------------------------------------
# Frozen panes
# --------------------------------------------------------------------------
def test_a_frozen_row_stays_drawn_when_the_body_is_scrolled_to_the_bottom():
    """That is the whole contract of ``TableSetupScrollFreeze``."""
    p = RecordingPainter()
    rows = [[f"r{i}", str(i), "x"] for i in range(60)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, freeze_rows=1, cell_padding=0.0, outer_padding=0.0
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert "r0" in p.strings
    table.scroll(10_000)
    bottom = RecordingPainter()
    table.draw(bottom, 0.0, 0.0, 300.0, 120.0)
    assert "r59" in bottom.strings
    assert "r0" in bottom.strings          # frozen: still there
    assert "r1" not in bottom.strings      # scrolled away


def test_frozen_rows_are_not_part_of_the_scrolled_range():
    """Scrolling counts the rows below the frozen ones, not all of them."""
    p = RecordingPainter()
    rows = [[str(i), str(i), str(i)] for i in range(20)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, freeze_rows=2, cell_padding=0.0, outer_padding=0.0
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.bar._total == 18


def test_pressing_a_frozen_row_selects_that_row_not_a_scrolled_one():
    """The hit test has to know about the pane split too."""
    p = RecordingPainter()
    rows = [[f"r{i}", str(i), "x"] for i in range(60)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, freeze_rows=1, cell_padding=0.0, outer_padding=0.0
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.scroll(30)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    _x, _y, _w, _h, row_h, header_h, _frozen_h, _visible = table._geometry
    assert table.press(50.0, header_h + row_h * 0.5, 0.0, 0.0, 300.0, 120.0) == ("row", 0)
    below = table.press(50.0, header_h + row_h * 1.5, 0.0, 0.0, 300.0, 120.0)
    assert below == ("row", 31)


def test_a_frozen_column_does_not_move_when_the_table_is_scrolled_sideways():
    """The frozen pane keeps its x; the rest slides under it."""
    p = RecordingPainter()
    table = make_table(freeze_cols=1, scroll_x=True, keep_columns_visible=False)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    frozen_x = table.columns[0].min_x
    unfrozen_x = table.columns[1].min_x
    table.scroll_offset_x = 40.0
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.columns[0].min_x == frozen_x
    assert table.columns[1].min_x == unfrozen_x - 40.0


def test_a_scrolled_column_is_clipped_to_the_unfrozen_pane():
    """It must not draw over the frozen column it slides beneath."""
    p = TracingPainter()
    table = make_table(freeze_cols=1, scroll_x=True, keep_columns_visible=False)
    table.scroll_offset_x = 60.0
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    pane_x = table.columns[0].max_x
    assert table.columns[1].min_x < pane_x  # it really has slid under the frozen one
    scrolled = [c for c, s in p.clipped_strings if s in ("1", "2", "3", "4")]
    assert scrolled
    for clip in scrolled:
        assert clip is not None and clip[0] >= pane_x


# --------------------------------------------------------------------------
# Row backgrounds
# --------------------------------------------------------------------------
def test_row_backgrounds_alternate():
    """``RowBg``: even rows one colour, odd rows the other."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    row_fills = [f for f in p.fills if f[4] in
                 (tables.style.TABLE_ROW_BG, tables.style.TABLE_ROW_BG_ALT)]
    assert [f[4] for f in row_fills[:4]] == [
        tables.style.TABLE_ROW_BG,
        tables.style.TABLE_ROW_BG_ALT,
        tables.style.TABLE_ROW_BG,
        tables.style.TABLE_ROW_BG_ALT,
    ]


def test_row_backgrounds_can_be_turned_off():
    """No ``RowBg`` means no alternating fills at all."""
    p = RecordingPainter()
    table = make_table(row_bg=False)
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    assert not [f for f in p.fills if f[4] in
                (tables.style.TABLE_ROW_BG, tables.style.TABLE_ROW_BG_ALT)]


def test_a_row_override_wins_over_the_alternating_colour():
    """``TableSetBgColor(RowBg0)``."""
    p = RecordingPainter()
    table = make_table()
    table.set_row_bg(1, (10, 20, 30, 255))
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    assert any(f[4] == (10, 20, 30, 255) for f in p.fills)
    assert sum(1 for f in p.fills if f[4] == tables.style.TABLE_ROW_BG_ALT) == 1


def test_a_cell_override_paints_only_that_cell():
    """``TableSetBgColor(CellBg)`` draws inside the column, not across the row."""
    p = RecordingPainter()
    table = make_table()
    table.set_cell_bg(2, 1, (99, 0, 0, 255))
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    marked = [f for f in p.fills if f[4] == (99, 0, 0, 255)]
    assert len(marked) == 1
    assert marked[0][0] == table.columns[1].min_x
    assert marked[0][2] == table.columns[1].max_x - table.columns[1].min_x


def test_overrides_can_be_cleared():
    """Passing ``None`` removes one; :meth:`clear_bg_overrides` removes all."""
    p = RecordingPainter()
    table = make_table()
    table.set_row_bg(1, (10, 20, 30, 255))
    table.set_cell_bg(2, 1, (99, 0, 0, 255))
    table.set_row_bg(1, None)
    table.clear_bg_overrides()
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    assert not [f for f in p.fills if f[4] in ((10, 20, 30, 255), (99, 0, 0, 255))]


# --------------------------------------------------------------------------
# Borders
# --------------------------------------------------------------------------
def test_inner_vertical_borders_land_on_the_column_edges():
    """One thin rectangle per inner column edge, at ``max_x``."""
    p = RecordingPainter()
    table = make_table(borders_outer_v=False, borders_inner_h=False, borders_outer_h=False)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    verticals = [f for f in p.fills if f[2] == tables.BORDER_SIZE]
    assert sorted(f[0] for f in verticals) == [100.0, 200.0]


def test_outer_vertical_borders_frame_the_table():
    """Left edge and right edge, both strong."""
    p = RecordingPainter()
    table = make_table(borders_inner_v=False, borders_inner_h=False, borders_outer_h=False)
    table.draw(p, 10.0, 0.0, 300.0, 120.0)
    verticals = [f for f in p.fills if f[2] == tables.BORDER_SIZE]
    assert sorted(f[0] for f in verticals) == [10.0, 10.0 + 300.0 - tables.BORDER_SIZE]
    assert all(f[4] == tables.style.TABLE_BORDER_STRONG for f in verticals)


def test_the_border_under_the_header_is_strong_and_the_ones_between_rows_light():
    """The reference marks the header seam with the strong colour."""
    p = RecordingPainter()
    table = make_table(borders_inner_v=False, borders_outer_v=False, borders_outer_h=False)
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    horizontals = [f for f in p.fills if f[3] == tables.BORDER_SIZE]
    _x, _y, _w, _h, _row_h, header_h, _frozen_h, _visible = table._geometry
    under_header = [f for f in horizontals if f[1] == header_h]
    assert under_header and under_header[0][4] == tables.style.TABLE_BORDER_STRONG
    assert any(f[4] == tables.style.TABLE_BORDER_LIGHT for f in horizontals)


def test_the_frozen_row_seam_is_strong():
    """A pane boundary is not the same thing as a row boundary."""
    p = RecordingPainter()
    rows = [[str(i), str(i), str(i)] for i in range(20)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, freeze_rows=2, borders_inner_v=False,
        borders_outer_v=False, borders_outer_h=False,
        cell_padding=0.0, outer_padding=0.0,
    )
    table.draw(p, 0.0, 0.0, 300.0, 200.0)
    _x, _y, _w, _h, row_h, header_h, frozen_h, _visible = table._geometry
    seam = [f for f in p.fills if f[3] == tables.BORDER_SIZE and f[1] == header_h + frozen_h]
    assert seam and seam[0][4] == tables.style.TABLE_BORDER_STRONG


def test_the_frozen_column_seam_is_strong():
    """Same rule, sideways."""
    p = RecordingPainter()
    table = make_table(freeze_cols=1, scroll_x=True, borders_outer_v=False,
                       borders_inner_h=False, borders_outer_h=False)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    verticals = [f for f in p.fills if f[2] == tables.BORDER_SIZE]
    seam = [f for f in verticals if f[0] == table.columns[0].max_x]
    assert seam and seam[0][4] == tables.style.TABLE_BORDER_STRONG


def test_borders_can_all_be_turned_off():
    """No border flags, no thin rectangles."""
    p = RecordingPainter()
    table = make_table(borders_inner_v=False, borders_outer_v=False,
                       borders_inner_h=False, borders_outer_h=False)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert not [f for f in p.fills if tables.BORDER_SIZE in (f[2], f[3])]


# --------------------------------------------------------------------------
# Clipping
# --------------------------------------------------------------------------
def test_a_long_cell_value_is_clipped_to_its_own_column():
    """The value is drawn whole and the clip stops it, exactly as pushed."""
    p = TracingPainter()
    rows = [["a value far too long to fit in a hundred pixels", "1", "x"]]
    table = tables.DataTable(
        ["A", "B", "C"], rows, cell_padding=0.0, outer_padding=0.0, sortable=False
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    clip = next(c for c, s in p.clipped_strings if s.startswith("a value far"))
    assert clip == (0.0, pytest.approx(table._geometry[5]), 100.0, pytest.approx(
        table._geometry[4]))
    # Its neighbour's cell begins where the clip ends.
    assert table.columns[1].min_x == clip[0] + clip[2]


def test_every_cell_is_clipped_to_its_column():
    """Not just the long one: the clip is the mechanism, not a special case."""
    p = TracingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    for clip, string in p.clipped_strings:
        if string in ("a", "b", "c", "d"):
            assert clip[0] == 0.0 and clip[2] == 100.0
        if string in ("1", "2", "3", "4"):
            assert clip[0] == 100.0 and clip[2] == 100.0


def test_header_labels_are_clipped_too():
    """A header wider than its column does not run into the next one."""
    p = TracingPainter()
    columns = [tables.Column("An extremely long header label"), tables.Column("B")]
    table = tables.DataTable(columns, [["a", "b"]], cell_padding=0.0, outer_padding=0.0)
    table.draw(p, 0.0, 0.0, 200.0, 120.0)
    header_clips = [c for c, s in p.clipped_strings if s.startswith("An extr")]
    assert header_clips
    assert header_clips[0][2] == 100.0


# --------------------------------------------------------------------------
# Scrolling and hit-testing
# --------------------------------------------------------------------------
def test_the_scrollbar_is_reused_not_reimplemented():
    """It is :class:`~cmtk.widgets.basic.ScrollBar`, the shared one."""
    from cmtk.widgets import basic as widgets

    assert isinstance(make_table().bar, widgets.ScrollBar)


def test_the_scrollbar_takes_its_width_out_of_the_columns():
    """Otherwise the right-most column draws underneath it."""
    p = RecordingPainter()
    rows = [[str(i), str(i), str(i)] for i in range(100)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, cell_padding=0.0, outer_padding=0.0
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.bar.needed()
    assert sum(c.width_given for c in table.columns) == 300.0 - table.bar.width


def test_pressing_a_row_selects_it_by_its_absolute_index():
    """Not by its position in the visible window."""
    p = RecordingPainter()
    rows = [[str(i), str(i), str(i)] for i in range(60)]
    table = tables.DataTable(
        ["A", "B", "C"], rows, cell_padding=0.0, outer_padding=0.0
    )
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.scroll(20)
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    _x, _y, _w, _h, row_h, header_h, _frozen_h, _visible = table._geometry
    assert table.press(50.0, header_h + row_h * 0.5, 0.0, 0.0, 300.0, 120.0) == ("row", 20)
    assert table.selected_row == 20


def test_a_press_outside_the_box_is_ignored():
    """Every control here starts with that test."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    assert table.press(400.0, 400.0, 0.0, 0.0, 300.0, 120.0) is None


def test_release_lets_go_of_everything():
    """A drag that outlives its release is the bug this prevents."""
    p = RecordingPainter()
    table = make_table()
    table.draw(p, 0.0, 0.0, 300.0, 120.0)
    table.press(100.0, 5.0, 0.0, 0.0, 300.0, 120.0)
    table.release()
    assert table.drag(200.0, 5.0, 0.0, 0.0, 300.0, 120.0) is False
