"""Menus and popups, as painter-level controls.

Why this is a module and not more code in the panel
---------------------------------------------------
An application's own chrome already draws menus against the same six
painter operations -- a menu bar across the top of the scene, per-object
context menus, submenus that flip to the other side of their parent when the
window edge is close. All of it is *inline*: the rectangles live in the panel's
own dataclasses, the hit test is a method on the panel, and nothing else can
put a menu on screen without owning a panel first.

This is the same behaviour as a set of controls in the idiom the rest of
:mod:`.widgets` uses: one class per control, its state and its hit test in the
same object as its drawing. A host constructs a :class:`MenuBar`, draws it into
a box, and hands it the presses that land anywhere -- not only in that box,
because an open menu is drawn *outside* the strip that opened it.

What was taken from the reference implementation
------------------------------------------------
* **The column layout.** ``ImGuiMenuColumns`` lays a row out as four columns --
  icon, label, shortcut, mark -- each as wide as the widest row's, with spacing
  inserted only between columns that are actually used. That is what makes a
  shortcut a *column* rather than a suffix on the label, and it is why a menu
  carrying shortcuts is wider than the same menu without them. The icon column
  is not ported (cmtk has no per-item icons); the other three are.
* **The placement rule.** ``FindBestWindowPosForPopupEx`` is ported whole, as
  :func:`best_popup_pos`. It tries right, down, up, left -- skipping any
  direction that does not have room on its own axis -- against a rectangle to
  *avoid*, which is what makes one function serve three cases: a bar menu drops
  below the bar, a submenu opens beside its parent and flips to the other side
  near the right edge, and a free-floating popup flips up and left near the
  bottom-right corner. A submenu that opens off-screen is the classic bug and
  this is the reference's answer to it.
* **Modal versus plain.** In the reference a plain popup is closed by the click
  that lands outside it, and that click is *not* owned -- it reaches whatever is
  behind. A modal is not closed by it, and the click is captured
  (``WantCaptureMouse ... || has_open_modal``). :class:`PopupModal` reports
  exactly that, through :class:`PopupPress`.

What was deliberately skipped
-----------------------------
* **Time.** The reference opens a submenu on hover after a delay, and keeps it
  open while the pointer moves diagonally toward it. Both need a per-frame
  clock and a hover feed, and cmtk has neither here. Submenus open on
  **press**. :attr:`MenuItem.hovered` is a plain attribute a host may set if it
  has hover information; nothing in this module reads a clock.
* **Keyboard navigation.** The reference's menus are fully navigable, through a
  global input context. Introducing one would be a second paradigm beside the
  retained controls, so keys are left to the host.
* **Scrolling.** A menu taller than the viewport is placed by
  :func:`best_popup_pos` and clipped; the panel's inline menus page through a
  too-tall menu instead, and that behaviour belongs with them until a host asks
  for it here.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Union

from .. import style
from ..painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Painter

__all__ = [
    "PAD",
    "SPACING",
    "OVERLAP",
    "ROW_SCALE",
    "MARK_SCALE",
    "SEPARATOR_SCALE",
    "best_popup_pos",
    "PopupPress",
    "MenuItem",
    "Menu",
    "MenuBar",
    "Popup",
    "PopupModal",
]

#: Padding between a panel's edge and its contents, in pixels.
PAD = 6.0

#: Gap between two used columns of a row. The reference's ``ItemSpacing.x``.
SPACING = 8.0

#: How far a submenu overlaps the parent it hangs off, so the relative depth of
#: two panels reads at a glance. The reference's ``ItemInnerSpacing.x``.
OVERLAP = 4.0

#: A row's height, as a multiple of the painter's line height.
ROW_SCALE = 1.4

#: The width of the check/arrow column, as a multiple of the line height. The
#: reference's ``FontSize * 1.20``, and it is reserved even in a menu with no
#: checkmarks in it -- otherwise a menu changes width when an item is ticked.
MARK_SCALE = 1.2

#: A separator row's height, as a multiple of a normal row's.
SEPARATOR_SCALE = 0.5

#: Stands in for the reference's ``FLT_MAX`` in a rectangle that is unbounded
#: on one axis. A real number rather than ``inf`` because an unbounded viewport
#: is also a large number, and ``inf - inf`` is a NaN that compares false
#: against every bound -- which would place a panel at infinity instead of
#: rejecting the direction.
_FAR = 1.0e9

#: The viewport a control assumes until a host tells it otherwise: large enough
#: that nothing ever flips, small enough to stay far below :data:`_FAR`.
_UNBOUNDED = (1.0e6, 1.0e6)

#: A menu's entries: items, nested menus, and ``None`` for a separator rule.
Entry = Union["MenuItem", "Menu", None]

#: A laid-out row: its entry and the ``(x, y, w, h)`` it was drawn in.
Row = tuple[Entry, tuple[float, float, float, float]]

#: The four directions :func:`best_popup_pos` tries, in the order the reference
#: tries them.
_DIRECTIONS = ("right", "down", "up", "left")


def best_popup_pos(
    ref: tuple[float, float],
    size: tuple[float, float],
    outer: tuple[float, float, float, float],
    avoid: tuple[float, float, float, float],
    last_dir: str | None = None,
) -> tuple[float, float, str]:
    """Where to put a panel so it stays inside the viewport.

    A port of the reference implementation's ``FindBestWindowPosForPopupEx``
    with its default policy. Each direction is tried in turn -- the one used
    last time first, so an open menu does not jitter from side to side as its
    parent moves -- and a direction whose own axis has no room is skipped
    entirely rather than clamped, because clamping is what draws a submenu on
    top of the menu it came from.

    Parameters
    ----------
    ref : tuple of float
        The preferred top-left corner, ``(x, y)``.
    size : tuple of float
        The panel's ``(width, height)``.
    outer : tuple of float
        The viewport, as ``(x0, y0, x1, y1)``.
    avoid : tuple of float
        The rectangle the panel must not cover, as ``(x0, y0, x1, y1)``. A
        degenerate rectangle (a point) is what a free-floating popup passes; a
        menu bar passes a strip unbounded horizontally, and a parent menu passes
        a column unbounded vertically. Use :data:`_FAR`, never ``inf``.
    last_dir : str, optional
        The direction chosen last time, one of ``"right"``, ``"down"``,
        ``"up"``, ``"left"``.

    Returns
    -------
    tuple
        ``(x, y, direction)``. ``direction`` is ``"none"`` when no side had
        room and the panel was simply pushed back inside the viewport.
    """
    width, height = size
    out_x0, out_y0, out_x1, out_y1 = outer
    avo_x0, avo_y0, avo_x1, avo_y1 = avoid
    base_x = style.clamp(ref[0], out_x0, out_x1 - width)
    base_y = style.clamp(ref[1], out_y0, out_y1 - height)

    order: list[str] = list(_DIRECTIONS)
    if last_dir in order:
        order.remove(last_dir)
        order.insert(0, last_dir)

    for direction in order:
        avail_w = (avo_x0 if direction == "left" else out_x1) - (
            avo_x1 if direction == "right" else out_x0
        )
        avail_h = (avo_y0 if direction == "up" else out_y1) - (
            avo_y1 if direction == "down" else out_y0
        )
        if avail_w < width and direction in ("left", "right"):
            continue
        if avail_h < height and direction in ("up", "down"):
            continue
        pos_x = avo_x0 - width if direction == "left" else (
            avo_x1 if direction == "right" else base_x
        )
        pos_y = avo_y0 - height if direction == "up" else (
            avo_y1 if direction == "down" else base_y
        )
        return (max(pos_x, out_x0), max(pos_y, out_y0), direction)

    # Nothing had room: keep as much of it on screen as there is room for.
    pos_x = max(min(ref[0] + width, out_x1) - width, out_x0)
    pos_y = max(min(ref[1] + height, out_y1) - height, out_y0)
    return (pos_x, pos_y, "none")


class PopupPress(NamedTuple):
    """What a menu or popup did with one press.

    Three questions, because a host needs all three and cannot recover any of
    them from the others: *what fired*, *may the press also reach the scene
    behind*, and *is the panel still up*.

    Attributes
    ----------
    item : MenuItem or None
        The item that was activated, if any. ``None`` covers every other
        outcome, including a press that opened a submenu and a press that a
        disabled item refused.
    consumed : bool
        Whether the press belongs to this control and must not be passed on. A
        press outside a **modal** is consumed -- that is what modal means. A
        press outside a plain popup is *not*: in the reference the click that
        dismisses a popup still reaches what is behind it.
    closed : bool
        Whether the panel dismissed itself as a result. Activating an item
        closes its menu, as does a press outside a plain popup.
    """

    item: MenuItem | None
    consumed: bool
    closed: bool


#: The answer when a press had nothing to do with a control at all.
_IGNORED = PopupPress(None, False, False)


def _columns_width(label_w: float, shortcut_w: float, mark_w: float) -> float:
    """Total content width of a row laid out in the reference's columns.

    Spacing goes only *between* columns that are used, which is the whole of
    ``ImGuiMenuColumns::CalcNextTotalWidth``: a menu with no shortcuts is not
    padded by the width of a shortcut column that is not there.

    Parameters
    ----------
    label_w, shortcut_w, mark_w : float
        The widest label, the widest shortcut, and the check/arrow column.

    Returns
    -------
    float
        The content width, excluding the panel's own padding.
    """
    offset = 0.0
    want_spacing = False
    for width in (label_w, shortcut_w, mark_w):
        if want_spacing and width > 0.0:
            offset += SPACING
        want_spacing = want_spacing or width > 0.0
        offset += width
    return offset


def _panel_metrics(
    p: Painter, entries: Sequence[Entry], title: str
) -> tuple[float, float, float, float, float]:
    """Measure a panel from its entries.

    Parameters
    ----------
    p : Painter
        Used to measure text.
    entries : sequence
        The entries; ``None`` is a separator.
    title : str
        The panel's caption, or ``""`` for none.

    Returns
    -------
    tuple of float
        ``(width, height, row_h, title_h, shortcut_w)``.
    """
    row_h = p.line_height() * ROW_SCALE
    title_h = row_h if title else 0.0
    mark_w = p.line_height() * MARK_SCALE
    label_w = 0.0
    shortcut_w = 0.0
    for entry in entries:
        if entry is None:
            continue
        label_w = max(label_w, p.text_width(entry.label))
        if entry.shortcut:
            shortcut_w = max(shortcut_w, p.text_width(entry.shortcut))
    content = _columns_width(label_w, shortcut_w, mark_w)
    width = max(content, p.text_width(title)) + 2.0 * PAD
    height = title_h + 2.0 * PAD + sum(
        row_h * SEPARATOR_SCALE if entry is None else row_h for entry in entries
    )
    return (width, height, row_h, title_h, shortcut_w)


def _lay_rows(
    p: Painter,
    x: float,
    y: float,
    w: float,
    entries: Sequence[Entry],
    title: str,
    viewport: tuple[float, float],
) -> list[Row]:
    """Give every entry its rectangle inside a panel already placed and sized.

    The rectangles are the single source of truth for both drawing and hit
    testing, so the two cannot disagree about where a row is.

    Parameters
    ----------
    p : Painter
        Used to measure.
    x, y, w : float
        The panel's left edge, top edge and width.
    entries : sequence
        The entries.
    title : str
        The panel's caption, or ``""``.
    viewport : tuple of float
        Handed down to nested menus so a submenu knows where the edges are.

    Returns
    -------
    list
        ``(entry, (x, y, w, h))`` pairs, separators included.
    """
    _width, _height, row_h, title_h, shortcut_w = _panel_metrics(p, entries, title)
    rows: list[Row] = []
    row_y = y + PAD + title_h
    for entry in entries:
        if entry is None:
            rows.append((None, (x, row_y, w, row_h * SEPARATOR_SCALE)))
            row_y += row_h * SEPARATOR_SCALE
            continue
        entry.column_shortcut_width = shortcut_w
        if isinstance(entry, Menu):
            entry.horizontal = False
            entry.viewport = viewport
        rows.append((entry, (x, row_y, w, row_h)))
        row_y += row_h
    return rows


def _paint_panel(
    p: Painter,
    x: float,
    y: float,
    w: float,
    h: float,
    rows: Sequence[Row],
    title: str,
) -> None:
    """Paint a panel's frame, caption and rows, then any open submenu beside it.

    The rows are drawn inside a clip so a row wider than the panel cannot spill
    over the frame; the submenu panels are drawn **after** it is popped, because
    a submenu hangs outside its parent by definition and would otherwise be
    clipped away entirely.

    Parameters
    ----------
    p : Painter
        The surface.
    x, y, w, h : float
        The panel.
    rows : sequence
        As returned by :func:`_lay_rows`.
    title : str
        The caption, or ``""``.
    """
    p.stroke_rect(x, y, w, h, style.BORDER, style.POPUP_BG)
    row_h = p.line_height() * ROW_SCALE
    title_h = row_h if title else 0.0
    if title:
        p.text(x + PAD, y + PAD, max(w - 2.0 * PAD, 1.0), row_h,
               ALIGN_VCENTER | ALIGN_LEFT,
               style.fit_text(p, title, w - 2.0 * PAD), style.GOLD, bold=True)

    p.push_clip(x, y + PAD + title_h, w, max(h - 2.0 * PAD - title_h, 0.0))
    try:
        for entry, rect in rows:
            if entry is None:
                rule_y = rect[1] + rect[3] * 0.5
                p.fill_rect(rect[0] + PAD, rule_y, max(rect[2] - 2.0 * PAD, 1.0),
                            1.0, style.SEPARATOR)
                continue
            entry.draw_row(p, *rect)
    finally:
        p.pop_clip()

    for entry, rect in rows:
        if isinstance(entry, Menu) and entry.open:
            entry.draw_panel(p, *rect)


def _route(rows: Sequence[Row], x: float, y: float) -> PopupPress:
    """Send a press to the deepest row that wants it.

    Open submenus are asked first and in the order they are drawn, which is
    front to back: a submenu is painted over its parent, so a press that lands
    on both belongs to the submenu.

    Parameters
    ----------
    rows : sequence
        As returned by :func:`_lay_rows`.
    x, y : float
        The press.

    Returns
    -------
    PopupPress
        With ``consumed`` false when the press missed every row.
    """
    for entry, rect in rows:
        if not isinstance(entry, Menu) or not entry.open:
            continue
        result = entry.press(x, y, *rect)
        if result.item is not None or result.consumed:
            return result

    for entry, rect in rows:
        if entry is None or not style.hit(x, y, *rect):
            continue
        if isinstance(entry, Menu):
            result = entry.press(x, y, *rect)
            for other, _rect in rows:
                if isinstance(other, Menu) and other is not entry:
                    other.close()
            return result
        fired = entry.press(x, y, *rect)
        # A press on a disabled row is still the panel's: it must not fall
        # through to the scene behind, or a menu would rotate the molecule.
        return PopupPress(entry if fired else None, True, fired)

    return _IGNORED


class MenuItem:
    """One row of a menu: a label, an optional shortcut, an optional tick.

    The shortcut is a **column**, not a suffix: every row's shortcut ends at the
    same x, just left of the check column, and the panel is wide enough for the
    widest of them. That is the reference's ``ImGuiMenuColumns`` layout, and it
    is why ``Ctrl+Shift+Z`` on one row widens the menu that ``Undo`` is in.

    Parameters
    ----------
    label : str
        The row's text.
    shortcut : str, optional
        Accelerator text, drawn dim in its own column. Nothing here binds it --
        the host owns keys.
    checked : bool, optional
        Whether the tick is drawn.
    enabled : bool, optional
        A disabled row draws dimmed and refuses its click. It is still *shown*:
        a command that exists but cannot run right now says more than a menu
        that silently loses entries.
    checkable : bool, optional
        Whether activating the row flips :attr:`checked`. The reference has the
        same two spellings -- one takes ``bool selected``, the other
        ``bool* p_selected`` and toggles it.

    Attributes
    ----------
    hovered : bool
        Set by a host that has hover information; drawn as a highlight. Nothing
        in this module sets it, because nothing here reads the pointer between
        presses.
    column_shortcut_width : float
        The widest shortcut in the menu this row belongs to, set by the owning
        :class:`Menu` so every row's shortcut lands in the same column. Zero
        when the row is drawn on its own, which right-aligns its own shortcut in
        its own box -- the same result for a menu of one.
    """

    def __init__(
        self,
        label: str,
        shortcut: str = "",
        checked: bool = False,
        enabled: bool = True,
        checkable: bool = False,
    ) -> None:
        self.label = str(label)
        self.shortcut = str(shortcut)
        self.checked = bool(checked)
        self.enabled = bool(enabled)
        self.checkable = bool(checkable)
        self.hovered = False
        self.column_shortcut_width = 0.0

    def toggle(self) -> bool:
        """Flip the tick and return its new state.

        Returns
        -------
        bool
            Whether the row is now ticked.
        """
        self.checked = not self.checked
        return self.checked

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the row: highlight, label, shortcut column, tick.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row's box.
        """
        mark_w = p.line_height() * MARK_SCALE
        if self.hovered and self.enabled:
            p.fill_rect(x + 1.0, y, max(w - 2.0, 1.0), h, style.HEADER_HOVERED)

        shortcut_w = max(
            self.column_shortcut_width,
            p.text_width(self.shortcut) if self.shortcut else 0.0,
        )
        mark_left = x + w - PAD - mark_w
        shortcut_right = mark_left - SPACING
        room = shortcut_right - (x + PAD)
        if shortcut_w > 0.0:
            room -= shortcut_w + SPACING
        room = max(room, 1.0)

        colour = style.TEXT if self.enabled else style.TEXT_DISABLED
        p.text(x + PAD, y, room, h, ALIGN_VCENTER | ALIGN_LEFT,
               style.fit_text(p, self.label, room), colour)

        if self.shortcut:
            dim = style.DIM if self.enabled else style.with_alpha(style.TEXT_DISABLED, 140)
            p.text(shortcut_right - shortcut_w, y, shortcut_w, h,
                   ALIGN_VCENTER | ALIGN_RIGHT, self.shortcut, dim)

        if self.checked:
            # A filled square, not a "✓": the painter has no polyline, and a
            # glyph the atlas has not baked draws as nothing at all -- a tick
            # that is silently absent is worse than one that is a square.
            side = mark_w * 0.5
            p.fill_rect(mark_left + (mark_w - side) * 0.5, y + (h - side) * 0.5,
                        side, side, style.CHECK_MARK)

    def draw_row(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the row alone, without anything that hangs off it.

        A :class:`MenuItem` has nothing hanging off it, so this is
        :meth:`draw`. It exists so a panel can paint every kind of entry the
        same way and still keep submenu panels outside its own clip.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row's box.
        """
        self.draw(p, x, y, w, h)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Process a press. Returns whether the row activated.

        Parameters
        ----------
        x, y : float
            The press.
        box_x, box_y, box_w, box_h : float
            The row's box, as last drawn.

        Returns
        -------
        bool
            True when the row fired. A disabled row returns False even when the
            press is squarely on it -- it refuses the click rather than
            swallowing it silently and pretending to have run.
        """
        if not style.hit(x, y, box_x, box_y, box_w, box_h):
            return False
        if not self.enabled:
            return False
        if self.checkable:
            self.toggle()
        return True


class Menu:
    """A labelled row that opens a panel of items and nested menus.

    The same class serves both places a menu appears: a title on a
    :class:`MenuBar`, whose panel drops **below** the strip, and a row inside
    another menu, whose panel opens **beside** it and flips to the other side
    when there is no room. :attr:`horizontal` picks which, and the owner sets it
    -- a menu never has to be told twice.

    Parameters
    ----------
    label : str
        The row's text, and the name on the bar.
    entries : sequence, optional
        Items (:class:`MenuItem`), nested menus (:class:`Menu`), and ``None``
        for a separator rule.
    title : str, optional
        A caption drawn bold at the top of the panel. The reference's menus have
        none; cmtk's do, because a context menu opened at the pointer has
        nothing else to say what it is a menu *of*.
    enabled : bool, optional
        A disabled menu draws dimmed and refuses to open.

    Attributes
    ----------
    open : bool
        Whether the panel is down.
    horizontal : bool
        Whether the row sits in a horizontal bar. Set by the owner.
    viewport : tuple of float
        ``(width, height)`` the panel must stay inside. Set by the owner, or
        with :meth:`set_viewport`; until then it is large enough that nothing
        flips.
    hovered : bool
        As :attr:`MenuItem.hovered`.
    """

    def __init__(
        self,
        label: str,
        entries: Sequence[Entry] = (),
        title: str = "",
        enabled: bool = True,
    ) -> None:
        self.label = str(label)
        self.shortcut = ""
        self.title = str(title)
        self.entries: list[Entry] = list(entries)
        self.enabled = bool(enabled)
        self.open = False
        self.horizontal = False
        self.hovered = False
        self.viewport: tuple[float, float] = _UNBOUNDED
        self.column_shortcut_width = 0.0
        #: The direction the panel opened last time, kept so it does not jitter
        #: from side to side while its parent moves.
        self.last_dir: str | None = None
        self._row: tuple[float, float, float, float] | None = None
        self._panel: tuple[float, float, float, float] | None = None
        self._rows: list[Row] = []

    # ------------------------------------------------------------------ #
    def set_viewport(self, width: float, height: float) -> None:
        """Tell this menu and everything under it where the edges are.

        Parameters
        ----------
        width, height : float
            The viewport, in the same space the boxes are given in.
        """
        self.viewport = (float(width), float(height))
        for entry in self.entries:
            if isinstance(entry, Menu):
                entry.set_viewport(width, height)

    def close(self) -> None:
        """Put the panel away, and every panel under it."""
        self.open = False
        for entry in self.entries:
            if isinstance(entry, Menu):
                entry.close()

    def panel_size(self, p: Painter) -> tuple[float, float]:
        """Measure the ``(width, height)`` the panel needs for its entries.

        The width comes from the widest label *plus its shortcut column* plus
        the check column, so a menu carrying accelerators is wider than the same
        menu without them -- which is the point of laying them out in columns.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            ``(width, height)``.
        """
        width, height, _row_h, _title_h, _shortcut_w = _panel_metrics(
            p, self.entries, self.title
        )
        return (width, height)

    @property
    def panel_rect(self) -> tuple[float, float, float, float] | None:
        """Where the panel was last painted, as ``(x, y, w, h)``, or ``None``.

        Placement is decided at draw time, because it is the only moment the
        width is known, so this is the answer to "did it flip".
        """
        return self._panel

    def contains(self, x: float, y: float) -> bool:
        """Whether a point is on this menu's row or anywhere in its open panels.

        A pure query: unlike :meth:`press` it changes nothing, so a host can ask
        "is the pointer over the chrome" without dismissing a menu by asking.

        Parameters
        ----------
        x, y : float
            The point.

        Returns
        -------
        bool
            True if the point is over the row, the panel, or an open submenu.
        """
        if self._row is not None and style.hit(x, y, *self._row):
            return True
        if not self.open:
            return False
        if self._panel is not None and style.hit(x, y, *self._panel):
            return True
        return any(
            isinstance(entry, Menu) and entry.open and entry.contains(x, y)
            for entry in self.entries
        )

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the row, and the panel below or beside it when it is open.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row's box.
        """
        self.draw_row(p, x, y, w, h)
        if self.open:
            self.draw_panel(p, x, y, w, h)

    def draw_row(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the labelled row alone, without its panel.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The row's box.
        """
        self._row = (x, y, w, h)
        colour = style.TEXT if self.enabled else style.TEXT_DISABLED

        if self.horizontal:
            if self.open:
                p.fill_rect(x, y, w, h, style.HEADER_ACTIVE)
            elif self.hovered and self.enabled:
                p.fill_rect(x, y, w, h, style.HEADER_HOVERED)
            p.text(x, y, w, h, ALIGN_VCENTER | ALIGN_HCENTER,
                   style.fit_text(p, self.label, w - 2.0 * PAD), colour)
            return

        if self.open or (self.hovered and self.enabled):
            p.fill_rect(x + 1.0, y, max(w - 2.0, 1.0), h,
                        style.HEADER_HOVERED if self.hovered else style.HEADER)
        mark_w = p.line_height() * MARK_SCALE
        room = max(w - 2.0 * PAD - mark_w - SPACING, 1.0)
        p.text(x + PAD, y, room, h, ALIGN_VCENTER | ALIGN_LEFT,
               style.fit_text(p, self.label, room), colour)
        # "▸" and not ">": the baked atlas has this one, and it is the marker
        # the panel's inline menus already use.
        p.text(x, y, max(w - PAD, 1.0), h, ALIGN_VCENTER | ALIGN_RIGHT, "▸", colour)

    def draw_panel(
        self, p: Painter, row_x: float, row_y: float, row_w: float, row_h: float
    ) -> None:
        """Place and paint the panel that hangs off a row.

        Parameters
        ----------
        p : Painter
            The surface.
        row_x, row_y, row_w, row_h : float
            The row the panel hangs off, as last drawn.
        """
        width, height = self.panel_size(p)
        view_w, view_h = self.viewport
        if self.horizontal:
            # A bar menu must clear the whole strip, not just its own title, so
            # the strip is what it avoids -- unbounded left and right, which is
            # exactly what rules "right" and "left" out and drops it below.
            avoid = (-_FAR, row_y, _FAR, row_y + row_h)
            ref = (row_x, row_y)
        else:
            # A submenu avoids its parent's *column*, overlapping it slightly so
            # the two panels read as nested rather than as one wide block.
            avoid = (row_x + OVERLAP, -_FAR, row_x + row_w - OVERLAP, _FAR)
            ref = (row_x, row_y - PAD)
        pos_x, pos_y, self.last_dir = best_popup_pos(
            ref, (width, height), (0.0, 0.0, view_w, view_h), avoid, self.last_dir
        )
        self._panel = (pos_x, pos_y, width, height)
        self._rows = _lay_rows(p, pos_x, pos_y, width, self.entries, self.title,
                               self.viewport)
        _paint_panel(p, pos_x, pos_y, width, height, self._rows, self.title)

    # ------------------------------------------------------------------ #
    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> PopupPress:
        """Process a press against the row and, if it is open, the panel.

        The panel is tested **first**, and the deepest open submenu inside it
        before that: a submenu is painted over everything behind it, so a press
        that lands on a submenu row and on a parent row belongs to the submenu.
        Getting this backwards is the bug where a nested menu can be seen but
        never clicked.

        Parameters
        ----------
        x, y : float
            The press.
        box_x, box_y, box_w, box_h : float
            The row's box, as last drawn.

        Returns
        -------
        PopupPress
            ``item`` is the row that fired anywhere in the tree.
        """
        if self.open and self._rows:
            result = _route(self._rows, x, y)
            if result.item is not None:
                self.close()
                return PopupPress(result.item, True, True)
            if result.consumed:
                return result
            if self._panel is not None and style.hit(x, y, *self._panel):
                return PopupPress(None, True, False)

        if style.hit(x, y, box_x, box_y, box_w, box_h):
            if not self.enabled:
                return PopupPress(None, True, False)
            if self.open:
                self.close()
                return PopupPress(None, True, True)
            self.open = True
            return PopupPress(None, True, False)

        was_open = self.open
        self.close()
        return PopupPress(None, False, was_open)


class MenuBar:
    """A horizontal strip of :class:`Menu` titles.

    Parameters
    ----------
    menus : sequence of Menu
        Left to right.
    title_pad : float, optional
        Padding either side of a title, which is what sets how far apart the
        names sit.

    Attributes
    ----------
    viewport : tuple of float
        Handed to every menu so a panel dropped from the far right title flips
        rather than running off the edge. :meth:`draw` fills it in from the
        strip it is given when a host has not set it.
    """

    def __init__(self, menus: Sequence[Menu] = (), title_pad: float = 10.0) -> None:
        self.menus: list[Menu] = list(menus)
        self.title_pad = float(title_pad)
        self.viewport: tuple[float, float] | None = None
        self._box: tuple[float, float, float, float] | None = None
        self._titles: list[tuple[Menu, tuple[float, float, float, float]]] = []

    def set_viewport(self, width: float, height: float) -> None:
        """Tell the bar and every menu on it where the edges are.

        Parameters
        ----------
        width, height : float
            The viewport.
        """
        self.viewport = (float(width), float(height))
        for menu in self.menus:
            menu.set_viewport(width, height)

    def close(self, keep: Menu | None = None) -> None:
        """Put every menu away.

        Parameters
        ----------
        keep : Menu, optional
            One to leave as it is -- the one a press is about to open.
        """
        for menu in self.menus:
            if menu is not keep:
                menu.close()

    def title_width(self, p: Painter, menu: Menu) -> float:
        """How wide a title sits on the bar.

        Parameters
        ----------
        p : Painter
            Used to measure.
        menu : Menu
            The menu.

        Returns
        -------
        float
            Its label's width plus padding either side.
        """
        return p.text_width(menu.label) + 2.0 * self.title_pad

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the strip, its titles, and any panel that is down.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The strip.
        """
        self._box = (x, y, w, h)
        viewport = self.viewport or (max(x + w, _UNBOUNDED[0]), _UNBOUNDED[1])
        p.fill_rect(x, y, w, h, style.MENU_BAR_BG)

        self._titles = []
        title_x = x
        for menu in self.menus:
            title_w = self.title_width(p, menu)
            menu.horizontal = True
            menu.viewport = viewport
            for entry in menu.entries:
                if isinstance(entry, Menu):
                    entry.set_viewport(*viewport)
            self._titles.append((menu, (title_x, y, title_w, h)))
            title_x += title_w

        p.push_clip(x, y, w, h)
        try:
            for menu, rect in self._titles:
                menu.draw_row(p, *rect)
        finally:
            p.pop_clip()

        for menu, rect in self._titles:
            if menu.open:
                menu.draw_panel(p, *rect)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> PopupPress:
        """Process a press against the bar and anything it has open.

        A press picks the menu whose *label extent* contains it -- the title's
        own box, not an equal share of the strip: names are not equally long,
        and a bar that divides its width evenly puts the wrong menu under half
        of its own titles.

        Parameters
        ----------
        x, y : float
            The press. It need not be inside the strip: an open panel hangs
            below it.
        box_x, box_y, box_w, box_h : float
            The strip, as last drawn.

        Returns
        -------
        PopupPress
            ``item`` is the row that fired anywhere on the bar.
        """
        for menu, rect in self._titles:
            if not menu.open:
                continue
            result = menu.press(x, y, *rect)
            if result.item is not None or result.consumed:
                return result

        for menu, rect in self._titles:
            if style.hit(x, y, *rect):
                self.close(keep=menu)
                return menu.press(x, y, *rect)

        if style.hit(x, y, box_x, box_y, box_w, box_h):
            self.close()
            return PopupPress(None, True, False)

        self.close()
        return _IGNORED


class Popup:
    """A free-floating panel anchored at a point, dismissed by a press outside.

    Unlike every other control here, the box handed to :meth:`draw` is **not**
    where the popup goes -- it is the viewport the popup must stay inside. The
    popup's own position is :attr:`anchor`, and :func:`best_popup_pos` moves it
    off that anchor as far as it must to keep the whole panel on screen: down
    and right by preference, up and left near the far corner.

    Parameters
    ----------
    entries : sequence, optional
        As :class:`Menu`.
    title : str, optional
        A caption drawn bold at the top.

    Attributes
    ----------
    open : bool
        Whether the panel is up. Opened with :meth:`open_at`.
    anchor : tuple of float or None
        Where it was asked to appear. ``None`` centres it in the viewport, which
        is what the reference does for modals.
    modal : bool
        False here; see :class:`PopupModal`.
    """

    #: Whether presses outside the panel are swallowed rather than passed on.
    modal = False

    def __init__(self, entries: Sequence[Entry] = (), title: str = "") -> None:
        self.entries: list[Entry] = list(entries)
        self.title = str(title)
        self.open = False
        self.anchor: tuple[float, float] | None = None
        self.last_dir: str | None = None
        self._panel: tuple[float, float, float, float] | None = None
        self._rows: list[Row] = []

    # ------------------------------------------------------------------ #
    def open_at(self, x: float | None = None, y: float | None = None) -> None:
        """Put the panel up at a point.

        Parameters
        ----------
        x, y : float, optional
            Where. Omit both to centre it in the viewport.
        """
        self.anchor = None if x is None or y is None else (float(x), float(y))
        self.last_dir = None
        self.open = True

    def close(self) -> None:
        """Put the panel away, and every submenu in it."""
        self.open = False
        for entry in self.entries:
            if isinstance(entry, Menu):
                entry.close()

    def panel_size(self, p: Painter) -> tuple[float, float]:
        """Measure the ``(width, height)`` the panel needs for its entries.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            ``(width, height)``.
        """
        width, height, _row_h, _title_h, _shortcut_w = _panel_metrics(
            p, self.entries, self.title
        )
        return (width, height)

    @property
    def panel_rect(self) -> tuple[float, float, float, float] | None:
        """Where the panel was last painted, as ``(x, y, w, h)``, or ``None``."""
        return self._panel

    def contains(self, x: float, y: float) -> bool:
        """Whether a point is on the panel or on an open submenu of it.

        Parameters
        ----------
        x, y : float
            The point.

        Returns
        -------
        bool
            True if the point is over the popup.
        """
        if not self.open:
            return False
        if self._panel is not None and style.hit(x, y, *self._panel):
            return True
        return any(
            isinstance(entry, Menu) and entry.open and entry.contains(x, y)
            for entry in self.entries
        )

    # ------------------------------------------------------------------ #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the popup inside a viewport.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The **viewport** the panel must stay inside, not the panel's own
            box. A closed popup draws nothing at all.
        """
        if not self.open:
            return
        if self.modal:
            p.fill_rect(x, y, w, h, style.MODAL_DIM_BG)

        width, height = self.panel_size(p)
        if self.anchor is None:
            ref = (x + (w - width) * 0.5, y + (h - height) * 0.5)
        else:
            ref = self.anchor
        avoid = (ref[0], ref[1], ref[0], ref[1])
        pos_x, pos_y, self.last_dir = best_popup_pos(
            ref, (width, height), (x, y, x + w, y + h), avoid, self.last_dir
        )
        self._panel = (pos_x, pos_y, width, height)
        self._rows = _lay_rows(p, pos_x, pos_y, width, self.entries, self.title,
                               (x + w, y + h))
        _paint_panel(p, pos_x, pos_y, width, height, self._rows, self.title)

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> PopupPress:
        """Process a press against the popup.

        Parameters
        ----------
        x, y : float
            The press.
        box_x, box_y, box_w, box_h : float
            The viewport handed to :meth:`draw`. Unused by a plain popup -- a
            press is outside it or not -- and taken for the same reason every
            other control takes its box: so a host routes presses one way.

        Returns
        -------
        PopupPress
            A press outside a plain popup closes it and is **not** consumed:
            in the reference the click that dismisses a popup still reaches
            what is behind it.
        """
        if not self.open:
            return _IGNORED

        if self._rows:
            result = _route(self._rows, x, y)
            if result.item is not None:
                self.close()
                return PopupPress(result.item, True, True)
            if result.consumed:
                return result
        if self._panel is not None and style.hit(x, y, *self._panel):
            return PopupPress(None, True, False)

        return self._press_outside()

    def _press_outside(self) -> PopupPress:
        """Report what a press that missed the panel does.

        Returns
        -------
        PopupPress
            Closed and not consumed, for a plain popup.
        """
        self.close()
        return PopupPress(None, False, True)


class PopupModal(Popup):
    """A :class:`Popup` that takes every press, inside it or not.

    Two things separate it from a plain popup, and they are the two the
    reference gives it: a wash of :data:`~cmtk.style.MODAL_DIM_BG`
    over everything behind, and a press outside that is **swallowed** rather
    than passed through -- ``WantCaptureMouse`` is forced true while a modal is
    up, and ``ClosePopupsExceptModals`` steps over it. So a stray click cannot
    dismiss it, and cannot reach the scene either; the host closes it with
    :meth:`close` when the dialog is answered.

    Parameters
    ----------
    entries : sequence, optional
        As :class:`Menu`.
    title : str, optional
        A caption drawn bold at the top.
    """

    modal = True

    def _press_outside(self) -> PopupPress:
        """Report what a press that missed the panel does.

        Returns
        -------
        PopupPress
            Consumed and *not* closed: that is what modal means.
        """
        return PopupPress(None, True, False)
