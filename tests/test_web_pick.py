"""The file dialog's "Load from computer…" moves real bytes and real state.

A user who has dropped nothing and mounted nothing used to face an empty
virtual filesystem: the page's files were the only way in, and the file
dialog had none. ``boot.js``'s picker opens the browser's own file sheet,
writes what was chosen into Pyodide's filesystem and reports it through
``__emtkPicked``; this runs that very block of ``boot.js`` under node
against stand-ins for ``document`` and ``pyodide.FS``, then the Python side
of the handshake in ``emtk.web.page`` against a stand-in ``js`` module.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from emtk.web import serve

WEB = pathlib.Path(serve.__file__).parent

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

BLOCK = re.search(
    r"// <copy-picked>.*?// </copy-picked>", (WEB / "boot.js").read_text(), re.S
).group(0)


def run_node(script: str) -> dict:
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


HARNESS = r"""
%(block)s

// A stand-in pyodide.FS that records what was written.
const written = {};
const FS = {
  mkdirTree: () => {},
  writeFile: (path, bytes) => { written[path] = Array.from(bytes); },
};

// A stand-in document whose input fires change (or cancel) on click.
const listeners = {};
const input = {
  type: "", multiple: false, accept: undefined, style: {},
  files: [],
  addEventListener: (kind, fn) => { listeners[kind] = fn; },
  click: () => {}, remove: () => {},
};
globalThis.document = {
  createElement: () => input,
  body: { appendChild: () => {} },
};
globalThis.emtkDroppedFiles = null;

const file = (name, text) => ({
  name, arrayBuffer: async () => new TextEncoder().encode(text).buffer,
});

(async () => {
  // 1. copyPicked writes every chosen file under the dir and keeps a handle.
  const names = await copyPicked([file("a.csv", "x,y\n1,2\n"), file("b.csv", "3,4\n")],
                                 "/mnt/user-files", FS);
  // 2. installPicker wires the global; a click arms the sheet.
  installPicker({ FS }, "/mnt/user-files");
  const idle = JSON.stringify(globalThis.__emtkPicked);
  globalThis.emtkPickLocalFiles(".csv .dat");
  const accept = input.accept, multiple = input.multiple;
  const waiting = JSON.stringify(globalThis.__emtkPicked);
  // 3. The user chooses: the files land in the FS and the state names them.
  input.files = [file("picked.csv", "5,6\n")];
  await listeners.change();
  const done = JSON.stringify(globalThis.__emtkPicked);
  // 4. The user cancels instead: the state says so, nothing is written.
  globalThis.emtkPickLocalFiles();
  input.files = [];
  listeners.cancel();
  const cancel = JSON.stringify(globalThis.__emtkPicked);
  const filesBefore = Object.keys(globalThis.emtkDroppedFiles).length;
  console.log(JSON.stringify({ names, idle, accept, multiple, waiting, done, cancel,
                               written, filesBefore }));
})();
"""


def test_the_picker_writes_the_chosen_files_and_reports_them():
    """copyPicked lands every file under the pick dir; the state machine holds."""
    report = run_node(HARNESS % {"block": BLOCK})
    assert report["names"] == ["a.csv", "b.csv"]
    assert report["written"]["/mnt/user-files/a.csv"] == [120, 44, 121, 10, 49, 44, 50, 10]
    assert report["idle"] == '{"state":"idle"}'
    assert report["accept"] == ".csv .dat"
    assert report["multiple"] is True
    assert report["waiting"] == '{"state":"waiting"}'
    assert json.loads(report["done"]) == {
        "state": "done", "dir": "/mnt/user-files", "names": ["picked.csv"]}
    assert report["written"]["/mnt/user-files/picked.csv"] == [53, 44, 54, 10]
    assert json.loads(report["cancel"]) == {"state": "cancel"}
    # a handle for the by-reference job path survives the copies
    assert report["filesBefore"] == 3


def test_the_page_bridge_reads_the_state_the_picker_left():
    """start_local_pick calls the installed picker; local_pick_result converts."""
    import types

    from emtk.web import page as web_page

    calls = []
    window = types.SimpleNamespace(
        __emtkPicked=None,
        emtkPickLocalFiles=lambda accept: calls.append(accept),
    )
    js = types.SimpleNamespace(window=window)
    fake_js = types.ModuleType("js")
    fake_js.window = window
    monkey = pytest.MonkeyPatch()
    monkey.setitem(__import__("sys").modules, "js", fake_js)
    try:
        monkey.setattr(web_page, "ON_PAGE", True)
        assert web_page.start_local_pick(".csv") is True
        assert calls == [".csv"]
        assert web_page.local_pick_result() in (None, "waiting")
        window.__emtkPicked = types.SimpleNamespace(
            state="done", dir="/mnt/user-files", names=["x.csv"])
        # names arrives as a JsProxy in the page; .to_py() is emulated
        class _Arr(types.SimpleNamespace):
            def to_py(self):
                return ["x.csv"]
        window.__emtkPicked.names = _Arr()
        assert web_page.local_pick_result() == ("/mnt/user-files", ["x.csv"])
        window.__emtkPicked = types.SimpleNamespace(state="cancel")
        assert web_page.local_pick_result() == "cancel"
        window.__emtkPicked = types.SimpleNamespace(state="error", message="boom")
        assert web_page.local_pick_result() == "error: boom"
    finally:
        monkey.undo()
    assert js  # the namespace was used only through the injected module
