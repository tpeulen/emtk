"""Read the baked glyph atlas.

The atlas is produced by ``tools/bake_chrome_atlas.py`` and committed
beside this module. Baking needs a font engine; reading needs a JSON file and a
PNG, which is the whole point -- text renders identically wherever the chrome
runs, and layout no longer depends on whether a toolkit is present to measure
it.

Loading is lazy and cached: the panel repaints every frame and the atlas is one
image.
"""
from __future__ import annotations

import json
import pathlib

__all__ = ["Atlas", "load_atlas", "ATLAS_DIR", "MISSING_GLYPH"]

#: Drawn in place of a character the atlas has no glyph for. Matches the
#: baker's own constant; a placeholder that is itself missing would be the bug
#: twice over, so it is in the charset by construction.
MISSING_GLYPH = "\u00a4"

#: Where the baked atlas lives.
ATLAS_DIR = pathlib.Path(__file__).resolve().parent / "atlas"

_CACHE: dict[str, "Atlas"] = {}


class Atlas:
    """A baked font: where each glyph sits, and how wide it is.

    Parameters
    ----------
    meta : dict
        The contents of ``chrome.json``.

    Attributes
    ----------
    scale : int
        Supersampling factor the atlas was baked at. Every texel measurement
        below is at that scale; :meth:`advance` divides it out so callers work
        in the logical pixels the layout uses.
    """

    def __init__(self, meta: dict) -> None:
        self._meta = meta
        self.scale = int(meta["scale"])
        self.pad = int(meta["pad"])
        self.cell = tuple(meta["cell"])
        #: Built on first miss; see `cache`.
        self._cache = None
        self._cache_failed = False
        self.size = tuple(meta["size"])
        self.solid = tuple(meta["solid"])
        self.ascent = int(meta["ascent"])
        self._glyphs = meta["glyphs"]
        # The 1x advance, when the baker recorded one. Font metrics do not
        # scale linearly, so the baked 4x advance divided by four is 8.5 where
        # Qt's 10 pt is 8 -- a 6% stretch across every string in the panel, and
        # a panel that disagrees with the toolkit it shares a window with.
        self._advance = float(
            meta.get("advance_1x") or float(meta["advance"]) / self.scale
        )

    @property
    def render_scale(self) -> float:
        """Logical pixels per baked texel, for the glyph *quad*.

        Not simply ``1 / scale``. The atlas is baked at four times the point
        size and its metrics do not scale linearly -- Menlo advances 34 texels
        at 40 pt where it advances 8 px at 10 pt, so a quad sized ``cell /
        scale`` draws ink 6 % wider than the toolkit does beside it. This is the
        ratio that makes the drawn glyph the size the layout budgeted for it.
        """
        baked = float(self._meta["advance"]) / self.scale
        return (self._advance / baked) / self.scale if baked else 1.0 / self.scale

    @property
    def line_height(self) -> float:
        """Height of one line, in logical pixels."""
        meta = self._meta
        return float(meta.get("line_height_1x") or meta["line_height"] / self.scale)

    def advance(self, string: str = "") -> float:
        """Advance width of *string*, in logical pixels.

        Parameters
        ----------
        string : str
            The text to measure. Empty gives one character's advance.

        Returns
        -------
        float

        Notes
        -----
        Monospaced, so this is a multiplication rather than a sum over the
        glyph table. That is a property of the baked font, not an assumption
        about text: the baker asserts one advance across both faces, because a
        proportional font would make every ``char_w``-based layout in the panel
        wrong in a way no single number could express.
        """
        return self._advance * (len(string) if string else 1)

    def cell_of(self, char: str, bold: bool = False) -> tuple | None:
        """Return ``(x, y, w, h)`` of *char*'s cell, in texels.

        Parameters
        ----------
        char : str
            A single character.
        bold : bool
            Which face to look in.

        Returns
        -------
        tuple or None
            The cell of *char*, or of :data:`MISSING_GLYPH` when the character
            was not baked -- a **visible** placeholder rather than nothing.

            Drawing nothing is what this used to do, and it is the worst of the
            three options: an accented letter typed into the command line
            simply vanished, with no error anywhere, and "Zelldichte für
            Fläche" came back as "Zelldichte f r Fl che". A placeholder is
            wrong on screen, which is how anyone finds out.

            ``None`` only when the placeholder itself is missing, which means
            the atlas is not the one this code was written for.
        """
        table = self._glyphs["bold" if bold else "regular"]
        entry = table.get(char)
        if entry is not None:
            return entry[0], entry[1], entry[2], entry[3]

        # Not baked: rasterise it now, into the cache that lives below the
        # baked rows. This is what makes the chrome *full* Unicode rather than
        # the alphabet somebody chose at build time -- Greek, Cyrillic, CJK and
        # every symbol are glyphs the machine already has, and the only reason
        # they were invisible is that nobody asked for them.
        rect = self._dynamic_cell(char)
        if rect is not None:
            return rect

        entry = table.get(MISSING_GLYPH)
        if entry is None:
            return None
        return entry[0], entry[1], entry[2], entry[3]

    @property
    def cache(self):
        """The runtime glyph cache, built on first use.

        ``None`` when there is no rasteriser -- the chrome then draws the
        placeholder, which is visible, rather than nothing.
        """
        if self._cache is None and not self._cache_failed:
            try:
                from .dynamic_font import GlyphCache  # noqa: PLC0415

                self._cache = GlyphCache(self.cell, self.ascent)
            except Exception:  # noqa: BLE001 - a cache is not worth a frame
                self._cache_failed = True
        return self._cache

    def _dynamic_cell(self, char: str):
        """A rasterised cell for *char*, in **atlas** coordinates, or ``None``.

        The cache's rows sit under the baked image, so its own y is offset by
        the baked height -- one texture, two halves, and the shader neither
        knows nor cares which half a glyph came from.
        """
        cache = self.cache
        if cache is None:
            return None
        rect = cache.cell_of(char)
        if rect is None:
            return None
        return rect[0], rect[1] + self.baked_height, rect[2], rect[3]

    @property
    def baked_height(self) -> int:
        """Height of the baked image, which is where the cache starts."""
        return int(self._meta["size"][1])

    @property
    def texture_height(self) -> int:
        """Height of the texture to allocate: the baked rows plus the cache."""
        cache = self.cache
        return self.baked_height + (cache.image.shape[0] if cache is not None else 0)

    def covers(self, char: str) -> bool:
        """Whether *char* has a glyph of its own.

        For a caller that would rather substitute something readable than show
        a placeholder -- a transliteration, or a shorter label.
        """
        return char in self._glyphs["regular"]

    @property
    def image_path(self) -> pathlib.Path:
        """Path to the atlas PNG."""
        return ATLAS_DIR / "chrome.png"


def load_atlas(name: str = "chrome") -> Atlas:
    """Load a baked atlas by name, cached.

    Parameters
    ----------
    name : str
        Base name of the ``.json`` / ``.png`` pair.

    Returns
    -------
    Atlas

    Raises
    ------
    FileNotFoundError
        If the atlas has not been baked. Raised rather than falling back to a
        measured font: a silent fallback would work on the desktop and fail
        only where there is no font engine, which is the one place nobody is
        watching.
    """
    cached = _CACHE.get(name)
    if cached is not None:
        return cached
    path = ATLAS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no baked glyph atlas at {path}; run "
            "`python tools/bake_chrome_atlas.py` in a checkout of cmtk"
        )
    atlas = Atlas(json.loads(path.read_text(encoding="utf-8")))
    _CACHE[name] = atlas
    return atlas
