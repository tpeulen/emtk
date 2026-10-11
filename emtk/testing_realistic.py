"""Drive an app the way a person and a platform deliver input -- not the way a test would.

:class:`emtk.testing.Driver` delivers a click as three surface calls in three frames at one
fixed size, at scale 1, measured by the screenshot painter. Bugs that only a real session
shows pass straight through it:

* a click after a window resize (the platform stamps a press with a pointer position from
  *before* the resize, or the surface still answers for the old size);
* a press and release that land in *different* frames, with the hand moving in between --
  a widget that decides on the press frame alone, or loses the active item on a one-pixel
  move, never shows up when press and release are back to back at one point;
* content scale 2 (a Retina display): logical vs physical pixels, framebuffer vs window
  coordinates, a painter rebuilt at the wrong ratio;
* key repeat, wheel notches arriving one per frame, a window losing focus with a key held;
* the text metrics of the painter that actually draws (the GPU :class:`~.quad_painter.QuadPainter`),
  not the screenshot painter's.

Two drivers, both :class:`~emtk.testing.Driver` subclasses so every helper written for the
synthetic one (``click(name)``, ``rect(caption)``, ``screenshot``) keeps working:

:class:`RealisticDriver`
    No window, no GPU. Events are dicts in the ``rendercanvas`` vocabulary, queued and merged
    by rendercanvas' own ``EventEmitter`` (consecutive pointer moves and wheel deltas merge
    between frames, exactly as on a desktop) and translated by :class:`emtk.native.CanvasEvents`
    -- the code a real window runs. Frames are drawn into a recording wrapper around the real
    ``QuadPainter`` at the device scale. Time is virtual: a frame advances it by
    ``frame_interval`` and fires due key-repeat callbacks, and the double-click clock reads it.

:class:`HostedDriver`
    A real :class:`emtk.native.NativeHost` (wgpu device, real surface) on either an offscreen
    ``rendercanvas`` canvas with a chosen pixel ratio, or a **hidden glfw window** -- the
    platform input path itself: glfw's content scale, ``framebuffer_size`` vs ``window_size``,
    resize callbacks and rendercanvas' glfw event code. Input enters where glfw would call
    rendercanvas (its cursor/button/scroll/key callbacks); only the OS cursor is simulated
    (``glfw.get_cursor_pos`` answers where the simulated hand is, never warping the real
    pointer).

Gestures
--------
``click(target)`` moves the pointer to the target along ``move_steps`` frames, presses,
holds for ``hold_frames`` frames while the hand drifts ``jitter`` pixels, and releases in a
later frame. ``drag``, ``double_click``, ``wheel`` (one notch per frame), ``hold_key``
(platform key repeat on the virtual clock), ``type`` (key down, ``char``, key up per
character), ``blur``/``focus``, ``resize`` (the window manager resizes under a still pointer)
and ``set_scale`` (dragged to a display of another density).
"""
from __future__ import annotations

import heapq
import math
from contextlib import contextmanager
from unittest import mock

from .events import (ALT_MODIFIER, CONTROL_MODIFIER, LEFT_BUTTON, META_MODIFIER,
                     MIDDLE_BUTTON, RIGHT_BUTTON, SHIFT_MODIFIER)
from .testing import Driver, RecordingPainter

__all__ = ["VirtualLoop", "HostPainter", "SyntheticCanvas", "RealisticDriver",
           "HostedDriver", "clipped_texts"]

#: emtk button -> rendercanvas button number.
_CANVAS_BUTTON = {LEFT_BUTTON: 1, RIGHT_BUTTON: 2, MIDDLE_BUTTON: 3}


def _canvas_modifiers(modifiers: int) -> tuple:
    """emtk's modifier mask -> rendercanvas' names, undoing the Mac Cmd/Ctrl swap."""
    from .keys import mac_behaviors  # noqa: PLC0415

    mac = mac_behaviors()
    names = []
    if modifiers & SHIFT_MODIFIER:
        names.append("Shift")
    if modifiers & ALT_MODIFIER:
        names.append("Alt")
    if modifiers & CONTROL_MODIFIER:
        names.append("Meta" if mac else "Control")
    if modifiers & META_MODIFIER:
        names.append("Control" if mac else "Meta")
    return tuple(sorted(names))


def _dom_name(key: int, text: str = "") -> str:
    """The ``KeyboardEvent.key`` a platform reports for an emtk key code."""
    from .keys import _DOM_KEYS  # noqa: PLC0415

    for name, code in _DOM_KEYS.items():  # the primary spelling comes first
        if code == key and key:
            return name
    if text:
        return text
    return chr(key) if 0 < key < 0x110000 else ""


# --------------------------------------------------------------------------- #
# Time
# --------------------------------------------------------------------------- #
class VirtualLoop:
    """A clock and ``call_later`` that only move when the driver draws a frame.

    Stands in for rendercanvas' asyncio loop, which is what key repeat is scheduled on.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)
        self._queue: list = []
        self._seq = 0

    def call_later(self, delay, callback, *args) -> None:
        self._seq += 1
        heapq.heappush(self._queue, (self.now + float(delay), self._seq, callback, args))

    def call_soon(self, callback, *args) -> None:
        self.call_later(0.0, callback, *args)

    def advance(self, seconds: float) -> int:
        """Move the clock, firing every callback that falls due; return how many fired."""
        end = self.now + max(float(seconds), 0.0)
        fired = 0
        while self._queue and self._queue[0][0] <= end:
            when, _seq, callback, args = heapq.heappop(self._queue)
            self.now = max(self.now, when)
            callback(*args)
            fired += 1
        self.now = end
        return fired

    def perf_counter(self) -> float:
        return self.now


# --------------------------------------------------------------------------- #
# The painter that draws
# --------------------------------------------------------------------------- #
class HostPainter(RecordingPainter):
    """Record a frame while the **real** device painter draws and measures it.

    Every operation is recorded (``texts``, ``visible_texts``, ``clips``...) for target lookup
    and layout assertions, then forwarded to *real* -- a ``QuadPainter`` at the device scale,
    as :class:`emtk.app.ControlSurface` builds it. Measurements (``text_width``,
    ``line_height``) are the real painter's, so a label that the GPU draws clipped is
    recorded clipped. Anything the recorder does not define (``image``, ``polyline``,
    ``text_rotated``...) is the real painter's, so an app takes the path it takes on screen.
    """

    def __init__(self, real) -> None:
        super().__init__()
        self._real = real

    def __getattr__(self, name):
        real = self.__dict__.get("_real")
        if real is None:
            raise AttributeError(name)
        return getattr(real, name)

    # recorded and drawn
    def fill_rect(self, x, y, w, h, colour) -> None:
        super().fill_rect(x, y, w, h, colour)
        self._real.fill_rect(x, y, w, h, colour)

    def stroke_rect(self, x, y, w, h, edge, fill=None, *, width=1.0) -> None:
        super().stroke_rect(x, y, w, h, edge, fill, width=width)
        self._real.stroke_rect(x, y, w, h, edge, fill, width=width)

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        super().gradient_rect(x, y, w, h, stops, edge)
        self._real.gradient_rect(x, y, w, h, stops, edge)

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        super().text(x, y, w, h, align, string, colour, bold)
        self._real.text(x, y, w, h, align, string, colour, bold)

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        super().fill_triangle(p0, p1, p2, colour)
        self._real.fill_triangle(p0, p1, p2, colour)

    def gradient_triangle(self, p0, p1, p2, c0, c1, c2) -> None:
        super().gradient_triangle(p0, p1, p2, c0, c1, c2)
        self._real.gradient_triangle(p0, p1, p2, c0, c1, c2)

    def image_triangle(self, p0, p1, p2, handle, uv0=(0.0, 0.0), uv1=(1.0, 0.0),
                       uv2=(1.0, 1.0), tint=(255, 255, 255, 255)) -> None:
        super().image_triangle(p0, p1, p2, handle, uv0, uv1, uv2, tint)
        self._real.image_triangle(p0, p1, p2, handle, uv0, uv1, uv2, tint)

    def push_clip(self, x, y, w, h) -> None:
        super().push_clip(x, y, w, h)
        self._real.push_clip(x, y, w, h)

    def pop_clip(self) -> None:
        super().pop_clip()
        self._real.pop_clip()

    # measured by the real painter
    def text_width(self, string) -> float:
        return self._real.text_width(string)

    def line_height(self) -> float:
        return self._real.line_height()

    def set_font(self, value=None, size=0.0) -> None:
        self._real.set_font(value, size)
        # Measure through the real painter, never the recorder's own font tables.
        self._font_spec = None

    def set_font_scale(self, scale: float) -> None:
        self._font_scale = float(scale)
        self._real.set_font_scale(scale)

    def clear(self) -> None:
        self._real.clear()


def clipped_texts(painter, *, tolerance: float = 0.5, min_chars: int = 2) -> list[dict]:
    """Labels whose glyphs the active clip cut, from a recording painter's last frame.

    A text counts as clipped when part of its measured glyph run lies outside the clip in
    force when it was drawn, and at least *min_chars* characters' worth is hidden (so a
    trailing space or a glyph's antialiased edge is not a finding). A text clipped away
    completely (scrolled out of a child, behind a fold) is not reported -- that is a
    scrolled list, not a squeezed label.

    Returns
    -------
    list of dict
        ``{"text", "measured", "visible", "hidden_px"}`` per clipped label.
    """
    out = []
    for entry, meta in zip(painter.visible_texts, painter.text_metadata):
        string = str(entry[5])
        mx, my, mw, mh = meta["measured_bounds"]
        vx, vy, vw, vh = meta["visible_bounds"]
        if not string.strip() or mw <= 0 or vw <= 0 or vh <= 0:
            continue
        hidden = (mw - vw)
        per_char = mw / max(len(string.strip()), 1)
        if hidden > tolerance and hidden >= per_char * (min_chars - 0.5) and vh >= mh * 0.5:
            out.append({"text": string, "measured": (mx, my, mw, mh),
                        "visible": (vx, vy, vw, vh), "hidden_px": round(hidden, 1)})
    return out


# --------------------------------------------------------------------------- #
# A canvas that is only an event source
# --------------------------------------------------------------------------- #
class SyntheticCanvas:
    """The event half of a ``rendercanvas`` canvas, with rendercanvas' own emitter.

    Events are *submitted* (queued; consecutive pointer moves and wheel deltas merge) and
    *flushed* once per frame, as rendercanvas' scheduler does before a draw.
    """

    def __init__(self, size, ratio: float = 1.0) -> None:
        from rendercanvas.core.events import EventEmitter  # noqa: PLC0415

        self._events = EventEmitter()
        # Ask for a ``char`` event as glfw has: typed text comes from it, not from key names.
        self._events._known_event_types = frozenset(
            {"pointer_down", "pointer_up", "pointer_move", "double_click", "wheel",
             "key_down", "key_up", "char", "resize", "close"})
        self.logical_size = tuple(float(v) for v in size)
        self.ratio = float(ratio)

    def add_event_handler(self, callback, *types, order: float = 0):
        return self._events.add_handler(callback, *types, order=order)

    def submit_event(self, event: dict) -> None:
        self._events.submit(event)

    def flush(self) -> None:
        self._events.flush()

    def get_physical_size(self):
        return (max(1, round(self.logical_size[0] * self.ratio)),
                max(1, round(self.logical_size[1] * self.ratio)))

    def get_logical_size(self):
        return self.logical_size

    def get_pixel_ratio(self):
        return self.ratio


# --------------------------------------------------------------------------- #
# The realistic driver
# --------------------------------------------------------------------------- #
class RealisticDriver(Driver):
    """Feed an app input the way a person on a desktop does (see the module docstring).

    Parameters
    ----------
    app : control or callable
        As :class:`~emtk.testing.Driver`.
    size : tuple of int
        Logical window size.
    scale : float
        Content scale (device pixels per logical pixel).
    move_steps : int
        Frames the pointer takes to travel to a target.
    hold_frames : int
        Frames a button is held between press and release.
    jitter : float
        How far (logical px) the hand drifts while the button is held. Stays inside the
        target's rectangle.
    frame_interval : float
        Seconds of virtual time per frame (60 Hz by default).
    real_painter : bool
        Draw into the real ``QuadPainter`` (``True``) or the screenshot painter's metrics.
    """

    def __init__(self, app, size=(1000, 700), *, scale: float = 1.0, move_steps: int = 4,
                 hold_frames: int = 2, jitter: float = 1.0, frame_interval: float = 1 / 60,
                 real_painter: bool = True) -> None:
        super().__init__(app, size)
        from .native import CanvasEvents  # noqa: PLC0415

        self.scale = float(scale)
        self.move_steps = max(int(move_steps), 1)
        self.hold_frames = max(int(hold_frames), 1)
        self.jitter = float(jitter)
        self.frame_interval = float(frame_interval)
        self.real_painter = bool(real_painter)
        self.loop = VirtualLoop()
        self.canvas = SyntheticCanvas(self.size, self.scale)
        self.events = CanvasEvents(self.canvas, self.surface, loop=self.loop,
                                   input_method=_NoComposition())
        self._buttons: tuple = ()
        self._modifiers: tuple = ()
        self._renderer = None
        self._quad = None
        #: Gestures whose press and release did not resolve to the same drawn rectangle.
        self.log: list[tuple] = []
        self._resize_to(self.size, self.scale)

    # -- time and frames -------------------------------------------------- #
    @contextmanager
    def _clock(self):
        """Let the platform layer read the virtual clock (double-click timing)."""
        with mock.patch("time.perf_counter", self.loop.perf_counter):
            yield

    def _submit(self, event: dict) -> None:
        event.setdefault("time_stamp", self.loop.now)
        self.canvas.submit_event(event)

    def _flush(self) -> None:
        with self._clock():
            self.canvas.flush()

    def _painter_for_frame(self):
        if not self.real_painter:
            from .testing import MetricPainter  # noqa: PLC0415

            return MetricPainter()
        # As ControlSurface.render builds it: the surface's font size (the user's setting
        # unless one was given) at the surface's device ratio, rebuilt when either changes.
        key = (self.surface.ratio, float(self.surface.font_pt))
        if self._quad is None or getattr(self, "_quad_key", None) != key:
            from .wgpu_host import WgpuRenderer  # noqa: PLC0415

            if self._renderer is None:
                self._renderer = WgpuRenderer()
            self._quad = self._renderer.painter(font_pt=key[1], scale=key[0])
            self._quad_key = key
        self._quad.clear()
        return HostPainter(self._quad)

    def _draw_frame(self, painter):
        """Draw the surface's box: logical size derived from physical size and ratio."""
        for registry in self._registries():
            registry.clear()
        self.painter = painter
        self.app.draw(painter, *self.surface._box())
        self._rects = {key: tuple(box) for registry in self._registries()
                       for key, box in registry.items() if box is not None}

    def frame(self, n=1):
        """Flush pending platform events, draw *n* frames, advance virtual time."""
        if n < 1:
            raise ValueError("frame count must be positive")
        for _ in range(n):
            self._flush()
            self._draw_frame(self._painter_for_frame())
            self.loop.advance(self.frame_interval)
        return self.painter

    # -- window ----------------------------------------------------------- #
    def _resize_to(self, size, scale) -> None:
        self.canvas.logical_size = tuple(float(v) for v in size)
        self.canvas.ratio = float(scale)
        width, height = self.canvas.get_physical_size()
        self._submit({"event_type": "resize", "width": float(size[0]),
                      "height": float(size[1]), "pixel_ratio": float(scale)})
        self._flush()
        self.size = tuple(int(v) for v in size)
        self.scale = float(scale)
        assert self.surface.size == (width, height), (self.surface.size, (width, height))

    def resize(self, size, frames: int = 2):
        """The window manager resizes the window; the pointer stays where it was on screen."""
        self._resize_to(tuple(map(int, size)), self.scale)
        return self.frame(frames)

    def draw(self, frames=2, size=None):
        if size is not None:
            return self.resize(size, frames)
        return self.frame(frames)

    def set_scale(self, scale: float, frames: int = 2):
        """The window moves to a display of another density; logical size unchanged."""
        self._resize_to(self.size, float(scale))
        return self.frame(frames)

    def move_window(self, dx: float, dy: float, frames: int = 1):
        """The window moves by (*dx*, *dy*) under a hand that stays still on screen.

        No pointer event is delivered (none is, by a platform): the hand is now at a
        different place *in the window*, which only a live cursor query can know.
        """
        self._pointer = (self._pointer[0] - float(dx), self._pointer[1] - float(dy))
        self._sync_cursor()
        return self.frame(frames)

    def _sync_cursor(self) -> None:
        """Where the OS says the cursor is; the synthetic canvas has no live query."""

    def press_here(self, button=LEFT_BUTTON):
        """Press and release where the hand is now, without moving it first."""
        self._button_event("pointer_down", button)
        self.frame()
        self._button_event("pointer_up", button)
        return self.frame()

    def blur(self):
        """The window loses focus (another app in front): held keys are released."""
        self.events.release_keys()
        return self.frame()

    def focus(self):
        """The window comes back to the front."""
        return self.frame()

    # -- pointer ---------------------------------------------------------- #
    def _move_event(self, x, y):
        self._stamp = (float(x), float(y))
        self._submit({"event_type": "pointer_move", "x": float(x), "y": float(y), "button": 0,
                      "buttons": self._buttons, "modifiers": self._modifiers,
                      "ntouches": 0, "touches": {}})

    def _travel(self, point, steps=None):
        """Move the hand to *point* over several frames (one merged move per frame)."""
        steps = self.move_steps if steps is None else max(int(steps), 1)
        x0, y0 = self._pointer
        x1, y1 = point
        for i in range(1, steps + 1):
            t = i / steps
            # ease-out: fast at first, settling on the target the way a hand does
            e = 1 - (1 - t) ** 2
            self._pointer = (x0 + (x1 - x0) * e, y0 + (y1 - y0) * e)
            self._move_event(*self._pointer)
            self.frame()
        self._pointer = (float(x1), float(y1))

    def hover(self, target):
        point = self._point(target)
        self._travel(point)
        return self.painter

    def _button_event(self, kind, button):
        number = _CANVAS_BUTTON.get(button, 1)
        held = set(self._buttons)
        if kind == "pointer_down":
            held.add(number)
        else:
            held.discard(number)
        self._buttons = tuple(sorted(held))
        # rendercanvas stamps a button event with the last *move* it saw, not the live
        # cursor: after the window moved under a still hand the two differ.
        x, y = getattr(self, "_stamp", self._pointer)
        self._submit({"event_type": kind, "x": x, "y": y,
                      "button": number, "buttons": self._buttons,
                      "modifiers": self._modifiers, "ntouches": 0, "touches": {}})

    def _target_box(self, target):
        if isinstance(target, (str, int)):
            return self.rect(target)
        if len(target) == 4:
            return tuple(float(v) for v in target)
        x, y = target
        return (float(x) - 1, float(y) - 1, 2.0, 2.0)

    def click(self, target, button=LEFT_BUTTON, modifiers: int = 0):
        """Travel, press, hold (drifting) over frames, release in a later frame."""
        box = self._target_box(target)
        point = self._point(target)
        self._travel(point)
        self._modifiers = _canvas_modifiers(modifiers)
        self._button_event("pointer_down", button)
        self.frame()
        x, y = point
        for i in range(self.hold_frames):
            if self.jitter:
                angle = 2.4 * (i + 1)
                dx, dy = math.cos(angle) * self.jitter, math.sin(angle) * self.jitter
                bx, by, bw, bh = box
                nx = min(max(x + dx, bx + 0.5), bx + max(bw - 0.5, 0.5))
                ny = min(max(y + dy, by + 0.5), by + max(bh - 0.5, 0.5))
                self._pointer = (nx, ny)
                self._move_event(nx, ny)
            self.frame()
        self._button_event("pointer_up", button)
        out = self.frame()
        self._modifiers = ()
        return out

    def double_click(self, target, button=LEFT_BUTTON):
        """Two clicks inside the platform's double-click time, with no travel between."""
        point = self._point(target)
        self._travel(point)
        for _ in range(2):
            self._button_event("pointer_down", button)
            self.frame()
            self._button_event("pointer_up", button)
            self.frame()
        return self.painter

    def drag(self, start, end, steps: int = 8, button=LEFT_BUTTON):
        """Press at *start*, move to *end* over *steps* frames, release there."""
        self._travel(self._point(start))
        self._button_event("pointer_down", button)
        self.frame()
        self._travel(self._point(end), steps)
        self._button_event("pointer_up", button)
        return self.frame()

    def wheel(self, dy, at=None, *, dx=0.0):
        """Wheel notches, one per frame, at a target (positive *dy* scrolls up)."""
        if at is not None:
            self._travel(self._point(at))
        notches = int(round(abs(float(dy)))) or (1 if dy else 0)
        sign = 1.0 if dy > 0 else -1.0
        for _ in range(notches):
            self._submit({"event_type": "wheel", "dx": -100.0 * float(dx), "dy": -100.0 * sign,
                          "x": self._pointer[0], "y": self._pointer[1],
                          "buttons": self._buttons, "modifiers": self._modifiers})
            self.frame()
        if not notches and dx:
            self._submit({"event_type": "wheel", "dx": -100.0 * float(dx), "dy": 0.0,
                          "x": self._pointer[0], "y": self._pointer[1],
                          "buttons": self._buttons, "modifiers": self._modifiers})
            self.frame()
        return self.painter

    # -- keys ------------------------------------------------------------- #
    def key(self, code, text="", modifiers=0):
        """Key down (and the ``char`` the OS types for it); the key stays held."""
        name = _dom_name(code, text)
        mods = _canvas_modifiers(modifiers)
        self._submit({"event_type": "key_down", "key": name, "modifiers": mods})
        if text and not (modifiers & (CONTROL_MODIFIER | META_MODIFIER)):
            self._submit({"event_type": "char", "data": text, "char_str": text,
                          "modifiers": mods})
        self._held = (name, mods)
        return self.frame()

    def release_key(self):
        held = getattr(self, "_held", None)
        if held is not None:
            self._submit({"event_type": "key_up", "key": held[0], "modifiers": held[1]})
            self._held = None
        return self.frame()

    def press(self, key, mods=0):
        """Press, hold for a frame, release -- as a quick tap."""
        self.key(key, modifiers=mods)
        return self.release_key()

    def type(self, text):
        for char in text:
            self.key(0, char)
            self.release_key()
        return self.painter

    def hold_key(self, key, seconds: float, text: str = "", modifiers: int = 0):
        """Hold a key for *seconds* of virtual time; the platform repeats it."""
        self.key(key, text, modifiers)
        frames = max(int(round(float(seconds) / self.frame_interval)), 1)
        self.frame(frames)
        return self.release_key()


class _NoComposition:
    """No OS input method is composing in a synthetic session."""

    def composing(self) -> bool:
        return False


# --------------------------------------------------------------------------- #
# A real host
# --------------------------------------------------------------------------- #
class HostedDriver(RealisticDriver):
    """Drive a real :class:`emtk.native.NativeHost` on an offscreen canvas or a hidden glfw window.

    Parameters
    ----------
    backend : {"offscreen", "glfw"}
        ``glfw`` opens a real window, never shown (``glfw.show_window`` is suppressed while
        it is created), so glfw's content scale, framebuffer size and resize callbacks are the
        platform's. Needs a display session; :meth:`available` says whether one is usable.
    scale : float
        Pixel ratio of the offscreen canvas. A glfw window takes the display's own.
    """

    def __init__(self, app, size=(1000, 700), *, backend: str = "offscreen",
                 scale: float = 1.0, **options) -> None:
        self.backend = backend
        self.host = None
        self._cursor = (0.0, 0.0)
        self._patches: list = []
        super().__init__(app, size, scale=scale, **options)

    # The base class builds a synthetic canvas; replace it with a real host.
    def _resize_to(self, size, scale) -> None:
        if self.host is None:
            self._open(size, scale)
            return
        canvas = self.host.canvas
        if self.backend == "glfw":
            import glfw  # noqa: PLC0415

            # What a window manager does: the window changes size; rendercanvas hears the
            # framebuffer callback, the app the resize event at the next flush.
            glfw.set_window_size(canvas._window, int(size[0]), int(size[1]))
            glfw.poll_events()
        else:
            if float(scale) != canvas.get_pixel_ratio():
                canvas.set_pixel_ratio(float(scale))
            canvas.set_logical_size(float(size[0]), float(size[1]))
        self._flush()
        self.size = tuple(int(round(v)) for v in canvas.get_logical_size())
        self.scale = float(canvas.get_pixel_ratio())

    def _open(self, size, scale) -> None:
        from .native import CanvasEvents, NativeHost  # noqa: PLC0415

        if self.backend == "glfw":
            import glfw  # noqa: PLC0415
            from rendercanvas.glfw import RenderCanvas  # noqa: PLC0415

            with mock.patch.object(glfw, "show_window", lambda *_a, **_k: None):
                canvas = RenderCanvas(size=tuple(size), title="emtk-realistic")
            # The OS cursor is the simulated hand, in window (screen) coordinates.
            real_pos = glfw.get_cursor_pos

            def cursor_pos(window):
                if window == getattr(canvas, "_window", None):
                    return self._cursor
                return real_pos(window)

            patch = mock.patch.object(glfw, "get_cursor_pos", cursor_pos)
            patch.start()
            self._patches.append(patch)
        else:
            from rendercanvas.offscreen import RenderCanvas  # noqa: PLC0415

            canvas = RenderCanvas(size=tuple(size), pixel_ratio=float(scale))
        self.host = NativeHost(self.app, canvas=canvas)
        # The host translates with the real loop; the driver's virtual one runs key repeat.
        self.events = self.host.events
        self.events._loop = self.loop
        self.events.input_method = _NoComposition()
        self.surface = self.host.surface
        self.canvas = canvas
        self.size = tuple(int(round(v)) for v in canvas.get_logical_size())
        self.scale = float(canvas.get_pixel_ratio())
        if self.backend == "glfw":
            canvas._on_cursor_enter(canvas._window, True)
        self._flush()

    @classmethod
    def available(cls, backend: str = "offscreen") -> bool:
        """Whether this machine can open the host (a GPU adapter; a display for glfw)."""
        try:
            from .wgpu_host import default_device  # noqa: PLC0415

            default_device()
            if backend == "glfw":
                import glfw  # noqa: PLC0415

                return bool(glfw.init())
            return True
        except Exception:  # noqa: BLE001 - no adapter, no display
            return False

    def _sync_cursor(self) -> None:
        self._cursor = self._screen(*self._pointer)

    # -- the platform's side of input ---------------------------------- #
    def _screen(self, x, y):
        """Logical -> glfw window coordinates (points on macOS, pixels elsewhere)."""
        canvas = self.canvas
        if getattr(canvas, "_screen_size_is_logical", True):
            return float(x), float(y)
        ratio = float(canvas.get_pixel_ratio()) or 1.0
        return float(x) * ratio, float(y) * ratio

    def _submit(self, event: dict) -> None:
        if self.backend != "glfw":
            event.setdefault("time_stamp", self.loop.now)
            self.canvas.submit_event(event)
            return
        import glfw  # noqa: PLC0415

        canvas, window = self.canvas, self.canvas._window
        kind = event["event_type"]
        if kind == "pointer_move":
            self._cursor = self._screen(event["x"], event["y"])
            canvas._on_cursor_pos(window, *self._cursor)
        elif kind in ("pointer_down", "pointer_up"):
            button = {1: glfw.MOUSE_BUTTON_LEFT, 2: glfw.MOUSE_BUTTON_RIGHT,
                      3: glfw.MOUSE_BUTTON_MIDDLE}.get(event["button"], glfw.MOUSE_BUTTON_LEFT)
            action = glfw.PRESS if kind == "pointer_down" else glfw.RELEASE
            with self._clock():
                canvas._on_mouse_button(window, button, action, 0)
        elif kind == "wheel":
            canvas._on_scroll(window, -float(event.get("dx", 0.0)) / 100.0,
                              -float(event.get("dy", 0.0)) / 100.0)
        elif kind == "char":
            for char in event["data"]:
                canvas._on_char(window, ord(char))
        else:
            event.setdefault("time_stamp", self.loop.now)
            canvas.submit_event(event)

    def _flush(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None or self.host is None:
            return
        with self._clock():
            canvas._process_events()

    def _painter_for_frame(self):
        """Hand the surface a recording wrapper around the painter it would build itself."""
        surface = self.surface
        real = getattr(surface, "_painter", None)
        if isinstance(real, HostPainter):
            real = real._real
        font_pt = float(surface.font_pt)
        if (real is None or surface._painter_ratio != surface.ratio
                or getattr(surface, "_painter_font_pt", font_pt) != font_pt):
            real = surface.renderer.painter(font_pt=font_pt, scale=surface.ratio)
        recorder = HostPainter(real)
        surface._painter = recorder
        surface._painter_ratio = surface.ratio
        if hasattr(surface, "_painter_font_pt"):
            surface._painter_font_pt = font_pt
        return recorder

    def frame(self, n=1):
        if n < 1:
            raise ValueError("frame count must be positive")
        for _ in range(n):
            self._flush()
            self.painter = self._painter_for_frame()
            for registry in self._registries():
                registry.clear()
            if self.backend == "glfw":
                # A hidden window's swap chain is occluded: wgpu cancels the frame before
                # the app draws. Run the surface's CPU half -- what ControlSurface.render
                # does before it uploads -- with the glfw-derived size and ratio.
                self.painter.clear()
                self.surface.control.draw(self.painter, *self.surface._box())
            else:
                self.host.draw_frame()
            self._rects = {key: tuple(box) for registry in self._registries()
                           for key, box in registry.items() if box is not None}
            self.size = tuple(int(round(v)) for v in self.canvas.get_logical_size())
            self.loop.advance(self.frame_interval)
        return self.painter

    def screenshot(self, path=None):
        """The GPU's own pixels at device resolution (offscreen canvas only)."""
        if self.backend != "offscreen":
            return super().screenshot(path)
        from .testing import png_encode  # noqa: PLC0415

        self._flush()
        self.painter = self._painter_for_frame()
        image = self.host.draw_frame()
        height, width = image.shape[:2]
        png = png_encode(width, height, image.tobytes())
        if path is not None:
            from pathlib import Path  # noqa: PLC0415

            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(png)
        return png

    def close(self) -> None:
        for patch in self._patches:
            patch.stop()
        self._patches.clear()
        if self.host is not None:
            self.host.close()
            self.host = None
