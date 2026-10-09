"""Floating dock captions route authored help without changing controls or layout."""

from __future__ import annotations

import pytest
from emtk import i18n, im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.testing import Driver

DESCRIPTION = "Panel help describes the displayed measurement and its units."
TRANSLATED = "Aide du panneau pour la mesure affichée et ses unités."


class DockApp(ImApp):
    """Render a real floating dock and retain its actual tooltip context."""

    def __init__(self, description=DESCRIPTION):
        self.docks = DockManager(Region("main"))
        self.docks.add_window("panel", "Measurement", self.content,
                              box=(20, 30, 240, 180), tooltip=description)
        self.context = None
        super().__init__(self.gui)
        self.io.wall_clock = False

    def content(self, box):
        """Draw realistic panel content separate from its title hit target."""
        im.text("Measured results")

    def gui(self):
        """Draw the normal manager surface through the immediate-mode app."""
        self.context = im.get_current_context()
        self.docks.draw(self.context.box)

    def target(self, kind="title"):
        """Return an actual header control or body coordinate."""
        x, y, w, _ = self.docks.window("panel").frame
        th = self.docks._title_h
        if kind == "close":
            return x + w - th / 2, y + th / 2
        if kind == "fold":
            return x + th / 2, y + th / 2
        if kind == "body":
            return x + w / 2, y + th + 40
        return x + w / 2, y + th / 2


def hover_and_wait(driver, target):
    """Use normal pointer delivery and the normal delayed tooltip painter."""
    driver.hover(target)
    driver.app.io.now += 1.0
    return driver.frame(2)


def test_floating_title_help_waits_paints_and_leaves_with_stable_owner():
    """Help belongs to the title item and disappears when the pointer leaves."""
    app = DockApp()
    driver = Driver(app, (640, 400))
    driver.frame(2)
    painter = driver.hover(app.target())
    assert app.context.tooltip == DESCRIPTION
    assert app.context.tooltip_owner == app.docks._id("title", "panel")
    assert app.context.box_tooltip is None
    assert DESCRIPTION not in " ".join(painter.strings)
    owner = app.context.tooltip_owner
    painter = hover_and_wait(driver, app.target())
    assert app.context.box_tooltip is not None
    assert DESCRIPTION in " ".join(painter.strings)
    assert app.context.tooltip_owner == owner
    painter = driver.hover(app.target("body"))
    assert app.context.tooltip is None and app.context.box_tooltip is None
    assert DESCRIPTION not in " ".join(painter.strings)


@pytest.mark.parametrize("kind,expected", [
    ("fold", "Collapse or expand this panel."),
    ("close", "Close this panel; reopen it from a dock header context menu."),
])
def test_floating_title_help_preserves_header_button_priority(kind, expected):
    """Fold and close retain their specific help when reached from the title."""
    app = DockApp()
    driver = Driver(app, (640, 400))
    driver.frame(2)
    hover_and_wait(driver, app.target())
    painter = hover_and_wait(driver, app.target(kind))
    assert app.context.tooltip == expected
    assert expected in " ".join(painter.strings)
    assert DESCRIPTION not in " ".join(painter.strings)


def test_floating_title_help_uses_the_active_translation():
    """The authored description uses the shared translation service at draw time."""
    previous = i18n.get_locale()
    i18n.add_translations("dock-help-test", {DESCRIPTION: TRANSLATED})
    try:
        i18n.set_locale("dock-help-test")
        app = DockApp()
        driver = Driver(app, (640, 400))
        driver.frame(2)
        painter = hover_and_wait(driver, app.target())
        assert app.context.tooltip == TRANSLATED
        assert TRANSLATED in " ".join(painter.strings)
    finally:
        i18n.set_locale(previous)


def test_empty_floating_description_does_not_invent_help():
    """Absent metadata leaves the title hover without synthetic panel help."""
    app = DockApp("")
    driver = Driver(app, (320, 400))
    driver.frame(2)
    hover_and_wait(driver, app.target())
    assert app.context.tooltip is None and app.context.box_tooltip is None


@pytest.mark.parametrize("width", [640, 320])
def test_floating_help_preserves_default_and_narrow_geometry(width):
    """Help metadata changes neither header/body rectangles nor idle paint."""
    frames = []
    for description in ("", DESCRIPTION):
        app = DockApp(description)
        driver = Driver(app, (width, 400))
        painter = driver.frame(2)
        panel = app.docks.window("panel")
        frames.append((panel.frame, panel.content, app.target(), painter.calls))
    assert frames[0] == frames[1]
