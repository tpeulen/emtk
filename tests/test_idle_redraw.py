from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.events import LEFT_BUTTON
from emtk.im_core import IO, get_current_context
from emtk.testing import RecordingPainter


def test_closing_a_panel_requests_the_idle_hosts_next_frame():
    docks = DockManager(Region("main"))
    docks.add_window("panel", "Panel", lambda box: im.text("Panel content"), dock="main")
    app = ImApp(lambda: docks.draw((0, 0, 400, 300)))
    app.draw(RecordingPainter(), 0, 0, 400, 300)
    app.pointer_press(390, 8, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 400, 300)
    app.pointer_release(390, 8, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 400, 300)
    assert not docks.window("panel").visible
    assert app.animating()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 400, 300)
    assert "Panel content" not in painter.strings
    assert not app.animating()


def test_unsubmitted_window_no_longer_blocks_pointer_after_one_empty_frame():
    storage = {}
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage):
        im.begin("popup", (0, 0, 200, 200))
        im.text("Popup")
        im.end()
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage):
        pass
    with im.frame(RecordingPainter(), (0, 0, 400, 300), storage=storage,
                  io=IO(mouse_pos=(10, 10))):
        assert get_current_context().hovered_window is None
