"""A change to emtk's public API comes with a new ``__version__``.

Applications pin emtk by version: ChiSurf refuses to start on an emtk older
than the minimum it names. emtk once added ``DockWindow(workspace=...)`` while
``__version__`` still said ``0.1.8``; an installed emtk without the keyword
passed ChiSurf's check and the window crashed with a ``TypeError``.

``tests/api_fingerprint.json`` records the public API (read from the source by
``tools/api_fingerprint.py``) together with the version it belongs to. This
test fails when the API moved and the version did not -- the message says to
bump ``__version__`` and re-record -- and when the version moved and the
snapshot was not re-recorded. The recorder itself refuses to re-record a
changed API under an unchanged version, so the drift cannot be papered over.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import api_fingerprint  # noqa: E402


def test_the_public_api_and_version_agree_with_the_snapshot():
    problems = api_fingerprint.check()
    assert not problems, "\n\n".join(problems)


def test_a_new_keyword_is_an_api_change(tmp_path):
    """The case that broke ChiSurf: a constructor gains a keyword."""
    before = tmp_path / "before.py"
    after = tmp_path / "after.py"
    before.write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\nclass DockWindow:\n    key: str\n    closable: bool = True\n"
        "def open_window(key, *, dock=None):\n    pass\n"
    )
    after.write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\nclass DockWindow:\n    key: str\n    closable: bool = True\n"
        "    workspace: bool = False\n"
        "def open_window(key, *, dock=None, workspace=False):\n    pass\n"
    )
    old = {"m": api_fingerprint.module_api(before)}
    new = {"m": api_fingerprint.module_api(after)}
    assert api_fingerprint.digest(old) != api_fingerprint.digest(new)
    assert api_fingerprint.changes(old, new) == ["~ m.DockWindow", "~ m.open_window"]


def test_formatting_and_private_names_are_not_api_changes(tmp_path):
    before = tmp_path / "before.py"
    after = tmp_path / "after.py"
    before.write_text("def f(a, b=1):\n    return a\n")
    after.write_text(
        "def f(a,\n      b = 1) -> int:\n    '''Now documented.'''\n    return a + 0\n"
        "def _helper(x):\n    pass\n"
    )
    assert api_fingerprint.module_api(before) == api_fingerprint.module_api(after)


def test_the_recorder_refuses_a_changed_api_under_the_same_version(tmp_path, monkeypatch):
    snapshot = tmp_path / "api_fingerprint.json"
    api = api_fingerprint.current_api()
    version = api_fingerprint.package_version()
    stale = {"m": {"f": "def(a)"}}
    snapshot.write_text(
        __import__("json").dumps(
            {"version": version, "sha256": api_fingerprint.digest(stale), "api": stale}
        )
    )
    monkeypatch.setattr(api_fingerprint, "SNAPSHOT", snapshot)
    assert api_fingerprint.record() == 1
    assert api_fingerprint.load_snapshot()["api"] == stale, "the snapshot was left alone"
    problems = api_fingerprint.check()
    assert any("bump" in problem and version in problem for problem in problems), problems
    assert api != stale
