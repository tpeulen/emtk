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
    pytest.importorskip("matplotlib", reason="math rendering needs matplotlib")
    tex = render_math_to_texture(r"E = \frac{F_{12}}{F_{12} + \gamma F_{11}}", font_size=16.0)
    assert tex is not None
    assert tex.width > 0
    assert tex.height > 0
    assert len(tex.px) == tex.width * tex.height * 4

    # Ensure caching works
    tex2 = render_math_to_texture(r"E = \frac{F_{12}}{F_{12} + \gamma F_{11}}", font_size=16.0)
    assert tex2 is tex


def test_im_math_widget():
    pytest.importorskip("matplotlib", reason="math rendering needs matplotlib")
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

        # Auto-scaling with max_width
        w3, h3 = im.math(r"\chi^2 = \sum_{i=1}^N \frac{(y_i - f(x_i))^2}{\sigma_i^2}", max_width=120.0)
        assert w3 <= 120.001
        assert h3 > 0

        im.end()


def test_advanced_math_transforms():
    # Nested fractions
    nested = r"\frac{1}{1 + \frac{R}{R_0}}"
    u_nested = latex_to_unicode(nested)
    assert "(1)/(" in u_nested
    assert "(R)/(R₀)" in u_nested

    # Accents
    u_accents = latex_to_unicode(r"\hat{x} + \bar{y} + \vec{v} + \dot{z}")
    assert "x̂" in u_accents or "x\u0302" in u_accents
    assert "ȳ" in u_accents or "y\u0304" in u_accents
    assert "v⃗" in u_accents or "v\u20D7" in u_accents
    assert "ż" in u_accents or "z\u0307" in u_accents

    # Functions
    u_fn = latex_to_unicode(r"\sin(\theta) + \cos(\phi) + \exp(-t/\tau)")
    assert "sin(θ)" in u_fn
    assert "cos(" in u_fn
    assert "exp(" in u_fn

    # Matrices and cases
    mat = r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"
    norm_mat = normalize_latex(mat)
    assert "a b" in norm_mat
    assert "c d" in norm_mat



@pytest.mark.parametrize("latex, expected", [
    (r"A = \log_{10}(I_0/I)", "A = log₁₀(I₀/I)"),
    (r"\max_i x", "maxᵢ x"),
    (r"\sin\theta", "sin θ"),
    (r"\sinh x", "sinh x"),
    (r"\exp(-t/\tau)", "exp(-t/τ)"),
])
def test_an_operator_name_survives_its_subscript(latex, expected):
    """``\\log_{10}`` lost its ``log``: ``\\b`` does not match before ``_``."""
    from emtk import latex_to_unicode

    assert latex_to_unicode(latex) == expected


def test_a_formula_drawn_as_text_wraps_to_the_column(monkeypatch):
    """When the typesetter declines, the Unicode fallback wraps rather than running past the edge."""
    import emtk.mathtext as mathtext
    from emtk import im
    from emtk.testing import RecordingPainter

    monkeypatch.setattr(mathtext, "render_math_to_texture", lambda *a, **k: None)
    painter = RecordingPainter()
    formula = r"\underbrace{\text{per-trace VBEM}}_{\text{inner: fit each trace to the current prior, then again}}"
    for _ in range(2):
        painter = RecordingPainter()
        with im.frame(painter, (0.0, 0.0, 160.0, 300.0)):
            im.math(formula)
    lines = [t for t in painter.texts if t[5].strip()]
    assert len(lines) > 1, "the fallback text was not wrapped"
    for x, _y, _w, _h, _align, string, *_ in lines:
        assert x + painter.text_width(string) <= 160.0 + 1.0, string
