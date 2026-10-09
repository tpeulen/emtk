"""Declared section help reaches real caption/table hovers without changing layout."""

from __future__ import annotations

import copy

import pytest
from emtk import i18n, im
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form

DESCRIPTION = "Section help explains the measured rows and their units."
TRANSLATED = "Aide de section pour les lignes mesurées et leurs unités."
HEADER_HELP = "Specific name column help."
ROW_HELP = "Specific first row help."
LONG_VALUE = "The complete cell text must remain available when its column is narrow."


def table_spec(dialect, *, description=DESCRIPTION):
    """Declare the same records in each supported AutoForm table dialect."""
    options = {
        "source": "rows", "height": 150, "tooltip_key": "note",
        "columns": [{"key": "name", "title": "Name", "width": 100,
                     "tooltip": HEADER_HELP},
                    {"key": "value", "title": "Value", "width": 80}],
    }
    if dialect == "custom":
        return {"type": "custom", "key": "data_table", "title": "Records",
                "description": description, "options": options}
    return {"type": "table", "description": description, **options}


def spec_for(kind, *, description=DESCRIPTION):
    """Build existing caption variants followed by an unrelated control."""
    field = {"type": "toggle", "attr": "enabled", "label": "Enabled"}
    if kind == "panel":
        section = {"type": "panel", "title": "Section caption",
                   "description": description, "sections": [field]}
    elif kind == "tabs":
        section = {"type": "tabs", "title": "Section caption", "name": "pages",
                   "description": description, "sections": [
                       {"type": "panel", "name": "first", "title": "First page",
                        "sections": [field]}]}
    else:
        section = table_spec(kind, description=description)
    return {"sections": [section, {"type": "button_row", "buttons": [
        {"label": "Finish", "action": "finish"}]}]}


class FormApp(ImApp):
    """Drive the owning form renderer through its ordinary immediate-mode window."""

    def __init__(self, spec, *, titles=True):
        self.spec = copy.deepcopy(spec)
        self.titles = titles
        self.form = FormState()
        self.enabled = True
        self.rows = [{"name": "first", "value": 1, "note": ROW_HELP},
                     {"name": "second", "value": 2, "note": ""},
                     {"name": LONG_VALUE, "value": 3, "note": "Row help below cell help."}]
        self.context = None
        super().__init__(self.gui)
        self.io.wall_clock = False

    def finish(self):
        """Expose the following button without changing the fixture."""

    def gui(self):
        """Render the actual form and retain its frame context for tooltip assertions."""
        im.begin("Form", im.get_current_context().box)
        draw_form(self.spec, self, self.form, titles=self.titles)
        self.context = im.get_current_context()
        im.end()


def hover_and_wait(driver, target):
    """Move the actual pointer, then allow the normal tooltip timer to paint help."""
    driver.hover(target)
    driver.app.io.now += 1.0
    painter = driver.frame(2)
    assert driver.app.context.box_tooltip is not None
    return " ".join(painter.strings)


@pytest.mark.parametrize("kind", ["panel", "tabs", "custom"])
def test_existing_caption_help_waits_then_paints_and_leaves(kind):
    """Existing captions expose descriptions after the delay, without leaking help."""
    app = FormApp(spec_for(kind))
    driver = Driver(app, (640, 400))
    driver.frame(2)
    caption = "Records" if kind == "custom" else "Section caption"
    painter = driver.hover(caption)
    assert app.context.tooltip == DESCRIPTION
    assert app.context.box_tooltip is None
    assert DESCRIPTION not in " ".join(painter.strings)
    assert DESCRIPTION in hover_and_wait(driver, caption)
    assert app.context.tooltip == DESCRIPTION
    painter = driver.hover("Finish")
    assert app.context.tooltip is None and app.context.box_tooltip is None
    assert DESCRIPTION not in " ".join(painter.strings)


@pytest.mark.parametrize("dialect", ["table", "custom"])
@pytest.mark.parametrize("width", [640, 320])
def test_table_section_fallback_preserves_specific_help(dialect, width):
    """Specific header, row and elided-cell help wins; otherwise section help is painted."""
    app = FormApp(spec_for(dialect))
    driver = Driver(app, (width, 400))
    driver.frame(2)
    table = app.form.tables["rows"].control
    hx, hy, _, hh = table._header_box
    bx, by, _, _ = table._body_box
    row_h = table._row_h
    assert HEADER_HELP in hover_and_wait(driver, (hx + 10, hy + hh / 2))
    assert app.context.tooltip == HEADER_HELP
    assert ROW_HELP in hover_and_wait(driver, (bx + 10, by + row_h / 2))
    assert app.context.tooltip == ROW_HELP
    assert LONG_VALUE in hover_and_wait(driver, (bx + 10, by + row_h * 2.5))
    assert app.context.tooltip == LONG_VALUE
    assert DESCRIPTION in hover_and_wait(driver, (bx + 10, by + row_h * 1.5))
    owner = app.context.tooltip_owner
    assert DESCRIPTION in hover_and_wait(driver, (bx + 10, by + row_h * 3.5))
    assert app.context.tooltip_owner == owner
    assert DESCRIPTION in hover_and_wait(driver, (hx + table._widths[0] + 10, hy + hh / 2))
    driver.hover("Finish")
    assert app.context.tooltip is None


@pytest.mark.parametrize("dialect", ["table", "custom"])
def test_empty_table_uses_section_help_without_inventing_missing_descriptions(dialect):
    """The real empty table remains helpful only when its section declares help."""
    for description in (DESCRIPTION, ""):
        app = FormApp(spec_for(dialect, description=description))
        app.rows = []
        driver = Driver(app, (320, 400))
        driver.frame(2)
        x, y, _, _ = app.form.tables["rows"].control._body_box
        driver.hover((x + 10, y + 10))
        app.io.now += 1.0
        painter = driver.frame(2)
        if description:
            assert app.context.tooltip == description
            assert DESCRIPTION in " ".join(painter.strings)
        else:
            assert app.context.tooltip is None and app.context.box_tooltip is None


@pytest.mark.parametrize("kind", ["panel", "tabs", "custom", "table"])
def test_section_help_uses_existing_translation_path(kind):
    """Both caption and table fallback descriptions use the active locale."""
    previous = i18n.get_locale()
    i18n.add_translations("section-help-test", {DESCRIPTION: TRANSLATED})
    try:
        i18n.set_locale("section-help-test")
        app = FormApp(spec_for(kind))
        driver = Driver(app, (640, 400))
        driver.frame(2)
        if kind in {"panel", "tabs"}:
            target = "Section caption"
        else:
            x, y, _, _ = app.form.tables["rows"].control._body_box
            target = (x + 10, y + app.form.tables["rows"].control._row_h * 3.5)
        assert TRANSLATED in hover_and_wait(driver, target)
        assert app.context.tooltip == TRANSLATED
    finally:
        i18n.set_locale(previous)


@pytest.mark.parametrize("kind", ["panel", "tabs", "custom", "table"])
@pytest.mark.parametrize("width", [640, 320])
def test_descriptions_do_not_change_geometry_or_unhovered_paint(kind, width):
    """Metadata help adds neither a visible control nor a new layout row at either width."""
    frames = []
    for description in ("", DESCRIPTION):
        app = FormApp(spec_for(kind, description=description))
        driver = Driver(app, (width, 400))
        painter = driver.frame(2)
        tables = {name: (table.control._header_box, table.control._body_box,
                         tuple(table.control._widths), table.control._row_h)
                  for name, table in app.form.tables.items()}
        frames.append((dict(app.form.rects), tables, painter.calls))
    assert frames[0] == frames[1]


def test_suppressed_panel_caption_does_not_invent_child_help():
    """A host suppressing captions remains responsible for the missing hover target."""
    app = FormApp(spec_for("panel"), titles=False)
    driver = Driver(app, (640, 400))
    driver.frame(2)
    driver.hover("enabled")
    assert app.context.tooltip is None
