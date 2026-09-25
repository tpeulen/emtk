"""The system clipboard, from any emtk host.

An immediate-mode frame keeps its own clipboard (``im.set_clipboard_text``)
for copy and paste between its own text fields. That text never leaves the
process, so a "Copy as CSV" that should reach a spreadsheet needs the
*system* clipboard. There is no one API for it: a browser has
``navigator.clipboard``, and a desktop has a command per platform.
:func:`copy` tries them in that order and says whether one worked;
:func:`paste` reads it back the same way. A host that owns a clipboard of
its own (Tk, Qt, glfw) registers it with :func:`set_hook` and is asked first
(:func:`use_tk`, :func:`use_glfw`, and ``emtk.qt_host.use_qt_clipboard`` --
Qt is only ever named in the Qt modules).

A page cannot *read* the clipboard synchronously (``readText`` is a promise
behind a permission prompt), so ``boot.js`` forwards the DOM's ``paste``
event instead and :func:`receive` holds its text for the paste it causes.

Nothing here is imported at module scope beyond the standard library, so it
imports in Pyodide and headless alike.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable

__all__ = ["copy", "paste", "receive", "holding", "set_hook", "commands", "paste_commands",
           "use_tk", "use_glfw",
           "last_copied"]

_hook: Callable[[str], None] | None = None
_paste_hook: Callable[[], str] | None = None
#: The text the page's last ``paste`` event carried (see :func:`receive`).
_received: str | None = None
#: What :func:`copy` was last handed, with a count so a caller can tell a
#: fresh copy from an old one (the page's ``copy`` event does).
_last: tuple[int, str] = (0, "")


def set_hook(hook: Callable[[str], None] | None,
             paste_hook: Callable[[], str] | None = None) -> None:
    """Route :func:`copy` to *hook* and :func:`paste` to *paste_hook* (a
    host's own clipboard); ``None`` removes them."""
    global _hook, _paste_hook
    _hook = hook
    _paste_hook = paste_hook if hook is not None or paste_hook is not None else None


def use_tk(root) -> None:
    """Route the clipboard through a Tk root's ``clipboard_get/append``."""
    def put(text: str) -> None:
        root.clipboard_clear()
        root.clipboard_append(text)

    def get() -> str:
        try:
            return str(root.clipboard_get())
        except Exception:  # noqa: BLE001 - TclError: the clipboard holds no text
            return ""

    set_hook(put, get)


def use_glfw(window=None) -> bool:
    """Route the clipboard through glfw (a native rendercanvas host on glfw).

    *window* is the ``GLFWwindow``; glfw 3.3 and later ignore it, so ``None``
    serves when the canvas does not say.
    """
    try:
        import glfw  # noqa: PLC0415
    except ImportError:
        return False

    def get() -> str:
        value = glfw.get_clipboard_string(window)
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        return value or ""

    set_hook(lambda text: glfw.set_clipboard_string(window, text), get)
    return True


def receive(text: str | None) -> None:
    """Hold *text* as the clipboard for the next :func:`paste` (a DOM paste);
    ``None`` drops what is held."""
    global _received
    _received = None if text is None else str(text)


def holding() -> bool:
    """Whether a received paste is still waiting for its :func:`paste`."""
    return _received is not None


def last_copied() -> tuple[int, str]:
    """``(count, text)`` of the most recent :func:`copy`."""
    return _last


def paste_commands() -> list[list[str]]:
    """The desktop paste commands to try on this platform, in order."""
    if sys.platform == "darwin":
        return [["pbpaste"]]
    if sys.platform.startswith("win"):
        return [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]]
    return [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"]]


def paste() -> str:
    """The system clipboard's text, or ``""``.

    Tried in order: the host's paste hook, the text a page's ``paste`` event
    delivered (:func:`receive`), the platform's paste command, and last the
    immediate-mode context's own clipboard.
    """
    global _received
    if _paste_hook is not None:
        try:
            return str(_paste_hook() or "")
        except Exception:  # noqa: BLE001 - a host clipboard holding no text
            pass
    if _received is not None:
        text, _received = _received, None
        return text
    if sys.platform != "emscripten":
        for command in paste_commands():
            if shutil.which(command[0]) is None:
                continue
            try:
                done = subprocess.run(command, capture_output=True, check=True, timeout=5)
            except (OSError, subprocess.SubprocessError):
                continue
            text = done.stdout.decode("utf-8", "replace")
            return text[:-2] if text.endswith("\r\n") and command[0] == "powershell" else text
    try:
        from . import im_widgets  # noqa: PLC0415

        text = im_widgets.get_clipboard_text()
        if text:
            return text
    except Exception:  # noqa: BLE001 - no frame running
        pass
    return _last[1]


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
    global _last
    text = str(text)
    _last = (_last[0] + 1, text)
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
