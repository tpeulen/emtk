"""Composed text input: dead keys, accented characters and input methods (IME).

Typing ``é`` with a dead key, or ``日本`` through a Japanese input method, is
two different things the operating system does on behalf of an application:

* it **composes** -- shows a provisional string (the *preedit*: ``´``, or
  ``にほん`` underlined) that the user is still editing, and that the keys go to;
* it **commits** -- hands the finished text to the application, which inserts
  it like any typed character.

emtk receives committed text exactly as it receives typing: as the ``text`` of
a key event (``on_key_press(0, "日本", 0)``), so every field takes it without
knowing an input method was involved. The preedit is separate state, delivered
by a host that can see it through :meth:`emtk.app.Surface.on_text_compose`.
It lives in ``io.preedit`` until the next composition event replaces it, and the
focused text widget draws it at its caret (underlined, never part of the value)
and reports where its caret is in ``io.ime_caret``, which a host hands back to
the operating system so the candidate window opens beside the text.

What each host can see
----------------------
* **Qt** (:mod:`emtk.qt_host`) receives ``QInputMethodEvent``: the commit and
  the preedit with its cursor, and asks the control for the caret rectangle.
* **glfw** (:mod:`emtk.native`) delivers committed text through its ``char``
  callback, one code point at a time, whatever the layout, input method or dead
  key produced it. GLFW 3.4 exposes no preedit: on macOS its view keeps the
  marked text to itself. What its view *does* answer, through the public
  ``NSTextInputClient`` protocol, is whether a composition is under way
  (``hasMarkedText``). That is what matters most: GLFW reports every physical
  key before the input method sees it, so without asking, the Return that
  confirms a conversion also submitted the line, and the Backspace that edits a
  composition also deleted a character of the field.
  :class:`MarkedTextProbe` asks, and the native host holds such keys back.

This module imports no toolkit. The Cocoa probe reaches the Objective-C runtime
through :mod:`ctypes` and is only built on a glfw window on macOS.
"""
from __future__ import annotations

import sys
import unicodedata
from typing import NamedTuple

__all__ = [
    "MarkedTextProbe",
    "Preedit",
    "committed_text",
    "input_method_probe",
    "splice",
]


class Preedit(NamedTuple):
    """The provisional text of a composition and the cursor inside it.

    Attributes
    ----------
    text : str
        What the input method shows as not yet committed; ``""`` when nothing
        is being composed.
    cursor : int
        The input method's cursor, an index into *text*.
    """

    text: str = ""
    cursor: int = 0


def committed_text(text: str) -> str:
    """The part of a ``char`` event's text that types, or ``""``.

    Control characters (category ``Cc``: Return, Tab, Escape as characters)
    are the key events' business and are dropped. Everything else types --
    including the *format* characters that ``str.isprintable`` rejects: the
    zero-width joiner of an emoji sequence (``👩‍💻``), the zero-width
    non-joiner Persian and the Indic scripts write with, and a variation
    selector. Lone surrogates (a host that split a character) are dropped.
    """
    return "".join(
        ch for ch in str(text or "")
        if unicodedata.category(ch) not in ("Cc", "Cs")
    )


def splice(text: str, caret: int, preedit: str) -> tuple[str, int, int]:
    """*text* as drawn while *preedit* is composed at *caret*.

    Returns
    -------
    tuple
        ``(shown, start, end)``: the string to draw, and the span of the
        preedit in it (``start == end`` when nothing is composed). The caret is
        drawn at ``start + preedit cursor``.
    """
    caret = max(0, min(int(caret), len(text)))
    if not preedit:
        return text, caret, caret
    return text[:caret] + preedit + text[caret:], caret, caret + len(preedit)


class MarkedTextProbe:
    """Asks a glfw window's Cocoa view whether an input method is composing.

    Parameters
    ----------
    view : int
        The ``NSView`` pointer (the window's ``contentView``).

    Notes
    -----
    Only the public ``NSTextInputClient`` protocol is used:
    ``hasMarkedText`` is how AppKit itself asks the same view. The view is
    asked on every key, which costs one message send.
    """

    def __init__(self, view: int) -> None:
        self._view = int(view)
        self._send_bool = _objc_function("bool")
        self._has_marked = _selector(b"hasMarkedText")

    def composing(self) -> bool:
        """Whether a composition (marked text) is under way in the view."""
        try:
            return bool(self._send_bool(self._view, self._has_marked))
        except Exception:  # noqa: BLE001 - a view that went away is not composing
            return False

    @classmethod
    def for_glfw_window(cls, window) -> MarkedTextProbe | None:
        """A probe for a glfw window on macOS, else ``None``.

        ``None`` too when the view does not answer ``hasMarkedText`` -- a GLFW
        built without its text-input client -- so nothing is ever held back on
        a guess.
        """
        if sys.platform != "darwin" or window is None:
            return None
        try:
            import glfw  # noqa: PLC0415

            ns_window = glfw.get_cocoa_window(window)
            if not ns_window:
                return None
            send_id = _objc_function("id")
            view = send_id(int(ns_window), _selector(b"contentView"))
            if not view:
                return None
            responds = _objc_function("bool_sel")
            if not responds(int(view), _selector(b"respondsToSelector:"),
                            _selector(b"hasMarkedText")):
                return None
            return cls(int(view))
        except Exception:  # noqa: BLE001 - no runtime, no Cocoa window: no probe
            return None


def input_method_probe(canvas) -> MarkedTextProbe | None:
    """The composition probe for a rendercanvas *canvas*, or ``None``.

    Only a glfw canvas on macOS has one (see the module notes); every other
    host either sees the input method itself (Qt) or filters composing keys
    before the application gets them (glfw on X11 and Windows).
    """
    return MarkedTextProbe.for_glfw_window(getattr(canvas, "_window", None))


# --------------------------------------------------------------------------- #
# The Objective-C runtime, through ctypes
# --------------------------------------------------------------------------- #
_RUNTIME: dict = {}


def _runtime():
    if "lib" not in _RUNTIME:
        import ctypes  # noqa: PLC0415
        import ctypes.util  # noqa: PLC0415

        path = ctypes.util.find_library("objc")
        if not path:
            raise OSError("no Objective-C runtime")
        lib = ctypes.cdll.LoadLibrary(path)
        lib.sel_registerName.restype = ctypes.c_void_p
        lib.sel_registerName.argtypes = [ctypes.c_char_p]
        _RUNTIME["lib"] = lib
    return _RUNTIME["lib"]


def _selector(name: bytes) -> int:
    return int(_runtime().sel_registerName(name))


def _objc_function(kind: str):
    """``objc_msgSend`` cast to one signature (arm64 requires the exact one)."""
    import ctypes  # noqa: PLC0415

    key = "send_" + kind
    if key not in _RUNTIME:
        address = ctypes.cast(_runtime().objc_msgSend, ctypes.c_void_p).value
        signature = {
            "id": ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p),
            "bool": ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p),
            "bool_sel": ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_void_p),
        }[kind]
        _RUNTIME[key] = signature(address)
    return _RUNTIME[key]
