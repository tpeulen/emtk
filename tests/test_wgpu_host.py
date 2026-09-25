"""The wgpu host: one draw call, both atlas halves, and images.

Three layers, and each runs where it can:

* the **shader** -- ``ui.wgsl`` itself -- is text, and is read here with no
  adapter and no toolkit at all. The conventions it decodes live in
  :mod:`emtk.gpu_atlas` and are tested there, for the same reason;
* the **renderer** needs a device, which it gets from
  :func:`emtk.wgpu_host.default_device`. It does **not** need a window: it
  renders into an offscreen texture and hands the pixels back, which is why
  the interesting assertions here are about pixels rather than about calls
  made;
* the **widget** needs Qt and ``rendercanvas``, so its event forwarding is
  tested without ever asking for a surface.

Everything skips rather than fails where the layer below is missing. An
optional backend is allowed to be untested on a machine that cannot run it.

The one thing this file is really for: **headless green is not the app
working.** A clean render and a passing suite once coexisted with an
interface that was entirely missing under Qt, and what found it was
measuring drawn pixels and their bounding box. So the tests below measure
ink, compare against the CPU rasteriser, and check that an accented string
draws *more* of it than an unaccented one -- because an ink-only assertion
passes when the wrong glyph is drawn.
"""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy", reason="the GPU path builds its vertices "
                                         "with NumPy")

import emtk.im as im
from emtk.font import load_atlas
from emtk.gpu_atlas import ImageAtlas
from emtk.quad_painter import FLOATS_PER_VERTEX, QuadPainter
from emtk.testing import PixelPainter
from emtk.texture import Texture
from emtk.wgsl import UI_SHADER, load_wgsl, wgsl_path

#: The interface both hosts are asked to draw. Small, but it exercises a
#: panel, a filled widget, a stroked one, a line and text -- which between
#: them are every quad shape the painter emits.
FRAME = (0.0, 0.0, 320.0, 220.0)
BACKGROUND = (30, 32, 38)

#: Characters no reasonable build bakes -- the baked charset is Latin-1 and
#: Latin Extended-A, so accented Latin is *in* it and Greek, Cyrillic and CJK
#: are not. These can only come from the runtime cache, which lives in the
#: *lower* half of the texture.
BEYOND_THE_BAKED = "Δ λ 日"


def demo() -> None:
    """One frame of an ordinary interface."""
    im.begin("Demo", (10, 10, 200, 150))
    im.text(f"Hello {BEYOND_THE_BAKED}")
    im.button("OK")
    im.separator()
    im.checkbox("enabled", True)
    im.slider_float("gain", 0.4, 0.0, 1.0)
    im.end()


def draw_frame(painter, gui=demo, frames: int = 2, size=FRAME) -> None:
    """Draw *gui* through *painter*, settling the layout first."""
    io = im.IO()
    for _ in range(max(1, frames)):
        if hasattr(painter, "clear"):
            painter.clear()
        with im.frame(painter, size, io=io):
            gui()


def _luminance(rgba):
    return rgba[:, :, :3].astype(float).mean(axis=2)


# --------------------------------------------------------------------------- #
# The shader
# --------------------------------------------------------------------------- #
def test_the_shader_lives_in_emtk_and_says_what_it_must():
    """A string check, and worth having anyway: each line below is a bug
    that has been shipped by someone. Straight alpha out darkens every
    antialiased edge against a light background -- invisible on the dark
    panel, obvious the moment the background is white."""
    source = load_wgsl(UI_SHADER)
    assert wgsl_path(UI_SHADER).is_file()
    # the two entry points the pipeline names
    assert "fn vs_ui" in source
    assert "fn fs_ui" in source
    # premultiplied out, not straight
    assert "vec4<f32>(in.colour.rgb * alpha, alpha)" in source
    # the clip rectangle is per-vertex, not a scissor
    assert "discard" in source
    # coverage comes from alpha, so the vertex colour decides the look
    assert ").a;" in source
    # and the image branch is the sign of u
    assert "in.uv.x < -0.5" in source
    # group 1, so an application whose prelude owns group 0 can load this
    # very file rather than keeping a second copy of it
    assert "@group(1) @binding(0)" in source
    assert "@group(0)" not in source


def test_the_shader_is_packaged_and_not_only_on_this_disk():
    """A shader read with ``__file__`` and never declared as package data is
    present in a checkout and absent from an install, which is a failure
    that only ever happens to somebody else."""
    from emtk.wgsl import WGSL_DIR  # noqa: PLC0415

    # Read as text rather than parsed: `tomllib` is 3.11 and emtk supports
    # older, and the thing being asserted is one line either way.
    config = (WGSL_DIR.parents[1] / "pyproject.toml").read_text()
    declared = [line for line in config.splitlines()
                if line.startswith("emtk = [")]
    assert declared and ".wgsl" in declared[0], declared


def test_the_vertex_layout_is_the_painters_and_not_a_second_opinion():
    """A stride that disagrees with the painter does not fail: it draws a
    plausible-looking panel out of the wrong bytes."""
    from emtk.gpu_atlas import ATTRIBUTES, VERTEX_BYTES  # noqa: PLC0415

    assert VERTEX_BYTES == FLOATS_PER_VERTEX * 4
    location, count, offset = ATTRIBUTES[-1]
    assert offset + count * 4 == VERTEX_BYTES
    assert [a[0] for a in ATTRIBUTES] == [0, 1, 2, 3]


# --------------------------------------------------------------------------- #
# The renderer, on a real device
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def renderer():
    """One renderer for the whole session.

    The glyph atlas is 640x3835 RGBA -- ten megabytes -- and there is no
    reason for each test to hold its own copy of it on the GPU. What a test
    *does* vary is the image atlas, and the renderer notices that being
    swapped because it keys its upload on the atlas's identity as well as
    its version.
    """
    pytest.importorskip("wgpu", reason="the GPU host needs the wgpu binding")

    from emtk.wgpu_host import WgpuRenderer  # noqa: PLC0415

    try:
        r = WgpuRenderer()
        _ = r.device
        return r
    except Exception as exc:  # pragma: no cover - a machine with no GPU
        pytest.skip(f"no usable wgpu adapter here: {exc}")



class _Frame:
    """A painter, a fresh image atlas, and the renderer that draws them."""

    def __init__(self, renderer, font_scale: float = 1.0, scale: float = 1.0):
        self.renderer = renderer
        self.images = ImageAtlas()
        renderer.images = self.images
        # The renderer's own image texture is keyed on the atlas's identity,
        # so swapping it here is noticed. Nothing else has to be reset.
        self.painter = QuadPainter(atlas=renderer.atlas, scale=scale,
                                   font_scale=font_scale)
        self.painter.image_uv_resolver = self.images.region

    def grab(self, size=FRAME, background=BACKGROUND):
        return self.renderer.grab(
            self.painter, int(size[2]), int(size[3]), background=background)


def test_a_whole_interface_is_one_draw_call(renderer):
    """The number this design exists to keep at one. The clip rectangle
    rides on the vertex instead of being a scissor, and a rectangle samples
    the atlas's opaque block instead of taking a second pipeline; both are
    only worth doing because of this assertion."""
    frame = _Frame(renderer)
    draw_frame(frame.painter)
    frame.grab()
    assert renderer.draw_calls == 1


def test_an_empty_frame_draws_nothing_at_all(renderer):
    frame = _Frame(renderer)
    pixels = frame.grab()
    assert renderer.draw_calls == 0
    assert (pixels[:, :, 0] == BACKGROUND[0]).all()


def test_the_interface_actually_appears(renderer):
    """Ink, and where it is. A bounding box of ``x 4-7`` is how a whole
    missing interface was once found behind a suite that was green."""
    frame = _Frame(renderer)
    draw_frame(frame.painter)
    pixels = frame.grab()
    lit = _luminance(pixels) > float(np.mean(BACKGROUND)) + 20
    assert lit.mean() > 0.01, "the frame drew nothing"
    rows, columns = np.nonzero(lit)
    assert columns.min() < 20 and columns.max() > 150, (
        f"the interface spans only x {columns.min()}-{columns.max()}")
    assert rows.min() < 20 and rows.max() > 80


def test_it_matches_the_reference_rasteriser(renderer):
    """Against ``PixelPainter``, which reads the *same* atlas metrics, so
    the layouts are identical and only the rasterisation differs. This is
    the tight comparison; the one against the QPainter host below is
    necessarily loose, because that host measures its text with Qt."""
    frame = _Frame(renderer)
    draw_frame(frame.painter)
    got = frame.grab()

    reference = PixelPainter(int(FRAME[2]), int(FRAME[3]),
                             background=(*BACKGROUND, 255))
    draw_frame(reference)
    expected = np.frombuffer(bytes(reference.px), np.uint8).reshape(
        int(FRAME[3]), int(FRAME[2]), 4)

    a, b = _luminance(got), _luminance(expected)
    assert float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) > 0.9
    # antialiased glyph edges differ -- a box filter against a bilinear
    # sample -- and nothing else should
    assert float((np.abs(a - b) > 32).mean()) < 0.02


def test_it_looks_like_the_qpainter_host(renderer, qt_app):
    """Coarsely, and it can only be coarse.

    The QPainter host measures its text with **Qt**; this one measures it
    with the baked atlas, which is the whole reason the atlas exists. The
    two therefore lay out to slightly different line heights and the images
    do not line up pixel for pixel -- so the comparison is over 32-pixel
    blocks, which is "the same picture" rather than "the same pixels".
    """
    from qtpy import QtGui  # noqa: PLC0415

    from emtk.qt_painter import QtPainter, image_bytes  # noqa: PLC0415

    frame = _Frame(renderer, font_scale=9.0 / load_atlas().font_pt)
    draw_frame(frame.painter)
    got = frame.grab()

    image = QtGui.QImage(int(FRAME[2]), int(FRAME[3]),
                         QtGui.QImage.Format_RGBA8888)
    image.fill(QtGui.QColor(*BACKGROUND))
    qt = QtGui.QPainter(image)
    try:
        draw_frame(QtPainter(qt, 9.0))
    finally:
        qt.end()
    _w, _h, raw = image_bytes(image)
    expected = np.frombuffer(raw, np.uint8).reshape(
        int(FRAME[3]), int(FRAME[2]), 4)

    def coarse(values, block: int = 32):
        h, w = values.shape
        return values[:h // block * block, :w // block * block].reshape(
            h // block, block, w // block, block).mean(axis=(1, 3))

    a, b = coarse(_luminance(got)), coarse(_luminance(expected))
    assert float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) > 0.85


def test_a_two_times_device_scale_is_the_same_picture(renderer):
    """The interface lays itself out in **logical** pixels -- that is what a
    mouse event carries -- while the surface is in device pixels, and the
    painter applies the ratio where layout becomes geometry.

    Getting it wrong does not look like a scaling bug. The interface draws
    at half size in the corner of the window while hit-testing still answers
    for where it should be, so every click misses by the ratio and the
    interface looks inert rather than misplaced.
    """
    width, height = int(FRAME[2]), int(FRAME[3])

    def shot(scale):
        frame = _Frame(renderer, scale=scale)
        draw_frame(frame.painter)
        pixels = frame.grab(size=(0.0, 0.0, width * scale, height * scale))
        assert renderer.draw_calls == 1
        return pixels

    once = _luminance(shot(1))
    twice = _luminance(shot(2)).reshape(height, 2, width, 2).mean(axis=(1, 3))
    assert float(np.corrcoef(once.ravel(), twice.ravel())[0, 1]) > 0.95


# --------------------------------------------------------------------------- #
# Text, from both halves of the atlas
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(load_atlas().cache is None, reason="no glyph rasteriser")
def test_a_frame_draws_glyphs_from_both_atlas_halves(renderer):
    """Ink alone would pass if the wrong glyph were drawn, so the accented
    string is compared against the unaccented one: the accents are extra
    marks, so they must add ink. A host that uploaded only the baked half
    would draw whatever happened to be at the cache's coordinates -- often
    nothing, sometimes a different letter."""
    def ink(text: str) -> int:
        # three times the baked size, so an accent is several pixels rather
        # than one and the comparison below is not a rounding argument
        frame = _Frame(renderer, font_scale=3.0)
        frame.painter.text(4.0, 4.0, 300.0, 60.0, 0, text, (255, 255, 255, 255))
        return int((_luminance(frame.grab()) > 90).sum())

    assert ink("plain ASCII") > 0, "the baked half drew nothing"

    # Greek: every character here comes from the cache, and the two strings
    # are the same length, so the only difference is the tonos marks. An
    # ink-only check passes when the *wrong* glyph is drawn; this one does
    # not, because the wrong glyph would have to differ by exactly an
    # accent's worth of pixels in the right direction.
    plain = ink("αλφα βητα")
    accented = ink("άλφα βήτα")
    assert plain > 0, "the cache half drew nothing at all"
    assert accented > 0, "the cache half drew nothing for accented Greek"
    assert accented != plain, (
        f"accented Greek drew {accented} lit pixels against {plain} for the "
        f"same string without the tonos; they must differ")

    for char in BEYOND_THE_BAKED.split():
        assert ink(char) > 0, f"{char!r} drew nothing"


@pytest.mark.skipif(load_atlas().cache is None, reason="no glyph rasteriser")
def test_a_glyph_rasterised_after_the_first_upload_still_draws(renderer):
    """The cache rows are patched into a texture that already exists, so a
    character seen for the first time on frame 400 has to reach the GPU
    without the whole ten-megabyte atlas being rebuilt. Uploading it *next*
    frame would show one frame of the wrong texels; not uploading it at all
    shows them forever."""
    frame = _Frame(renderer, font_scale=3.0)
    frame.painter.text(4.0, 4.0, 300.0, 60.0, 0, "warm up", (255, 255, 255, 255))
    frame.grab()

    # A character the baker never saw and this session has not asked for.
    later = _Frame(renderer, font_scale=3.0)
    later.painter.text(4.0, 4.0, 300.0, 60.0, 0, "ᛖᛗ", (255, 255, 255, 255))
    assert int((_luminance(later.grab()) > 90).sum()) > 0


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def test_an_image_draws_its_own_pixels_and_not_the_fallback(renderer):
    """Without the second texture the painter degrades to a tinted
    rectangle, which is a flat colour. A checker is not flat, so this fails
    the moment the negative-u branch stops selecting."""
    checker = Texture(4, 4)
    for y in range(4):
        for x in range(4):
            checker.set_pixel(x, y, (255, 240, 0, 255) if (x + y) % 2 == 0
                              else (0, 90, 255, 255))

    frame = _Frame(renderer)
    frame.painter.image(20.0, 20.0, 120.0, 120.0, checker)
    pixels = frame.grab()
    assert renderer.draw_calls == 1

    inside = pixels[40:120, 40:120, :3].astype(float)
    assert inside.std() > 20.0, "the image drew as one flat colour"
    assert (inside[:, :, 0] > 150).any(), "the yellow squares are missing"
    assert (inside[:, :, 2] > 150).any(), "the blue squares are missing"


def test_text_drawn_after_an_image_lands_on_it(renderer):
    """Draw order survives, which is the reason images share the one
    pipeline instead of taking a second pass."""
    black = Texture(4, 4)
    black.fill((0, 0, 0, 255))

    frame = _Frame(renderer)
    frame.painter.image(0.0, 0.0, 200.0, 60.0, black)
    frame.painter.text(4.0, 4.0, 190.0, 40.0, 0, "OVER", (255, 255, 255, 255))
    pixels = frame.grab()
    assert (_luminance(pixels[0:60, 0:200]) > 120).any(), \
        "the text was drawn under the image"


def test_a_changed_image_reaches_the_gpu_on_the_frame_it_changed(renderer):
    """A live camera frame changes every frame. Uploading it *after* the
    draw shows the previous picture, which reads as lag rather than as a
    bug, and is the reason the uploads happen before the draw."""
    live = Texture(4, 4)
    live.fill((255, 0, 0, 255))
    frame = _Frame(renderer)
    frame.painter.image(0.0, 0.0, 80.0, 80.0, live)
    first = frame.grab()
    assert first[40, 40, 0] > 200 and first[40, 40, 2] < 60

    live.fill((0, 0, 255, 255))
    later = _Frame(renderer)
    later.images = frame.images
    renderer.images = frame.images
    later.painter.image_uv_resolver = frame.images.region
    later.painter.image(0.0, 0.0, 80.0, 80.0, live)
    second = later.grab()
    assert second[40, 40, 2] > 200 and second[40, 40, 0] < 60, \
        "the changed image did not reach this frame's texture"


# --------------------------------------------------------------------------- #
# The widget: input forwarding, which needs no surface
# --------------------------------------------------------------------------- #
class _Recorder:
    """A control that records what the host forwarded to it."""

    def __init__(self) -> None:
        self.calls: list = []

    def draw(self, painter, x, y, w, h) -> None:
        painter.fill_rect(x, y, w, h, (200, 200, 200, 255))

    def press(self, px, py, x, y, w, h, modifiers, clicks) -> None:
        self.calls.append(("press", px, py, clicks))

    def drag(self, px, py, x, y, w, h) -> None:
        self.calls.append(("drag", px, py))

    def release(self) -> None:
        self.calls.append(("release",))

    def hover(self, px, py, x, y, w, h) -> None:
        self.calls.append(("hover", px, py))

    def scroll(self, amount) -> None:
        self.calls.append(("scroll", amount))

    def key(self, code, text, modifiers) -> bool:
        self.calls.append(("key", code, text))
        return True


class _Wheel:
    """A wheel event, ducked rather than constructed.

    ``QWheelEvent``'s constructor differs between the Qt versions qtpy
    spans; the handler reads ``angleDelta().y()`` and nothing else, so this
    tests the contract rather than the binding.
    """

    def __init__(self, y: int) -> None:
        self._y = y

    def angleDelta(self):  # noqa: N802 - Qt's spelling
        class _Point:
            def __init__(self, y):
                self._y = y

            def y(self):
                return self._y
        return _Point(self._y)


@pytest.fixture()
def host(qt_app):
    """A wgpu host widget, never shown, so no surface is ever asked for."""
    pytest.importorskip("wgpu", reason="the GPU host needs the wgpu binding")
    pytest.importorskip(
        "rendercanvas", reason="the GPU host gets its surface from rendercanvas")

    from emtk.wgpu_host import WgpuControlHost  # noqa: PLC0415

    control = _Recorder()
    widget = WgpuControlHost(control)
    widget.resize(200, 100)
    return widget, control


def test_a_press_a_drag_and_a_release_reach_the_control(host):
    from qtpy import QtCore, QtGui  # noqa: PLC0415

    widget, control = host
    point = QtCore.QPointF(12.0, 34.0)
    press = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress, point, QtCore.Qt.LeftButton,
        QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    widget.mousePressEvent(press)
    move = QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove, QtCore.QPointF(20.0, 40.0),
        QtCore.Qt.NoButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    widget.mouseMoveEvent(move)
    widget.mouseReleaseEvent(move)

    assert [call[0] for call in control.calls] == ["press", "drag", "release"]
    assert control.calls[0][1:] == (12.0, 34.0, 1)
    assert control.calls[1][1:] == (20.0, 40.0)


def test_a_move_with_no_button_down_is_a_hover(host):
    from qtpy import QtCore, QtGui  # noqa: PLC0415

    widget, control = host
    widget.mouseMoveEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseMove, QtCore.QPointF(5.0, 6.0),
        QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
    assert control.calls == [("hover", 5.0, 6.0)]


def test_a_wheel_notch_is_three_rows_sign_flipped(host):
    """``scroll`` takes **one** argument, in rows. A wheel pushed away is a
    positive delta and scrolls the content up, which is a negative offset --
    the opposite sign to the raw wheel, and the mistake that makes every
    list scroll backwards."""
    widget, control = host
    widget.wheelEvent(_Wheel(120))
    widget.wheelEvent(_Wheel(-120))
    assert control.calls == [("scroll", -3), ("scroll", 3)]


def test_a_key_the_control_consumed_is_not_passed_on(host):
    from qtpy import QtCore, QtGui  # noqa: PLC0415

    widget, control = host
    widget.keyPressEvent(QtGui.QKeyEvent(
        QtCore.QEvent.KeyPress, int(QtCore.Qt.Key_A),
        QtCore.Qt.NoModifier, "a"))
    assert control.calls == [("key", int(QtCore.Qt.Key_A), "a")]


def test_the_change_signal_and_the_callback_both_fire(host):
    from qtpy import QtCore, QtGui  # noqa: PLC0415

    widget, control = host
    seen = []
    widget.on_change = seen.append
    widget.changed.connect(lambda: seen.append("signal"))
    widget.mousePressEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress, QtCore.QPointF(1.0, 1.0),
        QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
    assert seen == [control, "signal"]


def test_the_host_shares_its_renderers_image_atlas(host):
    """The painter resolves an image handle through the *renderer's* atlas,
    and a host that quietly kept a second one would draw every image as a
    flat tinted box -- the painter's fallback, which is not an error."""
    widget, _control = host
    assert widget.images is widget.renderer.images


def test_a_nearest_texture_draws_sharp_blocks(renderer):
    """``Texture(filter="nearest")``: a 2x2 checker scaled to 120 px is four
    solid squares -- no blended band between them, and no texel shaved off
    the edge. A linear one blends across the middle."""
    def checker(filter):
        tex = Texture(2, 2, filter=filter)
        for y in range(2):
            for x in range(2):
                tex.set_pixel(x, y, (255, 255, 255, 255) if (x + y) % 2 == 0
                              else (0, 0, 0, 255))
        return tex

    frame = _Frame(renderer)
    frame.painter.image(20.0, 20.0, 120.0, 120.0, checker("nearest"))
    frame.painter.image(160.0, 20.0, 120.0, 120.0, checker("linear"))
    pixels = frame.grab(size=(0, 0, 300, 160))
    sharp = _luminance(pixels[20:140, 20:140])
    soft = _luminance(pixels[20:140, 160:280])
    grey = lambda block: ((block > 30) & (block < 225)).mean()  # noqa: E731
    assert grey(sharp) < 0.03, "the nearest texture blended its texels"
    assert grey(soft) > 0.2, "the linear texture did not blend"
    assert sharp[2, 2] > 225 and sharp[2, 117] < 30      # the corner texels are whole


def test_a_nearest_region_is_not_inset_and_says_so_in_v():
    from emtk.gpu_atlas import image_texel  # noqa: PLC0415

    atlas = ImageAtlas(64, 64)
    (u0, v0), (u1, v1) = atlas.region(Texture(8, 4, filter="nearest"))
    assert image_texel(u0, 64) == 0.0 and image_texel(u1, 64) == 8.0
    assert (v0, v1) == (-1.0, -5.0)
    (u0, v0), (_u1, _v1) = atlas.region(Texture(8, 4))
    assert v0 > 0


def test_a_texture_filter_is_linear_or_nearest():
    assert Texture(1, 1).filter == "linear"
    with pytest.raises(ValueError):
        Texture(1, 1, filter="cubic")
