"""Find and replace with a regular expression in the text editor (``set_find_text(..., regex=True)``)."""

from __future__ import annotations

from emtk.widgets.text_editor import Pos, TextEditor


def _editor(text: str) -> TextEditor:
    editor = TextEditor(text=text)
    editor.set_cursor(Pos(0, 0))
    return editor


def test_a_literal_search_escapes_what_a_regex_search_interprets():
    editor = _editor("a.c abc a.c")
    editor.set_find_text("a.c")
    assert editor.find_all() == 2
    editor.set_find_text("a.c", regex=True)
    assert editor.find_all() == 3


def test_find_next_selects_the_regex_match_and_wraps():
    editor = _editor("x = 12\ny = 345\n")
    editor.set_find_text(r"\d+", regex=True)
    assert editor.find_next()
    assert editor.selected_text() == "12"
    assert editor.find_next()
    assert editor.selected_text() == "345"
    assert editor.find_next()  # wraps to the first
    assert editor.selected_text() == "12"


def test_find_previous_with_a_regex():
    editor = _editor("aa1 bb2 cc3")
    editor.set_find_text(r"[a-z]+\d", regex=True)
    assert editor.find_previous()
    assert editor.selected_text() == "cc3"


def test_case_and_whole_word_apply_to_a_regex():
    editor = _editor("Foo foo food")
    editor.set_find_text("fo+", case_sensitive=False, regex=True)
    assert editor.find_all() == 3
    editor.set_find_text("fo+", case_sensitive=True, whole_word=True, regex=True)
    assert editor.find_all() == 1  # "foo" only: "food" is not a whole-word match
    editor.set_find_text("fo+d?", case_sensitive=True, whole_word=True, regex=True)
    assert editor.find_all() == 2


def test_an_invalid_expression_finds_nothing_and_does_not_raise():
    editor = _editor("(a)")
    editor.set_find_text("(", regex=True)
    assert not editor.find_next()
    assert editor.find_all() == 0
    assert editor.replace_all("x") == 0


def test_an_expression_that_matches_only_the_empty_string_finds_nothing():
    editor = _editor("bbb")
    editor.set_find_text("a*", regex=True)
    assert not editor.find_next()
    assert editor.find_all() == 0


def test_empty_matches_are_skipped_but_real_ones_found():
    editor = _editor("bba")
    editor.set_find_text("a*", regex=True)
    assert editor.find_next()
    assert editor.selected_text() == "a"


def test_replace_all_with_a_regex_inserts_the_replacement_literally():
    editor = _editor("v1 v22 v333")
    editor.set_find_text(r"\d+", regex=True)
    assert editor.replace_all(r"\1") == 3
    assert editor.text == r"v\1 v\1 v\1"
