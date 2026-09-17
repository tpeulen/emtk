# Credits — what emtk was built by reading

emtk is a re-implementation, not an original design, and the projects below are
what it was written against. Every one is MIT licensed; their licence texts are
reproduced in `licenses/`, and each ported module names its source in its own
docstring. emtk itself is MIT (see `LICENSE`).

- **[Dear ImGui](https://github.com/ocornut/imgui)** (Omar Cornut, MIT) — the
  whole design and most of the code. `im_core.py` follows `imgui.cpp`,
  `im_widgets.py` follows `imgui_widgets.cpp` and `imgui_tables.cpp`, `im.py`
  follows `imgui.h`, and `drawlist.py` follows `imgui_draw.cpp`. The behaviour,
  the layout arithmetic, the `StyleColorsDark` palette and the naming are the
  reference's; all 362 published `ImGui::` names and all 60 `ImDrawList::`
  methods translate, and all 187 sections of `imgui_demo.cpp` are ported and
  run as tests. The controls under `widgets/` are additionally offered as
  retained objects drawn through the painter, for hosts that keep a widget
  rather than redrawing one.
- **[ImGuiColorTextEdit](https://github.com/goossens/ImGuiColorTextEdit)**
  (Johan A. Goossens, after Balázs Jákó and Santiago; MIT) —
  `widgets/text_editor.py`. The colouriser state machine, the multi-cursor
  model, the transaction-based undo and the language definitions come from it;
  its keyword tables are extracted from the source rather than retyped, and a
  test re-extracts them to prove they have not drifted.
- **[imgui_club](https://github.com/ocornut/imgui_club)** (Omar Cornut, MIT) —
  `widgets/memory_editor.py`, the hex view over host arrays and device
  buffers, from `imgui_memory_editor`. Its layout arithmetic, HexII
  compression and data-preview footer are transcribed.
- **[pyCirclize](https://github.com/moshi4/pyCirclize)** (moshi4, MIT) —
  `widgets/circle.py`, the Circos-style circular layout. Its arithmetic is
  kept: sectors sharing the circle in proportion to their sizes with a gap
  between them, `Sector.x_to_rad`, the 0..100 radius space, north at the top
  with angles running clockwise, and the Bezier control point that gives a
  chord its height. Its canvas is not — pyCirclize draws matplotlib patches on
  a `PolarAxes`, so every shape is projected here and emitted as triangles
  through the painter.
- **[ImPlot](https://github.com/epezent/implot)** (Evan Pezent and Breno
  Cunha Queiroz, MIT; read at commit 7eeb916) -- `implot.py` follows
  `implot.h` and `implot.cpp`, `implot_internal.py` follows
  `implot_internal.h`, `implot_items.py` follows `implot_items.cpp`,
  `implot_demo.py` follows `implot_demo.cpp`. The axis (transforms, locks,
  constraints, fitting), the linear/log/symlog/time locators and the time
  format tables, `SetupFinish`'s padding arithmetic, `UpdateInput`'s pan, zoom
  and box select, the legend, the context menus, subplots, the drag tools,
  every item renderer and the marker tables, and all sixteen built-in
  colormaps with their lookup tables are transcribed; the demo's custom
  candlestick plotter is ported as the demo writes it. The enumerations keep
  the reference's values, so a C++ port that passes `ImPlotAxisFlags_Invert`
  lands on the same bit. What emtk does differently -- items drawn in
  `end_plot` after the fit, axes that follow their data until touched -- is
  said in `implot.py`'s docstring. `widgets/axis.py` and `widgets/plot.py`
  took their first arithmetic from the same reference.
- **[ImPlot3D](https://github.com/brenocq/implot3d)** (Breno Cunha Queiroz,
  MIT; read at commit 6cbefa9) -- `implot3d.py` follows `implot3d.h`,
  `implot3d_internal.h` and `implot3d.cpp`, `implot3d_items.py` follows
  `implot3d_items.cpp`, `implot3d_demo.py` follows `implot3d_demo.cpp`. The
  rotation quaternion and its animation, the box's active faces and axis-edge
  lookup tables, the locators, the input bindings, the item renderers and
  their depth sort are transcribed; the cube, icosphere and duck meshes are
  extracted from `implot3d_meshes.cpp` by `tools/port_implot3d_meshes.py`
  rather than retyped. The duck is "Rubber Duck" by Poly by Google (CC-BY,
  via Poly Pizza), as the reference credits it. What it draws goes through
  the painter's triangles, which is why the painter grew the optional
  `gradient_triangle` and `image_triangle`.

## Porting another one

The data half of a port — enums, palettes, option structs, keyword tables — is
mechanical and is *not* to be typed by hand; the body half is transliterated
line by line against `emtk.im` (`ctx.draw` = `ImDrawList`, `ctx.io` =
`ImGuiIO`, `ctx.layout` = the cursor, `ctx.button_behavior` =
`ButtonBehavior`):

```bash
python tools/port_imgui_widget.py \
    ~/dev/chisurf/junk/imgui/imgui_widgets.cpp --module knobs --class Knob \
    --origin "imgui -- Dear ImGui, MIT"
```

It extracts the data, emits `def knobs(ctx, ...)` with every public method's
C++ body pasted in as comment blocks (each line annotated with the `ctx.`
spelling of the ImGui names it uses), wraps it as `class Knob(ImWidget)`,
writes a test on `emtk.testing.RecordingPainter`, registers the module in
`CONTROL_MODULES`, regenerates the lazy name map, and prints a porting
checklist — which primitives, IO fields, IDs, style vars and popups the source
touches — plus the methods still to write.

A port that merely runs is not evidence. Porting the reference's own demo is
how this toolkit was found to be wrong twenty-two times; that is why
`tests/test_imgui_demo_remaining.py` exists and why its count may not fall.
