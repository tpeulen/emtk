"""Scale painter geometry *and* text: lay out in logical pixels, draw at k times.

A print figure is laid out once, in logical pixels, and written at whatever
resolution the page needs: 300 dpi is the same layout drawn at 3.125 times
96 dpi. Scaling the canvas alone would leave the text at its screen size --
small, thin labels on a large picture -- so this also scales the font, through
the optional ``set_font_scale`` of the painter underneath, and reports metrics
back in logical pixels so the layout never sees the factor.
"""

from __future__ import annotations

__all__ = ["ScaledPainter"]


class ScaledPainter:
    """Draw on *painter* at *k* device pixels per logical pixel.

    Parameters
    ----------
    painter : Painter
        Must offer ``set_font_scale`` for the text to scale with the geometry;
        without it the text stays at the device size.
    k : float
        Device pixels per logical pixel.
    """

    def __init__(self, painter, k: float) -> None:
        self.painter = painter
        self.k = float(k)
        self._font_scale = 1.0
        self._apply_font()

    def _apply_font(self) -> None:
        op = getattr(self.painter, "set_font_scale", None)
        if callable(op):
            op(self._font_scale * self.k)

    def _point(self, point):
        return point[0] * self.k, point[1] * self.k

    # -- metrics come back in logical pixels -------------------------------
    def text_width(self, string) -> float:
        return self.painter.text_width(string) / self.k

    def line_height(self) -> float:
        return self.painter.line_height() / self.k

    def set_font_scale(self, scale: float) -> None:
        self._font_scale = float(scale)
        self._apply_font()

    # -- geometry goes out in device pixels --------------------------------
    def __getattr__(self, name):
        operation = getattr(self.painter, name)
        k = self.k
        if name in {"fill_rect", "push_clip"}:
            def box(x, y, w, h, *args, **kwargs):
                return operation(x * k, y * k, w * k, h * k, *args, **kwargs)
            return box
        if name in {"stroke_rect", "gradient_rect", "image"}:
            def box(x, y, w, h, *args, **kwargs):
                return operation(x * k, y * k, w * k, h * k, *args, **kwargs)
            return box
        if name == "text":
            def text(x, y, w, h, *args, **kwargs):
                return operation(x * k, y * k, w * k, h * k, *args, **kwargs)
            return text
        if name in {"fill_triangle", "gradient_triangle", "image_triangle"}:
            def triangle(p0, p1, p2, *args, **kwargs):
                return operation(self._point(p0), self._point(p1), self._point(p2),
                                 *args, **kwargs)
            return triangle
        if name == "polyline":
            def polyline(vertices, width, *args, **kwargs):
                return operation([self._point(p) for p in vertices], width * k, *args, **kwargs)
            return polyline
        if name == "fill_convex":
            def convex(vertices, *args, **kwargs):
                return operation([self._point(p) for p in vertices], *args, **kwargs)
            return convex
        if name == "fill_triangles":
            def triangles(vertices, *args, **kwargs):
                return operation([[self._point(p) for p in tri] for tri in vertices],
                                 *args, **kwargs)
            return triangles
        return operation

    def text_rotated(self, x, y, w, h, align, string, colour, degrees=0.0):
        operation = getattr(self.painter, "text_rotated", None)
        k = self.k
        if callable(operation):
            return operation(x * k, y * k, w * k, h * k, align, string, colour, degrees)
        return self.painter.text(x * k, y * k, w * k, h * k, align, string, colour)
