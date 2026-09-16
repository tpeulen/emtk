"""QuadPainter.image: the optional blit, resolved by the host.

`Painter.image` has been an optional operation with no implementation in any
shipped painter -- an API surface only. This pins the QuadPainter's version of
it: the host installs `image_uv_resolver`, the painter emits a quad whose UVs
are the host's region (windowed by uv0/uv1), and without a resolver -- or when
one declines -- the call degrades to the protocol's own fallback, a tinted
rectangle, so no host ever crashes or draws silence over a missing image.
"""
from __future__ import annotations

import numpy as np
import pytest

from emtk.quad_painter import FLOATS_PER_QUAD, QuadPainter


@pytest.fixture()
def painter():
    return QuadPainter()


def _quads(painter):
    data = np.asarray(painter._data, dtype=float).reshape(-1, FLOATS_PER_QUAD)
    return data


def test_without_a_resolver_it_is_a_tinted_rect(painter):
    painter.image(4.0, 6.0, 30.0, 20.0, "some-handle", tint=(200, 40, 40, 255))
    (quad,) = _quads(painter)
    # the geometry of a rect ...
    assert quad[0:4] == pytest.approx((4.0, 6.0, 34.0, 26.0))
    # ... sampling the atlas's solid texel, tinted
    assert quad[4:6] == pytest.approx(painter._solid_uv)
    assert quad[6:8] == pytest.approx((painter._solid_uv[0],
                                       painter._solid_uv[1]))
    assert quad[8:12] == pytest.approx((200 / 255, 40 / 255, 40 / 255, 1.0))


def test_a_declining_resolver_falls_back(painter):
    painter.image_uv_resolver = lambda handle: None
    painter.image(0.0, 0.0, 5.0, 5.0, object())
    (quad,) = _quads(painter)
    assert quad[4:6] == pytest.approx(painter._solid_uv)


def test_the_resolved_region_rides_the_quads_uv(painter):
    painter.image_uv_resolver = lambda h: ((10.0, 20.0), (110.0, 70.0))
    painter.image(0.0, 0.0, 50.0, 50.0, "img")
    (quad,) = _quads(painter)
    assert quad[4:8] == pytest.approx((10.0, 20.0, 110.0, 70.0))


def test_uv_windowing_selects_a_sub_rectangle(painter):
    painter.image_uv_resolver = lambda h: ((10.0, 20.0), (110.0, 70.0))
    # the right half of the placed region only
    painter.image(0.0, 0.0, 25.0, 50.0, "img", uv0=(0.5, 0.0), uv1=(1.0, 1.0))
    (quad,) = _quads(painter)
    assert quad[4:8] == pytest.approx((60.0, 20.0, 110.0, 70.0))


def test_images_and_rects_interleave_in_draw_order(painter):
    painter.image_uv_resolver = lambda h: ((0.0, 0.0), (4.0, 4.0))
    painter.fill_rect(0.0, 0.0, 1.0, 1.0, (255, 255, 255, 255))
    painter.image(0.0, 2.0, 1.0, 1.0, "img")
    painter.fill_rect(0.0, 4.0, 1.0, 1.0, (255, 255, 255, 255))
    quads = _quads(painter)
    assert len(quads) == 3
    assert quads[1][4] == pytest.approx(0.0)      # the image is in the middle
    assert quads[0][4] == pytest.approx(painter._solid_uv[0])


def test_the_handle_is_passed_through_verbatim(painter):
    seen = []
    painter.image_uv_resolver = lambda h: (seen.append(h), ((0, 0), (1, 1)))[1]
    sentinel = object()
    painter.image(0.0, 0.0, 1.0, 1.0, sentinel)
    assert seen == [sentinel]
