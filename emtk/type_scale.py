"""One type scale for every piece of text emtk draws.

Why this exists
---------------
Text sizes used to be chosen where the text was drawn: the Markdown widget
scaled its headings by ``1.55``/``1.3``/``1.15``, a documentation browser drew
its body at the *host toolkit's* 13 pt (an emtk point is not a Qt point), and
a heading pushed ``{"bold": True}`` and so silently fell back to the default
size underneath a 13 pt body. Every one of those was a size nobody else could
see, so the help window and the documentation viewer drifted apart from each
other and from the rest of the interface.

The scale
---------
Every size is a *role*, a whole number of steps away from the body:

========  =====  =======================================================
role      steps  used for
========  =====  =======================================================
caption   -1     figure captions, footnotes, secondary notes
body       0     prose, list items, table cells, tooltips, the chrome
code       0     code (monospace, at the body size)
h4         1     fourth-level headings
h3         2     third-level headings
h2         3     section headings
h1         4     page titles
========  =====  =======================================================

One step is :data:`STEP` (a major second, 1.125), so ``h1`` is 1.6x the body
and a caption 0.89x. The body *is* the interface font: the size every button,
label and table cell is already drawn at.

The setting
-----------
The body size is **one** number, :func:`ui_font_pt`, the user's interface
font size in emtk points. Hosts that are not handed an explicit ``font_pt``
follow it (a change takes effect on the next frame), and the style editor
exposes it. Changing it scales every role together, because the role sizes
below are expressed against the size the font atlas is baked at and the
painter multiplies by ``ui_font_pt / baked`` once, for all text alike.

Use :func:`text_font` to get the font for a role, or :func:`text_style` /
:func:`push_text_style` to draw in it. Never pass a literal size.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

from .font import DEFAULT_FONT_PT

__all__ = [
    "ROLES",
    "STEP",
    "PROSE_FAMILY",
    "CODE_FAMILY",
    "ui_font_pt",
    "set_ui_font_pt",
    "factor",
    "size_pt",
    "text_font",
    "math_args",
    "push_text_style",
    "pop_text_style",
    "text_style",
]

#: Ratio between two neighbouring sizes of the scale.
STEP = 1.125

#: Steps above (positive) or below (negative) the body size.
ROLES: dict[str, int] = {
    "caption": -1,
    "body": 0,
    "code": 0,
    "h4": 1,
    "h3": 2,
    "h2": 3,
    "h1": 4,
}

#: The face prose and headings are set in; code and the chrome stay monospace.
#:
#: ``"prose"`` is its own generic family (see :func:`emtk.font_render.font_spec`):
#: Verdana, else DejaVu Sans / Bitstream Vera Sans, before the plain sans-serif
#: list. The chrome is baked from Menlo, a Bitstream Vera (= DejaVu Sans Mono)
#: derivative, and these are its proportional relatives: the same x-height
#: (~0.55 em, so prose and chrome capitals and lower case line up), open
#: apertures and wide spacing, drawn for the screen at ten pixels. Arial at the
#: body size (10.7 px) set words that read as glued together and thin beside
#: the chrome -- what users compared the documentation against.
PROSE_FAMILY = "prose"
CODE_FAMILY = "monospace"

#: Smallest and largest interface size a user may choose, in emtk points.
MIN_UI_FONT_PT = 6.0
MAX_UI_FONT_PT = 24.0

#: Environment override for the initial interface size (``EMTK_FONT_PT=10``).
ENV = "EMTK_FONT_PT"

_ui_font_pt: float | None = None


def _clamp(pt: float) -> float:
    return min(MAX_UI_FONT_PT, max(MIN_UI_FONT_PT, float(pt)))


def ui_font_pt() -> float:
    """The interface (= body) font size in emtk points: the one setting.

    Defaults to :data:`emtk.font.DEFAULT_FONT_PT`, or ``$EMTK_FONT_PT``.
    """
    global _ui_font_pt
    if _ui_font_pt is None:
        try:
            _ui_font_pt = _clamp(float(os.environ.get(ENV, "") or DEFAULT_FONT_PT))
        except ValueError:
            _ui_font_pt = DEFAULT_FONT_PT
    return _ui_font_pt


def set_ui_font_pt(pt: float) -> float:
    """Set the interface font size (clamped); returns the size in force."""
    global _ui_font_pt
    _ui_font_pt = _clamp(pt)
    return _ui_font_pt


def factor(role: str = "body") -> float:
    """Size of *role* as a multiple of the body size."""
    try:
        return STEP ** ROLES[role]
    except KeyError:
        raise ValueError(f"unknown text role {role!r}; one of {sorted(ROLES)}") from None


def size_pt(role: str = "body") -> float:
    """Font-spec size of *role*, in points **relative to the baked interface size**.

    This is the number a ``push_font({"size": ...})`` takes: the painter scales
    every font spec by ``ui_font_pt() / baked`` once, so the body role is the
    baked size and the user setting scales every role alike.
    """
    return _baked_pt() * factor(role)


def _baked_pt() -> float:
    """The size the interface atlas is baked at: what a spec size of "body" is."""
    from .font import load_atlas  # noqa: PLC0415

    return float(load_atlas().font_pt)


def text_font(role: str = "body", *, bold: bool | None = None,
              family: str | None = None, zoom: float = 1.0) -> dict:
    """The font dict (for ``im.push_font``) of *role*.

    Parameters
    ----------
    role : str
        A key of :data:`ROLES`.
    bold : bool, optional
        Headings are bold by default, everything else regular.
    family : str, optional
        Overrides the role's face (prose: :data:`PROSE_FAMILY`; code:
        :data:`CODE_FAMILY`).
    zoom : float
        A reader's own zoom on top of the scale (a documentation browser's
        A-/A+); 1.0 everywhere else.
    """
    heading = role.startswith("h")
    if family is None:
        family = CODE_FAMILY if role == "code" else PROSE_FAMILY
    return {
        "family": family,
        "size": size_pt(role) * float(zoom),
        "bold": heading if bold is None else bool(bold),
    }


def math_args(role: str = "body", zoom: float = 1.0) -> dict:
    """``font_size``/``scale`` for :func:`emtk.im.math` at *role*'s size.

    The formula is rasterised at twice its display size (``scale=0.5``) so it
    stays sharp on a 2x display; its display size follows the setting like text.
    """
    display = size_pt(role) * float(zoom) * ui_font_pt() / _baked_pt()
    return {"font_size": 2.0 * display, "scale": 0.5}


def push_text_style(role: str = "body", **kwargs) -> None:
    """``im.push_font(text_font(role, ...))``; pair with :func:`pop_text_style`."""
    from . import im_widgets  # noqa: PLC0415

    im_widgets.push_font(text_font(role, **kwargs))


def pop_text_style() -> None:
    """Undo :func:`push_text_style`."""
    from . import im_widgets  # noqa: PLC0415

    im_widgets.pop_font()


@contextmanager
def text_style(role: str = "body", **kwargs):
    """``with text_style("h2"):`` -- draw the block in *role*'s font."""
    push_text_style(role, **kwargs)
    try:
        yield
    finally:
        pop_text_style()
