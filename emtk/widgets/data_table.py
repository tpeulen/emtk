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
    the record field holding a row's longer description. The Qt table shows
    it as a tooltip; a painter has no tooltips, so this table shows the
    selected row's under the rows;
``row_key``
    the record field that identifies a row, so a selection survives rows
    streaming in above it. Without one, a row is its position in the source;
``editable`` (the section, or one column)
    cells the user may change: a ``True``/``False`` cell is a check box a click
    flips, any other cell opens for typing on a double click (Enter commits,
    Escape cancels, a click elsewhere commits). The new value is written into
    a mutable record and handed to ``edited_call(record, key, value)``;
``delete_call``
    called with the selected record when Delete (or Backspace) is pressed.

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
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
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
    ) -> None:
        self.columns: list[TableColumn] = list(columns)
        self.on_select = on_select
        self.on_activate = on_activate
        self.on_edit = on_edit
        self.on_delete = on_delete
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
        """The columns drawn."""
        return [c for c in self.columns if c.visible]

    def order(self) -> list[int]:
        """Source indices, filtered and sorted as displayed (cached per change)."""
        wanted = (self.revision, self.row_count(), self.filter.text, self.sort_key_name,
                  self.descending, tuple(c.key for c in self.columns))
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
        self._order = indices
        self._order_for = wanted
        return indices

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

    def column_at(self, x: float) -> Optional[TableColumn]:
        """The column under an x position of the last draw."""
        if self._header_box is None:
            return None
        edge = self._header_box[0]
        for column, width in zip(self.visible_columns(), self._widths):
            if edge <= x < edge + width:
                return column
            edge += width
        return None

    def _column_widths(self, total: float) -> list[float]:
        columns = self.visible_columns()
        fixed = sum(c.width for c in columns if c.width)
        flexible = [c for c in columns if not c.width]
        share = max(total - fixed, 0.0) / len(flexible) if flexible else 0.0
        widths = [c.width if c.width else share for c in columns]
        scale = total / sum(widths) if sum(widths) > total and sum(widths) > 0 else 1.0
        return [w * scale for w in widths]

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
        header_h = line * 1.35
        order = self.order()
        body_top = cursor + header_h
        body_h = max(y + h - note_h - body_top, row_h)
        self._visible = max(int(body_h // row_h), 1)
        self.bar.clamp(len(order), self._visible)
        bar_w = self.bar.width if self.bar.needed() else 0.0
        list_w = max(w - bar_w, 1.0)
        columns = self.visible_columns()
        self._widths = self._column_widths(list_w)
        self._header_box = (x, cursor, list_w, header_h)
        self._body_box = (x, body_top, list_w, body_h)

        p.stroke_rect(x, cursor, list_w, header_h, _style.BORDER, _style.HEADER_BG)
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

        p.stroke_rect(x, body_top, list_w, body_h, _style.BORDER, _style.TABLE_ROW_BG)
        p.push_clip(x, body_top, list_w, body_h)
        top = self.bar.top
        row_y = body_top
        for position in range(top, min(top + self._visible + 1, len(order))):
            self._draw_row(p, position, order[position], columns, order, x, row_y, row_h)
            row_y += row_h
        p.pop_clip()
        if bar_w:
            self.bar.draw(p, x + list_w, body_top, body_h)

        if note_lines:
            note_y = body_top + body_h + 4.0
            for offset, text in enumerate(_wrap(p, note, w - 8.0, note_lines)):
                p.text(x + 4.0, note_y + offset * line, w - 8.0, line,
                       ALIGN_VCENTER | ALIGN_LEFT, text, _style.DIM)

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
        if self.selected_key is not None and key == self.selected_key:
            background = _style.ROW_SEL
        elif position == self.hovered:
            background = _style.HEADER
        else:
            background = _style.TABLE_ROW_BG_ALT if position % 2 else None
        if background is not None:
            p.fill_rect(x, y, sum(self._widths), h, background)
        text_h = min(h, p.line_height() * 1.15)
        col_x = x
        for column, width in zip(columns, self._widths):
            value = self.value(index, column.key)
            if self.editing == (index, column.key):
                self._draw_editor(p, col_x, y, width, h)
                col_x += width
                continue
            if isinstance(value, (bool, _np_bool())):
                self._draw_check(p, col_x, y, width, h, bool(value))
                col_x += width
                continue
            bar = column.bar(value)
            if bar is not None:
                start, end, colour = bar
                bar_h = max(3.0, h * 0.14)
                inner = width - 8.0
                p.fill_rect(col_x + 4.0 + start * inner, y + h - bar_h - 2.0,
                            max((end - start) * inner, 1.0), bar_h, colour)
            right = self._right_aligned(column, order)
            p.text(col_x + 6.0, y + 1.0, max(width - 12.0, 1.0), text_h,
                   ALIGN_VCENTER | (ALIGN_RIGHT if right else ALIGN_LEFT),
                   fit_text(p, column.text(value), width - 12.0), _style.TEXT)
            col_x += width

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
                    else float(text)
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
        if column is not None and column.editable:
            value = self.value(index, column.key)
            if isinstance(value, (bool, _np_bool())):
                self._write(index, column.key, not bool(value))
                return True
            if clicks > 1:
                self.begin_edit(index, column.key)
                return True
        if clicks > 1 and self.on_activate is not None:
            self.on_activate(index)
        return True

    def _select_position(self, position: int) -> None:
        order = self.order()
        if not order:
            return
        position = min(max(position, 0), len(order) - 1)
        index = order[position]
        key = self.key_of(index)
        changed = key != self.selected_key
        self.selected_key = key
        self._scroll_to(position)
        if changed and self.on_select is not None:
            self.on_select(index)

    def drag(self, x: float, y: float, *_box: Any) -> bool:
        """Continue a scrollbar drag."""
        return self.bar.drag(y)

    def release(self, *_args: Any, **_kw: Any) -> None:
        """End a scrollbar drag."""
        self.bar.release()

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
            index = self.selected_index()
            if index is None or self.on_delete is None:
                return False
            self.on_delete(index)
            self.selected_key = None
            return True
        current = next((pos for pos, i in enumerate(order)
                        if self.key_of(i) == self.selected_key), None)
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
        self.editable = bool(merged.get("editable", False))
        self.height = float(merged.get("height", 240) or 240)
        self.expand = bool(merged.get("expand", False))
        self._declared_columns = list(merged.get("columns") or [])
        self.control = DataTable(
            on_select=self._on_select,
            on_activate=self._on_activate,
            on_edit=self._on_edit,
            on_delete=self._on_delete,
            filter_box=bool(merged.get("filter", False)),
            tooltip_key=str(merged.get("tooltip_key", "") or ""),
            row_key=str(merged.get("row_key", "") or ""),
        )
        sort = merged.get("sort")
        if isinstance(sort, Mapping) and sort.get("key"):
            self.control.sort_by(str(sort["key"]), bool(sort.get("descending", False)))
        self._data_token: tuple = ()
        self._columns_token: tuple = ()
        self.refresh()

    # -- reading the model ------------------------------------------------------- #

    def _call(self, name: str) -> Any:
        if not name:
            return None
        value = getattr(self.model, name, None)
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

    def _on_select(self, index: Optional[int]) -> None:
        payload = self.record(index)
        if self.selected_attr:
            try:
                setattr(self.model, self.selected_attr, payload if payload is not None else {})
            except Exception:  # noqa: BLE001
                pass
        if self.selected_call:
            fn = getattr(self.model, self.selected_call, None)
            if callable(fn):
                fn(payload)

    def _on_edit(self, index: int, key: str, value: Any) -> None:
        if self.edited_call:
            fn = getattr(self.model, self.edited_call, None)
            if callable(fn):
                fn(self.record(index), key, value)

    def _on_delete(self, index: int) -> None:
        if self.delete_call:
            fn = getattr(self.model, self.delete_call, None)
            if callable(fn):
                fn(self.record(index))

    def _on_activate(self, index: int) -> None:
        if self.activated_call:
            fn = getattr(self.model, self.activated_call, None)
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
        max(float(avail_h), 60.0) if binding.expand else binding.height)
    box = ctx.layout.row(height=h, width=w)
    hovered = ctx.item_add(box, ctx.get_id(f"##table-{name}"))
    control = binding.control
    io = ctx.io
    px, py = io.mouse_pos
    if hovered:
        control.hover(px, py)
        if io.mouse_clicked[0]:
            control.press(px, py, *box, 0, 2 if io.mouse_double_clicked[0] else 1)
        if io.mouse_wheel:
            control.scroll(-int(io.mouse_wheel) * DataTable.WHEEL_ROWS or
                           (-DataTable.WHEEL_ROWS if io.mouse_wheel > 0 else DataTable.WHEEL_ROWS))
    else:
        control.hovered = None
        if io.mouse_clicked[0]:
            control.filter_focused = False
    if io.mouse_down[0] and control.bar.needed():
        control.drag(px, py)
    if io.mouse_released[0]:
        control.release()
    if io.key or io.text:
        if hovered or control.filter_focused or control.editing is not None:
            control.key(int(io.key), io.text, 0)
    control.draw(ctx.p, *box)
