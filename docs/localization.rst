Localization
============

EMTK's ``emtk.i18n`` module supports runtime UI translation without Qt or
other dependencies. Applications supply source-to-translation catalogs::

    from emtk import i18n, im

    i18n.add_translations("de", {
        "Save": "Speichern",
        "Save this document": "Dieses Dokument speichern",
    })
    i18n.set_locale("de")
    im.button("Save##save_document")
    im.set_item_tooltip("Save this document")

Immediate-mode widget labels and tooltips use the selected catalog. Hidden
``##`` or ``###`` identity suffixes stay unchanged, including while the language
changes. Widget sizing measures the translated label. Translate other UI prose
explicitly with ``i18n.tr(text)``; application data and editable text buffers are
not translated. For ambiguous terms, use ``i18n.tr(text, context="status")`` and
register the corresponding catalog context.

A regional locale such as ``de-DE`` falls back to ``de``. Missing or empty
translations fall back to the source string. ``available_locales()`` lists
registered locales; ``get_locale()`` reports the selected locale. Switching
languages takes effect on the next frame. Hosts must request a redraw when a
language is changed outside an input event.

Translation catalogs do not provide fonts. The host must supply dynamic font
coverage for scripts outside the baked Latin, Cyrillic, Greek, and mathematical
glyph set. The bundled atlas covers the six existing ChiSurf interface locales.
Translation support does not imply bidirectional layout, shaping, or
count-aware plural selection.
