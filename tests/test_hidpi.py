"""One rule on every host: logical sizes in, the device pixel ratio applied once.

A frame is laid out in logical pixels -- what a window's size and a mouse
event are in -- and the ratio turns it into device pixels at exactly one
place. Applied twice, text comes out twice the size the layout budgeted and
clips; applied nowhere, the interface draws in a corner while clicks land
where it should have been.

Each host that can run headless draws the same text at ratio 1 and ratio 2,
and the test measures the pixels:

* a capital's height doubles with the ratio, and is the same logical size
  on every host (an emtk point is :data:`emtk.font.PX_PER_PT` logical
  pixels everywhere);
* the glyph pitch on screen is ``text_width`` times the ratio -- what the
  layout measured is what was drawn;
* a click at the logical centre of a drawn button presses that button;
* the surface is the logical size asked for, times the ratio.
"""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from emtk.font import DEFAULT_FONT_PT, PX_PER_PT, load_atlas  # noqa: E402
from emtk.native import fit_to_screen  # noqa: E402
from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER  # noqa: E402

#: The probe string: capitals only, so ink height is the cap height and
#: every glyph's left edge sits the same distance into its advance cell.
PROBE = "HHHHHHHH"
#: Where the probe is drawn, logical.
BOX = (10.0, 10.0, 200.0, 24.0)
SIZE = (240, 48)
BACKGROUND = (0, 0, 0)
WHITE = (255, 255, 255, 255)


class _Probe:
    """A control drawing :data:`PROBE` and remembering what it measured."""

    def __init__(self) -> None:
        self.advance = None

    def draw(self, painter, x, y, w, h) -> None:
        painter.fill_rect(x, y, w, h, BACKGROUND + (255,))
        self.advance = painter.text_width("H")
        painter.text(*BOX, ALIGN_LEFT | ALIGN_VCENTER, PROBE, WHITE)


def _measure(pixels) -> dict:
    """Cap height and glyph pitch of the probe, in the image's pixels."""
    rgb = np.asarray(pixels)[..., :3].astype(float)
    mask = rgb.mean(axis=2) > 110.0
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    assert rows.size and cols.size, "nothing was drawn"
    # Left edges of the glyphs: a column with ink after one without.
    inked = mask.any(axis=0)
    starts = [c for c in range(1, inked.size) if inked[c] and not inked[c - 1]]
    if inked[0]:
        starts.insert(0, 0)
    assert len(starts) == len(PROBE), f"{len(starts)} glyphs found, not {len(PROBE)}"
    return {"cap": float(rows[-1] - rows[0] + 1),
            "pitch": float(np.diff(starts).mean()),
            "left": float(cols[0]), "right": float(cols[-1] + 1)}


def _check_pair(one: dict, two: dict, advance: float) -> None:
    """The ratio-2 picture is the ratio-1 picture, twice as many pixels."""
    assert two["cap"] == pytest.approx(2.0 * one["cap"], abs=2.0)
    for ratio, got in ((1.0, one), (2.0, two)):
        # What the layout measured is what was drawn.
        assert got["pitch"] == pytest.approx(advance * ratio, abs=0.3 * ratio)
        assert got["right"] - got["left"] <= advance * len(PROBE) * ratio + 1.0
        # And it starts where the layout put it.
        assert got["left"] == pytest.approx(BOX[0] * ratio, abs=2.0 * ratio)


#: Logical cap height every host must agree on, within :data:`CAP_TOLERANCE`:
#: Menlo's capitals are ~0.73 em, and an em is ``font_pt * PX_PER_PT``.
CAP = 0.73 * DEFAULT_FONT_PT * PX_PER_PT
CAP_TOLERANCE = 0.2


# --------------------------------------------------------------------------- #
# The GPU: the native window and the browser page
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def device():
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


def _native(control, device, ratio: float, size=SIZE):
    from rendercanvas.offscreen import RenderCanvas

    from emtk.native import NativeHost

    canvas = RenderCanvas(size=size, pixel_ratio=ratio)
    return NativeHost(control, canvas=canvas, device=device)


def test_native_text_is_one_logical_size_at_every_ratio(device):
    shots = {}
    for ratio in (1.0, 2.0):
        probe = _Probe()
        host = _native(probe, device, ratio)
        image = np.asarray(host.draw_frame())
        assert image.shape[:2] == (SIZE[1] * ratio, SIZE[0] * ratio)
        shots[ratio] = _measure(image)
    _check_pair(shots[1.0], shots[2.0], probe.advance)
    assert shots[2.0]["cap"] / 2.0 == pytest.approx(CAP, rel=CAP_TOLERANCE)


def test_native_surface_is_the_logical_size_times_the_ratio(device):
    host = _native(_Probe(), device, 2.0, size=(1400, 900))
    assert tuple(host.canvas.get_physical_size()) == (2800, 1800)
    assert host.surface.size == (2800, 1800)
    assert host.surface.ratio == 2.0
    assert host.surface._box() == (0.0, 0.0, 1400.0, 900.0)


def test_a_window_is_clamped_to_the_screen_and_no_further():
    assert fit_to_screen((1400, 900), (1512, 949)) == (1400, 900)
    assert fit_to_screen((1400, 900), (1280, 800)) == (1280, 760)
    assert fit_to_screen((1400, 900), None) == (1400, 900)


def _button_app():
    from emtk import im
    from emtk.app import ImApp

    state = {"rect": None, "clicks": 0}

    def gui() -> None:
        im.set_cursor_pos((40.0, 30.0))
        if im.button("Press here"):
            state["clicks"] += 1
        state["rect"] = (tuple(im.get_item_rect_min()), tuple(im.get_item_rect_max()))

    return ImApp(gui), state


@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_a_click_lands_on_the_button_drawn_there(device, ratio):
    app, state = _button_app()
    host = _native(app, device, ratio, size=(240, 120))
    image = np.asarray(host.draw_frame())[..., :3].astype(float)
    (x0, y0), (x1, y1) = state["rect"]
    background = image[2, 2]
    inside = image[int(y0 * ratio) + 2:int(y1 * ratio) - 2,
                   int(x0 * ratio) + 2:int(x1 * ratio) - 2]
    # The button is drawn where its logical rect says, in device pixels ...
    assert np.abs(inside.mean(axis=(0, 1)) - background).max() > 10.0
    assert np.abs(image[int(y1 * ratio) + 3, int(x1 * ratio) + 3] - background).max() < 10.0
    # ... and a click at the logical centre (what the canvas reports) presses it.
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    event = {"x": cx, "y": cy, "button": 1, "buttons": (1,), "modifiers": ()}
    host.events._on_pointer_down(dict(event, event_type="pointer_down"))
    host.draw_frame()
    host.events._on_pointer_up(dict(event, event_type="pointer_up", buttons=()))
    host.draw_frame()
    assert state["clicks"] == 1


class _WebCanvas:
    """A ``<canvas>`` stand-in whose current texture is a real wgpu texture."""

    def __init__(self, device, css, dpr):
        self.device = device
        self.clientWidth, self.clientHeight = css
        self.width, self.height = int(css[0] * dpr), int(css[1] * dpr)
        self.texture = None

    def getContext(self, kind):  # noqa: N802 - the DOM's spelling
        return self

    def getCurrentTexture(self):  # noqa: N802
        import wgpu

        self.texture = self.device.create_texture(
            size=(self.width, self.height, 1), format="rgba8unorm",
            usage=wgpu.TextureUsage.RENDER_ATTACHMENT | wgpu.TextureUsage.COPY_SRC)
        texture = self.texture

        class _Texture:
            def createView(self):  # noqa: N802
                return texture.create_view()
        return _Texture()

    def pixels(self):
        stride = self.width * 4
        data = self.device.queue.read_texture(
            {"texture": self.texture, "origin": (0, 0, 0), "mip_level": 0},
            {"offset": 0, "bytes_per_row": stride, "rows_per_image": self.height},
            (self.width, self.height, 1))
        return np.frombuffer(data, np.uint8).reshape(self.height, self.width, 4)


def test_the_page_follows_device_pixel_ratio_the_same_way(device):
    from emtk.web.page import WebPage

    shots = {}
    for ratio in (1.0, 2.0):
        probe = _Probe()
        canvas = _WebCanvas(device, SIZE, ratio)
        page = WebPage(canvas, probe, device=device, format="rgba8unorm")
        assert page.surface._box() == (0.0, 0.0, float(SIZE[0]), float(SIZE[1]))
        page.draw()
        shots[ratio] = _measure(canvas.pixels())
        # A resize is CSS pixels in, device pixels to the surface.
        assert page.resize(SIZE[0] + 10, SIZE[1], ratio)
        assert page.surface.size == (int((SIZE[0] + 10) * ratio), int(SIZE[1] * ratio))
        assert page.surface._box()[2] == pytest.approx(SIZE[0] + 10)
    _check_pair(shots[1.0], shots[2.0], probe.advance)
    assert shots[2.0]["cap"] / 2.0 == pytest.approx(CAP, rel=CAP_TOLERANCE)


# --------------------------------------------------------------------------- #
# Qt: QPainter on an image with a device pixel ratio, as a Retina widget has
# --------------------------------------------------------------------------- #
def test_qt_text_is_one_logical_size_at_every_ratio(qt_app):
    from qtpy import QtGui

    from emtk.qt_painter import QtPainter, image_bytes

    shots = {}
    for ratio in (1.0, 2.0):
        image = QtGui.QImage(int(SIZE[0] * ratio), int(SIZE[1] * ratio),
                             QtGui.QImage.Format_RGBA8888)
        image.setDevicePixelRatio(ratio)
        image.fill(QtGui.QColor(*BACKGROUND))
        qt = QtGui.QPainter(image)
        try:
            probe = _Probe()
            probe.draw(QtPainter(qt, DEFAULT_FONT_PT), 0.0, 0.0, *SIZE)
        finally:
            qt.end()
        w, h, raw = image_bytes(image)
        shots[ratio] = _measure(np.frombuffer(raw, np.uint8).reshape(h, w, 4))
    _check_pair(shots[1.0], shots[2.0], probe.advance)
    # The same logical size as the GPU hosts: a Qt point is not an emtk point
    # (72 dpi on macOS and on a QImage), and the painter must not care.
    assert shots[2.0]["cap"] / 2.0 == pytest.approx(CAP, rel=CAP_TOLERANCE)


# --------------------------------------------------------------------------- #
# Tk: Pillow, one pixel per logical pixel
# --------------------------------------------------------------------------- #
def test_the_tk_frame_draws_the_same_logical_text():
    pytest.importorskip("PIL")
    from emtk.pil_painter import PilPainter

    probe = _Probe()
    painter = PilPainter(*SIZE, background=BACKGROUND + (255,),
                         scale=DEFAULT_FONT_PT / load_atlas().font_pt)
    probe.draw(painter, 0.0, 0.0, *SIZE)
    got = _measure(np.asarray(painter.frame))
    assert got["pitch"] == pytest.approx(probe.advance, abs=0.3)
    assert got["cap"] == pytest.approx(CAP, rel=CAP_TOLERANCE)
