"""Keyboard navigation is part of the frame, independent of host or application."""
import pytest

from emtk import im, keys
from emtk.app import ImApp
from emtk.events import SHIFT_MODIFIER
from emtk.testing import Driver


class NavForm(ImApp):
    """A realistic form with each focusable control and application key handling."""

    def __init__(self):
        super().__init__(self.render)
        self.count = 0
        self.checked = False
        self.floating = 0.5
        self.integer = 5
        self.choice = 1
        self.value = "sample"
        self.seen_keys = []
        self.ids_by_label = {}

    def remember_item(self, label):
        self.ids_by_label[label] = im.get_item_id()
        self.remember(label)

    def render(self):
        self.seen_keys.append(self.io.key)
        im.begin("Keyboard form", (0, 0, 420, 320))
        if im.button("Run"):
            self.count += 1
        self.remember_item("Run")
        im.small_button("Reset")
        self.remember_item("Reset")
        _, self.checked = im.checkbox("Enabled", self.checked)
        self.remember_item("Enabled")
        im.radio_button("Choice", True)
        self.remember_item("Choice")
        im.set_next_item_width(300)
        _, self.floating = im.slider_float("Gain", self.floating, 0, 1)
        self.remember_item("Gain")
        im.set_next_item_width(300)
        _, self.integer = im.slider_int("Count", self.integer, 0, 10)
        self.remember_item("Count")
        im.set_next_item_width(300)
        _, self.choice = im.combo("Mode", self.choice, ["First", "Second", "Third"])
        self.remember_item("Mode")
        im.set_next_item_width(300)
        _, self.value = im.input_text("Name", self.value)
        self.remember_item("Name")
        im.end()


def form():
    app = NavForm()
    driver = Driver(app, (420, 320))
    driver.frame(2)
    return app, driver


def focus(app, driver, label):
    app.storage["__nav_id__"] = app.ids_by_label[label]
    driver.frame()


def test_keyboard_navigation_is_enabled_by_default():
    assert im.IO().config_flags & im.ConfigFlags.NAV_ENABLE_KEYBOARD


def test_tab_is_consumed_before_application_key_handling_and_wraps():
    app, driver = form()
    labels = list(app.ids_by_label)
    for label in labels + labels[:1]:
        app.seen_keys.clear()
        driver.press(keys.KEY_TAB)
        assert keys.KEY_TAB not in app.seen_keys
        assert app.storage["__nav_id__"] == app.ids_by_label[label]
    driver.press(keys.KEY_TAB, SHIFT_MODIFIER)
    assert app.storage["__nav_id__"] == app.ids_by_label[labels[-1]]


@pytest.mark.parametrize("key", [keys.KEY_RETURN, keys.KEY_ENTER, keys.KEY_SPACE])
def test_focused_button_activates_once_and_consumes_key(key):
    app, driver = form()
    focus(app, driver, "Run")
    driver.press(key)
    driver.frame(2)
    assert app.count == 1
    assert app.io.key == 0


@pytest.mark.parametrize("label", ["Run", "Reset", "Enabled", "Choice", "Gain", "Count", "Mode", "Name"])
def test_focused_controls_draw_a_focus_ring(label):
    app, driver = form()
    focus(app, driver, label)
    assert any(stroke[4] == im.Style().color(im.Col.NAV_HIGHLIGHT)
               for stroke in driver.painter.strokes)


def test_arrows_adjust_float_integer_and_combo_values_and_clamp():
    app, driver = form()
    focus(app, driver, "Gain")
    driver.press(keys.KEY_RIGHT)
    assert app.floating == pytest.approx(0.51)
    driver.press(keys.KEY_LEFT)
    assert app.floating == pytest.approx(0.5)
    focus(app, driver, "Count")
    driver.press(keys.KEY_RIGHT)
    assert app.integer == 6
    focus(app, driver, "Mode")
    driver.press(keys.KEY_DOWN)
    assert app.choice == 2
    driver.press(keys.KEY_DOWN)
    assert app.choice == 2
    driver.press(keys.KEY_UP)
    assert app.choice == 1


def test_tab_focus_gives_text_field_caret_and_typing_including_space():
    app, driver = form()
    driver.press(keys.KEY_TAB, SHIFT_MODIFIER)
    assert app.io.want_text_input
    x, y, w, h = driver.rect("Name")
    assert any(colour == im.Style().color(im.Col.TEXT)
               and all(y < point[1] < y + h for point in (a, b, c))
               and max(point[0] for point in (a, b, c)) - min(point[0] for point in (a, b, c)) <= 1
               for a, b, c, colour in driver.painter.triangles), "focused field has no caret"
    driver.type("hello world")
    assert app.value == "hello world"


def test_tab_leaves_mouse_focused_text_field():
    app, driver = form()
    driver.click("Name")
    driver.press(keys.KEY_TAB)
    driver.press(keys.KEY_SPACE)
    assert app.count == 1
    assert app.value == "sample"
    assert not app.io.want_text_input


def test_navigation_can_be_disabled_for_application_tab_handling():
    app, driver = form()
    app.io.config_flags = im.ConfigFlags.NONE
    app.seen_keys.clear()
    driver.press(keys.KEY_TAB)
    assert keys.KEY_TAB in app.seen_keys
    assert app.storage.get("__nav_id__") is None


def test_tab_wraps_inside_the_focused_window():
    ids = {}
    def gui():
        for title, x in (("First", 0), ("Second", 220)):
            im.begin(title, (x, 0, 200, 160))
            for label in ("One", "Two"):
                im.button(f"{label}##{title}-{label}")
                ids[title, label] = im.get_item_id()
            im.end()
    app = ImApp(gui)
    driver = Driver(app, (440, 160))
    driver.frame(2)
    app.storage["__nav_id__"] = ids["Second", "Two"]
    driver.press(keys.KEY_TAB)
    assert app.storage["__nav_id__"] == ids["Second", "One"]
    driver.press(keys.KEY_TAB, SHIFT_MODIFIER)
    assert app.storage["__nav_id__"] == ids["Second", "Two"]


@pytest.mark.parametrize("key", [keys.KEY_RETURN, keys.KEY_SPACE])
def test_combo_activation_opens_popup(key):
    from emtk import overlays
    app, driver = form()
    focus(app, driver, "Mode")
    driver.press(key)
    assert overlays.open_panels(app.storage)


def test_enter_remains_available_to_text_input():
    entered = []
    def gui():
        im.set_keyboard_focus_here()
        entered.append(im.input_text("Name", "sample", flags=im.InputTextFlags.ENTER_RETURNS_TRUE)[0])
    app = ImApp(gui)
    driver = Driver(app)
    driver.frame(2)
    driver.press(keys.KEY_RETURN)
    assert any(entered)
