"""cmtk stands on its own: its code, its tests, its examples.

    It is its own project now (``~/dev/cmtk``), which is what these checks were
    for all along -- they held the separation while it still lived inside a
    molecular viewer, and they are what made moving it out a rename rather than
    an excavation.

A widget toolkit that can only be built, run and tested inside the application
it grew in is not a toolkit -- it is that application's drawing code with an
optimistic directory name. And the point of cmtk is the opposite: Dear ImGui
code should port into it, on any painter, without bringing a molecular viewer
along.

So this file pins the separation in all three directions:

* **the code** -- ``import cmtk`` pulls in no other part of chimol;
* **the tests** -- everything in ``tests/cmtk`` imports only ``cmtk``,
  and runs without a viewer, a host, a toolkit or chisurf;
* **the examples** -- each one runs, on a painter that draws to nothing.

Whichever of those slips first, the others follow: a test that reaches for the
viewer is a licence for the code to do the same next week.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CMTK = ROOT / "cmtk"
TESTS = ROOT / "tests"
EXAMPLES = ROOT / "examples"

#: What cmtk must not reach for. It is a toolkit: a painter, some geometry,
#: and the standard library.
FOREIGN = ("chimol", "chisurf", "numpy", "qtpy", "PyQt5", "PyQt6", "PySide2",
           "PySide6", "wgpu", "rendercanvas")


def _imports(path: pathlib.Path) -> set[str]:
    """Every module a file imports, as dotted names."""
    tree = ast.parse(path.read_text(errors="ignore"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # relative: resolve against the file
                base = path.relative_to(ROOT).parent.as_posix().replace("/", ".")
                parts = base.split(".")
                up = parts[: len(parts) - node.level + 1]
                found.add(".".join([*up, node.module or ""]).strip("."))
            elif node.module:
                found.add(node.module)
    return found


# --------------------------------------------------------------------------- #
# The code
# --------------------------------------------------------------------------- #
def test_the_library_imports_nothing_else_from_chimol():
    """Statically: no module under `cmtk/` names another part of chimol."""
    offenders = {}
    for path in sorted(CMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        bad = sorted(
            name for name in _imports(path)
            if name.startswith("chimol.") and not name.startswith("cmtk")
        )
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, offenders


def test_the_prose_names_no_application_either():
    """Docstrings must not cross-reference an application's modules.

    A `:mod:`chimol.render.pack`` in a cmtk docstring is a dangling link the
    moment cmtk is read on its own, and it is the same rot as an import: the
    library describing itself in terms of one caller. The provenance line in
    `cmtk/__init__.py` is the single allowed mention, and it is a URL, not a
    cross-reference.

    Case-insensitively, because the first thing this caught was a prompt
    string reading `"ChiMOL>"` -- a *default value* naming the application,
    which a case-sensitive check walks straight past. A widget that knows the
    program's name is a widget the next program cannot use unchanged.
    """
    offenders = {}
    for path in sorted(CMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hits = [
            line.strip()
            for line in path.read_text().splitlines()
            if "chimol" in line.lower() and "github.com/tpeulen/chimol" not in line
        ]
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, offenders


def test_importing_it_pulls_in_nothing_else():
    """And at run time, which is the half a static check cannot see."""
    code = (
        "import sys, cmtk, cmtk.im; "
        "print(sorted({m.split('.')[0] for m in sys.modules "
        "if m.split('.')[0] in %r}))" % (FOREIGN,)
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]", out.stdout


def test_it_needs_no_toolkit():
    """No Qt, no rendercanvas, no wgpu -- it is a painter and some geometry."""
    code = (
        "import sys; import cmtk.im as im; import cmtk.widgets.tables; "
        "print([m for m in sys.modules "
        "if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6','qtpy',"
        "'wgpu','rendercanvas','numpy')])"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]", out.stdout


# --------------------------------------------------------------------------- #
# The tests
# --------------------------------------------------------------------------- #
#: An optional backend a *test* may import, because testing the Qt painter
#: needs Qt. The library itself may not -- `test_it_needs_no_toolkit` is what
#: says so, and it launches a fresh interpreter to prove it.
OPTIONAL_IN_TESTS = ("numpy", "qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6")


def test_the_suite_reaches_for_no_application():
    """A test may exercise an optional backend; none may need an application.

    The distinction is the whole separation: cmtk's tests must run in a
    checkout of cmtk with nothing else present. A test that imports the viewer
    it grew in is a licence for the code to do the same next week.
    """
    offenders = {}
    for path in sorted(TESTS.glob("*.py")):
        bad = sorted(
            name for name in _imports(path)
            if name.split(".")[0] in ("chimol", "chisurf", "toolkit_free")
        )
        if bad:
            offenders[path.name] = bad
    assert not offenders, offenders


def test_the_suite_is_not_empty():
    """A separation that holds because there is nothing left proves nothing."""
    files = [p for p in TESTS.glob("test_*.py")]
    assert len(files) >= 15, [p.name for p in files]


# --------------------------------------------------------------------------- #
# The examples
# --------------------------------------------------------------------------- #
def _examples() -> list[pathlib.Path]:
    return sorted(EXAMPLES.glob("*.py")) if EXAMPLES.exists() else []


def test_there_are_examples():
    assert _examples(), f"no examples under {EXAMPLES}"


@pytest.mark.parametrize("example", [p.name for p in _examples()])
def test_every_example_runs(example):
    """Run it. An example that does not run is documentation that is wrong."""
    out = subprocess.run([sys.executable, str(EXAMPLES / example)], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-3000:]
