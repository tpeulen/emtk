"""The combo box: a framed preview that opens a list you pick from.

Why this module exists beside ``widgets.Combo``
-----------------------------------------------
:class:`~.widgets.Combo` is a *spinner*. It draws ``label: < value >`` and its
press moves to the next option, so the whole set of choices is only ever
visible one at a time and picking the fifth of six means pressing four times.
That is a legitimate compact control -- it costs one row and no popup, which is
what a dense settings panel wants -- and it has callers, so it stays exactly as
it is.

It is not what the reference implementation calls a combo. ``BeginCombo`` draws
a framed preview with an arrow button, and clicking it **opens a list**: every
option at once, one press to pick any of them, the current one highlighted and
scrolled into view. That control had no counterpart here, and it is the last
section of the reference's widget stack that did not.

What was taken from the reference
---------------------------------
* **The closed frame's layout**, from ``BeginCombo``: the frame is split at
  ``value_x2 = max(bb.Min.x, bb.Max.x - arrow_size)`` into a preview drawn in
  ``FrameBg`` and an arrow button drawn in ``Button``/``ButtonHovered``, with
  the whole thing outlined afterwards and the label drawn *outside* the frame
  on the right. ``arrow_size`` is the frame height, which is why the arrow
  button is square.
* **The height flags**, from ``BeginComboPopup`` and
  ``CalcMaxPopupHeightFromItemCount``. These cap the popup's height *in items*
  and the default is **not** "all of them": ``HeightRegular`` (8) is applied
  when no height flag is given, ``HeightSmall`` is 4, ``HeightLarge`` is 20,
  and only ``HeightLargest`` passes ``-1`` -- the ``items_count <= 0`` case
  that returns ``FLT_MAX`` and means "as many as fit". Anything past the cap is
  still reachable; it is *scrolled*, not dropped.
* **The width rule**: ``constraint_min.x = w`` -- the popup is at least as wide
  as the frame that opened it, and wider when an option needs it. A popup
  narrower than its own combo reads as a different control having opened.
* **The placement**, through :func:`~.menus.best_popup_pos`, with the frame as
  the rectangle to avoid: below the frame by preference, flipped above it when
  the frame is near the bottom of the viewport.
  ``ImGuiComboFlags_PopupAlignLeft`` is the reference's ``ImGuiDir_Left`` --
  "below, toward left" -- and is expressed here as the reference expresses it,
  by anchoring the popup's *right* edge to the frame's rather than its left.
  The reference **always overrides** its remembered direction for a combo
  ("not to leave a chance for a past value to affect us"), so nothing is
  carried between openings and a popup that once flipped up does not stay up
  once there is room below.
* **``SetItemDefaultFocus``**: opening a list on a selection near its end
  shows that selection, not the top of the list.

What was deliberately skipped
-----------------------------
* **``ImGuiComboFlags_CustomPreview``** and the ``BeginComboPreview`` /
  ``EndComboPreview`` pair. They exist so arbitrary widgets can be drawn inside
  the preview box by re-pointing the layout cursor at it, which needs the
  reference's per-frame cursor; cmtk has no such cursor, and the flag is
  marked experimental in the reference itself.
* **The list clipper.** ``Combo()`` runs an ``ImGuiListClipper`` so a
  hundred-thousand-item combo only lays out what is on screen. Here only the
  visible window is ever drawn anyway, which is the same saving without the
  machinery.
* **Keyboard navigation and the nav cursor** (``RenderNavCursor``), for the
  reason the rest of this package skips them: they read a global input context
  that would be a second paradigm beside the retained controls.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from .. import style
from .menus import best_popup_pos
from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter
from .selection import SELECTABLE_SPAN_ALL_COLUMNS, Selectable
from .basic import ScrollBar

__all__ = [
    "COMBO_NONE",
    "COMBO_POPUP_ALIGN_LEFT",
    "COMBO_HEIGHT_SMALL",
    "COMBO_HEIGHT_REGULAR",
    "COMBO_HEIGHT_LARGE",
    "COMBO_HEIGHT_LARGEST",
    "COMBO_HEIGHT_MASK",
    "COMBO_NO_ARROW_BUTTON",
    "COMBO_NO_PREVIEW",
    "COMBO_WIDTH_FIT_PREVIEW",
    "PAD",
    "FRAME_PAD",
    "INNER_SPACING",
    "ROW_SCALE",
    "ComboPress",
    "ComboBox",
]

#: No flags. The reference's ``ImGuiComboFlags_None``.
COMBO_NONE = 0
#: Anchor the popup's right edge to the frame's rather than its left, so it
#: grows leftward when it is wider than the frame. The reference's
#: ``PopupAlignLeft``, which it implements as the ``ImGuiDir_Left`` placement
#: ("below, toward left").
COMBO_POPUP_ALIGN_LEFT = 1 << 0
#: At most ~4 items visible at once; the rest are scrolled to.
COMBO_HEIGHT_SMALL = 1 << 1
#: At most ~8 items visible at once. **This is the default** -- a combo with no
#: height flag is given this one, so a twenty-option combo scrolls rather than
#: opening a twenty-row panel.
COMBO_HEIGHT_REGULAR = 1 << 2
#: At most ~20 items visible at once.
COMBO_HEIGHT_LARGE = 1 << 3
#: As many items as fit in the viewport, with no count of its own. The
#: reference's ``-1`` item count, which is the ``FLT_MAX`` branch of
#: ``CalcMaxPopupHeightFromItemCount``.
COMBO_HEIGHT_LARGEST = 1 << 4
#: Draw the preview without the arrow button beside it.
COMBO_NO_ARROW_BUTTON = 1 << 5
#: Draw *only* the square arrow button, with no preview of the current value.
#: Cannot be combined with :data:`COMBO_NO_ARROW_BUTTON`; the reference asserts
#: on the pair, and a control that draws neither half is invisible.
COMBO_NO_PREVIEW = 1 << 6
#: Size the frame from the preview text instead of from the box it is given.
COMBO_WIDTH_FIT_PREVIEW = 1 << 7
#: The four height flags. The reference's ``ImGuiComboFlags_HeightMask_``.
COMBO_HEIGHT_MASK = (
    COMBO_HEIGHT_SMALL | COMBO_HEIGHT_REGULAR | COMBO_HEIGHT_LARGE | COMBO_HEIGHT_LARGEST
)

#: How many items each height flag allows. ``None`` is the reference's
#: ``FLT_MAX``: no cap of its own, so the viewport is the only limit.
_HEIGHT_ITEMS: dict[int, int | None] = {
    COMBO_HEIGHT_SMALL: 4,
    COMBO_HEIGHT_REGULAR: 8,
    COMBO_HEIGHT_LARGE: 20,
    COMBO_HEIGHT_LARGEST: None,
}

#: The popup's own padding above and below its rows. The reference's
#: ``WindowPadding.y``, which is what ``CalcMaxPopupHeightFromItemCount`` adds
#: twice on top of the rows themselves.
PAD = 6.0

#: Padding between the frame's edge and the preview text. The reference's
#: ``FramePadding.x``, which it also uses as the popup's horizontal padding so
#: an option in the list sits directly under the preview of itself.
FRAME_PAD = 4.0

#: Gap between the frame and the label drawn after it. The reference's
#: ``ItemInnerSpacing.x``.
INNER_SPACING = 4.0

#: A popup row's height, as a multiple of the painter's line height. The
#: reference's row is ``FontSize + ItemSpacing.y``, which at its own defaults
#: (13 and 4) is this ratio.
ROW_SCALE = 1.3

#: The inset :class:`~.selection.Selectable` draws its caption at, either side.
#: Used to size the popup wide enough for its longest option rather than
#: measuring the row and finding out it was clipped.
_ROW_INSET = 8.0

#: Stands in for the reference's ``FLT_MAX`` on the axis a frame is unbounded
#: along. A real number and never ``inf``, for the reason
#: :func:`~.menus.best_popup_pos` gives: ``inf - inf`` is a NaN that compares
#: false against every bound, which places a panel at infinity instead of
#: rejecting a direction.
_FAR = 1.0e9

#: The viewport a combo assumes until a host calls :meth:`ComboBox.set_viewport`:
#: large enough that the popup never flips, small enough to stay below
#: :data:`_FAR`.
_UNBOUNDED = (1.0e6, 1.0e6)


class ComboPress(NamedTuple):
    """What a combo did with one press.

    Four questions rather than one return value, because a host needs all four
    and cannot recover any of them from the others: *which row was picked*,
    *did the value actually move*, *may the press also reach the scene behind*,
    and *is the popup still up*.

    Attributes
    ----------
    index : int or None
        The row picked, or ``None`` for every other outcome -- a press that
        opened the popup, one that landed on the scrollbar, one that dismissed
        the popup, and one that missed the control entirely.
    changed : bool
        Whether the selection moved. Picking the row that was already selected
        reports an ``index`` but no change, which is the reference's
        ``value_changed = ... && *current_item != i``.
    consumed : bool
        Whether the press belongs to this control and must not be passed on. A
        press *outside* an open popup is not consumed: as with a plain popup in
        the reference, the click that dismisses it still reaches what is behind.
    closed : bool
        Whether the popup went away as a result.
    """

    index: int | None
    changed: bool
    consumed: bool
    closed: bool


#: The answer when a press had nothing to do with the control at all.
_IGNORED = ComboPress(None, False, False, False)


class ComboBox:
    """A framed preview of the current value that opens a list of the options.

    Parameters
    ----------
    label : str
        Caption drawn *after* the frame, as the reference draws it. It is not
        part of the frame, so a press on the label is not a press on the combo.
    options : sequence of str
        The choices, in the order they are listed.
    index : int, optional
        Which one is current. Clamped to the options.
    flags : int, optional
        Any of :data:`COMBO_POPUP_ALIGN_LEFT`, the four ``COMBO_HEIGHT_*``,
        :data:`COMBO_NO_ARROW_BUTTON`, :data:`COMBO_NO_PREVIEW` and
        :data:`COMBO_WIDTH_FIT_PREVIEW`, or-ed together.

    Attributes
    ----------
    open : bool
        Whether the list is down.
    hovered : bool
        Set by a host that has hover information; brightens the frame. Nothing
        here sets it, because nothing here reads the pointer between presses.
    viewport : tuple of float
        ``(width, height)`` the popup must stay inside, as
        :meth:`set_viewport` sets it. Until then it is large enough that the
        popup never flips.
    last_dir : str or None
        Which way the popup went last time it was placed, as
        :func:`~.menus.best_popup_pos` reports it. An *output*: the reference
        overrides the remembered direction on every opening of a combo, so it
        is never fed back in.
    bar : ScrollBar
        The list's scrollbar -- the shared one, so the last row lands where it
        does in every other scrolling control here.
    """

    def __init__(
        self,
        label: str,
        options: Sequence[str],
        index: int = 0,
        flags: int = COMBO_NONE,
    ) -> None:
        self.label = str(label)
        self.flags = int(flags)
        self.open = False
        self.hovered = False
        self.viewport: tuple[float, float] = _UNBOUNDED
        self.last_dir: str | None = None
        self.bar = ScrollBar()
        self.rows: list[Selectable] = []
        self.index = 0
        self.set_options(options, index)
        #: Whether the next draw must scroll the selection into view. The
        #: reference's ``SetItemDefaultFocus``, deferred because how many rows
        #: fit is only known once there is a painter to measure with.
        self._focus_selected = True
        self._frame: tuple[float, float, float, float] | None = None
        self._popup: tuple[float, float, float, float] | None = None
        #: Set by :meth:`draw` while open: ``(x, top, list_w, row_h, visible)``.
        self._geometry: tuple[float, float, float, float, int] | None = None

    # ------------------------------------------------------------------ #
    @property
    def value(self) -> str:
        """The current option, or ``""`` when there are none."""
        return self.rows[self.index].label if self.rows else ""

    @property
    def options(self) -> list[str]:
        """The choices, in list order."""
        return [row.label for row in self.rows]

    @property
    def max_items(self) -> int | None:
        """How many rows the height flags allow the popup to show.

        Returns
        -------
        int or None
            The cap, or ``None`` for :data:`COMBO_HEIGHT_LARGEST`, which has no
            cap of its own. A combo carrying no height flag is given
            :data:`COMBO_HEIGHT_REGULAR`, exactly as ``BeginComboPopup`` does.
        """
        height = self.flags & COMBO_HEIGHT_MASK
        if height == 0:
            height = COMBO_HEIGHT_REGULAR
        # Only one height flag is meaningful; the reference asserts on that and
        # then reads them in a fixed order. The lowest set bit is that order.
        for flag in (
            COMBO_HEIGHT_SMALL,
            COMBO_HEIGHT_REGULAR,
            COMBO_HEIGHT_LARGE,
            COMBO_HEIGHT_LARGEST,
        ):
            if height & flag:
                return _HEIGHT_ITEMS[flag]
        return _HEIGHT_ITEMS[COMBO_HEIGHT_REGULAR]

    @property
    def popup_rect(self) -> tuple[float, float, float, float] | None:
        """Where the popup was last painted, as ``(x, y, w, h)``, or ``None``.

        Placement happens at draw time, because that is the only moment the
        popup's width is known, so this is the answer to "did it flip".
        """
        return self._popup

    @property
    def frame_rect(self) -> tuple[float, float, float, float] | None:
        """Where the closed frame was last painted, as ``(x, y, w, h)``.

        Narrower than the box handed to :meth:`draw` whenever there is a label
        or :data:`COMBO_NO_PREVIEW` / :data:`COMBO_WIDTH_FIT_PREVIEW` is set,
        and it is the frame -- not the box -- that a press must hit.
        """
        return self._frame

    # ------------------------------------------------------------------ #
    def set_options(self, options: Sequence[str], index: int | None = None) -> None:
        """Replace the choices.

        Parameters
        ----------
        options : sequence of str
            The new choices.
        index : int, optional
            Which one to select; the current index is kept (and clamped) when
            omitted.
        """
        self.rows = [
            Selectable(str(one), flags=SELECTABLE_SPAN_ALL_COLUMNS) for one in options
        ]
        self.select(self.index if index is None else index)
        self.bar.top = 0

    def select(self, index: int) -> str:
        """Make an option current, by index.

        Parameters
        ----------
        index : int
            The row, clamped to the options.

        Returns
        -------
        str
            The option now current.
        """
        if not self.rows:
            self.index = 0
            return ""
        self.index = int(style.clamp(int(index), 0, len(self.rows) - 1))
        return self.value

    def set_viewport(self, width: float, height: float) -> None:
        """Tell the combo where the edges its popup must stay inside are.

        Parameters
        ----------
        width, height : float
            The viewport, in the same space the boxes are given in.
        """
        self.viewport = (float(width), float(height))

    def open_popup(self) -> None:
        """Put the list down, scrolled so the current option is in view."""
        self.open = True
        self.last_dir = None
        self._focus_selected = True

    def close(self) -> None:
        """Put the list away, leaving the selection where it is."""
        self.open = False
        self.bar.release()
        for row in self.rows:
            row.release()

    def contains(self, x: float, y: float) -> bool:
        """Whether a point is on the frame or anywhere in the open popup.

        A pure query: unlike :meth:`press` it changes nothing, so a host can ask
        "is the pointer over the chrome" without dismissing the popup by asking.

        Parameters
        ----------
        x, y : float
            The point.

        Returns
        -------
        bool
            True if the point is over the control.
        """
        if self._frame is not None and style.hit(x, y, *self._frame):
            return True
        return bool(self.open and self._popup is not None and style.hit(x, y, *self._popup))

    # ------------------------------------------------------------------ #
    def frame_width(self, p: Painter, w: float, h: float) -> float:
        """How wide the framed part of the control is inside a box of width ``w``.

        The reference computes this as ``arrow_size`` for
        :data:`COMBO_NO_PREVIEW`, ``arrow_size + preview + 2 * FramePadding.x``
        for :data:`COMBO_WIDTH_FIT_PREVIEW`, and ``CalcItemWidth()`` otherwise
        -- an item width that does not include the label, which is drawn past
        the frame's right edge. Here the box *does* include the label, so the
        label's room is taken off it.

        Parameters
        ----------
        p : Painter
            Used to measure.
        w, h : float
            The box's width and height.

        Returns
        -------
        float
            The frame's width, never less than the arrow button's.
        """
        arrow = self.arrow_size(h)
        if self.flags & COMBO_NO_PREVIEW:
            return max(arrow, 1.0)
        if self.flags & COMBO_WIDTH_FIT_PREVIEW:
            return max(arrow + p.text_width(self.value) + 2.0 * FRAME_PAD, 1.0)
        if self.label:
            return max(w - (p.text_width(self.label) + INNER_SPACING), arrow, 1.0)
        return max(w, 1.0)

    def arrow_size(self, h: float) -> float:
        """Measure the arrow button: the frame's height, or zero without one.

        Parameters
        ----------
        h : float
            The frame's height.

        Returns
        -------
        float
            The width. The button is square, which is why this is ``h``.
        """
        return 0.0 if self.flags & COMBO_NO_ARROW_BUTTON else float(h)

    def popup_metrics(self, p: Painter, frame_w: float) -> tuple[float, float, float, int]:
        """Measure the popup: how wide, how tall, and how many rows it shows.

        The item cap comes from the height flags (:attr:`max_items`) and the
        viewport caps it again, which is the whole of "as many fitting items as
        possible". The width is the reference's ``constraint_min.x = w``: at
        least the frame, and wider when an option needs it.

        Parameters
        ----------
        p : Painter
            Used to measure.
        frame_w : float
            The frame's width, which is the popup's minimum.

        Returns
        -------
        tuple
            ``(width, height, row_h, visible)``.
        """
        row_h = max(p.line_height() * ROW_SCALE, 1.0)
        _view_w, view_h = self.viewport
        fits = max(int((view_h - 2.0 * PAD) // row_h), 1)
        cap = self.max_items
        visible = min(len(self.rows), fits) if cap is None else min(len(self.rows), cap, fits)
        visible = max(visible, 1)
        scrolling = len(self.rows) > visible
        longest = max((p.text_width(row.label) for row in self.rows), default=0.0)
        content = longest + _ROW_INSET + (self.bar.width if scrolling else 0.0)
        width = max(frame_w, content)
        height = row_h * visible + 2.0 * PAD
        return (width, height, row_h, visible)

    def ensure_visible(self, index: int, visible: int) -> int:
        """Scroll the list so a row is inside the window.

        Parameters
        ----------
        index : int
            The row to bring into view.
        visible : int
            How many rows the window shows.

        Returns
        -------
        int
            The new top row.
        """
        if index < self.bar.top:
            self.bar.top = index
        elif index >= self.bar.top + visible:
            self.bar.top = index - visible + 1
        return self.bar.clamp(len(self.rows), visible)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, its label, and the list when it is open.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The control's box. The *frame* may be narrower than it -- see
            :meth:`frame_width` -- and the popup is not inside it at all.
        """
        arrow = self.arrow_size(h)
        frame_w = self.frame_width(p, w, h)
        self._frame = (x, y, frame_w, h)
        # The reference's split point: everything left of it is the preview,
        # everything right of it is the arrow button.
        value_x2 = max(x, x + frame_w - arrow)

        if not (self.flags & COMBO_NO_PREVIEW):
            p.fill_rect(x, y, value_x2 - x, h,
                        style.FRAME_BG_HOVERED if self.hovered else style.FRAME_BG)
        if not (self.flags & COMBO_NO_ARROW_BUTTON):
            lit = self.open or self.hovered
            p.fill_rect(value_x2, y, x + frame_w - value_x2, h,
                        style.BUTTON_HOVERED if lit else style.BUTTON)
            # The reference draws the arrow only when there is room for it, so
            # a frame narrower than its own button shows the button and no mark
            # rather than a mark hanging outside the frame.
            if value_x2 + arrow - FRAME_PAD <= x + frame_w:
                p.text(value_x2, y, arrow, h, ALIGN_CENTER, "▼", style.TEXT)
        p.stroke_rect(x, y, frame_w, h, style.BORDER, None)

        if not (self.flags & COMBO_NO_PREVIEW):
            room = max(value_x2 - x - 2.0 * FRAME_PAD, 1.0)
            p.push_clip(x, y, max(value_x2 - x, 0.0), h)
            try:
                p.text(x + FRAME_PAD, y, room, h, ALIGN_LEFT | ALIGN_VCENTER,
                       style.fit_text(p, self.value, room), style.TEXT)
            finally:
                p.pop_clip()

        if self.label:
            left = x + frame_w + INNER_SPACING
            room = max(x + w - left, 1.0)
            p.text(left, y, room, h, ALIGN_LEFT | ALIGN_VCENTER,
                   style.fit_text(p, self.label, room), style.TEXT)

        if self.open:
            self._draw_popup(p, x, y, frame_w, h)

    def _draw_popup(
        self, p: Painter, frame_x: float, frame_y: float, frame_w: float, frame_h: float
    ) -> None:
        """Place and paint the list that hangs off the frame.

        Parameters
        ----------
        p : Painter
            The surface.
        frame_x, frame_y, frame_w, frame_h : float
            The frame, as just drawn.
        """
        width, height, row_h, visible = self.popup_metrics(p, frame_w)
        view_w, view_h = self.viewport
        # The frame is what the popup must not cover, unbounded left and right
        # -- which is what rules the sideways directions out and leaves "below
        # the frame" and, when there is no room, "above" it.
        avoid = (-_FAR, frame_y, _FAR, frame_y + frame_h)
        ref_x = (
            frame_x + frame_w - width
            if self.flags & COMBO_POPUP_ALIGN_LEFT
            else frame_x
        )
        # No remembered direction is fed in: the reference overrides it on every
        # opening of a combo, so a popup that once flipped up does not stay up
        # after the frame has moved away from the bottom edge.
        pos_x, pos_y, self.last_dir = best_popup_pos(
            (ref_x, frame_y), (width, height), (0.0, 0.0, view_w, view_h), avoid, None
        )
        self._popup = (pos_x, pos_y, width, height)

        self.bar.clamp(len(self.rows), visible)
        if self._focus_selected and self.rows:
            self.ensure_visible(self.index, visible)
            self._focus_selected = False
        list_w = width - (self.bar.width if self.bar.needed() else 0.0)
        top = pos_y + PAD
        body_h = row_h * visible
        self._geometry = (pos_x, top, list_w, row_h, visible)

        p.stroke_rect(pos_x, pos_y, width, height, style.BORDER, style.POPUP_BG)
        p.push_clip(pos_x, top, list_w, body_h)
        try:
            for offset in range(visible):
                index = self.bar.top + offset
                if index >= len(self.rows):
                    break
                row = self.rows[index]
                row.selected = index == self.index
                row.span = (pos_x, list_w)
                row.draw(p, pos_x, top + offset * row_h, list_w, row_h)
        finally:
            p.pop_clip()
        if self.bar.needed():
            self.bar.draw(p, pos_x + list_w, top, body_h)

    # ------------------------------------------------------------------ #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> ComboPress:
        """Process a press against the frame and, when it is open, the list.

        The popup is tested **first**: it is painted over whatever is behind it,
        including the frame it came from when the frame is near the bottom edge
        and the popup flipped up over it.

        Parameters
        ----------
        x, y : float
            The press. It need not be inside the box -- the popup is outside it
            by definition.
        box_x, box_y, box_w, box_h : float
            The control's box, as handed to :meth:`draw`. Only the *frame* part
            of it opens the popup; the frame is taken from the last draw, and
            the whole box stands in for it before the first one.

        Returns
        -------
        ComboPress
            ``index`` is the row picked, if any.
        """
        frame = self._frame or (box_x, box_y, box_w, box_h)

        if self.open:
            if self.bar.press(x, y):
                return ComboPress(None, False, True, False)
            if self._popup is not None and style.hit(x, y, *self._popup):
                picked = self._press_row(x, y)
                if picked is None:
                    # Inside the panel but on no row: the padding, or a gap
                    # under a list shorter than its window. It is still the
                    # popup's press, so it must not reach the scene behind.
                    return ComboPress(None, False, True, False)
                changed = picked != self.index
                self.index = picked
                self.close()
                return ComboPress(picked, changed, True, True)
            # Outside the popup. A press on the frame closes it and is the
            # control's; a press anywhere else closes it and is not, exactly as
            # a plain popup in the reference lets the dismissing click through.
            self.close()
            return ComboPress(None, False, style.hit(x, y, *frame), True)

        if style.hit(x, y, *frame):
            self.open_popup()
            return ComboPress(None, False, True, False)
        return _IGNORED

    def _press_row(self, x: float, y: float) -> int | None:
        """Which row of the open list a press landed on.

        Parameters
        ----------
        x, y : float
            The press, already known to be inside the panel.

        Returns
        -------
        int or None
            The row, or ``None`` for a press on the padding or past the last
            row. The row itself is asked, so a disabled one refuses.
        """
        if self._geometry is None:
            return None
        geo_x, top, list_w, row_h, _visible = self._geometry
        index = self.bar.top + int((y - top) // row_h)
        if not (0 <= index < len(self.rows)):
            return None
        row_y = top + (index - self.bar.top) * row_h
        if not self.rows[index].press(x, y, geo_x, row_y, list_w, row_h):
            return None
        return index

    def scroll(self, rows: int) -> int:
        """Move the open list's window by whole rows.

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
