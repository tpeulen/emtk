"""A one-line text field for panels drawn inside the viewport.

Why this exists rather than reusing the prompt
----------------------------------------------
:class:`~emtk.widgets.command_line.CommandLine` is a one-line editor
already, but it is *the prompt*: it owns a history, a log of what came back, and
a submit that runs a command. A search box shares none of that and would have to
be told to suppress all three.

What it does share is the part that is genuinely hard — editing text with a
caret through nothing but key codes — so that is what is here, and nothing else.
The panel decides where it is drawn and what a change means; this holds the
string and the caret.

Focus is **not** held here. The window manager above owns which field has the
caret, because a key arrives at the panel and something
has to say where it goes — and two carets on screen is two places a keystroke
could be going with no way to tell which.
"""
from __future__ import annotations

from collections.abc import Callable

__all__ = ["TextField"]


class TextField:
    """An editable string with a caret.

    Parameters
    ----------
    on_change : callable, optional
        Called with the new text after every edit. A search box filters as you
        type, which is the whole reason it is a field and not a prompt.
    placeholder : str, optional
        Drawn when the field is empty; the panel reads it.
    """

    def __init__(
        self,
        on_change: Callable[[str], None] | None = None,
        placeholder: str = "",
    ) -> None:
        self.text = ""
        self.cursor = 0
        self.placeholder = placeholder
        self.on_change = on_change

    # ------------------------------------------------------------------ #
    def set_text(self, text: str) -> None:
        """Replace the contents, caret at the end."""
        self.text = str(text)
        self.cursor = len(self.text)
        self._changed()

    def clear(self) -> bool:
        """Empty it. Returns whether there was anything to clear."""
        if not self.text:
            return False
        self.text = ""
        self.cursor = 0
        self._changed()
        return True

    # ------------------------------------------------------------------ #
    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press. Returns whether it was consumed.

        Every key is consumed while the field has the caret, including the ones
        it does nothing with -- a search box that lets `s` through to the
        shortcut that shows sticks is worse than one that ignores it.
        """
        from ..keys import KEY_BACKSPACE, KEY_DELETE, KEY_END, KEY_HOME, KEY_LEFT, KEY_RIGHT

        if key == KEY_BACKSPACE:
            if self.cursor > 0:
                self.text = self.text[: self.cursor - 1] + self.text[self.cursor:]
                self.cursor -= 1
                self._changed()
            return True
        if key == KEY_DELETE:
            if self.cursor < len(self.text):
                self.text = self.text[: self.cursor] + self.text[self.cursor + 1:]
                self._changed()
            return True
        if key == KEY_LEFT:
            self.cursor = max(self.cursor - 1, 0)
            return True
        if key == KEY_RIGHT:
            self.cursor = min(self.cursor + 1, len(self.text))
            return True
        if key == KEY_HOME:
            self.cursor = 0
            return True
        if key == KEY_END:
            self.cursor = len(self.text)
            return True

        # Printable text only. A paste carries newlines and tabs, and a tab that
        # reaches the buffer draws as a missing glyph while a newline is
        # invisible -- the prompt drops both for the same reason.
        clean = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
        if clean:
            self.text = self.text[: self.cursor] + clean + self.text[self.cursor:]
            self.cursor += len(clean)
            self._changed()
        return True

    # ------------------------------------------------------------------ #
    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change(self.text)
