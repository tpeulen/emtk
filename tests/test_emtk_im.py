"""emtk's porting kit: polyline/convex on any Painter, DrawList, the im Context, ImWidget.

What a Dear ImGui port needs and could not have: thick polylines and filled
convex shapes (one numpy pass on the quad painter, thin quads elsewhere),
``ImDrawList`` names over a Painter, an ``ImGuiIO`` snapshot, an ID stack,
per-widget storage, ``ButtonBehavior``, child regions, and a wrapper that
makes ``def widget(ctx, ...)`` a retained emtk control.
"""
from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")   # optional: emtk itself needs none

from emtk.drawlist import DRAW_FLAGS_CLOSED, DrawList
from emtk.im import ButtonFlags, Context, ImWidget
from emtk.painter import fill_circle, fill_convex, polyline
from emtk.quad_painter import FLOATS_PER_VERTEX, QuadPainter
from emtk.testing import RecordingPainter


def test_polyline_falls_back_to_thin_quads_on_a_plain_painter():
    p = RecordingPainter()
    polyline(p, [(0, 0), (10, 0), (10, 10)], 2.0, (255, 0, 0))
    assert len(p.triangles) == 4                       # two per segment
    polyline(p, [(0, 0), (10, 0), (10, 10)], 2.0, (255, 0, 0), closed=True)
    assert len(p.triangles) == 4 + 6                   # the closing segment too
    fill_convex(p, [(0, 0), (4, 0), (4, 4), (0, 4)], (0, 255, 0))
    assert len(p.triangles) == 12                      # a fan: n - 2
    fill_circle(p, 5, 5, 3, (0, 0, 255), segments=12)
    assert len(p.triangles) == 12 + 10


def test_the_quad_painter_polyline_matches_the_fallback_geometry():
    """Same triangles, one numpy pass: the fast path is a speed-up, not a different picture."""
    pts = [(1.0, 2.0), (11.0, 2.0), (11.0, 22.0), (-4.0, 30.0)]
    fast = QuadPainter(scale=1.0)
    fast.polyline(pts, 3.0, (10, 20, 30, 255))
    slow = RecordingPainter()
    from emtk.painter import line

    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        line(slow, x0, y0, x1, y1, 3.0, (10, 20, 30))
    got = fast.vertices()
    assert got.shape == (len(slow.triangles) * 3, FLOATS_PER_VERTEX)
    want = np.array([c for tri in slow.triangles for c in tri[:3]], dtype=np.float32)
    assert np.allclose(got[:, :2], want, atol=1e-4)
    # colour is 0..1 in the vertex stream
    assert np.allclose(got[0, 4:8], (10 / 255, 20 / 255, 30 / 255, 1.0), atol=1e-6)


def test_the_quad_painter_polyline_is_vectorised():
    """Ten thousand samples must not cost ten thousand Python calls."""
    import time

    xs = np.linspace(0, 1000, 10_000)
    pts = np.column_stack([xs, 50 + 40 * np.sin(xs / 30)])
    p = QuadPainter(scale=1.0)
    t0 = time.perf_counter()
    p.polyline(pts, 1.5, (255, 255, 255))
    dt = time.perf_counter() - t0
    assert p.vertex_count == (len(pts) - 1) * 6
    assert dt < 0.2, f"polyline of 10k points took {dt * 1000:.0f} ms"


def test_drawlist_speaks_imdrawlist():
    p = RecordingPainter()
    dl = DrawList(p)
    dl.add_rect_filled((0, 0), (10, 10), (1, 2, 3))
    assert p.fills[-1][:4] == (0, 0, 10, 10)
    dl.add_rect((0, 0), (10, 10), (1, 2, 3))
    assert p.strokes[-1][:4] == (0, 0, 10, 10)
    n = len(p.triangles)
    dl.add_rect_filled((0, 0), (20, 20), (1, 2, 3), rounding=4.0)     # a corner fan, not a rect
    assert len(p.triangles) > n
    n = len(p.triangles)
    dl.add_circle_filled((5, 5), 4, (9, 9, 9), num_segments=8)
    assert len(p.triangles) == n + 6
    n = len(p.triangles)
    dl.add_bezier_cubic((0, 0), (10, 0), (10, 10), (20, 10), (1, 1, 1), thickness=1.0, num_segments=8)
    assert len(p.triangles) == n + 16
    dl.path_line_to((0, 0))
    dl.path_arc_to((0, 0), 5, 0, math.pi / 2, num_segments=4)
    dl.path_stroke((1, 1, 1), flags=DRAW_FLAGS_CLOSED, thickness=1.0)
    dl.add_text((3, 4), (255, 255, 255), "hi")
    assert p.strings[-1] == "hi"
    assert dl.calc_text_size("abc") == (21.0, 16.0)
    dl.push_clip_rect((0, 0), (5, 5))
    assert p.clips[-1] == (0, 0, 5, 5)
    dl.pop_clip_rect()
    assert p.clips == []


# --------------------------------------------------------------------------- #
# A port, the way the shim is meant to be used
# --------------------------------------------------------------------------- #
def im_button(ctx: Context, label: str, size=(60.0, 20.0)) -> bool:
    """A transliterated ImGui ``Button``: ItemSize + ButtonBehavior + draw."""
    item_id = ctx.get_id(label)
    box = ctx.item_size(*size)
    hovered, held, pressed = ctx.button_behavior(box, item_id)
    col = (90, 90, 90) if held else (70, 70, 70) if hovered else (50, 50, 50)
    ctx.draw.add_rect_filled((box[0], box[1]), (box[0] + box[2], box[1] + box[3]), col,
                             rounding=ctx.style.frame_rounding)
    ctx.draw.add_text((box[0] + 4, box[1] + 2), (255, 255, 255), label.split("##")[0])
    if hovered:
        ctx.set_tooltip(f"press {label}")
    return pressed


def test_button_behavior_presses_on_release_inside():
    p = RecordingPainter()
    clicks: list[bool] = []
    widget = ImWidget(im_button, "OK##ok", on_result=lambda r: clicks.append(r) if r else None)
    widget.draw(p, 10, 10, 200, 100)
    assert p.strings[-1] == "OK"
    box = (10, 10, 60, 20)                                  # the first row of the layout
    assert widget.press(20, 15, *box) is False              # down: held, not pressed
    assert widget.io.mouse_down[0]
    assert widget.release(22, 16, *box) is True             # up inside: pressed
    assert clicks == [True]
    assert widget.press(20, 15, *box) is False
    assert widget.release(300, 300, *box) is False          # up outside: not a press
    assert clicks == [True]
    assert widget.tooltip is None or widget.tooltip.startswith("press")


def test_ids_layout_storage_and_child_regions():
    p = RecordingPainter()
    seen = {}

    def widget(ctx: Context):
        ctx.push_id("row")
        a = ctx.get_id("Same##x")
        ctx.pop_id()
        b = ctx.get_id("Same##x")
        seen["ids_differ"] = a != b and a[-1] == "x"
        store = ctx.get_storage("count")
        store["n"] = store.get("n", 0) + 1
        seen["n"] = store["n"]
        r1 = ctx.item_size(50, 10)
        ctx.layout.same_line()
        r2 = ctx.item_size(50, 10)
        seen["same_line"] = r2[1] == r1[1] and r2[0] > r1[0]
        child = ctx.begin_child((0, 40, 100, 30))
        inner = ctx.item_size(20, 10)
        ctx.end_child()
        seen["child"] = (inner[0], inner[1]) == (0, 40) and ctx.layout is not child
        after = ctx.item_size(20, 10)
        seen["parent_resumes"] = after[1] > r1[1]
        return None

    w = ImWidget(widget)
    w.draw(p, 0, 0, 200, 200)
    w.draw(p, 0, 0, 200, 200)
    assert seen["ids_differ"] and seen["same_line"] and seen["child"] and seen["parent_resumes"]
    assert seen["n"] == 2, "per-id storage must persist across frames"
    assert p.clips == [] and any(c[0] == "push_clip" for c in p.calls)


def test_button_flags_pressed_on_click():
    p = RecordingPainter()

    def widget(ctx: Context):
        box = ctx.item_size(30, 10)
        _h, _held, pressed = ctx.button_behavior(box, ctx.get_id("b"), ButtonFlags.PRESSED_ON_CLICK)
        return pressed

    w = ImWidget(widget)
    w.draw(p, 0, 0, 100, 100)
    assert w.press(5, 5, 0, 0, 100, 100) is True


@pytest.mark.parametrize("enter", [13, 0x01000004, 0x01000005])
def test_enter_returns_true_accepts_every_spelling_of_enter(enter):
    """``ENTER_RETURNS_TRUE`` must fire for Qt's Return and Enter codes as well
    as for a plain carriage return: a host that forwards Qt key codes is the
    common case, and under it a field could be typed into but never committed."""
    import emtk
    from emtk.flags import InputTextFlags

    io, storage = emtk.IO(), {}
    seen = {}

    def frame():
        with emtk.frame(RecordingPainter(), (0, 0, 300, 80), io=io, storage=storage) as ctx:
            emtk.begin("w", (0, 0, 300, 80))
            seen["changed"], seen["value"] = emtk.input_text(
                "##f", "0.5", "", InputTextFlags.ENTER_RETURNS_TRUE)
            seen["box"] = ctx.get_item_rect()
            emtk.end()

    frame()
    x, y, w, h = seen["box"]
    io.mouse_pos = io.mouse_clicked_pos[0] = (x + 4, y + 4)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    frame()
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    frame()
    io.key = enter
    frame()
    assert seen["changed"] is True
