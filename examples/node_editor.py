"""A node editor, drawn to a PNG with no window and no toolkit.

Run it::

    python examples/node_editor.py

It writes ``node_editor.png`` beside itself: four nodes, two of them wired up,
with a slider and a combo inside node bodies and a minimap in the corner. That
is the whole surface -- there is no scene, no items, no view; the graph is the
code that draws it.
"""
from __future__ import annotations

import pathlib

import emtk
from emtk import im, nodes
from emtk.testing import PixelPainter, save_png

#: The graph this example draws. Ids are the editor's only handle on a node, so
#: they live with the data rather than being invented at draw time.
GRAPH: dict = {
    "nodes": [
        {"id": 1, "title": "Constant", "pos": (40.0, 40.0),
         "out": 11, "kind": "value", "value": 2.5},
        {"id": 2, "title": "Constant", "pos": (40.0, 200.0),
         "out": 21, "kind": "value", "value": 4.0},
        {"id": 3, "title": "Operation", "pos": (300.0, 110.0),
         "ins": (31, 32), "out": 33, "kind": "op", "op": 0},
        {"id": 4, "title": "Output", "pos": (560.0, 110.0),
         "ins": (41,), "kind": "sink"},
    ],
    "links": [(100, 11, 31), (101, 21, 32), (102, 33, 41)],
}

#: The operations the middle node offers.
OPS: list = ["Add", "Subtract", "Multiply", "Divide"]


def draw(state: dict) -> None:
    """Submit the whole editor for one frame.

    Parameters
    ----------
    state : dict
        Mutable model state: the editor context, and the value each node holds.
    """
    ctx = state["editor"]
    nodes.begin_node_editor(ctx, box=(0, 0, 820, 400))
    nodes.mini_map(ctx, size_fraction=0.22, location=nodes.MiniMapLocation.BOTTOM_RIGHT)

    for spec in GRAPH["nodes"]:
        nodes.set_node_grid_space_pos(ctx, spec["id"], spec["pos"])
        nodes.begin_node(spec["id"])
        # Without this a slider claims the whole editor's width, exactly as it
        # would in a window: an item's default width comes from the container,
        # and a node is not a container. imnodes' own examples push a width
        # here for the same reason.
        im.push_item_width(120.0)

        nodes.begin_node_title_bar()
        im.text(spec["title"])
        nodes.end_node_title_bar()

        for pin_id in spec.get("ins", ()):
            nodes.begin_input_attribute(pin_id)
            im.text("in")
            nodes.end_input_attribute()

        if spec["kind"] == "value":
            nodes.begin_static_attribute(spec["id"] * 1000)
            _, state["values"][spec["id"]] = im.slider_float(
                "value", state["values"][spec["id"]], 0.0, 10.0
            )
            nodes.end_static_attribute()
        elif spec["kind"] == "op":
            nodes.begin_static_attribute(spec["id"] * 1000)
            _, state["op"] = im.combo("op", state["op"], OPS)
            nodes.end_static_attribute()

        if "out" in spec:
            nodes.begin_output_attribute(spec["out"])
            im.text("out")
            nodes.end_output_attribute()

        im.pop_item_width()
        nodes.end_node()

    for link_id, start, end in GRAPH["links"]:
        nodes.link(link_id, start, end)

    nodes.end_node_editor()


def main() -> None:
    """Draw one frame and write it out."""
    state = {
        "editor": nodes.EditorContext(),
        "values": {1: 2.5, 2: 4.0},
        "op": 0,
        "io": im.IO(),
        "storage": {},
    }
    # The second node is selected so the screenshot shows both node states.
    nodes.select_node(state["editor"], 2)

    painter = PixelPainter(820, 400, background=(30, 32, 38, 255))
    with emtk.frame(painter, (0, 0, 820, 400), io=state["io"], storage=state["storage"]):
        draw(state)

    out = pathlib.Path(__file__).with_name("node_editor.png")
    save_png(str(out), painter.width, painter.height, painter.px)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
