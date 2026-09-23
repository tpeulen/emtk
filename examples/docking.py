"""Sticky windows and dock regions: :mod:`emtk.docking` in one small app.

Run it on any host::

    python -m emtk.native --app examples.docking:make_app      # from the emtk checkout
    python -m emtk.web.serve --app examples.docking:make_app
    python examples/docking.py                                  # the same, natively

Three regions -- *left*, *center* and *bottom* -- and five windows: a form
and a table sharing the left region as tabs, a plot filling the centre, a log
along the bottom, and a floating "Notes" window. Drag a window by its title bar: it snaps to the
edges and to other floating windows, and windows stuck to it travel with it
(shift-drag to take it alone). While it is dragged every region shows a drop
pad; over one, the region lights up, and releasing docks the window there,
filling the region. Drag a tab off its strip to float it again, drag the bars
between regions to resize them. The layout is remembered in
``~/.emtk/docking_example.json`` (``localStorage`` in a page).
"""
from __future__ import annotations

import math
import pathlib

from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, LayoutStore, Region, Split

#: The rows of the table window.
ROWS = [("alpha", 0.12, "ok"), ("beta", 3.4, "ok"), ("gamma", 12.0, "warn"),
        ("delta", 0.8, "ok"), ("epsilon", 7.25, "fail")]


class DockingExample:
    """The example's state and its windows."""

    def __init__(self, store: LayoutStore | None = None) -> None:
        self.frequency = 3.0
        self.damping = 0.35
        self.show_envelope = True
        self.name = "trace 1"
        self.notes = "Drag me onto a region's pad."
        self.docks = DockManager(
            Split("h", 0.28, Region("left"),
                  Split("v", 0.68, Region("center"), Region("bottom"))),
            store=store)
        self.docks.add_window("form", "Form", self.draw_form, dock="left")
        self.docks.add_window("table", "Table", self.draw_table, dock="left")
        self.docks.add_window("plot", "Plot", self.draw_plot, dock="center")
        self.docks.add_window("log", "Log", self.draw_log, dock="bottom")
        self.docks.add_window("notes", "Notes", self.draw_notes,
                              box=(620.0, 90.0, 260.0, 150.0))
        self.docks.load()

    # ------------------------------------------------------------ windows
    def draw_form(self, box) -> None:
        _c, self.name = im.input_text("name", self.name)
        _c, self.frequency = im.slider_float("frequency", self.frequency, 0.5, 10.0)
        _c, self.damping = im.slider_float("damping", self.damping, 0.0, 1.0)
        _c, self.show_envelope = im.checkbox("envelope", self.show_envelope)
        if im.button("Reset layout"):
            self.docks.reset()

    def draw_table(self, box) -> None:
        if im.begin_table("rows", 3):
            im.table_setup_column("name")
            im.table_setup_column("value")
            im.table_setup_column("state")
            im.table_headers_row()
            for name, value, state in ROWS:
                im.table_next_row()
                im.table_next_column()
                im.text(name)
                im.table_next_column()
                im.text(f"{value:.2f}")
                im.table_next_column()
                im.text(state)
            im.end_table()

    def draw_plot(self, box) -> None:
        xs = [i / 200.0 for i in range(401)]
        ys = [math.exp(-self.damping * x) * math.cos(self.frequency * x * math.pi)
              for x in xs]
        if implot.begin_plot(f"{self.name}##plot", (box[2], box[3])):
            implot.setup_axes("t", "signal")
            implot.plot_line("signal", xs, ys, len(xs))
            if self.show_envelope:
                env = [math.exp(-self.damping * x) for x in xs]
                implot.plot_line("envelope", xs, env, len(xs))
            implot.end_plot()

    def draw_log(self, box) -> None:
        for key in self.docks.windows:
            where = self.docks.region_of(key) or "floating"
            im.text(f"{key:>6}: {where}")

    def draw_notes(self, box) -> None:
        im.text_wrapped(self.notes)

    # ---------------------------------------------------------------- gui
    def gui(self) -> None:
        from emtk.im_core import get_current_context

        x, y, w, h = get_current_context().box
        self.docks.draw((x, y, w, h))


def make_app(store: bool = True) -> ImApp:
    """The example as an emtk app: ``python -m emtk.native --app examples.docking:make_app``."""
    layout = None
    if store:
        layout = LayoutStore("docking-example",
                             path=pathlib.Path.home() / ".emtk" / "docking_example.json")
    example = DockingExample(layout)
    app = ImApp(example.gui)
    app.example = example
    return app


if __name__ == "__main__":  # pragma: no cover - a window
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from emtk.native import main

    raise SystemExit(main(["--app", "examples.docking:make_app", "--size", "1100x720"]))
