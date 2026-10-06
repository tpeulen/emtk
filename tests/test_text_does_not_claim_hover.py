"""A text item never owns the pointer: a button drawn over its end still takes the click.

ImGui's ``ItemAdd(id=0)`` does not claim HoveredId. emtk claimed it with the text's box
as key, so a status line wider than its room, drawn before Back / Next on the same line,
held the pointer over them and they took no clicks.
"""

from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def _frame(gui, io, storage):
    with im.frame(RecordingPainter(), (0, 0, 400.0, 120.0), io=io, storage=storage):
        gui()


def test_a_button_drawn_over_a_long_text_takes_the_click():
    storage, clicks, rect = {}, [], {}

    def gui():
        im.begin("bar")
        im.text_unformatted("a status line much wider than the room left of the buttons " * 3)
        im.same_line(200.0)
        if im.button("Next"):
            clicks.append(1)
        rect["next"] = im.get_item_rect()
        im.end()

    io = IO()
    _frame(gui, io, storage)
    x, y, w, h = rect["next"]
    centre = (x + w / 2, y + h / 2)
    for down, clicked, released in ((True, True, False), (False, False, True)):
        io = IO()
        io.mouse_pos = centre
        io.mouse_down[0] = down
        io.mouse_clicked[0] = clicked
        io.mouse_clicked_pos[0] = centre
        io.mouse_released[0] = released
        _frame(gui, io, storage)
    assert clicks == [1]


def test_a_text_is_still_hovered_for_its_own_tooltip():
    hovered = {}

    def gui():
        im.begin("bar")
        im.text_unformatted("hover me")
        hovered["text"] = im.is_item_hovered()
        im.end()

    storage = {}
    _frame(gui, IO(), storage)
    io = IO()
    io.mouse_pos = (20.0, 8.0)
    _frame(gui, io, storage)
    _frame(gui, io, storage)
    assert hovered["text"]


def test_text_ellipsis_keeps_to_its_room_and_tooltips_the_whole():
    shown = {}

    def gui():
        im.begin("bar")
        shown["cut"] = im.text_ellipsis("Bursts for the later steps: /a/very/long/path/to/the/burst/folder", 120.0)
        shown["rect"] = im.get_item_rect()
        shown["short"] = im.text_ellipsis("short", 120.0)
        im.end()

    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 400.0, 120.0), io=IO(), storage={}):
        gui()
    assert shown["cut"] and not shown["short"]
    assert shown["rect"][2] <= 120.0
    assert any(s.endswith("…") for s in painter.strings) and "short" in painter.strings
