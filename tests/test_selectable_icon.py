"""A selectable's icon sits in a slot of its own, so every label starts in one column."""

from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def draw(gui, storage):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 300.0, 200.0), io=IO(), storage=storage):
        gui()
    return painter


def x_of(painter, string):
    return next(t[0] for t in painter.texts if t[5] == string)


def test_icon_gets_a_slot_and_labels_align():
    def gui():
        im.selectable("ALEX Creator", icon="🔀")
        im.selectable("Micro-time Shifter", icon="⏱️")
        im.selectable("Plain row")

    painter = draw(gui, {})
    assert "🔀" in painter.strings
    # The variation selector draws nothing of its own; left in, it is a missing-glyph box.
    assert "⏱" in painter.strings and "⏱️" not in painter.strings
    assert x_of(painter, "ALEX Creator") == x_of(painter, "Micro-time Shifter")
    assert x_of(painter, "ALEX Creator") > x_of(painter, "🔀")
    assert x_of(painter, "Plain row") < x_of(painter, "ALEX Creator")


def test_icon_does_not_change_the_id_or_the_click():
    storage = {}
    rects = {}

    def gui():
        im.selectable("Row##a", icon="🎵")
        rects["a"] = im.get_item_rect()

    draw(gui, storage)
    painter = draw(gui, storage)
    assert "Row" in painter.strings and "Row##a" not in painter.strings
    assert rects["a"][2] > 0


def test_icon_width_is_the_label_offset():
    widths = {}

    def gui():
        widths["slot"] = im.selectable_icon_width()
        im.selectable("With", icon="🔀")
        im.selectable("Without")

    painter = draw(gui, {})
    assert x_of(painter, "With") - x_of(painter, "Without") == widths["slot"]
