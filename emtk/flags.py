"""Dear ImGui's flag families, spelled for Python.

A mechanical port writes ``ImGuiWindowFlags_NoMove`` as
``im.WindowFlags.NO_MOVE`` -- these namespaces are what makes that line
parse, and where their meaning in emtk lives. Two shapes:

* **Flag families** are classes of small ints, so ``|`` and ``&`` behave as
  the C++ did. The bit values are emtk's own (assigned in the order Dear
  ImGui declares them); a port that only ORs, ANDs and tests them never
  notices.
* ``StyleVar`` members name attributes of :class:`~emtk.Style` -- that is
  what ``PushStyleVar`` pushes in emtk.
* ``Key`` members carry :mod:`emtk.keys` values, which is what ``io.key``
  delivers.
* ``DataType`` members are strings, because emtk's scalar widgets dispatch
  on the Python type of the value.

A bit a widget does not implement is a widget's business: emtk functions
accept the flags and implement what they implement, which is always at
least the bits this module's docstring lists per family.
"""
from __future__ import annotations

from . import keys as _keys

__all__ = [
    "WindowFlags", "ChildFlags", "InputTextFlags", "StyleVar", "Cond",
    "HoveredFlags", "SliderFlags", "TreeNodeFlags", "SelectableFlags",
    "ComboFlags", "TabBarFlags", "TabItemFlags", "ColorEditFlags",
    "FocusedFlags", "PopupFlags", "MouseButton", "MouseCursor", "Key",
    "DataType", "SortDirection", "DragDropFlags", "DrawFlags", "Axis",
]


def _bits(*names: str) -> type:
    """A flag namespace: ``NONE = 0`` and one bit each, in declaration order.

    Members are spelled the way :func:`emtk.im_compat.mechanical_name`
    spells them uppercased: ``NoMove`` lands as ``NO_MOVE``, matching what
    ``tools/autoport.py`` writes.
    """
    def upper(s: str) -> str:
        import re as _re
        s = _re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", s)
        s = _re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
        return s.upper()

    members = {"NONE": 0}
    for i, name in enumerate(names):
        members[upper(name)] = 1 << i
    return type("Flags", (), members)


def _named(**members) -> type:
    """A namespace whose members carry non-int meanings (strings, ints)."""
    return type("Named", (), members)


WindowFlags = _bits(
    "NoTitleBar", "NoResize", "NoMove", "NoScrollbar", "NoScrollWithMouse",
    "NoCollapse", "AlwaysAutoResize", "NoBackground", "NoSavedSettings",
    "NoMouseInputs", "NoInputs", "NoNavInputs", "NoNavFocus", "NoNav",
    "MenuBar", "HorizontalScrollbar", "NoFocusOnAppearing",
    "NoBringToFrontOnFocus", "AlwaysVerticalScrollbar", "AlwaysHorizontalScrollbar",
    "UnsavedDocument", "NoDocking", "NoDecoration",
)

ColorEditFlags = _bits(
    "NoAlpha", "NoPicker", "NoOptions", "NoSmallPreview", "NoInputs",
    "NoTooltip", "NoLabel", "NoSidePreview", "NoDragDrop", "NoBorder",
    "AlphaBar", "AlphaPreview", "AlphaPreviewHalf", "HDR", "DisplayRGB",
    "DisplayHSV", "DisplayHex", "Uint8", "Float", "PickerHueBar",
    "PickerHueWheel", "InputRGB", "InputHSV",
    # emtk's colour widgets take these and implement what they implement --
    # a swatch that ignores NoTooltip still draws the swatch, which is what
    # a port needs from it.
)

ChildFlags = _bits(
    "Borders", "AlwaysUseWindowPadding", "ResizeX", "ResizeY",
    "AutoResizeX", "AutoResizeY", "AlwaysAutoResize", "FrameStyle",
)

InputTextFlags = _bits(
    "CharsDecimal", "CharsHexadecimal", "CharsUppercase", "CharsNoBlank",
    "AutoSelectAll", "EnterReturnsTrue", "CallbackCompletion", "CallbackHistory",
    "AlwaysOverwrite", "ReadOnly", "Password", "NoUndoRedo",
    # emtk implements (im.input_text): CharsHexadecimal, CharsDecimal,
    # ReadOnly, AlwaysOverwrite, EnterReturnsTrue.
)

Cond = _bits("Always", "Once", "FirstUseEver", "Appearing")

HoveredFlags = _bits(
    "ChildWindows", "RootWindow", "AnyWindow", "NoPopupHierarchy",
    "DockHierarchy", "AllowWhenBlockedByPopup", "AllowWhenBlockedByActiveItem",
    "AllowWhenOverlappedByItem", "AllowWhenOverlappedByWindow",
    "AllowWhenDisabled", "NoNavOverride", "ForTooltip", "NonInteractive",
)

SliderFlags = _bits(
    "Logarithmic", "NoRoundToFormat", "NoInput", "WrapAround", "ClampOnInput",
    "AlwaysClamp", "NoSpeedTiebreak", "KeyboardSupport",
    # emtk implements: none of the behaviour bits yet; drag_scalar/slider_scalar
    # accept and ignore them visibly through im SliderFlags documentation.
)

TreeNodeFlags = _bits(
    "Selected", "Framed", "AllowOverlap", "NoTreePushOnOpen", "NoAutoOpenOnLog",
    "DefaultOpen", "OpenOnDoubleClick", "OpenOnArrow", "Leaf", "Bullet",
    "FramePadding", "SpanAvailWidth", "SpanFullWidth", "SpanTextWidth",
    "SpanAllColumns", "LabelSpanAllColumns", "NavLeftJumpsToParent",
    "CollapsingHeader",
)

SelectableFlags = _bits(
    "NoAutoClosePopups", "SpanAllColumns", "TextAlignLeft", "TextAlignRight",
    "NoPadWithHalfSpacing", "DontClosePopups", "SpanAvailWidth",
    "AllowDoubleClick", "Disabled", "AllowOverlap",
)

ComboFlags = _bits(
    "PopupAlignLeft", "HeightSmall", "HeightRegular", "HeightLarge",
    "HeightLargest", "NoArrowButton", "NoPreview", "WidthFitPreview",
)

TabBarFlags = _bits(
    "Reorderable", "AutoSelectNewTabs", "TabListPopupButton", "NoCloseWithMiddleMouseButton",
    "NoTabListScrollingButtons", "NoTooltip", "DrawSelectedOverline", "FittingPolicyResizeDown",
    "FittingPolicyScroll", "FittingPolicyMask", "FittingPolicyDefault",
)

TabItemFlags = _bits(
    "UnsavedDocument", "SetSelected", "NoCloseWithMiddleMouseButton",
    "NoPushId", "NoTooltip", "NoReorder", "Leading", "Trailing",
    "NoAssumedFlags",
)

FocusedFlags = _bits("ChildWindows", "RootWindow", "AnyWindow", "NoPopupHierarchy")

PopupFlags = _bits(
    "MouseButtonLeft", "MouseButtonRight", "MouseButtonMiddle",
    "MouseButtonMask", "MouseButtonDefault", "NoReopen", "NoOpenOverExistingPopup",
    "NoOpenOverItems", "AnyPopupId", "AnyPopupLevel", "AnyPopup",
)

MouseButton = _named(LEFT=0, RIGHT=1, MIDDLE=2)

#: ``ImGuiAxis``. Internal in the reference, but a splitter takes one as an
#: argument, so a port that resizes anything has to be able to name it. The
#: values are the reference's, and they are also the index into a
#: ``(x, y)`` pair -- which is what every use of it here is for.
Axis = _named(NONE=-1, X=0, Y=1)

MouseCursor = _named(
    NONE=-1, ARROW=0, TEXT_INPUT=1, RESIZE_ALL=2, RESIZE_NS=3, RESIZE_EW=4,
    RESIZE_NESW=5, RESIZE_NWSE=6, HAND=7, NOT_ALLOWED=8,
)

Key = _named(
    NONE=0,
    TAB=_keys.KEY_TAB, LEFT_ARROW=_keys.KEY_LEFT, RIGHT_ARROW=_keys.KEY_RIGHT,
    UP_ARROW=_keys.KEY_UP, DOWN_ARROW=_keys.KEY_DOWN, PAGE_UP=_keys.KEY_PAGE_UP,
    PAGE_DOWN=_keys.KEY_PAGE_DOWN, HOME=_keys.KEY_HOME, END=_keys.KEY_END,
    INSERT=_keys.KEY_INSERT, DELETE=_keys.KEY_DELETE,
    BACKSPACE=_keys.KEY_BACKSPACE,
    # `SPACE` and `INSERT` were `None`, which is not "unbound" but *wrong*:
    # `io.key == Key.SPACE` is then false for every key including space, so
    # a shortcut bound to one silently never fired. A code emtk already had.
    SPACE=_keys.KEY_SPACE, ENTER=_keys.KEY_RETURN, ESCAPE=_keys.KEY_ESCAPE,
    # The function keys. An application binds its shortcuts to these -- cmc
    # toggles an acquisition on F2 -- and every one of them was missing.
    F1=_keys.KEY_F1, F2=_keys.KEY_F2, F3=_keys.KEY_F3, F4=_keys.KEY_F4,
    F5=_keys.KEY_F5, F6=_keys.KEY_F6, F7=_keys.KEY_F7, F8=_keys.KEY_F8,
    F9=_keys.KEY_F9, F10=_keys.KEY_F10, F11=_keys.KEY_F11, F12=_keys.KEY_F12,
    # These four have no code of their own: they are *modifiers*, and emtk
    # reports them through `io.key_ctrl` and friends rather than as keys.
    LEFT_CTRL=None, LEFT_SHIFT=None, LEFT_ALT=None, LEFT_SUPER=None,
)

DataType = _named(
    NONE="none", S8="s8", U8="u8", S16="s16", U16="u16", S32="s32", U32="u32",
    S64="s64", U64="u64", FLOAT="float", DOUBLE="double",
)

SortDirection = _named(NONE=0, ASCENDING=1, DESCENDING=2)

DragDropFlags = _bits(
    "NoPreviewTooltip", "NoHideTooltipOnDrag", "NoCopyRetention", "NoMoveRetention",
    "SourceNoPreviewTooltip", "SourceNoDisableHover", "SourceNotDraggable",
    "SourceNoHoldToOpenOthers", "SourceAllowNullId", "SourceAutoExpirePayload",
    "AcceptBeforeDelivery", "AcceptNoDrawDefaultRect", "AcceptNoPreviewTooltip",
    "AcceptPeekOnly",
)

DrawFlags = _bits(
    "Closed", "RoundCornersTopLeft", "RoundCornersTopRight",
    "RoundCornersBottomLeft", "RoundCornersBottomRight", "RoundCornersNone",
    "RoundCornersTop", "RoundCornersBottom", "RoundCornersLeft",
    "RoundCornersRight", "RoundCornersAll",
)

StyleVar = _named(
    ALPHA="alpha",
    DISABLED_ALPHA="disabled_alpha",
    WINDOW_PADDING="window_padding",
    WINDOW_ROUNDING="window_rounding",
    WINDOW_BORDER_SIZE="window_border_size",
    WINDOW_MIN_SIZE="window_min_size",
    CHILD_ROUNDING="child_rounding",
    CHILD_BORDER_SIZE="child_border_size",
    POPUP_ROUNDING="popup_rounding",
    POPUP_BORDER_SIZE="popup_border_size",
    FRAME_PADDING="frame_padding",
    FRAME_ROUNDING="frame_rounding",
    FRAME_BORDER_SIZE="frame_border_size",
    ITEM_SPACING="item_spacing",
    ITEM_INNER_SPACING="item_inner_spacing",
    INDENT_SPACING="indent_spacing",
    CELL_PADDING="cell_padding",
    SCROLLBAR_SIZE="scrollbar_size",
    SCROLLBAR_ROUNDING="scrollbar_rounding",
    GRAB_MIN_SIZE="grab_min_size",
    GRAB_ROUNDING="grab_rounding",
    TAB_ROUNDING="tab_rounding",
    BUTTON_TEXT_ALIGN="button_text_align",
    SELECTABLE_TEXT_ALIGN="selectable_text_align",
)
