"""imgui_toggle: auto-ported from imgui_toggle.h, imgui_toggle.cpp
(upstream, MIT) by tools/autoport.py.

A mechanical port of Dear ImGui C++ to emtk. Lines flagged
TODO(autoport) need a hand; everything else is the C++ under the
naming rules in tools/autoport.py.
"""
import math

import emtk.im as im

Phi = 1.6180339887498948482045
DiameterToRadiusRatio = 0.5
AnimationDurationDisabled = 0.0
AnimationDurationDefault = 0.1
AnimationDurationMinimum = AnimationDurationDisabled
FrameRoundingDefault = 1.0
FrameRoundingMinimum = 0.0
FrameRoundingMaximum = 1.0
KnobRoundingDefault = 1.0
KnobRoundingMinimum = 0.0
KnobRoundingMaximum = 1.0
WidthRatioDefault = Phi
WidthRatioMinimum = 1.0
WidthRatioMaximum = 10.0
KnobInsetMinimum = -100.0
KnobInsetMaximum = 100.0
BorderThicknessDefault = 1.0
ShadowThicknessDefault = 2.0

from enum import IntFlag

class ToggleFlags(IntFlag):
    """ImGuiToggleFlags, from imgui_toggle.h."""
    NONE = 0
    ANIMATED = 1
    BORDERED_FRAME = 2
    BORDERED_KNOB = 4
    SHADOWED_FRAME = 8
    SHADOWED_KNOB = 16
    A11Y = 32
    BORDERED = 64
    SHADOWED = 128
    DEFAULT = 256

def set_to_alias_defaults(config):
    """SetToAliasDefaults()."""
    config.flags = ToggleFlags.DEFAULT
    config.animation_duration = AnimationDurationDisabled
    config.frame_rounding = FrameRoundingDefault
    config.knob_rounding = KnobRoundingDefault

def toggle(label, v, size):
    """ImGui::Toggle()."""
    set_to_alias_defaults(_internalConfig)
    _internalConfig.size = size
    return toggle_internal(label, v, _internalConfig)

def toggle(label, v, flags, size):
    """ImGui::Toggle()."""
    set_to_alias_defaults(_internalConfig)
    _internalConfig.flags = flags
    _internalConfig.size = size
    if (flags & ToggleFlags.ANIMATED) != 0:
        _internalConfig.animation_duration = AnimationDurationDefault
    return toggle_internal(label, v, _internalConfig)

def toggle(label, v, flags, animation_duration, size):
    """ImGui::Toggle()."""
    if animation_duration > 0  and  (flags & ToggleFlags.ANIMATED) != 0:
        flags = flags | (ToggleFlags.ANIMATED)
    set_to_alias_defaults(_internalConfig)
    _internalConfig.flags = flags
    _internalConfig.animation_duration = animation_duration
    _internalConfig.size = size
    return toggle_internal(label, v, _internalConfig)

def toggle(label, v, flags, frame_rounding, knob_rounding, size):
    """ImGui::Toggle()."""
    set_to_alias_defaults(_internalConfig)
    _internalConfig.flags = flags
    _internalConfig.frame_rounding = frame_rounding
    _internalConfig.knob_rounding = knob_rounding
    _internalConfig.size = size
    return toggle_internal(label, v, _internalConfig)

def toggle(label, v, flags, animation_duration, frame_rounding, knob_rounding, size):
    """ImGui::Toggle()."""
    if animation_duration > 0  and  (flags & ToggleFlags.ANIMATED) != 0:
        flags = flags | (ToggleFlags.ANIMATED)
    _internalConfig.flags = flags
    _internalConfig.animation_duration = animation_duration
    _internalConfig.frame_rounding = frame_rounding
    _internalConfig.knob_rounding = knob_rounding
    _internalConfig.size = size
    return toggle_internal(label, v, _internalConfig)

def toggle(label, v, config):
    """ImGui::Toggle()."""
    return toggle_internal(label, v, config)

def toggle_internal(label, v, config):
    """ToggleInternal()."""
    renderer = None  # TODO(autoport): static -- construct this state
    renderer.set_config(label, v, config)
    return renderer.render()
