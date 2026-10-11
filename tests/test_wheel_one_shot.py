"""One wheel notch is one step: a one-shot input reaches exactly one frame.

The bug (2026-10-12): one notch over a plot zoomed again on *every* following frame while the
pointer stayed on the plot, and stopped only when the pointer left it. ``IO.end_event`` kept
``mouse_wheel`` until "a widget consumed it", the plot reads the wheel without zeroing it, and
an ``ImApp`` whose wheel was still set asked the host for another frame -- so the host drew,
the plot zoomed, and the app asked again, forever.

The tests replay what a desktop delivers -- one notch, then the hand held still while the host
keeps drawing -- through :class:`emtk.testing_realistic.RealisticDriver`, and the old synthetic
test drivers that zeroed ``io.mouse_wheel`` themselves after each frame (doing the frame loop's
job) cannot hide it any more.
"""
from __future__ import annotations

import pytest

import emtk
from emtk import im, implot
from emtk.app import ImApp
from emtk.testing import RecordingPainter
from emtk.testing_realistic import RealisticDriver, assert_settles


@pytest.fixture(autouse=True)
def _clean():
    yield
    implot._cur.plot = None
    implot._cur.pending_popups = []


def _plot_app():
    out: dict = {}

    def gui():
        im.begin("w", (0, 0, 600, 420))
        implot.begin_plot("##p", (500, 300), implot.FLAGS_NO_LEGEND)
        implot.setup_axes("x", "y")
        implot.setup_axes_limits(0, 10, 0, 10)
        implot.plot_line("line", [0, 10], [0, 10])
        out["rect"] = implot.get_plot_pos() + implot.get_plot_size()
        implot.end_plot()
        lim = implot.get_plot_limits()
        out["limits"] = (lim.x_min, lim.x_max, lim.y_min, lim.y_max)
        im.end()

    app = ImApp(gui)
    app.io.wall_clock = False
    return app, out


def _centre(out):
    x, y, w, h = out["rect"]
    return x + w / 2, y + h / 2


def test_one_notch_over_a_plot_zooms_once_then_holds_still():
    app, out = _plot_app()
    driver = RealisticDriver(app, (600, 420), real_painter=False)
    driver.frame(2)
    centre = _centre(out)
    driver.hover(centre)
    before = out["limits"]
    driver.wheel(1, at=centre)
    after_notch = out["limits"]
    assert after_notch != before, "the notch did not zoom at all"
    driver.frame(30)              # the hand rests on the plot; the host keeps drawing
    assert out["limits"] == pytest.approx(after_notch), "the zoom kept going on idle frames"
    assert not app.animating(), "an idle plot keeps asking the host for frames"


def test_a_notch_is_delivered_to_exactly_one_frame():
    seen = []

    def gui():
        im.begin("w", (0, 0, 200, 200))
        seen.append(im.get_io().mouse_wheel)   # read, never consumed
        im.end()

    app = ImApp(gui)
    app.draw(RecordingPainter(), 0, 0, 200, 200)
    app.wheel(50, 50, 1)
    for _ in range(4):
        app.draw(RecordingPainter(), 0, 0, 200, 200)
    assert seen == [0.0, 1.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize("edge", ["wheel", "wheel_h", "click", "release", "double", "key", "text"])
def test_every_one_shot_edge_is_spent_by_the_frame_that_saw_it(edge):
    io = emtk.IO()
    io.wall_clock = False
    if edge == "wheel":
        io.mouse_wheel = 1.0
    elif edge == "wheel_h":
        io.mouse_wheel_h = 1.0
    elif edge == "click":
        io.mouse_clicked[0] = True
    elif edge == "release":
        io.mouse_released[0] = True
    elif edge == "double":
        io.mouse_double_clicked[0] = True
    elif edge == "key":
        io.key = 65
        io.key_events.append((65, "a", 0))
    else:
        io.text = "a"
    with emtk.frame(RecordingPainter(), (0, 0, 100, 100), io=io):
        pass
    assert io.one_shot_state() == io.__class__().one_shot_state()


def test_a_nested_frame_on_the_same_io_does_not_spend_the_outer_frames_edges():
    """A child drawn inside the parent's frame on the parent's IO is part of that frame:
    widgets the parent draws after the child still see this frame's wheel and click."""
    io = emtk.IO()
    io.wall_clock = False
    io.mouse_wheel = 1.0
    io.mouse_clicked[0] = True
    with emtk.frame(RecordingPainter(), (0, 0, 100, 100), io=io):
        with emtk.frame(RecordingPainter(), (0, 0, 50, 50), io=io):
            pass
        assert io.mouse_wheel == 1.0 and io.mouse_clicked[0]
    assert io.mouse_wheel == 0.0 and not io.mouse_clicked[0]


def test_assert_settles_flags_a_widget_that_keeps_changing():
    """The helper itself: a gui that drifts on every frame fails it."""
    state = {"n": 0}

    def gui():
        im.begin("w", (0, 0, 200, 200))
        state["n"] += 1
        im.end()

    app = ImApp(gui)
    driver = RealisticDriver(app, (200, 200), real_painter=False)
    driver.frame(2)
    with pytest.raises(AssertionError):
        assert_settles(driver, lambda d: d.wheel(1, at=(100, 100)), lambda: state["n"], frames=10)


def test_assert_settles_passes_a_plot_after_a_notch():
    app, out = _plot_app()
    driver = RealisticDriver(app, (600, 420), real_painter=False)
    driver.frame(2)
    centre = _centre(out)
    assert_settles(driver, lambda d: d.wheel(1, at=centre), lambda: out["limits"], frames=30)


# --------------------------------------------------------------------------- #
# Trackpads: many small deltas are notches in proportion, not a notch each
# --------------------------------------------------------------------------- #
def test_the_accumulator_gives_notches_in_proportion_to_the_deltas():
    from emtk.events import WheelAccumulator

    acc = WheelAccumulator(100.0)
    # a swipe worth three notches, as fifty small deltas, 1/60 s apart
    notches = sum(acc.feed(6.0, now=i / 60) for i in range(50))
    assert notches == 3


def test_a_flick_shorter_than_a_notch_still_counts_once():
    from emtk.events import WheelAccumulator

    acc = WheelAccumulator(100.0)
    assert acc.feed(10.0, now=0.0) == 1
    # ...and the rest of that gesture pays the notch back before giving another
    assert sum(acc.feed(10.0, now=0.01 * (i + 1)) for i in range(9)) == 0
    assert acc.feed(-10.0, now=5.0) == -1     # a new gesture, the other way


def test_a_mouse_notch_is_still_one_notch():
    from emtk.events import WheelAccumulator

    acc = WheelAccumulator(120.0)
    assert [acc.feed(120.0, now=t) for t in (0.0, 0.05, 1.0)] == [1, 1, 1]
    assert acc.feed(-240.0, now=2.0) == -2


def test_a_trackpad_swipe_zooms_in_proportion_and_then_holds_still():
    app, out = _plot_app()
    driver = RealisticDriver(app, (600, 420), real_painter=False)
    driver.frame(2)
    centre = _centre(out)
    driver.hover(centre)
    x0, x1 = out["limits"][:2]
    driver.swipe(2, at=centre)            # two notches' worth, fifty events + momentum
    swiped = out["limits"]
    span = swiped[1] - swiped[0]
    # two notches of ImPlot's default rate, not fifty
    step = (1.0 + 0.1) / (1.0 + 0.2)
    assert span == pytest.approx((x1 - x0) * step ** 2, rel=0.02)
    driver.frame(30)
    assert out["limits"] == pytest.approx(swiped)


def test_a_burst_of_notches_in_one_frame_zooms_in_proportion_but_bounded():
    from emtk.implot import WHEEL_NOTCHES_PER_FRAME

    app, out = _plot_app()
    driver = RealisticDriver(app, (600, 420), real_painter=False)
    driver.frame(2)
    centre = _centre(out)
    driver.hover(centre)
    span0 = out["limits"][1] - out["limits"][0]
    app.wheel(*centre, 50)                # fifty notches between two frames
    driver.frame(1)
    span = out["limits"][1] - out["limits"][0]
    step = (1.0 + 0.1) / (1.0 + 0.2)
    assert span == pytest.approx(span0 * step ** WHEEL_NOTCHES_PER_FRAME, rel=0.01)
