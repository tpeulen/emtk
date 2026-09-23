"""``emtk.implot_internal`` -- ImPlot's ``implot_internal.h``, and the parts of
``implot.cpp`` everything else stands on.

Ported from epezent/implot at 7eeb916 (``junk/implot``, MIT; the licence is in
``licenses/``). This module holds what the reference keeps in its internal
header and in the context: the enumerations, :class:`PlotSpec`, the style and
the input map, the axis (:class:`Axis` = ``ImPlotAxis``, transforms, locks,
constraints, fitting), the tickers and locators (linear, log10, symlog, time),
the time utilities and formatters, the colormap tables, and the persistent
per-plot state (:class:`Plot`, :class:`Subplot`, :class:`ItemGroup`,
:class:`Legend`, :class:`Item`).

How ImPlot's global context maps onto emtk
------------------------------------------
ImPlot keeps one ``GImPlot``: the style, the colormaps, the input map, the
"next item/plot" data and the pools of plot and subplot state that must
outlive ``EndPlot``. emtk's contexts live for one frame, and what a widget
remembers across frames lives in the ``storage`` dict the host hands to
``emtk.frame`` -- so the split is:

* the **pools** (``Plots``, ``Subplots``, ``AlignmentData``) live in
  ``ctx.state("implot")``, keyed by the emtk id of the plot's title -- the
  same door every other emtk widget uses to remember itself;
* everything else -- style, colormaps, input map, the per-plot scratch that
  ``BeginPlot`` resets -- is module state (:data:`gp`), exactly as the
  reference's global is.

Colours are 0-255 RGBA tuples, as everywhere in emtk; ``None`` plays the part
of ``IMPLOT_AUTO_COL``.
"""
from __future__ import annotations

import calendar
import math
import time as _time
from typing import Any, Callable, Optional

from . import im_core as _core

# --------------------------------------------------------------------------- #
# [SECTION] Enums (implot.h)
# --------------------------------------------------------------------------- #
IMPLOT_AUTO = -1
AUTO_COL = None

AXIS_X1, AXIS_X2, AXIS_X3, AXIS_Y1, AXIS_Y2, AXIS_Y3 = range(6)
AXIS_COUNT = 6
NUM_X_AXES = AXIS_Y1
NUM_Y_AXES = AXIS_COUNT - NUM_X_AXES

# ImPlotProp_
(PROP_LINE_COLOR, PROP_LINE_COLORS, PROP_LINE_WEIGHT, PROP_FILL_COLOR, PROP_FILL_COLORS,
 PROP_FILL_ALPHA, PROP_MARKER, PROP_MARKER_SIZE, PROP_MARKER_SIZES, PROP_MARKER_LINE_COLOR,
 PROP_MARKER_LINE_COLORS, PROP_MARKER_FILL_COLOR, PROP_MARKER_FILL_COLORS, PROP_SIZE,
 PROP_OFFSET, PROP_STRIDE, PROP_FLAGS) = range(17)

# ImPlotFlags_
FLAGS_NONE = 0
FLAGS_NO_TITLE = 1 << 0
FLAGS_NO_LEGEND = 1 << 1
FLAGS_NO_MOUSE_TEXT = 1 << 2
FLAGS_NO_INPUTS = 1 << 3
FLAGS_NO_MENUS = 1 << 4
FLAGS_NO_BOX_SELECT = 1 << 5
FLAGS_NO_FRAME = 1 << 6
FLAGS_EQUAL = 1 << 7
FLAGS_CROSSHAIRS = 1 << 8
FLAGS_CANVAS_ONLY = (FLAGS_NO_TITLE | FLAGS_NO_LEGEND | FLAGS_NO_MENUS
                     | FLAGS_NO_BOX_SELECT | FLAGS_NO_MOUSE_TEXT)

# ImPlotAxisFlags_
AXIS_FLAGS_NONE = 0
AXIS_FLAGS_NO_LABEL = 1 << 0
AXIS_FLAGS_NO_GRID_LINES = 1 << 1
AXIS_FLAGS_NO_TICK_MARKS = 1 << 2
AXIS_FLAGS_NO_TICK_LABELS = 1 << 3
AXIS_FLAGS_NO_INITIAL_FIT = 1 << 4
AXIS_FLAGS_NO_MENUS = 1 << 5
AXIS_FLAGS_NO_SIDE_SWITCH = 1 << 6
AXIS_FLAGS_NO_HIGHLIGHT = 1 << 7
AXIS_FLAGS_OPPOSITE = 1 << 8
AXIS_FLAGS_FOREGROUND = 1 << 9
AXIS_FLAGS_INVERT = 1 << 10
AXIS_FLAGS_AUTO_FIT = 1 << 11
AXIS_FLAGS_RANGE_FIT = 1 << 12
AXIS_FLAGS_PAN_STRETCH = 1 << 13
AXIS_FLAGS_LOCK_MIN = 1 << 14
AXIS_FLAGS_LOCK_MAX = 1 << 15
AXIS_FLAGS_LOCK = AXIS_FLAGS_LOCK_MIN | AXIS_FLAGS_LOCK_MAX
AXIS_FLAGS_NO_DECORATIONS = (AXIS_FLAGS_NO_LABEL | AXIS_FLAGS_NO_GRID_LINES
                             | AXIS_FLAGS_NO_TICK_MARKS | AXIS_FLAGS_NO_TICK_LABELS)
AXIS_FLAGS_AUX_DEFAULT = AXIS_FLAGS_NO_GRID_LINES | AXIS_FLAGS_OPPOSITE

# ImPlotSubplotFlags_
SUBPLOT_FLAGS_NONE = 0
SUBPLOT_FLAGS_NO_TITLE = 1 << 0
SUBPLOT_FLAGS_NO_LEGEND = 1 << 1
SUBPLOT_FLAGS_NO_MENUS = 1 << 2
SUBPLOT_FLAGS_NO_RESIZE = 1 << 3
SUBPLOT_FLAGS_NO_ALIGN = 1 << 4
SUBPLOT_FLAGS_SHARE_ITEMS = 1 << 5
SUBPLOT_FLAGS_LINK_ROWS = 1 << 6
SUBPLOT_FLAGS_LINK_COLS = 1 << 7
SUBPLOT_FLAGS_LINK_ALL_X = 1 << 8
SUBPLOT_FLAGS_LINK_ALL_Y = 1 << 9
SUBPLOT_FLAGS_COL_MAJOR = 1 << 10

# ImPlotLegendFlags_
LEGEND_FLAGS_NONE = 0
LEGEND_FLAGS_NO_BUTTONS = 1 << 0
LEGEND_FLAGS_NO_HIGHLIGHT_ITEM = 1 << 1
LEGEND_FLAGS_NO_HIGHLIGHT_AXIS = 1 << 2
LEGEND_FLAGS_NO_MENUS = 1 << 3
LEGEND_FLAGS_OUTSIDE = 1 << 4
LEGEND_FLAGS_HORIZONTAL = 1 << 5
LEGEND_FLAGS_SORT = 1 << 6
LEGEND_FLAGS_REVERSE = 1 << 7

# ImPlotMouseTextFlags_
MOUSE_TEXT_FLAGS_NONE = 0
MOUSE_TEXT_FLAGS_NO_AUX_AXES = 1 << 0
MOUSE_TEXT_FLAGS_NO_FORMAT = 1 << 1
MOUSE_TEXT_FLAGS_SHOW_ALWAYS = 1 << 2

# ImPlotDragToolFlags_
DRAG_TOOL_FLAGS_NONE = 0
DRAG_TOOL_FLAGS_NO_CURSORS = 1 << 0
DRAG_TOOL_FLAGS_NO_FIT = 1 << 1
DRAG_TOOL_FLAGS_NO_INPUTS = 1 << 2
DRAG_TOOL_FLAGS_DELAYED = 1 << 3

# ImPlotColormapScaleFlags_
COLORMAP_SCALE_FLAGS_NONE = 0
COLORMAP_SCALE_FLAGS_NO_LABEL = 1 << 0
COLORMAP_SCALE_FLAGS_OPPOSITE = 1 << 1
COLORMAP_SCALE_FLAGS_INVERT = 1 << 2

# ImPlotItemFlags_ and the per-item flags (specialised bits start at 10)
ITEM_FLAGS_NONE = 0
ITEM_FLAGS_NO_LEGEND = 1 << 0
ITEM_FLAGS_NO_FIT = 1 << 1
LINE_FLAGS_NONE = 0
LINE_FLAGS_SEGMENTS = 1 << 10
LINE_FLAGS_LOOP = 1 << 11
LINE_FLAGS_SKIP_NAN = 1 << 12
LINE_FLAGS_NO_CLIP = 1 << 13
LINE_FLAGS_SHADED = 1 << 14
SCATTER_FLAGS_NONE = 0
SCATTER_FLAGS_NO_CLIP = 1 << 10
BUBBLES_FLAGS_NONE = 0
POLYGON_FLAGS_NONE = 0
POLYGON_FLAGS_CONCAVE = 1 << 10
STAIRS_FLAGS_NONE = 0
STAIRS_FLAGS_PRE_STEP = 1 << 10
STAIRS_FLAGS_SHADED = 1 << 11
SHADED_FLAGS_NONE = 0
BARS_FLAGS_NONE = 0
BARS_HORIZONTAL = BARS_FLAGS_HORIZONTAL = 1 << 10
BAR_GROUPS_FLAGS_NONE = 0
BAR_GROUPS_FLAGS_HORIZONTAL = 1 << 10
BAR_GROUPS_FLAGS_STACKED = 1 << 11
ERROR_BARS_FLAGS_NONE = 0
ERROR_BARS_FLAGS_HORIZONTAL = 1 << 10
STEMS_FLAGS_NONE = 0
STEMS_FLAGS_HORIZONTAL = 1 << 10
INF_LINES_FLAGS_NONE = 0
INF_LINES_HORIZONTAL = INF_LINES_FLAGS_HORIZONTAL = 1 << 10
PIE_CHART_FLAGS_NONE = 0
PIE_CHART_FLAGS_NORMALIZE = 1 << 10
PIE_CHART_FLAGS_IGNORE_HIDDEN = 1 << 11
PIE_CHART_FLAGS_EXPLODING = 1 << 12
PIE_CHART_FLAGS_NO_SLICE_BORDER = 1 << 13
HEATMAP_NONE = HEATMAP_FLAGS_NONE = 0
HEATMAP_COL_MAJOR = HEATMAP_FLAGS_COL_MAJOR = 1 << 10
HISTOGRAM_FLAGS_NONE = 0
HISTOGRAM_FLAGS_HORIZONTAL = 1 << 10
HISTOGRAM_FLAGS_CUMULATIVE = 1 << 11
HISTOGRAM_FLAGS_DENSITY = 1 << 12
HISTOGRAM_FLAGS_NO_OUTLIERS = 1 << 13
HISTOGRAM_FLAGS_COL_MAJOR = 1 << 14
DIGITAL_FLAGS_NONE = 0
IMAGE_FLAGS_NONE = 0
TEXT_FLAGS_NONE = 0
TEXT_FLAGS_VERTICAL = 1 << 10
DUMMY_FLAGS_NONE = 0

# ImPlotCond_ (ImGuiCond values)
COND_NONE, COND_ALWAYS, COND_ONCE = 0, 1, 2

# ImPlotCol_
(COL_FRAME_BG, COL_PLOT_BG, COL_PLOT_BORDER, COL_LEGEND_BG, COL_LEGEND_BORDER,
 COL_LEGEND_TEXT, COL_TITLE_TEXT, COL_INLAY_TEXT, COL_AXIS_TEXT, COL_AXIS_GRID,
 COL_AXIS_TICK, COL_AXIS_BG, COL_AXIS_BG_HOVERED, COL_AXIS_BG_ACTIVE, COL_SELECTION,
 COL_CROSSHAIRS) = range(16)
COL_COUNT = 16
COL_NAMES = ("FrameBg", "PlotBg", "PlotBorder", "LegendBg", "LegendBorder", "LegendText",
             "TitleText", "InlayText", "AxisText", "AxisGrid", "AxisTick", "AxisBg",
             "AxisBgHovered", "AxisBgActive", "Selection", "Crosshairs")

# ImPlotStyleVar_ -> the attribute of PlotStyle it names
STYLE_VAR_ATTRS = (
    "plot_default_size", "plot_min_size", "plot_border_size", "minor_alpha",
    "major_tick_len", "minor_tick_len", "major_tick_size", "minor_tick_size",
    "major_grid_size", "minor_grid_size", "plot_padding", "label_padding",
    "legend_padding", "legend_inner_padding", "legend_spacing", "mouse_pos_padding",
    "annotation_padding", "fit_padding", "digital_padding", "digital_spacing",
)
(STYLE_VAR_PLOT_DEFAULT_SIZE, STYLE_VAR_PLOT_MIN_SIZE, STYLE_VAR_PLOT_BORDER_SIZE,
 STYLE_VAR_MINOR_ALPHA, STYLE_VAR_MAJOR_TICK_LEN, STYLE_VAR_MINOR_TICK_LEN,
 STYLE_VAR_MAJOR_TICK_SIZE, STYLE_VAR_MINOR_TICK_SIZE, STYLE_VAR_MAJOR_GRID_SIZE,
 STYLE_VAR_MINOR_GRID_SIZE, STYLE_VAR_PLOT_PADDING, STYLE_VAR_LABEL_PADDING,
 STYLE_VAR_LEGEND_PADDING, STYLE_VAR_LEGEND_INNER_PADDING, STYLE_VAR_LEGEND_SPACING,
 STYLE_VAR_MOUSE_POS_PADDING, STYLE_VAR_ANNOTATION_PADDING, STYLE_VAR_FIT_PADDING,
 STYLE_VAR_DIGITAL_PADDING, STYLE_VAR_DIGITAL_SPACING) = range(20)

# ImPlotScale_
SCALE_LINEAR, SCALE_TIME, SCALE_LOG10, SCALE_SYMLOG = 0, 1, 2, 3

# ImPlotMarker_
MARKER_NONE, MARKER_AUTO = -2, -1
(MARKER_CIRCLE, MARKER_SQUARE, MARKER_DIAMOND, MARKER_UP, MARKER_DOWN, MARKER_LEFT,
 MARKER_RIGHT, MARKER_CROSS, MARKER_PLUS, MARKER_ASTERISK, MARKER_VERTICAL,
 MARKER_HORIZONTAL) = range(12)
MARKER_COUNT = 12
MARKER_INVALID = -3
MARKER_NAMES = ("Circle", "Square", "Diamond", "Up", "Down", "Left", "Right", "Cross",
                "Plus", "Asterisk", "Vertical", "Horizontal")

# ImPlotColormap_
(COLORMAP_DEEP, COLORMAP_DARK, COLORMAP_PASTEL, COLORMAP_PAIRED, COLORMAP_VIRIDIS,
 COLORMAP_PLASMA, COLORMAP_HOT, COLORMAP_COOL, COLORMAP_PINK, COLORMAP_JET,
 COLORMAP_TWILIGHT, COLORMAP_RDBU, COLORMAP_BRBG, COLORMAP_PIYG, COLORMAP_SPECTRAL,
 COLORMAP_GREYS) = range(16)

# ImPlotLocation_
LOCATION_CENTER = 0
LOCATION_NORTH = 1 << 0
LOCATION_SOUTH = 1 << 1
LOCATION_WEST = 1 << 2
LOCATION_EAST = 1 << 3
LOCATION_NORTH_WEST = LOCATION_NORTH | LOCATION_WEST
LOCATION_NORTH_EAST = LOCATION_NORTH | LOCATION_EAST
LOCATION_SOUTH_WEST = LOCATION_SOUTH | LOCATION_WEST
LOCATION_SOUTH_EAST = LOCATION_SOUTH | LOCATION_EAST

# ImPlotBin_
BIN_SQRT, BIN_STURGES, BIN_RICE, BIN_SCOTT = -1, -2, -3, -4

# ImGuiMod_ -- the key modifiers an input map names
MOD_NONE = 0
MOD_CTRL = 1 << 12
MOD_SHIFT = 1 << 13
MOD_ALT = 1 << 14
MOD_SUPER = 1 << 15

# ImGuiMouseButton_
MOUSE_BUTTON_LEFT, MOUSE_BUTTON_RIGHT, MOUSE_BUTTON_MIDDLE = 0, 1, 2

# implot_internal.h
IMPLOT_MIN_TIME = 0.0
IMPLOT_MAX_TIME = 32503680000.0
IMPLOT_LABEL_FORMAT = "%g"
DBL_MAX = 1.7976931348623157e308
DBL_MIN = 2.2250738585072014e-308
DBL_EPSILON = 2.220446049250313e-16
INF = float("inf")

(TIME_UNIT_US, TIME_UNIT_MS, TIME_UNIT_S, TIME_UNIT_MIN, TIME_UNIT_HR, TIME_UNIT_DAY,
 TIME_UNIT_MO, TIME_UNIT_YR) = range(8)
TIME_UNIT_COUNT = 8
(DATE_FMT_NONE, DATE_FMT_DAY_MO, DATE_FMT_DAY_MO_YR, DATE_FMT_MO_YR, DATE_FMT_MO,
 DATE_FMT_YR) = range(6)
(TIME_FMT_NONE, TIME_FMT_US, TIME_FMT_S_US, TIME_FMT_S_MS, TIME_FMT_S, TIME_FMT_MIN_S_MS,
 TIME_FMT_HR_MIN_S_MS, TIME_FMT_HR_MIN_S, TIME_FMT_HR_MIN, TIME_FMT_HR) = range(10)


# --------------------------------------------------------------------------- #
# [SECTION] Generic helpers
# --------------------------------------------------------------------------- #
def has_flag(flags: int, flag: int) -> bool:
    """``ImHasFlag``: all bits of *flag* are set. A zero flag is always set."""
    return (int(flags) & int(flag)) == int(flag)


def remap(x, x0, x1, y0, y1):
    """``ImRemap``."""
    if x1 == x0:
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def nan_or_inf(v) -> bool:
    """``ImNanOrInf``."""
    try:
        return not math.isfinite(v)
    except TypeError:
        return True


def constrain_nan(v):
    return 0.0 if v != v else v


def constrain_inf(v):
    return DBL_MAX if v >= DBL_MAX else (-DBL_MAX if v <= -DBL_MAX else v)


def constrain_time(v):
    return IMPLOT_MIN_TIME if v < IMPLOT_MIN_TIME else (IMPLOT_MAX_TIME if v > IMPLOT_MAX_TIME else v)


def almost_equal(v1, v2, ulp: int = 2) -> bool:
    """``ImAlmostEqual``."""
    return abs(v1 - v2) < DBL_EPSILON * abs(v1 + v2) * ulp or abs(v1 - v2) < DBL_MIN


def nice_num(x: float, round_: bool) -> float:
    """``NiceNum``: Graphics Gems' nice numbers, as the reference spells them."""
    if x <= 0.0 or not math.isfinite(x):
        return 0.0
    expv = math.floor(math.log10(x))
    f = x / 10.0 ** expv
    if round_:
        nf = 1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10
    else:
        nf = 1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10
    return nf * 10.0 ** expv


def order_of_magnitude(val: float) -> int:
    return 0 if val == 0 else int(math.floor(math.log10(abs(val))))


def order_to_precision(order: int) -> int:
    return 0 if order > 0 else 1 - order


def precision(val: float) -> int:
    return order_to_precision(order_of_magnitude(val))


def round_to(val: float, prec: int) -> float:
    p = 10.0 ** prec
    return math.floor(val * p + 0.5) / p


def intersection(a1, a2, b1, b2):
    """The intersection point of line A and line B (not parallel)."""
    v1 = a1[0] * a2[1] - a1[1] * a2[0]
    v2 = b1[0] * b2[1] - b1[1] * b2[0]
    v3 = (a1[0] - a2[0]) * (b1[1] - b2[1]) - (a1[1] - a2[1]) * (b1[0] - b2[0])
    if v3 == 0:
        return a2
    return ((v1 * (b1[0] - b2[0]) - v2 * (a1[0] - a2[0])) / v3,
            (v1 * (b1[1] - b2[1]) - v2 * (a1[1] - a2[1])) / v3)


def split_label(label: str) -> str:
    """``FindRenderedTextEnd``: the part of a label that is shown."""
    if label is None:
        return ""
    return str(label).split("##", 1)[0]


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #
def rgba(colour) -> Optional[tuple]:
    """A colour in emtk's 0-255 RGBA, or ``None`` for ``IMPLOT_AUTO_COL``.

    ImPlot styles in ``ImVec4`` floats; emtk paints in bytes. A tuple whose
    entries are all Python floats in 0..1 is read as the former. A float
    colour whose alpha is ``-1`` is the reference's auto colour.
    """
    if colour is None:
        return None
    if isinstance(colour, int):  # an ImU32, 0xAABBGGRR
        c = int(colour) & 0xFFFFFFFF
        return (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF, (c >> 24) & 0xFF)
    vals = list(colour)
    if len(vals) == 4 and vals[3] == -1:
        return None
    if vals and all(isinstance(v, float) and -0.001 <= v <= 1.001 for v in vals):
        vals = [int(round(max(0.0, min(1.0, v)) * 255)) for v in vals]
    vals = [int(v) for v in vals[:4]]
    if len(vals) == 3:
        vals.append(255)
    return tuple(max(0, min(255, v)) for v in vals)


def col_u32_to_float4(col) -> tuple:
    """The float spelling of a byte colour -- what ``GetLastItemColor`` hands back."""
    c = rgba(col) or (0, 0, 0, 0)
    return tuple(v / 255.0 for v in c)


def mix_u32(a, b, s: int) -> tuple:
    """``ImMixU32``: *a* and *b* mixed by ``s`` in 0..256."""
    af = 256 - s
    return tuple((a[i] * af + b[i] * s) >> 8 for i in range(4))


def alpha_u32(col, alpha: float) -> tuple:
    """``ImAlphaU32``: the colour with its alpha scaled."""
    return (col[0], col[1], col[2], int(col[3] * max(0.0, min(1.0, alpha))))


def calc_text_color(bg) -> tuple:
    """``CalcTextColor``: black on a light background, white on a dark one."""
    return (0, 0, 0, 255) if (bg[0] * 0.299 + bg[1] * 0.587 + bg[2] * 0.114) / 255.0 > 0.5 \
        else (255, 255, 255, 255)


def calc_hover_color(col) -> tuple:
    return mix_u32(col, calc_text_color(col), 32)


# --------------------------------------------------------------------------- #
# [SECTION] Transforms and formatters
# --------------------------------------------------------------------------- #
def transform_forward_log10(v, _data=None):
    return math.log10(DBL_MIN if v <= 0.0 else v)


def transform_inverse_log10(v, _data=None):
    try:
        return 10.0 ** v
    except OverflowError:
        return DBL_MAX


def transform_forward_symlog(v, _data=None):
    return 2.0 * math.asinh(v / 2.0)


def transform_inverse_symlog(v, _data=None):
    try:
        return 2.0 * math.sinh(v / 2.0)
    except OverflowError:
        return DBL_MAX if v > 0 else -DBL_MAX


def transform_forward_logit(v, _data=None):
    v = min(max(v, DBL_MIN), 1.0 - DBL_EPSILON)
    return math.log10(v / (1 - v))


def transform_inverse_logit(v, _data=None):
    return 1.0 / (1.0 + 10.0 ** (-v))


def format_printf(fmt: str, value) -> str:
    """``ImFormatString(buff, size, fmt, value)``.

    A Python ``{}`` format is accepted too: a hand-ported call site often
    carries one, and printing it literally is the worse failure.
    """
    try:
        if "%" in fmt:
            return fmt % value
        if "{" in fmt:
            return fmt.format(value)
        return fmt
    except (TypeError, ValueError):
        return f"{value:g}"


def formatter_default(value, data=None) -> str:
    """``Formatter_Default``: *data* is the printf format."""
    return format_printf(data or IMPLOT_LABEL_FORMAT, value)


def formatter_logit(value, _data=None) -> str:
    if value == 0.5:
        return "1/2"
    if value < 0.5:
        return f"{value:g}"
    return f"1 - {1 - value:g}"


def call_formatter(formatter, value, data) -> str:
    """Call a user formatter. ImPlot's is ``(value, buff, size, data)``; a
    Python one returns the string, taking ``(value, data)`` or ``(value)``."""
    try:
        return str(formatter(value, data))
    except TypeError:
        return str(formatter(value))


# --------------------------------------------------------------------------- #
# Text metrics, through the painter of the current frame
# --------------------------------------------------------------------------- #
def _painter():
    ctx = _core.get_current_context()
    return ctx.draw.p


def calc_text_size(text: str, hide_after_hashes: bool = False) -> tuple:
    """``ImGui::CalcTextSize``: width of the widest line, height of all lines."""
    if hide_after_hashes:
        text = split_label(text)
    p = _painter()
    lines = str(text).split("\n")
    return (max((p.text_width(line) if line else 0.0 for line in lines), default=0.0),
            p.line_height() * len(lines))


def text_line_height() -> float:
    return _painter().line_height()


# --------------------------------------------------------------------------- #
# [SECTION] Spec, style, input map
# --------------------------------------------------------------------------- #
_PROP_ATTRS = ("line_color", "line_colors", "line_weight", "fill_color", "fill_colors",
               "fill_alpha", "marker", "marker_size", "marker_sizes", "marker_line_color",
               "marker_line_colors", "marker_fill_color", "marker_fill_colors", "size",
               "offset", "stride", "flags")


class PlotSpec:
    """``ImPlotSpec``: how one item is drawn.

    Built three ways, as the reference allows two of them::

        spec = PlotSpec(); spec.line_color = (255, 0, 0, 255)
        PlotSpec(PROP_LINE_COLOR, (1.0, 0.0, 0.0, 1.0), PROP_MARKER, MARKER_CIRCLE)
        PlotSpec(line_color=(255, 0, 0), marker=MARKER_CIRCLE)

    Any ``spec=`` argument of an item also takes a ``dict`` of the keyword
    spelling, or the flat ``(prop, value, ...)`` list. ``dash`` -- an
    ``(on, off)`` pattern in pixels -- is emtk's own: ImPlot draws every line
    solid.
    """

    def __init__(self, *props, **kw) -> None:
        self.line_color = None
        self.line_colors = None
        self.line_weight = 1.0
        self.fill_color = None
        self.fill_colors = None
        self.fill_alpha = 1.0
        self.marker = MARKER_NONE
        self.marker_size = 4.0
        self.marker_sizes = None
        self.marker_line_color = None
        self.marker_line_colors = None
        self.marker_fill_color = None
        self.marker_fill_colors = None
        self.size = 4.0
        self.offset = 0
        self.stride = IMPLOT_AUTO
        self.flags = 0
        self.dash = None
        self.set_prop(*props)
        for key, value in kw.items():
            if not hasattr(self, key):
                raise TypeError(f"PlotSpec has no property {key!r}")
            setattr(self, key, value)

    def set_prop(self, *pairs) -> "PlotSpec":
        """``SetProp``: ``(prop, value)`` pairs in any order."""
        if len(pairs) % 2:
            raise ValueError("PlotSpec: provide (ImPlotProp, value) pairs")
        for i in range(0, len(pairs), 2):
            setattr(self, _PROP_ATTRS[int(pairs[i])], pairs[i + 1])
        return self

    def copy(self) -> "PlotSpec":
        out = PlotSpec()
        out.__dict__.update(self.__dict__)
        return out


def as_spec(spec) -> PlotSpec:
    """Whatever a caller passed as ``spec``, as a fresh :class:`PlotSpec`."""
    if spec is None:
        return PlotSpec()
    if isinstance(spec, PlotSpec):
        return spec.copy()
    if isinstance(spec, dict):
        return PlotSpec(**spec)
    return PlotSpec(*spec)


class PlotStyle:
    """``ImPlotStyle``. Colours are ``None`` (auto) until set."""

    def __init__(self) -> None:
        self.plot_default_size = (400.0, 300.0)
        self.plot_min_size = (200.0, 150.0)
        self.plot_border_size = 1.0
        self.minor_alpha = 0.25
        self.major_tick_len = (10.0, 10.0)
        self.minor_tick_len = (5.0, 5.0)
        self.major_tick_size = (1.0, 1.0)
        self.minor_tick_size = (1.0, 1.0)
        self.major_grid_size = (1.0, 1.0)
        self.minor_grid_size = (1.0, 1.0)
        self.plot_padding = (10.0, 10.0)
        self.label_padding = (5.0, 5.0)
        self.legend_padding = (10.0, 10.0)
        self.legend_inner_padding = (5.0, 5.0)
        self.legend_spacing = (5.0, 0.0)
        self.mouse_pos_padding = (10.0, 10.0)
        self.annotation_padding = (2.0, 2.0)
        self.fit_padding = (0.0, 0.0)
        self.digital_padding = 20.0
        self.digital_spacing = 4.0
        self.colors: list = [None] * COL_COUNT
        self.colormap = COLORMAP_DEEP
        self.use_local_time = False
        self.use_iso8601 = False
        self.use_24_hour_clock = False

    def copy(self) -> "PlotStyle":
        out = PlotStyle()
        out.__dict__.update(self.__dict__)
        out.colors = list(self.colors)
        return out


class InputMap:
    """``ImPlotInputMap``; the defaults are ``MapInputDefault``'s."""

    def __init__(self) -> None:
        map_input_default(self)


def map_input_default(dst: InputMap) -> None:
    dst.pan = MOUSE_BUTTON_LEFT
    dst.pan_mod = MOD_NONE
    dst.fit = MOUSE_BUTTON_LEFT
    dst.menu = MOUSE_BUTTON_RIGHT
    dst.select = MOUSE_BUTTON_RIGHT
    dst.select_mod = MOD_NONE
    dst.select_cancel = MOUSE_BUTTON_LEFT
    dst.select_horz_mod = MOD_ALT
    dst.select_vert_mod = MOD_SHIFT
    dst.override_mod = MOD_CTRL
    dst.zoom_mod = MOD_NONE
    dst.zoom_rate = 0.1


def map_input_reverse(dst: InputMap) -> None:
    dst.pan = MOUSE_BUTTON_RIGHT
    dst.pan_mod = MOD_NONE
    dst.fit = MOUSE_BUTTON_LEFT
    dst.menu = MOUSE_BUTTON_RIGHT
    dst.select = MOUSE_BUTTON_LEFT
    dst.select_mod = MOD_NONE
    dst.select_cancel = MOUSE_BUTTON_RIGHT
    dst.select_horz_mod = MOD_ALT
    dst.select_vert_mod = MOD_SHIFT
    dst.override_mod = MOD_CTRL
    dst.zoom_mod = MOD_NONE
    dst.zoom_rate = 0.1


def key_mods(io) -> int:
    """``io.KeyMods`` from emtk's four booleans."""
    return ((MOD_CTRL if io.key_ctrl else 0) | (MOD_SHIFT if io.key_shift else 0)
            | (MOD_ALT if io.key_alt else 0) | (MOD_SUPER if io.key_super else 0))


# --------------------------------------------------------------------------- #
# [SECTION] Colormaps
# --------------------------------------------------------------------------- #
def _rgb(r, g, b):
    return (r, g, b, 255)


_BUILTIN_COLORMAPS = (
    ("Deep", True, [_rgb(76, 114, 176), _rgb(221, 132, 82), _rgb(85, 168, 104), _rgb(196, 78, 82), _rgb(129, 114, 179), _rgb(147, 120, 96), _rgb(218, 139, 195), _rgb(140, 140, 140), _rgb(204, 185, 116), _rgb(100, 181, 205)]),
    ("Dark", True, [_rgb(228, 26, 28), _rgb(55, 126, 184), _rgb(77, 175, 74), _rgb(152, 78, 163), _rgb(255, 127, 0), _rgb(255, 255, 51), _rgb(166, 86, 40), _rgb(247, 129, 191), _rgb(153, 153, 153)]),
    ("Pastel", True, [_rgb(251, 180, 174), _rgb(179, 205, 227), _rgb(204, 235, 197), _rgb(222, 203, 228), _rgb(254, 217, 166), _rgb(255, 255, 204), _rgb(229, 216, 189), _rgb(253, 218, 236), _rgb(242, 242, 242)]),
    ("Paired", True, [_rgb(66, 206, 227), _rgb(31, 120, 180), _rgb(178, 223, 138), _rgb(51, 160, 44), _rgb(251, 154, 153), _rgb(227, 26, 28), _rgb(253, 191, 111), _rgb(255, 127, 0), _rgb(202, 178, 214), _rgb(106, 61, 154), _rgb(255, 255, 153), _rgb(177, 89, 40)]),
    ("Viridis", False, [_rgb(68, 1, 84), _rgb(72, 36, 117), _rgb(65, 68, 135), _rgb(53, 95, 141), _rgb(42, 120, 142), _rgb(33, 145, 140), _rgb(34, 168, 132), _rgb(68, 191, 112), _rgb(122, 209, 81), _rgb(189, 223, 38), _rgb(253, 231, 37)]),
    ("Plasma", False, [_rgb(13, 8, 135), _rgb(65, 4, 157), _rgb(106, 0, 168), _rgb(143, 13, 164), _rgb(177, 42, 144), _rgb(204, 71, 120), _rgb(225, 100, 98), _rgb(242, 132, 75), _rgb(252, 166, 54), _rgb(252, 206, 37), _rgb(240, 249, 33)]),
    ("Hot", False, [_rgb(64, 0, 0), _rgb(128, 0, 0), _rgb(191, 0, 0), _rgb(255, 0, 0), _rgb(255, 64, 0), _rgb(255, 128, 0), _rgb(255, 191, 0), _rgb(255, 255, 0), _rgb(255, 255, 85), _rgb(255, 255, 170), _rgb(255, 255, 255)]),
    ("Cool", False, [_rgb(0, 255, 255), _rgb(26, 230, 255), _rgb(51, 204, 255), _rgb(77, 179, 255), _rgb(102, 153, 255), _rgb(128, 128, 255), _rgb(153, 102, 255), _rgb(179, 77, 255), _rgb(204, 51, 255), _rgb(230, 26, 255), _rgb(255, 0, 255)]),
    ("Pink", False, [_rgb(74, 0, 0), _rgb(123, 66, 66), _rgb(158, 93, 93), _rgb(186, 114, 114), _rgb(198, 151, 132), _rgb(208, 180, 147), _rgb(218, 206, 161), _rgb(228, 228, 174), _rgb(237, 237, 205), _rgb(246, 246, 231), _rgb(255, 255, 255)]),
    ("Jet", False, [_rgb(0, 0, 170), _rgb(0, 0, 255), _rgb(0, 85, 255), _rgb(0, 170, 255), _rgb(0, 255, 255), _rgb(85, 255, 170), _rgb(170, 255, 85), _rgb(255, 255, 0), _rgb(255, 170, 0), _rgb(255, 85, 0), _rgb(255, 0, 0)]),
    ("Twilight", False, [_rgb(226, 217, 226), _rgb(166, 191, 202), _rgb(109, 144, 192), _rgb(95, 88, 176), _rgb(83, 30, 124), _rgb(47, 20, 54), _rgb(100, 25, 75), _rgb(159, 60, 80), _rgb(192, 117, 94), _rgb(208, 179, 158), _rgb(226, 217, 226)]),
    ("RdBu", False, [_rgb(103, 0, 31), _rgb(178, 24, 43), _rgb(214, 96, 77), _rgb(244, 165, 130), _rgb(253, 219, 199), _rgb(247, 247, 247), _rgb(209, 229, 240), _rgb(146, 197, 222), _rgb(67, 147, 195), _rgb(33, 102, 172), _rgb(5, 48, 97)]),
    ("BrBG", False, [_rgb(84, 48, 5), _rgb(140, 81, 10), _rgb(191, 129, 45), _rgb(223, 194, 125), _rgb(246, 232, 195), _rgb(245, 245, 245), _rgb(199, 234, 229), _rgb(128, 205, 193), _rgb(53, 151, 143), _rgb(1, 102, 94), _rgb(0, 60, 48)]),
    ("PiYG", False, [_rgb(142, 1, 82), _rgb(197, 27, 125), _rgb(222, 119, 174), _rgb(241, 182, 218), _rgb(253, 224, 239), _rgb(247, 247, 247), _rgb(230, 245, 208), _rgb(184, 225, 134), _rgb(127, 188, 65), _rgb(77, 146, 33), _rgb(39, 100, 25)]),
    ("Spectral", False, [_rgb(158, 1, 66), _rgb(213, 62, 79), _rgb(244, 109, 67), _rgb(253, 174, 97), _rgb(254, 224, 139), _rgb(255, 255, 191), _rgb(230, 245, 152), _rgb(171, 221, 164), _rgb(102, 194, 165), _rgb(50, 136, 189), _rgb(94, 79, 162)]),
    ("Greys", False, [(255, 255, 255, 255), (0, 0, 0, 255)]),
)


class ColormapData:
    """``ImPlotColormapData``: named key colours and their lookup tables.

    A qualitative map's table is its keys; a continuous one's is the keys
    mixed in 255 steps per interval, exactly as ``_AppendTable`` builds it, so
    ``LerpTable`` lands on the same bytes the reference does.
    """

    def __init__(self) -> None:
        self.keys: list[list[tuple]] = []
        self.tables: list[list[tuple]] = []
        self.quals: list[bool] = []
        self.names: list[str] = []
        self.map: dict[str, int] = {}

    @property
    def count(self) -> int:
        return len(self.keys)

    def append(self, name: str, keys, qual: bool) -> int:
        if name in self.map:
            return -1
        self.keys.append([rgba(k) for k in keys])
        self.quals.append(bool(qual))
        self.names.append(name)
        idx = len(self.keys) - 1
        self.map[name] = idx
        self.tables.append(self._build_table(idx))
        return idx

    def _build_table(self, cmap: int) -> list:
        keys = self.keys[cmap]
        if self.quals[cmap]:
            return list(keys)
        out = []
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            for s in range(255):
                out.append(mix_u32(a, b, s))
        out.append(keys[-1])
        return out

    def rebuild_tables(self) -> None:
        self.tables = [self._build_table(i) for i in range(self.count)]

    def is_qual(self, cmap: int) -> bool:
        return self.quals[cmap]

    def get_name(self, cmap: int):
        return self.names[cmap] if 0 <= cmap < self.count else None

    def get_index(self, name: str) -> int:
        return self.map.get(name, -1)

    def get_keys(self, cmap: int) -> list:
        return self.keys[cmap]

    def get_key_count(self, cmap: int) -> int:
        return len(self.keys[cmap])

    def get_key_color(self, cmap: int, idx: int) -> tuple:
        return self.keys[cmap][idx]

    def set_key_color(self, cmap: int, idx: int, value) -> None:
        self.keys[cmap][idx] = rgba(value)
        self.rebuild_tables()

    def get_table(self, cmap: int) -> list:
        return self.tables[cmap]

    def get_table_size(self, cmap: int) -> int:
        return len(self.tables[cmap])

    def lerp_table(self, cmap: int, t: float) -> tuple:
        """``LerpTable``."""
        table = self.tables[cmap]
        siz = len(table)
        if t != t:
            t = 0.0
        if self.quals[cmap]:
            idx = min(max(int(siz * t), 0), siz - 1)
        else:
            idx = int((siz - 1) * t + 0.5)
            idx = min(max(idx, 0), siz - 1)
        return table[idx]


def lerp_colors(colors, t: float) -> tuple:
    """``ImLerpU32``."""
    size = len(colors)
    i1 = int((size - 1) * t)
    i2 = i1 + 1
    if i2 == size or size == 1:
        return colors[min(max(i1, 0), size - 1)]
    den = 1.0 / (size - 1)
    tr = (t - i1 * den) / den
    return mix_u32(colors[i1], colors[i2], int(tr * 256))


# --------------------------------------------------------------------------- #
# [SECTION] Time
# --------------------------------------------------------------------------- #
class PlotTime:
    """``ImPlotTime``: whole seconds and microseconds."""

    __slots__ = ("s", "us")

    def __init__(self, s: int = 0, us: int = 0) -> None:
        s, us = int(s), int(us)
        self.s = s + us // 1000000 if us >= 0 else s + int(us / 1000000)
        self.us = us % 1000000 if us >= 0 else int(math.fmod(us, 1000000))

    def roll_over(self) -> None:
        self.s = self.s + self.us // 1000000
        self.us = self.us % 1000000

    def to_double(self) -> float:
        return float(self.s) + float(self.us) / 1000000.0

    @staticmethod
    def from_double(t: float) -> "PlotTime":
        return PlotTime(int(t), int(t * 1000000 - math.floor(t) * 1000000))

    def _key(self):
        return (self.s, self.us)

    def __add__(self, o):
        return PlotTime(self.s + o.s, self.us + o.us)

    def __sub__(self, o):
        return PlotTime(self.s - o.s, self.us - o.us)

    def __eq__(self, o):
        return isinstance(o, PlotTime) and self._key() == o._key()

    def __lt__(self, o):
        return self._key() < o._key()

    def __le__(self, o):
        return self._key() <= o._key()

    def __gt__(self, o):
        return self._key() > o._key()

    def __ge__(self, o):
        return self._key() >= o._key()

    def __repr__(self):
        return f"PlotTime({self.s}, {self.us})"


def _tm(t: PlotTime):
    """``GetTime``: a ``struct tm`` for the style's time zone."""
    try:
        if gp.style.use_local_time:
            return list(_time.localtime(t.s))
        return list(_time.gmtime(t.s))
    except (OverflowError, OSError, ValueError):
        return list(_time.gmtime(0))


def _mk_time(tm) -> PlotTime:
    """``MkTime``: a timestamp from ``(year, mon1, mday, hour, min, sec, ...)``.

    The fields are normalised the way ``timegm``/``mktime`` normalise them,
    so a month of 12 rolls into the next year, as C's does.
    """
    year, mon, mday, hour, minute, sec = tm[:6]
    year += (mon - 1) // 12
    mon = (mon - 1) % 12 + 1
    try:
        if gp.style.use_local_time:
            s = int(_time.mktime((year, mon, 1, hour, minute, sec, 0, 0, -1))) + (mday - 1) * 86400
        else:
            s = calendar.timegm((year, mon, 1, hour, minute, sec, 0, 0, 0)) + (mday - 1) * 86400
    except (OverflowError, ValueError):
        s = 0
    return PlotTime(max(s, 0), 0)


def is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def get_days_in_month(year: int, month: int) -> int:
    """*month* is zero indexed, as in the reference."""
    days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return days[month] + int(month == 1 and is_leap_year(year))


def make_time(year: int, month: int = 0, day: int = 1, hour: int = 0, minute: int = 0,
              sec: int = 0, us: int = 0) -> PlotTime:
    """``MakeTime``: *month* zero indexed."""
    year = max(year, 1900)
    sec = sec + us // 1000000
    us = us % 1000000
    t = _mk_time((year, month + 1, day, hour, minute, sec))
    t.us = us
    return t


def get_year(t: PlotTime) -> int:
    return _tm(t)[0]


def get_month(t: PlotTime) -> int:
    return _tm(t)[1] - 1


def add_time(t: PlotTime, unit: int, count: int) -> PlotTime:
    """``AddTime``."""
    out = PlotTime(t.s, t.us)
    if unit == TIME_UNIT_US:
        out.us += count
    elif unit == TIME_UNIT_MS:
        out.us += count * 1000
    elif unit == TIME_UNIT_S:
        out.s += count
    elif unit == TIME_UNIT_MIN:
        out.s += count * 60
    elif unit == TIME_UNIT_HR:
        out.s += count * 3600
    elif unit == TIME_UNIT_DAY:
        out.s += count * 86400
    elif unit == TIME_UNIT_MO:
        for _ in range(abs(count)):
            tm = _tm(out)
            if count > 0:
                out.s += 86400 * get_days_in_month(tm[0], tm[1] - 1)
            elif count < 0:
                mon = tm[1] - 1
                out.s -= 86400 * get_days_in_month(tm[0] - (1 if mon == 0 else 0),
                                                   11 if mon == 0 else mon - 1)
    elif unit == TIME_UNIT_YR:
        for _ in range(abs(count)):
            if count > 0:
                out.s += 86400 * (365 + int(is_leap_year(get_year(out))))
            elif count < 0:
                out.s -= 86400 * (365 + int(is_leap_year(get_year(out) - 1)))
    out.roll_over()
    return out


def floor_time(t: PlotTime, unit: int) -> PlotTime:
    """``FloorTime``."""
    if unit == TIME_UNIT_S:
        return PlotTime(t.s, 0)
    if unit == TIME_UNIT_MS:
        return PlotTime(t.s, (t.us // 1000) * 1000)
    if unit == TIME_UNIT_US:
        return t
    tm = _tm(t)  # year, mon(1..12), mday, hour, min, sec
    year, mon, mday, hour, minute, sec = tm[:6]
    if unit in (TIME_UNIT_YR,):
        mon = 1
    if unit in (TIME_UNIT_YR, TIME_UNIT_MO):
        mday = 1
    if unit in (TIME_UNIT_YR, TIME_UNIT_MO, TIME_UNIT_DAY):
        hour = 0
    if unit in (TIME_UNIT_YR, TIME_UNIT_MO, TIME_UNIT_DAY, TIME_UNIT_HR):
        minute = 0
    if unit in (TIME_UNIT_YR, TIME_UNIT_MO, TIME_UNIT_DAY, TIME_UNIT_HR, TIME_UNIT_MIN):
        sec = 0
    else:
        return t
    return _mk_time((year, mon, mday, hour, minute, sec))


def ceil_time(t: PlotTime, unit: int) -> PlotTime:
    return add_time(floor_time(t, unit), unit, 1)


def round_time(t: PlotTime, unit: int) -> PlotTime:
    t1 = floor_time(t, unit)
    t2 = add_time(t1, unit, 1)
    if t1.s == t2.s:
        return t1 if t.us - t1.us < t2.us - t.us else t2
    return t1 if t.s - t1.s < t2.s - t.s else t2


def combine_date_time(date_part: PlotTime, tod_part: PlotTime) -> PlotTime:
    d = _tm(date_part)
    tod = _tm(tod_part)
    t = _mk_time((d[0], d[1], d[2], tod[3], tod[4], tod[5]))
    t.us = tod_part.us
    return t


MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December")
MONTH_ABRVS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WD_ABRVS = ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")


def format_time(t: PlotTime, fmt: int, use_24_hr_clk: bool) -> str:
    """``FormatTime``."""
    tm = _tm(t)
    us = t.us % 1000
    ms = t.us // 1000
    sec, minute, hour = tm[5], tm[4], tm[3]
    if use_24_hr_clk:
        table = {
            TIME_FMT_US: ".%03d %03d" % (ms, us),
            TIME_FMT_S_US: ":%02d.%03d %03d" % (sec, ms, us),
            TIME_FMT_S_MS: ":%02d.%03d" % (sec, ms),
            TIME_FMT_S: ":%02d" % sec,
            TIME_FMT_MIN_S_MS: ":%02d:%02d.%03d" % (minute, sec, ms),
            TIME_FMT_HR_MIN_S_MS: "%02d:%02d:%02d.%03d" % (hour, minute, sec, ms),
            TIME_FMT_HR_MIN_S: "%02d:%02d:%02d" % (hour, minute, sec),
            TIME_FMT_HR_MIN: "%02d:%02d" % (hour, minute),
            TIME_FMT_HR: "%02d:00" % hour,
        }
        return table.get(fmt, "")
    ap = "am" if hour < 12 else "pm"
    hr = 12 if hour in (0, 12) else hour % 12
    table = {
        TIME_FMT_US: ".%03d %03d" % (ms, us),
        TIME_FMT_S_US: ":%02d.%03d %03d" % (sec, ms, us),
        TIME_FMT_S_MS: ":%02d.%03d" % (sec, ms),
        TIME_FMT_S: ":%02d" % sec,
        TIME_FMT_MIN_S_MS: ":%02d:%02d.%03d" % (minute, sec, ms),
        TIME_FMT_HR_MIN_S_MS: "%d:%02d:%02d.%03d%s" % (hr, minute, sec, ms, ap),
        TIME_FMT_HR_MIN_S: "%d:%02d:%02d%s" % (hr, minute, sec, ap),
        TIME_FMT_HR_MIN: "%d:%02d%s" % (hr, minute, ap),
        TIME_FMT_HR: "%d%s" % (hr, ap),
    }
    return table.get(fmt, "")


def format_date(t: PlotTime, fmt: int, use_iso_8601: bool) -> str:
    """``FormatDate``."""
    tm = _tm(t)
    day, mon, year = tm[2], tm[1], tm[0]
    yr = year % 100
    if use_iso_8601:
        table = {
            DATE_FMT_DAY_MO: "--%02d-%02d" % (mon, day),
            DATE_FMT_DAY_MO_YR: "%d-%02d-%02d" % (year, mon, day),
            DATE_FMT_MO_YR: "%d-%02d" % (year, mon),
            DATE_FMT_MO: "--%02d" % mon,
            DATE_FMT_YR: "%d" % year,
        }
        return table.get(fmt, "")
    table = {
        DATE_FMT_DAY_MO: "%d/%d" % (mon, day),
        DATE_FMT_DAY_MO_YR: "%d/%d/%02d" % (mon, day, yr),
        DATE_FMT_MO_YR: "%s %d" % (MONTH_ABRVS[mon - 1], year),
        DATE_FMT_MO: "%s" % MONTH_ABRVS[mon - 1],
        DATE_FMT_YR: "%d" % year,
    }
    return table.get(fmt, "")


class DateTimeSpec:
    """``ImPlotDateTimeSpec``."""

    __slots__ = ("date", "time", "use_iso8601", "use_24_hour_clock")

    def __init__(self, date=DATE_FMT_NONE, time_=TIME_FMT_NONE, use_24_hr_clk=False,
                 use_iso_8601=False) -> None:
        self.date = date
        self.time = time_
        self.use_24_hour_clock = use_24_hr_clk
        self.use_iso8601 = use_iso_8601


def format_date_time(t: PlotTime, fmt: DateTimeSpec) -> str:
    """``FormatDateTime``."""
    out = ""
    if fmt.date != DATE_FMT_NONE:
        out += format_date(t, fmt.date, fmt.use_iso8601)
    if fmt.time != TIME_FMT_NONE:
        if fmt.date != DATE_FMT_NONE:
            out += " "
        out += format_time(t, fmt.time, fmt.use_24_hour_clock)
    return out


def get_date_time_width(fmt: DateTimeSpec) -> float:
    """``GetDateTimeWidth``: the widest label this format can print."""
    t_max_width = make_time(2888, 12, 22, 12, 58, 58, 888888)
    return calc_text_size(format_date_time(t_max_width, fmt))[0]


def time_label_same(l1: str, l2: str) -> bool:
    n = min(len(l1), len(l2))
    return l1[len(l1) - n:] == l2[len(l2) - n:]


def _spec_table(rows):
    return tuple(DateTimeSpec(d, t) for d, t in rows)


TIME_FORMAT_LEVEL0 = _spec_table([
    (DATE_FMT_NONE, TIME_FMT_US), (DATE_FMT_NONE, TIME_FMT_S_MS), (DATE_FMT_NONE, TIME_FMT_S),
    (DATE_FMT_NONE, TIME_FMT_HR_MIN), (DATE_FMT_NONE, TIME_FMT_HR), (DATE_FMT_DAY_MO, TIME_FMT_NONE),
    (DATE_FMT_MO, TIME_FMT_NONE), (DATE_FMT_YR, TIME_FMT_NONE)])
TIME_FORMAT_LEVEL1 = _spec_table([
    (DATE_FMT_NONE, TIME_FMT_HR_MIN), (DATE_FMT_NONE, TIME_FMT_HR_MIN_S), (DATE_FMT_NONE, TIME_FMT_HR_MIN),
    (DATE_FMT_NONE, TIME_FMT_HR_MIN), (DATE_FMT_DAY_MO_YR, TIME_FMT_NONE), (DATE_FMT_DAY_MO_YR, TIME_FMT_NONE),
    (DATE_FMT_YR, TIME_FMT_NONE), (DATE_FMT_YR, TIME_FMT_NONE)])
TIME_FORMAT_LEVEL1_FIRST = _spec_table([
    (DATE_FMT_DAY_MO_YR, TIME_FMT_HR_MIN_S), (DATE_FMT_DAY_MO_YR, TIME_FMT_HR_MIN_S),
    (DATE_FMT_DAY_MO_YR, TIME_FMT_HR_MIN), (DATE_FMT_DAY_MO_YR, TIME_FMT_HR_MIN),
    (DATE_FMT_DAY_MO_YR, TIME_FMT_NONE), (DATE_FMT_DAY_MO_YR, TIME_FMT_NONE),
    (DATE_FMT_YR, TIME_FMT_NONE), (DATE_FMT_YR, TIME_FMT_NONE)])
TIME_FORMAT_MOUSE_CURSOR = _spec_table([
    (DATE_FMT_NONE, TIME_FMT_US), (DATE_FMT_NONE, TIME_FMT_S_US), (DATE_FMT_NONE, TIME_FMT_S_MS),
    (DATE_FMT_NONE, TIME_FMT_HR_MIN_S), (DATE_FMT_NONE, TIME_FMT_HR_MIN), (DATE_FMT_DAY_MO, TIME_FMT_HR),
    (DATE_FMT_DAY_MO_YR, TIME_FMT_NONE), (DATE_FMT_MO_YR, TIME_FMT_NONE)])

TIME_UNIT_SPANS = (0.000001, 0.001, 1, 60, 3600, 86400, 2629800, 31557600)


def get_date_time_fmt(table, idx: int) -> DateTimeSpec:
    src = table[idx]
    return DateTimeSpec(src.date, src.time, gp.style.use_24_hour_clock, gp.style.use_iso8601)


def get_unit_for_range(rng: float) -> int:
    cutoffs = (0.001, 1, 60, 3600, 86400, 2629800, 31557600, IMPLOT_MAX_TIME)
    for i, cut in enumerate(cutoffs):
        if rng <= cut:
            return i
    return TIME_UNIT_YR


def _lower_bound_step(max_divs: int, divs, step) -> int:
    if max_divs < divs[0]:
        return 0
    for i in range(1, len(divs)):
        if max_divs < divs[i]:
            return step[i - 1]
    return step[-1]


def get_time_step(max_divs: int, unit: int) -> int:
    if unit in (TIME_UNIT_MS, TIME_UNIT_US):
        return _lower_bound_step(max_divs, (2, 4, 5, 10, 20, 40, 50, 100, 200, 500, 1000),
                                 (500, 250, 200, 100, 50, 25, 20, 10, 5, 2, 1))
    if unit in (TIME_UNIT_S, TIME_UNIT_MIN):
        return _lower_bound_step(max_divs, (2, 4, 6, 12, 60), (30, 15, 10, 5, 1))
    if unit == TIME_UNIT_HR:
        return _lower_bound_step(max_divs, (2, 4, 8, 12, 24), (12, 6, 3, 2, 1))
    if unit == TIME_UNIT_DAY:
        return _lower_bound_step(max_divs, (2, 4, 14, 28), (14, 7, 2, 1))
    if unit == TIME_UNIT_MO:
        return _lower_bound_step(max_divs, (2, 4, 6, 12), (6, 3, 2, 1))
    return 0


# --------------------------------------------------------------------------- #
# [SECTION] Ticks and locators
# --------------------------------------------------------------------------- #
class Tick:
    """``ImPlotTick``."""

    __slots__ = ("plot_pos", "pixel_pos", "label_size", "text", "major", "show_label",
                 "level", "idx")

    def __init__(self, value: float, major: bool, level: int, show_label: bool) -> None:
        self.plot_pos = value
        self.pixel_pos = 0.0
        self.label_size = (0.0, 0.0)
        self.text: Optional[str] = None
        self.major = major
        self.show_label = show_label
        self.level = level
        self.idx = -1


class Ticker:
    """``ImPlotTicker``."""

    def __init__(self) -> None:
        self.ticks: list[Tick] = []
        self.max_size = (0.0, 0.0)
        self.late_size = (0.0, 0.0)
        self.levels = 1

    def add_tick(self, value: float, major: bool, level: int, show_label: bool,
                 label=None, formatter=None, data=None) -> Tick:
        tick = Tick(value, major, level, show_label)
        if show_label:
            if label is not None:
                tick.text = str(label)
            elif formatter is not None:
                tick.text = call_formatter(formatter, tick.plot_pos, data)
            if tick.text is not None:
                tick.label_size = calc_text_size(tick.text)
        return self._add(tick)

    def _add(self, tick: Tick) -> Tick:
        if tick.show_label:
            self.max_size = (max(self.max_size[0], tick.label_size[0]),
                             max(self.max_size[1], tick.label_size[1]))
        tick.idx = len(self.ticks)
        self.ticks.append(tick)
        return tick

    def override_size_late(self, size) -> None:
        self.late_size = (max(self.late_size[0], size[0]), max(self.late_size[1], size[1]))

    def reset(self) -> None:
        self.ticks = []
        self.max_size = self.late_size
        self.late_size = (0.0, 0.0)
        self.levels = 1

    def tick_count(self) -> int:
        return len(self.ticks)

    def get_text(self, idx: int) -> str:
        return self.ticks[idx].text or ""


TICK_FILL_X = 0.8
TICK_FILL_Y = 1.0


def locator_default(ticker: Ticker, rng, pixels: float, vertical: bool, formatter, data) -> None:
    """``Locator_Default``."""
    rmin, rmax = rng
    if rmin == rmax:
        return
    n_minor = 10
    n_major = max(2, int(round(pixels / (300.0 if vertical else 400.0))))
    nice_range = nice_num((rmax - rmin) * 0.99, False)
    interval = nice_num(nice_range / (n_major - 1), True)
    if interval <= 0.0 or not math.isfinite(interval):
        return
    graphmin = math.floor(rmin / interval) * interval
    graphmax = math.ceil(rmax / interval) * interval
    first_major_set = False
    first_major_idx = 0
    idx0 = ticker.tick_count()
    total = [0.0, 0.0]
    major = graphmin
    guard = 0
    while major < graphmax + 0.5 * interval and guard < 10000:
        guard += 1
        if major - interval < 0 < major + interval:
            major = 0.0
        if rmin <= major <= rmax:
            if not first_major_set:
                first_major_idx = ticker.tick_count()
                first_major_set = True
            t = ticker.add_tick(major, True, 0, True, formatter=formatter, data=data)
            total[0] += t.label_size[0]
            total[1] += t.label_size[1]
        for i in range(1, n_minor):
            minor = major + i * interval / n_minor
            if rmin <= minor <= rmax:
                t = ticker.add_tick(minor, False, 0, True, formatter=formatter, data=data)
                total[0] += t.label_size[0]
                total[1] += t.label_size[1]
        major += interval
    if (not vertical and total[0] > pixels * TICK_FILL_X) or (vertical and total[1] > pixels * TICK_FILL_Y):
        for i in range(first_major_idx - 1, idx0 - 1, -2):
            ticker.ticks[i].show_label = False
        for i in range(first_major_idx + 1, ticker.tick_count(), 2):
            ticker.ticks[i].show_label = False


def calc_logarithmic_exponents(rng, pix: float, vertical: bool):
    """``CalcLogarithmicExponents``: ``(ok, exp_min, exp_max, exp_step)``."""
    rmin, rmax = rng
    if rmin * rmax > 0:
        n_major = max(2, int(round(pix * 0.02))) if vertical else max(2, int(round(pix * 0.01)))
        log_min = math.log10(abs(rmin))
        log_max = math.log10(abs(rmax))
        log_a, log_b = min(log_min, log_max), max(log_min, log_max)
        exp_step = max(1, int(log_b - log_a) // n_major)
        exp_min = int(log_a)
        exp_max = int(log_b)
        if exp_step != 1:
            while exp_step % 3 != 0:
                exp_step += 1
            while exp_min % exp_step != 0:
                exp_min -= 1
        return True, exp_min, exp_max, exp_step
    return False, 0, 0, 1


def add_ticks_logarithmic(rng, exp_min: int, exp_max: int, exp_step: int, ticker: Ticker,
                          formatter, data, label_minors=()) -> None:
    """``AddTicksLogarithmic``. *label_minors* -- emtk's -- names the minor
    mantissas (``2``..``9``) whose ticks also get a label."""
    rmin, rmax = rng
    sign = 1.0 if rmax > 0 else (-1.0 if rmax < 0 else 0.0)
    e = exp_min - exp_step
    while e < exp_max + exp_step:
        major1 = sign * 10.0 ** e
        if rmin - DBL_EPSILON <= major1 <= rmax + DBL_EPSILON:
            ticker.add_tick(major1, True, 0, True, formatter=formatter, data=data)
        for j in range(exp_step):
            major1 = sign * 10.0 ** (e + j)
            major2 = sign * 10.0 ** (e + j + 1)
            interval = (major2 - major1) / 9
            for i in range(1, 9 + int(j < exp_step - 1)):
                minor = major1 + i * interval
                if rmin - DBL_EPSILON <= minor <= rmax + DBL_EPSILON:
                    labelled = (i + 1) in label_minors and exp_step == 1
                    ticker.add_tick(minor, False, 0, labelled, formatter=formatter, data=data)
        e += exp_step


def locator_log10(ticker: Ticker, rng, pixels: float, vertical: bool, formatter, data) -> None:
    """``Locator_Log10``, plus emtk's: a range with fewer than two decades on it
    labels minor ticks too (2..9, or 2 and 5 when space is short), so an axis
    0.5..5 does not read as a lone "1"."""
    ok, emin, emax, estep = calc_logarithmic_exponents(rng, pixels, vertical)
    if not ok:
        return
    lo, hi = sorted(abs(v) for v in rng)
    majors = sum(1 for e in range(emin - 1, emax + 2) if lo <= 10.0 ** e <= hi)
    label_minors = ()
    if majors < 2:
        span = math.log10(hi / lo) if lo > 0 else 1.0
        per_decade = pixels / max(span, 1e-9)
        label_minors = tuple(range(2, 10)) if per_decade > 400 else (2, 5)
    add_ticks_logarithmic(rng, emin, emax, estep, ticker, formatter, data, label_minors)


def calc_symlog_pixel(plt: float, rng, pixels: float) -> float:
    rmin, rmax = rng
    scale_to_pixels = pixels / (rmax - rmin)
    smin = transform_forward_symlog(rmin)
    smax = transform_forward_symlog(rmax)
    s = transform_forward_symlog(plt)
    t = (s - smin) / (smax - smin)
    plt = rmin + (rmax - rmin) * t
    return scale_to_pixels * (plt - rmin)


def locator_symlog(ticker: Ticker, rng, pixels: float, vertical: bool, formatter, data) -> None:
    """``Locator_SymLog``."""
    rmin, rmax = rng
    if rmin >= -1 and rmax <= 1:
        locator_default(ticker, rng, pixels, vertical, formatter, data)
    elif rmin * rmax < 0:
        pix_min, pix_max = 0.0, pixels
        pix_p1 = calc_symlog_pixel(1, rng, pixels)
        pix_n1 = calc_symlog_pixel(-1, rng, pixels)
        _, emin_p, emax_p, estep_p = calc_logarithmic_exponents((1, rmax), abs(pix_max - pix_p1), vertical)
        _, emin_n, emax_n, estep_n = calc_logarithmic_exponents((rmin, -1), abs(pix_n1 - pix_min), vertical)
        estep = max(estep_n, estep_p)
        ticker.add_tick(0.0, True, 0, True, formatter=formatter, data=data)
        add_ticks_logarithmic((1, rmax), emin_p, emax_p, estep, ticker, formatter, data)
        add_ticks_logarithmic((rmin, -1), emin_n, emax_n, estep, ticker, formatter, data)
    else:
        locator_log10(ticker, rng, pixels, vertical, formatter, data)


def add_ticks_custom(values, labels, ticker: Ticker, formatter, data) -> None:
    """``AddTicksCustom``."""
    for i, value in enumerate(values):
        if labels is not None:
            ticker.add_tick(float(value), False, 0, True, label=labels[i])
        else:
            ticker.add_tick(float(value), False, 0, True, formatter=formatter, data=data)


def locator_time(ticker: Ticker, rng, pixels: float, vertical: bool, formatter, data) -> None:
    """``Locator_Time``: two levels of labels, minor units over major ones."""
    rmin, rmax = rng
    if pixels <= 0 or rmax <= rmin:
        return
    unit0 = get_unit_for_range((rmax - rmin) / (pixels / 100.0))
    unit1 = min(max(unit0 + 1, 0), TIME_UNIT_COUNT - 1)
    fmt0 = get_date_time_fmt(TIME_FORMAT_LEVEL0, unit0)
    fmt1 = get_date_time_fmt(TIME_FORMAT_LEVEL1, unit1)
    fmtf = get_date_time_fmt(TIME_FORMAT_LEVEL1_FIRST, unit1)
    t_min = PlotTime.from_double(rmin)
    t_max = PlotTime.from_double(rmax)
    max_density = 0.5
    last_major_text = None

    def fmt_time(t, spec):
        return lambda _v, _d=None: format_date_time(t, spec)

    if unit0 != TIME_UNIT_YR:
        pix_per_major_div = pixels / ((rmax - rmin) / TIME_UNIT_SPANS[unit1])
        fmt0_width = get_date_time_width(fmt0)
        fmt1_width = get_date_time_width(fmt1)
        fmtf_width = get_date_time_width(fmtf)
        minor_per_major = int(max_density * pix_per_major_div / fmt0_width) if fmt0_width > 0 else 0
        step = get_time_step(minor_per_major, unit0)
        t1 = floor_time(PlotTime.from_double(rmin), unit1)
        guard = 0
        while t1 < t_max and guard < 5000:
            guard += 1
            t2 = add_time(t1, unit1, 1)
            if t2 <= t1:
                break
            if t_min <= t1 <= t_max:
                ticker.add_tick(t1.to_double(), True, 0, True, formatter=fmt_time(t1, fmt0))
                spec = fmtf if last_major_text is None else fmt1
                tick_maj = ticker.add_tick(t1.to_double(), True, 1, True, formatter=fmt_time(t1, spec))
                this_major = tick_maj.text or ""
                if last_major_text is not None and time_label_same(last_major_text, this_major):
                    tick_maj.show_label = False
                last_major_text = this_major
            if minor_per_major > 1 and step > 0 and (t_min <= t2 and t1 <= t_max):
                t12 = add_time(t1, unit0, step)
                inner = 0
                while t12 < t2 and inner < 5000:
                    inner += 1
                    px_to_t2 = ((t2 - t12).to_double() / (rmax - rmin)) * pixels
                    if t_min <= t12 <= t_max:
                        ticker.add_tick(t12.to_double(), False, 0, px_to_t2 >= fmt0_width,
                                        formatter=fmt_time(t12, fmt0))
                        if (last_major_text is None and px_to_t2 >= fmt0_width
                                and px_to_t2 >= (fmt1_width + fmtf_width) / 2):
                            tick_maj = ticker.add_tick(t12.to_double(), True, 1, True,
                                                       formatter=fmt_time(t12, fmtf))
                            last_major_text = tick_maj.text or ""
                    nxt = add_time(t12, unit0, step)
                    if nxt <= t12:
                        break
                    t12 = nxt
            t1 = t2
    else:
        fmty = get_date_time_fmt(TIME_FORMAT_LEVEL0, TIME_UNIT_YR)
        label_width = get_date_time_width(fmty)
        max_labels = int(max_density * pixels / label_width) if label_width > 0 else 2
        year_min = get_year(t_min)
        year_max = get_year(ceil_time(t_max, TIME_UNIT_YR))
        nice_range = nice_num((year_max - year_min) * 0.99, False)
        interval = nice_num(nice_range / max(max_labels - 1, 1), True)
        if interval <= 0:
            interval = 1
        graphmin = int(math.floor(year_min / interval) * interval)
        graphmax = int(math.ceil(year_max / interval) * interval)
        step = int(interval) if int(interval) > 0 else 1
        for y in range(graphmin, graphmax, step):
            t = make_time(y)
            if t_min <= t <= t_max:
                ticker.add_tick(t.to_double(), True, 0, True, formatter=fmt_time(t, fmty))


# --------------------------------------------------------------------------- #
# [SECTION] Structs
# --------------------------------------------------------------------------- #
class Axis:
    """``ImPlotAxis``: the state of one axis that must persist after EndPlot."""

    def __init__(self, vertical: bool = False) -> None:
        self.id: Any = None
        self.flags = AXIS_FLAGS_NONE
        self.previous_flags = AXIS_FLAGS_NONE
        self.range_min = 0.0
        self.range_max = 1.0
        self.range_cond = COND_NONE
        self.scale = SCALE_LINEAR
        self.fit_min = INF
        self.fit_max = -INF
        self.ortho_axis: Optional["Axis"] = None
        self.constraint_range = (-INF, INF)
        self.constraint_zoom = (DBL_MIN, INF)
        self.ticker = Ticker()
        self.formatter: Optional[Callable] = None
        self.formatter_data: Any = None
        self.format_spec = ""
        self.locator: Optional[Callable] = None
        self.linked_min = None  # (owner, key) of the linked value
        self.linked_max = None
        self.picker_level = 0
        self.transform_forward: Optional[Callable] = None
        self.transform_inverse: Optional[Callable] = None
        self.transform_data = None
        self.pixel_min = 0.0
        self.pixel_max = 0.0
        self.scale_min = 0.0
        self.scale_max = 1.0
        self.scale_to_pixel = 1.0
        self.datum1 = 0.0
        self.datum2 = 0.0
        self.hover_rect = (0.0, 0.0, 0.0, 0.0)  # x0, y0, x1, y1
        self.label: Optional[str] = None
        self.color_maj = self.color_min = self.color_tick = self.color_txt = (0, 0, 0, 0)
        self.color_bg = self.color_hov = self.color_act = (0, 0, 0, 0)
        self.color_hili = (0, 0, 0, 0)
        self.enabled = False
        self.vertical = vertical
        self.fit_this_frame = False
        self.has_range = False
        self.has_format_spec = False
        self.show_default_ticks = True
        self.hovered = False
        self.held = False
        #: emtk: an axis nobody has panned or zoomed keeps following its data
        #: -- see the module docstring of :mod:`emtk.implot`.
        self.follow = True
        #: emtk: the last limits asked for with ``COND_ONCE``; a different
        #: request is a new request.
        self.once_request = None

    # -- range --------------------------------------------------------------
    @property
    def range(self) -> tuple:
        return (self.range_min, self.range_max)

    def range_size(self) -> float:
        return self.range_max - self.range_min

    def range_contains(self, v: float) -> bool:
        return self.range_min <= v <= self.range_max

    def reset(self) -> None:
        self.enabled = False
        self.scale = SCALE_LINEAR
        self.transform_forward = self.transform_inverse = None
        self.transform_data = None
        self.label = None
        self.has_format_spec = False
        self.formatter = None
        self.formatter_data = None
        self.locator = None
        self.show_default_ticks = True
        self.fit_this_frame = False
        self.fit_min = INF
        self.fit_max = -INF
        self.ortho_axis = None
        self.constraint_range = (-INF, INF)
        self.constraint_zoom = (DBL_MIN, INF)
        self.ticker.reset()

    def set_min(self, _min: float, force: bool = False) -> bool:
        if not force and self.is_locked_min():
            return False
        _min = constrain_nan(constrain_inf(_min))
        if _min < self.constraint_range[0]:
            _min = self.constraint_range[0]
        z = self.range_max - _min
        if z < self.constraint_zoom[0]:
            _min = self.range_max - self.constraint_zoom[0]
        if z > self.constraint_zoom[1]:
            _min = self.range_max - self.constraint_zoom[1]
        if _min >= self.range_max:
            return False
        self.range_min = _min
        self.update_transform_cache()
        return True

    def set_max(self, _max: float, force: bool = False) -> bool:
        if not force and self.is_locked_max():
            return False
        _max = constrain_nan(constrain_inf(_max))
        if _max > self.constraint_range[1]:
            _max = self.constraint_range[1]
        z = _max - self.range_min
        if z < self.constraint_zoom[0]:
            _max = self.range_min + self.constraint_zoom[0]
        if z > self.constraint_zoom[1]:
            _max = self.range_min + self.constraint_zoom[1]
        if _max <= self.range_min:
            return False
        self.range_max = _max
        self.update_transform_cache()
        return True

    def set_range(self, v1: float, v2: float) -> None:
        self.range_min = min(v1, v2)
        self.range_max = max(v1, v2)
        self.constrain()
        self.update_transform_cache()

    def set_aspect(self, unit_per_pix: float) -> None:
        new_size = unit_per_pix * self.pixel_size()
        delta = (new_size - self.range_size()) * 0.5
        if self.is_locked():
            return
        if self.is_locked_min() and not self.is_locked_max():
            self.set_range(self.range_min, self.range_max + 2 * delta)
        elif not self.is_locked_min() and self.is_locked_max():
            self.set_range(self.range_min - 2 * delta, self.range_max)
        else:
            self.set_range(self.range_min - delta, self.range_max + delta)

    def pixel_size(self) -> float:
        return abs(self.pixel_max - self.pixel_min)

    def get_aspect(self) -> float:
        px = self.pixel_size()
        return self.range_size() / px if px else 0.0

    def constrain(self) -> None:
        self.range_min = constrain_nan(constrain_inf(self.range_min))
        self.range_max = constrain_nan(constrain_inf(self.range_max))
        if self.range_min < self.constraint_range[0]:
            self.range_min = self.constraint_range[0]
        if self.range_max > self.constraint_range[1]:
            self.range_max = self.constraint_range[1]
        z = self.range_size()
        if z < self.constraint_zoom[0]:
            delta = (self.constraint_zoom[0] - z) * 0.5
            self.range_min -= delta
            self.range_max += delta
        if z > self.constraint_zoom[1]:
            delta = (z - self.constraint_zoom[1]) * 0.5
            self.range_min += delta
            self.range_max -= delta
        if self.range_max <= self.range_min:
            self.range_max = self.range_min + max(DBL_EPSILON, abs(self.range_min) * DBL_EPSILON * 4)

    def update_transform_cache(self) -> None:
        size = self.range_size()
        self.scale_to_pixel = (self.pixel_max - self.pixel_min) / size if size else 0.0
        if self.transform_forward is not None:
            self.scale_min = self.transform_forward(self.range_min, self.transform_data)
            self.scale_max = self.transform_forward(self.range_max, self.transform_data)
        else:
            self.scale_min = self.range_min
            self.scale_max = self.range_max

    def plot_to_pixels(self, plt: float) -> float:
        if self.transform_forward is not None:
            s = self.transform_forward(plt, self.transform_data)
            den = self.scale_max - self.scale_min
            t = (s - self.scale_min) / den if den else 0.0
            plt = self.range_min + self.range_size() * t
        return self.pixel_min + self.scale_to_pixel * (plt - self.range_min)

    def pixels_to_plot(self, pix: float) -> float:
        if self.scale_to_pixel == 0:
            return self.range_min
        plt = (pix - self.pixel_min) / self.scale_to_pixel + self.range_min
        if self.transform_inverse is not None:
            size = self.range_size()
            t = (plt - self.range_min) / size if size else 0.0
            s = t * (self.scale_max - self.scale_min) + self.scale_min
            plt = self.transform_inverse(s, self.transform_data)
        return plt

    def extend_fit(self, v: float) -> None:
        if not nan_or_inf(v) and self.constraint_range[0] <= v <= self.constraint_range[1]:
            if v < self.fit_min:
                self.fit_min = v
            if v > self.fit_max:
                self.fit_max = v

    def extend_fit_with(self, alt: "Axis", v: float, v_alt: float) -> None:
        if has_flag(self.flags, AXIS_FLAGS_RANGE_FIT) and not alt.range_contains(v_alt):
            return
        self.extend_fit(v)

    def apply_fit(self, padding: float) -> None:
        ext_size = (self.fit_max - self.fit_min) * 0.5
        if math.isfinite(ext_size):
            self.fit_min -= ext_size * padding
            self.fit_max += ext_size * padding
        if not self.is_locked_min() and not nan_or_inf(self.fit_min):
            self.range_min = self.fit_min
        if not self.is_locked_max() and not nan_or_inf(self.fit_max):
            self.range_max = self.fit_max
        if almost_equal(self.range_min, self.range_max):
            self.range_max += 0.5
            self.range_min -= 0.5
        self.constrain()
        self.update_transform_cache()

    def has_label(self) -> bool:
        return bool(self.label) and not has_flag(self.flags, AXIS_FLAGS_NO_LABEL)

    def has_grid_lines(self) -> bool:
        return not has_flag(self.flags, AXIS_FLAGS_NO_GRID_LINES)

    def has_tick_labels(self) -> bool:
        return not has_flag(self.flags, AXIS_FLAGS_NO_TICK_LABELS)

    def has_tick_marks(self) -> bool:
        return not has_flag(self.flags, AXIS_FLAGS_NO_TICK_MARKS)

    def will_render(self) -> bool:
        return self.enabled and (self.has_grid_lines() or self.has_tick_labels() or self.has_tick_marks())

    def is_opposite(self) -> bool:
        return has_flag(self.flags, AXIS_FLAGS_OPPOSITE)

    def is_inverted(self) -> bool:
        return has_flag(self.flags, AXIS_FLAGS_INVERT)

    def is_foreground(self) -> bool:
        return has_flag(self.flags, AXIS_FLAGS_FOREGROUND)

    def is_auto_fitting(self) -> bool:
        return has_flag(self.flags, AXIS_FLAGS_AUTO_FIT)

    def can_init_fit(self) -> bool:
        return (not has_flag(self.flags, AXIS_FLAGS_NO_INITIAL_FIT) and not self.has_range
                and self.linked_min is None and self.linked_max is None)

    def is_range_locked(self) -> bool:
        return self.has_range and self.range_cond == COND_ALWAYS

    def is_locked_min(self) -> bool:
        return not self.enabled or self.is_range_locked() or has_flag(self.flags, AXIS_FLAGS_LOCK_MIN)

    def is_locked_max(self) -> bool:
        return not self.enabled or self.is_range_locked() or has_flag(self.flags, AXIS_FLAGS_LOCK_MAX)

    def is_locked(self) -> bool:
        return self.is_locked_min() and self.is_locked_max()

    def is_input_locked_min(self) -> bool:
        return self.is_locked_min() or self.is_auto_fitting()

    def is_input_locked_max(self) -> bool:
        return self.is_locked_max() or self.is_auto_fitting()

    def is_input_locked(self) -> bool:
        return self.is_locked() or self.is_auto_fitting()

    def has_menus(self) -> bool:
        return not has_flag(self.flags, AXIS_FLAGS_NO_MENUS)

    def is_pan_locked(self, increasing: bool) -> bool:
        if has_flag(self.flags, AXIS_FLAGS_PAN_STRETCH):
            return self.is_input_locked()
        if self.is_locked_min() or self.is_locked_max() or self.is_auto_fitting():
            return False
        if increasing:
            return self.range_max == self.constraint_range[1]
        return self.range_min == self.constraint_range[0]

    def push_links(self) -> None:
        if self.linked_min is not None:
            _link_set(self.linked_min, self.range_min)
        if self.linked_max is not None:
            _link_set(self.linked_max, self.range_max)

    def pull_links(self) -> None:
        if self.linked_min is not None and self.linked_max is not None:
            self.set_range(_link_get(self.linked_min), _link_get(self.linked_max))
        elif self.linked_min is not None:
            self.set_min(_link_get(self.linked_min), True)
        elif self.linked_max is not None:
            self.set_max(_link_get(self.linked_max), True)


def _link_get(link):
    owner, key = link
    return float(getattr(owner, key) if isinstance(key, str) else owner[key])


def _link_set(link, value) -> None:
    owner, key = link
    if isinstance(key, str):
        setattr(owner, key, value)
    else:
        owner[key] = value


class AlignmentData:
    """``ImPlotAlignmentData``."""

    def __init__(self) -> None:
        self.vertical = True
        self.pad_a = self.pad_b = self.pad_a_max = self.pad_b_max = 0.0

    def begin(self) -> None:
        self.pad_a_max = self.pad_b_max = 0.0

    def update(self, pad_a: float, pad_b: float):
        """Returns ``(pad_a, pad_b, delta_a, delta_b)``."""
        self.pad_a_max = max(self.pad_a_max, pad_a)
        self.pad_b_max = max(self.pad_b_max, pad_b)
        delta_a = delta_b = 0.0
        if pad_a < self.pad_a:
            delta_a = self.pad_a - pad_a
            pad_a = self.pad_a
        if pad_b < self.pad_b:
            delta_b = self.pad_b - pad_b
            pad_b = self.pad_b
        return pad_a, pad_b, delta_a, delta_b

    def end(self) -> None:
        self.pad_a = self.pad_a_max
        self.pad_b = self.pad_b_max

    def reset(self) -> None:
        self.pad_a = self.pad_b = self.pad_a_max = self.pad_b_max = 0.0


class Item:
    """``ImPlotItem``."""

    def __init__(self) -> None:
        self.id: Any = None
        self.color = (255, 255, 255, 255)
        self.marker = MARKER_NONE
        self.legend_hover_rect = (0.0, 0.0, 0.0, 0.0)
        self.label = ""
        self.show = True
        self.legend_hovered = False
        self.seen_this_frame = False


class Legend:
    """``ImPlotLegend``."""

    def __init__(self) -> None:
        self.flags = LEGEND_FLAGS_NONE
        self.previous_flags = LEGEND_FLAGS_NONE
        self.location = LOCATION_NORTH_WEST
        self.previous_location = LOCATION_NORTH_WEST
        self.scroll = (0.0, 0.0)
        self.indices: list[int] = []
        self.rect = (0.0, 0.0, 0.0, 0.0)
        self.rect_clamped = (0.0, 0.0, 0.0, 0.0)
        self.hovered = False
        self.held = False
        self.can_go_inside = True

    def reset(self) -> None:
        self.indices = []


class ItemGroup:
    """``ImPlotItemGroup``: the items of a plot (or a subplot) and its legend."""

    def __init__(self) -> None:
        self.id: Any = None
        self.legend = Legend()
        self.items: list[Item] = []
        self.by_id: dict = {}
        self.colormap_idx = 0
        self.marker_idx = 0

    def get_item_count(self) -> int:
        return len(self.items)

    def get_item(self, item_id) -> Optional[Item]:
        return self.by_id.get(item_id)

    def get_or_add_item(self, item_id) -> Item:
        item = self.by_id.get(item_id)
        if item is None:
            item = Item()
            item.id = item_id
            self.by_id[item_id] = item
            self.items.append(item)
        return item

    def get_item_by_index(self, i: int) -> Item:
        return self.items[i]

    def get_item_index(self, item: Item) -> int:
        return self.items.index(item)

    def get_legend_count(self) -> int:
        return len(self.legend.indices)

    def get_legend_item(self, i: int) -> Item:
        return self.items[self.legend.indices[i]]

    def get_legend_label(self, i: int) -> str:
        return self.get_legend_item(i).label

    def reset(self) -> None:
        self.items = []
        self.by_id = {}
        self.legend.reset()
        self.colormap_idx = 0


class Plot:
    """``ImPlotPlot``: a plot's state, persistent across frames.

    ``frame_rect``/``canvas_rect``/``plot_rect``/``axes_rect``/``select_rect``
    are ``(x0, y0, x1, y1)``, as ``ImRect`` holds them.
    """

    def __init__(self) -> None:
        self.id: Any = None
        self.flags = FLAGS_NONE
        self.previous_flags = FLAGS_NONE
        self.mouse_text_location = LOCATION_SOUTH | LOCATION_EAST
        self.mouse_text_flags = MOUSE_TEXT_FLAGS_NONE
        self.axes = [Axis(vertical=i >= AXIS_Y1) for i in range(AXIS_COUNT)]
        self.items = ItemGroup()
        self.current_x = AXIS_X1
        self.current_y = AXIS_Y1
        self.frame_rect = (0.0, 0.0, 0.0, 0.0)
        self.canvas_rect = (0.0, 0.0, 0.0, 0.0)
        self.plot_rect = (0.0, 0.0, 0.0, 0.0)
        self.axes_rect = (0.0, 0.0, 0.0, 0.0)
        self.select_rect = (0.0, 0.0, 0.0, 0.0)
        self.select_start = (0.0, 0.0)
        self.title: Optional[str] = None
        self.just_created = True
        self.initialized = False
        self.setup_locked = False
        self.fit_this_frame = False
        self.hovered = False
        self.held = False
        self.selecting = False
        self.selected = False
        self.context_locked = False
        #: emtk: the draw queue (items, tools, custom drawing) replayed in
        #: ``EndPlot`` with the final axes -- see :mod:`emtk.implot`.
        self.queue: list = []
        #: emtk: what each item plotted this frame, in plot units.
        self.records: list = []
        #: emtk: an open context menu, as ``(kind, index, (x, y))``.
        self.context_menu = None

    def is_input_locked(self) -> bool:
        return all(ax.is_input_locked() for ax in self.axes)

    def x_axis(self, i: int) -> Axis:
        return self.axes[AXIS_X1 + i]

    def y_axis(self, i: int) -> Axis:
        return self.axes[AXIS_Y1 + i]

    def enabled_axes_x(self) -> int:
        return sum(1 for i in range(NUM_X_AXES) if self.x_axis(i).enabled)

    def enabled_axes_y(self) -> int:
        return sum(1 for i in range(NUM_Y_AXES) if self.y_axis(i).enabled)

    def set_title(self, title: Optional[str]) -> None:
        shown = split_label(title) if title else ""
        self.title = shown if shown else None

    def has_title(self) -> bool:
        return self.title is not None and not has_flag(self.flags, FLAGS_NO_TITLE)


class Subplot:
    """``ImPlotSubplot``."""

    def __init__(self) -> None:
        self.id: Any = None
        self.flags = SUBPLOT_FLAGS_NONE
        self.previous_flags = SUBPLOT_FLAGS_NONE
        self.items = ItemGroup()
        self.items.legend.location = LOCATION_NORTH
        self.items.legend.flags = LEGEND_FLAGS_HORIZONTAL | LEGEND_FLAGS_OUTSIDE
        self.items.legend.can_go_inside = False
        self.rows = 0
        self.cols = 0
        self.current_idx = 0
        self.frame_rect = (0.0, 0.0, 0.0, 0.0)
        self.grid_rect = (0.0, 0.0, 0.0, 0.0)
        self.cell_size = (0.0, 0.0)
        self.row_alignment_data: list[AlignmentData] = []
        self.col_alignment_data: list[AlignmentData] = []
        self.row_ratios: list[float] = []
        self.col_ratios: list[float] = []
        self.row_link_data: list[list[float]] = []
        self.col_link_data: list[list[float]] = []
        self.temp_sizes = [0.0, 0.0]
        self.frame_hovered = False
        self.has_title = False


class NextPlotData:
    """``ImPlotNextPlotData``."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.range_cond = [COND_NONE] * AXIS_COUNT
        self.range = [(0.0, 0.0)] * AXIS_COUNT
        self.has_range = [False] * AXIS_COUNT
        self.fit = [False] * AXIS_COUNT
        self.linked_min = [None] * AXIS_COUNT
        self.linked_max = [None] * AXIS_COUNT


class NextItemData:
    """``ImPlotNextItemData``."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.spec = PlotSpec()
        self.render_line = False
        self.render_fill = False
        self.render_marker_line = False
        self.render_marker_fill = False
        self.render_markers = False
        self.has_hidden = False
        self.hidden = False
        self.hidden_cond = COND_NONE


class PlotContext:
    """``ImPlotContext``, less the pools (which live in emtk storage)."""

    def __init__(self) -> None:
        self.current_plot: Optional[Plot] = None
        self.current_subplot: Optional[Subplot] = None
        self.current_items: Optional[ItemGroup] = None
        self.current_item: Optional[Item] = None
        self.previous_item: Optional[Item] = None
        self.c_ticker = Ticker()
        self.annotations: list = []
        self.tags: list = []
        self.style = PlotStyle()
        self.color_modifiers: list = []
        self.style_modifiers: list = []
        self.colormap_data = ColormapData()
        self.colormap_modifiers: list = []
        self.digital_plot_item_cnt = 0
        self.digital_plot_offset = 0
        self.next_plot_data = NextPlotData()
        self.next_item_data = NextItemData()
        self.input_map = InputMap()
        self.open_context_this_frame = False
        self.current_alignment_h: Optional[AlignmentData] = None
        self.current_alignment_v: Optional[AlignmentData] = None
        #: emtk: which emtk context and frame opened the current plot.
        self.owner = None
        self.frame = -1
        #: emtk: the colours of a pushed colour *list* (``push_colormap([...])``),
        #: an emtk convenience over the reference's index-or-name.
        self.anon_colormaps: dict = {}
        #: emtk: popups waiting to be drawn over the plot (or subplot grid).
        self.pending_popups: list = []
        self.last_plot: Optional[Plot] = None
        self.last_plot_rect = (0.0, 0.0, 0.0, 0.0)
        #: emtk: the obsolete ``SetNext*Style`` values, merged into the next spec.
        self.legacy_line = None
        self.legacy_fill = None
        self.legacy_marker = None
        for name, qual, keys in _BUILTIN_COLORMAPS:
            self.colormap_data.append(name, keys, qual)

    # the spelling the module used before the port: ``_cur.plot``
    @property
    def plot(self) -> Optional[Plot]:
        return self.current_plot

    @property
    def box(self):
        """The plot area as ``(x, y, w, h)``: the current plot's, else the last one's."""
        r = self.current_plot.plot_rect if self.current_plot is not None else self.last_plot_rect
        return (r[0], r[1], r[2] - r[0], r[3] - r[1])

    @property
    def colormap(self):
        return self.colormap_modifiers[-1] if self.colormap_modifiers else None

    @colormap.setter
    def colormap(self, value) -> None:
        if value is None:
            while self.colormap_modifiers:
                self.style.colormap = self.colormap_modifiers.pop()

    @plot.setter
    def plot(self, value) -> None:
        self.current_plot = value
        if value is None:
            self.current_items = None
            self.current_subplot = None
            self.current_alignment_h = self.current_alignment_v = None


gp = PlotContext()


def pools() -> dict:
    """The per-storage pools: plots, subplots and alignment groups by id."""
    state = _core.get_current_context().state("implot")
    state.setdefault("plots", {})
    state.setdefault("subplots", {})
    state.setdefault("alignment", {})
    return state


def reset_ctx_for_next_plot() -> None:
    """``ResetCtxForNextPlot``."""
    gp.next_plot_data.reset()
    gp.next_item_data.reset()
    gp.annotations = []
    gp.tags = []
    gp.open_context_this_frame = False
    gp.digital_plot_item_cnt = 0
    gp.digital_plot_offset = 0
    gp.current_plot = None
    gp.current_item = None
    gp.previous_item = None


def reset_ctx_for_next_aligned_plots() -> None:
    gp.current_alignment_h = None
    gp.current_alignment_v = None


def reset_ctx_for_next_subplot() -> None:
    gp.current_subplot = None
    gp.current_alignment_h = None
    gp.current_alignment_v = None


# --------------------------------------------------------------------------- #
# [SECTION] Style colours
# --------------------------------------------------------------------------- #
def _imgui_col(which) -> tuple:
    ctx = _core.get_current_context()
    return rgba(ctx.style.color(which))


def get_auto_color(idx: int) -> tuple:
    """``GetAutoColor``: a style colour from the emtk (ImGui) style."""
    Col = _core.Col
    if idx == COL_FRAME_BG:
        return _imgui_col(Col.FRAME_BG)
    if idx == COL_PLOT_BG:
        return _imgui_col(Col.WINDOW_BG)
    if idx == COL_PLOT_BORDER:
        return _imgui_col(Col.BORDER)
    if idx == COL_LEGEND_BG:
        return _imgui_col(Col.POPUP_BG)
    if idx == COL_LEGEND_BORDER:
        return get_style_color_u32(COL_PLOT_BORDER)
    if idx == COL_LEGEND_TEXT:
        return get_style_color_u32(COL_INLAY_TEXT)
    if idx in (COL_TITLE_TEXT, COL_INLAY_TEXT, COL_AXIS_TEXT):
        return _imgui_col(Col.TEXT)
    if idx == COL_AXIS_GRID:
        c = get_style_color_u32(COL_AXIS_TEXT)
        return (c[0], c[1], c[2], int(c[3] * 0.25))
    if idx == COL_AXIS_TICK:
        return get_style_color_u32(COL_AXIS_GRID)
    if idx == COL_AXIS_BG:
        return (0, 0, 0, 0)
    if idx == COL_AXIS_BG_HOVERED:
        return _imgui_col(Col.BUTTON_HOVERED)
    if idx == COL_AXIS_BG_ACTIVE:
        return _imgui_col(Col.BUTTON_ACTIVE)
    if idx == COL_SELECTION:
        return (255, 255, 0, 255)
    if idx == COL_CROSSHAIRS:
        return get_style_color_u32(COL_PLOT_BORDER)
    return (0, 0, 0, 255)


def get_style_color_u32(idx: int) -> tuple:
    """``GetStyleColorU32``."""
    col = gp.style.colors[idx]
    return get_auto_color(idx) if col is None else col


def update_axis_colors(axis: Axis) -> None:
    """``UpdateAxisColors``."""
    grid = get_style_color_u32(COL_AXIS_GRID)
    axis.color_maj = grid
    axis.color_min = (grid[0], grid[1], grid[2], int(grid[3] * gp.style.minor_alpha))
    axis.color_tick = get_style_color_u32(COL_AXIS_TICK)
    axis.color_txt = get_style_color_u32(COL_AXIS_TEXT)
    axis.color_bg = get_style_color_u32(COL_AXIS_BG)
    axis.color_hov = get_style_color_u32(COL_AXIS_BG_HOVERED)
    axis.color_act = get_style_color_u32(COL_AXIS_BG_ACTIVE)


def get_colormap_color_u32(idx: int, cmap: int = IMPLOT_AUTO) -> tuple:
    cmap = gp.style.colormap if cmap == IMPLOT_AUTO else cmap
    n = gp.colormap_data.get_key_count(cmap)
    return gp.colormap_data.get_key_color(cmap, idx % n)


def next_colormap_color_u32() -> tuple:
    items = gp.current_items
    cmap = gp.style.colormap
    idx = items.colormap_idx % gp.colormap_data.get_key_count(cmap)
    col = gp.colormap_data.get_key_color(cmap, idx)
    items.colormap_idx += 1
    return col


def sample_colormap_u32(t: float, cmap: int = IMPLOT_AUTO) -> tuple:
    cmap = gp.style.colormap if cmap == IMPLOT_AUTO else cmap
    return gp.colormap_data.lerp_table(cmap, t)


# --------------------------------------------------------------------------- #
# [SECTION] Rects
# --------------------------------------------------------------------------- #
def rect_contains(r, p) -> bool:
    return r[0] <= p[0] < r[2] and r[1] <= p[1] < r[3]


def rect_overlaps(a, b) -> bool:
    return b[1] < a[3] and b[3] > a[1] and b[0] < a[2] and b[2] > a[0]


def rect_expand(r, amount: float):
    return (r[0] - amount, r[1] - amount, r[2] + amount, r[3] + amount)


def rect_size(r):
    return (r[2] - r[0], r[3] - r[1])


def rect_center(r):
    return ((r[0] + r[2]) * 0.5, (r[1] + r[3]) * 0.5)


def get_location_pos(outer, inner_size, loc: int, pad=(0.0, 0.0)):
    """``GetLocationPos``."""
    if has_flag(loc, LOCATION_WEST) and not has_flag(loc, LOCATION_EAST):
        x = outer[0] + pad[0]
    elif not has_flag(loc, LOCATION_WEST) and has_flag(loc, LOCATION_EAST):
        x = outer[2] - pad[0] - inner_size[0]
    else:
        x = rect_center(outer)[0] - inner_size[0] * 0.5
    if has_flag(loc, LOCATION_NORTH) and not has_flag(loc, LOCATION_SOUTH):
        y = outer[1] + pad[1]
    elif not has_flag(loc, LOCATION_NORTH) and has_flag(loc, LOCATION_SOUTH):
        y = outer[3] - pad[1] - inner_size[1]
    else:
        y = rect_center(outer)[1] - inner_size[1] * 0.5
    return (float(round(x)), float(round(y)))


def calc_legend_size(items: ItemGroup, pad, spacing, vertical: bool):
    """``CalcLegendSize``."""
    n = items.get_legend_count()
    txt_ht = text_line_height()
    icon_size = txt_ht
    widths = [calc_text_size(items.get_legend_label(i))[0] for i in range(n)]
    max_w = max(widths, default=0.0)
    sum_w = sum(widths)
    if vertical:
        return (pad[0] * 2 + icon_size + max_w, pad[1] * 2 + n * txt_ht + (n - 1) * spacing[1])
    return (pad[0] * 2 + icon_size * n + sum_w + (n - 1) * spacing[0], pad[1] * 2 + txt_ht)


def clamp_legend_rect(legend_rect, outer, pad):
    """``ClampLegendRect``: ``(rect, clamped)``."""
    x0, y0, x1, y1 = legend_rect
    ox0, oy0, ox1, oy1 = outer[0] + pad[0], outer[1] + pad[1], outer[2] - pad[0], outer[3] - pad[1]
    clamped = False
    if x0 < ox0:
        x0, clamped = ox0, True
    if y0 < oy0:
        y0, clamped = oy0, True
    if x1 > ox1:
        x1, clamped = ox1, True
    if y1 > oy1:
        y1, clamped = oy1, True
    return (x0, y0, x1, y1), clamped


def calc_bins(values, count: int, meth: int, rng):
    """``CalculateBins``: ``(bins, width)``."""
    rmin, rmax = rng
    width = 0.0
    if meth == BIN_SQRT:
        bins = int(math.ceil(math.sqrt(count)))
    elif meth == BIN_STURGES:
        bins = int(math.ceil(1.0 + math.log2(count)))
    elif meth == BIN_RICE:
        bins = int(math.ceil(2 * count ** (1.0 / 3.0)))
    elif meth == BIN_SCOTT:
        mu = sum(values[:count]) / count
        sd = math.sqrt(sum((v - mu) ** 2 for v in values[:count]) / max(count - 1, 1))
        width = 3.49 * sd / count ** (1.0 / 3.0)
        bins = int(round((rmax - rmin) / width)) if width > 0 else 1
    else:
        bins = 1
    bins = max(bins, 1)
    return bins, (rmax - rmin) / bins
