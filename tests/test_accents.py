"""Accents: a dock window's tab and a ribbon group drawn in the colour of their kind of task.

An application colour-codes its panels by task (documentation, wizards, imaging, ...). The
toolkit's part is to draw a given :class:`emtk.style.Accent` the same way everywhere: the
active tab in its fill, an inactive tab muted with a line of the full colour, a stripe under
the tab strip, a floating title bar, section headers inside the window, a ribbon group's
caption and underline. These tests read the recorded painter calls, the way a screenshot
would show them.
"""
from __future__ import annotations

import pytest

from emtk import im
from emtk import style as st
from emtk.accents import header_colours, region_colours
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.ribbon import Ribbon, RibbonButton, RibbonGroup, RibbonTab
from emtk.testing import Driver, RecordingPainter

BLUE = st.Accent("#1F62B5", ink="#8DBBF5")
ORANGE = st.Accent("#B34D00", ink="#FFA65C")


def _fills(painter: RecordingPainter) -> set:
    return {tuple(colour)[:3] for *_box, colour in painter.fills if colour is not None}


def _text_colour(painter: RecordingPainter, string: str) -> tuple:
    for _x, _y, _w, _h, _align, text, colour, _bold in painter.texts:
        if text == string:
            return tuple(colour)[:3]
    raise AssertionError(f"{string!r} was not drawn")


# -- the arithmetic -------------------------------------------------------------- #
def test_parse_colour_reads_hex_and_tuples_and_rejects_typos():
    assert st.parse_colour("#1f62b5") == (31, 98, 181, 255)
    assert st.parse_colour("#1F62B580") == (31, 98, 181, 128)
    assert st.parse_colour((1, 2, 3)) == (1, 2, 3, 255)
    for bad in ("#12345", "blue", (1, 2), (300, 0, 0)):
        with pytest.raises(ValueError):
            st.parse_colour(bad)


def test_contrast_ratio_is_wcag():
    assert st.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert st.contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)
    assert st.is_dark((15, 15, 15)) and not st.is_dark((240, 240, 240))
    assert st.most_readable((240, 240, 240), (255, 255, 255), (20, 20, 20)) == (20, 20, 20, 255)


def test_an_accent_mutes_into_a_ground_and_keeps_its_alpha():
    muted = BLUE.mute((60, 60, 60, 79), 0.5)
    assert muted[3] == 79
    assert 31 < muted[0] < 60 and 60 < muted[2] < 181
    assert BLUE.foreground == (0x8D, 0xBB, 0xF5, 255)
    assert st.Accent("#102030").foreground == (16, 32, 48, 255)


# -- dock windows ------------------------------------------------------------------ #
def _docks():
    docks = DockManager(Region("main"))
    docks.add_window("doc", "Documentation", lambda box: im.text("doc"), dock="main", accent=BLUE)
    docks.add_window("wiz", "Wizards", lambda box: im.text("wiz"), dock="main", accent=ORANGE)
    docks.add_window("plain", "Plain", lambda box: im.text("plain"), dock="main")
    return docks


def _draw(docks, frames=2) -> RecordingPainter:
    app = ImApp(lambda: docks.draw((0.0, 0.0, 800.0, 500.0)))
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, 800.0, 500.0)
    return painter


def test_the_active_tab_is_its_accent_and_an_inactive_one_is_muted_with_a_line_of_it():
    docks = _docks()
    docks.focus("doc")
    painter = _draw(docks)
    fills = _fills(painter)
    assert BLUE.fill[:3] in fills                       # the active tab
    assert _text_colour(painter, "Documentation") == BLUE.text[:3]
    assert ORANGE.fill[:3] in fills                     # the inactive tab's line
    # The inactive tab's own background is neither the theme's tab colour nor the full accent.
    wiz = docks.tab_rect("wiz")
    under = [c for x, y, w, h, c in painter.fills if (x, w) == (wiz[0], wiz[2]) and h > 3.0]
    assert under and tuple(under[0])[:3] not in (ORANGE.fill[:3], tuple(st.TAB)[:3])
    # Its text reads on it.
    text = _text_colour(painter, "Wizards")
    assert st.contrast_ratio(text, under[0]) >= 4.5


def test_the_stripe_under_the_strip_follows_the_window_on_top():
    docks = _docks()
    docks.focus("wiz")
    painter = _draw(docks)
    stripes = [c for x, y, w, h, c in painter.fills if w == 800.0 and h <= 2.5]
    assert stripes and tuple(stripes[-1])[:3] == ORANGE.fill[:3]


def test_a_window_without_an_accent_draws_the_theme_tab():
    docks = _docks()
    docks.focus("plain")
    painter = _draw(docks)
    assert tuple(st.TAB_SELECTED)[:3] in _fills(painter)
    assert _text_colour(painter, "Plain") == tuple(st.TEXT)[:3]


def test_a_floating_window_wears_its_accent_on_the_title_bar():
    docks = DockManager(Region("main"))
    docks.add_window("doc", "Documentation", lambda box: None, box=(50.0, 50.0, 300.0, 200.0),
                     accent=BLUE)
    painter = _draw(docks)
    assert BLUE.fill[:3] in _fills(painter)
    assert _text_colour(painter, "Documentation") == BLUE.text[:3]


def test_header_tint_recolours_section_headers_inside_the_window_only():
    seen = {}

    def content(box):
        seen["inside"] = im.get_style().color(im.Col.HEADER)

    docks = DockManager(Region("main"))
    docks.add_window("doc", "Documentation", content, dock="main", accent=BLUE, header_tint=True)
    app = ImApp(lambda: (docks.draw((0.0, 0.0, 600.0, 400.0)),
                         seen.__setitem__("after", im.get_style().color(im.Col.HEADER))))
    app.draw(RecordingPainter(), 0.0, 0.0, 600.0, 400.0)
    from emtk.im_core import Style

    expected = header_colours(Style(), BLUE)[im.Col.HEADER]
    assert tuple(seen["inside"]) == tuple(expected)
    assert tuple(seen["after"]) == tuple(st.HEADER)      # popped again
    assert expected[3] == tuple(st.HEADER)[3]            # a resting header stays translucent


# -- the ribbon --------------------------------------------------------------------- #
class _RibbonApp(ImApp):
    def __init__(self, ribbon: Ribbon) -> None:
        self.ribbon = ribbon
        self.item_rects = ribbon.item_rects
        super().__init__(self.gui)

    def gui(self) -> None:
        width, _height = im.get_main_viewport().size
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, 300.0), im.Cond.ALWAYS)
        if im.begin("ribbon host", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            self.ribbon.draw((0.0, 0.0, width, self.ribbon.height()))
        im.end()


def test_a_group_caption_and_underline_take_its_accent_and_a_button_of_another_kind_is_marked():
    tabs = [RibbonTab("Tools", [
        RibbonGroup("Help", [RibbonButton("help", "Documentation", "📖", large=True)], accent=BLUE),
        RibbonGroup("Calculators", [RibbonButton("calc", "Calculator", "🧮"),
                                    RibbonButton("wiz", "Wizards", "🪄", accent=ORANGE)]),
    ])]
    driver = Driver(_RibbonApp(Ribbon(tabs)), size=(1000, 300))
    driver.frame(2)
    painter = driver.frame()
    assert _text_colour(painter, "Help") == BLUE.foreground[:3]
    assert _text_colour(painter, "Calculators") == tuple(st.TEXT_DISABLED)[:3]
    assert BLUE.foreground[:3] in _fills(painter)       # the underline
    wiz = driver.rect("ribbon.button.wiz")
    marks = [(x, w) for x, y, w, h, c in painter.fills
             if tuple(c)[:3] == ORANGE.foreground[:3] and abs(x - wiz[0]) < 1.0]
    assert marks and marks[0][1] <= 4.0                  # a thin bar at the button's edge


def test_ambient_colours_reach_a_hosted_app_and_the_app_it_hosts_and_end_with_the_block():
    from emtk.im_core import Style

    seen = []
    grandchild = ImApp(lambda: seen.append(("grandchild", im.get_style().color(im.Col.TAB))))

    def child_gui():
        seen.append(("child", im.get_style().color(im.Col.TAB)))
        child.draw_child(im.get_current_context().p, grandchild, 0.0, 0.0, 50.0, 50.0)

    child = ImApp(child_gui)
    tint = region_colours(Style(), ORANGE)

    def host_gui():
        with st.ambient_colours(tint):
            host.draw_child(im.get_current_context().p, child, 0.0, 0.0, 100.0, 100.0)
        seen.append(("host", im.get_style().color(im.Col.TAB)))

    host = ImApp(host_gui)
    host.draw(RecordingPainter(), 0.0, 0.0, 200.0, 200.0)
    colours = dict(seen)
    assert tuple(colours["child"]) == tuple(colours["grandchild"]) == tuple(tint[im.Col.TAB])
    assert tuple(colours["host"]) == tuple(st.TAB)
    assert child.style is None and st.current_ambient() == {}
    # The tint keeps the theme's text readable on the tabs and title bars it recolours.
    for role in (im.Col.TAB, im.Col.TAB_SELECTED, im.Col.TITLE_BG_ACTIVE):
        assert st.contrast_ratio(tint[role], st.TEXT) >= 4.5


LIGHT_BLUE = st.Accent("#2470CF", ink="#1A5297")
THEMED = st.ThemedAccent(BLUE, LIGHT_BLUE)


def _light_style():
    from emtk.im_core import Style

    style = Style()
    im.style_colors_light(style)
    return style


def test_a_themed_accent_resolves_by_the_window_background():
    from emtk.accents import resolve
    from emtk.im_core import Style

    assert resolve(THEMED, Style()) is BLUE
    assert resolve(THEMED, _light_style()) is LIGHT_BLUE
    assert resolve(None, Style()) is None and resolve(ORANGE, Style()) is ORANGE


@pytest.mark.parametrize("light", [False, True], ids=["dark", "light"])
def test_a_tint_never_reads_worse_than_the_theme_it_tints(light):
    from emtk.im_core import Style

    style = _light_style() if light else Style()
    text = style.color(im.Col.TEXT)
    behind = style.color(im.Col.WINDOW_BG)

    def seen(colour):
        return st.lerp_colour(behind, colour, colour[3] / 255.0) if colour[3] < 255 else colour

    for accent in (BLUE, ORANGE, THEMED):
        for role, colour in region_colours(style, accent).items():
            own = st.contrast_ratio(seen(st.parse_colour(style.color(role))), text)
            assert st.contrast_ratio(seen(colour), text) >= min(4.5, own) - 1e-6, (role, accent)


def test_a_tool_list_marks_items_writes_captions_and_tints_headers():
    from emtk import accents

    seen = {}

    def gui():
        im.begin("list")
        accents.caption("Imaging", THEMED)
        with accents.headers(ORANGE):
            seen["header"] = im.get_style().color(im.Col.BUTTON)
            im.collapsing_header("Tools")
        seen["after"] = im.get_style().color(im.Col.BUTTON)
        im.selectable("Image Tools")
        accents.mark_item(THEMED)
        im.end()

    app = ImApp(gui)
    painter = RecordingPainter()
    app.draw(painter, 0.0, 0.0, 400.0, 300.0)
    assert _text_colour(painter, "Imaging") == BLUE.foreground[:3]
    assert tuple(seen["after"]) == tuple(st.BUTTON)
    assert tuple(seen["header"]) != tuple(st.BUTTON)
    bars = [(x, w) for x, y, w, h, c in painter.fills if tuple(c)[:3] == BLUE.foreground[:3]]
    assert bars and bars[0][1] == pytest.approx(accents.MARK_WIDTH)
