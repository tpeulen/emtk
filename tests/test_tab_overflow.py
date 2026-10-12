"""Tabs that do not fit give way: dock tabs end in an ellipsis, a tab bar wraps onto more rows."""

from __future__ import annotations

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.testing import Driver

LONG = "Channel definition"


class TabsApp(ImApp):
    def __init__(self):
        self.docks = DockManager(Region("main"))
        self.docks.add_window("params", "IRF parameters", self.content, dock="main")
        self.docks.add_window("channels", LONG, self.content, dock="main")
        super().__init__(self.gui)
        self.io.wall_clock = False

    def content(self, box):
        im.text("content")

    def gui(self):
        self.docks.draw(im.get_current_context().box)


def _strip(width):
    app = TabsApp()
    painter = Driver(app, (width, 200)).frame(3)
    return app, painter


def test_a_tab_that_does_not_fit_ends_in_an_ellipsis_and_stays_inside_the_strip():
    app, painter = _strip(230)
    rects = dict(app.docks._tab_rects["main"])
    shown = [t for t in painter.texts if t[5].startswith("Channel") or t[5].startswith("IRF")]
    assert len(shown) == 2
    assert any(t[5].endswith("…") for t in shown)
    for key, (x, _y, w, _h) in rects.items():
        assert x + w <= 230.0
    for entry in shown:
        assert entry[0] + painter.text_width(entry[5]) <= 230.0


def test_a_wide_strip_keeps_every_title_whole():
    _app, painter = _strip(700)
    assert any(t[5] == LONG for t in painter.texts)
    assert any(t[5] == "IRF parameters" for t in painter.texts)


TITLES = ("Spectrum", "Duration", "Photons per burst", "Distance", "Fragments")


def _bar():
    im.begin("bars")
    if im.begin_tab_bar("tabs"):
        for title in TITLES:
            if im.begin_tab_item(title):
                im.text("body " + title)
                im.end_tab_item()
        im.end_tab_bar()
    im.end()


def _label_rects(painter):
    return {t[5]: (t[0], t[1]) for t in painter.texts if t[5] in TITLES}


def test_a_tab_bar_wider_than_its_window_wraps_its_tabs_onto_more_rows_all_inside_it():
    painter = Driver(_bar, size=(300, 240)).frame(4)
    where = _label_rects(painter)
    assert set(where) == set(TITLES)  # every tab is drawn whole
    assert len({y for _x, y in where.values()}) >= 2  # on more than one row
    for title, (x, _y) in where.items():
        assert x + painter.text_width(title) <= 300.0


def test_a_tab_bar_that_fits_stays_on_one_row():
    painter = Driver(_bar, size=(900, 240)).frame(4)
    where = _label_rects(painter)
    assert set(where) == set(TITLES)
    assert len({y for _x, y in where.values()}) == 1


def test_a_wrapped_tab_bar_still_selects_by_click():
    driver = Driver(_bar, size=(300, 240))
    painter = driver.frame(4)
    x, y = _label_rects(painter)["Fragments"]
    driver.click((x + 4.0, y + 4.0))
    texts = [t[5] for t in driver.frame(3).texts]
    assert "body Fragments" in texts
