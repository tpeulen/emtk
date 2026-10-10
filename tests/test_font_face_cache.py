"""The installed-face scan persists between processes and rescans only changed files."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PIL")
from emtk import font_render


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EMTK_CACHE_DIR", str(tmp_path))
    font_render._faces.cache_clear()
    yield tmp_path
    font_render._faces.cache_clear()


def test_second_process_reuses_the_scan(cache_dir, monkeypatch):
    first = font_render._faces()
    if not first:
        pytest.skip("no system font")
    assert (cache_dir / "font_faces.json").is_file()
    font_render._faces.cache_clear()

    def no_scan(*args, **kwargs):
        raise AssertionError("an unchanged font file was reopened")

    monkeypatch.setattr(font_render, "_scan_file", no_scan)
    assert font_render._faces() == first


def test_changed_file_is_rescanned(cache_dir, monkeypatch):
    first = font_render._faces()
    if not first:
        pytest.skip("no system font")
    path = cache_dir / "font_faces.json"
    data = json.loads(path.read_text())
    stale = next(iter(data["files"]))
    data["files"][stale]["sig"] = [0, 0]
    path.write_text(json.dumps(data))
    font_render._faces.cache_clear()
    scanned = []
    real = font_render._scan_file
    monkeypatch.setattr(font_render, "_scan_file", lambda p, f: scanned.append(str(p)) or real(p, f))
    assert font_render._faces() == first
    assert scanned == [stale]


def test_corrupt_cache_falls_back_to_a_scan(cache_dir):
    (cache_dir / "font_faces.json").write_text("{not json")
    assert isinstance(font_render._faces(), dict)
    assert json.loads((cache_dir / "font_faces.json").read_text())["version"] == 1
