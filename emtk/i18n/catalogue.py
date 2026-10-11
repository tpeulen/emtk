"""Read and write translation catalogues without Qt.

Two formats:

* **Qt Linguist ``.ts`` XML** -- what Qt's ``lupdate``/``linguist`` read and
  write, so an existing catalogue (and a translator's tool) keeps working.
  ``unfinished`` translations are not used at runtime, ``obsolete`` and
  ``vanished`` ones never are, and plural (``numerus``) messages are skipped
  rather than concatenated.
* **JSON** -- ``{"source": "translation"}``, or contexts as nested objects
  ``{"context": {"source": "translation"}}``, optionally wrapped as
  ``{"language": "de", "messages": {...}}``. An empty translation is
  unfinished; ``"obsolete"`` holds retired entries the extractor kept.

:class:`Message` is the full record the extractor merges; :func:`read_catalogue`
is the runtime view (finished translations only).
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Message", "read_catalogue", "read_messages", "write_messages"]

DEFAULT_CONTEXT = "default"


@dataclass
class Message:
    """One catalogue entry.

    ``status`` is ``""`` (finished), ``"unfinished"``, ``"obsolete"`` or
    ``"vanished"``. ``element`` keeps the parsed ``.ts`` element so a rewrite
    preserves what this module does not model (comments, plurals, extra
    attributes).
    """

    context: str
    source: str
    translation: str = ""
    status: str = "unfinished"
    locations: list[tuple[str, int]] = field(default_factory=list)
    numerus: bool = False
    element: ET.Element | None = field(default=None, repr=False, compare=False)


# --------------------------------------------------------------------- reading


def read_catalogue(path: str | os.PathLike) -> dict[str, dict[str, str]]:
    """Return ``{context: {source: translation}}`` of the finished translations."""
    out: dict[str, dict[str, str]] = {}
    for message in read_messages(path)[1]:
        if message.status or message.numerus or not message.translation:
            continue
        out.setdefault(message.context, {})[message.source] = message.translation
    return out


def read_messages(path: str | os.PathLike) -> tuple[str | None, list[Message]]:
    """Return ``(language, messages)`` of a ``.ts`` or ``.json`` catalogue."""
    path = Path(path)
    if path.suffix == ".json":
        return _read_json(path)
    return _read_ts(path)


def _read_ts(path: Path) -> tuple[str | None, list[Message]]:
    root = ET.parse(path).getroot()
    messages: list[Message] = []
    for context in root.findall("context"):
        name = context.findtext("name") or DEFAULT_CONTEXT
        for element in context.findall("message"):
            source = element.findtext("source")
            if not source:
                continue
            translation = element.find("translation")
            numerus = element.get("numerus") == "yes" or (
                translation is not None and translation.find("numerusform") is not None)
            status = "unfinished" if translation is None else (translation.get("type") or "")
            text = "" if translation is None or numerus else "".join(translation.itertext())
            locations = [(loc.get("filename", ""), int(loc.get("line") or 0))
                         for loc in element.findall("location")]
            messages.append(Message(name, source, text, status, locations, numerus, element))
    return root.get("language"), messages


def _read_json(path: Path) -> tuple[str | None, list[Message]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    language = None
    obsolete: dict = {}
    if isinstance(data, dict) and isinstance(data.get("messages"), dict):
        language = data.get("language")
        obsolete = data.get("obsolete") or {}
        data = data["messages"]
    messages: list[Message] = []

    def walk(table: dict, status_for_empty: str, status: str | None) -> None:
        for key, value in table.items():
            if isinstance(value, str):
                messages.append(Message(DEFAULT_CONTEXT, key, value,
                                        status if status is not None
                                        else ("" if value else status_for_empty)))
            elif isinstance(value, dict):
                for source, text in value.items():
                    if isinstance(text, str):
                        messages.append(Message(key, source, text,
                                                status if status is not None
                                                else ("" if text else status_for_empty)))

    if isinstance(data, dict):
        walk(data, "unfinished", None)
    if isinstance(obsolete, dict):
        walk(obsolete, "obsolete", "obsolete")
    return language, messages


# --------------------------------------------------------------------- writing


def write_messages(path: str | os.PathLike, messages: list[Message],
                   language: str | None = None) -> None:
    """Write ``messages`` as a ``.ts`` or ``.json`` catalogue (by suffix)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        _write_json(path, messages, language)
    else:
        _write_ts(path, messages, language)


def _write_json(path: Path, messages: list[Message], language: str | None) -> None:
    live: dict[str, dict[str, str]] = {}
    gone: dict[str, dict[str, str]] = {}
    for m in messages:
        target = gone if m.status in ("obsolete", "vanished") else live
        target.setdefault(m.context, {})[m.source] = m.translation if m.status != "unfinished" \
            else (m.translation or "")
    payload: dict = {"language": language, "messages": live}
    if gone:
        payload["obsolete"] = gone
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_ts(path: Path, messages: list[Message], language: str | None) -> None:
    root = ET.Element("TS", {"version": "2.1"})
    if language:
        root.set("language", language)
    contexts: dict[str, ET.Element] = {}
    for m in messages:
        context = contexts.get(m.context)
        if context is None:
            context = contexts[m.context] = ET.SubElement(root, "context")
            ET.SubElement(context, "name").text = m.context
        if m.element is not None and m.numerus:
            # Plurals are not modelled: carry the element through unchanged
            # apart from the status the merge decided.
            element = m.element
            translation = element.find("translation")
            if translation is not None:
                if m.status:
                    translation.set("type", m.status)
                else:
                    translation.attrib.pop("type", None)
            context.append(element)
            continue
        element = ET.SubElement(context, "message")
        for filename, line in m.locations:
            ET.SubElement(element, "location", {"filename": filename, "line": str(line)})
        ET.SubElement(element, "source").text = m.source
        if m.element is not None:
            # Translator comments and extra fields survive a rewrite.
            for child in m.element:
                if child.tag in ("comment", "extracomment", "translatorcomment", "oldsource"):
                    element.append(child)
        translation = ET.SubElement(element, "translation")
        if m.status:
            translation.set("type", m.status)
        translation.text = m.translation or None
    ET.indent(root, space="    ")
    content = ET.tostring(root, encoding="unicode")
    # Qt keeps significant trailing blanks; ElementTree's indent would not care.
    content = re.sub(r" +(?=\n)", lambda match: "&#32;" * len(match[0]), content)
    path.write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n' + content + "\n",
                    encoding="utf-8")
