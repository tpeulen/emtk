"""A later repack must not invalidate earlier image/font quads in this frame."""

import numpy as np

from emtk.gpu_atlas import ImageAtlas
from emtk.quad_painter import QuadPainter
from emtk.texture import Texture


def test_quads_and_image_triangles_refresh_after_repack():
    atlas = ImageAtlas(16, 16)
    filler = Texture(8, 8)
    filler.fill((255, 0, 0, 255))
    live = Texture(8, 8)
    live.fill((0, 255, 0, 255))
    atlas.region(filler)
    p = QuadPainter()
    p.image_uv_resolver = atlas.region
    p.image(0, 0, 8, 8, live)
    p.image_triangle((0, 8), (8, 8), (8, 16), live)
    before = atlas.region(live)
    atlas.forget(filler)
    assert atlas._repack()
    after = atlas.region(live)
    assert before != after
    vertices = p.vertices()
    expected = np.asarray(
        [
            after[0],
            (after[1][0], after[0][1]),
            after[1],
            after[0],
            after[1],
            (after[0][0], after[1][1]),
        ]
    )
    np.testing.assert_allclose(vertices[:6, 2:4], expected, rtol=1e-7)
    np.testing.assert_allclose(vertices[6:, 2:4], expected[:3], rtol=1e-7)


def test_current_frame_handles_stay_alive_until_clear():
    import weakref

    atlas = ImageAtlas(16, 16)
    p = QuadPainter()
    p.image_uv_resolver = atlas.region
    texture = Texture(8, 8)
    ref = weakref.ref(texture)
    p.image(0, 0, 8, 8, texture)
    del texture
    assert ref() is not None
    p.clear()
    assert ref() is None
