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
