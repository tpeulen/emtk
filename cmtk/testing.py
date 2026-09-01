"""cmtk's own test doubles: a Painter that records, and fixed metrics.

The chisurf test dir carried :class:`RecordingPainter` (and ten earlier copies
of it); a widget library that ships without its own recorder makes every port's
first test start by writing one. It lives here now, importable from anywhere
cmtk is -- ``cmtk.testing.RecordingPainter`` -- and the tests import it
from here.

The metrics are deliberately round -- seven pixels a character, sixteen a line
-- so an expected position in a test is arithmetic a reader can do in their
head rather than a number that had to be measured.
"""
from __future__ import annotations

from .painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER  # noqa: E402

__all__ = [
    "RecordingPainter", "FIXED_GLYPH_W", "FIXED_LINE_H",
    "PixelPainter", "png_encode", "png_decode", "render",
    "screenshot", "save_png", "assert_images_equal",
]

FIXED_GLYPH_W = 7.0
FIXED_LINE_H = 16.0


class RecordingPainter:
    """Records the painter operations instead of performing them."""

    #: Advance width of one character, in pixels.
    GLYPH_W = 7.0
    #: Height of one line of text, in pixels.
    LINE_H = 16.0

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[str] = []
        self.texts: list[tuple] = []
        self.clips: list[tuple] = []
        self.triangles: list[tuple] = []
        #: Every operation, in call order, as ``(kind, *args)`` -- the
        #: per-kind lists above lose draw order *across* kinds (a fill and a
        #: triangle interleaved land in two separate lists with no shared
        #: index), which is exactly what "is X drawn over Y" needs. Kept
        #: alongside them rather than instead of them: most tests want "how
        #: many of this kind" and this list makes that a `len(x for ... if
        #: kind == ...)` instead of a plain `len`.
        self.calls: list[tuple] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        """Record a filled rectangle."""
        self.fills.append((x, y, w, h, colour))
        self.calls.append(("fill_rect", x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        """Record an outlined rectangle."""
        self.strokes.append((x, y, w, h, edge, fill))
        self.calls.append(("stroke_rect", x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        """Record a gradient as its first stop, which is what a test asserts on."""
        self.fills.append((x, y, w, h, stops[0] if stops else None))
        self.calls.append(("gradient_rect", x, y, w, h, stops, edge))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        """Record a string and, separately, everything about where it went."""
        self.strings.append(string)
        self.texts.append((x, y, w, h, align, string, colour, bold))
        self.calls.append(("text", x, y, w, h, align, string, colour, bold))

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        """Record a filled triangle."""
        self.triangles.append((p0, p1, p2, colour))
        self.calls.append(("fill_triangle", p0, p1, p2, colour))

    def push_clip(self, x, y, w, h) -> None:
        """Record a clip rectangle."""
        self.clips.append((x, y, w, h))
        self.calls.append(("push_clip", x, y, w, h))

    def pop_clip(self) -> None:
        """Drop the most recent clip rectangle."""
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        """Monospaced advance width."""
        return len(string) * self.GLYPH_W

    def line_height(self) -> float:
        """Height of one line."""
        return self.LINE_H


# --------------------------------------------------------------------------- #
# The screenshot painter: the six operations, rasterised in pure Python
# --------------------------------------------------------------------------- #
import struct as _struct
import zlib as _zlib

from .font import load_atlas as _load_atlas  # noqa: E402

_ATLAS_PIXELS: dict = {}


def _atlas_pixels():
    """The baked atlas, decoded once: ``(width, height, rgba)``."""
    if "px" not in _ATLAS_PIXELS:
        data = _load_atlas().image_path.read_bytes()
        w, h, px = png_decode(data)
        _ATLAS_PIXELS["px"] = (w, h, px)
    return _ATLAS_PIXELS["px"]


#: The dynamic glyph cache's rows, flattened like the baked atlas and keyed
#: on the cache's ``version`` -- which it bumps for every glyph it stores, so
#: a character rasterised since the last call is present and the flattening
#: is paid once per new glyph rather than once per draw.
_CACHE_PIXELS: dict = {}


def _cache_pixels(cache):
    """``(rgba, width)`` for the runtime glyph cache, or ``None``.

    ``None`` when there is no cache -- rasterising needs a font library cmtk
    does not depend on, so a checkout without one draws the atlas's visible
    placeholder instead, which is the same thing every other painter does.
    """
    if cache is None:
        return None
    key = id(cache)
    got = _CACHE_PIXELS.get(key)
    if got is None or got[0] != cache.version:
        image = cache.image
        got = (cache.version, bytes(image.tobytes()), int(image.shape[1]))
        _CACHE_PIXELS[key] = got
    return got[1], got[2]


def png_encode(width: int, height: int, rgba) -> bytes:
    """Pack an RGBA buffer as a PNG (colour type 6, no filter)."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (_struct.pack(">I", len(payload)) + kind + payload
                + _struct.pack(">I", _zlib.crc32(kind + payload) & 0xFFFFFFFF))

    raw = b"".join(
        b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4])
        for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", _struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", _zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def png_decode(data: bytes):
    """Unpack a simple PNG (8-bit RGBA, all filter types) -> ``(w, h, rgba)``."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    width = height = None
    idat = b""
    while pos < len(data):
        (length,), kind = _struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, colour, _, _, interlace = _struct.unpack(
                ">IIBBBBB", payload)
            assert (depth, colour, interlace) == (8, 6, 0), "expected 8-bit RGBA"
        elif kind == b"IDAT":
            idat += payload
        pos += 12 + length
    raw = _zlib.decompress(idat)
    stride = width * 4
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ft = raw[pos]
        pos += 1
        row = bytearray(raw[pos:pos + stride])
        pos += stride
        if ft == 1:      # Sub
            for i in range(4, stride):
                row[i] = (row[i] + row[i - 4]) & 255
        elif ft == 2:    # Up
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif ft == 3:    # Average
            for i in range(stride):
                left = row[i - 4] if i >= 4 else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:    # Paeth
            for i in range(stride):
                a = row[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return width, height, out


def save_png(path, width: int, height: int, rgba) -> None:
    path = _pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_encode(width, height, rgba))


class PixelPainter:
    """The painter contract, rasterised onto an RGBA buffer.

    What the two shipped painters could not do -- draw in a test with no
    toolkit and no window -- this one does: it draws into memory a test can
    hash, diff or write out as a PNG. Pure standard library, so a screenshot
    pipeline needs no numpy and no Qt.

    Colours are RGBA tuples as everywhere in cmtk. Text is blitted from the
    baked atlas, so screenshots render real glyphs and are identical on every
    machine that runs the same commit.
    """

    def __init__(self, width: int, height: int,
                 background=(0, 0, 0, 255), scale: float = 1.0):
        self.width = int(width)
        self.height = int(height)
        self.px = bytearray(self.width * self.height * 4)
        self.scale = float(scale)
        # Before the fill, not after: `_fill` clips, so a background that is
        # not the all-zero fast path below reaches a painter with no clip
        # stack at all.
        self._clips = [(0, 0, self.width, self.height)]
        if tuple(background[:3]) != (0, 0, 0):
            self._fill(0, 0, self.width, self.height, background)
        else:
            for i in range(3, len(self.px), 4):
                self.px[i] = background[3]
        self._atlas = _load_atlas()

    # -- plumbing ---------------------------------------------------------- #

    def _clip(self):
        return self._clips[-1]

    @staticmethod
    def _rgba(colour):
        """RGB or RGBA tuples both arrive; RGBA leaves, alpha defaults on."""
        if len(colour) == 3:
            return (colour[0], colour[1], colour[2], 255)
        return tuple(colour)

    def push_clip(self, x, y, w, h) -> None:
        """Intersect with the current clip. Stored as whole pixels.

        Widget boxes arrive as floats; a clip is a range of pixels to write,
        and every consumer below indexes the buffer with it. Rounding once
        here beats each of them coercing -- and beats the bug that was: a
        float clip made ``range()`` raise from inside the glyph loop, but only
        once something had pushed a clip that was not the full canvas.
        """
        cx, cy, cw, ch = self._clip()
        x0, y0 = max(int(x), cx), max(int(y), cy)
        x1 = min(int(x + w), cx + cw)
        y1 = min(int(y + h), cy + ch)
        self._clips.append((x0, y0, max(0, x1 - x0), max(0, y1 - y0)))

    def pop_clip(self) -> None:
        if len(self._clips) > 1:
            self._clips.pop()

    def _fill(self, x, y, w, h, colour):
        cx, cy, cw, ch = self._clip()
        x0 = max(int(x), cx)
        y0 = max(int(y), cy)
        x1 = min(int(x + w), cx + cw)
        y1 = min(int(y + h), cy + ch)
        if x1 <= x0 or y1 <= y0:
            return
        r, g, b, a = self._rgba(colour)
        stride = self.width * 4
        for yy in range(y0, y1):
            base = yy * stride + x0 * 4
            for i in range(x0, x1):
                o = base + (i - x0) * 4
                sa = a / 255.0
                self.px[o] = int(r * sa + self.px[o] * (1 - sa))
                self.px[o + 1] = int(g * sa + self.px[o + 1] * (1 - sa))
                self.px[o + 2] = int(b * sa + self.px[o + 2] * (1 - sa))
                self.px[o + 3] = max(self.px[o + 3], a)

    # -- the six required operations --------------------------------------- #

    def fill_rect(self, x, y, w, h, colour) -> None:
        self._fill(x, y, w, h, colour)

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        edge = self._rgba(edge)
        if fill is not None:
            self._fill(x, y, w, h, fill)
        t = 1.0
        self._fill(x, y, w, t, edge)
        self._fill(x, y + h - t, w, t, edge)
        self._fill(x, y, t, h, edge)
        self._fill(x + w - t, y, t, h, edge)

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        cx, cy, cw, ch = self._clip()
        x0, x1 = max(int(x), cx), min(int(x + w), cx + cw)
        if x1 <= x0:
            return
        pts = [(float(t), self._rgba(c)) for t, c in stops]
        span = max(1.0, float(w))
        for xx in range(x0, x1):
            t = (xx - x) / span
            lo = pts[0]
            hi = pts[-1]
            for k in range(len(pts) - 1):
                if pts[k][0] <= t <= pts[k + 1][0]:
                    lo, hi = pts[k], pts[k + 1]
                    break
            span2 = (hi[0] - lo[0]) or 1.0
            f = max(0.0, min(1.0, (t - lo[0]) / span2))
            colour = tuple(int(lo[1][i] + (hi[1][i] - lo[1][i]) * f)
                           for i in range(4))
            self._fill(xx, y, 1, h, colour)

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        (x0, y0), (x1, y1), (x2, y2) = p0, p1, p2
        minx = max(int(min(x0, x1, x2)), self._clip()[0])
        maxx = min(int(max(x0, x1, x2)) + 1, self._clip()[0] + self._clip()[2])
        miny = max(int(min(y0, y1, y2)), self._clip()[1])
        maxy = min(int(max(y0, y1, y2)) + 1, self._clip()[1] + self._clip()[3])
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if den == 0:
            return
        r, g, b, a = self._rgba(colour)
        stride = self.width * 4
        for yy in range(miny, maxy):
            for xx in range(minx, maxx):
                fx, fy = xx + 0.5, yy + 0.5
                w0 = ((y1 - y2) * (fx - x2) + (x2 - x1) * (fy - y2)) / den
                w1 = ((y2 - y0) * (fx - x2) + (x0 - x2) * (fy - y2)) / den
                w2 = 1.0 - w0 - w1
                if w0 >= 0 and w1 >= 0 and w2 >= 0:
                    o = yy * stride + xx * 4
                    sa = a / 255.0
                    self.px[o] = int(r * sa + self.px[o] * (1 - sa))
                    self.px[o + 1] = int(g * sa + self.px[o + 1] * (1 - sa))
                    self.px[o + 2] = int(b * sa + self.px[o + 2] * (1 - sa))
                    self.px[o + 3] = max(self.px[o + 3], a)

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        """Blit *string* from the baked atlas, one glyph cell per character.

        Two things here are easy to get backwards, and getting either wrong
        gives text a screenshot is no use with.

        The first is the direction of :attr:`~cmtk.font.Atlas.render_scale`:
        it is logical pixels *per baked texel*, so texel measurements are
        multiplied by it, never divided. Dividing gives glyphs roughly four
        times too big, which is text that swallows the window.

        The second is the downsample. The atlas is baked at four times the
        point size precisely so a glyph can be filtered down to a screen
        pixel; taking the single nearest texel throws that away and gives the
        jagged edges the supersampling was paid for to avoid. So each
        destination pixel averages the texels it actually covers -- more
        arithmetic than a nearest lookup, but this painter draws documentation
        screenshots and golden images, not frames.
        """
        if not string:
            return
        atlas = self._atlas
        shrink = atlas.render_scale * self.scale
        if shrink <= 0.0:
            return
        advance = atlas.advance() * self.scale
        span = advance * len(string)
        pen_x = (x + w - span if align & ALIGN_RIGHT
                 else x + (w - span) * 0.5 if align & ALIGN_HCENTER else x)
        ascent, pad, cell_h = atlas.ascent, atlas.pad, atlas.cell[1]
        baseline = (y + h * 0.5 + (ascent - cell_h * 0.5) * shrink
                    if align & ALIGN_VCENTER else y + ascent * shrink)
        # The pen sits a fixed (pad, pad + ascent) inside every cell, so a
        # glyph's quad is the whole cell placed relative to the baseline and
        # no per-glyph bearing is needed -- the baker guarantees that, and
        # `quad_painter` places its quads the same way.
        top = baseline - (ascent + pad) * shrink
        left = pen_x - pad * shrink
        cx, cy, cw, ch = self._clip()
        r, g, b, a = self._rgba(colour)
        baked_w, _baked_h, baked = _atlas_pixels()
        stride = self.width * 4
        sa = a / 255.0
        texels = 1.0 / shrink          # baked texels covered by one pixel
        for index, char in enumerate(string):
            cell = atlas.cell_of(char, bold=bold)
            if cell is None:
                continue
            u, v, gw, gh = cell
            # Which half of the atlas this glyph is in. The baked rows are on
            # top and the runtime cache's rows sit under them, as one texture
            # -- `Atlas.cell_of` returns coordinates in that combined space,
            # and this painter was decoding only the baked PNG. So a character
            # the baker never saw (any accent, Greek, Cyrillic, CJK) sampled
            # past the end of the image: an IndexError where it ran off the
            # buffer, and silently the wrong glyph where it did not.
            if v < atlas.baked_height:
                src, src_w = baked, baked_w
            else:
                half = _cache_pixels(atlas.cache)
                if half is None:
                    continue
                src, src_w = half
                v -= atlas.baked_height
            x0 = left + index * advance
            gx0 = max(int(x0), cx)
            gy0 = max(int(top), cy)
            gx1 = min(int(x0 + gw * shrink) + 1, cx + cw)
            gy1 = min(int(top + gh * shrink) + 1, cy + ch)
            for yy in range(gy0, gy1):
                fy = (yy - top) * texels
                sy0 = v + (int(fy) if fy > 0.0 else 0)
                fy += texels
                sy1 = v + (gh if fy >= gh else int(fy) + 1)
                if sy1 <= sy0:
                    continue
                row = yy * stride
                for xx in range(gx0, gx1):
                    fx = (xx - x0) * texels
                    sx0 = u + (int(fx) if fx > 0.0 else 0)
                    fx += texels
                    sx1 = u + (gw if fx >= gw else int(fx) + 1)
                    if sx1 <= sx0:
                        continue
                    total = 0
                    for ty in range(sy0, sy1):
                        base = ty * src_w * 4 + 3
                        for tx in range(sx0, sx1):
                            total += src[base + tx * 4]
                    alpha = total / ((sy1 - sy0) * (sx1 - sx0))
                    if alpha < 0.5:
                        continue
                    o = row + xx * 4
                    s = sa * alpha / 255.0
                    self.px[o] = int(r * s + self.px[o] * (1 - s))
                    self.px[o + 1] = int(g * s + self.px[o + 1] * (1 - s))
                    self.px[o + 2] = int(b * s + self.px[o + 2] * (1 - s))
                    self.px[o + 3] = max(self.px[o + 3], int(a * alpha / 255))

    def text_width(self, string) -> float:
        return self._atlas.advance(string) * self.scale

    def line_height(self) -> float:
        return self._atlas.line_height * self.scale

    # -- optional operations ----------------------------------------------- #

    def image(self, x, y, w, h, handle, uv0=(0.0, 0.0), uv1=(1.0, 1.0),
              tint=(255, 255, 255, 255)) -> None:
        """Draw *handle* into the box.

        The signature is the ``Painter.image`` protocol's -- ``(x, y, w, h,
        handle, ...)``. It used to be ``(handle, p_min, p_max, ...)``, which
        ``cmtk.painter.image`` calls positionally, so ``handle`` bound to the
        *x coordinate* and every image drew a rectangle at the wrong place.

        A :class:`~cmtk.texture.Texture` is rasterised here, nearest
        neighbour: this painter owns its pixels, so it needs no upload and no
        graphics API, which is the point of drawing pictures through a
        painter at all. Any other handle is opaque and degrades to a tinted
        box, as it did before.
        """
        from .texture import Texture
        if isinstance(handle, Texture):
            self._blit_texture(x, y, w, h, handle, uv0, uv1, tint)
            return
        self._fill(x, y, w, h, tint)

    def _blit_texture(self, x, y, w, h, tex, uv0, uv1, tint) -> None:
        """Nearest-neighbour blit of *tex* into the box, tinted and clipped.

        Nearest rather than bilinear on purpose: a scientific image scaled up
        should show its pixels, not a smooth guess between them.
        """
        x0, y0 = int(x), int(y)
        x1, y1 = int(x + w), int(y + h)
        if x1 <= x0 or y1 <= y0:
            return
        tr, tg, tb, ta = (list(tint) + [255])[:4]
        u0, v0 = uv0
        du, dv = (uv1[0] - u0), (uv1[1] - v0)
        span_x, span_y = max(x1 - x0, 1), max(y1 - y0, 1)
        for py in range(max(y0, 0), min(y1, self.height)):
            v = v0 + dv * ((py - y0) + 0.5) / span_y
            sy = min(max(int(v * tex.height), 0), tex.height - 1)
            row = sy * tex.width
            for px in range(max(x0, 0), min(x1, self.width)):
                u = u0 + du * ((px - x0) + 0.5) / span_x
                sx = min(max(int(u * tex.width), 0), tex.width - 1)
                si = (row + sx) * 4
                sr, sg, sb, sa = tex.px[si:si + 4]
                a = (sa * ta) // 255
                if not a:
                    continue
                di = (py * self.width + px) * 4
                if a == 255:
                    self.px[di:di + 4] = bytes(((sr * tr) // 255, (sg * tg) // 255,
                                                (sb * tb) // 255, 255))
                    continue
                inv = 255 - a
                for k, s in enumerate(((sr * tr) // 255, (sg * tg) // 255,
                                       (sb * tb) // 255)):
                    self.px[di + k] = (s * a + self.px[di + k] * inv) // 255
                self.px[di + 3] = min(255, a + self.px[di + 3] * inv // 255)

    def set_font(self, _spec) -> None:
        """Font pushes are ignored: the atlas is the one size there is."""

    def text_rotated(self, x, y, string, colour, angle, pivot) -> None:
        self.text(x, y, self.text_width(string), self.line_height(), 0,
                  string, colour)


# --------------------------------------------------------------------------- #
# Driving a frame and comparing screenshots
# --------------------------------------------------------------------------- #
import pathlib as _pathlib

import cmtk as _cmtk


def render(gui, size=(0.0, 0.0, 320.0, 200.0), io=None, frames: int = 2):
    """Draw *gui* into a :class:`PixelPainter` through ``im.frame``.

    Two frames by default: the first one opens windows and settles layout,
    the second draws the settled interface, which is the one a screenshot
    means.
    """
    io = io if io is not None else _cmtk.im.IO()
    painter = None
    for _ in range(max(1, frames)):
        painter = PixelPainter(int(size[2]), int(size[3]))
        with _cmtk.im.frame(painter, size, io=io):
            gui()
    return painter


def screenshot(gui, size=(0.0, 0.0, 320.0, 200.0), io=None, frames: int = 2):
    """``render``, then pack the buffer as PNG bytes."""
    painter = render(gui, size, io, frames)
    return png_encode(painter.width, painter.height, painter.px)


def assert_images_equal(actual: bytes, expected_path, max_different: int = 0):
    """Decode two PNGs and compare pixel for pixel.

    ``max_different`` is the number of differing pixels tolerated -- zero,
    unless a test explicitly says otherwise.
    """
    w1, h1, p1 = png_decode(actual)
    expected = _pathlib.Path(expected_path).read_bytes()
    w2, h2, p2 = png_decode(expected)
    assert (w1, h1) == (w2, h2), f"size differs: {(w1, h1)} != {(w2, h2)}"
    different = [i for i in range(len(p1)) if p1[i] != p2[i]]
    pixels = len({i // 4 for i in different})
    assert pixels <= max_different, (
        f"{pixels} differing pixels (tolerated {max_different}); "
        f"first at byte {different[0] if different else None}")
