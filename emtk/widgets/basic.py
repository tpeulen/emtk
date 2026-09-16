"""Reusable painter-level ImGui-style controls.

Everything is drawn through :class:`~emtk.painter.Painter`'s six
operations so controls run natively on desktop quads, Qt, and in the browser.

Includes:
- SliderFloat
- ColorEdit4
- Table (scrolling)
- ScrollBar
- Checkbox
- Combo
- Button
- ProgressBar
- TreeNode
- Separator
- Toggle
- RadioGroup
- InputInt
- ListBox
- Tabs
- PlotLines
- Histogram
- Tooltip
- TextInput

Every control keeps its *state* and its *hit test* in the same object as its
drawing, so a host that owns neither a widget tree nor a layout pass can still
put one on screen: construct it, draw it into a box, and hand it the presses
that land in that box.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Painter

__all__ = [
    "fit_text",
    "ScrollBar",
    "SliderFloat",
    "ColorEdit4",
    "Table",
    "Checkbox",
    "Combo",
    "Button",
    "ProgressBar",
    "TreeNode",
    "Separator",
    "Toggle",
    "RadioGroup",
    "InputInt",
    "ListBox",
    "Tabs",
    "PlotLines",
    "Histogram",
    "Tooltip",
    "TextInput",
]

# The ImGui StyleColorsDark palette now lives in :mod:`.style`, so that the
# modules ported alongside this one name the same colours rather than keeping
# their own drifting copies. These are aliases and nothing more -- every value
# is the one this module shipped with, and `style` records which of them
# differ from the reference's, and why. Written as assignments rather than
# `from .style import X as _X` because fourteen aliased imports are split into
# fourteen statements by the import sorter, which buries the one thing this
# block is trying to say: that these names are that module's, unchanged.
from ..style import (
    TEXT as _TEXT,
    DIM as _DIM,
    GOLD as _GOLD,
    HEADER_BG as _HEADER_BG,
    TRACK_BG as _TRACK_BG,
    THUMB as _THUMB_COLOR,
    THUMB_HELD as _THUMB_HELD,
    BORDER as _BORDER,
    TABLE_ROW_BG as _ROW_EVEN,
    TABLE_ROW_BG_ALT as _ROW_ODD,
    ROW_SEL as _ROW_SEL,
    CHECK_ON as _CHECK_ON,
    BTN_BG as _BTN_BG,
    BTN_HELD as _BTN_HELD,
    _PERCENT_SPEC as _PERCENT_SPEC,
    fit_text as fit_text,
    format_value as _format,
)

#: The percentage spec ``%.0%``, kept importable from here because callers
#: outside this package reach for it. See :mod:`.style` for what it is.

#: ``label`` shortened with a trailing dot until it fits. Lives in
#: :mod:`.style` so the ported control modules share one implementation; kept
#: under its original name here because this module's controls and at least
#: one plugin outside it already call it.

#: Render a number through a control's format string -- printf spec, or the
#: percentage spec above. Also :mod:`.style`'s, for the same reason;
#: Lumis Quest imports it from this module by this name.


class SliderFloat:
    """A floating-point slider control (ImGui style)."""

    def __init__(
        self,
        label: str,
        v_min: float,
        v_max: float,
        value: float = 0.0,
        fmt: str = "%.2f",
        step: float | None = None,
    ) -> None:
        self.label = label
        self.v_min = float(v_min)
        self.v_max = float(v_max)
        #: Snap to multiples of this (from ``v_min``); ``None`` is continuous.
        #: An integer-valued slider (``step=1``) then reads and lands on whole
        #: numbers, which is what a "passes" or a "count" slider must do.
        self.step = float(step) if step else None
        self.fmt = fmt
        self._held = False
        self.value = self._snap(float(min(max(value, self.v_min), self.v_max)))

    def _snap(self, value: float) -> float:
        if not self.step:
            return value
        n = round((value - self.v_min) / self.step)
        return float(min(max(self.v_min + n * self.step, self.v_min), self.v_max))

    @property
    def fraction(self) -> float:
        """Fraction of track filled (0.0..1.0)."""
        span = (self.v_max - self.v_min) or 1.0
        return min(max((self.value - self.v_min) / span, 0.0), 1.0)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the slider track, thumb and text label."""
        norm = self.fraction

        # Track background
        p.stroke_rect(x, y, w, h, _BORDER, _TRACK_BG)

        # Filled track progress
        fill_w = norm * w
        if fill_w > 0:
            p.fill_rect(x, y, fill_w, h, _THUMB_COLOR)

        # Thumb knob, centred on the value: the pointer sets the fraction of
        # the track, so the thumb has to sit *on* that point rather than
        # starting at it, or the knob trails the cursor by half its width.
        thumb_w = 8.0
        thumb_x = min(max(x + norm * w - thumb_w * 0.5, x), x + max(w - thumb_w, 0.0))
        thumb_color = _THUMB_HELD if self._held else _GOLD
        p.fill_rect(thumb_x, y, thumb_w, h, thumb_color)

        # Value text + label
        text_val = _format(self.fmt, self.value)
        display = f"{self.label}: {text_val}" if self.label else text_val
        p.text(x + 4.0, y, max(w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, display, _TEXT)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Returns True if press hit the control."""
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            self._held = False
            return False
        self._held = True
        self._update_from_pos(x, box_x, box_w)
        return True

    def drag(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse drag. Returns True if value changed."""
        if not self._held:
            return False
        self._update_from_pos(x, box_x, box_w)
        return True

    def release(self) -> None:
        """Release drag hold."""
        self._held = False

    def nudge(self, delta: float) -> float:
        """Step value up/down by *delta* (or by one snap step when ``step`` is set and delta is +-1)."""
        if self.step and abs(delta) == 1.0:
            delta = delta * self.step
        self.value = self._snap(float(min(max(self.value + delta, self.v_min), self.v_max)))
        return self.value

    def set_fraction(self, fraction: float) -> float:
        """Set the value from a 0..1 position along the track.

        Parameters
        ----------
        fraction : float
            Position along the track; clamped to 0..1.

        Returns
        -------
        float
            The resulting value.
        """
        fraction = min(max(float(fraction), 0.0), 1.0)
        self.value = self._snap(self.v_min + fraction * (self.v_max - self.v_min))
        return self.value

    def _update_from_pos(self, x: float, box_x: float, box_w: float) -> None:
        # The pointer's fraction **of the track**, so a click a quarter along
        # is a quarter of the range -- what the value means, and what a caller
        # (and its test) computes. The thumb is drawn centred on that value,
        # so it still lands under the cursor; mapping the pointer onto the
        # thumb's own travel instead shifted every click by half a thumb.
        fraction = (x - box_x) / max(box_w, 1.0)
        fraction = min(max(fraction, 0.0), 1.0)
        self.value = self._snap(self.v_min + fraction * (self.v_max - self.v_min))


class ColorEdit4:
    """A color swatch control with RGBA components (ImGui style)."""

    def __init__(self, label: str = "", color: Sequence = (255, 255, 255, 255)) -> None:
        self.label = label
        self.color = self._parse_color(color)

    def _parse_color(self, c: Sequence) -> tuple[int, int, int, int]:
        c_list = list(c)
        if len(c_list) < 4:
            c_list = c_list + [1.0 if isinstance(c_list[0], float) else 255] * (4 - len(c_list))
        if any(isinstance(val, float) for val in c_list):
            return tuple(int(round(float(val) * (255.0 if float(val) <= 1.0 else 1.0))) for val in c_list[:4])
        return tuple(int(val) for val in c_list[:4])

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the color swatch square and label text."""
        swatch_size = h
        p.stroke_rect(x, y, swatch_size, swatch_size, _BORDER, self.color)

        if self.label:
            p.text(x + swatch_size + 6.0, y, max(w - swatch_size - 6.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Returns True if click landed inside the swatch control."""
        return box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h


class ScrollBar:
    """A vertical scrollbar: geometry, drawing and the drag, in one place.

    Every scrolling panel here had its own copy of "how tall is the thumb,
    where does a click put the window, is the drag still held" -- three copies
    that disagreed about the last row. This is the one copy.

    Parameters
    ----------
    width : float, optional
        How wide the bar draws.
    """

    def __init__(self, width: float = 7.0) -> None:
        self.width = float(width)
        self.top = 0
        self.held = False
        self._box: tuple[float, float, float, float] | None = None
        self._total = 0
        self._visible = 1

    # ------------------------------------------------------------------ #
    def clamp(self, total: int, visible: int) -> int:
        """Keep the window inside a list of ``total`` rows showing ``visible``."""
        self._total, self._visible = int(total), max(int(visible), 1)
        self.top = max(0, min(self.top, max(self._total - self._visible, 0)))
        return self.top

    def scroll(self, rows: int) -> int:
        """Move the window by ``rows``."""
        self.top += int(rows)
        return self.clamp(self._total, self._visible)

    def needed(self) -> bool:
        """Whether there is anything to scroll."""
        return self._total > self._visible

    def draw(self, p: Painter, x: float, y: float, h: float) -> None:
        """Paint the bar down the right-hand edge of a list."""
        self._box = (x, y, self.width, h)
        p.fill_rect(x, y, self.width, h, _ROW_ODD)
        if not self.needed():
            return
        span = max(h * self._visible / max(self._total, 1), 10.0)
        travel = max(h - span, 0.0)
        at = y + travel * (self.top / max(self._total - self._visible, 1))
        p.fill_rect(x + 1.0, at, max(self.width - 2.0, 1.0), span,
                    _THUMB_HELD if self.held else _DIM)

    # ------------------------------------------------------------------ #
    def hit(self, x: float, y: float) -> bool:
        """Whether a press landed on the bar, as last drawn."""
        if self._box is None:
            return False
        box_x, box_y, box_w, box_h = self._box
        return box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h

    def press(self, x: float, y: float) -> bool:
        """Grab the bar. Returns whether it was hit."""
        if not self.hit(x, y):
            return False
        self.held = True
        self.drag_to(y)
        return True

    def drag_to(self, y: float) -> int:
        """Put the window where the bar was dragged."""
        if self._box is None:
            return self.top
        _, box_y, _, box_h = self._box
        fraction = (y - box_y) / max(box_h, 1e-6)
        self.top = int(round(min(max(fraction, 0.0), 1.0)
                             * max(self._total - self._visible, 0)))
        return self.clamp(self._total, self._visible)

    def drag(self, y: float) -> bool:
        """Continue a drag. Returns whether anything moved."""
        if not self.held:
            return False
        self.drag_to(y)
        return True

    def release(self) -> None:
        """Let go."""
        self.held = False


class Table:
    """An ImGui-style multi-column data table, scrolled when it does not fit.

    Parameters
    ----------
    headers : sequence of str
        Column title headers.
    rows : sequence of sequence of str
        2D matrix of cell contents.
    col_widths : sequence of float, optional
        Relative or pixel widths per column. Defaults to equal split.
    selected_row : int, optional
        Index of highlighted row.
    sort_col : int, optional
        Active sort column index.
    sort_ascending : bool, optional
        Sort direction.
    row_scale : float, optional
        Row height as a multiple of the line height. The default is tight on
        purpose: a table is read as a block, and the space between rows is
        space the rows themselves do not get.

    Notes
    -----
    Rows past the bottom are **scrolled**, not dropped. They used to be simply
    not drawn -- and the hit test then read them at a *fixed* 18-pixel pitch
    that had nothing to do with the pitch they were drawn at, so clicking a row
    selected a different one as soon as the font was not exactly 13 px tall.
    Both now come from the geometry the last draw actually used.
    """

    def __init__(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        col_widths: Sequence[float] | None = None,
        selected_row: int | None = None,
        sort_col: int | None = None,
        sort_ascending: bool = True,
        row_scale: float = 1.15,
    ) -> None:
        self.headers = list(headers)
        self.rows = [list(r) for r in rows]
        self.col_widths = list(col_widths) if col_widths else None
        self.selected_row = selected_row
        self.sort_col = sort_col
        self.sort_ascending = sort_ascending
        self.row_scale = float(row_scale)
        self.bar = ScrollBar()
        #: Set by :meth:`draw`: ``(x, y, w, row_h, header_h, visible)``.
        self._geometry: tuple[float, float, float, float, float, int] | None = None

    @property
    def top(self) -> int:
        """First visible row."""
        return self.bar.top

    def scroll(self, rows: int) -> int:
        """Scroll by whole rows."""
        return self.bar.scroll(rows)

    def sort(self, col_index: int) -> None:
        """Sort rows by the given column."""
        if not (0 <= col_index < len(self.headers)):
            return
        if self.sort_col == col_index:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_col = col_index
            self.sort_ascending = True

        def key_fn(row):
            val = row[col_index] if col_index < len(row) else ""
            try:
                return (0, float(val))
            except ValueError:
                return (1, str(val).lower())

        self.rows.sort(key=key_fn, reverse=not self.sort_ascending)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the header row, the visible data rows and the scrollbar."""
        num_cols = max(len(self.headers), 1)
        row_h = p.line_height() * self.row_scale
        header_h = row_h * 1.1
        body_h = max(h - header_h, row_h)
        visible = max(int(body_h / max(row_h, 1e-6)), 1)
        self.bar.clamp(len(self.rows), visible)
        list_w = w - (self.bar.width if self.bar.needed() else 0.0)

        if self.col_widths and len(self.col_widths) == num_cols:
            total_w = sum(self.col_widths) or 1.0
            widths = [list_w * (cw / total_w) for cw in self.col_widths]
        else:
            widths = [list_w / num_cols] * num_cols
        self._geometry = (x, y, list_w, row_h, header_h, visible)

        p.push_clip(x, y, w, h)

        p.stroke_rect(x, y, list_w, header_h, _BORDER, _HEADER_BG)
        col_x = x
        for idx, head in enumerate(self.headers):
            cw = widths[idx]
            sort_mark = " ▴" if (self.sort_col == idx and self.sort_ascending) else (" ▾" if self.sort_col == idx else "")
            p.text(col_x + 3.0, y, max(cw - 6.0, 1.0), header_h,
                   ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, f"{head}{sort_mark}", cw - 6.0), _GOLD, bold=True)
            p.stroke_rect(col_x, y, cw, header_h, _BORDER, None)
            col_x += cw

        row_y = y + header_h
        for offset in range(visible):
            r_idx = self.bar.top + offset
            if r_idx >= len(self.rows):
                break
            row_data = self.rows[r_idx]
            bg_color = _ROW_SEL if (self.selected_row == r_idx) else (_ROW_EVEN if (r_idx % 2 == 0) else _ROW_ODD)
            p.stroke_rect(x, row_y, list_w, row_h, _BORDER, bg_color)
            col_x = x
            for c_idx in range(num_cols):
                cw = widths[c_idx]
                cell_text = str(row_data[c_idx]) if c_idx < len(row_data) else ""
                p.text(col_x + 3.0, row_y, max(cw - 6.0, 1.0), row_h,
                       ALIGN_VCENTER | ALIGN_LEFT,
                       fit_text(p, cell_text, cw - 6.0), _TEXT)
                col_x += cw
            row_y += row_h

        p.pop_clip()
        if self.bar.needed():
            self.bar.draw(p, x + list_w, y + header_h, h - header_h)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> tuple[str, int] | None:
        """Process mouse press.

        Returns
        -------
        tuple or None
            ``("header", col)``, ``("row", row)`` -- the row's index in the
            whole table, not in the visible window -- ``("scroll", top)``, or
            ``None``.
        """
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            return None
        if self.bar.press(x, y):
            return ("scroll", self.bar.top)
        if self._geometry is None:
            return None
        geo_x, geo_y, list_w, row_h, header_h, _visible = self._geometry
        if y <= geo_y + header_h:
            num_cols = max(len(self.headers), 1)
            widths = ([list_w * (cw / (sum(self.col_widths) or 1.0)) for cw in self.col_widths]
                      if self.col_widths and len(self.col_widths) == num_cols
                      else [list_w / num_cols] * num_cols)
            edge, col_idx = geo_x, 0
            for idx, cw in enumerate(widths):
                if x < edge + cw:
                    col_idx = idx
                    break
                edge += cw
                col_idx = idx
            self.sort(col_idx)
            return ("header", col_idx)
        row_idx = self.bar.top + int((y - (geo_y + header_h)) / max(row_h, 1e-6))
        if 0 <= row_idx < len(self.rows):
            self.selected_row = row_idx
            return ("row", row_idx)
        return None

    def drag(self, y: float) -> bool:
        """Continue a scrollbar drag."""
        return self.bar.drag(y)

    def release(self) -> None:
        """End a scrollbar drag."""
        self.bar.release()


class Checkbox:
    """A checkbox control (ImGui style)."""

    def __init__(self, label: str, checked: bool = False) -> None:
        self.label = label
        self.checked = bool(checked)

    def toggle(self) -> bool:
        """Toggle checked state."""
        self.checked = not self.checked
        return self.checked

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the checkbox square, checkmark and label text."""
        box_size = h * 0.8
        p.stroke_rect(x, y + (h - box_size) * 0.5, box_size, box_size, _BORDER, _TRACK_BG)

        if self.checked:
            p.fill_rect(
                x + box_size * 0.25,
                y + (h - box_size) * 0.5 + box_size * 0.25,
                box_size * 0.5,
                box_size * 0.5,
                _CHECK_ON,
            )

        if self.label:
            p.text(x + box_size + 6.0, y, max(w - box_size - 6.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Toggles state if hit."""
        if box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h:
            self.toggle()
            return True
        return False


class Combo:
    """A dropdown select combo control (ImGui style)."""

    def __init__(self, label: str, options: Sequence[str], index: int = 0) -> None:
        self.label = label
        self.options = list(options)
        self.index = max(0, min(index, len(self.options) - 1)) if self.options else 0

    @property
    def value(self) -> str:
        """Selected option string."""
        return self.options[self.index] if self.options else ""

    def cycle(self, step: int = 1) -> str:
        """Cycle option index forward or backward."""
        if not self.options:
            return ""
        self.index = (self.index + step) % len(self.options)
        return self.value

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint selector box `< Value >` and label."""
        val_str = self.value
        display = f"{self.label}: < {val_str} >" if self.label else f"< {val_str} >"
        p.stroke_rect(x, y, w, h, _BORDER, _BTN_BG)
        p.text(x + 4.0, y, max(w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, display, _GOLD)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> str:
        """Process mouse press. Cycles option if hit."""
        if box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h:
            return self.cycle(1)
        return self.value


class Button:
    """An action button control (ImGui style)."""

    def __init__(self, label: str) -> None:
        self.label = label
        self._held = False

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint button box and label text."""
        bg = _BTN_HELD if self._held else _BTN_BG
        p.stroke_rect(x, y, w, h, _BORDER, bg)
        p.text(x, y, w, h, ALIGN_CENTER, f"[ {self.label} ]", _TEXT)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Returns True if hit."""
        if box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h:
            self._held = True
            return True
        self._held = False
        return False

    def release(self) -> None:
        """Release press hold."""
        self._held = False


class ProgressBar:
    """A progress bar control (ImGui style)."""

    def __init__(self, label: str = "", fraction: float = 0.0, fmt: str = "%.0%") -> None:
        self.label = label
        self.fraction = max(0.0, min(1.0, float(fraction)))
        self.fmt = fmt

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint progress bar background, fill and text."""
        p.stroke_rect(x, y, w, h, _BORDER, _TRACK_BG)
        fill_w = self.fraction * w
        if fill_w > 0:
            p.fill_rect(x, y, fill_w, h, _THUMB_COLOR)

        percent_str = _format(self.fmt, self.fraction)
        display = f"{self.label} {percent_str}".strip()
        p.text(x, y, w, h, ALIGN_CENTER, display, _TEXT)


class TreeNode:
    """A collapsible tree node control (ImGui style)."""

    def __init__(
        self,
        label: str,
        expanded: bool = False,
        children: Sequence[str] | None = None,
    ) -> None:
        self.label = label
        self.expanded = expanded
        self.children = list(children) if children else []

    def toggle(self) -> bool:
        """Toggle expansion."""
        self.expanded = not self.expanded
        return self.expanded

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint disclosure arrow `v` / `>` and node label."""
        arrow = "v " if self.expanded else "> "
        display = f"{arrow}{self.label}"
        p.text(x + 4.0, y, max(w - 8.0, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT, display, _GOLD)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Toggles node expansion if hit."""
        if box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h:
            self.toggle()
            return True
        return False


class Separator:
    """A horizontal rule, optionally with a caption sitting in it.

    Parameters
    ----------
    label : str, optional
        Caption. Drawn left-aligned with the rule continuing past it, which is
        what makes a run of settings read as groups rather than as one list.
    """

    def __init__(self, label: str = "") -> None:
        self.label = label

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the rule and its caption."""
        mid = y + h * 0.5
        rule_h = max(1.0, h * 0.25)
        if not self.label:
            p.fill_rect(x, mid - rule_h * 0.5, w, rule_h, _BORDER)
            return
        text_w = min(p.text_width(self.label) + 8.0, max(w - 24.0, 0.0))
        p.text(x, y, text_w, h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _DIM)
        rest = w - text_w
        if rest > 0.0:
            p.fill_rect(x + text_w, mid - rule_h * 0.5, rest, rule_h, _BORDER)


class Toggle:
    """An on/off switch: a pill track with a knob that slides.

    A :class:`Checkbox` says "this is ticked"; a switch says "this is *running*",
    and the two read differently at a glance even though the state is one bool.

    Parameters
    ----------
    label : str
        Caption drawn after the pill.
    on : bool, optional
        Initial state.
    """

    def __init__(self, label: str, on: bool = False) -> None:
        self.label = label
        self.on = bool(on)

    def toggle(self) -> bool:
        """Flip the switch and return the new state."""
        self.on = not self.on
        return self.on

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the track, the knob and the label."""
        track_w = h * 2.0
        track_h = h * 0.7
        track_y = y + (h - track_h) * 0.5
        p.stroke_rect(x, track_y, track_w, track_h, _BORDER,
                      _CHECK_ON if self.on else _TRACK_BG)
        knob_w = track_w * 0.45
        knob_x = x + (track_w - knob_w) if self.on else x
        p.fill_rect(knob_x, track_y, knob_w, track_h, _GOLD if self.on else _DIM)
        if self.label:
            left = x + track_w + 6.0
            p.text(left, y, max(w - track_w - 6.0, 1.0), h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Flips the switch if hit."""
        if box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h:
            self.toggle()
            return True
        return False


class RadioGroup:
    """A row of mutually exclusive options.

    Parameters
    ----------
    label : str
        Caption drawn before the options.
    options : sequence of str
        Choices, in the order they are drawn.
    index : int, optional
        Which one is picked.
    """

    def __init__(self, label: str, options: Sequence[str], index: int = 0) -> None:
        self.label = label
        self.options = list(options)
        self.index = max(0, min(index, len(self.options) - 1)) if self.options else 0

    @property
    def value(self) -> str:
        """The picked option."""
        return self.options[self.index] if self.options else ""

    def select(self, index: int) -> str:
        """Pick an option by index (clamped)."""
        if self.options:
            self.index = max(0, min(int(index), len(self.options) - 1))
        return self.value

    def cycle(self, step: int = 1) -> str:
        """Move the pick forward or backward, wrapping."""
        if not self.options:
            return ""
        self.index = (self.index + step) % len(self.options)
        return self.value

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption and one bullet per option."""
        left = x
        if self.label:
            label_w = min(p.text_width(self.label) + 8.0, w * 0.5)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)
            left = x + label_w
        if not self.options:
            return
        cell = max(w - (left - x), 1.0) / len(self.options)
        for idx, option in enumerate(self.options):
            picked = idx == self.index
            cell_x = left + idx * cell
            dot = h * 0.5
            dot_y = y + (h - dot) * 0.5
            p.stroke_rect(cell_x, dot_y, dot, dot, _BORDER, _TRACK_BG)
            if picked:
                p.fill_rect(cell_x + dot * 0.25, dot_y + dot * 0.25,
                            dot * 0.5, dot * 0.5, _THUMB_COLOR)
            p.text(cell_x + dot + 4.0, y, max(cell - dot - 4.0, 1.0), h,
                   ALIGN_VCENTER | ALIGN_LEFT, option, _GOLD if picked else _DIM)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> str:
        """Process mouse press. Picks the option the press landed on."""
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            return self.value
        if not self.options:
            return ""
        cell = box_w / len(self.options)
        return self.select(int((x - box_x) / max(cell, 1e-6)))


class InputInt:
    """A whole-number stepper: ``- value +``.

    Parameters
    ----------
    label : str
        Caption.
    value : int, optional
        Initial value.
    v_min, v_max : int, optional
        Inclusive bounds.
    step : int, optional
        How much one press moves it.
    """

    def __init__(
        self,
        label: str,
        value: int = 0,
        v_min: int = 0,
        v_max: int = 100,
        step: int = 1,
    ) -> None:
        self.label = label
        self.v_min = int(v_min)
        self.v_max = int(v_max)
        self.step = int(step)
        self.value = int(min(max(int(value), self.v_min), self.v_max))

    def set_value(self, value: int) -> int:
        """Set the value, clamped to the bounds."""
        self.value = int(min(max(int(value), self.v_min), self.v_max))
        return self.value

    def increment(self) -> int:
        """Step up."""
        return self.set_value(self.value + self.step)

    def decrement(self) -> int:
        """Step down."""
        return self.set_value(self.value - self.step)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the two steppers and the value between them."""
        btn = h
        if self.label:
            label_w = max(w - btn * 2.0 - 40.0, 1.0)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)
        right = x + w
        p.stroke_rect(right - btn, y, btn, h, _BORDER, _BTN_BG)
        p.text(right - btn, y, btn, h, ALIGN_CENTER, "+", _TEXT)
        p.stroke_rect(right - btn * 3.0, y, btn, h, _BORDER, _BTN_BG)
        p.text(right - btn * 3.0, y, btn, h, ALIGN_CENTER, "-", _TEXT)
        p.text(right - btn * 3.0, y, btn * 3.0, h, ALIGN_CENTER, str(self.value), _GOLD)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> int:
        """Process mouse press. Steps up or down when a stepper is hit."""
        if not (box_y <= y <= box_y + box_h):
            return self.value
        right = box_x + box_w
        if right - box_h <= x <= right:
            return self.increment()
        if right - box_h * 3.0 <= x <= right - box_h * 2.0:
            return self.decrement()
        return self.value


class ListBox:
    """A scrolling list of strings with one selected row.

    Parameters
    ----------
    label : str
        Caption drawn above the list.
    items : sequence of str
        Entries.
    index : int, optional
        Selected entry.
    visible_rows : int, optional
        How many rows the box shows at once; the window follows the selection.
    """

    def __init__(
        self,
        label: str,
        items: Sequence[str],
        index: int = 0,
        visible_rows: int = 6,
    ) -> None:
        self.label = label
        self.items = list(items)
        self.index = max(0, min(index, len(self.items) - 1)) if self.items else 0
        self.visible_rows = max(1, int(visible_rows))

    @property
    def value(self) -> str:
        """The selected entry."""
        return self.items[self.index] if self.items else ""

    @property
    def first_visible(self) -> int:
        """Index of the top row of the window that keeps the selection in view."""
        if self.index < self.visible_rows:
            return 0
        return min(self.index - self.visible_rows + 1,
                   max(len(self.items) - self.visible_rows, 0))

    def move(self, delta: int) -> str:
        """Move the selection, wrapping at both ends."""
        if not self.items:
            return ""
        self.index = (self.index + delta) % len(self.items)
        return self.value

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the framed list and its rows."""
        top = y
        if self.label:
            head_h = h / (self.visible_rows + 1)
            p.text(x, y, w, head_h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _DIM)
            top = y + head_h
        body_h = max(y + h - top, 1.0)
        p.stroke_rect(x, top, w, body_h, _BORDER, _ROW_EVEN)
        p.push_clip(x, top, w, body_h)
        row_h = body_h / self.visible_rows
        start = self.first_visible
        for offset in range(self.visible_rows):
            idx = start + offset
            if idx >= len(self.items):
                break
            row_y = top + offset * row_h
            if idx == self.index:
                p.fill_rect(x, row_y, w, row_h, _ROW_SEL)
            p.text(x + 5.0, row_y, max(w - 10.0, 1.0), row_h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.items[idx],
                   _TEXT if idx == self.index else _DIM)
        p.pop_clip()

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> int | None:
        """Process mouse press. Returns the row index hit, or ``None``."""
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            return None
        row_h = box_h / self.visible_rows
        idx = self.first_visible + int((y - box_y) / max(row_h, 1e-6))
        if 0 <= idx < len(self.items):
            self.index = idx
            return idx
        return None


class Tabs:
    """A strip of tabs, one of them current.

    Parameters
    ----------
    labels : sequence of str
        Tab captions, left to right.
    index : int, optional
        Which tab is current.
    """

    def __init__(self, labels: Sequence[str], index: int = 0) -> None:
        self.labels = list(labels)
        self.index = max(0, min(index, len(self.labels) - 1)) if self.labels else 0

    @property
    def value(self) -> str:
        """The current tab's caption."""
        return self.labels[self.index] if self.labels else ""

    def select(self, index: int) -> str:
        """Make a tab current, by index (clamped)."""
        if self.labels:
            self.index = max(0, min(int(index), len(self.labels) - 1))
        return self.value

    def cycle(self, step: int = 1) -> str:
        """Move to the next or previous tab, wrapping."""
        if not self.labels:
            return ""
        self.index = (self.index + step) % len(self.labels)
        return self.value

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint one pill per tab, the current one lit.

        A label wider than its pill is shortened rather than drawn over the
        neighbour: a strip is sized by how many tabs there are, so the longest
        caption in the set decides whether the whole row is legible, and one
        long word running into the tab beside it is the failure that looks
        like a layout bug rather than a caption that did not fit.
        """
        if not self.labels:
            return
        cell = w / len(self.labels)
        for idx, label in enumerate(self.labels):
            current = idx == self.index
            cell_x = x + idx * cell
            pill_w = cell * 0.92
            p.stroke_rect(cell_x, y, pill_w, h, _BORDER,
                          _HEADER_BG if current else _TRACK_BG)
            p.text(cell_x, y, pill_w, h, ALIGN_CENTER,
                   fit_text(p, label, pill_w - 4.0),
                   _GOLD if current else _DIM)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> int | None:
        """Process mouse press. Returns the tab index hit, or ``None``."""
        if not (box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h):
            return None
        if not self.labels:
            return None
        idx = int((x - box_x) / max(box_w / len(self.labels), 1e-6))
        self.select(idx)
        return self.index


class PlotLines:
    """A sparkline: a run of samples drawn as a staircase inside a frame.

    The painter has no line operation on purpose -- everything is a rectangle --
    so a segment is drawn as the column that spans it. At sparkline sizes that
    is indistinguishable from a polyline, and it stays exact under any backend.

    Parameters
    ----------
    label : str
        Caption drawn over the plot.
    values : sequence of float
        Samples, oldest first.
    v_min, v_max : float, optional
        Fixed vertical range. Taken from the data when omitted.
    """

    def __init__(
        self,
        label: str,
        values: Sequence[float],
        v_min: float | None = None,
        v_max: float | None = None,
    ) -> None:
        self.label = label
        self.values = [float(v) for v in values]
        self.v_min = v_min
        self.v_max = v_max

    def range(self) -> tuple[float, float]:
        """The vertical range actually used, as ``(low, high)``."""
        if not self.values:
            return (0.0, 1.0)
        low = float(self.v_min) if self.v_min is not None else min(self.values)
        high = float(self.v_max) if self.v_max is not None else max(self.values)
        if high <= low:
            high = low + 1.0
        return (low, high)

    def _y(self, value: float, y: float, h: float) -> float:
        low, high = self.range()
        norm = (float(value) - low) / (high - low)
        return y + h - min(max(norm, 0.0), 1.0) * h

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, the staircase and the caption."""
        p.stroke_rect(x, y, w, h, _BORDER, _TRACK_BG)
        if len(self.values) >= 2:
            p.push_clip(x, y, w, h)
            step = w / (len(self.values) - 1)
            thick = max(1.0, h * 0.06)
            previous = self._y(self.values[0], y, h)
            for idx in range(1, len(self.values)):
                here = self._y(self.values[idx], y, h)
                seg_x = x + (idx - 1) * step
                top = min(previous, here)
                span = max(abs(here - previous), thick)
                p.fill_rect(seg_x, top, max(step, thick), span, _THUMB_COLOR)
                previous = here
            p.pop_clip()
        if self.label:
            p.text(x + 4.0, y, max(w - 8.0, 1.0), h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)


class Histogram:
    """A bar chart of a run of samples.

    Parameters
    ----------
    label : str
        Caption drawn over the bars.
    values : sequence of float
        Bar heights, left to right.
    v_min, v_max : float, optional
        Fixed vertical range. Taken from the data (with zero as the floor) when
        omitted -- bars that do not start at zero lie about their proportions.
    """

    def __init__(
        self,
        label: str,
        values: Sequence[float],
        v_min: float | None = None,
        v_max: float | None = None,
    ) -> None:
        self.label = label
        self.values = [float(v) for v in values]
        self.v_min = v_min
        self.v_max = v_max

    def range(self) -> tuple[float, float]:
        """The vertical range actually used, as ``(low, high)``."""
        if not self.values:
            return (0.0, 1.0)
        low = float(self.v_min) if self.v_min is not None else min(0.0, min(self.values))
        high = float(self.v_max) if self.v_max is not None else max(self.values)
        if high <= low:
            high = low + 1.0
        return (low, high)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame, one bar per sample and the caption."""
        p.stroke_rect(x, y, w, h, _BORDER, _TRACK_BG)
        if self.values:
            p.push_clip(x, y, w, h)
            low, high = self.range()
            cell = w / len(self.values)
            for idx, value in enumerate(self.values):
                norm = (value - low) / (high - low)
                norm = min(max(norm, 0.0), 1.0)
                bar_h = norm * h
                p.fill_rect(x + idx * cell + cell * 0.1, y + h - bar_h,
                            max(cell * 0.8, 1.0), max(bar_h, 1.0), _THUMB_COLOR)
            p.pop_clip()
        if self.label:
            p.text(x + 4.0, y, max(w - 8.0, 1.0), h,
                   ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)


class Tooltip:
    """A framed floating box of one or more lines.

    Parameters
    ----------
    lines : str or sequence of str
        Contents. A single string is one line.
    """

    def __init__(self, lines: str | Sequence[str]) -> None:
        self.lines = [lines] if isinstance(lines, str) else [str(one) for one in lines]

    def size(self, p: Painter) -> tuple[float, float]:
        """Measured ``(width, height)`` the box needs for its contents."""
        line_h = p.line_height() * 1.2
        width = max((p.text_width(one) for one in self.lines), default=0.0)
        return (width + 12.0, line_h * max(len(self.lines), 1) + 8.0)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the box and its lines."""
        p.stroke_rect(x, y, w, h, _BORDER, _ROW_ODD)
        line_h = p.line_height() * 1.2
        for idx, line in enumerate(self.lines):
            p.text(x + 6.0, y + 4.0 + idx * line_h, max(w - 12.0, 1.0), line_h,
                   ALIGN_VCENTER | ALIGN_LEFT, line, _TEXT)


class TextInput:
    """A one-line editable field with a caret.

    The editing itself is :class:`~emtk.widgets.text_field.TextField` --
    this adds the box, the caret and the placeholder, and nothing else, so a
    host that already routes keys into a field keeps doing exactly that.

    Parameters
    ----------
    label : str, optional
        Caption drawn before the box.
    text : str, optional
        Initial contents.
    placeholder : str, optional
        Drawn dim when the field is empty.
    """

    def __init__(self, label: str = "", text: str = "", placeholder: str = "") -> None:
        from .text_field import TextField

        self.label = label
        self.field = TextField(placeholder=placeholder)
        if text:
            self.field.set_text(text)

    @property
    def text(self) -> str:
        """The current contents."""
        return self.field.text

    @property
    def cursor(self) -> int:
        """Caret position, in characters from the start."""
        return self.field.cursor

    def set_text(self, text: str) -> None:
        """Replace the contents, caret at the end."""
        self.field.set_text(text)

    def insert(self, text: str) -> str:
        """Type printable characters at the caret."""
        clean = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
        if clean:
            field = self.field
            field.text = field.text[: field.cursor] + clean + field.text[field.cursor:]
            field.cursor += len(clean)
            field._changed()
        return self.field.text

    def backspace(self) -> str:
        """Delete the character before the caret."""
        field = self.field
        if field.cursor > 0:
            field.text = field.text[: field.cursor - 1] + field.text[field.cursor:]
            field.cursor -= 1
            field._changed()
        return field.text

    def move(self, delta: int) -> int:
        """Move the caret, clamped to the ends."""
        self.field.cursor = max(0, min(self.field.cursor + int(delta), len(self.field.text)))
        return self.field.cursor

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption, the box, the contents and the caret."""
        left = x
        box_w = w
        if self.label:
            label_w = min(p.text_width(self.label) + 8.0, w * 0.5)
            p.text(x, y, label_w, h, ALIGN_VCENTER | ALIGN_LEFT, self.label, _TEXT)
            left = x + label_w
            box_w = max(w - label_w, 1.0)
        p.stroke_rect(left, y, box_w, h, _BORDER, _TRACK_BG)
        shown = self.field.text or self.field.placeholder
        colour = _TEXT if self.field.text else _DIM
        p.push_clip(left, y, box_w, h)
        p.text(left + 4.0, y, max(box_w - 8.0, 1.0), h,
               ALIGN_VCENTER | ALIGN_LEFT, shown, colour)
        caret_x = left + 4.0 + p.text_width(self.field.text[: self.field.cursor])
        p.fill_rect(caret_x, y + h * 0.15, max(1.0, h * 0.08), h * 0.7, _GOLD)
        p.pop_clip()

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process mouse press. Returns whether the press landed in the field."""
        return box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h
