"""A scrolling child measures the room left from its own height, not from its height plus the scroll.

``begin_child`` gave the child's layout a height of ``box + scroll_y``. An item that fills the room it
is given (a table with ``expand``, the plot of a panel) then grew by the scroll amount every frame: the
content height grew with it, so did the scroll range, and the wheel never reached the rows below the
item -- they stayed at the same place on screen while the rows above scrolled away (found in the FPS
JSON editor, whose position form below an expanding table was unreachable at 800x600).
"""

from __future__ import annotations

import emtk
from emtk.testing import RecordingPainter

BOX = (0.0, 0.0, 280.0, 200.0)
KEY = ("__child__", "c")


def _frame(storage, wheel=0.0):
    """One frame: a title row, an item filling the room but 40 px, then six 20 px rows; their tops."""
    with emtk.frame(RecordingPainter(), (0, 0, 300, 300), storage=storage) as ctx:
        ctx.io.mouse_pos = (40.0, 40.0)
        ctx.io.mouse_wheel = wheel
        ctx.begin_child(BOX, child_id="c")
        ctx.layout.advance(100.0, 20.0)
        w, h = ctx.layout.avail()
        filler = max(h - 40.0, 120.0)
        ctx.layout.advance(w, filler)
        rows = []
        for _ in range(6):
            rows.append(ctx.layout.cursor[1])
            ctx.layout.advance(60.0, 20.0)
        ctx.end_child()
    return {"filler": filler, "rows": rows, "scroll": storage[KEY]["scroll_y"],
            "content": storage[KEY]["content_height"]}


def test_wheel_reaches_the_rows_below_an_expanding_item_and_stops():
    storage: dict = {}
    first = _frame(storage)
    _frame(storage)
    bottom = BOX[1] + BOX[3]
    assert first["rows"][-1] > bottom, "the last row starts below the child (the case under test)"
    seen = [_frame(storage, wheel=-3.0) for _ in range(20)]
    last = _frame(storage)
    # the rows below the expanding item scroll up with the rest and come into view ...
    assert last["rows"][-1] + 20.0 <= bottom + 1.0, last
    # ... and the scroll ends: neither the content nor the range grows with every notch
    assert {s["content"] for s in seen[3:]} == {first["content"]}
    assert seen[-1]["scroll"] == seen[-5]["scroll"] == first["content"] - BOX[3]


def test_expanding_item_has_the_same_height_scrolled_or_not():
    storage: dict = {}
    still = _frame(storage)
    _frame(storage)
    scrolled = _frame(storage, wheel=-1.0)
    scrolled = _frame(storage)
    assert scrolled["scroll"] > 0.0
    assert scrolled["filler"] == still["filler"]
    assert scrolled["rows"][0] == still["rows"][0] - scrolled["scroll"]
