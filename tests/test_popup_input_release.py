"""A popup that has closed, by whatever path, gives the input back.

A context menu or a list holds its frame's input while it is up
(:mod:`emtk.overlays`). These are the ways that hold outlived the popup -- a
user right-clicked a plot, chose an item, and no click landed anywhere after:

* a submenu row (:class:`~emtk.widgets.menus.Menu`) raised when highlighted
  (it had no ``tooltip``), so the popup failed in every frame after the
  pointer crossed it -- drawn, never closed, holding every click;
* an overlay that raises left ``__overlays_open__`` as it was, open;
* a hosted frame never saw the press outside it that should close its menu
  (:func:`emtk.overlays.dismiss` is how its host tells it).

And a row with a whole sentence in it made the menu as wide as the window:
it is cut to :data:`~emtk.widgets.menus.MAX_LABEL_LINES` and shown whole in a
tooltip.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import overlays
from emtk.app import ImApp
from emtk.events import RIGHT_BUTTON
from emtk.keys import KEY_ESCAPE
from emtk.testing import RecordingPainter
from emtk.testing_realistic import RealisticDriver, assert_input_released, held_overlays
from emtk.widgets import menus
from emtk.widgets.menus import Menu, MenuItem, Popup

LONG = ("Send selection to — This table has no burst provenance: First File, First Photon, "
        "Last Photon missing, so the photons of a burst cannot be found again")


class Frame:
    """A window with a button, and a context menu on a right-click anywhere else."""

    def __init__(self, entries, size=(800.0, 500.0)):
        self.entries, self.size = entries, size
        self.io, self.storage = emtk.IO(), {}
        self.popup = None
        self.picked, self.presses = [], 0
        self.button_rect = None
        self.frame()

    def frame(self):
        w, h = self.size
        with emtk.frame(RecordingPainter(), (0.0, 0.0, w, h), io=self.io, storage=self.storage):
            emtk.begin("win", (0.0, 0.0, w, h))
            if emtk.button("Press"):
                self.presses += 1
            self.button_rect = emtk.get_item_rect()
            emtk.end()
            if self.io.mouse_clicked[1] and self.popup is None:
                self.popup = Popup(list(self.entries))
                self.popup.open_at(*self.io.mouse_pos)
            if self.popup is not None and not self.popup.open:
                self.popup = None
            if self.popup is not None:
                overlays.popup("menu", self.popup, on_pick=self.picked.append)
        io = self.io
        for i in range(3):
            io.mouse_clicked[i] = io.mouse_released[i] = False
        io.key, io.text, io.key_events = 0, "", []
        io.mouse_wheel = 0.0

    def click(self, x, y, button=0):
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[button] = (float(x), float(y))
        io.mouse_down[button] = io.mouse_clicked[button] = True
        self.frame()
        io.mouse_down[button], io.mouse_released[button] = False, True
        self.frame()
        self.frame()

    def hover(self, x, y):
        self.io.mouse_pos = (float(x), float(y))
        self.frame()

    def press_button(self):
        x, y, w, h = self.button_rect
        before = self.presses
        self.click(x + w / 2.0, y + h / 2.0)
        return self.presses == before + 1

    def row_centre(self, index):
        x, y, w, h = self.popup.row_rect(index)
        return x + w / 2.0, y + h / 2.0


def _entries():
    send = Menu(LONG, [MenuItem("Burst analysis")], enabled=False,
                tooltip="This table has no burst provenance.")
    return [MenuItem("Copy"), MenuItem("Disabled", enabled=False), None, send]


def test_a_highlighted_submenu_row_draws_and_shows_its_tooltip():
    f = Frame(_entries())
    f.click(400.0, 300.0, button=1)
    assert f.popup is not None
    f.hover(*f.row_centre(3))
    assert f.popup is not None and f.popup.open, "the menu fell over on its submenu row"
    assert f.popup.tooltip == "This table has no burst provenance."
    assert not overlays.holding(f.storage) or f.popup.open
    f.click(*f.row_centre(0))
    assert [item.label for item in f.picked] == ["Copy"]
    assert not held_overlays(f.storage)
    assert f.press_button()


def test_a_long_row_is_cut_to_the_menu_width_and_shown_whole():
    p = RecordingPainter()
    cap = p.line_height() * menus.MAX_LABEL_LINES
    width, _height = Popup([MenuItem(LONG, enabled=False)]).panel_size(p)
    assert p.text_width(LONG) > cap
    assert width < cap + 10.0 * p.line_height(), "one long row made the whole menu as wide"
    f = Frame([MenuItem("Copy"), MenuItem(LONG, enabled=False)], size=(1600.0, 500.0))
    f.click(10.0, 300.0, button=1)
    x, _y, w, _h = f.popup.panel_rect
    assert w < 1600.0 * 0.6
    f.hover(*f.row_centre(1))
    assert f.popup.tooltip == LONG


@pytest.mark.parametrize("path", ["item", "escape", "click_outside", "right_click_again",
                                  "wheel_then_escape", "disabled_then_escape"])
def test_after_the_menu_closes_the_next_click_lands(path):
    f = Frame(_entries())
    f.click(400.0, 300.0, button=1)
    assert f.popup is not None
    if path == "item":
        f.click(*f.row_centre(0))
    elif path == "escape":
        f.io.key = KEY_ESCAPE
        f.frame()
    elif path == "click_outside":
        f.click(700.0, 450.0)
    elif path == "right_click_again":
        f.click(700.0, 450.0, button=1)
    elif path == "wheel_then_escape":
        f.io.mouse_pos = f.row_centre(0)
        f.io.mouse_wheel = -1.0
        f.frame()
        f.io.key = KEY_ESCAPE
        f.frame()
    elif path == "disabled_then_escape":
        f.click(*f.row_centre(1))
        assert f.popup is not None and f.popup.open, "a disabled row is inert"
        f.io.key = KEY_ESCAPE
        f.frame()
    f.frame()
    assert f.popup is None
    assert not held_overlays(f.storage)
    assert f.press_button(), f"{path}: the click after the menu closed did not land"


def test_a_popup_that_raises_is_closed_and_gives_the_input_back(caplog):
    f = Frame(_entries())
    f.click(400.0, 300.0, button=1)

    def broken(*_a, **_k):
        raise RuntimeError("a row that cannot draw")

    f.popup.draw = broken
    f.frame()
    assert not held_overlays(f.storage)
    assert f.press_button()
    assert "failed to draw" in caplog.text


def test_an_overlay_that_raises_does_not_hold_the_next_frame():
    io, storage = emtk.IO(), {}

    def draw(ctx):
        raise RuntimeError("broken overlay")

    with emtk.frame(RecordingPainter(), (0.0, 0.0, 300.0, 200.0), io=io, storage=storage) as ctx:
        ctx.add_overlay("bad", draw)
    assert storage["__overlays_open__"] == []


def test_dismiss_closes_the_menu_of_a_frame_the_press_never_reached():
    """What a host does for its hosted frames: the press went to another one."""
    f = Frame(_entries())
    f.click(400.0, 300.0, button=1)
    assert overlays.open_panels(f.storage)
    assert overlays.dismiss(f.storage) == 1
    assert not held_overlays(f.storage)
    assert f.press_button(), "the first click after the host closed the menu was eaten"
    assert overlays.dismiss(f.storage) == 0
    assert overlays.dismiss(None) == 0


def test_assert_input_released_names_what_still_holds_the_input():
    state = {"menu": None, "presses": 0}

    def gui():
        if emtk.button("Press"):
            state["presses"] += 1
        io = emtk.get_io()
        if io.mouse_clicked[1] and state["menu"] is None:
            state["menu"] = Popup(_entries())
            state["menu"].open_at(*io.mouse_pos)
        if state["menu"] is not None and not state["menu"].open:
            state["menu"] = None
        if state["menu"] is not None:
            overlays.popup("m", state["menu"])

    app = ImApp(gui)
    driver = RealisticDriver(app, (600, 400), real_painter=False)
    driver.frame(2)
    driver.click((400.0, 300.0), button=RIGHT_BUTTON)
    assert held_overlays(app)
    with pytest.raises(AssertionError, match="still held"):
        assert_input_released(driver, "Press", lambda: state["presses"] == 1, label="open")
    driver.press(KEY_ESCAPE)
    assert_input_released(driver, "Press", lambda: state["presses"] == 1, label="escape")


def test_a_nested_frame_whose_end_raises_gives_the_host_its_context_back(monkeypatch):
    """A hosted frame that fails at its end must not stay current for its host."""
    from emtk import im_core

    outer_io, inner_io = emtk.IO(), emtk.IO()
    with emtk.frame(RecordingPainter(), (0.0, 0.0, 300.0, 200.0), io=outer_io) as outer:
        def broken_end(self):
            raise RuntimeError("end of the child frame")

        with monkeypatch.context() as patch:
            patch.setattr(im_core.Context, "end_frame", broken_end)
            with pytest.raises(RuntimeError):
                with emtk.frame(RecordingPainter(), (0.0, 0.0, 100.0, 100.0), io=inner_io):
                    pass
        assert im_core.get_current_context() is outer


def test_escape_closes_a_plot_context_menu_and_the_next_click_lands():
    """implot's right-click menu is a window, not an overlay: Escape closed it nowhere."""
    from emtk import implot

    io, storage, state = emtk.IO(), {}, {"presses": 0, "plot": None, "button": None}
    io.wall_clock = False

    def frame():
        with emtk.frame(RecordingPainter(), (0.0, 0.0, 600.0, 420.0), io=io, storage=storage):
            emtk.begin("w")
            if emtk.button("Press"):
                state["presses"] += 1
            state["button"] = emtk.get_item_rect()
            if implot.begin_plot("p", (400.0, 300.0)):
                implot.plot_line("y", [0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
                state["plot"] = implot.get_plot_pos(), implot.get_plot_size()
                implot.end_plot()
            emtk.end()
        for k in range(3):
            io.mouse_clicked[k] = io.mouse_released[k] = False
        io.key, io.key_events = 0, []

    def click(x, y, button=0):
        io.mouse_pos = (float(x), float(y))
        frame()
        io.mouse_down[button] = io.mouse_clicked[button] = True
        io.mouse_clicked_pos[button] = (float(x), float(y))
        frame()
        io.mouse_down[button], io.mouse_released[button] = False, True
        frame()
        frame()

    try:
        frame()
        (px, py), (pw, ph) = state["plot"]
        click(px + pw / 2.0, py + ph / 2.0, button=1)
        assert implot._cur.last_plot.context_menu is not None
        io.key = KEY_ESCAPE
        frame()
        frame()
        assert implot._cur.last_plot.context_menu is None, "Escape left the plot's menu up"
        bx, by, bw, bh = state["button"]
        click(bx + bw / 2.0, by + bh / 2.0)
        assert state["presses"] == 1
    finally:
        implot._cur.plot = None
        implot._cur.pending_popups = []


def test_a_plot_menu_opened_near_the_corner_stays_inside_the_window():
    """The sweep found plot menus running out of the window at the right and bottom edges."""
    from emtk import implot

    io, storage = emtk.IO(), {}
    io.wall_clock = False
    size = (400.0, 300.0)

    def frame():
        with emtk.frame(RecordingPainter(), (0.0, 0.0, *size), io=io, storage=storage):
            emtk.begin("w", (0.0, 0.0, *size))
            if implot.begin_plot("p", (-1.0, -1.0)):
                implot.plot_line("y", [0.0, 1.0, 2.0], [0.0, 1.0, 0.0])
                implot.end_plot()
            emtk.end()
        for k in range(3):
            io.mouse_clicked[k] = io.mouse_released[k] = False

    try:
        frame()
        plot = implot._cur.last_plot
        x0, y0, x1, y1 = plot.plot_rect
        corner = (x1 - 8.0, y1 - 8.0)
        io.mouse_pos = corner
        frame()
        io.mouse_down[1] = io.mouse_clicked[1] = True
        io.mouse_clicked_pos[1] = corner
        frame()
        io.mouse_down[1], io.mouse_released[1] = False, True
        for _ in range(3):
            frame()
        menu = implot._cur.last_plot.context_menu
        assert menu is not None
        (mx, my), (mw, mh) = menu["pos"], menu["size"]
        assert 0.0 <= mx and mx + mw <= size[0] + 0.5, (mx, mw)
        assert 0.0 <= my and my + mh <= size[1] + 0.5, (my, mh)
    finally:
        implot._cur.plot = None
        implot._cur.pending_popups = []
