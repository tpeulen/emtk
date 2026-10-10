"""A button-row entry's ``icon`` is drawn in front of its label, the label untouched."""

from __future__ import annotations

from emtk import im
from emtk.testing import MetricPainter
from emtk.view_form import FormState, draw_sections, icon_caption


def test_icon_caption_spacing():
    """Colour pictograms take two spaces, geometric glyphs one, no icon none."""
    assert icon_caption("❓", "Help") == "❓  Help"
    assert icon_caption("▶", "Run") == "▶ Run"
    assert icon_caption("", "Run") == "Run"


def test_button_row_draws_icon_before_label():
    """The drawn caption carries the icon; the action, rect key and tooltip stay as declared."""
    spec = [{"type": "button_row", "buttons": [
        {"action": "open_help", "label": "Hilfe", "icon": "❓", "description": "Open help."},
        {"action": "run", "label": "Run"},
    ]}]
    state = FormState()

    class Model:
        def open_help(self):
            pass

    def gui():
        im.begin("w", (0, 0, 400, 80))
        draw_sections(spec, Model(), state, titles=False)
        im.end()

    for _ in range(2):
        painter = MetricPainter()
        with im.frame(painter, (0, 0, 400, 80)):
            gui()
    strings = painter.strings
    assert "❓  Hilfe" in strings and "Run" in strings
    assert set(state.rects) >= {"open_help", "run"}
