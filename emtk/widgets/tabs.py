"""A tab strip whose tabs are as wide as their labels.

Why this is not :class:`~emtk.widgets.basic.Tabs`
--------------------------------------------------------
:class:`~emtk.widgets.basic.Tabs` divides its box into *N* equal
slices. That is the right amount of machinery for a three-way view switch, and
the wrong amount for anything that holds documents: an equal slice is decided
by the tab *count*, so adding a ninth tab makes the other eight narrower, and
the longest caption in the set decides whether the whole row is legible. Nine
tabs called "1" through "9" get the same width as nine file names.

The reference implementation measures each tab instead, lays them end to end,
and then deals with the case they do not fit -- which is the interesting half
and the reason this module exists:

* **shrink**, taking the width from the *widest* tab first rather than scaling
  everything down together (:func:`shrink_widths`). Three tabs of 20, 20 and
  153 pixels squeezed into 150 do not become 15, 15 and 114: the two short ones
  are already short, so they keep their width and the long one pays the whole
  51 pixels. This is the whole point of the policy and it is what a uniform
  scale gets wrong;
* **scroll**, when shrinking is either not enough or not wanted, with the
  selected tab kept inside the visible extent and a pair of arrows that step
  the selection along;
* **reorder**, by dragging a tab past its neighbour.

What was left in the reference
------------------------------
The reference splits its tabs into three sections -- leading, central and
trailing -- so that pinned tabs can sit at either end and only the middle
scrolls. That is a docking-host feature; this port has one section, which
collapses ``TabBarLayout``'s three-section bookkeeping into a single run and
makes ``TabBarScrollToTab``'s "positions relative to section 0" arithmetic a
no-op. The animated scroll (``ScrollingAnim`` sweeping towards
``ScrollingTarget`` at a speed chosen to arrive in a third of a second) is also
gone: the chrome repaints on change rather than every frame, so an animation
would either stall halfway or force the repaint it was designed to avoid.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from functools import cmp_to_key
from typing import NamedTuple

from .. import style
from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter

__all__ = [
    "TAB_BAR_NONE",
    "TAB_BAR_REORDERABLE",
    "TAB_BAR_AUTO_SELECT_NEW_TABS",
    "TAB_BAR_TAB_LIST_POPUP_BUTTON",
    "TAB_BAR_NO_CLOSE_WITH_MIDDLE_MOUSE_BUTTON",
    "TAB_BAR_NO_TAB_LIST_SCROLLING_BUTTONS",
    "TAB_BAR_FITTING_POLICY_RESIZE_DOWN",
    "TAB_BAR_FITTING_POLICY_SCROLL",
    "TAB_BAR_FITTING_POLICY_MASK",
    "TAB_BAR_FITTING_POLICY_DEFAULT",
    "PAD_X",
    "TAB_SPACING",
    "SHRINK_MIN_WIDTH",
    "MAX_TAB_WIDTH_EM",
    "shrink_widths",
    "TabPress",
    "TabItem",
    "TabItemButton",
    "TabBar",
]


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------
# Bit positions follow the reference's ``ImGuiTabBarFlags_`` so a port can be
# checked against the source it came from by reading down the column.
#: No flags.
TAB_BAR_NONE = 0
#: Tabs may be dragged past one another to change their order.
TAB_BAR_REORDERABLE = 1 << 0
#: A tab added with :meth:`TabBar.add` becomes the selected one.
TAB_BAR_AUTO_SELECT_NEW_TABS = 1 << 1
#: Put a drop-down at the left of the strip listing every tab. It takes its
#: width out of the strip, which is the part that changes the layout.
TAB_BAR_TAB_LIST_POPUP_BUTTON = 1 << 2
#: Middle-clicking a closable tab does *not* close it.
TAB_BAR_NO_CLOSE_WITH_MIDDLE_MOUSE_BUTTON = 1 << 3
#: Do not put the two stepping arrows at the right of the strip. Only means
#: anything under :data:`TAB_BAR_FITTING_POLICY_SCROLL`.
TAB_BAR_NO_TAB_LIST_SCROLLING_BUTTONS = 1 << 4
#: Tabs that do not fit are shrunk, widest first.
TAB_BAR_FITTING_POLICY_RESIZE_DOWN = 1 << 8
#: Tabs that do not fit keep their width and the strip scrolls.
TAB_BAR_FITTING_POLICY_SCROLL = 1 << 9
#: The two policies, for testing whether one was asked for at all.
TAB_BAR_FITTING_POLICY_MASK = (
    TAB_BAR_FITTING_POLICY_RESIZE_DOWN | TAB_BAR_FITTING_POLICY_SCROLL
)
#: What a bar gets when it asks for neither.
TAB_BAR_FITTING_POLICY_DEFAULT = TAB_BAR_FITTING_POLICY_RESIZE_DOWN


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
#: Horizontal padding inside a tab, each side (the reference's
#: ``style.FramePadding.x``).
PAD_X = 6.0
#: Gap between two tabs (the reference's ``style.ItemInnerSpacing.x``).
TAB_SPACING = 4.0
#: How narrow shrinking is allowed to make a tab.
SHRINK_MIN_WIDTH = 1.0
#: The widest a tab may measure, as a multiple of the line height. The
#: reference's ``TabBarCalcMaxTabWidth`` is ``FontSize * 20``.
MAX_TAB_WIDTH_EM = 20.0


def _shrink_comparer(a: list[float], b: list[float]) -> int:
    """Order two shrink entries largest-first, as the reference does.

    Parameters
    ----------
    a, b : list
        ``[width, initial_width, index]`` entries.

    Returns
    -------
    int
        Negative, zero or positive in the usual comparison sense.

    Notes
    -----
    The reference truncates the width difference to an ``int`` before testing
    it, so two widths less than a pixel apart compare *equal* and the tie is
    settled by descending index. Ported as written: it decides which of two
    near-identical tabs gives up its pixel first, and a "cleaner" float compare
    would silently disagree with the source this was checked against.
    """
    diff = int(b[0] - a[0])
    if diff:
        return diff
    return b[2] - a[2]


def shrink_widths(
    widths: Sequence[float],
    excess: float,
    width_min: float = SHRINK_MIN_WIDTH,
) -> list[float]:
    """Take ``excess`` pixels out of a set of widths, widest first.

    Parameters
    ----------
    widths : sequence of float
        The wanted widths, in layout order.
    excess : float
        How much total width has to go.
    width_min : float, optional
        How narrow any one entry may end up.

    Returns
    -------
    list of float
        The widths, in the same order they came in.

    Notes
    -----
    This is the reference's ``ShrinkWidths`` and the reason a measured tab bar
    is worth having. It repeatedly finds the *widest* entries, works out how
    much it can take from them before they are no wider than the next one down,
    and takes at most that -- so width comes off the long tabs until they are
    as short as the short ones, and only then does everybody shrink together.
    Scaling every width by the same factor gives a visibly different answer:
    it makes an already-short tab shorter to spare a long one.

    The tail of the function truncates each width to whole pixels and hands the
    accumulated fractions back out one at a time, so the right-hand edge of the
    last tab lands exactly where the strip ends rather than a rounding error
    short of it.
    """
    count = len(widths)
    if count == 0:
        return []
    items = [[float(w), float(w), i] for i, w in enumerate(widths)]
    excess = float(excess)

    if count == 1:
        if items[0][0] >= 0.0:
            items[0][0] = max(items[0][0] - excess, width_min)
        return [items[0][0]]

    items.sort(key=cmp_to_key(_shrink_comparer))
    count_same_width = 1
    while excess > 0.001 and count_same_width < count:
        while count_same_width < count and items[0][0] <= items[count_same_width][0]:
            count_same_width += 1
        if count_same_width < count and items[count_same_width][0] >= 0.0:
            max_remove = items[0][0] - items[count_same_width][0]
        else:
            max_remove = items[0][0] - 1.0
        max_remove = min(items[0][0] - width_min, max_remove)
        if max_remove <= 0.0:
            break
        base_remove = min(excess / count_same_width, max_remove)
        for entry in items[:count_same_width]:
            take = min(base_remove, entry[0] - width_min)
            entry[0] -= take
            excess -= take

    # Round down and redistribute the remainder.
    excess = 0.0
    for entry in items:
        rounded = float(math.trunc(entry[0]))
        excess += entry[0] - rounded
        entry[0] = rounded
    while excess > 0.0:
        given = 0.0
        for entry in items:
            if excess <= 0.0:
                break
            add = min(entry[1] - entry[0], 1.0)
            if add <= 0.0:
                continue
            entry[0] += add
            excess -= add
            given += add
        # The reference cannot stall here because its widths arrive as whole
        # pixels; ours arrive from a text measurement and can be fractional
        # without anything having been shrunk, which would spin this loop
        # forever handing out nothing.
        if given <= 0.0:
            break

    out = [0.0] * count
    for entry in items:
        out[int(entry[2])] = entry[0]
    return out


class TabPress(NamedTuple):
    """What a press on a :class:`TabBar` did.

    Attributes
    ----------
    action : str
        ``"select"``, ``"close"``, ``"button"`` (a :class:`TabItemButton` was
        pressed), ``"scroll"`` (a stepping arrow), or ``"list"`` (the tab-list
        drop-down was toggled).
    item : TabItem or None
        The tab it happened to. ``None`` for ``"list"``.
    index : int
        Where that tab sat, or ``-1``. For ``"close"`` this is where it sat
        *before* it was removed.
    """

    action: str
    item: TabItem | None
    index: int


class TabItem:
    """One tab: a label, and optionally a close button and an unsaved dot.

    Unlike a slice of :class:`~emtk.widgets.basic.Tabs`, a tab knows
    how wide it wants to be -- see :meth:`content_width` -- and the strip lays
    it out from that.

    Parameters
    ----------
    label : str
        The caption.
    closable : bool, optional
        Draw a close button, and report a press on it as a close rather than a
        selection. This is the reference's ``p_open`` out-parameter: a tab is
        closable exactly when the caller passed somewhere to put the answer.
    modified : bool, optional
        Draw a dot instead of the close button while the pointer is elsewhere,
        the way an editor says a document has unsaved changes. The reference
        calls this ``UnsavedDocument`` and gives it priority over the close
        button for the same reason: the two share the one slot at the right of
        the tab, and the dot is what you need to see at a glance.
    disabled : bool, optional
        Draw dimmed and swallow presses.
    button : bool, optional
        A tab-shaped button rather than a tab: it can be pressed but never
        becomes the selected tab. Prefer :class:`TabItemButton`.
    reorderable : bool, optional
        Whether a drag may move this tab, or move another tab across it. The
        reference's ``NoReorder``, inverted so the permissive case is the
        default.
    no_close_with_middle_mouse : bool, optional
        Middle-clicking this tab does not close it, whatever the bar says.
    """

    def __init__(
        self,
        label: str,
        closable: bool = False,
        modified: bool = False,
        disabled: bool = False,
        button: bool = False,
        reorderable: bool = True,
        no_close_with_middle_mouse: bool = False,
    ) -> None:
        self.label = str(label)
        self.closable = bool(closable)
        self.modified = bool(modified)
        self.disabled = bool(disabled)
        self.button = bool(button)
        self.reorderable = bool(reorderable)
        self.no_close_with_middle_mouse = bool(no_close_with_middle_mouse)
        #: Set by the owning :class:`TabBar` before it draws.
        self.selected = False
        #: Set by the owning :class:`TabBar` from the pointer position.
        self.hovered = False
        #: When this tab was last made current; the bar uses it to pick a
        #: replacement when the current tab is closed.
        self.last_selected = 0
        self._close_size = 0.0

    def __repr__(self) -> str:
        """Name the tab, for a debugger or a log line."""
        return f"<{type(self).__name__} {self.label!r}>"

    # ------------------------------------------------------------------ #
    def content_width(self, p: Painter) -> float:
        """How wide this tab wants to be, in pixels.

        Parameters
        ----------
        p : Painter
            Used to measure the label and the line height.

        Returns
        -------
        float
            The measured width, capped at :data:`MAX_TAB_WIDTH_EM` line
            heights so that one pathological caption cannot own the strip.

        Notes
        -----
        The reference's ``TabItemCalcSize``: the label plus padding on both
        sides, plus room for the close button (or the unsaved dot, which sits
        in the same place) when there is one, plus a single pixel when there is
        not -- so a strip of closable tabs and a strip of plain ones do not
        line up their labels differently.
        """
        line = p.line_height()
        width = p.text_width(self.label) + PAD_X
        if self.closable or self.modified:
            width += PAD_X + TAB_SPACING + line
        else:
            width += PAD_X + 1.0
        return min(width, line * MAX_TAB_WIDTH_EM)

    def close_button_box(
        self,
        p: Painter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> tuple[float, float, float, float] | None:
        """Where the close button (or the unsaved dot) goes, if it fits.

        Parameters
        ----------
        p : Painter
            Used to measure.
        x, y, w, h : float
            The tab's box.

        Returns
        -------
        tuple of float or None
            ``(x, y, w, h)`` of the button, or ``None`` when this tab has no
            button or has been shrunk too narrow to hold one. A shrunk tab
            dropping its close button is deliberate: a two-pixel-wide ✕ is not
            a target, and drawing one over the label costs the label the room
            it needed.
        """
        if not (self.closable or self.modified):
            return None
        size = p.line_height()
        if w < size + PAD_X * 2.0:
            return None
        box_x = max(x, x + w - PAD_X - size)
        box_y = y + max((h - size) * 0.5, 0.0)
        return (box_x, box_y, size, size)

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the tab shape, its label and its button.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box the strip laid out for this tab.
        """
        if w <= 1.0:
            self._close_size = 0.0
            return
        if self.button:
            fill = style.BUTTON_HOVERED if self.hovered else style.BUTTON
        elif self.disabled:
            fill = style.FRAME_BG
        elif self.hovered:
            fill = style.TAB_HOVERED
        elif self.selected:
            fill = style.TAB_SELECTED
        else:
            fill = style.TAB
        # The reference trims a pixel off the top so a tab looks detached from
        # the frame below it.
        top = y + 1.0
        body = max(h - 1.0, 1.0)
        p.stroke_rect(x, top, w, body, style.BORDER, fill)
        if self.selected and not self.button:
            p.fill_rect(x, top, w, max(1.0, h * 0.09), style.NAV_CURSOR)

        button_box = self.close_button_box(p, x, y, w, h)
        self._close_size = button_box[2] if button_box else 0.0
        right = (button_box[0] - TAB_SPACING) if button_box else (x + w - PAD_X)
        room = max(right - (x + PAD_X), 0.0)
        if self.disabled:
            colour = style.TEXT_DISABLED
        elif self.selected or self.button or self.hovered:
            colour = style.TEXT
        else:
            colour = style.DIM
        p.text(
            x + PAD_X,
            y,
            room,
            h,
            ALIGN_LEFT | ALIGN_VCENTER,
            style.fit_text(p, self.label, room),
            colour,
        )
        if button_box is None:
            return
        bx, by, size, _ = button_box
        if self.modified and not self.hovered:
            dot = size * 0.4
            p.fill_rect(bx + (size - dot) * 0.5, by + (size - dot) * 0.5, dot, dot, style.GOLD)
        elif self.closable:
            p.text(bx, by, size, size, ALIGN_CENTER, "x",
                   style.TEXT if self.hovered else style.DIM)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        button: int = 0,
    ) -> str | None:
        """Work out what a press on this tab means.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The tab's box, as last laid out.
        button : int, optional
            ``0`` for the left mouse button, ``2`` for the middle one -- the
            reference's numbering.

        Returns
        -------
        str or None
            ``"close"``, ``"select"``, ``"button"``, or ``None`` when the
            press missed or the tab is disabled.

        Notes
        -----
        Whether the close button is *there* comes from the last :meth:`draw`,
        because that is where it was measured; where it is comes from the box
        passed in, so a strip that scrolled since then still tests the right
        strip of pixels.

        The reference only shows the ✕ while the tab is hovered, and shows the
        unsaved dot the rest of the time. A press implies the pointer is on the
        tab, so at the moment a press is delivered the ✕ is what is under it --
        which is why a modified tab still closes from that slot rather than
        needing to be hovered first as a separate step.
        """
        if self.disabled or not style.hit(x, y, box_x, box_y, box_w, box_h):
            return None
        if button == 2:
            if self.closable and not self.no_close_with_middle_mouse:
                return "close"
            return None
        if self.closable and self._close_size > 0.0:
            edge = max(box_x, box_x + box_w - PAD_X - self._close_size)
            if x >= edge:
                return "close"
        return "button" if self.button else "select"


class TabItemButton(TabItem):
    """A tab-shaped button that is not a tab.

    It is pressed, it is reported, and it never becomes the selected tab --
    which is the whole distinction. A "+" at the end of a strip of documents is
    the case that wants it: shaped like the tabs beside it so it reads as part
    of the strip, but selecting it would mean showing its contents, and it has
    none.

    Parameters
    ----------
    label : str
        The caption.
    disabled : bool, optional
        Draw dimmed and swallow presses.
    """

    def __init__(self, label: str, disabled: bool = False) -> None:
        super().__init__(
            label,
            closable=False,
            modified=False,
            disabled=disabled,
            button=True,
            reorderable=False,
        )


class TabBar:
    """A strip of measured tabs, one of them current.

    Parameters
    ----------
    items : sequence, optional
        The tabs: :class:`TabItem` objects, or plain strings for the simple
        case.
    flags : int, optional
        Any of the ``TAB_BAR_*`` constants, or-ed together. A bar that names
        neither fitting policy gets :data:`TAB_BAR_FITTING_POLICY_DEFAULT`.
    index : int, optional
        Which tab starts out current.

    Notes
    -----
    :meth:`press` and :meth:`drag` read the geometry the last :meth:`draw`
    produced, which is how every control here works: there is no layout pass,
    so drawing *is* the layout pass.

    Selection is held as the tab itself rather than as an index, because
    reordering and closing both move indices around underneath it -- an index
    would quietly start pointing at the neighbour.
    """

    def __init__(
        self,
        items: Sequence[str | TabItem] = (),
        flags: int = TAB_BAR_NONE,
        index: int = 0,
    ) -> None:
        self.items: list[TabItem] = [
            one if isinstance(one, TabItem) else TabItem(str(one)) for one in items
        ]
        self.flags = int(flags)
        if not (self.flags & TAB_BAR_FITTING_POLICY_MASK):
            self.flags |= TAB_BAR_FITTING_POLICY_DEFAULT
        #: How far the strip is scrolled, in pixels.
        self.scroll = 0.0
        #: Whether the tab-list drop-down is showing.
        self.popup_open = False
        self._stamp = 1
        self._selected: TabItem | None = None
        self._held: TabItem | None = None
        self._drag_x = 0.0
        self._geometry: list[tuple[TabItem, float, float]] = []
        self._visible: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self._popup_box: tuple[float, float, float, float] | None = None
        self._popup_rows: list[tuple[TabItem, float, float, float, float]] = []
        self._scroll_boxes: tuple[tuple[float, ...], tuple[float, ...]] | None = None
        self._scroll_enabled = False
        self._width_all = 0.0
        self._ideal_width = 0.0
        self.select(index)
        if self._selected is None:
            # The asked-for tab was a button or disabled: a bar that has
            # something selectable in it always starts with something selected,
            # or its first draw shows a strip with no current tab at all.
            for one in self.items:
                if not (one.button or one.disabled):
                    self._select(one)
                    break

    # ------------------------------------------------------------------ #
    # The list
    # ------------------------------------------------------------------ #
    @property
    def selected(self) -> TabItem | None:
        """The current tab, or ``None`` when there is not one."""
        return self._selected

    @property
    def index(self) -> int:
        """Where the current tab sits, or ``-1``."""
        if self._selected is None or self._selected not in self.items:
            return -1
        return self.items.index(self._selected)

    @property
    def value(self) -> str:
        """The current tab's caption, or ``""``."""
        return self._selected.label if self._selected is not None else ""

    @property
    def labels(self) -> list[str]:
        """Every caption, in the order the tabs are drawn."""
        return [one.label for one in self.items]

    def select(self, index: int) -> str:
        """Make a tab current, by index.

        Parameters
        ----------
        index : int
            Clamped into range. A :class:`TabItemButton` cannot be selected, so
            asking for one leaves the selection alone.

        Returns
        -------
        str
            The current tab's caption.
        """
        if self.items:
            item = self.items[int(style.clamp(int(index), 0, len(self.items) - 1))]
            self._select(item)
        return self.value

    def cycle(self, step: int = 1) -> str:
        """Move to the next or previous tab, wrapping and skipping buttons.

        Parameters
        ----------
        step : int, optional
            How many tabs, and which way.

        Returns
        -------
        str
            The current tab's caption.
        """
        selectable = [one for one in self.items if not one.button]
        if not selectable:
            return ""
        if self._selected in selectable:
            at = selectable.index(self._selected)
        else:
            at = 0
            step = 0
        self._select(selectable[(at + int(step)) % len(selectable)])
        return self.value

    def add(self, item: str | TabItem) -> TabItem:
        """Append a tab.

        Parameters
        ----------
        item : str or TabItem
            The tab, or a caption to make one from.

        Returns
        -------
        TabItem
            What was appended.

        Notes
        -----
        Under :data:`TAB_BAR_AUTO_SELECT_NEW_TABS` the new tab becomes current,
        which is what an editor's "new document" wants. Without the flag it
        still becomes current if nothing else was -- an empty bar's first tab
        has nothing to lose the selection to.
        """
        one = item if isinstance(item, TabItem) else TabItem(str(item))
        self.items.append(one)
        if not one.button:
            if (self.flags & TAB_BAR_AUTO_SELECT_NEW_TABS) or self._selected is None:
                self._select(one)
        return one

    def close(self, item: TabItem) -> bool:
        """Remove a tab.

        Parameters
        ----------
        item : TabItem
            The tab to drop.

        Returns
        -------
        bool
            Whether it was there to drop.

        Notes
        -----
        Closing the current tab moves the selection to the tab that was current
        most recently before it, which is the reference's
        ``most_recently_selected_tab`` rule and reads far better than "the one
        to the left": closing a tab you opened from another one puts you back
        where you came from.
        """
        if item not in self.items:
            return False
        self.items.remove(item)
        if item is self._held:
            self._held = None
        if item is self._selected:
            self._selected = None
            best: TabItem | None = None
            for one in self.items:
                if one.button:
                    continue
                if best is None or one.last_selected > best.last_selected:
                    best = one
            if best is not None:
                self._select(best)
        return True

    def _select(self, item: TabItem | None) -> None:
        """Make ``item`` current, unless it is a button or disabled."""
        if item is None or item.button or item.disabled:
            return
        item.last_selected = self._stamp
        self._stamp += 1
        self._selected = item
        for one in self.items:
            one.selected = one is item

    def _set_hover(self, item: TabItem | None) -> None:
        """Mark exactly one tab hovered."""
        for one in self.items:
            one.hovered = one is item

    def hover(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> TabItem | None:
        """Follow the pointer, so tabs can light up and show their ✕.

        Parameters
        ----------
        x, y : float
            The pointer.
        box_x, box_y, box_w, box_h : float
            The strip's box.

        Returns
        -------
        TabItem or None
            The tab under the pointer.
        """
        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            self._set_hover(None)
            return None
        vis_x, vis_y, vis_w, vis_h = self._visible
        found: TabItem | None = None
        if style.hit(x, y, vis_x, vis_y, vis_w, vis_h):
            for one, item_x, item_w in self._geometry:
                if style.hit(x, y, item_x, vis_y, item_w, vis_h):
                    found = one
                    break
        self._set_hover(found)
        return found

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def layout(
        self,
        p: Painter,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> list[tuple[TabItem, float, float]]:
        """Work out where every tab goes, and remember it.

        Parameters
        ----------
        p : Painter
            Used to measure.
        x, y, w, h : float
            The strip's box.

        Returns
        -------
        list of tuple
            ``(item, x, width)`` per tab, in draw order and in the same
            coordinates the box was given in. A scrolled strip returns
            positions outside the box; :meth:`draw` clips them and
            :meth:`press` ignores them.

        Notes
        -----
        The reference's ``TabBarLayout``, in the order it does things, because
        the order matters: the drop-down and the scrolling arrows each take
        their width out of the strip *before* the excess is worked out, so
        adding either one can be what makes the tabs need shrinking.
        """
        line = p.line_height()
        bar_x, bar_w = float(x), float(w)
        self._popup_box = None
        if self.flags & TAB_BAR_TAB_LIST_POPUP_BUTTON:
            popup_w = line + PAD_X
            self._popup_box = (bar_x, float(y), popup_w, float(h))
            bar_x += popup_w
            bar_w -= popup_w

        widths = [one.content_width(p) for one in self.items]
        spacing = TAB_SPACING * max(len(self.items) - 1, 0)
        self._ideal_width = sum(widths) + spacing

        can_scroll = bool(self.flags & TAB_BAR_FITTING_POLICY_SCROLL)
        self._scroll_boxes = None
        self._scroll_enabled = (
            can_scroll
            and self._ideal_width > bar_w
            and len(self.items) > 1
            and not (self.flags & TAB_BAR_NO_TAB_LIST_SCROLLING_BUTTONS)
        )
        if self._scroll_enabled:
            arrow_w = max(line - 2.0, 4.0)
            buttons_w = arrow_w * 2.0
            at = max(bar_x, bar_x + bar_w - buttons_w)
            self._scroll_boxes = (
                (at, float(y), arrow_w, float(h)),
                (at + arrow_w, float(y), arrow_w, float(h)),
            )
            bar_w = max(bar_w - buttons_w - 1.0, 1.0)

        excess = max(self._ideal_width - bar_w, 0.0)
        if excess >= 1.0 and (self.flags & TAB_BAR_FITTING_POLICY_RESIZE_DOWN):
            widths = shrink_widths(widths, excess, SHRINK_MIN_WIDTH)

        offsets: list[float] = []
        run = 0.0
        for width in widths:
            offsets.append(run)
            run += width + TAB_SPACING
        self._width_all = max(run - TAB_SPACING, 0.0)

        if can_scroll:
            self._scroll_to_selected(offsets, widths, bar_w, line)
        else:
            self.scroll = 0.0

        self._visible = (bar_x, float(y), bar_w, float(h))
        self._geometry = [
            (one, bar_x + offset - self.scroll, width)
            for one, offset, width in zip(self.items, offsets, widths)
        ]
        for one in self.items:
            one.selected = one is self._selected
        return self._geometry

    def _scroll_to_selected(
        self,
        offsets: Sequence[float],
        widths: Sequence[float],
        bar_w: float,
        margin: float,
    ) -> None:
        """Bring the current tab inside the visible extent.

        Notes
        -----
        The reference's ``TabBarScrollToTab``, minus the animation. The margin
        is what makes a scrolled strip readable: stopping with the next tab's
        edge just showing is what says there is more to scroll, since there is
        no scrollbar to say it.
        """
        count = len(self.items)
        if self._selected is None or self._selected not in self.items or count == 0:
            self.scroll = 0.0
            return
        order = self.items.index(self._selected)
        x1 = offsets[order] - (margin if order > 0 else 0.0)
        x2 = offsets[order] + widths[order] + (margin if order + 1 < count else 1.0)
        if self.scroll > x1 or (x2 - x1) >= bar_w:
            self.scroll = x1
        elif self.scroll < x2 - bar_w:
            self.scroll = x2 - bar_w
        self.scroll = style.clamp(self.scroll, 0.0, max(self._width_all - bar_w, 0.0))

    # ------------------------------------------------------------------ #
    # Drawing
    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the strip: its tabs, its arrows, its drop-down, its rule.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The strip's box.
        """
        geometry = self.layout(p, x, y, w, h)
        p.fill_rect(x, y + h - 1.0, w, 1.0, style.TAB_SELECTED)

        if self._popup_box is not None:
            box_x, box_y, box_w, box_h = self._popup_box
            p.stroke_rect(box_x, box_y + 1.0, box_w, max(box_h - 1.0, 1.0),
                          style.BORDER, style.FRAME_BG)
            p.text(box_x, box_y, box_w, box_h, ALIGN_CENTER, "▾", style.DIM)

        vis_x, vis_y, vis_w, vis_h = self._visible
        p.push_clip(vis_x, vis_y, max(vis_w, 1.0), vis_h)
        try:
            for item, item_x, item_w in geometry:
                if item_x + item_w < vis_x or item_x > vis_x + vis_w:
                    continue
                item.draw(p, item_x, vis_y, item_w, vis_h)
        finally:
            p.pop_clip()

        if self._scroll_boxes is not None:
            for box, glyph in zip(self._scroll_boxes, ("◀", "▶")):
                box_x, box_y, box_w, box_h = box
                p.stroke_rect(box_x, box_y + 1.0, box_w, max(box_h - 1.0, 1.0),
                              style.BORDER, style.FRAME_BG)
                p.text(box_x, box_y, box_w, box_h, ALIGN_CENTER, glyph, style.DIM)

        self._popup_rows = []
        if self.popup_open:
            self._draw_popup(p, x, y, w, h)

    def _draw_popup(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the tab-list drop-down under the strip."""
        rows = [one for one in self.items if not one.button]
        if not rows:
            return
        row_h = p.line_height() * 1.4
        width = max(p.text_width(one.label) for one in rows) + PAD_X * 3.0
        width = min(max(width, 40.0), max(w, 40.0))
        top = y + h
        p.stroke_rect(x, top, width, row_h * len(rows), style.BORDER, style.POPUP_BG)
        p.push_clip(x, top, width, row_h * len(rows))
        try:
            for at, one in enumerate(rows):
                row_y = top + at * row_h
                if one is self._selected:
                    p.fill_rect(x, row_y, width, row_h, style.HEADER)
                p.text(x + PAD_X, row_y, max(width - PAD_X * 2.0, 1.0), row_h,
                       ALIGN_LEFT | ALIGN_VCENTER,
                       style.fit_text(p, one.label, max(width - PAD_X * 2.0, 1.0)),
                       style.TEXT_DISABLED if one.disabled else style.TEXT)
                self._popup_rows.append((one, x, row_y, width, row_h))
        finally:
            p.pop_clip()

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
        button: int = 0,
    ) -> TabPress | None:
        """Route a press to a tab, an arrow, the drop-down, or nowhere.

        Parameters
        ----------
        x, y : float
            The point.
        box_x, box_y, box_w, box_h : float
            The strip's box.
        button : int, optional
            ``0`` for the left mouse button, ``2`` for the middle one. A middle
            press closes a closable tab unless
            :data:`TAB_BAR_NO_CLOSE_WITH_MIDDLE_MOUSE_BUTTON` is set, and never
            changes the selection -- the reference's button behaviour is
            left-only, so there is nothing else for it to do.

        Returns
        -------
        TabPress or None
            What happened, or ``None`` when the press hit nothing that acts.
        """
        if self.popup_open:
            for one, row_x, row_y, row_w, row_h in self._popup_rows:
                if style.hit(x, y, row_x, row_y, row_w, row_h):
                    self.popup_open = False
                    self._select(one)
                    return TabPress("select", one, self.items.index(one))
            self.popup_open = False

        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            self._set_hover(None)
            return None

        if self._popup_box is not None and style.hit(x, y, *self._popup_box):
            self.popup_open = not self.popup_open
            return TabPress("list", None, -1)

        if self._scroll_boxes is not None:
            for box, direction in zip(self._scroll_boxes, (-1, +1)):
                if style.hit(x, y, *box):
                    stepped = self._step_selection(direction)
                    at = self.items.index(stepped) if stepped is not None else -1
                    return TabPress("scroll", stepped, at)

        vis_x, vis_y, vis_w, vis_h = self._visible
        if not style.hit(x, y, vis_x, vis_y, vis_w, vis_h):
            return None
        for item, item_x, item_w in self._geometry:
            if not style.hit(x, y, item_x, vis_y, item_w, vis_h):
                continue
            what = item.press(x, y, item_x, vis_y, item_w, vis_h, button)
            if what is None:
                return None
            self._set_hover(item)
            if what == "close":
                at = self.items.index(item)
                self.close(item)
                self._set_hover(None)
                return TabPress("close", item, at)
            if what == "button":
                self._held = None
                return TabPress("button", item, self.items.index(item))
            self._select(item)
            self._held = item
            self._drag_x = float(x)
            return TabPress("select", item, self.items.index(item))
        return None

    def _step_selection(self, direction: int) -> TabItem | None:
        """Move the selection one tab along, skipping buttons.

        Notes
        -----
        The reference's scrolling arrows do not scroll: they *select* the next
        or previous tab and let the scroll follow it. Two arrows that moved the
        view without moving the selection would let you scroll the current tab
        off the strip, which is the state the scroll-into-view rule exists to
        prevent.
        """
        if not self.items:
            return None
        at = self.index
        if at < 0:
            at = 0 if direction > 0 else len(self.items) - 1
        target = at + direction
        while 0 <= target < len(self.items) and self.items[target].button:
            target += direction
        if not (0 <= target < len(self.items)):
            target = at
        item = self.items[target]
        self._select(item)
        return self._selected if self._selected is not None else item

    def drag(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Continue a drag, reordering when the tab crosses a neighbour.

        Parameters
        ----------
        x, y : float
            The pointer.
        box_x, box_y, box_w, box_h : float
            The strip's box. Unused for the test itself -- the geometry from
            the last :meth:`draw` is what the crossing is measured against --
            but taken so every control here drags the same way.

        Returns
        -------
        bool
            Whether the order changed.

        Notes
        -----
        The reference's ``TabBarQueueReorderFromMousePos``: the reorder fires
        only once the pointer has left the dragged tab's own box *in the
        direction it is travelling*, then it walks the neighbours it has
        cleared and moves the tab past all of them at once. Testing the
        direction as well as the position is what stops a tab oscillating --
        a moved tab jumps to the other side of the pointer, and without the
        direction test that jump immediately looks like grounds for moving it
        back.
        """
        if self._held is None or not (self.flags & TAB_BAR_REORDERABLE):
            return False
        if not self._held.reorderable:
            return False
        held_box: tuple[float, float] | None = None
        for item, item_x, item_w in self._geometry:
            if item is self._held:
                held_box = (item_x, item_w)
                break
        if held_box is None:
            return False
        delta = float(x) - self._drag_x
        self._drag_x = float(x)
        left, width = held_box
        if delta < 0.0 and x < left:
            pass
        elif delta > 0.0 and x > left + width:
            pass
        else:
            return False
        return self._reorder_from_pointer(float(x))

    def _reorder_from_pointer(self, x: float) -> bool:
        """Move the held tab to wherever the pointer has got to."""
        held = self._held
        if held is None or held not in self.items:
            return False
        source = self.items.index(held)
        positions = {item: (item_x, item_w) for item, item_x, item_w in self._geometry}
        if held not in positions:
            return False
        direction = -1 if positions[held][0] > x else +1
        destination = source
        at = source
        while 0 <= at < len(self.items):
            candidate = self.items[at]
            if not candidate.reorderable:
                break
            if candidate not in positions:
                break
            destination = at
            cand_x, cand_w = positions[candidate]
            x1 = cand_x - TAB_SPACING
            x2 = cand_x + cand_w + TAB_SPACING
            if (direction < 0 and x > x1) or (direction > 0 and x < x2):
                break
            at += direction
        if destination == source:
            return False
        self.items.insert(destination, self.items.pop(source))
        return True

    def release(self) -> None:
        """Let go of a dragged tab."""
        self._held = None
