"""A Qt application made before a glfw window still runs its event loop (macOS).

Qt's first ``processEvents`` calls ``[NSApp run]`` and waits for its own delegate's
"did finish launching" to stop it. A glfw window opened in between -- before Qt ever
spun -- made glfw the delegate and finished the launch itself, so Qt's event loop then
blocked for good at 0 % CPU. In the full suite this was ``test_qt_host`` hanging after a
test that made the ``QApplication`` (the marker tests) and one that opened a glfw window
(the resize-click tests); each file passed alone. :func:`emtk.native.launch_qt_first`
spins Qt once before glfw starts. Each case runs in a subprocess with a deadline, so a
regression fails instead of hanging the suite.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="an AppKit launch-order trap")

_SCRIPT = textwrap.dedent("""
    import sys, time
    from qtpy import QtWidgets
    app = QtWidgets.QApplication([])            # made, never spun: as after the marker tests
    if {guard}:
        from emtk.native import launch_qt_first
        launch_qt_first()
    import glfw
    from rendercanvas.glfw import RenderCanvas
    try:
        canvas = RenderCanvas(size=(200, 150), title="qt-after-glfw")
    except Exception as exc:
        print("SKIP", exc); sys.exit(0)
    glfw.hide_window(canvas._window)
    glfw.poll_events()
    canvas.close()
    from emtk.qt_host import ControlHost

    class Ticker:
        frames = 0
        def draw(self, *a): self.frames += 1
        def animating(self): return self.frames < 5

    control = Ticker()
    host = ControlHost(control)
    host.resize(100, 80)
    host.show()
    end = time.time() + 5.0
    while control.frames < 5 and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    print("FRAMES", control.frames)
""")


def _run(guard: bool):
    pytest.importorskip("glfw")
    pytest.importorskip("rendercanvas.glfw")
    pytest.importorskip("qtpy.QtWidgets", exc_type=ImportError)
    try:
        done = subprocess.run([sys.executable, "-c", _SCRIPT.format(guard=guard)],
                              capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    if "SKIP" in done.stdout:
        pytest.skip(done.stdout.strip())
    return done


def test_a_qt_loop_made_before_a_glfw_window_keeps_running():
    done = _run(guard=True)
    assert done is not None, "the Qt event loop blocked after a glfw window opened"
    assert "FRAMES 5" in done.stdout, done.stdout + done.stderr


def test_open_canvas_launches_qt_first():
    """The product path: emtk.native.open_canvas spins a waiting Qt application first."""
    from emtk import native

    calls = []

    class _App:
        def processEvents(self):
            calls.append(1)

    class _Widgets:
        class QApplication:
            @staticmethod
            def instance():
                return _App()

    saved = (native._QT_LAUNCHED, dict(sys.modules))
    try:
        native._QT_LAUNCHED = False
        sys.modules["PyQt5.QtWidgets"] = _Widgets
        if sys.platform == "darwin":
            assert native.launch_qt_first() is True
            assert native.launch_qt_first() is False      # once per process
            assert calls == [1]
    finally:
        native._QT_LAUNCHED = saved[0]
        sys.modules.clear()
        sys.modules.update(saved[1])
