"""``ListView`` and ``TreeView``: rows a model owns, and only the visible ones drawn.

Every list in this UI was written twice: the object panel lays out a ``Rect``
per row per frame with no scroll at all, the hierarchy window re-slices its
visible nodes on a hover repaint, and the file dialog, the history panel and
the settings window each carry their own copy of "how tall is the thumb, which
row is under the cursor, what does shift-click select". Five copies that
disagree about the last row, and a sixth that cannot scroll.

This is the one copy, and it is *virtualised*: the view asks the model for the
rows it is about to draw and no others, so a list of a hundred thousand rows
costs the same as a list of twenty. That is the point for the structures this
viewer is meant to open -- an object panel that walks every chain of a nuclear
pore once per mouse move is the reason the chrome's frame cost is what it is.

The pieces
----------
``RowModel`` is the contract: how many rows, what is row *i*, and a
``revision`` that changes when the answer to either would. ``Row`` is what a
row *looks like* -- text, an optional right-hand cell, an indent, a twisty, a
colour -- rather than what it *is*, so a model can be a list of strings, a
scene graph, or a database cursor.

``ListView`` draws them, scrolls them (through the one :class:`ScrollBar`),
tracks hover and selection (through the one :class:`MultiSelectState`), and
takes input as :class:`~emtk.router.Event` records returning a
:class:`~emtk.router.Verdict` -- so the thumb drag is a *capture*, the
same one the canvas and the chrome now use, rather than a sixth ``_held`` flag
somebody has to remember to clear.

``TreeView`` is the same view over ``TreeRows``, which flattens a tree to the
rows its expansion state makes visible. Clicking a twisty expands; everything
else about it is a list.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Optional, Protocol, Sequence

from ..keys import KEY_DOWN, KEY_END, KEY_HOME, KEY_LEFT, KEY_PAGE_DOWN, KEY_PAGE_UP, KEY_RIGHT, KEY_UP
from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Painter
from ..router import Capture, Consumed, Event, Pass, Verdict
from ..style import (
    Colour,
    DIM as _DIM,
    HEADER as _SEL_HOVER,
    ROW_SEL as _SEL,
    TABLE_ROW_BG as _ROW_EVEN,
    TABLE_ROW_BG_ALT as _ROW_ODD,
    TEXT as _TEXT,
    fit_text,
)
from .basic import ScrollBar
from .selection import MultiSelectState

__all__ = ["ListRows", "ListView", "Row", "RowModel", "TreeItem", "TreeRows", "TreeView"]

#: The twisty, in glyphs the atlas actually bakes (see `test_chrome_atlas`).
_OPEN = "▾"        # ▾
_CLOSED = "▸"      # ▸

#: How far one level of nesting shifts a row, in pixels before ui scaling.
INDENT = 12.0


@dataclass(frozen=True)
class Row:
    """What one row looks like.

    Deliberately presentation, not data: a model turns whatever it holds into
    this, so the view never learns what an object, a file or an undo record is.

    Attributes
    ----------
    text : str
        The label, drawn left-aligned and elided if the row is too narrow.
    right : str
        An optional trailing cell, drawn right-aligned -- a size, a count, a
        revision. Empty means no cell, not an empty one.
    colour, right_colour : tuple, optional
        Overrides for this row alone; ``None`` takes the view's colours.
    indent : int
        Nesting level. ``TreeRows`` fills it in; a flat list leaves it at 0.
    twisty : str
        ``""`` for a leaf, otherwise the glyph to draw in the indent column.
        ``TreeView`` reads it to know where a click expands rather than selects.
    background : tuple, optional
        Overrides the zebra stripe -- how a model marks a row out (the current
        frame, a changed setting) without the view knowing why.
    key : str
        The model's own name for the row, carried back to whoever asked.
    selectable : bool
        A separator or a heading says ``False`` and a click passes over it.
    """

    text: str = ""
    right: str = ""
    colour: Optional[Colour] = None
    right_colour: Optional[Colour] = None
    indent: int = 0
    twisty: str = ""
    background: Optional[Colour] = None
    key: str = ""
    selectable: bool = True


class RowModel(Protocol):
    """What a view needs of whatever holds the rows.

    ``revision`` exists so a view (and a cache above it) can tell "the same
    list" from "a list that has changed" in O(1) -- the alternative is
    re-reading every row every frame to find out, which is the cost this class
    exists to remove.
    """

    revision: int

    def row_count(self) -> int: ...
    def row(self, index: int) -> Row: ...


class ListRows:
    """The simplest model: rows held in a list.

    Parameters
    ----------
    rows : iterable, optional
        :class:`Row` records, or plain strings for a list of labels.
    """

    def __init__(self, rows: Iterable = ()) -> None:
        self.revision = 0
        self._rows: list[Row] = []
        self.set_rows(rows)

    def set_rows(self, rows: Iterable) -> None:
        """Replace the contents, and say so with a new revision."""
        self._rows = [r if isinstance(r, Row) else Row(str(r)) for r in rows]
        self.revision += 1

    def row_count(self) -> int:
        return len(self._rows)

    def row(self, index: int) -> Row:
        return self._rows[index]


class ListView:
    """A scrolling, selectable list that draws only the rows on screen.

    Parameters
    ----------
    model : RowModel
        Where the rows come from.
    row_height : float, optional
        One row, in pixels.
    multi_select : bool, optional
        Whether ctrl and shift extend the selection.
    zebra : bool, optional
        Alternate row backgrounds. Off for lists drawn over a busy panel.
    on_activate : callable, optional
        ``on_activate(index)`` for a double click or Return -- "open this".
    """

    #: Rows one wheel notch moves.
    WHEEL_ROWS = 3

    def __init__(
        self,
        model: RowModel,
        *,
        row_height: float = 15.0,
        multi_select: bool = False,
        zebra: bool = True,
        on_activate: Optional[Callable[[int], None]] = None,
    ) -> None:
        self.model = model
        self.row_height = float(row_height)
        self.zebra = bool(zebra)
        self.on_activate = on_activate
        self.selection = MultiSelectState(model.row_count(), single_select=not multi_select)
        self.scrollbar = ScrollBar()
        self.hovered: Optional[int] = None
        #: The box the last :meth:`draw` used, and the rows it covered.
        self._box: tuple[float, float, float, float] | None = None
        self._visible = 1
        self._held = ""
        self._seen_revision = -1

    # -- geometry ---------------------------------------------------------- #

    def row_count(self) -> int:
        """How many rows the model has *now*, keeping the selection in step."""
        count = self.model.row_count()
        if self.model.revision != self._seen_revision:
            self._seen_revision = self.model.revision
            self.selection.set_count(count)
        return count

    def visible_rows(self, h: float) -> int:
        """How many whole rows fit in a box of height *h*."""
        return max(int(h // self.row_height), 1)

    def row_at(self, x: float, y: float) -> Optional[int]:
        """The row under a point, or ``None`` -- off the list, or on the bar."""
        if self._box is None:
            return None
        box_x, box_y, box_w, box_h = self._box
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            return None
        if self.scrollbar.needed() and x >= box_x + box_w - self.scrollbar.width:
            return None
        index = self.scrollbar.top + int((y - box_y) // self.row_height)
        return index if 0 <= index < self.row_count() else None

    def scroll_to(self, index: int) -> None:
        """Bring a row into view, moving as little as possible."""
        top = self.scrollbar.top
        if index < top:
            self.scrollbar.top = max(index, 0)
        elif index >= top + self._visible:
            self.scrollbar.top = max(index - self._visible + 1, 0)
        self.scrollbar.clamp(self.row_count(), self._visible)

    # -- drawing ----------------------------------------------------------- #

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the rows that fall inside ``(x, y, w, h)`` -- and no others."""
        self._box = (float(x), float(y), float(w), float(h))
        count = self.row_count()
        self._visible = self.visible_rows(h)
        self.scrollbar.clamp(count, self._visible)
        bar = self.scrollbar.width if count > self._visible else 0.0
        content = max(w - bar, 1.0)

        p.push_clip(x, y, content, h)
        top = self.scrollbar.top
        # The virtualisation, in one line: the model is asked for the rows on
        # screen, plus the one straddling the bottom edge, and never for the
        # rest of the list.
        row_y = y
        for index in range(top, min(top + self._visible + 1, count)):
            self.draw_row(p, index, self.model.row(index), x, row_y, content, self.row_height)
            row_y += self.row_height
        p.pop_clip()

        if bar:
            self.scrollbar.draw(p, x + w - bar, y, h)

    def draw_row(
        self, p: Painter, index: int, row: Row, x: float, y: float, w: float, h: float
    ) -> None:
        """Paint one row. Subclasses override this and still get the rest."""
        background = row.background
        if background is None and self.selection.is_selected(index):
            background = _SEL_HOVER if index == self.hovered else _SEL
        elif background is None and index == self.hovered:
            background = _ROW_ODD
        elif background is None and self.zebra and index % 2:
            background = _ROW_ODD
        if background is not None:
            p.fill_rect(x, y, w, h, background)

        pad = 4.0
        left = x + pad + row.indent * INDENT
        if row.twisty:
            p.text(left, y, INDENT, h, ALIGN_VCENTER | ALIGN_LEFT, row.twisty, _DIM)
            left += INDENT

        right_w = (p.text_width(row.right) + pad) if row.right else 0.0
        text_w = max(x + w - pad - right_w - left, 1.0)
        p.text(left, y, text_w, h, ALIGN_VCENTER | ALIGN_LEFT,
               fit_text(p, row.text, text_w), row.colour or _TEXT)
        if row.right:
            p.text(x, y, w - pad, h, ALIGN_VCENTER | ALIGN_RIGHT,
                   row.right, row.right_colour or _DIM)

    # -- input -------------------------------------------------------------- #

    def event(self, ev: Event) -> Verdict:
        """Take one input event. ``Capture(self)`` means "the rest is mine"."""
        handler = getattr(self, "_on_" + ev.kind, None)
        return handler(ev) if handler is not None else Pass

    def _on_press(self, ev: Event) -> Verdict:
        if self._box is None:
            return Pass
        box_x, box_y, box_w, box_h = self._box
        if not (box_x <= ev.x <= box_x + box_w and box_y <= ev.y <= box_y + box_h):
            return Pass
        if self.scrollbar.needed() and self.scrollbar.press(ev.x, ev.y):
            self._held = "bar"
            return Capture(self)
        index = self.row_at(ev.x, ev.y)
        if index is None:
            return Consumed
        if self.press_row(index, ev):
            return Capture(self)
        return Consumed

    def press_row(self, index: int, ev: Event) -> bool:
        """A press landed on a row. Returns whether it starts a drag.

        Split out because ``TreeView`` needs the twisty to happen *here*, in
        front of the selection, without copying the hit test above.
        """
        from ..events import CONTROL_MODIFIER, SHIFT_MODIFIER

        row = self.model.row(index)
        if not row.selectable:
            return False
        self.selection.click(
            index,
            ctrl=bool(ev.modifiers & CONTROL_MODIFIER),
            shift=bool(ev.modifiers & SHIFT_MODIFIER),
        )
        if ev.clicks > 1 and self.on_activate is not None:
            self.on_activate(index)
        self._held = "rows"
        return True

    def _on_move(self, ev: Event) -> Verdict:
        if self._held == "bar":
            self.scrollbar.drag(ev.y)
            return Consumed
        index = self.row_at(ev.x, ev.y)
        if self._held == "rows":
            # A drag across rows extends the selection, which is what a list
            # that answers a shift-click ought to do with a held button too.
            if index is not None and not self.selection.single_select:
                self.selection.click(index, shift=True)
            return Consumed
        if index != self.hovered:
            self.hovered = index
            return Consumed
        return Pass if index is None else Consumed

    def _on_release(self, ev: Event) -> Verdict:
        held, self._held = self._held, ""
        self.scrollbar.release()
        return Consumed if held else Pass

    def _on_cancel(self, ev: Event) -> Verdict:
        self._held = ""
        self.scrollbar.release()
        return Consumed

    def _on_leave(self, ev: Event) -> Verdict:
        self.hovered = None
        return Consumed

    def _on_wheel(self, ev: Event) -> Verdict:
        steps = int(ev.wheel_dy) or (1 if ev.wheel_dy > 0 else -1 if ev.wheel_dy else 0)
        if not steps:
            return Pass
        self.scrollbar.scroll(-steps * self.WHEEL_ROWS)
        # Consumed whether or not it moved: at the top or the bottom the list
        # has nowhere to go, and letting the notch fall through there scrolls
        # whatever is behind the panel the reader is looking at.
        return Consumed

    def _on_key_press(self, ev: Event) -> Verdict:
        count = self.row_count()
        if not count:
            return Pass
        current = self.selection.anchor
        moves = {
            KEY_UP: -1,
            KEY_DOWN: 1,
            KEY_PAGE_UP: -self._visible,
            KEY_PAGE_DOWN: self._visible,
        }
        if ev.key in moves:
            start = 0 if current is None else current
            index = min(max(start + moves[ev.key], 0), count - 1)
        elif ev.key == KEY_HOME:
            index = 0
        elif ev.key == KEY_END:
            index = count - 1
        else:
            return Pass
        self.selection.click(index)
        self.scroll_to(index)
        return Consumed

    # -- the shapes the chrome's panels already speak ----------------------- #

    def press(self, x: float, y: float, modifiers: int = 0, clicks: int = 1) -> bool:
        """A press, for a caller that has not been converted to events yet."""
        verdict = self.event(Event("press", x, y, modifiers=modifiers, clicks=clicks))
        return verdict is not Pass

    def drag(self, x: float, y: float) -> bool:
        return self.event(Event("move", x, y, buttons=1)) is Consumed

    def release(self) -> None:
        self.event(Event("release"))

    def wheel(self, steps: int) -> bool:
        return self.event(Event("wheel", wheel_dy=steps)) is Consumed


# ---------------------------------------------------------------------------- #
# Trees
# ---------------------------------------------------------------------------- #


@dataclass
class TreeItem:
    """One node of a tree, as the model holds it (not as it is drawn)."""

    key: str
    text: str
    right: str = ""
    colour: Optional[Colour] = None
    children: Sequence["TreeItem"] = field(default_factory=tuple)


class TreeRows:
    """A tree, flattened to the rows its expansion state makes visible.

    The flattening is cached against ``(revision, expanded)``: a hover repaint
    re-slices nothing, which is what the hierarchy window does today on every
    frame it draws.

    Parameters
    ----------
    roots : sequence of TreeItem, optional
    expanded : set of str, optional
        Keys that start open. Everything else starts closed.
    """

    def __init__(self, roots: Sequence[TreeItem] = (), expanded: Optional[set] = None) -> None:
        self.revision = 0
        self._roots: tuple[TreeItem, ...] = tuple(roots)
        self.expanded: set[str] = set(expanded or ())
        self._flat: list[tuple[TreeItem, int]] = []
        self._cache_key: tuple | None = None

    def set_roots(self, roots: Sequence[TreeItem]) -> None:
        self._roots = tuple(roots)
        self.revision += 1

    def is_expanded(self, key: str) -> bool:
        return key in self.expanded

    def toggle(self, key: str) -> bool:
        """Open or close a node. Returns whether it is open afterwards."""
        if key in self.expanded:
            self.expanded.discard(key)
            open_now = False
        else:
            self.expanded.add(key)
            open_now = True
        self.revision += 1
        return open_now

    def _flatten(self) -> list[tuple[TreeItem, int]]:
        key = (self.revision, frozenset(self.expanded))
        if self._cache_key == key:
            return self._flat
        out: list[tuple[TreeItem, int]] = []

        def walk(nodes, depth):
            for node in nodes:
                out.append((node, depth))
                if node.children and node.key in self.expanded:
                    walk(node.children, depth + 1)

        walk(self._roots, 0)
        self._flat, self._cache_key = out, key
        return out

    def node_at(self, index: int) -> TreeItem:
        """The node a row index stands for."""
        return self._flatten()[index][0]

    def row_count(self) -> int:
        return len(self._flatten())

    def row(self, index: int) -> Row:
        node, depth = self._flatten()[index]
        twisty = ""
        if node.children:
            twisty = _OPEN if node.key in self.expanded else _CLOSED
        return Row(
            text=node.text,
            right=node.right,
            colour=node.colour,
            indent=depth,
            twisty=twisty,
            key=node.key,
        )


class TreeView(ListView):
    """A :class:`ListView` whose model is a :class:`TreeRows`.

    The only thing it adds is where a click means *expand* rather than
    *select*: the twisty column of a row that has children. Left and right
    close and open, as every tree does.
    """

    def __init__(self, model: TreeRows, **kwargs) -> None:
        super().__init__(model, **kwargs)
        self.model: TreeRows = model

    def _twisty_hit(self, index: int, x: float) -> bool:
        if self._box is None:
            return False
        row = self.model.row(index)
        if not row.twisty:
            return False
        left = self._box[0] + 4.0 + row.indent * INDENT
        return left <= x <= left + INDENT

    def press_row(self, index: int, ev: Event) -> bool:
        if self._twisty_hit(index, ev.x):
            self.model.toggle(self.model.row(index).key)
            return False
        return super().press_row(index, ev)

    def _on_key_press(self, ev: Event) -> Verdict:
        index = self.selection.anchor
        if index is not None and ev.key in (KEY_LEFT, KEY_RIGHT) and index < self.row_count():
            row = self.model.row(index)
            if row.twisty:
                open_now = self.model.is_expanded(row.key)
                if (ev.key == KEY_RIGHT) != open_now:
                    self.model.toggle(row.key)
                return Consumed
            return Consumed
        return super()._on_key_press(ev)
