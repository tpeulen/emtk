"""A second kind of native window: undecorated, floating, transparent, centred -- a splash screen.

The glfw parts are checked against a stand-in glfw module (the hints set, and reset after the
window opened); what a GPU surface does with a transparent clear is checked on the offscreen
canvas, which needs ``rendercanvas``, ``wgpu`` and an adapter.
"""
from __future__ import annotations

import sys
import types

import pytest

from emtk import native


def test_an_ordinary_window_gets_no_hints():
    assert native.window_hints() == {}


def test_a_splash_window_is_undecorated_floating_transparent_and_placed():
    hints = native.window_hints(decorated=False, floating=True, transparent=True,
                                position=(10, 20))
    assert hints == {"DECORATED": False, "FLOATING": True, "TRANSPARENT_FRAMEBUFFER": True,
                     "POSITION_X": 10, "POSITION_Y": 20}


@pytest.mark.parametrize(
    "size, rect, expected",
    [
        ((500, 300), (0, 25, 1512, 957, 1.0), (506, 353)),
        ((500, 300), (0, 0, 3840, 2160, 2.0), (1420, 780)),     # physical screen coordinates
        ((500, 300), (1512, 0, 1920, 1080, 1.0), (2222, 390)),  # a second monitor's area
        ((4000, 3000), (0, 0, 1920, 1080, 1.0), (0, 0)),        # larger than the screen: its corner
        ((500, 300), None, None),
    ],
)
def test_centred_position(size, rect, expected):
    assert native.centred_position(size, rect) == expected


class _FakeGlfw(types.ModuleType):
    DECORATED, FLOATING, TRANSPARENT_FRAMEBUFFER, POSITION_X, POSITION_Y = range(1, 6)

    def __init__(self):
        super().__init__("glfw")
        self.calls = []

    def init(self):
        return True

    def window_hint(self, attribute, value):
        self.calls.append(("hint", attribute, value))

    def default_window_hints(self):
        self.calls.append(("defaults",))


def test_hints_apply_to_the_next_glfw_window_only(monkeypatch):
    fake = _FakeGlfw()
    monkeypatch.setitem(sys.modules, "glfw", fake)
    module = types.SimpleNamespace(__name__="rendercanvas.glfw")
    with native._glfw_hints(module, {"DECORATED": False, "FLOATING": True}):
        opened = list(fake.calls)
    assert opened == [("hint", fake.DECORATED, False), ("hint", fake.FLOATING, True)]
    # Reset afterwards: rendercanvas never resets hints it did not set itself.
    assert fake.calls[-1] == ("defaults",)


def test_other_backends_ignore_the_hints(monkeypatch):
    fake = _FakeGlfw()
    monkeypatch.setitem(sys.modules, "glfw", fake)
    module = types.SimpleNamespace(__name__="rendercanvas.offscreen")
    with native._glfw_hints(module, {"DECORATED": False}):
        pass
    assert fake.calls == []


class _Context:
    def __init__(self, offered):
        self.offered = offered
        self.configured = []

    def configure(self, device, format, alpha_mode="opaque"):
        if alpha_mode not in self.offered:
            raise ValueError(f"unsupported alpha-mode: {alpha_mode}")
        self.configured.append(alpha_mode)


def test_a_transparent_surface_is_premultiplied_where_offered():
    context = _Context({"opaque", "premultiplied"})
    assert native.configure_surface(context, object(), "bgra8unorm", transparent=True) == (
        "premultiplied")
    assert context.configured == ["premultiplied"]


def test_metal_is_transparent_through_its_unpremultiplied_mode():
    # Metal offers opaque and unpremultiplied; the latter makes its layer non-opaque.
    context = _Context({"opaque", "unpremultiplied"})
    assert native.configure_surface(context, object(), "bgra8unorm", transparent=True) == (
        "unpremultiplied")


def test_a_transparent_surface_falls_back_to_opaque():
    context = _Context({"opaque"})
    assert native.configure_surface(context, object(), "bgra8unorm", transparent=True) == "opaque"
    assert context.configured == ["opaque"]


def test_an_ordinary_surface_stays_opaque():
    context = _Context({"opaque", "premultiplied"})
    assert native.configure_surface(context, object(), "bgra8unorm") == "opaque"


# -- on the GPU ------------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def device():
    pytest.importorskip("rendercanvas")
    pytest.importorskip("wgpu")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


class _Picture:
    """A control drawing one image into the middle of its window."""

    def __init__(self, texture):
        self.texture = texture

    def draw(self, painter, x, y, w, h):
        from emtk import painter as paint

        paint.image(painter, x + w / 4, y + h / 4, w / 2, h / 2, self.texture)


def test_a_cleared_transparent_surface_keeps_alpha_zero_around_the_art(device):
    np = pytest.importorskip("numpy")
    from emtk import Texture
    from emtk.app import ControlSurface
    from emtk.gpu_atlas import ImageAtlas

    # Wider than the default 1024-texel atlas: a bigger atlas for this surface draws it.
    texture = Texture(1200, 40)
    texture.fill((255, 0, 0, 255))
    surface = ControlSurface(_Picture(texture), background=(0, 0, 0, 0),
                             images=ImageAtlas(2048, 2048))
    host = native.NativeHost(surface, size=(400, 200), backend="offscreen", device=device)
    image = np.asarray(host.draw_frame())
    assert image[5, 5, 3] == 0, "the cleared surface must stay see-through"
    centre = image[100, 200]
    assert centre[3] == 255 and centre[0] > 200 and centre[1] < 40, (
        "a 1200-texel image draws in a surface with a 2048 atlas (not a blank rectangle)")


def test_a_cancelled_frame_asks_for_another(device):
    from emtk.app import ImApp

    host = native.NativeHost(ImApp(lambda: None), size=(100, 60), backend="offscreen",
                             device=device)

    class DrawCancelled(Exception):
        pass

    def occluded():
        raise DrawCancelled("Occluded")

    asked = []
    host.context.get_current_texture = occluded
    host.canvas.request_draw = lambda *a: asked.append(a)
    with pytest.raises(DrawCancelled):
        host._draw_frame()
    assert asked, "an occluded frame must be asked for again, or the window stays blank"


class _FullscreenGlfw(types.ModuleType):
    DECORATED = 1

    def __init__(self):
        super().__init__("glfw")
        self.calls = []
        self.mon = [object(), object()]

    def get_primary_monitor(self):
        return self.mon[0]

    def get_monitors(self):
        return self.mon

    def get_window_pos(self, window):
        return (2000, 100)                                   # opened on the second monitor

    def get_monitor_pos(self, m):
        return (0, 0) if m is self.mon[0] else (1920, 0)

    def get_video_mode(self, m):
        w, h = (1920, 1080) if m is self.mon[0] else (2560, 1440)
        return types.SimpleNamespace(size=types.SimpleNamespace(width=w, height=h))

    def set_window_attrib(self, window, attr, value):
        self.calls.append(("attrib", attr, value))

    def set_window_pos(self, window, x, y):
        self.calls.append(("pos", x, y))

    def set_window_size(self, window, w, h):
        self.calls.append(("size", w, h))


def test_fullscreen_covers_the_monitor_the_window_is_on(monkeypatch):
    fake = _FullscreenGlfw()
    monkeypatch.setitem(sys.modules, "glfw", fake)
    canvas_cls = type("RenderCanvas", (), {"__module__": "rendercanvas.glfw"})
    canvas = canvas_cls()
    canvas._window = object()
    assert native.make_fullscreen(canvas)
    assert fake.calls == [("attrib", 1, False), ("pos", 1920, 0), ("size", 2560, 1440)]


def test_fullscreen_is_a_no_op_off_glfw():
    canvas = type("RenderCanvas", (), {"__module__": "rendercanvas.qt"})()
    canvas._window = object()
    assert not native.make_fullscreen(canvas)
