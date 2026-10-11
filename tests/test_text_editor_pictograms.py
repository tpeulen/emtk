"""A pictogram typed into the code editor takes two cells, everywhere.

The editor lays text out by monospace cell. Since captions draw an emoji as a
colour image (``icons.pictogram_runs``) a typed emoji came out wider than the
one cell the layout gave it and overlapped the next character. The editor now
has one cell rule -- a colour pictogram cluster is :data:`te.ICON_CELLS` (two,
East-Asian-wide) cells -- that its layout, caret, selection, hit-testing,
cursor movement and drawing all go through, and it draws the cluster itself as
a colour image fitted into those cells. The same on every real painter.
"""
from __future__ import annotations

import pytest

from emtk import icons
from emtk.keys import KEY_BACKSPACE
from emtk.pil_painter import PilPainter
from emtk.quad_painter import QuadPainter
from emtk.testing import PixelPainter
from emtk.widgets import text_editor as te
from emtk.widgets.text_editor import Pos, TextEditor

pytestmark = pytest.mark.skipif(not icons.icon_spans("a😀b"),
                                reason="no colour-emoji font on this machine")


def _recording(base):
    class Recording(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.texts = []
            self.images = []
            self.rects = []

        def text(self, x, y, w, h, align, string, colour, bold=False):
            self.texts.append((x, string))
            super().text(x, y, w, h, align, string, colour, bold)

        def image(self, x, y, w, h, handle, *rest, **kw):
            self.images.append((getattr(handle, "icon", None), x, y, w, h))
            super().image(x, y, w, h, handle, *rest, **kw)

        def fill_rect(self, x, y, w, h, colour):
            self.rects.append((x, y, w, h, tuple(colour)))
            super().fill_rect(x, y, w, h, colour)

    return Recording


def _quad():
    p = _recording(QuadPainter)()
    p.image_uv_resolver = lambda handle: ((0.0, 0.0), (1.0, 1.0))
    return p


PAINTERS = {
    "pixel": lambda: _recording(PixelPainter)(400, 120),
    "pil": lambda: _recording(PilPainter)(400, 120),
    "gpu": _quad,
}

SELECTION = (1, 2, 3, 99)


@pytest.fixture(params=sorted(PAINTERS))
def painter(request):
    return PAINTERS[request.param]()


def _editor(text):
    editor = TextEditor(text)
    editor.config.show_line_numbers = False
    editor.config.highlight_current_line = False
    editor.config.selection_color = SELECTION
    return editor


def _draw(editor, painter):
    editor.draw(painter, 0.0, 0.0, 400.0, 120.0)
    return editor._text_x, editor._glyph_w, editor._line_h


def test_a_pictogram_is_two_columns_in_layout():
    editor = _editor("a😀b👍🏽c")
    column = editor._column_of
    assert [column(Pos(0, i)) for i in range(len("a😀b👍🏽c") + 1)] == [
        0, 1, 3, 4, 4, 6, 7]       # the skin tone has no stop of its own
    assert editor._index_at_column(0, 1) == 1
    assert editor._index_at_column(0, 2) == 1      # inside the emoji: its start
    assert editor._index_at_column(0, 3) == 2


def test_caret_x_after_an_emoji_is_the_drawn_advance(painter):
    editor = _editor("a😀b")
    _draw(editor, painter)            # a first draw gives the editor its width
    editor.set_cursor(Pos(0, 2))
    editor.config.carets_visible = True
    painter.rects.clear()
    painter.texts.clear()
    painter.images.clear()
    text_x, gw, lh = _draw(editor, painter)
    caret = [r for r in painter.rects if r[2] <= gw * 0.5 and r[3] < lh]
    assert caret and caret[-1][0] == pytest.approx(text_x + 3 * gw)
    # ... and that is exactly where the next character is drawn
    (b_x,) = [x for x, string in painter.texts if string == "b"]
    assert b_x == pytest.approx(text_x + 3 * gw)


def test_the_emoji_is_a_colour_image_inside_its_two_cells(painter):
    editor = _editor("a😀b")
    text_x, gw, lh = _draw(editor, painter)
    (icon, x, y, w, h), = [i for i in painter.images if i[0] == "😀"]
    assert w == h <= lh + 1e-6
    assert x >= text_x + gw - 1e-6
    assert x + w <= text_x + 3 * gw + 1e-6           # no overlap with the next character
    (b_x,) = [bx for bx, string in painter.texts if string == "b"]
    assert x + w <= b_x + 1e-6
    # nothing handed to the painter as text carries the emoji
    assert all("😀" not in string for _x, string in painter.texts)


def test_clicking_right_of_an_emoji_puts_the_caret_after_it(painter):
    editor = _editor("a😀b👍🏽c")
    text_x, gw, lh = _draw(editor, painter)
    y = lh * 0.5

    def at(cells):
        return editor.position_at(text_x + cells * gw, y)

    assert at(0.2) == Pos(0, 0)
    assert at(0.9) == Pos(0, 1)           # nearer the end of a than its start
    assert at(1.4) == Pos(0, 1)           # left half of the emoji: before it
    assert at(2.2) == Pos(0, 2)           # right half: after it
    assert at(2.9) == Pos(0, 2)
    assert at(3.6) == Pos(0, 3)           # after b, before the thumbs-up
    assert at(4.4) == Pos(0, 3)           # left half of the two-code-point emoji
    assert at(5.2) == Pos(0, 5)           # right half: after both code points
    assert at(6.6) == Pos(0, 6)           # after c


def test_clicking_right_half_of_a_wide_cluster_lands_after_all_its_code_points(painter):
    editor = _editor("x👍🏽y")
    text_x, gw, lh = _draw(editor, painter)
    assert editor.position_at(text_x + 1.2 * gw, lh * 0.5) == Pos(0, 1)
    assert editor.position_at(text_x + 2.6 * gw, lh * 0.5) == Pos(0, 3)
    assert editor.position_at(text_x + 3.6 * gw, lh * 0.5) == Pos(0, 4)


def test_selection_covers_the_emoji_exactly(painter):
    editor = _editor("a😀b")
    _draw(editor, painter)
    editor.select_region(Pos(0, 1), Pos(0, 2))
    painter.rects.clear()
    painter.texts.clear()
    painter.images.clear()
    text_x, gw, lh = _draw(editor, painter)
    (x, y, w, h, colour), = [r for r in painter.rects if r[4] == SELECTION]
    assert x == pytest.approx(text_x + gw)
    assert w == pytest.approx(2 * gw)
    # the emoji image sits inside that highlight
    (_i, ix, _y, iw, _h), = [i for i in painter.images if i[0] == "😀"]
    assert x - 1e-6 <= ix and ix + iw <= x + w + 1e-6


def test_the_caret_steps_over_a_whole_cluster_and_backspace_deletes_it():
    editor = _editor("x👍🏽y")
    editor.set_cursor(Pos(0, 1))
    editor.move_right()
    assert editor.cursors.main.end == Pos(0, 3)
    editor.move_left()
    assert editor.cursors.main.end == Pos(0, 1)
    editor.move_right()
    editor.key(KEY_BACKSPACE)
    assert editor.text == "xy"


def test_plain_text_is_laid_out_as_before(painter):
    editor = _editor("ab\tc")
    text_x, gw, lh = _draw(editor, painter)
    assert [editor._column_of(Pos(0, i)) for i in range(5)] == [0, 1, 2, 4, 5]
    assert editor.position_at(text_x + 1.4 * gw, lh * 0.5) == Pos(0, 1)
    assert editor.position_at(text_x + 3.4 * gw, lh * 0.5) == Pos(0, 2)   # whole tab is "before"
    assert editor.position_at(text_x + 3.6 * gw, lh * 0.5) == Pos(0, 3)
    assert not painter.images


def test_a_pictogram_is_drawn_the_same_on_every_painter():
    positions = {}
    for name, make in PAINTERS.items():
        p = make()
        editor = _editor("a😀b")
        text_x, gw, lh = _draw(editor, p)
        (_i, x, _y, w, _h), = [i for i in p.images if i[0] == "😀"]
        (b_x,) = [bx for bx, s in p.texts if s == "b"]
        positions[name] = ((x - text_x) / gw, w / gw, (b_x - text_x) / gw)
    first = next(iter(positions.values()))
    for name, got in positions.items():
        assert got == pytest.approx(first, abs=0.02), name
    assert first[2] == pytest.approx(3.0)


def test_the_cell_rule_is_the_icon_rule():
    assert te.ICON_CELLS == 2
    assert icons.icon_spans("a😀b") == ((1, 2),)
    assert icons.icon_spans("x👍🏽y") == ((1, 3),)
