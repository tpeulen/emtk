"""``emtk.view_form`` -- an AutoForm view spec drawn as an immediate-mode form.

Driven the way a user drives a form: by clicking what was drawn and typing into
it. No window, no toolkit.
"""
from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter
from emtk.view_form import FormState, draw_form, find_section, format_value, parse_value


class Model:
    """A dialog's model: plain attributes, one action, the two hooks."""

    def __init__(self):
        self.method = "Manual"
        self.don = False
        self.don_value = 0.0
        self.restarts = 2
        self.series = 1
        self.pressed = []
        self.series_max = 10

    def ok(self):
        self.pressed.append("ok")

    def cancel(self):
        self.pressed.append("cancel")

    def enabled(self, name):
        if name == "don_value":
            return self.don
        return True

    def bounds(self, name):
        if name == "series":
            return (1, self.series_max)
        return None


SPEC = {
    "sections": [
        {"type": "panel", "title": "Thresholds", "sections": [
            {"type": "choice", "attr": "method", "label": "Threshold",
             "options": ["Manual", "Auto"], "description": "How to find the bleach"},
            {"type": "toggle", "attr": "don", "label": "Donor"},
            {"type": "value", "attr": "don_value", "label": "", "kind": "float"},
        ]},
        {"type": "panel", "title": "Run", "n_col": 2, "sections": [
            {"type": "value", "attr": "restarts", "label": "Restarts", "kind": "int",
             "minimum": 0, "maximum": 10},
            {"type": "value", "attr": "series", "label": "Series", "kind": "int",
             "style": "slider"},
        ]},
        {"type": "panel", "title": "Hidden", "hidden_when": {"attr": "method", "equals": "Auto"},
         "sections": [{"type": "info", "text": "only in manual mode"}]},
        {"type": "button_row", "buttons": [{"label": "Ok", "action": "ok"},
                                           {"label": "Cancel", "action": "cancel"}]},
    ]
}


class Driver:
    def __init__(self, spec, model):
        self.spec, self.model = spec, model
        self.io, self.storage, self.state = emtk.IO(), {}, FormState()
        self.painter = None

    def frame(self):
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0, 0, 500, 400), io=self.io, storage=self.storage):
            emtk.begin("form", (0, 0, 500, 400))
            draw_form(self.spec, self.model, self.state)
            emtk.end()

    def click(self, name):
        self.frame()
        x, y, w, h = self.state.rects[name]
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = (x + 3, y + h / 2)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        self.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        self.frame()

    def type(self, name, text, enter=True):
        self.click(name)
        self.io.text = text
        self.frame()
        if enter:
            self.io.key = 0x01000004
            self.frame()


def test_numbers_are_spelled_the_way_the_spec_asks():
    assert format_value(0.05, {"kind": "float"}) == "0.05"
    assert format_value(1e-3, {"kind": "float", "style": "scientific", "decimals": 1}) == "1.0e-03"
    assert format_value(2.0, {"kind": "int"}) == "2"
    assert format_value(0.5, {"kind": "float", "decimals": 3}) == "0.500"


def test_what_was_typed_is_parsed_and_clamped_or_refused():
    section = {"kind": "int", "minimum": 0, "maximum": 10}
    assert parse_value("12", section) == 10
    assert parse_value("3.6", section) == 4
    assert parse_value("abc", section) is None
    assert parse_value("5", {"kind": "float"}, bounds=(0, 1)) == 1.0


def test_every_control_is_drawn_with_its_label():
    driver = Driver(SPEC, Model())
    driver.frame()
    for text in ("Thresholds", "Threshold", "Donor", "Restarts", "Series", "Ok", "Cancel",
                 "only in manual mode"):
        assert text in driver.painter.strings, text
    for name in ("method", "don", "don_value", "restarts", "series.edit", "series.slider",
                 "ok", "cancel"):
        assert name in driver.state.rects, name


def test_fields_packed_by_n_col_share_a_line():
    driver = Driver(SPEC, Model())
    driver.frame()
    restarts, series = driver.state.rects["restarts"], driver.state.rects["series.edit"]
    assert abs(restarts[1] - series[1]) < 1.0
    assert series[0] > restarts[0] + restarts[2]


def test_typing_commits_on_enter_and_clamps():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("restarts", "0")  # typed after the existing "2" -> "20", clamped to 10
    assert model.restarts == 10


def test_nothing_is_written_until_the_edit_is_committed():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("restarts", "5", enter=False)
    assert model.restarts == 2
    driver.click("don")          # the pointer goes down elsewhere: commit
    assert model.restarts == 10  # "25" clamped


def test_a_toggle_writes_its_attribute_and_enables_what_depends_on_it():
    model = Model()
    driver = Driver(SPEC, model)
    driver.type("don_value", "5")
    assert model.don_value == 0.0, "a disabled field must not accept typing"
    driver.click("don")
    assert model.don is True
    driver.type("don_value", "5")
    assert model.don_value == 5.0


def _drawn_last(painter, string):
    """Where *string* was last drawn: the list is drawn over the form."""
    return next(t for t in reversed(painter.texts) if t[5] == string)


def test_a_choice_opens_its_own_list_and_takes_the_pick():
    model = Model()
    driver = Driver(SPEC, model)
    driver.click("method")
    x, y, w, h = _drawn_last(driver.painter, "Auto")[:4]
    field = driver.state.rects["method"]
    assert y >= field[1] + field[3] - 0.5, "the list opens below its field"
    driver.io.mouse_pos = driver.io.mouse_clicked_pos[0] = (x + 2.0, y + h / 2.0)
    driver.io.mouse_down[0] = driver.io.mouse_clicked[0] = True
    driver.frame()
    driver.io.mouse_down[0], driver.io.mouse_released[0] = False, True
    driver.frame()
    assert model.method == "Auto"
    driver.frame()
    assert "only in manual mode" not in driver.painter.strings, "hidden_when must hide it"


def test_buttons_call_their_action_and_report_use():
    model = Model()
    driver = Driver(SPEC, model)
    used = []
    driver.state.on_used = used.append
    driver.click("ok")
    assert model.pressed == ["ok"]
    assert "ok" in used


def test_a_slider_takes_its_range_from_the_model():
    model = Model()
    model.series_max = 3
    driver = Driver(SPEC, model)
    driver.type("series.edit", "9")  # "19" clamped to the run-time maximum
    assert model.series == 3


def test_find_section_finds_a_panel_by_title():
    assert find_section(SPEC, "Run")["n_col"] == 2
    assert find_section(SPEC, "missing") is None


def test_fields_of_a_panel_line_up_in_columns():
    """Labels of different lengths must not push their fields to different x."""
    spec = {"sections": [{"type": "panel", "n_col": 1, "sections": [
        {"type": "value", "attr": "restarts", "label": "Min Center", "kind": "int"},
        {"type": "value", "attr": "series", "label": "Dwell", "kind": "int"},
    ]}]}
    driver = Driver(spec, Model())
    driver.frame()
    first, second = driver.state.rects["restarts"], driver.state.rects["series"]
    assert abs(first[0] - second[0]) < 0.5
    assert second[1] > first[1]


def test_a_collapsible_panel_folds_and_remembers():
    """``collapsible`` draws a header; ``collapsed`` closes it at first; a click
    on the header opens it and the fold is kept by title."""
    spec = {"sections": [
        {"type": "panel", "title": "Axes", "collapsible": True, "collapsed": True,
         "sections": [{"type": "value", "attr": "restarts", "label": "Restarts", "kind": "int"}]},
        {"type": "panel", "title": "Open", "collapsible": True,
         "sections": [{"type": "value", "attr": "series", "label": "Series", "kind": "int"}]},
    ]}
    driver = Driver(spec, Model())
    driver.frame()
    assert "restarts" not in driver.state.rects
    assert "series" in driver.state.rects
    assert "Axes" in driver.painter.strings and "Open" in driver.painter.strings
    driver.click("Axes.fold")
    assert driver.state.folds["Axes"] is True
    driver.state.rects.clear()
    driver.frame()
    assert "restarts" in driver.state.rects
    # the open panel's field moved down below the first panel's
    assert driver.state.rects["series"][1] > driver.state.rects["restarts"][1]


def test_a_fold_header_is_compact_left_aligned_and_its_buttons_sit_close():
    """A fold is a text line plus a little padding -- shorter than a field --
    with its title at the left; the buttons of one row are an inner spacing
    apart, and a label an inner spacing from its field."""
    spec = {"sections": [
        {"type": "panel", "title": "Axes", "collapsible": True, "sections": [
            {"type": "value", "attr": "restarts", "label": "Restarts", "kind": "int"},
            {"type": "button_row", "buttons": [{"label": "Ok", "action": "ok"},
                                               {"label": "Cancel", "action": "cancel"}]},
        ]},
    ]}
    driver = Driver(spec, Model())
    driver.frame()
    line = RecordingPainter.LINE_H
    inner = emtk.Style().item_inner_spacing[0]
    fold = driver.state.rects["Axes.fold"]
    field = driver.state.rects["restarts"]
    assert fold[3] < field[3]
    pad_y = max(emtk.Style().frame_padding[1] - 1.0, 1.0)
    assert fold[3] == line + 2 * pad_y                   # a text line + a little padding
    tx = next(t[0] for t in driver.painter.texts if t[5] == "Axes")
    assert tx < fold[0] + 30.0                           # left-aligned, not centred
    ok, cancel = driver.state.rects["ok"], driver.state.rects["cancel"]
    assert abs(cancel[0] - (ok[0] + ok[2]) - inner) < 0.5
    label_w = len("Restarts") * RecordingPainter.GLYPH_W
    assert abs(field[0] - fold[0] - label_w - inner) < 1.0


def test_a_declared_width_fixes_the_control():
    spec = {"sections": [{"type": "panel", "n_col": 3, "sections": [
        {"type": "choice", "attr": "method", "label": "x:", "options": ["Manual", "Auto"]},
        {"type": "value", "attr": "restarts", "kind": "int", "width": 50},
        {"type": "value", "attr": "series", "kind": "int", "width": 60},
    ]}]}
    driver = Driver(spec, Model())
    driver.frame()
    assert abs(driver.state.rects["restarts"][2] - 50) < 0.5
    assert abs(driver.state.rects["series"][2] - 60) < 0.5
    # what is left of the line goes to the field without a width
    assert driver.state.rects["method"][2] > 200


def test_a_custom_section_is_drawn_by_the_host_in_its_place():
    seen = []

    def draw_plot(section, model, state, width):
        seen.append((section["options"]["what"], width))
        emtk.dummy(width, 40)

    spec = {"sections": [
        {"type": "value", "attr": "restarts", "label": "Restarts", "kind": "int"},
        {"type": "custom", "key": "plot", "options": {"what": "z"}},
        {"type": "value", "attr": "series", "label": "Series", "kind": "int"},
    ]}
    driver = Driver(spec, Model())
    driver.state.custom["plot"] = draw_plot
    driver.frame()
    assert seen and seen[0][0] == "z" and seen[0][1] > 100
    gap = driver.state.rects["series"][1] - driver.state.rects["restarts"][1]
    assert gap > 40


def test_labels_take_the_style_text_colour():
    """A light theme draws its labels dark: the colour comes from the style."""
    from emtk.im_core import Col, Style

    style = Style()
    style.colors[Col.TEXT] = (1, 2, 3, 255)
    painter = RecordingPainter()
    with emtk.frame(painter, (0, 0, 400, 200), style=style):
        emtk.begin("form", (0, 0, 400, 200))
        draw_form({"sections": [{"type": "value", "attr": "restarts", "label": "Restarts",
                                 "kind": "int"}]}, Model(), FormState())
        emtk.end()
    colours = [t[6] for t in painter.texts if t[5] == "Restarts"]
    assert colours and all(tuple(c)[:3] == (1, 2, 3) for c in colours)


def test_a_label_ending_in_a_hash_keeps_it():
    """"log #" + "##name" must not read as ImGui's "###" id marker."""
    class M:
        log_counts = False

    spec = {"sections": [{"type": "toggle", "attr": "log_counts", "label": "log #"}]}
    driver = Driver(spec, M())
    driver.frame()
    assert any(s.strip() == "log #" for s in driver.painter.strings)


def test_a_choice_is_drawn_as_a_combo_box():
    """The current option left-aligned in the field; a click asks for the list."""
    driver = Driver({"sections": [{"type": "choice", "attr": "method", "label": "Threshold",
                                   "options": ["Manual", "Auto"]}]}, Model())
    driver.frame()
    x, y, w, h = driver.state.rects["method"]
    text = next(t for t in driver.painter.texts if t[5] == "Manual")
    assert text[0] < x + 10.0                       # left-aligned, not centred
    driver.click("method")
    assert driver.painter.strings[-2:] == ["Manual", "Auto"], "the list, drawn last"


def test_a_long_choice_is_cut_with_an_ellipsis_before_the_arrow():
    """A caption wider than the field ends in "…" clear of the arrow, not
    clipped mid-glyph under it; the full text is still what was chosen."""
    class Wide:
        param = "Proximity ratio (green channel)"

        def enabled(self, name):
            return True

    driver = Driver({"sections": [{"type": "choice", "attr": "param", "width": 90,
                                   "options": [Wide.param, "Tau (green)"]}]}, Wide())
    driver.frame()
    x, y, w, h = driver.state.rects["param"]
    shown = [t for t in driver.painter.texts if t[5].startswith("Prox")]
    assert shown and shown[0][5].endswith("…"), [t[5] for t in driver.painter.texts]
    assert shown[0][5] != Wide.param
    assert shown[0][0] + driver.painter.text_width(shown[0][5]) <= x + w - h * 0.32 * 1.4


def test_a_suffix_is_written_after_the_number_and_read_back():
    """AutoForm's ``suffix`` (``" fps"``): shown in the field, accepted when typed."""
    section = {"kind": "int", "suffix": " fps", "minimum": 1, "maximum": 60}
    assert format_value(10, section) == "10 fps"
    assert parse_value("12 fps", section) == 12
    assert parse_value("12", section) == 12
    assert parse_value("99fps", section) == 60
    assert format_value("text", {"kind": "str", "suffix": " fps"}) == "text"


def test_a_radio_list_stacks_its_options_and_a_click_picks_one():
    """``style: radio_list`` draws one radio per line (options that are
    sentences do not fit on one); each option's rect is ``<name>.<i>``."""
    model = Model()
    spec = {"sections": [{"type": "choice", "attr": "method", "style": "radio_list",
                          "options": ["Manual", "Auto", "Other"]}]}
    driver = Driver(spec, model)
    driver.frame()
    rects = [driver.state.rects[f"method.{i}"] for i in range(3)]
    assert rects[0][1] < rects[1][1] < rects[2][1]
    assert abs(rects[0][0] - rects[2][0]) < 1.0
    driver.click("method.2")
    assert model.method == "Other"
    inline = Driver({"sections": [dict(spec["sections"][0], style="radio")]}, Model())
    inline.frame()
    assert abs(inline.state.rects["method.0"][1] - inline.state.rects["method.1"][1]) < 1.0


# ------------------------------------------------------------- colour + code editor
class Styled:
    def __init__(self):
        self.colour = "#bb3838"
        self.script = "plots:\n- type: 1d\n"


COLOUR_SPEC = {"sections": [
    {"type": "value", "attr": "colour", "label": "Title color", "kind": "color"},
    {"type": "custom", "key": "code_editor", "target": "script",
     "options": {"height": 120, "language": "none"}},
]}


def test_colour_values_are_parsed_as_hex():
    assert parse_value("BB3838", {"kind": "color"}) == "#bb3838"
    assert parse_value("#abc", {"kind": "color"}) == "#aabbcc"
    assert parse_value("not a colour", {"kind": "color"}) is None


def test_a_colour_field_has_a_swatch_that_opens_a_picker():
    model = Styled()
    driver = Driver(COLOUR_SPEC, model)
    driver.frame()
    assert "colour.swatch" in driver.state.rects and "colour" in driver.state.rects
    assert any(tuple(call[-1])[:3] == (187, 56, 56) for call in driver.painter.calls
               if call[0] == "fill_rect" and isinstance(call[-1], tuple))
    driver.click("colour.swatch")
    assert "colour" in driver.state.pickers
    driver.frame()
    assert "colour.picker" in driver.state.rects


def test_typing_a_hex_colour_commits_it():
    model = Styled()
    driver = Driver(COLOUR_SPEC, model)
    driver.frame()
    driver.state.buffers["colour"] = "#00ff00"
    driver.type("colour", "")
    assert model.colour == "#00ff00"


def test_a_code_editor_shows_and_writes_back_its_attribute():
    model = Styled()
    driver = Driver(COLOUR_SPEC, model)
    driver.frame()
    assert "script" in driver.state.rects
    assert driver.state.editors["script"].text == model.script
    driver.click("script")
    assert driver.state.editor_focus == "script"
    driver.io.text = "x"
    driver.frame()
    assert "x" in model.script and model.script != "plots:\n- type: 1d\n"
    model.script = "loaded: 1\n"
    driver.frame()
    assert driver.state.editors["script"].text == "loaded: 1\n"


def test_a_spin_value_steps_with_its_arrows_and_the_wheel():
    """style "spin": arrows at the field's right edge; up adds a step, down
    takes one; the wheel over the field does the same; bounds hold."""
    from emtk.view_form import spin_step

    spec = {"sections": [
        {"type": "value", "attr": "restarts", "label": "Bins", "kind": "int", "style": "spin",
         "minimum": 0, "maximum": 3},
        {"type": "value", "attr": "don_value", "label": "Min", "kind": "float",
         "style": "spin"},
    ]}
    model = Model()
    model.don = True
    model.don_value = 6.0
    driver = Driver(spec, model)
    driver.frame()
    x, y, w, h = driver.state.rects["restarts.stepper"]
    assert x > driver.state.rects["restarts"][0] + driver.state.rects["restarts"][2] - 1

    def click(px, py):
        io = driver.io
        io.mouse_pos = io.mouse_clicked_pos[0] = (px, py)
        io.mouse_down[0] = io.mouse_clicked[0] = True
        driver.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        driver.frame()

    click(x + w / 2, y + h * 0.25)
    assert model.restarts == 3
    click(x + w / 2, y + h * 0.25)
    assert model.restarts == 3                       # the maximum holds
    click(x + w / 2, y + h * 0.75)
    assert model.restarts == 2
    fx, fy, fw, fh = driver.state.rects["don_value"]
    driver.io.mouse_pos = (fx + 5, fy + fh / 2)
    driver.io.mouse_wheel = -1.0
    driver.frame()
    assert model.don_value == 5.9
    assert spin_step(0.05, {"kind": "float"}) == 0.001
    assert spin_step(3, {"kind": "int"}) == 1.0
    assert spin_step(1.0, {"kind": "float", "step": 0.25}) == 0.25


def test_a_value_without_spin_has_no_arrows():
    driver = Driver({"sections": [{"type": "value", "attr": "restarts", "kind": "int"}]},
                    Model())
    driver.frame()
    assert "restarts.stepper" not in driver.state.rects


def test_special_text_stands_for_the_minimum():
    section = {"kind": "int", "minimum": -1, "maximum": 64, "special_text": "All cores"}
    assert format_value(-1, section) == "All cores"
    assert format_value(4, section) == "4"
    assert parse_value("all cores", section) == -1
    assert parse_value("8", section) == 8


class Runner:
    def __init__(self):
        self.running = False
        self.count = 0
        self.fraction = None
        self.log = []

    def run(self):
        self.log.append("run")

    def stop(self):
        self.log.append("stop")

    def columns_label(self):
        return f"Columns ({self.count})"

    def status(self):
        return "Running…"


RUN_SPEC = {"sections": [
    {"type": "button_row", "buttons": [
        {"label": "Run", "action": "run", "hidden_when": {"attr": "running", "equals": "true"}},
        {"label": "Stop", "action": "stop",
         "hidden_when": {"attr": "running", "equals": "false"}},
        {"label": "Columns", "action": "pick", "label_source": "columns_label"},
    ]},
    {"type": "progress", "attr": "fraction", "text_source": "status"},
]}


def test_a_button_can_hide_and_take_its_label_from_the_model():
    model = Runner()
    model.count = 3
    driver = Driver(RUN_SPEC, model)
    driver.frame()
    assert "Run" in driver.painter.strings and "Stop" not in driver.painter.strings
    assert "Columns (3)" in driver.painter.strings
    model.running = True
    driver.frame()
    assert "Stop" in driver.painter.strings and "Run" not in driver.painter.strings
    driver.click("stop")
    assert model.log == ["stop"]


def test_a_progress_bar_is_determinate_or_sweeps():
    model = Runner()
    driver = Driver(RUN_SPEC, model)
    driver.frame()                       # None: indeterminate, still draws its text
    assert "Running…" in driver.painter.strings
    model.fraction = 0.5
    driver.frame()
    assert "Running…" in driver.painter.strings


def test_spin_true_adds_arrows_to_a_scientific_value():
    spec = {"sections": [{"type": "value", "attr": "don_value", "kind": "float",
                          "style": "scientific", "decimals": 2, "spin": True}]}
    model = Model()
    model.don, model.don_value = True, 85.9
    driver = Driver(spec, model)
    driver.frame()
    x, y, w, h = driver.state.rects["don_value.stepper"]
    io = driver.io
    io.mouse_pos = io.mouse_clicked_pos[0] = (x + w / 2, y + h * 0.25)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    driver.frame()
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    driver.frame()
    assert abs(model.don_value - 86.9) < 1e-9


# ------------------------------------------------------ narrow windows
class AxisModel:
    def __init__(self):
        self.x_name = "Proximity ratio"
        self.bins = 81
        self.log = False
        self.path = "/Users/someone/data/experiment/burstwise_All 0.1500#30"

    def parameter_options(self):
        return ["Tau (green)", "Proximity ratio"]

    def set_axis(self):
        pass


AXIS_ROW = {"sections": [{"type": "row", "n_col": 4, "sections": [
    {"type": "choice", "attr": "x_name", "label": "x:", "options_source": "parameter_options"},
    {"type": "value", "attr": "bins", "kind": "int", "width": 48, "wrap_before": True},
    {"type": "toggle", "attr": "log", "label": ""},
    {"type": "button_row", "weight": 0, "buttons": [{"label": "Set", "action": "set_axis"}]},
]}]}


def _draw_at(spec, model, width, state=None, io=None):
    state = state or FormState()
    io = io or emtk.IO()
    with emtk.frame(RecordingPainter(), (0, 0, width, 300), io=io, storage={}):
        emtk.begin("form", (0, 0, width, 300))
        draw_form(spec, model, state)
        emtk.end()
    return state


def _chars_shown(width):
    """Characters of "0" that fit in a combo box *width* wide."""
    with emtk.frame(RecordingPainter(), (0, 0, 10, 10), io=emtk.IO(), storage={}):
        emtk.begin("m", (0, 0, 10, 10))
        one = emtk.calc_text_size("0")[0]
        emtk.end()
    return width / one


def test_a_line_that_fits_stays_one_line_and_the_choice_takes_the_room():
    state = _draw_at(AXIS_ROW, AxisModel(), 500)
    rects = state.rects
    assert len({round(r[1]) for r in rects.values()}) == 1
    assert rects["x_name"][2] > 250, "the combo box is the flexible one"
    assert rects["set_axis"][2] < 60, "a weight-0 button is as wide as its label"


def test_a_line_too_narrow_wraps_at_its_break_and_nothing_overflows():
    width = 170
    state = _draw_at(AXIS_ROW, AxisModel(), width)
    rects = state.rects
    assert rects["bins"][1] > rects["x_name"][1], "wrapped before the bins"
    assert rects["set_axis"][1] == rects["bins"][1]
    for name, (x, _y, w, _h) in rects.items():
        assert x + w <= width + 0.5, f"{name} runs past the form"
    assert _chars_shown(rects["x_name"][2]) >= 12


def test_the_continuation_line_starts_under_the_controls():
    rects = _draw_at(AXIS_ROW, AxisModel(), 170).rects
    assert abs(rects["bins"][0] - rects["x_name"][0]) < 1.0


def test_a_toolbar_row_wraps_to_the_left_edge():
    """``"wrap_indent": false``: a toolbar's lines all start at the left edge,
    none indented under the first label into a dead strip."""
    spec = {"sections": [dict(AXIS_ROW["sections"][0], wrap_indent=False)]}
    rects = _draw_at(spec, AxisModel(), 170).rects
    assert rects["bins"][1] > rects["x_name"][1]
    assert rects["bins"][0] < rects["x_name"][0] - 1.0
    assert rects["bins"][0] <= 10.0


def test_a_button_row_too_narrow_for_its_labels_wraps_them():
    spec = {"sections": [{"type": "button_row", "buttons": [
        {"label": "Screenshot", "action": "a"}, {"label": "Data", "action": "b"},
        {"label": "Clear", "action": "c"}]}]}

    class M:
        a = b = c = staticmethod(lambda: None)

    wide = _draw_at(spec, M(), 400).rects
    assert len({r[1] for r in wide.values()}) == 1
    narrow = _draw_at(spec, M(), 110).rects
    assert len({r[1] for r in narrow.values()}) >= 2
    for x, _y, w, _h in narrow.values():
        assert x + w <= 110.5


def test_a_path_shows_its_end_at_rest():
    spec = {"sections": [{"type": "value", "attr": "path", "kind": "str", "elide": "start"}]}
    painter = RecordingPainter()
    with emtk.frame(painter, (0, 0, 200, 60), io=emtk.IO(), storage={}):
        emtk.begin("form", (0, 0, 200, 60))
        draw_form(spec, AxisModel(), FormState())
        emtk.end()
    shown = [t for t in painter.strings if "#30" in t]
    assert shown and shown[0].startswith("…"), painter.strings


def test_a_slider_without_a_field_writes_its_value_on_itself_and_types_on_double_click():
    """``"field": false``: one control, not a field and a slider showing the
    same number. The value (and its suffix) is on the slider; a double click
    makes it a field, Enter commits, Escape leaves it."""
    spec = {"sections": [{"type": "value", "attr": "series", "label": "Step", "kind": "int",
                          "style": "slider", "field": False, "suffix": " fps"}]}
    model = Model()
    model.series = 4
    driver = Driver(spec, model)
    driver.frame()
    rects = driver.state.rects
    assert "series.slider" in rects and "series.edit" not in rects
    assert "4 fps" in driver.painter.strings
    # the slider spans the line the field and slider shared
    assert rects["series.slider"][2] > 300

    x, y, w, h = rects["series.slider"]
    io = driver.io
    io.mouse_pos = io.mouse_clicked_pos[0] = (x + w / 2, y + h / 2)
    io.mouse_double_clicked[0] = True
    driver.frame()
    io.mouse_double_clicked[0] = False
    driver.frame()
    assert "series.edit" in driver.state.rects and model.series == 4
    io.text = "7"
    driver.frame()
    io.text = ""
    io.key = 0x01000004                     # Enter
    driver.frame()
    io.key = 0
    driver.frame()
    assert model.series == 7 and "series.slider" in driver.state.rects

    io.mouse_double_clicked[0] = True
    driver.frame()
    io.mouse_double_clicked[0] = False
    io.text = "9"
    driver.frame()
    io.text, io.key = "", 0x01000000         # Escape
    driver.frame()
    io.key = 0
    driver.frame()
    assert model.series == 7


def test_a_wrapped_line_is_cut_evenly_not_greedily():
    """Greedy packing leaves the last line short (a button alone, the rest of
    the line dead); the same number of lines cut evenly fills both."""
    from emtk.view_form import _segments

    label_w = [0.0] * 4
    need_w = [100.0, 100.0, 100.0, 60.0]
    # pieces [0], [1], [2], [3]: greedy fits three on a 330 line, one on the next
    runs = _segments(label_w, need_w, 330.0, 8.0, frozenset({1, 2, 3}))
    assert runs == [[0, 1], [2, 3]]
    # never two pieces on a line wider than the room
    wide = [100.0, 400.0, 100.0, 100.0]
    runs = _segments(label_w, wide, 330.0, 8.0, frozenset({1, 2, 3}))
    assert [c for run in runs for c in run] == [0, 1, 2, 3]
    for run in runs:
        assert len(run) == 1 or sum(wide[c] for c in run) + 8.0 * (len(run) - 1) <= 330.5
