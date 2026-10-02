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
system faces. Unknown named families, unavailable bold/italic faces, invalid
attributes and invalid sizes raise an explicit error rather than appearing to
change settings while drawing the same font. The baked face includes regular
and bold glyphs; italic requires an actual system family such as Menlo or
DejaVu Sans Mono.

Selected faces use a shared bounded glyph-texture cache (512 entries), loaded
font cache (64 entries), and text-position cache (128 entries). Raster glyphs
cap at 48 pixels and scale for larger point sizes, trading sharpness at large
sizes for bounded atlas occupancy. Layout uses actual family advances, with
prefix kerning positions; this is not a complete contextual-script shaping
engine. Unsupported characters retain the selected font's visible missing-glyph
shape rather than silently disappearing.

GPU hosts must install the existing image-atlas resolver; WgpuRenderer.painter
does this automatically. A missing/full resolver produces an explicit font
rendering error. Current-frame image handles stay alive and their UVs refresh
at vertex submission, so repacking the image atlas cannot give earlier quads
stale regions.
