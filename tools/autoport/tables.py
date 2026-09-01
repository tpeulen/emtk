"""The rule tables: C++ -> cmtk names, enums, printf formats, prelude helpers.

Pure data -- every translating pass reads these; nothing here runs code."""

# --------------------------------------------------------------------------- #
# The rule tables
# --------------------------------------------------------------------------- #

#: ``ImGui<Family>_<Member>`` -> the Python namespace the member lives in.
#: ``cmtk.flags`` guarantees every namespace here exists.
ENUM_FAMILIES = {
    "ImGuiCol": "im.Col", "ImGuiDir": "im.Dir",
    "ImGuiWindowFlags": "im.WindowFlags", "ImGuiChildFlags": "im.ChildFlags",
    "ImGuiInputTextFlags": "im.InputTextFlags", "ImGuiStyleVar": "im.StyleVar",
    "ImGuiCond": "im.Cond", "ImGuiHoveredFlags": "im.HoveredFlags",
    "ImGuiSliderFlags": "im.SliderFlags", "ImGuiTreeNodeFlags": "im.TreeNodeFlags",
    "ImGuiSelectableFlags": "im.SelectableFlags", "ImGuiButtonFlags": "im.ButtonFlags",
    "ImGuiComboFlags": "im.ComboFlags", "ImGuiTabBarFlags": "im.TabBarFlags",
    "ImGuiTabItemFlags": "im.TabItemFlags", "ImGuiTableFlags": "im.TableFlags",
    "ImGuiTableColumnFlags": "im.TableColumnFlags", "ImGuiTableRowFlags": "im.TableRowFlags",
    "ImGuiTableBgTarget": "im.TableBgTarget", "ImGuiFocusedFlags": "im.FocusedFlags",
    "ImGuiPopupFlags": "im.PopupFlags", "ImGuiMouseButton": "im.MouseButton",
    "ImGuiMouseCursor": "im.MouseCursor", "ImGuiKey": "im.Key",
    "ImGuiDataType": "im.DataType", "ImGuiSortDirection": "im.SortDirection",
    "ImGuiDragDropFlags": "im.DragDropFlags", "ImGuiConfigFlags": "im.ConfigFlags",
    "ImGuiBackendFlags": "im.BackendFlags", "ImGuiItemFlags": "im.ItemFlags",
    "ImDrawFlags": "im.DrawFlags", "ImDrawCornerFlags": "im.DrawFlags",
    "ImGuiColorEditFlags": "im.ColorEditFlags",
}

#: C++ math helpers -> Python. ``im_*`` names come from the emitted prelude.
MATH_FUNCS = {
    "ImSin": "math.sin", "ImCos": "math.cos", "ImFabs": "abs", "ImAbs": "abs",
    "ImFmod": "math.fmod", "ImSqrt": "math.sqrt", "ImPow": "math.pow",
    "ImFloor": "math.floor", "ImFloorSig": "math.floor", "ImLog": "math.log",
    "ImInvLerp": "im_inv_lerp", "ImRemap": "im_remap", "ImRemap01": "im_remap01",
    "ImLerp": "im_lerp", "ImClamp": "im_clamp", "ImMin": "min", "ImMax": "max",
    "ImSign": "im_sign", "ImIsNan": "math.isnan", "ImTrunc": "math.trunc",
    "ImModPositive": "im_mod_positive",
    "sinf": "math.sin", "cosf": "math.cos", "fabsf": "abs", "sqrtf": "math.sqrt",
    "powf": "math.pow", "fmodf": "math.fmod", "floorf": "math.floor",
    "ceilf": "math.ceil", "atan2f": "math.atan2", "atanf": "math.atan",
    "tanf": "math.tan", "expf": "math.exp", "logf": "math.log",
    "fmod": "math.fmod", "sqrt": "math.sqrt", "pow": "math.pow",
    "sin": "math.sin", "cos": "math.cos", "tan": "math.tan", "fabs": "abs",
    "floor": "math.floor", "ceil": "math.ceil", "atan2": "math.atan2",
    "roundf": "round", "truncf": "math.trunc", "strlen": "len",
    "MIN": "min", "MAX": "max",
}

CONSTANTS = {
    "nullptr": "None", "NULL": "None", "true": "True", "false": "False",
    "IM_PI": "math.pi", "IM_PI_2": "math.pi / 2", "INT_MAX": "2**31 - 1",
    "UINT8_MAX": "255", "INT16_MAX": "32767",
}

#: ImGui calls whose C++ signature takes ``T*`` out-params: the value position
#: in the cmtk Python signature (the label is position 0). The call gains an
#: assignment: ``_changed, v = im.slider_float(...)``.
OUT_PARAM_INDEX = {
    "SliderFloat": 1, "SliderInt": 1, "SliderAngle": 1,
    # The *Scalar* family takes an `ImGuiDataType` second, so the value it
    # writes through is third -- `SliderScalar(label, data_type, p_data,
    # p_min, p_max, ...)`. Recorded as 1, the rewrite assigned to the data
    # type: `_changed, im.DataType.DOUBLE = im.slider_scalar(...)`. It went
    # unnoticed because the old guard only accepted a bare name, so the
    # whole rewrite was skipped and the call merely lost its result.
    "SliderScalar": 2, "DragScalar": 2, "InputScalar": 2,
    "VSliderScalar": 3,
    "SliderFloat2": 1, "SliderFloat3": 1, "SliderFloat4": 1,
    "SliderInt2": 1, "SliderInt3": 1, "SliderInt4": 1,
    "VSliderFloat": 1, "VSliderInt": 1,
    "DragFloat": 1, "DragInt": 1,
    "DragFloatRange2": 1, "DragIntRange2": 1,
    "DragFloat2": 1, "DragFloat3": 1, "DragFloat4": 1,
    "DragInt2": 1, "DragInt3": 1, "DragInt4": 1,
    "InputFloat": 1, "InputInt": 1, "InputDouble": 1,
    "InputFloat2": 1, "InputFloat3": 1, "InputFloat4": 1,
    "InputInt2": 1, "InputInt3": 1, "InputInt4": 1,
    "InputText": 1, "InputTextWithHint": 2, "InputTextMultiline": 1,
    "Checkbox": 1, "CheckboxFlags": 1,
    "ColorEdit3": 1, "ColorEdit4": 1, "ColorPicker3": 1, "ColorPicker4": 1,
    "Combo": 1, "ListBox": 1,
    # Two out-params, like the Range2 drags: `SplitterBehavior(bb, id, axis,
    # float* size1, float* size2, ...)` moves space between two panes, so
    # both come back. Without this the call ported with its result dropped
    # and the splitter dragged while nothing moved.
    "SplitterBehavior": 3,
}

#: ImGui calls taking a printf format + varargs: Python formats with ``%``.
FMT_FUNCS = {
    "Text", "TextColored", "TextDisabled", "TextWrapped", "BulletText",
    "LabelText", "SetTooltip", "SetItemTooltip", "TreeNode", "TreeNodeEx",
    "BeginTabItem", "ProgressBar", "DebugLog", "LogText",
}

#: Where the printf format sits, for the functions whose format is not the
#: first argument. ``TextColored(col, fmt, ...)`` takes a colour first, and
#: folding from argument 0 leaves the varargs unfolded and the call arity
#: wrong -- cmtk's ``text_colored(col, s)`` takes two.
FMT_ARG_INDEX = {
    "TextColored": 1,
    "LabelText": 1,
    "TreeNodeEx": 1,
}

#: Arguments that are an ``ImVec4`` *colour*. Dear ImGui spells a colour in
#: floats 0..1; cmtk paints in bytes 0..255, and a float tuple handed to a
#: cmtk painter is very nearly black -- it draws, so nothing raises, and the
#: text is simply invisible. These are folded through ``floats_to_rgba``.
COLOUR_ARG_INDEX = {
    "TextColored": 0,
    "PushStyleColor": 1,
    "ColorButton": 1,
    "ColorConvertFloat4ToU32": 0,
}

IO_FIELDS = {
    "MousePos": "mouse_pos", "MouseDown": "mouse_down", "MouseClicked": "mouse_clicked",
    "MouseReleased": "mouse_released", "MouseWheel": "mouse_wheel",
    "MouseWheelH": "mouse_wheel_h", "DeltaTime": "delta_time",
    "KeyCtrl": "key_ctrl", "KeyShift": "key_shift", "KeyAlt": "key_alt",
    "KeySuper": "key_super", "WantCaptureMouse": "want_capture_mouse",
    "WantCaptureKeyboard": "want_capture_keyboard", "FrameCount": "frame_count",
    "MouseDragDelta": "mouse_drag_delta", "WantTextInput": "want_text_input",
    "MouseClickedPos": "mouse_clicked_pos", "FontGlobalScale": "font_global_scale",
}

CPP_TYPES = [
    "unsigned long long", "unsigned long", "unsigned int", "unsigned short",
    "unsigned char", "signed char", "long long", "const char* const*",
    "const char*", "const float", "const int", "const bool", "const double",
    "ImTextureID", "ImDrawList*", "ImGuiStorage*", "ImGuiIO&", "ImGuiIO*",
    "ImVec4", "ImVec2", "ImColor", "ImU32", "ImS64", "ImU64", "ImS32",
    "ImWchar", "ImGuiID", "ImGuiKey", "ImGuiDir", "ImGuiCol", "ImGuiDataType",
    "ImGuiWindowFlags", "ImGuiInputTextFlags", "ImGuiSliderFlags", "ImGuiCond",
    "ImGuiTableFlags", "ImGuiSelectableFlags", "ImGuiComboFlags",
    "ImGuiTreeNodeFlags", "ImGuiButtonFlags", "ImGuiHoveredFlags",
    "ImGuiTabBarFlags", "ImGuiTabItemFlags", "ImGuiStyleVar",
    "ImGuiIO&", "ImGuiStyle&", "ImFont*", "ImFont", "ImDrawList&",
    "ImGuiIO", "ImGuiStyle", "ImVec2&", "const ImVec2&", "const ImVec2",
    "std::string", "string", "ImDrawList", "ImRect", "const ImRect&",
    "const ImVec4&", "const ImVec4*", "unsigned",
    # Application code, unlike an ImGui extension, declares standard-library
    # and fixed-width types. Without them a declaration is not recognised as
    # one and ``std::vector<double> v = x;`` ports to ``std.vector v = x`` --
    # a syntax error that costs the enclosing function.
    "std::unordered_map", "std::unordered_set", "std::shared_ptr",
    "std::unique_ptr", "std::optional", "std::vector", "std::array",
    "std::pair", "std::map", "std::set", "std::atomic", "std::function",
    "unordered_map", "shared_ptr", "unique_ptr", "optional", "vector",
    "array", "pair", "map", "set", "function",
    "uint_least8_t", "uint_fast8_t", "uint64_t", "uint32_t", "uint16_t",
    "uint8_t", "int64_t", "int32_t", "int16_t", "int8_t", "ptrdiff_t",
    "size_t", "intptr_t", "uintptr_t", "float", "double",
    "bool", "char", "int", "short", "long", "auto", "void", "static",
    "inline", "const", "mutable", "constexpr",
]

TYPE_WORDS = {"const", "unsigned", "signed", "static", "inline", "virtual",
              "explicit", "constexpr", "extern", "override", "noexcept",
              "int", "float", "bool", "char", "double", "long", "short",
              "void", "auto", "size_t", "uint8_t", "uint16_t", "uint32_t",
              "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
              "ImU32", "ImS32", "ImU64", "ImS64", "ImVec2", "ImVec4",
              "ImColor", "ImU8", "ImS8", "ImWchar", "ImGuiID", "string"}

PRELUDE = {
    "im_lerp": ("def im_lerp(a, b, t):\n"
                '    """ImLerp: blend a toward b by t. C++ overloads this for\n'
                '    scalars and ImVec2/4; a tuple is blended component-wise."""\n'
                "    if isinstance(a, tuple):\n"
                "        return tuple(im_lerp(x, y, t) for x, y in zip(a, b))\n"
                "    return a + (b - a) * t\n"),
    "im_clamp": ("def im_clamp(v, mn, mx):\n"
                 '    """ImClamp."""\n'
                 "    return max(mn, min(mx, v))\n"),
    "im_inv_lerp": ("def im_inv_lerp(a, b, t):\n"
                    '    """ImInvLerp: t in [a,b] -> [0,1]."""\n'
                    "    return (t - a) / (b - a)\n"),
    "im_remap": ("def im_remap(t, a, b):\n"
                 '    """ImRemap: t in [a,b] -> [out_min,out_max]."""\n'
                 "    return im_lerp(a, b, im_clamp((t - a) / (b - a), 0, 1))\n"),
    "im_remap01": ("def im_remap01(t, a, b):\n"
                   '    """ImRemap01."""\n'
                   "    return (t - a) / (b - a)\n"),
    "im_sign": ("def im_sign(v):\n"
                '    """ImSign."""\n'
                "    return -1 if v < 0 else (1 if v > 0 else 0)\n"),
    "im_mod_positive": ("def im_mod_positive(a, b):\n"
                        '    """ImModPositive."""\n'
                        "    return ((a % b) + b) % b\n"),
    "im_sizeof": ("def im_sizeof(_v):\n"
                  '    """C sizeof: a Python sequence knows its own length."""\n'
                  "    return len(_v)\n"),
    "ImRect": ('class ImRect:\n'
               '    """ImRect: axis-aligned rectangle, as the ImGuizmo family\n'
               '    expects it. Corners are ``(x, y)`` tuples; min is inclusive,\n'
               '    max exclusive -- the same convention as a clip rect.\n'
               "\n"
               '    The corners are *lists*, not tuples: C++ writes\n'
               '    ``bb.Min.x += pad`` and the port spells that\n'
               '    ``bb.min[0] = bb.min[0] + pad``, which a tuple refuses.\n'
               '    They index the same either way."""\n'
               "    def __init__(self, a=(0.0, 0.0), b=(0.0, 0.0)):\n"
               "        self.min = list(a)\n"
               "        self.max = list(b)\n"
               "\n"
               "    def contains(self, p):\n"
               "        return (self.min[0] <= p[0] < self.max[0]\n"
               "                and self.min[1] <= p[1] < self.max[1])\n"
               "\n"
               "    def get_center(self):\n"
               "        return ((self.min[0] + self.max[0]) * 0.5,\n"
               "                (self.min[1] + self.max[1]) * 0.5)\n"
               "\n"
               "    def get_size(self):\n"
               "        return (self.max[0] - self.min[0], self.max[1] - self.min[1])\n"
               "\n"
               "    def get_width(self):\n"
               "        return self.max[0] - self.min[0]\n"
               "\n"
               "    def get_height(self):\n"
               "        return self.max[1] - self.min[1]\n"
               "\n"
               "    def get_area(self):\n"
               "        return self.get_width() * self.get_height()\n"
               "\n"
               "    def get_tl(self):\n"
               "        return self.min\n"
               "\n"
               "    def get_br(self):\n"
               "        return self.max\n"
               "\n"
               "    def get_tr(self):\n"
               "        return (self.max[0], self.min[1])\n"
               "\n"
               "    def get_bl(self):\n"
               "        return (self.min[0], self.max[1])\n"
               "\n"
               "    def expand(self, amount):\n"
               "        return ImRect((self.min[0] - amount, self.min[1] - amount),\n"
               "                      (self.max[0] + amount, self.max[1] + amount))\n"),
}


