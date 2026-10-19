"""A press and its release that arrive between two frames still make a click.

A trackpad tap, a fast click or a click during a slow frame delivers both before the next
frame. That frame used to see the press with the button already up, so every widget that
acts while the button is *held* -- a slider set by a click, a drag, a text field taking
focus -- ignored it, while buttons (which fire on release) worked: "sometimes a click does
not land". The release is held back one frame, as ImGui's input queue trickles it.
"""

from emtk import im
from emtk.app import ImApp
from emtk.events import LEFT_BUTTON
from emtk.testing import Driver


def _slider_app():
    state = {"v": 0.5, "box": None}

    def gui():
        im.begin("w", (0, 0, 400, 120))
        _changed, state["v"] = im.slider_float("##v", state["v"], 0.0, 1.0)
        state["box"] = im.get_item_rect()
        im.end()

    return ImApp(gui), state


def _tap(driver, x, y):
    surface = driver.surface
    surface.on_pointer_move(x, y, 0, 0)
    driver.frame()
    surface.on_pointer_press(x, y, LEFT_BUTTON, 0)
    surface.on_pointer_release(x, y, LEFT_BUTTON, 0)  # same delivery: no frame between
    driver.frame()
    driver.frame()


def test_a_tap_sets_a_slider():
    app, state = _slider_app()
    driver = Driver(app, (400, 120))
    driver.frame()
    x, y, w, h = state["box"]
    _tap(driver, x + 0.9 * w, y + h / 2)
    assert state["v"] > 0.8
    _tap(driver, x + 0.1 * w, y + h / 2)
    assert state["v"] < 0.2


def test_the_release_lands_one_frame_after_the_press():
    app, _state = _slider_app()
    io = app.io
    app.pointer_press(10, 10, LEFT_BUTTON)
    app.pointer_release(10, 10, LEFT_BUTTON)
    assert io.mouse_down[0] and io.mouse_clicked[0] and not io.mouse_released[0]
    io.end_event()
    assert not io.mouse_down[0] and io.mouse_released[0] and not io.mouse_clicked[0]
    io.end_event()
    assert not io.mouse_released[0]


def test_a_release_after_a_frame_is_not_delayed():
    app, _state = _slider_app()
    io = app.io
    app.pointer_press(10, 10, LEFT_BUTTON)
    io.end_event()
    app.pointer_release(10, 10, LEFT_BUTTON)
    assert not io.mouse_down[0] and io.mouse_released[0]


def test_a_second_press_before_the_frame_keeps_the_button_down():
    app, _state = _slider_app()
    io = app.io
    app.pointer_press(10, 10, LEFT_BUTTON)
    app.pointer_release(10, 10, LEFT_BUTTON)
    app.pointer_press(10, 10, LEFT_BUTTON)
    io.end_event()
    assert io.mouse_down[0]
