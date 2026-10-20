"""Execute the real loader with a shared runtime and DOM stand-ins."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

from emtk.web import serve

HARNESS = r"""
const calls = [];
const elements = {};
const targets = () => ({
  listeners: {},
  addEventListener(name, fn) { this.listeners[name] = fn; },
});
const canvas = Object.assign(targets(), {
  clientWidth: 320, clientHeight: 200, width: 0, height: 0,
  getBoundingClientRect: () => ({left: 0, top: 0}),
  setPointerCapture() {}, hasPointerCapture: () => false,
  releasePointerCapture() {}, classList: {add() {}, remove() {}},
});
elements.view = canvas;
elements['emtk-config'] = {textContent: JSON.stringify({
  app: 'example:app', archive: 'app.zip', extract_dir: '/app', drop: false, mount: false,
})};
elements.status = {textContent: ''};
globalThis.document = Object.assign(targets(), {
  getElementById: name => elements[name] || null, title: '',
});
globalThis.window = Object.assign(targets(), {devicePixelRatio: 2});
Object.defineProperty(globalThis, 'navigator', {value: {gpu: {}, platform: 'Linux'}});
const timers = new Map();
let nextTimer = 1;
globalThis.setInterval = fn => { const id = nextTimer++; timers.set(id, fn); return id; };
globalThis.clearInterval = id => timers.delete(id);
const frames = new Map();
globalThis.requestAnimationFrame = fn => { const id = nextTimer++; frames.set(id, fn); return id; };
globalThis.cancelAnimationFrame = id => frames.delete(id);
globalThis.ResizeObserver = class {
  constructor(fn) { this.fn = fn; }
  observe() {}
  disconnect() { calls.push(['disconnect']); }
};
const page = {app: {}, DROP_DIR: '/drop', MOUNT_DIR: '/mount'};
for (const name of ['draw', 'title', 'animating', 'wake_in', 'move', 'wheel', 'resize',
                    'press', 'release', 'key', 'key_up', 'clear_keys', 'copy', 'paste']) {
  page[name] = (...args) => {
    calls.push([name, ...args]);
    if (name === 'copy') return 'selected';
    if (name === 'wake_in') return -1;
    if (name === 'title') return '';
    return name !== 'animating';
  };
}
WebAssembly.Suspending = function () {};
page.key.callPromising = async (...args) => {
  calls.push(['jspi']); return page.key(...args);
};
let locked = false;
const pending = [];
const pyodide = {
  globals: {set(name, value) { calls.push(['global', name, value === canvas]); }},
  loadPackage: async () => {}, unpackArchive() {},
  runPythonAsync: async code => {
    if (/^  \S/m.test(code)) throw Error('indented Python');
    calls.push(['gpu']);
  },
  runPython: code => {
    if (code.includes('mount(')) {
      if (!code.includes('mount(_emtk_canvas')) throw Error('wrong canvas binding');
      return page;
    }
  },
};
let loaded = 0;
globalThis.loadPyodide = async () => { loaded++; return pyodide; };
globalThis.fetch = async () => ({ok: true, arrayBuffer: async () => new ArrayBuffer(0)});
if (SHARED) globalThis.emtkRuntime = async (config, element, status) => ({
  pyodide,
  mount: async (element, spec) => {
    calls.push(['mount', element === canvas, spec]); return page;
  },
  call: task => { if (locked) pending.push(task); else return task(); },
  promising: async task => { calls.push(['promising']); return task(); },
  busy: () => locked,
  close: p => calls.push(['close', p === page]),
});
console.log = () => {};
BOOT
(async () => {
  for (let i = 0; i < 10 && !globalThis.emtkReady; i++) await new Promise(resolve => setImmediate(resolve));
  if (!globalThis.emtkReady) throw Error(globalThis.emtkError || 'not ready');
  const event = () => ({
    clientX: 10, clientY: 20, button: 0, buttons: 1, deltaY: 30,
    key: 'a', target: canvas, prevented: false,
    preventDefault() {this.prevented = true;},
  });
  const out = {loaded, width: canvas.width, height: canvas.height};
  const cut = event();
  cut.clipboardData = {setData: (type, text) => { out.clipboard = text; }};
  document.listeners.cut(cut);
  locked = SHARED;
  canvas.listeners.pointermove(event());
  canvas.listeners.wheel(event());
  const key = event();
  await window.listeners.keydown(key);
  out.keyPrevented = key.prevented;
  out.beforeFlush = calls.filter(c => c[0] === 'move').length;
  const busyCut = event();
  busyCut.clipboardData = {setData() {throw Error('busy copy must not run');}};
  if (SHARED) document.listeners.cut(busyCut);
  locked = false;
  while (pending.length) pending.shift()();
  await emtkInvoke(page.key, 'Enter');
  out.afterFlush = calls.filter(c => c[0] === 'move').length;
  locked = SHARED;
  canvas.listeners.pointermove(event());
  emtkRedraw();
  window.listeners.pagehide();
  locked = false;
  while (pending.length) pending.shift()();
  out.afterDispose = calls.filter(c => c[0] === 'move').length;
  out.frames = frames.size;
  out.timers = timers.size;
  out.calls = calls;
  process.stdout.write(JSON.stringify(out));
})().catch(e => {process.stderr.write(String(e.stack || e)); process.exitCode = 1;});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
@pytest.mark.parametrize("shared", [False, True], ids=["standalone", "shared"])
def test_loader_reuses_runtime_and_disposes_queued_events(tmp_path, shared):
    boot = pathlib.Path(serve.__file__).with_name("boot.js").read_text()
    script = tmp_path / "runtime.js"
    script.write_text(HARNESS.replace("SHARED", json.dumps(shared)).replace("BOOT", boot))
    result = subprocess.run(["node", str(script)], capture_output=True, text=True,
                            check=True, timeout=30)
    out = json.loads(result.stdout)
    assert out["loaded"] == (0 if shared else 1)
    assert (out["width"], out["height"]) == (640, 400)
    assert out["clipboard"] == "selected", "idle copy/cut preserves synchronous text"
    assert ["jspi"] in out["calls"], "external commands use the suspendable stack"
    assert out["keyPrevented"]
    assert out["beforeFlush"] == (0 if shared else 1)
    assert out["afterFlush"] == 1
    assert out["afterDispose"] == (1 if shared else 2)
    assert out["frames"] == out["timers"] == 0
    if shared:
        assert ["mount", True, "example:app"] in out["calls"]
        assert ["close", True] in out["calls"]
        assert ["promising"] in out["calls"]
        assert sum(call[0] == "copy" for call in out["calls"]) == 1
    else:
        assert ["global", "_emtk_canvas", True] in out["calls"]
        assert ["gpu"] in out["calls"]
