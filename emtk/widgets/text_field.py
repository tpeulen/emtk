"""A one-line text field: the editor every emtk text entry shares.

Why this exists rather than reusing the prompt
----------------------------------------------
:class:`~emtk.widgets.command_line.CommandLine` is a one-line editor
already, but it is *the prompt*: it owns a history, a log of what came back, and
a submit that runs a command. A search box shares none of that and would have to
be told to suppress all three.

What it does share is the part that is genuinely hard -- editing text through
nothing but key codes -- so that is what is here: the string, the caret, a
selection, undo, the clipboard and the platform's shortcuts. ``im.input_text``,
a combo list's filter, a DataTable cell and the retained inputs all edit
through it, so a shortcut works in one exactly when it works in all.

Shortcuts
---------
Modifiers arrive normalised (:mod:`emtk.keys`): ``CONTROL_MODIFIER`` is the
primary one, Command on a Mac and Ctrl elsewhere; ``META_MODIFIER`` is the
Mac's physical Control key.

=====================  ===================  =========================
action                 Mac                  Windows / Linux
=====================  ===================  =========================
select all             Cmd+A                Ctrl+A
copy / cut / paste     Cmd+C / X / V        Ctrl+C / X / V
undo                   Cmd+Z                Ctrl+Z
redo                   Cmd+Shift+Z          Ctrl+Y, Ctrl+Shift+Z
word left / right      Option+Left/Right    Ctrl+Left/Right
line start / end       Cmd+Left/Right,      Home / End
                       Home/End, Ctrl+A/E
delete word            Option+Backspace     Ctrl+Backspace / Delete
delete to line start   Cmd+Backspace        --
=====================  ===================  =========================

Shift with any movement extends the selection; typing or pasting replaces it;
Backspace and Delete delete it. Control-A/E/B/F/D/H/K on a Mac are the Emacs
bindings a Cocoa field has, which is why Control-A is *not* select-all there.

Focus is **not** held here. The window manager above owns which field has the
caret, because a key arrives at the panel and something has to say where it
goes.
"""
from __future__ import annotations

from collections.abc import Callable

__all__ = ["TextField", "index_at", "paint"]

_UNDO_DEPTH = 100


def _is_word(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class TextField:
    """An editable string with a caret and a selection.

    Parameters
    ----------
    on_change : callable, optional
        Called with the new text after every edit. A search box filters as you
        type, which is the whole reason it is a field and not a prompt.
    placeholder : str, optional
        Drawn when the field is empty; the panel reads it.

    Attributes
    ----------
    anchor : int
        The fixed end of the selection; the caret is the moving one. Equal to
        :attr:`cursor` when nothing is selected. Assigning :attr:`cursor`
        collapses the selection, so an owner that moves the caret by hand
        never leaves one behind by accident.
    """

    def __init__(self, on_change: Callable[[str], None] | None = None,
                 placeholder: str = "") -> None:
        self.text = ""
        self._cursor = 0
        self.anchor = 0
        self.placeholder = placeholder
        self.on_change = on_change
        self._undo: list[tuple[str, int, int]] = []
        self._redo: list[tuple[str, int, int]] = []
        self._typing = False

    # -- the caret and the selection ------------------------------------ #
    @property
    def cursor(self) -> int:
        return min(self._cursor, len(self.text))

    @cursor.setter
    def cursor(self, value: int) -> None:
        self._cursor = self.anchor = max(0, min(int(value), len(self.text)))

    def move(self, index: int, extend: bool = False) -> None:
        """Put the caret at *index*; with *extend*, the selection follows it."""
        self._typing = False
        index = max(0, min(int(index), len(self.text)))
        if extend:
            self.anchor = min(self.anchor, len(self.text))
            self._cursor = index
        else:
            self.cursor = index

    def has_selection(self) -> bool:
        return self.cursor != min(self.anchor, len(self.text))

    def selection(self) -> tuple[int, int]:
        """``(start, end)`` of the selection, ordered; equal when empty."""
        a, b = min(self.anchor, len(self.text)), self.cursor
        return (a, b) if a <= b else (b, a)

    def selected_text(self) -> str:
        lo, hi = self.selection()
        return self.text[lo:hi]

    def select_all(self) -> None:
        self._typing = False
        self.anchor, self._cursor = 0, len(self.text)

    def select_word_at(self, index: int) -> None:
        """Select the word (or the run of spaces or punctuation) at *index*."""
        n = len(self.text)
        index = max(0, min(int(index), n))
        if n == 0:
            return
        probe = index if index < n else n - 1
        kind = _is_word(self.text[probe])
        lo = hi = probe
        while lo > 0 and _is_word(self.text[lo - 1]) == kind:
            lo -= 1
        while hi < n and _is_word(self.text[hi]) == kind:
            hi += 1
        self.anchor, self._cursor = lo, hi

    def word_left(self, i: int) -> int:
        while i > 0 and not _is_word(self.text[i - 1]):
            i -= 1
        while i > 0 and _is_word(self.text[i - 1]):
            i -= 1
        return i

    def word_right(self, i: int, mac: bool) -> int:
        n = len(self.text)
        if mac:                       # to the end of this word, or the next
            while i < n and not _is_word(self.text[i]):
                i += 1
            while i < n and _is_word(self.text[i]):
                i += 1
        else:                         # to the start of the next word
            while i < n and _is_word(self.text[i]):
                i += 1
            while i < n and not _is_word(self.text[i]):
                i += 1
        return i

    # -- editing -------------------------------------------------------- #
    def set_text(self, text: str) -> None:
        """Replace the contents, caret at the end, history forgotten."""
        self.text = str(text)
        self.cursor = len(self.text)
        self._undo.clear()
        self._redo.clear()
        self._typing = False
        self._changed()

    def clear(self) -> bool:
        """Empty it. Returns whether there was anything to clear."""
        if not self.text:
            return False
        self._replace(0, len(self.text), "")
        return True

    def _snapshot(self) -> None:
        self._undo.append((self.text, self.cursor, self.anchor))
        del self._undo[:-_UNDO_DEPTH]
        self._redo.clear()

    def _replace(self, lo: int, hi: int, new: str, typing: bool = False) -> None:
        if not (typing and self._typing):
            self._snapshot()
        self._typing = typing
        self.text = self.text[:lo] + new + self.text[hi:]
        self.cursor = lo + len(new)
        self._changed()

    def insert(self, text: str, typing: bool = False) -> bool:
        """Put *text* in place of the selection (at the caret when none).

        Printable text only: a tab that reaches the buffer draws as a missing
        glyph and a newline is invisible, so a paste loses both.
        """
        clean = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
        if not clean and not self.has_selection():
            return False
        lo, hi = self.selection()
        self._replace(lo, hi, clean, typing=typing and bool(clean))
        return True

    def delete_selection(self) -> bool:
        if not self.has_selection():
            return False
        lo, hi = self.selection()
        self._replace(lo, hi, "")
        return True

    def _delete_to(self, index: int) -> None:
        if self.delete_selection():
            return
        lo, hi = sorted((self.cursor, max(0, min(index, len(self.text)))))
        if lo != hi:
            self._replace(lo, hi, "")

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append((self.text, self.cursor, self.anchor))
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append((self.text, self.cursor, self.anchor))
        self._restore(self._redo.pop())
        return True

    def _restore(self, state: tuple[str, int, int]) -> None:
        self.text, cursor, anchor = state
        self.cursor = cursor
        self.anchor = anchor
        self._typing = False
        self._changed()

    # -- the clipboard -------------------------------------------------- #
    def copy(self) -> bool:
        """The selection to the system clipboard (:mod:`emtk.clipboard`)."""
        if not self.has_selection():
            return False
        from .. import clipboard  # noqa: PLC0415

        clipboard.copy(self.selected_text())
        return True

    def cut(self) -> bool:
        return self.copy() and self.delete_selection()

    def paste(self, text: str | None = None) -> bool:
        """The clipboard (or *text*) in place of the selection."""
        if text is None:
            from .. import clipboard  # noqa: PLC0415

            text = clipboard.paste()
        return self.insert(text or "")

    # -- keys ----------------------------------------------------------- #
    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press. Returns whether it was consumed.

        Every plain key is consumed while the field has the caret, including
        the ones it does nothing with -- a search box that lets `s` through to
        the shortcut that shows sticks is worse than one that ignores it. A
        primary-modifier chord the field does not know (Cmd+S, say) is *not*
        consumed, so the app's shortcut still runs.
        """
        from ..events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
        from ..keys import (KEY_BACKSPACE, KEY_DELETE, KEY_END, KEY_HOME, KEY_LEFT,
                            KEY_RIGHT, letter_of, mac_behaviors)

        mac = mac_behaviors()
        primary = bool(modifiers & CONTROL_MODIFIER)
        other = bool(modifiers & META_MODIFIER)
        alt = bool(modifiers & ALT_MODIFIER)
        shift = bool(modifiers & SHIFT_MODIFIER)
        # AltGr on Windows arrives as Ctrl+Alt with the character it typed.
        altgr = primary and alt and not mac and bool(text)
        chord = (primary and not altgr) or (mac and other)
        letter = letter_of(key, text) if chord else ""
        if letter:
            return (self._command(letter, shift, mac) if primary and not altgr
                    else self._emacs(letter))
        word = alt if mac else primary
        line = primary and mac
        n = len(self.text)
        if key in (KEY_LEFT, KEY_RIGHT):
            forward = key == KEY_RIGHT
            if line:
                target = n if forward else 0
            elif word:
                target = self.word_right(self.cursor, mac) if forward else self.word_left(self.cursor)
            elif self.has_selection() and not shift:
                target = self.selection()[1 if forward else 0]
            else:
                target = self.cursor + (1 if forward else -1)
            self.move(target, extend=shift)
            return True
        if key in (KEY_HOME, KEY_END):
            self.move(0 if key == KEY_HOME else n, extend=shift)
            return True
        if key == KEY_BACKSPACE:
            if line:
                self._delete_to(0)
            else:
                self._delete_to(self.word_left(self.cursor) if word else self.cursor - 1)
            return True
        if key == KEY_DELETE:
            self._delete_to(self.word_right(self.cursor, mac) if word else self.cursor + 1)
            return True
        if chord:
            return False              # Ctrl+- and the like: the app's, never typed
        if text:
            self.insert(text, typing=True)
        return True

    def _command(self, letter: str, shift: bool, mac: bool) -> bool:
        if letter == "a":
            self.select_all()
        elif letter == "c":
            self.copy()
        elif letter == "x":
            self.cut()
        elif letter == "v":
            self.paste()
        elif letter == "z":
            self.redo() if shift else self.undo()
        elif letter == "y" and not mac:
            self.redo()
        else:
            return False
        return True

    def _emacs(self, letter: str) -> bool:
        """Control-<letter> on a Mac, as a Cocoa text field has them."""
        n, at = len(self.text), self.cursor
        moves = {"a": 0, "e": n, "b": at - 1, "f": at + 1}
        if letter in moves:
            self.move(moves[letter])
        elif letter in ("d", "h", "k"):
            self._delete_to({"d": at + 1, "h": at - 1, "k": n}[letter])
        else:
            return False
        return True

    # ------------------------------------------------------------------ #
    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change(self.text)


def paint(p, field: TextField, x: float, y: float, w: float, h: float, colour,
          caret_colour=None, pad: float = 4.0) -> list[float]:
    """Draw *field* in a box: its selection, its text and (with *caret_colour*)
    the caret, scrolled so the caret is inside. Clipped by the caller.

    Returns the x of every caret position, ``len(text) + 1`` of them, for
    :func:`index_at` to turn a click into a place in the text.
    """
    from ..painter import ALIGN_LEFT, ALIGN_VCENTER  # noqa: PLC0415
    from ..style import TEXT_SELECTED_BG  # noqa: PLC0415

    text, at = field.text, field.cursor
    room = max(w - 2.0 * pad, 1.0)
    start = 0
    while caret_colour is not None and start < at and p.text_width(text[start:at]) > room - 1.0:
        start += 1
    left = x + pad
    xs = [left - p.text_width(text[i:start]) if i < start
          else left + p.text_width(text[start:i]) for i in range(len(text) + 1)]
    if caret_colour is not None and field.has_selection():
        lo, hi = field.selection()
        sx = max(xs[lo], x)
        p.fill_rect(sx, y + 2.0, max(min(xs[hi], x + w) - sx, 0.0), max(h - 4.0, 1.0),
                    TEXT_SELECTED_BG)
    p.text(left, y, room, h, ALIGN_VCENTER | ALIGN_LEFT, text[start:], colour)
    if caret_colour is not None:
        p.fill_rect(xs[at], y + h * 0.2, 1.0, h * 0.6, caret_colour)
    return xs


def index_at(xs: list[float], x: float) -> int:
    """The caret position nearest *x*, given :func:`paint`'s positions."""
    if not xs:
        return 0
    return min(range(len(xs)), key=lambda i: abs(xs[i] - x))
