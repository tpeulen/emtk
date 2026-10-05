"""Cells that name another record: ``display: "link"``, ``activated_cell_call`` and ``background``.

A database admin table shows foreign keys -- a sample's condition, an experiment's
setup. The Qt table drew those cells as links and opened the referenced record on a
double click *of that cell*; ``activated_call`` only says which row was opened, so a
port could not tell the condition cell from the sample cell. A status column is
coloured by value (approved green, rejected red). Recording painter, no window.
"""

from __future__ import annotations

from emtk import style
from emtk.testing import RecordingPainter
from emtk.widgets.data_table import TableBinding


class _Samples:
    def __init__(self):
        self.rows = [
            {"sample_id": "s1", "condition_id": "cond_a", "status": "approved"},
            {"sample_id": "s2", "condition_id": "", "status": "rejected"},
        ]
        self.opened = []
        self.rows_opened = []

    def records(self):
        return self.rows

    def open_cell(self, record, key):
        self.opened.append((record["sample_id"], key))

    def open_row(self, record):
        self.rows_opened.append(record["sample_id"])


SECTION = {
    "type": "custom",
    "key": "data_table",
    "options": {
        "source": "records",
        "row_key": "sample_id",
        "activated_call": "open_row",
        "activated_cell_call": "open_cell",
        "columns": [
            {"key": "sample_id", "title": "Sample", "width": 120},
            {"key": "condition_id", "title": "Condition", "width": 120, "display": "link"},
            {"key": "status", "title": "Status", "width": 120,
             "background": {"approved": "#d6f5dc", "rejected": [255, 220, 220]}},
        ],
    },
}


def _draw(control):
    painter = RecordingPainter()
    control.draw(painter, 0.0, 0.0, 400.0, 200.0)
    return painter


def _cell(control, position, column):
    bx, by, _bw, _bh = control._body_box
    x = bx + sum(control._widths[:column]) + control._widths[column] / 2
    return x, by + control._row_h * (position + 0.5)


def test_a_double_click_names_the_cell_it_landed_on():
    model = _Samples()
    binding = TableBinding(SECTION, model)
    control = binding.control
    _draw(control)
    control.press(*_cell(control, 0, 1), clicks=2)
    assert model.opened[-1] == ("s1", "condition_id")
    control.press(*_cell(control, 0, 0), clicks=2)
    assert model.opened[-1] == ("s1", "sample_id")
    assert model.rows_opened == ["s1", "s1"]  # the row call still comes


def test_a_link_cell_is_drawn_in_the_link_colour_and_underlined():
    model = _Samples()
    control = TableBinding(SECTION, model).control
    painter = _draw(control)
    link_texts = [t for t in painter.texts if t[5] == "cond_a"]
    assert link_texts and tuple(link_texts[0][6][:3]) == tuple(style.CHECK_MARK[:3])
    plain = [t for t in painter.texts if t[5] == "s1"]
    assert plain and tuple(plain[0][6][:3]) != tuple(style.CHECK_MARK[:3])
    x, y, w, h = link_texts[0][:4]
    underline = [r for r in painter.fills
                 if r[3] <= 1.5 and abs(r[1] - (y + h / 2)) < h and x - 1 <= r[0] <= x + w]
    assert underline, "no underline under the link"


def test_a_status_cell_is_filled_with_its_value_colour():
    model = _Samples()
    control = TableBinding(SECTION, model).control
    painter = _draw(control)
    fills = {tuple(r[4][:3]) for r in painter.fills if r[4] is not None}
    assert (0xD6, 0xF5, 0xDC) in fills
    assert (255, 220, 220) in fills


def _luminance(colour):
    r, g, b = (c / 255.0 for c in tuple(colour)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_text_on_a_value_fill_contrasts_with_the_fill():
    """A pale status fill under the dark theme's pale text made the value unreadable
    (MMFDB Admin's Spectra: "unverified" on #fff4cc). The text takes the ink that
    contrasts with the fill it sits on."""
    model = _Samples()
    control = TableBinding(SECTION, model).control
    painter = _draw(control)
    for value, fill in (("approved", (0xD6, 0xF5, 0xDC)), ("rejected", (255, 220, 220))):
        texts = [t for t in painter.texts if t[5] == value]
        assert texts, value
        assert abs(_luminance(texts[0][6]) - _luminance(fill)) > 0.45, (value, texts[0][6])


def test_text_on_a_dark_value_fill_stays_light():
    section = {**SECTION, "options": {**SECTION["options"], "columns": [
        {"key": "sample_id", "title": "Sample", "width": 120},
        {"key": "status", "title": "Status", "width": 120,
         "background": {"approved": "#204020"}},
    ]}}
    control = TableBinding(section, _Samples()).control
    painter = _draw(control)
    text = next(t for t in painter.texts if t[5] == "approved")
    assert _luminance(text[6]) > 0.5
