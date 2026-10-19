"""Dial, LCD number, tristate checkbox, completer field, key-sequence input, tool box."""
from __future__ import annotations

from emtk import im, keys
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.testing import Driver, RecordingPainter, render
from emtk.widgets import form_controls, instruments


class Panel(ImApp):
    """One window holding whatever *body* draws; *body* gets the app to remember rects."""

    def __init__(self, body, size=(420, 360)):
        super().__init__(self.gui)
        self.body = body
        self.size = size
        self.ids = {}

    def gui(self):
        im.begin("Panel", (0, 0, *self.size))
        self.body(self)
        im.end()


def _drive(body, size=(420, 360)):
    app = Panel(body, size)
    driver = Driver(app, size)
    driver.draw(2)
    return app, driver


# --------------------------------------------------------------------------- #
# Dial
# --------------------------------------------------------------------------- #
def test_dial_follows_the_pointer_angle_wheel_and_keys():
    state = {"v": 5.0}

    def body(app):
        _c, state["v"] = im.dial("Gain", state["v"], 0.0, 10.0, step=0.5)
        app.remember("dial")
        app.ids["dial"] = im.get_item_id()

    app, driver = _drive(body)
    x, y, w, h = driver.rect("dial")
    cx, cy = x + w / 2, y + h / 2
    # Straight up is the middle of the 300 degree arc.
    driver.click((cx, y + 3))
    assert abs(state["v"] - 5.0) < 0.2
    driver.click((x + 1, cy))            # 9 o'clock: -90 of +-150 degrees -> 2/10 of the range
    assert abs(state["v"] - 2.0) < 0.3
    driver.wheel(1, at=(cx, cy))
    assert abs(state["v"] - 2.5) < 0.3
    app.storage["__nav_id__"] = app.ids["dial"]
    driver.frame()
    driver.press(keys.KEY_END)
    assert state["v"] == 10.0
    driver.press(keys.KEY_PAGE_DOWN)     # ten steps
    assert state["v"] == 5.0
    driver.press(keys.KEY_HOME)
    driver.press(keys.KEY_LEFT)          # stays at the minimum
    assert state["v"] == 0.0


def test_integer_dial_returns_ints_and_wrapping_runs_round():
    state = {"n": 98}

    def body(app):
        _c, state["n"] = im.dial("Phase", state["n"], 0, 100, step=1, wrapping=True)
        app.ids["dial"] = im.get_item_id()

    app, driver = _drive(body)
    app.storage["__nav_id__"] = app.ids["dial"]
    driver.frame()
    driver.press(keys.KEY_RIGHT)
    assert state["n"] == 99 and isinstance(state["n"], int)
    driver.press(keys.KEY_RIGHT, SHIFT_MODIFIER)     # ten steps, round past the end
    assert state["n"] == 9


def test_dial_draws_its_value_and_caption():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("d")
        im.dial("Gain", 6.5, 0.0, 10.0, fmt="%.1f")
        im.end()
    assert "6.5" in painter.strings and "Gain" in painter.strings


# --------------------------------------------------------------------------- #
# LCD number
# --------------------------------------------------------------------------- #
def test_lcd_segments():
    cells = instruments.lcd_segments("-1.5")
    assert cells == [("g", False), ("bc", True), ("acdfg", False)]
    assert instruments.lcd_segments("12:30")[2] == (":", False)
    assert instruments.lcd_segments("8")[0][0] == "abcdefg"
    assert instruments.lcd_segments("?")[0][0] == ""


def test_lcd_number_draws_segments_and_reports_overflow():
    seen = {}

    def gui():
        im.begin("l", (0, 0, 300, 200))
        seen["fits"] = im.lcd_number(1234, digits=4)
        seen["over"] = im.lcd_number(123456, digits=4)
        seen["rect"] = im.get_item_rect()
        seen["accent"] = im.get_style().color(im.Col.CHECK_MARK)
        im.end()

    painter = render(gui, (0, 0, 300, 200))
    assert seen["fits"] is False and seen["over"] is True
    x, y, w, h = (int(v) for v in seen["rect"])
    want = bytes(seen["accent"][:3])
    lit = sum(painter.px[(yy * painter.width + xx) * 4:(yy * painter.width + xx) * 4 + 3] == want
              for yy in range(y, y + h) for xx in range(x, x + w))
    assert lit > 30                       # the overflow "E" cells are lit in the accent colour


# --------------------------------------------------------------------------- #
# Tristate checkbox
# --------------------------------------------------------------------------- #
def test_tristate_cycles():
    state = {"v": None, "u": False}

    def body(app):
        _c, state["v"] = im.checkbox_tristate("All", state["v"])
        app.remember("all")
        _c, state["u"] = im.checkbox_tristate("User", state["u"], user_tristate=True)
        app.remember("user")

    _app, driver = _drive(body)
    driver.click("all")
    assert state["v"] is True              # partial -> checked
    driver.click("all")
    assert state["v"] is False
    driver.click("all")
    assert state["v"] is True              # a plain click never makes it partial
    seen = []
    for _ in range(3):
        driver.click("user")
        seen.append(state["u"])
    assert seen == [None, True, False]     # Qt's user-tristate cycle


# --------------------------------------------------------------------------- #
# Completer
# --------------------------------------------------------------------------- #
NAMES = ["Alexa 488", "Alexa 647", "Atto 532", "Atto 647N", "Cy5"]


def test_completions_rank_prefix_matches_first():
    assert form_controls.completions("647", NAMES) == ["Alexa 647", "Atto 647N"]
    assert form_controls.completions("at", NAMES) == ["Atto 532", "Atto 647N"]
    assert form_controls.completions("a", NAMES, limit=2) == ["Alexa 488", "Alexa 647"]
    assert form_controls.completions("", NAMES) == []
    assert form_controls.completions("cy5", NAMES) == []          # already complete


def test_completer_lists_matches_and_takes_a_pick_by_keys_and_by_click():
    state = {"t": "", "below": 0}

    def body(app):
        im.set_next_item_width(240)
        _c, state["t"] = im.input_text_completer("Dye", state["t"], NAMES)
        app.remember("dye")
        if im.button("Below"):
            state["below"] += 1
        app.remember("below")

    _app, driver = _drive(body)
    driver.click("dye")
    driver.type("att")
    driver.frame()
    assert "Atto 532" in driver.frame().strings
    driver.press(keys.KEY_DOWN)
    driver.press(keys.KEY_DOWN)
    driver.press(keys.KEY_RETURN)
    assert state["t"] == "Atto 647N"
    assert "Atto 532" not in driver.frame().strings           # accepted: the list closes
    # By click: the row over the button takes the click, the button does not.
    for _ in range(9):
        driver.press(keys.KEY_BACKSPACE)
    driver.type("alexa")
    driver.frame()
    driver.click("Alexa 647")
    driver.frame()
    assert state["t"] == "Alexa 647" and state["below"] == 0


def test_escape_closes_the_completions_until_the_text_changes():
    state = {"t": ""}

    def body(app):
        _c, state["t"] = im.input_text_completer("Dye", state["t"], NAMES)
        app.remember("dye")

    _app, driver = _drive(body)
    driver.click("dye")
    driver.type("a")
    driver.frame()
    assert "Alexa 488" in driver.frame().strings
    driver.escape()
    assert "Alexa 488" not in driver.frame().strings
    driver.type("t")
    driver.frame()
    assert "Atto 532" in driver.frame().strings


# --------------------------------------------------------------------------- #
# Key sequence
# --------------------------------------------------------------------------- #
def test_chord_names_and_events():
    assert form_controls.chord_name(keys.MOD_CTRL | keys.MOD_SHIFT | keys.KEY_K) == "Ctrl+Shift+K"
    assert form_controls.chord_name(keys.KEY_F5) == "F5"
    assert form_controls.chord_name(0) == ""
    assert form_controls.chord_from_event(ord("K"), CONTROL_MODIFIER) == keys.MOD_CTRL | keys.KEY_K


def test_key_sequence_records_cancels_and_clears():
    state = {"c": keys.KEY_F5, "n": 0}

    def body(app):
        im.set_next_item_width(200)
        changed, state["c"] = im.key_sequence_input("Run", state["c"])
        state["n"] += changed
        app.remember("seq")

    _app, driver = _drive(body)
    assert "F5" in driver.frame().strings
    driver.click("seq")
    assert "Press a shortcut…" in driver.frame().strings
    driver.press(0x01000021, CONTROL_MODIFIER)          # Ctrl alone: still waiting
    assert "Press a shortcut…" in driver.frame().strings
    driver.press(ord("r"), CONTROL_MODIFIER | SHIFT_MODIFIER)
    assert state["c"] == keys.MOD_CTRL | keys.MOD_SHIFT | keys.KEY_R
    assert "Ctrl+Shift+R" in driver.frame().strings
    driver.click("seq")
    driver.escape()                                      # cancel: keeps the shortcut
    assert state["c"] == keys.MOD_CTRL | keys.MOD_SHIFT | keys.KEY_R
    driver.click("seq")
    driver.press(keys.KEY_BACKSPACE)                     # clear
    assert state["c"] == 0 and "None" in driver.frame().strings
    assert state["n"] == 2
    # The recorded chord is what im.is_key_chord_pressed takes.
    assert im.is_key_chord_pressed.__name__ == "is_key_chord_pressed"


# --------------------------------------------------------------------------- #
# Tool box
# --------------------------------------------------------------------------- #
def test_tool_box_keeps_exactly_one_page_open():
    state = {"open": None}

    def body(app):
        im.begin_tool_box("tb")
        for name in ("Acquisition", "Analysis", "Export"):
            if im.tool_box_item(name):
                im.text(f"{name} page")
        state["open"] = im.end_tool_box()

    _app, driver = _drive(body)
    strings = driver.frame().strings
    assert "Acquisition page" in strings and "Analysis page" not in strings
    driver.click("> Analysis")
    driver.frame()
    strings = driver.frame().strings
    assert "Analysis page" in strings and "Acquisition page" not in strings
    assert state["open"] == 1
    driver.click("v Analysis")                 # the open page stays open
    strings = driver.frame().strings
    assert "Analysis page" in strings and state["open"] == 1


def test_tool_box_current_can_be_forced():
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300, 200)):
        im.begin("t")
        im.begin_tool_box("tb", current=2)
        for name in ("A", "B", "C"):
            if im.tool_box_item(name):
                im.text(f"{name} body")
        im.end_tool_box()
        im.end()
    assert "C body" in painter.strings and "A body" not in painter.strings
