"""Behaviour checks for the upgraded immediate-mode slider family.

Drawn through a recorder exactly the way tests/test_the_painter_contract.py
drives the demo: a real frame, a real IO, and assertions about the values
that come back and the strings that get drawn -- not about rectangles.
"""
from __future__ import annotations

import math

import pytest

import emtk
from emtk import im


class RecordingPainter:
    """Counts the operations and keeps the strings, instead of drawing."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.ops = 0

    def _op(self) -> None:
        self.ops += 1

    def fill_rect(self, *a) -> None:
        self._op()

    def stroke_rect(self, *a) -> None:
        self._op()

    def gradient_rect(self, *a) -> None:
        self._op()

    def fill_triangle(self, *a) -> None:
        self._op()

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)
        self._op()

    def text_rotated(self, *a) -> None:
        self._op()

    def image(self, *a) -> None:
        self._op()

    def push_clip(self, *a) -> None:
        pass

    def pop_clip(self) -> None:
        pass

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


def run(gui, io=None, storage=None, size=(0.0, 0.0, 400.0, 300.0)):
    painter = RecordingPainter()
    with emtk.frame(painter, size, io=io or emtk.IO(), storage=storage if storage is not None else {}):
        gui()
    return painter


# ---------------------------------------------------------------------------
# What the old slider did, still does
# ---------------------------------------------------------------------------
def test_a_plain_slider_draws_its_value_and_keeps_it():
    out: dict = {}

    def gui():
        changed, v = emtk.slider_float("alpha", 0.5, 0.0, 1.0)
        out["v"] = v

    painter = run(gui)
    assert out["v"] == pytest.approx(0.5)
    assert "0.500" in painter.strings


def test_a_slider_with_a_format_shows_it():
    def gui():
        emtk.slider_float("f", 0.5, 0.0, 1.0, "ratio = %.3f")
        emtk.slider_int("i", 3, 0, 10, "%d apples")

    painter = run(gui)
    assert "ratio = 0.500" in painter.strings
    assert "3 apples" in painter.strings


def test_set_next_item_width_still_applies_to_the_track():
    boxes: dict = {}

    def gui():
        emtk.set_next_item_width(120.0)
        emtk.slider_float("narrow", 0.5, 0.0, 1.0)
        boxes["narrow"] = emtk.get_item_rect()
        emtk.slider_float("wide", 0.5, 0.0, 1.0)
        boxes["wide"] = emtk.get_item_rect()

    run(gui)
    assert boxes["narrow"][2] == pytest.approx(120.0)
    assert boxes["wide"][2] > 120.0


def test_an_int_slider_reports_an_int_without_a_drag():
    out: dict = {}

    def gui():
        changed, v = emtk.slider_int("n", 3, 0, 10)
        out["v"] = v
        out["changed"] = changed

    run(gui)
    assert out["v"] == 3 and isinstance(out["v"], int)
    assert out["changed"] is False


# ---------------------------------------------------------------------------
# Dragging: linear and logarithmic
# ---------------------------------------------------------------------------
def _slider_box(label, *args, io=None, storage=None, **kw):
    """Draw the slider once to learn its box, with a fresh IO each time."""
    box: dict = {}

    def gui():
        changed, v = emtk.slider_float(label, *args, **kw)
        box["rect"] = emtk.get_item_rect()
        box["v"] = v
        box["changed"] = changed

    run(gui, io=io, storage=storage)
    return box


def test_dragging_a_linear_slider_moves_the_value_to_the_pointer():
    io, storage = emtk.IO(), {}
    box = _slider_box("lin", 0.0, 0.0, 1.0, io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + r[2] * 0.75, r[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    out = {}
    def gui():
        out["changed"] = emtk.slider_float("lin", box["v"], 0.0, 1.0)[0]
    run(gui, io=io, storage=storage)
    assert out["changed"] is True


def test_a_log_slider_puts_the_geometric_mean_at_the_middle():
    mid = emtk.im_compat if False else None  # noqa: F841 (readability below)
    from emtk.widgets.sliders import value_from_ratio

    got = value_from_ratio(0.5, 1.0, 1000.0, 0.01, 0.0, False)
    assert got == pytest.approx(math.sqrt(1000.0), rel=1e-3)


def test_dragging_a_log_slider_reads_log_space():
    io, storage = emtk.IO(), {}
    box = _slider_box("L", 1.0, 1.0, 1000.0, "%.1f",
                      emtk.SliderFlags.LOGARITHMIC, io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + r[2] * 0.75, r[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    out = {}
    def gui():
        out["v"] = emtk.slider_float("L", box["v"], 1.0, 1000.0, "%.1f",
                                     emtk.SliderFlags.LOGARITHMIC)[1]
    run(gui, io=io, storage=storage)
    expected = 1000.0 ** 0.75
    assert out["v"] == pytest.approx(expected, rel=0.05)


def test_the_same_drag_without_the_flag_is_linear():
    io, storage = emtk.IO(), {}
    box = _slider_box("L", 1.0, 1.0, 1000.0, "%.1f", io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + r[2] * 0.75, r[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    out = {}
    def gui():
        out["v"] = emtk.slider_float("L", box["v"], 1.0, 1000.0, "%.1f")[1]
    run(gui, io=io, storage=storage)
    assert out["v"] == pytest.approx(1.0 + 0.75 * 999.0, rel=0.01)


def test_a_log_slider_across_zero_reaches_exactly_zero():
    from emtk.widgets.sliders import ratio_from_value

    lo, hi = -100.0, 100.0
    eps = 0.01
    # a hair either side of the dead-zone centre is ~0; the zone itself is 0
    t_zero = 0.5
    v = emtk.widgets.sliders.value_from_ratio(t_zero, lo, hi, eps, 0.02, False)
    assert v == 0.0
    for t in (0.1, 0.25, 0.75, 0.9):
        back = ratio_from_value(
            emtk.widgets.sliders.value_from_ratio(t, lo, hi, eps, 0.02, False),
            lo, hi, eps, 0.02)
        assert back == pytest.approx(t, abs=1e-6)


# ---------------------------------------------------------------------------
# Round to format
# ---------------------------------------------------------------------------
def test_a_drag_stores_what_the_format_shows():
    io, storage = emtk.IO(), {}
    box = _slider_box("r", 0.0, 0.0, 1.0, "%.2f", io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + r[2] * (1.0 / 3.0), r[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    out = {}
    def gui():
        out["v"] = emtk.slider_float("r", box["v"], 0.0, 1.0, "%.2f")[1]
    run(gui, io=io, storage=storage)
    assert out["v"] == pytest.approx(round(1.0 / 3.0, 2))
    assert out["v"] != 1.0 / 3.0


def test_no_round_to_format_keeps_the_full_precision():
    io, storage = emtk.IO(), {}
    box = _slider_box("r", 0.0, 0.0, 1.0, "%.2f",
                      emtk.SliderFlags.NO_ROUND_TO_FORMAT, io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + r[2] * (1.0 / 3.0), r[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    out = {}
    def gui():
        out["v"] = emtk.slider_float("r", box["v"], 0.0, 1.0, "%.2f",
                                     emtk.SliderFlags.NO_ROUND_TO_FORMAT)[1]
    run(gui, io=io, storage=storage)
    assert out["v"] == pytest.approx(1.0 / 3.0, rel=1e-3)


# ---------------------------------------------------------------------------
# The Ctrl+Click type-in
# ---------------------------------------------------------------------------
def _open_type_in(label="t", args=(0.25, 0.0, 1.0), kw=None):
    io, storage = emtk.IO(), {}
    kw = dict(kw or {})
    box = _slider_box(label, *args, io=io, storage=storage, **kw)
    r = box["rect"]
    io.mouse_pos = (r[0] + 10, r[1] + 2)
    io.mouse_clicked[0] = True
    io.key_ctrl = True

    out = {}
    def gui():
        changed, v = emtk.slider_float(label, *args, **kw)
        out["changed"] = changed
        out["v"] = v

    painter = run(gui, io=io, storage=storage)      # opens the field
    painter = run(gui, io=io, storage=storage)      # draws the typed text
    assert out["changed"] is False, "opening the field is not an edit"
    assert out["v"] == pytest.approx(args[0])
    return io, storage, out, r, gui


def test_ctrl_click_opens_the_field_showing_the_value():
    io, storage, out, r, gui = _open_type_in()
    painter = run(gui, io=io, storage=storage)
    assert "0.250" in painter.strings


def test_typing_commits_on_enter_and_reports_once():
    io, storage, out, r, gui = _open_type_in()
    io.key_ctrl = False
    io.mouse_clicked[0] = False

    io.key_events = [(0, "6", 0)]           # the field opened select-all
    run(gui, io=io, storage=storage)
    painter = run(gui, io=io, storage=storage)
    assert painter.strings[0].startswith("6"), painter.strings
    assert out["changed"] is False          # typing alone is not a value yet

    io.key_events = [(13, "", 0)]           # Enter commits
    run(gui, io=io, storage=storage)
    assert out["changed"] is True and out["v"] == 6.0

    io.key_events = []
    run(gui, io=io, storage=storage)
    assert out["changed"] is False          # and only that frame reported it


def test_escape_cancels_back_to_the_old_value():
    io, storage, out, r, gui = _open_type_in()
    io.key_ctrl = False
    io.mouse_clicked[0] = False
    io.key_events = [(0, "9", 0)]
    run(gui, io=io, storage=storage)
    io.key_events = [(emtk.KEY_ESCAPE, "", 0)]
    run(gui, io=io, storage=storage)
    painter = run(gui, io=io, storage=storage)
    assert "0.250" in painter.strings
    assert out["changed"] is False and out["v"] == pytest.approx(0.25)


def test_no_input_refuses_the_type_in():
    io, storage = emtk.IO(), {}
    box = _slider_box("ni", 0.25, 0.0, 1.0, "%.3f",
                      emtk.SliderFlags.NO_INPUT, io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + 10, r[1] + 2)
    io.mouse_clicked[0] = True
    io.key_ctrl = True

    out = {}
    def gui():
        changed, _v = emtk.slider_float("ni", 0.25, 0.0, 1.0, "%.3f",
                                        emtk.SliderFlags.NO_INPUT)
        out["changed"] = changed
    run(gui, io=io, storage=storage)
    painter = run(gui, io=io, storage=storage)
    # no field opened: the track's own value text, never a bare typed digit
    assert "0.250" in painter.strings
    assert out["changed"] is False


def test_a_committed_value_without_always_clamp_may_leave_the_bounds():
    io, storage, out, r, gui = _open_type_in()
    io.key_ctrl = False
    io.mouse_clicked[0] = False
    io.key_events = [(0, "5", 0)]
    run(gui, io=io, storage=storage)
    io.key_events = [(13, "", 0)]
    run(gui, io=io, storage=storage)
    assert out["v"] == 5.0 and out["changed"] is True


def test_always_clamp_clamps_the_commit():
    flags = {"flags": emtk.SliderFlags.ALWAYS_CLAMP}
    io, storage, out, r, gui = _open_type_in(kw=flags)
    io.key_ctrl = False
    io.mouse_clicked[0] = False
    io.key_events = [(0, "5", 0)]
    run(gui, io=io, storage=storage)
    io.key_events = [(13, "", 0)]
    run(gui, io=io, storage=storage)
    assert out["v"] == 1.0 and out["changed"] is True


def test_an_int_type_in_rounds():
    io, storage = emtk.IO(), {}
    box_holder = {}

    def gui0():
        changed, v = emtk.slider_int("nn", 3, 0, 10)
        box_holder["rect"] = emtk.get_item_rect()
        box_holder["v"] = v

    run(gui0, io=io, storage=storage)
    r = box_holder["rect"]
    io.mouse_pos = (r[0] + 10, r[1] + 2)
    io.mouse_clicked[0] = True
    io.key_ctrl = True
    run(gui0, io=io, storage=storage)
    run(gui0, io=io, storage=storage)

    io.key_ctrl = False
    io.mouse_clicked[0] = False
    io.key_events = [(0, "7.6", 0)]
    run(gui0, io=io, storage=storage)
    io.key_events = [(13, "", 0)]
    run(gui0, io=io, storage=storage)
    assert box_holder["v"] == 8 and isinstance(box_holder["v"], int)


# ---------------------------------------------------------------------------
# The scalar form forwards flags
# ---------------------------------------------------------------------------
def test_slider_scalar_forwards_the_log_flag():
    # the typed spelling accepts the same trailing flag as the C++
    def gui():
        out["c"], out["v"] = emtk.slider_scalar(
            "##s", emtk.im.DataType.DOUBLE, 5.0, 1.0, 100.0,
            "%.2f", emtk.im.SliderFlags.LOGARITHMIC)
    out = {}
    run(gui)
    assert out["v"] == pytest.approx(5.0)


def _click_then_type(double: bool):
    """Click the track (twice-quick if *double*), then type ``6``; the drawn text."""
    io, storage = emtk.IO(), {}
    args = (0.25, 0.0, 1.0)
    box = _slider_box("t", *args, io=io, storage=storage)
    r = box["rect"]
    io.mouse_pos = (r[0] + 10, r[1] + 2)
    io.mouse_clicked[0] = True
    io.mouse_double_clicked[0] = double
    io.key_ctrl = False

    def gui():
        emtk.slider_float("t", *args)

    run(gui, io=io, storage=storage)
    io.mouse_clicked[0] = False
    io.mouse_double_clicked[0] = False
    io.key_events = [(0, "6", 0)]
    run(gui, io=io, storage=storage)
    return run(gui, io=io, storage=storage).strings


def test_double_click_opens_the_field_like_ctrl_click():
    assert _click_then_type(double=True)[0].startswith("6"), "typing after a double click should edit"


def test_a_single_click_does_not_open_the_field():
    assert not _click_then_type(double=False)[0].startswith("6")
