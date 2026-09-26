"""Tests for EMTK math rendering and typesetting capabilities."""

import pytest
from emtk import im, latex_to_unicode, normalize_latex, render_math_to_texture
from emtk.painter import Painter
from emtk.testing import RecordingPainter


def test_normalize_latex():
    # Enclosing dollar signs stripped
    assert normalize_latex("$$ E = mc^2 $$") == "E = mc^2"
    assert normalize_latex("$a + b$") == "a + b"

    # Multi-line environments flattened
    raw_env = r"\begin{equation}x = 1 \\ y = 2\end{equation}"
    assert normalize_latex(raw_env) == "x = 1 y = 2"

    # Common macros
    assert normalize_latex(r"\text{hello} + \mathbf{v}") == r"\mathrm{hello} + \mathbf{v}"
    assert normalize_latex(r"\boxed{42}") == "{42}"


def test_latex_to_unicode():
    # Greek letters
    assert "α" in latex_to_unicode(r"\alpha + \beta = \gamma")
    assert "β" in latex_to_unicode(r"\alpha + \beta = \gamma")
    assert "γ" in latex_to_unicode(r"\alpha + \beta = \gamma")

    # Subscripts and superscripts
    res = latex_to_unicode("F_{12} = I_{11}^2 + R_0")
    assert "₁₂" in res
    assert "₁₁" in res
    assert "²" in res
    assert "₀" in res

    # Fractions and square roots
    assert "(a)/(b)" in latex_to_unicode(r"\frac{a}{b}")
    assert "√(x)" in latex_to_unicode(r"\sqrt{x}")


def test_render_math_to_texture():
    tex = render_math_to_texture(r"E = \frac{F_{12}}{F_{12} + \gamma F_{11}}", font_size=16.0)
    assert tex is not None
    assert tex.width > 0
    assert tex.height > 0
    assert len(tex.px) == tex.width * tex.height * 4

    # Ensure caching works
    tex2 = render_math_to_texture(r"E = \frac{F_{12}}{F_{12} + \gamma F_{11}}", font_size=16.0)
    assert tex2 is tex


def test_im_math_widget():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 800, 600)):
        im.begin("Math Test Window")
        w, h = im.math(r"\tau = \frac{1}{k_r + k_{nr}}", font_size=14.0)
        assert w > 0
        assert h > 0

        # Math text with alignment
        w2, h2 = im.math_text(r"R_0 = 9780 \cdot (J \cdot \kappa^2 \cdot n^{-4} \cdot \Phi_D)^{1/6}", align_center=True)
        assert w2 > 0
        assert h2 > 0

        # Size calculation
        cw, ch = im.calc_math_size(r"E = mc^2")
        assert cw > 0
        assert ch > 0
        im.end()
