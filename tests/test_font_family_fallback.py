"""An unavailable font family draws in the default family instead of raising.

The fit pages push a bold ``sans-serif`` caption; the web page has exactly one
baked face and no system fonts, so ``_face`` raised
``ValueError: Font family 'sans-serif' is not available`` -- the dock caught it
and the What-if window "failed to draw". A font request is a hint, not a
contract: the face falls back, the window draws, and a warning says what
happened.
"""
import logging

import pytest

from emtk.font_render import (
    FontSpec, _cmap, _face, _face_for, _family_face, _fallback_family,
    _layout_metrics, _layout_width, _loaded, _resolve_family, _runs,
    text_width,
)

#: Every cache that can hold a face-derived entry. A test that swaps
#: ``_faces()`` must drop them again AFTER the monkeypatch is undone, or the
#: next test's equal specs hit faces resolved in the fake world.
_FACE_CACHES = (
    _face, _resolve_family, _loaded, _layout_metrics, _cmap,
    _family_face, _face_for, _runs, _layout_width, text_width,
)


@pytest.fixture
def empty_face_world(monkeypatch):
    """``_faces()`` -> {}: the web page's world, restored cleanly."""
    from emtk import font_render

    monkeypatch.setattr(font_render, "_faces", lambda: {})
    _face.cache_clear()
    yield
    for cache in _FACE_CACHES:
        cache.cache_clear()


def test_an_unavailable_family_draws_in_the_default_family(caplog):
    spec = FontSpec(family="Definitely Not Installed 4f2a1")
    with caplog.at_level(logging.WARNING, logger="emtk.font_render"):
        face = _face(spec)
    assert face is _face(FontSpec(family=_fallback_family()))
    assert any("not available" in r.getMessage() for r in caplog.records)


def test_an_unavailable_family_keeps_a_bold_request_working():
    # no ValueError: the window that asked for bold sans-serif keeps drawing
    face = _face(FontSpec(family="Definitely Not Installed 4f2a1", bold=True))
    assert isinstance(face.bold, bool)  # a real face came back


def test_with_no_installed_faces_the_baked_atlas_face_answers(empty_face_world, caplog):
    """The web page's world: ``_faces()`` is empty, the baked atlas is the only face.

    Pyodide ships no system fonts, so nothing resolves -- not even the default
    family. The What-if window died here too (StopIteration in the fallback
    walk) before the baked face answered.
    """
    from emtk import font_render

    with caplog.at_level(logging.WARNING, logger="emtk.font_render"):
        face = font_render._face(FontSpec(family="sans-serif", bold=True))
    assert face.path == ":baked-atlas:" and face.bold and face.monospaced
    assert any("baked atlas" in r.getMessage() for r in caplog.records)
    # and the face measures: width from the atlas, not a font file
    w = font_render.text_width(font_render.font_spec({"family": "sans-serif", "size": 8}), "Hello", 1.0)
    assert 0 < w < 500


def test_a_family_without_the_requested_cut_falls_back_to_regular(caplog):
    # find a family with a regular face but no bold one, if any exists
    import pytest

    from emtk.font_render import _faces

    candidates = [
        name
        for name, faces in _faces().items()
        if any(not f.bold and not f.italic for f in faces)
        and not any(f.bold and not f.italic for f in faces)
    ]
    if not candidates:
        pytest.skip("every installed family has a bold face")
    family = candidates[0]
    with caplog.at_level(logging.WARNING, logger="emtk.font_render"):
        face = _face(FontSpec(family=family, bold=True))
    assert not face.bold
    assert any("regular face" in r.getMessage() for r in caplog.records)
