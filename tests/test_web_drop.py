"""A dropped folder reaches the app whole, as one path.

A browser hands a dropped folder over as a ``FileSystemDirectoryEntry``; its
``File`` in ``dataTransfer.files`` has size 0 and no readable bytes. A page that
reads only ``files`` therefore cannot open a burst-analysis folder, the thing
ndXplorer is dropped most. ``boot.js``'s ``copyDropped`` walks the entry into
Pyodide's filesystem; this runs that very block of ``boot.js`` under node
against stand-ins for the entry API and ``pyodide.FS``, including the part that
is easy to get wrong: ``readEntries`` returns a directory in *batches* and one
call reads only the first.
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

HARNESS = r"""
%(block)s

// A FileSystemEntry tree: {name: bytes-as-string | {subtree}}.
function entry(name, value, batch) {
  if (typeof value === "string") {
    const file = { name, arrayBuffer: async () => new TextEncoder().encode(value).buffer };
    return { name, isFile: true, isDirectory: false, file: (ok) => ok(file) };
  }
  const children = Object.entries(value).map(([n, v]) => entry(n, v, batch));
  return {
    name, isFile: false, isDirectory: true,
    createReader() {
      let at = 0;
      return { readEntries(ok) { const out = children.slice(at, at + batch); at += out.length; ok(out); } };
    },
  };
}

const written = {};
const dirs = new Set();
const FS = {
  mkdirTree: (p) => dirs.add(p),
  writeFile: (p, bytes) => { written[p] = new TextDecoder().decode(bytes); },
};

(async () => {
  const tree = %(tree)s;
  const folder = await copyDropped(entry("burst#30", tree, 2), "/mnt/dropped", FS);
  const plain = { name: "one.bur", arrayBuffer: async () => new TextEncoder().encode("x").buffer };
  const file = await copyDropped(plain, "/mnt/dropped", FS);
  console.log(JSON.stringify({ folder, file, written, dirs: [...dirs].sort() }));
})();
"""


def _block() -> str:
    text = (WEB / "boot.js").read_text(encoding="utf-8")
    match = re.search(r"// <copy-dropped>.*?// </copy-dropped>", text, re.S)
    assert match, "boot.js lost its copy-dropped block"
    return match.group(0)


def test_a_dropped_folder_is_copied_whole_and_opened_as_one_path(tmp_path):
    tree = {"Info": {"a.txt": "info"},
            "bi4_bur": {f"m{i:03d}_0.bur": f"bur{i}" for i in range(5)},
            "bg4": {"m000_0.bg4": "bg"}}
    script = tmp_path / "drop.js"
    script.write_text(HARNESS % {"block": _block(), "tree": json.dumps(tree)})
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True,
                                    check=True, timeout=60).stdout)
    assert out["folder"] == "/mnt/dropped/burst#30", "the app gets the folder, not its files"
    assert out["file"] == "/mnt/dropped/one.bur"
    root = "/mnt/dropped/burst#30"
    # Five files in batches of two: all five, not the first batch.
    for i in range(5):
        assert out["written"][f"{root}/bi4_bur/m{i:03d}_0.bur"] == f"bur{i}"
    assert out["written"][f"{root}/Info/a.txt"] == "info"
    assert out["written"][f"{root}/bg4/m000_0.bg4"] == "bg"
    assert f"{root}/bi4_bur" in out["dirs"]
    assert len(out["written"]) == 8


def test_the_drop_handler_takes_entries_before_it_awaits():
    """``dataTransfer.items`` is emptied at the handler's first ``await``, so the
    entries must be taken before one -- else every drop reads as empty."""
    text = (WEB / "boot.js").read_text(encoding="utf-8")
    handler = text[text.index('addEventListener("drop"'):]
    handler = handler[:handler.index("});")]
    handler = "\n".join(line for line in handler.splitlines()
                        if not line.lstrip().startswith("//"))
    assert "webkitGetAsEntry" in handler
    assert handler.index("webkitGetAsEntry") < handler.index("await")
    assert "copyDropped(" in handler


BY_REFERENCE = r"""
%(block)s

const written = {};
const FS = { mkdirTree: () => {}, writeFile: (p, bytes) => { written[p] = bytes.length; } };
const big = { name: "big.ptu", size: 5000, arrayBuffer: async () => { throw new Error("read the big file"); } };
const small = { name: "small.ptu", size: 10, arrayBuffer: async () => new Uint8Array(10).buffer };
(async () => {
  const a = await copyDropped(big, "/mnt/dropped", FS, 1000);
  const b = await copyDropped(small, "/mnt/dropped", FS, 1000);
  console.log(JSON.stringify({ a, b, written, handles: Object.keys(globalThis.emtkDroppedFiles),
                               byref: globalThis.emtkDroppedByReference }));
})();
"""


def test_a_large_drop_is_kept_by_reference_when_the_app_asks(tmp_path):
    """Above the app's limit the page keeps only the File handle and an empty
    placeholder; smaller files are copied as before; both handles are kept."""
    script = tmp_path / "byref.js"
    script.write_text(BY_REFERENCE % {"block": _block()})
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True,
                                    check=True).stdout)
    assert out["written"] == {"/mnt/dropped/big.ptu": 0, "/mnt/dropped/small.ptu": 10}
    assert sorted(out["handles"]) == ["/mnt/dropped/big.ptu", "/mnt/dropped/small.ptu"]
    assert out["byref"] == {"/mnt/dropped/big.ptu": 5000}


def test_the_page_config_carries_the_limit():
    bundle = serve.Bundle(app="emtk.implot_demo:make_app", drop_by_reference_above=123)
    assert serve._config(bundle, [])["drop_by_reference_above"] == 123
    assert serve._config(serve.Bundle(app="emtk.implot_demo:make_app"), [])["drop_by_reference_above"] == 0


def test_dropped_by_reference_reads_the_page_table():
    from types import SimpleNamespace

    from emtk.web.page import dropped_by_reference

    js = SimpleNamespace(emtkDroppedByReference=SimpleNamespace(**{"/mnt/dropped/big.ptu": 5000}))
    assert dropped_by_reference("/mnt/dropped/big.ptu", js=js) == 5000
    assert dropped_by_reference("/mnt/dropped/other.ptu", js=js) is None
    assert dropped_by_reference("/x") is None          # not a page
