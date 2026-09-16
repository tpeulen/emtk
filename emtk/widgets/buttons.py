"""The button family, ported from the reference implementation's *Widgets: Main*.

What is here
------------
* :class:`ButtonState` -- the reference's ``ButtonBehavior`` reduced to the
  three states a painter actually needs: *hovered*, *held*, *activated*.
* :class:`SmallButton` -- a button with no vertical frame padding, so it sits
  inside a line of text.
* :class:`InvisibleButton` -- a hit box that paints nothing.
* :class:`ArrowButton` -- a framed button carrying a triangular arrow.
* :class:`CheckboxFlags` -- a checkbox over a bitmask, with the reference's
  *mixed* state.
* :class:`RadioButton` -- the single-button form, which does **not** own the
  exclusivity (that is the host's, or :class:`~.widgets.RadioGroup`'s).

The list dot is **not** here: ``Bullet`` and ``BulletText`` live in
:mod:`.text`, beside the other things that are a glyph plus a caption.
The reference files ``Bullet()`` under Main and ``BulletText()`` under
Text, which would split one dot across two modules; keeping both in
``text`` is the one change of address in this port.

Why hovering is a method
------------------------
The reference recomputes ``hovered`` every frame from a mouse position it is
handed on every frame. emtk has no such feed: the chrome is repainted when it
changes, and the host delivers *presses*, not motion. Inferring hover from the
press position alone would be wrong in the one direction that matters -- a
button would stay lit long after the pointer left it.

So hovering is explicit: a host that tracks the pointer calls
:meth:`ButtonState.hover` (or the control's ``hover``) and gets the reference's
three-state colouring; a host that does not never calls it and gets a control
that is simply never in the hovered colour. A press always sets the hover state
too, because a press *is* a position sample, and that is what makes the
reference's ``(held && hovered) ? Active : hovered ? Hovered : Base`` formula
give a visible pressed state without a motion feed.

What the six painter operations cannot express
----------------------------------------------
``Image`` and ``ImageButton`` live in this section of the reference and are
**not** ported: the painter has no image operation, and a fake -- a coloured
rectangle where a texture belongs -- would be a control that silently draws the
wrong thing. Everything round or diagonal (the arrow, the radio dot, the check
mark) is approximated from axis-aligned rectangles; each such approximation is
described where it is drawn.
"""
from __future__ import annotations

import math

from ..painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER, Colour, Painter
from ..style import (
    BORDER,
    BUTTON,
    BUTTON_ACTIVE,
    BUTTON_HOVERED,
    CHECK_MARK,
    FRAME_BG,
    FRAME_BG_ACTIVE,
    FRAME_BG_HOVERED,
    TEXT,
    clamp,
    disc,
    fit_text,
    hit,
)

__all__ = [
    "DIR_LEFT",
    "DIR_RIGHT",
    "DIR_UP",
    "DIR_DOWN",
    "ButtonState",
    "SmallButton",
    "InvisibleButton",
    "ArrowButton",
    "CheckboxFlags",
    "RadioButton",
]

#: The four directions an :class:`ArrowButton` can point, numbered as the
#: reference's ``ImGuiDir`` is so a port can be read against it.
DIR_LEFT = 0
DIR_RIGHT = 1
DIR_UP = 2
DIR_DOWN = 3

#: The reference's ``style.FramePadding``: how far a framed control's contents
#: sit inside its frame.
_FRAME_PAD_X = 4.0

#: The gap between a control's frame and its label, the reference's
#: ``style.ItemInnerSpacing.x``.
_INNER_SPACING = 6.0

#: How many rectangles an approximated shape is allowed to cost. A disc and an
#: arrow are drawn as a stack of bands; more bands is smoother and slower, and
#: past this many the difference stops being visible at chrome sizes.
_MAX_BANDS = 9


# --------------------------------------------------------------------------
# Shape approximations
# --------------------------------------------------------------------------
#: The shared scan-converted circle. Lived here first; promoted to
#: :mod:`.style` when the ported text family turned out to draw its list
#: bullet as an inscribed square, so the same dot had two silhouettes.
_disc = disc


def _check_mark(p: Painter, x: float, y: float, size: float, colour: Colour) -> None:
    """Draw a tick as a staircase of small squares.

    The reference's ``RenderCheckMark`` is two thick line segments -- a short
    one down-right and a long one up-right. There is no line operation and no
    rotation, so each segment is walked in even steps and a square of the
    segment's thickness is stamped at every step. At checkbox sizes the
    staircase is what a rasterised diagonal looks like anyway.

    Parameters
    ----------
    p : Painter
        Where to draw.
    x, y : float
        Top-left of the square the tick is inscribed in.
    size : float
        Side of that square.
    colour : Colour
        Tick colour.
    """
    if size <= 0.0:
        return
    thickness = max(size / 5.0, 1.0)
    span = size - thickness * 0.5
    left = x + thickness * 0.25
    top = y + thickness * 0.25
    third = span / 3.0
    # The three corners of the tick, in the reference's proportions.
    ax, ay = left, top + span - 1.5 * third
    bx, by = left + third, top + span - 0.5 * third
    cx, cy = left + 3.0 * third, top + span - 2.5 * third
    for (x0, y0, x1, y1, steps) in ((ax, ay, bx, by, 3), (bx, by, cx, cy, 6)):
        for index in range(steps + 1):
            t = index / float(steps)
            px = x0 + (x1 - x0) * t
            py = y0 + (y1 - y0) * t
            p.fill_rect(px - thickness * 0.5, py - thickness * 0.5, thickness, thickness, colour)


def _arrow(
    p: Painter,
    cx: float,
    cy: float,
    glyph: float,
    direction: int,
    colour: Colour,
) -> None:
    """Draw a triangular arrow as a stack of tapering bands.

    There is no triangle operation, so the triangle the reference draws --
    ``0.866r`` half-base by ``0.750r`` half-height, ``r = 0.4 * font_size`` --
    is sliced perpendicular to the direction it points and each slice drawn as
    one rectangle whose extent is the triangle's width there. Up and down taper
    in width across horizontal bands; left and right taper in height across
    vertical ones, which is what makes the four directions distinguishable from
    the emitted rectangles alone.

    Parameters
    ----------
    p : Painter
        Where to draw.
    cx, cy : float
        Centre of the glyph box.
    glyph : float
        Side of that box; the arrow is drawn to the reference's fractions of it.
    direction : int
        One of :data:`DIR_LEFT`, :data:`DIR_RIGHT`, :data:`DIR_UP`,
        :data:`DIR_DOWN`. Anything else draws nothing, matching the reference's
        refusal to render ``ImGuiDir_None``.
    colour : Colour
        Fill colour.
    """
    if glyph <= 0.0 or direction not in (DIR_LEFT, DIR_RIGHT, DIR_UP, DIR_DOWN):
        return
    radius = glyph * 0.40
    base = 2.0 * 0.866 * radius
    depth = 2.0 * 0.750 * radius
    bands = int(clamp(round(depth), 3, _MAX_BANDS))

    if direction in (DIR_UP, DIR_DOWN):
        step = depth / bands
        top = cy - depth * 0.5
        for index in range(bands):
            grow = (index + 1) / bands if direction == DIR_UP else (bands - index) / bands
            width = base * grow
            p.fill_rect(cx - width * 0.5, top + index * step, width, step, colour)
        return

    step = depth / bands
    left = cx - depth * 0.5
    for index in range(bands):
        grow = (index + 1) / bands if direction == DIR_LEFT else (bands - index) / bands
        height = base * grow
        p.fill_rect(left + index * step, cy - height * 0.5, step, height, colour)


# --------------------------------------------------------------------------
# The shared behaviour
# --------------------------------------------------------------------------
class ButtonState:
    """The reference's ``ButtonBehavior``, kept as retained state.

    The reference computes hovered/held/pressed every frame from a whole input
    context: mouse buttons, keyboard navigation, drag-and-drop holds, key
    owners, repeat timers. None of that exists here, and most of it never will
    -- the chrome is repainted on change and handed presses, not frames. What
    survives the reduction is the part the *painting* depends on:

    ``hovered``
        The pointer is over the control. Set by :meth:`hover` and by any press,
        because a press is a position sample too. Without it the reference's
        colour formula could never reach its active colour and a pressed button
        would look untouched.
    ``held``
        The control has the press. Set by a press inside, cleared by
        :meth:`release` and by a press that lands elsewhere.
    ``activated``
        This press is the one that took the hold -- the reference's
        ``IsItemActivated``. It distinguishes "the button went down now" from
        "the button is still down", which is what a repeat or a drag start
        needs.

    Notes
    -----
    Firing happens on *press*, not on click-release. The reference's default is
    ``PressedOnClickRelease`` -- press inside, release inside, then it counts --
    which needs a release that carries a position, delivered on the same
    control that took the press. a host routes a release to whatever
    they last gave the press to and carry no coordinates, so the release half
    of that contract cannot be honoured; offering it anyway would mean two ways
    for a control to fire, and one of them silently never doing so. Pressing is
    the reference's ``ImGuiButtonFlags_PressedOnClick``, which it supports for
    exactly this reason.
    """

    def __init__(self) -> None:
        self.hovered = False
        self.held = False
        self.activated = False

    def hover(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Tell the control where the pointer is.

        Parameters
        ----------
        x, y : float
            The pointer.
        box_x, box_y, box_w, box_h : float
            The box the control was last drawn into.

        Returns
        -------
        bool
            Whether the pointer is over the control.
        """
        self.hovered = hit(x, y, box_x, box_y, box_w, box_h)
        return self.hovered

    def press(
        self,
        x: float,
        y: float,
        box_x: float,
        box_y: float,
        box_w: float,
        box_h: float,
    ) -> bool:
        """Take a press.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the control was last drawn into.

        Returns
        -------
        bool
            Whether the press was inside -- which is also whether the control
            fires.
        """
        inside = hit(x, y, box_x, box_y, box_w, box_h)
        self.activated = inside and not self.held
        self.held = inside
        self.hovered = inside
        return inside

    def release(self) -> None:
        """Let go. The hover state is left alone: the pointer has not moved."""
        self.held = False
        self.activated = False

    def background(
        self,
        base: Colour = BUTTON,
        hovered: Colour = BUTTON_HOVERED,
        active: Colour = BUTTON_ACTIVE,
    ) -> Colour:
        """Pick the frame colour for the current state.

        This is the reference's own expression, kept literally:
        ``(held && hovered) ? Active : hovered ? Hovered : Base``. Held but not
        hovered -- the pointer was dragged off the control without releasing --
        deliberately falls back to the base colour, which is how the reference
        says "let go here and nothing happens".

        Parameters
        ----------
        base, hovered, active : Colour
            The three colours of the control's role.

        Returns
        -------
        Colour
            One of them.
        """
        if self.held and self.hovered:
            return active
        if self.hovered:
            return hovered
        return base


# --------------------------------------------------------------------------
# The controls
# --------------------------------------------------------------------------
class SmallButton:
    """A button sized to fit inside a line of text.

    The reference builds this by zeroing ``FramePadding.y`` for one call: the
    frame is exactly as tall as the text, so a small button dropped in a
    sentence does not push the line apart. Here the box is given by the host,
    so the frame is drawn one line tall and centred in it, and :meth:`size`
    reports what the host should have reserved.

    Parameters
    ----------
    label : str
        Caption.
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.state = ButtonState()

    def size(self, p: Painter) -> tuple[float, float]:
        """Measure the ``(width, height)`` the button wants.

        Parameters
        ----------
        p : Painter
            Used to measure the caption.

        Returns
        -------
        tuple of float
            Caption width plus horizontal padding, by one line height.
        """
        return (p.text_width(self.label) + _FRAME_PAD_X * 2.0, p.line_height())

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame and the caption.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        frame_h = min(h, p.line_height())
        frame_y = y + (h - frame_h) * 0.5
        p.stroke_rect(x, frame_y, w, frame_h, BORDER, self.state.background())
        p.text(x, frame_y, w, frame_h, ALIGN_CENTER,
               fit_text(p, self.label, w - _FRAME_PAD_X * 2.0), TEXT)

    def hover(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Tell the button where the pointer is. Returns whether it is over it."""
        return self.state.hover(x, y, box_x, box_y, box_w, box_h)

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Process a press. Returns whether the button fired."""
        return self.state.press(x, y, box_x, box_y, box_w, box_h)

    def release(self) -> None:
        """Release the hold."""
        self.state.release()


class InvisibleButton:
    """A hit box that paints nothing.

    This is not a button someone forgot to style. The reference offers it so a
    caller that draws its *own* graphics -- a splitter bar, a custom-drawn
    item, a region of a plot, a drag surface -- can still get the whole button
    behaviour over it: hovered, held, activated, and a press it can act on. The
    drawing is the caller's; only the behaviour is the widget's. It is also the
    reference's standard way of reserving an area of a layout that reacts.

    Consequently :meth:`draw` emits nothing at all, and that is the invariant
    worth testing: a control whose whole contract is "no marks, but it still
    answers" fails silently the moment someone adds a helpful outline to it.

    Parameters
    ----------
    name : str, optional
        An identifier for the host's benefit; the reference's ``str_id``. Never
        drawn.
    """

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.state = ButtonState()

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint nothing.

        Parameters
        ----------
        p : Painter
            Unused; the signature is the family's.
        x, y, w, h : float
            The box. Unused for the same reason.
        """

    def hover(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Tell the button where the pointer is. Returns whether it is over it."""
        return self.state.hover(x, y, box_x, box_y, box_w, box_h)

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Process a press. Returns whether the press landed inside."""
        return self.state.press(x, y, box_x, box_y, box_w, box_h)

    def release(self) -> None:
        """Release the hold."""
        self.state.release()


class ArrowButton:
    """A square button carrying an arrow, for steppers and disclosure.

    Parameters
    ----------
    direction : int, optional
        :data:`DIR_LEFT`, :data:`DIR_RIGHT`, :data:`DIR_UP` or
        :data:`DIR_DOWN`.

    Notes
    -----
    The arrow is a triangle in the reference and there is no triangle
    operation here, so it is drawn as a stack of tapering rectangles -- see
    :func:`_arrow` for the geometry. The taper runs along the direction of
    travel, so the widest band of an up arrow is its bottom one and of a down
    arrow its top one.
    """

    def __init__(self, direction: int = DIR_RIGHT) -> None:
        self.direction = int(direction)
        self.state = ButtonState()

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the frame and the arrow.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        p.stroke_rect(x, y, w, h, BORDER, self.state.background())
        _arrow(p, x + w * 0.5, y + h * 0.5, min(w, h), self.direction, TEXT)

    def hover(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Tell the button where the pointer is. Returns whether it is over it."""
        return self.state.hover(x, y, box_x, box_y, box_w, box_h)

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Process a press. Returns whether the button fired."""
        return self.state.press(x, y, box_x, box_y, box_w, box_h)

    def release(self) -> None:
        """Release the hold."""
        self.state.release()


class CheckboxFlags:
    """A checkbox over one or more bits of a bitmask.

    Parameters
    ----------
    label : str
        Caption drawn after the square.
    flags : int, optional
        The whole mask the control edits.
    flags_value : int, optional
        The bits this checkbox owns. More than one bit is the interesting case.

    Notes
    -----
    Three states, from the reference's ``CheckboxFlagsT``: every owned bit set
    (*all*), none set (*none*), and some but not all (*mixed* -- the
    reference's undocumented tri-state, drawn as a filled inner square rather
    than a tick).

    The cycle a press produces is the reference's and is **not** a three-way
    rotation: the widget hands the checkbox ``all_on``, which is false in the
    mixed state, so a press on a mixed checkbox turns *every* owned bit on, and
    the next press turns them all off. Mixed is a state the data can be in, not
    one a click can return to -- which is exactly right, because there is no
    single answer to which subset "back to mixed" would mean.
    """

    def __init__(self, label: str, flags: int = 0, flags_value: int = 0) -> None:
        self.label = label
        self.flags = int(flags)
        self.flags_value = int(flags_value)
        self.state = ButtonState()

    @property
    def all_on(self) -> bool:
        """Whether every bit this checkbox owns is set."""
        return (self.flags & self.flags_value) == self.flags_value

    @property
    def any_on(self) -> bool:
        """Whether any bit this checkbox owns is set."""
        return (self.flags & self.flags_value) != 0

    @property
    def mixed(self) -> bool:
        """Whether some but not all of the owned bits are set."""
        return self.any_on and not self.all_on

    def toggle(self) -> int:
        """Apply one press to the mask.

        Returns
        -------
        int
            The whole mask afterwards. Mixed and none both become all; all
            becomes none.
        """
        if self.all_on:
            self.flags &= ~self.flags_value
        else:
            self.flags |= self.flags_value
        return self.flags

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the square, its mark and the caption.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        square = min(h, max(w, 1.0))
        square_y = y + (h - square) * 0.5
        p.stroke_rect(x, square_y, square, square, BORDER,
                      self.state.background(FRAME_BG, FRAME_BG_HOVERED, FRAME_BG_ACTIVE))
        if self.mixed:
            pad = max(1.0, math.trunc(square / 3.6))
            p.fill_rect(x + pad, square_y + pad, square - pad * 2.0, square - pad * 2.0, CHECK_MARK)
        elif self.all_on:
            pad = max(1.0, math.trunc(square / 6.0))
            _check_mark(p, x + pad, square_y + pad, square - pad * 2.0, CHECK_MARK)
        if self.label:
            left = x + square + _INNER_SPACING
            p.text(left, y, max(x + w - left, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, max(x + w - left, 1.0)), TEXT)

    def hover(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Tell the checkbox where the pointer is. Returns whether it is over it."""
        return self.state.hover(x, y, box_x, box_y, box_w, box_h)

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> int:
        """Process a press.

        Parameters
        ----------
        x, y : float
            Where the press landed.
        box_x, box_y, box_w, box_h : float
            The box the checkbox was last drawn into.

        Returns
        -------
        int
            The whole mask, changed if the press was inside and unchanged if it
            was not -- a value control returns its value, so a caller can store
            the result without asking whether anything happened.
        """
        if self.state.press(x, y, box_x, box_y, box_w, box_h):
            return self.toggle()
        return self.flags

    def release(self) -> None:
        """Release the hold."""
        self.state.release()


class RadioButton:
    """One radio button: a dot that is on or off, with a caption.

    Parameters
    ----------
    label : str
        Caption drawn after the dot.
    active : bool, optional
        Whether this one is the chosen one.

    Notes
    -----
    This is the reference's single-button form, and like it the button does
    **not** own the exclusivity: a radio button that turned its neighbours off
    would have to know who they are. Pressing it makes it active and reports
    the press; switching the others off is the host's, which is what the
    reference's ``RadioButton(label, &v, v_button)`` overload does by writing
    one shared variable. :class:`~.widgets.RadioGroup` is the packaged form for
    a host that just wants a row of choices; this is for the case where the
    choices are laid out among other things and each has its own box.

    A press on an already-active button reports the press and leaves it active:
    radio buttons do not toggle off.

    The dot is a circle in the reference and there is no circle operation, so
    both the well and the dot are scan-converted into horizontal bands -- see
    :func:`_disc`.
    """

    def __init__(self, label: str, active: bool = False) -> None:
        self.label = label
        self.active = bool(active)
        self.state = ButtonState()

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the well, the dot when active, and the caption.

        Parameters
        ----------
        p : Painter
            Where to draw.
        x, y, w, h : float
            The box.
        """
        square = min(h, max(w, 1.0))
        radius = (square - 1.0) * 0.5
        cx = x + square * 0.5
        cy = y + h * 0.5
        _disc(p, cx, cy, radius,
              self.state.background(FRAME_BG, FRAME_BG_HOVERED, FRAME_BG_ACTIVE))
        if self.active:
            pad = max(1.0, math.trunc(square / 6.0))
            _disc(p, cx, cy, radius - pad, CHECK_MARK)
        if self.label:
            left = x + square + _INNER_SPACING
            p.text(left, y, max(x + w - left, 1.0), h, ALIGN_VCENTER | ALIGN_LEFT,
                   fit_text(p, self.label, max(x + w - left, 1.0)), TEXT)

    def hover(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Tell the button where the pointer is. Returns whether it is over it."""
        return self.state.hover(x, y, box_x, box_y, box_w, box_h)

    def press(self, x: float, y: float, box_x: float, box_y: float,
              box_w: float, box_h: float) -> bool:
        """Process a press. Returns whether it fired, and makes the button active."""
        if self.state.press(x, y, box_x, box_y, box_w, box_h):
            self.active = True
            return True
        return False

    def release(self) -> None:
        """Release the hold."""
        self.state.release()
