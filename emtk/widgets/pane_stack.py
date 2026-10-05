"""Several controls side by side or stacked, with a draggable bar between each pair.

:class:`~emtk.widgets.splitter.Splitter` is one bar between two panes, sized in
pixels. A stack of plots -- residuals over a decay, three strips sharing an
x-axis -- wants more panes, and wants them to keep their *proportion* when the
window is resized: pixel sizes drift the moment the box changes. So a stack
holds a weight per pane. The panes divide the box by weight, a drag moves weight
between the two panes beside the bar, and a pane dragged down to nothing stays
reachable because its bar does not go with it (collapsible, as a Qt splitter is).

The stack is itself a control, and a container: it draws its panes and routes
input to the pane under the pointer, with the pointer captured by whatever was
pressed -- a pane or a bar -- until the release, as a host does for a window.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..control import Control
from ..flags import Axis
from ..painter import Painter
from ..style import SEPARATOR, SEPARATOR_ACTIVE, SEPARATOR_HOVERED

__all__ = ["PaneStack"]

Rect = tuple[float, float, float, float]


class PaneStack(Control):
    """Panes along one axis, divided by weight, with draggable bars between them.

    Parameters
    ----------
    panes : sequence
        The child controls, first to last along *axis*.
    weights : sequence of float, optional
        Each pane's share of the room. Equal shares by default.
    axis : int, optional
        :data:`~emtk.flags.Axis.Y` stacks the panes top to bottom (the bars are
        horizontal); :data:`~emtk.flags.Axis.X` sets them side by side.
    thickness : float, optional
        The space a bar takes, which is also its grab target.
    collapsible : bool, optional
        Whether a pane may be dragged down to zero. Otherwise a pane keeps
        *min_size*.
    min_size : float, optional
        The smallest a pane gets while it is not collapsed.

    Attributes
    ----------
    weights : list of float
        The panes' shares, normalised to sum to one. Write it to set the split.
    user_sized : bool
        Whether the user has dragged a bar -- the moment a caller that applies
        its own default split should stop doing so.
    """

    def __init__(self, panes: Sequence[Any], weights: Sequence[float] | None = None,
                 axis: int = Axis.Y, thickness: float = 5.0, collapsible: bool = True,
                 min_size: float = 24.0) -> None:
        self.panes = list(panes)
        self.axis = 1 if axis == Axis.Y else 0
        self.thickness = float(thickness)
        self.collapsible = bool(collapsible)
        self.min_size = float(min_size)
        self.weights = self._normalised(weights)
        self.user_sized = False
        self.hovered_bar: int | None = None
        self._held_bar: int | None = None
        self._held_pane: int | None = None
        self._focus_pane: int | None = None
        self._hover_pane: int | None = None
        self._pane_boxes: list[Rect] = []
        self._bar_boxes: list[Rect] = []

    # -- geometry ---------------------------------------------------------- #
    def _normalised(self, weights: Sequence[float] | None) -> list[float]:
        n = len(self.panes)
        if n == 0:
            return []
        if weights is None or len(weights) != n:
            return [1.0 / n] * n
        values = [max(0.0, float(v)) for v in weights]
        total = sum(values)
        return [v / total for v in values] if total > 0 else [1.0 / n] * n

    def set_weights(self, weights: Sequence[float]) -> None:
        """Set the panes' shares (any positive scale)."""
        self.weights = self._normalised(weights)

    def layout(self, x: float, y: float, w: float, h: float) -> tuple[list[Rect], list[Rect]]:
        """Divide a box into the pane boxes and the bar boxes between them.

        The boxes tile the region exactly, in order along the axis.
        """
        n = len(self.panes)
        if n == 0:
            return [], []
        total = h if self.axis else w
        room = max(0.0, total - self.thickness * (n - 1))
        sizes = [room * f for f in self.weights]
        panes: list[Rect] = []
        bars: list[Rect] = []
        cursor = y if self.axis else x
        for i, size in enumerate(sizes):
            if i == n - 1:      # the last pane takes the rounding, so the tiling is exact
                size = max(0.0, (y + h if self.axis else x + w) - cursor)
            panes.append((x, cursor, w, size) if self.axis else (cursor, y, size, h))
            cursor += size
            if i < n - 1:
                bars.append((x, cursor, w, self.thickness) if self.axis
                            else (cursor, y, self.thickness, h))
                cursor += self.thickness
        return panes, bars

    def measure(self, p: Painter) -> tuple[float, float]:
        """Room for every pane's minimum and every bar."""
        n = max(len(self.panes), 1)
        along = n * self.min_size + (n - 1) * self.thickness
        return (200.0, along) if self.axis else (along, 120.0)

    # -- drawing ----------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Draw every pane with room in its box, then the bars between them."""
        self.remember(x, y, w, h)
        self._pane_boxes, self._bar_boxes = self.layout(x, y, w, h)
        for pane, box in zip(self.panes, self._pane_boxes):
            if box[2] >= 1.0 and box[3] >= 1.0:
                push = getattr(p, "push_clip", None)
                if callable(push):
                    p.push_clip(*box)
                try:
                    pane.draw(p, *box)
                finally:
                    pop = getattr(p, "pop_clip", None)
                    if callable(pop):
                        p.pop_clip()
        for i, (bx, by, bw, bh) in enumerate(self._bar_boxes):
            colour = (SEPARATOR_ACTIVE if self._held_bar == i
                      else SEPARATOR_HOVERED if self.hovered_bar == i else SEPARATOR)
            if self.axis:
                p.fill_rect(bx, by + bh * 0.5 - 1.0, bw, 2.0, colour)
            else:
                p.fill_rect(bx + bw * 0.5 - 1.0, by, 2.0, bh, colour)

    # -- input ------------------------------------------------------------- #
    def _bar_at(self, px: float, py: float) -> int | None:
        for i, (bx, by, bw, bh) in enumerate(self._bar_boxes):
            if bx <= px <= bx + bw and by <= py <= by + bh:
                return i
        return None

    def _pane_at(self, px: float, py: float) -> int | None:
        for i, (bx, by, bw, bh) in enumerate(self._pane_boxes):
            if bw >= 1.0 and bh >= 1.0 and bx <= px < bx + bw and by <= py < by + bh:
                return i
        return None

    def _call(self, index: int, name: str, *args):
        method = getattr(self.panes[index], name, None)
        return method(*args) if callable(method) else None

    def press(self, px: float, py: float, x: float, y: float, w: float, h: float,
              modifiers: int = 0, clicks: int = 1):
        """Grab a bar, or hand the press to the pane under the pointer."""
        self._pane_boxes, self._bar_boxes = self.layout(x, y, w, h)
        bar = self._bar_at(px, py)
        if bar is not None:
            self._held_bar = bar
            return self
        pane = self._pane_at(px, py)
        if pane is not None and pane != self._focus_pane and self._focus_pane is not None:
            self._call(self._focus_pane, "focus_lost")
        self._focus_pane = pane
        if pane is None:
            return None
        self._held_pane = pane
        return self._call(pane, "press", px, py, *self._pane_boxes[pane], modifiers, clicks)

    def drag(self, px: float, py: float, *_args: Any):
        """Move the held bar, or drag inside the held pane."""
        if self._held_bar is not None:
            self._move_bar(self._held_bar, py if self.axis else px)
            return self.weights
        if self._held_pane is not None:
            return self._call(self._held_pane, "drag", px, py, *self._pane_boxes[self._held_pane])
        return None

    def _move_bar(self, i: int, pointer: float) -> None:
        a, b = self._pane_boxes[i], self._pane_boxes[i + 1]
        start = a[1] if self.axis else a[0]
        pair = (a[3] + b[3]) if self.axis else (a[2] + b[2])
        floor = 0.0 if self.collapsible else self.min_size
        first = min(max(pointer - start - self.thickness * 0.5, floor), pair - floor)
        share = self.weights[i] + self.weights[i + 1]
        if pair <= 0.0:
            return
        self.weights[i] = share * first / pair
        self.weights[i + 1] = share - self.weights[i]
        self.user_sized = True

    def release(self, *_args: Any) -> None:
        """Let go of the bar or the pane that was held."""
        if self._held_pane is not None:
            self._call(self._held_pane, "release")
        self._held_bar = None
        self._held_pane = None

    def hover(self, px: float, py: float, *_args: Any) -> None:
        """Light the bar under the pointer, or tell the pane under it."""
        self.hovered_bar = self._bar_at(px, py)
        pane = None if self.hovered_bar is not None else self._pane_at(px, py)
        self._hover_pane = pane
        if pane is not None:
            self._call(pane, "hover", px, py, *self._pane_boxes[pane])

    def tooltip_at(self, px: float, py: float):
        """The tooltip of the pane under the pointer, as that pane names it."""
        pane = self._pane_at(px, py)
        if pane is None:
            return ""
        return self._call(pane, "tooltip_at", px, py) or ""

    def scroll(self, rows: float, *_args: Any):
        """The wheel goes to the pane under the pointer (else the one last pressed)."""
        target = self._hover_pane if self._hover_pane is not None else self._focus_pane
        if target is None:
            return None
        return self._call(target, "scroll", rows)

    def key(self, key: int, text: str = "", modifiers: int = 0):
        """Keys go to the pane that was pressed last."""
        if self._focus_pane is None:
            return False
        return bool(self._call(self._focus_pane, "key", key, text, modifiers))

    def focus_lost(self) -> None:
        """Pass the loss of focus on to the pane that had it."""
        if self._focus_pane is not None:
            self._call(self._focus_pane, "focus_lost")
        self._focus_pane = None
