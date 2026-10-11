"""The ribbon bar: tabs, grouped large/small buttons, tooltips, folding, search and overflow."""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.ribbon import Ribbon, RibbonButton, RibbonGroup, RibbonTab
from emtk.testing import Driver


def _tabs(pressed: list[str]) -> list[RibbonTab]:
    def button(key, label, icon, **kwargs):
        return RibbonButton(key, label, icon, tooltip=f"Open {label}.",
                            on_press=lambda: pressed.append("cb:" + key), **kwargs)

    return [
        RibbonTab("Spectroscopy", [
            RibbonGroup("Decay", [button("decay", "Decay Analysis", "📉", large=True)]),
            RibbonGroup("Correlation", [button("fcs", "FCS", "〰️"), button("pch", "PCH", "📊")]),
            RibbonGroup("Single-Molecule", [
                button("alex", "ALEX Suite", "🚦"), button("burst", "Burst Analysis", "💥"),
                button("trace", "Intensity trace", "📶"), button("browser", "Trace Browser", "📈"),
            ]),
            RibbonGroup("Kinetics", [button("hmm", "Hidden Markov model", "🔀")]),
            RibbonGroup("Imaging", [button("image", "Image Tools", "🔬", large=True)]),
        ]),
        RibbonTab("Tools", [
            RibbonGroup("System", [button("games", "Games", "🎮"),
                                   button("off", "Disabled tool", "🚫", enabled=False)]),
        ]),
    ]


class _App(ImApp):
    def __init__(self, ribbon: Ribbon, width_box=None) -> None:
        self.ribbon = ribbon
        self.item_rects = ribbon.item_rects
        self.returned: list[str] = []
        super().__init__(self.gui)

    def gui(self) -> None:
        width, height = im.get_main_viewport().size
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)
        if im.begin("ribbon host", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            key = self.ribbon.draw((0.0, 0.0, width, self.ribbon.height()))
            if key:
                self.returned.append(key)
        im.end()


def _driver(width=1200, pressed=None):
    pressed = [] if pressed is None else pressed
    ribbon = Ribbon(_tabs(pressed))
    app = _App(ribbon)
    driver = Driver(app, size=(width, 300))
    driver.frame(2)
    return driver, ribbon, app, pressed


def test_tabs_groups_and_buttons_are_drawn_with_icons_and_captions():
    driver, ribbon, _app, _pressed = _driver()
    painter = driver.frame()
    strings = painter.strings
    for text in ("Spectroscopy", "Tools", "Decay", "Correlation", "Single-Molecule", "FCS", "PCH",
                 "ALEX Suite", "Trace Browser", "📉", "📊", "🚦"):
        assert text in strings, text
    assert "Games" not in strings  # another tab's button
    # A large button is as tall as the band; a small one is one row.
    large = driver.rect("ribbon.button.decay")
    small = driver.rect("ribbon.button.fcs")
    assert large[3] > 2.5 * small[3]
    # Four small buttons make two columns of up to three.
    alex, browser = driver.rect("ribbon.button.alex"), driver.rect("ribbon.button.browser")
    assert browser[0] > alex[0] and browser[1] == alex[1]
    assert set(ribbon.group_modes.values()) == {"full"}


def test_a_pressed_button_fires_its_callback_and_returns_its_key():
    driver, _ribbon, app, pressed = _driver()
    driver.click("ribbon.button.pch")
    assert pressed == ["cb:pch"]
    assert app.returned == ["pch"]


def test_a_tab_click_switches_the_band():
    driver, ribbon, _app, pressed = _driver()
    driver.click("ribbon.tab.Tools")
    assert ribbon.current == "Tools"
    painter = driver.frame()
    assert "Games" in painter.strings and "FCS" not in painter.strings
    driver.click("ribbon.button.off")
    assert pressed == []  # a disabled button does not fire
    driver.click("ribbon.button.games")
    assert pressed == ["cb:games"]


def test_a_button_shows_its_tooltip():
    driver, _ribbon, _app, _pressed = _driver()
    driver.hover("ribbon.button.burst")
    for _ in range(40):
        driver.surface.on_pointer_move(*driver._pointer, 0, 0)
        painter = driver.frame()
        if "Open Burst Analysis." in painter.strings:
            break
        import time

        time.sleep(0.02)
    assert "Open Burst Analysis." in painter.strings


def test_narrow_width_collapses_groups_from_the_right_and_keeps_every_button_reachable():
    driver, ribbon, app, pressed = _driver(width=600)
    modes = ribbon.group_modes
    assert modes["Imaging"] != "full" and modes["Decay"] == "full"
    order = ["Decay", "Correlation", "Single-Molecule", "Kinetics", "Imaging"]
    ranks = {"full": 0, "collapsed": 1, "overflow": 2}
    assert [ranks[modes[g]] for g in order] == sorted(ranks[modes[g]] for g in order)
    # The collapsed group opens a menu of its buttons; picking one fires it.
    target = "ribbon.group.Spectroscopy.Kinetics" if modes["Kinetics"] == "collapsed" else "ribbon.overflow"
    driver.click(target)
    driver.frame()
    driver.click("Hidden Markov model")
    driver.frame()
    assert pressed == ["cb:hmm"]
    assert "hmm" in app.returned


def test_very_narrow_width_puts_the_rest_behind_the_overflow_button():
    driver, ribbon, _app, pressed = _driver(width=300)
    assert "overflow" in ribbon.group_modes.values()
    driver.click("ribbon.overflow")
    painter = driver.frame()
    assert "Image Tools" in painter.strings
    driver.click("Image Tools")
    driver.frame()
    assert pressed == ["cb:image"]


def test_search_lists_matching_buttons_of_every_tab():
    driver, ribbon, _app, pressed = _driver()
    ribbon.query = "gam"
    painter = driver.frame(2)
    assert "Games" in painter.strings and "FCS" not in painter.strings
    driver.click("ribbon.button.games")
    assert pressed == ["cb:games"]
    ribbon.query = "zzz"
    assert "No tool matches the search." in driver.frame(2).strings


def test_folding_hides_the_band_and_a_tab_click_shows_it_for_one_pick():
    driver, ribbon, _app, pressed = _driver()
    tall = ribbon.height()
    driver.click("ribbon.fold")
    assert ribbon.folded and ribbon.height() < tall
    assert "FCS" not in driver.frame().strings
    driver.click("ribbon.tab.Spectroscopy")
    assert ribbon.peek and ribbon.height() == tall
    driver.click("ribbon.button.fcs")
    assert pressed == ["cb:fcs"] and not ribbon.peek
    driver.click("ribbon.fold")
    assert not ribbon.folded


def test_menu_rows_with_icons_share_one_label_column():
    from emtk.testing import RecordingPainter
    from emtk.widgets.menus import Popup, MenuItem

    painter = RecordingPainter()
    popup = Popup([MenuItem("With icon", icon="🔬"), MenuItem("Plain")])
    popup.open_at(10.0, 10.0)
    popup.open = True
    popup.draw(painter, 0.0, 0.0, 400.0, 300.0)
    xs = {t[5]: t[0] for t in painter.texts}
    assert "🔬" in xs
    assert xs["With icon"] == xs["Plain"] > xs["🔬"]
