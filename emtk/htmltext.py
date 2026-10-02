"""HTML fragment → Markdown conversion for rich-text rendering.

Plugins that already produce HTML (status pages built from ``<h3>`` and
``<table>`` fragments, doc pages, ``<b>`` warnings) used to hand those strings
to :func:`emtk.im.markdown`, which drew the tags as literal text. This module
converts a conservative HTML subset into the Markdown the renderer understands
— headings, pipe tables, bold/italic/code, links, lists and paragraphs — using
only the standard library.

The subset is deliberately conservative: it recognises the structural tags
above and *strips* everything else (including inline ``style`` attributes and
unknown elements), so unknown HTML degrades to readable text instead of
mark-up noise. It is a rendering fallback, not a browser.
"""

from __future__ import annotations

import html as _html
import re

__all__ = ["html_to_markdown", "looks_like_html"]

_LOOKS_LIKE_HTML = re.compile(
    r"<(/?)(?:h[1-6]|p|br|b|strong|i|em|code|pre|li|ul|ol"
    r"|table|tr|t[hd]|div|span|a|hr)(?=[\s/>])",
    re.IGNORECASE,
)
_STYLE_OR_SCRIPT = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_TABLE = re.compile(r"<table\b[^>]*>(.*?)</table\s*>", re.IGNORECASE | re.DOTALL)
_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr\s*>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]\s*>", re.IGNORECASE | re.DOTALL)
_HEADING = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1\s*>", re.IGNORECASE | re.DOTALL)
_LINK = re.compile(r"<a\b[^>]*href\s*=\s*[\"']([^\"']*)[\"'][^>]*>(.*?)</a\s*>",
                   re.IGNORECASE | re.DOTALL)
_LINE_BREAK = re.compile(r"<br\s*/?\s*>", re.IGNORECASE)
_LIST_ITEM = re.compile(r"<li\b[^>]*>", re.IGNORECASE)
_RULE = re.compile(r"<hr\s*/?\s*>", re.IGNORECASE)
_PARA = re.compile(r"<p\b[^>]*>|</p\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"\n{3,}")


def looks_like_html(text: str) -> bool:
    """Whether *text* carries HTML mark-up worth converting."""
    return bool(text) and bool(_LOOKS_LIKE_HTML.search(text))


def _cells(row_html: str) -> list[str]:
    return [_inline(_CELL_CLEAN.sub("", c)) for c in _CELL.findall(row_html)]


_CELL_CLEAN = _TAG


def _inline(fragment: str) -> str:
    """Convert inline mark-up in *fragment* and strip leftover tags."""
    fragment = _LINK.sub(lambda m: f"[{_stripped(m.group(2))}]({m.group(1)})", fragment)
    fragment = re.sub(r"<(b|strong)\b[^>]*>", "**", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"</(b|strong)\s*>", "**", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<(i|em)\b[^>]*>", "*", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"</(i|em)\s*>", "*", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<code\b[^>]*>", "`", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"</code\s*>", "`", fragment, flags=re.IGNORECASE)
    fragment = _LINE_BREAK.sub("\n", fragment)
    return _stripped(fragment)


def _stripped(fragment: str) -> str:
    """Strip remaining tags and decode entities, collapsing whitespace."""
    text = _TAG.sub("", fragment)
    text = _html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _table_to_markdown(table_html: str) -> str:
    rows = [_cells(r) for r in _ROW.findall(table_html)]
    rows = [r for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head = "| " + " | ".join(rows[0]) + " |"
    rule = "|" + "|".join("---" for _ in range(width)) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([head, rule, *body])


def html_to_markdown(text: str) -> str:
    """Convert an HTML fragment to the Markdown subset the renderer supports."""
    if not looks_like_html(text):
        return text
    text = _STYLE_OR_SCRIPT.sub("", text)
    text = _HEADING.sub(
        lambda m: "\n\n" + "#" * int(m.group(1)) + " " + _inline(m.group(2)) + "\n\n",
        text,
    )
    text = _TABLE.sub(lambda m: "\n\n" + _table_to_markdown(m.group(1)) + "\n\n", text)
    text = _LINK.sub(lambda m: f"[{_inline(m.group(2))}]({m.group(1)})", text)
    text = _LINE_BREAK.sub("\n", text)
    text = _LIST_ITEM.sub("\n- ", text)
    text = _RULE.sub("\n\n---\n\n", text)
    text = _PARA.sub("\n\n", text)
    text = _inline(text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()
