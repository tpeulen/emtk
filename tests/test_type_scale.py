"""One type scale: every text size is a role, and prose is drawn the size it is measured.

What went wrong, and what each test pins:

* the Markdown widget picked its own sizes (``push_font_scale(1.55)``…), and a
  documentation reader drew its body at a Qt point size -- so help windows and
  the reader disagreed with each other and with the interface. Now every size is
  a role of :mod:`emtk.type_scale`; a guard greps the drawing code for literal
  sizes and a recording run checks every string drawn is at a role's size;
* proportional prose was rasterised at the *logical* size and stretched onto a
  2x display, on hinted 1x advances -- soft and squeezed. Glyphs are now
  rasterised at device resolution and placed on a size-linear layout, so prose
  is the body size on screen at ratio 1 and 2, and the pitch drawn is the
  advance measured;
* ``QuadPainter.set_font_scale`` *replaced* the host's font scale instead of
  multiplying it, so a heading on a larger interface came out smaller than the
  body beneath it;
* a runtime glyph (``✕``) was sized from the cell height, 1.66x too large, and
  squeezed into its advance: the shared close mark read as a letter X.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from emtk import type_scale
from emtk.font import PX_PER_PT, load_atlas
from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

ROOT = pathlib.Path(__file__).resolve().parents[1] / "emtk"

#: The files that draw documentation text. Every size there is a type-scale role.
TEXT_FILES = ("widgets/markdown.py", "help_guide.py")

#: A literal size: a font scale, a ``"size": n`` font dict, a ``font_size=n``,
#: or a direct family push (``push_font("sans-serif")``), which bypasses the roles.
LITERAL = re.compile(
    r"push_font_scale\(|[\"']size[\"']\s*:\s*[\d.]|font_size\s*=\s*[\d.]"
    r"|push_font\(\s*[\"'{]"
)


@pytest.mark.parametrize("name", TEXT_FILES)
def test_documentation_text_has_no_literal_sizes(name):
    source = (ROOT / name).read_text(encoding="utf-8")
    hits = [line.strip() for line in source.splitlines() if LITERAL.search(line)]
    assert not hits, f"{name} sizes text outside emtk.type_scale: {hits}"


def test_the_scale_is_steps_of_one_ratio_around_the_body():
    body = type_scale.size_pt("body")
    assert body == load_atlas().font_pt  # the body *is* the interface font
    assert type_scale.size_pt("code") == body
    assert type_scale.size_pt("caption") == pytest.approx(body / type_scale.STEP)
    sizes = [type_scale.size_pt(r) for r in ("body", "h4", "h3", "h2", "h1")]
    assert sizes == sorted(sizes)
    for low, high in zip(sizes, sizes[1:]):
        assert high / low == pytest.approx(type_scale.STEP)
    assert type_scale.text_font("h2")["bold"] and not type_scale.text_font("body")["bold"]
    assert type_scale.text_font("code")["family"] == type_scale.CODE_FAMILY
    with pytest.raises(ValueError):
        type_scale.size_pt("huge")


def test_the_interface_size_is_one_clamped_setting():
    before = type_scale.ui_font_pt()
    try:
        assert type_scale.set_ui_font_pt(10.0) == 10.0
        assert type_scale.ui_font_pt() == 10.0
        assert type_scale.set_ui_font_pt(100.0) == type_scale.MAX_UI_FONT_PT
        assert type_scale.math_args("body")["font_size"] == pytest.approx(
            2.0 * type_scale.size_pt("body") * type_scale.MAX_UI_FONT_PT / load_atlas().font_pt)
    finally:
        type_scale.set_ui_font_pt(before)


def test_hosts_follow_the_setting():
    from emtk.app import ControlSurface

    surface = ControlSurface(object())
    before = type_scale.ui_font_pt()
    try:
        type_scale.set_ui_font_pt(11.0)
        assert surface.font_pt == 11.0
        surface.font_pt = 9.0  # an explicit size wins
        assert surface.font_pt == 9.0
    finally:
        type_scale.set_ui_font_pt(before)


MARKDOWN = """# Title

Prose with **emphasis** and `code`.

## Section

- an item

### Sub

```python
x = 1
```
"""


def test_every_markdown_string_is_drawn_at_a_role_size():
    from emtk import im
    from emtk.testing import RecordingPainter

    sizes = {round(type_scale.size_pt(r), 6) for r in type_scale.ROLES}

    class Spy(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.spec_size = None
            self.drawn = []

        def set_font(self, value=None, size=0.0):
            super().set_font(value, size)
            self.spec_size = None if value is None else (value.get("size") if isinstance(
                value, dict) else size)

        def text(self, x, y, w, h, align, string, colour, bold=False):
            super().text(x, y, w, h, align, string, colour, bold)
            self.drawn.append((string, self.spec_size))

    spy = Spy()
    with im.frame(spy, (0.0, 0.0, 600.0, 800.0)):
        im.begin("doc")
        im.markdown(MARKDOWN)
        im.end()
    prose = [(s, size) for s, size in spy.drawn
             if any(w in s for w in ("Title", "Prose", "Section", "item", "Sub", "x = 1"))]
    assert len(prose) >= 6, spy.drawn
    for string, size in prose:
        assert size is not None and round(size, 6) in sizes, (string, size)


def test_quad_painter_font_scale_is_relative_to_the_interface_size():
    from emtk.quad_painter import QuadPainter

    base = QuadPainter(font_scale=1.5)
    plain = QuadPainter(font_scale=1.0)
    width = base.text_width("Hello")
    base.set_font_scale(1.3)
    assert base.text_width("Hello") == pytest.approx(1.3 * width)
    assert base.text_width("Hello") > plain.text_width("Hello")
    base.set_font_scale(1.0)
    assert base.text_width("Hello") == pytest.approx(width)


# --------------------------------------------------------------------------- #
# Real pixels through the native host, at ratio 1 and 2
# --------------------------------------------------------------------------- #
PROBE = "HHHHHHHH"
#: Prose pitch probe: a proportional face's capitals nearly touch at 1x, and
#: antialiasing merges them, so the pitch is measured on letters with air between.
PITCH_PROBE = "l l l l l l l l"
SIZE = (260, 100)
#: Where each probe is drawn, logical: the chrome face above, prose below.
CHROME_BOX = (10.0, 4.0, 240.0, 28.0)
PROSE_BOX = (10.0, 36.0, 240.0, 28.0)
PITCH_BOX = (10.0, 68.0, 240.0, 28.0)


class _Probe:
    """Draws PROBE in the interface face and in the prose (body) face."""

    def __init__(self):
        self.advance = {}

    def draw(self, painter, x, y, w, h):
        painter.fill_rect(x, y, w, h, (0, 0, 0, 255))
        self.advance["chrome"] = painter.text_width("H")
        painter.text(*CHROME_BOX, ALIGN_LEFT | ALIGN_VCENTER, PROBE, (255, 255, 255, 255))
        painter.set_font(type_scale.text_font("body"))
        self.advance["prose"] = painter.text_width("l ")
        self.prose_width = painter.text_width(PITCH_PROBE)
        painter.text(*PROSE_BOX, ALIGN_LEFT | ALIGN_VCENTER, PROBE, (255, 255, 255, 255))
        painter.text(*PITCH_BOX, ALIGN_LEFT | ALIGN_VCENTER, PITCH_PROBE, (255, 255, 255, 255))
        painter.set_font(None)


def _ink(pixels, box, ratio, glyphs=8):
    x, y, w, h = (int(round(v * ratio)) for v in box)
    rgb = np.asarray(pixels)[y:y + h, x:x + w, :3].astype(float)
    mask = rgb.mean(axis=2) > 110.0
    rows = np.flatnonzero(mask.any(axis=1))
    inked = mask.any(axis=0)
    starts = [c for c in range(1, inked.size) if inked[c] and not inked[c - 1]]
    if inked[0]:
        starts.insert(0, 0)
    assert len(starts) == glyphs, f"{len(starts)} glyphs, not {glyphs}"
    cols = np.flatnonzero(inked)
    return {"cap": float(rows[-1] - rows[0] + 1) / ratio,
            "pitch": float(np.diff(starts).mean()) / ratio,
            "span": float(cols[-1] - cols[0] + 1) / ratio}


def _cap(pixels, box, ratio):
    x, y, w, h = (int(round(v * ratio)) for v in box)
    mask = np.asarray(pixels)[y:y + h, x:x + w, :3].astype(float).mean(axis=2) > 110.0
    rows = np.flatnonzero(mask.any(axis=1))
    return float(rows[-1] - rows[0] + 1) / ratio


@pytest.fixture(scope="module")
def device():
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_prose_is_the_body_size_and_drawn_as_measured(device, ratio):
    from rendercanvas.offscreen import RenderCanvas

    from emtk.native import NativeHost

    probe = _Probe()
    host = NativeHost(probe, canvas=RenderCanvas(size=SIZE, pixel_ratio=ratio), device=device)
    image = np.asarray(host.draw_frame())
    chrome = _ink(image, CHROME_BOX, ratio)
    prose = _ink(image, PITCH_BOX, ratio)
    prose["cap"] = _cap(image, PROSE_BOX, ratio)
    # The body size: prose capitals as tall as the interface's, within a pixel ...
    assert prose["cap"] == pytest.approx(chrome["cap"], abs=1.0)
    # ... and the cap height an em of the body size implies (~0.72 em).
    em = type_scale.size_pt("body") * PX_PER_PT
    assert prose["cap"] == pytest.approx(0.72 * em, rel=0.2)
    # Drawn as measured: glyph pitch is the measured advance (no squeeze) ...
    assert prose["pitch"] == pytest.approx(probe.advance["prose"], abs=0.5)
    # ... and the ink never runs past the measured width.
    # (pitch probe: "l " pairs, so the pitch is the advance of "l ")
    assert prose["span"] <= probe.prose_width + 1.0


def test_prose_glyphs_are_rasterised_at_device_resolution():
    """At ratio 2 a glyph is a 2x raster occupying the same logical box -- not a 1x one stretched."""
    from emtk import font_render

    spec = font_render.font_spec(type_scale.text_font("body"))
    (tex1, x1, y1, w1, h1), = font_render.glyphs(spec, "H", 1.0, device=1.0)
    (tex2, x2, y2, w2, h2), = font_render.glyphs(spec, "H", 1.0, device=2.0)
    # (a glyph texture carries one texel of padding on each side, and one more
    # on the right for the sub-pixel pen phase)
    assert tex2.height - 2 >= 1.8 * (tex1.height - 2)
    # the ink boxes (padding removed: 3 texels across, 2 down) agree within a 1x pixel
    assert w2 - 3 / 2 == pytest.approx(w1 - 3, abs=1.0)
    assert h2 - 2 / 2 == pytest.approx(h1 - 2, abs=1.0)
    # Pen position comes from the size-linear layout, not the raster: the same at both.
    assert x2 == pytest.approx(x1, abs=0.6)
    assert font_render.text_width(spec, "Hamburg", 2.0) == pytest.approx(
        2.0 * font_render.text_width(spec, "Hamburg", 1.0))


def test_runtime_close_mark_is_the_size_of_the_baked_one():
    from emtk.pil_painter import PilPainter

    def ink_height(char):
        p = PilPainter(40, 40, background=(0, 0, 0, 255))
        p.text(4, 4, 30, 30, 0, char, (255, 255, 255, 255))
        mask = np.asarray(p.frame)[..., :3].mean(axis=2) > 100
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        return rows[-1] - rows[0] + 1, cols[-1] - cols[0] + 1

    baked = ink_height("×")  # × is in the bake
    runtime = ink_height("✕")  # ✕ is rasterised on demand
    assert abs(runtime[0] - baked[0]) <= 2 and abs(runtime[1] - baked[1]) <= 2
    # Not the letter: an X is a cap height tall, the close mark is not.
    assert runtime[0] < ink_height("X")[0]


def test_the_style_editor_exposes_the_setting():
    from emtk import im
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    with im.frame(painter, (0.0, 0.0, 600.0, 900.0)):
        im.begin("style")
        im.show_style_editor()
        im.end()
    assert any("Interface font size" in s for s in painter.strings)
