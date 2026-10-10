"""``im.toggle_button``: a checkbox's on/off contract drawn as a button."""

from __future__ import annotations

from emtk import im, style
from emtk.testing import Driver, render


def _pixel(painter, x, y):
    i = (y * painter.width + x) * 4
    return tuple(painter.px[i:i + 3])


def test_on_and_off_differ_only_in_the_button_fill():
    """On uses the active button colour, off the normal one; same box either way."""
    rects = {}

    def gui_for(value):
        def gui():
            im.begin("w", (0, 0, 200, 80))
            im.toggle_button("Sound##t", value)
            rects[value] = im.get_item_rect()
            im.end()
        return gui

    off = render(gui_for(False), (0, 0, 200, 80))
    on = render(gui_for(True), (0, 0, 200, 80))
    assert rects[False] == rects[True]
    x, y, w, h = rects[True]
    probe = (int(x + 2), int(y + h / 2))
    assert _pixel(on, *probe) == style.BUTTON_ACTIVE[:3]
    assert _pixel(off, *probe) != _pixel(on, *probe)


def test_click_flips_value_and_reports_change():
    """A completed click returns ``(True, not value)``; an idle frame ``(False, value)``."""
    state = {"value": False, "changes": 0}

    class App:
        item_rects = {}

    def gui():
        im.begin("w", (0, 0, 200, 80))
        changed, state["value"] = im.toggle_button("Sound##t", state["value"])
        App.item_rects["t"] = im.get_item_rect()
        state["changes"] += changed
        im.end()

    from emtk.app import ImApp

    app = ImApp(gui)
    app.item_rects = App.item_rects
    driver = Driver(app, (200, 80))
    driver.draw(2)
    assert state == {"value": False, "changes": 0}
    driver.click("t")
    driver.draw(1)
    assert state["value"] is True and state["changes"] == 1
    driver.click("t")
    driver.draw(1)
    assert state["value"] is False and state["changes"] == 2
