"""Child scroll ranges include the final fractional item without growing."""

from __future__ import annotations

from math import ceil

import emtk
import pytest
from emtk.layout import Layout
from emtk.testing import RecordingPainter

ROW_HEIGHT = 16.796875
BOX = (0.0, 20.0, 220.0, 100.0)
KEY = ("__child__", "fractional")


def _frame(storage, wheel=0.0):
    """Draw finite fractional-height rows through a real scrolling child."""
    painter = RecordingPainter()
    with emtk.frame(painter, (0, 0, 240, 180), storage=storage) as ctx:
        ctx.io.mouse_pos = (40, 40)
        ctx.io.mouse_wheel = wheel
        ctx.begin_child(BOX, child_id="fractional")
        rows = []
        for index in range(12):
            row = ctx.layout.row(ROW_HEIGHT)
            rows.append(row)
            painter.text(*row, 0, f"row {index}", (255, 255, 255, 255))
        ctx.end_child()
    return rows, dict(storage[KEY]), painter


def test_fractional_item_extent_preserves_bottom_without_trailing_spacing():
    """Measuring a row must retain its actual bottom while snapping the cursor."""
    layout = Layout(RecordingPainter(), 0, 20, 220, 100)
    row = layout.row(ROW_HEIGHT)
    assert layout.cursor[1] == int(layout.cursor[1])
    assert layout.content_height() == ceil(row[1] + row[3]) - 20


def test_fractional_row_pitch_does_not_change_above_screen_origin():
    """Scrolling a fractional row above zero must not add a pixel per row."""
    positive = Layout(RecordingPainter(), 0, 20, 220, 100)
    negative = Layout(RecordingPainter(), 0, -200, 220, 100)
    positive_rows = [positive.row(ROW_HEIGHT) for _ in range(12)]
    negative_rows = [negative.row(ROW_HEIGHT) for _ in range(12)]
    assert [row[1] - 20 for row in positive_rows] == [row[1] + 200 for row in negative_rows]
    assert all(row[1] == int(row[1]) for row in positive_rows + negative_rows)
    assert positive.content_height() == negative.content_height()


def test_final_fractional_row_fully_visible_at_stable_max_scroll():
    """The last row and its drawn text reach the clip without scroll feedback."""
    storage = {}
    _, first, _ = _frame(storage)
    _frame(storage)
    frames = [_frame(storage, wheel=-20) for _ in range(20)]
    rows, last, painter = _frame(storage)
    assert rows[-1][1] >= BOX[1]
    assert rows[-1][1] + rows[-1][3] <= BOX[1] + BOX[3]
    final_label = painter.texts[-1]
    assert final_label[1] + final_label[3] <= BOX[1] + BOX[3]
    assert last["content_height"] == pytest.approx(first["content_height"])
    assert len({round(state["content_height"], 8) for _, state, _ in frames[3:]}) == 1
    assert len({round(state["scroll_y"], 8) for _, state, _ in frames[3:]}) == 1
