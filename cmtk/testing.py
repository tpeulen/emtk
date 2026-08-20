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

__all__ = ["RecordingPainter", "FIXED_GLYPH_W", "FIXED_LINE_H"]

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
