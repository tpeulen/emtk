"""A frame that raises is logged, reported and drawn -- never a silent blank window.

The defect this guards: an app's ``draw`` raised every frame (it called an
emtk API the installed emtk did not have yet); rendercanvas caught the
exception, presented a texture nothing had been drawn into, and the window
showed solid magenta on Metal with the traceback only in a logger.
"""
from __future__ import annotations

import logging

import pytest

from emtk import frame_errors
from emtk.testing import RecordingPainter


@pytest.fixture(autouse=True)
def _fresh_errors():
    frame_errors._seen.clear()
    yield
    frame_errors._seen.clear()


class Broken:
    """A control whose draw always fails half-way through."""

    def draw(self, painter, x, y, w, h):
        painter.fill_rect(x, y, w, h, (1, 2, 3, 255))
        raise AttributeError("'DockManager' object has no attribute 'focused'")


def test_a_raising_draw_is_logged_once_reported_once_and_drawn(caplog):
    seen = []
    frame_errors.add_frame_error_handler(seen.append)
    try:
        with caplog.at_level(logging.DEBUG, logger="emtk"):
            for _ in range(3):
                painter = RecordingPainter()
                assert frame_errors.draw_control(Broken(), painter, 0, 0, 400, 300) is False
    finally:
        frame_errors.remove_frame_error_handler(seen.append)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, "the traceback is logged once, not every frame"
    assert "focused" in errors[0].getMessage() and "Traceback" in errors[0].getMessage()
    assert len(seen) == 1 and seen[0].summary.startswith("AttributeError:")

    # The last frame: the error panel covers the half-drawn frame.
    assert painter.fills[-1] == (0, 0, 400, 300, frame_errors._PANEL)
    text = "\n".join(painter.strings)
    assert "This window failed to draw." in text
    assert "AttributeError: 'DockManager' object has no attribute 'focused'" in text
    assert "Repeated in 3 frames." in text


def test_a_clean_draw_is_untouched():
    class Fine:
        def draw(self, painter, x, y, w, h):
            painter.fill_rect(x, y, w, h, (9, 9, 9, 255))

    painter = RecordingPainter()
    assert frame_errors.draw_control(Fine(), painter, 0, 0, 10, 10) is True
    assert painter.fills == [(0, 0, 10, 10, (9, 9, 9, 255))]


def test_a_failing_handler_does_not_hide_the_error(caplog):
    def bad(_record):
        raise RuntimeError("reporter broke")

    frame_errors.add_frame_error_handler(bad)
    try:
        painter = RecordingPainter()
        with caplog.at_level(logging.ERROR, logger="emtk"):
            frame_errors.draw_control(Broken(), painter, 0, 0, 200, 100)
    finally:
        frame_errors.remove_frame_error_handler(bad)
    assert "This window failed to draw." in painter.strings


def test_version_info_names_the_version():
    import emtk

    info = emtk.version_info()
    assert info["version"] == emtk.__version__
    assert info["commit"] is None or isinstance(info["commit"], str)


# -- the real GPU path: what the user would have seen --------------------- #

@pytest.fixture(scope="module")
def device():
    pytest.importorskip("rendercanvas")
    pytest.importorskip("wgpu")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


def _is_panel(image) -> bool:
    np = pytest.importorskip("numpy")
    pixel = np.asarray(image)[2, 2, :3].astype(int)
    return bool(np.all(np.abs(pixel - np.array(frame_errors._PANEL[:3])) <= 2))


def test_a_native_window_whose_control_raises_shows_the_error_panel(device):
    np = pytest.importorskip("numpy")
    from emtk.native import NativeHost

    host = NativeHost(Broken(), size=(480, 320), backend="offscreen", device=device)
    image = np.asarray(host.draw_frame())
    assert _is_panel(image)
    assert len(np.unique(image[..., :3].reshape(-1, 3), axis=0)) > 5, "the message is drawn"
    host.close()


def test_a_native_window_whose_surface_raises_shows_the_error_panel(device):
    np = pytest.importorskip("numpy")
    from emtk.app import Surface
    from emtk.native import NativeHost

    class BrokenSurface(Surface):
        def render(self, view):
            raise RuntimeError("scene renderer exploded")

    host = NativeHost(BrokenSurface(), size=(480, 320), backend="offscreen", device=device)
    image = np.asarray(host.draw_frame())
    assert _is_panel(image)
    assert len(np.unique(image[..., :3].reshape(-1, 3), axis=0)) > 5
    host.close()
