from emtk.app import ControlSurface
from emtk.native import CanvasEvents


def test_canvas_close_releases_control_once_and_stops_key_repeat():
    callbacks = {}

    class Canvas:
        def add_event_handler(self, callback, *names):
            callbacks.update({name: callback for name in names})

    class Control:
        closes = 0

        def close(self):
            self.closes += 1

    control = Control()
    surface = ControlSurface(control)
    events = CanvasEvents(Canvas(), surface)
    events._repeat_key = "a"
    callbacks["close"]({})
    callbacks["close"]({})
    surface.close()
    assert control.closes == 1
    assert events._repeat_key is None
