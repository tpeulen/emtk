"""``emtk.qt_host``: a control in a QWidget -- here, that it keeps drawing
while the control is animating, as every other host does."""
from __future__ import annotations

import time


class _Ticker:
    def __init__(self, frames_wanted):
        self.frames = 0
        self.frames_wanted = frames_wanted

    def draw(self, painter, x, y, w, h):
        self.frames += 1

    def animating(self):
        return self.frames < self.frames_wanted


def _pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def test_an_animating_control_gets_frames_without_input(qt_app):
    from emtk.qt_host import ControlHost

    control = _Ticker(frames_wanted=5)
    host = ControlHost(control)
    host.resize(100, 80)
    host.show()
    _pump(qt_app, 0.6)
    assert control.frames >= 5, "the host drew once and stopped"
    drawn = control.frames
    _pump(qt_app, 0.2)
    assert control.frames <= drawn + 1, "an idle control kept being redrawn"
    host.close()
