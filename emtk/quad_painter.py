"""Draw the chrome as quads instead of rasterising it on the CPU.

This is the other implementation of :class:`~.painter.Painter`. It draws
nothing: it *appends*, building one interleaved vertex array that
:mod:`emtk.wgsl`'s ``ui.wgsl`` turns into the panel, the strip, the menus
and the transport in a single draw call. :mod:`emtk.wgpu_host` is the host
that does it.

Why that is worth doing is measured, not assumed. ``wgpu_view`` records the
``QPainter`` path at **9.6 ms of a 21 ms frame** with a quarter-million beads on
screen -- so the chrome was mitigated by a *timer* that lets the panel go stale
rather than repaint when it changes, and that mitigation is bypassed entirely
for any scene carrying labels, because labels move with the camera. A frame of
chrome is a few hundred rectangles and a few thousand glyphs; as vertices that
is kilobytes and no rasterisation.

Vertex format
-------------
Six vertices per quad -- two triangles, no index buffer, because the chrome is
rebuilt every frame and an index buffer would be another allocation to keep in
step for no reuse. Those six vertices are **made in NumPy**, from one
:data:`FLOATS_PER_QUAD` record per quad that Python emits; see
:meth:`QuadPainter.vertices` for why, and for the property that makes it safe
(the expansion computes nothing). What the GPU receives is unchanged: each
vertex is 12 floats::

    position  x, y            pixels, y-down from the top left
    uv        u, v            atlas texels
    colour    r, g, b, a      0-1, straight alpha; the shader premultiplies
    box       x0, y0, x1, y1  the clip rectangle in pixels

The clip rectangle rides on the vertex rather than being a scissor, so the
whole chrome stays one draw call.

A rectangle points at the atlas's opaque block, so there is no second pipeline
and no "is this text" branch: the difference between a panel background and a
letter is which texels the quad samples.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .font import Atlas, load_atlas
from .painter import (
    ALIGN_HCENTER,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
)

__all__ = ["QuadPainter", "FLOATS_PER_VERTEX", "VERTICES_PER_QUAD"]

#: Floats per vertex; see the module docstring.
FLOATS_PER_VERTEX = 12

#: Two triangles.
VERTICES_PER_QUAD = 6

#: Corners a quad expands to before :data:`_TRIANGLES` turns them into the
#: six vertices the GPU is given.
CORNERS_PER_QUAD = 4

#: Floats Python emits per quad: ``x0, y0, x1, y1``, ``u0, v0, u1, v1``,
#: ``r, g, b, a`` and the clip box. Every one of them is a *final* value --
#: the scale is already applied -- so :meth:`QuadPainter.vertices` moves them
#: into place and computes nothing, which is what makes the expansion
#: bit-identical to emitting the vertices one at a time.
FLOATS_PER_QUAD = 16

#: Which corner each of the six vertices is: top-left, top-right,
#: bottom-right, then top-left, bottom-right, bottom-left. The winding is the
#: one the pipeline was built for, so this must not be reordered casually.
_TRIANGLES = np.array([0, 1, 2, 0, 2, 3], dtype=np.intp)

#: The clip rectangle used when nothing is clipping. Large enough to pass any
#: on-screen fragment, and finite so the comparison in the shader stays a
#: comparison rather than a NaN.
_NO_CLIP = (-1.0e6, -1.0e6, 1.0e6, 1.0e6)


#: The two vertex streams, as :meth:`QuadPainter._note` names them.
_RECTS = 0
_TRIS = 1


def _rgba(colour: Colour) -> tuple[float, float, float, float]:
    """Return *colour* as floats in ``[0, 1]``, with alpha.

    Parameters
    ----------
    colour : tuple
        ``(r, g, b)`` or ``(r, g, b, a)``, 0-255.

    Returns
    -------
    tuple of float
    """
    if len(colour) == 3:
        r, g, b = colour
        a = 255
    else:
        r, g, b, a = colour
    return r / 255.0, g / 255.0, b / 255.0, a / 255.0



def _interleave(rects: np.ndarray, tris: np.ndarray, runs) -> np.ndarray:
    """One buffer, in the order the primitives were drawn.

    The two streams are kept apart while a frame is built -- a rect is one
    compact record that :meth:`QuadPainter.vertices` expands, a triangle is
    three independent vertices -- and putting all of one before all of the
    other is what made a chord drawn as triangles float above the menu drawn
    over it. The runs say how to zip them back together; there are a handful
    per frame, so this is a few array copies, not one per primitive.

    Parameters
    ----------
    rects : numpy.ndarray
        Expanded rect vertices, six per quad, in order.
    tris : numpy.ndarray
        Triangle vertices, three per triangle, in order.
    runs : sequence
        ``[kind, primitives]`` pairs, as recorded while drawing.

    Returns
    -------
    numpy.ndarray
        The two, interleaved by run.
    """
    if not runs:
        return np.concatenate((rects, tris), axis=0)
    pieces = []
    at = [0, 0]
    per = (CORNERS_PER_QUAD + 2, 3)     # vertices per rect quad, per triangle
    for kind, count in runs:
        source = rects if kind == _RECTS else tris
        start = at[kind]
        stop = start + count * per[kind]
        pieces.append(source[start:stop])
        at[kind] = stop
    # Anything a caller wrote without saying so (a painter subclass, a stream
    # written directly) still reaches the buffer, at the end, where it would
    # have been before.
    if at[_RECTS] < len(rects):
        pieces.append(rects[at[_RECTS]:])
    if at[_TRIS] < len(tris):
        pieces.append(tris[at[_TRIS]:])
    return np.concatenate(pieces, axis=0)


class QuadPainter:
    """Accumulate the chrome as an interleaved vertex array.

    Parameters
    ----------
    atlas : Atlas, optional
        The baked font. Loaded from the package by default.
    scale : float, optional
        Device pixels per logical pixel.
    font_scale : float, optional
        Text size, as a multiple of the baked one. The atlas is a bitmap face,
        so this scales the glyph quads and their advance together -- there is
        no second size to bake. It is the *drawing* half of the chrome scale;
        the layout half is ``InternalGui.FONT_PT``, and the two must be given
        the same number or the boxes and the text they hold disagree.
    """

    def __init__(self, atlas: Atlas | None = None, scale: float = 1.0,
                 font_scale: float = 1.0) -> None:
        self._atlas = atlas if atlas is not None else load_atlas()
        self._font_scale = float(font_scale)
        self._data: list[float] = []
        #: ``(quad index, four RGBA tuples)`` for the handful of quads whose
        #: corners differ. See :meth:`vertices`.
        self._gradients: list[tuple[int, tuple]] = []
        #: Triangle vertices, as ``(n, FLOATS_PER_VERTEX)`` float32 blocks --
        #: unlike a rect quad's four corners derived from ``x, y, w, h``, a
        #: triangle's three corners are independent and have nowhere to sit in
        #: the rect record, so they bypass the :data:`FLOATS_PER_QUAD`
        #: expansion and are concatenated in :meth:`vertices`.
        #:
        #: **Blocks, not a float list.** The bulk fills build their vertices
        #: with numpy and used to hand them over as Python floats
        #: (``block.ravel().tolist()``), which was measured at 2.2 ms of a
        #: 9 ms panel repaint -- more than the drawing. A numpy array stays a
        #: numpy array until the buffer is assembled.
        self._tris: list = []
        #: The order the two streams were written in, as runs of
        #: ``[kind, primitives]`` -- kind 0 rects, kind 1 triangles.
        #:
        #: Without it the buffer is every rect and then every triangle, which
        #: is not what the painter was asked to draw. Batching by primitive
        #: *kind* throws away paint order between kinds: a chord drawn as
        #: triangles floated above the menu that was drawn after it, and above
        #: the window frame it was inside, because the menu and the frame are
        #: rects. Runs are cheap -- a chrome frame has a handful of them, not
        #: one per primitive -- and they put the two streams back in order in
        #: :meth:`vertices`.
        self._runs: list[list[int]] = []
        self._clips: list[tuple[float, float, float, float]] = []
        #: Device pixels per logical pixel.
        #:
        #: The panel lays itself out in **logical** pixels -- that is what a
        #: window's coordinates are, and what a mouse event carries -- while the
        #: surface it lands on is in **device** pixels. Applied here, at the one
        #: point where layout becomes geometry, so hit-testing keeps working in
        #: the coordinates the events arrive in.
        #:
        #: Getting this wrong does not look like a scaling bug. On a 2x display
        #: the panel draws at half size in the corner of the window while
        #: ``hit_test`` still answers for where it *should* be, so every click
        #: misses by the ratio and the panel looks inert rather than misplaced.
        self._scale = float(scale)
        #: The clip rectangle in force, in logical and in device pixels. Plain
        #: attributes rather than a property: the quad loop reads the scaled
        #: one once per quad, and a property is a Python call.
        self._clip: tuple[float, float, float, float] = _NO_CLIP
        self._scaled_clip = self._scale_clip(_NO_CLIP)

        # The atlas metrics, resolved once. Every one of them is fixed for a
        # given atlas and font scale, and `text` was recomputing the lot on
        # each call -- two property evaluations, a method call and four
        # multiplications -- of which there are ~340 a frame carrying under
        # three characters each. The setup, not the glyph loop, was the cost.
        atlas = self._atlas
        sx, sy, sw, sh = atlas.solid
        #: A texel well inside the opaque block, so filtering cannot reach its
        #: edge. Every rectangle in the chrome samples this one point.
        self._solid_uv = (sx + sw * 0.5, sy + sh * 0.5)
        #: The host's image placement, or ``None``: a callable taking the
        #: ``handle`` :meth:`image` received and returning
        #: ``((u0, v0), (u1, v1))`` in whatever texture the host binds, or
        #: ``None`` to decline. emtk never looks inside the handle -- where
        #: an image lives is the host's knowledge (an atlas it owns), which
        #: is why this is a hook rather than a table.
        self.image_uv_resolver = None
        #: Advance width of one character, in logical pixels.
        self._advance = atlas.advance() * self._font_scale
        #: Logical pixels per baked texel, for the glyph quad.
        self._shrink = atlas.render_scale * self._font_scale
        self._glyph_w = atlas.cell[0] * self._shrink
        self._glyph_h = atlas.cell[1] * self._shrink
        self._ascent = atlas.ascent
        self._half_cell_h = atlas.cell[1] * 0.5
        self._pad = atlas.pad

    def set_font_scale(self, scale: float) -> None:
        """Draw and measure text `scale` times the baked size.

        The atlas is a bitmap face, so the glyph *quads* and their advance
        scale together -- text above 1.0 softens the way any scaled bitmap
        does, while text below it stays clean. The resolved metrics are
        recomputed here rather than per call: the quad loop reads them once
        per glyph, and a property in that loop was measurable.
        """
        self._font_scale = float(scale)
        atlas = self._atlas
        self._advance = atlas.advance() * self._font_scale
        self._shrink = atlas.render_scale * self._font_scale
        self._glyph_w = atlas.cell[0] * self._shrink
        self._glyph_h = atlas.cell[1] * self._shrink

    # -- output ------------------------------------------------------------

    @property
    def vertex_count(self) -> int:
        """Number of vertices the emitted quads and triangles expand to."""
        return (
            (len(self._data) // FLOATS_PER_QUAD) * VERTICES_PER_QUAD
            + sum(len(block) for block in self._tris)
        )

    def vertices(self) -> np.ndarray:
        """Return the interleaved array, ready for upload.

        Returns
        -------
        numpy.ndarray
            ``(n, 12)`` float32, C-contiguous -- the guarantee a geometry
            packer makes, for the same reason: a view onto the interpreter's
            heap can only be handed to a GPU if it is already in the layout
            the GPU expects.

        Notes
        -----
        **Python emits one record per quad; the six vertices are made here.**
        Floats are what this costs: each one is a ``PyFloat`` that has to be
        built into a tuple, appended to a list, and then converted one at a
        time. Emitting the six vertices directly was 72 floats a quad --
        150,696 on a chrome frame, 0.94 ms to emit and 2.7 ms to convert -- and
        two thirds of them were redundant. Four of the six vertices are copies
        of the other two; the colour and the clip box are the same at all four
        corners; and a corner's position and uv are one of two values on each
        axis. So :data:`FLOATS_PER_QUAD` carries each distinct number **once**
        and NumPy does the copying, which is a handful of C-level assignments
        over the whole frame rather than 150,000 interpreter operations.

        The expansion computes **nothing**. Every value in the record is final
        -- the device scale is applied where the quad is emitted, in Python
        float64, exactly as it was before -- so this is data movement and the
        output is bit-identical to emitting the vertices one at a time. That is
        asserted, over a whole chrome frame at two device scales, by
        ``test_chrome_frame_cost``.

        ``fromiter`` with an exact ``count``, not ``asarray``: both walk the
        same list of Python floats, but ``asarray`` has to discover the length
        and the type first. Measured at 2.7 ms against 3.2 ms on the old,
        three-times-larger buffer.
        """
        if not self._data:
            if not self._tris:
                return np.zeros((0, FLOATS_PER_VERTEX), dtype=np.float32)
            return np.concatenate(self._tris, axis=0)
        quads = np.fromiter(
            self._data, dtype=np.float32, count=len(self._data)
        ).reshape(-1, FLOATS_PER_QUAD)

        corners = np.empty(
            (len(quads), CORNERS_PER_QUAD, FLOATS_PER_VERTEX), dtype=np.float32
        )
        left, top, right, bottom = quads[:, 0], quads[:, 1], quads[:, 2], quads[:, 3]
        u0, v0, u1, v1 = quads[:, 4], quads[:, 5], quads[:, 6], quads[:, 7]
        # Top-left, top-right, bottom-right, bottom-left -- the order
        # :data:`_TRIANGLES` indexes.
        corners[:, 0, 0] = corners[:, 3, 0] = left
        corners[:, 1, 0] = corners[:, 2, 0] = right
        corners[:, 0, 1] = corners[:, 1, 1] = top
        corners[:, 2, 1] = corners[:, 3, 1] = bottom
        corners[:, 0, 2] = corners[:, 3, 2] = u0
        corners[:, 1, 2] = corners[:, 2, 2] = u1
        corners[:, 0, 3] = corners[:, 1, 3] = v0
        corners[:, 2, 3] = corners[:, 3, 3] = v1
        # Colour and clip are per *quad*, so they broadcast across the corners.
        corners[:, :, 4:8] = quads[:, None, 8:12]
        corners[:, :, 8:12] = quads[:, None, 12:16]

        # The one thing a record cannot hold: a gradient's four corner colours.
        # Patched afterwards rather than widening every record by twelve floats
        # for the ~40 quads a frame that need them -- and patched *in place*, so
        # a gradient keeps its position in the draw order, which is what decides
        # what is drawn over what.
        for index, quad_colours in self._gradients:
            corners[index, :, 4:8] = quad_colours

        rect_vertices = corners[:, _TRIANGLES, :].reshape(-1, FLOATS_PER_VERTEX)
        if not self._tris:
            return rect_vertices
        tri_vertices = np.concatenate(self._tris, axis=0)
        return _interleave(rect_vertices, tri_vertices, self._runs)

    def clear(self) -> None:
        """Drop everything accumulated, keeping the loaded atlas."""
        self._data.clear()
        self._gradients.clear()
        self._tris.clear()
        self._runs.clear()
        del self._clips[:]
        self._clip = _NO_CLIP
        self._scaled_clip = self._scale_clip(_NO_CLIP)

    # -- internals ---------------------------------------------------------

    def _scale_clip(self, box) -> tuple[float, float, float, float]:
        """The clip rectangle in device pixels.

        Computed when the clip *changes* rather than per quad. It was four
        multiplications and a property call inside the hot loop, ~2,100 times a
        frame, to produce the same four numbers each time -- clips change a
        handful of times per frame.
        """
        scale = self._scale
        return (box[0] * scale, box[1] * scale, box[2] * scale, box[3] * scale)

    def _quad(
        self,
        x: float, y: float, w: float, h: float,
        u: float, v: float, uw: float, vh: float,
        corners,
    ) -> None:
        """Append one quad.

        Parameters
        ----------
        x, y, w, h : float
            Destination rectangle, in pixels.
        u, v, uw, vh : float
            Source rectangle, in atlas texels.
        corners : sequence
            Per-corner RGBA, in the order top-left, top-right, bottom-right,
            bottom-left. A single tuple is accepted and used for all four,
            which is every case except the gradient.
        """
        if w <= 0.0 or h <= 0.0:
            return
        if isinstance(corners, tuple) and corners and isinstance(corners[0], float):
            self._corner_quad(x, y, w, h, u, v, uw, vh, corners)
            return

        # The record carries corner 0's colour like any other quad; the four
        # are handed to :meth:`vertices` separately and patched into place
        # there, so a gradient costs twelve extra floats rather than every quad
        # in the frame costing them.
        self._gradients.append((len(self._data) // FLOATS_PER_QUAD, tuple(corners)))
        self._corner_quad(x, y, w, h, u, v, uw, vh, corners[0])

    def _note(self, kind: int, count: int = 1) -> None:
        """Record that *count* primitives of *kind* were written."""
        runs = self._runs
        if runs and runs[-1][0] == kind:
            runs[-1][1] += count
        else:
            runs.append([kind, count])

    def _corner_quad(
        self,
        x: float, y: float, w: float, h: float,
        u: float, v: float, uw: float, vh: float,
        rgba,
    ) -> None:
        """Append one quad, as one :data:`FLOATS_PER_QUAD` record.

        This is the hot path -- every quad the chrome draws reaches it, ~2,100
        a frame -- so it does the minimum: one multiplication per coordinate,
        one tuple, one ``extend``. The clip box arrives already scaled, the
        colour is unpacked once rather than four times, and the corner geometry
        is left to :meth:`vertices`.
        """
        if w <= 0.0 or h <= 0.0:
            return
        scale = self._scale
        cx0, cy0, cx1, cy1 = self._scaled_clip
        r, g, b, a = rgba
        x = x * scale
        y = y * scale
        self._data.extend((
            x, y, x + w * scale, y + h * scale,
            u, v, u + uw, v + vh,
            r, g, b, a,
            cx0, cy0, cx1, cy1,
        ))
        self._note(_RECTS)

    def _solid(self, x: float, y: float, w: float, h: float, corners) -> None:
        """Append a quad that samples the atlas's opaque block.

        The generic entry: it accepts either one colour or four. Callers that
        know which they have -- which is all of them inside this file -- go
        straight to :meth:`_corner_quad` or :meth:`_quad` instead, because at
        ~1,200 solid quads a frame the ``isinstance`` pair and the extra call
        are not free.
        """
        u, v = self._solid_uv
        if isinstance(corners, tuple) and corners and isinstance(corners[0], float):
            self._corner_quad(x, y, w, h, u, v, 0.0, 0.0, corners)
        else:
            self._quad(x, y, w, h, u, v, 0.0, 0.0, corners)

    # -- the interface -----------------------------------------------------

    def fill_rect(self, x: float, y: float, w: float, h: float, colour: Colour) -> None:
        """Fill a rectangle. No outline."""
        u, v = self._solid_uv
        self._corner_quad(x, y, w, h, u, v, 0.0, 0.0, _rgba(colour))

    def image(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        handle,
        uv0=(0.0, 0.0),
        uv1=(1.0, 1.0),
        tint: Colour = (255, 255, 255, 255),
    ) -> None:
        """Blit *handle* into the box (the optional ``Painter.image`` op).

        ``handle`` is host-defined and opaque to emtk. This painter resolves
        it through :attr:`image_uv_resolver` -- a callable the *host*
        installs, returning ``((u0, v0), (u1, v1))`` in the host's own
        texture, or ``None`` to decline. Without a resolver, or when it
        declines, the box degrades to a :meth:`fill_rect` in *tint*: the
        same fallback :func:`emtk.painter.image` gives every painter
        without the operation, so a missing image reads as a coloured box
        rather than a crash or silence.

        ``uv0``/``uv1`` window into the handle's region (0..1 of it), so a
        host can draw a sub-rectangle of a placed image without placing it
        twice.
        """
        resolve = self.image_uv_resolver
        region = resolve(handle) if callable(resolve) else None
        if region is None:
            self.fill_rect(x, y, w, h, tint)
            return
        (ru0, rv0), (ru1, rv1) = region
        fu0, fv0 = uv0
        fu1, fv1 = uv1
        u = ru0 + max(fu0, 0.0) * (ru1 - ru0)
        v = rv0 + max(fv0, 0.0) * (rv1 - rv0)
        uw = (min(fu1, 1.0) - max(fu0, 0.0)) * (ru1 - ru0)
        vh = (min(fv1, 1.0) - max(fv0, 0.0)) * (rv1 - rv0)
        self._corner_quad(x, y, w, h, u, v, uw, vh, _rgba(tint))

    def stroke_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        edge: Colour,
        fill: Colour | None = None,
    ) -> None:
        """Draw a one-pixel outline, optionally over a fill."""
        u, v = self._solid_uv
        quad = self._corner_quad
        if fill is not None:
            quad(x, y, w, h, u, v, 0.0, 0.0, _rgba(fill))
        line = _rgba(edge)
        quad(x, y, w, 1.0, u, v, 0.0, 0.0, line)
        quad(x, y + h - 1.0, w, 1.0, u, v, 0.0, 0.0, line)
        quad(x, y, 1.0, h, u, v, 0.0, 0.0, line)
        quad(x + w - 1.0, y, 1.0, h, u, v, 0.0, 0.0, line)

    def fill_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        colour: Colour,
    ) -> None:
        """Fill a triangle with three independent corners. No outline.

        Flat-shaded like a rect quad -- each vertex samples the atlas's opaque
        block -- so ``ui.wgsl`` needs no second pipeline, only a longer vertex
        buffer; see :meth:`vertices`.
        """
        u, v = self._solid_uv
        scale = self._scale
        r, g, b, a = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((3, FLOATS_PER_VERTEX), dtype=np.float32)
        for row, (x, y) in enumerate((p0, p1, p2)):
            block[row, 0] = x * scale
            block[row, 1] = y * scale
        block[:, 2] = u
        block[:, 3] = v
        block[:, 4:8] = (r, g, b, a)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS)

    def gradient_triangle(self, p0, p1, p2, c0: Colour, c1: Colour,
                          c2: Colour) -> None:
        """Fill a triangle whose colour is interpolated from its corners.

        The vertex format already carries a colour per vertex, so this is
        :meth:`fill_triangle` with three colours instead of one -- the GPU
        interpolates them, which is exactly Gouraud shading.
        """
        u, v = self._solid_uv
        scale = self._scale
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((3, FLOATS_PER_VERTEX), dtype=np.float32)
        for row, ((x, y), colour) in enumerate(((p0, c0), (p1, c1), (p2, c2))):
            block[row, 0] = x * scale
            block[row, 1] = y * scale
            block[row, 4:8] = _rgba(colour)
        block[:, 2] = u
        block[:, 3] = v
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS)

    def image_triangle(self, p0, p1, p2, handle, uv0=(0.0, 0.0),
                       uv1=(1.0, 0.0), uv2=(1.0, 1.0),
                       tint: Colour = (255, 255, 255, 255)) -> None:
        """Map part of an image onto a triangle.

        ``handle`` is resolved through :attr:`image_uv_resolver`, as for
        :meth:`image`; the three ``uv`` (0..1 of the resolved region) become
        the three vertices' texel coordinates. Declined or unresolved, the
        triangle is filled with *tint*.
        """
        resolve = self.image_uv_resolver
        region = resolve(handle) if callable(resolve) else None
        if region is None:
            self.fill_triangle(p0, p1, p2, tint)
            return
        (ru0, rv0), (ru1, rv1) = region
        scale = self._scale
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((3, FLOATS_PER_VERTEX), dtype=np.float32)
        for row, ((x, y), (fu, fv)) in enumerate(((p0, uv0), (p1, uv1), (p2, uv2))):
            block[row, 0] = x * scale
            block[row, 1] = y * scale
            block[row, 2] = ru0 + fu * (ru1 - ru0)
            block[row, 3] = rv0 + fv * (rv1 - rv0)
        block[:, 4:8] = _rgba(tint)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS)

    def text_rotated(self, x: float, y: float, w: float, h: float, align: int,
                     string: str, colour: Colour, degrees: float = 0.0) -> None:
        """Draw *string* in the box, turned by *degrees* about its centre.

        The glyph quads :meth:`text` would emit, with their four corners
        rotated -- so they can no longer ride the axis-aligned rect record and
        go out as two triangles each, sampling the same atlas cells.
        """
        import math

        if not string:
            return
        shrink = self._shrink
        quad_w, quad_h = self._glyph_w, self._glyph_h
        if quad_w <= 0.0 or quad_h <= 0.0:
            return
        advance = self._advance
        span = advance * len(string)
        pen_x = (x + w - span if align & ALIGN_RIGHT
                 else x + (w - span) * 0.5 if align & ALIGN_HCENTER else x)
        baseline = (y + h * 0.5 + (self._ascent - self._half_cell_h) * shrink
                    if align & ALIGN_VCENTER else y + self._ascent * shrink)
        top = baseline - (self._ascent + self._pad) * shrink
        left = pen_x - self._pad * shrink
        ccx, ccy = x + w * 0.5, y + h * 0.5
        rad = math.radians(float(degrees))
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        scale = self._scale
        r, g, b, a = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        corners = []
        uvs = []
        for index, char in enumerate(string):
            cell = self._atlas.cell_of(char)
            if cell is None:
                continue
            u, v, cw, ch = cell
            gx0 = left + index * advance
            quad = ((gx0, top, u, v), (gx0 + quad_w, top, u + cw, v),
                    (gx0 + quad_w, top + quad_h, u + cw, v + ch),
                    (gx0, top + quad_h, u, v + ch))
            for k in (0, 1, 2, 0, 2, 3):
                qx, qy, qu, qv = quad[k]
                dx, dy = qx - ccx, qy - ccy
                corners.append(((ccx + dx * cos_a - dy * sin_a) * scale,
                                (ccy + dx * sin_a + dy * cos_a) * scale))
                uvs.append((qu, qv))
        if not corners:
            return
        block = np.empty((len(corners), FLOATS_PER_VERTEX), dtype=np.float32)
        block[:, 0:2] = corners
        block[:, 2:4] = uvs
        block[:, 4:8] = (r, g, b, a)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS, len(corners) // 3)

    def polyline(self, points, width: float, colour: Colour, closed: bool = False) -> None:
        """Stroke a path in one numpy pass: two triangles per segment, no Python loop.

        A plot trace is thousands of samples; :func:`painter.line` per
        segment costs a Python call and a list-extend each. Here the
        perpendicular offsets are computed for every segment at once and the
        six vertices per segment are laid out by fancy indexing.
        """
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
        if closed and pts.shape[0] > 2:
            pts = np.vstack([pts, pts[:1]])
        if pts.shape[0] < 2:
            return
        a = pts[:-1]
        b = pts[1:]
        d = b - a
        length = np.hypot(d[:, 0], d[:, 1])
        keep = length > 0.0
        if not keep.any():
            return
        a, b, d, length = a[keep], b[keep], d[keep], length[keep]
        hw = float(width) * 0.5
        off = np.column_stack([-d[:, 1], d[:, 0]]) / length[:, None] * hw
        c0 = a + off   # a + n
        c1 = b + off   # b + n
        c2 = b - off   # b - n
        c3 = a - off   # a - n
        # triangles (c0, c1, c2) and (c0, c2, c3), as painter.line draws them
        corners = np.stack([c0, c1, c2, c0, c2, c3], axis=1).reshape(-1, 2) * self._scale
        n = corners.shape[0]
        u, v = self._solid_uv
        r, g, bb, aa = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((n, FLOATS_PER_VERTEX), dtype=np.float32)
        block[:, 0:2] = corners
        block[:, 2] = u
        block[:, 3] = v
        block[:, 4:8] = (r, g, bb, aa)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS, n // 3)

    def fill_triangles(self, triangles, colour: Colour) -> None:
        """Fill an ``(n, 3, 2)`` block of triangles in one numpy pass."""
        pts = np.asarray(triangles, dtype=np.float32).reshape(-1, 3, 2)
        if pts.shape[0] == 0:
            return
        corners = pts.reshape(-1, 2) * self._scale
        n = corners.shape[0]
        u, v = self._solid_uv
        r, g, b, a = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((n, FLOATS_PER_VERTEX), dtype=np.float32)
        block[:, 0:2] = corners
        block[:, 2] = u
        block[:, 3] = v
        block[:, 4:8] = (r, g, b, a)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS, n // 3)

    def fill_convex(self, points, colour: Colour) -> None:
        """Fill a convex polygon as a fan, in one numpy pass."""
        pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
        if pts.shape[0] < 3:
            return
        first = np.repeat(pts[:1], pts.shape[0] - 2, axis=0)
        corners = np.stack([first, pts[1:-1], pts[2:]], axis=1).reshape(-1, 2) * self._scale
        n = corners.shape[0]
        u, v = self._solid_uv
        r, g, bb, aa = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        block = np.empty((n, FLOATS_PER_VERTEX), dtype=np.float32)
        block[:, 0:2] = corners
        block[:, 2] = u
        block[:, 3] = v
        block[:, 4:8] = (r, g, bb, aa)
        block[:, 8:12] = (cx0, cy0, cx1, cy1)
        self._tris.append(block)
        self._note(_TRIS, n // 3)

    def gradient_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        stops: Sequence[Colour],
        edge: Colour | None = None,
    ) -> None:
        """Fill a rectangle with a left-to-right gradient through *stops*."""
        colours = [_rgba(stop) for stop in stops]
        if len(colours) == 1:
            self._solid(x, y, w, h, colours[0])
        else:
            span = w / (len(colours) - 1)
            for index in range(len(colours) - 1):
                left, right = colours[index], colours[index + 1]
                self._solid(
                    x + index * span, y, span, h,
                    (left, right, right, left),
                )
        if edge is not None:
            line = _rgba(edge)
            self._solid(x, y, w, 1.0, line)
            self._solid(x, y + h - 1.0, w, 1.0, line)
            self._solid(x, y, 1.0, h, line)
            self._solid(x + w - 1.0, y, 1.0, h, line)

    def text(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        align: int,
        string: str,
        colour: Colour,
        bold: bool = False,
    ) -> None:
        """Draw *string* aligned inside the box, one quad per glyph."""
        if not string:
            return
        advance = self._advance
        shrink = self._shrink
        ascent = self._ascent
        quad_w, quad_h = self._glyph_w, self._glyph_h
        if quad_w <= 0.0 or quad_h <= 0.0:
            return

        span = advance * len(string)
        if align & ALIGN_RIGHT:
            pen_x = x + w - span
        elif align & ALIGN_HCENTER:
            pen_x = x + (w - span) * 0.5
        else:
            pen_x = x

        # The pen sits a fixed (pad, pad + ascent) inside every cell, so a
        # glyph's quad is the cell placed relative to the baseline. No
        # per-glyph bearing is needed; see the baker.
        baseline = (
            y + h * 0.5 + (ascent - self._half_cell_h) * shrink
            if align & ALIGN_VCENTER
            else y + ascent * shrink
        )
        top = baseline - (ascent + self._pad) * shrink

        # The glyph loop is the other half of the chrome's quads -- ~900 of the
        # ~2,100 in a frame -- and everything it needs except the cell and the
        # pen position is the same for every character in the string. So it is
        # emitted here rather than through `_corner_quad`: the per-glyph work
        # becomes a dict lookup, two multiplications and one `extend`.
        r, g, b, a = _rgba(colour)
        cx0, cy0, cx1, cy1 = self._scaled_clip
        scale = self._scale
        left = (pen_x - self._pad * shrink) * scale
        step = advance * scale
        y0 = top * scale
        y1 = y0 + quad_h * scale
        width = quad_w * scale
        cell_of = self._atlas.cell_of
        data = self._data

        # Straight into the buffer, one record per glyph: this is the hottest
        # loop in the chrome and a call per character would show. The run log
        # is told once, afterwards, for the same reason.
        drawn = 0
        for index, char in enumerate(string):
            cell = cell_of(char, bold=bold)
            if cell is None:
                continue
            cx, cy, cw, ch = cell
            x0 = left + index * step
            data.extend((
                x0, y0, x0 + width, y1,
                cx, cy, cx + cw, cy + ch,
                r, g, b, a,
                cx0, cy0, cx1, cy1,
            ))
            drawn += 1
        if drawn:
            self._note(_RECTS, drawn)

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Restrict drawing to a rectangle until :meth:`pop_clip`."""
        box = (x, y, x + w, y + h)
        if self._clips:
            px0, py0, px1, py1 = self._clips[-1]
            box = (
                max(box[0], px0), max(box[1], py0),
                min(box[2], px1), min(box[3], py1),
            )
        self._clips.append(box)
        # Kept scaled as well, because the quad loop reads it and only the
        # clip *stack* knows when it changes -- a handful of times a frame
        # against a couple of thousand quads.
        self._clip = box
        self._scaled_clip = self._scale_clip(box)

    def pop_clip(self) -> None:
        """Undo the most recent :meth:`push_clip`."""
        if self._clips:
            self._clips.pop()
        self._clip = self._clips[-1] if self._clips else _NO_CLIP
        self._scaled_clip = self._scale_clip(self._clip)

    def text_width(self, string: str) -> float:
        """Advance width of *string*, in pixels."""
        return self._atlas.advance(string) * self._font_scale

    def line_height(self) -> float:
        """Height of one line of text, in pixels."""
        return self._atlas.line_height * self._font_scale
