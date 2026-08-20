# cmtk

**Dear ImGui for Python — with nothing to compile.**

An immediate-mode GUI toolkit that draws through a *painter*: six operations, no
toolkit, no native extension, no build step. It runs wherever Python runs — on
a desktop OpenGL context, in a browser under Pyodide, or in a test with no
window at all — and the same widget code runs on all three.

```python
from cmtk import im

with im.frame(painter, (0, 0, 320, 200)):
    im.begin("Hello, world!")
    im.text("This is some useful text.")
    changed, alpha = im.slider_float("alpha", alpha, 0.0, 1.0)
    if im.button("Button"):
        counter += 1
    im.same_line()
    im.text("counter = %d" % counter)
    im.end()
```

MIT licensed. No dependencies — not numpy, not a toolkit, not a compiler.
It is a re-implementation, and [CREDITS.md](CREDITS.md) names what it was
written by reading — Dear ImGui above all — with the upstream MIT texts in
`licenses/`.

## Why

Dear ImGui is the right design for tools: the interface is the code that draws
it, there is no retained widget tree to keep in sync with your data, and a
panel is a function you can delete. Its reasons for existing are ours.

What it cannot do is ship inside a Python program without a build. The
established bindings are C++ extension modules: a wheel per platform per Python
version, a compiler for anything unwheeled, and nothing at all in a browser
under Pyodide or in an environment where you cannot install binaries. For a
scientific tool that has to run on a workstation, a cluster login node, a
colleague's laptop and a web page, that is the whole problem.

cmtk is the same design, written in Python, drawing through an interface small
enough that any surface can implement it:

| | Dear ImGui | pyimgui / imgui-bundle | cmtk |
|---|---|---|---|
| immediate mode | yes | yes | yes |
| needs a compiler | yes | pre-built wheels, else yes | **no** |
| runs under Pyodide / in a browser | no | no | **yes** |
| new platform | port the backend | wait for a wheel | **implement six methods** |
| pure Python | no | no | **yes** |

The cost is real and worth naming: Python draws a frame more slowly than C++,
so cmtk suits tool and instrument interfaces — panels, tables, plots, editors —
rather than a game's HUD at 240 Hz.

## Compatibility with Dear ImGui

Porting is mechanical. Three rules and no thought:

| C++ | Python |
|---|---|
| `ImGui::Button("Save")` | `im.button("Save")` — `::` becomes `.` |
| `ImGui::SliderFloat` | `im.slider_float` — `CamelCase` becomes `snake_case` |
| `ImGui::Checkbox("x", &b)` | `changed, b = im.checkbox("x", b)` |

The third is the only place Python forces a difference: C++ writes results
through `bool*`, `float*` and `char*`, and Python has no pointers, so the value
comes back beside the changed flag. That is what pyimgui and imgui-bundle do,
so a port from C++ *or* from either binding lands unchanged.

Enums follow: `ImGuiCol_Button` → `im.Col.BUTTON`, `ImGuiDir_Left` →
`im.Dir.LEFT`, `ImGuiItemFlags_ButtonRepeat` → `im.ItemFlags.BUTTON_REPEAT`.

**All 362 published `ImGui::` names and all 60 `ImDrawList::` methods translate,
and all 187 sections of `imgui_demo.cpp` are ported and driven as tests** —
including docking, keyboard navigation, table sizing and `ImGuiListClipper`.
`tests/test_imgui_api_coverage.py` and `tests/test_imgui_demo_remaining.py`
prove both, and neither figure may fall.

That is not decoration. Porting the reference's own demo is how the toolkit was
found to be wrong twenty-two times — a label claiming a full-width item so the
buttons beside it were dead, `IsItemDeactivated` firing for widgets nobody had
touched, `TableNextColumn` one column out of step, `ImVec2(120, 0)` taken
literally so a button was zero pixels tall. A port that runs is the only
evidence that a re-implementation matches.

## What a host provides

Three things, and that is the whole contract:

1. **A painter.** `cmtk.painter.REQUIRED_OPERATIONS` is the list, and it is a
   list in code rather than a promise in prose: `fill_rect`, `stroke_rect`,
   `gradient_rect`, `text`, `push_clip`/`pop_clip`, `fill_triangle`, plus
   `text_width` and `line_height` to measure with. `OPTIONAL_OPERATIONS`
   (`image`, `set_font`, `text_rotated`) add what cannot be decomposed — cmtk
   asks `io.BackendFlags` what the painter in hand can do and falls back
   visibly where it cannot — and `ACCELERATIONS` are faster spellings of what
   the required ones already do, which change nothing on screen.
   `tests/test_the_painter_contract.py` drives the whole widget set through a
   host that has the required operations and *nothing* else, so the claim is
   checked rather than asserted. `cmtk.testing.RecordingPainter`
   records instead of drawing, which is what makes a widget testable with no
   window.
2. **Pointer and key state**, in `im.IO`: where the pointer is, which buttons
   went down or up this delivery, the modifiers, the wheel.
3. **Time.** Dear ImGui reads no clock — the backend sets `io.delta_time` and
   the context accumulates it. cmtk reads the wall clock by default; set
   `io.wall_clock = False` and drive `delta_time` yourself for a fixed step, a
   recorded session, or a test of anything timing-dependent.

## Hit-testing is a by-product of drawing

There is no second list of where things are. Every widget calls
`ItemAdd(box, id)` **as it draws**, so a widget cannot be clickable where it is
not visible. Between windows the rule is the same one shape up: one list in
display order, walked forward to paint and backward to hit-test. A window that
is drawn but takes no input says so with a flag on its entry, rather than by
being absent from a second list — a second list is the thing that drifts out of
step with the first.

## Keeping last frame's drawing

A host that caches what it drew has to decide when to throw it away, and there
is a wrong way that looks right: a revision counter the control's writers bump.
The rule it needs ("everything that writes must bump") lives in every writer,
and the writer that forgets produces no error and no missing pixel -- it
produces a correct picture of an *older moment*, which reads to a user as "the
buttons do not work". A playback panel once read `1 / 464` through an entire
animation that way; every press worked, and nothing on screen said so.

`cmtk.redraw` is the other way. A control says what it is about to draw --

```python
def content_key(self):
    return (self.frame, self.total, self.playing, self.stride)
```

-- and `redraw.content_key(control)` reads it, `redraw.changed(before, now)`
compares. There is nothing to remember, because the key is computed from the
same state the drawing reads. A control that cannot summarise itself returns
`redraw.always()` and is redrawn every frame: slower, never stale, and the
honest default. (`always()` is a fresh object each call, not a shared sentinel:
keys are usually tuples, and tuple equality short-circuits on element
*identity* -- a shared sentinel would compare equal to itself in the one place
it matters most.)

`redraw.BlockCache` is the host side of it: give it `(key, make)` per block and
it builds only what moved, keeps what did not, and forgets the blocks that
stopped being drawn -- the third being the one a hand-rolled dict leaks.

## Layout

```
cmtk/im_core.py       the context, windows, ItemAdd, ButtonBehavior   (imgui.cpp)
cmtk/im_widgets.py    everything built on those                        (imgui_widgets.cpp)
cmtk/im.py            the facade you import                            (imgui.h)
cmtk/drawlist.py      ImDrawList over a painter
cmtk/painter.py       the six operations, and the optional three
cmtk/redraw.py        content keys and the block cache: when to redraw
cmtk/widgets/         retained controls: lists, trees, tables, editors, plots
cmtk/testing.py       RecordingPainter
cmtk/atlas/           the baked glyph atlas -- committed, so using cmtk needs no font engine
tools/                not shipped: bake the atlas, scaffold an ImGui port, regenerate the name map
```

The three-file split at the top is the reference's own, and for the same
reason: the widgets are written *against* the context, so one module would have
to import the thing importing it.

## Testing a widget

No window, no toolkit, no event loop:

```python
from cmtk import im
from cmtk.testing import RecordingPainter

io, storage = im.IO(), {}
painter = RecordingPainter()
with im.frame(painter, (0, 0, 200, 80), io=io, storage=storage) as ctx:
    im.button("Press me")
    box = ctx.get_item_rect()

io.mouse_pos = (box[0] + 4, box[1] + 4)     # the pointer arrives
io.mouse_down[0] = io.mouse_clicked[0] = True
# ...draw again, then release, and the button reports its click.
```

`examples/clicking.py` is that, end to end. `pytest` runs the suite — 952
tests, under four seconds, no display required.

## Status

Beta. The API is Dear ImGui's, so it is stable by construction; what moves is
what has been implemented behind it. cmtk grew inside
[chimol](https://github.com/tpeulen/chimol), a molecular viewer, and was moved
out once its own tests, examples and documentation stood on their own.
