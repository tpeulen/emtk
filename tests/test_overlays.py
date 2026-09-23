"""A combo's list and a context menu, drawn by emtk over the frame.

Driven through :mod:`emtk.view_form` and ``emtk.combo`` the way a user drives
them -- a click on the closed field, the wheel, keys, a click on a row -- with
no host code in between: nothing here reads a request or draws a popup.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_ESCAPE, KEY_UP
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form
from emtk.widgets import menus

ROW_H = RecordingPainter.LINE_H * menus.ROW_SCALE


class Model:
    def __init__(self, options, value=None):
        self.options = list(options)
        self.pick = value if value is not None else self.options[0]
        self.presses = 0

    def press(self):
        self.presses += 1


def _spec(width=None, above=0, below=0, button_above=False):
    choice = {"type": "choice", "attr": "pick", "label": "", "options_source": "options"}
    if width is not None:
        choice["width"] = width
    sections = [{"type": "info", "text": f"line {i}"} for i in range(above)]
    if button_above:
        sections.append({"type": "button_row", "buttons": [{"label": "Press", "action": "press"}]})
    sections.append(choice)
    sections += [{"type": "button_row", "buttons": [{"label": "Press", "action": "press"}]}
                 for _ in range(below)]
    return {"sections": sections}


class Form:
    """A form in a frame of *size*, and a pointer and keyboard to drive it."""

    def __init__(self, model, spec, size=(400.0, 300.0)):
        self.model, self.spec, self.size = model, spec, size
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.painter = RecordingPainter()
        self.frame()

    def frame(self):
        self.painter = RecordingPainter()
        w, h = self.size
        with emtk.frame(self.painter, (0.0, 0.0, w, h), io=self.io, storage=self.storage):
            emtk.begin("form", (0.0, 0.0, w, h))
            draw_form(self.spec, self.model, self.state, titles=False)
            emtk.end()
        return self.painter

    def click(self, x, y, button=0):
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[button] = (float(x), float(y))
        io.mouse_down[button] = io.mouse_clicked[button] = True
        self.frame()
        io.mouse_down[button], io.mouse_released[button] = False, True
        return self.frame()

    def open(self):
        x, y, w, h = self.state.rects["pick"]
        self.click(x + 5.0, y + h / 2.0)
        return self.panel()

    def key(self, key=0, text=""):
        self.io.key, self.io.text = key, text
        return self.frame()

    def wheel(self, x, y, steps):
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_wheel = float(steps)
        return self.frame()

    def panel(self):
        """The list the form has up, or ``None``."""
        for key, value in self.storage.items():
            if (isinstance(key, tuple) and key[0] == "__state__" and isinstance(key[1], tuple)
                    and key[1][0] == "overlay.combo" and value.get("panel") is not None):
                return value["panel"]
        return None


def _inside(rect, outer):
    x, y, w, h = rect
    ox, oy, ow, oh = outer
    return x >= ox - 0.01 and y >= oy - 0.01 and x + w <= ox + ow + 0.01 and y + h <= oy + oh + 0.01


# --------------------------------------------------------------------------- #
def test_a_narrow_combo_opens_a_list_as_wide_as_its_widest_item():
    names = ["a", "Number of photons (green, prompt)", "b"]
    form = Form(Model(names), _spec(width=60))
    field = form.state.rects["pick"]
    assert field[2] <= 61.0
    panel = form.open()
    x, y, w, h = panel.panel_rect
    need = RecordingPainter.GLYPH_W * len(names[1])
    assert w >= field[2] and w >= need + RecordingPainter.LINE_H * menus.MARK_SCALE
    assert not any(entry.cut(form.painter, panel.row_rect(i)[2])
                   for i, entry in enumerate(panel.entries)), "no row is cut"
    assert names[1] in form.painter.strings, "the long item is drawn whole"
    assert y == pytest.approx(field[1] + field[3]), "below the field"
    assert x == pytest.approx(field[0])


def test_an_item_wider_than_the_frame_ends_in_an_ellipsis_with_a_tooltip():
    long = "x" * 90                                   # 630 px in a 300 px frame
    form = Form(Model(["short", long]), _spec(width=80), size=(300.0, 300.0))
    panel = form.open()
    assert panel.panel_rect[2] == pytest.approx(300.0), "as wide as the frame, no wider"
    assert any(s.endswith("…") and s.startswith("xxx") for s in form.painter.strings)
    form.key(KEY_DOWN)                                # highlight the long one
    assert panel.tooltip == long
    tip = [t for t in form.painter.texts if t[5] and set(t[5]) == {"x"}]
    assert "".join(t[5] for t in tip) == long, "the tooltip says it all, wrapped"
    assert all(t[0] >= 0.0 and t[0] + 7.0 * len(t[5]) <= 300.0 for t in tip)


def test_a_list_near_the_bottom_flips_above_its_field():
    options = [f"option {i}" for i in range(6)]
    form = Form(Model(options), _spec(above=9), size=(300.0, 260.0))
    field = form.state.rects["pick"]
    assert 260.0 - (field[1] + field[3]) < 6 * ROW_H, "no room below"
    panel = form.open()
    x, y, w, h = panel.panel_rect
    assert y + h == pytest.approx(field[1]), "flipped: its bottom on the field's top"
    assert _inside(panel.panel_rect, (0, 0, 300, 260))
    assert panel.max_scroll == 0.0, "all of it fits above"


def test_a_list_with_room_on_neither_side_is_shifted_to_fit():
    options = [f"option {i}" for i in range(9)]       # ~210 px in a 260 px frame
    form = Form(Model(options), _spec(above=4), size=(300.0, 260.0))
    field = form.state.rects["pick"]
    panel = form.open()
    x, y, w, h = panel.panel_rect
    assert h > field[1] and h > 260.0 - (field[1] + field[3]), "fits neither side"
    assert _inside(panel.panel_rect, (0, 0, 300, 260))
    assert panel.max_scroll == 0.0, "shifted, whole, not scrolled"


def test_a_long_list_is_capped_to_the_frame_and_scrolls():
    options = [f"parameter {i:03d}" for i in range(200)]
    form = Form(Model(options, value="parameter 150"), _spec(above=2))
    panel = form.open()
    assert _inside(panel.panel_rect, (0, 0, 400, 300))
    assert panel.panel_rect[3] == pytest.approx(300.0)
    assert panel.max_scroll > 0.0
    view = panel.view_rect
    row = panel.row_rect(150)
    assert view[1] <= row[1] and row[1] + row[3] <= view[1] + view[3], "current row in view"
    assert "parameter 150" in form.painter.strings
    assert "parameter 000" not in form.painter.strings, "rows out of view are not drawn"
    # The wheel scrolls the list ...
    before = panel.scroll
    form.wheel(view[0] + 20.0, view[1] + 40.0, 2.0)
    assert panel.scroll == pytest.approx(before - 2 * menus.WHEEL_ROWS * ROW_H)
    # ... and the scrollbar's thumb drags it to the top.
    form.frame()
    bar = panel._thumb
    io = form.io
    io.mouse_pos = io.mouse_clicked_pos[0] = (bar[0] + 2.0, bar[1] + 2.0)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    form.frame()
    io.mouse_pos = (bar[0] + 2.0, -500.0)
    form.frame()
    io.mouse_down[0], io.mouse_released[0] = False, True
    form.frame()
    assert panel.scroll == 0.0
    assert panel.open, "a scrollbar drag is not a pick"
    assert form.model.pick == "parameter 150"


def test_the_keyboard_moves_picks_and_closes():
    options = ["alpha", "beta", "gamma", "delta"]
    model = Model(options, value="beta")
    form = Form(model, _spec())
    panel = form.open()
    assert panel.highlight == 1
    form.key(KEY_DOWN)
    form.key(KEY_DOWN)
    assert panel.highlight == 3
    form.key(KEY_UP)
    form.key(KEY_ENTER)
    assert not panel.open
    form.frame()
    assert model.pick == "gamma"
    panel = form.open()
    form.key(KEY_ESCAPE)
    assert not panel.open
    form.frame()
    assert model.pick == "gamma"


def test_typing_jumps_to_the_first_item_that_starts_with_it():
    options = ["Alpha", "Rate", "Ratio green", "Ratio red", "Red", "Tau"]
    form = Form(Model(options), _spec())
    panel = form.open()
    clock = [0.0]
    panel.clock = lambda: clock[0]
    form.key(ord("R"), "r")
    assert panel.highlight == 1                        # "Rate"
    clock[0] += 0.2
    form.key(ord("A"), "a")
    clock[0] += 0.2
    form.key(ord("T"), "t")
    clock[0] += 0.2
    form.key(ord("I"), "i")
    assert panel.highlight == 2                        # "Rati" -> "Ratio green"
    clock[0] += 5.0                                    # a pause starts a new search
    form.key(ord("T"), "t")
    assert panel.highlight == 5
    clock[0] += 5.0
    form.key(ord("R"), "r")
    clock[0] += 0.2
    form.key(ord("R"), "r")                            # the same letter again: the next
    assert panel.highlight == 2
    form.key(KEY_ENTER)
    form.frame()
    assert form.model.pick == "Ratio green"


def test_a_click_on_an_item_picks_it():
    options = ["one", "two", "three"]
    model = Model(options)
    form = Form(model, _spec())
    panel = form.open()
    x, y, w, h = panel.row_rect(2)
    form.click(x + w / 2.0, y + h / 2.0)
    assert not panel.open
    assert model.pick == "three"
    assert form.panel() is None


def test_a_click_outside_closes_the_list_and_reaches_nothing_behind():
    model = Model(["one", "two"])
    form = Form(model, _spec(button_above=True))
    panel = form.open()
    bx, by, bw, bh = form.state.rects["press"]
    px, py = bx + bw - 5.0, by + bh / 2.0
    assert not panel.contains(px, py)
    form.click(px, py)
    assert not panel.open
    assert model.presses == 0, "the click that closed the list pressed the button"
    assert model.pick == "one"
    form.click(px, py)
    assert model.presses == 1, "closed, the form takes clicks again"


def test_a_click_on_the_field_again_closes_its_list():
    form = Form(Model(["one", "two"]), _spec())
    panel = form.open()
    x, y, w, h = form.state.rects["pick"]
    form.click(x + 5.0, y + h / 2.0)
    assert not panel.open and form.panel() is None


def test_the_form_under_an_open_list_sees_no_pointer_wheel_or_keys():
    options = [f"p{i}" for i in range(200)]
    seen = []
    spec = _spec()
    spec["sections"].append({"type": "custom", "key": "probe"})
    form = Form(Model(options), spec)
    form.state.custom["probe"] = lambda *a: seen.append(
        (tuple(emtk.get_io().mouse_pos), emtk.get_io().mouse_wheel, emtk.get_io().key))
    panel = form.open()
    assert form.io.want_capture_mouse
    view = panel.view_rect
    before = panel.scroll
    seen.clear()
    form.io.key = KEY_DOWN
    form.wheel(view[0] + 5.0, view[1] + 5.0, -1.0)
    assert seen == [((-1.0, -1.0), 0.0, 0)], "the frame under the list saw the input"
    assert panel.scroll > before, "the list got the wheel"
    assert form.io.mouse_pos == (view[0] + 5.0, view[1] + 5.0), "the host's pointer is kept"


def test_emtk_combo_opens_the_same_list():
    """The ImGui-style combo: a click opens the list, a pick is the change."""
    io, storage = emtk.IO(), {}
    items = [f"item {i}" for i in range(100)]
    state = {"current": 3, "changed": []}

    def frame():
        painter = RecordingPainter()
        with emtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=io, storage=storage):
            emtk.set_next_item_width(60.0)
            changed, state["current"] = emtk.combo("##c", state["current"], items)
            state["rect"] = emtk.get_item_rect()
            state["changed"].append(changed)
        return painter

    def click(x, y):
        io.mouse_pos = io.mouse_clicked_pos[0] = (x, y)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        frame()
        io.mouse_down[0], io.mouse_released[0] = False, True
        return frame()

    frame()
    x, y = state["rect"][0] + 3.0, state["rect"][1] + 3.0
    painter = click(x, y)
    assert state["current"] == 3, "a click opens the list; it does not step"
    row = next(t for t in reversed(painter.texts) if t[5] == "item 5")
    assert row[1] < 200.0
    assert "item 3" in painter.strings[-40:], "the current item is in view"
    click(row[0] + 2.0, row[1] + row[3] / 2.0)
    frame()
    assert state["current"] == 5 and any(state["changed"])


# --------------------------------------------------------------------------- #
# Context menus: the same placement and scrolling
# --------------------------------------------------------------------------- #
def test_a_tall_context_menu_is_capped_and_scrolls():
    painter = RecordingPainter()
    popup = menus.Popup([menus.MenuItem(f"Action {i}") for i in range(60)])
    popup.open_at(50.0, 80.0)
    popup.draw(painter, 0.0, 0.0, 300.0, 200.0)
    assert _inside(popup.panel_rect, (0, 0, 300, 200))
    assert popup.max_scroll > 0.0
    popup.wheel(60.0, 100.0, -1.0)
    assert popup.scroll == pytest.approx(menus.WHEEL_ROWS * ROW_H)
    popup.key(KEY_DOWN)
    popup.draw(painter, 0.0, 0.0, 300.0, 200.0)
    view, row = popup.view_rect, popup.row_rect(popup.highlight)
    assert view[1] <= row[1] and row[1] + row[3] <= view[1] + view[3]


def test_a_context_menu_through_the_overlay_layer_picks_and_closes():
    io, storage = emtk.IO(), {}
    items = [menus.MenuItem("Copy"), None, menus.MenuItem("Paste")]
    popup = menus.Popup(items)
    popup.open_at(40.0, 40.0)
    picked = []

    def frame():
        painter = RecordingPainter()
        with emtk.frame(painter, (0.0, 0.0, 300.0, 200.0), io=io, storage=storage):
            item = emtk.overlays.popup("menu", popup)
            if item is not None:
                picked.append(item.label)
        return painter

    frame()
    frame()
    x, y, w, h = popup.row_rect(2)
    io.mouse_pos = io.mouse_clicked_pos[0] = (x + 4.0, y + h / 2.0)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    frame()
    io.mouse_down[0] = False
    frame()
    assert picked == ["Paste"] and not popup.open


# --------------------------------------------------------------------------- #
# HiDPI: logical coordinates in, the ratio applied once
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def device():
    pytest.importorskip("numpy")
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


@pytest.mark.parametrize("ratio", [1.0, 2.0])
def test_the_list_is_drawn_and_hit_in_logical_pixels_at_every_ratio(device, ratio):
    import numpy as np
    from rendercanvas.offscreen import RenderCanvas

    from emtk.app import ImApp
    from emtk.native import NativeHost

    options = [f"channel {i}" for i in range(40)]
    model = Model(options, value="channel 20")
    form_state = FormState()
    spec = _spec(width=70)

    def gui():
        draw_form(spec, model, form_state, titles=False)

    app = ImApp(gui)
    host = NativeHost(app, canvas=RenderCanvas(size=(320, 240), pixel_ratio=ratio),
                      device=device)
    host.draw_frame()

    def click(x, y):
        event = {"x": x, "y": y, "button": 1, "buttons": (1,), "modifiers": ()}
        host.events._on_pointer_down(dict(event, event_type="pointer_down"))
        host.draw_frame()
        host.events._on_pointer_up(dict(event, event_type="pointer_up", buttons=()))
        return np.asarray(host.draw_frame())[..., :3].astype(float)

    fx, fy, fw, fh = form_state.rects["pick"]
    image = click(fx + 5.0, fy + fh / 2.0)
    panel = next(v["panel"] for k, v in app.storage.items()
                 if isinstance(k, tuple) and k[0] == "__state__"
                 and isinstance(k[1], tuple) and k[1][0] == "overlay.combo")
    px, py, pw, ph = panel.panel_rect
    assert image.shape[:2] == (240 * ratio, 320 * ratio)
    assert _inside(panel.panel_rect, (0, 0, 320, 240)), "inside the logical frame"
    assert pw > fw, "wider than the 70 px field"
    # The panel is where its logical rect says, in device pixels: its fill
    # differs from the frame's background just outside it.
    inside = image[int((py + ph / 2) * ratio), int((px + pw / 2) * ratio)]
    outside = image[int((py + ph / 2) * ratio), min(int((px + pw + 6) * ratio), 320 * int(ratio) - 1)]
    assert np.abs(inside - outside).max() > 3.0
    row = panel.row_rect(22)
    click(row[0] + row[2] / 2.0, row[1] + row[3] / 2.0)
    host.draw_frame()
    assert model.pick == "channel 22"
