"""``emtk.implot3d_demo`` -- ``implot3d_demo.cpp``, section for section.

Every ``Demo*`` function of the reference is here under its snake-case name,
with the same data, the same controls and the same plots; ``show_all_demos``
lays them out in the same tabs and headers. Two things could not be carried
over literally:

* **Image Plots** shows ImGui's font atlas texture, which emtk does not have
  as a texture; a generated checkerboard :class:`~emtk.texture.Texture`
  stands in for it.
* C++ ``static`` locals are kept per host in the im storage
  (:func:`emtk.implot3d._demo_state`), so a demo's sliders keep their values
  across frames the way the reference's do.

Run headlessly, :data:`SECTIONS` is what a gallery walks: ``(tab, title,
function)`` for every demo.
"""
from __future__ import annotations

import colorsys
import math
import random

from . import im
from . import implot3d as p3
from .implot3d import Point, Spec

__all__ = ["show_demo_window", "show_all_demos", "show_style_editor", "show_about_window",
           "SECTIONS"]


# --------------------------------------------------------------------------- #
# [SECTION] Helpers
# --------------------------------------------------------------------------- #
def _state(key: str, **defaults) -> dict:
    return p3._demo_state("demo." + key, **defaults)


def checkbox_flag(flags: int, name: str) -> int:
    """``CHECKBOX_FLAG(flags, flag)``: the flag's own name as the label."""
    _c, flags = im.checkbox_flags(name, flags, getattr(p3, name))
    return flags


def help_marker(desc: str) -> None:
    im.text_disabled("(?)")
    if im.is_item_hovered():
        im.set_tooltip(desc)


def _hsv(h: float, s: float, v: float) -> int:
    """``ImColor::HSV``, packed."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return p3.color_convert_float4_to_u32((r, g, b, 1.0))


class ScrollingBuffer:
    """The demo's ring buffer for the realtime plot."""

    def __init__(self, max_size: int = 2000) -> None:
        self.max_size = max_size
        self.offset = 0
        self.data: list[float] = []

    def add_point(self, x: float) -> None:
        if len(self.data) < self.max_size:
            self.data.append(x)
        else:
            self.data[self.offset] = x
            self.offset = (self.offset + 1) % self.max_size

    def erase(self) -> None:
        self.data = []
        self.offset = 0


def metric_formatter(value: float, unit) -> str:
    """The demo's ``MetricFormatter``: SI prefixes on tick labels."""
    v = (1e9, 1e6, 1e3, 1, 1e-3, 1e-6, 1e-9)
    p = ("G", "M", "k", "", "m", "u", "n")
    if value == 0:
        return "0 %s" % unit
    for i in range(7):
        if abs(value) >= v[i]:
            return "%g %s%s" % (value / v[i], p[i], unit)
    return "%g %s%s" % (value / v[6], p[6], unit)


def _srand_rand(seed: int = 0):
    """``srand(seed); rand() / RAND_MAX`` -- a seeded sequence, not glibc's."""
    rng = random.Random(seed)
    return rng.random


# --------------------------------------------------------------------------- #
# [SECTION] Plots
# --------------------------------------------------------------------------- #
def demo_line_plots() -> None:
    t = im.get_time()
    xs1 = [i * 0.001 for i in range(1001)]
    ys1 = [0.5 + 0.5 * math.cos(50 * (x + t / 10)) for x in xs1]
    zs1 = [0.5 + 0.5 * math.sin(50 * (x + t / 10)) for x in xs1]
    xs2 = [i * 1 / 19.0 for i in range(20)]
    ys2 = [x * x for x in xs2]
    zs2 = [x * y for x, y in zip(xs2, ys2)]
    if p3.begin_plot("Line Plots"):
        p3.setup_axes("x", "y", "z")
        p3.plot_line("f(x)", xs1, ys1, zs1, 1001)
        p3.plot_line("g(x)", xs2, ys2, zs2, 20,
                     (p3.PROP_MARKER, p3.MARKER_CIRCLE, p3.PROP_FLAGS, p3.LINE_FLAGS_SEGMENTS))
        p3.end_plot()


def demo_scatter_plots() -> None:
    rand = _srand_rand(0)
    xs1 = [i * 0.01 for i in range(100)]
    ys1, zs1 = [], []
    for x in xs1:
        ys1.append(x + 0.1 * rand())
        zs1.append(x + 0.1 * rand())
    xs2, ys2, zs2 = [], [], []
    for _ in range(50):
        xs2.append(0.25 + 0.2 * rand())
        ys2.append(0.50 + 0.2 * rand())
        zs2.append(0.75 + 0.2 * rand())
    if p3.begin_plot("Scatter Plots"):
        p3.plot_scatter("Data 1", xs1, ys1, zs1, 100)
        spec = Spec()
        spec.marker = p3.MARKER_SQUARE
        spec.marker_size = 6
        spec.marker_line_color = p3.get_colormap_color(1)
        spec.marker_fill_color = p3.get_colormap_color(1)
        spec.fill_alpha = 0.25
        p3.plot_scatter("Data 2", xs2, ys2, zs2, 50, spec)
        p3.end_plot()


def _pyramid():
    ax, ay, az = 0.0, 0.0, 1.0
    cx, cy, cz = (-0.5, 0.5, 0.5, -0.5), (-0.5, -0.5, 0.5, 0.5), (0.0, 0.0, 0.0, 0.0)
    order = [("a", 0, 1), ("a", 1, 2), ("a", 2, 3), ("a", 3, 0), (0, 1, 2), (0, 2, 3)]
    xs, ys, zs = [], [], []
    for tri in order:
        for v in tri:
            if v == "a":
                xs.append(ax), ys.append(ay), zs.append(az)
            else:
                xs.append(cx[v]), ys.append(cy[v]), zs.append(cz[v])
    return xs, ys, zs


def demo_triangle_plots() -> None:
    xs, ys, zs = _pyramid()
    st = _state("triangle", flags=p3.TRIANGLE_FLAGS_NONE)
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DTriangleFlags_NoLines")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DTriangleFlags_NoFill")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DTriangleFlags_NoMarkers")
    if p3.begin_plot("Triangle Plots"):
        p3.setup_axes_limits(-1, 1, -1, 1, -0.5, 1.5)
        spec = Spec()
        spec.fill_color = p3.get_colormap_color(0)
        spec.line_color = p3.get_colormap_color(1)
        spec.marker = p3.MARKER_SQUARE
        spec.marker_size = 3
        spec.flags = st["flags"]
        p3.plot_triangle("Pyramid", xs, ys, zs, 6 * 3, spec)
        p3.end_plot()


def _cube_faces(lo: float, hi: float):
    """The quad demo's six faces, in its vertex order: +x, -x, +y, -y, +z, -z."""
    faces = [
        [(hi, lo, lo), (hi, hi, lo), (hi, hi, hi), (hi, lo, hi)],
        [(lo, lo, lo), (lo, hi, lo), (lo, hi, hi), (lo, lo, hi)],
        [(lo, hi, lo), (hi, hi, lo), (hi, hi, hi), (lo, hi, hi)],
        [(lo, lo, lo), (hi, lo, lo), (hi, lo, hi), (lo, lo, hi)],
        [(lo, lo, hi), (hi, lo, hi), (hi, hi, hi), (lo, hi, hi)],
        [(lo, lo, lo), (hi, lo, lo), (hi, hi, lo), (lo, hi, lo)],
    ]
    verts = [v for face in faces for v in face]
    return [v[0] for v in verts], [v[1] for v in verts], [v[2] for v in verts]


def demo_quad_plots() -> None:
    xs, ys, zs = _cube_faces(-1.0, 1.0)
    st = _state("quad", flags=p3.QUAD_FLAGS_NONE)
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DQuadFlags_NoLines")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DQuadFlags_NoFill")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DQuadFlags_NoMarkers")
    if p3.begin_plot("Quad Plots"):
        p3.setup_axes_limits(-1.5, 1.5, -1.5, 1.5, -1.5, 1.5)
        spec = Spec()
        spec.marker = p3.MARKER_SQUARE
        spec.marker_size = 3
        spec.flags = st["flags"]
        for name, start, colour in (("X", 0, (0.8, 0.2, 0.2, 0.8)), ("Y", 8, (0.2, 0.8, 0.2, 0.8)),
                                    ("Z", 16, (0.2, 0.2, 0.8, 0.8))):
            spec.fill_color = colour
            spec.line_color = colour
            p3.plot_quad(name, xs[start:], ys[start:], zs[start:], 8, spec)
        p3.end_plot()


SURFACE_COLORMAPS = ["Viridis", "Plasma", "Hot", "Cool", "Pink", "Jet", "Twilight", "RdBu",
                     "BrBG", "PiYG", "Spectral", "Greys"]


def demo_surface_plots() -> None:
    n = 20
    st = _state("surface", t=0.0, selected_fill=1, solid_color=(0.8, 0.8, 0.2, 0.6),
                sel_colormap=5, custom_range=False, range_min=-1.0, range_max=1.0,
                flags=p3.SURFACE_FLAGS_NO_MARKERS)
    st["t"] += im.get_io().delta_time
    t = st["t"]
    min_val, max_val = -1.0, 1.0
    step = (max_val - min_val) / (n - 1)
    xs, ys, zs, custom = [], [], [], []
    for i in range(n):
        for j in range(n):
            x, y = min_val + j * step, min_val + i * step
            z = math.sin(2 * t + math.sqrt(x * x + y * y))
            xs.append(x), ys.append(y), zs.append(z)
            custom.append(p3.IM_COL32(int((x + 1) * 0.5 * 255), int((y + 1) * 0.5 * 255),
                                      int((z + 1) * 0.5 * 255), 255))
    im.text("Fill color")
    im.indent()
    _c, st["selected_fill"] = im.radio_button("Solid", st["selected_fill"], 0)
    if st["selected_fill"] == 0:
        im.same_line()
        _c, st["solid_color"] = im.color_edit4("##SurfaceSolidColor", st["solid_color"])
    _c, st["selected_fill"] = im.radio_button("Colormap", st["selected_fill"], 1)
    if st["selected_fill"] == 1:
        im.same_line()
        _c, st["sel_colormap"] = im.combo("##SurfaceColormap", st["sel_colormap"], SURFACE_COLORMAPS)
    _c, st["selected_fill"] = im.radio_button("Custom Per-Point", st["selected_fill"], 2)
    if st["selected_fill"] == 2:
        im.same_line()
        im.text_disabled("R=x, G=y, B=z")
    im.unindent()
    im.begin_disabled(st["selected_fill"] != 1)
    _c, st["custom_range"] = im.checkbox("Custom range", st["custom_range"])
    im.indent()
    im.begin_disabled(not st["custom_range"])
    _c, st["range_min"] = im.slider_float("Range min", st["range_min"], -1.0, st["range_max"] - 0.01)
    _c, st["range_max"] = im.slider_float("Range max", st["range_max"], st["range_min"] + 0.01, 1.0)
    im.end_disabled()
    im.unindent()
    im.end_disabled()
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DSurfaceFlags_NoLines")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DSurfaceFlags_NoFill")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DSurfaceFlags_NoMarkers")

    if st["selected_fill"] == 1:
        p3.push_colormap(SURFACE_COLORMAPS[st["sel_colormap"]])
    if p3.begin_plot("Surface Plots", (-1, 0), p3.FLAGS_NO_CLIP):
        p3.setup_axes_limits(-1, 1, -1, 1, -1.5, 1.5)
        spec = Spec()
        spec.fill_alpha = 0.8
        spec.flags = st["flags"]
        spec.marker = p3.MARKER_SQUARE
        spec.line_color = p3.get_colormap_color(1)
        if st["selected_fill"] == 0:
            spec.fill_color = st["solid_color"]
        elif st["selected_fill"] == 2:
            spec.fill_colors = custom
        if st["custom_range"]:
            p3.plot_surface("Wave Surface", xs, ys, zs, n, n, st["range_min"], st["range_max"], spec)
        else:
            p3.plot_surface("Wave Surface", xs, ys, zs, n, n, 0.0, 0.0, spec)
        p3.end_plot()
    if st["selected_fill"] == 1:
        p3.pop_colormap()


def demo_mesh_plots() -> None:
    st = _state("mesh", mesh_id=0, line_color=(0.5, 0.5, 0.2, 0.6),
                fill_color=(0.8, 0.8, 0.2, 0.6), marker_color=(0.5, 0.5, 0.2, 0.6),
                flags=p3.MESH_FLAGS_NO_MARKERS)
    _c, st["mesh_id"] = im.combo("Mesh", st["mesh_id"], ["Duck", "Sphere", "Cube"])
    _c, st["line_color"] = im.color_edit4("Line Color##Mesh", st["line_color"])
    _c, st["fill_color"] = im.color_edit4("Fill Color##Mesh", st["fill_color"])
    _c, st["marker_color"] = im.color_edit4("Marker Color##Mesh", st["marker_color"])
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DMeshFlags_NoLines")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DMeshFlags_NoFill")
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DMeshFlags_NoMarkers")
    if p3.begin_plot("Mesh Plots"):
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        spec = Spec()
        spec.flags = st["flags"]
        spec.fill_color = st["fill_color"]
        spec.line_color = st["line_color"]
        spec.marker = p3.MARKER_SQUARE
        spec.marker_size = 3.0
        spec.marker_line_color = st["marker_color"]
        spec.marker_fill_color = st["marker_color"]
        mesh = ((p3.DUCK_VTX, p3.DUCK_IDX, "Duck"), (p3.SPHERE_VTX, p3.SPHERE_IDX, "Sphere"),
                (p3.CUBE_VTX, p3.CUBE_IDX, "Cube"))[st["mesh_id"]]
        p3.plot_mesh(mesh[2], mesh[0], mesh[1], spec=spec)
        p3.end_plot()


def demo_texture():
    """The stand-in for ImGui's font atlas: a 64x64 checkerboard with a gradient."""
    st = _state("texture", tex=None)
    if st["tex"] is None:
        from .texture import Texture
        size = 64
        px = bytearray(size * size * 4)
        for y in range(size):
            for x in range(size):
                o = (y * size + x) * 4
                on = ((x // 8) + (y // 8)) % 2
                px[o] = 60 + int(195 * x / (size - 1)) if on else 30
                px[o + 1] = 60 + int(195 * y / (size - 1)) if on else 30
                px[o + 2] = 200 if on else 60
                px[o + 3] = 255
        st["tex"] = Texture(size, size, px)
    return st["tex"]


def demo_image_plots() -> None:
    im.bullet_text("Below we are displaying a generated texture (the reference shows its\n"
                   "font atlas, which emtk does not have as a texture).")
    im.bullet_text("Pass an emtk.texture.Texture, or whatever your painter's image_triangle reads.")
    st = _state("image", tint1=(1.0, 1.0, 1.0, 1.0), tint2=(1.0, 1.0, 1.0, 1.0),
                center1=(0.0, 0.0, 1.0), axis_u1=(1.0, 0.0, 0.0), axis_v1=(0.0, 1.0, 0.0),
                uv0_1=(0.0, 0.0), uv1_1=(1.0, 1.0), p0=(-1.0, -1.0, 0.0), p1=(1.0, -1.0, 0.0),
                p2=(1.0, 1.0, 0.0), p3=(-1.0, 1.0, 0.0), uv0=(0.0, 0.0), uv1=(1.0, 0.0),
                uv2=(1.0, 1.0), uv3=(0.0, 1.0))
    im.dummy(0, 10)
    if im.tree_node_ex("Image 1 Controls: Center + Axes"):
        _c, st["center1"] = im.slider_float3("Center", st["center1"], -2, 2, "%.1f")
        _c, st["axis_u1"] = im.slider_float3("Axis U", st["axis_u1"], -2, 2, "%.1f")
        _c, st["axis_v1"] = im.slider_float3("Axis V", st["axis_v1"], -2, 2, "%.1f")
        _c, st["uv0_1"] = im.slider_float2("UV0", st["uv0_1"], 0, 1, "%.2f")
        _c, st["uv1_1"] = im.slider_float2("UV1", st["uv1_1"], 0, 1, "%.2f")
        _c, st["tint1"] = im.color_edit4("Tint", st["tint1"])
        im.tree_pop()
    if im.tree_node_ex("Image 2 Controls: Full Quad"):
        for key in ("p0", "p1", "p2", "p3"):
            _c, st[key] = im.slider_float3(key.upper(), st[key], -2, 2, "%.1f")
        for key in ("uv0", "uv1", "uv2", "uv3"):
            _c, st[key] = im.slider_float2(key.upper(), st[key], 0, 1, "%.2f")
        _c, st["tint2"] = im.color_edit4("Tint##2", st["tint2"])
        im.tree_pop()
    if p3.begin_plot("Image Plot", (-1, 0), p3.FLAGS_NO_CLIP):
        tex = demo_texture()
        p3.plot_image("Image 1", tex, st["center1"], st["axis_u1"], st["axis_v1"],
                      st["uv0_1"], st["uv1_1"], st["tint1"])
        p3.plot_image("Image 2", tex, st["p0"], st["p1"], st["p2"], st["p3"],
                      st["uv0"], st["uv1"], st["uv2"], st["uv3"], st["tint2"])
        p3.end_plot()


def demo_realtime_plots() -> None:
    im.bullet_text("Move your mouse to change the data!")
    st = _state("realtime", sdata1=ScrollingBuffer(), sdata2=ScrollingBuffer(),
                sdata3=ScrollingBuffer(), flags=p3.AXIS_FLAGS_NO_TICK_LABELS, t=0.0, last_t=-1.0)
    if p3.begin_plot("Scrolling Plot"):
        st["t"] += im.get_io().delta_time
        t = st["t"]
        if t - st["last_t"] > 0.01:
            st["last_t"] = t
            mouse = im.get_mouse_pos()
            if abs(mouse[0]) < 1e4 and abs(mouse[1]) < 1e4:
                fx, fy = p3.get_frame_pos()
                fw, fh = p3.get_frame_size()
                st["sdata1"].add_point(t)
                st["sdata2"].add_point(mouse[0] - (fx + fw / 2))
                st["sdata3"].add_point(mouse[1] - (fy + fh / 2))
        flags = st["flags"]
        p3.setup_axes("Time", "Mouse X", "Mouse Y", flags, flags, flags)
        p3.setup_axis_limits(p3.AXIS_X, t - 10.0, t, p3.COND_ALWAYS)
        p3.setup_axis_limits(p3.AXIS_Y, -400, 400, p3.COND_ONCE)
        p3.setup_axis_limits(p3.AXIS_Z, -400, 400, p3.COND_ONCE)
        d1, d2, d3 = st["sdata1"], st["sdata2"], st["sdata3"]
        if d1.data:
            p3.plot_line("Mouse", d1.data, d2.data, d3.data, len(d1.data),
                         (p3.PROP_OFFSET, d1.offset, p3.PROP_STRIDE, 1))
        p3.end_plot()


_PLOT_FLAG_HELP = (
    ("ImPlot3DFlags_NoTitle", "Hide plot title"),
    ("ImPlot3DFlags_NoLegend", "Hide plot legend"),
    ("ImPlot3DFlags_NoMouseText", "Hide mouse position in plot coordinates"),
    ("ImPlot3DFlags_NoClip", "Disable 3D box clipping"),
    ("ImPlot3DFlags_NoMenus", "The user will not be able to open context menus"),
    ("ImPlot3DFlags_Equal", "X, Y, and Z axes will be constrained to have the same units/pixel"),
    ("ImPlot3DFlags_NoRotate", "Lock rotation interaction"),
    ("ImPlot3DFlags_NoPan", "Lock panning/translation interaction"),
    ("ImPlot3DFlags_NoZoom", "Lock zooming interaction"),
    ("ImPlot3DFlags_NoInputs", "Disable all user inputs"),
)


def demo_plot_flags() -> None:
    st = _state("plot_flags", flags=p3.FLAGS_NONE)
    for name, tip in _PLOT_FLAG_HELP:
        st["flags"] = checkbox_flag(st["flags"], name)
        im.same_line()
        help_marker(tip)
    if p3.begin_plot("Plot Flags Demo", (-1, 0), st["flags"]):
        p3.setup_axes("X-axis", "Y-axis", "Z-axis")
        p3.setup_axes_limits(-10, 10, -10, 10, -5, 5)
        ts = [i * 0.1 for i in range(100)]
        p3.plot_line("Helix", [3.0 * math.cos(t) for t in ts], [3.0 * math.sin(t) for t in ts],
                     [t - 5.0 for t in ts], 100)
        p3.plot_scatter("Cube corners", [-10, 10, -10, 10, -10, 10, -10, 10],
                        [-10, -10, 10, 10, -10, -10, 10, 10], [-5, -5, -5, -5, 5, 5, 5, 5], 8)
        p3.end_plot()


def demo_offset_and_stride() -> None:
    k_spirals, k_points_per = 11, 50
    data = [0.0] * (3 * k_points_per * k_spirals)
    for p in range(k_points_per):
        for s in range(k_spirals):
            r = s / (k_spirals - 1) * 0.2 + 0.2
            theta = p / k_points_per * 6.28
            data[p * 3 * k_spirals + 3 * s + 0] = 0.5 + r * math.cos(theta)
            data[p * 3 * k_spirals + 3 * s + 1] = 0.5 + r * math.sin(theta)
            data[p * 3 * k_spirals + 3 * s + 2] = 0.5 + 0.5 * math.sin(2.0 * theta)
    st = _state("stride", offset=0)
    im.bullet_text("Offsetting is useful for realtime plots (see above) and circular buffers.")
    im.bullet_text("Striding is useful for interleaved data (e.g. audio) or plotting structs.")
    im.bullet_text("Here, all spiral data is stored in a single interleaved buffer:")
    im.bullet_text("[s0.x0 s0.y0 s0.z0 ... sn.x0 sn.y0 sn.z0 s0.x1 s0.y1 s0.z1 ... sn.xm sn.ym sn.zm]")
    im.bullet_text("The offset value indicates which spiral point index is considered the first.")
    im.bullet_text("Offsets can be negative and/or larger than the actual data count.")
    _c, st["offset"] = im.slider_int("Offset", st["offset"], -2 * k_points_per, 2 * k_points_per)
    if p3.begin_plot("##strideoffset", (-1, 0)):
        p3.push_colormap(p3.COLORMAP_JET)
        for s in range(k_spirals):
            spec = Spec(offset=st["offset"], stride=3 * k_spirals)
            p3.plot_line("Spiral %d" % s, data[s * 3 + 0:], data[s * 3 + 1:], data[s * 3 + 2:],
                         k_points_per, spec)
        p3.end_plot()
        p3.pop_colormap()


def demo_legend_options() -> None:
    st = _state("legend", loc=p3.LOCATION_EAST, flags=0, num_dummy_items=25, t=0.0)
    for name, bit in (("North", p3.LOCATION_NORTH), ("South", p3.LOCATION_SOUTH),
                      ("West", p3.LOCATION_WEST), ("East", p3.LOCATION_EAST)):
        _c, st["loc"] = im.checkbox_flags(name, st["loc"], bit)
        if name != "East":
            im.same_line()
    for name, tip in (("ImPlot3DLegendFlags_Horizontal", "Legend entries will be displayed horizontally"),
                      ("ImPlot3DLegendFlags_NoButtons", "Legend icons will not function as hide/show buttons"),
                      ("ImPlot3DLegendFlags_NoHighlightItem",
                       "Plot items will not be highlighted when their legend entry is hovered")):
        st["flags"] = checkbox_flag(st["flags"], name)
        im.same_line()
        help_marker(tip)
    style = p3.get_style()
    _c, style.legend_padding = im.slider_float2("LegendPadding", style.legend_padding, 0.0, 20.0, "%.0f")
    _c, style.legend_inner_padding = im.slider_float2("LegendInnerPadding", style.legend_inner_padding, 0.0, 10.0, "%.0f")
    _c, style.legend_spacing = im.slider_float2("LegendSpacing", style.legend_spacing, 0.0, 5.0, "%.0f")
    _c, st["num_dummy_items"] = im.slider_int("Num Dummy Items (Demo Scrolling)", st["num_dummy_items"], 0, 100)
    if p3.begin_plot("Legend Options Demo", (-1, 0)):
        p3.setup_axes("X-Axis", "Y-Axis", "Z-Axis")
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        p3.setup_legend(st["loc"], st["flags"])
        st["t"] += im.get_io().delta_time * 0.5
        phase = [i * 0.1 + st["t"] for i in range(50)]
        p3.plot_line("Helix A", [0.8 * math.cos(a) for a in phase], [0.8 * math.sin(a) for a in phase],
                     [0.5 * math.sin(a * 2) for a in phase], 50)
        p3.plot_line("Helix B##IDText", [0.6 * math.cos(a + 1.0) for a in phase],
                     [0.6 * math.sin(a + 1.0) for a in phase], [-0.3 * math.cos(a * 1.5) for a in phase], 50)
        p3.plot_line("##NotListed", [0.4 * math.sin(a) for a in phase], [0.4 * math.cos(a) for a in phase],
                     [0.7 * math.cos(a * 0.8) for a in phase], 50)
        for i in range(st["num_dummy_items"]):
            p3.plot_dummy("Item %03d" % i)
        p3.end_plot()


def demo_markers_and_text() -> None:
    st = _state("markers", mk_size=p3.get_style().marker_size, mk_weight=p3.get_style().line_weight)
    _c, st["mk_size"] = im.drag_float("Marker Size", st["mk_size"], 0.1, 2.0, 10.0, "%.2f px")
    _c, st["mk_weight"] = im.drag_float("Marker Weight", st["mk_weight"], 0.05, 0.5, 3.0, "%.2f px")
    if p3.begin_plot("##MarkerStyles", (-1, 0), p3.FLAGS_CANVAS_ONLY):
        nd = p3.AXIS_FLAGS_NO_DECORATIONS
        p3.setup_axes(None, None, None, nd, nd, nd)
        p3.setup_axes_limits(-0.5, 1.5, -0.5, 1.5, 0, p3.MARKER_COUNT + 1)
        count = float(p3.MARKER_COUNT)
        for base, sign, name, extra in (((0.0, 0.0), 1.0, "##Filled", ()),
                                        ((1.0, 1.0), -1.0, "##Open", (p3.PROP_FILL_COLOR, (0.0, 0.0, 0.0, 0.0)))):
            zs = [count, count + 1]
            for m in range(p3.MARKER_COUNT):
                xs = [base[0], base[0] + math.cos(zs[0] / count * 2 * math.pi) * 0.5]
                ys = [base[1], base[1] + sign * math.sin(zs[0] / count * 2 * math.pi) * 0.5]
                im.push_id(m)
                p3.plot_line(name, xs, ys, list(zs), 2,
                             (p3.PROP_MARKER, m, p3.PROP_MARKER_SIZE, st["mk_size"],
                              p3.PROP_LINE_WEIGHT, st["mk_weight"], *extra))
                im.pop_id()
                zs = [zs[0] - 1, zs[1] - 1]
        p3.plot_text("Filled Markers", 0.0, 0.0, 6.0)
        p3.plot_text("Open Markers", 1.0, 1.0, 6.0)
        p3.push_style_color(p3.COL_INLAY_TEXT, (1.0, 0.0, 1.0, 1.0))
        p3.plot_text("Rotated Text", 0.5, 0.5, 6.0, math.pi / 4, (0, 0))
        p3.pop_style_color()
        p3.end_plot()


def demo_nan_values() -> None:
    st = _state("nan", include_nan=True, flags=0)
    data1 = [0.0, 0.25, 0.5, 0.75, 1.0]
    data2 = list(data1)
    data3 = list(data1)
    if st["include_nan"]:
        data1[2] = math.nan
    _c, st["include_nan"] = im.checkbox("Include NaN", st["include_nan"])
    im.same_line()
    _c, st["flags"] = im.checkbox_flags("Skip NaN", st["flags"], p3.LINE_FLAGS_SKIP_NAN)
    if p3.begin_plot("##NaNValues"):
        p3.plot_line("Line", data1, data2, data3, 5,
                     (p3.PROP_FLAGS, st["flags"], p3.PROP_MARKER, p3.MARKER_SQUARE))
        p3.end_plot()


def _duck_gouraud_colors():
    st = _state("duck_colors", colors=None)
    if st["colors"] is not None:
        return st["colors"]
    vtx, idx = p3.DUCK_VTX, p3.DUCK_IDX
    normals = [[0.0, 0.0, 0.0] for _ in vtx]
    for i in range(0, len(idx), 3):
        i0, i1, i2 = idx[i], idx[i + 1], idx[i + 2]
        p0, p1, p2 = vtx[i0], vtx[i1], vtx[i2]
        a = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        b = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        fn = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        for v in (i0, i1, i2):
            for k in range(3):
                normals[v][k] += fn[k]

    def norm3(v):
        length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        return (v[0] / length, v[1] / length, v[2] / length) if length > 1e-8 else (0.0, 0.0, 1.0)

    light_pos, duck_col = (2.0, 2.0, 3.0), (1.0, 0.85, 0.1)
    light_col, ambient = (1.0, 0.95, 0.8), (0.15, 0.12, 0.03)
    vtx_colors = []
    for v, pos in enumerate(vtx):
        n = norm3(normals[v])
        to_light = norm3((light_pos[0] - pos[0], light_pos[1] - pos[1], light_pos[2] - pos[2]))
        diff = max(0.0, n[0] * to_light[0] + n[1] * to_light[1] + n[2] * to_light[2])
        rgb = [min(1.0, ambient[k] + duck_col[k] * light_col[k] * diff) for k in range(3)]
        vtx_colors.append(p3.IM_COL32(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255), 255))
    st["colors"] = [vtx_colors[i] for i in idx]
    return st["colors"]


def demo_per_index_colors() -> None:
    t = im.get_time()
    xs1 = [i * 0.001 for i in range(1001)]
    ys1 = [0.5 + 0.5 * math.sin(50 * (x + t / 10)) for x in xs1]
    zs1 = [0.5 + 0.5 * math.cos(50 * (x + t / 10)) for x in xs1]
    colors1 = [_hsv(i / 1000.0, 0.8, 0.9) for i in range(1001)]
    xs2 = [i * 1 / 19.0 for i in range(20)]
    ys2 = [x * x for x in xs2]
    zs2 = [x * y for x, y in zip(xs2, ys2)]
    colors2 = [p3.color_convert_float4_to_u32(p3.sample_colormap(i / 19.0, p3.COLORMAP_VIRIDIS))
               for i in range(20)]
    if p3.begin_plot("Colorful Lines"):
        p3.plot_line("f(x)", xs1, ys1, zs1, 1001, (p3.PROP_LINE_COLORS, colors1))
        p3.plot_line("g(x)", xs2, ys2, zs2, 20,
                     (p3.PROP_MARKER, p3.MARKER_CIRCLE, p3.PROP_FLAGS, p3.LINE_FLAGS_SEGMENTS,
                      p3.PROP_LINE_COLORS, colors2, p3.PROP_MARKER_FILL_COLORS, colors2,
                      p3.PROP_MARKER_LINE_COLORS, colors2))
        p3.end_plot()

    rand = _srand_rand(0)
    xs_s1 = [i * 0.01 for i in range(100)]
    ys_s1, zs_s1, fill1, line1, sizes1 = [], [], [], [], []
    for i, x in enumerate(xs_s1):
        ys_s1.append(x + 0.1 * rand())
        zs_s1.append(x + 0.1 * rand())
        fill1.append(_hsv(i / 99.0, 0.8, 0.9))
        line1.append(_hsv(i / 99.0, 0.9, 0.7))
        sizes1.append(2.0 + 4.0 * rand())
    xs_s2, ys_s2, zs_s2, col_s2, sizes2 = [], [], [], [], []
    for i in range(50):
        xs_s2.append(0.25 + 0.2 * rand())
        ys_s2.append(0.50 + 0.2 * rand())
        zs_s2.append(0.75 + 0.2 * rand())
        col_s2.append(p3.color_convert_float4_to_u32(p3.sample_colormap(i / 49.0, p3.COLORMAP_VIRIDIS)))
        sizes2.append(2.0 + 4.0 * rand())
    if p3.begin_plot("Colorful Scatter"):
        p3.plot_scatter("Data 1", xs_s1, ys_s1, zs_s1, 100,
                        (p3.PROP_MARKER_FILL_COLORS, fill1, p3.PROP_MARKER_LINE_COLORS, line1,
                         p3.PROP_MARKER_SIZES, sizes1))
        p3.plot_scatter("Data 2", xs_s2, ys_s2, zs_s2, 50,
                        (p3.PROP_MARKER, p3.MARKER_SQUARE, p3.PROP_MARKER_FILL_COLORS, col_s2,
                         p3.PROP_MARKER_LINE_COLORS, col_s2, p3.PROP_MARKER_SIZES, sizes2,
                         p3.PROP_FILL_ALPHA, 0.5))
        p3.end_plot()

    xs_t, ys_t, zs_t = _pyramid()
    colors_t = [p3.color_convert_float4_to_u32(p3.sample_colormap(0.5 * z, p3.COLORMAP_HOT)) for z in zs_t]
    if p3.begin_plot("Colorful Triangles"):
        p3.setup_axes_limits(-1, 1, -1, 1, -0.5, 1.5)
        p3.plot_triangle("Pyramid", xs_t, ys_t, zs_t, 18,
                         (p3.PROP_FILL_COLORS, colors_t, p3.PROP_FILL_ALPHA, 0.8))
        p3.end_plot()

    xs_q, ys_q, zs_q = _cube_faces(0.0, 1.0)
    colors_q = [p3.IM_COL32(int(x * 255), int(y * 255), int(z * 255), 255)
                for x, y, z in zip(xs_q, ys_q, zs_q)]
    if p3.begin_plot("Colorful Quads"):
        p3.setup_axes_limits(-0.5, 1.5, -0.5, 1.5, -0.5, 1.5)
        p3.plot_quad("Cube", xs_q, ys_q, zs_q, 24, (p3.PROP_FILL_COLORS, colors_q, p3.PROP_FILL_ALPHA, 0.8))
        p3.end_plot()

    if p3.begin_plot("Gouraud Duck"):
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        p3.plot_mesh("Duck", p3.DUCK_VTX, p3.DUCK_IDX,
                     spec=(p3.PROP_FILL_COLORS, _duck_gouraud_colors(), p3.PROP_FLAGS,
                           p3.MESH_FLAGS_NO_LINES))
        p3.end_plot()


# --------------------------------------------------------------------------- #
# [SECTION] Axes
# --------------------------------------------------------------------------- #
def demo_box_scale() -> None:
    n = 100
    ts = [i / (n - 1) for i in range(n)]
    st = _state("box_scale", scale=(1.0, 1.0, 1.0))
    _c, st["scale"] = im.slider_float3("Box Scale", st["scale"], 0.1, 2.0, "%.2f")
    if p3.begin_plot("##BoxScale"):
        p3.setup_box_scale(*st["scale"])
        p3.plot_line("3D Curve", [math.sin(t * 2 * math.pi) for t in ts],
                     [math.cos(t * 4 * math.pi) for t in ts], [t * 2.0 - 1.0 for t in ts], n)
        p3.end_plot()


def demo_box_rotation() -> None:
    origin, axis = [0.0, 0.0], [0.0, 1.0]
    st = _state("box_rotation", elevation=45.0, azimuth=-135.0, animate=False,
                init_elevation=45.0, init_azimuth=-135.0)
    im.text("Rotation")
    changed = False
    c, st["elevation"] = im.slider_float("Elevation", st["elevation"], -90.0, 90.0, "%.1f degrees")
    changed = changed or c
    c, st["azimuth"] = im.slider_float("Azimuth", st["azimuth"], -180.0, 180.0, "%.1f degrees")
    changed = changed or c
    _c, st["animate"] = im.checkbox("Animate", st["animate"])
    im.text("Initial Rotation")
    im.same_line()
    help_marker("The rotation will be reset to the initial rotation when you double right-click")
    _c, st["init_elevation"] = im.slider_float("Initial Elevation", st["init_elevation"], -90.0, 90.0, "%.1f degrees")
    _c, st["init_azimuth"] = im.slider_float("Initial Azimuth", st["init_azimuth"], -180.0, 180.0, "%.1f degrees")
    if p3.begin_plot("##BoxRotation"):
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1, p3.COND_ALWAYS)
        p3.setup_box_initial_rotation(st["init_elevation"], st["init_azimuth"])
        if changed or st.pop("force", False):
            p3.setup_box_rotation(st["elevation"], st["azimuth"], st["animate"], p3.COND_ALWAYS)
        p3.plot_line("X-Axis", axis, origin, origin, 2, (p3.PROP_LINE_COLOR, (0.8, 0.2, 0.2, 1.0)))
        p3.plot_line("Y-Axis", origin, axis, origin, 2, (p3.PROP_LINE_COLOR, (0.2, 0.8, 0.2, 1.0)))
        p3.plot_line("Z-Axis", origin, origin, axis, 2, (p3.PROP_LINE_COLOR, (0.2, 0.2, 0.8, 1.0)))
        p3.end_plot()


def demo_log_scale() -> None:
    xs = [i * 0.1 for i in range(1001)]
    ys1 = [math.sin(x) + 1 for x in xs]
    ys2 = [math.log(x) if x > 0 else -math.inf for x in xs]
    ys3 = [10.0 ** x for x in xs[:21]]
    zs = [0.0] * 1001
    if p3.begin_plot("Log Plot 3D", (-1, 0)):
        p3.setup_axis_scale(p3.AXIS_X, p3.SCALE_LOG10)
        p3.setup_axes_limits(0.1, 100, 0, 10, -1, 1)
        p3.plot_line("f(x) = x", xs, xs, zs, 1001)
        p3.plot_line("f(x) = sin(x)+1", xs, ys1, zs, 1001)
        p3.plot_line("f(x) = log(x)", xs, ys2, zs, 1001)
        p3.plot_line("f(x) = 10^x", xs, ys3, zs, 21)
        p3.end_plot()


def demo_symmetric_log_scale() -> None:
    xs = [i * 0.1 - 50 for i in range(1001)]
    ys1 = [math.sin(x) for x in xs]
    ys2 = [i * 0.002 - 1 for i in range(1001)]
    zs = [0.0] * 1001
    if p3.begin_plot("SymLog Plot", (-1, 0)):
        p3.setup_axis_scale(p3.AXIS_X, p3.SCALE_SYMLOG)
        p3.plot_line("f(x) = a*x+b", xs, ys2, zs, 1001)
        p3.plot_line("f(x) = sin(x)", xs, ys1, zs, 1001)
        p3.end_plot()


def demo_tick_labels() -> None:
    st = _state("ticks", custom_fmt=True, custom_ticks=False, custom_labels=True)
    _c, st["custom_fmt"] = im.checkbox("Show Custom Format", st["custom_fmt"])
    im.same_line()
    _c, st["custom_ticks"] = im.checkbox("Show Custom Ticks", st["custom_ticks"])
    if st["custom_ticks"]:
        im.same_line()
        _c, st["custom_labels"] = im.checkbox("Show Custom Labels", st["custom_labels"])
    letters_ticks = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    letters_labels = ["A", "B", "C", "D", "E", "F"]
    if p3.begin_plot("##Ticks"):
        p3.setup_axes_limits(2, 5, 0, 1, 0, 1000)
        if st["custom_fmt"]:
            p3.setup_axis_format(p3.AXIS_Y, metric_formatter, "Hz")
            p3.setup_axis_format(p3.AXIS_Z, metric_formatter, "m")
        if st["custom_ticks"]:
            labels = st["custom_labels"]
            p3.setup_axis_ticks(p3.AXIS_X, [3.14], 1, ["PI"] if labels else None, True)
            p3.setup_axis_ticks(p3.AXIS_Y, letters_ticks, 6, letters_labels if labels else None, False)
            p3.setup_axis_ticks(p3.AXIS_Z, 0, 1000, 6, letters_labels if labels else None, False)
        p3.end_plot()


def demo_axis_constraints() -> None:
    st = _state("constraints", limits=(-10.0, 10.0), zoom=(1.0, 20.0), flags=0)
    _c, st["limits"] = im.drag_float2("Limits Constraints", st["limits"], 0.01)
    _c, st["zoom"] = im.drag_float2("Zoom Constraints", st["zoom"], 0.01)
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DAxisFlags_PanStretch")
    if p3.begin_plot("##AxisConstraints", (-1, 0)):
        f = st["flags"]
        p3.setup_axes("X", "Y", "Z", f, f, f)
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        for axis in (p3.AXIS_X, p3.AXIS_Y, p3.AXIS_Z):
            p3.setup_axis_limits_constraints(axis, *st["limits"])
            p3.setup_axis_zoom_constraints(axis, *st["zoom"])
        p3.end_plot()


def demo_equal_axes() -> None:
    im.bullet_text("Equal constraint applies to all three axes (X, Y, Z)")
    im.bullet_text("When enabled, the axes maintain the same units/pixel ratio")
    angles = [i * 2 * math.pi / 359.0 for i in range(360)]
    st = _state("equal", flags=p3.FLAGS_EQUAL)
    st["flags"] = checkbox_flag(st["flags"], "ImPlot3DFlags_Equal")
    if p3.begin_plot("##EqualAxes", (-1, 0), st["flags"]):
        p3.setup_axes("X-Axis", "Y-Axis", "Z-Axis")
        p3.plot_line("Circle", [math.cos(a) for a in angles], [math.sin(a) for a in angles], [0.0] * 360, 360)
        p3.plot_line("Helix", [0.5 * math.cos(a) for a in angles], [0.5 * math.sin(a) for a in angles],
                     [i / 359.0 * 2.0 - 1.0 for i in range(360)], 360)
        p3.plot_line("Square", [-0.5, 0.5, 0.5, -0.5, -0.5], [-0.5, -0.5, 0.5, 0.5, -0.5], [-0.5] * 5, 5)
        p3.end_plot()


def demo_auto_fitting_data() -> None:
    im.bullet_text("Axes can be configured to auto-fit to data extents.")
    im.bullet_text("Try panning and zooming to see the axes adjust.")
    im.bullet_text("Disable AutoFit on an axis to fix its range.")
    st = _state("autofit", x=0, y=0, z=p3.AXIS_FLAGS_AUTO_FIT)
    for key in ("x", "y", "z"):
        im.text_unformatted("%s: " % key.upper())
        im.same_line()
        _c, st[key] = im.checkbox_flags("ImPlot3DAxisFlags_AutoFit##%s" % key.upper(), st[key],
                                        p3.AXIS_FLAGS_AUTO_FIT)
    if p3.begin_plot("##AutoFitting"):
        p3.setup_axes("X-Axis", "Y-Axis", "Z-Axis", st["x"], st["y"], st["z"])
        p3.plot_line("Wave", [i * 0.1 for i in range(101)], [i * 0.1 for i in range(101)],
                     [1 + math.sin(i / 10.0) for i in range(101)], 101)
        p3.end_plot()


# --------------------------------------------------------------------------- #
# [SECTION] Tools
# --------------------------------------------------------------------------- #
def demo_mouse_picking() -> None:
    st = _state("picking", points=[], rays=[], selected_plane=p3.PLANE_XY, mask_plane=True)
    im.bullet_text("Click anywhere in the plot to place points/rays.")
    _c, st["selected_plane"] = im.radio_button("XY-Plane", st["selected_plane"], p3.PLANE_XY)
    im.same_line()
    _c, st["selected_plane"] = im.radio_button("XZ-Plane", st["selected_plane"], p3.PLANE_XZ)
    im.same_line()
    _c, st["selected_plane"] = im.radio_button("YZ-Plane", st["selected_plane"], p3.PLANE_YZ)
    _c, st["mask_plane"] = im.checkbox("Mask Plane", st["mask_plane"])
    if im.button("Clear"):
        st["points"], st["rays"] = [], []
    if p3.begin_plot("Mouse Picking", (-1, 0), p3.FLAGS_NO_CLIP):
        p3.setup_axes("X-Axis", "Y-Axis", "Z-Axis")
        p3.setup_axes_limits(-1, 1, -1, 1, -1, 1)
        mouse = im.get_mouse_pos()
        ray = p3.pixels_to_plot_ray(mouse)
        point = p3.pixels_to_plot_plane(mouse, st["selected_plane"], st["mask_plane"])
        hovered = im.is_item_hovered()
        if hovered and not point.is_nan():
            spec = Spec(marker=p3.MARKER_CIRCLE, marker_size=5, fill_color=(1.0, 1.0, 0.0, 1.0))
            p3.plot_scatter("##Intersection", [point.x], [point.y], [point.z], 1, spec)
        if hovered and im.is_mouse_clicked(0) and not point.is_nan():
            st["points"].append(point)
            st["rays"].append(ray)
        if st["points"]:
            pts = st["points"]
            p3.plot_scatter("Placed Points", [q.x for q in pts], [q.y for q in pts], [q.z for q in pts],
                            len(pts), Spec(marker=p3.MARKER_CIRCLE, marker_size=3))
        if st["rays"]:
            ray_points = []
            for q, r in zip(st["points"], st["rays"]):
                ray_points += [q, q - r.direction]
            p3.plot_line("Placed Rays", [q.x for q in ray_points], [q.y for q in ray_points],
                         [q.z for q in ray_points], len(ray_points), Spec(flags=p3.LINE_FLAGS_SEGMENTS))
        p3.end_plot()


# --------------------------------------------------------------------------- #
# [SECTION] Custom
# --------------------------------------------------------------------------- #
def style_seaborn() -> None:
    """``MyImPlot3D::StyleSeaborn``."""
    style = p3.get_style()
    c = style.colors
    c[p3.COL_FRAME_BG] = (1.00, 1.00, 1.00, 1.00)
    c[p3.COL_PLOT_BG] = (0.92, 0.92, 0.95, 1.00)
    c[p3.COL_PLOT_BORDER] = (0.00, 0.00, 0.00, 0.00)
    c[p3.COL_LEGEND_BG] = (0.92, 0.92, 0.95, 1.00)
    c[p3.COL_LEGEND_BORDER] = (0.80, 0.81, 0.85, 1.00)
    c[p3.COL_LEGEND_TEXT] = (0.00, 0.00, 0.00, 1.00)
    c[p3.COL_TITLE_TEXT] = (0.00, 0.00, 0.00, 1.00)
    c[p3.COL_INLAY_TEXT] = (0.00, 0.00, 0.00, 1.00)
    c[p3.COL_AXIS_TEXT] = (0.00, 0.00, 0.00, 1.00)
    c[p3.COL_AXIS_GRID] = (1.00, 1.00, 1.00, 1.00)
    style.line_weight = 1.5
    style.marker = p3.MARKER_NONE
    style.marker_size = 4
    style.fill_alpha = 1.0
    style.plot_padding = (12.0, 12.0)
    style.label_padding = (5.0, 5.0)
    style.legend_padding = (5.0, 5.0)
    style.plot_min_size = (300.0, 225.0)


def demo_custom_styles() -> None:
    p3.push_colormap(p3.COLORMAP_DEEP)
    backup = p3.get_style().copy()
    style_seaborn()
    if p3.begin_plot("Seaborn Style"):
        p3.setup_axes("X-axis", "Y-axis", "Z-axis")
        p3.setup_axes_limits(-0.5, 9.5, -0.5, 0.5, 0, 10)
        xs = list(range(10))
        ys = [0] * 10
        lin = [8, 8, 9, 7, 8, 8, 8, 9, 7, 8]
        dot = [7, 6, 6, 7, 8, 5, 6, 5, 8, 7]
        p3.next_colormap_color()
        p3.plot_line("Line", xs, ys, lin, 10)
        p3.next_colormap_color()
        p3.plot_scatter("Scatter", xs, ys, dot, 10)
        p3.end_plot()
    p3._gp().style = backup
    p3.pop_colormap()


def demo_custom_rendering() -> None:
    if p3.begin_plot("##CustomRend"):
        p3.setup_axes_limits(-0.1, 1.1, -0.1, 1.1, -0.1, 1.1)
        cntr = p3.plot_to_pixels(Point(0.5, 0.5, 0.5))
        p3.get_plot_draw_list().add_circle_filled(cntr, 20, (255, 255, 0, 255), 20)
        corners = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
        px = [p3.plot_to_pixels(c) for c in corners]
        col = (128, 0, 255, 255)
        dl = p3.get_plot_draw_list()
        for i in range(4):
            dl.add_line(px[i], px[(i + 1) % 4], col)
            dl.add_line(px[i + 4], px[(i + 1) % 4 + 4], col)
            dl.add_line(px[i], px[i + 4], col)
        p3.end_plot()


def demo_custom_overlay() -> None:
    im.bullet_text("Demonstrates custom 2D overlays using GetPlotRectPos/GetPlotRectSize.")
    im.bullet_text("Shows mouse tooltip, line to closest point, and orientation gizmo.")
    rand = _srand_rand(0)
    xs, ys, zs = [], [], []
    for _ in range(50):
        xs.append(rand()), ys.append(rand()), zs.append(rand())
    if p3.begin_plot("##CustomOverlay", (-1, 0)):
        p3.setup_axes("X-Axis", "Y-Axis", "Z-Axis")
        p3.setup_axes_limits(0, 1, 0, 1, 0, 1)
        p3.plot_scatter("Data", xs, ys, zs, 50)
        dl = p3.get_plot_draw_list()
        mouse = im.get_mouse_pos()
        plot_pos, plot_size = p3.get_plot_rect_pos(), p3.get_plot_rect_size()
        if im.is_item_hovered():
            best, best_d2, best_px = -1, 1e10, None
            for i in range(50):
                pt = p3.plot_to_pixels(xs[i], ys[i], zs[i])
                d2 = (pt[0] - mouse[0]) ** 2 + (pt[1] - mouse[1]) ** 2
                if d2 < best_d2:
                    best, best_d2, best_px = i, d2, pt
            if best >= 0:
                dl.add_line(mouse, best_px, (255, 255, 0, 255), 2.0)
                im.set_tooltip("Mouse: (%.1f, %.1f)\nClosest Point #%d\nPosition: (%.3f, %.3f, %.3f)\n"
                               "Distance: %.1f px" % (mouse[0], mouse[1], best, xs[best], ys[best],
                                                     zs[best], math.sqrt(best_d2)))
        plot = p3.get_current_plot()
        if plot is not None:
            center = (plot_pos[0] + plot_size[0] - 50, plot_pos[1] + plot_size[1] - 50)
            size = 30.0
            dl.add_circle_filled(center, size + 5, (0, 0, 0, 100))
            for axis, col, label in (((1, 0, 0), (200, 50, 50, 255), "X"),
                                     ((0, 1, 0), (50, 200, 50, 255), "Y"),
                                     ((0, 0, 1), (50, 50, 200, 255), "Z")):
                r = plot.rotation * axis
                end = (center[0] + r.x * size, center[1] - r.y * size)
                dl.add_line(center, end, col, 2.0)
                dl.add_circle_filled(end, 4.0, col)
                dl.add_text((end[0] + 8, end[1] - 8), col, label)
        p3.end_plot()


def demo_custom_per_point_style() -> None:
    im.bullet_text("Demonstrates per-point coloring using colormap sampling.")
    im.bullet_text("A different color is sampled for each point.")
    im.bullet_text("All points share the same label for a single legend entry.")
    st = _state("per_point", marker_size=4.0, cmap=p3.COLORMAP_VIRIDIS, torus=None)
    _c, st["marker_size"] = im.slider_float("Marker Size", st["marker_size"], 2.0, 10.0)
    if im.begin_combo("Colormap", p3.get_colormap_name(st["cmap"])):
        for i in range(p3.get_colormap_count()):
            if not p3._gp().colormap_data.is_qual(i):
                if im.selectable(p3.get_colormap_name(i), st["cmap"] == i):
                    st["cmap"] = i
        im.end_combo()
    if st["torus"] is None:
        big_r, small_r = 0.6, 0.2
        data = []
        for torus in range(3):
            z_offset = (2 - torus) * 0.6
            pts = []
            for i in range(20):
                u = i / 20 * 2.0 * math.pi
                for j in range(20):
                    v = j / 20 * 2.0 * math.pi
                    x = (big_r + small_r * math.cos(v)) * math.cos(u)
                    y = (big_r + small_r * math.cos(v)) * math.sin(u)
                    z = small_r * math.sin(v) + z_offset
                    if torus == 0:
                        t = (z - (z_offset - small_r)) / (2.0 * small_r)
                    elif torus == 1:
                        t = (math.cos(v) + 1.0) / 2.0
                    else:
                        t = (math.cos(u) + 1.0) / 2.0
                    pts.append((x, y, z, t))
            data.append(pts)
        st["torus"] = data
    if p3.begin_plot("##PerPointStyle", (-1, 0)):
        p3.setup_axes("X", "Y", "Z")
        p3.setup_axes_limits(-1, 1, -1, 1, -0.5, 1.5)
        labels = ("Height-colored", "Radial-colored", "Angular-colored")
        legend_colors = ((1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0))
        for torus, pts in enumerate(st["torus"]):
            colors = [p3.color_convert_float4_to_u32(p3.sample_colormap(p[3], st["cmap"])) for p in pts]
            spec = Spec(marker=p3.MARKER_CIRCLE, marker_size=st["marker_size"],
                        marker_fill_colors=colors, marker_line_colors=colors)
            p3.plot_scatter(labels[torus], [p[0] for p in pts], [p[1] for p in pts],
                            [p[2] for p in pts], 400, spec)
            spec.marker_fill_colors = spec.marker_line_colors = None
            spec.marker_fill_color = spec.marker_line_color = legend_colors[torus]
            p3.plot_dummy(labels[torus], spec)
        p3.end_plot()


# --------------------------------------------------------------------------- #
# [SECTION] Config / Help
# --------------------------------------------------------------------------- #
def demo_config() -> None:
    im.show_font_selector("Font")
    im.show_style_selector("ImGui Style")
    p3.show_style_selector("ImPlot3D Style")
    p3.show_colormap_selector("ImPlot3D Colormap")
    im.separator()
    if p3.begin_plot("Preview", (-1, 0)):
        for i in range(10):
            ts = [j / 49.0 for j in range(50)]
            radius = 0.3 + i * 0.05
            im.push_id(i)
            p3.plot_line("##Spiral", [radius * math.cos(t * 4 * math.pi) for t in ts],
                         [radius * math.sin(t * 4 * math.pi) for t in ts], [i / 9.0] * 50, 50)
            im.pop_id()
        p3.end_plot()


def demo_help() -> None:
    im.separator_text("ABOUT THIS DEMO:")
    im.bullet_text("The other tabs are demonstrating many aspects of the library.")
    im.separator_text("PROGRAMMER GUIDE:")
    im.bullet_text("See the show_demo_window() code in emtk/implot3d_demo.py. <- you are here!")
    im.separator_text("USER GUIDE:")
    for title, lines in (
        ("Translation", ("Left-click drag to translate.", "If over axis, only that axis will translate.",
                         "If over plane, only that plane will translate.",
                         "If outside plot area, translate in the view plane.")),
        ("Zoom", ("Scroll or middle-click drag to zoom.", "If over axis, only that axis will zoom.",
                  "If over plane, only that plane will zoom.", "If outside plot area, zoom the entire plot.")),
        ("Rotation", ("Right-click drag to rotate.", "To reset rotation, double right-click outside plot area.",
                      "To rotate to plane, double right-click when over the plane.")),
        ("Fit data", ("Double left-click to fit.", "If over axis, fit data to axis.",
                      "If over plane, fit data to plane.", "If outside plot area, fit data to plot.")),
        ("Context Menus", ("Right-click outside plot area to show full context menu.",
                           "Right-click over legend to show legend context menu.",
                           "Right-click over axis to show axis context menu.",
                           "Right-click over plane to show plane context menu.")),
    ):
        im.bullet_text(title)
        im.indent()
        for line in lines:
            im.bullet_text(line)
        im.unindent()
    im.bullet_text("Click legend label icons to show/hide plot items.")


#: ``(tab, header, function)`` in ``ShowAllDemos`` order.
SECTIONS = (
    ("Plots", "Line Plots", demo_line_plots),
    ("Plots", "Scatter Plots", demo_scatter_plots),
    ("Plots", "Triangle Plots", demo_triangle_plots),
    ("Plots", "Quad Plots", demo_quad_plots),
    ("Plots", "Surface Plots", demo_surface_plots),
    ("Plots", "Mesh Plots", demo_mesh_plots),
    ("Plots", "Realtime Plots", demo_realtime_plots),
    ("Plots", "Image Plots", demo_image_plots),
    ("Plots", "Plot Flags", demo_plot_flags),
    ("Plots", "Offset and Stride", demo_offset_and_stride),
    ("Plots", "Legend Options", demo_legend_options),
    ("Plots", "Markers and Text", demo_markers_and_text),
    ("Plots", "NaN Values", demo_nan_values),
    ("Plots", "Per-Index Colors", demo_per_index_colors),
    ("Axes", "Box Scale", demo_box_scale),
    ("Axes", "Box Rotation", demo_box_rotation),
    ("Axes", "Log Scale", demo_log_scale),
    ("Axes", "Symmetric Log Scale", demo_symmetric_log_scale),
    ("Axes", "Tick Labels", demo_tick_labels),
    ("Axes", "Axis Constraints", demo_axis_constraints),
    ("Axes", "Equal Axes", demo_equal_axes),
    ("Axes", "Auto-Fitting Data", demo_auto_fitting_data),
    ("Tools", "Mouse Picking", demo_mouse_picking),
    ("Custom", "Custom Styles", demo_custom_styles),
    ("Custom", "Custom Rendering", demo_custom_rendering),
    ("Custom", "Custom Overlay", demo_custom_overlay),
    ("Custom", "Custom Per-Point Style", demo_custom_per_point_style),
    ("Config", "Config", demo_config),
    ("Help", "Help", demo_help),
)


def show_all_demos() -> None:
    im.text("ImPlot3D says ola! (%s) (%d)" % (p3.IMPLOT3D_VERSION, p3.IMPLOT3D_VERSION_NUM))
    im.spacing()
    if im.begin_tab_bar("ImPlot3DDemoTabs"):
        for tab in ("Plots", "Axes", "Tools", "Custom", "Config", "Help"):
            if im.begin_tab_item(tab):
                for section_tab, title, fn in SECTIONS:
                    if section_tab != tab:
                        continue
                    if tab in ("Config", "Help"):
                        fn()
                    elif im.tree_node_ex(title):
                        fn()
                        im.tree_pop()
                im.end_tab_item()
        im.end_tab_bar()


def show_demo_window() -> None:
    st = _state("window", metrics=False, style_editor=False, about=False)
    if st["metrics"]:
        p3.show_metrics_window()
    if st["style_editor"]:
        im.begin("Style Editor (ImPlot3D)")
        show_style_editor()
        im.end()
    if st["about"]:
        show_about_window()
    im.begin("ImPlot3D Demo")
    if im.begin_menu_bar():
        if im.begin_menu("Tools"):
            if im.menu_item("Metrics", "", st["metrics"]):
                st["metrics"] = not st["metrics"]
            if im.menu_item("Style Editor", "", st["style_editor"]):
                st["style_editor"] = not st["style_editor"]
            if im.menu_item("About ImPlot3D", "", st["about"]):
                st["about"] = not st["about"]
            im.end_menu()
        im.end_menu_bar()
    show_all_demos()
    im.end()


# --------------------------------------------------------------------------- #
# [SECTION] Style Editor
# --------------------------------------------------------------------------- #
def show_style_editor(ref=None) -> None:
    gp = p3._gp()
    style = p3.get_style()
    st = _state("style_editor", ref_saved=None, edit=False, custom=None, name="MyColormap", qual=True)
    if st["ref_saved"] is None:
        st["ref_saved"] = style.copy()
    if ref is None:
        ref = st["ref_saved"]
    if p3.show_style_selector("Colors##Selector"):
        st["ref_saved"] = style.copy()
    if im.button("Save Ref"):
        st["ref_saved"] = style.copy()
    im.same_line()
    if im.button("Revert Ref"):
        gp.style = ref.copy()
        style = gp.style
    im.same_line()
    help_marker("Save/Revert in local non-persistent storage. Default Colors definition are not affected.")
    im.separator()
    if im.begin_tab_bar("##Tabs"):
        if im.begin_tab_item("Variables"):
            im.text("Item Styling")
            _c, style.line_weight = im.slider_float("LineWeight", style.line_weight, 0.0, 5.0, "%.1f")
            _c, style.marker_size = im.slider_float("MarkerSize", style.marker_size, 2.0, 10.0, "%.1f")
            _c, style.fill_alpha = im.slider_float("FillAlpha", style.fill_alpha, 0.0, 1.0, "%.2f")
            im.text("Plot Styling")
            for name, attr, hi in (("PlotDefaultSize", "plot_default_size", 1000), ("PlotMinSize", "plot_min_size", 300),
                                   ("PlotPadding", "plot_padding", 20.0), ("LabelPadding", "label_padding", 20.0)):
                _c, value = im.slider_float2(name, getattr(style, attr), 0.0, hi, "%.0f")
                setattr(style, attr, value)
            _c, style.view_scale_factor = im.slider_float("ViewScaleFactor", style.view_scale_factor, 0.1, 2.0, "%.2f")
            im.text("Legend Styling")
            for name, attr, hi in (("LegendPadding", "legend_padding", 20.0),
                                   ("LegendInnerPadding", "legend_inner_padding", 10.0),
                                   ("LegendSpacing", "legend_spacing", 5.0)):
                _c, value = im.slider_float2(name, getattr(style, attr), 0.0, hi, "%.0f")
                setattr(style, attr, value)
            im.end_tab_item()
        if im.begin_tab_item("Colors"):
            for i in range(p3.COL_COUNT):
                name = p3.get_style_color_name(i)
                im.push_id(i)
                is_auto = p3.is_color_auto(style.colors[i])
                im.begin_disabled(is_auto)
                if im.button("Auto"):
                    style.colors[i] = p3.IMPLOT3D_AUTO_COL
                im.end_disabled()
                im.same_line()
                shown = p3.get_style_color_vec4(i)
                changed, col = im.color_edit4("##Color", shown)
                if changed:
                    style.colors[i] = tuple(float(v) for v in col)
                if style.colors[i] != ref.colors[i]:
                    im.same_line()
                    if im.button("Save"):
                        ref.colors[i] = style.colors[i]
                    im.same_line()
                    if im.button("Revert"):
                        style.colors[i] = ref.colors[i]
                im.same_line()
                im.text_unformatted(name)
                im.pop_id()
            im.end_tab_item()
        if im.begin_tab_item("Colormaps"):
            _c, st["edit"] = im.checkbox("Edit Mode", st["edit"])
            im.separator()
            data = gp.colormap_data
            for i in range(data.count):
                im.push_id(i)
                if im.button(p3.get_colormap_name(i), (100, 0)):
                    gp.style.colormap = i
                    p3.bust_item_cache()
                im.same_line()
                if st["edit"]:
                    for c in range(data.get_key_count(i)):
                        im.push_id(c)
                        changed, col = im.color_edit4("", p3.color_convert_u32_to_float4(data.get_key_color(i, c)))
                        if changed:
                            data.set_key_color(i, c, tuple(float(v) for v in col))
                            p3.bust_item_cache()
                        if (c + 1) % 12 != 0 and c != data.get_key_count(i) - 1:
                            im.same_line()
                        im.pop_id()
                elif p3.colormap_button("##", (-1, 0), i):
                    st["edit"] = True
                im.pop_id()
            if st["custom"] is None:
                st["custom"] = [(1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0)]
            im.separator()
            if im.button("+", (46, 0)):
                st["custom"].append((0.0, 0.0, 0.0, 1.0))
            im.same_line()
            if im.button("-", (46, 0)) and len(st["custom"]) > 2:
                st["custom"].pop()
            _c, st["name"] = im.input_text("##Name", st["name"])
            _c, st["qual"] = im.checkbox("Qualitative", st["qual"])
            if im.button("Add", (100, 0)) and data.get_index(st["name"]) == -1:
                p3.add_colormap(st["name"], st["custom"], st["qual"])
            for c in range(len(st["custom"])):
                im.push_id(c)
                _c, col = im.color_edit4("##Col1", st["custom"][c])
                st["custom"][c] = tuple(float(v) for v in col)
                if (c + 1) % 12 != 0:
                    im.same_line()
                im.pop_id()
            im.new_line()
            im.end_tab_item()
        im.end_tab_bar()


def show_about_window() -> None:
    im.begin("About ImPlot3D")
    im.text("ImPlot3D %s (%d)" % (p3.IMPLOT3D_VERSION, p3.IMPLOT3D_VERSION_NUM))
    im.text_link_open_url("Homepage", "https://github.com/brenocq/implot3d")
    im.separator()
    im.text("(c) 2024-2025 Breno Cunha Queiroz")
    im.text("Developed by Breno Cunha Queiroz and all ImPlot3D contributors.")
    im.text("ImPlot3D is licensed under the MIT License.")
    im.text("Ported onto emtk; see CREDITS.md.")
    im.end()
