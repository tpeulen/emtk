Testing your UI
==================

emtk ships :mod:`emtk.testing`, which is why a widget test needs no window,
no toolkit and no event loop.

RecordingPainter
-----------------

:class:`~emtk.testing.RecordingPainter` implements the painter contract by
recording every call. Its metrics are deliberately round — seven pixels
per character, sixteen per line — so an expected position in a test is
arithmetic a reader can do in their head::

    painter = RecordingPainter()
    assert painter.GLYPH_W == 7.0
    assert painter.LINE_H == 16.0
    assert painter.text_width("hello") == 5 * 7.0
    assert painter.line_height() == 16.0

The per-kind lists (``fills``, ``strokes``, ``strings``, ``texts``,
``clips``, ``triangles``) and the flat ``calls`` list cover both "how
many of this kind" and "is X drawn over Y"::

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 200, 80)):
        im.begin("T")
        im.button("A")
        im.button("B")
        im.end()

    assert len(painter.fills) > 0
    assert painter.strings == ["T", "A", "B"]

Simulating clicks
-------------------

A button fires on *release* inside, matching Dear ImGui's
``ButtonBehavior`` default. Simulate it by setting the pointer position,
pressing, and releasing::

    painter = RecordingPainter()
    io, storage = im.IO(), {}
    with im.frame(painter, (0, 0, 200, 80), io=io, storage=storage) as ctx:
        im.begin("Click", (0, 0, 200, 80))
        im.button("Press me")
        box = ctx.get_item_rect()
        im.end()

    # move pointer inside the button
    io.mouse_pos = (box[0] + 4, box[1] + 4)
    io.mouse_clicked[0] = True
    io.mouse_down[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 200, 80), io=io, storage=storage):
        im.begin("Click", (0, 0, 200, 80))
        clicked = im.button("Press me")
        im.end()

    assert not clicked  # fires on release

    io.mouse_down[0] = False
    io.mouse_released[0] = True

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 200, 80), io=io, storage=storage):
        im.begin("Click", (0, 0, 200, 80))
        clicked = im.button("Press me")
        im.end()

    assert clicked

PixelPainter and screenshots
-----------------------------

:class:`~emtk.testing.PixelPainter` rasterises into an RGBA buffer.
:func:`~emtk.testing.render` drives two frames through it (the first
settles layout; the second draws the settled interface).
:func:`~emtk.testing.screenshot` returns PNG bytes.
:func:`~emtk.testing.assert_images_equal` compares two PNGs pixel for
pixel::

    from emtk.testing import render, screenshot, assert_images_equal

    def gui():
        im.begin("Demo", (0, 0, 100, 60))
        im.text("hi")
        im.end()

    png = screenshot(gui, (0, 0, 100, 60))
    assert png[:4] == b'\x89PNG'  # valid PNG header

Deterministic output = doctestable output. The metrics are round, the
atlas is committed, and a screenshot is identical on every machine that
runs the same commit.
