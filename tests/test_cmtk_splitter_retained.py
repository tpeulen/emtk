"""``widgets.splitter.Splitter``: the retained divider.

The immediate-mode splitter is tested in ``test_cmtk_splitter.py``; this is
the other shape, and what is worth testing about it is different. The
immediate one is a *drag*, so its tests drive frames. This one owns the
boundary, so its tests are mostly about :meth:`Splitter.split` -- three
rectangles that have to tile a region exactly, at any size, including the
sizes that cannot satisfy the constraints they were given.
"""

from __future__ import annotations

import pytest

from cmtk.flags import Axis
from cmtk.style import SEPARATOR, SEPARATOR_ACTIVE, SEPARATOR_HOVERED
from cmtk.testing import RecordingPainter
from cmtk.widgets.splitter import Splitter


# --------------------------------------------------------------------------- #
# split(): the three rectangles
# --------------------------------------------------------------------------- #
def test_the_three_boxes_tile_the_region_exactly():
    sp = Splitter(150.0, thickness=12.0)
    pane1, bar, pane2 = sp.split(10.0, 20.0, 400.0, 300.0)

    assert pane1 == (10.0, 20.0, 150.0, 300.0)
    assert bar == (160.0, 20.0, 12.0, 300.0)
    assert pane2 == (172.0, 20.0, 238.0, 300.0)
    # no gap, no overlap, nothing off the end
    assert pane1[2] + bar[2] + pane2[2] == 400.0
    assert bar[0] == pane1[0] + pane1[2]
    assert pane2[0] == bar[0] + bar[2]


def test_the_y_axis_stacks_instead_of_columns():
    sp = Splitter(100.0, axis=Axis.Y, thickness=8.0)
    top, bar, bottom = sp.split(0.0, 0.0, 400.0, 300.0)

    assert top == (0.0, 0.0, 400.0, 100.0)
    assert bar == (0.0, 100.0, 400.0, 8.0)
    assert bottom == (0.0, 108.0, 400.0, 192.0)
    assert top[3] + bar[3] + bottom[3] == 300.0
    assert all(box[2] == 400.0 for box in (top, bar, bottom))


def test_size2_is_derived_and_not_a_second_copy():
    """Two sizes and a total is one fact too many. `size2` follows the
    region, so a resize cannot leave it stale."""
    sp = Splitter(150.0, thickness=12.0)
    sp.split(0.0, 0.0, 400.0, 300.0)
    assert sp.size2 == 238.0
    sp.split(0.0, 0.0, 300.0, 300.0)
    assert sp.size2 == 138.0                   # not still 238


def test_a_shrinking_region_clamps_instead_of_inverting_a_pane():
    """The failure this guards: a pane with a negative width, which a painter
    either draws inside out or drops."""
    sp = Splitter(350.0, thickness=12.0)
    for total in (400.0, 300.0, 200.0, 100.0, 20.0, 5.0):
        pane1, bar, pane2 = sp.split(0.0, 0.0, total, 100.0)
        assert pane1[2] >= 0.0 and pane2[2] >= 0.0, f"inverted at {total}"
        assert pane1[2] + bar[2] + pane2[2] == pytest.approx(total) or total < bar[2]


def test_both_minimums_hold_while_there_is_room_for_both():
    sp = Splitter(150.0, thickness=12.0, min_size1=60.0, min_size2=80.0)
    sp.split(0.0, 0.0, 400.0, 300.0)
    assert (sp.size1, sp.size2) == (150.0, 238.0)

    sp.size1 = 10.0                            # below its own minimum
    sp.split(0.0, 0.0, 400.0, 300.0)
    assert sp.size1 == 60.0

    sp.size1 = 1000.0                          # past the other's
    sp.split(0.0, 0.0, 400.0, 300.0)
    assert (sp.size1, sp.size2) == (308.0, 80.0)


def test_when_the_region_cannot_hold_both_minimums_the_first_wins():
    """Arbitrary, but it has to be *stable*: a rule that picks whichever
    limit is nearer makes the boundary jump about as the window resizes."""
    sp = Splitter(150.0, thickness=12.0, min_size1=60.0, min_size2=80.0)
    pane1, bar, pane2 = sp.split(0.0, 0.0, 150.0, 300.0)
    assert (sp.size1, sp.size2) == (60.0, 78.0)
    assert pane1[2] + bar[2] + pane2[2] == 150.0

    # And it stays there rather than oscillating as the region shrinks.
    seen = [sp.split(0.0, 0.0, t, 300.0) and sp.size1
            for t in (150.0, 149.0, 148.0, 147.0)]
    assert seen == [60.0, 60.0, 60.0, 60.0]


# --------------------------------------------------------------------------- #
# the drag
# --------------------------------------------------------------------------- #
def test_dragging_moves_the_boundary_from_the_point_it_was_grabbed():
    sp = Splitter(150.0, thickness=12.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    assert sp.press(152.0, 50.0, *bar) is sp     # 2px into the bar
    assert sp.held is True
    assert sp.drag(152.0, 50.0, *bar) == (150.0, 238.0)   # not moved yet

    assert sp.drag(172.0, 50.0, *bar) == (170.0, 218.0)   # +20
    assert sp.size1 == 170.0


def test_a_press_that_misses_does_not_grab():
    sp = Splitter(150.0, thickness=12.0, hover_extend=0.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    assert sp.press(50.0, 50.0, *bar) is None
    assert sp.held is False
    assert sp.drag(200.0, 50.0, *bar) is None, "dragged without ever grabbing"
    assert sp.size1 == 150.0


def test_releasing_forgets_the_grab_point():
    sp = Splitter(150.0, thickness=12.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    sp.press(151.0, 50.0, *bar)                # 1px in
    sp.release()
    assert sp.held is False
    assert sp.drag(200.0, 50.0, *bar) is None

    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)
    sp.press(161.0, 50.0, *bar)                # 11px in, the other edge
    assert sp.drag(166.0, 50.0, *bar) == (155.0, 233.0)   # +5, not +15


def test_the_drag_respects_the_minimums():
    sp = Splitter(150.0, thickness=12.0, min_size1=60.0, min_size2=80.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    sp.press(156.0, 50.0, *bar)
    assert sp.drag(-900.0, 50.0, *bar) == (60.0, 328.0)
    assert sp.drag(9000.0, 50.0, *bar) == (308.0, 80.0)


def test_hover_extend_widens_the_grab_target():
    """A 4px bar is thinner than anyone can hit."""
    thin = Splitter(150.0, thickness=4.0, hover_extend=8.0)
    _p1, bar, _p2 = thin.split(0.0, 0.0, 400.0, 300.0)
    assert thin.press(145.0, 50.0, *bar) is thin      # 5px left of the bar

    strict = Splitter(150.0, thickness=4.0, hover_extend=0.0)
    _p1, bar, _p2 = strict.split(0.0, 0.0, 400.0, 300.0)
    assert strict.press(145.0, 50.0, *bar) is None


def test_a_held_splitter_stays_hovered_wherever_the_pointer_goes():
    """The bar is thin and the pointer outruns the layout that follows it, so
    leaving the bar mid-drag is the normal case, not the exception."""
    sp = Splitter(150.0, thickness=12.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    sp.press(156.0, 50.0, *bar)
    assert sp.hover(-500.0, -500.0) is True
    sp.release()
    assert sp.hover(-500.0, -500.0) is False


# --------------------------------------------------------------------------- #
# drawing
# --------------------------------------------------------------------------- #
def test_the_bar_is_inset_inside_its_grab_box_and_never_vanishes():
    sp = Splitter(150.0, thickness=12.0, bar_margin=4.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)
    p = RecordingPainter()
    sp.draw(p, *bar)
    x, y, w, h, _colour = p.fills[0]
    assert (x, y, w, h) == (154.0, 0.0, 4.0, 300.0)     # 12 - 2*4, centred

    thin = Splitter(150.0, thickness=4.0, bar_margin=4.0)
    _p1, bar, _p2 = thin.split(0.0, 0.0, 400.0, 300.0)
    p = RecordingPainter()
    thin.draw(p, *bar)
    assert p.fills[0][2] == 2.0, "a margin wider than the bar must not erase it"


def test_the_bar_shows_all_three_states():
    sp = Splitter(150.0, thickness=12.0)
    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)

    def colour():
        p = RecordingPainter()
        sp.draw(p, *bar)
        return p.fills[0][4]

    assert colour() == SEPARATOR
    sp.hover(156.0, 50.0)
    assert colour() == SEPARATOR_HOVERED
    sp.press(156.0, 50.0, *bar)
    assert colour() == SEPARATOR_ACTIVE


def test_it_honours_the_control_contract():
    """`Control` gives every port `remember`/`contains`; a control that does
    not call `remember` in `draw` hit-tests against stale geometry, which is
    the failure that looks like "clicks land one row off"."""
    from cmtk.control import Control

    sp = Splitter(150.0, thickness=12.0)
    assert isinstance(sp, Control)
    assert sp.box is None

    _p1, bar, _p2 = sp.split(0.0, 0.0, 400.0, 300.0)
    sp.draw(RecordingPainter(), *bar)
    assert sp.box == bar
    assert sp.contains(161.0, 50.0) is True
    assert sp.contains(50.0, 50.0) is False
