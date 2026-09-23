"""Tables declared in a ``view.json``: AutoForm's ``table`` and ``data_table``.

ChiSurf tools declare tables as data. Two dialects exist, and both are read
here, key for key, as the Qt renderer reads them:

``{"type": "table", ...}``
    the built-in record table: ``source`` (a model attribute or zero-argument
    method returning rows), ``columns`` (``key``, ``label``, ``width``,
    ``description``), ``selected_call`` / ``selected_attr`` /
    ``activated_call``, ``height``, ``expand``;
``{"type": "custom", "key": "data_table", "options": {...}}``
    the scalable table: ``source`` (records, or a mapping of equal-length
    arrays), ``columns`` (``key``, ``title``, ``units``, ``visible``,
    ``width``, ``tooltip``), ``selected_call``, ``height``.

and a handful of options both renderers honour, because a ranked or streamed
table needs them and neither dialect had them:

``display: "bar"`` and ``range: [lo, hi]`` on a column
    the value is drawn as a bar under the cell's text, ``(v - lo)/(hi - lo)``
    of the width. A range that spans zero draws a *diverging* bar from the zero
    point, coloured by sign -- a correlation reads at a glance;
``format`` on a column
    printf spec for numbers (``"%.3f"``); numbers otherwise use ``%.6g``;
``columns_source``
    a model method returning the column list, for a table whose columns are
    only known at run time (a score whose name and range depend on a setting);
``sort: {"key", "descending"}``
    the initial order; a header click sorts by that column, again flips it;
``filter: true``
    a filter box above the rows, matching any cell;
``tooltip_key``
    the record field holding a row's longer description: the tooltip of the
    row under the pointer, as in the Qt table, and the selected row's shown
    under the rows;
``row_key``
    the record field that identifies a row, so a selection survives rows
    streaming in above it. Without one, a row is its position in the source;
``editable`` (the section, or one column)
    cells the user may change: a ``True``/``False`` cell is a check box a click
    flips, any other cell opens for typing on a double click (Enter commits,
    Escape cancels, a click elsewhere commits). The new value is written into
    a mutable record and handed to ``edited_call(record, key, value)``;
``delete_call``
    called with the selected record when Delete (or Backspace) is pressed;
``context_call``
    called as ``context_call(record, key, (x, y))`` on a right click: the row
    under the pointer (selected first; ``None`` on the header) and the column
    key. The model opens its own menu there -- a painter has no popup of its
    own;
``colour_source``
    a model attribute (or method) saying how numeric cells are shaded by
    value: ``None`` (not at all), ``"column"`` (each column over its own
    range) or ``"table"`` (one range for every column). A column that says
    ``"shade": false`` is never shaded (a row number, an identifier). The ramp is a hue sweep
    at fixed saturation, as the Qt table's, so the text stays legible;
``reserve`` (with ``expand``)
    the height left free under an expanding table, for the rows after it;
``min_column_width``
    columns never get narrower than this; when they do not fit, the table
    scrolls sideways (a bar under the rows, the horizontal wheel, or shift and
    the wheel);
dotted names
    every model name above (``source``, the ``*_call`` and ``*_attr``
    options, ``columns_source``) may be a dotted path into the model --
    ``"curve_table.rows"`` -- so one form can hold several tables, each an
    object of its own with the same method names;
``editable_call``
    ``editable_call(record, key) -> bool``: whether one cell of an editable
    column may be changed *now* -- a value borrowed from another row, or a
    bound that only counts while its switch is on, is shown but refused;
``muted_key``
    the record field that, when true, draws the row's text dimmed: a row that
    is there to be read, not acted on (a parameter the fit will not move);
``column_picker: true``
    a right click on the header opens a list of the columns, each ticked
    while shown; picking one hides or shows it. The hidden set survives a
    rebind, so a source that streams new columns does not undo the choice;
``fit_columns: true``
    size the columns to their header and contents whenever the rows change;
    spare room is shared out, and a table too wide for its box first narrows
    the columns wider than their header, then scrolls;
``status: true``
    a line under the rows: how many are shown (of how many, while a filter
    narrows them) and across how many columns;
``tree_key`` (with ``row_key``)
    rows form a tree: a record's ``tree_key`` field names its parent's
    ``row_key`` (empty for a top-level row). A row with children draws a
    disclosure triangle in the first column; a click on it (a double click
    on the row, or Right/Left) expands or collapses it. Children stay under
    their parent whatever the sort, are indented a step per level, and are
    shown while a filter matches them or their parent;
``expanded_attr``
    a model attribute holding the ``set`` of expanded row keys. The table
    reads and writes that set, so the model can open a row itself and the
    choice survives a rebind; without one the table keeps its own.

A cell whose text is shortened to fit its column shows the whole text as its
tooltip.

:meth:`DataTable.fit_columns` sizes the columns to their contents on the next
draw, and :attr:`DataTable.column_filters` narrows the rows by the text of one
column each (``{key: text}``), on top of the filter box.

A ``True``/``False`` cell is drawn as a check box whether or not it is
editable. Colours are read from :mod:`emtk.style` as the table draws, so a
palette the application installs (:func:`emtk.style.use_palette`) applies.

Values are sorted as values, never as their text, and only the visible rows are
drawn, so a table of a hundred thousand rows costs what twenty cost.

:class:`TableBinding` owns the reading of a section against a model and the
refresh when the source grows; :class:`DataTable` is the retained control that
draws and takes input (``draw``/``press``/``drag``/``release``/``hover``/
``scroll``/``key``, the contract ``ControlHost`` drives); :func:`draw_table`
puts a binding into an immediate-mode window.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

from .. import style as _style
from ..keys import (
    KEY_BACKSPACE,
    KEY_DELETE,
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
    KEY_RIGHT,
    KEY_UP,
)
from ..painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Painter
from ..style import fit_text
from .basic import ScrollBar, TextInput

__all__ = [
    "BAR_COLOUR",
    "NEGATIVE_COLOUR",
    "POSITIVE_COLOUR",
    "TableColumn",
    "DataTable",
    "TableBinding",
    "is_table_section",
    "draw_table",
    "parse_number",
]

#: A bar whose range does not span zero.
BAR_COLOUR = (90, 150, 220, 255)
#: A diverging bar right of zero, and left of it (Orange3's correlation colours).
POSITIVE_COLOUR = (170, 242, 43, 255)
NEGATIVE_COLOUR = (70, 190, 250, 255)

#: Number format when a column names none; the Qt table's default.
DEFAULT_FORMAT = "%.6g"


def is_table_section(section: Mapping) -> bool:
    """Whether *section* declares a table this module renders."""
    kind = str(section.get("type", "")).strip().lower()
    if kind == "table":
        return True
    return kind == "custom" and str(section.get("key", "")).strip().lower() == "data_table"


@dataclass(frozen=True)
class TableColumn:
    """One column, as a spec declares it.

    Attributes
    ----------
    key : str
        Record field (or array name) the column shows.
    title : str
        Header text.
    width : float
        Preferred pixel width; ``0`` shares what the sized columns leave.
    fmt : str
        printf spec for numbers; empty uses :data:`DEFAULT_FORMAT`.
    display : str
        ``"text"`` or ``"bar"``.
    range : tuple or None
        ``(lo, hi)`` for a bar.
    tooltip : str
        What the column means.
    visible : bool
        Hidden columns are neither drawn nor filtered on.
    align_right : bool
        Numbers read best right-aligned; set from the first value if not given.
    editable : bool
        Whether the user may change the column's cells.
    """

    key: str
    title: str = ""
    width: float = 0.0
    fmt: str = ""
    display: str = "text"
    range: Optional[tuple] = None
    tooltip: str = ""
    visible: bool = True
    align_right: Optional[bool] = None
    editable: bool = False
    #: Whether value shading applies to this column; a row number or an
    #: identifier is a number that has no magnitude worth a colour.
    shade: bool = True

    @classmethod
    def from_spec(cls, spec: Mapping, editable: bool = False) -> "TableColumn":
        """Read either dialect's column mapping."""
        key = str(spec.get("key", ""))
        title = spec.get("title", spec.get("label", "")) or key
        units = spec.get("units")
        if units:
            title = f"{title} ({units})"
        span = spec.get("range")
        align = spec.get("align")
        return cls(
            key=key,
            title=str(title),
            width=float(spec.get("width", 0) or 0),
            fmt=str(spec.get("format", spec.get("fmt", "")) or ""),
            display=str(spec.get("display", "text") or "text").lower(),
            range=(float(span[0]), float(span[1])) if span and len(span) == 2 else None,
            tooltip=str(spec.get("tooltip", spec.get("description", "")) or ""),
            visible=bool(spec.get("visible", True)),
            align_right=None if align is None else str(align).lower() == "right",
            editable=bool(spec.get("editable", editable)),
            shade=bool(spec.get("shade", True)),
        )

    def text(self, value: Any) -> str:
        """The cell text for *value*."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, (int, float)) or hasattr(value, "__float__") and not isinstance(value, str):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value)
            if number != number:  # NaN
                return "N/A"
            if isinstance(value, int) and not self.fmt:
                return str(value)
            try:
                return (self.fmt or DEFAULT_FORMAT) % number
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    def bar(self, value: Any) -> Optional[tuple]:
        """``(start, end, colour)`` as fractions of the cell width, or ``None``."""
        if self.display != "bar" or self.range is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number:
            return None
        lo, hi = self.range
        if not hi > lo:
            return None

        def at(v: float) -> float:
            return min(max((v - lo) / (hi - lo), 0.0), 1.0)

        if lo < 0.0 < hi:
            zero, point = at(0.0), at(number)
            colour = POSITIVE_COLOUR if number >= 0 else NEGATIVE_COLOUR
            return (min(zero, point), max(zero, point), colour)
        return (0.0, at(number), BAR_COLOUR)


def _ramp(fraction: float) -> tuple:
    """The value shade: blue at a range's top to green at its bottom, half opaque.

    Hue sweeps 0.66 -> 0.99 at saturation 0.7 and value 1.0 (the Qt table's
    ramp), so the cell text stays readable on every shade.
    """
    import colorsys

    fraction = min(max(float(fraction), 0.0), 1.0)
    hue = (0.66 + 0.33 * fraction) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 1.0)
    return (int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5), 110)


def _np_bool():
    """numpy's bool type when numpy is loaded, for ``isinstance`` checks."""
    import sys

    numpy = sys.modules.get("numpy")
    return numpy.bool_ if numpy is not None else bool


def _is_number(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def parse_number(text: str) -> float:
    """A number as typed or as a table shows it.

    Accepts the typographic minus (U+2212) a formatted cell or a pasted
    value carries, and ``∞``/``−∞`` for an open bound, besides what
    :func:`float` reads. Raises :class:`ValueError` for anything else.
    """
    cleaned = str(text).strip().replace("\u2212", "-").replace("\u221e", "inf")
    cleaned = cleaned.replace("\u2009", "").replace(" ", "")
    return float(cleaned)


def _sort_key(value: Any) -> tuple:
    """Numbers before text; NaN and missing last."""
    if value is None:
        return (2, 0.0, "")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return (2, 0.0, "") if number != number else (0, number, "")
    try:
        number = float(value)  # numpy scalars
        if not isinstance(value, str):
            return (2, 0.0, "") if number != number else (0, number, "")
    except (TypeError, ValueError):
        pass
    return (1, 0.0, str(value).lower())


class DataTable:
    """A sortable, filterable, virtualised table over records.

    Parameters
    ----------
    columns : sequence of TableColumn
        Left to right.
    on_select : callable, optional
        ``on_select(index)`` with the **source index** of the row the user
        selected (by click or arrow key), ``None`` when the selection is
        cleared. Not called by :meth:`select_key`.
    on_activate : callable, optional
        ``on_activate(index)`` on a double click that does not open a cell.
    on_edit : callable, optional
        ``on_edit(index, key, value)`` when the user changed a cell.
    on_delete : callable, optional
        ``on_delete(index)`` when Delete is pressed on the selected row.
    filter_box : bool
        Draw a filter box above the rows.
    tooltip_key : str
        Record field shown under the rows for the selected row.
    row_key : str
        Record field that identifies a row; the source index otherwise.
    row_scale : float
        Row height as a multiple of the line height.
    """

    WHEEL_ROWS = 3
    #: Indent per tree level, and the room of the disclosure triangle.
    TREE_INDENT = 14.0

    def __init__(
        self,
        columns: Sequence[TableColumn] = (),
        *,
        on_select: Optional[Callable[[Optional[int]], None]] = None,
        on_activate: Optional[Callable[[int], None]] = None,
        filter_box: bool = False,
        tooltip_key: str = "",
        row_key: str = "",
        row_scale: float = 1.45,
        on_edit: Optional[Callable[[int, str, Any], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
        on_context: Optional[Callable[[Optional[int], Optional[str], float, float], None]] = None,
        min_column_width: float = 0.0,
        cell_editable: Optional[Callable[[int, str], bool]] = None,
        muted: Optional[Callable[[int], bool]] = None,
        status: bool = False,
        column_picker: bool = False,
        tree_key: str = "",
    ) -> None:
        self.columns: list[TableColumn] = list(columns)
        #: Record field naming a row's parent (its ``row_key``); ``""``: a flat table.
        self.tree_key = str(tree_key or "")
        #: Keys of the expanded rows of a tree.
        self.expanded: set = set()
        self._depth: dict = {}
        self._has_children: set = set()
        #: ``(source index, column key) -> full text`` of the cells drawn shortened.
        self._elided: dict = {}
        #: ``cell_editable(index, key)``: whether an editable column's cell at
        #: source *index* may be changed now. ``None`` allows every one.
        self.cell_editable = cell_editable
        #: ``muted(index)``: whether the row's text is drawn dimmed.
        self.muted = muted
        #: Draw the row/column count under the rows.
        self.show_status = bool(status)
        #: A right click on the header asks for the column list.
        self.column_picker = bool(column_picker)
        #: Keys of the columns the user hid through the picker.
        self.hidden: set = set()
        #: Where the header was right-clicked, while the column list is due.
        self.picker_at: Optional[tuple] = None
        #: The column list while it is open (a :class:`~.menus.Popup`).
        self.picker_panel: Any = None
        self._picker_keys: list = []
        self.on_select = on_select
        self.on_activate = on_activate
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_context = on_context
        #: ``None``, ``"column"`` or ``"table"``: how numeric cells are shaded.
        self.colour_values: Optional[str] = None
        self._colour_ranges: dict = {}
        self._colour_for: tuple = ()
        #: ``{column key: text}``: rows whose cell in that column contains it.
        self.column_filters: dict[str, str] = {}
        #: Narrowest a column is drawn; wider tables scroll sideways.
        self.min_column_width = float(min_column_width)
        #: Index (among the visible columns) of the leftmost column drawn.
        self.first_column = 0
        self._fit_pending = False
        self._fitted: dict[str, float] = {}
        #: Header widths, from the last measure: a column is not squeezed below it.
        self._title_w: dict[str, float] = {}
        #: Size the columns to their contents whenever the rows change.
        self.auto_fit = False
        self._fitted_for = -1
        self._shown: list[TableColumn] = []
        self._hbar_box: Optional[tuple] = None
        self._hbar_held = False
        #: ``(source index, column key)`` of the cell being typed into.
        self.editing: Optional[tuple] = None
        self.editor = TextInput("", "")
        self._editor_box: Optional[tuple] = None
        self.show_filter = bool(filter_box)
        self.tooltip_key = str(tooltip_key or "")
        self.row_key = str(row_key or "")
        self.row_scale = float(row_scale)
        self.records: Sequence[Any] = ()
        self.arrays: Optional[Mapping[str, Sequence]] = None
        self.sort_key_name: Optional[str] = None
        self.descending = False
        self.filter = TextInput("", "", placeholder="filter")
        self.filter_focused = False
        self.selected_key: Any = None
        #: Keys of rows selected *besides* :attr:`selected_key` (Select All);
        #: a click on a row or a move of the selection clears them.
        self.also_selected: set = set()
        self.hovered: Optional[int] = None
        self.bar = ScrollBar()
        self.revision = 0
        self._order: list[int] = []
        self._order_for: tuple = ()
        self._filter_box: Optional[tuple] = None
        self._header_box: Optional[tuple] = None
        self._body_box: Optional[tuple] = None
        self._widths: list[float] = []
        self._row_h = 20.0
        self._visible = 1

    # -- contents ---------------------------------------------------------------- #

    def set_records(self, records: Sequence[Any]) -> None:
        """Show *records*: mappings or objects, one per row."""
        self.records = records
        self.arrays = None
        self.revision += 1

    def set_arrays(self, arrays: Mapping[str, Sequence]) -> None:
        """Show a mapping of equal-length columns."""
        self.arrays = arrays
        self.records = ()
        self.revision += 1

    def changed(self) -> None:
        """The source changed in place (rows appended): recompute order and rows."""
        self.revision += 1

    def row_count(self) -> int:
        """Rows in the source."""
        if self.arrays is not None:
            return min((len(v) for v in self.arrays.values()), default=0)
        return len(self.records)

    def value(self, index: int, key: str) -> Any:
        """One cell's value."""
        if self.arrays is not None:
            column = self.arrays.get(key)
            return column[index] if column is not None else None
        record = self.records[index]
        if isinstance(record, Mapping):
            return record.get(key)
        return getattr(record, key, None)

    def key_of(self, index: int) -> Any:
        """The identity of the row at source *index*."""
        return self.value(index, self.row_key) if self.row_key else index

    def visible_columns(self) -> list[TableColumn]:
        """The columns drawn: declared visible, and not hidden by the user."""
        return [c for c in self.columns if c.visible and c.key not in self.hidden]

    def set_column_hidden(self, key: str, hidden: bool) -> None:
        """Hide or show one column, as the picker does. The last one stays."""
        if hidden and len([c for c in self.visible_columns() if c.key != key]) == 0:
            return
        (self.hidden.add if hidden else self.hidden.discard)(key)
        self.first_column = 0
        self.changed()

    def status_text(self) -> str:
        """``"6 rows × 11 columns"``, or ``"2 of 6 rows × ..."`` while filtered."""
        shown, total = len(self.order()), self.row_count()
        rows = f"{shown} of {total} rows" if shown != total else \
            f"{total} row{'' if total == 1 else 's'}"
        count = len(self.visible_columns())
        return f"{rows} × {count} column{'' if count == 1 else 's'}"

    def order(self) -> list[int]:
        """Source indices, filtered and sorted as displayed (cached per change)."""
        wanted = (self.revision, self.row_count(), self.filter.text, self.sort_key_name,
                  self.descending, tuple(c.key for c in self.columns),
                  tuple(sorted(self.column_filters.items())),
                  frozenset(self.expanded) if self.tree_key else None)
        if wanted == self._order_for:
            return self._order
        count = self.row_count()
        columns = self.visible_columns()
        needle = self.filter.text.strip().lower()
        indices = list(range(count))
        if needle:
            indices = [
                i for i in indices
                if any(needle in c.text(self.value(i, c.key)).lower() for c in columns)
            ]
        by_key = {c.key: c for c in self.columns}
        for key, text in self.column_filters.items():
            needle_c = str(text).strip().lower()
            column = by_key.get(key)
            if not needle_c or column is None:
                continue
            indices = [i for i in indices if needle_c in column.text(self.value(i, key)).lower()]
        if self.sort_key_name is not None:
            name = self.sort_key_name
            keyed = [(_sort_key(self.value(i, name)), i) for i in indices]
            present = [item for item in keyed if item[0][0] != 2]
            missing = [item for item in keyed if item[0][0] == 2]
            # `sort(reverse=True)` is stable too: equal values keep the
            # producer's order in both directions, and missing values stay
            # last either way.
            present.sort(key=lambda item: item[0], reverse=self.descending)
            keyed = present + missing
            indices = [i for _, i in keyed]
        if self.tree_key:
            filtering = bool(needle) or any(str(t).strip() for t in self.column_filters.values())
            indices = self._tree_order(indices, filtering)
        self._order = indices
        self._order_for = wanted
        return indices

    def _tree_order(self, kept: Sequence[int], filtering: bool) -> list[int]:
        """*kept* (filtered, sorted) as a tree: children under their parent.

        Siblings keep the sorted order; a row is shown while its parent is
        expanded, or, while a filter is on, when it or a descendant matches.
        """
        count = self.row_count()
        by_key = {self.key_of(i): i for i in range(count)}
        parent_of: dict = {}
        for i in range(count):
            pk = self.value(i, self.tree_key)
            if pk not in (None, "") and pk in by_key and by_key[pk] != i:
                parent_of[i] = by_key[pk]
        self._has_children = {self.key_of(i) for i in parent_of.values()}
        keep = set(kept)
        if filtering:
            for i in list(keep):
                seen = set()
                while i in parent_of and i not in seen:
                    seen.add(i)
                    i = parent_of[i]
                    keep.add(i)
        rank = {i: n for n, i in enumerate(kept)}
        children: dict = {}
        roots = []
        for i in sorted(keep, key=lambda i: (rank.get(i, len(rank)), i)):
            (children.setdefault(parent_of[i], []) if i in parent_of else roots).append(i)
        out: list[int] = []
        depth: dict = {}
        stack = [(i, 0) for i in reversed(roots)]
        while stack:
            i, level = stack.pop()
            if i in depth:
                continue
            out.append(i)
            depth[i] = level
            if filtering or self.key_of(i) in self.expanded:
                stack.extend((c, level + 1) for c in reversed(children.get(i, ())))
        self._depth = depth
        return out

    def is_parent(self, index: int) -> bool:
        """Whether the row at source *index* has children (a tree only)."""
        return bool(self.tree_key) and self.key_of(index) in self._has_children

    def depth_of(self, index: int) -> int:
        """Tree level of the row at source *index* (0 at the top)."""
        return int(self._depth.get(index, 0)) if self.tree_key else 0

    def set_expanded(self, key: Any, expanded: bool) -> None:
        """Open or close the row identified by *key*."""
        (self.expanded.add if expanded else self.expanded.discard)(key)

    def toggle(self, index: int) -> bool:
        """Flip a parent row open or closed; ``False`` for a row without children."""
        if not self.is_parent(index):
            return False
        key = self.key_of(index)
        self.set_expanded(key, key not in self.expanded)
        return True

    def _indent(self, index: int) -> float:
        """Room before the first column's text: the level, and the triangle."""
        if not self.tree_key:
            return 0.0
        # The triangle's room only while some row has one: a tree of leaves
        # (no vector yet) reads as a flat table.
        return (self.depth_of(index) + (1 if self._has_children else 0)) * self.TREE_INDENT

    def selected_index(self) -> Optional[int]:
        """Source index of the selected row, or ``None``."""
        if self.selected_key is None:
            return None
        for index in range(self.row_count()):
            if self.key_of(index) == self.selected_key:
                return index
        return None

    def select_key(self, key: Any) -> bool:
        """Select the row identified by *key* without notifying; scroll to it."""
        for position, index in enumerate(self.order()):
            if self.key_of(index) == key:
                self.selected_key = key
                self._scroll_to(position)
                return True
        self.selected_key = None
        return False

    def select_all(self) -> None:
        """Select every row (the rows the filter shows), without notifying."""
        order = self.order()
        self.also_selected = {self.key_of(i) for i in order}
        if order and self.selected_key not in self.also_selected:
            self.selected_key = self.key_of(order[0])

    def selected_indices(self) -> list[int]:
        """Source indices of every selected row, in source order."""
        keys = set(self.also_selected)
        if self.selected_key is not None:
            keys.add(self.selected_key)
        return [i for i in range(self.row_count()) if self.key_of(i) in keys]

    def sort_by(self, key: str, descending: Optional[bool] = None) -> None:
        """Sort by column *key*; without *descending*, the same key flips."""
        if descending is None:
            descending = (not self.descending) if self.sort_key_name == key else False
            column = next((c for c in self.columns if c.key == key), None)
            if self.sort_key_name != key and column is not None and column.display == "bar":
                descending = True  # a score opens best-first
        self.sort_key_name = key
        self.descending = bool(descending)

    # -- geometry ---------------------------------------------------------------- #

    def _scroll_to(self, position: int) -> None:
        top = self.bar.top
        if position < top:
            self.bar.top = max(position, 0)
        elif position >= top + self._visible:
            self.bar.top = max(position - self._visible + 1, 0)
        self.bar.clamp(len(self.order()), self._visible)

    def row_at(self, x: float, y: float) -> Optional[int]:
        """Display position of the row under a point."""
        if self._body_box is None:
            return None
        bx, by, bw, bh = self._body_box
        if not (bx <= x <= bx + bw and by <= y <= by + bh):
            return None
        position = self.bar.top + int((y - by) // max(self._row_h, 1e-6))
        return position if 0 <= position < len(self.order()) else None

    def tooltip_at(self, x: float, y: float) -> tuple[str, Any]:
        """``(text, part)`` of the tooltip under a point of the last draw.

        A header shows its column's ``tooltip`` (or ``description``); a row
        shows its ``tooltip_key`` field. ``part`` tells one header or row from
        the next, so moving between them is moving between items. ``("",
        None)`` where there is none.
        """
        if self._inside(self._header_box, x, y):
            column = self.column_at(x)
            if column is not None and column.tooltip:
                return (column.tooltip, ("header", column.key))
            return ("", None)
        position = self.row_at(x, y)
        if position is not None:
            index = self.order()[position]
            column = self.column_at(x)
            full = self._elided.get((index, column.key)) if column is not None else None
            if full:
                return (full, ("cell", index, column.key))
            if self.tooltip_key:
                note = str(self.value(index, self.tooltip_key) or "")
                if note:
                    return (note, ("row", index))
        return ("", None)

    def column_at(self, x: float) -> Optional[TableColumn]:
        """The column under an x position of the last draw."""
        if self._header_box is None:
            return None
        edge = self._header_box[0]
        for column, width in zip(self._shown, self._widths):
            if edge <= x < edge + width:
                return column
            edge += width
        return None

    def _column_widths(self, total: float) -> list[float]:
        """Widths of every visible column, filling *total*.

        A column's natural width is its fitted (measured) width, else its
        declared ``width``; the rest share what is left, never below
        :attr:`min_column_width`. Room to spare is handed back to the columns
        in proportion to their width, so a table never leaves the right half of
        its box empty; a shortfall is taken first from the columns wider than
        their header, and only what cannot be taken makes the table scroll.
        """
        columns = self.visible_columns()
        if not columns:
            return []
        floor = self.min_column_width
        natural = []
        for column in columns:
            width = self._fitted.get(column.key) or column.width
            natural.append(max(width, floor) if width else None)
        known = sum(w for w in natural if w)
        flexible = sum(1 for w in natural if w is None)
        share = max((total - known) / flexible, floor, 1.0) if flexible else 0.0
        widths = [w if w else share for w in natural]
        size = sum(widths)
        if size < total and size > 0.0:
            return [w * total / size for w in widths]
        if size <= total:
            return widths
        if not (floor > 0.0 or self._fitted):
            return [w * total / size for w in widths]
        # Down to the header (to the contents, for a column of numbers).
        least = [max(floor, self._title_w.get(c.key, 0.0)) for c in columns]
        slack = sum(max(w - m, 0.0) for w, m in zip(widths, least))
        deficit = size - total
        if slack <= 0.0:
            return widths
        take = min(deficit / slack, 1.0)
        return [w - take * max(w - m, 0.0) for w, m in zip(widths, least)]

    def fit_columns(self) -> None:
        """Size every column to its header and the rows in view, on the next draw."""
        self._fit_pending = True

    def _measure(self, p: Painter, order: Sequence[int]) -> None:
        self._fit_pending = False
        rows = order[self.bar.top:self.bar.top + max(self._visible, 1) + 50]
        fitted = {}
        first = next(iter(self.visible_columns()), None)
        for column in self.visible_columns():
            # The cell margins (6 each side), a little air, and room for the
            # sort mark only on the column that carries it.
            mark = p.text_width("▴ ") if column.key == self.sort_key_name else 0.0
            widest = p.text_width(column.title) + 16.0 + mark
            self._title_w[column.key] = widest
            numeric = False
            for index in rows:
                value = self.value(index, column.key)
                numeric = numeric or (_is_number(value) and not isinstance(value, (bool, _np_bool())))
                indent = self._indent(index) if column is first else 0.0
                widest = max(widest, p.text_width(column.text(value)) + 14.0 + indent)
            fitted[column.key] = widest
            if numeric:
                # A number is never shortened to fit: '2048' cut to '20.' is a
                # different number. Text columns give way instead, and elide.
                self._title_w[column.key] = widest
        self._fitted = fitted
        self._fitted_for = self.revision

    def scroll_columns(self, steps: int) -> None:
        """Move the leftmost column by *steps* (positive is right)."""
        count = len(self.visible_columns())
        self.first_column = max(0, min(self.first_column + int(steps), max(count - 1, 0)))

    def colour_of(self, key: str, value: Any) -> Optional[tuple]:
        """The shade of a numeric cell, or ``None`` (see :attr:`colour_values`)."""
        if self.colour_values not in ("column", "table") or not _is_number(value) \
                or isinstance(value, (bool, _np_bool())):
            return None
        number = float(value)
        if number != number:
            return None
        wanted = (self.revision, self.row_count(), self.colour_values,
                  tuple(c.key for c in self.columns))
        if wanted != self._colour_for:
            self._colour_for = wanted
            self._colour_ranges = self._value_ranges()
        span = self._colour_ranges.get("*" if self.colour_values == "table" else key)
        if span is None:
            return None
        lo, hi = span
        fraction = 0.5 if not hi > lo else (hi - number) / (hi - lo)
        return _ramp(fraction)

    def _value_ranges(self) -> dict:
        ranges: dict = {}
        count = self.row_count()
        for column in self.columns:
            if not column.shade:
                continue
            numbers = []
            if self.arrays is not None and column.key in self.arrays:
                data = self.arrays[column.key]
                try:
                    import numpy as np

                    array = np.asarray(data)
                    if array.dtype.kind in "fiu":
                        finite = array[np.isfinite(array)] if array.dtype.kind == "f" else array
                        if finite.size:
                            ranges[column.key] = (float(finite.min()), float(finite.max()))
                        continue
                except (ImportError, TypeError, ValueError):
                    pass
            for index in range(count):
                value = self.value(index, column.key)
                if _is_number(value) and not isinstance(value, (bool, _np_bool())):
                    number = float(value)
                    if number == number:
                        numbers.append(number)
            if numbers:
                ranges[column.key] = (min(numbers), max(numbers))
        if ranges:
            ranges["*"] = (min(lo for lo, _ in ranges.values()),
                           max(hi for _, hi in ranges.values()))
        return ranges

    # -- drawing ------------------------------------------------------------------- #

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the filter box, the header, the visible rows and the note."""
        line = p.line_height()
        self._row_h = row_h = line * self.row_scale
        cursor = y
        if self.show_filter:
            box_h = line * 1.5
            self._filter_box = (x, cursor, w, box_h)
            self._draw_filter(p, x, cursor, w, box_h)
            cursor += box_h + 4.0
        else:
            self._filter_box = None

        note = ""
        index = self.selected_index()
        if self.tooltip_key and index is not None:
            note = str(self.value(index, self.tooltip_key) or "")
        note_lines = 2 if note else 0
        note_h = note_lines * line + (6.0 if note_lines else 0.0)
        status_h = line * 1.2 if self.show_status else 0.0
        note_h += status_h
        header_h = line * 1.35
        order = self.order()
        body_top = cursor + header_h
        body_h = max(y + h - note_h - body_top, row_h)
        self._visible = max(int(body_h // row_h), 1)
        self.bar.clamp(len(order), self._visible)
        bar_w = self.bar.width if self.bar.needed() else 0.0
        list_w = max(w - bar_w, 1.0)
        if self._fit_pending or (self.auto_fit and self._fitted_for != self.revision):
            self._measure(p, order)
        widths = self._column_widths(list_w)
        wide = sum(widths) > list_w + 0.5
        if wide:
            hbar_h = self.bar.width
            body_h = max(body_h - hbar_h, row_h)
            self._visible = max(int(body_h // row_h), 1)
            self.bar.clamp(len(order), self._visible)
            self._hbar_box = (x, body_top + body_h, list_w, hbar_h)
        else:
            self.first_column = 0
            self._hbar_box = None
        self.first_column = max(0, min(self.first_column, max(len(widths) - 1, 0)))
        columns = self.visible_columns()[self.first_column:]
        self._shown = columns
        self._widths = widths[self.first_column:]
        self._header_box = (x, cursor, list_w, header_h)
        self._body_box = (x, body_top, list_w, body_h)

        p.stroke_rect(x, cursor, list_w, header_h, _style.BORDER, _style.HEADER_BG)
        p.push_clip(x, cursor, list_w, header_h)
        col_x = x
        for position, (column, width) in enumerate(zip(columns, self._widths)):
            right = self._right_aligned(column, order)
            mark = ""
            if column.key == self.sort_key_name:
                mark = "▾" if self.descending else "▴"
            title = (f"{mark} {column.title}" if right else f"{column.title} {mark}") if mark \
                else column.title
            p.text(col_x + 6.0, cursor, max(width - 12.0, 1.0), header_h,
                   ALIGN_VCENTER | (ALIGN_RIGHT if right else ALIGN_LEFT),
                   fit_text(p, title, width - 12.0), _style.TABLE_HEADER_TEXT, bold=True)
            if position:
                p.fill_rect(col_x, cursor + 3.0, 1.0, header_h - 6.0, _style.BORDER)
            col_x += width
        p.pop_clip()

        p.stroke_rect(x, body_top, list_w, body_h, _style.BORDER, _style.TABLE_ROW_BG)
        p.push_clip(x, body_top, list_w, body_h)
        self._elided = {}
        top = self.bar.top
        row_y = body_top
        for position in range(top, min(top + self._visible + 1, len(order))):
            self._draw_row(p, position, order[position], columns, order, x, row_y, row_h)
            row_y += row_h
        p.pop_clip()
        if bar_w:
            self.bar.draw(p, x + list_w, body_top, body_h)
        if self._hbar_box is not None:
            self._draw_hbar(p, widths, list_w)

        note_y = body_top + body_h + (self._hbar_box[3] if self._hbar_box else 0.0) + 4.0
        if note_lines:
            for offset, text in enumerate(_wrap(p, note, w - 8.0, note_lines)):
                p.text(x + 4.0, note_y + offset * line, w - 8.0, line,
                       ALIGN_VCENTER | ALIGN_LEFT, text, _style.DIM)
            note_y += note_lines * line + 2.0
        if self.show_status:
            p.text(x + 4.0, note_y, w - 8.0, line, ALIGN_VCENTER | ALIGN_LEFT,
                   self.status_text(), _style.DIM)

    def _right_aligned(self, column: TableColumn, order: Sequence[int]) -> bool:
        if column.align_right is not None:
            return column.align_right
        if not order:
            return column.display == "bar"
        return _sort_key(self.value(order[0], column.key))[0] == 0

    def _draw_filter(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        field = self.filter.field
        p.stroke_rect(x, y, w, h, _style.GOLD if self.filter_focused else _style.BORDER, _style.TRACK_BG)
        p.push_clip(x, y, w, h)
        p.text(x + 4.0, y, max(w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
               field.text or field.placeholder, _style.TEXT if field.text else _style.DIM)
        if self.filter_focused:
            caret = x + 4.0 + p.text_width(field.text[: field.cursor])
            p.fill_rect(caret, y + h * 0.15, max(1.0, h * 0.08), h * 0.7, _style.GOLD)
        p.pop_clip()

    def _draw_row(self, p: Painter, position: int, index: int, columns, order, x: float,
                  y: float, h: float) -> None:
        key = self.key_of(index)
        if (self.selected_key is not None and key == self.selected_key) \
                or key in self.also_selected:
            background = _style.ROW_SEL
        elif position == self.hovered:
            background = _style.HEADER
        else:
            background = _style.TABLE_ROW_BG_ALT if position % 2 else None
        if background is not None:
            p.fill_rect(x, y, sum(self._widths), h, background)
        text_h = min(h, p.line_height() * 1.15)
        colour = _style.DIM if self.muted is not None and self.muted(index) else _style.TEXT
        col_x = x
        tree_column = columns[0] if self.tree_key and self.first_column == 0 and columns else None
        for column, width in zip(columns, self._widths):
            value = self.value(index, column.key)
            indent = 0.0
            if column is tree_column:
                indent = self._indent(index)
                if self.is_parent(index):
                    self._draw_disclosure(p, col_x + indent - self.TREE_INDENT + 3.0, y, h,
                                          self.key_of(index) in self.expanded)
            if self.editing == (index, column.key):
                self._draw_editor(p, col_x, y, width, h)
                col_x += width
                continue
            if isinstance(value, (bool, _np_bool())):
                self._draw_check(p, col_x, y, width, h, bool(value))
                col_x += width
                continue
            shade = self.colour_of(column.key, value)
            if shade is not None:
                p.fill_rect(col_x, y, width, h, shade)
            bar = column.bar(value)
            if bar is not None:
                start, end, colour = bar
                bar_h = max(3.0, h * 0.14)
                inner = width - 8.0
                p.fill_rect(col_x + 4.0 + start * inner, y + h - bar_h - 2.0,
                            max((end - start) * inner, 1.0), bar_h, colour)
            right = self._right_aligned(column, order) and not indent
            text = column.text(value)
            shown = fit_text(p, text, width - 12.0 - indent)
            if shown != text:
                self._elided[(index, column.key)] = text
            p.text(col_x + 6.0 + indent, y + 1.0, max(width - 12.0 - indent, 1.0), text_h,
                   ALIGN_VCENTER | (ALIGN_RIGHT if right else ALIGN_LEFT), shown, colour)
            col_x += width

    def _draw_hbar(self, p: Painter, widths: Sequence[float], list_w: float) -> None:
        """The sideways scrollbar: the thumb covers the columns in view."""
        bx, by, bw, bh = self._hbar_box
        p.fill_rect(bx, by, bw, bh, _style.TABLE_ROW_BG_ALT)
        total = max(sum(widths), 1.0)
        start = sum(widths[:self.first_column])
        span = max(bw * min(list_w / total, 1.0), 12.0)
        at = bx + (bw - span) * min(start / max(total - list_w, 1.0), 1.0)
        p.fill_rect(at, by + 1.0, span, max(bh - 2.0, 1.0),
                    _style.CHECK_MARK if self._hbar_held else _style.DIM)

    def _hbar_to(self, x: float) -> None:
        bx, _by, bw, _bh = self._hbar_box
        count = len(self.visible_columns())
        fraction = min(max((x - bx) / max(bw, 1e-6), 0.0), 1.0)
        self.first_column = int(round(fraction * max(count - 1, 0)))

    def _draw_disclosure(self, p: Painter, x: float, y: float, h: float, open_: bool) -> None:
        """The ▸ / ▾ of a parent row, drawn as a triangle (no glyph needed)."""
        side = min(self.TREE_INDENT - 6.0, h * 0.5)
        cy = y + h / 2.0
        if open_:
            p.fill_triangle((x, cy - side * 0.35), (x + side, cy - side * 0.35),
                            (x + side / 2.0, cy + side * 0.5), _style.TEXT)
        else:
            p.fill_triangle((x + side * 0.15, cy - side / 2.0), (x + side * 0.15, cy + side / 2.0),
                            (x + side * 0.95, cy), _style.TEXT)

    @staticmethod
    def _draw_check(p: Painter, x: float, y: float, w: float, h: float, on: bool) -> None:
        """A check box centred in the cell."""
        side = max(8.0, min(h - 6.0, p.line_height() * 0.95))
        bx, by = x + (w - side) / 2.0, y + (h - side) / 2.0
        p.stroke_rect(bx, by, side, side, _style.BORDER, _style.FRAME_BG)
        if on:
            inset = max(2.0, side * 0.22)
            p.fill_rect(bx + inset, by + inset, side - 2 * inset, side - 2 * inset,
                        _style.CHECK_MARK)

    def _draw_editor(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """The cell being typed into: a field with a caret."""
        field = self.editor.field
        self._editor_box = (x, y, w, h)
        p.stroke_rect(x + 1.0, y + 1.0, w - 2.0, h - 2.0, _style.CHECK_MARK, _style.FRAME_BG)
        p.push_clip(x + 1.0, y + 1.0, w - 2.0, h - 2.0)
        p.text(x + 5.0, y, max(w - 10.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, field.text,
               _style.TEXT)
        caret = x + 5.0 + p.text_width(field.text[: field.cursor])
        p.fill_rect(caret, y + h * 0.2, 1.0, h * 0.6, _style.TEXT)
        p.pop_clip()

    # -- editing ------------------------------------------------------------------- #

    def column_editable(self, key: str) -> bool:
        column = next((c for c in self.columns if c.key == key), None)
        return bool(column is not None and column.editable)

    def can_edit(self, index: int, key: str) -> bool:
        """Whether cell ``(index, key)`` may be changed now."""
        if not self.column_editable(key):
            return False
        return self.cell_editable is None or bool(self.cell_editable(index, key))

    def begin_edit(self, index: int, key: str) -> None:
        """Open cell ``(index, key)`` for typing, filled with its text."""
        column = next(c for c in self.columns if c.key == key)
        self.editing = (index, key)
        value = self.value(index, key)
        self.editor.set_text("" if value is None else (
            repr(float(value)) if isinstance(value, float) and not column.fmt else column.text(value)))

    def commit_edit(self) -> None:
        """Parse what was typed like the value it replaces, and report it."""
        if self.editing is None:
            return
        index, key = self.editing
        self.editing = None
        self._editor_box = None
        old = self.value(index, key)
        text = self.editor.text.strip()
        value: Any = text
        if isinstance(old, (int, float)) and not isinstance(old, bool) or _is_number(old):
            try:
                value = int(text) if isinstance(old, int) and not isinstance(old, bool) \
                    else parse_number(text)
            except ValueError:
                return  # a typo leaves the cell as it was
        if value != old:
            self._write(index, key, value)

    def cancel_edit(self) -> None:
        self.editing = None
        self._editor_box = None

    def _write(self, index: int, key: str, value: Any) -> None:
        if self.arrays is None and 0 <= index < len(self.records):
            record = self.records[index]
            if isinstance(record, MutableMapping):
                record[key] = value
        self.revision += 1
        if self.on_edit is not None:
            self.on_edit(index, key, value)

    # -- input --------------------------------------------------------------------- #

    @staticmethod
    def _inside(box, x: float, y: float) -> bool:
        if box is None:
            return False
        bx, by, bw, bh = box
        return bx <= x <= bx + bw and by <= y <= by + bh

    def press(self, x: float, y: float, *box: Any, **kw: Any) -> bool:
        """Focus the filter, sort by a header, select a row, flip or open a cell.

        Accepts the host's ``press(px, py, bx, by, bw, bh, modifiers, clicks)``;
        returns whether the press landed on the table.
        """
        clicks = int(kw.get("clicks", box[5] if len(box) > 5 else 1) or 1)
        if self.editing is not None:
            if self._inside(self._editor_box, x, y):
                return True
            self.commit_edit()
        if self._inside(self._filter_box, x, y):
            self.filter_focused = True
            return True
        self.filter_focused = False
        if self.bar.needed() and self.bar.press(x, y):
            return True
        if self._inside(self._hbar_box, x, y):
            self._hbar_held = True
            self._hbar_to(x)
            return True
        if self._inside(self._header_box, x, y):
            column = self.column_at(x)
            if column is not None:
                self.sort_by(column.key)
            return True
        position = self.row_at(x, y)
        if position is None:
            return self._inside(self._body_box, x, y)
        self._select_position(position)
        index = self.order()[position]
        column = self.column_at(x)
        if self.is_parent(index) and self._on_disclosure(index, x):
            self.toggle(index)
            return True
        if column is not None and self.can_edit(index, column.key):
            value = self.value(index, column.key)
            if isinstance(value, (bool, _np_bool())):
                self._write(index, column.key, not bool(value))
                return True
            if clicks > 1:
                self.begin_edit(index, column.key)
                return True
        if clicks > 1 and self.is_parent(index):
            self.toggle(index)
        if clicks > 1 and self.on_activate is not None:
            self.on_activate(index)
        return True

    def _on_disclosure(self, index: int, x: float) -> bool:
        """Whether *x* falls on the triangle of the row at source *index*."""
        if self.first_column != 0 or self._header_box is None or not self._widths:
            return False
        left = self._header_box[0] + self._indent(index) - self.TREE_INDENT
        return left <= x <= left + self.TREE_INDENT + 4.0

    def _select_position(self, position: int) -> None:
        order = self.order()
        if not order:
            return
        position = min(max(position, 0), len(order) - 1)
        index = order[position]
        key = self.key_of(index)
        changed = key != self.selected_key
        self.selected_key = key
        self.also_selected = set()
        self._scroll_to(position)
        if changed and self.on_select is not None:
            self.on_select(index)

    def drag(self, x: float, y: float, *_box: Any) -> bool:
        """Continue a scrollbar drag."""
        if self._hbar_held and self._hbar_box is not None:
            self._hbar_to(x)
            return True
        return self.bar.drag(y)

    def release(self, *_args: Any, **_kw: Any) -> None:
        """End a scrollbar drag."""
        self._hbar_held = False
        self.bar.release()

    def context(self, x: float, y: float) -> bool:
        """A right click: select the row under it and report row and column.

        Returns whether it landed on the table (header or rows).
        """
        on_header = self._inside(self._header_box, x, y)
        if on_header and self.column_picker:
            self.picker_at = (x, y)
            return True
        position = self.row_at(x, y)
        if position is None and not on_header:
            return self._inside(self._body_box, x, y)
        index = None
        if position is not None:
            if self.editing is not None:
                self.commit_edit()
            index = self.order()[position]
            # A right click inside the selection keeps it, so a menu can act on
            # every selected row (Select All, then Delete); elsewhere it selects.
            if self.key_of(index) not in self.also_selected:
                self._select_position(position)
        column = self.column_at(x)
        if self.on_context is not None:
            self.on_context(index, column.key if column is not None else None, x, y)
        return True

    def hover(self, x: float, y: float, *_box: Any) -> None:
        """Track the row under the pointer."""
        self.hovered = self.row_at(x, y)

    def scroll(self, rows: int) -> int:
        """Scroll by whole rows (positive is down)."""
        return self.bar.scroll(int(rows))

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Type into a cell or the filter, delete a row, or move the selection."""
        if self.editing is not None:
            if key in (KEY_RETURN, KEY_ENTER):
                # Text typed in the same frame as Enter came first.
                if text:
                    self.editor.field.key(0, text, modifiers)
                self.commit_edit()
            elif key == KEY_ESCAPE:
                self.cancel_edit()
            else:
                self.editor.field.key(key, text, modifiers)
            return True
        if self.filter_focused:
            if key == KEY_ESCAPE:
                self.filter_focused = False
                return True
            return self.filter.field.key(key, text, modifiers)
        order = self.order()
        if not order:
            return False
        if key in (KEY_DELETE, KEY_BACKSPACE):
            indices = self.selected_indices()
            if not indices or self.on_delete is None:
                return False
            # Last first, so a source that renumbers on delete keeps the
            # earlier indices valid.
            for index in reversed(indices):
                self.on_delete(index)
            self.selected_key = None
            self.also_selected = set()
            return True
        current = next((pos for pos, i in enumerate(order)
                        if self.key_of(i) == self.selected_key), None)
        if key in (KEY_LEFT, KEY_RIGHT) and self.tree_key and current is not None:
            index = order[current]
            if not self.is_parent(index):
                return False
            self.set_expanded(self.key_of(index), key == KEY_RIGHT)
            return True
        moves = {KEY_UP: -1, KEY_DOWN: 1, KEY_PAGE_UP: -self._visible, KEY_PAGE_DOWN: self._visible}
        if key in moves:
            if current is None:
                target = 0 if moves[key] > 0 else len(order) - 1
            else:
                target = current + moves[key]
        elif key == KEY_HOME:
            target = 0
        elif key == KEY_END:
            target = len(order) - 1
        else:
            return False
        self._select_position(target)
        return True


def _wrap(p: Painter, text: str, width: float, lines: int) -> list[str]:
    """Break *text* at spaces into at most *lines* lines; the last is shortened."""
    words = str(text).split()
    out: list[str] = []
    current = ""
    while words and len(out) < lines - 1:
        candidate = f"{current} {words[0]}".strip()
        if current and p.text_width(candidate) > width:
            out.append(current)
            current = ""
            continue
        current = candidate
        words.pop(0)
    rest = " ".join(([current] if current else []) + words)
    if rest:
        out.append(fit_text(p, rest, width))
    return out


class TableBinding:
    """A table section read against a model.

    Parameters
    ----------
    section : mapping
        A ``table`` section or a ``custom`` ``data_table`` section.
    model : object
        What ``source``, ``columns_source`` and the callbacks are looked up on.

    Attributes
    ----------
    control : DataTable
        The control, refreshed from the model by :meth:`refresh`.
    height : float
        The section's ``height`` (default 240, as in the Qt renderer).
    expand : bool
        Fill the spare height.
    """

    def __init__(self, section: Mapping, model: Any) -> None:
        self.section = dict(section)
        self.model = model
        options = dict(section.get("options") or {})
        merged = {**{k: v for k, v in section.items() if k != "options"}, **options}
        self.options = merged
        self.source = str(merged.get("source", "") or merged.get("target", "") or "")
        self.columns_source = str(merged.get("columns_source", "") or "")
        self.selected_call = str(merged.get("selected_call", "") or "")
        self.selected_attr = str(merged.get("selected_attr", "") or "")
        self.activated_call = str(merged.get("activated_call", "") or "")
        self.edited_call = str(merged.get("edited_call", "") or "")
        self.delete_call = str(merged.get("delete_call", "") or "")
        self.context_call = str(merged.get("context_call", "") or "")
        self.colour_source = str(merged.get("colour_source", "") or "")
        self.editable = bool(merged.get("editable", False))
        self.height = float(merged.get("height", 240) or 240)
        self.expand = bool(merged.get("expand", False))
        #: Height an expanding table leaves free under it, for the rows that follow.
        self.reserve = float(merged.get("reserve", 0) or 0)
        self._declared_columns = list(merged.get("columns") or [])
        self.editable_call = str(merged.get("editable_call", "") or "")
        self.expanded_attr = str(merged.get("expanded_attr", "") or "")
        self.muted_key = str(merged.get("muted_key", "") or "")
        self.control = DataTable(
            cell_editable=self._cell_editable if self.editable_call else None,
            muted=self._muted if self.muted_key else None,
            status=bool(merged.get("status", False)),
            column_picker=bool(merged.get("column_picker", False)),
            tree_key=str(merged.get("tree_key", "") or ""),
            on_select=self._on_select,
            on_activate=self._on_activate,
            on_edit=self._on_edit,
            on_delete=self._on_delete,
            filter_box=bool(merged.get("filter", False)),
            tooltip_key=str(merged.get("tooltip_key", "") or ""),
            row_key=str(merged.get("row_key", "") or ""),
            on_context=self._on_context,
            min_column_width=float(merged.get("min_column_width", 0) or 0),
        )
        self.control.auto_fit = bool(merged.get("fit_columns", False))
        sort = merged.get("sort")
        if isinstance(sort, Mapping) and sort.get("key"):
            self.control.sort_by(str(sort["key"]), bool(sort.get("descending", False)))
        self._data_token: tuple = ()
        self._columns_token: tuple = ()
        self.refresh()

    # -- reading the model ------------------------------------------------------- #

    def _lookup(self, name: str) -> Any:
        """The model's attribute *name*; a dotted name walks into it (``table.rows``).

        A dotted name lets one model carry several tables, each an object of
        its own with the same method names.
        """
        target = self.model
        for part in str(name).split("."):
            target = getattr(target, part, None)
            if target is None:
                return None
        return target

    def _call(self, name: str) -> Any:
        if not name:
            return None
        value = self._lookup(name)
        try:
            return value() if callable(value) else value
        except Exception:  # noqa: BLE001 - a failing source shows an empty table
            return None

    def _column_specs(self, data: Any) -> list:
        declared = self._call(self.columns_source) if self.columns_source else None
        declared = list(declared) if declared else list(self._declared_columns)
        if isinstance(data, Mapping):
            keys = [str(k) for k in data]
        elif data:
            first = data[0]
            keys = [str(k) for k in first] if isinstance(first, Mapping) else []
        else:
            keys = []
        if not declared:
            return [{"key": key} for key in keys]
        # A record source shows every field unless the spec lists columns; the
        # built-in table shows exactly the listed ones. Listing is the common
        # case for both, and a listed-only table is what a ranked view wants.
        return declared

    def refresh(self) -> bool:
        """Re-read the source; rebind when it changed. Returns whether it did.

        A source that grows in place -- a list the producer appends to while a
        computation streams -- is noticed by its length, and one that carries a
        ``revision`` attribute by that, so an append costs one comparison here.
        """
        if self.expanded_attr:
            shared = self._lookup(self.expanded_attr)
            if isinstance(shared, set) and shared is not self.control.expanded:
                self.control.expanded = shared
        if self.colour_source:
            mode = self._call(self.colour_source)
            self.control.colour_values = str(mode) if mode in ("column", "table") else None
        data = self._call(self.source)
        size = None
        if data is not None:
            try:
                size = len(data) if not isinstance(data, Mapping) else \
                    min((len(v) for v in data.values()), default=0)
            except TypeError:
                size = None
        token = (id(data), size, getattr(data, "revision", None))
        specs = self._column_specs(data)
        columns_token = tuple(tuple(sorted((str(k), repr(v)) for k, v in dict(s).items()))
                              for s in specs if isinstance(s, Mapping))
        changed = False
        if columns_token != self._columns_token:
            self._columns_token = columns_token
            self.control.columns = [TableColumn.from_spec(s, self.editable) for s in specs
                                    if isinstance(s, Mapping)]
            self.control.changed()
            changed = True
        if token != self._data_token:
            self._data_token = token
            if data is None:
                self.control.set_records(())
            elif isinstance(data, Mapping):
                self.control.set_arrays(data)
            else:
                self.control.set_records(data)
            changed = True
        return changed

    def record(self, index: Optional[int]) -> Any:
        """What a callback receives for source *index*: the record, else the index."""
        if index is None:
            return None
        if self.control.arrays is None and 0 <= index < len(self.control.records):
            return self.control.records[index]
        return index

    def _cell_editable(self, index: int, key: str) -> bool:
        fn = self._lookup(self.editable_call)
        if not callable(fn):
            return True
        try:
            return bool(fn(self.record(index), key))
        except Exception:  # noqa: BLE001 - a failing rule refuses the edit
            return False

    def _muted(self, index: int) -> bool:
        return bool(self.control.value(index, self.muted_key))

    def _on_select(self, index: Optional[int]) -> None:
        payload = self.record(index)
        if self.selected_attr:
            try:
                owner, _, attr = self.selected_attr.rpartition(".")
                setattr(self._lookup(owner) if owner else self.model, attr,
                        payload if payload is not None else {})
            except Exception:  # noqa: BLE001
                pass
        if self.selected_call:
            fn = self._lookup(self.selected_call)
            if callable(fn):
                fn(payload)

    def _on_edit(self, index: int, key: str, value: Any) -> None:
        if self.edited_call:
            fn = self._lookup(self.edited_call)
            if callable(fn):
                fn(self.record(index), key, value)

    def _on_delete(self, index: int) -> None:
        if self.delete_call:
            fn = self._lookup(self.delete_call)
            if callable(fn):
                fn(self.record(index))

    def _on_context(self, index: Optional[int], key: Optional[str], x: float, y: float) -> None:
        if self.context_call:
            fn = self._lookup(self.context_call)
            if callable(fn):
                fn(self.record(index), key, (x, y))

    def _on_activate(self, index: int) -> None:
        if self.activated_call:
            fn = self._lookup(self.activated_call)
            if callable(fn):
                fn(self.record(index))


def draw_table(binding: TableBinding, name: str, width: Optional[float] = None,
               height: Optional[float] = None) -> None:
    """Draw a bound table as one item of the current immediate-mode window.

    The table is refreshed from its model, laid out as an item of *width* by
    *height* (the section's ``height``, or the remaining space when it asks to
    ``expand``), and fed the frame's pointer, wheel and keys while hovered or
    while its filter has focus.
    """
    from .. import im_core as core
    from .. import im_widgets as widgets

    ctx = core.get_current_context()
    binding.refresh()
    avail_w, avail_h = widgets.get_content_region_avail()[:2]
    w = float(width) if width is not None else float(avail_w)
    h = float(height) if height is not None else (
        max(float(avail_h) - binding.reserve, 60.0) if binding.expand else binding.height)
    box = ctx.layout.row(height=h, width=w)
    item_id = ctx.get_id(f"##table-{name}")
    hovered = ctx.item_add(box, item_id)
    control = binding.control
    io = ctx.io
    px, py = io.mouse_pos
    if hovered:
        control.hover(px, py)
        if io.mouse_clicked[0]:
            control.press(px, py, *box, 0, 2 if io.mouse_double_clicked[0] else 1)
        if io.mouse_clicked[1]:
            control.context(px, py)
        wheel_h = getattr(io, "mouse_wheel_h", 0.0) or (io.mouse_wheel if io.key_shift else 0.0)
        if wheel_h and control._hbar_box is not None:
            control.scroll_columns(-1 if wheel_h > 0 else 1)
        elif io.mouse_wheel:
            control.scroll(-int(io.mouse_wheel) * DataTable.WHEEL_ROWS or
                           (-DataTable.WHEEL_ROWS if io.mouse_wheel > 0 else DataTable.WHEEL_ROWS))
    else:
        control.hovered = None
        if io.mouse_clicked[0]:
            control.filter_focused = False
        # A click anywhere else ends the typing and keeps what was typed, as
        # Enter does; without it the cell stayed open, and uncommitted.
        if (io.mouse_clicked[0] or io.mouse_clicked[1]) and control.editing is not None:
            control.commit_edit()
    if io.mouse_down[0] and (control.bar.needed() or control._hbar_held):
        control.drag(px, py)
    if io.mouse_released[0]:
        control.release()
    if io.key or io.text:
        if hovered or control.filter_focused or control.editing is not None:
            control.key(int(io.key), io.text, 0)
    _column_picker(control, name)
    control.draw(ctx.p, *box)
    if hovered:
        tip, part = control.tooltip_at(px, py)
        if tip:
            ctx.set_tooltip(tip, owner=(item_id, part))


def _column_picker(control: DataTable, name: str) -> None:
    """Keep the header's column list up while it is open; apply what is picked."""
    from .. import overlays
    from .menus import MenuItem, Popup

    if control.picker_at is not None:
        keys = [c.key for c in control.columns if c.visible]
        items = [MenuItem(c.title or c.key, checked=c.key not in control.hidden, checkable=True)
                 for c in control.columns if c.visible]
        panel = Popup(items, title="Columns")
        panel.open_at(*control.picker_at)
        control.picker_panel, control._picker_keys = panel, keys
        control.picker_at = None
    panel = control.picker_panel
    if panel is None:
        return

    def close() -> None:
        control.picker_panel = None

    def picked(item) -> None:
        index = next((i for i, row in enumerate(panel.entries) if row is item), None)
        if index is not None and index < len(control._picker_keys):
            key = control._picker_keys[index]
            control.set_column_hidden(key, key not in control.hidden)
        close()

    overlays.popup(("table-picker", name), panel, on_close=close, on_pick=picked)
