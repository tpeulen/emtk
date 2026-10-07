"""Translate painter geometry while preserving optional backend capabilities."""
from __future__ import annotations


class OffsetPainter:
    """A local coordinate view of any EMTK painter, without native transforms.

    Only geometry is translated. Text/font metrics, texture handles, UVs,
    colours, and optional capability absence are preserved.
    """

    def __init__(self, painter, x: float, y: float) -> None:
        self.painter = painter
        self.x, self.y = float(x), float(y)

    def _point(self, point):
        return point[0] + self.x, point[1] + self.y

    def __getattr__(self, name):
        operation = getattr(self.painter, name)
        if name in {"fill_rect", "stroke_rect", "gradient_rect", "text",
                    "push_clip", "image", "marker", "box_has_colour"}:
            def rectangle(x, y, *args, **kwargs):
                return operation(x + self.x, y + self.y, *args, **kwargs)
            return rectangle
        if name in {"fill_triangle", "gradient_triangle", "image_triangle"}:
            def triangle(p0, p1, p2, *args, **kwargs):
                return operation(self._point(p0), self._point(p1), self._point(p2),
                                 *args, **kwargs)
            return triangle
        if name in {"polyline", "fill_convex"}:
            def points(vertices, *args, **kwargs):
                return operation([self._point(point) for point in vertices], *args, **kwargs)
            return points
        if name == "fill_triangles":
            def triangles(vertices, *args, **kwargs):
                return operation([[self._point(point) for point in triangle]
                                  for triangle in vertices], *args, **kwargs)
            return triangles
        return operation

    def text_rotated(self, x, y, w, h, align, string, colour, degrees=0.0):
        """Translate a rotated text box while preserving the painter capability."""
        operation = getattr(self.painter, "text_rotated", None)
        if callable(operation):
            return operation(x + self.x, y + self.y, w, h, align, string, colour, degrees)
        return self.painter.text(x + self.x, y + self.y, w, h, align, string, colour)
