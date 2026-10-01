"""A spec ``value`` of ``kind: "password"`` is drawn masked, never in clear.

``emtk.view_form`` had no password kind: a spec author who wrote ``kind: "password"`` got an ordinary
text field showing the secret. A port had to hand-draw its password entries to avoid it.
"""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


class _Model:
    secret = "hunter2-correct-horse"
    visible = "plain-text-value"


def _strings(kind_secret):
    spec = {"sections": [
        {"type": "value", "attr": "secret", "label": "Secret", "kind": kind_secret, "description": "d"},
        {"type": "value", "attr": "visible", "label": "Visible", "kind": "str", "description": "d"},
    ]}
    state, io, storage = FormState(), emtk.IO(), {}
    painter = None
    for _ in range(3):
        painter = RecordingPainter()
        with emtk.frame(painter, (0, 0, 400, 200), io=io, storage=storage):
            im.begin("t", (0, 0, 400, 200))
            draw_form(spec, _Model(), state)
            im.end()
    return " ".join(painter.strings)


def test_a_password_field_never_draws_its_text():
    text = _strings("password")
    assert "hunter2" not in text and "correct-horse" not in text
    assert "plain-text-value" in text


def test_an_ordinary_str_field_still_shows_its_text():
    assert "hunter2-correct-horse" in _strings("str")
