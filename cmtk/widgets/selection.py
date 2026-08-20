"""Rows you can pick: selectables, framed headers, and the selection model.

Why this is its own module
--------------------------
:mod:`.widgets` already has a :class:`~.widgets.ListBox` -- a list with *one*
selected row, moved by clicking it. That is the whole of its selection model,
and it is the right model for a settings enum. It is the wrong model for a list
of objects, where the question is never "which one" but "which ones", and where
the answer is built by clicking, ctrl-clicking and shift-clicking in some order
the list itself has no say in.

The reference implementation solves this with a *multi-select scope*: an item
carries a user-data index, and the scope turns a click plus its modifiers into
selection **requests** against an anchor it remembers between clicks. The anchor
is the part that carries the behaviour -- it is what makes shift-click extend a
range rather than select a pair -- and it is the part a naive port drops, because
a port that keeps only "the last clicked row" gets ranges right in one direction
and silently wrong in the other.

So the model is ported as an object, :class:`MultiSelectState`, which is
deliberately *not* a widget: it holds indices and knows nothing about pixels.
:class:`SelectableList` puts a scrollbar and a run of :class:`Selectable` rows in
front of it, and either can be used without the other.

What "no per-frame context" costs
---------------------------------
The reference reads the clock and the keyboard modifiers off a global context
that a frame loop refreshes. cmtk has neither, so the two are **arguments**:
:meth:`MultiSelectState.click` takes ``ctrl`` and ``shift`` as booleans, and
:meth:`TypingSelect.type_char` takes ``now`` as a float the caller supplies.
That is the only divergence in the ported behaviour, and it is a divergence in
*plumbing* rather than in what the controls do.
"""
from __future__ import annotations

from collections.abc import Sequence

from .. import style
from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter
from .basic import ScrollBar

__all__ = [
    "SELECTABLE_NONE",
    "SELECTABLE_SPAN_ALL_COLUMNS",
    "SELECTABLE_ALLOW_DOUBLE_CLICK",
    "SELECTABLE_DISABLED",
    "SELECTABLE_DONT_CLOSE_POPUPS",
    "Selectable",
    "CollapsingHeader",
    "MultiSelectState",
    "SelectableList",
    "TypingSelect",
]

#: No flags. The reference's ``ImGuiSelectableFlags_None``.
SELECTABLE_NONE = 0
#: Draw the highlight across the whole row rather than across the item's own
#: box. The reference's ``SpanAllColumns``: in a table the frame is widened to
#: the parent work rect while the *label* stays in its column. Here the wider
#: rect is :attr:`Selectable.span`, which the container sets.
SELECTABLE_SPAN_ALL_COLUMNS = 1 << 1
#: Report a press for a double click too. Without it a double click is a single
#: press followed by nothing, which is what the reference's default
#: ``PressedOnClickRelease`` behaviour amounts to.
SELECTABLE_ALLOW_DOUBLE_CLICK = 1 << 2
#: Draw dimmed and refuse every press.
SELECTABLE_DISABLED = 1 << 3
#: Pressing this one does not close the popup it sits in. The reference renamed
#: this to ``NoAutoClosePopups`` and kept the old name as an alias; the old name
#: is the one that says what it is for.
SELECTABLE_DONT_CLOSE_POPUPS = 1 << 0


def _alpha_of(colour: style.Colour) -> int:
    """The alpha channel of a colour, defaulting to opaque.

    Parameters
    ----------
    colour : Colour
        A three- or four-tuple.

    Returns
    -------
    int
        The alpha, 0-255.
    """
    return int(colour[3]) if len(colour) > 3 else 255


def _match_len(prefix: str, name: str) -> int:
    """How many leading characters of ``name`` match ``prefix``, case-blind.

    The reference calls this ``ImStrimatchlen`` and uses it for both type-ahead
    modes: the best *leading* match compares the whole buffer, the single-char
    mode compares only the first character.

    Parameters
    ----------
    prefix : str
        The typed text.
    name : str
        The item's name.

    Returns
    -------
    int
        The number of matching leading characters.
    """
    count = 0
    for a, b in zip(prefix, name):
        if a.upper() != b.upper():
            break
        count += 1
    return count


class Selectable:
    """A full-width clickable row that can be highlighted as selected.

    The reference's ``Selectable()`` is the row primitive everything selectable
    is built from -- list entries, menu items, table rows -- and it is one call
    that both draws and reports the click. Here that is one object: it keeps the
    ``selected`` and ``hovered`` state the reference keeps in its context, and
    reports the press.

    Parameters
    ----------
    label : str
        The caption. Shortened with :func:`~.style.fit_text` when the box is too
        narrow, rather than drawn over the next column.
    selected : bool, optional
        Whether it starts highlighted.
    flags : int, optional
        Any of :data:`SELECTABLE_SPAN_ALL_COLUMNS`,
        :data:`SELECTABLE_ALLOW_DOUBLE_CLICK`, :data:`SELECTABLE_DISABLED` and
        :data:`SELECTABLE_DONT_CLOSE_POPUPS`, or-ed together.

    Attributes
    ----------
    span : tuple of float or None
        ``(x, width)`` the highlight covers when
        :data:`SELECTABLE_SPAN_ALL_COLUMNS` is set. Set by the container -- a
        row does not know how wide its table is. ``None`` means "the box I was
        drawn into", which is what a stand-alone selectable wants.
    double_clicked : bool
        Whether the press that was last accepted was a double click.
    """

    def __init__(self, label: str, selected: bool = False, flags: int = SELECTABLE_NONE) -> None:
        self.label = str(label)
        self.selected = bool(selected)
        self.flags = int(flags)
        self.hovered = False
        self.span: tuple[float, float] | None = None
        self.double_clicked = False
        self._held = False

    # ------------------------------------------------------------------ #
    @property
    def disabled(self) -> bool:
        """Whether this row refuses presses and draws dimmed."""
        return bool(self.flags & SELECTABLE_DISABLED)

    @property
    def closes_popup(self) -> bool:
        """Whether pressing this row should close the popup containing it.

        The reference closes the popup on every press unless the row carries
        ``NoAutoClosePopups``; a row that opens a submenu or toggles a filter is
        exactly the case that flag exists for.
        """
        return not (self.flags & SELECTABLE_DONT_CLOSE_POPUPS)

    def _extent(self, x: float, w: float) -> tuple[float, float]:
        """The horizontal extent of the frame: the span, or the box.

        Parameters
        ----------
        x, w : float
            The box the row was given.

        Returns
        -------
        tuple of float
            ``(left, width)``.
        """
        if (self.flags & SELECTABLE_SPAN_ALL_COLUMNS) and self.span is not None:
            return (float(self.span[0]), float(self.span[1]))
        return (x, w)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the highlight, if any, and the caption.

        The highlight colour follows the reference exactly: held *and* hovered
        gives ``HeaderActive``, hovered alone gives ``HeaderHovered``, and a
        row that is merely selected gives ``Header``. A disabled row keeps its
        highlight but at half alpha, which is what the reference's
        ``BeginDisabled`` alpha multiplier amounts to at one level of nesting.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row's box.
        """
        frame_x, frame_w = self._extent(x, w)
        if self.selected or self.hovered:
            if self._held and self.hovered:
                colour: style.Colour = style.HEADER_ACTIVE
            elif self.hovered:
                colour = style.HEADER_HOVERED
            else:
                colour = style.HEADER
            if self.disabled:
                colour = style.with_alpha(colour, _alpha_of(colour) // 2)
            p.fill_rect(frame_x, y, frame_w, h, colour)
        p.push_clip(frame_x, y, frame_w, h)
        room = max(w - 8.0, 1.0)
        p.text(x + 4.0, y, room, h, ALIGN_LEFT | ALIGN_VCENTER,
               style.fit_text(p, self.label, room),
               style.TEXT_DISABLED if self.disabled else style.TEXT)
        p.pop_clip()

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        double: bool = False,
    ) -> bool:
        """Process a press. Returns whether the row reports one.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the row was drawn into.
        double : bool, optional
            Whether this is the second click of a double click. cmtk has no
            click-count feed, so the caller says; a row without
            :data:`SELECTABLE_ALLOW_DOUBLE_CLICK` reports nothing for it, which
            is the reference's behaviour of only generating the extra press when
            the flag asked for it.

        Returns
        -------
        bool
            True when the press was accepted. A disabled row is never accepted
            -- the reference wraps it in ``BeginDisabled``, which blocks the
            button behaviour entirely rather than merely greying the text.
        """
        frame_x, frame_w = self._extent(box_x, box_w)
        if not style.hit(x, y, frame_x, box_y, frame_w, box_h):
            self._held = False
            return False
        if self.disabled:
            self._held = False
            return False
        if double and not (self.flags & SELECTABLE_ALLOW_DOUBLE_CLICK):
            return False
        self._held = True
        self.double_clicked = bool(double)
        return True

    def release(self) -> None:
        """Let go, so the next draw stops using the held colour."""
        self._held = False


class CollapsingHeader:
    """A tree node drawn as a framed bar, optionally with a close button.

    The reference builds this out of ``TreeNodeBehavior`` with the framed flag
    set, so it *is* a :class:`~.widgets.TreeNode` -- same open state, same
    arrow, same toggle-on-click -- wearing a filled ``Header`` frame instead of
    a bare row.

    The close button is the part that is usually got wrong. It is not a second
    open state: it is an out-parameter, ``p_visible``, and the three cases in
    the reference's own comment are the whole contract.

    * no out-parameter: an ordinary header, no button;
    * out-parameter true: a small button on the right, which sets it false;
    * out-parameter false: **the header is not drawn at all**, and neither is
      its body.

    So a closed header is gone, not collapsed, and the caller is the one holding
    the flag that brings it back.

    Parameters
    ----------
    label : str
        The caption.
    expanded : bool, optional
        Whether it starts open.
    closable : bool, optional
        Whether to draw the close button. This is the presence of the
        reference's ``p_visible``, not its value.
    visible : bool, optional
        The value of that out-parameter.
    children : sequence of str, optional
        Body rows, drawn by :meth:`draw_body`.
    """

    def __init__(
        self,
        label: str,
        expanded: bool = False,
        closable: bool = False,
        visible: bool = True,
        children: Sequence[str] | None = None,
    ) -> None:
        self.label = str(label)
        self.expanded = bool(expanded)
        self.closable = bool(closable)
        self.visible = bool(visible)
        self.children: list[str] = [str(one) for one in children] if children else []
        self.hovered = False
        self._held = False

    # ------------------------------------------------------------------ #
    @property
    def body_visible(self) -> bool:
        """Whether the body should be drawn: present *and* open."""
        return self.visible and self.expanded

    def toggle(self) -> bool:
        """Open or close the header, and return the new open state."""
        self.expanded = not self.expanded
        return self.expanded

    def close_box(
        self, box_x: float, box_y: float, box_w: float, box_h: float
    ) -> tuple[float, float, float, float]:
        """Where the close button sits inside a header box.

        Derived from the box alone rather than from a painter measurement, so
        :meth:`press` -- which has no painter -- agrees with :meth:`draw` by
        construction rather than by both being edited together.

        The reference clamps the button's left edge to the header's own left
        edge, so a header narrower than its button still puts the button inside
        itself instead of off to the left.

        Parameters
        ----------
        box_x, box_y, box_w, box_h : float
            The header's box.

        Returns
        -------
        tuple of float
            ``(x, y, w, h)`` of the button.
        """
        size = box_h * 0.7
        pad = box_h * 0.15
        left = max(box_x, box_x + box_w - pad - size)
        return (left, box_y + pad, size, size)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the framed bar, the arrow, the caption and the close button.

        Draws **nothing** when the header has been closed.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The header's box.
        """
        if not self.visible:
            return
        if self._held and self.hovered:
            bg: style.Colour = style.HEADER_ACTIVE
        elif self.hovered:
            bg = style.HEADER_HOVERED
        else:
            bg = style.HEADER
        p.stroke_rect(x, y, w, h, style.BORDER, bg)
        arrow = "v " if self.expanded else "> "
        room = max(w - 8.0, 1.0)
        if self.closable:
            # The reference sets ClipLabelForTrailingButton so the caption stops
            # where the button starts instead of running under it.
            room = max(room - h, 1.0)
        p.push_clip(x, y, w, h)
        p.text(x + 4.0, y, room, h, ALIGN_LEFT | ALIGN_VCENTER,
               style.fit_text(p, f"{arrow}{self.label}", room), style.TEXT, bold=True)
        if self.closable:
            btn_x, btn_y, btn_w, btn_h = self.close_box(x, y, w, h)
            p.stroke_rect(btn_x, btn_y, btn_w, btn_h, style.BORDER, style.BUTTON)
            p.text(btn_x, btn_y, btn_w, btn_h, ALIGN_CENTER, "x", style.TEXT)
        p.pop_clip()

    def draw_body(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the child rows, or nothing when closed or collapsed.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box below the header.
        """
        if not self.body_visible or not self.children:
            return
        row_h = max(h / len(self.children), 1.0)
        p.push_clip(x, y, w, h)
        for index, child in enumerate(self.children):
            room = max(w - 20.0, 1.0)
            p.text(x + 16.0, y + index * row_h, room, row_h, ALIGN_LEFT | ALIGN_VCENTER,
                   style.fit_text(p, child, room), style.DIM)
        p.pop_clip()

    def press(
        self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float
    ) -> bool:
        """Process a press on the header bar.

        A press on the close button clears :attr:`visible` and does **not**
        toggle the open state -- the reference gives the button its own id, so
        the header's own click never sees it.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The header's box.

        Returns
        -------
        bool
            Whether the body should now be drawn, which is what the reference's
            ``CollapsingHeader`` returns: false for a closed header, false for a
            collapsed one, true only when its contents follow.
        """
        if not self.visible:
            return False
        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            self._held = False
            return self.body_visible
        if self.closable and style.hit(x, y, *self.close_box(box_x, box_y, box_w, box_h)):
            self.visible = False
            self._held = False
            return False
        self._held = True
        self.toggle()
        return self.body_visible

    def release(self) -> None:
        """Let go, so the next draw stops using the held colour."""
        self._held = False


class MultiSelectState:
    """Which rows are selected, and the anchor that makes ranges work.

    This is the reference's multi-select storage with the pixels taken out.
    Three rules, and the third is the one that carries the behaviour:

    * a plain click **replaces** the selection with the clicked row;
    * a ctrl-click **toggles** that one row and leaves the rest alone;
    * a shift-click selects the whole run between the *anchor* and the clicked
      row -- and leaves the anchor where it was, so a second shift-click
      re-extends from the same place rather than from the previous click.

    The anchor is ``RangeSrcItem`` in the reference. It is set by the clicks
    that are not shift-clicks, never by a shift-click, and the range runs from
    it to the clicked row **in either direction**: the reference orders the two
    ends when it emits the request (``range_dir > 0 ? (src, dst) : (dst, src)``)
    and keeps the direction beside them. A port that takes the anchor as the
    *lower* end works perfectly until the first shift-click above it, at which
    point it selects nothing at all -- which is why :attr:`direction` is kept
    here even though the selected set does not need it.

    Ctrl+shift is the fourth case and it is not "both of the above": it extends
    the range **without** clearing, and it applies the anchor's own selection
    state (:attr:`range_selected`) to the run, so shift-extending away from an
    unselected anchor *de*-selects. That is the reference's
    ``range_selected = (is_ctrl && RangeSelected != -1) ? RangeSelected : true``.

    Parameters
    ----------
    count : int, optional
        How many rows the list has. Clicks outside ``0..count-1`` do nothing.
    single_select : bool, optional
        The reference's ``SingleSelect`` flag: every click clears first and
        shift does not extend, so at most one row is ever selected.
    """

    def __init__(self, count: int = 0, single_select: bool = False) -> None:
        self.count = int(count)
        self.single_select = bool(single_select)
        self.selected: set[int] = set()
        #: ``RangeSrcItem``: the row a shift-click extends *from*.
        self.range_src: int | None = None
        #: ``RangeSelected``: whether the anchor was selected when it was set.
        self.range_selected = True
        #: ``NavIdItem``: the row last interacted with, which is where
        #: :class:`TypingSelect`'s single-character cycling continues from.
        self.nav_item: int | None = None
        #: ``RangeDirection`` of the last range: ``+1`` down the list, ``-1`` up.
        self.direction = 1

    # ------------------------------------------------------------------ #
    @property
    def anchor(self) -> int | None:
        """The anchor a shift-click extends from; ``None`` before any click."""
        return self.range_src

    def is_selected(self, index: int) -> bool:
        """Whether a row is selected.

        Parameters
        ----------
        index : int
            The row.

        Returns
        -------
        bool
            True when selected.
        """
        return index in self.selected

    def selection(self) -> list[int]:
        """The selected rows, in list order.

        Returns
        -------
        list of int
            Sorted indices.
        """
        return sorted(self.selected)

    def set_count(self, count: int) -> None:
        """Tell the model how long the list is now, dropping rows past the end.

        Parameters
        ----------
        count : int
            The new length.
        """
        self.count = max(int(count), 0)
        self.selected = {i for i in self.selected if i < self.count}
        if self.range_src is not None and self.range_src >= self.count:
            self.range_src = None
        if self.nav_item is not None and self.nav_item >= self.count:
            self.nav_item = None

    def clear(self) -> None:
        """Deselect everything. The reference's ``SetAll(false)``."""
        self.selected.clear()

    def select_all(self) -> None:
        """Select everything. The reference's ``SetAll(true)``."""
        self.selected = set(range(self.count))

    def set_range(self, first: int, last: int, selected: bool) -> None:
        """Select or deselect an inclusive run of rows.

        Parameters
        ----------
        first, last : int
            The ends, in either order -- they are sorted here, which is the
            reference's ordering step at request-emission time.
        selected : bool
            What to set them to.
        """
        low, high = (first, last) if first <= last else (last, first)
        low = int(style.clamp(low, 0, max(self.count - 1, 0)))
        high = int(style.clamp(high, 0, max(self.count - 1, 0)))
        for index in range(low, high + 1):
            if selected:
                self.selected.add(index)
            else:
                self.selected.discard(index)

    # ------------------------------------------------------------------ #
    def click(self, index: int, ctrl: bool = False, shift: bool = False) -> list[int]:
        """Apply a click with its modifiers and return the new selection.

        Parameters
        ----------
        index : int
            The row clicked. Out-of-range indices are ignored.
        ctrl : bool, optional
            Whether ctrl was held. cmtk has no modifier feed, so the caller
            says.
        shift : bool, optional
            Whether shift was held.

        Returns
        -------
        list of int
            The selection afterwards, in list order.
        """
        if not (0 <= index < self.count):
            return self.selection()

        if shift and not self.single_select:
            if self.range_src is None:
                # No anchor yet: the reference assigns the destination as the
                # source, which makes the first shift-click behave as a plain
                # one instead of selecting from nowhere.
                self.range_src = index
                self.range_selected = index in self.selected
            if not ctrl:
                # Mouse press without ctrl clears first; ctrl+shift extends on
                # top of whatever is already selected.
                self.clear()
            # Shift always selects; ctrl+shift copies the anchor's own state, so
            # extending away from an unselected anchor de-selects the run.
            wanted = self.range_selected if ctrl else True
            self.direction = 1 if self.range_src <= index else -1
            self.set_range(self.range_src, index, wanted)
        else:
            if not ctrl or self.single_select:
                self.clear()
            selected = (index not in self.selected) if (ctrl and not self.single_select) else True
            self.range_src = index
            self.direction = 1
            self.set_range(index, index, selected)

        # The reference refreshes RangeSelected from the anchor's actual state
        # every frame; doing it once here is the same thing without the frame.
        if self.range_src is not None:
            self.range_selected = self.range_src in self.selected
        self.nav_item = index
        return self.selection()


class SelectableList:
    """A scrolling list of :class:`Selectable` rows over a multi-selection.

    The scrollbar is :class:`~.widgets.ScrollBar` -- the same one the table and
    the menus use -- because a second scrollbar is a second answer to "where
    does the last row go", and the two do not stay in agreement.

    Parameters
    ----------
    items : sequence of str
        The captions.
    row_scale : float, optional
        Row height as a multiple of the line height, matching
        :class:`~.widgets.Table`.
    multi_select : bool, optional
        False makes it a single-selection list -- the reference's
        ``SingleSelect`` flag, not a different control.
    disabled : sequence of int, optional
        Rows that refuse their clicks and draw dimmed.
    """

    def __init__(
        self,
        items: Sequence[str],
        row_scale: float = 1.15,
        multi_select: bool = True,
        disabled: Sequence[int] | None = None,
    ) -> None:
        self.row_scale = float(row_scale)
        self.bar = ScrollBar()
        self.state = MultiSelectState(0, single_select=not multi_select)
        self.typing = TypingSelect()
        self.rows: list[Selectable] = []
        self.set_items(items, disabled)
        #: Set by :meth:`draw`: ``(x, y, list_w, row_h, visible)``.
        self._geometry: tuple[float, float, float, float, int] | None = None

    # ------------------------------------------------------------------ #
    @property
    def items(self) -> list[str]:
        """The captions, in list order."""
        return [row.label for row in self.rows]

    def set_items(
        self, items: Sequence[str], disabled: Sequence[int] | None = None
    ) -> None:
        """Replace the contents, keeping only the selection that still exists.

        Parameters
        ----------
        items : sequence of str
            The new captions.
        disabled : sequence of int, optional
            Which of them refuse their clicks.
        """
        dead = set(int(one) for one in disabled) if disabled else set()
        self.rows = [
            Selectable(
                label,
                flags=SELECTABLE_SPAN_ALL_COLUMNS
                | (SELECTABLE_DISABLED if index in dead else 0),
            )
            for index, label in enumerate(items)
        ]
        self.state.set_count(len(self.rows))

    def selection(self) -> list[int]:
        """The selected rows, in list order.

        Returns
        -------
        list of int
            Sorted indices.
        """
        return self.state.selection()

    def selected_labels(self) -> list[str]:
        """The captions of the selected rows, in list order.

        Returns
        -------
        list of str
            The captions.
        """
        return [self.rows[index].label for index in self.state.selection()]

    def scroll(self, rows: int) -> int:
        """Move the window by whole rows.

        Parameters
        ----------
        rows : int
            How far, signed.

        Returns
        -------
        int
            The new top row.
        """
        return self.bar.scroll(rows)

    def ensure_visible(self, index: int) -> int:
        """Scroll the window so a row is inside it.

        Parameters
        ----------
        index : int
            The row to bring into view.

        Returns
        -------
        int
            The new top row.
        """
        if self._geometry is None:
            return self.bar.top
        _, _, _, _, visible = self._geometry
        if index < self.bar.top:
            self.bar.top = index
        elif index >= self.bar.top + visible:
            self.bar.top = index - visible + 1
        return self.bar.clamp(len(self.rows), visible)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, the visible rows and the scrollbar.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The list's box.
        """
        row_h = max(p.line_height() * self.row_scale, 1.0)
        visible = max(int(h / row_h), 1)
        self.bar.clamp(len(self.rows), visible)
        list_w = w - (self.bar.width if self.bar.needed() else 0.0)
        self._geometry = (x, y, list_w, row_h, visible)

        p.stroke_rect(x, y, w, h, style.BORDER, style.TABLE_ROW_BG)
        p.push_clip(x, y, list_w, h)
        for offset in range(visible):
            index = self.bar.top + offset
            if index >= len(self.rows):
                break
            row = self.rows[index]
            row.selected = self.state.is_selected(index)
            row.span = (x, list_w)
            row.draw(p, x, y + offset * row_h, list_w, row_h)
        p.pop_clip()
        if self.bar.needed():
            self.bar.draw(p, x + list_w, y, h)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        ctrl: bool = False,
        shift: bool = False,
        double: bool = False,
    ) -> int | None:
        """Process a press, applying the modifiers to the selection.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The list's box.
        ctrl, shift : bool, optional
            The modifiers held, which the caller supplies.
        double : bool, optional
            Whether this is the second click of a double click.

        Returns
        -------
        int or None
            The row the press landed on, or ``None`` for a press that landed on
            the scrollbar, on empty space, or on a disabled row.
        """
        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            return None
        if self.bar.press(x, y):
            return None
        if self._geometry is None:
            return None
        geo_x, geo_y, _list_w, row_h, _visible = self._geometry
        index = self.bar.top + int((y - geo_y) / max(row_h, 1e-6))
        if not (0 <= index < len(self.rows)):
            return None
        row = self.rows[index]
        row_y = geo_y + (index - self.bar.top) * row_h
        if not row.press(x, y, geo_x, row_y, _list_w, row_h, double=double):
            return None
        self.state.click(index, ctrl=ctrl, shift=shift)
        return index

    def type_char(self, ch: str, now: float) -> int | None:
        """Type-ahead: jump the selection to the first row matching what was typed.

        Parameters
        ----------
        ch : str
            The character typed.
        now : float
            The caller's clock, in seconds; the buffer resets after
            :attr:`TypingSelect.timeout` of silence.

        Returns
        -------
        int or None
            The row jumped to, or ``None`` when nothing matched.
        """
        current = self.state.nav_item if self.state.nav_item is not None else -1
        index = self.typing.type_char(ch, self.items, now, current)
        if index is None:
            return None
        self.state.click(index)
        self.ensure_visible(index)
        return index

    def drag(self, y: float) -> bool:
        """Continue a scrollbar drag.

        Parameters
        ----------
        y : float
            Where the pointer is now.

        Returns
        -------
        bool
            Whether the window moved.
        """
        return self.bar.drag(y)

    def release(self) -> None:
        """End a scrollbar drag and let go of every row."""
        self.bar.release()
        for row in self.rows:
            row.release()


class TypingSelect:
    """Type-ahead over a list of names: two modes, not one.

    The obvious behaviour -- accumulate the typed characters and jump to the
    best leading match -- is the reference's ``TypingSelectFindBestLeadingMatch``
    and is only half of it. The other half is what happens when the *same*
    character is pressed again: "b, b, b" does not mean "search for bbb", it
    means "next thing starting with b", and the reference implements that as a
    genuinely separate search (``TypingSelectFindNextSingleCharMatch``) that
    walks past the current row to the following match and wraps.

    A buffer of one character is already in single-character mode -- the
    reference notes that a first keystroke "usually leads to a *next*" -- so the
    mode is decided by whether every character in the buffer is the same one,
    and only a buffer with two *different* characters searches for a prefix.
    After :attr:`single_char_lock_count` repeats the mode **locks**: further
    presses of that character stop growing the buffer at all, so a long run of
    "b" keeps cycling instead of searching for an ever-longer string of b's that
    matches nothing.

    Parameters
    ----------
    timeout : float, optional
        Seconds of silence after which the buffer is forgotten. The reference's
        ``TYPING_SELECT_RESET_TIMER``.
    single_char_lock_count : int, optional
        How many repeats lock single-character mode. The reference's
        ``TYPING_SELECT_SINGLE_CHAR_COUNT_FOR_LOCK``.

    Notes
    -----
    cmtk has no per-frame clock, so ``now`` is an argument to
    :meth:`type_char` rather than something read from a context.
    """

    def __init__(self, timeout: float = 1.8, single_char_lock_count: int = 4) -> None:
        self.timeout = float(timeout)
        self.single_char_lock_count = int(single_char_lock_count)
        self.buffer = ""
        self.single_char_lock = False
        self.single_char_mode = False
        self.last_time = 0.0

    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Forget the buffer. The reference clears it on Escape, Enter and focus loss."""
        self.buffer = ""
        self.single_char_lock = False
        self.single_char_mode = False

    def _accumulate(self, ch: str, now: float) -> bool:
        """Fold one character into the buffer.

        Parameters
        ----------
        ch : str
            The character. Control characters and a leading blank are ignored,
            as in the reference.
        now : float
            The caller's clock.

        Returns
        -------
        bool
            Whether a search should be run.
        """
        if not ch or len(ch) != 1 or ch < " " or ch == "\x7f":
            return False
        if self.buffer and now - self.last_time > self.timeout:
            self.reset()
        if not self.buffer and ch.isspace():
            return False
        self.last_time = float(now)
        if self.single_char_lock:
            if ch.upper() == self.buffer[:1].upper():
                # Same character while locked: search again, do not grow.
                return True
            self.reset()
            self.last_time = float(now)
        self.buffer += ch
        return True

    def type_char(
        self, ch: str, items: Sequence[str], now: float, current: int = -1
    ) -> int | None:
        """Feed one typed character and return the row to jump to.

        Parameters
        ----------
        ch : str
            The character typed.
        items : sequence of str
            The names to search.
        now : float
            The caller's clock, in seconds.
        current : int, optional
            The row the list is on, which single-character cycling continues
            *after*. ``-1`` means "no current row", and the first match is
            returned immediately.

        Returns
        -------
        int or None
            The matching row, or ``None`` when nothing matched.
        """
        if not self._accumulate(ch, now):
            return None
        head = self.buffer[0]
        repeated = all(one.upper() == head.upper() for one in self.buffer)
        self.single_char_mode = repeated or self.single_char_lock
        if repeated and len(self.buffer) >= self.single_char_lock_count:
            self.single_char_lock = True
        if self.single_char_mode:
            return self.find_next_single_char(head, items, current)
        return self.find_best_leading(self.buffer, items)

    # ------------------------------------------------------------------ #
    @staticmethod
    def find_best_leading(prefix: str, items: Sequence[str]) -> int | None:
        """The row whose name shares the longest leading run with ``prefix``.

        Parameters
        ----------
        prefix : str
            The typed buffer.
        items : sequence of str
            The names.

        Returns
        -------
        int or None
            The best row, or ``None`` when no name matched even one character.
            The first full-length match wins outright, which is the reference's
            early break.
        """
        best_index: int | None = None
        best_len = 0
        for index, name in enumerate(items):
            length = _match_len(prefix, name)
            if length <= best_len:
                continue
            best_index, best_len = index, length
            if length == len(prefix):
                break
        return best_index

    @staticmethod
    def find_next_single_char(
        ch: str, items: Sequence[str], current: int = -1
    ) -> int | None:
        """The next row starting with ``ch`` after ``current``, wrapping.

        Parameters
        ----------
        ch : str
            The character.
        items : sequence of str
            The names.
        current : int, optional
            Where to continue from. ``-1`` returns the first match.

        Returns
        -------
        int or None
            The row, or ``None`` when nothing starts with ``ch``.
        """
        first: int | None = None
        take_next = False
        for index, name in enumerate(items):
            if _match_len(ch, name) < 1:
                continue
            if take_next:
                return index
            if first is None and current == -1:
                return index
            if first is None:
                first = index
            if index == current:
                take_next = True
        return first

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the accumulated buffer as a small badge.

        Drawn only for a *multi-character* buffer: the reference notes that in
        single-character mode it is better **not** to show an indicator, because
        the buffer then says "bbb" while what the user did was press "b" three
        times, and showing that reads as a bug in the search rather than as the
        cycling it is.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The badge's box.
        """
        if not self.buffer or self.single_char_mode:
            return
        p.stroke_rect(x, y, w, h, style.BORDER, style.POPUP_BG)
        room = max(w - 8.0, 1.0)
        p.text(x + 4.0, y, room, h, ALIGN_LEFT | ALIGN_VCENTER,
               style.fit_text(p, self.buffer, room), style.GOLD)
