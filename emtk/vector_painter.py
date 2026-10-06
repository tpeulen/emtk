"""Vector painters: the painter contract written out as SVG or PDF.

A figure for print has to stay a figure when it is scaled: lines that are
lines, text that is text. :class:`SvgPainter` and :class:`PdfPainter` take the
same calls every raster painter takes and record them as shapes, so anything
emtk draws -- an :mod:`emtk.figure`, a whole app frame -- comes out as a
vector file.

Layout is the raster painters' layout. Text is measured with the baked atlas
(:func:`emtk.font.load_atlas`) and placed with the same pen and baseline
arithmetic :class:`emtk.testing.PixelPainter` uses, so a vector file and a PNG
of the same frame agree on where every string is. The atlas is a monospace
face, which is what makes the vector text faithful without embedding a font:

* SVG names a monospace family and pins each string to its laid-out width
  (``textLength``), so a viewer substituting a different monospace face
  still fills exactly the measured box.
* PDF uses the base-14 ``Courier`` (600/1000 em advance, against the baked
  face's 602) and ``Symbol`` for Greek and mathematical characters, both of
  which every PDF reader has. A character neither covers is drawn as ``?``.

Coordinates are the painter's logical pixels; the file's physical size is
``width x height`` pixels at :data:`PX_PER_INCH` (96, the CSS pixel), so a
640x480 figure is 6.67x5 inches, or 480x360 PDF points.
"""

from __future__ import annotations

import base64
import math
import zlib
from typing import Any

from .painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER, subdivide_gradient

__all__ = ["PX_PER_INCH", "PdfPainter", "SvgPainter", "VectorPainter"]

#: Logical pixels per inch in the written file: the CSS pixel.
PX_PER_INCH = 96.0
#: PDF points per logical pixel.
_PT = 72.0 / PX_PER_INCH
#: Courier's advance as a fraction of its em (all base-14 Courier glyphs).
_COURIER_ADVANCE = 0.6

#: Unicode code point -> base-14 Symbol font code, for the characters plot
#: labels use. Integers on both sides: this is an encoding table, never text
#: the chrome draws, and the atlas guard reads string literals.
_SYMBOL_CODES: dict[int, int] = {
    **{0x3B1 + i: ord(c) for i, c in enumerate("abgdezhqiklmnxoprVstufcyw")},
    **{0x391 + i: ord(c) for i, c in enumerate("ABGDEZHQIKLMNXOPR STUFCYW") if c != " "},
    0x3D1: ord("J"), 0x3D5: ord("j"), 0x3D6: ord("v"), 0x3C2: ord("V"),
    0x2264: 0xA3, 0x2265: 0xB3, 0x221E: 0xA5, 0xD7: 0xB4, 0xF7: 0xB8,
    0x221A: 0xD6, 0x2211: 0xE5, 0x220F: 0xD5, 0x222B: 0xF2, 0x2192: 0xAE,
    0x2190: 0xAC, 0x2191: 0xAD, 0x2193: 0xAF, 0x2194: 0xAB, 0x21D2: 0xDE,
    0x21D4: 0xDB, 0x2202: 0xB6, 0x2248: 0xBB, 0x2260: 0xB9, 0x2261: 0xBA,
    0x22C5: 0xD7, 0x2208: 0xCE, 0x2209: 0xCF, 0x2207: 0xD1, 0x2032: 0xA2,
    0x2033: 0xB2, 0x221D: 0xB5, 0x2022: 0xB7, 0x2026: 0xBC, 0x2200: 0x22,
    0x2203: 0x24, 0x2205: 0xC6, 0x2229: 0xC7, 0x222A: 0xC8, 0x2282: 0xCC,
    0x2283: 0xC9, 0x2286: 0xCD, 0x2287: 0xCA, 0x2227: 0xD9, 0x2228: 0xDA,
    0xAC: 0xD8, 0xB0: 0xB0, 0xB1: 0xB1, 0x223C: 0x7E, 0x2245: 0x40,
    0x2212: 0x2D, 0x210F: ord("h"),
}


def _rgba(colour) -> tuple[int, int, int, int]:
    c = tuple(colour)
    return (int(c[0]), int(c[1]), int(c[2]), int(c[3]) if len(c) > 3 else 255)


def _fmt(v: float) -> str:
    """A number for a vector file: short, and never ``-0``."""
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class VectorPainter:
    """Records the painter contract as shapes; subclasses serialise them.

    Parameters
    ----------
    width, height : float
        Page size in logical pixels.
    background : colour or None
        Filled under everything; ``None`` leaves the page transparent.
    """

    def __init__(self, width: float, height: float, background=(255, 255, 255, 255)):
        from .font import load_atlas

        self.width, self.height = float(width), float(height)
        self.background = None if background is None else _rgba(background)
        self._atlas = load_atlas()
        self._font_scale = 1.0
        self._clips: list[tuple[float, float, float, float]] = []
        #: ``(kind, clip, payload)`` in drawing order. ``clip`` is the clip
        #: rectangle in force, or ``None``.
        self.ops: list[tuple[str, Any, Any]] = []

    def reset(self) -> None:
        """Forget what was drawn (a settling frame), keep the page."""
        self.ops.clear()
        self._clips.clear()
        self._font_scale = 1.0

    # -- metrics (PixelPainter's) ------------------------------------------
    def _text_scale(self) -> float:
        return self._font_scale

    def text_width(self, string: str) -> float:
        return self._atlas.advance(string) * self._text_scale()

    def line_height(self) -> float:
        return self._atlas.line_height * self._text_scale()

    def set_font_scale(self, scale: float) -> None:
        self._font_scale = float(scale)

    # -- recording -----------------------------------------------------------
    def _clip(self):
        return self._clips[-1] if self._clips else None

    def _add(self, kind: str, payload) -> None:
        self.ops.append((kind, self._clip(), payload))

    def push_clip(self, x, y, w, h) -> None:
        x, y, w, h = float(x), float(y), max(float(w), 0.0), max(float(h), 0.0)
        if self._clips:
            cx, cy, cw, ch = self._clips[-1]
            x0, y0 = max(x, cx), max(y, cy)
            x1, y1 = min(x + w, cx + cw), min(y + h, cy + ch)
            x, y, w, h = x0, y0, max(x1 - x0, 0.0), max(y1 - y0, 0.0)
        self._clips.append((x, y, w, h))

    def pop_clip(self) -> None:
        if self._clips:
            self._clips.pop()

    def fill_rect(self, x, y, w, h, colour) -> None:
        if w <= 0 or h <= 0:
            return
        self._add("rect", ((float(x), float(y), float(w), float(h)), _rgba(colour)))

    def stroke_rect(self, x, y, w, h, edge, fill=None, *, width=1.0) -> None:
        if fill is not None:
            self.fill_rect(x, y, w, h, fill)
        width = max(0.0, min(float(width), w / 2, h / 2))
        if width == 0:
            return
        # Centre the stroke inside the box, as the raster painters do.
        self._add("rect_stroke", ((float(x) + width / 2, float(y) + width / 2,
                                  float(w) - width, float(h) - width), _rgba(edge), width))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        stops = list(stops)
        if not stops:
            return
        if isinstance(stops[0], tuple) and len(stops[0]) == 2 and not isinstance(stops[0][0], int):
            pts = [(float(t), _rgba(c)) for t, c in stops]
        else:
            n = max(len(stops) - 1, 1)
            pts = [(i / n, _rgba(c)) for i, c in enumerate(stops)]
        self._add("gradient", ((float(x), float(y), float(w), float(h)), pts))
        if edge is not None:
            self.stroke_rect(x, y, w, h, edge)

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        self._add("fill", ([tuple(map(float, p0)), tuple(map(float, p1)),
                            tuple(map(float, p2))], _rgba(colour)))

    def fill_convex(self, points, colour) -> None:
        pts = [(float(px), float(py)) for px, py in points]
        if len(pts) >= 3:
            self._add("fill", (pts, _rgba(colour)))

    def fill_triangles(self, triangles, colour) -> None:
        rgba = _rgba(colour)
        for tri in triangles:
            self._add("fill", ([(float(t[0]), float(t[1])) for t in tri], rgba))

    def polyline(self, points, width, colour, closed=False) -> None:
        pts = [(float(px), float(py)) for px, py in points]
        if len(pts) >= 2:
            self._add("stroke", (pts, float(width), _rgba(colour), bool(closed)))

    def gradient_triangle(self, p0, p1, p2, c0, c1, c2) -> None:
        subdivide_gradient(self.fill_triangle, p0, p1, p2, c0, c1, c2)

    def image(self, x, y, w, h, handle, uv0=(0.0, 0.0), uv1=(1.0, 1.0),
              tint=(255, 255, 255, 255)) -> None:
        from .texture import Texture

        if not isinstance(handle, Texture):
            self.fill_rect(x, y, w, h, tint)
            return
        crop = _crop(handle, uv0, uv1)
        if crop is None:
            return
        cw, ch, px = crop
        self._add("image", ((float(x), float(y), float(w), float(h)), cw, ch, px,
                            getattr(handle, "filter", "linear") == "nearest"))

    # -- text ------------------------------------------------------------------
    def _layout(self, x, y, w, h, align, string):
        """``(pen_x, baseline, advance, font_size)`` as PixelPainter places it."""
        atlas = self._atlas
        scale = self._text_scale()
        shrink = atlas.render_scale * scale
        advance = atlas.advance() * scale
        span = advance * len(string)
        pen_x = (x + w - span if align & ALIGN_RIGHT
                 else x + (w - span) * 0.5 if align & ALIGN_HCENTER else x)
        ascent, pad, cell_h = atlas.ascent, atlas.pad, atlas.cell[1]
        baseline = (y + h * 0.5 + (ascent - (cell_h - 2 * pad) * 0.5) * shrink
                    if align & ALIGN_VCENTER else y + ascent * shrink)
        return pen_x, baseline, advance, advance / _COURIER_ADVANCE

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        if not string:
            return
        pen_x, baseline, advance, size = self._layout(x, y, w, h, align, string)
        self._add("text", (pen_x, baseline, advance, size, str(string), _rgba(colour),
                           bool(bold), 0.0, None))

    def text_rotated(self, x, y, w, h, align, string, colour, degrees: float = 0.0) -> None:
        if not string:
            return
        pen_x, baseline, advance, size = self._layout(x, y, w, h, align, string)
        centre = (float(x) + float(w) * 0.5, float(y) + float(h) * 0.5)
        self._add("text", (pen_x, baseline, advance, size, str(string), _rgba(colour),
                           False, float(degrees), centre))


def _crop(texture, uv0, uv1):
    """The ``uv`` window of a texture as ``(w, h, RGBA bytes)``; ``None`` if empty."""
    tw, th = texture.width, texture.height
    u0, v0 = uv0
    u1, v1 = uv1
    x0, x1 = sorted((int(round(u0 * tw)), int(round(u1 * tw))))
    y0, y1 = sorted((int(round(v0 * th)), int(round(v1 * th))))
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, tw), min(y1, th)
    if x1 <= x0 or y1 <= y0:
        return None
    src = bytes(texture.pixels) if hasattr(texture, "pixels") else bytes(texture.px)
    rows = []
    for row in range(y0, y1):
        start = (row * tw + x0) * 4
        rows.append(src[start:start + (x1 - x0) * 4])
    flip_x, flip_y = u1 < u0, v1 < v0
    if flip_y:
        rows.reverse()
    if flip_x:
        rows = [b"".join(r[i:i + 4] for i in range(len(r) - 4, -4, -4)) for r in rows]
    return x1 - x0, y1 - y0, b"".join(rows)


def _png(width: int, height: int, rgba: bytes) -> bytes:
    from .testing import png_encode

    return png_encode(width, height, rgba)


def _merged(ops):
    """Consecutive same-colour, same-clip fills as one polygon list.

    A filled band or a marker arrives as many triangles; one path per run is
    a file a viewer opens quickly and edits as one shape -- and adjacent
    triangles in one path do not show the hairline seams separate shapes do.
    """
    run = None
    for kind, clip, payload in ops:
        if kind == "fill":
            pts, colour = payload
            if run is not None and run[1] == clip and run[2] == colour:
                run[3].append(pts)
                continue
            if run is not None:
                yield run
            run = ["fills", clip, colour, [pts]]
            continue
        if run is not None:
            yield run
            run = None
        yield [kind, clip, payload]
    if run is not None:
        yield run


# =============================================================================
class SvgPainter(VectorPainter):
    """Writes what is drawn as an SVG document (:meth:`svg_bytes`)."""

    FONT_FAMILY = "Menlo, 'DejaVu Sans Mono', Consolas, 'Courier New', monospace"

    def svg_bytes(self) -> bytes:
        w, h = self.width, self.height
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{_fmt(w * 72 / PX_PER_INCH)}pt" height="{_fmt(h * 72 / PX_PER_INCH)}pt" '
            f'viewBox="0 0 {_fmt(w)} {_fmt(h)}">\n',
        ]
        clips: dict = {}
        defs: list[str] = []
        body: list[str] = []
        if self.background is not None:
            body.append(f'<rect width="{_fmt(w)}" height="{_fmt(h)}"{_svg_fill(self.background)}/>\n')
        gradients = 0
        for item in _merged(self.ops):
            kind, clip = item[0], item[1]
            attr = ""
            if clip is not None:
                if clip not in clips:
                    cid = f"c{len(clips)}"
                    clips[clip] = cid
                    x, y, cw, ch = clip
                    defs.append(f'<clipPath id="{cid}"><rect x="{_fmt(x)}" y="{_fmt(y)}" '
                                f'width="{_fmt(cw)}" height="{_fmt(ch)}"/></clipPath>\n')
                attr = f' clip-path="url(#{clips[clip]})"'
            if kind == "fills":
                colour, polys = item[2], item[3]
                d = "".join("M" + "L".join(f"{_fmt(px)} {_fmt(py)}" for px, py in poly) + "Z"
                            for poly in polys)
                body.append(f'<path d="{d}"{_svg_fill(colour)}{attr}/>\n')
            elif kind == "stroke":
                pts, width, colour, closed = item[2]
                tag = "polygon" if closed else "polyline"
                points = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in pts)
                body.append(f'<{tag} points="{points}" fill="none"{_svg_stroke(colour, width)} '
                            f'stroke-linejoin="round" stroke-linecap="butt"{attr}/>\n')
            elif kind == "rect":
                (x, y, rw, rh), colour = item[2]
                # Abutting cells (a heatmap, a colour bar): anti-aliased edges
                # leave a light seam between neighbours; crisp edges do not.
                crisp = ' shape-rendering="crispEdges"' if colour[3] == 255 else ""
                body.append(f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(rw)}" '
                            f'height="{_fmt(rh)}"{_svg_fill(colour)}{crisp}{attr}/>\n')
            elif kind == "rect_stroke":
                (x, y, rw, rh), colour, width = item[2]
                body.append(f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(rw)}" '
                            f'height="{_fmt(rh)}" fill="none"{_svg_stroke(colour, width)}{attr}/>\n')
            elif kind == "gradient":
                (x, y, gw, gh), stops = item[2]
                gid = f"g{gradients}"
                gradients += 1
                defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
                            + "".join(f'<stop offset="{_fmt(t)}" stop-color="{_hex(c)}"'
                                      + (f' stop-opacity="{_fmt(c[3] / 255)}"' if c[3] < 255 else "")
                                      + "/>" for t, c in stops)
                            + "</linearGradient>\n")
                body.append(f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(gw)}" '
                            f'height="{_fmt(gh)}" fill="url(#{gid})"{attr}/>\n')
            elif kind == "image":
                (x, y, iw, ih), pw, ph, px, nearest = item[2]
                data = base64.b64encode(_png(pw, ph, px)).decode("ascii")
                style = ' style="image-rendering:pixelated"' if nearest else ""
                body.append(f'<image x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(iw)}" '
                            f'height="{_fmt(ih)}" preserveAspectRatio="none"{style} '
                            f'href="data:image/png;base64,{data}"{attr}/>\n')
            elif kind == "text":
                pen_x, baseline, advance, size, string, colour, bold, degrees, centre = item[2]
                rot = ""
                if degrees and centre is not None:
                    # PixelPainter turns positive degrees clockwise on the y-down page,
                    # which is SVG's own sense.
                    rot = f' transform="rotate({_fmt(degrees)} {_fmt(centre[0])} {_fmt(centre[1])})"'
                weight = ' font-weight="bold"' if bold else ""
                element = (
                    f'<text x="{_fmt(pen_x)}" y="{_fmt(baseline)}" font-family="{self.FONT_FAMILY}" '
                    f'font-size="{_fmt(size)}"{weight} textLength="{_fmt(advance * len(string))}" '
                    f'lengthAdjust="spacingAndGlyphs" xml:space="preserve"{_svg_fill(colour)}'
                    f'{rot}\x00>{_xml(string)}</text>')
                if rot and attr:
                    # A clip-path is read in the element's own (here rotated)
                    # coordinates: clip a group instead, so it stays the page's.
                    body.append(f"<g{attr}>{element.replace(chr(0), '', 1)}</g>\n")
                else:
                    body.append(element.replace(chr(0), attr, 1) + "\n")
        if defs:
            out.append("<defs>\n" + "".join(defs) + "</defs>\n")
        out.extend(body)
        out.append("</svg>\n")
        return "".join(out).encode("utf-8")


def _hex(c) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def _svg_fill(c) -> str:
    alpha = f' fill-opacity="{_fmt(c[3] / 255)}"' if c[3] < 255 else ""
    return f' fill="{_hex(c)}"{alpha}'


def _svg_stroke(c, width: float) -> str:
    alpha = f' stroke-opacity="{_fmt(c[3] / 255)}"' if c[3] < 255 else ""
    return f' stroke="{_hex(c)}" stroke-width="{_fmt(width)}"{alpha}'


def _xml(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# =============================================================================
class PdfPainter(VectorPainter):
    """Writes what is drawn as a one-page PDF (:meth:`pdf_bytes`)."""

    def pdf_bytes(self) -> bytes:
        h = self.height
        ops: list[str] = ["q", f"{_fmt(_PT)} 0 0 {_fmt(-_PT)} 0 {_fmt(h * _PT)} cm"]
        alphas: dict[int, str] = {}
        images: list[tuple[str, int, int, bytes, bool]] = []

        def gs(a: int) -> str:
            if a >= 255:
                return ""
            if a not in alphas:
                alphas[a] = f"GA{len(alphas)}"
            return f"/{alphas[a]} gs "

        def rgb(c) -> str:
            return f"{_fmt(c[0] / 255)} {_fmt(c[1] / 255)} {_fmt(c[2] / 255)}"

        if self.background is not None:
            ops.append(f"{gs(self.background[3])}{rgb(self.background)} rg 0 0 "
                       f"{_fmt(self.width)} {_fmt(h)} re f")
        # The clip lives in the graphics state, which only Q can undo: each
        # change of clip closes the state and reopens it with the page
        # transform and the new clip.
        unset = object()
        current_clip = unset
        for item in _merged(self.ops):
            kind, clip = item[0], item[1]
            if clip != current_clip:
                if current_clip is not unset or clip is not None:
                    ops.append("Q q")
                    ops.append(f"{_fmt(_PT)} 0 0 {_fmt(-_PT)} 0 {_fmt(h * _PT)} cm")
                    if clip is not None:
                        x, y, cw, ch = clip
                        ops.append(f"{_fmt(x)} {_fmt(y)} {_fmt(cw)} {_fmt(ch)} re W n")
                current_clip = clip
            if kind == "fills":
                colour, polys = item[2], item[3]
                path = " ".join(
                    f"{_fmt(poly[0][0])} {_fmt(poly[0][1])} m "
                    + " ".join(f"{_fmt(px)} {_fmt(py)} l" for px, py in poly[1:]) + " h"
                    for poly in polys)
                ops.append(f"q {gs(colour[3])}{rgb(colour)} rg {path} f Q")
            elif kind == "stroke":
                pts, width, colour, closed = item[2]
                path = (f"{_fmt(pts[0][0])} {_fmt(pts[0][1])} m "
                        + " ".join(f"{_fmt(px)} {_fmt(py)} l" for px, py in pts[1:])
                        + (" h" if closed else ""))
                ops.append(f"q {gs(colour[3])}{rgb(colour)} RG {_fmt(width)} w 1 j 0 J {path} S Q")
            elif kind == "rect":
                (x, y, rw, rh), colour = item[2]
                box = f"{_fmt(x)} {_fmt(y)} {_fmt(rw)} {_fmt(rh)} re"
                if colour[3] == 255:
                    # Fill and stroke in the fill colour, as a pcolormesh is
                    # written: the hairline closes the anti-aliasing seam
                    # between abutting cells. Opaque only -- a translucent
                    # edge would be painted twice.
                    ops.append(f"q {rgb(colour)} rg {rgb(colour)} RG 0.35 w {box} B Q")
                else:
                    ops.append(f"q {gs(colour[3])}{rgb(colour)} rg {box} f Q")
            elif kind == "rect_stroke":
                (x, y, rw, rh), colour, width = item[2]
                ops.append(f"q {gs(colour[3])}{rgb(colour)} RG {_fmt(width)} w "
                           f"{_fmt(x)} {_fmt(y)} {_fmt(rw)} {_fmt(rh)} re S Q")
            elif kind == "gradient":
                (x, y, gw, gh), stops = item[2]
                # Bands, one per stop interval, 32 steps across the rectangle.
                steps = 32
                for k in range(steps):
                    t = (k + 0.5) / steps
                    c = _sample(stops, t)
                    ops.append(f"q {gs(c[3])}{rgb(c)} rg {_fmt(x + gw * k / steps)} {_fmt(y)} "
                               f"{_fmt(gw / steps + 0.05)} {_fmt(gh)} re f Q")
            elif kind == "image":
                (x, y, iw, ih), pw, ph, px, nearest = item[2]
                name = f"Im{len(images)}"
                images.append((name, pw, ph, px, nearest))
                # Image space is the unit square with y up; this page is y down.
                ops.append(f"q {_fmt(iw)} 0 0 {_fmt(-ih)} {_fmt(x)} {_fmt(y + ih)} cm /{name} Do Q")
            elif kind == "text":
                pen_x, baseline, advance, size, string, colour, bold, degrees, centre = item[2]
                ops.append(self._pdf_text(pen_x, baseline, advance, size, string, colour,
                                          degrees, centre, gs(colour[3]) + rgb(colour)))
        ops.append("Q")
        content = "\n".join(o for o in ops if o).encode("latin-1")
        return _pdf_document(self.width * _PT, h * _PT, content, alphas, images)

    def _pdf_text(self, pen_x, baseline, advance, size, string, colour, degrees, centre,
                  fill) -> str:
        """Courier for what WinAnsi covers, Symbol for Greek and math, per run."""
        parts = [f"q {fill} rg"]
        if degrees and centre is not None:
            # Clockwise on the y-down page for positive degrees, as PixelPainter.
            a = math.radians(degrees)
            ca, sa = math.cos(a), math.sin(a)
            cx, cy = centre
            parts.append(f"1 0 0 1 {_fmt(cx)} {_fmt(cy)} cm {_fmt(ca)} {_fmt(sa)} {_fmt(-sa)} "
                         f"{_fmt(ca)} 0 0 cm 1 0 0 1 {_fmt(-cx)} {_fmt(-cy)} cm")
        parts.append("BT")
        for index, run_font, run in _runs(string):
            x = pen_x + index * advance
            # Text space is y up; flip back so glyphs stand upright on this page.
            # Courier's advance is 0.6 em and the size was chosen so that is
            # exactly the layout's advance: a Courier run needs no spacing.
            parts.append(f"/{run_font} {_fmt(size)} Tf 1 0 0 -1 {_fmt(x)} {_fmt(baseline)} Tm "
                         f"({_pdf_string(run)}) Tj")
        parts.append("ET Q")
        return " ".join(parts)


def _runs(string: str):
    """``(start index, font, encoded text)`` runs: F1 Courier, F2 Symbol."""
    out = []
    for i, ch in enumerate(string):
        if ord(ch) in _SYMBOL_CODES:
            font, code = "F2", chr(_SYMBOL_CODES[ord(ch)])
        else:
            try:
                code = ch.encode("cp1252").decode("latin-1")
                font = "F1"
            except UnicodeEncodeError:
                font, code = "F1", "?"
        if font == "F2":
            out.append((i, font, code))  # Symbol is proportional: one glyph per run
        elif out and out[-1][1] == "F1" and out[-1][0] + len(out[-1][2]) == i:
            out[-1] = (out[-1][0], "F1", out[-1][2] + code)
        else:
            out.append((i, font, code))
    return out


def _pdf_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _sample(stops, t: float):
    if t <= stops[0][0]:
        return stops[0][1]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(c0[k] + (c1[k] - c0[k]) * f)) for k in range(4))
    return stops[-1][1]


def _pdf_document(width_pt, height_pt, content: bytes, alphas: dict, images: list) -> bytes:
    """A minimal PDF 1.4: one page, two base-14 fonts, alpha states, images."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    def stream(dictionary: str, data: bytes) -> bytes:
        packed = zlib.compress(data)
        return (f"<< {dictionary} /Filter /FlateDecode /Length {len(packed)} >>\nstream\n"
                .encode("latin-1") + packed + b"\nendstream")

    catalog = add(b"")  # placeholders, filled once the ids are known
    pages = add(b"")
    courier = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    symbol = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Symbol >>")
    gs_ids = {name: add(f"<< /Type /ExtGState /ca {_fmt(a / 255)} /CA {_fmt(a / 255)} >>"
                         .encode("latin-1")) for a, name in alphas.items()}
    image_ids = {}
    for name, pw, ph, px, nearest in images:
        rgb = bytes(b for i in range(0, len(px), 4) for b in px[i:i + 3])
        alpha = px[3::4]
        interp = "false" if nearest else "true"
        smask = add(stream(f"/Type /XObject /Subtype /Image /Width {pw} /Height {ph} "
                           f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Interpolate {interp}",
                           bytes(alpha)))
        image_ids[name] = add(stream(f"/Type /XObject /Subtype /Image /Width {pw} /Height {ph} "
                                     f"/ColorSpace /DeviceRGB /BitsPerComponent 8 "
                                     f"/Interpolate {interp} /SMask {smask} 0 R", rgb))
    contents = add(stream("", content))
    resources = (f"<< /Font << /F1 {courier} 0 R /F2 {symbol} 0 R >>"
                 + (" /ExtGState << " + " ".join(f"/{n} {i} 0 R" for n, i in gs_ids.items()) + " >>"
                    if gs_ids else "")
                 + (" /XObject << " + " ".join(f"/{n} {i} 0 R" for n, i in image_ids.items()) + " >>"
                    if image_ids else "")
                 + " >>")
    page = add(f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {_fmt(width_pt)} "
               f"{_fmt(height_pt)}] /Resources {resources} /Contents {contents} 0 R >>"
               .encode("latin-1"))
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages} 0 R >>".encode("latin-1")
    objects[pages - 1] = f"<< /Type /Pages /Kids [{page} 0 R] /Count 1 >>".encode("latin-1")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
    return bytes(out)
