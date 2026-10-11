"""The shared translation seam: domains, catalogues, fallback, extraction, guard."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from emtk import i18n
from emtk.i18n import catalogue, extract
from emtk.i18n.testing import untranslated_literals

TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="de">
<context>
    <name>app</name>
    <message>
        <location filename="app/x.py" line="3"/>
        <source>Open</source>
        <translation>Öffnen</translation>
    </message>
    <message>
        <source>Draft</source>
        <translation type="unfinished">Entwurf</translation>
    </message>
    <message>
        <source>Gone</source>
        <translation type="obsolete">Weg</translation>
    </message>
    <message numerus="yes">
        <source>%n files</source>
        <translation><numerusform>%n Datei</numerusform><numerusform>%n Dateien</numerusform></translation>
    </message>
    <message>
        <source>Shortcut: {key}</source>
        <translation>Tastenkürzel: {key}</translation>
    </message>
</context>
<context>
    <name>status</name>
    <message>
        <source>Open</source>
        <translation>Offen</translation>
    </message>
</context>
</TS>
"""


@pytest.fixture(autouse=True)
def _isolated():
    previous = i18n.language()
    yield
    for name in ("app", "other", "mapdomain", "jsondomain"):
        i18n.remove_catalogue(name)
    i18n.set_default_domain(None)
    i18n.set_language(previous)


@pytest.fixture
def app_catalogue(tmp_path):
    (tmp_path / "app_de.ts").write_text(TS, encoding="utf-8")
    i18n.add_catalogue("app", tmp_path)
    return tmp_path


def test_ts_parsing_keeps_only_finished_singular_translations(app_catalogue):
    table = catalogue.read_catalogue(app_catalogue / "app_de.ts")
    assert table["app"] == {"Open": "Öffnen", "Shortcut: {key}": "Tastenkürzel: {key}"}
    assert table["status"] == {"Open": "Offen"}
    language, messages = catalogue.read_messages(app_catalogue / "app_de.ts")
    assert language == "de"
    assert {m.source: m.status for m in messages}["Gone"] == "obsolete"
    assert [m.numerus for m in messages if m.source == "%n files"] == [True]


def test_tr_domain_context_and_placeholders(app_catalogue):
    i18n.set_language("de")
    assert i18n.tr("Open", domain="app") == "Öffnen"
    assert i18n.tr("Open", domain="app", context="status") == "Offen"
    assert i18n.tr("Open", domain="app", context="nowhere") == "Öffnen"
    assert i18n.tr("Draft", domain="app") == "Draft"          # unfinished: not shown
    assert i18n.tr("Gone", domain="app") == "Gone"            # obsolete: not shown
    assert i18n.tr("Shortcut: {key}", domain="app").format(key="F1") == "Tastenkürzel: F1"
    assert i18n.tr("Never heard of it", domain="app") == "Never heard of it"
    assert i18n.tr("Open") == "Öffnen"                         # no domain: every domain
    i18n.set_language("en")
    assert i18n.tr("Open", domain="app") == "Open"


def test_fallback_chain_domain_then_emtk_then_source(tmp_path):
    i18n.add_catalogue("app", {"de": {"Local": "Lokal"}})
    i18n.set_language("de")
    assert i18n.tr("Local", domain="app") == "Lokal"
    assert i18n.tr("Cancel", domain="app") == "Abbrechen"      # emtk's own catalogue
    assert i18n.tr("Cancel", domain="emtk") == "Abbrechen"
    assert i18n.tr("Local", domain="other") == "Local"         # not another app's
    assert i18n.tr("Absent", domain="app") == "Absent"
    i18n.set_language("fr")
    assert i18n.tr("Cancel", domain="app") == "Annuler"


def test_regional_language_falls_back_to_base(app_catalogue):
    i18n.set_language("de_CH.UTF-8")
    assert i18n.language() == "de-ch"
    assert i18n.tr("Open", domain="app") == "Öffnen"


def test_generation_bumps_on_language_and_catalogue_changes(tmp_path):
    i18n.set_language("en")
    start = i18n.generation()
    i18n.set_language("en")
    assert i18n.generation() == start                          # no change, no bump
    i18n.set_language("de")
    assert i18n.generation() > start
    before = i18n.generation()
    i18n.add_catalogue("app", {"de": {"New": "Neu"}})
    assert i18n.generation() > before
    assert i18n.tr("New", domain="app") == "Neu"


def test_json_catalogues_flat_and_with_contexts(tmp_path):
    (tmp_path / "de.json").write_text(json.dumps({"Plain": "Schlicht",
                                                  "ctx": {"Nested": "Verschachtelt"}}))
    (tmp_path / "jsondomain_fr.json").write_text(json.dumps(
        {"language": "fr", "messages": {"jsondomain": {"Plain": "Simple", "Todo": ""}}}))
    i18n.add_catalogue("jsondomain", tmp_path)
    i18n.set_language("de")
    assert i18n.tr("Plain", domain="jsondomain") == "Schlicht"
    assert i18n.tr("Nested", domain="jsondomain", context="ctx") == "Verschachtelt"
    i18n.set_language("fr")
    assert i18n.tr("Plain", domain="jsondomain") == "Simple"
    assert i18n.tr("Todo", domain="jsondomain") == "Todo"
    assert {"de", "fr"} <= set(i18n.available_languages("jsondomain"))


def test_catalogue_is_parsed_lazily_and_once(app_catalogue, monkeypatch):
    calls = []
    real = catalogue.read_catalogue
    monkeypatch.setattr(catalogue, "read_catalogue", lambda p: calls.append(p) or real(p))
    i18n.add_catalogue("app", app_catalogue)                   # same dir: no-op
    i18n.set_language("fr")
    i18n.tr("Open", domain="app")
    assert calls == []                                         # no French file: nothing parsed
    i18n.set_language("de")
    i18n.tr("Open", domain="app")
    i18n.tr("Shortcut: {key}", domain="app")
    assert len(calls) == 1


def test_default_language_from_env(monkeypatch):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EMTK_LANG", "fr_FR")
    assert i18n._detect_language() == "fr-fr"
    monkeypatch.delenv("EMTK_LANG")
    monkeypatch.setenv("LANG", "C")
    assert i18n._detect_language() == "en"


def test_mark_is_identity_and_legacy_api_still_works():
    assert i18n.mark("Later") == "Later"
    i18n.add_translations("de", {"Legacy": "Altlast"})
    i18n.add_translations("de", {"Legacy": "Erbe"}, context="status")
    i18n.set_locale("de")
    assert i18n.get_locale() == "de"
    assert i18n.tr("Legacy") == "Altlast"
    assert i18n.tr("Legacy", "status") == "Erbe"
    assert i18n.tr("Legacy", domain="app") == "Altlast"


def test_emtk_catalogues_ship_de_and_fr():
    assert {"de", "fr"} <= set(i18n.available_languages("emtk"))
    for code in ("de", "fr"):
        table = catalogue.read_catalogue(i18n.catalogue_directory() / f"emtk_{code}.ts")
        assert len(table.get("emtk", {})) >= 20


def test_emtk_catalogues_cover_every_builtin_string(tmp_path):
    """Every tr(..., domain="emtk") literal in the toolkit has a finished de and fr entry."""
    from pathlib import Path

    package = Path(i18n.__file__).resolve().parents[1]
    wanted = {source for context, source in extract.collect(package, "emtk")
              if context == "emtk"}
    assert wanted
    for code in ("de", "fr"):
        table = catalogue.read_catalogue(i18n.catalogue_directory() / f"emtk_{code}.ts")
        missing = wanted - set(table.get("emtk", {}))
        assert not missing, f"{code}: {sorted(missing)}"


# --------------------------------------------------------------------- extraction


def _package(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "gui").mkdir(parents=True)
    (pkg / "tests").mkdir()
    (pkg / "gui" / "app.py").write_text(textwrap.dedent('''
        from emtk import i18n
        from emtk.i18n import tr, mark
        LABELS = [mark("Later")]
        def draw(im):
            im.button(tr("Open"))
            im.text(tr("Loaded {n} files").format(n=3))
            im.text(i18n.tr("Status", context="bar"))
            im.text(tr("Toolkit", domain="emtk"))
            im.text(tr(dynamic))
        '''))
    (pkg / "tests" / "test_x.py").write_text('tr("Test only")\n')
    (pkg / "gui" / "view.json").write_text(json.dumps({
        "sections": [{"type": "choice", "attr": "mode", "label": "Mode",
                      "options": [["fast", "Fast mode"]], "description": "How to run"}]}))
    (pkg / "setup_guide.json").write_text(json.dumps({"steps": [{"title": "Step one",
                                                                 "text": "Press it"}]}))
    return pkg


def test_collect_python_and_specs(tmp_path):
    found = extract.collect(_package(tmp_path), "pkg")
    keys = set(found)
    assert {("pkg", "Open"), ("pkg", "Later"), ("pkg", "Loaded {n} files"), ("bar", "Status"), ("pkg", "Mode"),
            ("pkg", "Fast mode"), ("pkg", "How to run"), ("pkg", "Step one"),
            ("pkg", "Press it")} <= keys
    sources = {s for _, s in keys}
    assert not {"Toolkit", "Test only", "mode", "fast"} & sources
    assert found[("pkg", "Open")][0][0] == "pkg/gui/app.py"


def test_extract_merges_without_losing_translations(tmp_path):
    pkg = _package(tmp_path)
    out = tmp_path / "i18n"
    out.mkdir()
    existing = [
        catalogue.Message("pkg", "Open", "Öffnen", ""),
        catalogue.Message("pkg", "Mode", "Modus (Entwurf)", "unfinished"),
        catalogue.Message("pkg", "Removed", "Entfernt", ""),
        catalogue.Message("Form", "Qt form text", "Qt-Text", ""),   # foreign context
        catalogue.Message("old", "Status", "Zustand", ""),          # context moved
    ]
    catalogue.write_messages(out / "pkg_de.ts", existing, "de")
    extract.extract(pkg, "pkg", ["de", "fr"], out)
    _, merged = catalogue.read_messages(out / "pkg_de.ts")
    by = {(m.context, m.source): m for m in merged}
    assert (by[("pkg", "Open")].translation, by[("pkg", "Open")].status) == ("Öffnen", "")
    assert by[("pkg", "Mode")].translation == "Modus (Entwurf)"
    assert by[("pkg", "Mode")].status == "unfinished"
    assert (by[("pkg", "Removed")].status, by[("pkg", "Removed")].translation) == \
        ("obsolete", "Entfernt")
    assert by[("Form", "Qt form text")].status == ""
    assert by[("bar", "Status")].translation == "Zustand"
    assert by[("pkg", "Later")].status == "unfinished"
    assert by[("pkg", "Open")].locations == [("pkg/gui/app.py", 6)]
    # A string that comes back is restored with its translation.
    (pkg / "gui" / "more.py").write_text('from emtk.i18n import tr\ntr("Removed")\n')
    extract.extract(pkg, "pkg", ["de"], out)
    _, again = catalogue.read_messages(out / "pkg_de.ts")
    restored = {(m.context, m.source): m for m in again}[("pkg", "Removed")]
    assert (restored.status, restored.translation) == ("", "Entfernt")
    # The merged catalogue is still a runtime catalogue.
    i18n.add_catalogue("other", out)
    i18n.set_language("de")
    assert i18n.tr("Open", domain="other") == "Öffnen"
    assert (out / "pkg_fr.ts").is_file()


def test_extract_json_format_round_trips(tmp_path):
    pkg = _package(tmp_path)
    extract.extract(pkg, "pkg", ["de"], tmp_path / "out", fmt="json")
    data = json.loads((tmp_path / "out" / "pkg_de.json").read_text())
    assert data["messages"]["pkg"]["Open"] == ""
    data["messages"]["pkg"]["Open"] = "Öffnen"
    (tmp_path / "out" / "pkg_de.json").write_text(json.dumps(data))
    extract.extract(pkg, "pkg", ["de"], tmp_path / "out", fmt="json")
    data = json.loads((tmp_path / "out" / "pkg_de.json").read_text())
    assert data["messages"]["pkg"]["Open"] == "Öffnen"


def test_extra_specs_collect_declared_keys_of_app_data(tmp_path):
    pkg = _package(tmp_path)
    (pkg / "ui" / "data").mkdir(parents=True)
    (pkg / "ui" / "data" / "menus.json").write_text(json.dumps(
        {"menu_bar": [{"label": "File", "id": "file", "note": "File things"}]}))
    (pkg / "data" / "tours").mkdir(parents=True)
    (pkg / "data" / "tours" / "a.json").write_text(json.dumps([{"say": "Hello", "id": "x"}]))
    (pkg / "data" / "tours" / "b.json").write_text(json.dumps([{"say": "Bye"}]))
    found = extract.collect(pkg, "pkg", extra_specs={
        "ui/data/menus.json": ("label", "note"), "data/tours/*.json": ("say",)})
    sources = {s for _, s in found}
    assert {"File", "File things", "Hello", "Bye"} <= sources
    assert not {"file", "x"} & sources
    with pytest.raises(ValueError, match="matches no file"):
        extract.collect(pkg, "pkg", extra_specs={"nothing/*.json": ("say",)})
    assert extract.parse_spec_args(["data/tours/*.json:say", "ui/data/menus.json:label,note"]) \
        == {"data/tours/*.json": ("say",), "ui/data/menus.json": ("label", "note")}
    with pytest.raises(ValueError):
        extract.parse_spec_args(["no-keys"])


def test_docstrings_of_decorated_functions(tmp_path):
    pkg = _package(tmp_path)
    (pkg / "commands.py").write_text(textwrap.dedent('''
        @command
        def color(sel):
            """Colour a selection.

            Long help that is not a summary.
            """

        @command("hide")
        def hide():
            """Hide atoms."""

        @registry.command(name="x")
        async def zoom():
            """  Zoom the view.  """

        @other
        def private():
            """Not a command."""

        @command
        def undocumented():
            pass
        '''))
    found = extract.collect(pkg, "pkg", docstrings_of=("command",))
    sources = {s for _, s in found}
    assert {"Colour a selection.", "Hide atoms.", "Zoom the view."} <= sources
    assert "Not a command." not in sources and "Long help that is not a summary." not in sources
    assert "Hide atoms." not in {s for _, s in extract.collect(pkg, "pkg")}


def test_cli(tmp_path):
    pkg = _package(tmp_path)
    (pkg / "menus.json").write_text(json.dumps({"items": [{"prompt": "Ask me"}]}))
    (pkg / "cmd.py").write_text('@command\ndef f():\n    """Do f."""\n')
    out = tmp_path / "out"
    result = subprocess.run([sys.executable, "-m", "emtk.i18n.extract", str(pkg), "--domain",
                             "pkg", "--locales", "de", "fr", "--out", str(out),
                             "--spec", "menus.json:prompt", "--docstrings", "command"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    sources = {m.source for m in catalogue.read_messages(out / "pkg_fr.ts")[1]}
    assert {"Open", "Ask me", "Do f."} <= sources


# --------------------------------------------------------------------- guard


def test_untranslated_literals_guard(tmp_path):
    pkg = tmp_path / "guarded"
    pkg.mkdir()
    (pkg / "ui.py").write_text(textwrap.dedent('''
        from emtk import im as widgets
        from emtk.i18n import tr
        widgets.button("Run")
        widgets.button(tr("Fine"))
        widgets.text("##hidden")
        widgets.text("123.4")
        widgets.input_text("##f", v, hint="Name")
        ctx.set_tooltip("Bare tooltip")
        model.text("Data")
        widgets.button("Save##doc")
        widgets.text(f"Loaded {n} files")
        widgets.text(f"{a}/{b}")
        widgets.text(tr("Loaded {n} files").format(n=n))
        '''))
    (pkg / "test_ui.py").write_text('im.button("Ignored")\n')
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "draw.py").write_text('self.label("Hi")\np.label(f"N={n} atoms")\nq.label("No")\n')
    assert [f.text for f in untranslated_literals(custom, sinks={"label": 0},
                                                  receivers={"self", "p", "painter"})] \
        == ["Hi", "N={n} atoms"]
    found = untranslated_literals(pkg)
    assert [f.text for f in found] == ["Run", "Bare tooltip", "Save##doc", "Loaded {n} files"]
    assert found[0].key.startswith("guarded/ui.py:4:")
    (pkg / "broken.py").write_text("def broken(:\n")
    with pytest.raises(SyntaxError):
        untranslated_literals(pkg)


def test_emtk_builtin_widgets_have_no_untranslated_literals():
    from pathlib import Path

    package = Path(i18n.__file__).resolve().parents[1]
    found = untranslated_literals(package, exclude=("implot_demo", "implot3d_demo"))
    assert found == [], "\n".join(f.key for f in found)


def test_use_domain_puts_the_drawing_apps_catalogue_first():
    i18n.add_catalogue("app", {"de": {"Run": "Starten"}})
    i18n.add_catalogue("other", {"de": {"Run": "Laufen"}})
    i18n.set_language("de")
    assert i18n.tr("Run") == "Starten"                         # registration order
    with i18n.use_domain("other"):
        assert i18n.tr("Run") == "Laufen"
        assert i18n.tr("Run", domain="app") == "Starten"       # an explicit domain wins
        assert i18n.tr("Cancel") == "Abbrechen"
    assert i18n.tr("Run") == "Starten"
