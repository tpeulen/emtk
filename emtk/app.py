"""What a host drives: the app contract shared by the browser and the desktop.

Two levels, and a factory
-------------------------
emtk already has one contract every host speaks -- the **control**:
``draw(painter, x, y, w, h)`` plus whichever of ``press``, ``drag``,
``hover``, ``release``, ``key`` and ``scroll`` it answers
(:class:`~.control.Control`, :mod:`.qt_host`, :mod:`.tk_host`,
:mod:`.wgpu_host`). An application that only draws an interface is a control
and nothing else, and it runs under every host unchanged.

The GPU hosts -- :mod:`emtk.web` in a page and :mod:`emtk.native` on a
desktop window -- drive one level lower, a :class:`Surface`: something that
is handed a device and a texture view each frame and is told about pointer,
wheel, key, resize and file-drop events in emtk's own vocabulary
(:mod:`emtk.events`, :mod:`emtk.keys`). A control is lifted onto that level by
:class:`ControlSurface`, which draws it with
:class:`~.wgpu_host.WgpuRenderer` in one draw call. An application that draws
more than an interface -- a 3-D viewer rendering its own scene -- subclasses :class:`Surface` directly and renders whatever it likes into the
view it is given.

Both hosts start an application the same way, from a **factory spec**::

    pkg.module:make_app

where ``make_app()`` takes no arguments and returns either a control or a
:class:`Surface`. :func:`load_app` resolves the spec and :func:`as_surface`
lifts the result, so ``python -m emtk.web.serve --app pkg.module:make_app``
and ``python -m emtk.native --app pkg.module:make_app`` open the same
application in a browser tab and in a desktop window.

Immediate mode
--------------
:class:`ImApp` turns a ``gui()`` callback written against :mod:`emtk.im` --
Dear ImGui's ``Begin ... End`` style -- into a control, feeding the host's
events into an :class:`~.im_core.IO` and running one frame per draw. It is
also a control under the classic hosts, so a ``gui()`` runs in a Tk or Qt
window as well.

Nothing here imports a GPU binding or a toolkit at module scope.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence
from typing import Any

from .events import (
    ALT_MODIFIER,
    CONTROL_MODIFIER,
    LEFT_BUTTON,
    META_MODIFIER,
    MIDDLE_BUTTON,
    RIGHT_BUTTON,
    SHIFT_MODIFIER,
)

__all__ = [
    "Surface",
    "ControlSurface",
    "ImApp",
    "load_app",
    "as_surface",
    "window_title",
    "WHEEL_ROWS",
]

#: Rows a wheel notch scrolls a classic control by -- the convention
#: :mod:`.qt_host` and :mod:`.tk_host` already use (``scroll(-3)`` per notch
#: away from the user).
WHEEL_ROWS = 3


def window_title(app) -> str | None:
    """The title *app* wants its window to carry now, or ``None`` for "leave it".

    An app says so with a ``window_title`` attribute or property (a string);
    a host reads it after each frame and retitles the window when it changed
    -- "ndX -- m000.bur" once a file is open. Hosts: :mod:`.native`
    (``canvas.set_title``), :mod:`.tk_host` (``root.title``), :mod:`.qt_host`
    (the top-level widget's title) and :mod:`.web` (``document.title``).
    """
    title = getattr(app, "window_title", None)
    if callable(title):
        title = title()
    return None if title is None else str(title)


class Surface:
    """A GPU-drawn application surface, as :mod:`emtk.web` and :mod:`emtk.native` drive it.

    Coordinates in every event are **logical** pixels (CSS pixels in a page),
    the space an interface lays itself out in. Sizes handed to
    :meth:`attach` and :meth:`on_resize` are **device** pixels plus the ratio
    between the two, because that is what a surface is allocated in.

    Every ``on_*`` handler returns whether a frame is now due. A host redraws
    only when one is, so a press that changes no pixels costs no frame.
    Defaults do nothing and ask for no frame; a subclass implements what it
    answers.

    Buttons are :mod:`emtk.events`' ``*_BUTTON`` values, modifiers a mask of
    its ``*_MODIFIER`` values, keys :mod:`emtk.keys`' ``KEY_*`` values (``0``
    for a key that only types *text*). Wheel *steps* are notches, positive
    away from the user.
    """

    # -- lifecycle ------------------------------------------------------- #
    def attach(self, device, format: str, width: int, height: int,
               ratio: float) -> None:
        """Take the GPU device and the target's colour format, once.

        Parameters
        ----------
        device : object
            A ``GPUDevice`` from :mod:`emtk.gpu` -- ``wgpu-py``'s on the
            desktop, the browser shim's in a page. The same methods either way.
        format : str
            The colour format of the views :meth:`render` will draw into.
        width, height : int
            The target's size in device pixels.
        ratio : float
            Device pixels per logical pixel.
        """

    def on_resize(self, width: int, height: int, ratio: float) -> bool:
        """The target changed size (device pixels) or pixel ratio."""
        return True

    def render(self, view):
        """Draw one frame into *view*, a texture view of the attached format.

        May return a statistic of the frame (a quad count, say); hosts ignore
        it, and :meth:`emtk.web.page.WebPage.draw` hands it back to a caller.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement render()")

    def animating(self) -> bool:
        """Whether frames are wanted continuously (a movie, a live plot)."""
        return False

    # -- input ----------------------------------------------------------- #
    def on_pointer_press(self, x: float, y: float, button: int, modifiers: int,
                         double: bool = False) -> bool:
        """A button went down; *double* for the second press of a double click."""
        return False

    def on_pointer_move(self, x: float, y: float, buttons: int,
                        modifiers: int) -> bool:
        """The pointer moved; *buttons* is the mask of buttons held."""
        return False

    def on_pointer_release(self, x: float, y: float, button: int,
                           modifiers: int) -> bool:
        """A button came up."""
        return False

    def on_wheel(self, x: float, y: float, steps: int, modifiers: int) -> bool:
        """The wheel turned *steps* notches (positive away from the user)."""
        return False

    def on_key_press(self, key: int, text: str, modifiers: int) -> bool:
        """A key went down. Returns whether it was *consumed* -- see the note.

        Notes
        -----
        The browser host uses the answer to decide ``preventDefault``, so it
        must be honest: a surface that claims every key takes reload, find
        and the developer console away from the page.
        """
        return False

    def on_files_dropped(self, paths: Sequence[str]) -> bool:
        """Files were dropped on the surface, as local paths.

        In a page the bytes have already been written to Pyodide's
        filesystem (under :data:`emtk.web.page.DROP_DIR`) and these are those
        paths -- a surface never learns the difference.
        """
        return False


class ControlSurface(Surface):
    """A control, drawn on the GPU in one draw call.

    Parameters
    ----------
    control : object
        Anything with the control contract (see the module docstring). Richer
        hooks are used when the control has them, because the classic
        contract cannot say which button went down or where the wheel was:

        ``pointer_press(x, y, button, modifiers, clicks)``,
        ``pointer_move(x, y, buttons, modifiers)``,
        ``pointer_release(x, y, button, modifiers)``,
        ``wheel(x, y, steps, modifiers)``, ``files_dropped(paths)`` and
        ``animating()``.
    font_pt : float, optional
        Point size of the interface font.
    background : tuple, optional
        0-255 RGB(A) cleared to before the control draws.
    """

    def __init__(self, control, font_pt: float = 9.0,
                 background: tuple = (30, 32, 38)) -> None:
        self.control = control
        self.font_pt = float(font_pt)
        self.background = tuple(background)
        self.renderer = None
        self.format: str | None = None
        self.size = (1, 1)
        self.ratio = 1.0
        self._painter = None
        self._painter_ratio: float | None = None
        self._pressed = False

    # -- geometry -------------------------------------------------------- #
    def _box(self) -> tuple[float, float, float, float]:
        """The box the control is drawn in: the whole surface, in logical pixels."""
        return (0.0, 0.0, self.size[0] / self.ratio, self.size[1] / self.ratio)

    def _hook(self, name: str):
        handler = getattr(self.control, name, None)
        return handler if callable(handler) else None

    # -- lifecycle ------------------------------------------------------- #
    def attach(self, device, format, width, height, ratio) -> None:
        from .wgpu_host import WgpuRenderer  # noqa: PLC0415

        self.renderer = WgpuRenderer(device=device, format=format)
        self.format = str(format)
        self.on_resize(width, height, ratio)

    def on_resize(self, width, height, ratio) -> bool:
        self.size = (max(int(width), 1), max(int(height), 1))
        self.ratio = float(ratio) if float(ratio or 0.0) > 0.0 else 1.0
        return True

    def render(self, view) -> None:
        if self.renderer is None:
            raise RuntimeError("ControlSurface.render before attach()")
        # Rebuilt when the ratio changes (a window dragged to another
        # display); a stale scale draws at half size while hit tests answer
        # for full size, so every click misses by the ratio.
        if self._painter is None or self._painter_ratio != self.ratio:
            self._painter = self.renderer.painter(font_pt=self.font_pt,
                                                  scale=self.ratio)
            self._painter_ratio = self.ratio
        painter = self._painter
        painter.clear()
        self.control.draw(painter, *self._box())
        width, height = self.size
        self.renderer.render(painter, width, height, view,
                             background=self.background, format=self.format)

    def animating(self) -> bool:
        hook = self._hook("animating")
        return bool(hook()) if hook is not None else False

    # -- input ----------------------------------------------------------- #
    def on_pointer_press(self, x, y, button, modifiers, double=False) -> bool:
        clicks = 2 if double else 1
        rich = self._hook("pointer_press")
        if rich is not None:
            rich(float(x), float(y), int(button), int(modifiers), clicks)
            return True
        if button != LEFT_BUTTON:
            return False
        press = self._hook("press")
        self._pressed = True
        if press is not None:
            press(float(x), float(y), *self._box(), int(modifiers), clicks)
        return True

    def on_pointer_move(self, x, y, buttons, modifiers) -> bool:
        rich = self._hook("pointer_move")
        if rich is not None:
            rich(float(x), float(y), int(buttons), int(modifiers))
            return True
        name = "drag" if (self._pressed and int(buttons) & LEFT_BUTTON) else "hover"
        handler = self._hook(name)
        if handler is None:
            return False
        handler(float(x), float(y), *self._box())
        return True

    def on_pointer_release(self, x, y, button, modifiers) -> bool:
        rich = self._hook("pointer_release")
        if rich is not None:
            rich(float(x), float(y), int(button), int(modifiers))
            return True
        if button != LEFT_BUTTON:
            return False
        self._pressed = False
        release = self._hook("release")
        if release is not None:
            release()
        return True

    def on_wheel(self, x, y, steps, modifiers) -> bool:
        rich = self._hook("wheel")
        if rich is not None:
            rich(float(x), float(y), int(steps), int(modifiers))
            return True
        scroll = self._hook("scroll")
        if scroll is None or not steps:
            return False
        scroll(-WHEEL_ROWS * int(steps))
        return True

    def on_key_press(self, key, text, modifiers) -> bool:
        handler = self._hook("key")
        if handler is None:
            return False
        return bool(handler(int(key), str(text or ""), int(modifiers)))

    def on_files_dropped(self, paths) -> bool:
        handler = self._hook("files_dropped")
        if handler is None:
            return False
        handler([str(p) for p in paths])
        return True


class ImApp:
    """An immediate-mode ``gui()`` as a control -- Dear ImGui's app loop, in emtk.

    Parameters
    ----------
    gui : callable
        Called with no arguments inside :func:`emtk.frame` once per drawn
        frame; it calls :mod:`emtk.im` / :mod:`emtk.implot` functions, exactly
        as ``examples/hello_world.py`` does.
    continuous : bool, optional
        Ask the host for frames continuously, as a render loop does. Off by
        default: a page or window then draws on events only, and a widget that
        animates asks for its own frames (``ctx.frame_requested``).
    style : emtk.style.Style, optional

    Notes
    -----
    Events only *record* into :attr:`io`; the next :meth:`draw` runs the
    frame that sees them, and ``end_frame`` spends the edges. That is how a
    Dear ImGui backend queues input, and it means a press and a release that
    arrive before one frame are both seen, as a click.
    """

    def __init__(self, gui: Callable[[], Any], continuous: bool = False,
                 style=None) -> None:
        from .im_core import IO  # noqa: PLC0415

        self.gui = gui
        self.continuous = bool(continuous)
        self.style = style
        self.io = IO()
        self.storage: dict = {}
        self.wants_frame = False

    # -- drawing --------------------------------------------------------- #
    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        from .im_core import frame  # noqa: PLC0415

        with frame(painter, (x, y, w, h), io=self.io, style=self.style,
                   storage=self.storage) as ctx:
            self.gui()
        self.wants_frame = bool(getattr(ctx, "frame_requested", False))

    def animating(self) -> bool:
        return self.continuous or self.wants_frame

    # -- the rich hooks (ControlSurface) --------------------------------- #
    @staticmethod
    def _index(button: int) -> int:
        return {LEFT_BUTTON: 0, RIGHT_BUTTON: 1, MIDDLE_BUTTON: 2}.get(int(button), -1)

    def _modifiers(self, modifiers: int) -> None:
        io = self.io
        io.key_ctrl = bool(modifiers & CONTROL_MODIFIER)
        io.key_shift = bool(modifiers & SHIFT_MODIFIER)
        io.key_alt = bool(modifiers & ALT_MODIFIER)
        io.key_super = bool(modifiers & META_MODIFIER)

    def pointer_press(self, x, y, button, modifiers=0, clicks=1) -> None:
        i = self._index(button)
        self.io.mouse_pos = (float(x), float(y))
        self._modifiers(int(modifiers))
        if i < 0:
            return
        self.io.mouse_down[i] = True
        self.io.mouse_clicked[i] = True
        self.io.mouse_double_clicked[i] = int(clicks) >= 2
        self.io.mouse_clicked_pos[i] = (float(x), float(y))

    def pointer_move(self, x, y, buttons=0, modifiers=0) -> None:
        self.io.mouse_pos = (float(x), float(y))
        self._modifiers(int(modifiers))

    def pointer_release(self, x, y, button, modifiers=0) -> None:
        i = self._index(button)
        self.io.mouse_pos = (float(x), float(y))
        self._modifiers(int(modifiers))
        if i < 0:
            return
        self.io.mouse_down[i] = False
        self.io.mouse_released[i] = True

    def wheel(self, x, y, steps, modifiers=0) -> None:
        self.io.mouse_pos = (float(x), float(y))
        self.io.mouse_wheel += float(steps)
        self._modifiers(int(modifiers))

    # -- the classic control contract (qt_host, tk_host, wgpu_host) ------ #
    def press(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0, modifiers=0, clicks=1):
        self.pointer_press(px, py, LEFT_BUTTON, modifiers, clicks)

    def drag(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0):
        self.pointer_move(px, py, LEFT_BUTTON)

    def hover(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0):
        self.pointer_move(px, py, 0)

    def release(self) -> None:
        self.pointer_release(*self.io.mouse_pos, LEFT_BUTTON)

    def scroll(self, rows: int) -> int:
        # Rows are sign-flipped notches (see WHEEL_ROWS); back to notches.
        self.io.mouse_wheel += -float(rows) / WHEEL_ROWS
        return 0

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        self.io.key = int(key)
        self.io.text = str(text or "")
        self._modifiers(int(modifiers))
        # Honest about consumption: only while a widget holds the keyboard
        # (a focused text field), as ImGui's WantCaptureKeyboard says -- as of
        # the last frame, which is the one the user is looking at. The key is
        # recorded either way; the host draws a frame after every key.
        return bool(self.io.want_capture_keyboard)


def load_app(spec: str):
    """Resolve ``"pkg.module:factory"`` and call the factory.

    Parameters
    ----------
    spec : str
        A module path and a callable in it, joined by ``:``. The callable
        takes no arguments.

    Returns
    -------
    object
        Whatever the factory returned -- a control or a :class:`Surface`.

    Raises
    ------
    ValueError
        If *spec* is not ``module:attribute``.
    """
    module_name, sep, attribute = str(spec).partition(":")
    if not sep or not module_name or not attribute:
        raise ValueError(
            f"an app spec is 'package.module:factory', got {spec!r}"
        )
    target: Any = importlib.import_module(module_name)
    for part in attribute.split("."):
        target = getattr(target, part)
    if not callable(target):
        raise TypeError(f"{spec} is not callable")
    return target()


def as_surface(app, **options) -> Surface:
    """*app* as a :class:`Surface`: itself if it is one, else a :class:`ControlSurface`.

    Parameters
    ----------
    app : object
        A :class:`Surface`, or anything with ``draw(painter, x, y, w, h)``.
    **options
        Passed to :class:`ControlSurface` (``font_pt``, ``background``).

    Raises
    ------
    TypeError
        If *app* is neither.
    """
    if isinstance(app, Surface):
        return app
    if callable(getattr(app, "draw", None)):
        return ControlSurface(app, **options)
    raise TypeError(
        f"{type(app).__name__} is neither an emtk.app.Surface nor a control "
        "with draw(painter, x, y, w, h)"
    )
