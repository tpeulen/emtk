"""Qt texture blits preserve signed UV orientation and painter state."""

from __future__ import annotations

import pytest
from emtk.qt_painter import QtPainter, image_bytes
from emtk.testing import PixelPainter
from emtk.texture import Texture

BACKGROUND = (11, 19, 27, 255)
UV_WINDOWS = [
    ((0, 0), (1, 1)),
    ((1, 0), (0, 1)),
    ((0, 1), (1, 0)),
    ((1, 1), (0, 0)),
    ((0.5, 0), (1, 1)),
    ((1, 0), (0.5, 1)),
    ((0, 1), (1, 0.5)),
    ((1, 1), (0.5, 0.5)),
]


def _texture(alpha=255):
    """Return four unmistakable colored corners."""
    return Texture(2, 2, bytes((
        240, 30, 20, alpha, 20, 220, 40, alpha,
        30, 40, 210, alpha, 240, 200, 20, alpha,
    )), filter="nearest")


def _render_qt(texture, uv0, uv1, tint, *, clipped=False, opacity=1.0):
    """Draw a real Qt image and assert state survives the texture draw."""
    from qtpy import QtGui

    image = QtGui.QImage(28, 24, QtGui.QImage.Format_RGBA8888)
    image.fill(QtGui.QColor(*BACKGROUND))
    painter = QtGui.QPainter(image)
    try:
        painter.translate(2, 1)
        painter.setOpacity(opacity)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        canvas = QtPainter(painter)
        if clipped:
            canvas.push_clip(3, 2, 15, 15)
            canvas.push_clip(7, 5, 7, 9)
        transform = painter.transform()
        clip = painter.clipBoundingRect()
        hints = painter.renderHints()
        canvas.image(0, 0, 20, 20, texture, uv0, uv1, tint)
        assert painter.transform() == transform
        assert painter.clipBoundingRect() == clip
        assert painter.renderHints() == hints
        assert painter.opacity() == opacity
        if clipped:
            canvas.pop_clip()
            canvas.pop_clip()
        canvas.fill_rect(22, 20, 2, 2, (150, 180, 210, 255))
    finally:
        painter.end()
    return image_bytes(image)[2]


def _render_pixels(texture, uv0, uv1, tint, *, clipped=False):
    """Render the same device coordinates through the software painter."""
    painter = PixelPainter(28, 24, BACKGROUND)
    if clipped:
        painter.push_clip(5, 3, 15, 15)
        painter.push_clip(9, 6, 7, 9)
    painter.image(2, 1, 20, 20, texture, uv0, uv1, tint)
    if clipped:
        painter.pop_clip()
        painter.pop_clip()
    painter.fill_rect(24, 21, 2, 2, (150, 180, 210, 255))
    return painter.px


@pytest.mark.parametrize("uv0,uv1", UV_WINDOWS)
@pytest.mark.parametrize("clipped", [False, True])
def test_signed_uvs_match_software_corners_and_crop(qt_app, uv0, uv1, clipped):
    """Normal, horizontal, vertical and double flips retain nearest samples."""
    texture = _texture()
    tint = (255, 255, 255, 255)
    assert _render_qt(texture, uv0, uv1, tint, clipped=clipped) == _render_pixels(
        texture, uv0, uv1, tint, clipped=clipped,
    )


@pytest.mark.parametrize("tint", [(255, 255, 255, 128), (180, 230, 140, 127),
                                 (240, 150, 210, 0)])
@pytest.mark.parametrize("uv0,uv1", [((0, 0), (1, 1)), ((0, 1), (1, 0))])
def test_signed_uvs_preserve_tint_and_texture_alpha(qt_app, tint, uv0, uv1):
    """Qt rounding differs at most two levels from the integer reference."""
    texture = _texture(alpha=150)
    original = bytes(texture.px)
    actual = _render_qt(texture, uv0, uv1, tint, clipped=True)
    expected = _render_pixels(texture, uv0, uv1, tint, clipped=True)
    assert max(abs(a - b) for a, b in zip(actual, expected)) <= 2
    assert bytes(texture.px) == original


def test_image_respects_existing_painter_opacity(qt_app):
    """Image-local opacity multiplies the caller's opacity and restores it."""
    opaque = _render_qt(_texture(), (0, 1), (1, 0), (255, 255, 255, 128), opacity=0.5)
    # A corner has combined 25% coverage, rather than replacing caller opacity.
    offset = (3 * 28 + 4) * 4
    assert all(abs(opaque[offset + channel] - (BACKGROUND[channel] * 0.75 +
               (30, 40, 210)[channel] * 0.25)) <= 2 for channel in range(3))
