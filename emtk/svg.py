"""Draw an SVG document into pixels: what a console needs to show ``_repr_svg_``.

A Python object that shows itself as SVG -- a matplotlib figure saved with
``figure_format = 'svg'``, a chemical structure, a diagram library's output --
has to become pixels before a painter can draw it, and emtk has no browser to
ask. This is the subset of SVG 1.1 such output uses:

* ``svg`` (``width`` / ``height`` in px, pt, in, cm, mm; ``viewBox``), ``g``,
  ``defs``, ``use``, ``symbol``;
* ``path`` (every command, arcs included), ``rect`` (``rx`` / ``ry``),
  ``circle``, ``ellipse``, ``line``, ``polyline``, ``polygon``, and ``text``
  (drawn with Pillow's default face -- matplotlib writes its glyphs as paths);
* ``transform`` (``matrix``, ``translate``, ``scale``, ``rotate``, ``skewX``,
  ``skewY``), presentation attributes and ``style``, inherited down the tree:
  ``fill``, ``stroke``, ``stroke-width``, the three opacities, ``fill-rule``;
* ``clip-path`` to the bounding box of the clip's shapes (axes clip to a
  rectangle; a curved clip is drawn as its box).

Not drawn: gradients and patterns (filled with their first stop's colour if
they have one, else grey), filters, masks, markers, dashes (drawn solid), CSS
``<style>`` sheets. The edges are anti-aliased by drawing at three times the
size and averaging down.

    >>> from emtk.svg import svg_to_png
    >>> png = svg_to_png('<svg width="4" height="4"><rect width="4" height="4" fill="red"/></svg>')
    >>> png[:4] == b"\\x89PNG"
    True

numpy and Pillow do the arithmetic and the encoding (both are what
:class:`emtk.texture.Texture` already reads images with).
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any

__all__ = ["rasterize_svg", "svg_to_png", "svg_to_texture"]

#: Supersampling factor: edges are drawn this many times finer, then averaged.
SUPERSAMPLE = 3
#: Largest side, in pixels, an SVG is drawn at (a stray ``width="1e6"`` is not a picture).
MAX_SIDE = 4096
_UNITS = {"px": 1.0, "pt": 4.0 / 3.0, "pc": 16.0, "in": 96.0, "cm": 96.0 / 2.54,
          "mm": 96.0 / 25.4, "": 1.0}
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_INHERITED = ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "fill-rule",
              "font-size", "color")
_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _length(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    match = re.fullmatch(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-z%]*)\s*",
                         str(value))
    if not match or match.group(2) == "%":
        return default
    return float(match.group(1)) * _UNITS.get(match.group(2), 1.0)


def _multiply(m: tuple, n: tuple) -> tuple:
    """``m · n``: *n* applied first."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def _transform(text: str | None) -> tuple:
    m = _IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in _NUMBER.findall(args)]
        if name == "matrix" and len(v) == 6:
            n = tuple(v)
        elif name == "translate" and v:
            n = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale" and v:
            n = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "rotate" and v:
            r = math.radians(v[0])
            n = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0.0, 0.0)
            if len(v) == 3:
                n = _multiply(_multiply((1, 0, 0, 1, v[1], v[2]), n), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX" and v:
            n = (1.0, 0.0, math.tan(math.radians(v[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and v:
            n = (1.0, math.tan(math.radians(v[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        m = _multiply(m, n)
    return m


def _style(element: ET.Element, parent: dict) -> dict:
    """The element's presentation, inherited properties from *parent* first."""
    style = {k: parent[k] for k in _INHERITED if k in parent}
    for key in ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-opacity", "opacity",
                "fill-rule", "font-size", "color", "clip-path", "display", "visibility"):
        if key in element.attrib:
            style[key] = element.attrib[key].strip()
    for item in element.attrib.get("style", "").split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            style[key.strip()] = value.strip()
    return style


def _colour(value: str | None, style: dict, gradients: dict) -> tuple[int, int, int] | None:
    if value is None:
        return None
    value = value.strip()
    if value in ("none", "transparent", ""):
        return None
    if value == "currentColor":
        value = style.get("color", "black")
    if value.startswith("url("):
        ref = re.search(r"#([^)'\"]+)", value)
        return gradients.get(ref.group(1) if ref else "", (128, 128, 128))
    from PIL import ImageColor

    try:
        rgb = ImageColor.getrgb(value)
    except ValueError:
        return (0, 0, 0)
    return tuple(int(c) for c in rgb[:3])


# --------------------------------------------------------------------------- #
# Geometry: everything becomes closed or open polylines in user units.
# --------------------------------------------------------------------------- #
def _bezier(points: list, p0, controls, steps: int = 16) -> None:
    pts = [p0, *controls]
    n = len(pts) - 1
    for i in range(1, steps + 1):
        t = i / steps
        if n == 2:
            u = 1 - t
            x = u * u * pts[0][0] + 2 * u * t * pts[1][0] + t * t * pts[2][0]
            y = u * u * pts[0][1] + 2 * u * t * pts[1][1] + t * t * pts[2][1]
        else:
            u = 1 - t
            x = (u ** 3 * pts[0][0] + 3 * u * u * t * pts[1][0] + 3 * u * t * t * pts[2][0]
                 + t ** 3 * pts[3][0])
            y = (u ** 3 * pts[0][1] + 3 * u * u * t * pts[1][1] + 3 * u * t * t * pts[2][1]
                 + t ** 3 * pts[3][1])
        points.append((x, y))


def _arc(points: list, p0, rx, ry, phi, large, sweep, p1) -> None:
    """SVG's endpoint arc, by its centre parametrisation (SVG 1.1 F.6.5)."""
    if p0 == p1:
        return
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        points.append(p1)
        return
    cos_p, sin_p = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cos_p * dx + sin_p * dy
    y1 = -sin_p * dx + cos_p * dy
    scale = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        k = -k
    cx1, cy1 = k * rx * y1 / ry, -k * ry * x1 / rx
    cx = cos_p * cx1 - sin_p * cy1 + (p0[0] + p1[0]) / 2
    cy = sin_p * cx1 + cos_p * cy1 + (p0[1] + p1[1]) / 2
    start = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    end = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx)
    delta = end - start
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    steps = max(4, int(abs(delta) / (math.pi / 16)))
    for i in range(1, steps + 1):
        a = start + delta * i / steps
        x, y = rx * math.cos(a), ry * math.sin(a)
        points.append((cos_p * x - sin_p * y + cx, sin_p * x + cos_p * y + cy))


def _path(d: str) -> list[tuple[list, bool]]:
    """``d`` as ``[(points, closed), ...]``."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|" + _NUMBER.pattern, d or "")
    subpaths: list[tuple[list, bool]] = []
    points: list = []
    x = y = sx = sy = 0.0
    last_control = None
    command = ""
    i = 0

    def number() -> float:
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    def flag() -> int:
        # Arc flags may be written run together ("a1 1 0 00 1 1"); the tokenizer keeps "00".
        nonlocal i
        token = tokens[i]
        if len(token) > 1 and token[0] in "01" and not token.startswith(("0.", "1.")):
            tokens[i] = token[1:]
            return int(token[0])
        i += 1
        return int(float(token))

    def finish(closed: bool) -> None:
        nonlocal points
        if len(points) > 1:
            subpaths.append((points, closed))
        points = []

    while i < len(tokens):
        if re.fullmatch(r"[A-Za-z]", tokens[i]):
            command = tokens[i]
            i += 1
            if command in "Zz":
                finish(True)
                x, y = sx, sy
                last_control = None
                continue
        if not command:
            break
        rel = command.islower()
        c = command.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        try:
            if c == "M":
                finish(False)
                x, y = number() + ox, number() + oy
                sx, sy = x, y
                points = [(x, y)]
                command = "l" if rel else "L"
                last_control = None
                continue
            if not points:
                points = [(x, y)]
            if c == "L":
                x, y = number() + ox, number() + oy
                points.append((x, y))
                last_control = None
            elif c == "H":
                x = number() + ox
                points.append((x, y))
                last_control = None
            elif c == "V":
                y = number() + oy
                points.append((x, y))
                last_control = None
            elif c == "C":
                c1 = (number() + ox, number() + oy)
                c2 = (number() + ox, number() + oy)
                end = (number() + ox, number() + oy)
                _bezier(points, (x, y), [c1, c2, end])
                last_control, (x, y) = ("C", c2), end
            elif c == "S":
                c1 = ((2 * x - last_control[1][0], 2 * y - last_control[1][1])
                      if last_control and last_control[0] == "C" else (x, y))
                c2 = (number() + ox, number() + oy)
                end = (number() + ox, number() + oy)
                _bezier(points, (x, y), [c1, c2, end])
                last_control, (x, y) = ("C", c2), end
            elif c == "Q":
                c1 = (number() + ox, number() + oy)
                end = (number() + ox, number() + oy)
                _bezier(points, (x, y), [c1, end])
                last_control, (x, y) = ("Q", c1), end
            elif c == "T":
                c1 = ((2 * x - last_control[1][0], 2 * y - last_control[1][1])
                      if last_control and last_control[0] == "Q" else (x, y))
                end = (number() + ox, number() + oy)
                _bezier(points, (x, y), [c1, end])
                last_control, (x, y) = ("Q", c1), end
            elif c == "A":
                rx, ry, phi = number(), number(), number()
                large, sweep = flag(), flag()
                end = (number() + ox, number() + oy)
                _arc(points, (x, y), rx, ry, phi, large, sweep, end)
                x, y = end
                last_control = None
            else:
                i += 1
        except (IndexError, ValueError):
            break
    finish(False)
    return subpaths


def _ellipse(cx: float, cy: float, rx: float, ry: float, steps: int = 48) -> list:
    return [(cx + rx * math.cos(2 * math.pi * k / steps), cy + ry * math.sin(2 * math.pi * k / steps))
            for k in range(steps)]


def _shape(element: ET.Element, tag: str) -> list[tuple[list, bool]]:
    a = element.attrib
    num = lambda key, default=0.0: _length(a.get(key), default)  # noqa: E731
    if tag == "path":
        return _path(a.get("d", ""))
    if tag == "rect":
        x, y, w, h = num("x"), num("y"), num("width"), num("height")
        if w <= 0 or h <= 0:
            return []
        rx, ry = _length(a.get("rx")), _length(a.get("ry"))
        rx = min(w / 2, rx if rx is not None else (ry or 0.0))
        ry = min(h / 2, ry if ry is not None else rx)
        if rx <= 0 or ry <= 0:
            return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        pts: list = []
        for cx, cy, a0 in ((x + w - rx, y + ry, -90), (x + w - rx, y + h - ry, 0),
                           (x + rx, y + h - ry, 90), (x + rx, y + ry, 180)):
            for k in range(9):
                t = math.radians(a0 + 90 * k / 8)
                pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
        return [(pts, True)]
    if tag == "circle":
        r = num("r")
        return [(_ellipse(num("cx"), num("cy"), r, r), True)] if r > 0 else []
    if tag == "ellipse":
        rx, ry = num("rx"), num("ry")
        return [(_ellipse(num("cx"), num("cy"), rx, ry), True)] if rx > 0 and ry > 0 else []
    if tag == "line":
        return [([(num("x1"), num("y1")), (num("x2"), num("y2"))], False)]
    if tag in ("polyline", "polygon"):
        v = [float(n) for n in _NUMBER.findall(a.get("points", ""))]
        pts = list(zip(v[0::2], v[1::2]))
        return [(pts, tag == "polygon")] if len(pts) > 1 else []
    return []


# --------------------------------------------------------------------------- #
# Rasterising: polygons to coverage, coverage to colour.
# --------------------------------------------------------------------------- #
class _Canvas:
    def __init__(self, width: int, height: int, background) -> None:
        import numpy as np

        self.np = np
        self.w, self.h = width, height
        self.rgba = np.zeros((height, width, 4), dtype=np.float32)
        if background is not None:
            self.rgba[:] = [c / 255.0 for c in background] + [1.0] if len(background) == 3 else [
                c / 255.0 for c in background]

    def fill(self, polygons: list, colour, alpha: float, evenodd: bool, clip=None) -> None:
        """Fill *polygons* (device pixels) with the non-zero or even-odd rule."""
        np = self.np
        edges = []
        for pts in polygons:
            if len(pts) < 3:
                continue
            p = np.asarray(pts, dtype=np.float64)
            edges.append(np.concatenate([p, np.roll(p, -1, axis=0)], axis=1))
        if not edges or alpha <= 0:
            return
        e = np.concatenate(edges)
        e = e[e[:, 1] != e[:, 3]]
        if not len(e):
            return
        x0, x1 = 0, self.w
        y0, y1 = 0, self.h
        if clip is not None:
            x0, y0 = max(x0, int(math.floor(clip[0]))), max(y0, int(math.floor(clip[1])))
            x1, y1 = min(x1, int(math.ceil(clip[2]))), min(y1, int(math.ceil(clip[3])))
        lo = int(max(y0, math.floor(min(e[:, 1].min(), e[:, 3].min()))))
        hi = int(min(y1, math.ceil(max(e[:, 1].max(), e[:, 3].max()))))
        left = int(max(x0, math.floor(min(e[:, 0].min(), e[:, 2].min()))))
        right = int(min(x1, math.ceil(max(e[:, 0].max(), e[:, 2].max())) + 1))
        if hi <= lo or right <= left:
            return
        rows = np.arange(lo, hi) + 0.5
        ya, yb = e[:, 1][None, :], e[:, 3][None, :]
        r = rows[:, None]
        hit = ((ya <= r) & (r < yb)) | ((yb <= r) & (r < ya))
        ri, ei = np.nonzero(hit)
        if not len(ri):
            return
        ex = e[ei]
        t = (rows[ri] - ex[:, 1]) / (ex[:, 3] - ex[:, 1])
        xs = ex[:, 0] + t * (ex[:, 2] - ex[:, 0])
        direction = np.where(ex[:, 3] > ex[:, 1], 1, -1)
        order = np.lexsort((xs, ri))
        ri, xs, direction = ri[order], xs[order], direction[order]
        # Winding after each crossing, per row.
        starts = np.r_[0, np.nonzero(np.diff(ri))[0] + 1]
        winding = np.cumsum(direction)
        base = np.repeat(winding[starts] - direction[starts], np.diff(np.r_[starts, len(ri)]))
        winding = winding - base
        inside = (winding % 2 == 1) if evenodd else (winding != 0)
        # A span runs from a crossing that leaves the shape "inside" to the next crossing.
        nxt = np.r_[xs[1:], xs[-1]]
        same_row = np.r_[ri[1:] == ri[:-1], False]
        span = inside & same_row
        width = right - left
        diff = np.zeros((hi - lo, width + 1), dtype=np.int32)
        a = np.clip(np.ceil(xs[span] - 0.5).astype(int) - left, 0, width)
        b = np.clip(np.ceil(nxt[span] - 0.5).astype(int) - left, 0, width)
        np.add.at(diff, (ri[span], a), 1)
        np.add.at(diff, (ri[span], b), -1)
        mask = np.cumsum(diff[:, :width], axis=1) > 0
        if not mask.any():
            return
        region = self.rgba[lo:hi, left:right]
        src = np.array([c / 255.0 for c in colour], dtype=np.float32)
        a_src = np.float32(alpha) * mask[..., None]
        out_a = a_src[..., 0] + region[..., 3] * (1 - a_src[..., 0])
        region[..., :3] = src * a_src + region[..., :3] * (1 - a_src)
        region[..., 3] = out_a

    def image(self):
        np = self.np
        k = SUPERSAMPLE
        h, w = self.h // k, self.w // k
        data = self.rgba[: h * k, : w * k].reshape(h, k, w, k, 4).mean(axis=(1, 3))
        return (np.clip(data, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def _stroke_polygons(points: list, closed: bool, width: float) -> list:
    """A polyline's outline: one quad per segment and a disc at every vertex, all wound alike."""
    half = width / 2.0
    out = []
    pts = list(points) + ([points[0]] if closed else [])
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        nx, ny = -dy / length * half, dx / length * half
        out.append([(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)])
    if half >= 0.75:
        for x, y in pts:
            out.append(_ellipse(x, y, half, half, 12))
    return out


def _apply(m: tuple, pts: list) -> list:
    a, b, c, d, e, f = m
    return [(a * x + c * y + e, b * x + d * y + f) for x, y in pts]


class _Renderer:
    def __init__(self, root: ET.Element, scale: float, background) -> None:
        self.root = root
        self.ids = {el.attrib["id"]: el for el in root.iter() if "id" in el.attrib}
        self.gradients = {}
        for key, el in self.ids.items():
            if _local(el.tag) in ("linearGradient", "radialGradient"):
                for stop in el.iter():
                    if _local(stop.tag) == "stop":
                        st = _style(stop, {})
                        colour = stop.attrib.get("stop-color") or st.get("stop-color")
                        if colour:
                            self.gradients[key] = _colour(colour, st, {})
                            break
        width = _length(root.attrib.get("width"))
        height = _length(root.attrib.get("height"))
        box = [float(v) for v in _NUMBER.findall(root.attrib.get("viewBox", ""))]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            box = [0.0, 0.0, width or 300.0, height or 150.0]
        if width is None and height is None:
            width, height = box[2], box[3]
        elif width is None:
            width = height * box[2] / box[3]
        elif height is None:
            height = width * box[3] / box[2]
        side = max(width, height) * scale
        if side > MAX_SIDE:
            scale *= MAX_SIDE / side
        self.size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
        k = SUPERSAMPLE
        sx = self.size[0] * k / box[2]
        sy = self.size[1] * k / box[3]
        self.base = (sx, 0.0, 0.0, sy, -box[0] * sx, -box[1] * sy)
        self.canvas = _Canvas(self.size[0] * k, self.size[1] * k, background)

    def run(self):
        self._children(self.root, self.base, _style(self.root, {}), None, 0)
        return self.canvas.image()

    def _children(self, element, m, style, clip, depth) -> None:
        for child in element:
            self._element(child, m, style, clip, depth + 1)

    def _clip_box(self, value: str | None, m: tuple, clip):
        ref = re.search(r"#([^)'\"]+)", value or "")
        target = self.ids.get(ref.group(1)) if ref else None
        if target is None:
            return clip
        xs, ys = [], []
        for child in target.iter():
            local = _transform(child.attrib.get("transform"))
            for pts, _closed in _shape(child, _local(child.tag)):
                for x, y in _apply(_multiply(m, local), pts):
                    xs.append(x)
                    ys.append(y)
        if not xs:
            return clip
        box = (min(xs), min(ys), max(xs), max(ys))
        if clip is not None:
            box = (max(box[0], clip[0]), max(box[1], clip[1]), min(box[2], clip[2]),
                   min(box[3], clip[3]))
        return box

    def _element(self, element, m, parent_style, clip, depth) -> None:
        if depth > 64:
            return
        tag = _local(element.tag)
        if tag in ("defs", "clipPath", "mask", "pattern", "linearGradient", "radialGradient",
                   "style", "title", "desc", "metadata", "marker", "symbol", "filter"):
            return
        style = _style(element, parent_style)
        if style.get("display") == "none" or style.get("visibility") == "hidden":
            return
        m = _multiply(m, _transform(element.attrib.get("transform")))
        if "clip-path" in style:
            clip = self._clip_box(style.pop("clip-path"), m, clip)
        opacity = float(style.pop("opacity", 1.0) or 1.0)
        if opacity != 1.0:
            for key in ("fill-opacity", "stroke-opacity"):
                style[key] = float(style.get(key, 1.0)) * opacity
        if tag in ("svg", "g", "a", "switch"):
            if tag == "svg" and element is not self.root:
                x, y = _length(element.attrib.get("x"), 0.0), _length(element.attrib.get("y"), 0.0)
                m = _multiply(m, (1, 0, 0, 1, x, y))
            self._children(element, m, style, clip, depth)
            return
        if tag == "use":
            href = element.attrib.get("{http://www.w3.org/1999/xlink}href") or element.attrib.get(
                "href", "")
            target = self.ids.get(href.lstrip("#"))
            if target is None:
                return
            x, y = _length(element.attrib.get("x"), 0.0), _length(element.attrib.get("y"), 0.0)
            m = _multiply(m, (1, 0, 0, 1, x, y))
            if _local(target.tag) == "symbol":
                self._children(target, m, style, clip, depth)
            else:
                self._element_unhidden(target, m, style, clip, depth)
            return
        if tag == "text":
            self._text(element, m, style, clip)
            return
        self._draw(_shape(element, tag), m, style, clip)

    def _element_unhidden(self, element, m, style, clip, depth) -> None:
        tag = _local(element.tag)
        if tag in ("g", "svg"):
            inner = _style(element, style)
            self._children(element, _multiply(m, _transform(element.attrib.get("transform"))),
                           inner, clip, depth + 1)
            return
        self._element(element, m, style, clip, depth + 1)

    def _draw(self, subpaths, m, style, clip) -> None:
        if not subpaths:
            return
        fill = _colour(style.get("fill", "black"), style, self.gradients)
        if fill is not None:
            polygons = [_apply(m, pts) for pts, _closed in subpaths]
            self.canvas.fill(polygons, fill, float(style.get("fill-opacity", 1.0)),
                             style.get("fill-rule") == "evenodd", clip)
        stroke = _colour(style.get("stroke"), style, self.gradients)
        width = _length(style.get("stroke-width"), 1.0) or 0.0
        if stroke is not None and width > 0:
            a, b, c, d = m[:4]
            device = width * math.sqrt(abs(a * d - b * c))
            device = max(device, 1.0 * SUPERSAMPLE * 0.75)
            polygons = []
            for pts, closed in subpaths:
                polygons.extend(_stroke_polygons(_apply(m, pts), closed, device))
            self.canvas.fill(polygons, stroke, float(style.get("stroke-opacity", 1.0)), False, clip)

    def _text(self, element, m, style, clip) -> None:
        text = "".join(element.itertext()).strip()
        fill = _colour(style.get("fill", "black"), style, self.gradients)
        if not text or fill is None:
            return
        from PIL import Image, ImageDraw, ImageFont

        size = _length(style.get("font-size"), 16.0) or 16.0
        a, b, c, d = m[:4]
        device = max(4, int(round(size * math.sqrt(abs(a * d - b * c)))))
        try:
            font = ImageFont.load_default(device)
        except TypeError:  # Pillow < 10.1: one bitmap size
            font = ImageFont.load_default()
        x, y = _length(element.attrib.get("x"), 0.0), _length(element.attrib.get("y"), 0.0)
        px, py = _apply(m, [(x, y)])[0]
        left, top, right, bottom = font.getbbox(text)
        stamp = Image.new("L", (max(1, right - left), max(1, bottom - top)), 0)
        ImageDraw.Draw(stamp).text((-left, -top), text, fill=255, font=font)
        anchor = element.attrib.get("text-anchor") or style.get("text-anchor")
        ox = {"middle": -stamp.width / 2, "end": -stamp.width}.get(anchor, 0.0)
        np = self.canvas.np
        alpha = np.asarray(stamp, dtype=np.float32)[..., None] / 255.0 * float(
            style.get("fill-opacity", 1.0))
        x0, y0 = int(round(px + ox + left)), int(round(py - device * 0.8 + top))
        h, w = alpha.shape[:2]
        cx0, cy0, cx1, cy1 = 0, 0, self.canvas.w, self.canvas.h
        if clip is not None:
            cx0, cy0, cx1, cy1 = (max(0, int(clip[0])), max(0, int(clip[1])),
                                  min(cx1, int(clip[2]) + 1), min(cy1, int(clip[3]) + 1))
        sx0, sy0 = max(x0, cx0), max(y0, cy0)
        sx1, sy1 = min(x0 + w, cx1), min(y0 + h, cy1)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        region = self.canvas.rgba[sy0:sy1, sx0:sx1]
        a_src = alpha[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        src = np.array([v / 255.0 for v in fill], dtype=np.float32)
        region[..., :3] = src * a_src + region[..., :3] * (1 - a_src)
        region[..., 3] = a_src[..., 0] + region[..., 3] * (1 - a_src[..., 0])


def rasterize_svg(data: bytes | str, scale: float = 1.0, background=None):
    """Draw the SVG *data*; returns an ``(h, w, 4)`` uint8 RGBA array.

    Parameters
    ----------
    data : bytes or str
        The SVG document.
    scale : float, optional
        Device pixels per CSS pixel (2 for a high-density screen).
    background : tuple, optional
        ``(r, g, b[, a])`` under the drawing; transparent when omitted.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    # The DOCTYPE of a matplotlib SVG names a DTD; ElementTree must not go looking for it.
    data = re.sub(r"<!DOCTYPE[^>[]*(\[[^]]*\])?>", "", data, count=1)
    root = ET.fromstring(data)
    if _local(root.tag) != "svg":
        raise ValueError(f"not an SVG document: the root element is <{_local(root.tag)}>")
    return _Renderer(root, float(scale), background).run()


def svg_to_png(data: bytes | str, scale: float = 1.0, background=None) -> bytes:
    """Draw the SVG *data* and encode it as PNG (see :func:`rasterize_svg`)."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(rasterize_svg(data, scale, background)).save(buffer, format="PNG")
    return buffer.getvalue()


def svg_to_texture(data: bytes | str, scale: float = 1.0, background=None):
    """Draw the SVG *data* into a :class:`emtk.texture.Texture`."""
    from .texture import Texture

    pixels = rasterize_svg(data, scale, background)
    return Texture(pixels.shape[1], pixels.shape[0], pixels.tobytes())
