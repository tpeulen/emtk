"""What a GPU host uploads: two atlases, and the trick that keeps them one draw.

:class:`~.quad_painter.QuadPainter` builds vertices; a host turns them into
pixels. Between the two sit three pieces of knowledge that are the *same*
whichever graphics API the host speaks, and that is why they are here rather
than in any one host:

* :func:`atlas_pixels` -- the glyph atlas as **one** array, the baked rows
  and the runtime cache together. Uploading only the baked half is a bug
  that has already shipped once; see the function.
* :class:`ImageAtlas` -- where a host's images live, packed and
  premultiplied. This is what a host installs as
  ``QuadPainter.image_uv_resolver``.
* :func:`image_u` -- the negative-u convention that lets an image quad and a
  glyph quad ride in the same vertex buffer and the same pipeline, so the
  whole interface stays **one draw call**.

Nothing here knows what a device is. That is deliberate: these can all be
tested with no window, no adapter and no toolkit, which is most of what
makes the GPU path testable at all -- see ``tests/test_gpu_atlas.py``, which
runs anywhere. :mod:`.wgpu_host` is the host built on them, and it is the
only one: a second host would mean a second shading language and a second
copy of a packing rule, and the way that fails is not a crash but a panel
that looks slightly wrong somewhere, months later.

NumPy is imported on **use**, never at module scope, so importing this in a
headless process is as cheap and as harmless as importing :mod:`.qt_host`
there.
"""
from __future__ import annotations

__all__ = [
    "ImageAtlas",
    "atlas_pixels",
    "image_u",
    "image_texel",
    "png_decode",
    "BAKED_FONT_PT",
    "IMAGE_ATLAS_SIZE",
    "DIRTY_LOG",
    "FLOATS_PER_VERTEX",
    "VERTEX_BYTES",
    "ATTRIBUTES",
]

#: Point size the atlas was baked at, used to turn a caller's ``font_pt``
#: into the ``font_scale`` :class:`~.quad_painter.QuadPainter` takes. Read
#: from the atlas rather than assumed; this is only the fallback for an
#: atlas old enough not to record it.
BAKED_FONT_PT = 8.0

#: Side of the image atlas, in texels. 1024x1024 RGBA is 4 MB and holds a
#: camera frame with room beside it. It is not grown: an image that does not
#: fit is *declined*, and the painter's own fallback draws a tinted
#: rectangle -- a visible wrong thing rather than a silent allocation storm.
IMAGE_ATLAS_SIZE = 1024

#: How many writes :meth:`ImageAtlas.dirty_since` remembers. Long enough
#: that a consumer redrawing every frame never falls off it, short enough
#: that a consumer which stopped asking does not grow a list forever. Past
#: the end the answer is "everything", which is slow and correct rather
#: than fast and wrong.
DIRTY_LOG = 64

#: Floats per vertex. :data:`emtk.quad_painter.FLOATS_PER_VERTEX`, repeated
#: here so a host can declare its vertex layout without importing the
#: painter -- and asserted equal to it, because a mismatch is a *stride*
#: error, which draws a plausible-looking panel out of the wrong bytes
#: rather than failing.
FLOATS_PER_VERTEX = 12

#: Bytes per vertex.
VERTEX_BYTES = FLOATS_PER_VERTEX * 4

#: ``(shader location, float count, byte offset)`` for each attribute:
#: position, uv, colour, clip box. The layout is
#: :class:`~.quad_painter.QuadPainter`'s and is not negotiable -- see its
#: module docstring.
ATTRIBUTES = (
    (0, 2, 0),      # position
    (1, 2, 8),      # uv
    (2, 4, 16),     # colour
    (3, 4, 32),     # clip box
)


# --------------------------------------------------------------------------- #
# The negative-u convention
# --------------------------------------------------------------------------- #
def image_u(texel_x: float, width: int) -> float:
    """Encode a column of the image atlas as a **negative** u.

    Parameters
    ----------
    texel_x : float
        Column in the image atlas.
    width : int
        Width of the image atlas, in texels.

    Returns
    -------
    float
        A value in ``[-2, -1]``. Every glyph and rectangle u is a texel
        coordinate ``>= 0``, so the sign alone says which texture a quad
        samples -- one vertex format, one pipeline, one draw call. The
        decoder is the ``in.uv.x < -0.5`` branch in ``wgsl/ui.wgsl``.

    Notes
    -----
    The encoding is **affine** in *texel_x*, which is not an accident:
    :meth:`~.quad_painter.QuadPainter.image` interpolates between the two
    corners a resolver returns when a caller windows into an image with
    ``uv0``/``uv1``. An encoding that was not affine would decode that
    interpolation to the wrong column.

    Examples
    --------
    >>> from emtk.gpu_atlas import image_u, image_texel
    >>> image_u(0.0, 1024)
    -1.0
    >>> image_texel(image_u(512.0, 1024), 1024)
    512.0
    """
    return -(1.0 + texel_x / float(width))


def image_texel(u: float, width: int) -> float:
    """Decode an :func:`image_u`, the way the fragment shader does."""
    return (-u - 1.0) * float(width)


# --------------------------------------------------------------------------- #
# Lazy imports
# --------------------------------------------------------------------------- #
def _numpy():
    """NumPy, imported on use.

    The vertex array is NumPy's, so no host can work without it -- but
    importing this module must not be what drags it into a process that
    only wanted to know the class exists.
    """
    import numpy  # noqa: PLC0415

    return numpy


def png_decode(data: bytes):
    """``(width, height, rgba bytes)`` from PNG *data*, fast where it can be.

    Parameters
    ----------
    data : bytes

    Returns
    -------
    tuple

    Notes
    -----
    Three decoders, and the choice is not about correctness -- they agree --
    but about **2 seconds**. The pure-Python one in :mod:`.testing` unfilters
    the 640x2795 atlas a byte at a time, which is seven million interpreter
    iterations and a visible pause at start-up (half a minute in WebAssembly).

    Pillow is tried first: a browser page has it (Pyodide ships it), and a
    desktop process on this GPU path is one that chose *not* to have a
    toolkit -- decoding through Qt imported all of PyQt into it just to read
    one picture. Qt, through :mod:`.qt_painter` (which imports it inside its
    functions), is the fallback where there is no Pillow, and the slow decoder
    the last resort. This module names no toolkit and works without one.
    """
    try:
        return _pil_decode(data)
    except ImportError:
        pass
    from .qt_painter import png_decode as qt_decode  # noqa: PLC0415

    try:
        return qt_decode(data)
    except ImportError:
        from .testing import png_decode as slow_decode  # noqa: PLC0415

        return slow_decode(data)


def _pil_decode(data: bytes):
    """``(width, height, rgba bytes)`` through Pillow; ``ImportError`` without it."""
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    with Image.open(io.BytesIO(data)) as image:
        rgba = image.convert("RGBA")
        return rgba.width, rgba.height, rgba.tobytes()


# --------------------------------------------------------------------------- #
# The glyph atlas, both halves of it
# --------------------------------------------------------------------------- #
#: ``id(atlas) -> (cache version, array)``. The baked half is 640x2795 RGBA
#: and decoding it is not free, so the combined buffer is built once per
#: atlas and rebuilt only when the runtime cache has grown.
_ATLAS_PIXELS: dict = {}


def atlas_pixels(atlas):
    """The **combined** glyph atlas as an ``(h, w, 4)`` uint8 array.

    Parameters
    ----------
    atlas : emtk.font.Atlas

    Returns
    -------
    numpy.ndarray
        The rows baked at build time on top, the runtime glyph cache
        underneath, ``Atlas.texture_height`` rows in all.

    Notes
    -----
    Uploading only the baked PNG is the trap this function exists to close,
    and it has already been sprung once: ``Atlas.cell_of`` returns
    coordinates in the *combined* space, so a host holding only the baked
    half samples past the end of its texture for any character the baker
    never saw. Out of bounds it is a hard failure; in bounds it is silently
    the **wrong glyph**, which is the version that ships.

    The result is cached against ``cache.version``, which the cache bumps
    for every glyph it stores -- so a character rasterised since the last
    call is present, and the assembly is paid once per new character rather
    than once per frame.
    """
    np = _numpy()
    cache = atlas.cache
    version = cache.version if cache is not None else -1
    key = id(atlas)
    got = _ATLAS_PIXELS.get(key)
    if got is not None and got[0] == version:
        return got[1]

    width = int(atlas.size[0])
    buffer = np.zeros((int(atlas.texture_height), width, 4), dtype=np.uint8)
    baked_w, baked_h, baked = png_decode(atlas.image_path.read_bytes())
    flat = np.frombuffer(bytes(baked), dtype=np.uint8).reshape(baked_h, baked_w, 4)
    rows = min(baked_h, buffer.shape[0])
    columns = min(baked_w, width)
    buffer[:rows, :columns] = flat[:rows, :columns]
    if cache is not None:
        image = cache.image
        top = int(atlas.baked_height)
        buffer[top:top + image.shape[0], :image.shape[1]] = image
    _ATLAS_PIXELS[key] = (version, buffer)
    return buffer


# --------------------------------------------------------------------------- #
# The image atlas
# --------------------------------------------------------------------------- #
class ImageAtlas:
    """Where a host's images live: one texture, shelf-packed, premultiplied.

    Parameters
    ----------
    width, height : int
        Size in texels.

    Attributes
    ----------
    pixels : numpy.ndarray
        ``(height, width, 4)`` uint8, **premultiplied** -- the shader
        multiplies by the tint and composites with ``ONE,
        ONE_MINUS_SRC_ALPHA``, so anything else darkens every soft edge.
    version : int
        Bumped whenever a texel changes, so an uploader re-uploads only
        when it has to. A live camera frame changes every frame and a
        colour map almost never; both go through here.

    Notes
    -----
    This is what a host installs as
    ``QuadPainter.image_uv_resolver``::

        painter.image_uv_resolver = images.region

    emtk never looks inside an image handle -- where an image lives is the
    host's own knowledge -- and this class is that knowledge, kept out of
    the widget so it can be tested with no window and no device at all.

    Packing is by **shelf**: a row is opened at the height of the first
    image placed in it and later images fill along it. It never
    defragments and never grows. An image that does not fit is declined,
    and the painter's own fallback draws it as a tinted rectangle -- see
    :meth:`~.quad_painter.QuadPainter.image`.

    Examples
    --------
    >>> from emtk import Texture
    >>> from emtk.gpu_atlas import ImageAtlas, image_texel
    >>> atlas = ImageAtlas(64, 64)
    >>> frame = Texture(8, 4)
    >>> frame.fill((255, 0, 0, 255))
    >>> (u0, v0), (u1, v1) = atlas.region(frame)
    >>> u0 < -0.5 and u1 < -0.5          # the sign says "image, not glyph"
    True
    >>> round(image_texel(u0, 64), 1), round(image_texel(u1, 64), 1)
    (0.5, 7.5)
    >>> atlas.region(frame) == ((u0, v0), (u1, v1))   # placed once
    True
    """

    def __init__(self, width: int = IMAGE_ATLAS_SIZE,
                 height: int = IMAGE_ATLAS_SIZE) -> None:
        np = _numpy()
        self.width, self.height = int(width), int(height)
        self.pixels = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.version = 0
        #: ``id(handle) -> (revision, x, y, w, h)``. Keyed on identity
        #: because a ``Texture`` is mutable and unhashable by value, and
        #: the caller owns its lifetime.
        self._placed: dict = {}
        self._shelf_x = 0
        self._shelf_y = 0
        self._shelf_h = 0
        #: ``(version, x, y, w, h)`` per write, newest last, capped at
        #: :data:`DIRTY_LOG` entries. A consumer further behind than the log
        #: goes is told "everything" rather than being told wrong; see
        #: :meth:`dirty_since`.
        self._log: list = []

    # -- the resolver ---------------------------------------------------- #
    def region(self, handle):
        """``((u0, v0), (u1, v1))`` for *handle*, or ``None`` to decline.

        Parameters
        ----------
        handle : object
            Anything with ``width``, ``height``, ``px`` and ``revision`` --
            a :class:`~.texture.Texture`. Anything else is declined rather
            than guessed at.

        Returns
        -------
        tuple or None
            u is :func:`image_u`-encoded; v is a texel row. Both corners
            are inset by half a texel, so a linear sample at the edge of
            one image cannot reach into the one packed beside it. A texture
            whose ``filter`` is ``"nearest"`` is not inset and its v is
            ``-(1 + row)``: the fragment stage samples it texel by texel.
        """
        width = getattr(handle, "width", None)
        height = getattr(handle, "height", None)
        pixels = getattr(handle, "px", None)
        if width is None or height is None or pixels is None:
            return None

        revision = int(getattr(handle, "revision", 0))
        placed = self._placed.get(id(handle))
        if placed is None:
            spot = self._place(int(width), int(height))
            if spot is None:
                return None
            placed = (revision - 1, *spot)
        if placed[0] != revision:
            self._write(placed[1], placed[2], handle)
            placed = (revision, *placed[1:])
        self._placed[id(handle)] = placed

        _rev, x, y, w, h = placed
        if getattr(handle, "filter", "linear") == "nearest":
            # Sampled texel by texel: the corners are the image's own edges
            # (no inset, so no texel is shaved off), and v is negated --
            # ``-(1 + row)`` -- which is how the fragment stage knows to take
            # the nearest texel instead of blending four.
            return (
                (image_u(x, self.width), -(1.0 + y)),
                (image_u(x + w, self.width), -(1.0 + y + h)),
            )
        return (
            (image_u(x + 0.5, self.width), y + 0.5),
            (image_u(x + w - 0.5, self.width), y + h - 0.5),
        )

    def forget(self, handle) -> None:
        """Drop *handle*'s placement. Its texels stay until overwritten."""
        self._placed.pop(id(handle), None)

    def dirty_since(self, version: int):
        """``(rectangles, version)`` -- what has changed since *version*.

        Parameters
        ----------
        version : int
            The :attr:`version` a caller last uploaded.

        Returns
        -------
        tuple
            ``(rects, version)``, where *rects* is a list of
            ``(x, y, w, h)`` to re-upload and *version* is what to pass back
            next time. *rects* is **None** when the answer is "everything":
            the caller is further behind than the log goes.

        Notes
        -----
        A version and a rectangle log, not a dirty flag, because there is
        more than one consumer -- a window and an offscreen grab each hold
        their own texture, and a flag that the first one clears leaves the
        second drawing stale texels. That has happened: the window drew
        Japanese and the grab drew blanks.

        Why it matters at all: a live camera frame changes every frame. A
        1024x1024 atlas re-uploaded whole is 4 MB per frame to move a
        512x512 picture, and putting 4 MB back into the frame's critical
        path is most of the cost that drawing quads removed.

        Examples
        --------
        >>> from emtk import Texture
        >>> atlas = ImageAtlas(64, 64)
        >>> seen = atlas.version
        >>> frame = Texture(8, 4)
        >>> _ = atlas.region(frame)
        >>> rects, seen = atlas.dirty_since(seen)
        >>> rects
        [(0, 0, 8, 4)]
        >>> atlas.dirty_since(seen)[0]           # nothing since
        []
        """
        version = int(version)
        if not self._log or version < self._log[0][0] - 1:
            return None, self.version
        return (
            [tuple(rect) for stamp, *rect in self._log if stamp > version],
            self.version,
        )

    # -- internals ------------------------------------------------------- #
    def _place(self, width: int, height: int):
        """Reserve ``(x, y, width, height)``, or ``None`` if it will not fit."""
        if width <= 0 or height <= 0 or width > self.width:
            return None
        if self._shelf_x + width > self.width:
            self._shelf_y += self._shelf_h
            self._shelf_x = 0
            self._shelf_h = 0
        if self._shelf_y + height > self.height:
            return None
        spot = (self._shelf_x, self._shelf_y, width, height)
        self._shelf_x += width
        self._shelf_h = max(self._shelf_h, height)
        return spot

    def _write(self, x: int, y: int, handle) -> None:
        """Copy *handle*'s pixels in, premultiplying as they go."""
        np = _numpy()
        w, h = int(handle.width), int(handle.height)
        rgba = np.frombuffer(bytes(handle.px), dtype=np.uint8).reshape(h, w, 4)
        alpha = rgba[:, :, 3:4].astype(np.uint16)
        out = self.pixels[y:y + h, x:x + w]
        out[:, :, :3] = (rgba[:, :, :3].astype(np.uint16) * alpha // 255).astype(
            np.uint8
        )
        out[:, :, 3] = rgba[:, :, 3]
        self.version += 1
        self._log.append((self.version, int(x), int(y), w, h))
        del self._log[:-DIRTY_LOG]
