"""Every ``ImGui::`` name answers to something. Nothing pretends.

A port should never stop at an ``AttributeError``. So this installs, for each
of Dear ImGui's published names, whatever emtk has to offer under the name the
mechanical translation produces:

* the implementation under its readable name, where the mechanical spelling
  and a name a person would write disagree;
* the sibling a ``va_list`` form shares -- ``TextV`` is ``text``, because
  Python's own formatting leaves nothing for a second entry point to do.

Everything else already answers to its mechanical spelling directly. Nothing
here is a stub: where the reference needs an operation emtk did not have --
images, fonts -- the *painter* gained an optional one and emtk falls back
visibly rather than pretending.

The naming rule
---------------
``CamelCase`` -> ``snake_case`` by inserting an underscore at every
lowercase-to-uppercase boundary. It handles the whole API except names with an
acronym followed by a word -- ``ColorConvertHSVtoRGB`` comes out as
``color_converths_vto_rgb``, which no one would write. Those keep a readable
name *and* answer to the mechanical one, so a transliterated port and a human
both find them.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import im_core, im_widgets

__all__ = ["MECHANICAL_ALIASES", "VARIADIC", "install", "mechanical_name"]


def mechanical_name(camel: str) -> str:
    """The name a straight ``CamelCase`` -> ``snake_case`` port produces."""
    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", camel)
    out = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", out)
    return out.lower()


#: Where the mechanical spelling and the readable one differ. The readable name
#: is the real function; the mechanical one is installed beside it.
MECHANICAL_ALIASES: dict[str, str] = {
    "ColorConvertHSVtoRGB": "color_convert_hsv_to_rgb",
    "ColorConvertRGBtoHSV": "color_convert_rgb_to_hsv",
}

#: The ``...V`` forms take a ``va_list``. Python's ``%`` and f-strings make the
#: caller do the formatting, so each is the same function as its sibling.
VARIADIC = {
    "TextV": "text", "TextColoredV": "text_colored",
    "TextDisabledV": "text_disabled", "TextWrappedV": "text_wrapped",
    "BulletTextV": "bullet_text", "LabelTextV": "label_text",
    "SetTooltipV": "set_tooltip", "SetItemTooltipV": "set_item_tooltip",
    "TreeNodeV": "tree_node", "TreeNodeExV": "tree_node_ex",
    "LogTextV": "log_text", "DebugLogV": "debug_log",
}

def install(namespace, names) -> list[str]:
    """Give *namespace* the mechanical spelling of every name in *names*.

    Returns which ones needed one. A name already answering to its mechanical
    spelling is left alone; the rest are pointed at the implementation that
    carries a readable name, or at the sibling a ``va_list`` form shares.
    """
    aliased = []
    for camel in names:
        wanted = mechanical_name(camel)
        if hasattr(namespace, wanted):
            continue
        target = MECHANICAL_ALIASES.get(camel) or VARIADIC.get(camel)
        if target and hasattr(namespace, target):
            setattr(namespace, wanted, getattr(namespace, target))
            aliased.append(camel)
    return aliased
