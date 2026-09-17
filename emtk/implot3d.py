"""``emtk.implot3d`` -- ImPlot3D, ported onto emtk.

A line-by-line port of `ImPlot3D <https://github.com/brenocq/implot3d>`_
(Breno Cunha Queiroz, MIT) -- ``implot3d.h``, ``implot3d_internal.h`` and
``implot3d.cpp`` here, ``implot3d_items.cpp`` in :mod:`emtk.implot3d_items`,
the bundled meshes in :mod:`emtk.implot3d_meshes` and the demo in
:mod:`emtk.implot3d_demo`. The call shape is the reference's, snake-cased::

    if implot3d.begin_plot("Line Plots"):
        implot3d.setup_axes("x", "y", "z")
        implot3d.plot_line("f(x)", xs, ys, zs)
        implot3d.end_plot()

and every C++ spelling is bound as well (``ImPlot3DFlags_NoTitle``,
``ImAxis3D_X``, ``ImPlot3DMarker_Circle`` ...), so a ported line can keep the
reference's constants.

How it draws
------------
Exactly as the reference does, on emtk's painter instead of an
``ImDrawList``. The box (background faces, grid, ticks, labels) is drawn when
setup locks; every item -- fills, lines as two-triangle strips, markers as fans
-- is projected through the plot's rotation into screen triangles that carry a
depth (the rotated *plot-space* centroid, as ``GetPointDepth`` computes it),
collected in a :class:`DrawList3D`, sorted back to front and emitted at
``end_plot`` through :meth:`~emtk.painter.Painter.fill_triangle`, and the two
optional operations :func:`~emtk.painter.gradient_triangle` (per-vertex colour,
for colormapped surfaces and Gouraud meshes) and
:func:`~emtk.painter.image_triangle` (``PlotImage``). A painter without those
still draws everything: gradients are subdivided, images become their tint.

What differs from the reference, and why
----------------------------------------
* **Pure Python, no NumPy** -- emtk has no dependencies. Projection is one
  3x3 matrix built per item from the quaternion (the same linear map the
  reference's ``q * v`` formula applies) rather than a quaternion product per
  vertex.
* **Stride counts elements, not bytes.** A Python sequence has no byte layout;
  ``Spec(stride=33)`` steps 33 elements, which is what
  ``sizeof(double) * 33`` meant.
* **Colours** are accepted as ImGui floats ``(r, g, b, a)`` in 0..1, as
  emtk bytes ``(r, g, b, a)`` in 0..255 (all ints), or as packed ``ImU32``.
* **Popups** are emtk's: drawn in the layout after the plot, not floating,
  and keyed per plot (the reference's names collide between two plots in one
  window).
* **Formatters and transforms** are Python callables returning the value:
  ``formatter(value, user_data) -> str``, ``forward(value, user_data) ->
  float``.
"""
from __future__ import annotations

import math
import re

from . import im_core as _core
from . import painter as _painter
from .painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER

IMPLOT3D_VERSION = "0.5 WIP"
IMPLOT3D_VERSION_NUM = 500
IMPLOT3D_AUTO = -1
IMPLOT3D_AUTO_COL = (0.0, 0.0, 0.0, -1.0)
IMPLOT3D_LABEL_FORMAT = "%g"
IMPLOT3D_LABEL_MAX_SIZE = 32

__all__ = ["IMPLOT3D_VERSION", "IMPLOT3D_VERSION_NUM", "IMPLOT3D_AUTO",
           "IMPLOT3D_AUTO_COL"]

# --------------------------------------------------------------------------- #
# [SECTION] Flags & Enumerations
#
# Data, not typed twice: each family is listed once with its C++ prefix and
# bound under both spellings -- ``FLAGS_NO_TITLE`` and ``ImPlot3DFlags_NoTitle``.
# --------------------------------------------------------------------------- #
_ENUMS = (
    ("ImPlot3DProp_", "PROP_", [
        ("LineColor", 0), ("LineColors", 1), ("LineWeight", 2), ("FillColor", 3),
        ("FillColors", 4), ("FillAlpha", 5), ("Marker", 6), ("MarkerSize", 7),
        ("MarkerSizes", 8), ("MarkerLineColor", 9), ("MarkerLineColors", 10),
        ("MarkerFillColor", 11), ("MarkerFillColors", 12), ("Offset", 13),
        ("Stride", 14), ("Flags", 15)]),
    ("ImPlot3DFlags_", "FLAGS_", [
        ("None", 0), ("NoTitle", 1 << 0), ("NoLegend", 1 << 1), ("NoMouseText", 1 << 2),
        ("NoClip", 1 << 3), ("NoMenus", 1 << 4), ("Equal", 1 << 5), ("NoRotate", 1 << 6),
        ("NoPan", 1 << 7), ("NoZoom", 1 << 8), ("NoInputs", 1 << 9),
        ("CanvasOnly", (1 << 0) | (1 << 1) | (1 << 2))]),
    ("ImPlot3DCond_", "COND_", [("None", 0), ("Always", 1), ("Once", 2)]),
    ("ImPlot3DCol_", "COL_", [
        ("TitleText", 0), ("InlayText", 1), ("FrameBg", 2), ("PlotBg", 3),
        ("PlotBorder", 4), ("LegendBg", 5), ("LegendBorder", 6), ("LegendText", 7),
        ("AxisText", 8), ("AxisGrid", 9), ("AxisTick", 10), ("AxisBg", 11),
        ("AxisBgHovered", 12), ("AxisBgActive", 13), ("COUNT", 14)]),
    ("ImPlot3DStyleVar_", "STYLEVAR_", [
        ("LineWeight", 0), ("Marker", 1), ("MarkerSize", 2), ("FillAlpha", 3),
        ("PlotDefaultSize", 4), ("PlotMinSize", 5), ("PlotPadding", 6),
        ("LabelPadding", 7), ("ViewScaleFactor", 8), ("LegendPadding", 9),
        ("LegendInnerPadding", 10), ("LegendSpacing", 11), ("COUNT", 12)]),
    ("ImPlot3DMarker_", "MARKER_", [
        ("None", -2), ("Auto", -1), ("Circle", 0), ("Square", 1), ("Diamond", 2),
        ("Up", 3), ("Down", 4), ("Left", 5), ("Right", 6), ("Cross", 7), ("Plus", 8),
        ("Asterisk", 9), ("COUNT", 10), ("Invalid", -3)]),
    ("ImPlot3DItemFlags_", "ITEM_FLAGS_", [("None", 0), ("NoLegend", 1), ("NoFit", 2)]),
    ("ImPlot3DScatterFlags_", "SCATTER_FLAGS_", [("None", 0), ("NoLegend", 1), ("NoFit", 2)]),
    ("ImPlot3DLineFlags_", "LINE_FLAGS_", [
        ("None", 0), ("NoLegend", 1), ("NoFit", 2), ("Segments", 1 << 10),
        ("Loop", 1 << 11), ("SkipNaN", 1 << 12)]),
    ("ImPlot3DTriangleFlags_", "TRIANGLE_FLAGS_", [
        ("None", 0), ("NoLegend", 1), ("NoFit", 2), ("NoLines", 1 << 10),
        ("NoFill", 1 << 11), ("NoMarkers", 1 << 12)]),
    ("ImPlot3DQuadFlags_", "QUAD_FLAGS_", [
        ("None", 0), ("NoLegend", 1), ("NoFit", 2), ("NoLines", 1 << 10),
        ("NoFill", 1 << 11), ("NoMarkers", 1 << 12)]),
    ("ImPlot3DSurfaceFlags_", "SURFACE_FLAGS_", [
        ("None", 0), ("NoLegend", 1), ("NoFit", 2), ("NoLines", 1 << 10),
        ("NoFill", 1 << 11), ("NoMarkers", 1 << 12)]),
    ("ImPlot3DMeshFlags_", "MESH_FLAGS_", [
        ("None", 0), ("NoLegend", 1), ("NoFit", 2), ("NoLines", 1 << 10),
        ("NoFill", 1 << 11), ("NoMarkers", 1 << 12)]),
    ("ImPlot3DImageFlags_", "IMAGE_FLAGS_", [("None", 0), ("NoLegend", 1), ("NoFit", 2)]),
    ("ImPlot3DDummyFlags_", "DUMMY_FLAGS_", [("None", 0)]),
    ("ImPlot3DLegendFlags_", "LEGEND_FLAGS_", [
        ("None", 0), ("NoButtons", 1 << 0), ("NoHighlightItem", 1 << 1),
        ("Horizontal", 1 << 2)]),
    ("ImPlot3DLocation_", "LOCATION_", [
        ("Center", 0), ("North", 1), ("South", 2), ("West", 4), ("East", 8),
        ("NorthWest", 5), ("NorthEast", 9), ("SouthWest", 6), ("SouthEast", 10)]),
    ("ImPlot3DAxisFlags_", "AXIS_FLAGS_", [
        ("None", 0), ("NoLabel", 1 << 0), ("NoGridLines", 1 << 1), ("NoTickMarks", 1 << 2),
        ("NoTickLabels", 1 << 3), ("LockMin", 1 << 4), ("LockMax", 1 << 5),
        ("AutoFit", 1 << 6), ("Invert", 1 << 7), ("PanStretch", 1 << 8),
        ("Lock", (1 << 4) | (1 << 5)),
        ("NoDecorations", (1 << 0) | (1 << 1) | (1 << 3))]),
    ("ImAxis3D_", "AXIS_", [("X", 0), ("Y", 1), ("Z", 2), ("COUNT", 3)]),
    ("ImPlane3D_", "PLANE_", [("YZ", 0), ("XZ", 1), ("XY", 2), ("COUNT", 3)]),
    ("ImPlot3DScale_", "SCALE_", [("Linear", 0), ("Log10", 1), ("SymLog", 2)]),
    ("ImPlot3DColormap_", "COLORMAP_", [
        ("Deep", 0), ("Dark", 1), ("Pastel", 2), ("Paired", 3), ("Viridis", 4),
        ("Plasma", 5), ("Hot", 6), ("Cool", 7), ("Pink", 8), ("Jet", 9),
        ("Twilight", 10), ("RdBu", 11), ("BrBG", 12), ("PiYG", 13), ("Spectral", 14),
        ("Greys", 15)]),
)


def _upper_snake(name: str) -> str:
    if name.isupper():
        return name
    name = name.replace("NaN", "Nan")
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", name)
    return name.upper()


for _cpp, _py, _members in _ENUMS:
    for _name, _value in _members:
        globals()[_cpp + _name] = _value
        globals()[_py + _upper_snake(_name)] = _value
        __all__ += [_cpp + _name, _py + _upper_snake(_name)]
del _cpp, _py, _members, _name, _value
#: ``emtk.implot``'s spelling of the same scale.
SCALE_SYMLOG = SCALE_SYM_LOG
__all__.append("SCALE_SYMLOG")


# --------------------------------------------------------------------------- #
# [SECTION] Generic Helpers (implot3d_internal.h)
# --------------------------------------------------------------------------- #
DBL_MAX = 1.7976931348623157e308
DBL_MIN = 2.2250738585072014e-308
DBL_EPSILON = 2.220446049250313e-16
FLT_MIN = 1.1754943508222875e-38
HUGE_VAL = math.inf


def im_has_flag(flag_set: int, flag: int) -> bool:
    """``ImHasFlag``: every bit of *flag* is set."""
    return (flag_set & flag) == flag


def im_flip_flag(flag_set: int, flag: int) -> int:
    """``ImFlipFlag``, returning the new set (Python cannot write through)."""
    return flag_set & ~flag if im_has_flag(flag_set, flag) else flag_set | flag


def im_remap01(x, x0, x1):
    return (x - x0) / (x1 - x0) if (x1 - x0) else 0.0


def im_pos_mod(left: int, right: int) -> int:
    return (left % right + right) % right


def im_nan(v: float) -> bool:
    return v != v


def im_nan_or_inf(v: float) -> bool:
    return not (-DBL_MAX <= v <= DBL_MAX)


def im_constrain_nan(v: float) -> float:
    return 0.0 if v != v else v


def im_constrain_inf(v: float) -> float:
    max_val = DBL_MAX * 0.5
    return max_val if v >= max_val else -max_val if v <= -max_val else v


def im_almost_equal(v1: float, v2: float, ulp: int = 2) -> bool:
    return (abs(v1 - v2) < DBL_EPSILON * abs(v1 + v2) * ulp
            or abs(v1 - v2) < DBL_MIN)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# -- colours: ImU32 (A << 24 | B << 16 | G << 8 | R) and ImVec4 floats -------- #
def IM_COL32(r: int, g: int, b: int, a: int = 255) -> int:  # noqa: N802
    return ((int(a) & 255) << 24) | ((int(b) & 255) << 16) | ((int(g) & 255) << 8) | (int(r) & 255)


IM_COL32_WHITE = IM_COL32(255, 255, 255, 255)
IM_COL32_BLACK = IM_COL32(0, 0, 0, 255)
IM_COL32_BLACK_TRANS = IM_COL32(0, 0, 0, 0)
IM_COL32_A_MASK = 0xFF000000


def _sat8(f: float) -> int:
    return int(_clamp(f, 0.0, 1.0) * 255.0 + 0.5)


def color_convert_float4_to_u32(c) -> int:
    return IM_COL32(_sat8(c[0]), _sat8(c[1]), _sat8(c[2]), _sat8(c[3]))


def color_convert_u32_to_float4(u: int):
    return ((u & 255) / 255.0, ((u >> 8) & 255) / 255.0,
            ((u >> 16) & 255) / 255.0, ((u >> 24) & 255) / 255.0)


def im_alpha_u32(col: int, alpha: float) -> int:
    return col & ~(int((1.0 - alpha) * 255) << 24) & 0xFFFFFFFF


def im_mix_u32(a: int, b: int, s: int) -> int:
    """``ImMixU32``: *a* and *b* mixed by ``s / 256``, the 32-bit path."""
    af, bf = 256 - s, s
    al, ah = a & 0x00FF00FF, (a & 0xFF00FF00) >> 8
    bl, bh = b & 0x00FF00FF, (b & 0xFF00FF00) >> 8
    ml = (al * af + bl * bf) & 0xFFFFFFFF
    mh = (ah * af + bh * bf) & 0xFFFFFFFF
    return ((mh & 0xFF00FF00) | ((ml & 0xFF00FF00) >> 8)) & 0xFFFFFFFF


def to_vec4(colour):
    """Any accepted colour as an ``ImVec4`` float tuple.

    ``None`` is ``IMPLOT3D_AUTO_COL``; an ``int`` is a packed ``ImU32``; a
    tuple with any float in it is 0..1 (ImGui), one of ints is 0..255 (emtk).
    """
    if colour is None:
        return IMPLOT3D_AUTO_COL
    if isinstance(colour, int):
        return color_convert_u32_to_float4(colour)
    vals = tuple(colour)
    if any(isinstance(v, float) for v in vals):
        vals = tuple(float(v) for v in vals)
        return vals if len(vals) == 4 else vals[:3] + (1.0,)
    vals = tuple(int(v) / 255.0 for v in vals)
    return vals if len(vals) == 4 else vals[:3] + (1.0,)


def to_u32(colour) -> int:
    """Any accepted colour as a packed ``ImU32``."""
    if isinstance(colour, int):
        return colour & 0xFFFFFFFF
    return color_convert_float4_to_u32(to_vec4(colour))


def u32_to_rgba(u: int) -> tuple[int, int, int, int]:
    """A packed colour as the painter's ``(r, g, b, a)`` bytes."""
    return (u & 255, (u >> 8) & 255, (u >> 16) & 255, (u >> 24) & 255)


def _vec4_mul(a, b):
    return (a[0] * b[0], a[1] * b[1], a[2] * b[2], a[3] * b[3])


def _vec4_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2], a[3] + b[3])


__all__ += ["IM_COL32", "to_vec4", "to_u32", "u32_to_rgba",
            "color_convert_float4_to_u32", "color_convert_u32_to_float4"]


# --------------------------------------------------------------------------- #
# [SECTION] ImPlot3DPoint, Ray, Plane, Box, Range, Quat
# --------------------------------------------------------------------------- #
class Point:
    """``ImPlot3DPoint``: a 3-D vector of doubles."""

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __getitem__(self, i: int) -> float:
        return (self.x, self.y, self.z)[i]

    def __setitem__(self, i: int, v: float) -> None:
        setattr(self, "xyz"[i], float(v))

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __len__(self) -> int:
        return 3

    def __repr__(self) -> str:
        return f"Point({self.x!r}, {self.y!r}, {self.z!r})"

    def __mul__(self, rhs):
        if isinstance(rhs, Point):
            return Point(self.x * rhs.x, self.y * rhs.y, self.z * rhs.z)
        return Point(self.x * rhs, self.y * rhs, self.z * rhs)

    __rmul__ = __mul__

    def __truediv__(self, rhs):
        if isinstance(rhs, Point):
            return Point(self.x / rhs.x, self.y / rhs.y, self.z / rhs.z)
        return Point(self.x / rhs, self.y / rhs, self.z / rhs)

    def __add__(self, rhs):
        return Point(self.x + rhs.x, self.y + rhs.y, self.z + rhs.z)

    def __sub__(self, rhs):
        return Point(self.x - rhs.x, self.y - rhs.y, self.z - rhs.z)

    def __neg__(self):
        return Point(-self.x, -self.y, -self.z)

    def __eq__(self, rhs) -> bool:
        return (isinstance(rhs, Point) and self.x == rhs.x and self.y == rhs.y
                and self.z == rhs.z)

    def __ne__(self, rhs) -> bool:
        return not self == rhs

    __hash__ = None

    def dot(self, rhs) -> float:
        return self.x * rhs.x + self.y * rhs.y + self.z * rhs.z

    def cross(self, rhs) -> "Point":
        return Point(self.y * rhs.z - self.z * rhs.y, self.z * rhs.x - self.x * rhs.z,
                     self.x * rhs.y - self.y * rhs.x)

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalize(self) -> None:
        n = self.length()
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n

    def normalized(self) -> "Point":
        n = self.length()
        return Point(self.x / n, self.y / n, self.z / n)

    def is_nan(self) -> bool:
        return im_nan(self.x) or im_nan(self.y) or im_nan(self.z)

    Dot, Cross, Length, LengthSquared = dot, cross, length, length_squared
    Normalize, Normalized, IsNaN = normalize, normalized, is_nan


def _point(p) -> Point:
    return p if isinstance(p, Point) else Point(*p)


class Ray:
    """``ImPlot3DRay``: an origin and a (not necessarily unit) direction."""

    __slots__ = ("origin", "direction")

    def __init__(self, origin=None, direction=None) -> None:
        self.origin = _point(origin) if origin is not None else Point()
        self.direction = _point(direction) if direction is not None else Point()

    Origin = property(lambda s: s.origin)
    Direction = property(lambda s: s.direction)


class Plane:
    """``ImPlot3DPlane``: a point on the plane and its normal."""

    __slots__ = ("point", "normal")

    def __init__(self, point=None, normal=None) -> None:
        self.point = _point(point) if point is not None else Point()
        self.normal = _point(normal) if normal is not None else Point()


class Box:
    """``ImPlot3DBox``: an axis-aligned box."""

    __slots__ = ("min", "max")

    def __init__(self, bmin=None, bmax=None) -> None:
        self.min = _point(bmin) if bmin is not None else Point()
        self.max = _point(bmax) if bmax is not None else Point()

    def expand(self, p) -> None:
        self.min = Point(min(self.min.x, p[0]), min(self.min.y, p[1]), min(self.min.z, p[2]))
        self.max = Point(max(self.max.x, p[0]), max(self.max.y, p[1]), max(self.max.z, p[2]))

    def contains(self, p) -> bool:
        return (self.min.x <= p[0] <= self.max.x and self.min.y <= p[1] <= self.max.y
                and self.min.z <= p[2] <= self.max.z)

    def clip_line_segment(self, p0, p1):
        """Liang-Barsky. Returns ``(visible, p0_clipped, p1_clipped)`` as tuples."""
        return _clip_segment(self.min.x, self.min.y, self.min.z, self.max.x,
                             self.max.y, self.max.z, tuple(p0), tuple(p1))

    Expand, Contains, ClipLineSegment = expand, contains, clip_line_segment


def _clip_segment(xmin, ymin, zmin, xmax, ymax, zmax, p0, p1):
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    if (xmin <= x0 <= xmax and ymin <= y0 <= ymax and zmin <= z0 <= zmax
            and xmin <= x1 <= xmax and ymin <= y1 <= ymax and zmin <= z1 <= zmax):
        return True, p0, p1
    t0, t1 = 0.0, 1.0
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin),
                 (dy, ymax - y0), (-dz, z0 - zmin), (dz, zmax - z0)):
        if p == 0.0:
            if q < 0.0:
                return False, p0, p1
            continue
        r = q / p
        if p < 0.0:
            if r > t1:
                return False, p0, p1
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return False, p0, p1
            if r < t1:
                t1 = r
    return (True, (x0 + dx * t0, y0 + dy * t0, z0 + dz * t0),
            (x0 + dx * t1, y0 + dy * t1, z0 + dz * t1))


class Range:
    """``ImPlot3DRange``."""

    __slots__ = ("min", "max")

    def __init__(self, vmin: float = 0.0, vmax: float = 0.0) -> None:
        self.min, self.max = float(vmin), float(vmax)

    def expand(self, v: float) -> None:
        self.min, self.max = min(self.min, v), max(self.max, v)

    def contains(self, v: float) -> bool:
        return self.min <= v <= self.max

    def size(self) -> float:
        return self.max - self.min

    Expand, Contains, Size = expand, contains, size

    def __repr__(self) -> str:
        return f"Range({self.min!r}, {self.max!r})"


class Quat:
    """``ImPlot3DQuat``: ``(x, y, z, w)``, identity by default.

    ``Quat.from_angle_axis(angle, axis)`` is the C++ ``ImPlot3DQuat(angle,
    axis)`` constructor, which Python cannot overload on.
    """

    __slots__ = ("x", "y", "z", "w")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, w: float = 1.0) -> None:
        self.x, self.y, self.z, self.w = float(x), float(y), float(z), float(w)

    def __repr__(self) -> str:
        return f"Quat({self.x!r}, {self.y!r}, {self.z!r}, {self.w!r})"

    def __iter__(self):
        return iter((self.x, self.y, self.z, self.w))

    @classmethod
    def from_angle_axis(cls, angle: float, axis) -> "Quat":
        half = angle * 0.5
        s = math.sin(half)
        return cls(s * axis[0], s * axis[1], s * axis[2], math.cos(half))

    @staticmethod
    def from_two_vectors(v0, v1) -> "Quat":
        v0, v1 = _point(v0), _point(v1)
        normalized_dot = v0.dot(v1) / (v0.length() * v1.length())
        epsilon = 1e-6
        if abs(normalized_dot - 1.0) < epsilon:
            return Quat(0.0, 0.0, 0.0, 1.0)
        if abs(normalized_dot + 1.0) < epsilon:
            axis = (Point(-v0.y, v0.x, 0.0) if abs(v0.x) > abs(v0.z)
                    else Point(0.0, -v0.z, v0.y))
            axis.normalize()
            return Quat(axis.x, axis.y, axis.z, 0.0)
        axis = v0.cross(v1)
        axis.normalize()
        half = math.acos(normalized_dot) * 0.5
        s = math.sin(half)
        return Quat(s * axis.x, s * axis.y, s * axis.z, math.cos(half))

    @staticmethod
    def from_el_az(elevation: float, azimuth: float) -> "Quat":
        azimuth_quat = Quat.from_angle_axis(azimuth, (0.0, 0.0, 1.0))
        elevation_quat = Quat.from_angle_axis(elevation, (1.0, 0.0, 0.0))
        zero_quat = Quat.from_angle_axis(-math.pi / 2, (1.0, 0.0, 0.0))
        return elevation_quat * zero_quat * azimuth_quat

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w)

    def normalized(self) -> "Quat":
        n = self.length()
        return Quat(self.x / n, self.y / n, self.z / n, self.w / n)

    def conjugate(self) -> "Quat":
        return Quat(-self.x, -self.y, -self.z, self.w)

    def inverse(self) -> "Quat":
        l2 = self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w
        return Quat(-self.x / l2, -self.y / l2, -self.z / l2, self.w / l2)

    def normalize(self) -> "Quat":
        n = self.length()
        self.x, self.y, self.z, self.w = self.x / n, self.y / n, self.z / n, self.w / n
        return self

    def __mul__(self, rhs):
        if isinstance(rhs, Quat):
            w, x, y, z = self.w, self.x, self.y, self.z
            return Quat(w * rhs.x + x * rhs.w + y * rhs.z - z * rhs.y,
                        w * rhs.y - x * rhs.z + y * rhs.w + z * rhs.x,
                        w * rhs.z + x * rhs.y - y * rhs.x + z * rhs.w,
                        w * rhs.w - x * rhs.x - y * rhs.y - z * rhs.z)
        # rotate a point: p + 2w (qv x p) + 2 qv x (qv x p)
        px, py, pz = rhs[0], rhs[1], rhs[2]
        qx, qy, qz, w = self.x, self.y, self.z, self.w
        ux, uy, uz = qy * pz - qz * py, qz * px - qx * pz, qx * py - qy * px
        uux, uuy, uuz = qy * uz - qz * uy, qz * ux - qx * uz, qx * uy - qy * ux
        return Point(px + ux * w * 2.0 + uux * 2.0, py + uy * w * 2.0 + uuy * 2.0,
                     pz + uz * w * 2.0 + uuz * 2.0)

    def __eq__(self, rhs) -> bool:
        return (isinstance(rhs, Quat) and self.x == rhs.x and self.y == rhs.y
                and self.z == rhs.z and self.w == rhs.w)

    __hash__ = None

    def dot(self, rhs: "Quat") -> float:
        return self.x * rhs.x + self.y * rhs.y + self.z * rhs.z + self.w * rhs.w

    @staticmethod
    def slerp(q1: "Quat", q2: "Quat", t: float) -> "Quat":
        t = _clamp(t, 0.0, 1.0)
        dot = q1.x * q2.x + q1.y * q2.y + q1.z * q2.z + q1.w * q2.w
        q2_ = q2
        if dot < 0.0:
            q2_ = Quat(-q2.x, -q2.y, -q2.z, -q2.w)
            dot = -dot
        if dot > 0.9995:
            return Quat(q1.x + t * (q2_.x - q1.x), q1.y + t * (q2_.y - q1.y),
                        q1.z + t * (q2_.z - q1.z), q1.w + t * (q2_.w - q1.w)).normalized()
        theta_0 = math.acos(dot)
        theta = theta_0 * t
        sin_theta, sin_theta_0 = math.sin(theta), math.sin(theta_0)
        s1 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s2 = sin_theta / sin_theta_0
        return Quat(s1 * q1.x + s2 * q2_.x, s1 * q1.y + s2 * q2_.y,
                    s1 * q1.z + s2 * q2_.z, s1 * q1.w + s2 * q2_.w)

    def matrix(self):
        """The 3x3 matrix of ``q * v`` -- the same linear map, row-major.

        ``v + 2w (qv x v) + 2 qv x (qv x v)`` is linear in ``v`` for *any*
        ``q`` (unit or not), so ``I + 2w[qv]x + 2(qv qv^T - |qv|^2 I)`` gives
        the reference's rotated point to rounding, at a third of the cost.
        """
        x, y, z, w = self.x, self.y, self.z, self.w
        n2 = x * x + y * y + z * z
        return ((1.0 + 2.0 * (x * x - n2), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)),
                (2.0 * (x * y + w * z), 1.0 + 2.0 * (y * y - n2), 2.0 * (y * z - w * x)),
                (2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 + 2.0 * (z * z - n2)))

    FromTwoVectors, FromElAz, Slerp = from_two_vectors, from_el_az, slerp
    Length, Normalized, Conjugate, Inverse = length, normalized, conjugate, inverse
    Normalize, Dot = normalize, dot


__all__ += ["Point", "Ray", "Plane", "Box", "Range", "Quat"]


# --------------------------------------------------------------------------- #
# [SECTION] Specs API
# --------------------------------------------------------------------------- #
_SPEC_FIELDS = (
    ("line_color", "LineColor", IMPLOT3D_AUTO_COL), ("line_colors", "LineColors", None),
    ("line_weight", "LineWeight", 1.0), ("fill_color", "FillColor", IMPLOT3D_AUTO_COL),
    ("fill_colors", "FillColors", None), ("fill_alpha", "FillAlpha", float(IMPLOT3D_AUTO)),
    ("marker", "Marker", -1), ("marker_size", "MarkerSize", float(IMPLOT3D_AUTO)),
    ("marker_sizes", "MarkerSizes", None),
    ("marker_line_color", "MarkerLineColor", IMPLOT3D_AUTO_COL),
    ("marker_line_colors", "MarkerLineColors", None),
    ("marker_fill_color", "MarkerFillColor", IMPLOT3D_AUTO_COL),
    ("marker_fill_colors", "MarkerFillColors", None),
    ("offset", "Offset", 0), ("stride", "Stride", IMPLOT3D_AUTO), ("flags", "Flags", 0),
)
#: ``ImPlot3DProp_`` value -> field, in enum order.
_PROP_FIELD = {i: f[0] for i, f in enumerate(_SPEC_FIELDS)}
_CPP_FIELD = {f[1]: f[0] for f in _SPEC_FIELDS}
_COLOUR_FIELDS = {"line_color", "fill_color", "marker_line_color", "marker_fill_color"}


class Spec:
    """``ImPlot3DSpec``: how one item is drawn.

    Build it the three ways the reference allows::

        spec = Spec(); spec.line_color = (1.0, 0.0, 0.0, 1.0)
        Spec(PROP_LINE_COLOR, (1.0, 0.0, 0.0, 1.0), PROP_MARKER, MARKER_CIRCLE)
        Spec(line_weight=2.0, flags=LINE_FLAGS_SEGMENTS)

    The C++ field names (``spec.LineColor``) read and write the same fields.
    """

    __slots__ = tuple(f[0] for f in _SPEC_FIELDS)

    def __init__(self, *props, **fields) -> None:
        for name, _cpp, default in _SPEC_FIELDS:
            object.__setattr__(self, name, default)
        if len(props) == 1 and isinstance(props[0], (list, tuple, dict)):
            props = props[0]
        if isinstance(props, dict):
            props = [v for kv in props.items() for v in kv]
        if len(props) % 2:
            raise ValueError("Spec(...) takes (ImPlot3DProp, value) pairs")
        for i in range(0, len(props), 2):
            self.set_prop(props[i], props[i + 1])
        for name, value in fields.items():
            setattr(self, name, value)

    def set_prop(self, prop, value, *more) -> "Spec":
        """``SetProp``: one or more ``(prop, value)`` pairs, in any order."""
        setattr(self, _PROP_FIELD[int(prop)], value)
        if more:
            self.set_prop(*more)
        return self

    SetProp = set_prop

    def __setattr__(self, name, value) -> None:
        name = _CPP_FIELD.get(name, name)
        if name in _COLOUR_FIELDS:
            value = to_vec4(value)
        object.__setattr__(self, name, value)

    def __getattr__(self, name):
        if name in _CPP_FIELD:
            return object.__getattribute__(self, _CPP_FIELD[name])
        raise AttributeError(name)

    def copy(self) -> "Spec":
        out = Spec()
        for name, _cpp, _d in _SPEC_FIELDS:
            object.__setattr__(out, name, getattr(self, name))
        return out


def as_spec(spec) -> Spec:
    """``None``, a :class:`Spec`, a dict ``{prop: value}`` or a flat pair list."""
    if spec is None:
        return Spec()
    if isinstance(spec, Spec):
        return spec
    return Spec(spec)


__all__ += ["Spec", "as_spec"]


# --------------------------------------------------------------------------- #
# [SECTION] ImPlot3DStyle
# --------------------------------------------------------------------------- #
_STYLE_FIELDS = (
    ("line_weight", "LineWeight", 1.0), ("marker", "Marker", MARKER_NONE),
    ("marker_size", "MarkerSize", 4.0), ("fill_alpha", "FillAlpha", 1.0),
    ("plot_default_size", "PlotDefaultSize", (400.0, 400.0)),
    ("plot_min_size", "PlotMinSize", (200.0, 200.0)),
    ("plot_padding", "PlotPadding", (10.0, 10.0)),
    ("label_padding", "LabelPadding", (5.0, 5.0)),
    ("view_scale_factor", "ViewScaleFactor", 1.0),
    ("legend_padding", "LegendPadding", (10.0, 10.0)),
    ("legend_inner_padding", "LegendInnerPadding", (5.0, 5.0)),
    ("legend_spacing", "LegendSpacing", (5.0, 0.0)),
)
#: ``ImPlot3DStyleVar_`` -> field, in enum order.
_STYLEVAR_FIELD = [f[0] for f in _STYLE_FIELDS]
_STYLE_CPP = {f[1]: f[0] for f in _STYLE_FIELDS}
_STYLE_CPP.update({"Colors": "colors", "Colormap": "colormap"})


class Style:
    """``ImPlot3DStyle``. Colours are ``ImVec4`` float tuples, as the reference
    keeps them, so ``IMPLOT3D_AUTO_COL`` can mean "take it from the ImGui style"."""

    def __init__(self) -> None:
        for name, _cpp, default in _STYLE_FIELDS:
            setattr(self, name, default)
        self.colors = [IMPLOT3D_AUTO_COL] * COL_COUNT
        style_colors_auto(self)
        self.colormap = COLORMAP_DEEP

    def get_color(self, idx: int):
        return self.colors[idx]

    def set_color(self, idx: int, col) -> None:
        self.colors[idx] = to_vec4(col)

    GetColor, SetColor = get_color, set_color

    def __setattr__(self, name, value) -> None:
        object.__setattr__(self, _STYLE_CPP.get(name, name), value)

    def __getattr__(self, name):
        if name in _STYLE_CPP:
            return object.__getattribute__(self, _STYLE_CPP[name])
        raise AttributeError(name)

    def copy(self) -> "Style":
        out = Style()
        for key, value in self.__dict__.items():
            object.__setattr__(out, key, list(value) if isinstance(value, list) else value)
        return out


__all__ += ["Style"]


# --------------------------------------------------------------------------- #
# [SECTION] Structs (implot3d_internal.h)
# --------------------------------------------------------------------------- #
class DrawList3D:
    """``ImDrawList3D``: screen triangles with a depth each, sorted at the end.

    A triangle is ``(p0, p1, p2, c0, c1, c2, tex, uv0, uv1, uv2)`` with packed
    ``ImU32`` colours; ``tex`` is ``None`` for an untextured one. The depth
    list runs beside it, one entry per triangle, as ``ZBuffer`` does.
    """

    def __init__(self) -> None:
        self.tris: list = []
        self.z: list[float] = []

    def reset_buffers(self) -> None:
        self.tris = []
        self.z = []

    ResetBuffers = reset_buffers

    def add(self, p0, p1, p2, c0, c1, c2, z, tex=None, uv0=None, uv1=None, uv2=None) -> None:
        self.tris.append((p0, p1, p2, c0, c1, c2, tex, uv0, uv1, uv2))
        self.z.append(z)

    def prim_line(self, x1, y1, x2, y2, half_weight, col, z) -> None:
        """``PrimLine``: a segment as a quad, two triangles at one depth."""
        dx, dy = x2 - x1, y2 - y1
        d2 = dx * dx + dy * dy
        if d2 > 0.0:
            inv = 1.0 / math.sqrt(d2)
            dx *= inv
            dy *= inv
        dx *= half_weight
        dy *= half_weight
        v0 = (x1 + dy, y1 - dx)
        v1 = (x2 + dy, y2 - dx)
        v2 = (x2 - dy, y2 + dx)
        v3 = (x1 - dy, y1 + dx)
        self.tris.append((v0, v1, v2, col, col, col, None, None, None, None))
        self.tris.append((v0, v2, v3, col, col, col, None, None, None, None))
        self.z.append(z)
        self.z.append(z)

    def sorted_move_to_draw_list(self, p) -> None:
        """``SortedMoveToImGuiDrawList``: back to front, onto the painter.

        Sorted by depth ascending -- most negative (farthest from the viewer)
        first -- and stably, so triangles of equal depth keep their submission
        order. Runs of flat triangles in one colour go to the painter as one
        :func:`~emtk.painter.fill_triangles` block.
        """
        count = len(self.z)
        if not count:
            self.reset_buffers()
            return
        zs, tris = self.z, self.tris
        order = sorted(range(count), key=zs.__getitem__)
        colours: dict = {}

        def rgba(u):
            got = colours.get(u)
            if got is None:
                got = colours[u] = u32_to_rgba(u)
            return got

        run: list = []
        run_col = None
        for i in order:
            p0, p1, p2, c0, c1, c2, tex, uv0, uv1, uv2 = tris[i]
            area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
            if not (area > 0.0 or area < 0.0):
                continue                      # no area, or NaN corners: nothing to cover
            if tex is None and c0 == c1 == c2:
                if run and c0 != run_col:
                    _painter.fill_triangles(p, run, rgba(run_col))
                    run = []
                run_col = c0
                run.append((p0, p1, p2))
                continue
            if run:
                _painter.fill_triangles(p, run, rgba(run_col))
                run = []
            if tex is not None:
                _painter.image_triangle(p, p0, p1, p2, tex, uv0, uv1, uv2, rgba(c0))
            else:
                _painter.gradient_triangle(p, p0, p1, p2, rgba(c0), rgba(c1), rgba(c2))
        if run:
            _painter.fill_triangles(p, run, rgba(run_col))
        self.reset_buffers()


class NextItemData:
    """``ImPlot3DNextItemData``."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.spec = Spec()
        self.render_line = False
        self.render_fill = False
        self.render_marker_line = True
        self.render_marker_fill = True
        self.is_auto_fill = True
        self.is_auto_line = True
        self.hidden = False


class ColormapData:
    """``ImPlot3DColormapData``: named key lists and their lookup tables."""

    def __init__(self) -> None:
        self.keys: list[list[int]] = []
        self.tables: list[list[int]] = []
        self.names: list[str] = []
        self.quals: list[bool] = []
        self.map: dict[str, int] = {}
        self.count = 0

    def append(self, name: str, keys, qual: bool) -> int:
        if self.get_index(name) != -1:
            return -1
        self.keys.append([to_u32(k) for k in keys])
        self.names.append(name)
        self.quals.append(bool(qual))
        idx = self.count
        self.count += 1
        self.map[name] = idx
        self._append_table(idx)
        return idx

    def _append_table(self, cmap: int) -> None:
        keys = self.keys[cmap]
        if self.quals[cmap]:
            self.tables.append(list(keys))
            return
        table = []
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            for s in range(255):
                table.append(im_mix_u32(a, b, s))
        table.append(keys[-1])
        self.tables.append(table)

    def rebuild_tables(self) -> None:
        self.tables = []
        for i in range(self.count):
            self._append_table(i)

    def is_qual(self, cmap: int) -> bool:
        return self.quals[cmap]

    def get_name(self, cmap: int):
        return self.names[cmap] if 0 <= cmap < self.count else None

    def get_index(self, name: str) -> int:
        return self.map.get(name, -1)

    def get_keys(self, cmap: int):
        return self.keys[cmap]

    def get_key_count(self, cmap: int) -> int:
        return len(self.keys[cmap])

    def get_key_color(self, cmap: int, idx: int) -> int:
        return self.keys[cmap][idx]

    def set_key_color(self, cmap: int, idx: int, value) -> None:
        self.keys[cmap][idx] = to_u32(value)
        self.rebuild_tables()

    def get_table(self, cmap: int):
        return self.tables[cmap]

    def get_table_size(self, cmap: int) -> int:
        return len(self.tables[cmap])

    def get_table_color(self, cmap: int, idx: int) -> int:
        return self.tables[cmap][idx]

    def lerp_table(self, cmap: int, t: float) -> int:
        table = self.tables[cmap]
        siz = len(table)
        idx = (_clamp(int(siz * t), 0, siz - 1) if self.quals[cmap]
               else int((siz - 1) * t + 0.5))
        return table[_clamp(idx, 0, siz - 1)]


class Item:
    """``ImPlot3DItem``."""

    def __init__(self) -> None:
        self.id = None
        self.color = IM_COL32_WHITE
        self.marker = MARKER_NONE
        self.name: str | None = None
        self.show = True
        self.legend_hovered = False
        self.seen_this_frame = False


class Legend:
    """``ImPlot3DLegend``. Rects are ``(x0, y0, x1, y1)``."""

    def __init__(self) -> None:
        self.flags = self.previous_flags = LEGEND_FLAGS_NONE
        self.location = self.previous_location = LOCATION_NORTH_WEST
        self.scroll = (0.0, 0.0)
        self.indices: list[int] = []
        self.rect = (0.0, 0.0, 0.0, 0.0)
        self.rect_clamped = (0.0, 0.0, 0.0, 0.0)
        self.hovered = False
        self.held = False

    def reset(self) -> None:
        self.indices = []


class ItemGroup:
    """``ImPlot3DItemGroup``: the items of one plot, in first-seen order."""

    def __init__(self) -> None:
        self.id = None
        self.items: dict = {}
        self.order: list[Item] = []
        self.legend = Legend()
        self.colormap_idx = 0
        self.marker_idx = 0

    def get_item_count(self) -> int:
        return len(self.order)

    def get_item(self, item_id):
        return self.items.get(item_id)

    def get_or_add_item(self, item_id) -> Item:
        item = self.items.get(item_id)
        if item is None:
            item = self.items[item_id] = Item()
            self.order.append(item)
        return item

    def get_item_by_index(self, i: int) -> Item:
        return self.order[i]

    def get_item_index(self, item: Item) -> int:
        return self.order.index(item)

    def get_legend_count(self) -> int:
        return len(self.legend.indices)

    def get_legend_item(self, i: int) -> Item:
        return self.order[self.legend.indices[i]]

    def get_legend_label(self, i: int) -> str:
        return self.get_legend_item(i).name or ""

    def reset(self) -> None:
        self.items = {}
        self.order = []
        self.legend.reset()
        self.colormap_idx = 0
        self.marker_idx = 0


class Tick:
    """``ImPlot3DTick``."""

    __slots__ = ("plot_pos", "major", "show_label", "label_size", "text", "idx")

    def __init__(self, value: float, major: bool, show_label: bool) -> None:
        self.plot_pos = float(value)
        self.major = major
        self.show_label = show_label
        self.label_size = (0.0, 0.0)
        self.text: str | None = None
        self.idx = 0


class Ticker:
    """``ImPlot3DTicker``."""

    def __init__(self) -> None:
        self.ticks: list[Tick] = []

    def add_tick(self, value: float, major: bool, show_label: bool,
                 formatter=None, data=None, label: str | None = None) -> Tick:
        tick = Tick(value, major, show_label)
        if show_label and label is not None:
            tick.text = label
            tick.label_size = calc_text_size(label)
        elif show_label and formatter is not None:
            tick.text = str(formatter(tick.plot_pos, data))[:IMPLOT3D_LABEL_MAX_SIZE - 1]
            tick.label_size = calc_text_size(tick.text)
        tick.idx = len(self.ticks)
        self.ticks.append(tick)
        return tick

    def get_text(self, tick) -> str:
        if isinstance(tick, int):
            tick = self.ticks[tick]
        return tick.text or ""

    def reset(self) -> None:
        self.ticks = []

    def tick_count(self) -> int:
        return len(self.ticks)


class Axis:
    """``ImPlot3DAxis``: range, scale, ticks, constraints and input state."""

    def __init__(self) -> None:
        self.flags = self.previous_flags = AXIS_FLAGS_NONE
        self.range = Range(0.0, 1.0)
        self.range_cond = COND_NONE
        self.ndc_scale = 1.0
        self.scale = SCALE_LINEAR
        self.label = ""
        self.ticker = Ticker()
        self.formatter = None
        self.formatter_data = None
        self.locator = None
        self.show_default_ticks = True
        self.transform_forward = None
        self.transform_inverse = None
        self.transform_data = None
        self.scaled_range = Range(0.0, 1.0)
        self.fit_this_frame = True
        self.fit_extents = Range(HUGE_VAL, -HUGE_VAL)
        self.constraint_range = Range(-math.inf, math.inf)
        self.constraint_zoom = Range(DBL_MIN, math.inf)
        self.hovered = False
        self.held = False
        self.color_bg = self.color_hov = self.color_act = IM_COL32_BLACK_TRANS

    def reset(self) -> None:
        self.range_cond = COND_NONE
        self.scale = SCALE_LINEAR
        self.transform_forward = self.transform_inverse = None
        self.transform_data = None
        self.ticker.reset()
        self.formatter = None
        self.formatter_data = None
        self.locator = None
        self.show_default_ticks = True
        self.fit_extents = Range(HUGE_VAL, -HUGE_VAL)
        self.constraint_range = Range(-math.inf, math.inf)
        self.constraint_zoom = Range(DBL_MIN, math.inf)

    def set_range(self, v1: float, v2: float) -> None:
        v1 = im_constrain_nan(im_constrain_inf(v1))
        v2 = im_constrain_nan(im_constrain_inf(v2))
        self.range.min, self.range.max = min(v1, v2), max(v1, v2)
        self.constrain()
        self.update_transform_cache()

    def set_min(self, vmin: float, force: bool = False) -> bool:
        if not force and self.is_locked_min():
            return False
        vmin = im_constrain_nan(im_constrain_inf(vmin))
        if vmin < self.constraint_range.min:
            vmin = self.constraint_range.min
        zoom = self.range.max - vmin
        if zoom < self.constraint_zoom.min:
            vmin = self.range.max - self.constraint_zoom.min
        if zoom > self.constraint_zoom.max:
            vmin = self.range.max - self.constraint_zoom.max
        if vmin >= self.range.max:
            return False
        self.range.min = vmin
        self.update_transform_cache()
        return True

    def set_max(self, vmax: float, force: bool = False) -> bool:
        if not force and self.is_locked_max():
            return False
        vmax = im_constrain_nan(im_constrain_inf(vmax))
        if vmax > self.constraint_range.max:
            vmax = self.constraint_range.max
        zoom = vmax - self.range.min
        if zoom < self.constraint_zoom.min:
            vmax = self.range.min + self.constraint_zoom.min
        if zoom > self.constraint_zoom.max:
            vmax = self.range.min + self.constraint_zoom.max
        if vmax <= self.range.min:
            return False
        self.range.max = vmax
        self.update_transform_cache()
        return True

    def constrain(self) -> None:
        r = self.range
        r.min = im_constrain_nan(im_constrain_inf(r.min))
        r.max = im_constrain_nan(im_constrain_inf(r.max))
        if r.min < self.constraint_range.min:
            r.min = self.constraint_range.min
        if r.max > self.constraint_range.max:
            r.max = self.constraint_range.max
        zoom = r.size()
        if zoom < self.constraint_zoom.min:
            delta = (self.constraint_zoom.min - zoom) * 0.5
            r.min -= delta
            r.max += delta
        if zoom > self.constraint_zoom.max:
            delta = (zoom - self.constraint_zoom.max) * 0.5
            r.min += delta
            r.max -= delta
        if r.max <= r.min:
            r.max = r.min + DBL_EPSILON

    def update_transform_cache(self) -> None:
        if self.transform_forward is not None:
            self.scaled_range.min = self.transform_forward(self.range.min, self.transform_data)
            self.scaled_range.max = self.transform_forward(self.range.max, self.transform_data)
        else:
            self.scaled_range.min, self.scaled_range.max = self.range.min, self.range.max

    def plot_to_ndc(self, plt: float) -> float:
        if self.transform_forward is not None:
            s = self.transform_forward(plt, self.transform_data)
            return (s - self.scaled_range.min) / (self.scaled_range.max - self.scaled_range.min)
        return (plt - self.range.min) / (self.range.max - self.range.min)

    def ndc_to_plot(self, t: float) -> float:
        if self.transform_inverse is not None:
            s = t * (self.scaled_range.max - self.scaled_range.min) + self.scaled_range.min
            return self.transform_inverse(s, self.transform_data)
        return self.range.min + t * (self.range.max - self.range.min)

    def is_range_locked(self) -> bool:
        return self.range_cond == COND_ALWAYS

    def is_locked_min(self) -> bool:
        return self.is_range_locked() or im_has_flag(self.flags, AXIS_FLAGS_LOCK_MIN)

    def is_locked_max(self) -> bool:
        return self.is_range_locked() or im_has_flag(self.flags, AXIS_FLAGS_LOCK_MAX)

    def is_locked(self) -> bool:
        return self.is_locked_min() and self.is_locked_max()

    def is_input_locked_min(self) -> bool:
        return self.is_locked_min() or self.is_auto_fitting()

    def is_input_locked_max(self) -> bool:
        return self.is_locked_max() or self.is_auto_fitting()

    def is_input_locked(self) -> bool:
        return self.is_locked() or self.is_auto_fitting()

    def is_pan_locked(self, increasing: bool) -> bool:
        if im_has_flag(self.flags, AXIS_FLAGS_PAN_STRETCH):
            return self.is_input_locked()
        if self.is_locked_min() or self.is_locked_max() or self.is_auto_fitting():
            return False
        if increasing:
            return self.range.max == self.constraint_range.max
        return self.range.min == self.constraint_range.min

    def set_label(self, label) -> None:
        self.label = _display_text(label) if label else ""

    def get_label(self) -> str:
        return self.label

    def ndc_size(self) -> float:
        return self.ndc_scale

    def set_aspect(self, units_per_ndc_unit: float) -> None:
        new_size = units_per_ndc_unit * self.ndc_size()
        delta = (new_size - self.range.size()) * 0.5
        if self.is_locked():
            return
        if self.is_locked_min() and not self.is_locked_max():
            self.set_range(self.range.min, self.range.max + 2 * delta)
        elif not self.is_locked_min() and self.is_locked_max():
            self.set_range(self.range.min - 2 * delta, self.range.max)
        else:
            self.set_range(self.range.min - delta, self.range.max + delta)

    def get_aspect(self) -> float:
        return self.range.size() / self.ndc_size()

    def has_label(self) -> bool:
        return bool(self.label) and not im_has_flag(self.flags, AXIS_FLAGS_NO_LABEL)

    def has_grid_lines(self) -> bool:
        return not im_has_flag(self.flags, AXIS_FLAGS_NO_GRID_LINES)

    def has_tick_labels(self) -> bool:
        return not im_has_flag(self.flags, AXIS_FLAGS_NO_TICK_LABELS)

    def has_tick_marks(self) -> bool:
        return not im_has_flag(self.flags, AXIS_FLAGS_NO_TICK_MARKS)

    def is_auto_fitting(self) -> bool:
        return im_has_flag(self.flags, AXIS_FLAGS_AUTO_FIT)

    def extend_fit(self, value: float) -> None:
        if (not im_nan_or_inf(value) and self.constraint_range.min <= value
                <= self.constraint_range.max):
            self.fit_extents.min = min(self.fit_extents.min, value)
            self.fit_extents.max = max(self.fit_extents.max, value)

    def apply_fit(self) -> None:
        if not self.is_locked_min() and not im_nan_or_inf(self.fit_extents.min):
            self.range.min = self.fit_extents.min
        if not self.is_locked_max() and not im_nan_or_inf(self.fit_extents.max):
            self.range.max = self.fit_extents.max
        if im_almost_equal(self.range.min, self.range.max):
            self.range.max += 0.5
            self.range.min -= 0.5
        self.constrain()
        self.update_transform_cache()
        self.fit_extents = Range(HUGE_VAL, -HUGE_VAL)


#: ``ImPlot3DPlot::InitialRotation``'s default.
DEFAULT_INITIAL_ROTATION = (-0.513269, -0.212596, -0.318184, 0.76819)


class Plot:
    """``ImPlot3DPlot``: what persists about one plot between frames.

    Rects are ``(x0, y0, x1, y1)``, as ``ImRect`` holds them.
    """

    def __init__(self) -> None:
        self.id = None
        self.flags = self.previous_flags = FLAGS_NONE
        self.title = ""
        self.just_created = True
        self.initialized = False
        self.frame_rect = (0.0, 0.0, 0.0, 0.0)
        self.canvas_rect = (0.0, 0.0, 0.0, 0.0)
        self.plot_rect = (0.0, 0.0, 0.0, 0.0)
        self.initial_rotation = Quat(*DEFAULT_INITIAL_ROTATION)
        self.rotation = Quat(0.0, 0.0, 0.0, 1.0)
        self.rotation_cond = COND_NONE
        self.axes = [Axis(), Axis(), Axis()]
        self.animation_time = 0.0
        self.rotation_animation_end = Quat(0.0, 0.0, 0.0, 1.0)
        self.setup_locked = False
        self.hovered = False
        self.held = False
        self.held_edge_idx = -1
        self.held_plane_idx = -1
        self.drag_rotation_axis = Point(0.0, 0.0, 0.0)
        self.fit_this_frame = True
        self.items = ItemGroup()
        self.draw_list = DrawList3D()
        self.context_click = False
        self.open_context_this_frame = False
        #: ``io.MouseClickedTime[Right]``, which emtk's IO does not keep.
        self.right_clicked_time = -1.0e9
        #: Popup names, per plot (see the module docstring).
        self.popups: list[str] = []

    def set_title(self, title) -> None:
        self.title = _display_text(title) if title else ""

    def has_title(self) -> bool:
        return bool(self.title) and not im_has_flag(self.flags, FLAGS_NO_TITLE)

    def get_title(self) -> str:
        return self.title

    def is_rotation_locked(self) -> bool:
        return self.rotation_cond == COND_ALWAYS

    def extend_fit(self, point) -> None:
        for i in range(3):
            v = point[i]
            if not im_nan_or_inf(v) and self.axes[i].fit_this_frame:
                self.axes[i].extend_fit(v)

    def range_min(self) -> Point:
        return Point(self.axes[0].range.min, self.axes[1].range.min, self.axes[2].range.min)

    def range_max(self) -> Point:
        return Point(self.axes[0].range.max, self.axes[1].range.max, self.axes[2].range.max)

    def range_center(self) -> Point:
        a = self.axes
        return Point((a[0].range.min + a[0].range.max) * 0.5,
                     (a[1].range.min + a[1].range.max) * 0.5,
                     (a[2].range.min + a[2].range.max) * 0.5)

    def set_range(self, pmin, pmax) -> None:
        for i in range(3):
            self.axes[i].set_range(pmin[i], pmax[i])

    def get_view_scale(self) -> float:
        x0, y0, x1, y1 = self.plot_rect
        return min(x1 - x0, y1 - y0) / 1.8 * _gp().style.view_scale_factor

    def get_box_scale(self) -> Point:
        return Point(self.axes[0].ndc_size(), self.axes[1].ndc_size(), self.axes[2].ndc_size())

    def apply_equal_aspect(self, ref_axis: int) -> None:
        aspect = self.axes[ref_axis].get_aspect()
        for i in range(3):
            if i != ref_axis and not self.axes[i].is_input_locked():
                self.axes[i].set_aspect(aspect)


class Context:
    """``ImPlot3DContext``."""

    def __init__(self) -> None:
        self.plots: dict = {}
        self.current_plot: Plot | None = None
        self.current_items: ItemGroup | None = None
        self.current_item: Item | None = None
        self.next_item_data = NextItemData()
        self.style = Style()
        self.color_modifiers: list = []
        self.style_modifiers: list = []
        self.colormap_modifiers: list = []
        self.colormap_data = ColormapData()
        #: Which im context and frame opened the current plot, so a plot left
        #: open by an exception does not wedge every later frame.
        self.current_owner = None


__all__ += ["DrawList3D", "NextItemData", "ColormapData", "Item", "Legend",
            "ItemGroup", "Tick", "Ticker", "Axis", "Plot", "Context"]


# --------------------------------------------------------------------------- #
# [SECTION] Context
# --------------------------------------------------------------------------- #
_G: Context | None = None           # GImPlot3D
_FALLBACK: Context | None = None
_STORAGE_KEY = ("__implot3d__",)


def create_context() -> Context:
    """``CreateContext``: made current if none is."""
    global _G
    ctx = Context()
    if _G is None:
        _G = ctx
    initialize_context(ctx)
    return ctx


def destroy_context(ctx: Context | None = None) -> None:
    global _G
    if ctx is None:
        ctx = _G
    if _G is ctx:
        _G = None


def get_current_context() -> Context | None:
    return _G


def set_current_context(ctx: Context | None) -> None:
    global _G
    _G = ctx


def _gp() -> Context:
    """The current ImPlot3D context.

    The reference asserts one was created. Here, with none current, the
    context lives in the im context's storage -- which a host keeps across
    frames, so each host (and each test) has its own plots -- or, outside any
    frame, in one module-wide fallback.
    """
    global _FALLBACK
    if _G is not None:
        return _G
    im_ctx = _core._CURRENT
    if im_ctx is not None:
        ctx = im_ctx.storage.get(_STORAGE_KEY)
        if ctx is None:
            ctx = Context()
            initialize_context(ctx)
            if _FALLBACK is not None:
                ctx.style = _FALLBACK.style
            im_ctx.storage[_STORAGE_KEY] = ctx
        return ctx
    if _FALLBACK is None:
        _FALLBACK = Context()
        initialize_context(_FALLBACK)
    return _FALLBACK


__all__ += ["create_context", "destroy_context", "get_current_context",
            "set_current_context"]


# --------------------------------------------------------------------------- #
# [SECTION] Text Utils
# --------------------------------------------------------------------------- #
def _im():
    return _core.get_current_context()


def _display_text(label: str) -> str:
    """``FindRenderedTextEnd``: what precedes ``##`` is shown."""
    return label.split("##", 1)[0]


def calc_text_size(text: str) -> tuple[float, float]:
    """``CalcTextSize``, from the current painter's metrics."""
    im_ctx = _core._CURRENT
    if im_ctx is None:
        return (len(text) * 7.0, 16.0)
    return (im_ctx.p.text_width(text), im_ctx.p.line_height())


def _text_line_height() -> float:
    im_ctx = _core._CURRENT
    return im_ctx.p.line_height() if im_ctx is not None else 16.0


def add_text_rotated(draw_list, pos, angle: float, col, text: str) -> None:
    """``AddTextRotated``: *text* centred on *pos*, turned by *angle* radians.

    ImGui's angle is counter-clockwise on screen; the painter's degrees are
    clockwise, hence the sign.
    """
    if not text:
        return
    x, y = math.floor(pos[0]), math.floor(pos[1])
    w, h = draw_list.calc_text_size(text)
    _painter.text_rotated(draw_list.p, x - w * 0.5, y - h * 0.5, w, h, ALIGN_CENTER,
                          text, u32_to_rgba(to_u32(col)), -math.degrees(angle))


def add_text_centered(draw_list, top_center, col, text: str) -> None:
    """``AddTextCentered``."""
    shown = _display_text(text)
    w, _h = draw_list.calc_text_size(shown)
    draw_list.add_text((top_center[0] - w * 0.5, top_center[1]),
                       u32_to_rgba(to_u32(col)), shown)


# --------------------------------------------------------------------------- #
# [SECTION] Style Utils
# --------------------------------------------------------------------------- #
def _imgui_color(which: int, alpha_mul: float = 1.0):
    """``ImGui::GetStyleColorVec4`` from emtk's style (0..255 -> floats)."""
    im_ctx = _core._CURRENT
    style = im_ctx.style if im_ctx is not None else _core.Style()
    c = to_vec4(tuple(int(v) for v in style.color(which)))
    return (c[0], c[1], c[2], c[3] * alpha_mul)


def is_color_auto(col) -> bool:
    if isinstance(col, int) and not isinstance(col, bool):
        return is_color_auto(_gp().style.colors[col])
    return col[3] == -1.0


def get_auto_color(idx: int):
    C = _core.Col
    if idx in (COL_TITLE_TEXT, COL_INLAY_TEXT, COL_LEGEND_TEXT, COL_AXIS_TEXT):
        return _imgui_color(C.TEXT)
    if idx == COL_FRAME_BG:
        return _imgui_color(C.FRAME_BG)
    if idx == COL_PLOT_BG:
        return _imgui_color(C.WINDOW_BG)
    if idx in (COL_PLOT_BORDER, COL_LEGEND_BORDER):
        return _imgui_color(C.BORDER)
    if idx == COL_LEGEND_BG:
        return _imgui_color(C.POPUP_BG)
    if idx == COL_AXIS_GRID:
        return _vec4_mul(_imgui_color(C.TEXT), (1.0, 1.0, 1.0, 0.25))
    if idx == COL_AXIS_TICK:
        return get_style_color_vec4(COL_AXIS_GRID)
    if idx == COL_AXIS_BG:
        return (0.0, 0.0, 0.0, 0.0)
    if idx == COL_AXIS_BG_HOVERED:
        return _imgui_color(C.BUTTON_HOVERED)
    if idx == COL_AXIS_BG_ACTIVE:
        return _imgui_color(C.BUTTON_ACTIVE)
    return IMPLOT3D_AUTO_COL


_COLOR_NAMES = ("TitleText", "InlayText", "FrameBg", "PlotBg", "PlotBorder", "LegendBg",
                "LegendBorder", "LegendText", "AxisText", "AxisGrid", "AxisTick", "AxisBg",
                "AxisBgHovered", "AxisBgActive")


def get_style_color_name(idx: int) -> str:
    return _COLOR_NAMES[idx]


def get_item_data() -> NextItemData:
    return _gp().next_item_data


def calc_text_color(bg) -> int:
    """``CalcTextColor``: black on a light background, white on a dark one."""
    bg = to_vec4(bg)
    return (IM_COL32_BLACK if bg[0] * 0.299 + bg[1] * 0.587 + bg[2] * 0.114 > 0.5
            else IM_COL32_WHITE)


# --------------------------------------------------------------------------- #
# [SECTION] Legend Utils
# --------------------------------------------------------------------------- #
_SHORT_LEGEND_LOCATION = {LOCATION_CENTER: "C", LOCATION_NORTH: "N", LOCATION_SOUTH: "S",
                          LOCATION_WEST: "W", LOCATION_EAST: "E", LOCATION_NORTH_WEST: "NW",
                          LOCATION_NORTH_EAST: "NE", LOCATION_SOUTH_WEST: "SW",
                          LOCATION_SOUTH_EAST: "SE"}


def get_location_pos(outer_rect, inner_size, loc: int, pad):
    x0, y0, x1, y1 = outer_rect
    if im_has_flag(loc, LOCATION_WEST) and not im_has_flag(loc, LOCATION_EAST):
        px = x0 + pad[0]
    elif not im_has_flag(loc, LOCATION_WEST) and im_has_flag(loc, LOCATION_EAST):
        px = x1 - pad[0] - inner_size[0]
    else:
        px = (x0 + x1) * 0.5 - inner_size[0] * 0.5
    if im_has_flag(loc, LOCATION_NORTH) and not im_has_flag(loc, LOCATION_SOUTH):
        py = y0 + pad[1]
    elif not im_has_flag(loc, LOCATION_NORTH) and im_has_flag(loc, LOCATION_SOUTH):
        py = y1 - pad[1] - inner_size[1]
    else:
        py = (y0 + y1) * 0.5 - inner_size[1] * 0.5
    return (float(math.floor(px + 0.5)), float(math.floor(py + 0.5)))


def calc_legend_size(items: ItemGroup, pad, spacing, vertical: bool):
    n = items.get_legend_count()
    txt_ht = _text_line_height()
    icon_size = txt_ht
    widths = [calc_text_size(_display_text(items.get_legend_label(i)))[0] for i in range(n)]
    max_w = max(widths, default=0.0)
    sum_w = sum(widths)
    if vertical:
        return (pad[0] * 2 + icon_size + max_w, pad[1] * 2 + n * txt_ht + (n - 1) * spacing[1])
    return (pad[0] * 2 + icon_size * n + sum_w + (n - 1) * spacing[0], pad[1] * 2 + txt_ht)


def clamp_legend_rect(legend_rect, outer_rect, pad):
    """``ClampLegendRect``. Returns ``(clamped, rect)``."""
    x0, y0, x1, y1 = legend_rect
    ox0, oy0, ox1, oy1 = (outer_rect[0] + pad[0], outer_rect[1] + pad[1],
                          outer_rect[2] - pad[0], outer_rect[3] - pad[1])
    clamped = False
    if x0 < ox0:
        x0, clamped = ox0, True
    if y0 < oy0:
        y0, clamped = oy0, True
    if x1 > ox1:
        x1, clamped = ox1, True
    if y1 > oy1:
        y1, clamped = oy1, True
    return clamped, (x0, y0, x1, y1)


def _rect_contains(rect, pos) -> bool:
    return rect[0] <= pos[0] < rect[2] and rect[1] <= pos[1] < rect[3]


def _button_behavior(rect, item_id, buttons=(0, 1, 2)):
    """``ButtonBehavior`` with ``PressedOnClick | PressedOnDoubleClick |
    AllowOverlap`` over several mouse buttons: ``(pressed, hovered, held)``.

    emtk's :meth:`~emtk.im_core.Context.button_behavior` takes one button;
    the plot and its legend listen to three.
    """
    ctx = _im()
    io = ctx.io
    x0, y0, x1, y1 = rect
    ctx.set_next_item_allow_overlap()
    hovered = ctx.item_hoverable((x0, y0, x1 - x0, y1 - y0), item_id)
    pressed = False
    if hovered and any(io.mouse_clicked[b] or io.mouse_double_clicked[b] for b in buttons):
        pressed = True
        ctx.set_active_id(item_id)
    held = ctx.active_id == item_id and any(io.mouse_down[b] for b in buttons)
    if ctx.active_id == item_id and not held:
        ctx.clear_active_id()
    return pressed, hovered, held


def show_legend_entries(items: ItemGroup, legend_bb, pad, spacing, vertical: bool, draw_list) -> None:
    txt_ht = _text_line_height()
    icon_size = txt_ht
    icon_shrink = 2.0
    col_txt = get_style_color_u32(COL_LEGEND_TEXT)
    col_txt_dis = im_alpha_u32(col_txt, 0.25)
    sum_label_width = 0.0
    n = items.get_legend_count()
    for i in range(n):
        item = items.get_legend_item(i)
        label = items.get_legend_label(i)
        label_width = calc_text_size(_display_text(label))[0]
        if vertical:
            top_left = (legend_bb[0] + pad[0], legend_bb[1] + pad[1] + i * (txt_ht + spacing[1]))
        else:
            top_left = (legend_bb[0] + pad[0] + i * (icon_size + spacing[0]) + sum_label_width,
                        legend_bb[1] + pad[1])
        sum_label_width += label_width
        icon_bb = (top_left[0] + icon_shrink, top_left[1] + icon_shrink,
                   top_left[0] + icon_size - icon_shrink, top_left[1] + icon_size - icon_shrink)
        label_max = (top_left[0] + label_width + icon_size, top_left[1] + icon_size)
        col_item = im_alpha_u32(item.color, 1.0)
        button_bb = (icon_bb[0], icon_bb[1], label_max[0], label_max[1])
        item_hov = item_hld = item_clk = False
        if not im_has_flag(items.legend.flags, LEGEND_FLAGS_NO_BUTTONS):
            item_clk, item_hov, item_hld = _button_behavior(button_bb, ("__legend__", item.id), (0,))
            item_clk = item_clk and _im().io.mouse_clicked[0]
        if item_clk:
            item.show = not item.show
        hovering = item_hov and not im_has_flag(items.legend.flags, LEGEND_FLAGS_NO_HIGHLIGHT_ITEM)
        if hovering:
            item.legend_hovered = True
            col_txt_hl = im_mix_u32(col_txt, col_item, 64)
        else:
            item.legend_hovered = False
            col_txt_hl = col_txt
        disabled = to_u32(_imgui_color(_core.Col.TEXT_DISABLED))
        if item_hld:
            col_icon = im_alpha_u32(col_item, 0.5) if item.show else im_alpha_u32(disabled, 0.5)
        elif item_hov:
            col_icon = im_alpha_u32(col_item, 0.75) if item.show else im_alpha_u32(disabled, 0.75)
        else:
            col_icon = col_item if item.show else col_txt_dis
        draw_list.add_rect_filled(icon_bb[:2], icon_bb[2:], u32_to_rgba(col_icon))
        shown = _display_text(label)
        if shown:
            draw_list.add_text((top_left[0] + icon_size, top_left[1]),
                               u32_to_rgba(col_txt_hl if item.show else col_txt_dis), shown)


def render_legend() -> None:
    gp = _gp()
    plot = gp.current_plot
    if im_has_flag(plot.flags, FLAGS_NO_LEGEND) or plot.items.get_legend_count() == 0:
        return
    ctx = _im()
    draw_list = ctx.draw
    io = ctx.io
    legend = plot.items.legend
    horz = im_has_flag(legend.flags, LEGEND_FLAGS_HORIZONTAL)
    size = calc_legend_size(plot.items, gp.style.legend_inner_padding,
                            gp.style.legend_spacing, not horz)
    pos = get_location_pos(plot.plot_rect, size, legend.location, gp.style.legend_padding)
    legend.rect = (pos[0], pos[1], pos[0] + size[0], pos[1] + size[1])
    scrollable, legend.rect_clamped = clamp_legend_rect(legend.rect, plot.plot_rect,
                                                        gp.style.legend_padding)
    _pressed, legend.hovered, legend.held = _button_behavior(legend.rect_clamped, plot.items.id)
    legend.hovered = legend.hovered or _rect_contains(legend.rect_clamped, io.mouse_pos)
    if scrollable:
        rc, r = legend.rect_clamped, legend.rect
        sx, sy = legend.scroll
        if legend.hovered and io.mouse_wheel != 0.0:
            max_step = ((r[2] - r[0]) * 0.67, (r[3] - r[1]) * 0.67)
            step = math.floor(min(2 * _text_line_height(), max_step[0]))
            sx += step * io.mouse_wheel
            sy += step * io.mouse_wheel
        min_off = ((rc[2] - rc[0]) - (r[2] - r[0]), (rc[3] - rc[1]) - (r[3] - r[1]))
        sx = _clamp(sx, min_off[0], 0.0)
        sy = _clamp(sy, min_off[1], 0.0)
        legend.scroll = (sx, sy)
        off = (sx, 0.0) if horz else (0.0, sy)
        dx = rc[0] - r[0] + off[0]
        dy = rc[1] - r[1] + off[1]
        legend.rect = (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)
    else:
        legend.scroll = (0.0, 0.0)
    rc = legend.rect_clamped
    draw_list.push_clip_rect(rc[:2], rc[2:], True)
    draw_list.add_rect_filled(rc[:2], rc[2:], u32_to_rgba(get_style_color_u32(COL_LEGEND_BG)))
    show_legend_entries(plot.items, legend.rect, gp.style.legend_inner_padding,
                        gp.style.legend_spacing, not horz, draw_list)
    draw_list.add_rect(rc[:2], rc[2:], u32_to_rgba(get_style_color_u32(COL_LEGEND_BORDER)))
    draw_list.pop_clip_rect()


# --------------------------------------------------------------------------- #
# [SECTION] Mouse Position Utils
# --------------------------------------------------------------------------- #
def render_mouse_pos() -> None:
    gp = _gp()
    plot = gp.current_plot
    if im_has_flag(plot.flags, FLAGS_NO_MOUSE_TEXT):
        return
    ctx = _im()
    mouse = ctx.io.mouse_pos
    p = pixels_to_plot_plane(mouse, PLANE_YZ, True)
    if p.is_nan():
        p = pixels_to_plot_plane(mouse, PLANE_XZ, True)
    if p.is_nan():
        p = pixels_to_plot_plane(mouse, PLANE_XY, True)
    if p.is_nan():
        return
    parts = [str(plot.axes[i].formatter(p[i], plot.axes[i].formatter_data)) for i in range(3)]
    text = "(" + ", ".join(parts) + ")"
    size = calc_text_size(text)
    pos = get_location_pos(plot.plot_rect, size, LOCATION_SOUTH_EAST, (10.0, 10.0))
    ctx.draw.add_text(pos, u32_to_rgba(get_style_color_u32(COL_INLAY_TEXT)), text)


# --------------------------------------------------------------------------- #
# [SECTION] Plot Box Utils
# --------------------------------------------------------------------------- #
#: Faces of the box, four corner indices each: X-min, Y-min, Z-min, X-max, Y-max, Z-max.
FACES = ((0, 3, 7, 4), (0, 4, 5, 1), (0, 1, 2, 3), (1, 2, 6, 5), (3, 7, 6, 2), (4, 5, 6, 7))
#: Edges of the box, two corner indices each.
EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
         (0, 4), (1, 5), (2, 6), (3, 7))
#: The four edges of each face.
FACE_EDGES = ((3, 11, 8, 7), (0, 8, 4, 9), (0, 1, 2, 3), (1, 9, 5, 10), (2, 10, 6, 11),
              (4, 5, 6, 7))
#: Axis corner pairs by active faces ``(x << 2 | y << 1 | z)``.
AXIS_CORNERS_LOOKUP_3D = (
    ((3, 2), (1, 2), (1, 5)), ((7, 6), (5, 6), (1, 5)), ((0, 1), (1, 2), (2, 6)),
    ((4, 5), (5, 6), (2, 6)), ((3, 2), (0, 3), (0, 4)), ((7, 6), (4, 7), (0, 4)),
    ((0, 1), (0, 3), (3, 7)), ((4, 5), (4, 7), (3, 7)),
)
AXIS_EDGES_LOOKUP_3D = ((2, 1, 9), (6, 5, 9), (0, 1, 10), (4, 5, 10), (2, 3, 8), (6, 7, 8),
                        (0, 3, 11), (4, 7, 11))
#: Edge -> ((face, plane), (face, plane)).
EDGE_TO_FACES = (
    ((1, PLANE_XZ), (2, PLANE_XY)), ((2, PLANE_XY), (3, PLANE_YZ)),
    ((2, PLANE_XY), (4, PLANE_XZ)), ((0, PLANE_YZ), (2, PLANE_XY)),
    ((1, PLANE_XZ), (5, PLANE_XY)), ((3, PLANE_YZ), (5, PLANE_XY)),
    ((4, PLANE_XZ), (5, PLANE_XY)), ((0, PLANE_YZ), (5, PLANE_XY)),
    ((0, PLANE_YZ), (1, PLANE_XZ)), ((1, PLANE_XZ), (3, PLANE_YZ)),
    ((3, PLANE_YZ), (4, PLANE_XZ)), ((0, PLANE_YZ), (4, PLANE_XZ)),
)

AXIS_TICK_INNER_PAD = 5.0
AXIS_LABEL_PAD = 10.0
AXIS_RECT_MIN_WIDTH = 40.0


def active_3d_faces_to_axis_lookup_index(active_faces) -> int:
    return (int(active_faces[0]) << 2) | (int(active_faces[1]) << 1) | int(active_faces[2])


def im_triangle_contains_point(a, b, c, p) -> bool:
    b1 = ((p[0] - b[0]) * (a[1] - b[1]) - (p[1] - b[1]) * (a[0] - b[0])) < 0.0
    b2 = ((p[0] - c[0]) * (b[1] - c[1]) - (p[1] - c[1]) * (b[0] - c[0])) < 0.0
    b3 = ((p[0] - a[0]) * (c[1] - a[1]) - (p[1] - a[1]) * (c[0] - a[0])) < 0.0
    return b1 == b2 and b2 == b3


def get_mouse_over_plane(active_faces, corners_pix):
    """``GetMouseOverPlane``: ``(plane, plane)`` -- the C++ out-param twice."""
    mouse = _im().io.mouse_pos
    for a in range(3):
        f = FACES[a + 3 * int(active_faces[a])]
        p0, p1, p2, p3 = (corners_pix[f[0]], corners_pix[f[1]], corners_pix[f[2]],
                          corners_pix[f[3]])
        if (im_triangle_contains_point(p0, p1, p2, mouse)
                or im_triangle_contains_point(p2, p3, p0, mouse)):
            return a
    return -1


def is_point_in_edge_hover_region(point, p0, p1, outward_dir, width: float) -> bool:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.001:
        return False
    dx, dy = dx / length, dy / length
    lx, ly = point[0] - p0[0], point[1] - p0[1]
    along = lx * dx + ly * dy
    across = lx * outward_dir[0] + ly * outward_dir[1]
    return 0.0 <= along <= length and 0.0 <= across <= width


def compute_edge_outward_dir(p0, p1, box_center):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.001:
        return (0.0, 0.0)
    dx, dy = dx / length, dy / length
    perp = (-dy, dx)
    to_edge = ((p0[0] + p1[0]) * 0.5 - box_center[0], (p0[1] + p1[1]) * 0.5 - box_center[1])
    if perp[0] * to_edge[0] + perp[1] * to_edge[1] < 0.0:
        perp = (-perp[0], -perp[1])
    return perp


def compute_max_tick_label_extent(axis: Axis) -> float:
    if im_has_flag(axis.flags, AXIS_FLAGS_NO_TICK_LABELS):
        return 0.0
    return max((t.label_size[0] * 0.5 for t in axis.ticker.ticks if t.show_label), default=0.0)


def compute_axis_hover_width(axis: Axis) -> float:
    w = 2.0 * compute_max_tick_label_extent(axis) + AXIS_TICK_INNER_PAD
    if axis.has_label():
        w += AXIS_LABEL_PAD + calc_text_size(axis.get_label())[1] * 0.5
    return max(w, AXIS_RECT_MIN_WIDTH)


def _box_center(corners_pix):
    return (sum(c[0] for c in corners_pix) / 8.0, sum(c[1] for c in corners_pix) / 8.0)


def get_mouse_over_axis(plot: Plot, corners_pix, plane_2d: int, axis_corners):
    """``GetMouseOverAxis``: ``(axis, edge)``, ``-1`` for none."""
    mouse = _im().io.mouse_pos
    center = _box_center(corners_pix)
    for axis_idx in range(3):
        if plane_2d != -1 and axis_idx == plane_2d:
            continue
        idx0, idx1 = axis_corners[axis_idx]
        if idx0 == -1 or idx1 == -1:
            continue
        edge = -1
        for e in range(12):
            if (EDGES[e][0] == idx0 and EDGES[e][1] == idx1) or (EDGES[e][0] == idx1 and EDGES[e][1] == idx0):
                edge = e
                break
        if edge == -1:
            continue
        p0, p1 = corners_pix[idx0], corners_pix[idx1]
        outward = compute_edge_outward_dir(p0, p1, center)
        if is_point_in_edge_hover_region(mouse, p0, p1, outward,
                                         compute_axis_hover_width(plot.axes[axis_idx])):
            return axis_idx, edge
    return -1, -1


def render_plot_background(draw_list, plot: Plot, corners_pix, active_faces, plane_2d, axis_corners) -> None:
    col_bg = get_style_color_vec4(COL_PLOT_BG)
    col_bg_hov = _vec4_add(col_bg, (0.03, 0.03, 0.03, 0.0))
    if not plot.held:
        hovered_plane = get_mouse_over_plane(active_faces, corners_pix)
        if get_mouse_over_axis(plot, corners_pix, plane_2d, axis_corners)[0] != -1:
            hovered_plane = -1
    else:
        hovered_plane = plot.held_plane_idx
    for a in range(3):
        f = FACES[a + 3 * int(active_faces[a])]
        col = u32_to_rgba(color_convert_float4_to_u32(col_bg_hov if hovered_plane == a else col_bg))
        draw_list.add_quad_filled(corners_pix[f[0]], corners_pix[f[1]], corners_pix[f[2]],
                                  corners_pix[f[3]], col)


def render_axis_rects(draw_list, plot: Plot, corners_pix, active_faces, plane_2d, axis_corners) -> None:
    hovered_axis = get_mouse_over_axis(plot, corners_pix, plane_2d, axis_corners)[0]
    center = _box_center(corners_pix)
    for axis_idx in range(3):
        if plane_2d != -1 and axis_idx == plane_2d:
            continue
        idx0, idx1 = axis_corners[axis_idx]
        if idx0 == -1 or idx1 == -1:
            continue
        axis = plot.axes[axis_idx]
        p0, p1 = corners_pix[idx0], corners_pix[idx1]
        out = compute_edge_outward_dir(p0, p1, center)
        width = compute_axis_hover_width(axis)
        if axis.held and plot.held_edge_idx != -1:
            col = axis.color_act
        elif axis_idx == hovered_axis and not plot.held:
            col = axis.color_hov
        else:
            col = axis.color_bg
        if col != IM_COL32_BLACK_TRANS:
            c1 = (p0[0] + out[0] * width, p0[1] + out[1] * width)
            c2 = (p1[0] + out[0] * width, p1[1] + out[1] * width)
            draw_list.add_quad_filled(p0, c1, c2, p1, u32_to_rgba(col))


def render_plot_border(draw_list, plot: Plot, corners_pix, active_faces, plane_2d) -> None:
    render_edge = [False] * 12
    for a in range(3):
        if plane_2d != -1 and a != plane_2d:
            continue
        for e in FACE_EDGES[a + 3 * int(active_faces[a])]:
            render_edge[e] = True
    col = u32_to_rgba(get_style_color_u32(COL_PLOT_BORDER))
    for i in range(12):
        if render_edge[i]:
            draw_list.add_line(corners_pix[EDGES[i][0]], corners_pix[EDGES[i][1]], col, 1.0)


def render_grid(draw_list, plot: Plot, corners, active_faces, plane_2d) -> None:
    col_grid = get_style_color_vec4(COL_AXIS_GRID)
    col_minor = u32_to_rgba(to_u32(_vec4_mul(col_grid, (1, 1, 1, 0.3))))
    col_major = u32_to_rgba(to_u32(_vec4_mul(col_grid, (1, 1, 1, 0.6))))
    proj = _Projector(plot)
    for face in range(3):
        if plane_2d != -1 and face != plane_2d:
            continue
        f = FACES[face + 3 * int(active_faces[face])]
        axis_u = plot.axes[(face + 1) % 3]
        axis_v = plot.axes[(face + 2) % 3]
        p0, p1, p3 = corners[f[0]], corners[f[1]], corners[f[3]]
        u_vec = p1 - p0
        v_vec = p3 - p0
        for axis, vec, start, end in ((axis_u, u_vec, p0, p3), (axis_v, v_vec, p0, p1)):
            if im_has_flag(axis.flags, AXIS_FLAGS_NO_GRID_LINES):
                continue
            span = axis.range.max - axis.range.min
            for tick in axis.ticker.ticks:
                t = (tick.plot_pos - axis.range.min) / span
                if t < 0.0 or t > 1.0:
                    continue
                a = start + vec * t
                b = end + vec * t
                draw_list.add_line(proj.to_pixels(a.x, a.y, a.z), proj.to_pixels(b.x, b.y, b.z),
                                   col_major if tick.major else col_minor)


def render_tick_marks(draw_list, plot: Plot, corners, corners_pix, axis_corners, plane_2d) -> None:
    col_tick = u32_to_rgba(get_style_color_u32(COL_AXIS_TICK))
    for a in range(3):
        axis = plot.axes[a]
        if im_has_flag(axis.flags, AXIS_FLAGS_NO_TICK_MARKS):
            continue
        idx0, idx1 = axis_corners[a]
        if idx0 == idx1:
            continue
        axis_start, axis_end = corners[idx0], corners[idx1]
        axis_dir = axis_end - axis_start
        axis_len = axis_dir.length()
        if axis_len < 1e-12:
            continue
        axis_dir = axis_dir / axis_len
        draw_list.add_line(corners_pix[idx0], corners_pix[idx1], col_tick)
        chosen = plane_2d if plane_2d != -1 else (1 if a == 2 else 2)
        proj_dir = Point(*axis_dir)
        proj_dir[chosen] = 0.0
        proj_len = proj_dir.length()
        if proj_len < 1e-12:
            continue
        proj_dir = proj_dir / proj_len
        if chosen == 0:
            tick_dir = Point(0.0, -proj_dir.z, proj_dir.y)
        elif chosen == 1:
            tick_dir = Point(-proj_dir.z, 0.0, proj_dir.x)
        else:
            tick_dir = Point(-proj_dir.y, proj_dir.x, 0.0)
        tick_dir.normalize()
        span = axis.range.max - axis.range.min
        for tick in axis.ticker.ticks:
            v = (tick.plot_pos - axis.range.min) / span
            if v < 0.0 or v > 1.0:
                continue
            pos_ndc = plot_to_ndc(axis_start + axis_dir * (v * axis_len))
            half = tick_dir * ((0.06 if tick.major else 0.03) * 0.5)
            draw_list.add_line(ndc_to_pixels(pos_ndc - half), ndc_to_pixels(pos_ndc + half), col_tick)


def _upright(angle: float) -> float:
    if angle > math.pi * 0.5:
        angle -= math.pi
    if angle < -math.pi * 0.5:
        angle += math.pi
    return angle


def render_tick_labels(draw_list, plot: Plot, corners, corners_pix, axis_corners) -> None:
    col = get_style_color_u32(COL_AXIS_TEXT)
    center_pix = plot_to_pixels(plot.range_center())
    for a in range(3):
        axis = plot.axes[a]
        if im_has_flag(axis.flags, AXIS_FLAGS_NO_TICK_LABELS):
            continue
        idx0, idx1 = axis_corners[a]
        if idx0 == idx1:
            continue
        axis_start = corners[idx0]
        axis_dir = corners[idx1] - axis_start
        s, e = corners_pix[idx0], corners_pix[idx1]
        sdx, sdy = e[0] - s[0], e[1] - s[1]
        slen = math.sqrt(sdx * sdx + sdy * sdy)
        sdx, sdy = (sdx / slen, sdy / slen) if slen > 0.0 else (1.0, 0.0)
        out = compute_edge_outward_dir(s, e, center_pix)
        extent = compute_max_tick_label_extent(axis)
        off = (out[0] * (extent + AXIS_TICK_INNER_PAD), out[1] * (extent + AXIS_TICK_INNER_PAD))
        angle = math.atan2(-sdy, sdx) + math.pi * 0.5
        if angle > math.pi:
            angle -= 2 * math.pi
        if angle < -math.pi:
            angle += 2 * math.pi
        angle = _upright(angle)
        span = axis.range.max - axis.range.min
        for tick in axis.ticker.ticks:
            if not tick.show_label:
                continue
            t = (tick.plot_pos - axis.range.min) / span
            if t < 0.0 or t > 1.0:
                continue
            pix = plot_to_pixels(axis_start + axis_dir * t)
            add_text_rotated(draw_list, (pix[0] + off[0], pix[1] + off[1]), angle, col,
                             axis.ticker.get_text(tick))


def render_axis_labels(draw_list, plot: Plot, corners, corners_pix, axis_corners) -> None:
    col = get_style_color_u32(COL_AXIS_TEXT)
    center_pix = plot_to_pixels(plot.range_center())
    for a in range(3):
        axis = plot.axes[a]
        if not axis.has_label():
            continue
        idx0, idx1 = axis_corners[a]
        if idx0 == idx1:
            continue
        s, e = corners_pix[idx0], corners_pix[idx1]
        sdx, sdy = e[0] - s[0], e[1] - s[1]
        slen = math.sqrt(sdx * sdx + sdy * sdy)
        sdx, sdy = (sdx / slen, sdy / slen) if slen > 0.0 else (1.0, 0.0)
        out = compute_edge_outward_dir(s, e, center_pix)
        extent = compute_max_tick_label_extent(axis)
        total = (extent + AXIS_TICK_INNER_PAD) + extent + AXIS_LABEL_PAD
        pos = ((s[0] + e[0]) * 0.5 + out[0] * total, (s[1] + e[1]) * 0.5 + out[1] * total)
        add_text_rotated(draw_list, pos, _upright(math.atan2(-sdy, sdx)), col, axis.get_label())


def compute_active_faces(rotation: Quat, axes):
    """``ComputeActiveFaces``: ``(active_faces, plane_2d)``."""
    active = [False, False, False]
    plane_2d = -1
    num_deg = 0
    for i, n in enumerate((rotation * (1.0, 0.0, 0.0), rotation * (0.0, 1.0, 0.0),
                           rotation * (0.0, 0.0, 1.0))):
        if abs(n.z) < 0.025:
            active[i] = n.x + n.y < 0.0
            num_deg += 1
        else:
            inverted = im_has_flag(axes[i].flags, AXIS_FLAGS_INVERT)
            active[i] = (n.z > 0.0) if inverted else (n.z < 0.0)
            plane_2d = i
    if num_deg != 2:
        plane_2d = -1
    return active, plane_2d


def compute_box_corners(range_min, range_max):
    lo, hi = range_min, range_max
    return [Point(lo[0], lo[1], lo[2]), Point(hi[0], lo[1], lo[2]), Point(hi[0], hi[1], lo[2]),
            Point(lo[0], hi[1], lo[2]), Point(lo[0], lo[1], hi[2]), Point(hi[0], lo[1], hi[2]),
            Point(hi[0], hi[1], hi[2]), Point(lo[0], hi[1], hi[2])]


class _Projector:
    """``PlotToNDC`` then ``NDCToPixels`` for one plot state, in plain floats.

    Built per item (and per box render) so each vertex is a handful of
    multiply-adds. The depth is ``GetPointDepth``: the rotated *plot-space*
    point with inverted axes negated -- the reference's own definition, not
    NDC.
    """

    __slots__ = ("m", "scale", "cx", "cy", "axes", "inv", "linear")

    def __init__(self, plot: Plot) -> None:
        self.m = plot.rotation.matrix()
        self.scale = plot.get_view_scale()
        x0, y0, x1, y1 = plot.plot_rect
        self.cx, self.cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        self.axes = []
        self.inv = []
        for axis in plot.axes:
            inv = im_has_flag(axis.flags, AXIS_FLAGS_INVERT)
            self.inv.append(inv)
            if axis.transform_forward is not None:
                self.axes.append((axis.transform_forward, axis.transform_data,
                                  axis.scaled_range.min, axis.scaled_range.max - axis.scaled_range.min,
                                  inv, axis.ndc_scale))
            else:
                self.axes.append((None, None, axis.range.min, axis.range.max - axis.range.min,
                                  inv, axis.ndc_scale))

        # A linear axis is ``ndc = a * v + b``; with all three linear the
        # projection is one affine map, folded here into ``to_pixels``.
        self.linear = None
        if all(a[0] is None for a in self.axes):
            ab = []
            for _f, _d, lo, span, inv, sc in self.axes:
                a = sc / span
                ab.append((-a, (0.5 + lo / span) * sc) if inv else (a, (-lo / span - 0.5) * sc))
            m0, m1 = self.m[0], self.m[1]
            s = self.scale
            rows = []
            for row, sign, c in ((m0, s, self.cx), (m1, -s, self.cy)):
                rows.append((sign * row[0] * ab[0][0], sign * row[1] * ab[1][0],
                             sign * row[2] * ab[2][0],
                             sign * (row[0] * ab[0][1] + row[1] * ab[1][1] + row[2] * ab[2][1]) + c))
            self.linear = rows

    def ndc(self, x: float, y: float, z: float):
        out = []
        for v, (fwd, data, lo, span, inv, sc) in zip((x, y, z), self.axes):
            if fwd is not None:
                v = fwd(v, data)
            t = (v - lo) / span
            out.append(((0.5 - t) if inv else (t - 0.5)) * sc)
        return out

    def to_pixels(self, x: float, y: float, z: float):
        lin = self.linear
        if lin is not None:
            r0, r1 = lin
            return (r0[0] * x + r0[1] * y + r0[2] * z + r0[3],
                    r1[0] * x + r1[1] * y + r1[2] * z + r1[3])
        nx, ny, nz = self.ndc(x, y, z)
        m0, m1 = self.m[0], self.m[1]
        s = self.scale
        return (s * (m0[0] * nx + m0[1] * ny + m0[2] * nz) + self.cx,
                -s * (m1[0] * nx + m1[1] * ny + m1[2] * nz) + self.cy)

    def ndc_to_pixels(self, nx: float, ny: float, nz: float):
        m0, m1 = self.m[0], self.m[1]
        s = self.scale
        return (s * (m0[0] * nx + m0[1] * ny + m0[2] * nz) + self.cx,
                -s * (m1[0] * nx + m1[1] * ny + m1[2] * nz) + self.cy)

    def depth(self, x: float, y: float, z: float) -> float:
        inv = self.inv
        if inv[0]:
            x = -x
        if inv[1]:
            y = -y
        if inv[2]:
            z = -z
        m2 = self.m[2]
        return m2[0] * x + m2[1] * y + m2[2] * z


def get_axes_parameters(plot: Plot):
    """``GetAxesParameters``: ``(active_faces, corners_pix, corners, plane_2d, axis_corners)``."""
    active_faces, plane_2d = compute_active_faces(plot.rotation, plot.axes)
    corners = compute_box_corners(plot.range_min(), plot.range_max())
    proj = _Projector(plot)
    corners_pix = [proj.to_pixels(c.x, c.y, c.z) for c in corners]
    axis_corners = [[-1, -1], [-1, -1], [-1, -1]]
    if plane_2d != -1:
        face = plane_2d + 3 * int(active_faces[plane_2d])
        common = [-1, -1]
        for edge in FACE_EDGES[face]:
            for j in range(2):
                axis = (plane_2d + 1 + j) % 3
                if edge in FACE_EDGES[axis + int(active_faces[axis]) * 3]:
                    common[j] = edge
        origin = x_corner = y_corner = -1
        for i in range(2):
            for j in range(2):
                if EDGES[common[0]][i] == EDGES[common[1]][j]:
                    origin = EDGES[common[0]][i]
                    x_corner = EDGES[common[0]][1 - i]
                    y_corner = EDGES[common[1]][1 - j]
        xv = (corners_pix[x_corner][0] - corners_pix[origin][0])
        yv = (corners_pix[y_corner][0] - corners_pix[origin][0])
        if yv > xv:
            x_corner, y_corner = y_corner, x_corner
        o3 = corners[origin]
        x3 = (corners[x_corner] - o3).normalized()
        y3 = (corners[y_corner] - o3).normalized()
        x_axis = y_axis = -1
        x_inv = y_inv = False
        for i in range(2):
            axis_i = (plane_2d + 1 + i) % 3
            if y_axis != -1 or (abs(x3[axis_i]) > 1e-8 and x_axis == -1):
                x_axis, x_inv = axis_i, x3[axis_i] < 0.0
            else:
                y_axis, y_inv = axis_i, y3[axis_i] < 0.0
        axis_corners[plane_2d] = [-1, -1]
        axis_corners[x_axis] = [x_corner, origin] if x_inv else [origin, x_corner]
        axis_corners[y_axis] = [y_corner, origin] if y_inv else [origin, y_corner]
    else:
        index = active_3d_faces_to_axis_lookup_index(active_faces)
        for a in range(3):
            axis_corners[a] = list(AXIS_CORNERS_LOOKUP_3D[index][a])
    return active_faces, corners_pix, corners, plane_2d, axis_corners


def render_plot_box(draw_list, plot: Plot) -> None:
    active_faces, corners_pix, corners, plane_2d, axis_corners = get_axes_parameters(plot)
    render_plot_background(draw_list, plot, corners_pix, active_faces, plane_2d, axis_corners)
    render_axis_rects(draw_list, plot, corners_pix, active_faces, plane_2d, axis_corners)
    render_plot_border(draw_list, plot, corners_pix, active_faces, plane_2d)
    render_grid(draw_list, plot, corners, active_faces, plane_2d)
    render_tick_marks(draw_list, plot, corners, corners_pix, axis_corners, plane_2d)
    render_tick_labels(draw_list, plot, corners, corners_pix, axis_corners)
    render_axis_labels(draw_list, plot, corners, corners_pix, axis_corners)


# --------------------------------------------------------------------------- #
# [SECTION] Formatter
# --------------------------------------------------------------------------- #
def formatter_default(value: float, data) -> str:
    """``Formatter_Default``: *data* is a printf format (``"%g"``)."""
    return (data or IMPLOT3D_LABEL_FORMAT) % value


# --------------------------------------------------------------------------- #
# [SECTION] Locator
# --------------------------------------------------------------------------- #
def nice_num(x: float, round_: bool) -> float:
    expv = int(math.floor(math.log10(x)))
    f = x / 10.0 ** expv
    if round_:
        nf = 1.0 if f < 1.5 else 2.0 if f < 3 else 5.0 if f < 7 else 10.0
    else:
        nf = 1.0 if f <= 1 else 2.0 if f <= 2 else 5.0 if f <= 5 else 10.0
    return nf * 10.0 ** expv


def _round(v: float) -> int:
    """``IM_ROUND``: ``(int)(v + 0.5)``."""
    return int(v + 0.5)


def locator_default(ticker: Ticker, rng: Range, pixels: float, formatter, data) -> None:
    if rng.min == rng.max:
        return
    n_minor = min(max(1, _round(pixels / 30.0)), 5)
    n_major = max(2, _round(pixels / 80.0))
    max_ticks_labels = 7
    nice_range = nice_num(rng.size() * 0.99, False)
    interval = nice_num(nice_range / (n_major - 1), True)
    graphmin = math.floor(rng.min / interval) * interval
    graphmax = math.ceil(rng.max / interval) * interval
    first_major_set = False
    first_major_idx = 0
    idx0 = ticker.tick_count()
    major = graphmin
    while major < graphmax + 0.5 * interval:
        if major - interval < 0 and major + interval > 0:
            major = 0.0
        if rng.contains(major):
            if not first_major_set:
                first_major_idx = ticker.tick_count()
                first_major_set = True
            ticker.add_tick(major, True, True, formatter, data)
        for i in range(1, n_minor):
            minor = major + i * interval / n_minor
            if rng.contains(minor):
                ticker.add_tick(minor, False, True, formatter, data)
        major += interval
    if ticker.tick_count() > max_ticks_labels:
        for i in range(first_major_idx - 1, idx0 - 1, -2):
            ticker.ticks[i].show_label = False
        for i in range(first_major_idx + 1, ticker.tick_count(), 2):
            ticker.ticks[i].show_label = False


def calc_logarithmic_exponents(rng: Range, pix: float):
    """``(ok, exp_min, exp_max, exp_step)``."""
    if rng.min * rng.max > 0:
        n_major = max(2, _round(pix * 0.01))
        log_min = math.log10(abs(rng.min))
        log_max = math.log10(abs(rng.max))
        log_a, log_b = min(log_min, log_max), max(log_min, log_max)
        exp_step = max(1, int(int(log_b - log_a) / n_major))
        exp_min, exp_max = int(log_a), int(log_b)
        if exp_step != 1:
            while exp_step % 3 != 0:
                exp_step += 1
            while exp_min % exp_step != 0:
                exp_min -= 1
        return True, exp_min, exp_max, exp_step
    return False, 0, 0, 1


def add_ticks_logarithmic(rng: Range, exp_min, exp_max, exp_step, ticker: Ticker,
                          formatter, data) -> None:
    sign = 1.0 if rng.max > 0 else -1.0 if rng.max < 0 else 0.0
    for e in range(exp_min - exp_step, exp_max + exp_step, exp_step):
        major1 = sign * 10.0 ** e
        if rng.min - DBL_EPSILON <= major1 <= rng.max + DBL_EPSILON:
            ticker.add_tick(major1, True, True, formatter, data)
        for j in range(exp_step):
            major1 = sign * 10.0 ** (e + j)
            major2 = sign * 10.0 ** (e + j + 1)
            interval = (major2 - major1) / 9
            for i in range(1, 9 + int(j < exp_step - 1)):
                minor = major1 + i * interval
                if rng.min - DBL_EPSILON <= minor <= rng.max + DBL_EPSILON:
                    ticker.add_tick(minor, False, False, formatter, data)


def locator_log10(ticker: Ticker, rng: Range, pixels: float, formatter, data) -> None:
    ok, emin, emax, estep = calc_logarithmic_exponents(rng, pixels)
    if ok:
        add_ticks_logarithmic(rng, emin, emax, estep, ticker, formatter, data)


def transform_forward_log10(v: float, _data=None) -> float:
    return math.log10(DBL_MIN if v <= 0.0 else v)


def transform_inverse_log10(v: float, _data=None) -> float:
    return 10.0 ** v


def transform_forward_symlog(v: float, _data=None) -> float:
    return 2.0 * math.asinh(v / 2.0)


def transform_inverse_symlog(v: float, _data=None) -> float:
    return 2.0 * math.sinh(v / 2.0)


def calc_symlog_pixel(plt: float, rng: Range, pixels: float) -> float:
    scale_to_pixels = pixels / rng.size()
    smin = transform_forward_symlog(rng.min)
    smax = transform_forward_symlog(rng.max)
    t = (transform_forward_symlog(plt) - smin) / (smax - smin)
    plt = rng.min + rng.size() * t
    return scale_to_pixels * (plt - rng.min)


def locator_symlog(ticker: Ticker, rng: Range, pixels: float, formatter, data) -> None:
    if rng.min >= -1 and rng.max <= 1:
        locator_default(ticker, rng, pixels, formatter, data)
    elif rng.min * rng.max < 0:
        pix_p1 = calc_symlog_pixel(1, rng, pixels)
        pix_n1 = calc_symlog_pixel(-1, rng, pixels)
        _ok, emin_p, emax_p, estep_p = calc_logarithmic_exponents(Range(1, rng.max), abs(pixels - pix_p1))
        _ok, emin_n, emax_n, estep_n = calc_logarithmic_exponents(Range(rng.min, -1), abs(pix_n1))
        step = max(estep_n, estep_p)
        ticker.add_tick(0.0, True, True, formatter, data)
        add_ticks_logarithmic(Range(1, rng.max), emin_p, emax_p, step, ticker, formatter, data)
        add_ticks_logarithmic(Range(rng.min, -1), emin_n, emax_n, step, ticker, formatter, data)
    else:
        locator_log10(ticker, rng, pixels, formatter, data)


def add_ticks_custom(values, labels, n: int, ticker: Ticker, formatter, data) -> None:
    for i in range(n):
        if labels is not None:
            ticker.add_tick(values[i], False, True, label=labels[i])
        else:
            ticker.add_tick(values[i], False, True, formatter, data)


# --------------------------------------------------------------------------- #
# [SECTION] Context Menus
# --------------------------------------------------------------------------- #
AXIS_CONTEXTS = ("##XAxisContext", "##YAxisContext", "##ZAxisContext")
AXIS_LABELS = ("X-Axis", "Y-Axis", "Z-Axis")
PLANE_CONTEXTS = ("##YZPlaneContext", "##XZPlaneContext", "##XYPlaneContext")
PLANE_LABELS = ("YZ-Plane", "XZ-Plane", "XY-Plane")


def _popup_name(plot: Plot, name: str) -> str:
    return f"{name}{plot.id!r}"


def _widgets():
    from . import im_widgets
    return im_widgets


def show_legend_context_menu(legend: Legend, visible: bool) -> bool:
    w = _widgets()
    s = w.get_frame_height()
    ret = False
    changed, visible = w.checkbox("Show", visible)
    if changed:
        ret = True
    if w.radio_button("H", im_has_flag(legend.flags, LEGEND_FLAGS_HORIZONTAL)):
        legend.flags |= LEGEND_FLAGS_HORIZONTAL
    w.same_line()
    if w.radio_button("V", not im_has_flag(legend.flags, LEGEND_FLAGS_HORIZONTAL)):
        legend.flags &= ~LEGEND_FLAGS_HORIZONTAL
    size = (1.5 * s, s)
    rows = ((LOCATION_NORTH_WEST, LOCATION_NORTH, LOCATION_NORTH_EAST),
            (LOCATION_WEST, LOCATION_CENTER, LOCATION_EAST),
            (LOCATION_SOUTH_WEST, LOCATION_SOUTH, LOCATION_SOUTH_EAST))
    for row in rows:
        for k, loc in enumerate(row):
            label = _SHORT_LEGEND_LOCATION[loc]
            if loc == LOCATION_CENTER:
                w.invisible_button(label, size)
            elif w.button(label, size):
                legend.location = loc
            if k < 2:
                w.same_line(0.0, 2.0)
    return ret


def show_axis_context_menu(plot: Plot, axis_id: int) -> None:
    w = _widgets()
    axis = plot.axes[axis_id]
    always_locked = axis.is_range_locked() or axis.is_auto_fitting()
    label, grid = axis.has_label(), axis.has_grid_lines()
    ticks, labels = axis.has_tick_marks(), axis.has_tick_labels()
    size = axis.range.size()
    drag_speed = DBL_EPSILON * 1.0e13 if size <= DBL_EPSILON else 0.01 * size
    equal_aspect = im_has_flag(plot.flags, FLAGS_EQUAL)

    w.begin_disabled(always_locked)
    _c, axis.flags = w.checkbox_flags("##LockMin", axis.flags, AXIS_FLAGS_LOCK_MIN)
    w.end_disabled()
    w.same_line()
    w.begin_disabled(axis.is_locked_min() or always_locked)
    changed, temp_min = w.drag_float("Min", axis.range.min, drag_speed,
                                     axis.constraint_range.min, axis.range.max)
    if changed:
        axis.set_min(temp_min, True)
        if equal_aspect:
            plot.apply_equal_aspect(axis_id)
    w.end_disabled()

    w.begin_disabled(always_locked)
    _c, axis.flags = w.checkbox_flags("##LockMax", axis.flags, AXIS_FLAGS_LOCK_MAX)
    w.end_disabled()
    w.same_line()
    w.begin_disabled(axis.is_locked_max() or always_locked)
    changed, temp_max = w.drag_float("Max", axis.range.max, drag_speed,
                                     axis.range.min, axis.constraint_range.max)
    if changed:
        axis.set_max(temp_max, True)
        if equal_aspect:
            plot.apply_equal_aspect(axis_id)
    w.end_disabled()

    w.separator()
    _c, axis.flags = w.checkbox_flags("Auto-Fit", axis.flags, AXIS_FLAGS_AUTO_FIT)
    w.separator()
    changed, _v = w.checkbox("Invert", im_has_flag(axis.flags, AXIS_FLAGS_INVERT))
    if changed:
        axis.flags = im_flip_flag(axis.flags, AXIS_FLAGS_INVERT)
    w.separator()
    w.begin_disabled(not axis.label)
    if w.checkbox("Label", label)[0]:
        axis.flags = im_flip_flag(axis.flags, AXIS_FLAGS_NO_LABEL)
    w.end_disabled()
    if w.checkbox("Grid Lines", grid)[0]:
        axis.flags = im_flip_flag(axis.flags, AXIS_FLAGS_NO_GRID_LINES)
    if w.checkbox("Tick Marks", ticks)[0]:
        axis.flags = im_flip_flag(axis.flags, AXIS_FLAGS_NO_TICK_MARKS)
    if w.checkbox("Tick Labels", labels)[0]:
        axis.flags = im_flip_flag(axis.flags, AXIS_FLAGS_NO_TICK_LABELS)


def show_plane_context_menu(plot: Plot, plane_idx: int) -> None:
    w = _widgets()
    for i in range(3):
        if i == plane_idx:
            continue
        axis = plot.axes[i]
        w.push_id(i)
        if w.begin_menu(axis.get_label() if axis.has_label() else AXIS_LABELS[i]):
            show_axis_context_menu(plot, i)
            w.end_menu()
        w.pop_id()


def show_plot_context_menu(plot: Plot) -> None:
    w = _widgets()
    for i in range(3):
        axis = plot.axes[i]
        w.push_id(i)
        if w.begin_menu(axis.get_label() if axis.has_label() else AXIS_LABELS[i]):
            show_axis_context_menu(plot, i)
            w.end_menu()
        w.pop_id()
    w.separator()
    if w.begin_menu("Box"):
        for i, name in enumerate(("Scale X", "Scale Y", "Scale Z")):
            changed, v = w.drag_float(name, plot.axes[i].ndc_scale, 0.01, 0.1, 3.0)
            if changed:
                plot.axes[i].ndc_scale = max(v, 0.01)
        w.end_menu()
    w.separator()
    if w.begin_menu("Legend"):
        if show_legend_context_menu(plot.items.legend, not im_has_flag(plot.flags, FLAGS_NO_LEGEND)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_NO_LEGEND)
        w.end_menu()
    if w.begin_menu("Settings"):
        if w.menu_item("Equal", "", im_has_flag(plot.flags, FLAGS_EQUAL)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_EQUAL)
        if w.menu_item("Title", "", plot.has_title(), enabled=bool(plot.title)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_NO_TITLE)
        if w.menu_item("Clip", "", not im_has_flag(plot.flags, FLAGS_NO_CLIP)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_NO_CLIP)
        if w.menu_item("Mouse Position", "", not im_has_flag(plot.flags, FLAGS_NO_MOUSE_TEXT)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_NO_MOUSE_TEXT)
        w.end_menu()


# --------------------------------------------------------------------------- #
# [SECTION] Begin/End Plot
# --------------------------------------------------------------------------- #
def _calc_item_size(size, default_w: float, default_h: float):
    """``ImGui::CalcItemSize``."""
    w, h = float(size[0]), float(size[1])
    if w < 0.0 or h < 0.0:
        avail = _widgets().get_content_region_avail()
    if w == 0.0:
        w = default_w
    elif w < 0.0:
        w = max(4.0, avail[0] + w)
    if h == 0.0:
        h = default_h
    elif h < 0.0:
        h = max(4.0, avail[1] + h)
    return w, h


def begin_plot(title_id: str, size=(-1.0, 0.0), flags: int = 0) -> bool:
    """``BeginPlot``. If it returns True, :func:`end_plot` must be called."""
    gp = _gp()
    ctx = _im()
    owner = (id(ctx), ctx.io.frame_count)
    if gp.current_plot is not None:
        if gp.current_owner == owner:
            raise RuntimeError("Mismatched BeginPlot()/EndPlot()!")
        gp.current_plot = None                 # left open by an earlier frame
    plot_id = ctx.get_id(title_id)
    just_created = plot_id not in gp.plots
    plot = gp.plots.get(plot_id)
    if plot is None:
        plot = gp.plots[plot_id] = Plot()
    gp.current_plot = plot
    gp.current_items = plot.items
    gp.current_owner = owner
    plot.id = plot_id
    plot.items.id = (plot_id, "##items")
    plot.just_created = just_created
    if just_created:
        plot.rotation = Quat(*plot.initial_rotation)
        plot.fit_this_frame = True
        plot.axes = [Axis(), Axis(), Axis()]
        for axis in plot.axes:
            axis.fit_this_frame = True
    if plot.previous_flags != flags:
        plot.flags = flags
    plot.previous_flags = flags
    plot.setup_locked = False
    plot.open_context_this_frame = False
    plot.rotation_cond = COND_NONE
    plot.set_title(title_id)

    style = gp.style
    fw, fh = _calc_item_size(size, style.plot_default_size[0], style.plot_default_size[1])
    if fw < style.plot_min_size[0] and size[0] < 0.0:
        fw = style.plot_min_size[0]
    if fh < style.plot_min_size[1] and size[1] < 0.0:
        fh = style.plot_min_size[1]
    x, y, w, h = ctx.item_size(fw, fh)
    plot.frame_rect = (x, y, x + fw, y + fh)
    ctx.item_add((x, y, fw, fh), plot_id)
    if not ctx._overlaps_clip((x, y, fw, fh)):
        gp.current_plot = gp.current_items = gp.current_item = None
        return False
    plot.items.legend.reset()
    for axis in plot.axes:
        axis.reset()
    ctx.draw.push_clip_rect(plot.frame_rect[:2], plot.frame_rect[2:], True)
    return True


def end_plot() -> None:
    """``EndPlot``: sort and draw the items, fit, legend, menus."""
    gp = _gp()
    plot = gp.current_plot
    if plot is None:
        raise RuntimeError("Mismatched BeginPlot()/EndPlot()!")
    ctx = _im()
    # Lock setup first: an empty plot never reached it, and the box, the
    # rotation and the input are all drawn and handled there.
    setup_lock()
    plot.draw_list.sorted_move_to_draw_list(ctx.draw.p)

    if plot.fit_this_frame:
        plot.fit_this_frame = False
        if not im_has_flag(plot.flags, FLAGS_EQUAL):
            for axis in plot.axes:
                if axis.fit_this_frame:
                    axis.fit_this_frame = False
                    axis.apply_fit()
        else:
            ref_axis, max_aspect = AXIS_X, 0.0
            for i, axis in enumerate(plot.axes):
                if axis.fit_this_frame:
                    axis.fit_this_frame = False
                    axis.apply_fit()
                    aspect = axis.get_aspect()
                    if aspect > max_aspect:
                        max_aspect, ref_axis = aspect, i
            plot.apply_equal_aspect(ref_axis)

    ctx.draw.pop_clip_rect()                   # plot rect
    plot.items.legend.hovered = False
    render_legend()
    render_mouse_pos()

    w = _widgets()
    name = _popup_name(plot, "##LegendContext")
    if w.begin_popup(name):
        w.text("Legend")
        w.separator()
        if show_legend_context_menu(plot.items.legend, not im_has_flag(plot.flags, FLAGS_NO_LEGEND)):
            plot.flags = im_flip_flag(plot.flags, FLAGS_NO_LEGEND)
        w.end_popup()
    for i in range(3):
        axis = plot.axes[i]
        if w.begin_popup(_popup_name(plot, AXIS_CONTEXTS[i])):
            w.text(axis.get_label() if axis.has_label() else "%s-Axis" % "XYZ"[i])
            w.separator()
            show_axis_context_menu(plot, i)
            w.end_popup()
    for i in range(3):
        if w.begin_popup(_popup_name(plot, PLANE_CONTEXTS[i])):
            w.text(PLANE_LABELS[i])
            w.separator()
            show_plane_context_menu(plot, i)
            w.end_popup()
    if w.begin_popup(_popup_name(plot, "##PlotContext")):
        show_plot_context_menu(plot)
        w.end_popup()

    ctx.draw.pop_clip_rect()                   # frame rect
    gp.current_plot = gp.current_items = gp.current_item = None
    for item in plot.items.order:
        item.seen_this_frame = False


__all__ += ["begin_plot", "end_plot"]


# --------------------------------------------------------------------------- #
# [SECTION] Setup
# --------------------------------------------------------------------------- #
ANIMATION_ANGULAR_VELOCITY = 2 * 3.1415


def calc_animation_time(q0: Quat, q1: Quat) -> float:
    dot = _clamp(q0.dot(q1), -1.0, 1.0)
    return 2.0 * math.acos(abs(dot)) / ANIMATION_ANGULAR_VELOCITY


def _setup_plot(what: str) -> Plot:
    gp = _gp()
    if gp.current_plot is None or gp.current_plot.setup_locked:
        raise RuntimeError(f"{what}() needs to be called after BeginPlot() and before any "
                           "setup locking functions (e.g. PlotX)!")
    return gp.current_plot


def setup_axis(idx: int, label: str | None = None, flags: int = 0) -> None:
    plot = _setup_plot("SetupAxis")
    axis = plot.axes[idx]
    if axis.previous_flags != flags:
        axis.flags = flags
    axis.previous_flags = flags
    axis.set_label(label)


def setup_axis_limits(idx: int, min_lim: float, max_lim: float, cond: int = COND_ONCE) -> None:
    plot = _setup_plot("SetupAxisLimits")
    axis = plot.axes[idx]
    if not plot.initialized or cond == COND_ALWAYS:
        axis.set_range(min_lim, max_lim)
        axis.range_cond = cond
        axis.fit_this_frame = False
        if im_has_flag(plot.flags, FLAGS_EQUAL):
            plot.apply_equal_aspect(idx)


def setup_axis_format(idx: int, formatter, data=None) -> None:
    """``SetupAxisFormat``: *formatter* is ``f(value, data) -> str``; a
    printf string is accepted as well, as sugar for ``formatter_default``."""
    plot = _setup_plot("SetupAxisFormat")
    axis = plot.axes[idx]
    if isinstance(formatter, str):
        formatter, data = formatter_default, formatter
    axis.formatter = formatter
    axis.formatter_data = data


def setup_axis_ticks(idx: int, *args, labels=None, keep_default: bool = False) -> None:
    """``SetupAxisTicks``, both overloads:
    ``(axis, values[, n_ticks][, labels][, keep_default])`` and
    ``(axis, v_min, v_max, n_ticks[, labels][, keep_default])``."""
    plot = _setup_plot("SetupAxisTicks")
    axis = plot.axes[idx]
    args = list(args)
    if args and hasattr(args[0], "__len__"):
        values = list(args.pop(0))
        n_ticks = int(args.pop(0)) if args and isinstance(args[0], int) and not isinstance(args[0], bool) else len(values)
    else:
        v_min, v_max = float(args.pop(0)), float(args.pop(0))
        n_ticks = max(int(args.pop(0)), 2)
        step = (v_max - v_min) / (n_ticks - 1)
        values = [v_min + i * step for i in range(n_ticks)]
    if args:
        labels = args.pop(0)
    if args:
        keep_default = bool(args.pop(0))
    axis.show_default_ticks = keep_default
    add_ticks_custom(values, labels, n_ticks, axis.ticker,
                     axis.formatter if axis.formatter else formatter_default,
                     axis.formatter_data if (axis.formatter and axis.formatter_data)
                     else IMPLOT3D_LABEL_FORMAT)


def setup_axis_scale(idx: int, scale, inverse=None, data=None) -> None:
    """``SetupAxisScale``: a built-in ``SCALE_*``, or ``(forward, inverse, data)``."""
    plot = _setup_plot("SetupAxisScale")
    axis = plot.axes[idx]
    if callable(scale):
        axis.scale = IMPLOT3D_AUTO
        axis.transform_forward, axis.transform_inverse = scale, inverse
        axis.transform_data = data
        return
    axis.scale = scale
    if scale == SCALE_LOG10:
        axis.transform_forward, axis.transform_inverse = transform_forward_log10, transform_inverse_log10
        axis.transform_data = None
        axis.locator = locator_log10
        axis.constraint_range = Range(FLT_MIN, math.inf)
    elif scale == SCALE_SYMLOG:
        axis.transform_forward, axis.transform_inverse = transform_forward_symlog, transform_inverse_symlog
        axis.transform_data = None
        axis.locator = locator_symlog
        axis.constraint_range = Range(-math.inf, math.inf)
    else:
        axis.transform_forward = axis.transform_inverse = axis.transform_data = None
        axis.locator = None
        axis.constraint_range = Range(-math.inf, math.inf)


def setup_axis_limits_constraints(idx: int, v_min: float, v_max: float) -> None:
    axis = _setup_plot("SetupAxisLimitsConstraints").axes[idx]
    axis.constraint_range.min, axis.constraint_range.max = float(v_min), float(v_max)


def setup_axis_zoom_constraints(idx: int, zoom_min: float, zoom_max: float) -> None:
    axis = _setup_plot("SetupAxisZoomConstraints").axes[idx]
    axis.constraint_zoom.min, axis.constraint_zoom.max = float(zoom_min), float(zoom_max)


def setup_axes(x_label=None, y_label=None, z_label=None, x_flags: int = 0,
               y_flags: int = 0, z_flags: int = 0) -> None:
    setup_axis(AXIS_X, x_label, x_flags)
    setup_axis(AXIS_Y, y_label, y_flags)
    setup_axis(AXIS_Z, z_label, z_flags)


def setup_axes_limits(x_min, x_max, y_min, y_max, z_min, z_max, cond: int = COND_ONCE) -> None:
    setup_axis_limits(AXIS_X, x_min, x_max, cond)
    setup_axis_limits(AXIS_Y, y_min, y_max, cond)
    setup_axis_limits(AXIS_Z, z_min, z_max, cond)
    if cond == COND_ONCE:
        _gp().current_plot.fit_this_frame = False


def setup_box_rotation(*args, animate: bool = False, cond: int = COND_ONCE) -> None:
    """``SetupBoxRotation(elevation, azimuth[, animate][, cond])`` in degrees,
    or ``SetupBoxRotation(quat[, animate][, cond])``."""
    args = list(args)
    if isinstance(args[0], Quat):
        rotation = args.pop(0)
    else:
        elev, azim = float(args.pop(0)), float(args.pop(0))
        rotation = Quat.from_el_az(elev * math.pi / 180.0, azim * math.pi / 180.0)
    if args:
        animate = bool(args.pop(0))
    if args:
        cond = int(args.pop(0))
    plot = _setup_plot("SetupBoxRotation")
    if not plot.initialized or cond == COND_ALWAYS:
        if not animate:
            plot.rotation = Quat(*rotation)
            plot.animation_time = 0.0
        else:
            plot.rotation_animation_end = Quat(*rotation)
            plot.animation_time = calc_animation_time(plot.rotation, plot.rotation_animation_end)
        plot.rotation_cond = cond


def setup_box_initial_rotation(*args) -> None:
    """``SetupBoxInitialRotation(elevation, azimuth)`` in degrees, or ``(quat)``."""
    if isinstance(args[0], Quat):
        rotation = args[0]
    else:
        rotation = Quat.from_el_az(float(args[0]) * math.pi / 180.0,
                                   float(args[1]) * math.pi / 180.0)
    _setup_plot("SetupBoxInitialRotation").initial_rotation = Quat(*rotation)


def setup_box_scale(x: float, y: float, z: float) -> None:
    plot = _setup_plot("SetupBoxScale")
    if not (x > 0.0 and y > 0.0 and z > 0.0):
        raise ValueError("SetupBoxScale() requires all aspect ratios to be greater than 0!")
    plot.axes[0].ndc_scale, plot.axes[1].ndc_scale, plot.axes[2].ndc_scale = float(x), float(y), float(z)


def setup_legend(location: int, flags: int = 0) -> None:
    _setup_plot("SetupLegend")
    legend = _gp().current_items.legend
    if legend.previous_location != location:
        legend.location = location
    legend.previous_location = location
    if legend.previous_flags != flags:
        legend.flags = flags
    legend.previous_flags = flags


__all__ += ["setup_axis", "setup_axis_limits", "setup_axis_format", "setup_axis_ticks",
            "setup_axis_scale", "setup_axis_limits_constraints", "setup_axis_zoom_constraints",
            "setup_axes", "setup_axes_limits", "setup_box_rotation",
            "setup_box_initial_rotation", "setup_box_scale", "setup_legend"]


# --------------------------------------------------------------------------- #
# [SECTION] Plot Utils
# --------------------------------------------------------------------------- #
def _current_plot(what: str) -> Plot:
    plot = _gp().current_plot
    if plot is None:
        raise RuntimeError(f"{what}() needs to be called between BeginPlot() and EndPlot()!")
    return plot


def get_current_plot() -> Plot | None:
    return _gp().current_plot


def bust_plot_cache() -> None:
    _gp().plots.clear()


def _xyz(args):
    if len(args) == 1:
        return tuple(args[0])
    return (float(args[0]), float(args[1]), float(args[2]))


def plot_to_pixels(*point):
    """``PlotToPixels(point)`` or ``PlotToPixels(x, y, z)``: screen ``(x, y)``."""
    plot = _current_plot("PlotToPixels")
    setup_lock()
    x, y, z = _xyz(point)
    return _Projector(plot).to_pixels(x, y, z)


def plot_to_ndc(point) -> Point:
    plot = _current_plot("PlotToNDC")
    setup_lock()
    return Point(*_Projector(plot).ndc(point[0], point[1], point[2]))


def ndc_to_plot(point) -> Point:
    plot = _current_plot("NDCToPlot")
    setup_lock()
    out = Point()
    for i in range(3):
        axis = plot.axes[i]
        ndc_range = 0.5 * axis.ndc_scale
        v = point[i]
        t = (ndc_range - v) if im_has_flag(axis.flags, AXIS_FLAGS_INVERT) else (v + ndc_range)
        out[i] = axis.ndc_to_plot(t / axis.ndc_scale)
    return out


def ndc_to_pixels(point):
    plot = _current_plot("NDCToPixels")
    setup_lock()
    return _Projector(plot).ndc_to_pixels(point[0], point[1], point[2])


def pixels_to_ndc_ray(pix) -> Ray:
    plot = _current_plot("PixelsToNDCRay")
    setup_lock()
    zoom = plot.get_view_scale()
    x0, y0, x1, y1 = plot.plot_rect
    x = (pix[0] - (x0 + x1) * 0.5) / zoom
    y = -(pix[1] - (y0 + y1) * 0.5) / zoom
    inv = plot.rotation.inverse()
    near = inv * (x, y, 10.0)
    far = inv * (x, y, -10.0)
    return Ray(near, (far - near).normalized())


def ndc_ray_to_plot_ray(ray: Ray) -> Ray:
    _current_plot("NDCRayToPlotRay")
    origin = ndc_to_plot(ray.origin)
    along = ndc_to_plot(ray.origin + ray.direction)
    return Ray(origin, (along - origin).normalized())


def pixels_to_plot_ray(*pix) -> Ray:
    """``PixelsToPlotRay``: the ray through a pixel, in plot coordinates."""
    _current_plot("PixelsToPlotRay")
    pix = pix[0] if len(pix) == 1 else pix
    return ndc_ray_to_plot_ray(pixels_to_ndc_ray(pix))


_NAN_POINT = (math.nan, math.nan, math.nan)


def pixels_to_plot_plane(*args, mask: bool = True) -> Point:
    """``PixelsToPlotPlane(pix, plane, mask=True)`` or ``(x, y, plane, mask)``.

    NaNs when the ray misses the plane (or, masked, the box face).
    """
    args = list(args)
    pix = args.pop(0) if hasattr(args[0], "__len__") else (args.pop(0), args.pop(0))
    plane = int(args.pop(0))
    if args:
        mask = bool(args.pop(0))
    plot = _current_plot("PixelsToPlotPlane")
    ray = pixels_to_ndc_ray(pix)
    o, d = ray.origin, ray.direction
    active_faces, _p2d = compute_active_faces(plot.rotation, plot.axes)
    coord = (0.5 if active_faces[plane] else -0.5) * plot.axes[plane].ndc_scale
    denom, numer = d[plane], coord - o[plane]
    if abs(denom) < 1e-12:
        return Point(*_NAN_POINT)
    t = numer / denom
    if t < 0.0:
        return Point(*_NAN_POINT)
    p = o + d * t
    if mask:
        bs = plot.get_box_scale()
        q = Point(p.x, p.y, p.z)
        q[plane] = 0.0
        if not (-0.5 * bs.x <= q.x <= 0.5 * bs.x and -0.5 * bs.y <= q.y <= 0.5 * bs.y
                and -0.5 * bs.z <= q.z <= 0.5 * bs.z):
            return Point(*_NAN_POINT)
    return ndc_to_plot(p)


def get_plot_rect_pos():
    plot = _current_plot("GetPlotRectPos")
    setup_lock()
    return plot.plot_rect[:2]


def get_plot_rect_size():
    plot = _current_plot("GetPlotRectSize")
    setup_lock()
    x0, y0, x1, y1 = plot.plot_rect
    return (x1 - x0, y1 - y0)


def get_frame_pos():
    return _current_plot("GetFramePos").frame_rect[:2]


def get_frame_size():
    x0, y0, x1, y1 = _current_plot("GetFrameSize").frame_rect
    return (x1 - x0, y1 - y0)


#: Obsolete in the reference (v0.3), kept there until v1.0.
get_plot_pos, get_plot_size = get_plot_rect_pos, get_plot_rect_size

__all__ += ["plot_to_pixels", "plot_to_ndc", "ndc_to_plot", "ndc_to_pixels",
            "pixels_to_ndc_ray", "ndc_ray_to_plot_ray", "pixels_to_plot_ray",
            "pixels_to_plot_plane", "get_plot_rect_pos", "get_plot_rect_size",
            "get_frame_pos", "get_frame_size", "get_plot_pos", "get_plot_size",
            "get_current_plot", "bust_plot_cache"]


# --------------------------------------------------------------------------- #
# [SECTION] Setup Utils -- input
# --------------------------------------------------------------------------- #
MOUSE_CURSOR_DRAG_THRESHOLD = 5.0
MOUSE_DRAG_THRESHOLD = 6.0          # io.MouseDragThreshold
MOUSE_DOUBLE_CLICK_TIME = 0.30      # io.MouseDoubleClickTime


def _mouse_drag_delta(io, button: int):
    """``GetMouseDragDelta(button)`` with ImGui's lock threshold."""
    if not io.mouse_down[button]:
        return (0.0, 0.0)
    dx, dy = io.mouse_drag_delta(button)
    if dx * dx + dy * dy < MOUSE_DRAG_THRESHOLD * MOUSE_DRAG_THRESHOLD:
        return (0.0, 0.0)
    return (dx, dy)


def handle_input(plot: Plot) -> None:
    """``HandleInput``: pan (left drag), zoom (wheel / middle drag), rotate
    (right drag), fit (double left), reset/snap rotation (double right),
    context menus (right click)."""
    if im_has_flag(plot.flags, FLAGS_NO_INPUTS):
        return
    ctx = _im()
    io = ctx.io
    if io.mouse_clicked[1]:
        plot.right_clicked_time = io.now

    plot_clicked, plot.hovered, plot.held = _button_behavior(plot.plot_rect, plot.id)
    rx, ry = _mouse_drag_delta(io, 1)
    rotating = rx * rx + ry * ry > MOUSE_CURSOR_DRAG_THRESHOLD
    axis_equal = im_has_flag(plot.flags, FLAGS_EQUAL)
    allow_rotate = not im_has_flag(plot.flags, FLAGS_NO_ROTATE)
    allow_pan = not im_has_flag(plot.flags, FLAGS_NO_PAN)
    allow_zoom = not im_has_flag(plot.flags, FLAGS_NO_ZOOM)

    # HOVERING STATE
    active_faces, corners_pix, corners, plane_2d, axis_corners = get_axes_parameters(plot)
    hovered_plane = get_mouse_over_plane(active_faces, corners_pix)
    hovered_plane_idx = hovered_plane
    hovered_axis, hovered_edge_idx = get_mouse_over_axis(plot, corners_pix, plane_2d, axis_corners)
    if hovered_axis != -1:
        hovered_plane_idx = hovered_plane = -1

    if not io.mouse_down[0] and not io.mouse_down[2]:
        for axis in plot.axes:
            axis.held = False
    if not plot.held:
        plot.held_edge_idx = plot.held_plane_idx = -1

    any_axis_held = any(a.held for a in plot.axes)
    if not any_axis_held:
        for a in plot.axes:
            a.hovered = False
        if hovered_axis != -1:
            plot.axes[hovered_axis].hovered = True
        elif hovered_plane != -1:
            plot.axes[(hovered_plane + 1) % 3].hovered = True
            plot.axes[(hovered_plane + 2) % 3].hovered = True
        else:
            for a in plot.axes:
                a.hovered = True

    ax = plot.axes
    mouse_plane = PLANE_XY
    if plane_2d != -1:
        mouse_plane = plane_2d
    elif ax[1].hovered and ax[2].hovered:
        mouse_plane = PLANE_YZ
    elif ax[0].hovered and ax[2].hovered:
        mouse_plane = PLANE_XZ
    elif ax[0].hovered and ax[1].hovered:
        mouse_plane = PLANE_XY
    elif plot.held_edge_idx != -1 or hovered_edge_idx != -1:
        edge = plot.held_edge_idx if plot.held_edge_idx != -1 else hovered_edge_idx
        (face0, plane0), (face1, plane1) = EDGE_TO_FACES[edge]
        face0_active = (not active_faces[face0]) if face0 < 3 else active_faces[face0 - 3]
        face1_active = (not active_faces[face1]) if face1 < 3 else active_faces[face1 - 3]
        mouse_plane = plane0 if face0_active else plane1 if face1_active else plane0
    mouse_pos = io.mouse_pos
    mouse_pos_plot = pixels_to_plot_plane(mouse_pos, mouse_plane, False)
    proj = _Projector(plot)

    # AUTO FIT
    if (plot_clicked and (io.mouse_double_clicked[0] or io.mouse_double_clicked[2])
            and allow_pan and allow_zoom):
        plot.fit_this_frame = True
        for a in ax:
            a.fit_this_frame = a.hovered
    for a in ax:
        if a.is_auto_fitting():
            plot.fit_this_frame = True
            a.fit_this_frame = True

    # TRANSLATION
    if plot.held and io.mouse_down[0] and allow_pan:
        delta = io.mouse_delta
        if ax[0].hovered and ax[1].hovered and ax[2].hovered:
            zoom = plot.get_view_scale()
            delta_ndc = plot.rotation.inverse() * (delta[0] / zoom, -delta[1] / zoom, 0.0)
            p_min_ndc, p_max_ndc = Point(), Point()
            for i in range(3):
                half = 0.5 * ax[i].ndc_scale
                p_min_ndc[i] = -half - delta_ndc[i]
                p_max_ndc[i] = half - delta_ndc[i]
            p_min_plt, p_max_plt = ndc_to_plot(p_min_ndc), ndc_to_plot(p_max_ndc)
            for i in range(3):
                if ax[i].hovered:
                    new_min = min(p_min_plt[i], p_max_plt[i])
                    new_max = max(p_min_plt[i], p_max_plt[i])
                    increasing = new_min > ax[i].range.min
                    if ((new_min != ax[i].range.min or new_max != ax[i].range.max)
                            and not ax[i].is_pan_locked(increasing)):
                        ax[i].set_range(new_min, new_max)
                        if axis_equal:
                            plot.apply_equal_aspect(i)
                    ax[i].held = True
                if not any_axis_held:
                    plot.held_edge_idx, plot.held_plane_idx = hovered_edge_idx, hovered_plane_idx
        elif ax[0].hovered or ax[1].hovered or ax[2].hovered:
            for i in range(3):
                if ax[i].hovered:
                    axis = ax[i]
                    p_min, p_max = Point(*mouse_pos_plot), Point(*mouse_pos_plot)
                    p_min[i], p_max[i] = axis.range.min, axis.range.max
                    pix_min = proj.to_pixels(*p_min)
                    pix_max = proj.to_pixels(*p_max)
                    pix_min = (pix_min[0] - delta[0], pix_min[1] - delta[1])
                    pix_max = (pix_max[0] - delta[0], pix_max[1] - delta[1])
                    new_min = pixels_to_plot_plane(pix_min, mouse_plane, False)[i]
                    new_max = pixels_to_plot_plane(pix_max, mouse_plane, False)[i]
                    increasing = new_min < axis.range.min
                    if ((new_min != axis.range.min or new_max != axis.range.max)
                            and not axis.is_pan_locked(increasing)):
                        axis.set_range(new_min, new_max)
                        if axis_equal:
                            plot.apply_equal_aspect(i)
                    axis.held = True
                if not any_axis_held:
                    plot.held_edge_idx, plot.held_plane_idx = hovered_edge_idx, hovered_plane_idx

    # ROTATION: double right click resets / snaps to a plane
    if (plot.held and io.mouse_double_clicked[1] and not plot.is_rotation_locked()
            and allow_rotate):
        end = Quat(*plot.rotation)
        if hovered_plane == -1:
            end = Quat(*plot.initial_rotation)
        else:
            normal = Point(0.0, 0.0, 0.0)
            normal[hovered_plane] = -1.0 if active_faces[hovered_plane] else 1.0
            if im_has_flag(ax[hovered_plane].flags, AXIS_FLAGS_INVERT):
                normal[hovered_plane] *= -1
            align_normal = Quat.from_two_vectors(end * normal, (0.0, 0.0, 1.0))
            end = align_normal * end
            if hovered_plane != 2:
                align_up = Quat.from_two_vectors(end * (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
                end = align_up * end
            else:
                up = Point(0.0, 1.0, 0.0)
                candidates = [end * (1.0, 0.0, 0.0), end * (0.0, 1.0, 0.0),
                              end * (-1.0, 0.0, 0.0), end * (0.0, -1.0, 0.0)]
                best = candidates[0]
                for c in candidates[1:]:
                    if c.dot(up) > best.dot(up):
                        best = c
                end = Quat.from_two_vectors(best, up) * end
        plot.rotation_animation_end = end
        plot.animation_time = calc_animation_time(plot.rotation, plot.rotation_animation_end)

    # ROTATION: right drag
    if plot.held and io.mouse_down[1] and not plot.is_rotation_locked() and allow_rotate:
        delta = io.mouse_delta
        angle_x = delta[0] * (3.1415 / 180.0)
        angle_y = delta[1] * (3.1415 / 180.0)
        if plot.drag_rotation_axis == Point(0.0, 0.0, 0.0):
            up_vector = plot.rotation * (0.0, 0.0, 1.0)
            plot.drag_rotation_axis = (Point(0.0, 0.0, -1.0) if up_vector.z < 0.0
                                       else Point(0.0, 0.0, 1.0))
        quat_x = Quat.from_angle_axis(angle_y, (1.0, 0.0, 0.0))
        quat_z = Quat.from_angle_axis(angle_x, plot.drag_rotation_axis)
        plot.rotation = quat_x * plot.rotation * quat_z
        plot.rotation.normalize()
    else:
        plot.drag_rotation_axis = Point(0.0, 0.0, 0.0)

    # ZOOM
    if plot.hovered and allow_zoom and (io.mouse_down[2] or io.mouse_wheel != 0.0):
        zoom_rate = (-0.01 * io.mouse_delta[1]) if io.mouse_down[2] else (-0.1 * io.mouse_wheel)
        zoom_around_mouse = hovered_axis != -1 or hovered_plane != -1
        ref_axis = AXIS_X
        for i in range(3):
            axis = ax[i]
            if not axis.hovered or axis.is_input_locked():
                continue
            p_min, p_max = Point(*mouse_pos_plot), Point(*mouse_pos_plot)
            p_min[i], p_max[i] = axis.range.min, axis.range.max
            pix_min, pix_max = proj.to_pixels(*p_min), proj.to_pixels(*p_max)
            mouse_pix = proj.to_pixels(*mouse_pos_plot)
            dist_min = math.hypot(pix_min[0] - mouse_pix[0], pix_min[1] - mouse_pix[1])
            dist_max = math.hypot(pix_max[0] - mouse_pix[0], pix_max[1] - mouse_pix[1])
            if zoom_around_mouse and (dist_min > 0 or dist_max > 0):
                pix_min = (mouse_pix[0] + (pix_min[0] - mouse_pix[0]) * (1.0 + zoom_rate),
                           mouse_pix[1] + (pix_min[1] - mouse_pix[1]) * (1.0 + zoom_rate))
                pix_max = (mouse_pix[0] + (pix_max[0] - mouse_pix[0]) * (1.0 + zoom_rate),
                           mouse_pix[1] + (pix_max[1] - mouse_pix[1]) * (1.0 + zoom_rate))
                axis.set_range(pixels_to_plot_plane(pix_min, mouse_plane, False)[i],
                               pixels_to_plot_plane(pix_max, mouse_plane, False)[i])
            else:
                ndc_limit = 0.5 * axis.ndc_scale
                zoom_factor = 1.0 + zoom_rate
                ndc_min, ndc_max = Point(), Point()
                ndc_min[i] = -ndc_limit * zoom_factor
                ndc_max[i] = ndc_limit * zoom_factor
                axis.set_range(ndc_to_plot(ndc_min)[i], ndc_to_plot(ndc_max)[i])
            axis.held = True
            ref_axis = i
        if axis_equal:
            plot.apply_equal_aspect(ref_axis)
        if not any_axis_held:
            plot.held_edge_idx, plot.held_plane_idx = hovered_edge_idx, hovered_plane_idx

    # CONTEXT MENU
    if plot.held and io.mouse_clicked[1] and not im_has_flag(plot.flags, FLAGS_NO_MENUS):
        plot.context_click = True
    if rotating or (io.mouse_double_clicked[1] and allow_rotate):
        plot.context_click = False
    not_double_click = ((io.now - plot.right_clicked_time) > MOUSE_DOUBLE_CLICK_TIME
                        if allow_rotate else True)
    if plot.hovered and plot.context_click and not_double_click and not io.mouse_down[1]:
        plot.context_click = False
        plot.open_context_this_frame = True
    if plot.context_click:
        ctx.request_frame()                    # the double-click window has to run out

    names = [_popup_name(plot, n) for n in
             ("##LegendContext", "##PlotContext", *AXIS_CONTEXTS, *PLANE_CONTEXTS)]
    if plot_clicked and not plot.open_context_this_frame:
        for name in names:                     # a click on the plot closes its menus
            ctx.close_current_popup(name)
    if plot.open_context_this_frame:
        for name in names:
            ctx.close_current_popup(name)
        if plot.items.legend.hovered:
            ctx.open_popup(names[0])
        elif hovered_axis != -1:
            ctx.open_popup(_popup_name(plot, AXIS_CONTEXTS[hovered_axis]))
        elif hovered_plane != -1:
            ctx.open_popup(_popup_name(plot, PLANE_CONTEXTS[hovered_plane]))
        elif plot.hovered:
            ctx.open_popup(names[1])


def setup_lock() -> None:
    """``SetupLock``: finish setup, draw the frame and the box, handle input."""
    gp = _gp()
    plot = gp.current_plot
    if plot is None:
        raise RuntimeError("SetupLock() needs to be called between BeginPlot() and EndPlot()!")
    if plot.setup_locked:
        return
    plot.setup_locked = True
    ctx = _im()
    draw_list = ctx.draw
    for axis in plot.axes:
        if axis.formatter is None:
            axis.formatter = formatter_default
            if axis.formatter_data is None:
                axis.formatter_data = IMPLOT3D_LABEL_FORMAT
        if axis.locator is None:
            axis.locator = locator_default
    fx0, fy0, fx1, fy1 = plot.frame_rect
    draw_list.add_rect_filled((fx0, fy0), (fx1, fy1), u32_to_rgba(get_style_color_u32(COL_FRAME_BG)))
    pad = gp.style.plot_padding
    plot.canvas_rect = (fx0 + pad[0], fy0 + pad[1], fx1 - pad[0], fy1 - pad[1])
    plot.plot_rect = plot.canvas_rect

    if im_has_flag(plot.flags, FLAGS_EQUAL):
        xar, yar, zar = (a.get_aspect() for a in plot.axes)
        if not im_almost_equal(xar, yar) or not im_almost_equal(xar, zar):
            aspect = (xar + yar + zar) / 3.0
            for a in plot.axes:
                a.set_aspect(aspect)

    for axis in plot.axes:
        if axis.show_default_ticks:
            pixels = float(plot.get_view_scale() * axis.ndc_scale)
            axis.locator(axis.ticker, axis.range, pixels, axis.formatter, axis.formatter_data)
    for axis in plot.axes:
        axis.color_bg = get_style_color_u32(COL_AXIS_BG)
        axis.color_hov = get_style_color_u32(COL_AXIS_BG_HOVERED)
        axis.color_act = get_style_color_u32(COL_AXIS_BG_ACTIVE)

    if plot.has_title():
        add_text_centered(draw_list, ((fx0 + fx1) * 0.5, plot.canvas_rect[1]),
                          get_style_color_u32(COL_TITLE_TEXT), plot.get_title())
        x0, y0, x1, y1 = plot.plot_rect
        plot.plot_rect = (x0, y0 + _text_line_height() + gp.style.label_padding[1], x1, y1)

    if plot.animation_time > 0.0:
        dt = ctx.io.delta_time
        t = _clamp(dt / plot.animation_time, 0.0, 1.0)
        plot.animation_time -= dt
        if plot.animation_time < 0.0:
            plot.animation_time = 0.0
        plot.rotation = Quat.slerp(plot.rotation, plot.rotation_animation_end, t)
        ctx.request_frame()

    plot.initialized = True
    handle_input(plot)
    draw_list.push_clip_rect(plot.plot_rect[:2], plot.plot_rect[2:], True)
    render_plot_box(draw_list, plot)


# --------------------------------------------------------------------------- #
# [SECTION] Miscellaneous
# --------------------------------------------------------------------------- #
def get_plot_draw_list():
    """``GetPlotDrawList``: emtk's draw list for the current frame."""
    return _im().draw


__all__ += ["setup_lock", "get_plot_draw_list"]


# --------------------------------------------------------------------------- #
# [SECTION] Styles
# --------------------------------------------------------------------------- #
def get_style() -> Style:
    return _gp().style


def set_style(style: Style) -> None:
    _gp().style = style.copy()


def _set_colors(style, table) -> None:
    for idx, col in enumerate(table):
        style.colors[idx] = col


_A = IMPLOT3D_AUTO_COL


def style_colors_auto(dst: Style | None = None) -> None:
    style = dst if dst is not None else get_style()
    _set_colors(style, [_A] * COL_COUNT)


def style_colors_dark(dst: Style | None = None) -> None:
    style = dst if dst is not None else get_style()
    _set_colors(style, [(1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 0.07),
                        (0.0, 0.0, 0.0, 0.5), (0.43, 0.43, 0.5, 0.5), (0.08, 0.08, 0.08, 0.94),
                        (0.43, 0.43, 0.5, 0.5), (1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 1.0),
                        (1.0, 1.0, 1.0, 0.25), _A, _A, _A, _A])


def style_colors_light(dst: Style | None = None) -> None:
    style = dst if dst is not None else get_style()
    _set_colors(style, [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0, 1.0),
                        (0.42, 0.57, 1.0, 0.13), (0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0, 0.98),
                        (0.82, 0.82, 0.82, 0.8), (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0),
                        (1.0, 1.0, 1.0, 1.0), _A, _A, _A, _A])


def style_colors_classic(dst: Style | None = None) -> None:
    style = dst if dst is not None else get_style()
    _set_colors(style, [(0.9, 0.9, 0.9, 1.0), (0.9, 0.9, 0.9, 1.0), (0.43, 0.43, 0.43, 0.39),
                        (0.0, 0.0, 0.0, 0.35), (0.5, 0.5, 0.5, 0.5), (0.11, 0.11, 0.14, 0.92),
                        (0.5, 0.5, 0.5, 0.5), (0.9, 0.9, 0.9, 1.0), (0.9, 0.9, 0.9, 1.0),
                        (0.9, 0.9, 0.9, 0.25), _A, _A, _A, _A])


def show_style_selector(label: str) -> bool:
    w = _widgets()
    state = _demo_state("style_selector", idx=-1)
    changed, state["idx"] = w.combo(label, state["idx"], ["Auto", "Classic", "Dark", "Light"])
    if changed:
        (style_colors_auto, style_colors_classic, style_colors_dark,
         style_colors_light)[state["idx"]]()
        return True
    return False


def show_colormap_selector(label: str) -> bool:
    gp = _gp()
    w = _widgets()
    changed = False
    if w.begin_combo(label, gp.colormap_data.get_name(gp.style.colormap)):
        for i in range(gp.colormap_data.count):
            if w.selectable(gp.colormap_data.get_name(i), gp.style.colormap == i):
                gp.style.colormap = i
                bust_item_cache()
                changed = True
        w.end_combo()
    return changed


def push_style_color(idx: int, col) -> None:
    gp = _gp()
    gp.color_modifiers.append((idx, gp.style.colors[idx]))
    gp.style.colors[idx] = to_vec4(col)


def pop_style_color(count: int = 1) -> None:
    gp = _gp()
    if count > len(gp.color_modifiers):
        raise RuntimeError("You can't pop more modifiers than have been pushed!")
    for _ in range(count):
        idx, backup = gp.color_modifiers.pop()
        gp.style.colors[idx] = backup


def push_style_var(idx: int, val) -> None:
    gp = _gp()
    name = _STYLEVAR_FIELD[idx]
    current = getattr(gp.style, name)
    if isinstance(current, tuple) != isinstance(val, (tuple, list)):
        raise TypeError(f"PushStyleVar(): {name} takes {type(current).__name__}")
    gp.style_modifiers.append((idx, current))
    if isinstance(current, tuple):
        val = (float(val[0]), float(val[1]))
    elif isinstance(current, int):
        val = int(val)
    else:
        val = float(val)
    setattr(gp.style, name, val)


def pop_style_var(count: int = 1) -> None:
    gp = _gp()
    if count > len(gp.style_modifiers):
        raise RuntimeError("You can't pop more modifiers than have been pushed!")
    for _ in range(count):
        idx, backup = gp.style_modifiers.pop()
        setattr(gp.style, _STYLEVAR_FIELD[idx], backup)


def get_style_color_vec4(idx: int):
    return get_auto_color(idx) if is_color_auto(idx) else _gp().style.colors[idx]


def get_style_color_u32(idx: int) -> int:
    return color_convert_float4_to_u32(get_style_color_vec4(idx))


def next_marker() -> int:
    gp = _gp()
    if gp.current_items is None:
        raise RuntimeError("NextMarker() needs to be called between BeginPlot() and EndPlot()!")
    idx = gp.current_items.marker_idx % MARKER_COUNT
    gp.current_items.marker_idx += 1
    return idx


__all__ += ["get_style", "set_style", "style_colors_auto", "style_colors_dark",
            "style_colors_light", "style_colors_classic", "show_style_selector",
            "show_colormap_selector", "push_style_color", "pop_style_color",
            "push_style_var", "pop_style_var", "get_style_color_vec4",
            "get_style_color_u32", "next_marker"]


# --------------------------------------------------------------------------- #
# [SECTION] Colormaps
# --------------------------------------------------------------------------- #
def add_colormap(name: str, cols, qual: bool = True) -> int:
    """``AddColormap``: colours as floats, bytes or ``ImU32``."""
    gp = _gp()
    if len(cols) <= 1:
        raise ValueError("The colormap size must be greater than 1!")
    if gp.colormap_data.get_index(name) != -1:
        raise ValueError("The colormap name has already been used!")
    return gp.colormap_data.append(name, [to_u32(c) for c in cols], qual)


def get_colormap_count() -> int:
    return _gp().colormap_data.count


def get_colormap_name(cmap: int):
    return _gp().colormap_data.get_name(cmap)


def get_colormap_index(name: str) -> int:
    return _gp().colormap_data.get_index(name)


def push_colormap(cmap) -> None:
    """``PushColormap``, by index or by name."""
    gp = _gp()
    if isinstance(cmap, str):
        idx = gp.colormap_data.get_index(cmap)
        if idx == -1:
            raise ValueError("The colormap name is invalid!")
        cmap = idx
    if not 0 <= cmap < gp.colormap_data.count:
        raise ValueError("The colormap index is invalid!")
    gp.colormap_modifiers.append(gp.style.colormap)
    gp.style.colormap = cmap


def pop_colormap(count: int = 1) -> None:
    gp = _gp()
    if count > len(gp.colormap_modifiers):
        raise RuntimeError("You can't pop more modifiers than have been pushed!")
    for _ in range(count):
        gp.style.colormap = gp.colormap_modifiers.pop()


def next_colormap_color_u32() -> int:
    gp = _gp()
    if gp.current_items is None:
        raise RuntimeError("NextColormapColor() needs to be called between BeginPlot() and EndPlot()!")
    data = gp.colormap_data
    idx = gp.current_items.colormap_idx % data.get_key_count(gp.style.colormap)
    col = data.get_key_color(gp.style.colormap, idx)
    gp.current_items.colormap_idx += 1
    return col


def next_colormap_color():
    return color_convert_u32_to_float4(next_colormap_color_u32())


def _cmap(cmap: int) -> int:
    gp = _gp()
    cmap = gp.style.colormap if cmap == IMPLOT3D_AUTO else cmap
    if not 0 <= cmap < gp.colormap_data.count:
        raise ValueError("Invalid colormap index!")
    return cmap


def get_colormap_size(cmap: int = IMPLOT3D_AUTO) -> int:
    return _gp().colormap_data.get_key_count(_cmap(cmap))


def get_colormap_color_u32(idx: int, cmap: int = IMPLOT3D_AUTO) -> int:
    cmap = _cmap(cmap)
    data = _gp().colormap_data
    return data.get_key_color(cmap, idx % data.get_key_count(cmap))


def get_colormap_color(idx: int, cmap: int = IMPLOT3D_AUTO):
    return color_convert_u32_to_float4(get_colormap_color_u32(idx, cmap))


def sample_colormap_u32(t: float, cmap: int = IMPLOT3D_AUTO) -> int:
    return _gp().colormap_data.lerp_table(_cmap(cmap), t)


def sample_colormap(t: float, cmap: int = IMPLOT3D_AUTO):
    return color_convert_u32_to_float4(sample_colormap_u32(t, cmap))


def render_color_bar(colors, size: int, draw_list, bounds, vert: bool, reversed_: bool,
                     continuous: bool) -> None:
    """``RenderColorBar``: *bounds* is ``(x0, y0, x1, y1)``."""
    n = size - 1 if continuous else size
    x0, y0, x1, y1 = bounds
    step = ((y1 - y0) if vert else (x1 - x0)) / n
    for i in range(n):
        if reversed_:
            c1 = colors[size - i - 1]
            c2 = colors[size - i - 2] if continuous else c1
        else:
            c1 = colors[i]
            c2 = colors[i + 1] if continuous else c1
        a, b = u32_to_rgba(c1), u32_to_rgba(c2)
        if vert:
            ry0 = y0 + i * step
            pts = ((x0, ry0), (x1, ry0), (x1, ry0 + step), (x0, ry0 + step))
            cols = (a, a, b, b)
        else:
            rx0 = x0 + i * step
            pts = ((rx0, y0), (rx0 + step, y0), (rx0 + step, y1), (rx0, y1))
            cols = (a, b, b, a)
        _painter.gradient_triangle(draw_list.p, pts[0], pts[1], pts[2], cols[0], cols[1], cols[2])
        _painter.gradient_triangle(draw_list.p, pts[0], pts[2], pts[3], cols[0], cols[2], cols[3])


def colormap_slider(label: str, t: float, fmt: str = "", cmap: int = IMPLOT3D_AUTO):
    """``ColormapSlider``: ``(changed, t, colour)``."""
    t = _clamp(t, 0.0, 1.0)
    gp = _gp()
    cmap = _cmap(cmap)
    w = _widgets()
    ctx = _im()
    data = gp.colormap_data
    x, y = w.get_cursor_screen_pos()
    width = w.calc_item_width()
    h = w.get_frame_height()
    render_color_bar(data.get_keys(cmap), data.get_key_count(cmap), ctx.draw,
                     (x, y, x + width, y + h), False, False, not data.is_qual(cmap))
    changed, t = w.slider_float(label, t, 0.0, 1.0, fmt or "%.3f")
    return changed, t, color_convert_u32_to_float4(data.lerp_table(cmap, t))


def colormap_button(label: str, size=(0.0, 0.0), cmap: int = IMPLOT3D_AUTO) -> bool:
    """``ColormapButton`` (the demo's): the colormap drawn as a button."""
    gp = _gp()
    cmap = _cmap(cmap)
    w = _widgets()
    ctx = _im()
    data = gp.colormap_data
    x, y = w.get_cursor_screen_pos()
    shown = _display_text(label)
    tw, th = calc_text_size(shown)
    pad = ctx.style.frame_padding
    bw, bh = _calc_item_size(size, tw + pad[0] * 2, th + pad[1] * 2)
    render_color_bar(data.get_keys(cmap), data.get_key_count(cmap), ctx.draw,
                     (x, y, x + bw, y + bh), False, False, not data.is_qual(cmap))
    return w.invisible_button(label, (bw, bh))


def bust_item_cache() -> None:
    for plot in _gp().plots.values():
        plot.items.reset()


__all__ += ["add_colormap", "get_colormap_count", "get_colormap_name", "get_colormap_index",
            "push_colormap", "pop_colormap", "next_colormap_color", "next_colormap_color_u32",
            "get_colormap_size", "get_colormap_color", "get_colormap_color_u32",
            "sample_colormap", "sample_colormap_u32", "render_color_bar",
            "colormap_slider", "colormap_button", "bust_item_cache"]


# --------------------------------------------------------------------------- #
# [SECTION] Context Utils
# --------------------------------------------------------------------------- #
def _rgb(r, g, b):
    return IM_COL32(r, g, b, 255)


COLORMAPS = (
    ("Deep", True, (4289753676, 4283598045, 4285048917, 4283584196, 4289950337, 4284512403,
                    4291005402, 4287401100, 4285839820, 4291671396)),
    ("Dark", True, (4280031972, 4290281015, 4283084621, 4288892568, 4278222847, 4281597951,
                    4280833702, 4290740727, 4288256409)),
    ("Pastel", True, (4289639675, 4293119411, 4291161036, 4293184478, 4289124862, 4291624959,
                      4290631909, 4293712637, 4294111986)),
    ("Paired", True, (4293119554, 4290017311, 4287291314, 4281114675, 4288256763, 4280031971,
                      4285513725, 4278222847, 4292260554, 4288298346, 4288282623, 4280834481)),
    ("Viridis", False, (4283695428, 4285867080, 4287054913, 4287455029, 4287526954, 4287402273,
                        4286883874, 4285579076, 4283552122, 4280737725, 4280674301)),
    ("Plasma", False, (4287039501, 4288480321, 4289200234, 4288941455, 4287638193, 4286072780,
                       4284638433, 4283139314, 4281771772, 4280667900, 4280416752)),
    ("Hot", False, (4278190144, 4278190208, 4278190271, 4278190335, 4278206719, 4278223103,
                    4278239231, 4278255615, 4283826175, 4289396735, 4294967295)),
    ("Cool", False, (4294967040, 4294960666, 4294954035, 4294947661, 4294941030, 4294934656,
                     4294928025, 4294921651, 4294915020, 4294908646, 4294902015)),
    ("Pink", False, (4278190154, 4282532475, 4284308894, 4285690554, 4286879686, 4287870160,
                     4288794330, 4289651940, 4291685869, 4293392118, 4294967295)),
    ("Jet", False, (4289331200, 4294901760, 4294923520, 4294945280, 4294967040, 4289396565,
                    4283826090, 4278255615, 4278233855, 4278212095, 4278190335)),
    ("Twilight", False, (_rgb(226, 217, 226), _rgb(166, 191, 202), _rgb(109, 144, 192),
                         _rgb(95, 88, 176), _rgb(83, 30, 124), _rgb(47, 20, 54), _rgb(100, 25, 75),
                         _rgb(159, 60, 80), _rgb(192, 117, 94), _rgb(208, 179, 158),
                         _rgb(226, 217, 226))),
    ("RdBu", False, (_rgb(103, 0, 31), _rgb(178, 24, 43), _rgb(214, 96, 77), _rgb(244, 165, 130),
                     _rgb(253, 219, 199), _rgb(247, 247, 247), _rgb(209, 229, 240),
                     _rgb(146, 197, 222), _rgb(67, 147, 195), _rgb(33, 102, 172), _rgb(5, 48, 97))),
    ("BrBG", False, (_rgb(84, 48, 5), _rgb(140, 81, 10), _rgb(191, 129, 45), _rgb(223, 194, 125),
                     _rgb(246, 232, 195), _rgb(245, 245, 245), _rgb(199, 234, 229),
                     _rgb(128, 205, 193), _rgb(53, 151, 143), _rgb(1, 102, 94), _rgb(0, 60, 48))),
    ("PiYG", False, (_rgb(142, 1, 82), _rgb(197, 27, 125), _rgb(222, 119, 174), _rgb(241, 182, 218),
                     _rgb(253, 224, 239), _rgb(247, 247, 247), _rgb(230, 245, 208),
                     _rgb(184, 225, 134), _rgb(127, 188, 65), _rgb(77, 146, 33), _rgb(39, 100, 25))),
    ("Spectral", False, (_rgb(158, 1, 66), _rgb(213, 62, 79), _rgb(244, 109, 67), _rgb(253, 174, 97),
                         _rgb(254, 224, 139), _rgb(255, 255, 191), _rgb(230, 245, 152),
                         _rgb(171, 221, 164), _rgb(102, 194, 165), _rgb(50, 136, 189),
                         _rgb(94, 79, 162))),
    ("Greys", False, (IM_COL32_WHITE, IM_COL32_BLACK)),
)


def initialize_context(ctx: Context) -> None:
    reset_context(ctx)
    for name, qual, keys in COLORMAPS:
        ctx.colormap_data.append(name, keys, qual)


def reset_context(ctx: Context) -> None:
    ctx.plots = {}
    ctx.current_plot = ctx.current_items = ctx.current_item = None
    ctx.next_item_data.reset()
    ctx.style = Style()


__all__ += ["initialize_context", "reset_context", "COLORMAPS"]


# --------------------------------------------------------------------------- #
# [SECTION] Metrics
# --------------------------------------------------------------------------- #
def _demo_state(key: str, **defaults) -> dict:
    """What a C++ ``static`` inside a demo or tool function holds."""
    im_ctx = _core._CURRENT
    store = im_ctx.storage if im_ctx is not None else _MODULE_STATE
    state = store.setdefault(("__implot3d_state__", key), {})
    for k, v in defaults.items():
        state.setdefault(k, v)
    return state


_MODULE_STATE: dict = {}


def show_metrics_window() -> None:
    """``ShowMetricsWindow``: plots, axes, items and colormaps, as a tree."""
    w = _widgets()
    gp = _gp()
    io = _im().io
    st = _demo_state("metrics", t=0.5)
    w.begin("Metrics (ImPlot3D)")
    w.text("ImPlot3D " + IMPLOT3D_VERSION)
    w.text("Mouse Position: [%.0f,%.0f]" % tuple(io.mouse_pos))
    w.separator()
    if w.tree_node("Tools"):
        if w.button("Bust Plot Cache"):
            bust_plot_cache()
        w.same_line()
        if w.button("Bust Item Cache"):
            bust_item_cache()
        w.tree_pop()
    plots = list(gp.plots.values())
    if w.tree_node("Plots (%d)##Plots" % len(plots)):
        for p, plot in enumerate(plots):
            w.push_id(p)
            if w.tree_node("Plot [%r]##Plot" % (plot.id,)):
                if w.tree_node("Items (%d)##Items" % plot.items.get_item_count()):
                    for i, item in enumerate(plot.items.order):
                        w.push_id(i)
                        if w.tree_node("Item [%r]##Item" % (item.id,)):
                            _c, item.show = w.checkbox("Show", item.show)
                            w.bullet_text("Name: %s" % (item.name or "N/A"))
                            w.bullet_text("Hovered: %s" % str(item.legend_hovered).lower())
                            w.tree_pop()
                        w.pop_id()
                    w.tree_pop()
                if w.tree_node("Axes"):
                    active_faces, corners_pix, corners, plane_2d, axis_corners = get_axes_parameters(plot)
                    for a in range(3):
                        if plane_2d != -1 and plane_2d == a:
                            continue
                        if w.tree_node(AXIS_LABELS[a]):
                            axis = plot.axes[a]
                            w.bullet_text("Label: %s" % axis.get_label())
                            w.bullet_text("Flags: 0x%08X" % axis.flags)
                            w.bullet_text("Range: [%f,%f]" % (axis.range.min, axis.range.max))
                            w.bullet_text("NDC Scale: %f" % axis.ndc_scale)
                            w.bullet_text("Aspect: %f" % axis.get_aspect())
                            w.bullet_text("Ticks: %d" % axis.ticker.tick_count())
                            w.bullet_text("Hovered: %s  Held: %s" % (axis.hovered, axis.held))
                            w.tree_pop()
                    if plane_2d != -1:
                        w.bullet_text("Plane2D: %d %s" % (plane_2d, PLANE_LABELS[plane_2d]))
                    else:
                        w.bullet_text("3D Active Faces: [%s,%s,%s]=%d" % (
                            "X-max" if active_faces[0] else "X-min",
                            "Y-max" if active_faces[1] else "Y-min",
                            "Z-max" if active_faces[2] else "Z-min",
                            active_3d_faces_to_axis_lookup_index(active_faces)))
                    for c in range(8):
                        w.bullet_text("Corner %d: [%.2f,%.2f,%.2f] [%.2f,%.2f]" % (
                            c, corners[c].x, corners[c].y, corners[c].z, *corners_pix[c]))
                    w.tree_pop()
                w.bullet_text("Title: %s" % (plot.get_title() if plot.has_title() else "none"))
                w.bullet_text("Flags: 0x%08X" % plot.flags)
                w.bullet_text("Hovered: %s  Held: %s" % (plot.hovered, plot.held))
                w.bullet_text("Rotation: [%.2f,%.2f,%.2f,%.2f]" % tuple(plot.rotation))
                w.bullet_text("ViewScale: %.2f" % plot.get_view_scale())
                w.tree_pop()
            w.pop_id()
        w.tree_pop()
    if w.tree_node("Colormaps"):
        data = gp.colormap_data
        w.bullet_text("Colormaps:  %d" % data.count)
        for m in range(data.count):
            if w.tree_node(data.get_name(m)):
                w.bullet_text("Qualitative: %s" % str(data.is_qual(m)).lower())
                w.bullet_text("Key Count: %d" % data.get_key_count(m))
                w.bullet_text("Table Size: %d" % data.get_table_size(m))
                _c, st["t"], _col = colormap_slider("##Sample", st["t"], "%.3f", m)
                w.tree_pop()
        w.tree_pop()
    w.end()


__all__ += ["show_metrics_window"]


# --------------------------------------------------------------------------- #
# Items, meshes and the demo live in their own modules, as in the reference;
# the names are re-exported here so ``implot3d.plot_line`` is the one import.
# --------------------------------------------------------------------------- #
from .implot3d_items import *  # noqa: E402,F401,F403
from .implot3d_items import __all__ as _ITEMS  # noqa: E402
from .implot3d_meshes import *  # noqa: E402,F401,F403
from .implot3d_meshes import __all__ as _MESHES  # noqa: E402

__all__ += list(_ITEMS) + list(_MESHES)


def show_demo_window() -> None:
    """``ShowDemoWindow`` -- see :mod:`emtk.implot3d_demo`."""
    from .implot3d_demo import show_demo_window as _show
    _show()


def show_all_demos() -> None:
    from .implot3d_demo import show_all_demos as _show
    _show()


def show_style_editor(ref: Style | None = None) -> None:
    from .implot3d_demo import show_style_editor as _show
    _show(ref)


def show_about_window() -> None:
    from .implot3d_demo import show_about_window as _show
    _show()


__all__ += ["show_demo_window", "show_all_demos", "show_style_editor", "show_about_window"]


# --------------------------------------------------------------------------- #
# The C++ spellings of the functions and types, for a line-by-line port.
# --------------------------------------------------------------------------- #
def _cpp_name(snake: str) -> str:
    special = {"ndc": "NDC", "u32": "U32", "vec4": "Vec4", "el": "El", "az": "Az"}
    return "".join(special.get(part, part.capitalize()) for part in snake.split("_"))


_CPP_FUNCTIONS = [
    "create_context", "destroy_context", "get_current_context", "set_current_context",
    "begin_plot", "end_plot", "setup_axis", "setup_axis_limits", "setup_axis_format",
    "setup_axis_ticks", "setup_axis_scale", "setup_axis_limits_constraints",
    "setup_axis_zoom_constraints", "setup_axes", "setup_axes_limits", "setup_box_rotation",
    "setup_box_initial_rotation", "setup_box_scale", "setup_legend", "plot_scatter",
    "plot_line", "plot_triangle", "plot_quad", "plot_surface", "plot_mesh", "plot_image",
    "plot_text", "plot_dummy", "plot_to_pixels", "pixels_to_plot_ray", "pixels_to_plot_plane",
    "get_plot_rect_pos", "get_plot_rect_size", "get_plot_draw_list", "get_style", "set_style",
    "style_colors_auto", "style_colors_dark", "style_colors_light", "style_colors_classic",
    "push_style_color", "pop_style_color", "push_style_var", "pop_style_var",
    "get_style_color_vec4", "get_style_color_u32", "next_marker", "add_colormap",
    "get_colormap_count", "get_colormap_name", "get_colormap_index", "push_colormap",
    "pop_colormap", "next_colormap_color", "get_colormap_size", "get_colormap_color",
    "sample_colormap", "show_demo_window", "show_all_demos", "show_style_editor",
    "show_style_selector", "show_colormap_selector", "show_metrics_window",
    "show_about_window", "get_plot_pos", "get_plot_size", "plot_to_ndc", "ndc_to_plot",
    "ndc_to_pixels", "pixels_to_ndc_ray", "ndc_ray_to_plot_ray", "get_frame_pos",
    "get_frame_size", "setup_lock", "bust_plot_cache", "bust_item_cache", "get_current_plot",
    "begin_item", "end_item", "get_current_item",
]
for _snake in _CPP_FUNCTIONS:
    globals()[_cpp_name(_snake)] = globals()[_snake]
    __all__.append(_cpp_name(_snake))
del _snake

ImPlot3DPoint, ImPlot3DRay, ImPlot3DPlane, ImPlot3DBox = Point, Ray, Plane, Box
ImPlot3DRange, ImPlot3DQuat, ImPlot3DSpec, ImPlot3DStyle = Range, Quat, Spec, Style
ImPlot3DContext = Context
__all__ += ["ImPlot3DPoint", "ImPlot3DRay", "ImPlot3DPlane", "ImPlot3DBox",
            "ImPlot3DRange", "ImPlot3DQuat", "ImPlot3DSpec", "ImPlot3DStyle",
            "ImPlot3DContext"]
