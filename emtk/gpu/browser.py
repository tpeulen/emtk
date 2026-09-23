"""The browser backend: WebGPU through Pyodide, without a second engine.

What this is
------------
The other side of :mod:`emtk.gpu.api`. On the desktop that surface is
served by ``wgpu-py``; here it is served by the browser's own
``navigator.gpu``, reached from Python running in WebAssembly.

The engine does not change. It calls ``device.create_buffer(size=..., usage=...)``
either way, and the eighteen WGSL shaders are the same text -- which is the whole
reason the port is a few hundred lines rather than a second renderer. What
changes is only how a Python call reaches a JavaScript object, and that is three
mechanical differences:

* **names** -- ``create_buffer`` is ``createBuffer``. ``wgpu-py`` is a literal
  transliteration of the WebGPU IDL, so the mapping is snake_case to camelCase
  and nothing else;
* **arguments** -- Python keyword arguments become one JavaScript object
  literal, and its keys are camelCase too;
* **memory** -- a numpy array has to reach the GPU as a JavaScript typed array
  over the WebAssembly heap, not as a ``memoryview``.

``wgpu.backends.js_webgpu`` was checked first and is an explicit stub -- its own
source says ``# NOTE: this is just a stub for now!!`` and
``get_preferred_canvas_format`` raises ``NotImplementedError``. There is no
device, buffer or pipeline API in it, so ``rendercanvas``'s pyodide backend has
nothing to drive. This module is what that gap needs.

Async, and where it is allowed to be
------------------------------------
``navigator.gpu.requestAdapter()`` and ``adapter.requestDevice()`` return
promises. Everything after them is synchronous, because WebGPU's command
recording is: you build buffers, encode a pass and submit, and the driver
resolves it later.

So the ``await`` lives in :func:`request_adapter_async`, which the **loader**
calls once before the engine starts. :func:`request_adapter_sync` then hands
back what it resolved. If the ``await`` leaked into the engine instead, every
call site would have to become a coroutine on both targets, and the desktop
would grow an event loop it does not need -- which is the same "two
implementations that merely do the same thing" the whole arrangement exists to
avoid.

The canvas format
-----------------
``navigator.gpu.getPreferredCanvasFormat()`` returns ``bgra8unorm`` or
``rgba8unorm`` -- **never** an ``-srgb`` variant. The default is already what
the engine wants, and the trap is sprung only by a well-meaning "fix" that adds
``viewFormats`` and ``createView({format})``: an sRGB target gamma-encodes on
write, so a clear value of 0.09 comes back as 85 instead of 23 and every colour
washes out. :func:`configure_canvas` therefore *refuses* an sRGB format rather
than converting one.
"""
from __future__ import annotations

from typing import Optional

__all__ = [
    "is_available",
    "name",
    "request_adapter_async",
    "request_adapter_sync",
    "configure_canvas",
    "preferred_format",
    "to_js",
]

#: What :func:`emtk.gpu.backend_name` reports for this backend.
name = "browser"

#: Resolved by :func:`request_adapter_async` before the engine starts.
_ADAPTER = None


def is_available() -> bool:
    """Whether this process is Pyodide with a WebGPU-capable browser under it.

    Returns
    -------
    bool
        ``True`` only when ``js`` imports *and* ``navigator.gpu`` exists.
        Checked separately: a browser without WebGPU imports ``js`` perfectly
        well and then has nothing to render with, and the difference decides
        whether the answer is "run somewhere else" or "enable a flag".
    """
    try:
        import js  # noqa: F401
    except Exception:
        return False
    try:
        return bool(getattr(js.navigator, "gpu", None))
    except Exception:
        return False


def to_js(value):
    """Convert a Python mapping or sequence into a JavaScript value.

    Parameters
    ----------
    value : object
        Typically a ``dict`` of descriptor fields.

    Returns
    -------
    object
        A JavaScript object, with ``dict`` converted to ``Object`` rather than
        to ``Map``.

    Notes
    -----
    ``Object.fromEntries`` is not optional. Pyodide's default for a ``dict`` is
    a JavaScript ``Map``, and WebGPU's descriptors are read as plain objects --
    a ``Map`` arrives with every field ``undefined``, which surfaces as a
    validation error naming a field the caller did in fact pass.
    """
    import js
    from pyodide.ffi import to_js as _to_js

    return _to_js(value, dict_converter=js.Object.fromEntries)


async def request_adapter_async(power_preference: str = "high-performance"):
    """Resolve an adapter, and remember it for :func:`request_adapter_sync`.

    Parameters
    ----------
    power_preference : str
        ``"high-performance"`` or ``"low-power"``.

    Returns
    -------
    object
        A ``GPUAdapter``.

    Raises
    ------
    RuntimeError
        If the browser has no WebGPU, or no adapter is available.
    """
    global _ADAPTER
    import js

    gpu = getattr(js.navigator, "gpu", None)
    if gpu is None:
        raise RuntimeError(
            "this browser has no WebGPU (navigator.gpu is undefined)"
        )
    adapter = await gpu.requestAdapter(
        to_js({"powerPreference": power_preference})
    )
    if adapter is None:
        raise RuntimeError(
            "the browser has WebGPU but returned no adapter; on Linux this is "
            "usually a driver the browser will not use without a flag"
        )
    _ADAPTER = _Adapter(adapter)
    return _ADAPTER


def request_adapter_sync(power_preference: Optional[str] = "high-performance"):
    """Return the adapter the loader already resolved.

    Parameters
    ----------
    power_preference : str, optional
        Accepted for signature parity with the native backend and ignored:
        the preference was applied when the adapter was requested.

    Returns
    -------
    object

    Raises
    ------
    RuntimeError
        If the loader did not call :func:`request_adapter_async` first. Raised
        rather than blocking, because there is no way to block on a promise on
        the browser's main thread -- a synchronous wait here would deadlock the
        page rather than be slow.
    """
    if _ADAPTER is None:
        raise RuntimeError(
            "no GPU adapter yet: the page must await "
            "emtk.gpu.browser.request_adapter_async() before "
            "starting the renderer"
        )
    return _ADAPTER


def preferred_format() -> str:
    """Return the canvas format the browser prefers.

    Returns
    -------
    str
        ``"bgra8unorm"`` or ``"rgba8unorm"``.
    """
    import js

    return str(js.navigator.gpu.getPreferredCanvasFormat())


def configure_canvas(canvas, device, format: Optional[str] = None) -> str:
    """Configure a canvas' WebGPU context and return the format it took.

    Parameters
    ----------
    canvas : object
        A JavaScript ``HTMLCanvasElement``.
    device : object
        The device to configure against, as returned by
        ``adapter.request_device_sync()``.
    format : str, optional
        Overrides :func:`preferred_format`.

    Returns
    -------
    str
        The format the context was configured with.

    Raises
    ------
    ValueError
        If an sRGB format is requested. See the module docstring: the browser
        never asks for one, and choosing one silently washes out every colour.
    """
    chosen = format or preferred_format()
    if chosen.endswith("-srgb"):
        raise ValueError(
            f"refusing the sRGB canvas format {chosen!r}: the shaders write "
            "colours for a linear target, and an sRGB one gamma-encodes on "
            "write -- a clear of 0.09 comes back as 85 instead of 23"
        )
    context = canvas.getContext("webgpu")
    context.configure(
        to_js({"device": device.js, "format": chosen, "alphaMode": "opaque"})
    )
    return chosen


def _camel(snake: str) -> str:
    """Return ``snake_case`` as ``camelCase``.

    Parameters
    ----------
    snake : str

    Returns
    -------
    str
    """
    head, _, tail = snake.partition("_")
    return head + "".join(part.title() for part in tail.split("_") if part)


class _Js:
    """Base for the thin wrappers that translate one call into JavaScript.

    Holds the underlying JavaScript object as :attr:`js` and turns any
    ``snake_case`` method into its ``camelCase`` counterpart, passing keyword
    arguments as one object literal. That is the whole translation: ``wgpu-py``
    is a transliteration of the same IDL the browser implements, so there is no
    per-call mapping table to get wrong.
    """

    def __init__(self, js_object) -> None:
        self.js = js_object

    def __getattr__(self, item: str):
        """Return a callable that invokes the camelCase method on :attr:`js`.

        Private names are refused rather than forwarded. Without that, a miss
        on ``self._device`` would look up ``device`` on the JavaScript object
        and hand back *a method*, so a "have I resolved one yet" check would
        find a truthy callable and report yes.
        """
        if item.startswith("_"):
            raise AttributeError(item)
        target = getattr(self.js, _camel(item))

        # Properties are values, not calls. WebGPU has both -- `texture.width`
        # beside `texture.createView()` -- and wrapping a property in a callable
        # hands back something truthy that is never the value, so a caller
        # reading it gets a function where it expected a number.
        if not callable(target):
            return _wrap(target)

        def call(*args, **kwargs):
            if kwargs:
                return _wrap(target(to_js(_descriptor(kwargs))))
            return _wrap(target(*[_argument(a) for a in args]))

        return call

    def __repr__(self) -> str:
        """Show what this wraps."""
        return f"<{type(self).__name__} {self.js}>"


def _descriptor(kwargs: dict) -> dict:
    """Return *kwargs* with its keys and nested keys camelCased.

    Parameters
    ----------
    kwargs : dict
        Keyword arguments as the engine spells them.

    Returns
    -------
    dict
        The same values under the descriptor keys WebGPU expects.

    Notes
    -----
    Recursive, because a render-pipeline descriptor nests four levels deep --
    ``vertex.buffers[].attributes[].shader_location`` is a ``shaderLocation``
    inside a list inside a list inside a dict, and a translation that stopped
    at the top level would pass validation on the outer object and silently
    drop the inner fields.
    """
    out = {}
    for key, value in kwargs.items():
        out[_camel(key)] = _descriptor_value(value)
    return out


def _descriptor_value(value):
    """Camel-case a descriptor value, recursing into dicts and lists."""
    if isinstance(value, dict):
        return _descriptor(value)
    if isinstance(value, (list, tuple)):
        return [_descriptor_value(item) for item in value]
    return _unwrap(value)


def _unwrap(value):
    """Return the JavaScript object behind a wrapper, or *value* unchanged."""
    return value.js if isinstance(value, _Js) else value


def _bytes_to_js(data):
    """Return *data* as a JavaScript ``Uint8Array``.

    Parameters
    ----------
    data : bytes or numpy.ndarray or memoryview

    Returns
    -------
    object
        A ``Uint8Array`` over a copy.

    Notes
    -----
    A copy, deliberately. A zero-copy view onto Pyodide's heap is possible and
    is invalidated the moment WebAssembly memory grows -- which numpy can cause
    on the very next allocation, leaving the GPU reading freed memory. The
    buffers here are kilobytes (the chrome is ~107 KB a frame); the atlas is the
    only large one and it is uploaded once.
    """
    if hasattr(data, "tobytes"):
        data = data.tobytes()
    return to_js(bytes(data))


def _argument(value):
    """Convert one positional argument for a JavaScript call.

    Parameters
    ----------
    value : object

    Returns
    -------
    object

    Notes
    -----
    Positional arguments need this as much as keyword ones do, and that is
    easy to miss: ``queue.write_texture(destination, data, layout, size)``
    passes three dicts and an array *positionally*, and handing those to
    JavaScript unconverted fails as ``Overload resolution failed`` -- which
    names the method and says nothing about which argument was wrong.
    """
    if isinstance(value, _Js):
        return value.js
    if isinstance(value, dict):
        return to_js(_descriptor(value))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _bytes_to_js(value)
    if hasattr(value, "dtype") and hasattr(value, "tobytes"):
        return _bytes_to_js(value)
    if isinstance(value, (list, tuple)):
        return to_js([_argument(item) for item in value])
    return value


def _wrap(value):
    """Wrap a JavaScript object so its methods can be called snake_case."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _is_device(value):
        return _Device(value)
    return _Js(value)


def _is_device(js_object) -> bool:
    """Whether a JavaScript object looks like a ``GPUDevice``."""
    return hasattr(js_object, "createBuffer") and hasattr(js_object, "queue")


class _Device(_Js):
    """A ``GPUDevice``, plus the two conveniences the engine expects of it."""

    @property
    def queue(self):
        """The device's queue, wrapped so ``read_buffer`` exists on it."""
        return _Queue(self.js.queue, self.js)

    def create_buffer_with_data(self, data, usage):
        """Create a buffer already holding *data*.

        Parameters
        ----------
        data : numpy.ndarray or bytes
            The contents.
        usage : int
            Usage flags.

        Returns
        -------
        _Js
            The new buffer.

        Notes
        -----
        ``createBufferWithData`` does not exist in WebGPU -- it is a wgpu-py
        convenience, and the engine uses it for every vertex, index and uniform
        buffer it makes. The specification's way is to create the buffer
        ``mappedAtCreation``, write into the mapped range and unmap, which is
        what this does.

        The size is rounded up to a multiple of four: ``getMappedRange`` refuses
        a size that is not, and a chrome vertex buffer is a multiple of four
        anyway -- but the atlas is not always, and the failure there names the
        range rather than the buffer.
        """
        import js

        payload = data.tobytes() if hasattr(data, "tobytes") else bytes(data)
        size = (len(payload) + 3) & ~3
        buffer = self.js.createBuffer(
            to_js({"size": size, "usage": usage, "mappedAtCreation": True})
        )
        view = js.Uint8Array.new(buffer.getMappedRange())
        view.set(_bytes_to_js(payload))
        buffer.unmap()
        return _Js(buffer)


class _Queue(_Js):
    """A ``GPUQueue``, plus the one readback the engine's compute paths expect.

    ``read_buffer`` is a wgpu-py convenience -- copy into a mappable staging
    buffer, map it, take the bytes. WebGPU maps *asynchronously* and nothing
    else, so a synchronous engine can only read back where the JavaScript
    stack can be suspended: Pyodide's ``run_sync`` does that with JSPI, and
    only when the Python call was entered through ``callPromising`` (which is
    how ``boot.js`` calls the viewer). Outside such a call this raises rather
    than hangs, and names the cure.
    """

    def __init__(self, js_object, js_device) -> None:
        super().__init__(js_object)
        self._device_js = js_device

    def read_buffer(self, buffer, buffer_offset: int = 0, size=None):
        import js
        from pyodide.ffi import can_run_sync, run_sync  # type: ignore[import-not-found]

        source = _unwrap(buffer)
        offset = int(buffer_offset)
        length = int(size) if size else int(source.size) - offset
        padded = (length + 3) & ~3
        if not can_run_sync():
            raise RuntimeError(
                "reading a GPU buffer back needs a suspendable call: the page "
                "must enter Python through callPromising (JSPI) for this "
                "command; see emtk/web/boot.js"
            )
        staging = self._device_js.createBuffer(
            to_js({"size": padded, "usage": _MAP_READ | _COPY_DST})
        )
        encoder = self._device_js.createCommandEncoder()
        encoder.copyBufferToBuffer(source, offset, staging, 0, padded)
        self.js.submit(to_js([encoder.finish()]))
        run_sync(staging.mapAsync(js.GPUMapMode.READ))
        try:
            data = js.Uint8Array.new(staging.getMappedRange()).to_py().tobytes()
        finally:
            staging.unmap()
            staging.destroy()
        return memoryview(data[:length])


#: ``GPUBufferUsage`` bits the readback needs (the IDL constants).
_MAP_READ = 0x0001
_COPY_DST = 0x0008


class _Adapter(_Js):
    """A ``GPUAdapter``, with the device request the engine expects."""

    def __init__(self, js_object) -> None:
        super().__init__(js_object)
        self._device = None

    def request_device_sync(self, **kwargs):
        """Return the device the loader already resolved.

        Raises
        ------
        RuntimeError
            If the loader has not resolved one. As with the adapter, this
            cannot block: there is no way to wait on a promise from the
            browser's main thread without deadlocking the page.
        """
        device = self._device
        if device is None:
            raise RuntimeError(
                "no GPU device yet: the page must await "
                "`adapter.request_device_async()` before starting the renderer"
            )
        return device

    async def request_device_async(self, **kwargs):
        """Resolve a device and remember it for :meth:`request_device_sync`.

        The engine's limits are asked for here, up to what the adapter offers.
        WebGPU's *default* device is the lowest common denominator --
        eight storage buffers per shader stage -- and the ray tracer binds
        eleven, so on a default device every `ray` compiled to an invalid
        pipeline and traced a black frame (the failure is a console warning,
        not an exception). A desktop wgpu-py device is created with the
        adapter's own limits; this asks for the same.
        """
        descriptor = _descriptor(kwargs)
        descriptor.setdefault("requiredLimits", self._wanted_limits())
        self._device = _wrap(await self.js.requestDevice(to_js(descriptor)))
        return self._device

    #: Limits raised from WebGPU's defaults to what the adapter supports.
    #: Named individually: asking for a limit the adapter lacks makes
    #: `requestDevice` reject, so each is clamped to `adapter.limits`.
    _RAISED_LIMITS = (
        "maxStorageBuffersPerShaderStage",
        "maxStorageBufferBindingSize",
        "maxBufferSize",
        "maxComputeWorkgroupStorageSize",
        "maxComputeInvocationsPerWorkgroup",
        "maxBindGroups",
        "maxBindingsPerBindGroup",
    )

    def _wanted_limits(self) -> dict:
        limits = {}
        supported = getattr(self.js, "limits", None)
        for name in self._RAISED_LIMITS:
            value = getattr(supported, name, None) if supported is not None else None
            if value is not None:
                limits[name] = int(value)
        return limits
