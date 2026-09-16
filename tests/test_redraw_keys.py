"""A cached drawing is thrown away when what it draws changes -- and only then.

The rule this module exists to replace is "whoever writes must bump a
revision", which is a rule that lives in every writer and fails silently in the
one that forgets: the picture is not missing, it is *old*. See the module
docstring for the session that lost a playback panel to it.
"""
from __future__ import annotations

import emtk
from emtk import redraw


class Transport:
    """A control that says what it draws."""

    def __init__(self) -> None:
        self.frame, self.total, self.playing = 1, 464, False

    def content_key(self):
        return (self.frame, self.total, self.playing)


class Silent:
    """A control that says nothing -- the honest worst case."""


class Broken:
    """A control whose summary raises."""

    def content_key(self):
        raise RuntimeError("no")


def test_a_control_that_says_what_it_draws_caches():
    panel = Transport()
    first = redraw.content_key(panel)
    assert not redraw.changed(first, redraw.content_key(panel)), "nothing moved"

    panel.frame = 2
    assert redraw.changed(first, redraw.content_key(panel)), "the frame moved"


def test_every_field_the_key_names_invalidates_it():
    """A key that omits a field it draws is the bug in a new costume."""
    panel = Transport()
    for field, value in (("frame", 7), ("total", 500), ("playing", True)):
        before = redraw.content_key(panel)
        setattr(panel, field, value)
        assert redraw.changed(before, redraw.content_key(panel)), field


def test_a_control_that_will_not_say_is_always_redrawn():
    """Slower, never stale. That is the safe direction and so it is the default."""
    key = redraw.content_key(Silent())
    assert redraw.is_always(key)
    assert redraw.changed(key, redraw.content_key(Silent()))
    assert redraw.changed(key, key), "a refusal must not compare equal to itself"


def test_a_refusal_survives_being_put_in_a_tuple():
    """The trap this is a class and not a shared sentinel for.

    Keys are tuples -- a window's is its frame plus what its body draws -- and
    tuple equality short-circuits on element *identity*: a shared sentinel
    inside two tuples is never asked whether it is equal, so it compares equal
    and the window is drawn from a cache it should have missed.
    """
    left = ("window", "mouse", redraw.content_key(Silent()))
    right = ("window", "mouse", redraw.content_key(Silent()))
    assert left != right
    one = redraw.content_key(Silent())
    assert ("window", one) != ("window", redraw.content_key(Silent()))


def test_a_broken_summary_redraws_rather_than_raising():
    """A control that cannot summarise itself must not take the window down."""
    assert redraw.is_always(redraw.content_key(Broken()))


def test_none_is_a_key_and_not_a_refusal():
    """`None` means "I draw nothing"; the refusal is ALWAYS, and they differ."""
    assert not redraw.changed(None, None)
    assert redraw.changed(None, redraw.always())


def test_it_is_reachable_from_the_package():
    """A host reaches for `emtk.redraw`; it must be there without an import dance."""
    assert emtk.redraw.content_key(Transport()) == (1, 464, False)


class TestBlockCache:
    """A frame of blocks, built only where its key moved."""

    def _frame(self, cache, spec):
        """Build *spec* (``{key: payload}``) and report what was made."""
        made = []
        out = cache.build(
            (key, (lambda k=key, v=payload: (made.append(k), v)[1]))
            for key, payload in spec
        )
        return out, made

    def test_a_block_whose_key_held_still_is_not_rebuilt(self):
        cache = redraw.BlockCache()
        spec = [(("under", 1), "u"), (("window", "mouse", 3), "m")]
        self._frame(cache, spec)
        out, made = self._frame(cache, spec)
        assert made == [], "nothing moved and something was rebuilt"
        assert out == ["u", "m"]
        assert cache.rebuilt == 0

    def test_only_the_block_that_moved_is_rebuilt(self):
        cache = redraw.BlockCache()
        self._frame(cache, [(("under", 1), "u"), (("window", "mouse", 3), "m")])
        out, made = self._frame(
            cache, [(("under", 1), "u"), (("window", "mouse", 4), "m2")]
        )
        assert made == [("window", "mouse", 4)]
        assert out == ["u", "m2"]

    def test_a_block_that_stops_being_drawn_is_forgotten(self):
        """Otherwise a closed window's vertices live for ever -- and come back."""
        cache = redraw.BlockCache()
        self._frame(cache, [(("under", 1), "u"), (("window", "dbg", 1), "d")])
        self._frame(cache, [(("under", 1), "u")])
        assert len(cache) == 1
        _out, made = self._frame(
            cache, [(("under", 1), "u"), (("window", "dbg", 1), "d")]
        )
        assert made == [("window", "dbg", 1)], "a reopened window drew a stale body"

    def test_a_refusal_in_the_key_rebuilds_every_frame(self):
        cache = redraw.BlockCache()
        spec = lambda: [(("window", "opaque", redraw.always()), "o")]
        self._frame(cache, spec())
        _out, made = self._frame(cache, spec())
        assert len(made) == 1

    def test_an_unhashable_key_costs_a_rebuild_and_not_a_crash(self):
        """A control returning a list from `content_key` must not kill the frame."""
        cache = redraw.BlockCache()
        spec = [(("window", "listy", ["a", "b"]), "l")]
        out, _made = self._frame(cache, spec)
        assert out == ["l"]
        out, made = self._frame(cache, spec)
        assert out == ["l"]
        assert made == [], "an equal unhashable key still found its payload"

    def test_order_is_the_order_the_blocks_were_given(self):
        """Paint order is draw order; a cache must not reshuffle it."""
        cache = redraw.BlockCache()
        spec = [(("under", 1), "u"), (("window", "a", 1), "a"), (("over", 1), "o")]
        out, _ = self._frame(cache, spec)
        assert out == ["u", "a", "o"]
        out, _ = self._frame(cache, spec)
        assert out == ["u", "a", "o"]

    def test_clear_forgets_everything(self):
        cache = redraw.BlockCache()
        self._frame(cache, [(("under", 1), "u")])
        cache.clear()
        _out, made = self._frame(cache, [(("under", 1), "u")])
        assert made == [("under", 1)]
