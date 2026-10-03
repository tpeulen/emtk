"""``emtk.jobs`` -- long computations that never stall the page.

:mod:`emtk.tasks` interleaves work with frames, which on a page with no threads
still freezes the interface for as long as any single call takes (a C++ routine
of a few seconds, say). A *job* runs elsewhere: in a **Web Worker** -- a second
Pyodide that loads the same packages, wheels and app archive as the page -- or,
on a desktop, in a thread. The page keeps drawing; the job reports progress.

A job is a plain function, named by ``"package.module:function"``, called as
``fn(report, **params)``. ``params`` and the return value are JSON (they cross
into another interpreter); ``report(fraction, message)`` sets the progress::

    def analyse(report, pdb_id):
        report(0.1, "fetching")
        ...
        return {"rows": rows}

    job = emtk.jobs.start("myapp.jobs:analyse", {"pdb_id": "1omp"})
    # every frame
    if job.done:
        use(job.result) if job.error is None else show(job.error)

:func:`warm` starts the worker early (it takes as long to boot as the page),
so the first job does not pay for it. ``env`` is set in the worker's
``os.environ`` before the function runs, for what a page knows and a worker
cannot read.

``files`` names files on the page's file system (a dropped file, say) that the
job reads: in a page they appear in the worker's file system at the same path
before the function runs, and stay there for later jobs, which need not send
them again. A file the user dropped goes as its ``File`` handle (kept by the
page's drop handler): the worker mounts it read-only and reads it from disk
as it goes, so a large file costs the worker no memory. Any other file is
copied, as a transferred buffer, not encoded into the JSON. On a desktop the thread shares the file system and ``files`` is a
no-op.
"""
from __future__ import annotations

import importlib
import itertools
import json
import os
import threading
import traceback
from typing import Any, Callable, Optional

__all__ = ["Job", "configure", "in_browser", "start", "warm", "worker_state"]

_ids = itertools.count(1)

#: Pyodide packages the worker loads; ``None``: all the page loads.
_worker_packages: Optional[list] = None


def configure(packages: Optional[list] = None) -> None:
    """Say what the page's worker needs, before it starts (:func:`warm`, the first job).

    ``packages``: the Pyodide packages to load there, e.g. ``["numpy"]`` -- a
    worker that only computes need not load what the page loads for drawing or
    for other tools (scipy, matplotlib, ...), and boots that much sooner.
    ``None`` (the default) loads all of the page's. The page's wheels and app
    archive are always loaded.
    """
    global _worker_packages
    _worker_packages = None if packages is None else [str(p) for p in packages]


def in_browser() -> bool:
    try:
        import js  # noqa: F401,PLC0415
        import pyodide  # noqa: F401,PLC0415
    except ImportError:
        return False
    return hasattr(__import__("js"), "document")


def _resolve(spec: str) -> Callable:
    module, _, name = spec.partition(":")
    if not name:
        raise ValueError(f"a job is 'package.module:function', not {spec!r}")
    return getattr(importlib.import_module(module), name)


class Job:
    """One job's state, updated as the worker (or thread) reports."""

    def __init__(self, spec: str) -> None:
        self.id = next(_ids)
        self.spec = spec
        self.progress: Optional[float] = None   # None: not reported yet
        self.message = "starting"
        self.done = False
        self.result: Any = None
        self.error: Optional[str] = None
        self.cancelled = False
        self._on_cancel: Optional[Callable[[], None]] = None

    @property
    def running(self) -> bool:
        return not self.done

    def cancel(self) -> None:
        if self.done:
            return
        self.cancelled = True
        self.done = True
        self.error = "cancelled"
        if self._on_cancel is not None:
            self._on_cancel()

    def _report(self, fraction=None, message=None) -> None:
        if fraction is not None:
            self.progress = max(0.0, min(1.0, float(fraction)))
        if message is not None:
            self.message = str(message)


# --------------------------------------------------------------------------- #
# desktop: a thread
# --------------------------------------------------------------------------- #
def _start_thread(job: Job, params: dict, env: dict) -> None:
    def run() -> None:
        try:
            for key, value in env.items():
                os.environ.setdefault(key, str(value))
            fn = _resolve(job.spec)
            result = fn(job._report, **params)
            # The same JSON round trip as a worker, so both hosts hand back the same thing.
            result = json.loads(json.dumps(result))
            if not job.cancelled:
                job.result, job.done = result, True
        except Exception:  # noqa: BLE001 - handed to the caller
            if not job.cancelled:
                job.error, job.done = traceback.format_exc(limit=8), True

    threading.Thread(target=run, name=f"emtk-job-{job.id}", daemon=True).start()


# --------------------------------------------------------------------------- #
# page: a Web Worker running a second Pyodide
# --------------------------------------------------------------------------- #
_WORKER_JS = r"""
const cfg = __CONFIG__;
importScripts(cfg.pyodide_js);
const ready = (async () => {
  const py = await loadPyodide();
  if (cfg.packages.length) await py.loadPackage(cfg.packages);
  if (cfg.wheels.length) await py.loadPackage(cfg.wheels);
  const response = await fetch(cfg.archive);
  if (!response.ok) throw new Error(cfg.archive + ": " + response.status);
  py.unpackArchive(await response.arrayBuffer(), "zip", { extractDir: cfg.extract_dir });
  py.globals.set("_emtk_extract_dir", cfg.extract_dir);
  py.runPython("import sys; sys.path.insert(0, _emtk_extract_dir)");
  return py;
})();
ready.then(() => postMessage({ ready: true }),
           (e) => postMessage({ ready: false, error: String(e) }));
onmessage = async (event) => {
  const job = event.data;
  let py;
  try { py = await ready; } catch (e) { postMessage({ id: job.id, error: "worker failed to start: " + e }); return; }
  try {
    // Files the job reads: written where the page had them, then dropped
    // from the message so the buffers never reach Python as JSON.
    for (const f of (job.files || [])) {
      const dir = f.path.substring(0, f.path.lastIndexOf("/"));
      if (dir) py.FS.mkdirTree(dir);
      try { py.FS.unlink(f.path); } catch (e) { /* not there yet */ }
      if (f.file && py.FS.filesystems.WORKERFS) {
        // The File itself: mounted read-only, read lazily from disk -- no
        // copy of a large file in this worker's memory.
        const at = "/mnt/emtk-jobfiles/" + (self.emtkJobFileMounts = (self.emtkJobFileMounts || 0) + 1);
        py.FS.mkdirTree(at);
        py.FS.mount(py.FS.filesystems.WORKERFS, { files: [f.file] }, at);
        py.FS.symlink(at + "/" + f.file.name, f.path);
      } else {
        const data = f.data ? new Uint8Array(f.data) : new Uint8Array(await f.file.arrayBuffer());
        py.FS.writeFile(f.path, data);
      }
    }
    delete job.files;
  } catch (e) {
    postMessage({ id: job.id, error: "could not copy the job's files: " + e });
    return;
  }
  try {
    py.globals.set("_emtk_job", py.toPy(job));
    py.runPython("from emtk.jobs import _worker_run; _worker_run(_emtk_job)");
  } catch (e) {
    postMessage({ id: job.id, error: String(e) });
  }
};
"""


class _Worker:
    """The page's one worker, started on first use (or by :func:`warm`)."""

    def __init__(self) -> None:
        import js  # noqa: PLC0415
        from pyodide.ffi import create_proxy  # noqa: PLC0415

        config = json.loads(js.document.getElementById("emtk-config").textContent)
        base = str(js.location.href)
        absolute = lambda url: str(js.URL.new(url, base).href)  # noqa: E731
        script = js.document.querySelector('script[src*="pyodide"]')
        cfg = {
            "pyodide_js": absolute(script.src if script is not None else "pyodide/pyodide.js"),
            "packages": list(config.get("pyodide_packages", []) if _worker_packages is None
                             else _worker_packages),
            "wheels": [absolute(w) for w in config.get("wheels", [])],
            "archive": absolute(config["archive"]),
            "extract_dir": config.get("extract_dir", "/app"),
        }
        source = _WORKER_JS.replace("__CONFIG__", json.dumps(cfg))
        from pyodide.ffi import to_js  # noqa: PLC0415

        blob = js.Blob.new(to_js([source]), to_js({"type": "text/javascript"},
                                                  dict_converter=js.Object.fromEntries))
        self.worker = js.Worker.new(js.URL.createObjectURL(blob))
        self.jobs: dict[int, Job] = {}
        self.state = "starting"        # starting -> ready | failed
        self.error: Optional[str] = None
        self._handler = create_proxy(self._message)
        self.worker.onmessage = self._handler

    def _message(self, event) -> None:
        data = event.data.to_py() if hasattr(event.data, "to_py") else dict(event.data)
        if "ready" in data:
            self.state = "ready" if data["ready"] else "failed"
            self.error = data.get("error")
            if self.state == "failed":
                for job in self.jobs.values():
                    if not job.done:
                        job.error, job.done = f"worker failed to start: {self.error}", True
            return
        job = self.jobs.get(int(data.get("id", -1)))
        if job is None or job.done:
            return
        if "progress" in data or "message" in data:
            job._report(data.get("progress"), data.get("message"))
        if "result" in data:
            job.result, job.done = json.loads(data["result"]), True
        elif "error" in data:
            job.error, job.done = str(data["error"]), True

    def submit(self, job: Job, params: dict, env: dict, files=()) -> None:
        from pyodide.ffi import to_js  # noqa: PLC0415
        import js  # noqa: PLC0415

        self.jobs[job.id] = job
        if self.state == "starting":
            job._report(None, "starting the compute worker (first run only)")
        message = {"id": job.id, "spec": job.spec, "params": json.dumps(params), "env": json.dumps(env)}
        message = to_js(message, dict_converter=js.Object.fromEntries)
        transfer = []
        if files:
            import pyodide_js  # noqa: PLC0415

            entries = js.Array.new()
            handles = getattr(js, "emtkDroppedFiles", None)
            for path in files:
                entry = js.Object.new()
                entry.path = str(path)
                handle = None
                if handles is not None:
                    try:
                        handle = getattr(handles, str(path), None)
                    except Exception:  # noqa: BLE001 - a path JS cannot index by
                        handle = None
                if handle is not None:
                    entry.file = handle                          # cloned, not copied
                else:
                    data = pyodide_js.FS.readFile(str(path))     # a copy, as a Uint8Array
                    entry.data = data.buffer
                    transfer.append(data.buffer)
                entries.push(entry)
            message.files = entries
        if transfer:
            self.worker.postMessage(message, to_js(transfer))
        else:
            self.worker.postMessage(message)
        job._on_cancel = _restart

    def terminate(self) -> None:
        self.worker.terminate()


_worker: Optional[_Worker] = None


def _get_worker() -> _Worker:
    global _worker
    if _worker is None:
        _worker = _Worker()
    return _worker


def _restart() -> None:
    """Stop a running job: a worker cannot be interrupted, so it is replaced."""
    global _worker
    if _worker is not None:
        old, _worker = _worker, None
        old.terminate()
        for job in old.jobs.values():
            if not job.done:
                job.error, job.done = "cancelled", True
    warm()


def _worker_run(job) -> None:
    """Inside the worker: run one job and post its progress and result."""
    import js  # noqa: PLC0415
    from pyodide.ffi import to_js  # noqa: PLC0415

    job = dict(job)
    job_id = int(job["id"])

    def post(payload: dict) -> None:
        payload["id"] = job_id
        js.postMessage(to_js(payload, dict_converter=js.Object.fromEntries))

    def report(fraction=None, message=None) -> None:
        payload = {}
        if fraction is not None:
            payload["progress"] = float(fraction)
        if message is not None:
            payload["message"] = str(message)
        post(payload)

    try:
        for key, value in json.loads(job.get("env") or "{}").items():
            os.environ[key] = str(value)
        fn = _resolve(job["spec"])
        result = fn(report, **json.loads(job.get("params") or "{}"))
        post({"result": json.dumps(result)})
    except Exception:  # noqa: BLE001 - handed to the page
        post({"error": traceback.format_exc(limit=8)})


# --------------------------------------------------------------------------- #
# the API
# --------------------------------------------------------------------------- #
def start(spec: str, params: Optional[dict] = None, env: Optional[dict] = None,
          files: Optional[list] = None) -> Job:
    """Run ``spec`` with ``params`` off the page's thread; returns its :class:`Job`.

    ``files``: paths on the page's file system the job reads; copied into the
    worker's file system first (see the module docstring). A desktop thread
    reads them where they are.
    """
    job = Job(spec)
    params = dict(params or {})
    env = {k: str(v) for k, v in (env or {}).items()}
    files = [str(f) for f in (files or ())]
    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        raise FileNotFoundError(f"job files not found: {', '.join(missing)}")
    if in_browser():
        _get_worker().submit(job, params, env, files)
    else:
        _start_thread(job, params, env)
    return job


def warm() -> None:
    """Start the page's worker now, so the first job finds it booted. No-op on a desktop."""
    if in_browser():
        _get_worker()


def worker_state() -> str:
    """``"none"``, ``"starting"``, ``"ready"`` or ``"failed"`` (``"thread"`` on a desktop)."""
    if not in_browser():
        return "thread"
    return "none" if _worker is None else _worker.state
