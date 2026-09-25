"""Keyboard keys, as plain integers, and how each host spells them.

Why the engine owns these
-------------------------
The in-viewport command line is a text editor, and a text editor is decisions
about keys: Return submits, Up recalls, ctrl+A goes to the start of the line.
That is the same arithmetic-over-a-table shape as :mod:`emtk.events`, and
it has the same constraint -- the engine must be able to make those decisions
where there is no window system.

The values are Qt's ``Qt.Key_*``, for the same reason the button values are
Qt's: they are fixed by an ABI, so writing them out costs nothing, and a Qt
event's ``key()`` can be passed straight in. A browser reports something else
entirely -- ``KeyboardEvent.key`` is a *string* -- so :func:`key_from_dom`
translates into these rather than the engine learning a second vocabulary.

The DOM table is deliberately small: printable characters do not appear in it at
all, because a browser reports them as their own text and the editor inserts
that text. Only the keys that *act* need names.
"""
from __future__ import annotations

__all__ = [
    "KEY_BACKSPACE",
    "KEY_DELETE",
    "KEY_DOWN",
    "KEY_END",
    "KEY_ENTER",
    "KEY_ESCAPE",
    "KEY_HOME",
    "KEY_LEFT",
    "KEY_PAGE_DOWN",
    "KEY_INSERT",
    "KEY_F1",
    "KEY_F2",
    "KEY_F3",
    "KEY_F4",
    "KEY_F5",
    "KEY_F6",
    "KEY_F7",
    "KEY_F8",
    "KEY_F9",
    "KEY_F10",
    "KEY_F11",
    "KEY_F12",
    "KEY_PAGE_UP",
    "KEY_RETURN",
    "KEY_RIGHT",
    "KEY_TAB",
    "KEY_UP",
    "key_from_dom",
    "letter_of",
    "mac_behaviors",
    "modifiers_from_dom",
    "set_mac_behaviors",
    "typed_text",
]

#: ``Qt.Key_*``. Return and Enter are distinct -- Enter is the numeric keypad's
#: -- and both submit, which is why every caller has to test for the pair.
KEY_ESCAPE = 0x01000000
KEY_TAB = 0x01000001
KEY_BACKSPACE = 0x01000003
KEY_RETURN = 0x01000004
KEY_ENTER = 0x01000005
KEY_DELETE = 0x01000007
KEY_HOME = 0x01000010
KEY_END = 0x01000011
KEY_LEFT = 0x01000012
KEY_UP = 0x01000013
KEY_RIGHT = 0x01000014
KEY_DOWN = 0x01000015
#: The paging pair. Nothing needed them while the only editor was one line
#: long; a document editor is the first control for which "move a screenful"
#: is a distinct idea from "move a line".
KEY_PAGE_UP = 0x01000016
KEY_PAGE_DOWN = 0x01000017
KEY_INSERT = 0x01000006

#: The function keys, ``Qt.Key_F1`` upward and contiguous. An application
#: binds its shortcuts to these -- cmc starts and stops an acquisition on
#: F2 -- and without them `im.Key.F2` was `None`, so the test against it
#: could never be true and the shortcut silently did nothing.
KEY_F1 = 0x01000030
KEY_F2 = 0x01000031
KEY_F3 = 0x01000032
KEY_F4 = 0x01000033
KEY_F5 = 0x01000034
KEY_F6 = 0x01000035
KEY_F7 = 0x01000036
KEY_F8 = 0x01000037
KEY_F9 = 0x01000038
KEY_F10 = 0x01000039
KEY_F11 = 0x0100003A
KEY_F12 = 0x0100003B

# --------------------------------------------------------------------------- #
# The printable keys
# --------------------------------------------------------------------------- #
#
# ``ImGuiKey_A`` ... ``ImGuiKey_Z`` and ``ImGuiKey_0`` ... ``ImGuiKey_9``. A
# text field never needed them -- it reads ``io.text``, which is the character
# the host produced, shift and layout already applied. A *shortcut* does:
# "Ctrl+Z" is a question about which key is down, not about what it typed.
#
# Their values are the ordinals, so a host that has a character in hand can use
# it directly and one that has a keycode can too.
for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    globals()["KEY_" + _letter] = ord(_letter.lower())
del _letter
for _digit in range(10):
    globals()["KEY_%d" % _digit] = ord(str(_digit))
del _digit

KEY_SPACE = ord(" ")

# --------------------------------------------------------------------------- #
# Chord modifiers
# --------------------------------------------------------------------------- #
#
# ``ImGuiMod_Ctrl`` and friends: bits a key is OR-ed with to make a chord, so
# "Ctrl+S" is one value a shortcut table can hold. High enough not to collide
# with a key code, which is an ordinal or a 0x0100xxxx special.
MOD_NONE = 0
MOD_CTRL = 1 << 28
MOD_SHIFT = 1 << 29
MOD_ALT = 1 << 30
MOD_SUPER = 1 << 31
MOD_MASK = MOD_CTRL | MOD_SHIFT | MOD_ALT | MOD_SUPER

#: ``KeyboardEvent.key`` -> the constants above.
#:
#: A browser names the keypad's Enter ``"Enter"`` as well, so there is nothing
#: to distinguish; it maps to ``KEY_RETURN`` and the pair test still holds.
_DOM_KEYS: dict[str, int] = {
    "Escape": KEY_ESCAPE,
    "Esc": KEY_ESCAPE,             # IE/Edge legacy spelling, still emitted
    "Tab": KEY_TAB,
    "Backspace": KEY_BACKSPACE,
    "Enter": KEY_RETURN,
    "Delete": KEY_DELETE,
    "Del": KEY_DELETE,
    "Home": KEY_HOME,
    "End": KEY_END,
    "ArrowLeft": KEY_LEFT,
    "ArrowUp": KEY_UP,
    "ArrowRight": KEY_RIGHT,
    "ArrowDown": KEY_DOWN,
    "PageUp": KEY_PAGE_UP,
    "PageDown": KEY_PAGE_DOWN,
    "Left": KEY_LEFT,
    "Up": KEY_UP,
    "Right": KEY_RIGHT,
    "Down": KEY_DOWN,
}


def key_from_dom(name: str) -> int:
    """Return the engine's key value for a DOM ``KeyboardEvent.key``.

    Parameters
    ----------
    name : str
        The browser's name for the key, e.g. ``"ArrowLeft"`` or ``"a"``.

    Returns
    -------
    int
        One of the ``KEY_*`` constants, or ``0`` for a key with no special
        meaning -- which is every printable character, and is not a failure:
        the caller passes the character's *text* alongside and the editor
        inserts it.
    """
    return _DOM_KEYS.get(str(name), 0)


# --------------------------------------------------------------------------- #
# The primary modifier
# --------------------------------------------------------------------------- #
#
# One convention on every host: once a host has translated its event,
# ``CONTROL_MODIFIER`` (``io.key_ctrl``) is the *primary* modifier -- Command
# on a Mac, Ctrl elsewhere -- and ``META_MODIFIER`` (``io.key_super``) is the
# other one: the physical Control key on a Mac, Win/Super elsewhere. That is
# Qt's macOS convention (and so Tk's, which copies it) and Dear ImGui's
# (``ConfigMacOSXBehaviors`` swaps Cmd and Ctrl), so "Ctrl+A" in a shortcut
# table means Cmd-A on a Mac and nobody tests for two keys. The hosts whose
# toolkits do not swap -- glfw through rendercanvas, the browser -- swap here.
#
# *Which* platform is the client's: in a page it is the browser's
# ``navigator``, not the server's ``sys.platform``.
_mac_override: bool | None = None
_mac_detected: bool | None = None


def _detect_mac() -> bool:
    import sys  # noqa: PLC0415

    if sys.platform == "darwin":
        return True
    if sys.platform != "emscripten":
        return False
    try:
        import js  # type: ignore[import-not-found]  # noqa: PLC0415 - Pyodide
    except ImportError:
        return False
    nav = getattr(js, "navigator", None)
    names = []
    for getter in (lambda: nav.userAgentData.platform, lambda: nav.platform,
                   lambda: nav.userAgent):
        try:
            names.append(str(getter() or ""))
        except Exception:  # noqa: BLE001 - an attribute this browser lacks
            continue
    return any(tag in n.lower() for n in names for tag in ("mac", "iphone", "ipad"))


def mac_behaviors() -> bool:
    """Whether text editing follows the Mac's conventions (the client's platform).

    Command is the primary modifier, Option moves by word, Command-arrows go
    to the line's ends, and Control-A / Control-E are Emacs' line start and
    end -- as a Cocoa text field does. Elsewhere Ctrl moves by word and
    Ctrl+Y redoes.
    """
    global _mac_detected
    if _mac_override is not None:
        return _mac_override
    if _mac_detected is None:
        _mac_detected = _detect_mac()
    return _mac_detected


def set_mac_behaviors(flag: bool | None) -> None:
    """Force the Mac conventions on or off; ``None`` goes back to detecting them."""
    global _mac_override
    _mac_override = None if flag is None else bool(flag)


def letter_of(key: int, text: str = "") -> str:
    """The letter or digit a shortcut names, lower case, else ``""``.

    Qt (and Tk, which copies it) reports ``Qt.Key_A`` -- the *uppercase*
    ordinal -- emtk's own :data:`KEY_A` is the lowercase one, and a browser
    or glfw may give no code at all, only the typed *text*. All three mean
    the same shortcut.
    """
    key = int(key or 0)
    if 65 <= key <= 90 or 97 <= key <= 122 or 48 <= key <= 57:
        return chr(key).lower()
    text = str(text or "")
    if len(text) == 1 and text.isascii() and text.isalnum():
        return text.lower()
    return ""


def typed_text(text: str, modifiers: int) -> str:
    """What a key event *types*: its text, unless a shortcut modifier is held.

    A browser reports Cmd+A with ``key == "a"``, and a text field that took
    that as typing inserted an "a". Ctrl+Alt is AltGr off a Mac, which types
    (``@`` on a German layout), so it is kept there.
    """
    from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER  # noqa: PLC0415

    modifiers = int(modifiers or 0)
    mac = mac_behaviors()
    if modifiers & CONTROL_MODIFIER and not (not mac and modifiers & ALT_MODIFIER):
        return ""
    if mac and modifiers & META_MODIFIER:
        return ""
    return str(text or "")


def modifiers_from_dom(ctrl: bool, shift: bool, alt: bool, meta: bool,
                       mac: bool | None = None) -> int:
    """Pack a DOM event's four modifier booleans into an engine mask.

    Parameters
    ----------
    ctrl, shift, alt, meta : bool
        ``KeyboardEvent.ctrlKey`` and friends.
    mac : bool, optional
        Whether the client is a Mac; :func:`mac_behaviors` by default.

    Returns
    -------
    int
        A mask of :mod:`emtk.events`' ``*_MODIFIER`` values.

    Notes
    -----
    ``metaKey`` is Command on a Mac, the primary modifier, so there it is
    reported as ``CONTROL_MODIFIER`` and ``ctrlKey`` as ``META_MODIFIER`` --
    the convention every host follows (see above).
    """
    from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER

    if mac_behaviors() if mac is None else mac:
        ctrl, meta = meta, ctrl
    mask = 0
    if ctrl:
        mask |= CONTROL_MODIFIER
    if shift:
        mask |= SHIFT_MODIFIER
    if alt:
        mask |= ALT_MODIFIER
    if meta:
        mask |= META_MODIFIER
    return mask
