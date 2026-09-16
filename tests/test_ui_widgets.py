"""Painter-level tests for the shared ImGui-style controls.

These need no GUI toolkit at all -- that is the point of the painter seam, and
a control that quietly grows a Qt dependency fails here first.
"""

from __future__ import annotations

import pytest

from emtk.widgets import basic as widgets


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


ALL = [
    lambda: widgets.SliderFloat("v", 0.0, 1.0, 0.5, fmt="%.0%"),
    lambda: widgets.ColorEdit4("c", (200, 40, 40, 255)),
    lambda: widgets.Table(["a", "b"], [["1", "2"]]),
    lambda: widgets.Checkbox("c", True),
    lambda: widgets.Combo("c", ["x", "y"]),
    lambda: widgets.Button("b"),
    lambda: widgets.ProgressBar("p", 0.25),
    lambda: widgets.TreeNode("t", True, ["child"]),
    lambda: widgets.Separator("group"),
    lambda: widgets.Toggle("t", True),
    lambda: widgets.RadioGroup("r", ["one", "two"], 1),
    lambda: widgets.InputInt("i", 2, 0, 5),
    lambda: widgets.ListBox("l", ["a", "b", "c"], 1, visible_rows=2),
    lambda: widgets.Tabs(["A", "B"], 1),
    lambda: widgets.PlotLines("p", [1.0, 3.0, 2.0]),
    lambda: widgets.Histogram("h", [1.0, 3.0, 2.0]),
    lambda: widgets.Tooltip(["one", "two"]),
    lambda: widgets.TextInput("t", "abc"),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


def test_percentage_format_does_not_raise():
    """``"%.0%"`` is a percentage here; printf would call it a ValueError."""
    assert widgets._format("%.0%", 0.5) == "50%"
    assert widgets._format("%.1%", 0.125) == "12.5%"
    assert widgets._format("%.1f tiles", 4.5) == "4.5 tiles"
    assert widgets._format("%.2f", 1.0) == "1.00"
    # An unusable spec falls back rather than taking the frame down with it.
    assert widgets._format("%(missing)s", 1.0) == "1.00"


def test_slider_set_fraction_matches_the_drawn_track():
    slider = widgets.SliderFloat("v", 10.0, 20.0, 10.0)
    assert slider.set_fraction(0.5) == pytest.approx(15.0)
    assert slider.fraction == pytest.approx(0.5)
    assert slider.set_fraction(9.0) == pytest.approx(20.0)


def test_list_box_press_selects_the_visible_row():
    box = widgets.ListBox("", [f"r{i}" for i in range(6)], index=5, visible_rows=3)
    # Window is showing rows 3..5; the middle one is row 4.
    assert box.press(5.0, 15.0, 0.0, 0.0, 100.0, 30.0) == 4
    assert box.value == "r4"


def test_tabs_press_returns_the_tab_under_the_point():
    tabs = widgets.Tabs(["A", "B", "C", "D"])
    assert tabs.press(85.0, 5.0, 0.0, 0.0, 100.0, 10.0) == 3
    assert tabs.value == "D"


def test_text_input_holds_a_text_field():
    field = widgets.TextInput("name", "ab")
    assert field.text == "ab"
    field.move(-1)
    assert field.insert("X") == "aXb"
    assert field.backspace() == "ab"


def test_a_table_scrolls_rather_than_dropping_its_tail():
    """Rows past the bottom are reachable, not simply undrawn."""
    painter = RecordingPainter()
    table = widgets.Table(["n"], [[str(i)] for i in range(40)])
    # 12 line-heights of room, one used by the header.
    table.draw(painter, 0.0, 0.0, 100.0, 12 * painter.line_height())
    assert table.bar.needed()
    drawn = [s for s in painter.strings if s.isdigit()]
    assert drawn[0] == "0" and len(drawn) < 40

    table.scroll(1000)          # all the way down
    painter.strings.clear()
    table.draw(painter, 0.0, 0.0, 100.0, 12 * painter.line_height())
    drawn = [s for s in painter.strings if s.isdigit()]
    assert drawn[-1] == "39", "the last row must be reachable"


def test_a_table_press_hits_the_row_that_was_drawn():
    """The hit test uses the pitch the draw used, not a hard-coded one."""
    painter = RecordingPainter()
    table = widgets.Table(["n"], [[str(i)] for i in range(40)])
    height = 12 * painter.line_height()
    table.draw(painter, 0.0, 0.0, 100.0, height)
    row_h = painter.line_height() * table.row_scale
    header_h = row_h * 1.1

    assert table.press(10.0, header_h + row_h * 2.5, 0.0, 0.0, 100.0, height) == ("row", 2)
    table.scroll(10)
    table.draw(painter, 0.0, 0.0, 100.0, height)
    # The same point now names the row that is *there*, ten further down.
    assert table.press(10.0, header_h + row_h * 2.5, 0.0, 0.0, 100.0, height) == ("row", 12)


def test_a_table_header_press_sorts_the_column_it_hit():
    painter = RecordingPainter()
    table = widgets.Table(["a", "b"], [["2", "x"], ["1", "y"]])
    table.draw(painter, 0.0, 0.0, 100.0, 100.0)
    assert table.press(60.0, 2.0, 0.0, 0.0, 100.0, 100.0) == ("header", 1)
    assert table.sort_col == 1


def test_the_scrollbar_is_one_implementation():
    """Every scrolling panel shares it, so they cannot disagree on the last row."""
    bar = widgets.ScrollBar()
    bar.clamp(total=40, visible=10)
    assert bar.needed()
    bar.scroll(100)
    assert bar.top == 30, "cannot scroll past the last full window"
    bar.scroll(-100)
    assert bar.top == 0
    bar.clamp(total=3, visible=10)
    assert not bar.needed() and bar.top == 0
