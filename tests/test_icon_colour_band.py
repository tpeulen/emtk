"""The atlas's colour band: baked emoji, drawn in colour, at every font size.

The monochrome pictograph bake gave the web page *a* glyph where it had the
``¤`` placeholder, and the owner read it exactly right: "the icons are super
ugly and black and white". The band here is the replacement -- the same
pictographs baked again from a pinned Noto Color Emoji into 128 px RGBA cells
(``chrome.json``'s ``icons`` table), and an icon path that reads them before
it asks the machine for a colour font. Colour comes from the bake, scaling
from the icon box being a line height, and the bake is byte-for-byte
repeatable, because the atlas is committed and a bake that depends on whose
font it found is not a bake.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import numpy as np
import pytest

pytest.importorskip("PIL")

from emtk import font, icons  # noqa: E402
from emtk.painter import ALIGN_VCENTER  # noqa: E402
from emtk.quad_painter import FLOATS_PER_VERTEX, VERTICES_PER_QUAD, QuadPainter  # noqa: E402
from emtk.testing import PixelPainter  # noqa: E402

SAMPLE = ("🤖", "🧬", "📊", "⚖", "🔬")


def _baker():
    """The bake script, imported from the checkout it lives in."""
    root = pathlib.Path(font.__file__).resolve().parents[1]
    path = root / "tools" / "bake_chrome_atlas.py"
    if not path.is_file():  # an installed emtk without its checkout
        pytest.skip("no tools/bake_chrome_atlas.py beside this checkout")
    spec = importlib.util.spec_from_file_location("bake_chrome_atlas", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def atlas_rgba():
    """``(rgba, meta)``: the committed atlas and its JSON."""
    from PIL import Image

    image = np.array(
        Image.open(font.ATLAS_DIR / "chrome.png").convert("RGBA"), dtype=np.uint8
    )
    meta = json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))
    return image, meta


def test_the_committed_atlas_ships_a_colour_band(atlas_rgba):
    """The band is there, its cells are where the JSON says, and they fit."""
    image, meta = atlas_rgba
    icons_table = meta.get("icons") or {}
    assert len(icons_table) >= 100, f"only {len(icons_table)} colour cells baked"
    assert meta["icon_cell"] == [128, 128]
    height, width = image.shape[:2]
    assert width <= 8192 and height <= 8192, meta["size"]
    for char, (x, y, w, h) in icons_table.items():
        assert (w, h) == tuple(meta["icon_cell"]), char
        assert x + w <= width and y + h <= height, f"{char!r} outside the sheet"


@pytest.mark.parametrize("char", SAMPLE)
def test_a_baked_cell_is_colour_not_a_grey_mask(char, atlas_rgba):
    """The band replaces the grey bake: real chroma, from the bake, not a tint."""
    image, meta = atlas_rgba
    cell = meta["icons"][char]
    x, y, w, h = cell
    rgba = image[y:y + h, x:x + w]
    opaque = rgba[..., 3] > 64
    assert opaque.any(), f"{char!r} baked blank"
    r, g, b = rgba[..., 0][opaque].astype(int), rgba[..., 1][opaque].astype(int), \
        rgba[..., 2][opaque].astype(int)
    chromatic = int(((r != g) | (g != b)).sum())
    assert chromatic > 30, f"{char!r} baked as a monochrome mask ({chromatic} chroma texels)"


@pytest.mark.parametrize("char", SAMPLE)
def test_a_baked_cell_is_the_ink_fitted_and_centred(char, atlas_rgba):
    """Crop-to-ink and centre: what the runtime does with its own rasters."""
    from PIL import Image

    image, meta = atlas_rgba
    x, y, w, h = meta["icons"][char]
    cell = Image.fromarray(image[y:y + h, x:x + w])
    left, top, right, bottom = cell.getchannel("A").getbbox()
    assert max(right - left, bottom - top) >= w - 8, f"{char!r} baked small"
    assert abs(left - (w - right)) <= 4 and abs(top - (h - bottom)) <= 4, \
        f"{char!r} not centred in its cell"


def test_the_pure_symbols_have_no_colour_cell(atlas_rgba):
    """├ ─ ◐ ▶ stay monospace-face masks: monochrome behaviour unchanged."""
    _image, meta = atlas_rgba
    icons_table = meta.get("icons") or {}
    for symbol in ("├", "└", "│", "─", "◐", "▶", "≔", "⟵"):
        assert symbol not in icons_table, f"{symbol!r} grew a colour cell"
        assert font.load_atlas().cell_of(symbol) is not None, \
            f"{symbol!r} lost its monochrome cell"


def test_the_runtime_reads_a_baked_cell_back():
    """``icons`` crops the band the way the docstring says, and it is colour."""
    texture, colour = icons.icon_texture("🤖", 32)
    assert texture is not None and colour
    assert icons._atlas_ink("🤖") is not None
    # a cluster with its presentation selector resolves to the same base cell
    assert icons._atlas_ink("⚖️") is not None


def _caption(scale: float) -> PixelPainter:
    """\"🤖 density\" through the real text path, text colour pure red."""
    painter = PixelPainter(640, 160, background=(0, 0, 0, 255))
    painter.set_font_scale(scale)
    painter.text(4.0, 4.0, 630.0, 150.0, ALIGN_VCENTER, "🤖 density",
                 (255, 0, 0, 255))
    return painter


def _chromatic_bbox(pixels: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box ``(x0, y0, x1, y1)`` of pixels that are neither red nor black."""
    r = pixels[..., 0].astype(int)
    g = pixels[..., 1].astype(int)
    b = pixels[..., 2].astype(int)
    red_text = (r > 200) & (g < 60) & (b < 60)
    dark = (r < 10) & (g < 10) & (b < 10)
    other = (pixels[..., 3] > 0) & ~red_text & ~dark
    ys, xs = np.nonzero(other)
    assert len(xs), "nothing drawn but the text colour"
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def test_a_colour_cell_draws_its_own_pixels_not_the_text_colour():
    """The CPU painter: the robot keeps its colours under a red pen."""
    painter = _caption(1.0)
    pixels = np.frombuffer(bytes(painter.px), dtype=np.uint8).reshape(
        painter.height, painter.width, 4
    )
    r = pixels[..., 0].astype(int)
    g = pixels[..., 1].astype(int)
    b = pixels[..., 2].astype(int)
    red_text = (r > 200) & (g < 60) & (b < 60)
    dark = (r < 10) & (g < 10) & (b < 10)
    other = (pixels[..., 3] > 0) & ~red_text & ~dark
    # the icon's own colours: chromatic texels that are not the text colour
    chromatic = other & ((r != g) | (g != b))
    assert int(chromatic.sum()) > 50, "the icon drew as the text colour's mask"


def test_the_gpu_painter_emits_the_baked_cell_as_an_untinted_image():
    """The GPU path: an image quad, white tint -- the shader's pass-through."""
    painter = QuadPainter()
    seen: list = []
    painter.image_uv_resolver = lambda handle: seen.append(
        getattr(handle, "icon", None)) or ((0.25, 0.25), (0.75, 0.75))
    painter.text(0, 0, 200, 20, ALIGN_VCENTER, "🤖 EN", (255, 255, 255, 255))
    assert "🤖" in seen, "the colour cell went through the text (tinted) path"
    vertices = painter.vertices().reshape(-1, FLOATS_PER_VERTEX)
    u, v = vertices[:, 2], vertices[:, 3]
    # the resolver's region rides the quad: the icon went out as an image
    region = (u > 0.2) & (u < 0.8) & (v > 0.2) & (v < 0.8)
    assert int(region.sum()) == VERTICES_PER_QUAD, "no image quad for the icon"
    # white tint -- draw_icon's colour branch leaves the RGB to the texture
    assert np.allclose(np.unique(vertices[region][:, 4:7], axis=0),
                       [[1.0, 1.0, 1.0]])
    # and no glyph quad points into the colour band, where the shader's
    # coverage-tint path would flatten the picture to the text colour
    meta = json.loads((font.ATLAS_DIR / "chrome.json").read_text(encoding="utf-8"))
    x, y, w, h = meta["icons"]["🤖"]
    in_band = (u >= x) & (u <= x + w) & (v >= y) & (v <= y + h)
    assert not in_band.any()


def test_at_two_font_sizes_the_icon_scales_and_stays_colour():
    """One icon, two sizes: the box tracks the line height, the colour stays."""
    first = _caption(1.0)
    second = _caption(2.0)
    small = np.frombuffer(bytes(first.px), dtype=np.uint8).reshape(
        first.height, first.width, 4)
    large = np.frombuffer(bytes(second.px), dtype=np.uint8).reshape(
        second.height, second.width, 4)
    x0, y0, x1, y1 = _chromatic_bbox(small)
    X0, Y0, X1, Y1 = _chromatic_bbox(large)
    w1, h1 = x1 - x0 + 1, y1 - y0 + 1
    w2, h2 = X1 - X0 + 1, Y1 - Y0 + 1
    assert w2 > w1 * 1.5 and h2 > h1 * 1.5, \
        f"the icon did not scale with the font size ({w1}x{h1} -> {w2}x{h2})"
    for pixels in (small, large):
        r = pixels[..., 0].astype(int)
        g = pixels[..., 1].astype(int)
        b = pixels[..., 2].astype(int)
        chromatic = ((pixels[..., 3] > 0) & ((r != g) | (g != b))).sum()
        assert chromatic > 50, "the icon lost its colour at a drawn size"


@pytest.mark.slow
def test_a_bake_is_deterministic(tmp_path):
    """Two bakes, one atlas: identical PNG and JSON bytes.

    The atlas is committed, so a bake that cannot repeat itself rewrites every
    icon on every re-run and buries real diffs. It needs the pinned emoji font
    (fetched and hash-verified by the baker) and Qt for the monospace faces.
    """
    baker = _baker()
    try:
        baker._emoji_font()
    except RuntimeError as error:
        pytest.skip(f"no pinned emoji font available: {error}")
    one, two = tmp_path / "a", tmp_path / "b"
    baker.bake(one)
    baker.bake(two)
    for name in ("chrome.png", "chrome.json"):
        assert (one / name).read_bytes() == (two / name).read_bytes(), \
            f"{name} differs between two bakes"
