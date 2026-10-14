"""Themes: every palette name has a value in every theme, text stays readable, the switch reaches
painter-level controls, immediate-mode styles, text editors and plots -- and switching back
restores the shipped look exactly."""
from __future__ import annotations

import pytest

import emtk
from emtk import im
from emtk import style as st
from emtk import theme
from emtk.im_core import Col, Style
from emtk.testing import RecordingPainter


@pytest.fixture(autouse=True)
def _dark_after():
    yield
    theme.apply_theme("dark")


def _colours(painter):
    found = set()
    for call in painter.calls:
        for arg in call[1:]:
            if isinstance(arg, tuple) and len(arg) in (3, 4) and all(isinstance(v, int) for v in arg):
                found.add(tuple(arg[:3]))
    return found


@pytest.mark.parametrize("name", sorted(theme.THEMES))
def test_every_theme_sets_every_palette_name(name):
    palette, _border = theme.THEMES[name]
    assert set(palette) == set(theme.palette_names())
    for value in palette.values():
        st.parse_colour(value)


@pytest.mark.parametrize("name", sorted(theme.THEMES))
def test_text_reads_on_every_surface(name):
    palette, _border = theme.THEMES[name]
    window = palette["WINDOW_BG"][:3]

    def seen(colour):
        colour = st.parse_colour(colour)
        return st.lerp_colour(window, colour, colour[3] / 255.0)[:3] if colour[3] < 255 else colour[:3]

    for surface in theme.TEXT_SURFACES:
        ratio = st.contrast_ratio(seen(palette[surface]), palette["TEXT"])
        assert ratio >= 4.5, f"{name}: TEXT on {surface} {ratio:.2f}"
    for role in ("TABLE_HEADER_TEXT", "TEXT_LINK", "HEADING_1", "HEADING_2", "HEADING_3",
                 "TEXT_NOTE", "TEXT_WARNING", "TEXT_DANGER", "PLOT_LABEL_TEXT", "PLOT_TICK_TEXT"):
        surface = "TABLE_HEADER_BG" if role == "TABLE_HEADER_TEXT" else (
            "PLOT_BG" if role.startswith("PLOT") else "WINDOW_BG")
        ratio = st.contrast_ratio(seen(palette[surface]), palette[role])
        assert ratio >= 4.5, f"{name}: {role} on {surface} {ratio:.2f}"
    assert st.contrast_ratio(seen(palette["WINDOW_BG"]), palette["DIM"]) >= 4.5


def test_light_is_light_and_dark_is_dark():
    assert not st.is_dark(theme.LIGHT["WINDOW_BG"])
    assert st.is_dark(theme.DARK["WINDOW_BG"])
    for surface in ("WINDOW_BG", "FRAME_BG", "TAB", "TABLE_ROW_BG", "MENU_BAR_BG", "PLOT_BG",
                    "POPUP_BG", "TITLE_BG", "CODE_BG", "WORKSPACE_BG"):
        assert not st.is_dark(theme.LIGHT[surface]), surface


def test_the_switch_reaches_the_palette_styles_and_back():
    before = {name: getattr(st, name) for name in theme.palette_names()}
    kept = Style()
    assert theme.apply_theme("light", styles=[kept]) == "dark"
    assert theme.current_theme() == "light" and theme.is_light()
    assert st.WINDOW_BG == theme.LIGHT["WINDOW_BG"]
    assert Style().color(Col.WINDOW_BG)[:3] == theme.LIGHT["WINDOW_BG"][:3]
    assert Style().frame_border_size == 1.0, "a light field needs an edge"
    assert kept.color(Col.TAB)[:3] == theme.LIGHT["TAB"][:3] and kept.frame_border_size == 1.0
    theme.apply_theme("dark", styles=[kept])
    assert {name: getattr(st, name) for name in theme.palette_names()} == before
    assert Style().frame_border_size == 0.0
    assert kept.color(Col.TAB)[:3] == before["TAB"][:3]


def test_listeners_hear_the_switch():
    heard = []
    stop = theme.on_change(heard.append)
    theme.apply_theme("light")
    stop()
    theme.apply_theme("dark")
    assert heard == ["light"]


def test_an_unknown_theme_is_refused():
    with pytest.raises(KeyError, match="not a theme"):
        theme.apply_theme("sepia")


def test_an_app_without_a_style_draws_in_the_new_theme():
    def gui():
        im.begin("w", (0, 0, 300, 200))
        im.text("hello")
        im.button("Go")
        im.end()

    from emtk.app import ImApp

    app = ImApp(gui)
    theme.apply_theme("light")
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 300, 200)
    colours = _colours(painter)
    assert theme.LIGHT["BUTTON"][:3] in colours
    text = [t[6] for t in painter.texts if t[5] == "hello"]
    assert text and tuple(text[0])[:3] == theme.LIGHT["TEXT"][:3]


def test_painter_level_controls_and_plots_follow_the_theme():
    from emtk.widgets.basic import ProgressBar
    from emtk.widgets.plot import Plot

    theme.apply_theme("light")
    painter = RecordingPainter()
    ProgressBar("p", 0.5).draw(painter, 0, 0, 100, 20)
    plot = Plot(0, 30, 200, 120)
    plot.line("data", [0, 1, 2], [0, 1, 0])
    plot.draw(painter)
    colours = _colours(painter)
    assert theme.LIGHT["TRACK_BG"][:3] in colours
    assert theme.LIGHT["PLOT_AXIS_LINE"][:3] in colours


def test_a_text_editor_takes_the_light_token_palette_unless_given_one():
    from emtk.widgets.text_editor import DARK_PALETTE, LIGHT_PALETTE, TextEditor

    editor = TextEditor("x = 1")
    assert editor.palette == DARK_PALETTE
    theme.apply_theme("light")
    assert editor.palette == LIGHT_PALETTE
    editor.palette = DARK_PALETTE
    assert editor.palette == DARK_PALETTE, "an assigned palette is kept"


def test_button_roles_take_the_light_variant():
    theme.apply_theme("light")
    assert st.button_role("primary", Style().color(Col.WINDOW_BG)) is st.BUTTON_ROLES["primary"].light
