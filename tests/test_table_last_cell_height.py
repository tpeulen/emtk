"""``end_table`` leaves the cursor below the last row's tallest cell, whichever column it is in."""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter


def _after_table(last_cell_lines: int) -> tuple[float, float]:
    """Draw a two-row table whose last cell holds *last_cell_lines* lines; ``(table_end_y, line_h)``."""
    io, out = emtk.IO(), {}
    for _ in range(2):
        painter = RecordingPainter()
        with im.frame(painter, (0.0, 0.0, 400.0, 300.0), io=io):
            im.begin("w")
            if im.begin_table("t", 2):
                for row in range(2):
                    im.table_next_row()
                    im.table_next_column()
                    im.text("a")
                    im.table_next_column()
                    lines = last_cell_lines if row == 1 else 1
                    for k in range(lines):
                        im.text(f"line {k}")
                im.end_table()
            out["y"] = im.get_cursor_screen_pos()[1]
            out["h"] = im.get_text_line_height()
            im.end()
    return out["y"], out["h"]


def test_the_last_cell_of_the_last_row_sets_the_tables_height():
    one, line_h = _after_table(1)
    three, _ = _after_table(3)
    assert three - one >= 2 * line_h - 0.5
