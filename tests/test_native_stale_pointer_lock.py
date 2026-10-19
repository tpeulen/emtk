"""A press while rendercanvas' pointer lock is held is a click, not the missing release.

The glfw backend locks the pointer on a press it takes as "the click that focuses the
window" and ends the lock on the next release. When that release never reached the window
(released over another one, during a window switch), the lock stayed: every move was
dropped and the next real press was eaten as the release -- a click that did not land,
at random. ``CanvasEvents._button_arrived`` runs ahead of the backend's callback.
"""

import sys
import types

import pytest

from emtk.native import CanvasEvents


@pytest.fixture
def fake_glfw(monkeypatch):
    glfw = types.SimpleNamespace(PRESS=1, RELEASE=0, HOVERED=0x0002000B,
                                 hovered=True,
                                 get_cursor_pos=lambda window: (12.0, 34.0))
    glfw.get_window_attrib = lambda window, attrib: glfw.hovered
    monkeypatch.setitem(sys.modules, "glfw", glfw)
    return glfw


def _events(lock, inside=True):
    events = object.__new__(CanvasEvents)
    events.canvas = types.SimpleNamespace(_pointer_lock=lock, _pointer_inside=inside)
    return events


def test_a_press_over_the_window_clears_a_stale_lock(fake_glfw):
    events = _events(lock=True)
    events._button_arrived("window", 0, fake_glfw.PRESS, 0)
    assert events.canvas._pointer_lock is False


def test_the_release_that_ends_a_real_lock_is_left_to_the_backend(fake_glfw):
    events = _events(lock=True)
    events._button_arrived("window", 0, fake_glfw.RELEASE, 0)
    assert events.canvas._pointer_lock is True


def test_a_press_off_the_window_keeps_the_lock(fake_glfw):
    fake_glfw.hovered = False
    events = _events(lock=True, inside=False)
    events._button_arrived("window", 0, fake_glfw.PRESS, 0)
    assert events.canvas._pointer_lock is True
