"""The browser backend translates a renderer's calls into WebGPU's JavaScript.

Why this can be tested without a browser
----------------------------------------
The backend's whole job is a translation: ``create_buffer(size=..., usage=...)``
becomes ``createBuffer({size, usage})``. That is a property of the *mapping*,
not of the GPU, so it can be checked against a recording stand-in for ``js`` --
and it is worth checking that way, because the mistakes it makes are silent.
A descriptor key left in ``snake_case`` arrives as ``undefined`` and surfaces as
a validation error naming a field the caller did pass; a nested key missed one
level down passes the outer validation and drops the inner value.

What still needs a browser is whether the frame *looks* right, and that is a
different question asked with a screenshot.
"""

from __future__ import annotations

import sys
import types

import pytest
from emtk.gpu import browser


class _Recorder:
    """Stands in for a JavaScript object, remembering what was called on it."""

    def __init__(self, name="root", log=None):
        self.name = name
        self.log = log if log is not None else []

    def __getattr__(self, item):
        if item.startswith("_"):
            raise AttributeError(item)

        def call(*args, **kwargs):
            self.log.append((f"{self.name}.{item}", args, kwargs))
            return _Recorder(f"{self.name}.{item}()", self.log)

        call.__name__ = item
        return call


@pytest.fixture
def fake_js(monkeypatch):
    """Install a fake ``js`` and ``pyodide.ffi`` so the backend can be driven."""
    js = types.ModuleType("js")

    class _Object:
        @staticmethod
        def fromEntries(pairs):  # noqa: N802 - JavaScript's spelling
            return dict(pairs)

    js.Object = _Object
    js.navigator = types.SimpleNamespace(gpu=_Recorder("navigator.gpu"))

    ffi = types.ModuleType("pyodide.ffi")

    def _to_js(value, dict_converter=None, **_kwargs):
        # Mirror Pyodide: a dict becomes whatever `dict_converter` makes of its
        # items. The default there is a Map, which is exactly the trap the
        # backend passes `Object.fromEntries` to avoid.
        if isinstance(value, dict):
            items = [(k, _to_js(v, dict_converter=dict_converter)) for k, v in value.items()]
            return dict_converter(items) if dict_converter else dict(items)
        if isinstance(value, (list, tuple)):
            return [_to_js(v, dict_converter=dict_converter) for v in value]
        return value

    ffi.to_js = _to_js
    pyodide = types.ModuleType("pyodide")
    pyodide.ffi = ffi

    monkeypatch.setitem(sys.modules, "js", js)
    monkeypatch.setitem(sys.modules, "pyodide", pyodide)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi)
    return js


def test_a_dict_becomes_an_object_and_not_a_map(fake_js):
    """``to_js`` uses ``Object.fromEntries``.

    Pyodide's default for a ``dict`` is a JavaScript ``Map``, and WebGPU reads
    its descriptors as plain objects -- a ``Map`` arrives with every field
    ``undefined``, which surfaces as a validation error naming a field the
    caller did in fact pass.
    """
    assert browser.to_js({"size": 16}) == {"size": 16}


def test_calls_are_camel_cased(fake_js):
    """``create_buffer`` reaches JavaScript as ``createBuffer``."""
    log: list = []
    device = browser._Js(_Recorder("device", log))
    device.create_buffer(size=16, usage=32)
    assert log[0][0] == "device.createBuffer"


def test_keyword_arguments_become_one_descriptor(fake_js):
    """The engine's kwargs arrive as a single object, with camelCase keys."""
    log: list = []
    device = browser._Js(_Recorder("device", log))
    device.create_texture(size=(4, 4, 1), format="rgba8unorm", usage=16)
    _name, args, kwargs = log[0]
    assert not kwargs, "descriptor fields must not stay as keyword arguments"
    assert args[0] == {"size": [4, 4, 1], "format": "rgba8unorm", "usage": 16}


def test_nested_descriptor_keys_are_camel_cased_too(fake_js):
    """A render-pipeline descriptor is camelCased all the way down.

    ``vertex.buffers[].attributes[].shader_location`` is four levels in, and a
    translation that stopped at the top would pass the outer validation while
    silently dropping the attribute's location -- which draws a plausible
    picture out of the wrong bytes.
    """
    log: list = []
    device = browser._Js(_Recorder("device", log))
    device.create_render_pipeline(
        vertex={
            "entry_point": "vs_ui",
            "buffers": [
                {
                    "array_stride": 48,
                    "step_mode": "vertex",
                    "attributes": [{"format": "float32x2", "offset": 0, "shader_location": 0}],
                }
            ],
        }
    )
    _name, args, _kwargs = log[0]
    vertex = args[0]["vertex"]
    assert vertex["entryPoint"] == "vs_ui"
    buffer = vertex["buffers"][0]
    assert buffer["arrayStride"] == 48
    assert buffer["stepMode"] == "vertex"
    assert buffer["attributes"][0]["shaderLocation"] == 0


def test_a_wrapped_object_is_unwrapped_when_passed_on(fake_js):
    """Passing one wrapper into another call hands over the JavaScript object."""
    log: list = []
    inner = _Recorder("texture", log)
    encoder = browser._Js(_Recorder("encoder", log))
    encoder.copy_texture_to_buffer(browser._Js(inner))
    _name, args, _kwargs = log[0]
    assert args[0] is inner


def test_private_attributes_are_not_forwarded(fake_js):
    """A miss on ``_device`` raises rather than returning a JavaScript method.

    Forwarded, it would return the *method* ``device`` -- truthy -- so a "have
    I resolved a device yet" check would answer yes and the next call would
    fail somewhere unrelated.
    """
    wrapper = browser._Js(_Recorder("adapter"))
    with pytest.raises(AttributeError):
        wrapper._device  # noqa: B018


def test_the_sync_adapter_refuses_rather_than_blocking(fake_js, monkeypatch):
    """Without a resolved adapter it raises, and says what the page must do.

    It cannot block: there is no way to wait on a promise from the browser's
    main thread, so a synchronous wait would deadlock the page rather than be
    slow.
    """
    monkeypatch.setattr(browser, "_ADAPTER", None)
    with pytest.raises(RuntimeError, match="await"):
        browser.request_adapter_sync()


def test_an_srgb_canvas_format_is_refused(fake_js):
    """``configure_canvas`` refuses sRGB instead of quietly converting.

    The browser never asks for one -- ``getPreferredCanvasFormat`` returns
    ``bgra8unorm`` or ``rgba8unorm`` -- so an sRGB format can only arrive by
    someone "fixing" it, and it washes out every colour: a clear of 0.09 comes
    back as 85 instead of 23.
    """
    canvas = _Recorder("canvas")
    device = browser._Js(_Recorder("device"))
    with pytest.raises(ValueError, match="srgb"):
        browser.configure_canvas(canvas, device, format="bgra8unorm-srgb")


def test_availability_is_false_without_a_browser():
    """On the desktop the browser backend must not select itself."""
    assert browser.is_available() is False


def test_the_backend_choice_falls_back_to_native():
    """With no browser under it, the seam picks the native backend."""
    from emtk.gpu import api

    assert api.backend_name() == "native"


def test_emtk_s_own_renderer_survives_the_translation(fake_js):
    """The interface renderer builds its pipeline through the browser backend.

    The tests above check the mapping on calls written for them; this checks it
    on the calls :class:`emtk.wgpu_host.WgpuRenderer` actually makes -- bind
    group layouts, a pipeline layout, the ``ui.wgsl`` module and a render
    pipeline with a four-attribute vertex buffer -- which is what a page draws
    every emtk interface with.
    """
    from emtk.gpu import api
    from emtk.wgpu_host import WgpuRenderer

    log: list = []
    device = browser._Js(_Recorder("device", log))
    renderer = WgpuRenderer(device=device, format="bgra8unorm")
    api.use_backend(browser)
    try:
        renderer.pipeline()
    finally:
        api.use_backend(None)

    made = [entry[0].rsplit(".", 1)[-1] for entry in log]
    for call in ("createShaderModule", "createBindGroupLayout",
                 "createPipelineLayout", "createRenderPipeline"):
        assert call in made, f"{call} was never reached: {made}"

    def keys_of(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys_of(nested)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from keys_of(item)

    snake = sorted({
        key
        for _name, args, _kwargs in log
        for arg in args
        for key in keys_of(arg)
        if isinstance(key, str) and "_" in key
    })
    assert not snake, f"these descriptor keys were never camel-cased: {snake}"
    shaders = [args[0]["code"] for name, args, _kw in log if name.endswith("createShaderModule")]
    assert shaders and "fn vs_ui" in shaders[0], "the ui.wgsl source did not arrive"


# --------------------------------------------------------------------------- #
# A whole frame through the browser backend
# --------------------------------------------------------------------------- #
class _JsLike:
    """A JavaScript object as Pyodide shows it: only the members it really has.

    :class:`_Recorder` answers every attribute with a method, so it cannot tell
    a property from a call, nor a member WebGPU has from one it lacks -- which is
    exactly how ``device.limits.get(...)`` (wgpu-py's ``dict``; in the browser a
    ``GPUSupportedLimits`` object with no ``get``) passed every test here and
    failed the first frame of every page. This one raises ``AttributeError`` for
    anything not given, as a ``JsProxy`` does.
    """

    def __init__(self, name, log, **members):
        self._name = name
        self._log = log
        for key, value in members.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<js {self._name}>"


def _method(name, log, make=None):
    """A JavaScript method that logs its call and returns ``make(*args)``."""

    def call(*args):
        log.append((name, args))
        return make(*args) if make is not None else _JsLike(f"{name}()", log)

    return call


class _GPUSupportedLimits:
    """Limits are getters on the *prototype*: an instance has no own fields."""

    maxTextureDimension2D = 8192
    maxBindGroups = 4
    maxComputeWorkgroupSizeX = 256


def _js_device(log):
    """A ``GPUDevice`` with the members the interface renderer touches."""

    def texture(descriptor):
        return _JsLike("texture", log, width=descriptor["size"][0],
                       createView=_method("texture.createView", log),
                       destroy=_method("texture.destroy", log))

    def buffer(descriptor):
        return _JsLike("buffer", log, size=int(descriptor["size"]),
                       getMappedRange=_method("buffer.getMappedRange", log),
                       unmap=_method("buffer.unmap", log),
                       destroy=_method("buffer.destroy", log))

    def render_pass(_descriptor):
        return _JsLike("pass", log, **{
            name: _method(f"pass.{name}", log)
            for name in ("setPipeline", "setBindGroup", "setVertexBuffer",
                         "setScissorRect", "draw", "end")})

    def encoder(*_args):
        return _JsLike("encoder", log,
                       beginRenderPass=_method("encoder.beginRenderPass", log, render_pass),
                       finish=_method("encoder.finish", log))

    queue = _JsLike("queue", log, **{
        name: _method(f"queue.{name}", log)
        for name in ("writeBuffer", "writeTexture", "submit")})
    members = {name: _method(f"device.{name}", log)
               for name in ("createShaderModule", "createBindGroupLayout",
                            "createBindGroup", "createPipelineLayout",
                            "createRenderPipeline", "createSampler")}
    return _JsLike("device", log, queue=queue, limits=_GPUSupportedLimits(),
                   createBuffer=_method("device.createBuffer", log, buffer),
                   createTexture=_method("device.createTexture", log, texture),
                   createCommandEncoder=_method("device.createCommandEncoder", log, encoder),
                   **members)


@pytest.fixture
def js_device(fake_js):
    """A wrapped browser device, with the backend selected while a test runs."""
    from emtk.gpu import api

    class _Object:
        @staticmethod
        def fromEntries(pairs):  # noqa: N802 - JavaScript's spelling
            return dict(pairs)

        @staticmethod
        def getPrototypeOf(value):  # noqa: N802
            return type(value)

        @staticmethod
        def getOwnPropertyNames(value):  # noqa: N802
            return [k for k in vars(value) if not k.startswith("_")]

    fake_js.Object = _Object
    fake_js.Uint8Array = types.SimpleNamespace(
        new=lambda _range: types.SimpleNamespace(set=lambda _data: None))
    log: list = []
    device = browser._wrap(_js_device(log))
    api.use_backend(browser)
    try:
        yield device, log
    finally:
        api.use_backend(None)


def test_device_limits_are_a_dict_in_wgpu_py_spelling(js_device):
    """``device.limits`` reads as wgpu-py's ``dict``, from the prototype's getters."""
    device, _log = js_device
    limits = device.limits
    assert isinstance(limits, dict)
    assert limits["max-texture-dimension-2d"] == 8192
    assert limits["max-compute-workgroup-size-x"] == 256


class _Panel:
    """A control: a filled box and a word, optionally under a frosted modal."""

    def __init__(self, modal=False):
        self.modal = modal

    def draw(self, painter, x, y, w, h):
        painter.fill_rect(x + 4, y + 4, w - 8, h - 8, (200, 40, 40, 255))
        painter.text(x + 8, y + 8, 40, 16, 0, "ndX", (255, 255, 255, 255))
        if self.modal:
            painter.backdrop(x, y, w, h, (0, 0, 0, 120), radius=6.0)
            painter.fill_rect(x + 16, y + 16, 32, 16, (40, 40, 200, 255))


@pytest.mark.parametrize("modal", [False, True], ids=["plain", "frosted"])
def test_a_surface_renders_a_frame_through_the_browser_backend(js_device, modal, caplog):
    """``Surface.render`` -- what ``emtk.web.page.WebPage.draw`` calls each frame --
    completes against a device shaped like the browser's, and submits a draw.

    The plain frame is the one every page draws first; the frosted one is a modal
    window open (the backdrop blur's offscreen textures and extra passes).
    """
    from emtk.app import ControlSurface

    device, log = js_device
    surface = ControlSurface(_Panel(modal=modal), background=(20, 20, 24))
    surface.attach(device, "bgra8unorm", 96, 64, 1.0)
    canvas_view = _JsLike("canvas.getCurrentTexture().createView()", log)
    surface.render(canvas_view)

    assert "failed to draw" not in caplog.text, caplog.text
    called = [entry[0] for entry in log]
    assert "queue.submit" in called
    assert "pass.draw" in called
    # Frosted: the scene offscreen, two blur passes, the copy back, the blurred
    # rectangle over it and the rest of the frame on top.
    passes = called.count("encoder.beginRenderPass")
    assert passes == (6 if modal else 1), called
