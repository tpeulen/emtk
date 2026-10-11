"""Collect translatable strings of a package into its catalogues.

    python -m emtk.i18n.extract <package_dir> --domain <d> --locales de fr --out <dir>

Collected:

* the first string literal of every ``tr(...)`` / ``mark(...)`` call --
  bare, or as an attribute (``i18n.tr``, ``emtk.i18n.mark``); a call naming a
  different ``domain=`` literal is left to that domain, a ``context=`` literal
  files the string under that context;
* the text fields (:data:`TEXT_KEYS`) of every ``*view.json``,
  ``*guide*.json`` and ``manifest.json`` -- the AutoForm specs, guided tours
  and plugin manifests that :mod:`emtk.widgets.view_spec` and the help cards
  pass through ``tr()`` at render time.

The catalogue of each locale (``<out>/<domain>_<lang>.ts``, or ``.json`` with
``--format json``) is **merged**, never overwritten: a translation already
there is kept (finished or not), a new string is added ``unfinished``, a
string no longer found is marked ``obsolete`` (its translation kept, so a
string that comes back is restored), and contexts this extraction does not
own -- a Qt ``.ui`` form's class context in a shared catalogue -- are left
alone. A string whose context moved inherits its old finished translation
when that is unambiguous.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from .catalogue import Message, read_messages, write_messages

__all__ = ["TEXT_KEYS", "collect", "collect_json", "collect_python", "extract", "merge", "main",
           "parse_spec_args"]

#: Keys whose values are user-facing text in view.json / guide.json / manifest.json.
#: Identity keys (``attr``, ``key``, ``id``, ``display_name``, ``categories``) are
#: never collected; ``options``/``choices`` only when they are the visible labels.
TEXT_KEYS = frozenset({
    "title", "description", "label", "suffix", "placeholder", "add_label", "remove_label",
    "component_title", "subtitle", "text", "x_label", "y_label", "hint", "tooltip", "units",
    "caption", "special_text", "descriptions", "labels", "menu", "body", "help",
    "summary", "experimental_message", "deprecation_message",
})

_SKIP_PARTS = frozenset({"test", "tests", "__pycache__", ".git", "node_modules"})

Entry = tuple[str, str]  # (context, source)


def _shipped(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return not (any(p in _SKIP_PARTS or p.startswith(".") for p in parts[:-1])
                or path.name.startswith("test_"))


# --------------------------------------------------------------------- python


def _callee(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _decorator_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        node = node.func
    return _callee(node)


def collect_python(source: str, filename: str, domain: str, *,
                   functions: Iterable[str] = ("tr", "mark"),
                   docstrings_of: Iterable[str] = ()
                   ) -> dict[Entry, list[tuple[str, int]]]:
    """Literal ``tr()``/``mark()`` strings of one Python source → locations.

    With ``docstrings_of``, also the first line of the docstring of every
    function or class decorated with one of those names -- bare
    (``@command``), called (``@command("x")``) or as an attribute
    (``@registry.command(...)``) -- for apps that show it as a summary.
    """
    names = set(functions)
    decorators = set(docstrings_of)
    tree = ast.parse(source, filename=filename)
    found: dict[Entry, list[tuple[str, int]]] = {}
    if decorators:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if not any(_decorator_name(d) in decorators for d in node.decorator_list):
                continue
            doc = ast.get_docstring(node)
            summary = doc.strip().splitlines()[0].strip() if doc and doc.strip() else ""
            if summary:
                found.setdefault((domain, summary), []).append((filename, node.lineno))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args or _callee(node.func) not in names:
            continue
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "self":
            continue  # Qt's QObject.tr resolves under the class context
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                and first.value.strip()):
            continue
        keywords = {k.arg: k.value for k in node.keywords if k.arg}
        named = keywords.get("domain")
        if isinstance(named, ast.Constant) and isinstance(named.value, str) \
                and named.value != domain:
            continue
        context = domain
        given = keywords.get("context")
        if given is None and len(node.args) > 1:
            given = node.args[1]
        if isinstance(given, ast.Constant) and isinstance(given.value, str) and given.value:
            context = given.value
        found.setdefault((context, first.value), []).append((filename, node.lineno))
    return found


# --------------------------------------------------------------------- json


def collect_json(data: object, out: set[str], text_keys: frozenset[str] = TEXT_KEYS) -> None:
    """Collect authored text of a spec; binding identities and hidden values stay out."""

    def text(value: object) -> None:
        if isinstance(value, str) and value.strip():
            out.add(value)
        elif isinstance(value, list):
            for item in value:
                text(item)
        elif isinstance(value, dict):
            for item in value.values():
                text(item)

    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("options", "choices"):
                if data.get("type") == "choice" and not data.get("labels") \
                        and isinstance(value, list):
                    for option in value:
                        # A (value, label) pair shows its second slot.
                        text(option[1] if isinstance(option, (list, tuple)) and len(option) == 2
                             else option)
            elif key in text_keys:
                if isinstance(value, (str, list)):
                    text(value)
            collect_json(value, out, text_keys)
    elif isinstance(data, list):
        for item in data:
            collect_json(item, out, text_keys)


def _is_spec(path: Path) -> bool:
    name = path.name
    return name.endswith("view.json") or name == "manifest.json" or (
        name.endswith(".json") and "guide" in name)


# --------------------------------------------------------------------- package


ExtraSpecs = Mapping[str, Iterable[str]]


def _read_json_spec(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ValueError(f"cannot extract from {path}: {error}") from error


def collect(package_dir: str | os.PathLike, domain: str, *,
            text_keys: frozenset[str] = TEXT_KEYS,
            extra_specs: ExtraSpecs | None = None,
            docstrings_of: Iterable[str] = ()) -> dict[Entry, list[tuple[str, int]]]:
    """Every translatable string of a package → its source locations.

    ``extra_specs`` declares an application's own JSON data files and which of
    their keys hold display text: ``{"ui/data/menus.json": ("label", "note"),
    "data/tours/*.json": ("say",)}`` -- glob patterns relative to
    ``package_dir`` (``**`` allowed), each matched file collected with exactly
    those keys (a key whose value is a list or object contributes every string
    inside it). ``docstrings_of`` names decorators whose functions' docstring
    summaries are collected (see :func:`collect_python`). A pattern that matches no file is an error: a renamed data
    file must not silently drop its strings from the catalogue.

    Raises ``ValueError`` on a Python file or spec that does not parse: a
    broken file must not silently shrink the catalogue.
    """
    root = Path(package_dir).resolve()
    found: dict[Entry, list[tuple[str, int]]] = {}
    for pattern, keys in (extra_specs or {}).items():
        matches = sorted(p for p in root.glob(pattern) if p.is_file())
        if not matches:
            raise ValueError(f"extra spec pattern {pattern!r} matches no file under {root}")
        keys = frozenset([keys] if isinstance(keys, str) else keys)
        for path in matches:
            strings: set[str] = set()
            collect_json(_read_json_spec(path), strings, keys)
            rel = path.relative_to(root.parent).as_posix()
            for text in sorted(strings):
                found.setdefault((domain, text), []).append((rel, 0))
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _shipped(path, root):
            continue
        rel = path.relative_to(root.parent).as_posix()
        if path.suffix == ".py":
            try:
                entries = collect_python(path.read_text(encoding="utf-8"), rel, domain,
                                         docstrings_of=docstrings_of)
            except (SyntaxError, UnicodeError) as error:
                raise ValueError(f"cannot extract from {path}: {error}") from error
            for key, locations in entries.items():
                found.setdefault(key, []).extend(locations)
        elif path.suffix == ".json" and _is_spec(path):
            data = _read_json_spec(path)
            strings: set[str] = set()
            collect_json(data, strings, text_keys)
            for text in sorted(strings):
                locations = found.setdefault((domain, text), [])
                if (rel, 0) not in locations:
                    locations.append((rel, 0))
    return found


def merge(existing: list[Message], extracted: dict[Entry, list[tuple[str, int]]]
          ) -> list[Message]:
    """Merge an extraction into a catalogue without losing a translation."""
    owned = {context for context, _ in extracted}
    by_key = {(m.context, m.source): m for m in existing}
    finished: dict[str, set[str]] = {}
    for m in existing:
        if m.translation and not m.numerus and m.status in ("", "obsolete", "vanished"):
            finished.setdefault(m.source, set()).add(m.translation)

    out: list[Message] = []
    for m in existing:
        key = (m.context, m.source)
        if key in extracted:
            if m.status in ("obsolete", "vanished"):
                m.status = "" if m.translation else "unfinished"
            m.locations = sorted(set(extracted[key]))
        elif m.context in owned and m.status not in ("obsolete", "vanished"):
            m.status = "obsolete"
        out.append(m)
    for key in sorted(k for k in extracted if k not in by_key):
        context, source = key
        choices = finished.get(source, set())
        text = next(iter(choices)) if len(choices) == 1 else ""
        out.append(Message(context, source, text, "" if text else "unfinished",
                           sorted(set(extracted[key]))))
    return out


def extract(package_dir: str | os.PathLike, domain: str, locales: Iterable[str],
            out: str | os.PathLike, *, fmt: str = "ts",
            extra_specs: ExtraSpecs | None = None,
            docstrings_of: Iterable[str] = ()) -> dict[str, Path]:
    """Collect ``package_dir`` and merge into ``<out>/<domain>_<lang>.<fmt>``.

    ``extra_specs`` and ``docstrings_of`` are passed to :func:`collect`. Returns the written path per
    locale.
    """
    extracted = collect(package_dir, domain, extra_specs=extra_specs,
                        docstrings_of=tuple(docstrings_of))
    written: dict[str, Path] = {}
    for code in locales:
        path = Path(out) / f"{domain}_{code}.{fmt}"
        language, existing = read_messages(path) if path.is_file() else (code, [])
        write_messages(path, merge(existing, extracted), language or code)
        written[code] = path
    return written


def parse_spec_args(values: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """``["ui/menus.json:label,note"]`` → ``{"ui/menus.json": ("label", "note")}``."""
    specs: dict[str, tuple[str, ...]] = {}
    for value in values:
        pattern, sep, keys = value.rpartition(":")
        names = tuple(k.strip() for k in keys.split(",") if k.strip())
        if not sep or not pattern or not names:
            raise ValueError(f"--spec expects GLOB:KEY1,KEY2, got {value!r}")
        specs[pattern] = tuple(dict.fromkeys(specs.get(pattern, ()) + names))
    return specs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emtk.i18n.extract",
                                     description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("package_dir")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--locales", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--format", choices=("ts", "json"), default="ts")
    parser.add_argument("--spec", action="append", default=[], metavar="GLOB:KEY1,KEY2",
                        help="an extra JSON data file (glob relative to package_dir) and the "
                             "keys holding its display text; repeatable")
    parser.add_argument("--docstrings", action="append", default=[], metavar="DECORATOR",
                        help="collect the docstring summary of functions decorated with "
                             "this name; repeatable")
    args = parser.parse_args(argv)
    try:
        extra = parse_spec_args(args.spec)
        written = extract(args.package_dir, args.domain, args.locales, args.out,
                          fmt=args.format, extra_specs=extra,
                          docstrings_of=args.docstrings)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for code, path in written.items():
        _, messages = read_messages(path)
        todo = sum(1 for m in messages if m.status == "unfinished")
        print(f"{code}: {path} ({len(messages)} messages, {todo} unfinished)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
