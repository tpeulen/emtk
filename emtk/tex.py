"""A small TeX math typesetter: LaTeX in, positioned glyphs and rules out.

emtk draws the formulas of help pages, model equations and expression
previews. This is the engine behind :func:`emtk.mathtext.render_math_to_texture`:
it parses the LaTeX subset those formulas use, lays it out the way TeX lays
out a math list -- boxes with a width, a height above the baseline and a
depth below it -- and draws the result into an RGBA texture with FreeType
glyphs (Pillow), no plotting library involved.

What it knows: groups, ``^`` and ``_`` (stacked when both), ``\\frac``
``\\dfrac`` ``\\tfrac`` ``\\binom``, ``\\sqrt`` with an optional index, the
Greek and symbol commands of :data:`emtk.mathtext._GREEK_AND_SYMBOLS`,
``\\left``/``\\right`` delimiters grown to their contents (``\\big`` and
friends too), ``\\sum`` ``\\prod`` ``\\int``-style big operators with limits,
``\\mathrm`` ``\\mathit`` ``\\mathbf`` ``\\text`` ``\\operatorname``, the
function names (``\\exp`` ``\\ln`` ``\\sin`` ...) upright, accents
(``\\hat`` ``\\bar`` ``\\vec`` ``\\dot`` ``\\ddot`` ``\\tilde`` ``\\overline``
``\\underline``), and TeX's spacing (``\\,`` ``\\;`` ``\\quad`` ... and the
thin/medium/thick space TeX puts around operators and relations).

What it does not: environments, matrices, ``\\over``-style infix commands,
macros. The help viewer rewrites those into this subset before calling
(:func:`chisurf.plugins.core.help.api.mathtext.normalise_latex`), as it did
for the engine this replaces.

Fonts: a serif text face (upright and italic) and a math face for symbols,
the first of :data:`TEXT_FAMILIES` / :data:`MATH_FAMILIES` the system has. A
character the chosen face lacks is taken from the next face that has it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

__all__ = ["Layout", "TexError", "render_rgba", "typeset"]

#: Text faces, in preference order; each needs an upright and an italic style.
TEXT_FAMILIES = ("STIX Two Text", "STIXGeneral", "Times New Roman", "Times", "DejaVu Serif",
                 "Liberation Serif", "Noto Serif", "Georgia")
#: Sans text faces (``sans=True``): a formula that has to match a sans
#: interface font, as inline maths does on a help page.
SANS_FAMILIES = ("Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans", "Liberation Sans",
                 "Noto Sans", "Segoe UI")
#: Faces tried for symbols the text face lacks.
MATH_FAMILIES = ("STIX Two Math", "STIXGeneral", "DejaVu Sans", "Apple Symbols",
                 "Arial Unicode MS", "Noto Sans Math", "Cambria Math")

#: Size of a style relative to the text size: display, text, script, scriptscript.
_STYLE_SCALE = (1.0, 1.0, 0.7, 0.5)
_D, _T, _S, _SS = range(4)

_FUNCTIONS = {"exp", "log", "ln", "lg", "sin", "cos", "tan", "cot", "sec", "csc", "sinh",
              "cosh", "tanh", "coth", "arcsin", "arccos", "arctan", "max", "min", "sup", "inf",
              "lim", "limsup", "liminf", "det", "dim", "ker", "deg", "arg", "gcd", "Pr", "erf",
              "erfc", "sgn", "tr", "diag", "mod"}
_LIMIT_FUNCTIONS = {"lim", "max", "min", "sup", "inf", "limsup", "liminf", "det", "Pr", "gcd"}
_BIG_OPS = {"sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫",
            "iint": "∬", "iiint": "∭", "oint": "∮", "bigcup": "⋃",
            "bigcap": "⋂", "bigoplus": "⨁", "bigotimes": "⨂"}
_INTEGRALS = {"int", "iint", "iiint", "oint"}
_ACCENTS = {"hat": "ˆ", "widehat": "ˆ", "bar": "¯", "vec": "→",
            "dot": "˙", "ddot": "¨", "tilde": "˜", "widetilde": "˜",
            "acute": "´", "grave": "`", "check": "ˇ", "breve": "˘"}
_FONTS = {"mathrm": "rm", "rm": "rm", "textrm": "rm", "text": "text", "mbox": "text",
          "textup": "rm", "mathup": "rm", "operatorname": "rm", "mathit": "it", "textit": "it",
          "mathbf": "bf", "textbf": "bf", "bf": "bf", "boldsymbol": "bfit", "bm": "bfit",
          "mathsf": "rm", "mathtt": "rm", "mathcal": "cal", "mathbb": "bb", "mathscr": "cal",
          "mathfrak": "frak", "emph": "it"}
_SPACES = {",": 3 / 18, ":": 4 / 18, ">": 4 / 18, ";": 5 / 18, "!": -3 / 18, " ": 1 / 4,
           "quad": 1.0, "qquad": 2.0, "enspace": 0.5, "thinspace": 3 / 18}
_DELIMS = {"(": "(", ")": ")", "[": "[", "]": "]", "\\{": "{", "\\}": "}", "|": "|",
           "\\|": "‖", "\\lbrace": "{", "\\rbrace": "}", "\\langle": "⟨",
           "\\rangle": "⟩", "\\lvert": "|", "\\rvert": "|", "\\lVert": "‖",
           "\\rVert": "‖", "\\lfloor": "⌊", "\\rfloor": "⌋",
           "\\lceil": "⌈", "\\rceil": "⌉", "/": "/", ".": "", "<": "⟨",
           ">": "⟩", "\\vert": "|", "\\Vert": "‖"}
_BIG = {"big": 1.2, "Big": 1.8, "bigg": 2.4, "Bigg": 3.0}
#: Binary operators and relations by character (TeX's medium and thick spaces).
_BIN = set("+−±∓×÷·∘∙⋅∗⊕⊗⊙"
           "∧∨∩∪∖⋆")
_REL = set("=<>≤≥≠≈≡∼≃≅∝≪≫∈"
           "∉∋⊂⊆⊃⊇∥⊥→←⇒⇐"
           "↔⇔↦↑↓:≔≲≳⟹⟸⟺⟶⟵⟼⇌⇋")


class TexError(ValueError):
    """The formula is outside the subset this typesetter reads."""


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=2)
def _families(sans: bool = False):
    from .font_render import _faces

    faces = _faces()
    text = next((f for f in (SANS_FAMILIES if sans else TEXT_FAMILIES)
                 if f in faces and any(x.italic for x in faces[f])
                 and any(not x.italic and not x.bold for x in faces[f])), None)
    if text is None:
        text = next((f for f, styles in faces.items()
                     if any(x.italic for x in styles) and not any(x.mono for x in styles)), None)
    symbols = [f for f in MATH_FAMILIES if f in faces]
    if text is None:
        raise TexError("no serif face with an italic style is installed")
    return text, tuple(symbols)


def _face_path(family: str, italic: bool, bold: bool):
    from .font_render import _faces

    styles = _faces()[family]
    for want in ((italic, bold), (italic, False), (False, bold), (False, False)):
        for face in styles:
            if face.italic == want[0] and face.bold == want[1]:
                return face
    return styles[0]


@lru_cache(maxsize=256)
def _font(family: str, italic: bool, bold: bool, px: int):
    from .font_render import _loaded

    return _loaded(_face_path(family, italic, bold), max(1, px))


@lru_cache(maxsize=4096)
def _has_glyph(family: str, italic: bool, bold: bool, ch: str) -> bool:
    """Whether the face draws *ch* itself rather than its missing-glyph box."""
    font = _font(family, italic, bold, 48)
    if ch.isspace():
        return True
    try:
        mask = bytes(font.getmask(ch))
    except Exception:  # noqa: BLE001 - a face Pillow cannot shape counts as missing
        return False
    missing = bytes(font.getmask("\U0010fffd"))
    return bool(mask.strip(b"\x00")) and mask != missing


@lru_cache(maxsize=8192)
def _ink(family: str, italic: bool, bold: bool, px: int, ch: str):
    """Tight ink box ``(left, top, right, bottom)`` of *ch* about its origin on
    the baseline. Pillow's ``getbbox`` clamps the bottom to the baseline for a
    glyph drawn wholly above it (an accent), which floated accents a glyph
    height too high; the rendered mask does not."""
    font = _font(family, italic, bold, px)
    if ch.isspace():
        return 0.0, 0.0, float(font.getlength(ch)), 0.0
    mask, (ox, oy) = font.getmask2(ch, anchor="ls")
    box = mask.getbbox()
    if box is None:
        return 0.0, 0.0, 0.0, 0.0
    x0, y0, x1, y1 = box
    return float(ox + x0), float(oy + y0), float(ox + x1), float(oy + y1)


#: Unicode's mathematical alphabets: ``(capital A, small a)`` of each, and the
#: letters that live in Letterlike Symbols instead (the "holes").
_ALPHABETS = {
    "cal": (0x1D49C, None, {"B": "\u212c", "E": "\u2130", "F": "\u2131", "H": "\u210b",
                            "I": "\u2110", "L": "\u2112", "M": "\u2133", "R": "\u211b"}),
    "bb": (0x1D538, 0x1D552, {"C": "\u2102", "H": "\u210d", "N": "\u2115", "P": "\u2119",
                              "Q": "\u211a", "R": "\u211d", "Z": "\u2124"}),
    "frak": (0x1D504, 0x1D51E, {"C": "\u212d", "H": "\u210c", "I": "\u2111", "R": "\u211c",
                                "Z": "\u2128"}),
}


def _alphabet(ch: str, variant: str) -> str:
    """*ch* in the script, double-struck or fraktur alphabet, where there is one."""
    caps, small, holes = _ALPHABETS[variant]
    if ch in holes:
        return holes[ch]
    if "A" <= ch <= "Z":
        return chr(caps + ord(ch) - 65)
    if small is not None and "a" <= ch <= "z":
        return chr(small + ord(ch) - 97)
    if variant == "bb" and ch.isdigit():
        return chr(0x1D7D8 + int(ch))
    return ch


@lru_cache(maxsize=2)
def _bold_family(sans: bool = False) -> str:
    """The text face, or the first one that has a bold style if it has none
    (STIX Two Text ships upright and italic only)."""
    from .font_render import _faces

    faces = _faces()
    text = _families(sans)[0]
    if any(f.bold for f in faces[text]):
        return text
    return next((f for f in (SANS_FAMILIES if sans else TEXT_FAMILIES)
                 if f in faces and any(x.bold for x in faces[f])), text)


def _pick(ch: str, variant: str, sans: bool = False):
    """``(family, italic, bold)`` that draws *ch* in *variant* (rm/it/bf/bfit)."""
    text, symbols = _families(sans)
    italic = variant in ("it", "bfit")
    bold = variant in ("bf", "bfit")
    if bold:
        text = _bold_family(sans)
    if _has_glyph(text, italic, bold, ch):
        return text, italic, bold
    for family in symbols:
        if _has_glyph(family, False, bold, ch):
            return family, False, bold
    return text, italic, bold


# --------------------------------------------------------------------------- #
# Boxes
# --------------------------------------------------------------------------- #
@dataclass
class Box:
    """A laid-out piece: ``width``, ``height`` above and ``depth`` below the baseline.

    ``items`` are drawing operations relative to the box's own origin (its
    left end, on its baseline, y growing downwards).
    """

    width: float = 0.0
    height: float = 0.0
    depth: float = 0.0
    items: list = field(default_factory=list)
    kind: str = "ord"     # ord / op / bin / rel / open / close / punct / inner
    italic_corr: float = 0.0
    #: Horizontal ink extent and the ink's signed bottom (negative: above the
    #: baseline) -- what an accent is centred on and rests on.
    ink: tuple = (0.0, 0.0)
    ink_bottom: float = 0.0

    def shifted(self, dx: float, dy: float) -> list:
        out = []
        for item in self.items:
            tag = item[0]
            if tag == "glyph":
                _, x, y, *rest = item
                out.append(("glyph", x + dx, y + dy, *rest))
            elif tag == "rule":
                _, x0, y0, x1, y1 = item
                out.append(("rule", x0 + dx, y0 + dy, x1 + dx, y1 + dy))
            elif tag == "poly":
                _, pts, w = item
                out.append(("poly", [(px + dx, py + dy) for px, py in pts], w))
        return out


def _hbox(boxes: list[Box], kind: str = "ord") -> Box:
    out = Box(kind=kind)
    x = 0.0
    for b in boxes:
        out.items.extend(b.shifted(x, 0.0))
        x += b.width
        out.height = max(out.height, b.height)
        out.depth = max(out.depth, b.depth)
    out.width = x
    if boxes:
        out.italic_corr = boxes[-1].italic_corr
        first = next((b for b in boxes if b.kind != "kern"), boxes[0])
        offset = sum(b.width for b in boxes[:-1])
        out.ink = (first.ink[0], offset + boxes[-1].ink[1]) if len(boxes) > 1 else boxes[0].ink
        if len(boxes) == 1:
            out.ink_bottom = boxes[0].ink_bottom
    return out


def _kern(w: float) -> Box:
    return Box(width=w, kind="kern")


@dataclass
class _Ctx:
    size: float        # pixels of the text size (style "text")
    style: int = _T
    variant: str = "it"  # default math letters
    sans: bool = False

    @property
    def px(self) -> float:
        return self.size * _STYLE_SCALE[self.style]

    def at(self, style: int) -> "_Ctx":
        return _Ctx(self.size, style, self.variant, self.sans)

    def with_variant(self, variant: str) -> "_Ctx":
        return _Ctx(self.size, self.style, variant, self.sans)

    @property
    def sup_style(self) -> int:
        return {_D: _S, _T: _S, _S: _SS, _SS: _SS}[self.style]

    @property
    def frac_style(self) -> int:
        return {_D: _T, _T: _S, _S: _SS, _SS: _SS}[self.style]


def _glyph(ch: str, ctx: _Ctx, variant: Optional[str] = None, scale: float = 1.0) -> Box:
    variant = variant or ctx.variant
    family, italic, bold = _pick(ch, variant, ctx.sans)
    px = max(1, int(round(ctx.px * scale)))
    font = _font(family, italic, bold, px)
    left, top, right, bottom = _ink(family, italic, bold, px, ch)
    adv = float(font.getlength(ch))
    box = Box(width=adv, height=float(max(-top, 0)), depth=float(max(bottom, 0)),
              items=[("glyph", 0.0, 0.0, ch, family, italic, bold, px)],
              ink=(float(left), float(right)), ink_bottom=float(bottom))
    # The overhang of an italic letter past its advance: TeX's italic
    # correction, used before an upright superscript or a closing glyph.
    box.italic_corr = max(0.0, right - adv) if italic else 0.0
    if ch in _BIN:
        box.kind = "bin"
    elif ch in _REL:
        box.kind = "rel"
    elif ch in "([{⟨⌊⌈":
        box.kind = "open"
    elif ch in ")]}⟩⌋⌉":
        box.kind = "close"
    elif ch in ",;":
        box.kind = "punct"
    return box


def _text_run(text: str, ctx: _Ctx, variant: str) -> Box:
    """Upright (or *variant*) text as one run, spaces kept."""
    boxes = []
    for ch in text:
        if ch == " ":
            boxes.append(_kern(ctx.px * 0.25))
        else:
            b = _glyph(ch, ctx, variant)
            b.kind = "ord"
            boxes.append(b)
    return _hbox(boxes)


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def _tokens(src: str) -> list[str]:
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            j = i + 1
            if j < n and src[j].isalpha():
                while j < n and src[j].isalpha():
                    j += 1
                out.append(src[i:j])
                i = j
            else:
                out.append(src[i:j + 1])
                i = j + 1
        else:
            out.append(c)
            i += 1
    return out


class _Parser:
    def __init__(self, src: str) -> None:
        self.toks = _tokens(src)
        self.i = 0

    def peek(self) -> Optional[str]:
        while self.i < len(self.toks) and self.toks[self.i] in (" ", "\t", "\n"):
            self.i += 1
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> Optional[str]:
        t = self.peek()
        if t is not None:
            self.i += 1
        return t

    def raw_group(self) -> str:
        """The raw text of the next ``{...}`` (or single token), for ``\\text``."""
        t = self.take()
        if t != "{":
            return t or ""
        depth, parts = 1, []
        while self.i < len(self.toks):
            t = self.toks[self.i]
            self.i += 1
            if t == "{":
                depth += 1
            elif t == "}":
                depth -= 1
                if depth == 0:
                    break
            parts.append(t)
        return "".join(parts)

    def optional(self) -> Optional[list]:
        if self.peek() != "[":
            return None
        self.take()
        out = []
        while self.peek() not in (None, "]"):
            out.append(self.atom())
        self.take()
        return out

    def argument(self) -> list:
        """The next group or single atom, as a list of nodes."""
        t = self.peek()
        if t is None:
            raise TexError("an argument is missing")
        if t == "{":
            self.take()
            nodes = self.until("}")
            self.take()
            return nodes
        return [self.atom()]

    def until(self, end: Optional[str]) -> list:
        nodes = []
        while True:
            t = self.peek()
            if t is None or t == end:
                return nodes
            if t == "\\right" and end == "\\right":
                return nodes
            if t in ("^", "_"):
                self.take()
                base = nodes.pop() if nodes else ("empty",)
                arg = self.argument()
                sup = sub = None
                if base[0] == "scripts" and base[3 if t == "^" else 2] is None:
                    _, b, sub, sup = base
                    base = b
                if t == "^":
                    sup = arg
                else:
                    sub = arg
                # A following script attaches to the same base.
                nxt = self.peek()
                if nxt in ("^", "_") and ((nxt == "^" and sup is None) or (nxt == "_" and sub is None)):
                    self.take()
                    arg2 = self.argument()
                    if nxt == "^":
                        sup = arg2
                    else:
                        sub = arg2
                nodes.append(("scripts", base, sub, sup))
                continue
            if t == "'":
                self.take()
                primes = "′"
                while self.peek() == "'":
                    self.take()
                    primes += "′"
                base = nodes.pop() if nodes else ("empty",)
                nodes.append(("scripts", base, None, [("char", primes, "rm")]))
                continue
            nodes.append(self.atom())

    def atom(self):
        from .mathtext import _GREEK_AND_SYMBOLS

        t = self.take()
        if t is None:
            raise TexError("unexpected end")
        if t == "{":
            nodes = self.until("}")
            self.take()
            return ("group", nodes)
        if t == "}":
            raise TexError("unbalanced '}'")
        if not t.startswith("\\"):
            if t.isdigit() or t == ".":
                return ("char", t, "rm")
            if t.isalpha():
                return ("char", t, None)
            mapped = {"-": "−", "*": "∗"}.get(t, t)
            return ("char", mapped, "rm")
        name = t[1:]
        if name in _SPACES:
            return ("space", _SPACES[name])
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            num, den = self.argument(), self.argument()
            return ("frac", num, den, {"dfrac": _D, "tfrac": _T}.get(name), True)
        if name == "binom":
            num, den = self.argument(), self.argument()
            return ("delim", "(", [("frac", num, den, None, False)], ")", None)
        if name == "sqrt":
            index = self.optional()
            return ("sqrt", self.argument(), index)
        if name == "left":
            open_ = self._delim()
            body = self.until("\\right")
            if self.peek() == "\\right":
                self.take()
                close = self._delim()
            else:
                close = ""
            return ("delim", open_, body, close, None)
        if name in ("right", "middle"):
            self._delim()
            return ("group", [])
        if name in _BIG or name.rstrip("lrm") in _BIG:
            d = self._delim()
            return ("bigdelim", d, _BIG.get(name, _BIG.get(name.rstrip("lrm"), 1.2)))
        if name in _BIG_OPS:
            limits = name not in _INTEGRALS
            if self.peek() in ("\\limits", "\\nolimits"):
                limits = self.take() == "\\limits"
            return ("bigop", _BIG_OPS[name], limits, name in _INTEGRALS)
        if name in _FUNCTIONS:
            return ("func", name, name in _LIMIT_FUNCTIONS)
        if name == "operatorname":
            return ("func", self.raw_group().replace(" ", ""), False)
        if name in _FONTS:
            variant = _FONTS[name]
            if variant == "text":
                return ("text", self.raw_group(), "rm")
            return ("font", variant, self.argument())
        if name in _ACCENTS:
            return ("accent", _ACCENTS[name], self.argument())
        if name in ("overline", "underline"):
            return ("line", name == "overline", self.argument())
        if name in ("underset", "overset", "stackrel"):
            mark, body = self.argument(), self.argument()
            if name == "underset":
                return ("stack", body, mark, None)
            return ("stack", body, None, mark)
        if name == "bmod":
            return ("func", "mod", False)
        if name == "pmod":
            return ("group", [("space", 1.0), ("char", "(", "rm"), ("func", "mod", False),
                              ("space", 3 / 18), ("group", self.argument()),
                              ("char", ")", "rm")])
        if name in ("displaystyle", "textstyle", "scriptstyle", "limits", "nolimits"):
            return ("group", [])
        if name in ("left.", "right."):
            return ("group", [])
        if t in _GREEK_AND_SYMBOLS:
            ch = _GREEK_AND_SYMBOLS[t]
            # Lowercase Greek is italic in maths, capitals upright (TeX).
            variant = None if ("α" <= ch <= "ω" or ch in "ϑϕϖϱϵ") else "rm"
            return ("char", ch, variant)
        extra = {"\\{": "{", "\\}": "}", "\\%": "%", "\\$": "$", "\\#": "#", "\\&": "&",
                 "\\_": "_", "\\|": "‖", "\\ldots": "…", "\\cdots": "⋯",
                 "\\dots": "…", "\\vdots": "⋮", "\\ddots": "⋱",
                 "\\prime": "′", "\\degree": "°", "\\ell": "ℓ",
                 "\\hbar": "ℏ", "\\infty": "∞", "\\partial": "∂",
                 "\\nabla": "∇", "\\colon": ":", "\\lbrace": "{", "\\rbrace": "}",
                 "\\langle": "⟨", "\\rangle": "⟩", "\\mid": "|", "\\vert": "|",
                 "\\gtrsim": "≳", "\\lesssim": "≲", "\\top": "⊤", "\\bot": "⊥",
                 "\\Longrightarrow": "⟹", "\\Longleftarrow": "⟸",
                 "\\Longleftrightarrow": "⟺", "\\longrightarrow": "⟶",
                 "\\longleftarrow": "⟵", "\\longmapsto": "⟼",
                 "\\rightleftharpoons": "⇌", "\\leftrightharpoons": "⇋",
                 "\\iff": "⟺", "\\implies": "⟹", "\\impliedby": "⟸"}
        if t in extra:
            return ("char", extra[t], "rm")
        raise TexError(f"unknown command {t}")

    def _delim(self) -> str:
        t = self.take()
        if t is None:
            raise TexError("a delimiter is missing")
        if t in _DELIMS:
            return _DELIMS[t]
        from .mathtext import _GREEK_AND_SYMBOLS

        return _GREEK_AND_SYMBOLS.get(t, t)


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def _axis(ctx: _Ctx) -> float:
    """Height of the math axis (fraction bars, operator centres) above the baseline."""
    return 0.25 * ctx.px


def _rule(ctx: _Ctx) -> float:
    return max(1.0, 0.05 * ctx.size * _STYLE_SCALE[min(ctx.style, _S)])


def _layout_list(nodes: list, ctx: _Ctx) -> Box:
    boxes = [_layout(n, ctx) for n in nodes]
    # TeX's inter-atom spacing, simplified: a binary operator after something
    # that cannot be its left operand is an ordinary symbol (a leading minus).
    spaced: list[Box] = []
    prev = None
    for i, b in enumerate(boxes):
        kind = b.kind
        if kind == "bin" and (prev in (None, "bin", "rel", "open", "op", "punct")):
            kind = "ord"
            b.kind = "ord"
        if kind == "bin" and (i + 1 == len(boxes) or boxes[i + 1].kind in ("rel", "close", "punct")):
            kind = "ord"
            b.kind = "ord"
        if prev is not None and ctx.style < _S:
            gap = 0.0
            if kind == "rel" or prev == "rel":
                gap = 5 / 18 if not (kind == "rel" and prev == "rel") else 0.0
            elif kind == "bin" or prev == "bin":
                gap = 4 / 18
            elif prev == "op" and kind in ("ord", "op", "inner"):
                gap = 3 / 18
            elif kind in ("op", "op_limits") and prev in ("ord", "close", "inner"):
                gap = 3 / 18
            elif prev == "punct":
                gap = 3 / 18
            if gap:
                spaced.append(_kern(gap * ctx.px))
        if b.kind != "kern":
            prev = kind
        spaced.append(b)
    return _hbox(spaced)


def _layout(node, ctx: _Ctx) -> Box:
    tag = node[0]
    if tag == "empty":
        return Box()
    if tag == "group":
        b = _layout_list(node[1], ctx)
        b.kind = "ord"
        return b
    if tag == "char":
        _, ch, variant = node
        if variant is None:
            variant = ctx.variant
        elif ctx.variant in ("bf", "bfit") and variant == "rm":
            variant = "bf"
        if variant in _ALPHABETS:
            ch, variant = _alphabet(ch, variant), "rm"
        return _glyph(ch, ctx, variant)
    if tag == "text":
        return _text_run(node[1], ctx, "rm")
    if tag == "font":
        _, variant, body = node
        b = _layout_list(body, ctx.with_variant(variant))
        b.kind = "ord"
        return b
    if tag == "space":
        return _kern(node[1] * ctx.px)
    if tag == "func":
        _, name, limits = node
        b = _text_run(name, ctx, "rm")
        # lim/max/min take their subscript underneath in display style.
        b.kind = "op_limits" if (limits and ctx.style == _D) else "op"
        return b
    if tag == "scripts":
        return _scripts(node, ctx)
    if tag == "frac":
        return _frac(node, ctx)
    if tag == "sqrt":
        return _sqrt(node, ctx)
    if tag == "delim":
        _, open_, body, close, _ = node
        inner = _layout_list(body, ctx)
        parts = []
        if open_:
            parts.append(_grown(open_, inner, ctx))
        parts.append(inner)
        if close:
            parts.append(_grown(close, inner, ctx))
        b = _hbox(parts)
        b.kind = "inner"
        return b
    if tag == "bigdelim":
        _, d, factor = node
        if not d:
            return Box()
        return _glyph(d, ctx, "rm", scale=factor)
    if tag == "bigop":
        _, ch, limits, integral = node
        scale = 1.6 if ctx.style == _D else 1.15
        b = _glyph(ch, ctx, "rm", scale=scale)
        # Centre the operator on the math axis.
        centre = (b.height - b.depth) / 2.0
        shift = centre - _axis(ctx)
        b = Box(width=b.width, height=b.height - shift, depth=b.depth + shift,
                items=[("glyph", 0.0, shift, *b.items[0][3:])], italic_corr=b.italic_corr)
        b.kind = "op_limits" if (limits and ctx.style == _D) else "op"
        if integral:
            b.kind = "op"
        return b
    if tag == "accent":
        _, mark, body = node
        inner = _layout_list(body, ctx)
        acc = _glyph(mark, ctx, "rm", scale=0.9 if mark != "→" else 0.75)
        gap = 0.08 * ctx.px
        # Centre the accent's ink over the body's ink, nudged right on an
        # italic body (TeX's skew), and rest its ink bottom a gap above it.
        centre = (inner.ink[0] + inner.ink[1]) / 2.0 + inner.italic_corr * 0.4
        x = centre - (acc.ink[0] + acc.ink[1]) / 2.0
        y = -(inner.height + gap) - acc.ink_bottom
        top = inner.height + gap + (acc.height + acc.ink_bottom)
        b = Box(width=inner.width, height=max(inner.height, top), depth=inner.depth,
                items=inner.shifted(0.0, 0.0) + acc.shifted(x, y), ink=inner.ink,
                italic_corr=inner.italic_corr)
        return b
    if tag == "stack":
        _, body_n, below_n, above_n = node
        base = _layout_list(body_n, ctx)
        sctx = ctx.at(ctx.sup_style)
        below = _layout_list(below_n, sctx) if below_n is not None else None
        above = _layout_list(above_n, sctx) if above_n is not None else None
        gap = 0.1 * ctx.px
        width = max(base.width, below.width if below else 0.0, above.width if above else 0.0)
        items = base.shifted((width - base.width) / 2.0, 0.0)
        height, depth = base.height, base.depth
        if above is not None:
            items += above.shifted((width - above.width) / 2.0,
                                   -(base.height + gap + above.depth))
            height = base.height + gap + above.depth + above.height
        if below is not None:
            items += below.shifted((width - below.width) / 2.0, base.depth + gap + below.height)
            depth = base.depth + gap + below.height + below.depth
        b = Box(width=width, height=height, depth=depth, items=items)
        # \stackrel{def}{=} is still a relation.
        b.kind = base.kind if base.kind in ("rel", "bin") else "ord"
        return b
    if tag == "line":
        _, over, body = node
        inner = _layout_list(body, ctx)
        t = _rule(ctx)
        gap = 0.12 * ctx.px
        if over:
            y = -(inner.height + gap)
            return Box(width=inner.width, height=inner.height + gap + t, depth=inner.depth,
                       items=inner.shifted(0, 0) + [("rule", 0.0, y - t, inner.width, y)])
        y = inner.depth + gap
        return Box(width=inner.width, height=inner.height, depth=inner.depth + gap + t,
                   items=inner.shifted(0, 0) + [("rule", 0.0, y, inner.width, y + t)])
    raise TexError(f"cannot lay out {tag}")  # pragma: no cover


def _scripts(node, ctx: _Ctx) -> Box:
    _, base_node, sub_node, sup_node = node
    base = _layout(base_node, ctx)
    sctx = ctx.at(ctx.sup_style)
    sup = _layout_list(sup_node, sctx) if sup_node is not None else None
    sub = _layout_list(sub_node, sctx) if sub_node is not None else None
    if base.kind == "op_limits":
        # Limits above and below, centred (display-style sums, lim).
        gap = 0.1 * ctx.px
        width = max(base.width, sup.width if sup else 0.0, sub.width if sub else 0.0)
        items = base.shifted((width - base.width) / 2.0, 0.0)
        height, depth = base.height, base.depth
        if sup is not None:
            y = -(base.height + gap + sup.depth)
            items += sup.shifted((width - sup.width) / 2.0, y)
            height = base.height + gap + sup.depth + sup.height
        if sub is not None:
            y = base.depth + gap + sub.height
            items += sub.shifted((width - sub.width) / 2.0, y)
            depth = base.depth + gap + sub.height + sub.depth
        b = Box(width=width, height=height, depth=depth, items=items)
        b.kind = "op"
        return b
    px = ctx.px
    # TeX's rules, in em of the current style: raise a superscript to at
    # least 0.36 em (or its base's height less a quarter em), drop a
    # subscript 0.2 em, and keep 0.2 em between them when both are present.
    up = max(0.36 * px, base.height - 0.25 * sctx.px)
    if sup is not None:
        up = max(up, sup.depth + 0.25 * px)
    down = max(0.2 * px, base.depth + 0.1 * sctx.px)
    if sub is not None:
        down = max(down, sub.height - 0.8 * 0.45 * px)
    if sup is not None and sub is not None:
        gap = (up - sup.depth) - (sub.height - down)
        if gap < 0.2 * px:
            down += 0.2 * px - gap
    items = base.shifted(0.0, 0.0)
    width = base.width
    height, depth = base.height, base.depth
    after = base.width
    if sup is not None:
        items += sup.shifted(after + base.italic_corr, -up)
        width = max(width, after + base.italic_corr + sup.width)
        height = max(height, up + sup.height)
        depth = max(depth, sup.depth - up)
    if sub is not None:
        items += sub.shifted(after, down)
        width = max(width, after + sub.width)
        depth = max(depth, down + sub.depth)
        height = max(height, sub.height - down)
    width += 0.05 * px
    b = Box(width=width, height=height, depth=depth, items=items)
    b.kind = base.kind if base.kind in ("op",) else "ord"
    return b


def _frac(node, ctx: _Ctx) -> Box:
    _, num_n, den_n, forced, bar = node
    # \dfrac sets its parts in text style, \tfrac in script style; a plain
    # \frac one style smaller than the one it is in.
    fctx = ctx.at(ctx.frac_style if forced is None else (_T if forced == _D else _S))
    num = _layout_list(num_n, fctx)
    den = _layout_list(den_n, fctx)
    t = _rule(ctx) if bar else 0.0
    axis = _axis(ctx)
    gap = (0.15 if ctx.style == _D or forced == _D else 0.1) * ctx.px
    width = max(num.width, den.width) + 0.2 * ctx.px
    num_y = -(axis + t / 2.0 + gap + num.depth)
    den_y = -axis + t / 2.0 + gap + den.height
    items = num.shifted((width - num.width) / 2.0, num_y)
    items += den.shifted((width - den.width) / 2.0, den_y)
    if bar:
        items.append(("rule", 0.05 * ctx.px, -axis - t / 2.0, width - 0.05 * ctx.px, -axis + t / 2.0))
    b = Box(width=width, height=-num_y + num.height, depth=den_y + den.depth, items=items)
    b.kind = "inner"
    return b


def _sqrt(node, ctx: _Ctx) -> Box:
    _, body_n, index_n = node
    body = _layout_list(body_n, ctx)
    t = _rule(ctx)
    gap = 0.12 * ctx.px
    top = body.height + gap + t
    bottom = max(body.depth, 0.1 * ctx.px)
    total = top + bottom
    # The radical: a short rising tick, a long stroke down to the bottom, a
    # long stroke up to the vinculum -- drawn, so it grows with its contents.
    w_sign = 0.35 * ctx.px + 0.08 * total
    x_tick0, y_tick0 = 0.0, -total * 0.45 + bottom
    x_tick1, y_tick1 = w_sign * 0.25, -total * 0.52 + bottom
    x_low, y_low = w_sign * 0.55, bottom
    x_top, y_top = w_sign, -top + t / 2.0
    lw = max(1.0, t * 1.1)
    items = [("poly", [(x_tick0, y_tick0), (x_tick1, y_tick1)], lw),
             ("poly", [(x_tick1, y_tick1), (x_low, y_low)], lw * 1.6),
             ("poly", [(x_low, y_low), (x_top, y_top)], lw)]
    body_x = w_sign + 0.08 * ctx.px
    items += body.shifted(body_x, 0.0)
    end = body_x + body.width + 0.06 * ctx.px
    items.append(("rule", x_top, -top, end, -top + t))
    width = end + 0.05 * ctx.px
    height = top
    if index_n:
        ictx = ctx.at(_SS)
        index = _layout_list(index_n, ictx)
        raise_ = total * 0.6 - bottom
        shift = max(0.0, index.width - x_tick1)
        items = [_shift_item(it, shift) for it in items]
        items += index.shifted(max(0.0, x_tick1 - index.width), -(raise_ + index.depth))
        width += shift
        height = max(height, raise_ + index.depth + index.height)
    return Box(width=width, height=height, depth=bottom, items=items)


def _shift_item(item, dx: float):
    tag = item[0]
    if tag == "rule":
        _, x0, y0, x1, y1 = item
        return ("rule", x0 + dx, y0, x1 + dx, y1)
    if tag == "poly":
        _, pts, w = item
        return ("poly", [(x + dx, y) for x, y in pts], w)
    _, x, y, *rest = item
    return ("glyph", x + dx, y, *rest)


def _grown(ch: str, inner: Box, ctx: _Ctx) -> Box:
    """*ch* scaled to span *inner*, centred on the math axis."""
    plain = _glyph(ch, ctx, "rm")
    need = 2.0 * max(inner.height - _axis(ctx), inner.depth + _axis(ctx)) * 1.05
    have = max(plain.height + plain.depth, 1.0)
    scale = max(1.0, need / have)
    if scale <= 1.05:
        return plain
    b = _glyph(ch, ctx, "rm", scale=min(scale, 6.0))
    centre = (b.height - b.depth) / 2.0
    shift = centre - _axis(ctx)
    return Box(width=b.width, height=b.height - shift, depth=b.depth + shift,
               items=[("glyph", 0.0, shift, *b.items[0][3:])], kind=plain.kind)


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #
@dataclass
class Layout:
    """A typeset formula: its metrics in pixels and its drawing operations.

    ``items`` are ``("glyph", x, baseline_y, char, family, italic, bold, px)``,
    ``("rule", x0, y0, x1, y1)`` (a filled rectangle) and
    ``("poly", points, width)`` (a stroked path), relative to the formula's
    left end on its baseline, y growing downwards.
    """

    width: float
    height: float
    depth: float
    items: list


def typeset(latex: str, size_px: float, display: bool = False, sans: bool = False) -> Layout:
    """Lay out *latex* (math mode, no ``$``) at a text size of *size_px* pixels.

    ``sans`` sets letters and digits in a sans face (symbols still come from
    the math face), to sit beside a sans interface font.

    Raises
    ------
    TexError
        For syntax outside the subset (see the module docstring).
    """
    parser = _Parser(latex.strip().strip("$"))
    nodes = parser.until(None)
    box = _layout_list(nodes, _Ctx(float(size_px), _D if display else _T, "it", sans))
    return Layout(box.width, box.height, box.depth, box.items)


def render_rgba(latex: str, size_px: float, colour=(0, 0, 0, 255), pad: int = 2,
                display: bool = False, background=None, sans: bool = False):
    """Typeset and rasterise: ``(width, height, RGBA bytes, baseline)``.

    Transparent around the ink unless *background* is given. ``baseline`` is
    the row of the baseline, for aligning the image with surrounding text.
    """
    from PIL import Image, ImageDraw

    layout = typeset(latex, size_px, display, sans)
    # Pillow's text and lines are drawn at twice the size and filtered down,
    # so a thin rule and a glyph stem get the same anti-aliasing.
    k = 2
    w = int(math.ceil(layout.width)) + 2 * pad
    h = int(math.ceil(layout.height + layout.depth)) + 2 * pad
    w, h = max(w, 1), max(h, 1)
    ox, oy = pad, pad + layout.height
    rgba = tuple(int(c) for c in colour)
    rgba = rgba + (255,) if len(rgba) == 3 else rgba
    bg = (rgba[0], rgba[1], rgba[2], 0) if background is None else tuple(background)
    image = Image.new("RGBA", (w * k, h * k), bg)
    draw = ImageDraw.Draw(image)
    for item in layout.items:
        tag = item[0]
        if tag == "glyph":
            _, x, y, ch, family, italic, bold, px = item
            font = _font(family, italic, bold, px * k)
            draw.text(((x + ox) * k, (y + oy) * k), ch, font=font, fill=rgba, anchor="ls")
        elif tag == "rule":
            _, x0, y0, x1, y1 = item
            draw.rectangle(((x0 + ox) * k, (y0 + oy) * k, max((x1 + ox) * k - 1, (x0 + ox) * k),
                            max((y1 + oy) * k - 1, (y0 + oy) * k)), fill=rgba)
        elif tag == "poly":
            _, pts, lw = item
            draw.line([((px_ + ox) * k, (py + oy) * k) for px_, py in pts], fill=rgba,
                      width=max(1, int(round(lw * k))), joint="curve")
    image = image.resize((w, h), Image.LANCZOS)
    return w, h, image.tobytes(), int(round(oy))
