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

The user resizes it from any edge or corner (the pointer shows the resize
arrow; the bottom-right grip is the visible handle; ``resizable=False`` turns
it off, ``min_size`` bounds it) and folds it to its header with a double click
on the header -- not on its buttons -- and back. A ``fit_height`` window and a
folded one resize sideways only.
"""
from __future__ import annotations

from collections.abc import Sequence

from . import im_core as _core
from . import im_widgets as _w
from .i18n import tr
from .keys import KEY_ESCAPE

__all__ = ["DialogWindow"]

Rect = tuple[float, float, float, float]


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
    modal : bool
        Wash and blur what is behind the window (:func:`emtk.backdrop.draw_modal_backdrop`);
        ``False`` for a tool window beside the work.

    Attributes
    ----------
    open : bool
        Whether the app should draw it; :meth:`show` / :meth:`hide` flip it.
    box, content_box : tuple or None
        The window and its content region, last frame.
    """

    HEADER_H = 16.0
    PADDING = 8.0

    def __init__(self, title: str, size: Sequence[float] = (420.0, 300.0),
                 pos: Sequence[float] | None = None, key: str = "",
                 escape_closes: bool = True, fit_height: bool = False,
                 close_button: bool = True, modal: bool = True, resizable: bool = True,
                 min_size: Sequence[float] = (160.0, 80.0)) -> None:
        self.title = str(title)
        #: A dialog: what lies behind it, in the frame it is drawn over, is washed and
        #: (``emtk.style.MODAL_BLUR``) blurred, so the window in front is the one in
        #: focus. A tool window that sits beside the work passes ``False``.
        self.modal = bool(modal)
        #: Draw the title bar's ``×``. A window whose content already carries a
        #: labelled Close (the help window) turns it off: one close control, and
        #: Escape still closes.
        self.close_button = bool(close_button)
        self.size = (float(size[0]), float(size[1]))
        self.pos = None if pos is None else (float(pos[0]), float(pos[1]))
        self.key = key or self.title
        self.escape_closes = escape_closes
        #: Size the height to the content drawn last frame (``size[1]`` is then
        #: only the first frame's guess): a form that folds open or shut, or a
        #: denser style, never leaves the window half empty or cut short.
        self.fit_height = bool(fit_height)
        self.open = False
        self.box: Rect | None = None
        self.content_box: Rect | None = None
        self._drag: tuple[float, float] | None = None
        #: Drag any edge or corner to resize (a ``fit_height`` window: its sides only).
        self.resizable = bool(resizable)
        self.min_size = (float(min_size[0]), float(min_size[1]))
        #: Folded to its header by a double click on it; a second one unfolds it at
        #: the height it had. The content still runs, clipped away and inert.
        self.folded = False
        self._resize: tuple | None = None

    # ---------------------------------------------------------------- state
    def show(self) -> None:
        self.open = True

    def hide(self) -> None:
        self.open = False
        self._drag = None
        self._resize = None

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
        # Clamp the complete window, not merely a visible title/header strip. A
        # dialog can outlive a host resize (or a host can be recreated smaller),
        # so the saved position must never leave Apply/Close controls unreachable.
        x = min(max(self.pos[0], fx), max(fx, fx + fw - w))
        y = min(max(self.pos[1], fy), max(fy, fy + fh - h))
        self.box = (x, y, w, h)
        return self.box

    def contains(self, x: float, y: float) -> bool:
        if self.box is None:
            return False
        bx, by, bw, bh = self.box
        return bx <= x < bx + bw and by <= y < by + bh

    # ---------------------------------------------------------------- frame
    def begin(self, frame: Rect, buttons: Sequence[str] = ()) -> str | None:
        """Draw the window and open its content region.

        Returns the label of the header button pressed (``"close"`` for × or
        Escape), or ``None``. Always pair with :meth:`end`.
        """
        x, y, w, h = self.place(frame)
        if self.folded:
            h = self.HEADER_H
            self.box = (x, y, w, h)
        if self.modal:
            from .backdrop import draw_modal_backdrop  # noqa: PLC0415

            draw_modal_backdrop(_core.get_current_context().p, *frame)
        _w.begin(f"{self.title}##dialog-{self.key}", (x, y, w, h))
        style = _core.get_style()
        draw = _core.get_window_draw_list()
        io = _core.get_io()
        resizing = self._resize_zones(frame, (x, y, w, h))
        r, g, b = style.color(_core.Col.WINDOW_BG)[:3]
        draw.add_rect_filled((x, y), (x + w, y + h), (r, g, b, 255))
        draw.add_rect_filled((x, y), (x + w, y + self.HEADER_H),
                             style.color(_core.Col.TITLE_BG_ACTIVE))
        draw.add_rect((x, y), (x + w, y + h), style.color(_core.Col.BORDER))
        if self.resizable and not (self.folded or self.fit_height):
            # The visible handle, as on a floating dock window: every edge resizes too.
            from .docking import GRIP  # noqa: PLC0415

            hot = self._resize is not None and self._resize[0] == "se"
            colour = style.color(_core.Col.BUTTON_HOVERED if hot else _core.Col.HEADER)
            draw.add_triangle_filled((x + w, y + h - GRIP), (x + w, y + h),
                                     (x + w - GRIP, y + h), colour)
        # Translated once, then measured and drawn as the same string; the
        # pressed label stays the caller's source label.
        title = tr(self.title)
        th = _w.calc_text_size(title)[1]
        draw.add_text((x + self.PADDING, y + (self.HEADER_H - th) / 2.0),
                      style.color(_core.Col.TEXT), title)

        pressed = None
        labels = list(buttons) + (["×"] if self.close_button else [])
        shown = [tr(label) for label in labels]
        widths = [_w.calc_text_size(text)[0] + 14.0 for text in shown]
        bh = _core.get_frame_height()
        bx = x + w - sum(widths) - 4.0 * len(labels) - 2.0
        on_button = False
        for label, text, bw in zip(labels, shown, widths):
            _w.set_cursor_screen_pos((bx, y + (self.HEADER_H - bh) / 2.0))
            if _w.button(f"{text}##{self.key}.header.{label}", (bw, bh)):
                pressed = "close" if label == "×" else label
            if label == "×":
                _w.set_item_tooltip(tr("Close this window (Escape).", domain="emtk"))
            on_button = on_button or _w.is_item_hovered()
            bx += bw + 4.0

        mx, my = io.mouse_pos
        over_header = x <= mx < x + w and y <= my < y + self.HEADER_H
        if (io.mouse_clicked[0] and over_header and not on_button and pressed is None
                and not resizing):
            if io.mouse_double_clicked[0]:
                # The window managers' gesture: fold to the header, and back.
                self.folded = not self.folded
                _core.get_current_context().request_frame()
            else:
                self._drag = (mx - x, my - y)
        if self._drag is not None:
            if io.mouse_down[0]:
                self.pos = (mx - self._drag[0], my - self._drag[1])
            else:
                self._drag = None
        if self.escape_closes and io.key == KEY_ESCAPE and self.contains(mx, my):
            pressed = "close"

        p = self.PADDING
        if self.folded:
            # Nothing below the header: the content runs clipped to nothing, and inert.
            self.content_box = (x + p, y + self.HEADER_H, w - 2 * p, 0.0)
        else:
            self.content_box = (x + p, y + self.HEADER_H + p * 0.75, w - 2 * p,
                                h - self.HEADER_H - p * 1.75)
        _w.begin_child(self.content_box)
        return pressed

    def _resize_zones(self, frame: Rect, box: Rect) -> bool:
        """Claim the edges and corners (:func:`emtk.docking.resize_zones`); drag them.

        Returns whether the pointer is on one (or a resize is under way), so the
        header does not start a move or a fold there.
        """
        if not self.resizable:
            return False
        from .docking import ZONE_CURSORS, resize_frame, resize_zones  # noqa: PLC0415

        ctx = _core.get_current_context()
        io = ctx.io
        mx, my = io.mouse_pos
        sideways = self.folded or self.fit_height
        hot = None
        if self._resize is None:
            for zone, rects in resize_zones(box, folded=sideways).items():
                for index, rect in enumerate(rects):
                    if ctx.item_add(rect, f"##{self.key}.edge.{zone}.{index}") and hot is None:
                        hot = zone
            if hot is not None and io.mouse_clicked[0]:
                self._resize = (hot, mx, my, box[0], box[1], box[2],
                                self.size[1] if self.folded else box[3])
        if self._resize is not None:
            zone, ox, oy, x0, y0, w0, h0 = self._resize
            hot = zone
            if io.mouse_down[0]:
                nx, ny, nw, nh = resize_frame(zone, (x0, y0, w0, h0), mx - ox, my - oy,
                                              (self.min_size[0],
                                               max(self.min_size[1], self.HEADER_H + 20.0)),
                                              frame)
                self.pos = (nx, y0 if sideways else ny)
                self.size = (nw, h0 if sideways else nh)
                ctx.request_frame()
            else:
                self._resize = None
        if hot is not None:
            io.mouse_cursor = 4 if sideways else ZONE_CURSORS[hot]
        return hot is not None

    def end(self) -> None:
        """Close the content region and the window."""
        if self.fit_height and self.content_box is not None and not self.folded:
            # the cursor sits under the last item: that is how tall the content is
            used = float(_w.get_cursor_screen_pos()[1]) - self.content_box[1]
            height = round(self.HEADER_H + self.PADDING * 1.75 + max(used, 0.0))
            if abs(height - self.size[1]) >= 1.0:
                self.size = (self.size[0], float(height))
                _core.get_current_context().request_frame()
        _w.end_child()
        _w.end()
