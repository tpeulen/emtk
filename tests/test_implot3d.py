"""``emtk.implot3d`` -- ImPlot3D ported onto emtk.

What is asserted, and against what:

* the quaternion and projection arithmetic against values worked by hand
  (a 90-degree turn, the elevation/azimuth composition, the NDC box and the
  view scale of ``PlotRect / 1.8``), and the round trip pixel -> plane -> pixel;
* the bundled meshes against the counts in ``implot3d.h`` and against their
  own topology (the sphere is closed and consistently wound; the reference's
  duck has an open seam and its cube mixes windings -- asserted as they are,
  so a regeneration that changes them is noticed);
* depth: triangles reach the painter far to near;
* each item kind reaches the painter as the primitives it should;
* input driven through ``emtk.IO``: a right drag turns the box by exactly the
  reference's ``quat_x * rotation * quat_z``, the wheel zooms the limits, a
  left drag pans, a double right click animates back to the initial rotation,
  a right click opens the plot's context menu.
"""
from __future__ import annotations

import math
from collections import Counter

import pytest

import emtk
from emtk import implot3d as p3
from emtk import implot3d_meshes as meshes
from emtk import painter as painter_mod
from emtk.testing import PixelPainter, RecordingPainter


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class Host:
    """One emtk host: the IO and storage a real one keeps across frames."""

    def __init__(self, size=(420.0, 420.0)) -> None:
        self.io = emtk.IO()
        self.io.wall_clock = False
        self.storage: dict = {}
        self.size = size
        self.seen: dict = {}

    def frame(self, gui, painter=None):
        painter = painter if painter is not None else RecordingPainter()
        with emtk.frame(painter, (0.0, 0.0, *self.size), io=self.io, storage=self.storage):
            emtk.begin("w")
            gui(self.seen)
            emtk.end()
        return painter


def _box_plot(seen, flags=p3.FLAGS_NO_TITLE | p3.FLAGS_NO_LEGEND | p3.FLAGS_NO_MOUSE_TEXT,
              rotation=None, items=None):
    if p3.begin_plot("##t", (400, 400), flags):
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        if rotation is not None:
            p3.setup_box_rotation(rotation, False, p3.COND_ALWAYS)
        if items:
            items()
        plot = p3.get_current_plot()
        p3.setup_lock()
        seen["rect"] = plot.plot_rect
        seen["rotation"] = p3.Quat(*plot.rotation)
        seen["ranges"] = [(a.range.min, a.range.max) for a in plot.axes]
        seen["plot"] = plot
        p3.end_plot()


def _approx(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# --------------------------------------------------------------------------- #
# quaternions
# --------------------------------------------------------------------------- #
def test_a_quarter_turn_about_z_takes_x_to_y():
    q = p3.Quat.from_angle_axis(math.pi / 2, (0.0, 0.0, 1.0))
    assert _approx(q * p3.Point(1, 0, 0), (0.0, 1.0, 0.0))
    assert _approx((q.x, q.y, q.z, q.w), (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)))


def test_elevation_azimuth_zero_is_minus_ninety_about_x():
    """``FromElAz(0, 0) = el * zero * az`` with ``zero`` a -90 degree turn about
    X: the plot's +z (up) lands on the screen's +y."""
    q = p3.Quat.from_el_az(0.0, 0.0)
    assert _approx(q * (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    assert _approx(q * (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))


def test_the_matrix_is_the_same_linear_map_as_the_product():
    q = p3.Quat(-0.513269, -0.212596, -0.318184, 0.76819)      # not exactly unit
    m = q.matrix()
    for v in ((1, 2, 3), (-0.5, 4.0, 0.25), (0, 0, 1)):
        by_matrix = [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]
        assert _approx(q * v, by_matrix, 1e-12)


def test_slerp_ends_and_two_vectors_and_inverse():
    a = p3.Quat()
    b = p3.Quat.from_angle_axis(1.2, (0.0, 1.0, 0.0))
    assert _approx(tuple(p3.Quat.slerp(a, b, 0.0)), tuple(a))
    assert _approx(tuple(p3.Quat.slerp(a, b, 1.0)), tuple(b), 1e-12)
    half = p3.Quat.slerp(a, b, 0.5)
    assert _approx(tuple(half), tuple(p3.Quat.from_angle_axis(0.6, (0.0, 1.0, 0.0))), 1e-12)
    q = p3.Quat.from_two_vectors((1.0, 0.0, 0.0), (0.0, 0.0, 2.0))
    assert _approx(q * (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    assert _approx((q * q.inverse()).__iter__(), (0.0, 0.0, 0.0, 1.0), 1e-12)


def test_the_liang_barsky_clip():
    box = p3.Box((0, 0, 0), (1, 1, 1))
    visible, a, b = box.clip_line_segment((-1.0, 0.5, 0.5), (2.0, 0.5, 0.5))
    assert visible and _approx(a, (0.0, 0.5, 0.5)) and _approx(b, (1.0, 0.5, 0.5))
    assert not box.clip_line_segment((2.0, 2.0, 2.0), (3.0, 2.0, 2.0))[0]


# --------------------------------------------------------------------------- #
# projection
# --------------------------------------------------------------------------- #
def test_plot_to_pixels_by_hand_with_no_rotation():
    """Identity rotation: NDC x is screen x, NDC y is screen *up*. The view
    scale is ``min(w, h) / 1.8`` and the box spans NDC -0.5..0.5."""
    host = Host()
    got = {}

    def items():
        got["px"] = p3.plot_to_pixels(1.0, 0.0, 0.0)
        got["py"] = p3.plot_to_pixels(0.0, 1.0, 0.0)
        got["pz"] = p3.plot_to_pixels(0.0, 0.0, 1.0)
        got["ndc"] = p3.plot_to_ndc((0.5, -1.0, 1.0))

    def gui(seen):
        _box_plot(seen, rotation=p3.Quat(), items=items)

    host.frame(gui)
    x0, y0, x1, y1 = host.seen["rect"]
    scale = min(x1 - x0, y1 - y0) / 1.8
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    assert _approx(got["px"], (cx + 0.5 * scale, cy))
    assert _approx(got["py"], (cx, cy - 0.5 * scale))
    assert _approx(got["pz"], (cx, cy))                  # along the view axis
    assert _approx(got["ndc"], (0.25, -0.5, 0.5))


def test_an_inverted_axis_flips_ndc_and_depth():
    host = Host()
    got = {}

    def gui(seen):
        if p3.begin_plot("##inv", (400, 400)):
            p3.setup_axis(p3.AXIS_X, "x", p3.AXIS_FLAGS_INVERT)
            p3.setup_axes_limits(0, 10, 0, 1, 0, 1)
            got["ndc"] = p3.plot_to_ndc((10.0, 0.0, 0.0))
            got["back"] = p3.ndc_to_plot(got["ndc"])
            p3.end_plot()

    host.frame(gui)
    assert _approx(got["ndc"], (-0.5, -0.5, -0.5))
    assert _approx(got["back"], (10.0, 0.0, 0.0))


def test_pixels_to_plane_is_the_inverse_of_plot_to_pixels():
    host = Host()
    got = {}

    def gui(seen):
        if p3.begin_plot("##rt", (400, 400)):
            p3.setup_axes_limits(-2, 2, 0, 10, -1, 1)
            plot = p3.get_current_plot()
            active, _p2d = p3.compute_active_faces(plot.rotation, plot.axes)
            z = 1.0 if active[p3.PLANE_XY] else -1.0      # the drawn XY face
            point = (0.7, 3.0, z)
            pix = p3.plot_to_pixels(point)
            got["point"] = point
            got["back"] = p3.pixels_to_plot_plane(pix, p3.PLANE_XY)
            ray = p3.pixels_to_plot_ray(pix)
            got["ray"] = ray
            p3.end_plot()

    host.frame(gui)
    # 1e-5, not tighter: the reference's initial rotation is not exactly unit,
    # and ``q.Inverse() * (q * v)`` of a non-unit q is v only to that order.
    assert _approx(got["back"], got["point"], 1e-5)
    # the ray passes through the point: origin + t * direction
    o, d = got["ray"].origin, got["ray"].direction
    t = (got["point"][0] - o.x) / d.x
    assert _approx((o.x + t * d.x, o.y + t * d.y, o.z + t * d.z), got["point"], 1e-5)


def test_a_missed_plane_is_nan():
    host = Host()
    got = {}

    def gui(seen):
        if p3.begin_plot("##nan", (400, 400)):
            got["p"] = p3.pixels_to_plot_plane((0.0, 0.0), p3.PLANE_XY, True)
            p3.end_plot()

    host.frame(gui)
    assert got["p"].is_nan()


def test_the_default_locator_ticks_nice_numbers():
    ticker = p3.Ticker()
    p3.locator_default(ticker, p3.Range(0.0, 1.0), 222.0, p3.formatter_default, "%g")
    majors = [t.plot_pos for t in ticker.ticks if t.major]
    assert majors == pytest.approx([0.0, 0.5, 1.0])
    assert [t.text for t in ticker.ticks if t.major] == ["0", "0.5", "1"]


def test_log_ticks_land_on_decades():
    ticker = p3.Ticker()
    p3.locator_log10(ticker, p3.Range(0.1, 100.0), 222.0, p3.formatter_default, "%g")
    assert [t.plot_pos for t in ticker.ticks if t.major] == pytest.approx([0.1, 1, 10, 100])


# --------------------------------------------------------------------------- #
# meshes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, vtx, idx", [("CUBE", 8, 36), ("SPHERE", 162, 960),
                                            ("DUCK", 254, 1428)])
def test_mesh_counts_match_the_header(name, vtx, idx):
    assert getattr(meshes, name + "_VTX_COUNT") == len(getattr(meshes, name + "_VTX")) == vtx
    assert getattr(meshes, name + "_IDX_COUNT") == len(getattr(meshes, name + "_IDX")) == idx
    assert max(getattr(meshes, name + "_IDX")) < vtx
    assert meshes.CUBE_VTX[0] == (-1.0, -1.0, -1.0) and meshes.CUBE_IDX[:6] == (0, 1, 2, 0, 2, 3)
    assert meshes.SPHERE_VTX[0] == (-0.525731, 0.850651, 0.0)


def _edges(idx):
    directed = Counter()
    for i in range(0, len(idx), 3):
        a, b, c = idx[i:i + 3]
        directed.update([(a, b), (b, c), (c, a)])
    undirected = Counter()
    for (a, b), n in directed.items():
        undirected[frozenset((a, b))] += n
    return directed, undirected


def test_the_sphere_is_closed_wound_outward():
    directed, undirected = _edges(meshes.SPHERE_IDX)
    assert set(undirected.values()) == {2}
    assert all((b, a) in directed for a, b in directed)
    vtx = meshes.SPHERE_VTX
    for i in range(0, len(meshes.SPHERE_IDX), 3):
        a, b, c = (vtx[k] for k in meshes.SPHERE_IDX[i:i + 3])
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        centroid = [(a[k] + b[k] + c[k]) / 3 for k in range(3)]
        assert sum(n[k] * centroid[k] for k in range(3)) > 0.0


def test_the_cube_and_duck_topology_is_the_references():
    _d, cube = _edges(meshes.CUBE_IDX)
    assert set(cube.values()) == {2}                     # closed
    _d, duck = _edges(meshes.DUCK_IDX)
    assert Counter(duck.values()) == Counter({2: 702, 1: 24})   # the duck's open seam


# --------------------------------------------------------------------------- #
# depth ordering
# --------------------------------------------------------------------------- #
def test_triangles_reach_the_painter_far_to_near():
    """Two quads at z = -0.5 and z = +0.5, viewed from +z: the far one first,
    whatever order they were plotted in."""
    host = Host()
    near, far = (255, 0, 0, 255), (0, 0, 255, 255)

    def items():
        sq = ([-0.5, 0.5, 0.5, -0.5], [-0.5, -0.5, 0.5, 0.5])
        p3.plot_quad("near", sq[0], sq[1], [0.5] * 4, spec=p3.Spec(fill_color=near, line_weight=0))
        p3.plot_quad("far", sq[0], sq[1], [-0.5] * 4, spec=p3.Spec(fill_color=far, line_weight=0))

    painter = host.frame(lambda seen: _box_plot(seen, rotation=p3.Quat(), items=items))
    colours = [tuple(c[-1]) for c in painter.calls if c[0] == "fill_triangle"
               and tuple(c[-1]) in (near, far)]
    assert colours == [far, far, near, near]


def test_draw_list_sort_is_stable_for_equal_depth():
    dl = p3.DrawList3D()
    for k in range(5):
        c = p3.IM_COL32(k, 0, 0, 255)
        dl.add((0, 0), (10, 0), (0, 10), c, c, c, 0.0)
    rp = RecordingPainter()
    dl.sorted_move_to_draw_list(rp)
    assert [t[-1][0] for t in rp.triangles] == [0, 1, 2, 3, 4]
    assert dl.tris == [] and dl.z == []


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
def _draw_item(fn, **host_kw):
    host = Host(**host_kw)
    painter = host.frame(lambda seen: _box_plot(seen, items=fn))
    host.frame(lambda seen: _box_plot(seen, items=fn), painter := RecordingPainter())
    return painter, host


def test_scatter_draws_a_fan_per_point():
    painter, _h = _draw_item(lambda: p3.plot_scatter("s", [0.0, 0.5], [0.0, 0.5], [0.0, 0.5],
                                                     spec=p3.Spec(line_weight=0)))
    item = p3.IM_COL32(*p3.u32_to_rgba(p3.COLORMAPS[0][2][0]))
    fans = [c for c in painter.calls if c[0] == "fill_triangle"
            and tuple(c[-1]) == p3.u32_to_rgba(item)]
    assert len(fans) == 2 * 8                           # circle: 10 corners, 8 triangles


def test_line_segments_and_loop():
    painter, _h = _draw_item(lambda: p3.plot_line("l", [0, 0.5, 0.5], [0, 0, 0.5], [0, 0, 0],
                                                  spec=p3.Spec(flags=p3.LINE_FLAGS_LOOP)))
    assert len(painter.triangles) >= 3 * 2


def test_triangle_quad_mesh_surface_image_and_text_reach_the_painter():
    tex = emtk.texture.Texture(2, 2, bytes([255, 0, 0, 255] * 4)) if hasattr(emtk, "texture") else None
    from emtk.texture import Texture
    tex = Texture(2, 2, bytes([255, 0, 0, 255] * 4))
    n = 4
    grid = [(i / 3, j / 3) for j in range(n) for i in range(n)]

    def items():
        p3.plot_triangle("t", [0, 1, 0], [0, 0, 1], [0, 0, 0],
                         spec=p3.Spec(fill_colors=[p3.IM_COL32(255, 0, 0), p3.IM_COL32(0, 255, 0),
                                                   p3.IM_COL32(0, 0, 255)]))
        p3.plot_mesh("m", meshes.CUBE_VTX, meshes.CUBE_IDX, spec=p3.Spec(line_color=(1.0, 1.0, 1.0, 1.0)))
        p3.plot_surface("s", [g[0] for g in grid], [g[1] for g in grid],
                        [g[0] * g[1] for g in grid], n, n)
        p3.plot_image("img", tex, (0, 0, 0), (0.5, 0, 0), (0, 0.5, 0))
        p3.plot_text("hello", 0.0, 0.0, 0.0)

    painter, _h = _draw_item(items)
    assert painter.gradient_triangles, "the colormapped surface is Gouraud-shaded"
    assert len(painter.image_triangles) == 2
    assert "hello" in painter.strings


def test_a_hidden_item_draws_nothing_and_the_legend_lists_by_display_name():
    host = Host()

    def items():
        p3.plot_line("a##id", [0, 1], [0, 1], [0, 1])
        p3.plot_line("##hidden", [0, 1], [1, 0], [0, 1])

    host.frame(lambda seen: _box_plot(seen, flags=0, items=items))
    painter = host.frame(lambda seen: _box_plot(seen, flags=0, items=items))
    plot = host.seen["plot"]
    assert [plot.items.get_legend_label(i) for i in range(plot.items.get_legend_count())] == ["a##id"]
    assert "a" in painter.strings and "hidden" not in painter.strings


def test_a_minimal_painter_draws_a_surface_through_the_fallbacks():
    """No gradient_triangle, no image_triangle, no text_rotated: still drawn."""
    class Minimal:
        def __init__(self):
            self.tris = 0

        def fill_rect(self, *a): pass
        def stroke_rect(self, *a, **k): pass
        def gradient_rect(self, *a, **k): pass
        def text(self, *a, **k): pass
        def push_clip(self, *a): pass
        def pop_clip(self): pass
        def fill_triangle(self, *a): self.tris += 1
        def text_width(self, s): return 7.0 * len(s)
        def line_height(self): return 16.0

    host = Host()
    grid = [(i / 4, j / 4) for j in range(5) for i in range(5)]
    items = lambda: p3.plot_surface("s", [g[0] for g in grid], [g[1] for g in grid],  # noqa: E731
                                    [g[0] ** 2 for g in grid], 5, 5)
    host.frame(lambda seen: _box_plot(seen, items=items), Minimal())
    painter = host.frame(lambda seen: _box_plot(seen, items=items), Minimal())
    assert painter.tris > 32 * 2


# --------------------------------------------------------------------------- #
# interaction
# --------------------------------------------------------------------------- #
def _outside_the_box(rect):
    """A point in the plot rect that is on no face and no axis: a corner."""
    return (rect[0] + 3.0, rect[1] + 3.0)


def test_a_right_drag_turns_the_box_by_the_references_quaternions():
    host = Host()
    gui = lambda seen: _box_plot(seen)  # noqa: E731
    host.frame(gui)
    host.frame(gui)
    start = _outside_the_box(host.seen["rect"])
    before = p3.Quat(*host.seen["plot"].rotation)
    io = host.io
    io.mouse_pos = start
    host.frame(gui)                                     # the pointer arrives
    io.mouse_down[1] = io.mouse_clicked[1] = True
    io.mouse_clicked_pos[1] = start
    host.frame(gui)                                     # press: held, no move yet
    io.mouse_pos = (start[0] + 30.0, start[1] + 12.0)
    host.frame(gui)                                     # drag
    after = host.seen["plot"].rotation
    axis = (0.0, 0.0, -1.0) if (before * (0.0, 0.0, 1.0)).z < 0.0 else (0.0, 0.0, 1.0)
    expected = (p3.Quat.from_angle_axis(12.0 * 3.1415 / 180.0, (1.0, 0.0, 0.0)) * before
                * p3.Quat.from_angle_axis(30.0 * 3.1415 / 180.0, axis)).normalize()
    assert _approx(tuple(after), tuple(expected), 1e-12)


def test_the_wheel_zooms_every_axis_about_the_centre():
    host = Host()
    gui = lambda seen: _box_plot(seen)  # noqa: E731
    host.frame(gui)
    host.io.mouse_pos = _outside_the_box(host.seen["rect"])
    host.frame(gui)
    host.io.mouse_wheel = 1.0
    host.frame(gui)
    plot = host.seen["plot"]
    for axis in plot.axes:
        assert (axis.range.min, axis.range.max) == pytest.approx((-0.9, 0.9))


def test_a_left_drag_outside_the_box_pans_in_the_view_plane():
    host = Host()
    gui = lambda seen: _box_plot(seen, rotation=p3.Quat())  # noqa: E731
    host.frame(gui)
    start = _outside_the_box(host.seen["rect"])
    io = host.io
    io.mouse_pos = start
    host.frame(gui)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = start
    host.frame(gui)
    io.mouse_pos = (start[0] + 20.0, start[1])
    host.frame(gui)
    x0, y0, x1, y1 = host.seen["rect"]
    scale = min(x1 - x0, y1 - y0) / 1.8
    shift = 20.0 / scale * 2.0                          # NDC -> units of a span of 2
    xr = host.seen["plot"].axes[0].range
    assert (xr.min, xr.max) == pytest.approx((-1.0 - shift, 1.0 - shift))


def test_a_double_right_click_outside_animates_back_to_the_initial_rotation():
    host = Host()
    gui = lambda seen: _box_plot(seen, rotation=p3.Quat())  # noqa: E731
    host.frame(gui)
    plain = lambda seen: _box_plot(seen)  # noqa: E731
    io = host.io
    io.mouse_pos = _outside_the_box(host.seen["rect"])
    host.frame(plain)
    io.mouse_down[1] = io.mouse_clicked[1] = io.mouse_double_clicked[1] = True
    io.mouse_clicked_pos[1] = io.mouse_pos
    host.frame(plain)
    plot = host.seen["plot"]
    assert plot.animation_time > 0.0
    io.mouse_down[1] = False
    io.delta_time = 10.0                                # one long frame finishes it
    host.frame(plain)
    assert _approx(tuple(plot.rotation), p3.DEFAULT_INITIAL_ROTATION, 1e-6)


def test_a_right_click_opens_the_plot_context_menu():
    host = Host()
    gui = lambda seen: _box_plot(seen)  # noqa: E731
    host.frame(gui)
    io = host.io
    io.mouse_pos = _outside_the_box(host.seen["rect"])
    host.frame(gui)
    io.mouse_down[1] = io.mouse_clicked[1] = True
    io.mouse_clicked_pos[1] = io.mouse_pos
    host.frame(gui)
    io.mouse_down[1] = False
    io.mouse_released[1] = True
    io.delta_time = 0.5                                 # past the double-click window
    host.frame(gui)
    plot = host.seen["plot"]
    assert host.storage["__popups__"].get(p3._popup_name(plot, "##PlotContext"))
    painter = host.frame(gui)
    assert "Box" in painter.strings and "Settings" in painter.strings


def test_clicking_a_legend_entry_hides_the_item():
    host = Host()
    items = lambda: p3.plot_line("curve", [0, 1], [0, 1], [0, 1])  # noqa: E731
    gui = lambda seen: _box_plot(seen, flags=0, items=items)  # noqa: E731
    host.frame(gui)
    host.frame(gui)
    legend = host.seen["plot"].items.legend
    x0, y0, x1, y1 = legend.rect
    io = host.io
    io.mouse_pos = (x0 + 8.0, y0 + 10.0)
    host.frame(gui)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    host.frame(gui)
    assert host.seen["plot"].items.order[0].show is False


# --------------------------------------------------------------------------- #
# the painter operations ImPlot3D added
# --------------------------------------------------------------------------- #
def test_gradient_triangle_interpolates_on_the_pixel_painter():
    p = PixelPainter(40, 40)
    p.gradient_triangle((0, 0), (40, 0), (0, 40), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
    o = (5 * 40 + 20) * 4                                # (20.5, 5.5): mostly red + green
    r, g, b = p.px[o], p.px[o + 1], p.px[o + 2]
    w1, w2 = 20.5 / 40, 5.5 / 40
    assert (r, g, b) == pytest.approx((255 * (1 - w1 - w2), 255 * w1, 255 * w2), abs=2)


def test_the_subdivision_fallback_is_close_to_the_exact_gradient():
    exact = PixelPainter(60, 60)
    exact.gradient_triangle((0, 0), (60, 0), (0, 60), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
    approx = PixelPainter(60, 60)
    painter_mod.subdivide_gradient(approx.fill_triangle, (0, 0), (60, 0), (0, 60),
                                   (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
    worst = max(abs(exact.px[i] - approx.px[i]) for i in range(0, len(exact.px), 4))
    assert worst <= 24


def test_quad_painter_carries_three_colours_and_uvs():
    np = pytest.importorskip("numpy")
    from emtk.quad_painter import QuadPainter

    q = QuadPainter()
    q.gradient_triangle((0, 0), (10, 0), (0, 10), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 128))
    v = q.vertices()
    assert np.allclose(v[:, 4:8], [[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 128 / 255]])
    q = QuadPainter()
    q.image_uv_resolver = lambda handle: ((10.0, 20.0), (30.0, 60.0))
    q.image_triangle((0, 0), (1, 0), (1, 1), "h", (0, 0), (1, 0), (1, 1))
    assert np.allclose(q.vertices()[:, 2:4], [[10, 20], [30, 20], [30, 60]])
    q = QuadPainter()
    q.text_rotated(0, 0, 40, 16, 0, "ab", (255, 255, 255, 255), 90.0)
    assert q.vertex_count == 12


def test_rotated_text_on_the_pixel_painter_is_turned():
    """A wide string turned 90 degrees covers a tall box."""
    p = PixelPainter(120, 120)
    p.text_rotated(20, 52, 80, 16, painter_mod.ALIGN_CENTER, "MMMMMMMMMM", (255, 255, 255, 255), 90.0)
    lit = [(i // 4) % 120 for i in range(0, len(p.px), 4) if p.px[i] > 0]
    ys = [(i // 4) // 120 for i in range(0, len(p.px), 4) if p.px[i] > 0]
    assert max(ys) - min(ys) > max(lit) - min(lit)


def test_qt_painter_matches_the_pixel_painter_on_the_new_operations(qt_app):
    qtgui = pytest.importorskip("qtpy.QtGui", exc_type=ImportError)
    from qtpy import QtCore

    from emtk.qt_painter import QtPainter
    from emtk.texture import Texture

    image = qtgui.QImage(60, 60, qtgui.QImage.Format_ARGB32)
    image.fill(QtCore.Qt.black)
    qp = qtgui.QPainter(image)
    tex = Texture(2, 1, bytes([255, 0, 0, 255, 0, 255, 0, 255]))
    try:
        p = QtPainter(qp)
        p.gradient_triangle((0, 0), (60, 0), (0, 60), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
        p.image_triangle((30, 30), (60, 30), (60, 60), tex, (0, 0), (1, 0), (1, 1))
    finally:
        qp.end()
    ref = PixelPainter(60, 60)
    ref.gradient_triangle((0, 0), (60, 0), (0, 60), (255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
    ref.image_triangle((30, 30), (60, 30), (60, 60), tex, (0, 0), (1, 0), (1, 1))
    for x, y in ((10, 10), (25, 5), (5, 25), (55, 35), (40, 35)):
        c = image.pixelColor(x, y)
        o = (y * 60 + x) * 4
        assert (c.red(), c.green(), c.blue()) == pytest.approx(tuple(ref.px[o:o + 3]), abs=24), (x, y)


# --------------------------------------------------------------------------- #
# the demo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("section", [s[1] for s in __import__(
    "emtk.implot3d_demo", fromlist=["SECTIONS"]).SECTIONS])
def test_every_demo_section_draws(section):
    from emtk import implot3d_demo as demo

    fn = {title: f for _tab, title, f in demo.SECTIONS}[section]
    host = Host(size=(520.0, 900.0))
    host.frame(lambda seen: fn())
    painter = host.frame(lambda seen: fn())
    assert painter.calls


def test_the_demo_window_and_tools_draw():
    host = Host(size=(700.0, 900.0))

    def gui(seen):
        p3.show_all_demos()
        p3.show_metrics_window()
        p3.show_style_editor()
        p3.show_about_window()

    host.frame(gui)
    assert host.frame(gui).calls


def test_the_cpp_spellings_are_bound():
    assert p3.ImPlot3DFlags_NoTitle == p3.FLAGS_NO_TITLE == 1
    assert p3.ImPlot3DLineFlags_SkipNaN == p3.LINE_FLAGS_SKIP_NAN == 1 << 12
    assert p3.BeginPlot is p3.begin_plot and p3.PixelsToPlotPlane is p3.pixels_to_plot_plane
    assert p3.ImAxis3D_Z == p3.AXIS_Z == 2 and p3.ImPlane3D_XY == p3.PLANE_XY == 2


def test_the_folded_affine_projection_equals_the_general_one():
    host = Host()
    got = {}

    def items():
        plot = p3.get_current_plot()
        proj = p3._Projector(plot)
        assert proj.linear is not None
        pts = [(0.3, -0.7, 0.9), (-1.0, 1.0, -1.0), (2.0, 0.1, 0.4)]
        got["fast"] = [proj.to_pixels(*pt) for pt in pts]
        proj.linear = None
        got["slow"] = [proj.to_pixels(*pt) for pt in pts]

    host.frame(lambda seen: _box_plot(seen, items=items))
    for a, b in zip(got["fast"], got["slow"]):
        assert _approx(a, b, 1e-9)


def test_a_double_right_click_on_a_plane_snaps_the_view_to_it():
    """Over the XY face the animation ends looking straight down z: the
    face's normal on the view axis, one box axis pointing up."""
    host = Host()
    gui = lambda seen: _box_plot(seen)  # noqa: E731
    host.frame(gui)
    plot = host.seen["plot"]
    active, corners_pix, _c, _p2d, _ac = p3.get_axes_parameters(plot)
    face = p3.FACES[p3.PLANE_XY + 3 * int(active[p3.PLANE_XY])]
    cx = sum(corners_pix[i][0] for i in face) / 4
    cy = sum(corners_pix[i][1] for i in face) / 4
    io = host.io
    io.mouse_pos = (cx, cy)
    host.frame(gui)
    io.mouse_down[1] = io.mouse_clicked[1] = io.mouse_double_clicked[1] = True
    io.mouse_clicked_pos[1] = io.mouse_pos
    host.frame(gui)
    end = plot.rotation_animation_end
    view_z = end * (0.0, 0.0, 1.0)
    assert abs(abs(view_z.z) - 1.0) < 1e-9
    ups = [end * v for v in ((1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0))]
    assert max(u.y for u in ups) == pytest.approx(1.0)
