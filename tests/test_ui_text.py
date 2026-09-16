"""Painter-level tests for the text family of controls.

Like the rest of the painter seam these need no GUI toolkit: the painter is a
recorder, and what is asserted is *where the six operations landed*, not that
nothing raised. A text control that draws nothing at all still passes a "it did
not crash" test, which is why almost none of these are that test.
"""

from __future__ import annotations

import pytest

from emtk import style
from emtk.widgets import text as uitext


class RecordingPainter:
    """Records the six operations instead of performing them.

    Copied from ``test_ui_widgets`` rather than imported -- a shared fixture
    module between test files is a dependency that makes one suite's failure
    look like the other's. The one addition is ``texts``: the text family is
    laid out horizontally, so *where* a string went is the whole assertion.
    """

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[str] = []
        self.texts: list[tuple] = []
        self.clips: list[tuple] = []
        self.clip_depth_max = 0

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.fills.append((x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        self.strokes.append((x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        self.fills.append((x, y, w, h, stops[0] if stops else None))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append(string)
        self.texts.append((x, y, w, h, string, colour))

    def push_clip(self, x, y, w, h) -> None:
        self.clips.append((x, y, w, h))
        self.clip_depth_max = max(self.clip_depth_max, len(self.clips))

    def pop_clip(self) -> None:
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


#: One character's width in :class:`RecordingPainter`.
CHAR = 7.0


ALL = [
    lambda: uitext.Text("plain"),
    lambda: uitext.TextColored((255, 0, 0), "red"),
    lambda: uitext.TextDisabled("greyed"),
    lambda: uitext.TextWrapped("a paragraph that will have to fold somewhere"),
    lambda: uitext.LabelText("label", "value"),
    lambda: uitext.BulletText("item"),
    lambda: uitext.Bullet(),
    lambda: uitext.SeparatorText("group"),
    lambda: uitext.TextLink("open"),
    lambda: uitext.Value("count", 3),
]


@pytest.mark.parametrize("build", ALL, ids=lambda b: type(b()).__name__)
def test_every_control_paints_and_balances_its_clips(build):
    """Every control draws something and leaves the clip stack as it found it."""
    painter = RecordingPainter()
    widget = build()
    widget.draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.fills or painter.strokes or painter.strings
    assert painter.clips == []


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------
def test_text_draws_one_call_per_line():
    """Embedded newlines become separate draws, stacked a line height apart."""
    painter = RecordingPainter()
    uitext.Text("one\ntwo\nthree").draw(painter, 10.0, 20.0, 100.0, 12.0)
    assert painter.strings == ["one", "two", "three"]
    assert [entry[1] for entry in painter.texts] == [20.0, 32.0, 44.0]


def test_text_does_not_hide_its_hash_suffix():
    """``Text`` shows the whole string; only *labels* hide what follows ``##``."""
    painter = RecordingPainter()
    uitext.Text("visible##hidden").draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert painter.strings == ["visible##hidden"]


def test_text_colored_and_disabled_differ_only_in_colour():
    """The two convenience forms are Text with a pushed colour, nothing else."""
    red = RecordingPainter()
    grey = RecordingPainter()
    uitext.TextColored((255, 0, 0), "same").draw(red, 0.0, 0.0, 100.0, 18.0)
    uitext.TextDisabled("same").draw(grey, 0.0, 0.0, 100.0, 18.0)
    assert red.texts[0][:5] == grey.texts[0][:5]
    assert red.texts[0][5] == (255, 0, 0)
    assert grey.texts[0][5] == style.TEXT_DISABLED


# --------------------------------------------------------------------------
# TextWrapped
# --------------------------------------------------------------------------
def test_wrapped_breaks_at_the_expected_places():
    """Ten characters' worth of width folds a known sentence into known lines."""
    painter = RecordingPainter()
    widget = uitext.TextWrapped("the quick brown fox jumps")
    assert widget.wrapped(painter, 10 * CHAR) == ["the quick", "brown fox", "jumps"]


def test_wrapped_never_draws_a_line_wider_than_the_box():
    """Whatever the width, no drawn line overflows it."""
    painter = RecordingPainter()
    words = "wrapping has to hold at every width or a caption runs into its neighbour"
    widget = uitext.TextWrapped(words)
    for width in range(40, 200, 7):
        lines = widget.wrapped(painter, float(width))
        assert lines
        assert max(painter.text_width(line) for line in lines) <= float(width)


def test_wrapped_drops_the_blank_it_broke_at():
    """A line does not start with the space the break happened on."""
    painter = RecordingPainter()
    lines = uitext.wrap_lines(painter, "hello    world", 6 * CHAR)
    assert lines == ["hello", "world"]


def test_wrapped_breaks_after_punctuation_like_the_reference():
    """A comma inside ``ccc,ddd`` is a break candidate, so the pair can split.

    The reference's own worked example, ``"aaa bbb, ccc,ddd. eee"``: the break
    points it marks are after each blank *and* after the comma in ``ccc,ddd``.
    A greedy split on spaces has no such point and would put ``ccc,ddd`` whole
    on the second line.
    """
    painter = RecordingPainter()
    assert uitext.wrap_lines(painter, "aaa bbb, ccc,ddd. eee", 12 * CHAR) == [
        "aaa bbb,",
        "ccc,ddd. eee",
    ]
    assert uitext.wrap_lines(painter, "aaa bbb, ccc,ddd. eee", 16 * CHAR) == [
        "aaa bbb, ccc,",
        "ddd. eee",
    ]


def test_wrapped_keeps_a_decimal_together():
    """The punctuation rule exempts digits, so ``3.14159`` is not broken at the dot.

    The letters version is the control: same shape, same width, and it *does*
    break after the dot. Without the digit exemption a column of numbers would
    fold in the middle of its values.
    """
    painter = RecordingPainter()
    assert uitext.wrap_lines(painter, "pi is 3.14159 ok", 9 * CHAR) == ["pi is", "3.14159", "ok"]
    assert uitext.wrap_lines(painter, "pi is a.bcdefg ok", 9 * CHAR) == ["pi is a.", "bcdefg ok"]


def test_wrapped_cuts_a_word_too_long_for_the_column():
    """A word wider than the whole column is cut, not allowed to overflow.

    The reference's source comment claims six characters of width turn
    ``"The tropical fish"`` into ``"The tr"``/``"opical"``/``"fish"``; its code
    does not do that and has not for some time -- the break is taken at the last
    *committed* span end, so the short word goes on a line of its own and only
    the over-long word is cut. This is the code's behaviour, not the comment's.
    """
    painter = RecordingPainter()
    lines = uitext.wrap_lines(painter, "The tropical fish", 6 * CHAR)
    assert lines == ["The", "tropic", "al", "fish"]
    assert max(painter.text_width(line) for line in lines) <= 6 * CHAR


def test_wrapped_honours_explicit_newlines():
    """A newline breaks the line wherever it is, and is not drawn."""
    painter = RecordingPainter()
    assert uitext.wrap_lines(painter, "a\n\nb", 200.0) == ["a", "", "b"]


def test_wrapped_draws_one_call_per_folded_line_and_clips():
    """Each folded line is its own draw, inside one clip that is popped."""
    painter = RecordingPainter()
    widget = uitext.TextWrapped("the quick brown fox jumps")
    widget.draw(painter, 5.0, 7.0, 10 * CHAR, 40.0)
    assert painter.strings == ["the quick", "brown fox", "jumps"]
    assert [entry[1] for entry in painter.texts] == [7.0, 19.0, 31.0]
    assert painter.clip_depth_max == 1
    assert painter.clips == []


def test_wrapped_size_reports_the_folded_height():
    """The height is the number of folded lines, which is what the caller lays out from."""
    painter = RecordingPainter()
    widget = uitext.TextWrapped("the quick brown fox jumps")
    assert widget.size(painter, 10 * CHAR) == (9 * CHAR, 3 * 12.0)


# --------------------------------------------------------------------------
# LabelText
# --------------------------------------------------------------------------
def test_label_text_draws_the_value_first_and_the_label_after_it():
    """The reference's order: value inside the item box, label trailing it."""
    painter = RecordingPainter()
    uitext.LabelText("label", "42").draw(painter, 10.0, 0.0, 200.0, 18.0)
    assert [entry[4] for entry in painter.texts] == ["42", "label"]
    value_x, label_x = painter.texts[0][0], painter.texts[1][0]
    assert value_x < label_x
    # Value box is 65% of 200 -> the label starts past its right edge.
    assert value_x == pytest.approx(10.0 + 4.0)
    assert label_x == pytest.approx(10.0 + 130.0 + 4.0)


def test_label_text_clips_the_value_to_its_own_box():
    """A long value stays inside the item box rather than running over the label."""
    painter = RecordingPainter()
    uitext.LabelText("label", "a value far too long for its box").draw(
        painter, 0.0, 0.0, 100.0, 18.0
    )
    clip = painter.clip_depth_max
    assert clip == 1
    assert painter.clips == []
    assert painter.texts[0][2] <= 65.0


def test_label_text_hides_its_hash_suffix_and_an_empty_label():
    """``##`` is an id, not text; an empty label draws only the value."""
    painter = RecordingPainter()
    uitext.LabelText("shown##id", "v").draw(painter, 0.0, 0.0, 200.0, 18.0)
    assert [entry[4] for entry in painter.texts] == ["v", "shown"]

    bare = RecordingPainter()
    uitext.LabelText("", "v").draw(bare, 0.0, 0.0, 200.0, 18.0)
    assert [entry[4] for entry in bare.texts] == ["v"]


# --------------------------------------------------------------------------
# Bullet / BulletText
# --------------------------------------------------------------------------
def test_bullet_text_puts_the_mark_before_the_text():
    """The mark sits left of the string, at the row's vertical centre.

    The mark is a scan-converted disc (``style.disc``), so it is several bands
    rather than one rectangle; the assertions are on the shape they add up to.
    """
    painter = RecordingPainter()
    uitext.BulletText("item").draw(painter, 20.0, 0.0, 200.0, 18.0)
    bands = painter.fills
    diameter = 12.0 * 0.4
    left = min(b[0] for b in bands)
    right = max(b[0] + b[2] for b in bands)
    top = min(b[1] for b in bands)
    bottom = max(b[1] + b[3] for b in bands)
    assert right - left == pytest.approx(diameter)
    assert bottom - top == pytest.approx(diameter)
    assert (top + bottom) * 0.5 == pytest.approx(9.0)
    assert left > 20.0
    text_x = painter.texts[0][0]
    assert text_x == pytest.approx(20.0 + 12.0 + 8.0)
    assert right <= text_x


def test_bullet_alone_draws_a_mark_and_no_text():
    """``Bullet`` is the mark by itself, and reports how far it advances."""
    painter = RecordingPainter()
    bullet = uitext.Bullet()
    bullet.draw(painter, 0.0, 0.0, 40.0, 18.0)
    assert painter.strings == []
    # A disc, so more than one band -- but symmetric about its centre, which
    # is the property that says it is a disc and not a staircase.
    assert len(painter.fills) >= 3
    centre_x = 4.0 + 12.0 * 0.5
    for bx, _by, bw, _bh, _c in painter.fills:
        assert bx + bw * 0.5 == pytest.approx(centre_x)
    assert bullet.advance(painter) == pytest.approx(12.0 + 8.0)


def test_bullet_text_size_adds_no_padding_for_empty_text():
    """The reference's rule: an empty bullet item is just the mark's width."""
    painter = RecordingPainter()
    assert uitext.BulletText("").size(painter) == (12.0, 12.0)
    assert uitext.BulletText("ab").size(painter)[0] == pytest.approx(12.0 + 2 * CHAR + 8.0)


# --------------------------------------------------------------------------
# SeparatorText
# --------------------------------------------------------------------------
def test_separator_text_draws_a_rule_either_side_of_its_caption():
    """Two segments, with the caption in the gap between them."""
    painter = RecordingPainter()
    uitext.SeparatorText("group").draw(painter, 0.0, 0.0, 300.0, 18.0)
    assert len(painter.fills) == 2
    left, right = painter.fills
    label_x, _, label_w, _, label, _ = painter.texts[0]
    assert label == "group"
    # Left stub: inset 20, ending an ItemSpacing before the caption.
    assert left[0] == pytest.approx(0.0)
    assert left[0] + left[2] == pytest.approx(label_x - 8.0)
    # Right segment resumes an ItemSpacing past it and runs to the edge.
    assert right[0] == pytest.approx(label_x + label_w + 8.0)
    assert right[0] + right[2] == pytest.approx(300.0)


def test_separator_text_without_a_label_is_one_rule():
    """An empty caption gives the plain rule right across the box."""
    painter = RecordingPainter()
    uitext.SeparatorText("").draw(painter, 5.0, 0.0, 100.0, 18.0)
    assert painter.strings == []
    assert len(painter.fills) == 1
    assert painter.fills[0][0] == 5.0
    assert painter.fills[0][2] == 100.0


def test_separator_text_alignment_moves_the_caption():
    """``align`` slides the caption between the two insets."""
    left_painter = RecordingPainter()
    centre_painter = RecordingPainter()
    right_painter = RecordingPainter()
    uitext.SeparatorText("mid", align=0.0).draw(left_painter, 0.0, 0.0, 300.0, 18.0)
    uitext.SeparatorText("mid", align=0.5).draw(centre_painter, 0.0, 0.0, 300.0, 18.0)
    uitext.SeparatorText("mid", align=1.0).draw(right_painter, 0.0, 0.0, 300.0, 18.0)
    xs = [p.texts[0][0] for p in (left_painter, centre_painter, right_painter)]
    assert xs[0] < xs[1] < xs[2]
    assert xs[0] == pytest.approx(20.0)
    assert xs[2] == pytest.approx(300.0 - 20.0 - 3 * CHAR)


def test_separator_text_rule_is_three_pixels_thick_and_centred():
    """``SeparatorTextBorderSize`` is 3, and the rule sits in the row's middle."""
    painter = RecordingPainter()
    uitext.SeparatorText("g").draw(painter, 0.0, 10.0, 200.0, 20.0)
    for rect in painter.fills:
        assert rect[3] == pytest.approx(3.0)
        assert rect[1] + rect[3] * 0.5 == pytest.approx(20.0)


# --------------------------------------------------------------------------
# TextLink
# --------------------------------------------------------------------------
def test_text_link_fires_only_inside_its_text():
    """The hit box is the string's extent, not the row it was laid out in."""
    painter = RecordingPainter()
    link = uitext.TextLink("open")  # 4 chars -> 28 px wide
    link.draw(painter, 0.0, 0.0, 400.0, 18.0)
    assert link.press(10.0, 9.0, 0.0, 0.0, 400.0, 18.0) is True
    link.release()
    assert link.press(200.0, 9.0, 0.0, 0.0, 400.0, 18.0) is False
    assert link.press(27.0, 9.0, 0.0, 0.0, 400.0, 18.0) is True
    link.release()
    assert link.press(29.0, 9.0, 0.0, 0.0, 400.0, 18.0) is False


def test_text_link_that_was_never_drawn_has_no_extent():
    """Without a measurement there is no hit box, and guessing the row is the bug."""
    link = uitext.TextLink("open")
    assert link.extent(0.0, 0.0, 400.0, 18.0) is None
    assert link.press(10.0, 9.0, 0.0, 0.0, 400.0, 18.0) is False


def test_text_link_follows_the_row_it_is_redrawn_in():
    """The extent is a width, so a relaid-out link is hit at its new position."""
    painter = RecordingPainter()
    link = uitext.TextLink("open")
    link.draw(painter, 0.0, 0.0, 400.0, 18.0)
    assert link.press(110.0, 59.0, 100.0, 50.0, 400.0, 18.0) is True
    link.release()
    assert link.press(10.0, 9.0, 100.0, 50.0, 400.0, 18.0) is False


def test_text_link_underlines_exactly_its_text():
    """A one-pixel rule under the string, no wider than the string."""
    painter = RecordingPainter()
    uitext.TextLink("open").draw(painter, 4.0, 0.0, 400.0, 18.0)
    assert len(painter.fills) == 1
    rule_x, rule_y, rule_w, rule_h, colour = painter.fills[0]
    assert rule_x == 4.0
    assert rule_w == pytest.approx(4 * CHAR)
    assert rule_h == 1.0
    assert rule_y + rule_h <= 18.0
    # The rule is a darker shade of the link colour, never the same one.
    assert colour[:3] < style.TEXT_LINK[:3]


def test_text_link_brightens_while_held():
    """Held is a different colour from at rest -- the reference lifts the value."""
    rest = RecordingPainter()
    held = RecordingPainter()
    link = uitext.TextLink("open")
    link.draw(rest, 0.0, 0.0, 400.0, 18.0)
    link.press(5.0, 9.0, 0.0, 0.0, 400.0, 18.0)
    link.draw(held, 0.0, 0.0, 400.0, 18.0)
    assert held.texts[0][5] != rest.texts[0][5]
    link.release()
    after = RecordingPainter()
    link.draw(after, 0.0, 0.0, 400.0, 18.0)
    assert after.texts[0][5] == rest.texts[0][5]


def test_text_link_hides_its_hash_suffix():
    """``##`` identifies the link; it is not part of what is shown or measured."""
    painter = RecordingPainter()
    link = uitext.TextLink("open##link-1")
    link.draw(painter, 0.0, 0.0, 400.0, 18.0)
    assert painter.strings == ["open"]
    assert link.extent(0.0, 0.0, 400.0, 18.0)[2] == pytest.approx(4 * CHAR)


# --------------------------------------------------------------------------
# Value
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        (True, "flag: true"),
        (False, "flag: false"),
        (7, "flag: 7"),
        (-2, "flag: -2"),
        (0.5, "flag: 0.500"),
    ],
)
def test_value_formats_each_type_the_way_the_reference_does(value, expected):
    """Bool prints true/false, int prints as an integer, float gets three decimals."""
    assert uitext.Value("flag", value).text == expected


def test_value_bool_is_not_written_as_an_integer():
    """A bool is an int in Python; taking the int branch would print ``1``."""
    assert uitext.Value("v", True).formatted == "true"
    assert uitext.Value("v", 1).formatted == "1"


def test_value_honours_a_float_format():
    """The caller's format is used, percentage specs included."""
    assert uitext.Value("v", 0.25, "%.1f").text == "v: 0.2"
    assert uitext.Value("v", 0.25, "%.0%").text == "v: 25%"


def test_value_draws_the_whole_line_in_one_call():
    """One string, so it aligns like any other line of text."""
    painter = RecordingPainter()
    uitext.Value("count", 3).draw(painter, 2.0, 0.0, 100.0, 18.0)
    assert painter.strings == ["count: 3"]
    assert painter.texts[0][0] == 2.0
