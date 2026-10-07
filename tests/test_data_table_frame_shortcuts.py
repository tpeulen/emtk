"""Table text editing keeps the host's modifiers through the real frame bridge."""

from __future__ import annotations

import pytest
from emtk import clipboard, im, keys
from emtk.app import ImApp
from emtk.events import LEFT_BUTTON, META_MODIFIER, SHIFT_MODIFIER
from emtk.testing import Driver
from emtk.widgets.data_table import TableBinding, draw_table


class TableApp(ImApp):
    """Draw editable scientific settings through the production immediate-mode table."""

    def __init__(self):
        self.rows = [{"tail": "700-2000", "mixing": 0.05, "locked": "reference"}]
        self.edits = []
        self.binding = TableBinding(
            {
                "type": "table",
                "source": "rows",
                "filter": True,
                "height": 200,
                "edited_call": "edited",
                "columns": [
                    {"key": "tail", "label": "Tail bins", "editable": True},
                    {"key": "mixing", "label": "Mixing", "editable": True},
                    {"key": "locked", "label": "Source", "editable": False},
                ],
            },
            self,
        )
        super().__init__(self.gui)
        self.io.wall_clock = False

    def edited(self, record, key, value):
        """Record actual public table commits without replacing the input bridge."""
        self.edits.append((key, value))

    def gui(self):
        """Render the same bound settings on every frame."""
        im.begin("Calibration", (0, 0, 640, 300))
        draw_table(self.binding, "settings")
        im.end()


@pytest.fixture(params=[False, True], ids=["physical-ctrl-pc", "physical-super-mac"])
def primary(request):
    """Normalize physical Ctrl or Super as a real host does before dispatch."""
    mac = request.param
    keys.set_mac_behaviors(mac)
    yield keys.modifiers_from_dom(not mac, False, False, mac, mac=mac)
    keys.set_mac_behaviors(None)


@pytest.fixture
def table():
    """Drive the real app/surface with painted cell targets."""
    app = TableApp()
    ui = Driver(app, (640, 300))
    ui.frame(2)
    yield app, ui


def open_cell(app, ui, caption, key):
    """Double-click the painted cell; never start an editor through internal state."""
    ui.hover(caption)
    x, y, w, h = ui.rect(caption)
    point = (x + w / 2, y + h / 2)
    ui.surface.on_pointer_press(*point, LEFT_BUTTON, 0, double=True)
    ui.frame()
    ui.surface.on_pointer_release(*point, LEFT_BUTTON, 0)
    ui.frame()
    assert app.binding.control.editing == (0, key)


@pytest.mark.parametrize(
    "key,caption,typed,expected",
    [
        ("tail", "700-2000", "850-1850", "850-1850"),
        ("mixing", "0.05", "0.071", 0.071),
    ],
)
@pytest.mark.parametrize("commit", [True, False], ids=["enter", "escape"])
def test_primary_select_all_replaces_cell_then_commits_or_cancels(
    table, primary, key, caption, typed, expected, commit
):
    """Replacement removes the entire old value and commits exactly once, or not at all."""
    app, ui = table
    original = dict(app.rows[0])
    open_cell(app, ui, caption, key)
    ui.key(ord("A"), "a", primary)
    assert app.binding.control.editor.field.selected_text() == caption
    ui.type(typed)
    assert app.binding.control.editor.text == typed
    assert app.rows[0] == original
    ui.press(keys.KEY_RETURN if commit else keys.KEY_ESCAPE)
    assert app.binding.control.editing is None
    assert app.rows[0][key] == (expected if commit else original[key])
    assert app.edits == ([(key, expected)] if commit else [])


def test_filter_select_all_replaces_query(table, primary):
    """The table's filter receives the same primary shortcut as its editable cells."""
    app, ui = table
    ui.click(app.binding.control._filter_box)
    ui.type("700")
    ui.key(ord("A"), "a", primary)
    ui.type("reference")
    assert app.binding.control.filter.text == "reference"
    assert app.binding.control.order() == [0]
    assert app.edits == []


def test_cell_clipboard_roundtrip_and_shift_navigation(table, primary):
    """Modifier forwarding preserves clipboard and selection navigation before commit."""
    app, ui = table
    held = {"text": ""}
    clipboard.set_hook(lambda text: held.__setitem__("text", text), lambda: held["text"])
    try:
        open_cell(app, ui, "700-2000", "tail")
        ui.key(ord("A"), "a", primary)
        ui.key(ord("C"), "c", primary)
        assert held["text"] == "700-2000"
        held["text"] = "850-1850"
        ui.key(ord("V"), "v", primary)
        assert app.binding.control.editor.text == "850-1850"
        ui.press(keys.KEY_LEFT, SHIFT_MODIFIER)
        assert app.binding.control.editor.field.selected_text() == "0"
        ui.type("5")
        ui.press(keys.KEY_RETURN)
        assert app.rows[0]["tail"] == "850-1855"
        assert app.edits == [("tail", "850-1855")]
    finally:
        clipboard.set_hook(None)


def test_secondary_mac_control_keeps_emacs_line_navigation(table):
    """Physical Mac Control-A goes to the line start; it is not primary Command-A."""
    keys.set_mac_behaviors(True)
    try:
        app, ui = table
        open_cell(app, ui, "700-2000", "tail")
        ui.key(ord("A"), "a", META_MODIFIER)
        field = app.binding.control.editor.field
        assert field.cursor == 0 and not field.has_selection()
        ui.type("#")
        ui.press(keys.KEY_RETURN)
        assert app.rows[0]["tail"] == "#700-2000"
    finally:
        keys.set_mac_behaviors(None)


def test_read_only_cell_ignores_replacement_and_navigation_still_selects(table, primary):
    """A primary shortcut cannot turn a locked cell into an editor or alter its row."""
    app, ui = table
    ui.click("reference")
    ui.click("reference")
    assert app.binding.control.editing is None
    ui.key(ord("A"), "a", primary)
    ui.type("replacement")
    ui.press(keys.KEY_DOWN)
    assert app.rows[0]["locked"] == "reference"
    assert app.binding.control.selected_index() == 0
    assert app.edits == []
