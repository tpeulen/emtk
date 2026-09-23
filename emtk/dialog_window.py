"""``emtk.dialog_window`` -- a titled window over an app: a dialog or a tool window.

An emtk window (:func:`emtk.begin`) is a box to lay out in: no background, no
title bar, no chrome. An application that shows a dialog over its plots needs
one with all three -- an opaque body, a header with the title that drags the
window, a close button -- and each app was drawing its own. This is that one.

.. code-block:: python

    settings = DialogWindow("GMM Settings", size=(420, 330))
    ...
    # every frame, inside emtk.frame
    if settings.open:
        pressed = settings.begin(app_box)          # header, body, child region
        draw_form(spec, model, form)               # the content
        settings.end()
        if pressed == "close":
            settings.hide()

``begin`` places the window (centred at first, or where the user dragged it,
kept on screen), paints it, draws the header's buttons -- ``buttons`` plus the
closing × -- and opens a child region for the content. It returns the header
button pressed, ``"close"`` for × or Escape, or ``None``. :attr:`box` and
:attr:`content_box` are the screen rectangles of the last frame, for a test or
a screenshot of just the dialog.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from . import im_core as _core
from . import im_widgets as _w
from .keys import KEY_ESCAPE

__all__ = ["DialogWindow"]

Rect = Tuple[float, float, float, float]


class DialogWindow:
    """A movable, closable window with a title bar and an opaque body.

    Parameters
    ----------
    title : str
        Shown in the header; also the window's identity (with *key*).
    size : tuple of float
        ``(w, h)``; clamped to the frame it is drawn in.
    pos : tuple of float, optional
        Top-left corner; centred in the frame when omitted.
    key : str, optional
        Distinguishes two windows with one title.
    escape_closes : bool
        Escape (while the pointer is over the window) returns ``"close"``.

    Attributes
    ----------
    open : bool
        Whether the app should draw it; :meth:`show` / :meth:`hide` flip it.
    box, content_box : tuple or None
        The window and its content region, last frame.
    """

    HEADER_H = 26.0
    PADDING = 8.0

    def __init__(self, title: str, size: Sequence[float] = (420.0, 300.0),
                 pos: Optional[Sequence[float]] = None, key: str = "",
                 escape_closes: bool = True, fit_height: bool = False) -> None:
        self.title = str(title)
        self.size = (float(size[0]), float(size[1]))
        self.pos = None if pos is None else (float(pos[0]), float(pos[1]))
        self.key = key or self.title
        self.escape_closes = escape_closes
        #: Size the height to the content drawn last frame (``size[1]`` is then
        #: only the first frame's guess): a form that folds open or shut, or a
        #: denser style, never leaves the window half empty or cut short.
        self.fit_height = bool(fit_height)
        self.open = False
        self.box: Optional[Rect] = None
        self.content_box: Optional[Rect] = None
        self._drag: Optional[Tuple[float, float]] = None

    # ---------------------------------------------------------------- state
    def show(self) -> None:
        self.open = True

    def hide(self) -> None:
        self.open = False
        self._drag = None

    def toggle(self) -> None:
        if self.open:
            self.hide()
        else:
            self.show()

    def place(self, frame: Rect) -> Rect:
        """The window's box in *frame*: where it was put, kept on screen."""
        fx, fy, fw, fh = frame
        w = min(self.size[0], max(fw - 20.0, 80.0))
        h = min(self.size[1], max(fh - 20.0, self.HEADER_H + 20.0))
        if self.pos is None:
            self.pos = (fx + (fw - w) / 2.0, fy + (fh - h) / 2.0)
        x = min(max(self.pos[0], fx), fx + fw - min(w, 60.0))
        y = min(max(self.pos[1], fy), fy + fh - self.HEADER_H)
        self.box = (x, y, w, h)
        return self.box

    def contains(self, x: float, y: float) -> bool:
        if self.box is None:
            return False
        bx, by, bw, bh = self.box
        return bx <= x < bx + bw and by <= y < by + bh

    # ---------------------------------------------------------------- frame
    def begin(self, frame: Rect, buttons: Sequence[str] = ()) -> Optional[str]:
        """Draw the window and open its content region.

        Returns the label of the header button pressed (``"close"`` for × or
        Escape), or ``None``. Always pair with :meth:`end`.
        """
        x, y, w, h = self.place(frame)
        _w.begin(f"{self.title}##dialog-{self.key}", (x, y, w, h))
        style = _core.get_style()
        draw = _core.get_window_draw_list()
        r, g, b = style.color(_core.Col.WINDOW_BG)[:3]
        draw.add_rect_filled((x, y), (x + w, y + h), (r, g, b, 255))
        draw.add_rect_filled((x, y), (x + w, y + self.HEADER_H),
                             style.color(_core.Col.TITLE_BG_ACTIVE))
        draw.add_rect((x, y), (x + w, y + h), style.color(_core.Col.BORDER))
        io = _core.get_io()
        th = _w.calc_text_size(self.title)[1]
        draw.add_text((x + self.PADDING, y + (self.HEADER_H - th) / 2.0),
                      style.color(_core.Col.TEXT), self.title)

        pressed = None
        labels = list(buttons) + ["×"]
        widths = [_w.calc_text_size(label)[0] + 14.0 for label in labels]
        bh = _core.get_frame_height()
        bx = x + w - sum(widths) - 4.0 * len(labels) - 2.0
        on_button = False
        for label, bw in zip(labels, widths):
            _w.set_cursor_screen_pos((bx, y + (self.HEADER_H - bh) / 2.0))
            if _w.button(f"{label}##{self.key}.header.{label}", (bw, bh)):
                pressed = "close" if label == "×" else label
            on_button = on_button or _w.is_item_hovered()
            bx += bw + 4.0

        mx, my = io.mouse_pos
        over_header = x <= mx < x + w and y <= my < y + self.HEADER_H
        if io.mouse_clicked[0] and over_header and not on_button and pressed is None:
            self._drag = (mx - x, my - y)
        if self._drag is not None:
            if io.mouse_down[0]:
                self.pos = (mx - self._drag[0], my - self._drag[1])
            else:
                self._drag = None
        if self.escape_closes and io.key == KEY_ESCAPE and self.contains(mx, my):
            pressed = "close"

        p = self.PADDING
        self.content_box = (x + p, y + self.HEADER_H + p * 0.75, w - 2 * p,
                            h - self.HEADER_H - p * 1.75)
        _w.begin_child(self.content_box)
        return pressed

    def end(self) -> None:
        """Close the content region and the window."""
        if self.fit_height and self.content_box is not None:
            # the cursor sits under the last item: that is how tall the content is
            used = float(_w.get_cursor_screen_pos()[1]) - self.content_box[1]
            height = round(self.HEADER_H + self.PADDING * 1.75 + max(used, 0.0))
            if abs(height - self.size[1]) >= 1.0:
                self.size = (self.size[0], float(height))
                _core.get_current_context().request_frame()
        _w.end_child()
        _w.end()
