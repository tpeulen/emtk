"""The page's Python half: DOM values in, emtk values out.

``boot.js`` hands :class:`emtk.web.page.WebPage` the browser's own numbers --
``MouseEvent.button`` (0 left, 1 middle, 2 right), ``MouseEvent.buttons`` (a
mask), ``KeyboardEvent.key``, four modifier flags, ``WheelEvent.deltaY`` -- and
every one of them is translated here, through :mod:`emtk.events` and
:mod:`emtk.keys`, before the surface sees it. Replayed without a browser
against a recording surface and a stand-in canvas.
"""
from __future__ import annotations

import pytest

from emtk.app import Surface
from emtk.events import (
    ALT_MODIFIER,
    CONTROL_MODIFIER,
    LEFT_BUTTON,
    META_MODIFIER,
    MIDDLE_BUTTON,
    RIGHT_BUTTON,
    SHIFT_MODIFIER,
)
from emtk.keys import KEY_ESCAPE, KEY_LEFT, KEY_RETURN
from emtk.web.page import DROP_DIR, MOUNT_DIR, WebPage, mount, wheel_steps_from_dom


class _Recorder(Surface):
    def __init__(self):
        self.calls = []
        self.attached = None
        self.rendered = []

    def attach(self, device, format, width, height, ratio):
        self.attached = (device, format, width, height, ratio)

    def render(self, view):
        self.rendered.append(view)

    def _log(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return True

    def on_pointer_press(self, *a, **k):
        return self._log("press", *a, **k)

    def on_pointer_move(self, *a, **k):
        return self._log("move", *a, **k)

    def on_pointer_release(self, *a, **k):
        return self._log("release", *a, **k)

    def on_wheel(self, *a, **k):
        return self._log("wheel", *a, **k)

    def on_key_press(self, key, text, modifiers):
        self.calls.append(("key", (key, text, modifiers), {}))
        return key == KEY_ESCAPE      # consumes one key only

    def on_resize(self, *a):
        return self._log("resize", *a)

    def on_files_dropped(self, paths):
        return self._log("drop", list(paths))


class _Context:
    class _Texture:
        def createView(self):  # noqa: N802 - the DOM's spelling
            return "the-view"

    def getCurrentTexture(self):  # noqa: N802
        return self._Texture()


class _Canvas:
    def __init__(self, width=1600, height=1000, client_width=800):
        self.width, self.height, self.clientWidth = width, height, client_width

    def getContext(self, kind):  # noqa: N802
        assert kind == "webgpu"
        return _Context()


@pytest.fixture
def page():
    surface = _Recorder()
    return WebPage(_Canvas(), surface, device="dev", format="bgra8unorm"), surface


def test_attach_gets_device_pixels_and_the_ratio(page):
    web, surface = page
    assert surface.attached == ("dev", "bgra8unorm", 1600, 1000, 2.0)


def test_dom_buttons_are_translated(page):
    """The DOM numbers 0/1/2 as left/middle/right; emtk's constants differ."""
    web, surface = page
    web.press(10, 20, 0)
    web.press(10, 20, 1)
    web.press(10, 20, 2, False, True, False, False, True)
    assert [c[1][2] for c in surface.calls] == [LEFT_BUTTON, MIDDLE_BUTTON, RIGHT_BUTTON]
    assert surface.calls[2] == ("press", (10.0, 20.0, RIGHT_BUTTON, SHIFT_MODIFIER),
                                {"double": True})


def test_a_move_carries_the_held_mask(page):
    """``buttons`` on a move is what is *held* -- 1 left, 2 right, 4 middle."""
    web, surface = page
    web.move(1, 2, 1 | 4, True, False, False, True)
    assert surface.calls == [("move", (1.0, 2.0, LEFT_BUTTON | MIDDLE_BUTTON,
                                       CONTROL_MODIFIER | META_MODIFIER), {})]


def test_release_translates_too(page):
    web, surface = page
    web.release(3, 4, 2, False, False, True, False)
    assert surface.calls == [("release", (3.0, 4.0, RIGHT_BUTTON, ALT_MODIFIER), {})]


@pytest.mark.parametrize("delta, steps", [(100, -1), (3, -1), (-53, 1), (0, 0)])
def test_the_wheel_is_flipped_to_positive_away(delta, steps):
    """``deltaY`` is positive *toward* the user; emtk's steps are positive away.
    The page once passed it through and zoomed backwards against every
    desktop host.
    """
    assert wheel_steps_from_dom(delta) == steps


def test_the_wheel_reaches_the_surface_with_its_position(page):
    web, surface = page
    assert web.wheel(120, 5, 6) is True
    assert web.wheel(0, 5, 6) is False
    assert surface.calls == [("wheel", (5.0, 6.0, -1, 0), {})]


def test_keys_are_named_through_emtk_and_consumption_is_honest(page):
    web, surface = page
    assert web.key("ArrowLeft", "") is False
    assert web.key("Enter", "", True) is False
    assert web.key("z", "z") is False
    assert web.key("Escape", "") is True
    keys = [c[1] for c in surface.calls]
    assert keys[0] == (KEY_LEFT, "", 0)
    assert keys[1] == (KEY_RETURN, "", CONTROL_MODIFIER)
    assert keys[2] == (0, "z", 0), "a printable key is text, not a key code"


def test_resize_moves_the_backing_store_and_tells_the_surface(page):
    web, surface = page
    assert web.resize(800, 500, 2.0) is False, "nothing changed"
    assert web.resize(640, 480, 1.5) is True
    assert (web.canvas.width, web.canvas.height) == (960, 720)
    assert surface.calls[-1] == ("resize", (960, 720, 1.5), {})


def test_draw_renders_into_the_current_texture(page):
    web, surface = page
    web.draw()
    assert surface.rendered == ["the-view"] and web.frames == 1


def test_a_dropped_path_reaches_the_surface(page):
    web, surface = page
    assert web.open_path(DROP_DIR + "/x.pdb") is True
    assert surface.calls == [("drop", ([DROP_DIR + "/x.pdb"],), {})]
    assert web.DROP_DIR == DROP_DIR and web.MOUNT_DIR == MOUNT_DIR


def test_a_control_is_lifted_and_a_spec_is_mounted(monkeypatch):
    """``mount(canvas, "pkg.mod:make_app")`` is what ``boot.js`` runs."""
    import types
    import sys

    class _Control:
        def draw(self, painter, x, y, w, h):
            pass

    module = types.ModuleType("_emtk_test_webapp")
    module.make_app = _Control
    monkeypatch.setitem(sys.modules, "_emtk_test_webapp", module)
    monkeypatch.setattr("emtk.app.ControlSurface.attach",
                        lambda self, *a: setattr(self, "attached", a))
    web = mount(_Canvas(), "_emtk_test_webapp:make_app", device="d", format="rgba8unorm")
    assert isinstance(web.app, _Control)
    assert web.surface.control is web.app
    assert web.surface.attached == ("d", "rgba8unorm", 1600, 1000, 2.0)
