"""What lies behind a modal window: washed with ``MODAL_DIM_BG`` and, by default, blurred.

One function every modal surface calls before it draws itself -- a question
(:class:`~emtk.message_dialog.MessageDialog`), a modal menu, a guided tour's card -- so the
look is decided once. The blur is a painter capability (``Painter.backdrop``): the GPU
painter splits its frame and blurs the part drawn so far
(:meth:`~emtk.wgpu_host.WgpuRenderer.render`), the pixel painter blurs its buffer; a
painter without it washes only, as before.
"""

from __future__ import annotations

from . import style

__all__ = ["draw_modal_backdrop", "modal_blur", "set_modal_blur"]


def modal_blur() -> bool:
    """Whether a modal window blurs what is behind it (:data:`emtk.style.MODAL_BLUR`)."""
    return bool(style.MODAL_BLUR)


def set_modal_blur(enabled: bool, radius: float | None = None) -> None:
    """Switch the blur behind modal windows on or off (and set its reach, logical pixels)."""
    style.MODAL_BLUR = bool(enabled)
    if radius is not None:
        style.MODAL_BLUR_RADIUS = max(0.0, float(radius))


def draw_modal_backdrop(painter, x: float, y: float, w: float, h: float) -> None:
    """Wash, and blur when on, everything *painter* has drawn under ``x, y, w, h``.

    Call it right before the modal window draws, over the viewport the modal blocks:
    what was drawn before is behind it, what comes after (the window, its popups, a
    tooltip) stays sharp.
    """
    if w <= 0.0 or h <= 0.0:
        return
    tint = style.MODAL_DIM_BG
    radius = float(style.MODAL_BLUR_RADIUS) if style.MODAL_BLUR else 0.0
    operation = getattr(painter, "backdrop", None) if radius > 0.0 else None
    if callable(operation):
        operation(x, y, w, h, tint, radius)
    else:
        painter.fill_rect(x, y, w, h, tint)
