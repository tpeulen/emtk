"""A first-viewport default is declared once without overriding saved or user layouts."""

from copy import deepcopy

import pytest
from emtk.app import ImApp
from emtk.docking import DockManager, LayoutStore, Region, Split
from emtk.testing import RecordingPainter


def make(store=None):
    """Declare the actual form/plot shape a compact calculator changes at its first viewport."""
    manager = DockManager(
        Split("h", 0.32, Region("editor"), Split("v", 0.5, Region("distance"), Region("rate"))),
        store=store,
    )
    manager.add_window("editor", "Parameters", lambda box: None, dock="editor", closable=False)
    manager.add_window("distribution", "Distribution", lambda box: None, dock="distance")
    manager.add_window("rate", "Rate", lambda box: None, dock="rate", visible=False)
    manager.add_window(
        "notes",
        "Notes",
        lambda box: None,
        box=(22, 44, 220, 140),
        visible=False,
        collapsed=True,
        anchor="bottom-right",
        tooltip="Keep this.",
    )
    return manager


def compact():
    """Keep both plots while placing controls above them in a narrow host."""
    return Split("v", 0.44, Region("controls"), Split("h", 0.5, Region("distance"), Region("rate")))


def test_fresh_default_updates_current_and_reset_layout_without_changing_window_properties(
    tmp_path,
):
    """Reset restores the selected compact declaration and clears the existing store."""
    store = LayoutStore("compact", path=tmp_path / "layout.json")
    manager = make(store)
    original_windows = dict(manager.windows)
    original_properties = {key: vars(win).copy() for key, win in manager.windows.items()}
    declared = compact()
    declaration_before = deepcopy(declared)
    assert manager.configure_default_layout(declared, {"editor": "controls"})
    assert declared.name == ""  # the caller's tree was not indexed/mutated
    assert declared == declaration_before
    assert manager.layout.axis == "v" and manager.layout.ratio == 0.44
    assert manager.region_of("editor") == "controls"
    assert manager.region_of("distribution") == "distance"
    assert manager.region_of("notes") is None and manager.floating() == ["notes"]
    assert manager.store is store and not store.load()
    assert manager.windows == original_windows
    assert {key: vars(win) for key, win in manager.windows.items()} == original_properties
    manager.dock("editor", "rate")
    manager.set_ratio("root", 0.7)
    manager.show("rate")
    manager.save()
    assert store.load()
    manager.reset()
    assert manager.layout.axis == "v" and manager.layout.ratio == 0.44
    assert manager.region_of("editor") == "controls"
    assert not manager.window("rate").visible
    assert manager.floating() == ["notes"]
    assert manager.window("notes").box == (22, 44, 220, 140)
    assert not store.load()


@pytest.mark.parametrize("restored", [{}, {"version": 1}, {"windows": {}, "regions": {}}])
def test_empty_restore_does_not_prevent_a_fresh_viewport_default(restored):
    """An empty preferences/layout loader is not evidence of a saved user choice."""
    manager = make()
    manager.restore(restored)
    assert manager.configure_default_layout(compact(), {"editor": "controls"})


def test_a_real_saved_layout_always_wins_even_when_it_matches_constructor_defaults():
    """Saved window visibility, floating boxes and selection must remain untouched."""
    source = make()
    saved = source.state()
    manager = make()
    manager.restore(saved)
    before = deepcopy(manager.state())
    assert not manager.configure_default_layout(compact(), {"editor": "controls"})
    assert manager.state() == before


@pytest.mark.parametrize(
    "action",
    [
        lambda manager: manager.dock("editor", "distance"),
        lambda manager: manager.set_ratio("root", 0.7),
        lambda manager: manager.show("rate"),
        lambda manager: manager.set_extra("plot_height", 250),
    ],
)
@pytest.mark.parametrize("flush", [False, True])
def test_user_changes_before_first_draw_are_not_replaced_even_after_flush(action, flush):
    """Writing a user change cannot make it look fresh after _dirty is cleared."""
    manager = make()
    action(manager)
    if flush:
        manager.flush()
    before = deepcopy(manager.state())
    assert not manager.configure_default_layout(compact(), {"editor": "controls"})
    assert manager.state() == before


def test_first_configuration_is_not_repeated_after_resize_or_reset():
    """The selected first-viewport default remains the declaration for this app instance."""
    manager = make()
    assert manager.configure_default_layout(compact(), {"editor": "controls"})
    before = manager.state()
    assert not manager.configure_default_layout(
        Region("all"), dict.fromkeys(manager.windows, "all")
    )
    assert manager.state() == before
    manager.reset()
    assert not manager.configure_default_layout(
        Region("all"), dict.fromkeys(manager.windows, "all")
    )


def test_rendered_layout_is_not_replaced_by_late_application_adaptation():
    """Select a viewport default before drawing rather than rearranging an existing session."""
    manager = make()
    app = ImApp(lambda: manager.draw((0, 0, 640, 480)))
    app.draw(RecordingPainter(), 0, 0, 640, 480)
    before = manager.state()
    assert not manager.configure_default_layout(compact(), {"editor": "controls"})
    assert manager.state() == before


@pytest.mark.parametrize(
    "layout, mapping",
    [
        (compact(), {"unknown": "controls"}),
        (compact(), {"editor": "unknown"}),
        (Region("all"), {"editor": "all"}),  # unmapped plot regions disappeared
        (Split("h", 0.5, Region("same"), Region("same")), {"editor": "same"}),
        (Split("invalid", 0.5, Region("controls"), Region("rate")), {"editor": "controls"}),
        (Split("h", 0.5, Region("controls"), None), {"editor": "controls"}),
    ],
)
def test_invalid_region_or_window_mapping_is_atomic_and_does_not_consume_fresh_selection(
    layout, mapping
):
    """No half-applied tree/defaults remain after input validation fails."""
    manager = make()
    before = deepcopy(manager.state())
    with pytest.raises((KeyError, ValueError)):
        manager.configure_default_layout(layout, mapping)
    assert manager.state() == before
    assert manager.configure_default_layout(compact(), {"editor": "controls"})


def test_saved_unknown_windows_cannot_be_discarded_by_a_default_selection():
    """Lazy windows from a persisted session are meaningful even before they are constructed."""
    manager = make()
    manager.restore({"windows": {"later": {"dock": "editor", "visible": False}}})
    before = manager.state()
    assert not manager.configure_default_layout(compact(), {"editor": "controls"})
    assert manager.state() == before and "later" in manager.state()["windows"]


def test_declared_split_ratio_precision_survives_configuration_and_reset():
    """Copying a declaration is not a persistence round trip that rounds its ratios."""
    manager = make()
    declared = compact()
    declared.ratio = 1.0 / 3.0
    assert manager.configure_default_layout(declared, {"editor": "controls"})
    assert manager.layout.ratio == declared.ratio
    manager.set_ratio("root", 0.7)
    manager.reset()
    assert manager.layout.ratio == declared.ratio


def test_saved_selection_extras_and_floating_boxes_remain_identical():
    """A persisted customized session is not partially overwritten by viewport defaults."""
    source = make()
    source.dock("editor", "rate")
    source.focus("rate")
    source.undock("distribution", (11, 22, 240, 180))
    source.set_extra("plot_height", 250)
    manager = make()
    manager.restore(source.state())
    before = deepcopy(manager.state())
    assert not manager.configure_default_layout(compact(), {"editor": "controls"})
    assert manager.state() == before
    assert manager.extra("plot_height") == 250
    assert manager.window("distribution").box == (11, 22, 240, 180)
    assert manager.active_tab("rate") == "rate"


def test_invalid_mapping_keeps_reset_defaults_window_objects_and_store_bytes(tmp_path):
    """Validation cannot mutate defaults or persistence before all mapping entries are valid."""
    path = tmp_path / "layout.json"
    store = LayoutStore("atomic", path=path)
    store.save({"unrecognized_metadata": "preserved"})
    saved_bytes = path.read_bytes()
    manager = make(store)
    defaults = deepcopy(manager._defaults)
    windows = {key: vars(win).copy() for key, win in manager.windows.items()}
    with pytest.raises(KeyError):
        manager.configure_default_layout(compact(), {"editor": "controls", "rate": "unknown"})
    assert manager._defaults == defaults
    assert {key: vars(win) for key, win in manager.windows.items()} == windows
    assert path.read_bytes() == saved_bytes
    assert manager.layout.axis == "h" and manager.layout.ratio == 0.32
