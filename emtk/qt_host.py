"""Put any painter-level control inside a Qt widget.

Why one widget and not one per control
--------------------------------------
The controls in this package are deliberately toolkit-free: they draw through
:class:`~.painter.Painter` and take their input as numbers. That is what lets
them run in the viewport chrome, on the GPU painter and in the browser -- and
it is also what stopped them being usable anywhere Qt expects a ``QWidget``,
which is most of ChiSurf.

Writing a ``QWidget`` subclass per control would undo the seam one control at a
time: each would re-derive the same four event translations, and each would be
a second place the control's behaviour lives. So there is exactly one host. It
knows nothing about any particular control -- it paints whatever it was given
through :class:`~.qt_painter.QtPainter` and forwards presses, drags, wheels and
keys.

The translation is nearly free, and not by accident:
:mod:`emtk.keys` and :mod:`emtk.events` took **Qt's** numeric
values as the engine's own, precisely so that a Qt event's ``key()`` and
``modifiers()`` could be passed straight through. The browser build translates;
this one does not have to.

Why the class is built on first call
------------------------------------
Importing this module must not be what pulls a GUI toolkit into a headless
process -- emtk is meant to run with Qt as an *option*, and
``test_engine_is_portable.py`` holds the line with a shrinking list of modules
allowed to import Qt at module scope. A ``class ControlHost(QtWidgets.QWidget)``
at module level would have to join that list. So the class is defined inside
:func:`_host_class` and cached, exactly as :mod:`.qt_painter` imports Qt inside
its constructor. :func:`ControlHost` stays spelled like the constructor it
replaces, so no call site knows the difference.

What this makes possible
------------------------
It is the seam that makes a port *AutoForm-conform*. ``AutoForm`` builds a form
from a ``view.json`` and needs a ``QWidget`` for a custom section; a host
control is not one. With this host, a section is a dozen lines that construct a
control and bind it to a model attribute -- see
``chisurf/gui/autoform/sections/code_editor_section.py`` and its memory-editor
neighbour -- and the *same* control object is what the viewport chrome draws.
One implementation, two hosts, no parity to maintain between them.
"""
from __future__ import annotations

import threading
import weakref
from collections.abc import Callable

from .font import DEFAULT_FONT_PT

__all__ = ["ControlHost", "DEFAULT_WINDOW_SIZE", "make_control_host", "host_class"]

#: What a stand-alone window opens at when its control names no size: enough
#: for a tool panel beside a plot, which is what every port in ChiSurf is.
DEFAULT_WINDOW_SIZE = (1200, 800)

#: The built class, cached. Rebuilding it per widget would give every host its
#: own type, which breaks ``isinstance`` and makes Qt re-register the signal.
_CLASS = None


def host_class():
    """Return the ``QWidget`` subclass that hosts a control, building it once.

    Returns
    -------
    type
        A ``QtWidgets.QWidget`` subclass.

    Raises
    ------
    ImportError
        If no Qt binding is installed.
    """
    global _CLASS
    if _CLASS is not None:
        return _CLASS

    from qtpy import QtCore, QtGui, QtWidgets

    class _ControlHost(QtWidgets.QWidget):
        """A ``QWidget`` that draws one painter-level control and drives it.

        Parameters
        ----------
        control : object
            The control. Must have ``draw(painter, x, y, w, h)``; ``press``,
            ``drag``, ``release``, ``hover``, ``key`` and ``scroll`` are used
            when present, so a control that has none of them still hosts fine.
        font_pt : float, optional
            Point size of the monospaced font the control is drawn with. The
            two editors assume a monospaced face, as their references do.
        background : tuple, optional
            Filled before the control draws. The chrome is normally drawn over
            a lit 3-D scene and most controls do not paint their own backdrop;
            in a form there is nothing behind them, so the host supplies one.
        on_change : callable, optional
            Called with the control after any event the control consumed. This
            is what a form binds to.
        parent : QWidget, optional
        """

        #: Emitted after an event the control consumed. A signal *and* the
        #: ``on_change`` callback: a section wires the callback, a dialog
        #: connects the signal, and neither has to adapt to the other.
        changed = QtCore.Signal()
        frame_requested = QtCore.Signal()
        is_emtk: bool = True
        _emtk_native: bool = True

        def __init__(
            self,
            control,
            font_pt: float = DEFAULT_FONT_PT,
            background: tuple = (30, 32, 38),
            on_change: Callable[[object], None] | None = None,
            parent=None,
        ) -> None:
            super().__init__(parent)
            self.control = control
            self.frame_requested.connect(self.update)
            set_callback = getattr(control, "set_frame_request_callback", None)
            if callable(set_callback):
                # Store a weak host reference instead of a bound Qt signal.
                # A control may outlive a Qt form that embedded it, and worker
                # notifications can arrive after that form's C++ widget dies.
                control_ref = weakref.ref(control)
                host_ref = weakref.ref(self)
                active = threading.Event()
                active.set()

                def detach():
                    active.clear()
                    owner = control_ref()
                    if owner is not None:
                        setter = getattr(owner, "set_frame_request_callback", None)
                        if callable(setter):
                            setter(None)

                def request_frame():
                    if not active.is_set():
                        return
                    host = host_ref()
                    if host is None:
                        detach()
                        return
                    try:
                        host.frame_requested.emit()
                    except RuntimeError:
                        # SIP/Shiboken report a deleted C++ QObject this way.
                        # The Python control can remain alive in a form model.
                        detach()

                self._detach_control_callback = detach
                self._control_callback_finalizer = weakref.finalize(self, detach)
                set_callback(request_frame)
            self.font_pt = float(font_pt)
            bg_vals = tuple(background[:3])
            if any(isinstance(c, float) and c <= 1.0 for c in bg_vals):
                self.background = tuple(int(round(c * 255)) for c in bg_vals)
            else:
                self.background = tuple(int(round(c)) for c in bg_vals)
            self.on_change = on_change
            self._pressed = False
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.setMouseTracking(True)
            self.setMinimumHeight(80)
            self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
            # A file dragged over the control is the control's event, not the
            # embedding window's: Qt delivers drag events to the widget under
            # the pointer and drops them there when it ignores them -- they do
            # not climb to a parent that accepts drops. Without this an app
            # hosted here (ndX) never sees a drop its own window is wired for.
            self.setAcceptDrops(True)
            use_qt_clipboard()        # copy *and* paste through QClipboard
            if parent is None:
                self._size_as_window()

        # -- sizing ------------------------------------------------------- #
        def window_size_hint(self) -> tuple[int, int]:
            """The size a stand-alone window for this control opens at.

            The control's own ``preferred_size`` (a ``(w, h)`` pair, or a
            callable returning one) wins; otherwise :data:`DEFAULT_WINDOW_SIZE`.
            Either is clamped to 92 % of the screen the window opens on, so a
            large default never opens taller than the display.
            """
            wanted = getattr(self.control, "preferred_size", None)
            if callable(wanted):
                wanted = wanted()
            try:
                width, height = (int(wanted[0]), int(wanted[1]))
            except (TypeError, ValueError, IndexError):
                width, height = DEFAULT_WINDOW_SIZE
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                width = min(width, int(area.width() * 0.92))
                height = min(height, int(area.height() * 0.92))
            return max(width, 240), max(height, 160)

        def _size_as_window(self) -> None:
            """Give a parentless host a usable size.

            Qt opens a bare widget at 640 x 480, which is small enough to cut
            off the toolbar of every tool that is shown in a window of its own.
            A host that is embedded (it has a parent) is sized by its layout
            and is left alone.
            """
            self.resize(*self.window_size_hint())

        # -- painting ----------------------------------------------------- #
        def paintEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Draw the control across the whole widget."""
            from .qt_painter import QtPainter

            painter = QtGui.QPainter(self)
            try:
                painter.fillRect(self.rect(), QtGui.QColor(*self.background))
                surface = QtPainter(painter, self.font_pt)
                self.control.draw(
                    surface, 0.0, 0.0, float(self.width()), float(self.height())
                )
            finally:
                painter.end()
            if getattr(self.control, "close_requested", False):
                QtCore.QTimer.singleShot(0, self.window().close)
                return
            from .app import window_title

            title = window_title(self.control)
            if title is not None and title != self.window().windowTitle():
                self.window().setWindowTitle(title)
            # A control that is animating (a playback, results streaming in)
            # needs frames without input, as it gets in every other host:
            # ask for the next one once this one is on screen.
            animating = getattr(self.control, "animating", None)
            if callable(animating) and animating():
                QtCore.QTimer.singleShot(16, self.update)
                return
            # Or one frame later, though nothing happens -- a tooltip's
            # delay. One timer, restarted: never a stream of frames.
            from .app import next_frame_in

            delay = next_frame_in(self.control)
            if delay is not None:
                if getattr(self, "_wake", None) is None:
                    self._wake = QtCore.QTimer(self)
                    self._wake.setSingleShot(True)
                    self._wake.timeout.connect(self.update)
                self._wake.start(max(int(delay * 1000.0 + 0.5), 1))
            elif getattr(self, "_wake", None) is not None:
                self._wake.stop()

        def closeEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Detach queued repaint callbacks before closing the widget."""
            detach = getattr(self, "_detach_control_callback", None)
            if callable(detach):
                detach()
                self._detach_control_callback = None
            super().closeEvent(event)

        def _box(self) -> tuple[float, float, float, float]:
            """The box the control is drawn in: the whole widget."""
            return (0.0, 0.0, float(self.width()), float(self.height()))

        def _notify(self) -> None:
            """Repaint and tell whoever is listening."""
            self.update()
            if self.on_change is not None:
                self.on_change(self.control)
            self.changed.emit()

        @staticmethod
        def _point(event) -> tuple[float, float]:
            """A mouse event's position, across the Qt versions qtpy spans."""
            position = getattr(event, "position", None)
            if callable(position):
                point = position()
                return (float(point.x()), float(point.y()))
            return (float(event.x()), float(event.y()))

        # -- input -------------------------------------------------------- #
        def _rich(self, name: str):
            """The control's rich pointer hook *name*, when it has all four.

            The classic contract (``press``/``drag``/``hover``/``release``/
            ``scroll``) knows one button, so a right click arrived as a left
            one and a middle-button pan did not arrive at all. A control that
            speaks :class:`emtk.app.ImApp`'s ``pointer_press``/``pointer_move``/
            ``pointer_release``/``wheel`` is given every button, as the GPU
            hosts give it; Qt's button and modifier codes are emtk's
            (:mod:`emtk.events`), so they pass through unchanged.
            """
            control = self.control
            if all(callable(getattr(control, hook, None)) for hook in
                   ("pointer_press", "pointer_move", "pointer_release", "wheel")):
                return getattr(control, name)
            return None

        def mousePressEvent(self, event) -> None:  # noqa: N802
            """Forward a press, with the modifier mask Qt already agrees on."""
            px, py = self._point(event)
            rich = self._rich("pointer_press")
            if rich is not None:
                rich(px, py, int(event.button()), int(event.modifiers()), 1)
                self._pressed = True
                self._notify()
                return
            press = getattr(self.control, "press", None)
            if callable(press):
                press(px, py, *self._box(), int(event.modifiers()), 1)
                self._pressed = True
                self._notify()

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            """Forward a double click as ``clicks=2``.

            Qt counts the clicks, so the control does not have to hold a clock
            -- which is exactly the arrangement this package's docstring asks
            for: anything the chrome has no feed for arrives as an argument.
            """
            px, py = self._point(event)
            rich = self._rich("pointer_press")
            if rich is not None:
                rich(px, py, int(event.button()), int(event.modifiers()), 2)
                self._pressed = True
                self._notify()
                return
            press = getattr(self.control, "press", None)
            if callable(press):
                press(px, py, *self._box(), int(event.modifiers()), 2)
                self._notify()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            """Forward a drag while a button is down, a hover otherwise."""
            px, py = self._point(event)
            rich = self._rich("pointer_move")
            if rich is not None:
                rich(px, py, int(event.buttons()), int(event.modifiers()))
                self.update()
                return
            if self._pressed:
                drag = getattr(self.control, "drag", None)
                if callable(drag):
                    drag(px, py, *self._box())
                    self.update()
                return
            hover = getattr(self.control, "hover", None)
            if callable(hover):
                hover(px, py, *self._box())
                self.update()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            """Forward the button coming up."""
            self._pressed = False
            rich = self._rich("pointer_release")
            if rich is not None:
                px, py = self._point(event)
                rich(px, py, int(event.button()), int(event.modifiers()))
                self._notify()
                return
            release = getattr(self.control, "release", None)
            if callable(release):
                release()
            self.update()

        def wheelEvent(self, event) -> None:  # noqa: N802
            """Forward a wheel notch as three rows, the usual Qt convention."""
            delta = (
                event.angleDelta().y()
                if hasattr(event, "angleDelta")
                else event.delta()
            )
            rich = self._rich("wheel")
            if rich is not None:
                # Notches, up positive -- Dear ImGui's sign, and Qt's.
                point = event.position() if hasattr(event, "position") else event.pos()
                rich(float(point.x()), float(point.y()), delta / 120.0,
                     int(event.modifiers()))
                self.update()
                return
            scroll = getattr(self.control, "scroll", None)
            if not callable(scroll):
                return
            scroll(-3 if delta > 0 else 3)
            self.update()

        def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Forward a key press; unhandled keys go on to Qt."""
            key = getattr(self.control, "key", None)
            if callable(key) and key(
                int(event.key()), event.text(), int(event.modifiers())
            ):
                self._notify()
                return
            super().keyPressEvent(event)

        # -- file drops ---------------------------------------------------- #
        def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Accept file URL drags when the control takes drops."""
            if not event.mimeData().hasUrls():
                event.ignore()
                return
            if callable(getattr(self.control, "files_dropped", None)) \
                    or callable(getattr(self.control, "on_files_dropped", None)):
                event.acceptProposedAction()
            else:
                event.ignore()

        def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Accept URL moves over the control."""
            event.acceptProposedAction()

        def dropEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Hand the dropped local paths to the control and repaint it.

            The rich hook (:meth:`emtk.app.ControlSurface`'s ``files_dropped``)
            is preferred, the surface verb (:meth:`~.app.Surface`'s
            ``on_files_dropped``, answered for by :class:`~.app.ImApp`) takes
            the paths when there is no rich one. A drop that opens data asks
            for the frame that shows it itself (``_frame_due``); the repaint
            here covers a control that changes without asking.
            """
            paths = [url.toLocalFile() for url in event.mimeData().urls()]
            paths = [p for p in paths if p]
            rich = getattr(self.control, "files_dropped", None)
            if callable(rich):
                rich(paths)
            else:
                on_files = getattr(self.control, "on_files_dropped", None)
                if not callable(on_files) or not on_files(paths):
                    event.ignore()
                    return
            event.acceptProposedAction()
            self._notify()

    _CLASS = _ControlHost
    return _CLASS


def use_qt_clipboard() -> bool:
    """Route :mod:`emtk.clipboard` through Qt's ``QClipboard``, both ways.

    Every Qt host calls it; returns whether there was a Qt to route through.
    """
    try:
        from qtpy import QtWidgets  # noqa: PLC0415
    except ImportError:
        return False
    from . import clipboard  # noqa: PLC0415

    def board():
        return QtWidgets.QApplication.clipboard()

    clipboard.set_hook(lambda text: board().setText(text), lambda: board().text())
    return True


def ControlHost(control, **kwargs):  # noqa: N802 - it stands in for a class
    """Build a host widget around *control*.

    Spelled like a class because it replaces one: call sites read
    ``ControlHost(editor, on_change=...)`` either way, and the module stays
    importable where there is no Qt.

    Parameters
    ----------
    control : object
        Anything with the package's ``draw``/``press``/``key`` contract.
    **kwargs
        ``font_pt``, ``background``, ``on_change``, ``parent``.

    Returns
    -------
    QtWidgets.QWidget
    """
    return host_class()(control, **kwargs)


#: The older, more explicit spelling. Kept because "make a host" reads better
#: at a call site that is not pretending to construct a class.
make_control_host = ControlHost
