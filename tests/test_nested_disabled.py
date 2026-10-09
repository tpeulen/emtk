"""Nested disabled scopes cannot re-enable parent-disabled widget actions."""

import pytest
from emtk import im
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_sections

HELP = "Unavailable while its parent is disabled."


class NestedApp(ImApp):
    """Draw actual buttons and an AutoForm action through nested scopes."""

    def __init__(self, outer, inner):
        self.outer, self.inner = outer, inner
        self.clicked = {"nested": 0, "action": 0, "parent": 0, "outside": 0}
        self.rects = {}
        self.flags = []
        self.form = FormState()
        self.context = None
        super().__init__(self.gui)
        self.io.wall_clock = False

    def action(self):
        """Record activation from the actual AutoForm action dispatcher."""
        self.clicked["action"] += 1

    def button(self, name):
        """Render a button and retain its actual hit rectangle."""
        if im.button(name):
            self.clicked[name] += 1
        self.rects[name] = im.get_item_rect()
        im.set_item_tooltip(HELP)

    def disabled(self):
        """Read the active disabled bit at the current scope depth."""
        return bool(im.get_item_flags() & im.ItemFlags.DISABLED)

    def gui(self):
        """Draw each nesting level followed by an enabled sibling."""
        self.context = im.get_current_context()
        im.begin("Nested scopes", self.context.box)
        im.begin_disabled(self.outer)
        im.begin_disabled(self.inner)
        self.flags = [self.disabled()]
        self.button("nested")
        draw_sections([{"type": "button_row", "buttons": [
            {"label": "Action", "action": "action", "description": HELP}
        ]}], self, self.form)
        self.flags.append(self.disabled())
        im.end_disabled()
        self.flags.append(self.disabled())
        self.button("parent")
        im.end_disabled()
        self.flags.append(self.disabled())
        self.button("outside")
        im.end()


@pytest.mark.parametrize("outer,inner", [(True, False), (True, True), (False, True), (False, False)])
def test_nested_disabled_state_and_real_actions_restore_each_scope(outer, inner):
    """Pointer clicks and AutoForm dispatch obey inherited disablement, then recover."""
    app = NestedApp(outer, inner)
    driver = Driver(app, (400, 300))
    driver.frame(2)
    assert app.flags == [outer or inner, outer or inner, outer, False]
    driver.click(app.rects["nested"])
    driver.click(app.form.rects["action"])
    driver.click(app.rects["parent"])
    driver.click(app.rects["outside"])
    assert app.clicked == {
        "nested": int(not (outer or inner)),
        "action": int(not (outer or inner)),
        "parent": int(not outer),
        "outside": 1,
    }
    assert app.flags == [outer or inner, outer or inner, outer, False]


@pytest.mark.parametrize("target", ["nested", "action"])
def test_nested_disabled_controls_retain_delayed_hover_help(target):
    """Disabled buttons explain their state while rejecting real activation."""
    app = NestedApp(True, False)
    driver = Driver(app, (400, 300))
    driver.frame(2)
    rect = app.form.rects["action"] if target == "action" else app.rects[target]
    painter = driver.hover(rect)
    assert app.context.tooltip == HELP
    assert app.context.box_tooltip is None
    assert HELP not in " ".join(painter.strings)
    app.io.now += 1.0
    painter = driver.frame(2)
    assert app.context.box_tooltip is not None
    assert HELP in " ".join(painter.strings)
    driver.click(rect)
    assert app.clicked[target] == 0
    driver.hover((390, 290))
    assert app.context.tooltip is None
