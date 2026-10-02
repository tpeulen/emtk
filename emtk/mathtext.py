"""Math typesetting and LaTeX rendering for EMTK.

Renders LaTeX mathematics into transparent textures using matplotlib's mathtext
engine when available, with fast caching and a graceful Unicode fallback.
"""

from __future__ import annotations

import base64
import io
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .texture import Texture

logger = logging.getLogger(__name__)

__all__ = [
    "MathTextureCache",
    "calc_math_size",
    "convert_script_markup",
    "latex_to_unicode",
    "normalize_latex",
    "render_math_to_texture",
]

_GREEK_AND_SYMBOLS: dict[str, str] = {
    # Lowercase Greek
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\varepsilon": "ε",
    r"\zeta": "ζ",
    r"\eta": "η",
    r"\theta": "θ",
    r"\vartheta": "ϑ",
    r"\iota": "ι",
    r"\kappa": "κ",
    r"\varkappa": "ϰ",
    r"\lambda": "λ",
    r"\mu": "µ",
    r"\nu": "ν",
    r"\xi": "ξ",
    r"\omicron": "ο",
    r"\pi": "π",
    r"\varpi": "ϖ",
    r"\rho": "ρ",
    r"\varrho": "ϱ",
    r"\sigma": "σ",
    r"\varsigma": "ς",
    r"\tau": "τ",
    r"\upsilon": "υ",
    r"\phi": "φ",
    r"\varphi": "ϕ",
    r"\chi": "χ",
    r"\psi": "ψ",
    r"\omega": "ω",
    # Uppercase Greek
    r"\Alpha": "Α",
    r"\Beta": "Β",
    r"\Gamma": "Γ",
    r"\Delta": "Δ",
    r"\Epsilon": "Ε",
    r"\Zeta": "Ζ",
    r"\Eta": "Η",
    r"\Theta": "Θ",
    r"\Iota": "Ι",
    r"\Kappa": "Κ",
    r"\Lambda": "Λ",
    r"\Mu": "Μ",
    r"\Nu": "Ν",
    r"\Xi": "Ξ",
    r"\Omicron": "Ο",
    r"\Pi": "Π",
    r"\Rho": "Ρ",
    r"\Sigma": "Σ",
    r"\Tau": "Τ",
    r"\Upsilon": "Υ",
    r"\Phi": "Φ",
    r"\Chi": "Χ",
    r"\Psi": "Ψ",
    r"\Omega": "Ω",
    # Operators & arithmetic
    r"\times": "×",
    r"\div": "÷",
    r"\pm": "±",
    r"\mp": "∓",
    r"\cdot": "·",
    r"\circ": "∘",
    r"\bullet": "•",
    r"\star": "⋆",
    r"\ast": "∗",
    r"\oplus": "⊕",
    r"\ominus": "⊖",
    r"\otimes": "⊗",
    r"\odot": "⊙",
    r"\wedge": "∧",
    r"\vee": "∨",
    r"\cap": "∩",
    r"\cup": "∪",
    r"\setminus": "∖",
    # Relations
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\approx": "≈",
    r"\equiv": "≡",
    r"\sim": "∼",
    r"\simeq": "≃",
    r"\cong": "≅",
    r"\propto": "∝",
    r"\ll": "≪",
    r"\gg": "≫",
    r"\in": "∈",
    r"\notin": "∉",
    r"\ni": "∋",
    r"\subset": "⊂",
    r"\subseteq": "⊆",
    r"\supset": "⊃",
    r"\supseteq": "⊇",
    r"\parallel": "∥",
    r"\perp": "⊥",
    # Arrows
    r"\to": "→",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\Leftarrow": "⇐",
    r"\Rightarrow": "⇒",
    r"\leftrightarrow": "↔",
    r"\Leftrightarrow": "⇔",
    r"\mapsto": "↦",
    r"\uparrow": "↑",
    r"\downarrow": "↓",
    # Calculus, sets, logic
    r"\partial": "∂",
    r"\nabla": "∇",
    r"\int": "∫",
    r"\iint": "∬",
    r"\iiint": "∭",
    r"\oint": "∮",
    r"\sum": "∑",
    r"\prod": "∏",
    r"\coprod": "∐",
    r"\infty": "∞",
    r"\forall": "∀",
    r"\exists": "∃",
    r"\nexists": "∄",
    r"\emptyset": "∅",
    r"\varnothing": "⌀",
    r"\sqrt": "√",
    # Brackets & fences
    r"\langle": "⟨",
    r"\rangle": "⟩",
    r"\lceil": "⌈",
    r"\rceil": "⌉",
    r"\lfloor": "⌊",
    r"\rfloor": "⌋",
    r"\vert": "|",
    r"\lvert": "|",
    r"\rvert": "|",
    r"\Vert": "‖",
    r"\lVert": "‖",
    r"\rVert": "‖",
    # Ellipses & dots
    r"\cdots": "⋯",
    r"\ldots": "…",
    r"\dots": "…",
    r"\ddots": "⋱",
    r"\vdots": "⋮",
}

_SUBSCRIPTS: dict[str, str] = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "b": "ᵦ", "c": "꜀", "d": "ᑯ", "e": "ₑ",
    "f": "բ", "g": "ᵧ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ",
    "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ",
    "v": "ᵥ", "x": "ₓ", "y": "ᵧ", "z": "𝓏",
    "A": "ₐ", "B": "ᵦ", "D": "ᵨ", "E": "ₑ", "H": "ₕ",
    "I": "ᵢ", "J": "ⱼ", "K": "ₖ", "L": "ₗ", "M": "ₘ",
    "N": "ₙ", "O": "ₒ", "P": "ₚ", "R": "ᵣ", "S": "ₛ",
    "T": "ₜ", "U": "ᵤ", "V": "ᵥ", "X": "ₓ",
    "α": "ᵦ", "β": "ᵦ", "γ": "ᵧ", "ρ": "ᵨ", "φ": "ᵩ", "χ": "ᵪ",
}

_SUPERSCRIPTS: dict[str, str] = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "q": "ᑫ", "r": "ʳ", "s": "ˢ", "t": "ᵗ",
    "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "A": "ᴬ", "B": "ᴮ", "C": "ᶜ", "D": "ᴰ", "E": "ᴱ",
    "F": "ᶠ", "G": "ᴳ", "H": "ᴴ", "I": "ᴵ", "J": "ᴶ",
    "K": "ᴷ", "L": "ᴸ", "M": "ᴹ", "N": "ᴺ", "O": "ᴼ",
    "P": "ᴾ", "R": "ᴿ", "T": "ᵀ", "U": "ᵁ", "V": "ⱽ", "W": "ᵂ",
}

_MATH_FUNCTIONS = (
    "sin", "cos", "tan", "sec", "csc", "cot",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
    "exp", "ln", "log", "lg", "det", "dim", "ker",
    "lim", "max", "min", "sup", "inf", "arg", "deg", "gcd", "Pr",
)


def _extract_braced(s: str, start: int) -> tuple[str, int] | None:
    """Extract content inside matching braces {...} starting at *start*."""
    while start < len(s) and s[start].isspace():
        start += 1
    if start >= len(s) or s[start] != "{":
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1:i], i + 1
    return None


def normalize_latex(latex: str) -> str:
    """Normalize LaTeX formula string into a format mathtext can parse cleanly."""
    text = latex.strip()
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()

    # Environments (align, equation, matrix, cases, split, etc.)
    text = re.sub(
        r"\\begin\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|cases)\}(.*?)\\end\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*|matrix|pmatrix|bmatrix|vmatrix|Vmatrix|array|cases)\}",
        lambda m: m.group(1).replace(r"\\", " ").replace("&", " "),
        text,
        flags=re.DOTALL,
    )
    text = text.replace(r"\\", " ")
    text = re.sub(r"(?<!\\)&", "", text)
    text = re.sub(r"\s+", " ", text)

    # Fractions and binomials
    text = re.sub(r"\\(?:dfrac|tfrac|cfrac)\b", r"\\frac", text)
    text = re.sub(r"\\binom\s*\{([^}]+)\}\s*\{([^}]+)\}", r"{\1 \\choose \2}", text)

    # Common LaTeX macros and fonts
    text = re.sub(r"\\(?:text|textrm|mbox|textnormal)\s*\{", r"\\mathrm{", text)
    text = re.sub(r"\\(?:textbf)\s*\{", r"\\mathbf{", text)
    text = re.sub(r"\\(?:textit|emph)\s*\{", r"\\mathit{", text)
    text = re.sub(r"\\boxed\s*\{", "{", text)

    # Blackboard bold / script / sans-serif mapping
    text = re.sub(r"\\(?:mathbb|mathbf|bm|symbf)\s*\{([A-Za-z0-9])\}", r"\\mathbf{\1}", text)
    text = re.sub(r"\\(?:mathsf|mathtt|mathfrak|mathscr|mathcal)(?![A-Za-z])", r"\\mathrm", text)
    text = re.sub(r"\\(?:boldsymbol|bm|pmb)(?![A-Za-z])\s*", r"\\mathbf", text)

    # Delimiters
    text = re.sub(
        r"\\(?:Biggl|Biggr|biggl|biggr|Bigll|Bigl|Bigr|bigl|bigr|Bigg|bigg|Big|big)(?![A-Za-z])",
        "",
        text,
    )
    text = text.replace(r"\left.", "").replace(r"\right.", "")

    # Spacing and tags
    text = re.sub(r"\\(?:!|>|medspace|thinspace|thickspace|negthinspace)", " ", text)
    text = text.replace(r"\qquad", "  ").replace(r"\quad", " ")
    text = text.replace(r"\nonumber", "").replace(r"\notag", "")
    text = re.sub(r"\\label\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:displaystyle|textstyle|scriptstyle|limits|nolimits)\b", "", text)
    text = re.sub(r"\\operatorname\s*\*?\s*\{", r"\\mathrm{", text)

    return text.strip()


_SCRIPT_MARKUP = re.compile(r"(\\?)([_^])\{([^{}]*)\}")


def convert_script_markup(s: str) -> str:
    """Convert inline ``_{...}`` / ``^{...}`` markup to Unicode sub/superscripts.

    Plain labels ("R_{0} [Å]", "x^{2}") render as "R₀ [Å]", "x²" through the
    same Unicode maps the LaTeX fallback uses, so *every* text path that goes
    through the painters — widget labels, :func:`emtk.im.text`,
    :func:`emtk.im.label_text` — gets real sub/superscripts without needing the
    mathtext renderer.

    Braces are required so ordinary text that merely contains ``_`` or ``^``
    (file names, units) is never mangled; ``\\_{...}`` / ``\\^{...}`` escape the
    markup. A group whose characters have no Unicode form is left unchanged,
    so the source string stays readable instead of silently losing content.
    """
    if "_" not in s and "^" not in s:
        return s

    def _sub(m: re.Match[str]) -> str:
        escape, kind, content = m.group(1), m.group(2), m.group(3)
        if escape:
            return f"{kind}{{{content}}}"
        table = _SUBSCRIPTS if kind == "_" else _SUPERSCRIPTS
        mapped = "".join(table.get(ch, "") for ch in content)
        return mapped if len(mapped) == len(content) else m.group(0)

    return _SCRIPT_MARKUP.sub(_sub, s)


def latex_to_unicode(latex: str) -> str:
    """Best-effort conversion of a LaTeX formula into clean Unicode text."""
    text = normalize_latex(latex)

    # Nested fraction replacement via balanced braces
    frac_pat = re.compile(r"\\(?:frac|tfrac|dfrac|cfrac)")
    while True:
        m = frac_pat.search(text)
        if not m:
            break
        pos = m.end()
        num_res = _extract_braced(text, pos)
        if num_res is None:
            break
        num, next_pos = num_res
        den_res = _extract_braced(text, next_pos)
        if den_res is None:
            break
        den, end_pos = den_res
        # Convert sub-expressions recursively
        sub_num = latex_to_unicode(num)
        sub_den = latex_to_unicode(den)
        text = text[:m.start()] + f"({sub_num})/({sub_den})" + text[end_pos:]

    # Square root
    text = re.sub(r"\\sqrt\{([^}]+)\}", r"√(\1)", text)

    # Standard math functions (\sin, \cos, \ln, etc.)
    for fn in _MATH_FUNCTIONS:
        text = re.sub(r"\\" + fn + r"\b", fn, text)

    # Accents: \hat{x} -> x̂, \bar{x} -> x̄, \vec{x} -> x⃗, \dot{x} -> ẋ, \ddot{x} -> ẍ, \tilde{x} -> x̃
    _ACCENTS = {
        "hat": "\u0302",
        "bar": "\u0304",
        "vec": "\u20D7",
        "dot": "\u0307",
        "ddot": "\u0308",
        "tilde": "\u0303",
    }
    for acc_cmd, acc_char in _ACCENTS.items():
        text = re.sub(
            r"\\" + acc_cmd + r"\{([^}]+)\}",
            lambda m, c=acc_char: m.group(1) + c,
            text,
        )

    # Greek letters and math symbols
    for cmd, sym in _GREEK_AND_SYMBOLS.items():
        text = re.sub(re.escape(cmd) + r"(?![A-Za-z])", sym, text)

    # Subscripts: _{12} or _0
    def _sub(m: re.Match[str]) -> str:
        content = m.group(1) or m.group(2)
        return "".join(_SUBSCRIPTS.get(c, c) for c in content)

    text = re.sub(r"_\{([^}]+)\}|_([0-9a-zA-Z+-])", _sub, text)

    # Superscripts: ^{2} or ^2
    def _sup(m: re.Match[str]) -> str:
        content = m.group(1) or m.group(2)
        return "".join(_SUPERSCRIPTS.get(c, c) for c in content)

    text = re.sub(r"\^\{([^}]+)\}|\^([0-9a-zA-Z+-])", _sup, text)

    # Strip formatting tags and delimiters
    text = re.sub(r"\\(?:left|right|mathrm|mathbf|mathit|mathcal)\b", "", text)
    text = re.sub(r"\\[A-Za-z]+", "", text)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip()



class MathTextureCache:
    """LRU Texture cache for rasterized LaTeX mathematics."""

    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = maxsize
        self._cache: dict[tuple[str, tuple[int, int, int, int], float, int], Texture] = {}
        self._keys: list[tuple[str, tuple[int, int, int, int], float, int]] = []

    def get(
        self,
        formula: str,
        colour: tuple[int, int, int, int],
        font_size: float,
        dpi: int,
    ) -> Texture | None:
        key = (formula, colour, font_size, dpi)
        tex = self._cache.get(key)
        if tex is not None:
            # Move to MRU
            self._keys.remove(key)
            self._keys.append(key)
        return tex

    def put(
        self,
        formula: str,
        colour: tuple[int, int, int, int],
        font_size: float,
        dpi: int,
        texture: Texture,
    ) -> None:
        key = (formula, colour, font_size, dpi)
        if key in self._cache:
            self._keys.remove(key)
        elif len(self._keys) >= self.maxsize:
            oldest = self._keys.pop(0)
            self._cache.pop(oldest, None)
        self._cache[key] = texture
        self._keys.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._keys.clear()


_GLOBAL_MATH_CACHE = MathTextureCache()


def _color_to_rgba_tuple(c: object) -> tuple[int, int, int, int]:
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        r, g, b = int(c[0]), int(c[1]), int(c[2])
        a = int(c[3]) if len(c) > 3 else 255
        return (r, g, b, a)
    if isinstance(c, str):
        hex_val = c.lstrip("#")
        if len(hex_val) == 6:
            return (int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16), 255)
        if len(hex_val) == 8:
            return (int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16), int(hex_val[6:8], 16))
    return (255, 255, 255, 255)


def render_math_to_texture(
    formula: str,
    colour: tuple[int, int, int, int] | str = (255, 255, 255, 255),
    font_size: float = 14.0,
    dpi: int = 144,
    cache: MathTextureCache | None = None,
) -> Texture | None:
    """Render LaTeX formula to an RGBA EMTK Texture with transparent background.

    Parameters
    ----------
    formula : str
        LaTeX mathematical expression.
    colour : tuple or str
        RGBA colour tuple or hex string.
    font_size : float
        Font size in points.
    dpi : int
        Rendering DPI (default 144 for crisp high-DPI).
    cache : MathTextureCache, optional
        Optional custom cache instance.

    Returns
    -------
    Texture or None
        Cached EMTK Texture or None if rasterization failed.
    """
    if cache is None:
        cache = _GLOBAL_MATH_CACHE

    rgba = _color_to_rgba_tuple(colour)
    norm = normalize_latex(formula)
    if not norm:
        return None

    cached = cache.get(norm, rgba, font_size, dpi)
    if cached is not None:
        return cached

    try:
        from matplotlib.figure import Figure
        from matplotlib.font_manager import FontProperties
        from PIL import Image

        from .texture import Texture
    except Exception as e:
        logger.debug("matplotlib or PIL not available for math rendering: %s", e)
        return None

    try:
        fig = Figure(figsize=(0.01, 0.01), dpi=dpi)
        fig.patch.set_alpha(0.0)

        # Normalise colour for matplotlib (0.0 to 1.0)
        c_norm = (rgba[0] / 255.0, rgba[1] / 255.0, rgba[2] / 255.0, rgba[3] / 255.0)
        prop = FontProperties(size=font_size)

        fig.text(0, 0, f"${norm}$", fontproperties=prop, color=c_norm)

        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            transparent=True,
            bbox_inches="tight",
            pad_inches=0.03,
        )
        buf.seek(0)
        img = Image.open(buf).convert("RGBA")
        w, h = img.size
        tex = Texture(w, h, img.tobytes(), filter="linear")
        cache.put(norm, rgba, font_size, dpi, tex)
        return tex
    except Exception as e:
        logger.debug("render_math_to_texture failed for %r: %s", formula, e)
        return None


def calc_math_size(
    formula: str,
    font_size: float = 14.0,
    dpi: int = 144,
    scale: float = 0.5,
) -> tuple[float, float]:
    """Calculate the layout size of a LaTeX formula."""
    tex = render_math_to_texture(formula, font_size=font_size, dpi=dpi)
    if tex is not None:
        return (tex.width * scale, tex.height * scale)
    # Fallback approximation based on Unicode text
    u = latex_to_unicode(formula)
    return (len(u) * font_size * 0.6, font_size * 1.4)
