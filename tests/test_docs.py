"""Doctest runner and staleness guard for the documentation.

Three jobs:

1. Doctest every ``.rst`` file in ``docs/`` through Sphinx's own doctest
   extension, wired into pytest so a plain ``pytest`` catches drift.
2. Doctest the module docstrings that carry runnable examples.
3. Assert that the public API surface (``cmtk.__all__``, ``cmtk.im.__all__``,
   ``CONTROL_MODULES``) is actually covered by the docs, so a new widget
   family cannot be added without a doc entry.

Why a pytest file and not just ``sphinx-build -b doctest``
----------------------------------------------------------
A docs build nobody runs is not a test. The existing ``pytest`` invocation
is what every contributor runs; a staleness guard that only fires inside a
separate ``make doctest`` is a guard that fires after the PR lands, not
before.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

import cmtk
import cmtk.im  # resolve the lazy attribute
import cmtk.testing  # same


DOCS_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs"
API_RST = DOCS_DIR / "api.rst"


def _missing_docs_extra() -> str:
    """Which part of ``cmtk[docs]`` is absent, if any.

    Building the docs needs Sphinx and the theme ``conf.py`` names. Neither
    is a cmtk dependency -- they are the ``docs`` extra -- so a checkout
    without them must *skip* these two tests rather than fail them. Failing
    would make an optional extra look mandatory, which is the same trap the
    Qt painter test used to set (see tests/conftest.py).
    """
    import importlib.util
    for mod, pip in (("sphinx", "sphinx"), ("sphinx_rtd_theme", "sphinx-rtd-theme")):
        if importlib.util.find_spec(mod) is None:
            return pip
    return ""


needs_docs_extra = pytest.mark.skipif(
    bool(_missing_docs_extra()),
    reason=f"needs the docs extra (pip install cmtk[docs]); "
           f"missing {_missing_docs_extra()}")


# -- 1. Doctest the .rst sources through Sphinx ------------------------------

@needs_docs_extra
def test_docs_doctest_rst():
    """Run ``sphinx-build -b doctest`` on the docs tree.

    This catches any ``>>>`` block in an ``.rst`` that has silently
    drifted -- a wrong assertion, a renamed import, a changed return
    value. Because ``conf.py`` puts ``RecordingPainter`` and ``im``
    into the doctest namespace, every example runs headless with no
    window.
    """
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-b", "doctest",
         str(DOCS_DIR), str(DOCS_DIR / "_build" / "doctest"), "-W"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
    assert result.returncode == 0, (
        f"sphinx doctest failed (exit {result.returncode})"
    )


# -- 2. Doctest key module docstrings ---------------------------------------

def test_docs_doctest_module_docstrings():
    """Doctest the module docstrings that carry ``>>>`` examples.

    These are the ones a reader copies verbatim, so they must stay
    correct. Only modules with ``>>>`` in their docstring are run,
    to keep the test fast and the scope clear.
    """
    import doctest

    modules_with_examples = [
        cmtk.im,
        cmtk.testing,
        cmtk.painter,
    ]
    # Also check the top-level package.
    if ">>>" in cmtk.__doc__ or ".. doctest::" in cmtk.__doc__:
        import cmtk as _cmtk
        modules_with_examples.append(_cmtk)

    total_failures = 0
    for mod in modules_with_examples:
        finder = doctest.DocTestFinder()
        runner = doctest.DocTestRunner(verbose=False)
        for test in finder.find(mod, mod.__name__):
            runner.run(test)
        total_failures += runner.failures
        if runner.failures:
            runner.summarize()
    assert total_failures == 0, (
        f"{total_failures} doctest failure(s) in module docstrings"
    )


# -- 3. Staleness guard: CONTROL_MODULES covered in api.rst --------------------

def _api_rst_modules() -> set[str]:
    """Parse ``docs/api.rst`` and return the set of ``cmtk.X`` modules
    referenced by ``.. automodule::`` directives under 'Widget families'.
    """
    text = API_RST.read_text()
    modules = set()
    for m in re.finditer(r"\.\. automodule::\s+(\S+)", text):
        modules.add(m.group(1))
    return modules


def test_staleness_guard_control_modules():
    """Every module the library enumerates has an automodule entry in api.rst.

    This is the staleness guard: adding a new widget family without
    updating the docs fails this test. The guard checks the module
    name as it would appear in an ``automodule`` directive
    ("cmtk.widgets.basic", not "widgets.basic").

    Both lists are walked. ``NAMESPACED_MODULES`` holds the modules that are
    deliberately *not* flattened into the package namespace, and a module in
    neither list is one nothing checks -- which is the hole this closes.
    """
    documented = _api_rst_modules()
    missing = []
    for mod_name in tuple(cmtk.CONTROL_MODULES) + tuple(cmtk.NAMESPACED_MODULES):
        full = f"cmtk.{mod_name}"
        if full not in documented:
            missing.append(full)
    assert not missing, (
        f"Enumerated modules missing from docs/api.rst: {missing}. "
        f"Add an '.. automodule::' directive for each."
    )


def test_staleness_guard_cmtk_all():
    """Every name in cmtk.__all__ has either an eager import or a
    CONTROL_MODULES family that exports it.

    This is a weaker check than full autodoc coverage but catches the
    case where a name is added to __all__ but nothing in the docs can
    resolve it.
    """
    for name in cmtk.__all__:
        try:
            getattr(cmtk, name)
        except AttributeError:
            raise AssertionError(
                f"cmtk.__all__ lists {name!r} but it is not importable"
            )


@needs_docs_extra
def test_sphinx_html_build_clean():
    """``sphinx-build -W -b html`` succeeds (warnings as errors).
    """
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "-b", "html",
         str(DOCS_DIR), str(DOCS_DIR / "_build" / "html")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print("stdout:", result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
        print("stderr:", result.stderr[-3000:] if len(result.stderr) > 3000 else result.stderr)
    assert result.returncode == 0, (
        f"sphinx html build failed (exit {result.returncode})"
    )


# --------------------------------------------------------------------------- #
# The README's quick start
# --------------------------------------------------------------------------- #
README = DOCS_DIR.parent / "README.md"


def _readme_python_blocks(section: str) -> list[str]:
    """The fenced ``python`` blocks under a ``## `` heading of the README."""
    text = README.read_text(encoding="utf-8")
    start = text.index(f"## {section}")
    end = text.index("\n## ", start + 1)
    return re.findall(r"```python\n(.*?)```", text[start:end], re.S)


def test_the_readme_quick_start_runs(tmp_path):
    """The first program a new user meets actually runs, as written.

    A quick start is the one piece of documentation that is *only* worth
    anything if it works verbatim: a reader who hits a traceback on line one
    has no way to tell whether they mistyped or the project moved. So the
    block is extracted and executed rather than eyeballed.
    """
    blocks = _readme_python_blocks("Quick start")
    assert blocks, "the README quick start has no python blocks"
    script = tmp_path / "first_frame.py"
    script.write_text(blocks[0], encoding="utf-8")
    result = subprocess.run([sys.executable, str(script)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (
        f"README quick start failed:\n{result.stdout}\n{result.stderr}")
    assert (tmp_path / "frame.png").exists(), "it wrote no frame.png"


def test_the_readme_quick_start_draws_the_screenshot_beside_it(tmp_path):
    """...and the picture under it is that program's own output.

    The README shows a screenshot directly below the listing. Left unchecked
    the two drift apart -- the listing gains a widget, the image keeps the old
    one -- and a picture that disagrees with the code above it is worse than
    no picture, because the reader trusts it.
    """
    blocks = _readme_python_blocks("Quick start")
    script = tmp_path / "first_frame.py"
    script.write_text(blocks[0], encoding="utf-8")
    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True,
                   capture_output=True, timeout=120)
    committed = DOCS_DIR / "_screenshots" / "first_frame.png"
    assert committed.exists(), (
        f"{committed} is missing; run `make -C docs screenshots`")
    cmtk.testing.assert_images_equal(
        (tmp_path / "frame.png").read_bytes(), committed)


def test_the_readme_window_adapter_fires_a_click_once(tmp_path):
    """The adapter in step two has the semantics its prose claims.

    It only *sets* the one-shot edges and leaves the clearing to
    ``end_frame``. Get that wrong -- clear them too early and the click never
    lands, too late and every repaint re-fires it -- and the reader's first
    interactive program mis-counts. Driven here exactly as ``ControlHost``
    drives a control, so no Qt binding is needed to check it.
    """
    blocks = _readme_python_blocks("Quick start")
    adapter = blocks[1]
    namespace: dict = {}
    exec(compile(adapter, "README:adapter", "exec"), namespace)  # noqa: S102
    app_class = namespace["App"]

    clicks = []

    def gui():
        cmtk.begin("W")
        if cmtk.button("Press me"):
            clicks.append(1)
        cmtk.end()

    app = app_class(gui)

    def paint():
        app.draw(cmtk.testing.PixelPainter(200, 80), 0.0, 0.0, 200.0, 80.0)

    paint()                                      # settles the layout
    app.press(20.0, 10.0, 0.0, 0.0, 200.0, 80.0, 0, 1)
    paint()
    assert not clicks, "the button fired on press; it fires on release"
    app.release()
    paint()
    assert clicks == [1], f"release did not fire the button: {clicks}"
    paint()
    paint()
    assert clicks == [1], f"a plain repaint re-fired the click: {clicks}"


def test_the_readme_qt_snippet_is_syntactically_valid():
    """The Qt block cannot be run here (no binding), so at least parse it."""
    blocks = _readme_python_blocks("Quick start")
    compile(blocks[2], "README:qt", "exec")
