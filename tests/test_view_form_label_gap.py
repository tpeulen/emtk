"""The longest label of a grid column never touches the control beside it."""

from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter

from test_view_form import Driver


class _Model:
    short = 1
    longest = 2


def test_a_long_label_keeps_an_item_spacing_from_its_control():
    spec = {"sections": [
        {"type": "value", "attr": "short", "label": "Q", "kind": "int"},
        {"type": "value", "attr": "longest", "label": "Acceptor absorption", "kind": "int"},
    ]}
    driver = Driver(spec, _Model())
    driver.frame()
    label_w = len("Acceptor absorption") * RecordingPainter.GLYPH_W
    gap = driver.state.rects["longest"][0] - label_w
    assert gap >= emtk.Style().item_spacing[0] - 0.5
    assert driver.state.rects["short"][0] == driver.state.rects["longest"][0]
