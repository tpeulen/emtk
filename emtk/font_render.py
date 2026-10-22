"""Optional real font selection, shared by native and CPU painters.

The packaged monospace atlas stays the default. Explicit system faces use
Pillow's existing FreeType support, without Qt or a platform font server.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from .font import DEFAULT_FONT_PT, PX_PER_PT
from .grapheme import display

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FontSpec:
    family: str = "monospace"
    size: float = DEFAULT_FONT_PT
    bold: bool = False
    italic: bool = False
    #: Families tried, in order, for a character *family* lacks -- before the
    #: system coverage faces (:data:`emtk.dynamic_font.FONT_CANDIDATES`). Filled
    #: by :func:`font_spec` from a comma-separated family chain and the
    #: configured :attr:`emtk.fonts.FontConfig.fallbacks`.
    fallback: tuple = ()


@dataclass(frozen=True)
class Face:
    path: str
    index: int
    bold: bool
    italic: bool
    monospaced: bool
    style: str


_FACE_CACHE_VERSION = 1


def _face_cache_path() -> Path:
    """Where the scanned face table persists between processes.

    ``EMTK_CACHE_DIR`` overrides; otherwise the platform user cache directory.
    """
    override = os.environ.get("EMTK_CACHE_DIR")
    if override:
        return Path(override) / "font_faces.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        base = Path(xdg)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".cache"
    return base / "emtk" / "font_faces.json"


def _scan_file(path: Path, image_font) -> list[list]:
    """Open every face in one font file: ``[index, family, style, bold, italic, mono]`` rows."""
    rows: list[list] = []
    for index in range(64 if path.suffix.lower() == ".ttc" else 1):
        try:
            font = image_font.truetype(str(path), 16, index=index)
            family, style = font.getname()
            # Names alone are insufficient: only faces FreeType actually
            # opens and measures are offered to the caller.
            advances = [font.getlength(char) for char in "ilMW@08."]
            mono = max(advances) - min(advances) < 0.1 and bytes(
                font.getmask("i")
            ) != bytes(font.getmask("M"))
            style = style.casefold()
            rows.append(
                [
                    index,
                    family,
                    style,
                    "bold" in style or "black" in style,
                    "italic" in style or "oblique" in style,
                    bool(mono),
                ]
            )
        except (OSError, ValueError):
            break
    return rows


def _load_face_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != _FACE_CACHE_VERSION:
        return {}
    files = data.get("files")
    return files if isinstance(files, dict) else {}


def _store_face_cache(path: Path, files: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps({"version": _FACE_CACHE_VERSION, "files": files}), encoding="utf-8"
        )
        os.replace(tmp, path)
    except OSError:
        pass  # A read-only cache directory only costs the rescan next time.


@lru_cache(maxsize=1)
def _faces() -> dict[str, tuple[Face, ...]]:
    try:
        from PIL import ImageFont
    except ImportError:
        return {}
    directories = [
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    ]
    paths = sorted(
        {
            p
            for directory in directories
            if directory.exists()
            for p in directory.rglob("*")
            if p.suffix.lower() in {".ttf", ".otf", ".ttc"}
        }
    )
    # Opening every installed face with FreeType costs ~250 ms; walking and
    # stat-ing the files costs ~10 ms. The scan result is persisted per file
    # (path, mtime, size), so only new or changed font files are reopened.
    cache_path = _face_cache_path()
    cached = _load_face_cache(cache_path)
    files: dict[str, dict] = {}
    result: dict[str, list[Face]] = {}
    changed = False
    for path in paths[:4096]:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature = [stat.st_mtime_ns, stat.st_size]
        entry = cached.get(str(path))
        if not (isinstance(entry, dict) and entry.get("sig") == signature):
            entry = {"sig": signature, "faces": _scan_file(path, ImageFont)}
            changed = True
        files[str(path)] = entry
        for index, family, style, bold, italic, mono in entry["faces"]:
            result.setdefault(family, []).append(
                Face(str(path), index, bold, italic, mono, style)
            )
    if changed or len(files) != len(cached):  # a font added, changed or removed
        _store_face_cache(cache_path, files)
    preferred = {
        "regular",
        "normal",
        "roman",
        "book",
        "bold",
        "italic",
        "bold italic",
        "bolditalic",
    }
    return {
        name: tuple(sorted(faces, key=lambda face: face.style not in preferred))
        for name, faces in result.items()
    }


def available_fonts(monospaced: bool = False) -> tuple[str, ...]:
    """Actual loadable family names, plus the packaged ``monospace`` default.

    ``monospaced=True`` limits choices to faces with fixed Latin advances,
    useful for editors whose column geometry assumes a fixed-width font.
    """
    return (
        "monospace",
        *sorted(
            (
                name
                for name, faces in _faces().items()
                if not name.startswith(".")
                and any(not f.bold and not f.italic for f in faces)
                and (not monospaced or _face(FontSpec(name)).monospaced)
            ),
            key=str.casefold,
        ),
    )


@lru_cache(maxsize=256)
def _face(spec: FontSpec) -> Face:
    # Resolved once per spec: the lookup casefolds every installed family, which
    # text measurement was paying on every call (hundreds of times per frame).
    family = next(
        (name for name in _faces() if name.casefold() == spec.family.casefold()), None
    )
    if family is None:
        # A font request is a hint, not a contract. A host with one baked face
        # (the web page: Pyodide ships no system fonts) must not lose a window
        # over it -- the fit pages' bold ``sans-serif`` captions killed the
        # What-if window with ``ValueError: Font family 'sans-serif' is not
        # available``, caught by the dock as "failed to draw". Draw in the
        # default family and say so.
        family = _fallback_family()
        logger.warning(
            "font family %r is not available; drawing %r in %r",
            spec.family, spec, family,
        )
    faces = _faces().get(family) or ()
    found = next(
        (
            face
            for face in faces
            if face.bold == spec.bold and face.italic == spec.italic
        ),
        None,
    )
    if found is None:
        # Same tolerance for the cut: the family exists but not in this
        # bold/italic combination -- its regular face beats a dead window.
        found = next(
            (
                face
                for face in faces
                if not face.bold and not face.italic
            ),
            None,
        )
        if found is not None:
            logger.warning(
                "font family %r has no %s%s face; drawing the regular face",
                family, "bold " if spec.bold else "", "italic" if spec.italic else "",
            )
    if found is None:
        # Nothing is installed at all (the web page: ``_faces()`` is empty and
        # the baked atlas is the only face there is) -- the baked face answers,
        # keeping the requested cut as bookkeeping for the painter.
        logger.warning(
            "no installed font faces; drawing %r with the baked atlas face", spec
        )
        found = Face(path=":baked-atlas:", index=0, bold=spec.bold,
                     italic=False, monospaced=True, style="baked")
    return found


def _fallback_family() -> str:
    """The family an unavailable name draws in: the spec default if it exists,
    else the first real family with a regular face, else the baked default."""
    default = FontSpec().family
    names = _faces()
    if not names or any(name.casefold() == default.casefold() for name in names):
        return default
    return next(
        (
            name
            for name, faces in sorted(names.items(), key=lambda kv: str.casefold(kv[0]))
            if not name.startswith(".") and any(not f.bold and not f.italic for f in faces)
        ),
        default,
    )


def font_spec(value=None, size: float | None = 0.0) -> FontSpec:
    """Validate string/dict/None font input; sizes are points, as in QtPainter."""
    if value is None:
        data = {}
    elif isinstance(value, str):
        data = {"family": value}
    elif isinstance(value, dict):
        unknown = set(value) - {"family", "size", "bold", "italic"}
        if unknown:
            raise ValueError(f"Unsupported font attributes: {sorted(unknown)}")
        data = value
    else:
        raise TypeError("Font must be a family name, font dictionary, or None")
    effective_size = size if size is not None and size != 0 else data.get("size")
    if effective_size is None or effective_size == 0:
        effective_size = DEFAULT_FONT_PT
    effective_size = float(effective_size)
    if not math.isfinite(effective_size) or not 0 < effective_size <= 256:
        raise ValueError("Font size must be finite and between 0 and 256 points")
    explicit = "family" in data
    family = data.get("family") if explicit else _default_family()
    if not isinstance(family, str) or not family.strip():
        raise ValueError("Font family must be a nonempty name")
    for attribute in ("bold", "italic"):
        if attribute in data and not isinstance(data[attribute], bool):
            raise ValueError(f"Font {attribute} must be a boolean")
    chain = [name for name in (_resolve_family(part) for part in family.split(",")
                               if part.strip()) if name]
    if not chain:
        # Nothing in the chain is installed: name the first entry, as a
        # single unknown family always did.
        chain = [family.split(",")[0].strip()]
    primary = chain[0]
    if not explicit and primary.casefold() != "monospace" and primary not in _faces():
        primary = "monospace"  # a configured interface face that is gone draws the bake
    from . import fonts  # noqa: PLC0415

    fallback = tuple(
        dict.fromkeys(
            name
            for name in (*chain[1:], *(_resolve_family(f) for f in fonts._config.fallbacks))
            if name and name.casefold() != "monospace" and name != primary
        )
    )
    spec = FontSpec(
        primary, effective_size, data.get("bold", False), data.get("italic", False), fallback
    )
    if spec.family.casefold() == "monospace":
        if spec.italic:
            # The baked face has no italic cut (it bakes regular and bold).
            # Raising here killed windows that pushed italic on the web page,
            # where the baked face is the only one: draw it upright and say so,
            # the same tolerance ``_face`` applies to a missing family.
            logger.warning(
                "the baked monospace face has no italic style; drawing upright"
            )
            spec = FontSpec(spec.family, spec.size, spec.bold, False, spec.fallback)
        return FontSpec("monospace", spec.size, spec.bold, False)
    _face(spec)
    return spec


#: Generic family names and the installed families they stand for, in preference order.
GENERIC_FAMILIES: dict[str, tuple[str, ...]] = {
    "sans-serif": ("Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans"),
    "sans": ("Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans"),
    # Running text beside the Menlo/DejaVu Sans Mono chrome (type_scale.PROSE_FAMILY).
    "prose": (
        "Verdana",
        "DejaVu Sans",
        "Bitstream Vera Sans",
        "Tahoma",
        "Lucida Grande",
        "Arial",
        "Helvetica",
        "Liberation Sans",
        "Noto Sans",
    ),
    "serif": ("Times New Roman", "Times", "DejaVu Serif", "Liberation Serif", "Noto Serif"),
}


@lru_cache(maxsize=512)
def _resolve_family(name: str) -> str | None:
    """*name* as an installed family (generics expanded), ``monospace``, or ``None`` if absent."""
    name = name.strip()
    if not name:
        return None
    key = name.casefold()
    if key == "monospace":
        return "monospace"
    faces = _faces()
    if key in GENERIC_FAMILIES:
        return next((f for f in GENERIC_FAMILIES[key] if f in faces), None)
    return next((f for f in faces if f.casefold() == key), None)


def _default_family() -> str:
    """The family a font without one is drawn in: the configured interface face."""
    from . import fonts  # noqa: PLC0415

    return fonts._config.ui.family or "monospace"


def family_available(family: object) -> bool:
    """Whether *family* (a name, generic, or comma chain) has an installed entry.

    The non-raising probe the settings layer needs: ``_face`` now *draws* an
    unavailable family in the default one (a window must not fail to draw over
    a font hint), so a ``try: font_spec(...)`` around a configured family no
    longer detects a missing face. This says it directly, with the same chain
    semantics ``font_spec`` applies.
    """
    if not isinstance(family, str) or not family.strip():
        return False
    return any(
        _resolve_family(part) is not None
        for part in family.split(",")
        if part.strip()
    )


class _BakedAtlasFace:
    """PIL-compatible face from the committed atlas: metrics *and* pixels.

    The face :func:`_face` hands out when nothing is installed (the web page:
    Pyodide ships no font files). The atlas is baked at ``scale`` texels per
    logical pixel, so every metric it records is divided out here; the glyph
    cells themselves carry ``pad`` texels of margin around a line box whose
    baseline sits ``pad + ascent`` texels from the cell's top.

    A face is a full PIL stand-in or it is a trap: measurement alone made a
    theme switch blank the page twice -- first ``getbbox`` rejecting the
    ``anchor`` keyword, then ``getmask`` missing so the glyph rasteriser could
    not draw a dock title at all. :meth:`getbbox` honours anchors,
    :meth:`getmask` renders coverage, and both answer in the same pixels.
    """

    __slots__ = ("_atlas", "_scale", "_ascent", "_descent", "_image")

    def __init__(self, pixels: float):
        from .font import load_atlas  # noqa: PLC0415

        self._atlas = load_atlas()
        self._scale = pixels / (self._atlas.font_pt * PX_PER_PT)
        self._image = None
        # The atlas records texels; a logical pixel is ``scale`` texels (the
        # advance's own 1x value, which does not divide evenly out of the
        # bake, already comes that way through ``advance()``).
        per_texel = self._scale / float(self._atlas.scale)
        # ``ascent`` and the JSON ``line_height`` are texels; the Atlas
        # property of that name is the 1x-logical line height, which is a
        # different unit and would not hold the cells the mask blits.
        self._ascent = int(round(self._atlas.ascent * per_texel))
        height = int(round(float(self._atlas._meta["line_height"]) * per_texel))
        self._descent = max(1, height - self._ascent)

    def getlength(self, text: str) -> float:
        return self._atlas.advance(text) * self._scale

    def getmetrics(self) -> tuple[int, int]:
        return self._ascent, self._descent

    def _texel(self) -> float:
        """Face pixels per atlas texel, the bake's own advance ratio kept."""
        return self._scale * self._atlas.render_scale

    def _atlas_image(self):
        """The atlas PNG, ``RGBA``, loaded once."""
        if self._image is None:
            from PIL import Image  # noqa: PLC0415

            self._image = Image.open(self._atlas.image_path).convert("RGBA")
        return self._image

    def getmask(self, text: str, mode: str = "", *args, **kwargs):
        """PIL's mask for *text*: each glyph's coverage, white on black.

        The box is ``(width, ascent + descent)`` at the origin -- the ``la``
        box :meth:`getbbox` reports -- so PIL's own anchor arithmetic places
        it. Returns ``None`` for empty text, as PIL's faces do.
        """
        from PIL import Image  # noqa: PLC0415

        text = str(text or "")
        if not text:
            return None
        from .grapheme import clusters  # noqa: PLC0415

        width = max(1, int(round(self.getlength(text))))
        image = Image.new("L", (width, self._ascent + self._descent))
        atlas = self._atlas_image()
        pad = float(self._atlas.pad)
        baseline = pad + float(self._atlas.ascent)  # texels, from the cell's top
        k = self._texel()
        pen = 0.0
        for char in clusters(text):
            cell = self._atlas.cell_of(char)
            if cell is None:
                pen += self._atlas.advance() * self._scale
                continue
            cx, cy, cw, ch = (int(v) for v in cell[:4])
            coverage = atlas.crop((cx, cy, cx + cw, cy + ch)).getchannel("A")
            box = coverage.getbbox()
            if box is None:  # a space: advance only
                pen += self._atlas.advance() * self._scale
                continue
            ink = coverage.crop(box)
            target = (max(1, round(ink.width * k)), max(1, round(ink.height * k)))
            if target != ink.size:
                ink = ink.resize(target, Image.Resampling.BILINEAR)
            # The pen origin inside a cell is the padding's left edge; the
            # baseline is ``pad + ascent`` texels down from the cell's top.
            x = int(round(pen + (box[0] - pad) * k))
            y = int(round(self._ascent - (baseline - box[1]) * k))
            image.paste(ink, (x, y), ink)
            pen += self._atlas.advance() * self._scale
        return image.im

    def getbbox(self, text: str, mode: str = "", *args, **kwargs) -> tuple[int, int, int, int]:
        """PIL's ``(x0, y0, x1, y1)`` for *text*, honouring ``anchor``.

        The real ``FreeTypeFont.getbbox`` takes ``anchor`` (and friends), and
        :func:`_glyph` measures single characters with ``anchor="ls"`` -- a
        face that rejects the keyword kills the whole frame, and with it
        the frame-error panel too, which is how a theme switch once left the
        page a flat colour.
        """
        width = int(self.getlength(text))
        height = self._ascent + self._descent
        anchor = str(kwargs.get("anchor") or "la")
        horizontal = anchor[0] if len(anchor) > 0 else "l"
        vertical = anchor[1] if len(anchor) > 1 else "a"
        x0 = {"l": 0, "s": 0, "m": -width // 2, "r": -width}.get(horizontal, 0)
        y0 = {
            "a": 0, "t": 0,
            "m": -(self._ascent + height - self._ascent) // 2,
            "s": -self._ascent,
            "b": -(height), "d": -self._ascent,
        }.get(vertical, -self._ascent)
        return x0, y0, x0 + width, y0 + height


@lru_cache(maxsize=128)
def _loaded(face: Face, pixels: float):
    if face.path == ":baked-atlas:":
        return _BakedAtlasFace(pixels)

    from PIL import ImageFont

    return ImageFont.truetype(face.path, pixels, index=face.index)


def _font(spec: FontSpec, scale: float, bold: bool = False):
    actual = replace(spec, bold=spec.bold or bold)
    return _loaded(_face(actual), max(1, round(actual.size * PX_PER_PT * scale)))


#: Pixel size text is *laid out* at, whatever size it is drawn at.
#:
#: Measuring at the drawn size is what made proportional text look squeezed:
#: FreeType hints a face to whole pixels at small sizes, so an 11 px layout
#: is not the 22 px layout halved, and the glyphs -- rasterised at 11 px and
#: stretched onto a 2x display -- were both soft and set on tighter advances
#: than the face has. At this size hinting is lost in the noise, so widths
#: and pen positions are exactly linear in the size: what a layout measures
#: at ratio 1 is what is drawn at ratio 2, and at every font scale.
LAYOUT_PX = 512


def _px(spec: FontSpec, scale: float) -> float:
    """Logical pixel size of *spec* at *scale*: an em, unrounded."""
    return spec.size * PX_PER_PT * scale


@lru_cache(maxsize=256)
def _layout_metrics(spec: FontSpec) -> tuple[float, float]:
    """``(ascent, descent)`` of *spec* at :data:`LAYOUT_PX`."""
    ascent, descent = _loaded(_face(spec), LAYOUT_PX).getmetrics()
    return float(ascent), float(descent)


@lru_cache(maxsize=64)
def _cmap(path: str, index: int):
    """Codepoints a face covers, or ``None`` when its tables cannot be read."""
    try:
        from fontTools.ttLib import TTFont  # noqa: PLC0415

        return frozenset(TTFont(path, fontNumber=index, lazy=True).getBestCmap())
    except Exception:  # noqa: BLE001 - unknown coverage is "assume covered"
        return None


@lru_cache(maxsize=256)
def _family_face(family: str, bold: bool, italic: bool) -> Face | None:
    """The face of an installed *family* nearest the requested style, or ``None``."""
    styles = _faces().get(family)
    if not styles:
        return None
    for want in ((bold, italic), (False, italic), (bold, False), (False, False)):
        for face in styles:
            if (face.bold, face.italic) == want:
                return face
    return styles[0]


@lru_cache(maxsize=4096)
def _face_for(face: Face, char: str, chain: tuple = ()) -> Face:
    """*face* when it has *char*, else the first fallback face that has it.

    A proportional face (Arial, Helvetica) lacks much of what documentation
    writes -- subscript digits (R\u2080), arrows, dingbats -- and drawing its
    ``.notdef`` box is the bug the baked chrome solved long ago with its own
    fallback list. The same list serves here, so a character looks the same
    in prose as in a button. *chain* -- the spec's own fallback families
    (:attr:`FontSpec.fallback`) -- is tried first, so a role's fallbacks win.
    """
    covered = _cmap(face.path, face.index)
    if covered is None or ord(char) in covered or char.isspace():
        return face
    for family in chain:
        other_face = _family_face(family, face.bold, face.italic)
        if other_face is None:
            continue
        other = _cmap(other_face.path, other_face.index)
        if other is not None and ord(char) in other:
            return other_face
    from .dynamic_font import FONT_CANDIDATES  # noqa: PLC0415

    for path in FONT_CANDIDATES:
        if "emoji" in path.lower() or not os.path.exists(path):
            continue  # colour strikes cannot be rasterised as outlines
        other = _cmap(path, 0)
        if other is not None and ord(char) in other:
            return Face(path, 0, face.bold, face.italic, False, "fallback")
    return face


@lru_cache(maxsize=4096)
def _runs(spec: FontSpec, string: str) -> tuple[tuple[Face, int, str], ...]:
    """*string* split into ``(face, start, text)`` runs of one face each."""
    primary = _face(spec)
    runs: list[list] = []
    for index, char in enumerate(string):
        face = _face_for(primary, char, spec.fallback)
        if runs and runs[-1][0] == face:
            runs[-1][2] += char
        else:
            runs.append([face, index, char])
    return tuple((face, start, text) for face, start, text in runs)


@lru_cache(maxsize=16384)
def _layout_width(spec: FontSpec, string: str) -> float:
    return float(sum(_loaded(face, LAYOUT_PX).getlength(text)
                     for face, _, text in _runs(spec, string)))


@lru_cache(maxsize=16384)
def text_width(spec: FontSpec, string: str, scale: float) -> float:
    """Advance width of *string*, in the caller's pixels; linear in *scale*."""
    string = display(string)
    return _layout_width(spec, string) * _px(spec, scale) / LAYOUT_PX


def line_height(spec: FontSpec, scale: float) -> float:
    """Ascent plus descent, in the caller's pixels; linear in *scale*."""
    ascent, descent = _layout_metrics(spec)
    return (ascent + descent) * _px(spec, scale) / LAYOUT_PX


#: Pen positions a glyph is rasterised at, per device pixel. A glyph drawn
#: at a whole pixel when its pen is at x.4 sits 0.4 px off; per glyph those
#: errors do not cancel, and a line of 10 px prose read as words glued
#: together and spaced unevenly ("theyare"). Four phases keep every pen
#: within 1/8 px of where the layout put it.
SUBPIXEL_STEPS = 4

#: Raster sizes are quantised to this fraction of a pixel (bounds the cache).
RASTER_QUANTUM = 8


@lru_cache(maxsize=4096)
def _glyph(face: Face, pixels: float, char: str, phase: float = 0.0,
           filter: str = "linear", antialias: bool = True):
    """*char* of *face* rasterised at *pixels* per em with its pen *phase* px right of a texel edge.

    Returns ``(texture, left, top)``: the texture's top-left corner relative to the
    whole-pixel pen position and the baseline, in texels. The size is the exact
    (fractional) em, not a whole pixel: a 10.67 px em rasterised at 11 px is 3 %
    wider than the advances it is set on, which closes every gap between words.

    *filter* ``"nearest"`` is for a glyph drawn one texel per device pixel: a
    linear image is sampled half a texel inside its edges (so it cannot bleed
    into its atlas neighbour), which squeezes a 5-texel ``t`` by a fifth and
    smears it into the next letter ("to" read as "b").
    """
    from PIL import Image, ImageDraw

    from .texture import Texture

    font = _loaded(face, pixels)
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    # Guard degenerate spaces; every real glyph has a tiny owned texture. One
    # texel of padding round the ink, and one more on the right for the phase.
    width, height = max(1, right - left + 3), max(1, bottom - top + 2)
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    if not antialias:
        draw.fontmode = "1"  # bi-level glyphs (emtk.fonts antialias=False)
    draw.text(
        (1 - left + float(phase), 1 - top), char, font=font, anchor="ls",
        fill=(255, 255, 255, 255),
    )
    return (Texture(width, height, image.tobytes(), filter=filter),
            float(left - 1), float(top - 1))


#: Largest glyph raster, in device pixels. Bounds GPU image-atlas occupancy;
#: larger text scales the raster of the real face.
MAX_RASTER_PX = 64


def glyphs(spec: FontSpec, string: str, scale: float, bold: bool = False,
           device: float = 1.0, origin: tuple[float, float] | None = None):
    """Yield texture, bounds and pen position of each glyph.

    Geometry is in the caller's pixels (logical for a GPU painter, which
    applies the device ratio itself). *device* is how many device pixels one
    of those is: the glyph is **rasterised at the device size**, so a 2x
    display gets a 2x raster rather than a 1x one stretched. Pen positions
    come from the :data:`LAYOUT_PX` layout, the same numbers
    :func:`text_width` returns, so measurement and drawing agree.

    Without *origin* the boxes are relative to the string's top-left. With
    *origin* (the string's top-left, in caller pixels) they are absolute and
    laid on the device grid the way they will be drawn: the baseline snapped
    once for the whole line, each glyph rasterised at its pen's sub-pixel
    phase (:data:`SUBPIXEL_STEPS`) and boxed one texel per device pixel, so
    nothing is resampled and no glyph moves off its advance.
    """
    string = display(string)
    actual = replace(spec, bold=spec.bold or bold)
    em = _px(actual, scale)
    device = float(device) if device and device > 0 else 1.0
    from . import fonts  # noqa: PLC0415

    # emtk.fonts' oversampling: rasterise finer than the device and scale down.
    over = max(1.0, fonts.oversample())
    smooth = fonts.antialias()
    exact = em * device
    raster = max(1.0, min(round(exact * over * RASTER_QUANTUM) / RASTER_QUANTUM,
                          float(MAX_RASTER_PX)))
    unit = em / raster  # caller pixels per raster texel
    k = em / LAYOUT_PX
    ascent = _layout_metrics(actual)[0] * k
    positions = _positions(actual, string)
    faces = [face for face, _, text in _runs(actual, string) for _ in text]
    # On the grid only when a texel is a device pixel (a clamped or oversampled raster
    # is scaled).
    snap = origin is not None and abs(raster - exact) * RASTER_QUANTUM <= 1.0
    ox, oy = origin if origin is not None else (0.0, 0.0)
    baseline = round((oy + ascent) * device)
    for index, char in enumerate(string):
        if char.isspace():
            continue
        pen = positions[index] * k
        if snap:
            pen_device = (ox + pen) * device
            whole = math.floor(pen_device)
            phase = round((pen_device - whole) * SUBPIXEL_STEPS) / SUBPIXEL_STEPS
            if phase >= 1.0:
                whole, phase = whole + 1, 0.0
            texture, left, top = _glyph(faces[index], raster, char, phase, "nearest", smooth)
            yield (
                texture,
                (whole + left) / device,
                (baseline + top) / device,
                texture.width / device,
                texture.height / device,
            )
            continue
        texture, left, top = _glyph(faces[index], raster, char, 0.0, "linear", smooth)
        yield (texture, ox + pen + left * unit, oy + ascent + top * unit,
               texture.width * unit, texture.height * unit)


@lru_cache(maxsize=1024)
def _positions(spec, string):
    """Pen position of every character at :data:`LAYOUT_PX`, kerning included.

    ``getlength(text[:i + 1]) - getlength(char)`` per character is the definition (the
    advances before it plus the kerning up to and including its pair with the previous
    character), but measuring every prefix is quadratic: a 150-character prose line
    was 150 FreeType layouts of up to 150 glyphs, a second per frame for a page of
    documentation. The same sum is built from cached single advances and pair kerns.
    """
    out: list[float] = []
    offset = 0.0
    for face, _, text in _runs(spec, string):
        pen = offset
        previous = None
        for char in text:
            if previous is not None:
                pen += _kern(face, previous, char)
            out.append(pen)
            pen += _advance(face, char)
            previous = char
        offset += float(_loaded(face, LAYOUT_PX).getlength(text))
    return tuple(out)


@lru_cache(maxsize=8192)
def _advance(face: Face, char: str) -> float:
    """Advance of *char* at :data:`LAYOUT_PX`."""
    return float(_loaded(face, LAYOUT_PX).getlength(char))


@lru_cache(maxsize=65536)
def _kern(face: Face, left: str, right: str) -> float:
    """Kerning of the pair at :data:`LAYOUT_PX` (zero for most pairs)."""
    font = _loaded(face, LAYOUT_PX)
    return float(font.getlength(left + right)) - _advance(face, left) - _advance(face, right)


def draw_text(
    painter,
    spec,
    scale,
    x,
    y,
    w,
    h,
    align,
    string,
    colour,
    bold=False,
    degrees=0.0,
    require_resolver=False,
    device=1.0,
):
    """Draw shared real-font glyph textures through the existing image seam.

    *device* is device pixels per caller pixel (a GPU painter's ratio): the
    glyphs are rasterised at that resolution and their boxes snapped to the
    device pixel grid, so text is as sharp on a 2x display as the chrome is.
    """
    from .painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER

    if require_resolver and not callable(painter.image_uv_resolver):
        raise RuntimeError(
            "Selected font rendering requires the host image atlas resolver"
        )
    spec = replace(spec, bold=spec.bold or bold)
    span = text_width(spec, string, scale)
    height = line_height(spec, scale)
    left = x + (
        w - span
        if align & ALIGN_RIGHT
        else (w - span) / 2
        if align & ALIGN_HCENTER
        else 0
    )
    top = y + ((h - height) / 2 if align & ALIGN_VCENTER else 0)
    co, si = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    centre = (x + w / 2, y + h / 2)
    device = float(device) if device and device > 0 else 1.0
    origin = (left, top) if not degrees else None
    for texture, gx, gy, gw, gh in glyphs(spec, string, scale, bold, device, origin):
        if require_resolver and painter.image_uv_resolver(texture) is None:
            raise RuntimeError("Selected font glyph does not fit the host image atlas")
        if degrees:
            gx, gy = gx + left, gy + top
        if not degrees:
            painter.image(gx, gy, gw, gh, texture, tint=colour)
        else:
            points = [(gx, gy), (gx + gw, gy), (gx + gw, gy + gh), (gx, gy + gh)]
            points = [
                (
                    centre[0] + (px - centre[0]) * co - (py - centre[1]) * si,
                    centre[1] + (px - centre[0]) * si + (py - centre[1]) * co,
                )
                for px, py in points
            ]
            painter.image_triangle(*points[:3], texture, uv2=(1, 1), tint=colour)
            painter.image_triangle(
                points[0],
                points[2],
                points[3],
                texture,
                uv0=(0, 0),
                uv1=(1, 1),
                uv2=(0, 1),
                tint=colour,
            )
