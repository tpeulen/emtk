"""The desktop backend: WebGPU through ``wgpu-py``.

This module is the **only** place in emtk allowed to name ``wgpu``, and a
guard test enforces that. Everything else reaches the GPU through
:mod:`emtk.gpu.api`, whose surface is deliberately the same as
``wgpu-py``'s -- so this file is almost a pass-through, and the seam cost the
engine nothing at the call sites.

What is left once the constants are excluded (see :mod:`.enums`) is one
function: getting an adapter and a device. Every other GPU call the engine
makes is a *method* on a device, queue, encoder or pass object that this
function ultimately returns, and those are already spelled identically by the
specification -- which is what a second backend will be written against.
"""
from __future__ import annotations

from typing import Optional

__all__ = ["is_available", "request_adapter_sync", "name"]

#: What :func:`emtk.gpu.backend_name` reports for this backend.
name = "native"


def is_available() -> bool:
    """Whether ``wgpu-py`` can be imported.

    Returns
    -------
    bool
        ``True`` if the binding is present. This does **not** mean an adapter
        exists -- a machine with the package and no usable GPU returns ``True``
        here and fails in :func:`request_adapter_sync`, which is the right
        place for it to fail because that is where the error says why.
    """
    try:
        import wgpu  # noqa: F401
    except Exception:
        return False
    return True


def request_adapter_sync(power_preference: Optional[str] = "high-performance"):
    """Return a GPU adapter.

    Parameters
    ----------
    power_preference : str, optional
        ``"high-performance"`` or ``"low-power"``. Passed through unchanged.

    Returns
    -------
    object
        A ``GPUAdapter``. Call ``request_device_sync()`` on it for a device.

    Notes
    -----
    Synchronous, matching ``wgpu-py``. A browser's ``requestAdapter`` returns a
    promise instead, so a browser backend has to resolve it before handing the
    device to the engine rather than inside it -- keeping the engine's own code
    free of ``await`` is the reason this function returns an adapter rather
    than taking a callback.
    """
    import wgpu

    return wgpu.gpu.request_adapter_sync(power_preference=power_preference)
