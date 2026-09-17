"""The painter contract on Pillow: a window-sized frame, fast enough to live in.

Why this exists
---------------
:class:`~.testing.PixelPainter` proved the interface can be drawn with no
toolkit at all -- every glyph from the baked atlas, every rectangle into a
byte buffer. It is also pure Python per pixel, which is right for a golden
image and wrong for a window: a 1080x720 application frame costs over a
second. A host that owns no GPU and no Qt still needs *frames*.

Pillow already is the per-pixel loop, in C. This painter keeps
``PixelPainter``'s semantics -- the same atlas glyphs, the same clip rule,
the same colours -- and hands the inner loops to Pillow: a rectangle is one
``ImageDraw`` call, a glyph is one masked ``paste`` of a cell that was box-
filtered down once and cached. The result is what :mod:`.tk_host` presents,
and it is identical on every machine for the same reason the screenshot
painter is: nothing here asks the platform for a font.

What is not accelerated
-----------------------
``gradient_triangle``, ``image_triangle`` and ``text_rotated`` are drawn by
``PixelPainter`` itself on a scratch buffer the size of the shape's clipped
bounding box, then pasted back. They are rare in an application frame (plots,
3-D meshes), and borrowing the reference implementation means they cannot
disagree with it.

Pillow is imported on construction, not at module scope, so importing this
module never pulls a dependency into a process that does not draw.
"""
from __future__ import annotations

import math

from .font import load_atlas
from .painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER

__all__ = ["PilPainter"]

#: Glyph masks, box-filtered from the baked atlas once per (cell, scale).
#: Module level because every frame builds a new painter.
_GLYPHS: dict = {}
#: The atlas alpha channel as a Pillow image, decoded once.
_ATLAS: dict = {}


def _pil():
    from PIL import Image, ImageDraw  # noqa: PLC0415

    return Image, ImageDraw


def _rgba(colour):
    """RGB or RGBA tuples both arrive; RGBA leaves, alpha defaults on."""
    if len(colour) == 3:
        return (int(colour[0]), int(colour[1]), int(colour[2]), 255)
    return (int(colour[0]), int(colour[1]), int(colour[2]), int(colour[3]))


class PilPainter:
    """Draw into an RGB :class:`PIL.Image.Image` of ``width`` x ``height``.

    Parameters
    ----------
    width, height : int
        Frame size in pixels.
    background : tuple, optional
        Filled first. The frame is opaque: a window has nothing behind it.
    scale : float, optional
        Text scale, as :class:`~.testing.PixelPainter` takes it.
    frame : PIL.Image.Image, optional
        Draw into this RGB image instead of a new one -- a host reuses its
        frame rather than allocating one per paint.

    Attributes
    ----------
    frame : PIL.Image.Image
        The frame. Not ``image``: that name is the optional operation, and an
        attribute spelled the same hides it -- ``painter_capabilities`` then
        reports no image support and every picture becomes a tinted box.
    """

    def __init__(self, width: int, height: int, background=(0, 0, 0, 255),
                 scale: float = 1.0, frame=None) -> None:
        Image, ImageDraw = _pil()
        self.width, self.height = int(width), int(height)
        if frame is None or frame.size != (self.width, self.height) or frame.mode != "RGB":
            frame = Image.new("RGB", (self.width, self.height))
        self.frame = frame
        # "RGBA" ink on an RGB image is Pillow's blending mode: a translucent
        # fill composites in C instead of replacing the pixels.
        self._draw = ImageDraw.Draw(frame, "RGBA")
        self.frame.paste(_rgba(background)[:3], (0, 0, self.width, self.height))
        self.scale = float(scale)
        self._font_scale = 1.0
        self._clips = [(0, 0, self.width, self.height)]
        self._atlas = load_atlas()

    # -- plumbing ---------------------------------------------------------- #

    @property
    def px(self) -> bytearray:
        """The frame as RGBA bytes, the layout :func:`~.testing.save_png` takes."""
        return bytearray(self.frame.convert("RGBA").tobytes())

    def _clip(self):
        return self._clips[-1]

    def push_clip(self, x, y, w, h) -> None:
        """Intersect with the current clip, in whole pixels (``PixelPainter``'s rule)."""
        cx, cy, cw, ch = self._clip()
        x0, y0 = max(int(x), cx), max(int(y), cy)
        x1, y1 = min(int(x + w), cx + cw), min(int(y + h), cy + ch)
        self._clips.append((x0, y0, max(0, x1 - x0), max(0, y1 - y0)))

    def pop_clip(self) -> None:
        if len(self._clips) > 1:
            self._clips.pop()

    def _clipped(self, x0, y0, x1, y1):
        """Pixel box ``[x0, x1) x [y0, y1)`` cut to the clip, or ``None``."""
        cx, cy, cw, ch = self._clip()
        x0, y0 = max(x0, cx), max(y0, cy)
        x1, y1 = min(x1, cx + cw), min(y1, cy + ch)
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1, y1

    def _fill(self, x, y, w, h, colour) -> None:
        box = self._clipped(int(x), int(y), int(x + w), int(y + h))
        if box is None:
            return
        rgba = _rgba(colour)
        if rgba[3] == 0:
            return
        x0, y0, x1, y1 = box
        if rgba[3] == 255:
            self.frame.paste(rgba[:3], box)
        else:
            self._draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=rgba)

    # -- the required operations ------------------------------------------- #

    def fill_rect(self, x, y, w, h, colour) -> None:
        self._fill(x, y, w, h, colour)

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        if fill is not None:
            self._fill(x, y, w, h, fill)
        self._fill(x, y, w, 1.0, edge)
        self._fill(x, y + h - 1.0, w, 1.0, edge)
        self._fill(x, y, 1.0, h, edge)
        self._fill(x + w - 1.0, y, 1.0, h, edge)

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        """Left-to-right gradient through evenly spaced (or ``(t, colour)``) stops."""
        box = self._clipped(int(x), int(y), int(x + w), int(y + h))
        if box is None or not stops:
            return
        Image, _ = _pil()
        if not (len(stops[0]) == 2 and isinstance(stops[0][1], (tuple, list))):
            n = max(len(stops) - 1, 1)
            stops = [(k / n, c) for k, c in enumerate(stops)]
        pts = [(float(t), _rgba(c)) for t, c in stops]
        x0, y0, x1, y1 = box
        span = max(1.0, float(w))
        row = bytearray()
        for xx in range(x0, x1):
            t = (xx - x) / span
            lo, hi = pts[0], pts[-1]
            for k in range(len(pts) - 1):
                if pts[k][0] <= t <= pts[k + 1][0]:
                    lo, hi = pts[k], pts[k + 1]
                    break
            f = max(0.0, min(1.0, (t - lo[0]) / ((hi[0] - lo[0]) or 1.0)))
            row.extend(int(lo[1][i] + (hi[1][i] - lo[1][i]) * f) for i in range(4))
        strip = Image.frombytes("RGBA", (x1 - x0, 1), bytes(row)).resize((x1 - x0, y1 - y0))
        self.frame.paste(strip.convert("RGB"), (x0, y0), strip.getchannel("A"))
        if edge is not None:
            self.stroke_rect(x, y, w, h, edge)

    def _polygon(self, points, colour) -> None:
        """Fill a convex polygon: pixel centres inside or on an edge, one span per row.

        Not ``ImageDraw.polygon``. Pillow's fill also sets every pixel an edge
        passes through, so a line drawn as two thin triangles came out a pixel
        fatter than on every other painter (a checkmark visibly bolder), and it
        cannot clip. The pixel-centre rule is ``PixelPainter``'s, which is what
        makes the two agree; the Python cost is a loop over *rows*, while the
        pixels of each row are one C fill.
        """
        rgba = _rgba(colour)
        if rgba[3] == 0 or len(points) < 3:
            return
        pts = [(float(px), float(py)) for px, py in points]
        ys = [p[1] for p in pts]
        cx, cy, cw, ch = self._clip()
        row0 = max(math.ceil(min(ys) - 0.5), cy)
        row1 = min(math.floor(max(ys) - 0.5), cy + ch - 1)
        if row1 < row0:
            return
        edges = list(zip(pts, pts[1:] + pts[:1]))
        opaque = rgba[3] == 255
        left_clip, right_clip = cx, cx + cw - 1
        for row in range(row0, row1 + 1):
            fy = row + 0.5
            lo, hi = math.inf, -math.inf
            for (ax, ay), (bx, by) in edges:
                if (ay <= fy <= by) or (by <= fy <= ay):
                    if ay == by:
                        lo, hi = min(lo, ax, bx), max(hi, ax, bx)
                    else:
                        ex = ax + (fy - ay) * (bx - ax) / (by - ay)
                        lo, hi = min(lo, ex), max(hi, ex)
            if hi < lo:
                continue
            first = max(math.ceil(lo - 0.5), left_clip)
            last = min(math.floor(hi - 0.5), right_clip)
            if last < first:
                continue
            if opaque:
                self.frame.paste(rgba[:3], (first, row, last + 1, row + 1))
            else:
                self._draw.rectangle((first, row, last, row), fill=rgba)

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        (x0, y0), (x1, y1), (x2, y2) = p0, p1, p2
        if (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2) == 0:
            return
        self._polygon((p0, p1, p2), colour)

    def fill_convex(self, points, colour) -> None:
        """One polygon instead of a fan: no seams where translucent fans overlap."""
        self._polygon([(float(px), float(py)) for px, py in points], colour)

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        """Paste atlas glyphs, each box-filtered to the screen once and cached."""
        if not string:
            return
        atlas = self._atlas
        scale = self.scale * self._font_scale
        shrink = atlas.render_scale * scale
        if shrink <= 0.0:
            return
        rgba = _rgba(colour)
        if rgba[3] == 0:
            return
        advance = atlas.advance() * scale
        span = advance * len(string)
        pen_x = (x + w - span if align & ALIGN_RIGHT
                 else x + (w - span) * 0.5 if align & ALIGN_HCENTER else x)
        ascent, pad, cell_h = atlas.ascent, atlas.pad, atlas.cell[1]
        baseline = (y + h * 0.5 + (ascent - cell_h * 0.5) * shrink
                    if align & ALIGN_VCENTER else y + ascent * shrink)
        top = int(baseline - (ascent + pad) * shrink)
        left = pen_x - pad * shrink
        cx, cy, cw, ch = self._clip()
        if top >= cy + ch:
            return
        for index, char in enumerate(string):
            if char == " ":
                continue
            gx = int(left + index * advance)
            if gx >= cx + cw:
                break
            mask = self._glyph(char, bold, shrink, rgba[3])
            if mask is None:
                continue
            mw, mh = mask.size
            box = self._clipped(gx, top, gx + mw, top + mh)
            if box is None:
                continue
            bx0, by0, bx1, by1 = box
            if (bx1 - bx0, by1 - by0) != (mw, mh):
                mask = mask.crop((bx0 - gx, by0 - top, bx1 - gx, by1 - top))
            self.frame.paste(rgba[:3], box, mask)

    def _glyph(self, char, bold, shrink, alpha):
        """The screen-sized coverage mask of *char*, or ``None`` if it has no cell."""
        atlas = self._atlas
        cell = atlas.cell_of(char, bold=bold)
        if cell is None:
            return None
        u, v, gw, gh = cell
        dynamic = v >= atlas.baked_height
        version = atlas.cache.version if dynamic and atlas.cache is not None else 0
        key = (u, v, gw, gh, round(shrink, 4), alpha, version)
        got = _GLYPHS.get(key)
        if got is not None:
            return got
        Image, _ = _pil()
        source = self._source(dynamic)
        if source is None:
            return None
        if dynamic:
            v -= atlas.baked_height
        size = (max(1, math.ceil(gw * shrink)), max(1, math.ceil(gh * shrink)))
        mask = source.crop((u, v, u + gw, v + gh)).resize(size, Image.BOX)
        if alpha != 255:
            mask = mask.point(lambda c: c * alpha // 255)
        if len(_GLYPHS) > 4096:
            _GLYPHS.clear()
        _GLYPHS[key] = mask
        return mask

    def _source(self, dynamic):
        """Atlas alpha as an ``L`` image: the baked half, or the runtime cache's rows."""
        Image, _ = _pil()
        if not dynamic:
            if "baked" not in _ATLAS:
                with Image.open(self._atlas.image_path) as img:
                    _ATLAS["baked"] = img.convert("RGBA").getchannel("A")
            return _ATLAS["baked"]
        from .testing import _cache_pixels  # noqa: PLC0415

        got = _cache_pixels(self._atlas.cache)
        if got is None:
            return None
        rgba, width = got
        height = len(rgba) // (4 * width)
        return Image.frombytes("RGBA", (width, height), rgba).getchannel("A")

    def text_width(self, string) -> float:
        return self._atlas.advance(string) * self.scale * self._font_scale

    def line_height(self) -> float:
        return self._atlas.line_height * self.scale * self._font_scale

    def set_font_scale(self, scale: float) -> None:
        """Scale the glyph cell on top of the device scale."""
        self._font_scale = float(scale)

    # -- optional operations ----------------------------------------------- #

    def set_font(self, _spec) -> None:
        """Font pushes are ignored: the atlas is the one size there is."""

    def image(self, x, y, w, h, handle, uv0=(0.0, 0.0), uv1=(1.0, 1.0),
              tint=(255, 255, 255, 255)) -> None:
        """Draw a :class:`~.texture.Texture` into the box, nearest texel, tinted.

        Any other handle is opaque and becomes a box of *tint*, as in every
        painter.
        """
        from .texture import Texture  # noqa: PLC0415

        if not isinstance(handle, Texture):
            self._fill(x, y, w, h, tint)
            return
        dx0, dy0, dx1, dy1 = int(x), int(y), int(x + w), int(y + h)
        box = self._clipped(dx0, dy0, dx1, dy1)
        if box is None:
            return
        Image, _ = _pil()
        src = self._texture(handle)
        tw, th = handle.width, handle.height
        # Source rectangle in texels; flipped uvs mirror, as they do on a GPU.
        su0, su1 = uv0[0] * tw, uv1[0] * tw
        sv0, sv1 = uv0[1] * th, uv1[1] * th
        region = src.transform(
            (dx1 - dx0, dy1 - dy0), Image.EXTENT, (su0, sv0, su1, sv1), Image.NEAREST)
        tint = _rgba(tint)
        if tint != (255, 255, 255, 255):
            from PIL import ImageChops  # noqa: PLC0415

            region = ImageChops.multiply(region, Image.new("RGBA", region.size, tint))
        bx0, by0, bx1, by1 = box
        if (bx0, by0, bx1, by1) != (dx0, dy0, dx1, dy1):
            region = region.crop((bx0 - dx0, by0 - dy0, bx1 - dx0, by1 - dy0))
        self.frame.paste(region.convert("RGB"), (bx0, by0), region.getchannel("A"))

    @staticmethod
    def _texture(tex):
        """*tex* as a Pillow image, rebuilt only when its revision moves."""
        Image, _ = _pil()
        key = ("tex", id(tex))
        got = _GLYPHS.get(key)
        if got is None or got[0] is not tex or got[1] != tex.revision:
            got = (tex, tex.revision,
                   Image.frombytes("RGBA", (tex.width, tex.height), bytes(tex.px)))
            _GLYPHS[key] = got
        return got[2]

    def _via_pixels(self, xs, ys, draw) -> None:
        """Run *draw* on a :class:`~.testing.PixelPainter` over the clipped bbox.

        The scratch starts as a copy of the frame under the box and is pasted
        back, so blending sees the real destination.
        """
        box = self._clipped(int(min(xs)), int(min(ys)), int(max(xs)) + 1, int(max(ys)) + 1)
        if box is None:
            return
        from .testing import PixelPainter  # noqa: PLC0415

        Image, _ = _pil()
        x0, y0, x1, y1 = box
        scratch = PixelPainter.__new__(PixelPainter)
        scratch.width, scratch.height = x1 - x0, y1 - y0
        scratch.px = bytearray(self.frame.crop(box).convert("RGBA").tobytes())
        scratch.scale = self.scale
        scratch._clips = [(0, 0, scratch.width, scratch.height)]
        scratch._atlas = self._atlas
        scratch._font_scale = self._font_scale
        draw(scratch, x0, y0)
        patch = Image.frombytes("RGBA", (scratch.width, scratch.height), bytes(scratch.px))
        self.frame.paste(patch.convert("RGB"), (x0, y0))

    def gradient_triangle(self, p0, p1, p2, c0, c1, c2) -> None:
        pts = (p0, p1, p2)
        self._via_pixels(
            [p[0] for p in pts], [p[1] for p in pts],
            lambda s, ox, oy: s.gradient_triangle(
                *[(px - ox, py - oy) for px, py in pts], c0, c1, c2))

    def image_triangle(self, p0, p1, p2, handle, uv0=(0.0, 0.0),
                       uv1=(1.0, 0.0), uv2=(1.0, 1.0),
                       tint=(255, 255, 255, 255)) -> None:
        pts = (p0, p1, p2)
        self._via_pixels(
            [p[0] for p in pts], [p[1] for p in pts],
            lambda s, ox, oy: s.image_triangle(
                *[(px - ox, py - oy) for px, py in pts], handle, uv0, uv1, uv2, tint))

    def text_rotated(self, x, y, w, h, align, string, colour, degrees: float = 0.0) -> None:
        half = 0.5 * math.hypot(w, h) + 2.0
        ccx, ccy = x + w * 0.5, y + h * 0.5
        self._via_pixels(
            (ccx - half, ccx + half), (ccy - half, ccy + half),
            lambda s, ox, oy: s.text_rotated(
                x - ox, y - oy, w, h, align, string, colour, degrees))
