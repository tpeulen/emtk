// Load an emtk app into the page. This file draws nothing.
//
// It is a *loader* and an *event forwarder*: it starts Pyodide, loads the
// packages and wheels the build named, unpacks the app archive, resolves the
// WebGPU device, and hands the canvas to `emtk.web.page.mount`. Every frame
// after that is Python calling WebGPU (emtk/gpu/browser.py), and every event
// is handed to Python with the DOM's own values -- `emtk.events` and
// `emtk.keys` decide what they mean, not this file.
//
// A guard test fails if this file ever contains `createRenderPipeline`,
// `createBuffer` or `beginRenderPass`.
//
// The one thing here that is not plumbing is the *async* handover. WebGPU's
// `requestAdapter` and `requestDevice` return promises; everything after them
// is synchronous, because command recording is. Resolving both before the app
// starts keeps `await` out of every renderer.

const config = JSON.parse(document.getElementById("emtk-config").textContent);

const status = (message) => {
  const el = document.getElementById("status");
  if (el) el.textContent = message;
  console.log(`[${config.name || "emtk"}]`, message);
};

async function boot() {
  const canvas = document.getElementById("view");
  const dpr0 = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr0));
  canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr0));

  if (!navigator.gpu) {
    status("this browser has no WebGPU (navigator.gpu is undefined)");
    return;
  }

  status("loading Pyodide…");
  const pyodide = await loadPyodide({ enableRunUntilComplete: true });
  globalThis.emtkPyodide = pyodide;

  if (config.pyodide_packages && config.pyodide_packages.length) {
    status(`loading ${config.pyodide_packages.join(", ")}…`);
    await pyodide.loadPackage(config.pyodide_packages);
  }
  // Local wheels (a compiled extension built for Pyodide, say). By URL:
  // `loadPackage` installs a wheel it is pointed at, with no index.
  if (config.wheels && config.wheels.length) {
    status(`installing ${config.wheels.length} wheel(s)…`);
    const urls = config.wheels.map((name) => new URL(name, location.href).href);
    await pyodide.loadPackage(urls);
  }

  status(`fetching ${config.archive}…`);
  const response = await fetch(config.archive);
  if (!response.ok) throw new Error(`${config.archive}: ${response.status}`);
  pyodide.unpackArchive(await response.arrayBuffer(), "zip", { extractDir: config.extract_dir });
  pyodide.globals.set("_emtk_extract_dir", config.extract_dir);
  pyodide.runPython(`import sys; sys.path.insert(0, _emtk_extract_dir)`);

  status("requesting a GPU device…");
  // Both promises resolve here, before any app code runs.
  await pyodide.runPythonAsync(`
from emtk.gpu import api, browser
api.use_backend(browser)
_emtk_adapter = await browser.request_adapter_async()
await _emtk_adapter.request_device_async()
`);

  status(`starting ${config.app}…`);
  globalThis.emtkCanvas = canvas;
  pyodide.globals.set("_emtk_app_spec", config.app);
  const page = pyodide.runPython(`
import js
from emtk.web.page import mount
mount(js.emtkCanvas, _emtk_app_spec)
`);
  globalThis.emtkPage = page;
  globalThis.emtkApp = page.app;

  // A call that may *run something* -- a menu entry, a command line's Return,
  // a dropped file -- enters Python on a suspendable stack (JSPI) when the
  // browser has one, so a synchronous renderer can wait for the one thing
  // WebGPU only does asynchronously: mapping a buffer to read it back
  // (`emtk/gpu/browser.py::_Queue.read_buffer`). Moves and wheels stay plain:
  // a hover must not queue behind an await.
  const jspi = typeof WebAssembly !== "undefined" && "Suspending" in WebAssembly;
  const promising = async (fn, ...args) =>
    jspi && typeof fn.callPromising === "function" ? await fn.callPromising(...args) : fn(...args);

  // Draw on demand, and keep a frame loop only while Python is animating.
  let frame = null;
  const redraw = () => {
    if (frame !== null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      page.draw();
      if (page.animating()) redraw();
    });
  };
  // The loop above is only ever *started* by an event; an animation can begin
  // without one (a script, a test), so check a few times a second while idle.
  setInterval(() => {
    if (frame === null && page.animating()) redraw();
  }, 250);
  globalThis.emtkRedraw = redraw;

  // CSS pixels: the app lays out and hit-tests in them.
  const at = (event) => {
    const box = canvas.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
  };
  const mods = (event) => [event.ctrlKey, event.shiftKey, event.altKey, event.metaKey];

  canvas.addEventListener("pointerdown", async (event) => {
    canvas.setPointerCapture(event.pointerId);
    event.preventDefault();
    const [x, y] = at(event);
    if (await promising(page.press, x, y, event.button, ...mods(event), false)) redraw();
  });
  // The DOM delivers `down, up, down, up, dblclick`: the `dblclick` is a fifth
  // event with no `up` of its own. It says `double` and then releases, or the
  // double press would stay held forever.
  canvas.addEventListener("dblclick", async (event) => {
    event.preventDefault();
    const [x, y] = at(event);
    let changed = await promising(page.press, x, y, event.button, ...mods(event), true);
    changed = (await promising(page.release, x, y, event.button, ...mods(event))) || changed;
    if (changed) redraw();
  });
  canvas.addEventListener("pointermove", (event) => {
    const [x, y] = at(event);
    if (page.move(x, y, event.buttons, ...mods(event))) redraw();
  });
  const end = async (event) => {
    const [x, y] = at(event);
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (await promising(page.release, x, y, event.button, ...mods(event))) redraw();
    syncMount();
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const [x, y] = at(event);
    if (page.wheel(event.deltaY, x, y, ...mods(event))) redraw();
  }, { passive: false });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  const resize = () => {
    if (page.resize(canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio || 1)) redraw();
  };
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(resize).observe(canvas);
  else window.addEventListener("resize", resize);

  // Keys on `window`, so the app takes typing without a click first; real
  // form controls on the page are left alone. Return may *run* something, so
  // it goes in on the suspendable stack with its default prevented first.
  // Every other key is answered synchronously, so whether it was consumed can
  // decide `preventDefault` -- browser shortcuts stay the browser's.
  window.addEventListener("keydown", async (event) => {
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || event.target?.isContentEditable) return;
    const args = [event.key, event.key.length === 1 ? event.key : "", ...mods(event)];
    let consumed;
    if (event.key === "Enter") {
      event.preventDefault();
      consumed = await promising(page.key, ...args);
      syncMount();
    } else {
      consumed = page.key(...args);
    }
    if (consumed) event.preventDefault();
    redraw();
  });

  // Local files, both ending as a path on Pyodide's filesystem.
  const dropHint = document.getElementById("drop-hint");
  if (config.drop !== false) {
    if (dropHint) dropHint.hidden = false;
    canvas.addEventListener("dragover", (event) => {
      event.preventDefault();
      canvas.classList.add("dropping");
    });
    canvas.addEventListener("dragleave", () => canvas.classList.remove("dropping"));
    canvas.addEventListener("drop", async (event) => {
      event.preventDefault();
      canvas.classList.remove("dropping");
      const files = Array.from((event.dataTransfer && event.dataTransfer.files) || []);
      for (const file of files) {
        status(`opening ${file.name}…`);
        try {
          pyodide.FS.mkdirTree(page.DROP_DIR);
          const path = `${page.DROP_DIR}/${file.name}`;
          pyodide.FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
          if (await promising(page.open_path, path)) redraw();
        } catch (error) {
          status(`could not open ${file.name}: ${error}`);
          console.error(error);
        }
      }
      if (files.length) status(`opened ${files.map((f) => f.name).join(", ")}`);
    });
  }
  // Mount: Chrome's File System Access API hands over a directory handle and
  // Pyodide mounts it (`mountNativeFS`). Its own function, so a test can hand
  // it a handle it *can* get without a picker (the origin-private FS).
  const mountDirectory = async (handle) => {
    if (globalThis.emtkMount) {
      await globalThis.emtkMount.syncfs();
      pyodide.FS.unmount(page.MOUNT_DIR);
      globalThis.emtkMount = null;
    }
    pyodide.FS.mkdirTree(page.MOUNT_DIR);
    globalThis.emtkMount = await pyodide.mountNativeFS(page.MOUNT_DIR, handle);
    status(`${handle.name || "folder"} is mounted at ${page.MOUNT_DIR}`);
    return page.MOUNT_DIR;
  };
  globalThis.emtkMountDirectory = mountDirectory;
  const mountButton = document.getElementById("mount");
  if (config.mount !== false && mountButton && typeof window.showDirectoryPicker === "function"
      && typeof pyodide.mountNativeFS === "function") {
    mountButton.hidden = false;
    mountButton.addEventListener("click", async () => {
      try {
        const handle = await window.showDirectoryPicker({ mode: "readwrite" });
        await mountDirectory(handle);
        mountButton.textContent = `Mounted: ${handle.name}`;
      } catch (error) {
        if (error && error.name === "AbortError") return;
        status(`could not mount the folder: ${error}`);
        console.error(error);
      }
    });
  }
  // Writes into a mount reach the disk on `syncfs`; after anything that could
  // have written, and on the way out.
  function syncMount() {
    if (globalThis.emtkMount) globalThis.emtkMount.syncfs().catch(() => {});
  }
  globalThis.emtkSyncMount = syncMount;
  window.addEventListener("beforeunload", syncMount);

  page.draw();
  if (page.animating()) redraw();
  globalThis.emtkReady = true;
  status(config.ready_message || "ready");
}

boot().catch((error) => {
  // Kept whole on `window` as well as logged: a Python traceback crossing into
  // the console is truncated, and the useful line is the innermost one.
  globalThis.emtkError = String((error && error.stack) || error);
  status(`failed: ${error}`);
  console.error(error);
});
