"""A modal progress overlay: what the viewport shows while it is busy.

Why this exists
---------------
Opening a structure is not instant. The nuclear pore takes seconds even after
the quadratic passes were removed from it, and during those seconds cmtk
looked **broken**: the viewport kept drawing the previous scene, the menus
still highlighted under the mouse, and nothing anywhere said that work was
happening. A user cannot tell that from a hang, so the reasonable thing to do
is exactly the wrong thing -- click again, and start a second load.

So this does the two things that turn a wait into a wait:

* it **says what is happening**, with a bar, a percentage and an estimate;
* it **blocks the interface**, so the click that would start a second load
  lands on the overlay instead of on the menu behind it.

It is deliberately a *general* widget rather than a loading screen for files.
Anything that takes long enough to notice -- a trace, a surface, a trajectory
scrub, a fit -- can drive it, which is why it knows nothing about structures.

Driving it
----------
Three calls, and the middle one may be called as often as convenient::

    gui.progress.begin("Loading 5xyz.cif")
    gui.progress.update(0.4, "reading beads")   # 0..1, or None when unknown
    gui.progress.end()

:meth:`update` accepts ``None`` for the fraction, which draws an indeterminate
bar. That is not a decoration: a reader that cannot say how much is left is
common (a stream, an unknown record count), and forcing it to invent a
percentage would make the bar lie.

On the estimate
---------------
The ETA is deliberately **conservative and slow to appear**. An estimate formed
from the first 2 % of a load is nearly always wrong, and a countdown that jumps
from four minutes to nine seconds is worse than none -- it teaches people to
distrust the number. So it waits for :data:`_ETA_MIN_FRACTION` of the work and
:data:`_ETA_MIN_SECONDS` of wall clock before saying anything, and then smooths
what it reports. It is also **monotone in the short run**: it will not rise
again once it has fallen, unless the rate genuinely collapses.
"""
from __future__ import annotations

import time

from .. import style
from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER

__all__ = ["ProgressOverlay"]

#: Fraction of the work that must be done before an estimate is offered.
_ETA_MIN_FRACTION = 0.05

#: Seconds that must have passed before an estimate is offered.
_ETA_MIN_SECONDS = 0.75

#: How long a completed overlay lingers, so a fast load is still *seen* to have
#: happened rather than flashing.
_LINGER_SECONDS = 0.15


def format_duration(seconds: float) -> str:
    """Return *seconds* as a short human duration.

    Parameters
    ----------
    seconds : float

    Returns
    -------
    str
        ``"12s"``, ``"1m 04s"``, ``"2h 03m"``. Deliberately coarse: a progress
        estimate that claims tenths of a second is claiming a precision it does
        not have.
    """
    seconds = max(float(seconds), 0.0)
    if seconds < 60.0:
        return f"{int(round(seconds))}s"
    if seconds < 3600.0:
        minutes, rest = divmod(int(round(seconds)), 60)
        return f"{minutes}m {rest:02d}s"
    hours, rest = divmod(int(round(seconds)), 3600)
    return f"{hours}h {rest // 60:02d}m"


class ProgressOverlay:
    """Modal progress reporting, drawn through the shared painter seam.

    Attributes
    ----------
    active : bool
        Whether anything is drawn and input is blocked. This is the flag the
        canvas consults before handing an event to the chrome.
    title : str
        What is happening, in a few words.
    message : str
        The current step, which changes as work proceeds.
    fraction : float or None
        Completion in ``0..1``, or ``None`` when it is not known.
    cancellable : bool
        Whether a Cancel button is offered. It is only honest to show one when
        the caller can actually act on :attr:`cancelled`.
    cancelled : bool
        Set when the user asks to stop. The *caller* must poll this and stop;
        nothing here can interrupt it.
    """

    #: Height of the bar itself, in unscaled pixels.
    BAR_H = 10

    #: Padding inside the panel.
    PAD = 14

    #: Width of the panel, as a fraction of the viewport, and its bounds.
    WIDTH_FRACTION = 0.42
    MIN_W = 260
    MAX_W = 560

    def __init__(self) -> None:
        self.active = False
        self.title = ""
        self.message = ""
        self.fraction: float | None = None
        self.cancellable = False
        self.cancelled = False
        self._started = 0.0
        self._rate: float | None = None
        self._last_eta: float | None = None
        self._finished_at: float | None = None
        self._cancel_rect: tuple[float, float, float, float] | None = None

    # -- driving it ---------------------------------------------------------
    def begin(self, title: str, *, message: str = "", cancellable: bool = False) -> None:
        """Start reporting. Everything resets, including a previous cancel."""
        self.active = True
        self.title = str(title or "Working")
        self.message = str(message or "")
        self.fraction = None
        self.cancellable = bool(cancellable)
        self.cancelled = False
        self._started = time.monotonic()
        self._rate = None
        self._last_eta = None
        self._finished_at = None

    def update(
        self,
        fraction: float | None = None,
        message: str | None = None,
    ) -> None:
        """Report progress.

        Parameters
        ----------
        fraction : float or None, optional
            Completion in ``0..1``. ``None`` leaves the bar indeterminate,
            which is the honest answer for a step that cannot measure itself.
        message : str, optional
            The current step. Omitted leaves the previous one standing, so a
            caller that only has a number does not have to invent words.
        """
        if not self.active:
            return
        if message is not None:
            self.message = str(message)
        if fraction is None:
            return

        try:
            value = float(fraction)
        except (TypeError, ValueError):
            return
        value = min(max(value, 0.0), 1.0)
        # Never go backwards: a caller reporting two independent phases would
        # otherwise make the bar retreat, which reads as an error.
        self.fraction = value if self.fraction is None else max(self.fraction, value)
        self._update_rate()

    def end(self) -> None:
        """Stop reporting and unblock the interface."""
        self.active = False
        self.title = ""
        self.message = ""
        self.fraction = None
        self.cancellable = False
        self._finished_at = None
        self._cancel_rect = None

    # -- the estimate -------------------------------------------------------
    def _update_rate(self) -> None:
        """Recompute the rate as the *overall average*: done over elapsed.

        Deliberately not an incrementally smoothed rate. That was tried and it
        blows up on the first observation: a caller that reports 5 % a
        millisecond after ``begin`` implies a rate of fifty per second, and an
        estimate built from it says "about 0s left" for the rest of the load --
        which was exactly what the first screenshot of this widget showed.

        An overall average cannot do that, because :meth:`eta_seconds` refuses
        to divide until :data:`_ETA_MIN_SECONDS` of wall clock have passed. It
        is also the more honest summary of an uneven load: what is wanted is
        "how fast has this gone so far", not "how fast was the last step".
        """
        elapsed = time.monotonic() - self._started
        done = self.fraction or 0.0
        if elapsed < _ETA_MIN_SECONDS or done <= 0.0:
            return
        self._rate = done / elapsed

    def eta_seconds(self) -> float | None:
        """Seconds remaining, or ``None`` when it is too early to say.

        Returns
        -------
        float or None
            ``None`` until enough of the work and enough wall clock have
            passed for the number to mean anything -- see the module docstring
            on why an early estimate is worse than none.
        """
        if not self.active or self.fraction is None or self._rate in (None, 0.0):
            return None
        elapsed = time.monotonic() - self._started
        if self.fraction < _ETA_MIN_FRACTION or elapsed < _ETA_MIN_SECONDS:
            return None
        remaining = (1.0 - self.fraction) / self._rate
        if remaining < 0.0:
            return None
        # Monotone in the short run: an estimate that ticks upward while you
        # watch it is the single thing that makes people stop believing them.
        if self._last_eta is not None:
            remaining = min(remaining, self._last_eta)
        self._last_eta = remaining
        return remaining

    def status_text(self) -> str:
        """The one line under the bar: percentage, elapsed and estimate."""
        parts = []
        if self.fraction is not None:
            parts.append(f"{self.fraction * 100.0:.0f}%")
        if self.active:
            parts.append(format_duration(time.monotonic() - self._started))
        eta = self.eta_seconds()
        if eta is not None:
            # Floored at a second: "about 0s left" is not an estimate, it is a
            # claim that the wait is over while the user is still waiting.
            parts.append(f"about {format_duration(max(eta, 1.0))} left")
        return "  ".join(parts)

    # -- input --------------------------------------------------------------
    def handle_press(self, x: float, y: float) -> bool:
        """Consume a press. Returns whether the overlay took it.

        It takes **every** press while active, not only the ones on Cancel.
        That is the blocking half of the widget: a press that fell through to
        the menu behind would start the second load this exists to prevent.
        """
        if not self.active:
            return False
        rect = self._cancel_rect
        if self.cancellable and rect is not None:
            rx, ry, rw, rh = rect
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self.cancelled = True
        return True

    # -- drawing ------------------------------------------------------------
    def paint(self, painter, width: float, height: float, scale: float = 1.0) -> None:
        """Draw the scrim and the panel.

        Parameters
        ----------
        painter : object
            Anything with the six painter operations; see ``ui/__init__``.
        width, height : float
            Viewport size in the painter's own units.
        scale : float, optional
            Chrome scale, so the panel follows the UI-size knob like the rest
            of the chrome rather than staying one fixed size.
        """
        if not self.active:
            return

        pad = self.PAD * scale
        bar_h = self.BAR_H * scale
        line = painter.line_height()

        panel_w = min(max(width * self.WIDTH_FRACTION, self.MIN_W * scale), self.MAX_W * scale)
        panel_w = min(panel_w, width - 2 * pad)
        rows = 2 if self.message else 1
        panel_h = pad * 2 + line * (rows + 1) + bar_h + pad * 0.7
        if self.cancellable:
            panel_h += line + pad * 0.6
        px = (width - panel_w) * 0.5
        py = (height - panel_h) * 0.5

        # A scrim over everything: it dims the stale scene, which is the visual
        # cue that it is stale, and it makes plain that the chrome behind is
        # not accepting input.
        painter.fill_rect(0, 0, width, height, (0, 0, 0, 140))

        painter.fill_rect(px, py, panel_w, panel_h, style.WINDOW_BG)
        painter.stroke_rect(px, py, panel_w, panel_h, style.BORDER)

        text_x = px + pad
        text_w = panel_w - 2 * pad
        y = py + pad
        painter.text(text_x, y, text_w, line, ALIGN_VCENTER | ALIGN_LEFT,
                     self._fit(painter, self.title, text_w), style.TEXT)
        if self.message:
            y += line
            painter.text(text_x, y, text_w, line, ALIGN_VCENTER | ALIGN_LEFT,
                         self._fit(painter, self.message, text_w), style.DIM)

        y += line + pad * 0.4
        bar_w = panel_w - 2 * pad
        painter.fill_rect(text_x, y, bar_w, bar_h, style.FRAME_BG)
        if self.fraction is None:
            # Indeterminate: a block that sweeps. It says "working" without
            # claiming a proportion nobody measured.
            span = bar_w * 0.28
            phase = (time.monotonic() * 0.6) % 1.0
            painter.fill_rect(
                text_x + (bar_w + span) * phase - span, y, span, bar_h, style.SLIDER_GRAB
            )
        elif self.fraction > 0.0:
            painter.fill_rect(text_x, y, bar_w * self.fraction, bar_h, style.SLIDER_GRAB)
        painter.stroke_rect(text_x, y, bar_w, bar_h, style.BORDER)

        y += bar_h + pad * 0.3
        status = self.status_text()
        if status:
            painter.text(text_x, y, text_w, line, ALIGN_VCENTER | ALIGN_LEFT,
                         status, style.DIM)

        self._cancel_rect = None
        if self.cancellable:
            label = "Cancelling…" if self.cancelled else "Cancel"
            btn_w = painter.text_width(label) + pad * 2
            btn_h = line + pad * 0.4
            bx = px + panel_w - pad - btn_w
            by = py + panel_h - pad - btn_h + pad * 0.35
            painter.fill_rect(bx, by, btn_w, btn_h, style.BUTTON)
            painter.stroke_rect(bx, by, btn_w, btn_h, style.BORDER)
            painter.text(bx, by, btn_w, btn_h, ALIGN_CENTER, label, style.TEXT)
            self._cancel_rect = (bx, by, btn_w, btn_h)

    @staticmethod
    def _fit(painter, text: str, limit: float) -> str:
        """Trim *text* with an ellipsis until it fits *limit*."""
        if painter.text_width(text) <= limit:
            return text
        trimmed = text
        while trimmed and painter.text_width(trimmed + "…") > limit:
            trimmed = trimmed[:-1]
        return (trimmed + "…") if trimmed else ""
