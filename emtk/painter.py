"""The drawing surface the in-viewport chrome is written against.

Why the chrome needs one
------------------------
the host's own furniture -- an object panel, a
sequence strip, the wizard, the movie transport and the menus -- is a layout and
hit-test engine with a painter bolted to the end of it. The layout half is
arithmetic and has never needed a GUI toolkit; the painting half called
``QPainter`` directly, and that one dependency decided where the whole app could
run.

It is also the app's largest per-frame cost. The chrome is rasterised into a
full-viewport premultiplied RGBA image and uploaded as a texture, which
``wgpu_view`` measured at **9.6 ms of a 21 ms frame** with a quarter of a
million beads on screen. The mitigation is a timer that lets the panel go
*stale* rather than repaint it when it changes -- and it is bypassed entirely
for any scene carrying labels, because labels move with the camera.

So the painting half is expressed here instead, as operations that a triangle
rasteriser can serve directly -- six of them axis-aligned rectangles, plus one
arbitrary filled triangle for the callers a rectangle cannot serve: a diagonal
line, a scatter marker, a projected 3-D face. See
the operation list below for what added the seventh one and why it
is additive rather than a reversal of the floor described below.

What the interface is, and what it deliberately is not
------------------------------------------------------
Not a ``QPainter`` with the names changed. ``QPainter`` is a *state machine* --
set a pen, set a brush, draw, and hope nothing in between changed either -- and
the chrome used it that way: thirty-one ``setPen`` and twenty ``setBrush`` calls
feeding eighteen ``drawRect``\\ s and fourteen ``drawText``\\ s. Ported literally,
that state would have to be tracked while emitting vertices, and a stale brush
becomes a mis-coloured quad rather than an error.

Every call here carries its own colour, so there is no state to get wrong and
each call maps to a fixed number of quads:

* :meth:`Painter.fill_rect` -- one quad;
* :meth:`Painter.stroke_rect` -- an optional fill plus four edge quads;
* :meth:`Painter.gradient_rect` -- one quad with per-vertex colour;
* :meth:`Painter.text` -- one quad per glyph, from an atlas;
* :meth:`Painter.push_clip` / :meth:`Painter.pop_clip` -- a scissor rectangle;
* :meth:`Painter.fill_triangle` -- three independent corners, flat-shaded.

Colours are plain ``(r, g, b)`` or ``(r, g, b, a)`` tuples of 0-255 ints,
because that is what the chrome's palette constants already are.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, Union

__all__ = [
    "REQUIRED_OPERATIONS",
    "OPTIONAL_OPERATIONS",
    "ACCELERATIONS",
    "polyline",
    "fill_convex",
    "fill_triangles",
    "fill_circle",
    "stroke_circle",
    "stroke_arc",
    "ALIGN_LEFT",
    "ALIGN_RIGHT",
    "ALIGN_HCENTER",
    "ALIGN_VCENTER",
    "ALIGN_CENTER",
    "Colour",
    "Painter",
    "line",
    "gradient_triangle",
    "image_triangle",
    "text_rotated",
    "subdivide_gradient",
]

#: A colour: ``(r, g, b)`` or ``(r, g, b, a)``, 0-255.
Colour = Union[tuple[int, int, int], tuple[int, int, int, int]]

#: Horizontal alignment within the box passed to :meth:`Painter.text`.
ALIGN_LEFT = 0x01
ALIGN_RIGHT = 0x02
ALIGN_HCENTER = 0x04

#: Vertical alignment. There is no top or bottom: the chrome centres every
#: string in its row, and offering alignments nobody uses would mean a glyph
#: rasteriser that has to implement them.
ALIGN_VCENTER = 0x80

#: The two combined, as the menus and buttons want.
ALIGN_CENTER = ALIGN_HCENTER | ALIGN_VCENTER


#: The operations a host **must** implement. This is the whole contract: a
#: surface that can do these can draw every widget emtk has, and everything
#: richer -- a polyline, a filled circle, an arc -- is decomposed onto them by
#: the module-level helpers below.
#:
#: Written down rather than left to prose. The protocol below declares eleven
#: methods and marks three of them optional in a docstring, which a type
#: checker cannot read and a new host author has no way to act on: it says
#: "implement six", the class says eleven, and `painter_capabilities` decides
#: at run time by asking. Now all three read the same tuples.
REQUIRED_OPERATIONS: tuple[str, ...] = (
    "fill_rect",
    "stroke_rect",
    "gradient_rect",
    "text",
    "push_clip",
    "pop_clip",
    "fill_triangle",
    "text_width",
    "line_height",
)

#: Operations a host **may** implement, each adding something emtk cannot
#: decompose. Their absence is normal and is not an error: emtk asks
#: `painter_capabilities` what the painter in hand can do, fills
#: `io.backend_flags` from the answer, and falls back visibly where one is
#: missing -- an image becomes its frame, a font push is ignored.
OPTIONAL_OPERATIONS: tuple[str, ...] = ("image", "set_font", "set_font_scale",
                                        "text_rotated", "gradient_triangle",
                                        "image_triangle")

#: Faster spellings of what the helpers below already do with the required
#: operations. A host that has a vectorised path offers one of these and the
#: helper uses it; a host that does not is *not* missing a feature, and no
#: backend flag reports them -- the picture is identical either way, which is
#: what separates them from :data:`OPTIONAL_OPERATIONS`.
ACCELERATIONS: tuple[str, ...] = ("polyline", "fill_triangles", "fill_convex")


class Painter(Protocol):
    """What the chrome needs in order to draw itself.

    :data:`REQUIRED_OPERATIONS` is the list to implement;
    :data:`OPTIONAL_OPERATIONS` may be left out. Two implementations ship and
    must agree: the Qt one, which is the reference, and the GPU one, which
    emits quads.
    """

    def fill_rect(self, x: float, y: float, w: float, h: float, colour: Colour) -> None:
        """Fill a rectangle. No outline."""
        ...

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
        ...

    def gradient_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        stops: Sequence[Colour],
        edge: Colour | None = None,
    ) -> None:
        """Fill a rectangle with a left-to-right gradient through *stops*.

        One caller: the panel's ``C`` button, whose rainbow is what says the
        button colours things. Evenly spaced -- the palette carries no offsets.
        """
        ...

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
        """Draw *string* aligned inside the box.

        ``bold`` has exactly one caller -- a menu's title row, which is how a
        menu says what it is a menu *of*. It is a parameter rather than painter
        state because state is what made the ``QPainter`` version awkward to
        emit vertices from, and because a glyph atlas has to bake a second face
        for it: a flag that is invisible at the call site is a flag that gets
        baked wrong.
        """
        ...

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Restrict drawing to a rectangle until :meth:`pop_clip`.

        Menus are the only caller, and they are the reason clipping exists at
        all: a menu taller than its allotted height scrolls inside a fixed box.
        """
        ...

    def pop_clip(self) -> None:
        """Undo the most recent :meth:`push_clip`."""
        ...

    def fill_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        colour: Colour,
    ) -> None:
        """Fill a triangle with three independent corners. No outline.

        The one primitive a rectangle cannot serve: a diagonal edge. Every
        other shape a plot needs -- a line segment, a marker -- is one or two
        calls to this, done by :func:`line` and by the callers in ``emtk``.
        """
        ...

    def text_width(self, string: str) -> float:
        """Advance width of *string*, in pixels."""
        ...

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
        """Blit *handle* into the box. **Optional** -- see :func:`image`."""

    def set_font(self, font) -> None:
        """Draw subsequent text in *font*. **Optional** -- see :func:`set_font`."""

    def set_font_scale(self, scale: float) -> None:
        """Draw subsequent text `scale` times the painter's base size.

        **Optional.** ``1.0`` restores the base size, which is the whole
        contract: the caller scales, draws, and hands back ``1.0``. A painter
        whose glyphs cannot change size simply does not define this, and
        callers probe for it rather than assume it --
        :func:`painter_capabilities` reports ``RENDERER_HAS_FONTS`` for a
        painter that can at least swap faces.

        The node editor's zoom is the user here: a node's content is laid out
        from the font metrics, so scaling the metrics scales the node, and
        re-shaping the glyphs at the scaled size keeps the text crisp instead
        of blowing up a bitmap.
        """

    def text_rotated(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        align: int,
        string: str,
        colour: Colour,
        degrees: float = 0.0,
    ) -> None:
        """Draw *string* turned by *degrees*. **Optional**.

        Declared because `painter_capabilities` asks every painter whether it
        has this, and an operation the run time probes for but the protocol
        never names is one a host author cannot discover.
        """

    def gradient_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        c0: Colour,
        c1: Colour,
        c2: Colour,
    ) -> None:
        """Fill a triangle whose colour is interpolated from its corners.

        **Optional** -- see :func:`gradient_triangle`. Gouraud shading: the
        colour at a point is the barycentric mix of ``c0``, ``c1`` and ``c2``,
        alpha included. The caller is ImPlot3D's surface and mesh, where a
        colormap is sampled per *vertex* and a flat triangle would show every
        facet of the grid.
        """

    def image_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        handle,
        uv0=(0.0, 0.0),
        uv1=(1.0, 0.0),
        uv2=(1.0, 1.0),
        tint: Colour = (255, 255, 255, 255),
    ) -> None:
        """Map the ``uv`` triangle of *handle* onto a screen triangle.

        **Optional** -- see :func:`image_triangle`. The affine map an
        axis-aligned :meth:`image` cannot express: a picture lying on a face
        of a rotated 3-D box.
        """

    def line_height(self) -> float:
        """Height of one line of text, in pixels."""
        ...


def line(
    p: "Painter",
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: float,
    colour: Colour,
) -> None:
    """Draw a segment of *width* pixels through :meth:`Painter.fill_triangle`.

    Not a :class:`Painter` method. A segment is a thin quad -- two triangles
    -- built once here from the perpendicular offset, rather than asked of
    every implementation separately; that is what keeps a new :class:`Painter`
    backend at seven methods instead of eight, and what keeps this arithmetic
    in one place instead of two copies quietly disagreeing at a shared
    endpoint's width.

    A degenerate segment (``x0 == x1 and y0 == y1``) draws nothing -- there is
    no direction to offset a zero-length line perpendicular to.
    """
    dx = x1 - x0
    dy = y1 - y0
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        return
    hw = width * 0.5
    ox = -dy / length * hw
    oy = dx / length * hw
    a = (x0 + ox, y0 + oy)
    b = (x1 + ox, y1 + oy)
    c = (x1 - ox, y1 - oy)
    d = (x0 - ox, y0 - oy)
    p.fill_triangle(a, b, c, colour)
    p.fill_triangle(a, c, d, colour)


def polyline(
    p: "Painter",
    points,
    width: float,
    colour: Colour,
    closed: bool = False,
) -> None:
    """Stroke a path of *width* pixels through *points* (``(n, 2)`` array or list).

    Uses the painter's own ``polyline`` when it has one (:class:`QuadPainter`
    does -- one numpy pass for the whole path, which is what a plot trace with
    ten thousand samples needs) and falls back to one thin quad per segment
    through :func:`line` otherwise. Every :class:`Painter` therefore takes a
    polyline; only the cost differs.
    """
    fast = getattr(p, "polyline", None)
    if callable(fast):
        fast(points, width, colour, closed)
        return
    pts = [(float(x), float(y)) for x, y in points]
    if closed and len(pts) > 2:
        pts.append(pts[0])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        line(p, x0, y0, x1, y1, width, colour)


def fill_triangles(p: "Painter", triangles, colour: Colour) -> None:
    """Fill many triangles at once: ``triangles`` is ``(n, 3, 2)``.

    One call for a whole band, ribbon or mesh. The per-triangle entry point
    costs a Python call and a twelve-float extend *each*, which is what made a
    Circos plot of a hundred chords cost nine milliseconds of a frame -- the
    quads were not the problem, the interpreter was. A painter with a numpy
    path (:class:`~.quad_painter.QuadPainter`) fills the block in one pass;
    every other painter still gets its triangles, one at a time, through the
    same six operations as before.
    """
    fast = getattr(p, "fill_triangles", None)
    if callable(fast):
        fast(triangles, colour)
        return
    for tri in triangles:
        p.fill_triangle(
            (float(tri[0][0]), float(tri[0][1])),
            (float(tri[1][0]), float(tri[1][1])),
            (float(tri[2][0]), float(tri[2][1])),
            colour,
        )


def fill_convex(p: "Painter", points, colour: Colour) -> None:
    """Fill a convex polygon (a fan from its first vertex)."""
    fast = getattr(p, "fill_convex", None)
    if callable(fast):
        fast(points, colour)
        return
    pts = [(float(x), float(y)) for x, y in points]
    for i in range(1, len(pts) - 1):
        p.fill_triangle(pts[0], pts[i], pts[i + 1], colour)


def _circle_points(cx: float, cy: float, r: float, segments: int, a0: float = 0.0, a1: float = 6.283185307179586):
    import math

    n = max(int(segments), 3)
    step = (a1 - a0) / n
    return [(cx + r * math.cos(a0 + i * step), cy + r * math.sin(a0 + i * step)) for i in range(n + 1)]


def _segments_for(r: float) -> int:
    return max(12, min(64, int(r * 1.5)))


def fill_circle(p: "Painter", cx: float, cy: float, r: float, colour: Colour, segments: int = 0) -> None:
    """Fill a circle: a fan of ``segments`` triangles (chosen from the radius by default)."""
    pts = _circle_points(cx, cy, r, segments or _segments_for(r))
    fill_convex(p, pts[:-1], colour)


def stroke_circle(p: "Painter", cx: float, cy: float, r: float, width: float, colour: Colour, segments: int = 0) -> None:
    """Outline a circle with a closed polyline."""
    pts = _circle_points(cx, cy, r, segments or _segments_for(r))
    polyline(p, pts[:-1], width, colour, closed=True)


def stroke_arc(p: "Painter", cx: float, cy: float, r: float, a0: float, a1: float,
               width: float, colour: Colour, segments: int = 0) -> None:
    """Stroke an arc from angle *a0* to *a1* (radians)."""
    pts = _circle_points(cx, cy, r, segments or _segments_for(r), a0, a1)
    polyline(p, pts, width, colour)


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #
def image(
    p: "Painter",
    x: float,
    y: float,
    w: float,
    h: float,
    handle,
    uv0=(0.0, 0.0),
    uv1=(1.0, 1.0),
    tint: Colour = (255, 255, 255, 255),
) -> None:
    """Draw *handle* into ``(x, y, w, h)``. ``ImDrawList::AddImage``.

    A painter that can blit implements ``image`` and this calls it. One that
    cannot -- a recording double, a text dump -- gets a tinted rectangle, which
    is what an image *is* to a painter that has no pixels: something occupying
    that box. The alternative was refusing, and then no port that shows a
    picture could run at all.

    The handle is whatever the host's painter understands: a texture id, a
    ``QImage``, an array. emtk never looks inside it.
    """
    op = getattr(p, "image", None)
    if callable(op):
        op(x, y, w, h, handle, uv0, uv1, tint)
        return
    p.fill_rect(x, y, w, h, tint)


def text_rotated(p: "Painter", x: float, y: float, w: float, h: float,
                 align: int, string: str, colour: Colour,
                 degrees: float = 0.0) -> bool:
    """Draw *string* in the box turned by *degrees* about the box centre.

    Positive degrees turn clockwise on screen, as ``QPainter::rotate`` does
    in a y-down frame. A painter without the operation gets the string
    unrotated in the same box -- still legible, still where it was asked for
    -- and the return value says which happened.
    """
    op = getattr(p, "text_rotated", None)
    if callable(op) and abs(float(degrees)) > 1e-9:
        op(x, y, w, h, align, string, colour, float(degrees))
        return True
    p.text(x, y, w, h, align, string, colour)
    return abs(float(degrees)) <= 1e-9


def _spread(c0, c1, c2) -> int:
    a, b, c = _rgba255(c0), _rgba255(c1), _rgba255(c2)
    return max(max(a[k], b[k], c[k]) - min(a[k], b[k], c[k]) for k in range(4))


def _rgba255(colour) -> tuple[int, int, int, int]:
    return (int(colour[0]), int(colour[1]), int(colour[2]),
            int(colour[3]) if len(colour) > 3 else 255)


def _mix(a, b):
    return tuple((a[k] + b[k]) * 0.5 for k in range(4))


def subdivide_gradient(fill, p0, p1, p2, c0, c1, c2,
                       tolerance: int = 6, max_depth: int = 5) -> None:
    """Approximate a Gouraud triangle with flat ones, calling ``fill(a, b, c, colour)``.

    Split at the edge midpoints until the corners of a piece differ by no more
    than *tolerance* levels on any channel, or its longest edge is under two
    pixels, or *max_depth* halvings have been made; each piece is filled with
    the mean of its corners. This is what a painter with no per-vertex colour
    draws, and what the Qt painter draws natively: ``QPainter`` has no vertex
    colours, and at the size a surface cell is on screen the steps are below
    what the eye resolves.
    """
    c0, c1, c2 = _rgba255(c0), _rgba255(c1), _rgba255(c2)
    stack = [(p0, p1, p2, c0, c1, c2, 0)]
    while stack:
        a, b, c, ca, cb, cc, depth = stack.pop()
        longest = max((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2,
                      (b[0] - c[0]) ** 2 + (b[1] - c[1]) ** 2,
                      (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2)
        if (depth >= max_depth or longest < 4.0
                or _spread(ca, cb, cc) <= tolerance):
            mean = tuple(int(round((ca[k] + cb[k] + cc[k]) / 3.0)) for k in range(4))
            fill(a, b, c, mean)
            continue
        ab = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
        bc = ((b[0] + c[0]) * 0.5, (b[1] + c[1]) * 0.5)
        ca_ = ((c[0] + a[0]) * 0.5, (c[1] + a[1]) * 0.5)
        cab, cbc, cca = _mix(ca, cb), _mix(cb, cc), _mix(cc, ca)
        d = depth + 1
        stack.append((a, ab, ca_, ca, cab, cca, d))
        stack.append((ab, b, bc, cab, cb, cbc, d))
        stack.append((ca_, bc, c, cca, cbc, cc, d))
        stack.append((ab, bc, ca_, cab, cbc, cca, d))


def gradient_triangle(p: "Painter", p0, p1, p2, c0: Colour, c1: Colour,
                      c2: Colour) -> None:
    """Fill a triangle with per-corner colours on any painter.

    The painter's own ``gradient_triangle`` when it has one; three equal
    colours are one :meth:`Painter.fill_triangle`; anything else is
    :func:`subdivide_gradient` over ``fill_triangle``.
    """
    op = getattr(p, "gradient_triangle", None)
    if callable(op):
        op(p0, p1, p2, c0, c1, c2)
        return
    if _rgba255(c0) == _rgba255(c1) == _rgba255(c2):
        p.fill_triangle(p0, p1, p2, c0)
        return
    subdivide_gradient(p.fill_triangle, p0, p1, p2, c0, c1, c2)


def image_triangle(p: "Painter", p0, p1, p2, handle, uv0=(0.0, 0.0),
                   uv1=(1.0, 0.0), uv2=(1.0, 1.0),
                   tint: Colour = (255, 255, 255, 255)) -> None:
    """Map part of an image onto a triangle on any painter.

    A painter without ``image_triangle`` fills the triangle with *tint* --
    the same "a picture occupies this area" fallback :func:`image` gives.
    """
    op = getattr(p, "image_triangle", None)
    if callable(op):
        op(p0, p1, p2, handle, uv0, uv1, uv2, tint)
        return
    p.fill_triangle(p0, p1, p2, tint)


def set_font(p: "Painter", font) -> bool:
    """Ask the painter to draw in *font*. ``ImGui::PushFont``.

    Returns whether it could. Metrics come from the painter
    (``text_width``/``line_height``), so a painter that changes font changes
    both, and emtk needs to know nothing about either.
    """
    op = getattr(p, "set_font", None)
    if callable(op):
        op(font)
        return True
    return False
