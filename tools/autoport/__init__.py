r"""Port Dear ImGui C++ to cmtk Python -- mechanically, and say where it can't.

The claim this tool exists to test: cmtk's API is close enough to Dear ImGui's
that a *script*, with no understanding of the code it is moving, produces a
port that runs and draws the same picture. Every rule below is mechanical --
the same one a person applies, written down so it applies the same way every
time:

* ``ImGui::Button("Save")``              -> ``im.button("Save")``
* ``ImGui::SliderFloat("a", &a, 0, 1)``  -> ``_changed, a = im.slider_float("a", a, 0, 1)``
  (C++ writes through ``T*``; Python returns the value beside the flag)
* ``ImGuiCol_Button``                    -> ``im.Col.BUTTON``
* ``CamelCase``                          -> ``snake_case`` (one shared rule)
* ``ImVec2(x, y)``                       -> ``(x, y)``; ``.x``/``.y`` -> ``[0]``/``[1]``
* ``float f = 0.5f;``                    -> ``f = 0.5``
* ``ImSin/ImLerp/sinf/powf``             -> ``math.sin/im_lerp/math.sin/math.pow``
* ``ImGui::Text("%d items", n)``         -> ``im.text("%d items" % n)``

What a script cannot do honestly, it does not pretend to: any construct the
tables do not cover is passed through under a ``# TODO(autoport):`` comment
naming what a hand must decide. Never a silent wrong answer.

Use::

    python tools/autoport/__main__.py tests/fixtures/extensions/imgui-knobs.cpp \
        --module imgui_knobs --origin "imgui-knobs, MIT" --out DIR
"""
# ruff: noqa: E402  (the sys.path bootstrap below must run before these imports)

from __future__ import annotations

import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cmtk.im_compat import mechanical_name
from autoport.expressions import Porter
from autoport.statements import StatementPorter
from autoport.port_file import port_file
from autoport.cli import main
from autoport.lex import _fix_printf

__all__ = ["Porter", "StatementPorter", "port_file", "main",
           "mechanical_name", "_fix_printf"]
