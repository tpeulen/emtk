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
    # Up to 3 s for the five frames: a fixed 0.6 s window failed under the
    # load of the full suite although the host keeps drawing.
    end = time.time() + 3.0
    while control.frames < 5 and time.time() < end:
        _pump(qt_app, 0.05)
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


class _Keys:
    """A control that records key presses, releases and focus loss."""

    def __init__(self):
        self.events = []

    def draw(self, painter, x, y, w, h):
        pass

    def key(self, key, text="", modifiers=0):
        self.events.append(("press", key))
        return True

    def key_release(self, key, text="", modifiers=0):
        self.events.append(("release", key))
        return True

    def focus_lost(self):
        self.events.append(("focus_lost",))


def test_key_releases_reach_the_control_and_auto_repeat_releases_do_not(qt_app):
    from qtpy import QtCore, QtGui

    from emtk.qt_host import ControlHost

    control = _Keys()
    host = ControlHost(control)
    up = QtCore.Qt.Key_Up
    for kind, repeat in ((QtCore.QEvent.KeyPress, False), (QtCore.QEvent.KeyRelease, True),
                         (QtCore.QEvent.KeyPress, True), (QtCore.QEvent.KeyRelease, False)):
        event = QtGui.QKeyEvent(kind, up, QtCore.Qt.NoModifier, "", repeat)
        qt_app.sendEvent(host, event)
    assert control.events == [("press", int(up)), ("press", int(up)), ("release", int(up))]


def test_losing_focus_is_reported(qt_app):
    from qtpy import QtCore, QtGui

    from emtk.qt_host import ControlHost

    control = _Keys()
    host = ControlHost(control)
    qt_app.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert control.events == [("focus_lost",)]


def test_a_drop_the_rich_hook_declines_is_ignored(qt_app, tmp_path):
    """``files_dropped`` returning False refuses the drop, as ``on_files_dropped`` always did."""
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    class _Picky:
        def draw(self, painter, x, y, w, h):
            pass

        def files_dropped(self, paths):
            return False

    host = ControlHost(_Picky())
    f = tmp_path / "a.txt"
    f.write_text("x")
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(f))])
    drop = QtGui.QDropEvent(QtCore.QPoint(5, 5), QtCore.Qt.CopyAction, mime,
                            QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    QtCore.QCoreApplication.sendEvent(host, drop)
    assert not drop.isAccepted()
    host.close()


def test_tab_and_backtab_reach_the_control_through_widget_events(qt_app):
    """Qt must not turn Tab into a focus change before the control sees it."""
    from qtpy import QtCore, QtGui
    from emtk.events import SHIFT_MODIFIER
    from emtk.keys import KEY_TAB
    from emtk.qt_host import ControlHost

    class Control(_Keys):
        def key(self, key, text='', modifiers=0):
            self.events.append((key, modifiers))
            return True

    control = Control()
    host = ControlHost(control)
    for key in (QtCore.Qt.Key_Tab, QtCore.Qt.Key_Backtab):
        qt_app.sendEvent(host, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key,
                                            QtCore.Qt.NoModifier))
    assert control.events == [(KEY_TAB, 0), (KEY_TAB, SHIFT_MODIFIER)]
    assert not host.focusNextPrevChild(True)
    assert not host.focusNextPrevChild(False)
    host.close()


def test_keypad_is_masked_and_real_modifiers_survive_press_and_release(qt_app):
    """macOS keypad decoration on arrow keys is not a keyboard shortcut."""
    from qtpy import QtCore, QtGui
    from emtk.events import SHIFT_MODIFIER, CONTROL_MODIFIER, ALT_MODIFIER, META_MODIFIER
    from emtk.qt_host import ControlHost

    class Control(_Keys):
        def key(self, key, text='', modifiers=0):
            self.events.append(('press', modifiers))
            return True

        def key_release(self, key, text='', modifiers=0):
            self.events.append(('release', modifiers))
            return True

    control = Control()
    host = ControlHost(control)
    mask = SHIFT_MODIFIER | CONTROL_MODIFIER | ALT_MODIFIER | META_MODIFIER
    for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
        qt_app.sendEvent(host, QtGui.QKeyEvent(kind, QtCore.Qt.Key_Left,
                                            QtCore.Qt.KeyboardModifiers(mask)
                                            | QtCore.Qt.KeypadModifier))
    assert control.events == [('press', mask), ('release', mask)]
    host.close()


def test_host_close_closes_a_control_once(qt_app):
    """A repeated close event cannot run shutdown or persistence twice."""
    from qtpy import QtGui
    from emtk.qt_host import ControlHost

    class Control(_Ticker):
        closed = 0

        def close(self):
            self.closed += 1

    control = Control(0)
    host = ControlHost(control)
    host.close()
    host.closeEvent(QtGui.QCloseEvent())
    assert control.closed == 1


def test_host_restores_position_size_and_reports_moves(qt_app):
    """Persisted top-level geometry wins over the first-launch size hint."""
    from emtk.qt_host import ControlHost

    control = _Ticker(0)
    control.preferred_size = (500, 350)
    control.window_size = (600, 400)
    control.window_pos = (70, 80)
    moves, sizes, screens = [], [], []
    control.window_moved = lambda x, y: moves.append((x, y))
    control.window_resized = lambda w, h: sizes.append((w, h))
    control.window_screen_changed = screens.append
    host = ControlHost(control)
    host.show()
    qt_app.processEvents()
    assert (host.width(), host.height()) == (600, 400)
    assert (host.x(), host.y()) == (70, 80)
    assert screens
    host.move(110, 120)
    host.resize(620, 420)
    qt_app.processEvents()
    assert moves[-1] == (110, 120)
    assert sizes[-1] == (620, 420)
    host.close()


def test_saved_offscreen_position_is_not_applied(qt_app):
    """A monitor removed since the last launch cannot hide the window."""
    from emtk.qt_host import ControlHost

    control = _Ticker(0)
    control.window_pos = (100000, 100000)
    host = ControlHost(control)
    assert (host.x(), host.y()) != control.window_pos
    host.close()


def test_pointer_and_wheel_modifiers_are_masked(qt_app):
    """The rich pointer path sees the same modifier vocabulary as keys."""
    from qtpy import QtCore, QtGui
    from emtk.events import CONTROL_MODIFIER
    from emtk.qt_host import ControlHost

    class Control(_Ticker):
        def __init__(self):
            super().__init__(0)
            self.modifiers = []

        def pointer_press(self, x, y, button, modifiers, clicks):
            self.modifiers.append(modifiers)

        def pointer_move(self, x, y, buttons, modifiers):
            self.modifiers.append(modifiers)

        def pointer_release(self, x, y, button, modifiers):
            self.modifiers.append(modifiers)

        def wheel(self, x, y, steps, modifiers):
            self.modifiers.append(modifiers)

    control = Control()
    host = ControlHost(control)
    mods = QtCore.Qt.ControlModifier | QtCore.Qt.KeypadModifier
    for kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonDblClick,
                 QtCore.QEvent.MouseMove, QtCore.QEvent.MouseButtonRelease):
        event = QtGui.QMouseEvent(kind, QtCore.QPointF(30, 40), QtCore.Qt.LeftButton,
                                  QtCore.Qt.LeftButton, mods)
        qt_app.sendEvent(host, event)
    wheel = QtGui.QWheelEvent(QtCore.QPointF(30, 40), QtCore.QPointF(30, 40),
                              QtCore.QPoint(0, 0), QtCore.QPoint(0, 120),
                              QtCore.Qt.NoButton, mods, QtCore.Qt.NoScrollPhase, False)
    qt_app.sendEvent(host, wheel)
    assert control.modifiers == [CONTROL_MODIFIER] * 5
    host.close()


def test_initial_tab_schedules_an_idle_imapp_frame(qt_app):
    """Queued input needs a redraw before WantCaptureKeyboard can be true."""
    from emtk import im, keys
    from emtk.app import ImApp
    from emtk.testing import RecordingPainter
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    app = ImApp(lambda: im.button('Run analysis'))
    app.draw(RecordingPainter(), 0, 0, 320, 200)
    host = ControlHost(app)
    updates = []
    host.update = lambda: updates.append(True)
    try:
        qt_app.sendEvent(host, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, keys.KEY_TAB, QtCore.Qt.NoModifier))
        assert updates
        app.draw(RecordingPainter(), 0, 0, 320, 200)
        assert app.storage.get('__nav_id__') is not None
    finally:
        host.close()
