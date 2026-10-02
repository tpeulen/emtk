"""Optional real font selection, shared by native and CPU painters.

The packaged monospace atlas stays the default. Explicit system faces use
Pillow's existing FreeType support, without Qt or a platform font server.
"""

from __future__ import annotations

import math
import os
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
    result: dict[str, list[Face]] = {}
    for path in paths[:4096]:
        for index in range(64 if path.suffix.lower() == ".ttc" else 1):
            try:
                font = ImageFont.truetype(str(path), 16, index=index)
                family, style = font.getname()
                # Names alone are insufficient: only faces FreeType actually
                # opens and measures are offered to the caller.
                advances = [font.getlength(char) for char in "ilMW@08."]
                mono = max(advances) - min(advances) < 0.1 and bytes(
                    font.getmask("i")
                ) != bytes(font.getmask("M"))
                style = style.casefold()
                face = Face(
                    str(path),
                    index,
                    "bold" in style or "black" in style,
                    "italic" in style or "oblique" in style,
                    mono,
                    style,
                )
                result.setdefault(family, []).append(face)
            except (OSError, ValueError):
                break
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


def _face(spec: FontSpec) -> Face:
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


@lru_cache(maxsize=64)
def _loaded(face: Face, pixels: int):
    from PIL import ImageFont

    return ImageFont.truetype(face.path, pixels, index=face.index)


def _font(spec: FontSpec, scale: float, bold: bool = False):
    actual = FontSpec(spec.family, spec.size, spec.bold or bold, spec.italic)
    return _loaded(_face(actual), max(1, round(actual.size * PX_PER_PT * scale)))


def text_width(spec: FontSpec, string: str, scale: float) -> float:
    return float(_font(spec, scale).getlength(string))


def line_height(spec: FontSpec, scale: float) -> float:
    ascent, descent = _font(spec, scale).getmetrics()
    return float(ascent + descent)


@lru_cache(maxsize=512)
def _glyph(spec: FontSpec, pixels: int, char: str):
    from PIL import Image, ImageDraw

    from .texture import Texture

    font = _loaded(_face(spec), pixels)
    left, top, right, bottom = font.getbbox(char, anchor="ls")
    # Guard degenerate spaces; every real glyph has a tiny owned texture.
    width, height = max(1, right - left + 2), max(1, bottom - top + 2)
    image = Image.new("RGBA", (width, height))
    ImageDraw.Draw(image).text(
        (1 - left, 1 - top), char, font=font, anchor="ls", fill=(255, 255, 255, 255)
    )
    return Texture(width, height, image.tobytes()), float(left - 1), float(top - 1)


def glyphs(spec: FontSpec, string: str, scale: float, bold: bool = False):
    """Yield texture, baseline-relative bounds and real shaped advance.

    The shared glyph LRU is bounded. Raster pixels cap at 48px for bounded
    GPU image-atlas occupancy; larger fonts scale the selected real face.
    """
    actual = FontSpec(spec.family, spec.size, spec.bold or bold, spec.italic)
    font = _font(actual, scale)
    size = max(1, round(actual.size * PX_PER_PT * scale))
    raster_size = min(size, 48)
    factor = size / raster_size
    ascent, _ = font.getmetrics()
    positions = _positions(actual, size, string)
    for index, char in enumerate(string):
        if char.isspace():
            continue
        texture, left, top = _glyph(actual, raster_size, char)
        # Prefix measurement includes kerning. Glyph positions and the width
        # query therefore agree for proportional as well as fixed-width faces.
        advance = positions[index]
        yield (
            texture,
            advance + left * factor,
            ascent + top * factor,
            texture.width * factor,
            texture.height * factor,
        )


@lru_cache(maxsize=128)
def _positions(spec, size, string):
    font = _loaded(_face(spec), size)
    return tuple(
        float(font.getlength(string[: index + 1]) - font.getlength(char))
        for index, char in enumerate(string)
    )


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
):
    """Draw shared real-font glyph textures through the existing image seam."""
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
    for texture, dx, dy, gw, gh in glyphs(spec, string, scale, bold):
        if require_resolver and painter.image_uv_resolver(texture) is None:
            raise RuntimeError("Selected font glyph does not fit the host image atlas")
        gx, gy = left + dx, top + dy
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
