#!/usr/bin/env python
r"""Scaffold a cmtk port of a Dear ImGui widget -- in the shape that ports easily.

Two thirds of a port is transcribing the C++ body; the third that is data
(enums, palettes, options structs, word lists) this script does exactly. What
changed from the first scaffolder is the *shape* it emits, because the shape
decides how much of the body can be transliterated line by line:

* an **im-style function** ``def <module>(ctx, ...)`` written against
  :mod:`chimol.cmtk.im` -- ``ctx.draw`` (the ``ImDrawList`` names),
  ``ctx.io`` (``ImGuiIO``), ``ctx.layout`` (``ItemSize/SameLine/Indent``),
  ``ctx.style``, ``ctx.push_id/get_id``, ``ctx.get_storage``,
  ``ctx.button_behavior`` -- with the C++ body of every public method pasted
  in as **comment blocks**, each line prefixed by the Python spelling of the
  ImGui name it uses (a lookup table below), so the translation is one line
  under each comment rather than a search;
* a **retained control** ``class <Cls>(ImWidget)`` wrapping it, which is what
  the chrome, the gallery and the tests use;
* a test on ``chimol.cmtk.testing.RecordingPainter`` that draws it and presses it;
* the module registered in ``CONTROL_MODULES`` and the lazy name map regenerated;
* a **porting checklist** printed at the end: which draw primitives, IO
  fields, ID/storage calls, style vars and popups the source uses -- detected
  by grepping it -- so what is left is a list, not a reading.

Use::

    python tools/port_imgui_widget.py ~/dev/chisurf/junk/imspinner/imspinner.h \
        --module spinner --class Spinner --origin "imspinner, MIT" [--test-dir ...] [--print]

It does not translate C++ statements. Every attempt at that produces Python
that runs and is wrong in a way that reads as intentional.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "chimol" / "cmtk"
DEFAULT_TEST_DIR = pathlib.Path.home() / "dev" / "chisurf" / "chisurf" / "plugins" / "chimol" / "test"

#: ImGui spellings -> the cmtk.im spelling, for the comment prefixes and the checklist.
IM_NAMES: dict[str, str] = {
    "GetWindowDrawList": "ctx.draw", "GetForegroundDrawList": "ctx.draw", "GetBackgroundDrawList": "ctx.draw",
    "AddLine": "ctx.draw.add_line", "AddRect": "ctx.draw.add_rect", "AddRectFilled": "ctx.draw.add_rect_filled",
    "AddRectFilledMultiColor": "ctx.draw.add_rect_filled_multi_color", "AddQuad": "ctx.draw.add_quad",
    "AddQuadFilled": "ctx.draw.add_quad_filled", "AddTriangle": "ctx.draw.add_triangle",
    "AddTriangleFilled": "ctx.draw.add_triangle_filled", "AddCircle": "ctx.draw.add_circle",
    "AddCircleFilled": "ctx.draw.add_circle_filled", "AddNgon": "ctx.draw.add_ngon",
    "AddNgonFilled": "ctx.draw.add_ngon_filled", "AddPolyline": "ctx.draw.add_polyline",
    "AddConvexPolyFilled": "ctx.draw.add_convex_poly_filled", "AddBezierCubic": "ctx.draw.add_bezier_cubic",
    "AddBezierQuadratic": "ctx.draw.add_bezier_quadratic", "AddText": "ctx.draw.add_text",
    "AddImage": "ctx.draw.add_image  # TODO: no image op yet (plan P1)",
    "PathClear": "ctx.draw.path_clear", "PathLineTo": "ctx.draw.path_line_to", "PathArcTo": "ctx.draw.path_arc_to",
    "PathArcToFast": "ctx.draw.path_arc_to", "PathBezierCubicCurveTo": "ctx.draw.path_bezier_cubic_curve_to",
    "PathBezierQuadraticCurveTo": "ctx.draw.path_bezier_quadratic_curve_to", "PathRect": "ctx.draw.path_rect",
    "PathStroke": "ctx.draw.path_stroke", "PathFillConvex": "ctx.draw.path_fill_convex",
    "PushClipRect": "ctx.draw.push_clip_rect", "PopClipRect": "ctx.draw.pop_clip_rect",
    "CalcTextSize": "ctx.draw.calc_text_size",
    "GetIO": "ctx.io", "MousePos": "ctx.io.mouse_pos", "MouseDown": "ctx.io.mouse_down",
    "MouseClicked": "ctx.io.mouse_clicked", "MouseReleased": "ctx.io.mouse_released",
    "MouseDoubleClicked": "ctx.io.mouse_double_clicked", "MouseWheel": "ctx.io.mouse_wheel",
    "MouseWheelH": "ctx.io.mouse_wheel_h", "KeyCtrl": "ctx.io.key_ctrl", "KeyShift": "ctx.io.key_shift",
    "KeyAlt": "ctx.io.key_alt", "KeySuper": "ctx.io.key_super", "DeltaTime": "ctx.io.delta_time",
    "GetTime": "ctx.io.now", "GetFrameCount": "ctx.io.frame_count", "GetMouseDragDelta": "ctx.io.mouse_drag_delta",
    "IsMouseDown": "ctx.io.mouse_down[b]", "IsMouseClicked": "ctx.io.mouse_clicked[b]",
    "IsMouseReleased": "ctx.io.mouse_released[b]", "IsMouseDoubleClicked": "ctx.io.mouse_double_clicked[b]",
    "GetCursorScreenPos": "ctx.layout.cursor()", "GetCursorPos": "ctx.layout.cursor()",
    "SetCursorScreenPos": "ctx.layout.reset(x, y)", "ItemSize": "ctx.item_size", "ItemAdd": "ctx.item_add",
    "SameLine": "ctx.layout.same_line", "NewLine": "ctx.layout.new_line", "Indent": "ctx.layout.indent",
    "Unindent": "ctx.layout.unindent", "Dummy": "ctx.layout.dummy", "Separator": "ctx.layout.separator",
    "Spacing": "ctx.layout.spacing", "BeginGroup": "ctx.layout.begin_group", "EndGroup": "ctx.layout.end_group",
    "Columns": "ctx.layout.columns", "NextColumn": "ctx.layout.next_column",
    "GetContentRegionAvail": "ctx.layout.avail()", "GetFrameHeight": "ctx.layout.row_height",
    "GetTextLineHeight": "ctx.layout.line_h", "GetTextLineHeightWithSpacing": "ctx.layout.row_height",
    "BeginChild": "ctx.begin_child", "EndChild": "ctx.end_child",
    "PushID": "ctx.push_id", "PopID": "ctx.pop_id", "GetID": "ctx.get_id",
    "GetStateStorage": "ctx.get_storage()", "ImGuiStorage": "ctx.get_storage()",
    "IsItemHovered": "ctx.is_item_hovered", "IsItemActive": "ctx.is_item_active", "IsItemClicked": "ctx.is_item_clicked",
    "GetItemRectMin": "ctx.get_item_rect()", "GetItemRectMax": "ctx.get_item_rect()",
    "ButtonBehavior": "ctx.button_behavior", "SetActiveID": "ctx.set_active_id", "ClearActiveID": "ctx.clear_active_id",
    "GetStyle": "ctx.style", "FramePadding": "ctx.style.frame_padding", "ItemSpacing": "ctx.style.item_spacing",
    "ItemInnerSpacing": "ctx.style.item_inner_spacing", "FrameRounding": "ctx.style.frame_rounding",
    "GrabMinSize": "ctx.style.grab_min_size", "GetColorU32": "ctx.style.color", "PushStyleColor": "# style push: use ctx.style.colors[...]",
    "PopStyleColor": "# style pop", "PushStyleVar": "# style var push", "PopStyleVar": "# style var pop",
    "OpenPopup": "ctx.open_popup", "BeginPopup": "ctx.begin_popup", "EndPopup": "ctx.end_popup",
    "IsPopupOpen": "ctx.is_popup_open", "CloseCurrentPopup": "ctx.close_current_popup",
    "SetTooltip": "ctx.set_tooltip", "BeginTooltip": "ctx.set_tooltip", "EndTooltip": "# tooltip end",
    "SetKeyboardFocusHere": "# focus: FocusManager (plan P1)", "IM_COL32": "(r, g, b, a)",
    "ImVec2": "(x, y)", "ImMin": "min", "ImMax": "max", "ImClamp": "clamp", "ImLerp": "lerp", "ImFabs": "abs",
    "IM_PI": "math.pi", "ImCos": "math.cos", "ImSin": "math.sin", "ImSqrt": "math.sqrt",
}

CHECKLIST_GROUPS = {
    "draw primitives": ("AddLine", "AddRect", "AddRectFilled", "AddRectFilledMultiColor", "AddQuad", "AddQuadFilled",
                        "AddTriangle", "AddTriangleFilled", "AddCircle", "AddCircleFilled", "AddNgon", "AddNgonFilled",
                        "AddPolyline", "AddConvexPolyFilled", "AddBezierCubic", "AddBezierQuadratic", "AddText",
                        "AddImage", "PathLineTo", "PathArcTo", "PathArcToFast", "PathBezierCubicCurveTo",
                        "PathBezierQuadraticCurveTo", "PathRect", "PathStroke", "PathFillConvex", "PushClipRect"),
    "io fields": ("MousePos", "MouseDown", "MouseClicked", "MouseReleased", "MouseDoubleClicked", "MouseWheel",
                  "KeyCtrl", "KeyShift", "KeyAlt", "KeySuper", "DeltaTime", "GetTime", "GetMouseDragDelta",
                  "IsMouseDown", "IsMouseClicked", "IsMouseReleased", "IsMouseDoubleClicked"),
    "layout": ("GetCursorScreenPos", "SetCursorScreenPos", "ItemSize", "ItemAdd", "SameLine", "NewLine", "Indent",
               "Unindent", "Dummy", "Separator", "BeginGroup", "EndGroup", "Columns", "GetContentRegionAvail",
               "BeginChild", "EndChild"),
    "ids and storage": ("PushID", "PopID", "GetID", "GetStateStorage", "ImGuiStorage"),
    "item state": ("IsItemHovered", "IsItemActive", "IsItemClicked", "ButtonBehavior", "SetActiveID", "ClearActiveID"),
    "style": ("GetStyle", "FramePadding", "ItemSpacing", "ItemInnerSpacing", "FrameRounding", "GrabMinSize",
              "GetColorU32", "PushStyleColor", "PushStyleVar"),
    "popups / tooltips / focus": ("OpenPopup", "BeginPopup", "IsPopupOpen", "SetTooltip", "BeginTooltip",
                                  "SetKeyboardFocusHere"),
}

#: C++ spellings mapped to Python ones. ``ImU32`` is a packed colour in the
#: reference and a ``(r, g, b, a)`` tuple here, which is why it maps to the
#: chrome's ``Colour`` rather than to ``int``.
_TYPES = {
    "bool": ("bool", "False"),
    "float": ("float", "0.0"),
    "double": ("float", "0.0"),
    "int": ("int", "0"),
    "size_t": ("int", "0"),
    "unsigned": ("int", "0"),
    "ImU32": ("Colour", "(255, 255, 255, 255)"),
    "ImWchar": ("str", '""'),
    "std::string": ("str", '""'),
    "char": ("str", '""'),
}


def _snake(name: str) -> str:
    """Turn a C++ ``CamelCase`` or ``camelCase`` name into ``snake_case``."""
    body = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", body).lower()


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------
def extract_enums(text: str) -> dict[str, list[str]]:
    """Return every ``enum``'s members, keyed by the enum's name.

    Parameters
    ----------
    text : str
        C++ source.

    Returns
    -------
    dict of str to list of str
        Member names in declaration order, which is what makes them safe to
        turn into an ``IntEnum``: the reference indexes palettes by these
        values, so the order *is* the meaning.

    Notes
    -----
    Members with an explicit ``= value`` keep only the name; a sentinel called
    ``count`` or ``COUNT`` is dropped, because Python's ``len()`` answers that
    and a member called ``count`` on an ``IntEnum`` shadows a real method.
    """
    found: dict[str, list[str]] = {}
    pattern = re.compile(
        r"enum(?:\s+class)?\s+(\w+)\s*(?::\s*\w+\s*)?\{(.*?)\}\s*;", re.S
    )
    for match in pattern.finditer(text):
        members = []
        for raw in match.group(2).split(","):
            body = re.sub(r"//.*", "", raw)
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S).strip()
            name = body.split("=")[0].strip()
            # The sentinel is spelled ``count`` in ImGuiColorTextEdit and
            # ``DataFormat_COUNT`` in imgui_club, so both spellings go: it is
            # not a value, and a member called ``count`` on an ``IntEnum``
            # shadows a real method.
            sentinel = name.lower() == "count" or name.lower().endswith("_count")
            if name and not sentinel and re.fullmatch(r"\w+", name):
                members.append(name)
        if members:
            found[match.group(1)] = members
    return found


def extract_palettes(text: str) -> list[tuple[str, list[tuple[tuple[int, ...], str]]]]:
    """Return every run of ``IM_COL32`` literals, with the comment on each line.

    Returns
    -------
    list of tuple
        ``(name, [((r, g, b, a), comment), ...])``. The name is the enclosing
        function's, which for the reference's palettes is ``GetDarkPalette`` and
        friends. The comments matter: they are what say which palette *slot*
        each colour is, and a colour list without them is unreviewable.
    """
    palettes: list[tuple[str, list[tuple[tuple[int, ...], str]]]] = []
    entry = re.compile(
        r"IM_COL32\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*,?\s*(?://\s*(.*))?"
    )
    for block in re.finditer(r"(\w+)\s*\([^)]*\)\s*\{(.*?)\n\}", text, re.S):
        colours = [
            ((int(m[1]), int(m[2]), int(m[3]), int(m[4])), (m[5] or "").strip())
            for m in entry.finditer(block.group(2))
        ]
        if len(colours) >= 3:
            palettes.append((block.group(1), colours))
    return palettes


def extract_options(text: str, struct: str = "Config") -> list[tuple[str, str, str]]:
    """Return an options struct's fields as ``(python_name, type, default)``.

    Parameters
    ----------
    text : str
        C++ source.
    struct : str, optional
        The struct's name. ``Config`` for ImGuiColorTextEdit; a widget that
        keeps its options as plain members instead (``imgui_club``'s memory
        editor does) yields nothing here and is transcribed by hand -- which
        the caller is told rather than left to discover from an empty
        dataclass.
    """
    match = re.search(rf"struct\s+{re.escape(struct)}\s*\{{(.*?)\n\s*\}}", text, re.S)
    if match is None:
        return []
    fields: list[tuple[str, str, str]] = []
    for line in match.group(1).splitlines():
        body = re.sub(r"//.*", "", line).strip().rstrip(";")
        if not body or body.startswith(("struct", "//", "#")):
            continue
        found = re.match(r"^(?:const\s+)?([\w:]+(?:\s*\*)?)\s+(\w+)\s*(?:=\s*(.+))?$", body)
        if found is None:
            continue
        c_type, name, default = found.group(1), found.group(2), found.group(3)
        py_type, py_default = _TYPES.get(c_type.replace(" ", ""), ("object", "None"))
        if default is not None:
            default = default.strip()
            if default in ("true", "false"):
                py_default = default.capitalize()
            elif re.fullmatch(r"-?\d+", default):
                py_default = default
            elif re.fullmatch(r"-?\d*\.\d+f?", default):
                py_default = default.rstrip("f")
            elif default.startswith('"'):
                py_default = default
        fields.append((_snake(name), py_type, py_default))
    return fields


def extract_word_lists(text: str) -> dict[str, list[str]]:
    """Return every ``static const char* const NAME[] = {...}`` as a word list.

    These are the keyword tables, and they are the single most error-prone
    thing to copy by hand: they are long, they are not alphabetical, and a
    missing entry has no symptom except one word that does not colour.

    Notes
    -----
    The array name alone is not a key: the reference declares eleven languages
    and every one of them has an array called ``keywords``, so keying by name
    merges C's keywords into Python's. The enclosing function is what
    distinguishes them, so the key is ``Function.array`` when a function can be
    found by scanning back from the declaration -- which is the difference
    between a usable extraction and one that has to be thrown away.
    """
    found: dict[str, list[str]] = {}
    pattern = re.compile(
        r"static\s+const\s+char\s*\*\s*const\s+(\w+)\s*\[\]\s*=\s*\{(.*?)\}\s*;", re.S
    )
    scope = re.compile(r"(\w+)\s*\(\s*\)\s*\{")
    for match in pattern.finditer(text):
        words = re.findall(r'"([^"]*)"', match.group(2))
        if not words:
            continue
        before = text[: match.start()]
        owner = scope.findall(before[-4000:])
        key = f"{owner[-1]}_{match.group(1)}" if owner else match.group(1)
        found.setdefault(key, []).extend(words)
    return found


def extract_methods(text: str, class_name: str) -> list[tuple[str, str]]:
    """Return the class's public API as ``(cpp_name, python_name)``.

    The reference's own convention is what makes this reliable: Dear ImGui and
    both ported widgets start every *public* member function with an uppercase
    letter and every private one with a lowercase letter, and say so in a
    comment. So the public API is exactly the uppercase-initial declarations,
    and no C++ parsing is needed to find it.

    Notes
    -----
    Only *declarations* count, so the scan stops at the ``protected``/``private``
    label that both references put between their public API and their internals,
    and skips any line carrying ``::`` -- an out-of-line definition in the
    ``.cpp`` is the same method again, and counting it inflates the checklist
    with duplicates until nobody reads it. On ImGuiColorTextEdit that is the
    difference between 253 entries and the ninety-odd the class really has.
    """
    for opener in (f"class {class_name}", f"struct {class_name}"):
        if opener in text:
            text = text.split(opener, 1)[1]
            break
    for closer in ("\nprotected:", "\nprivate:"):
        if closer in text:
            text = text.split(closer, 1)[0]
    seen: list[tuple[str, str]] = []
    pattern = re.compile(
        r"^\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+)*"
        r"[\w:<>&*,\s]+?\b([A-Z]\w+)\s*\([^;{]*\)\s*(?:const\s*)?[;{]",
        re.M,
    )
    for match in pattern.finditer(text):
        # Only the *return type and name* may not carry ``::`` -- the argument
        # list is full of ``std::string`` and testing the whole match drops
        # every method that takes one, which is most of them.
        head = match.group(0).split("(")[0]
        name = match.group(1)
        if "::" in head or name in (class_name, "IM_COL32") or name.startswith("Im"):
            continue
        python = _snake(name)
        if python not in {one[1] for one in seen}:
            seen.append((name, python))
    return seen



# --------------------------------------------------------------------------
# Bodies: the C++ text of each public method, for the comment blocks
# --------------------------------------------------------------------------
def extract_bodies(text: str, class_name: str, methods: list[tuple[str, str]]) -> dict[str, str]:
    """``{cpp_name: body}`` for every method whose definition (``{ ... }``) can be found."""
    out: dict[str, str] = {}
    for cpp, _py in methods:
        m = re.search(r"\b(?:%s::)?%s\s*\([^;{]*\)\s*(?:const\s*)?\{" % (re.escape(class_name), re.escape(cpp)), text)
        if m is None:
            continue
        i = m.end()
        depth = 1
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        out[cpp] = text[m.end(): i - 1].strip("\n")
    return out


def _annotate(line: str) -> str:
    """Prefix a C++ line with the cmtk.im spellings of the ImGui names it uses."""
    names = [n for n in IM_NAMES if re.search(r"\b%s\b" % re.escape(n), line)]
    hint = "; ".join(f"{n} -> {IM_NAMES[n]}" for n in names[:3])
    return f"    #   {line.rstrip()}" + (f"    # {hint}" if hint else "")


def render_checklist(text: str) -> str:
    lines = ["porting checklist (found in the source):"]
    for group, names in CHECKLIST_GROUPS.items():
        used = [n for n in names if re.search(r"\b%s\b" % re.escape(n), text)]
        if used:
            lines.append(f"  {group}: " + ", ".join(f"{n} -> {IM_NAMES.get(n, '?')}" for n in used))
    return "\n".join(lines)


_MODULE_TEMPLATE = '''"""{title}

Where it comes from
-------------------
{origin}

TODO: name the file(s) read and what the widget is for.

Deliberate divergences
----------------------
TODO: every place this does *not* match the reference, and why.

What is deliberately not ported
-------------------------------
TODO: the features left out, and what has no caller for them.

Shape
-----
``{fn}(ctx, ...)`` is the immediate-mode function, transliterated from the C++
against :class:`chimol.cmtk.im.Context` (``ctx.draw`` is the ``ImDrawList``,
``ctx.io`` the ``ImGuiIO``, ``ctx.layout`` the cursor). :class:`{cls}` wraps
it as a retained control for the chrome, the gallery and the tests.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .im import ButtonFlags, Context, ImWidget
from .painter import Colour
from .style import clamp

__all__ = {exports}

{data}

def {fn}(ctx: Context, config: "{config_cls} | None" = None):
    """TODO: one line saying what it draws and what it returns.

    Translate the comment blocks below one line each; delete the block when its
    line is written. The names after ``->`` are where each ImGui call went.
    """
    config = config or {config_cls}()
    raise NotImplementedError("port {fn} from {source}")
{bodies}

class {cls}(ImWidget):
    """The retained control: ``{cls}(config)`` draws through :func:`{fn}`."""

    def __init__(self, config: "{config_cls} | None" = None, **kwargs) -> None:
        super().__init__({fn}, config or {config_cls}(), **kwargs)
'''

_TEST_TEMPLATE = '''"""Painter-level tests for the ported {module} control (no toolkit)."""
from __future__ import annotations

import pytest

from chimol.cmtk import {module}
from chimol.cmtk.testing import RecordingPainter


@pytest.mark.xfail(raises=NotImplementedError, reason="scaffolded; port the body", strict=False)
def test_it_draws_without_a_toolkit():
    control = {module}.{cls}()
    painter = RecordingPainter()
    control.draw(painter, 0.0, 0.0, 320.0, 120.0)
    assert painter.fills or painter.strokes or painter.strings or painter.triangles


@pytest.mark.xfail(raises=NotImplementedError, reason="scaffolded; port the body", strict=False)
def test_a_press_reaches_it():
    control = {module}.{cls}()
    control.draw(RecordingPainter(), 10.0, 20.0, 100.0, 40.0)
    assert control.contains(50.0, 30.0)
    control.press(50.0, 30.0, 10.0, 20.0, 100.0, 40.0)
    control.release(50.0, 30.0, 10.0, 20.0, 100.0, 40.0)
'''


def render_module(module, cls, origin, enums, palettes, options, words, methods, bodies, source) -> str:
    blocks: list[str] = []
    exports = [cls, module]
    for name, members in enums.items():
        exports.append(name)
        lines = [f"class {name}(IntEnum):", f'    """TODO: what {name} distinguishes."""', ""]
        lines += [f"    {_snake(one).upper()} = {index}" for index, one in enumerate(members)]
        blocks.append("\n".join(lines))
    for name, colours in palettes:
        constant = _snake(name).upper()
        exports.append(constant)
        lines = [f"#: The reference's ``{name}``, as the chrome's 0-255 tuples.", f"{constant}: tuple[Colour, ...] = ("]
        for (r, g, b, a), comment in colours:
            value = f"({r}, {g}, {b})" if a == 255 else f"({r}, {g}, {b}, {a})"
            lines.append(f"    {value},{'  # ' + comment if comment else ''}")
        lines.append(")")
        blocks.append("\n".join(lines))
    for name, entries in words.items():
        constant = _snake(name).upper()
        exports.append(constant)
        joined = "\n".join(f'    "{one} "' for one in entries)
        blocks.append(f"#: The reference's ``{name}`` table, verbatim.\n{constant} = frozenset(\n{joined}\n    .split()\n)")
    config_cls = f"{cls}Config"
    exports.append(config_cls)
    lines = ["@dataclass", f"class {config_cls}:", '    """The reference\'s options, field for field."""', ""]
    lines += [f"    {n}: {k} = {d}" for n, k, d in options] or ["    pass"]
    blocks.append("\n".join(lines))
    body_blocks = []
    for cpp, py in methods:
        body = bodies.get(cpp)
        body_blocks.append(f"\n    # ---- {cpp}() -> {py}() " + ("-" * max(4, 60 - len(cpp) - len(py))))
        if body is None:
            body_blocks.append("    #   (declaration only; body not found in the sources given)")
            continue
        for line in body.splitlines()[:400]:
            body_blocks.append(_annotate(line))
    head = "from enum import IntEnum\n" if enums else ""
    text = _MODULE_TEMPLATE.format(
        title=f"{cls}: a port of {source}.", origin=origin,
        exports="[\n" + "".join(f'    "{one}",\n' for one in exports) + "]",
        data="\n\n\n".join(blocks) + "\n", cls=cls, fn=module, config_cls=config_cls,
        bodies="\n".join(body_blocks) + "\n", source=source,
    )
    if head:
        text = text.replace("from dataclasses import dataclass", "from dataclasses import dataclass\n" + head.rstrip())
    return text


def render_test(module: str, cls: str) -> str:
    return _TEST_TEMPLATE.format(module=module, cls=cls)


def _register(module: str) -> bool:
    path = UI_DIR / "__init__.py"
    text = path.read_text()
    if f'"{module}"' in text:
        return False
    marker = '    "keys",\n)'
    if marker not in text:
        raise SystemExit("CONTROL_MODULES marker not found in cmtk/__init__.py")
    path.write_text(text.replace(marker, f'    "{module}",\n{marker}', 1))
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("sources", nargs="+", type=pathlib.Path)
    parser.add_argument("--module", required=True, help="Python module name, snake_case")
    parser.add_argument("--class", dest="cls", default="")
    parser.add_argument("--struct", default="Config")
    parser.add_argument("--origin", default="TODO: the checkout, the author, the licence")
    parser.add_argument("--test-dir", type=pathlib.Path, default=DEFAULT_TEST_DIR)
    parser.add_argument("--print", dest="show", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    text = "\n".join(one.read_text(errors="replace") for one in args.sources)
    cls = args.cls or "".join(part.capitalize() for part in args.module.split("_"))
    enums = extract_enums(text)
    palettes = extract_palettes(text)
    options = extract_options(text, args.struct)
    words = extract_word_lists(text)
    methods = extract_methods(text, cls)
    bodies = extract_bodies(text, cls, methods)
    print(f"mined {sum(one.stat().st_size for one in args.sources) // 1024} kB: {len(enums)} enums, "
          f"{len(palettes)} palettes, {len(options)} options, {len(words)} word lists, "
          f"{len(methods)} public methods ({len(bodies)} bodies found)")
    module_text = render_module(args.module, cls, args.origin, enums, palettes, options, words, methods, bodies,
                                source=", ".join(str(one) for one in args.sources))
    test_text = render_test(args.module, cls)
    checklist = render_checklist(text)
    if args.show:
        print(module_text)
        print("---- test ----")
        print(test_text)
        print(checklist)
        return 0
    module_path = UI_DIR / f"{args.module}.py"
    test_path = args.test_dir / f"test_ui_{args.module}.py"
    for path, body in ((module_path, module_text), (test_path, test_text)):
        if path.exists() and not args.force:
            print(f"refusing to overwrite {path} (use --force)", file=sys.stderr)
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        print(f"wrote {path}")
    if _register(args.module):
        print(f"registered {args.module!r} in CONTROL_MODULES")
    subprocess.run([sys.executable, str(ROOT / "tools" / "gen_names.py")], check=False)
    print()
    print(checklist)
    print("\nstill to do, in source order:")
    for cpp, python in methods:
        print(f"  {cpp}() -> {python}()  [{'body pasted' if cpp in bodies else 'no body found'}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
