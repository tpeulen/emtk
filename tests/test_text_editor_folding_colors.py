"""Line folding and hex-colour swatches in the ported text editor.

Folding is the one feature the port's header said it had deliberately left
out ("no caller"). The style manager and the JSON settings editor are both
callers now, so the editor folds again -- brace pairs, because that is one
rule that serves JSON, CSS/QSS and C-family code alike, and the collapsed
state rides on the line object (as markers do) so edits above a fold cannot
desynchronise the fold map from the text.

The hex swatch answers the other half of editing a stylesheet: the file is
mostly colours, and ``#aabbcc`` as grey text tells you nothing about the
colour it names.
"""
from __future__ import annotations


from emtk.widgets import text_editor as te
from emtk.testing import RecordingPainter


def _drawn(editor, w: float = 400.0, h: float = 200.0) -> RecordingPainter:
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, w, h)
    return painter


# --------------------------------------------------------------------------
# The fold map
# --------------------------------------------------------------------------
JSON_SAMPLE = """{
    "importer": {
        "active": true,
        "models": [
            "foo",
            "bar"
        ]
    },
    "count": 1
}"""


def _foldable() -> te.TextEditor:
    editor = te.TextEditor(JSON_SAMPLE, te.Language.json())
    editor.config.tab_size = 4
    return editor


def test_fold_regions_are_the_brace_pairs_of_the_document():
    """One fold per matching ``{``/``}`` (and ``[``/``]``) pair, innermost-first."""
    editor = _foldable()
    _drawn(editor)
    folds = editor.folds.regions()
    starts = {f.start.line for f in folds}
    assert starts == {0, 1, 3}  # the outer object, "importer", "models"
    by_start = {f.start: f for f in folds}
    assert by_start[te.Pos(0, 0)].end.line == 9    # closes on line 10 (``}``)
    assert by_start[te.Pos(1, 16)].end.line == 7   # the "importer" object
    assert by_start[te.Pos(3, 18)].end.line == 6   # the "models" list


def test_foldable_lines_are_marked_in_the_gutter():
    """A line that opens a region draws the fold control in the gutter."""
    editor = _foldable()
    _drawn(editor)
    assert editor.folds.foldable_at(0)
    assert editor.folds.foldable_at(1)
    assert not editor.folds.foldable_at(5)


def test_collapsing_hides_the_folded_lines_and_keeps_a_holder_row():
    editor = _foldable()
    _drawn(editor)
    assert editor.folds.toggle(1) is True
    assert editor.folds.is_collapsed(1) is True
    # display rows: lines 0 and 1, the interior (2-6) hidden, 7 on row 2
    assert editor.folds.display_row(9) == 4
    assert editor.folds.document_line(2) == 7
    # hidden lines have no display row
    assert editor.folds.display_row(3) is None


def test_toggling_again_restores_the_document_view():
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(1)
    assert editor.folds.toggle(1) is False
    assert not editor.folds.is_collapsed(1)
    assert editor.folds.display_row(3) == 3


def test_a_fold_inside_a_collapsed_outer_fold_is_hidden_too():
    """Collapsing the outer object hides everything, including inner folds."""
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(0)
    assert editor.folds.display_row(5) is None
    # the inner fold's line is hidden; its own collapsed flag is untouched
    editor.folds.toggle(0)
    assert editor.folds.display_row(5) == 5


def test_editing_above_a_fold_does_not_lose_the_collapse():
    """Collapse state rides on the line object, so an insert above moves it."""
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(1)
    editor.set_cursor(te.Pos(0, 0))
    editor.insert("# comment\n")
    _drawn(editor)
    # the fold was on the line that held "importer"; it is one line down now
    collapsed = [n for n, line in enumerate(editor.document.lines) if line.collapsed]
    assert collapsed == [2]
    assert editor.folds.is_collapsed(2)


def test_fold_map_rebuilds_after_an_edit_and_drops_stale_folds():
    editor = _foldable()
    _drawn(editor)
    assert editor.folds.foldable_at(1)
    editor.set_cursor(te.Pos(1, 17))  # just past the ``{`` of "importer"
    editor.backspace()
    _drawn(editor)
    assert not editor.folds.foldable_at(1)


def test_folding_survives_when_disabled():
    """No folding (the old behaviour) must keep working exactly as before."""
    editor = _foldable()
    editor.folds.toggle(1)
    editor.config.show_folds = False
    _drawn(editor)
    # every document line is on screen: the display map is the identity
    assert editor.folds.display_row(5) == 5


def test_hidden_lines_are_not_drawn_and_the_holder_shows_an_expansion_mark():
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(1)
    painter = _drawn(editor)
    # the folded-away text is not drawn
    drawn = " ".join(s for s in painter.strings)
    assert "bar" not in drawn
    assert "importer" in drawn
    # the holder row draws the ellipsis marker
    assert any("…" in s for s in painter.strings)


def test_scrolling_and_the_caret_use_display_rows():
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(1)
    editor.set_cursor(te.Pos(9, 0))  # the line after the collapsed block
    # draw at two visible rows, then move again: the follow uses the rows
    # the current box shows, and the caret lands inside them
    _drawn(editor, 400.0, 32.0)
    editor.set_cursor(te.Pos(9, 0))
    _drawn(editor, 400.0, 32.0)
    row_of_9 = editor.folds.display_row(9)
    assert row_of_9 is not None
    assert 0 <= row_of_9 - editor.first_visible_line < editor.visible_lines
    assert editor.cursors.main.end.line == 9


def test_click_in_gutter_toggles_the_fold():
    """The gutter control is a first-class click target."""
    editor = _foldable()
    _drawn(editor)
    gutter_x = editor._text_x - editor._glyph_w * 0.5
    hit = editor.press(gutter_x, 0 * editor._line_h, 0, 0, 400.0, 200.0)
    assert editor.folds.is_collapsed(0)
    assert hit is None or hit == editor.cursors.current.end  # no caret move


def test_press_on_a_folded_row_moves_the_caret_not_past_the_hidden_lines():
    editor = _foldable()
    _drawn(editor)
    editor.folds.toggle(1)
    where = editor.position_at(editor._text_x + 4.0, 1 * editor._line_h)
    # row 1 is the holder; the caret may sit on it, but rows below map to
    # document lines past the hidden block (never into it)
    assert where.line in (1, 9)


# --------------------------------------------------------------------------
# Hex-colour swatches
# --------------------------------------------------------------------------
CSS_SAMPLE = """window {
    background-color: #242424;
    border: 1px solid #ff8800;
}
menu { background-color: #abc; }
"""


def test_hex_literals_get_a_swatch_fill_in_the_true_colour():
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    _drawn(editor)
    swatches = editor.color_swatches()
    assert [s.text for s in swatches] == ["#242424", "#ff8800", "#abc"]
    assert swatches[0].colour == (0x24, 0x24, 0x24, 255)
    assert swatches[1].colour == (0xFF, 0x88, 0x00, 255)
    assert swatches[2].colour == (0xAA, 0xBB, 0xCC, 255)


def test_swatch_geometry_is_drawn_behind_the_token():
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    painter = _drawn(editor)
    fills = [c for c in painter.calls if c[0] == "fill_rect"]
    swatch = editor.color_swatches()[0]
    # a fill exists at the swatch's computed box with the swatch colour
    assert any(
        abs(c[1] - swatch.rect[0]) < 0.6 and abs(c[2] - (swatch.rect[1])) < 1.0
        for c in fills
    )


def test_swatch_colours_the_token_text_for_contrast():
    """``#242424`` on a dark background stays readable: the text is tinted."""
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    _drawn(editor)
    swatch = editor.color_swatches()[0]
    assert swatch.text_colour is not None


def test_disabled_swatch_config_draws_no_chips():
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    editor.config.show_color_swatches = False
    _drawn(editor)
    assert editor.color_swatches() == []


def test_an_unterminated_hex_literal_has_no_swatch():
    editor = te.TextEditor("a { color: #12; }", te.Language.css())
    _drawn(editor)
    assert editor.color_swatches() == []


def test_8_digit_hex_parses_the_alpha():
    editor = te.TextEditor("a { color: #11223344; }", te.Language.css())
    _drawn(editor)
    swatches = editor.color_swatches()
    assert swatches[0].colour == (0x11, 0x22, 0x33, 0x44)


def test_swatch_map_moves_with_an_edit():
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    _drawn(editor)
    editor.set_cursor(te.Pos(0, 0))
    editor.insert("// padding\n")
    _drawn(editor)
    swatches = editor.color_swatches()
    assert swatches[0].start == te.Pos(2, 22)  # moved down a line


def test_swatch_positions_are_folding_aware():
    """A swatch on a hidden line draws nothing; on the holder it stays put."""
    editor = te.TextEditor(CSS_SAMPLE, te.Language.css())
    _drawn(editor)
    editor.folds.toggle(0)
    swatch = editor.color_swatches()[0]
    assert swatch.visible is False


def test_no_language_no_swatch():
    editor = te.TextEditor("# not a colour\n")
    _drawn(editor)
    assert editor.color_swatches() == []


def test_typing_over_the_whole_document_never_indexes_stale_folds():
    """Select-all + type shrinks the text before update() re-reads the pairs."""
    editor = _foldable()
    _drawn(editor)
    assert editor.folds.regions()
    editor.select_all()
    editor.insert("[]")  # one line now; the old pairs end on line 9
    _drawn(editor)
    assert editor.folds.row_count() == 1
