"""``im.splitter`` / ``im.splitter_behavior``: the draggable divider.

A splitter is the one control whose whole behaviour is a drag, so almost
nothing about it can be checked by looking at a single frame. Every test here
drives a *sequence* of frames through one ``IO`` and one storage dict -- press,
move, move, release -- because that is the only way the interesting parts are
reachable at all: the grab offset survives between frames, the minimums have to
hold while the pointer keeps going, and "changed" has to stop being true when
the boundary stops moving even though the button is still down.

The numbers are worked out from the geometry in each test rather than read off
the implementation, which is the point.
"""

from __future__ import annotations

import cmtk
import cmtk.im as im
from cmtk.testing import RecordingPainter

SIZE = (0.0, 0.0, 400.0, 300.0)


class Driver:
    """One session: the same IO and storage across frames, as a host has."""

    def __init__(self) -> None:
        self.io = cmtk.IO()
        # A clock the test owns. Wall time would make `hover_visibility_delay`
        # depend on how fast the machine runs the test.
        self.io.wall_clock = False
        self.io.delta_time = 1.0 / 60.0
        self.storage: dict = {}
        self.painter = RecordingPainter()

    def frame(self, gui):
        self.painter = RecordingPainter()
        with cmtk.frame(self.painter, SIZE, io=self.io, storage=self.storage):
            out = gui()
        self.io.end_event()
        return out

    # -- pointer ---------------------------------------------------------- #
    def move(self, x, y) -> None:
        self.io.mouse_pos = (float(x), float(y))

    def press(self, x, y) -> None:
        self.move(x, y)
        self.io.mouse_clicked[0] = True
        self.io.mouse_clicked_pos[0] = (float(x), float(y))
        self.io.mouse_down[0] = True

    def release(self) -> None:
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True


# --------------------------------------------------------------------------- #
# splitter_behavior: the interaction, with no bar drawn
# --------------------------------------------------------------------------- #
def _behave(d, box, size1, size2, **kw):
    """One frame of `splitter_behavior` over a fixed box."""
    return d.frame(lambda: im.splitter_behavior(
        box, im.get_id("##s"), im.Axis.X, size1, size2, **kw))


def _pane_frame(d, sizes, origin=0.0, thickness=8.0, **kw):
    """One frame the way a real caller runs it.

    The bar's position is *derived* from the sizes, because that is what a
    two-pane layout does: pane one occupies ``[origin, origin + size1)`` and
    the bar sits immediately after it. So the box moves as the sizes change,
    which is exactly the feedback the delta arithmetic is written against.
    """
    box = (origin + sizes[0], 0.0, thickness, 300.0)
    changed, a, b = d.frame(lambda: im.splitter_behavior(
        box, im.get_id("##s"), im.Axis.X, sizes[0], sizes[1], **kw))
    sizes[0], sizes[1] = a, b
    return changed


def test_dragging_moves_space_from_one_pane_to_the_other():
    """The total is conserved: what one pane gains the other loses."""
    d = Driver()
    sizes = [100.0, 200.0]

    d.press(104.0, 50.0)                       # grab the middle of the bar
    assert _pane_frame(d, sizes) is False      # pressed, not yet moved
    assert sizes == [100.0, 200.0]

    d.move(124.0, 50.0)                        # 20 to the right
    assert _pane_frame(d, sizes) is True
    assert sizes == [120.0, 180.0]
    assert sum(sizes) == 300.0

    # Held still at the new place: the bar has caught up with the pointer, so
    # there is no residual left to apply and nothing more changes.
    assert _pane_frame(d, sizes) is False
    assert sizes == [120.0, 180.0]

    d.move(144.0, 50.0)                        # another 20
    assert _pane_frame(d, sizes) is True
    assert sizes == [140.0, 160.0]


def test_the_grab_point_is_kept_so_the_bar_does_not_jump():
    """Pressing near the bar's edge must not snap the boundary to the centre."""
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.press(101.0, 50.0)                       # 1px in from the left edge
    _behave(d, box, 100.0, 200.0)

    d.move(101.0, 50.0)                        # held, but not moved at all
    changed, a, b = _behave(d, box, 100.0, 200.0)
    assert (changed, a, b) == (False, 100.0, 200.0)

    d.move(106.0, 50.0)                        # +5 from where it was grabbed
    _changed, a, b = _behave(d, box, 100.0, 200.0)
    assert (a, b) == (105.0, 195.0)


def test_both_minimums_hold_while_the_pointer_keeps_going():
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.press(104.0, 50.0)
    _behave(d, box, 100.0, 200.0, min_size1=60.0, min_size2=80.0)

    d.move(-500.0, 50.0)                       # far past the left limit
    _changed, a, b = _behave(d, box, 100.0, 200.0,
                             min_size1=60.0, min_size2=80.0)
    assert (a, b) == (60.0, 240.0)

    d.move(5000.0, 50.0)                       # and far past the right one
    _changed, a, b = _behave(d, box, 100.0, 200.0,
                             min_size1=60.0, min_size2=80.0)
    assert (a, b) == (220.0, 80.0)             # size2 == its minimum


def test_changed_is_false_once_the_boundary_stops_moving():
    """A caller saves its layout on `changed`; pinned against a minimum with
    the button still down is not a change, and reporting one there wrote a
    settings file every frame."""
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.press(104.0, 50.0)
    _behave(d, box, 100.0, 200.0, min_size1=60.0)

    d.move(-500.0, 50.0)
    changed, a, _b = _behave(d, box, 100.0, 200.0, min_size1=60.0)
    assert changed is True and a == 60.0

    # Now the caller has re-laid-out at the minimum and the pointer is still
    # off to the left: the boundary cannot move, so nothing changed.
    d.move(-500.0, 50.0)
    changed, a, _b = _behave(d, (60.0, 0.0, 8.0, 300.0), 60.0, 240.0,
                             min_size1=60.0)
    assert changed is False
    assert a == 60.0


def test_releasing_forgets_the_grab_so_the_next_press_starts_clean():
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.press(101.0, 50.0)
    _behave(d, box, 100.0, 200.0)
    d.release()
    _behave(d, box, 100.0, 200.0)

    # A second press at the *other* edge must be measured from there.
    d.press(107.0, 50.0)
    _behave(d, box, 100.0, 200.0)
    d.move(112.0, 50.0)
    _changed, a, _b = _behave(d, box, 100.0, 200.0)
    assert a == 105.0                          # +5, not +11


def test_the_y_axis_reads_the_other_coordinate():
    """`Axis.Y` is a horizontal bar between stacked panes: the sizes run down."""
    d = Driver()
    box = (0.0, 100.0, 400.0, 8.0)

    d.press(50.0, 104.0)
    d.frame(lambda: im.splitter_behavior(box, im.get_id("##h"), im.Axis.Y,
                                         100.0, 200.0))
    d.move(50.0, 84.0)                         # 20 up
    _changed, a, b = d.frame(lambda: im.splitter_behavior(
        box, im.get_id("##h"), im.Axis.Y, 100.0, 200.0))
    assert (a, b) == (80.0, 220.0)


def test_hover_extend_widens_the_hit_box_along_the_axis_only():
    """A 4px bar is hard to hit. The extension must not also make it catch
    presses off the ends, which would steal them from the panes."""
    d = Driver()
    box = (100.0, 100.0, 4.0, 100.0)           # y runs 100..200

    d.press(94.0, 150.0)                       # 6px left of the bar
    changed, a, _b = _behave(d, box, 100.0, 200.0, hover_extend=8.0)
    d.move(104.0, 150.0)
    _changed, a, _b = _behave(d, box, 100.0, 200.0, hover_extend=8.0)
    assert a == 110.0                          # grabbed: 94 -> 104 is +10

    d2 = Driver()
    d2.press(102.0, 250.0)                     # on the bar's line, past its end
    _changed, a, _b = d2.frame(lambda: im.splitter_behavior(
        box, im.get_id("##s"), im.Axis.X, 100.0, 200.0, hover_extend=8.0))
    d2.move(122.0, 250.0)
    _changed, a, _b = d2.frame(lambda: im.splitter_behavior(
        box, im.get_id("##s"), im.Axis.X, 100.0, 200.0, hover_extend=8.0))
    assert a == 100.0                          # never grabbed


def test_the_reference_two_corner_rect_is_accepted_as_well():
    """`ImGui::SplitterBehavior` takes an `ImRect`, so a port arrives holding
    two corners rather than a position and a size. Both must mean the same
    rectangle, or every ported call site has to convert by hand."""

    class ImRect:                              # what autoport's prelude emits
        def __init__(self, a, b):
            self.min, self.max = a, b

    d = Driver()
    d.press(104.0, 50.0)
    d.frame(lambda: im.splitter_behavior(
        ImRect((100.0, 0.0), (108.0, 300.0)), im.get_id("##s"), im.Axis.X,
        100.0, 200.0))
    d.move(124.0, 50.0)
    _changed, a, b = d.frame(lambda: im.splitter_behavior(
        ImRect((100.0, 0.0), (108.0, 300.0)), im.get_id("##s"), im.Axis.X,
        100.0, 200.0))
    assert (a, b) == (120.0, 180.0)


def test_the_cursor_becomes_a_resize_arrow_over_the_bar():
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.move(104.0, 50.0)
    shape = d.frame(lambda: (im.splitter_behavior(box, im.get_id("##s"),
                                                  im.Axis.X, 100.0, 200.0),
                             im.get_mouse_cursor())[1])
    assert shape == im.MouseCursor.RESIZE_EW

    shape = d.frame(lambda: (im.splitter_behavior(box, im.get_id("##h"),
                                                  im.Axis.Y, 100.0, 200.0),
                             im.get_mouse_cursor())[1])
    assert shape == im.MouseCursor.RESIZE_NS


def test_the_delay_does_not_change_what_is_item_hovered_reports():
    """The delay is about *appearance*. `is_item_hovered` stays the raw hit,
    so a caller asking "is the pointer on my splitter" -- to show a tooltip,
    to suppress a drag elsewhere -- gets the truth rather than a value that
    is false for the first fifth of a second."""
    d = Driver()
    box = (100.0, 0.0, 8.0, 300.0)

    d.move(104.0, 50.0)
    hovered = d.frame(lambda: (im.splitter_behavior(
        box, im.get_id("##s"), im.Axis.X, 100.0, 200.0,
        hover_visibility_delay=0.2), im.is_item_hovered())[1])
    assert hovered is True


# --------------------------------------------------------------------------- #
# splitter: the whole control
# --------------------------------------------------------------------------- #
def test_the_splitter_reserves_its_thickness_so_the_next_pane_clears_it():
    """The bug this guards: with no space reserved, the pane after the
    splitter starts underneath it and swallows every press meant for it.

    Checked the way it is used -- with ``same_line(0, 0)`` either side, which
    is what puts two panes and a bar on one row -- rather than by reading the
    cursor directly, because a bare ``get_cursor_screen_pos`` after an item
    also carries the row's item spacing and would be asserting that instead.
    """
    d = Driver()
    seen: dict = {}

    def gui():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((10.0, 20.0))
        seen["before"] = im.get_cursor_screen_pos()
        im.splitter("##v", im.Axis.X, 12.0, 200.0, 100.0, 200.0)
        im.same_line(0.0, 0.0)
        seen["after"] = im.get_cursor_screen_pos()
        im.end()

    d.frame(gui)
    assert seen["after"][0] == seen["before"][0] + 12.0     # exactly the bar
    assert seen["after"][1] == seen["before"][1]            # same row


def test_the_bar_is_inset_inside_its_hit_box():
    """A comfortable grab target that is drawn as a slab looks like a divider
    nobody chose. The drawn bar is `thickness - 2 * margin`, floored at 2."""
    d = Driver()
    drawn: dict = {}

    def gui():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((100.0, 20.0))
        im.splitter("##v", im.Axis.X, 12.0, 200.0, 100.0, 200.0,
                    bar_margin=4.0)
        im.end()

    d.frame(gui)
    bars = [f for f in d.painter.fills if f[2] == 4.0 and f[3] == 200.0]
    assert bars, f"no 4x200 bar among {[f[:4] for f in d.painter.fills]}"
    x, y, w, h, _colour = bars[0]
    assert (x, y, w, h) == (104.0, 20.0, 4.0, 200.0)       # 12 - 2*4 = 4

    drawn.clear()
    d2 = Driver()

    def thin():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((100.0, 20.0))
        im.splitter("##v", im.Axis.X, 4.0, 200.0, 100.0, 200.0, bar_margin=4.0)
        im.end()

    d2.frame(thin)
    assert any(f[2] == 2.0 and f[3] == 200.0 for f in d2.painter.fills), \
        "a bar narrower than the floor should still be 2px, not 0 or negative"


def test_the_bar_changes_colour_when_hovered_and_when_held():
    d = Driver()

    def gui():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((100.0, 20.0))
        im.splitter("##v", im.Axis.X, 12.0, 200.0, 100.0, 200.0)
        im.end()

    def bar_colour(painter):
        return [f[4] for f in painter.fills if f[2] == 4.0 and f[3] == 200.0][0]

    d.move(-99.0, -99.0)
    d.frame(gui)
    idle = bar_colour(d.painter)

    d.move(106.0, 100.0)
    d.frame(gui)
    hovered = bar_colour(d.painter)

    d.press(106.0, 100.0)
    d.frame(gui)
    held = bar_colour(d.painter)

    assert idle != hovered != held and idle != held, (
        f"idle={idle} hovered={hovered} held={held}: a splitter that looks "
        f"the same in all three states gives no sign it can be grabbed")


def test_the_delay_gates_the_bar_colour_and_not_the_drag():
    """`hover_visibility_delay` exists so a bar between two panes does not
    light up every time the pointer crosses it on the way somewhere else. It
    must reach the *drawing*: gating only the mouse cursor is half a feature.
    """
    d = Driver()
    d.io.delta_time = 0.1                      # so two frames pass the 0.15s

    def gui():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((100.0, 20.0))
        im.splitter("##v", im.Axis.X, 12.0, 200.0, 100.0, 200.0,
                    hover_visibility_delay=0.15)
        im.end()

    def bar_colour(painter):
        return [f[4] for f in painter.fills if f[2] == 4.0 and f[3] == 200.0][0]

    d.move(-99.0, -99.0)
    d.frame(gui)
    idle = bar_colour(d.painter)

    d.move(106.0, 100.0)                       # arrive on the bar
    d.frame(gui)
    assert bar_colour(d.painter) == idle, "lit up before the delay elapsed"

    d.frame(gui)                               # 0.2s resting on it
    assert bar_colour(d.painter) != idle, "never lit up at all"

    # And a press on the very first frame still drags: a press is a press.
    d2 = Driver()
    sizes = [100.0, 200.0]
    d2.press(104.0, 50.0)
    _pane_frame(d2, sizes, hover_visibility_delay=10.0)
    d2.move(114.0, 50.0)
    assert _pane_frame(d2, sizes, hover_visibility_delay=10.0) is True
    assert sizes == [110.0, 190.0]


def test_two_splitters_with_different_ids_drag_independently():
    d = Driver()
    sizes = {"a": (100.0, 200.0), "b": (100.0, 200.0)}

    def gui():
        im.begin("w", SIZE)
        im.set_cursor_screen_pos((100.0, 20.0))
        _c, *sizes["a"] = im.splitter("##one", im.Axis.X, 8.0, 100.0, *sizes["a"])
        im.set_cursor_screen_pos((200.0, 20.0))
        _c, *sizes["b"] = im.splitter("##two", im.Axis.X, 8.0, 100.0, *sizes["b"])
        im.end()

    d.press(104.0, 50.0)
    d.frame(gui)
    d.move(124.0, 50.0)
    d.frame(gui)
    assert sizes["a"] == [120.0, 180.0]
    assert sizes["b"] == [100.0, 200.0], "the second splitter must not follow the first"


def test_a_full_two_pane_layout_stays_put_across_frames():
    """The shape cmc's main window uses: child / splitter / child, with the
    fractions carried between frames. Nothing may drift when nothing moves."""
    d = Driver()
    state = {"left": 150.0, "right": 242.0}

    def gui():
        im.begin("w", SIZE)
        x, y = im.get_cursor_screen_pos()
        im.begin_child((x, y, state["left"], 200.0))
        im.text("controls")
        im.end_child()
        im.same_line(0.0, 0.0)
        _c, state["left"], state["right"] = im.splitter(
            "##v", im.Axis.X, 8.0, 200.0, state["left"], state["right"],
            60.0, 80.0)
        im.same_line(0.0, 0.0)
        px, py = im.get_cursor_screen_pos()
        im.begin_child((px, py, state["right"], 200.0))
        im.text("plots")
        im.end_child()
        im.end()
        return px

    d.move(-99.0, -99.0)
    first = d.frame(gui)
    for _ in range(4):
        again = d.frame(gui)
    assert (state["left"], state["right"]) == (150.0, 242.0)
    assert again == first, "the right pane moved with nothing touching it"
