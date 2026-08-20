"""Painter-level tests for the ported colourising text editor.

No GUI toolkit: the editor is drawn against the recording painter, which is
what the painter seam exists for and what a control that quietly grew a Qt
dependency fails first.

The tests are grouped the way the port is: the colouriser, the document and
its coordinates, the cursors, undo, brackets, the line operations, and the
drawing. Each names the behaviour it protects rather than the method it calls,
because several of these are the reference's *bugs already fixed once* -- the
preferred column across a short line, the multi-cursor edit order -- and a
test called ``test_move_up`` would not say so.
"""
from __future__ import annotations

import pathlib

import pytest

from cmtk.events import ALT_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER
from cmtk.keys import (
    KEY_BACKSPACE,
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_LEFT,
    KEY_RETURN,
    KEY_TAB,
    KEY_UP,
)
from cmtk.widgets import text_editor as te
from cmtk.testing import RecordingPainter

#: The reference checkout. Gitignored and re-clonable, so the tests that read
#: it skip rather than fail when it is absent.
REFERENCE = (
    pathlib.Path(__file__).resolve().parents[4] / "junk" / "ImGuiColorTextEdit"
)


def _drawn(editor, w: float = 400.0, h: float = 200.0) -> RecordingPainter:
    """Draw *editor* once and return the painter that recorded it."""
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, w, h)
    return painter


# --------------------------------------------------------------------------
# Colouriser
# --------------------------------------------------------------------------
def test_a_keyword_a_string_and_a_comment_get_three_different_colours():
    """The one thing a colourising editor must do, at all."""
    editor = te.TextEditor('def f():  # note\n    return "x"\n', te.Language.python())
    _drawn(editor)
    first = editor.document.lines[0]
    assert first.colours[0] == int(te.Token.KEYWORD)          # def
    assert first.colours[4] == int(te.Token.IDENTIFIER)       # f
    assert first.colours[10] == int(te.Token.COMMENT)         # #
    second = editor.document.lines[1]
    assert second.colours[11] == int(te.Token.STRING)         # "


def test_a_multi_line_comment_recolours_every_line_after_it():
    """Opening ``/*`` at the top must reach the bottom.

    This is the state machine's whole reason for existing: a line's colours
    depend on the state the previous line left, and the reference propagates
    that forward one line at a time. A per-line colouriser passes every
    single-line test and gets this wrong.
    """
    editor = te.TextEditor("int a;\nint b;\nint c;\n", te.Language.c())
    _drawn(editor)
    assert editor.document.lines[2].colours[0] == int(te.Token.DECLARATION)

    editor.set_cursor(te.Pos(0, 0))
    editor.insert("/*")
    _drawn(editor)
    assert editor.document.lines[2].colours[0] == int(te.Token.COMMENT)
    assert editor.document.lines[2].state == te.LineState.IN_COMMENT


def test_a_triple_quote_is_tried_before_a_single_quote():
    """``\"\"\"`` must not read as an empty string followed by a quote.

    The order of the tests in the ``IN_TEXT`` scan is load-bearing, and getting
    it wrong colours a Python docstring as code from the second line on.
    """
    editor = te.TextEditor('"""doc\nstill doc\n"""\ncode = 1\n', te.Language.python())
    _drawn(editor)
    assert editor.document.lines[1].colours[0] == int(te.Token.STRING)
    assert editor.document.lines[3].colours[0] == int(te.Token.IDENTIFIER)


def test_a_case_insensitive_language_matches_a_keyword_in_any_case():
    """SQL is the reference's case-insensitive language, so it is the test."""
    editor = te.TextEditor("SELECT x FROM t\n", te.Language.sql())
    _drawn(editor)
    assert editor.document.lines[0].colours[0] == int(te.Token.KEYWORD)


def test_no_language_leaves_every_character_plain():
    """A document with no language is not a document with a broken one."""
    editor = te.TextEditor("def f():\n", None)
    _drawn(editor)
    assert set(editor.document.lines[0].colours) == {int(te.Token.TEXT)}


@pytest.mark.skipif(not REFERENCE.is_dir(), reason="reference checkout absent")
def test_the_word_tables_still_match_the_reference():
    """The generated keyword tables have not drifted from ``TextEditor.cpp``.

    They are 873 words, they are not alphabetical in the source, and a word
    lost in transcription colours one identifier wrong in one language and
    fails nothing else. So they are extracted rather than typed -- and this
    re-extracts them and compares, which is the only way anybody would find out
    that an edit had quietly changed one.
    """
    from build_tools.dev_utils.port_imgui_widget import extract_word_lists

    source = (REFERENCE / "TextEditor.cpp").read_text(errors="replace")
    reference = extract_word_lists(source)
    for key, mine in te._WORDS.items():
        assert set(reference[key]) == set(mine), f"{key} has drifted"


# --------------------------------------------------------------------------
# Document and coordinates
# --------------------------------------------------------------------------
def test_inserting_across_a_line_break_returns_the_position_after_it():
    """Multi-line insert has to report where the caret ended up."""
    document = te.Document("ab\n")
    end = document.insert_text(te.Pos(0, 1), "X\nY")
    assert end == te.Pos(1, 1)
    assert document.get_text() == "aX\nYb\n"


def test_deleting_across_lines_joins_the_ends():
    """The classic off-by-one: the tail of the last line must survive."""
    document = te.Document("one\ntwo\nthree\n")
    document.delete_text(te.Pos(0, 1), te.Pos(2, 2))
    assert document.get_text() == "oree\n"


def test_word_movement_stops_at_the_three_run_kinds():
    """ctrl+Left stops between a word, a space and a punctuation run."""
    document = te.Document("alpha  beta(gamma)")
    assert document.find_word_start(te.Pos(0, 5)) == te.Pos(0, 0)
    assert document.find_word_end(te.Pos(0, 7)) == te.Pos(0, 11)
    assert document.word_at(te.Pos(0, 13)) == "gamma"


def test_a_search_wraps_once_and_then_stops():
    """Find-next must reach a match above the caret without looping."""
    document = te.Document("needle\nhay\nhay\n")
    found = document.find_text(te.Pos(2, 0), "needle")
    assert found is not None and found[0] == te.Pos(0, 0)
    assert document.find_text(te.Pos(0, 0), "absent") is None


# --------------------------------------------------------------------------
# Cursors
# --------------------------------------------------------------------------
def test_the_preferred_column_survives_a_short_line():
    """Down onto a short line and back up must land where it started.

    Storing the clamped column instead is the reference's ``preferredColumn``
    bug, and it is invisible until a short line sits between two long ones.
    """
    editor = te.TextEditor("aaaaaaaaaa\nbb\ncccccccccc\n")
    editor.set_cursor(te.Pos(0, 9))
    editor.move_down()
    assert editor.cursors.main.end == te.Pos(1, 2)
    editor.move_down()
    assert editor.cursors.main.end == te.Pos(2, 9)


def test_two_cursors_on_the_same_spot_become_one():
    """Otherwise one keystroke types twice."""
    editor = te.TextEditor("abc\n")
    editor.cursors.set_cursor(te.Pos(0, 1))
    editor.cursors.add_cursor(te.Pos(0, 1))
    editor.cursors.merge_overlapping()
    assert len(editor.cursors) == 1

    # ...and two at different places stay two.
    editor.cursors.add_cursor(te.Pos(0, 3))
    editor.cursors.merge_overlapping()
    assert len(editor.cursors) == 2


def test_a_multi_cursor_insert_edits_from_the_last_caret_backwards():
    """Every caret must get the text at the position the user saw.

    Editing forwards shifts the offsets the later carets were holding, so the
    second insert lands one character further along each time. Backwards is
    the fix, and the symptom of getting it wrong is a staircase.
    """
    editor = te.TextEditor("a a a\n")
    editor.cursors.set_cursor(te.Pos(0, 0))
    editor.cursors.add_cursor(te.Pos(0, 2))
    editor.cursors.add_cursor(te.Pos(0, 4))
    editor.insert("X")
    assert editor.text == "Xa Xa Xa\n"


def test_add_next_occurrence_walks_forward_from_the_newest_caret():
    """ctrl+D twice must select the second and third copies, not the same one."""
    editor = te.TextEditor("tau tau tau\n")
    editor.select_region(te.Pos(0, 0), te.Pos(0, 3))
    assert editor.add_next_occurrence()
    assert editor.add_next_occurrence()
    assert len(editor.cursors) == 3
    assert {one.selection()[0].index for one in editor.cursors} == {0, 4, 8}


# --------------------------------------------------------------------------
# Undo
# --------------------------------------------------------------------------
def test_undo_and_redo_round_trip_one_gesture_at_a_time():
    """A typed word is one transaction, not one per character.

    It is not: each :meth:`insert` is its own transaction, which is what the
    reference does too. The property this protects is that the *stack* is
    consistent -- undoing everything reaches the original text exactly.
    """
    editor = te.TextEditor("start\n")
    for piece in ("a", "b", "c"):
        editor.insert(piece)
    while editor.undo():
        pass
    assert editor.text == "start\n"
    while editor.redo():
        pass
    assert editor.text == "abcstart\n"


def test_undo_restores_the_carets_it_was_made_with():
    """Undoing a multi-cursor edit must put the carets back."""
    editor = te.TextEditor("a a\n")
    editor.cursors.set_cursor(te.Pos(0, 0))
    editor.cursors.add_cursor(te.Pos(0, 2))
    editor.insert("Z")
    editor.undo()
    assert len(editor.cursors) == 2


def test_typing_after_an_undo_discards_the_redone_future():
    """The stack is linear; a branch would make redo ambiguous."""
    editor = te.TextEditor("")
    editor.insert("one")
    editor.undo()
    editor.insert("two")
    assert not editor.transactions.can_redo


# --------------------------------------------------------------------------
# Brackets
# --------------------------------------------------------------------------
def test_brackets_are_coloured_by_nesting_level_and_an_orphan_is_an_error():
    """Three levels cycle, and an unmatched closer goes red."""
    editor = te.TextEditor("f(g(h(x))))\n", te.Language.python())
    _drawn(editor)
    line = editor.document.lines[0]
    assert line.colours[1] == int(te.Token.BRACKET_LEVEL1)
    assert line.colours[3] == int(te.Token.BRACKET_LEVEL2)
    assert line.colours[5] == int(te.Token.BRACKET_LEVEL3)
    assert line.colours[10] == int(te.Token.BRACKET_ERROR)


def test_a_bracket_inside_a_string_does_not_match():
    """Only characters the colouriser called punctuation are candidates."""
    editor = te.TextEditor('x = "(" + y\n', te.Language.python())
    _drawn(editor)
    assert len(editor.bracketeer) == 0


# --------------------------------------------------------------------------
# Line operations
# --------------------------------------------------------------------------
def test_a_mixed_block_comments_in_rather_than_out():
    """"All commented", not "any": the alternative deletes a real ``#``."""
    editor = te.TextEditor("# already\nplain\n", te.Language.python())
    editor.select_region(te.Pos(0, 0), te.Pos(1, 5))
    editor.toggle_comments()
    assert editor.text.splitlines() == ["# # already", "# plain"]


def test_toggling_an_all_commented_block_removes_the_prefix():
    """And removes the space the toggle added, not one the user typed."""
    editor = te.TextEditor("# one\n# two\n", te.Language.python())
    editor.select_region(te.Pos(0, 0), te.Pos(1, 5))
    editor.toggle_comments()
    assert editor.text.splitlines() == ["one", "two"]


def test_indent_and_deindent_are_inverses():
    """Including on a line whose indent is not a whole tab stop."""
    editor = te.TextEditor("  body\n")
    editor.select_all()
    editor.indent_lines()
    assert editor.document.get_line_text(0) == "      body"
    editor.deindent_lines()
    assert editor.document.get_line_text(0) == "  body"


def test_moving_a_line_down_swaps_it_with_the_one_below():
    """And carries the caret, or the next press edits the wrong line."""
    editor = te.TextEditor("first\nsecond\nthird\n")
    editor.set_cursor(te.Pos(0, 2))
    editor.move_lines(down=True)
    assert editor.text.splitlines()[:2] == ["second", "first"]
    assert editor.cursors.main.end.line == 1


def test_replace_all_rewrites_every_occurrence_as_one_undoable_step():
    """A hundred replacements must undo with one press, not a hundred."""
    editor = te.TextEditor("a b a b a\n")
    editor.set_find_text("a")
    assert editor.replace_all("Z") == 3
    assert editor.text == "Z b Z b Z\n"
    editor.undo()
    assert editor.text == "a b a b a\n"


def test_strip_trailing_whitespace_leaves_the_text_alone():
    """The operation people run before committing; it must not eat a word."""
    editor = te.TextEditor("keep   \n  indent kept\n")
    editor.strip_trailing_whitespace()
    assert editor.text == "keep\n  indent kept\n"


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------
def test_a_read_only_editor_still_selects_and_copies_but_does_not_change():
    """The reference made read-only selectable deliberately; so does this."""
    editor = te.TextEditor("locked\n", read_only=True)
    editor.select_all()
    assert editor.copy() == "locked\n"
    editor.key(0, "x")
    editor.key(KEY_BACKSPACE)
    assert editor.text == "locked\n"


def test_auto_indent_carries_the_indent_of_the_line_it_split():
    """And carries only the part *before* the caret."""
    editor = te.TextEditor("    body\n")
    editor.set_cursor(te.Pos(0, 8))
    editor.key(KEY_RETURN)
    assert editor.document.get_line_text(1) == "    "


def test_tab_indents_a_selection_and_types_spaces_without_one():
    """Two different jobs on one key, decided by whether anything is selected."""
    editor = te.TextEditor("a\nb\n")
    editor.key(KEY_TAB)
    assert editor.document.get_line_text(0) == "    a"

    editor.select_region(te.Pos(0, 0), te.Pos(1, 1))
    editor.key(KEY_TAB)
    assert editor.document.get_line_text(1) == "    b"


def test_home_goes_to_the_first_non_blank_then_to_column_zero():
    """A deliberate improvement on the reference, which goes straight to zero."""
    editor = te.TextEditor("    indented\n")
    editor.set_cursor(te.Pos(0, 8))
    editor.key(KEY_HOME)
    assert editor.cursors.main.end.index == 4
    editor.key(KEY_HOME)
    assert editor.cursors.main.end.index == 0


def test_shift_arrow_extends_the_selection_and_a_bare_arrow_collapses_it():
    """The behaviour every editor has and every hand-rolled one gets wrong."""
    editor = te.TextEditor("abcdef\n")
    editor.set_cursor(te.Pos(0, 2))
    editor.key(KEY_END, modifiers=SHIFT_MODIFIER)
    assert editor.selected_text() == "cdef"
    editor.key(KEY_LEFT)
    assert not editor.cursors.any_has_selection


def test_alt_up_moves_the_line_and_plain_up_moves_the_caret():
    """The same key, two jobs, told apart by the modifier mask."""
    editor = te.TextEditor("one\ntwo\n")
    editor.set_cursor(te.Pos(1, 0))
    editor.key(KEY_UP)
    assert editor.cursors.main.end.line == 0
    editor.set_cursor(te.Pos(1, 0))
    editor.key(KEY_UP, modifiers=ALT_MODIFIER)
    assert editor.text.splitlines()[:2] == ["two", "one"]


def test_ctrl_slash_toggles_comments_and_ctrl_a_selects_all():
    """The shortcuts arrive as text plus a modifier, as the host sends them."""
    editor = te.TextEditor("x = 1\n", te.Language.python())
    editor.key(0, "/", CONTROL_MODIFIER)
    assert editor.document.get_line_text(0).startswith("# ")
    editor.key(0, "a", CONTROL_MODIFIER)
    assert editor.selected_text().startswith("# x")


def test_typing_an_opening_bracket_completes_the_pair_and_stays_inside():
    """Closing-glyph completion, with the caret between the two."""
    editor = te.TextEditor("")
    editor.key(0, "(")
    assert editor.text == "()"
    assert editor.cursors.main.end.index == 1


def test_key_down_scrolls_the_view_to_follow_the_caret():
    """A caret off screen is a caret nobody can find."""
    editor = te.TextEditor("\n".join(str(one) for one in range(100)))
    _drawn(editor, h=100.0)
    for _ in range(30):
        editor.key(KEY_DOWN)
    assert editor.first_visible_line > 0
    assert (
        editor.first_visible_line
        <= editor.cursors.main.end.line
        < editor.first_visible_line + editor.visible_lines
    )


# --------------------------------------------------------------------------
# Drawing and mouse
# --------------------------------------------------------------------------
def test_drawing_emits_the_line_numbers_and_the_text_and_clips():
    """The gutter, the body, and a clip so a long line stops at the edge."""
    editor = te.TextEditor("alpha\nbeta\n", te.Language.python())
    painter = _drawn(editor)
    assert "1" in painter.strings and "2" in painter.strings
    assert "alpha" in painter.strings
    assert painter.clips == []  # pushed and popped, not left open


def test_a_press_lands_on_the_character_it_points_at():
    """Column arithmetic through the gutter, in the monospaced metric."""
    editor = te.TextEditor("abcdefgh\n")
    _drawn(editor)
    where = editor.press(
        editor._text_x + 3 * editor._glyph_w, 4.0, 0.0, 0.0, 400.0, 200.0
    )
    assert where == te.Pos(0, 3)


def test_a_double_click_selects_a_word_and_a_triple_click_the_line():
    """Click count is an argument, because the chrome has no clock."""
    editor = te.TextEditor("alpha beta\n")
    _drawn(editor)
    x = editor._text_x + 7 * editor._glyph_w
    editor.press(x, 4.0, 0.0, 0.0, 400.0, 200.0, clicks=2)
    assert editor.selected_text() == "beta"
    editor.press(x, 4.0, 0.0, 0.0, 400.0, 200.0, clicks=3)
    assert editor.selected_text() == "alpha beta"


def test_a_tab_is_drawn_at_its_stop_not_as_one_character():
    """A tab is a width, so a press after it must land past the whole stop."""
    editor = te.TextEditor("\tx\n")
    editor.config.tab_size = 4
    _drawn(editor)
    assert editor._column_of(te.Pos(0, 1)) == 4
    assert editor._index_at_column(0, 2) == 0
    assert editor._index_at_column(0, 4) == 1


def test_whitespace_marks_are_drawn_only_when_asked_for():
    """They are off by default; a document full of dots is nobody's default."""
    editor = te.TextEditor("a b\n")
    assert "·" not in _drawn(editor).strings
    editor.config.show_spaces = True
    assert "·" in _drawn(editor).strings


def test_a_marker_recolours_its_line_number_and_its_text():
    """What an error marker is for: finding the line without reading it."""
    editor = te.TextEditor("fine\nbroken\n")
    editor.add_marker(1, (220, 90, 80), (220, 140, 130), "syntax error")
    painter = _drawn(editor)
    assert (220, 90, 80) in [one[6] for one in painter.texts]


def test_the_picker_offers_every_language_the_class_can_build():
    """The list is derived, not written down.

    A hand-kept tuple beside the builders is a list that goes stale silently:
    rename a builder and the picker raises, or drop one and it disappears with
    no test noticing. So `shipped_languages` asks the class, and this pins that
    every public builder is reachable and every entry is keyed by its own name.
    """
    builders = {
        name
        for name in vars(te.Language)
        if not name.startswith("_") and isinstance(vars(te.Language)[name], staticmethod)
    }
    shipped = te.shipped_languages()
    assert len(shipped) == len(builders)
    for key, one in shipped.items():
        assert key == one.name
    assert shipped is not te.shipped_languages()  # fresh, never shared


def test_a_command_language_is_built_from_the_applications_own_words():
    """cmtk holds no verb list of its own -- the application supplies both.

    The toolkit knows the *shape* of a command script (verbs, `#` comments,
    strings, numbers); which verbs and which argument words exist belongs to
    whoever owns the command registry and the grammar.
    """
    lang = te.Language.commands(("fetch", "show"), ("all", "within"), name="viewer")
    assert lang.name == "viewer"
    assert lang.keywords == frozenset({"fetch", "show"})
    assert lang.identifiers == frozenset({"all", "within"})
    bare = te.Language.commands()
    assert bare.keywords == frozenset() and bare.identifiers == frozenset()
    assert bare.single_line_comment == "#"
