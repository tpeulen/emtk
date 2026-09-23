"""The Python half of a page: DOM events in, emtk events out, frames on WebGPU.

``boot.js`` hands every DOM event to a :class:`WebPage` with the browser's own
values -- ``MouseEvent.button``, ``KeyboardEvent.key``, the four modifier
flags, ``WheelEvent.deltaY`` -- and this module translates them through
:mod:`emtk.events` and :mod:`emtk.keys` into the vocabulary every emtk host
speaks, then calls the :class:`emtk.app.Surface`. Nothing in JavaScript decides
what an event means, and nothing in JavaScript draws: a frame is Python
calling WebGPU through :mod:`emtk.gpu.browser`.

Each handler returns whether a frame is due, and the page asks for one with
``requestAnimationFrame`` only then -- a page draws on demand, and keeps a
frame loop going only while :meth:`WebPage.animating` says so.

This module is importable anywhere (it names ``js`` only inside the calls a
page makes), which is what lets the translation be tested without a browser.
"""
from __future__ import annotations

import pathlib

from ..events import button_from_dom, buttons_from_dom
from ..keys import key_from_dom, modifiers_from_dom

__all__ = [
    "DROP_DIR",
    "MOUNT_DIR",
    "WebPage",
    "download",
    "in_browser",
    "mount",
    "wheel_steps_from_dom",
    "user_files_dir",
]

#: Where dropped files are written on Pyodide's filesystem before the surface
#: is told their paths. A browser cannot read the path a user dragged, so
#: ``boot.js`` writes the bytes here first.
DROP_DIR = "/mnt/dropped"

#: Where a local folder is mounted (Chrome's File System Access API, through
#: ``pyodide.mountNativeFS``) when the page's "Mount folder" button is used.
MOUNT_DIR = "/mnt/local"


def wheel_steps_from_dom(delta_y: float) -> int:
    """Notches, positive away from the user, from ``WheelEvent.deltaY``.

    The DOM's ``deltaY`` is positive scrolling *down* (toward the user) and
    emtk's steps are positive *away* -- the sign every desktop host already
    flips. A page once passed it through unflipped and zoomed and scrolled
    backwards against every other host.
    """
    delta = float(delta_y or 0.0)
    if delta > 0:
        return -1
    if delta < 0:
        return 1
    return 0


def user_files_dir(fallback: str = "/") -> str:
    """Where a file dialog in a page should open: the mount, else drops, else *fallback*."""
    for candidate in (MOUNT_DIR, DROP_DIR):
        if pathlib.Path(candidate).is_dir():
            return candidate
    return fallback


def in_browser() -> bool:
    """Whether this interpreter runs in a page (Pyodide), where files come and go
    through drops, the mounted folder and downloads."""
    import sys  # noqa: PLC0415

    return sys.platform == "emscripten"


def download(name: str, data: bytes, mime: str = "application/octet-stream", js=None) -> None:
    """Hand *data* to the browser as a download called *name*.

    A page has no file system of the user's: a file written to Pyodide's is
    gone when the tab closes, and one written into the mounted folder only
    exists where a folder was mounted. A download is the one way out that
    always works -- what "Save" means in a page.

    Parameters
    ----------
    name : str
        The file name the browser suggests.
    data : bytes
        The content.
    mime : str
        Its media type (``image/png``, ``application/json``, ...).
    js : module, optional
        The ``js`` namespace; Pyodide's by default. A test passes a stand-in.
    """
    if js is None:
        import js  # noqa: PLC0415 - only exists inside Pyodide
    try:
        from pyodide.ffi import to_js  # noqa: PLC0415
    except ImportError:  # a stand-in js namespace: pass Python values through
        def to_js(value, **_kw):
            return value
    buffer = to_js(memoryview(bytes(data)))
    options = to_js({"type": str(mime)}, dict_converter=js.Object.fromEntries)
    blob = js.Blob.new(to_js([buffer]), options)
    url = js.URL.createObjectURL(blob)
    try:
        anchor = js.document.createElement("a")
        anchor.href = url
        anchor.download = str(name)
        anchor.style.display = "none"
        js.document.body.appendChild(anchor)
        anchor.click()
        js.document.body.removeChild(anchor)
    finally:
        js.URL.revokeObjectURL(url)


class WebPage:
    """One app on one ``<canvas>``.

    Parameters
    ----------
    canvas : object
        A JavaScript ``HTMLCanvasElement`` (or a stand-in with ``width``,
        ``height``, ``clientWidth`` and ``getContext``).
    app : object
        What the factory returned: an :class:`emtk.app.Surface` or a control.
    device : object, optional
        A ``GPUDevice``; the one ``boot.js`` resolved through
        :mod:`emtk.gpu.browser` otherwise.
    format : str, optional
        The canvas format; configured through
        :func:`emtk.gpu.browser.configure_canvas` when a device is resolved
        here.

    Attributes
    ----------
    app : object
        The factory's object, untouched -- what a test driving the page reads
        (``globalThis.emtkApp``).
    surface : emtk.app.Surface
        The app, lifted.
    """

    DROP_DIR = DROP_DIR
    MOUNT_DIR = MOUNT_DIR

    def __init__(self, canvas, app, device=None, format: str | None = None) -> None:
        from ..app import as_surface  # noqa: PLC0415

        self.canvas = canvas
        self.app = app
        self.surface = as_surface(app)
        # Device pixels for the surface, CSS pixels for events and layout.
        self.width = max(int(canvas.width), 1)
        self.height = max(int(canvas.height), 1)
        try:
            self.dpr = float(canvas.width) / float(canvas.clientWidth)
        except Exception:  # noqa: BLE001 - clientWidth 0 or missing
            self.dpr = 1.0
        if not (self.dpr > 0.0):
            self.dpr = 1.0
        if device is None:
            from ..gpu import api, browser  # noqa: PLC0415

            api.use_backend(browser)
            device = browser.request_adapter_sync().request_device_sync()
            format = browser.configure_canvas(canvas, device, format)
        self.device = device
        self.format = str(format or "bgra8unorm")
        self.surface.attach(device, self.format, self.width, self.height, self.dpr)
        self.frames = 0

    # -- drawing --------------------------------------------------------- #
    def draw(self):
        """Render one frame into the canvas' current texture.

        Returns whatever the surface's ``render`` returned -- a statistic of
        the frame, if it reports one -- so a test driving the page can read it.
        """
        context = self.canvas.getContext("webgpu")
        result = self.surface.render(context.getCurrentTexture().createView())
        self.frames += 1
        return result

    def animating(self) -> bool:
        """Whether ``boot.js`` should keep a frame loop going."""
        try:
            return bool(self.surface.animating())
        except Exception:  # noqa: BLE001 - a broken clock is not animating
            return False

    def resize(self, css_width: float, css_height: float, dpr: float = 0.0) -> bool:
        """Take a new canvas size in CSS pixels; resize the backing store.

        Returns whether anything changed, so the page can skip a redraw.
        """
        ratio = float(dpr) if float(dpr or 0.0) > 0.0 else self.dpr
        width = max(int(round(float(css_width) * ratio)), 1)
        height = max(int(round(float(css_height) * ratio)), 1)
        if (width, height, ratio) == (self.width, self.height, self.dpr):
            return False
        self.width, self.height, self.dpr = width, height, ratio
        self.canvas.width = width
        self.canvas.height = height
        self.surface.on_resize(width, height, ratio)
        return True

    # -- pointer --------------------------------------------------------- #
    def press(self, x: float, y: float, button: int, ctrl: bool = False,
              shift: bool = False, alt: bool = False, meta: bool = False,
              double: bool = False) -> bool:
        """``pointerdown`` (or ``dblclick`` with *double*): ``MouseEvent.button``, CSS pixels."""
        return bool(self.surface.on_pointer_press(
            float(x), float(y), button_from_dom(button),
            modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta)),
            double=bool(double)))

    def move(self, x: float, y: float, buttons: int = 0, ctrl: bool = False,
             shift: bool = False, alt: bool = False, meta: bool = False) -> bool:
        """``pointermove``: ``MouseEvent.buttons`` -- held, which decides drag or hover."""
        return bool(self.surface.on_pointer_move(
            float(x), float(y), buttons_from_dom(buttons),
            modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta))))

    def release(self, x: float, y: float, button: int = 0, ctrl: bool = False,
                shift: bool = False, alt: bool = False, meta: bool = False) -> bool:
        """``pointerup`` / ``pointercancel``."""
        return bool(self.surface.on_pointer_release(
            float(x), float(y), button_from_dom(button),
            modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta))))

    def wheel(self, delta_y: float, x: float = 0.0, y: float = 0.0,
              ctrl: bool = False, shift: bool = False, alt: bool = False,
              meta: bool = False) -> bool:
        """``wheel``: the raw ``deltaY`` and where the pointer is."""
        steps = wheel_steps_from_dom(delta_y)
        if not steps:
            return False
        return bool(self.surface.on_wheel(
            float(x), float(y), steps,
            modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta))))

    # -- keys ------------------------------------------------------------ #
    def key(self, name: str, text: str = "", ctrl: bool = False,
            shift: bool = False, alt: bool = False, meta: bool = False) -> bool:
        """``keydown``: ``KeyboardEvent.key`` and the character it typed.

        Returns whether the surface *consumed* it, which ``boot.js`` turns
        into ``preventDefault``. ``KeyboardEvent.key`` is layout-aware and
        already shifted, so *text* passes through untouched.
        """
        return bool(self.surface.on_key_press(
            key_from_dom(name), str(text or ""),
            modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta))))

    # -- files ----------------------------------------------------------- #
    def open_path(self, path: str) -> bool:
        """A file ``boot.js`` wrote to Pyodide's filesystem (a drop)."""
        return bool(self.surface.on_files_dropped([str(path)]))

    def user_files_dir(self) -> str:
        """See :func:`user_files_dir`."""
        return user_files_dir()


def mount(canvas, spec: str, **options) -> WebPage:
    """Build the app named by *spec* on *canvas* -- what ``boot.js`` calls.

    Parameters
    ----------
    canvas : object
        The page's ``<canvas>``.
    spec : str
        ``"pkg.module:make_app"``; see :func:`emtk.app.load_app`.
    **options
        Passed to :class:`WebPage`.
    """
    from ..app import load_app  # noqa: PLC0415

    return WebPage(canvas, load_app(spec), **options)
