"""EMTK Native Stylesheets.

Pure CSS stylesheets designed specifically for EMTK windows, docks, widgets, and plots.
"""
from __future__ import annotations

import pathlib
from typing import Any

_STYLES_DIR = pathlib.Path(__file__).parent


def available_stylesheets() -> list[str]:
    """Return names of all shipped EMTK native stylesheets (without .css extension)."""
    return sorted(p.stem for p in _STYLES_DIR.glob("*.css"))


def get_stylesheet_path(name: str) -> pathlib.Path | None:
    """Return the filesystem path to a shipped stylesheet, or None if not found."""
    stem = name.removesuffix(".css")
    target = _STYLES_DIR / f"{stem}.css"
    if target.is_file():
        return target
    return None


def get_stylesheet(name: str) -> str | None:
    """Read the CSS text of a shipped stylesheet, or None if not found."""
    path = get_stylesheet_path(name)
    if path is not None:
        return path.read_text(encoding="utf-8")
    return None
