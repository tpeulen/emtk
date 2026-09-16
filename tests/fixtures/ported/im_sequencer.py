"""im_sequencer: auto-ported from ImSequencer.h, ImSequencer.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

from enum import IntFlag

class SEQUENCER_OPTIONS(IntFlag):
    """SEQUENCER_OPTIONS, from ImSequencer.h."""
    sequencer_edit_none = 0
    sequencer_edit_startend = 1
    sequencer_change_frame = 2
    sequencer_add = 3
    sequencer_del = 4
    sequencer_copypaste = 5
    sequencer_edit_all = 6

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

def im_clamp(v, mn, mx):
    """ImClamp."""
    return max(mn, min(mx, v))

def im_lerp(a, b, t):
    """ImLerp: blend a toward b by t. C++ overloads this for
    scalars and ImVec2/4; a tuple is blended component-wise."""
    if isinstance(a, tuple):
        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))
    return a + (b - a) * t

class SequenceInterface:
    """SequenceInterface, from ImSequencer.h."""

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def begin_edit(self, _arg0):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def end_edit(self):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def get_item_type_count(self):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def duplicate(self, _arg0):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def copy(self):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def paste(self):
    pass
    def get_custom_height(self, _arg0):
        """GetCustomHeight()."""
        return 0

    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def double_click(self, _arg0):
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def custom_draw(self, _arg0, ImDrawList, ImRect, ImRect, ImRect, ImRec
    pass
    # TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def custom_draw_compact(self, _arg0, ImDrawList, ImRect, ImRect):
    pass
def sequencer_add_del_button(draw_list, pos, add=True):
    """SequencerAddDelButton()."""
    io = im.get_io()
    btnRect = ImRect(pos, (pos[0] + 16, pos[1] + 16))
    overBtn = btnRect.contains(io.mouse_pos)
    containedClick = overBtn  and  btnRect.contains(io.mouse_clicked_pos[0])
    clickedBtn = containedClick  and  io.mouse_released[0]
    btnColor = (0xAAEAFFAA if overBtn else 0x77A3B2AA)
    if containedClick  and  io.mouse_down_duration[0] > 0:
        btnRect.expand(2.0)
    midy = pos[1] + 16 / 2 - 0.5
    midx = pos[0] + 16 / 2 - 0.5
    draw_list.add_rect(btnRect.min, btnRect.max, btnColor, 4)
    draw_list.add_line((btnRect.min[0] + 3, midy), (btnRect.max[0] - 3, midy), btnColor, 2)
    if add:
        draw_list.add_line((midx, btnRect.min[1] + 3), (midx, btnRect.max[1] - 3), btnColor, 2)
    return clickedBtn

# TODO(autoport): hand-translate (the rules mangled this line): this region resisted the mechanical port: def sequencer(sequence, currentFrame, expanded, selectedEntry, firstFr
pass