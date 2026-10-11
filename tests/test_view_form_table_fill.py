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


# ---- stretch weights: the room shared among the items that matter ------------------------------


def _stretch_spec(w1, w2, status=True):
    first, second = _table("sheet"), _table("other")
    first["options"].update(stretch=w1, expand=False)
    second["options"].update(stretch=w2, expand=False)
    sections = [first, second, {"type": "choice", "attr": "model", "label": "Model",
                                 "options": ["a", "b"]}, _AFTER[2]]
    if status:
        sections.append({"type": "label", "text": "Ready"})
    return {"sections": sections}


class _Two(_Model):
    model = "a"

    def other(self):
        return self.rows


@pytest.mark.parametrize("weights", [(1, 1), (1, 2), (3, 1)])
@pytest.mark.parametrize("size", [(320, 500), (800, 600), (1100, 720)])
def test_stretch_weights_share_the_room(weights, size):
    model, state = _Two(), FormState()
    rects = _settled(_stretch_spec(*weights), model, state, *size)
    a, b = rects["sheet"][3], rects["other"][3]
    assert abs(a / b - weights[0] / weights[1]) < 0.05, (a, b)
    assert _bottom(rects["remove"]) <= size[1]
    # The tables take the room; what is left is the fixed rows (choice, buttons, a status line).
    assert a + b >= 0.6 * size[1]


def test_a_stretching_table_keeps_its_minimum():
    spec = _stretch_spec(1, 1)
    spec["sections"][0]["options"]["min_height"] = 150
    rects = _settled(spec, _Two(), FormState(), 320, 300)
    assert rects["sheet"][3] >= 150


def test_stretch_survives_a_resize_and_twice_the_text_size():
    model, state = _Two(), FormState()
    _settled(_stretch_spec(1, 1), model, state, 800, 600)
    rects = _settled(_stretch_spec(1, 1), model, state, 400, 500, font_scale=2.0)
    assert _bottom(rects["remove"]) <= 500
    assert abs(rects["sheet"][3] - rects["other"][3]) <= 1
    again, more = _frame(_stretch_spec(1, 1), model, state, 400, 500, 2.0)
    assert again == rects and not more


def test_a_hand_drawn_item_stretches_by_weight():
    storage = {}
    boxes = []
    for _ in range(3):
        with im.frame(MetricPainter(), (0, 0, 300, 400), storage=storage) as ctx:
            im.begin("w", (0, 0, 300, 400))
            h1 = im.stretch_height("plot", weight=2, minimum=40)
            im.dummy((300, h1))
            h2 = im.stretch_height("list", weight=1, minimum=40)
            im.dummy((300, h2))
            im.button("OK")
            im.text("Ready")
            last = im.get_item_rect()
            im.end()
        boxes.append((h1, h2, last))
    h1, h2, last = boxes[-1]
    assert abs(h1 - 2 * h2) <= 2 and last[1] + last[3] <= 400 and last[1] + last[3] >= 390
    assert boxes[-1] == boxes[-2]


def test_a_button_row_under_a_stacked_field_leaves_no_blank_line():
    """A column whose label stacks above its field: the unlabelled row after it is not pushed down a line."""

    class M:
        model = "a"

        def model_names(self):
            return ["a", "b"]

        def add(self):
            pass

        def remove(self):
            pass

    spec = {"sections": [
        {"type": "choice", "attr": "model", "label": "Model", "options_source": "model_names"},
        _AFTER[2]]}
    rects = _settled(spec, M(), FormState(), 200, 300)
    field, add, remove = rects["model"], rects["add"], rects["remove"]
    gap = 3.0  # emtk ITEM_SPACING y
    assert add[1] - _bottom(field) <= gap + 1                # the next line, not one further
    assert add[0] == 0.0 and _bottom(remove) <= 300 and remove[0] + remove[2] <= 200
