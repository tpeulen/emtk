import threading
from types import SimpleNamespace

from emtk.app import ImApp
from emtk.native import NativeHost


def test_external_request_wakes_an_idle_app_and_detaches_cleanly():
    app = ImApp(lambda: None)
    requested = []
    app.set_frame_request_callback(lambda: requested.append(True))
    thread = threading.Thread(target=app.request_frame)
    thread.start()
    thread.join()
    assert requested == [True]
    assert app.wants_frame
    app.set_frame_request_callback(None)
    app.request_frame()
    assert requested == [True]


def test_native_worker_request_uses_the_host_loop_threadsafe_scheduler():
    queued = []
    draws = []
    host = NativeHost.__new__(NativeHost)
    host.events = SimpleNamespace(_closed=False)
    host._host_thread = threading.get_ident()
    host._pending_external_redraw = threading.Event()
    host._loop = SimpleNamespace(call_soon_threadsafe=queued.append)
    host.canvas = SimpleNamespace(request_draw=lambda: draws.append(threading.get_ident()))
    thread = threading.Thread(target=host.request_draw_threadsafe)
    thread.start()
    thread.join()
    assert not draws
    assert len(queued) == 1
    queued[0]()
    assert draws == [threading.get_ident()]
