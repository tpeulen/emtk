"""Pictograms -- the emoji a ribbon button, a menu row or a list row carries -- drawn in colour.

Why icons are not text
----------------------
An icon used to be drawn as a *glyph*: one character through the text path.
The text path draws every glyph as a coverage mask tinted with the text colour,
which is right for letters and wrong for a pictogram: a colour emoji came out
as a grey silhouette (its light fill thinned away, so the 🪄 of a wizard was a
few dark pixels), and its size was whatever was left of a monospace cell once
the picture had been squeezed into one advance -- a different size for every
emoji, since each fills its em differently, sitting on the text baseline rather
than centred in its slot. Same manifest icon, colour and evenly sized in the Qt
window, grey and ragged here.

So an icon is an **image**: the emoji is rasterised in colour from the system's
colour-emoji font, cropped to its own ink (not its advance, which includes the
font's side bearings and differs per glyph), scaled to fit a square box with
its aspect preserved and centred in it, and drawn with ``Painter.image``. The
box is the size *class* (:data:`SMALL_ICON`, :data:`LARGE_ICON`, both in
line heights) -- one rule, used by every place that draws an icon, so the icons
of one class are one size wherever they appear. It is rasterised at the device
scale, so a Retina display gets device pixels rather than a blown-up bitmap.

A pictogram the colour font does not have (◐, a plain geometric mark) is
rasterised from the first font that covers it, as a white mask the caller's
text colour tints -- the one case where monochrome is the picture.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict

from .texture import Texture

__all__ = [
    "SMALL_ICON",
    "LARGE_ICON",
    "EMOJI_FONTS",
    "IconTexture",
    "icon_box",
    "icon_texture",
    "draw_icon",
]

logger = logging.getLogger(__name__)

#: A small icon's square box, in line heights: a menu row, a list row, a small
#: ribbon button. One line, so a row of icons is no taller than a row of text.
SMALL_ICON = 1.0
#: A large ribbon button's (or a collapsed group's) icon, in line heights.
LARGE_ICON = 2.0

#: Colour-emoji fonts, tried in order; the first that loads and covers the
#: pictogram draws it. Bitmap fonts (Apple's ``sbix``, Noto's ``CBDT``) load
#: only at their strike size, so each comes with the sizes to try.
EMOJI_FONTS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("/System/Library/Fonts/Apple Color Emoji.ttc", (160, 96, 64, 48, 40, 32, 20)),
    ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", (109,)),
    ("/usr/share/fonts/noto-color-emoji/NotoColorEmoji.ttf", (109,)),
    ("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf", (109,)),
    ("C:/Windows/Fonts/seguiemj.ttf", (160,)),
)

#: Codepoints that select a presentation or join a sequence; dropped when the
#: font draws the sequence as nothing (PIL's basic layout has no shaping).
_MODIFIERS = dict.fromkeys((0xFE0E, 0xFE0F, 0x200D))

#: ``(icon, pixels) -> (Texture, colour)`` -- most recent last.
_CACHE: OrderedDict = OrderedDict()
_CACHE_SIZE = 512
#: path -> loaded font (or ``None`` when it does not load), and path -> cmap.
_FONTS: dict = {}
_COVERAGE: dict = {}


def icon_box(line_height: float, large: bool = False) -> float:
    """The side of an icon's square box, in logical pixels: the one size rule."""
    return float(line_height) * (LARGE_ICON if large else SMALL_ICON)


def _covers(path: str, code: int) -> bool:
    covered = _COVERAGE.get(path)
    if covered is None:
        covered = set()
        try:
            from fontTools.ttLib import TTCollection, TTFont  # noqa: PLC0415

            faces = (TTCollection(path, lazy=True).fonts if path.lower().endswith(".ttc")
                     else [TTFont(path, lazy=True)])
            for face in faces:
                covered |= set(face.getBestCmap() or {})
        except Exception:  # noqa: BLE001 - no fontTools, or an unreadable font
            covered = None
        _COVERAGE[path] = covered if covered is not None else False
        covered = _COVERAGE[path]
    if covered is False:
        return True       # cannot tell: let the rasteriser try and judge by its ink
    return code in covered


def _font(path: str, sizes):
    if path in _FONTS:
        return _FONTS[path]
    import pathlib  # noqa: PLC0415

    font = None
    if pathlib.Path(path).exists():
        from PIL import ImageFont  # noqa: PLC0415

        for size in sizes:
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:  # noqa: BLE001 - a bitmap font refuses every non-strike size
                continue
    _FONTS[path] = font
    return font


def _ink(canvas):
    """*canvas* cropped to its non-transparent pixels, or ``None`` if it has none."""
    box = canvas.getchannel("A").getbbox()
    return canvas.crop(box) if box else None


def _rasterise_colour(icon: str):
    """The pictogram drawn by the first colour-emoji font that has it, cropped to its ink."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    code = ord(icon[0])
    for path, sizes in EMOJI_FONTS:
        if not _covers(path, code):
            continue
        font = _font(path, sizes)
        if font is None:
            continue
        side = int(font.size * 2)
        for text in dict.fromkeys((icon, icon.translate(_MODIFIERS))):
            if not text:
                continue
            canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            try:
                ImageDraw.Draw(canvas).text((side // 2, side // 2), text, font=font,
                                            anchor="mm", embedded_color=True)
            except Exception:  # noqa: BLE001 - a glyph is not worth a frame
                logger.debug("could not rasterise icon %r from %s", text, path, exc_info=True)
                continue
            ink = _ink(canvas)
            if ink is not None:
                return ink
    return None


def _rasterise_mask(icon: str):
    """A pictogram no colour font has, as a white mask from the first text font that covers it."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from .dynamic_font import FONT_CANDIDATES  # noqa: PLC0415

    text = icon.translate(_MODIFIERS)
    if not text:
        return None
    code = ord(text[0])
    for path in FONT_CANDIDATES:
        if "emoji" in path.lower() or not _covers(path, code):
            continue
        font = _font(path, (128,))
        if font is None:
            continue
        canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text((128, 128), text, font=font, anchor="mm",
                                    fill=(255, 255, 255, 255))
        ink = _ink(canvas)
        if ink is not None:
            return ink
    return None


class IconTexture(Texture):
    """A :class:`~emtk.texture.Texture` that knows which pictogram it shows.

    ``icon`` is what a recording painter reports, so a test can ask "was the 📉
    drawn" of an image as it asks it of a string.
    """

    __slots__ = ("icon",)


def _fit(ink, pixels: int, icon: str):
    """*ink* scaled to fit a ``pixels`` square, aspect preserved, centred, as a texture."""
    from PIL import Image  # noqa: PLC0415

    factor = pixels / max(ink.width, ink.height)
    w = max(1, round(ink.width * factor))
    h = max(1, round(ink.height * factor))
    small = ink.resize((w, h), Image.LANCZOS)
    square = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
    square.paste(small, ((pixels - w) // 2, (pixels - h) // 2))
    texture = IconTexture(pixels, pixels, square.tobytes())
    texture.icon = icon
    return texture


def icon_texture(icon: str, pixels: int):
    """*icon* rasterised into a ``pixels`` square: ``(Texture, colour)`` or ``(None, False)``.

    ``colour`` is ``True`` for a colour emoji (draw it untinted) and ``False``
    for a mask (tint it with the text colour). Cached per ``(icon, pixels)``.
    """
    pixels = max(4, int(pixels))
    key = (icon, pixels)
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return hit
    result = (None, False)
    try:
        ink = _rasterise_colour(icon)
        colour = ink is not None
        if ink is None:
            ink = _rasterise_mask(icon)
        if ink is not None:
            result = (_fit(ink, pixels, icon), colour)
    except ImportError:
        logger.debug("no PIL: icons draw as text")
    _CACHE[key] = result
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return result


def _device_scale(p) -> float:
    """Device pixels per logical pixel of the painter *p* (wrappers unwrapped); 2 when unknown."""
    for _depth in range(8):
        if p is None:
            break
        own = getattr(p, "__dict__", {})
        for name in ("_scale", "scale"):
            value = own.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                return float(value)
        p = own.get("_real") or own.get("painter") or own.get("p")
    return 2.0


def draw_icon(p, icon: str, x: float, y: float, size: float, colour=(255, 255, 255, 255),
              enabled: bool = True) -> bool:
    """Draw *icon* fitted into the square ``(x, y, size, size)`` on the painter *p*.

    Parameters
    ----------
    p : Painter
        The painter (``ctx.p``, or a ``DrawList``'s ``p``).
    icon : str
        The pictogram, normally an emoji.
    x, y, size : float
        The box, in logical pixels: :func:`icon_box` gives *size*.
    colour : tuple
        The text colour: tints a monochrome pictogram, and its alpha fades a colour one.
    enabled : bool
        ``False`` draws a colour icon faded, as a disabled control's.

    Returns
    -------
    bool
        ``False`` when nothing could be rasterised; the caller may then draw the
        icon as text.
    """
    if not icon or size <= 0:
        return False
    pixels = math.ceil(size * _device_scale(p))
    texture, is_colour = icon_texture(icon, pixels)
    if texture is None:
        return False
    r, g, b, a = (tuple(colour) + (255,))[:4]
    if is_colour:
        tint = (255, 255, 255, int(a if enabled else a * 0.4))
    else:
        tint = (int(r), int(g), int(b), int(a))
    from .painter import image  # noqa: PLC0415

    image(p, float(x), float(y), float(size), float(size), texture, (0.0, 0.0), (1.0, 1.0), tint)
    return True
