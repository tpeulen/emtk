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
import logging
import os
from collections.abc import Callable, Sequence

from .events import NO_BUTTON, button_from_canvas, modifiers_from_canvas
from .keys import KEY_ENTER, KEY_ESCAPE, KEY_RETURN, key_from_dom

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
    "event_types",
    "open_canvas",
    "wheel_steps",
    "main",
]

logger = logging.getLogger(__name__)

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


def open_canvas(module, size=DEFAULT_WINDOW_SIZE, title: str = "emtk",
                max_fps: float = DEFAULT_MAX_FPS, present_method: str = "auto"):
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

    Returns
    -------
    rendercanvas.BaseRenderCanvas
    """
    options = {} if present_method in (None, "", "auto") else {"present_method": present_method}
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
                 loop=None) -> None:
        self.canvas = canvas
        self.sink = sink
        self.on_frame = on_frame
        self._loop = loop
        self.typed_via_char = False
        self.drop_callback = None
        self._repeat_key = None
        self._repeat_generation = 0
        self.connect()

    # -- wiring ---------------------------------------------------------- #
    def connect(self) -> None:
        """Register a handler for every event the surface acts on."""
        add = getattr(self.canvas, "add_event_handler", None)
        if add is None:  # pragma: no cover - a canvas with no event system
            return
        add(self._on_pointer_down, "pointer_down")
        add(self._on_double_click, "double_click")
        add(self._on_pointer_move, "pointer_move")
        add(self._on_pointer_up, "pointer_up")
        add(self._on_wheel, "wheel")
        add(self._on_key_down, "key_down")
        # Decided once, from the backend -- deciding on the first char event
        # would mis-handle exactly one character, irreproducibly.
        self.typed_via_char = "char" in event_types(self.canvas)
        if self.typed_via_char:
            add(self._on_char, "char")
        add(self._on_key_up, "key_up")
        add(self._on_resize, "resize")
        self._connect_file_drop()

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
            self._deliver("on_files_dropped", [str(p) for p in (paths or ())])

        # Held here: glfw keeps no reference, so a local callback is collected
        # and drops silently stop after the first garbage collection.
        self.drop_callback = dropped
        try:
            setter(window, dropped)
        except Exception:  # noqa: BLE001 - claims one and has none
            self.drop_callback = None

    @property
    def supports_file_drop(self) -> bool:
        """Whether this canvas delivers drops (a real glfw window does)."""
        return self.drop_callback is not None

    def _deliver(self, name: str, *args, **kwargs):
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

    def _on_pointer_down(self, event: dict) -> None:
        self._deliver("on_pointer_press", float(event["x"]), float(event["y"]),
                      button_from_canvas(event.get("button", 0)),
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_double_click(self, event: dict) -> None:
        # Delivered *in addition to* the ordinary press, so it only says double.
        self._deliver("on_pointer_press", float(event["x"]), float(event["y"]),
                      button_from_canvas(event.get("button", 0)),
                      modifiers_from_canvas(event.get("modifiers")), double=True)

    def _on_pointer_move(self, event: dict) -> None:
        self._deliver("on_pointer_move", float(event["x"]), float(event["y"]),
                      self.buttons_mask(event),
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_pointer_up(self, event: dict) -> None:
        self._deliver("on_pointer_release", float(event["x"]), float(event["y"]),
                      button_from_canvas(event.get("button", 0)),
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_wheel(self, event: dict) -> None:
        steps = wheel_steps(event)
        if steps:
            self._deliver("on_wheel", float(event.get("x", 0.0)),
                          float(event.get("y", 0.0)), steps,
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

    def _on_key_down(self, event: dict) -> None:
        name = str(event.get("key", "") or "")
        text = self.key_text(event)
        key = key_from_dom(name)
        modifiers = modifiers_from_canvas(event.get("modifiers"))
        self._deliver("on_key_press", key, text, modifiers)
        # Only keys that *do* something repeated: a held Escape must not fire
        # a hundred times.
        if key not in (KEY_ESCAPE, KEY_ENTER, KEY_RETURN) and (text or key):
            self._start_key_repeat(key, text, modifiers)

    def _on_char(self, event: dict) -> None:
        """Text the operating system produced, whatever the layout.

        Repeats are the OS's here (glfw calls this again while a key is held),
        so none is synthesised -- that would double every repeated character.
        """
        text = str(event.get("data") or event.get("char_str") or "")
        if not text or not text.isprintable():
            return
        self._deliver("on_key_press", 0, text,
                      modifiers_from_canvas(event.get("modifiers")))

    def _on_key_up(self, _event: dict) -> None:
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
    """

    def __init__(self, app, size=DEFAULT_WINDOW_SIZE, title: str = "emtk",
                 backend: str | None = None, canvas=None, device=None) -> None:
        from .app import as_surface  # noqa: PLC0415

        self.app = app
        self.surface = as_surface(app)
        if canvas is None:
            module = canvas_module(backend)
            self._loop = getattr(module, "loop", None)
            self.backend = module.__name__.rsplit(".", 1)[-1]
            canvas = open_canvas(module, size=size, title=title)
        else:
            self._loop = None
            self.backend = type(canvas).__module__.rsplit(".", 1)[-1]
        self.canvas = canvas
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
        self.context.configure(device=device, format=self.format)
        width, height = canvas.get_physical_size()
        self.surface.attach(device, self.format, int(width), int(height),
                            float(canvas.get_pixel_ratio()))
        self.events = CanvasEvents(canvas, self.surface, on_frame=self.request_draw,
                                   loop=self._loop)
        canvas.request_draw(self._draw_frame)

    def _draw_frame(self) -> None:
        width, height = self.canvas.get_physical_size()
        if width <= 0 or height <= 0:
            return
        self.surface.render(self.context.get_current_texture().create_view())
        if self.surface.animating():
            self.canvas.request_draw()

    def request_draw(self) -> None:
        """Ask for a frame; the canvas coalesces requests."""
        self.canvas.request_draw()

    def draw_frame(self):
        """Render one frame now. The offscreen canvas returns the image."""
        draw = getattr(self.canvas, "draw", None)
        if callable(draw):
            return draw()
        return self.canvas.force_draw()

    def is_interactive(self) -> bool:
        """``False`` for the offscreen canvas, which shows nothing."""
        return self._loop is not None and self.backend != "offscreen"

    def run(self) -> None:
        """Pump the canvas' loop until the window closes."""
        if self._loop is not None:
            self._loop.run()

    def close(self) -> None:
        try:
            self.canvas.close()
        except Exception:  # noqa: BLE001
            pass


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
    parser.add_argument("--size", default="1280x860", help="WIDTHxHEIGHT")
    parser.add_argument("--backend", default=None,
                        help="rendercanvas backend (glfw, offscreen, ...)")
    parser.add_argument("--screenshot", default=None,
                        help="render one frame offscreen to this PNG and exit")
    args = parser.parse_args(argv)
    width, _, height = str(args.size).partition("x")
    size = (int(width), int(height or width))
    backend = "offscreen" if args.screenshot else args.backend
    host = NativeHost(load_app(args.app), size=size,
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
        elif not args.screenshot:
            print("no interactive rendercanvas backend (pip install glfw); "
                  "rendered one frame offscreen", file=sys.stderr)
        return 0
    host.run()
    return 0


if __name__ == "__main__":  # pragma: no cover - a window
    raise SystemExit(main())
