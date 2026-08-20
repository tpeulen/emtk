"""The text family of painter-level controls: the things a panel *says*.

Why these are controls at all
-----------------------------
Nine of the ten here draw a string and nothing else, which reads like a reason
not to write them. The reason to write them is that the reference implementation
does not treat "a string" as one thing: a caption, a value beside a caption, a
paragraph that has to fold, a bulleted item and a section rule are five
different layouts of the same glyphs, and a panel that draws them by hand gets
each one *slightly* differently. :class:`LabelText` in particular is not the
layout its name suggests -- the reference draws the **value on the left** and the
label after it, so that a column of ``LabelText`` rows lines up with a column of
sliders, whose values also sit in the item box with their labels trailing.
Writing that out by hand from the name alone produces the opposite order, and it
only looks wrong once there is a slider next to it.

What is faithful and what could not be
--------------------------------------
The wrapping in :class:`TextWrapped` is a port of the reference's
``ImFontCalcWordWrapPositionEx``, blank-skipping and punctuation rules included,
because greedy split-on-space disagrees with it on exactly the strings a panel
shows: ``"aaa bbb, ccc,ddd. eee"`` may break after the comma in ``ccc,ddd``, and
a word longer than the column is *cut* rather than allowed to overflow.

Two things the six painter operations cannot express, and what they became:

* the bullet is a **filled circle** in the reference (``RenderBullet`` ->
  ``AddCircleFilled``). There is no circle operation, so it is the square that
  inscribes it. At a bullet's size -- two fifths of the font -- the difference is
  a pixel at each corner;
* the link's underline is a **line**. There is no line operation either, so it
  is a one-pixel :meth:`~.painter.Painter.fill_rect`, which is what a
  one-pixel-tall line is anyway.
"""
from __future__ import annotations

from .. import style
from ..painter import ALIGN_LEFT, ALIGN_VCENTER, Colour, Painter

__all__ = [
    "Text",
    "TextColored",
    "TextDisabled",
    "TextWrapped",
    "LabelText",
    "BulletText",
    "Bullet",
    "SeparatorText",
    "TextLink",
    "Value",
    "wrap_lines",
]


# --------------------------------------------------------------------------
# The reference's style metrics, at its own defaults.
#
# ``style`` carries the palette and not these, because a colour shared between
# two modules drifts and a metric does not: these are read from the reference's
# ``ImGuiStyle`` constructor and are what make a ported control land where the
# original did.
# --------------------------------------------------------------------------
#: ``ImGuiStyle::FramePadding``.
_FRAME_PAD_X = 4.0
#: ``ImGuiStyle::ItemSpacing.x`` -- the gap either side of a separator caption.
_ITEM_SPACING_X = 8.0
#: ``ImGuiStyle::ItemInnerSpacing.x`` -- the gap between a widget and its label.
_ITEM_INNER_SPACING_X = 4.0
#: ``ImGuiStyle::SeparatorTextPadding`` -- how far the caption is inset.
_SEPARATOR_TEXT_PAD_X = 20.0
#: ``ImGuiStyle::SeparatorTextBorderSize``.
_SEPARATOR_TEXT_BORDER = 3.0
#: What ``CalcItemWidth()`` defaults to: ``window width * 0.65``. It is why a
#: column of :class:`LabelText` rows lines up with a column of sliders.
_ITEM_WIDTH_FRACTION = 0.65
#: ``RenderBullet``'s radius, as a fraction of the font size.
_BULLET_RADIUS = 0.20


# --------------------------------------------------------------------------
# Word wrapping -- a port of ``ImFontCalcWordWrapPositionEx``
# --------------------------------------------------------------------------
_BLANK = 0
_PUNCT = 1
_OTHER = 2

#: The reference's hardcoded blanks and separators, plus the two ideographic
#: ones it classifies in the ``0x3000`` block.
_BLANK_CHARS = " \t　"
_PUNCT_CHARS = ".,;!?\"、。"


def _char_class(char: str) -> int:
    """Which of the reference's three character classes ``char`` is in.

    Parameters
    ----------
    char : str
        A single character.

    Returns
    -------
    int
        :data:`_BLANK`, :data:`_PUNCT` or :data:`_OTHER`.
    """
    if char in _BLANK_CHARS:
        return _BLANK
    if char in _PUNCT_CHARS:
        return _PUNCT
    return _OTHER


def _wrap_position(
    text: str,
    start: int,
    wrap_width: float,
    widths: dict,
    p: Painter,
) -> int:
    """Where the line starting at ``start`` has to break.

    A port of the reference's ``ImFontCalcWordWrapPositionEx``. It tracks three
    running widths -- the committed line, the run of blanks after it, and the
    span (word) being built -- so that a break at a blank does not carry the
    blank onto the next line, and so that a span too long for a whole line is
    cut mid-word rather than allowed to overflow.

    Parameters
    ----------
    text : str
        The whole string. Only the part from ``start`` is looked at.
    start : int
        Index the line starts at.
    wrap_width : float
        Width available to the line.
    widths : dict
        Per-character advance cache; filled as it goes.
    p : Painter
        Used to measure a character not yet in ``widths``.

    Returns
    -------
    int
        Index one past the last character of the line. Never equal to ``start``
        unless ``text[start]`` is a newline -- a width too small to fit even one
        character forces one anyway, because the alternative is a loop that
        never advances.
    """
    line_width = 0.0
    blank_width = 0.0
    span_width = 0.0
    span_end = start
    prev_type = _OTHER
    index = start
    end = len(text)

    while index < end:
        char = text[index]
        if char == "\n":
            return index
        if char == "\r":
            index += 1
            continue
        char_width = widths.get(char)
        if char_width is None:
            char_width = float(p.text_width(char))
            widths[char] = char_width
        curr_type = _char_class(char)

        if curr_type == _BLANK:
            # End of a span: the break goes before the blank, and the blank's
            # width is held back so a line that ends here is not padded by it.
            if prev_type != _BLANK:
                span_end = index
                line_width += span_width
                span_width = 0.0
            blank_width += char_width
        else:
            # ".X" is a break too -- unless X is a digit, so "3.14" holds.
            if prev_type == _PUNCT and curr_type != _PUNCT and not ("0" <= char <= "9"):
                span_end = index
                line_width += span_width + blank_width
                span_width = blank_width = 0.0
            span_width += char_width

        if span_width + blank_width + line_width > wrap_width:
            if span_width + blank_width > wrap_width:
                break  # The span alone does not fit a line: cut it here.
            return span_end

        prev_type = curr_type
        index += 1

    if index == start and start < end:
        return start + 1
    return index


def wrap_lines(p: Painter, text: str, width: float) -> list[str]:
    """``text`` folded into lines no wider than ``width``.

    Parameters
    ----------
    p : Painter
        Used to measure.
    text : str
        The paragraph. Embedded newlines break the line where they appear.
    width : float
        The column width, in pixels.

    Returns
    -------
    list of str
        The lines, without their trailing blanks or newlines. Empty text gives
        one empty line, which is what the reference draws for it.

    Notes
    -----
    A word wider than the whole column is cut, exactly as the reference cuts it:
    ``"The tropical fish"`` in five characters' worth of width is ``"The tr"``,
    ``"opical"``, ``"fish"``. Overflowing instead would be the more forgiving
    choice, and is the one that draws over the neighbouring column.
    """
    if not text:
        return [""]
    if width <= 0.0:
        return text.split("\n")

    widths: dict = {}
    lines: list[str] = []
    index = 0
    end = len(text)
    while index < end:
        stop = _wrap_position(text, index, width, widths, p)
        lines.append(text[index:stop])
        # Wrapping skips the blanks it broke at, then one newline
        # (``ImTextCalcWordWrapNextLineStart``).
        nxt = stop
        while nxt < end and text[nxt] in " \t":
            nxt += 1
        if nxt < end and text[nxt] == "\n":
            nxt += 1
        index = nxt if nxt > index else index + 1
    return lines or [""]


def _shade(colour: Colour, delta: float) -> tuple[int, int, int, int]:
    """``colour`` with its HSV *value* moved by ``delta``, done in RGB.

    The reference brightens a hovered link and darkens its underline by
    converting to HSV, shifting the value and converting back. With hue and
    saturation unchanged that is a plain scale of all three channels, so the
    round trip is arithmetic rather than a colour-space conversion nobody else
    here needs.

    Parameters
    ----------
    colour : Colour
        The colour; its alpha is carried through.
    delta : float
        How far to move the value, in ``0..1`` units. Negative darkens.

    Returns
    -------
    tuple of int
        The shifted ``(r, g, b, a)``.
    """
    red, green, blue = colour[0], colour[1], colour[2]
    alpha = colour[3] if len(colour) > 3 else 255
    top = max(red, green, blue)
    if top <= 0:
        level = int(round(style.clamp(delta, 0.0, 1.0) * 255.0))
        return (level, level, level, alpha)
    value = top / 255.0
    factor = style.clamp(value + delta, 0.0, 1.0) / value
    return (
        int(round(style.clamp(red * factor, 0.0, 255.0))),
        int(round(style.clamp(green * factor, 0.0, 255.0))),
        int(round(style.clamp(blue * factor, 0.0, 255.0))),
        alpha,
    )


def _rendered(label: str) -> str:
    """``label`` up to its ``##`` marker.

    The reference's ``FindRenderedTextEnd``: everything from ``##`` on is the
    part of a label that makes its id unique and is *not* drawn. Deliberately
    not applied by :class:`Text`, which the reference documents as showing the
    whole string -- only the controls that take an identifying *label*
    (:class:`LabelText`, :class:`SeparatorText`, :class:`TextLink`) hide it.

    Parameters
    ----------
    label : str
        The label.

    Returns
    -------
    str
        The visible part.
    """
    cut = label.find("##")
    return label if cut < 0 else label[:cut]


class Text:
    """A run of text, drawn as it is.

    The reference's ``TextUnformatted``/``Text``: no frame, no interaction, and
    -- unlike every control that takes a *label* -- no hiding of anything after
    a ``##``, because this one is the end-user function for showing a string.

    Parameters
    ----------
    text : str, optional
        The string. Embedded newlines start a new line.
    colour : Colour, optional
        What to draw it in.
    """

    def __init__(self, text: str = "", colour: Colour = style.TEXT) -> None:
        self.text = str(text)
        self.colour = colour

    def lines(self) -> list[str]:
        """Split the text at its newlines.

        Returns
        -------
        list of str
            One entry per line; a single entry for text without newlines.
        """
        return self.text.split("\n")

    def size(self, p: Painter) -> tuple[float, float]:
        """Measured ``(width, height)`` the text needs.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            Width of the widest line, and the height of all of them.
        """
        rows = self.lines()
        widest = max((p.text_width(row) for row in rows), default=0.0)
        return (widest, p.line_height() * max(len(rows), 1))

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the text, one call per line.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        rows = self.lines()
        if len(rows) == 1:
            p.text(x, y, max(w, 1.0), h, ALIGN_LEFT | ALIGN_VCENTER, rows[0], self.colour)
            return
        line_h = p.line_height()
        for index, row in enumerate(rows):
            p.text(x, y + index * line_h, max(w, 1.0), line_h,
                   ALIGN_LEFT | ALIGN_VCENTER, row, self.colour)


class TextColored(Text):
    """Text in a colour of the caller's choosing.

    The reference pushes ``ImGuiCol_Text`` and calls ``Text``, which is why the
    colour comes *first* in its signature and why this is :class:`Text` with one
    argument reordered rather than a control of its own.

    Parameters
    ----------
    colour : Colour
        The colour.
    text : str, optional
        The string.
    """

    def __init__(self, colour: Colour, text: str = "") -> None:
        super().__init__(text, colour)


class TextDisabled(Text):
    """Text in the palette's disabled grey.

    Parameters
    ----------
    text : str, optional
        The string.
    """

    def __init__(self, text: str = "") -> None:
        super().__init__(text, style.TEXT_DISABLED)


class TextWrapped(Text):
    """A paragraph folded to the width of the box it is drawn into.

    Parameters
    ----------
    text : str, optional
        The paragraph.
    colour : Colour, optional
        What to draw it in.

    Notes
    -----
    The height passed to :meth:`draw` is the box the paragraph is *clipped* to,
    not the space it takes: ask :meth:`size` for that and lay the box out from
    the answer, or the tail of a long paragraph is drawn over whatever follows
    it. The clip is what keeps that from happening silently.
    """

    def __init__(self, text: str = "", colour: Colour = style.TEXT) -> None:
        super().__init__(text, colour)

    def wrapped(self, p: Painter, w: float) -> list[str]:
        """Fold this text into lines at width ``w``.

        Parameters
        ----------
        p : Painter
            Used to measure.
        w : float
            Column width.

        Returns
        -------
        list of str
            The folded lines.
        """
        return wrap_lines(p, self.text, w)

    def size(self, p: Painter, w: float = 0.0) -> tuple[float, float]:
        """Measured ``(width, height)`` at a given column width.

        Parameters
        ----------
        p : Painter
            Used to measure.
        w : float, optional
            The column width. Zero means "do not fold", which measures the same
            as :class:`Text`.

        Returns
        -------
        tuple of float
            Width of the widest folded line, and the height of all of them.
        """
        if w <= 0.0:
            return super().size(p)
        rows = self.wrapped(p, w)
        widest = max((p.text_width(row) for row in rows), default=0.0)
        return (widest, p.line_height() * max(len(rows), 1))

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the folded paragraph, one call per line.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box. Lines past its bottom are clipped away.
        """
        rows = self.wrapped(p, w)
        line_h = p.line_height()
        p.push_clip(x, y, max(w, 1.0), max(h, 1.0))
        for index, row in enumerate(rows):
            p.text(x, y + index * line_h, max(w, 1.0), line_h,
                   ALIGN_LEFT | ALIGN_VCENTER, row, self.colour)
        p.pop_clip()


class LabelText:
    """A value with its caption *after* it, aligned to other labelled widgets.

    Parameters
    ----------
    label : str
        The caption. Anything from ``##`` on is not drawn.
    value : str, optional
        The value, already formatted.
    value_fraction : float, optional
        How much of the box the value gets, before the caption starts. The
        default is the reference's ``CalcItemWidth()`` default.

    Notes
    -----
    The order is the surprising half and the whole point of the control: the
    **value is drawn on the left**, inside a box the same width a slider or a
    drag would get, and the **label follows it**. That is what makes a stack of
    these line up with a stack of real widgets. Reading the name and drawing
    "label then value" produces something that looks fine on its own and is
    visibly out of step the moment a slider is put beside it.
    """

    def __init__(self, label: str, value: str = "", value_fraction: float = _ITEM_WIDTH_FRACTION) -> None:
        self.label = label
        self.value = value
        self.value_fraction = float(value_fraction)

    def value_width(self, w: float) -> float:
        """How wide the value box is inside a box of width ``w``.

        Parameters
        ----------
        w : float
            The whole box's width.

        Returns
        -------
        float
            The value box's width.
        """
        return max(w * style.clamp(self.value_fraction, 0.0, 1.0), 0.0)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the value in its box and the caption after it.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        value_w = self.value_width(w)
        p.push_clip(x, y, max(value_w, 1.0), max(h, 1.0))
        p.text(x + _FRAME_PAD_X, y, max(value_w - _FRAME_PAD_X, 1.0), h,
               ALIGN_LEFT | ALIGN_VCENTER, str(self.value), style.TEXT)
        p.pop_clip()
        shown = _rendered(self.label)
        if not shown:
            return
        left = x + value_w + _ITEM_INNER_SPACING_X
        p.text(left, y, max(x + w - left, 1.0), h,
               ALIGN_LEFT | ALIGN_VCENTER, shown, style.TEXT)


class Bullet:
    """The bullet alone: the glyph a :class:`BulletText` puts before its text.

    Its own control because the reference's ``Bullet()`` is: it draws the mark
    and then stays on the same line, so a caller can follow it with any widget
    at all rather than only with text.

    Parameters
    ----------
    colour : Colour, optional
        What to draw the mark in.

    Notes
    -----
    The reference draws a filled circle and the painter has no circle
    operation, so it is scan-converted by :func:`~.style.disc`. That helper is
    shared rather than local: this was an inscribed square first, which is
    indistinguishable from a disc in isolation and obvious the moment a bullet
    sits in a column above a radio button drawn the other way.
    """

    def __init__(self, colour: Colour = style.TEXT) -> None:
        self.colour = colour

    def advance(self, p: Painter) -> float:
        """How far to the right the next item starts.

        Parameters
        ----------
        p : Painter
            Used to measure the font.

        Returns
        -------
        float
            The mark's own width plus the reference's ``SameLine`` spacing.
        """
        return p.line_height() + _FRAME_PAD_X * 2.0

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the mark, centred in the row like the text beside it.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box. Only its left edge and its vertical centre are used; the
            mark is font-sized whatever the box is.
        """
        font = p.line_height()
        centre_x = x + _FRAME_PAD_X + font * 0.5
        centre_y = y + h * 0.5
        style.disc(p, centre_x, centre_y, font * _BULLET_RADIUS, self.colour)


class BulletText:
    """A bulleted line of text.

    Parameters
    ----------
    text : str, optional
        The string.
    colour : Colour, optional
        What to draw the mark and the text in.
    """

    def __init__(self, text: str = "", colour: Colour = style.TEXT) -> None:
        self.text = str(text)
        self.colour = colour
        self.bullet = Bullet(colour)

    def size(self, p: Painter) -> tuple[float, float]:
        """Measured ``(width, height)`` of the mark and its text together.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            The size. Empty text adds no padding, which is the reference's rule.
        """
        font = p.line_height()
        text_w = p.text_width(self.text)
        extra = (text_w + _FRAME_PAD_X * 2.0) if text_w > 0.0 else 0.0
        return (font + extra, font)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the mark and the text after it.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        self.bullet.draw(p, x, y, w, h)
        left = x + p.line_height() + _FRAME_PAD_X * 2.0
        p.text(left, y, max(x + w - left, 1.0), h,
               ALIGN_LEFT | ALIGN_VCENTER, self.text, self.colour)


class SeparatorText:
    """A rule with a caption sitting in a gap in it.

    Parameters
    ----------
    label : str, optional
        The caption. Anything from ``##`` on is not drawn. Empty draws a plain
        rule right across.
    align : float, optional
        Where the caption sits: ``0.0`` left, ``0.5`` centred, ``1.0`` right.
        The reference's default is left.

    Notes
    -----
    :class:`~.widgets.Separator` also takes a label and is *not* this: it draws
    the caption hard against the left edge with the rule picking up after it, so
    a run of them reads as a list of groups. This one is the reference's
    dedicated ``SeparatorText``, and the difference is that the rule runs on
    **both** sides of the caption -- inset by ``SeparatorTextPadding`` (20 px)
    with an ``ItemSpacing`` gap (8 px) either side of the text, which leaves a
    short 12-pixel stub to the caption's left even at the default left
    alignment. That stub is what makes it read as a caption *in* a rule rather
    than as a heading with a rule after it.
    """

    def __init__(self, label: str = "", align: float = 0.0) -> None:
        self.label = label
        self.align = float(align)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the caption and the one or two rule segments.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        shown = _rendered(self.label)
        thickness = _SEPARATOR_TEXT_BORDER
        rule_y = y + (h - thickness) * 0.5
        if not shown:
            p.fill_rect(x, rule_y, max(w, 0.0), thickness, style.SEPARATOR)
            return

        avail = max(0.0, w - _SEPARATOR_TEXT_PAD_X * 2.0)
        shown = style.fit_text(p, shown, avail)
        label_w = p.text_width(shown)
        label_x = x + _SEPARATOR_TEXT_PAD_X + max(
            0.0, (avail - label_w) * style.clamp(self.align, 0.0, 1.0)
        )

        left_end = label_x - _ITEM_SPACING_X
        if left_end > x:
            p.fill_rect(x, rule_y, left_end - x, thickness, style.SEPARATOR)
        right_start = label_x + label_w + _ITEM_SPACING_X
        if x + w > right_start:
            p.fill_rect(right_start, rule_y, x + w - right_start, thickness, style.SEPARATOR)
        p.text(label_x, y, max(label_w, 1.0), h, ALIGN_LEFT | ALIGN_VCENTER, shown, style.TEXT)


class TextLink:
    """A clickable, underlined label.

    Parameters
    ----------
    label : str
        The text. Anything from ``##`` on is not drawn but is still part of the
        label the caller identifies it by.

    Notes
    -----
    The hit box is the **text's own extent**, not the row it sits in: the
    reference sizes the item to ``CalcTextSize(label)``, so a link at the start
    of a wide row does not swallow clicks halfway across the panel. The extent
    is measured by :meth:`draw`, which is what a control that has never been
    drawn is missing -- :meth:`press` on one of those reports no hit rather than
    guessing, because guessing "the whole row" is exactly the bug the reference
    avoids.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.hovered = False
        self._held = False
        self._text_w: float | None = None

    def extent(self, box_x: float, box_y: float, box_w: float, box_h: float) -> tuple[float, float, float, float] | None:
        """Give the box a press has to land in, or ``None`` if never drawn.

        Parameters
        ----------
        box_x, box_y, box_w, box_h : float
            The row the link was laid out in.

        Returns
        -------
        tuple of float or None
            The text's box, never wider than the row it is in.
        """
        if self._text_w is None:
            return None
        return (box_x, box_y, min(self._text_w, box_w), box_h)

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the underline and the label over it.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box. The link takes only as much of it as the text needs.
        """
        shown = _rendered(self.label)
        text_w = min(p.text_width(shown), max(w, 0.0))
        self._text_w = text_w
        if text_w <= 0.0:
            return

        lift = 0.4 if self._held else (0.3 if self.hovered else 0.0)
        text_colour = _shade(style.TEXT_LINK, lift) if lift else style.TEXT_LINK
        line_colour = _shade(text_colour, -0.20)

        # The reference puts the rule a fifth of the descent below the text; no
        # descent is exposed here, so it goes just under the line box the text
        # is centred in, kept inside the item.
        line_h = p.line_height()
        line_y = min(y + (h + line_h) * 0.5, y + h - 1.0)
        p.fill_rect(x, line_y, text_w, 1.0, line_colour)
        p.text(x, y, max(text_w, 1.0), h, ALIGN_LEFT | ALIGN_VCENTER, shown, text_colour)

    def press(self, x: float, y: float, box_x: float, box_y: float, box_w: float, box_h: float) -> bool:
        """Process a press. Returns whether the link fired.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The row the link was drawn in.

        Returns
        -------
        bool
            True if the press was inside the text itself.
        """
        box = self.extent(box_x, box_y, box_w, box_h)
        if box is None or not style.hit(x, y, *box):
            self._held = False
            return False
        self._held = True
        return True

    def release(self) -> None:
        """Let go of the link."""
        self._held = False


class Value:
    """A caption and a value, as ``prefix: value``.

    The reference's ``Value()`` overloads, which are one line of ``Text`` each
    and differ only in how the number is written: ``true``/``false`` for a bool,
    ``%d`` for an integer, and three decimals for a float unless the caller says
    otherwise.

    Parameters
    ----------
    prefix : str
        The caption.
    value : bool, int or float
        The number. A bool is checked for first -- in Python it *is* an int, and
        a bool falling through to the integer branch prints ``1`` where the
        reference prints ``true``.
    float_format : str, optional
        The format a float is written with.
    colour : Colour, optional
        What to draw the line in.
    """

    def __init__(
        self,
        prefix: str,
        value: bool | int | float,
        float_format: str = "%.3f",
        colour: Colour = style.TEXT,
    ) -> None:
        self.prefix = prefix
        self.value = value
        self.float_format = float_format
        self.colour = colour

    @property
    def text(self) -> str:
        """The whole line, caption and value together.

        Returns
        -------
        str
            ``"prefix: value"``.
        """
        return f"{self.prefix}: {self.formatted}"

    @property
    def formatted(self) -> str:
        """Just the value, written the way its type is written.

        Returns
        -------
        str
            The rendered number.
        """
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, int):
            return f"{self.value:d}"
        return style.format_value(self.float_format, float(self.value))

    def size(self, p: Painter) -> tuple[float, float]:
        """Measured ``(width, height)`` of the line.

        Parameters
        ----------
        p : Painter
            Used to measure.

        Returns
        -------
        tuple of float
            The size.
        """
        return (p.text_width(self.text), p.line_height())

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the line.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        p.text(x, y, max(w, 1.0), h, ALIGN_LEFT | ALIGN_VCENTER, self.text, self.colour)
