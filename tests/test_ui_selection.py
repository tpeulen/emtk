"""Painter-level tests for the selection controls.

Behaviour, not pixels: what a click plus its modifiers does to the selection,
which end of a range the anchor sits at, whether a disabled row refuses its
click, and whether a closed header takes its body with it.
"""

from __future__ import annotations

import pytest

from cmtk.widgets import selection


class RecordingPainter:
    """Records the six operations instead of performing them."""

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[str] = []
        self.clips: list[tuple] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.fills.append((x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        self.strokes.append((x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        self.fills.append((x, y, w, h, stops[0] if stops else None))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)

    def push_clip(self, x, y, w, h) -> None:
        self.clips.append((x, y, w, h))

    def pop_clip(self) -> None:
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


#: Row pitch a :class:`SelectableList` uses with the recording painter's
#: 12-pixel line height and the default row scale.
ROW_H = 12.0 * 1.15

ALL = [
    lambda: selection.Selectable("row", selected=True),
    lambda: selection.CollapsingHeader("head", expanded=True, closable=True,
                                       children=["a", "b"]),
    lambda: selection.SelectableList(["a", "b", "c"]),
    lambda: _typed(selection.TypingSelect(), "ab"),
]


def _typed(typing: selection.TypingSelect, text: str) -> selection.TypingSelect:
    """Feed a buffer into a :class:`TypingSelect` so it has something to draw."""
    for index, ch in enumerate(text):
        typing.type_char(ch, ["alpha", "beta"], now=index * 0.1)
    return typing


def _list_at(items, x=0.0, y=0.0, w=200.0, h=None, **kwargs):
    """A drawn :class:`SelectableList` plus the box it was drawn into."""
    box_h = h if h is not None else ROW_H * len(items)
    widget = selection.SelectableList(items, **kwargs)
    widget.draw(RecordingPainter(), x, y, w, box_h)
    return widget, (x, y, w, box_h)


def _click(widget, box, row, **mods):
    """Click the middle of a row of a drawn list."""
    x, y, w, h = box
    return widget.press(x + 5.0, y + row * ROW_H + ROW_H * 0.5, x, y, w, h, **mods)


# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


def test_plain_click_replaces_the_whole_selection():
    """A click without modifiers drops everything else."""
    widget, box = _list_at(["a", "b", "c", "d"])
    _click(widget, box, 0)
    _click(widget, box, 2, ctrl=True)
    assert widget.selection() == [0, 2]

    _click(widget, box, 3)
    assert widget.selection() == [3]


def test_ctrl_click_toggles_exactly_one_row():
    """Ctrl adds, ctrl again removes, and the neighbours never move."""
    widget, box = _list_at(["a", "b", "c", "d"])
    _click(widget, box, 1)
    _click(widget, box, 3, ctrl=True)
    assert widget.selection() == [1, 3]

    _click(widget, box, 1, ctrl=True)
    assert widget.selection() == [3]


def test_shift_click_extends_a_range_downwards_from_the_anchor():
    """The anchor is the plain-clicked row, not the shift-clicked one."""
    widget, box = _list_at(["a", "b", "c", "d", "e"])
    _click(widget, box, 1)
    _click(widget, box, 3, shift=True)
    assert widget.selection() == [1, 2, 3]
    assert widget.state.anchor == 1
    assert widget.state.direction == 1


def test_shift_click_above_the_anchor_extends_upwards():
    """The direction a naive port gets wrong: clicking *before* the anchor.

    An implementation that treats the anchor as the low end of the range selects
    nothing here, and every downward test still passes.
    """
    widget, box = _list_at(["a", "b", "c", "d", "e"])
    _click(widget, box, 3)
    _click(widget, box, 1, shift=True)
    assert widget.selection() == [1, 2, 3]
    assert widget.state.anchor == 3
    assert widget.state.direction == -1


def test_second_shift_click_re_extends_from_the_same_anchor():
    """Shift-clicking never moves the anchor, so the range shrinks back."""
    state = selection.MultiSelectState(6)
    state.click(2)
    state.click(5, shift=True)
    assert state.selection() == [2, 3, 4, 5]

    state.click(0, shift=True)
    assert state.selection() == [0, 1, 2]
    assert state.anchor == 2


def test_ctrl_shift_extends_without_clearing_and_copies_the_anchor_state():
    """Ctrl+shift keeps what was selected and applies the anchor's own state."""
    state = selection.MultiSelectState(8)
    state.click(6)
    state.click(1, ctrl=True)
    state.click(3, ctrl=True, shift=True)
    assert state.selection() == [1, 2, 3, 6]

    # Anchor de-selected by a ctrl-click: extending from it now de-selects.
    state.click(1, ctrl=True)
    assert state.anchor == 1 and state.range_selected is False
    state.click(3, ctrl=True, shift=True)
    assert state.selection() == [6]


def test_single_select_never_holds_two_rows():
    """The reference's SingleSelect flag: shift does not extend either."""
    widget, box = _list_at(["a", "b", "c"], multi_select=False)
    _click(widget, box, 0)
    _click(widget, box, 2, ctrl=True)
    assert widget.selection() == [2]

    _click(widget, box, 0, shift=True)
    assert widget.selection() == [0]


def test_a_disabled_selectable_refuses_its_click():
    """Dimmed and inert -- the press is not reported and nothing is selected."""
    row = selection.Selectable("nope", flags=selection.SELECTABLE_DISABLED)
    assert row.press(10.0, 5.0, 0.0, 0.0, 100.0, 18.0) is False

    widget, box = _list_at(["a", "b", "c"], disabled=[1])
    assert _click(widget, box, 1) is None
    assert widget.selection() == []
    assert _click(widget, box, 2) == 2
    assert widget.selection() == [2]


def test_a_disabled_selectable_draws_dimmed():
    """Its caption uses the disabled colour, and its highlight is halved."""
    painter = RecordingPainter()
    row = selection.Selectable("nope", selected=True,
                               flags=selection.SELECTABLE_DISABLED)
    row.draw(painter, 0.0, 0.0, 100.0, 18.0)
    assert painter.fills[0][4][3] == selection.style.HEADER[3] // 2


def test_double_click_is_reported_only_when_the_flag_asks_for_it():
    """AllowDoubleClick is the flag that turns the second click into a press."""
    plain = selection.Selectable("plain")
    assert plain.press(5.0, 5.0, 0.0, 0.0, 100.0, 18.0, double=True) is False

    keen = selection.Selectable("keen", flags=selection.SELECTABLE_ALLOW_DOUBLE_CLICK)
    assert keen.press(5.0, 5.0, 0.0, 0.0, 100.0, 18.0, double=True) is True
    assert keen.double_clicked is True


def test_dont_close_popups_is_reported_per_row():
    """A row says whether pressing it should close the popup it sits in."""
    assert selection.Selectable("ordinary").closes_popup is True
    assert selection.Selectable(
        "keeps it open", flags=selection.SELECTABLE_DONT_CLOSE_POPUPS
    ).closes_popup is False


def test_span_all_columns_widens_the_frame_and_the_hit_test():
    """The highlight covers the row the container set, not just the item's box."""
    painter = RecordingPainter()
    row = selection.Selectable("wide", selected=True,
                               flags=selection.SELECTABLE_SPAN_ALL_COLUMNS)
    row.span = (0.0, 300.0)
    row.draw(painter, 100.0, 0.0, 50.0, 18.0)
    assert painter.fills[0][0] == 0.0 and painter.fills[0][2] == 300.0
    # A press left of the item's own box still lands on it.
    assert row.press(10.0, 5.0, 100.0, 0.0, 50.0, 18.0) is True


def test_collapsing_header_toggles_and_draws_its_body():
    """A framed header is a tree node: clicking the bar opens and closes it."""
    head = selection.CollapsingHeader("Atoms", children=["C", "N"])
    assert head.press(10.0, 5.0, 0.0, 0.0, 200.0, 18.0) is True
    assert head.expanded is True

    painter = RecordingPainter()
    head.draw_body(painter, 0.0, 18.0, 200.0, 24.0)
    assert painter.strings == ["C", "N"]
    assert painter.clips == []

    assert head.press(10.0, 5.0, 0.0, 0.0, 200.0, 18.0) is False
    assert head.expanded is False


def test_collapsing_header_close_button_reports_not_visible():
    """The close button is p_visible, not a second open state.

    It does not toggle the header, it removes it: the bar stops drawing and so
    does the body, even though the header is still *expanded*.
    """
    head = selection.CollapsingHeader("Atoms", expanded=True, closable=True,
                                      children=["C", "N"])
    box = (0.0, 0.0, 200.0, 18.0)
    btn_x, btn_y, btn_w, btn_h = head.close_box(*box)

    assert head.press(btn_x + btn_w * 0.5, btn_y + btn_h * 0.5, *box) is False
    assert head.visible is False
    assert head.expanded is True
    assert head.body_visible is False

    painter = RecordingPainter()
    head.draw(painter, 0.0, 0.0, 200.0, 18.0)
    head.draw_body(painter, 0.0, 18.0, 200.0, 24.0)
    assert painter.fills == [] and painter.strokes == [] and painter.strings == []
    assert painter.clips == []


def test_a_closable_header_still_toggles_when_the_bar_is_clicked():
    """The button owns its own rectangle and nothing more."""
    head = selection.CollapsingHeader("Atoms", closable=True)
    assert head.press(10.0, 9.0, 0.0, 0.0, 200.0, 18.0) is True
    assert head.visible is True and head.expanded is True


def test_type_ahead_matches_a_multi_character_buffer():
    """Two different characters search for a prefix, not for the second letter."""
    items = ["Apple", "Banana", "Blueberry", "Blade"]
    typing = selection.TypingSelect()
    assert typing.type_char("b", items, now=0.0) == 1
    assert typing.type_char("l", items, now=0.1, current=1) == 2
    assert typing.buffer == "bl"
    assert typing.single_char_mode is False


def test_repeating_one_character_cycles_instead_of_searching():
    """"b, b, b" means "next thing starting with b", and it wraps."""
    items = ["Apple", "Banana", "Blueberry", "Blade"]
    typing = selection.TypingSelect()
    assert typing.type_char("b", items, now=0.0) == 1
    assert typing.type_char("b", items, now=0.1, current=1) == 2
    assert typing.type_char("b", items, now=0.2, current=2) == 3
    assert typing.type_char("b", items, now=0.3, current=3) == 1
    assert typing.single_char_mode is True
    # Four repeats lock the mode, and the buffer then stops growing.
    assert typing.single_char_lock is True
    typing.type_char("b", items, now=0.4, current=1)
    assert typing.buffer == "bbbb"


def test_type_ahead_forgets_its_buffer_after_the_timeout():
    """Silence past the reset timer starts a fresh search."""
    items = ["Apple", "Banana", "Blueberry"]
    typing = selection.TypingSelect(timeout=1.8)
    typing.type_char("b", items, now=0.0)
    typing.type_char("l", items, now=0.1)
    assert typing.buffer == "bl"

    assert typing.type_char("a", items, now=10.0) == 0
    assert typing.buffer == "a"


def test_type_ahead_is_case_blind_and_reports_no_match():
    """Matching ignores case; a character nothing starts with returns None."""
    items = ["Apple", "Banana"]
    typing = selection.TypingSelect()
    assert typing.type_char("A", items, now=0.0) == 0
    typing.reset()
    assert typing.type_char("z", items, now=1.0) is None


def test_list_type_ahead_selects_and_scrolls_the_row_into_view():
    """Typing in the list moves the selection, not just the search."""
    items = [f"a{i}" for i in range(6)] + ["zebra"]
    widget, _box = _list_at(items, h=ROW_H * 3)
    assert widget.type_char("z", now=0.0) == 6
    assert widget.selection() == [6]
    assert widget.bar.top == 4


def test_the_list_scrolls_and_clicks_the_row_that_is_actually_showing():
    """The row index a press reports comes from the scrolled window."""
    items = [f"r{i}" for i in range(10)]
    widget, box = _list_at(items, h=ROW_H * 4)
    widget.scroll(3)
    assert _click(widget, box, 1) == 4
    assert widget.selection() == [4]


def test_set_items_drops_a_selection_that_no_longer_exists():
    """A shorter list cannot keep selecting rows that are gone."""
    widget, box = _list_at(["a", "b", "c", "d"])
    _click(widget, box, 3)
    assert widget.selection() == [3]

    widget.set_items(["a", "b"])
    assert widget.selection() == []
    assert widget.state.anchor is None
