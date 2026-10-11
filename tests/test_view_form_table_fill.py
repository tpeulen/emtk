"""An expanding table leaves exactly the room the rows after it take -- measured, not declared.

The rows under an expanding table (fields, a button row, a status line) are
drawn after it, so the table cannot know their height in the frame it is laid
out. It learns it at the end of the region and keeps it from the next frame on
(:class:`emtk.layout.Fill`); a hand-set ``reserve`` number used to stand in for
that and broke whenever a label stacked under its field or a translation grew.
"""

from __future__ import annotations

import pytest

from emtk import im
from emtk.layout import Fill, Layout
from emtk.testing import MetricPainter
from emtk.view_form import FormState, draw_form


class _Model:
    """Rows for the table, two values and two actions."""

    def __init__(self):
        self.rows = [{"a": i, "b": i * i} for i in range(40)]
        self.amplitude = 1.0
        self.lifetime = 4.0

    def sheet(self):
        return self.rows

    def add(self):
        pass

    def remove(self):
        pass


def _table(source="sheet"):
    return {"type": "custom", "key": "data_table",
            "options": {"source": source, "expand": True, "height": 120,
                        "columns": [{"key": "a", "title": "A"}, {"key": "b", "title": "B"}]}}


_AFTER = [
    {"type": "value", "attr": "amplitude", "kind": "float", "label": "Amplitude of the new component"},
    {"type": "value", "attr": "lifetime", "kind": "float",
     "label": "Fluorescence lifetime of the new component (ns)"},
    {"type": "button_row", "buttons": [
        {"label": "Add component", "action": "add"},
        {"label": "Remove selected", "action": "remove"}]},
]

SPEC = {"sections": [{"type": "panel", "title": "Lifetime spectrum",
                      "sections": [_table(), *_AFTER]}]}


def _frame(spec, model, state, w, h, font_scale=1.0):
    painter = MetricPainter()
    if font_scale != 1.0:
        painter.set_font_scale(font_scale)
    with im.frame(painter, (0, 0, w, h)) as ctx:
        im.begin("form", (0, 0, w, h))
        draw_form(spec, model, state)
        im.end()
    return dict(state.rects), ctx.frame_requested


def _bottom(box):
    return box[1] + box[3]


def _settled(spec, model, state, w, h, font_scale=1.0):
    """Draw until nothing asks for another frame; return the last frame's rects."""
    for _ in range(4):
        rects, again = _frame(spec, model, state, w, h, font_scale)
        if not again:
            return rects
    raise AssertionError("the layout never settled")


@pytest.mark.parametrize("height", [260, 400, 700])
@pytest.mark.parametrize("width", [180, 320, 640])
def test_the_rows_after_an_expanding_table_stay_inside_the_region(width, height):
    model, state = _Model(), FormState()
    rects = _settled(SPEC, model, state, width, height)
    last = max(_bottom(rects["add"]), _bottom(rects["remove"]))
    assert last <= height, (rects, height)
    # ... and the table takes the room, rather than leaving it empty under the buttons.
    assert last >= height - 12, (rects, height)


def test_labels_that_stack_under_their_fields_are_left_room():
    model = _Model()
    wide = _settled(SPEC, model, FormState(), 640, 400)
    narrow = _settled(SPEC, model, FormState(), 180, 400)
    # At 180 px the labels stack: more rows follow the table, so it is shorter.
    assert narrow["sheet"][3] < wide["sheet"][3]
    assert _bottom(narrow["remove"]) <= 400


def test_it_settles_in_one_frame_and_then_does_not_move():
    model, state = _Model(), FormState()
    _frame(SPEC, model, state, 320, 400)             # the first frame guesses
    second, again = _frame(SPEC, model, state, 320, 400)
    assert not again and _bottom(second["remove"]) <= 400
    for _ in range(5):
        rects, again = _frame(SPEC, model, state, 320, 400)
        assert not again and rects == second


def test_a_resize_keeps_the_rows_inside_without_another_frame():
    model, state = _Model(), FormState()
    _settled(SPEC, model, state, 320, 600)
    rects, again = _frame(SPEC, model, state, 320, 300)
    assert _bottom(rects["remove"]) <= 300 and not again


def test_a_resize_that_stacks_the_labels_settles_in_one_frame():
    model, state = _Model(), FormState()
    _settled(SPEC, model, state, 640, 400)
    _frame(SPEC, model, state, 180, 400)             # labels stack: one frame to learn it
    rects, again = _frame(SPEC, model, state, 180, 400)
    assert _bottom(rects["remove"]) <= 400 and not again


def test_at_twice_the_text_size():
    model, state = _Model(), FormState()
    rects = _settled(SPEC, model, state, 320, 500, font_scale=2.0)
    assert _bottom(rects["remove"]) <= 500
    assert _bottom(rects["remove"]) >= 500 - 24


def test_a_table_in_a_tab_leaves_room_for_the_rows_after_the_tab_bar():
    spec = {"sections": [
        {"type": "tabs", "sections": [
            {"type": "panel", "title": "Rows", "sections": [_table(), _AFTER[2]]}]},
        {"type": "value", "attr": "amplitude", "kind": "float", "label": "After the tabs"},
    ]}
    model, state = _Model(), FormState()
    rects = _settled(spec, model, state, 320, 400)
    assert _bottom(rects["remove"]) <= _bottom(rects["amplitude"]) <= 400


def test_two_expanding_tables_share_the_room():
    spec = {"sections": [_table("sheet"), {"type": "button_row", "buttons": [
        {"label": "Add component", "action": "add"}]}, _table("other"), _AFTER[2]]}
    model, state = _Model(), FormState()
    model.other = model.sheet
    rects = _settled(spec, model, state, 320, 500)
    assert abs(rects["sheet"][3] - rects["other"][3]) <= 1
    assert _bottom(rects["remove"]) <= 500


def test_a_table_inside_a_child_region_is_bounded_by_the_child():
    model, state = _Model(), FormState()
    rects = {}
    for _ in range(3):
        with im.frame(MetricPainter(), (0, 0, 320, 500)):
            im.begin("form", (0, 0, 320, 500))
            im.begin_child("body", (320, 300))
            draw_form(SPEC, model, state)
            im.end_child()
            im.text("status line")
            im.end()
        rects = dict(state.rects)
    assert _bottom(rects["remove"]) <= 300


def test_fill_height_before_and_after_it_is_measured():
    fill = Fill()
    assert fill.height(500, 120, 60) == 120         # a first guess, capped by the room
    assert fill.height(80, 120, 60) == 80
    fill.tail, fill.later = 100.0, 0
    assert fill.height(500, 120, 60) == 400
    assert fill.height(120, 120, 60) == 60          # never below the minimum
    fill.later = 1
    assert fill.height(500, 120, 60) == 200         # shared with the fill after it


class _P:
    def line_height(self):
        return 12.0


def test_settle_measures_from_the_fill_to_the_end_of_the_region():
    layout = Layout(_P(), 0, 0, 200, 300)
    fill = Fill()
    box = layout.row(height=100)
    layout.add_fill(fill, box)
    layout.row()                                    # a 16 px row after it
    assert layout.settle_fills() is True
    assert fill.tail == 3 + 16                      # the gap and the row
    assert layout.settle_fills() is False           # nothing left to settle
