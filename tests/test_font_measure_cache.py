"""Text measurement must not re-resolve the font face on every call."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")
from emtk import font_render
from emtk.font import available_fonts
from emtk.font_render import font_spec


def _spec():
    names = [n for n in available_fonts() if n != "monospace"]
    if not names:
        pytest.skip("no system font")
    return font_spec(names[0])


def test_face_and_width_are_memoised():
    spec = _spec()
    font_render._face.cache_clear()
    font_render.text_width.cache_clear()
    first = font_render.text_width(spec, "hello world", 1.0)
    for _ in range(50):
        assert font_render.text_width(spec, "hello world", 1.0) == first
    assert font_render.text_width.cache_info().hits >= 50
    font_render._font(spec, 1.0)
    font_render._font(spec, 2.0)
    assert font_render._face.cache_info().hits >= 1


def test_width_still_depends_on_scale_and_text():
    spec = _spec()
    assert font_render.text_width(spec, "abcd", 2.0) > font_render.text_width(spec, "abcd", 1.0)
    assert font_render.text_width(spec, "abcdef", 1.0) > font_render.text_width(spec, "abcd", 1.0)
