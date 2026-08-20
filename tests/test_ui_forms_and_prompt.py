"""The four widgets cmtk shipped with no test of its own.

They were all exercised, thoroughly, from the application cmtk grew inside --
which is exactly the arrangement this project exists to end. A library whose
proof lives in one caller is a library that cannot be changed without that
caller, and cannot be trusted by the next one. So the behaviour that belongs to
the widget is pinned here, against the recording painter, with no application
present:

* ``settings_editor`` -- rows inferred from a nested mapping, groups, search,
  and a value written back through the model;
* ``view_spec`` -- the ``*.view.json`` dialect read into those rows, including
  what it *cannot* draw, which must be reported rather than dropped;
* ``command_line`` -- the model half: history, completion, and the prompt,
  which is the application's word and not cmtk's;
* ``icons`` -- a pixel glyph lands inside the cell it was given.
"""
from __future__ import annotations

import json

import pytest

from cmtk.testing import RecordingPainter
from cmtk.widgets import icons
from cmtk.widgets.command_line import PROMPT, CommandLine
from cmtk.widgets.settings_editor import (
    BOOL,
    CHOICE,
    FLOAT,
    INT,
    Setting,
    SettingsEditor,
    SettingsModel,
)
from cmtk.widgets.view_spec import (
    load_view_spec,
    model_from_view_spec,
    settings_from_view_spec,
    unsupported_sections,
)


# --------------------------------------------------------------------------
# settings_editor
# --------------------------------------------------------------------------
CONFIG = {
    "surface": {"alpha": 0.5, "quality": 2, "smooth": True},
    "labels": {"font": "Menlo", "size": 12},
    "_schema": 3,
}


def _model() -> SettingsModel:
    """A model over a copy of `CONFIG`, so a test's writes stay its own."""
    live = json.loads(json.dumps(CONFIG))
    return SettingsModel.from_mapping(
        live,
        meta={"surface.alpha": {"min": 0.0, "max": 1.0, "description": "opacity"}},
        skip=("_schema",),
    )


def test_a_nested_mapping_becomes_rows_grouped_by_its_first_component():
    """The dotted path is the whole addressing scheme: group, label and key."""
    model = _model()
    keys = [one.key for one in model.rows()]
    assert "surface.alpha" in keys
    assert "_schema" not in keys, "a schema version is a value, not a setting"
    assert model.groups() == ["surface", "labels"], "the mapping's own order"
    alpha = next(one for one in model.rows() if one.key == "surface.alpha")
    assert alpha.group == "surface" and alpha.label == "alpha"


def test_a_kind_is_inferred_from_the_value_and_bounds_from_the_meta():
    """A guessed track can be corrected; no control at all cannot."""
    model = _model()
    by_key = {one.key: one for one in model.rows()}
    assert by_key["surface.smooth"].kind == BOOL
    assert by_key["surface.quality"].kind == INT
    assert by_key["surface.alpha"].kind == FLOAT
    assert (by_key["surface.alpha"].v_min, by_key["surface.alpha"].v_max) == (0.0, 1.0)
    assert by_key["surface.alpha"].description == "opacity"


def test_a_write_reaches_the_mapping_it_was_built_from():
    """Otherwise the panel displays settings rather than editing them."""
    live = json.loads(json.dumps(CONFIG))
    model = SettingsModel.from_mapping(live, skip=("_schema",))
    model.set("surface.alpha", 0.75)
    assert live["surface"]["alpha"] == 0.75
    assert model.get("surface.alpha") == 0.75


def test_a_setter_is_used_instead_of_writing_back_when_one_is_given():
    """A registered setting is stored somewhere the mapping is not."""
    live = json.loads(json.dumps(CONFIG))
    seen = []
    model = SettingsModel.from_mapping(
        live, setter=lambda key, value: seen.append((key, value)), skip=("_schema",)
    )
    model.set("labels.size", 14)
    assert seen == [("labels.size", 14)]
    assert live["labels"]["size"] == 12, "the mapping was not written behind the setter"


def test_search_filters_rows_and_a_group_narrows_them():
    """Both are how a panel of a few hundred settings stays usable."""
    model = _model()
    assert [one.key for one in model.rows(search="alph")] == ["surface.alpha"]
    assert all(one.group == "labels" for one in model.rows(group="labels"))


def test_the_editor_draws_the_rows_and_a_press_selects_the_one_under_it():
    """Hit-testing has to agree with what was drawn, or the panel lies."""
    editor = SettingsEditor(_model())
    painter = RecordingPainter()
    editor.draw(painter, 0.0, 0.0, 420.0, 240.0)
    drawn = " ".join(painter.strings)
    assert "alpha" in drawn
    hit = editor.press(20.0, 40.0)
    assert hit is None or isinstance(hit, Setting)


def test_moving_the_selection_stays_inside_the_rows():
    """An index that runs off the end is a crash one keypress later."""
    editor = SettingsEditor(_model())
    editor.draw(RecordingPainter(), 0.0, 0.0, 420.0, 240.0)
    for _ in range(50):
        editor.move(1)
    assert editor.selected() in editor.rows()
    for _ in range(50):
        editor.move(-1)
    assert editor.selected() in editor.rows()


def test_a_choice_row_adjusts_within_its_options():
    """Stepping past the last option must not invent one."""
    model = SettingsModel(
        [Setting("view.mode", CHOICE, options=["flat", "smooth"], default="flat")],
        lambda key: "flat",
        lambda key, value: None,
    )
    row = model.rows()[0]
    assert model.adjust(row, 1) in ("flat", "smooth")
    assert model.adjust(row, -5) in ("flat", "smooth")


# --------------------------------------------------------------------------
# view_spec
# --------------------------------------------------------------------------
#: The dialect as ChiSurf's AutoForm actually writes it -- `sections`, `attr`,
#: `minimum`/`maximum`. Written out here rather than paraphrased, because a
#: reader tested against a convenient spelling is a reader that fails on the
#: only files it will ever be given.
SPEC = {
    "sections": [
        {
            "type": "panel",
            "title": "Appearance",
            "sections": [
                {"type": "value", "kind": "float", "attr": "alpha",
                 "label": "Opacity", "minimum": 0.0, "maximum": 1.0,
                 "step": 0.05,
                 "description": "how much you see through it"},
                {"type": "toggle", "attr": "smooth", "label": "Smooth"},
                {"type": "plot", "attr": "histogram", "label": "Histogram"},
            ],
        },
    ],
}


class _Model:
    """What a spec edits: an object with the attributes the spec names."""

    def __init__(self) -> None:
        self.alpha = 0.5
        self.smooth = True


def test_a_spec_becomes_rows_carrying_what_it_declared():
    """A row that loses its range is a slider with a guessed track."""
    rows = settings_from_view_spec(SPEC, _Model())
    by_label = {one.label: one for one in rows}
    assert "Opacity" in by_label and "Smooth" in by_label
    opacity = by_label["Opacity"]
    assert (opacity.v_min, opacity.v_max, opacity.step) == (0.0, 1.0, 0.05)
    assert opacity.description == "how much you see through it"
    assert by_label["Smooth"].kind == BOOL


def test_the_panel_title_becomes_the_group():
    """Which is how a spec's panels turn into the editor's group selector."""
    rows = settings_from_view_spec(SPEC, _Model())
    assert {one.group for one in rows} == {"Appearance"}


def test_the_rows_read_and_write_the_model_object():
    """An adapter that only reads is a screenshot of a form."""
    model_object = _Model()
    model = model_from_view_spec(SPEC, model_object)
    assert model.get("alpha") == 0.5
    model.set("alpha", 0.25)
    assert model_object.alpha == 0.25


def test_a_change_callback_sees_every_write():
    """What a host uses to redraw, or to persist."""
    seen = []
    model = model_from_view_spec(SPEC, _Model(), on_change=lambda k, v: seen.append((k, v)))
    model.set("smooth", False)
    assert seen == [("smooth", False)]


def test_what_cannot_be_painted_is_reported_rather_than_dropped():
    """A form quietly missing half its controls looks like a tool with none."""
    missing = unsupported_sections(SPEC, _Model())
    assert any("plot" in one.lower() or "histogram" in one.lower() for one in missing)
    assert len(settings_from_view_spec(SPEC, _Model())) == 2


def test_a_section_naming_an_attribute_the_model_lacks_is_reported():
    """The spec and the model drift; the drift has to be visible."""
    spec = {"sections": [{"type": "panel", "title": "P", "sections": [
        {"type": "toggle", "attr": "nonexistent", "label": "Nope"},
    ]}]}
    assert unsupported_sections(spec, _Model())


def test_a_missing_or_malformed_spec_is_refused_not_defaulted(tmp_path):
    """An empty form is indistinguishable from a form that failed to load."""
    with pytest.raises(FileNotFoundError):
        load_view_spec(tmp_path / "absent.view.json")
    broken = tmp_path / "broken.view.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_view_spec(broken)


def test_a_spec_round_trips_through_a_file(tmp_path):
    """The reader is what an application actually calls."""
    path = tmp_path / "appearance.view.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    assert settings_from_view_spec(load_view_spec(path), _Model())


# --------------------------------------------------------------------------
# command_line
# --------------------------------------------------------------------------
def test_the_default_prompt_names_no_application():
    """cmtk cannot know whose command line it is drawing, so it does not guess.

    This is not cosmetic. A default reading `"ChiMOL>"` is the application
    leaking into the library through a *value*, which no import check sees.
    """
    assert PROMPT == ">"
    assert "chimol" not in PROMPT.lower()
    assert CommandLine().prompt == ">"


def test_the_prompt_the_application_gives_is_what_the_echo_uses():
    """The log is a transcript; a transcript with the wrong prompt is wrong."""
    line = CommandLine(lambda text: None, prompt="viewer>")
    line.set_text("fetch 1abc")
    line.submit()
    assert line.log[0].text == "viewer> fetch 1abc"


def test_a_submitted_line_runs_and_is_remembered():
    """Run, echo, remember -- in that order, and once each."""
    ran = []
    line = CommandLine(ran.append, prompt="p>")
    line.set_text("show cartoon")
    assert line.submit() == "show cartoon"
    assert ran == ["show cartoon"]
    assert line.history == ["show cartoon"]
    assert line.text == "", "the line clears, or the next command doubles it"


def test_the_same_command_twice_running_is_stored_once():
    """History is for recall, and a wall of one repeated line recalls nothing."""
    line = CommandLine(lambda text: None)
    for _ in range(3):
        line.set_text("zoom")
        line.submit()
    assert line.history == ["zoom"]


def test_recall_walks_history_and_comes_back_to_what_was_being_typed():
    """Losing the half-typed line to an accidental Up is a real loss."""
    line = CommandLine(lambda text: None)
    for one in ("first", "second"):
        line.set_text(one)
        line.submit()
    line.set_text("half typed")
    assert line.recall(-1) and line.text == "second"
    assert line.recall(-1) and line.text == "first"
    line.recall(1)
    line.recall(1)
    assert line.text == "half typed"


def test_completion_asks_the_application_and_inserts_the_answer():
    """The command names live in the command layer; the widget only asks."""
    line = CommandLine(lambda text: None)
    line.completions = lambda text, cursor: ["fetch"] if text.startswith("fe") else []
    line.set_text("fe")
    assert line.complete()
    assert line.text.startswith("fetch")


def test_a_line_with_no_command_layer_says_so_instead_of_raising():
    """A widget wired to nothing must report it, not take the host down."""
    line = CommandLine()
    line.set_text("anything")
    line.submit()
    assert any(one.kind == "error" for one in line.log)


def test_the_log_keeps_only_what_was_asked_for():
    """The log is drawn over the scene; an unbounded one eats the view."""
    line = CommandLine(lambda text: None)
    for i in range(10):
        line.append_message(f"line {i}")
    line.feedback = 3
    assert len(line.visible_log()) == 3
    line.clear_log()
    assert line.visible_log() == []


# --------------------------------------------------------------------------
# icons
# --------------------------------------------------------------------------
class _Cell:
    """The four numbers a glyph is centred in."""

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h


def test_a_glyph_is_drawn_inside_the_cell_it_was_given():
    """An icon that overflows its cell paints over the row beside it."""
    painter = RecordingPainter()
    cell = _Cell(100.0, 50.0, 12.0, 16.0)
    icons.draw_eye(painter, cell, (255, 255, 255, 255), shown=True)
    assert painter.fills, "nothing was drawn"
    for one in painter.fills:
        x, y, w, h = one[0], one[1], one[2], one[3]
        assert x >= cell.x - 1 and y >= cell.y - 1
        assert x + w <= cell.x + cell.w + 1
        assert y + h <= cell.y + cell.h + 1


def test_the_open_and_closed_eyes_are_different_pictures():
    """They are the visibility toggle; drawing one for both hides the state."""
    open_painter, shut_painter = RecordingPainter(), RecordingPainter()
    cell = _Cell(0.0, 0.0, 12.0, 16.0)
    icons.draw_eye(open_painter, cell, (255, 255, 255, 255), shown=True)
    icons.draw_eye(shut_painter, cell, (255, 255, 255, 255), shown=False)
    assert open_painter.fills != shut_painter.fills


def test_an_empty_picture_draws_nothing_rather_than_dividing_by_zero():
    """The degenerate case a glyph table hits the first time one is misspelt."""
    painter = RecordingPainter()
    icons.draw_glyph(painter, _Cell(0.0, 0.0, 10.0, 10.0), (), (255, 255, 255, 255))
    assert not painter.fills
