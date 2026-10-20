"""Tests for EMTK style sheets: parsing CSS/QSS, palette mapping, metrics, Language.css, and live application."""
from __future__ import annotations

import pytest

import emtk
from emtk import im, theme
from emtk.im_core import Col, Style
from emtk.stylesheet import StyleSheet, apply_stylesheet, parse_color, parse_length, parse_stylesheet
from emtk.widgets.text_editor import Language, shipped_languages


@pytest.fixture(autouse=True)
def _restore_theme():
    yield
    theme.apply_theme("dark")


def test_parse_color():
    assert parse_color("#fff") == (255, 255, 255, 255)
    assert parse_color("#123456") == (18, 52, 86, 255)
    assert parse_color("#12345678") == (18, 52, 86, 120)
    assert parse_color("rgb(10, 20, 30)") == (10, 20, 30, 255)
    assert parse_color("rgba(10, 20, 30, 0.5)") == (10, 20, 30, 128)
    assert parse_color("transparent") == (0, 0, 0, 0)
    with pytest.raises(ValueError):
        parse_color("invalid_color_format_xyz")


def test_parse_length():
    assert parse_length("4px") == 4.0
    assert parse_length("2.5em") == 2.5
    assert parse_length("10") == 10.0


def test_css_language_available():
    lang = Language.css()
    assert lang.name == "CSS"
    assert "color" in lang.keywords
    assert "background-color" in lang.keywords
    shipped = shipped_languages()
    assert "CSS" in shipped


def test_parse_stylesheet_css_rules():
    css = """
    /* Main window and buttons */
    window {
        background-color: #202228;
        color: #e0e4ec;
        border-color: #404452;
        border-radius: 6px;
    }

    button {
        background-color: #324060;
        color: #ffffff;
        border-radius: 4px;
        padding: 5px 10px;
    }

    button:hover {
        background-color: #445880;
    }

    button:active {
        background-color: #243048;
    }

    tab:selected {
        background-color: #384868;
    }
    """
    palette, metrics, style = parse_stylesheet(css)

    assert palette["WINDOW_BG"] == (32, 34, 40, 255)
    assert palette["TEXT"] == (224, 228, 236, 255)
    assert palette["BUTTON"] == (50, 64, 96, 255)
    assert palette["BUTTON_HOVERED"] == (68, 88, 128, 255)
    assert palette["BUTTON_ACTIVE"] == (36, 48, 72, 255)
    assert palette["TAB_SELECTED"] == (56, 72, 104, 255)

    assert metrics["frame_rounding"] == 4.0
    assert metrics["frame_padding"] == (5.0, 10.0)
    assert style.frame_rounding == 4.0
    assert style.color(Col.BUTTON) == (50, 64, 96, 255)


def test_parse_stylesheet_native_rules():
    css = """
    /* EMTK native selectors */
    window {
        background: #1e1e1e;
        color: #dcdcdc;
    }

    button {
        background-color: #2d2d30;
    }

    button:hover {
        background-color: #3e3e42;
    }

    tab {
        background: #252526;
    }

    tab:selected {
        background: #1e1e1e;
    }
    """
    palette, metrics, style = parse_stylesheet(css)

    assert palette["WINDOW_BG"] == (30, 30, 30, 255)
    assert palette["TEXT"] == (220, 220, 220, 255)
    assert palette["BUTTON"] == (45, 45, 48, 255)
    assert palette["BUTTON_HOVERED"] == (62, 62, 66, 255)
    assert palette["TAB"] == (37, 37, 38, 255)
    assert palette["TAB_SELECTED"] == (30, 30, 30, 255)


def test_parse_stylesheet_direct_palette_variables():
    css = """
    :root {
        --window-bg: #102030;
        --button: #204060;
        --plot-bg: #050a10;
        --frame-rounding: 8;
        --frame-border-size: 1.5;
    }
    """
    palette, metrics, style = parse_stylesheet(css)
    assert palette["WINDOW_BG"] == (16, 32, 48, 255)
    assert palette["BUTTON"] == (32, 64, 96, 255)
    assert palette["PLOT_BG"] == (5, 10, 16, 255)
    assert metrics["frame_rounding"] == 8.0
    assert metrics["frame_border_size"] == 1.5


def test_apply_stylesheet_updates_process_and_listeners():
    notifications = []
    stop = theme.on_change(notifications.append)

    css = """
    * {
        background-color: #121820;
        color: #f0f2f5;
    }
    button {
        background-color: #203550;
    }
    """
    kept_style = Style()
    applied_name = apply_stylesheet(css, name="my_custom_theme", styles=[kept_style])

    assert applied_name == "my_custom_theme"
    assert theme.current_theme() == "my_custom_theme"
    assert "my_custom_theme" in theme.THEMES

    assert emtk.style.WINDOW_BG == (18, 24, 32, 255)
    assert emtk.style.BUTTON == (32, 53, 80, 255)

    assert kept_style.color(Col.WINDOW_BG)[:3] == (18, 24, 32)
    assert kept_style.color(Col.BUTTON)[:3] == (32, 53, 80)

    assert "my_custom_theme" in notifications
    stop()


def test_apply_stylesheet_from_file(tmp_path):
    path = tmp_path / "test_theme.css"
    path.write_text("window { background: #223344; color: #ffffff; }")

    name = theme.apply_stylesheet(path)
    assert name == "test_theme"
    assert emtk.style.WINDOW_BG == (34, 51, 68, 255)


def test_tooltip_does_not_override_popup_bg():
    css = """
    menu {
        background-color: #2c2c2c;
    }
    tooltip {
        background-color: rgba(255, 200, 80, 0.9);
        color: #000000;
    }
    """
    palette, metrics, style = parse_stylesheet(css)
    assert palette["POPUP_BG"] == (44, 44, 44, 255)
    assert style.colors[Col.POPUP_BG] == (44, 44, 44, 255)


def test_shipped_native_stylesheets():
    from emtk import styles

    available = styles.available_stylesheets()
    assert "dark" in available
    assert "dark_blue" in available
    assert "light" in available

    name = theme.apply_stylesheet("dark_blue")
    assert name == "dark_blue"
    assert emtk.style.WINDOW_BG == (30, 34, 43, 255)


def test_parse_stylesheet_css_variables():
    css = """
    :root {
        --my-win-bg: #112233;
        --my-pop-bg: #223344;
        --my-rounding: 7px;
    }
    window {
        background-color: var(--my-win-bg);
        border-radius: var(--my-rounding);
    }
    menu {
        background-color: var(--my-pop-bg);
    }
    """
    palette, metrics, style = parse_stylesheet(css)
    assert palette["WINDOW_BG"] == (17, 34, 51, 255)
    assert palette["POPUP_BG"] == (34, 51, 68, 255)
    assert metrics["frame_rounding"] == 7.0
    assert style.frame_rounding == 7.0


def test_apply_stylesheet_updates_all_active_styles_and_menu_popup():
    from emtk.widgets import menus

    # Create a Style instance without passing it explicitly
    standalone_style = Style()
    initial_win_bg = standalone_style.color(Col.WINDOW_BG)

    css = """
    :root {
        --popup-bg: #446688;
        --window-bg: #335577;
        --frame-rounding: 9px;
    }
    window { background: var(--window-bg); }
    menu { background: var(--popup-bg); }
    """
    # Apply stylesheet WITHOUT passing standalone_style
    apply_stylesheet(css, name="test_live_all")

    # 1. Standalone Style must be updated automatically
    assert standalone_style.color(Col.WINDOW_BG) != initial_win_bg
    assert standalone_style.color(Col.WINDOW_BG)[:3] == (51, 85, 119)
    assert standalone_style.color(Col.POPUP_BG)[:3] == (68, 102, 136)
    assert standalone_style.frame_rounding == 9.0

    # 2. menus._OPAQUE_POPUP_BG must reflect the new popup background immediately
    assert menus._OPAQUE_POPUP_BG == (68, 102, 136, 255)
    assert menus._opaque_popup_bg() == (68, 102, 136, 255)


def test_theme_switch_updates_all_active_styles():
    standalone_style = Style()
    theme.apply_theme("light")
    assert standalone_style.color(Col.WINDOW_BG)[:3] == (243, 244, 246)
    theme.apply_theme("dark")
    assert standalone_style.color(Col.WINDOW_BG)[:3] == (15, 15, 15)


