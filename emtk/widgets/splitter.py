"""A draggable divider between two resizable panes.

The retained half of :func:`emtk.im_widgets.splitter`. Same control, other
shape: this one *owns* the boundary rather than being handed it and giving it
back, because that is what a retained host has no immediate-mode loop to do
for it.

What it is actually for
-----------------------
Splitting a region is three rectangles and one drag, and the three rectangles
are the part everyone gets slightly wrong -- off by the bar's width, or by
half of it, or right until the window is resized small enough that one pane
inverts. So :meth:`Splitter.split` hands them over already clamped::

    pane1, bar, pane2 = splitter.split(0, 0, 800, 600)
    draw_controls(p, *pane1)
    splitter.draw(p, *bar)
    draw_plots(p, *pane2)

and the host feeds it presses the way it feeds any control. Nothing here
needs a layout pass, a theme or an event loop -- a splitter is a rectangle
that remembers where it was grabbed.
"""

from __future__ import annotations

from ..control import Control
from ..flags import Axis
from ..painter import Painter
from ..style import SEPARATOR, SEPARATOR_ACTIVE, SEPARATOR_HOVERED

__all__ = ["Splitter"]

Rect = tuple[float, float, float, float]


class Splitter(Control):
    """A divider that moves space between two panes when dragged.

    Parameters
    ----------
    size1 : float
        The first pane's size along *axis*, in pixels. Clamped by every call
        to :meth:`split`, so a starting guess is fine and a window resize
        cannot invert the panes.
    axis : int, optional
        :data:`~emtk.flags.Axis.X` for a vertical bar between side-by-side
        panes, :data:`~emtk.flags.Axis.Y` for a horizontal one between
        stacked panes. This is the axis the *sizes* run along, not the bar.
    thickness : float, optional
        The space the divider occupies, which is also the grab target.
    min_size1, min_size2 : float, optional
        How small each pane may get. Both hold at once: a drag stops at
        whichever limit it reaches first rather than collapsing the other.
    bar_margin : float, optional
        Inset the drawn bar by this much on each side, so a comfortable grab
        target is not drawn as a slab. Never thinner than two pixels.
    hover_extend : float, optional
        Grow the hit test by this much either side, along *axis* only. A
        divider thin enough to look tidy is thinner than anyone can hit.

    Attributes
    ----------
    size1 : float
        The first pane's size. Read it for the layout; write it to set the
        boundary. :meth:`split` clamps it.
    hovered, held : bool
        What the bar draws as. The chrome has no ambient pointer state, so
        :meth:`hover` is how it is told -- the rule the package docstring
        sets for every control here.
    """

    def __init__(self, size1: float, axis: int = Axis.X,
                 thickness: float = 12.0, min_size1: float = 0.0,
                 min_size2: float = 0.0, bar_margin: float = 4.0,
                 hover_extend: float = 8.0) -> None:
        self.size1 = float(size1)
        self.axis = 1 if axis == Axis.Y else 0
        self.thickness = float(thickness)
        self.min_size1 = float(min_size1)
        self.min_size2 = float(min_size2)
        self.bar_margin = float(bar_margin)
        self.hover_extend = float(hover_extend)
        self.hovered = False
        self.held = False
        #: Where in the bar the press landed, so the boundary follows the
        #: point that was grabbed instead of jumping to the centre.
        self._grab: float | None = None
        #: The region last split, so a drag can clamp against the total
        #: without the caller passing it a second time.
        self._region: Rect | None = None

    # -- geometry ---------------------------------------------------------- #
    @property
    def size2(self) -> float:
        """The second pane's size, from the last :meth:`split`.

        Derived rather than stored: two sizes and a total is one fact too
        many, and the copy that is not the source of truth is the one that
        goes stale after a resize.
        """
        if self._region is None:
            return 0.0
        return max(0.0, self._total() - self.thickness - self.size1)

    def _total(self) -> float:
        if self._region is None:
            return 0.0
        x, y, w, h = self._region
        return h if self.axis else w

    def clamp(self, total: float | None = None) -> float:
        """Keep :attr:`size1` inside both minimums. Returns it.

        Called by :meth:`split`, so a host that uses that never needs this.
        """
        if total is None:
            total = self._total()
        room = max(0.0, total - self.thickness)
        # `max` after `min`, not before: when the region is too small for
        # both minimums something has to give, and giving pane one its
        # minimum is the arbitrary-but-stable choice. Reversing them makes
        # the boundary jump between the two limits as the window resizes.
        self.size1 = max(self.min_size1, min(self.size1, room - self.min_size2))
        self.size1 = max(0.0, min(self.size1, room))
        return self.size1

    def split(self, x: float, y: float, w: float, h: float) -> tuple[Rect, Rect, Rect]:
        """Divide a region into ``(pane1, bar, pane2)``.

        The three rectangles tile the region exactly -- no gap, no overlap --
        and :attr:`size1` is clamped first, so a region too small for the
        starting sizes gives valid boxes rather than a negative one.

        Parameters
        ----------
        x, y, w, h : float
            The whole region, panes and divider together.

        Returns
        -------
        tuple
            Three ``(x, y, w, h)`` boxes, in order along *axis*.
        """
        self._region = (float(x), float(y), float(w), float(h))
        self.clamp()
        if self.axis:
            top = (x, y, w, self.size1)
            bar = (x, y + self.size1, w, self.thickness)
            bottom = (x, y + self.size1 + self.thickness, w,
                      max(0.0, h - self.size1 - self.thickness))
            return (top, bar, bottom)
        left = (x, y, self.size1, h)
        bar = (x + self.size1, y, self.thickness, h)
        right = (x + self.size1 + self.thickness, y,
                 max(0.0, w - self.size1 - self.thickness), h)
        return (left, bar, right)

    def measure(self, p: Painter) -> tuple[float, float]:
        """The divider's own size. Its long axis is the caller's to decide."""
        return (self.thickness, self.thickness)

    # -- drawing ----------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the bar into the divider's box -- the middle one from
        :meth:`split`."""
        self.remember(x, y, w, h)
        span = self.thickness
        bar = max(2.0, span - self.bar_margin * 2.0)
        inset = (span - bar) * 0.5
        colour = (SEPARATOR_ACTIVE if self.held
                  else SEPARATOR_HOVERED if self.hovered else SEPARATOR)
        if self.axis:
            p.fill_rect(x, y + inset, w, bar, colour)
        else:
            p.fill_rect(x + inset, y, bar, h, colour)

    # -- input ------------------------------------------------------------- #
    def _hit(self, px: float, py: float) -> bool:
        if self._box is None:
            return False
        x, y, w, h = self._box
        if self.hover_extend:
            if self.axis:
                y, h = y - self.hover_extend, h + self.hover_extend * 2.0
            else:
                x, w = x - self.hover_extend, w + self.hover_extend * 2.0
        return x <= px <= x + w and y <= py <= y + h

    def hover(self, px: float, py: float) -> bool:
        """Tell the divider where the pointer is. Returns whether it is on it.

        A held divider stays held wherever the pointer goes, which is what
        makes a drag survive leaving the bar -- and leaving it is the normal
        case, because the bar is thin and the pointer is faster than the
        layout that follows it.
        """
        self.hovered = self.held or self._hit(px, py)
        return self.hovered

    def press(self, px: float, py: float, x: float, y: float, w: float,
              h: float, modifiers: int = 0, clicks: int = 1):
        """Grab the divider. Returns ``self`` if it was hit, else ``None``."""
        self.remember(x, y, w, h)
        if not self._hit(px, py):
            return None
        self.held = True
        self.hovered = True
        origin = y if self.axis else x
        self._grab = (py if self.axis else px) - origin
        return self

    def drag(self, px: float, py: float, x: float, y: float, w: float,
             h: float):
        """Move the boundary. Returns ``(size1, size2)``, or ``None`` if the
        divider is not held."""
        if not self.held or self._grab is None:
            return None
        self.remember(x, y, w, h)
        origin = y if self.axis else x
        pointer = py if self.axis else px
        self.size1 += pointer - self._grab - origin
        self.clamp()
        return (self.size1, self.size2)

    def release(self) -> None:
        """Let go. The grab point goes with it, so the next press is measured
        from wherever *it* lands."""
        self.held = False
        self._grab = None
