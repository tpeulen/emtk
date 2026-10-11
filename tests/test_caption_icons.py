"""A pictogram typed into a caption is drawn in colour, in one small icon box.

``"❓  Help"`` used to go through the text path whole, so its ❓ came out as a
grey mask squeezed into one monospace cell while the tool icons beside it were
colour images. The real painters now split a caption into runs
(:func:`emtk.icons.pictogram_runs`): a colour cluster is drawn with
``icons.draw_icon`` in a box of :func:`emtk.icons.icon_box`, the rest as text,
and ``text_width`` measures exactly that. What a recording painter records --
and what tests click on -- is still the whole caption string.
"""
from __future__ import annotations

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.icons import icon_box, pictogram_runs
from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
from emtk.quad_painter import QuadPainter
from emtk.testing import PixelPainter, _ScreenshotPainter

pytestmark = pytest.mark.skipif(pictogram_runs("❓ x") is None,
                                reason="no colour-emoji font on this machine")

ALIGN = ALIGN_LEFT | ALIGN_VCENTER


class _Runs(PixelPainter):
    """A pixel painter that also records each text run and each image tint."""

    def __init__(self, width=320, height=60):
        super().__init__(width, height)
        self.runs = []
        self.tints = []

    def _text_run(self, x, y, w, h, align, string, colour, bold=False):
        self.runs.append((x, string))
        super()._text_run(x, y, w, h, align, string, colour, bold)

    def image(self, x, y, w, h, handle, uv0=(0.0, 0.0), uv1=(1.0, 1.0),
              tint=(255, 255, 255, 255)):
        self.tints.append((getattr(handle, "icon", None), x, y, w, h, tuple(tint)))
        super().image(x, y, w, h, handle, uv0, uv1, tint)


def test_runs_split_colour_clusters_and_leave_masks_as_text():
    assert pictogram_runs("❓  Help") == (("❓", True), ("  Help", False))
    assert pictogram_runs("🌍 EN") == (("🌍", True), (" EN", False))
    # a skin-tone modifier stays with its emoji
    assert pictogram_runs("👍🏽 ok")[0] == ("👍🏽", True)
    # a leading pictograph whose U+FE0F icon_text dropped is still an icon
    assert pictogram_runs("⚙ Settings")[0] == ("⚙", True)
    # glyphs with no colour form, plain text, and explicit text presentation
    for plain in ("◐ half", "✕", "Next › more", "Next → Intensity", "Fläche", "© 2024",
                  "▶ Run", "Help", "⚙︎ Settings"):
        assert pictogram_runs(plain) is None, plain


def test_caption_draws_a_colour_image_and_records_the_whole_string():
    p = _ScreenshotPainter(240, 40)
    p.fill_rect(0, 0, 240, 40, (40, 40, 40, 255))
    p.text(10, 8, 200, 24, ALIGN, "❓  Help", (220, 220, 220, 255))
    assert p.strings == ["❓  Help"]
    assert [icon for icon, *_ in p.icons] == ["❓"]
    icon, x, y, w, h = p.icons[0]
    assert (x, w, h) == (10, icon_box(p.line_height()), icon_box(p.line_height()))
    # the ❓ is red, not the grey of the text colour
    reds = 0
    for yy in range(int(y), int(y + h)):
        for xx in range(int(x), int(x + w)):
            o = (yy * p.width + xx) * 4
            r, g, b = p.px[o], p.px[o + 1], p.px[o + 2]
            reds += r > 150 and g < 100 and b < 100
    assert reds > 5


def test_width_is_what_is_drawn():
    p = _Runs()
    caption = "📖  Guide"
    box = icon_box(p.line_height())
    assert p.text_width(caption) == pytest.approx(box + p._text_run_width("  Guide"))
    p.text(5, 5, 200, 24, ALIGN, caption, (255, 255, 255, 255))
    (icon,) = p.tints
    assert icon[0] == "📖" and icon[1] == 5 and icon[3] == box
    assert p.runs == [(5 + box, "  Guide")]
    # right alignment puts the caption's measured right edge on the box edge
    from emtk.painter import ALIGN_RIGHT

    p = _Runs()
    p.text(0, 5, 200, 24, ALIGN_RIGHT | ALIGN_VCENTER, caption, (255, 255, 255, 255))
    x, string = p.runs[0]
    assert x + p._text_run_width(string) == pytest.approx(200)


def test_a_faded_text_colour_fades_the_icon():
    p = _Runs()
    p.text(5, 5, 200, 24, ALIGN, "❓  Help", (200, 200, 200, 153))
    assert p.tints[0][5][3] == 153


def test_a_disabled_button_fades_its_icon():
    p = _Runs(400, 200)

    def frame():
        im.begin("w")
        im.begin_disabled(True)
        im.button("❓  Help")
        im.end_disabled()
        im.button("📖  Guide")
        im.end()

    app = ImApp(frame)
    for _ in range(2):
        p.tints.clear()
        app.draw(p, 0, 0, 400, 200)
    tints = {icon: tint for icon, *_rest, tint in p.tints}
    assert tints["❓"][3] < 255
    assert tints["📖"][3] == 255


def test_gpu_painter_emits_the_icon_as_an_image():
    p = QuadPainter()
    images = []
    p.image_uv_resolver = lambda handle: images.append(getattr(handle, "icon", None)) or (
        (0.0, 0.0), (1.0, 1.0))
    p.text(0, 0, 200, 20, ALIGN, "🌍 EN", (255, 255, 255, 255))
    assert "🌍" in images
    assert p.text_width("🌍 EN") == pytest.approx(
        icon_box(p.line_height()) + p._text_run_width(" EN"))
