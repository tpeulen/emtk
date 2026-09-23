"""``Texture`` -- pixels a painter can draw, with no graphics API in sight.

A program that shows a *picture* -- a camera frame, a CLSM scan, a heatmap --
has pixels and needs them on the screen. In Dear ImGui that means uploading a
GPU texture and handing ``ImGui::Image`` the id, which puts a graphics API in
the application and ends the arrangement that makes emtk work: the same
widget code on a GPU surface, in a browser, and in a test with no window.

So the pixels go in a :class:`Texture` and the *painter* decides what to do
with them -- rasterise them directly, wrap them in a ``QImage``, upload them
to a real texture. The application never learns which:

    >>> from emtk import Texture
    >>> frame = Texture(2, 2)
    >>> frame.fill((10, 20, 30, 255))
    >>> frame.set_pixel(1, 0, (255, 0, 0, 255))
    >>> frame.get_pixel(1, 0)
    (255, 0, 0, 255)

and then ``im.image(frame, (w, h))`` draws it, wherever it is running.

Uploading is not free, and a live frame changes every frame while a colour
map changes almost never. :attr:`revision` counts writes, so a painter that
holds a real texture can re-upload only when it has to -- and a painter with
no state at all can ignore it. Cache on ``(id(texture), texture.revision)``
and check the entry is still *this* texture (a weak reference): an id is
reused as soon as the texture that had it dies.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["Texture"]

_CHANNELS = 4          # RGBA, the one layout every painter here understands


class Texture:
    """An RGBA image, row-major from the top left, 8 bits per channel.

    Parameters
    ----------
    width, height : int
        Size in pixels. Both must be positive: a zero-sized texture has no
        pixels to draw and every consumer would have to special-case it.
    pixels : bytes-like, optional
        Initial contents, ``width * height * 4`` bytes. Omitted, the texture
        starts fully transparent.

    Attributes
    ----------
    revision : int
        Incremented on every write. A painter that uploads caches against it.
    filter : str
        ``"linear"`` (the default: a photograph scaled smoothly) or
        ``"nearest"`` -- every texel a sharp block, which is what a picture of
        *bins* has to look like (a 2-D histogram, a pixel image at high zoom).
        Set at construction or later; painters read it when they draw.
    """

    # ``__weakref__``: a host that keeps an uploaded copy (the GPU image
    # atlas, the Qt painter's QImage cache) holds the texture weakly, to
    # learn when it has died -- its id then belongs to the next object.
    __slots__ = ("width", "height", "px", "revision", "filter", "__weakref__")

    def __init__(self, width: int, height: int, pixels: Sequence[int] | None = None,
                 filter: str = "linear") -> None:
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise ValueError(
                f"a Texture needs a positive size, not {width}x{height}: there "
                f"are no pixels to draw and every painter would have to say so "
                f"separately.")
        self.width, self.height = width, height
        want = width * height * _CHANNELS
        if pixels is None:
            self.px = bytearray(want)
        else:
            self.px = bytearray(pixels)
            if len(self.px) != want:
                raise ValueError(
                    f"{width}x{height} RGBA needs {want} bytes, got "
                    f"{len(self.px)}. A short buffer drawn as-is is a picture "
                    f"of whatever followed it in memory.")
        self.revision = 0
        if filter not in ("linear", "nearest"):
            raise ValueError(f"filter must be 'linear' or 'nearest', not {filter!r}")
        self.filter = filter

    # -- writing ----------------------------------------------------------- #
    def touch(self) -> None:
        """Say the pixels changed.

        Call this after writing through :attr:`px` directly -- which is the
        fast path for a frame built a row at a time, and the one case where
        the texture cannot notice for itself.
        """
        self.revision += 1

    def fill(self, colour) -> None:
        """Set every pixel to *colour* (r, g, b[, a])."""
        r, g, b, a = _rgba(colour)
        self.px[:] = bytes((r, g, b, a)) * (self.width * self.height)
        self.revision += 1

    def set_pixel(self, x: int, y: int, colour) -> None:
        """One pixel. Out of bounds is ignored, as a clipped blit would be."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        i = (y * self.width + x) * _CHANNELS
        self.px[i:i + _CHANNELS] = bytes(_rgba(colour))
        self.revision += 1

    def set_rows(self, y: int, rows: Sequence[int]) -> None:
        """Write whole rows from a flat RGBA buffer, starting at row *y*.

        The bulk path: a frame arriving as one buffer is one slice assignment
        and one revision bump, where per-pixel writes would be a bump each and
        make a caching painter re-upload for every pixel.
        """
        start = y * self.width * _CHANNELS
        end = start + len(rows)
        if end > len(self.px):
            raise ValueError(
                f"{len(rows)} bytes from row {y} runs past the end of a "
                f"{self.width}x{self.height} texture.")
        self.px[start:end] = bytes(rows)
        self.revision += 1

    # -- reading ----------------------------------------------------------- #
    def get_pixel(self, x: int, y: int) -> tuple:
        i = (y * self.width + x) * _CHANNELS
        return tuple(self.px[i:i + _CHANNELS])

    @property
    def size(self) -> tuple:
        return (self.width, self.height)

    def __repr__(self) -> str:
        return f"Texture({self.width}x{self.height}, revision={self.revision})"


def _rgba(colour) -> tuple:
    vals = list(colour)
    if len(vals) == 3:
        vals.append(255)
    return tuple(int(v) & 0xFF for v in vals[:4])
