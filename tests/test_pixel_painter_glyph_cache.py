"""PixelPainter text: the summed-area/coverage caches draw exactly what the texel loop drew.

The downsample used to sum every atlas texel under every destination pixel, which made an
800x600 tool frame cost ~3.7 s and every test that clicks through PixelPainter frames cost
tens of seconds. The cached path must stay bit-identical to that loop, so the loop is kept
here as the reference.
"""

from __future__ import annotations

import emtk.testing as et
from emtk.painter import ALIGN_HCENTER, ALIGN_VCENTER
from emtk.testing import PixelPainter


def _reference_alpha(src, src_w, u, v, gw, gh, x0, top, shrink):
    """The original per-texel box filter: ``{(x, y): alpha}`` for alpha >= 0.5."""
    texels = 1.0 / shrink
    out = {}
    for yy in range(int(top), int(top + gh * shrink) + 1):
        fy = (yy - top) * texels
        sy0 = v + (int(fy) if fy > 0.0 else 0)
        fy += texels
        sy1 = v + (gh if fy >= gh else int(fy) + 1)
        if sy1 <= sy0:
            continue
        for xx in range(int(x0), int(x0 + gw * shrink) + 1):
            fx = (xx - x0) * texels
            sx0 = u + (int(fx) if fx > 0.0 else 0)
            fx += texels
            sx1 = u + (gw if fx >= gw else int(fx) + 1)
            if sx1 <= sx0:
                continue
            total = 0
            for ty in range(sy0, sy1):
                base = ty * src_w * 4 + 3
                for tx in range(sx0, sx1):
                    total += src[base + tx * 4]
            alpha = total / ((sy1 - sy0) * (sx1 - sx0))
            if alpha >= 0.5:
                out[(xx, yy)] = alpha
    return out


def test_cached_coverage_equals_the_texel_loop_at_fractional_placements_and_scales():
    atlas = et._load_atlas()
    baked_w, _h, baked = et._atlas_pixels()
    for char in "Ag0%W":
        u, v, gw, gh = atlas.cell_of(char)
        assert v < atlas.baked_height
        for shrink in (atlas.render_scale, atlas.render_scale * 1.37, atlas.render_scale * 2.0):
            for x0, top in ((0.0, 0.0), (3.3, 2.7), (10.75, -1.25), (-2.4, 5.5)):
                got = et._glyph_coverage(("baked", u, v, gw, gh), baked, baked_w,
                                         u, v, gw, gh, x0, top, shrink, 1.0 / shrink)
                want = _reference_alpha(baked, baked_w, u, v, gw, gh, x0, top, shrink)
                assert {(x, y): a for x, y, a in got} == want


def test_a_redrawn_frame_reuses_the_coverage_and_draws_the_same_pixels():
    def frame():
        p = PixelPainter(240, 80, background=(10, 20, 30, 255))
        p.text(2.5, 1.5, 236, 30, 0, "Estimate 0.123", (255, 255, 255, 255))
        p.text(0, 40, 240, 30, ALIGN_HCENTER | ALIGN_VCENTER, "Fit", (200, 90, 40, 200), bold=True)
        return bytes(p.px)

    first = frame()
    cached = len(et._GLYPH_COVERAGE)
    assert cached > 0
    assert frame() == first
    assert len(et._GLYPH_COVERAGE) == cached


def test_clipping_still_bounds_cached_glyphs():
    whole = PixelPainter(120, 40)
    whole.text(0, 0, 120, 40, 0, "WWWW", (255, 255, 255, 255))
    clipped = PixelPainter(120, 40)
    clipped.push_clip(0, 0, 20, 40)
    clipped.text(0, 0, 120, 40, 0, "WWWW", (255, 255, 255, 255))
    stride = 120 * 4
    for y in range(40):
        row = slice(y * stride, y * stride + 20 * 4)
        assert clipped.px[row] == whole.px[row]
        assert not any(clipped.px[y * stride + 20 * 4: (y + 1) * stride][i] for i in range(0, 100 * 4, 4))
