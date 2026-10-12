"""Extended grapheme clusters: the unit a user sees as one character.

A skin-toned thumbs-up is two code points (U+1F44D U+1F3FD), a family is five,
a flag two, a keycap three. Every layer that splits text -- measuring, drawing
a glyph per cell, moving the caret, deleting, selecting -- has to agree on what
"one character" is, or an emoji draws as two glyphs while the caret steps
through its middle. This module is that one answer.

The rules are the emoji-relevant part of UAX #29, kept as a small table rather
than a dependency:

* CR LF is one cluster;
* a code point is joined to the one before it when it is *Extend*: a combining
  mark (``Mn``, ``Me``, ``Mc``), a variation selector (U+FE00..FE0F,
  U+E0100..E01EF), a zero-width (non-)joiner, an emoji modifier (skin tone,
  U+1F3FB..1F3FF) or a tag character (U+E0020..E007F);
* a ZWJ (U+200D) also joins the pictographic code point that follows it;
* regional indicators pair up into flags;
* Hangul jamo are not sequenced (precomposed syllables are single code points).

:func:`display` turns a string into one code point per cluster, which is how
the monospace painters, whose unit is a glyph cell, stay cluster-aware without
each loop learning about clusters.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache

__all__ = ["clusters", "count", "display", "glyph_of", "is_ascii_simple",
           "next_boundary", "prev_boundary", "snap"]

_ZWJ = 0x200D
_EXTEND_FIXED = frozenset((0x200C, _ZWJ))
_PICTOGRAPHIC_BMP = frozenset((0xA9, 0xAE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D,
                               0x3297, 0x3299))


def _is_regional(code: int) -> bool:
    return 0x1F1E6 <= code <= 0x1F1FF


def _is_extend(char: str) -> bool:
    code = ord(char)
    if code < 0x300:
        return False
    if (0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF or 0x1F3FB <= code <= 0x1F3FF
            or 0xE0020 <= code <= 0xE007F or code in _EXTEND_FIXED):
        return True
    return unicodedata.category(char) in ("Mn", "Me", "Mc")


def _is_pictographic(code: int) -> bool:
    return (0x1F000 <= code <= 0x1FAFF or 0x2190 <= code <= 0x2BFF
            or code in _PICTOGRAPHIC_BMP or 0x2300 <= code <= 0x23FF)


def is_ascii_simple(string: str) -> bool:
    """Whether *string* has no cluster longer than one code point (cheap test)."""
    return string.isascii() and "\r\n" not in string


@lru_cache(maxsize=8192)
def _boundaries(string: str) -> tuple[int, ...]:
    """Every cluster boundary of *string*: ``0``, the cut points, ``len(string)``."""
    n = len(string)
    cuts = [0]
    i = 0
    while i < n:
        char = string[i]
        j = i + 1
        if char == "\r" and j < n and string[j] == "\n":
            j += 1
        elif _is_regional(ord(char)):
            if j < n and _is_regional(ord(string[j])):
                j += 1
        elif char not in "\r\n":
            while j < n:
                if _is_extend(string[j]):
                    zwj = ord(string[j]) == _ZWJ
                    j += 1
                    if zwj and j < n and _is_pictographic(ord(string[j])):
                        j += 1
                else:
                    break
        cuts.append(j)
        i = j
    return tuple(cuts)


def clusters(string: str) -> list[str]:
    """*string* split into extended grapheme clusters."""
    if is_ascii_simple(string):
        return list(string)
    cuts = _boundaries(string)
    return [string[a:b] for a, b in zip(cuts, cuts[1:])]


def count(string: str) -> int:
    """How many clusters *string* has."""
    if is_ascii_simple(string):
        return len(string)
    return len(_boundaries(string)) - 1


def prev_boundary(string: str, index: int) -> int:
    """The cluster boundary strictly before *index* (``0`` at the start)."""
    if index <= 0:
        return 0
    if is_ascii_simple(string):
        return min(index, len(string)) - 1
    index = min(index, len(string))
    return max(c for c in _boundaries(string) if c < index)


def next_boundary(string: str, index: int) -> int:
    """The cluster boundary strictly after *index* (``len(string)`` at the end)."""
    n = len(string)
    if index >= n:
        return n
    if is_ascii_simple(string):
        return max(index, 0) + 1
    index = max(index, 0)
    return min(c for c in _boundaries(string) if c > index)


def snap(string: str, index: int) -> int:
    """*index* moved forward to the nearest cluster boundary (itself if on one)."""
    index = max(0, min(int(index), len(string)))
    if is_ascii_simple(string):
        return index
    return min(c for c in _boundaries(string) if c >= index)


@lru_cache(maxsize=4096)
def glyph_of(cluster: str) -> str:
    """The single code point a one-glyph-per-cluster painter draws for *cluster*.

    A single code point is itself; a base with combining marks is its composed
    form when there is one (``e`` + U+0301 is ``\\u00e9``). A sequence the font
    cannot compose (a skin-toned, ZWJ, flag or keycap emoji) falls back to its
    **base** code point: one cell with the base emoji, never two cells.
    """
    if len(cluster) == 1:
        return cluster
    composed = unicodedata.normalize("NFC", cluster)
    if len(composed) == 1:
        return composed
    return cluster[0]


@lru_cache(maxsize=8192)
def _display(string: str) -> str:
    return "".join(glyph_of(c) for c in clusters(string))


def display(string: str) -> str:
    """*string* with every cluster reduced to the one code point drawn for it.

    ``len(display(s)) == count(s)``: the cell count of *s* on a monospace
    painter, and the string a glyph loop may iterate one cell per character.
    """
    if is_ascii_simple(string):
        return string
    return _display(string)
