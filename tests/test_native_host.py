"""The toolkit-free desktop host draws an app, end to end, on the offscreen canvas.

Needs ``rendercanvas``, ``wgpu`` and an adapter -- skipped where any is
missing, which is the one thing a build machine may legitimately lack.
"""
from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas")
pytest.importorskip("wgpu")
np = pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def device():
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as exc:  # noqa: BLE001 - no adapter here
        pytest.skip(f"no wgpu adapter: {exc}")


def test_the_implot_demo_renders_in_a_native_window(device):
    from emtk.implot_demo import make_app
    from emtk.native import NativeHost

    host = NativeHost(make_app(), size=(640, 420), backend="offscreen", device=device)
    assert host.is_interactive() is False
    assert not host.format.endswith("-srgb"), "an sRGB target washes every colour out"
    image = np.asarray(host.draw_frame())
    assert image.shape[:2] == (420, 640)
    # Not one flat colour: the plot, its axes and its labels are there.
    assert len(np.unique(image[..., :3].reshape(-1, 3), axis=0)) > 50


def test_events_reach_the_app_through_the_canvas(device):
    from emtk.app import ImApp
    from emtk.native import NativeHost

    app = ImApp(lambda: None)
    host = NativeHost(app, size=(200, 100), backend="offscreen", device=device)
    # rendercanvas' dispatch is its own business; what is emtk's is the
    # translation it calls -- registered on this very canvas.
    registered = [entry[-1] for entry in host.canvas._events._event_handlers["pointer_down"]]
    assert host.events._on_pointer_down in registered
    host.events._on_pointer_down({"event_type": "pointer_down", "x": 12.0, "y": 34.0,
                                  "button": 1, "buttons": (1,), "modifiers": ()})
    host.draw_frame()
    assert app.io.mouse_pos == (12.0, 34.0)


@pytest.mark.parametrize(
    "declared, expected",
    [
        ((700, 500), (700, 500)),
        (lambda: (710, 510), (710, 510)),
        (None, None),
        ("1234", None),
        ({"width": 700, "height": 500}, None),
        (("bad", 400), None),
        ((500,), None),
        ((float("nan"), 400), None),
        ((float("inf"), 400), None),
        ((-1, 400), None),
        ((500, 0), None),
    ],
)
def test_native_host_uses_only_valid_window_size_before_opening_canvas(
    monkeypatch, declared, expected
):
    """Size resolution runs at the actual host boundary before any canvas/device allocation."""
    from types import SimpleNamespace

    from emtk import native
    from emtk.app import ImApp

    class CanvasOpened(Exception):
        """Stop at canvas construction after recording its actual size argument."""

    opened = []

    def open_canvas(module, size, title):
        opened.append(size)
        raise CanvasOpened

    monkeypatch.setattr(
        native, "canvas_module", lambda backend: SimpleNamespace(__name__="rendercanvas.offscreen")
    )
    monkeypatch.setattr(native, "open_canvas", open_canvas)
    app = ImApp(lambda: None)
    app.window_size = declared
    app.preferred_size = (650, 450)
    with pytest.raises(CanvasOpened):
        native.NativeHost(app)
    assert opened == [expected or native.DEFAULT_WINDOW_SIZE]


def test_explicit_native_size_wins_without_calling_app_size(monkeypatch):
    """An explicit launch size bypasses even an unusable callable declaration."""
    from types import SimpleNamespace

    from emtk import native
    from emtk.app import ImApp

    def unavailable():
        raise AssertionError("Explicit launch must not query the app's default size.")

    class CanvasOpened(Exception):
        """Stop before device allocation with the explicit size captured."""

    opened = []

    def open_canvas(module, size, title):
        opened.append(size)
        raise CanvasOpened

    monkeypatch.setattr(
        native, "canvas_module", lambda backend: SimpleNamespace(__name__="rendercanvas.offscreen")
    )
    monkeypatch.setattr(native, "open_canvas", open_canvas)
    app = ImApp(lambda: None)
    app.window_size = unavailable
    with pytest.raises(CanvasOpened):
        native.NativeHost(app, size=(800, 600))
    assert opened == [(800, 600)]


@pytest.mark.parametrize(
    "size_args, expected", [([], (710, 510)), (["--size", "800x600"], (800, 600))]
)
def test_native_cli_routes_declared_or_explicit_size_through_the_host(
    monkeypatch, size_args, expected
):
    """The CLI leaves app geometry resolution to NativeHost when no --size is supplied."""
    from types import SimpleNamespace

    import emtk.app
    from emtk import native
    from emtk.app import ImApp

    class CanvasOpened(Exception):
        """Stop before device allocation, after the actual CLI resolves its size."""

    opened = []

    def open_canvas(module, size, title):
        opened.append(size)
        raise CanvasOpened

    app = ImApp(lambda: None)
    app.window_size = lambda: (710, 510)
    monkeypatch.setattr(emtk.app, "load_app", lambda spec: app)
    monkeypatch.setattr(
        native, "canvas_module", lambda backend: SimpleNamespace(__name__="rendercanvas.offscreen")
    )
    monkeypatch.setattr(native, "open_canvas", open_canvas)
    with pytest.raises(CanvasOpened):
        native.main(["--app", "fixture:app", *size_args])
    assert opened == [expected]
