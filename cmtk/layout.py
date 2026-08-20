"""The cursor the painter-level controls are laid out against.

Why this exists
---------------
Every control in :mod:`.widgets` takes an explicit box -- ``draw(p, x, y, w,
h)`` -- and that is deliberate: it is why a control needs no global context, no
window stack and no "current" anything, and why it can be tested by handing it
four numbers. It is also why every *host* ends up writing the same arithmetic.
:mod:`.settings_editor` derives its own head, body and foot bands and then
walks ``row_y = body_y + offset * row_h``; :mod:`..density_window` carries
``_ROW``, ``_GAP`` and ``_PAD`` module constants and threads a running ``y``
through four ``_draw_*`` helpers, each of which has to remember to return the
next one. Three hosts, three private ideas of how far apart two rows sit.

The reference implementation solves this with a cursor: ``ItemSize`` advances
it by the item just laid out, ``SameLine`` puts the next item beside the last
instead of below it, ``Indent`` moves the left margin, ``BeginGroup`` /
``EndGroup`` make a run of items measure as one, and ``Columns`` splits the
width. That is what :class:`Layout` is.

What it is not
--------------
Not an immediate-mode context. The reference reaches ``GImGui`` -- a global --
from every one of those functions, and the whole point of the cmtk port is
that there is exactly one code path and no ambient state: two panels drawn in
the same frame must not be able to see each other's cursor. So the cursor is an
*object the host threads through*, constructed with the box it lays out inside:

.. code-block:: python

    layout = Layout(p, x, y, w, h)
    title.draw(p, *layout.row())
    layout.separator()
    for setting in settings:
        control.draw(p, *layout.row())
    if layout.content_height() > h:
        ...  # the host now knows it needs a scrollbar

:class:`Layout` draws nothing. It reads ``p.line_height()`` once, to derive a
row height and an indent step, and after that it is arithmetic -- which is what
makes it testable against hand-computed rectangles.

Where the numbers come from
---------------------------
``ImGuiStyle`` in the reference's ``imgui.cpp``: ``ItemSpacing = (8, 4)``,
``FramePadding = (4, 3)``, ``IndentSpacing = 21`` (documented there as
"generally ``FontSize + FramePadding.x * 2``", which is how it is derived here
so it tracks the chrome's font rather than the reference's 13-pixel one), and
``SeparatorSize = 1``. The advance itself is ``ItemSize``:

.. code-block:: text

    line_y1     = IsSameLine ? CursorPosPrevLine.y : CursorPos.y
    line_height = max(CurrLineSize.y, CursorPos.y - line_y1 + size.y)
    CursorPos.x = trunc(Pos.x + Indent.x + ColumnsOffset.x)
    CursorPos.y = trunc(line_y1 + line_height + ItemSpacing.y)

including the truncation, which is what keeps a fractional row height from
smearing text off the pixel grid one row at a time.
"""
from __future__ import annotations

from dataclasses import dataclass

from .painter import Painter

__all__ = [
    "LayoutStyle",
    "Layout",
]

#: A rectangle, in the order every control's ``draw`` takes it.
Rect = tuple[float, float, float, float]


def _trunc(value: float) -> float:
    """The reference's ``IM_TRUNC``: drop the fraction, towards zero.

    Parameters
    ----------
    value : float
        The coordinate.

    Returns
    -------
    float
        ``value`` with its fractional part removed.
    """
    return float(int(value))


@dataclass
class LayoutStyle:
    """The spacing constants a :class:`Layout` lays out with.

    The defaults are the reference implementation's ``ImGuiStyle``, in pixels.

    Attributes
    ----------
    item_spacing_x, item_spacing_y : float
        Gap between two items on a line, and between two lines. The reference's
        ``ItemSpacing = (8, 4)``.
    frame_padding_x, frame_padding_y : float
        Padding inside a framed control. Only the vertical half is used for
        layout -- it is what makes a row taller than its text -- but both are
        kept because the horizontal half is what ``indent_spacing`` derives
        from. The reference's ``FramePadding = (4, 3)``.
    indent_spacing : float or None
        How far :meth:`Layout.indent` moves the left margin. ``None`` derives
        it as ``line_height + frame_padding_x * 2``, which is what the
        reference's ``IndentSpacing = 21`` is documented to be.
    separator_size : float
        Thickness of the rule :meth:`Layout.separator` reserves room for. The
        reference's ``SeparatorSize = 1``.
    """

    item_spacing_x: float = 8.0
    item_spacing_y: float = 4.0
    frame_padding_x: float = 4.0
    frame_padding_y: float = 3.0
    indent_spacing: float | None = None
    separator_size: float = 1.0


@dataclass
class _GroupState:
    """What :meth:`Layout.begin_group` saves and :meth:`Layout.end_group` puts back."""

    cursor_x: float
    cursor_y: float
    prev_line_x: float
    prev_line_y: float
    max_x: float
    max_y: float
    indent: float
    group_offset: float
    curr_line_h: float
    same_line: bool


@dataclass
class _ColumnState:
    """A live ``Columns()`` set: how wide, where the row started, which one is current."""

    count: int
    current: int
    off_min_x: float
    off_max_x: float
    line_min_y: float
    line_max_y: float
    host_max_x: float


class Layout:
    """A layout cursor over a box: ask it for the next row, and it advances.

    The host owns it, passes it around, and throws it away at the end of the
    frame (or calls :meth:`reset`). Nothing else can see it -- there is no
    global "current layout", because two panels drawn in one frame must not be
    able to disturb each other.

    Parameters
    ----------
    p : Painter
        Measured once, for :meth:`Painter.line_height`. Nothing is drawn.
    x, y, w, h : float
        The box to lay out inside. ``x, y`` is the top-left corner and where
        the cursor starts; the right edge ``x + w`` is what a full-width row
        reaches and what :meth:`avail` measures against.
    style : LayoutStyle, optional
        The spacing constants. Defaults to the reference's.

    Attributes
    ----------
    line_h : float
        One line of text, as the painter measures it.
    row_height : float
        The default height of a :meth:`row`: ``line_h + frame_padding_y * 2``,
        the reference's ``GetFrameHeight()``.
    indent_step : float
        How far one :meth:`indent` moves the margin.

    Examples
    --------
    >>> class P:                     # a painter that only has to measure
    ...     def line_height(self): return 12.0
    >>> layout = Layout(P(), 10.0, 20.0, 200.0, 300.0)
    >>> layout.row()
    (10.0, 20.0, 200.0, 18.0)
    >>> layout.row()
    (10.0, 42.0, 200.0, 18.0)
    >>> layout.content_height()
    40.0
    """

    def __init__(
        self,
        p: Painter,
        x: float,
        y: float,
        w: float,
        h: float,
        style: LayoutStyle | None = None,
    ) -> None:
        self.style = style if style is not None else LayoutStyle()
        self.line_h = float(p.line_height())
        self.row_height = self.line_h + self.style.frame_padding_y * 2.0
        self.indent_step = (
            self.line_h + self.style.frame_padding_x * 2.0
            if self.style.indent_spacing is None
            else float(self.style.indent_spacing)
        )
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)
        self._groups: list[_GroupState] = []
        self._columns: _ColumnState | None = None
        self.reset()

    # ------------------------------------------------------------------ #
    # The cursor
    # ------------------------------------------------------------------ #
    def reset(
        self,
        x: float | None = None,
        y: float | None = None,
        w: float | None = None,
        h: float | None = None,
    ) -> None:
        """Put the cursor back at the top-left, optionally in a new box.

        A host that keeps its :class:`Layout` between frames -- so that last
        frame's :meth:`content_height` is still readable while this frame is
        being laid out -- calls this at the top of its ``draw``.

        Parameters
        ----------
        x, y, w, h : float, optional
            A new box. Each defaults to the current one.
        """
        if x is not None:
            self.x = float(x)
        if y is not None:
            self.y = float(y)
        if w is not None:
            self.w = float(w)
        if h is not None:
            self.h = float(h)
        self._cursor_x = self.x
        self._cursor_y = self.y
        self._prev_line_x = self.x
        self._prev_line_y = self.y
        self._max_x = self.x
        self._max_y = self.y
        self._indent = 0.0
        self._group_offset = 0.0
        self._columns_offset = 0.0
        self._curr_line_h = 0.0
        self._prev_line_h = 0.0
        self._same_line = False
        self._last_item: Rect = (self.x, self.y, 0.0, 0.0)
        self._groups.clear()
        self._columns = None

    @property
    def cursor(self) -> tuple[float, float]:
        """Where the next item would be placed, as ``(x, y)``."""
        return (self._cursor_x, self._cursor_y)

    @property
    def indent_x(self) -> float:
        """The current left margin, relative to the box's left edge."""
        return self._indent

    def advance(self, width: float, height: float) -> None:
        """Move the cursor past an item of this size. The reference's ``ItemSize``.

        Every other method here is written in terms of this one. A host that
        drew something the layout does not know about -- a hand-placed block,
        a control it sized itself -- calls this to keep the cursor honest.

        Parameters
        ----------
        width : float
            How far right the item reached. This is what a following
            :meth:`same_line` with no offset measures from, which is why
            :meth:`separator` passes zero: a rule spans the whole width but
            must not push the cursor off the right edge.
        height : float
            How tall the item was.
        """
        line_y1 = self._prev_line_y if self._same_line else self._cursor_y
        line_height = max(self._curr_line_h, self._cursor_y - line_y1 + float(height))

        self._prev_line_x = self._cursor_x + float(width)
        self._prev_line_y = line_y1
        self._cursor_x = _trunc(self.x + self._indent + self._columns_offset)
        self._cursor_y = _trunc(line_y1 + line_height + self.style.item_spacing_y)
        self._max_x = max(self._max_x, self._prev_line_x)
        self._max_y = max(self._max_y, self._cursor_y - self.style.item_spacing_y)

        self._prev_line_h = line_height
        self._curr_line_h = 0.0
        self._same_line = False

    # ------------------------------------------------------------------ #
    # Items
    # ------------------------------------------------------------------ #
    def row(self, height: float | None = None, width: float | None = None) -> Rect:
        """The next row's rectangle, and advance past it.

        This is the method hosts live on: ``control.draw(p, *layout.row())``.

        Parameters
        ----------
        height : float, optional
            Row height. Defaults to :attr:`row_height`.
        width : float, optional
            Row width. Defaults to everything left to the right edge (of the
            current column, inside :meth:`columns`). Pass a width when the row
            is going to be followed by :meth:`same_line` -- a full-width row
            leaves the cursor at the right edge, and the reference behaves the
            same way.

        Returns
        -------
        tuple of float
            ``(x, y, w, h)``, in the order every control's ``draw`` takes it.
        """
        row_h = self.row_height if height is None else float(height)
        row_w = self.avail()[0] if width is None else float(width)
        box = (self._cursor_x, self._cursor_y, row_w, row_h)
        self.advance(row_w, row_h)
        self._last_item = box
        return box

    def spacing(self) -> None:
        """Leave one item-spacing gap. The reference's ``Spacing()`` -- ``ItemSize(0, 0)``."""
        self.advance(0.0, 0.0)

    def dummy(self, w: float, h: float) -> Rect:
        """Reserve a rectangle without drawing in it. The reference's ``Dummy()``.

        Parameters
        ----------
        w, h : float
            The size to reserve.

        Returns
        -------
        tuple of float
            The reserved ``(x, y, w, h)``, so the caller can draw into it if it
            turns out it wants to after all.
        """
        box = (self._cursor_x, self._cursor_y, float(w), float(h))
        self.advance(float(w), float(h))
        self._last_item = box
        return box

    def new_line(self) -> None:
        """End the current line, whether or not anything was put on it.

        The reference's ``NewLine()``: a line that already has items keeps its
        own height (``ItemSize(0, 0)``); an empty one gets a blank text line
        (``ItemSize(0, FontSize)``) so that two ``new_line`` calls in a row are
        two visible gaps rather than one.
        """
        self._same_line = False
        if self._curr_line_h > 0.0:
            self.advance(0.0, 0.0)
        else:
            self.advance(0.0, self.line_h)

    def separator(self, thickness: float | None = None) -> Rect:
        """Reserve the rule between two groups of rows.

        Draws nothing -- hand the rectangle to
        :class:`~cmtk.widgets.basic.Separator`, which is the control
        that knows what a rule looks like (and how to sit a caption in one).

        Parameters
        ----------
        thickness : float, optional
            Height to reserve. Defaults to :attr:`LayoutStyle.separator_size`.

        Returns
        -------
        tuple of float
            ``(x, y, w, thickness)``, spanning to the right edge.

        Notes
        -----
        The reference's ``SeparatorEx`` spans ``CursorPos.x`` to
        ``WorkRect.Max.x`` but feeds ``ItemSize(ImVec2(0.0f, thickness))`` --
        zero width -- to the layout, with the comment *"We don't provide our
        width to the layout so that it doesn't get feed back into AutoFit"*.
        That is ported as-is: a rule does not widen the panel that contains it.
        """
        rule = self.style.separator_size if thickness is None else float(thickness)
        box = (self._cursor_x, self._cursor_y, max(self._work_right() - self._cursor_x, 0.0), rule)
        self.advance(0.0, rule)
        self._last_item = box
        return box

    # ------------------------------------------------------------------ #
    # Placement
    # ------------------------------------------------------------------ #
    def same_line(self, offset: float = 0.0, spacing: float | None = None) -> None:
        """Put the next item beside the previous one instead of below it.

        The two forms are **not** the same rule, and that is the reference's
        design rather than an accident:

        ==================  ==========================================
        ``offset == 0``     right after the previous item, default gap
                            ``item_spacing_x``
        ``offset != 0``     at ``offset`` from the box's left edge (plus
                            any group and column offset), default gap
                            **zero**
        ==================  ==========================================

        The second form is how a column of aligned labels is built -- the
        offset is an absolute position, so a gap on top of it would be a
        surprise; the first is how two buttons are put side by side, where the
        gap is the whole point. Both take the previous line's ``y``, so the two
        items line up.

        Parameters
        ----------
        offset : float, optional
            Distance from the box's left edge. Zero (the default) means "right
            after the previous item".
        spacing : float, optional
            Override the gap. ``None`` takes the default for the form in use.
        """
        if offset != 0.0:
            gap = 0.0 if spacing is None or spacing < 0.0 else float(spacing)
            self._cursor_x = (
                self.x + float(offset) + gap + self._group_offset + self._columns_offset
            )
        else:
            gap = self.style.item_spacing_x if spacing is None or spacing < 0.0 else float(spacing)
            self._cursor_x = self._prev_line_x + gap
        self._cursor_y = self._prev_line_y
        self._curr_line_h = self._prev_line_h
        self._same_line = True

    def indent(self, width: float | None = None) -> None:
        """Move the left margin right by one step.

        Parameters
        ----------
        width : float, optional
            How far. Defaults to :attr:`indent_step`.
        """
        step = self.indent_step if not width else float(width)
        self._indent += step
        self._cursor_x = self.x + self._indent + self._columns_offset

    def unindent(self, width: float | None = None) -> None:
        """Move the left margin back left by one step.

        Parameters
        ----------
        width : float, optional
            How far. Defaults to :attr:`indent_step`, so that an
            :meth:`indent` / :meth:`unindent` pair returns to exactly where it
            started.
        """
        step = self.indent_step if not width else float(width)
        self._indent -= step
        self._cursor_x = self.x + self._indent + self._columns_offset

    # ------------------------------------------------------------------ #
    # Groups
    # ------------------------------------------------------------------ #
    def begin_group(self) -> None:
        """Start measuring a run of items as one.

        Inside a group the left margin is locked to wherever the cursor was,
        so a group opened after :meth:`same_line` lays out down its own edge
        rather than the panel's. :meth:`end_group` gives back the bounding box
        of everything laid out in between -- which is what a host needs to draw
        a frame around it, or to hit-test it as a unit.
        """
        self._groups.append(
            _GroupState(
                cursor_x=self._cursor_x,
                cursor_y=self._cursor_y,
                prev_line_x=self._prev_line_x,
                prev_line_y=self._prev_line_y,
                max_x=self._max_x,
                max_y=self._max_y,
                indent=self._indent,
                group_offset=self._group_offset,
                curr_line_h=self._curr_line_h,
                same_line=self._same_line,
            )
        )
        self._group_offset = self._cursor_x - self.x - self._columns_offset
        self._indent = self._group_offset
        self._max_x = self._cursor_x
        self._max_y = self._cursor_y
        self._curr_line_h = 0.0

    def end_group(self) -> Rect:
        """Close the group and return its bounding box.

        The group then advances the cursor as a single item of that size, so
        the row after it clears the whole group and a :meth:`same_line` after
        it lands beside the group's right edge.

        Returns
        -------
        tuple of float
            ``(x, y, w, h)`` spanning every item in the group, including ones
            placed with :meth:`same_line`.

        Raises
        ------
        RuntimeError
            If there is no open group. Unbalanced groups are the one way to
            corrupt a layout silently -- the margin stays where the group left
            it and every row after it is wrong -- so this is loud.
        """
        if not self._groups:
            raise RuntimeError("end_group() without begin_group()")
        saved = self._groups.pop()
        last_x, last_y, last_w, last_h = self._last_item
        bb_max_x = max(self._max_x, last_x + last_w, saved.cursor_x)
        bb_max_y = max(self._max_y, last_y + last_h, saved.cursor_y)
        box = (
            saved.cursor_x,
            saved.cursor_y,
            bb_max_x - saved.cursor_x,
            bb_max_y - saved.cursor_y,
        )

        self._cursor_x = saved.cursor_x
        self._cursor_y = saved.cursor_y
        self._prev_line_x = saved.prev_line_x
        self._prev_line_y = saved.prev_line_y
        self._max_x = max(saved.max_x, bb_max_x)
        self._max_y = max(saved.max_y, bb_max_y)
        self._indent = saved.indent
        self._group_offset = saved.group_offset
        self._curr_line_h = saved.curr_line_h
        self._same_line = saved.same_line

        self.advance(box[2], box[3])
        self._last_item = box
        return box

    # ------------------------------------------------------------------ #
    # Columns
    # ------------------------------------------------------------------ #
    def columns(self, count: int) -> None:
        """Split the remaining width into ``count`` equal columns.

        Items go into the current column until :meth:`next_column`; wrapping
        past the last column starts a new row below the *tallest* column, so
        columns of unequal length still line up underneath.

        Parameters
        ----------
        count : int
            How many columns. ``1`` ends the current set, which is exactly what
            the reference's ``Columns(1)`` does. Re-declaring the same count is
            a no-op, so a host may call this every frame.

        Notes
        -----
        The reference divides ``[OffMinX, OffMaxX]`` evenly
        (``OffsetNorm = n / count``) and then insets each column by
        ``column_padding = ItemSpacing.x``: the left edge of column *n* is
        ``Pos.x + Indent + n * column_width`` and its right edge is
        ``column_width - 2 * padding`` further on. ``OffMinX`` is pulled
        ``padding`` left of the indent, which is what makes the last column
        stop one padding short of the right edge instead of touching it.
        """
        count = int(count)
        if count < 1:
            raise ValueError("columns(count) needs at least one column")
        if self._columns is not None and self._columns.count == count:
            return
        if self._columns is not None:
            self.end_columns()
        if count == 1:
            return
        padding = self.style.item_spacing_x
        off_min = self._indent - padding
        self._columns = _ColumnState(
            count=count,
            current=0,
            off_min_x=off_min,
            off_max_x=max(self.w, off_min + 1.0),
            line_min_y=self._cursor_y,
            line_max_y=self._cursor_y,
            host_max_x=self._max_x,
        )
        self._columns_offset = 0.0
        self._cursor_x = _trunc(self.x + self._indent + self._columns_offset)

    def next_column(self) -> None:
        """Move to the next column, wrapping to a new row after the last one."""
        columns = self._columns
        if columns is None:
            return
        columns.current = (columns.current + 1) % columns.count
        columns.line_max_y = max(columns.line_max_y, self._cursor_y)
        if columns.current > 0:
            # Columns 1+ ignore the indent, by cancelling it out.
            self._columns_offset = (
                self._column_offset(columns.current) - self._indent + self.style.item_spacing_x
            )
        else:
            self._columns_offset = 0.0
            self._same_line = False
            columns.line_min_y = columns.line_max_y
        self._cursor_x = _trunc(self.x + self._indent + self._columns_offset)
        self._cursor_y = columns.line_min_y
        self._curr_line_h = 0.0

    def end_columns(self) -> None:
        """Close the column set, leaving the cursor below the tallest column."""
        columns = self._columns
        if columns is None:
            return
        columns.line_max_y = max(columns.line_max_y, self._cursor_y)
        self._cursor_y = columns.line_max_y
        # Columns do not grow the panel that contains them.
        self._max_x = columns.host_max_x
        self._columns = None
        self._columns_offset = 0.0
        self._cursor_x = _trunc(self.x + self._indent)

    @property
    def column_index(self) -> int:
        """Which column items are going into; ``0`` when there is no column set."""
        return 0 if self._columns is None else self._columns.current

    @property
    def column_count(self) -> int:
        """How many columns are open; ``1`` when there is no column set."""
        return 1 if self._columns is None else self._columns.count

    def _column_offset(self, index: int) -> float:
        """Left edge of column ``index``, relative to the box's left edge.

        Parameters
        ----------
        index : int
            Column number. ``count`` is valid and gives the right edge of the
            last column, which is how the reference measures widths.

        Returns
        -------
        float
            The offset.
        """
        columns = self._columns
        if columns is None:
            return 0.0
        span = columns.off_max_x - columns.off_min_x
        return columns.off_min_x + span * (index / columns.count)

    # ------------------------------------------------------------------ #
    # Measurement
    # ------------------------------------------------------------------ #
    def _work_right(self) -> float:
        """The x the current row may reach: the box's right edge, or the column's."""
        if self._columns is None:
            return self.x + self.w
        right = self.x + self._column_offset(self._columns.current + 1)
        return right - self.style.item_spacing_x

    def avail(self) -> tuple[float, float]:
        """How much room is left from the cursor, as ``(width, height)``.

        The reference's ``GetContentRegionAvail()``. Never negative: a cursor
        already past the edge reports zero rather than a width that would draw
        a control inside out.

        Returns
        -------
        tuple of float
            ``(width, height)``.
        """
        return (
            max(self._work_right() - self._cursor_x, 0.0),
            max(self.y + self.h - self._cursor_y, 0.0),
        )

    def content_width(self) -> float:
        """How wide everything laid out so far reached, from the box's left edge."""
        return self._max_x - self.x

    def content_height(self) -> float:
        """How tall everything laid out so far was, from the box's top edge.

        This is what a host tests against its own height to decide whether it
        needs a scrollbar -- the reference sizes its windows off exactly this
        (``CursorMaxPos - CursorStartPos``). The trailing item spacing after
        the last row is not counted, so a panel whose rows exactly fill it does
        not report itself one gap too tall and grow a scrollbar for nothing.
        """
        return self._max_y - self.y
