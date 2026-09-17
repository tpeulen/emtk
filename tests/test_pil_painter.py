"""``PilPainter`` draws what ``PixelPainter`` draws, a few hundred times faster.

``PixelPainter`` is the reference: pure Python, every pixel decided in plain
sight. ``PilPainter`` exists to put the same picture in a window, so the tests
here are parity tests against it -- exact where the arithmetic is the same
(rectangles, clips, triangles by the pixel-centre rule, nearest-texel images),
bounded where it legitimately is not (a glyph lands on a whole pixel instead
of being resampled at a fractional pen position).
"""
from __future__ import annotations

import pytest

pytest.importorskip("PIL", reason="PilPainter needs Pillow")

from emtk import im  # noqa: E402
from emtk.im_core import BackendFlags, painter_capabilities  # noqa: E402
from emtk.painter import (  # noqa: E402
    ALIGN_CENTER,
    OPTIONAL_OPERATIONS,
    REQUIRED_OPERATIONS,
    fill_convex,
)
from emtk.pil_painter import PilPainter  # noqa: E402
from emtk.testing import PixelPainter  # noqa: E402
from emtk.texture import Texture  # noqa: E402

BG = (30, 32, 38, 255)


def pair(w=64, h=48):
    return PilPainter(w, h, background=BG), PixelPainter(w, h, background=BG)


def rgb(painter):
    """RGB triples, row-major: alpha is not part of what a window shows."""
    px = painter.px
    return [tuple(px[i:i + 3]) for i in range(0, len(px), 4)]


def max_channel_error(a, b):
    return max(max(abs(p - q) for p, q in zip(x, y)) for x, y in zip(rgb(a), rgb(b)))


def test_every_operation_is_there_and_callable():
    p = PilPainter(4, 4)
    for name in REQUIRED_OPERATIONS + OPTIONAL_OPERATIONS:
        assert callable(getattr(p, name, None)), name


def test_capabilities_report_images():
    """The frame is ``.frame``: an attribute named ``image`` hid the method.

    ``painter_capabilities`` asks ``callable(painter.image)``; with the frame
    stored under that name the answer was no, and every picture in a window
    silently became a white box.
    """
    flags = painter_capabilities(PilPainter(4, 4))
    assert flags & BackendFlags.RENDERER_HAS_IMAGES
    assert flags & BackendFlags.RENDERER_HAS_ROTATED_TEXT


@pytest.mark.parametrize("colour", [(200, 90, 40, 255), (200, 90, 40, 128), (10, 250, 10, 30)])
def test_rectangles_match(colour):
    a, b = pair()
    for p in (a, b):
        p.fill_rect(3.7, 2.2, 40.5, 20.9, colour)
        p.stroke_rect(10, 12, 30, 20, (240, 240, 240, 255))
    assert max_channel_error(a, b) <= 1


def test_clips_nest_and_cut_everything():
    a, b = pair()
    for p in (a, b):
        p.push_clip(10, 10, 30, 20)
        p.push_clip(0, 15, 64, 48)
        p.fill_rect(0, 0, 64, 48, (255, 0, 0, 255))
        p.fill_triangle((0, 0), (64, 0), (0, 48), (0, 255, 0, 200))
        p.pop_clip()
        p.pop_clip()
        p.fill_rect(50, 40, 10, 5, (0, 0, 255, 255))
    assert max_channel_error(a, b) <= 1


@pytest.mark.parametrize("tri", [
    ((5.0, 5.0), (60.0, 9.0), (20.0, 44.0)),
    # Not (2.5, 40.5), (2.5, 3.5): an edge through pixel centres is a tie, and the
    # reference's barycentric floats settle it differently on alternate rows. That
    # is noise in the reference, not a rule to match.
    ((2.6, 40.3), (2.6, 3.4), (61.25, 22.75)),
    ((10.0, 10.0), (11.2, 10.0), (30.0, 40.0)),     # a sliver: where fill rules show
])
@pytest.mark.parametrize("alpha", [255, 140])
def test_triangles_follow_the_pixel_centre_rule(tri, alpha):
    a, b = pair()
    for p in (a, b):
        p.fill_triangle(*tri, (250, 200, 30, alpha))
    assert max_channel_error(a, b) <= 1


def test_a_line_as_two_triangles_is_not_fatter():
    """Pillow's own polygon fill sets every pixel an edge touches; a thin
    quad came out a pixel wider (a checkmark visibly bolder) and the diagonal
    seam of a translucent quad double-blended."""
    a, b = pair()
    quad = [(8.0, 30.0), (40.0, 6.0), (41.5, 8.0), (9.5, 32.0)]
    for p in (a, b):
        p.fill_triangle(quad[0], quad[1], quad[2], (80, 160, 255, 160))
        p.fill_triangle(quad[0], quad[2], quad[3], (80, 160, 255, 160))
    assert max_channel_error(a, b) <= 1


def test_fill_convex_is_one_polygon():
    a, _ = pair()
    fill_convex(a, [(10, 10), (50, 12), (54, 40), (30, 46), (8, 30)], (255, 255, 255, 255))
    lit = sum(1 for c in rgb(a) if c == (255, 255, 255))
    assert 1000 < lit < 1500


def test_images_match_nearest_texel_and_tint():
    pixels = bytes(v for i in range(12) for v in (
        (i * 37) % 256, (i * 91) % 256, (i * 13) % 256, 255 if i % 3 else 120))
    tex = Texture(4, 3, pixels)
    a, b = pair()
    for p in (a, b):
        p.image(5, 4, 40, 30, tex)
        p.image(48, 30, 12, 12, tex, tint=(255, 128, 255, 255))
    assert max_channel_error(a, b) <= 2


def test_an_image_follows_its_texture_revision():
    tex = Texture(2, 2, bytes([255, 0, 0, 255] * 4))
    p = PilPainter(8, 8, background=BG)
    p.image(0, 0, 8, 8, tex)
    assert rgb(p)[0] == (255, 0, 0)
    tex.px[:] = bytes([0, 0, 255, 255] * 4)
    tex.touch()
    p = PilPainter(8, 8, background=BG)
    p.image(0, 0, 8, 8, tex)
    assert rgb(p)[0] == (0, 0, 255)


def ink(painter):
    lit = [i for i, c in enumerate(rgb(painter)) if c[0] > 120]
    w = painter.width
    if not lit:
        return 0, None
    xs = [i % w for i in lit]
    ys = [i // w for i in lit]
    return len(lit), (min(xs), min(ys), max(xs), max(ys))


@pytest.mark.parametrize("bold", [False, True])
def test_text_lands_where_the_reference_puts_it(bold):
    a, b = pair(220, 40)
    for p in (a, b):
        p.text(4, 4, 212, 32, ALIGN_CENTER, "Print 3 labels: QR 0-9", (255, 255, 255, 255), bold)
    na, box_a = ink(a)
    nb, box_b = ink(b)
    assert nb > 100
    assert abs(na - nb) <= 0.15 * nb
    assert all(abs(p - q) <= 1 for p, q in zip(box_a, box_b)), (box_a, box_b)


def test_text_is_clipped():
    p = PilPainter(120, 30, background=BG)
    p.push_clip(0, 0, 40, 30)
    p.text(0, 0, 120, 30, ALIGN_CENTER, "WWWWWWWWWWWWWWW", (255, 255, 255, 255))
    assert all(c == BG[:3] for i, c in enumerate(rgb(p)) if i % 120 >= 40)


def test_the_slow_operations_borrow_the_reference():
    a, b = pair()
    for p in (a, b):
        p.gradient_triangle((2, 2), (60, 10), (10, 44), (255, 0, 0, 255), (0, 255, 0, 255),
                            (0, 0, 255, 128))
        p.text_rotated(10, 10, 40, 16, ALIGN_CENTER, "rot", (255, 255, 255, 255), 90.0)
    assert max_channel_error(a, b) <= 1


def widgets():
    im.begin("w", (0, 0, 300, 160), im.WindowFlags.NO_TITLE_BAR)
    im.text("Label settings")
    im.button("Print 1 label")
    im.checkbox("invert", True)
    im.slider_int("density", 7, 1, 15)
    im.separator()
    im.text_disabled("put {uuid} into a text to use it")
    im.end()


def test_a_frame_of_widgets_matches_the_reference():
    frames = []
    for cls in (PilPainter, PixelPainter):
        io = im.IO()
        painter = None
        for _ in range(2):
            painter = cls(300, 160, background=BG)
            with im.frame(painter, (0, 0, 300, 160), io=io):
                widgets()
        frames.append(painter)
    a, b = frames
    differ = sum(1 for x, y in zip(rgb(a), rgb(b)) if max(abs(p - q) for p, q in zip(x, y)) > 32)
    # glyph edges only: whole-pixel placement against a resampled pen position
    assert differ < 0.03 * 300 * 160, differ


def test_a_window_frame_is_fast():
    import time

    painter = None
    io = im.IO()
    start = time.perf_counter()
    for _ in range(10):
        painter = PilPainter(300, 160, background=BG, frame=painter.frame if painter else None)
        with im.frame(painter, (0, 0, 300, 160), io=io):
            widgets()
    per_frame = (time.perf_counter() - start) / 10
    assert per_frame < 0.05, "%.1f ms per frame" % (per_frame * 1e3)


def test_a_reused_frame_is_repainted_not_reallocated():
    first = PilPainter(20, 10, background=(255, 0, 0, 255))
    again = PilPainter(20, 10, background=(0, 255, 0, 255), frame=first.frame)
    assert again.frame is first.frame
    assert rgb(again)[0] == (0, 255, 0)
    resized = PilPainter(30, 10, background=BG, frame=first.frame)
    assert resized.frame is not first.frame and resized.frame.size == (30, 10)
