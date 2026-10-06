"""Retained view-spec panels use the immediate-mode form's grid and events."""
from types import SimpleNamespace

import pytest
from emtk.testing import Driver, RecordingPainter
from emtk.widgets.view_spec import ViewSpecPanel


def test_panel_grid_packs_two_fields_per_line_and_shares_width_by_weight():
    """The declared column count and 1:3 weights reach the form renderer."""
    model = SimpleNamespace(first="one", second="three", third="next", fourth="row")
    spec = {"n_col": 2, "sections": [
        {"type": "value", "kind": "str", "attr": name, "weight": weight,
         "description": "An editable value."}
        for name, weight in (("first", 1), ("second", 3), ("third", 1), ("fourth", 3))
    ]}
    panel = ViewSpecPanel(spec, model)
    panel.draw(RecordingPainter(), 0, 0, 800, 400)
    first, second, third, fourth = [panel.item_rects[name] for name in vars(model)]
    assert first[1] == pytest.approx(second[1])
    assert third[1] == pytest.approx(fourth[1])
    assert third[1] > first[1] + first[3]
    assert second[2] == pytest.approx(first[2] * 3)
    assert second[0] >= first[0] + first[2]


def test_panel_stretches_button_row_and_calls_action_on_input_frame():
    """A weighted action fills its row and receives delegated pointer input."""
    pressed = []
    panel = ViewSpecPanel({"sections": [
        {"type": "button_row", "weight": 1, "description": "Run the analysis.",
         "buttons": [{"label": "Run", "action": "run", "description": "Run the analysis."}]}
    ]}, SimpleNamespace(run=lambda: pressed.append("run")))
    driver = Driver(panel, (800, 400))
    driver.frame()
    assert panel.item_rects["run"][2] > 750
    driver.click("run")
    assert pressed == ["run"]


def test_panel_keeps_group_selector_and_search_and_notifies_field_changes():
    """The old panel's discovery controls remain usable with the new form."""
    model = SimpleNamespace(first=False, second=False)
    changed = []
    panel = ViewSpecPanel({"sections": [
        {"type": "panel", "title": title, "sections": [
            {"type": "toggle", "attr": name, "label": label, "description": label}]}
        for title, name, label in (("First group", "first", "Alpha"),
                                   ("Second group", "second", "Beta"))
    ]}, model, lambda name, value: changed.append((name, value)))
    driver = Driver(panel, (800, 400))
    driver.frame()
    assert {"view_spec.group", "view_spec.filter", "first", "second"} <= panel.item_rects.keys()
    driver.click("first")
    assert model.first is True
    assert changed == [("first", True)]
    driver.click("view_spec.group")
    driver.click("Second group")
    driver.frame()
    assert "first" not in panel.item_rects
    assert "second" in panel.item_rects
    driver.click("view_spec.group")
    driver.click("< all >")
    driver.frame()
    assert {"first", "second"} <= panel.item_rects.keys()
    driver.click("view_spec.filter")
    driver.type("Beta")
    assert "first" not in panel.item_rects
    assert "second" in panel.item_rects


def test_panel_keeps_bound_tables_refreshing_and_selectable():
    """A growing result source keeps its bindings and applies row callbacks."""
    selected = []
    model = SimpleNamespace(rows=[{"name": "first"}], pick=selected.append)
    panel = ViewSpecPanel({"sections": [
        {"type": "table", "source": "rows", "selected_call": "pick", "expand": True,
         "columns": [{"key": "name", "title": "Name"}], "description": "Results."}
    ]}, model)
    driver = Driver(panel, (800, 400))
    driver.frame()
    binding = panel.tables[0]
    model.rows.append({"name": "second"})
    driver.frame()
    assert panel.tables[0] is binding
    assert "second" in driver.painter.strings
    table = binding.control
    x, y, _, _ = table._body_box
    driver.click((x + 30, y + table._row_h * 1.5))
    assert selected == [{"name": "second"}]


def test_panel_preserves_unspecified_numeric_styles_without_mutating_spec():
    """Default integers retain stepping and floats retain a usable slider."""
    spec = {"sections": [
        {"type": "value", "kind": "int", "attr": "count", "description": "Count."},
        {"type": "value", "kind": "float", "attr": "fraction", "description": "Fraction."},
    ]}
    model = SimpleNamespace(count=2, fraction=0.25)
    panel = ViewSpecPanel(spec, model)
    driver = Driver(panel, (800, 400))
    driver.frame()
    assert {"count.stepper", "fraction.slider"} <= panel.item_rects.keys()
    x, y, w, h = panel.item_rects["count.stepper"]
    driver.click((x + w / 2, y + h / 4))
    assert model.count == 3
    x, y, w, h = panel.item_rects["fraction.slider"]
    driver.click((x + w * 0.75, y + h / 2))
    assert model.fraction > 0.5
    assert all("style" not in section and "minimum" not in section for section in spec["sections"])


def test_explicit_numeric_style_overrides_legacy_panel_defaults():
    """A caller can request plain edit fields without inferred subcontrols."""
    panel = ViewSpecPanel({"sections": [
        {"type": "value", "kind": kind, "attr": name, "style": "edit",
         "description": "Plain value field."}
        for kind, name in (("int", "count"), ("float", "fraction"))
    ]}, SimpleNamespace(count=2, fraction=0.25))
    driver = Driver(panel, (800, 400))
    driver.frame()
    assert {"count", "fraction"} <= panel.item_rects.keys()
    assert "count.stepper" not in panel.item_rects
    assert "fraction.slider" not in panel.item_rects
