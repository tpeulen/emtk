"""A ``value`` with ``read_only: true`` is drawn dimmed, so a reported value does not read as one to
edit -- as the date and multi-line fields already were.

A settings form generated from a device's description shows measured values (a laser head's type,
its slot) beside settings; drawn like every other field, they invited edits that could not happen.
"""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


class _Model:
    slot = 200
    level = -50


def _colour_of(text: str, read_only: bool):
    spec = {"sections": [
        {"type": "value", "attr": "slot", "label": "Slot", "kind": "int",
         "read_only": read_only, "description": "d"},
        {"type": "value", "attr": "level", "label": "Level", "kind": "int", "description": "d"},
    ]}
    state, io, storage = FormState(), emtk.IO(), {}
    painter = None
    for _ in range(3):
        painter = RecordingPainter()
        with emtk.frame(painter, (0, 0, 400, 200), io=io, storage=storage):
            im.begin("t", (0, 0, 400, 200))
            draw_form(spec, _Model(), state)
            im.end()
    return next(t[6] for t in painter.texts if t[5] == text)


def _alpha(colour) -> int:
    return colour[3] if len(colour) > 3 else 255


def test_a_read_only_value_is_dimmed_and_an_editable_one_is_not():
    editable = _colour_of("-50", read_only=True)
    dimmed = _colour_of("200", read_only=True)
    plain = _colour_of("200", read_only=False)
    assert _alpha(dimmed) < _alpha(plain), "read-only text drawn at lower alpha"
    assert _alpha(editable) == _alpha(plain), "the editable field beside it is unchanged"
