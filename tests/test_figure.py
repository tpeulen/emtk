"""emtk.figure: a static figure is recorded, drawn by implot, and saved as PNG."""

from __future__ import annotations

import time

import pytest

from emtk import implot
from emtk.figure import Figure
from emtk.testing import RecordingPainter, png_decode


@pytest.fixture(autouse=True)
def _no_module_state_left_over():
    yield
    implot._cur.plot = None
    implot._cur.colormap = None


def _texts(fig):
    app = fig._app()
    painter = None
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(fig.size[0]), float(fig.size[1]))
    return " ".join(str(t) for t in painter.texts) + " ".join(str(c) for c in painter.calls)


def _every_item(fig):
    ax = fig.ax()
    ax.line([0, 1, 2], [1, 3, 2], color="C1", dash="--", marker="o", label="line")
    ax.scatter([0, 1, 2], [2, 1, 3], colors=["red", "green", "blue"], label="pts")
    ax.bars([0, 1, 2], [1, 2, 1], width=0.5, color="0.8")
    ax.hist([0.1, 0.2, 0.2, 1.5], bins=4, color="C2")
    ax.stairs([0, 1, 2], [0.5, 1.5, 1.0])
    ax.fill_between([0, 1, 2], [0, 0, 0], [1, 2, 1], color="C3")
    ax.errorbars([0, 1, 2], [1, 1, 1], [0.2, 0.3, 0.1])
    ax.vline(1.0, dash=":")
    ax.hline(1.0)
    ax.vspan(0.5, 1.5)
    ax.text(1.0, 2.5, "note")
    ax.set_title("All items")
    ax.set_labels(x="XLABEL", y="YLABEL")
    ax.set_xticks([0, 1, 2], ["a", "b", "c"])
    ax.legend("ne")
    return fig


def test_a_figure_is_a_png_of_the_requested_size(tmp_path):
    fig = _every_item(Figure(size=(420, 300), title="Figure title"))
    path = fig.save(tmp_path / "f.png")
    width, height, px = png_decode(path.read_bytes())
    assert (width, height) == (420, 300)
    assert any(px[i] != px[0] for i in range(0, len(px), 4)), "the picture is blank"
    w, h, rgba = fig.rgba()
    assert (w, h) == (420, 300) and len(rgba) == 420 * 300 * 4


def test_titles_axis_labels_and_tick_names_are_drawn():
    text = _texts(_every_item(Figure(size=(420, 300), title="Figure title")))
    for expected in ("Figure title", "All items", "XLABEL", "YLABEL", "note", "line", "pts"):
        assert expected in text, expected


def test_panels_heatmap_and_colorbar():
    fig = Figure(1, 2, size=(600, 260))
    fig.ax(0, 0).line([0, 1], [0, 1])
    fig.ax(0, 1).heatmap([[1, 2], [3, 4]], colormap="magma", cell_labels="%.0f", colorbar="rate")
    text = _texts(fig)
    assert "rate" in text and "4" in text
    assert fig[1] is fig.ax(0, 1) and fig[0, 0] is fig.axes[0]


def test_the_shared_plot_style_is_left_as_it_was():
    style = implot.get_style()
    before, minor, pad = list(style.colors), style.minor_alpha, style.fit_padding
    _every_item(Figure(size=(300, 200))).png_bytes()
    assert list(style.colors) == before and style.minor_alpha == minor
    assert style.fit_padding == pad


def test_what_is_not_offered_raises():
    ax = Figure().ax()
    with pytest.raises(ValueError):
        ax.line([0], [0], dash="~~")
    with pytest.raises(ValueError):
        ax.scatter([0], [0], marker="?")
    with pytest.raises(KeyError):
        ax.heatmap([[1]], colormap="no-such-map")
    with pytest.raises(ValueError):
        ax.legend("upper left")
    with pytest.raises(ValueError):
        Figure().save("figure.svg")
    with pytest.raises(ValueError):
        Figure(rows=0)


def test_hist_returns_numpy_compatible_edges_and_counts():
    np = pytest.importorskip("numpy")
    values = [0.1, 0.4, 0.4, 0.9, 1.0, 2.5]
    edges, counts = Figure().ax().hist(values, bins=5)
    ref_counts, ref_edges = np.histogram(values, bins=5)
    assert np.allclose(edges, ref_edges) and np.allclose(counts, ref_counts)
    _, dens = Figure().ax().hist(values, bins=5, density=True)
    assert np.allclose(dens, np.histogram(values, bins=5, density=True)[0])


def test_a_dashed_reference_line_is_drawn_in_dashes():
    """``plot_inf_lines`` honours ``spec.dash`` as ``plot_line`` does."""

    def segments(dash):
        fig = Figure(size=(300, 200))
        fig.ax().line([0, 1], [0, 1])
        fig.ax().vline(0.5, dash=dash)
        app = fig._app()
        painter = None
        for _ in range(2):
            painter = RecordingPainter()
            app.draw(painter, 0.0, 0.0, 300.0, 200.0)
        return len(painter.calls)

    assert segments(":") > segments("-") + 5


def test_a_panel_knows_its_figure_and_both_show_in_jupyter():
    fig = Figure(1, 2, size=(300, 150))
    ax = fig.ax(0, 1)
    assert ax.figure is fig
    assert fig._repr_png_()[:8] == b"\x89PNG\r\n\x1a\n"
    assert ax._repr_png_()[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_step_histogram_is_an_outline_ending_on_the_last_edge():
    ax = Figure().ax()
    edges, counts = ax.hist([0.1, 0.2, 0.8], bins=2, step=True, label="s")
    kind, data = ax._items[-1]
    assert kind == "stairs"
    assert data["x"] == edges and data["y"] == counts + [counts[-1]]


def test_a_hidden_panel_leaves_its_cell_empty():
    fig = Figure(1, 2, size=(400, 200))
    fig.ax(0, 0).line([0, 1], [0, 1]).set_title("shown")
    fig.ax(0, 1).set_title("HIDDEN").hide()
    text = _texts(fig)
    assert "shown" in text and "HIDDEN" not in text


def test_row_heights_follow_height_ratios():
    fig = Figure(2, 1, size=(300, 400), height_ratios=(3, 1))
    assert fig.height_ratios == [0.75, 0.25] and fig.width_ratios == [1.0]
    fig.ax(0, 0).line([0, 1], [0, 1])
    fig.ax(1, 0).line([0, 1], [1, 0])
    assert fig.png_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ValueError):
        Figure(2, 1, height_ratios=(1,))


def test_a_line_on_the_right_axis_gets_its_own_range():
    fig = Figure(size=(360, 220))
    ax = fig.ax()
    ax.line(range(10), [v / 10 for v in range(10)], label="left")
    ax.line(range(10), [1000 + v for v in range(10)], right=True, label="right")
    ax.set_right_label("RIGHTLAB")
    text = _texts(fig)
    assert "RIGHTLAB" in text and "1000" in text


def test_bars_horizontal_outlined_and_uneven():
    fig = Figure(1, 2, size=(420, 220))
    left = fig.ax(0, 0)
    left.bars([0.5, 2.0], [3, 1], width=[1.0, 2.0], edgecolor="k")
    left.hist([0.1, 0.2, 0.9], bins=[0.0, 0.5, 2.0])
    right = fig.ax(0, 1)
    right.bars([1, 2, 3], [5, 2, 4], horizontal=True, color="darkorange")
    right.hide_tick_labels(y=True).add_colorbar("Counts", 0, 9, "Greys")
    assert fig.png_bytes()[:4] == b"\x89PNG"
    assert "Counts" in _texts(fig)
    with pytest.raises(ValueError):
        Figure().ax().bars([1, 2], [1, 1], width=[1.0])
    with pytest.raises(KeyError):
        Figure().ax().add_colorbar("x", 0, 1, "no-such")


def test_horizontal_bars_lie_along_x_at_their_positions():
    from emtk import implot

    calls = []
    original = implot.plot_bars

    def record(label, xs, *args, ys=None, **kw):
        calls.append((list(xs), list(ys)))
        return original(label, xs, *args, ys=ys, **kw)

    implot.plot_bars = record
    try:
        fig = Figure(size=(200, 200))
        fig.ax().bars([1, 2, 3], [10, 20, 30], horizontal=True)
        fig.png_bytes()
    finally:
        implot.plot_bars = original
    assert calls[-1] == ([10.0, 20.0, 30.0], [1.0, 2.0, 3.0])


def test_fitted_axes_leave_five_percent_a_side():
    seen = []
    original = implot.end_plot

    def end():
        limits = implot.get_plot_limits()
        seen.append((limits.x_min, limits.x_max))
        return original()

    implot.end_plot = end
    try:
        fig = Figure(size=(300, 200))
        fig.ax().line([1, 2, 3], [0, 1, 0])
        fig.png_bytes()
    finally:
        implot.end_plot = original
    low, high = seen[-1]
    assert abs(low - 0.9) < 1e-9 and abs(high - 3.1) < 1e-9


def test_a_heatmap_fills_its_frame():
    seen = []
    original = implot.end_plot

    def end():
        limits = implot.get_plot_limits()
        seen.append((limits.x_min, limits.x_max, limits.y_min, limits.y_max))
        return original()

    implot.end_plot = end
    try:
        fig = Figure(size=(300, 200))
        fig.ax().heatmap([[1, 2], [3, 4]], extent=(0.0, 2.0, 1.0, 0.0))
        fig.png_bytes()
    finally:
        implot.end_plot = original
    assert seen[-1] == (0.0, 2.0, 0.0, 1.0)


def test_a_figure_saved_inside_another_apps_plot_leaves_it_intact():
    """An export button inside an app's frame: the app's plot and window go on."""
    import emtk
    from emtk.app import ImApp
    from emtk.testing import PixelPainter

    saved = []

    def gui():
        emtk.begin("host", (0.0, 0.0, 300.0, 200.0))
        if implot.begin_plot("##host", (280, 160)):
            implot.plot_line("a", [0, 1], [0, 1])
            fig = Figure(size=(120, 80))
            fig.ax().line([0, 1], [1, 0])
            saved.append(fig.png_bytes())
            implot.plot_line("b", [0, 1], [1, 1])
            implot.end_plot()
        emtk.end()

    app = ImApp(gui)
    for _ in range(2):
        app.draw(PixelPainter(300, 200), 0.0, 0.0, 300.0, 200.0)
    assert saved and saved[-1][:4] == b"\x89PNG"


def test_a_figure_saved_on_a_worker_thread_waits_for_the_gui_frame():
    """A background export saving a figure while the GUI thread is mid-plot.

    The figure swaps implot's and im's process-wide state; without the frame
    lock it did so in the middle of the host's frame, and the host's plot
    calls then ran against the figure's fresh state ("begin_plot() inside a
    plot", mismatched subplots) -- the trace browser's DOCX export on its job
    thread.
    """
    import threading

    import emtk
    from emtk.app import ImApp
    from emtk.testing import PixelPainter

    inside, saved, errors = threading.Event(), [], []

    def worker():
        inside.wait(5.0)
        fig = Figure(size=(120, 80))
        fig.ax().line([0, 1], [1, 0])
        saved.append(fig.png_bytes())

    def gui():
        emtk.begin("host", (0.0, 0.0, 300.0, 200.0))
        if implot.begin_subplots("##grid", 1, 2, (280, 160)):
            if implot.begin_plot("##left"):
                implot.plot_line("a", [0, 1], [0, 1])
                inside.set()
                # Keep plotting while the worker would run without the lock:
                # the host's calls interleave with the figure's state swap.
                deadline = time.monotonic() + 0.3
                while time.monotonic() < deadline:
                    implot.plot_line("b", [0, 1], [1, 1])
                implot.end_plot()
            if implot.begin_plot("##right"):
                implot.plot_line("c", [0, 1], [1, 0])
                implot.end_plot()
            implot.end_subplots()
        emtk.end()

    thread = threading.Thread(target=worker)
    thread.start()
    app = ImApp(gui)
    try:
        app.draw(PixelPainter(300, 200), 0.0, 0.0, 300.0, 200.0)
    except Exception as exc:  # noqa: BLE001 - the regression is any raise here
        errors.append(exc)
    thread.join(10.0)
    assert not errors, errors
    assert saved and saved[-1][:4] == b"\x89PNG"
    app.draw(PixelPainter(300, 200), 0.0, 0.0, 300.0, 200.0)  # and the next frame is clean
