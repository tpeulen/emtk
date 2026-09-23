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

from collections.abc import Callable

__all__ = ["ControlHost", "make_control_host", "host_class"]

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

        def __init__(
            self,
            control,
            font_pt: float = 9.0,
            background: tuple = (30, 32, 38),
            on_change: Callable[[object], None] | None = None,
            parent=None,
        ) -> None:
            super().__init__(parent)
            self.control = control
            self.font_pt = float(font_pt)
            self.background = tuple(background)
            self.on_change = on_change
            self._pressed = False
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.setMouseTracking(True)
            self.setMinimumHeight(80)
            self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)

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
        def mousePressEvent(self, event) -> None:  # noqa: N802
            """Forward a press, with the modifier mask Qt already agrees on."""
            press = getattr(self.control, "press", None)
            if callable(press):
                px, py = self._point(event)
                press(px, py, *self._box(), int(event.modifiers()), 1)
                self._pressed = True
                self._notify()

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            """Forward a double click as ``clicks=2``.

            Qt counts the clicks, so the control does not have to hold a clock
            -- which is exactly the arrangement this package's docstring asks
            for: anything the chrome has no feed for arrives as an argument.
            """
            press = getattr(self.control, "press", None)
            if callable(press):
                px, py = self._point(event)
                press(px, py, *self._box(), int(event.modifiers()), 2)
                self._notify()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            """Forward a drag while a button is down, a hover otherwise."""
            px, py = self._point(event)
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
            release = getattr(self.control, "release", None)
            if callable(release):
                release()
            self.update()

        def wheelEvent(self, event) -> None:  # noqa: N802
            """Forward a wheel notch as three rows, the usual Qt convention."""
            scroll = getattr(self.control, "scroll", None)
            if not callable(scroll):
                return
            delta = (
                event.angleDelta().y()
                if hasattr(event, "angleDelta")
                else event.delta()
            )
            scroll(-3 if delta > 0 else 3)
            self.update()

        def keyPressEvent(self, event) -> None:  # noqa: N802
            """Forward a key press; unhandled keys go on to Qt."""
            key = getattr(self.control, "key", None)
            if callable(key) and key(
                int(event.key()), event.text(), int(event.modifiers())
            ):
                self._notify()
                return
            super().keyPressEvent(event)

    _CLASS = _ControlHost
    return _CLASS


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
