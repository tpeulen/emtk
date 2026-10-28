"""``emtk.logo`` -- logos and icons from image files: ``.ico``, ``.svg``, ``.png`` and the rest.

An application's logo comes as whatever its designer delivered: a Windows icon holding several
sizes, an SVG, a PNG. This reads any of them into an RGBA image at the size it is needed, picks
the right frame of an ``.ico`` (the smallest one at least as large, else the largest), draws an
SVG with :mod:`emtk.svg` at that size instead of scaling pixels, and scales the rest. From there:

* :func:`logo_texture` -- a :class:`~emtk.texture.Texture` to draw with ``im.image``;
* :func:`set_window_icon` -- the window's icon (glfw), given every common size; an app sets
  ``window_icon`` (a path or bytes) and :class:`~emtk.native.NativeHost` applies it;
* :func:`set_app_id` -- on Windows, the process's AppUserModelID (an app's ``app_id``), so the
  task bar groups the window as this application with its icon instead of as ``python.exe``;
* :func:`write_ico` -- an ``.ico`` with every size from any logo, for shortcuts;
* :func:`install_shortcut` -- a Start-menu (and desktop) entry with the icon and the same
  AppUserModelID, so a pinned or started app shows its own icon.

    >>> from emtk.logo import load_logo
    >>> load_logo("app.ico", 32).size          # doctest: +SKIP
    (32, 32)
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
from typing import Any

__all__ = [
    "WINDOW_ICON_SIZES", "install_shortcut", "load_logo", "logo_texture", "set_app_id",
    "set_window_icon", "write_ico",
]

#: The sizes a window icon is given (the system picks per place: title bar, task bar, switcher).
WINDOW_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

Source = "str | os.PathLike[str] | bytes"


def _read(source) -> tuple[bytes, str]:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source), ""
    path = os.fspath(source)
    with open(path, "rb") as f:
        return f.read(), os.path.splitext(path)[1].lower()


def _is_svg(data: bytes, suffix: str) -> bool:
    if suffix in (".svg", ".svgz"):
        return True
    head = data[:512].lstrip()
    return head.startswith(b"<") and b"<svg" in data[:4096]


def load_logo(source, size: int | None = None):
    """The logo in *source* (a path or the file's bytes) as an RGBA ``PIL.Image``.

    Parameters
    ----------
    source : str, os.PathLike or bytes
        An ``.ico``, ``.svg``, or any image Pillow reads (PNG, JPEG, BMP, GIF, WebP, ...).
    size : int, optional
        The edge it should fit in (aspect kept). ``None``: as delivered (an ``.ico``: its
        largest frame; an SVG: its own size).
    """
    from PIL import Image

    data, suffix = _read(source)
    if _is_svg(data, suffix):
        from .svg import rasterize_svg

        natural = rasterize_svg(data)
        scale = 1.0
        if size:
            scale = float(size) / max(1, max(natural.shape[:2]))
        image = Image.fromarray(rasterize_svg(data, scale) if scale != 1.0 else natural, "RGBA")
    else:
        image = Image.open(io.BytesIO(data))
        sizes = sorted(image.info.get("sizes") or [], key=lambda s: s[0] * s[1])
        if sizes:   # an .ico / .icns: take the frame that scales least
            fits = [s for s in sizes if size is None or min(s) >= size]
            image.size = fits[0] if (fits and size is not None) else sizes[-1]
        image.load()
        image = image.convert("RGBA")
    if size and max(image.size) != size:
        w, h = image.size
        k = float(size) / max(w, h)
        image = image.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    return image


def logo_texture(source, size: int | None = None, filter: str = "linear"):
    """The logo as a :class:`~emtk.texture.Texture` (for ``im.image``)."""
    from .texture import Texture

    return Texture.from_pil(load_logo(source, size), filter=filter)


def set_window_icon(canvas: Any, source) -> bool:
    """Give a native window its icon, in every size of :data:`WINDOW_ICON_SIZES`.

    Returns whether it was set: only a glfw window can take one (macOS shows the application
    bundle's icon instead and ignores it; an offscreen canvas has no window).
    """
    window = getattr(canvas, "_window", None)
    if window is None or type(canvas).__module__.rsplit(".", 1)[-1] != "glfw":
        return False
    try:
        import glfw  # noqa: PLC0415

        images = [load_logo(source, s) for s in WINDOW_ICON_SIZES]
        glfw.set_window_icon(window, len(images), images)
    except Exception:  # noqa: BLE001 - a window without an icon is still a window
        return False
    return True


def set_app_id(app_id: str) -> bool:
    """Windows: make this process the application *app_id* (``"Company.Product"``).

    Without it every Python program is ``python.exe`` to the task bar: grouped with the others
    and shown with Python's icon. Call before the first window opens. Elsewhere: nothing.
    """
    if sys.platform != "win32" or not app_id:
        return False
    try:
        import ctypes  # noqa: PLC0415

        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id)) == 0
    except Exception:  # noqa: BLE001
        return False


def write_ico(source, path, sizes=WINDOW_ICON_SIZES) -> str:
    """Write *source* (any logo) as an ``.ico`` holding every size in *sizes*; returns *path*."""
    largest = load_logo(source, max(sizes))
    path = os.fspath(path)
    largest.save(path, format="ICO", sizes=[(s, s) for s in sizes])
    return path


def _ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def install_shortcut(name: str, target: str, arguments: str = "", icon=None,
                     app_id: str | None = None, working_dir: str | None = None,
                     start_menu: bool = True, desktop: bool = False,
                     minimized: bool = False) -> list[str]:
    """Windows: a Start-menu (and optionally desktop) shortcut *name* running *target*.

    *icon* is any logo (an ``.svg`` or ``.png`` is written as ``<name>.ico`` beside the
    shortcut's target); *app_id* is stamped on the shortcut so the started window (which calls
    :func:`set_app_id` with the same id) is one task-bar entry with that icon, also when pinned.
    *minimized* starts the target minimized (a launcher script's console stays out of the way).
    Returns the shortcut paths written; elsewhere nothing.
    """
    if sys.platform != "win32":
        return []
    if icon is not None and not os.fspath(icon).lower().endswith(".ico"):
        icon = write_ico(icon, os.path.join(os.path.dirname(os.path.abspath(target)),
                                            f"{name}.ico"))
    places = []
    if start_menu:
        places.append(os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                                   "Start Menu", "Programs"))
    if desktop:
        places.append(os.path.join(os.path.expanduser("~"), "Desktop"))
    written = []
    for place in places:
        os.makedirs(place, exist_ok=True)
        link = os.path.join(place, f"{name}.lnk")
        script = [
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s)" % _ps_quote(link),
            "$s.TargetPath = %s" % _ps_quote(target),
            "$s.Arguments = %s" % _ps_quote(arguments),
            "$s.WorkingDirectory = %s" % _ps_quote(working_dir or os.path.dirname(target)),
        ]
        if icon is not None:
            script.append("$s.IconLocation = %s" % _ps_quote(f"{os.fspath(icon)},0"))
        if minimized:
            script.append("$s.WindowStyle = 7")
        script.append("$s.Save()")
        subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(script)],
                       check=True, capture_output=True)
        if app_id:
            _stamp_app_id(link, app_id)
        written.append(link)
    return written


def _stamp_app_id(link: str, app_id: str) -> None:
    """Set System.AppUserModel.ID on a .lnk (through the shell's property store)."""
    import ctypes  # noqa: PLC0415
    from ctypes import wintypes  # noqa: PLC0415

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                    ("d", ctypes.c_ubyte * 8)]

        def __init__(self, text):
            super().__init__()
            ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(self))

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("pwsz", ctypes.c_wchar_p), ("pad", ctypes.c_void_p)]

    ole32, shell32 = ctypes.oledll.ole32, ctypes.oledll.shell32
    ole32.CoInitialize(None)
    store = ctypes.c_void_p()
    iid = GUID("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")             # IPropertyStore
    shell32.SHGetPropertyStoreFromParsingPath(link, None, 2, ctypes.byref(iid),   # GPS_READWRITE
                                              ctypes.byref(store))
    vtbl = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0],
                       ctypes.POINTER(ctypes.c_void_p))
    proto = ctypes.WINFUNCTYPE
    set_value = proto(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                      ctypes.POINTER(PROPVARIANT))(vtbl[6])
    commit = proto(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])
    release = proto(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    key = PROPERTYKEY(GUID("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"), 5)  # AppUserModel.ID
    value = PROPVARIANT(vt=31, pwsz=app_id)                            # VT_LPWSTR
    try:
        set_value(store, ctypes.byref(key), ctypes.byref(value))
        commit(store)
    finally:
        release(store)
