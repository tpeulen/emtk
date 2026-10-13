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

import logging

_log = logging.getLogger(__name__)

__all__ = [
    "ImageAtlas",
    "atlas_pixels",
    "image_u",
    "image_texel",
    "png_decode",
    "BAKED_FONT_PT",
    "MAX_IMAGE_ATLAS_SIZE",
    "MAX_IMAGE_SIDE",
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

#: Side the image atlas starts at, in texels. 1024x1024 RGBA is 4 MB and
#: holds a camera frame with room beside it.
IMAGE_ATLAS_SIZE = 1024

#: Side the image atlas may grow to (doubling from :data:`IMAGE_ATLAS_SIZE`
#: when the live images no longer fit). 4096x4096 RGBA is 64 MB -- paid only
#: by a host that shows that many pictures at once, such as a documentation
#: page of screenshots beside an interface full of icons and glyphs.
MAX_IMAGE_ATLAS_SIZE = 4096

#: Longest side, in texels, one image is stored at. A larger picture (a
#: 3000 px screenshot) is stored scaled down to it -- it is never drawn
#: larger than a window, and a full-size copy would take a quarter of the
#: largest atlas. The same rule shrinks an image further when even the grown
#: atlas has no room: a picture drawn softer is a picture, where the old rule
#: (decline it) drew a blank white rectangle in its place.
MAX_IMAGE_SIDE = 2048

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
def _ref(handle):
    """A weak reference to *handle*, or a strong stand-in for one that takes none.

    Either way, calling it gives the handle back while it lives; a weak one
    gives ``None`` after, which is how the atlas learns a spot is free.
    """
    import weakref  # noqa: PLC0415

    try:
        return weakref.ref(handle)
    except TypeError:
        return lambda: handle


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
def _fit(width: int, height: int, side: int) -> tuple[int, int]:
    """*width* x *height* scaled down (aspect kept) so neither side exceeds *side*."""
    longest = max(width, height)
    if longest <= side:
        return int(width), int(height)
    k = side / longest
    return max(1, round(width * k)), max(1, round(height * k))


def _resample(pixels, width: int, height: int, nearest: bool = False):
    """*pixels* (premultiplied RGBA, ``(h, w, 4)``) resized to *width* x *height*.

    Area-averaged (Pillow's ``BOX``) when shrinking, so a screenshot stored
    at half size keeps its thin lines and its text legible; premultiplied
    input, so a soft edge is not darkened by averaging in transparent black.
    """
    from PIL import Image  # noqa: PLC0415

    image = Image.fromarray(pixels, "RGBA")
    method = Image.Resampling.NEAREST if nearest else Image.Resampling.BOX
    _np = _numpy()
    return _np.asarray(image.resize((int(width), int(height)), method), dtype=_np.uint8)


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
    image placed in it and later images fill along it. The space of an
    image that has died (or been :meth:`forget`-ten) is reused by the next
    one that fits, and when the shelves run out the live images are packed
    again. Then the atlas **grows** (each side doubled, up to *max_size*),
    and last the newcomer is stored at a reduced size (halved until it
    fits). A real image is therefore never declined: declining drew it as
    a tinted -- for a white tint, blank white -- rectangle, which is what a
    documentation page of screenshots wider than 1024 px showed. Only a
    handle that is not an image at all is declined.

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
                 height: int = IMAGE_ATLAS_SIZE, *,
                 max_size: int | None = None,
                 max_side: int = MAX_IMAGE_SIDE) -> None:
        np = _numpy()
        self.width, self.height = int(width), int(height)
        #: Largest side the atlas grows to. A host lowers it to its device's
        #: texture limit; the default never grows a small (test) atlas past
        #: the larger of its own size and :data:`MAX_IMAGE_ATLAS_SIZE`.
        self.max_size = int(max_size) if max_size is not None else max(
            MAX_IMAGE_ATLAS_SIZE, self.width, self.height)
        #: Longest side one image is stored at (see :data:`MAX_IMAGE_SIDE`).
        self.max_side = int(max_side)
        self.pixels = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.version = 0
        #: ``id(handle) -> (ref, revision, x, y, w, h)``. Keyed on identity
        #: because a ``Texture`` is mutable and unhashable by value, and
        #: the caller owns its lifetime. *ref* is a weak reference to the
        #: handle (a strong one for a handle that takes none): an id is
        #: only unique among **live** objects, and a new texture allocated
        #: where a dead one was gets its id -- and, both at revision 0, its
        #: stale pixels and its size. ndXplorer makes a new texture per
        #: redraw of its map and drew an old map, or a blank one, that way.
        self._placed: dict = {}
        #: Spots whose image died: reused before the shelf grows.
        self._free: list = []
        self._shelf_x = 0
        self._shelf_y = 0
        self._shelf_h = 0
        #: ``[y, h, x]`` of every shelf closed so far: its top, its height and where
        #: its free tail starts. A shelf is closed when an image does not fit the rest
        #: of its width, but a narrower one still does -- after a repack by height the
        #: tail of a row of wide figures is the only room left for a glyph.
        self._rows: list = []
        #: Whether the live images are packed as tightly as a repack packs them: true
        #: right after one, false after any placement or release. A full atlas is only
        #: repacked when this is false, so a newcomer that cannot fit even after the
        #: repack does not repack again on every halving of its size.
        self._compact = True
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
        key = id(handle)
        placed = self._placed.get(key)
        if placed is not None and placed[0]() is not handle:
            # The id of a handle that has died, now worn by a new one.
            self._release(key)
            placed = None
        if placed is None:
            spot = self._place(int(width), int(height))
            if spot is None:
                return None
            placed = (_ref(handle), revision - 1, *spot)
            if (spot[2], spot[3]) != (int(width), int(height)):
                _log.debug("image %dx%d stored at %dx%d (atlas %dx%d)", width, height,
                           spot[2], spot[3], self.width, self.height)
        if placed[1] != revision:
            self._write(placed[2], placed[3], handle, placed[4], placed[5])
            placed = (placed[0], revision, *placed[2:])
        self._placed[key] = placed

        _ref_, _rev, x, y, w, h = placed
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
        """Drop *handle*'s placement. Its texels stay until overwritten;
        its spot is free for the next image that fits."""
        placed = self._placed.get(id(handle))
        if placed is not None and placed[0]() is handle:
            self._release(id(handle))

    def _release(self, key) -> None:
        """Give the spot of placement *key* back."""
        placed = self._placed.pop(key, None)
        if placed is not None:
            self._free.append(tuple(placed[2:]))
            self._compact = False

    def _reap(self) -> None:
        """Release the spots of every image that has died since the last call."""
        for key in [k for k, p in self._placed.items() if p[0]() is None]:
            self._release(key)

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
        """Reserve ``(x, y, w, h)`` for a *width* x *height* image; ``None`` only for no size.

        ``(w, h)`` is the size the image is **stored** at: its own, or less
        when it is longer than :attr:`max_side` or when nothing else made
        room. In order: the spot of a dead image it fits in (the smallest
        such), then the shelf, then -- the atlas being full -- a repack of
        the images still alive (:meth:`_repack`), then a larger atlas
        (:meth:`_grow`), then the same again at half the size.

        Reuse comes first because the common churn is one picture replaced
        by another of the same size -- a map redrawn with a new colour
        scale, a camera frame in a new texture -- and without it every one
        of those took fresh space until the atlas was full and every image
        after that drew as a flat tinted box.
        """
        if width <= 0 or height <= 0:
            return None
        self._reap()
        w, h = _fit(width, height, min(self.max_side, self.max_size))
        while True:
            spot = self._fit_once(w, h)
            if spot is not None:
                return spot
            if w <= 1 and h <= 1:
                return None
            w, h = max(1, w // 2), max(1, h // 2)

    def _fit_once(self, width: int, height: int):
        """Room for exactly *width* x *height*, making it if the atlas can; else ``None``."""
        spot = None
        if width <= self.width and height <= self.height:
            spot = self._reuse(width, height)
            if spot is None:
                spot = self._shelf(width, height)
            if spot is None and self._repack():
                spot = self._shelf(width, height)
            if spot is None and not self._compact and (
                self._live_area() + width * height <= self.width * self.height
            ):
                # No dead image to win back, but the shelves are fragmented: each opened
                # at the height of its first image, so a tall figure followed by glyphs
                # wastes most of its row. Packing by height wins that back. Without it
                # a 4096 x 4096 atlas only 60 % full declined a 1 x 1 glyph.
                self._repack(force=True)
                spot = self._shelf(width, height)
        if spot is not None:
            self._compact = False
        while spot is None and self._grow():
            spot = self._shelf(width, height) if (
                width <= self.width and height <= self.height) else None
        return spot

    def _grow(self) -> bool:
        """Double each side (up to :attr:`max_size`), keeping every texel; whether it grew.

        The live images are packed again across the new width; their *u*
        changes, which the painter picks up because it resolves every image
        again when the frame is submitted. A host
        sees a new :attr:`width`/:attr:`height` and makes a new texture, and
        :meth:`dirty_since` answers "everything".
        """
        if self.width >= self.max_size and self.height >= self.max_size:
            return False
        np = _numpy()
        width = min(self.max_size, self.width * 2)
        height = min(self.max_size, self.height * 2)
        self.pixels = np.zeros((height, width, 4), dtype=np.uint8)
        self.width, self.height = width, height
        self.version += 1
        self._log.clear()  # a consumer of the old size uploads everything
        # The live images packed again across the new width: left where they
        # were, the old shelves' right halves would stay empty for good.
        self._repack(force=True)
        self._log.clear()
        _log.info("image atlas grew to %dx%d", width, height)
        return True

    def _reuse(self, width: int, height: int):
        """The smallest free spot *width* x *height* fits in, taken; or ``None``."""
        best = None
        for i, (_x, _y, w, h) in enumerate(self._free):
            if w >= width and h >= height and (best is None or
                                               w * h < self._free[best][2] * self._free[best][3]):
                best = i
        if best is None:
            return None
        x, y, _w, _h = self._free.pop(best)
        return (x, y, width, height)

    def _shelf(self, width: int, height: int):
        """Space at the end of the shelves; ``None`` -- and nothing moved -- if none.

        The tail of a closed shelf comes first (the lowest one tall enough), then the
        open shelf, then a new one below it.
        """
        best = None
        for row in self._rows:
            if row[1] >= height and row[2] + width <= self.width and (
                    best is None or row[1] < best[1]):
                best = row
        if best is not None:
            x = best[2]
            best[2] = x + width
            return (x, best[0], width, height)
        x, y, h = self._shelf_x, self._shelf_y, self._shelf_h
        closed = None
        if x + width > self.width:
            closed = [y, h, x]
            x, y, h = 0, y + h, 0
        if y + height > self.height:
            return None
        if closed is not None and closed[1] > 0 and closed[2] < self.width:
            self._rows.append(closed)
        self._shelf_x, self._shelf_y, self._shelf_h = x + width, y, max(h, height)
        return (x, y, width, height)

    def _repack(self, force: bool = False) -> bool:
        """Pack the live images again from the top left; whether anything was freed.

        Only when the shelf is full and there is dead space to win back.
        The live images move -- each is rewritten at its new spot and so
        reported dirty. QuadPainter holds current-frame handles and refreshes
        their UVs at vertex submission, so earlier quads use their new region
        in this frame rather than briefly sampling unrelated pixels.
        """
        if not self._free and not force:
            return False
        live = sorted(self._placed.items(), key=lambda kv: -kv[1][5])
        self._placed.clear()
        self._free.clear()
        self._shelf_x = self._shelf_y = self._shelf_h = 0
        self._rows = []
        for key, (ref, _rev, _x, _y, w, h) in live:
            handle = ref()
            spot = self._shelf(w, h)
            if handle is None or spot is None:
                continue
            self._write(spot[0], spot[1], handle, w, h)
            self._placed[key] = (ref, int(getattr(handle, "revision", 0)), *spot)
        self._compact = True
        return True

    def _live_area(self) -> int:
        """Texels the live images occupy."""
        return sum(p[4] * p[5] for p in self._placed.values() if p[0]() is not None)

    def _write(self, x: int, y: int, handle, w: int | None = None,
               h: int | None = None) -> None:
        """Copy *handle*'s pixels in at ``w`` x ``h`` (its own size by default), premultiplied."""
        np = _numpy()
        width, height = int(handle.width), int(handle.height)
        w = width if w is None else int(w)
        h = height if h is None else int(h)
        rgba = np.frombuffer(bytes(handle.px), dtype=np.uint8).reshape(height, width, 4)
        alpha = rgba[:, :, 3:4].astype(np.uint16)
        premultiplied = np.empty_like(rgba)
        premultiplied[:, :, :3] = (rgba[:, :, :3].astype(np.uint16) * alpha // 255).astype(
            np.uint8)
        premultiplied[:, :, 3] = rgba[:, :, 3]
        if (w, h) != (width, height):
            premultiplied = _resample(premultiplied, w, h,
                                      getattr(handle, "filter", "linear") == "nearest")
        self.pixels[y:y + h, x:x + w] = premultiplied
        self.version += 1
        self._log.append((self.version, int(x), int(y), w, h))
        del self._log[:-DIRTY_LOG]
