"""A hex viewer and editor: the port of ``imgui_club``'s memory editor.

Where it comes from
-------------------
``junk/imgui_club/imgui_memory_editor`` -- Omar Cornut's mini memory editor for
Dear ImGui, MIT licensed. The layout arithmetic below is transcribed from its
``CalcSizes``, and the cell rules (grey zeroes, HexII, the mid-column gap, the
one-byte-wide edit box) from its ``DrawContents``. Its own header says the code
"assumes a mono-space font for simplicity", which is the same assumption
:mod:`.text_editor` makes and which the chrome satisfies.

Why cmtk has one at all
-------------------------
The renderer's cost is measured in **bytes**: a scene is vertex buffers,
instance buffers, a chrome texture and a glyph atlas, and the difference
between a fast frame and a slow one is usually how many of those exist and how
large they are. The question "what is actually in that buffer" was, until now,
answerable only by adding a print statement and re-running -- and for a GPU
buffer, not even then.

So this control draws any :class:`MemorySource`: a host array (RAM) or a
mapped-back GPU buffer (VRAM). Enumerating them is the application's job;
this file only knows how to draw one.

What is deliberately not ported
-------------------------------
The right-click options popup and the standalone ``DrawWindow``. Both are
window management, which in this package belongs to the host: the chrome's
menus are :mod:`.menus`, and a control that opened its own window would be the
only one that did. Every option the popup sets is a public attribute here, so
a host draws whatever settings UI it wants against them -- which is what the
AutoForm section and the cmtk dock both do.
"""
from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Colour, Painter
from ..style import BORDER, FRAME_BG, TEXT, TEXT_DISABLED, clamp, hit
from .basic import ScrollBar

__all__ = [
    "MemorySource",
    "BufferSource",
    "PREVIEW_TYPES",
    "MemoryEditor",
]


@runtime_checkable
class MemorySource(Protocol):
    """A block of bytes the editor can show, wherever it lives.

    The indirection is the whole point: RAM is a buffer and can be sliced;
    VRAM is not addressable from Python at all and has to be *copied back*
    through the graphics API, one range at a time. Both answer the same three
    questions, so the control asks those and nothing else.
    """

    #: What to call it in a picker.
    name: str

    def size(self) -> int:
        """Total number of bytes."""
        ...

    def read(self, offset: int, length: int) -> bytes:
        """Return up to *length* bytes starting at *offset*."""
        ...


class BufferSource:
    """A :class:`MemorySource` over anything that supports the buffer protocol.

    Parameters
    ----------
    data : bytes, bytearray, memoryview or numpy.ndarray
        The bytes. A NumPy array is taken as its raw memory, which is the
        useful reading -- a vertex buffer *is* its bytes, and reinterpreting it
        as floats is what the data preview is for.
    name : str, optional
        Shown in a picker.
    base_address : int, optional
        Added to every displayed offset, so an address column can show where
        the block actually lives rather than starting at zero.
    writable : bool, optional
        Whether :meth:`write` is allowed. Defaults to whether the underlying
        object is mutable -- a ``bytes`` is not.
    """

    def __init__(
        self,
        data,
        name: str = "buffer",
        base_address: int = 0,
        writable: bool | None = None,
    ) -> None:
        view = memoryview(data)
        # A multi-dimensional or non-contiguous array has no single byte
        # ordering to show, so it is flattened here rather than drawn wrong.
        self._view = view.cast("B") if view.ndim == 1 else view.toreadonly().cast("B")
        self.name = str(name)
        self.base_address = int(base_address)
        self.writable = (not self._view.readonly) if writable is None else bool(writable)

    def size(self) -> int:
        """Total number of bytes."""
        return len(self._view)

    def read(self, offset: int, length: int) -> bytes:
        """Return the bytes in ``[offset, offset + length)``, clipped."""
        offset = max(int(offset), 0)
        return bytes(self._view[offset: offset + max(int(length), 0)])

    def write(self, offset: int, value: int) -> bool:
        """Write one byte. Returns whether it was allowed."""
        if not self.writable or not 0 <= offset < len(self._view):
            return False
        self._view[offset] = int(value) & 0xFF
        return True


#: The preview types, as ``(label, struct code, size)``. The reference's
#: ``ImGuiDataType`` list, minus the ones ``struct`` has no code for.
PREVIEW_TYPES: tuple[tuple[str, str, int], ...] = (
    ("Int8", "b", 1),
    ("Uint8", "B", 1),
    ("Int16", "h", 2),
    ("Uint16", "H", 2),
    ("Int32", "i", 4),
    ("Uint32", "I", 4),
    ("Int64", "q", 8),
    ("Uint64", "Q", 8),
    ("Float", "f", 4),
    ("Double", "d", 8),
)


class MemoryEditor:
    """A scrollable hex dump with an ASCII pane, edit cells and a data preview.

    Follows the package contract: :meth:`draw` into a box, :meth:`press` with
    the presses that land in it, :meth:`key` with the keys.

    Parameters
    ----------
    source : MemorySource, optional
        What to show. May be set later, or swapped, with :meth:`set_source`.
    columns : int, optional
        Bytes per row.
    read_only : bool, optional
        A read-only editor still selects and previews -- the reference made
        that change deliberately in v0.54 and it is what makes this usable on a
        GPU buffer, which cannot be written back through this path at all.
    """

    def __init__(
        self,
        source: MemorySource | None = None,
        columns: int = 16,
        read_only: bool = True,
    ) -> None:
        self.source = source
        self.columns = max(int(columns), 1)
        self.read_only = bool(read_only)

        # -- options, one per reference field ---------------------------- #
        self.show_ascii = True
        self.show_hex_ii = False
        self.show_data_preview = True
        self.grey_out_zeroes = True
        self.upper_case_hex = True
        #: Extra gap every N columns; 0 disables it. Eight is the reference's
        #: default and is what makes a 16-wide dump readable at a glance.
        self.mid_columns_count = 8
        #: 0 means "as many digits as the highest address needs".
        self.address_digits = 0
        self.highlight_colour: Colour = (255, 255, 255, 50)

        # -- state -------------------------------------------------------- #
        self.first_visible_row = 0
        self.visible_rows = 1
        #: The vertical scrollbar, drawn when the dump is taller than the box.
        self.vbar = ScrollBar()
        #: The byte the preview reads from, and the byte being typed into.
        self.preview_address = -1
        self.editing_address = -1
        self.hovered_address = -1
        self.highlight_min = -1
        self.highlight_max = -1
        self.preview_type = 4  # Int32, the reference's default
        self.preview_big_endian = False
        self._edit_digits = ""
        #: Optional per-byte background, for a host that wants to mark ranges.
        self.background_of: Callable[[int], Colour | None] | None = None

        self._glyph_w = 8.0
        self._line_h = 14.0
        self._body_y = 0.0
        self._hex_x = 0.0
        self._ascii_x = 0.0
        self._hex_cell_w = 20.0
        self._mid_gap = 5.0
        self._digits = 4

    # -- source --------------------------------------------------------- #
    def set_source(self, source: MemorySource | None) -> None:
        """Show a different block, resetting everything that indexed the old one."""
        self.source = source
        self.first_visible_row = 0
        self.preview_address = -1
        self.editing_address = -1
        self.hovered_address = -1
        self._edit_digits = ""

    @property
    def size(self) -> int:
        """Bytes in the current source, or zero when there is none."""
        return int(self.source.size()) if self.source is not None else 0

    @property
    def base_address(self) -> int:
        """The source's base address, if it has one."""
        return int(getattr(self.source, "base_address", 0) or 0)

    @property
    def row_count(self) -> int:
        """Number of rows the whole block occupies."""
        return (self.size + self.columns - 1) // self.columns

    def goto(self, address: int, highlight_to: int | None = None) -> None:
        """Scroll to an address and optionally highlight a range from it."""
        address = int(clamp(int(address), 0, max(self.size - 1, 0)))
        self.first_visible_row = max(
            0, address // self.columns - max(self.visible_rows // 2, 0)
        )
        self.preview_address = address
        self.highlight_min = address
        self.highlight_max = address if highlight_to is None else int(highlight_to)

    # -- geometry ------------------------------------------------------- #
    def _calc_sizes(self, p: Painter) -> None:
        """The reference's ``CalcSizes``, in the chrome's units.

        Kept as its own step because the reference's whole layout -- where the
        ASCII pane starts, how wide the ideal window is -- falls out of five
        numbers, and computing them twice with a typo in one is the classic way
        the hex column and the ASCII column stop agreeing about which byte is
        which.
        """
        self._glyph_w = max(p.text_width("F"), 1.0) + 1.0
        self._line_h = max(p.line_height(), 1.0)
        self._hex_cell_w = float(int(self._glyph_w * 2.5))
        self._mid_gap = float(int(self._hex_cell_w * 0.25))
        digits = self.address_digits
        if digits == 0:
            digits = 0
            highest = self.base_address + max(self.size - 1, 0)
            while highest > 0:
                digits += 1
                highest >>= 4
        self._digits = max(digits, 1)

    def ideal_width(self) -> float:
        """How wide the control wants to be, for a host that can grant it."""
        hex_min = (self._digits + 2) * self._glyph_w
        hex_max = hex_min + self._hex_cell_w * self.columns
        if not self.show_ascii:
            return hex_max + self._glyph_w
        gaps = 0.0
        if self.mid_columns_count > 0:
            gaps = (
                (self.columns + self.mid_columns_count - 1) // self.mid_columns_count
            ) * self._mid_gap
        return hex_max + self._glyph_w + gaps + self.columns * self._glyph_w + self._glyph_w

    def _byte_x(self, column: int) -> float:
        """Left edge of a hex cell, including the mid-column gaps before it."""
        x = self._hex_x + self._hex_cell_w * column
        if self.mid_columns_count > 0:
            x += (column // self.mid_columns_count) * self._mid_gap
        return x

    # -- drawing -------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the dump.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        self._calc_sizes(p)
        p.fill_rect(x, y, w, h, FRAME_BG)
        p.push_clip(x, y, w, h)

        footer = (self._line_h * 4.0) if self.show_data_preview else 0.0
        body_h = max(h - footer, self._line_h)
        self._body_y = y
        self.visible_rows = max(int(body_h / self._line_h), 1)
        self.first_visible_row = int(
            clamp(self.first_visible_row, 0, max(self.row_count - self.visible_rows, 0))
        )
        # A scrollbar down the right when the dump is taller than the box.
        self.vbar.top = self.first_visible_row
        self.vbar.clamp(self.row_count, self.visible_rows)
        if self.vbar.needed():
            self.vbar.draw(p, x + w - self.vbar.width, y, body_h)
        self._hex_x = x + (self._digits + 2) * self._glyph_w
        gaps = 0.0
        if self.mid_columns_count > 0:
            gaps = (
                (self.columns + self.mid_columns_count - 1) // self.mid_columns_count
            ) * self._mid_gap
        self._ascii_x = (
            self._hex_x + self._hex_cell_w * self.columns + self._glyph_w + gaps
        )

        if self.source is None:
            p.text(x, y, w, self._line_h, ALIGN_LEFT | ALIGN_VCENTER,
                   "no memory source", TEXT_DISABLED)
            p.pop_clip()
            p.stroke_rect(x, y, w, h, BORDER)
            return

        if self.show_ascii:
            p.fill_rect(self._ascii_x - self._glyph_w, y, 1.0, body_h, BORDER)

        preview_size = PREVIEW_TYPES[self.preview_type][2] if self.show_data_preview else 0
        fmt = "{:02X}" if self.upper_case_hex else "{:02x}"

        for row in range(self.visible_rows):
            number = self.first_visible_row + row
            if number >= self.row_count:
                break
            address = number * self.columns
            row_y = y + row * self._line_h
            chunk = self.source.read(address, self.columns)

            p.text(
                x,
                row_y,
                (self._digits + 1) * self._glyph_w,
                self._line_h,
                ALIGN_RIGHT | ALIGN_VCENTER,
                self._format_address(self.base_address + address),
                TEXT_DISABLED,
            )
            for column, value in enumerate(chunk):
                here = address + column
                cell_x = self._byte_x(column)
                self._draw_background(p, here, column, cell_x, row_y, preview_size)
                if here == self.editing_address and not self.read_only:
                    p.stroke_rect(cell_x - 1.0, row_y, self._glyph_w * 2.0 + 2.0,
                                  self._line_h, TEXT, (40, 60, 90))
                    shown = self._edit_digits or fmt.format(value)
                else:
                    shown = fmt.format(value)
                colour = TEXT
                if self.show_hex_ii:
                    shown, colour = self._hex_ii(value, fmt)
                elif value == 0 and self.grey_out_zeroes:
                    colour = TEXT_DISABLED
                p.text(cell_x, row_y, self._glyph_w * 2.5, self._line_h,
                       ALIGN_LEFT | ALIGN_VCENTER, shown, colour)

            if self.show_ascii:
                p.text(
                    self._ascii_x,
                    row_y,
                    self.columns * self._glyph_w,
                    self._line_h,
                    ALIGN_LEFT | ALIGN_VCENTER,
                    "".join(
                        chr(one) if 32 <= one < 127 else "." for one in chunk
                    ),
                    TEXT,
                )

        if self.show_data_preview:
            self._draw_preview(p, x, y + body_h, w, footer)
        p.pop_clip()
        p.stroke_rect(x, y, w, h, BORDER)

    def _format_address(self, address: int) -> str:
        """The address column's text for one row."""
        spec = f"0{self._digits}X" if self.upper_case_hex else f"0{self._digits}x"
        return format(address, spec) + ":"

    def _hex_ii(self, value: int, fmt: str) -> tuple[str, Colour]:
        """HexII: hide zeroes, show printable bytes as ``.X``.

        The reference's own compression, and it is genuinely better for looking
        at a mostly-empty buffer: a screen of ``00`` tells you nothing, a screen
        of blanks with a few values in it tells you where the data is.
        """
        if 32 <= value < 128:
            return f".{chr(value)}", TEXT
        if value == 0:
            return "  ", TEXT_DISABLED
        if value == 0xFF and self.grey_out_zeroes:
            return "##", TEXT_DISABLED
        return fmt.format(value), TEXT

    def _draw_background(
        self,
        p: Painter,
        address: int,
        column: int,
        cell_x: float,
        row_y: float,
        preview_size: int,
    ) -> None:
        """Fill a cell's background, from the highlight range or a host callback."""
        highlighted = (
            self.highlight_min >= 0 and self.highlight_min <= address <= self.highlight_max
        ) or (
            0 <= self.preview_address <= address < self.preview_address + preview_size
        )
        colour: Colour | None = self.highlight_colour if highlighted else None
        if colour is None and self.background_of is not None:
            colour = self.background_of(address)
        if colour is None:
            return
        width = self._glyph_w * 2.0
        if column + 1 == self.columns:
            width = self._hex_cell_w
        p.fill_rect(cell_x, row_y, width, self._line_h, colour)

    def _draw_preview(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Draw the footer: the type, the endianness, and the decoded value."""
        label, code, size = PREVIEW_TYPES[self.preview_type]
        p.fill_rect(x, y, w, h, (0, 0, 0, 40))
        rows = [
            f"Preview  {label}  {'big' if self.preview_big_endian else 'little'}-endian",
            f"Dec  {self._preview_text(code, size, 'dec')}",
            f"Hex  {self._preview_text(code, size, 'hex')}",
            f"Bin  {self._preview_text(code, size, 'bin')}",
        ]
        for index, text in enumerate(rows):
            p.text(x + self._glyph_w, y + index * self._line_h, w, self._line_h,
                   ALIGN_LEFT | ALIGN_VCENTER, text,
                   TEXT if index else TEXT_DISABLED)

    def _preview_text(self, code: str, size: int, form: str) -> str:
        """Decode the bytes at :attr:`preview_address` in one representation."""
        if self.source is None or not 0 <= self.preview_address < self.size:
            return "-"
        raw = self.source.read(self.preview_address, size)
        if len(raw) < size:
            return "-"
        value = struct.unpack((">" if self.preview_big_endian else "<") + code, raw)[0]
        if form == "dec":
            return f"{value:.9g}" if isinstance(value, float) else str(value)
        # A float has no meaningful hex or binary *value*, so its raw bytes are
        # shown instead -- which is the question somebody looking at a float in
        # a hex editor is actually asking.
        if isinstance(value, float):
            blob = raw
        else:
            blob = value.to_bytes(size, "big", signed=code.islower())
        if form == "hex":
            return " ".join(f"{one:02X}" for one in blob)
        return " ".join(format(one, "08b") for one in blob)

    # -- interaction ---------------------------------------------------- #
    def address_at(self, px: float, py: float) -> int:
        """Which byte a point is over, or ``-1``.

        Both panes answer: a press in the ASCII column selects the same byte as
        a press on its hex cell, which is what makes the two panes feel like
        one view of one buffer.
        """
        row = int((py - self._body_y) // max(self._line_h, 1e-6))
        if not 0 <= row < self.visible_rows:
            return -1
        base = (self.first_visible_row + row) * self.columns
        if self.show_ascii and px >= self._ascii_x:
            column = int((px - self._ascii_x) / max(self._glyph_w, 1e-6))
        elif px >= self._hex_x:
            column = int((px - self._hex_x) / max(self._hex_cell_w + self._mid_gap
                                                 / max(self.mid_columns_count, 1), 1e-6))
        else:
            return -1
        if not 0 <= column < self.columns:
            return -1
        address = base + column
        return address if address < self.size else -1

    def hover(self, px: float, py: float, x: float, y: float, w: float, h: float) -> int:
        """Record and return the hovered address, or ``-1``."""
        self.hovered_address = self.address_at(px, py) if hit(px, py, x, y, w, h) else -1
        return self.hovered_address

    def press(
        self, px: float, py: float, x: float, y: float, w: float, h: float
    ) -> int | None:
        """Select the byte under the pointer; returns its address or ``None``."""
        if not hit(px, py, x, y, w, h):
            return None
        if self.vbar.press(px, py):
            self.first_visible_row = self.vbar.top
            return None
        address = self.address_at(px, py)
        if address < 0:
            return None
        self.preview_address = address
        self.editing_address = -1 if self.read_only else address
        self._edit_digits = ""
        return address

    def drag(self, px: float, py: float, x: float = 0.0, y: float = 0.0, w: float = 0.0, h: float = 0.0) -> None:
        """Drag the scrollbar's thumb (the only thing this control drags)."""
        if self.vbar.held:
            self.vbar.drag_to(py)
            self.first_visible_row = self.vbar.top

    def release(self) -> None:
        """Let the scrollbar's thumb go."""
        self.vbar.held = False

    def scroll(self, rows: int) -> int:
        """Scroll by *rows*; returns the new first visible row."""
        highest = max(self.row_count - self.visible_rows, 0)
        self.first_visible_row = int(clamp(self.first_visible_row + int(rows), 0, highest))
        return self.first_visible_row

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key: arrows move the selection, hex digits type a byte.

        Two typed hex digits commit the byte and step forward, which is the
        reference's behaviour and the reason the edit cell holds a *string* of
        digits rather than a value: after one digit the cell is legitimately
        half-typed, and rendering it as a number would show the wrong byte.
        """
        from ..keys import KEY_DOWN, KEY_ESCAPE, KEY_LEFT, KEY_RIGHT, KEY_UP

        if self.source is None or self.preview_address < 0:
            return False
        step = {KEY_LEFT: -1, KEY_RIGHT: 1, KEY_UP: -self.columns, KEY_DOWN: self.columns}
        if key in step:
            self.preview_address = int(
                clamp(self.preview_address + step[key], 0, max(self.size - 1, 0))
            )
            if not self.read_only:
                self.editing_address = self.preview_address
            self._edit_digits = ""
            self._follow_selection()
            return True
        if key == KEY_ESCAPE:
            self.editing_address = -1
            self._edit_digits = ""
            return True

        if self.read_only or self.editing_address < 0:
            return False
        for char in str(text):
            if char not in "0123456789abcdefABCDEF":
                continue
            self._edit_digits += char.upper()
            if len(self._edit_digits) == 2:
                self._commit_byte()
        return True

    def _commit_byte(self) -> None:
        """Write the two typed digits and move to the next byte."""
        write = getattr(self.source, "write", None)
        if callable(write):
            write(self.editing_address, int(self._edit_digits, 16))
        self._edit_digits = ""
        self.editing_address = int(
            clamp(self.editing_address + 1, 0, max(self.size - 1, 0))
        )
        self.preview_address = self.editing_address
        self._follow_selection()

    def _follow_selection(self) -> None:
        """Scroll so the selected byte is on screen."""
        row = self.preview_address // self.columns
        if row < self.first_visible_row:
            self.first_visible_row = row
        elif row >= self.first_visible_row + self.visible_rows:
            self.first_visible_row = row - self.visible_rows + 1
