"""emtk in a browser: Pyodide runs the app, the browser's WebGPU draws it.

* :mod:`emtk.web.serve` -- builds a page for an app factory and serves it
  (``python -m emtk.web.serve --app pkg.module:make_app``);
* ``boot.js`` / ``index.html`` -- the loader: starts Pyodide, installs what the
  build named, resolves the GPU device and forwards DOM events. It draws
  nothing;
* :mod:`emtk.web.page` -- the Python half: DOM values in, :mod:`emtk.events`
  and :mod:`emtk.keys` values out, frames through :mod:`emtk.gpu.browser`.

The app contract is :mod:`emtk.app`'s, the same one :mod:`emtk.native` runs on
a desktop window.
"""
from __future__ import annotations

__all__: list[str] = []
