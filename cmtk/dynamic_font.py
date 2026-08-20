"""Glyphs for the rest of Unicode, rasterised when they are first drawn.

Why the baked atlas is not enough
---------------------------------
The chrome's font is baked at build time into one image, which is what lets it
draw where there is no font engine. An atlas is a fixed-size image, so it holds
a *chosen* set: ASCII, the chrome's own symbols, and the accented Latin letters
people type. Everything else drew as nothing -- so "Zelldichte für Fläche" came
back as "Zelldichte f r Fl che", with no error anywhere, and Greek, Cyrillic,
CJK and every symbol were simply invisible.

Unicode has about 150,000 assigned codepoints. Baking them is not an option and
choosing a bigger subset only moves the edge. So the edge is removed instead:
anything not baked is rasterised **on first use** into a cache appended below
the baked rows, and the texture is updated. The first frame that shows a new
character pays for it; every frame after reads the cache.

What this does not do
---------------------
It does not make the chrome proportional. The layout is monospaced throughout --
every cell is one advance wide, and the panel's arithmetic depends on it -- so a
glyph that is *drawn* wider than a cell is scaled to fit rather than allowed to
overlap its neighbour. For a CJK character, whose natural width is two cells,
that means it renders narrow. Legible and honest; the alternative is a layout
that shifts under text nobody measured.

It also cannot invent a glyph the system has no font for. The rasteriser walks a
short chain of fonts and falls back to the atlas's own placeholder, which is
visible -- the failure this whole module exists to stop being an invisible one.
"""
from __future__ import annotations

import logging
import pathlib

import numpy as np

__all__ = ["FONT_CANDIDATES", "GlyphCache"]

logger = logging.getLogger(__name__)

#: Fonts tried in order, first that has the character wins. Menlo first because
#: it is what the atlas is baked from, so a character it covers looks identical
#: whether it came from the bake or from here. The rest are coverage: a
#: pan-Unicode face, then the symbol and CJK faces macOS ships.
#:
#: Paths rather than family names: this runs where there may be no font
#: database to query, and a missing file is skipped rather than fatal.
FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Apple Symbols.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/arialuni.ttf",
)


class GlyphCache:
    """Glyphs rasterised at runtime, in rows appended below the baked atlas.

    Parameters
    ----------
    cell : tuple of int
        ``(width, height)`` of one cell, in texels -- the baked atlas's own, so
        a runtime glyph is laid out exactly like a baked one.
    ascent : int
        Baseline offset inside the cell, again the atlas's.
    columns : int
        Cells per row. The baked atlas uses 16 and the cache matches it, so the
        two halves of the texture have the same stride.
    rows : int
        How many rows to reserve. 16 rows x 16 columns is 256 live glyphs,
        which is a page of CJK or several alphabets at once; beyond that the
        least recently used cell is taken.

    Attributes
    ----------
    dirty : list
        Cells rasterised since the last :meth:`take_dirty`, for the backend to
        upload. The cache never touches the GPU itself: it is drawn by three
        different backends and knows about none of them.
    """

    def __init__(self, cell, ascent: int, columns: int = 16, rows: int = 16) -> None:
        self.cell_w, self.cell_h = int(cell[0]), int(cell[1])
        self.ascent = int(ascent)
        self.columns = int(columns)
        self.rows = int(rows)
        self.image = np.zeros(
            (self.rows * self.cell_h, self.columns * self.cell_w, 4), dtype=np.uint8
        )
        #: char -> (x, y, w, h) in the cache's own coordinates.
        self._cells: dict[str, tuple[int, int, int, int]] = {}
        #: Insertion order, for the eviction that a full cache needs.
        self._order: list[str] = []
        self.dirty: list[tuple[int, int, int, int]] = []
        #: Bumped by every glyph stored. A *consumed* dirty list cannot serve
        #: two textures -- the second one gets nothing, which is how the
        #: offscreen grab drew blanks while the window drew glyphs. Each
        #: backend remembers the version it last uploaded instead, so any
        #: number of devices can be fed from one cache.
        self.version = 0
        #: path -> loaded PIL font, and path -> covered codepoints. Both are
        #: per file and neither changes while the program runs.
        self._loaded: dict = {}
        self._coverage_cache: dict = {}
        self._unavailable = False

    # ------------------------------------------------------------------ #
    @property
    def capacity(self) -> int:
        """How many glyphs fit before one has to be evicted."""
        return self.columns * self.rows

    def cell_of(self, char: str) -> tuple[int, int, int, int] | None:
        """The cache cell for *char*, rasterising it if this is its first use.

        Returns
        -------
        tuple or None
            ``(x, y, w, h)`` in the cache image, or ``None`` when no font on
            this machine has the character -- the caller then draws the atlas's
            placeholder, which is visible.
        """
        found = self._cells.get(char)
        if found is not None:
            return found
        if self._unavailable:
            return None
        rendered = self._rasterise(char)
        if rendered is None:
            return None
        return self._store(char, rendered)

    def take_dirty(self) -> list:
        """Return the cells written since the last call, and forget them.

        Only useful with a single consumer. Anything drawing to more than one
        texture should compare :attr:`version` instead -- see the note there.
        """
        pending, self.dirty = self.dirty, []
        return pending

    # ------------------------------------------------------------------ #
    def _font_for(self, char: str):
        """The first candidate font that actually **covers** *char*.

        Coverage is read from the font's own character map, not guessed from
        whether it drew something: a font asked for a character it lacks
        happily draws its "tofu" box, so "did it render?" answers yes for every
        font and the first candidate always wins. That is why CJK came out as
        empty boxes while Greek and Cyrillic worked -- Menlo has Greek, has no
        kanji, and was drawing the box.
        """
        code = ord(char)
        for path in FONT_CANDIDATES:
            covered = self._coverage(path)
            if covered is None or code not in covered:
                continue
            font = self._loaded.get(path)
            if font is None:
                font = self._load(path)
                if font is None:
                    continue
            return font
        return None

    def _coverage(self, path: str):
        """The codepoints a font file covers, or ``None`` if it cannot be read.

        Read once per file and cached: parsing a font's tables is milliseconds,
        and the answer does not change while the program runs.
        """
        if path in self._coverage_cache:
            return self._coverage_cache[path]
        covered = None
        if pathlib.Path(path).exists():
            try:
                from fontTools.ttLib import TTCollection, TTFont  # noqa: PLC0415

                if path.lower().endswith(".ttc"):
                    faces = TTCollection(path, lazy=True).fonts
                else:
                    faces = [TTFont(path, lazy=True)]
                covered = set()
                for face in faces:
                    covered |= set(face.getBestCmap())
            except Exception:  # noqa: BLE001 - an unreadable font is skipped
                covered = None
        self._coverage_cache[path] = covered
        return covered

    def _load(self, path: str):
        """Load one font at the cell's size, remembering it."""
        try:
            from PIL import ImageFont  # noqa: PLC0415
        except ImportError:
            self._unavailable = True
            logger.debug("no PIL: runtime glyphs are unavailable")
            return None
        # Sized from the cell's height rather than a point size: the baked
        # atlas is supersampled, and matching its *cell* is what makes a
        # runtime glyph the same size as a baked one.
        size = max(int(self.cell_h * 0.72), 6)
        try:
            font = ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 - try the next candidate
            return None
        self._loaded[path] = font
        return font

    def _rasterise(self, char: str):
        """Draw one character into a cell-sized RGBA array, or ``None``."""
        font = self._font_for(char)
        if font is None:
            return None
        try:
            from PIL import Image, ImageDraw  # noqa: PLC0415

            # Measured first: a glyph wider than the cell is scaled to fit
            # rather than allowed to run into its neighbour, because the
            # layout is monospaced and nothing downstream would notice.
            box = font.getbbox(char)
            if box is None:
                return None
            width = max(int(box[2] - box[0]), 1)
            scale = min(1.0, (self.cell_w - 2) / float(width)) if width else 1.0

            canvas = Image.new("L", (self.cell_w * 2, self.cell_h * 2), 0)
            draw = ImageDraw.Draw(canvas)
            draw.text((1, 0), char, fill=255, font=font, anchor="la")
            if scale < 1.0:
                canvas = canvas.resize(
                    (max(int(canvas.width * scale), 1), canvas.height),
                    Image.LANCZOS,
                )
            glyph = np.asarray(canvas, dtype=np.uint8)[: self.cell_h, : self.cell_w]
            if glyph.max() == 0:
                # The font has no glyph and drew its own blank. Reported as a
                # miss so the caller shows the placeholder: a blank cell here
                # would be the invisible failure again, one layer down.
                return None
        except Exception:  # noqa: BLE001 - a glyph is not worth a frame
            logger.debug("could not rasterise %r", char, exc_info=True)
            return None

        cell = np.zeros((self.cell_h, self.cell_w, 4), dtype=np.uint8)
        rows, columns = glyph.shape[:2]
        cell[:rows, :columns, 0] = 255
        cell[:rows, :columns, 1] = 255
        cell[:rows, :columns, 2] = 255
        cell[:rows, :columns, 3] = glyph
        return cell

    def _store(self, char: str, cell) -> tuple[int, int, int, int]:
        """Put a rasterised cell in the cache and return where it went."""
        if len(self._order) >= self.capacity:
            # Oldest out. A cache that refused new glyphs once full would make
            # the *next* language the user types invisible, which is the bug.
            evicted = self._order.pop(0)
            self._cells.pop(evicted, None)
        index = len(self._order)
        # Reuse the freed slot when one was evicted, so the cache stays packed.
        used = {c[1] // self.cell_h * self.columns + c[0] // self.cell_w
                for c in self._cells.values()}
        index = next(i for i in range(self.capacity) if i not in used)

        x = (index % self.columns) * self.cell_w
        y = (index // self.columns) * self.cell_h
        self.image[y:y + self.cell_h, x:x + self.cell_w] = cell
        rect = (x, y, self.cell_w, self.cell_h)
        self._cells[char] = rect
        self._order.append(char)
        self.dirty.append(rect)
        self.version += 1
        return rect
