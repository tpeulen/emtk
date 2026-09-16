"""emtk's virtualised list and tree: only the visible rows are ever asked for.

Every list in the chrome was written twice -- the object panel lays out a rect
per row per frame and cannot scroll at all, the hierarchy re-slices its visible
nodes on a hover repaint, and the file dialog, the history panel and the
settings window each carry their own thumb arithmetic and their own answer to
"which row is under the cursor". `ListView`/`TreeView` are the one copy, and
the property that matters for the structures this viewer is meant to open is
virtualisation: a hundred thousand rows must cost what twenty cost.

These run against the recording painter, with no viewer and no window: emtk is
a standalone toolkit and its widgets are testable as one.
"""
from __future__ import annotations

import pytest

from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.keys import KEY_DOWN, KEY_END, KEY_HOME, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.router import Capture, Consumed, Event, Pass
from emtk.testing import RecordingPainter
from emtk.widgets.list_view import ListRows, ListView, Row, TreeItem, TreeRows, TreeView


class _CountingRows(ListRows):
    """A model that records which rows the view asked it for."""

    def __init__(self, count):
        super().__init__(f"row {i}" for i in range(count))
        self.asked: list[int] = []

    def row(self, index):
        self.asked.append(index)
        return super().row(index)


@pytest.fixture
def painter():
    return RecordingPainter()


def _list(count=100, **kw):
    model = _CountingRows(count)
    return model, ListView(model, row_height=15.0, **kw)


# -- virtualisation ------------------------------------------------------- #


def test_only_the_rows_on_screen_are_asked_for(painter):
    model, view = _list(100_000)
    view.draw(painter, 0, 0, 200, 90)
    # Six whole rows fit in ninety pixels, plus the one straddling the bottom.
    assert model.asked == list(range(0, 7))
    assert len(painter.strings) == 7


def test_scrolling_asks_for_the_rows_that_scrolled_into_view(painter):
    model, view = _list(1000)
    view.draw(painter, 0, 0, 200, 90)
    model.asked.clear()
    view.wheel(-1)                      # one notch down: three rows
    view.draw(painter, 0, 0, 200, 90)
    assert model.asked == list(range(3, 10))


def test_a_short_list_draws_no_scrollbar(painter):
    model, view = _list(3)
    view.draw(painter, 0, 0, 200, 90)
    assert not view.scrollbar.needed()


def test_the_wheel_is_consumed_even_at_the_end_of_the_list():
    """Or the notch scrolls whatever is behind the panel being read."""
    _model, view = _list(4)
    assert view.event(Event("wheel", 10, 10, wheel_dy=-1)) is Consumed


# -- hit testing and selection -------------------------------------------- #


def test_the_row_under_the_pointer_accounts_for_the_scroll(painter):
    _model, view = _list(100)
    view.draw(painter, 10, 20, 200, 90)
    assert view.row_at(50, 20) == 0
    assert view.row_at(50, 20 + 15 * 3 + 1) == 3
    view.wheel(-1)
    assert view.row_at(50, 20) == 3          # three rows scrolled past
    assert view.row_at(50, 500) is None      # off the bottom
    assert view.row_at(500, 25) is None      # off the side


def test_a_click_selects_and_the_press_captures(painter):
    _model, view = _list(100)
    view.draw(painter, 0, 0, 200, 90)
    verdict = view.event(Event("press", 10, 16, button=1))
    assert isinstance(verdict, Capture) and verdict.handler is view
    assert view.selection.selection() == [1]


def test_shift_extends_only_when_multi_select_is_on(painter):
    _model, single = _list(100)
    single.draw(painter, 0, 0, 200, 90)
    single.event(Event("press", 10, 1, button=1))
    single.event(Event("press", 10, 46, button=1, modifiers=SHIFT_MODIFIER))
    assert single.selection.selection() == [3]

    _model, multi = _list(100, multi_select=True)
    multi.draw(painter, 0, 0, 200, 90)
    multi.event(Event("press", 10, 1, button=1))
    multi.event(Event("press", 10, 46, button=1, modifiers=SHIFT_MODIFIER))
    assert multi.selection.selection() == [0, 1, 2, 3]

    multi.event(Event("press", 10, 76, button=1, modifiers=CONTROL_MODIFIER))
    assert multi.selection.selection() == [0, 1, 2, 3, 5]


def test_a_double_click_activates(painter):
    opened: list[int] = []
    model = ListRows(["a", "b", "c"])
    view = ListView(model, row_height=15.0, on_activate=opened.append)
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 10, 16, button=1, clicks=2))
    assert opened == [1]


def test_a_press_outside_the_box_is_not_the_lists(painter):
    _model, view = _list(10)
    view.draw(painter, 0, 0, 200, 90)
    assert view.event(Event("press", 400, 400, button=1)) is Pass


def test_an_unselectable_row_takes_the_click_without_selecting(painter):
    model = ListRows([Row("heading", selectable=False), Row("item")])
    view = ListView(model, row_height=15.0)
    view.draw(painter, 0, 0, 200, 90)
    assert view.event(Event("press", 10, 1, button=1)) is Consumed
    assert view.selection.selection() == []


# -- the thumb is a capture, not a sixth `_held` flag ---------------------- #


def test_the_thumb_drag_captures_and_the_release_lets_go(painter):
    _model, view = _list(1000)
    view.draw(painter, 0, 0, 200, 90)
    bar_x = 200 - view.scrollbar.width + 1
    verdict = view.event(Event("press", bar_x, 45, button=1))
    assert isinstance(verdict, Capture)
    assert view.scrollbar.held
    view.event(Event("move", bar_x, 90, buttons=1))
    assert view.scrollbar.top > 0
    view.event(Event("release", bar_x, 90, button=1))
    assert not view.scrollbar.held


def test_a_cancel_lets_go_of_the_thumb(painter):
    """The router's answer to a press that lost its release."""
    _model, view = _list(1000)
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 200 - view.scrollbar.width + 1, 45, button=1))
    view.event(Event("cancel"))
    assert not view.scrollbar.held


# -- keyboard -------------------------------------------------------------- #


def test_the_arrows_move_the_selection_and_scroll_it_into_view(painter):
    _model, view = _list(100)
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 10, 1, button=1))
    for _ in range(10):
        view.event(Event("key_press", key=KEY_DOWN))
    assert view.selection.selection() == [10]
    assert view.scrollbar.top == 5           # row 10 is the last visible one
    view.event(Event("key_press", key=KEY_HOME))
    assert view.selection.selection() == [0] and view.scrollbar.top == 0
    view.event(Event("key_press", key=KEY_END))
    assert view.selection.selection() == [99]
    view.event(Event("key_press", key=KEY_UP))
    assert view.selection.selection() == [98]


# -- trees ----------------------------------------------------------------- #


def _tree():
    return TreeRows([
        TreeItem("a", "Alpha", children=[TreeItem("a1", "one"), TreeItem("a2", "two")]),
        TreeItem("b", "Beta"),
    ])


def test_a_closed_tree_is_its_roots(painter):
    model = _tree()
    assert model.row_count() == 2
    assert [model.row(i).text for i in range(2)] == ["Alpha", "Beta"]
    assert model.row(0).twisty == "▸" and model.row(1).twisty == ""


def test_the_twisty_expands_and_the_label_selects(painter):
    model = _tree()
    view = TreeView(model, row_height=15.0)
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 6, 1, button=1))          # on the twisty
    assert model.row_count() == 4
    assert view.selection.selection() == []             # expanding is not selecting
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 60, 1, button=1))         # on the label
    assert view.selection.selection() == [0]
    assert model.row_count() == 4                       # and it stayed open


def test_children_are_indented_and_the_flattening_is_cached(painter):
    model = _tree()
    model.toggle("a")
    assert [model.row(i).indent for i in range(4)] == [0, 1, 1, 0]
    before = model._flatten()
    assert model._flatten() is before                   # no re-walk without a change
    model.toggle("a")
    assert model._flatten() is not before


def test_left_and_right_close_and_open_the_selected_node(painter):
    model = _tree()
    view = TreeView(model, row_height=15.0)
    view.draw(painter, 0, 0, 200, 90)
    view.event(Event("press", 60, 1, button=1))
    view.event(Event("key_press", key=KEY_RIGHT))
    assert model.row_count() == 4
    view.event(Event("key_press", key=KEY_LEFT))
    assert model.row_count() == 2


def test_a_deep_tree_still_only_draws_what_fits(painter):
    """The hierarchy of a large structure is the reason this class exists."""
    roots = [TreeItem(f"c{i}", f"chain {i}",
                      children=[TreeItem(f"c{i}r{j}", f"res {j}") for j in range(5000)])
             for i in range(50)]
    model = TreeRows(roots, expanded={f"c{i}" for i in range(50)})
    view = TreeView(model, row_height=15.0)
    assert model.row_count() == 50 + 50 * 5000
    view.draw(painter, 0, 0, 200, 90)
    assert len(painter.strings) <= 7 * 2       # a label, and at most a twisty, each
