"""The toolkit driver exercises real widgets through host events."""
from types import SimpleNamespace

import pytest

from emtk import im, keys
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER
from emtk.testing import Driver, MetricPainter, PixelPainter, png_decode


class Form(ImApp):
    def __init__(self):
        super().__init__(self.render)
        self.count = 0
        self.value = ""
        self.show_button = True

    def render(self):
        im.begin("Driver demo", (0, 0, 360, 200))
        if self.show_button:
            if im.button("Increment"):
                self.count += 1
            self.remember("increment")
        _, self.value = im.input_text("Name", self.value)
        self.remember("name")
        im.text(f"Count: {self.count}")
        im.end()


def test_click_resolves_ids_captions_rectangles_and_points():
    app = Form()
    drv = Driver(app, (360, 200))
    drv.frame(2)
    assert drv.ids() == ["increment", "name"]
    for target in ("increment", "Increment", drv.rect("increment")):
        drv.click(target)
    x, y, w, h = drv.rect("increment")
    drv.click((x + w / 2, y + h / 2))
    assert app.count == 4
    assert not any(app.io.mouse_down)


def test_type_and_modifiers_reach_a_real_text_field():
    app = Form()
    drv = Driver(app, (360, 200))
    drv.frame(2)
    drv.click("name")
    drv.type("old")
    drv.press(ord("A"), CONTROL_MODIFIER)
    drv.type("new")
    drv.press(keys.KEY_RETURN)
    assert app.value == "new"


def test_ids_only_include_controls_drawn_in_the_last_frame():
    app = Form()
    drv = Driver(app)
    drv.frame(2)
    app.show_button = False
    drv.frame()
    assert "increment" not in drv.ids()
    with pytest.raises(LookupError, match="was not drawn"):
        drv.click("increment")


def test_wheel_and_hover_follow_host_coordinates():
    app = Form()
    seen = []
    wheel = app.wheel
    def record(x, y, steps, modifiers=0):
        seen.append((x, y, steps))
        wheel(x, y, steps, modifiers)
    app.wheel = record
    drv = Driver(app)
    drv.wheel(-2, at=(50, 60))
    assert app.io.mouse_pos == (50, 60)
    assert seen == [(50, 60, -2)]


def test_screenshot_is_a_png_at_the_canvas_size(tmp_path):
    drv = Driver(Form(), (360, 200))
    drv.frame(2)
    drv.click("Increment")
    path = tmp_path / "renders" / "driver.png"
    png = drv.screenshot(path)
    assert path.read_bytes() == png
    w, h, px = png_decode(png)
    assert (w, h) == (360, 200)
    assert len(set(tuple(px[i:i + 4]) for i in range(0, len(px), 4))) > 10


def test_metric_painters_match_pixels_and_do_not_share_font_state():
    a, b = MetricPainter(), MetricPainter()
    pixels = PixelPainter(1, 1)
    a.set_font_scale(1.75)
    pixels.set_font_scale(1.75)
    assert a.text_width("driver") == pixels.text_width("driver")
    assert a.line_height() == pixels.line_height()
    assert b.line_height() != a.line_height()


def test_settle_needs_no_model_and_waits_for_every_busy_source():
    drv = Driver(Form())
    drv.settle(timeout=0)
    drv.app.model = SimpleNamespace(busy=True)
    with pytest.raises(TimeoutError):
        drv.settle(timeout=0)
    drv.app.model.busy = False
    drv.app.running = True
    with pytest.raises(TimeoutError):
        drv.settle(timeout=0)
    drv.app.running = False
    drv.app.job = SimpleNamespace(busy=True)
    with pytest.raises(TimeoutError):
        drv.settle(timeout=0)


def test_callback_and_resize_are_supported():
    drv = Driver(lambda: im.text("callback"), (320, 200))
    assert "callback" in drv.draw(size=(400, 240)).strings
    assert drv.size == (400, 240)


@pytest.mark.parametrize("size", [(0, 20), (20, -1), (1, 2, 3)])
def test_invalid_canvas_size_fails_early(size):
    with pytest.raises(ValueError):
        Driver(Form(), size)
