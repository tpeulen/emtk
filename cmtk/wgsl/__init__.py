"""cmtk's shaders, and the two calls that find them.

cmtk is **WGSL-native**. There is one shader for the interface --
``ui.wgsl`` -- and it lives here, in the toolkit, rather
than in whichever program happens to draw with it. Two copies of one
pipeline's shader are two things to keep in step, and the way that fails is
not a crash: it is a panel that looks slightly wrong in one of the two
programs, months later.

This module deliberately imports **nothing**. Finding a file is not a reason
to pull in ``wgpu``, and a consumer that only wants the source text -- a
browser build, a shader-validating test, an application's own loader --
should not have to have an adapter on the machine to read it.

Examples
--------
>>> from cmtk.wgsl import load_wgsl, wgsl_path
>>> wgsl_path("ui.wgsl").name
'ui.wgsl'
>>> "fn vs_ui" in load_wgsl("ui.wgsl")
True
"""
from __future__ import annotations

import pathlib

__all__ = ["WGSL_DIR", "UI_SHADER", "load_wgsl", "wgsl_path"]

#: The directory this file is in, which is where the shaders are.
WGSL_DIR = pathlib.Path(__file__).resolve().parent

#: The interface shader, by name. Spelled as a constant so a consumer that
#: gets it wrong fails at import rather than at pipeline creation, where the
#: message is about a missing file and not about a shader.
UI_SHADER = "ui.wgsl"


def wgsl_path(name: str = UI_SHADER) -> pathlib.Path:
    """Where *name* is on disk.

    Parameters
    ----------
    name : str, optional
        A file in this directory, e.g. ``"ui.wgsl"``.

    Returns
    -------
    pathlib.Path

    Raises
    ------
    FileNotFoundError
        Rather than returning a path that does not exist -- a caller that
        goes on to read it would otherwise fail one frame later, in
        ``create_shader_module``, with a message about WGSL.
    """
    path = WGSL_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"no shader named {name!r} in {WGSL_DIR}")
    return path


def load_wgsl(name: str = UI_SHADER) -> str:
    """The source of *name*, unmodified.

    Parameters
    ----------
    name : str, optional

    Returns
    -------
    str
        The file's text. **Nothing is rewritten on the way through**: a
        consumer that prepends its own prelude concatenates, and
        concatenation is the only composition rule here. A loader that
        edited the source would be the drift this arrangement exists to
        prevent.
    """
    return wgsl_path(name).read_text(encoding="utf-8")
