"""Behind a modal window: washed with MODAL_DIM_BG and, by default, blurred.

The blur is a painter capability: the GPU painter splits its frame at the backdrop and
blurs what was drawn before it, the pixel painter blurs its buffer, any other painter washes
only. ``emtk.backdrop.draw_modal_backdrop`` is the one call every modal surface makes.
"""

from __future__ import annotations

import numpy as np
import pytest

import emtk
from emtk import backdrop, style
from emtk.message_dialog import MessageDialogs
from emtk.testing import PixelPainter, RecordingPainter

W, H = 160, 100


def _stripes(painter):
    for x in range(0, W, 8):
        painter.fill_rect(x, 0, 4, H, (255, 255, 255, 255))


def _pixels(painter):
    return np.frombuffer(bytes(painter.px), np.uint8).reshape(H, W, 4)[:, :, :3].astype(int)


@pytest.fixture(autouse=True)
def _blur_on():
    before = (style.MODAL_BLUR, style.MODAL_BLUR_RADIUS)
    backdrop.set_modal_blur(True, 6.0)
    yield
    style.MODAL_BLUR, style.MODAL_BLUR_RADIUS = before


def test_the_pixel_painter_blurs_and_tints_only_the_backdrop():
    painter = PixelPainter(W, H)
    _stripes(painter)
    sharp = _pixels(painter).copy()
    painter.backdrop(0, 0, W // 2, H, (0, 0, 0, 0), radius=6.0)
    out = _pixels(painter)
    assert np.ptp(sharp[:, 20:60, 0]) == 255
    assert np.ptp(out[:, 20:60, 0]) < 40, "stripes inside the backdrop are blurred"
    assert np.array_equal(out[:, W // 2 + 1:], sharp[:, W // 2 + 1:]), "outside stays sharp"


def test_switched_off_the_backdrop_only_washes():
    backdrop.set_modal_blur(False)
    painter = PixelPainter(W, H)
    _stripes(painter)
    backdrop.draw_modal_backdrop(painter, 0, 0, W, H)
    out = _pixels(painter)
    assert np.ptp(out[:, :, 0]) > 100, "no blur: the stripes are still there, only washed"


def test_a_painter_without_the_capability_washes():
    painter = RecordingPainter()
    backdrop.draw_modal_backdrop(painter, 0, 0, 50, 40)
    assert any(call[0] == "fill_rect" for call in painter.calls)


def test_a_question_frosts_what_is_behind_it():
    painter = PixelPainter(800, 600)
    calls = []
    real = painter.backdrop
    painter.backdrop = lambda *args: (calls.append(args), real(*args))
    dialogs = MessageDialogs()
    dialogs.confirm("Remove fit", "Remove the fit and its window?", lambda answer: None)
    with emtk.frame(painter, (0.0, 0.0, 800.0, 600.0), io=emtk.IO(), storage={}):
        dialogs.draw((0.0, 0.0, 800.0, 600.0))
    assert calls and calls[0][:4] == (0.0, 0.0, 800.0, 600.0)
    assert calls[0][5] == style.MODAL_BLUR_RADIUS


def test_the_gpu_painter_marks_where_the_frame_splits():
    from emtk.quad_painter import QuadPainter

    painter = QuadPainter(scale=2.0)
    painter.fill_rect(0, 0, 10, 10, (255, 0, 0, 255))
    before = painter.vertex_count
    painter.backdrop(0, 0, 40, 30, (0, 0, 0, 90), radius=6.0)
    (index, box, radius), = painter.backdrops()
    assert index == before and box == (0.0, 0.0, 80.0, 60.0) and radius == 12.0
    assert painter.vertex_count > before, "the tint is still drawn"
    painter.clear()
    assert painter.backdrops() == []


def test_the_gpu_frame_is_blurred_behind_and_sharp_in_front():
    wgpu_host = pytest.importorskip("emtk.wgpu_host")
    try:
        renderer = wgpu_host.WgpuRenderer()
        renderer.device  # noqa: B018 - an adapter, or skip
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"no GPU adapter: {error}")
    painter = renderer.painter()
    _stripes(painter)
    painter.backdrop(0, 0, W, H, (0, 0, 0, 0), radius=6.0)
    painter.fill_rect(100, 40, 30, 20, (255, 0, 0, 255))      # the modal window: drawn after
    image = renderer.grab(painter, W, H, background=(0, 0, 0))[:, :, :3].astype(int)
    assert np.ptp(image[10:90, 10:90, 1]) < 60, "behind the backdrop the stripes are blurred"
    assert (image[45:55, 105:125] == (255, 0, 0)).all(), "the window in front is sharp"
