"""An ``info`` section with ``is_markdown`` is drawn as a document, not flattened.

Tables are a grid with the delimiter row's alignment, and every punctuation
mark of a paragraph leaves ink, at scale 1 and at scale 2.
"""
from __future__ import annotations

import pytest

import emtk
from emtk.testing import PixelPainter, RecordingPainter
from emtk.view_form import FormState, draw_form

TABLE = """| Name | Value | Unit |
|:-----|------:|:----:|
| tau | 2.5 | ns |
| gamma | 1.07 | - |
"""
PUNCT = list(".,=:;()!-+")


def _draw(painter, md, size=(500, 300)):
    spec = {"sections": [{"type": "info", "text": md, "is_markdown": True}]}
    io, state, store = emtk.IO(), FormState(), {}
    for _ in range(3):
        with emtk.frame(painter, (0, 0, *size), io=io, storage=store):
            emtk.begin("form", (0, 0, *size))
            draw_form(spec, object(), state)
            emtk.end()


def test_a_markdown_table_is_drawn_as_a_grid_with_alignment():
    p = RecordingPainter()
    _draw(p, TABLE)
    assert not any("|" in s for s in p.strings)
    texts = {t[5].strip(): t for t in p.texts}
    # Ink extents as drawn, in the face and weight each was drawn in (the header is bold:
    # measured in the regular weight it is ~2 px narrower in a wide face such as Verdana).
    bounds = {t[5].strip(): m["measured_bounds"] for t, m in zip(p.texts, p.text_metadata)}
    # right-aligned column: both numbers end on the same edge, "Value" too
    right = [bounds[k][0] + bounds[k][2] for k in ("2.5", "1.07", "Value")]
    assert max(right) - min(right) <= 1.5
    # centred column: shared centre
    centre = [texts[k][0] + p.text_width(texts[k][5]) / 2 for k in ("ns", "-", "Unit")]
    assert max(centre) - min(centre) <= 3.0  # bold header measures wider
    # left column starts at one x
    assert len({round(texts[k][0], 0) for k in ("Name", "tau", "gamma")}) == 1
    # a rule above, between and below the 3 rows, and a rule at every column edge
    rules_h = {round(f[1]) for f in p.fills if f[3] <= 1.5 and f[2] > 100}
    rules_v = {round(f[0]) for f in p.fills if f[2] <= 1.5 and f[3] > 10}
    assert len(rules_h) >= 4
    assert len(rules_v) >= 4


@pytest.mark.parametrize("scale", [1.0, 2.0])
def test_a_table_and_prose_render_at_device_scale(scale):
    p = PixelPainter(int(500 * scale), int(300 * scale), background=(0, 0, 0, 255), scale=scale)
    _draw(p, "Intro, with = signs.\n\n" + TABLE)
    assert sum(1 for i in range(0, len(p.px), 4) if p.px[i] > 60) > 200


@pytest.mark.parametrize("scale", [1.0, 2.0])
@pytest.mark.parametrize("ch", PUNCT)
def test_every_punctuation_mark_in_prose_has_ink(scale, ch):
    p = PixelPainter(int(120 * scale), int(60 * scale), background=(0, 0, 0, 255), scale=scale)
    _draw(p, f"a{ch}b", size=(120, 60))
    blank = PixelPainter(int(120 * scale), int(60 * scale), background=(0, 0, 0, 255), scale=scale)
    _draw(blank, "ab", size=(120, 60))
    lit = lambda q: sum(1 for i in range(0, len(q.px), 4) if q.px[i] > 60)
    assert lit(p) > lit(blank)


def test_a_dialog_can_drop_its_title_bar_close_for_one_in_the_content():
    from emtk.dialog_window import DialogWindow
    from emtk.help_guide import EmTkHelpWindow

    def shown(dlg):
        p = RecordingPainter()
        dlg.show()
        for _ in range(2):
            with emtk.frame(p, (0, 0, 600, 400), io=emtk.IO(), storage={}):
                dlg.begin((0, 0, 600, 400))
                dlg.end()
        return p.strings

    assert "×" in shown(DialogWindow("t", key="a"))
    assert "×" not in shown(DialogWindow("t", key="b", close_button=False))
    assert EmTkHelpWindow("Help", "# x\ntext").dlg.close_button is False
