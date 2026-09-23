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
  is not ported (emtk has no per-item icons); the other three are.
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
  clock and a hover feed, and emtk has neither here. Submenus open on
  **press**. :attr:`MenuItem.hovered` is a plain attribute a host may set if it
  has hover information; nothing in this module reads a clock.
* **Keyboard navigation of bar menus.** The reference's menus are fully
  navigable, through a global input context. A :class:`Popup` takes keys
  through :meth:`Popup.key` (up, down, Enter, Escape, and -- in a combo's
  list -- a filter typed into a field at its top), which is what a combo's
  list and a context menu need; a :class:`MenuBar` leaves keys to the host.

A :class:`Popup` taller than its viewport is capped to it and **scrolls** (the
wheel, a scrollbar, the keyboard), and one opened under a field
(:meth:`Popup.open_below`) is the list of a combo box: as wide as the field and
its widest row, below it or flipped above it, never outside the viewport. A
long one has a **filter** at its top (:data:`FILTER_MIN_ITEMS`): what is typed
narrows the list to the rows that contain every word of it, in any order.
:mod:`emtk.overlays` draws one over an immediate-mode frame and feeds it the
frame's input.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Union

from .. import style
from ..keys import (KEY_BACKSPACE, KEY_DOWN, KEY_END, KEY_ENTER, KEY_ESCAPE, KEY_HOME, KEY_PAGE_DOWN,
                    KEY_PAGE_UP, KEY_RETURN, KEY_UP)
from ..painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Painter

__all__ = [
    "PAD",
    "SPACING",
    "OVERLAP",
    "ROW_SCALE",
    "MARK_SCALE",
    "SEPARATOR_SCALE",
    "SCROLLBAR_W",
    "WHEEL_ROWS",
    "FILTER_MIN_ITEMS",
    "FILTER_PLACEHOLDER",
    "NO_MATCH",
    "filter_marks",
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

#: A :class:`Popup`'s fill: the style's popup colour, opaque.
_OPAQUE_POPUP_BG = (*tuple(style.POPUP_BG)[:3], 255)

#: Width of a scrolling popup's scrollbar, in logical pixels.
SCROLLBAR_W = 10.0

#: Rows one notch of the wheel scrolls a popup by.
WHEEL_ROWS = 3

#: A combo's list of at least this many items opens with a filter field at its
#: top; a shorter one is read at a glance and has none. The same for every
#: host; :func:`emtk.overlays.combo_list` takes ``filter=`` to force either.
FILTER_MIN_ITEMS = 8

#: What an empty filter field says.
FILTER_PLACEHOLDER = "filter…"

#: The dim row a filter that matches nothing leaves in the list.
NO_MATCH = "no match"

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


def filter_marks(label: str, query: str) -> list[tuple[int, int]] | None:
    """Where *query* matches *label*, or ``None`` when it does not.

    The query is split at whitespace and **every** word must occur in the
    label, case-insensitively, in any order: "tau gr" matches "Tau (green)".
    The result is the matched ``(start, end)`` spans, sorted and merged -- what
    a row draws highlighted; an empty query matches with no spans.
    """
    words = query.lower().split()
    text = label.lower()
    spans: list[tuple[int, int]] = []
    for word in words:
        at = text.find(word)
        if at < 0:
            return None
        spans.append((at, at + len(word)))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


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


def _ellipsize(p: Painter, text: str, room: float) -> str:
    """*text*, or its longest prefix plus "…" that fits in *room*.

    Half a pixel of slack, as :func:`emtk.style.fit_text` has, so a row sized
    to exactly its label does not lose its last letter to float arithmetic.
    """
    if p.text_width(text) <= room + 0.5:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if p.text_width(text[:mid].rstrip() + "…") <= room + 0.5:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo else "…"


def _wrap(p: Painter, text: str, room: float) -> list[str]:
    """*text* broken into lines no wider than *room*: at spaces where it can,
    mid-word where a word alone is wider."""
    lines: list[str] = []
    line = ""
    for word in text.split(" "):
        trial = f"{line} {word}" if line else word
        if p.text_width(trial) <= room or not line and len(word) <= 1:
            line = trial
            continue
        if line:
            lines.append(line)
        line = ""
        for char in word:
            if line and p.text_width(line + char) > room:
                lines.append(line)
                line = ""
            line += char
    lines.append(line)
    return lines


def _draw_marked(p: Painter, x: float, y: float, room: float, h: float, shown: str,
                 label: str, marks, colour) -> None:
    """Draw *shown* (*label*, perhaps cut) with the *marks* spans in gold.

    The label is drawn in runs, each at the width of the text before it, so
    the letters land where one :meth:`Painter.text` would put them. A cut
    label marks only what is still visible of it.
    """
    visible = len(shown) if shown == label else max(len(shown) - 1, 0)
    cuts = sorted({0, len(shown)} | {min(max(i, 0), visible)
                                     for span in marks for i in span})
    marked = [False] * len(shown)
    for start, end in marks:
        for i in range(min(start, visible), min(end, visible)):
            marked[i] = True
    for start, end in zip(cuts, cuts[1:]):
        if start >= end:
            continue
        left = p.text_width(shown[:start]) if start else 0.0   # some painters measure "" as a glyph
        p.text(x + left, y, max(room - left, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
               shown[start:end], style.GOLD if marked[start] else colour)


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
    marks : tuple of (int, int)
        Spans of the label a filter matched, drawn in the accent colour. Set by
        the :class:`Popup` filtering the row; empty otherwise.
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
        self.marks: tuple[tuple[int, int], ...] = ()

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

        shortcut_w = self._shortcut_width(p)
        mark_left = x + w - PAD - mark_w
        shortcut_right = mark_left - SPACING
        room = self.label_room(p, w)

        colour = style.TEXT if self.enabled else style.TEXT_DISABLED
        shown = _ellipsize(p, self.label, room)
        if self.marks and self.enabled:
            _draw_marked(p, x + PAD, y, room, h, shown, self.label, self.marks, colour)
        else:
            p.text(x + PAD, y, room, h, ALIGN_VCENTER | ALIGN_LEFT, shown, colour)

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

    def _shortcut_width(self, p: Painter) -> float:
        return max(self.column_shortcut_width,
                   p.text_width(self.shortcut) if self.shortcut else 0.0)

    def label_room(self, p: Painter, w: float) -> float:
        """How wide the label may be drawn in a row *w* wide."""
        room = w - 2.0 * PAD - p.line_height() * MARK_SCALE - SPACING
        shortcut_w = self._shortcut_width(p)
        if shortcut_w > 0.0:
            room -= shortcut_w + SPACING
        return max(room, 1.0)

    def cut(self, p: Painter, w: float) -> bool:
        """Whether the label does not fit a row *w* wide, and ends in "…"."""
        return p.text_width(self.label) > self.label_room(p, w) + 0.5

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
        none; emtk's do, because a context menu opened at the pointer has
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

    def cut(self, p: Painter, w: float) -> bool:
        """Whether the label does not fit a row *w* wide."""
        room = w - 2.0 * PAD - p.line_height() * MARK_SCALE - SPACING
        return p.text_width(self.label) > room + 0.5

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
    """A free-floating panel, dismissed by a press outside.

    Unlike every other control here, the box handed to :meth:`draw` is **not**
    where the popup goes -- it is the viewport the popup must stay inside. A
    popup is put up one of two ways:

    * :meth:`open_at` -- at a point (a context menu at the pointer).
      :func:`best_popup_pos` moves it off that point as far as it must to keep
      the whole panel on screen: down and right by preference, up and left near
      the far corner.
    * :meth:`open_below` -- under a field (the list of a combo box). The panel
      is at least as wide as the field and as wide as its widest row; it drops
      below the field when it fits there, flips above when it fits there, and
      otherwise is shifted, as tall as the viewport allows, to cover what it
      must. It never leaves the viewport, on either axis.

    A panel taller than the viewport is capped to it and **scrolls**: the
    wheel (:meth:`wheel`), a scrollbar on its right edge (:meth:`press`,
    :meth:`drag`, :meth:`release`) and the keyboard (:meth:`key`: up, down,
    Home, End, Page up/down, Enter, Escape). A row too long even for the
    viewport ends in "…" and shows its whole text in a tooltip while it is
    highlighted.

    A popup opened with ``filter=True`` (the list of a long combo) has a text
    field at its top that takes what is typed: the list shows only the rows
    containing every word of :attr:`query` (:func:`filter_marks`), with the
    matched letters in gold, or one dim "no match" row. The arrows and Enter
    work among the matches, Backspace edits, and Escape clears the filter
    before it closes the list. While it filters, the panel keeps the place and
    the width it opened with and only gives up height, at the bottom.

    Parameters
    ----------
    entries : sequence, optional
        As :class:`Menu`.
    title : str, optional
        A caption drawn bold at the top.

    Attributes
    ----------
    open : bool
        Whether the panel is up.
    anchor : tuple of float or None
        Where it was asked to appear. ``None`` centres it in the viewport, which
        is what the reference does for modals.
    below : tuple of float or None
        The field ``(x, y, w, h)`` it drops from, after :meth:`open_below`.
    min_width : float
        The narrowest the panel may be (the field's width, for a combo).
    scroll : float
        How far the rows are scrolled, in logical pixels.
    highlight : int or None
        Index into :attr:`entries` of the row under the pointer or the keyboard.
    tooltip : str or None
        The whole text of the highlighted row when the row had to be cut.
    filterable : bool
        Whether the panel has a filter field (see :meth:`open_below`).
    query : str
        What is typed into the filter field.
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
        self.below: tuple[float, float, float, float] | None = None
        self.min_width = 0.0
        self.last_dir: str | None = None
        self.scroll = 0.0
        self.highlight: int | None = None
        self.tooltip: str | None = None
        self.filterable = False
        self.query = ""
        self._panel: tuple[float, float, float, float] | None = None
        self._view: tuple[float, float, float, float] | None = None
        self._rows: list[Row] = []
        self._row_h = 0.0
        self._max_scroll = 0.0
        self._bar: tuple[float, float, float, float] | None = None
        self._thumb: tuple[float, float, float, float] | None = None
        self._grab: float | None = None
        self._reveal: tuple[int, bool] | None = None
        self._pointer: tuple[float, float] | None = None
        self._rehover = False
        self._filter_rect: tuple[float, float, float, float] | None = None

    # ------------------------------------------------------------------ #
    def _reset(self) -> None:
        self.last_dir = None
        self.scroll = 0.0
        self.tooltip = None
        self.query = ""
        self._grab = None
        self._pointer = None
        for entry in self.entries:
            if entry is not None:
                entry.hovered = False
                entry.marks = ()
        self.open = True

    def shown(self) -> list[int]:
        """Indices into :attr:`entries` of the rows the list shows: all of
        them, or -- while a filter is typed -- the items that match it."""
        if not (self.filterable and self.query.strip()):
            return list(range(len(self.entries)))
        return [i for i, entry in enumerate(self.entries)
                if entry is not None and filter_marks(entry.label, self.query) is not None]

    def _filter_h(self, row_h: float) -> float:
        """The height the filter field takes at the top, with its gap."""
        return row_h + PAD * 0.5 if self.filterable else 0.0

    def open_at(self, x: float | None = None, y: float | None = None) -> None:
        """Put the panel up at a point.

        Parameters
        ----------
        x, y : float, optional
            Where. Omit both to centre it in the viewport.
        """
        self.anchor = None if x is None or y is None else (float(x), float(y))
        self.below = None
        self.highlight = None
        self._reveal = None
        self._reset()

    def open_below(self, field: Sequence[float], current: int | None = None,
                   filter: bool = False) -> None:
        """Put the panel up as the list of the field ``(x, y, w, h)``.

        Parameters
        ----------
        field : sequence of float
            The closed control the list belongs to: the panel is at least as
            wide, and drops below it (or flips above it).
        current : int, optional
            Index into :attr:`entries` of the current choice: highlighted, and
            scrolled into view when the panel first draws.
        filter : bool, optional
            Give the list a filter field at its top, which takes the keys.
        """
        fx, fy, fw, fh = (float(v) for v in field)
        self.filterable = bool(filter)
        self.below = (fx, fy, fw, fh)
        self.anchor = (fx, fy + fh)
        self.min_width = fw
        self._reset()
        valid = current is not None and 0 <= current < len(self.entries) \
            and self.entries[current] is not None
        self.highlight = int(current) if valid else None
        self._reveal = (int(current), True) if valid else None
        if valid:
            self.entries[current].hovered = True

    def close(self) -> None:
        """Put the panel away, and every submenu in it."""
        self.open = False
        self._grab = None
        self.tooltip = None
        for entry in self.entries:
            if isinstance(entry, Menu):
                entry.close()

    def panel_size(self, p: Painter) -> tuple[float, float]:
        """Measure the ``(width, height)`` the panel needs for its entries,
        before any viewport caps it.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            ``(width, height)``.
        """
        width, height, row_h, _title_h, _shortcut_w = _panel_metrics(
            p, self.entries, self.title
        )
        return (max(width, self.min_width), height + self._filter_h(row_h))

    @property
    def panel_rect(self) -> tuple[float, float, float, float] | None:
        """Where the panel was last painted, as ``(x, y, w, h)``, or ``None``."""
        return self._panel

    @property
    def view_rect(self) -> tuple[float, float, float, float] | None:
        """The part of the panel the rows scroll in, as last painted."""
        return self._view

    @property
    def max_scroll(self) -> float:
        """How far the rows can scroll; zero when they all fit."""
        return self._max_scroll

    def row_rect(self, index: int) -> tuple[float, float, float, float] | None:
        """Where entry *index* was last painted (scrolled), or ``None``."""
        for entry, rect in self._rows:
            if entry is not None and entry is self.entries[index]:
                return rect
        return None

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
    def place(self, p: Painter, x: float, y: float, w: float, h: float
              ) -> tuple[float, float, float, float]:
        """The panel's ``(x, y, w, h)`` inside the viewport ``(x, y, w, h)``.

        Never outside the viewport: taller than it, the panel is capped to it
        (and scrolls); wider than it, the panel is the viewport's width (and
        its longest rows end in "…").

        The place is worked out from **all** the entries, whatever the filter
        shows, so a list does not move or change width while it is filtered;
        a filtered list is only shorter, from the bottom.
        """
        pos_x, pos_y, pan_w, pan_h = self._place_all(p, x, y, w, h)
        shown = self.shown()
        if len(shown) < len(self.entries):
            _w, need, row_h, _t, _s = _panel_metrics(
                p, [self.entries[i] for i in shown] or [MenuItem(NO_MATCH)], self.title)
            pan_h = min(pan_h, need + self._filter_h(row_h))
        return (pos_x, pos_y, pan_w, pan_h)

    def _place_all(self, p: Painter, x: float, y: float, w: float, h: float
                   ) -> tuple[float, float, float, float]:
        width, height, row_h, _title_h, _shortcut_w = _panel_metrics(
            p, self.entries, self.title
        )
        height += self._filter_h(row_h)
        pan_h = min(height, h)
        if height > h + 0.5:
            width += SCROLLBAR_W
        pan_w = min(max(width, self.min_width), w)
        right, bottom = x + w, y + h
        if self.below is not None:
            fx, fy, _fw, fh = self.below
            if fy + fh + pan_h <= bottom + 0.5:
                pos_y = fy + fh                       # below the field
            elif fy - pan_h >= y - 0.5:
                pos_y = fy - pan_h                    # flipped above it
            else:                                     # shifted to fit
                pos_y = style.clamp(fy + fh, y, bottom - pan_h)
            pos_x = style.clamp(fx, x, right - pan_w)
            return (pos_x, max(pos_y, y), pan_w, pan_h)
        if self.anchor is None:
            ref = (x + (w - pan_w) * 0.5, y + (h - pan_h) * 0.5)
        else:
            ref = self.anchor
        avoid = (ref[0], ref[1], ref[0], ref[1])
        pos_x, pos_y, self.last_dir = best_popup_pos(
            ref, (pan_w, pan_h), (x, y, right, bottom), avoid, self.last_dir
        )
        return (pos_x, pos_y, pan_w, pan_h)

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

        pos_x, pos_y, width, height = self.place(p, x, y, w, h)
        shown = self.shown()
        entries = [self.entries[i] for i in shown]
        _nat_w, nat_h, row_h, title_h, _shortcut_w = _panel_metrics(
            p, entries or [MenuItem(NO_MATCH)], self.title
        )
        head = title_h + self._filter_h(row_h)
        self._row_h = row_h
        self._panel = (pos_x, pos_y, width, height)
        view = (pos_x, pos_y + PAD + head, width, max(height - 2.0 * PAD - head, 0.0))
        self._view = view
        content = nat_h - 2.0 * PAD - title_h
        self._max_scroll = max(content - view[3], 0.0)
        bar_w = SCROLLBAR_W if self._max_scroll > 0.0 else 0.0
        row_w = width - bar_w
        if self._reveal is not None:
            index, centre = self._reveal
            self._reveal = None
            self._reveal_row(p, index, centre, view[3])
        self.scroll = style.clamp(self.scroll, 0.0, self._max_scroll)
        self._rows = _lay_rows(p, pos_x, pos_y + head - title_h - self.scroll, row_w,
                               entries, self.title, (x + w, y + h))
        filtering = self.filterable and bool(self.query.strip())
        for index, entry in enumerate(self.entries):
            if entry is not None:
                entry.hovered = index == self.highlight
                marks = filter_marks(entry.label, self.query) if filtering else None
                entry.marks = tuple(marks or ())

        # Opaque, as emtk's windows are: a list over a form must not show the
        # form's text through its rows.
        p.stroke_rect(pos_x, pos_y, width, height, style.BORDER, _OPAQUE_POPUP_BG)
        if self.title:
            p.text(pos_x + PAD, pos_y + PAD, max(width - 2.0 * PAD, 1.0), row_h,
                   ALIGN_VCENTER | ALIGN_LEFT,
                   style.fit_text(p, self.title, width - 2.0 * PAD), style.GOLD, bold=True)
        p.push_clip(*view)
        try:
            for entry, rect in self._rows:
                if rect[1] + rect[3] < view[1] or rect[1] > view[1] + view[3]:
                    continue
                if entry is None:
                    rule_y = rect[1] + rect[3] * 0.5
                    p.fill_rect(rect[0] + PAD, rule_y, max(rect[2] - 2.0 * PAD, 1.0),
                                1.0, style.SEPARATOR)
                    continue
                entry.draw_row(p, *rect)
            if not entries:
                p.text(pos_x + PAD, view[1], max(row_w - 2.0 * PAD, 1.0), row_h,
                       ALIGN_VCENTER | ALIGN_LEFT, NO_MATCH, style.TEXT_DISABLED)
        finally:
            p.pop_clip()
        self._filter_rect = None
        if self.filterable:
            self._draw_filter(p, pos_x + PAD, pos_y + PAD + title_h,
                              max(width - 2.0 * PAD, 1.0), row_h)
        self._draw_scrollbar(p, view, content)

        for entry, rect in self._rows:
            if isinstance(entry, Menu) and entry.open:
                entry.draw_panel(p, *rect)
        self._draw_tooltip(p, x, y, w, h)

    def _draw_filter(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """The filter field: what is typed and a caret, or a dim placeholder."""
        self._filter_rect = (x, y, w, h)
        p.stroke_rect(x, y, w, h, style.FRAME_BG_ACTIVE, style.FRAME_BG)
        room = max(w - 2.0 * PAD, 1.0)
        if not self.query:
            p.fill_rect(x + PAD, y + 3.0, 1.0, max(h - 6.0, 1.0), style.TEXT)
            p.text(x + PAD + 2.0, y, room, h, ALIGN_VCENTER | ALIGN_LEFT,
                   _ellipsize(p, FILTER_PLACEHOLDER, room), style.DIM)
            return
        text = self.query
        while len(text) > 1 and p.text_width(text) > room - 2.0:
            text = text[1:]                     # a long filter shows its end
        p.push_clip(x, y, w, h)
        try:
            p.text(x + PAD, y, room, h, ALIGN_VCENTER | ALIGN_LEFT, text, style.TEXT)
            caret = min(x + PAD + p.text_width(text) + 1.0, x + w - 2.0)
            p.fill_rect(caret, y + 3.0, 1.0, max(h - 6.0, 1.0), style.TEXT)
        finally:
            p.pop_clip()

    @property
    def filter_rect(self) -> tuple[float, float, float, float] | None:
        """Where the filter field was last painted, or ``None`` without one."""
        return self._filter_rect

    def _reveal_row(self, p: Painter, index: int, centre: bool, view_h: float) -> None:
        """Scroll so entry *index* is in view: centred, or just inside an edge."""
        _w, _h, row_h, _title_h, _sw = _panel_metrics(p, self.entries, self.title)
        shown = self.shown()
        if index not in shown:
            return
        top = 0.0
        for i in shown[:shown.index(index)]:
            top += row_h * SEPARATOR_SCALE if self.entries[i] is None else row_h
        if centre:
            self.scroll = top - (view_h - row_h) * 0.5
        elif top < self.scroll:
            self.scroll = top
        elif top + row_h > self.scroll + view_h:
            self.scroll = top + row_h - view_h

    def _draw_scrollbar(self, p: Painter, view, content: float) -> None:
        self._bar = self._thumb = None
        if self._max_scroll <= 0.0 or view[3] <= 0.0:
            return
        bar = (view[0] + view[2] - SCROLLBAR_W, view[1], SCROLLBAR_W, view[3])
        self._bar = bar
        p.fill_rect(*bar, style.SCROLLBAR_BG)
        span = max(bar[3] * view[3] / max(content, 1.0), min(16.0, bar[3]))
        at = bar[1] + (bar[3] - span) * (self.scroll / self._max_scroll)
        self._thumb = (bar[0] + 2.0, at, SCROLLBAR_W - 4.0, span)
        grabbed = self._grab is not None
        hovered = self._pointer is not None and style.hit(*self._pointer, *self._thumb)
        colour = (style.SCROLLBAR_GRAB_ACTIVE if grabbed
                  else style.SCROLLBAR_GRAB_HOVERED if hovered else style.SCROLLBAR_GRAB)
        p.fill_rect(*self._thumb, colour)

    def _draw_tooltip(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """The whole text of a highlighted row that had to be cut, under it."""
        self.tooltip = None
        if self.highlight is None or self._view is None:
            return
        entry = self.entries[self.highlight]
        rect = self.row_rect(self.highlight)
        if entry is None or rect is None or not entry.cut(p, rect[2]):
            return
        self.tooltip = entry.label
        room = max(w - 2.0 * PAD, 1.0)
        lines = _wrap(p, entry.label, room)
        line_h = p.line_height()
        tip_w = min(max(p.text_width(line) for line in lines) + 2.0 * PAD, w)
        tip_h = line_h * len(lines) + PAD
        tip_x = style.clamp(rect[0] + PAD, x, x + w - tip_w)
        tip_y = rect[1] + rect[3] + 2.0
        if tip_y + tip_h > y + h:
            tip_y = rect[1] - tip_h - 2.0
        tip_y = style.clamp(tip_y, y, y + h - tip_h)
        p.stroke_rect(tip_x, tip_y, tip_w, tip_h, style.BORDER, _OPAQUE_POPUP_BG)
        for i, line in enumerate(lines):
            p.text(tip_x + PAD, tip_y + PAD * 0.5 + i * line_h, tip_w - 2.0 * PAD, line_h,
                   ALIGN_VCENTER | ALIGN_LEFT, line, style.TEXT)

    # ------------------------------------------------------------------ #
    def _row_at(self, x: float, y: float) -> int | None:
        """Index of the entry whose row is under ``(x, y)``, inside the view."""
        if self._view is None or not style.hit(x, y, *self._view):
            return None
        if self._bar is not None and style.hit(x, y, *self._bar):
            return None
        for entry, rect in self._rows:
            if entry is not None and style.hit(x, y, *rect):
                return self.entries.index(entry)
        return None

    def hover(self, x: float, y: float) -> None:
        """The pointer moved to ``(x, y)``: highlight the row under it.

        A pointer that has not moved leaves the highlight alone, so the
        keyboard's highlight survives the next frame.
        """
        if not self.open or (self._pointer == (x, y) and not self._rehover):
            return
        first, self._pointer = self._pointer is None, (x, y)
        self._rehover = False
        if first:
            # Where the pointer rests as the list opens is not a choice: a
            # list shifted over its own field would otherwise trade the
            # current row's highlight for whatever row landed under it.
            return
        index = self._row_at(x, y)
        if index is not None:
            self.highlight = index

    def wheel(self, x: float, y: float, steps: float) -> bool:
        """Scroll by *steps* notches (positive: up). True when over the panel."""
        if not self.contains(x, y):
            return False
        self.scroll = style.clamp(self.scroll - float(steps) * WHEEL_ROWS * self._row_h,
                                  0.0, self._max_scroll)
        self._rehover = True          # the rows moved under a resting pointer
        return True

    def drag(self, x: float, y: float) -> bool:
        """Move the scrollbar's thumb while it is held. True when it was."""
        if self._grab is None or self._bar is None or self._thumb is None:
            return False
        travel = self._bar[3] - self._thumb[3]
        if travel > 0.0:
            self.scroll = style.clamp((y - self._grab - self._bar[1]) / travel
                                      * self._max_scroll, 0.0, self._max_scroll)
        return True

    def release(self) -> None:
        """Let go of the scrollbar's thumb."""
        self._grab = None

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

        if self._bar is not None and style.hit(x, y, *self._bar):
            thumb = self._thumb
            if thumb is not None and thumb[1] <= y <= thumb[1] + thumb[3]:
                self._grab = y - thumb[1]
            else:
                page = self._view[3] if self._view is not None else 0.0
                step = -page if thumb is not None and y < thumb[1] else page
                self.scroll = style.clamp(self.scroll + step, 0.0, self._max_scroll)
            return PopupPress(None, True, False)
        if self._rows:
            in_view = self._view is not None and style.hit(x, y, *self._view)
            rows = self._rows if in_view else [
                (entry, rect) for entry, rect in self._rows
                if isinstance(entry, Menu) and entry.open
            ]
            result = _route(rows, x, y)
            if result.item is not None:
                self.close()
                return PopupPress(result.item, True, True)
            if result.consumed:
                return result
        if self._panel is not None and style.hit(x, y, *self._panel):
            return PopupPress(None, True, False)

        return self._press_outside()

    # ------------------------------------------------------------------ #
    def _navigable(self) -> list[int]:
        return [i for i in self.shown()
                if self.entries[i] is not None and self.entries[i].enabled]

    def set_query(self, query: str) -> None:
        """Filter the list by *query*: the first match is highlighted and the
        list scrolls to its top; cleared, the highlight stays and is shown."""
        query = str(query)
        if query == self.query:
            return
        self.query = query
        rows = self._navigable()
        if query.strip():
            self.highlight = rows[0] if rows else None
            self.scroll = 0.0
            self._reveal = None
        else:
            if self.highlight not in rows:
                self.highlight = rows[0] if rows else None
            self._reveal = (self.highlight, True) if self.highlight is not None else None

    def _go(self, index: int | None) -> None:
        if index is not None:
            self.highlight = index
            self._reveal = (index, False)

    def key(self, key: int, text: str = "") -> PopupPress:
        """Process a key while the popup is up.

        Up/Down move the highlight (Home/End to the ends, Page up/down by a
        page) and Enter activates the highlighted row. With a filter field,
        typed text and Backspace edit the filter, and Escape clears a filter
        before it closes the popup; without one, Escape closes it and text is
        ignored.

        Returns
        -------
        PopupPress
            ``item`` is the row Enter activated. Every key is consumed.
        """
        if not self.open:
            return _IGNORED
        rows = self._navigable()
        at = rows.index(self.highlight) if self.highlight in rows else None
        page = max(int(self._view[3] // self._row_h) - 1, 1) if self._view and self._row_h else 8
        if key == KEY_ESCAPE:
            if self.filterable and self.query:
                self.set_query("")
                return PopupPress(None, True, False)
            self.close()
            return PopupPress(None, True, True)
        if self.filterable and key == KEY_BACKSPACE:
            self.set_query(self.query[:-1])
            return PopupPress(None, True, False)
        if key in (KEY_RETURN, KEY_ENTER):
            if self.highlight is None:
                return PopupPress(None, True, False)
            entry = self.entries[self.highlight]
            if isinstance(entry, Menu):
                entry.open = entry.enabled
                return PopupPress(None, True, False)
            if entry is not None and entry.enabled:
                if entry.checkable:
                    entry.toggle()
                self.close()
                return PopupPress(entry, True, True)
            return PopupPress(None, True, False)
        moves = {KEY_DOWN: 1, KEY_UP: -1, KEY_PAGE_DOWN: page, KEY_PAGE_UP: -page}
        if rows and key in moves:
            step = moves[key]
            if at is None:
                at = -1 if step > 0 else len(rows)
            self._go(rows[max(0, min(len(rows) - 1, at + step))])
        elif rows and key == KEY_HOME:
            self._go(rows[0])
        elif rows and key == KEY_END:
            self._go(rows[-1])
        elif self.filterable and text:
            typed = "".join(ch for ch in text if ch.isprintable())
            if typed:
                self.set_query(self.query + typed)
        return PopupPress(None, True, False)

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
    reference gives it: a wash of :data:`~emtk.style.MODAL_DIM_BG`
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
