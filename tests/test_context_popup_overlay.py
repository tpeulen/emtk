"""Dear ImGui context menus must float over their parent content."""

from emtk import im
from emtk.im_core import IO
from emtk.testing import RecordingPainter


def draw(gui, io, storage, size=(500.0, 300.0)):
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, *size), io=io, storage=storage):
        gui()
    return painter


def test_context_menu_is_an_overlay_and_dispatches_selection_next_frame():
    storage = {}
    io = IO()
    actions = []
    item_rect = None

    def gui():
        nonlocal item_rect
        im.selectable("Target row")
        item_rect = im.get_item_rect()
        if im.begin_popup_context_item("row-actions"):
            if im.menu_item("Remove row"):
                actions.append("remove")
            im.set_item_tooltip("Remove the row without deleting its source")
            im.end_popup()
        im.text("Content remains in the parent layout")

    painter = draw(gui, io, storage)
    assert "Remove row" not in painter.strings
    io.mouse_pos = (item_rect[0] + 5, item_rect[1] + 5)
    io.mouse_down[1] = True
    io.mouse_clicked[1] = True
    io.mouse_clicked_pos[1] = io.mouse_pos
    painter = draw(gui, io, storage)
    assert "Remove row" in painter.strings
    popup = storage[("__state__", ("context_popup", "row-actions"))]["popup"]
    row = popup.row_rect(0)
    assert row is not None
    assert popup.panel_rect is not None
    assert popup.panel_rect[0] >= 0 and popup.panel_rect[1] >= 0

    io.mouse_clicked[1] = False
    io.mouse_down[1] = False
    io.mouse_pos = (row[0] + row[2] / 2, row[1] + row[3] / 2)
    io.mouse_down[0] = True
    io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    draw(gui, io, storage)

    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    painter = draw(gui, io, storage)
    assert actions == ["remove"]
    assert "Remove row" not in painter.strings
