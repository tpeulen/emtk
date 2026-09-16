"""Painter-level tests for the measured tab strip.

No GUI toolkit is involved -- that is the point of the painter seam, and a
control that quietly grows a Qt dependency fails here first.

Each test names the behaviour that separates :class:`TabBar` from the
equal-slice ``widgets.Tabs`` it is meant to replace: a tab measured from its
label, width taken off the widest tab first, a drag that reorders, a close
button that reports which tab it closed, a button that never becomes current,
and a scrolled strip that always shows the current tab.
"""

from __future__ import annotations

import pytest

from emtk.widgets import tabs


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


BAR_H = 18.0


def _bar(labels, flags=tabs.TAB_BAR_NONE, **kwargs):
    """Build a strip of plain tabs from a list of captions."""
    return tabs.TabBar([tabs.TabItem(one, **kwargs) for one in labels], flags=flags)


# ---------------------------------------------------------------------- #
# Smoke
# ---------------------------------------------------------------------- #
def test_the_strip_paints_and_balances_its_clips():
    """It draws something, and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    bar = tabs.TabBar(
        [
            tabs.TabItem("Alpha", closable=True),
            tabs.TabItem("Beta", modified=True, closable=True),
            tabs.TabItem("Gamma", disabled=True),
            tabs.TabItemButton("+"),
        ],
        flags=tabs.TAB_BAR_REORDERABLE | tabs.TAB_BAR_TAB_LIST_POPUP_BUTTON,
    )
    bar.popup_open = True
    bar.draw(painter, 0.0, 0.0, 300.0, BAR_H)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []
    assert bar.value == "Alpha"


# ---------------------------------------------------------------------- #
# Measured widths -- the thing an equal-slice strip cannot do
# ---------------------------------------------------------------------- #
def test_a_long_label_gets_a_wider_tab_than_a_short_one():
    """Width comes from the label, not from the number of tabs."""
    painter = RecordingPainter()
    bar = _bar(["I", "A much longer caption"])
    laid = bar.layout(painter, 0.0, 0.0, 600.0, BAR_H)
    short_w, long_w = laid[0][2], laid[1][2]
    assert long_w > short_w
    # And they are laid end to end rather than sliced: the second starts after
    # the first, not at half the box.
    assert laid[1][1] == pytest.approx(laid[0][1] + short_w + tabs.TAB_SPACING)
    assert laid[0][1] + short_w < 300.0


def test_a_close_button_makes_its_tab_wider_and_a_pathological_label_cannot_own_the_strip():
    """Room for the ✕ is measured in, and one caption is capped."""
    painter = RecordingPainter()
    plain = tabs.TabItem("doc")
    closable = tabs.TabItem("doc", closable=True)
    assert closable.content_width(painter) > plain.content_width(painter)
    huge = tabs.TabItem("x" * 400)
    assert huge.content_width(painter) == pytest.approx(
        painter.line_height() * tabs.MAX_TAB_WIDTH_EM
    )


# ---------------------------------------------------------------------- #
# The shrink policy
# ---------------------------------------------------------------------- #
def test_shrink_takes_width_from_the_widest_tab_not_from_everybody():
    """Uniform scaling and the reference's policy disagree; this is the latter.

    Three tabs of 20, 20 and 153 pixels have 51 pixels too many. Scaling them
    all by ``150/201`` would give roughly 15, 15 and 114 -- it makes the two
    already-short tabs shorter to spare the long one. The reference takes the
    excess off the widest first, so the short tabs are untouched.
    """
    out = tabs.shrink_widths([20.0, 20.0, 153.0], 51.0)
    assert out == [20.0, 20.0, 102.0]
    # The uniform answer, for contrast, is not what we got.
    uniform = [w * (142.0 / 193.0) for w in (20.0, 20.0, 153.0)]
    assert out[0] != pytest.approx(uniform[0], abs=0.5)


def test_shrink_levels_the_widest_tabs_down_together_once_they_match():
    """Past the point where the leaders meet, they shrink as a group."""
    # 100, 100, 20: 60 too many. The two leaders are already level, so they
    # share the excess -- 30 each -- and the short one is never touched,
    # because they never come down as far as its 20.
    assert tabs.shrink_widths([100.0, 100.0, 20.0], 60.0) == [70.0, 70.0, 20.0]
    # Take enough and they do reach it, and then all three shrink together.
    assert tabs.shrink_widths([100.0, 100.0, 20.0], 190.0) == [10.0, 10.0, 10.0]


def test_shrink_never_goes_below_the_floor():
    """A hopeless strip clamps rather than producing negative tabs."""
    out = tabs.shrink_widths([30.0, 30.0], 500.0, width_min=4.0)
    assert out == [4.0, 4.0]


def test_the_strip_shrinks_the_widest_tab_when_the_box_is_too_small():
    """The policy reaches the laid-out strip, not just the helper."""
    painter = RecordingPainter()
    # "A" and "B" measure 20 each; the long one measures 153.
    bar = _bar(["A", "B", "L" * 20])
    wide = {item.label: w for item, _, w in bar.layout(painter, 0.0, 0.0, 600.0, BAR_H)}
    assert (wide["A"], wide["B"], wide["L" * 20]) == (20.0, 20.0, 153.0)
    tight = {item.label: w for item, _, w in bar.layout(painter, 0.0, 0.0, 150.0, BAR_H)}
    assert tight["A"] == 20.0 and tight["B"] == 20.0
    assert tight["L" * 20] == 102.0
    assert sum(tight.values()) + 2 * tabs.TAB_SPACING == pytest.approx(150.0)


def test_the_scroll_policy_does_not_shrink_anything():
    """Under FittingPolicyScroll the tabs keep the width they measured."""
    painter = RecordingPainter()
    bar = _bar(["A", "B", "L" * 20], flags=tabs.TAB_BAR_FITTING_POLICY_SCROLL)
    laid = bar.layout(painter, 0.0, 0.0, 150.0, BAR_H)
    assert [w for _, _, w in laid] == [20.0, 20.0, 153.0]


# ---------------------------------------------------------------------- #
# Reordering
# ---------------------------------------------------------------------- #
def test_dragging_a_tab_past_its_neighbour_swaps_them_and_dragging_back_restores():
    """The order follows the pointer, and comes back when it does."""
    painter = RecordingPainter()
    bar = _bar(["one", "two", "three"], flags=tabs.TAB_BAR_REORDERABLE)
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    assert bar.labels == ["one", "two", "three"]

    positions = {item.label: (x, w) for item, x, w in bar._geometry}
    two_x, _ = positions["two"]
    three_x, three_w = positions["three"]

    assert bar.press(two_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H).action == "select"
    assert bar.drag(three_x + three_w * 0.5, 6.0, 0.0, 0.0, 400.0, BAR_H) is True
    assert bar.labels == ["one", "three", "two"]

    # The strip has to be re-laid before the next crossing is measured, exactly
    # as a real frame would: the boxes moved. Dragging back over the neighbour
    # it just passed puts it where it started.
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    positions = {item.label: (x, w) for item, x, w in bar._geometry}
    three_x, three_w = positions["three"]
    assert bar.drag(three_x + three_w * 0.5, 6.0, 0.0, 0.0, 400.0, BAR_H) is True
    assert bar.labels == ["one", "two", "three"]

    # Dragged the whole way to the left it lands at the front, crossing both.
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    one_x, _ = [(x, w) for it, x, w in bar._geometry if it.label == "one"][0]
    assert bar.drag(one_x + 1.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is True
    assert bar.labels == ["two", "one", "three"]

    bar.release()
    assert bar.drag(10.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is False


def test_a_drag_that_has_not_left_its_own_tab_moves_nothing():
    """The crossing test is a crossing, not any movement at all."""
    painter = RecordingPainter()
    bar = _bar(["one", "two", "three"], flags=tabs.TAB_BAR_REORDERABLE)
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item_x, item_w = [(x, w) for it, x, w in bar._geometry if it.label == "two"][0]
    bar.press(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert bar.drag(item_x + item_w - 1.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is False
    assert bar.labels == ["one", "two", "three"]


def test_a_bar_that_is_not_reorderable_never_reorders():
    """Without the flag a drag is just a drag."""
    painter = RecordingPainter()
    bar = _bar(["one", "two", "three"])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item_x, _ = [(x, w) for it, x, w in bar._geometry if it.label == "two"][0]
    bar.press(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert bar.drag(390.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is False
    assert bar.labels == ["one", "two", "three"]


# ---------------------------------------------------------------------- #
# Closing
# ---------------------------------------------------------------------- #
def test_the_close_button_reports_its_own_tab_and_the_label_does_not_close():
    """Which half of the tab was pressed decides what the press means."""
    painter = RecordingPainter()
    bar = tabs.TabBar([tabs.TabItem(name, closable=True) for name in ("a", "b", "c")])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    middle, middle_x, middle_w = bar._geometry[1]

    # The left of the tab is the label: it selects.
    pressed = bar.press(middle_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert pressed.action == "select" and pressed.item is middle
    assert bar.labels == ["a", "b", "c"]

    # The right of the tab is the ✕: it closes, and says which one.
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    middle, middle_x, middle_w = bar._geometry[1]
    pressed = bar.press(middle_x + middle_w - 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert pressed.action == "close"
    assert pressed.item is middle and pressed.index == 1
    assert bar.labels == ["a", "c"]


def test_closing_the_current_tab_falls_back_to_the_one_used_before_it():
    """Not "the tab on the left" -- the tab you came from."""
    painter = RecordingPainter()
    bar = tabs.TabBar([tabs.TabItem(name, closable=True) for name in ("a", "b", "c")])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    bar.select(2)          # c
    bar.select(0)          # a, most recently before...
    bar.select(1)          # ...b
    bar.close(bar.items[1])
    assert bar.value == "a"


def test_a_tab_with_no_close_button_is_selected_by_a_press_anywhere_on_it():
    """A plain tab has no ✕ region to lose its right-hand edge to."""
    painter = RecordingPainter()
    bar = _bar(["alpha", "beta"])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item, item_x, item_w = bar._geometry[1]
    pressed = bar.press(item_x + item_w - 1.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert pressed.action == "select" and pressed.item is item
    assert bar.labels == ["alpha", "beta"]


def test_the_middle_button_closes_unless_the_flag_says_otherwise():
    """``NoCloseWithMiddleMouseButton`` is the flag, and it is honoured."""
    painter = RecordingPainter()
    bar = tabs.TabBar([tabs.TabItem(name, closable=True) for name in ("a", "b")])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item, item_x, _ = bar._geometry[0]
    assert bar.press(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H, button=2).action == "close"
    assert bar.labels == ["b"]

    guarded = tabs.TabBar(
        [tabs.TabItem(name, closable=True) for name in ("a", "b")],
        flags=tabs.TAB_BAR_NO_CLOSE_WITH_MIDDLE_MOUSE_BUTTON,
    )
    for one in guarded.items:
        one.no_close_with_middle_mouse = True
    guarded.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item, item_x, _ = guarded._geometry[0]
    assert guarded.press(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H, button=2) is None
    assert guarded.labels == ["a", "b"]


def test_a_shrunk_tab_gives_up_its_close_button_rather_than_its_label():
    """Below a certain width there is no ✕ to press, so the press selects."""
    painter = RecordingPainter()
    narrow = tabs.TabItem("doc", closable=True)
    assert narrow.close_button_box(painter, 0.0, 0.0, 120.0, BAR_H) is not None
    assert narrow.close_button_box(painter, 0.0, 0.0, 14.0, BAR_H) is None
    narrow.draw(painter, 0.0, 0.0, 14.0, BAR_H)
    assert narrow.press(6.0, 6.0, 0.0, 0.0, 14.0, BAR_H) == "select"


# ---------------------------------------------------------------------- #
# TabItemButton
# ---------------------------------------------------------------------- #
def test_a_tab_item_button_never_becomes_the_selected_tab():
    """It is pressed and reported, and the selection does not move."""
    painter = RecordingPainter()
    plus = tabs.TabItemButton("+")
    bar = tabs.TabBar([tabs.TabItem("a"), tabs.TabItem("b"), plus])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    bar.select(1)
    assert bar.value == "b"

    _, button_x, _ = bar._geometry[2]
    pressed = bar.press(button_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H)
    assert pressed.action == "button" and pressed.item is plus
    assert bar.value == "b"
    assert bar.selected is not plus

    # Nor by any other route into the selection.
    bar.select(2)
    assert bar.value == "b"
    bar.cycle(1)
    assert bar.value == "a"      # wraps past the button, not onto it
    assert bar.selected is not plus


def test_auto_select_new_tabs_is_a_flag_and_buttons_are_exempt():
    """A new tab takes the selection only when the bar asked for that."""
    quiet = tabs.TabBar([tabs.TabItem("a")])
    quiet.add("b")
    assert quiet.value == "a"

    eager = tabs.TabBar([tabs.TabItem("a")], flags=tabs.TAB_BAR_AUTO_SELECT_NEW_TABS)
    eager.add("b")
    assert eager.value == "b"
    eager.add(tabs.TabItemButton("+"))
    assert eager.value == "b"


# ---------------------------------------------------------------------- #
# Scrolling
# ---------------------------------------------------------------------- #
def test_with_the_scroll_policy_the_selected_tab_is_always_visible():
    """Whichever tab is current, the strip scrolls it into the visible extent."""
    painter = RecordingPainter()
    bar = _bar([f"document {n}" for n in range(9)],
               flags=tabs.TAB_BAR_FITTING_POLICY_SCROLL)
    box = (0.0, 0.0, 200.0, BAR_H)
    bar.draw(painter, *box)
    assert bar._scroll_enabled, "nine tabs in 200 px should need scrolling"

    for at in list(range(9)) + list(range(8, -1, -1)):
        bar.select(at)
        bar.draw(painter, *box)
        item, item_x, item_w = bar._geometry[at]
        vis_x, _, vis_w, _ = bar._visible
        assert item_x >= vis_x - 1e-6, f"tab {at} scrolled off the left"
        assert item_x + item_w <= vis_x + vis_w + 1e-6, f"tab {at} scrolled off the right"


def test_the_scrolling_arrows_step_the_selection():
    """The arrows select the neighbouring tab; the scroll follows it."""
    painter = RecordingPainter()
    bar = _bar([f"document {n}" for n in range(9)],
               flags=tabs.TAB_BAR_FITTING_POLICY_SCROLL)
    bar.draw(painter, 0.0, 0.0, 200.0, BAR_H)
    left_box, right_box = bar._scroll_boxes

    start = bar.index
    pressed = bar.press(right_box[0] + 1.0, 6.0, 0.0, 0.0, 200.0, BAR_H)
    assert pressed.action == "scroll"
    assert bar.index == start + 1
    bar.draw(painter, 0.0, 0.0, 200.0, BAR_H)
    left_box, right_box = bar._scroll_boxes
    bar.press(left_box[0] + 1.0, 6.0, 0.0, 0.0, 200.0, BAR_H)
    assert bar.index == start


def test_a_strip_that_fits_neither_scrolls_nor_grows_arrows():
    """The arrows and the scroll offset only appear when they are needed."""
    painter = RecordingPainter()
    bar = _bar(["a", "b"], flags=tabs.TAB_BAR_FITTING_POLICY_SCROLL)
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    assert bar._scroll_enabled is False
    assert bar._scroll_boxes is None
    assert bar.scroll == 0.0


# ---------------------------------------------------------------------- #
# The tab-list drop-down
# ---------------------------------------------------------------------- #
def test_the_tab_list_button_takes_its_width_out_of_the_strip():
    """That is the layout half of the flag, and the reason it is ported."""
    painter = RecordingPainter()
    plain = _bar(["a", "b"])
    with_button = _bar(["a", "b"], flags=tabs.TAB_BAR_TAB_LIST_POPUP_BUTTON)
    plain.layout(painter, 0.0, 0.0, 300.0, BAR_H)
    with_button.layout(painter, 0.0, 0.0, 300.0, BAR_H)
    assert with_button._visible[0] > plain._visible[0]
    assert with_button._visible[2] < plain._visible[2]
    assert with_button._geometry[0][1] > plain._geometry[0][1]


def test_the_tab_list_popup_selects_a_tab_from_outside_the_strip():
    """The drop-down opens, lists the tabs, and one of them can be picked."""
    painter = RecordingPainter()
    bar = _bar(["alpha", "beta", "gamma"], flags=tabs.TAB_BAR_TAB_LIST_POPUP_BUTTON)
    bar.draw(painter, 0.0, 0.0, 300.0, BAR_H)
    assert bar.press(2.0, 6.0, 0.0, 0.0, 300.0, BAR_H).action == "list"
    assert bar.popup_open is True

    bar.draw(painter, 0.0, 0.0, 300.0, BAR_H)
    assert painter.clips == []
    third = [row for row in bar._popup_rows if row[0].label == "gamma"][0]
    _, row_x, row_y, row_w, row_h = third
    pressed = bar.press(row_x + 2.0, row_y + row_h * 0.5, 0.0, 0.0, 300.0, BAR_H)
    assert pressed.action == "select" and bar.value == "gamma"
    assert bar.popup_open is False


# ---------------------------------------------------------------------- #
# Odds and ends
# ---------------------------------------------------------------------- #
def test_a_disabled_tab_swallows_its_press():
    """It is drawn, it is measured, and it cannot be selected."""
    painter = RecordingPainter()
    bar = tabs.TabBar([tabs.TabItem("a"), tabs.TabItem("b", disabled=True)])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    _, item_x, _ = bar._geometry[1]
    assert bar.press(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is None
    assert bar.value == "a"


def test_an_empty_strip_draws_nothing_and_answers_nothing():
    """No tabs is a state, not a crash."""
    painter = RecordingPainter()
    bar = tabs.TabBar([])
    bar.draw(painter, 0.0, 0.0, 200.0, BAR_H)
    assert painter.clips == []
    assert bar.value == "" and bar.index == -1
    assert bar.press(10.0, 6.0, 0.0, 0.0, 200.0, BAR_H) is None
    assert bar.cycle(1) == ""


def test_hover_follows_the_pointer_and_lets_go():
    """Hover state is what decides between the unsaved dot and the ✕."""
    painter = RecordingPainter()
    bar = _bar(["alpha", "beta"])
    bar.draw(painter, 0.0, 0.0, 400.0, BAR_H)
    item, item_x, _ = bar._geometry[1]
    assert bar.hover(item_x + 2.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is item
    assert item.hovered is True
    assert bar.hover(500.0, 6.0, 0.0, 0.0, 400.0, BAR_H) is None
    assert item.hovered is False
