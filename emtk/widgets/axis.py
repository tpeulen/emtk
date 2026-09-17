"""A linear axis: value range, pixel span, and the transform between them.

Ported from ``implot_internal.h``'s ``ImPlotAxis`` (`junk/implot`) -- not
transcribed field for field (that struct also carries time/log scaling,
constraint ranges, linked axes and a picker, none of which this MVP needs),
but the one piece of arithmetic that every plot type shares is taken exactly:

    ScaleToPixel = (PixelMax - PixelMin) / (Max - Min)
    PlotToPixels(v) = PixelMin + ScaleToPixel * (v - Min)

The same formula serves an X axis (``pixel_min`` at the left, smaller than
``pixel_max`` at the right) and a Y axis (``pixel_min`` at the *bottom*,
numerically larger than ``pixel_max`` at the top, because screen pixels grow
downward) without a special case: handing the Y axis its pixels bottom-first
makes ``scale_to_pixel`` negative and the axis inverts itself.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = ["Axis", "nice_ticks"]


class Axis:
    """A value range mapped onto a pixel span.

    Parameters
    ----------
    v_min, v_max : float, optional
        Fixed range. ``None`` means auto-fit from the data handed to
        :meth:`fit` -- the common case, since a live readout's range is
        whatever the samples happen to cover this frame.
    """

    def __init__(self, v_min: float | None = None, v_max: float | None = None) -> None:
        self._fixed_min = v_min
        self._fixed_max = v_max
        self._fit_min = float("inf")
        self._fit_max = float("-inf")
        self.pixel_min = 0.0
        self.pixel_max = 0.0
        #: The range holds log10 of the samples. Ticks then go on whole
        #: decades, as ImPlot's log ticker puts them: a tick at 10**0.5 reads as
        #: "3.16228", which is a number nobody chose.
        self.log_decades = False

    def fit(self, values: Sequence[float]) -> None:
        """Extend the auto-fit range to cover *values*.

        A no-op on the axes whose bound was fixed at construction -- fitting
        a caller-specified range would silently override what they asked for.
        """
        for v in values:
            if not math.isfinite(v):
                continue  # a gap in a series, not a range to show
            if v < self._fit_min:
                self._fit_min = v
            if v > self._fit_max:
                self._fit_max = v

    def pad(self, fraction: float) -> None:
        """Widen the *fitted* range by ``fraction`` of its span on each side.

        A fixed bound stays where the caller put it. Without padding the
        extreme samples sit on the frame, where a curve's peak is half hidden
        by the border drawn over it.
        """
        if not (self._fit_max > self._fit_min):
            return
        margin = (self._fit_max - self._fit_min) * float(fraction)
        if self._fixed_min is None:
            self._fit_min -= margin
        if self._fixed_max is None:
            self._fit_max += margin

    @property
    def range(self) -> tuple[float, float]:
        """The range actually used: fixed bounds, or the fitted ones.

        A degenerate or never-fitted range (``max <= min``) returns ``(0, 1)``
        -- the same fallback :class:`~emtk.widgets.basic.PlotLines`
        uses, so an empty plot draws a frame rather than dividing by zero.
        """
        lo = self._fixed_min if self._fixed_min is not None else self._fit_min
        hi = self._fixed_max if self._fixed_max is not None else self._fit_max
        if not (hi > lo):
            return (0.0, 1.0)
        return (lo, hi)

    def set_pixels(self, pixel_min: float, pixel_max: float) -> None:
        """Place the range onto a pixel span. See the module docstring for
        why the same call serves an inverted (Y) axis."""
        self.pixel_min = pixel_min
        self.pixel_max = pixel_max

    def to_pixels(self, v: float) -> float:
        """Map a value to a pixel coordinate."""
        lo, hi = self.range
        span = hi - lo
        if span <= 0.0:
            return self.pixel_min
        scale = (self.pixel_max - self.pixel_min) / span
        return self.pixel_min + scale * (v - lo)

    def to_plot(self, px: float) -> float:
        """Map a pixel coordinate back to a value. Inverse of :meth:`to_pixels`."""
        lo, hi = self.range
        pixel_span = self.pixel_max - self.pixel_min
        if pixel_span == 0.0:
            return lo
        scale = pixel_span / (hi - lo) if hi > lo else 1.0
        return (px - self.pixel_min) / scale + lo

    def ticks(self, target_count: int = 4) -> list[float]:
        """"Nice" tick positions inside the range. See :func:`nice_ticks`."""
        lo, hi = self.range
        if self.log_decades:
            first, last = math.ceil(lo - 1e-9), math.floor(hi + 1e-9)
            if last > first:
                step = max(1, math.ceil((last - first) / max(target_count, 1)))
                return [float(v) for v in range(first, last + 1, step)]
            # Less than two decades on screen: nice numbers of the *samples*,
            # placed at their exponents. Nice exponents are not nice values --
            # a tick at 10**2.3 is 199.53, which no label can spell honestly.
            if hi - lo > 50.0 or lo < -300.0:
                return []
            return [math.log10(v) for v in nice_ticks(10.0 ** lo, 10.0 ** hi, target_count) if v > 0.0]
        return nice_ticks(lo, hi, target_count)

    def minor_ticks(self) -> list[float]:
        """The 2..9 multiples inside each decade of a log axis, as exponents.

        Empty on a linear axis, and when so many decades are shown that the
        lines would merge into a band.
        """
        if not self.log_decades:
            return []
        lo, hi = self.range
        if not (hi > lo) or hi - lo > 8.0:
            return []
        out = []
        for decade in range(math.floor(lo), math.ceil(hi) + 1):
            for multiple in range(2, 10):
                v = decade + math.log10(multiple)
                if lo <= v <= hi:
                    out.append(v)
        return out


def nice_ticks(lo: float, hi: float, target_count: int = 4) -> list[float]:
    """Tick positions at a "nice" step (1/2/5 x a power of ten) within [lo, hi].

    The standard algorithm (Heckbert, "Nice Numbers for Graph Labels") --
    picked because it is what every plotting library's default ticker traces
    back to, ImPlot's own ``ImPlotTicker`` included, and re-deriving a
    different one would make this port's gridlines match no one's intuition
    including the reference's.

    Parameters
    ----------
    lo, hi : float
        The range to place ticks in. Returns ``[]`` if ``hi <= lo``.
    target_count : int, optional
        Roughly how many ticks are wanted; the step is rounded to the nearest
        "nice" value so the actual count varies by a tick or two.
    """
    if not (hi > lo) or target_count < 1:
        return []
    span = hi - lo
    raw_step = span / target_count
    magnitude = 10.0 ** _floor_log10(raw_step)
    residual = raw_step / magnitude
    if residual > 5.0:
        step = 10.0 * magnitude
    elif residual > 2.0:
        step = 5.0 * magnitude
    elif residual > 1.0:
        step = 2.0 * magnitude
    else:
        step = magnitude

    first = _ceil_to_step(lo, step)
    ticks = []
    v = first
    # A fixed cap, not a while-True: floating point drift on a pathological
    # (span, step) pair must not hang the paint loop.
    for _ in range(target_count + 4):
        if v > hi + step * 1e-9:
            break
        ticks.append(round(v / step) * step)
        v += step
    return ticks


def _floor_log10(x: float) -> int:
    import math

    return math.floor(math.log10(x)) if x > 0.0 else 0


def _ceil_to_step(value: float, step: float) -> float:
    import math

    return math.ceil(value / step) * step
