"""The desktop host's event translation: rendercanvas events in, emtk events out.

:class:`emtk.native.CanvasEvents` is what every toolkit-free emtk window --
and chimol's viewport -- hears the canvas through, so its rules are pinned
here once, against a stand-in canvas that records handlers and emits events
the way rendercanvas does.

Typing respects the system keyboard layout
------------------------------------------
glfw's key event carries **its own keycode**, a US-QWERTY position, and
rendercanvas turns it into a name with ``chr(key)`` -- its own source says
shift+5 reports ``"5"``, not ``"%"``. Taking text from that typed US letters on
a German keyboard (the physical Z key produced ``y``) and got every shifted
symbol wrong. So where a backend offers a ``char`` event -- what the operating
system actually produced -- a key event contributes **no** text; ``key_down``
supplies only the keys that act (Return, arrows, Escape).
"""
from __future__ import annotations

import pathlib

import pytest

from emtk.events import (
    CONTROL_MODIFIER,
    LEFT_BUTTON,
    MIDDLE_BUTTON,
    RIGHT_BUTTON,
    SHIFT_MODIFIER,
)
from emtk.keys import KEY_BACKSPACE, KEY_LEFT, KEY_RETURN
from emtk.native import (
    CHAR_BACKENDS,
    SHIFT_MAP,
    CanvasEvents,
    canvas_module,
    event_types,
    wheel_steps,
)


class _Canvas:
    """A canvas that records handlers and reports the backend we want."""

    def __init__(self, module: str = "rendercanvas.offscreen", size=(200, 100), ratio=2.0):
        self.handlers: dict[str, list] = {}
        self._size, self._ratio = size, ratio
        type(self).__module__ = module

    def add_event_handler(self, callback, *event_types):
        for name in event_types:
            self.handlers.setdefault(name, []).append(callback)

    def emit(self, name: str, event: dict | None = None):
        for callback in self.handlers.get(name, ()):
            callback({**(event or {}), "event_type": name})

    def get_physical_size(self):
        return self._size

    def get_pixel_ratio(self):
        return self._ratio


def _canvas(module: str = "rendercanvas.offscreen", **kw):
    # A class per call: `__module__` is a class attribute, and the backend is
    # read from it.
    return type("_C", (_Canvas,), {})(module, **kw)


class _Sink:
    """Records every call, answering that a frame is due."""

    def __init__(self):
        self.calls: list = []

    def __getattr__(self, name):
        if not name.startswith("on_"):
            raise AttributeError(name)

        def handler(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return True

        return handler

    def typed(self) -> str:
        return "".join(args[1] for name, args, _ in self.calls if name == "on_key_press")


class _Loop:
    """Collects ``call_later`` callbacks so a test can fire them by hand."""

    def __init__(self):
        self.pending: list = []

    def call_later(self, delay, callback, *args):
        self.pending.append((delay, callback, args))

    def fire(self):
        pending, self.pending = self.pending, []
        for _delay, callback, args in pending:
            callback(*args)


def _events(module="rendercanvas.glfw", **kw):
    canvas, sink, loop = _canvas(module), _Sink(), _Loop()
    return CanvasEvents(canvas, sink, loop=loop, **kw), canvas, sink, loop


# --------------------------------------------------------------- layouts
#: (what glfw reports as the key, what the OS produced) on a German layout.
GERMAN = [
    ("y", "z", "the Z key: US position Y"),
    ("z", "y", "the Y key: US position Z"),
    ("7", "/", "shift+7 is / on German and & on US"),
    ("'", "ä", "an umlaut, which has no US keycode at all"),
    ("-", "ß", "eszett"),
]


@pytest.mark.parametrize("reported, produced, why", GERMAN, ids=[c[2] for c in GERMAN])
def test_the_character_the_os_produced_is_what_gets_typed(reported, produced, why):
    _ev, canvas, sink, _loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": reported, "modifiers": ()})
    canvas.emit("char", {"data": produced, "modifiers": ()})
    assert sink.typed() == produced, f"{why}: typed {sink.typed()!r}"


def test_a_key_event_contributes_no_text_on_a_char_backend():
    _ev, canvas, sink, _loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": "y", "modifiers": ()})
    assert sink.typed() == "", "the char event is the only text source"


def test_shift_is_not_applied_twice():
    _ev, canvas, sink, _loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": "7", "modifiers": ("Shift",)})
    canvas.emit("char", {"data": "/", "modifiers": ("Shift",)})
    assert sink.typed() == "/"


def test_a_backend_without_char_events_still_types_with_shift_applied():
    """No ``char`` event (the offscreen canvas, a browser-like backend): the
    key's own name is the text, shifted through the US map.
    """
    events, canvas, sink, _loop = _events("rendercanvas.offscreen")
    assert not events.typed_via_char
    canvas.emit("key_down", {"key": "z", "modifiers": ()})
    canvas.emit("key_down", {"key": "z", "modifiers": ("Shift",)})
    canvas.emit("key_down", {"key": "-", "modifiers": ("Shift",)})
    assert sink.typed() == "zZ_"
    assert SHIFT_MAP["-"] == "_"


def test_a_control_character_is_not_typed():
    _ev, canvas, sink, _loop = _events("rendercanvas.glfw")
    canvas.emit("char", {"data": "\r", "modifiers": ()})
    canvas.emit("char", {"data": "\x00", "modifiers": ()})
    assert sink.calls == []


def test_keys_that_act_are_translated_and_carry_modifiers():
    _ev, canvas, sink, _loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": "ArrowLeft", "modifiers": ("Control", "Shift")})
    name, args, _ = sink.calls[0]
    assert name == "on_key_press"
    assert args == (KEY_LEFT, "", CONTROL_MODIFIER | SHIFT_MODIFIER)


def test_a_glfw_canvas_is_recognised_as_char_capable():
    assert "char" in event_types(_canvas("rendercanvas.glfw"))
    assert "char" not in event_types(_canvas("rendercanvas.offscreen"))


def test_the_backend_list_matches_what_the_backends_do():
    """:data:`CHAR_BACKENDS` against the installed backends' source."""
    rendercanvas = pytest.importorskip("rendercanvas")
    base = pathlib.Path(rendercanvas.__file__).parent
    emitting = set()
    for module in base.glob("*.py"):
        text = module.read_text(encoding="utf-8", errors="ignore")
        if "set_char_callback" in text or "_char_input_event(" in text:
            emitting.add(module.stem)
    assert emitting, "found no backend emitting char; has rendercanvas changed?"
    assert emitting == set(CHAR_BACKENDS), f"out of date: {emitting ^ set(CHAR_BACKENDS)}"


# --------------------------------------------------------------- repeat
def test_a_held_key_repeats_until_released():
    """rendercanvas' glfw backend drops ``REPEAT``; a held backspace deleted
    one character. The repeat is generated on the loop and stops on key-up.
    """
    _ev, canvas, sink, loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": "Backspace", "modifiers": ()})
    assert len(sink.calls) == 1 and loop.pending
    loop.fire()
    loop.fire()
    assert [a[0] for _n, a, _k in sink.calls] == [KEY_BACKSPACE] * 3
    canvas.emit("key_up", {"key": "Backspace"})
    loop.fire()
    assert len(sink.calls) == 3, "a released key kept repeating"
    assert not loop.pending


def test_return_does_not_repeat():
    _ev, canvas, sink, loop = _events("rendercanvas.glfw")
    canvas.emit("key_down", {"key": "Enter", "modifiers": ()})
    assert sink.calls[0][1][0] == KEY_RETURN
    assert not loop.pending


# --------------------------------------------------------------- pointer
def test_pointer_events_translate_buttons():
    _ev, canvas, sink, _loop = _events()
    canvas.emit("pointer_down", {"x": 3, "y": 4, "button": 2, "modifiers": ("Shift",)})
    canvas.emit("pointer_move", {"x": 5, "y": 6, "buttons": (1, 3), "modifiers": ()})
    canvas.emit("pointer_up", {"x": 5, "y": 6, "button": 3, "modifiers": ()})
    assert sink.calls == [
        ("on_pointer_press", (3.0, 4.0, RIGHT_BUTTON, SHIFT_MODIFIER), {}),
        ("on_pointer_move", (5.0, 6.0, LEFT_BUTTON | MIDDLE_BUTTON, 0), {}),
        ("on_pointer_release", (5.0, 6.0, MIDDLE_BUTTON, 0), {}),
    ]


def _click(canvas, x=3, y=4, button=1):
    canvas.emit("pointer_down", {"x": x, "y": y, "button": button, "modifiers": ()})
    canvas.emit("pointer_up", {"x": x, "y": y, "button": button, "modifiers": ()})


def test_the_second_press_of_a_double_click_says_double_and_is_released():
    """rendercanvas emits ``double_click`` after the second release. Passed on
    as a third press it left the button held with nothing to release it."""
    _ev, canvas, sink, _loop = _events()
    _click(canvas)
    _click(canvas)
    canvas.emit("double_click", {"x": 3, "y": 4, "button": 1, "modifiers": ()})
    presses = [(n, k) for n, _a, k in sink.calls if n == "on_pointer_press"]
    releases = [n for n, _a, _k in sink.calls if n == "on_pointer_release"]
    assert presses == [("on_pointer_press", {}), ("on_pointer_press", {"double": True})]
    assert len(releases) == 2, "every press is released: no button is left down"


def test_presses_apart_in_space_or_time_are_single():
    ev, canvas, sink, _loop = _events()
    _click(canvas, 3, 4)
    _click(canvas, 30, 40)
    ev._last_down = (ev._last_down[0] - 1.0,) + ev._last_down[1:]
    _click(canvas, 30, 40)
    assert all(k == {} for n, _a, k in sink.calls if n == "on_pointer_press")


@pytest.mark.parametrize("dy, steps", [(100, -1), (-100, 1), (250, -2), (3, -1), (-3, 1), (0, 0)])
def test_wheel_steps_are_positive_away_and_round_away_from_zero(dy, steps):
    """``dy`` is the DOM's (positive downwards); steps are positive away. A
    trackpad's small deltas round *away* from zero, or the gesture does nothing.
    """
    assert wheel_steps({"dy": dy}) == steps


def test_the_wheel_reaches_the_sink_with_its_position():
    _ev, canvas, sink, _loop = _events()
    canvas.emit("wheel", {"x": 10, "y": 20, "dy": -100, "modifiers": ("Control",)})
    canvas.emit("wheel", {"x": 10, "y": 20, "dy": 0, "modifiers": ()})
    assert sink.calls == [("on_wheel", (10.0, 20.0, 1, CONTROL_MODIFIER), {})]


def test_resize_reports_physical_size_and_ratio():
    _ev, canvas, sink, _loop = _events()
    canvas.emit("resize", {"width": 100, "height": 50})
    assert sink.calls == [("on_resize", (200, 100, 2.0), {})]


def test_on_frame_is_called_only_when_a_frame_is_due():
    frames = []
    canvas = _canvas()

    class _Quiet(_Sink):
        def on_pointer_move(self, *a):
            return False

    sink = _Quiet()
    CanvasEvents(canvas, sink, on_frame=lambda: frames.append(1), loop=_Loop())
    canvas.emit("pointer_move", {"x": 1, "y": 1, "buttons": (), "modifiers": ()})
    assert frames == []
    canvas.emit("pointer_down", {"x": 1, "y": 1, "button": 1, "modifiers": ()})
    assert frames == [1]


def test_an_offscreen_canvas_takes_no_drops():
    events, _canvas_, _sink, _loop = _events("rendercanvas.offscreen")
    assert events.supports_file_drop is False


def test_a_named_backend_is_imported_as_asked(monkeypatch):
    pytest.importorskip("rendercanvas")
    monkeypatch.setenv("EMTK_CANVAS", "offscreen")
    assert canvas_module().__name__ == "rendercanvas.offscreen"
    monkeypatch.delenv("EMTK_CANVAS")
    monkeypatch.setenv("MYAPP_CANVAS", "offscreen")
    assert canvas_module(env="MYAPP_CANVAS").__name__ == "rendercanvas.offscreen"
    with pytest.raises(ImportError):
        canvas_module("no_such_backend")


def test_a_click_lands_where_the_pointer_is_not_where_it_last_moved(monkeypatch):
    """A window moved under a still pointer (Magnet, tiling) gets no move;
    rendercanvas stamps the click with the stale position. glfw is asked."""
    import sys
    import types

    ev, canvas, sink, _loop = _events()
    canvas._window = object()
    canvas._screen_size_is_logical = True
    monkeypatch.setitem(sys.modules, "glfw",
                        types.SimpleNamespace(get_cursor_pos=lambda _w: (40.0, 50.0)))
    _click(canvas, 3, 4)
    assert [a[:2] for _n, a, _k in sink.calls] == [(40.0, 50.0), (40.0, 50.0)]
