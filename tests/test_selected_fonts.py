"""Actual face selection changes ink and layout without introducing Qt."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytest.importorskip("PIL")
from emtk.font import available_fonts, load_atlas
from emtk.font_render import _faces, _glyph, font_spec
from emtk.gpu_atlas import ImageAtlas
from emtk.painter import ALIGN_HCENTER, ALIGN_VCENTER
from emtk.pil_painter import PilPainter
from emtk.quad_painter import QuadPainter
from emtk.testing import PixelPainter, RecordingPainter


@pytest.fixture
def family():
    choices = available_fonts(monospaced=True)
    for preferred in ("Menlo", "DejaVu Sans Mono", "Courier New", "Liberation Mono"):
        if preferred in choices:
            return preferred
    selected = next((name for name in choices if name != "monospace"), None)
    if selected is None:
        pytest.skip("No system mono font")
    return selected


def painters():
    quad = QuadPainter()
    atlas = ImageAtlas(1024, 1024)
    quad.image_uv_resolver = atlas.region
    return [PilPainter(260, 120), PixelPainter(260, 120), quad]


def test_default_metrics_and_reset_are_unchanged(family):
    atlas = load_atlas()
    for p in painters():
        original = p.text_width("Hello"), p.line_height()
        assert original == (atlas.advance("Hello"), atlas.line_height)
        p.set_font({"family": family, "size": 18})
        assert p.text_width("Hello") > original[0]
        p.set_font(None)
        assert (p.text_width("Hello"), p.line_height()) == original


def test_actual_font_metrics_agree_between_backends(family):
    metrics = []
    for p in painters():
        p.set_font({"family": family, "size": 14})
        p.set_font_scale(1.25)
        metrics.append((p.text_width("Hello WMi"), p.line_height()))
        p.text(
            4, 4, 250, 100, ALIGN_HCENTER | ALIGN_VCENTER, "Hello WMi", (240, 220, 210)
        )
    assert metrics[0] == metrics[1] == metrics[2]
    assert RecordingPainter().text_width("Hello") == 35


def test_face_selection_changes_real_cpu_ink(family):
    for cls in (PilPainter, PixelPainter):
        p = cls(260, 120)
        p.text(10, 10, 240, 90, 0, "WWW iii", (255, 255, 255))
        old = bytes(p.px)
        p = cls(260, 120)
        p.set_font({"family": family, "size": 18})
        p.text(10, 10, 240, 90, 0, "WWW iii", (255, 255, 255))
        assert bytes(p.px) != old
        assert any(p.px[0::4])


def test_proportional_family_has_real_variable_metrics():
    family = next(
        (
            name
            for name in available_fonts()
            if name != "monospace" and not _faces()[name][0].monospaced
        ),
        None,
    )
    if family is None:
        pytest.skip("No proportional system font")
    p = PilPainter(260, 120)
    p.set_font(family)
    assert p.text_width("iiii") != p.text_width("MMMM")


def test_unsupported_choice_is_explicit_and_preserves_state(family):
    for p in painters():
        p.set_font(family, 14)
        before = p.text_width("Hello")
        with pytest.raises(ValueError, match="not available"):
            p.set_font("Definitely not an installed font 12345")
        assert p.text_width("Hello") == before
        with pytest.raises(ValueError, match="italic"):
            p.set_font({"family": "monospace", "italic": True})
        with pytest.raises(ValueError, match="size"):
            p.set_font(family, float("nan"))


def test_baked_size_and_bold_are_supported_without_system_fonts():
    p = PilPainter(260, 120)
    original = p.text_width("Hello")
    p.set_font({"family": "monospace", "size": 16, "bold": True})
    assert p.text_width("Hello") == original * 2
    p.text(0, 0, 250, 110, 0, "Hello", (255, 255, 255))
    assert any(p.px[0::4])


def test_rotated_selected_font_emits_image_triangles(family):
    p = painters()[-1]
    p.set_font(family, 14)
    p.text_rotated(10, 10, 120, 90, 0, "Hi", (255, 255, 255), 45)
    assert p.vertex_count == 12
    assert p._tris


def test_gpu_without_image_resolver_fails_instead_of_fake_text(family):
    p = QuadPainter()
    p.set_font(family)
    with pytest.raises(RuntimeError, match="image atlas resolver"):
        p.text(0, 0, 100, 40, 0, "Hi", (255, 255, 255))


def test_glyph_cache_is_bounded():
    assert _glyph.cache_info().maxsize == 512


def test_generic_families_resolve_to_real_faces():
    for family in ("sans-serif", "serif"):
        spec = font_spec({"family": family, "bold": True})
        assert spec.family in available_fonts()
        assert spec.family != family


def test_bold_and_italic_change_actual_ink():
    spec = font_spec("sans-serif", 16)
    pictures = []
    for bold, italic in ((False, False), (True, False), (False, True)):
        p = PilPainter(260, 120)
        p.set_font({"family": spec.family, "size": 16, "bold": bold, "italic": italic})
        p.text(10, 10, 240, 90, 0, "Font appearance", (255, 255, 255))
        pictures.append(bytes(p.px))
    assert len(set(pictures)) == 3


def test_different_real_families_at_the_same_size_have_different_ink(family):
    candidates = available_fonts(monospaced=True)
    second = next(
        (
            name
            for name in ("Courier New", "Liberation Mono", "DejaVu Sans Mono", "Menlo")
            if name in candidates and name != family
        ),
        None,
    )
    if second is None:
        pytest.skip("Need two different installed designs")
    frames = []
    for name in (family, second):
        p = PilPainter(260, 120)
        p.set_font(name, 16)
        p.text(10, 10, 240, 90, 0, "Hello 0123 café", (255, 255, 255))
        frames.append(bytes(p.px))
    assert frames[0] != frames[1]


def test_offscreen_gpu_draws_selected_face(family, tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("wgpu")
    from emtk.wgpu_host import WgpuRenderer, default_device

    try:
        device = default_device()
    except RuntimeError as error:
        if "Request adapter failed" not in str(error):
            raise
        pytest.skip(f"GPU adapter unavailable: {error}")

    renderer = WgpuRenderer(device=device)
    p = renderer.painter()
    p.set_font(family, 18)
    p.text(10, 10, 240, 90, 0, "Hello", (255, 255, 255))
    gpu = renderer.grab(p, 260, 120, background=(0, 0, 0))
    cpu = PilPainter(260, 120)
    cpu.set_font(family, 18)
    cpu.text(10, 10, 240, 90, 0, "Hello", (255, 255, 255))
    cpu_pixels = np.asarray(cpu.frame)
    gy, gx = np.nonzero(gpu[:, :, :3].max(axis=2) > 40)
    cy, cx = np.nonzero(cpu_pixels.max(axis=2) > 40)
    assert len(gx) > 100
    assert abs(gx.min() - cx.min()) <= 2
    assert abs(gx.max() - cx.max()) <= 2
    assert abs(gy.min() - cy.min()) <= 2
    assert abs(gy.max() - cy.max()) <= 2
    # Concrete artifacts for independent visual review, not a self verdict.
    from PIL import Image

    Image.fromarray(gpu).save(tmp_path / "selected-font-gpu.png")
    cpu.frame.save(tmp_path / "selected-font-cpu.png")
    # Same-size family/style sheet makes independent review meaningful rather
    # than merely comparing the default8pt bake with one larger system face.
    q = renderer.painter()
    sheet = PilPainter(640, 260, background=(18, 20, 24))
    rows = [
        (family, False, False),
        (font_spec("serif").family, False, False),
        (font_spec("sans-serif").family, False, False),
        (font_spec("sans-serif").family, True, False),
        (font_spec("sans-serif").family, False, True),
    ]
    for index, (name, bold, italic) in enumerate(rows):
        for painter in (q, sheet):
            painter.set_font(
                {"family": name, "size": 14, "bold": bold, "italic": italic}
            )
            painter.text(
                10,
                8 + index * 48,
                620,
                45,
                0,
                name + " · Hello café Привет 0123",
                (240, 240, 245),
            )
    Image.fromarray(renderer.grab(q, 640, 260, background=(18, 20, 24))).save(
        tmp_path / "font-families-gpu.png"
    )
    sheet.frame.save(tmp_path / "font-families-cpu.png")
    print(f"Font review captures: {tmp_path}")


def test_discovery_and_real_rendering_do_not_import_qt():
    code = """
import importlib.abc, sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, NoQt())
from emtk.font import available_fonts
from emtk.pil_painter import PilPainter
family = next((f for f in available_fonts(True) if f != 'monospace'), 'monospace')
p = PilPainter(200,80); p.set_font(family,12)
p.text(0,0,180,70,0,'Hello',(255,255,255))
assert any(p.px[0::4])
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30)
