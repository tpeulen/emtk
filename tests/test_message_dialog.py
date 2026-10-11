"""emtk.message_dialog: message, confirm, choice and text questions, and their scripted answers."""
from __future__ import annotations

import pytest

import emtk
from emtk.keys import KEY_ESCAPE, KEY_RETURN
from emtk.message_dialog import MessageDialogs, auto_answer
from emtk.testing import RecordingPainter

FRAME = (0.0, 0.0, 800.0, 600.0)


class Host:
    """Draws the dialogs every frame and clicks the rectangles they report."""

    def __init__(self, dialogs: MessageDialogs):
        self.dialogs = dialogs
        self.io, self.storage = emtk.IO(), {}
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, FRAME, io=self.io, storage=self.storage):
            self.dialogs.draw(FRAME)
        self.io.mouse_clicked[0] = False
        self.io.mouse_released[0] = False
        self.io.key = 0
        self.io.text = ""

    def click(self, rect):
        x, y, w, h = rect
        point = (x + w / 2, y + h / 2)
        self.io.mouse_pos = point
        self.frame()
        self.io.mouse_clicked_pos[0] = point
        self.io.mouse_down[0] = self.io.mouse_clicked[0] = True
        self.frame()
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        self.frame()

    def key(self, code, text=""):
        self.io.key, self.io.text = code, text
        self.frame()


def test_confirm_draws_title_message_and_buttons_and_answers_yes():
    answers = []
    dialogs = MessageDialogs()
    dialogs.confirm("Remove fit", "Remove the fit and its window?", answers.append)
    host = Host(dialogs)
    host.frame()
    for text in ("Remove fit", "Remove the fit and its window?", "Yes", "No"):
        assert text in host.painter.strings, text
    assert dialogs.modal
    host.click(dialogs.current.rects["button.yes"])
    assert answers == [True]
    assert not dialogs.modal
    host.frame()
    assert "Remove fit" not in host.painter.strings, "an answered question is not drawn again"


def test_the_window_close_and_enter_give_the_safe_answers():
    answers = []
    dialogs = MessageDialogs()
    host = Host(dialogs)
    dialogs.confirm("Quit", "Are you sure to quit?", answers.append)
    host.frame()
    x, y, w, _h = dialogs.current.rects["window"]
    host.io.mouse_pos = (x + 20, y + 40)
    host.key(KEY_ESCAPE)
    assert answers == [False], "Escape (the window's close) declines"
    dialogs.confirm("Quit", "Are you sure to quit?", answers.append, default=False)
    host.frame()
    host.key(KEY_RETURN)
    assert answers == [False, False], "Enter takes the default, which is No"


def test_choice_answers_the_key_and_close_answers_none():
    answers = []
    dialogs = MessageDialogs()
    options = {"save": "Save", "discard": "Don't Save", "cancel": "Cancel"}
    dialogs.choice("Unsaved Project", "Save changes?", options, answers.append, default="cancel")
    host = Host(dialogs)
    host.frame()
    for label in options.values():
        assert label in host.painter.strings
    host.click(dialogs.current.rects["button.discard"])
    assert answers == ["discard"]
    dialogs.choice("Unsaved Project", "Save changes?", options, answers.append)
    host.frame()
    x, y, w, _h = dialogs.current.rects["window"]
    host.click((x + w - 14, y + 4, 4, 4))  # the header's ×
    assert answers == ["discard", None]
    with pytest.raises(ValueError):
        dialogs.choice("x", "y", options, default="nope")


def test_text_question_is_typed_into_and_cancel_answers_none():
    answers = []
    dialogs = MessageDialogs()
    dialogs.text("Project name", "Name the project:", answers.append, value="")
    host = Host(dialogs)
    host.frame()
    host.click(dialogs.current.rects["field"])
    for char in "abc":
        host.key(0, char)
    assert dialogs.current.value == "abc"
    host.click(dialogs.current.rects["button.ok"])
    assert answers == ["abc"]
    dialogs.text("Project name", "Name the project:", answers.append, value="x")
    host.frame()
    host.click(dialogs.current.rects["button.cancel"])
    assert answers == ["abc", None]


def test_questions_queue_and_are_drawn_oldest_first():
    answers = []
    dialogs = MessageDialogs()
    dialogs.message("First", "one", on_answer=answers.append)
    dialogs.message("Second", "two", on_answer=answers.append)
    host = Host(dialogs)
    host.frame()
    assert "First" in host.painter.strings and "Second" not in host.painter.strings
    host.click(dialogs.current.rects["button.ok"])
    host.frame()
    assert "Second" in host.painter.strings
    assert answers == [None]


def test_auto_answer_answers_without_drawing_and_defaults_are_safe(caplog):
    answers = []
    dialogs = MessageDialogs()
    with auto_answer(confirm=True, choice="save", text="named"):
        assert dialogs.confirm("Remove", "Sure?", answers.append) is None
        dialogs.choice("Unsaved", "Save?", {"save": "Save", "cancel": "Cancel"}, answers.append)
        dialogs.text("Name", "Name?", answers.append)
    assert answers == [True, "save", "named"]
    assert not dialogs.modal, "a scripted question is never drawn"
    answers.clear()
    with caplog.at_level("INFO", logger="emtk.message_dialog"), auto_answer(defaults=True):
        dialogs.confirm("Remove", "Remove everything?", answers.append)
        dialogs.choice("Overwrite", "Exists.", {"overwrite": "Overwrite", "skip": "Skip"},
                       answers.append)
        dialogs.text("Name", "Name?", answers.append, value="typed")
        dialogs.message("Done", "Saved.", on_answer=answers.append)
    assert answers == [False, None, None, None], "unattended, nothing destructive is confirmed"
    assert "Remove everything?" in caplog.text, "an unattended question is still logged"
    with pytest.raises(ValueError):
        with auto_answer(question=True):
            pass


def test_answer_by_key_matches_the_buttons():
    answers = []
    dialogs = MessageDialogs()
    dialogs.confirm("A", "a", answers.append)
    dialogs.text("B", "b", answers.append, value="v")
    dialogs.answer(key="yes")
    dialogs.answer(key="ok")
    assert answers == [True, "v"]
