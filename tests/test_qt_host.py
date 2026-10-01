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


def test_destroying_hosts_detaches_repaint_callbacks_safely(qt_app):
    """Repeated Qt cleanup must not leave a callback bound to a dying signal."""
    from qtpy import QtCore, QtWidgets

    from emtk.app import ImApp
    from emtk.qt_host import ControlHost

    for _ in range(20):
        control = ImApp(lambda: None)
        parent = QtWidgets.QWidget()
        host = ControlHost(control, parent=parent)
        assert control._frame_request_callback is not None
        parent.deleteLater()
        qt_app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        qt_app.processEvents()
        # Keep the Python wrapper alive after Qt has deleted its C++ child,
        # then deliver the late worker-style repaint request.
        control.request_frame()
        assert control._frame_request_callback is None
        del host


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


def test_a_file_drop_reaches_the_control(qt_app, tmp_path):
    """A file dragged over the host is delivered to the control's drop hook.

    Qt hands drag events to the widget under the pointer and drops them there
    when it ignores them -- they do not climb to an embedding window that
    accepts drops. The host did neither, so an app hosted in Qt (ndX) never
    saw a drop its own window logic was wired for.
    """
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    dropped = []

    class _Droplet:
        def draw(self, painter, x, y, w, h):
            pass

        def files_dropped(self, paths):
            dropped.extend(paths)
            return True

    control = _Droplet()
    host = ControlHost(control)
    assert host.acceptDrops(), "the host must take drops or Qt never asks it"

    csv = tmp_path / "bursts.csv"
    csv.write_text("I_DD,I_DA,I_AA\n10,4,7\n")

    def drag(kind, accept_expected):
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(csv))])
        event_type = (QtGui.QDragEnterEvent if kind == "enter"
                      else QtGui.QDragMoveEvent)
        event = event_type(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                           QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        QtCore.QCoreApplication.sendEvent(host, event)
        assert event.isAccepted() == accept_expected

    drag("enter", True)
    drag("move", True)

    # A non-URL drag (plain text) is refused:
    mime = QtCore.QMimeData()
    mime.setText("no files here")
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, enter)
    assert not enter.isAccepted()

    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(csv))])
    drop = QtGui.QDropEvent(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, drop)
    assert drop.isAccepted()
    assert dropped == [str(csv)]
    host.close()


def test_a_control_without_a_drop_hook_refuses_drops(qt_app, tmp_path):
    """No hook, no acceptance: the drop stays with the embedding window."""
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    host = ControlHost(_Ticker(frames_wanted=0))
    assert host.acceptDrops()

    csv = tmp_path / "x.csv"
    csv.write_text("a\n1\n")
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(csv))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, enter)
    assert not enter.isAccepted()
    host.close()


def test_a_top_level_host_opens_at_a_usable_size(qt_app):
    from emtk.qt_host import ControlHost

    host = ControlHost(_Ticker(frames_wanted=0))
    assert host.width() > 640 and host.height() > 480
    assert host.width() <= qt_app.primaryScreen().availableGeometry().width()


def test_a_control_names_its_own_window_size(qt_app):
    from emtk.qt_host import ControlHost

    control = _Ticker(frames_wanted=0)
    control.preferred_size = (700, 500)
    host = ControlHost(control)
    assert (host.width(), host.height()) == (700, 500)


def test_an_embedded_host_is_left_to_its_layout(qt_app):
    from qtpy import QtWidgets

    from emtk.qt_host import ControlHost

    parent = QtWidgets.QWidget()
    host = ControlHost(_Ticker(frames_wanted=0), parent=parent)
    from emtk.qt_host import DEFAULT_WINDOW_SIZE

    assert (host.width(), host.height()) != DEFAULT_WINDOW_SIZE
    parent.close()


def test_an_on_paths_dropped_control_takes_drops(qt_app, tmp_path):
    """The ``on_paths_dropped`` spelling (most ChiSurf apps) is a drop hook too.

    The host only knew ``files_dropped`` / ``on_files_dropped``, so a drag over such an app was
    refused and its drop never arrived (found by the photon_table / tttr_to_pto / pto_inspector
    ports). It need not return a flag.
    """
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    dropped = []

    class _Paths:
        def draw(self, painter, x, y, w, h):
            pass

        def on_paths_dropped(self, paths):
            dropped.extend(paths)

    host = ControlHost(_Paths())
    f = tmp_path / "a.pto"
    f.write_text("x")
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(f))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                                  QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, enter)
    assert enter.isAccepted()
    drop = QtGui.QDropEvent(QtCore.QPoint(30, 40), QtCore.Qt.CopyAction, mime,
                            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, drop)
    assert drop.isAccepted()
    assert dropped == [str(f)]
    host.close()
