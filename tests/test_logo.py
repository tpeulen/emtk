"""emtk.logo: an .ico, an .svg and a PNG read at the size they are needed; the window icon."""
from __future__ import annotations

import io

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from emtk.logo import WINDOW_ICON_SIZES, load_logo, logo_texture, set_window_icon  # noqa: E402


def _ico(tmp_path):
    """An .ico whose frames differ in colour by size, so the frame taken shows."""
    big = Image.new("RGBA", (256, 256), (200, 30, 120, 255))
    path = tmp_path / "logo.ico"
    big.save(path, sizes=[(16, 16), (32, 32), (64, 64), (256, 256)])
    return path


def test_an_ico_gives_the_frame_that_scales_least(tmp_path):
    path = _ico(tmp_path)
    assert load_logo(path).size == (256, 256)            # as delivered: the largest
    for size in (16, 32, 48, 100):
        im = load_logo(path, size)
        assert im.size == (size, size) and im.mode == "RGBA"
        assert im.getpixel((size // 2, size // 2))[:3] == pytest.approx((200, 30, 120), abs=3)


def test_an_svg_is_drawn_at_the_size_not_scaled():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="20">'
           '<rect width="10" height="20" fill="#2266cc"/></svg>')
    im = load_logo(svg.encode(), 64)
    assert im.size == (32, 64)                           # aspect kept, fits 64
    assert im.getpixel((16, 32))[:3] == pytest.approx((0x22, 0x66, 0xCC), abs=3)


def test_a_png_and_a_texture(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (10, 200, 10)).save(buf, format="PNG")
    im = load_logo(buf.getvalue(), 20)
    assert im.size == (20, 10) and im.mode == "RGBA"
    tex = logo_texture(_ico(tmp_path), 32)
    assert (tex.width, tex.height) == (32, 32)


def test_a_window_icon_needs_a_glfw_window():
    class Offscreen:
        pass

    assert not set_window_icon(Offscreen(), b"")          # nothing to set it on
    assert 16 in WINDOW_ICON_SIZES and 256 in WINDOW_ICON_SIZES


def test_an_ico_is_written_with_every_size(tmp_path):
    from emtk.logo import write_ico

    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><circle cx="4" cy="4" r="4" fill="red"/></svg>'
    path = write_ico(svg, tmp_path / "app.ico")
    sizes = set(Image.open(path).info["sizes"])
    assert {(s, s) for s in WINDOW_ICON_SIZES} <= sizes


def test_off_windows_the_app_id_and_shortcut_do_nothing(monkeypatch):
    import emtk.logo as logo

    monkeypatch.setattr(logo.sys, "platform", "darwin")
    assert logo.set_app_id("Peulen.PhAcq") is False
    assert logo.install_shortcut("PhAcq", "x.exe") == []
