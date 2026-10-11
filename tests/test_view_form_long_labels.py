"""A field whose label leaves it no room is drawn under the label, not past the right edge."""

from __future__ import annotations

from emtk import im
from emtk.testing import MetricPainter
from emtk.view_form import FormState, draw_sections


class _Model:
    lifetime = 4.2
    other = 7.5


SPEC = [
    {"type": "value", "attr": "lifetime", "kind": "float", "label": "Unquenched lifetime (ns)"},
    {"type": "value", "attr": "other", "kind": "float", "label": "Donor diffusion coefficient (Å²/ns)"},
]


def _rects(width):
    state = FormState()
    for _ in range(2):
        with im.frame(MetricPainter(), (0, 0, width, 200)):
            im.begin("w", (0, 0, width, 200))
            draw_sections(SPEC, _Model(), state, n_col=1, titles=False)
            im.end()
    return state.rects


def test_a_field_stays_inside_the_window_when_its_label_is_long():
    for width in (200.0, 260.0):
        rects = _rects(width)
        for name in ("lifetime", "other"):
            x, y, w, h = rects[name]
            assert w >= 30.0 and x + w <= width, (name, rects[name], width)


def test_a_wide_window_keeps_the_label_beside_its_field():
    rects = _rects(700.0)
    x, y, w, h = rects["lifetime"]
    assert x > 100.0  # the field starts after its label, on the label's own line
    assert abs(y - rects["other"][1]) > 5  # one row per field
