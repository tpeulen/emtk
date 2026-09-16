"""The command line that lives *inside* the viewport.

Why there are two command lines
-------------------------------
emtk's typed interface used to exist in exactly one place: a console docked
under the 3-D view, made of widgets. That is fine on a desktop and it is nothing
at all in a browser, where there are no widgets -- so the browser could render a
molecule and had no way to say anything to it. PyMOL solved the same problem the
same way thirty years ago and kept both halves: an *internal* prompt drawn by
the viewer itself, and an *external* one in the surrounding GUI. Both drive one
command layer.

This module is the internal half, and it is deliberately only a **model**: a
string, a cursor, a history and a log. It draws nothing, it imports no toolkit
and it knows no GPU. The application's window manager places and paints it as
quads, the same way it paints every other piece of chrome, and
each host feeds it keys -- Qt through ``keyPressEvent``, the browser through a
``keydown`` listener, both translating into :mod:`emtk.keys` first.

What it deliberately is not
---------------------------
Not a terminal. There is no multi-line editing, no selection and no mouse-drag
region: one line, a caret, and a short scrollback of what the command layer
said. Anything richer belongs in the docked console, which is a real text widget
and already has it.

Focus is explicit, and that is a decision rather than an oversight. The viewport
binds single letters to actions -- ``r`` for cartoon, ``s`` for sidechains -- so
a prompt that swallowed every keystroke would silently disable them. The prompt
takes keys only once it has focus, which a click gives it, and so does Return
pressed over the scene; Escape gives it back. The unfocused prompt says so, so
the rule is discoverable rather than folklore.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..events import CONTROL_MODIFIER, META_MODIFIER
from ..keys import (
    KEY_BACKSPACE,
    KEY_DELETE,
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_HOME,
    KEY_LEFT,
    KEY_RETURN,
    KEY_RIGHT,
    KEY_UP,
)

__all__ = ["CommandLine", "LogLine"]

#: What the prompt says when the application does not say. PyMOL writes its own
#: name here, and an application should: the line is drawn over the scene, not
#: in a terminal, so it has to declare what it is a prompt *for*. emtk does not
#: know the name of the program it is drawing, so it asks -- pass ``prompt=``
#: to :class:`CommandLine`.
PROMPT = ">"

#: Shown instead of the prompt when nothing has focus. It is the only place the
#: focus rule is stated, so it states it.
HINT = "press Return to type a command"


@dataclass(frozen=True)
class LogLine:
    """One line of scrollback.

    Attributes
    ----------
    text : str
        The line, already formatted.
    kind : str
        ``"echo"`` for the command as typed, ``"message"`` for output,
        ``"error"`` for a refusal. The painter colours by this rather than by
        parsing the text, because a message that happens to start with "error"
        is not one.
    """

    text: str
    kind: str = "message"


class CommandLine:
    """A one-line editor, its history, and the log of what came back.

    Parameters
    ----------
    run : callable, optional
        Receives the submitted line. This is the whole seam between the prompt
        and the command language: the desktop passes ``Cmd.do``, and anything
        else that can run a emtk command passes its own.
    """

    #: How many scrollback lines are kept. PyMOL's ``internal_feedback`` governs
    #: how many are *shown*; this is the buffer behind it, so scrolling up
    #: through a fetch that printed twenty lines works.
    MAX_LOG = 200

    #: How many are shown by default. One, as PyMOL ships: the log is over the
    #: molecule, and a viewer that permanently hides a fifth of its scene to
    #: show output nobody is reading is worse than one that shows the last line.
    DEFAULT_FEEDBACK = 1

    #: How many history entries are kept.
    MAX_HISTORY = 500

    def __init__(
        self,
        run: Callable[[str], None] | None = None,
        prompt: str = PROMPT,
    ) -> None:
        #: What is drawn before the typed text, and echoed into the log.
        #: The application's name belongs here, not in this module.
        self.prompt = prompt
        #: Whether the prompt is drawn at all. PyMOL's ``internal_prompt``.
        self.visible = True
        #: Whether keys reach it. See the module docstring for why this is not
        #: simply always true.
        self.focused = False
        self.text = ""
        self.cursor = 0
        self.log: list[LogLine] = []
        self.feedback = self.DEFAULT_FEEDBACK
        self.history: list[str] = []
        #: Where Up/Down currently sits: ``len(history)`` means "on the line
        #: being typed", which is the entry the arrows return to.
        self._history_index = 0
        #: What was being typed before Up was first pressed, so Down all the way
        #: back restores it rather than leaving the last recalled command.
        self._pending = ""
        self._run = run
        #: Supplies completions for ``(line, cursor)``. The command names live
        #: in the command layer, not here.
        self.completions: Callable[[str, int], Sequence[str]] | None = None
        #: Called when the prompt gains or loses focus, so a host can stop
        #: routing shortcuts past it.
        self.on_focus_change: Callable[[bool], None] | None = None

    # ── wiring ───────────────────────────────────────────────────────────
    def set_run(self, run: Callable[[str], None] | None) -> None:
        """Set the callable a submitted line is handed to."""
        self._run = run

    def set_focus(self, focused: bool) -> None:
        """Focus or unfocus the prompt, notifying the host when it changes."""
        focused = bool(focused)
        if focused == self.focused:
            return
        self.focused = focused
        if self.on_focus_change is not None:
            self.on_focus_change(focused)

    # ── the log ──────────────────────────────────────────────────────────
    def append(self, text: str, kind: str = "message") -> None:
        """Add a line of output, splitting it if it carries newlines.

        Parameters
        ----------
        text : str
            The output. A multi-line string becomes several entries, because
            the painter draws one entry per row and would otherwise print the
            escape as a glyph.
        kind : str
            ``"echo"``, ``"message"`` or ``"error"``.
        """
        for part in str(text).splitlines() or [""]:
            self.log.append(LogLine(part, kind))
        if len(self.log) > self.MAX_LOG:
            del self.log[: len(self.log) - self.MAX_LOG]

    def append_message(self, text: str) -> None:
        """Add ordinary output. Shaped to be passed as a message callback."""
        self.append(text, "message")

    def append_error(self, text: str) -> None:
        """Add a refusal. Shaped to be passed as an error callback."""
        self.append(text, "error")

    def clear_log(self) -> None:
        """Empty the scrollback."""
        self.log.clear()

    def visible_log(self) -> list[LogLine]:
        """Return the last :attr:`feedback` lines, oldest first."""
        if self.feedback <= 0:
            return []
        return self.log[-int(self.feedback):]

    # ── editing ──────────────────────────────────────────────────────────
    def set_text(self, text: str, cursor: int | None = None) -> None:
        """Replace the line, putting the caret at *cursor* (default: the end)."""
        self.text = str(text)
        self.cursor = len(self.text) if cursor is None else self._clamp(cursor)

    def insert(self, text: str) -> None:
        """Insert *text* at the caret.

        Control characters are dropped rather than inserted: a paste carries
        newlines and tabs, and a tab that reaches the buffer draws as a missing
        glyph while a newline is invisible and breaks the line silently.
        """
        clean = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
        if not clean:
            return
        self.text = self.text[: self.cursor] + clean + self.text[self.cursor:]
        self.cursor += len(clean)

    def _clamp(self, index: int) -> int:
        return max(0, min(int(index), len(self.text)))

    def submit(self) -> str:
        """Run the current line, log it, and clear the editor.

        Returns
        -------
        str
            The line that was run, or ``""`` when it was blank.

        Notes
        -----
        The line is echoed into the log *before* it runs, so output produced by
        the command lands underneath the command that produced it rather than
        above it. Exceptions are caught and logged as errors: a prompt that
        propagates a mistyped command into the host's paint loop takes the
        window down with it.
        """
        line = self.text.strip()
        self.text = ""
        self.cursor = 0
        self._history_index = len(self.history)
        self._pending = ""
        if not line:
            return ""

        if not self.history or self.history[-1] != line:
            self.history.append(line)
            if len(self.history) > self.MAX_HISTORY:
                del self.history[: len(self.history) - self.MAX_HISTORY]
        self._history_index = len(self.history)

        self.append(f"{self.prompt} {line}", "echo")
        if self._run is None:
            self.append_error("no command layer is connected")
            return line
        try:
            self._run(line)
        except Exception as exc:  # noqa: BLE001 - a bad command is not a crash
            self.append_error(f"{type(exc).__name__}: {exc}")
        return line

    def recall(self, delta: int) -> bool:
        """Step through the history. ``-1`` is older, ``+1`` newer.

        Returns
        -------
        bool
            Whether anything changed.
        """
        if not self.history:
            return False
        if self._history_index >= len(self.history):
            self._pending = self.text
        index = max(0, min(self._history_index + delta, len(self.history)))
        if index == self._history_index:
            return False
        self._history_index = index
        self.set_text(
            self._pending if index >= len(self.history) else self.history[index]
        )
        return True

    def complete(self) -> bool:
        """Extend the line to the longest common completion, or list them.

        Returns
        -------
        bool
            Whether the line or the log changed.

        Notes
        -----
        The two behaviours are the shell's, and both matter here: a unique
        completion should not make the user read a list of one, and an ambiguous
        one should not silently do nothing. The word being completed is found by
        the same whitespace-and-comma split the dispatcher uses, so ``color
        re<Tab>`` completes the colour and not the command.
        """
        if self.completions is None:
            return False
        try:
            candidates = [str(c) for c in self.completions(self.text, self.cursor)]
        except Exception:  # noqa: BLE001 - completion is a convenience
            return False
        if not candidates:
            return False

        head = self.text[: self.cursor]
        word = _current_word(head)
        shared = _common_prefix(candidates)
        if len(shared) > len(word):
            self.text = head[: len(head) - len(word)] + shared + self.text[self.cursor:]
            self.cursor = len(head) - len(word) + len(shared)
            return True
        if len(candidates) > 1:
            self.append("  ".join(sorted(candidates)[:40]), "message")
            return True
        return False

    # ── keys ─────────────────────────────────────────────────────────────
    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        # Tab completes. `complete()` has been here all along with nothing
        # calling it: the key was never handled, and would not have arrived
        # anyway -- Qt gives Tab to focus navigation before a key handler sees
        # it, so the widget has to claim it in `event()`.
        from ..keys import KEY_TAB

        if key == KEY_TAB:
            self.complete()
            return True

        """Handle one key press. Returns whether it was consumed.

        Parameters
        ----------
        key : int
            One of :mod:`emtk.keys`' constants, or ``0`` for a key that
            only produces text.
        text : str
            The character the key produced, if any.
        modifiers : int
            A mask of :mod:`emtk.events`' ``*_MODIFIER`` values.

        Notes
        -----
        Command on macOS and Control elsewhere are accepted interchangeably for
        the line-editing shortcuts. A browser on a Mac reports ``metaKey`` where
        the same user's Linux browser reports ``ctrlKey``, and a prompt that
        honoured only one of them would work on one machine.
        """
        if not self.focused:
            return False

        control = bool(modifiers & (CONTROL_MODIFIER | META_MODIFIER))
        if control:
            return self._control_key(text)

        if key in (KEY_RETURN, KEY_ENTER):
            self.submit()
            return True
        if key == KEY_ESCAPE:
            # Escape clears a half-typed line first and only then gives focus
            # back, which is the behaviour of every prompt that has both: a
            # single key that does two things in an order nobody can predict is
            # how a line you meant to keep disappears.
            if self.text:
                self.set_text("")
            else:
                self.set_focus(False)
            return True
        if key == KEY_TAB:
            self.complete()
            return True
        if key == KEY_BACKSPACE:
            if self.cursor > 0:
                self.text = self.text[: self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
            return True
        if key == KEY_DELETE:
            if self.cursor < len(self.text):
                self.text = self.text[: self.cursor] + self.text[self.cursor + 1:]
            return True
        if key == KEY_LEFT:
            self.cursor = self._clamp(self.cursor - 1)
            return True
        if key == KEY_RIGHT:
            self.cursor = self._clamp(self.cursor + 1)
            return True
        if key == KEY_HOME:
            self.cursor = 0
            return True
        if key == KEY_END:
            self.cursor = len(self.text)
            return True
        if key == KEY_UP:
            self.recall(-1)
            return True
        if key == KEY_DOWN:
            self.recall(+1)
            return True

        if text:
            self.insert(text)
            return True
        # A focused prompt eats bare modifier presses rather than letting them
        # fall through to the viewport's letter shortcuts.
        return key != 0

    def _control_key(self, text: str) -> bool:
        """Handle the ctrl/command shortcuts. Returns whether one applied.

        The readline set, minus what a one-line editor cannot use. ``ctrl+W``
        deletes the word behind the caret, which is the one an ordinary
        backspace cannot replace.
        """
        # Qt reports ctrl+A as the control character \x01 rather than as "a".
        letter = (text or "").lower()
        if len(letter) == 1 and letter < " ":
            letter = chr(ord(letter) + 96)
        if letter == "a":
            self.cursor = 0
            return True
        if letter == "e":
            self.cursor = len(self.text)
            return True
        if letter == "k":
            self.text = self.text[: self.cursor]
            return True
        if letter == "u":
            self.text = self.text[self.cursor:]
            self.cursor = 0
            return True
        if letter == "w":
            head = self.text[: self.cursor].rstrip()
            cut = max(head.rfind(" "), head.rfind(",")) + 1
            self.text = self.text[:cut] + self.text[self.cursor:]
            self.cursor = cut
            return True
        if letter == "l":
            self.clear_log()
            return True
        return False


def _current_word(head: str) -> str:
    """Return the word the caret sits at the end of.

    Parameters
    ----------
    head : str
        The line up to the caret.

    Returns
    -------
    str
        The trailing run of non-separator characters, empty when the caret
        follows a separator.
    """
    for index in range(len(head) - 1, -1, -1):
        if head[index] in " \t,":
            return head[index + 1:]
    return head


def _common_prefix(values: Sequence[str]) -> str:
    """Return the longest prefix every value in *values* shares."""
    if not values:
        return ""
    shortest = min(values, key=len)
    for index, char in enumerate(shortest):
        if any(value[index] != char for value in values):
            return shortest[:index]
    return shortest
