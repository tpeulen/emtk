"""Inline rich-text runs: links sit inside the wrapped text, emphasis is real, nothing leaks raw."""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter
from emtk.widgets.markdown import parse_inline, render_markdown

SOURCE = (
    "Intro with **bold words**, `code_span` and *slanted* text, then "
    "[The four factors](docs/a.md#The four factors) in prose.\n\n"
    "- item with [a link](docs/b.md) and `x`\n\n"
    "| name | alias |\n|---|---|\n| I11 | `i_dd` |\n| I12 | **red** |\n"
)


def _draw(source, click=None, width=500.0, frames=5):
    io, storage, clicked = emtk.IO(), {}, []
    last = RecordingPainter()
    for frame in range(frames):
        io.mouse_clicked[0] = io.mouse_released[0] = False
        io.mouse_down[0] = False
        if click is not None and frame >= 2:
            hit = next(t for t in last.texts if t[5] == click)
            io.mouse_pos = (hit[0] + 3.0, hit[1] + 6.0)
            if frame == 3:
                io.mouse_clicked[0] = io.mouse_down[0] = True
            elif frame == 4:
                io.mouse_released[0] = True
        last = RecordingPainter()
        with emtk.frame(last, (0, 0, width, 600), io=io, storage=storage):
            im.begin("MD")
            render_markdown(source, on_link=clicked.append)
            im.end()
    return last, clicked


def test_runs_carry_style_and_target():
    runs = parse_inline("a **b** `c` [d *e*](t.md)")
    by = {r.text: r for r in runs}
    assert by["b"].bold and by["c"].code
    assert by["d "].target == "t.md" and by["e"].italic and by["e"].target == "t.md"


def test_no_markup_reaches_the_screen():
    painter, _ = _draw(SOURCE)
    drawn = " ".join(t[5] for t in painter.texts)
    for literal in ("**", "`", "](", "[The"):
        assert literal not in drawn
    assert "code_span" in drawn and "i_dd" in drawn and "red" in drawn


def test_link_text_is_drawn_exactly_once():
    painter, _ = _draw(SOURCE)
    words = [t[5] for t in painter.texts]
    assert words.count("four") == 1 and words.count("factors") == 1
    assert words.count("link") == 1


def test_bold_uses_the_bold_face_and_links_are_underlined():
    painter, _ = _draw(SOURCE)
    bold = {t[5] for t in painter.texts if t[7]}
    assert {"bold", "words"} <= bold
    assert "four" not in bold


def test_click_on_an_inline_link_calls_on_link():
    _painter, clicked = _draw(SOURCE, click="four")
    assert clicked == ["docs/a.md#The four factors"]
    _painter, clicked = _draw(SOURCE, click="link")
    assert clicked == ["docs/b.md"]


def test_link_words_stay_whole_when_a_line_breaks():
    source = "alpha " * 6 + "[Accurate FRET corrections](docs/x.md) omega"
    painter, _ = _draw(source, width=150.0)
    texts = [t for t in painter.texts if t[5] in ("Accurate", "FRET", "corrections")]
    assert [t[5] for t in texts] == ["Accurate", "FRET", "corrections"]
    assert max(t[0] + t[2] for t in painter.texts) <= 150.0 + 1.0
    assert len({round(t[1]) for t in painter.texts}) > 1
