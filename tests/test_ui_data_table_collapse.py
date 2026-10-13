"""A table short of width drops whole columns before it scrolls (``collapse_order``).

The parameter tables of a fitting program are asked to fit anything from a wide
window to a docked side panel. Their columns are not equally worth the room:
the bounds go first, then the error, then the fixed flag; the name and the value
never. A spec says so per column with ``collapse_order`` and the table decides
from the width it is given, every frame, without flicker.
Recording painter (7 px a glyph, 16 px a line), no window, no toolkit.
"""
from __future__ import annotations

from emtk.testing import RecordingPainter
from emtk.widgets.data_table import DataTable, TableBinding, TableColumn

COLUMNS = [
    {"key": "name", "title": "Name"},
    {"key": "value", "title": "Value", "format": "%.5g"},
    {"key": "fixed", "title": "Fixed", "collapse_order": 3},
    {"key": "lo", "title": "Lo", "format": "%.4g", "collapse_order": 1},
    {"key": "hi", "title": "Hi", "format": "%.4g", "collapse_order": 1},
    {"key": "bounds_on", "title": "Bounds", "collapse_order": 1},
    {"key": "error", "title": "Error", "format": "%.3g", "collapse_order": 2},
]
ROWS = [
    {"name": "tau(1)", "value": 4.1234, "fixed": False, "lo": 0.1, "hi": 10.0,
     "bounds_on": True, "error": 0.012},
    {"name": "x(1)", "value": 0.75, "fixed": True, "lo": 0.0, "hi": 1.0,
     "bounds_on": False, "error": 0.003},
]


class Model:
    def rows(self):
        return ROWS


def _table() -> DataTable:
    binding = TableBinding({"type": "table", "source": "rows", "fit_columns": True,
                            "columns": COLUMNS}, Model())
    return binding.control


def _shown(table: DataTable, width: float) -> list[str]:
    table.draw(RecordingPainter(), 0, 0, width, 200)
    return [c.key for c in table.visible_columns()]


def _natural(table: DataTable) -> float:
    table.draw(RecordingPainter(), 0, 0, 2000, 200)
    return sum(table._fitted[c.key] for c in table.wanted_columns())


def test_spec_reads_collapse_order():
    assert TableColumn.from_spec({"key": "a", "collapse_order": 2}).collapse_order == 2
    assert TableColumn.from_spec({"key": "a"}).collapse_order == 0


def test_wide_table_keeps_every_column():
    table = _table()
    assert _shown(table, 2000) == [c["key"] for c in COLUMNS]
    assert table.collapsed == set()


def test_tiers_drop_in_declared_order_and_name_value_never():
    table = _table()
    full = _natural(table)
    widths = {c.key: table._fitted[c.key] for c in table.wanted_columns()}
    bounds = widths["lo"] + widths["hi"] + widths["bounds_on"]
    # Just too narrow for everything: the bounds go, all three together.
    seen = _shown(_table(), full - 20)
    assert seen == ["name", "value", "fixed", "error"]
    # Too narrow without the bounds too: the error goes next.
    seen = _shown(_table(), full - bounds - 20)
    assert seen == ["name", "value", "fixed"]
    # Then the fixed flag; the name and value stay at any width.
    seen = _shown(_table(), full - bounds - widths["error"] - 20)
    assert seen == ["name", "value"]
    assert _shown(_table(), 40) == ["name", "value"]


def test_widening_brings_the_last_dropped_tier_back_first():
    table = _table()
    full = _natural(table)
    widths = {c.key: table._fitted[c.key] for c in table.wanted_columns()}
    bounds = widths["lo"] + widths["hi"] + widths["bounds_on"]
    assert _shown(table, 60) == ["name", "value"]
    assert _shown(table, full - bounds + 40) == ["name", "value", "fixed", "error"]
    assert _shown(table, full + 40) == [c["key"] for c in COLUMNS]


def test_no_flicker_while_a_splitter_is_dragged():
    """Every width maps to one column set, and a width near a threshold does not toggle it."""
    table = _table()
    full = _natural(table)
    slack, margin = DataTable.COLLAPSE_SLACK, DataTable.COLLAPSE_HYSTERESIS
    # A few pixels short is tolerated; past the slack the bounds go, and stay gone frame after frame.
    assert "lo" in _shown(table, full - slack)
    sets = {tuple(_shown(table, full - slack - 1)) for _ in range(5)}
    assert sets == {("name", "value", "fixed", "error")}
    # Widening by less than the hysteresis does not bring them back ...
    for width in (full - slack, full, full + margin - 1, full - 2, full + 1):
        assert "lo" not in _shown(table, width)
    # ... widening by more does, and then going back inside the band does not drop them again.
    assert "lo" in _shown(table, full + margin)
    for width in (full + 1, full - slack, full + margin - 1):
        assert "lo" in _shown(table, width)


def test_the_user_hidden_set_is_not_the_collapsed_set():
    table = _table()
    table.set_column_hidden("error", True)
    _shown(table, 60)
    assert "error" not in table.collapsed
    assert table.hidden == {"error"}
    assert _shown(table, 2000) == ["name", "value", "fixed", "lo", "hi", "bounds_on"]


def test_a_dropped_cell_stays_reachable_in_the_row_tooltip():
    table = _table()
    table.draw(RecordingPainter(), 0, 0, 60, 200)
    assert table.collapsed >= {"lo", "hi", "error"}
    _, header_y, _, header_h = table._header_box
    body_x, body_y, _, _ = table._body_box
    text, part = table.tooltip_at(body_x + 5, body_y + 2)
    assert part[1] == 0
    assert "Lo: 0.1" in text and "Hi: 10" in text and "Bounds: on" in text
    assert "Error: 0.012" in text


def test_a_filter_does_not_depend_on_the_width():
    table = _table()
    table.filter.set_text("0.012")
    assert len(table.order()) == 1
    table.draw(RecordingPainter(), 0, 0, 60, 200)
    table.changed()
    assert len(table.order()) == 1


def test_a_table_without_collapse_order_still_scrolls():
    binding = TableBinding({"type": "table", "source": "rows", "fit_columns": True,
                            "columns": [{k: v for k, v in c.items() if k != "collapse_order"}
                                        for c in COLUMNS]}, Model())
    table = binding.control
    table.draw(RecordingPainter(), 0, 0, 120, 200)
    assert table.collapsed == set()
    assert table._hbar_box is not None


def test_a_language_switch_re_measures_the_headers():
    """Translated headers are re-measured, so they are neither cut nor make the table collapse late."""
    from emtk import i18n

    table = _table()
    table.draw(RecordingPainter(), 0, 0, 2000, 200)
    english = dict(table._title_w)
    before = i18n.language()
    try:
        i18n.add_translations("xx", {"Fixed": "Festgehaltener Wert"})
        i18n.set_language("xx")
        table.draw(RecordingPainter(), 0, 0, 2000, 200)
        assert table._title_w["fixed"] > english["fixed"]
    finally:
        i18n.set_language(before)
