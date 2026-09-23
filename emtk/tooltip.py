"""The frame's one tooltip: when it shows, where it goes, and how it is drawn.

A widget says *what* its tooltip is -- ``set_item_tooltip("...")`` while it is
hovered, which :meth:`~emtk.im_core.Context.set_tooltip` records together with
the item it belongs to. This module decides the rest, once per frame, at the
end of :meth:`~emtk.im_core.Context.end_frame` -- after the overlays, so the
tooltip lies over everything the frame drew, a combo's open list included.

Timing, as Dear ImGui and the desktop toolkits do it:

* a tooltip shows once the pointer has rested on the same item for
  :attr:`~emtk.im_core.Style.tooltip_delay` seconds (0.5);
* it hides when the pointer leaves the item, and on a press, a held button, a
  wheel or a key -- and stays hidden while the pointer is still on that item;
* once one has shown, the next item's tooltip shows **at once** while the
  pointer moves on within :attr:`~emtk.im_core.Style.tooltip_grace` seconds
  (the "warm" state), so reading along a row of controls does not wait at
  every one.

The delay needs a frame when it runs out, although nothing happened: the
context asks for one with :meth:`~emtk.im_core.Context.request_frame_at`, the
frame's end turns it into :attr:`~emtk.im_core.IO.next_frame_in`, and a host
reads that (:func:`emtk.app.next_frame_in`) and schedules *one* wake-up --
never a stream of frames.

Everything is in logical pixels, clamped to the frame's box: the painter
applies the device ratio, once.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = ["CURSOR_OFFSET", "MARGIN", "PAD", "update", "place", "wrap"]

#: Where the box sits from the pointer, so the cursor does not cover its first
#: character (``TOOLTIP_DEFAULT_OFFSET_MOUSE``).
CURSOR_OFFSET = (16.0, 10.0)
#: Room kept between the box and the frame's edge.
MARGIN = 4.0
#: Padding inside the box.
PAD = 6.0

_STATE = "__tooltip__"


def wrap(p, text: str, room: float) -> list[str]:
    """*text* as lines no wider than *room*: at its own line breaks, then at
    spaces, and mid-word only where one word alone is wider."""
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = f"{line} {word}" if line else word
            if p.text_width(trial) <= room or (not line and len(word) <= 1):
                line = trial
                continue
            if line:
                lines.append(line)
            line = ""
            for char in word:
                if line and p.text_width(line + char) > room:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return lines


def place(pointer: tuple[float, float], size: tuple[float, float],
          frame: tuple[float, float, float, float]) -> tuple[float, float]:
    """Where a box of *size* goes for a pointer at *pointer*, inside *frame*.

    Below-right of the pointer; flipped to its left when that runs past the
    right edge, above it when past the bottom; then clamped inside the frame,
    so a box larger than the room left still starts on screen.
    """
    fx, fy, fw, fh = frame
    w, h = size
    mx, my = pointer
    ox, oy = CURSOR_OFFSET
    x, y = mx + ox, my + oy
    if x + w > fx + fw - MARGIN:
        x = mx - w - MARGIN
    if y + h > fy + fh - MARGIN:
        y = my - h - MARGIN
    x = min(max(x, fx + MARGIN), max(fx + fw - MARGIN - w, fx + MARGIN))
    y = min(max(y, fy + MARGIN), max(fy + fh - MARGIN - h, fy + MARGIN))
    return (x, y)


def _interrupted(io) -> bool:
    """A press, a held button, a wheel or a key: what hides a tooltip."""
    return (any(io.mouse_clicked) or any(io.mouse_down) or any(io.mouse_released)
            or bool(io.mouse_wheel) or bool(getattr(io, "mouse_wheel_h", 0.0))
            or bool(io.key) or bool(io.text))


def update(ctx) -> Optional[tuple[float, float, float, float]]:
    """Decide and draw this frame's tooltip. Returns its box, or ``None``.

    Called once by :meth:`~emtk.im_core.Context.end_frame`, after the
    overlays. Reads :attr:`ctx.tooltip` and :attr:`ctx.tooltip_owner` (the
    item it belongs to) and keeps its timers in ``ctx.storage``.
    """
    io = ctx.io
    style = ctx.style
    st: dict = ctx.storage.setdefault(_STATE, {
        "owner": None, "since": 0.0, "shown": False,
        "warm_until": float("-inf"), "suppressed": None, "box": None,
    })
    st["box"] = None
    now = float(io.now)
    text = ctx.tooltip
    owner: Any = ctx.tooltip_owner if text else None
    delay = max(float(getattr(style, "tooltip_delay", 0.5)), 0.0)
    grace = max(float(getattr(style, "tooltip_grace", 0.6)), 0.0)

    if _interrupted(io):
        # Gone, cooled, and not back while the pointer stays on this item.
        st.update(owner=None, shown=False, warm_until=float("-inf"),
                  suppressed=owner if owner is not None else st.get("owner"))
        ctx.box_tooltip = None
        return None
    if owner is None or io.mouse_pos == (-1.0, -1.0):
        if st["shown"]:
            st["warm_until"] = now + grace
        st.update(owner=None, shown=False, suppressed=None)
        ctx.box_tooltip = None
        return None
    if st.get("suppressed") is not None:
        if owner == st["suppressed"]:
            ctx.box_tooltip = None
            return None
        st["suppressed"] = None
    if owner != st["owner"]:
        warm = st["shown"] or now <= st["warm_until"]
        st.update(owner=owner, since=now, shown=warm)
    if not st["shown"] and now - st["since"] >= delay - 1e-9:
        st["shown"] = True
    if not st["shown"]:
        # One wake-up when the delay runs out -- not a frame per frame.
        ctx.request_frame_at(st["since"] + delay)
        ctx.box_tooltip = None
        return None
    st["warm_until"] = now + grace
    box = draw(ctx, str(text))
    ctx.box_tooltip = st["box"] = box
    return box


def draw(ctx, text: str) -> tuple[float, float, float, float]:
    """Paint *text* as the tooltip at the pointer, over everything.

    In the default style: the popup background (made opaque, as a list over a
    form is), the border and the text colour of ``ctx.style``.
    """
    from .im_core import Col  # noqa: PLC0415 - im_core imports this module
    from .painter import ALIGN_LEFT, ALIGN_VCENTER  # noqa: PLC0415

    p = ctx.p
    style = ctx.style
    fx, fy, fw, fh = ctx.box
    room = min(float(getattr(style, "tooltip_max_width", 360.0)),
               fw - 2.0 * (MARGIN + PAD))
    room = max(room, p.text_width("M") * 4.0)
    lines = wrap(p, text, room)
    line_h = p.line_height()
    w = max((p.text_width(line) for line in lines), default=0.0) + 2.0 * PAD
    w = min(w, max(fw - 2.0 * MARGIN, 1.0))
    h = line_h * len(lines) + PAD
    x, y = place(tuple(ctx.io.mouse_pos), (w, h), ctx.box)
    background = tuple(style.color(Col.POPUP_BG))
    background = (*background[:3], 255)
    p.push_clip(fx, fy, fw, fh)
    try:
        p.stroke_rect(x, y, w, h, tuple(style.color(Col.BORDER)), background)
        for i, line in enumerate(lines):
            p.text(x + PAD, y + PAD * 0.5 + i * line_h, max(w - 2.0 * PAD, 1.0), line_h,
                   ALIGN_LEFT | ALIGN_VCENTER, line, tuple(style.color(Col.TEXT)))
    finally:
        p.pop_clip()
    return (x, y, w, h)
