"""A narrow fixed-width control in a form grid is drawn in the column the layout gave it.

The grid floors every control at 30 px when it draws it, but a fixed-width
column -- a ``weight`` 0 button row, a toggle -- is laid out at its natural
width. A ``+`` button narrower than the floor was therefore drawn wider than
its column and ran into the control beside it.
"""

from __future__ import annotations

from emtk import im
from emtk.testing import MetricPainter
from emtk.view_form import FormState, draw_sections


class _Model:
    tw = 2.0
    auto = True

    def add(self):
        pass


def _rects(spec, width=420.0):
    state = FormState()

    def gui():
        im.begin("w", (0, 0, width, 120))
        draw_sections(spec, _Model(), state, n_col=3, titles=False)
        im.end()

    for _ in range(2):
        with im.frame(MetricPainter(), (0, 0, width, 120)):
            gui()
    return state.rects


def test_a_narrow_button_does_not_run_into_the_next_column():
    spec = [
        {"type": "value", "attr": "tw", "kind": "float", "label": "TW [ms]"},
        {"type": "button_row", "weight": 0, "buttons": [{"label": "+", "action": "add"}]},
        {"type": "toggle", "attr": "auto", "label": "Auto load"},
    ]
    rects = _rects(spec)
    bx, _by, bw, _bh = rects["add"]
    tx = rects["auto"][0]
    assert bx + bw <= tx, f"the button ({bx}+{bw}) overlaps the toggle at {tx}"
    vx, _vy, vw, _vh = rects["tw"]
    assert vx + vw <= bx, "the value field overlaps the button"
