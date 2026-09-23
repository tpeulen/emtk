"""The WebGPU constants the engine uses, written out once.

Why these are values here rather than a re-export
-------------------------------------------------
Every constant below is fixed by the **WebGPU specification**, not by the Python
binding: the string enums are the spec's own kebab-case spellings and the usage
flags are the spec's own bit values. ``wgpu-py`` reports exactly these, and so
does a browser -- ``GPUBufferUsage.VERTEX`` is 32 in both places.

That is worth stating because it decides the shape of the whole seam. Of the
thirty-eight ``wgpu.*`` names a full 3-D engine touches, thirty-four are these
constants and three more appear only in docstrings, which leaves **one** name
that a backend actually has to provide (see :mod:`.native`). Delegating the
constants to a backend would have implied a translation step that does not
exist, and would have put a per-frame attribute lookup in front of values that
never change.

``tests/test_gpu_seam.py``
asserts these against the installed binding, so a drift on either side fails
rather than silently rendering something else.

The names are spelled as ``wgpu-py`` spells them -- ``triangle_list`` for
``"triangle-list"`` -- so that call sites read the same before and after the
seam went in.
"""
from __future__ import annotations

__all__ = [
    "BlendFactor",
    "BlendOperation",
    "BufferBindingType",
    "BufferUsage",
    "CompareFunction",
    "CullMode",
    "FilterMode",
    "IndexFormat",
    "LoadOp",
    "PrimitiveTopology",
    "SamplerBindingType",
    "ShaderStage",
    "StoreOp",
    "TextureFormat",
    "TextureSampleType",
    "TextureUsage",
]


class BlendFactor:
    """Blend-equation factors."""

    one = "one"
    src_alpha = "src-alpha"
    one_minus_src_alpha = "one-minus-src-alpha"


class BlendOperation:
    """Blend-equation operators."""

    add = "add"
    #: The min/max operators (WebGPU core, GPUBlendOperation): the volume's
    #: MIP accumulation reduces N tiles along a ray to the true maximum
    #: through ``max`` -- src-alpha compositing of per-tile LUT colours
    #: blended LUT(max1) over LUT(max2) instead (PRD-126 WP1).
    min = "min"
    max = "max"


class BufferBindingType:
    """How a shader may bind a buffer."""

    uniform = "uniform"
    storage = "storage"
    read_only_storage = "read-only-storage"


class BufferUsage:
    """Buffer usage flags. Bit values, combined with ``|``."""

    #: Readable by the CPU after ``map``. Only ``COPY_DST`` may accompany it --
    #: a mappable buffer cannot also be bound to a shader, which is why a
    #: readback is always a copy into a buffer of its own.
    MAP_READ = 1
    MAP_WRITE = 2
    COPY_SRC = 4
    COPY_DST = 8
    INDEX = 16
    VERTEX = 32
    UNIFORM = 64
    STORAGE = 128


class CompareFunction:
    """Depth/stencil comparison functions."""

    less = "less"
    #: Passes where the depth is *equal* too -- the colour pass of a
    #: single-layer translucent draw, over the depth its own pre-pass wrote.
    less_equal = "less-equal"
    greater = "greater"
    greater_equal = "greater-equal"
    #: Draw whatever is already in the depth buffer -- what an *overlay* object
    #: needs. A selection marker has to be visible on the far side of a
    #: space-filling model, which is PyMOL's ``selection_overlay``.
    always = "always"


class CullMode:
    """Face culling."""

    none = "none"


class FilterMode:
    """Sampler filtering.

    ``nearest`` for the chrome image, which is drawn at exactly the size it is
    composited at; ``linear`` for the glyph atlas, which is baked supersampled
    and sampled down, so filtering is what turns that coverage into a smooth
    edge rather than a stair.
    """

    nearest = "nearest"
    linear = "linear"


class IndexFormat:
    """Index buffer element type.

    ``uint32`` and ``uint16`` are the only two WebGPU accepts, which is why
    an application packing indices casts the builders' ``int32``.
    """

    uint32 = "uint32"


class LoadOp:
    """What a render pass does with an attachment's existing contents."""

    clear = "clear"
    load = "load"


class PrimitiveTopology:
    """Primitive assembly."""

    triangle_list = "triangle-list"
    line_list = "line-list"


class SamplerBindingType:
    """How a shader may bind a sampler."""

    filtering = "filtering"
    non_filtering = "non-filtering"


class ShaderStage:
    """Shader stage flags. Bit values, combined with ``|``."""

    VERTEX = 1
    FRAGMENT = 2
    COMPUTE = 4


class StoreOp:
    """What a render pass does with an attachment's results."""

    store = "store"
    #: Legal on a read-only depth attachment: the pass never wrote it, so
    #: there is nothing to store (the volume accumulation reads the frame's
    #: depth this way, PRD-126 WP1).
    discard = "discard"


class TextureFormat:
    """Texture formats.

    ``bgra8unorm`` and ``rgba8unorm`` are here because they are what a canvas
    reports as its preferred format -- on the desktop and in a browser alike.
    Neither is an ``-srgb`` variant, and that is not an oversight to correct:
    the shaders write colours the baseline renderer wrote to a plain
    framebuffer, and an sRGB target gamma-encodes on write, so a clear value of
    0.09 comes back as 85 instead of 23 and every colour washes out.
    """

    rgba8unorm = "rgba8unorm"
    bgra8unorm = "bgra8unorm"
    depth24plus = "depth24plus"


class TextureSampleType:
    """How a shader samples a bound texture."""

    float = "float"
    depth = "depth"
    #: A float texture that cannot be *filtered*. `r32float` is the case:
    #: linear sampling of it is optional in WebGPU, so binding one as
    #: ``float`` is a validation error rather than a soft fallback to nearest.
    unfilterable_float = "unfilterable-float"


class TextureUsage:
    """Texture usage flags. Bit values, combined with ``|``.

    ``RENDER_ATTACHMENT | TEXTURE_BINDING`` together are load-bearing: the
    second pass reads the depth the first pass wrote, so the depth texture has
    to be both drawn into and sampled. A backend that offers only
    ``RENDER_ATTACHMENT`` cannot run this engine's silhouette pass at all.
    """

    COPY_SRC = 1
    COPY_DST = 2
    TEXTURE_BINDING = 4
    RENDER_ATTACHMENT = 16
