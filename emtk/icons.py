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

So an icon is an **image**: the emoji is taken **from the atlas's baked colour
band** first -- pictographs rasterised from a pinned Noto Color Emoji at bake
time, so every host draws the same picture, including the ones with no colour
font at all (the web release: Pyodide ships no fonts, and before the band its
icons fell back to the grey masks of the text path) -- or, for a pictograph the
bake does not cover, rasterised in colour from the system's colour-emoji font.
Either way it is cropped to its own ink (not its advance, which includes the
font's side bearings and differs per glyph), scaled to fit a square box with
its aspect preserved and centred in it, and drawn with ``Painter.image``. The
box is the size *class* (:data:`SMALL_ICON`, :data:`LARGE_ICON`, both in
line heights) -- one rule, used by every place that draws an icon, so the icons
of one class are one size wherever they appear, and they scale with the font
size the line height tracks. The texture is fitted at the device scale, so a
Retina display gets device pixels rather than a blown-up bitmap, and the bake
at 128 px makes every drawn size a minification -- the painter's ordinary
filtering is all the resampling an icon needs at any size the interface asks
for.

A pictogram the colour font does not have (◐, a plain geometric mark) is
rasterised from the first font that covers it, as a white mask the caller's
text colour tints -- the one case where monochrome is the picture.

Pictograms inside a caption
---------------------------
A caption may *start* with a pictogram (``"❓  Help"``, ``"📖  Guide"``,
``"🌍 EN"``) or carry one mid-text. Those go through the painter's ``text``,
so the real painters (the GPU one, the Pillow and pixel screenshot ones) split
the string with :func:`pictogram_runs` and draw each colour cluster as an image
in a small icon box, the rest as text: :func:`caption_width` and
:func:`draw_caption` share one measurement, so a button sized from
``text_width`` fits what is drawn. A recording painter still records the whole
string -- what a test clicks on is the caption, not its pieces. A glyph with no
colour form (◐ ✕ ›) stays text. The icon's alpha follows the text colour's, so
a disabled caption fades its icon with its words.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from contextlib import contextmanager
from functools import lru_cache

from .texture import Texture

__all__ = [
    "SMALL_ICON",
    "LARGE_ICON",
    "EMOJI_FONTS",
    "IconTexture",
    "icon_box",
    "icon_texture",
    "draw_icon",
    "pictogram_runs",
    "plain_text",
    "icon_spans",
    "caption_width",
    "draw_caption",
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
        for text in _forms(icon):
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
            if ink is not None and (text != icon or len(icon) == 1
                                    or ink.width <= 1.6 * ink.height):
                return ink
    return None


def _atlas_ink(icon: str):
    """The pictogram's **baked colour cell**, cropped to its ink, or ``None``.

    The atlas ships a band of pictographs rasterised from a pinned Noto Color
    Emoji at bake time (see ``tools/bake_chrome_atlas.py``). Reading the band
    instead of a machine's colour font is what makes an icon the same picture
    everywhere -- and the one picture there is on a host with no fonts at all,
    which is the web release: Pyodide ships no system fonts, so
    :func:`_rasterise_colour` finds nothing to load and every menu icon fell
    back to the grey monochrome mask the text path draws.

    Falls open on anything -- no baked cell, no Pillow to crop with -- to the
    system-font rasters below, which is how a pictograph newer than the bake
    still draws.
    """
    from PIL import Image  # noqa: PLC0415

    from . import grapheme  # noqa: PLC0415
    from .font import load_atlas  # noqa: PLC0415
    from .gpu_atlas import png_decode  # noqa: PLC0415

    atlas = load_atlas()
    cell = atlas.icon_cell_of(grapheme.glyph_of(icon))
    if cell is None:
        return None
    global _ATLAS_IMAGE
    if _ATLAS_IMAGE is None:
        width, height, rgba = png_decode(atlas.image_path.read_bytes())
        _ATLAS_IMAGE = Image.frombytes("RGBA", (width, height), bytes(rgba))
    x, y, w, h = cell
    return _ATLAS_IMAGE.crop((x, y, x + w, y + h))


#: The atlas PNG, decoded once -- every icon reads a crop of the same image.
_ATLAS_IMAGE = None


def _shaped() -> bool:
    """Whether Pillow lays text out with a shaping engine (so a sequence can compose)."""
    try:
        from PIL import features  # noqa: PLC0415

        return bool(features.check("raqm"))
    except Exception:  # noqa: BLE001 - no PIL, no shaping
        return False


def _forms(icon: str) -> tuple[str, ...]:
    """The strings to try drawing for the cluster *icon*, best first.

    A multi-code-point cluster (skin tone, ZWJ, flag, tag, keycap) is one glyph
    only where the layout engine shapes it; without one Pillow draws each code
    point on its own -- the two glyphs of a skin-toned thumbs-up. Then the
    composed form is skipped and the **base** emoji is drawn alone, so one
    cluster is always one image.
    """
    from . import grapheme  # noqa: PLC0415

    base = grapheme.glyph_of(icon)
    if _EMOJI_SELECTOR in icon and base != icon:
        base += _EMOJI_SELECTOR
    forms = [icon] if (len(icon) == 1 or _shaped()) else []
    stripped = icon.translate(_MODIFIERS)
    forms += [base, stripped if len(stripped) == 1 else "", icon[0]]
    return tuple(dict.fromkeys(forms))


def _rasterise_mask(icon: str):
    """A pictogram no colour font has, as a white mask from the first text font that covers it."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    from . import grapheme  # noqa: PLC0415
    from .dynamic_font import _candidate_paths  # noqa: PLC0415

    text = icon.translate(_MODIFIERS)
    if len(text) > 1:
        text = grapheme.glyph_of(icon)      # one glyph for one cluster, never a row of them
    if not text:
        return None
    code = ord(text[0])
    for path in _candidate_paths():
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
        # The baked colour band first: the same picture on every host,
        # including the ones with no colour font to rasterise from. The
        # machine's faces stay as the fallback for a pictograph the bake
        # does not cover, then the white mask a text font can still draw.
        ink = _atlas_ink(icon)
        colour = ink is not None
        if ink is None:
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


# -- pictograms inside a caption ------------------------------------------- #

#: BMP codepoints whose default presentation is emoji (Unicode
#: ``Emoji_Presentation=Yes``); a text-default pictograph is one only when a
#: U+FE0F follows it or it leads a caption. Everything in the supplementary
#: pictograph planes (U+1F000--U+1FAFF) is a candidate by itself.
_BMP_EMOJI: tuple[tuple[int, int], ...] = (
    (0x231A, 0x231B), (0x23E9, 0x23EC), (0x23F0, 0x23F0), (0x23F3, 0x23F3),
    (0x25FD, 0x25FE), (0x2614, 0x2615), (0x2648, 0x2653), (0x267F, 0x267F),
    (0x2693, 0x2693), (0x26A1, 0x26A1), (0x26AA, 0x26AB), (0x26BD, 0x26BE),
    (0x26C4, 0x26C5), (0x26CE, 0x26CE), (0x26D4, 0x26D4), (0x26EA, 0x26EA),
    (0x26F2, 0x26F3), (0x26F5, 0x26F5), (0x26FA, 0x26FA), (0x26FD, 0x26FD),
    (0x2705, 0x2705), (0x270A, 0x270B), (0x2728, 0x2728), (0x274C, 0x274C),
    (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757), (0x2795, 0x2797),
    (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
)
#: Plain geometric shapes (▶ ■ ◐): a caption's mark, drawn as text even where
#: the colour font has a form for one -- ``view_form.icon_caption`` gives them
#: a one-space gap for exactly that reason.
_GEOMETRIC = (0x25A0, 0x25FF)
#: Codepoints that continue a cluster: presentation selectors, skin tones,
#: the keycap mark and tag characters.
_CONTINUES = frozenset((0xFE0F, 0x20E3)) | frozenset(range(0x1F3FB, 0x1F400)) | \
    frozenset(range(0xE0020, 0xE0080))
_ZWJ = 0x200D
_TEXT_SELECTOR = chr(0xFE0E)
_EMOJI_SELECTOR = chr(0xFE0F)
_REGIONAL = (0x1F1E6, 0x1F1FF)


def _emoji_default(code: int) -> bool:
    if 0x1F000 <= code <= 0x1FAFF:
        return True
    return any(lo <= code <= hi for lo, hi in _BMP_EMOJI)


def _cluster_end(string: str, start: int) -> int:
    """Index after the emoji cluster that starts at *start* (selectors, ZWJ joins, flags)."""
    n = len(string)
    i = start + 1
    if _REGIONAL[0] <= ord(string[start]) <= _REGIONAL[1]:
        if i < n and _REGIONAL[0] <= ord(string[i]) <= _REGIONAL[1]:
            i += 1
        return i
    while i < n:
        code = ord(string[i])
        if code in _CONTINUES:
            i += 1
        elif code == _ZWJ and i + 1 < n:
            i += 2
        else:
            break
    return i


def _is_candidate(string: str, start: int, end: int) -> bool:
    """Whether the cluster ``string[start:end]`` asks for its emoji (colour) form."""
    code = ord(string[start])
    tail = string[start + 1:end]
    if _TEXT_SELECTOR in string[start:end + 1]:
        return False                       # text presentation, asked for explicitly
    if chr(0x20E3) in tail:
        return True                        # keycap
    if code < 0x2190 or _GEOMETRIC[0] <= code <= _GEOMETRIC[1]:
        return False
    if _emoji_default(code) or _EMOJI_SELECTOR in tail:
        return True
    # A caption's leading pictogram, whose U+FE0F ``icon_text`` dropped: ⚙ Settings.
    return start == 0 and (end == len(string) or string[end].isspace())


@lru_cache(maxsize=4096)
def _has_colour(cluster: str) -> bool:
    """Whether *cluster* rasterises in colour (the font has it and PIL draws it)."""
    try:
        return bool(icon_texture(cluster, 32)[1])
    except Exception:  # noqa: BLE001 - a missing font is "no colour form"
        return False


@lru_cache(maxsize=8192)
def _runs(string: str):
    runs: list[tuple[str, bool]] = []
    text_start = 0
    i = 0
    n = len(string)
    found = False
    while i < n:
        char = string[i]
        code = ord(char)
        if code < 0x2190 and not ("0" <= char <= "9" or char in "#*"):
            i += 1
            continue
        end = _cluster_end(string, i)
        cluster = string[i:end]
        if _is_candidate(string, i, end) and _has_colour(cluster):
            if text_start < i:
                runs.append((string[text_start:i], False))
            runs.append((cluster, True))
            found = True
            text_start = end
        i = end
    if not found:
        return None
    if text_start < n:
        runs.append((string[text_start:], False))
    return tuple(runs)


_plain_text = 0


@contextmanager
def plain_text():
    """Within the block a painter draws every caption as text, with no icon runs.

    For a widget that lays characters out on a grid of its own -- the code editor
    -- and draws the colour clusters itself, in the cells it gave them. Whatever
    it passes to the painter's ``text`` is then one run of plain glyphs, measured
    and drawn at the font's own advance.
    """
    global _plain_text
    _plain_text += 1
    try:
        yield
    finally:
        _plain_text -= 1


def pictogram_runs(string: str):
    """*string* split into ``(text, is_icon)`` runs, or ``None`` when it has no colour pictogram.

    A colour run is one emoji cluster (selectors, skin tones, ZWJ sequences and
    flags included) that the colour font draws; everything else is text.
    ``None`` as well inside :func:`plain_text`.
    """
    if not string or string.isascii() or _plain_text:
        return None
    return _runs(string)


@lru_cache(maxsize=4096)
def icon_spans(string: str) -> tuple[tuple[int, int], ...]:
    """The ``(start, end)`` index ranges of *string* that are colour pictograms.

    The same clusters :func:`pictogram_runs` finds, as character ranges, and
    unaffected by :func:`plain_text` -- for a widget that must know where the
    clusters are to give each one its cells.
    """
    if not string or string.isascii():
        return ()
    spans = []
    at = 0
    for text, icon in _runs(string) or ():
        if icon:
            spans.append((at, at + len(text)))
        at += len(text)
    return tuple(spans)


def caption_width(runs, measure, line_height: float) -> float:
    """Width of *runs*: text by *measure*, each icon one small :func:`icon_box`."""
    box = icon_box(line_height)
    return float(sum(box if icon else measure(text) for text, icon in runs))


def draw_caption(p, runs, x: float, y: float, w: float, h: float, align: int, colour,
                 bold: bool, draw_text, measure, line_height: float) -> None:
    """Draw *runs* aligned in the box: text through *draw_text*, icons as colour images.

    *draw_text* and *measure* are the painter's own text primitives (its
    ``text``/``text_width`` before captions were split), so a text run looks
    exactly as it would alone; the layout is :func:`caption_width`'s.
    """
    from .painter import ALIGN_HCENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER  # noqa: PLC0415

    box = icon_box(line_height)
    widths = [box if icon else measure(text) for text, icon in runs]
    span = sum(widths)
    pen = (x + w - span if align & ALIGN_RIGHT
           else x + (w - span) * 0.5 if align & ALIGN_HCENTER else x)
    top = y + (h - box) * 0.5 if align & ALIGN_VCENTER else y + (line_height - box) * 0.5
    run_align = (align & ~(ALIGN_RIGHT | ALIGN_HCENTER)) | ALIGN_LEFT
    for (text, icon), width in zip(runs, widths):
        if not icon:
            draw_text(pen, y, width, h, run_align, text, colour, bold)
        elif not draw_icon(p, text, pen, top, box, colour):
            draw_text(pen, y, width, h, run_align, text, colour, bold)
        pen += width
