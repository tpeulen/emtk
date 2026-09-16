# -- emtk documentation build configuration ----------------------------------

import os
import sys

# The source tree, so autodoc can import emtk without installing.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# -- Project information -----------------------------------------------------

project = "emtk"
copyright = "2025, Thomas-Otavio Peulen"

import emtk  # noqa: E402
release = emtk.__version__
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
]

# Doctest setup: a RecordingPainter and im in scope for every example.
# Also provides names that pre-existing module docstring examples reference.
doctest_global_setup = """\
from emtk import im
from emtk.testing import RecordingPainter, FIXED_GLYPH_W, FIXED_LINE_H
from emtk.layout import Layout
from emtk.widgets.plot import begin_plot
from emtk.widgets.circle import begin_circle
# Variables that module-level docstring examples in plot.py / circle.py use.
painter = RecordingPainter()
xs = [0, 1, 2, 3]
ys = [0, 1, 0, -1]
x, y, w, h = 10.0, 10.0, 200.0, 60.0
"""

# Autodoc: show the signatures and docstrings, skip the dunder attrs.
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_member_order = "bysource"

# Intersphinx: Python stdlib only (zero runtime deps means no numpy etc.)
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Read the Docs theme ----------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
}

rst_prolog = """
.. |CONTROL_MODULES| replace:: ``emtk.CONTROL_MODULES``
"""
