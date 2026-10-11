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

Driving an application
----------------------

``Driver`` operates an ``ImApp`` or control through pointer and keyboard
input, without a toolkit or display. It records frames with ``MetricPainter``,
which measures the same fonts as ``PixelPainter``. Named controls come from
``app.remember(name)``, ``app.item_rects`` or ``app.form.rects``; a drawn
caption, rectangle or coordinate pair is also a click target::

    from emtk.testing import Driver
    from emtk.keys import KEY_TAB, KEY_RETURN

    driver = Driver(app, (1100, 720))
    driver.frame(2)
    print(driver.ids())
    driver.click("Run")
    driver.settle(timeout=30)
    driver.press(KEY_TAB)
    driver.press(KEY_RETURN)
    driver.click("name")
    driver.type("Sample A")
    driver.wheel(-2, at=(100, 200), dx=0)
    driver.screenshot("renders/sample.png")

``frame(n=1)`` returns the last recording painter. ``draw(frames=2)`` is
also available for existing harnesses. Unknown targets raise ``LookupError``
so a missing control cannot silently become a click at an arbitrary point.
``settle`` watches optional ``running``, ``job.busy`` and ``model.busy``
flags and raises ``TimeoutError`` if work does not finish. A driver does
not own an application's lifetime: close the app at the end of the test
when it owns workers or other resources. ``screenshot()`` returns PNG bytes;
passing a path saves those bytes too.

A named target recorded as ``None`` has not been submitted in that frame (for
example, an image canvas before data loads). Driver omits it from ``ids()``
and raises ``LookupError`` if it is clicked. It does not invent geometry for
an unavailable control; normal named rectangles and caption lookup still work.

One-shot input and settling
---------------------------

A wheel notch, a click, a key, typed text and a drop are *one-shot* inputs:
each is delivered once and seen by exactly one frame. The frame loop spends
them (``IO.end_event``, called when the outermost frame on an ``IO`` ends) --
never the widget that reads them. A widget may still zero ``io.mouse_wheel``
to keep a notch from a widget drawn *later in the same frame* (a scroll area
taking the wheel from the page around it); that is routing, not clearing.
``IO.ONE_SHOT`` names the fields and ``IO.one_shot_state()`` snapshots them.

The rule exists because the opposite once shipped: the wheel was kept "until
a widget consumed it", a plot read it without zeroing it, and one notch zoomed
the plot on every frame until the pointer left it. Every test passed, because
every test looked at the frame *after* the notch and its hand-rolled driver
zeroed the wheel itself -- doing the frame loop's job.

Hosts turn raw platform deltas into whole notches with
``emtk.events.WheelAccumulator``: a trackpad sends dozens of small deltas a
second (and a momentum tail), and rounding each up to a notch made one swipe
dozens of notches. A plot zooms in proportion to the notches of a frame, at
most ``emtk.implot.WHEEL_NOTCHES_PER_FRAME``.

Test the settling, not only the response.
``emtk.testing_realistic.assert_settles`` performs a gesture, then draws idle
frames with the hand held still and fails if the observed state (by default
the whole drawn frame) changes again, or if the app keeps asking the host for
frames::

    from emtk.testing_realistic import RealisticDriver, assert_settles

    driver = RealisticDriver(app, (800, 600))
    driver.frame(2)
    assert_settles(driver, lambda d: d.wheel(1, at=plot_centre),
                   lambda: plot_limits(), frames=30)
    assert_settles(driver, lambda d: d.swipe(2, at=plot_centre), frames=30)

``swipe(dy)`` is a trackpad gesture: *dy* notches' worth of small deltas, one
per frame, followed by a decaying momentum tail. Replay input as the real
sequence -- the notch, then the hover that follows it -- rather than as a
single synthetic call.
