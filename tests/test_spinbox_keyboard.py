"""Driver-based keyboard tests verifying integer inputs behave as spinboxes."""
import pytest
from emtk import im, keys
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER, LEFT_BUTTON
from emtk.testing import Driver
from emtk.widgets.basic import InputInt as BasicInputInt
from emtk.widgets.drag import DragInt as WidgetDragInt
from emtk.widgets.inputs import InputScalar


class IntInputsApp(ImApp):
    """An ImApp containing im.input_int and im.drag_int."""

    def __init__(self):
        super().__init__(self.render)
        self.val_input_int = 10
        self.val_drag_int = 50
        self.seen_keys = []
        self.ids = {}

    def render(self):
        self.seen_keys.append(self.io.key)
        im.begin("Spinbox Form", (0, 0, 400, 300))
        _, self.val_input_int = im.input_int("MyInputInt", self.val_input_int, step=1, step_fast=100)
        self.ids["MyInputInt"] = im.get_item_id()
        self.remember("MyInputInt")

        _, self.val_drag_int = im.drag_int("MyDragInt", self.val_drag_int, speed=1, v_min=0, v_max=100)
        self.ids["MyDragInt"] = im.get_item_id()
        self.remember("MyDragInt")
        im.end()


def test_im_input_int_spinbox_keyboard():
    app = IntInputsApp()
    driver = Driver(app, (400, 300))
    driver.frame(2)

    # Focus MyInputInt
    app.storage["__nav_id__"] = app.ids["MyInputInt"]
    driver.frame()

    # Up arrow increments by 1
    driver.press(keys.KEY_UP)
    assert app.val_input_int == 11

    # Down arrow decrements by 1
    driver.press(keys.KEY_DOWN)
    assert app.val_input_int == 10

    # Fast step with Control modifier increments by 100
    driver.press(keys.KEY_UP, mods=CONTROL_MODIFIER)
    assert app.val_input_int == 110

    # Fast step with Control modifier decrements by 100
    driver.press(keys.KEY_DOWN, mods=CONTROL_MODIFIER)
    assert app.val_input_int == 10


def test_im_drag_int_spinbox_keyboard():
    app = IntInputsApp()
    driver = Driver(app, (400, 300))
    driver.frame(2)

    # Focus MyDragInt
    app.storage["__nav_id__"] = app.ids["MyDragInt"]
    driver.frame()

    # Up arrow increments by 1
    driver.press(keys.KEY_UP)
    assert app.val_drag_int == 51

    # Down arrow decrements by 1
    driver.press(keys.KEY_DOWN)
    assert app.val_drag_int == 50

    # Fast step with Control modifier increments and clamps to v_max (100)
    driver.press(keys.KEY_UP, mods=CONTROL_MODIFIER)
    assert app.val_drag_int == 100

    # Fast step with Control modifier decrements and clamps to v_min (0)
    driver.press(keys.KEY_DOWN, mods=CONTROL_MODIFIER)
    assert app.val_drag_int == 0


def test_widgets_basic_input_int_spinbox():
    w = BasicInputInt("Counter", value=5, v_min=0, v_max=50, step=1, step_fast=10)

    # Keyboard Up/Down
    assert w.key(keys.KEY_UP) is True
    assert w.value == 6

    assert w.key(keys.KEY_DOWN) is True
    assert w.value == 5

    # Fast modifier
    assert w.key(keys.KEY_UP, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 15

    assert w.key(keys.KEY_DOWN, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 5

    # Bounds clamping
    w.set_value(48)
    w.key(keys.KEY_UP, modifiers=CONTROL_MODIFIER)
    assert w.value == 50

    # Mouse stepper press behavior preserved
    # Stepper "-" at right - 3*h to right - 2*h; Stepper "+" at right - h to right
    # Box: x=0, y=0, w=100, h=20. Stepper "+": [80, 100], Stepper "-": [40, 60]
    val = w.press(90, 10, 0, 0, 100, 20)
    assert val == 50  # clamped at max
    w.set_value(20)
    val = w.press(90, 10, 0, 0, 100, 20)
    assert val == 21
    val = w.press(50, 10, 0, 0, 100, 20)
    assert val == 20


def test_widgets_inputs_input_scalar_spinbox():
    w = InputScalar("Number", value=42, integer=True, step=1, step_fast=10)

    # When not editing, Up/Down works
    assert w.key(keys.KEY_UP) is True
    assert w.value == 43

    assert w.key(keys.KEY_DOWN) is True
    assert w.value == 42

    # Fast modifier
    assert w.key(keys.KEY_UP, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 52

    assert w.key(keys.KEY_DOWN, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 42

    # While editing
    w.begin_edit()
    assert w.editing is True
    w.key(keys.KEY_UP)
    assert w.value == 43
    assert w.field.text == "43"

    # Commit with Enter
    w.key(keys.KEY_ENTER)
    assert w.editing is False
    assert w.value == 43


def test_widgets_drag_int_spinbox():
    w = WidgetDragInt("Scrub", value=10, v_speed=1.0, v_min=0, v_max=200)

    # Keyboard Up/Down
    assert w.key(keys.KEY_UP) is True
    assert w.value == 11

    assert w.key(keys.KEY_DOWN) is True
    assert w.value == 10

    # Fast modifier
    assert w.key(keys.KEY_UP, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 110

    assert w.key(keys.KEY_DOWN, modifiers=CONTROL_MODIFIER) is True
    assert w.value == 10

    # Drag behavior preserved
    # press at x=50, y=10 in box (0, 0, 100, 20)
    assert w.press(50, 10, 0, 0, 100, 20) is True
    assert w.held is True
    w.drag(70, 10, 0, 0, 100, 20)
    assert w.value > 10
    w.release()
    assert w.held is False
