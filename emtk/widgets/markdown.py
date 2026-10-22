"""Immediate-mode Markdown rendering widget for EMTK.

Renders formatted Markdown documents directly into an EMTK layout with native
typography, heading font scaling, math expressions, inline codes and links,
images, tables, and admonition boxes.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Callable

from .. import im
from .. import style as _style
from ..i18n import tr
from ..im_core import Col
from ..type_scale import math_args, pop_text_style, push_text_style, text_font

__all__ = ["InlineRun", "MarkdownBlock", "draw_inline", "parse_inline", "parse_markdown", "render_markdown"]



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


_MERMAID_HEADER = re.compile(r"^(?:graph|flowchart)\s+(TD|TB|LR|RL)\s*$", re.I)
_MERMAID_NODE = re.compile(r"^([A-Za-z_][\w]*)(?:\[+([^\]]*)\]+|\(\(+([^\)]*)\)\+|\{+([^}]*)\}+)?$")
def _parse_mermaid(text: str):
    """Parse the small Mermaid subset the record layouts use: ``graph TD`` with
    ``A[Label] --> B``, ``A -.label.-> B`` and ``A -->|label| B`` edges.

    Returns ``(nodes, edges)`` -- ``nodes`` is ``[(id, label, shape)]`` in
    first-seen order, ``edges`` is ``[(src_id, dst_id, style, label)]`` with
    style ``"solid" | "dotted" | "thick"`` -- or ``None`` when the text uses
    anything outside that subset (the caller falls back to a code block).
    """
    raw = [ln for ln in text.splitlines()]
    lines: list[str] = []
    for ln in raw:
        ln = ln.strip()
        if not ln:
            continue
        # html_to_markdown turns a <br/> inside a quoted node label into a real
        # line break; re-join the pieces before parsing.
        if lines and lines[-1].count('"') % 2 == 1 and '["' in lines[-1]:
            lines[-1] += " " + ln
        else:
            lines.append(ln)
    if not lines or not _MERMAID_HEADER.match(lines[0]):
        return None
    nodes: list[tuple[str, str, str]] = []
    by_id: dict[str, tuple[str, str, str]] = {}

    def seen(nid: str, label: str, shape: str) -> None:
        if nid not in by_id:
            by_id[nid] = (nid, label or nid, shape)
            nodes.append(by_id[nid])
        elif label:
            by_id[nid] = (nid, label, shape)

    def node_of(token: str) -> tuple[str, str, str] | None:
        m = _MERMAID_NODE.match(token.strip())
        if m is None:
            return None
        nid, square, round_, brace = m.group(1), m.group(2), m.group(3), m.group(4)
        label = (square or round_ or brace or "").strip().strip('"').replace("<br/>", "\n").replace("<br>", "\n")
        shape = "box" if square else ("round" if round_ else ("diamond" if brace else "box"))
        return nid, label, shape

    edge_re = re.compile(
        r"^\s*(?P<a>[A-Za-z_]\w*)\s*(?P<as>\[[^\]]*\]|\([^)]*\))*\s*"
        r"(?:(?P<arrow>-->|==>)|(?P<darrow>-\.\s*(?P<dlab>.*?)\s*\.->)|(?P<larrow>-{3}))\s*"
        r"(?:\|(?P<elabel>[^|]*)\|\s*)?"
        r"(?P<b>[A-Za-z_]\w*)\s*(?P<bs>\[[^\]]*\]|\([^)]*\))*\s*$")
    edges: list[tuple[str, str, str, str]] = []
    for ln in lines[1:]:
        m = edge_re.match(ln)
        if m is not None:
            a, b = node_of(m.group("a") + (m.group("as") or "")), node_of(m.group("b") + (m.group("bs") or ""))
            if a is None or b is None:
                return None
            arrow = m.group("arrow") or m.group("darrow") or m.group("larrow")
            style = ("dotted" if m.group("darrow") else
                     "thick" if m.group("arrow") == "==>" else "solid")
            elabel = (m.group("dlab") or m.group("elabel") or "").strip()
            seen(*a)
            seen(*b)
            edges.append((a[0], b[0], style, elabel))
            continue
        n = node_of(ln)
        if n is None:
            return None
        seen(*n)
    if not edges:
        return None
    return [by_id[n[0]] for n in nodes], edges


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
            body = "\n".join(body_lines)
            if code_lang.lower() == "mermaid" and _parse_mermaid(body) is not None:
                blocks.append(MarkdownBlock(kind="mermaid", text=body))
            else:
                blocks.append(MarkdownBlock(kind="code", text=body, arg=code_lang))
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

    s = re.sub(r"\[([^\]]+)\]\(((?:[^()]|\([^()]*\))+)\)", link_sub, text)

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


_INLINE = re.compile(
    # 1,2 link; the target may hold one level of parentheses (a DOI such as 10.1016/S0006-3495(79)85271-6)
    r"\[([^\]]+)\]\(((?:[^()]|\([^()]*\))+)\)"
    r"|`([^`]+)`"                            # 3 code
    r"|\*\*(.+?)\*\*"                       # 4 bold
    r"|__(.+?)__"                            # 5 bold
    r"|(?<![*\w])\*([^*\s][^*]*?)\*(?!\*)"   # 6 italic
    r"|(?<![_\w])_([^_\s][^_]*?)_(?!\w)"    # 7 italic
    r"|(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)"  # 8 math
)


@dataclass(frozen=True)
class InlineRun:
    """One styled stretch of inline text: ``bold``/``italic``/``code`` and an optional link ``target``."""

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    target: str = ""


def parse_inline(text: str, _bold=False, _italic=False, _target="") -> list[InlineRun]:
    """Split inline Markdown into styled runs (links, ``code``, bold, italic, ``$math$``)."""
    runs: list[InlineRun] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            runs.append(InlineRun(text[pos : m.start()], _bold, _italic, False, _target))
        pos = m.end()
        if m.group(1) is not None:
            runs.extend(parse_inline(m.group(1), _bold, _italic, m.group(2).strip()))
        elif m.group(3) is not None:
            runs.append(InlineRun(m.group(3), _bold, _italic, True, _target))
        elif m.group(4) is not None or m.group(5) is not None:
            runs.extend(parse_inline(m.group(4) or m.group(5), True, _italic, _target))
        elif m.group(6) is not None or m.group(7) is not None:
            runs.extend(parse_inline(m.group(6) or m.group(7), _bold, True, _target))
        else:
            try:
                from ..mathtext import latex_to_unicode

                body = latex_to_unicode(m.group(8).strip())
            except Exception:
                body = m.group(8)
            runs.append(InlineRun(body, _bold, _italic, False, _target))
    if pos < len(text):
        runs.append(InlineRun(text[pos:], _bold, _italic, False, _target))
    return runs


def _atoms(runs: list[InlineRun]) -> list[list[InlineRun]]:
    """Words as lists of run pieces (a word keeps its pieces together); a space is ``[InlineRun(" ")]``."""
    atoms: list[list[InlineRun]] = []
    current: list[InlineRun] = []
    for run in runs:
        for tok in re.findall(r"[ \t\n]+|[^ \t\n]+", run.text):
            piece = dataclasses.replace(run, text=" " if tok[0] in " \t\n" else tok)
            if tok[0] in " \t\n":
                if current:
                    atoms.append(current)
                    current = []
                atoms.append([piece])
            else:
                current.append(piece)
    if current:
        atoms.append(current)
    return atoms


_CODE_FACE: dict[str, bool] = {}


def _code_face_available() -> bool:
    """Whether the configured monospace face can be rendered here (else code spans use the prose face)."""
    from ..type_scale import text_font

    try:
        font = text_font("code")
        key = str(font.get("family"))
        if key not in _CODE_FACE:
            from ..font_render import FontSpec, text_width

            try:
                text_width(FontSpec(key, font["size"], False, False), "ab", 1.0)
                _CODE_FACE[key] = True
            except (ValueError, TypeError):
                _CODE_FACE[key] = False
        return _CODE_FACE[key]
    except Exception:
        return False


def _frame_face(ctx, role: str, bold: bool, zoom: float) -> dict:
    """``text_font(role, bold, zoom)``, resolved once per frame (it validates the face each call).

    The font settings cannot change inside a frame, so a page of paragraphs shares the answer.
    """
    store = ctx.state(("markdown_faces",))
    frame = ctx.io.frame_count
    if store.get("frame") != frame:
        store.clear()
        store["frame"] = frame
    key = (role, bool(bold), float(zoom))
    if key not in store:
        store[key] = text_font(role, bold=bold, zoom=zoom)
    return store[key]


#: Wrapped paragraph layouts of :func:`draw_inline`, least recently used first.
_LAYOUTS: dict = {}
_LAYOUT_CAP = 4096


def _layout_inline(ctx, text, prefix, avail, code_face, font_for, face):
    """Wrap one paragraph: ``(lines, line_h, max_w)``, or ``None`` when it has no runs.

    Each line is a list of ``(x, run, width)``. Words of one face are measured under one
    font push, not one push per word.
    """
    from ..im_widgets import pop_font, push_font

    runs = parse_inline(text)
    if prefix:
        runs.insert(0, InlineRun(prefix))
    if not runs:
        return None
    cache: dict = {}

    def warm(pieces) -> None:
        """Measure every not-yet-measured piece, one font push per face."""
        todo: dict = {}
        for run in pieces:
            k = (run.text, run.bold, run.code)
            if k not in cache:
                todo.setdefault(font_for(run), {})[k] = run.text
        for fk, items in todo.items():
            push_font(face(fk))
            try:
                h = ctx.p.line_height()
                for k, t in items.items():
                    cache[k] = (ctx.p.text_width(t), h)
            finally:
                pop_font()

    def measure(run: InlineRun) -> tuple[float, float]:
        k = (run.text, run.bold, run.code)
        if k not in cache:
            warm([run])
        return cache[k]

    pad = 2.0  # horizontal padding of a code span
    lines: list[list[tuple[float, InlineRun, float]]] = [[]]
    x = 0.0
    line_h = 0.0
    def _hard_break(atom):
        """Split a word wider than the line into line-sized chunks (as plain wrapping does)."""
        out: list[list[InlineRun]] = [[]]
        used = 0.0
        for r in atom:
            buf = ""
            for ch in r.text:
                cw = measure(dataclasses.replace(r, text=ch))[0] + (2 * pad if r.code and code_face else 0.0)
                if used + cw > avail and (buf or out[-1] or used > 0.0):
                    if buf:
                        out[-1].append(dataclasses.replace(r, text=buf))
                        buf = ""
                    out.append([])
                    used = 0.0
                buf += ch
                used += cw
            if buf:
                out[-1].append(dataclasses.replace(r, text=buf))
        return out

    atoms: list[list[InlineRun]] = []
    words = _atoms(runs)
    warm([r for atom in words for r in atom])
    for atom in words:
        probe = sum(measure(r)[0] + (2 * pad if r.code and r.text != " " else 0.0) for r in atom)
        if probe > avail and not (len(atom) == 1 and atom[0].text == " "):
            chunks = _hard_break(atom)
            for k, chunk in enumerate(chunks):
                if chunk:
                    atoms.append(chunk)
                    if k < len(chunks) - 1:
                        atoms.append([InlineRun("\n")])
        else:
            atoms.append(atom)
    for atom in atoms:
        if len(atom) == 1 and atom[0].text == "\n":
            if lines[-1]:
                lines.append([])
            x = 0.0
            continue
        widths = [measure(r)[0] + (2 * pad if r.code and r.text != " " else 0.0) for r in atom]
        for r in atom:
            line_h = max(line_h, measure(r)[1])
        w = sum(widths)
        is_space = atom[0].text == " " and len(atom) == 1
        if is_space:
            if x == 0.0 and not lines[-1]:
                continue
            lines[-1].append((x, atom[0], widths[0]))
            x += w
            continue
        if x > 0.0 and x + w > avail:
            while lines[-1] and lines[-1][-1][1].text == " ":
                lines[-1].pop()
            lines.append([])
            x = 0.0
        for r, rw in zip(atom, widths):
            lines[-1].append((x, r, rw))
            x += rw
    return lines, line_h, max((seg[0] + seg[2] for ln in lines for seg in ln), default=0.0)


def draw_inline(
    text: str,
    on_link: Callable[[str], None] | None = None,
    tag: str = "inl",
    role: str = "body",
    colour=None,
    bold: bool = False,
    prefix: str = "",
    zoom: float = 1.0,
) -> None:
    """Draw one wrapped paragraph of inline Markdown as rich-text runs.

    Links are drawn where they sit in the text (coloured, underlined, clickable);
    bold uses the bold face, code the monospace face on a subtle background. A
    word is never split, even when it spans several runs (``**a**,``).
    """
    from ..im_core import get_current_context
    from ..im_widgets import _col, pop_font, push_font

    ctx = get_current_context()
    code_face = _code_face_available()
    avail = max(1.0, float(ctx.layout.avail()[0]))
    faces: dict[tuple[str, bool], dict] = {}

    def font_for(run: InlineRun):
        if run.code and code_face:
            return "code", False
        return role, bool(bold or run.bold)

    def face(key: tuple[str, bool]) -> dict:
        if key not in faces:
            faces[key] = _frame_face(ctx, key[0], key[1], zoom)
        return faces[key]

    # The wrapped layout depends only on the text, the width and the faces, so it is kept across
    # frames: a long page re-measured every word in every frame (a 340-paragraph bibliography
    # took seconds per frame). The faces in the key carry every font setting and the zoom.
    scale = ctx.state(("font_scale",)).get("current", 1.0)
    key = (
        text, prefix, role, bool(bold), float(zoom), round(avail, 1), code_face, float(scale),
        type(ctx.p).__name__,
        repr([face((role, b)) for b in (bool(bold), True)]),
        repr(face(("code", False))) if code_face else None,
    )
    layout = _LAYOUTS.get(key)
    if layout is None:
        layout = _layout_inline(ctx, text, prefix, avail, code_face, font_for, face)
        if len(_LAYOUTS) >= _LAYOUT_CAP:
            _LAYOUTS.pop(next(iter(_LAYOUTS)))
        _LAYOUTS[key] = layout
    else:
        _LAYOUTS[key] = _LAYOUTS.pop(key)  # most recently used last
    if layout is None:
        return
    lines, line_h, max_w = layout
    line_h = max(line_h, ctx.p.line_height())
    pad = 2.0  # horizontal padding of a code span
    box = ctx.layout.row(height=len(lines) * line_h, width=min(avail, max(max_w, 1.0)))
    ctx.item_add(box)
    if not ctx._overlaps_clip(box):
        return  # scrolled out of view: the box holds its place, nothing to paint or click
    base = colour if colour is not None else _col(Col.TEXT)
    link_col = _col(Col.CHECK_MARK)
    for li, raw in enumerate(lines):
        y = box[1] + li * line_h
        ln: list[tuple[float, InlineRun, float]] = []
        for sx, run, rw in raw:  # one string per styled stretch, spaces inside it included
            if ln and not run.code:
                px, prun, pw = ln[-1]
                if (prun.bold, prun.italic, prun.code, prun.target) == (
                    run.bold, run.italic, run.code, run.target,
                ) and abs(px + pw - sx) < 1e-6:
                    ln[-1] = (px, dataclasses.replace(prun, text=prun.text + run.text), pw + rw)
                    continue
            ln.append((sx, run, rw))
        for si, (sx, run, rw) in enumerate(ln):
            if run.text.strip() == "" and not run.target:
                continue
            x0 = box[0] + sx
            hovered = False
            if run.target:
                hit = (x0, y, rw, line_h)
                hovered, _held, pressed = ctx.button_behavior(hit, ctx.get_id(f"{tag}_{li}_{si}"))
                if hovered:
                    ctx.set_tooltip(run.target)
                if pressed and on_link:
                    on_link(run.target)
            if run.code:
                ctx.draw.add_rect_filled((x0, y + 1), (x0 + rw, y + line_h - 1), _style.CODE_INLINE_BG, 3.0)
            fr, fb = font_for(run)
            push_font(face((fr, fb)))
            if run.target:
                col = tuple(min(255, int(c) + 40) for c in link_col[:3]) + tuple(link_col[3:]) if hovered else link_col
            elif run.italic:
                col = tuple(int(c * 0.82) for c in base[:3]) + tuple(base[3:])
            else:
                col = base
            ctx.draw.add_text((x0 + (pad if run.code else 0.0), y), col, run.text, bold=fb)
            pop_font()
            if run.target:
                ctx.draw.add_line((x0, y + line_h - 1.0), (x0 + rw, y + line_h - 1.0), col, 1.0)


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


def _wrap_label(label: str, width: float) -> list[str]:
    """Greedy word wrap for a node label at ``width`` px (uses the live font)."""
    out: list[str] = []
    for para in label.split("\n"):
        line = ""
        for word in para.split():
            cand = f"{line} {word}".strip()
            if line and im.calc_text_size(cand)[0] > width:
                out.append(line)
                line = word
            else:
                line = cand
        out.append(line)
    return out or [""]


def _draw_mermaid(block: MarkdownBlock, avail_w: float) -> bool:
    """Draw a parsed Mermaid ``graph TD`` as boxes and arrows.

    Returns ``False`` when the text is not in the supported subset, so the
    caller can fall back to rendering the source as a code block.
    """
    parsed = _parse_mermaid(block.text)
    if parsed is None:
        return False
    nodes, edges = parsed
    label_of = {n[0]: n[1] for n in nodes}
    depth = {n[0]: 0 for n in nodes}
    for _ in range(len(nodes)):
        for s, d, _st, _l in edges:
            depth[d] = max(depth[d], depth[s] + 1)
    levels: dict[int, list[str]] = {}
    for n in nodes:
        levels.setdefault(depth[n[0]], []).append(n[0])

    pad, gap_x, gap_y, line_h = 7.0, 10.0, 30.0, 15.0
    cols = max(1, int((avail_w + gap_x) / (130.0 + gap_x)))
    node_w = min(230.0, (avail_w - (cols - 1) * gap_x) / cols)
    dl = im.get_window_draw_list()
    ox, oy = im.get_cursor_screen_pos()

    boxes: dict[str, tuple[tuple[float, float], tuple[float, float], list[str]]] = {}
    y = oy + 2.0
    for lvl in sorted(levels):
        row = levels[lvl]
        for k0 in range(0, len(row), cols):
            chunk = row[k0:k0 + cols]
            row_h = 0.0
            for k, nid in enumerate(chunk):
                lines = _wrap_label(label_of.get(nid, nid), node_w - 2 * pad)
                h = 2 * pad + len(lines) * line_h
                x = ox + k * (node_w + gap_x)
                boxes[nid] = ((x, y), (x + node_w, y + h), lines)
                row_h = max(row_h, h)
            y += row_h + gap_y

    for nid, ((x0, y0), (x1, y1), lines) in boxes.items():
        dl.add_rect_filled((x0, y0), (x1, y1), _style.CODE_BG, rounding=4.0)
        dl.add_rect((x0, y0), (x1, y1), _style.FRAME_BG, rounding=4.0)
        for j, ln in enumerate(lines):
            dl.add_text((x0 + pad, y0 + pad + j * line_h), _style.TEXT, ln)

    for s, d, st, elabel in edges:
        if s not in boxes or d not in boxes:
            continue
        (sx0, sy0), (sx1, sy1), _ = boxes[s]
        (dx0, dy0), (dx1, dy1), _ = boxes[d]
        s_mid, d_mid = ((sx0 + sx1) / 2.0, sy1), ((dx0 + dx1) / 2.0, dy0)
        col = _style.TEXT_DISABLED if st == "dotted" else (110, 110, 120, 255)
        dl.add_bezier_cubic(s_mid, (s_mid[0], s_mid[1] + gap_y * 0.5),
                            (d_mid[0], d_mid[1] - gap_y * 0.5), (d_mid[0], d_mid[1] + 7.0),
                            col, thickness=1.4 if st != "dotted" else 1.0)
        dl.add_triangle_filled((d_mid[0] - 4.0, d_mid[1]), (d_mid[0] + 4.0, d_mid[1]),
                               (d_mid[0], d_mid[1] + 7.0), col)
        if elabel:
            lx = (s_mid[0] + d_mid[0]) / 2.0
            ly = (s_mid[1] + d_mid[1]) / 2.0 - 8.0
            dl.add_text((lx - im.calc_text_size(elabel)[0] / 2.0, ly), col, elabel)

    total_h = y - oy - gap_y + 8.0
    im.dummy(0.0, max(total_h, 10.0))
    return True


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
            im.text_colored(_style.HEADING_1, block.text)
            pop_text_style()
            im.dummy(0.0, 2.0)
            im.separator()
            im.dummy(0.0, 6.0)

        elif block.kind == "h2":
            im.dummy(0.0, 10.0)
            push_text_style("h2")
            im.text_colored(_style.HEADING_2, block.text)
            pop_text_style()
            im.dummy(0.0, 4.0)

        elif block.kind == "h3":
            im.dummy(0.0, 8.0)
            push_text_style("h3")
            im.text_colored(_style.HEADING_3, block.text)
            pop_text_style()
            im.dummy(0.0, 3.0)

        elif block.kind == "h4":
            im.dummy(0.0, 6.0)
            push_text_style("h4")
            im.text_colored(_style.HEADING_4, block.text)
            pop_text_style()
            im.dummy(0.0, 2.0)

        elif block.kind == "p":
            draw_inline(block.text, on_link, f"p{idx}")
            im.dummy(0.0, 4.0)

        elif block.kind == "math":
            im.dummy(0.0, 4.0)
            im.math(
                block.text,
                colour=_style.TEXT,
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
                im.push_style_color(Col.TEXT, _style.TEXT_QUOTE)
                im.text_wrapped(tr("Figure: {caption}", domain="emtk").format(caption=caption))
                im.pop_style_color()
                pop_text_style()
            im.dummy(0.0, 6.0)

        elif block.kind == "code" or (block.kind == "mermaid"
                                      and not _draw_mermaid(block, avail_w)):
            im.dummy(0.0, 3.0)
            lang_label = f" [{block.arg}]" if block.arg else ""
            if block.kind == "mermaid":
                lang_label = " [mermaid]"
                block = MarkdownBlock(kind="code", text=block.text, arg="mermaid")
            im.text_disabled(tr("Code", domain="emtk") + lang_label)
            im.same_line()
            if im.small_button(tr("Copy", domain="emtk") + f"##cp_{idx}"):
                try:
                    from ..clipboard import set_clipboard_text

                    set_clipboard_text(block.text)
                except Exception:
                    pass

            push_text_style("code")
            im.push_style_color(Col.FRAME_BG, _style.CODE_BG)
            im.text_wrapped(block.text)
            im.pop_style_color()
            pop_text_style()
            im.dummy(0.0, 4.0)

        elif block.kind in ("admonition", "quote"):
            adm_colors = {
                "note": _style.TEXT_NOTE,
                "tip": _style.TEXT_TIP,
                "hint": _style.TEXT_TIP,
                "seealso": _style.TEXT_NOTE,
                "warning": _style.TEXT_WARNING,
                "caution": _style.TEXT_WARNING,
                "danger": _style.TEXT_DANGER,
                "error": _style.TEXT_DANGER,
                "quote": _style.TEXT_QUOTE,
            }
            adm_color = adm_colors.get(block.arg, _style.TEXT_NOTE)
            adm_title = block.items[0] if block.items else block.arg.capitalize()
            im.dummy(0.0, 2.0)
            push_text_style("body", bold=True)
            im.text_colored(adm_color, f"[{adm_title}]")
            pop_text_style()
            draw_inline(block.text, on_link, f"adm{idx}")
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
                        align = block.arg[c_idx] if c_idx < len(block.arg) else "l"
                        if align == "l":
                            draw_inline(
                                cell_text, on_link, f"c{idx}_{r_idx}_{c_idx}",
                                colour=_style.HEADING_1 if r_idx == 0 else None,
                                bold=r_idx == 0,
                            )
                            continue
                        clean_cell, _ = _format_inline_text(cell_text)
                        if r_idx == 0:
                            push_text_style("body", bold=True)
                            _aligned_cell(clean_cell, align, _style.HEADING_1)
                            pop_text_style()
                        else:
                            push_text_style("body")
                            _aligned_cell(clean_cell, align, None)
                            pop_text_style()
                im.end_table()
            im.dummy(0.0, 4.0)

        elif block.kind == "list_item":
            bullet_sym = block.arg if block.arg and not block.arg.startswith(("-", "*", "+")) else "•"
            draw_inline(block.text, on_link, f"li{idx}", prefix=f"  {bullet_sym}  ")
            im.dummy(0.0, 2.0)

        elif block.kind == "hr":
            im.dummy(0.0, 4.0)
            im.separator()
            im.dummy(0.0, 4.0)

        im.pop_id()
