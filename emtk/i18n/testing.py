"""A guard against display text that cannot reach a catalogue.

``im.button("Open")`` renders, and is even translated at runtime when some
catalogue happens to hold "Open" -- but no extractor can see it, so it never
gets a catalogue entry of its own. :func:`untranslated_literals` finds such
literals statically (no import of the scanned code) so each repository can
pin them with a test::

    from emtk.i18n.testing import untranslated_literals

    def test_no_untranslated_literals():
        assert untranslated_literals("mypackage") == []

or, while a backlog is paid down, compare against a shrinking allow-list
of :attr:`Literal.key` values.
"""
from __future__ import annotations

import ast
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DEFAULT_KEYWORDS", "DEFAULT_SINKS", "Literal", "literals_in_source",
           "untranslated_literals"]

#: Widget calls whose positional argument (index) is shown to the user.
DEFAULT_SINKS: Mapping[str, int] = {
    "text": 0, "text_wrapped": 0, "text_disabled": 0, "text_colored": 1, "bullet_text": 0,
    "label_text": 0, "separator_text": 0, "button": 0, "small_button": 0, "checkbox": 0,
    "radio_button": 0, "selectable": 0, "menu_item": 0, "begin_menu": 0,
    "collapsing_header": 0, "tree_node": 0, "begin_tab_item": 0, "tab_item_button": 0,
    "set_item_tooltip": 0, "set_tooltip": 0, "progress_bar": 2,
}

#: Keyword arguments of any sink call that are shown to the user.
DEFAULT_KEYWORDS = frozenset({"hint", "tooltip", "overlay", "description"})

#: Receivers a sink is recognised on; import aliases of ``emtk.im`` are added.
DEFAULT_RECEIVERS = frozenset({"im", "emtk.im", "_w", "_im", "imgui"})

#: Sinks recognised on any receiver (and as bare names): the tooltip setters.
ANY_RECEIVER = frozenset({"set_item_tooltip", "set_tooltip"})

_SKIP_PARTS = frozenset({"test", "tests", "__pycache__", ".git", "node_modules"})


@dataclass(frozen=True)
class Literal:
    """One display literal that bypasses ``tr()``."""

    path: str
    line: int
    column: int
    call: str
    text: str

    @property
    def key(self) -> str:
        """A stable allow-list key: path, call position and the text."""
        return f"{self.path}:{self.line}:{self.column}:{self.call}:{self.text}"


def _dotted(node: ast.expr) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _literal_text(value: ast.expr) -> str | None:
    """The authored text of a display literal, or ``None`` when it is not one.

    A plain string counts when its visible part (before ``##``) has a letter.
    An f-string counts when its constant parts do; it is reported with its
    placeholders spelled out (``f"Loaded {n} files"`` → ``Loaded {n} files``),
    which is also the source to translate: ``tr("Loaded {n} files").format(n=n)``.
    """
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        shown = value.value.split("##", 1)[0]
        return value.value if any(ch.isalpha() for ch in shown) else None
    if isinstance(value, ast.JoinedStr):
        text, constant = [], []
        for part in value.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                text.append(part.value)
                constant.append(part.value)
            elif isinstance(part, ast.FormattedValue):
                text.append("{" + ast.unparse(part.value) + "}")
        shown = "".join(constant).split("##", 1)[0]
        return "".join(text) if any(ch.isalpha() for ch in shown) else None
    return None


def literals_in_source(source: str, path: str, *, sinks: Mapping[str, int] = DEFAULT_SINKS,
                       keywords: Iterable[str] = DEFAULT_KEYWORDS,
                       receivers: Iterable[str] = DEFAULT_RECEIVERS) -> list[Literal]:
    """Display literals at widget sinks of one Python source.

    A ``SyntaxError`` propagates: a file that does not parse must fail the
    guard rather than silently count as clean.
    """
    tree = ast.parse(source, filename=path)
    receivers = set(receivers)
    keywords = set(keywords)
    direct: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "emtk.im":
                    receivers.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if node.module in ("emtk", "emtk.widgets") and alias.name == "im" \
                        or (node.module or "").endswith("im_widgets") and alias.name == "*":
                    receivers.add(alias.asname or alias.name)
                elif node.module in ("emtk.im", "emtk.im_widgets") and alias.name in sinks:
                    direct[alias.asname or alias.name] = alias.name
    found: list[Literal] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        prefix, _, method = name.rpartition(".")
        if name in direct:
            method = direct[name]
        elif method in ANY_RECEIVER:
            pass
        elif prefix not in receivers:
            continue
        if method not in sinks:
            continue
        values: list[ast.expr] = []
        position = sinks[method]
        if len(node.args) > position:
            values.append(node.args[position])
        values.extend(k.value for k in node.keywords if k.arg in keywords)
        for value in values:
            text = _literal_text(value)
            if text is not None:
                found.append(Literal(path, node.lineno, node.col_offset, method, text))
    return found


def untranslated_literals(package_dir: str | os.PathLike, *,
                          sinks: Mapping[str, int] = DEFAULT_SINKS,
                          keywords: Iterable[str] = DEFAULT_KEYWORDS,
                          receivers: Iterable[str] = DEFAULT_RECEIVERS,
                          exclude: Iterable[str] = ()) -> list[Literal]:
    """Every display literal at a widget sink in a package's shipped Python.

    Tests (``test``/``tests`` directories, ``test_*.py``) are skipped, as are
    paths containing any ``exclude`` substring. ``path`` in each result is
    relative to the package's parent directory, so keys are stable across
    checkouts. A literal wrapped in ``tr()``/``mark()`` is a call, not a
    literal, and is never reported; nor are hidden ids (``"##id"``) and text
    without a letter (``"…"``, ``"123"``). An f-string with prose is a
    literal too (reported with its ``{…}`` placeholders): translate the
    template and format after, ``tr("Loaded {n} files").format(n=n)``, which
    :mod:`emtk.i18n.extract` collects.
    """
    root = Path(package_dir).resolve()
    exclude = tuple(exclude)
    found: list[Literal] = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if any(p in _SKIP_PARTS for p in parts[:-1]) or path.name.startswith("test_"):
            continue
        rel = path.relative_to(root.parent).as_posix()
        if any(token in rel for token in exclude):
            continue
        found.extend(literals_in_source(path.read_text(encoding="utf-8"), rel, sinks=sinks,
                                        keywords=keywords, receivers=receivers))
    return found
