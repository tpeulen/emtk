"""Static figures: describe a plot, get a PNG -- no window, GPU, toolkit or matplotlib.

For the pictures an application *writes* rather than shows: a report page, a
workflow step's diagnostic, a figure a script or an agent saves. Calls are
recorded on a :class:`Figure` and drawn by :mod:`emtk.implot` on the CPU
rasteriser (:mod:`emtk.export`), so the same code runs on a headless server.

.. code-block:: python

    from emtk.figure import Figure

    fig = Figure(size=(600, 450), title="Decay")
    ax = fig.ax()
    ax.line(t, counts, color="C0", label="data")
    ax.line(t, model, color="crimson", width=2, label="fit")
    ax.set_labels(x="t / ns", y="counts")
    ax.set_log(y=True)
    ax.legend()
    fig.save("decay.png")

Several panels: ``Figure(rows=2, cols=2)`` and ``fig.ax(row, col)``. The
spelling follows what plotting code is used to (``line``, ``scatter``,
``bars``, ``hist``, ``heatmap``, ``vspan``, ``text``, ``set_xticks``...), but
this is a recorder of a small vocabulary, not a clone of anything: what it
does not offer raises instead of drawing something else.

Colours are anything :func:`emtk.colormaps.to_rgba` reads (``"C0"``,
``"steelblue"``, ``"#1f77b4"``, ``(r, g, b)``); an item without one takes the
next colour of the ``C0``..``C9`` cycle of its panel.
"""

from __future__ import annotations

import contextlib
import math
import pathlib
from typing import Any, Iterable, Sequence

from . import colormaps

__all__ = ["Axes", "Figure", "colorbar_space"]

#: Matplotlib-style marker codes -> implot marker index (``MARKER_NAMES`` order).
_MARKERS = {"o": 0, "s": 1, "D": 2, "d": 2, "^": 3, "v": 4, "<": 5, ">": 6,
            "x": 7, "+": 8, "*": 9, "|": 10, "_": 11}
#: Dash patterns as (on, off) pixel lengths.
_DASHES = {"-": None, "solid": None, "--": (6.0, 4.0), "dashed": (6.0, 4.0),
           ":": (1.5, 3.0), "dotted": (1.5, 3.0), "-.": (6.0, 3.0), "dashdot": (6.0, 3.0)}
_LEGEND_AT = {"nw": "LOCATION_NORTH_WEST", "ne": "LOCATION_NORTH_EAST",
              "sw": "LOCATION_SOUTH_WEST", "se": "LOCATION_SOUTH_EAST",
              "n": "LOCATION_NORTH", "s": "LOCATION_SOUTH", "e": "LOCATION_EAST",
              "w": "LOCATION_WEST", "c": "LOCATION_CENTER"}

#: Width of a colour bar beside a heatmap, in pixels.
_COLORBAR_WIDTH = 70.0
#: A log colour bar is a plot of its own, with its ticks and label on the right
#: of a narrow strip: it needs more room than implot's linear scale.
_LOG_COLORBAR_WIDTH = 110.0
_GAP = 8.0


def colorbar_space(log: bool = False) -> float:
    """Pixels a colour bar takes beside its panel (bar and gap) -- for a layout
    that has to leave room for it, such as a map with marginals."""
    return (_LOG_COLORBAR_WIDTH if log else _COLORBAR_WIDTH) + _GAP


def _floats(values: Iterable) -> list[float]:
    return [float(v) for v in values]


def _rgba(colour, alpha: float | None = None) -> tuple[float, float, float, float]:
    return colormaps.to_rgba(colour, alpha)


def _histogram(values: Sequence[float], bins: int | Sequence[float],
               value_range: tuple[float, float] | None, density: bool):
    """``(edges, counts)`` as numpy's histogram computes them, numpy optional."""
    finite = [v for v in _floats(values) if math.isfinite(v)]
    if isinstance(bins, int):
        lo, hi = value_range if value_range is not None else (
            (min(finite), max(finite)) if finite else (0.0, 1.0))
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
        edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    else:
        edges = _floats(bins)
    counts = [0.0] * (len(edges) - 1)
    first, last = edges[0], edges[-1]
    import bisect

    for v in finite:
        if v < first or v > last:
            continue
        i = min(bisect.bisect_right(edges, v) - 1, len(counts) - 1)
        counts[i] += 1.0
    if density:
        total = sum(counts)
        counts = [c / (total * (edges[i + 1] - edges[i])) if total else 0.0
                  for i, c in enumerate(counts)]
    return edges, counts


class Axes:
    """One panel of a :class:`Figure`; every method records, nothing draws until saved.

    ``axes.figure`` is the figure it belongs to, so a function handed a panel
    can still save the whole picture.
    """

    def __init__(self, figure: Figure | None = None) -> None:
        self.figure = figure
        self._items: list[tuple[str, dict]] = []
        self._cycle = 0
        self.title = ""
        self.xlabel = ""
        self.ylabel = ""
        self.xlim: tuple[float, float] | None = None
        self.ylim: tuple[float, float] | None = None
        self.xlog = False
        self.ylog = False
        self.xticks: tuple[list[float], list[str] | None] | None = None
        self.yticks: tuple[list[float], list[str] | None] | None = None
        self.legend_at: str | None = None
        self.colorbar: dict | None = None
        self.yinvert = False
        self.hidden = False
        self.has_right = False
        self.y2label = ""
        self.no_xticklabels = False
        self.no_yticklabels = False

    # -- colours ----------------------------------------------------------
    def _colour(self, colour, alpha: float | None = None) -> tuple[float, float, float, float]:
        if colour is None:
            colour = f"C{self._cycle % 10}"
            self._cycle += 1
        return _rgba(colour, alpha)

    def _add(self, kind: str, **data) -> Axes:
        self._items.append((kind, data))
        return self

    # -- items --------------------------------------------------------------
    def line(self, x, y, *, color=None, width: float = 1.5, dash: str = "-",
             marker: str | None = None, marker_size: float = 4.0, alpha: float | None = None,
             label: str | None = None, right: bool = False) -> Axes:
        """A polyline through ``(x, y)``; ``dash`` is ``"-"``, ``"--"``, ``":"`` or ``"-."``.

        ``right=True`` plots against a second y-axis on the right, with its own
        range (a quantity in other units over the same x).
        """
        if dash not in _DASHES:
            raise ValueError(f"dash is one of {sorted(_DASHES)}, got {dash!r}")
        if marker is not None and marker not in _MARKERS:
            raise ValueError(f"marker is one of {sorted(_MARKERS)}, got {marker!r}")
        if right:
            self.has_right = True
        return self._add("line", x=_floats(x), y=_floats(y), color=self._colour(color, alpha),
                         width=float(width), dash=_DASHES[dash], marker=marker,
                         marker_size=float(marker_size), label=label, right=bool(right))

    def scatter(self, x, y, *, color=None, colors=None, size: float = 3.0,
                alpha: float | None = None, marker: str = "o", label: str | None = None) -> Axes:
        """Markers at ``(x, y)``; ``colors`` gives one colour per point."""
        if marker not in _MARKERS:
            raise ValueError(f"marker is one of {sorted(_MARKERS)}, got {marker!r}")
        per_point = None if colors is None else [_rgba(c, alpha) for c in colors]
        return self._add("scatter", x=_floats(x), y=_floats(y), color=self._colour(color, alpha),
                         colors=per_point, size=float(size), marker=marker, label=label)

    def bars(self, x, heights, *, width=0.8, color=None, alpha: float | None = None,
             edgecolor=None, horizontal: bool = False, label: str | None = None) -> Axes:
        """Bars centred on ``x``, ``width`` in data units (one value, or one per bar).

        ``horizontal=True`` lays them along x from the y-axis (``x`` is then
        the bar centres on y) -- a y-marginal histogram. ``edgecolor`` outlines
        each bar.
        """
        xs, ys = _floats(x), _floats(heights)
        widths = _floats(width) if isinstance(width, Iterable) else [float(width)] * len(xs)
        if len(widths) != len(xs):
            raise ValueError(f"width needs one value or {len(xs)}, got {len(widths)}")
        fill = self._colour(color, alpha)
        edge = None if edgecolor is None else _rgba(edgecolor)
        return self._add("bars", x=xs, y=ys, widths=widths, color=fill, edge=edge,
                         horizontal=bool(horizontal), label=label)

    def hist(self, values, bins: int | Sequence[float] = 40, *, range=None,  # noqa: A002
             density: bool = False, step: bool = False, color=None, alpha: float | None = None,
             width: float = 1.5, label: str | None = None) -> tuple[list[float], list[float]]:
        """A histogram of *values*; returns ``(edges, counts)``.

        Drawn as bars, or with ``step=True`` as the outline only (``width`` is
        then the line width) -- the readable choice for several overlaid
        distributions.
        """
        edges, counts = _histogram(values, bins, range, density)
        if step:
            # Each count held from its left edge to the next; the closing
            # point carries the last count to the right edge.
            xs = list(edges)
            ys = list(counts) + [counts[-1] if counts else 0.0]
            self._add("stairs", x=xs, y=ys, color=self._colour(color, alpha), width=float(width),
                      label=label)
            return edges, counts
        centres = [(a + b) / 2.0 for a, b in zip(edges[:-1], edges[1:])]
        widths = [b - a for a, b in zip(edges[:-1], edges[1:])]
        self.bars(centres, counts, width=widths, color=color, alpha=alpha, label=label)
        return edges, counts

    def stairs(self, x, y, *, color=None, width: float = 1.5, label: str | None = None) -> Axes:
        """A step curve (each value held until the next x)."""
        return self._add("stairs", x=_floats(x), y=_floats(y), color=self._colour(color),
                         width=float(width), label=label)

    def fill_between(self, x, lower, upper, *, color=None, alpha: float = 0.3,
                     label: str | None = None) -> Axes:
        """The band between two curves."""
        return self._add("band", x=_floats(x), lower=_floats(lower), upper=_floats(upper),
                         color=self._colour(color, alpha), label=label)

    def errorbars(self, x, y, err, *, color=None, label: str | None = None) -> Axes:
        """Symmetric vertical error bars of half-height ``err``."""
        return self._add("errorbars", x=_floats(x), y=_floats(y), err=_floats(err),
                         color=self._colour(color), label=label)

    def vline(self, x: float, *, color="0.5", width: float = 1.0, dash: str = "-",
              label: str | None = None) -> Axes:
        """A vertical line across the panel at ``x``."""
        return self._add("inf", value=float(x), horizontal=False, color=_rgba(color),
                         width=float(width), dash=_DASHES[dash], label=label)

    def hline(self, y: float, *, color="0.5", width: float = 1.0, dash: str = "-",
              label: str | None = None) -> Axes:
        """A horizontal line across the panel at ``y``."""
        return self._add("inf", value=float(y), horizontal=True, color=_rgba(color),
                         width=float(width), dash=_DASHES[dash], label=label)

    def vspan(self, x0: float, x1: float, *, color="C3", alpha: float = 0.1,
              label: str | None = None) -> Axes:
        """A shaded band from ``x0`` to ``x1`` over the panel's full height."""
        return self._add("vspan", x0=float(x0), x1=float(x1), color=_rgba(color, alpha),
                         label=label)

    def heatmap(self, values, *, colormap: str = "viridis", extent=None, levels=None,
                cell_labels: str | None = None, colorbar: str | None = None,
                label: str | None = None) -> Axes:
        """A 2-D array as coloured cells, row 0 at the top.

        ``extent`` is ``(x0, x1, y0, y1)`` (default: one unit per cell, cell
        centres on integers); ``levels`` is ``(low, high)`` for the colours
        (default: the data's range); ``cell_labels`` a ``%``-format written into
        every cell; ``colorbar`` a label, which draws a colour bar beside the
        panel.
        """
        rows = [list(r) for r in values]
        n_rows, n_cols = len(rows), (len(rows[0]) if rows else 0)
        flat = [float(v) for r in rows for v in r]
        finite = [v for v in flat if math.isfinite(v)]
        low, high = levels if levels is not None else (
            (min(finite), max(finite)) if finite else (0.0, 1.0))
        if high <= low:
            high = low + 1.0
        if extent is None:
            extent = (-0.5, n_cols - 0.5, n_rows - 0.5, -0.5)
        # (left, right, bottom, top): a bottom above the top is an image's own
        # orientation -- row 0 at the top and y growing downwards.
        if extent[2] > extent[3]:
            self.yinvert = True
        if not colormaps.has(colormap):
            raise KeyError(f"no colormap named {colormap!r}")
        if colorbar is not None:
            self.colorbar = {"label": colorbar, "low": float(low), "high": float(high),
                             "colormap": colormap}
        return self._add("heatmap", values=flat, rows=n_rows, cols=n_cols, low=float(low),
                         high=float(high), extent=tuple(float(e) for e in extent),
                         colormap=colormap, fmt=cell_labels or "", label=label)

    def mesh(self, x_edges, y_edges, values, *, colormap: str = "viridis", levels=None,
             log: bool = False, colorbar: str | None = None, label: str | None = None) -> Axes:
        """Coloured cells between *x_edges* and *y_edges* (``pcolormesh``).

        ``values[j][i]`` fills ``x_edges[i]..x_edges[i+1]`` by
        ``y_edges[j]..y_edges[j+1]``: row 0 at the *first* y edge, so a 2-D
        histogram goes in as it was counted. The edges need not be even, and
        the cells follow a log axis (:meth:`set_log`) -- unlike
        :meth:`heatmap`, whose cells are even in the data. ``log`` colours by
        ``log10`` of the value (``LogNorm``); a cell that is not positive is
        then left empty, as are non-finite cells always. ``levels`` is
        ``(low, high)`` for the colours (default: the data's range, the
        smallest *positive* value for ``log``); ``colorbar`` a label, which
        draws a colour bar -- on a log scale for ``log`` -- beside the panel.
        """
        xs, ys = _floats(x_edges), _floats(y_edges)
        rows = [list(map(float, r)) for r in values]
        if len(rows) != len(ys) - 1 or any(len(r) != len(xs) - 1 for r in rows):
            raise ValueError(f"values must be {len(ys) - 1} rows of {len(xs) - 1}, one per cell")
        flat = [v for r in rows for v in r if math.isfinite(v) and (v > 0.0 or not log)]
        if levels is not None:
            low, high = float(levels[0]), float(levels[1])
        elif flat:
            low, high = min(flat), max(flat)
        else:
            low, high = (1.0, 10.0) if log else (0.0, 1.0)
        if log:
            low = max(low, 1e-300)
            high = max(high, low * 10.0) if high <= low else high
        elif high <= low:
            high = low + 1.0
        if not colormaps.has(colormap):
            raise KeyError(f"no colormap named {colormap!r}")
        table = colormaps.lookup_table(colormap, 256)
        lo_t, hi_t = (math.log10(low), math.log10(high)) if log else (low, high)
        cells = []
        for j, r in enumerate(rows):
            for i, v in enumerate(r):
                if not math.isfinite(v) or (log and v <= 0.0):
                    continue
                t = ((math.log10(v) if log else v) - lo_t) / (hi_t - lo_t)
                k = min(255, max(0, int(t * 255.0 + 0.5)))
                cells.append((xs[i], xs[i + 1], ys[j], ys[j + 1], table[k]))
        if colorbar is not None:
            self.colorbar = {"label": colorbar, "low": low, "high": high,
                             "colormap": colormap, "log": bool(log)}
        return self._add("mesh", cells=cells, extent=(xs[0], xs[-1], ys[0], ys[-1]),
                         label=label)

    def text(self, x: float, y: float, s: str, *, color="k", offset=(0.0, 0.0)) -> Axes:
        """``s`` centred on the data point ``(x, y)``, shifted by ``offset`` pixels."""
        return self._add("text", x=float(x), y=float(y), s=str(s), color=_rgba(color),
                         offset=(float(offset[0]), float(offset[1])))

    # -- decoration -------------------------------------------------------
    def set_title(self, title: str) -> Axes:
        self.title = str(title)
        return self

    def set_labels(self, x: str | None = None, y: str | None = None) -> Axes:
        """Axis labels; ``None`` leaves one as it is."""
        if x is not None:
            self.xlabel = str(x)
        if y is not None:
            self.ylabel = str(y)
        return self

    def hide_tick_labels(self, x: bool = False, y: bool = False) -> Axes:
        """Drop the tick labels of an axis another panel already labels (a marginal)."""
        self.no_xticklabels = self.no_xticklabels or bool(x)
        self.no_yticklabels = self.no_yticklabels or bool(y)
        return self

    def add_colorbar(self, label: str, low: float, high: float, colormap: str = "viridis",
                     log: bool = False) -> Axes:
        """A colour bar beside this panel for ``low``..``high`` -- also for a map
        drawn in another panel (the colour bar of a map with marginals sits
        right of the y-marginal). ``log`` puts the bar on a log scale."""
        if not colormaps.has(colormap):
            raise KeyError(f"no colormap named {colormap!r}")
        if log and not (0.0 < float(low) < float(high)):
            raise ValueError("a log colour bar needs 0 < low < high")
        self.colorbar = {"label": str(label), "low": float(low), "high": float(high),
                         "colormap": colormap, "log": bool(log)}
        return self

    def set_right_label(self, label: str) -> Axes:
        """Label of the right-hand y-axis (used by ``line(..., right=True)``)."""
        self.y2label = str(label)
        return self

    def set_xlim(self, low: float, high: float) -> Axes:
        self.xlim = (float(low), float(high))
        return self

    def set_ylim(self, low: float, high: float) -> Axes:
        self.ylim = (float(low), float(high))
        return self

    def set_log(self, x: bool | None = None, y: bool | None = None) -> Axes:
        """Logarithmic axes; ``None`` leaves one as it is."""
        if x is not None:
            self.xlog = bool(x)
        if y is not None:
            self.ylog = bool(y)
        return self

    def set_xticks(self, values, labels: Sequence[str] | None = None) -> Axes:
        """Ticks at *values*, optionally named (categories)."""
        self.xticks = (_floats(values), None if labels is None else [str(s) for s in labels])
        return self

    def set_yticks(self, values, labels: Sequence[str] | None = None) -> Axes:
        self.yticks = (_floats(values), None if labels is None else [str(s) for s in labels])
        return self

    def _repr_png_(self) -> bytes:
        """A panel shows its whole figure in Jupyter."""
        if self.figure is None:
            raise ValueError("this panel belongs to no figure")
        return self.figure.png_bytes()

    def hide(self) -> Axes:
        """Leave this panel's cell empty (an unused cell of a grid)."""
        self.hidden = True
        return self

    def legend(self, at: str = "ne") -> Axes:
        """Show the labelled items' legend in a corner (``"ne"``, ``"nw"``, ``"se"``...)."""
        if at not in _LEGEND_AT:
            raise ValueError(f"legend position is one of {sorted(_LEGEND_AT)}, got {at!r}")
        self.legend_at = at
        return self


class Figure:
    """A grid of :class:`Axes`, saved as a PNG.

    Parameters
    ----------
    rows, cols : int
        Panel grid.
    size : (int, int)
        Picture size in pixels.
    title : str
        Centred above the panels.
    height_ratios, width_ratios : sequence of float, optional
        Relative row heights / column widths (e.g. ``(3, 1)`` for a curve
        above its residuals); equal when omitted.
    """

    def __init__(self, rows: int = 1, cols: int = 1, size=(640, 480), title: str = "",
                 height_ratios: Sequence[float] | None = None,
                 width_ratios: Sequence[float] | None = None):
        if rows < 1 or cols < 1:
            raise ValueError("a figure has at least one row and one column")
        self.rows, self.cols = int(rows), int(cols)
        self.height_ratios = _ratios(height_ratios, self.rows, "height_ratios")
        self.width_ratios = _ratios(width_ratios, self.cols, "width_ratios")
        self.size = (int(size[0]), int(size[1]))
        self.title = str(title)
        self._axes = [[Axes(self) for _ in range(self.cols)] for _ in range(self.rows)]

    def ax(self, row: int = 0, col: int = 0) -> Axes:
        """The panel at ``(row, col)``."""
        return self._axes[row][col]

    def __getitem__(self, key) -> Axes:
        if isinstance(key, tuple):
            return self.ax(*key)
        return self.ax(*divmod(int(key), self.cols))

    @property
    def axes(self) -> list[Axes]:
        """Every panel, row by row."""
        return [a for row in self._axes for a in row]

    # -- output -----------------------------------------------------------
    def png_bytes(self, dpi: float | None = None) -> bytes:
        """The figure encoded as PNG.

        ``dpi`` draws the same layout at ``dpi / 96`` device pixels per logical
        pixel -- text included -- for print; ``None`` is one to one.
        """
        from .export import png_bytes
        from .testing import png_encode

        k = 1.0 if dpi is None else float(dpi) / 96.0
        if abs(k - 1.0) < 1e-9:
            with _isolated():
                return png_bytes(self._app(), self.size, frames=2, painter=_painter())
        canvas = self._scaled_canvas(k)
        return png_encode(canvas.width, canvas.height, canvas.px)

    def _scaled_canvas(self, k: float):
        from .scaled_painter import ScaledPainter

        if _painter() == "pil":
            from .pil_painter import PilPainter as make
        else:
            from .testing import PixelPainter as make
        w, h = float(self.size[0]), float(self.size[1])
        dw, dh = max(1, int(round(w * k))), max(1, int(round(h * k)))
        app = self._app()
        canvas = None
        with _isolated():
            for _ in range(2):
                # White under the layout: a rounded-up last row or column is
                # outside it and would keep the painter's default black.
                canvas = make(dw, dh, background=(255, 255, 255, 255))
                app.draw(ScaledPainter(canvas, k), 0.0, 0.0, w, h)
        return canvas

    def svg_bytes(self) -> bytes:
        """The figure as an SVG document: lines, fills and text stay vectors."""
        from .vector_painter import SvgPainter

        return self._vector(SvgPainter).svg_bytes()

    def pdf_bytes(self) -> bytes:
        """The figure as a one-page PDF: lines, fills and text stay vectors."""
        from .vector_painter import PdfPainter

        return self._vector(PdfPainter).pdf_bytes()

    def _vector(self, make):
        w, h = float(self.size[0]), float(self.size[1])
        painter = make(w, h)
        app = self._app()
        with _isolated():
            # The first frame fits the axes; only the second is kept.
            app.draw(painter, 0.0, 0.0, w, h)
            painter.reset()
            app.draw(painter, 0.0, 0.0, w, h)
        return painter

    def to_bytes(self, fmt: str, dpi: float | None = None) -> bytes:
        """The figure as a ``"png"``, ``"svg"`` or ``"pdf"`` file's bytes."""
        fmt = fmt.lower().lstrip(".")
        if fmt == "png":
            return self.png_bytes(dpi=dpi)
        if fmt == "svg":
            return self.svg_bytes()
        if fmt == "pdf":
            return self.pdf_bytes()
        raise ValueError(f"emtk figures are written as png, svg or pdf, not {fmt!r}")

    def rgba(self) -> tuple[int, int, bytes]:
        """``(width, height, RGBA bytes)``, for a texture or an image widget."""
        from .export import grab

        with _isolated():
            canvas = grab(self._app(), self.size, frames=2, painter=_painter())
        return canvas.width, canvas.height, bytes(canvas.px)

    def _repr_png_(self) -> bytes:
        """Shown inline by Jupyter, as a plotting library's figure is."""
        return self.png_bytes()

    def save(self, path, dpi: float | None = None) -> pathlib.Path:
        """Write the figure to *path*: ``.png``, ``.svg`` or ``.pdf`` by suffix."""
        target = pathlib.Path(path)
        suffix = target.suffix.lower()
        if suffix not in (".png", ".svg", ".pdf"):
            raise ValueError(f"emtk figures are written as .png, .svg or .pdf, "
                             f"not {target.suffix or 'no suffix'}")
        target.write_bytes(self.to_bytes(suffix, dpi=dpi))
        return target

    # -- drawing ----------------------------------------------------------
    def _app(self):
        """The figure as an app: an app keeps the plots' state from the frame
        that fits the axes to the frame that is kept (axis labels and spans
        need the fitted limits)."""
        from .app import ImApp

        return ImApp(self._gui)

    def _gui(self) -> None:
        from . import im, implot
        from . import implot_internal as I

        style = implot.get_style()
        saved, saved_minor, saved_pad = list(style.colors), style.minor_alpha, style.fit_padding
        _paper(style, I)
        # A margin around fitted data, so a point on the extreme is not drawn
        # on the frame (an IRF spike at t=0 vanished into the axis without it).
        # implot pads by this fraction of *half* the range: 0.1 is 5% a side.
        style.fit_padding = (0.1, 0.1)
        try:
            w, h = float(self.size[0]), float(self.size[1])
            from .im_core import Col

            im.push_style_color(Col.WINDOW_BG, (255, 255, 255, 255))
            im.push_style_color(Col.BORDER, (255, 255, 255, 255))
            im.push_style_color(Col.TEXT, (0, 0, 0, 255))
            pushed = 3
            im.begin("##emtk-figure", (0.0, 0.0, w, h))
            left = im.get_cursor_pos()[0]
            if self.title:
                text_w = im.calc_text_size(self.title)[0]
                im.set_cursor_pos_x(max(0.0, (im.get_content_region_avail()[0] - text_w) / 2.0))
                im.text(self.title)
            avail_w, avail_h = im.get_content_region_avail()
            top = im.get_cursor_pos()[1]
            free_w = avail_w - (self.cols - 1) * _GAP
            free_h = avail_h - (self.rows - 1) * _GAP
            widths = [free_w * f for f in self.width_ratios]
            heights = [free_h * f for f in self.height_ratios]
            xs = [left + sum(widths[:c]) + c * _GAP for c in range(self.cols)]
            ys = [top + sum(heights[:r]) + r * _GAP for r in range(self.rows)]
            # Column by column, one aligned group each: the panels of a column
            # share the widest y-axis gutter, so stacked panels share their x
            # position (a curve above its residuals). A group across the whole
            # grid gave a narrow right column -- a y-marginal, its colour bar
            # -- the left column's gutter, and squeezed it to nothing.
            for c in range(self.cols):
                aligned = self.rows > 1 and implot.begin_aligned_plots(f"##emtk-figure-col{c}")
                try:
                    for r in range(self.rows):
                        im.set_cursor_pos((xs[c], ys[r]))
                        _draw_axes(self._axes[r][c], f"##p{r}_{c}", widths[c], heights[r],
                                   implot, I)
                finally:
                    if aligned:
                        implot.end_aligned_plots()
            im.set_cursor_pos((left, ys[-1] + heights[-1]))
            im.end()
            im.pop_style_color(pushed)
        finally:
            style.colors[:] = saved
            style.minor_alpha = saved_minor
            style.fit_padding = saved_pad


@contextlib.contextmanager
def _isolated():
    """Draw with a clean im and implot state, and put the caller's back after.

    A figure is often saved from *inside* an application's frame (an export
    button in an emtk app). implot keeps its state in one module-level
    context and im has one current context; drawn without this, the figure
    found the app's plot still open ("begin_plot() inside a plot") and left
    the app's window stack corrupted for the rest of its frame.

    It also takes :data:`emtk.im_core.FRAME_LOCK`: a figure is as often saved
    by a background job (a DOCX export) while the GUI thread is drawing, and
    the state swapped here is shared by every thread.
    """
    from . import im_core
    from .implot_internal import PlotContext, gp

    with im_core.FRAME_LOCK:
        saved_plot = dict(gp.__dict__)
        saved_im = getattr(im_core, "_CURRENT", None)
        gp.__dict__.update(PlotContext().__dict__)
        try:
            yield
        finally:
            gp.__dict__.clear()
            gp.__dict__.update(saved_plot)
            im_core.set_current_context(saved_im)


def _ratios(ratios, count: int, name: str) -> list[float]:
    """*ratios* normalised to sum to one; equal parts when ``None``."""
    if ratios is None:
        return [1.0 / count] * count
    values = [float(v) for v in ratios]
    if len(values) != count or any(v <= 0 for v in values):
        raise ValueError(f"{name} needs {count} positive values, got {ratios!r}")
    total = sum(values)
    return [v / total for v in values]


def _painter() -> str:
    try:
        import PIL  # noqa: F401, PLC0415
    except ImportError:
        return "pixel"
    return "pil"


def _paper(style, I) -> None:
    """A print look: white plot area, light grey grid, black text."""
    colours = {
        I.COL_FRAME_BG: (1.0, 1.0, 1.0, 1.0), I.COL_PLOT_BG: (1.0, 1.0, 1.0, 1.0),
        I.COL_PLOT_BORDER: (0.15, 0.15, 0.15, 1.0), I.COL_LEGEND_BG: (1.0, 1.0, 1.0, 0.92),
        I.COL_LEGEND_BORDER: (0.75, 0.75, 0.75, 1.0), I.COL_LEGEND_TEXT: (0.0, 0.0, 0.0, 1.0),
        I.COL_TITLE_TEXT: (0.0, 0.0, 0.0, 1.0), I.COL_INLAY_TEXT: (0.0, 0.0, 0.0, 1.0),
        I.COL_AXIS_TEXT: (0.0, 0.0, 0.0, 1.0), I.COL_AXIS_GRID: (0.88, 0.88, 0.88, 1.0),
        I.COL_AXIS_TICK: (0.0, 0.0, 0.0, 0.4),
    }
    from .implot import _style_colors

    # Through implot's own setter: it converts the colours to the form the
    # renderer reads (raw tuples written into ``style.colors`` lose the
    # rotated y-axis label).
    _style_colors(style, colours, 1.0)


def _colormap_index(implot, name: str) -> int:
    key = f"emtk.colormaps:{name}"
    index = implot.add_colormap(key, [tuple(c / 255.0 for c in row)
                                      for row in colormaps.lookup_table(name, 256)], qual=False)
    return index if index >= 0 else implot.get_colormap_index(key)


def _spec(I, **fields):
    spec = I.PlotSpec()
    for key, value in fields.items():
        setattr(spec, key, value)
    return spec


def _draw_axes(axes: Axes, ident: str, width: float, height: float, implot, I) -> None:
    from . import im

    if axes.hidden:
        im.dummy(width, height)
        return

    plot_w = width - (colorbar_space(axes.colorbar.get("log", False)) if axes.colorbar else 0.0)
    flags = I.FLAGS_NO_MENUS | I.FLAGS_NO_MOUSE_TEXT | I.FLAGS_NO_INPUTS
    if not axes.title:
        flags |= I.FLAGS_NO_TITLE
    labelled = any(data.get("label") for _, data in axes._items)
    if axes.legend_at is None or not labelled:
        flags |= I.FLAGS_NO_LEGEND
    if not implot.begin_plot((axes.title or "") + ident, (plot_w, height), flags):
        return
    try:
        x_flags = I.AXIS_FLAGS_NO_TICK_LABELS if axes.no_xticklabels else 0
        y_flags = (I.AXIS_FLAGS_INVERT if axes.yinvert else 0) | (
            I.AXIS_FLAGS_NO_TICK_LABELS if axes.no_yticklabels else 0)
        implot.setup_axes(axes.xlabel or None, axes.ylabel or None, x_flags, y_flags)
        if axes.has_right:
            implot.setup_axis(I.AXIS_Y2, axes.y2label or None, I.AXIS_FLAGS_AUX_DEFAULT)
        if axes.xlog:
            implot.setup_axis_scale(I.AXIS_X1, I.SCALE_LOG10)
        if axes.ylog:
            implot.setup_axis_scale(I.AXIS_Y1, I.SCALE_LOG10)
        xlim, ylim = axes.xlim, axes.ylim
        maps = [d for kind, d in axes._items if kind in ("heatmap", "mesh")]
        if maps:
            # An image fills its frame: no fit margin around a heatmap.
            x0, x1, y0, y1 = maps[0]["extent"]
            xlim = xlim or (min(x0, x1), max(x0, x1))
            ylim = ylim or (min(y0, y1), max(y0, y1))
        if xlim:
            implot.setup_axis_limits(I.AXIS_X1, *xlim, I.COND_ALWAYS)
        if ylim:
            implot.setup_axis_limits(I.AXIS_Y1, *ylim, I.COND_ALWAYS)
        if axes.xticks:
            implot.setup_axis_ticks(I.AXIS_X1, axes.xticks[0], labels=axes.xticks[1])
        if axes.yticks:
            implot.setup_axis_ticks(I.AXIS_Y1, axes.yticks[0], labels=axes.yticks[1])
        if axes.legend_at is not None and labelled:
            implot.setup_legend(getattr(I, _LEGEND_AT[axes.legend_at]))
        for k, (kind, d) in enumerate(axes._items):
            if d.get("right"):
                implot.set_axes(I.AXIS_X1, I.AXIS_Y2)
            _draw_item(kind, d, f"{d.get('label') or ''}##{k}", implot, I)
            if d.get("right"):
                implot.set_axes(I.AXIS_X1, I.AXIS_Y1)
    finally:
        implot.end_plot()
    if axes.colorbar:
        im.same_line(0.0, _GAP)
        bar = axes.colorbar
        if bar.get("log"):
            # A colour bar is no panel of the column: keep it out of the
            # column's gutter alignment.
            from .implot_internal import gp

            held = gp.current_alignment_v, gp.current_alignment_h
            gp.current_alignment_v = gp.current_alignment_h = None
            try:
                _log_colorbar(bar, ident, height, implot, I,
                              like=(bool(axes.xlabel), not axes.no_xticklabels))
            finally:
                gp.current_alignment_v, gp.current_alignment_h = held
        else:
            implot.colormap_scale(bar["label"], bar["low"], bar["high"],
                                  (_COLORBAR_WIDTH, height),
                                  cmap=_colormap_index(implot, bar["colormap"]))


def _log_colorbar(bar: dict, ident: str, height: float, implot, I,
                  like: tuple[bool, bool] = (False, False)) -> None:
    """A colour bar on a log axis: implot's own scale is linear only.

    Drawn as a narrow plot holding one column of 256 cells spaced evenly in
    ``log10``, with the ticks and the label on its right, as a colour bar has.
    ``like`` is whether the panel beside it has an x label and x tick labels:
    the bar reserves the same (blank) room under it, so its strip ends where
    the panel's plot area does instead of running down past the axis.
    """
    low, high = bar["low"], bar["high"]
    flags = (I.FLAGS_NO_MENUS | I.FLAGS_NO_MOUSE_TEXT | I.FLAGS_NO_INPUTS | I.FLAGS_NO_TITLE
             | I.FLAGS_NO_LEGEND)
    if not implot.begin_plot("##cbar" + ident, (_LOG_COLORBAR_WIDTH, height), flags):
        return
    try:
        has_label, has_ticks = like
        x_flags = I.AXIS_FLAGS_NO_GRID_LINES | I.AXIS_FLAGS_NO_TICK_MARKS
        if not has_ticks:
            x_flags |= I.AXIS_FLAGS_NO_TICK_LABELS
        implot.setup_axes(" " if has_label else None, bar["label"] or None, x_flags,
                          I.AXIS_FLAGS_OPPOSITE | I.AXIS_FLAGS_NO_GRID_LINES)
        if has_ticks:
            implot.setup_axis_ticks(I.AXIS_X1, [0.5], labels=[" "])
        implot.setup_axis_scale(I.AXIS_Y1, I.SCALE_LOG10)
        implot.setup_axis_limits(I.AXIS_X1, 0.0, 1.0, I.COND_ALWAYS)
        implot.setup_axis_limits(I.AXIS_Y1, low, high, I.COND_ALWAYS)
        table = colormaps.lookup_table(bar["colormap"], 256)
        l0, l1 = math.log10(low), math.log10(high)
        n = len(table)
        cells = [(0.0, 1.0, 10.0 ** (l0 + (l1 - l0) * k / n), 10.0 ** (l0 + (l1 - l0) * (k + 1) / n),
                  table[k]) for k in range(n)]
        _draw_mesh(cells, implot)
    finally:
        implot.end_plot()


def _draw_mesh(cells, implot) -> None:
    """Fill each ``(x0, x1, y0, y1, rgba)`` cell in data coordinates, clipped to the plot."""
    draw = implot.get_plot_draw_list()
    implot.push_plot_clip_rect()
    try:
        for x0, x1, y0, y1, colour in cells:
            ax, ay = implot.plot_to_pixels(x0, y0)
            bx, by = implot.plot_to_pixels(x1, y1)
            draw.add_rect_filled((min(ax, bx), min(ay, by)), (max(ax, bx), max(ay, by)), colour)
    finally:
        implot.pop_plot_clip_rect()


def _draw_item(kind: str, d: dict, label: str, implot, I) -> None:
    hidden = 0 if d.get("label") else I.ITEM_FLAGS_NO_LEGEND
    if kind == "line":
        spec = _spec(I, line_color=d["color"], line_weight=d["width"], dash=d["dash"],
                     flags=hidden)
        if d["marker"] is not None:
            spec.marker = _MARKERS[d["marker"]]
            spec.marker_size = d["marker_size"]
            spec.marker_fill_color = d["color"]
            spec.marker_line_color = d["color"]
        implot.plot_line(label, d["x"], d["y"], spec=spec)
    elif kind == "scatter":
        spec = _spec(I, marker=_MARKERS[d["marker"]], marker_size=d["size"],
                     marker_fill_color=d["color"], marker_line_color=d["color"],
                     line_weight=0.0, flags=hidden)
        if d["colors"] is not None:
            spec.marker_fill_colors = d["colors"]
            spec.marker_line_colors = d["colors"]
        implot.plot_scatter(label, d["x"], d["y"], spec=spec)
    elif kind == "bars":
        flags = hidden | (I.BARS_FLAGS_HORIZONTAL if d["horizontal"] else 0)
        spec = _spec(I, fill_color=d["color"], line_color=d["edge"] or d["color"], flags=flags)
        widths = d["widths"]
        # implot's horizontal bars take (lengths, positions), as ImPlot's do.
        pos, val = d["x"], d["y"]
        xs, ys = (val, pos) if d["horizontal"] else (pos, val)
        if widths and all(abs(w - widths[0]) <= 1e-12 * max(abs(widths[0]), 1.0) for w in widths):
            implot.plot_bars(label, xs, ys=ys, bar_size=widths[0], spec=spec)
        else:
            # Uneven bins: one bar per call, each its own width, one legend entry.
            for x, y, w in zip(xs, ys, widths):
                implot.plot_bars(label, [x], ys=[y], bar_size=w, spec=spec)
    elif kind == "stairs":
        implot.plot_stairs(label, d["x"], d["y"],
                           spec=_spec(I, line_color=d["color"], line_weight=d["width"],
                                      flags=hidden))
    elif kind == "band":
        implot.plot_shaded(label, d["x"], d["lower"], d["upper"],
                           spec=_spec(I, fill_color=d["color"], flags=hidden))
    elif kind == "errorbars":
        implot.plot_error_bars(label, d["x"], d["y"], d["err"],
                               spec=_spec(I, line_color=d["color"], flags=hidden))
    elif kind == "inf":
        flags = hidden | I.ITEM_FLAGS_NO_FIT
        if d["horizontal"]:
            flags |= I.INF_LINES_FLAGS_HORIZONTAL
        implot.plot_inf_lines(label, [d["value"]],
                              spec=_spec(I, line_color=d["color"], line_weight=d["width"],
                                         dash=d["dash"], flags=flags))
    elif kind == "vspan":
        # The panel's current y range: the figure draws two frames of one app,
        # and the second one sees the limits the first fitted. Infinite ys would shade
        # "to the edge" in the reference but reach the rasteriser unclipped.
        limits = implot.get_plot_limits()
        low, high = limits.y_min, limits.y_max
        implot.plot_shaded(label, [d["x0"], d["x1"]], [high, high], yref=low,
                           spec=_spec(I, fill_color=d["color"],
                                      flags=hidden | I.ITEM_FLAGS_NO_FIT))
    elif kind == "heatmap":
        x0, x1, y0, y1 = d["extent"]
        values = d["values"]
        if y0 > y1:
            # implot puts row 0 at the *top bound*; on an inverted axis that is
            # drawn at the bottom, so the rows go in reversed.
            cols = d["cols"]
            values = [v for r in range(d["rows"] - 1, -1, -1) for v in values[r * cols:(r + 1) * cols]]
        implot.push_colormap(_colormap_index(implot, d["colormap"]))
        try:
            implot.plot_heatmap(label, values, d["rows"], d["cols"], d["low"], d["high"],
                                d["fmt"], (x0, min(y0, y1)), (x1, max(y0, y1)),
                                spec=_spec(I, flags=hidden))
        finally:
            implot.pop_colormap()
    elif kind == "mesh":
        _draw_mesh(d["cells"], implot)
    elif kind == "text":
        from . import implot_internal

        implot.push_style_color(implot_internal.COL_INLAY_TEXT, d["color"])
        try:
            implot.plot_text(d["s"], d["x"], d["y"], d["offset"])
        finally:
            implot.pop_style_color()
    else:  # pragma: no cover - every recorder above maps to one branch
        raise ValueError(f"unknown item kind {kind!r}")
