"""Position persistence uses the native backend's actual window capability."""
from types import SimpleNamespace
import sys

from emtk.native import CanvasEvents


class Canvas:
    """A rendercanvas-like surface; its event contract has no move event."""

    def __init__(self, window=None):
        self._window = window
        self.events = {}

    def add_event_handler(self, callback, *names):
        """Record supported canvas handlers."""
        self.events.update({name: callback for name in names})


def backend(monkeypatch, *, screen=(0, 0, 800, 600)):
    """Install a GLFW stand-in with a callback and window-position capability."""
    state = {'pos': (20, 30), 'callback': None, 'previous_calls': []}

    def previous(window, x, y):
        state['previous_calls'].append((x, y))

    state['callback'] = previous

    def set_callback(window, callback):
        old, state['callback'] = state['callback'], callback
        return old

    def set_pos(window, x, y):
        state['pos'] = (x, y)
        if state['callback'] is not None:
            state['callback'](window, x, y)

    monkeypatch.setitem(sys.modules, 'glfw', SimpleNamespace(
        set_window_pos_callback=set_callback,
        set_window_pos=set_pos,
        get_window_pos=lambda window: state['pos'],
        get_primary_monitor=lambda: object(),
        get_monitor_workarea=lambda monitor: screen,
    ))
    return state, previous


def test_glfw_restores_valid_position_reports_moves_and_restores_callback(monkeypatch):
    """A backend callback remains chained while geometry is recorded."""
    state, previous = backend(monkeypatch)
    moves, screens = [], []
    control = SimpleNamespace(window_pos=(100, 120), window_moved=lambda x, y: moves.append((x, y)),
                              window_screen_changed=screens.append)
    events = CanvasEvents(Canvas(object()), SimpleNamespace(control=control))
    assert events.position_supported
    assert screens == [(0, 0, 800, 600)]
    assert state['pos'] == (100, 120)
    state['callback'](events.canvas._window, 200, 220)
    assert moves[-1] == (200, 220)
    assert state['previous_calls'][-1] == (200, 220)
    events._on_close({})
    assert state['callback'] is previous


def test_glfw_rejects_a_position_outside_primary_work_area(monkeypatch):
    """A changed monitor arrangement leaves the native default position intact."""
    state, _ = backend(monkeypatch, screen=(100, 100, 700, 500))
    control = SimpleNamespace(window_pos=(0, 0))
    events = CanvasEvents(Canvas(object()), control)
    assert events.position_supported
    assert state['pos'] == (20, 30)
    events._on_close({})


def test_offscreen_has_no_window_position_capability():
    """No fictional rendercanvas move event is registered on offscreen canvases."""
    canvas = Canvas()
    events = CanvasEvents(canvas, SimpleNamespace(window_pos=(100, 120)))
    assert not events.position_supported
    assert not any('move' == name or 'position' in name for name in canvas.events)
    events._on_close({})


def test_native_host_uses_remembered_size_unless_explicitly_overridden(monkeypatch):
    """A direct NativeHost launch honors the same saved size as the Qt host."""
    import emtk.app
    import emtk.native

    opened = []
    context = SimpleNamespace(get_preferred_format=lambda adapter: 'rgba8unorm',
                              configure=lambda **kwargs: None)
    canvas = Canvas()
    canvas.get_context = lambda kind: context
    canvas.get_physical_size = lambda: (700, 500)
    canvas.get_pixel_ratio = lambda: 1.0
    canvas.request_draw = lambda callback: None
    canvas.close = lambda: None
    surface = SimpleNamespace(attach=lambda *args: None,
                              set_frame_request_callback=lambda callback: None)
    monkeypatch.setattr(emtk.app, 'as_surface', lambda app: surface)
    monkeypatch.setattr(emtk.native, 'canvas_module', lambda backend: SimpleNamespace(__name__='rendercanvas.offscreen'))

    def open_canvas(module, size, title):
        opened.append(size)
        return canvas

    monkeypatch.setattr(emtk.native, 'open_canvas', open_canvas)
    app = SimpleNamespace(window_size=(700, 500), preferred_size=(600, 400))
    device = SimpleNamespace(adapter=None)
    host = emtk.native.NativeHost(app, device=device)
    assert opened[-1] == (700, 500)
    host.close()
    host = emtk.native.NativeHost(app, size=(800, 600), device=device)
    assert opened[-1] == (800, 600)
    host.close()
