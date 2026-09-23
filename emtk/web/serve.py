"""Build and serve an emtk app as a web page: Pyodide + WebGPU, no build step.

Use
---
::

    python -m emtk.web.serve --app pkg.module:make_app [--package PATH_OR_NAME ...]
        [--extra-packages NAME_OR_PATH ...] [--pyodide-packages numpy,scipy,...]
        [--wheels path/*.whl ...] [--port 8788] [--no-open]

then open the printed URL. ``make_app()`` takes no arguments and returns an
emtk control or an :class:`emtk.app.Surface` -- see :mod:`emtk.app`. The same
factory runs on the desktop with ``python -m emtk.native --app ...``.

Example -- ImPlot's demo in a browser tab::

    python -m emtk.web.serve --app emtk.implot_demo:make_app

What it builds
--------------
A directory (``--out``, by default a per-app folder under the user cache)
holding:

* ``index.html`` -- the canvas, a status bar, and the build's configuration
  as JSON;
* ``boot.js`` -- the loader (:mod:`emtk.web`'s, copied);
* ``app.zip`` -- the **app package**, **emtk** itself, and every
  ``--extra-packages`` dependency: pure Python plus the data files named by
  :data:`INCLUDE_SUFFIXES` (emtk's glyph atlas and WGSL shader are data, and a
  zip without them imports cleanly and then cannot lay out a menu bar). A
  wheel would be tidier and needs a build step; a zip needs none;
* ``wheels/`` -- local wheels (``--wheels``), installed in the page with
  ``pyodide.loadPackage`` -- a compiled extension built for Pyodide, for
  instance;
* ``pyodide/`` -- a local Pyodide, when ``--pyodide DIR`` is given.

Packages Pyodide already ships (numpy, scipy, Pillow, ...) are *not* zipped:
``--pyodide-packages`` names them and the page loads them from the Pyodide
distribution. numpy and Pillow are loaded by default -- emtk's GPU renderer
builds vertices with numpy and decodes its glyph atlas with Pillow.

Why a script and not ``python -m http.server``
----------------------------------------------
Headers. ``--isolate`` sends cross-origin isolation (COOP/COEP), which Pyodide
threading wants -- and which **blocks the CDN** Pyodide is otherwise loaded
from, so it is off unless ``--pyodide`` serves a local copy. Every response is
``no-store``: the archive is a build artifact, and a cached one runs old code.
A browser enables WebGPU only on a secure origin, which ``localhost`` is.
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import glob
import html
import http.server
import importlib.util
import json
import os
import pathlib
import shutil
import sys
import zipfile
from collections.abc import Iterable, Sequence

__all__ = [
    "Bundle",
    "DEFAULT_PORT",
    "DEFAULT_PYODIDE_PACKAGES",
    "DEFAULT_PYODIDE_URL",
    "INCLUDE_SUFFIXES",
    "WEB_DIR",
    "build",
    "default_out_dir",
    "main",
    "pack_zip",
    "resolve_package",
    "serve",
]

#: This directory: ``index.html`` and ``boot.js``.
WEB_DIR = pathlib.Path(__file__).resolve().parent

#: The emtk package, which every page ships: it *is* the host.
EMTK_DIR = WEB_DIR.parent

#: Where the page is served. Not 8765, which is ChiSurf's command port.
DEFAULT_PORT = 8788

#: The Pyodide the page loads when no local one is given.
DEFAULT_PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.28.0/full/pyodide.js"

#: Loaded from the Pyodide distribution on every page (see the module docstring).
DEFAULT_PYODIDE_PACKAGES = ("numpy", "Pillow")

#: File types packed into the archive: code and the data an app reads at run
#: time. Anything else in a package directory (build output, notebooks,
#: compiled extensions for *this* platform) stays behind.
INCLUDE_SUFFIXES = (".py", ".wgsl", ".json", ".png", ".txt", ".csv", ".toml",
                    ".yaml", ".yml", ".js", ".html", ".css", ".md")

#: Directory names never packed.
EXCLUDE_DIRS = ("__pycache__", ".git", ".pytest_cache", ".mypy_cache")

#: Where the archive is unpacked on Pyodide's filesystem and put on ``sys.path``.
EXTRACT_DIR = "/emtk_app"

#: The archive's file name in the served directory.
ARCHIVE_NAME = "app.zip"


@dataclasses.dataclass
class Bundle:
    """Everything a page build needs to know.

    Parameters
    ----------
    app : str
        ``"pkg.module:make_app"``.
    packages : list of str or pathlib.Path
        The app's own packages: directories, or importable names. Empty means
        the top-level package of :attr:`app`.
    extra_packages : list of str or pathlib.Path
        Installed pure-Python dependencies Pyodide does not ship, by import
        name or path. emtk is always added.
    pyodide_packages : list of str
        Loaded from the Pyodide distribution.
    wheels : list of pathlib.Path
        Local wheels to install in the page.
    title : str
        The page title; the app spec when empty.
    include_suffixes : tuple of str
        See :data:`INCLUDE_SUFFIXES`; an app with data of its own (``.pdb``,
        ``.npz``) extends it.
    exclude : tuple of str
        Archive paths to leave out, as prefixes (``"myapp/qt/"``) -- a
        desktop-only subpackage a page cannot import.
    extra_files : dict
        ``archive path -> bytes`` written into the archive as well (a version
        stamp computed at build time, say).
    pyodide_url : str
        Where ``pyodide.js`` comes from.
    mount, drop : bool
        Whether the page offers "Mount folder" and file drop.
    ready_message : str
        The status line once the first frame is drawn -- what a browser test
        waits for.
    """

    app: str
    packages: list = dataclasses.field(default_factory=list)
    extra_packages: list = dataclasses.field(default_factory=list)
    pyodide_packages: list = dataclasses.field(
        default_factory=lambda: list(DEFAULT_PYODIDE_PACKAGES))
    wheels: list = dataclasses.field(default_factory=list)
    title: str = ""
    include_suffixes: tuple = INCLUDE_SUFFIXES
    exclude: tuple = ()
    extra_files: dict = dataclasses.field(default_factory=dict)
    pyodide_url: str = DEFAULT_PYODIDE_URL
    mount: bool = True
    drop: bool = True
    ready_message: str = "ready"

    def __post_init__(self) -> None:
        module, sep, attribute = str(self.app).partition(":")
        if not sep or not module or not attribute:
            raise ValueError(f"--app is 'package.module:factory', got {self.app!r}")

    @property
    def name(self) -> str:
        """The app's top-level package name."""
        return str(self.app).split(":", 1)[0].split(".", 1)[0]


# --------------------------------------------------------------------------- #
# Packing
# --------------------------------------------------------------------------- #
def resolve_package(item) -> pathlib.Path:
    """A package directory (or single module file) from a path or an import name.

    Parameters
    ----------
    item : str or pathlib.Path
        A directory holding ``__init__.py``, a ``.py`` file, or an importable
        name such as ``"ihm"``.

    Returns
    -------
    pathlib.Path

    Raises
    ------
    FileNotFoundError
        If it is neither an existing path nor importable here. Raised, not
        warned: a page missing a dependency imports it at the worst moment,
        in a browser console, far from the build that dropped it.
    """
    path = pathlib.Path(os.path.expanduser(str(item)))
    if path.exists():
        return path.resolve()
    spec = importlib.util.find_spec(str(item))
    if spec is None or not spec.origin or spec.origin in ("built-in", "frozen"):
        raise FileNotFoundError(
            f"{item!r} is neither a path nor an importable package here; "
            f"install it (pip install {item}) or pass its directory")
    origin = pathlib.Path(spec.origin).resolve()
    if origin.name == "__init__.py":
        return origin.parent
    if origin.suffix != ".py":
        raise FileNotFoundError(
            f"{item!r} is a compiled module ({origin.name}); a page needs a "
            "Pyodide wheel for it -- pass it with --wheels")
    return origin


def _files(root: pathlib.Path, suffixes: Iterable[str]) -> list[pathlib.Path]:
    """Files under a package directory worth shipping, sorted."""
    if root.is_file():
        return [root]
    suffixes = tuple(suffixes)
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        out.append(path)
    return out


def pack_zip(bundle: Bundle, destination) -> pathlib.Path:
    """Write the app archive: the app's packages, emtk and the extra packages.

    Parameters
    ----------
    bundle : Bundle
    destination : str or pathlib.Path
        The ``.zip`` to write.

    Returns
    -------
    pathlib.Path
        The archive. Paths inside are relative to each package's parent, so
        unpacking it onto a directory on ``sys.path`` makes every package
        importable by its own name.
    """
    destination = pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    roots: list[pathlib.Path] = []
    for item in list(bundle.packages or [bundle.name]) + [EMTK_DIR] + list(bundle.extra_packages):
        root = resolve_package(item)
        if root not in roots:
            roots.append(root)
    exclude = tuple(str(e).replace(os.sep, "/") for e in bundle.exclude)
    written: set[str] = set()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for root in roots:
            for path in _files(root, bundle.include_suffixes):
                name = path.relative_to(root.parent).as_posix()
                if name in written or (exclude and name.startswith(exclude)):
                    continue
                archive.write(path, name)
                written.add(name)
        for name, data in (bundle.extra_files or {}).items():
            archive.writestr(str(name), data)
    return destination


def default_out_dir(bundle: Bundle) -> pathlib.Path:
    """Where a build goes when ``--out`` is not given: the user cache, per app."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return pathlib.Path(base) / "emtk-web" / bundle.name


def _config(bundle: Bundle, wheels: Sequence[str]) -> dict:
    return {
        "app": bundle.app,
        "name": bundle.name,
        "archive": ARCHIVE_NAME,
        "extract_dir": EXTRACT_DIR,
        "pyodide_packages": list(bundle.pyodide_packages),
        "wheels": list(wheels),
        "mount": bool(bundle.mount),
        "drop": bool(bundle.drop),
        "ready_message": str(bundle.ready_message),
    }


def render_index(bundle: Bundle, config: dict, pyodide_js: str) -> str:
    """``index.html`` with the build's title, app and configuration filled in."""
    template = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    # `</` cannot appear inside a <script> element's text, whatever the type.
    payload = json.dumps(config, indent=1).replace("</", "<\\/")
    return (template
            .replace("{{TITLE}}", html.escape(bundle.title or bundle.app))
            .replace("{{APP}}", html.escape(bundle.app, quote=True))
            .replace("{{PYODIDE_JS}}", html.escape(pyodide_js, quote=True))
            .replace("{{CONFIG}}", payload))


def build(bundle: Bundle, out_dir=None, pyodide: pathlib.Path | None = None) -> pathlib.Path:
    """Write the whole site for *bundle* into *out_dir* and return it.

    Parameters
    ----------
    bundle : Bundle
    out_dir : str or pathlib.Path, optional
        Defaults to :func:`default_out_dir`.
    pyodide : pathlib.Path, optional
        A local Pyodide distribution, copied to ``pyodide/`` and used instead
        of :attr:`Bundle.pyodide_url`.
    """
    out = pathlib.Path(out_dir) if out_dir is not None else default_out_dir(bundle)
    out.mkdir(parents=True, exist_ok=True)
    pack_zip(bundle, out / ARCHIVE_NAME)
    shutil.copyfile(WEB_DIR / "boot.js", out / "boot.js")

    wheel_dir = out / "wheels"
    if wheel_dir.exists():
        shutil.rmtree(wheel_dir)
    wheels = []
    for wheel in bundle.wheels:
        wheel = pathlib.Path(os.path.expanduser(str(wheel)))
        if wheel.suffix != ".whl" or not wheel.is_file():
            raise FileNotFoundError(f"not a wheel file: {wheel}")
        wheel_dir.mkdir(exist_ok=True)
        shutil.copyfile(wheel, wheel_dir / wheel.name)
        wheels.append(f"wheels/{wheel.name}")

    pyodide_js = bundle.pyodide_url
    if pyodide is not None:
        target = out / "pyodide"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(pathlib.Path(pyodide), target)
        pyodide_js = "pyodide/pyodide.js"
    (out / "index.html").write_text(
        render_index(bundle, _config(bundle, wheels), pyodide_js), encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #
class Handler(http.server.SimpleHTTPRequestHandler):
    """Static files; no-store; cross-origin isolation only when asked."""

    #: COOP/COEP. Off by default: ``require-corp`` blocks the Pyodide CDN.
    isolate = False

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".mjs": "text/javascript",
        ".js": "text/javascript",
        ".whl": "application/zip",
        ".zip": "application/zip",
    }

    def end_headers(self) -> None:
        if self.isolate:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args) -> None:
        """Only the misses; the default logs every asset."""
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def already_serving(port: int, app: str) -> bool:
    """Whether *port* already serves a page for *app*."""
    import urllib.request  # noqa: PLC0415

    marker = f'<meta name="emtk-app" content="{html.escape(app, quote=True)}">'.encode()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as page:
            return marker in page.read(4096)
    except Exception:  # noqa: BLE001 - nothing there, or something else
        return False


def bind(handler, port: int):
    """``(server, port)``, stepping to a free port when *port* is taken."""
    try:
        return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler), port
    except OSError as exc:
        if exc.errno not in (48, 98):  # EADDRINUSE on BSD and Linux
            raise
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    chosen = int(server.server_address[1])
    print(f"port {port} is in use; serving on {chosen} instead")
    return server, chosen


def serve(bundle: Bundle, port: int = DEFAULT_PORT, out_dir=None,
          pyodide: pathlib.Path | None = None, open_browser: bool = False,
          isolate: bool = False) -> None:
    """Build *bundle* and serve it until interrupted."""
    if already_serving(port, bundle.app):
        url = f"http://localhost:{port}/"
        print(f"{bundle.app} is already being served at {url}")
        if open_browser:
            import webbrowser  # noqa: PLC0415

            webbrowser.open(url)
        return
    site = build(bundle, out_dir, pyodide=pyodide)
    size = (site / ARCHIVE_NAME).stat().st_size / 1024
    print(f"built {site} ({ARCHIVE_NAME}: {size:.0f} KB)")
    handler = functools.partial(type("Handler", (Handler,), {"isolate": bool(isolate)}),
                                directory=str(site))
    server, port = bind(handler, port)
    url = f"http://localhost:{port}/"
    print(f"serving {bundle.app} at {url}  (ctrl-c to stop)", flush=True)
    if open_browser:
        import threading  # noqa: PLC0415
        import webbrowser  # noqa: PLC0415

        # After the server listens, or the browser races it to a refusal.
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def _split(values: Sequence[str] | None) -> list[str]:
    """``--x a,b --x c`` and ``--x a b`` alike -> ``[a, b, c]``."""
    out: list[str] = []
    for value in values or ():
        out.extend(part.strip() for part in str(value).split(",") if part.strip())
    return out


def _expand_wheels(values: Sequence[str] | None) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for value in _split(values):
        matches = sorted(glob.glob(os.path.expanduser(value)))
        if not matches:
            raise FileNotFoundError(f"--wheels {value}: no such file")
        out.extend(pathlib.Path(m) for m in matches)
    return out


def parser() -> argparse.ArgumentParser:
    """The command line, shared by apps that wrap it with a preset bundle."""
    p = argparse.ArgumentParser(
        prog="python -m emtk.web.serve",
        description="Build an emtk app for the browser (Pyodide + WebGPU) and serve it.",
    )
    p.add_argument("--app", help="factory spec 'package.module:make_app'")
    p.add_argument("--package", action="append", default=None,
                   help="the app's package (directory or import name); repeatable. "
                        "Default: the --app module's top-level package")
    p.add_argument("--extra-packages", nargs="+", action="extend", default=None,
                   metavar="PKG", help="pure-Python dependencies to ship (names or paths)")
    p.add_argument("--pyodide-packages", nargs="+", action="extend", default=None,
                   metavar="NAME",
                   help="packages from the Pyodide distribution, e.g. numpy,scipy "
                        f"(default {','.join(DEFAULT_PYODIDE_PACKAGES)}; always included)")
    p.add_argument("--wheels", nargs="+", action="extend", default=None, metavar="WHL",
                   help="local wheels to install in the page (globs allowed)")
    p.add_argument("--exclude", nargs="+", action="extend", default=None, metavar="PREFIX",
                   help="archive path prefixes to leave out, e.g. myapp/qt/")
    p.add_argument("--include-suffix", nargs="+", action="extend", default=None,
                   metavar=".EXT", help="extra file types to ship, e.g. .npz .pdb")
    p.add_argument("--title", default="")
    p.add_argument("--out", type=pathlib.Path, default=None,
                   help="build directory (default: ~/.cache/emtk-web/<app>)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--pyodide", type=pathlib.Path, default=None,
                   help="a local Pyodide distribution to serve instead of the CDN")
    p.add_argument("--pyodide-url", default=DEFAULT_PYODIDE_URL)
    p.add_argument("--isolate", action="store_true",
                   help="send COOP/COEP; needs --pyodide, since it blocks the CDN")
    p.add_argument("--build-only", action="store_true", help="build and exit")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    return p


def bundle_from_args(args, base: Bundle | None = None) -> Bundle:
    """A :class:`Bundle` from parsed arguments, on top of *base* when given."""
    if base is None:
        if not args.app:
            raise SystemExit("--app is required")
        base = Bundle(app=args.app)
    bundle = dataclasses.replace(base)
    if args.app:
        bundle = dataclasses.replace(bundle, app=args.app)
    if args.package:
        bundle.packages = _split(args.package)
    bundle.extra_packages = list(bundle.extra_packages) + _split(args.extra_packages)
    wanted = list(bundle.pyodide_packages)
    for name in _split(args.pyodide_packages):
        if name not in wanted:
            wanted.append(name)
    bundle.pyodide_packages = wanted
    bundle.wheels = list(bundle.wheels) + _expand_wheels(args.wheels)
    bundle.exclude = tuple(bundle.exclude) + tuple(_split(args.exclude))
    bundle.include_suffixes = tuple(bundle.include_suffixes) + tuple(
        s if s.startswith(".") else "." + s for s in _split(args.include_suffix))
    if args.title:
        bundle.title = args.title
    if args.pyodide_url != DEFAULT_PYODIDE_URL:
        bundle.pyodide_url = args.pyodide_url
    return bundle


def main(argv: Sequence[str] | None = None, base: Bundle | None = None) -> int:
    """Command-line entry point; *base* presets a bundle for an app's own wrapper."""
    args = parser().parse_args(argv)
    bundle = bundle_from_args(args, base)
    if args.build_only:
        print(build(bundle, args.out, pyodide=args.pyodide))
        return 0
    serve(bundle, port=args.port, out_dir=args.out, pyodide=args.pyodide,
          open_browser=not args.no_open, isolate=args.isolate)
    return 0


if __name__ == "__main__":  # pragma: no cover - a dev server
    sys.exit(main())
