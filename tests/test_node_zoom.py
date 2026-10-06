"""An overflowing node canvas owns the wheel and inverse zoom is symmetric."""

import math

import pytest
from emtk import im, nodes
from emtk.app import ImApp
from emtk.testing import Driver


def editor():
    ctx = nodes.EditorContext()

    def gui():
        nodes.begin_node_editor(ctx, box=(0, 0, 400, 300))
        for nid, pos in [(1, (30, 30)), (2, (900, 600))]:
            nodes.set_node_grid_space_pos(ctx, nid, pos)
            nodes.begin_node(nid)
            nodes.begin_node_title_bar()
            im.text("Analysis node")
            nodes.end_node_title_bar()
            im.text("A realistic overflowing graph")
            nodes.end_node()
        nodes.end_node_editor()

    return ctx, Driver(ImApp(gui), (400, 300))


def test_overflowing_editor_wheel_zooms_instead_of_scrolling():
    ctx, drv = editor()
    drv.frame(3)
    drv.wheel(2, at=(200, 150))
    assert ctx.canvas.zoom == pytest.approx(math.exp(0.2))
    drv.wheel(-2, at=(200, 150))
    assert ctx.canvas.zoom == pytest.approx(1.0, abs=1e-12)
    windows = drv.app.storage["__windows__"]
    assert all(window.scroll_y == 0 for window in windows)


def test_wheel_is_consumed_once_and_fractional_wheel_is_preserved():
    ctx, drv = editor()
    drv.frame(2)
    drv.wheel(0.5, at=(200, 150))
    expected = math.exp(0.05)
    assert ctx.canvas.zoom == pytest.approx(expected)
    drv.frame(3)
    assert ctx.canvas.zoom == pytest.approx(expected)
    assert drv.app.io.mouse_wheel == 0


def test_repeated_inverse_zoom_preserves_transform():
    ctx, drv = editor()
    drv.frame(3)
    original = ctx.canvas.panning
    for _ in range(5):
        drv.wheel(1, at=(170, 110))
        drv.wheel(-1, at=(170, 110))
    assert ctx.canvas.zoom == pytest.approx(1.0, abs=1e-12)
    assert ctx.canvas.panning == pytest.approx(original, abs=1e-12)
