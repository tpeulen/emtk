# Continue here

Two repos, one job: cmc's C++/ImGui GUI is being ported to Python on cmtk.
`~/dev/cmtk` is the toolkit + `tools/autoport`; `~/dev/cmc` is the app.
A third, the GPU viewer at `~/dev/chimol`, consumes cmtk and now loads its
shader.

## State (2026-09-01, later)

* cmtk: **1272 passed, 3 skipped** in the `arm64` env (Qt + wgpu);
  **1266 passed, 9 skipped** in the base env, which has no Qt.
  `tools/gen_names.py --check` current.
* One GPU host (`wgpu_host`), one shading language (`wgsl/ui.wgsl`), and the
  QPainter host as the reference and the no-adapter fallback.
* Port: **cut=0** — every function in cmc's 9,393 lines of GUI C++ ports.
* Sweep: **22/22** render methods draw with the default flags.
* The app runs under Qt, and the acquisition works.
* **PRD-001 (wgpu host) and PRD-002 (sticky windows) are done.** Read the
  foot of `prds/PRD-001-wgpu-host.md` for what was built and measured.

### What landed

* `cmtk/wgsl/ui.wgsl` — the toolkit's shader, moved out of chimol; chimol's
  `load_wgsl` now falls back to `cmtk.wgsl` and its own copy is deleted.
* `cmtk/wgpu_host.py` — `WgpuRenderer` (no window, no toolkit: `grab()`
  renders offscreen and hands back a NumPy array) and `WgpuControlHost` (a
  `rendercanvas.qt.QRenderWidget`).
* `cmtk/gpu_atlas.py` — the two atlases and the negative-u convention, with
  no idea what a device is; `tests/test_gpu_atlas.py` exercises all of it on
  any machine.
* **`gl_host.py` retired.** One GPU host, one shading language. See the foot
  of the PRD for what moved and what went.
* Sticky windows — `im.set_window_placement(PLACE_CASCADE)`, and
  `SetNextWindowPos`/`Size` are honoured at last (they were being discarded).
* cmc: `%ignore DataBridge::get_image_node;` deleted and rebuilt —
  `get_image_node` and `ImageNode` are both wrapped now.

Measured, not assumed: cmc's whole 1400x900 interface through the GPU is
**one draw call**, correlation **0.933** against `PixelPainter` with 1.2 %
of pixels differing — antialiased glyph edges and nothing else.

## Run and verify

```bash
cd ~/dev/cmtk  && python -m pytest tests/ -q && python tools/gen_names.py --check
cd ~/dev/cmc   && python tools/port_ui.py && cp src/ext/python/pycmc/*.py bin/pycmc/ \
                  && cp src/ext/python/pycmc/ui/*.py bin/pycmc/ui/
PYTHONPATH=~/dev/cmc/bin:~/dev/cmtk ~/mambaforge/envs/arm64/bin/python /tmp/draw_real.py
PYTHONPATH=~/dev/cmc/bin:~/dev/cmtk ~/mambaforge/envs/arm64/bin/python /tmp/draw_app_gpu.py
python src/ext/python/pycmc/check_split.py      # the GUI/compute boundary
```

`/tmp/draw_real.py` drives every render method of the wired app and prints
`DREW n/m`, one line per failure, and each window's box; pass a substring for
a full traceback. `/tmp/draw_app_gpu.py` draws the same interface through
`cmtk.wgpu_host.WgpuRenderer`, writes `/tmp/cmc_gpu.png` and prints the
correlation against the CPU rasteriser. Both are rebuildable from their own
docstrings if lost.

The app: `PYTHONPATH=~/dev/cmc/bin:~/dev/cmtk python -m pycmc` (ported UI is
the default; `--ui simple` is the small hand-written one).

## What is next

1. **The image window dereferences a null frame.** With no acquisition
   running, `image_window.py:441` does `self.render_histogram(frame.get())`
   and `frame` is `None`. In C++ `frame` is a `shared_ptr` initialised to
   `nullptr` and `.get()` on it is legally `nullptr`; the port maps a smart
   pointer to the object itself, so `None.get()` raises. It only shows when
   the image window is *open* — hence 22/22 above and a failure the moment
   `show_image_window_` is forced on. The fix belongs in
   `tools/autoport/expressions.py`: `decls.py` already knows which locals are
   `_NULLABLE` smart pointers, so a bare `.get()` on one should be dropped
   (the Python value *is* the pointee, or `None`). Do not add a generic
   `hasattr(x, "get")` shim — `.get()` on a SWIG object means something else.
   This is the last thing between the wrapped `get_image_node` and a drawing
   image window.
2. **`analysis::MaxEntSolver` is unwrapped** — five `Eigen::VectorXd`
   members, no typemap, and its symbols are not linked into the module.
   Needs Eigen↔Python interop; a project of its own, and why
   `maxent_fcs_window_` stays `None`.

## Traps that cost real time

* **Headless green ≠ the app works.** Render to a PNG *and look at it*;
  measure drawn pixels and the bounding box. A bbox of `x 4-7` is how the
  whole interface was found missing. `WgpuRenderer.grab()` exists for this:
  it needs no window and returns an array to assert on.
* **Compare like with like.** The first GPU-vs-CPU comparison correlated at
  0.42 and looked broken; the painter had been built at `font_pt=9` against
  an atlas baked at 8, so the two had laid out at different sizes. At the
  same font scale it is 0.94. A parity check that varies two things measures
  neither.
* **A guard that is too narrow hides the bugs behind it.** `if
  im.combo(...)` was always true (cmtk returns `(changed, value)`, a truthy
  tuple) because the out-param guard rejected `self.member`. Widening it then
  exposed a *wrong table* it had been masking.
* **`pycmc/ui/` is generated** — `port_ui.py` overwrites it. Hand-finished
  code goes in `pycmc/wiring.py` and `pycmc/__main__.py`, which are not.
  `wiring.py` is untracked, so `git checkout` on it does nothing.
* Colours are **bytes 0..255** in cmtk, floats 0..1 in ImGui and in wgpu.
  Floats don't raise headless; they raise under Qt, and in wgpu they draw a
  black window.
* Both repos' build flags and env are in `ARCHITECTURE.md` next to
  `check_split.py`. Use the `arm64` conda env — the base env has no Qt.
  It has wgpu, though, so the GPU tests run in both.

## The boundary

`~/dev/cmc/src/ext/python/pycmc/ARCHITECTURE.md`: GUI is Python on cmtk,
everything that computes is C++ behind SWIG. `check_split.py` enforces it.
