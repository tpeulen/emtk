"""The tkinter host: Qt's key vocabulary, and a real Tk window that presents frames.

The translation tests need no Tk at all. The window tests build a real ``Tk``
root, withdrawn -- presenting a frame does not need the window on screen, and
a test that pops windows is one nobody runs twice -- and skip where there is
no Tk or no display.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from emtk import keys
from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from emtk.tk_host import key_from_tk, modifiers_from_tk, qt_application_exists


@pytest.mark.parametrize("keysym, char, code", [
    ("Return", "\r", keys.KEY_RETURN),
    ("KP_Enter", "\r", keys.KEY_ENTER),
    ("Escape", "\x1b", keys.KEY_ESCAPE),
    ("BackSpace", "\x08", keys.KEY_BACKSPACE),
    ("Delete", "\x7f", keys.KEY_DELETE),
    ("Left", "", keys.KEY_LEFT),
    ("Prior", "", keys.KEY_PAGE_UP),
    ("F2", "", keys.KEY_F2),
    ("F12", "", keys.KEY_F12),
    ("ISO_Left_Tab", "", keys.KEY_TAB),
    # Qt reports a letter key as its *uppercase* ordinal whatever Shift says,
    # and controls written against the Qt host test for exactly that
    ("o", "o", ord("O")),
    ("O", "O", ord("O")),
    ("5", "5", ord("5")),
    ("space", " ", ord(" ")),
    ("comma", ",", ord(",")),
    ("Shift_L", "", 0),
    ("Meta_L", "", 0),
])
def test_keys_are_qt_codes(keysym, char, code):
    assert key_from_tk(keysym, char) == code


def test_command_is_control_on_macos_as_in_qt():
    assert modifiers_from_tk(0x8, "darwin") == CONTROL_MODIFIER        # Command
    assert modifiers_from_tk(0x4, "darwin") == META_MODIFIER           # Control
    assert modifiers_from_tk(0x10 | 0x1, "darwin") == ALT_MODIFIER | SHIFT_MODIFIER


def test_windows_alt_is_its_own_bit():
    assert modifiers_from_tk(0x4, "win32") == CONTROL_MODIFIER
    assert modifiers_from_tk(0x20000, "win32") == ALT_MODIFIER
    assert modifiers_from_tk(0x8, "win32") == 0                        # Num Lock, not a modifier


def test_x11():
    assert modifiers_from_tk(0x4 | 0x8, "linux") == CONTROL_MODIFIER | ALT_MODIFIER
    assert modifiers_from_tk(0x40, "linux") == META_MODIFIER


class Recorder:
    """A control that draws a marker and records what the host sent it."""

    def __init__(self):
        self.calls = []

    def draw(self, painter, x, y, w, h):
        painter.fill_rect(x, y, w, h, (10, 20, 30, 255))
        painter.fill_rect(5, 5, 20, 10, (250, 120, 0, 255))
        painter.text(30, 2, 100, 16, 0, "hello", (255, 255, 255, 255))

    def press(self, *args):
        self.calls.append(("press",) + args)

    def drag(self, *args):
        self.calls.append(("drag",) + args[:2])

    def hover(self, *args):
        self.calls.append(("hover",) + args[:2])

    def release(self):
        self.calls.append(("release",))

    def scroll(self, rows):
        self.calls.append(("scroll", rows))

    def key(self, code, text, modifiers):
        self.calls.append(("key", code, text, modifiers))
        return True


@pytest.fixture
def host():
    pytest.importorskip("PIL.ImageTk", reason="the Tk host presents through Pillow's ImageTk")
    tk = pytest.importorskip("tkinter")
    if qt_application_exists():
        # on macOS a Tk root beside Qt aborts the whole session, not just this test
        pytest.skip("a QApplication already owns this process; Tk cannot share it "
                    "(run tests/test_tk_host.py on its own)")
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip("no display for Tk: %s" % e)
    root.withdraw()
    from emtk.tk_host import TkHost

    closed = []
    h = TkHost(Recorder(), size=(160, 40), root=root, on_close=lambda: closed.append(True))
    h.closed = closed
    try:
        yield h
    finally:
        h.close()


def test_a_painted_frame_is_presented(host):
    frame = host.paint()
    assert frame.size == (160, 40)
    assert frame.getpixel((10, 10)) == (250, 120, 0)
    assert frame.getpixel((150, 35)) == (10, 20, 30)
    assert host.frames == 1
    again = host.paint()
    assert again is frame, "same size: the frame is repainted in place"
    assert host.grab() is not frame and host.grab().getpixel((10, 10)) == (250, 120, 0)


def test_events_reach_the_control_translated(host):
    rec = host.control
    ev = SimpleNamespace(x=12, y=7, state=0x1, keysym="a", char="A", delta=120,
                         width=160, height=40)
    host._on_press(ev, 1)
    host._on_motion(ev)
    host._on_release(ev)
    host._on_motion(ev)
    host._on_wheel(ev)
    host._on_key(ev)
    host._on_key(SimpleNamespace(keysym="Shift_L", char="", state=0))   # a modifier alone: nothing
    names = [c[0] for c in rec.calls]
    assert names == ["press", "drag", "release", "hover", "scroll", "key"]
    assert rec.calls[0] == ("press", 12.0, 7.0, 0.0, 0.0, 160.0, 40.0, SHIFT_MODIFIER, 1)
    assert rec.calls[4] == ("scroll", -3)
    assert rec.calls[5] == ("key", ord("A"), "A", SHIFT_MODIFIER)


def test_a_resize_repaints_at_the_new_size(host):
    host._on_configure(SimpleNamespace(width=200, height=60))
    host.root.update()
    assert host.grab().size == (200, 60)


def test_clipboard_round_trips(host):
    host.clipboard_set("P21 sample 7")
    assert host.clipboard_get() == "P21 sample 7"


def test_close_runs_on_close_once(host):
    host.close()
    host.close()
    assert host.closed == [True]


def test_the_window_takes_the_controls_title(host):
    host.control.window_title = "ndX -- m000.bur"
    host.paint()
    assert host.root.title() == "ndX -- m000.bur"
