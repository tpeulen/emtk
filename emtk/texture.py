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

import io
import os
import pathlib
from collections.abc import Sequence
from typing import Any

__all__ = ["Texture", "ImageTextureCache", "get_texture"]

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

    # -- conversion & factories -------------------------------------------- #
    @classmethod
    def from_pil(cls, image: Any, filter: str = "linear") -> Texture:
        """Create a Texture from a PIL Image instance."""
        rgba = image.convert("RGBA")
        return cls(rgba.width, rgba.height, rgba.tobytes(), filter=filter)

    @classmethod
    def from_file(cls, path: str | os.PathLike[str], filter: str = "linear") -> Texture:
        """Load an image file from disk and return a Texture."""
        from PIL import Image

        p = pathlib.Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Image file not found: {p}")
        with Image.open(p) as img:
            return cls.from_pil(img, filter=filter)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        width: int | None = None,
        height: int | None = None,
        filter: str = "linear",
    ) -> Texture:
        """Create a Texture from raw bytes or encoded image data (PNG, JPEG, etc.)."""
        if width is not None and height is not None:
            return cls(width, height, data, filter=filter)
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return cls.from_pil(img, filter=filter)

    @classmethod
    def from_numpy(cls, arr: Any, filter: str = "linear") -> Texture:
        """Create a Texture from a 2D or 3D numpy array.

        Supports:
        - 2D (H, W) grayscale
        - 3D (H, W, 1) grayscale
        - 3D (H, W, 3) RGB
        - 3D (H, W, 4) RGBA
        - float arrays (0.0 to 1.0) or integer arrays (0 to 255)
        """
        import numpy as np

        a = np.asarray(arr)
        if a.ndim == 2:
            h, w = a.shape
            if np.issubdtype(a.dtype, np.floating):
                a = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
            else:
                a = np.clip(a, 0, 255).astype(np.uint8)
            rgba = np.zeros((h, w, 4), dtype=np.uint8)
            rgba[:, :, 0] = a
            rgba[:, :, 1] = a
            rgba[:, :, 2] = a
            rgba[:, :, 3] = 255
            return cls(w, h, rgba.tobytes(), filter=filter)

        if a.ndim == 3:
            h, w, c = a.shape
            if np.issubdtype(a.dtype, np.floating):
                a = (np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)
            else:
                a = np.clip(a, 0, 255).astype(np.uint8)

            if c == 1:
                return cls.from_numpy(a[:, :, 0], filter=filter)
            elif c == 3:
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                rgba[:, :, :3] = a
                rgba[:, :, 3] = 255
                return cls(w, h, rgba.tobytes(), filter=filter)
            elif c == 4:
                return cls(w, h, a.tobytes(), filter=filter)
            else:
                raise ValueError(f"Unsupported number of channels in numpy array: {c}")

        raise ValueError(f"Array must be 2D or 3D, got ndim={a.ndim}")

    def to_pil(self) -> Any:
        """Export Texture pixels to a PIL Image (RGBA)."""
        from PIL import Image

        return Image.frombytes("RGBA", (self.width, self.height), bytes(self.px))

    def save(self, path: str | os.PathLike[str], format: str | None = None) -> None:
        """Save Texture pixels to disk as an image file."""
        pil_img = self.to_pil()
        pil_img.save(path, format=format)


class ImageTextureCache:
    """Cache for loaded textures to prevent redundant file I/O and decodes."""

    def __init__(self, maxsize: int = 256) -> None:
        self.maxsize = maxsize
        self._cache: dict[tuple[str, str, int], Texture] = {}
        self._keys: list[tuple[str, str, int]] = []

    def get(self, path: pathlib.Path, filter: str) -> Texture | None:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        key = (str(path.resolve()), filter, mtime_ns)
        tex = self._cache.get(key)
        if tex is not None:
            self._keys.remove(key)
            self._keys.append(key)
        return tex

    def put(self, path: pathlib.Path, filter: str, texture: Texture) -> None:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        key = (str(path.resolve()), filter, mtime_ns)
        if key in self._cache:
            self._keys.remove(key)
        elif len(self._keys) >= self.maxsize:
            oldest = self._keys.pop(0)
            self._cache.pop(oldest, None)
        self._cache[key] = texture
        self._keys.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._keys.clear()


_GLOBAL_IMAGE_CACHE = ImageTextureCache()


def get_texture(
    source: Any,
    filter: str = "linear",
    cache: ImageTextureCache | None = None,
) -> Texture | None:
    """Resolve an image source into a Texture.

    Parameters
    ----------
    source : Texture, str, Path, PIL Image, or numpy array
        The image data or reference.
    filter : str
        ``"linear"`` or ``"nearest"``.
    cache : ImageTextureCache, optional
        Custom cache instance (uses global cache by default for paths).

    Returns
    -------
    Texture or None
        The resolved Texture, or None if resolution failed.
    """
    if isinstance(source, Texture):
        return source

    if cache is None:
        cache = _GLOBAL_IMAGE_CACHE

    if isinstance(source, (str, os.PathLike)):
        p = pathlib.Path(source)
        if not p.is_file():
            return None
        cached = cache.get(p, filter)
        if cached is not None:
            return cached
        try:
            tex = Texture.from_file(p, filter=filter)
            cache.put(p, filter, tex)
            return tex
        except Exception:
            return None

    # PIL Image
    if hasattr(source, "convert") and hasattr(source, "tobytes"):
        try:
            return Texture.from_pil(source, filter=filter)
        except Exception:
            return None

    # Numpy array
    if hasattr(source, "shape") and hasattr(source, "dtype"):
        try:
            return Texture.from_numpy(source, filter=filter)
        except Exception:
            return None

    return None


def _rgba(colour) -> tuple:
    vals = list(colour)
    if len(vals) == 3:
        vals.append(255)
    return tuple(int(v) & 0xFF for v in vals[:4])

