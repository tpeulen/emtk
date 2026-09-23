"""A window with no GUI toolkit to install: tkinter opens it, Pillow draws it.

Why a third host
----------------
:mod:`.qt_host` and :mod:`.wgpu_host` both ask Qt for the window. For a
small application that is most of what it ships: a frozen label-printer app
was 94 MB, of which PyQt5 was half, for a window, a timer and a clipboard.
``tkinter`` is part of the standard library and brings all three, and
:class:`~.pil_painter.PilPainter` draws a frame fast enough to present
(a 1080x720 application frame in about five milliseconds). So this host is
the whole toolkit for such an application: create it, give it the control,
run it.

What Tk is used for, and what it is not
---------------------------------------
Tk owns the window, the event loop, the clipboard and one image item that
the frame is pasted into. It draws nothing itself -- no Tk widget, no Tk
font -- so the interface is the same pixels :class:`~.testing.PixelPainter`
produces, on every platform, and a screenshot test of the control is a test
of what the window shows.

Keys are Qt's numbers
---------------------
:mod:`emtk.keys` and :mod:`emtk.events` use Qt's values, and controls written
against :mod:`.qt_host` test for them -- including Qt's *uppercase* ordinal
for a letter key and Qt's macOS convention that Command reports as
``CONTROL_MODIFIER`` (and Control as ``META_MODIFIER``). :func:`key_from_tk`
and :func:`modifiers_from_tk` translate into exactly that, so a control moves
between the two hosts unchanged.

Imports
-------
``tkinter`` and Pillow are imported when a host is built, never at module
scope: importing this module in a headless process (or a Python built
without Tk) costs nothing, and the key translation is testable anywhere.
"""
from __future__ import annotations

import sys
from collections.abc import Callable

from .events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from .keys import (
    KEY_BACKSPACE,
    KEY_DELETE,
    KEY_DOWN,
    KEY_END,
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_F1,
    KEY_HOME,
    KEY_INSERT,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RETURN,
    KEY_RIGHT,
    KEY_TAB,
    KEY_UP,
)

__all__ = ["TkHost", "key_from_tk", "modifiers_from_tk", "qt_application_exists"]

#: Tk keysym -> Qt key code, for every key that acts rather than types.
_TK_KEYS: dict[str, int] = {
    "Escape": KEY_ESCAPE,
    "Tab": KEY_TAB,
    "ISO_Left_Tab": KEY_TAB,       # X11's Shift+Tab; the Shift bit says "back"
    "BackSpace": KEY_BACKSPACE,
    "Return": KEY_RETURN,
    "KP_Enter": KEY_ENTER,
    "Insert": KEY_INSERT,
    "Delete": KEY_DELETE,
    "Home": KEY_HOME,
    "End": KEY_END,
    "Left": KEY_LEFT,
    "Up": KEY_UP,
    "Right": KEY_RIGHT,
    "Down": KEY_DOWN,
    "Prior": KEY_PAGE_UP,
    "Next": KEY_PAGE_DOWN,
    **{"F%d" % n: KEY_F1 + n - 1 for n in range(1, 13)},
}

#: Keysyms Tk reports for a modifier going down on its own. Not keys to a
#: control: the modifier arrives as a bit on the next real key.
_MODIFIER_KEYSYMS = frozenset((
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
    "Option_L", "Option_R", "Command", "Hyper_L", "Hyper_R",
))

_TK_SHIFT, _TK_CONTROL, _TK_MOD1, _TK_MOD2, _TK_MOD4 = 0x1, 0x4, 0x8, 0x10, 0x40
#: Tk on Windows reports Alt as this bit, not as Mod1 (which is Num Lock there).
_TK_WIN_ALT = 0x20000


def key_from_tk(keysym: str, char: str = "") -> int:
    """Return Qt's key code for a Tk key event.

    Parameters
    ----------
    keysym : str
        ``event.keysym``, e.g. ``"Left"``, ``"o"``, ``"O"``, ``"5"``.
    char : str, optional
        ``event.char``, used for printable keys whose keysym is a name
        (``"comma"``, ``"space"``).

    Returns
    -------
    int
        The ``Qt.Key_*`` value, or ``0`` for a modifier alone or a key with
        no code (the caller still passes its text on).
    """
    keysym = str(keysym)
    if keysym in _MODIFIER_KEYSYMS:
        return 0
    code = _TK_KEYS.get(keysym)
    if code is not None:
        return code
    if len(keysym) == 1:
        return ord(keysym.upper())
    if keysym == "space":
        return ord(" ")
    if char and len(char) == 1 and char >= " " and char != "\x7f":
        return ord(char.upper())
    return 0


def modifiers_from_tk(state: int, platform: str | None = None) -> int:
    """Pack Tk's ``event.state`` into an :mod:`emtk.events` modifier mask.

    Parameters
    ----------
    state : int
        ``event.state``.
    platform : str, optional
        ``sys.platform``; the bits mean different keys on each.

    Returns
    -------
    int
        ``*_MODIFIER`` bits, with Qt's macOS convention: Command is
        ``CONTROL_MODIFIER`` and Control is ``META_MODIFIER``.
    """
    platform = sys.platform if platform is None else platform
    state = int(state)
    mask = SHIFT_MODIFIER if state & _TK_SHIFT else 0
    if platform == "darwin":
        if state & _TK_MOD1:
            mask |= CONTROL_MODIFIER      # Command
        if state & _TK_CONTROL:
            mask |= META_MODIFIER         # Control
        if state & _TK_MOD2:
            mask |= ALT_MODIFIER          # Option
    elif platform == "win32":
        if state & _TK_CONTROL:
            mask |= CONTROL_MODIFIER
        if state & _TK_WIN_ALT:
            mask |= ALT_MODIFIER
    else:
        if state & _TK_CONTROL:
            mask |= CONTROL_MODIFIER
        if state & _TK_MOD1:
            mask |= ALT_MODIFIER
        if state & _TK_MOD4:
            mask |= META_MODIFIER
    return mask


def qt_application_exists() -> bool:
    """Whether this process already has a ``QApplication``.

    On macOS, Tk and Qt each take the process's one ``NSApplication``; a Tk
    root created after Qt has done so aborts the interpreter -- not an
    exception, the process dies. So a process hosts one toolkit or the other,
    and :class:`TkHost` asks this first.
    """
    for binding in ("PyQt5", "PyQt6", "PySide2", "PySide6"):
        widgets = sys.modules.get(binding + ".QtWidgets")
        if widgets is not None and widgets.QApplication.instance() is not None:
            return True
    return False


def _typed(char: str) -> str:
    """The text a key typed: printable characters only (Tk sends control codes too)."""
    return "".join(c for c in (char or "") if c >= " " and c != "\x7f")


class TkHost:
    """A top-level window that draws one control and drives it.

    Parameters
    ----------
    control : object
        Anything with ``draw(painter, x, y, w, h)``. ``press``, ``drag``,
        ``release``, ``hover``, ``key`` and ``scroll`` are used when present,
        with :mod:`.qt_host`'s signatures.
    title : str, optional
        Window title.
    size : tuple of int, optional
        Initial ``(width, height)``.
    background : tuple, optional
        Filled before the control draws.
    interval_ms : int, optional
        Repaint period. The control is immediate-mode and may change without
        input (a worker thread reporting, a caret blinking), so the host
        repaints on a timer as well as after every event.
    on_close : callable, optional
        Called once when the window closes, before Tk is torn down.
    root : tkinter.Tk, optional
        Use this root instead of creating one (tests share one).
    font_pt : float, optional
        Point size of the interface font, as every other host takes it.

        The window is in logical pixels and the frame is drawn at one pixel
        per logical pixel: Tk shows a photo image a pixel per point, so on a
        2x display the frame is the right size and softer, never twice the
        size.

    Notes
    -----
    Call :meth:`run` to enter the event loop, :meth:`close` to leave it.
    """

    def __init__(self, control, title: str = "emtk", size: tuple = (800, 600),
                 background: tuple = (30, 32, 38, 255), interval_ms: int = 50,
                 on_close: Callable[[], None] | None = None, root=None,
                 font_pt: float | None = None) -> None:
        if root is None and qt_application_exists():
            raise RuntimeError(
                "a QApplication already runs in this process; a Tk window beside it "
                "aborts the interpreter on macOS. Host the control with emtk.qt_host instead.")
        import tkinter as tk  # noqa: PLC0415

        self._tk = tk
        self.control = control
        self.background = tuple(background)
        from .font import DEFAULT_FONT_PT  # noqa: PLC0415

        self.font_pt = float(DEFAULT_FONT_PT if font_pt is None else font_pt)
        self.interval_ms = int(interval_ms)
        self.on_close = on_close
        self.root = root if root is not None else tk.Tk()
        self.root.title(title)
        self.root.geometry("%dx%d" % (int(size[0]), int(size[1])))
        self.root.configure(background="#%02x%02x%02x" % self.background[:3])
        self.canvas = tk.Canvas(self.root, highlightthickness=0, borderwidth=0,
                                background="#%02x%02x%02x" % self.background[:3],
                                width=int(size[0]), height=int(size[1]))
        self.canvas.pack(fill="both", expand=True)
        self._size = (int(size[0]), int(size[1]))
        self._frame = None       # the PIL frame, reused between paints
        self._photo = None       # the Tk image it is pasted into
        self._item = None
        self._pressed = False
        self._scheduled = None   # a pending "paint soon" after an event
        self._timer = None
        self._closed = False
        self.frames = 0
        self._bind()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if sys.platform == "darwin":
            # Cmd+Q and the application menu's Quit would otherwise exit the
            # Tcl interpreter directly, skipping on_close and any cleanup.
            self.root.createcommand("tk::mac::Quit", self.close)

    # -- window ----------------------------------------------------------- #
    def set_icon(self, path) -> None:
        """Use the image at *path* as the window (and dock/taskbar) icon."""
        from PIL import Image, ImageTk  # noqa: PLC0415

        with Image.open(path) as img:
            self._icon = ImageTk.PhotoImage(img.convert("RGBA"), master=self.root)
        self.root.iconphoto(True, self._icon)

    def clipboard_get(self) -> str:
        """The clipboard's text, or ``""`` when it holds none."""
        try:
            return self.root.clipboard_get()
        except self._tk.TclError:
            return ""

    def clipboard_set(self, text: str) -> None:
        """Replace the clipboard's contents with *text*."""
        self.root.clipboard_clear()
        self.root.clipboard_append(str(text))

    def run(self) -> int:
        """Show the window and process events until it closes. Returns ``0``."""
        self.paint()
        self._tick()
        self.root.mainloop()
        return 0

    def close(self) -> None:
        """Close the window and leave :meth:`run`. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        for pending in (self._timer, self._scheduled):
            if pending is not None:
                try:
                    self.root.after_cancel(pending)
                except self._tk.TclError:
                    pass
        if self.on_close is not None:
            self.on_close()
        try:
            self.root.quit()
            self.root.destroy()
        except self._tk.TclError:
            pass

    # -- painting --------------------------------------------------------- #
    def paint(self):
        """Draw the control into the frame and present it. Returns the frame."""
        if self._closed:
            return self._frame
        from PIL import ImageTk  # noqa: PLC0415

        from .pil_painter import PilPainter  # noqa: PLC0415

        w, h = self._size
        painter = PilPainter(w, h, background=self.background, frame=self._frame,
                             scale=self._font_scale())
        self.control.draw(painter, 0.0, 0.0, float(w), float(h))
        frame = painter.frame
        if self._photo is None or frame is not self._frame:
            self._photo = ImageTk.PhotoImage(frame, master=self.root)
            if self._item is None:
                self._item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
            else:
                self.canvas.itemconfigure(self._item, image=self._photo)
        else:
            self._photo.paste(frame)
        self._frame = frame
        self.frames += 1
        from .app import window_title  # noqa: PLC0415

        title = window_title(self.control)
        if title is not None and title != self.root.title():
            self.root.title(title)
        return frame

    def _font_scale(self) -> float:
        """:attr:`font_pt` as a multiple of the baked atlas, as the GPU hosts take it."""
        from .font import load_atlas  # noqa: PLC0415

        baked = float(load_atlas().font_pt)
        return self.font_pt / baked if baked else 1.0

    def grab(self):
        """The last presented frame as a :class:`PIL.Image.Image` copy."""
        return None if self._frame is None else self._frame.copy()

    def _tick(self) -> None:
        if self._closed:
            return
        self.paint()
        self._timer = self.root.after(self.interval_ms, self._tick)

    def _soon(self) -> None:
        """Paint once the pending events are processed (coalesces a burst)."""
        if self._scheduled is None and not self._closed:
            self._scheduled = self.root.after_idle(self._paint_scheduled)

    def _paint_scheduled(self) -> None:
        self._scheduled = None
        self.paint()

    # -- input ------------------------------------------------------------ #
    def _bind(self) -> None:
        c = self.canvas
        c.bind("<Configure>", self._on_configure)
        c.bind("<ButtonPress-1>", lambda e: self._on_press(e, 1))
        c.bind("<Double-Button-1>", lambda e: self._on_press(e, 2))
        c.bind("<B1-Motion>", self._on_motion)
        c.bind("<Motion>", self._on_motion)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Button-4>", lambda e: self._scroll(-3))   # X11 wheel up
        c.bind("<Button-5>", lambda e: self._scroll(3))    # X11 wheel down
        self.root.bind("<KeyPress>", self._on_key)
        c.focus_set()

    def _box(self):
        return (0.0, 0.0, float(self._size[0]), float(self._size[1]))

    def _on_configure(self, event) -> None:
        size = (max(1, int(event.width)), max(1, int(event.height)))
        if size != self._size:
            self._size = size
            self._soon()

    def _on_press(self, event, clicks: int) -> None:
        self.canvas.focus_set()
        press = getattr(self.control, "press", None)
        if callable(press):
            press(float(event.x), float(event.y), *self._box(),
                  modifiers_from_tk(event.state), clicks)
        self._pressed = True
        self._soon()

    def _on_motion(self, event) -> None:
        px, py = float(event.x), float(event.y)
        name = "drag" if self._pressed else "hover"
        handler = getattr(self.control, name, None)
        if callable(handler):
            handler(px, py, *self._box())
            self._soon()

    def _on_release(self, _event) -> None:
        self._pressed = False
        release = getattr(self.control, "release", None)
        if callable(release):
            release()
        self._soon()

    def _on_wheel(self, event) -> None:
        if event.delta:
            self._scroll(-3 if event.delta > 0 else 3)

    def _scroll(self, rows: int) -> None:
        scroll = getattr(self.control, "scroll", None)
        if callable(scroll):
            scroll(rows)
            self._soon()

    def _on_key(self, event) -> None:
        handler = getattr(self.control, "key", None)
        if not callable(handler):
            return
        code = key_from_tk(event.keysym, event.char)
        text = _typed(event.char)
        if not code and not text:
            return
        handler(code, text, modifiers_from_tk(event.state))
        self._soon()
