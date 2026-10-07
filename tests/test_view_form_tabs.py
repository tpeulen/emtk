"""Semantic form tabs preserve models while showing only their selected body."""
from types import SimpleNamespace

from emtk import im, keys
from emtk.app import ImApp
from emtk.testing import Driver
from emtk.view_form import FormState, draw_form


def spec(key="parameters"):
    """Return three ordinary AutoForm pages with explicit identities and help."""
    return {"sections": [{"type": "tabs", "key": key, "sections": [
        {"type": "tab", "key": "decay", "title": "Decay", "description": "Lifetime settings.",
         "sections": [{"type": "value", "attr": "lifetime", "label": "Lifetime", "kind": "float",
                       "description": "Decay time in nanoseconds."}]},
        {"type": "tab", "key": "rates", "title": "Rates", "description": "Photon rate settings.",
         "sections": [{"type": "value", "attr": "rate", "label": "Count rate", "kind": "int",
                       "description": "Photon rate in kilohertz."}]},
        {"type": "tab", "key": "preview", "title": "Preview", "description": "Current sampled decay.",
         "sections": [{"type": "info", "text": "Computed preview"}]},
    ]}]}


class FormApp(ImApp):
    """Host only the existing spec renderer and expose its real guide targets."""
    def __init__(self, specification=None, state=None):
        self.spec = specification or spec()
        self.state = state or FormState()
        self.model = SimpleNamespace(lifetime=3.5, rate=25)
        super().__init__(self.gui)

    @property
    def item_rects(self):
        """Return rectangles recorded by the form itself."""
        return self.state.rects

    def gui(self):
        """Draw in a stable window identity so reopened form state is comparable."""
        im.begin("Scientific form", (0, 0, 640, 400))
        draw_form(self.spec, self.model, self.state)
        self.nav_ids = list(im.get_current_context().nav_ring)
        self.tooltip = im.get_current_context().tooltip
        im.end()


def form(specification=None, state=None):
    """Build and settle one toolkit-free form."""
    app = FormApp(specification, state)
    driver = Driver(app, (640, 400))
    driver.frame(3)
    return app, driver


def test_only_active_tab_children_draw():
    app, driver = form()
    assert "Lifetime" in driver.painter.strings
    assert "Count rate" not in driver.painter.strings
    assert "Computed preview" not in driver.painter.strings
    assert "parameters.decay" in app.state.rects
    assert "parameters.rates" in app.state.rects


def test_real_click_switches_tabs_and_header_targets_remain_headers():
    app, driver = form()
    first = app.state.rects["parameters.decay"]
    second = app.state.rects["parameters.rates"]
    assert first[1] == second[1]
    assert second[0] > first[0] + first[2]
    driver.click("parameters.rates")
    assert "Count rate" in driver.painter.strings
    assert "Lifetime" not in driver.painter.strings
    assert app.model.lifetime == 3.5 and app.model.rate == 25
    assert "lifetime" not in app.state.rects
    driver.click("parameters.decay")
    assert "Lifetime" in driver.painter.strings


def test_keyboard_focus_and_activation_switch_the_real_tab():
    app, driver = form()
    driver.press(keys.KEY_TAB)
    driver.press(keys.KEY_TAB)
    driver.press(keys.KEY_RETURN)
    assert "Count rate" in driver.painter.strings
    assert "Lifetime" not in driver.painter.strings
    assert app.model.lifetime == 3.5 and app.model.rate == 25


def test_selected_tab_reopens_with_the_same_form_state():
    app, driver = form()
    driver.click("parameters.rates")
    reopened, driver = form(state=app.state)
    assert "Count rate" in driver.painter.strings
    assert "Lifetime" not in driver.painter.strings
    assert reopened.model.rate == 25


def test_separate_tab_bars_have_independent_selected_pages():
    specification = {"sections": [*spec("first")["sections"], *spec("second")["sections"]]}
    app, driver = form(specification)
    driver.click("second.rates")
    assert app.state.rects["first.decay"][1] < app.state.rects["second.decay"][1]
    assert "Lifetime" in driver.painter.strings and "Count rate" in driver.painter.strings
    driver.click("first.preview")
    assert "Computed preview" in driver.painter.strings and "Count rate" in driver.painter.strings


def test_identical_field_names_in_tabs_have_different_engine_ids():
    specification = spec()
    specification["sections"][0]["sections"][1]["sections"] = [
        {"type": "value", "attr": "lifetime", "label": "Lifetime", "kind": "float",
         "description": "The same model value on a different page."}]
    app, driver = form(specification)
    ids_before = {item for item in app.nav_ids if item[-1] == "lifetime"}
    driver.click("parameters.rates")
    ids_after = {item for item in app.nav_ids if item[-1] == "lifetime"}
    assert ids_before and ids_after and ids_before.isdisjoint(ids_after)
    assert app.model.lifetime == 3.5


def test_ordinary_panel_titles_and_layout_survive_nested_tabs():
    specification = {"sections": [{"type": "panel", "title": "Simulation", "sections": [
        *spec()["sections"], {"type": "info", "text": "After tabs"}]}]}
    app, driver = form(specification)
    assert "Simulation" in driver.painter.strings
    assert "After tabs" in driver.painter.strings
    positions = {text[5]: text[1] for text in driver.painter.texts}
    assert positions["After tabs"] > positions["Lifetime"]


def test_edited_fields_survive_switching_and_usage_reports_the_header():
    app, driver = form()
    used = []
    app.state.on_used = used.append
    driver.click("lifetime")
    driver.type("8.25")
    driver.press(keys.KEY_RETURN)
    driver.click("parameters.rates")
    driver.click("rate")
    driver.type("70")
    driver.press(keys.KEY_RETURN)
    driver.click("parameters.decay")
    assert app.model.lifetime == 8.25 and app.model.rate == 70
    assert "8.25" in driver.painter.strings
    assert "parameters.rates" in used and "parameters.decay" in used


def test_hidden_active_page_selects_visible_page_and_retires_targets():
    specification = spec()
    rates = specification["sections"][0]["sections"][1]
    rates["hidden_when"] = {"attr": "hide_rates", "equals": True}
    app, driver = form(specification)
    driver.click("parameters.rates")
    app.model.hide_rates = True
    driver.frame(2)
    assert "Count rate" not in driver.painter.strings
    assert "Lifetime" in driver.painter.strings
    assert "parameters.rates" not in app.state.rects
    assert "rate" not in app.state.rects


def test_translated_headers_keep_stable_targets_and_selected_page():
    from emtk import i18n

    locale = i18n.get_locale()
    i18n.add_translations("form-tabs-test", {"Rates": "Raten", "Decay": "Zerfall"})
    try:
        app, driver = form()
        driver.click("parameters.rates")
        i18n.set_locale("form-tabs-test")
        driver.frame(2)
        assert "Raten" in driver.painter.strings and "Zerfall" in driver.painter.strings
        assert "Count rate" in driver.painter.strings
        driver.click("parameters.decay")
        assert "Lifetime" in driver.painter.strings
    finally:
        i18n.set_locale(locale)


def test_same_named_bars_use_structural_scope_for_independent_widgets():
    specification = {"sections": [*spec()["sections"], *spec()["sections"]]}
    app, driver = form(specification)
    decay_ids = [item for item in app.nav_ids if item[-1] == "decay"]
    assert len(decay_ids) == 2 and len(set(decay_ids)) == 2
    driver.click("Rates")  # The first caption, rather than a duplicate guide key.
    assert "Count rate" in driver.painter.strings and "Lifetime" in driver.painter.strings


def test_title_only_specs_have_reachable_header_targets():
    specification = spec()
    bar = specification["sections"][0]
    bar.pop("key")
    bar["title"] = "Simulation"
    for child in bar["sections"]:
        child.pop("key")
    app, driver = form(specification)
    driver.click("Simulation.Preview")
    assert "Computed preview" in driver.painter.strings
    assert "Lifetime" not in driver.painter.strings


def test_header_help_uses_the_header_rectangle_and_translation():
    from emtk import i18n

    locale = i18n.get_locale()
    i18n.add_translations("form-tabs-help", {"Photon rate settings.": "Rate help translated"})
    try:
        app, driver = form()
        i18n.set_locale("form-tabs-help")
        driver.hover("parameters.rates")
        assert app.tooltip == "Rate help translated"
        assert "Count rate" not in driver.painter.strings
    finally:
        i18n.set_locale(locale)


def test_switching_commits_typed_value_before_preview_and_calls_once():
    specification = spec()
    value = specification["sections"][0]["sections"][0]["sections"][0]
    value["call"] = "changed"
    app, driver = form(specification)
    changes = []
    app.model.changed = changes.append
    seen = []
    app.spec["sections"][0]["sections"][2]["sections"].append(
        {"type": "custom", "key": "preview", "description": "Read the committed lifetime."})
    app.state.custom["preview"] = lambda *_: seen.append(app.model.lifetime)
    driver.click("lifetime")
    driver.type("8.25")
    assert app.model.lifetime == 3.5
    driver.click("parameters.preview")
    assert app.model.lifetime == 8.25
    assert seen and all(value == 8.25 for value in seen)
    driver.frame(3)
    assert changes == [8.25]
    assert "lifetime" not in app.state.buffers


def test_switch_commit_keeps_invalid_numeric_text_from_changing_model():
    app, driver = form()
    changes = []
    app.spec["sections"][0]["sections"][0]["sections"][0]["call"] = "changed"
    app.model.changed = changes.append
    driver.click("lifetime")
    driver.type("invalid")
    driver.click("parameters.preview")
    assert app.model.lifetime == 3.5
    assert changes == []
    assert "lifetime" not in app.state.buffers  # Same rejection as click-away in a panel.


def test_switch_commit_uses_runtime_bounds_and_only_the_page_being_left():
    specification = spec()
    value = specification["sections"][0]["sections"][0]["sections"][0]
    value["call"] = "changed"
    app, driver = form(specification)
    app.model.limit = 6.0
    app.model.bounds = lambda name: (0, app.model.limit) if name == "lifetime" else None
    changes = []
    app.model.changed = changes.append
    app.state.buffers["rate"] = "80"  # Pending field on an inactive page is not committed.
    driver.click("lifetime")
    driver.type("90")
    driver.click("parameters.preview")
    assert app.model.lifetime == 6.0 and changes == [6.0]
    assert app.model.rate == 25 and app.state.buffers["rate"] == "80"
