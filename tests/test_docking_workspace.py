"""emtk.docking: the workspace -- the region the documents (``workspace=True`` windows) live in.

Driven as a host drives an app: pointer and key events into an :class:`~emtk.app.ImApp`
that draws a :class:`~emtk.docking.DockManager`, one frame after each event.
"""
from __future__ import annotations

import json

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.docking import MIN_TILE, DockManager, Region, Split, tile_grid
from emtk.events import CONTROL_MODIFIER, LEFT_BUTTON, RIGHT_BUTTON, SHIFT_MODIFIER
from emtk.keys import KEY_ESCAPE, KEY_TAB
from emtk.testing import RecordingPainter

BOX = (0.0, 0.0, 1400.0, 900.0)


class Host:
    def __init__(self, docks: DockManager, box=BOX) -> None:
        self.docks = docks
        self.box = box
        self.app = ImApp(lambda: docks.draw(self.box))
        self.frame()
        self.frame()

    def frame(self):
        self.painter = RecordingPainter()
        self.app.draw(self.painter, *self.box)
        return self.painter

    def click(self, x, y, button=LEFT_BUTTON):
        self.app.pointer_move(x, y, 0, 0)
        self.frame()
        self.app.pointer_press(x, y, button, 0, 1)
        self.frame()
        self.app.pointer_release(x, y, button)
        self.frame()
        self.frame()

    def drag(self, start, *points):
        self.app.pointer_move(*start, 0, 0)
        self.frame()
        self.app.pointer_press(*start, LEFT_BUTTON, 0, 1)
        self.frame()
        for point in points:
            self.app.pointer_move(*point, LEFT_BUTTON, 0)
            self.frame()
        self.app.pointer_release(*points[-1], LEFT_BUTTON)
        self.frame()
        self.frame()

    def title(self, key, dx=40.0):
        x, y, _w, _h = self.docks.window(key).frame
        return (x + dx, y + self.docks._title_h / 2.0)

    def text(self, label):
        hits = [t for t in self.painter.texts if t[5].strip() == label]
        assert hits, f"{label!r} not drawn"
        x, y, w, h = hits[-1][:4]
        return (x + w / 2.0, y + h / 2.0)


def _content(key):
    def draw(_box):
        im.text(f"content of {key}")
    return draw


def make(windows=("a", "b", "c")) -> DockManager:
    docks = DockManager(Split("h", 0.25, Region("left"), Region("center", workspace=True)))
    docks.add_window("tools", "Tools", _content("tools"), dock="left", closable=False, core=True)
    for index, key in enumerate(windows):
        docks.add_window(key, key.upper(), _content(key),
                         box=(400.0 + 30 * index, 100.0 + 30 * index, 420.0, 300.0),
                         workspace=True)
    return docks


def _inside(frame, bounds) -> bool:
    x, y, w, h = frame
    bx, by, bw, bh = bounds
    return x >= bx - 0.5 and y >= by - 0.5 and x + w <= bx + bw + 0.5 and y + h <= by + bh + 0.5


def test_tile_grid_is_near_square_and_never_below_the_minimum_tile():
    assert tile_grid(6, 1700, 900) == (2, 3)
    assert tile_grid(4, 1200, 800) == (2, 2)
    assert tile_grid(2, 1200, 800) == (1, 2)
    assert tile_grid(6, 400, 300) == (1, 1)
    rows, cols = tile_grid(5, 1300, 700)
    assert 1300 / cols >= MIN_TILE[0] and 700 / rows >= MIN_TILE[1]


def test_floating_windows_live_inside_the_workspace_and_cannot_be_dragged_out():
    docks = make()
    host = Host(docks)
    bounds = docks.floating_bounds()
    left = docks.region_boxes["left"]
    assert bounds[0] >= left[0] + left[2], "the workspace is right of the Tools dock"
    for key in "abc":
        assert _inside(docks.window(key).frame, bounds)
    # Flung far to the left, over Tools and off the canvas: it stays in the workspace.
    host.drag(host.title("a"), (200.0, 300.0), (-400.0, -200.0))
    assert docks.region_of("a") is None
    assert _inside(docks.window("a").frame, docks.floating_bounds())


def test_a_shrinking_window_clamps_the_children_back_into_the_workspace():
    docks = make()
    host = Host(docks)
    docks.window("c").box = (1000.0, 600.0, 380.0, 280.0)
    host.frame()
    host.box = (0.0, 0.0, 900.0, 600.0)
    host.frame()
    host.frame()
    bounds = docks.floating_bounds()
    for key in "abc":
        assert _inside(docks.window(key).frame, bounds), key



def test_a_window_placed_below_the_edge_keeps_its_title_bar_reachable():
    docks = make()
    host = Host(docks)
    bounds = docks.floating_bounds()
    bottom = bounds[1] + bounds[3]
    docks.window("a").box = (500.0, bottom + 300.0, 420.0, 300.0)
    host.frame()
    _x, y, _w, h = docks.window("a").frame
    assert y + h > bottom, "a placed window may hang below the workspace"
    assert abs(y + docks._title_h - bottom) <= 0.5, "but never below its title bar"

def test_the_workspace_is_always_there_even_empty_and_survives_close_all_panels():
    docks = make(windows=())
    host = Host(docks)
    assert "center" in docks.region_boxes, "an empty workspace keeps its space"
    docks.close_panels()
    host.frame()
    assert "center" in docks.region_boxes
    assert docks.workspace == "center"


def test_tile_lays_the_children_in_a_grid_of_usable_tiles():
    docks = make(windows=("a", "b", "c", "d"))
    host = Host(docks)
    docks.dock("d", "center")              # a tab of the workspace is one of its children too
    host.frame()
    docks.tile_workspace()
    host.frame()
    host.frame()
    frames = [docks.window(k).frame for k in "abcd"]
    assert all(f is not None for f in frames)
    assert len({tuple(f) for f in frames}) == 4
    assert min(f[2] for f in frames) >= MIN_TILE[0] - 1 and min(f[3] for f in frames) >= MIN_TILE[1] - 1
    bounds = docks.floating_bounds()
    assert all(_inside(f, bounds) for f in frames)
    for i, f in enumerate(frames):              # no two tiles overlap
        for g in frames[i + 1:]:
            assert f[0] + f[2] <= g[0] + 0.5 or g[0] + g[2] <= f[0] + 0.5 \
                or f[1] + f[3] <= g[1] + 0.5 or g[1] + g[3] <= f[1] + 0.5


def test_tile_minimizes_what_the_workspace_cannot_hold_and_a_chip_brings_it_back():
    docks = make(windows=tuple("abcdef"))
    host = Host(docks, box=(0.0, 0.0, 1000.0, 700.0))
    docks.tile_workspace()
    host.frame()
    host.frame()
    tiled = [k for k in "abcdef" if docks.window(k).frame is not None]
    hidden = [k for k in "abcdef" if docks.window(k).minimized]
    assert tiled and hidden and len(tiled) + len(hidden) == 6
    # The strip shows a chip per minimized window; a click on it restores that window.
    host.click(*host.text(hidden[0].upper()))
    assert not docks.window(hidden[0]).minimized
    assert docks.floating()[-1] == hidden[0]
    assert docks.window(hidden[0]).frame is not None


def test_cascade_floats_each_child_a_step_below_the_last_and_the_last_on_top():
    docks = make()
    host = Host(docks)
    docks.dock("b", "center")
    docks.cascade_workspace()
    host.frame()
    host.frame()
    assert docks.region_of("b") is None
    xs = [docks.window(k).frame[0] for k in "abc"]
    ys = [docks.window(k).frame[1] for k in "abc"]
    assert xs == sorted(xs) and ys == sorted(ys) and len(set(ys)) == 3
    assert docks.floating()[-1] == "c"


def test_tabbed_docks_every_child_in_the_workspace():
    docks = make()
    host = Host(docks)
    docks.minimize("b")
    docks.tab_workspace()
    host.frame()
    assert docks.docked("center") == ["a", "b", "c"]
    assert not docks.window("b").minimized
    assert docks.floating() == []


def test_the_toolbar_buttons_tile_cascade_and_tab():
    docks = make()
    host = Host(docks)
    host.click(*host.text("Tabbed"))
    assert docks.docked("center") == ["a", "b", "c"]
    host.click(*host.text("Tile"))
    assert docks.docked("center") == [] and len(docks.floating()) == 3
    host.click(*host.text("Cascade"))
    assert docks.floating()[-1] == "c"


def test_the_windows_menu_lists_the_children_and_picks_one():
    docks = make()
    host = Host(docks)
    docks.minimize("a")
    host.frame()
    host.click(*host.text("Windows"))
    host.frame()
    assert any(t[5].strip().startswith("A (minimized)") for t in host.painter.texts)
    host.app.key(KEY_ESCAPE, "", 0)
    host.frame()
    host.frame()
    assert not any(t[5].strip().startswith("A (minimized)") for t in host.painter.texts), \
        "Escape closes the list"
    host.click(*host.text("Windows"))
    host.frame()
    host.click(*host.text("A (minimized)"))
    assert not docks.window("a").minimized and docks.focused == "a"
    assert docks.floating()[-1] == "a"


def test_right_click_on_the_workspace_opens_its_menu():
    docks = make(windows=())
    host = Host(docks)
    x, y, w, h = docks.region_boxes["center"]
    host.click(x + w / 2.0, y + h / 2.0, button=RIGHT_BUTTON)
    host.frame()
    assert any(t[5].strip() == "No windows in the workspace." for t in host.painter.texts)


def test_the_minimize_button_puts_a_window_on_the_strip():
    docks = make()
    host = Host(docks)
    x, y, w, _h = docks.window("c").frame
    th = docks._title_h
    # Right to left on the title bar: close, then minimize.
    host.click(x + w - th - th / 2.0, y + th / 2.0)
    assert docks.window("c").minimized and docks.window("c").frame is None
    assert not docks.is_shown("c")
    bounds = docks.floating_bounds()
    assert bounds[1] + bounds[3] < docks.region_boxes["center"][1] + docks.region_boxes["center"][3] - th


def test_ctrl_tab_cycles_the_children_and_shift_goes_back():
    docks = make()
    host = Host(docks)
    docks.focus("a")
    assert docks.handle_key(KEY_TAB, CONTROL_MODIFIER)
    assert docks.focused == "b" and docks.floating()[-1] == "b"
    docks.minimize("c")
    assert docks.handle_key(KEY_TAB, CONTROL_MODIFIER)
    assert docks.focused == "c" and not docks.window("c").minimized
    assert docks.handle_key(KEY_TAB, CONTROL_MODIFIER | SHIFT_MODIFIER)
    assert docks.focused == "b"
    assert not docks.handle_key(KEY_TAB, 0), "a plain Tab is the focus ring's"
    # The same keys arriving through the host's input, for an app that passes them on.
    host.app.key(KEY_TAB, "", CONTROL_MODIFIER)
    host.frame()
    assert docks.focused == "c"


def test_the_arrangement_round_trips_through_the_state():
    docks = make()
    host = Host(docks)
    docks.tile_workspace()
    docks.minimize("b")
    host.frame()
    state = json.loads(json.dumps(docks.state()))
    again = make()
    again.restore(state)
    Host(again)
    assert again.workspace == "center"
    assert again.window("b").minimized
    for key in "ac":
        assert again.window(key).box == pytest.approx(docks.window(key).box, abs=0.01)


def test_a_layout_saved_before_the_workspace_was_declared_still_has_it():
    old = DockManager(Split("h", 0.25, Region("left"), Region("center")))
    old.add_window("a", "A", _content("a"), dock="center")
    state = json.loads(json.dumps(old.state()))
    docks = make()
    docks.restore(state)
    assert docks.workspace == "center"


def test_without_a_workspace_floating_windows_range_over_the_whole_box():
    docks = DockManager(Split("h", 0.25, Region("left"), Region("center")))
    docks.add_window("a", "A", _content("a"), box=(10.0, 10.0, 300.0, 200.0))
    Host(docks)
    assert docks.workspace is None
    assert docks.floating_bounds() == BOX
    assert docks.window("a").frame[:2] == (10.0, 10.0)
    assert not docks.handle_key(KEY_TAB, CONTROL_MODIFIER)


# -- documents live in the workspace, docks everywhere else ---------------------------------- #


def _with_tool(docks, key="tool", **options):
    docks.add_window(key, key.title(), _content(key), **options)
    return docks


def test_a_dock_is_never_a_workspace_child_and_floats_over_the_whole_box():
    docks = _with_tool(make(), box=(10.0, 10.0, 300.0, 200.0))
    host = Host(docks)
    assert "tool" not in docks.workspace_children()
    frame = docks.window("tool").frame
    assert frame[0] < docks.floating_bounds()[0], "it floats over the Tools dock, outside the workspace"
    # Tile, Cascade and Tabbed leave it where it is.
    docks.tile_workspace()
    docks.cascade_workspace()
    docks.tab_workspace()
    host.frame()
    assert docks.region_of("tool") is None and "tool" in docks.z
    assert sorted(docks.tabs["center"]) == ["a", "b", "c"]


def test_a_dock_asked_into_the_workspace_docks_where_it_was_declared_or_floats():
    docks = _with_tool(make(), dock="left")
    docks.dock("tool", "center")
    assert docks.region_of("tool") == "left", "the workspace takes no docks"
    _with_tool(docks, "loose", box=(10.0, 10.0, 300.0, 200.0))
    docks.dock("loose", "center")
    assert docks.region_of("loose") is None
    docks.add_window("born", "Born", _content("born"), dock="center")
    assert docks.region_of("born") is None, "added into the workspace, it floats instead"


def test_a_document_docks_only_in_the_workspace():
    docks = make()
    docks.dock("a", "left")
    assert docks.region_of("a") == "center"
    assert docks.admits("a", "center") and not docks.admits("a", "left")
    assert docks.admits("tools", "left") and not docks.admits("tools", "center")


def test_drop_targets_follow_the_rule():
    docks = _with_tool(make(), box=(10.0, 10.0, 300.0, 200.0))
    Host(docks)
    assert not docks.target_admits("tool", "center")
    assert docks.target_admits("tool", "center:left"), "beside the workspace is a dock of its own"
    assert docks.target_admits("tool", "left")
    assert docks.target_admits("a", "center")
    assert not docks.target_admits("a", "left") and not docks.target_admits("a", "center:left")
    assert not docks.target_admits("a", "root:left")


def test_dragging_a_dock_onto_the_workspace_pad_does_not_dock_it_there():
    docks = _with_tool(make(windows=()), box=(10.0, 10.0, 300.0, 200.0))
    host = Host(docks)
    cx, cy, cw, ch = docks.region_boxes["center"]
    middle = (cx + cw / 2.0, cy + ch / 2.0)
    host.drag(host.title("tool"), (middle[0] - 50.0, middle[1]), middle)
    assert docks.region_of("tool") is None, "the workspace's centre pad is not offered to a dock"
    left = docks.region_boxes["left"]
    middle = (left[0] + left[2] / 2.0, left[1] + left[3] / 2.0)
    host.drag(host.title("tool"), (middle[0] + 20.0, middle[1]), middle)
    assert docks.region_of("tool") == "left"


def test_only_documents_have_a_minimize_button():
    docks = _with_tool(make(), box=(10.0, 10.0, 300.0, 200.0))
    host = Host(docks)
    host.frame()
    labels = [t[5] for t in host.painter.texts]
    assert labels.count("_") == 3, "a, b and c; not the tool"
    docks.minimize("tool")
    assert not docks.window("tool").minimized


def test_a_saved_layout_with_a_dock_in_the_workspace_puts_it_back_where_it_belongs():
    docks = _with_tool(make(), dock="left")
    state = docks.state()
    state["windows"]["tool"]["dock"] = "center"
    state["regions"]["center"] = {"tabs": ["tool"], "selected": "tool"}
    fresh = _with_tool(make(), dock="left")
    fresh.restore(json.loads(json.dumps(state)))
    assert fresh.region_of("tool") == "left"


def test_the_workspace_background_is_drawn_in_its_body_under_the_floating_windows():
    """A host's watermark: drawn into the workspace body (under its tool bar) every frame,
    before -- so under -- the floating windows; a failing hook is logged, not raised."""
    docks = make(("a",))
    seen = []

    def background(rect):
        seen.append(rect)
        im.get_window_draw_list().add_text((rect[0] + 4.0, rect[1] + 4.0), (1, 1, 1, 0.3),
                                           "WATERMARK")

    docks.workspace_background = background
    host = Host(docks)
    painter = host.frame()
    inner = docks._inner_boxes["center"]
    assert seen and seen[-1] == inner
    order = [t[5] for t in painter.texts]
    assert "WATERMARK" in order and "content of a" in order
    assert order.index("WATERMARK") < order.index("content of a"), "drawn before the window"
    # A tab filling the body is drawn after (over) it too.
    docks.add_window("doc", "Doc", _content("doc"), dock="center", workspace=True)
    order = [t[5] for t in host.frame().texts]
    assert order.index("WATERMARK") < order.index("content of doc")

    def broken(rect):
        raise RuntimeError("boom")

    docks.workspace_background = broken
    host.frame()  # does not raise
