"""Composed text input (:mod:`emtk.ime`): dead keys, accented characters and input methods.

Three halves, pinned separately:

* **commit** -- what an input method finishes arrives as typed text: through glfw's
  ``char`` event (one code point each), Qt's commit string, or :meth:`Driver.commit`;
  it must type in every text widget, including the format characters (zero-width
  joiner, non-joiner) that ``str.isprintable`` rejects;
* **composition** -- while the OS composes, the keys are its: the native host holds
  back the Return that confirms a conversion and the Backspace that edits it;
* **preedit** -- the provisional text is drawn at the caret of the focused field,
  underlined, and never becomes part of the value until it is committed.
"""
from __future__ import annotations

import sys

import pytest

from emtk import im
from emtk.app import ImApp
from emtk.ime import MarkedTextProbe, Preedit, committed_text, splice
from emtk.keys import KEY_BACKSPACE, KEY_RETURN
from emtk.native import CanvasEvents
from emtk.testing import Driver
from emtk.widgets.text_editor import TextEditor
from emtk.widgets.text_field import TextField, paint


# --------------------------------------------------------------- the pieces
def test_committed_text_keeps_format_characters_and_drops_controls():
    assert committed_text("é") == "é"
    assert committed_text("日本") == "日本"
    # An emoji ZWJ sequence and Persian's zero-width non-joiner type whole.
    assert committed_text("👩‍💻") == "👩‍💻"
    assert committed_text("می‌خواهم") == "می‌خواهم"
    # A variation selector (text vs emoji presentation) is kept.
    assert committed_text("❤️") == "❤️"
    # Return, Tab, Escape and DEL as characters are the key events' business.
    assert committed_text("\r\t\x1b\x7f") == ""
    assert committed_text(None) == ""


def test_splice_inserts_the_preedit_at_the_caret():
    assert splice("ab", 1, "にほ") == ("aにほb", 1, 3)
    assert splice("ab", 9, "x") == ("abx", 2, 3)
    assert splice("ab", 1, "") == ("ab", 1, 1)
    assert Preedit() == ("", 0)


# --------------------------------------------------------------- native host
class _Canvas:
    def __init__(self):
        self.handlers: dict[str, list] = {}

    def add_event_handler(self, callback, *event_types):
        for name in event_types:
            self.handlers.setdefault(name, []).append(callback)

    def emit(self, name, event=None):
        for callback in self.handlers.get(name, ()):
            callback({**(event or {}), "event_type": name})


def _glfw_canvas():
    # The backend is read from the class's module: this one has a ``char`` event.
    return type("_C", (_Canvas,), {"__module__": "rendercanvas.glfw"})()


class _Sink:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if not name.startswith("on_"):
            raise AttributeError(name)
        return lambda *args: self.calls.append((name, args)) or True

    def presses(self):
        return [args for name, args in self.calls if name == "on_key_press"]

    def releases(self):
        return [args for name, args in self.calls if name == "on_key_release"]


class _Probe:
    """Stands in for the OS: composing while ``active``."""

    def __init__(self):
        self.active = False

    def composing(self):
        return self.active


class _Loop:
    def call_later(self, *_args):
        pass


def _host():
    canvas, sink, probe = _glfw_canvas(), _Sink(), _Probe()
    CanvasEvents(canvas, sink, loop=_Loop(), input_method=probe)
    return canvas, sink, probe


def test_committed_cjk_and_accents_arrive_as_typed_text():
    canvas, sink, _probe = _host()
    for ch in "日本é":                 # glfw's char callback: one code point each
        canvas.emit("char", {"data": ch, "modifiers": ()})
    for ch in "👩‍💻":
        canvas.emit("char", {"data": ch, "modifiers": ()})
    assert "".join(args[1] for args in sink.presses()) == "日本é👩‍💻"


def test_keys_go_to_the_input_method_while_it_composes():
    canvas, sink, probe = _host()
    # Typing "nihon" into a Japanese IME: the first key starts the composition.
    canvas.emit("key_down", {"key": "n", "modifiers": ()})
    canvas.emit("key_up", {"key": "n", "modifiers": ()})
    probe.active = True
    # Backspace edits the composition, Return confirms it: neither is the app's.
    for name in ("Backspace", "Enter"):
        canvas.emit("key_down", {"key": name, "modifiers": ()})
        if name == "Enter":
            probe.active = False                       # the conversion is committed...
            canvas.emit("char", {"data": "日", "modifiers": ()})
            canvas.emit("char", {"data": "本", "modifiers": ()})
        canvas.emit("key_up", {"key": name, "modifiers": ()})
    keys = [args[0] for args in sink.presses()]
    assert KEY_BACKSPACE not in keys and KEY_RETURN not in keys
    assert not [args for args in sink.releases() if args[0] in (KEY_BACKSPACE, KEY_RETURN)], (
        "a release whose press went to the input method must not reach the app either")
    assert "".join(args[1] for args in sink.presses()) == "日本"
    # ...and once it is, Return is the app's again.
    canvas.emit("key_down", {"key": "Enter", "modifiers": ()})
    assert sink.presses()[-1][0] == KEY_RETURN


def test_a_dead_key_types_the_composed_character_only():
    canvas, sink, probe = _host()
    canvas.emit("key_down", {"key": "e", "modifiers": ("Alt",)})   # Option+E: the accent
    probe.active = True                                            # ´ is marked text now
    canvas.emit("key_up", {"key": "e", "modifiers": ()})
    canvas.emit("key_down", {"key": "e", "modifiers": ()})
    probe.active = False
    canvas.emit("char", {"data": "é", "modifiers": ()})
    canvas.emit("key_up", {"key": "e", "modifiers": ()})
    assert "".join(args[1] for args in sink.presses()) == "é"


@pytest.mark.skipif(sys.platform != "darwin", reason="the marked-text probe is Cocoa's")
def test_the_cocoa_probe_reads_a_real_views_marked_text():
    glfw = pytest.importorskip("glfw")
    if not glfw.init():
        pytest.skip("no window system")
    glfw.window_hint(glfw.VISIBLE, False)
    window = glfw.create_window(64, 64, "ime", None, None)
    if not window:
        glfw.terminate()
        pytest.skip("no window")
    try:
        probe = MarkedTextProbe.for_glfw_window(window)
        assert probe is not None, "GLFW's view answers hasMarkedText"
        assert probe.composing() is False
        _set_marked_text(probe._view, "に")             # what AppKit does for an IME key
        assert probe.composing() is True
        _send(probe._view, b"unmarkText")
        assert probe.composing() is False
    finally:
        glfw.destroy_window(window)
        glfw.terminate()


def _send(obj, selector):
    import ctypes

    from emtk.ime import _objc_function, _selector

    _objc_function("id")(obj, _selector(selector))
    return ctypes


def _set_marked_text(view, text):
    """``[view setMarkedText:text selectedRange:{len,0} replacementRange:{NSNotFound,0}]``."""
    import ctypes

    from emtk.ime import _runtime, _selector

    class NSRange(ctypes.Structure):
        _fields_ = [("location", ctypes.c_ulong), ("length", ctypes.c_ulong)]

    lib = _runtime()
    lib.objc_getClass.restype = ctypes.c_void_p
    lib.objc_getClass.argtypes = [ctypes.c_char_p]
    address = ctypes.cast(lib.objc_msgSend, ctypes.c_void_p).value
    make = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_char_p)(address)
    string = make(lib.objc_getClass(b"NSString"), _selector(b"stringWithUTF8String:"),
                  text.encode("utf-8"))
    mark = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            NSRange, NSRange)(address)
    mark(view, _selector(b"setMarkedText:selectedRange:replacementRange:"), string,
         NSRange(len(text), 0), NSRange(sys.maxsize * 2 + 1, 0))


# --------------------------------------------------------------- widgets
def _field_app(state):
    def gui():
        im.set_next_window_pos((0.0, 0.0))
        im.set_next_window_size((400.0, 200.0))
        if im.begin("w"):
            _changed, state["value"] = im.input_text("##name", state["value"])
            state["rect"] = im.get_item_rect()
        im.end()
    return ImApp(gui)


def _texts(painter):
    return [entry[5] for entry in painter.texts]


def test_input_text_draws_the_preedit_and_types_only_the_commit():
    state = {"value": "a"}
    driver = Driver(_field_app(state), size=(420, 220))
    driver.frame(2)
    driver.click(state["rect"])
    driver.compose("にほん", 2)
    assert state["value"] == "a", "a composition is not typed"
    assert any("aにほん" in text for text in _texts(driver.painter)), _texts(driver.painter)
    caret = driver.app.io.ime_caret
    assert caret is not None and state["rect"][0] < caret[0] < state["rect"][0] + 200
    driver.commit("日本")
    assert state["value"] == "a日本"
    assert driver.app.io.preedit == ""
    assert not any("にほん" in text for text in _texts(driver.painter))


def test_input_text_dead_key_then_letter():
    state = {"value": "caf"}
    driver = Driver(_field_app(state), size=(420, 220))
    driver.frame(2)
    driver.click(state["rect"])
    driver.compose("´")
    assert state["value"] == "caf"
    driver.commit("é")
    assert state["value"] == "café"


def test_an_unfocused_field_does_not_draw_the_preedit():
    state = {"value": "x"}
    driver = Driver(_field_app(state), size=(420, 220))
    driver.frame(2)
    driver.compose("にほん")
    assert not any("にほん" in text for text in _texts(driver.painter))


def test_text_editor_composes_at_the_caret_and_commits():
    editor = TextEditor("print()")
    editor.config.show_line_numbers = False
    state = {}

    def gui():
        im.set_next_window_pos((0.0, 0.0))
        im.set_next_window_size((500.0, 300.0))
        if im.begin("e"):
            im.text_editor("##code", editor, (480.0, 200.0))
            state["rect"] = im.get_item_rect()
        im.end()

    driver = Driver(ImApp(gui), size=(520, 320))
    driver.frame(2)
    driver.click(state["rect"])
    from emtk.widgets.text_editor import Pos

    editor.set_cursor(Pos(0, 6))
    driver.compose("にほん")
    assert editor.preedit == "にほん" and editor.text == "print()"
    assert "にほん" in _texts(driver.painter)
    assert driver.app.io.ime_caret is not None
    driver.commit("日本")
    assert editor.text == "print(日本)" and editor.preedit == ""


def test_a_read_only_editor_takes_no_composition():
    editor = TextEditor("log", read_only=True)
    editor.compose("x")
    assert editor.preedit == ""


def test_text_field_paint_draws_the_preedit_and_keeps_the_fields_positions():
    from emtk.testing import MetricPainter

    field = TextField()
    field.set_text("ab")
    field.move(1)
    field.compose("çd", 1)
    painter = MetricPainter()
    xs = paint(painter, field, 0, 0, 200, 20, (255, 255, 255), caret_colour=(255, 255, 255))
    assert len(xs) == 3, "one position per caret place of the field's own text"
    assert "açdb" in _texts(painter)
    field.compose("")
    field.key(0, "ç", 0)
    assert field.text == "açb"


# --------------------------------------------------------------- Qt host
def test_qt_host_routes_the_input_method_to_the_control(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("qtpy")
    from qtpy import QtCore, QtGui, QtWidgets

    from emtk.qt_host import ControlHost

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state = {"value": ""}
    control = _field_app(state)
    host = ControlHost(control)
    host.resize(420, 220)
    assert host.testAttribute(QtCore.Qt.WA_InputMethodEnabled)
    assert host.inputMethodQuery(QtCore.Qt.ImEnabled) is True
    host.grab()
    # Focus the field the way a click does.
    control.pointer_press(*_centre(state), 1, 0)
    control.pointer_release(*_centre(state), 1, 0)
    host.grab()
    attrs = [QtGui.QInputMethodEvent.Attribute(QtGui.QInputMethodEvent.Cursor, 2, 1, None)]
    QtWidgets.QApplication.sendEvent(host, QtGui.QInputMethodEvent("にほ", attrs))
    assert control.io.preedit == "にほ" and control.io.preedit_cursor == 2
    host.grab()
    assert host.inputMethodQuery(QtCore.Qt.ImCursorRectangle).isValid()
    event = QtGui.QInputMethodEvent("", [])
    event.setCommitString("日本")
    QtWidgets.QApplication.sendEvent(host, event)
    host.grab()
    assert control.io.preedit == ""
    assert state["value"] == "日本"
    host.close()
    del app


def _centre(state):
    x, y, w, h = state["rect"]
    return x + w / 2, y + h / 2
