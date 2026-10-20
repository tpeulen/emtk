"""The palette and the arithmetic every painter-level control shares.

Why this exists
---------------
:mod:`.widgets` grew the first nineteen controls and kept its palette as a
block of private module constants. That was fine while there was one module;
it stops being fine the moment a second one wants the same blue, because two
modules holding their own copy of ``(66, 150, 250, 240)`` do not stay the same
colour -- they drift one tweak at a time, and nothing fails when they do.

So the palette lives here, once, and is **public**: a control in
:mod:`.drag` and a control in :mod:`.widgets` that both draw a slider grab
draw it in the same blue because they name the same constant.

Where the numbers come from
---------------------------
``StyleColorsDark`` in the reference implementation's ``imgui_draw.cpp``,
converted from its ``0.0-1.0`` floats to the ``0-255`` ints the chrome's
palette has always used. Names follow the reference's ``ImGuiCol_`` roles
with the prefix dropped, so a port can be checked against the source it came
from by reading down the column.

The three that are **not** the reference's
----------------------------------------------
:data:`TEXT`, :data:`DIM` and :data:`GOLD` predate this file and are what the
chrome already reads as. The reference's ``Text`` is pure white and its
``TextDisabled`` a flat mid-grey; these are slightly blue-cool and lighter
respectively, because the chrome is drawn *over a lit 3-D scene* rather than
over an opaque window, and pure white on a pale backdrop loses its edge.
Keeping them is deliberate -- a faithful palette that makes the chrome harder
to read is not the goal.
"""
from __future__ import annotations

import math
import re
from contextlib import contextmanager
from dataclasses import dataclass

#: Most horizontal bands a :func:`disc` is scan-converted into. A dot in this
#: chrome is a handful of pixels across, so the cap costs nothing visible and
#: bounds the quad count of a control that draws several of them.
_MAX_BANDS = 24

__all__ = [
    "Colour",
    "use_palette",
    "TEXT",
    "DIM",
    "GOLD",
    "TEXT_DISABLED",
    "WINDOW_BG",
    "POPUP_BG",
    "BORDER",
    "FRAME_BG",
    "FRAME_BG_HOVERED",
    "FRAME_BG_ACTIVE",
    "TITLE_BG",
    "TITLE_BG_ACTIVE",
    "MENU_BAR_BG",
    "SCROLLBAR_BG",
    "SCROLLBAR_GRAB",
    "SCROLLBAR_GRAB_HOVERED",
    "SCROLLBAR_GRAB_ACTIVE",
    "LINKED",
    "CHECK_MARK",
    "SLIDER_GRAB",
    "SLIDER_GRAB_ACTIVE",
    "BUTTON",
    "BUTTON_HOVERED",
    "BUTTON_ACTIVE",
    "HEADER",
    "HEADER_HOVERED",
    "HEADER_ACTIVE",
    "SEPARATOR",
    "SEPARATOR_HOVERED",
    "SEPARATOR_ACTIVE",
    "TAB",
    "TAB_SELECTED",
    "TAB_HOVERED",
    "PLOT_LINES",
    "PLOT_HISTOGRAM",
    "TABLE_HEADER_BG",
    "TABLE_BORDER_STRONG",
    "TABLE_BORDER_LIGHT",
    "TABLE_ROW_BG",
    "TABLE_ROW_BG_ALT",
    "TEXT_LINK",
    "TEXT_SELECTED_BG",
    "DRAG_DROP_TARGET",
    "NAV_CURSOR",
    "MODAL_DIM_BG",
    "HEADER_BG",
    "TRACK_BG",
    "THUMB",
    "THUMB_HELD",
    "ROW_SEL",
    "CHECK_ON",
    "BTN_BG",
    "BTN_HELD",
    "SCROLL_TRACK",
    "SCROLL_THUMB",
    "SCROLL_THUMB_HOT",
    "PLOT_BG",
    "PLOT_FRAME_BG",
    "PLOT_GRID",
    "PLOT_MINOR_GRID",
    "PLOT_TICK_TEXT",
    "PLOT_LABEL_TEXT",
    "PLOT_AXIS_LINE",
    "PLOT_LEGEND_BG",
    "TABLE_BAR",
    "TABLE_BAR_POSITIVE",
    "TABLE_BAR_NEGATIVE",
    "CODE_BG",
    "CODE_INLINE_BG",
    "HEADING_1",
    "HEADING_2",
    "HEADING_3",
    "HEADING_4",
    "TEXT_NOTE",
    "TEXT_TIP",
    "TEXT_WARNING",
    "TEXT_DANGER",
    "TEXT_QUOTE",
    "CARD_BG",
    "WORKSPACE_BG",
    "HOST_BG",
    "WATERMARK",
    "FRAME_BORDER_SIZE",
    "hit",
    "clamp",
    "lerp",
    "lerp_colour",
    "with_alpha",
    "fit_text",
    "format_value",
    "disc",
    "Accent",
    "ThemedAccent",
    "ButtonRole",
    "ThemedButtonRole",
    "BUTTON_ROLES",
    "ROLE_ALIASES",
    "button_role",
    "set_button_role",
    "parse_colour",
    "relative_luminance",
    "contrast_ratio",
    "is_dark",
    "most_readable",
    "ambient_colours",
    "current_ambient",
]

#: A colour: ``(r, g, b)`` or ``(r, g, b, a)``, 0-255. Re-exported from
#: :mod:`.painter` so a control module needs one import, not two.
Colour = tuple[int, int, int] | tuple[int, int, int, int]


# --------------------------------------------------------------------------
# The palette
# --------------------------------------------------------------------------
# emtk's own three (see the module docstring for why they are not the
# reference's).
TEXT = (235, 235, 240)
DIM = (150, 150, 160)
#: A row whose value is borrowed from another (a linked parameter): dimmer than TEXT, bluer than DIM.
LINKED = (140, 150, 235)
GOLD = (245, 225, 128)

# ImGuiCol_TextDisabled
TEXT_DISABLED = (128, 128, 128)
# ImGuiCol_WindowBg / PopupBg
WINDOW_BG = (15, 15, 15, 240)
POPUP_BG = (20, 20, 20, 240)
# ImGuiCol_Border
BORDER = (90, 90, 96, 200)
# ImGuiCol_FrameBg and its two states -- the background of every "field": a
# slider track, a checkbox square, a text box.
FRAME_BG = (50, 50, 56, 220)
FRAME_BG_HOVERED = (66, 150, 250, 102)
FRAME_BG_ACTIVE = (66, 150, 250, 171)
# ImGuiCol_TitleBg / TitleBgActive
TITLE_BG = (10, 10, 10, 255)
TITLE_BG_ACTIVE = (41, 74, 122, 255)
# ImGuiCol_MenuBarBg
MENU_BAR_BG = (36, 36, 36, 255)
# ImGuiCol_Scrollbar*
SCROLLBAR_BG = (5, 5, 5, 135)
SCROLLBAR_GRAB = (79, 79, 79, 255)
SCROLLBAR_GRAB_HOVERED = (105, 105, 105, 255)
SCROLLBAR_GRAB_ACTIVE = (130, 130, 130, 255)
# ImGuiCol_CheckMark
CHECK_MARK = (66, 150, 250, 255)
# ImGuiCol_SliderGrab / SliderGrabActive
SLIDER_GRAB = (61, 133, 224, 255)
SLIDER_GRAB_ACTIVE = (66, 150, 250, 255)
# ImGuiCol_Button and its two states
BUTTON = (66, 150, 250, 102)
BUTTON_HOVERED = (66, 150, 250, 255)
BUTTON_ACTIVE = (15, 135, 250, 255)
# ImGuiCol_Header* -- selectables, tree nodes, collapsing headers, the
# highlight behind a selected row.
HEADER = (66, 150, 250, 79)
HEADER_HOVERED = (66, 150, 250, 204)
HEADER_ACTIVE = (66, 150, 250, 255)
# ImGuiCol_Separator (the reference aliases this to Border) and the two
# states a *draggable* separator has. A plain rule never leaves the first,
# but a splitter is a control: without somewhere to say "you are on it" and
# "you have hold of it", the one widget whose whole job is to be grabbed
# gives no sign that it can be.
SEPARATOR = BORDER
SEPARATOR_HOVERED = (26, 102, 191, 199)
SEPARATOR_ACTIVE = (26, 102, 250, 255)
# ImGuiCol_Tab / TabSelected / TabHovered
TAB = (37, 63, 100, 255)
TAB_SELECTED = (51, 105, 173, 255)
TAB_HOVERED = HEADER_HOVERED
# ImGuiCol_PlotLines / PlotHistogram
PLOT_LINES = (156, 156, 156, 255)
PLOT_HISTOGRAM = (230, 179, 0, 255)
# ImGuiCol_Table*
TABLE_HEADER_BG = (48, 48, 51, 255)
TABLE_BORDER_STRONG = (79, 79, 89, 255)
TABLE_BORDER_LIGHT = (59, 59, 64, 255)
TABLE_ROW_BG = (25, 25, 28, 220)
TABLE_ROW_BG_ALT = (34, 34, 38, 220)
#: Header captions of a painted table (emtk's gold, as the chrome's headers).
TABLE_HEADER_TEXT = GOLD
# ImGuiCol_TextLink (the reference aliases this to HeaderActive)
TEXT_LINK = HEADER_ACTIVE
# ImGuiCol_TextSelectedBg
TEXT_SELECTED_BG = (66, 150, 250, 89)
# ImGuiCol_DragDropTarget
DRAG_DROP_TARGET = (255, 255, 0, 230)
# ImGuiCol_NavCursor -- the keyboard-focus ring.
NAV_CURSOR = (66, 150, 250, 255)
#: The wash a modal popup lays over everything behind it. The reference calls
#: this ``ModalWindowDimBg``.
MODAL_DIM_BG = (204, 204, 204, 89)
#: Blur what lies behind a modal window (a question, a modal menu) as well as washing it
#: with :data:`MODAL_DIM_BG`: the window in front is the only thing in focus. A user
#: preference, not part of a theme (:func:`emtk.backdrop.set_modal_blur`).
MODAL_BLUR = True
#: How far the blur reaches, in logical pixels (the Gaussian's sigma).
MODAL_BLUR_RADIUS = 6.0


# --------------------------------------------------------------------------
# emtk's own, kept at their shipped values
# --------------------------------------------------------------------------
# These are the names the first nineteen controls in :mod:`.widgets` were
# written against. Several are *close to* a role above but not equal to it,
# and the differences are the reason this block exists rather than a set of
# aliases: re-pointing ``CHECK_ON`` at :data:`CHECK_MARK` would silently turn
# every checkbox in the shipped chrome from green to blue, which is a restyle
# nobody asked for wearing the clothes of a refactor.
#
# Each is annotated with the role it is near and how it differs, so a future
# decision to converge on the reference is a decision someone can actually
# take, rather than a diff nobody can read.

#: :data:`TITLE_BG_ACTIVE` at alpha 235 -- the chrome sits over a lit scene
#: and its panel headers are deliberately not quite opaque.
HEADER_BG = (41, 74, 122, 235)
#: Identical to :data:`FRAME_BG`; kept as a name because the controls read
#: better saying "track" where a track is what it is.
TRACK_BG = FRAME_BG
#: :data:`SLIDER_GRAB_ACTIVE` at alpha 240.
THUMB = (66, 150, 250, 240)
#: emtk turns a held thumb **gold**; the reference brightens the same blue
#: instead. The gold reads at a glance over a scene of arbitrary colour,
#: which a second blue does not.
THUMB_HELD = (255, 200, 90, 240)
#: :data:`HEADER_HOVERED` at alpha 180.
ROW_SEL = (66, 150, 250, 180)
#: emtk's tick is **green**; the reference's :data:`CHECK_MARK` is the
#: accent blue. Green separates "this is on" from "this is selected", which
#: share a colour in the reference.
CHECK_ON = (90, 230, 120)
#: emtk's buttons are a desaturated slate rather than the reference's
#: translucent accent blue (:data:`BUTTON`), which disappears over a blue
#: scene.
BTN_BG = (50, 64, 82, 230)
#: The pressed state of :data:`BTN_BG`.
BTN_HELD = (75, 100, 135, 255)


# --------------------------------------------------------------------------
# Surfaces the reference has no role for
# --------------------------------------------------------------------------
# Each of these was a literal in the module that draws it. A literal does not follow a
# theme (:mod:`emtk.theme`), so a light window kept dark plots, code blocks and scroll
# thumbs; as palette names they switch with the rest.

#: A child region's scroll track, its thumb, and the thumb under the pointer or held.
SCROLL_TRACK = (25, 28, 35, 120)
SCROLL_THUMB = (95, 105, 125, 170)
SCROLL_THUMB_HOT = (160, 175, 205, 230)
#: A plot's data area when the plot does not choose one, its frame wash, grid lines,
#: tick numbers, axis captions, axis lines and legend box.
PLOT_BG = (30, 32, 38, 255)
PLOT_FRAME_BG = (0, 0, 0, 60)
PLOT_GRID = (255, 255, 255, 20)
PLOT_MINOR_GRID = (255, 255, 255, 9)
PLOT_TICK_TEXT = (160, 165, 175)
PLOT_LABEL_TEXT = (196, 201, 212)
PLOT_AXIS_LINE = (110, 115, 125)
PLOT_LEGEND_BG = (20, 22, 26, 200)
#: A table cell's in-cell bar: one whose range does not span zero, and a diverging one
#: right of zero (blue) and left of it (orange). Blue against orange stays apart under every
#: common colour-vision deficiency, and each keeps 3:1 against both table row colours.
TABLE_BAR = (90, 150, 220, 255)
TABLE_BAR_POSITIVE = (66, 150, 250, 255)
TABLE_BAR_NEGATIVE = (240, 150, 40, 255)
#: A code block's or a chat message's field.
CODE_BG = (20, 24, 30, 255)
#: The wash behind inline ``code`` in running text.
CODE_INLINE_BG = (255, 255, 255, 28)
#: Document text roles (markdown headings, admonitions, quotes, table captions).
HEADING_1 = (125, 205, 255, 255)
HEADING_2 = (145, 225, 160, 255)
HEADING_3 = (245, 205, 115, 255)
HEADING_4 = (220, 225, 235, 255)
TEXT_NOTE = (110, 190, 255, 255)
TEXT_TIP = (130, 220, 140, 255)
TEXT_WARNING = (235, 185, 95, 255)
TEXT_DANGER = (245, 110, 110, 255)
TEXT_QUOTE = (160, 175, 195, 255)
#: A panel drawn over the window (a tour card, a dialog body).
CARD_BG = (26, 28, 36, 250)
#: What a host surface is cleared to before the control draws (the gaps between docks).
HOST_BG = (30, 32, 38, 255)
#: A host-drawn workspace behind the docked windows, and a watermark drawn on it.
WORKSPACE_BG = (12, 12, 14, 255)
WATERMARK = (255, 255, 255, 18)

#: The outline around fields and buttons, in pixels (``Style.frame_border_size``): none on
#: the dark theme; a light theme needs it, since a white field on a pale window has no edge.
#: Not a colour, so :func:`use_palette` leaves it alone; :func:`emtk.theme.apply_theme` sets it.
FRAME_BORDER_SIZE = 0.0


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------
def hit(
    x: float,
    y: float,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
) -> bool:
    """Whether ``(x, y)`` lands inside the box.

    Every control's ``press`` starts with this test, and each of the first
    nineteen wrote it out inline. Written nineteen times it is nineteen
    chances to compare against ``box_w`` where ``box_x + box_w`` was meant --
    a bug that shows up as a control that only responds near the left edge of
    the screen, and never at all once it is laid out anywhere else.

    Parameters
    ----------
    x, y : float
        The point, in the same space the box is given in.
    box_x, box_y, box_w, box_h : float
        The box: its top-left corner, its width and its height.

    Returns
    -------
    bool
        True if the point is inside, edges included.
    """
    return box_x <= x <= box_x + box_w and box_y <= y <= box_y + box_h


def clamp(value: float, low: float, high: float) -> float:
    """``value`` confined to ``[low, high]``.

    Parameters
    ----------
    value : float
        The number.
    low, high : float
        The bounds. Passed reversed, ``low`` wins -- the same as the
        reference's ``ImClamp``.

    Returns
    -------
    float
        The confined value.
    """
    return low if value < low else (high if value > high else value)


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from ``a`` to ``b`` by ``t``.

    Parameters
    ----------
    a, b : float
        The ends.
    t : float
        The position between them. Not clamped: callers that want the segment
        rather than the line clamp first, which is what the reference does.

    Returns
    -------
    float
        ``a + (b - a) * t``.
    """
    return a + (b - a) * t


def lerp_colour(a: Colour, b: Colour, t: float) -> tuple[int, int, int, int]:
    """Blend two colours channel by channel, alpha included.

    The reference builds several of its dark-theme entries this way
    (``ImLerp(colors[Header], colors[TitleBgActive], 0.80f)``), and the
    controls use it for hover states.

    Parameters
    ----------
    a, b : Colour
        The ends. A three-tuple is taken as fully opaque.
    t : float
        Position between them; clamped to ``0..1``.

    Returns
    -------
    tuple of int
        The blended ``(r, g, b, a)``.
    """
    t = clamp(float(t), 0.0, 1.0)
    ca = tuple(a) + ((255,) if len(a) < 4 else ())
    cb = tuple(b) + ((255,) if len(b) < 4 else ())
    return tuple(int(round(lerp(ca[i], cb[i], t))) for i in range(4))


def with_alpha(colour: Colour, alpha: int) -> tuple[int, int, int, int]:
    """``colour`` at a different opacity.

    Parameters
    ----------
    colour : Colour
        The colour; its own alpha is discarded.
    alpha : int
        The new alpha, 0-255, clamped.

    Returns
    -------
    tuple of int
        ``(r, g, b, alpha)``.
    """
    c = tuple(colour)
    return (c[0], c[1], c[2], int(clamp(alpha, 0, 255)))


def disc(p, cx: float, cy: float, radius: float, colour: Colour) -> None:
    """Draw a filled circle as a stack of horizontal bands.

    The painter has no circle operation, so the disc is scan-converted: each
    band spans ``2 * sqrt(r^2 - dy^2)``, measured at the band's *middle*. The
    obvious alternative -- measuring at the edge nearest the centre, so the
    silhouette never cuts inside the true circle -- makes the polar bands far
    too wide (two thirds of the diameter where the circle is at half) and the
    dot reads as a rounded square at every size the chrome uses.

    Shared rather than per-module because a radio button, a list bullet and a
    colour picker's cursor are the same circle. Two of them were drawn
    differently -- one scan-converted here, one an inscribed square -- which
    is invisible in any one control and obvious the moment a bullet sits above
    a radio button.

    Parameters
    ----------
    p : Painter
        Where to draw.
    cx, cy : float
        Centre.
    radius : float
        Radius, in pixels. Nothing is drawn for a non-positive radius.
    colour : Colour
        Fill colour.
    """
    if radius <= 0.0:
        return
    bands = int(clamp(round(radius), 3, _MAX_BANDS))
    step = 2.0 * radius / bands
    for index in range(bands):
        top = cy - radius + index * step
        middle = top + step * 0.5 - cy
        half = math.sqrt(max(radius * radius - middle * middle, 0.0))
        if half > 0.0:
            p.fill_rect(cx - half, top, 2.0 * half, step, colour)


def tab_cap(widths, room: float, floor: float) -> float:
    """The width above which tabs are shortened so that *widths* fit *room*.

    Water-filling: the widest tabs give way first and the narrow ones stay whole. The cap never goes
    under *floor*; a strip that still does not fit then scrolls (or runs on) instead.

    Parameters
    ----------
    widths : sequence of float
        The natural width of every tab.
    room : float
        The width of the strip.
    floor : float
        The narrowest a tab is squeezed to.

    Returns
    -------
    float
        The cap; no tab is wider than it.
    """
    widths = list(widths)
    if len(widths) < 2 or sum(widths) <= room:
        return max(widths, default=0.0)
    cap = max(widths)
    while cap > floor and sum(min(w, cap) for w in widths) > room:
        cap -= 1.0
    return max(cap, floor)


def fit_text(p, label: str, room: float) -> str:
    """``label`` shortened with a trailing dot until it fits ``room``.

    The painter clips nothing by itself, so a caption wider than its column is
    drawn straight over the neighbouring one -- which reads as a layout bug
    rather than as a name that did not fit.

    Parameters
    ----------
    p : Painter
        Used to measure.
    label : str
        The text.
    room : float
        Width available.

    Returns
    -------
    str
        The text, or as much of it as fits.
    """
    # Half a pixel of slack: a column sized to exactly the widest label comes
    # back through float arithmetic as 41.99999999999999 against a 42.0 label,
    # and the widest entry of every menu lost its last letter to a dot.
    if room <= 0.0:
        return ""  # no room: the whole label would be drawn over the neighbour
    if p.text_width(label) <= room + 0.5:
        return label
    for cut in range(len(label) - 1, 0, -1):
        short = label[:cut] + "."
        if p.text_width(short) <= room + 0.5:
            return short
    return ""


#: ``%.0%`` and friends: a percentage, written the way the value reads rather
#: than the way printf would need it (``%.0f%%`` against a value already
#: multiplied by a hundred). ``"%.0%" % 0.5`` is a ``ValueError``, which is why
#: this is a substitution and not a format string.
_PERCENT_SPEC = re.compile(r"%\.(\d+)%")


def format_value(fmt: str, value: float) -> str:
    """Render a number through a control's format string.

    Parameters
    ----------
    fmt : str
        Either a printf spec (``"%.1f tiles"``) or a percentage spec
        (``"%.0%"``), which multiplies by a hundred and appends a sign.
    value : float
        The number.

    Returns
    -------
    str
        The rendered text. A format string the value does not fit falls back
        to two decimals rather than raising: a slider that cannot draw its own
        label takes the whole frame down with it.
    """
    match = _PERCENT_SPEC.search(fmt)
    if match:
        digits = int(match.group(1))
        return fmt[: match.start()] + f"{value * 100.0:.{digits}f}%" + fmt[match.end():]
    try:
        return fmt % value
    except (TypeError, ValueError):
        return f"{value:.2f}"



def use_palette(colours: dict) -> dict:
    """Replace palette entries; returns the entries it replaced.

    The painter-level controls read this module's colours as they draw, so an
    application that is not drawn over a dark scene -- a desktop tool in a
    light window -- installs its palette once at start-up::

        previous = style.use_palette({"TEXT": (0, 0, 0), "BORDER": (160, 160, 160)})
        ...
        style.use_palette(previous)        # put it back (a test does)

    Immediate-mode windows take their colours from an
    :class:`~emtk.im_core.Style`, whose defaults are read from here when it is
    made, so a style made after this call starts from the new palette too.

    Parameters
    ----------
    colours : dict
        Upper-case palette name -> colour.

    Returns
    -------
    dict
        The previous colour of every name given.

    Raises
    ------
    KeyError
        For a name that is not in the palette -- a typo would otherwise
        silently leave the old colour in place.
    """
    module = globals()
    previous = {}
    for name, colour in colours.items():
        if not name.isupper() or name not in module or not isinstance(module[name], tuple):
            raise KeyError(f"{name!r} is not a palette colour")
        previous[name] = module[name]
    module.update({name: tuple(colour) for name, colour in colours.items()})
    return previous


# --------------------------------------------------------------------------
# Accents: a colour that marks what a panel is for
# --------------------------------------------------------------------------
def parse_colour(value) -> tuple[int, int, int, int]:
    """``"#rrggbb"``, ``"#rrggbbaa"`` or an ``(r, g, b[, a])`` tuple -> ``(r, g, b, a)``.

    Raises
    ------
    ValueError
        For anything else -- a palette file with a typo must fail where it is read.
    """
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) not in (6, 8) or not re.fullmatch(r"[0-9a-fA-F]+", text):
            raise ValueError(f"{value!r} is not a #rrggbb colour")
        channels = [int(text[i:i + 2], 16) for i in range(0, len(text), 2)]
    else:
        channels = [int(v) for v in value]
        if len(channels) not in (3, 4) or not all(0 <= v <= 255 for v in channels):
            raise ValueError(f"{value!r} is not an (r, g, b[, a]) colour")
    return tuple(channels + [255] * (4 - len(channels)))


def relative_luminance(colour: Colour) -> float:
    """WCAG 2 relative luminance of *colour* (its alpha ignored), 0 (black) .. 1 (white)."""

    def channel(v: float) -> float:
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(float(v)) for v in tuple(colour)[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: Colour, b: Colour) -> float:
    """WCAG 2 contrast ratio of two opaque colours, 1 .. 21 (text needs 4.5)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def is_dark(colour: Colour) -> bool:
    """Whether *colour* is a dark background (light text reads better on it than dark text)."""
    return contrast_ratio(colour, (255, 255, 255)) >= contrast_ratio(colour, (0, 0, 0))


def most_readable(background: Colour, *candidates: Colour) -> tuple[int, int, int, int]:
    """The candidate text colour with the highest contrast on *background*."""
    best = max(candidates, key=lambda c: contrast_ratio(background, c))
    return parse_colour(best)


@dataclass(frozen=True)
class Accent:
    """A colour that tells which kind of task a panel belongs to.

    An application gives a dock window (:class:`emtk.docking.DockWindow`) or a ribbon group
    (:class:`emtk.ribbon.RibbonGroup`) an accent; the toolkit draws the active tab in
    :attr:`fill` with :attr:`text`, an inactive tab in a muted share of it, a stripe under
    the tab strip and the group caption in :attr:`ink`. Which colours mean what is the
    application's business (a palette file), so the class holds colours only.

    Attributes
    ----------
    fill : Colour
        The strong colour: an active tab's background.
    text : Colour
        Text on :attr:`fill` (white by default).
    ink : Colour or None
        The colour as a foreground on the window background (a caption, a stripe);
        :attr:`fill` when not given.
    muted : float
        Share of :attr:`fill` mixed into the neutral background of an inactive tab or a
        section header.
    """

    fill: Colour
    text: Colour = (255, 255, 255, 255)
    ink: Colour | None = None
    muted: float = 0.35

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill", parse_colour(self.fill))
        object.__setattr__(self, "text", parse_colour(self.text))
        if self.ink is not None:
            object.__setattr__(self, "ink", parse_colour(self.ink))

    @property
    def foreground(self) -> tuple[int, int, int, int]:
        """:attr:`ink`, else :attr:`fill`: the accent drawn as a line or a caption."""
        return self.ink if self.ink is not None else self.fill

    def mute(self, base: Colour, share: float | None = None) -> tuple[int, int, int, int]:
        """*base* (a neutral background) with :attr:`muted` (or *share*) of :attr:`fill`, *base*'s alpha kept."""
        mixed = lerp_colour(base, self.fill, self.muted if share is None else share)
        alpha = tuple(base)[3] if len(tuple(base)) > 3 else 255
        return (mixed[0], mixed[1], mixed[2], alpha)

    def mute_readable(self, base: Colour, text: Colour, share: float = 0.55,
                      behind: Colour | None = None, minimum: float = 4.5) -> tuple[int, int, int, int]:
        """:meth:`mute` *base* with the largest share up to *share* that keeps *text* readable.

        For a background whose text colour is not the accent's to choose (a section header, a
        child window's title bar): the tint backs off until *text* has *minimum* contrast on
        it. A translucent result is judged over *behind* (the window background). When no
        share reaches *minimum*, the one with the best contrast.
        """
        best, best_ratio = None, -1.0
        steps = max(int(round(share / 0.05)), 0)
        for i in range(steps, -1, -1):
            colour = self.mute(base, share * i / steps if steps else 0.0)
            seen = colour
            if behind is not None and colour[3] < 255:
                seen = lerp_colour(behind, colour, colour[3] / 255.0)
            ratio = contrast_ratio(seen, text)
            if ratio >= minimum:
                return colour
            if ratio > best_ratio:
                best, best_ratio = colour, ratio
        return best

    def muted_text(self, background: Colour, text: Colour) -> tuple[int, int, int, int]:
        """The better of the theme's *text* and :attr:`text` on a muted *background*."""
        return most_readable(background, text, self.text)



@dataclass(frozen=True)
class ThemedAccent:
    """An :class:`Accent` for each theme; the one for the window background drawn on is used.

    An application declares a kind's colour once per theme; the toolkit picks by the
    background's lightness (:func:`is_dark`) at draw time, so a theme switch needs no
    re-assignment.
    """

    dark: Accent
    light: Accent

    def resolve(self, background: Colour) -> Accent:
        """:attr:`dark` on a dark *background*, else :attr:`light`."""
        return self.dark if is_dark(background) else self.light


#: The colours apps drawn now take over their own (innermost last); see :func:`ambient_colours`.
_AMBIENT: list[dict] = []


@contextmanager
def ambient_colours(colours: dict):
    """While inside, every :class:`emtk.app.ImApp` drawn takes *colours* (``Col`` role -> colour).

    A host that draws other apps inside a region (``ImApp.draw_child``) uses it to give the
    region's look to whatever is drawn there -- also to the apps those apps host in turn,
    which a change of the child's own style would not reach. Nested blocks merge, the inner
    one winning.
    """
    merged = dict(_AMBIENT[-1]) if _AMBIENT else {}
    merged.update(colours)
    _AMBIENT.append(merged)
    try:
        yield merged
    finally:
        _AMBIENT.pop()


def current_ambient() -> dict:
    """The colours of the innermost :func:`ambient_colours` block (empty outside any)."""
    return _AMBIENT[-1] if _AMBIENT else {}


# --------------------------------------------------------------------------
# Button roles: what kind of action a button is
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ButtonRole:
    """The colours of a button whose kind of action is declared (its *role*).

    A panel leads with one main action (Fit, Run, Compute) and may carry a destructive one
    (Delete, Clear, Stop); the rest are neutral. A role names that kind, and the toolkit draws
    it from these colours: :attr:`fill` at rest, :attr:`hovered` under the pointer,
    :attr:`active` while held, :attr:`text` on all three. Each must keep :attr:`text` at
    WCAG AA (4.5:1) -- ``tests/test_button_roles.py`` holds every shipped role to it.

    A disabled role button does not keep its colour: :meth:`disabled_fill` mixes only
    :attr:`disabled_share` of :attr:`fill` into the neutral button colour, so a primary
    action that cannot run reads as unavailable, not as a live button drawn faintly.
    """

    fill: Colour
    hovered: Colour
    active: Colour
    text: Colour = (255, 255, 255, 255)
    disabled_share: float = 0.3

    def __post_init__(self) -> None:
        for name in ("fill", "hovered", "active", "text"):
            object.__setattr__(self, name, parse_colour(getattr(self, name)))

    def disabled_fill(self, neutral: Colour) -> tuple[int, int, int, int]:
        """*neutral* (the theme's button colour) with :attr:`disabled_share` of :attr:`fill`, opaque."""
        mixed = lerp_colour(neutral, self.fill, self.disabled_share)
        return (mixed[0], mixed[1], mixed[2], 255)


@dataclass(frozen=True)
class ThemedButtonRole:
    """A :class:`ButtonRole` per theme, picked by the window background's lightness at draw time."""

    dark: ButtonRole
    light: ButtonRole

    def resolve(self, background: Colour) -> ButtonRole:
        """:attr:`dark` on a dark *background*, else :attr:`light`."""
        return self.dark if is_dark(background) else self.light


#: The shipped roles. ``"default"`` (or ``None``) is the neutral button and has no entry.
#: ``primary`` is the one main action of a panel (accent blue), ``success`` a confirming
#: action (green), ``danger`` a destructive one (red). Light-theme fills are darker so the
#: white text keeps its contrast; hover darkens there and lightens on the dark theme.
BUTTON_ROLES: dict[str, ThemedButtonRole] = {
    "primary": ThemedButtonRole(
        dark=ButtonRole((38, 104, 196), (44, 112, 206), (28, 88, 170)),
        light=ButtonRole((25, 103, 210), (21, 90, 190), (13, 71, 161)),
    ),
    "success": ThemedButtonRole(
        dark=ButtonRole((28, 120, 56), (34, 134, 64), (24, 104, 48)),
        light=ButtonRole((30, 126, 58), (26, 112, 52), (20, 96, 44)),
    ),
    "danger": ThemedButtonRole(
        dark=ButtonRole((156, 52, 52), (172, 60, 60), (136, 44, 44)),
        light=ButtonRole((176, 48, 48), (158, 40, 40), (136, 32, 32)),
    ),
}
#: Other spellings a spec may use for a role.
ROLE_ALIASES: dict[str, str] = {"confirm": "success", "destructive": "danger", "accent": "primary"}


def button_role(role: str | None, background: Colour) -> ButtonRole | None:
    """The colours of *role* on *background* (the window background); ``None`` for a neutral button.

    Raises
    ------
    ValueError
        For a role that is not :data:`BUTTON_ROLES` or :data:`ROLE_ALIASES` -- a typo in a
        spec must fail where it is drawn, not silently draw a plain button.
    """
    if role is None or role == "" or role == "default":
        return None
    name = ROLE_ALIASES.get(role, role)
    themed = BUTTON_ROLES.get(name)
    if themed is None:
        known = ", ".join(sorted({"default", *BUTTON_ROLES, *ROLE_ALIASES}))
        raise ValueError(f"{role!r} is not a button role ({known})")
    return themed.resolve(background)


def set_button_role(name: str, role: ThemedButtonRole) -> ThemedButtonRole | None:
    """Give role *name* an application's colours; returns the previous ones (``None`` for a new role)."""
    previous = BUTTON_ROLES.get(name)
    BUTTON_ROLES[name] = role
    return previous
