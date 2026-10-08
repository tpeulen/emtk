"""Automatic tick labels fit their measured, rendered axis positions."""
from __future__ import annotations

import emtk
import pytest
from emtk import implot
from emtk.testing import RecordingPainter


@pytest.fixture(autouse=True)
def _close_plot():
    """Leave no open plot after a failed assertion."""
    yield
    implot._cur.plot = None


def _render(*, vertical=False, inverted=False, custom=None, auto=False, size=175):
    """Draw an axis at the narrow projection-panel size."""
    painter = RecordingPainter()
    axis_id = implot.AXIS_Y1 if vertical else implot.AXIS_X1
    other_id = implot.AXIS_X1 if vertical else implot.AXIS_Y1
    storage = {}
    for _ in range(2 if auto else 1):
        painter = RecordingPainter()
        with emtk.frame(painter, (0, 0, 400, 400), storage=storage):
            emtk.begin("w", (0, 0, 400, 400))
            implot.push_style_var(implot.STYLE_VAR_PLOT_PADDING, (0, 0))
            implot.begin_plot("##spacing", (240, size) if vertical else (size, 240))
            implot.setup_axis(axis_id, flags=implot.AXIS_FLAGS_INVERT if inverted else 0)
            implot.setup_axis_format(axis_id, "%.2f")
            implot.setup_axis(other_id, flags=implot.AXIS_FLAGS_NO_TICK_LABELS)
            if not auto:
                implot.setup_axis_limits(axis_id, 0, 120, implot.COND_ALWAYS)
            implot.setup_axis_limits(other_id, 0, 1, implot.COND_ALWAYS)
            if custom is not None:
                implot.setup_axis_ticks(axis_id, custom[0], labels=custom[1], keep_default=True)
            implot.plot_line("##line", [0, 120] if not vertical else [0, 1],
                             [0, 1] if not vertical else [0, 120])
            implot.end_plot()
            axis = implot._cur.last_plot.axes[axis_id]
            implot.pop_style_var()
            emtk.end()
    return painter, axis


@pytest.mark.parametrize("vertical", [False, True])
@pytest.mark.parametrize("inverted", [False, True])
@pytest.mark.parametrize("size", [120, 175, 240])
def test_narrow_axis_labels_do_not_overlap(vertical, inverted, size):
    """Final painter rectangles, including clamped edges, stay disjoint."""
    painter, axis = _render(vertical=vertical, inverted=inverted, size=size)
    dimension = 1 if vertical else 0
    labels = sorted(painter.texts, key=lambda item: item[dimension])
    assert len(labels) >= 2
    for previous, following in zip(labels, labels[1:]):
        assert previous[dimension] + previous[dimension + 2] <= following[dimension]
    # Label density must not change data limits or remove ticks/grid positions.
    assert axis.range == (0, 120)
    assert [round(t.plot_pos, 8) for t in axis.ticker.ticks] == list(range(0, 121, 20))
    assert all(t.pixel_pos >= min(axis.pixel_min, axis.pixel_max) for t in axis.ticker.ticks)


def test_custom_labels_take_priority_over_automatic_labels():
    """Explicit labels survive even when their own requested bounds overlap."""
    custom = ([45, 46], ["requested first label", "requested second label"])
    painter, axis = _render(custom=custom)
    assert all(label in painter.strings for label in custom[1])
    assert [t.text for t in axis.ticker.ticks[:2]] == custom[1]
    assert all(t.show_label for t in axis.ticker.ticks[:2])
    assert len(axis.ticker.ticks) == 9


def test_auto_fitted_axis_keeps_data_range_and_clear_labels():
    """Fitting data still determines limits before label placement."""
    painter, axis = _render(auto=True)
    assert axis.range[0] <= 0 and axis.range[1] >= 120
    labels = sorted(painter.texts, key=lambda item: item[0])
    assert len(labels) >= 2
    assert all(left[0] + left[2] <= right[0] for left, right in zip(labels, labels[1:]))


def test_label_placement_does_not_change_grid_or_data_rendering(monkeypatch):
    """Only text visibility changes; all geometry calls remain identical."""
    painter, axis = _render()
    monkeypatch.setattr(implot, "_space_tick_labels", lambda *args: None)
    baseline, original = _render()
    assert painter.fills == baseline.fills
    assert painter.triangles == baseline.triangles
    assert [(t.plot_pos, t.pixel_pos) for t in axis.ticker.ticks] == [
        (t.plot_pos, t.pixel_pos) for t in original.ticker.ticks
    ]
