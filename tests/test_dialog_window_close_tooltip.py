"""The close button of a ``DialogWindow`` carries a tooltip, so an app that opens a dialog has no untooltipped control."""

from __future__ import annotations

import emtk
from emtk import im, im_widgets
from emtk.dialog_window import DialogWindow
from emtk.testing import RecordingPainter


def test_the_close_button_has_a_tooltip():
    tips = []
    real = im_widgets.set_item_tooltip
    im_widgets.set_item_tooltip = lambda text, *a, **k: (tips.append(text), real(text, *a, **k))[1]
    try:
        dialog = DialogWindow("Title", size=(300, 160), key="t")
        dialog.show()
        io, storage = emtk.IO(), {}
        for _ in range(3):
            with emtk.frame(RecordingPainter(), (0, 0, 600, 400), io=io, storage=storage):
                dialog.begin((0, 0, 600, 400))
                dialog.end()
    finally:
        im_widgets.set_item_tooltip = real
    assert any("Close" in t for t in tips), tips
