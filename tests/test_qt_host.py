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
