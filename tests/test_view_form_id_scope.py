"""Two forms that name an action alike are two buttons, not one.

emtk windows do not open an id scope, and a button's id is what follows ``##`` in its
label -- the action name. A toolbar form with an ``import_file`` action and a panel form
with its own ``import_file`` therefore shared one id: the press captured the panel's
button, the toolbar's (drawn first, not hovered) released the capture, and the panel's
action never ran. Each :class:`FormState` now draws inside its own id scope.
"""

from __future__ import annotations

import emtk
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form


class _Model:
    def __init__(self):
        self.ran = 0

    def import_file(self):
        self.ran += 1


def test_the_same_action_in_two_forms_runs_the_pressed_one():
    toolbar, panel = _Model(), _Model()
    top, body = FormState(), FormState()
    spec_top = {"sections": [{"type": "button_row", "buttons": [
        {"action": "import_file", "label": "Import"}]}]}
    spec_body = {"sections": [{"type": "button_row", "buttons": [
        {"action": "import_file", "label": "Import file"}]}]}

    def gui():
        emtk.begin("top", (0, 0, 400, 40))
        draw_form(spec_top, toolbar, top)
        emtk.end()
        emtk.begin("body", (0, 50, 400, 200))
        draw_form(spec_body, panel, body)
        emtk.end()

    app = ImApp(gui)
    driver = Driver(app, (400, 260))
    driver.draw(2)
    driver.click(body.rects["import_file"])
    driver.draw(2)
    assert (toolbar.ran, panel.ran) == (0, 1)
    driver.click(top.rects["import_file"])
    driver.draw(2)
    assert (toolbar.ran, panel.ran) == (1, 1)


def test_two_forms_get_two_scopes():
    assert FormState().scope != FormState().scope
