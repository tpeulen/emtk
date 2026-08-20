"""A real data table: sized, resized, reordered, multi-sorted, frozen, clipped.

Why this is not :class:`~cmtk.widgets.basic.Table`
----------------------------------------------------------
:class:`~cmtk.widgets.basic.Table` is a grid: it splits its width by a
list of ratios, sorts by one column, and scrolls. That is the right control for
a fixed report, and it stays.

What it cannot express is the thing a *column* is: something with a **sizing
policy**. A width ratio says "this column gets a fifth of whatever there is",
which is wrong for a column holding a checkbox and wrong again for one holding a
path. The reference implementation's answer is two policies per column --
``WidthFixed`` keeps a pixel width, ``WidthStretch`` takes a share of what is
*left over* after the fixed ones are paid -- plus a table-level default that
decides which one an unannotated column gets and how the stretch weights are
seeded. Everything else here follows from that: a border drag has to know which
neighbour absorbs the change, and the answer differs for fixed and stretch; a
hidden column has to give its width back to the others; a frozen pane has to be
laid out in the same arithmetic as the pane that scrolls.

So this module ports what ``TableUpdateLayout`` *computes*, not the
``BeginTable``/``EndTable`` call pattern it computes it in. There is no context,
no per-frame temp data and no call-order contract: a :class:`DataTable` is an
object that holds its columns, and :meth:`DataTable.draw` recomputes the layout
from the width it is handed, the way every other control here recomputes its
geometry from the box it is drawn into.

The sizing arithmetic, quoted
-----------------------------
The reference resolves stretch weights against the width that is *left*::

    width_avail_for_stretched_columns = width_avail - width_spacings - sum_width_requests
    weight_ratio  = column->StretchWeight / stretch_sum_weights
    WidthRequest  = TRUNC(MAX(width_avail_for_stretched * weight_ratio, MinColumnWidth) + 0.01)

then hands out the truncation remainder one pixel at a time, right to left, so
the columns exactly fill the row. ``SizingStretchProp`` seeds the weights from
measured content (``StretchWeight = WidthAuto / stretch_sum_width_auto *
count_stretch``); ``SizingStretchSame`` seeds them all to ``1.0``;
``SizingFixedSame`` widens every fixed column to the widest one's ideal width.

A fixed column that does not fit is not clipped away -- it is *shrunk*, by
``TableCalcMaxColumnWidth``, so that every column still to its right keeps at
least ``MinColumnWidth`` of room::

    trailing  = ColumnsEnabledCount - column->IndexWithinEnabledSet - 1
    width_max = WorkRect.Max.x - trailing * min_column_distance - column->MinX - padding

What was left out
-----------------
The reference's per-frame ``ImGuiTableTempData`` pooling and its draw-channel
splitter are answers to problems this painter does not have -- there is one
draw list, and clipping is a scissor push, not a channel merge. The ``.ini``
settings persistence has no counterpart either: a :class:`DataTable` *is* the
retained state, so there is nothing to serialise it into and back out of.
Angled headers would need rotated glyphs, which the painter has no operation
for.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .. import style
from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Colour, Painter
from .basic import ScrollBar

__all__ = [
    "SIZING_FIXED_FIT",
    "SIZING_FIXED_SAME",
    "SIZING_STRETCH_PROP",
    "SIZING_STRETCH_SAME",
    "WIDTH_FIXED",
    "WIDTH_STRETCH",
    "SORT_NONE",
    "SORT_ASCENDING",
    "SORT_DESCENDING",
    "BORDER_SIZE",
    "RESIZE_HALF_THICKNESS",
    "SortSpec",
    "Column",
    "DataTable",
]

# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------
#: Table-level sizing defaults. ``ImGuiTableFlags_Sizing*``.
SIZING_FIXED_FIT = "fixed_fit"
SIZING_FIXED_SAME = "fixed_same"
SIZING_STRETCH_PROP = "stretch_prop"
SIZING_STRETCH_SAME = "stretch_same"

#: Per-column sizing policies. ``ImGuiTableColumnFlags_Width*``.
WIDTH_FIXED = "fixed"
WIDTH_STRETCH = "stretch"

#: ``ImGuiSortDirection_``. The numbers matter: the reference's click cycle
#: indexes an "available directions" list whose unused slots read as zero, and
#: zero is *None*, which is what makes the tristate cycle come back round.
SORT_NONE = 0
SORT_ASCENDING = 1
SORT_DESCENDING = 2

#: ``TABLE_BORDER_SIZE`` -- borders are one pixel, drawn as thin rectangles.
BORDER_SIZE = 1.0

#: ``TABLE_RESIZE_SEPARATOR_HALF_THICKNESS`` -- how far either side of a column
#: border a press still counts as grabbing it.
RESIZE_HALF_THICKNESS = 4.0

#: The arrow drawn in a sorted column's header.
_ARROW = {SORT_ASCENDING: "▴", SORT_DESCENDING: "▾"}


def _trunc(value: float) -> float:
    """``IM_TRUNC``: drop the fractional part, toward zero.

    Parameters
    ----------
    value : float
        The number.

    Returns
    -------
    float
        The truncated value, still a float.
    """
    return float(math.trunc(value))


def _cell_key(value: Any) -> tuple[int, Any]:
    """A sort key that puts numbers before text and compares each sensibly.

    Parameters
    ----------
    value : Any
        A cell's contents.

    Returns
    -------
    tuple
        ``(0, number)`` for anything that parses as a number, ``(1, text)``
        otherwise -- so a column of mixed contents still has a total order
        rather than raising halfway through the sort.
    """
    if isinstance(value, bool):
        return (0, float(value))
    if isinstance(value, (int, float)):
        return (0, float(value))
    try:
        return (0, float(str(value)))
    except (TypeError, ValueError):
        return (1, str(value).lower())


class SortSpec:
    """One entry of a table's sort specification.

    Parameters
    ----------
    column_index : int
        Which column, by its *index*, not its display order.
    sort_order : int
        Its rank in the sort: 0 is the primary key.
    sort_direction : int
        :data:`SORT_ASCENDING` or :data:`SORT_DESCENDING`.
    """

    __slots__ = ("column_index", "sort_order", "sort_direction")

    def __init__(self, column_index: int, sort_order: int, sort_direction: int) -> None:
        self.column_index = int(column_index)
        self.sort_order = int(sort_order)
        self.sort_direction = int(sort_direction)

    def __repr__(self) -> str:
        """A short debug rendering."""
        arrow = "asc" if self.sort_direction == SORT_ASCENDING else "desc"
        return f"SortSpec(col={self.column_index}, order={self.sort_order}, {arrow})"

    def __eq__(self, other: object) -> bool:
        """Equality by all three fields, so specs compare in tests."""
        if not isinstance(other, SortSpec):
            return NotImplemented
        return (
            self.column_index == other.column_index
            and self.sort_order == other.sort_order
            and self.sort_direction == other.sort_direction
        )

    def __hash__(self) -> int:
        """Hash matching :meth:`__eq__`."""
        return hash((self.column_index, self.sort_order, self.sort_direction))


class Column:
    """A column: what it is called, how it is sized, and what it is doing now.

    A column carries three quite different kinds of state and it is worth
    keeping them apart when reading the code:

    * what the *caller* declared -- the name, the policy, the initial width or
      weight, and the "no" flags;
    * what the *layout* computed -- :attr:`width_auto`, :attr:`width_request`,
      :attr:`width_given` and the positions, all rewritten on every
      :meth:`DataTable.update_layout`;
    * what the *user* did -- visibility, display order, and the sort direction
      and rank.

    Parameters
    ----------
    name : str
        The header label.
    width : str, optional
        :data:`WIDTH_FIXED` or :data:`WIDTH_STRETCH`. Left out, the table's
        sizing default decides, which is the reference's behaviour and the
        reason a table has a sizing default at all.
    init_width_or_weight : float, optional
        Read as a pixel width for a fixed column and as a weight for a stretch
        one. Not positive means "no preference"; the reference stores the two
        in one field for exactly this reason.
    no_resize : bool, optional
        The border on this column's right cannot be dragged.
    no_reorder : bool, optional
        This column cannot be dragged, *and* no other column may cross it.
    no_hide : bool, optional
        Cannot be switched off from the context menu.
    no_sort : bool, optional
        Clicking the header does nothing.
    no_sort_ascending, no_sort_descending : bool, optional
        Drop one direction from the click cycle. Both means no sorting.
    prefer_sort_descending : bool, optional
        First click sorts descending rather than ascending.
    default_hide : bool, optional
        Starts hidden.
    default_sort : bool, optional
        Starts as a sort key.
    disabled : bool, optional
        Hidden *and* absent from the context menu -- the master switch, which
        is not the same as the user having hidden it.
    no_header_width : bool, optional
        The header label does not widen the column when it auto-fits.
    """

    def __init__(
        self,
        name: str,
        width: str | None = None,
        init_width_or_weight: float = -1.0,
        *,
        no_resize: bool = False,
        no_reorder: bool = False,
        no_hide: bool = False,
        no_sort: bool = False,
        no_sort_ascending: bool = False,
        no_sort_descending: bool = False,
        prefer_sort_descending: bool = False,
        default_hide: bool = False,
        default_sort: bool = False,
        disabled: bool = False,
        no_header_width: bool = False,
    ) -> None:
        self.name = str(name)
        self.width_policy = width
        self.init_width_or_weight = float(init_width_or_weight)
        self.no_resize = bool(no_resize)
        self.no_reorder = bool(no_reorder)
        self.no_hide = bool(no_hide)
        self.no_sort = bool(no_sort)
        self.no_sort_ascending = bool(no_sort_ascending)
        self.no_sort_descending = bool(no_sort_descending)
        self.prefer_sort_descending = bool(prefer_sort_descending)
        self.default_hide = bool(default_hide)
        self.default_sort = bool(default_sort)
        self.disabled = bool(disabled)
        self.no_header_width = bool(no_header_width)

        # Resolved every layout from the table's flags.
        self.policy: str = width or WIDTH_STRETCH
        self.no_resize_effective = self.no_resize
        self.no_sort_effective = self.no_sort or (no_sort_ascending and no_sort_descending)
        #: ``NoDirectResize_``: set by the layout on the right-most column when
        #: any stretch column exists -- dragging there has nothing to give to.
        self.no_direct_resize = False

        # Sizing state.
        self.width_auto = -1.0
        self.width_request = init_width_or_weight if (width == WIDTH_FIXED and
                                                      init_width_or_weight > 0.0) else -1.0
        self.stretch_weight = init_width_or_weight if (width == WIDTH_STRETCH and
                                                       init_width_or_weight > 0.0) else -1.0
        self.width_given = 0.0
        self.width_max = float("inf")
        #: The reference fits a fresh column for three frames; retained, once is
        #: enough -- what matters is that an explicit width is *not* overwritten.
        self.auto_fit = init_width_or_weight <= 0.0

        # Placement, rewritten every layout.
        self.min_x = 0.0
        self.max_x = 0.0
        self.work_min_x = 0.0
        self.work_max_x = 0.0

        # User state.
        self.display_order = 0
        self.index_within_enabled_set = -1
        self.prev_enabled = -1
        self.next_enabled = -1
        self.user_enabled = not self.default_hide
        self.user_enabled_next = self.user_enabled
        self.is_enabled = self.user_enabled and not self.disabled
        self.sort_order = 0 if default_sort else -1
        self.sort_direction = (
            (SORT_DESCENDING if prefer_sort_descending else SORT_ASCENDING)
            if default_sort
            else SORT_NONE
        )
        #: The reference packs this into two bits per entry; a list of three is
        #: the same thing, and the padding entries must be :data:`SORT_NONE`
        #: because that is what the packed zero bits decode to.
        self.sort_directions: list[int] = [SORT_NONE, SORT_NONE, SORT_NONE]
        self.sort_directions_count = 0

    # ------------------------------------------------------------------ #
    def is_stretch(self) -> bool:
        """Whether the resolved policy is :data:`WIDTH_STRETCH`."""
        return self.policy == WIDTH_STRETCH

    def is_fixed(self) -> bool:
        """Whether the resolved policy is :data:`WIDTH_FIXED`."""
        return self.policy == WIDTH_FIXED

    def avail_sort_direction(self, n: int) -> int:
        """The *n*-th direction in this column's cycle.

        Parameters
        ----------
        n : int
            Position in the cycle, 0-2.

        Returns
        -------
        int
            One of :data:`SORT_NONE`, :data:`SORT_ASCENDING`,
            :data:`SORT_DESCENDING`. Past the declared entries this reads
            :data:`SORT_NONE`, which is the tristate cycle's third state and
            not an accident.
        """
        return self.sort_directions[n] if 0 <= n < 3 else SORT_NONE

    def next_sort_direction(self) -> int:
        """What one more click on this header would set.

        Returns
        -------
        int
            ``TableGetColumnNextSortDirection``: the first available direction
            if the column is not currently a sort key, otherwise the one after
            the current direction, wrapping at the *count* -- which is one more
            than the declared directions when the table is tristate, and that
            extra slot is how the cycle gets back to "not sorted".
        """
        if self.sort_directions_count <= 0:
            return SORT_NONE
        if self.sort_order == -1:
            return self.avail_sort_direction(0)
        for n in range(3):
            if self.sort_direction == self.avail_sort_direction(n):
                return self.avail_sort_direction((n + 1) % self.sort_directions_count)
        return SORT_NONE

    def fix_sort_direction(self) -> bool:
        """Move off a direction this column no longer offers.

        Returns
        -------
        bool
            Whether anything changed -- the caller marks the sort specs dirty
            when it did.
        """
        if self.sort_order == -1:
            return False
        if self.sort_direction in self.sort_directions[: max(self.sort_directions_count, 0)]:
            return False
        if self.sort_direction == SORT_NONE and self.sort_directions_count >= 3:
            return False
        self.sort_direction = self.avail_sort_direction(0)
        return True

    def __repr__(self) -> str:
        """A short debug rendering."""
        return (
            f"Column({self.name!r}, {self.policy}, given={self.width_given:.1f}, "
            f"enabled={self.is_enabled})"
        )


class DataTable:
    r"""A table of rows and :class:`Column`\\ s that sizes itself like the reference.

    Parameters
    ----------
    columns : sequence
        :class:`Column` objects, or plain strings for columns that want nothing
        but a name.
    rows : sequence of sequence, optional
        The data, addressed as ``rows[row][column_index]`` -- by column *index*,
        never by display order, so reordering the columns does not touch it.
    sizing : str, optional
        The table-level default: :data:`SIZING_STRETCH_SAME` (every column an
        equal share), :data:`SIZING_STRETCH_PROP` (shares proportional to
        measured content), :data:`SIZING_FIXED_FIT` (every column its own ideal
        width) or :data:`SIZING_FIXED_SAME` (every column the widest ideal
        width).
    resizable, reorderable, hideable, sortable : bool, optional
        The four interactions.
    sort_multi : bool, optional
        ``SortMulti``: an appending click adds a secondary key instead of
        replacing the primary one.
    sort_tristate : bool, optional
        ``SortTristate``: the click cycle passes through "not sorted", and the
        table is allowed to have no sort at all.
    row_bg : bool, optional
        Alternating row backgrounds.
    borders_inner_v, borders_outer_v, borders_inner_h, borders_outer_h : bool, optional
        The four border sets.
    freeze_rows, freeze_cols : int, optional
        ``TableSetupScrollFreeze``: how many leading rows/columns stay put when
        the rest scrolls.
    scroll_x : bool, optional
        Let the columns be wider than the table and scroll horizontally. Off,
        the layout shrinks them to fit instead.
    keep_columns_visible : bool, optional
        The shrink-to-fit above. ``NoKeepColumnsVisible`` inverted.
    precise_widths : bool, optional
        Skip the right-to-left remainder handout, leaving the columns a pixel
        or two short of the full width.
    cell_padding : float, optional
        Padding inside a cell, per side.
    outer_padding : float, optional
        Padding outside the first and last columns.
    min_column_width : float, optional
        No column, however dragged, goes below this.
    row_scale : float, optional
        Row height as a multiple of the line height.
    show_headers : bool, optional
        Whether to draw (and hit-test) the header row.
    selected_row : int, optional
        The highlighted row.
    """

    def __init__(
        self,
        columns: Sequence[str | Column],
        rows: Sequence[Sequence[Any]] = (),
        *,
        sizing: str = SIZING_STRETCH_SAME,
        resizable: bool = True,
        reorderable: bool = True,
        hideable: bool = True,
        sortable: bool = True,
        sort_multi: bool = True,
        sort_tristate: bool = False,
        row_bg: bool = True,
        borders_inner_v: bool = True,
        borders_outer_v: bool = True,
        borders_inner_h: bool = True,
        borders_outer_h: bool = True,
        freeze_rows: int = 0,
        freeze_cols: int = 0,
        scroll_x: bool = False,
        keep_columns_visible: bool = True,
        precise_widths: bool = False,
        cell_padding: float = 4.0,
        outer_padding: float = 0.0,
        min_column_width: float = 4.0,
        row_scale: float = 1.15,
        show_headers: bool = True,
        selected_row: int | None = None,
    ) -> None:
        self.columns: list[Column] = [
            c if isinstance(c, Column) else Column(str(c)) for c in columns
        ]
        self.rows: list[list[Any]] = [list(r) for r in rows]
        self.sizing = sizing
        self.resizable = bool(resizable)
        self.reorderable = bool(reorderable)
        self.hideable = bool(hideable)
        self.sortable = bool(sortable)
        self.sort_multi = bool(sort_multi)
        self.sort_tristate = bool(sort_tristate)
        self.row_bg = bool(row_bg)
        self.borders_inner_v = bool(borders_inner_v)
        self.borders_outer_v = bool(borders_outer_v)
        self.borders_inner_h = bool(borders_inner_h)
        self.borders_outer_h = bool(borders_outer_h)
        self.freeze_rows = int(freeze_rows)
        self.freeze_cols = int(freeze_cols)
        self.scroll_x = bool(scroll_x)
        self.keep_columns_visible = bool(keep_columns_visible)
        self.precise_widths = bool(precise_widths)
        self.cell_padding = float(cell_padding)
        self.outer_padding = float(outer_padding)
        self.min_column_width = float(min_column_width)
        self.row_scale = float(row_scale)
        self.show_headers = bool(show_headers)
        self.selected_row = selected_row

        #: Set this from the host's shift key before calling :meth:`press`: it
        #: is what turns a header click into an *appending* one. The reference
        #: reads ``g.IO.KeyShift`` at the same point.
        self.append_sort = False
        #: Horizontal scroll offset, in pixels. Only the unfrozen pane moves.
        self.scroll_offset_x = 0.0
        #: How many rows :meth:`update_layout` measures for auto-fit. Measuring
        #: a million-row table every frame would cost more than drawing it.
        self.auto_fit_sample_rows = 200

        self.bar = ScrollBar()
        self.enabled_count = 0
        self.left_most_enabled = -1
        self.right_most_enabled = -1
        self.left_most_stretched = -1
        self.right_most_stretched = -1

        self.menu_open = False
        self.menu_column = -1
        self._menu_at: tuple[float, float] | None = None

        self._order_to_index: list[int] = list(range(len(self.columns)))
        for index, column in enumerate(self.columns):
            column.display_order = index
        self._sort_dirty = True
        self._row_bg: dict[int, Colour] = {}
        self._cell_bg: dict[tuple[int, int], Colour] = {}
        self._geometry: tuple[float, ...] | None = None
        self._menu_geometry: tuple[float, float, float, float, float] | None = None
        self._resizing = -1
        self._resize_grab = 0.0
        self._held_header = -1
        self._drag_from_x = 0.0

        for index, column in enumerate(self.columns):
            self._setup_column_flags(column, index)

    # ------------------------------------------------------------------ #
    # Column flags
    # ------------------------------------------------------------------ #
    def _setup_column_flags(self, column: Column, index: int) -> None:
        """Resolve a column's policy and sort cycle against the table's flags.

        ``TableSetupColumnFlags``. Run on every layout, because a table flag can
        change between frames and the reference re-derives rather than caching.

        Parameters
        ----------
        column : Column
            The column.
        index : int
            Its index, used only for the fixed-width implication below.
        """
        if column.width_policy is not None:
            column.policy = column.width_policy
        elif column.init_width_or_weight > 0.0 and self.sizing in (
            SIZING_FIXED_FIT,
            SIZING_FIXED_SAME,
        ):
            # "When passing a width automatically enforce WidthFixed policy".
            column.policy = WIDTH_FIXED
        elif self.sizing in (SIZING_FIXED_FIT, SIZING_FIXED_SAME):
            column.policy = WIDTH_FIXED
        else:
            column.policy = WIDTH_STRETCH

        column.no_resize_effective = column.no_resize or not self.resizable
        column.no_sort_effective = (
            column.no_sort
            or not self.sortable
            or (column.no_sort_ascending and column.no_sort_descending)
        )

        directions: list[int] = []
        if not column.no_sort_effective:
            if column.prefer_sort_descending and not column.no_sort_descending:
                directions.append(SORT_DESCENDING)
            if not column.prefer_sort_descending and not column.no_sort_ascending:
                directions.append(SORT_ASCENDING)
            if column.prefer_sort_descending and not column.no_sort_ascending:
                directions.append(SORT_ASCENDING)
            if not column.prefer_sort_descending and not column.no_sort_descending:
                directions.append(SORT_DESCENDING)
        count = len(directions)
        column.sort_directions = (directions + [SORT_NONE, SORT_NONE, SORT_NONE])[:3]
        # The tristate slot is counted but never listed: reading past the listed
        # entries yields SORT_NONE, which is precisely the extra state.
        if self.sortable and (self.sort_tristate or count == 0):
            count += 1
        column.sort_directions_count = count
        if column.fix_sort_direction():
            self._sort_dirty = True

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def column_width_auto(self, p: Painter, index: int) -> float:
        """The width this column would need for nothing to be clipped.

        ``TableGetColumnWidthAuto``: the widest cell, or the header label if
        that is wider and the column did not opt out of counting it.

        Parameters
        ----------
        p : Painter
            Used to measure.
        index : int
            Column index.

        Returns
        -------
        float
            The ideal content width, never below the table's minimum.
        """
        column = self.columns[index]
        widest = 0.0
        for row in self.rows[: self.auto_fit_sample_rows]:
            if index < len(row):
                widest = max(widest, p.text_width(str(row[index])))
        if not column.no_header_width and self.show_headers:
            head = p.text_width(column.name)
            if column.sort_order != -1 or (self.sortable and not column.no_sort_effective):
                head += p.text_width(" ▴")
            widest = max(widest, head)
        if (
            column.is_fixed()
            and column.init_width_or_weight > 0.0
            and column.no_resize_effective
        ):
            widest = column.init_width_or_weight
        return max(widest, self.min_column_width)

    def update_layout(self, p: Painter, x: float, w: float) -> None:
        """Resolve every column's width and position for a table ``w`` wide.

        This is ``TableUpdateLayout``, in its six parts, minus the parts that
        exist to serve a call-order contract this port does not have.

        Parameters
        ----------
        p : Painter
            Used to measure content for auto-fitting columns.
        x : float
            Left edge of the table.
        w : float
            Width available to the columns -- the caller has already taken the
            vertical scrollbar out of it.
        """
        columns = self.columns
        count = len(columns)
        self._sync_display_order()

        # [Part 1] Lock enabled state, measure ideal widths, count the policies.
        self.enabled_count = 0
        self.left_most_enabled = -1
        count_fixed = 0
        count_stretch = 0
        stretch_sum_width_auto = 0.0
        fixed_max_width_auto = 0.0
        prev_index = -1
        for order_n in range(count):
            index = self._order_to_index[order_n]
            column = columns[index]
            self._setup_column_flags(column, index)

            if not self.hideable or column.no_hide:
                column.user_enabled_next = True
            column.user_enabled = column.user_enabled_next
            column.is_enabled = column.user_enabled and not column.disabled

            if column.sort_order != -1 and not column.is_enabled:
                self._sort_dirty = True
            if column.sort_order > 0 and not self.sort_multi:
                self._sort_dirty = True

            if not column.is_enabled:
                column.index_within_enabled_set = -1
                column.prev_enabled = -1
                column.next_enabled = -1
                column.width_given = 0.0
                continue

            column.prev_enabled = prev_index
            column.next_enabled = -1
            if prev_index != -1:
                columns[prev_index].next_enabled = index
            else:
                self.left_most_enabled = index
            column.index_within_enabled_set = self.enabled_count
            self.enabled_count += 1
            prev_index = index

            column.width_auto = self.column_width_auto(p, index)
            if column.is_stretch():
                stretch_sum_width_auto += column.width_auto
                count_stretch += 1
            else:
                fixed_max_width_auto = max(fixed_max_width_auto, column.width_auto)
                count_fixed += 1
        self.right_most_enabled = prev_index
        if self.sortable and not self.sort_tristate and not self.sort_specs_count():
            self._sort_dirty = True

        # [Part 3] Latch fixed widths, seed stretch weights.
        sum_width_requests = 0.0
        stretch_sum_weights = 0.0
        self.left_most_stretched = -1
        self.right_most_stretched = -1
        for index, column in enumerate(columns):
            if not column.is_enabled:
                continue
            if column.is_fixed():
                width_auto = column.width_auto
                if self.sizing == SIZING_FIXED_SAME and (
                    column.auto_fit or column.no_resize_effective
                ):
                    width_auto = fixed_max_width_auto
                if column.auto_fit or column.no_resize_effective:
                    column.width_request = width_auto
                sum_width_requests += column.width_request
            else:
                if column.auto_fit or column.stretch_weight < 0.0 or column.no_resize_effective:
                    if column.init_width_or_weight > 0.0:
                        column.stretch_weight = column.init_width_or_weight
                    elif self.sizing == SIZING_STRETCH_PROP and stretch_sum_width_auto > 0.0:
                        column.stretch_weight = (
                            column.width_auto / stretch_sum_width_auto
                        ) * count_stretch
                    else:
                        column.stretch_weight = 1.0
                stretch_sum_weights += column.stretch_weight
                order = column.display_order
                if (
                    self.left_most_stretched == -1
                    or columns[self.left_most_stretched].display_order > order
                ):
                    self.left_most_stretched = index
                if (
                    self.right_most_stretched == -1
                    or columns[self.right_most_stretched].display_order < order
                ):
                    self.right_most_stretched = index
            sum_width_requests += self.cell_padding * 2.0

        # [Part 4] Hand the leftover width to the stretch columns by weight.
        width_spacings = self.outer_padding * 2.0
        width_avail = max(1.0, w)
        width_avail_for_stretched = width_avail - width_spacings - sum_width_requests
        width_remaining = width_avail_for_stretched
        for column in columns:
            if not column.is_enabled:
                continue
            if column.is_stretch() and stretch_sum_weights > 0.0:
                weight_ratio = column.stretch_weight / stretch_sum_weights
                column.width_request = _trunc(
                    max(width_avail_for_stretched * weight_ratio, self.min_column_width) + 0.01
                )
                width_remaining -= column.width_request
            # [Resize Rule 1] the right-most column has nothing to hand width to.
            column.no_direct_resize = (
                column.next_enabled == -1 and self.left_most_stretched != -1
            )
            column.width_given = _trunc(max(column.width_request, self.min_column_width))

        # [Part 5] Give the truncation remainder back, one pixel at a time,
        # right to left, so the row is exactly filled.
        if width_remaining >= 1.0 and not self.precise_widths and stretch_sum_weights > 0.0:
            for order_n in range(count - 1, -1, -1):
                if width_remaining < 1.0:
                    break
                column = columns[self._order_to_index[order_n]]
                if not column.is_enabled or not column.is_stretch():
                    continue
                column.width_request += 1.0
                column.width_given += 1.0
                width_remaining -= 1.0

        # [Part 6] Place the columns, shrinking any that would push a neighbour
        # off the right-hand edge.
        offset_x = x + self.outer_padding
        right_edge = x + w - self.outer_padding
        min_column_distance = self.min_column_width + self.cell_padding * 2.0
        for order_n in range(count):
            index = self._order_to_index[order_n]
            column = columns[index]
            if order_n == self.freeze_cols:
                offset_x -= self.scroll_offset_x
            if not column.is_enabled:
                column.min_x = column.max_x = offset_x
                column.work_min_x = column.work_max_x = offset_x
                column.width_given = 0.0
                continue
            column.min_x = offset_x
            column.width_max = self._calc_max_column_width(column, right_edge,
                                                           min_column_distance)
            column.width_given = min(column.width_given, column.width_max)
            column.width_given = max(
                column.width_given, min(column.width_request, self.min_column_width)
            )
            column.max_x = offset_x + column.width_given + self.cell_padding * 2.0
            column.work_min_x = column.min_x + self.cell_padding
            column.work_max_x = column.max_x - self.cell_padding
            column.auto_fit = False
            offset_x = column.max_x

    def _calc_max_column_width(
        self, column: Column, right_edge: float, min_column_distance: float
    ) -> float:
        """How wide this column may be without pushing its neighbours off-screen.

        ``TableCalcMaxColumnWidth``. This is what happens to a fixed column that
        does not fit: it is not clipped away, it is shrunk, and every column
        still to its right is reserved ``min_column_distance``.

        Parameters
        ----------
        column : Column
            The column.
        right_edge : float
            Where the columns must end.
        min_column_distance : float
            Minimum width plus this table's cell padding.

        Returns
        -------
        float
            The cap, or infinity when nothing constrains it.
        """
        if self.scroll_x:
            if column.display_order < self.freeze_cols:
                room = right_edge - (self.freeze_cols - column.display_order) * min_column_distance
                return room - column.min_x - self.outer_padding - self.cell_padding
            return float("inf")
        if not self.keep_columns_visible:
            return float("inf")
        trailing = self.enabled_count - column.index_within_enabled_set - 1
        room = right_edge - trailing * min_column_distance - column.min_x
        return room - self.cell_padding * 2.0

    def _sync_display_order(self) -> None:
        """Rebuild the display-order table from the columns' own ``display_order``."""
        count = len(self.columns)
        order = sorted(range(count), key=lambda i: self.columns[i].display_order)
        self._order_to_index = order
        for position, index in enumerate(order):
            self.columns[index].display_order = position

    # ------------------------------------------------------------------ #
    # Sizing by hand
    # ------------------------------------------------------------------ #
    def set_column_width(self, index: int, width: float) -> bool:
        """Resize a column, moving the width the reference says should move.

        ``TableSetColumnWidth``. Which neighbour pays for the change is the
        whole subtlety, and it is decided by policy rather than by position:

        * a **fixed** column that has no stretch column to its left simply
          takes the new width, and everything after it slides along -- no
          neighbour is touched at all;
        * otherwise the column *after* it pays, keeping the pair's total
          constant (``new_a = old_a + old_b - new_b``), and the stretch weights
          are re-derived from the resulting widths so the next layout keeps
          them.

        Parameters
        ----------
        index : int
            Column index.
        width : float
            Requested inner width, without padding.

        Returns
        -------
        bool
            Whether anything changed.
        """
        if not (0 <= index < len(self.columns)):
            return False
        column_0 = self.columns[index]
        min_width = self.min_column_width
        max_width = max(min_width, column_0.width_max)
        width = style.clamp(float(width), min_width, max_width)
        if column_0.width_given == width or column_0.width_request == width:
            return False

        column_1 = (
            self.columns[column_0.next_enabled] if column_0.next_enabled != -1 else None
        )
        if column_0.is_fixed():
            if (
                column_1 is None
                or self.left_most_stretched == -1
                or self.columns[self.left_most_stretched].display_order >= column_0.display_order
            ):
                column_0.width_request = width
                column_0.auto_fit = False
                return True

        if column_1 is None and column_0.prev_enabled != -1:
            column_1 = self.columns[column_0.prev_enabled]
        if column_1 is None:
            return False

        width_1 = max(column_1.width_request - (width - column_0.width_request), min_width)
        width = column_0.width_request + column_1.width_request - width_1
        column_0.width_request = width
        column_1.width_request = width_1
        column_0.auto_fit = False
        column_1.auto_fit = False
        if column_0.is_stretch() or column_1.is_stretch():
            self.update_weights_from_width()
        return True

    def update_weights_from_width(self) -> None:
        """Re-derive stretch weights from the widths the columns now have.

        ``TableUpdateColumnsWeightFromWidth``: without this a drag would be
        undone by the next layout, which resolves widths *from* the weights.
        """
        visible_weight = 0.0
        visible_width = 0.0
        for column in self.columns:
            if not column.is_enabled or not column.is_stretch():
                continue
            visible_weight += column.stretch_weight
            visible_width += column.width_request
        if visible_weight <= 0.0 or visible_width <= 0.0:
            return
        for column in self.columns:
            if not column.is_enabled or not column.is_stretch():
                continue
            column.stretch_weight = (column.width_request / visible_width) * visible_weight

    def auto_fit_column(self, index: int) -> None:
        """Make a column re-measure its contents on the next layout.

        Parameters
        ----------
        index : int
            Column index.
        """
        if 0 <= index < len(self.columns):
            self.columns[index].auto_fit = True

    def auto_fit_all(self) -> None:
        """Make every column re-measure its contents on the next layout."""
        for column in self.columns:
            column.auto_fit = True

    # ------------------------------------------------------------------ #
    # Visibility and order
    # ------------------------------------------------------------------ #
    def set_column_enabled(self, index: int, enabled: bool) -> None:
        """Show or hide a column.

        ``TableSetColumnEnabled``: the request lands on the *next* layout, the
        way the reference does it, so a caller that hides a column mid-frame
        does not tear the geometry the frame was drawn against.

        Parameters
        ----------
        index : int
            Column index.
        enabled : bool
            Whether it should be shown.
        """
        if 0 <= index < len(self.columns):
            self.columns[index].user_enabled_next = bool(enabled)

    def can_hide_column(self, index: int) -> bool:
        """Whether the context menu would let this column be switched off.

        Parameters
        ----------
        index : int
            Column index.

        Returns
        -------
        bool
            False for a ``no_hide`` column and for the last one still showing:
            a table with no columns is not a state the user can get out of.
        """
        if not (0 <= index < len(self.columns)) or not self.hideable:
            return False
        column = self.columns[index]
        if column.no_hide or column.disabled:
            return False
        if column.user_enabled and self.enabled_count <= 1:
            return False
        return True

    def max_display_order_allowed(self, src_order: int, dst_order: int) -> int:
        """Clamp a reorder to where the column is actually allowed to land.

        ``TableGetMaxDisplayOrderAllowed``: a column may not cross the frozen
        barrier, nor cross a ``no_reorder`` column.

        Parameters
        ----------
        src_order : int
            Where the column is now.
        dst_order : int
            Where the drag wants it.

        Returns
        -------
        int
            The allowed destination.
        """
        count = len(self.columns)
        dst_order = int(style.clamp(dst_order, 0, count - 1))
        if src_order == dst_order:
            return dst_order
        if self.freeze_cols > 0:
            if src_order < self.freeze_cols:
                dst_order = min(dst_order, self.freeze_cols - 1)
            else:
                dst_order = max(dst_order, self.freeze_cols)
        step = 1 if src_order < dst_order else -1
        order_n = src_order
        while (src_order < dst_order and order_n <= dst_order) or (
            dst_order < src_order and order_n >= dst_order
        ):
            if self.columns[self._order_to_index[order_n]].no_reorder:
                dst_order = src_order if order_n == src_order else order_n - step
                break
            order_n += step
        return dst_order

    def set_column_display_order(self, index: int, dst_order: int) -> bool:
        """Move a column to a display position, shuffling the ones it passes.

        ``TableSetColumnDisplayOrder``.

        Parameters
        ----------
        index : int
            Column index.
        dst_order : int
            Destination display order; clamped by
            :meth:`max_display_order_allowed`.

        Returns
        -------
        bool
            Whether the order changed.
        """
        if not (0 <= index < len(self.columns)) or not self.reorderable:
            return False
        src_order = self.columns[index].display_order
        dst_order = self.max_display_order_allowed(src_order, dst_order)
        if dst_order == src_order:
            return False
        step = -1 if dst_order < src_order else 1
        self.columns[index].display_order = dst_order
        order_n = src_order + step
        while order_n != dst_order + step:
            self.columns[self._order_to_index[order_n]].display_order -= step
            order_n += step
        self._sync_display_order()
        return True

    def reset_display_order(self) -> None:
        """Put the columns back in declaration order."""
        for index, column in enumerate(self.columns):
            column.display_order = index
        self._sync_display_order()

    def reset_visibility(self) -> None:
        """Show every column that is not hidden by default."""
        for column in self.columns:
            column.user_enabled_next = not column.default_hide

    def enabled_columns(self) -> list[int]:
        """Indices of the columns currently shown, in display order.

        Returns
        -------
        list of int
            As of the last layout.
        """
        return [i for i in self._order_to_index if self.columns[i].is_enabled]

    # ------------------------------------------------------------------ #
    # Sorting
    # ------------------------------------------------------------------ #
    def click_header(self, index: int, append: bool | None = None) -> int:
        """Advance a column through the sort cycle, as a header click does.

        Parameters
        ----------
        index : int
            Column index.
        append : bool, optional
            Add a secondary key instead of replacing the sort. Left out,
            :attr:`append_sort` decides -- which is where the host puts the
            shift key.

        Returns
        -------
        int
            The direction the column ended up in.
        """
        if not (0 <= index < len(self.columns)):
            return SORT_NONE
        column = self.columns[index]
        if column.no_sort_effective:
            return column.sort_direction
        if append is None:
            append = self.append_sort
        direction = column.next_sort_direction()
        self.set_column_sort_direction(index, direction, bool(append))
        return column.sort_direction

    def set_column_sort_direction(
        self, index: int, direction: int, append: bool = False
    ) -> None:
        """Make a column a sort key, or drop it.

        ``TableSetColumnSortDirection``.

        Parameters
        ----------
        index : int
            Column index.
        direction : int
            :data:`SORT_NONE` drops the column from the sort entirely.
        append : bool, optional
            Keep the existing keys and add this one after them. Ignored unless
            the table has ``sort_multi``.
        """
        if not (0 <= index < len(self.columns)):
            return
        if not self.sort_multi:
            append = False
        column = self.columns[index]
        sort_order_max = 0
        if append:
            sort_order_max = max(other.sort_order for other in self.columns)

        column.sort_direction = int(direction)
        if column.sort_direction == SORT_NONE:
            column.sort_order = -1
        elif column.sort_order == -1 or not append:
            column.sort_order = sort_order_max + 1 if append else 0

        for other in self.columns:
            if other is not column and not append:
                other.sort_order = -1
            other.fix_sort_direction()
        self._sort_dirty = True

    def sort_specs_count(self) -> int:
        """How many columns are currently sort keys.

        Returns
        -------
        int
            The count, without sanitising -- :meth:`sort_specs` does that.
        """
        return sum(1 for column in self.columns if column.sort_order != -1)

    def _sanitize_sort_specs(self) -> None:
        """Close gaps and duplicates in the sort order; apply the fallback.

        ``TableSortSpecsSanitize``.
        """
        for column in self.columns:
            if column.sort_order != -1 and not column.is_enabled:
                column.sort_order = -1
        sorted_cols = [c for c in self.columns if c.sort_order != -1]
        sorted_cols.sort(key=lambda c: c.sort_order)
        if not self.sort_multi and len(sorted_cols) > 1:
            for column in sorted_cols[1:]:
                column.sort_order = -1
            sorted_cols = sorted_cols[:1]
        for rank, column in enumerate(sorted_cols):
            column.sort_order = rank
        if not sorted_cols and not self.sort_tristate and self.sortable:
            for column in self.columns:
                if column.is_enabled and not column.no_sort_effective:
                    column.sort_order = 0
                    column.sort_direction = column.avail_sort_direction(0)
                    break

    def sort_specs(self) -> list[SortSpec]:
        """The sort keys, primary first.

        Returns
        -------
        list of SortSpec
            One entry per sorted column. More than one only when the table has
            ``sort_multi`` -- and the *list* is the point: a table that keeps a
            single sort column loses the tie-break the user asked for.
        """
        if self._sort_dirty:
            self._sanitize_sort_specs()
            self._sort_dirty = False
        specs = [
            SortSpec(index, column.sort_order, column.sort_direction)
            for index, column in enumerate(self.columns)
            if column.sort_order != -1
        ]
        specs.sort(key=lambda spec: spec.sort_order)
        return specs

    def sort_rows(self) -> None:
        """Reorder :attr:`rows` by the current sort specs.

        Applied from the last key to the first over a stable sort, so the
        primary key wins and the later ones break its ties -- which is what
        having a list of specs is *for*.
        """
        specs = self.sort_specs()
        for spec in reversed(specs):
            column_index = spec.column_index
            self.rows.sort(
                key=lambda row, c=column_index: _cell_key(row[c] if c < len(row) else ""),
                reverse=spec.sort_direction == SORT_DESCENDING,
            )

    # ------------------------------------------------------------------ #
    # Backgrounds
    # ------------------------------------------------------------------ #
    def set_row_bg(self, row: int, colour: Colour | None) -> None:
        """Override one row's background.

        ``TableSetBgColor(RowBg0)``.

        Parameters
        ----------
        row : int
            Row index.
        colour : Colour or None
            ``None`` removes the override.
        """
        if colour is None:
            self._row_bg.pop(int(row), None)
        else:
            self._row_bg[int(row)] = colour

    def set_cell_bg(self, row: int, column: int, colour: Colour | None) -> None:
        """Override one cell's background, drawn over the row's.

        ``TableSetBgColor(CellBg)``.

        Parameters
        ----------
        row, column : int
            The cell.
        colour : Colour or None
            ``None`` removes the override.
        """
        key = (int(row), int(column))
        if colour is None:
            self._cell_bg.pop(key, None)
        else:
            self._cell_bg[key] = colour

    def clear_bg_overrides(self) -> None:
        """Drop every row and cell background override."""
        self._row_bg.clear()
        self._cell_bg.clear()

    # ------------------------------------------------------------------ #
    # Scrolling
    # ------------------------------------------------------------------ #
    @property
    def top(self) -> int:
        """First scrolled row -- an offset past the frozen ones, not a row index."""
        return self.bar.top

    def scroll(self, rows: int) -> int:
        """Scroll the unfrozen rows.

        Parameters
        ----------
        rows : int
            How many rows to move by.

        Returns
        -------
        int
            The new top.
        """
        return self.bar.scroll(rows)

    # ------------------------------------------------------------------ #
    # Drawing
    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the header, the frozen pane, the scrolled rows and the borders.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.
        """
        # A painter that reports a zero line height would otherwise turn the
        # row loops into an unbounded walk down a table of zero-height rows.
        row_h = max(p.line_height() * self.row_scale, 1.0)
        header_h = row_h * 1.1 if self.show_headers else 0.0
        frozen_rows = max(0, min(self.freeze_rows, len(self.rows)))
        frozen_h = row_h * frozen_rows
        body_h = max(h - header_h - frozen_h, row_h)
        visible = max(int(body_h / max(row_h, 1e-6)), 1)
        self.bar.clamp(max(len(self.rows) - frozen_rows, 0), visible)
        inner_w = w - (self.bar.width if self.bar.needed() else 0.0)
        self.update_layout(p, x, inner_w)
        self._geometry = (x, y, inner_w, h, row_h, header_h, frozen_h, float(visible))

        enabled = self.enabled_columns()
        pane_x = x + self.outer_padding
        for index in enabled:
            column = self.columns[index]
            if column.display_order < self.freeze_cols:
                pane_x = max(pane_x, column.max_x)
        pane_right = x + inner_w

        p.push_clip(x, y, w, h)

        row_y = y
        if self.show_headers:
            p.fill_rect(x, y, inner_w, header_h, style.TABLE_HEADER_BG)
            for index in enabled:
                self._draw_header_cell(p, index, y, header_h, pane_x, pane_right)
            row_y += header_h

        for offset in range(frozen_rows):
            self._draw_row(p, offset, row_y, row_h, x, inner_w, pane_x, pane_right, enabled)
            row_y += row_h

        for offset in range(visible):
            row_index = frozen_rows + self.bar.top + offset
            if row_index >= len(self.rows):
                break
            self._draw_row(p, row_index, row_y, row_h, x, inner_w, pane_x, pane_right, enabled)
            row_y += row_h

        self._draw_borders(p, x, y, inner_w, h, row_h, header_h, frozen_h, enabled)
        p.pop_clip()

        if self.bar.needed():
            self.bar.draw(p, x + inner_w, y + header_h + frozen_h, h - header_h - frozen_h)
        if self.menu_open:
            self._draw_context_menu(p, x, y, w, h)

    def _cell_clip(
        self, column: Column, pane_x: float, pane_right: float
    ) -> tuple[float, float] | None:
        """The horizontal span a cell of this column may draw in.

        Parameters
        ----------
        column : Column
            The column.
        pane_x, pane_right : float
            The scrolling pane's bounds; a frozen column ignores the left one.

        Returns
        -------
        tuple or None
            ``(left, right)``, or ``None`` when the column is scrolled entirely
            out of sight.
        """
        left = column.min_x
        right = column.max_x
        if column.display_order >= self.freeze_cols:
            left = max(left, pane_x)
        right = min(right, pane_right)
        if right - left <= 0.0:
            return None
        return (left, right)

    def _draw_header_cell(
        self, p: Painter, index: int, y: float, header_h: float, pane_x: float, pane_right: float
    ) -> None:
        """Paint one header: its label, and its sort arrow and rank if sorted.

        Parameters
        ----------
        p : Painter
            The surface.
        index : int
            Column index.
        y, header_h : float
            The header row's box.
        pane_x, pane_right : float
            The scrolling pane's bounds.
        """
        column = self.columns[index]
        span = self._cell_clip(column, pane_x, pane_right)
        if span is None:
            return
        left, right = span
        p.push_clip(left, y, right - left, header_h)
        if index == self._held_header:
            p.fill_rect(left, y, right - left, header_h, style.HEADER_ACTIVE)
        mark = ""
        if column.sort_order != -1 and column.sort_direction != SORT_NONE:
            mark = _ARROW.get(column.sort_direction, "")
            if column.sort_order > 0:
                mark = f"{column.sort_order + 1}{mark}"
        room = max(column.work_max_x - column.work_min_x - p.text_width(mark), 1.0)
        p.text(
            column.work_min_x,
            y,
            room,
            header_h,
            ALIGN_VCENTER | ALIGN_LEFT,
            style.fit_text(p, column.name, room),
            style.GOLD,
            bold=True,
        )
        if mark:
            p.text(
                column.work_min_x,
                y,
                max(column.work_max_x - column.work_min_x, 1.0),
                header_h,
                ALIGN_VCENTER | ALIGN_RIGHT,
                mark,
                style.TEXT,
            )
        p.pop_clip()

    def _draw_row(
        self,
        p: Painter,
        row_index: int,
        row_y: float,
        row_h: float,
        x: float,
        inner_w: float,
        pane_x: float,
        pane_right: float,
        enabled: Sequence[int],
    ) -> None:
        """Paint one row: its background, its cell backgrounds and its cells.

        Parameters
        ----------
        p : Painter
            The surface.
        row_index : int
            Which row of :attr:`rows`.
        row_y, row_h : float
            Its box.
        x, inner_w : float
            The table's horizontal extent, for the full-width background.
        pane_x, pane_right : float
            The scrolling pane's bounds.
        enabled : sequence of int
            Column indices to draw, in display order.
        """
        row = self.rows[row_index]
        background: Colour | None = None
        if row_index in self._row_bg:
            background = self._row_bg[row_index]
        elif self.selected_row == row_index:
            background = style.HEADER
        elif self.row_bg:
            background = style.TABLE_ROW_BG_ALT if (row_index & 1) else style.TABLE_ROW_BG
        if background is not None:
            p.fill_rect(x, row_y, inner_w, row_h, background)

        for index in enabled:
            column = self.columns[index]
            span = self._cell_clip(column, pane_x, pane_right)
            if span is None:
                continue
            left, right = span
            p.push_clip(left, row_y, right - left, row_h)
            cell_bg = self._cell_bg.get((row_index, index))
            if cell_bg is not None:
                p.fill_rect(column.min_x, row_y, column.max_x - column.min_x, row_h, cell_bg)
            text = str(row[index]) if index < len(row) else ""
            if text:
                p.text(
                    column.work_min_x,
                    row_y,
                    max(column.work_max_x - column.work_min_x, 1.0),
                    row_h,
                    ALIGN_VCENTER | ALIGN_LEFT,
                    text,
                    style.TEXT,
                )
            p.pop_clip()

    def _draw_borders(
        self,
        p: Painter,
        x: float,
        y: float,
        inner_w: float,
        h: float,
        row_h: float,
        header_h: float,
        frozen_h: float,
        enabled: Sequence[int],
    ) -> None:
        """Paint the four border sets as one-pixel rectangles.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, inner_w, h : float
            The table's box, scrollbar excluded.
        row_h, header_h, frozen_h : float
            Row metrics, for where the horizontal borders go.
        enabled : sequence of int
            Column indices, in display order.
        """
        bottom = y + h
        if self.borders_inner_v:
            for position, index in enumerate(enabled):
                column = self.columns[index]
                if position == len(enabled) - 1:
                    continue
                frozen_separator = column.display_order + 1 == self.freeze_cols
                colour = (
                    style.TABLE_BORDER_STRONG if frozen_separator else style.TABLE_BORDER_LIGHT
                )
                if x <= column.max_x <= x + inner_w:
                    p.fill_rect(column.max_x, y, BORDER_SIZE, h, colour)
        if self.borders_outer_v:
            p.fill_rect(x, y, BORDER_SIZE, h, style.TABLE_BORDER_STRONG)
            p.fill_rect(x + inner_w - BORDER_SIZE, y, BORDER_SIZE, h, style.TABLE_BORDER_STRONG)
        if self.borders_inner_h:
            line_y = y + header_h
            if self.show_headers:
                p.fill_rect(x, line_y, inner_w, BORDER_SIZE, style.TABLE_BORDER_STRONG)
            frozen_rows = max(0, min(self.freeze_rows, len(self.rows)))
            for offset in range(1, frozen_rows):
                p.fill_rect(
                    x, line_y + offset * row_h, inner_w, BORDER_SIZE, style.TABLE_BORDER_LIGHT
                )
            if frozen_rows:
                # The unfreezing mark is always strong: it is the seam between
                # a pane that moves and one that does not.
                p.fill_rect(
                    x, line_y + frozen_h, inner_w, BORDER_SIZE, style.TABLE_BORDER_STRONG
                )
            body_y = line_y + frozen_h
            offset = 1
            while body_y + offset * row_h < bottom:
                p.fill_rect(
                    x, body_y + offset * row_h, inner_w, BORDER_SIZE, style.TABLE_BORDER_LIGHT
                )
                offset += 1
        if self.borders_outer_h:
            p.fill_rect(x, y, inner_w, BORDER_SIZE, style.TABLE_BORDER_STRONG)
            p.fill_rect(x, bottom - BORDER_SIZE, inner_w, BORDER_SIZE, style.TABLE_BORDER_STRONG)

    # ------------------------------------------------------------------ #
    # The context menu
    # ------------------------------------------------------------------ #
    def open_context_menu(self, column: int = -1, at: tuple[float, float] | None = None) -> None:
        """Open the column menu: the visibility list and the two resets.

        Parameters
        ----------
        column : int, optional
            The column the menu was opened over; ``-1`` for the table itself.
        at : tuple of float, optional
            Where to put it. Defaults to the table's top-left corner.
        """
        self.menu_open = True
        self.menu_column = int(column)
        self._menu_at = at

    def close_context_menu(self) -> None:
        """Close the column menu."""
        self.menu_open = False
        self._menu_geometry = None

    def menu_items(self) -> list[tuple[str, int, bool, bool]]:
        """What the context menu currently offers.

        Returns
        -------
        list of tuple
            ``(label, column_index, checked, enabled)`` -- one per hideable
            column in display order, then the two reset items with a column
            index of ``-1``.
        """
        items: list[tuple[str, int, bool, bool]] = []
        if self.hideable:
            for index in self._order_to_index:
                column = self.columns[index]
                if column.disabled:
                    continue
                items.append(
                    (column.name or "<unnamed>", index, column.user_enabled,
                     self.can_hide_column(index))
                )
        if self.reorderable:
            items.append(("Reset order", -1, False, True))
        if self.hideable:
            items.append(("Reset visibility", -1, False, True))
        return items

    def _draw_context_menu(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the column menu as a framed list of ticked entries.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The table's box, which the menu is placed inside.
        """
        items = self.menu_items()
        if not items:
            return
        line_h = p.line_height() * 1.4
        widest = max(p.text_width(label) for label, _, _, _ in items)
        menu_w = min(widest + 34.0, max(w, 40.0))
        menu_h = line_h * len(items) + 6.0
        at = self._menu_at
        menu_x = style.clamp(at[0] if at else x + 8.0, x, x + max(w - menu_w, 0.0))
        menu_y = style.clamp(at[1] if at else y + 8.0, y, y + max(h - menu_h, 0.0))
        self._menu_geometry = (menu_x, menu_y, menu_w, menu_h, line_h)
        p.stroke_rect(menu_x, menu_y, menu_w, menu_h, style.BORDER, style.POPUP_BG)
        p.push_clip(menu_x, menu_y, menu_w, menu_h)
        for position, (label, index, checked, item_enabled) in enumerate(items):
            item_y = menu_y + 3.0 + position * line_h
            if index != -1:
                tick = "■" if checked else " "
                p.text(menu_x + 6.0, item_y, 14.0, line_h, ALIGN_VCENTER | ALIGN_LEFT, tick,
                       style.CHECK_MARK if checked else style.TEXT_DISABLED)
            colour = style.TEXT if item_enabled else style.TEXT_DISABLED
            p.text(menu_x + 22.0, item_y, max(menu_w - 28.0, 1.0), line_h,
                   ALIGN_VCENTER | ALIGN_LEFT, label, colour)
        p.pop_clip()

    def _press_menu(self, x: float, y: float) -> tuple[str, int] | None:
        """Route a press into the open context menu.

        Parameters
        ----------
        x, y : float
            The press.

        Returns
        -------
        tuple or None
            The action taken, or ``None`` when the press was not in the menu --
            in which case the caller closes it.
        """
        if self._menu_geometry is None:
            return None
        menu_x, menu_y, menu_w, menu_h, line_h = self._menu_geometry
        if not style.hit(x, y, menu_x, menu_y, menu_w, menu_h):
            return None
        position = int((y - menu_y - 3.0) / max(line_h, 1e-6))
        items = self.menu_items()
        if not (0 <= position < len(items)):
            return ("menu", self.menu_column)
        label, index, checked, item_enabled = items[position]
        if not item_enabled:
            return ("menu", index)
        if index != -1:
            self.set_column_enabled(index, not checked)
            return ("visibility", index)
        self.close_context_menu()
        if label == "Reset order":
            self.reset_display_order()
            return ("reset_order", -1)
        self.reset_visibility()
        return ("reset_visibility", -1)

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #
    def press(
        self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float
    ) -> tuple[str, int] | None:
        """Route a press: menu, resize border, scrollbar, header, or row.

        The order matters and is the reference's: the resize border is a
        separate item that sits *over* the header, so a press four pixels from
        a column edge starts a drag rather than a sort.

        Parameters
        ----------
        x, y : float
            The press.
        box_x, box_y, box_w, box_h : float
            The box the table was drawn into.

        Returns
        -------
        tuple or None
            ``("visibility", col)``, ``("reset_order", -1)``,
            ``("reset_visibility", -1)``, ``("menu", col)``, ``("resize", col)``,
            ``("scroll", top)``, ``("header", col)``, ``("row", row)``, or
            ``None``.
        """
        if self.menu_open:
            handled = self._press_menu(x, y)
            if handled is not None:
                return handled
            self.close_context_menu()
        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            return None
        if self._geometry is None:
            return None
        geo_x, geo_y, inner_w, _h, row_h, header_h, frozen_h, _visible = self._geometry

        if self.resizable:
            border = self.column_border_at(x)
            if border != -1:
                self._resizing = border
                self._resize_grab = x - self.columns[border].max_x
                return ("resize", border)

        if self.bar.press(x, y):
            return ("scroll", self.bar.top)

        if self.show_headers and y <= geo_y + header_h:
            index = self.column_at(x)
            if index == -1:
                return None
            self._held_header = index
            self._drag_from_x = x
            self.click_header(index)
            return ("header", index)

        frozen_rows = max(0, min(self.freeze_rows, len(self.rows)))
        body_top = geo_y + header_h
        offset = int((y - body_top) / max(row_h, 1e-6))
        if offset < frozen_rows:
            row_index = offset
        else:
            row_index = frozen_rows + self.bar.top + (offset - frozen_rows)
        if 0 <= row_index < len(self.rows):
            self.selected_row = row_index
            return ("row", row_index)
        return None

    def column_at(self, x: float) -> int:
        """Which column a horizontal position lands in.

        Parameters
        ----------
        x : float
            The position.

        Returns
        -------
        int
            Column index, or ``-1`` past the last one.
        """
        for index in self.enabled_columns():
            column = self.columns[index]
            if column.min_x <= x < column.max_x:
                return index
        return -1

    def column_border_at(self, x: float) -> int:
        """Which column's right-hand border a press would grab.

        Parameters
        ----------
        x : float
            The position.

        Returns
        -------
        int
            Column index, or ``-1``. A column that cannot be resized, and the
            right-most one when any stretch column exists (Resize Rule 1), have
            no grabbable border.
        """
        for index in self.enabled_columns():
            column = self.columns[index]
            if column.no_resize_effective or column.no_direct_resize:
                continue
            if abs(x - column.max_x) <= RESIZE_HALF_THICKNESS:
                return index
        return -1

    def drag(
        self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float
    ) -> bool:
        """Continue a resize, a header reorder, or a scrollbar drag.

        Parameters
        ----------
        x, y : float
            Where the pointer is now.
        box_x, box_y, box_w, box_h : float
            The box the table was drawn into.

        Returns
        -------
        bool
            Whether anything moved.
        """
        if self._resizing != -1:
            column = self.columns[self._resizing]
            new_x2 = x - self._resize_grab
            width = _trunc(new_x2 - column.min_x - self.cell_padding * 2.0)
            return self.set_column_width(self._resizing, width)
        if self.bar.held:
            return self.bar.drag(y)
        if self._held_header != -1 and self.reorderable:
            column = self.columns[self._held_header]
            delta = x - self._drag_from_x
            self._drag_from_x = x
            if delta < 0.0 and x < column.min_x and column.prev_enabled != -1:
                return self.set_column_display_order(
                    self._held_header, self.columns[column.prev_enabled].display_order
                )
            if delta > 0.0 and x > column.max_x and column.next_enabled != -1:
                return self.set_column_display_order(
                    self._held_header, self.columns[column.next_enabled].display_order
                )
        return False

    def release(self) -> None:
        """Let go of whatever was being dragged."""
        self._resizing = -1
        self._held_header = -1
        self.bar.release()
