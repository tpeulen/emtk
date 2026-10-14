"""Button roles: a button says what kind of action it is, and the theme colours it.

A panel's one main action (Fit, Run) is ``primary``, a destructive one (Delete, Stop)
``danger``; the rest stay neutral. The colours come from :data:`emtk.style.BUTTON_ROLES`
for the theme the window background is in, so the same declaration reads on a dark and a
light window. These tests hold the shipped colours to WCAG AA, check that the immediate
mode button and a declared ``button_row`` both draw them, and that a disabled primary
does not look like a live one.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import im
from emtk import style as st
from emtk.im_core import Col, Style
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


def _style(dark: bool) -> Style:
    style = Style()
    if not dark:
        im.style_colors_light(style)
    return style


def _colours(painter: RecordingPainter) -> set[tuple]:
    """Every colour any operation was drawn with (fills, triangles, text)."""
    found = set()
    for call in painter.calls:
        for arg in call[1:]:
            if isinstance(arg, tuple) and len(arg) in (3, 4) and all(isinstance(v, int) for v in arg):
                found.add(tuple(arg[:3]))
    return found


def _draw(style: Style, body, painter=None) -> RecordingPainter:
    painter = painter or RecordingPainter()
    with emtk.frame(painter, (0, 0, 400, 200), style=style):
        emtk.begin("w", (0, 0, 400, 200))
        body()
        emtk.end()
    return painter


@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
@pytest.mark.parametrize("role", sorted(st.BUTTON_ROLES))
def test_every_role_keeps_its_text_readable_in_every_state(role, dark):
    background = _style(dark).color(Col.WINDOW_BG)
    colours = st.button_role(role, background)
    for state in ("fill", "hovered", "active"):
        ratio = st.contrast_ratio(getattr(colours, state), colours.text)
        assert ratio >= 4.5, f"{role} {state} text contrast {ratio:.2f} on the {'dark' if dark else 'light'} theme"


def test_the_theme_picks_the_variant():
    assert st.button_role("primary", _style(True).color(Col.WINDOW_BG)) is st.BUTTON_ROLES["primary"].dark
    assert st.button_role("primary", _style(False).color(Col.WINDOW_BG)) is st.BUTTON_ROLES["primary"].light
    assert st.button_role("primary", (15, 15, 15)) != st.button_role("primary", (240, 240, 240))


def test_neutral_aliases_and_typos():
    assert st.button_role(None, (0, 0, 0)) is None
    assert st.button_role("default", (0, 0, 0)) is None
    assert st.button_role("confirm", (0, 0, 0)) is st.BUTTON_ROLES["success"].dark
    assert st.button_role("destructive", (0, 0, 0)) is st.BUTTON_ROLES["danger"].dark
    with pytest.raises(ValueError, match="not a button role"):
        st.button_role("primery", (0, 0, 0))


def test_roles_differ_from_each_other_and_from_the_neutral_button():
    for dark in (True, False):
        style = _style(dark)
        fills = {name: st.button_role(name, style.color(Col.WINDOW_BG)).fill[:3] for name in st.BUTTON_ROLES}
        assert len(set(fills.values())) == len(fills)
        assert tuple(style.color(Col.BUTTON))[:3] not in fills.values()


@pytest.mark.parametrize("dark", [True, False], ids=["dark", "light"])
def test_a_role_button_draws_its_fill_and_text(dark):
    style = _style(dark)
    expected = st.button_role("primary", style.color(Col.WINDOW_BG))
    painter = _draw(style, lambda: im.button("Fit", role="primary"))
    colours = _colours(painter)
    assert expected.fill[:3] in colours
    text = [t[6] for t in painter.texts if t[5] == "Fit"]
    assert text and tuple(text[0])[:3] == expected.text[:3]
    plain = _colours(_draw(style, lambda: im.button("Fit")))
    assert expected.fill[:3] not in plain, "a button without a role stays neutral"


def test_a_disabled_primary_is_visibly_disabled():
    style = _style(True)
    expected = st.button_role("primary", style.color(Col.WINDOW_BG))

    def body():
        im.begin_disabled(True)
        im.button("Fit", role="primary")
        im.end_disabled()

    painter = _draw(style, body)
    assert expected.fill[:3] not in _colours(painter), "disabled must not keep the live fill"
    disabled = expected.disabled_fill(style.color(Col.BUTTON))
    # mostly the neutral button: closer to it than to the live primary fill
    neutral = tuple(style.color(Col.BUTTON))[:3]
    gap_neutral = sum(abs(a - b) for a, b in zip(disabled[:3], neutral))
    gap_live = sum(abs(a - b) for a, b in zip(disabled[:3], expected.fill[:3]))
    assert gap_neutral < gap_live
    text = [t[6] for t in painter.texts if t[5] == "Fit"]
    assert text and len(tuple(text[0])) == 4 and tuple(text[0])[3] < 255, "the label is dimmed"


def test_a_declared_button_row_takes_the_role():
    class Model:
        def __init__(self):
            self.pressed = []

        def run(self):
            self.pressed.append("run")

        def clear(self):
            self.pressed.append("clear")

    spec = {"sections": [{"type": "button_row", "buttons": [
        {"label": "Run", "action": "run", "role": "primary"},
        {"label": "Options", "action": "options"},
        {"label": "Clear", "action": "clear", "role": "danger"},
    ]}]}
    style = _style(False)
    background = style.color(Col.WINDOW_BG)
    model = Model()
    painter = RecordingPainter()
    with emtk.frame(painter, (0, 0, 500, 200), style=style):
        emtk.begin("form", (0, 0, 500, 200))
        draw_form(spec, model, FormState())
        emtk.end()
    colours = _colours(painter)
    assert st.button_role("primary", background).fill[:3] in colours
    assert st.button_role("danger", background).fill[:3] in colours


def test_an_application_can_restyle_a_role():
    mine = st.ThemedButtonRole(dark=st.ButtonRole((10, 20, 120), (12, 24, 140), (8, 16, 100)),
                               light=st.ButtonRole((10, 20, 120), (12, 24, 140), (8, 16, 100)))
    previous = st.set_button_role("primary", mine)
    try:
        assert st.button_role("primary", (0, 0, 0)).fill == (10, 20, 120, 255)
    finally:
        st.set_button_role("primary", previous)
    assert st.BUTTON_ROLES["primary"] is previous


def test_action_button_accent_is_the_success_role():
    style = _style(True)
    expected = st.button_role("success", style.color(Col.WINDOW_BG))
    painter = _draw(style, lambda: im.action_button("Go", "tip", None, accent=True))
    assert expected.fill[:3] in _colours(painter)
