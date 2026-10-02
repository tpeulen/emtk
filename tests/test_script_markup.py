"""Tests for inline sub/superscript markup and wrap-aware coloured text.

``convert_script_markup`` turns ``R_{0}`` / ``x^{2}`` in *any* label into the
Unicode forms the atlas renders, and :func:`emtk.im.text` (and every
``text_colored`` caller, widget labels included) draws and measures them
converted. ``push_text_wrap_pos`` now also wraps ``text_colored``/``text_disabled``
like the reference wraps ``Text`` under ``PushTextWrapPos``.
"""

from emtk import im
from emtk.mathtext import convert_script_markup
from emtk.testing import RecordingPainter


def test_convert_script_markup_basic():
    assert convert_script_markup("R_{0} [Ang]") == "R₀ [Ang]"
    assert convert_script_markup("x^{2}") == "x²"
    assert convert_script_markup("y_{12}") == "y₁₂"
    assert convert_script_markup("kappa^{2}") == "kappa²"


def test_convert_script_markup_requires_braces():
    # Plain underscores/carets (file names, units) must not be touched.
    assert convert_script_markup("my_file.txt") == "my_file.txt"
    assert convert_script_markup("a^b") == "a^b"


def test_convert_script_markup_unmapped_group_kept():
    # "Q" has no Unicode subscript form: keep the source readable.
    assert convert_script_markup("R_{Q}") == "R_{Q}"


def test_convert_script_markup_escape():
    assert convert_script_markup(r"\_{0}") == "_{0}"
    assert convert_script_markup(r"\^{2}") == "^{2}"


def test_convert_script_markup_noop_without_markers():
    assert convert_script_markup("plain text") == "plain text"


def test_draw_converts_markup():
    """add_text draws the converted string, and measures it converted too."""
    from emtk.drawlist import DrawList

    p = RecordingPainter()
    draw = DrawList(p)
    draw.add_text((0, 0), (255, 255, 255, 255), "R_{0}")
    assert p.strings == ["R₀"]

    width = draw.calc_text_size("R_{0}")[0]
    assert width == p.text_width("R₀")


def test_label_text_renders_markup():
    """The LabelText caption path renders sub/superscripts."""

    def gui():
        im.begin("markup", (0, 0, 320, 200))
        im.label_text("R_{0} [Ang]", "54.0")
        im.end()

    p = RecordingPainter()
    from emtk.im_core import frame

    with frame(p, (0.0, 0.0, 320.0, 200.0)):
        gui()

    assert "R₀ [Ang]" in p.strings
    assert "54.0" in p.strings


def test_text_colored_wraps_under_wrap_pos():
    """push_text_wrap_pos makes plain text wrap like TextWrapped."""

    def gui():
        im.begin("wrap", (0, 0, 200, 300))
        im.push_text_wrap_pos()
        im.text(
            "The transition dipole of a fluorophore pair defines the "
            "orientation factor"
        )
        im.pop_text_wrap_pos()
        im.end()

    p = RecordingPainter()
    from emtk.im_core import frame

    with frame(p, (0.0, 0.0, 200.0, 300.0)):
        gui()

    joined = " ".join(p.strings)
    # Wrapped into several drawn lines, none wider than the box.
    assert len(p.strings) >= 2
    for line in p.strings:
        assert p.text_width(line) <= 200.0 + 1e-6
    assert "orientation factor" in joined


def test_text_disabled_wraps_too():
    def gui():
        im.begin("wrap-disabled", (0, 0, 180, 300))
        im.push_text_wrap_pos(0.0)
        im.text_disabled("Two atoms per dye define the transition dipole")
        im.pop_text_wrap_pos()
        im.end()

    p = RecordingPainter()
    from emtk.im_core import frame

    with frame(p, (0.0, 0.0, 180.0, 300.0)):
        gui()

    assert len(p.strings) >= 2


def test_negative_wrap_pos_disables_wrapping():
    def gui():
        im.begin("nowrap", (0, 0, 200, 300))
        im.push_text_wrap_pos(-1)
        im.text("one long line that would certainly need wrapping otherwise")
        im.pop_text_wrap_pos()
        im.end()

    p = RecordingPainter()
    from emtk.im_core import frame

    with frame(p, (0.0, 0.0, 200.0, 300.0)):
        gui()

    assert len(p.strings) == 1


def test_no_wrap_stack_keeps_single_line():
    def gui():
        im.begin("plain", (0, 0, 200, 300))
        im.text("one long line that would certainly need wrapping otherwise")
        im.end()

    p = RecordingPainter()
    from emtk.im_core import frame

    with frame(p, (0.0, 0.0, 200.0, 300.0)):
        gui()

    assert len(p.strings) == 1
