"""``emtk.message_dialog`` -- message, confirm, choice and text questions over an app.

Every app that tells the user something or asks a yes/no question was drawing
its own little window for it. This is the shared one: a queue of questions,
each drawn as a :class:`~emtk.dialog_window.DialogWindow` over the app, the
oldest first. A question never blocks -- immediate mode has no ``exec`` -- so
the answer arrives in a callback.

.. code-block:: python

    dialogs = MessageDialogs(wake=app.request_frame)
    dialogs.confirm("Remove fit", "Remove the fit and its window?",
                    on_answer=lambda yes: yes and remove())
    # every frame, last, over the whole app
    dialogs.draw(app_box)

Four kinds, each answered with one value:

* :meth:`MessageDialogs.message` -- *OK*; answers ``None``;
* :meth:`MessageDialogs.confirm` -- *Yes* / *No*; answers ``True`` / ``False``
  (``False`` when the window is closed);
* :meth:`MessageDialogs.choice` -- one button per option; answers the option's
  key, ``None`` when the window is closed;
* :meth:`MessageDialogs.text` -- a field with *OK* / *Cancel*; answers the text,
  ``None`` on *Cancel*.

Scripted answers
----------------
:func:`auto_answer` answers questions from a script instead of from a person:
``auto_answer(confirm=True)`` makes every confirm answer *Yes* at once, without
drawing anything, for as long as the block runs. ``auto_answer(defaults=True)``
answers every question with its **default** -- what an unattended run must do,
which is why the default of a destructive question is the safe answer (*No*,
no choice, no text). Every question is logged either way, so a run with nobody
at the screen still says what it was asked.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from . import im_core as _core
from . import im_widgets as _w
from .dialog_window import DialogWindow
from .i18n import mark, tr
from .keys import KEY_ENTER, KEY_RETURN

__all__ = ["KINDS", "MessageDialogs", "Question", "auto_answer"]

_log = logging.getLogger("emtk.message_dialog")

#: The question kinds :func:`auto_answer` takes keywords for.
KINDS = ("message", "confirm", "choice", "text")

#: Scripted answers installed by :func:`auto_answer` (kind -> value; ``"defaults"`` -> bool).
_AUTO: dict[str, Any] = {}

Rect = tuple[float, float, float, float]


@contextlib.contextmanager
def auto_answer(**answers):
    """Answer questions from a script instead of from a person.

    Parameters
    ----------
    **answers
        ``kind=value`` for a kind of :data:`KINDS` (``confirm=True``,
        ``choice="discard"``, ``text="name"``, ``message=None``), and
        ``defaults=True`` to answer every kind not named with its default.

    Yields
    ------
    dict
        The active answer map (mutable, for nested adjustments).

    Raises
    ------
    ValueError
        For a keyword that names no kind.
    """
    unknown = set(answers) - set(KINDS) - {"defaults"}
    if unknown:
        raise ValueError(f"auto_answer takes {KINDS} and 'defaults', not {sorted(unknown)}")
    previous = dict(_AUTO)
    _AUTO.update(answers)
    try:
        yield _AUTO
    finally:
        _AUTO.clear()
        _AUTO.update(previous)


def _scripted(kind: str, default: Any) -> tuple[bool, Any]:
    """``(True, answer)`` when a script answers *kind*, else ``(False, None)``."""
    if kind in _AUTO:
        return True, _AUTO[kind]
    if _AUTO.get("defaults"):
        return True, default
    return False, None


@dataclass
class Question:
    """One open question: what it asks, the answers it offers and who hears the answer.

    Attributes
    ----------
    kind : str
        One of :data:`KINDS`.
    title, message : str
        The window title and the text (already translated by the caller).
    options : list of (str, str)
        ``(key, label)`` of the buttons, in order; the answer is the key.
    default : object
        The answer of Enter and of :func:`auto_answer` ``defaults``; the window's
        × answers :attr:`dismissed`.
    dismissed : object
        The answer when the window is closed (× or Escape).
    value : str
        The text field's content (``text`` questions).
    detail : str
        Second-tier text under the message.
    on_answer : callable or None
        ``on_answer(answer)``, called once.
    rects : dict
        Screen rectangles of the last frame: ``"button.<key>"``, ``"field"``,
        ``"window"`` -- for a test or a tour.
    """

    kind: str
    title: str
    message: str
    options: list[tuple[str, str]]
    default: Any = None
    dismissed: Any = None
    value: str = ""
    detail: str = ""
    on_answer: Callable[[Any], None] | None = None
    rects: dict[str, Rect] = field(default_factory=dict)
    window: DialogWindow | None = None
    _focused: bool = False


class MessageDialogs:
    """A queue of questions drawn over an app, oldest first.

    Parameters
    ----------
    wake : callable, optional
        The host's frame request, run when a question is asked from outside a
        frame (a worker's result), so it is drawn without waiting for input.
    width : float
        The windows' width.

    Attributes
    ----------
    pending : list of Question
        Questions asked and not yet answered; ``pending[0]`` is drawn.
    """

    def __init__(self, wake: Callable[[], None] | None = None, width: float = 440.0) -> None:
        self.wake = wake
        self.width = float(width)
        self.pending: list[Question] = []

    # -- asking ------------------------------------------------------------ #
    def _ask(self, question: Question) -> Question | None:
        _log.info("%s: %s%s", question.title, question.message,
                  f"\n{question.detail}" if question.detail else "")
        scripted, answer = _scripted(question.kind, question.default)
        if scripted:
            _log.info("%s: answered by script with %r", question.title, answer)
            if question.on_answer is not None:
                question.on_answer(answer)
            return None
        question.window = DialogWindow(question.title, size=(self.width, 160.0),
                                       key=f"message-{id(question)}", fit_height=True)
        question.window.show()
        self.pending.append(question)
        if self.wake is not None:
            self.wake()
        return question

    def message(self, title: str, message: str, *, detail: str = "",
                on_answer: Callable[[Any], None] | None = None) -> Question | None:
        """Tell the user something; *OK* answers ``None``.

        Returns
        -------
        Question or None
            The open question, ``None`` when a script answered it.
        """
        return self._ask(Question("message", str(title), str(message),
                                  [("ok", mark("OK", domain="emtk"))], detail=str(detail),
                                  on_answer=on_answer))

    def confirm(self, title: str, message: str, on_answer: Callable[[bool], None] | None = None,
                *, default: bool = False, detail: str = "",
                yes: str = mark("Yes", domain="emtk"),
                no: str = mark("No", domain="emtk")) -> Question | None:
        """Ask a yes/no question; the answer is ``True`` for *Yes*.

        *default* is Enter's answer and the scripted ``defaults`` answer: keep it
        ``False`` for anything destructive.
        """
        return self._ask(Question("confirm", str(title), str(message),
                                  [("yes", yes), ("no", no)], default=bool(default),
                                  dismissed=False, detail=str(detail), on_answer=on_answer))

    def choice(self, title: str, message: str,
               options: Mapping[str, str] | Iterable[tuple[str, str]],
               on_answer: Callable[[str | None], None] | None = None, *,
               default: str | None = None, detail: str = "") -> Question | None:
        """Offer one button per option; the answer is the pressed option's key.

        Parameters
        ----------
        options : mapping or sequence of (key, label)
            The buttons, in order; labels are translated when drawn.
        default : str, optional
            Enter's answer and the scripted ``defaults`` answer; ``None`` (no
            choice) is the safe default for an overwrite or a deletion.
        """
        pairs = list(options.items()) if isinstance(options, Mapping) else list(options)
        pairs = [(str(key), str(label)) for key, label in pairs]
        if default is not None and default not in {key for key, _label in pairs}:
            raise ValueError(f"default {default!r} is not among the options")
        return self._ask(Question("choice", str(title), str(message), pairs, default=default,
                                  dismissed=None, detail=str(detail), on_answer=on_answer))

    def text(self, title: str, message: str, on_answer: Callable[[str | None], None] | None = None,
             *, value: str = "", default: str | None = None, detail: str = "") -> Question | None:
        """Ask for a line of text; *OK* answers it, *Cancel* answers ``None``.

        *value* fills the field; *default* is the scripted ``defaults`` answer
        (``None``: an unattended run cancels).
        """
        return self._ask(Question("text", str(title), str(message),
                                  [("ok", mark("OK", domain="emtk")),
                                   ("cancel", mark("Cancel", domain="emtk"))],
                                  default=default, dismissed=None, value=str(value),
                                  detail=str(detail), on_answer=on_answer))

    # -- state ------------------------------------------------------------- #
    @property
    def modal(self) -> bool:
        """Whether a question is open (it takes the input until answered)."""
        return bool(self.pending)

    @property
    def current(self) -> Question | None:
        """The question drawn now."""
        return self.pending[0] if self.pending else None

    def contains(self, x: float, y: float) -> bool:
        """Whether (x, y) is on the open question's window."""
        question = self.current
        return bool(question and question.window and question.window.contains(x, y))

    def answer(self, value: Any = None, *, key: str | None = None) -> None:
        """Answer the open question, as its buttons do.

        Parameters
        ----------
        value : object
            The answer itself.
        key : str, optional
            A button key instead: ``"yes"``/``"no"`` for a confirm, an option
            key for a choice, ``"ok"``/``"cancel"`` for a text question.
        """
        question = self.current
        if question is None:
            return
        if key is not None:
            value = self._answer_of(question, key)
        self.pending.pop(0)
        if question.window is not None:
            question.window.hide()
        _log.info("%s: answered %r", question.title, value)
        if question.on_answer is not None:
            question.on_answer(value)
        if self.wake is not None:
            self.wake()

    @staticmethod
    def _answer_of(question: Question, key: str) -> Any:
        if question.kind == "confirm":
            return key == "yes"
        if question.kind == "text":
            return question.value if key == "ok" else None
        if question.kind == "message":
            return None
        return key

    # -- drawing ----------------------------------------------------------- #
    def draw(self, frame: Rect) -> None:
        """Draw the oldest open question over *frame*; call last in the frame."""
        question = self.current
        if question is None or question.window is None:
            return
        window = question.window
        pressed = window.begin(frame)
        io = _core.get_io()
        enter = io.key in (KEY_RETURN, KEY_ENTER)
        _w.text_wrapped(question.message)
        if question.detail:
            _w.text_disabled(question.detail)
        if question.kind == "text":
            if not question._focused:
                _w.set_keyboard_focus_here()
                question._focused = True
            _w.set_next_item_width(-1.0)
            changed, value = _w.input_text(f"##{window.key}.field", question.value)
            if changed:
                question.value = value
            question.rects["field"] = _w.get_item_rect()
        _w.spacing()
        chosen = None
        for index, (key, label) in enumerate(question.options):
            if index:
                _w.same_line()
            if _w.button(f"{tr(label)}##{window.key}.{key}"):
                chosen = key
            question.rects[f"button.{key}"] = _w.get_item_rect()
        window.end()
        if window.box is not None:
            question.rects["window"] = window.box
        if chosen is not None:
            self.answer(key=chosen)
        elif pressed == "close":
            self.answer(question.dismissed)
        elif enter:
            if question.kind == "text":
                self.answer(key="ok")
            elif question.kind == "message":
                self.answer(None)
            elif question.kind == "confirm" or question.default is not None:
                self.answer(question.default)
