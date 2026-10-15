from emtk import im
from emtk.docking import DockManager, Region
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def render(manager, storage, io=None):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 500, 300), storage=storage, io=io):
        manager.draw((0, 0, 500, 300))
    return painter


def test_dock_header_context_menu_offers_panel_actions():
    manager = DockManager(Region("main"))
    manager.add_window("files", "Project", dock="main")
    storage = {}
    render(manager, storage)
    painter = render(manager, storage, IO(mouse_pos=(25, 8),
        mouse_clicked=[False, True, False], mouse_down=[False, True, False]))
    labels = [s.strip() for s in painter.strings]
    assert "Undock" in labels
    assert "Close panel" in labels
    assert "Restore default layout" in labels


def test_closed_panel_can_be_reopened_from_empty_header():
    manager = DockManager(Region("main"))
    manager.add_window("files", "Project", dock="main")
    storage = {}
    render(manager, storage)
    tab_rect = next(r for k, r in manager._tab_rects["main"] if k == "files")
    close_pos = (tab_rect[0] + tab_rect[2] - 8, tab_rect[1] + 8)
    render(manager, storage, IO(mouse_pos=close_pos,
        mouse_clicked=[True, False, False], mouse_down=[True, False, False]))
    render(manager, storage, IO(mouse_pos=close_pos,
        mouse_released=[True, False, False]))
    assert not manager.window("files").visible
    render(manager, storage)
    render(manager, storage)
    painter = render(manager, storage, IO(mouse_pos=(25, 8),
        mouse_clicked=[False, True, False], mouse_down=[False, True, False]))
    assert "Show Project" in [s.strip() for s in painter.strings]
    text = next(t for t in painter.texts if t[5].strip() == "Show Project")
    position = (text[0] + 12, text[1] + 8)
    render(manager, storage, IO(mouse_pos=position))
    render(manager, storage, IO(mouse_pos=position,
        mouse_clicked=[True, False, False], mouse_down=[True, False, False]))
    render(manager, storage, IO(mouse_pos=position,
        mouse_released=[True, False, False]))
    assert manager.window("files").visible


# --------------------------------------------------------------------------- #
# Close all / close other panels, and the menu's height
# --------------------------------------------------------------------------- #
def _driven(core=("tools",)):
    from emtk.app import ImApp
    from emtk.docking import Split
    from emtk.testing_realistic import RealisticDriver

    manager = DockManager(Split("h", 0.3, Region("left"), Region("main")), name="ctx")
    for key, title, dock in [("tools", "Tools", "left"), ("a", "Alpha", "main"),
                             ("b", "Beta", "main"), ("c", "Gamma", "main")]:
        manager.add_window(key, title, lambda box: None, dock=dock, core=key in core)
    app = ImApp(lambda: manager.draw((0, 0, 800, 500)))
    driver = RealisticDriver(app, (800, 500), real_painter=False)
    driver.frame(3)
    return manager, driver


def _row(driver, label):
    return next(t[:4] for t in driver.painter.texts if t[5].strip() == label)


def _right_click_tab(manager, driver, key):
    from emtk.events import RIGHT_BUTTON

    rect = next(r for _k, r in manager._tab_rects["main"] if _k == key)
    driver.click((rect[0] + rect[2] / 2, rect[1] + rect[3] / 2), button=RIGHT_BUTTON)
    driver.frame(2)


def test_close_panels_leaves_core_and_kept_windows():
    manager = DockManager(Region("main"))
    manager.add_window("core", "Core", dock="main", core=True)
    manager.add_window("pinned", "Pinned", dock="main", closable=False)
    manager.add_window("a", "A", dock="main")
    manager.add_window("b", "B", dock="main")
    assert manager.close_panels(keep=("a",)) == ["b"]
    assert [k for k, w in manager.windows.items() if w.visible] == ["core", "pinned", "a"]
    assert manager.close_panels() == ["a"]
    assert manager.close_panels() == []
    manager.reset()
    assert all(w.visible for w in manager.windows.values())


def test_right_click_close_all_panels_leaves_only_core_docks():
    manager, driver = _driven()
    _right_click_tab(manager, driver, "b")
    driver.click(_row(driver, "Close all panels"))
    driver.frame(3)
    assert [k for k, w in manager.windows.items() if w.visible] == ["tools"]


def test_right_click_close_other_panels_keeps_the_clicked_one():
    manager, driver = _driven()
    _right_click_tab(manager, driver, "b")
    driver.click(_row(driver, "Close other panels"))
    driver.frame(3)
    assert [k for k, w in manager.windows.items() if w.visible] == ["tools", "b"]


def test_context_menu_has_no_blank_row():
    manager, driver = _driven()
    _right_click_tab(manager, driver, "b")
    scope = next(iter(manager._context_heights))
    items = [t for t in driver.painter.texts if t[5].strip() in (
        "Undock", "Close panel", "Close other panels", "Close all panels",
        "Restore default layout")]
    last_text_bottom = max(t[1] + t[3] for t in items)
    top = min(t[1] for t in items)
    # What is left under the last row is the panel's padding, not another row.
    assert manager._context_heights[scope] - (last_text_bottom - top) < 0.9 * manager._title_h
