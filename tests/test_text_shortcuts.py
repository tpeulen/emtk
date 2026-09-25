"""Text-editing shortcuts and the clipboard, in every emtk text entry.

The convention (see :mod:`emtk.keys`): after a host has translated its
event, ``CONTROL_MODIFIER`` / ``io.key_ctrl`` is the *primary* modifier --
Command on a Mac, Ctrl elsewhere -- and ``META_MODIFIER`` / ``io.key_super``
is the other one (the physical Control key on a Mac, Win/Super elsewhere).
That is Qt's convention on macOS and Dear ImGui's (``ConfigMacOSXBehaviors``
swaps Cmd and Ctrl), so a shortcut test is one test on every host.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import clipboard, keys
from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from emtk.keys import (
    KEY_BACKSPACE, KEY_END, KEY_HOME, KEY_LEFT, KEY_RIGHT,
)
from emtk.testing import RecordingPainter
from emtk.widgets.text_field import TextField

CMD = CONTROL_MODIFIER            # the primary modifier, normalised
SHIFT = SHIFT_MODIFIER
ALT = ALT_MODIFIER
MACCTRL = META_MODIFIER           # the physical Control key on a Mac


@pytest.fixture(params=[True, False], ids=["mac", "pc"])
def mac(request):
    keys.set_mac_behaviors(request.param)
    yield request.param
    keys.set_mac_behaviors(None)


@pytest.fixture
def board():
    """A fake system clipboard, through the host hook."""
    held = {"text": ""}
    clipboard.set_hook(lambda t: held.__setitem__("text", t), lambda: held["text"])
    yield held
    clipboard.set_hook(None)


def chord(field, letter, mods=CMD):
    """A shortcut as a host delivers it: the letter's key code and its text."""
    return field.key(ord(letter), letter, mods)


# -- the host translation ------------------------------------------------ #
def test_the_browser_on_a_mac_reports_command_as_the_primary_modifier():
    assert keys.modifiers_from_dom(False, False, False, True, mac=True) == CONTROL_MODIFIER
    assert keys.modifiers_from_dom(True, False, False, False, mac=True) == META_MODIFIER
    assert keys.modifiers_from_dom(True, False, False, False, mac=False) == CONTROL_MODIFIER


def test_glfw_on_a_mac_reports_command_as_the_primary_modifier():
    from emtk.events import modifiers_from_canvas

    assert modifiers_from_canvas(("Meta",), mac=True) == CONTROL_MODIFIER
    assert modifiers_from_canvas(("Control",), mac=True) == META_MODIFIER
    assert modifiers_from_canvas(("Control",), mac=False) == CONTROL_MODIFIER


# -- the one-line editor ------------------------------------------------- #
def test_select_all_then_typing_replaces(mac):
    f = TextField()
    f.set_text("hello")
    chord(f, "a")
    assert f.selected_text() == "hello"
    f.key(0, "x")
    assert (f.text, f.cursor) == ("x", 1)


def test_a_shortcut_types_nothing(mac):
    f = TextField()
    f.set_text("abc")
    for letter in "acvzy":
        chord(f, letter)
    assert f.text == "abc"


def test_copy_cut_paste_round_trip(mac, board):
    f = TextField()
    f.set_text("one two")
    chord(f, "a")
    chord(f, "c")
    assert board["text"] == "one two"
    f.key(KEY_END, "", 0)
    chord(f, "v")
    assert f.text == "one twoone two"
    chord(f, "a")
    chord(f, "x")
    assert (f.text, board["text"]) == ("", "one twoone two")


def test_undo_and_redo(mac):
    f = TextField()
    for ch in "abc":
        f.key(0, ch)
    f.key(KEY_BACKSPACE)
    assert f.text == "ab"
    chord(f, "z")
    assert f.text == "abc"
    if mac:
        chord(f, "z", CMD | SHIFT)
    else:
        chord(f, "y")
    assert f.text == "ab"
    chord(f, "z")
    chord(f, "z", CMD | SHIFT)          # both spellings redo off a Mac
    assert f.text == "ab"


def test_word_navigation(mac):
    f = TextField()
    f.set_text("alpha beta gamma")
    word = ALT if mac else CMD
    f.key(KEY_LEFT, "", word)
    assert f.cursor == len("alpha beta ")
    f.key(KEY_LEFT, "", word | SHIFT)
    assert f.selected_text() == "beta "
    f.key(KEY_RIGHT, "", word)
    assert f.cursor in (len("alpha beta"), len("alpha beta "))   # end of word, or next


def test_line_start_and_end(mac):
    f = TextField()
    f.set_text("abc")
    if mac:
        f.key(KEY_LEFT, "", CMD)
        assert f.cursor == 0
        f.key(KEY_RIGHT, "", CMD | SHIFT)
        assert f.selected_text() == "abc"
        # Emacs, as Cocoa fields do: Control-A / Control-E.
        chord(f, "a", MACCTRL)
        assert f.cursor == 0 and not f.has_selection()
        chord(f, "e", MACCTRL)
        assert f.cursor == 3
    f.key(KEY_HOME)
    assert f.cursor == 0
    f.key(KEY_END, "", SHIFT)
    assert f.selected_text() == "abc"


def test_shift_arrows_extend_and_backspace_deletes_the_selection(mac):
    f = TextField()
    f.set_text("abcd")
    f.key(KEY_LEFT, "", SHIFT)
    f.key(KEY_LEFT, "", SHIFT)
    assert f.selected_text() == "cd"
    f.key(KEY_BACKSPACE)
    assert (f.text, f.cursor) == ("ab", 2)


# -- im.input_text -------------------------------------------------------- #
class _Driver:
    """An :class:`emtk.app.ImApp` driven the way a host drives it."""

    def __init__(self, value="hello world"):
        from emtk.app import ImApp

        self.value = value
        self.box = None
        self.app = ImApp(self.gui)
        self.app.io.wall_clock = False

    def gui(self):
        from emtk.im_core import get_current_context

        emtk.begin("w", (0, 0, 400, 80))
        _changed, self.value = emtk.input_text("##f", self.value)
        self.box = get_current_context().get_item_rect()
        emtk.end()

    def frame(self):
        self.app.draw(RecordingPainter(), 0, 0, 400, 80)

    def click(self, dx=4.0, clicks=1):
        from emtk.events import LEFT_BUTTON

        x, y, _w, _h = self.box
        self.app.pointer_press(x + dx, y + 4, LEFT_BUTTON, 0, clicks)
        self.frame()
        self.app.pointer_release(x + dx, y + 4, LEFT_BUTTON, 0)
        self.frame()

    def key(self, key, text="", mods=0):
        self.app.key(key, text, mods)
        self.frame()


def test_input_text_select_all_and_type(mac):
    d = _Driver()
    d.frame()
    d.click()
    d.key(ord("a"), "a", CMD)
    d.key(0, "Z")
    assert d.value == "Z"


def test_input_text_copy_paste(mac, board):
    d = _Driver("abc")
    d.frame()
    d.click()
    d.key(ord("a"), "a", CMD)
    d.key(ord("c"), "c", CMD)
    assert board["text"] == "abc"
    d.key(KEY_END)
    d.key(ord("v"), "v", CMD)
    assert d.value == "abcabc"


def test_input_text_caret_moves_and_inserts_in_the_middle(mac):
    d = _Driver("ac")
    d.frame()
    d.click()
    d.key(KEY_END)
    d.key(KEY_LEFT)
    d.key(0, "b")
    assert d.value == "abc"


# -- the clipboard -------------------------------------------------------- #
def test_clipboard_round_trips_through_the_hook(board):
    assert clipboard.copy("x y")
    assert clipboard.paste() == "x y"


def test_input_text_double_click_selects_a_word_and_triple_click_all(mac):
    d = _Driver("alpha beta")
    d.frame()
    x = 4.0 + 7.0 * 7                 # inside "beta" (RecordingPainter: 7 px a glyph)
    d.click(x)
    d.click(x)
    d.key(0, "B")
    assert d.value == "alpha B"
    d.click(x)
    d.click(x)
    d.click(x)
    d.key(0, "z")
    assert d.value == "z"


def test_input_text_triple_click_waits_on_the_clock(mac):
    d = _Driver("alpha beta")
    d.frame()
    d.click(200.0)
    d.app.io.now += 5.0               # the fake clock: too slow for a double click
    d.click(200.0)
    d.key(0, "!")
    assert d.value == "alpha beta!"


def test_input_text_drag_selects(mac):
    from emtk.events import LEFT_BUTTON

    d = _Driver("abcdef")
    d.frame()
    x, y, _w, _h = d.box
    pad = 4.0
    d.app.pointer_press(x + pad + 1, y + 4, LEFT_BUTTON, 0, 1)
    d.frame()
    d.app.pointer_move(x + pad + 7 * 3, y + 4, LEFT_BUTTON, 0)
    d.frame()
    d.app.pointer_release(x + pad + 7 * 3, y + 4, LEFT_BUTTON, 0)
    d.frame()
    d.key(KEY_BACKSPACE)
    assert d.value == "def"


# -- the combo list's filter ---------------------------------------------- #
def _combo():
    from test_overlays import TAUS, Form, Model, _spec

    form = Form(Model(TAUS), _spec())
    return form, form.open()


def _send(form, key, text="", mods=0):
    form.io.key_events = [(key, text, mods)]
    form.io.key, form.io.text = key, keys.typed_text(text, mods)
    return form.frame()


def test_combo_filter_select_all_copy_paste_undo(mac, board):
    form, panel = _combo()
    for ch in "tau":
        _send(form, ord(ch.upper()), ch)
    assert panel.query == "tau"
    _send(form, ord("A"), "a", CMD)
    assert panel.filter_field.selected_text() == "tau"
    _send(form, ord("C"), "c", CMD)
    assert board["text"] == "tau"
    _send(form, 0, "g")
    assert panel.query == "g" and panel.open
    _send(form, ord("Z"), "z", CMD)
    assert panel.query == "tau"
    _send(form, KEY_END)                    # the list's End, not the field's
    _send(form, ord("A"), "a", CMD)
    _send(form, ord("V"), "v", CMD)
    assert panel.query == "tau"
    _send(form, KEY_LEFT)
    _send(form, 0, "X")
    assert panel.query == "taXu"


def test_combo_filter_word_delete_and_shift_select(mac):
    form, panel = _combo()
    for ch in "tau green":
        _send(form, 0, ch)
    _send(form, KEY_BACKSPACE, "", ALT if mac else CMD)
    assert panel.query == "tau "
    _send(form, KEY_LEFT, "", SHIFT)
    _send(form, KEY_LEFT, "", SHIFT)
    _send(form, KEY_BACKSPACE)
    assert panel.query == "ta"


# -- a DataTable cell editor ---------------------------------------------- #
def _table():
    from emtk.widgets.data_table import DataTable, TableColumn

    edits = []
    table = DataTable([TableColumn("name", editable=True)],
                      on_edit=lambda i, k, v: edits.append((i, k, v)))
    table.set_records([{"name": "donor"}, {"name": "acceptor"}])
    return table, edits


def test_data_table_cell_editor_shortcuts(mac, board):
    from emtk.keys import KEY_RETURN

    table, edits = _table()
    table.begin_edit(0, "name")
    assert table.key(ord("A"), "a", CMD)
    table.key(ord("X"), "x", CMD)
    assert board["text"] == "donor" and table.editor.text == ""
    table.key(ord("V"), "v", CMD)
    table.key(ord("V"), "v", CMD)
    assert table.editor.text == "donordonor"
    table.key(KEY_LEFT, "", CMD if mac else 0)  # Cmd+Left on a Mac: the line's start
    if not mac:
        table.key(KEY_HOME)
    table.key(0, "#")
    table.key(ord("Z"), "z", CMD)
    assert table.editor.text == "donordonor"
    table.key(ord("Z"), "z", CMD | SHIFT)
    table.key(KEY_RETURN)
    assert edits == [(0, "name", "#donordonor")]


def test_data_table_cell_editor_mouse(mac):
    table, _edits = _table()
    painter = RecordingPainter()
    table.draw(painter, 0, 0, 300, 200)
    table.begin_edit(1, "name")
    table.draw(painter, 0, 0, 300, 200)
    x, y, w, h = table._editor_box
    table.press(x + 10, y + 2, 0, 0, 300, 200, 0, 2)       # a double click: the word
    table.key(0, "Q")
    assert table.editor.text == "Q"
