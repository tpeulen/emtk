"""Render every section of :mod:`emtk.implot3d_demo` to a PNG, headlessly.

::

    python tools/implot3d_gallery.py OUT_DIR [substring ...]

Each section is drawn in its own window on :class:`emtk.testing.PixelPainter`
for a few frames (the first fits the axes, later ones draw the settled plot),
so the pictures are what the demo shows a user who opened that header. The
point is to *look* at them: axes on the outer edges, labels upright, surfaces
shaded and ordered back to front, meshes closed.
"""
from __future__ import annotations

import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import emtk  # noqa: E402
from emtk import implot3d_demo as demo  # noqa: E402
from emtk.testing import PixelPainter, save_png  # noqa: E402

HEIGHTS = {"Surface Plots": 640, "Image Plots": 520, "Per-Index Colors": 2150,
           "Plot Flags": 700, "Legend Options": 640, "Mesh Plots": 560, "Box Rotation": 640, "Box Scale": 500,
           "Offset and Stride": 580, "Help": 460, "Config": 560}


def render(title: str, fn, out: pathlib.Path, frames: int = 3, width: int = 520) -> float:
    io, storage = emtk.IO(), {}
    io.wall_clock = False
    io.mouse_pos = (-1.0, -1.0)
    height = HEIGHTS.get(title, 470)
    painter = None
    started = time.perf_counter()
    for _ in range(frames):
        painter = PixelPainter(width, height, background=(24, 24, 27, 255))
        with emtk.frame(painter, (8, 8, width - 16, height - 16), io=io, storage=storage):
            emtk.begin(title)
            fn()
            emtk.end()
    elapsed = (time.perf_counter() - started) / frames
    name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    save_png(out / f"{name}.png", painter.width, painter.height, painter.px)
    return elapsed


def main(argv) -> None:
    out = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path("implot3d_gallery")
    out.mkdir(parents=True, exist_ok=True)
    wanted = [a.lower() for a in argv[2:]]
    for _tab, title, fn in demo.SECTIONS:
        if wanted and not any(w in title.lower() for w in wanted):
            continue
        print(f"{title:28s} {render(title, fn, out):.2f} s/frame")


if __name__ == "__main__":
    main(sys.argv)
