"""The frame's tooltip: shown after a rest, one at a time, inside the frame.

``set_item_tooltip`` used to record a string that no frame-driven host ever
drew. The frame's end now draws it (:mod:`emtk.tooltip`), last, with the
timing of a desktop toolkit, and asks an idle host for one wake-up when the
delay runs out.
"""
from __future__ import annotations

import pytest

from emtk import im
from emtk import im_core as core
from emtk.app import ImApp, next_frame_in
from emtk.testing import PixelPainter

BOX = (0.0, 0.0, 400.0, 300.0)


class _Clock:
    """A form with two buttons and a field, drawn at the times a test says."""

    def __init__(self, gui=None, style=None) -> None:
        self.io = core.IO()
        self.storage: dict = {}
        self.style = style
        self.rects: dict = {}
        self.gui = gui or self._gui
        self.ctx = None

    def _gui(self) -> None:
        im.set_cursor_pos((20.0, 20.0))
        im.button("Alpha")
        self.rects["a"] = self._rect()
        im.set_item_tooltip("alpha's tooltip")
        im.same_line()
        im.button("Beta")
        self.rects["b"] = self._rect()
        im.set_item_tooltip("beta's tooltip")
        im.button("Plain")
        self.rects["plain"] = self._rect()

    @staticmethod
    def _rect():
        (x0, y0), (x1, y1) = im.get_item_rect_min(), im.get_item_rect_max()
        return (x0, y0, x1 - x0, y1 - y0)

    def centre(self, name):
        x, y, w, h = self.rects[name]
        return (x + w / 2.0, y + h / 2.0)

    def frame(self, now, box=BOX):
        painter = PixelPainter(int(box[2]), int(box[3]))
        with core.frame(painter, box, io=self.io, style=self.style,
                        storage=self.storage, now=now) as ctx:
            self.gui()
        self.ctx = ctx
        return ctx

    def move(self, name_or_pos):
        pos = self.centre(name_or_pos) if isinstance(name_or_pos, str) else name_or_pos
        self.io.mouse_pos = (float(pos[0]), float(pos[1]))


def _start(clock: _Clock) -> None:
    clock.frame(1.0)                      # lay out, pointer outside


def test_no_tooltip_before_the_delay_then_one_after_it():
    clock = _Clock()
    _start(clock)
    clock.move("a")
    ctx = clock.frame(2.0)
    assert ctx.tooltip == "alpha's tooltip"
    assert ctx.box_tooltip is None
    # The host is told when to come back -- once, not every frame.
    assert clock.io.next_frame_in == pytest.approx(0.5)
    assert not ctx.frame_requested
    ctx = clock.frame(2.3)
    assert ctx.box_tooltip is None
    assert clock.io.next_frame_in == pytest.approx(0.2)
    ctx = clock.frame(2.5)
    assert ctx.box_tooltip is not None
    assert clock.io.next_frame_in is None


def test_the_delay_is_a_style_setting():
    clock = _Clock(style=core.Style(tooltip_delay=1.5))
    _start(clock)
    clock.move("a")
    clock.frame(2.0)
    assert clock.frame(3.0).box_tooltip is None
    assert clock.frame(3.5).box_tooltip is not None


def test_only_one_tooltip_at_a_time():
    def gui():
        ctx = core.get_current_context()
        ctx.set_tooltip("first", owner="one")
        ctx.set_tooltip("second", owner="two")

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    clock.io.mouse_pos = (50.0, 50.0)
    ctx = clock.frame(1.0)
    assert ctx.tooltip == "second"
    assert ctx.box_tooltip is not None


def test_one_item_saying_two_things_shows_both_in_one_box():
    def gui():
        ctx = core.get_current_context()
        ctx.set_tooltip("a very long option name", owner="combo")
        ctx.set_tooltip("what the choice is for", owner="combo")
        ctx.set_tooltip("what the choice is for", owner="combo")

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    clock.io.mouse_pos = (50.0, 50.0)
    ctx = clock.frame(1.0)
    assert ctx.tooltip == "a very long option name\nwhat the choice is for"
    x, y, w, h = ctx.box_tooltip
    assert h > 1.5 * ctx.p.line_height()


@pytest.mark.parametrize("corner", ["right", "bottom", "both"])
def test_the_box_stays_inside_the_frame_at_its_edges(corner):
    text = "a tooltip long enough to need wrapping " * 4

    def gui():
        core.get_current_context().set_tooltip(text, owner="edge")

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    px = {"right": 396.0, "bottom": 100.0, "both": 396.0}[corner]
    py = {"right": 100.0, "bottom": 296.0, "both": 296.0}[corner]
    clock.io.mouse_pos = (px, py)
    ctx = clock.frame(1.0)
    x, y, w, h = ctx.box_tooltip
    assert 0.0 <= x and x + w <= BOX[2]
    assert 0.0 <= y and y + h <= BOX[3]
    assert w <= ctx.style.tooltip_max_width + 2 * 6.0 + 1.0, "it wraps"
    if corner in ("right", "both"):
        assert x + w <= px, "flipped to the pointer's left"
    if corner in ("bottom", "both"):
        assert y + h <= py, "flipped above the pointer"
    if corner == "right":
        assert y > py, "still below the pointer"


def test_a_press_hides_it_until_the_pointer_leaves_the_item():
    clock = _Clock()
    _start(clock)
    clock.move("a")
    clock.frame(2.0)
    assert clock.frame(2.6).box_tooltip is not None
    clock.io.mouse_down[0] = clock.io.mouse_clicked[0] = True
    assert clock.frame(2.7).box_tooltip is None
    clock.io.mouse_down[0] = False
    clock.io.mouse_released[0] = True
    assert clock.frame(2.8).box_tooltip is None
    # Resting on the pressed item does not bring it back ...
    assert clock.frame(5.0).box_tooltip is None
    assert clock.io.next_frame_in is None, "and asks for no wake-up"
    # ... leaving and coming back does, after the full delay (cooled).
    clock.move("plain")
    clock.frame(5.1)
    clock.move("a")
    assert clock.frame(5.2).box_tooltip is None
    assert clock.frame(5.8).box_tooltip is not None


@pytest.mark.parametrize("event", ["wheel", "key"])
def test_a_wheel_or_a_key_hides_it(event):
    clock = _Clock()
    _start(clock)
    clock.move("a")
    clock.frame(2.0)
    assert clock.frame(2.6).box_tooltip is not None
    if event == "wheel":
        clock.io.mouse_wheel = 1.0
    else:
        clock.io.key = 65
    assert clock.frame(2.7).box_tooltip is None


def test_moving_off_hides_it():
    clock = _Clock()
    _start(clock)
    clock.move("a")
    clock.frame(2.0)
    assert clock.frame(2.6).box_tooltip is not None
    clock.move((390.0, 290.0))
    assert clock.frame(2.7).box_tooltip is None


def test_the_warm_neighbour_shows_at_once_then_cools():
    clock = _Clock()
    _start(clock)
    clock.move("a")
    clock.frame(2.0)
    assert clock.frame(2.6).box_tooltip is not None
    clock.move("b")
    ctx = clock.frame(2.7)
    assert ctx.tooltip == "beta's tooltip"
    assert ctx.box_tooltip is not None, "warm: no second wait"
    # Across a gap with no tooltip, within the grace: still warm.
    clock.move("plain")
    assert clock.frame(2.8).box_tooltip is None
    clock.move("a")
    assert clock.frame(3.0).box_tooltip is not None
    # Long after: cold again, the full delay.
    clock.move("plain")
    clock.frame(3.1)
    clock.move("b")
    assert clock.frame(5.0).box_tooltip is None
    assert clock.frame(5.5).box_tooltip is not None


def test_it_is_drawn_over_the_overlays():
    order = []

    def gui():
        ctx = core.get_current_context()
        ctx.add_overlay("list", lambda c: order.append("overlay") or False)
        ctx.set_tooltip("on top", owner="x")

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    clock.io.mouse_pos = (50.0, 50.0)
    painter = PixelPainter(400, 300)
    stroke = painter.stroke_rect

    def spy(*args, **kw):
        order.append("tooltip")
        return stroke(*args, **kw)

    painter.stroke_rect = spy
    with core.frame(painter, BOX, io=clock.io, style=clock.style,
                    storage=clock.storage, now=1.0):
        gui()
    assert order == ["overlay", "tooltip"]


def test_im_app_reports_the_wake_up_to_its_host():
    app = ImApp(lambda: (im.button("Go"), im.set_item_tooltip("go")))
    app.io.wall_clock = False
    app.io.delta_time = 0.1
    app.draw(PixelPainter(200, 100), 0.0, 0.0, 200.0, 100.0)
    assert next_frame_in(app) is None
    app.pointer_move(20.0, 15.0)
    app.draw(PixelPainter(200, 100), 0.0, 0.0, 200.0, 100.0)
    assert not app.animating()
    assert next_frame_in(app) == pytest.approx(0.5)


def test_a_control_that_runs_frame_over_its_own_io_is_read_too():
    class Frameish:
        def __init__(self):
            self.io = core.IO()
            self.io.next_frame_in = 0.25

    assert next_frame_in(Frameish()) == 0.25
    assert next_frame_in(object()) is None


def test_data_table_headers_and_rows_have_tooltips():
    from emtk.widgets.data_table import TableBinding, draw_table

    class Model:
        rows = [{"name": "a", "note": "first row's note"},
                {"name": "b", "note": ""}]

    binding = TableBinding({"type": "data_table", "source": "rows", "tooltip_key": "note",
                            "columns": [{"key": "name", "tooltip": "the name column"}]},
                           Model())
    state = {}

    def gui():
        draw_table(binding, "t", 300.0, 120.0)

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    clock.frame(1.0)
    hx, hy, hw, hh = binding.control._header_box
    clock.io.mouse_pos = (hx + 10.0, hy + hh / 2.0)
    ctx = clock.frame(1.1)
    assert ctx.tooltip == "the name column"
    assert ctx.box_tooltip is not None
    bx, by, bw, bh = binding.control._body_box
    row_h = binding.control._row_h
    clock.io.mouse_pos = (bx + 10.0, by + row_h / 2.0)
    ctx = clock.frame(1.2)
    assert ctx.tooltip == "first row's note"
    state["owner0"] = ctx.tooltip_owner
    clock.io.mouse_pos = (bx + 10.0, by + row_h * 1.5)
    ctx = clock.frame(1.3)
    assert ctx.tooltip is None, "a row with no note has no tooltip"


def test_view_form_description_and_a_cut_combo_caption():
    from emtk import view_form

    long = "a remarkably long option that cannot fit"

    class Model:
        choice = long

    sections = [{"type": "choice", "attr": "choice", "options": [long, "b"],
                 "description": "which option"}]
    model = Model()
    state = view_form.FormState()

    def gui():
        view_form.draw_sections(sections, model, state)

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    small = (0.0, 0.0, 160.0, 120.0)
    clock.frame(1.0, box=small)
    rect = state.rects.get("choice")
    assert rect is not None
    clock.io.mouse_pos = (rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0)
    ctx = clock.frame(1.1, box=small)
    assert ctx.tooltip == f"{long}\nwhich option"
    x, y, w, h = ctx.box_tooltip
    assert x >= 0.0 and x + w <= small[2]


# --------------------------------------------------------------------------- #
# Hosts
# --------------------------------------------------------------------------- #
class _Loop:
    """A ``call_later`` that only records -- the test fires the callbacks."""

    def __init__(self) -> None:
        self.calls = []

    def call_later(self, delay, callback, *args):
        self.calls.append((delay, callback, args))

    def fire_last(self):
        _delay, callback, args = self.calls[-1]
        callback(*args)


@pytest.fixture(scope="module")
def device():
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


def _button_gui(state):
    def gui():
        im.set_cursor_pos((20.0, 20.0))
        im.button("Hover me")
        (x0, y0), (x1, y1) = im.get_item_rect_min(), im.get_item_rect_max()
        state["rect"] = (x0, y0, x1 - x0, y1 - y0)
        im.set_item_tooltip("A tooltip, drawn by the frame")
    return gui


def _native(app, device, ratio, size=(320, 160), loop=None):
    from rendercanvas.offscreen import RenderCanvas

    from emtk.native import NativeHost

    canvas = RenderCanvas(size=size, pixel_ratio=ratio)
    return NativeHost(app, canvas=canvas, device=device, loop=loop)


@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_the_native_host_draws_it_at_every_ratio(device, ratio):
    np = pytest.importorskip("numpy")
    state = {}
    app = ImApp(_button_gui(state), style=core.Style(tooltip_delay=0.0))
    host = _native(app, device, ratio)
    host.draw_frame()
    x, y, w, h = state["rect"]
    host.surface.on_pointer_move(x + w / 2.0, y + h / 2.0, 0, 0)
    image = np.asarray(host.draw_frame())[..., :3].astype(int)
    assert image.shape[:2] == (160 * ratio, 320 * ratio)
    tip = app.storage["__tooltip__"]["box"]
    assert tip is not None
    tx, ty, tw, th = tip
    # Logical box, device pixels: the popup background fills it at box * ratio.
    popup = np.array(app.style.color(core.Col.POPUP_BG)[:3] if app.style else
                     core.Style().color(core.Col.POPUP_BG)[:3])
    inside = image[int((ty + 2) * ratio), int((tx + 2) * ratio)]
    assert np.abs(inside - popup).max() <= 12
    # The box is as wide as its logical width times the ratio, no more.
    row = image[int((ty + 2) * ratio)]
    filled = np.flatnonzero(np.abs(row - popup).max(axis=1) <= 12)
    assert filled[0] == pytest.approx(tx * ratio, abs=2 * ratio)
    # Text on it: something much brighter than the background inside the box.
    region = image[int(ty * ratio):int((ty + th) * ratio), int(tx * ratio):int((tx + tw) * ratio)]
    assert (region.mean(axis=2) > 150).sum() > 20 * ratio


def test_an_idle_native_host_asks_for_one_wake_up_not_a_stream(device):
    state = {}
    app = ImApp(_button_gui(state))
    app.io.wall_clock = False
    app.io.delta_time = 0.5
    loop = _Loop()
    host = _native(app, device, 1.0, loop=loop)
    requested = []
    original = host.canvas.request_draw
    host.canvas.request_draw = lambda *a: (requested.append(a), original(*a))
    host.draw_frame()
    assert loop.calls == [], "nothing hovered: no wake-up"
    x, y, w, h = state["rect"]
    host.surface.on_pointer_move(x + w / 2.0, y + h / 2.0, 0, 0)
    host.draw_frame()
    assert not host.surface.animating(), "no continuous frames while waiting"
    assert len(loop.calls) == 1 and loop.calls[0][0] == pytest.approx(0.5)
    requested.clear()
    loop.fire_last()
    assert len(requested) == 1, "the wake-up asks for exactly one draw"
    host.draw_frame()
    assert app.storage["__tooltip__"]["box"] is not None
    assert len(loop.calls) == 1, "shown: nothing more to wait for"
    assert not host.surface.animating()


def test_a_stale_wake_up_draws_nothing(device):
    state = {}
    app = ImApp(_button_gui(state))
    app.io.wall_clock = False
    app.io.delta_time = 0.1
    loop = _Loop()
    host = _native(app, device, 1.0, loop=loop)
    host.draw_frame()
    x, y, w, h = state["rect"]
    host.surface.on_pointer_move(x + w / 2.0, y + h / 2.0, 0, 0)
    host.draw_frame()
    host.draw_frame()                     # another frame came first
    requested = []
    host.canvas.request_draw = lambda *a: requested.append(a)
    _delay, callback, args = loop.calls[0]
    callback(*args)
    assert requested == []


def test_the_web_page_hands_boot_js_a_number():
    from types import SimpleNamespace

    from emtk.web.page import WebPage

    page = SimpleNamespace(surface=SimpleNamespace(next_frame_in=lambda: 0.3))
    assert WebPage.wake_in(page) == pytest.approx(0.3)
    page = SimpleNamespace(surface=SimpleNamespace(next_frame_in=lambda: None))
    assert WebPage.wake_in(page) == -1.0


def test_boot_js_sets_one_timer_from_wake_in():
    import pathlib

    import emtk.web

    source = (pathlib.Path(emtk.web.__file__).parent / "boot.js").read_text()
    assert "page.wake_in()" in source
    assert "clearTimeout(wake)" in source


def test_the_qt_host_arms_one_single_shot_timer(qt_app):
    from emtk.qt_host import ControlHost

    state = {}
    app = ImApp(_button_gui(state))
    host = ControlHost(app)
    host.resize(240, 100)
    host.grab()
    x, y, w, h = state["rect"]
    app.pointer_move(x + w / 2.0, y + h / 2.0)
    host.grab()
    timer = getattr(host, "_wake", None)
    assert timer is not None and timer.isActive() and timer.isSingleShot()
    assert 0 < timer.interval() <= 500


def test_a_disabled_item_still_says_why_in_its_tooltip():
    """ImGui sets the hovered id of a disabled item and its tooltips allow
    disabled items (``ImGuiHoveredFlags_AllowWhenDisabled``): a greyed-out
    control can say why it is greyed out. It still neither hovers nor fires."""
    seen = {"pressed": False}

    def gui():
        im.set_cursor_pos((20.0, 20.0))
        im.begin_disabled(True)
        seen["pressed"] |= im.button("Off")
        seen["hovered"] = im.is_item_hovered()
        seen["for_tooltip"] = im.is_item_hovered(allow_when_disabled=True)
        clock.rects["off"] = clock._rect()
        im.set_item_tooltip("unavailable: no lifetime column")
        im.end_disabled()

    clock = _Clock(gui=gui, style=core.Style(tooltip_delay=0.0))
    _start(clock)
    clock.move("off")
    ctx = clock.frame(2.0)
    assert ctx.tooltip == "unavailable: no lifetime column"
    assert not seen["hovered"] and seen["for_tooltip"]
    clock.io.mouse_down[0] = True
    clock.frame(2.1)
    clock.io.mouse_down[0] = False
    ctx = clock.frame(2.2)
    assert not seen["pressed"] and ctx.active_id is None
