"""``ImGui::`` → ``cmtk.``: the translation is mechanical, and this measures it.

The goal for cmtk is that porting a Dear ImGui program needs no thought about
names: ``::`` becomes ``.``, ``CamelCase`` becomes ``snake_case``, and a
pointer argument becomes a returned value. Whether that *works* is not an
opinion -- it is a list, and the list is Dear ImGui's own public API, vendored
beside this file (``imgui_api.txt``, ``imdrawlist_api.txt``, taken from
``imgui.h``) so the check is hermetic.

So the test is: translate every published name mechanically, and see whether
``cmtk`` answers to it. The count may only go up. A name that is not there yet is
not a failure -- cmtk does not claim to be all of Dear ImGui -- but a name that
*was* there and is gone, or a rename that breaks the mechanical rule, is one,
because that is the property the whole exercise rests on.

Where the count stands is in ``COVERED``. Raise it when you add a function;
never lower it.
"""
from __future__ import annotations

import pathlib
import re

import pytest

import cmtk
from cmtk.drawlist import DrawList

HERE = pathlib.Path(__file__).parent

#: Every published name resolves. Not "most" -- a port that stops at an
#: `AttributeError` on line 400 of a transliteration is a port that has to be
#: read and understood before it can run, which is the thing this is for.
COVERED_IMGUI = 362
COVERED_DRAWLIST = 60


def snake(name: str) -> str:
    """``CamelCase`` -> ``snake_case``: the whole naming half of a port."""
    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    out = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", out)
    return out.lower()


def _names(filename: str) -> list[str]:
    return [line.strip() for line in (HERE / filename).read_text().splitlines()
            if line.strip()]


def _resolved(names, namespace) -> list[str]:
    return [n for n in names if hasattr(namespace, snake(n))]


# --------------------------------------------------------------------------- #
# The rule itself
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("camel,expected", [
    ("Button", "button"),
    ("SliderFloat", "slider_float"),
    ("BeginChild", "begin_child"),
    ("PushStyleColor", "push_style_color"),
    ("SetNextItemWidth", "set_next_item_width"),
    ("TextUnformatted", "text_unformatted"),
    ("IsItemHovered", "is_item_hovered"),
    ("AddRectFilled", "add_rect_filled"),
    ("PathArcTo", "path_arc_to"),
    ("GetIO", "get_io"),
])
def test_the_naming_rule(camel, expected):
    assert snake(camel) == expected


# --------------------------------------------------------------------------- #
# ...applied to the real API
# --------------------------------------------------------------------------- #
def test_every_imgui_name_translates():
    names = _names("imgui_api.txt")
    missing = [n for n in names if not hasattr(cmtk, snake(n))]
    assert not missing, f"{len(missing)} of {len(names)} do not translate: " + \
        ", ".join(f"ImGui::{n} -> cmtk.{snake(n)}" for n in missing[:30])
    assert len(names) >= COVERED_IMGUI


def test_every_drawlist_name_translates():
    names = _names("imdrawlist_api.txt")
    missing = [n for n in names if not hasattr(DrawList, snake(n))]
    assert not missing, ", ".join(missing[:30])
    assert len(names) >= COVERED_DRAWLIST


def test_nothing_is_a_stub():
    """A name that exists and does nothing is worse than one that is missing.

    Nothing in the surface raises `NotImplementedError` on being called with
    no arguments *because it refuses to work* -- where the reference needs an
    operation cmtk lacked, the painter gained an optional one and cmtk falls
    back to something visible instead.
    """
    names = _names("imgui_api.txt") + _names("imdrawlist_api.txt")
    refusing = [n for n in names
                if getattr(getattr(cmtk, snake(n), None), "cmtk_unsupported", False)]
    assert not refusing, refusing


def test_the_widgets_a_port_reaches_for_first_are_all_there():
    """Coverage as a number can hide a hole where it matters most.

    These are the calls in Dear ImGui's own "Hello, world!" and in the demo's
    Basic section -- if any of them needs a footnote, the translation is not
    mechanical for the first program anybody brings across.
    """
    for name in ("Begin", "End", "Text", "TextColored", "TextDisabled",
                 "TextWrapped", "BulletText", "LabelText", "Button",
                 "SmallButton", "InvisibleButton", "ArrowButton", "Checkbox",
                 "CheckboxFlags", "RadioButton", "ProgressBar", "Bullet",
                 "SliderFloat", "SliderInt", "SliderAngle", "DragFloat",
                 "DragInt", "InputText", "InputTextWithHint", "InputFloat",
                 "InputInt", "ColorEdit3", "ColorEdit4", "ColorButton",
                 "Selectable", "Combo", "CollapsingHeader", "TreeNode",
                 "TreePop", "Separator", "SeparatorText", "SameLine",
                 "NewLine", "Spacing", "Dummy", "Indent", "Unindent",
                 "BeginGroup", "EndGroup", "PushID", "PopID",
                 "PushStyleColor", "PopStyleColor", "PushItemFlag",
                 "PopItemFlag", "SetNextItemWidth", "AlignTextToFramePadding",
                 "SetTooltip", "SetItemTooltip", "IsItemHovered",
                 "IsItemActive", "IsItemClicked", "CalcTextSize", "GetIO",
                 "GetStyle", "GetWindowDrawList", "BeginChild", "EndChild"):
        assert hasattr(cmtk, snake(name)), f"ImGui::{name} -> cmtk.{snake(name)}"


def test_the_package_and_the_module_agree():
    """`cmtk.button` and `cmtk.im.button` are the same function.

    The package resolves names lazily from a generated map; a name bound only
    at import time inside `im` would answer there and not here, which is the
    half of the translation a port actually types.
    """
    from cmtk import im

    for name in _names("imgui_api.txt"):
        attr = snake(name)
        assert getattr(cmtk, attr) is getattr(im, attr), attr
