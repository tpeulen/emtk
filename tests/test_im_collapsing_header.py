"""``im.collapsing_header``: an ImGui flags word sets the *initial* state only.

Callers across the ports pass ``im.TreeNodeFlags.DEFAULT_OPEN`` or ``0`` as ImGui does.
Read as a bool, that forced the header open (or closed) on every frame, so a click
toggled it for one frame and the next frame put it back: the header could not be used.
"""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter


def _frames(flag, clicks, n=8):
    """Draw *n* frames of one header; click its bar on the frames in *clicks* (press on the
    frame, release on the next: a press fires on release). Return the ``open`` of every frame."""
    io, storage, seen = emtk.IO(), {}, []
    box = {}

    def gui():
        seen.append(im.collapsing_header("Fit", flag))
        box["r"] = im.get_item_rect()

    for frame in range(n):
        io.mouse_clicked[0] = io.mouse_released[0] = False
        io.mouse_down[0] = False
        if frame in clicks or frame - 1 in clicks:
            r = box["r"]
            io.mouse_pos = (r[0] + 10, r[1] + 3)
            if frame in clicks:
                io.mouse_clicked[0] = io.mouse_down[0] = True
            else:
                io.mouse_released[0] = True
        with emtk.frame(RecordingPainter(), (0, 0, 300, 200), io=io, storage=storage):
            gui()
    return seen


def test_default_open_starts_open_and_stays_where_the_user_leaves_it():
    seen = _frames(im.TreeNodeFlags.DEFAULT_OPEN, clicks={2})
    assert seen[0] is True and seen[1] is True
    assert seen[-1] is False, "a click must close a DEFAULT_OPEN header for good"


def test_flags_zero_starts_closed_and_a_click_opens_it_for_good():
    seen = _frames(0, clicks={2})
    assert seen[0] is False
    assert seen[-1] is True, "a click must open a header given flags=0 for good"


def test_a_bool_still_forces_the_state_each_frame():
    assert set(_frames(True, clicks={2})[-2:]) == {True}
    assert set(_frames(False, clicks={2})[-2:]) == {False}


def test_the_legacy_literal_one_means_open():
    assert _frames(1, clicks=set())[0] is True
