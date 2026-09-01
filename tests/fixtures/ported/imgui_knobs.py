"""imgui_knobs: auto-ported from imgui_knobs.h, imgui_knobs.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to cmtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import cmtk.im as im

IMGUIKNOBS_PI = 3.14159265358979323846

from enum import IntFlag

class KnobFlags(IntFlag):
    """ImGuiKnobFlags, from imgui_knobs.h."""
    NONE = 0
    NO_TITLE = 1
    NO_INPUT = 2
    VALUE_TOOLTIP = 4
    DRAG_HORIZONTAL = 8
    DRAG_VERTICAL = 16
    LOGARITHMIC = 32
    ALWAYS_CLAMP = 64

class KnobVariant(IntFlag):
    """ImGuiKnobVariant, from imgui_knobs.h."""
    NONE = 0
    TICK = 1
    DOT = 2
    WIPER = 4
    WIPER_ONLY = 8
    WIPER_DOT = 16
    STEPPED = 32
    SPACE = 64

class color_set:
    """color_set, from imgui_knobs.h."""

    def __init__(self, base, hovered, active):
        """color_set()."""
        self.base = None
        self.hovered = None
        self.active = None
        self.base = base
        self.hovered = hovered
        self.active = active

    def __init__2(self, color):
        """color_set()."""
        self.base = None
        self.hovered = None
        self.active = None
        self.base = color
        self.hovered = color
        self.active = color

class Knob:
    """Knob, from imgui_knobs.h."""

    def __init__(self, _label, data_type, p_value, v_min, v_max, speed, _radius, format, flags, _angle_min, _angle_max):
        """Knob()."""
        self.radius = None
        self.value_changed = None
        self.center = None
        self.is_active = None
        self.is_hovered = None
        self.angle_min = None
        self.angle_max = None
        self.t = None
        self.angle = None
        self.angle_cos = None
        self.angle_sin = None
        self.radius = _radius
        if flags & KnobFlags.LOGARITHMIC:
            v = max(min(p_value, v_max), v_min)
            self.t = (math.log(abs(v)) - math.log(abs(v_min))) / (math.log(abs(v_max)) - math.log(abs(v_min)))
        else:
            self.t = (float(p_value) - v_min) / (v_max - v_min)
        screen_pos = im.get_cursor_screen_pos()
        im.invisible_button(_label, (self.radius * 2.0, self.radius * 2.0))
        io = im.get_io()
        drag_vertical = not (flags & KnobFlags.DRAG_HORIZONTAL)  and  (flags & KnobFlags.DRAG_VERTICAL  or  abs(io.mouse_delta[1]) > abs(io.mouse_delta[0]))
        gid = im.get_id(_label)
        drag_behaviour_flags = 0
        if drag_vertical:
            drag_behaviour_flags = drag_behaviour_flags | im.SliderFlags.VERTICAL
        if flags & KnobFlags.ALWAYS_CLAMP:
            drag_behaviour_flags = drag_behaviour_flags | im.SliderFlags.ALWAYS_CLAMP
        if flags & KnobFlags.LOGARITHMIC:
            drag_behaviour_flags = drag_behaviour_flags | im.SliderFlags.LOGARITHMIC
        self.value_changed, p_value = im.drag_scalar(gid, p_value, speed, v_min, v_max, format)
        self.angle_min = (IMGUIKNOBS_PI * 0.75 if _angle_min < 0 else _angle_min)
        self.angle_max = (IMGUIKNOBS_PI * 2.25 if _angle_max < 0 else _angle_max)
        self.center = (screen_pos[0] + self.radius, screen_pos[1] + self.radius)
        self.is_active = im.is_item_active()
        self.is_hovered = im.is_item_hovered()
        self.angle = self.angle_min + (self.angle_max - self.angle_min) * self.t
        self.angle_cos = math.cos(self.angle)
        self.angle_sin = math.sin(self.angle)

    def draw_dot(self, size, radius, angle, color, filled, segments):
        """draw_dot()."""
        dot_size = size * self.radius
        dot_radius = self.radius * self.radius
        im.get_window_draw_list().add_circle_filled((self.center[0] + math.cos(self.angle) * dot_radius, self.center[1] + math.sin(self.angle) * dot_radius), dot_size, (color.active if self.is_active else ((color.hovered if self.is_hovered else color.base))), segments)

    def draw_tick(self, start, end, width, angle, color):
        """draw_tick()."""
        tick_start = start * self.radius
        tick_end = end * self.radius
        angle_cos = math.cos(self.angle)
        angle_sin = math.sin(self.angle)
        im.get_window_draw_list().add_line((self.center[0] + self.angle_cos * tick_end, self.center[1] + self.angle_sin * tick_end), (self.center[0] + self.angle_cos * tick_start, self.center[1] + self.angle_sin * tick_start), (color.active if self.is_active else ((color.hovered if self.is_hovered else color.base))), width * self.radius)

    def draw_circle(self, size, color, filled, segments):
        """draw_circle()."""
        circle_radius = size * self.radius
        im.get_window_draw_list().add_circle_filled(self.center, circle_radius, (color.active if self.is_active else ((color.hovered if self.is_hovered else color.base))))

    def draw_arc(self, radius, size, start_angle, end_angle, color):
        """draw_arc()."""
        track_radius = self.radius * self.radius
        track_size = size * self.radius * 0.5 + 0.0001
        draw_arc(self.center, track_radius, start_angle, end_angle, track_size, (color.active if self.is_active else ((color.hovered if self.is_hovered else color.base))))

def im_log(x):
    """ImLog()."""
    return math.log(static_cast(x))

def draw_arc(center, radius, start_angle, end_angle, thickness, color):
    """draw_arc()."""
    draw_list = im.get_window_draw_list()
    draw_list.path_arc_to(center, radius, start_angle, end_angle)
    draw_list.path_stroke(color, 0, thickness)

def knob_with_drag(label, data_type, value, v_min, v_max, _speed, format, size, flags, angle_min, angle_max):
    """knob_with_drag()."""
    if flags & KnobFlags.LOGARITHMIC  and  v_min <= 0.0  and  v_max >= 0.0:
        is_floating_point = (data_type == im.DataType.FLOAT)  or  (data_type == im.DataType.DOUBLE)
        decimal_precision = (im_parse_format_precision(format, 3) if is_floating_point else 1)
        v_min = math.pow(0.1, float(decimal_precision))
        v_max = max(v_min, v_max)
        value = max(min(value, v_max), v_min)
    speed = ((v_max - v_min) / 250. if _speed == 0 else _speed)
    im.push_id(label)
    font_scale = im.get_io().font_global_scale
    width = (im.get_text_line_height() * 4.0 if size == 0 else size * font_scale)
    im.push_item_width(width)
    im.begin_group()
    pass  # TODO(autoport): internal window state: ImGui::GetCurrentWindow()->DC.CurrLineTextBaseOffset = 0
    if not (flags & KnobFlags.NO_TITLE):
        title_size = im.calc_text_size(label, None, False, width)
        im.set_cursor_pos_x(im.get_cursor_pos_x() + (width - title_size[0]) * 0.5)
        im.text("%s" % label)
    k = Knob(label, data_type, value, v_min, v_max, speed, width * 0.5, format, flags, angle_min, angle_max)
    if flags & KnobFlags.VALUE_TOOLTIP  and  (im.is_item_hovered(im.HoveredFlags.ALLOW_WHEN_DISABLED)  or  im.is_item_active()):
        im.begin_tooltip()
        im.text(format, value)
        im.end_tooltip()
    if not (flags & KnobFlags.NO_INPUT):
        drag_scalar_flags = 0
        if flags & KnobFlags.ALWAYS_CLAMP:
            drag_scalar_flags = drag_scalar_flags | im.SliderFlags.ALWAYS_CLAMP
        if flags & KnobFlags.LOGARITHMIC:
            drag_scalar_flags = drag_scalar_flags | im.SliderFlags.LOGARITHMIC
        changed, value = im.drag_scalar("###knob_drag", value, speed, v_min, v_max, format)
        if changed:
            k.value_changed = True
    im.end_group()
    im.pop_item_width()
    im.pop_id()
    return k, value

def get_primary_color_set():
    """GetPrimaryColorSet()."""
    colors = im.get_style().colors
    return color_set(colors[im.Col.BUTTON_ACTIVE], colors[im.Col.BUTTON_HOVERED], colors[im.Col.BUTTON_HOVERED])

def get_secondary_color_set():
    """GetSecondaryColorSet()."""
    colors = im.get_style().colors
    active = (colors[im.Col.BUTTON_ACTIVE][0] * 0.5, colors[im.Col.BUTTON_ACTIVE][1] * 0.5, colors[im.Col.BUTTON_ACTIVE][2] * 0.5, colors[im.Col.BUTTON_ACTIVE][3])
    hovered = (colors[im.Col.BUTTON_HOVERED][0] * 0.5, colors[im.Col.BUTTON_HOVERED][1] * 0.5, colors[im.Col.BUTTON_HOVERED][2] * 0.5, colors[im.Col.BUTTON_HOVERED][3])
    return color_set(active, hovered, hovered)

def get_track_color_set():
    """GetTrackColorSet()."""
    colors = im.get_style().colors
    return color_set(colors[im.Col.BUTTON], colors[im.Col.BUTTON], colors[im.Col.BUTTON])

def base_knob(label, data_type, value, v_min, v_max, speed, format, variant, size, flags, steps, angle_min, angle_max):
    """BaseKnob()."""
    knob, value = knob_with_drag(label, data_type, value, v_min, v_max, speed, format, size, flags, angle_min, angle_max)
    if variant == KnobVariant.TICK:
        knob.draw_circle(0.85, get_secondary_color_set(), True, 32)
        knob.draw_tick(0.5, 0.85, 0.08, knob.angle, get_primary_color_set())
    elif variant == KnobVariant.DOT:
        knob.draw_circle(0.85, get_secondary_color_set(), True, 32)
        knob.draw_dot(0.12, 0.6, knob.angle, get_primary_color_set(), True, 12)
    elif variant == KnobVariant.WIPER:
        knob.draw_circle(0.7, get_secondary_color_set(), True, 32)
        knob.draw_arc(0.8, 0.41, knob.angle_min, knob.angle_max, get_track_color_set())
        if knob.t > 0.01:
            knob.draw_arc(0.8, 0.43, knob.angle_min, knob.angle, get_primary_color_set())
    elif variant == KnobVariant.WIPER_ONLY:
        knob.draw_arc(0.8, 0.41, knob.angle_min, knob.angle_max, get_track_color_set())
        if knob.t > 0.01:
            knob.draw_arc(0.8, 0.43, knob.angle_min, knob.angle, get_primary_color_set())
    elif variant == KnobVariant.WIPER_DOT:
        knob.draw_circle(0.6, get_secondary_color_set(), True, 32)
        knob.draw_arc(0.85, 0.41, knob.angle_min, knob.angle_max, get_track_color_set())
        knob.draw_dot(0.1, 0.85, knob.angle, get_primary_color_set(), True, 12)
    elif variant == KnobVariant.STEPPED:
        for n in range(int(0.), int(steps)):
            a = n / (steps - 1)
            angle = knob.angle_min + (knob.angle_max - knob.angle_min) * a
            knob.draw_tick(0.7, 0.9, 0.04, angle, get_primary_color_set())
        knob.draw_circle(0.6, get_secondary_color_set(), True, 32)
        knob.draw_dot(0.12, 0.4, knob.angle, get_primary_color_set(), True, 12)
    elif variant == KnobVariant.SPACE:
        knob.draw_circle(0.3 - knob.t * 0.1, get_secondary_color_set(), True, 16)
        if knob.t > 0.01:
            knob.draw_arc(0.4, 0.15, knob.angle_min - 1.0, knob.angle - 1.0, get_primary_color_set())
            knob.draw_arc(0.6, 0.15, knob.angle_min + 1.0, knob.angle + 1.0, get_primary_color_set())
            knob.draw_arc(0.8, 0.15, knob.angle_min + 3.0, knob.angle + 3.0, get_primary_color_set())
    return knob.value_changed, value

def knob(label, value, v_min, v_max, speed, format, variant, size, flags, steps, angle_min, angle_max):
    """Knob()."""
    return base_knob(label, im.DataType.FLOAT, value, v_min, v_max, speed, format, variant, size, flags, steps, angle_min, angle_max)

def knob_int(label, value, v_min, v_max, speed, format, variant, size, flags, steps, angle_min, angle_max):
    """KnobInt()."""
    return base_knob(label, im.DataType.S32, value, v_min, v_max, speed, format, variant, size, flags, steps, angle_min, angle_max)
