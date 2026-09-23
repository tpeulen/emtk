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
