"""emtk.docking: sticky windows and dock regions.

Driven the way a host drives an app -- pointer events into an
:class:`~emtk.app.ImApp`, one frame drawn after each -- so what is tested is
the gesture, not a setter. The geometry functions (moved here from a viewer's
in-viewport chrome) are pinned on their own first.
"""
from __future__ import annotations

import json

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.docking import (
    DockManager,
    LayoutStore,
    Region,
    Split,
    WindowDrag,
    anchored_position,
    frames_touch,
    snap,
    snap_to_frames,
    stuck_group,
)
from emtk.events import LEFT_BUTTON, SHIFT_MODIFIER
from emtk.testing import RecordingPainter

BOX = (0.0, 0.0, 1000.0, 700.0)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_snap_lands_flush_on_a_near_edge_and_anchors_there():
    assert snap(8.0, 300.0, 100.0, 80.0, 1000.0, 700.0) == (0.0, 300.0, "left")
    x, y, anchor = snap(893.0, 612.0, 100.0, 80.0, 1000.0, 700.0)
    assert (x, y, anchor) == (900.0, 620.0, "bottom-right")
    assert snap(400.0, 300.0, 100.0, 80.0, 1000.0, 700.0)[2] is None


def test_an_edge_flung_past_still_counts_as_reached():
    # The cursor overshoots: the frame ends far beyond the line.
    assert snap(-240.0, 300.0, 100.0, 80.0, 1000.0, 700.0) == (0.0, 300.0, "left")


def test_snap_respects_the_top_chrome_and_a_left_offset():
    x, y, anchor = snap(205.0, 30.0, 100.0, 80.0, 1000.0, 700.0, top=24.0, left=200.0)
    assert (x, y, anchor) == (200.0, 24.0, "top-left")


def test_an_anchored_window_follows_its_edge_and_keeps_its_own_other_coordinate():
    assert anchored_position("right", 900.0, 300.0, 100.0, 80.0, 1200.0, 700.0) == (1100.0, 300.0)
    assert anchored_position("bottom-left", 0.0, 620.0, 100.0, 80.0, 1200.0, 900.0) == (0.0, 820.0)


def test_frames_touch_is_flush_with_overlapping_spans():
    a = (0.0, 0.0, 100.0, 100.0)
    assert frames_touch(a, (100.0, 50.0, 80.0, 80.0))          # beside
    assert frames_touch(a, (20.0, 101.0, 50.0, 50.0))          # stacked, within slack
    assert not frames_touch(a, (100.0, 150.0, 80.0, 80.0))     # beside, no overlap
    assert not frames_touch(a, (110.0, 0.0, 80.0, 80.0))       # a gap


def test_stuck_group_is_transitive():
    frames = {"a": (0.0, 0.0, 100.0, 100.0), "b": (100.0, 0.0, 100.0, 100.0),
              "c": (200.0, 50.0, 100.0, 100.0), "d": (600.0, 0.0, 50.0, 50.0)}
    assert stuck_group(frames, "a") == ["a", "b", "c"]
    assert stuck_group(frames, "d") == ["d"]


def test_snap_to_frames_lands_flush_and_levels_the_other_edge():
    frames = {"other": (300.0, 100.0, 200.0, 150.0)}
    x, y, hit = snap_to_frames("me", 94.0, 104.0, 200.0, 120.0, frames)
    assert (x, y, hit) == (100.0, 100.0, {"other"})


def test_a_group_travels_at_its_offsets_and_a_shift_drag_goes_alone():
    frames = {"a": (100.0, 100.0, 100.0, 100.0), "b": (200.0, 100.0, 80.0, 60.0),
              "c": (100.0, 200.0, 60.0, 60.0)}
    drag = WindowDrag.start("a", 120.0, 110.0, frames)
    assert drag.follower_keys == {"b", "c"}
    for px, py in [(300.0, 250.0), (412.5, 333.0), (150.0, 400.0)]:
        step = drag.move(px, py, (100.0, 100.0), {}, bounds=None)
        # The invariant: every follower keeps its offset from the lead.
        for key, (fx, fy) in step.followers.items():
            ox, oy = frames[key][0] - frames["a"][0], frames[key][1] - frames["a"][1]
            assert (fx - step.x, fy - step.y) == pytest.approx((ox, oy))
    assert WindowDrag.start("a", 120.0, 110.0, frames, alone=True).followers == []


# --------------------------------------------------------------------------- #
# The manager, driven by pointer events
# --------------------------------------------------------------------------- #
class Driver:
    """An ImApp around one manager, fed pointer events and drawn after each."""

    def __init__(self, docks: DockManager, box=BOX) -> None:
        self.docks = docks
        self.box = box
        self.drawn: dict = {}
        self.app = ImApp(lambda: docks.draw(self.box))
        self.frame()

    def frame(self):
        self.painter = RecordingPainter()
        self.app.draw(self.painter, *self.box)
        return self.painter

    def press(self, x, y, modifiers=0, clicks=1):
        self.app.pointer_press(x, y, LEFT_BUTTON, modifiers, clicks)
        self.frame()

    def move(self, x, y, modifiers=0):
        self.app.pointer_move(x, y, LEFT_BUTTON, modifiers)
        self.frame()

    def release(self, x, y):
        self.app.pointer_release(x, y, LEFT_BUTTON)
        self.frame()
        self.frame()

    def drag(self, *points, modifiers=0):
        self.press(*points[0], modifiers=modifiers)
        for point in points[1:]:
            self.move(*point, modifiers=modifiers)
        self.release(*points[-1])

    def title(self, key, dx=40.0):
        """A point on *key*'s floating title bar."""
        x, y, _w, _h = self.docks.window(key).frame
        return (x + dx, y + self.docks._title_h / 2.0)

    def tab(self, key):
        for region, rects in self.docks._tab_rects.items():
            for other, (x, y, w, h) in rects:
                if other == key:
                    return (x + w / 2.0, y + h / 2.0)
        raise KeyError(key)

    def pad(self, region):
        _rect, (x, y, w, h), _strip = self.docks.drop_targets()[region]
        return (x + w / 2.0, y + h / 2.0)


def _content(log: list, key: str):
    def draw(box):
        log.append((key, box))
        im.text(f"content of {key}")
    return draw


def make(layout=None, **kwargs) -> tuple[DockManager, list]:
    log: list = []
    docks = DockManager(layout if layout is not None else
                        Split("h", 0.3, Region("left"),
                              Split("v", 0.7, Region("center"), Region("bottom"))),
                        **kwargs)
    docks.add_window("form", "Form", _content(log, "form"), dock="left")
    docks.add_window("table", "Table", _content(log, "table"), dock="left")
    docks.add_window("plot", "Plot", _content(log, "plot"), dock="center")
    docks.add_window("notes", "Notes", _content(log, "notes"), box=(600.0, 100.0, 240.0, 150.0))
    docks.add_window("log", "Log", _content(log, "log"), box=(600.0, 400.0, 240.0, 150.0))
    return docks, log


def test_the_regions_tile_the_box_and_an_empty_one_gives_its_space_away():
    docks, log = make()
    Driver(docks)
    left = docks.region_boxes["left"]
    center = docks.region_boxes["center"]
    assert "bottom" not in docks.region_boxes            # nothing docked there
    assert left[0] == 0.0 and left[3] == 700.0
    assert center[0] + center[2] == 1000.0 and center[3] == 700.0   # the full height
    assert docks.window("form").frame == left
    # The tab on top draws; the one under it does not.
    drawn = {key for key, _box in log}
    assert "form" in drawn and "table" not in drawn and "plot" in drawn


def test_dragging_a_window_onto_a_region_docks_it_and_it_fills_the_region():
    docks, log = make()
    host = Driver(docks)
    host.drag(host.title("notes"), (300.0, 300.0), host.pad("bottom"))
    assert docks.region_of("notes") == "bottom"
    assert docks.floating() == ["log"]
    bottom = docks.region_boxes["bottom"]
    assert docks.window("notes").frame == bottom
    assert bottom[0] + bottom[2] == 1000.0 and bottom[1] + bottom[3] == 700.0
    # The content fills it, inside the tab strip.
    cx, cy, cw, ch = docks.window("notes").content
    assert cy > bottom[1] + docks._title_h - 1 and cw > bottom[2] - 20.0


def test_while_dragged_the_region_under_the_pointer_is_the_drop_target():
    docks, _log = make()
    host = Driver(docks)
    host.press(*host.title("notes"))
    host.move(*host.pad("center"))
    assert docks.drop_target == "center"
    host.move(900.0, 650.0)          # nowhere near a pad
    assert docks.drop_target is None
    host.release(900.0, 650.0)
    assert docks.region_of("notes") is None


def test_a_window_dropped_elsewhere_stays_floating_where_it_was_dropped():
    docks, _log = make()
    host = Driver(docks)
    x, y, _w, _h = docks.window("notes").frame
    host.drag(host.title("notes"), (host.title("notes")[0] - 100.0, host.title("notes")[1] + 50.0))
    assert docks.region_of("notes") is None
    assert docks.window("notes").frame[:2] == (x - 100.0, y + 50.0)


def test_dropping_on_a_tab_strip_makes_it_a_tab_there():
    docks, log = make()
    host = Driver(docks)
    strip = docks.drop_targets()["center"][2]
    host.drag(host.title("notes"), (strip[0] + strip[2] - 30.0, strip[1] + strip[3] / 2.0))
    assert docks.docked("center") == ["plot", "notes"]
    assert docks.active_tab("center") == "notes"
    # Choosing the other tab puts it on top.
    host.press(*host.tab("plot"))
    host.release(*host.tab("plot"))
    assert docks.active_tab("center") == "plot"


def test_dragging_a_tab_off_its_strip_undocks_it_under_the_pointer():
    docks, _log = make()
    host = Driver(docks)
    tx, ty = host.tab("table")
    host.press(tx, ty)
    host.move(tx + 20.0, ty + 60.0)
    host.move(tx + 220.0, ty + 260.0)
    host.release(tx + 220.0, ty + 260.0)
    assert docks.region_of("table") is None
    assert docks.docked("left") == ["form"]
    fx, fy, fw, _fh = docks.window("table").frame
    assert fx <= tx + 220.0 <= fx + fw and fy <= ty + 260.0 <= fy + docks._title_h


def test_a_tab_carried_off_goes_straight_into_another_region():
    docks, _log = make()
    host = Driver(docks)
    tx, ty = host.tab("table")
    host.press(tx, ty)
    host.move(tx + 20.0, ty + 80.0)
    host.move(*host.pad("bottom"))
    host.release(*host.pad("bottom"))
    assert docks.region_of("table") == "bottom"


def test_a_tab_dragged_along_the_strip_reorders():
    docks, _log = make()
    host = Driver(docks)
    fx, fy = host.tab("form")
    tx, _ty = host.tab("table")
    host.drag((fx, fy), (fx + 10.0, fy), (tx + 30.0, fy))
    assert docks.docked("left") == ["table", "form"]


def test_a_dragged_window_snaps_to_the_edge_and_to_another_window():
    docks, _log = make()
    host = Driver(docks)
    # Near the right edge: flush, and anchored there.
    gx, gy = host.title("notes")
    host.drag((gx, gy), (gx + 150.0, gy))
    x, _y, w, _h = docks.window("notes").frame
    assert x + w == 1000.0 and docks.window("notes").anchor == "right"
    # Near another window's edge: flush against it.
    lx, ly, lw, _lh = docks.window("log").frame
    gx, gy = host.title("notes")
    host.drag((gx, gy), (lx - 240.0 - 5.0 + 40.0, ly + 3.0 + docks._title_h / 2.0))
    nx, ny, nw, _nh = docks.window("notes").frame
    assert nx + nw == lx and ny == ly


def test_the_snapped_group_travels_together_and_shift_takes_one_alone():
    docks, _log = make()
    host = Driver(docks)
    lx, ly, _lw, _lh = docks.window("log").frame
    gx, gy = host.title("notes")
    host.drag((gx, gy), (lx - 240.0 + 40.0, ly + docks._title_h / 2.0))   # flush left of log
    notes, log_ = docks.window("notes").frame, docks.window("log").frame
    offset = (log_[0] - notes[0], log_[1] - notes[1])
    gx, gy = host.title("notes")
    host.drag((gx, gy), (gx - 180.0, gy - 60.0))
    notes, log_ = docks.window("notes").frame, docks.window("log").frame
    assert (log_[0] - notes[0], log_[1] - notes[1]) == offset
    # Shift: the lead leaves, the other stays.
    before = docks.window("log").frame
    gx, gy = host.title("notes")
    host.drag((gx, gy), (gx - 50.0, gy + 200.0), modifiers=SHIFT_MODIFIER)
    assert docks.window("log").frame == before


def test_the_splitter_drags_the_ratio_and_close_hides_a_window():
    docks, _log = make()
    host = Driver(docks)
    split, _rect, bar = docks.splitters[0]
    bx, by = bar[0] + bar[2] / 2.0, 300.0
    host.drag((bx, by), (bx + 100.0, by))
    assert docks.region_boxes["left"][2] == pytest.approx(300.0 + 100.0, abs=2.0)
    assert split.ratio > 0.3
    # The × on the left strip closes the tab on top.
    x, y, w, _h = docks.region_boxes["left"]
    th = docks._title_h
    host.press(x + w - th / 2.0, y + th / 2.0)
    host.release(x + w - th / 2.0, y + th / 2.0)
    assert not docks.is_visible("form")
    assert docks.active_tab("left") == "table"


def test_fold_resize_and_raise_on_a_floating_window():
    docks, _log = make()
    host = Driver(docks)
    x, y, w, h = docks.window("notes").frame
    th = docks._title_h
    host.press(x + th / 2.0, y + th / 2.0)          # the fold arrow
    host.release(x + th / 2.0, y + th / 2.0)
    assert docks.window("notes").frame[3] == th
    host.press(x + th / 2.0, y + th / 2.0)
    host.release(x + th / 2.0, y + th / 2.0)
    assert docks.window("notes").frame[3] == h
    host.drag((x + w - 3.0, y + h - 3.0), (x + w + 57.0, y + h + 37.0))
    assert docks.window("notes").frame[2:] == (w + 60.0, h + 40.0)
    assert docks.floating()[-1] == "notes"
    lx, ly, _lw, _lh = docks.window("log").frame
    host.press(lx + 60.0, ly + 60.0)                 # the body raises it
    host.release(lx + 60.0, ly + 60.0)
    assert docks.floating()[-1] == "log"


def test_show_hide_toggle_and_focus():
    docks, _log = make()
    Driver(docks)
    assert docks.toggle("table") is True and docks.active_tab("left") == "table"
    assert docks.toggle("table") is False and docks.active_tab("left") == "form"
    docks.hide("form")
    docks.hide("table")
    host = Driver(docks)
    assert "left" not in docks.region_boxes
    docks.focus("form")
    host.frame()
    assert docks.region_boxes["left"] and docks.window("form").frame == docks.region_boxes["left"]


def test_the_layout_round_trips_through_json():
    docks, _log = make()
    host = Driver(docks)
    host.drag(host.title("notes"), host.pad("bottom"))
    docks.set_ratio("root", 0.4)
    docks.hide("log")
    text = docks.to_json()
    state = json.loads(text)
    assert state["regions"]["bottom"]["tabs"] == ["notes"]

    again, _ = make()
    again.restore(json.loads(text))
    assert again.state() == state
    Driver(again)
    assert again.region_of("notes") == "bottom" and not again.is_visible("log")


def test_a_saved_layout_places_windows_added_after_it_and_keeps_strangers():
    docks, _ = make()
    docks.dock("notes", "bottom")
    saved = docks.state()
    saved["windows"]["ghost"] = {"dock": "left", "box": None, "visible": True,
                                 "collapsed": False, "anchor": None}
    fresh = DockManager(Split("h", 0.3, Region("left"),
                              Split("v", 0.7, Region("center"), Region("bottom"))))
    fresh.restore(saved)
    fresh.add_window("notes", "Notes", box=(10.0, 10.0, 100.0, 100.0))
    assert fresh.region_of("notes") == "bottom"
    # A window this run does not have keeps its place in what is written back.
    assert fresh.state()["windows"]["ghost"]["dock"] == "left"
    assert "ghost" in fresh.state()["regions"]["left"]["tabs"]


def test_reset_puts_back_what_the_app_declared():
    docks, _ = make()
    docks.dock("notes", "bottom")
    docks.undock("form")
    docks.set_ratio("root", 0.6)
    docks.reset()
    assert docks.docked("left") == ["form", "table"]
    assert docks.region_of("notes") is None and docks.splits["root"].ratio == 0.3


class _LocalStorage:
    def __init__(self):
        self.items = {}

    def getItem(self, key):  # noqa: N802 - the DOM's spelling
        return self.items.get(key)

    def setItem(self, key, value):  # noqa: N802
        self.items[key] = value

    def removeItem(self, key):  # noqa: N802
        self.items.pop(key, None)


@pytest.mark.parametrize("where", ["file", "page"])
def test_a_store_saves_every_change_and_loads_it_next_run(tmp_path, where):
    def store():
        if where == "file":
            return LayoutStore("t", path=tmp_path / "layout.json")
        return LayoutStore("t", storage=page)

    page = _LocalStorage()
    docks, _ = make(store=store())
    host = Driver(docks)
    host.drag(host.title("notes"), host.pad("bottom"))       # a change: saved
    if where == "page":
        assert "emtk.layout.t" in page.items
    else:
        assert (tmp_path / "layout.json").is_file()
    again, _ = make(store=store())
    assert again.load()
    assert again.region_of("notes") == "bottom"
    again.reset()
    assert not store().load()


# --------------------------------------------------------------------------- #
# Hosts: a real GPU frame at ratio 2, and QPainter
# --------------------------------------------------------------------------- #
def test_a_drop_at_ratio_2_lands_where_the_region_is_drawn():
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from rendercanvas.offscreen import RenderCanvas

    from emtk.native import NativeHost
    from emtk.wgpu_host import default_device

    try:
        device = default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")
    docks, _ = make()
    app = ImApp(lambda: docks.draw(im.get_current_context().box))
    host = NativeHost(app, canvas=RenderCanvas(size=(1000, 700), pixel_ratio=2.0),
                      device=device)
    image = host.draw_frame()
    assert tuple(image.shape[:2]) == (1400, 2000)
    assert docks.box == BOX                     # laid out in logical pixels

    def event(kind, x, y, down):
        return {"event_type": kind, "x": x, "y": y, "button": 1,
                "buttons": (1,) if down else (), "modifiers": ()}

    x, y, _w, _h = docks.window("notes").frame
    start = (x + 40.0, y + 8.0)
    _r, (px, py, pw, ph), _s = docks.drop_targets()["bottom"]
    end = (px + pw / 2.0, py + ph / 2.0)
    host.events._on_pointer_down(event("pointer_down", *start, True))
    host.draw_frame()
    host.events._on_pointer_move(event("pointer_move", *end, True))
    host.draw_frame()
    host.events._on_pointer_up(event("pointer_up", *end, False))
    host.draw_frame()
    host.draw_frame()
    assert docks.region_of("notes") == "bottom"
    assert docks.window("notes").frame == docks.region_boxes["bottom"]


def test_the_windows_draw_through_qpainter(qt_app):
    from qtpy import QtGui

    from emtk.qt_painter import QtPainter

    docks, log = make()
    app = ImApp(lambda: docks.draw(BOX))
    image = QtGui.QImage(1000, 700, QtGui.QImage.Format_RGBA8888)
    image.fill(QtGui.QColor(0, 0, 0))
    qt = QtGui.QPainter(image)
    try:
        app.draw(QtPainter(qt, 9.0), *BOX)
    finally:
        qt.end()
    assert {key for key, _box in log} >= {"form", "plot", "notes", "log"}
    assert docks.window("plot").frame == docks.region_boxes["center"]


def test_the_windows_draw_through_pillow_as_the_tk_frame_does():
    pytest.importorskip("PIL")
    import numpy as np

    from emtk.pil_painter import PilPainter

    docks, log = make()
    app = ImApp(lambda: docks.draw(BOX))
    painter = PilPainter(1000, 700, background=(0, 0, 0, 255))
    app.draw(painter, *BOX)
    pixels = np.asarray(painter.frame)[..., :3]
    # The floating window's title bar is drawn where its frame says.
    x, y, w, _h = docks.window("log").frame
    assert pixels[int(y) + 3, int(x + w / 2)].sum() > 0
    assert {key for key, _box in log} >= {"form", "plot", "notes", "log"}


def test_view_changes_are_saved_too_not_only_drags(tmp_path):
    store = LayoutStore("t", path=tmp_path / "layout.json")
    docks, _ = make(store=store)
    host = Driver(docks)
    docks.hide("form")                   # the app's View menu, say
    host.frame()
    assert store.load()["windows"]["form"]["visible"] is False
    docks.focus("form")
    host.frame()
    assert store.load()["windows"]["form"]["visible"] is True
    again, _ = make(store=LayoutStore("t", path=tmp_path / "layout.json"))
    assert again.load() and again.is_visible("form")


def test_a_dialog_drawn_after_the_docks_takes_the_click_however_early_it_opened():
    docks, _ = make()
    clicks = []
    state = {"dialog": True}

    def gui():
        # The dialog exists before the docks' windows do, then is drawn after them.
        if state["dialog"] and not docks.region_boxes:
            im.begin("dialog", (100.0, 100.0, 300.0, 200.0))
            im.end()
        docks.draw(BOX)
        im.begin("dialog", (100.0, 100.0, 300.0, 200.0))
        im.set_cursor_screen_pos((120.0, 120.0))
        if im.button("dialog button", (200.0, 40.0)):
            clicks.append("dialog")
        im.end()

    app = ImApp(gui)
    for _ in range(2):
        app.draw(RecordingPainter(), *BOX)
    app.pointer_press(150.0, 130.0, LEFT_BUTTON, 0, 1)
    app.draw(RecordingPainter(), *BOX)
    app.pointer_release(150.0, 130.0, LEFT_BUTTON)
    app.draw(RecordingPainter(), *BOX)
    assert clicks == ["dialog"]
    assert docks.region_of("form") == "left"          # the tab under it was not hit
