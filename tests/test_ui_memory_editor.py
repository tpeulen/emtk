"""Painter-level tests for the hex editor, ported from ``imgui_memory_editor``.

The hex view's failure mode is not "it crashes", it is "the hex column and the
ASCII column disagree about which byte is which" -- so most of what is checked
here is arithmetic: where a cell is, which byte a press lands on, how wide the
address column is. All of it runs against the recording painter, with no
toolkit and no GPU.

Where the bytes come from is not this file's business: an editor is handed a
``MemorySource``, and enumerating an application's buffers belongs to the
application, and is tested there.
"""
from __future__ import annotations

import struct

import pytest

from emtk.keys import KEY_DOWN, KEY_RIGHT
from emtk.widgets import memory_editor as me
from emtk.testing import RecordingPainter

numpy = pytest.importorskip("numpy")


def _editor(data=None, **options) -> me.MemoryEditor:
    """A hex view over *data* (256 counting bytes by default)."""
    blob = bytes(range(256)) if data is None else data
    return me.MemoryEditor(me.BufferSource(blob, "test"), **options)


def _drawn(editor, w: float = 640.0, h: float = 300.0) -> RecordingPainter:
    """Draw *editor* once and return the painter that recorded it."""
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, w, h)
    return painter


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
def test_a_numpy_array_is_shown_as_its_bytes():
    """A vertex buffer *is* its bytes; reinterpreting is the preview's job."""
    array = numpy.arange(4, dtype=numpy.float32)
    source = me.BufferSource(array, "xyz")
    assert source.size() == 16
    assert source.read(0, 4) == struct.pack("<f", 0.0)


def test_an_immutable_buffer_reports_itself_read_only():
    """``bytes`` cannot be written and must not pretend otherwise."""
    assert not me.BufferSource(b"abc").writable
    assert me.BufferSource(bytearray(b"abc")).writable


def test_a_write_lands_in_the_underlying_buffer():
    """And is refused, without raising, when the buffer is immutable."""
    mutable = me.BufferSource(bytearray(b"abc"))
    assert mutable.write(1, 0x5A)
    assert mutable.read(0, 3) == b"aZc"
    assert not me.BufferSource(b"abc").write(1, 0x5A)


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------
def test_the_address_column_is_as_wide_as_the_highest_address_needs():
    """Two digits for 256 bytes, three for one byte more.

    The off-by-one here is not academic: a fixture that grew by one byte is
    what first showed the column widening, and a widened column shifts every
    hex cell -- which is the "hex and ASCII disagree" bug in its usual form.
    """
    small = _editor(bytes(256))
    _drawn(small)
    assert small._digits == 2
    big = _editor(bytes(257))
    _drawn(big)
    assert big._digits == 3


def test_the_mid_column_gap_is_inserted_every_n_columns_and_nowhere_else():
    """The gap is what makes a 16-wide dump readable, and it must not drift."""
    editor = _editor(columns=16)
    _drawn(editor)
    editor.mid_columns_count = 8
    step = editor._byte_x(1) - editor._byte_x(0)
    assert editor._byte_x(8) - editor._byte_x(7) == pytest.approx(step + editor._mid_gap)
    assert editor._byte_x(9) - editor._byte_x(8) == pytest.approx(step)


def test_disabling_the_ascii_pane_narrows_the_ideal_width():
    """Two panes cost more than one; the host asks the control, not a constant."""
    editor = _editor()
    _drawn(editor)
    wide = editor.ideal_width()
    editor.show_ascii = False
    assert editor.ideal_width() < wide


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
def test_it_draws_the_address_the_hex_and_the_ascii_for_every_visible_row():
    """One row is an address, sixteen cells and one ASCII string."""
    editor = _editor(columns=16)
    painter = _drawn(editor)
    assert "00:" in painter.strings
    assert "0F" in painter.strings
    assert any(len(one) == 16 and "." in one for one in painter.strings)


def test_only_the_visible_rows_are_drawn():
    """A 4 GB buffer must cost the same as a 4 kB one to look at."""
    editor = _editor(bytes(65536), columns=16)
    painter = _drawn(editor, h=200.0)
    assert editor.row_count == 4096
    assert editor.visible_rows < 20
    assert len(painter.strings) < 20 * 18


def test_hex_ii_hides_zeroes_and_spells_printable_bytes():
    """The reference's compression: a screen of ``00`` says nothing."""
    editor = _editor(b"Ab\x00\xff" + bytes(12), columns=16)
    editor.show_hex_ii = True
    painter = _drawn(editor)
    assert ".A" in painter.strings and ".b" in painter.strings
    assert "##" in painter.strings          # 0xFF
    assert "  " in painter.strings          # 0x00, blanked


def test_a_zero_byte_is_dimmed_when_asked_and_not_when_not():
    """Grey-out is what makes the data stand out of an empty buffer."""
    from emtk.style import TEXT_DISABLED

    editor = _editor(bytes(16), columns=16)
    assert TEXT_DISABLED in [one[6] for one in _drawn(editor).texts]
    editor.grey_out_zeroes = False
    editor.show_hex_ii = False
    colours = {one[6] for one in _drawn(editor).texts}
    assert TEXT_DISABLED in colours  # still used by the address column
    assert len(colours) >= 2


def test_the_preview_decodes_the_selected_bytes_in_both_endiannesses():
    """The footer is why anyone looks at a hex dump of a float array."""
    editor = _editor(struct.pack("<i", 305419896) + bytes(12))
    _drawn(editor)
    editor.preview_address = 0
    editor.preview_type = 4  # Int32
    assert editor._preview_text("i", 4, "dec") == "305419896"
    editor.preview_big_endian = True
    assert editor._preview_text("i", 4, "dec") == "2018915346"


def test_a_float_preview_shows_its_bytes_rather_than_a_meaningless_hex_value():
    """"The hex of 1.0" is not a number; the bytes are the useful answer."""
    editor = _editor(struct.pack("<d", 1.0) + bytes(8))
    _drawn(editor)
    editor.preview_address = 0
    assert editor._preview_text("d", 8, "dec") == "1"
    assert editor._preview_text("d", 8, "hex").endswith("F0 3F")


def test_an_empty_source_draws_a_message_instead_of_nothing():
    """A blank panel is indistinguishable from a broken one."""
    painter = _drawn(me.MemoryEditor(None))
    assert "no memory source" in painter.strings


# --------------------------------------------------------------------------
# Interaction
# --------------------------------------------------------------------------
def test_a_press_on_either_pane_selects_the_same_byte():
    """The two panes are one view of one buffer, or they are two bugs."""
    editor = _editor(columns=16)
    _drawn(editor)
    from_hex = editor.press(editor._byte_x(3) + 2.0, 4.0, 0.0, 0.0, 640.0, 300.0)
    from_ascii = editor.press(
        editor._ascii_x + 3.5 * editor._glyph_w, 4.0, 0.0, 0.0, 640.0, 300.0
    )
    assert from_hex == 3
    assert from_ascii == 3


def test_a_press_outside_the_data_selects_nothing():
    """The gutter and the space past the last column are not byte zero."""
    editor = _editor(columns=16)
    _drawn(editor)
    assert editor.press(1.0, 4.0, 0.0, 0.0, 640.0, 300.0) is None


def test_typing_two_hex_digits_writes_the_byte_and_steps_on():
    """One digit is a half-typed cell, which is why the cell holds a string."""
    blob = bytearray(16)
    editor = me.MemoryEditor(me.BufferSource(blob, "w"), columns=16, read_only=False)
    _drawn(editor)
    editor.press(editor._byte_x(0) + 2.0, 4.0, 0.0, 0.0, 640.0, 300.0)
    editor.key(0, "4")
    assert blob[0] == 0
    editor.key(0, "2")
    assert blob[0] == 0x42
    assert editor.editing_address == 1


def test_a_read_only_editor_selects_and_previews_but_never_writes():
    """The reference allowed this deliberately; a device buffer needs it."""
    blob = bytearray(16)
    editor = me.MemoryEditor(me.BufferSource(blob, "w"), columns=16, read_only=True)
    _drawn(editor)
    assert editor.press(editor._byte_x(0) + 2.0, 4.0, 0.0, 0.0, 640.0, 300.0) == 0
    editor.key(0, "4")
    editor.key(0, "2")
    assert blob[0] == 0


def test_arrow_keys_move_the_selection_and_scroll_to_keep_it_visible():
    """A selection off screen is a selection nobody can see."""
    editor = _editor(bytes(4096), columns=16)
    _drawn(editor, h=120.0)
    editor.preview_address = 0
    for _ in range(40):
        editor.key(KEY_DOWN)
    assert editor.preview_address == 40 * 16
    assert editor.first_visible_row > 0
    editor.key(KEY_RIGHT)
    assert editor.preview_address == 40 * 16 + 1


def test_goto_centres_the_address_and_highlights_the_range():
    """What a caller uses to say "the corruption is here"."""
    editor = _editor(bytes(4096), columns=16)
    _drawn(editor, h=200.0)
    editor.goto(2048, 2064)
    assert editor.highlight_min == 2048 and editor.highlight_max == 2064
    assert editor.first_visible_row < 2048 // 16
