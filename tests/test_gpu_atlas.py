"""The conventions a GPU host uploads by, tested with no GPU at all.

:mod:`emtk.gpu_atlas` is the layer between :class:`~emtk.quad_painter.QuadPainter`
and a device: the combined glyph atlas, the image atlas, and the negative-u
encoding that lets an image quad and a glyph quad ride in one vertex buffer,
one pipeline and one draw call.

None of it knows what a device is, and that is the point of the module and
of this file. These are the parts that used to be tested only through a
host, which meant they were tested only on a machine that could make a
context. They are arithmetic and NumPy; they should run anywhere, and here
they do.

:mod:`emtk.wgpu_host` is where the same conventions are checked against real
pixels on a real adapter -- see ``tests/test_wgpu_host.py``.
"""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy", reason="the GPU path builds its buffers "
                                         "with NumPy")

from emtk.font import load_atlas
from emtk.gpu_atlas import (
    DIRTY_LOG,
    ImageAtlas,
    atlas_pixels,
    image_texel,
    image_u,
)
from emtk.quad_painter import QuadPainter
from emtk.texture import Texture

#: Characters no reasonable build bakes -- the baked charset is Latin-1 and
#: Latin Extended-A, so accented Latin is *in* it and Greek, Cyrillic and CJK
#: are not. These can only come from the runtime cache, which lives in the
#: *lower* half of the texture.
BEYOND_THE_BAKED = "Δ λ 日"


# --------------------------------------------------------------------------- #
# The negative-u convention
# --------------------------------------------------------------------------- #
def test_an_image_u_is_negative_and_a_glyph_u_is_not():
    """The sign is the whole selector. One vertex format, one pipeline, one
    draw call -- the fragment stage tests ``u < -0.5`` and nothing else has
    to say which texture a quad meant."""
    assert image_u(0.0, 1024) == -1.0
    assert image_u(1024.0, 1024) == -2.0
    for x in (0.0, 1.0, 512.0, 1023.0):
        assert image_u(x, 1024) < -0.5

    painter = QuadPainter()
    painter.fill_rect(0.0, 0.0, 10.0, 10.0, (255, 255, 255, 255))
    painter.text(0.0, 0.0, 100.0, 20.0, 0, "Ag", (255, 255, 255, 255))
    uvs = painter.vertices()[:, 2]
    assert (uvs >= 0.0).all(), "a glyph or rect u must never look like an image"


@pytest.mark.parametrize("texel", [0.0, 0.5, 37.25, 512.0, 1023.5])
def test_the_encoding_round_trips(texel):
    assert image_texel(image_u(texel, 1024), 1024) == pytest.approx(texel)


def test_the_encoding_is_affine_so_windowing_survives_it():
    """``QuadPainter.image`` interpolates between the two corners a resolver
    returns when a caller windows into an image with ``uv0``/``uv1``. An
    encoding that was not affine in the texel would decode that
    interpolation to the wrong column -- silently, as a sheared picture."""
    width = 256
    u0, u1 = image_u(0.0, width), image_u(64.0, width)
    for fraction in (0.0, 0.25, 0.5, 1.0):
        midpoint = u0 + fraction * (u1 - u0)
        assert image_texel(midpoint, width) == pytest.approx(64.0 * fraction)


# --------------------------------------------------------------------------- #
# The image atlas
# --------------------------------------------------------------------------- #
def test_a_texture_is_placed_once_and_keeps_its_region():
    atlas = ImageAtlas(64, 64)
    texture = Texture(8, 4)
    texture.fill((10, 20, 30, 255))
    first = atlas.region(texture)
    assert first is not None
    assert atlas.region(texture) == first


def test_a_second_texture_is_packed_beside_the_first():
    atlas = ImageAtlas(64, 64)
    left, right = Texture(8, 4), Texture(8, 4)
    left.fill((255, 0, 0, 255))
    right.fill((0, 255, 0, 255))
    (lu0, _), _ = atlas.region(left)
    (ru0, _), _ = atlas.region(right)
    assert image_texel(ru0, 64) > image_texel(lu0, 64)


def test_the_shelf_wraps_and_then_declines():
    """It never grows and never defragments: an image that does not fit is
    declined, and the painter's own fallback draws a tinted rectangle. A
    visible wrong thing beats an allocation storm."""
    atlas = ImageAtlas(16, 16)
    first, second = Texture(16, 8), Texture(16, 8)
    assert atlas.region(first) is not None
    assert atlas.region(second) is not None      # the next shelf down
    assert atlas.region(Texture(16, 8)) is None  # no third shelf


def _solid(width, height, value):
    texture = Texture(width, height, filter="nearest")
    texture.fill((value, value, value, 255))
    return texture


def _texels(atlas, texture):
    """The atlas' copy of *texture*: ``(w, h, first texel's red)``."""
    _ref, _rev, x, y, w, h = atlas._placed[id(texture)]
    return w, h, int(atlas.pixels[y, x, 0])


def test_a_new_texture_at_a_dead_ones_id_gets_its_own_pixels_and_size():
    """An id is only unique among live objects. ndXplorer makes a new
    texture per redraw of its map; one allocated where a dead one was got
    its id, both were at revision 0, and the atlas handed back the dead
    map -- at the dead map's size. The allocator is not deterministic, so
    the reuse is played here the way it happens: the dead one's entry
    under the new one's id."""
    import gc

    atlas = ImageAtlas(64, 64)
    old = _solid(8, 4, 200)
    atlas.region(old)
    entry = atlas._placed.pop(id(old))
    del old
    gc.collect()
    new = _solid(4, 4, 50)
    atlas._placed[id(new)] = entry
    assert atlas.region(new) is not None
    assert _texels(atlas, new) == (4, 4, 50)


def test_textures_replaced_over_and_over_never_fill_the_atlas():
    """A map redrawn with a new colour scale is a new texture each time.
    Every one used to take fresh space, until the atlas was full and the
    map drew as a blank tinted box for the rest of the session."""
    import gc

    atlas = ImageAtlas(64, 64)
    live = None
    for i in range(500):
        size = (16, 16) if i % 3 else (20, 12)
        live = _solid(*size, i % 250 + 1)
        assert atlas.region(live) is not None, f"declined at redraw {i}"
        assert _texels(atlas, live) == (*size, i % 250 + 1)
        gc.collect()


def test_a_forgotten_spot_is_reused():
    atlas = ImageAtlas(16, 16)
    first, second = _solid(16, 8, 10), _solid(16, 8, 20)
    atlas.region(first)
    atlas.region(second)
    atlas.forget(first)
    third = _solid(16, 8, 30)
    assert atlas.region(third) is not None
    assert _texels(atlas, third) == (16, 8, 30)
    assert _texels(atlas, second) == (16, 8, 20)


def test_a_full_atlas_packs_its_live_images_again():
    """Dead space no newcomer fits in by itself is won back by packing
    what is still alive from the top left; the live images keep their
    pixels."""
    import gc

    atlas = ImageAtlas(16, 16)
    keep = _solid(4, 4, 70)
    atlas.region(keep)
    dead = [_solid(4, 4, 1) for _ in range(3)]      # the rest of the top shelf
    for texture in dead:
        atlas.region(texture)
    tall = _solid(16, 12, 2)                        # the rest of the atlas
    assert atlas.region(tall) is not None
    del dead, tall
    gc.collect()
    wide = _solid(12, 12, 90)                       # fits no dead spot alone
    assert atlas.region(wide) is not None
    assert _texels(atlas, wide) == (12, 12, 90)
    assert _texels(atlas, keep) == (4, 4, 70)


def test_a_handle_that_is_not_a_texture_is_declined_rather_than_guessed_at():
    assert ImageAtlas(32, 32).region("just a string") is None
    assert ImageAtlas(32, 32).region(object()) is None


def test_the_pixels_land_premultiplied():
    """The shader multiplies by the tint and composites with
    ``one, one_minus_src_alpha``. Straight alpha here is a light halo
    around every soft edge."""
    atlas = ImageAtlas(8, 8)
    texture = Texture(2, 1)
    texture.set_pixel(0, 0, (200, 100, 50, 128))
    texture.set_pixel(1, 0, (200, 100, 50, 255))
    atlas.region(texture)
    faded = atlas.pixels[0, 0]
    opaque = atlas.pixels[0, 1]
    assert tuple(int(v) for v in faded) == (100, 50, 25, 128)
    assert tuple(int(v) for v in opaque) == (200, 100, 50, 255)


def test_a_changed_texture_is_rewritten_and_an_unchanged_one_is_not():
    """A live camera frame changes every frame and a colour map almost
    never; ``revision`` is what tells the two apart, and ``version`` is what
    an uploader watches."""
    atlas = ImageAtlas(16, 16)
    texture = Texture(4, 4)
    texture.fill((255, 0, 0, 255))
    atlas.region(texture)
    settled = atlas.version
    atlas.region(texture)
    assert atlas.version == settled, "an unchanged texture was re-copied"

    texture.fill((0, 0, 255, 255))
    atlas.region(texture)
    assert atlas.version > settled
    assert tuple(int(v) for v in atlas.pixels[0, 0]) == (0, 0, 255, 255)


def test_the_region_insets_by_half_a_texel():
    """So a linear sample at the edge of one image cannot reach into the one
    packed beside it."""
    atlas = ImageAtlas(64, 64)
    texture = Texture(8, 4)
    (u0, v0), (u1, v1) = atlas.region(texture)
    assert image_texel(u0, 64) == pytest.approx(0.5)
    assert image_texel(u1, 64) == pytest.approx(7.5)
    assert (v0, v1) == pytest.approx((0.5, 3.5))


def test_the_painter_and_the_atlas_agree_on_a_windowed_image():
    """End to end, without a GPU: the painter windows into the region the
    atlas returned, and the shader's own arithmetic decodes it back to the
    right half of the picture."""
    atlas = ImageAtlas(128, 128)
    texture = Texture(20, 10)
    painter = QuadPainter()
    painter.image_uv_resolver = atlas.region
    painter.image(0.0, 0.0, 10.0, 10.0, texture, uv0=(0.5, 0.0), uv1=(1.0, 1.0))

    quad = np.asarray(painter._data, dtype=float)
    left, right = quad[4], quad[6]
    # half a texel in from the left of the right-hand half, and half a texel
    # short of the far edge
    assert image_texel(left, 128) == pytest.approx(0.5 + 0.5 * 19.0)
    assert image_texel(right, 128) == pytest.approx(19.5)


# --------------------------------------------------------------------------- #
# The dirty log
# --------------------------------------------------------------------------- #
def test_only_what_changed_is_reported_dirty():
    """A 1024x1024 atlas re-uploaded whole is 4 MB per frame to move a
    512x512 picture, and putting 4 MB back into the frame's critical path is
    most of the cost that drawing quads removed."""
    atlas = ImageAtlas(64, 64)
    seen = atlas.version
    left, right = Texture(8, 4), Texture(4, 4)
    atlas.region(left)
    atlas.region(right)
    rects, seen = atlas.dirty_since(seen)
    assert rects == [(0, 0, 8, 4), (8, 0, 4, 4)]
    assert atlas.dirty_since(seen)[0] == []

    left.fill((1, 2, 3, 255))
    atlas.region(left)
    assert atlas.dirty_since(seen)[0] == [(0, 0, 8, 4)]


def test_two_consumers_each_get_their_own_answer():
    """A version and a log, not a dirty flag: a flag the window clears
    leaves an offscreen grab drawing stale texels. That has happened -- the
    window drew Japanese and the grab drew blanks."""
    atlas = ImageAtlas(64, 64)
    window = grab = atlas.version
    texture = Texture(4, 4)
    atlas.region(texture)

    rects, window = atlas.dirty_since(window)
    assert rects == [(0, 0, 4, 4)]
    # the second consumer has not asked yet, and must still be told
    rects, grab = atlas.dirty_since(grab)
    assert rects == [(0, 0, 4, 4)]
    assert atlas.dirty_since(window)[0] == []


def test_a_consumer_further_behind_than_the_log_is_told_everything():
    """Slow and correct beats fast and wrong: a texture that missed some
    writes shows stale texels for as long as nothing else touches them."""
    atlas = ImageAtlas(64, 64)
    for _ in range(DIRTY_LOG + 2):
        handle = Texture(1, 1)
        atlas.region(handle)
        atlas.forget(handle)
    assert atlas.dirty_since(0)[0] is None


# --------------------------------------------------------------------------- #
# The combined glyph atlas
# --------------------------------------------------------------------------- #
def test_the_uploaded_atlas_is_both_halves():
    """``Atlas.cell_of`` returns coordinates in the *combined* space, so a
    host that uploads only the baked PNG samples past the end of its own
    texture for any character the baker never saw. Out of bounds that is a
    crash; in bounds it is silently the wrong glyph, which is the version
    that ships."""
    atlas = load_atlas()
    pixels = atlas_pixels(atlas)
    assert pixels.shape == (atlas.texture_height, atlas.size[0], 4)
    assert pixels.dtype == np.uint8
    assert pixels[:atlas.baked_height, :, 3].any(), "the baked half is blank"


@pytest.mark.skipif(load_atlas().cache is None,
                    reason="no glyph rasteriser on this machine; the atlas "
                           "draws its placeholder instead")
def test_a_cached_glyph_reaches_the_uploaded_atlas():
    atlas = load_atlas()
    for char in BEYOND_THE_BAKED.split():
        cell = atlas.cell_of(char)
        assert cell is not None
    pixels = atlas_pixels(atlas)
    assert pixels[atlas.baked_height:, :, 3].any(), (
        "a character the baker never saw was rasterised into the cache but "
        "did not reach the buffer the host uploads")


@pytest.mark.skipif(load_atlas().cache is None, reason="no glyph rasteriser")
def test_the_buffer_is_rebuilt_when_the_cache_grows():
    """The cache bumps ``version`` for every glyph it stores, and that -- not
    a consumed dirty list -- is what each consumer watches, so any number of
    devices can be fed from one cache."""
    atlas = load_atlas()
    atlas_pixels(atlas)
    before = atlas.cache.version
    atlas.cell_of("Ж")          # Cyrillic Zhe: never baked
    if atlas.cache.version == before:
        pytest.skip("this checkout's rasteriser has no glyph for it")
    pixels = atlas_pixels(atlas)
    assert pixels[atlas.baked_height:, :, 3].any()


def test_the_decoder_needs_no_toolkit_and_agrees_with_the_one_that_does():
    """Two decoders, one answer. The fast road is Qt's, through
    ``qt_painter``; the slow one is :mod:`emtk.testing`'s, and it is what
    runs on a machine with no toolkit at all. If they ever disagreed, the
    GPU path would draw differently depending on what happened to be
    installed."""
    from emtk.gpu_atlas import png_decode  # noqa: PLC0415
    from emtk.testing import png_decode as slow  # noqa: PLC0415

    data = load_atlas().image_path.read_bytes()
    fast_w, fast_h, fast = png_decode(data)
    slow_w, slow_h, pure = slow(data)
    assert (fast_w, fast_h) == (slow_w, slow_h)
    assert bytes(fast) == bytes(pure)


def test_the_atlas_decodes_without_importing_a_toolkit():
    """The GPU hosts exist so a process need not load Qt; reading the atlas
    must not load it either when Pillow can do the job."""
    import subprocess
    import sys

    pytest.importorskip("PIL")
    code = ("import sys\n"
            "from emtk.font import load_atlas\n"
            "from emtk.gpu_atlas import png_decode\n"
            "png_decode(load_atlas().image_path.read_bytes())\n"
            "print(','.join(m for m in sys.modules if m.split('.')[0] in "
            "('qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6')))\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ""
