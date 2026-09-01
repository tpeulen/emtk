Installation
============

cmtk has no runtime dependencies — not numpy, not a toolkit, not a compiler.
That is the point, and the ``dependencies`` list in ``pyproject.toml`` is empty
on purpose.

``pip install cmtk``

The ``docs`` extra pulls in Sphinx for building this documentation and the
``test`` extra pulls in pytest::

    pip install cmtk[docs,test]

That is all. There is nothing to compile, no native wheel to match to your
platform, and no C++ toolchain to discover. The package is pure Python.

Python version
--------------

3.10 or later. The code uses match statements, ``X | Y`` union syntax and
type hinting that earlier runtimes cannot parse.
