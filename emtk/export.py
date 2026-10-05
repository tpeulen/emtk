"""Save what an emtk app draws as a PNG, without a window or a GPU.

An app that wants a *Save picture* button (a plot's window, a result panel for a report) has
had no supported way to do it: the only renderer outside the hosts lived in
:mod:`emtk.testing`, named for tests. This module is the stable spelling:

.. code-block:: python

    from emtk.export import save_png

    save_png(app, "result.png", size=(1200, 800))

It draws on the CPU rasteriser (:class:`emtk.testing.PixelPainter`), so it works headless and
gives the same picture on every machine; it is the *whole app window* at the given size, not one
plot. An :class:`~emtk.app.ImApp` is drawn through its own ``draw`` (so hubs and docked windows
lay out as they do on screen); a bare ``gui()`` callable is drawn through ``im.frame``.
"""
from __future__ import annotations

import pathlib
from typing import Any, Callable, Tuple, Union

__all__ = ["grab", "png_bytes", "save_png"]

Size = Tuple[int, int]


def grab(app: Union[Any, Callable[[], Any]], size: Size = (1200, 800), frames: int = 3,
         painter: str = "pixel"):
    """Draw *app* and return the painter holding the pixels.

    Parameters
    ----------
    app : ImApp or callable
        An object with ``draw(painter, x, y, w, h)`` (an :class:`~emtk.app.ImApp`), or a
        ``gui()`` function that calls :mod:`emtk.im`.
    size : (int, int)
        Width and height in pixels.
    frames : int
        How many frames to run. The first opens windows and settles layout, the last is the
        picture; two is the least that is right, three also settles a docked layout.
    painter : {"pixel", "pil"}
        ``"pixel"`` (default) draws on :class:`emtk.testing.PixelPainter`, pure Python and
        the reference every golden image is taken with. ``"pil"`` draws the same picture on
        :class:`emtk.pil_painter.PilPainter`, whose inner loops are Pillow's -- many times
        faster for a large or busy frame (a figure for a report), and it needs Pillow.

    Returns
    -------
    PixelPainter or PilPainter
        ``.width``, ``.height`` and ``.px`` (RGBA bytes).
    """
    if painter == "pixel":
        from .testing import PixelPainter as make
    elif painter == "pil":
        from .pil_painter import PilPainter as make
    else:
        raise ValueError(f"painter is 'pixel' or 'pil', got {painter!r}")

    width, height = int(size[0]), int(size[1])
    if width < 1 or height < 1:
        raise ValueError(f"size must be positive, got {size!r}")
    canvas = None
    for _ in range(max(2, int(frames))):
        canvas = make(width, height)
        if hasattr(app, "draw"):
            app.draw(canvas, 0.0, 0.0, float(width), float(height))
        else:
            from . import im

            with im.frame(canvas, (0.0, 0.0, float(width), float(height))):
                app()
    return canvas


def png_bytes(app: Union[Any, Callable[[], Any]], size: Size = (1200, 800), frames: int = 3,
              painter: str = "pixel") -> bytes:
    """Draw *app* and return the picture encoded as PNG bytes (see :func:`grab`)."""
    from .testing import png_encode

    canvas = grab(app, size, frames, painter)
    return png_encode(canvas.width, canvas.height, canvas.px)


def save_png(app: Union[Any, Callable[[], Any]], path: Union[str, pathlib.Path],
             size: Size = (1200, 800), frames: int = 3, painter: str = "pixel") -> pathlib.Path:
    """Draw *app* and write it to *path* as a PNG; returns the path (see :func:`grab`).

    The parent folder must exist; an existing file is replaced.
    """
    target = pathlib.Path(path)
    data = png_bytes(app, size, frames, painter)
    target.write_bytes(data)
    return target
