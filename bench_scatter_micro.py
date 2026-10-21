"""Micro-benchmark comparing plot_line vs plot_scatter using emtk offscreen testing machinery."""
import time
import sys
from emtk import im, implot
from emtk.testing import RecordingPainter, PixelPainter

def run_single(painter_cls, kind, n_series, n_points, repeats=3):
    xs = list(range(n_points))
    ys = [float(i % 100) for i in range(n_points)]

    # Warmup
    painter = painter_cls() if painter_cls is RecordingPainter else painter_cls(800, 600)
    with im.frame(painter, (0, 0, 800, 600)):
        im.begin("Bench")
        if implot.begin_plot("Plot", (780, 560)):
            for s in range(n_series):
                if kind == "line":
                    implot.plot_line(f"s_{s}", xs, ys)
                else:
                    implot.set_next_marker_style(implot.MARKER_CIRCLE)
                    implot.plot_scatter(f"s_{s}", xs, ys)
            implot.end_plot()
        im.end()

    times = []
    for _ in range(repeats):
        painter = painter_cls() if painter_cls is RecordingPainter else painter_cls(800, 600)
        t0 = time.perf_counter()
        with im.frame(painter, (0, 0, 800, 600)):
            im.begin("Bench")
            if implot.begin_plot("Plot", (780, 560)):
                for s in range(n_series):
                    if kind == "line":
                        implot.plot_line(f"s_{s}", xs, ys)
                    else:
                        implot.set_next_marker_style(implot.MARKER_CIRCLE)
                        implot.plot_scatter(f"s_{s}", xs, ys)
                implot.end_plot()
            im.end()
        times.append((time.perf_counter() - t0) * 1000)
    return min(times)

def main():
    print(f"{'Painter':<18} | {'Series':<6} | {'Points':<7} | {'plot_line (ms)':<14} | {'plot_scatter (ms)':<17} | {'Ratio':<6}")
    print("-" * 80)
    for painter_cls in [RecordingPainter]:
        painter_name = painter_cls.__name__
        for n_series in [1, 20]:
            for n_points in [1000, 10000, 100000]:
                if n_series == 20 and n_points == 100000:
                    # Run 1 repeat if slow
                    repeats = 1
                elif n_points == 100000:
                    repeats = 1
                else:
                    repeats = 3
                t_line = run_single(painter_cls, "line", n_series, n_points, repeats=repeats)
                t_scatter = run_single(painter_cls, "scatter", n_series, n_points, repeats=repeats)
                ratio = t_scatter / max(t_line, 0.001)
                print(f"{painter_name:<18} | {n_series:<6} | {n_points:<7} | {t_line:<14.2f} | {t_scatter:<17.2f} | {ratio:<6.1f}x")

if __name__ == "__main__":
    main()
