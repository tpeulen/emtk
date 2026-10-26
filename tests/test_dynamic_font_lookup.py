"""The runtime coverage fonts are found by file name, wherever the distribution keeps them.

Fixed paths found DejaVu and Symbola on Debian (``truetype/dejavu/``) and nothing on
Fedora (``dejavu-sans-fonts/``, ``gdouros-symbola/``), so every glyph outside the baked
atlas drew as nothing there. These tests build a Fedora-shaped tree and never read the
host's fonts.
"""

from __future__ import annotations

import pytest

from emtk import dynamic_font


@pytest.fixture
def fedora(tmp_path, monkeypatch):
    """A /usr/share/fonts laid out the Fedora way, as the only font root."""
    root = tmp_path / "share" / "fonts"
    files = {
        "dejavu-sans-fonts/DejaVuSans.ttf",
        "gdouros-symbola/Symbola.ttf",
        "google-noto/NotoSansMono-Regular.ttf",
        "google-noto/NotoSansSymbols2-Regular.ttf",
        "google-noto-sans-mono-cjk-vf-fonts/NotoSansMonoCJK-VF.ttc",
        "google-noto/README.txt",
    }
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    monkeypatch.setattr(dynamic_font, "_FONT_ROOTS", (str(root), str(tmp_path / "absent")))
    # Debian's paths, which do not exist here.
    monkeypatch.setattr(
        dynamic_font,
        "FONT_CANDIDATES",
        ("/nonexistent/truetype/ancient-scripts/Symbola.ttf", "/nonexistent/DejaVuSans.ttf"),
    )
    dynamic_font._font_index.cache_clear()
    dynamic_font._candidate_paths.cache_clear()
    yield root
    dynamic_font._font_index.cache_clear()
    dynamic_font._candidate_paths.cache_clear()


def test_fedora_fonts_are_found_by_name(fedora):
    """A missing fixed path is looked up by its file name under the font roots."""
    paths = dynamic_font._candidate_paths()
    assert paths[:2] == (
        str(fedora / "gdouros-symbola" / "Symbola.ttf"),
        str(fedora / "dejavu-sans-fonts" / "DejaVuSans.ttf"),
    )
    assert str(fedora / "google-noto" / "NotoSansMono-Regular.ttf") in paths
    assert str(fedora / "google-noto-sans-mono-cjk-vf-fonts" / "NotoSansMonoCJK-VF.ttc") in paths


def test_each_font_appears_once_and_non_fonts_are_ignored(fedora):
    """A file reached both as a fixed path and by name is tried once; README is no font."""
    paths = dynamic_font._candidate_paths()
    assert len(paths) == len(set(paths))
    assert not any(p.endswith("README.txt") for p in paths)


def test_a_path_that_exists_is_used_as_given(fedora, tmp_path, monkeypatch):
    """The fixed path stays the fast path: it wins over a same-named file under a root."""
    direct = tmp_path / "direct" / "Symbola.ttf"
    direct.parent.mkdir()
    direct.write_bytes(b"")
    monkeypatch.setattr(dynamic_font, "FONT_CANDIDATES", (str(direct),))
    dynamic_font._candidate_paths.cache_clear()
    assert dynamic_font._candidate_paths()[0] == str(direct)
