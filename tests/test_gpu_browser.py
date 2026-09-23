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
