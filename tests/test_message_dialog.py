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
        # Draw until the open question's window has settled: a fit_height window learns its
        # height in its first frame and is centred on it in the next, as a running app shows
        # it before anyone can click.
        for _ in range(4):
            before = dict(self.dialogs.current.rects) if self.dialogs.current else None
            self._draw()
            after = self.dialogs.current.rects if self.dialogs.current else None
            if before is None or after is None or before.get("window") == after.get("window"):
                break
        self.io.mouse_clicked[0] = False
        self.io.mouse_released[0] = False
        self.io.key = 0
        self.io.text = ""

    def _draw(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, FRAME, io=self.io, storage=self.storage):
            self.dialogs.draw(FRAME)

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


def test_escape_dismisses_a_question_wherever_the_pointer_is():
    """A question is modal: Esc rejects it as Esc rejects a Qt message box, pointer or not."""
    answers = []
    dialogs = MessageDialogs()
    host = Host(dialogs)
    options = {"save": "Save", "discard": "Don't Save", "cancel": "Cancel"}
    dialogs.choice("Unsaved Project", "Save changes?", options, answers.append, default="cancel")
    host.frame()
    host.io.mouse_pos = (2.0, 2.0)  # far outside the window, e.g. on the menu bar
    assert not dialogs.current.window.contains(*host.io.mouse_pos)
    host.key(KEY_ESCAPE)
    assert answers == [None], "Escape dismissed the choice (the safe answer: nothing chosen)"
    assert not dialogs.modal
    dialogs.confirm("Quit", "Are you sure to quit?", answers.append)
    host.frame()
    host.key(KEY_ESCAPE)
    assert answers == [None, False], "Escape declines a confirm"


def _colours_inside(painter, rect):
    """Fill colours the painter drew inside *rect*, as 0..255 RGB."""
    x, y, w, h = rect
    out = []
    for fx, fy, fw, fh, *rest in [*painter.fills, *[(s[0], s[1], s[2], s[3], s[5]) for s in
                                                    painter.strokes]]:
        colour = rest[0]
        if colour is None or not (x - 1 <= fx and fy >= y - 1 and fx + fw <= x + w + 1
                                  and fy + fh <= y + h + 1):
            continue
        rgb = tuple(colour)[:3]
        if max(rgb) <= 1.0:
            rgb = tuple(round(c * 255) for c in rgb)
        out.append(tuple(int(round(c)) for c in rgb))
    return out


def test_a_confirm_shows_yes_green_and_no_red():
    from emtk.message_dialog import CONFIRM_COLOURS

    dialogs = MessageDialogs()
    dialogs.confirm("Update Available", "A new version is available.", lambda yes: None)
    host = Host(dialogs)
    host.frame()
    rects = dialogs.current.rects
    assert CONFIRM_COLOURS["yes"][0][:3] in _colours_inside(host.painter, rects["button.yes"])
    assert CONFIRM_COLOURS["no"][0][:3] in _colours_inside(host.painter, rects["button.no"])
    # a message's OK goes ahead: green too
    dialogs.answer(True)
    dialogs.message("Note", "Saved.")
    host.frame()
    assert CONFIRM_COLOURS["yes"][0][:3] in _colours_inside(host.painter,
                                                            dialogs.current.rects["button.ok"])


def test_a_long_question_is_centred_on_its_real_height():
    """The window's first height is a guess; a long message makes it grow, and it is centred
    again on the height it really has (it used to grow downward from a top placed for the
    guess, and sat low)."""
    dialogs = MessageDialogs()
    text = "\n".join(f"- change number {i}" for i in range(25))
    dialogs.confirm("Update Available", text, lambda yes: None)
    host = Host(dialogs)
    for _ in range(4):
        host.frame()
    x, y, w, h = dialogs.current.rects["window"]
    assert h > 300                                   # it grew to its content
    fx, fy, fw, fh = FRAME
    assert abs((y + h / 2) - (fy + fh / 2)) < 2.0
    assert abs((x + w / 2) - (fx + fw / 2)) < 2.0


def test_every_question_colours_its_buttons_by_role():
    """Save / Don't Save / Cancel as Yes / No / Cancel: green, red, yellow -- and a caller's own
    keys by the roles it names."""
    from emtk.message_dialog import ROLE_COLOURS

    green, red, yellow = (ROLE_COLOURS[r][0][:3] for r in ("yes", "no", "cancel"))
    dialogs = MessageDialogs()
    dialogs.choice("Unsaved Project", "Save changes?",
                   [("save", "Save"), ("discard", "Don't Save"), ("cancel", "Cancel")],
                   default="cancel")
    host = Host(dialogs)
    host.frame()
    rects = dialogs.current.rects
    assert green in _colours_inside(host.painter, rects["button.save"])
    assert red in _colours_inside(host.painter, rects["button.discard"])
    assert yellow in _colours_inside(host.painter, rects["button.cancel"])
    dialogs.answer(key="cancel")
    dialogs.choice("Folders exist", "Overwrite?",
                   [("overwrite", "Overwrite"), ("keep", "Keep both")], roles={"keep": "no"})
    host.frame()
    rects = dialogs.current.rects
    assert green in _colours_inside(host.painter, rects["button.overwrite"])
    assert red in _colours_inside(host.painter, rects["button.keep"])
    dialogs.answer(key="keep")
    dialogs.text("Name", "A name:")
    host.frame()
    rects = dialogs.current.rects
    assert green in _colours_inside(host.painter, rects["button.ok"])
    assert yellow in _colours_inside(host.painter, rects["button.cancel"])
