"""``cmtk.im``: Dear ImGui, in Python. Import this one.

The reference is three files and so is this: :mod:`~cmtk.im_core` is the
context, the window stack and ``ItemAdd``/``ButtonBehavior`` (``imgui.cpp``);
:mod:`~cmtk.im_widgets` is everything built on them
(``imgui_widgets.cpp``); and this is the facade a program includes
(``imgui.h``)::

    from cmtk import im

    with im.frame(painter, (0, 0, 300, 200)):        # NewFrame ... Render
        im.begin("Hello, world!")                    # ImGui::Begin
        im.text("This is some useful text.")         # ImGui::Text
        if im.button("Button"):                      # ImGui::Button
            counter += 1
        im.same_line()                               # ImGui::SameLine
        im.text("counter = %d" % counter)
        im.end()                                     # ImGui::End

A facade rather than one module because the widgets are written *against* the
context: with both in one file the widgets would have to import the thing
importing them, which is a cycle, and the layering check says so. The reference
splits at the same seam for the same reason.

The one place Python must differ from C++ is the pointer arguments: ``bool*``
and ``float*`` become a returned value, ``changed, v = im.slider_float(...)``,
as in pyimgui and imgui-bundle.
"""
from __future__ import annotations

from .im_core import *  # noqa: F401,F403
from .im_core import __all__ as _CORE
from .im_widgets import *  # noqa: F401,F403
from .im_widgets import __all__ as _WIDGETS

__all__ = list(_CORE) + list(_WIDGETS)

# ...and the spellings a purely mechanical port produces, for the handful of
# names where `CamelCase` -> `snake_case` and a readable Python name disagree
# (`ColorConvertHSVtoRGB`) or where C needed a second `va_list` entry point
# Python does not (`TextV`). See `im_compat`.
from .flags import *  # noqa: F401,F403
from .flags import __all__ as _FLAGS

__all__ += list(_FLAGS)


def col32(r, g, b, a=255):
    """``IM_COL32``: an RGBA tuple, cmtk's colour spelling."""
    return (int(r) & 255, int(g) & 255, int(b) & 255, int(a) & 255)


#: the mechanical spelling of the macro name, for transliterated ports
im_col32 = col32

__all__ += ["col32", "im_col32"]

from . import im_compat as _compat  # noqa: E402
import pathlib as _pathlib  # noqa: E402
import sys as _sys  # noqa: E402


def _published_names():
    """Dear ImGui's own list, as vendored beside the tests."""
    for candidate in (
        _pathlib.Path(__file__).resolve().parents[2] / "tests" / "cmtk" / "imgui_api.txt",
    ):
        if candidate.exists():
            return [line.strip() for line in candidate.read_text().splitlines()
                    if line.strip()]
    return list(_compat.MECHANICAL_ALIASES) + list(_compat.VARIADIC)


# The two colour conversions live with the colour widgets, but they are an
# *ImGui-facing* concern: the reference spells a colour as four floats 0..1
# and cmtk's painters take bytes 0..255, so any program transliterated from
# C++ needs the conversion, and needs it under the name it imported -- ``im``.
# Without this a ported ``TextColored`` reaches for ``im.floats_to_rgba`` and
# gets an AttributeError, or worse, passes the floats through and draws
# invisible black text.
from .widgets.color import floats_to_rgba, rgba_to_floats  # noqa: E402,F401

__all__ += ["floats_to_rgba", "rgba_to_floats"]

_ALIASED = _compat.install(_sys.modules[__name__], _published_names())

#: The spellings a purely mechanical port produces for the handful of names the
#: rule cannot render readably. Written out rather than computed because the
#: package's lazy attribute map is built by reading these lists -- a name bound
#: only at import time is a name `cmtk.<name>` cannot find.
#: `tests/cmtk/test_imgui_api_coverage.py` checks the two agree.
__all__ += [
    "bullet_text_v",             # ImGui::BulletTextV
    "color_convert_hs_vto_rgb",  # ImGui::ColorConvertHSVtoRGB
    "color_convert_rg_bto_hsv",  # ImGui::ColorConvertRGBtoHSV
    "debug_log_v",               # ImGui::DebugLogV
    "label_text_v",              # ImGui::LabelTextV
    "log_text_v",                # ImGui::LogTextV
    "set_item_tooltip_v",        # ImGui::SetItemTooltipV
    "set_tooltip_v",             # ImGui::SetTooltipV
    "text_colored_v",            # ImGui::TextColoredV
    "text_disabled_v",           # ImGui::TextDisabledV
    "text_v",                    # ImGui::TextV
    "text_wrapped_v",            # ImGui::TextWrappedV
    "tree_node_ex_v",            # ImGui::TreeNodeExV
    "tree_node_v",               # ImGui::TreeNodeV
]
