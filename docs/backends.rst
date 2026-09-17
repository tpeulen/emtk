Painter backends
==================

A backend is a class that implements the :class:`~emtk.painter.Painter`
protocol. ``emtk.painter.REQUIRED_OPERATIONS`` lists what it must do;
``OPTIONAL_OPERATIONS`` may be left out, and ``ACCELERATIONS`` are faster
spellings of what the helpers already decompose.

Qt painter
------------

``emtk.qt_painter.QtPainter`` draws through a ``QPainter``. It is the
reference implementation: the images it produces were byte-identical to the
direct ``QPainter`` calls the chrome used before the painter interface
existed, and a test asserted it.

Importing this module does not pull Qt into the process at import time.
The class is built inside the constructor, so a headless test never pays
the import cost.

Qt host
---------

``emtk.qt_host.ControlHost`` is a ``QWidget`` that knows nothing about
any particular control. It paints whatever it was given through
:class:`~emtk.qt_painter.QtPainter` and forwards presses, drags, wheels
and keys. One widget and not one per control, because each would
re-derive the same four event translations.

Pillow painter and Tk host
----------------------------

For an application that should ship **no GUI toolkit at all**.
``emtk.pil_painter.PilPainter`` is the painter contract on a Pillow image:
the same atlas glyphs, clip rule and pixel-centre triangle fill as
:class:`~emtk.testing.PixelPainter`, with the inner loops in Pillow's C, so
a 1080x720 application frame costs about five milliseconds instead of more
than a second. Tests hold it to ``PixelPainter`` pixel for pixel where the
arithmetic is the same.

``emtk.tk_host.TkHost`` presents those frames in a ``tkinter`` window --
standard library, so a frozen application carries Tcl/Tk (a few megabytes)
instead of a Qt binding. Tk owns the window, the event loop and the
clipboard and draws nothing itself. Keys and modifiers are translated into
the Qt values :mod:`emtk.keys` uses, including Qt's macOS convention that
Command reports as Control, so a control written against the Qt host moves
across unchanged::

    from emtk.tk_host import TkHost

    host = TkHost(App(gui), title="tool", size=(800, 600))
    host.run()

One process hosts one toolkit: on macOS a Tk root created beside a
``QApplication`` aborts the interpreter, so ``TkHost`` refuses with a
``RuntimeError`` instead.

GPU quad painter
------------------

``emtk.quad_painter.QuadPainter`` builds one interleaved vertex array
that a GPU shader turns into the whole interface in a single draw call.
Each quad is six vertices (two triangles, no index buffer) carrying
position, UV, colour and clip rectangle.

Why this exists is measured: the ``QPainter`` path cost 9.6 ms of a
21 ms frame with a quarter-million beads on screen.

wgpu host
-----------

emtk is **WGSL-native**, and this is the GPU path the toolkit is built
around. ``emtk/wgsl/ui.wgsl`` is the shader -- one file, in the toolkit,
loaded by ``emtk.wgsl.load_wgsl`` -- and an application that draws emtk's
interface inside its own render pass loads the *same* file rather than
keeping a second copy of it. Two copies of one pipeline's shader are two
things to keep in step, and they do not stay in step.

``emtk.wgpu_host.WgpuControlHost`` is a Qt widget that draws a control
through :class:`~emtk.quad_painter.QuadPainter`. Qt's job is a window;
``rendercanvas`` turns that into a surface, and nothing is rasterised on
the CPU. It forwards presses, drags, wheels and keys exactly as the Qt host
does, and swaps in at a call site by changing the name::

    from emtk.wgpu_host import WgpuControlHost

    widget = WgpuControlHost(editor, on_change=save)

``emtk.wgpu_host.WgpuRenderer`` is the half that needs **no window and no
toolkit**. Give it a texture view and it draws into it; give it nothing and
``grab()`` renders offscreen and hands back a NumPy array::

    from emtk.wgpu_host import WgpuRenderer

    renderer = WgpuRenderer()
    painter = renderer.painter()
    painter.fill_rect(4, 4, 40, 20, (255, 0, 0, 255))
    pixels = renderer.grab(painter, 64, 32)   # (32, 64, 4) uint8

That is what makes the GPU path checkable: headless green is not the same
as the interface being there, and a test that measures ink and its bounding
box against ``PixelPainter`` is worth more than any assertion about calls
made.

The whole interface -- panels, menus, text and images -- is **one** draw,
and ``renderer.draw_calls`` says so. Two decisions buy that: the clip
rectangle rides on the *vertex* rather than being a scissor rect, and a
rectangle samples the atlas's opaque block rather than taking a second
pipeline.

Images go through a second texture, selected by a **negative u**: an
image's u is ``-(1 + texel_x / width)`` while every glyph and rectangle u
is a texel coordinate ``>= 0``, so the fragment shader picks the texture
from the sign alone. That keeps one draw call and keeps images in the
interface's draw order -- text drawn after an image lands *on* it.
``emtk.gpu_atlas.ImageAtlas`` is where a :class:`~emtk.texture.Texture` is
placed, and the host installs it as the painter's ``image_uv_resolver``.

What the host uploads lives in ``emtk.gpu_atlas``: the combined glyph atlas
(baked rows on top, the runtime cache underneath -- a host that uploads only
the baked half draws the *wrong glyph* for anything the baker never saw),
the image atlas, and the negative-u encoding. That module names no toolkit
and needs no adapter, so those conventions are testable anywhere.

There is deliberately **one** GPU host and **one** shading language. An
OpenGL/GLSL host existed alongside this one and was retired: two shaders for
one pipeline are two things to keep in step, and the way that fails is not a
crash but a panel that looks slightly wrong in one of them, months later.

Pyodide / browser
------------------

The same widget code runs in a browser under Pyodide. A browser host
targets a canvas, implements the painter in JavaScript, and feeds pointer
and key events from the DOM.

``emtk.testing.PixelPainter``
````````````````````````````````

Pure Python, no window, no toolkit, no display.

:class:`~emtk.testing.PixelPainter` rasterises the six required operations
onto an RGBA buffer, using the baked glyph atlas for text. Screenshots
rendered through it are identical on every machine that runs the same
commit, which is what makes golden-image tests possible.

.. image:: _screenshots/hello_world.png
   :alt: A screenshot rendered by PixelPainter — identical on every machine

::

    from emtk.testing import PixelPainter, render

    def gui():
        im.begin("Demo", (0, 0, 100, 60))
        im.button("OK")
        im.end()

    painter = render(gui, (0, 0, 100, 60))
    assert painter.width == 100
    assert painter.height == 60
