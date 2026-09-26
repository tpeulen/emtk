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
    "latex_to_unicode",
    "normalize_latex",
    "render_math_to_texture",
]

_GREEK_AND_SYMBOLS: dict[str, str] = {
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
    r"\lambda": "λ",
    r"\mu": "µ",
    r"\nu": "ν",
    r"\xi": "ξ",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\varrho": "ϱ",
    r"\sigma": "σ",
    r"\varsigma": "ς",
    r"\tau": "τ",
    r"\upsilon": "υ",
    r"\phi": "φ",
    r"\varphi": "φ",
    r"\chi": "χ",
    r"\psi": "ψ",
    r"\omega": "ω",
    r"\Delta": "Δ",
    r"\Gamma": "Γ",
    r"\Sigma": "Σ",
    r"\Omega": "Ω",
    r"\Phi": "Φ",
    r"\Psi": "Ψ",
    r"\Lambda": "Λ",
    r"\Theta": "Θ",
    r"\Xi": "Ξ",
    r"\Pi": "Π",
    r"\times": "×",
    r"\cdot": "·",
    r"\cdots": "⋯",
    r"\ldots": "…",
    r"\dots": "…",
    r"\approx": "≈",
    r"\propto": "∝",
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\neq": "≠",
    r"\ne": "≠",
    r"\pm": "±",
    r"\mp": "∓",
    r"\to": "→",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\Rightarrow": "⇒",
    r"\leftrightarrow": "↔",
    r"\mapsto": "↦",
    r"\langle": "⟨",
    r"\rangle": "⟩",
    r"\infty": "∞",
    r"\partial": "∂",
    r"\sum": "Σ",
    r"\prod": "∏",
    r"\int": "∫",
    r"\sqrt": "√",
    r"\ll": "≪",
    r"\gg": "≫",
    r"\equiv": "≡",
    r"\sim": "∼",
    r"\simeq": "≃",
}

_SUBSCRIPTS: dict[str, str] = {
    "0": "₀",
    "1": "₁",
    "2": "₂",
    "3": "₃",
    "4": "₄",
    "5": "₅",
    "6": "₆",
    "7": "₇",
    "8": "₈",
    "9": "₉",
    "+": "₊",
    "-": "₋",
    "=": "₌",
    "(": "₍",
    ")": "₎",
    "a": "ₐ",
    "e": "ₑ",
    "h": "ₕ",
    "i": "ᵢ",
    "j": "ⱼ",
    "k": "ₖ",
    "l": "ₗ",
    "m": "ₘ",
    "n": "ₙ",
    "o": "ₒ",
    "p": "ₚ",
    "r": "ᵣ",
    "s": "ₛ",
    "t": "ₜ",
    "u": "ᵤ",
    "v": "ᵥ",
    "x": "ₓ",
}

_SUPERSCRIPTS: dict[str, str] = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
    "=": "⁼",
    "(": "⁽",
    ")": "⁾",
    "n": "ⁿ",
    "i": "ⁱ",
}


def normalize_latex(latex: str) -> str:
    """Normalize LaTeX formula string into a format mathtext can parse cleanly."""
    text = latex.strip()
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2].strip()
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1].strip()

    # Environments
    text = re.sub(
        r"\\begin\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*)\}(.*?)\\end\{(?:align|align\*|aligned|equation|equation\*|split|gather|gather\*)\}",
        lambda m: m.group(1).replace(r"\\", " ").replace("&", " "),
        text,
        flags=re.DOTALL,
    )
    text = text.replace(r"\\", " ")
    text = re.sub(r"(?<!\\)&", "", text)
    text = re.sub(r"\s+", " ", text)

    # Common LaTeX macros
    text = re.sub(r"\\(?:text|textrm|mbox|textnormal)\s*\{", r"\\mathrm{", text)
    text = re.sub(r"\\(?:textbf)\s*\{", r"\\mathbf{", text)
    text = re.sub(r"\\(?:textit|emph)\s*\{", r"\\mathit{", text)
    text = re.sub(r"\\boxed\s*\{", "{", text)

    # Delimiters
    text = re.sub(
        r"\\(?:Biggl|Biggr|biggl|biggr|Bigll|Bigl|Bigr|bigl|bigr|Bigg|bigg|Big|big)(?![A-Za-z])",
        "",
        text,
    )
    text = re.sub(r"\\(?:mathsf|mathtt|mathfrak|mathscr)(?![A-Za-z])", r"\\mathrm", text)
    text = re.sub(r"\\boldsymbol(?![A-Za-z])\s*", r"\\mathbf", text)
    text = re.sub(r"\\pmb(?![A-Za-z])\s*", r"\\mathbf", text)

    # Spacing and tags
    text = re.sub(r"\\(?:!|>|medspace|thinspace|thickspace|negthinspace)", " ", text)
    text = text.replace(r"\qquad", "  ").replace(r"\quad", " ")
    text = text.replace(r"\nonumber", "").replace(r"\notag", "")
    text = re.sub(r"\\label\s*\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:displaystyle|textstyle|scriptstyle|limits|nolimits)\b", "", text)
    text = re.sub(r"\\operatorname\s*\*?\s*\{", r"\\mathrm{", text)
    text = text.replace(r"\left.", "").replace(r"\right.", "")

    return text.strip()


def latex_to_unicode(latex: str) -> str:
    """Best-effort conversion of a LaTeX formula into clean Unicode text."""
    text = normalize_latex(latex)
    # Fractions: \frac{a}{b} -> (a)/(b)
    text = re.sub(r"\\(?:frac|tfrac|dfrac)\{([^}]+)\}\{([^}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^}]+)\}", r"√(\1)", text)

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

    # Strip formatting tags
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
