"""emtk.dialog_window: a titled, movable, closable window over an app."""
from __future__ import annotations

import emtk
from emtk.dialog_window import DialogWindow
from emtk.keys import KEY_ESCAPE
from emtk.testing import RecordingPainter

FRAME = (0.0, 0.0, 800.0, 600.0)


class Host:
    def __init__(self, window):
        self.window = window
        self.io, self.storage = emtk.IO(), {}
        self.pressed = []
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, FRAME, io=self.io, storage=self.storage):
            got = self.window.begin(FRAME, buttons=("Help",))
            emtk.text("content")
            self.window.end()
        self.pressed.append(got)
        self.io.mouse_clicked[0] = False
        self.io.mouse_released[0] = False
        self.io.key = 0
        return got

    def press(self, x, y):
        self.io.mouse_pos = self.io.mouse_clicked_pos[0] = (x, y)
        self.io.mouse_down[0] = self.io.mouse_clicked[0] = True
        self.frame()

    def release(self):
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True
        return self.frame()


def test_centred_with_title_content_and_header_buttons():
    host = Host(DialogWindow("GMM Settings", size=(400, 300)))
    host.frame()
    assert host.window.box == (200.0, 150.0, 400.0, 300.0)
    for text in ("GMM Settings", "content", "Help", "×"):
        assert text in host.painter.strings, text
    cx, cy, cw, ch = host.window.content_box
    assert cy > 150.0 + DialogWindow.HEADER_H - 1 and cx > 200.0


def test_dragging_the_header_moves_it_and_it_stays_on_screen():
    host = Host(DialogWindow("Tool", size=(300, 200)))
    host.frame()
    x, y, _w, _h = host.window.box
    host.press(x + 40, y + 10)
    host.io.mouse_pos = (x + 140, y + 60)
    host.frame()
    host.release()
    assert host.window.box[:2] == (x + 100, y + 50)
    host.window.pos = (5000.0, 5000.0)
    host.frame()
    bx, by, _, _ = host.window.box
    assert bx < 800 and by < 600


def test_close_button_and_escape_say_close():
    window = DialogWindow("Tool", size=(300, 200))
    host = Host(window)
    host.frame()
    x, y, w, _h = window.box
    # ✕ is the right-most header button
    host.io.mouse_pos = (x + w - 12, y + 12)
    host.frame()
    host.press(x + w - 12, y + 12)
    assert host.release() == "close"
    host.io.mouse_pos = (x + 50, y + 100)
    host.io.key = KEY_ESCAPE
    assert host.frame() == "close"


def test_show_hide_toggle():
    window = DialogWindow("Tool")
    assert not window.open
    window.toggle()
    assert window.open
    window.hide()
    assert not window.open


def test_fit_height_sizes_the_window_to_its_content():
    """A window told to fit shrinks to what it drew, and grows when more is drawn."""
    lines = {"n": 2}

    class Fitting(Host):
        def frame(self):
            self.painter = RecordingPainter()
            with emtk.frame(self.painter, FRAME, io=self.io, storage=self.storage):
                self.window.begin(FRAME)
                for i in range(lines["n"]):
                    emtk.text(f"line {i}")
                self.window.end()

    host = Fitting(DialogWindow("Fit", size=(400, 500), fit_height=True))
    host.frame()
    host.frame()
    short = host.window.size[1]
    assert short < 150.0, short
    _, cy, _, ch = host.window.content_box
    lines["n"] = 12
    host.frame()
    host.frame()
    assert host.window.size[1] > short + 100.0
    fixed = Fitting(DialogWindow("Fixed", size=(400, 500)))
    fixed.frame()
    fixed.frame()
    assert fixed.window.size[1] == 500.0
