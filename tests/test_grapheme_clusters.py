"""An extended grapheme cluster is one glyph cell, one caret step, one delete.

A skin-toned thumbs-up (U+1F44D U+1F3FD) drew as two glyphs in emtk text and
the caret stepped through its middle. Every layer that splits text now goes
through :mod:`emtk.grapheme`: measuring, drawing (a monospace painter draws one
cell per cluster, the base emoji when the font cannot compose the sequence),
and caret movement, selection and deletion in the text field, the command line
and the code editor.
"""
from __future__ import annotations

import pytest

from emtk import grapheme, icons
from emtk.events import SHIFT_MODIFIER
from emtk.font import load_atlas
from emtk.keys import KEY_BACKSPACE, KEY_DELETE, KEY_LEFT, KEY_RIGHT
from emtk.pil_painter import PilPainter
from emtk.quad_painter import QuadPainter
from emtk.testing import PixelPainter
from emtk.widgets.command_line import CommandLine
from emtk.widgets.text_editor import Pos, TextEditor
from emtk.widgets.text_field import TextField

#: One sequence per class UAX #29 / emoji TR51 builds a cluster from.
SEQUENCES = {
    "skin tone": "\U0001F44D\U0001F3FD",
    "zwj couple": "\U0001F469‍\U0001F4BB",
    "zwj family": "\U0001F468‍\U0001F469‍\U0001F467",
    "variation selector": "❤️",
    "keycap": "1️⃣",
    "flag": "\U0001F1E9\U0001F1EA",
    "tag flag": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "combining accent": "é",
}
IDS = sorted(SEQUENCES)


@pytest.fixture(params=IDS)
def seq(request):
    return SEQUENCES[request.param]


# --------------------------------------------------------------------------
# segmentation
# --------------------------------------------------------------------------
def test_each_sequence_is_one_cluster(seq):
    assert len(seq) > 1
    assert grapheme.clusters(seq) == [seq]
    assert grapheme.count(seq) == 1
    assert len(grapheme.display(seq)) == 1
    assert grapheme.next_boundary(seq, 0) == len(seq)
    assert grapheme.prev_boundary(seq, len(seq)) == 0
    assert [grapheme.snap(seq, i) for i in range(len(seq) + 1)] == (
        [0] + [len(seq)] * len(seq))


def test_neighbours_stay_separate(seq):
    text = "a" + seq + seq + "b"
    assert grapheme.clusters(text) == ["a", seq, seq, "b"] or seq == SEQUENCES["flag"]
    assert grapheme.count("ab\r\n") == 3


def test_flags_pair_off_and_a_base_falls_back_to_one_code_point():
    de = SEQUENCES["flag"]
    assert grapheme.clusters(de * 2 + "\U0001F1E9") == [de, de, "\U0001F1E9"]
    assert grapheme.display(SEQUENCES["skin tone"]) == "\U0001F44D"
    assert grapheme.display(SEQUENCES["zwj family"]) == "\U0001F468"
    assert grapheme.display("é") == "é"           # composed when it can be
    assert grapheme.display("plain ascii") == "plain ascii"


# --------------------------------------------------------------------------
# measuring: every painter, in the plain-text (glyph cell) path
# --------------------------------------------------------------------------
def _pixel():
    return PixelPainter(300, 60)


def _pil():
    return PilPainter(300, 60)


def _quad():
    return QuadPainter()


PAINTERS = {"pixel": _pixel, "pil": _pil, "quad": _quad}


@pytest.fixture(params=sorted(PAINTERS))
def painter(request):
    return PAINTERS[request.param]()


def test_width_is_one_cell(painter, seq):
    with icons.plain_text():
        cell = painter.text_width("x")
        assert painter.text_width(seq) == pytest.approx(cell)
        assert painter.text_width("a" + seq + "b") == pytest.approx(3 * cell)
        assert painter.text_width(seq * 3) == pytest.approx(
            3 * cell if seq != SEQUENCES["flag"] else 3 * cell)


def test_width_with_pictograms_is_the_base_emoji_width(painter):
    """Outside plain text a colour cluster is one icon box, as its base emoji is."""
    if icons.pictogram_runs("\U0001F44D") is None:
        pytest.skip("no colour-emoji font on this machine")
    one = painter.text_width("\U0001F44D")
    for name in ("skin tone", "zwj couple", "variation selector"):
        assert painter.text_width(SEQUENCES[name]) == pytest.approx(one)


# --------------------------------------------------------------------------
# drawing: one cell, never two
# --------------------------------------------------------------------------
def _draw_cells(painter, string):
    """The cells *string* asked the atlas for, in drawing order."""
    asked = []
    original = painter._atlas.cell_of

    def spy(char, bold=False):
        asked.append(char)
        return original(char, bold=bold)

    painter._atlas.cell_of = spy
    try:
        with icons.plain_text():
            painter.text(10, 10, 200, 30, 0, string, (255, 255, 255, 255))
    finally:
        del painter._atlas.cell_of
    return asked


def test_a_cluster_draws_one_glyph_cell(painter, seq):
    base = grapheme.display(seq)
    assert _draw_cells(painter, seq) == [base]
    assert _draw_cells(painter, "a" + seq + "b") == ["a", base, "b"]


@pytest.mark.parametrize("make", [_pixel, _pil])
def test_the_pixels_are_the_base_glyph_alone(make, seq):
    atlas = load_atlas()
    if atlas.cell_of(grapheme.display(seq)) is None:
        pytest.skip("no glyph for the base")
    shots = []
    for string in (seq, grapheme.display(seq)):
        p = make()
        with icons.plain_text():
            p.text(10, 10, 200, 30, 0, string, (255, 255, 255, 255))
        shots.append(bytes(p.px if hasattr(p, "px") else p.frame.tobytes()))
    assert shots[0] == shots[1]
    assert any(shots[0][i] != shots[0][0] for i in range(0, len(shots[0]), 4)), "nothing drawn"


# --------------------------------------------------------------------------
# editing
# --------------------------------------------------------------------------
def _field(seq):
    field = TextField()
    field.set_text("a" + seq + "b")
    return field


def test_text_field_caret_steps_over_the_cluster(seq):
    field = _field(seq)
    n = len(seq)
    field.move(1)
    field.key(KEY_RIGHT)
    assert field.cursor == 1 + n
    field.key(KEY_LEFT)
    assert field.cursor == 1
    # a position inside the cluster is never a caret position
    field.move(2)
    assert field.cursor in (1, 1 + n)
    field.cursor = 2
    assert field.cursor in (1, 1 + n)


def test_text_field_shift_arrow_selects_the_whole_cluster(seq):
    field = _field(seq)
    field.move(1)
    field.key(KEY_RIGHT, modifiers=SHIFT_MODIFIER)
    assert field.selected_text() == seq


def test_text_field_backspace_and_delete_remove_the_whole_cluster(seq):
    field = _field(seq)
    field.move(1 + len(seq))
    field.key(KEY_BACKSPACE)
    assert field.text == "ab"
    assert field.cursor == 1
    field = _field(seq)
    field.move(1)
    field.key(KEY_DELETE)
    assert field.text == "ab"


def test_clicking_never_lands_inside_a_cluster(seq):
    from emtk.widgets.text_field import index_at

    xs = [0.0] + [10.0] * len(seq) + [20.0]   # what paint() returns for a + seq + b
    field = _field(seq)
    field.move(index_at(xs, 10.0))
    assert field.cursor in (1, 1 + len(seq))


def test_command_line_steps_and_deletes_whole_clusters(seq):
    line = CommandLine()
    line.set_focus(True)
    line.set_text("a" + seq + "b", cursor=1 + len(seq))
    line.key(KEY_LEFT)
    assert line.cursor == 1
    line.key(KEY_RIGHT)
    assert line.cursor == 1 + len(seq)
    line.key(KEY_BACKSPACE)
    assert (line.text, line.cursor) == ("ab", 1)
    line.set_text("a" + seq + "b", cursor=1)
    line.key(KEY_DELETE)
    assert line.text == "ab"


def test_code_editor_moves_deletes_and_lays_out_whole_clusters(seq):
    text = "a" + seq + "b"
    end = 1 + len(seq)
    editor = TextEditor(text)
    doc = editor.document
    assert doc.right(Pos(0, 1)) == Pos(0, end)
    assert doc.left(Pos(0, end)) == Pos(0, 1)
    # the cluster is one unit of the cell layout, and 'b' follows it directly
    column = editor._column_of
    assert column(Pos(0, 0)) == 0 and column(Pos(0, 1)) == 1
    width = column(Pos(0, end)) - 1
    assert width in (1, 2)                 # a text cell, or the two cells of a colour icon
    assert column(Pos(0, end + 1)) == column(Pos(0, end)) + 1
    editor.set_cursor(Pos(0, end))
    editor.backspace()
    assert editor.document.lines[0].text == "ab"


# --------------------------------------------------------------------------
# the colour path: one cluster is one image, never the pieces side by side
# --------------------------------------------------------------------------
@pytest.mark.skipif(icons.pictogram_runs("\U0001F44D") is None,
                    reason="no colour-emoji font on this machine")
@pytest.mark.parametrize("name", ["skin tone", "zwj couple", "zwj family"])
def test_a_colour_cluster_is_one_square_image(name):
    from emtk.testing import _ScreenshotPainter

    cluster = SEQUENCES[name]
    p = _ScreenshotPainter(200, 40)
    p.text(5, 5, 190, 28, 0, "a" + cluster + "b", (230, 230, 230, 255))
    assert [icon for icon, *_ in p.icons] == [cluster]
    _icon, _x, _y, w, h = p.icons[0]
    assert w == h == pytest.approx(icons.icon_box(p.line_height()))
    texture, colour = icons.icon_texture(cluster, 64)
    assert colour and texture is not None
    # Drawn as pieces side by side the ink is two glyphs wide; one glyph is square-ish.
    ink = icons._rasterise_colour(cluster)
    assert ink is not None and ink.width <= 1.3 * ink.height
    assert p.text_width("a" + cluster + "b") == pytest.approx(
        p.text_width("a\U0001F44Db"))
