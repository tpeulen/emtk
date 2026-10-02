"""Qt-free translation catalogs for immediate-mode interfaces.

Translate display strings, never widget identities or application data. Changing
the locale takes effect on the next frame without recreating widget state.
Catalogs belong to the application; the toolkit adds no translation dependency.
"""
from __future__ import annotations

from collections.abc import Mapping

_locale = "en"
_catalogs: dict[str, dict[str, dict[str, str]]] = {}


def _normalize(locale: str) -> str:
    return str(locale).strip().replace("_", "-").lower() or "en"


def add_translations(locale: str, mapping: Mapping[str, str], context: str = "default") -> None:
    """Merge a context's source-to-translation strings into a locale catalog."""
    values = _catalogs.setdefault(_normalize(locale), {}).setdefault(context, {})
    values.update({source: translated for source, translated in mapping.items()
                   if isinstance(source, str) and isinstance(translated, str) and translated})


def set_locale(locale: str) -> None:
    """Select a locale; an unavailable regional catalog falls back to its language."""
    global _locale
    _locale = _normalize(locale)


def get_locale() -> str:
    return _locale


def available_locales() -> tuple[str, ...]:
    return tuple(sorted({"en", *_catalogs}))


def tr(text: str, context: str = "default") -> str:
    """Resolve a display string, falling back to its source when untranslated."""
    for locale in dict.fromkeys((_locale, _locale.split("-", 1)[0])):
        catalog = _catalogs.get(locale, {})
        for name in dict.fromkeys((context, "default")):
            translated = catalog.get(name, {}).get(text)
            if translated:
                return translated
    return text
