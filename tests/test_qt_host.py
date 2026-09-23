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


def test_the_window_takes_the_controls_title(qt_app):
    from emtk.qt_host import ControlHost

    control = _Ticker(frames_wanted=0)
    control.window_title = "ndX -- m000.bur"
    host = ControlHost(control)
    host.resize(100, 80)
    host.show()
    _pump(qt_app, 0.1)
    assert host.windowTitle() == "ndX -- m000.bur"
    host.close()


def test_the_qimage_cache_does_not_hand_a_new_texture_a_dead_ones_picture(qt_app):
    """An id is reused as soon as its texture dies; a cache keyed on the id
    and the revision alone drew the new texture as the old one's QImage.
    The reuse is played the way it happens: the dead entry under the new
    texture's id."""
    import gc

    from emtk.qt_painter import QtPainter
    from emtk.texture import Texture

    old = Texture(2, 2)
    old.fill((255, 0, 0, 255))
    QtPainter._qimage(old, 2, 2)
    entry = QtPainter._image_cache.pop(id(old))
    del old
    gc.collect()
    new = Texture(3, 1)
    new.fill((0, 0, 255, 255))
    QtPainter._image_cache[id(new)] = entry
    image = QtPainter._qimage(new, 3, 1)
    assert (image.width(), image.height()) == (3, 1)
    assert image.pixelColor(0, 0).blue() == 255


def test_an_im_app_gets_every_button_and_the_wheel(qt_app):
    """A right click is a right click, and a middle-button drag reaches the app.

    The classic contract carries one button, so under Qt an :class:`ImApp`
    saw a right click as a left one (a context menu opened *and* the row under
    it was pressed) and never saw the middle button a node editor pans with.
    """
    from qtpy import QtCore, QtGui

    from emtk.app import ImApp
    from emtk.qt_host import ControlHost

    app = ImApp(lambda: None)
    host = ControlHost(app)
    host.resize(200, 120)

    def mouse(kind, button, buttons):
        event = QtGui.QMouseEvent(kind, QtCore.QPointF(30.0, 40.0), button, buttons,
                                  QtCore.Qt.NoModifier)
        QtCore.QCoreApplication.sendEvent(host, event)

    mouse(QtCore.QEvent.MouseButtonPress, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
    assert app.io.mouse_clicked[1] and not app.io.mouse_clicked[0]
    mouse(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.RightButton, QtCore.Qt.NoButton)
    assert app.io.mouse_released[1]

    mouse(QtCore.QEvent.MouseButtonPress, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton)
    assert app.io.mouse_down[2]
    mouse(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
    assert not app.io.mouse_down[2]

    wheel = QtGui.QWheelEvent(QtCore.QPointF(30.0, 40.0), QtCore.QPointF(30.0, 40.0),
                              QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                              QtCore.Qt.NoButton, QtCore.Qt.NoModifier,
                              QtCore.Qt.NoScrollPhase, False)
    QtCore.QCoreApplication.sendEvent(host, wheel)
    assert app.io.mouse_wheel == 1.0, "one notch up is +1, as in Dear ImGui"
    host.close()
