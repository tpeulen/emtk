"""Optional real font selection, shared by native and CPU painters.

The packaged monospace atlas stays the default. Explicit system faces use
Pillow's existing FreeType support, without Qt or a platform font server.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .font import DEFAULT_FONT_PT, PX_PER_PT


@dataclass(frozen=True)
class FontSpec:
    family: str = "monospace"
    size: float = DEFAULT_FONT_PT
    bold: bool = False
    italic: bool = False


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
        raise ValueError(f"Font family {spec.family!r} is not available")
    found = next(
        (
            face
            for face in _faces()[family]
            if face.bold == spec.bold and face.italic == spec.italic
        ),
        None,
    )
    if found is None:
        raise ValueError(f"Font family {family!r} has no requested bold/italic face")
    return found


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
    family = data.get("family", "monospace")
    if not isinstance(family, str) or not family.strip():
        raise ValueError("Font family must be a nonempty name")
    for attribute in ("bold", "italic"):
        if attribute in data and not isinstance(data[attribute], bool):
            raise ValueError(f"Font {attribute} must be a boolean")
    family = family.strip()
    aliases = {
        "sans-serif": (
            "Arial",
            "Helvetica",
            "DejaVu Sans",
            "Liberation Sans",
            "Noto Sans",
        ),
        "sans": ("Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans"),
        "serif": (
            "Times New Roman",
            "Times",
            "DejaVu Serif",
            "Liberation Serif",
            "Noto Serif",
        ),
    }
    if family.casefold() in aliases:
        options = aliases[family.casefold()]
        family = next((name for name in options if name in _faces()), family)
    spec = FontSpec(
        family, effective_size, data.get("bold", False), data.get("italic", False)
    )
    if spec.family.casefold() == "monospace":
        if spec.italic:
            raise ValueError(
                "The baked monospace face has no italic style; select an available system family"
            )
        return FontSpec("monospace", spec.size, spec.bold, False)
    _face(spec)
    return spec


@lru_cache(maxsize=128)
def _loaded(face: Face, pixels: int):
    from PIL import ImageFont

    return ImageFont.truetype(face.path, pixels, index=face.index)


def _font(spec: FontSpec, scale: float, bold: bool = False):
    actual = FontSpec(spec.family, spec.size, spec.bold or bold, spec.italic)
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


@lru_cache(maxsize=4096)
def _face_for(face: Face, char: str) -> Face:
    """*face* when it has *char*, else the first fallback face that has it.

    A proportional face (Arial, Helvetica) lacks much of what documentation
    writes -- subscript digits (R\u2080), arrows, dingbats -- and drawing its
    ``.notdef`` box is the bug the baked chrome solved long ago with its own
    fallback list. The same list serves here, so a character looks the same
    in prose as in a button.
    """
    covered = _cmap(face.path, face.index)
    if covered is None or ord(char) in covered or char.isspace():
        return face
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
        face = _face_for(primary, char)
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
    return _layout_width(spec, string) * _px(spec, scale) / LAYOUT_PX


def line_height(spec: FontSpec, scale: float) -> float:
    """Ascent plus descent, in the caller's pixels; linear in *scale*."""
    ascent, descent = _layout_metrics(spec)
    return (ascent + descent) * _px(spec, scale) / LAYOUT_PX


@lru_cache(maxsize=512)
def _glyph(face: Face, pixels: int, char: str):
    from PIL import Image, ImageDraw

    from .texture import Texture

    font = _loaded(face, pixels)
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    # Guard degenerate spaces; every real glyph has a tiny owned texture.
    width, height = max(1, right - left + 2), max(1, bottom - top + 2)
    image = Image.new("RGBA", (width, height))
    ImageDraw.Draw(image).text(
        (1 - left, 1 - top), char, font=font, anchor="ls", fill=(255, 255, 255, 255)
    )
    return Texture(width, height, image.tobytes()), float(left - 1), float(top - 1)


#: Largest glyph raster, in device pixels. Bounds GPU image-atlas occupancy;
#: larger text scales the raster of the real face.
MAX_RASTER_PX = 64


def glyphs(spec: FontSpec, string: str, scale: float, bold: bool = False,
           device: float = 1.0):
    """Yield texture, baseline-relative bounds and pen position of each glyph.

    Geometry is in the caller's pixels (logical for a GPU painter, which
    applies the device ratio itself). *device* is how many device pixels one
    of those is: the glyph is **rasterised at the device size**, so a 2x
    display gets a 2x raster rather than a 1x one stretched. Pen positions
    come from the :data:`LAYOUT_PX` layout, the same numbers
    :func:`text_width` returns, so measurement and drawing agree.
    """
    actual = FontSpec(spec.family, spec.size, spec.bold or bold, spec.italic)
    em = _px(actual, scale)
    device = float(device) if device and device > 0 else 1.0
    raster = max(1, min(round(em * device), MAX_RASTER_PX))
    unit = em / raster  # caller pixels per raster texel
    k = em / LAYOUT_PX
    ascent = _layout_metrics(actual)[0] * k
    positions = _positions(actual, string)
    faces = [face for face, _, text in _runs(actual, string) for _ in text]
    for index, char in enumerate(string):
        if char.isspace():
            continue
        texture, left, top = _glyph(faces[index], raster, char)
        yield (
            texture,
            positions[index] * k + left * unit,
            ascent + top * unit,
            texture.width * unit,
            texture.height * unit,
        )


@lru_cache(maxsize=1024)
def _positions(spec, string):
    """Pen position of every character at :data:`LAYOUT_PX`, kerning included."""
    out: list[float] = []
    offset = 0.0
    for face, _, text in _runs(spec, string):
        font = _loaded(face, LAYOUT_PX)
        out.extend(
            offset + float(font.getlength(text[: index + 1]) - font.getlength(char))
            for index, char in enumerate(text)
        )
        offset += float(font.getlength(text))
    return tuple(out)


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
    spec = FontSpec(spec.family, spec.size, spec.bold or bold, spec.italic)
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
    for texture, dx, dy, gw, gh in glyphs(spec, string, scale, bold, device):
        if require_resolver and painter.image_uv_resolver(texture) is None:
            raise RuntimeError("Selected font glyph does not fit the host image atlas")
        gx, gy = left + dx, top + dy
        if not degrees:
            # One raster texel per device pixel: a box straddling pixels
            # would be resampled, which blurs every stem.
            gx, gy = round(gx * device) / device, round(gy * device) / device
            # The raster is em rounded to whole texels, so the glyph's box is a
            # few percent off texels / device. Left like that a full stop (3
            # texels tall, 1 of them ink) lands in a 2-pixel box that nearest
            # sampling reads at the two padding rows: the mark vanishes. When
            # the raster was not clamped, draw it 1:1.
            if 0.85 <= (gw * device / texture.width) <= 1.15 and \
                    0.85 <= (gh * device / texture.height) <= 1.15:
                gw, gh = texture.width / device, texture.height / device
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
