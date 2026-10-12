"""A frame that raises is reported and shown, never left as a blank window.

Every host draws its control once per frame. When that draw raises, the
host's event loop (rendercanvas, Qt, Tk) catches the exception so the
window survives -- and the window is then presented with whatever the
frame's target held: nothing drawn at all. On Metal that is a solid
magenta surface, elsewhere black or the last frame; in every case the
user sees an application that "does nothing" and the traceback sits in a
logger they never read.

:func:`draw_control` is the one place every host draws a control through.
It runs ``control.draw`` and, when that raises,

* logs the traceback on the ``emtk`` logger at ERROR (once per distinct
  error; repeats of the same error every frame are counted, not re-logged),
* hands it to every handler registered with :func:`add_frame_error_handler`
  (an application writes its crash log there), once per distinct error,
* throws away the half-drawn frame and draws an error panel in its place:
  what failed, the exception, the end of the traceback.

The panel stays until a frame draws cleanly again.
"""
from __future__ import annotations

import logging
import traceback
from collections.abc import Callable

from .painter import ALIGN_LEFT, ALIGN_VCENTER

__all__ = [
    "FrameError",
    "add_frame_error_handler",
    "remove_frame_error_handler",
    "draw_control",
    "draw_error_panel",
    "report_frame_error",
]

logger = logging.getLogger("emtk")

_handlers: list[Callable[["FrameError"], None]] = []
#: Distinct errors seen in this process: key -> number of frames it failed.
_seen: dict[tuple, int] = {}


class FrameError:
    """One failed frame: the exception, its formatted traceback, how often it recurred."""

    def __init__(self, error: BaseException, count: int = 1) -> None:
        self.error = error
        self.count = int(count)
        self.text = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    @property
    def summary(self) -> str:
        """``Type: message`` on one line."""
        message = str(self.error).strip().splitlines()
        first = message[0] if message else ""
        return f"{type(self.error).__name__}: {first}" if first else type(self.error).__name__

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FrameError({self.summary!r}, count={self.count})"


def add_frame_error_handler(handler: Callable[[FrameError], None]) -> None:
    """Call *handler* with a :class:`FrameError` the first time each distinct error occurs."""
    if handler not in _handlers:
        _handlers.append(handler)


def remove_frame_error_handler(handler: Callable[[FrameError], None]) -> None:
    """Undo :func:`add_frame_error_handler`; unknown handlers are ignored."""
    try:
        _handlers.remove(handler)
    except ValueError:
        pass


def _key(error: BaseException) -> tuple:
    frames = traceback.extract_tb(error.__traceback__)
    where = (frames[-1].filename, frames[-1].lineno) if frames else ("", 0)
    return (type(error).__name__, str(error), where)


def report_frame_error(error: BaseException) -> FrameError:
    """Log *error* and notify the handlers, once per distinct error; return its record."""
    key = _key(error)
    count = _seen.get(key, 0) + 1
    _seen[key] = count
    record = FrameError(error, count)
    if count == 1:
        logger.error("a frame failed to draw; the window shows the error instead\n%s",
                     record.text.rstrip())
        for handler in list(_handlers):
            try:
                handler(record)
            except Exception:  # noqa: BLE001 - a broken reporter must not hide the error
                logger.exception("frame error handler %r failed", handler)
    else:
        logger.debug("frame failed again (%d): %s", count, record.summary)
    return record


_PANEL = (40, 18, 22, 255)
_TITLE = (255, 120, 110, 255)
_BODY = (235, 225, 225, 255)
_DIM = (190, 170, 170, 255)


def draw_error_panel(painter, x: float, y: float, w: float, h: float,
                     record: FrameError) -> None:
    """Draw *record* across the box: a title, the exception, the end of its traceback."""
    from .i18n import tr  # noqa: PLC0415

    clear = getattr(painter, "clear", None)
    if callable(clear):
        clear()     # drop the half-drawn frame and any clip it left pushed
    painter.fill_rect(x, y, w, h, _PANEL)
    try:
        line = float(painter.line_height())
    except Exception:  # noqa: BLE001 - a painter without metrics still gets a panel
        line = 16.0
    line = max(line, 12.0) * 1.35
    pad = 16.0
    width = max(w - 2 * pad, 1.0)
    row = y + pad

    def put(string: str, colour, bold: bool = False) -> None:
        nonlocal row
        if row + line > y + h:
            return
        painter.text(x + pad, row, width, line, ALIGN_LEFT | ALIGN_VCENTER,
                     string, colour, bold)
        row += line

    put(tr("This window failed to draw."), _TITLE, bold=True)
    put(record.summary, _BODY)
    if record.count > 1:
        put(tr("Repeated in {count} frames.").format(count=record.count), _DIM)
    put(tr("The full traceback is in the log."), _DIM)
    row += line * 0.5
    tail = [text for text in record.text.rstrip().splitlines() if text.strip()]
    for text in tail[-14:]:
        put(text.rstrip(), _DIM)


def draw_control(control, painter, x: float, y: float, w: float, h: float) -> bool:
    """Draw *control* into *painter*; on an exception report it and draw the error panel.

    Returns
    -------
    bool
        ``True`` when the control drew, ``False`` when the error panel was drawn instead.
    """
    try:
        control.draw(painter, x, y, w, h)
        return True
    except Exception as error:  # noqa: BLE001 - reported and drawn, never swallowed
        record = report_frame_error(error)
        try:
            draw_error_panel(painter, x, y, w, h, record)
        except Exception:  # noqa: BLE001 - the panel itself failed: the log still has it
            logger.exception("could not draw the frame error panel")
        return False
