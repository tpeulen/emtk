from types import SimpleNamespace

from emtk.app import ImApp
from emtk.native import NativeHost


def test_close_request_is_deferred_until_after_current_render():
    app = ImApp(lambda: None)
    app.request_close()
    assert app.close_requested
    queued = []
    rendered = []
    host = NativeHost.__new__(NativeHost)
    host.app = app
    host.canvas = SimpleNamespace(get_physical_size=lambda: (100, 100))
    host.context = SimpleNamespace(get_current_texture=lambda: SimpleNamespace(create_view=lambda: None))
    host.surface = SimpleNamespace(render=lambda view: rendered.append(True))
    host._retitle = lambda: None
    host._loop = SimpleNamespace(call_soon=queued.append)
    host.close = lambda: None
    host._draw_frame()
    assert rendered == [True]
    assert queued == [host.close]
