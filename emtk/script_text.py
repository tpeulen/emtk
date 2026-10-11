"""Text with real sub- and superscripts, drawn on any painter.

Labels of scientific quantities carry scripts -- ``w_{r} [nm]``, ``τ_{D}``,
``x^{2}`` -- and :func:`emtk.mathtext.convert_script_markup` can only turn a
script into a Unicode glyph when one exists: there is a subscript ``r`` but no
subscript ``z``, so ``w_{z}`` stayed as typed. Here a script is drawn as what it
is, a smaller run set below or above the line, so every letter works.

The markup is the one :mod:`emtk.mathtext` reads: ``_{…}`` for a subscript,
``^{…}`` for a superscript, braces required (a bare ``_`` in a file name is
text), ``\\_{`` / ``\\^{`` for a literal. A painter that cannot scale its font
(no ``set_font_scale``) gets the Unicode conversion instead.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["SCRIPT_SCALE", "has_scripts", "script_runs", "script_width", "draw_script_text",
           "plain_script_text"]

#: Size of a script run relative to the base text.
SCRIPT_SCALE = 0.72
#: How far a subscript drops and a superscript rises, as a fraction of the line height.
_SUB_DROP, _SUP_RISE = 0.22, 0.32

_SCRIPT = re.compile(r"(\\?)([_^])\{([^{}]*)\}")


def has_scripts(text: str) -> bool:
    """Whether *text* holds any ``_{…}`` / ``^{…}`` run."""
    return bool(text) and any(not m.group(1) for m in _SCRIPT.finditer(text))


def script_runs(text: str) -> list[tuple[str, int]]:
    """Split *text* into ``(run, level)``: ``0`` base line, ``-1`` subscript, ``1`` superscript.

    Escaped markup (``\\_{x}``) is returned as literal base text without its backslash.
    """
    runs: list[tuple[str, int]] = []
    at = 0

    def push(run: str, level: int) -> None:
        if not run:
            return
        if runs and runs[-1][1] == level:
            runs[-1] = (runs[-1][0] + run, level)
        else:
            runs.append((run, level))

    for match in _SCRIPT.finditer(text):
        push(text[at:match.start()], 0)
        escape, kind, content = match.groups()
        if escape:
            push(f"{kind}{{{content}}}", 0)
        else:
            push(content, -1 if kind == "_" else 1)
        at = match.end()
    push(text[at:], 0)
    return runs


def plain_script_text(text: str) -> str:
    """*text* with the markup removed: what a reader of the label would say."""
    return "".join(run for run, _level in script_runs(text))


def _scale(p: Any, scale: float) -> bool:
    op = getattr(p, "set_font_scale", None)
    if not callable(op):
        return False
    op(scale)
    return True


def script_width(p: Any, text: str) -> float:
    """Advance width of *text* drawn by :func:`draw_script_text` on *p*."""
    if not has_scripts(text):
        return float(p.text_width(text))
    if not callable(getattr(p, "set_font_scale", None)):
        from .mathtext import convert_script_markup

        return float(p.text_width(convert_script_markup(text)))
    width = 0.0
    for run, level in script_runs(text):
        if level:
            _scale(p, SCRIPT_SCALE)
            try:
                width += float(p.text_width(run))
            finally:
                _scale(p, 1.0)
        else:
            width += float(p.text_width(run))
    return width


def draw_script_text(p: Any, x: float, y: float, w: float, h: float, align: int,
                     text: str, colour: Any) -> None:
    """Draw *text* in the box like ``p.text``, its ``_{…}`` / ``^{…}`` runs as scripts.

    *align* is the painter's flags; horizontal alignment is honoured for the
    whole label, the runs are laid out left to right from there.
    """
    from .painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER

    if not has_scripts(text):
        p.text(x, y, w, h, align, text, colour)
        return
    if not callable(getattr(p, "set_font_scale", None)):
        from .mathtext import convert_script_markup

        p.text(x, y, w, h, align, convert_script_markup(text), colour)
        return
    total = script_width(p, text)
    if align & ALIGN_RIGHT:
        at = x + w - total
    elif align & ALIGN_HCENTER:
        at = x + (w - total) / 2.0
    else:
        at = x
    line = float(p.line_height())
    vertical = align & ~(ALIGN_RIGHT | ALIGN_HCENTER | ALIGN_LEFT)
    for run, level in script_runs(text):
        if level == 0:
            run_w = float(p.text_width(run))
            p.text(at, y, run_w + 1.0, h, ALIGN_LEFT | (vertical or ALIGN_VCENTER), run, colour)
        else:
            _scale(p, SCRIPT_SCALE)
            try:
                run_w = float(p.text_width(run))
                shift = line * (_SUB_DROP if level < 0 else -_SUP_RISE)
                p.text(at, y + shift, run_w + 1.0, h, ALIGN_LEFT | (vertical or ALIGN_VCENTER),
                       run, colour)
            finally:
                _scale(p, 1.0)
        at += run_w
