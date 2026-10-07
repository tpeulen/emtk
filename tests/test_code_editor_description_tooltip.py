"""Declared code-editor descriptions appear over the editor's actual hover rectangle."""

from __future__ import annotations

import pytest
from emtk import i18n, im
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form

DESCRIPTION = "Edit the complete calibration JSON; Apply validates the working definition."
TRANSLATED = "Modifier la définition complète; Apply valide la configuration."


class EditorApp(ImApp):
    """Render the public form editor beside a separate following control."""

    def __init__(self, *, disabled=False, read_only=False, description=DESCRIPTION):
        self.json_text = '{"calibration_id": "known-reference", "mixing": [0.05, 0.02]}'
        self.disabled = disabled
        self.form = FormState()
        self.tooltip: str | None = None
        self.spec = {
            "sections": [
                {
                    "type": "custom",
                    "key": "code_editor",
                    "target": "json_text",
                    "title": "Complete JSON definition",
                    "description": description,
                    "options": {"language": "json", "height": 180, "read_only": read_only},
                },
                {"type": "button_row", "buttons": [{"label": "Cancel", "action": "cancel"}]},
            ]
        }
        super().__init__(self.gui)
        self.io.wall_clock = False

    def enabled(self, name):
        """Use the normal model permission hook for the disabled editor variant."""
        return not self.disabled

    def cancel(self):
        """Provide the following control without changing editor state."""

    def gui(self):
        """Render through draw_form and read its actual frame tooltip."""
        im.begin("Definition", (0, 0, 640, 300))
        draw_form(self.spec, self, self.form)
        self.tooltip = im.get_current_context().tooltip
        im.end()


@pytest.mark.parametrize("mode", ["editable", "read-only", "disabled"])
def test_actual_editor_hover_emits_description_without_mutating_the_model(mode):
    """The declared description is visible over the code region in all permission modes."""
    app = EditorApp(disabled=mode == "disabled", read_only=mode == "read-only")
    ui = Driver(app, (640, 300))
    ui.frame(2)
    original = app.json_text
    ui.hover("json_text")
    app.io.now += 2.0
    ui.frame(2)
    assert app.tooltip == DESCRIPTION
    assert "complete calibration JSON" in " ".join(ui.painter.strings)
    assert app.json_text == original
    ui.hover("Cancel")
    assert app.tooltip is None
    assert app.json_text == original
    if mode != "editable":
        ui.click("json_text")
        ui.type("corruption")
        assert app.json_text == original


def test_description_uses_the_existing_translation_path():
    """A code editor description is translated by the same tooltip helper as other fields."""
    old_locale = i18n.get_locale()
    i18n.add_translations("code-editor-tooltip-test", {DESCRIPTION: TRANSLATED})
    try:
        i18n.set_locale("code-editor-tooltip-test")
        app = EditorApp()
        ui = Driver(app, (640, 300))
        ui.frame(2)
        ui.hover("json_text")
        assert app.tooltip == TRANSLATED
    finally:
        i18n.set_locale(old_locale)


def test_editor_without_description_does_not_invent_a_tooltip():
    """Omitting optional description keeps the established no-tooltip behavior."""
    app = EditorApp(description="")
    ui = Driver(app, (640, 300))
    ui.frame(2)
    ui.hover("json_text")
    assert app.tooltip is None
