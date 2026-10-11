"""Every widget settles: after one input, idle frames with the hand held still change nothing.

The sweep behind :func:`emtk.testing_realistic.assert_settles`. Each widget that reads the
pointer, the wheel or the keys is given each gesture -- a wheel notch, a trackpad swipe, a
click, a small drag, a key -- through :class:`~emtk.testing_realistic.RealisticDriver`, and then
30 idle frames. The frame the user sees (every painter call) must not change after the gesture
has been handled, and the app must stop asking the host for frames.

A plot that zoomed on every frame after one notch is the defect this guards; a widget that
reads a one-shot input without consuming it would show the same.
"""
from __future__ import annotations

import pytest

from emtk import im, implot, nodes
from emtk.app import ImApp
from emtk.keys import KEY_DOWN
from emtk.testing_realistic import RealisticDriver, assert_settles
from emtk.view_form import FormState, draw_sections


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []


def _checkbox(state):
    _, state["v"] = im.checkbox("check", state.get("v", False))


def _slider(state):
    _, state["v"] = im.slider_float("slider", state.get("v", 0.5), 0.0, 1.0)


def _drag(state):
    _, state["v"] = im.drag_float("drag", state.get("v", 0.5), 0.01, 0.0, 1.0)


def _input_int(state):
    _, state["v"] = im.input_int("int", state.get("v", 5))


def _combo(state):
    _, state["v"] = im.combo("combo", state.get("v", 0), ["one", "two", "three"])


def _list_box(state):
    _, state["v"] = im.list_box("list", state.get("v", 0), [f"item {i}" for i in range(40)])


def _input_text(state):
    _, state["v"] = im.input_text("text", state.get("v", "hello"))


def _multiline(state):
    _, state["v"] = im.input_text_multiline(
        "lines", state.get("v", "\n".join(f"line {i}" for i in range(60))), (300, 120))


def _scroll_child(state):
    im.begin_child("rows", (300, 150))
    for i in range(80):
        im.text(f"row {i}")
    im.end_child()


def _table(state):
    if im.begin_table("t", 2, 0, (300, 150)):
        for i in range(80):
            im.table_next_row()
            im.table_next_column()
            im.text(str(i))
            im.table_next_column()
            im.text(f"value {i}")
        im.end_table()


def _plot(state):
    implot.begin_plot("##p", (300, 200), implot.FLAGS_NO_LEGEND)
    implot.setup_axes_limits(0, 10, 0, 10)
    implot.plot_line("line", [0, 10], [0, 10])
    implot.end_plot()


_SPIN = [{"type": "value", "attr": "v", "kind": "int", "style": "spin", "minimum": 0,
          "maximum": 99, "step": 1, "description": "a spin field"}]


class _Model:
    v = 5


def _spin(state):
    form = state.setdefault("form", (_Model(), FormState()))
    draw_sections(_SPIN, *form)


def _node_editor(state):
    ctx = state.setdefault("nodes", nodes.EditorContext())
    x, y = im.get_cursor_screen_pos()
    nodes.begin_node_editor(ctx, box=(x, y, 360, 240))
    for nid, pos in [(1, (30, 30)), (2, (500, 400))]:
        nodes.set_node_grid_space_pos(ctx, nid, pos)
        nodes.begin_node(nid)
        nodes.begin_node_title_bar()
        im.text("node")
        nodes.end_node_title_bar()
        nodes.end_node()
    nodes.end_node_editor()


WIDGETS = {
    "checkbox": _checkbox, "slider": _slider, "drag": _drag, "input_int": _input_int,
    "combo": _combo, "list_box": _list_box, "input_text": _input_text,
    "multiline": _multiline, "scroll_child": _scroll_child, "table": _table, "plot": _plot,
    "spin": _spin, "node_editor": _node_editor,
}

GESTURES = {
    "wheel": lambda d, c: d.wheel(1, at=c),
    "wheel_down": lambda d, c: d.wheel(-1, at=c),
    "swipe": lambda d, c: d.swipe(2, at=c, events=12, momentum=8),
    "click": lambda d, c: d.click(c),
    "drag": lambda d, c: d.drag(c, (c[0] + 12, c[1] + 6)),
    "key": lambda d, c: (d.hover(c), d.key(KEY_DOWN), d.release_key()),
}


def _app(build):
    state: dict = {"rect": None}

    def gui():
        im.begin("w", (0, 0, 640, 420))
        im.set_cursor_screen_pos((40, 40))
        im.begin_group()
        build(state)
        im.end_group()
        state["rect"] = im.get_item_rect()
        im.end()

    app = ImApp(gui)
    app.io.wall_clock = False
    return app, state


@pytest.mark.parametrize("gesture", sorted(GESTURES))
@pytest.mark.parametrize("widget", sorted(WIDGETS))
def test_every_widget_settles_after_every_gesture(widget, gesture):
    app, state = _app(WIDGETS[widget])
    driver = RealisticDriver(app, (640, 420), real_painter=False)
    driver.frame(3)
    x, y, w, h = state["rect"]
    centre = (x + min(w, 300) / 2.0, y + h / 2.0)
    assert_settles(driver, lambda d: GESTURES[gesture](d, centre), frames=30,
                   label=f"{widget}/{gesture}")
