"""A view spec renders entirely in the active language, measured as it is drawn.

The form lays a label out by its width; a widget translates what it draws.
When the two disagree -- the source measured, the translation drawn -- every
German button clips ("Setze(n)"). These tests render real specs, with
translations longer than their sources, and check two things: no English
source string is drawn, and no drawn label is wider than the place made for it.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from emtk import i18n
from emtk.dialog_window import DialogWindow
from emtk.i18n.testing import isolated
from emtk.testing import Driver, RecordingPainter
from emtk.widgets.view_spec import ViewSpecPanel

GERMAN = {
    "Acquisition settings": "Einstellungen der Datenerfassung",
    "Rate": "Wiederholungsrate des Lasers",
    "Mode": "Betriebsart der Messung",
    "Fast": "Schnell und ungenau",
    "Careful": "Langsam und gründlich",
    "Fit": "Anpassung durchführen",
    "Set": "Setzen und übernehmen",
    "Browse": "Durchsuchen nach Dateien",
    "Off": "Ausgeschaltet",
    "Run the analysis.": "Die Analyse ausführen.",
    "Results": "Ergebnisse der Auswertung",
    "Lifetime": "Fluoreszenzlebensdauer",
    "Notes": "Anmerkungen",
}

SPEC = {"domain": "renderapp", "sections": [
    {"type": "panel", "title": "Acquisition settings", "collapsible": True, "sections": [
        {"type": "value", "kind": "float", "attr": "rate", "label": "Rate", "minimum": 0,
         "special_text": "Off", "description": "Run the analysis."},
        {"type": "choice", "attr": "mode", "label": "Mode", "options": [["fast", "Fast"],
                                                                        ["careful", "Careful"]]},
        {"type": "toggle", "attr": "fit", "label": "Fit"},
        {"type": "button_row", "buttons": [
            {"label": "Set", "action": "apply", "description": "Run the analysis."},
            {"label": "Browse", "action": "browse", "description": "Run the analysis."}]},
    ]},
    {"type": "panel", "title": "Results", "collapsible": True, "sections": [
        {"type": "custom", "key": "data_table",
         "options": {"source": "rows", "columns": [
             {"key": "tau", "title": "Lifetime", "units": "ns"},
             {"key": "note", "title": "Notes"}]}}]},
]}


class Model(SimpleNamespace):
    def rows(self):
        return [{"tau": 1.5, "note": "x"}, {"tau": 3.0, "note": "y"}]


@pytest.fixture(autouse=True)
def _german():
    with isolated(language="de"):
        i18n.add_catalogue("renderapp", {"de": GERMAN})
        yield


def _model():
    return Model(rate=0.0, mode="fast", fit=False, apply=lambda: None, browse=lambda: None)


def _render(width=900, height=600):
    panel = ViewSpecPanel(SPEC, _model())
    driver = Driver(panel, (width, height))
    return panel, driver.frame(2)


def test_a_spec_draws_no_english_source_string():
    _panel, painter = _render()
    drawn = " | ".join(painter.strings)
    for source, german in GERMAN.items():
        # a tooltip; an unselected choice; a panel holding only a table (the
        # table is drawn below the form, without the panel's caption)
        if source in ("Run the analysis.", "Careful", "Results"):
            continue
        assert german in drawn, f"{german!r} not drawn"
        assert source not in [s.split("##")[0].strip(" ▾▸▴") for s in painter.strings], \
            f"English {source!r} drawn"
    assert "Fluoreszenzlebensdauer (ns)" in drawn


@pytest.mark.parametrize("width", [900, 520])
def test_no_translated_label_is_clipped(width):
    panel, painter = _render(width)
    clipped = []
    for (*_v, _align, text, _colour, _bold), meta in zip(painter.visible_texts,
                                                          painter.text_metadata):
        if text not in GERMAN.values() and not any(g in text for g in GERMAN.values()):
            continue
        measured, visible = meta["measured_bounds"], meta["visible_bounds"]
        if measured[2] - visible[2] > 0.5:
            clipped.append(text)
    assert not clipped, f"clipped: {clipped}"
    # Each button's caption lies inside the button the form made for it.
    texts = {t[5]: m["measured_bounds"] for t, m in zip(painter.visible_texts,
                                                         painter.text_metadata)}
    for action, caption in (("apply", "Setzen und übernehmen"),
                            ("browse", "Durchsuchen nach Dateien")):
        bx, _by, bw, _bh = panel.item_rects[action]
        tx, _ty, tw, _th = texts[caption]
        assert bx <= tx + 0.5 and tx + tw <= bx + bw + 0.5, (action, (bx, bw), (tx, tw))


def test_dialog_title_and_header_buttons_are_translated_and_fit():
    i18n.add_translations("de", {"Guide": "Geführte Einführung", "Settings": "Einstellungen"})
    dialog = DialogWindow("Settings", size=(500, 300), key="t")
    dialog.show()
    painter = RecordingPainter()
    from emtk import im

    with im.frame(painter, (0, 0, 800, 600)):
        dialog.begin((0, 0, 800, 600), buttons=("Guide",))
        dialog.end()
    assert "Einstellungen" in painter.strings
    assert any("Geführte Einführung" in s for s in painter.strings)
    assert "Guide" not in painter.strings and "Settings" not in painter.strings
    for (*_v, _a, text, _c, _b), meta in zip(painter.visible_texts, painter.text_metadata):
        if "Geführte" in text:
            assert meta["measured_bounds"][2] - meta["visible_bounds"][2] <= 0.5


def test_language_switch_relays_the_form_on_the_next_frame():
    panel = ViewSpecPanel(SPEC, _model())
    driver = Driver(panel, (900, 600))
    german = driver.frame(2)
    i18n.set_language("en")
    english = driver.frame(2)
    assert "Durchsuchen nach Dateien" in german.strings
    assert any(s.startswith("Browse") for s in english.strings)


def test_plot_title_and_axis_labels_are_translated_where_they_are_shown():
    """A plot's title and axis labels are display text, like a button's caption.

    Found by chisurf's real-use language matrix: a German session drew every
    widget German and every plot title/axis English ("Counts", "Micro-time (ns)").
    """
    from emtk import im, implot

    i18n.add_translations("de", {"Synthetic decay": "Synthetischer Zerfall",
                                 "Counts": "Zählungen", "Micro-time (ns)": "Mikrozeit (ns)"})
    painter = RecordingPainter()
    if True:
        for _ in range(2):
            with im.frame(painter, (0, 0, 600, 400)):
                im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
                im.set_next_window_size((600, 400), im.Cond.ALWAYS)
                im.begin("w")
                if implot.begin_plot("Synthetic decay##p", (-1, -1)):
                    implot.setup_axes("Micro-time (ns)", "Counts")
                    implot.plot_line("VV", [0.0, 1.0, 2.0], [3.0, 2.0, 1.0])
                    implot.end_plot()
                im.end()
    drawn = set(painter.strings)
    assert {"Synthetischer Zerfall", "Zählungen", "Mikrozeit (ns)"} <= drawn, drawn
    assert not {"Synthetic decay", "Counts", "Micro-time (ns)"} & drawn


def test_a_caption_padded_to_a_column_is_still_translated():
    """chisurf pads field captions with spaces so separate grids share one label column.

    The padded source ("Rate      ") is in no catalogue, so every padded caption of 19 tools
    drew English in a German session (found by chisurf's real-use language matrix).
    """
    from emtk.view_form import _tr_label

    assert _tr_label("Rate      ##rate") == "Wiederholungsrate des Lasers      ##rate"
    assert _tr_label("  Mode") == "  Betriebsart der Messung"
    assert _tr_label("   ") == "   "
