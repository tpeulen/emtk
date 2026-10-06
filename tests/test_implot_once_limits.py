"""Data arriving after the first plot still gets its first ONCE limits."""

from emtk import im, implot
from emtk.testing import RecordingPainter


def test_first_once_request_on_initialized_axis_applies_then_preserves_pan():
    storage = {}
    io = im.IO()

    def frame(limits=None):
        with im.frame(RecordingPainter(), (0, 0, 360, 240), io=io, storage=storage):
            im.begin("Plot test")
            if implot.begin_plot("Counts", (320, 200)):
                if limits is not None:
                    implot.setup_axis_limits(implot.AXIS_Y1, *limits, implot.COND_ONCE)
                observed = implot.get_plot_limits()
                implot.end_plot()
            im.end()
        return observed

    frame()
    limits = frame((0, 200))
    assert (limits.y_min, limits.y_max) == (0, 200)
    assert (frame((0, 300)).y_min, frame((0, 300)).y_max) == (0, 300)
