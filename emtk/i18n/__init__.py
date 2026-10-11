"""Qt-free translation for immediate-mode interfaces, shared by every emtk app.

Translate display strings, never widget identities or application data.
Changing the language takes effect on the next frame without recreating widget
state; :func:`generation` is bumped on every change so text an application
caches (laid-out labels, a menu built once) knows to re-render.

Translations are organised in **domains**: one per application or library
(``"emtk"`` for the toolkit's own buttons and tooltips, ``"myapp"``,
``"myplugin"`` …). A domain's catalogues are registered once with
:func:`add_catalogue` -- a directory of per-language files, Qt Linguist ``.ts``
XML or a plain JSON mapping -- and parsed lazily, the first time a string of
that domain is looked up in a language.

The lookup chain of :func:`tr` is ``domain → "emtk" → source``: an
application domain falls back to the toolkit's vocabulary, and an untranslated
string is returned unchanged. Placeholders are untouched -- translate first,
format after::

    tr("Shortcut: {key}", domain="myapp").format(key="Ctrl+S")

Strings that must be collected for translation but are translated later (a
module-level table of labels) are wrapped in :func:`mark`, which is the
identity. ``python -m emtk.i18n.extract`` collects ``tr()``/``mark()``
literals and the text fields of ``view.json``/``guide.json``/``manifest.json``
into the catalogues; :func:`emtk.i18n.testing.untranslated_literals` is the
guard each repository runs over its own package.
"""
from __future__ import annotations

import locale as _locale_module
import os
import re
import threading
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "EMTK_DOMAIN",
    "add_catalogue",
    "add_translations",
    "available_languages",
    "available_locales",
    "catalogue_directory",
    "default_domain",
    "domains",
    "generation",
    "get_locale",
    "language",
    "mark",
    "remove_catalogue",
    "set_default_domain",
    "set_language_provider",
    "set_language",
    "set_locale",
    "tr",
    "use_domain",
]

#: The toolkit's own domain; the last stop of every lookup before the source.
EMTK_DOMAIN = "emtk"

#: The context a catalogue entry without one belongs to.
DEFAULT_CONTEXT = "default"

_lock = threading.RLock()
_language: str | None = None          # None: not chosen yet, resolved on first use
_explicit = False                      # set_language() was called
_provider = None                       # the application's language setting
_generation = 0
_default_domain: str | None = None
# Per-domain catalogue sources, in registration order (a dict keeps it).
_sources: dict[str, list[object]] = {}
# Parsed catalogues: (domain, language) -> (contexts, merged-any-context).
_cache: dict[tuple[str, str], tuple[dict[str, dict[str, str]], dict[str, str]]] = {}
# In-memory translations registered with add_translations() and no domain:
# language -> context -> source -> translation. Searched before the domains
# when no domain is named, so applications registering by hand keep working.
_memory: dict[str, dict[str, dict[str, str]]] = {}

_LANG_CODE = re.compile(r"^[A-Za-z]{2,3}([_-][A-Za-z0-9]{2,8})*$")


def _normalize(code: str | None) -> str:
    """``de_DE.UTF-8`` → ``de-de``; empty, ``C`` and ``POSIX`` → ``en``."""
    text = str(code or "").strip().split(".", 1)[0].split("@", 1)[0]
    text = text.replace("_", "-").lower()
    if text in {"", "c", "posix"}:
        return "en"
    return text


def _chain(code: str) -> tuple[str, ...]:
    """A regional language falls back to its base language: ``de-ch`` → ``de``."""
    return tuple(dict.fromkeys((code, code.split("-", 1)[0])))


def _bump() -> None:
    global _generation
    _generation += 1


# --------------------------------------------------------------------- language


def _detect_language() -> str:
    """The language before anything chose one.

    ``EMTK_LANG``, else the application's setting (:func:`set_language_provider`),
    else the operating-system locale, else ``en``.
    """
    env = os.environ.get("EMTK_LANG", "").strip()
    if env:
        return _normalize(env)
    if _provider is not None:
        try:
            chosen = _provider()
        except Exception:  # noqa: BLE001 - a broken setting must not break text
            chosen = None
        if chosen:
            return _normalize(chosen)
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "").strip()
        if value:
            return _normalize(value)
    try:
        code = _locale_module.getlocale()[0]
    except (ValueError, TypeError):
        code = None
    return _normalize(code)


def language() -> str:
    """The active language code (lower case, ``-`` separated, e.g. ``de`` or ``pt-br``).

    Until :func:`set_language` is called it is read from the ``EMTK_LANG``
    environment variable, else the application's language setting
    (:func:`set_language_provider`), else the operating-system locale, else
    ``"en"``.
    """
    global _language
    if _language is None:
        with _lock:
            if _language is None:
                _language = _detect_language()
    return _language


def set_language(code: str) -> None:
    """Select the active language; a change bumps :func:`generation`.

    An unavailable regional variant falls back to its base language at lookup
    (``de-CH`` reads the ``de`` catalogue).
    """
    global _language, _explicit
    code = _normalize(code)
    with _lock:
        _explicit = True
        if code != _language:
            _language = code
            _bump()


def set_language_provider(provider) -> None:
    """Name where the application keeps its language setting.

    ``provider()`` returns a language code (or ``None``). It is consulted
    while no :func:`set_language` has been made, after ``EMTK_LANG`` and
    before the operating-system locale -- so a headless run of an application
    follows the application's setting rather than the machine's locale. A
    language already resolved from the defaults is re-resolved (and
    :func:`generation` bumped when that changes it); an explicit choice is
    kept.
    """
    global _provider, _language
    with _lock:
        _provider = provider
        if not _explicit and _language is not None:
            code = _detect_language()
            if code != _language:
                _language = code
                _bump()


def generation() -> int:
    """A counter bumped whenever translated text may have changed.

    It changes on :func:`set_language` (to a different language) and whenever
    catalogues are added or removed. Cache rendered text keyed by it.
    """
    return _generation


# Former names, kept: applications written before domains existed call these.
def set_locale(locale: str) -> None:
    """Alias of :func:`set_language`."""
    set_language(locale)


def get_locale() -> str:
    """Alias of :func:`language`."""
    return language()


# --------------------------------------------------------------------- domains


def set_default_domain(domain: str | None) -> None:
    """Name the application's domain, searched first by a ``tr()`` that names none."""
    global _default_domain
    with _lock:
        if domain != _default_domain:
            _default_domain = domain
            _bump()


def default_domain() -> str | None:
    """The domain set by :func:`set_default_domain`, or ``None``."""
    return _default_domain


_scope: list[str | None] = []


class use_domain:
    """Within the block, a ``tr()`` that names no domain searches ``domain`` first.

    Widgets translate the labels they are handed without knowing whose they
    are; a panel drawing an application's spec (a view.json form, a help or
    guide card) wraps its drawing in this so the application's catalogue wins
    an ambiguous string. ``None`` changes nothing. Re-entrant; usable as a
    context manager only.
    """

    def __init__(self, domain: str | None) -> None:
        self.domain = domain

    def __enter__(self) -> "use_domain":
        _scope.append(self.domain)
        return self

    def __exit__(self, *exc: object) -> None:
        _scope.pop()


def domains() -> tuple[str, ...]:
    """Every domain with a registered catalogue, in registration order."""
    _ensure_builtin()
    return tuple(_sources)


def add_catalogue(domain: str, source: object) -> None:
    """Register a domain's catalogues.

    Parameters
    ----------
    domain
        The domain name (``"myapp"``, ``"myplugin"`` …).
    source
        A directory of per-language catalogue files -- ``<domain>_<lang>.ts``,
        ``<lang>.ts``, ``<domain>_<lang>.json`` or ``<lang>.json`` -- or a
        mapping ``{language: {source: translation}}`` /
        ``{language: {context: {source: translation}}}``. Files are parsed
        lazily on the first lookup of that language and cached; registering
        the same directory again is a no-op, a new one is searched after the
        earlier ones.
    """
    if not domain:
        raise ValueError("a catalogue needs a domain")
    if not isinstance(source, Mapping):
        source = Path(os.fspath(source))
    with _lock:
        sources = _sources.setdefault(domain, [])
        if any(_same_source(source, known) for known in sources):
            return
        sources.append(source)
        for key in [key for key in _cache if key[0] == domain]:
            del _cache[key]
        _bump()


def remove_catalogue(domain: str) -> None:
    """Forget every catalogue of ``domain`` (tests, plugin unload)."""
    with _lock:
        _sources.pop(domain, None)
        for key in [key for key in _cache if key[0] == domain]:
            del _cache[key]
        _bump()


def _same_source(a: object, b: object) -> bool:
    if isinstance(a, Path) and isinstance(b, Path):
        try:
            return a.resolve() == b.resolve()
        except OSError:
            return a == b
    return a is b


def catalogue_directory() -> Path:
    """The directory holding emtk's own ``emtk_<lang>.ts`` catalogues."""
    return Path(__file__).resolve().parent / "locales"


_builtin_registered = False


def _ensure_builtin() -> None:
    global _builtin_registered
    if not _builtin_registered:
        with _lock:
            if not _builtin_registered:
                _builtin_registered = True
                sources = _sources.setdefault(EMTK_DOMAIN, [])
                builtin = catalogue_directory()
                if not any(_same_source(builtin, known) for known in sources):
                    sources.insert(0, builtin)


def add_translations(locale: str, mapping: Mapping[str, str], context: str = DEFAULT_CONTEXT,
                     *, domain: str | None = None) -> None:
    """Merge source → translation strings for one language by hand.

    Without ``domain`` they go to the application's in-memory catalogue, which
    a ``tr()`` naming no domain searches first; with one they are layered over
    that domain's catalogue files.
    """
    values = {source: translated for source, translated in mapping.items()
              if isinstance(source, str) and isinstance(translated, str) and translated}
    code = _normalize(locale)
    with _lock:
        if domain is None:
            _memory.setdefault(code, {}).setdefault(context or DEFAULT_CONTEXT, {}).update(values)
        else:
            sources = _sources.setdefault(domain, [])
            store = next((s for s in sources if isinstance(s, _Overlay)), None)
            if store is None:
                store = _Overlay()
                sources.append(store)
            store.setdefault(code, {}).setdefault(context or DEFAULT_CONTEXT, {}).update(values)
            for key in [key for key in _cache if key[0] == domain]:
                del _cache[key]
        _bump()


class _Overlay(dict):
    """Hand-added translations of a domain: language → context → source → text."""


def available_languages(domain: str | None = None) -> tuple[str, ...]:
    """Languages with a catalogue (``en`` always included), for one domain or all."""
    _ensure_builtin()
    codes = {"en", *_memory}
    names = [domain] if domain else list(_sources)
    for name in names:
        for source in _sources.get(name, ()):
            if isinstance(source, Mapping):
                codes.update(_normalize(code) for code in source)
            elif isinstance(source, Path) and source.is_dir():
                for path in source.iterdir():
                    code = _file_language(path, name)
                    if code:
                        codes.add(code)
    return tuple(sorted(codes))


def available_locales() -> tuple[str, ...]:
    """Alias of :func:`available_languages` over every domain."""
    return available_languages()


# --------------------------------------------------------------------- lookup


def _file_language(path: Path, domain: str) -> str | None:
    """The language a catalogue file is for, or ``None`` when it is not one."""
    if path.suffix not in (".ts", ".json") or not path.is_file():
        return None
    stem = path.stem
    if stem.startswith(domain + "_"):
        rest = stem[len(domain) + 1:]
        return _normalize(rest) if _LANG_CODE.match(rest) else None
    if _LANG_CODE.match(stem) and len(stem.split("_", 1)[0].split("-", 1)[0]) <= 3:
        return _normalize(stem)
    return None


def _load(domain: str, code: str) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    key = (domain, code)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    from .catalogue import read_catalogue

    contexts: dict[str, dict[str, str]] = {}

    def merge(found: Mapping[str, Mapping[str, str]]) -> None:
        for context, messages in found.items():
            contexts.setdefault(context, {}).update(
                {s: t for s, t in messages.items() if isinstance(t, str) and t})

    with _lock:
        for source in list(_sources.get(domain, ())):
            if isinstance(source, _Overlay):
                merge(source.get(code, {}))
            elif isinstance(source, Mapping):
                for language_code, table in source.items():
                    if _normalize(language_code) != code or not isinstance(table, Mapping):
                        continue
                    if all(isinstance(v, str) for v in table.values()):
                        merge({DEFAULT_CONTEXT: table})
                    else:
                        merge({c: m for c, m in table.items() if isinstance(m, Mapping)})
            elif isinstance(source, Path) and source.is_dir():
                for path in sorted(source.iterdir()):
                    if _file_language(path, domain) == code:
                        merge(read_catalogue(path))
        # Any-context table: the domain-named and default contexts win an
        # ambiguous source, then the first context that translates it.
        anywhere: dict[str, str] = {}
        for messages in contexts.values():
            for s, t in messages.items():
                anywhere.setdefault(s, t)
        anywhere.update(contexts.get(DEFAULT_CONTEXT, {}))
        anywhere.update(contexts.get(domain, {}))
        result = (contexts, anywhere)
        _cache[key] = result
        return result


def _lookup(domain: str, code: str, source: str, context: str | None) -> str | None:
    contexts, anywhere = _load(domain, code)
    if context:
        found = contexts.get(context, {}).get(source)
        if found:
            return found
    return anywhere.get(source) or None


def _lookup_memory(code: str, source: str, context: str | None) -> str | None:
    catalog = _memory.get(code)
    if not catalog:
        return None
    for name in dict.fromkeys((context or DEFAULT_CONTEXT, DEFAULT_CONTEXT)):
        found = catalog.get(name, {}).get(source)
        if found:
            return found
    return None


def tr(source: str, context: str | None = None, *, domain: str | None = None) -> str:
    """Translate ``source`` into the active language.

    Parameters
    ----------
    source
        The canonical (English) display string. Placeholders are returned as
        they are in the translation; format the result, never the source.
    context
        Optional disambiguation (a Qt Linguist context): the same English word
        translated differently in two places. An entry without that context
        still matches. May be passed positionally.
    domain
        The catalogue domain (``"myapp"``, ``"emtk"`` …). The chain is
        ``domain → "emtk" → source``. Without one, the hand-added catalogue,
        the :func:`default_domain` and every other registered domain are
        searched, then ``"emtk"``.

    Returns
    -------
    str
        The translation, or ``source`` unchanged.
    """
    if not source or not isinstance(source, str):
        return source
    scope = _scope[-1] if (domain is None and _scope) else None
    key = (source, context, domain, scope)
    if _memo_generation[0] == _generation:
        found = _memo.get(key)
        if found is not None:
            return found
    else:
        _memo.clear()
        _memo_generation[0] = _generation
    found = _resolve(source, context, domain, scope)
    if len(_memo) > 50_000:
        _memo.clear()
    _memo[key] = found
    return found


# Resolved strings for the current generation: a label is looked up every frame.
_memo: dict[tuple[str, str | None, str | None, str | None], str] = {}
_memo_generation = [-1]


def _resolve(source: str, context: str | None, domain: str | None,
             scope: str | None = None) -> str:
    _ensure_builtin()
    for code in _chain(language()):
        if domain is not None:
            names = [domain]
            memory_first = False
        else:
            names = [n for n in dict.fromkeys((scope, _default_domain, *_sources)) if n]
            memory_first = True
        if memory_first:
            found = _lookup_memory(code, source, context)
            if found:
                return found
        for name in names:
            if name == EMTK_DOMAIN:
                continue
            found = _lookup(name, code, source, context)
            if found:
                return found
        if not memory_first:
            # A named domain still sees the hand-added application strings
            # before the toolkit's own vocabulary.
            found = _lookup_memory(code, source, context)
            if found:
                return found
        found = _lookup(EMTK_DOMAIN, code, source, context)
        if found:
            return found
    return source


def mark(source: str, context: str | None = None, *, domain: str | None = None) -> str:
    """Mark ``source`` for extraction without translating it (identity).

    For text defined before a language is chosen -- a module-level table of
    labels -- and translated with :func:`tr` where it is shown.
    """
    return source
