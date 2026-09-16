# PRD-001 — A wgpu/WGSL host: Qt supplies the surface, nothing else

> **Corrected 2026-09-01.** This started out specifying an OpenGL/GLSL
> host. That was wrong: **emtk is WGSL-native**. chimol already renders
> emtk's chrome through wgpu with `ui.wgsl`, and a second shading language
> in the toolkit would mean two shaders to keep in step for one pipeline.
> Qt's job shrinks to owning the window and giving wgpu a surface to
> present to.

**Status: DONE (2026-09-01).** Built as specified. `emtk/wgpu_host.py`,
`emtk/wgsl/ui.wgsl`, `emtk/gpu_atlas.py`, `tests/test_wgpu_host.py`; chimol
loads emtk's shader. See *What was built* at the foot of this file.
**Repo:** emtk. Touches `emtk/wgpu_host.py` (new), `emtk/font.py`, `tests/`.

## The problem

`emtk/qt_host.py` does this:

```python
painter = QtGui.QPainter(self)
surface = QtPainter(painter, self.font_pt)
```

So the entire chrome is **rasterised on the CPU by QPainter** — every
rectangle, every glyph, every frame. That is not what emtk is for. Qt's job
is to open a window and hand wgpu a surface; the drawing belongs on the GPU.

The GPU path already exists and already works: `emtk/quad_painter.py` is a
full `Painter` implementation that emits vertices instead of rasterising,
and chimol consumes it through wgpu today. What is missing is that consumer
*inside emtk*, so any Qt window gets it.

Measured elsewhere (chimol, quarter-million beads): the QPainter chrome
cost **9.6 ms of a 21 ms frame** — enough that a timer was added to let the
panel go deliberately stale rather than repaint when it changed. A frame of
chrome is a few hundred rectangles and a few thousand glyphs; as vertices
that is kilobytes and no rasterisation at all.

## What to build

`emtk/wgpu_host.py` — a Qt widget owning a wgpu surface that renders a emtk
frame in **one draw call**, and forwards input exactly as
`qt_host.ControlHost` does.

Deliberately *not* a rewrite of `qt_host.py`: the QPainter host stays. It
is the reference the GPU output is compared against, and the fallback where
there is no wgpu adapter.

### The contract, already settled

`QuadPainter.vertices()` returns `(n, 12)` float32. Per vertex:

| floats | meaning |
|---|---|
| `x, y` | position in **pixels, y-down from the top left** |
| `u, v` | **atlas texels** (not normalised — the shader divides) |
| `r,g,b,a` | 0–1, **straight** alpha; the shader premultiplies |
| `x0,y0,x1,y1` | the clip rectangle, in pixels |

Six vertices per quad, two triangles, **no index buffer** (the chrome is
rebuilt every frame; an index buffer would be another allocation to keep in
step for no reuse). The clip rectangle rides **on the vertex** rather than
being a scissor, specifically so the whole chrome stays one draw call.

### The shader

`chimol/chimol/render/wgsl/ui.wgsl` is the shader. **Do not port it to
another language — move it into emtk and have chimol use emtk's copy.**
It belongs to the toolkit, not to one consumer of it. What it does:

* **Vertex:** pixels → NDC as `x/vw*2-1`, `1 - y/vh*2` (the chrome is
  y-down, clip space is y-up). Pass uv, colour, box, and the pixel position
  through.
* **Fragment:** `discard` when the pixel is outside `box`; sample the
  atlas's **alpha** as coverage (the atlas stores coverage in alpha and its
  colour channels are white, which is what lets the vertex colour decide
  the look); output **premultiplied** `vec4(rgb*alpha, alpha)`.

Straight alpha out is the trap: it darkens every antialiased glyph edge
against a light background — invisible on the dark panel, obvious the
moment the background is white.

### The texture

One RGBA8 texture of the **combined** atlas: baked rows on
top, the dynamic glyph cache underneath, total height `Atlas.texture_height`.

This is the same two-halves trap that bit `PixelPainter` (fixed
2026-08-31): `Atlas.cell_of` returns coordinates in the *combined* space,
so a host that uploads only the baked PNG samples past the end for any
character the baker never saw — an `IndexError` at best, silently the wrong
glyph at worst. Re-upload the cache rows when `cache.version` changes.

### Dependencies

`wgpu` (the Python binding) plus numpy, which `quad_painter` already
needs. Qt supplies only a window handle for the surface — no
`QOpenGL*` classes, no PyOpenGL. Import lazily and degrade the way
`qt_host` does where Qt or wgpu is absent, so emtk's zero-dependency
claim holds for anyone not asking for a window.

Read `chimol/chimol/viewport/canvas.py` first: it is a working wgpu
consumer of `QuadPainter` and settles the surface, pipeline and
bind-group questions before they are asked.

## Acceptance

1. The host renders cmc's ported interface, and a `grab()` of it
   matches the QPainter host's output closely enough to compare by eye.
   The existing driver is a good harness: see the `_Ported`/`_Adapter`
   pattern in `pycmc/__main__.py`.
2. One draw call per frame. Assert it — the whole design is that
   number staying at one.
3. Input still works: press, drag, wheel, keys. `Control.scroll(amount)`
   takes **one** argument in rows, sign-flipped from `io.mouse_wheel`.
4. A frame with text in it draws glyphs from **both** atlas halves —
   include a non-baked character (`ü`, `Δ`, `日`). Assert ink, and assert
   that accented text has *more* ink than unaccented: an ink-only check
   passes when the wrong glyph is drawn.
5. emtk's suite stays green, and `tools/gen_names.py --check` is current.

## The one genuinely undesigned piece — decided: port the negative-u

**Image quads.** emtk has `Texture` and `im.image`, and cmc's image window
uses them. chimol solves this with a second atlas selected by a **negative
u** (`u = -(1 + texel/W)`, tested `u < -0.5`), which keeps one pipeline and
preserves draw order — text after an image lands *on* it. emtk's
`QuadPainter` does not encode that today.

**Decided before starting: port the negative-u convention.** It is in
`emtk/gpu_atlas.py` (`image_u` / `image_texel` / `ImageAtlas`), shared by
both GPU hosts, and `wgsl/ui.wgsl` decodes it in the `u < -0.5` branch. The
alternative -- images that do not draw -- was rejected because cmc's image
window is the point of the image path, and because the OpenGL host had
already proved the encoding works. Two tests hold it: an image draws its own
pixels rather than the painter's flat fallback, and text drawn after an
image lands *on* it.

## Also open, smaller, not blocking this

* **`DataBridge::get_image_node` is `%ignore`d** in `cmc.i` but `ImageNode`
  is wrapped and the GUI needs it. Delete the one `%ignore` line, rebuild
  (`cmake --build build-swig312 --target cmc -j8`). Blocks the image path
  inside `start_acquisition`.
* **`analysis::MaxEntSolver` is unwrapped** — five `Eigen::VectorXd`
  members, no typemap, and its symbols are not linked into the module.
  Needs Eigen↔Python interop; a project of its own.

---

## PRD-002 — Sticky windows

**Status: DONE (2026-09-01).** See *What was built* at the foot of this
section.

cmc's floating sub-windows (BurstWindow, the MLE window, the image and
decay windows) all draw *on top of* the main window, because a emtk window
created with no explicit box follows the frame box every frame. emtk has no
window manager and no `.ini`, so nothing remembers where a window was.

**Make them sticky, as chimol does:** a window keeps its position and size
across frames once it has one, and a first appearance gets a sensible
placement rather than the whole frame. Read chimol's handling first and
follow it — the point is one behaviour across both, not a second invention.

Note `_Window.follows_frame` is *deliberate* (it fixed a real bug: a window
with no box latched its first frame's size and would not follow a resize).
Sticky placement has to be added **beside** that, not by reverting it: the
frame-following case is what a single full-window application still wants.


---

## What was built (2026-09-01)

* **`emtk/wgsl/ui.wgsl`** — moved out of the GPU viewer, unchanged as code.
  The comment header no longer names an application (emtk's own
  `test_the_prose_names_no_application_either` forbids it). Its bindings are
  still `@group(1)` with group 0 left alone, so an application whose prelude
  owns group 0 compiles the *same file*; `emtk.wgpu_host` binds an empty
  group 0. `emtk/wgsl/__init__.py` is the loader and imports nothing.
* **`emtk/gpu_atlas.py`** — the combined glyph atlas, `ImageAtlas` (now with
  `dirty_since`, so a live camera frame uploads its own rectangle instead of
  four megabytes), the negative-u encoding, and the vertex layout. Names no
  toolkit: it reaches Qt's PNG decoder through `qt_painter` when there is one
  and falls back to the pure-Python decoder when there is not — worth 2
  seconds on emtk's own atlas. `tests/test_gpu_atlas.py` tests all of it with
  no adapter and no toolkit.
* **`emtk/wgpu_host.py`** — `WgpuRenderer` (no window, no toolkit; `draw`
  into someone else's pass, `render` into a view, `grab` into a NumPy array)
  and `WgpuControlHost` (a `rendercanvas.qt.QRenderWidget`, on-demand draws,
  the same event forwarding as `qt_host`).
* **chimol** — `load_wgsl` falls back to `emtk.wgsl` and its own `ui.wgsl` is
  deleted. The page gets the file for free: `hosts/web/serve.py` packs a
  pure-Python dependency by suffix and `.wgsl` is one of them. Verified: the
  prelude plus emtk's shader compiles.

### Acceptance, measured

1. **cmc's ported interface renders, and matches the CPU rasteriser.**
   Against `PixelPainter` over the whole 1400x900 app frame: correlation
   **0.933**, **1.2 %** of pixels differing by more than 32 — antialiased
   glyph edges, a bilinear sample against a box filter.
2. **One draw call.** `renderer.draw_calls == 1` for the whole app frame,
   0 for an empty one. Asserted.
3. **Input works.** Press, drag, release, hover, wheel (one argument, in
   rows, sign-flipped) and keys, each asserted against a recording control.
4. **Both atlas halves.** Accented Greek draws *more* ink than the same
   string without the tonos, and `Δ λ 日` each draw — plus a character first
   rasterised *after* the texture was uploaded, which is the incremental
   cache patch.
5. **Green.** 1272 passed, 3 skipped with Qt and wgpu present; 1266 passed,
   9 skipped on an interpreter with no Qt at all, which is the claim emtk
   makes about itself. `tools/gen_names.py --check` current.

### One shading language (2026-09-01, decided)

The QPainter host stays, as specified — it is the reference and the fallback
where there is no adapter. **`gl_host.py` is retired**, and with it
`tests/test_gl_host.py`: it was a second shader for one pipeline, which is
what this PRD's correction argued against in the first place. emtk now has
exactly one GPU host and exactly one shading language.

Nothing was lost with it. The two atlases and the negative-u convention had
already moved to `emtk/gpu_atlas.py`, and the tests that were host-agnostic
moved to `tests/test_gpu_atlas.py` — where they are *better* placed, because
they need no context and now run on any machine rather than only on one that
can make an OpenGL 3.3 core profile. What went is genuinely OpenGL: the
GLSL, `surface_format()`, the `QOpenGL*` wrappers and the `glDrawArrays`.


---

## PRD-002, what was built (2026-09-01)

Two things were wrong and both are fixed in `emtk/im_core.py`:

* **`SetNextWindowPos` / `SetNextWindowSize` were accepted and discarded.**
  Literally: `if pending.pop("pos") is not None or ...: pass`. A port that
  places a floating window the way ImGui code does had its instruction
  dropped and got the whole frame. They are now honoured, with ImGui's
  condition — `Always` re-places every frame, `Once`/`FirstUseEver` place on
  creation (the same thing here: there is no `.ini` for "ever" to mean
  anything against), `Appearing` places whenever the window was absent last
  frame.
* **A box-less window could only be the frame.** `Context.set_window_placement`
  (`im.set_window_placement`) chooses: `PLACE_FRAME`, the default and
  unchanged — the window *is* the frame and keeps following it — or
  `PLACE_CASCADE`, placed once at a stepped offset and then kept.

`_Window.follows_frame` is untouched and still the default, exactly as this
PRD required. `_Window.sticky` sits **beside** it and means something the
other does not: the box was decided *once* and is emtk's to remember. A
window handed an explicit box every frame is neither — its caller owns the
placement — and a window re-placed unconditionally every frame is not sticky
either, which is what keeps a future `.ini` from saving a box nobody asked
to keep.

**In cmc:** one line in `pycmc/__main__.py`'s `_Adapter.draw`. MainWindow
still fills the frame — it says `SetNextWindowPos`/`Size` from the viewport
every frame, which outranks the placement and, deliberately, takes no step
of the cascade. `Burst` now lands at its own `(100, 100, 1000, 700)` (its
ported code asked for that and was being ignored) and `Image Scanning`
cascades to `(28, 28, 360, 260)`. Before this, all three were `(0, 0, 1400,
900)` and drew on top of each other.
