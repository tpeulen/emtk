"""im_zoom_slider: auto-ported from ImZoomSlider.h
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

from enum import IntFlag

class ZoomSliderFlags(IntFlag):
    """ImGuiZoomSliderFlags, from ImZoomSlider.h."""
    NONE = 0

class ImRect:
    """ImRect: axis-aligned rectangle, as the ImGuizmo family
    expects it. Corners are ``(x, y)`` tuples; min is inclusive,
    max exclusive -- the same convention as a clip rect."""
    def __init__(self, a=(0.0, 0.0), b=(0.0, 0.0)):
        self.min = a
        self.max = b

    def contains(self, p):
        return (self.min[0] <= p[0] < self.max[0]
                and self.min[1] <= p[1] < self.max[1])

    def get_center(self):
        return ((self.min[0] + self.max[0]) * 0.5,
                (self.min[1] + self.max[1]) * 0.5)

    def expand(self, amount):
        return ImRect((self.min[0] - amount, self.min[1] - amount),
                      (self.max[0] + amount, self.max[1] + amount))

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def im_zoom_slider(lower, higher, viewLower, viewHigher, wheelRatio=0.
pass