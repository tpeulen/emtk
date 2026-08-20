"""The contract every ported control follows, as a class instead of a habit.

Why this exists now and not at the start
----------------------------------------
The package docstring states the contract in prose: a control is a retained
object that draws into a box, is handed the presses that land in that box, and
takes anything the chrome has no feed for -- hover, a clock, a click count --
as an explicit argument. Fourteen modules were written against that prose, and
they agree, because one person held it in mind each time.

That stops scaling at the point where porting is supposed to become *routine*.
The prose does not tell a new port what the default :meth:`press` should return
when nothing was hit, or that geometry from the last draw has to be stored
because a press arrives with no idea where the control was drawn -- and those
are exactly the two things every port re-derives.

So the contract is a base class. It is deliberately thin: five methods, none of
them abstract except :meth:`draw`, and no layout, no theme, no event loop. A
control that needs none of it can still be a plain object -- the existing
fourteen are, and nothing here asks them to change. It is scaffolding for what
comes next, not a retrofit of what is already working.

What it gives a port
--------------------
* the geometry of the last draw, so :meth:`contains` and any hit test work
  without the caller passing the box a second time;
* no-op :meth:`press`, :meth:`drag`, :meth:`release`, :meth:`key` and
  :meth:`scroll`, so a control implements only the ones it has;
* :meth:`measure`, so a host that can grant a control its preferred size has
  something to ask.

Used by ``tools/port_imgui_widget.py``, which scaffolds a port
as a subclass of this and leaves the algorithms to be filled in.
"""
from __future__ import annotations

from .painter import Painter
from .style import hit

__all__ = ["Control"]


class Control:
    """Base class for a painter-level control.

    Subclasses implement :meth:`draw` and override whichever of the input
    methods they respond to.
    """

    #: Set by :meth:`draw` through :meth:`remember`; ``None`` until first drawn.
    _box: tuple[float, float, float, float] | None = None

    # -- geometry ------------------------------------------------------- #
    def remember(self, x: float, y: float, w: float, h: float) -> None:
        """Record where this control was drawn.

        Every :meth:`draw` should call this first. A press arrives in window
        coordinates with no memory of the layout that produced them, so a
        control that does not remember its box either has to be handed it again
        by the caller -- which every caller then has to keep -- or hit-tests
        against stale numbers, which is the failure that looks like "clicks land
        one row off".
        """
        self._box = (float(x), float(y), float(w), float(h))

    @property
    def box(self) -> tuple[float, float, float, float] | None:
        """The last drawn box, or ``None`` if it has never been drawn."""
        return self._box

    def contains(self, px: float, py: float) -> bool:
        """Whether a point is inside the last drawn box."""
        if self._box is None:
            return False
        return hit(px, py, *self._box)

    def measure(self, p: Painter) -> tuple[float, float]:
        """The size this control would like, in pixels.

        Parameters
        ----------
        p : Painter
            Asked for its metrics; a control's preferred size is almost always
            a multiple of the line height or the glyph width.

        Returns
        -------
        tuple of float
            ``(width, height)``. The default is one text line tall and wide
            enough for a short label, which is what most one-row controls want.
        """
        return (12.0 * p.text_width("W"), p.line_height())

    # -- the contract --------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the control into a box.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box.

        Raises
        ------
        NotImplementedError
            Always, in the base class -- drawing is the one thing a control
            cannot inherit.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement draw()")

    def press(
        self,
        px: float,
        py: float,
        x: float,
        y: float,
        w: float,
        h: float,
        modifiers: int = 0,
        clicks: int = 1,
    ):
        """Handle a press inside the box.

        Parameters
        ----------
        px, py : float
            The pointer.
        x, y, w, h : float
            The box the control was drawn in, passed again so a stateless
            caller need not have kept it.
        modifiers : int, optional
            A mask of :mod:`cmtk.events`' ``*_MODIFIER`` values.
        clicks : int, optional
            1, 2 or 3. An explicit argument because the chrome has no clock to
            derive a double-click from -- the rule the package docstring sets.

        Returns
        -------
        object or None
            Whatever the caller can act on; ``None`` when the press did not
            land on anything. Returning ``None`` rather than ``False`` matters:
            a control that returns an index has ``0`` as a valid answer, and
            ``if control.press(...)`` would drop it.
        """
        return None

    def drag(self, px: float, py: float, x: float, y: float, w: float, h: float):
        """Handle the pointer moving with the button held. Returns as :meth:`press`."""
        return None

    def release(self) -> None:
        """Handle the button coming up. Nothing by default."""

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press.

        Returns
        -------
        bool
            Whether the control consumed it. The default is ``False`` -- a
            control that does not edit text must let a keystroke through to the
            viewport's shortcuts, and a control that *does* consumes everything
            (see :class:`~.text_field.TextField` for why).
        """
        return False

    def scroll(self, amount: int) -> int:
        """Handle a wheel notch. Returns the new scroll position; zero by default."""
        return 0
