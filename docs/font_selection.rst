Native font selection
=====================

The packaged ``monospace`` face remains the default. Selecting no font, or
calling ``painter.set_font(None)``, restores its original metrics and atlas
pixels. The native GPU, Pillow and reference Pixel painters also support real
system font families when Pillow's existing FreeType support is available.
No Qt import or new dependency is needed by the font-selection code.

Discover choices instead of assuming a family exists::

    from emtk.font import available_fonts
    names = available_fonts(monospaced=True)
    painter.set_font({"family": names[1], "size": 12})

``available_fonts()`` returns a tuple containing the baked ``monospace`` alias
and system families that were actually opened and measured. The optional
monospaced filter checks fixed Latin advances, useful for editor column
geometry. New fonts installed after discovery require restarting the process.

``set_font`` accepts a family string, ``None``, or a dictionary containing
``family``, ``size``, ``bold`` and ``italic``. Sizes are points at 96 logical
pixels per inch, matching QtPainter's existing convention. Its optional second
size argument overrides the dictionary size; omitted, zero and ``None`` mean
the baked default size. ``set_font_scale`` scales ink and measured dimensions
together. The CPU painters additionally retain their existing text device-scale
convention, while QuadPainter reports logical dimensions.

Generic ``sans-serif``/``sans`` and ``serif`` families resolve to available
system faces. ``prose`` -- the face :mod:`emtk.type_scale` sets running text
and headings in -- resolves to Verdana, else DejaVu Sans / Bitstream Vera Sans:
the proportional relatives of the Menlo (DejaVu Sans Mono) chrome, with the
same x-height and screen spacing, so prose sits beside the interface without
looking smaller or thinner. Unknown named families, unavailable bold/italic
faces, invalid attributes and invalid sizes raise an explicit error rather than
appearing to change settings while drawing the same font. The baked face
includes regular and bold glyphs; italic requires an actual system family such
as Menlo or DejaVu Sans Mono.

Selected faces are laid out at 512 px, where hinting is lost in the noise, so
widths and pen positions are linear in the size (kerning pairs included; this
is not a complete contextual-script shaping engine). A glyph is rasterised at
the **exact** device em (not rounded to a whole pixel) and at one of four
sub-pixel pen phases, then drawn one texel per device pixel with nearest
sampling on a baseline snapped once per line: every pen lands within 1/8 device
pixel of the layout, and nothing is resampled. Rasters cap at 64 device pixels
and scale beyond that. The glyph-texture cache holds 4096 entries. Characters
the face lacks come from the shared fallback list (Menlo, Arial Unicode, Apple
Symbols, SF for the late subscripts ``ₖ ₘ ₙ``, ...). ``tests/test_prose_glyph_placement.py``
pins the placement.

GPU hosts must install the existing image-atlas resolver; WgpuRenderer.painter
does this automatically. A missing/full resolver produces an explicit font
rendering error. Current-frame image handles stay alive and their UVs refresh
at vertex submission, so repacking the image atlas cannot give earlier quads
stale regions.

Font settings: one configuration for every role
-----------------------------------------------

:mod:`emtk.fonts` is the one place an application offers font settings. A
:class:`~emtk.fonts.FontConfig` holds, per **role** -- ``ui`` (the chrome),
``code`` (editors and consoles), ``prose`` and ``heading`` (documentation),
``math`` and ``caption`` -- a family, a size in points (``0`` follows the
interface size, or for headings and captions the prose size by the steps of the
type scale) and a weight, plus four settings for all text:

``zoom``
    Interface magnification (0.5-3). :class:`emtk.app.ControlSurface` lays the
    control out in a box ``zoom`` times smaller and draws it ``zoom`` times
    larger, and divides pointer positions by it -- text, paddings, icons and
    plots grow together and clicks still land where things are drawn.
``oversample``
    Raster scale of real-font glyphs (1-4). ``1`` is one texel per device pixel
    on the device grid; above it glyphs are rasterised finer and scaled down.
``antialias``
    Grey-scale (on) or bi-level (off) real-font glyphs. FreeType through Pillow
    exposes no hinting control, so there is no hinting setting.
``heading_step``
    Ratio between heading sizes (the type scale's :data:`~emtk.type_scale.STEP`).

A family may be a chain, ``"Inter, Verdana, prose"``: the first installed entry
is the face and the rest are tried, in order, for any character it lacks, before
the system coverage faces. ``fallbacks`` is appended to every role's chain.

::

    from emtk import fonts

    fonts.update(code={"family": "Menlo", "size": 11}, zoom=1.25)
    settings["fonts"] = fonts.config().to_dict()     # plain dict, YAML/JSON-ready
    fonts.apply(settings["fonts"])                    # at startup
    fonts.system_families(monospace=True)             # for a picker
    fonts.measure("code", "def fit(x):")              # what a layout measures
    fonts.reset()                                     # back to the defaults

:func:`~emtk.fonts.apply` takes effect on the next frame: it clears the glyph,
layout and formula caches and bumps :func:`~emtk.fonts.generation`, which every
host compares to rebuild its painter. A hand-edited dict is clamped, never
rejected, and a family that is not installed falls back to the role's default,
so a settings file from another machine cannot stop an interface drawing.

The ``ui`` family defaults to ``monospace``, the baked face. Another family is
adopted by every new painter (``painter.set_font(None)`` and a font dict
without a family resolve to it); the interface lays out from measured widths,
so a proportional face works, at the cost of real-font drawing. The
:class:`~emtk.widgets.text_editor.TextEditor` draws in the ``code`` role
(``EditorConfig.font_role``) unless its host pushed a font of its own; its
columns assume a monospaced face, which is why a ``code`` picker should list
``system_families(monospace=True)``.
