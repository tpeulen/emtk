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

// <copy-dropped> -- tests/test_web_drop.py runs this block under node.
// Write one dropped thing into Pyodide's filesystem under `dir` and return its
// path there. A File is written as it is; a FileSystemEntry (what
// `DataTransferItem.webkitGetAsEntry` gives) may be a directory -- a
// burst-analysis folder, a sample's result folder -- and is copied whole,
// so the app is handed one folder path, as a desktop drop would hand it.
async function copyDropped(item, dir, FS, byReferenceAbove = 0) {
  const path = `${dir}/${item.name}`;
  FS.mkdirTree(dir);
  if (item.isDirectory) {
    FS.mkdirTree(path);
    const reader = item.createReader();
    // `readEntries` hands a directory over in batches (Chrome: 100) and an
    // empty batch at the end; one call reads only the first batch.
    for (;;) {
      const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!batch.length) break;
      for (const child of batch) await copyDropped(child, path, FS, byReferenceAbove);
    }
    return path;
  }
  const file = item.isFile
    ? await new Promise((resolve, reject) => item.file(resolve, reject))
    : item;
  // The handle always: a job that reads this path gets the File itself in its
  // worker (emtk.jobs), mounted read-only, instead of another copy of the bytes.
  (globalThis.emtkDroppedFiles = globalThis.emtkDroppedFiles || {})[path] = file;
  if (byReferenceAbove > 0 && file.size > byReferenceAbove) {
    // An app that reads large files only in jobs (Bundle.drop_by_reference_above):
    // no copy in the page -- an empty placeholder marks the path.
    FS.writeFile(path, new Uint8Array(0));
    (globalThis.emtkDroppedByReference = globalThis.emtkDroppedByReference || {})[path] = file.size;
    return path;
  }
  FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
  return path;
}
// </copy-dropped>

// <clipboard> -- tests/test_web_clipboard.py runs this block under node.
// Copy, cut and paste reach the app through the DOM's own clipboard events.
// A page cannot read the clipboard synchronously (`navigator.clipboard.
// readText` is a promise behind a permission prompt), but a `paste` event
// carries the text, and a `copy`/`cut` event takes it -- both need nothing
// but the keystroke. So Cmd/Ctrl+C/X/V are *not* forwarded as keys from
// `keydown`: the browser's default runs, raises the event, and the event
// delivers the shortcut (`page.copy`, `page.paste`) with its text. The
// default is prevented only when the app took the shortcut, so a copy in a
// real DOM control, or one the app has no use for, stays the browser's. If no
// event follows (a browser that raises none), the key is delivered plain.
function isMacClient(nav) {
  const n = nav || {};
  const names = [(n.userAgentData && n.userAgentData.platform) || "", n.platform || "",
                 n.userAgent || ""];
  return names.some((name) => /mac|iphone|ipad/i.test(name));
}

function clipboardShortcut(event, mac) {
  const primary = mac ? event.metaKey : event.ctrlKey;
  if (!primary || event.altKey) return null;
  const letter = (event.key || "").toLowerCase();
  return letter === "c" || letter === "x" || letter === "v" ? letter : null;
}

function forwardClipboard(target, page, redraw, isFormControl, busy = () => false) {
  let pending = null;       // a clipboard keystroke waiting for its DOM event
  const settle = () => { pending = null; };
  target.addEventListener("copy", (event) => onCopy(event, false));
  target.addEventListener("cut", (event) => onCopy(event, true));
  function onCopy(event, cut) {
    if (isFormControl(event.target)) return;
    settle();
    // Clipboard writes must finish in this event. Do not cut data when a
    // shared interpreter cannot return the clipboard text synchronously.
    if (busy()) { event.preventDefault(); return; }
    const text = page.copy(cut);
    if (text !== undefined && text !== null) {
      event.clipboardData.setData("text/plain", String(text));
      event.preventDefault();
    }
    redraw();
  }
  target.addEventListener("paste", (event) => {
    if (isFormControl(event.target)) return;
    settle();
    const data = event.clipboardData;
    const text = data ? data.getData("text/plain") : "";
    if (page.paste(text || "")) event.preventDefault();
    redraw();
  });
  // Called by `keydown`: true when the key is the clipboard's to deliver.
  return function divert(event, deliver) {
    if (!clipboardShortcut(event, isMacClient(globalThis.navigator))) return false;
    const mine = {};
    pending = mine;
    setTimeout(() => { if (pending === mine) { pending = null; deliver(); } }, 0);
    return true;
  };
}
// </clipboard>

async function boot() {
  const canvas = document.getElementById("view");
  const dpr0 = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr0));
  canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr0));

  if (!navigator.gpu) {
    status("this browser has no WebGPU (navigator.gpu is undefined)");
    return;
  }

  // An embedding host may own a persistent interpreter and serialize its
  // calls. Ordinary pages retain their independent loader and event path.
  const runtime = typeof globalThis.emtkRuntime === "function"
    ? await globalThis.emtkRuntime(config, canvas, status) : null;
  let pyodide;
  let page;
  if (runtime) {
    pyodide = runtime.pyodide;
    page = await runtime.mount(canvas, config.app);
  } else {
    status("loading Pyodide…");
    pyodide = await loadPyodide({ enableRunUntilComplete: true });

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

    // `config.archive` carries a content hash (`app.zip?v=…`) so a cached
    // copy never outlives a redeploy; the status line shows the bare name.
    const archiveName = String(config.archive).split("?")[0];
    status(`fetching ${archiveName}…`);
    const response = await fetch(config.archive);
    if (!response.ok) throw new Error(`${archiveName}: ${response.status}`);
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
    pyodide.globals.set("_emtk_canvas", canvas);
    pyodide.globals.set("_emtk_app_spec", config.app);
    page = pyodide.runPython(`
from emtk.web.page import mount
mount(_emtk_canvas, _emtk_app_spec)
`);
  }
  globalThis.emtkPyodide = pyodide;
  globalThis.emtkCanvas = canvas;
  globalThis.emtkPage = page;

  // Attribute access also enters Python. Cache bound handlers through the
  // shared queue before installing listeners, then dispatch them directly.
  const describe = () => ({
    app: page.app,
    methods: {
      draw: page.draw, title: page.title, animating: page.animating, wake_in: page.wake_in,
      press: page.press, release: page.release, move: page.move, wheel: page.wheel,
      resize: page.resize, key: page.key, key_up: page.key_up, clear_keys: page.clear_keys,
      copy: page.copy, paste: page.paste, open_path: page.open_path,
    },
    dropDir: page.DROP_DIR,
    mountDir: page.MOUNT_DIR,
  });
  const description = runtime && runtime.promising ? await runtime.promising(describe) : describe();
  const {methods, dropDir, mountDir} = description;
  globalThis.emtkApp = description.app;

  // A call that may *run something* -- a menu entry, a command line's Return,
  // a dropped file -- enters Python on a suspendable stack (JSPI) when the
  // browser has one, so a synchronous renderer can wait for the one thing
  // WebGPU only does asynchronously: mapping a buffer to read it back
  // (`emtk/gpu/browser.py::_Queue.read_buffer`). Independent pages keep moves
  // synchronous; a shared interpreter queues them while another call awaits.
  const jspi = typeof WebAssembly !== "undefined" && "Suspending" in WebAssembly;
  let disposed = false;
  const busy = () => Boolean(runtime && runtime.busy && runtime.busy());
  const invoke = async (fn, ...args) =>
    jspi && typeof fn.callPromising === "function" ? await fn.callPromising(...args) : fn(...args);
  const promising = (fn, ...args) => {
    const task = () => disposed ? undefined : invoke(fn, ...args);
    return runtime && runtime.promising ? runtime.promising(task) : task();
  };
  const call = (fn, ...args) => {
    const deferred = busy();
    const task = () => {
      if (disposed) return undefined;
      const value = fn(...args);
      if (deferred) redraw();
      return value;
    };
    return runtime && runtime.call ? runtime.call(task) : task();
  };
  globalThis.emtkInvoke = promising;

  // Draw on demand, and keep a frame loop only while Python is animating.
  // An idle app can still ask for *one* frame later (a tooltip waiting out
  // its delay): `page.wake_in()` seconds, one timer, replaced by every frame.
  let frame = null;
  let wake = null;
  const redraw = () => {
    if (disposed || frame !== null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      if (wake !== null) { clearTimeout(wake); wake = null; }
      call(methods.draw);
      const title = call(methods.title);
      if (title && document.title !== title) document.title = title;
      if (call(methods.animating)) { redraw(); return; }
      const due = call(methods.wake_in);
      if (due >= 0) wake = setTimeout(() => { wake = null; redraw(); }, due * 1000);
    });
  };
  // The loop above is only ever *started* by an event; an animation can begin
  // without one (a script, a test), so check a few times a second while idle.
  const animationTimer = setInterval(() => {
    if (!disposed && !busy() && frame === null && call(methods.animating)) redraw();
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
    if (await promising(methods.press, x, y, event.button, ...mods(event), false)) redraw();
  });
  // The DOM delivers `down, up, down, up, dblclick`: the `dblclick` is a fifth
  // event with no `up` of its own. It says `double` and then releases, or the
  // double press would stay held forever.
  canvas.addEventListener("dblclick", async (event) => {
    event.preventDefault();
    const [x, y] = at(event);
    let changed = await promising(methods.press, x, y, event.button, ...mods(event), true);
    changed = (await promising(methods.release, x, y, event.button, ...mods(event))) || changed;
    if (changed) redraw();
  });
  canvas.addEventListener("pointermove", (event) => {
    const [x, y] = at(event);
    if (call(methods.move, x, y, event.buttons, ...mods(event))) redraw();
  });
  const end = async (event) => {
    const [x, y] = at(event);
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (await promising(methods.release, x, y, event.button, ...mods(event))) redraw();
    syncMount();
  };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const [x, y] = at(event);
    if (call(methods.wheel, event.deltaY, x, y, ...mods(event))) redraw();
  }, { passive: false });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  const resize = () => {
    if (call(methods.resize, canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio || 1)) redraw();
  };
  const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
  if (observer) observer.observe(canvas);
  else window.addEventListener("resize", resize);

  // Keys on `window`, so the app takes typing without a click first; real
  // form controls on the page are left alone. Return may *run* something, so
  // it goes in on the suspendable stack with its default prevented first.
  // Every other key is answered synchronously, so whether it was consumed can
  // decide `preventDefault` -- browser shortcuts stay the browser's.
  const isFormControl = (el) => {
    const tag = (el && el.tagName) || "";
    return tag === "INPUT" || tag === "TEXTAREA" || Boolean(el && el.isContentEditable);
  };
  const clipboardPage = {
    copy: (cut) => call(methods.copy, cut),
    paste: (text) => call(methods.paste, text),
  };
  const divertClipboard = forwardClipboard(document, clipboardPage, redraw, isFormControl, busy);
  window.addEventListener("keydown", async (event) => {
    if (isFormControl(event.target)) return;
    if (busy()) event.preventDefault();
    const args = [event.key, event.key.length === 1 ? event.key : "", ...mods(event)];
    // Cmd/Ctrl+C/X/V: the browser's copy/cut/paste event delivers it, with
    // the clipboard's text (see forwardClipboard) -- no preventDefault here.
    if (divertClipboard(event, () => { if (call(methods.key, ...args)) redraw(); })) return;
    let consumed;
    if (event.key === "Enter") {
      event.preventDefault();
      consumed = await promising(methods.key, ...args);
      syncMount();
    } else {
      consumed = call(methods.key, ...args);
    }
    if (consumed) event.preventDefault();
    redraw();
  });
  window.addEventListener("keyup", (event) => {
    if (isFormControl(event.target)) return;
    if (busy()) event.preventDefault();
    const consumed = call(methods.key_up, event.key, ...mods(event));
    if (consumed) event.preventDefault();
    redraw();
  });
  window.addEventListener("blur", () => {
    if (call(methods.clear_keys)) redraw();
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
      // Entries, not `files`: a dropped *folder* is a File of size 0 in
      // `files`, whose bytes cannot be read. The entries have to be taken
      // now -- the DataTransfer is emptied at the first `await`.
      const items = Array.from((event.dataTransfer && event.dataTransfer.items) || []);
      const entries = items.map((item) => item.webkitGetAsEntry && item.webkitGetAsEntry())
        .filter(Boolean);
      const dropped = entries.length
        ? entries
        : Array.from((event.dataTransfer && event.dataTransfer.files) || []);
      for (const item of dropped) {
        status(`opening ${item.name}…`);
        try {
          const path = await copyDropped(item, dropDir, pyodide.FS,
                                         Number(config.drop_by_reference_above || 0));
          if (await promising(methods.open_path, path)) redraw();
        } catch (error) {
          status(`could not open ${item.name}: ${error}`);
          console.error(error);
        }
      }
      if (dropped.length) status(`opened ${dropped.map((f) => f.name).join(", ")}`);
    });
  }
  // Mount: Chrome's File System Access API hands over a directory handle and
  // Pyodide mounts it (`mountNativeFS`). Its own function, so a test can hand
  // it a handle it *can* get without a picker (the origin-private FS).
  const mountDirectory = async (handle) => {
    if (globalThis.emtkMount) {
      await globalThis.emtkMount.syncfs();
      pyodide.FS.unmount(mountDir);
      globalThis.emtkMount = null;
    }
    pyodide.FS.mkdirTree(mountDir);
    globalThis.emtkMount = runtime && runtime.mountDirectory
      ? await runtime.mountDirectory(handle, mountDir)
      : await pyodide.mountNativeFS(mountDir, handle);
    status(`${handle.name || "folder"} is mounted at ${mountDir}`);
    return mountDir;
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

  call(methods.draw);
  if (call(methods.animating)) redraw();
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    if (frame !== null) cancelAnimationFrame(frame);
    if (wake !== null) clearTimeout(wake);
    clearInterval(animationTimer);
    if (observer) observer.disconnect();
    if (runtime && runtime.close) {
      Promise.resolve(runtime.close(page)).then(() => {
        for (const method of Object.values(methods)) {
          if (method && typeof method.destroy === "function") method.destroy();
        }
      }).catch((error) => console.error(error));
    }
  };
  globalThis.emtkDispose = dispose;
  window.addEventListener("pagehide", dispose);
  window.addEventListener("beforeunload", dispose);
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
