"""emtk stands on its own: its code, its tests, its examples.

    It is its own project now (``~/dev/emtk``), which is what these checks were
    for all along -- they held the separation while it still lived inside a
    molecular viewer, and they are what made moving it out a rename rather than
    an excavation.

A widget toolkit that can only be built, run and tested inside the application
it grew in is not a toolkit -- it is that application's drawing code with an
optimistic directory name. And the point of emtk is the opposite: Dear ImGui
code should port into it, on any painter, without bringing a molecular viewer
along.

So this file pins the separation in all three directions:

* **the code** -- ``import emtk`` pulls in no other part of chimol;
* **the tests** -- everything in ``tests/emtk`` imports only ``emtk``,
  and runs without a viewer, a host, a toolkit or chisurf;
* **the examples** -- each one runs, on a painter that draws to nothing.

Whichever of those slips first, the others follow: a test that reaches for the
viewer is a licence for the code to do the same next week.
"""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EMTK = ROOT / "emtk"
TESTS = ROOT / "tests"
EXAMPLES = ROOT / "examples"

#: What emtk must not reach for. It is a toolkit: a painter, some geometry,
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
    """Statically: no module under `emtk/` names another part of chimol."""
    offenders = {}
    for path in sorted(EMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        bad = sorted(
            name for name in _imports(path)
            if name.startswith("chimol.") and not name.startswith("emtk")
        )
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, offenders


def test_the_prose_names_no_application_either():
    """Docstrings must not cross-reference an application's modules.

    A `:mod:`chimol.render.pack`` in a emtk docstring is a dangling link the
    moment emtk is read on its own, and it is the same rot as an import: the
    library describing itself in terms of one caller. The provenance line in
    `emtk/__init__.py` is the single allowed mention, and it is a URL, not a
    cross-reference.

    Case-insensitively, because the first thing this caught was a prompt
    string reading `"ChiMOL>"` -- a *default value* naming the application,
    which a case-sensitive check walks straight past. A widget that knows the
    program's name is a widget the next program cannot use unchanged.
    """
    offenders = {}
    for path in sorted(EMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hits = [
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if "chimol" in line.lower() and "github.com/tpeulen/chimol" not in line
        ]
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, offenders


def test_importing_it_pulls_in_nothing_else():
    """And at run time, which is the half a static check cannot see."""
    code = (
        "import sys, emtk, emtk.im; "
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
        "import sys; import emtk.im as im; import emtk.widgets.tables; "
        "print([m for m in sys.modules "
        "if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6','qtpy',"
        "'wgpu','rendercanvas','numpy')])"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]", out.stdout


#: Blocks every toolkit import for the interpreter it is prepended to, so
#: "emtk does not need Qt" is tested on a machine where Qt is *absent*
#: rather than merely on one where it happens not to be installed. The two
#: look identical until someone adds a lazy `import qtpy` inside a function.
_NO_TOOLKIT = """
import sys
class _Blocked:
    def find_module(self, name, path=None):
        if name.split('.')[0] in %r:
            return self
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in %r:
            raise ImportError('blocked for this test: ' + name)
    def load_module(self, name):
        raise ImportError('blocked for this test: ' + name)
sys.meta_path.insert(0, _Blocked())
""" % (FOREIGN, FOREIGN)


def _without_toolkit(body: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _NO_TOOLKIT + body],
                          cwd=ROOT, capture_output=True, text=True)


def test_it_draws_a_frame_with_every_toolkit_blocked():
    """The whole of it -- import, lay out, draw, encode -- on an interpreter
    where importing Qt *raises*.

    The checks above ask whether a toolkit ended up in ``sys.modules``, which
    on a machine that has none is a question that answers itself. This one
    makes the answer mean something: a lazy ``import qtpy`` inside a function
    passes those and fails this.
    """
    out = _without_toolkit("""
import emtk
from emtk.testing import PixelPainter, save_png
io, storage = emtk.IO(), {}
p = PixelPainter(200, 80, background=(30, 32, 38, 255))
with emtk.frame(p, (4, 4, 192, 72), io=io, storage=storage):
    emtk.begin("w")
    emtk.text("no toolkit here")
    emtk.button("ok")
    emtk.end()
lit = sum(1 for i in range(0, len(p.px), 4) if p.px[i] > 60)
print("lit", lit)
""")
    assert out.returncode == 0, out.stderr[-3000:]
    assert int(out.stdout.split()[1]) > 0, "drew nothing"


def test_the_plotting_layer_needs_no_toolkit_either():
    """``emtk.implot`` is the newest module and the one most likely to reach
    for a plotting library. It may not."""
    out = _without_toolkit("""
import emtk
from emtk import implot
from emtk.testing import PixelPainter
io, storage = emtk.IO(), {}
p = PixelPainter(240, 160, background=(30, 32, 38, 255))
with emtk.frame(p, (4, 4, 232, 152), io=io, storage=storage):
    emtk.begin("w")
    implot.begin_plot("t", (-1, 100))
    implot.setup_axes("x", "y")
    implot.plot_line("a", [0, 1, 2], [1.0, 3.0, 2.0])
    implot.end_plot()
    emtk.end()
print("ok")
""")
    assert out.returncode == 0, out.stderr[-3000:]
    assert out.stdout.strip() == "ok"


def test_the_qt_modules_are_the_only_ones_that_may_name_a_toolkit():
    """``qt_host``, ``qt_painter`` and ``wgpu_host`` are optional adapters:
    they exist to be imported *by* a Qt program, and nothing in emtk imports
    them. Any fourth module naming Qt would put the toolkit back on the
    critical path.

    ``wgpu_host`` is the one that has to be argued for, because it is the
    module that asks Qt for the *least*: a **window**, and nothing else.
    ``rendercanvas`` turns that into a surface, the drawing happens in
    ``wgsl/ui.wgsl``, and the geometry comes from
    :mod:`emtk.quad_painter` like any other consumer's. It names a toolkit
    for the same reason the other two do -- somebody has to open the window
    -- and, like them, it imports it inside the function that builds the
    class rather than at module scope.

    Note what is *not* on this list: :mod:`emtk.gpu_atlas` holds what a host
    uploads -- the combined glyph atlas, the image atlas, the negative-u
    encoding -- and names no toolkit at all. It reaches Qt's PNG decoder
    through ``qt_painter`` when there is one and falls back to the
    pure-Python decoder when there is not, so the GPU conventions stay
    testable on a machine with no toolkit installed.
    """
    naming = set()
    for path in sorted(EMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if any(mod.split(".")[0] in ("qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6")
               for mod in _imports(path)):
            naming.add(path.name)
    assert naming <= {"qt_host.py", "qt_painter.py", "wgpu_host.py"}, naming


def test_the_suite_itself_runs_without_a_qt_binding():
    """The suite is part of the claim. A test file that asks for a fixture
    only a Qt plugin supplies makes every *other* test unrunnable without
    Qt -- a collection error, not a skip.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(TESTS)],
        cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, (out.stdout + out.stderr)[-3000:]
    # the summary line, not the word anywhere: a test *named* for an error
    # is not an error
    import re as _re
    assert not _re.search(r"^\d+ errors?\b|\b\d+ errors? in ",
                          out.stdout, _re.M), out.stdout[-3000:]
    assert _re.search(r"\d+ tests? collected", out.stdout), out.stdout[-2000:]


# --------------------------------------------------------------------------- #
# The tests
# --------------------------------------------------------------------------- #
#: An optional backend a *test* may import, because testing the Qt painter
#: needs Qt. The library itself may not -- `test_it_needs_no_toolkit` is what
#: says so, and it launches a fresh interpreter to prove it.
OPTIONAL_IN_TESTS = ("numpy", "qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6")


def test_the_suite_reaches_for_no_application():
    """A test may exercise an optional backend; none may need an application.

    The distinction is the whole separation: emtk's tests must run in a
    checkout of emtk with nothing else present. A test that imports the viewer
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


#: Seconds an example gets. Each draws a frame or two; one still running after
#: this is waiting for a user who is not there.
EXAMPLE_TIMEOUT = 120


@pytest.mark.parametrize("example", [p.name for p in _examples()])
def test_every_example_runs(example):
    """Run it. An example that does not run is documentation that is wrong.

    Headless: an example that opens a window (``emtk.native``) would otherwise
    get a real one wherever glfw and a display are there, and pump its loop
    until somebody closes it -- the run never returns. On the offscreen canvas
    the native host draws one frame and exits, which is what is checked here.
    """
    env = {**os.environ, "EMTK_CANVAS": "offscreen"}
    out = subprocess.run([sys.executable, str(EXAMPLES / example)], cwd=ROOT,
                         capture_output=True, text=True, env=env,
                         timeout=EXAMPLE_TIMEOUT)
    if out.returncode != 0 and (
        "No module named 'wgpu'" in out.stderr
        or "No module named 'rendercanvas'" in out.stderr
        or "Request adapter failed" in out.stderr
        or "No suitable graphics adapter found" in out.stderr
    ):
        pytest.skip(f"optional dependency / GPU adapter not available for {example}")
    assert out.returncode == 0, out.stderr[-3000:]


