"""The one place emtk -- and any renderer built on it -- reaches a GPU.

A WGSL renderer (emtk's own interface pass in :mod:`emtk.wgpu_host`, or an
application's 3-D engine drawing beside it) should run unchanged on the
desktop and in a browser. What moves between the two is not the shaders and
not the code around them but the few dozen calls that hand shaders to a
driver, and those live behind :mod:`emtk.gpu.api`:

* :mod:`emtk.gpu.native` serves them with ``wgpu-py`` on the desktop;
* :mod:`emtk.gpu.browser` serves them with the browser's ``navigator.gpu``
  from Pyodide -- the shim :mod:`emtk.web` boots a page on.

Import the seam the way the binding used to be imported::

    from emtk.gpu import api as wgpu

and nothing else may name ``wgpu`` (``tests/test_gpu_seam.py``).
"""
from __future__ import annotations

from .api import backend_name, gpu, use_backend

__all__ = ["gpu", "backend_name", "use_backend"]
