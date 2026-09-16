"""Regenerate the screenshots the documentation embeds.

Run from anywhere::

    python docs/make_screenshots.py

or through the docs Makefile::

    make -C docs screenshots

The images are committed, because a documentation build should not need to
execute the library it documents -- Read the Docs builds this repository with
nothing but Sphinx installed. Regenerating them is therefore a deliberate step,
taken when a widget changes what it draws.

Every picture comes out of :class:`emtk.testing.PixelPainter`, which is the
same pure-Python rasteriser the golden-image tests use: no window, no toolkit,
no display, and byte-identical output on every machine at a given commit.

The one thing added on top of what emtk itself draws is the frame -- a backdrop
and a titled panel around the widgets. emtk's :func:`~emtk.im.begin` draws no
window chrome (a window is a *box*, and decorating it is the host's job), so a
screenshot of the raw output is widgets floating on nothing. The frame here is
this script's, not the library's; it is drawn with the library's own style
colours so the picture still shows what emtk looks like in a host that draws
one.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import emtk                                    # noqa: E402
import emtk.im as im                           # noqa: E402
from emtk import style                         # noqa: E402
from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER  # noqa: E402
from emtk.testing import PixelPainter, save_png  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "_screenshots"

#: Around the panel, so it reads as a window rather than a full-bleed image.
MARGIN = 10.0
#: Height of the panel's title bar, matching the reference's own.
TITLE_H = 22.0
#: Inside the panel, so the first widget is not flush against the edge.
PAD = 8.0
#: A shade darker than ``WINDOW_BG``, so the panel has an edge to be seen at.
BACKDROP = (24, 24, 27, 255)


def shot(name: str, title: str, gui, size=(320, 200),
         clicks=(), hover=None) -> pathlib.Path:
    """Draw *gui* inside a titled panel and write ``_screenshots/<name>.png``.

    Parameters
    ----------
    clicks : sequence of (float, float)
        Points to click before the picture is taken, in image coordinates.
        A menu that is never clicked is a menu that is never open, and a
        screenshot of a closed menu shows nothing worth documenting.
    hover : (float, float), optional
        Where the pointer rests in the final frame. Left alone the pointer
        sits off-canvas, so nothing is spuriously highlighted.

    Notes
    -----
    One ``storage`` dict spans every frame. That is what makes a widget's
    state survive: :func:`emtk.im.frame` builds a fresh context each time and
    the storage is the only thing carried across, so without it a menu opened
    by frame two is shut again by frame three.
    """
    width, height = int(size[0]), int(size[1])
    body = (MARGIN, MARGIN + TITLE_H,
            width - MARGIN * 2, height - MARGIN * 2 - TITLE_H)
    inner = (body[0] + PAD, body[1] + PAD,
             body[2] - PAD * 2, body[3] - PAD * 2)
    io, storage = im.IO(), {}

    def draw():
        """One frame onto a fresh canvas; returns the painter that holds it."""
        painter = PixelPainter(width, height, background=BACKDROP)
        # The host's chrome, drawn before the frame so every widget lands on
        # top of it.
        painter.fill_rect(MARGIN, MARGIN, width - MARGIN * 2, TITLE_H,
                          style.TITLE_BG_ACTIVE)
        painter.text(MARGIN + PAD, MARGIN, 200.0, TITLE_H,
                     ALIGN_LEFT | ALIGN_VCENTER, title, style.TEXT)
        painter.fill_rect(*body, style.WINDOW_BG)
        with emtk.im.frame(painter, inner, io=io, storage=storage):
            gui(painter, inner)
        return painter

    draw()                                  # settles the layout
    for point in clicks:
        # A control fires on release inside, so a click is two frames.
        io.mouse_pos = point
        io.mouse_clicked_pos[0] = point
        io.mouse_clicked[0] = io.mouse_down[0] = True
        io.mouse_released[0] = False
        draw()
        io.mouse_clicked[0] = io.mouse_down[0] = False
        io.mouse_released[0] = True
        draw()
        io.mouse_released[0] = False
    io.mouse_pos = hover if hover is not None else (-1.0, -1.0)
    painter = draw()
    path = OUT / f"{name}.png"
    save_png(path, painter.width, painter.height, painter.px)
    return path


# --------------------------------------------------------------------------- #
# The pictures
# --------------------------------------------------------------------------- #

def hello_world(_painter, box):
    im.begin("Hello, world!", box)
    im.text("This is some useful text.")
    im.checkbox("Demo Window", True)
    im.button("Save")
    im.same_line()
    im.text("counter = 1")
    im.end()


def text(_painter, box):
    im.begin("Text", box)
    im.text("plain text")
    im.text_colored((255, 200, 50), "coloured text")
    im.text_disabled("disabled text")
    im.bullet_text("a bulleted item")
    im.separator()
    im.label_text("label", "value")
    im.end()


def basic(_painter, box):
    im.begin("Basic", box)
    im.checkbox("enabled", True)
    im.button("Normal")
    im.same_line()
    im.small_button("Small")
    im.same_line()
    im.arrow_button("left", im.Dir.LEFT)
    im.progress_bar(0.7, (0.0, 0.0, -1.0, 0.0))
    im.end()


def sliders(_painter, box):
    """Sliders only -- ``drag_float`` uses its label for the id and does not
    draw it, so a drag in this picture would be an unlabelled bar."""
    im.begin("Sliders", box)
    im.slider_float("float", 0.35, 0.0, 1.0)
    im.slider_int("int", 42, 0, 100)
    im.slider_angle("angle", 0.6)
    im.end()


def selection(_painter, box):
    im.begin("Selection", box)
    if im.collapsing_header("Section", True):
        im.selectable("option A", True)
        im.selectable("option B")
        im.selectable("option C")
    im.end()


def menus(_painter, box):
    """The bar is horizontal only because the caller says ``same_line``.

    ``begin_menu`` takes a row like every other control; the reference's bar
    lays its titles out itself, this port leaves that to the caller. Which
    also decides which menu is worth opening for the picture: the *last* one.
    An open menu draws its items inline, as indented rows rather than a
    floating popup, so opening any earlier menu would push the titles after it
    onto a second line.
    """
    im.begin("Menus", box)
    if im.begin_menu_bar():
        if im.begin_menu("File"):
            im.menu_item("New", "Ctrl+N")
            im.end_menu()
        im.same_line()
        if im.begin_menu("Edit"):
            im.menu_item("Copy", "Ctrl+C")
            im.end_menu()
        im.same_line()
        if im.begin_menu("View"):
            im.menu_item("Zoom in", "Ctrl++")
            im.menu_item("Zoom out", "Ctrl+-")
            im.separator()
            im.menu_item("Full screen", "F11")
            im.end_menu()
        im.end_menu_bar()
    im.text("body text")
    im.end()


def tabs(_painter, box):
    """The selected tab's body goes *after* the bar, not inside the item.

    ``begin_tab_item`` ends with its own ``same_line``, so the titles run
    left to right -- which also means anything submitted between two items
    lands between two titles. ``end_tab_bar`` breaks the line; the body
    belongs after that.
    """
    im.begin("Tabs", box)
    selected = None
    if im.begin_tab_bar("bar"):
        for title in ("First", "Second", "Third"):
            if im.begin_tab_item(title):
                selected = title
            im.end_tab_item()
        im.end_tab_bar()
    im.text(f"the {selected} tab's contents")
    im.separator()
    im.text("a tab bar shrinks its widest tab first")
    im.end()


def table(_painter, box):
    rows = [("alpha", "1.0", "on"), ("beta", "2.5", "off"),
            ("gamma", "3.25", "on"), ("delta", "4.0", "off")]
    im.begin("Table", box)
    if im.begin_table("t", 3):
        for heading in ("Name", "Value", "State"):
            im.table_setup_column(heading)
        im.table_headers_row()
        for row in rows:
            im.table_next_row()
            for cell in row:
                im.table_next_column()
                im.text(cell)
        im.end_table()
    im.end()


def plot(painter, box):
    """``widgets.plot`` draws against a painter directly, not through ``im``."""
    import math

    from emtk.widgets.plot import begin_plot

    xs = [i * 0.1 for i in range(96)]
    with begin_plot(painter, *box, show_ticks=True) as p:
        p.line("sin", xs, [math.sin(v) for v in xs])
        p.line("cos", xs, [math.cos(v) * 0.6 for v in xs])


#: ``(name, title, gui, size, clicks, hover)``. The clicks are what open a
#: menu or a header before the shutter; see :func:`shot`.
SHOTS = [
    ("hello_world", "Hello, world!", hello_world, (320, 200), (), None),
    ("text", "Text", text, (320, 200), (), None),
    ("basic", "Basic", basic, (320, 190), (), None),
    ("sliders", "Sliders", sliders, (360, 170), (), None),
    ("selection", "Selection", selection, (320, 200), (), None),
    ("menus", "Menus", menus, (360, 190), ((120.0, 45.0),), None),
    ("tabs", "Tabs", tabs, (320, 170), (), None),
    ("table", "Table", table, (360, 210), (), None),
    ("plot", "Plot", plot, (360, 240), (), None),
]


def readme_first_frame() -> pathlib.Path:
    """``first_frame.png``: the README's quick-start program, byte for byte.

    Not a :func:`shot`. Everything above draws the host chrome a real window
    would have around it, and the README's first program draws no such thing --
    a picture with a title bar under code that does not draw one is a picture
    that lies about its own listing. So this mirrors the listing exactly, and
    ``tests/test_docs.py`` re-runs the README's block and compares the pixels.
    """
    state = {"io": im.IO(), "storage": {}, "show": True, "f": 0.35,
             "counter": 0}

    def gui():
        im.begin("Hello, world!")
        im.text("This is some useful text.")
        _, state["show"] = im.checkbox("Show demo", state["show"])
        _, state["f"] = im.slider_float("float", state["f"], 0.0, 1.0)
        if im.button("Button"):
            state["counter"] += 1
        im.same_line()
        im.text("counter = %d" % state["counter"])
        im.end()

    painter = PixelPainter(320, 140, background=(30, 32, 38, 255))
    with emtk.frame(painter, (8, 8, 304, 124), io=state["io"],
                    storage=state["storage"]):
        gui()
    path = OUT / "first_frame.png"
    save_png(path, painter.width, painter.height, painter.px)
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, title, gui, size, clicks, hover in SHOTS:
        path = shot(name, title, gui, size, clicks, hover)
        print(f"{path.relative_to(OUT.parent.parent)}  {size[0]}x{size[1]}")
    path = readme_first_frame()
    print(f"{path.relative_to(OUT.parent.parent)}  320x140")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
