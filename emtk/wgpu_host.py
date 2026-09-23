"""A wgpu host: Qt opens the window, the GPU draws the interface.

What this replaces
------------------
:mod:`.qt_host` puts a control in a ``QWidget`` and paints it with
:class:`~.qt_painter.QtPainter` -- which means every rectangle and every
glyph of the interface is rasterised on the **CPU**, every frame. Measured on
a GPU viewer carrying a quarter-million beads, that path cost **9.6 ms of a
21 ms frame**: enough that a timer was added to let the panel go deliberately
stale rather than repaint when it changed.

The other painter already exists and already works.
:class:`~.quad_painter.QuadPainter` emits *vertices* instead of rasterising;
a frame of interface is a few hundred rectangles and a few thousand glyphs,
which as vertices is kilobytes and no rasterisation at all. What was missing
was the consumer *inside emtk*, so that any Qt window gets it. That is this
module.

The QPainter host stays. It is the reference this output is compared
against, and it is the fallback where there is no adapter.

Why WGSL and not GLSL
---------------------
emtk is **WGSL-native**. ``wgsl/ui.wgsl`` is the toolkit's shader, and it is
the *same file* a wgpu application embedding emtk loads -- a second shading
language would mean two shaders to keep in step for one pipeline, and they
would not stay in step: the failure is not a crash but a panel that looks
subtly wrong in one of the two programs, months later. Qt's job here shrinks to owning a window and
handing wgpu a surface to present to.

One draw call, and why that is the whole design
-----------------------------------------------
The entire interface -- panels, menus, text, images -- is **one** ``draw``.
Two things make that possible and both are unusual:

* **The clip rectangle rides on the vertex** rather than being a scissor
  rect. A scissor would split the frame into one draw call per clip, and
  menus alone would multiply that.
* **A rectangle samples the atlas's opaque block.** There is no "is this
  text" branch and no second pipeline: the difference between a panel
  background and a letter is which texels the quad points at.

:attr:`WgpuRenderer.draw_calls` counts them, and a test asserts the number
is one.

Premultiplied out, always
-------------------------
The fragment stage emits ``vec4(rgb * a, a)`` and the blend state is
``one, one_minus_src_alpha``. Straight alpha is the trap here: it darkens
every antialiased glyph edge, which is invisible on a dark panel and obvious
the moment the background is white.

Images
------
Image quads point at a **second** texture and say so by carrying a
**negative u** -- see :func:`~.gpu_atlas.image_u`. The fragment stage tests
``u < -0.5`` and selects. That keeps one draw call, one vertex format and
one pipeline, and it keeps images in the interface's own draw order, so text
drawn after an image lands *on* it rather than under it.

Nothing in :class:`~.quad_painter.QuadPainter` had to change for this. The
painter already asks the host where an image lives, through
``image_uv_resolver``; the encoding is the *host's* answer, which is exactly
where knowledge of the host's own textures belongs.

The renderer needs no window and no toolkit
-------------------------------------------
:class:`WgpuRenderer` is a plain object. It draws into a view someone else
supplies -- a window's swapchain texture, or, through :meth:`~WgpuRenderer.grab`,
an offscreen one it makes itself. That is what makes the GPU path testable
without a display: an adapter is all it takes, and the result is a NumPy
array to assert on.

Only :func:`WgpuControlHost` needs Qt, and it needs it for a *window*:
``rendercanvas`` turns that window into a surface, which is the whole of the
toolkit's involvement. Every heavy import here happens on first **use**, so
``import emtk.wgpu_host`` in a headless process is as cheap and as harmless
as importing :mod:`.qt_host` there.

Bind groups
-----------
The shader's bindings are **group 1**, and group 0 is left empty. That is
not an oversight. An application that embeds emtk's interface in its own
render pass typically prepends a shared prelude declaring group 0 to every
shader it loads; a file that claimed group 0 could not be that file too.
Binding one empty group is what one shader costs instead of two.
"""
from __future__ import annotations

from collections.abc import Callable

from .font import DEFAULT_FONT_PT
from .gpu_atlas import (
    ATTRIBUTES,
    BAKED_FONT_PT,
    IMAGE_ATLAS_SIZE,
    VERTEX_BYTES,
    ImageAtlas,
    atlas_pixels,
    image_texel,
    image_u,
)
from .wgsl import UI_SHADER, load_wgsl

__all__ = [
    "WgpuRenderer",
    "WgpuControlHost",
    "ImageAtlas",
    "wgpu_host_class",
    "ui_bind_group_layout_entries",
    "ui_bind_group_entries",
    "ui_samplers",
    "make_wgpu_control_host",
    "default_device",
    "image_u",
    "image_texel",
    "UI_SHADER",
    "TEXTURE_FORMAT",
    "UNIFORM_FLOATS",
    "BAKED_FONT_PT",
    "IMAGE_ATLAS_SIZE",
]

#: The format an offscreen :meth:`WgpuRenderer.grab` renders into. A window
#: uses whatever its surface prefers, which is usually a ``*-srgb`` variant;
#: this one is linear, so a grab reads back the bytes the shader wrote and a
#: test comparing it against the CPU rasteriser compares like with like.
TEXTURE_FORMAT = "rgba8unorm"

#: Floats in the shader's ``UiUniforms``: viewport, atlas, atlas2 -- six,
#: padded to eight. WGSL rounds a uniform struct's size up to a multiple of
#: 16 bytes, and a buffer smaller than the struct is a validation error on
#: some backends and silence on others, which is the worse half.
UNIFORM_FLOATS = 8


# --------------------------------------------------------------------------- #
# Lazy imports
# --------------------------------------------------------------------------- #
def _numpy():
    """NumPy, imported on use."""
    import numpy  # noqa: PLC0415

    return numpy


def _wgpu():
    """The GPU seam, :mod:`emtk.gpu.api`, spelled like the binding.

    Not ``wgpu`` itself: the constants are the specification's and the
    adapter comes from whichever backend is live -- ``wgpu-py`` on the
    desktop, the browser's ``navigator.gpu`` in a page -- so this renderer
    draws in both without knowing which. Importing the seam imports no
    binding; asking it for an adapter without ``wgpu`` installed raises
    ``ImportError`` there, the same failure :func:`.qt_host.host_class`
    gives without Qt.
    """
    from .gpu import api  # noqa: PLC0415

    return api


#: The adapter and device shared by every renderer that did not ask for its
#: own. Requesting a device is not free and a machine has one GPU; a test
#: file that made one per test spends more time in the driver than in the
#: tests.
_DEVICE = None


def default_device():
    """The process-wide ``GPUDevice``, requested once.

    Returns
    -------
    wgpu.GPUDevice

    Raises
    ------
    RuntimeError
        If no adapter can be had. Raised rather than returning ``None``,
        which a caller would carry three calls further before failing on
        something that does not mention the GPU.
    """
    global _DEVICE
    if _DEVICE is not None:
        return _DEVICE
    wgpu = _wgpu()
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    if adapter is None:  # pragma: no cover - a machine with no GPU at all
        raise RuntimeError(
            "no wgpu adapter on this machine; emtk.qt_host is the fallback"
        )
    _DEVICE = adapter.request_device_sync()
    return _DEVICE


# --------------------------------------------------------------------------- #
# The shader's bindings, for anyone who draws with it
# --------------------------------------------------------------------------- #
def ui_bind_group_layout_entries() -> list:
    """The group-1 bind-group layout ``ui.wgsl`` declares, as layout entries.

    One definition for every pipeline that compiles ``ui.wgsl`` -- this
    renderer's, and an application's that draws emtk's interface inside its
    own render pass. A copy kept by the application goes stale the moment the
    shader gains a binding, and the failure is not an error at the change but
    a pipeline that no longer validates: a window cleared to its error colour.

    Bindings: 0 the uniforms (``UiUniforms``), 1 the glyph atlas, 2 its
    linear sampler, 3 the image atlas, 4 its linear sampler, 5 the nearest
    sampler for ``Texture(filter="nearest")``.
    """
    wgpu = _wgpu()
    fragment = wgpu.ShaderStage.FRAGMENT
    texture = {"sample_type": wgpu.TextureSampleType.float}
    sampler = {"type": wgpu.SamplerBindingType.filtering}
    return [
        # VERTEX|FRAGMENT: the vertex places the quad, the fragment decodes
        # the image quads' uvs against `atlas2`.
        {"binding": 0, "visibility": wgpu.ShaderStage.VERTEX | fragment,
         "buffer": {"type": wgpu.BufferBindingType.uniform}},
        {"binding": 1, "visibility": fragment, "texture": dict(texture)},
        {"binding": 2, "visibility": fragment, "sampler": dict(sampler)},
        # The image atlas. Zero texels are transparent, so it binds
        # harmlessly empty for an interface that shows no pictures.
        {"binding": 3, "visibility": fragment, "texture": dict(texture)},
        {"binding": 4, "visibility": fragment, "sampler": dict(sampler)},
        # Nearest texel, for textures drawn block by block (a histogram).
        {"binding": 5, "visibility": fragment, "sampler": dict(sampler)},
    ]


def ui_samplers(device) -> tuple:
    """``(linear, nearest)`` samplers for :func:`ui_bind_group_entries`.

    Linear for the atlases -- the glyphs are baked supersampled and sampled
    down, so filtering is what turns coverage into a smooth edge -- and
    nearest for textures drawn texel by texel.
    """
    wgpu = _wgpu()
    linear = device.create_sampler(
        label="emtk.ui.sampler",
        mag_filter=wgpu.FilterMode.linear, min_filter=wgpu.FilterMode.linear,
    )
    nearest = device.create_sampler(
        label="emtk.ui.sampler.nearest",
        mag_filter=wgpu.FilterMode.nearest, min_filter=wgpu.FilterMode.nearest,
    )
    return linear, nearest


def ui_bind_group_entries(uniform_buffer, atlas_view, image_view,
                          linear_sampler, nearest_sampler) -> list:
    """The group-1 bind-group entries matching :func:`ui_bind_group_layout_entries`."""
    return [
        {"binding": 0, "resource": {"buffer": uniform_buffer, "offset": 0,
                                    "size": uniform_buffer.size}},
        {"binding": 1, "resource": atlas_view},
        {"binding": 2, "resource": linear_sampler},
        {"binding": 3, "resource": image_view},
        {"binding": 4, "resource": linear_sampler},
        {"binding": 5, "resource": nearest_sampler},
    ]


# --------------------------------------------------------------------------- #
# The renderer
# --------------------------------------------------------------------------- #
class WgpuRenderer:
    """Draw a :class:`~.quad_painter.QuadPainter` frame in one call.

    Separate from the widget on purpose, and more usefully so than in the
    OpenGL host: this needs **no window and no toolkit**. Give it a texture
    view and it draws into it; give it nothing and :meth:`grab` makes one and
    hands back the pixels. That is how the GPU path is tested on a machine
    with no display.

    Parameters
    ----------
    atlas : emtk.font.Atlas, optional
        The glyph atlas. Loaded if not given.
    images : ImageAtlas, optional
        Where :meth:`~.quad_painter.QuadPainter.image` handles are placed.
        One is made if none is given.
    device : wgpu.GPUDevice, optional
        Defaults to :func:`default_device`.
    format : str, optional
        The colour format of the views this will draw into. A pipeline is
        built per format, so a renderer that draws into a window *and* into
        an offscreen grab keeps both.

    Attributes
    ----------
    draw_calls : int
        How many draws the last frame issued. The whole design is this
        number staying at one -- 0 for an empty frame.

    Examples
    --------
    >>> import numpy as np, pytest
    >>> renderer = WgpuRenderer()                        # doctest: +SKIP
    >>> painter = renderer.painter()                     # doctest: +SKIP
    >>> painter.fill_rect(4, 4, 40, 20, (255, 0, 0, 255))  # doctest: +SKIP
    >>> pixels = renderer.grab(painter, 64, 32)          # doctest: +SKIP
    >>> pixels.shape                                     # doctest: +SKIP
    (32, 64, 4)
    """

    def __init__(self, atlas=None, images=None, device=None,
                 format: str = TEXTURE_FORMAT) -> None:
        from .font import load_atlas  # noqa: PLC0415

        self.atlas = atlas if atlas is not None else load_atlas()
        self.images = images if images is not None else ImageAtlas()
        self.format = str(format)
        self.draw_calls = 0
        self._device = device
        self._module = None
        self._layout = None
        self._empty_layout = None
        self._empty_group = None
        self._sampler = None
        #: ``format -> pipeline``. One per colour format drawn into; a
        #: pipeline is bound to the format of its target and a window's is
        #: not the offscreen one's.
        self._pipelines: dict = {}
        self._atlas_texture = None
        self._atlas_size = (1, 1)
        #: The glyph-cache version last uploaded. Tracked **per renderer**,
        #: by version rather than by a dirty list: a list that is consumed
        #: can only ever feed one consumer, and there are several devices in
        #: play -- a window and an offscreen grab, each with its own texture.
        self._glyph_version = None
        self._image_texture = None
        #: ``(id(image atlas), its version)``. The identity matters as well
        #: as the version: a renderer handed a *different* image atlas whose
        #: version happens to match would otherwise keep drawing the old
        #: one's texels.
        self._image_version = None
        self._vertex_buffer = None
        self._vertex_capacity = 0
        self._uniform_buffer = None
        self._bind_group = None
        self._bind_key = None

    # -- lifecycle ------------------------------------------------------- #
    @property
    def device(self):
        """The ``GPUDevice`` this draws with, requested on first use."""
        if self._device is None:
            self._device = default_device()
        return self._device

    def painter(self, font_pt: float = DEFAULT_FONT_PT, scale: float = 1.0):
        """A :class:`~.quad_painter.QuadPainter` wired to this renderer.

        Parameters
        ----------
        font_pt : float, optional
            Point size of the interface font. Converted to the atlas's
            ``font_scale``: the atlas is a bitmap face, so there is no
            second size to bake.
        scale : float, optional
            Device pixels per interface pixel.

        Returns
        -------
        emtk.quad_painter.QuadPainter
            With :attr:`~.quad_painter.QuadPainter.image_uv_resolver` already
            pointed at this renderer's image atlas -- which is the one thing
            a caller building the painter itself reliably forgets, and the
            symptom is every image drawing as a flat tinted box.
        """
        from .quad_painter import QuadPainter  # noqa: PLC0415

        baked = float(getattr(self.atlas, "font_pt", BAKED_FONT_PT))
        painter = QuadPainter(
            atlas=self.atlas,
            scale=scale,
            font_scale=float(font_pt) / baked if baked else 1.0,
        )
        painter.image_uv_resolver = self.images.region
        return painter

    def _shader(self):
        """The compiled ``ui.wgsl`` module, built once per renderer."""
        if self._module is None:
            self._module = self.device.create_shader_module(
                label="emtk.ui", code=load_wgsl(UI_SHADER)
            )
        return self._module

    def _layouts(self):
        """``(empty group 0 layout, group 1 layout)``, built once.

        Group 0 is empty here and declared by an embedding application's
        prelude there; see the module docstring. An empty layout is legal,
        costs nothing, and is what lets both compile the *same* source.
        """
        if self._layout is not None:
            return self._empty_layout, self._layout
        wgpu = _wgpu()
        device = self.device
        self._empty_layout = device.create_bind_group_layout(
            label="emtk.ui.group0", entries=[]
        )
        self._empty_group = device.create_bind_group(
            layout=self._empty_layout, entries=[]
        )
        self._layout = device.create_bind_group_layout(
            label="emtk.ui.group1", entries=ui_bind_group_layout_entries()
        )
        return self._empty_layout, self._layout

    def pipeline(self, format: str | None = None):
        """The render pipeline for *format*, built once per format.

        Parameters
        ----------
        format : str, optional
            Defaults to :attr:`format`.

        Returns
        -------
        wgpu.GPURenderPipeline
        """
        format = str(format or self.format)
        got = self._pipelines.get(format)
        if got is not None:
            return got

        wgpu = _wgpu()
        device = self.device
        empty_layout, layout = self._layouts()
        module = self._shader()
        # Premultiplied, as `ui.wgsl` outputs. Straight alpha here darkens
        # every antialiased glyph edge against a light background.
        blend = {
            "src_factor": wgpu.BlendFactor.one,
            "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
            "operation": wgpu.BlendOperation.add,
        }
        pipeline = device.create_render_pipeline(
            label=f"emtk.ui[{format}]",
            layout=device.create_pipeline_layout(
                bind_group_layouts=[empty_layout, layout]
            ),
            vertex={
                "module": module,
                "entry_point": "vs_ui",
                "buffers": [
                    {
                        "array_stride": VERTEX_BYTES,
                        "step_mode": "vertex",
                        # position, uv, colour, clip box -- see
                        # :data:`emtk.gpu_atlas.ATTRIBUTES`, which is the
                        # one place the layout is written down.
                        "attributes": [
                            {
                                "format": f"float32x{count}",
                                "offset": offset,
                                "shader_location": location,
                            }
                            for location, count, offset in ATTRIBUTES
                        ],
                    }
                ],
            },
            # No depth attachment: the interface is drawn in the order it
            # was emitted, and that order is what decides what covers what.
            fragment={
                "module": module,
                "entry_point": "fs_ui",
                "targets": [
                    {"format": format, "blend": {"color": blend, "alpha": blend}}
                ],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
        )
        self._pipelines[format] = pipeline
        return pipeline

    # -- textures -------------------------------------------------------- #
    def _upload_atlas(self) -> None:
        """Create the glyph texture once, then patch the cache rows.

        Both halves, always: ``Atlas.cell_of`` returns coordinates in the
        *combined* space, so a host holding only the baked half samples past
        the end of its texture for any character the baker never saw -- out
        of bounds a hard failure, in bounds silently the **wrong glyph**.
        See :func:`~.gpu_atlas.atlas_pixels`.

        The baked rows are uploaded once; only the cache rows underneath are
        re-written, and only when a character has been rasterised since the
        last frame. Rebuilding the whole 640x3835 texture per new glyph
        would put back most of the cost that drawing quads removed.
        """
        np = _numpy()
        wgpu = _wgpu()
        cache = self.atlas.cache
        version = cache.version if cache is not None else -1
        if self._atlas_texture is None:
            pixels = atlas_pixels(self.atlas)
            height, width = int(pixels.shape[0]), int(pixels.shape[1])
            self._atlas_texture = self.device.create_texture(
                label="emtk.ui.glyphs",
                size=(width, height, 1),
                format=wgpu.TextureFormat.rgba8unorm,
                usage=(wgpu.TextureUsage.TEXTURE_BINDING
                       | wgpu.TextureUsage.COPY_DST),
            )
            self.device.queue.write_texture(
                {"texture": self._atlas_texture, "origin": (0, 0, 0)},
                np.ascontiguousarray(pixels),
                {"bytes_per_row": width * 4, "rows_per_image": height},
                (width, height, 1),
            )
            self._atlas_size = (width, height)
            self._glyph_version = version
            return

        if version == self._glyph_version or cache is None:
            return
        patch = np.ascontiguousarray(cache.image)
        rows, width = int(patch.shape[0]), int(patch.shape[1])
        if rows <= 0:
            return
        self.device.queue.write_texture(
            {"texture": self._atlas_texture,
             "origin": (0, int(self.atlas.baked_height), 0)},
            patch,
            {"bytes_per_row": width * 4, "rows_per_image": rows},
            (width, rows, 1),
        )
        self._glyph_version = version

    def _upload_images(self) -> None:
        """Create the image texture once, then write what has changed.

        A live camera frame changes every frame and a colour map almost
        never; both go through here, so the atlas is asked *what* moved
        rather than re-uploaded whole. See
        :meth:`~.gpu_atlas.ImageAtlas.dirty_since`.
        """
        np = _numpy()
        wgpu = _wgpu()
        images = self.images
        identity = id(images)
        if self._image_texture is None or self._image_version[0] != identity:
            self._image_texture = self.device.create_texture(
                label="emtk.ui.images",
                size=(images.width, images.height, 1),
                format=wgpu.TextureFormat.rgba8unorm,
                usage=(wgpu.TextureUsage.TEXTURE_BINDING
                       | wgpu.TextureUsage.COPY_DST),
            )
            self._image_version = (identity, -1)
            self._bind_group = None

        if self._image_version[1] == images.version:
            return
        dirty, version = images.dirty_since(self._image_version[1])
        if dirty is None:
            dirty = [(0, 0, images.width, images.height)]
        for x, y, w, h in dirty:
            patch = np.ascontiguousarray(images.pixels[y:y + h, x:x + w])
            self.device.queue.write_texture(
                {"texture": self._image_texture, "origin": (int(x), int(y), 0)},
                patch,
                {"bytes_per_row": int(patch.shape[1]) * 4,
                 "rows_per_image": int(patch.shape[0])},
                (int(patch.shape[1]), int(patch.shape[0]), 1),
            )
        self._image_version = (identity, version)

    def _bind(self, width: float, height: float):
        """The group-1 bind group for a viewport of *width* x *height*.

        Kept between frames and rebuilt only when something in it moved: the
        uniform buffer is written in place, so a window that is not being
        resized rebuilds nothing at all.
        """
        np = _numpy()
        wgpu = _wgpu()
        device = self.device
        if self._sampler is None:
            self._sampler, self._nearest_sampler = ui_samplers(device)
        uniforms = np.zeros(UNIFORM_FLOATS, dtype=np.float32)
        uniforms[0:2] = (float(width), float(height))
        uniforms[2:4] = (float(self._atlas_size[0]), float(self._atlas_size[1]))
        uniforms[4:6] = (float(self.images.width), float(self.images.height))
        if self._uniform_buffer is None:
            self._uniform_buffer = device.create_buffer_with_data(
                data=uniforms,
                usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
            )
        else:
            device.queue.write_buffer(self._uniform_buffer, 0, uniforms)

        key = (id(self._atlas_texture), id(self._image_texture))
        if self._bind_group is None or self._bind_key != key:
            _empty_layout, layout = self._layouts()
            self._bind_group = device.create_bind_group(
                label="emtk.ui.bind",
                layout=layout,
                entries=ui_bind_group_entries(
                    self._uniform_buffer,
                    self._atlas_texture.create_view(),
                    self._image_texture.create_view(),
                    self._sampler,
                    self._nearest_sampler,
                ),
            )
            self._bind_key = key
        return self._bind_group

    def _upload_vertices(self, data):
        """The vertex buffer holding *data*, grown only when it has to.

        An interface settles at a size within a frame or two, so after that
        a repaint writes into a live buffer rather than allocating one --
        which is the difference between a redraw and a redraw plus a
        driver allocation, every frame.
        """
        wgpu = _wgpu()
        payload = data.tobytes()
        if self._vertex_buffer is None or len(payload) > self._vertex_capacity:
            self._vertex_buffer = self.device.create_buffer(
                label="emtk.ui.vertices",
                size=max(len(payload), 4096),
                usage=wgpu.BufferUsage.VERTEX | wgpu.BufferUsage.COPY_DST,
            )
            self._vertex_capacity = self._vertex_buffer.size
        self.device.queue.write_buffer(self._vertex_buffer, 0, payload)
        return self._vertex_buffer

    # -- drawing --------------------------------------------------------- #
    def draw(self, render_pass, vertices, width: float, height: float,
             format: str | None = None) -> int:
        """Encode the interface into *render_pass*. One draw.

        Parameters
        ----------
        render_pass : wgpu.GPURenderPassEncoder
            Someone else's pass -- a 3-D viewport's second pass, say. The
            interface is drawn *into* it rather than over it in a pass of
            its own, so that what a program has already drawn stays under
            the panel with no extra target and no composite.
        vertices : numpy.ndarray or QuadPainter
            ``(n, 12)`` float32 straight from
            :meth:`~.quad_painter.QuadPainter.vertices`, or the painter
            itself.
        width, height : float
            Viewport size in **device** pixels -- the same space the vertex
            positions are in.
        format : str, optional
            The colour format of the pass's target. Defaults to
            :attr:`format`; pass it when drawing into a window whose surface
            prefers something else, or the pipeline will not match the
            attachment and wgpu will say so.

        Returns
        -------
        int
            :attr:`draw_calls`: 1 for any non-empty frame, 0 for an empty
            one.
        """
        np = _numpy()
        self.draw_calls = 0
        if hasattr(vertices, "vertices"):
            vertices = vertices.vertices()
        data = np.ascontiguousarray(vertices, dtype=np.float32)
        count = int(data.shape[0])
        if count == 0:
            return 0

        # Before the draw, not after: a glyph rasterised or an image written
        # while the quads were being built is needed by *this* frame, and
        # uploading it next frame shows one frame of the wrong texels.
        self._upload_atlas()
        self._upload_images()
        bind = self._bind(width, height)
        buffer = self._upload_vertices(data)

        render_pass.set_pipeline(self.pipeline(format))
        render_pass.set_bind_group(0, self._empty_group)
        render_pass.set_bind_group(1, bind)
        render_pass.set_vertex_buffer(0, buffer)
        render_pass.draw(count, 1, 0, 0)
        self.draw_calls = 1
        return 1

    def render(self, vertices, width: float, height: float, view,
               background=None, format: str | None = None) -> int:
        """Draw into *view* in a pass of this renderer's own.

        Parameters
        ----------
        vertices : numpy.ndarray or QuadPainter
        width, height : float
            Viewport size in device pixels.
        view : wgpu.GPUTextureView
            What to draw into -- a window's current texture, usually.
        background : tuple, optional
            Cleared to first, as 0-255 RGB(A). ``None`` loads what is
            already there instead, which is what an interface drawn over a
            3-D scene wants.
        format : str, optional

        Returns
        -------
        int
            :attr:`draw_calls`.
        """
        device = self.device
        encoder = device.create_command_encoder(label="emtk.ui")
        attachment = {
            "view": view,
            "resolve_target": None,
            "load_op": "clear" if background is not None else "load",
            "store_op": "store",
        }
        if background is not None:
            attachment["clear_value"] = _clear_value(background)
        render_pass = encoder.begin_render_pass(color_attachments=[attachment])
        drawn = self.draw(render_pass, vertices, width, height, format=format)
        render_pass.end()
        device.queue.submit([encoder.finish()])
        return drawn

    def grab(self, vertices, width: int, height: int, background=(30, 32, 38)):
        """Render offscreen and read the pixels back.

        Parameters
        ----------
        vertices : numpy.ndarray or QuadPainter
        width, height : int
            Size in device pixels.
        background : tuple, optional
            0-255 RGB(A). ``None`` leaves the target transparent.

        Returns
        -------
        numpy.ndarray
            ``(height, width, 4)`` uint8 RGBA.

        Notes
        -----
        This is the half of the design that makes the GPU path *checkable*.
        Headless green is not the same as the app working -- a whole
        interface once went missing behind a clean render and a passing
        suite -- so a test that measures ink, and its bounding box, against
        the CPU rasteriser is worth more than any number of assertions
        about calls made.
        """
        np = _numpy()
        wgpu = _wgpu()
        width, height = int(width), int(height)
        target = self.device.create_texture(
            label="emtk.ui.grab",
            size=(width, height, 1),
            format=TEXTURE_FORMAT,
            usage=(wgpu.TextureUsage.RENDER_ATTACHMENT
                   | wgpu.TextureUsage.COPY_SRC),
        )
        self.render(vertices, width, height, target.create_view(),
                    background=background, format=TEXTURE_FORMAT)
        raw = self.device.queue.read_texture(
            {"texture": target, "origin": (0, 0, 0)},
            {"bytes_per_row": width * 4, "rows_per_image": height},
            (width, height, 1),
        )
        return np.frombuffer(bytes(raw), np.uint8).reshape(height, width, 4)


def _clear_value(background) -> tuple:
    """A 0-255 colour as wgpu's 0-1 clear value.

    Colours are **bytes** in emtk and floats in wgpu. Handing 0-1 floats
    straight through is the mistake this exists to make impossible: it does
    not raise, it draws a black window.
    """
    values = tuple(float(c) / 255.0 for c in background[:4])
    if len(values) == 3:
        values += (1.0,)
    return values


# --------------------------------------------------------------------------- #
# The widget
# --------------------------------------------------------------------------- #
#: The built class, cached. Rebuilding it per widget would give every host
#: its own type, which breaks ``isinstance``.
_HOST_CLASS = None


def _render_widget():
    """``rendercanvas``'s Qt widget, imported on use.

    Raises
    ------
    ImportError
        If Qt or ``rendercanvas`` is missing.

    Notes
    -----
    Qt is imported **first, deliberately**: ``rendercanvas.qt`` refuses to
    load until a binding has been chosen, and the error it raises then says
    so in a sentence that reads like a bug in emtk. Importing ``qtpy``
    first is what picks the binding the rest of emtk is already using.
    """
    from qtpy import QtCore, QtWidgets  # noqa: F401,PLC0415

    from rendercanvas.qt import QRenderWidget  # noqa: PLC0415

    return QtCore, QRenderWidget


def wgpu_host_class():
    """Return the widget class that hosts a control on the GPU.

    Returns
    -------
    type
        A ``QWidget`` subclass -- ``rendercanvas``'s, which owns the surface.

    Raises
    ------
    ImportError
        If Qt or ``rendercanvas`` is not installed.
    """
    global _HOST_CLASS
    if _HOST_CLASS is not None:
        return _HOST_CLASS

    QtCore, QRenderWidget = _render_widget()

    class _WgpuControlHost(QRenderWidget):
        """A Qt widget that draws one control through wgpu.

        The same contract as :class:`.qt_host.ControlHost` -- it knows
        nothing about any particular control, draws whatever it was given
        and forwards presses, drags, wheels and keys -- with the CPU
        rasteriser taken out of the middle.

        Parameters
        ----------
        control : object
            Must have ``draw(painter, x, y, w, h)``; ``press``, ``drag``,
            ``release``, ``hover``, ``key`` and ``scroll`` are used when
            present, so a control with none of them still hosts fine.
        font_pt : float, optional
            Point size of the interface font.
        background : tuple, optional
            Cleared to before the control draws, as 0-255 RGB.
        on_change : callable, optional
            Called with the control after any event it consumed.
        images : ImageAtlas, optional
            Shared with the renderer, and installed as the painter's
            ``image_uv_resolver``.
        renderer : WgpuRenderer, optional
            Share one between several hosts and they share the glyph
            texture, which is ten megabytes.
        parent : QWidget, optional

        Notes
        -----
        The event translation below is deliberately the *same code* as
        :class:`.qt_host.ControlHost`'s rather than shared with it. The
        QPainter host is the reference this one's output is compared
        against, and a refactor that moved it would move both sides of the
        comparison at once. When the GPU path is the default, the two should
        become one mixin -- and not before.

        The widget draws **on demand**, not on a timer: ``rendercanvas``
        would otherwise repaint at its own rate whether or not anything
        moved, which for an interface is the cost this module exists to
        remove.
        """

        #: Emitted after an event the control consumed. The same signal
        #: :class:`.qt_host.ControlHost` has, so a call site that connected
        #: to one connects to the other unchanged.
        changed = QtCore.Signal()

        def __init__(
            self,
            control,
            font_pt: float = DEFAULT_FONT_PT,
            background: tuple = (30, 32, 38),
            on_change: Callable[[object], None] | None = None,
            images=None,
            renderer=None,
            parent=None,
            **kwargs,
        ) -> None:
            super().__init__(parent=parent, **kwargs)
            self.control = control
            self.font_pt = float(font_pt)
            self.background = tuple(background)
            self.on_change = on_change
            if renderer is None:
                renderer = WgpuRenderer(images=images)
            elif images is not None:
                renderer.images = images
            self.renderer = renderer
            self.images = renderer.images
            self._painter = None
            self._painter_scale = None
            self._context = None
            self._pressed = False
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.setMouseTracking(True)
            self.setMinimumHeight(80)
            self.set_update_mode("ondemand")
            self.request_draw(self._draw_frame)

        # -- painting ---------------------------------------------------- #
        @property
        def draw_calls(self) -> int:
            """How many draw calls the last frame took. One."""
            return self.renderer.draw_calls

        def _configure(self):
            """The presentation context, configured once.

            Returns
            -------
            wgpu.GPUCanvasContext

            Notes
            -----
            The format is the **surface's** preferred one, not emtk's: a
            window usually wants a ``*-srgb`` variant, and configuring it
            with something else is either a validation error or a picture
            with the wrong gamma. :meth:`WgpuRenderer.pipeline` keeps one
            pipeline per format for exactly this reason.
            """
            if self._context is None:
                context = self.get_context("wgpu")
                device = self.renderer.device
                self._format = context.get_preferred_format(device.adapter)
                context.configure(device=device, format=self._format)
                self._context = context
            return self._context

        def _make_painter(self, scale: float):
            """A painter for this widget at *scale* device pixels per pixel.

            One painter, cleared per frame rather than rebuilt: its
            constructor resolves a dozen atlas metrics that do not change.
            """
            painter = self.renderer.painter(font_pt=self.font_pt, scale=scale)
            self._painter_scale = scale
            return painter

        def _draw_frame(self) -> None:
            """Build the frame's vertices and draw them. One call."""
            context = self._configure()
            width, height = self.get_physical_size()
            if width <= 0 or height <= 0:
                return

            # Rebuilt when the device scale changes, which is what dragging
            # the window to a display with a different one does. A stale
            # scale does not look like a scaling bug: the interface draws at
            # half size in the corner while `hit_test` still answers for
            # where it should be, so every click misses by the ratio and the
            # interface looks inert rather than misplaced.
            scale = float(self.get_pixel_ratio())
            if self._painter is None or self._painter_scale != scale:
                self._painter = self._make_painter(scale)
            painter = self._painter
            painter.clear()
            logical_w, logical_h = width / scale, height / scale
            self.control.draw(painter, 0.0, 0.0, logical_w, logical_h)
            self.renderer.render(
                painter, width, height,
                context.get_current_texture().create_view(),
                background=self.background,
                format=self._format,
            )

        def _box(self) -> tuple[float, float, float, float]:
            """The box the control is drawn in: the whole widget."""
            return (0.0, 0.0, float(self.width()), float(self.height()))

        def _notify(self) -> None:
            """Repaint and tell whoever is listening."""
            self.request_draw()
            if self.on_change is not None:
                self.on_change(self.control)
            self.changed.emit()

        @staticmethod
        def _point(event) -> tuple[float, float]:
            """A mouse event's position, across the Qt versions qtpy spans."""
            position = getattr(event, "position", None)
            if callable(position):
                point = position()
                return (float(point.x()), float(point.y()))
            return (float(event.x()), float(event.y()))

        # -- input ------------------------------------------------------- #
        def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt's spelling
            """Forward a press, with the modifier mask Qt already agrees on."""
            press = getattr(self.control, "press", None)
            if callable(press):
                px, py = self._point(event)
                press(px, py, *self._box(), int(event.modifiers()), 1)
                self._pressed = True
                self._notify()

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            """Forward a double click as ``clicks=2``; Qt counts them."""
            press = getattr(self.control, "press", None)
            if callable(press):
                px, py = self._point(event)
                press(px, py, *self._box(), int(event.modifiers()), 2)
                self._notify()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            """Forward a drag while a button is down, a hover otherwise."""
            px, py = self._point(event)
            if self._pressed:
                drag = getattr(self.control, "drag", None)
                if callable(drag):
                    drag(px, py, *self._box())
                    self.request_draw()
                return
            hover = getattr(self.control, "hover", None)
            if callable(hover):
                hover(px, py, *self._box())
                self.request_draw()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            """Forward the button coming up."""
            self._pressed = False
            release = getattr(self.control, "release", None)
            if callable(release):
                release()
            self.request_draw()

        def wheelEvent(self, event) -> None:  # noqa: N802
            """Forward a wheel notch as three rows, the usual Qt convention.

            ``scroll`` takes **one** argument, in rows, sign-flipped from
            the wheel: a wheel pushed away is a positive delta and scrolls
            the content *up*, which is a negative row offset.
            """
            scroll = getattr(self.control, "scroll", None)
            if not callable(scroll):
                return
            delta = (
                event.angleDelta().y()
                if hasattr(event, "angleDelta")
                else event.delta()
            )
            scroll(-3 if delta > 0 else 3)
            self.request_draw()

        def keyPressEvent(self, event) -> None:  # noqa: N802
            """Forward a key press; unhandled keys go on to Qt."""
            key = getattr(self.control, "key", None)
            if callable(key) and key(
                int(event.key()), event.text(), int(event.modifiers())
            ):
                self._notify()
                return
            super().keyPressEvent(event)

    _HOST_CLASS = _WgpuControlHost
    return _HOST_CLASS


def WgpuControlHost(control, **kwargs):  # noqa: N802 - it stands in for a class
    """Build a GPU host widget around *control*.

    Spelled like a class because it replaces one, and shaped like
    :func:`.qt_host.ControlHost` so a call site swaps one for the other by
    changing the name.

    Parameters
    ----------
    control : object
        Anything with the package's ``draw``/``press``/``key`` contract.
    **kwargs
        ``font_pt``, ``background``, ``on_change``, ``images``, ``renderer``,
        ``parent``.

    Returns
    -------
    QWidget
    """
    return wgpu_host_class()(control, **kwargs)


#: The more explicit spelling, matching :func:`.qt_host.make_control_host`.
make_wgpu_control_host = WgpuControlHost
