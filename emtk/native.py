"""A desktop window with no GUI toolkit: ``rendercanvas`` opens it, wgpu draws it.

What this is
------------
The desktop twin of :mod:`emtk.web`. Both drive an :class:`emtk.app.Surface`
-- a control lifted by :class:`~emtk.app.ControlSurface`, or an application
that renders its own scene -- and both translate their platform's events into
emtk's vocabulary before the surface sees them. Here the platform is a
``rendercanvas`` canvas, whose events are the jupyter-rfb/DOM vocabulary a
browser also speaks, so the two translations are nearly one.

Three pieces, usable separately:

* :func:`canvas_module` / :func:`open_canvas` -- pick a ``rendercanvas``
  backend **explicitly** and open a window on it;
* :class:`CanvasEvents` -- the event translation, onto any object with the
  :class:`~emtk.app.Surface` ``on_*`` handlers. An application with a draw
  loop of its own (a 3-D viewport that owns its canvas) uses just this;
* :class:`NativeHost` -- all of it: a window, a device, a surface, a loop.

Run an app::

    python -m emtk.native --app pkg.module:make_app

Choosing a backend
------------------
Never through ``rendercanvas.auto``: its last fallback imports PyQt5 and
selects Qt whenever Qt is installed, which is exactly what a toolkit-free host
exists to avoid. :func:`canvas_module` names the backend it wants -- ``glfw``
for a window when the ``glfw`` package is present, ``offscreen`` otherwise --
and a backend asked for by name (argument or ``EMTK_CANVAS``) is imported as
asked, its failure raised rather than silently swapped.

Nothing here imports ``rendercanvas``, ``glfw`` or ``wgpu`` at module scope.
"""
from __future__ import annotations

import importlib
import math
import logging
import os
import sys
from collections.abc import Callable, Sequence

from .events import (CONTROL_MODIFIER, META_MODIFIER, NO_BUTTON, button_from_canvas,
                     modifiers_from_canvas)
from .keys import KEY_ENTER, KEY_ESCAPE, KEY_RETURN, key_from_dom, letter_of

__all__ = [
    "CHAR_BACKENDS",
    "DEFAULT_MAX_FPS",
    "DEFAULT_WINDOW_SIZE",
    "INTERACTIVE_BACKENDS",
    "SHIFT_MAP",
    "WHEEL_NOTCH",
    "CanvasEvents",
    "NativeHost",
    "canvas_module",
    "centred_position",
    "configure_surface",
    "event_types",
    "fit_to_screen",
    "screen_rect",
    "screen_workarea",
    "open_canvas",
    "window_hints",
    "wheel_steps",
    "launch_qt_first",
    "main",
]

logger = logging.getLogger(__name__)
#: ``EMTK_TRACE_INPUT=1``: every raw button event, the backend's inside/lock flags and
#: what was delivered, to ``~/.cache/emtk/input-trace.log`` -- the evidence for "a click
#: did not land", which no headless driver reproduces (it never goes through glfw).
input_trace = logging.getLogger("emtk.input")


def _start_input_trace() -> None:
    import os  # noqa: PLC0415

    if not os.environ.get("EMTK_TRACE_INPUT") or input_trace.handlers:
        return
    import pathlib  # noqa: PLC0415

    folder = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / "emtk"
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(folder / "input-trace.log", mode="w")
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(message)s", "%H:%M:%S"))
    input_trace.addHandler(handler)
    input_trace.setLevel(logging.DEBUG)
    input_trace.propagate = False

#: The window opened when nothing says otherwise, in logical pixels.
DEFAULT_WINDOW_SIZE = (1280, 860)

#: Frame-rate ceiling for a window. A **guard**, not a target: presentation is
#: vsynced, so the display paces the frames. A ceiling at or below the refresh
#: rate beats against the vsync grid and *halves* the rate -- rendercanvas'
#: own default of 30 gave a hard 15 fps; 60 gave a hard 30 on a 120 Hz screen
#: -- so it is set well above any refresh rate a screen has.
DEFAULT_MAX_FPS = 240.0

#: Backends that put a real window on a real screen without a GUI toolkit,
#: most preferred first. ``glfw`` needs the ``glfw`` package, a small ctypes
#: wrapper that pulls in nothing else.
INTERACTIVE_BACKENDS = ("glfw",)

#: One notch of a ``rendercanvas`` wheel event. Its ``dy`` follows the DOM's
#: ``WheelEvent.deltaY`` -- positive *downwards* -- where emtk's steps are
#: positive away from the user, so :func:`wheel_steps` flips the sign.
WHEEL_NOTCH = 100.0

#: rendercanvas backends that emit a layout-aware ``char`` event beside the key
#: event: glfw through ``set_char_callback``, Qt and wx through
#: ``_char_input_event``. The rule for adding to this list is exactly that the
#: backend module calls one of those, and ``tests/test_native_events.py``
#: checks it against the installed backends' source. The Qt shims (``pyqt5``,
#: ``pyside6``, ...) re-export ``rendercanvas.qt``'s class and are matched by
#: the *defining* module.
CHAR_BACKENDS = ("glfw", "qt", "wx")

#: What a US keyboard produces with shift held, for a backend with no ``char``
#: event. rendercanvas' glfw handler says so in its own comment: shift+5
#: reports ``5``, not ``%``. US layout deliberately -- a documented assumption
#: beats a guess at others; letters and unshifted keys work on every layout.
SHIFT_MAP = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?",
}


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
def canvas_module(backend: str | None = None, env: str = "EMTK_CANVAS"):
    """Import and return the ``rendercanvas`` backend module to draw on.

    Parameters
    ----------
    backend : str, optional
        A backend name (``"glfw"``, ``"offscreen"``, ``"qt"``, ...). When
        ``None``, the environment variable *env* is consulted, and after that
        an interactive backend is tried before the offscreen one.
    env : str, optional
        The environment variable naming a backend -- an application passes
        its own (``MYAPP_CANVAS``).

    Returns
    -------
    module
        A module exposing ``RenderCanvas`` and ``loop``.
    """
    name = (backend or os.environ.get(env, "")).strip()
    if name:
        return importlib.import_module(f"rendercanvas.{name}")
    for candidate in INTERACTIVE_BACKENDS:
        try:
            return importlib.import_module(f"rendercanvas.{candidate}")
        except Exception:  # noqa: BLE001 - not installed, or no display
            continue
    return importlib.import_module("rendercanvas.offscreen")


_QT_LAUNCHED = False


def launch_qt_first() -> bool:
    """Let a ``QApplication`` that has not run yet launch AppKit before glfw does (macOS).

    Qt's first ``processEvents`` on macOS calls ``[NSApp run]`` and waits for its own
    application delegate's *did finish launching* to stop it again. glfw, initialised in
    between, makes itself the delegate and finishes the launch on its own -- so Qt's
    notification never comes and the Qt event loop blocks forever, at 0 % CPU: the
    "test_qt_host hangs in the full suite" symptom (a test that made a ``QApplication``,
    then one that opened a glfw window, then a Qt host). Spinning Qt once first lets it
    launch AppKit under its own delegate; glfw then joins a running application.

    Returns ``True`` when a Qt application was spun. A no-op off macOS, without Qt, and
    after the first call.
    """
    global _QT_LAUNCHED
    if _QT_LAUNCHED or sys.platform != "darwin":
        return False
    for name in ("PyQt5.QtWidgets", "PySide6.QtWidgets", "PyQt6.QtWidgets", "PySide2.QtWidgets"):
        widgets = sys.modules.get(name)
        app = widgets.QApplication.instance() if widgets is not None else None
        if app is not None:
            app.processEvents()
            _QT_LAUNCHED = True
            return True
    return False


def open_canvas(module, size=DEFAULT_WINDOW_SIZE, title: str = "emtk",
                max_fps: float = DEFAULT_MAX_FPS, present_method: str = "auto",
                decorated: bool = True, floating: bool = False,
                transparent: bool = False, centred: bool = False):
    """Open a canvas on *module*, drawing on demand.

    Parameters
    ----------
    module : module
        From :func:`canvas_module`.
    size : tuple of int, optional
        Logical size.
    title : str, optional
    max_fps : float, optional
        See :data:`DEFAULT_MAX_FPS`; given explicitly because rendercanvas'
        default of 30 halves the rate on any display.
    present_method : str, optional
        ``"auto"`` (the library's choice), ``"screen"`` or ``"bitmap"``. A
        backend that cannot honour an explicit choice falls back to the
        library's, with a warning -- a setting for debugging a display must
        not stop the window opening.
    decorated, floating, transparent, centred : bool, optional
        The window's kind, honoured by the glfw backend (others open an
        ordinary window): ``decorated=False`` has no title bar or border,
        ``floating`` stays above other windows, ``transparent`` lets the
        framebuffer's alpha show the desktop through (the surface must then
        be configured premultiplied, see :class:`NativeHost`), ``centred``
        opens it in the middle of the primary screen's work area. A splash
        screen is all four.

    Returns
    -------
    rendercanvas.BaseRenderCanvas
    """
    options = {} if present_method in (None, "", "auto") else {"present_method": present_method}
    launch_qt_first()
    workarea = screen_workarea(module)
    size = fit_to_screen(size, workarea)
    hints = window_hints(decorated=decorated, floating=floating, transparent=transparent,
                         position=centred_position(size, screen_rect(module)) if centred
                         else None)
    with _glfw_hints(module, hints):
        try:
            return module.RenderCanvas(size=size, title=title, max_fps=max_fps,
                                       update_mode="ondemand", **options)
        except Exception:  # noqa: BLE001 - a backend that cannot honour it
            if not options:
                raise
            logger.warning("present_method=%r is not available here; falling back "
                           "to the library's own choice", present_method)
            return module.RenderCanvas(size=size, title=title, max_fps=max_fps,
                                       update_mode="ondemand")


def window_hints(decorated: bool = True, floating: bool = False, transparent: bool = False,
                 position: tuple | None = None) -> dict:
    """The glfw window hints for a window of this kind, by glfw attribute name.

    Only what differs from glfw's defaults is listed, so an ordinary window
    gets no hints at all. *position* is in screen coordinates (``POSITION_X``
    and ``POSITION_Y``, glfw 3.4): the window opens there instead of being
    moved after it has been shown.
    """
    hints: dict = {}
    if not decorated:
        hints["DECORATED"] = False
    if floating:
        hints["FLOATING"] = True
    if transparent:
        hints["TRANSPARENT_FRAMEBUFFER"] = True
    if position is not None:
        hints["POSITION_X"] = int(position[0])
        hints["POSITION_Y"] = int(position[1])
    return hints


class _glfw_hints:
    """Set *hints* (see :func:`window_hints`) for the next glfw window, then back to glfw's defaults.

    rendercanvas sets its own hints and never resets the others, so a hint
    left behind would shape every window opened after it.
    """

    def __init__(self, module, hints: dict) -> None:
        self.hints = hints if getattr(module, "__name__", "").rsplit(".", 1)[-1] == "glfw" else {}

    def __enter__(self):
        if self.hints:
            import glfw  # noqa: PLC0415

            glfw.init()
            for name, value in self.hints.items():
                attribute = getattr(glfw, name, None)
                if attribute is not None:  # an older glfw lacks the 3.4 hints
                    glfw.window_hint(attribute, value)
        return self

    def __exit__(self, *_exc) -> None:
        if self.hints:
            import glfw  # noqa: PLC0415

            glfw.default_window_hints()


def screen_rect(module) -> tuple | None:
    """The primary screen's work area as ``(x, y, width, height)`` in glfw screen coordinates.

    ``None`` when *module* is not the glfw backend or glfw cannot say.
    """
    if getattr(module, "__name__", "").rsplit(".", 1)[-1] != "glfw":
        return None
    try:
        import glfw  # noqa: PLC0415

        if not glfw.init():
            return None
        monitor = glfw.get_primary_monitor()
        if not monitor:
            return None
        x, y, width, height = glfw.get_monitor_workarea(monitor)
        scale = 1.0
        if sys.platform != "darwin":  # screen coordinates are physical there
            scale = float(glfw.get_monitor_content_scale(monitor)[0]) or 1.0
    except Exception:  # noqa: BLE001 - no display, or an old glfw
        return None
    if width <= 0 or height <= 0:
        return None
    return (x, y, width, height, scale)


def centred_position(size, rect) -> tuple | None:
    """Where a window of logical *size* sits centred in *rect* (from :func:`screen_rect`).

    Returns screen coordinates, or ``None`` when *rect* is unknown.

    >>> centred_position((500, 300), (0, 25, 1512, 957, 1.0))
    (506, 353)
    >>> centred_position((500, 300), (0, 0, 3840, 2160, 2.0))  # physical screen coordinates
    (1420, 780)
    """
    if not rect:
        return None
    x, y, width, height = rect[:4]
    scale = float(rect[4]) if len(rect) > 4 else 1.0
    w, h = float(size[0]) * scale, float(size[1]) * scale
    return (int(x + max(0.0, (width - w) / 2.0)), int(y + max(0.0, (height - h) / 2.0)))


#: Logical pixels a window's frame takes beyond its content -- a title bar.
#: Only used to keep a requested size on screen; generous rather than exact.
WINDOW_FRAME = (0, 40)


def screen_workarea(module) -> tuple | None:
    """The primary screen's usable area, ``(width, height)`` in **logical** pixels.

    ``None`` when *module* is not the glfw backend or glfw cannot say. glfw
    reports the work area in screen coordinates, which are logical on macOS
    and physical elsewhere; the monitor's content scale converts the latter.
    """
    if getattr(module, "__name__", "").rsplit(".", 1)[-1] != "glfw":
        return None
    try:
        import glfw  # noqa: PLC0415

        if not glfw.init():  # idempotent; the canvas calls it again
            return None
        monitor = glfw.get_primary_monitor()
        if not monitor:
            return None
        _x, _y, width, height = glfw.get_monitor_workarea(monitor)
        scale = 1.0
        if sys.platform != "darwin":
            scale = float(glfw.get_monitor_content_scale(monitor)[0]) or 1.0
    except Exception:  # noqa: BLE001 - no display, or an old glfw
        return None
    if width <= 0 or height <= 0:
        return None
    return (width / scale, height / scale)


def fit_to_screen(size, workarea) -> tuple:
    """*size* (logical), shrunk to fit *workarea* (logical) with its frame.

    A window asked for in logical pixels opens at that many logical pixels --
    ``ratio`` times as many device pixels -- and only a screen too small for
    it makes it smaller. Without the clamp the window manager does it, and
    each does it differently.
    """
    width, height = int(size[0]), int(size[1])
    if not workarea:
        return (width, height)
    room_w = int(workarea[0]) - WINDOW_FRAME[0]
    room_h = int(workarea[1]) - WINDOW_FRAME[1]
    return (max(1, min(width, room_w)), max(1, min(height, room_h)))


def event_types(canvas) -> frozenset:
    """The event names a canvas backend can emit.

    Asked rather than assumed: whether a backend has a layout-aware ``char``
    event decides where typed text comes from, and getting it wrong types US
    characters on every other keyboard layout.
    """
    for attr in ("_events", "events"):
        events = getattr(canvas, attr, None)
        known = getattr(events, "_known_event_types", None) or getattr(
            type(events), "_known_event_types", None
        )
        if known:
            return frozenset(str(name) for name in known)
    module = str(type(canvas).__module__ or "").rsplit(".", 1)[-1]
    return frozenset({"char"}) if module in CHAR_BACKENDS else frozenset()


def wheel_steps(event: dict) -> int:
    """Notches, positive away from the user, from a ``rendercanvas`` wheel event.

    Rounded *away from zero*: a trackpad sends many small deltas rather than
    whole notches, and truncating those makes the gesture do nothing at all.
    Returns ``0`` for an event with no delta.
    """
    raw = float(event.get("dy") or 0.0) or float(event.get("dx") or 0.0)
    if not raw:
        return 0
    steps = int(-raw / WHEEL_NOTCH)
    if steps == 0:
        steps = -1 if raw > 0 else 1
    return steps


def _default_loop():
    """rendercanvas' asyncio loop -- the one a glfw window is pumped by."""
    try:
        from rendercanvas.asyncio import loop  # noqa: PLC0415

        return loop
    except Exception:  # noqa: BLE001 - no canvas loop here
        return None


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
class CanvasEvents:
    """Translate a ``rendercanvas`` canvas' events onto a surface.

    Parameters
    ----------
    canvas : object
        A ``rendercanvas`` canvas (anything with ``add_event_handler``).
    sink : object
        Has the :class:`emtk.app.Surface` handlers: ``on_pointer_press``,
        ``on_pointer_move``, ``on_pointer_release``, ``on_wheel``,
        ``on_key_press``, and optionally ``on_files_dropped`` and
        ``on_resize(width, height, ratio)``.
    on_frame : callable, optional
        Called with no arguments whenever a handler answers that a frame is
        due -- :class:`NativeHost` requests a draw there. An application
        with a redraw rule of its own passes nothing.
    loop : object, optional
        Something with ``call_later(delay, callback, *args)``, for key repeat.
        Defaults to rendercanvas' asyncio loop.

    Notes
    -----
    Two things are generated here because rendercanvas does not deliver them:

    * **key repeat** -- its glfw backend drops ``glfw.REPEAT`` outright, so a
      held backspace deleted one character;
    * **file drops** -- rendercanvas has no drop event, so glfw's own
      ``set_drop_callback`` is reached for where the canvas has a glfw window.
    """

    #: Seconds before a held key repeats, and between repeats.
    KEY_REPEAT_DELAY = 0.40
    KEY_REPEAT_INTERVAL = 0.035

    def __init__(self, canvas, sink, on_frame: Callable[[], None] | None = None,
                 loop=None, input_method=None) -> None:
        self.canvas = canvas
        self.sink = sink
        self.on_frame = on_frame
        self._loop = loop
        #: Answers ``composing()``: whether the OS input method holds a
        #: composition, during which keys are its and not the app's
        #: (:mod:`emtk.ime`). Found from the canvas when not given.
        self.input_method = input_method
        #: Physical keys whose press went to the input method; their release does too.
        self._composing_keys: set[str] = set()
        self.typed_via_char = False
        self.drop_callback = None
        self._repeat_key = None
        self._repeat_generation = 0
        #: ``(time, x, y, button)`` of the last press that could start a double click.
        self._last_down = None
        self._closed = False
        self._pressed_keys = {}
        self.focus_callback = None
        self._previous_focus_callback = None
        self.position_supported = False
        self.position_callback = None
        self._previous_position_callback = None
        #: glfw callbacks chained by :meth:`_connect_pointer_presence`, as
        #: ``{setter name: (ours, the backend's)}``.
        self._presence_callbacks: dict = {}
        #: Raw wheel deltas -> whole notches in proportion (a trackpad sends many small ones).
        from .events import WheelAccumulator  # noqa: PLC0415

        self._wheel = WheelAccumulator(WHEEL_NOTCH)
        self.connect()

    # -- wiring ---------------------------------------------------------- #
    def connect(self) -> None:
        """Register a handler for every event the surface acts on."""
        _start_input_trace()
        add = getattr(self.canvas, "add_event_handler", None)
        if add is None:  # pragma: no cover - a canvas with no event system
            return
        add(self._on_pointer_down, "pointer_down")
        add(self._on_double_click, "double_click")
        add(self._on_pointer_move, "pointer_move")
        add(self._on_pointer_leave, "pointer_leave")
        add(self._on_pointer_up, "pointer_up")
        add(self._on_wheel, "wheel")
        add(self._on_key_down, "key_down")
        # Decided once, from the backend -- deciding on the first char event
        # would mis-handle exactly one character, irreproducibly.
        self.typed_via_char = "char" in event_types(self.canvas)
        if self.typed_via_char:
            add(self._on_char, "char")
        if self.input_method is None:
            from .ime import input_method_probe  # noqa: PLC0415

            self.input_method = input_method_probe(self.canvas)
        add(self._on_key_up, "key_up")
        add(self._on_resize, "resize")
        add(self._on_close, "close")
        self._connect_file_drop()
        self._connect_focus_loss()
        self._connect_close_request()
        self._connect_window_position()
        self._connect_pointer_presence()

    def _on_close(self, event) -> None:
        if self._closed:
            return
        self._closed = True
        self.release_keys()
        self._restore_focus_callback()
        self._restore_position_callback()
        self._restore_close_request_callback()
        self._restore_pointer_presence()
        close = getattr(self.sink, "close", None)
        if callable(close):
            close()

    def close_request(self) -> bool:
        """The window's close button was pressed: whether it may close now.

        Asks the sink's ``on_close_request`` (:meth:`emtk.app.Surface.on_close_request`);
        a sink without one, or one that raises, lets the window close. ``False``
        keeps the window open -- the app is then asking the user (unsaved work)
        and closes itself with ``request_close`` once answered.
        """
        ask = getattr(self.sink, "on_close_request", None)
        if not callable(ask):
            return True
        try:
            allowed = ask() is not False
        except Exception:  # noqa: BLE001 - a broken guard must not trap the user in the window
            return True
        if not allowed and self.on_frame is not None:
            self.on_frame()
        return allowed

    def _connect_close_request(self) -> None:
        """Let the app keep a glfw window open when its close button is pressed.

        rendercanvas's glfw backend closes on the window-should-close flag and
        leaves its close callback empty ("we could prevent closing here. But we
        don't"). This chains that callback and clears the flag when
        :meth:`close_request` says no, so an app with unsaved work can ask first.
        """
        window = getattr(self.canvas, "_window", None)
        self.close_request_callback = None
        if window is None:
            return
        try:
            import glfw  # noqa: PLC0415
            setter = getattr(glfw, "set_window_close_callback", None)
            keep_open = getattr(glfw, "set_window_should_close", None)
            if not callable(setter) or not callable(keep_open):
                return
            previous = setter(window, None)

            def closing(_window) -> None:
                if previous is not None:
                    previous(_window)
                if not self.close_request():
                    keep_open(_window, False)

            self.close_request_callback = closing
            self._previous_close_request_callback = previous
            setter(window, closing)
        except Exception:  # noqa: BLE001 - the guard is optional off GLFW
            self.close_request_callback = None

    def _restore_close_request_callback(self) -> None:
        window = getattr(self.canvas, "_window", None)
        if window is None or getattr(self, "close_request_callback", None) is None:
            return
        try:
            import glfw  # noqa: PLC0415
            glfw.set_window_close_callback(window, self._previous_close_request_callback)
        except Exception:  # noqa: BLE001 - the window may already be gone
            pass
        self.close_request_callback = None

    def _connect_window_position(self) -> None:
        """Persist geometry where a GLFW backend exposes a movable window.

        rendercanvas has no public move event or position setter. Other
        backends, including offscreen, deliberately leave this unsupported.
        """
        window = getattr(self.canvas, "_window", None)
        if window is None:
            return
        control = getattr(self.sink, "control", self.sink)
        try:
            import glfw  # noqa: PLC0415

            capabilities = ("set_window_pos_callback", "set_window_pos", "get_window_pos",
                            "get_primary_monitor", "get_monitor_workarea")
            if not all(callable(getattr(glfw, name, None)) for name in capabilities):
                return
            monitor = glfw.get_primary_monitor()
            if not monitor:
                return
            left, top, width, height = glfw.get_monitor_workarea(monitor)
            screen_changed = getattr(control, "window_screen_changed", None)
            if callable(screen_changed):
                screen_changed((left, top, width, height))
            previous = glfw.set_window_pos_callback(window, None)

            def moved(native_window, x, y) -> None:
                hook = getattr(control, "window_moved", None)
                if callable(hook):
                    hook(int(x), int(y))
                if previous is not None:
                    previous(native_window, x, y)

            self._previous_position_callback = previous
            self.position_callback = moved
            glfw.set_window_pos_callback(window, moved)
            self.position_supported = True
            pos = getattr(control, "window_pos", None)
            try:
                x, y = int(pos[0]), int(pos[1])
            except (TypeError, ValueError, OverflowError, IndexError):
                x = y = None
            if (x is not None and left <= x < left + width
                    and top <= y < top + height):
                glfw.set_window_pos(window, x, y)
            moved(window, *glfw.get_window_pos(window))
        except Exception:  # noqa: BLE001 - unavailable native backend capability
            self._restore_position_callback()
            self.position_supported = False

    def _restore_position_callback(self) -> None:
        """Restore a backend callback before its native window is destroyed."""
        if self.position_callback is None:
            return
        try:
            import glfw  # noqa: PLC0415

            glfw.set_window_pos_callback(self.canvas._window, self._previous_position_callback)
        except Exception:  # noqa: BLE001 - the backend may already have closed
            pass
        self.position_callback = None

    #: glfw's setters for the callbacks whose events rendercanvas gates on
    #: its idea of whether the pointer is inside the window.
    _PRESENCE_SETTERS = ("set_mouse_button_callback", "set_cursor_pos_callback")

    def _connect_pointer_presence(self) -> None:
        """Keep rendercanvas' "pointer inside" flag true to the OS.

        rendercanvas' glfw backend drops every pointer move while it believes
        the pointer is outside the window, and swallows a press there as the
        click that focuses the window. That belief comes only from glfw's
        cursor enter/leave callbacks, and on macOS those come from a tracking
        area glfw rebuilds on every resize with ``NSTrackingAssumeInside``: a
        pointer outside the content view at that moment -- on the edge being
        dragged, or anywhere while a tiling tool resizes the window --
        produces no enter event when it then moves in. After a resize every
        click was swallowed and every hover dropped until the pointer left
        the window and came back.

        Chained ahead of the backend's button and cursor callbacks: when the
        flag says outside but glfw's live ``HOVERED`` query says the pointer
        is over the window, the missing enter is delivered first.
        """
        window = getattr(self.canvas, "_window", None)
        if window is None or not hasattr(self.canvas, "_pointer_inside"):
            return
        try:
            import glfw  # noqa: PLC0415

            if not hasattr(glfw, "HOVERED"):
                return
            for name in self._PRESENCE_SETTERS:
                setter = getattr(glfw, name, None)
                if not callable(setter):
                    continue
                previous = setter(window, None)
                if previous is None:
                    continue

                def chained(native_window, *args, _previous=previous, _name=name) -> None:
                    if _name == "set_mouse_button_callback":
                        self._button_arrived(native_window, *args)
                    self.sync_pointer_inside(native_window)
                    _previous(native_window, *args)

                # Held here: glfw keeps the callback alive only while installed.
                self._presence_callbacks[name] = (chained, previous)
                setter(window, chained)
        except Exception:  # noqa: BLE001 - not a glfw window after all
            self._presence_callbacks = {}

    def _button_arrived(self, window, button=0, action=0, *_rest) -> None:
        """A raw glfw button event, before the backend sees it: a press over the window lands.

        rendercanvas' glfw backend swallows a press it believes happens outside the window
        as "the click that focuses the window", locks the pointer, drops every move and
        unlocks on the next release. Both halves of that belief went wrong in practice,
        each losing clicks: the inside flag missed its enter event after a resize (see
        :meth:`sync_pointer_inside`), and a lock whose release never reached the window
        stayed, so the next real press was eaten as that release -- a click that did not
        land, at random. emtk decides instead: a press over the window (glfw's live
        ``HOVERED``) is a click on what is under the pointer, the first click into an
        inactive window included, as a native control takes it. The lock is cleared, and
        :meth:`sync_pointer_inside` then delivers the enter the backend missed.
        """
        canvas = self.canvas
        try:
            import glfw  # noqa: PLC0415

            pressed = action == glfw.PRESS
            hovered = bool(glfw.get_window_attrib(window, glfw.HOVERED))
            cursor = glfw.get_cursor_pos(window)
        except Exception:  # noqa: BLE001 - not a glfw window after all
            return
        locked = bool(getattr(canvas, "_pointer_lock", False))
        inside = getattr(canvas, "_pointer_inside", None)
        if input_trace.isEnabledFor(logging.DEBUG):
            input_trace.debug("glfw %s button=%s cursor=(%.1f, %.1f) hovered=%s inside=%s lock=%s",
                              "press" if pressed else "release", button, cursor[0], cursor[1],
                              hovered, inside, locked)
        if pressed and hovered and locked:
            canvas._pointer_lock = False
            input_trace.debug("cleared a stale pointer lock: this press is delivered")

    def sync_pointer_inside(self, window=None) -> bool:
        """Deliver an enter glfw missed; return whether one was delivered."""
        canvas = self.canvas
        if getattr(canvas, "_pointer_inside", None) or getattr(canvas, "_pointer_lock", False):
            return False
        window = window if window is not None else getattr(canvas, "_window", None)
        if window is None:
            return False
        try:
            import glfw  # noqa: PLC0415

            if not glfw.get_window_attrib(window, glfw.HOVERED):
                return False
        except Exception:  # noqa: BLE001 - nothing to ask: leave the backend be
            return False
        enter = getattr(canvas, "_on_cursor_enter", None)
        if callable(enter):
            enter(window, True)
        else:
            canvas._pointer_inside = True
        return True

    def _restore_pointer_presence(self) -> None:
        """Put the backend's own callbacks back before the window goes."""
        callbacks, self._presence_callbacks = self._presence_callbacks, {}
        window = getattr(self.canvas, "_window", None)
        if window is None or not callbacks:
            return
        try:
            import glfw  # noqa: PLC0415

            for name, (_ours, previous) in callbacks.items():
                getattr(glfw, name)(window, previous)
        except Exception:  # noqa: BLE001 - the window may already be gone
            pass

    def _connect_file_drop(self) -> None:
        """Deliver dropped files where the backend has a glfw window."""
        window = getattr(self.canvas, "_window", None)
        if window is None:
            return
        try:
            import glfw  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - another backend, or none
            return
        setter = getattr(glfw, "set_drop_callback", None)
        if not callable(setter):
            return

        def dropped(_window, paths) -> None:
            self.files_dropped([str(p) for p in (paths or ())])

        # Held here: glfw keeps no reference, so a local callback is collected
        # and drops silently stop after the first garbage collection.
        self.drop_callback = dropped
        try:
            setter(window, dropped)
        except Exception:  # noqa: BLE001 - claims one and has none
            self.drop_callback = None

    def _connect_focus_loss(self) -> None:
        """Release held keys when a native window loses focus.

        rendercanvas uses GLFW's focus callback only to request a redraw. Chain
        that callback so its behavior is preserved while held controls are
        released on alt-tab or a click into another window.
        """
        window = getattr(self.canvas, "_window", None)
        if window is None:
            return
        try:
            import glfw  # noqa: PLC0415
            setter = getattr(glfw, "set_window_focus_callback", None)
            if not callable(setter):
                return

            previous = setter(window, None)

            def focused(_window, has_focus) -> None:
                if not has_focus:
                    self.release_keys()
                if previous is not None:
                    previous(_window, has_focus)

            self.focus_callback = focused
            self._previous_focus_callback = previous
            setter(window, focused)
        except Exception:  # noqa: BLE001 - focus release is optional off GLFW
            self.focus_callback = None

    def _restore_focus_callback(self) -> None:
        window = getattr(self.canvas, "_window", None)
        if window is None or self.focus_callback is None:
            return
        try:
            import glfw  # noqa: PLC0415
            glfw.set_window_focus_callback(window, self._previous_focus_callback)
        except Exception:  # noqa: BLE001 - the window may already be gone
            pass
        self.focus_callback = None

    def release_keys(self) -> None:
        """Deliver releases for every key still held by the current window."""
        self.stop_key_repeat()
        pressed, self._pressed_keys = self._pressed_keys, {}
        for key, text, modifiers in pressed.values():
            self._deliver("on_key_release", key, text, modifiers)

    def files_dropped(self, paths, position=None) -> bool:
        """Files were dropped at *position* (logical px; the live cursor when not given).

        A drop lands where the pointer is, not where the keyboard is. While the
        OS drags files in, the window sees no pointer moves (macOS delivers
        none), so the app's idea of the pointer is wherever it last was. The
        drop position therefore arrives first, as a pointer move, and the
        files after it: an app routing the drop to what is under the pointer
        (a docked tool among several) gets the right one.
        """
        if position is None:
            position = self._live_cursor()
        if position is not None:
            self._deliver("on_pointer_move", float(position[0]), float(position[1]),
                          NO_BUTTON, 0)
        return self._deliver("on_files_dropped", [str(p) for p in (paths or ())])

    def _live_cursor(self):
        """Where glfw says the cursor is, in logical pixels; ``None`` off glfw."""
        window = getattr(self.canvas, "_window", None)
        if window is None:
            return None
        try:
            import glfw  # noqa: PLC0415

            gx, gy = glfw.get_cursor_pos(window)
            if not getattr(self.canvas, "_screen_size_is_logical", True):
                ratio = float(self.canvas.get_pixel_ratio()) or 1.0
                gx, gy = gx / ratio, gy / ratio
            return float(gx), float(gy)
        except Exception:  # noqa: BLE001 - not a glfw window after all
            return None

    @property
    def supports_file_drop(self) -> bool:
        """Whether this canvas delivers drops (a real glfw window does)."""
        return self.drop_callback is not None

    def _deliver(self, name: str, *args, **kwargs):
        if name != "on_pointer_move" and input_trace.isEnabledFor(logging.DEBUG):
            input_trace.debug("deliver %s %s %s", name, args, kwargs or "")
        handler = getattr(self.sink, name, None)
        if not callable(handler):
            return False
        due = handler(*args, **kwargs)
        if due and self.on_frame is not None:
            self.on_frame()
        return due

    # -- pointer --------------------------------------------------------- #
    @staticmethod
    def buttons_mask(event: dict) -> int:
        """Fold a canvas event's held-button tuple into emtk's mask."""
        mask = NO_BUTTON
        for button in event.get("buttons") or ():
            mask |= button_from_canvas(button)
        return mask

    #: A second press this soon (seconds) and this near (logical px) to the
    #: first is a double click -- rendercanvas' own thresholds.
    DOUBLE_CLICK_TIME = 0.25
    DOUBLE_CLICK_DISTANCE = 5.0

    def _on_pointer_down(self, event: dict) -> None:
        import time  # noqa: PLC0415

        x, y = self.pointer_position(event)
        button = button_from_canvas(event.get("button", 0))
        now = time.perf_counter()
        last = self._last_down
        double = (last is not None and last[3] == button
                  and now - last[0] <= self.DOUBLE_CLICK_TIME
                  and math.hypot(x - last[1], y - last[2]) <= self.DOUBLE_CLICK_DISTANCE)
        # a third press starts over, as the platform's click count does
        self._last_down = None if double else (now, x, y, button)
        kwargs = {"double": True} if double else {}
        self._deliver("on_pointer_press", x, y, button,
                      modifiers_from_canvas(event.get("modifiers")), **kwargs)

    def pointer_position(self, event: dict) -> tuple:
        """Where the pointer is for a button event, in logical pixels.

        rendercanvas' glfw backend stamps a button event with the position of
        the last *move* it saw. A window that a window manager moves or
        resizes under a still pointer (Magnet, macOS tiling) sees no move, so
        the first click after it landed where the pointer had been relative to
        the old frame -- on another control. Asked of glfw instead where the
        canvas has a glfw window.
        """
        live = self._live_cursor()
        return live if live is not None else (float(event["x"]), float(event["y"]))

    def _on_double_click(self, _event: dict) -> None:
        """Ignored: the second press already said double (:meth:`_on_pointer_down`).

        rendercanvas emits ``double_click`` after the second *release*.
        Delivered as one more press, it left the button held in the app's
        eyes with nothing to release it -- the next pointer move was a drag,
        and the next stray release anywhere completed a click on whatever
        the phantom press had landed on.
        """

    def _on_pointer_move(self, event: dict) -> None:
        self._deliver("on_pointer_move", float(event["x"]), float(event["y"]),
                      self.buttons_mask(event),
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_pointer_leave(self, event: dict) -> None:
        self._deliver("on_pointer_move", -1.0, -1.0, NO_BUTTON, 0)

    def _on_pointer_up(self, event: dict) -> None:
        self._deliver("on_pointer_release", *self.pointer_position(event),
                      button_from_canvas(event.get("button", 0)),
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_wheel(self, event: dict) -> None:
        raw = float(event.get("dy") or 0.0) or float(event.get("dx") or 0.0)
        steps = self._wheel.feed(-raw, event.get("time_stamp"))
        if steps:
            x, y = self.pointer_position({"x": event.get("x", 0.0),
                                          "y": event.get("y", 0.0)})
            self._deliver("on_wheel", x, y, steps,
                          modifiers_from_canvas(event.get("modifiers")))

    # -- keys ------------------------------------------------------------ #
    def key_text(self, event: dict) -> str:
        """The text a ``key_down`` event types, given where text comes from.

        On a backend with a ``char`` event the key event types **nothing**:
        its name is a physical key (glfw hands back a US-QWERTY position), so
        text from it is wrong on every other layout. Otherwise a single-
        character name *is* the text, with shift applied through
        :data:`SHIFT_MAP`.
        """
        name = str(event.get("key", "") or "")
        text = name if len(name) == 1 else ""
        if self.typed_via_char:
            return ""
        if text and "Shift" in (event.get("modifiers") or ()):
            text = text.upper() if text.isalpha() else SHIFT_MAP.get(text, text)
        return text

    def composing(self) -> bool:
        """Whether the OS input method is composing (a dead key, an IME preedit).

        Asked *before* a key is delivered: GLFW reports the key first and lets
        the input method see it afterwards, so a composition under way when
        the key arrives is one the key belongs to -- the Return that confirms
        a conversion, the Backspace that edits it, the letter after a dead key.
        """
        probe = self.input_method
        if probe is None:
            return False
        try:
            return bool(probe.composing())
        except Exception:  # noqa: BLE001 - a probe that fails holds nothing back
            return False

    def _on_key_down(self, event: dict) -> None:
        name = str(event.get("key", "") or "")
        if self.composing():
            # The input method's key: what it produces arrives as a char event.
            if name:
                self._composing_keys.add(name)
            self.stop_key_repeat()
            return
        self._composing_keys.discard(name)
        text = self.key_text(event)
        key = key_from_dom(name)
        modifiers = modifiers_from_canvas(event.get("modifiers"))
        # A shortcut names its letter: glfw's key name is the only place it is
        # (the char event types nothing while Command or Ctrl is held).
        chord = bool(modifiers & (CONTROL_MODIFIER | META_MODIFIER))
        if chord and not key and letter_of(0, name):
            key = ord(letter_of(0, name))
        if name:
            self._pressed_keys.setdefault(name, (key, text, modifiers))
        self._deliver("on_key_press", key, text, modifiers)
        # Only keys that *do* something repeated: a held Escape must not fire
        # a hundred times, and nor may Cmd+V -- macOS sends no key-up for a
        # key released while Command is held, so its repeat would never stop.
        if (key not in (KEY_ESCAPE, KEY_ENTER, KEY_RETURN) and (text or key)
                and not (chord and letter_of(key, ""))):
            self._start_key_repeat(key, text, modifiers)

    def _on_char(self, event: dict) -> None:
        """Text the operating system produced, whatever the layout.

        Repeats are the OS's here (glfw calls this again while a key is held),
        so none is synthesised -- that would double every repeated character.
        """
        from .ime import committed_text  # noqa: PLC0415

        # Not ``isprintable``: that drops the zero-width joiner of an emoji
        # sequence and the non-joiner of Persian (see emtk.ime.committed_text).
        text = committed_text(event.get("data") or event.get("char_str") or "")
        if not text:
            return
        self._deliver("on_key_press", 0, text,
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_key_up(self, event: dict) -> None:
        name = str(event.get("key", "") or "")
        if name in self._composing_keys:
            self._composing_keys.discard(name)
            return
        key, text, _original_modifiers = self._pressed_keys.pop(
            name,
            (key_from_dom(name), "", modifiers_from_canvas(event.get("modifiers"))),
        )
        modifiers = modifiers_from_canvas(event.get("modifiers"))
        self._deliver("on_key_release", key, text, modifiers)
        if self._repeat_key is not None and self._repeat_key[0] == key:
            self.stop_key_repeat()

    def stop_key_repeat(self) -> None:
        """Cancel any pending repeat."""
        self._repeat_key = None
        self._repeat_generation += 1

    def _start_key_repeat(self, key: int, text: str, modifiers: int) -> None:
        loop = self._loop if self._loop is not None else _default_loop()
        if loop is None:
            return
        self._repeat_generation += 1
        self._repeat_key = (key, text, modifiers)
        try:
            loop.call_later(self.KEY_REPEAT_DELAY, self._repeat_tick,
                            self._repeat_generation)
        except Exception:  # noqa: BLE001 - a repeat is not worth the frame
            self._repeat_key = None

    def _repeat_tick(self, generation: int) -> None:
        # A stop or a new key bumps the generation; the loop cannot cancel a
        # queued callback, so a stale one is ignored here.
        if generation != self._repeat_generation or self._repeat_key is None:
            return
        self._deliver("on_key_press", *self._repeat_key)
        loop = self._loop if self._loop is not None else _default_loop()
        if loop is not None:
            loop.call_later(self.KEY_REPEAT_INTERVAL, self._repeat_tick, generation)

    # -- size ------------------------------------------------------------ #
    def _on_resize(self, _event: dict) -> None:
        try:
            width, height = self.canvas.get_physical_size()
            ratio = float(self.canvas.get_pixel_ratio())
        except Exception:  # noqa: BLE001 - a canvas that cannot say
            return
        self._deliver("on_resize", int(width), int(height), ratio)


# --------------------------------------------------------------------------- #
# The host
# --------------------------------------------------------------------------- #
class NativeHost:
    """A window, a GPU device and a surface, assembled.

    Parameters
    ----------
    app : object
        A control or an :class:`emtk.app.Surface` (lifted by
        :func:`emtk.app.as_surface`).
    size : tuple of int, optional
        Logical window size.
    title : str, optional
    backend : str, optional
        A rendercanvas backend name; see :func:`canvas_module`.
    canvas : object, optional
        An already-built canvas (a test's offscreen one). No window is opened.
    device : object, optional
        A ``GPUDevice``; :func:`emtk.wgpu_host.default_device` otherwise.
    loop : object, optional
        Something with ``call_later(delay, callback, *args)`` for the
        wake-ups an idle app asks for (:func:`emtk.app.next_frame_in`); the
        canvas' own loop by default.
    decorated, floating, transparent, centred : bool, optional
        The window's kind (:func:`open_canvas`); a splash screen is
        undecorated, floating, transparent and centred. *transparent* also
        configures the surface premultiplied when the platform offers it, so
        a surface cleared to alpha 0 (``ControlSurface(background=(0, 0, 0, 0))``)
        shows the desktop through.
    """

    def __init__(self, app, size=None, title: str = "emtk",
                 backend: str | None = None, canvas=None, device=None,
                 loop=None, decorated: bool = True, floating: bool = False,
                 transparent: bool = False, centred: bool = False) -> None:
        from .app import as_surface  # noqa: PLC0415

        self.app = app
        import threading

        self._host_thread = threading.get_ident()
        self._pending_external_redraw = threading.Event()
        self.surface = as_surface(app)
        if canvas is None:
            if size is None:
                size = getattr(app, "window_size", None)
                if callable(size):
                    size = size()
                try:
                    if isinstance(size, (str, bytes, dict)):
                        raise TypeError("window_size must be a width/height pair")
                    width, height = int(size[0]), int(size[1])
                    size = (width, height) if width > 0 and height > 0 else DEFAULT_WINDOW_SIZE
                except (TypeError, ValueError, OverflowError, IndexError):
                    size = DEFAULT_WINDOW_SIZE
            module = canvas_module(backend)
            self._loop = getattr(module, "loop", None)
            self.backend = module.__name__.rsplit(".", 1)[-1]
            # Only a window of another kind passes its kind: an ordinary one opens as it always has.
            kind = {key: value for key, value in (("decorated", decorated), ("floating", floating),
                                                  ("transparent", transparent),
                                                  ("centred", centred))
                    if value != (key == "decorated")}
            canvas = open_canvas(module, size=size, title=title, **kind)
        else:
            self._loop = None
            self.backend = type(canvas).__module__.rsplit(".", 1)[-1]
        self.canvas = canvas
        self._wake_loop = loop
        if self.backend == "glfw":    # copy *and* paste through glfw
            from . import clipboard  # noqa: PLC0415

            clipboard.use_glfw(getattr(canvas, "_window", None))
        #: Bumped by every frame: a wake-up queued before it is stale (the
        #: loop cannot cancel one), so only the latest can draw.
        self._wake_generation = 0
        #: How many wake-ups were scheduled -- what a test counts.
        self.wakeups = 0
        if device is None:
            from .wgpu_host import default_device  # noqa: PLC0415

            device = default_device()
        self.device = device
        self.context = canvas.get_context("wgpu")
        # Never the ``-srgb`` variant a window usually prefers: emtk's colours
        # are sRGB bytes already, and an sRGB target encodes them a second
        # time -- every panel washes out. The page refuses one outright
        # (:func:`emtk.gpu.browser.configure_canvas`); this takes the linear
        # twin of whatever the surface prefers.
        preferred = str(self.context.get_preferred_format(device.adapter))
        self.format = preferred[:-len("-srgb")] if preferred.endswith("-srgb") else preferred
        #: ``"premultiplied"`` for a transparent window whose surface can show
        #: the desktop through (the app clears to alpha 0), else ``"opaque"``.
        self.alpha_mode = configure_surface(self.context, device, self.format, transparent)
        width, height = canvas.get_physical_size()
        self.surface.attach(device, self.format, int(width), int(height),
                            float(canvas.get_pixel_ratio()))
        self.events = CanvasEvents(canvas, self.surface, on_frame=self.request_draw,
                                   loop=self._loop)
        self.surface.set_frame_request_callback(self.request_draw_threadsafe)
        canvas.request_draw(self._draw_frame)

    def _draw_frame(self) -> None:
        width, height = self.canvas.get_physical_size()
        if width <= 0 or height <= 0:
            return
        try:
            texture = self.context.get_current_texture()
        except Exception as error:
            if type(error).__name__ == "DrawCancelled":
                # macOS reports a window that has just opened (or sits under a floating
                # one) as occluded: rendercanvas cancels the frame and, drawing on
                # demand, never asks again -- the window stays blank until an input
                # event. Ask again; the scheduler waits a moment after a cancel.
                self.canvas.request_draw()
            raise
        view = texture.create_view()
        try:
            self.surface.render(view)
        except Exception as error:  # noqa: BLE001 - reported and drawn, never left blank
            # A ControlSurface already turns a failing control into an error panel; this is
            # a Surface of the app's own (or the renderer) failing. Without a pass of our own
            # the window presents a texture nothing was drawn into: solid magenta on Metal.
            from .frame_errors import report_frame_error  # noqa: PLC0415

            self._render_error_panel(view, report_frame_error(error))
        self._retitle()
        if getattr(self.app, "close_requested", False):
            if self._loop is not None and not getattr(self, "_close_scheduled", False):
                self._close_scheduled = True
                self._loop.call_soon(self.close)
            return
        self._wake_generation += 1
        if self.surface.animating():
            self.canvas.request_draw()
            return
        from .app import next_frame_in  # noqa: PLC0415

        delay = next_frame_in(self.surface)
        if delay is not None:
            self._schedule_wake(delay)

    def _render_error_panel(self, view, record) -> None:
        """Draw *record* (:class:`~emtk.frame_errors.FrameError`) into *view* with a renderer of our own."""
        from .frame_errors import draw_error_panel, logger as frame_logger  # noqa: PLC0415

        try:
            renderer = getattr(self, "_error_renderer", None)
            if renderer is None:
                from .wgpu_host import WgpuRenderer  # noqa: PLC0415

                renderer = self._error_renderer = WgpuRenderer(device=self.device,
                                                               format=self.format)
            width, height = self.canvas.get_physical_size()
            ratio = float(self.canvas.get_pixel_ratio() or 1.0)
            painter = renderer.painter(scale=ratio)
            draw_error_panel(painter, 0.0, 0.0, width / ratio, height / ratio, record)
            renderer.render(painter, width, height, view, background=(40, 18, 22, 255),
                            format=self.format)
        except Exception:  # noqa: BLE001 - the error itself is already in the log
            frame_logger.exception("could not draw the frame error panel")

    def _schedule_wake(self, delay: float) -> None:
        """One draw after *delay* seconds, unless a frame comes first."""
        loop = self._wake_loop or self._loop or _default_loop()
        if loop is None:
            return
        try:
            loop.call_later(float(delay), self._wake, self._wake_generation)
        except Exception:  # noqa: BLE001 - a missed wake is a late tooltip
            return
        self.wakeups += 1

    def _wake(self, generation: int) -> None:
        if generation == self._wake_generation:
            self.canvas.request_draw()

    def _retitle(self) -> None:
        """Carry the app's :func:`~emtk.app.window_title` onto the window."""
        from .app import window_title  # noqa: PLC0415

        title = window_title(self.app)
        if title is not None and title != getattr(self, "_title", None):
            self._title = title
            set_title = getattr(self.canvas, "set_title", None)
            if callable(set_title):
                set_title(title)

    def request_draw(self) -> None:
        """Ask for a frame; the canvas coalesces requests."""
        self.canvas.request_draw()

    def request_draw_threadsafe(self) -> None:
        """Marshal background notifications onto rendercanvas' event loop."""
        import threading

        if self.events._closed:
            return
        if threading.get_ident() == self._host_thread:
            self.request_draw()
            return
        schedule = getattr(self._loop, "call_soon_threadsafe", None)
        if callable(schedule):
            try:
                schedule(self.request_draw)
                return
            except (AttributeError, RuntimeError):
                # Before run() there is no asyncio loop yet. Its initial frame
                # will process queued work; never call a GUI backend off-thread.
                pass
        self._pending_external_redraw.set()

    def draw_frame(self):
        """Render one frame now. The offscreen canvas returns the image."""
        draw = getattr(self.canvas, "draw", None)
        if callable(draw):
            result = draw()
        else:
            result = self.canvas.force_draw()
        if getattr(self.app, "close_requested", False) and self._loop is None:
            self.close()
        return result

    def is_interactive(self) -> bool:
        """``False`` for the offscreen canvas, which shows nothing."""
        return self._loop is not None and self.backend != "offscreen"

    def run(self) -> None:
        """Pump the canvas' loop until the window closes."""
        if self._pending_external_redraw.is_set():
            self._pending_external_redraw.clear()
            self.request_draw()
        if self._loop is not None:
            self._loop.run()

    def close(self) -> None:
        try:
            self.events._on_close({"event_type": "close"})
        finally:
            self.canvas.close()


def configure_surface(context, device, format: str, transparent: bool = False) -> str:
    """Configure *context* for *device*; returns the alpha mode it got.

    A *transparent* window needs a surface that is not opaque. emtk's renderer
    writes premultiplied colour (``ONE, ONE_MINUS_SRC_ALPHA``), so
    ``"premultiplied"`` is asked for first. Metal offers only ``"opaque"`` and
    ``"unpremultiplied"``; the latter is what makes its layer non-opaque, and
    Core Animation composites a layer's pixels as premultiplied whatever the
    mode says, so it is the right mode there. Where neither is offered the
    window draws opaque: it shows its clear colour where it would have been
    see-through, which is a look, not a failure.
    """
    if transparent:
        for mode in ("premultiplied", "unpremultiplied"):
            try:
                context.configure(device=device, format=format, alpha_mode=mode)
                return mode
            except Exception:  # noqa: BLE001 - not offered here
                continue
        logger.info("this surface cannot be transparent; drawing it opaque")
    context.configure(device=device, format=format)
    return "opaque"


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m emtk.native --app pkg.module:make_app``."""
    import argparse  # noqa: PLC0415
    import sys  # noqa: PLC0415

    from .app import load_app  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        prog="python -m emtk.native",
        description="Open an emtk app in a desktop window (rendercanvas + wgpu, no Qt).",
    )
    parser.add_argument("--app", required=True,
                        help="factory spec 'package.module:make_app'")
    parser.add_argument("--title", default=None)
    parser.add_argument("--size", help="WIDTHxHEIGHT; otherwise use the app's saved/default size")
    parser.add_argument("--backend", default=None,
                        help="rendercanvas backend (glfw, offscreen, ...)")
    parser.add_argument("--screenshot", default=None,
                        help="render one frame offscreen to this PNG and exit")
    args = parser.parse_args(argv)
    app = load_app(args.app)
    if args.size:
        width, _, height = str(args.size).partition("x")
        size = (int(width), int(height or width))
    else:
        size = None  # NativeHost resolves the canonical saved/default size, including callables.
    backend = "offscreen" if args.screenshot else args.backend
    host = NativeHost(app, size=size,
                      title=args.title or args.app, backend=backend)
    if args.screenshot or not host.is_interactive():
        image = host.draw_frame()
        if args.screenshot and image is not None:
            from .testing import save_png  # noqa: PLC0415

            import numpy as np  # noqa: PLC0415

            pixels = np.ascontiguousarray(image)
            save_png(args.screenshot, pixels.shape[1], pixels.shape[0],
                     pixels.reshape(-1).tobytes())
            print(args.screenshot)
        elif not (backend or os.environ.get("EMTK_CANVAS", "").strip()):
            # Asked for offscreen (a headless run) is not a missing backend.
            print("no interactive rendercanvas backend (pip install glfw); "
                  "rendered one frame offscreen", file=sys.stderr)
        host.close()
        return 0
    host.run()
    host.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - a window
    raise SystemExit(main())
