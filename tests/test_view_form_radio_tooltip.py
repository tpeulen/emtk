"""A radio ``choice`` gives every button the section's description as its tooltip.

The drop-down branch did; the radio branch drew its buttons and set none, so a form that
preferred radios had controls with no tooltip and no way to say so in the spec.
"""

from __future__ import annotations

import emtk
from emtk import im, im_widgets
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form


class _Model:
    mode = "a"


def _tips(style):
    tips, buttons = [], []
    real_tip, real_radio = im_widgets.set_item_tooltip, im_widgets.radio_button

    def tip(text, *a, **k):
        tips.append((len(buttons), text))
        return real_tip(text, *a, **k)

    def radio(label, *a, **k):
        buttons.append(label)
        return real_radio(label, *a, **k)

    im_widgets.set_item_tooltip, im_widgets.radio_button = tip, radio
    try:
        spec = {"sections": [{"type": "choice", "attr": "mode", "options": ["a", "b", "c"],
                              "style": style, "description": "Pick the mode."}]}
        state, io, storage = FormState(), emtk.IO(), {}
        for _ in range(2):
            with emtk.frame(RecordingPainter(), (0, 0, 400, 200), io=io, storage=storage):
                im.begin("t", (0, 0, 400, 200))
                draw_form(spec, _Model(), state)
                im.end()
    finally:
        im_widgets.set_item_tooltip, im_widgets.radio_button = real_tip, real_radio
    return tips, buttons


def test_every_inline_radio_button_has_the_tooltip():
    tips, buttons = _tips("radio")
    assert len(buttons) >= 3
    assert {n for n, _ in tips} >= {1, 2, 3}, "each button must be followed by a tooltip"
    assert all(text == "Pick the mode." for _, text in tips)


def test_every_stacked_radio_button_has_the_tooltip():
    tips, buttons = _tips("radio_list")
    assert {n for n, _ in tips} >= {1, 2, 3}
