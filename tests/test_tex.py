"""emtk.tex: the math typesetter behind emtk.mathtext (no plotting library)."""

from __future__ import annotations

import sys

import pytest

tex = pytest.importorskip("emtk.tex")
try:
    tex._families()
except tex.TexError:  # pragma: no cover - a machine with no serif italic face
    pytest.skip("no serif face with an italic style installed", allow_module_level=True)


def _glyphs(layout):
    return [it for it in layout.items if it[0] == "glyph"]


def test_superscript_is_raised_and_subscript_lowered():
    layout = tex.typeset("x_i^2", 40)
    base, sup, sub = None, None, None
    for it in _glyphs(layout):
        if it[3] == "x":
            base = it
        elif it[3] == "2":
            sup = it
        elif it[3] == "i":
            sub = it
    assert sup[2] < base[2] < sub[2]                  # y grows downwards
    assert sup[7] < base[7] and sub[7] < base[7]      # smaller script size
    assert sup[1] == pytest.approx(sub[1], abs=6.0)   # stacked, not side by side


def test_a_fraction_puts_its_bar_on_the_math_axis_between_its_parts():
    layout = tex.typeset(r"\frac{a}{b}", 40)
    (rule,) = [it for it in layout.items if it[0] == "rule"]
    a = next(it for it in _glyphs(layout) if it[3] == "a")
    b = next(it for it in _glyphs(layout) if it[3] == "b")
    assert a[2] < rule[2] < rule[4] < b[2]
    # The bar sits above the baseline (on the axis), not on it.
    assert -0.4 * 40 < (rule[2] + rule[4]) / 2 < 0


def test_operators_and_relations_get_their_spaces():
    tight = tex.typeset("ab", 40).width
    plus = tex.typeset("a+b", 40).width - tex.typeset("+", 40).width
    equals = tex.typeset("a=b", 40).width - tex.typeset("=", 40).width
    assert plus > tight + 0.3 * 40 * 4 / 18
    assert equals > plus                              # thick space > medium space
    # A leading minus is a sign, not an operator: no space after it.
    assert tex.typeset("-a", 40).width < tex.typeset("b-a", 40).width - tex.typeset("b", 40).width


def test_an_accent_sits_over_its_letter():
    layout = tex.typeset(r"\hat{x}", 40)
    x = next(it for it in _glyphs(layout) if it[3] == "x")
    hat = next(it for it in _glyphs(layout) if it[3] != "x")
    xl, xt, xr, _ = tex._ink(*x[4:7], x[7], "x")
    hl, _, hr, hb = tex._ink(*hat[4:7], hat[7], hat[3])
    centre_x = x[1] + (xl + xr) / 2
    centre_hat = hat[1] + (hl + hr) / 2
    assert abs(centre_hat - centre_x) < 0.15 * 40
    assert hat[2] + hb <= x[2] + xt                   # above the letter's ink
    assert hat[2] + hb > x[2] + xt - 0.3 * 40         # ... but close to it


def test_alphabets_and_bold():
    script_l = next(it for it in _glyphs(tex.typeset(r"\mathcal{L}", 30)))
    assert script_l[3] == "ℒ"
    reals = next(it for it in _glyphs(tex.typeset(r"\mathbb{R}", 30)))
    assert reals[3] == "ℝ"
    bold = next(it for it in _glyphs(tex.typeset(r"\mathbf{A}", 30)))
    assert bold[6] is True                            # a bold face, not the regular one


def test_display_style_stacks_the_limits_of_a_sum():
    inline = tex.typeset(r"\sum_{i=1}^{N} x", 30)
    display = tex.typeset(r"\sum_{i=1}^{N} x", 30, display=True)
    assert display.height > inline.height and display.depth > inline.depth


def test_unknown_commands_raise():
    with pytest.raises(tex.TexError):
        tex.typeset(r"\nosuchcommand{x}", 20)
    with pytest.raises(tex.TexError):
        tex.typeset(r"\frac{a}", 20)


def test_mathtext_renders_without_matplotlib(monkeypatch):
    """The texture route must not reach for matplotlib any more."""
    from emtk import mathtext

    monkeypatch.setitem(sys.modules, "matplotlib", None)
    cache = mathtext.MathTextureCache()
    texture = mathtext.render_math_to_texture(r"G(\tau) = \frac{1}{N}", colour=(0, 0, 0, 255),
                                             cache=cache)
    assert texture is not None and texture.width > texture.height > 10
    w, h = mathtext.calc_math_size(r"G(\tau) = \frac{1}{N}")
    assert w == pytest.approx(texture.width * 0.5, abs=2) and h == pytest.approx(
        texture.height * 0.5, abs=2)


def test_renders_ink_in_the_requested_colour():
    w, h, px, baseline = tex.render_rgba("x^2", 30, colour=(200, 10, 10, 255))
    assert 0 < baseline < h
    inked = [px[i:i + 4] for i in range(0, len(px), 4) if px[i + 3] > 200]
    assert inked and all(p[0] > 150 and p[1] < 80 for p in inked)
