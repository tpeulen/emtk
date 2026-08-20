"""``CirclePlot`` -- a Circos-style circular layout, drawn through the painter.

Ported from **pyCirclize** (moshi4, MIT; ``junk/pyCirclize``). The layout
arithmetic is the reference's: sectors laid round the circle in proportion to
their size with a fixed gap between them (``Circos.__init__``), a per-sector
data-to-angle mapping (``Sector.x_to_rad``), a 0..100 radius space with zero at
the centre (``config.MIN_R``/``MAX_R``), north at the top and angles running
clockwise (``_initialize_polar_axes``), and links drawn as quadratic Bezier
ribbons whose control point is placed from a ``height_ratio``
(``patches.BezierCurveLink``). The call shape is kept where it survives the
move:

>>> with begin_circle(painter, x, y, w, h) as circle:
...     circle.sector("E", 164, colour=(90, 130, 190))
...     circle.link(("E", 3, 3), ("E", 119, 119), colour=(220, 160, 90))

What could not be kept is matplotlib. pyCirclize builds `Patch` objects on a
`PolarAxes` and lets it project them; there is no polar axis here, so each
shape is projected to pixels and emitted as triangles and polylines
(:mod:`cmtk.painter`) -- a ring segment and a chord ribbon are both
non-convex, so both are drawn as triangle strips rather than as one fan. Like
:class:`~.plot.Plot`, nothing draws when it is called: sectors, points and
links are recorded and drawn together at :meth:`draw`, because the chrome is
rebuilt from scratch each frame and there is no previous frame's layout to
draw against.

Angles are radians measured from the top, clockwise. Radii are in the
reference's 0..100 space; :meth:`draw` scales them to the box it is given.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from contextlib import contextmanager

import numpy as np

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from ..painter import fill_convex, fill_triangles, polyline

__all__ = ["CirclePlot", "CircleSector", "begin_circle"]

#: The reference's radius space (``config.MIN_R``/``MAX_R``): the centre is 0
#: and the outer edge is 100, whatever the box turns out to be in pixels.
MIN_R = 0.0
MAX_R = 100.0

#: Radians per step when an arc is flattened (``config.ARC_RADIAN_STEP``).
#: The reference draws into a vector canvas and can afford 0.01; a chrome quad
#: buffer cannot, and at these radii the difference is invisible -- a 100 px
#: radius moves 0.05 px between steps at 0.03.
ARC_RADIAN_STEP = 0.03

#: Samples along a link's Bezier. The reference hands the curve to matplotlib
#: and lets it flatten; here it is flattened once, at a fixed count, because a
#: chord's cost has to be predictable when a document has hundreds of them.
BEZIER_STEPS = 48

#: Stroke width for a chord between two *points* rather than two regions.
DEFAULT_LINK_WIDTH = 1.5

_LABEL = (225, 228, 235)
_DIM = (150, 155, 165)
_AXIS = (110, 115, 125)


def _strip(one, two):
    """The triangles between two runs of points: ``(n, 3, 2)``.

    A ring segment and a chord ribbon are both strips, and both are
    non-convex, so neither can be a fan. Built as one array and filled in one
    call -- emitted a triangle at a time it is two Python calls per step, which
    is most of what a network of chords used to cost.
    """
    a = np.asarray(one, dtype=np.float32)
    b = np.asarray(two, dtype=np.float32)
    count = min(len(a), len(b)) - 1
    if count <= 0:
        return np.zeros((0, 3, 2), dtype=np.float32)
    out = np.empty((count * 2, 3, 2), dtype=np.float32)
    out[0::2, 0], out[0::2, 1], out[0::2, 2] = a[:count], b[:count], b[1:count + 1]
    out[1::2, 0], out[1::2, 1], out[1::2, 2] = a[:count], b[1:count + 1], a[1:count + 1]
    return out


@dataclass
class CircleSector:
    """One sector of the circle: a named span at a fixed angular range.

    Attributes
    ----------
    name : str
        The sector's name, drawn as its label.
    start, end : float
        The sector's own coordinate range (residue numbers, base pairs, an
        index -- whatever the caller counts in).
    rad_start, rad_end : float
        Where it sits on the circle, in radians from the top, clockwise.
    colour : tuple
        The band's fill.
    clockwise : bool
        Whether its coordinates run with the circle or against it
        (``Sector.clockwise`` in the reference).
    """

    name: str
    start: float
    end: float
    rad_start: float
    rad_end: float
    colour: tuple = (110, 120, 140)
    clockwise: bool = True

    @property
    def size(self) -> float:
        return float(self.end - self.start)

    def x_to_rad(self, x: float) -> float:
        """Where coordinate *x* sits on the circle, in radians.

        ``Sector.x_to_rad``, without the range check: a position outside the
        sector is clamped rather than raised over, because this draws a
        document somebody is editing -- a residue number one past the end of a
        chain is a thing to see, not a traceback.
        """
        size = self.size
        if size <= 0.0:
            return self.rad_start
        value = min(max(float(x), self.start), self.end)
        if not self.clockwise:
            value = (self.start + self.end) - value
        ratio = (value - self.start) / size
        return self.rad_start + (self.rad_end - self.rad_start) * ratio


@dataclass
class _Link:
    rad1: tuple            # (start, end) radians of the first foot
    rad2: tuple            # ...and of the second
    r: float
    colour: tuple
    height_ratio: float
    width: float           # 0 draws a ribbon; > 0 draws a line of that width


@dataclass
class _Point:
    rad: float
    r: float
    radius: float
    colour: tuple


@dataclass
class _Text:
    rad: float
    r: float
    text: str
    colour: tuple
    outside: bool


@dataclass
class _Band:
    rad: tuple
    r: tuple
    colour: tuple


@dataclass
class _Tick:
    rad: float
    r: float
    length: float
    label: str
    colour: tuple


class CirclePlot:
    """A circular layout, built up by :meth:`sector`/:meth:`link`/... then drawn.

    Parameters
    ----------
    x, y, w, h : float
        The box to draw in, in painter pixels. The circle is centred in it and
        sized to the smaller side.
    start, end : float, optional
        First and last degree of the layout (``Circos(start=, end=)``). The
        default is the whole circle.
    space : float, optional
        Degrees of gap between sectors.
    endspace : bool, optional
        Whether a gap follows the last sector as well -- ``False`` closes the
        ring up against *end*.
    """

    def __init__(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        start: float = 0.0,
        end: float = 360.0,
        space: float = 2.0,
        endspace: bool = True,
    ) -> None:
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)
        self.start, self.end = float(start), float(end)
        self.space, self.endspace = float(space), bool(endspace)
        self.sectors: list[CircleSector] = []
        self._pending: list[tuple] = []
        self._links: list[_Link] = []
        self._points: list[_Point] = []
        self._texts: list[_Text] = []
        self._bands: list[_Band] = []
        self._ticks: list[_Tick] = []
        self._laid_out = False

    # -- geometry ---------------------------------------------------------- #
    @property
    def centre(self) -> tuple:
        """The circle's centre, in pixels."""
        return (self.x + self.w * 0.5, self.y + self.h * 0.5)

    @property
    def scale(self) -> float:
        """Pixels per radius unit (:data:`MAX_R` maps to the box's half-side)."""
        return min(self.w, self.h) * 0.5 / MAX_R

    def to_pixels(self, rad: float, r: float) -> tuple:
        """Polar (radians from the top, clockwise; radius 0..100) to pixels.

        The reference's ``set_theta_zero_location("N")`` plus
        ``set_theta_direction(-1)``, done here because there is no axis to ask.
        Screen y grows downward, which is what turns the reference's
        anticlockwise-from-north into a plain sine/cosine pair.
        """
        cx, cy = self.centre
        radius = r * self.scale
        return (cx + radius * math.sin(rad), cy - radius * math.cos(rad))

    # -- building ---------------------------------------------------------- #
    def sector(
        self,
        name: str,
        size,
        *,
        colour: tuple = (110, 120, 140),
        clockwise: bool = True,
    ) -> None:
        """Add a sector of *size* (a length, or a ``(start, end)`` range).

        Sectors share the circle in proportion to their sizes, with
        :attr:`space` degrees between them -- ``Circos.__init__``'s
        arithmetic. The angles are worked out once every sector is known, so
        this only records.
        """
        if isinstance(size, (tuple, list)):
            span = (float(size[0]), float(size[1]))
        else:
            span = (0.0, float(size))
        self._pending.append((str(name), span, colour, bool(clockwise)))
        self._laid_out = False

    def _lay_out(self) -> None:
        """Turn the recorded sectors into angular ranges."""
        if self._laid_out:
            return
        self.sectors = []
        if not self._pending:
            self._laid_out = True
            return
        gaps = len(self._pending) if self.endspace else len(self._pending) - 1
        degrees = (self.end - self.start) - self.space * max(gaps, 0)
        total = sum(max(span[1] - span[0], 0.0) for _n, span, _c, _cw in self._pending)
        if total <= 0.0 or degrees <= 0.0:
            # Every sector empty (a document with one position per chain), or
            # more gap than circle. Share the circle equally rather than
            # collapsing every sector onto one radian: the labels are the
            # point of such a plot, and they need somewhere to sit.
            total = float(len(self._pending))
            spans = [(0.0, 1.0)] * len(self._pending)
            degrees = max(degrees, 1.0)
        else:
            spans = [span for _n, span, _c, _cw in self._pending]
        rad = math.radians(self.start)
        for index, (name, _span, colour, clockwise) in enumerate(self._pending):
            span = spans[index]
            size = max(span[1] - span[0], 0.0) or (1.0 if total == len(spans) else 0.0)
            rad_size = math.radians(degrees * (size / total)) if total else 0.0
            self.sectors.append(CircleSector(
                name=name, start=span[0], end=span[1],
                rad_start=rad, rad_end=rad + rad_size,
                colour=colour, clockwise=clockwise,
            ))
            rad += rad_size + math.radians(self.space)
        self._laid_out = True

    def get_sector(self, name: str) -> CircleSector | None:
        """The sector called *name*, or ``None``."""
        self._lay_out()
        for sector in self.sectors:
            if sector.name == name:
                return sector
        return None

    def band(self, name: str, start: float, end: float, r_lim: tuple,
             *, colour: tuple) -> None:
        """A filled band across ``(start, end)`` of one sector, between two radii."""
        sector = self.get_sector(name)
        if sector is None:
            return
        self._bands.append(_Band(
            rad=(sector.x_to_rad(start), sector.x_to_rad(end)),
            r=(float(r_lim[0]), float(r_lim[1])), colour=tuple(colour),
        ))

    def point(self, name: str, x: float, r: float, *, radius: float = 3.0,
              colour: tuple = (230, 200, 120)) -> None:
        """A dot at coordinate *x* of one sector, at radius *r*."""
        sector = self.get_sector(name)
        if sector is None:
            return
        self._points.append(_Point(
            rad=sector.x_to_rad(x), r=float(r),
            radius=float(radius), colour=tuple(colour),
        ))

    def text(self, name: str, x: float, r: float, label: str, *,
             colour: tuple = _LABEL, outside: bool = True) -> None:
        """A label at coordinate *x* of one sector, at radius *r*."""
        sector = self.get_sector(name)
        if sector is None:
            return
        self._texts.append(_Text(
            rad=sector.x_to_rad(x), r=float(r), text=str(label),
            colour=tuple(colour), outside=bool(outside),
        ))

    def ticks(self, name: str, positions, r: float, *, length: float = 3.0,
              labels=None, colour: tuple = _AXIS) -> None:
        """Tick marks (and optional labels) at coordinates of one sector."""
        sector = self.get_sector(name)
        if sector is None:
            return
        labels = list(labels or [])
        for index, position in enumerate(positions):
            self._ticks.append(_Tick(
                rad=sector.x_to_rad(position), r=float(r), length=float(length),
                label=str(labels[index]) if index < len(labels) else "",
                colour=tuple(colour),
            ))

    def link(self, region1: tuple, region2: tuple, *, r: float = 72.0,
             colour: tuple = (150, 160, 180, 140), height_ratio: float = 0.5,
             width: float = 0.0) -> None:
        """A chord between two sector regions.

        ``Circos.link``: each region is ``(sector name, start, end)``. A region
        whose start equals its end has no width, so the chord is drawn as a
        line rather than a ribbon -- which is what a *point-to-point* link is,
        and what an fps.json distance between two labelling positions wants.

        Parameters
        ----------
        region1, region2 : tuple
            ``(name, start, end)``.
        r : float, optional
            Radius the chord's feet sit at.
        colour : tuple
            RGB or RGBA.
        height_ratio : float, optional
            Where the Bezier control point goes, as in the reference: 0.5 puts
            it at the centre (the classic Circos chord), higher bulges the
            curve away from the centre, lower pulls it toward the near edge.
        width : float, optional
            Stroke width for a point-to-point link. Ribbons ignore it.
        """
        first, second = self.get_sector(region1[0]), self.get_sector(region2[0])
        if first is None or second is None:
            return
        rad1 = (first.x_to_rad(region1[1]), first.x_to_rad(region1[2]))
        rad2 = (second.x_to_rad(region2[1]), second.x_to_rad(region2[2]))
        # A region with no width has no ribbon to draw -- two feet of zero
        # angle leave a strip of zero area -- so a point-to-point link is a
        # stroked curve, and gets a default width when the caller named none.
        flat = abs(rad1[1] - rad1[0]) < 1e-9 and abs(rad2[1] - rad2[0]) < 1e-9
        stroke = float(width) if float(width) > 0.0 else (DEFAULT_LINK_WIDTH if flat else 0.0)
        self._links.append(_Link(
            rad1=rad1, rad2=rad2, r=float(r), colour=tuple(colour),
            height_ratio=float(height_ratio), width=stroke,
        ))

    # -- drawing ----------------------------------------------------------- #
    def draw(self, p) -> None:
        """Draw everything recorded, back to front."""
        self._lay_out()
        for link in self._links:
            self._draw_link(p, link)
        for sector in self.sectors:
            self._draw_band(p, (sector.rad_start, sector.rad_end), (88.0, 96.0),
                            sector.colour)
        for band in self._bands:
            self._draw_band(p, band.rad, band.r, band.colour)
        for tick in self._ticks:
            self._draw_tick(p, tick)
        for point in self._points:
            self._draw_point(p, point)
        for text in self._texts:
            self._draw_text(p, text)
        self._draw_sector_labels(p)

    def _arc_points(self, a0: float, a1: float, r: float) -> np.ndarray:
        """The pixels of an arc, as an ``(n, 2)`` array.

        In numpy rather than a list comprehension of tuples: a ring of
        seventeen sectors and a hundred chords is thousands of points, and
        building each one as a Python tuple through :meth:`to_pixels` was the
        larger half of what this widget cost to draw -- more than the quads it
        produced.
        """
        steps = max(2, int(abs(a1 - a0) / ARC_RADIAN_STEP) + 1)
        angles = np.linspace(a0, a1, steps + 1)
        cx, cy = self.centre
        radius = r * self.scale
        return np.stack(
            [cx + radius * np.sin(angles), cy - radius * np.cos(angles)], axis=1
        )

    def _draw_band(self, p, rad: tuple, r: tuple, colour: tuple) -> None:
        """A ring segment, as a triangle strip.

        Not a convex fan: a ring segment has a hole in the middle of its own
        bounding shape, so filling it from one vertex draws over the centre.
        """
        inner = self._arc_points(rad[0], rad[1], min(r))
        outer = self._arc_points(rad[0], rad[1], max(r))
        fill_triangles(p, _strip(inner, outer), colour)

    def _bezier(self, start: tuple, end: tuple, rad1: float, rad2: float,
                height_ratio: float) -> list:
        """The reference's link curve, flattened.

        ``BezierCurveLink``'s control point, verbatim: at or beyond half height
        it sits *opposite* the midpoint angle and outside the centre, below it
        on the same side -- which is what makes a low ratio hug the rim and 0.5
        pass through the middle.
        """
        if height_ratio >= 0.5:
            r_control = MAX_R * (height_ratio - 0.5)
            rad_control = (rad1 + rad2) * 0.5 + math.pi
        else:
            r_control = MAX_R * (0.5 - height_ratio)
            rad_control = (rad1 + rad2) * 0.5
        control = self.to_pixels(rad_control, r_control)
        t = np.linspace(0.0, 1.0, BEZIER_STEPS + 1)
        u = 1.0 - t
        return np.stack([
            u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
            u * u * start[1] + 2 * u * t * control[1] + t * t * end[1],
        ], axis=1)

    def _draw_link(self, p, link: _Link) -> None:
        if link.width > 0.0:
            curve = self._bezier(
                self.to_pixels(link.rad1[0], link.r),
                self.to_pixels(link.rad2[0], link.r),
                link.rad1[0], link.rad2[0], link.height_ratio,
            )
            polyline(p, curve, link.width, link.colour)
            return
        # A ribbon: the two Beziers that join the feet, closed by the arcs
        # across each foot, filled as a strip between the curves.
        left = self._bezier(
            self.to_pixels(link.rad1[0], link.r),
            self.to_pixels(link.rad2[1], link.r),
            link.rad1[0], link.rad2[1], link.height_ratio,
        )
        right = self._bezier(
            self.to_pixels(link.rad1[1], link.r),
            self.to_pixels(link.rad2[0], link.r),
            link.rad1[1], link.rad2[0], link.height_ratio,
        )
        fill_triangles(p, _strip(left, right), link.colour)
        for rad in (link.rad1, link.rad2):
            arc = self._arc_points(rad[0], rad[1], link.r)
            if len(arc) > 2:
                fill_convex(p, arc, link.colour)

    def _draw_point(self, p, point: _Point) -> None:
        cx, cy = self.to_pixels(point.rad, point.r)
        angles = np.linspace(0.0, 2.0 * math.pi, 11)[:-1]
        ring = np.stack([cx + point.radius * np.cos(angles),
                         cy + point.radius * np.sin(angles)], axis=1)
        fill_convex(p, ring, point.colour)

    def _draw_tick(self, p, tick: _Tick) -> None:
        inner = self.to_pixels(tick.rad, tick.r)
        outer = self.to_pixels(tick.rad, tick.r + tick.length)
        polyline(p, [inner, outer], 1.0, tick.colour)
        if tick.label:
            self._label_at(p, tick.rad, tick.r + tick.length + 2.0,
                           tick.label, _DIM, outside=True)

    def _draw_text(self, p, text: _Text) -> None:
        self._label_at(p, text.rad, text.r, text.text, text.colour, text.outside)

    def _label_at(self, p, rad: float, r: float, label: str, colour: tuple,
                  outside: bool) -> None:
        """Place a label beside its radius, on the side the angle points at.

        The reference rotates its text to the tangent; there is no rotated
        text in the painter (glyphs come from a baked atlas), so the label is
        drawn horizontally and *aligned* by which half of the circle it is on
        -- left of the point on the left, right of it on the right. Which is
        what keeps a ring of labels from writing over the ring itself.
        """
        px, py = self.to_pixels(rad, r)
        width = p.text_width(label) + 4.0
        height = p.line_height()
        on_the_right = math.sin(rad) >= 0.0
        if not outside:
            p.text(px - width * 0.5, py - height * 0.5, width, height,
                   ALIGN_CENTER, label, colour)
        elif on_the_right:
            p.text(px + 3.0, py - height * 0.5, width, height,
                   ALIGN_LEFT | ALIGN_VCENTER, label, colour)
        else:
            p.text(px - width - 3.0, py - height * 0.5, width, height,
                   ALIGN_RIGHT | ALIGN_VCENTER, label, colour)

    def _draw_sector_labels(self, p) -> None:
        for sector in self.sectors:
            middle = (sector.rad_start + sector.rad_end) * 0.5
            self._label_at(p, middle, 99.0, sector.name, _LABEL, outside=True)


@contextmanager
def begin_circle(p, x: float, y: float, w: float, h: float, **kwargs):
    """Build a :class:`CirclePlot` and draw it when the block exits.

    The same shape as :func:`~.plot.begin_plot`, and for the same reason: what
    is drawn depends on everything that was added, so nothing can be drawn
    until the block is over.
    """
    circle = CirclePlot(x, y, w, h, **kwargs)
    try:
        yield circle
    finally:
        circle.draw(p)
