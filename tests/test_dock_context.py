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
    render(manager, storage, IO(mouse_pos=(489, 8),
        mouse_clicked=[True, False, False], mouse_down=[True, False, False]))
    render(manager, storage, IO(mouse_pos=(489, 8),
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
