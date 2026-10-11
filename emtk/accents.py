"""Accents in the immediate-mode UI: the colour of a kind of task, drawn the same way everywhere.

An application colour-codes its panels by what they are for (documentation, wizards,
imaging, ...). It declares the colours (:class:`emtk.style.Accent`, or
:class:`emtk.style.ThemedAccent` with a dark and a light variant) and says which panel is
which kind; this module and the controls that take an ``accent`` do the drawing:

* :class:`emtk.docking.DockWindow` ``accent`` -- the tab (strong on top, muted behind), the
  stripe under the tab strip, a floating title bar, and with ``header_tint`` the section
  headers inside;
* :class:`emtk.ribbon.RibbonGroup` / :class:`~emtk.ribbon.RibbonButton` ``accent`` -- the
  group caption and underline, a bar on a button of another kind;
* :func:`region` -- around ``ImApp.draw_child``: the hosted app (and the apps it hosts) wear
  the tint on their headers, tabs and title bars;
* :func:`headers`, :func:`caption`, :func:`mark_item` -- a tree or list of tools: a header
  tinted, a caption written in the colour, a bar beside an item.

Every tint keeps the theme's text readable: it backs off until the text has a WCAG contrast
of 4.5, or at least the contrast the theme's own colour had
(:meth:`emtk.style.Accent.mute_readable`).
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

from . import im_core as _core
from . import style as _style

__all__ = [
    "AnyAccent",
    "caption",
    "header_colours",
    "headers",
    "mark_item",
    "neutral_tab",
    "region",
    "region_colours",
    "resolve",
]

#: What a control's ``accent`` may be.
AnyAccent = _style.Accent | _style.ThemedAccent

#: The section-header colours a tint recolours. emtk draws a collapsing header in the button
#: colours (a selected row in the header ones), so both.
_HEADER_ROLES = (_core.Col.HEADER, _core.Col.HEADER_HOVERED, _core.Col.HEADER_ACTIVE,
                 _core.Col.BUTTON, _core.Col.BUTTON_HOVERED, _core.Col.BUTTON_ACTIVE)
#: The tab and title-bar roles :func:`region_colours` tints, with the share of the accent.
_REGION_SHARES = ((_core.Col.TAB, 0.35), (_core.Col.TAB_SELECTED, 0.7),
                  (_core.Col.TITLE_BG, 0.35), (_core.Col.TITLE_BG_ACTIVE, 0.55))
#: Width of the bar :func:`mark_item` draws, and its gap to the item.
MARK_WIDTH = 3.0
MARK_GAP = 3.0


def resolve(accent: AnyAccent | None, style=None) -> _style.Accent | None:
    """The plain :class:`~emtk.style.Accent` to draw *accent* with on *style* (the current one)."""
    if accent is None or isinstance(accent, _style.Accent):
        return accent
    if style is None:
        style = _core.get_current_context().style
    return accent.resolve(style.color(_core.Col.WINDOW_BG))


def neutral_tab(style) -> tuple:
    """The theme's inactive tab colour without its hue: the ground an accent is muted into.

    The default tab colour is a blue, and a blue ground would tint every accent towards blue
    (and make a blue accent indistinguishable from no accent), so the ground is its grey of
    the same lightness.
    """
    r, g, b, a = _style.parse_colour(style.color(_core.Col.TAB))
    grey = round(0.299 * r + 0.587 * g + 0.114 * b)
    return (grey, grey, grey, a)


@lru_cache(maxsize=1024)
def _tint(base: tuple, accent: _style.Accent, share: float, text: tuple,
          behind: tuple | None) -> tuple:
    """*base*'s grey with a readable muted share of *accent* (cached: drawn every frame).

    Readable means 4.5:1 for the theme's *text*, or -- where the theme's own *base* does not
    reach that -- no less than *base* had.
    """
    def seen(colour):
        if behind is not None and colour[3] < 255:
            return _style.lerp_colour(behind, colour, colour[3] / 255.0)
        return colour

    floor = min(4.5, _style.contrast_ratio(seen(base), text))
    grey = round(0.299 * base[0] + 0.587 * base[1] + 0.114 * base[2])
    tinted = accent.mute_readable((grey, grey, grey, base[3]), text, share, behind=behind,
                                  minimum=floor)
    if _style.contrast_ratio(seen(tinted), text) >= floor:
        return tinted
    # The theme's hue was carrying the contrast (its grey reads worse): tint the colour itself.
    return accent.mute_readable(base, text, share, behind=behind, minimum=floor)


def header_colours(style, accent: AnyAccent) -> dict[int, tuple]:
    """Section-header colours (``Col.HEADER*``, ``Col.BUTTON*``) of *style*, tinted with *accent*.

    Each role keeps its alpha (a resting header is translucent).
    """
    accent = resolve(accent, style)
    text = _style.parse_colour(style.color(_core.Col.TEXT))
    behind = _style.parse_colour(style.color(_core.Col.WINDOW_BG))
    return {role: _tint(_style.parse_colour(style.color(role)), accent, 0.55, text, behind)
            for role in _HEADER_ROLES}


def region_colours(style, accent: AnyAccent) -> dict[int, tuple]:
    """The colours of an app drawn inside a panel with *accent*: headers, tabs and title bars.

    :func:`header_colours` plus the tab strip (``TAB``, ``TAB_SELECTED``) and window title
    bars (``TITLE_BG``, ``TITLE_BG_ACTIVE``), each a readable muted share of the accent.
    """
    accent = resolve(accent, style)
    out = header_colours(style, accent)
    text = _style.parse_colour(style.color(_core.Col.TEXT))
    behind = _style.parse_colour(style.color(_core.Col.WINDOW_BG))
    for role, share in _REGION_SHARES:
        out[role] = _tint(_style.parse_colour(style.color(role)), accent, share, text, behind)
    return out


@contextmanager
def headers(accent: AnyAccent | None):
    """Inside: section headers (and selected rows, buttons) drawn in *accent*'s tint."""
    if accent is None:
        yield
        return
    ctx = _core.get_current_context()
    colours = header_colours(ctx.style, accent)
    for role, colour in colours.items():
        ctx.push_style_color(role, colour)
    try:
        yield
    finally:
        ctx.pop_style_color(len(colours))


@contextmanager
def region(accent: AnyAccent | None):
    """Inside: every app drawn (``ImApp.draw_child``) wears *accent*'s :func:`region_colours`.

    Reaches the apps those apps host in turn (:func:`emtk.style.ambient_colours`).
    """
    if accent is None:
        yield
        return
    with _style.ambient_colours(region_colours(_core.get_current_context().style, accent)):
        yield


def caption(text: str, accent: AnyAccent | None) -> None:
    """A caption line in *accent*'s ink (the theme's disabled text without one)."""
    from . import im_widgets as _w

    accent = resolve(accent)
    if accent is None:
        _w.text_disabled(text)
    else:
        _w.text_colored(accent.foreground, text)


def mark_item(accent: AnyAccent | None) -> None:
    """A thin bar of *accent* just left of the last item (a tool in a list of several kinds)."""
    accent = resolve(accent)
    if accent is None:
        return
    ctx = _core.get_current_context()
    rect = ctx.get_item_rect()
    if not rect:
        return
    x, y, _w, h = rect
    left = x - MARK_GAP - MARK_WIDTH
    ctx.draw.add_rect_filled((left, y + 2.0), (left + MARK_WIDTH, y + h - 2.0), accent.foreground)
