"""The system clipboard, from any emtk host.

An immediate-mode frame keeps its own clipboard (``im.set_clipboard_text``)
for copy and paste between its own text fields. That text never leaves the
process, so a "Copy as CSV" that should reach a spreadsheet needs the
*system* clipboard. There is no one API for it: a browser has
``navigator.clipboard``, and a desktop has a command per platform.
:func:`copy` tries them in that order and says whether one worked. A host
that owns a clipboard of its own (Tk, Qt) registers it with :func:`set_hook`
and is asked first.

Nothing here is imported at module scope beyond the standard library, so it
imports in Pyodide and headless alike.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable

__all__ = ["copy", "set_hook", "commands"]

_hook: Callable[[str], None] | None = None


def set_hook(hook: Callable[[str], None] | None) -> None:
    """Route :func:`copy` to *hook* (a host's own clipboard); ``None`` removes it."""
    global _hook
    _hook = hook


def commands() -> list[list[str]]:
    """The desktop copy commands to try on this platform, in order."""
    if sys.platform == "darwin":
        return [["pbcopy"]]
    if sys.platform.startswith("win"):
        return [["clip"]]
    return [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]


def _browser_copy(text: str) -> bool:
    try:
        import js  # type: ignore[import-not-found]  # Pyodide's bridge
    except ImportError:
        return False
    try:
        js.navigator.clipboard.writeText(text)
    except Exception:  # noqa: BLE001 - a page without clipboard permission
        return False
    return True


def copy(text: str) -> bool:
    """Put *text* on the system clipboard; returns whether it got there.

    Tried in order: the host's hook, the browser's ``navigator.clipboard``
    (under Pyodide), then the platform's copy command. Also keeps the text in
    the current immediate-mode context, when there is one, so a paste inside
    the app finds it too.
    """
    text = str(text)
    try:
        from . import im_widgets

        im_widgets.set_clipboard_text(text)
    except Exception:  # noqa: BLE001 - no frame running
        pass
    if _hook is not None:
        try:
            _hook(text)
            return True
        except Exception:  # noqa: BLE001
            pass
    if sys.platform == "emscripten":
        return _browser_copy(text)
    for command in commands():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode("utf-8"), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False
