"""Immediate-mode Markdown rendering widget for EMTK.

Renders formatted Markdown documents directly into an EMTK layout with native
typography, heading font scaling, math expressions, inline codes and links,
images, tables, and admonition boxes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .. import im
from ..i18n import tr
from ..im_core import Col
from ..type_scale import math_args, pop_text_style, push_text_style

__all__ = ["MarkdownBlock", "parse_markdown", "render_markdown"]



@dataclass
class MarkdownBlock:
    """A block element within a Markdown document."""

    kind: str  # "h1", "h2", "h3", "h4", "p", "code", "admonition", "list_item", "hr", "math", "figure", "table", "quote"
    text: str = ""
    arg: str = ""
    items: list[str] = field(default_factory=list)


#: Line starts that open a block of their own, so they end a wrapped list item.
_BLOCK_STARTS = ("#", "|", ">", "```", "~~~", ":::", "$$", "![", ".. ")

_OPTION = re.compile(r"^[ \t]*:([\w-]+):\s*(.*)$")


def _split_directive_body(body_lines: list[str]) -> tuple[dict[str, str], str]:
    options: dict[str, str] = {}
    idx = 0
    while idx < len(body_lines):
        line = body_lines[idx]
        if not line.strip():
            idx += 1
            if options:
                break
            continue
        opt_match = _OPTION.match(line)
        if opt_match is None:
            break
        options[opt_match.group(1).lower()] = opt_match.group(2).strip()
        idx += 1
    caption = "\n".join(body_lines[idx:]).strip()
    return options, caption


def parse_markdown(raw_text: str) -> list[MarkdownBlock]:
    """Parse a Markdown / MyST text stream into structural blocks.

    Content that carries HTML mark-up (status pages built from ``<h3>`` and
    ``<table>`` fragments) is converted to the Markdown subset first, so
    callers can hand either format to :func:`render_markdown`.
    """
    from ..htmltext import html_to_markdown

    raw_text = html_to_markdown(raw_text)
    blocks: list[MarkdownBlock] = []
    lines = raw_text.splitlines()
    n = len(lines)
    i = 0

    # Strip YAML frontmatter
    if n > 1 and lines[0].strip() == "---":
        i = 1
        while i < n and lines[i].strip() != "---":
            i += 1
        if i < n:
            i += 1

    p_lines: list[str] = []

    def flush_p() -> None:
        nonlocal p_lines
        if p_lines:
            text = " ".join(line.strip() for line in p_lines if line.strip())
            if text:
                blocks.append(MarkdownBlock(kind="p", text=text))
            p_lines = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Target anchor: (anchor-id)=
        if re.match(r"^\([\w.-]+\)=\s*$", stripped):
            i += 1
            continue

        # MyST Directive Fence (```{directive} or ::: {directive})
        d_match = re.match(r"^(?P<fence>`{3,}|~{3,}|:{3,})\{(?P<name>[\w.-]+)\}\s*(?P<arg>.*)$", stripped)
        if d_match:
            flush_p()
            fence = d_match.group("fence")
            name = d_match.group("name").lower()
            arg = d_match.group("arg").strip()
            marker = fence[0]
            body_lines = []
            i += 1
            while i < n:
                sub = lines[i].strip()
                c_match = re.match(r"^(?P<fence>`{3,}|~{3,}|:{3,})\s*$", sub)
                if c_match and c_match.group("fence")[0] == marker and len(c_match.group("fence")) >= len(fence):
                    i += 1
                    break
                body_lines.append(lines[i])
                i += 1

            opts, body_text = _split_directive_body(body_lines)
            if name in ("figure", "image"):
                fig_arg = arg or opts.get("figure", "")
                blocks.append(
                    MarkdownBlock(
                        kind="figure",
                        text=body_text,
                        arg=fig_arg,
                        items=[opts.get("alt", ""), opts.get("width", "")],
                    )
                )
            elif name == "math":
                blocks.append(MarkdownBlock(kind="math", text="\n".join(body_lines).strip()))
            elif name in ("code-block", "code", "sourcecode"):
                blocks.append(MarkdownBlock(kind="code", text="\n".join(body_lines).rstrip(), arg=arg))
            elif name in (
                "note", "warning", "tip", "important", "caution", "danger",
                "error", "hint", "seealso", "admonition", "details", "dropdown",
            ):
                title = arg or opts.get("title", "") or name.capitalize()
                blocks.append(MarkdownBlock(kind="admonition", text=body_text, arg=name, items=[title]))
            elif name in ("toctree", "contents", "index", "meta", "raw", "only"):
                pass
            else:
                blocks.append(MarkdownBlock(kind="admonition", text=body_text, arg="note", items=[arg or name.capitalize()]))
            continue

        # RST Directive: .. name:: arg
        rst_match = re.match(r"^\.\.\s+([\w-]+)::\s*(.*)$", stripped)
        if rst_match:
            flush_p()
            name = rst_match.group(1).lower()
            arg = rst_match.group(2).strip()
            body_lines = []
            i += 1
            while i < n:
                cur_line = lines[i]
                if cur_line.strip() and not (cur_line.startswith(("   ", "\t")) or cur_line.startswith("..")):
                    break
                body_lines.append(cur_line.strip())
                i += 1

            opts, body_text = _split_directive_body(body_lines)
            if name in ("image", "figure"):
                blocks.append(
                    MarkdownBlock(
                        kind="figure",
                        text=body_text,
                        arg=arg,
                        items=[opts.get("alt", ""), opts.get("width", "")],
                    )
                )
            elif name == "math":
                blocks.append(MarkdownBlock(kind="math", text="\n".join(body_lines).strip()))
            elif name in ("code-block", "sourcecode"):
                blocks.append(MarkdownBlock(kind="code", text="\n".join(body_lines).rstrip(), arg=arg))
            elif name in ("note", "warning", "tip", "important", "seealso", "admonition"):
                blocks.append(MarkdownBlock(kind="admonition", text=body_text, arg=name, items=[name.capitalize()]))
            elif name in ("toctree", "contents", "index"):
                pass
            else:
                if body_text:
                    blocks.append(MarkdownBlock(kind="p", text=body_text))
            continue

        # Plain Code Fence (``` or ~~~)
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_p()
            code_lang = stripped.lstrip("`~").strip()
            marker = stripped[0]
            body_lines = []
            i += 1
            while i < n:
                sub = lines[i].strip()
                if sub.startswith(marker * 3) and all(c == marker for c in sub):
                    i += 1
                    break
                body_lines.append(lines[i])
                i += 1
            blocks.append(MarkdownBlock(kind="code", text="\n".join(body_lines), arg=code_lang))
            continue

        # Display math block: $$ ... $$
        if stripped.startswith("$$"):
            flush_p()
            if stripped.endswith("$$") and len(stripped) > 2:
                math_content = stripped[2:-2].strip()
                blocks.append(MarkdownBlock(kind="math", text=math_content))
                i += 1
                continue
            else:
                math_lines = [stripped.lstrip("$").strip()]
                i += 1
                while i < n and not lines[i].strip().endswith("$$"):
                    math_lines.append(lines[i].strip())
                    i += 1
                if i < n:
                    math_lines.append(lines[i].strip().rstrip("$").strip())
                    i += 1
                blocks.append(MarkdownBlock(kind="math", text="\n".join(math_lines).strip()))
                continue

        # Standard Markdown Image: ![alt](path)
        img_match = re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", stripped)
        if img_match:
            flush_p()
            blocks.append(
                MarkdownBlock(
                    kind="figure",
                    text="",
                    arg=img_match.group(2).strip(),
                    items=[img_match.group(1).strip(), ""],
                )
            )
            i += 1
            continue

        # GitHub style callout: > [!NOTE], > [!WARNING]
        if stripped.startswith("> [!"):
            flush_p()
            m = re.match(r"^>\s*\[!(\w+)\]\s*(.*)", stripped)
            adm_k = m.group(1).lower() if m else "note"
            adm_t = (m.group(2).strip() if m else "") or adm_k.capitalize()
            b_lines: list[str] = []
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                b_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(MarkdownBlock(kind="admonition", text=" ".join(b_lines), arg=adm_k, items=[adm_t]))
            continue

        # Regular blockquote
        if stripped.startswith(">"):
            flush_p()
            b_lines = [stripped.lstrip(">").strip()]
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                b_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(MarkdownBlock(kind="quote", text=" ".join(b_lines)))
            continue

        # Markdown table
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_p()
            table_rows: list[list[str]] = []
            aligns: list[str] = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                r_strip = lines[i].strip()
                cells = [c.strip() for c in r_strip.strip("|").split("|")]
                if all(re.match(r"^:?-+:?$", c) for c in cells):
                    # The delimiter row carries the column alignment (:--, :-:, --:).
                    aligns = [
                        "c" if c.startswith(":") and c.endswith(":")
                        else "r" if c.endswith(":") else "l"
                        for c in cells
                    ]
                else:
                    table_rows.append(cells)
                i += 1
            if table_rows:
                blocks.append(MarkdownBlock(kind="table", arg="".join(aligns),
                                            items=["\t".join(r) for r in table_rows]))
            continue

        # Headings (# H1, ## H2, ### H3, #### H4)
        if stripped.startswith("#"):
            flush_p()
            lvl = len(stripped) - len(stripped.lstrip("#"))
            h_title = stripped.lstrip("#").strip()
            h_title = re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", h_title).strip()
            blocks.append(MarkdownBlock(kind=f"h{min(lvl, 4)}", text=h_title))
            i += 1
            continue

        # RST Heading underline
        if i + 1 < n:
            next_strip = lines[i + 1].strip()
            if (
                stripped
                and len(next_strip) >= 3
                and all(c == next_strip[0] for c in next_strip)
                and next_strip[0] in ("=", "-", "~", "^", '"')
            ):
                flush_p()
                char = next_strip[0]
                kind = "h1" if char == "=" else ("h2" if char == "-" else "h3")
                blocks.append(MarkdownBlock(kind=kind, text=stripped))
                i += 2
                continue

        # Horizontal rule
        if stripped in ("---", "***", "___", "===="):
            flush_p()
            blocks.append(MarkdownBlock(kind="hr"))
            i += 1
            continue

        # List Items (- , * , + , or 1. , 2. )
        list_m = re.match(r"^([-*+]|\d+\.)\s+(.*)", stripped)
        if list_m:
            flush_p()
            item = [list_m.group(2).strip()]
            i += 1
            # A wrapped item continues on the following lines (indented or not, as Markdown's
            # lazy continuation allows) until a blank line or the start of another block; drawn
            # as its own paragraph, the second line read as a new item missing its marker.
            while i < n:
                nxt = lines[i].strip()
                if not nxt or re.match(r"^([-*+]|\d+\.)\s+", nxt) or nxt.startswith(_BLOCK_STARTS):
                    break
                item.append(nxt)
                i += 1
            blocks.append(MarkdownBlock(kind="list_item", text=" ".join(item), arg=list_m.group(1)))
            continue

        # Blank line
        if not stripped:
            flush_p()
            i += 1
            continue

        p_lines.append(line)
        i += 1

    flush_p()
    return blocks


def _format_inline_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Parse inline Markdown formatting into clean readable text and link tuples."""
    links: list[tuple[str, str]] = []

    # Markdown links: [label](url)
    def link_sub(m: re.Match) -> str:
        lbl, target = m.group(1), m.group(2)
        links.append((lbl, target))
        return lbl

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_sub, text)

    # Inline math: $expr$
    try:
        from ..mathtext import latex_to_unicode

        s = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", lambda m: latex_to_unicode(m.group(1).strip()), s)
    except Exception:
        pass

    # Inline code: `code`
    s = re.sub(r"`([^`]+)`", r" \1 ", s)

    # Bold: **bold** or __bold__
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)

    # Italic: *italic* or _italic_
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
    s = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", s)

    return s, links


def _link_row(links: list[tuple[str, str]], tag: str, on_link: Callable[[str], None] | None) -> None:
    """Draw ``links`` as a ``•``-separated row that wraps onto the next line instead of leaving the window.

    A row longer than the available width used to run on past the clip edge, where its last links could be
    neither seen nor clicked.
    """
    avail_w = im.get_content_region_avail()[0]
    gap = im.get_style().item_spacing[0]
    bullet_w = im.calc_text_size("•")[0] + 2.0 * gap
    used = 0.0
    for l_idx, (label, target) in enumerate(links):
        caption = f"↗ {label}"
        width = im.calc_text_size(caption)[0]
        if l_idx > 0:
            if used + bullet_w + width <= avail_w:
                im.same_line()
                im.text_disabled("•")
                im.same_line()
                used += bullet_w
            else:
                used = 0.0
        if im.text_link(f"{caption}##{tag}_{l_idx}"):
            if on_link:
                on_link(target)
        used += width


def _aligned_cell(text: str, align: str, colour) -> None:
    """Draw one table cell, shifted right or to the centre when it fits on a line.

    ``align`` is ``"l"``, ``"c"`` or ``"r"`` from the delimiter row. A cell wider
    than its column wraps, left aligned, as it always did.
    """
    avail = im.get_content_region_avail()[0]
    width = im.calc_text_size(text)[0]
    if align in ("c", "r") and width < avail:
        shift = (avail - width) * (0.5 if align == "c" else 1.0)
        im.set_cursor_pos_x(im.get_cursor_pos_x() + shift)
    if colour is not None:
        im.text_colored(colour, text)
    else:
        im.text_wrapped(text)


def render_markdown(
    content: str | list[MarkdownBlock],
    on_link: Callable[[str], None] | None = None,
    max_width: float | None = None,
) -> None:
    """Render Markdown blocks into the current EMTK layout with rich typography.

    Parameters
    ----------
    content : str or list of MarkdownBlock
        Markdown source string or pre-parsed blocks.
    on_link : callable, optional
        Callback invoked when a link is clicked: ``on_link(url)``.
    max_width : float, optional
        Layout width limit in pixels.
    """
    blocks = parse_markdown(content) if isinstance(content, str) else content
    if not blocks:
        return

    avail_w = max_width or im.get_content_region_avail()[0]

    for idx, block in enumerate(blocks):
        im.push_id(f"md_{idx}")

        if block.kind == "h1":
            im.dummy(0.0, 12.0)
            push_text_style("h1")
            im.text_colored((125, 205, 255, 255), block.text)
            pop_text_style()
            im.dummy(0.0, 2.0)
            im.separator()
            im.dummy(0.0, 6.0)

        elif block.kind == "h2":
            im.dummy(0.0, 10.0)
            push_text_style("h2")
            im.text_colored((145, 225, 160, 255), block.text)
            pop_text_style()
            im.dummy(0.0, 4.0)

        elif block.kind == "h3":
            im.dummy(0.0, 8.0)
            push_text_style("h3")
            im.text_colored((245, 205, 115, 255), block.text)
            pop_text_style()
            im.dummy(0.0, 3.0)

        elif block.kind == "h4":
            im.dummy(0.0, 6.0)
            push_text_style("h4")
            im.text_colored((220, 225, 235, 255), block.text)
            pop_text_style()
            im.dummy(0.0, 2.0)

        elif block.kind == "p":
            clean_text, links = _format_inline_text(block.text)
            push_text_style("body")
            im.text_wrapped(clean_text)
            pop_text_style()
            if links:
                im.dummy(0.0, 1.0)
                _link_row(links, f"plnk_{idx}", on_link)
            im.dummy(0.0, 4.0)

        elif block.kind == "math":
            im.dummy(0.0, 4.0)
            im.math(
                block.text,
                colour=(216, 222, 233, 255),
                **math_args("body"),
                align_center=True,
                max_width=max(50.0, avail_w - 28.0),
            )
            im.dummy(0.0, 4.0)

        elif block.kind == "figure":
            im.dummy(0.0, 6.0)
            pct = 1.0
            if block.items and len(block.items) > 1 and "%" in str(block.items[1]):
                try:
                    pct = float(str(block.items[1]).replace("%", "").strip()) / 100.0
                except ValueError:
                    pct = 1.0
            target_max_w = max(100.0, (avail_w - 28.0) * pct)
            w, h = im.image(
                block.arg,
                max_size=(target_max_w, 560.0),
                align_center=True,
            )
            if block.text:
                im.dummy(0.0, 2.0)
                caption, _ = _format_inline_text(block.text)
                push_text_style("caption")
                im.push_style_color(Col.TEXT, (175, 185, 200, 255))
                im.text_wrapped(tr("Figure: {caption}", domain="emtk").format(caption=caption))
                im.pop_style_color()
                pop_text_style()
            im.dummy(0.0, 6.0)

        elif block.kind == "code":
            im.dummy(0.0, 3.0)
            lang_label = f" [{block.arg}]" if block.arg else ""
            im.text_disabled(tr("Code", domain="emtk") + lang_label)
            im.same_line()
            if im.small_button(tr("Copy", domain="emtk") + f"##cp_{idx}"):
                try:
                    from ..clipboard import set_clipboard_text

                    set_clipboard_text(block.text)
                except Exception:
                    pass

            push_text_style("code")
            im.push_style_color(Col.FRAME_BG, (20, 24, 30, 255))
            im.text_wrapped(block.text)
            im.pop_style_color()
            pop_text_style()
            im.dummy(0.0, 4.0)

        elif block.kind in ("admonition", "quote"):
            adm_colors = {
                "note": (110, 190, 255, 255),
                "tip": (130, 220, 140, 255),
                "hint": (130, 220, 140, 255),
                "seealso": (110, 190, 255, 255),
                "warning": (235, 185, 95, 255),
                "caution": (235, 185, 95, 255),
                "danger": (245, 110, 110, 255),
                "error": (245, 110, 110, 255),
                "quote": (160, 175, 195, 255),
            }
            adm_color = adm_colors.get(block.arg, (110, 190, 255, 255))
            adm_title = block.items[0] if block.items else block.arg.capitalize()
            im.dummy(0.0, 2.0)
            push_text_style("body", bold=True)
            im.text_colored(adm_color, f"[{adm_title}]")
            pop_text_style()
            clean_body, adm_links = _format_inline_text(block.text)
            push_text_style("body")
            im.text_wrapped(clean_body)
            pop_text_style()
            if adm_links:
                im.dummy(0.0, 1.0)
                _link_row(adm_links, f"admlnk_{idx}", on_link)
            im.dummy(0.0, 4.0)

        elif block.kind == "table" and block.items:
            rows = [item.split("\t") for item in block.items]
            cols = max(len(r) for r in rows) if rows else 1
            im.dummy(0.0, 4.0)
            flags = (im.TableFlags.BORDERS | im.TableFlags.ROW_BG
                     | im.TableFlags.SIZING_STRETCH_PROP)
            if im.begin_table(f"tbl_{idx}", cols, flags):
                for r_idx, row in enumerate(rows):
                    im.table_next_row()
                    for c_idx in range(cols):
                        cell_text = row[c_idx] if c_idx < len(row) else ""
                        im.table_next_column()
                        clean_cell, _ = _format_inline_text(cell_text)
                        align = block.arg[c_idx] if c_idx < len(block.arg) else "l"
                        if r_idx == 0:
                            push_text_style("body", bold=True)
                            _aligned_cell(clean_cell, align, (140, 205, 255, 255))
                            pop_text_style()
                        else:
                            push_text_style("body")
                            _aligned_cell(clean_cell, align, None)
                            pop_text_style()
                im.end_table()
            im.dummy(0.0, 4.0)

        elif block.kind == "list_item":
            clean_item, item_links = _format_inline_text(block.text)
            bullet_sym = block.arg if block.arg and not block.arg.startswith(("-", "*", "+")) else "•"
            push_text_style("body")
            im.text_wrapped(f"  {bullet_sym}  {clean_item}")
            pop_text_style()
            if item_links:
                im.dummy(0.0, 1.0)
                _link_row(item_links, f"llnk_{idx}", on_link)
            im.dummy(0.0, 2.0)

        elif block.kind == "hr":
            im.dummy(0.0, 4.0)
            im.separator()
            im.dummy(0.0, 4.0)

        im.pop_id()
