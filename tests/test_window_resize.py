"""Resizing windows from every edge and corner, and folding them by the title.

Floating dock windows (:mod:`emtk.docking`) and dialog windows
(:mod:`emtk.dialog_window`) are driven through the real event path -- pointer
events into an app, a frame drawn after each -- with the frame clock
(``io.wall_clock`` off), so a loaded machine cannot change what a gesture means.
"""
from __future__ import annotations

import json

import pytest

import emtk
from emtk import im
from emtk.app import ImApp, mouse_cursor
from emtk.dialog_window import DialogWindow
from emtk.docking import (
    CORNER,
    EDGE,
    GRIP,
    TOP_EDGE,
    DockManager,
    Region,
    Split,
    anchor_of,
    resize_frame,
    resize_zones,
)
from emtk.events import LEFT_BUTTON
from emtk.testing import RecordingPainter

BOX = (0.0, 0.0, 1000.0, 700.0)
ORIGIN = (600.0, 100.0, 240.0, 150.0)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("zone, expected", [
    ("n", (600.0, 80.0, 240.0, 170.0)),
    ("s", (600.0, 100.0, 240.0, 130.0)),
    ("e", (600.0, 100.0, 210.0, 150.0)),
    ("w", (570.0, 100.0, 270.0, 150.0)),
    ("nw", (570.0, 80.0, 270.0, 170.0)),
    ("ne", (600.0, 80.0, 210.0, 170.0)),
    ("sw", (570.0, 100.0, 270.0, 130.0)),
    ("se", (600.0, 100.0, 210.0, 130.0)),
])
def test_each_zone_moves_only_its_own_edges(zone, expected):
    assert resize_frame(zone, ORIGIN, -30.0, -20.0, (80.0, 40.0), BOX) == expected


def test_a_too_small_drag_from_the_left_or_top_keeps_the_opposite_edge():
    x, y, w, h = resize_frame("nw", ORIGIN, 500.0, 500.0, (80.0, 40.0), BOX)
    assert (w, h) == (80.0, 40.0)
    assert (x + w, y + h) == (840.0, 250.0)           # right and bottom stayed


def test_edges_stay_in_the_bounds_and_snap_flush():
    x, _y, w, _h = resize_frame("e", ORIGIN, 400.0, 0.0, (80.0, 40.0), BOX)
    assert x + w == 1000.0                              # clamped at the bound
    x, _y, w, _h = resize_frame("e", ORIGIN, 150.0, 0.0, (80.0, 40.0), BOX, snap=14.0)
    assert x + w == 1000.0                              # 990 snaps to 1000
    other = (300.0, 100.0, 200.0, 100.0)
    x, *_ = resize_frame("w", ORIGIN, -92.0, 0.0, (80.0, 40.0), BOX, [other], snap=14.0)
    assert x == 500.0                                   # flush to the other window
    x, *_ = resize_frame("w", ORIGIN, -92.0, 0.0, (80.0, 40.0), BOX, [other], snap=0.0)
    assert x == 508.0                                   # no snapping asked for


def test_the_zones_lie_inside_the_frame_and_a_folded_frame_has_only_sides():
    zones = resize_zones(ORIGIN)
    assert set(zones) == {"n", "s", "e", "w", "ne", "nw", "se", "sw"}
    x, y, w, h = ORIGIN
    for rects in zones.values():
        for rx, ry, rw, rh in rects:
            assert x <= rx and y <= ry and rx + rw <= x + w and ry + rh <= y + h
    assert zones["n"][0][3] == TOP_EDGE and zones["w"][0][2] == EDGE
    assert zones["se"][0][2:] == (GRIP, GRIP) and zones["nw"][0][2] == CORNER
    assert set(resize_zones((0.0, 0.0, 200.0, 20.0), folded=True)) == {"w", "e"}


def test_anchor_of_names_the_edges_a_frame_is_flush_with():
    assert anchor_of((800.0, 0.0, 200.0, 100.0), BOX) == "top-right"
    assert anchor_of((0.0, 300.0, 200.0, 100.0), BOX) == "left"
    assert anchor_of((10.0, 300.0, 200.0, 100.0), BOX) is None


# --------------------------------------------------------------------------- #
# Floating dock windows
# --------------------------------------------------------------------------- #
class Driver:
    def __init__(self, docks: DockManager, box=BOX) -> None:
        self.docks, self.box = docks, box
        self.app = ImApp(lambda: docks.draw(self.box))
        self.app.io.wall_clock = False
        self.frame()

    def frame(self):
        self.app.draw(RecordingPainter(), *self.box)

    def press(self, x, y, clicks=1):
        self.app.pointer_press(x, y, LEFT_BUTTON, 0, clicks)
        self.frame()

    def hover(self, x, y):
        self.app.pointer_move(x, y, 0, 0)
        self.frame()

    def move(self, x, y):
        self.app.pointer_move(x, y, LEFT_BUTTON, 0)
        self.frame()

    def release(self, x, y):
        self.app.pointer_release(x, y, LEFT_BUTTON)
        self.frame()
        self.frame()

    def drag(self, start, end):
        self.press(*start)
        self.move(*end)
        self.release(*end)


def make(**window):
    docks = DockManager(Split("h", 0.3, Region("left"), Region("center")))
    docks.add_window("plot", "Plot", lambda _b: None, dock="center")
    docks.add_window("notes", "Notes", lambda _b: im.text("notes"), box=ORIGIN, **window)
    docks.add_window("log", "Log", lambda _b: None, box=(100.0, 450.0, 240.0, 150.0))
    return docks


def point_in(zone, frame, th):
    x, y, w, h = frame
    return {"n": (x + w / 2.0, y + 1.0), "s": (x + w / 2.0, y + h - 2.0),
            "w": (x + 2.0, y + h / 2.0), "e": (x + w - 2.0, y + h / 2.0),
            "nw": (x + 1.0, y + 1.0), "ne": (x + w - 1.0, y + 1.0),
            "sw": (x + 2.0, y + h - 2.0), "se": (x + w - 3.0, y + h - 3.0)}[zone]


@pytest.mark.parametrize("zone", ["n", "s", "e", "w", "nw", "ne", "sw", "se"])
def test_every_edge_and_corner_of_a_floating_window_resizes_it(zone):
    docks = make()
    host = Driver(docks)
    frame = docks.window("notes").frame
    start = point_in(zone, frame, docks._title_h)
    host.drag(start, (start[0] - 30.0, start[1] - 20.0))
    assert docks.window("notes").frame == resize_frame(zone, frame, -30.0, -20.0,
                                                       (80.0, 40.0), BOX)


@pytest.mark.parametrize("zone, shape", [("n", 3), ("s", 3), ("e", 4), ("w", 4),
                                         ("ne", 5), ("sw", 5), ("nw", 6), ("se", 6)])
def test_the_pointer_takes_the_resize_shape_of_the_zone(zone, shape):
    docks = make()
    host = Driver(docks)
    host.hover(*point_in(zone, docks.window("notes").frame, docks._title_h))
    assert host.app.io.mouse_cursor == shape
    assert mouse_cursor(host.app) in {3: "ns-resize", 4: "ew-resize", 5: "nesw-resize",
                                      6: "nwse-resize"}[shape]
    host.hover(500.0, 650.0)                       # off every window: the arrow again
    assert host.app.io.mouse_cursor == 0 and mouse_cursor(host.app) == "default"


def test_left_resize_respects_the_minimum_and_keeps_the_right_edge():
    docks = make()
    host = Driver(docks)
    x, y, w, h = docks.window("notes").frame
    start = point_in("w", (x, y, w, h), docks._title_h)
    host.drag(start, (start[0] + 400.0, start[1]))
    fx, _fy, fw, _fh = docks.window("notes").frame
    assert fx + fw == x + w and fw == docks.window("notes").min_size[0]


def test_a_resize_to_the_edge_snaps_and_anchors_and_then_follows_the_edge():
    docks = make()
    host = Driver(docks)
    start = point_in("e", docks.window("notes").frame, docks._title_h)
    host.drag(start, (990.0, start[1]))
    x, _y, w, _h = docks.window("notes").frame
    assert x + w == 1000.0 and docks.window("notes").anchor == "right"
    host.box = (0.0, 0.0, 1200.0, 700.0)
    host.frame()
    host.frame()
    x, _y, w, _h = docks.window("notes").frame
    assert x + w == 1200.0


def test_the_title_still_drags_and_the_close_button_still_closes():
    docks = make()
    host = Driver(docks)
    x, y, w, _h = docks.window("notes").frame
    th = docks._title_h
    host.drag((x + 60.0, y + th / 2.0), (x + 10.0, y + th / 2.0 + 100.0))
    assert docks.window("notes").frame[:2] == (x - 50.0, y + 100.0)
    x, y, w, _h = docks.window("notes").frame
    host.press(x + w - th / 2.0, y + th / 2.0)
    host.release(x + w - th / 2.0, y + th / 2.0)
    assert not docks.is_visible("notes")


def test_a_double_click_on_the_title_folds_and_a_second_unfolds_at_the_same_height():
    docks = make()
    host = Driver(docks)
    x, y, w, h = docks.window("notes").frame
    th = docks._title_h
    title = (x + 60.0, y + th / 2.0)
    host.press(*title)
    host.release(*title)
    host.press(*title, clicks=2)
    host.release(*title)
    assert docks.window("notes").collapsed and docks.window("notes").frame == (x, y, w, th)
    host.press(*title)
    host.release(*title)
    host.press(*title, clicks=2)
    host.release(*title)
    assert not docks.window("notes").collapsed
    assert docks.window("notes").frame == (x, y, w, h)


def test_a_double_click_on_a_title_button_does_not_fold():
    pressed = []
    docks = make(title_buttons=[("Code", lambda: pressed.append(1), "")])
    host = Driver(docks)
    bx, by, bw, bh = docks.window("notes").title_button_rects[0]
    centre = (bx + bw / 2.0, by + bh / 2.0)
    host.press(*centre)
    host.release(*centre)
    host.press(*centre, clicks=2)
    host.release(*centre)
    assert pressed and not docks.window("notes").collapsed


def test_a_folded_window_resizes_sideways_only_and_unfolds_at_its_height():
    docks = make()
    host = Driver(docks)
    x, y, w, h = docks.window("notes").frame
    th = docks._title_h
    docks.window("notes").collapsed = True
    host.frame()
    host.hover(x + w - 2.0, y + th / 2.0)
    assert host.app.io.mouse_cursor == 4
    host.drag((x + w - 2.0, y + th / 2.0), (x + w + 58.0, y + th / 2.0 + 80.0))
    assert docks.window("notes").frame == (x, y, w + 60.0, th)
    host.hover(x + w / 2.0, y + th - 1.0)          # no bottom edge while folded
    assert host.app.io.mouse_cursor != 3
    docks.window("notes").collapsed = False
    host.frame()
    assert docks.window("notes").frame == (x, y, w + 60.0, h)


def test_the_fold_state_survives_a_saved_layout():
    docks = make()
    Driver(docks)
    docks.window("notes").collapsed = True
    text = json.dumps(docks.state())
    again = make()
    again.restore(json.loads(text))
    assert again.window("notes").collapsed


# --------------------------------------------------------------------------- #
# Dialog windows
# --------------------------------------------------------------------------- #
FRAME = (0.0, 0.0, 800.0, 600.0)


class DialogHost:
    def __init__(self, window, buttons=("Help",)):
        self.window, self.buttons = window, buttons
        self.io, self.storage = emtk.IO(), {}
        self.io.wall_clock = False
        self.pressed = []
        self.frame()

    def frame(self):
        with emtk.frame(RecordingPainter(), FRAME, io=self.io, storage=self.storage):
            got = self.window.begin(FRAME, buttons=self.buttons)
            emtk.text("content")
            self.window.end()
        self.pressed.append(got)
        for edge in ("mouse_clicked", "mouse_released", "mouse_double_clicked"):
            getattr(self.io, edge)[0] = False
        return got

    def press(self, x, y, double=False):
        self.io.mouse_pos = self.io.mouse_clicked_pos[0] = (x, y)
        self.io.mouse_down[0] = self.io.mouse_clicked[0] = True
        self.io.mouse_double_clicked[0] = double
        self.frame()

    def move(self, x, y):
        self.io.mouse_pos = (x, y)
        self.frame()

    def release(self):
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        return self.frame()

    def drag(self, start, end):
        self.press(*start)
        self.move(*end)
        self.release()


@pytest.mark.parametrize("zone", ["n", "s", "e", "w", "nw", "ne", "sw", "se"])
def test_every_edge_and_corner_of_a_dialog_resizes_it(zone):
    host = DialogHost(DialogWindow("Tool", size=(300, 200)))
    box = host.window.box
    start = point_in(zone, box, DialogWindow.HEADER_H)
    host.drag(start, (start[0] - 30.0, start[1] - 20.0))
    host.frame()
    assert host.window.box == resize_frame(zone, box, -30.0, -20.0, (160.0, 80.0), FRAME)


def test_a_dialog_shows_the_resize_pointer_and_keeps_its_minimum():
    host = DialogHost(DialogWindow("Tool", size=(300, 200)))
    x, y, w, h = host.window.box
    host.move(x + w - 2.0, y + h / 2.0)
    assert host.io.mouse_cursor == 4
    host.drag((x + 2.0, y + h / 2.0), (x + 400.0, y + h / 2.0))
    host.frame()
    bx, _by, bw, _bh = host.window.box
    assert bw == 160.0 and bx + bw == x + w


def test_a_dialog_header_double_click_folds_it_and_the_content_is_inert():
    host = DialogHost(DialogWindow("Tool", size=(300, 200)))
    x, y, w, h = host.window.box
    header = (x + 40.0, y + 10.0)
    host.press(*header)
    host.release()
    host.press(*header, double=True)
    host.release()
    assert host.window.folded and host.window.box == (x, y, w, DialogWindow.HEADER_H)
    assert host.window.content_box[3] == 0.0
    host.press(*header)
    host.release()
    host.press(*header, double=True)
    host.release()
    assert not host.window.folded and host.window.box == (x, y, w, h)


def test_a_double_click_on_a_dialog_header_button_does_not_fold():
    host = DialogHost(DialogWindow("Tool", size=(300, 200)))
    x, y, w, _h = host.window.box
    # The rightmost header button is the close ×; Help sits before it.
    host.frame()
    help_x = x + w - 60.0
    host.press(help_x, y + 8.0)
    host.release()
    host.press(help_x, y + 8.0, double=True)
    host.release()
    assert not host.window.folded


def test_a_folded_or_fitted_dialog_resizes_sideways_only():
    host = DialogHost(DialogWindow("Note", size=(300, 160), fit_height=True))
    host.frame()                                    # the height fits the content first
    x, y, w, h = host.window.box
    host.move(x + w / 2.0, y + h - 2.0)
    assert host.io.mouse_cursor != 3                # no bottom edge: the height fits itself
    host.drag((x + w - 2.0, y + h / 2.0), (x + w + 48.0, y + h / 2.0 + 60.0))
    host.frame()
    assert host.window.box[2] == w + 50.0 and host.window.box[1] == y
