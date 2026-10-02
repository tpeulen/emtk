"""``ImApp.draw_child``: one app's GUI inside a region of another's canvas.

The contract a workflow shell needs — chisurf's burst analysis shell composites
each step's app into its central area. The region becomes the child's viewport,
the clip keeps the child off the parent's chrome, and none of it may depend on
the painter having a transform (only the Qt painter does).
"""

from __future__ import annotations

import emtk.im as im
from emtk.app import ImApp


class RecordingPainter:
    """Records the six operations (and the clip stack) instead of performing."""

    def __init__(self) -> None:
        self.fills: list[tuple] = []
        self.strokes: list[tuple] = []
        self.strings: list[tuple] = []
        self.clips: list[tuple] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.fills.append((x, y, w, h, colour))

    def stroke_rect(self, x, y, w, h, edge, fill=None) -> None:
        self.strokes.append((x, y, w, h, edge, fill))

    def gradient_rect(self, x, y, w, h, stops, edge=None) -> None:
        self.fills.append((x, y, w, h, stops[0] if stops else None))

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.strings.append((x, y, string))

    def push_clip(self, x, y, w, h) -> None:
        self.clips.append((x, y, w, h))

    def pop_clip(self) -> None:
        if self.clips:
            self.clips.pop()

    def text_width(self, string) -> float:
        return len(string) * 7.0

    def line_height(self) -> float:
        return 12.0


class NoopClipPainter(RecordingPainter):
    """A painter whose clip does nothing — clipping is the parent's
    protection, not something the child may rely on to place itself."""

    def push_clip(self, x, y, w, h) -> None:
        pass

    def pop_clip(self) -> None:
        pass


def _filling_child(label: str):
    """An app whose one window fills whatever viewport it is given."""

    def gui() -> None:
        vp = im.get_main_viewport()
        im.set_next_window_pos((vp.pos[0], vp.pos[1]), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin(f"##{label}"):
            im.text(label)
        im.end()

    return ImApp(gui=gui)


def test_the_childs_viewport_is_the_region():
    """A child that fills its viewport fills the region it was given."""
    parent = ImApp(gui=lambda: None)
    child = _filling_child("child")
    painter = RecordingPainter()
    parent.draw_child(painter, child, 100.0, 50.0, 200.0, 100.0)

    # The window background lands exactly on the region.
    assert any(
        abs(x - 100.0) < 0.5 and abs(y - 50.0) < 0.5 and abs(w - 200.0) < 0.5
        for x, y, w, h, *_ in painter.fills + painter.strokes
    ), painter.fills + painter.strokes
    # ...and its content starts inside it.
    assert any(100.0 <= x <= 300.0 and 50.0 <= y <= 150.0 for x, y, s in painter.strings)


def test_the_clip_is_pushed_around_the_child_and_balanced():
    """The region is clipped while the child draws, and restored after."""
    parent = ImApp(gui=lambda: None)
    child = _filling_child("child")
    painter = RecordingPainter()

    seen: list[tuple] = []

    class Witness(RecordingPainter):
        def fill_rect(self, x, y, w, h, colour) -> None:
            seen.append(tuple(painter.clips))
            super().fill_rect(x, y, w, h, colour)

    parent.draw_child(Witness(), child, 100.0, 50.0, 200.0, 100.0)
    assert seen and all(clip == (100.0, 50.0, 200.0, 100.0) for clip in seen[0]), seen[0]
    assert painter.clips == []


def test_a_painter_whose_clip_is_a_noop_still_hosts_the_child():
    """Clip is the parent's protection, not the child's requirement."""
    parent = ImApp(gui=lambda: None)
    child = _filling_child("child")
    painter = NoopClipPainter()
    parent.draw_child(painter, child, 0.0, 0.0, 300.0, 200.0)
    assert painter.strings, "the child drew nothing"
