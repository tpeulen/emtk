"""Mouse buttons and keyboard modifiers, as plain integers.

Why the engine owns these
-------------------------
The panel's hit-testing and the mouse-mode table decide what a click *means*:
which row it landed on, and whether ctrl+shift+left is ``CtSh``'s left cell or
``Ctrl``'s. That is arithmetic over a table, and it was the last thing in
a host engine that reached for a GUI toolkit -- a mouse-mode table importing Qt
inside three functions purely to compare against ``Qt.LeftButton`` and
``Qt.ControlModifier``.

The values below are fixed by Qt's ABI, so nothing is lost by writing them out,
and what is gained is that the engine can decide what a click means with no
window system present. A browser reports a different set (DOM ``button`` is
0/1/2 and its modifiers are booleans), so a second host translates into *these*
rather than the engine learning a second vocabulary.

Named ``host`` rather than ``platform``: a package called ``platform`` beside
modules that are sometimes imported with their own directory on ``sys.path``
would shadow the standard library's, which is a failure this repository has
already paid for once with ``chisurf/math/`` and the stdlib ``math``.
"""
from __future__ import annotations

__all__ = [
    "NO_BUTTON",
    "LEFT_BUTTON",
    "RIGHT_BUTTON",
    "MIDDLE_BUTTON",
    "NO_MODIFIER",
    "SHIFT_MODIFIER",
    "CONTROL_MODIFIER",
    "ALT_MODIFIER",
    "META_MODIFIER",
    "KeyEvent",
    "Point",
    "PointerEvent",
    "Rect",
    "button_from_canvas",
    "button_from_dom",
    "button_name",
    "buttons_from_dom",
    "modifier_name",
    "modifiers_from_canvas",
]

#: Mouse buttons. These are ``Qt.LeftButton`` and friends -- note that middle
#: is 4 and right is 2, which is the ordering a hand-written table gets wrong.
NO_BUTTON = 0
LEFT_BUTTON = 1
RIGHT_BUTTON = 2
MIDDLE_BUTTON = 4

#: Keyboard modifiers, as ``Qt.KeyboardModifier`` spells them.
NO_MODIFIER = 0x00000000
SHIFT_MODIFIER = 0x02000000
CONTROL_MODIFIER = 0x04000000
ALT_MODIFIER = 0x08000000
META_MODIFIER = 0x10000000

#: PyMOL's modifier row names, most specific first.
#:
#: The order is the point: ctrl+shift is its own row (``CtSh``), not a ctrl row
#: that happens to have shift held, so the combination has to be tested before
#: either of its parts.
_MODIFIER_ROWS: tuple[tuple[str, int], ...] = (
    ("ctsh", CONTROL_MODIFIER | SHIFT_MODIFIER),
    ("ctrl", CONTROL_MODIFIER),
    ("shft", SHIFT_MODIFIER),
    ("alt", ALT_MODIFIER),
)

#: PyMOL's button names.
_BUTTON_NAMES: tuple[tuple[int, str], ...] = (
    (LEFT_BUTTON, "l"),
    (MIDDLE_BUTTON, "m"),
    (RIGHT_BUTTON, "r"),
)


def button_name(button) -> str:
    """Return PyMOL's name for a mouse button.

    Parameters
    ----------
    button : int
        One of the ``*_BUTTON`` constants. A Qt button enum compares equal to
        its integer value, so a Qt event's ``button()`` may be passed directly.

    Returns
    -------
    str
        ``"l"``, ``"m"``, ``"r"``, or ``""`` for anything else.
    """
    for value, name in _BUTTON_NAMES:
        if int(button) == value:
            return name
    return ""


def modifier_name(modifiers) -> str:
    """Return PyMOL's name for a modifier state.

    Parameters
    ----------
    modifiers : int
        A mask of the ``*_MODIFIER`` constants.

    Returns
    -------
    str
        ``"ctsh"``, ``"ctrl"``, ``"shft"``, ``"alt"`` or ``"none"``.
    """
    value = int(modifiers)
    for name, mask in _MODIFIER_ROWS:
        if (value & mask) == mask:
            return name
    return "none"


#: ``rendercanvas``' button numbers -- the jupyter-rfb vocabulary, which a
#: browser and every desktop backend it ships share. Note that it is *not* the
#: DOM's ``MouseEvent.button`` (0/1/2) and *not* Qt's mask (1/2/4): middle is 3
#: here, and getting that wrong silently binds the wrong mode-table cell.
_CANVAS_BUTTONS: dict[int, int] = {
    1: LEFT_BUTTON,
    2: RIGHT_BUTTON,
    3: MIDDLE_BUTTON,
}

#: ``rendercanvas``' modifier names, which are the DOM's.
_CANVAS_MODIFIERS: dict[str, int] = {
    "Shift": SHIFT_MODIFIER,
    "Control": CONTROL_MODIFIER,
    "Alt": ALT_MODIFIER,
    "Meta": META_MODIFIER,
}


def button_from_canvas(button) -> int:
    """Translate a ``rendercanvas`` button number into the engine's.

    Parameters
    ----------
    button : int
        ``1`` left, ``2`` right, ``3`` middle.

    Returns
    -------
    int
        One of the ``*_BUTTON`` constants, or :data:`NO_BUTTON`.
    """
    try:
        return _CANVAS_BUTTONS.get(int(button), NO_BUTTON)
    except (TypeError, ValueError):
        return NO_BUTTON


#: The DOM's ``MouseEvent.button``, which is a third vocabulary again: 0 left,
#: 1 middle, 2 right. Written out rather than derived, because the three
#: numberings agree on nothing -- Qt's mask is 1/2/4, ``rendercanvas`` is 1/2/3,
#: the DOM is 0/1/2 -- and a table that looks plausible in any two of them binds
#: the wrong mouse-mode cell in the third.
_DOM_BUTTONS: dict[int, int] = {
    0: LEFT_BUTTON,
    1: MIDDLE_BUTTON,
    2: RIGHT_BUTTON,
}


def button_from_dom(button) -> int:
    """Translate a DOM ``MouseEvent.button`` into the engine's.

    Parameters
    ----------
    button : int
        ``0`` left, ``1`` middle, ``2`` right.

    Returns
    -------
    int
        One of the ``*_BUTTON`` constants, or :data:`NO_BUTTON`.
    """
    try:
        return _DOM_BUTTONS.get(int(button), NO_BUTTON)
    except (TypeError, ValueError):
        return NO_BUTTON


def buttons_from_dom(buttons) -> int:
    """Translate a DOM ``MouseEvent.buttons`` mask into the engine's.

    The two masks happen to agree bit for bit -- 1 left, 2 right, 4 middle --
    and that is precisely why this is written out rather than passed through: a
    coincidence nobody has stated is one the next edit breaks silently, and the
    symptom would be a drag doing what a different mouse-mode cell promises.

    Parameters
    ----------
    buttons : int
        The DOM's held-button mask.

    Returns
    -------
    int
        A mask of the ``*_BUTTON`` constants.
    """
    try:
        value = int(buttons)
    except (TypeError, ValueError):
        return NO_BUTTON
    mask = NO_BUTTON
    for bit, engine in ((1, LEFT_BUTTON), (2, RIGHT_BUTTON), (4, MIDDLE_BUTTON)):
        if value & bit:
            mask |= engine
    return mask


def modifiers_from_canvas(modifiers) -> int:
    """Pack ``rendercanvas``' modifier names into an engine mask.

    Parameters
    ----------
    modifiers : iterable of str
        ``("Shift", "Control", ...)`` as the canvas reports them.

    Returns
    -------
    int
        A mask of the ``*_MODIFIER`` constants.
    """
    mask = NO_MODIFIER
    for name in modifiers or ():
        mask |= _CANVAS_MODIFIERS.get(str(name), 0)
    return mask


class Point:
    """A point in viewport pixels, spelled as a toolkit's is.

    Parameters
    ----------
    x, y : float
        Position in the viewport's logical pixels.
    """

    __slots__ = ("_x", "_y")

    def __init__(self, x: float, y: float) -> None:
        self._x = float(x)
        self._y = float(y)

    def x(self) -> float:
        """Horizontal position, in logical pixels."""
        return self._x

    def y(self) -> float:
        """Vertical position, in logical pixels."""
        return self._y

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        """Return a reconstructable representation."""
        return f"Point({self._x!r}, {self._y!r})"


class Rect:
    """An axis-aligned rectangle in viewport pixels.

    Why this exists
    ---------------
    Two things in the viewport are rectangles the *engine* decides: the
    rubber-band selection box and the column a traced frame is shown in. Both
    were ``QRect``, which is what tied the drag handlers -- pure arithmetic over
    a mode table -- to a window system.

    The spelling is deliberately Qt's, including the half-pixel convention that
    :meth:`right` is ``x + width - 1``: a rectangle handed to
    ``Viewer.handle_rect_selection`` reaches the same picker either way, and a
    silent off-by-one there selects a different set of residues than the box
    that was drawn.

    Parameters
    ----------
    x, y : float
        Top-left corner.
    width, height : float
        Extent. May be negative; see :meth:`normalized`.
    """

    __slots__ = ("_x", "_y", "_w", "_h")

    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self._x = float(x)
        self._y = float(y)
        self._w = float(width)
        self._h = float(height)

    @classmethod
    def from_corners(cls, x0: float, y0: float, x1: float, y1: float) -> Rect:
        """Build a normalised rectangle spanning two corners.

        Parameters
        ----------
        x0, y0, x1, y1 : float
            The two corners, in either order.

        Returns
        -------
        Rect
            Inclusive of both corners, as ``QRect(p0, p1)`` is -- so a drag of
            one pixel is one pixel wide, not zero.
        """
        left, right = (x0, x1) if x0 <= x1 else (x1, x0)
        top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
        return cls(left, top, right - left + 1.0, bottom - top + 1.0)

    def x(self) -> float:
        """Left edge."""
        return self._x

    def y(self) -> float:
        """Top edge."""
        return self._y

    def left(self) -> float:
        """Left edge."""
        return self._x

    def top(self) -> float:
        """Top edge."""
        return self._y

    def right(self) -> float:
        """Right edge, inclusive -- ``x + width - 1``, as ``QRect`` has it."""
        return self._x + self._w - 1.0

    def bottom(self) -> float:
        """Bottom edge, inclusive."""
        return self._y + self._h - 1.0

    def width(self) -> float:
        """Extent along x."""
        return self._w

    def height(self) -> float:
        """Extent along y."""
        return self._h

    def isNull(self) -> bool:  # noqa: N802 - the toolkit spelling
        """Whether the rectangle has no extent at all."""
        return self._w == 0.0 and self._h == 0.0

    def normalized(self) -> Rect:
        """Return an equivalent rectangle with non-negative extents."""
        x, w = (self._x, self._w) if self._w >= 0 else (self._x + self._w, -self._w)
        y, h = (self._y, self._h) if self._h >= 0 else (self._y + self._h, -self._h)
        return Rect(x, y, w, h)

    def getRect(self) -> tuple[float, float, float, float]:  # noqa: N802 - Qt spelling
        """Return ``(x, y, width, height)``."""
        return (self._x, self._y, self._w, self._h)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        """Return a reconstructable representation."""
        return f"Rect({self._x!r}, {self._y!r}, {self._w!r}, {self._h!r})"


class PointerEvent:
    """One press, move, release or click, in the engine's own vocabulary.

    Why this exists
    ---------------
    ``Viewer.handle_mouse_click`` and the picker take an *event*: they ask it
    where the pointer was and which modifiers were held. That was a
    ``QMouseEvent``, which is the reason a click could not be delivered without
    a window system -- not because picking needs Qt (it is a projection and an
    ``argmin``) but because the argument did.

    The accessors are Qt's names because that is what the call sites already
    speak, and a real ``QMouseEvent`` therefore remains an equally valid
    argument -- which is what keeps the Qt host's own tests meaningful.

    Parameters
    ----------
    x, y : float
        Pointer position, in the viewport's logical pixels.
    button : int, optional
        The button that changed; one of the ``*_BUTTON`` constants.
    buttons : int, optional
        Mask of the buttons currently held.
    modifiers : int, optional
        Mask of the ``*_MODIFIER`` constants.
    double : bool, optional
        Whether this press is the second of a double click.
    """

    __slots__ = ("_pos", "_button", "_buttons", "_modifiers", "_double", "_accepted")

    def __init__(
        self,
        x: float,
        y: float,
        button: int = NO_BUTTON,
        buttons: int = NO_BUTTON,
        modifiers: int = NO_MODIFIER,
        double: bool = False,
    ) -> None:
        self._pos = Point(x, y)
        self._button = int(button)
        self._buttons = int(buttons)
        self._modifiers = int(modifiers)
        self._double = bool(double)
        self._accepted = False

    def pos(self) -> Point:
        """Pointer position."""
        return self._pos

    def x(self) -> float:
        """Horizontal pointer position."""
        return self._pos.x()

    def y(self) -> float:
        """Vertical pointer position."""
        return self._pos.y()

    def button(self) -> int:
        """The button that changed state."""
        return self._button

    def buttons(self) -> int:
        """Mask of the buttons currently held."""
        return self._buttons

    def modifiers(self) -> int:
        """Mask of the modifiers held."""
        return self._modifiers

    def is_double(self) -> bool:
        """Whether this is the second press of a double click."""
        return self._double

    def accept(self) -> None:
        """Mark the event handled."""
        self._accepted = True

    def ignore(self) -> None:
        """Mark the event unhandled."""
        self._accepted = False

    def isAccepted(self) -> bool:  # noqa: N802 - the toolkit spelling
        """Whether the event was marked handled."""
        return self._accepted


class KeyEvent:
    """One key press, in the engine's own vocabulary.

    Parameters
    ----------
    key : int
        One of :mod:`cmtk.keys`' ``KEY_*`` values, or ``0`` for a key
        with no special meaning.
    text : str, optional
        The character the key produced, empty for one that produces none.
    modifiers : int, optional
        Mask of the ``*_MODIFIER`` constants.
    """

    __slots__ = ("_key", "_text", "_modifiers", "_accepted")

    def __init__(self, key: int, text: str = "", modifiers: int = NO_MODIFIER) -> None:
        self._key = int(key)
        self._text = str(text or "")
        self._modifiers = int(modifiers)
        self._accepted = False

    def key(self) -> int:
        """The key value."""
        return self._key

    def text(self) -> str:
        """The character the key produced."""
        return self._text

    def modifiers(self) -> int:
        """Mask of the modifiers held."""
        return self._modifiers

    def accept(self) -> None:
        """Mark the event handled."""
        self._accepted = True

    def ignore(self) -> None:
        """Mark the event unhandled."""
        self._accepted = False

    def isAccepted(self) -> bool:  # noqa: N802 - the toolkit spelling
        """Whether the event was marked handled."""
        return self._accepted
