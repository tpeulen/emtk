"""Themes: one set of palette values per look, switched for the whole process.

Every colour emtk draws with is a palette name in :mod:`emtk.style` (``WINDOW_BG``,
``TAB``, ``TABLE_ROW_BG``, ``PLOT_GRID`` ...), read by the controls as they draw, and an
immediate-mode :class:`~emtk.im_core.Style` made without colours copies them. So a theme
is a value for every palette name, and switching is :func:`emtk.style.use_palette` with
all of them:

    from emtk import theme
    theme.apply_theme("light")      # every window, dock, table, plot, field and menu
    theme.apply_theme("dark")       # the shipped look (the default)

What it reaches
---------------
- the painter-level controls (they read ``emtk.style.<NAME>`` when they draw);
- an :class:`~emtk.app.ImApp` without a style of its own (a fresh ``Style()`` each frame);
- an existing ``Style`` passed to :func:`apply_theme` (``styles=[app.style]``): an app
  that keeps one must hand it over, or it keeps the old colours;
- a text editor without an assigned palette, ImPlot's automatic colours, and the button
  roles (:data:`emtk.style.BUTTON_ROLES`, picked from the window background).

An application keeps colours of its own (a plot's data colours, a task accent) and listens
with :func:`on_change` for what it must re-read.

Contrast
--------
Both themes keep body text at WCAG AA (4.5:1) on every surface it is drawn on: the window,
popups, fields, tables (both row colours and the header), tabs, menus and title bars.
``tests/test_theme.py`` holds them to it.
"""
from __future__ import annotations

from typing import Callable

from . import style as _style

__all__ = [
    "THEMES",
    "TEXT_SURFACES",
    "apply_theme",
    "current_theme",
    "is_light",
    "on_change",
    "palette_names",
]


def palette_names() -> list[str]:
    """Every colour name of :mod:`emtk.style` a theme sets."""
    return sorted(
        name for name, value in vars(_style).items()
        if name.isupper() and isinstance(value, tuple) and name != "ROLE_ALIASES"
    )


#: The shipped (dark) look: :mod:`emtk.style`'s values as the module defines them.
DARK: dict[str, tuple] = {name: tuple(getattr(_style, name)) for name in palette_names()}

#: A light desktop look. Neutral greys with a faint blue cast for surfaces, white fields
#: and table rows, dark text, the same accent blue made deeper so it reads on white.
LIGHT: dict[str, tuple] = {
    "TEXT": (28, 30, 36),
    "DIM": (92, 96, 106),
    "LINKED": (52, 72, 180),
    "GOLD": (138, 96, 0),
    "TEXT_DISABLED": (128, 130, 138),
    "WINDOW_BG": (243, 244, 246, 255),
    "POPUP_BG": (252, 252, 253, 252),
    "BORDER": (184, 188, 196, 255),
    "FRAME_BG": (255, 255, 255, 255),
    "FRAME_BG_HOVERED": (232, 240, 252, 255),
    "FRAME_BG_ACTIVE": (214, 228, 250, 255),
    "TITLE_BG": (226, 228, 233, 255),
    "TITLE_BG_ACTIVE": (206, 218, 238, 255),
    "MENU_BAR_BG": (234, 236, 240, 255),
    "SCROLLBAR_BG": (236, 238, 241, 255),
    "SCROLLBAR_GRAB": (190, 194, 202, 255),
    "SCROLLBAR_GRAB_HOVERED": (160, 165, 175, 255),
    "SCROLLBAR_GRAB_ACTIVE": (130, 135, 146, 255),
    "CHECK_MARK": (22, 96, 200, 255),
    "SLIDER_GRAB": (52, 120, 210, 255),
    "SLIDER_GRAB_ACTIVE": (22, 96, 200, 255),
    "BUTTON": (224, 228, 234, 255),
    "BUTTON_HOVERED": (204, 216, 234, 255),
    "BUTTON_ACTIVE": (184, 202, 230, 255),
    "HEADER": (214, 226, 244, 255),
    "HEADER_HOVERED": (196, 214, 240, 255),
    "HEADER_ACTIVE": (176, 202, 238, 255),
    "SEPARATOR": (184, 188, 196, 255),
    "SEPARATOR_HOVERED": (90, 150, 230, 220),
    "SEPARATOR_ACTIVE": (22, 96, 200, 255),
    "TAB": (222, 225, 231, 255),
    "TAB_SELECTED": (255, 255, 255, 255),
    "TAB_HOVERED": (204, 216, 234, 255),
    "PLOT_LINES": (96, 100, 110, 255),
    "PLOT_HISTOGRAM": (196, 128, 0, 255),
    "TABLE_HEADER_BG": (228, 231, 236, 255),
    "TABLE_BORDER_STRONG": (176, 181, 190, 255),
    "TABLE_BORDER_LIGHT": (218, 221, 226, 255),
    "TABLE_ROW_BG": (255, 255, 255, 255),
    "TABLE_ROW_BG_ALT": (246, 247, 249, 255),
    "TABLE_HEADER_TEXT": (30, 58, 110),
    "TEXT_LINK": (20, 88, 196, 255),
    "TEXT_SELECTED_BG": (120, 170, 240, 110),
    "DRAG_DROP_TARGET": (220, 140, 0, 230),
    "NAV_CURSOR": (22, 96, 200, 255),
    "MODAL_DIM_BG": (20, 22, 28, 70),
    "HEADER_BG": (206, 218, 238, 255),
    "TRACK_BG": (220, 223, 229, 255),
    "THUMB": (22, 96, 200, 240),
    "THUMB_HELD": (214, 128, 10, 240),
    "ROW_SEL": (176, 202, 238, 255),
    "CHECK_ON": (24, 140, 60),
    "BTN_BG": (224, 228, 234, 255),
    "BTN_HELD": (184, 202, 230, 255),
    "SCROLL_TRACK": (0, 0, 0, 18),
    "SCROLL_THUMB": (150, 155, 166, 200),
    "SCROLL_THUMB_HOT": (106, 114, 130, 230),
    "PLOT_BG": (255, 255, 255, 255),
    "PLOT_FRAME_BG": (0, 0, 0, 8),
    "PLOT_GRID": (0, 0, 0, 26),
    "PLOT_MINOR_GRID": (0, 0, 0, 12),
    "PLOT_TICK_TEXT": (70, 74, 84),
    "PLOT_LABEL_TEXT": (40, 44, 52),
    "PLOT_AXIS_LINE": (150, 155, 165),
    "PLOT_LEGEND_BG": (255, 255, 255, 225),
    "CODE_BG": (236, 238, 242, 255),
    "CODE_INLINE_BG": (0, 0, 0, 16),
    "HEADING_1": (20, 84, 170, 255),
    "HEADING_2": (24, 112, 56, 255),
    "HEADING_3": (150, 92, 0, 255),
    "HEADING_4": (40, 44, 52, 255),
    "TEXT_NOTE": (20, 90, 180, 255),
    "TEXT_TIP": (24, 116, 56, 255),
    "TEXT_WARNING": (150, 90, 0, 255),
    "TEXT_DANGER": (176, 36, 36, 255),
    "TEXT_QUOTE": (80, 88, 104, 255),
    "CARD_BG": (252, 252, 253, 252),
    "WORKSPACE_BG": (228, 230, 234, 255),
    "HOST_BG": (214, 217, 223, 255),
    "WATERMARK": (0, 0, 0, 16),
}

#: Theme name -> ``(palette, frame border size)``.
THEMES: dict[str, tuple[dict[str, tuple], float]] = {
    "dark": (DARK, 0.0),
    "light": (LIGHT, 1.0),
}

#: Surfaces body text (``TEXT``) is drawn on; each must keep it at 4.5:1 in every theme.
TEXT_SURFACES = (
    "WINDOW_BG", "POPUP_BG", "FRAME_BG", "TITLE_BG", "TITLE_BG_ACTIVE", "MENU_BAR_BG",
    "BUTTON", "HEADER", "TAB", "TAB_SELECTED", "TABLE_HEADER_BG", "TABLE_ROW_BG",
    "TABLE_ROW_BG_ALT", "CARD_BG", "CODE_BG", "BTN_BG", "HEADER_BG",
)

_current = "dark"
_listeners: list[Callable[[str], None]] = []


def current_theme() -> str:
    """The name of the theme in effect (``"dark"`` until one is applied)."""
    return _current


def is_light() -> bool:
    """Whether the theme in effect is a light one (judged by its window background)."""
    return not _style.is_dark(_style.WINDOW_BG)


def on_change(callback: Callable[[str], None]) -> Callable[[], None]:
    """Call *callback(name)* after every :func:`apply_theme`; returns the unsubscribe function."""
    _listeners.append(callback)

    def unsubscribe() -> None:
        if callback in _listeners:
            _listeners.remove(callback)

    return unsubscribe


def apply_theme(name: str, styles=()) -> str:
    """Make theme *name* the process's look; returns the name of the theme it replaced.

    Parameters
    ----------
    name : str
        A key of :data:`THEMES` (``"dark"``, ``"light"``).
    styles : iterable of emtk.im_core.Style
        Styles that already exist and should take the theme too (an app that keeps one).
        Their colours and frame border are replaced; their sizes and spacing are kept.

    Raises
    ------
    KeyError
        For a name that is not a theme -- a typo in a settings file must say so.
    """
    global _current
    if name not in THEMES:
        raise KeyError(f"{name!r} is not a theme ({', '.join(sorted(THEMES))})")
    palette, border = THEMES[name]
    missing = set(palette_names()) - set(palette)
    if missing:
        raise KeyError(f"theme {name!r} has no value for {sorted(missing)}")
    previous = _current
    _style.use_palette(palette)
    _style.FRAME_BORDER_SIZE = float(border)
    from .im_core import _default_colors  # noqa: PLC0415

    colours = _default_colors()
    for style in styles:
        if style is None:
            continue
        style.colors.update(colours)
        style.frame_border_size = float(border)
    _reset_implot()
    _current = name
    for callback in list(_listeners):
        callback(name)
    return previous


def _reset_implot() -> None:
    """Put ImPlot back on its automatic colours, which follow the immediate-mode style."""
    import sys  # noqa: PLC0415

    implot = sys.modules.get("emtk.implot")
    gp = getattr(implot, "gp", None) if implot is not None else None
    if gp is not None and getattr(gp, "style", None) is not None:
        implot.style_colors_auto(gp.style)
    implot3d = sys.modules.get("emtk.implot3d")
    if implot3d is not None:
        try:
            implot3d.style_colors_auto()
        except Exception:  # noqa: BLE001 - no 3-D plot context yet: nothing to reset
            pass
