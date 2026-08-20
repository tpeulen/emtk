"""``Event``, ``Router``, ``OverlayStack``: one input contract, one capture slot, one z-order.

The chrome grew three capture layers with three release paths -- the canvas's
``_gui_grab``, the window framework's ``_window_body_drag`` plus eight
``_dragging_*`` flags, and a widget's own ``_held`` -- and that surface is
where BUG-001/002 lived (a press with no release, a release that never reached
its presser). It also had two hit orders to keep in sync: the list things are
painted in and the list they are hit-tested in.

This module is the toolkit-level answer, standalone and tested standalone:

* :class:`Event` -- every input as one record (``press release move wheel
  key_press key_release enter leave cancel``), position, button, held
  buttons, modifiers, click count, wheel deltas, key/text, time;
* :class:`Router` -- ``dispatch(ev)``: the capturer if there is one, else the
  deepest layer under the pointer; a handler returns ``Consumed``, ``Pass`` or
  ``Capture(handler)``; the release **always** goes to the capturer, with a
  position, and clears the capture; a foreign press or an explicit
  ``cancel`` tears the capture down (BUG-002's heuristic made first-class);
  enter/leave are computed from where consecutive moves land; a wheel is
  consumed by any layer under it -- never falls through to the camera unless
  no layer is there;
* :class:`OverlayStack` -- layers (windows, popups, tooltips, modals) hit-
  tested top-down and painted bottom-up from **one** list.

The chrome (``ui/gui.py``) migrates onto this piece by piece; nothing here
imports it.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from .style import hit

__all__ = ["Capture", "Consumed", "Event", "Handler", "Layer", "OverlayStack", "Pass", "Router", "Verdict"]

Rect = tuple[float, float, float, float]

KINDS = ("press", "release", "move", "wheel", "key_press", "key_release", "enter", "leave", "cancel", "tick")


@dataclass
class Event:
    kind: str
    x: float = -1.0
    y: float = -1.0
    button: int = 0            # the button that changed (press/release)
    buttons: int = 0           # the mask held now
    modifiers: int = 0
    clicks: int = 1
    wheel_dx: float = 0.0
    wheel_dy: float = 0.0
    key: int = 0
    text: str = ""
    time: float = field(default_factory=_time.monotonic)

    def at(self, x: float, y: float) -> "Event":
        """The same event, repositioned (a capturer sees window-local coordinates)."""
        return Event(self.kind, x, y, self.button, self.buttons, self.modifiers, self.clicks,
                     self.wheel_dx, self.wheel_dy, self.key, self.text, self.time)


class Verdict:
    """What a handler returns. ``Consumed``/``Pass`` are singletons; ``Capture`` names who wants the rest."""


class _Consumed(Verdict):
    def __repr__(self) -> str:
        return "Consumed"


class _Pass(Verdict):
    def __repr__(self) -> str:
        return "Pass"


Consumed = _Consumed()
Pass = _Pass()


@dataclass
class Capture(Verdict):
    handler: "Handler"


class Handler(Protocol):
    def event(self, ev: Event) -> Verdict: ...


class Layer(Protocol):
    """Something in the overlay stack: it knows its box, takes events, paints itself."""

    def bounds(self) -> Optional[Rect]: ...
    def event(self, ev: Event) -> Verdict: ...


class OverlayStack:
    """Z-ordered layers: hit top-down, painted bottom-up, from one list."""

    def __init__(self) -> None:
        self._layers: list[Any] = []

    def add(self, layer, *, top: bool = True) -> None:
        if layer in self._layers:
            self._layers.remove(layer)
        if top:
            self._layers.append(layer)
        else:
            self._layers.insert(0, layer)

    def remove(self, layer) -> None:
        if layer in self._layers:
            self._layers.remove(layer)

    def raise_(self, layer) -> None:
        self.add(layer, top=True)

    def layers(self) -> list:
        """Bottom-up: the paint order."""
        return list(self._layers)

    def hit(self, x: float, y: float):
        """The topmost layer that owns the point, or ``None``.

        ``bounds()`` is the box; a layer that is not a rectangle -- the chrome
        is a menu bar, a column, a strip and a handful of floating windows --
        may say so with a ``contains(x, y)`` of its own, and then that answer
        is the one that counts.
        """
        for layer in reversed(self._layers):
            visible = getattr(layer, "visible", True)
            if not visible:
                continue
            probe = getattr(layer, "contains", None)
            if probe is not None:
                if probe(x, y):
                    return layer
                continue
            box = layer.bounds()
            if box is not None and hit(x, y, *box):
                return layer
        return None

    def __len__(self) -> int:
        return len(self._layers)

    def __contains__(self, layer) -> bool:
        return layer in self._layers


class Router:
    """One capture slot; the release always reaches the presser.

    Parameters
    ----------
    stack : OverlayStack
        Where uncaptured events are hit-tested.
    fallthrough : callable, optional
        ``fallthrough(ev) -> Verdict`` for events no layer took (the camera).
    """

    def __init__(self, stack: OverlayStack, fallthrough: Optional[Callable[[Event], Verdict]] = None) -> None:
        self.stack = stack
        self.fallthrough = fallthrough
        self.capturer: Any = None
        self.hovered: Any = None
        self.focus: Any = None
        self.log: list[tuple[str, Any]] = []

    # -- capture --------------------------------------------------------- #
    def cancel(self) -> None:
        """Tear the capture down (a foreign press, a lost window, an Escape)."""
        if self.capturer is not None:
            try:
                self.capturer.event(Event("cancel"))
            finally:
                self.capturer = None

    def _deliver(self, target, ev: Event) -> Verdict:
        verdict = target.event(ev)
        if isinstance(verdict, Capture):
            self.capturer = verdict.handler
            return Consumed
        return verdict if isinstance(verdict, Verdict) else (Consumed if verdict else Pass)

    # -- dispatch ---------------------------------------------------------- #
    def dispatch(self, ev: Event) -> Verdict:
        self.log.append((ev.kind, self.capturer))
        if ev.kind == "cancel":
            self.cancel()
            return Consumed
        if ev.kind in ("key_press", "key_release"):
            target = self.capturer or self.focus
            if target is not None:
                v = self._deliver(target, ev)
                if v is Consumed:
                    return v
            return self._fall(ev)
        if ev.kind == "press" and self.capturer is not None:
            # A capture lives from a press to its release, so a *second* press
            # means the release never came. Every host delivers press-after-
            # release -- but the DOM sends `dblclick` as an extra press with no
            # trailing release (BUGS/001), and a capture left standing routed
            # every later move to its holder and swallowed the next click's
            # release before it could pick (BUGS/002). Tear it down here, where
            # the lost release is first provable, rather than guessing later.
            self.cancel()
        if self.capturer is not None:
            verdict = self._deliver(self.capturer, ev)
            if ev.kind == "release":
                self.capturer = None
            return verdict if verdict is not Pass else Consumed
        under = self.stack.hit(ev.x, ev.y)
        if ev.kind == "move":
            self._hover(under, ev)
        if under is None:
            return self._fall(ev)
        if ev.kind == "press":
            self.stack.raise_(under) if getattr(under, "raise_on_press", True) else None
            self.focus = under
        verdict = self._deliver(under, ev)
        if ev.kind == "wheel":
            # A wheel over a layer belongs to the layer, consumed or not: it must
            # never scroll the camera underneath a window (the round-22 bug).
            return Consumed
        return verdict if verdict is not Pass else self._fall(ev)

    def _hover(self, under, ev: Event) -> None:
        if under is self.hovered:
            return
        if self.hovered is not None:
            try:
                self.hovered.event(Event("leave", ev.x, ev.y, time=ev.time))
            except Exception:  # noqa: BLE001 - a leave must not break the move
                pass
        self.hovered = under
        if under is not None:
            under.event(Event("enter", ev.x, ev.y, time=ev.time))

    def _fall(self, ev: Event) -> Verdict:
        if self.fallthrough is None:
            return Pass
        v = self.fallthrough(ev)
        return v if isinstance(v, Verdict) else (Consumed if v else Pass)
