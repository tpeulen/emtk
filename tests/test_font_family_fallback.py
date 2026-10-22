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


def test_the_baked_atlas_face_measures_like_pil_with_anchors(empty_face_world):
    """A theme switch once blanked the page: the stylesheet asked for a font
    nobody installed, the synthetic ``:baked-atlas:`` face answered, and its
    ``getbbox`` rejected the ``anchor`` keyword ``_glyph`` measures glyphs
    with -- the frame died, and the frame-error panel died the same way."""
    from emtk.font_render import FontSpec, _face, _loaded

    face = _face(FontSpec(family="anything-at-all"))
    assert face.path == ":baked-atlas:"
    font = _loaded(face, 32)
    # the default (la): pen at the left, y down from the ascender
    x0, y0, x1, y1 = font.getbbox("Ag")
    assert (x0, x1) == (0, font.getlength("Ag"))
    assert y0 == 0
    # ls: the anchor _glyph uses -- y measured from the baseline
    lx0, ly0, lx1, ly1 = font.getbbox("Ag", anchor="ls")
    assert (lx0, lx1) == (x0, x1)
    ascent, descent = font.getmetrics()
    assert ly0 == -ascent
    assert ly1 == descent
    # centred and right anchors keep the width
    m0 = font.getbbox("Ag", anchor="ms")
    r0 = font.getbbox("Ag", anchor="rs")
    assert m0[0] < 0 < m0[2]
    assert r0[0] == -font.getlength("Ag")


def test_the_baked_atlas_face_rasterises_through_pil(empty_face_world):
    """The other blank-page face: a theme switch re-fonts the dock titles, the
    synthetic face answers, and the glyph rasteriser draws each character with
    PIL's ``ImageDraw.text`` -- which wants ``getmask`` (``getmask2`` first).
    A face without pixels killed the frame, and the error panel died drawing
    its own message the same way."""
    from PIL import Image, ImageDraw

    from emtk.font_render import FontSpec, _face, _loaded

    face = _face(FontSpec(family="nothing-installed"))
    assert face.path == ":baked-atlas:"
    font = _loaded(face, 24)

    # the rasteriser's own call, exactly as _glyph makes it
    image = Image.new("RGBA", (120, 60))
    draw = ImageDraw.Draw(image)
    draw.text((10, 30), "Setup", font=font, anchor="ls",
              fill=(255, 255, 255, 255))
    alpha = image.getchannel("A")
    assert alpha.getbbox() is not None, "no glyph ink was rasterised"

    # the mask itself: a box the metrics agree with, ink inside the ascent
    mask = font.getmask("Ag")
    assert mask is not None and mask.size[0] > 0 and mask.size[1] > 0
    from PIL import Image as _Image

    boxed = _Image.new("L", mask.size)
    boxed.frombytes(bytes(mask))
    ascent, descent = font.getmetrics()
    assert mask.size[1] == ascent + descent
    assert boxed.getbbox() is not None
    assert font.getmask("") is None
