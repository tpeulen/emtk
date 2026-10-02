from emtk import im, i18n
from emtk.im_core import get_current_context
from emtk.testing import RecordingPainter


def test_runtime_translation_preserves_widget_identity_and_sizes():
    i18n.add_translations("de", {"Save": "Speichern", "Save this document": "Dieses Dokument speichern"})
    storage = {}
    ids, widths = [], []
    try:
        for locale, expected in [("en", "Save"), ("de-DE", "Speichern")]:
            i18n.set_locale(locale)
            painter = RecordingPainter()
            with im.frame(painter, (0, 0, 500, 300), storage=storage):
                im.button("Save##document")
                ctx = get_current_context()
                ids.append(ctx._last_id)
                widths.append(ctx.get_item_rect()[2])
            assert expected in painter.strings
        assert ids[0] == ids[1]
        assert widths[1] > widths[0]
    finally:
        i18n.set_locale("en")


def test_context_and_missing_translation_fallback():
    i18n.add_translations("fr", {"Open": "Ouvrir"})
    i18n.add_translations("fr", {"Open": "Ouvert"}, context="status")
    try:
        i18n.set_locale("fr")
        assert i18n.tr("Open", "status") == "Ouvert"
        assert i18n.tr("Open", "action") == "Ouvrir"
        assert i18n.tr("Untranslated") == "Untranslated"
    finally:
        i18n.set_locale("en")


def test_text_and_progress_widgets_use_the_application_catalog():
    i18n.add_translations("de", {"Ready": "Bereit"})
    painter = RecordingPainter()
    try:
        i18n.set_locale("de")
        with im.frame(painter, (0, 0, 500, 300)):
            im.text("Ready")
            im.text_colored((255, 255, 255, 255), "Ready")
            im.text_disabled("Ready")
            im.text_wrapped("Ready")
            im.progress_bar(0.5, (120, 20), "Ready")
        assert painter.strings.count("Bereit") == 5
    finally:
        i18n.set_locale("en")


def test_painter_level_menu_titles_and_rows_translate_at_render_time():
    from emtk.widgets.menus import Menu, MenuBar, MenuItem

    i18n.add_translations("de", {"File": "Datei", "Open": "Öffnen"})
    menu = Menu("File", [MenuItem("Open")])
    menu.open = True
    bar = MenuBar([menu])
    painter = RecordingPainter()
    try:
        i18n.set_locale("de")
        with im.frame(painter, (0, 0, 500, 300)):
            bar.draw(painter, 0, 0, 300, 24)
        assert "Datei" in painter.strings
        assert "Öffnen" in painter.strings
        i18n.set_locale("en")
        painter = RecordingPainter()
        with im.frame(painter, (0, 0, 500, 300)):
            bar.draw(painter, 0, 0, 300, 24)
        assert "File" in painter.strings and "Open" in painter.strings
    finally:
        i18n.set_locale("en")
