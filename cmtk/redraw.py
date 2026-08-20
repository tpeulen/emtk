"""What a control draws, as a value -- so a cache cannot outlive its contents.

A host that keeps last frame's vertices has to decide when to throw them away.
There are two ways to decide, and only one of them works.

**A revision counter** is the tempting one: the control keeps a number, whoever
changes the control bumps it, and the cache compares numbers. It is cheap and
it is wrong in a way that never shows up in review -- because the rule it needs
("everything that writes must bump") lives in every writer, and a writer that
forgets produces no error, no warning and no missing pixel. It produces a
*correct picture of an older moment*, which reads as "the buttons do not work".

A playback panel lost a whole session to exactly that: the frame counter, the
transport slider, the stride and the input mode were written from outside once
a frame, nothing bumped the panel's revision, and the panel read ``1 / 464``
while the animation ran to the end. Pressing a button *did* change the frame;
nothing on screen ever said so.

**A content key** is the other way: the control says what it is about to draw,
as a small comparable value, and the cache compares that. There is nothing to
remember, because the key is computed from the same state the drawing reads --
if the picture would differ, the key differs, by construction. A control that
cannot summarise itself says so with an :class:`Always`, and is redrawn
every frame: slower, never stale, and the honest default.

Use it from a host like this::

    key = cmtk.redraw.content_key(panel)
    if cmtk.redraw.changed(cached_key, key):
        vertices = draw(panel)

and from a control by saying what it draws::

    class Transport:
        def content_key(self):
            return (self.frame, self.total, self.playing, self.stride)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Always", "always", "is_always", "Drawable", "content_key", "changed",
    "BlockCache",
]


class Always:
    """The key of a control that will not say what it draws.

    Every instance is a fresh one and no two are equal, so a cache keyed on it
    always misses -- which is the safe direction.

    A *class* whose instances are unequal rather than one shared sentinel,
    because a key is very often a tuple and **tuple equality short-circuits on
    element identity**: ``(1, S) == (1, S)`` is true for a shared ``S`` no
    matter what ``S.__eq__`` says, since the elements are the same object and
    the comparison never asks. A shared "never equal" sentinel is therefore
    exactly equal to itself in the one place it is most used, which is a bug
    that reads as a stale window and nothing else. A fresh instance per call
    has no identity to short-circuit on.

    It is not ``None``: ``None`` is a perfectly good key for "I draw nothing at
    the moment", and the two answers are opposites -- one means *never* redraw,
    the other *always*.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "cmtk.redraw.always()"

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return id(self)


def always() -> Always:
    """A key that is equal to nothing, not even the next one."""
    return Always()


def is_always(key: Any) -> bool:
    """Whether *key* is a refusal to say (and so a guaranteed redraw)."""
    return isinstance(key, Always)


@runtime_checkable
class Drawable(Protocol):
    """A control that can say what it is about to draw."""

    def content_key(self) -> Any:
        """A small comparable value that differs whenever the picture would.

        Cheap: it is computed every frame, before the drawing that it might
        save. A tuple of the numbers and flags the drawing reads is the usual
        answer; an array is not, unless something already summarises it.
        """


def content_key(control: Any) -> Any:
    """What *control* draws, or an :class:`Always` when it will not say.

    Parameters
    ----------
    control : object
        Anything a host might cache the drawing of.

    Returns
    -------
    object
        The control's own ``content_key()`` when it has one; otherwise an
        :class:`Always`, which never compares equal and so never caches.

    Notes
    -----
    A control whose ``content_key`` raises is treated as unable to say. A
    broken summary must not take the window down, and drawing it again is
    always safe.
    """
    method = getattr(control, "content_key", None)
    if not callable(method):
        return always()
    try:
        return method()
    except Exception:  # noqa: BLE001 - an unsummarisable control is redrawn
        return always()


def changed(previous: Any, current: Any) -> bool:
    """Whether the picture may differ between two keys.

    ``True`` whenever either side is an :class:`Always`, when they are unequal,
    or when comparing them raises -- every uncertain answer is "redraw", because
    the cost of an unnecessary redraw is a frame and the cost of a missed one is
    a picture that lies.
    """
    if is_always(previous) or is_always(current):
        return True
    try:
        return bool(previous != current)
    except Exception:  # noqa: BLE001 - an exotic comparison is not a promise
        return True


class BlockCache:
    """Last frame's drawing per block, kept only while its key holds still.

    A host that splits its chrome into blocks -- furniture, one per window --
    and keeps each block's vertices needs three things that are easy to get
    subtly wrong by hand, and were: rebuild a block whose key moved, *keep* the
    ones whose key did not, and forget the blocks that are no longer drawn at
    all. The third is the one that leaks: a dict that is only ever written to
    grows a stale entry per closed window for the life of the process, and the
    entry comes back to life if the key ever repeats.

    So a frame is one call::

        pieces = cache.build((key, painter_for(block)) for block in blocks)

    where each ``make`` takes no arguments and returns whatever the host wants
    to keep -- an array of vertices, a display list, an image. Blocks are
    returned in the order given, and :attr:`rebuilt` says how many were made
    rather than reused, which is the number worth logging when a frame is slow.

    A key that cannot go in a dict (a list, an array -- easy to produce by
    accident from a control's ``content_key``) is not an error: that block is
    simply rebuilt every frame, which is the same answer this module gives
    everywhere else for "I cannot tell whether it changed".
    """

    __slots__ = ("_entries", "_unhashable", "rebuilt")

    def __init__(self) -> None:
        self._entries: dict = {}
        #: Payloads whose key would not hash, as ``(key, payload)`` pairs. A
        #: list, compared by ``==``: a handful of blocks at most, and a linear
        #: scan of five keys is nothing beside re-emitting one of them.
        self._unhashable: list = []
        #: How many blocks the last :meth:`build` had to make.
        self.rebuilt: int = 0

    def build(self, blocks: Any) -> list:
        """The payload of every block, building only what changed.

        Parameters
        ----------
        blocks : iterable of (key, make)
            *key* is what the block draws (see :func:`content_key`); *make* is
            ``() -> payload``, called only on a miss.

        Returns
        -------
        list
            One payload per block, in the order the blocks were given.
        """
        entries: dict = {}
        unhashable: list = []
        out = []
        self.rebuilt = 0
        for key, make in blocks:
            payload, found = self._lookup(key)
            if not found:
                payload = make()
                self.rebuilt += 1
            out.append(payload)
            try:
                entries[key] = payload
            except TypeError:
                unhashable.append((key, payload))
        # Assigned rather than updated: a block that was not asked for this
        # frame is gone, and gone is what "the window was closed" means.
        self._entries = entries
        self._unhashable = unhashable
        return out

    def _lookup(self, key: Any) -> tuple:
        """``(payload, found)`` for *key*, without ever raising on the key."""
        try:
            if key in self._entries:
                return self._entries[key], True
            return None, False
        except TypeError:
            pass
        for known, payload in self._unhashable:
            try:
                if not changed(known, key):
                    return payload, True
            except Exception:  # noqa: BLE001 - an exotic key is a miss
                continue
        return None, False

    def clear(self) -> None:
        """Forget everything -- the display changed under the whole cache."""
        self._entries = {}
        self._unhashable = []
        self.rebuilt = 0

    def __len__(self) -> int:
        return len(self._entries) + len(self._unhashable)
