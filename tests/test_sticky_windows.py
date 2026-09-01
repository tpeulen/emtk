"""Windows that stay where they were put.

cmtk has no window manager and no ``.ini``, so nothing outside the context
remembers where a window was. Two things follow from that, and this file
pins both:

* a window opened with **no box** takes the frame's, every frame. That is
  deliberate and it is the default -- one window filling its host, still
  following it when the host is resized. Reverting it puts back a real bug:
  a stored box latches the first frame's size and a widened window goes
  blank past the old edge.
* an application with **floating sub-windows** wants the opposite. Under the
  default every one of them is the whole frame, so they draw on top of each
  other and of the main window; what is on screen is whichever was submitted
  last, and the rest read as "did not open".

So the placement is a mode, set once, and the frame-following case is what
it defaults to. Beside it, ``SetNextWindowPos``/``Size`` place one window --
which they had been accepting and silently discarding.
"""
from __future__ import annotations

import pytest

import cmtk.im as im
from cmtk.flags import Cond
from cmtk.testing import PixelPainter

FRAME = (0.0, 0.0, 400.0, 300.0)


@pytest.fixture()
def painter():
    return PixelPainter(int(FRAME[2]), int(FRAME[3]))


def run(painter, gui, frames: int = 2, storage=None, box=FRAME):
    """Draw *gui* for *frames* frames against one storage, and return it."""
    storage = {} if storage is None else storage
    io = im.IO()
    for _ in range(max(1, frames)):
        with im.frame(painter, box, io=io, storage=storage):
            gui()
    return storage


def windows(storage) -> dict:
    return {w.name: w for w in storage["__windows__"]}


# --------------------------------------------------------------------------- #
# The default, which must not move
# --------------------------------------------------------------------------- #
def test_a_box_less_window_still_follows_the_frame(painter):
    """The behaviour this feature had to be added *beside*, not instead of.

    A window with no box latching its first frame's size is a real bug that
    was fixed once: the content stops at the old edge and the rest of a
    widened window is blank.
    """
    storage = {}
    io = im.IO()
    for box in (FRAME, (0.0, 0.0, 600.0, 500.0)):
        with im.frame(painter, box, io=io, storage=storage):
            im.begin("main")
            im.text("hello")
            im.end()

    window = windows(storage)["main"]
    assert window.follows_frame is True
    assert window.sticky is False
    assert window.box == (0.0, 0.0, 600.0, 500.0), "it stopped following"


def test_an_explicit_box_is_not_sticky(painter):
    """The caller hands it a box every frame, so the caller owns the
    placement. Sticky means *cmtk* is remembering one, and claiming it here
    would make a future ``.ini`` write back a box its owner never asked to
    have saved."""
    storage = run(painter, lambda: (im.begin("panel", (5, 6, 100, 40)),
                                    im.end()))
    window = windows(storage)["panel"]
    assert window.follows_frame is False
    assert window.sticky is False
    assert window.box == (5, 6, 100, 40)


def test_an_unknown_placement_is_refused(painter):
    """A misspelt mode that silently meant "frame" would look exactly like
    the bug the setting exists to fix."""
    with im.frame(painter, FRAME) as ctx:
        with pytest.raises(ValueError, match="cascade"):
            ctx.set_window_placement("floating")


# --------------------------------------------------------------------------- #
# Cascade
# --------------------------------------------------------------------------- #
def _three_windows():
    for name in ("alpha", "beta", "gamma"):
        im.begin(name)
        im.text(name)
        im.end()


def test_cascaded_windows_do_not_sit_on_top_of_each_other(painter):
    def gui():
        im.set_window_placement(im.PLACE_CASCADE)
        _three_windows()

    storage = run(painter, gui)
    boxes = [windows(storage)[n].box for n in ("alpha", "beta", "gamma")]
    assert len({box[:2] for box in boxes}) == 3, boxes
    for first, second in zip(boxes, boxes[1:]):
        assert second[0] - first[0] == im.CASCADE_STEP
        assert second[1] - first[1] == im.CASCADE_STEP
    for box in boxes:
        # CASCADE_SIZE is a ceiling; the frame is the other bound, so on a
        # small frame the windows are smaller and several still fit.
        assert box[2] <= im.CASCADE_SIZE[0] and box[3] <= im.CASCADE_SIZE[1]
        assert box[0] + box[2] <= FRAME[2] and box[1] + box[3] <= FRAME[3], \
            f"{box} hangs off the frame"


def test_a_cascaded_window_keeps_its_box_when_the_frame_resizes(painter):
    """The whole point of sticky: it was placed once and it stays placed.
    A frame-following window would jump to the new size instead."""
    storage = {}
    io = im.IO()
    for box in (FRAME, (0.0, 0.0, 600.0, 500.0)):
        with im.frame(painter, box, io=io, storage=storage) as ctx:
            ctx.set_window_placement(im.PLACE_CASCADE)
            im.begin("floater")
            im.text("x")
            im.end()

    window = windows(storage)["floater"]
    assert window.sticky is True
    assert window.follows_frame is False
    assert window.box[:2] == (im.CASCADE_STEP, im.CASCADE_STEP)
    assert window.box[2:] == (FRAME[2] * im.CASCADE_FRACTION,
                              FRAME[3] * im.CASCADE_FRACTION)


def test_the_cascade_wraps_rather_than_marching_off_the_frame(painter):
    """Past the point where a whole window would no longer fit, it starts
    again at the margin -- which is what every window manager does, and for
    the same reason: a window placed outside the frame is a window the user
    cannot reach."""
    small = (0.0, 0.0, 420.0, 320.0)
    little = PixelPainter(int(small[2]), int(small[3]))

    def gui():
        im.set_window_placement(im.PLACE_CASCADE)
        for index in range(8):
            im.begin(f"w{index}")
            im.end()

    storage = run(little, gui, box=small)
    for window in storage["__windows__"]:
        x, y, w, h = window.box
        assert x + w <= small[2] + 0.001 and y + h <= small[3] + 0.001, window.box
    # and it did wrap, rather than every window landing in one place
    assert len({w.box[:2] for w in storage["__windows__"]}) > 1


def test_the_cascade_counts_placements_and_not_frames(painter):
    """A window created on frame 100 is offset from the one created on
    frame 1. Counting per frame would put every window opened later back at
    the margin, on top of the first."""
    storage = {}
    io = im.IO()
    opened = ["first"]
    for index in range(6):
        if index == 3:
            opened.append("second")
        with im.frame(painter, FRAME, io=io, storage=storage) as ctx:
            ctx.set_window_placement(im.PLACE_CASCADE)
            for name in opened:
                im.begin(name)
                im.end()

    got = windows(storage)
    assert got["second"].box[:2] != got["first"].box[:2]


# --------------------------------------------------------------------------- #
# SetNextWindowPos / SetNextWindowSize, which used to be discarded
# --------------------------------------------------------------------------- #
def test_set_next_window_pos_actually_places_the_window(painter):
    """It was accepted and dropped. A port that says ``SetNextWindowPos`` --
    the way ImGui code places a floating window -- got the whole frame."""
    def gui():
        im.set_next_window_pos((40, 50))
        im.set_next_window_size((120, 90))
        im.begin("placed")
        im.end()

    window = windows(run(painter, gui))["placed"]
    assert window.box == (40.0, 50.0, 120.0, 90.0)
    assert window.follows_frame is False


def test_always_re_places_every_frame_and_once_does_not(painter):
    """The difference between an animated window and a window the user is
    allowed to keep."""
    moving = iter([(10, 10), (99, 99), (99, 99)])

    def always():
        im.set_next_window_pos(next(moving), Cond.ALWAYS)
        im.begin("a")
        im.end()

    assert windows(run(painter, always, frames=2))["a"].box[:2] == (99.0, 99.0)

    settled = iter([(10, 10), (99, 99), (99, 99)])

    def once():
        im.set_next_window_pos(next(settled), Cond.ONCE)
        im.begin("b")
        im.end()

    window = windows(run(painter, once, frames=2))["b"]
    assert window.box[:2] == (10.0, 10.0)
    assert window.sticky is True, "a one-time placement is the sticky case"


def test_first_use_ever_is_once_here_because_there_is_no_ini(painter):
    """``FirstUseEver`` means "unless a saved layout says otherwise", and
    cmtk saves nothing -- so it can only mean ``Once``. Saying that out loud
    is better than a port silently getting ``Always``."""
    positions = iter([(11, 12), (77, 78), (77, 78)])

    def gui():
        im.set_next_window_pos(next(positions), Cond.FIRST_USE_EVER)
        im.begin("c")
        im.end()

    assert windows(run(painter, gui, frames=2))["c"].box[:2] == (11.0, 12.0)


def test_appearing_places_a_window_that_was_gone_last_frame(painter):
    """A window closed and reopened comes back where it was told to, not
    where the user last dragged something else."""
    storage = {}
    io = im.IO()
    positions = iter([(10, 10), (10, 10), (60, 60), (60, 60)])
    show = [True, True, False, True]

    for visible in show:
        with im.frame(painter, FRAME, io=io, storage=storage):
            if visible:
                im.set_next_window_pos(next(positions), Cond.APPEARING)
                im.begin("d")
                im.end()

    assert windows(storage)["d"].box[:2] == (60.0, 60.0)


def test_a_window_re_placed_every_frame_is_not_sticky(painter):
    """A main window pinned to the viewport says ``SetNextWindowPos`` with
    no condition, every frame. It is not remembering anything -- its owner
    restates it -- and recording it as sticky would have a future ``.ini``
    save a box nobody asked to keep."""
    def gui():
        im.set_window_placement(im.PLACE_CASCADE)
        im.set_next_window_pos((0, 0))
        im.set_next_window_size((400, 300))
        im.begin("MainWindow")
        im.end()
        im.begin("floater")            # no placement of its own: cascaded
        im.end()

    got = windows(run(painter, gui))
    assert got["MainWindow"].box == (0.0, 0.0, 400.0, 300.0)
    assert got["MainWindow"].sticky is False
    assert got["floater"].sticky is True
    # and the pinned window took no step of the cascade, so the first
    # floating window still starts at the margin
    assert got["floater"].box[:2] == (im.CASCADE_STEP, im.CASCADE_STEP)


def test_a_size_alone_keeps_the_position(painter):
    def gui():
        im.set_next_window_pos((20, 30), Cond.ONCE)
        im.set_next_window_size((150, 60), Cond.ALWAYS)
        im.begin("e")
        im.end()

    assert windows(run(painter, gui))["e"].box == (20.0, 30.0, 150.0, 60.0)


def test_a_placed_window_is_drawn_where_it_was_placed(painter):
    """The box is not the point; the pixels are. A window whose ``box``
    moved while its layout did not is the version of this bug that a
    field check walks straight past."""
    def gui():
        im.set_next_window_pos((200, 40), Cond.ONCE)
        im.set_next_window_size((150, 80), Cond.ONCE)
        im.begin("right")
        im.button("OK")
        im.end()

    shown = PixelPainter(int(FRAME[2]), int(FRAME[3]),
                         background=(30, 32, 38, 255))
    run(shown, gui)
    row = int(FRAME[2])
    lit = [
        (i // 4) % row
        for i in range(0, len(shown.px), 4)
        if shown.px[i] > 70
    ]
    assert lit, "nothing was drawn at all"
    assert min(lit) >= 200, f"the window drew from x={min(lit)}, not from 200"
