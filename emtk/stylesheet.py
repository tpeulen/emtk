"""EMTK Style Sheets: CSS and QSS parser, theme generator, and live styling engine.

Provides parsing of CSS and Qt Style Sheet (QSS) rules into EMTK palettes and
:class:`~emtk.im_core.Style` geometry metrics, with live application across the process.
"""
from __future__ import annotations

import os
import pathlib
import re
from typing import Any

from . import style as _style
from . import theme as _theme
from .im_core import Col, Style

__all__ = [
    "StyleSheet",
    "apply_stylesheet",
    "parse_color",
    "parse_length",
    "parse_stylesheet",
]

_NAMED_COLORS: dict[str, tuple[int, int, int, int]] = {
    "white": (255, 255, 255, 255),
    "black": (0, 0, 0, 255),
    "transparent": (0, 0, 0, 0),
    "none": (0, 0, 0, 0),
    "red": (230, 40, 40, 255),
    "green": (40, 200, 80, 255),
    "blue": (40, 120, 240, 255),
    "yellow": (240, 200, 40, 255),
    "gray": (128, 128, 128, 255),
    "grey": (128, 128, 128, 255),
    "lightgray": (211, 211, 211, 255),
    "darkgray": (64, 64, 64, 255),
}


def parse_color(value: str) -> tuple[int, int, int, int]:
    """Parse a CSS/QSS color specification into an RGBA 4-tuple of 0-255 ints.

    Supports:
    - ``#rgb``, ``#rrggbb``, ``#rrggbbaa``
    - ``rgb(r, g, b)``, ``rgba(r, g, b, a)`` (with integers 0-255 or alpha 0.0-1.0)
    - Named colours (``white``, ``black``, ``transparent``, etc.)
    """
    v = value.strip().lower()
    if v in _NAMED_COLORS:
        return _NAMED_COLORS[v]

    if v.startswith("#"):
        hex_digits = v[1:]
        if len(hex_digits) == 3:
            hex_digits = "".join(c * 2 for c in hex_digits) + "ff"
        elif len(hex_digits) == 4:
            hex_digits = "".join(c * 2 for c in hex_digits)
        elif len(hex_digits) == 6:
            hex_digits += "ff"
        if len(hex_digits) == 8 and re.fullmatch(r"[0-9a-f]{8}", hex_digits):
            return tuple(int(hex_digits[i : i + 2], 16) for i in (0, 2, 4, 6))

    match = re.fullmatch(r"rgba?\s*\(([^)]+)\)", v)
    if match:
        raw_parts = [p.strip() for p in match[1].split(",")]
        if len(raw_parts) in (3, 4):
            try:
                parts = [float(p.rstrip("%")) if "%" in p else float(p) for p in raw_parts]
                r, g, b = (max(0, min(255, round(c))) for c in parts[:3])
                if len(parts) == 4:
                    a_val = parts[3]
                    a = max(0, min(255, round(a_val * 255 if a_val <= 1.0 else a_val)))
                else:
                    a = 255
                return (r, g, b, a)
            except ValueError:
                pass

    raise ValueError(f"Unsupported color format: {value!r}")


def parse_length(value: str) -> float:
    """Parse a CSS length (e.g. ``"4px"``, ``"2.5"``, ``"1em"``) into a float pixel value."""
    v = value.strip().lower()
    for suffix in ("px", "pt", "em", "rem"):
        if v.endswith(suffix):
            v = v[: -len(suffix)].strip()
            break
    return float(v)


def parse_tuple2(value: str) -> tuple[float, float]:
    """Parse 1 or 2 lengths (e.g. ``"4px 8px"`` or ``"4px"``) into a 2-tuple of floats."""
    parts = value.strip().split()
    if len(parts) == 1:
        f = parse_length(parts[0])
        return (f, f)
    if len(parts) >= 2:
        return (parse_length(parts[0]), parse_length(parts[1]))
    return (0.0, 0.0)


# Maps (selector_pattern, property_name) -> list of palette keys or im.Col roles
_PALETTE_MAP: dict[str, dict[str, list[str]]] = {
    "root": {
        "background": ["WINDOW_BG"],
        "background-color": ["WINDOW_BG"],
        "color": ["TEXT"],
        "border-color": ["BORDER"],
    },
    "window": {
        "background": ["WINDOW_BG"],
        "background-color": ["WINDOW_BG"],
        "color": ["TEXT"],
        "border-color": ["BORDER"],
    },
    "widget": {
        "background": ["FRAME_BG"],
        "background-color": ["FRAME_BG"],
        "border-color": ["BORDER"],
    },
    "disabled": {
        "color": ["TEXT_DISABLED"],
    },
    "button": {
        "background": ["BUTTON", "BTN_BG"],
        "background-color": ["BUTTON", "BTN_BG"],
        "border-color": ["BORDER"],
    },
    "button_hover": {
        "background": ["BUTTON_HOVERED"],
        "background-color": ["BUTTON_HOVERED"],
    },
    "button_active": {
        "background": ["BUTTON_ACTIVE", "BTN_HELD"],
        "background-color": ["BUTTON_ACTIVE", "BTN_HELD"],
    },
    "tab": {
        "background": ["TAB"],
        "background-color": ["TAB"],
    },
    "tab_selected": {
        "background": ["TAB_SELECTED"],
        "background-color": ["TAB_SELECTED"],
    },
    "tab_hover": {
        "background": ["TAB_HOVERED", "HEADER_HOVERED"],
        "background-color": ["TAB_HOVERED", "HEADER_HOVERED"],
    },
    "input": {
        "background": ["FRAME_BG"],
        "background-color": ["FRAME_BG"],
        "border-color": ["BORDER"],
        "selection-background-color": ["TEXT_SELECTED_BG"],
    },
    "input_hover": {
        "background": ["FRAME_BG_HOVERED"],
        "background-color": ["FRAME_BG_HOVERED"],
    },
    "input_active": {
        "background": ["FRAME_BG_ACTIVE"],
        "background-color": ["FRAME_BG_ACTIVE"],
    },
    "menu": {
        "background": ["POPUP_BG"],
        "background-color": ["POPUP_BG"],
        "border-color": ["BORDER"],
        "color": ["TEXT"],
    },
    "menu_item": {
        "color": ["TEXT"],
        "background": ["POPUP_BG"],
        "background-color": ["POPUP_BG"],
    },
    "menu_item_hover": {
        "background": ["HEADER_HOVERED"],
        "background-color": ["HEADER_HOVERED"],
    },
    "menu_item_selected": {
        "background": ["HEADER_ACTIVE"],
        "background-color": ["HEADER_ACTIVE"],
    },
    "menubar": {
        "background": ["MENU_BAR_BG"],
        "background-color": ["MENU_BAR_BG"],
        "color": ["TEXT"],
    },
    "header": {
        "background": ["HEADER", "TABLE_HEADER_BG"],
        "background-color": ["HEADER", "TABLE_HEADER_BG"],
        "color": ["TABLE_HEADER_TEXT", "TEXT"],
    },
    "header_hover": {
        "background": ["HEADER_HOVERED"],
        "background-color": ["HEADER_HOVERED"],
    },
    "header_active": {
        "background": ["HEADER_ACTIVE"],
        "background-color": ["HEADER_ACTIVE"],
    },
    "table": {
        "background": ["TABLE_ROW_BG"],
        "background-color": ["TABLE_ROW_BG"],
        "alternate-background-color": ["TABLE_ROW_BG_ALT"],
        "color": ["TEXT"],
        "border-color": ["TABLE_BORDER_LIGHT"],
        "grid-color": ["TABLE_BORDER_LIGHT"],
    },
    "table_selected": {
        "background": ["ROW_SEL", "HEADER_ACTIVE"],
        "background-color": ["ROW_SEL", "HEADER_ACTIVE"],
    },
    "table_hover": {
        "background": ["HEADER_HOVERED"],
        "background-color": ["HEADER_HOVERED"],
    },
    "scrollbar": {
        "background": ["SCROLLBAR_BG", "SCROLL_TRACK"],
        "background-color": ["SCROLLBAR_BG", "SCROLL_TRACK"],
    },
    "scrollbar_handle": {
        "background": ["SCROLLBAR_GRAB", "SCROLL_THUMB"],
        "background-color": ["SCROLLBAR_GRAB", "SCROLL_THUMB"],
    },
    "scrollbar_handle_hover": {
        "background": ["SCROLLBAR_GRAB_HOVERED", "SCROLL_THUMB_HOT"],
        "background-color": ["SCROLLBAR_GRAB_HOVERED", "SCROLL_THUMB_HOT"],
    },
    "scrollbar_handle_active": {
        "background": ["SCROLLBAR_GRAB_ACTIVE"],
        "background-color": ["SCROLLBAR_GRAB_ACTIVE"],
    },
    "checkbox": {
        "color": ["CHECK_MARK", "CHECK_ON"],
        "background": ["CHECK_MARK", "CHECK_ON"],
        "background-color": ["CHECK_MARK", "CHECK_ON"],
    },
    "slider": {
        "background": ["TRACK_BG"],
        "background-color": ["TRACK_BG"],
        "color": ["SLIDER_GRAB", "THUMB"],
    },
    "slider_handle": {
        "background": ["SLIDER_GRAB", "THUMB"],
        "background-color": ["SLIDER_GRAB", "THUMB"],
    },
    "slider_handle_active": {
        "background": ["SLIDER_GRAB_ACTIVE", "THUMB_HELD"],
        "background-color": ["SLIDER_GRAB_ACTIVE", "THUMB_HELD"],
    },
    "dock_title": {
        "background": ["TITLE_BG"],
        "background-color": ["TITLE_BG"],
    },
    "dock_title_active": {
        "background": ["TITLE_BG_ACTIVE"],
        "background-color": ["TITLE_BG_ACTIVE"],
    },
    "plot": {
        "background": ["PLOT_BG"],
        "background-color": ["PLOT_BG"],
        "border-color": ["PLOT_GRID"],
        "grid-color": ["PLOT_GRID"],
        "color": ["PLOT_LABEL_TEXT", "PLOT_TICK_TEXT"],
    },
}

_COL_ROLE_MAP: dict[str, dict[str, int]] = {
    "root": {"background": Col.WINDOW_BG, "background-color": Col.WINDOW_BG, "color": Col.TEXT, "border-color": Col.BORDER},
    "window": {"background": Col.WINDOW_BG, "background-color": Col.WINDOW_BG, "color": Col.TEXT, "border-color": Col.BORDER},
    "disabled": {"color": Col.TEXT_DISABLED},
    "button": {"background": Col.BUTTON, "background-color": Col.BUTTON},
    "button_hover": {"background": Col.BUTTON_HOVERED, "background-color": Col.BUTTON_HOVERED},
    "button_active": {"background": Col.BUTTON_ACTIVE, "background-color": Col.BUTTON_ACTIVE},
    "tab": {"background": Col.TAB, "background-color": Col.TAB},
    "tab_selected": {"background": Col.TAB_SELECTED, "background-color": Col.TAB_SELECTED},
    "input": {"background": Col.FRAME_BG, "background-color": Col.FRAME_BG, "border-color": Col.BORDER},
    "input_hover": {"background": Col.FRAME_BG_HOVERED, "background-color": Col.FRAME_BG_HOVERED},
    "input_active": {"background": Col.FRAME_BG_ACTIVE, "background-color": Col.FRAME_BG_ACTIVE},
    "menu": {"background": Col.POPUP_BG, "background-color": Col.POPUP_BG, "color": Col.TEXT},
    "menu_item": {"color": Col.TEXT, "background": Col.POPUP_BG, "background-color": Col.POPUP_BG},
    "menu_item_hover": {"background": Col.HEADER_HOVERED, "background-color": Col.HEADER_HOVERED},
    "menu_item_selected": {"background": Col.HEADER_ACTIVE, "background-color": Col.HEADER_ACTIVE},
    "menubar": {"background": Col.MENU_BAR_BG, "background-color": Col.MENU_BAR_BG, "color": Col.TEXT},
    "header": {"background": Col.HEADER, "background-color": Col.HEADER},
    "header_hover": {"background": Col.HEADER_HOVERED, "background-color": Col.HEADER_HOVERED},
    "header_active": {"background": Col.HEADER_ACTIVE, "background-color": Col.HEADER_ACTIVE},
    "scrollbar": {"background": Col.SCROLLBAR_BG, "background-color": Col.SCROLLBAR_BG},
    "scrollbar_handle": {"background": Col.SCROLLBAR_GRAB, "background-color": Col.SCROLLBAR_GRAB},
    "checkbox": {"background": Col.CHECK_MARK, "background-color": Col.CHECK_MARK, "color": Col.CHECK_MARK},
    "slider_handle": {"background": Col.SLIDER_GRAB, "background-color": Col.SLIDER_GRAB},
    "slider_handle_active": {"background": Col.SLIDER_GRAB_ACTIVE, "background-color": Col.SLIDER_GRAB_ACTIVE},
    "dock_title": {"background": Col.TITLE_BG, "background-color": Col.TITLE_BG},
    "dock_title_active": {"background": Col.TITLE_BG_ACTIVE, "background-color": Col.TITLE_BG_ACTIVE},
}


def _calendar_rules(selectors, prop: str, value: str, metrics: dict) -> None:
    """Collect the colours of ``calendar::*`` rules into ``metrics["calendar"]``.

    The calendar has parts no palette role names (the selected day, today,
    weekends, the other months' days), so its rules are not palette entries: the
    selectors are read by :func:`emtk.widgets.calendar.stylesheet_part` and the
    colours handed to :func:`emtk.widgets.calendar.use_stylesheet` when the sheet
    is applied.
    """
    from .widgets import calendar as _calendar  # noqa: PLC0415

    for sel in selectors:
        part = _calendar.stylesheet_part(sel, prop)
        if part is None:
            continue
        try:
            metrics.setdefault("calendar", {})[part] = parse_color(value)
        except ValueError:
            pass


def _classify_selector(sel: str) -> str | None:
    """Map a CSS selector string to an internal EMTK category key."""
    s = sel.strip()
    if s in ("*", ":root", "html", "body"):
        return "root"
    if s in ("window", "Window"):
        return "window"
    if s in ("widget", "Widget", "frame", "Frame"):
        return "widget"
    if s in ("*:disabled", "disabled", ":disabled"):
        return "disabled"
    if s in ("button", "Button"):
        return "button"
    if s in ("button:hover", "button:hovered", ":hover"):
        return "button_hover"
    if s in ("button:active", "button:pressed"):
        return "button_active"
    if s in ("tab", "Tab"):
        return "tab"
    if s in ("tab:selected", "tab:active"):
        return "tab_selected"
    if s in ("tab:hover", "tab:hovered"):
        return "tab_hover"
    if s in ("input", "field", "text", "text_input", "editor", "text_editor"):
        return "input"
    if s in ("input:hover", "field:hover"):
        return "input_hover"
    if s in ("input:focus", "input:active", "field:focus", "field:active"):
        return "input_active"
    if s in ("menu", "popup", "Menu", "Popup"):
        return "menu"
    if s in ("menu::item", "menu:item", "menu_item", "MenuItem"):
        return "menu_item"
    if s in ("menu::item:hover", "menu:item:hover", "menu_item:hover"):
        return "menu_item_hover"
    if s in ("menu::item:selected", "menu:item:selected", "menu:hover", "menu_item:selected"):
        return "menu_item_selected"
    if s in ("menubar", "menu_bar", "MenuBar"):
        return "menubar"
    if s in ("header", "table_header"):
        return "header"
    if s in ("header:hover", "table_header:hover"):
        return "header_hover"
    if s in ("header:active", "table_header:active"):
        return "header_active"
    if s in ("table", "data_table", "tree"):
        return "table"
    if s in ("table:selected", "table::item:selected", "table:item:selected"):
        return "table_selected"
    if s in ("table:hover", "table::item:hover", "table:item:hover"):
        return "table_hover"
    if s in ("scrollbar", "scroll"):
        return "scrollbar"
    if s in ("scrollbar::handle", "scrollbar:handle", "scrollbar:thumb", "scroll_thumb"):
        return "scrollbar_handle"
    if s in ("scrollbar::handle:hover", "scrollbar:handle:hover", "scroll_thumb:hover"):
        return "scrollbar_handle_hover"
    if s in ("scrollbar::handle:active", "scrollbar:handle:active", "scroll_thumb:active"):
        return "scrollbar_handle_active"
    if s in ("checkbox", "check"):
        return "checkbox"
    if s in ("slider",):
        return "slider"
    if s in ("slider::handle", "slider:handle", "slider_thumb"):
        return "slider_handle"
    if s in ("slider::handle:active", "slider:handle:active", "slider_thumb:active"):
        return "slider_handle_active"
    if s in ("dock", "dock:title", "dock_title"):
        return "dock_title"
    if s in ("dock:title:active", "dock_title:active"):
        return "dock_title_active"
    if s in ("plot", "Plot", "implot"):
        return "plot"
    return None


class StyleSheet:
    """Represents a parsed stylesheet with its palette, style metrics, and ImGui Style."""

    def __init__(
        self,
        palette: dict[str, tuple[int, int, int, int]],
        metrics: dict[str, Any],
        style: Style,
        source: str = "",
        name: str = "custom",
    ):
        self.palette = palette
        self.metrics = metrics
        self.style = style
        self.source = source
        self.name = name

    def apply(self, styles=()) -> str:
        """Apply this stylesheet globally to EMTK and existing styles."""
        return apply_stylesheet(self.source, name=self.name, styles=styles)


def parse_stylesheet(
    source: str,
    base_theme: str = "dark",
) -> tuple[dict[str, tuple[int, int, int, int]], dict[str, Any], Style]:
    """Parse a CSS or QSS stylesheet into an EMTK palette dict, metrics dict, and Style object.

    Parameters
    ----------
    source : str
        The CSS/QSS stylesheet content.
    base_theme : str
        The theme to base unspecified colours and metrics on (``"dark"`` or ``"light"``).

    Returns
    -------
    tuple of (palette_dict, metrics_dict, Style)
    """
    valid_names = set(_theme.palette_names())
    base_palette, base_border = _theme.THEMES.get(base_theme, _theme.THEMES["dark"])
    palette: dict[str, tuple[int, int, int, int]] = dict(base_palette)
    metrics: dict[str, Any] = {"frame_border_size": float(base_border)}
    style = Style()

    # Strip multi-line comments
    clean_source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)

    # Find blocks: selectors { declarations }
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", clean_source)

    # Pre-collect CSS variables
    css_vars: dict[str, str] = {}
    for _sel_txt, b_body in blocks:
        for decl in b_body.split(";"):
            if ":" in decl:
                p_name, p_val = (part.strip() for part in decl.split(":", 1))
                if p_name.startswith("--"):
                    css_vars[p_name.lower()] = p_val
                    css_vars[p_name.lower().lstrip("-")] = p_val

    def resolve_val(v_str: str) -> str:
        for _ in range(5):
            if "var(" not in v_str:
                break

            def _repl(m: re.Match) -> str:
                vname = m.group(1).strip().lower()
                fb = m.group(2).strip() if m.group(2) else ""
                norm = vname.upper().replace("-", "_").lstrip("_")
                if norm in palette:
                    r, g, b, a = palette[norm]
                    return f"rgba({r},{g},{b},{a})"
                clean = vname.lstrip("-")
                if clean in css_vars:
                    return css_vars[clean]
                if vname in css_vars:
                    return css_vars[vname]
                return fb or vname

            v_str = re.sub(r"var\(\s*([^,\)]+)(?:\s*,\s*([^)]+))?\s*\)", _repl, v_str)
        return v_str

    for selectors_text, body in blocks:
        selectors = [s.strip() for s in selectors_text.split(",") if s.strip()]
        declarations = [d.strip() for d in body.split(";") if ":" in d]

        for decl in declarations:
            prop, raw_val = (part.strip() for part in decl.split(":", 1))
            val = resolve_val(raw_val)
            prop_lower = prop.lower()

            # Check direct palette property variable (e.g. `--window-bg: #242424` or `WINDOW_BG: #242424`)
            norm_prop = prop.upper().replace("-", "_").lstrip("_")
            if norm_prop in valid_names:
                try:
                    c = parse_color(val)
                    palette[norm_prop] = c
                except ValueError:
                    pass
                continue

            # Check metrics
            prop_clean = prop_lower.lstrip("-")
            if prop_clean in ("frame-rounding", "border-radius", "rounding"):
                try:
                    r = parse_length(val)
                    metrics["frame_rounding"] = r
                    style.frame_rounding = r
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("frame-border-size", "border-width", "border-size"):
                try:
                    b = parse_length(val)
                    metrics["frame_border_size"] = b
                    style.frame_border_size = b
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("window-border-size", "window-border"):
                try:
                    w = parse_length(val)
                    metrics["window_border_size"] = w
                    style.window_border_size = w
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("window-shadow-size", "window-shadow"):
                try:
                    s = parse_length(val)
                    metrics["window_shadow_size"] = s
                    style.window_shadow_size = s
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("padding", "frame-padding"):
                try:
                    pad = parse_tuple2(val)
                    metrics["frame_padding"] = pad
                    style.frame_padding = pad
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("spacing", "item-spacing"):
                try:
                    sp = parse_tuple2(val)
                    metrics["item_spacing"] = sp
                    style.item_spacing = sp
                except (ValueError, TypeError):
                    pass
            elif prop_clean in ("opacity", "disabled-alpha"):
                try:
                    a = float(val)
                    metrics["disabled_alpha"] = a
                    style.disabled_alpha = a
                except (ValueError, TypeError):
                    pass

            # `calendar::day:selected` and the other calendar parts colour the calendar alone
            _calendar_rules(selectors, prop_lower, val, metrics)

            # Classify selector and apply color rules
            for sel in selectors:
                cat = _classify_selector(sel)
                if cat is None:
                    continue

                # Palette mapping
                if cat in _PALETTE_MAP and prop_lower in _PALETTE_MAP[cat]:
                    try:
                        c = parse_color(val)
                        for target in _PALETTE_MAP[cat][prop_lower]:
                            if target in valid_names:
                                palette[target] = c
                    except ValueError:
                        pass

                # Style colors mapping (ImGui Col)
                if cat in _COL_ROLE_MAP and prop_lower in _COL_ROLE_MAP[cat]:
                    try:
                        c = parse_color(val)
                        col_enum = _COL_ROLE_MAP[cat][prop_lower]
                        style.colors[col_enum] = c
                    except ValueError:
                        pass

    # Ensure all style.colors follow the resolved palette
    for col_enum, pal_name in [
        (Col.TEXT, "TEXT"),
        (Col.TEXT_DISABLED, "TEXT_DISABLED"),
        (Col.WINDOW_BG, "WINDOW_BG"),
        (Col.POPUP_BG, "POPUP_BG"),
        (Col.BORDER, "BORDER"),
        (Col.FRAME_BG, "FRAME_BG"),
        (Col.FRAME_BG_HOVERED, "FRAME_BG_HOVERED"),
        (Col.FRAME_BG_ACTIVE, "FRAME_BG_ACTIVE"),
        (Col.TITLE_BG, "TITLE_BG"),
        (Col.TITLE_BG_ACTIVE, "TITLE_BG_ACTIVE"),
        (Col.MENU_BAR_BG, "MENU_BAR_BG"),
        (Col.BUTTON, "BUTTON"),
        (Col.BUTTON_HOVERED, "BUTTON_HOVERED"),
        (Col.BUTTON_ACTIVE, "BUTTON_ACTIVE"),
        (Col.HEADER, "HEADER"),
        (Col.HEADER_HOVERED, "HEADER_HOVERED"),
        (Col.HEADER_ACTIVE, "HEADER_ACTIVE"),
        (Col.TAB, "TAB"),
        (Col.TAB_SELECTED, "TAB_SELECTED"),
        (Col.SCROLLBAR_BG, "SCROLLBAR_BG"),
        (Col.SCROLLBAR_GRAB, "SCROLLBAR_GRAB"),
        (Col.CHECK_MARK, "CHECK_MARK"),
        (Col.SLIDER_GRAB, "SLIDER_GRAB"),
        (Col.SLIDER_GRAB_ACTIVE, "SLIDER_GRAB_ACTIVE"),
        (Col.PLOT_LINES, "PLOT_LINES"),
        (Col.PLOT_HISTOGRAM, "PLOT_HISTOGRAM"),
    ]:
        if col_enum not in style.colors and pal_name in palette:
            style.colors[col_enum] = palette[pal_name]

    return palette, metrics, style


def apply_stylesheet(
    source_or_path: str | pathlib.Path,
    name: str = "custom",
    styles: Any = (),
) -> str:
    """Parse and apply a CSS or QSS stylesheet to EMTK across the entire process.

    Parameters
    ----------
    source_or_path : str or pathlib.Path
        The stylesheet string or a path to a ``.css`` or ``.qss`` file.
    name : str
        Theme name to register and apply.
    styles : iterable of emtk.im_core.Style, optional
        Any existing Style instances that should take the new colours and metrics.

    Returns
    -------
    str
        The name of the theme that was applied.
    """
    text = ""
    if isinstance(source_or_path, (str, pathlib.Path)) and os.path.isfile(str(source_or_path)):
        p = pathlib.Path(source_or_path)
        name = p.stem
        text = p.read_text(encoding="utf-8")
    elif isinstance(source_or_path, str) and "{" not in source_or_path and ";" not in source_or_path:
        from . import styles as _styles
        shipped = _styles.get_stylesheet_path(source_or_path)
        if shipped is not None:
            name = shipped.stem
            text = shipped.read_text(encoding="utf-8")
        else:
            text = str(source_or_path)
    else:
        text = str(source_or_path)

    base = "light" if ("light" in name.lower() or _theme.is_light()) else "dark"
    palette, metrics, style_obj = parse_stylesheet(text, base_theme=base)

    # Register in themes
    border = float(metrics.get("frame_border_size", 0.0))
    if name not in ("dark", "light"):
        _theme.THEMES[name] = (palette, border)

    # Use palette
    _style.use_palette(palette)
    _style.FRAME_BORDER_SIZE = border
    # The calendar's own colours belong to this sheet's theme (none: the style colours again).
    from .widgets import calendar as _calendar  # noqa: PLC0415

    _calendar.use_stylesheet(name, metrics.get("calendar"))

    # Update styles passed in and all active styles across the process
    from .im_core import _ACTIVE_STYLES

    all_styles = set(styles or ()) | set(_ACTIVE_STYLES)
    for st in all_styles:
        if st is not None:
            st.colors.update(style_obj.colors)
            st.frame_border_size = border
            if "frame_rounding" in metrics:
                st.frame_rounding = metrics["frame_rounding"]
            if "frame_padding" in metrics:
                st.frame_padding = metrics["frame_padding"]
            if "item_spacing" in metrics:
                st.item_spacing = metrics["item_spacing"]
            if "window_border_size" in metrics:
                st.window_border_size = metrics["window_border_size"]
            if "window_shadow_size" in metrics:
                st.window_shadow_size = metrics["window_shadow_size"]
            if "disabled_alpha" in metrics:
                st.disabled_alpha = metrics["disabled_alpha"]

    # Reset implot automatic colours
    _theme._reset_implot()

    _theme._current = name
    for callback in list(_theme._listeners):
        try:
            callback(name)
        except Exception:
            pass

    return name
