"""An immediate-mode app drawn over another surface: a form beside a 3-D view.

:class:`OverlaySurface` puts an :class:`~emtk.app.ImApp` (its windows, its
forms, its tables) on top of any :class:`~emtk.app.Surface` -- a molecular
viewer, a plot canvas -- in one target::

    surface = OverlaySurface(viewer_surface, ImApp(gui))

Each frame the base draws first, then the app draws over it *without clearing*,
so wherever the app has no window the base shows through. Events go to the app
when it wants them -- the pointer is over one of its windows, an overlay (a
combo list, a tooltip) is open, or it holds the keyboard (a text field has
focus) -- and to the base otherwise. A press keeps going where it started
until the release, so a drag that leaves a window does not change hands.

The rule is Dear ImGui's: ``io.want_capture_mouse`` / ``want_capture_keyboard``
from the last frame decide, which is how an ImGui app routes input to the game
underneath. An app whose windows include a transparent full-size one (a
:class:`~emtk.docking.DockManager`'s area) answers more precisely with
``pointer_wanted(x, y)``: when it has that method, it decides the pointer.
"""
from __future__ import annotations

from typing import Sequence

from .app import ControlSurface, Surface

__all__ = ["OverlaySurface"]


class _Over(ControlSurface):
    """A control surface that draws over the target instead of clearing it."""

    def render(self, view) -> None:
        if self.renderer is None:
            raise RuntimeError("OverlaySurface: render before attach()")
        if self._painter is None or self._painter_ratio != self.ratio:
            self._painter = self.renderer.painter(font_pt=self.font_pt, scale=self.ratio)
            self._painter_ratio = self.ratio
        painter = self._painter
        painter.clear()
        self.control.draw(painter, *self._box())
        width, height = self.size
        # background=None: load what the base drew, do not clear it.
        self.renderer.render(painter, width, height, view, background=None, format=self.format)


class OverlaySurface(Surface):
    """``base`` underneath, the immediate-mode ``app`` on top.

    Parameters
    ----------
    base : Surface
        Drawn first, into the whole target; gets the events the app does not
        want.
    app : ImApp
        Anything with an ``io`` carrying ``want_capture_mouse`` and
        ``want_capture_keyboard`` (an :class:`~emtk.app.ImApp`), and the
        control contract.
    """

    def __init__(self, base: Surface, app, font_pt: float | None = None) -> None:
        self.base = base
        self.app = app
        kwargs = {} if font_pt is None else {"font_pt": font_pt}
        self.over = _Over(app, **kwargs)
        self._held: Surface | None = None  # who got the press, until the release
        self._pointer = (-1.0, -1.0)

    # -- whose event ------------------------------------------------------ #
    def _io(self, name: str) -> bool:
        io = getattr(self.app, "io", None)
        return bool(getattr(io, name, False)) if io is not None else False

    def _mouse_target(self) -> Surface:
        if self._held is not None:
            return self._held
        hook = getattr(self.app, "pointer_wanted", None)
        if callable(hook):
            return self.over if hook(*self._pointer) else self.base
        return self.over if self._io("want_capture_mouse") else self.base

    # -- lifecycle -------------------------------------------------------- #
    def attach(self, device, format, width, height, ratio) -> None:
        self.base.attach(device, format, width, height, ratio)
        self.over.attach(device, format, width, height, ratio)

    def on_resize(self, width, height, ratio) -> bool:
        a = self.base.on_resize(width, height, ratio)
        b = self.over.on_resize(width, height, ratio)
        return bool(a or b)

    def render(self, view):
        result = self.base.render(view)
        self.over.render(view)
        return result

    def animating(self) -> bool:
        return bool(self.base.animating() or self.over.animating())

    def next_frame_in(self) -> float | None:
        times = [t for t in (self.base.next_frame_in(), self.over.next_frame_in()) if t is not None]
        return min(times) if times else None

    def set_frame_request_callback(self, callback) -> None:
        super().set_frame_request_callback(callback)
        self.base.set_frame_request_callback(callback)
        self.over.set_frame_request_callback(callback)

    def close(self) -> None:
        self.over.close()
        self.base.close()

    # -- input ------------------------------------------------------------ #
    def on_pointer_press(self, x, y, button, modifiers, double=False) -> bool:
        self._pointer = (float(x), float(y))
        target = self._mouse_target()
        self._held = target
        due = bool(target.on_pointer_press(x, y, button, modifiers, double))
        if target is self.base:
            # The app still sees a press outside its windows -- it hits none of
            # them, but a focused text field has to lose focus on it.
            due = bool(self.over.on_pointer_press(x, y, button, modifiers, double)) or due
        return due

    def on_pointer_move(self, x, y, buttons, modifiers) -> bool:
        # The app always hears the pointer, so its hover (and so its claim on
        # the next press) is current.
        self._pointer = (float(x), float(y))
        app_due = bool(self.over.on_pointer_move(x, y, buttons, modifiers))
        target = self._mouse_target()
        if target is self.over:
            return app_due
        return bool(self.base.on_pointer_move(x, y, buttons, modifiers)) or app_due

    def on_pointer_release(self, x, y, button, modifiers) -> bool:
        target = self._held or self._mouse_target()
        self._held = None
        due = bool(target.on_pointer_release(x, y, button, modifiers))
        if target is self.base:
            due = bool(self.over.on_pointer_release(x, y, button, modifiers)) or due
        return due

    def on_wheel(self, x, y, steps, modifiers) -> bool:
        self._pointer = (float(x), float(y))
        return bool(self._mouse_target().on_wheel(x, y, steps, modifiers))

    def _key_target(self) -> Surface:
        wants = self._io("want_capture_keyboard") or self._io("want_text_input")
        return self.over if wants else self.base

    def on_key_press(self, key, text, modifiers) -> bool:
        return bool(self._key_target().on_key_press(key, text, modifiers))

    def on_key_release(self, key, text, modifiers) -> bool:
        return bool(self._key_target().on_key_release(key, text, modifiers))

    def on_files_dropped(self, paths: Sequence[str]) -> bool:
        return bool(self.over.on_files_dropped(paths) or self.base.on_files_dropped(paths))
