"""The GPU surface a WGSL renderer is written against.

Import it the way a renderer used to import the binding::

    from emtk.gpu import api as wgpu

    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    device = adapter.request_device_sync()
    buf = device.create_buffer(size=n, usage=wgpu.BufferUsage.VERTEX)

and every call site reads as it did before. That is the point: the seam is a
*rename layer* with one name in it, and it has no licence to change behaviour.
If a rendered frame moves when this module is introduced, the seam is wrong.

Why the surface is this small
-----------------------------
A full 3-D engine drawing through this seam touches thirty-eight ``wgpu.*``
names. Thirty-four are WebGPU
specification constants, which are the same integer or the same string in every
implementation, so :mod:`.enums` states them outright. Three more
(``GPUBuffer``, ``GPUTexture``, ``GPUTextureView``) appear only in docstrings
and need no runtime existence. The remainder is :data:`gpu`, below.

Everything else the engine does -- ``create_render_pipeline``,
``begin_compute_pass``, ``write_buffer``, ``submit`` -- is a method on an object
that :data:`gpu` transitively returns, and those names are the specification's,
identical in Python and in JavaScript. So a second backend supplies an adapter
and inherits the other twenty-odd calls for free.

Three things a backend must not flatten, because this engine needs all three
and a naive facade quietly drops them:

* **more than one bind group** -- ``silhouette.wgsl`` and ``overlay.wgsl`` each
  declare ``@group(1)``;
* **a depth texture that is both an attachment and a binding** -- the second
  pass samples the depth the first pass wrote;
* **compute passes**, not only render passes -- the ray tracer, the BVH build,
  marching cubes and the distance transform are all compute.
"""
from __future__ import annotations

from .enums import (
    BlendFactor,
    BlendOperation,
    BufferBindingType,
    BufferUsage,
    CompareFunction,
    CullMode,
    FilterMode,
    IndexFormat,
    LoadOp,
    PrimitiveTopology,
    SamplerBindingType,
    ShaderStage,
    StoreOp,
    TextureFormat,
    TextureSampleType,
    TextureUsage,
)

__all__ = [
    "gpu",
    "backend_name",
    "use_backend",
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


#: Overrides the automatic choice. Set by :func:`use_backend`.
_FORCED = None


def _backend():
    """Return the active backend module.

    Returns
    -------
    module
        :mod:`emtk.gpu.browser` when this process is Pyodide with a
        WebGPU-capable browser under it, and
        :mod:`emtk.gpu.native` otherwise.

    Notes
    -----
    Chosen by asking, not by a build flag: the same wheel is meant to run in
    both places, and a flag is a thing that can be set wrong. The browser
    backend's :func:`~.browser.is_available` returns ``False`` unless ``js``
    imports *and* ``navigator.gpu`` exists, so a desktop process cannot select
    it by accident.
    """
    if _FORCED is not None:
        return _FORCED

    from . import browser

    if browser.is_available():
        return browser

    from . import native

    return native


def use_backend(module) -> None:
    """Force a specific backend, or ``None`` to choose automatically.

    Parameters
    ----------
    module : module or None
        A module offering ``name``, ``is_available`` and
        ``request_adapter_sync``.

    Notes
    -----
    For tests and for a loader that has already resolved a device. Not a
    configuration knob -- the automatic choice is right in both real cases.
    """
    global _FORCED
    _FORCED = module


def backend_name() -> str:
    """Name of the active GPU backend.

    Returns
    -------
    str
        ``"native"`` for ``wgpu-py``.
    """
    return _backend().name


class _Gpu:
    """Stands in for ``wgpu.gpu``, the entry point to everything else.

    Named and shaped after the binding's own module-level object so that
    ``wgpu.gpu.request_adapter_sync(...)`` is spelled identically on either
    side of the seam.
    """

    def request_adapter_sync(self, power_preference: str = "high-performance"):
        """Return a GPU adapter from the active backend.

        Parameters
        ----------
        power_preference : str
            ``"high-performance"`` or ``"low-power"``.

        Returns
        -------
        object
            A ``GPUAdapter``; call ``request_device_sync()`` on it.
        """
        return _backend().request_adapter_sync(power_preference=power_preference)

    def __repr__(self) -> str:
        """Show which backend is behind the seam."""
        return f"<emtk gpu via {backend_name()!r}>"


#: The entry point, mirroring ``wgpu.gpu``.
gpu = _Gpu()
