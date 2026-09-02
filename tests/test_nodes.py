"""The node editor: layout, links, interaction and the transform.

Every test drives the editor with no window and no toolkit -- a
:class:`~cmtk.testing.RecordingPainter` where only the geometry matters, and
:class:`~cmtk.testing.PixelPainter` where the picture does.

The assertions are about behaviour, not about "it drew something". "A node's
rect encloses its contents" and "a drag of the same distance from two different
starting points moves the node the same way" are what prove the editor works;
counting draw calls proves only that it did not crash.
"""
from __future__ import annotations

import cmtk
from cmtk import im, nodes
from cmtk.testing import PixelPainter, RecordingPainter

#: The editor box every test draws into, unless it says otherwise.
BOX: tuple = (0, 0, 400, 300)


def _frame(build, io=None, storage=None, box=BOX, painter=None):
    """Run `build` inside one cmtk frame and hand back the painter.

    Parameters
    ----------
    build : callable
        Called with no arguments inside the frame.
    io : cmtk.IO, optional
        Carried across frames by the caller when a test needs two.
    storage : dict, optional
        Likewise.
    box : tuple
        The frame's box.
    painter : object, optional
        A painter to draw with; a fresh ``RecordingPainter`` when omitted.

    Returns
    -------
    object
        The painter that was drawn into.
    """
    painter = painter if painter is not None else RecordingPainter()
    with cmtk.frame(painter, box, io=io if io is not None else im.IO(),
                    storage=storage if storage is not None else {}):
        build()
    return painter


def _simple_graph(ctx, values=(1,), title="Node"):
    """Submit one node per id in `values`, each with one input and one output.

    Parameters
    ----------
    ctx : nodes.EditorContext
        The editor.
    values : tuple
        Node ids. Pin ids are derived as ``id * 10`` and ``id * 10 + 1``.
    title : str
        The title bar text, shared by every node.
    """
    nodes.begin_node_editor(ctx, box=BOX)
    for node_id in values:
        nodes.begin_node(node_id)
        nodes.begin_node_title_bar()
        im.text(title)
        nodes.end_node_title_bar()
        nodes.begin_input_attribute(node_id * 10)
        im.text("in")
        nodes.end_input_attribute()
        nodes.begin_output_attribute(node_id * 10 + 1)
        im.text("out")
        nodes.end_output_attribute()
        nodes.end_node()
    nodes.end_node_editor()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_a_node_rect_encloses_everything_drawn_inside_it():
    """The node's measured box must contain its title and both attributes.

    This is the property the whole editor rests on: the body is drawn from the
    measured rect, and pins are placed on its edges. A rect that only covers
    the *last* item still draws a node -- a small one, with the pins in the
    wrong place and the contents spilling out -- and no assertion about draw
    counts notices.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 30.0))
    _frame(lambda: _simple_graph(ctx, (1,), title="A long enough title"))

    x0, y0, x1, y1 = ctx._nodes[1].rect
    assert x1 - x0 > 80.0, "the rect is narrower than its title"
    # Title, "in" and "out" are three stacked rows, so the node cannot be one
    # row tall.
    assert y1 - y0 > 3 * 8.0

    for pin_id in (10, 11):
        px0, py0, px1, py1 = ctx._pins[pin_id].rect
        assert x0 <= px0 and px1 <= x1, f"pin {pin_id} is outside its node"
        assert y0 <= py0 and py1 <= y1, f"pin {pin_id} is outside its node"


def test_pins_sit_on_the_node_edges_not_on_their_labels():
    """An input pin is at the node's left edge and an output at its right.

    imnodes' rule, and the reason a column of pins lines up however wide the
    labels beside them are. Placing a pin at its *attribute's* edge instead
    makes a node with one long label and one short one grow a ragged left side.
    """
    ctx = nodes.EditorContext()
    _frame(lambda: _simple_graph(ctx, (1,)))

    x0, _, x1, _ = ctx._nodes[1].rect
    assert ctx._pins[10].pos[0] == x0
    assert ctx._pins[11].pos[0] == x1
    # And each sits at its own attribute's vertical centre, so two attributes
    # do not share a pin position.
    assert ctx._pins[10].pos[1] != ctx._pins[11].pos[1]


def test_a_static_attribute_gets_no_pin():
    """A static attribute takes part in no link, so it draws no pin."""
    ctx = nodes.EditorContext()

    def build():
        nodes.begin_node_editor(ctx, box=BOX)
        nodes.begin_node(1)
        nodes.begin_static_attribute(99)
        im.text("just a label")
        nodes.end_static_attribute()
        nodes.end_node()
        nodes.end_node_editor()

    _frame(build)
    assert ctx._nodes[1].pins == []
    assert 99 in ctx._pins, "it still needs an id, for is_any_attribute_active"


def test_a_node_that_stops_being_submitted_keeps_its_position():
    """Hiding a node and showing it again must not move it.

    The pool outlives the frame precisely so this holds; clearing it for
    unsubmitted nodes would make a filtered view of a graph destructive.
    """
    ctx = nodes.EditorContext()
    io, storage = im.IO(), {}
    nodes.set_node_grid_space_pos(ctx, 1, (123.0, 45.0))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _frame(lambda: _simple_graph(ctx, ()), io=io, storage=storage)

    assert nodes.get_node_grid_space_pos(ctx, 1) == (123.0, 45.0)


# ---------------------------------------------------------------------------
# The transform
# ---------------------------------------------------------------------------


def test_grid_and_screen_space_round_trip():
    """``to_grid`` undoes ``to_screen`` at any pan and zoom."""
    canvas = nodes.Canvas()
    canvas.origin = (17.0, 23.0)
    canvas.panning = (-40.0, 12.5)
    canvas.zoom = 1.75

    for point in ((0.0, 0.0), (100.0, -60.0), (-12.5, 33.25)):
        back = canvas.to_grid(canvas.to_screen(point))
        assert abs(back[0] - point[0]) < 1e-9
        assert abs(back[1] - point[1]) < 1e-9


def test_zooming_holds_the_point_under_the_pointer_still():
    """The grid point under the pointer stays under it across a zoom.

    Zooming about the origin instead walks whatever you were looking at off
    the edge, which reads as the canvas jumping.
    """
    canvas = nodes.Canvas()
    canvas.origin = (0.0, 0.0)
    pointer = (250.0, 140.0)
    before = canvas.to_grid(pointer)

    canvas.zoom_at(pointer, 1.4)
    after = canvas.to_grid(pointer)

    assert abs(after[0] - before[0]) < 1e-6
    assert abs(after[1] - before[1]) < 1e-6
    assert canvas.zoom > 1.0


def test_zoom_is_clamped_at_both_ends():
    """Repeated zooming stops at the range rather than running to zero."""
    canvas = nodes.Canvas()
    lo, hi = nodes.Canvas.ZOOM_RANGE
    for _ in range(80):
        canvas.zoom_at((0.0, 0.0), 0.5)
    assert canvas.zoom == lo
    for _ in range(80):
        canvas.zoom_at((0.0, 0.0), 2.0)
    assert canvas.zoom == hi


def test_a_node_moves_on_screen_when_the_canvas_pans():
    """Panning moves where a node draws without changing where it is stored."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (10.0, 10.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    first = ctx._nodes[1].rect

    ctx.canvas.panning = (60.0, -20.0)
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    second = ctx._nodes[1].rect

    assert abs((second[0] - first[0]) - 60.0) < 1e-6
    assert abs((second[1] - first[1]) + 20.0) < 1e-6
    assert nodes.get_node_grid_space_pos(ctx, 1) == (10.0, 10.0)


def test_fit_to_content_refuses_an_empty_graph():
    """Fitting before anything has been drawn must not zoom to the clamp.

    Fitting to an empty box is what renders a graph as a speck in the middle
    of the viewport, and it looks like a rendering bug rather than a call made
    too early.
    """
    ctx = nodes.EditorContext()
    ctx.fit_to_content((0, 0, 800, 600))
    assert ctx.canvas.zoom == 1.0
    assert ctx.canvas.panning == (0.0, 0.0)


def test_fit_to_content_frames_every_node():
    """After fitting, every node's grid box lies inside the editor box."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (0.0, 0.0))
    nodes.set_node_grid_space_pos(ctx, 2, (900.0, 700.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    ctx.fit_to_content(BOX)
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    for node_id in (1, 2):
        x0, y0, x1, y1 = ctx._nodes[node_id].rect
        assert BOX[0] <= x0 and x1 <= BOX[0] + BOX[2] + 1.0
        assert BOX[1] <= y0 and y1 <= BOX[1] + BOX[3] + 1.0


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_a_link_curve_leaves_rightwards_whichever_end_it_was_made_from():
    """The same pair of pins gives the same curve either way round.

    Without the swap, a link made by dragging from the input draws mirrored --
    the same connection with two appearances, depending on history nothing on
    screen records.
    """
    start, end = (100.0, 50.0), (300.0, 120.0)
    forward = nodes._cubic_bezier(start, end, "output", 0.1)
    backward = nodes._cubic_bezier(end, start, "input", 0.1)
    assert forward[:4] == backward[:4]


def test_a_link_control_point_offset_scales_with_the_distance():
    """A long link bows more than a short one, as imnodes' 0.25 rule gives."""
    short = nodes._cubic_bezier((0.0, 0.0), (40.0, 0.0), "output", 0.1)
    long_ = nodes._cubic_bezier((0.0, 0.0), (400.0, 0.0), "output", 0.1)
    assert (long_[1][0] - long_[0][0]) > (short[1][0] - short[0][0]) * 5


def test_a_link_naming_an_unsubmitted_pin_draws_nothing():
    """A dangling link must draw no curve at all.

    A ``(0, 0)`` fallback for the missing pin puts a line into the top-left
    corner, which reads as a corrupt graph rather than as a node that is not on
    screen. Measured by drawing the same frame twice -- once with the dangling
    link and once without -- and requiring the two to be identical: a curve
    that went anywhere would show up as extra calls.
    """
    def build(ctx, with_link):
        """Submit one node, optionally with a link to a pin nobody submitted."""
        nodes.begin_node_editor(ctx, box=BOX)
        nodes.begin_node(1)
        nodes.begin_output_attribute(11)
        im.text("out")
        nodes.end_output_attribute()
        nodes.end_node()
        if with_link:
            nodes.link(500, 11, 9999)
        nodes.end_node_editor()

    with_link = _frame(lambda: build(nodes.EditorContext(), True))
    without = _frame(lambda: build(nodes.EditorContext(), False))
    assert with_link.calls == without.calls


def test_a_link_between_two_submitted_pins_does_draw():
    """The counterpart, so the test above cannot pass by drawing nothing ever."""
    ctx_linked, ctx_bare = nodes.EditorContext(), nodes.EditorContext()
    for ctx in (ctx_linked, ctx_bare):
        nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
        nodes.set_node_grid_space_pos(ctx, 2, (220.0, 120.0))

    linked = _frame(lambda: _two_nodes_with_link(ctx_linked))
    bare = _frame(lambda: _two_nodes(ctx_bare))
    assert len(linked.calls) > len(bare.calls)


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


def _press(io, pos):
    """Put the pointer down at `pos`.

    Parameters
    ----------
    io : cmtk.IO
        The io the frame is driven with.
    pos : tuple
        Screen-space position.
    """
    io.mouse_pos = pos
    io.mouse_clicked_pos[0] = pos
    io.mouse_clicked[0] = True
    io.mouse_down[0] = True


def _move(io, pos):
    """Move the pointer to `pos` with the button still down.

    ``mouse_delta`` is derived from ``mouse_pos`` and ``mouse_pos_prev``, not
    set: writing it is what a host would get wrong, so the IO does not allow it.
    """
    io.mouse_pos = pos
    io.mouse_clicked[0] = False
    io.mouse_down[0] = True


def _release(io):
    """Lift the pointer."""
    io.mouse_down[0] = False
    io.mouse_released[0] = True


def test_clicking_a_node_selects_it():
    """A press inside a node's rect selects that node and nothing else."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    x0, y0, x1, y1 = ctx._nodes[1].rect
    _press(io, ((x0 + x1) * 0.5, (y0 + y1) * 0.5))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    assert nodes.get_selected_nodes(ctx) == [1]


def test_dragging_moves_the_node_by_the_pointer_travel():
    """A node follows the pointer one-for-one at zoom 1.

    Asserted as a *distance*, from two different starting points, because that
    is what separates a drag from a slider: a slider maps the absolute pointer
    position into its box, and would give a different answer for each start.
    """
    results = []
    for start in ((30.0, 30.0), (150.0, 90.0)):
        ctx = nodes.EditorContext()
        nodes.set_node_grid_space_pos(ctx, 1, start)
        io, storage = im.IO(), {}
        _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

        x0, y0, x1, y1 = ctx._nodes[1].rect
        grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
        _press(io, grab)
        _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
        _move(io, (grab[0] + 40.0, grab[1] + 25.0))
        _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

        moved = nodes.get_node_grid_space_pos(ctx, 1)
        results.append((moved[0] - start[0], moved[1] - start[1]))

    assert abs(results[0][0] - 40.0) < 1e-6
    assert abs(results[0][1] - 25.0) < 1e-6
    assert results[0] == results[1], "the drag depends on where it started"


def test_dragging_at_a_zoom_moves_the_node_by_the_scaled_distance():
    """At 2x zoom, 40 screen pixels of drag is 20 grid units of movement.

    Without dividing by the zoom the node runs away from the pointer, and at a
    small zoom it barely moves -- both of which read as an unresponsive editor
    rather than as a missing division.
    """
    ctx = nodes.EditorContext()
    ctx.set_zoom(2.0)
    nodes.set_node_grid_space_pos(ctx, 1, (10.0, 10.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    x0, y0, x1, y1 = ctx._nodes[1].rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _move(io, (grab[0] + 40.0, grab[1]))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    assert abs(nodes.get_node_grid_space_pos(ctx, 1)[0] - 30.0) < 1e-6


def test_a_node_marked_undraggable_does_not_move():
    """``set_node_draggable(False)`` pins a node but leaves it selectable."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (30.0, 30.0))
    nodes.set_node_draggable(ctx, 1, False)
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    x0, y0, x1, y1 = ctx._nodes[1].rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _move(io, (grab[0] + 60.0, grab[1] + 60.0))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    assert nodes.get_node_grid_space_pos(ctx, 1) == (30.0, 30.0)
    assert nodes.get_selected_nodes(ctx) == [1]


def _two_nodes(ctx):
    """Submit two nodes far enough apart that neither overlaps the other."""
    nodes.begin_node_editor(ctx, box=BOX)
    for node_id, title in ((1, "Source"), (2, "Sink")):
        nodes.begin_node(node_id)
        nodes.begin_node_title_bar()
        im.text(title)
        nodes.end_node_title_bar()
        if node_id == 1:
            nodes.begin_output_attribute(11)
            im.text("out")
            nodes.end_output_attribute()
        else:
            nodes.begin_input_attribute(21)
            im.text("in")
            nodes.end_input_attribute()
        nodes.end_node()
    nodes.end_node_editor()


def _two_nodes_with_link(ctx):
    """The same two nodes, wired output to input."""
    nodes.begin_node_editor(ctx, box=BOX)
    for node_id, title in ((1, "Source"), (2, "Sink")):
        nodes.begin_node(node_id)
        nodes.begin_node_title_bar()
        im.text(title)
        nodes.end_node_title_bar()
        if node_id == 1:
            nodes.begin_output_attribute(11)
            im.text("out")
            nodes.end_output_attribute()
        else:
            nodes.begin_input_attribute(21)
            im.text("in")
            nodes.end_input_attribute()
        nodes.end_node()
    nodes.link(500, 11, 21)
    nodes.end_node_editor()


def test_dragging_pin_to_pin_reports_a_created_link():
    """Releasing on another pin reports ``(output, input)``."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    nodes.set_node_grid_space_pos(ctx, 2, (220.0, 120.0))
    io, storage = im.IO(), {}
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    _press(io, ctx._pins[11].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    assert nodes.is_link_started(ctx) == 11

    _move(io, ctx._pins[21].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _release(io)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    assert nodes.is_link_created(ctx) == (11, 21)


def test_a_link_made_backwards_is_reported_output_first():
    """Dragging input-to-output still reports ``(output, input)``.

    The host stores a directed edge; making it depend on which end the user
    grabbed puts half the graph in backwards, and only some of the time.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    nodes.set_node_grid_space_pos(ctx, 2, (220.0, 120.0))
    io, storage = im.IO(), {}
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    _press(io, ctx._pins[21].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _move(io, ctx._pins[11].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _release(io)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    assert nodes.is_link_created(ctx) == (11, 21)


def test_two_pins_of_the_same_kind_do_not_make_a_link():
    """Output-to-output is not a connection, and is refused here.

    Refusing in the editor rather than in the host is what stops every host
    writing the same check -- and the host that forgets gets a graph with an
    edge that cannot be evaluated.
    """
    ctx = nodes.EditorContext()

    def build():
        nodes.begin_node_editor(ctx, box=BOX)
        for node_id, pin_id in ((1, 11), (2, 21)):
            nodes.begin_node(node_id)
            nodes.begin_output_attribute(pin_id)
            im.text("out")
            nodes.end_output_attribute()
            nodes.end_node()
        nodes.end_node_editor()

    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    nodes.set_node_grid_space_pos(ctx, 2, (220.0, 140.0))
    io, storage = im.IO(), {}
    _frame(build, io=io, storage=storage)

    _press(io, ctx._pins[11].pos)
    _frame(build, io=io, storage=storage)
    _move(io, ctx._pins[21].pos)
    _frame(build, io=io, storage=storage)
    _release(io)
    _frame(build, io=io, storage=storage)

    assert nodes.is_link_created(ctx) is None
    assert nodes.is_link_dropped(ctx) == 11


def test_a_drag_released_on_nothing_is_reported_dropped():
    """Releasing over empty canvas reports the pin it started from."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    nodes.set_node_grid_space_pos(ctx, 2, (220.0, 120.0))
    io, storage = im.IO(), {}
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    _press(io, ctx._pins[11].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _move(io, (380.0, 280.0))
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _release(io)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)

    assert nodes.is_link_created(ctx) is None
    assert nodes.is_link_dropped(ctx) == 11


def test_a_box_selection_catches_a_node_it_only_touches():
    """The rubber band selects on overlap, not on containment.

    Containment makes selecting a row of wide nodes need a drag wider than the
    viewport, which is not a selection anyone can perform.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    x0, y0, x1, y1 = ctx._nodes[1].rect

    # Start well clear of the node, and finish only just inside it.
    _press(io, (x1 + 60.0, y1 + 60.0))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _move(io, (x1 - 2.0, y1 - 2.0))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _release(io)
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    assert nodes.get_selected_nodes(ctx) == [1]


def test_the_per_frame_answers_are_cleared_between_frames():
    """A created link is reported once, not on every following frame.

    A stale answer here fires the host's "add an edge" callback again on every
    repaint, which fills the graph with duplicates and looks like a bug in the
    host.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    nodes.set_node_grid_space_pos(ctx, 2, (220.0, 120.0))
    io, storage = im.IO(), {}
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _press(io, ctx._pins[11].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _move(io, ctx._pins[21].pos)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    _release(io)
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    assert nodes.is_link_created(ctx) == (11, 21)

    io.mouse_released[0] = False
    _frame(lambda: _two_nodes(ctx), io=io, storage=storage)
    assert nodes.is_link_created(ctx) is None


# ---------------------------------------------------------------------------
# Style and scope
# ---------------------------------------------------------------------------


def test_a_pushed_colour_is_restored_by_its_pop():
    """``push_color_style``/``pop_color_style`` nest without leaking."""
    ctx = nodes.EditorContext()
    original = ctx.style.colors[nodes.Col.TITLE_BAR]

    def build():
        nodes.begin_node_editor(ctx, box=BOX)
        nodes.push_color_style(nodes.Col.TITLE_BAR, (1, 2, 3, 4))
        assert ctx.style.colors[nodes.Col.TITLE_BAR] == (1, 2, 3, 4)
        nodes.pop_color_style()
        nodes.end_node_editor()

    _frame(build)
    assert ctx.style.colors[nodes.Col.TITLE_BAR] == original


def test_a_mismatched_scope_says_which_scope_it_wanted():
    """Calling ``end_node`` outside a node names both scopes.

    An unbalanced begin/end otherwise surfaces as an unrelated failure much
    later, in code that has nothing to do with the mistake.
    """
    import pytest

    with pytest.raises(RuntimeError) as caught:
        nodes.end_node()
    message = str(caught.value)
    assert "end_node" in message and "node" in message


def test_the_editor_scope_closes_even_when_the_body_raises():
    """``editor_context`` is a context manager so a raise cannot wedge it.

    Without it, one exception inside a host's draw code leaves ``_scope`` at
    ``"editor"`` and every later frame raises instead -- an error that outlives
    its cause and points at the wrong place.
    """
    import pytest

    ctx = nodes.EditorContext()

    def build():
        with nodes.editor_context(ctx, box=BOX):
            raise ValueError("host code failed")

    with pytest.raises(ValueError):
        _frame(build)

    # The next frame works.
    _frame(lambda: _simple_graph(ctx, (1,)))
    assert 1 in ctx._nodes


# ---------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------


def test_a_node_body_is_painted_behind_its_contents():
    """The title text must survive the body that is drawn after it.

    The body's size is not known until the contents are laid out, so it is
    queued on a lower drawlist channel and merged underneath. Get the channel
    order wrong and the node is a filled rectangle with nothing on it -- which
    is exactly what a "did it draw?" assertion passes.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
    painter = PixelPainter(400, 300, background=(0, 0, 0, 255))
    _frame(lambda: _simple_graph(ctx, (1,), title="TITLE"), painter=painter)

    x0, y0, x1, y1 = ctx._nodes[1].rect

    def pixel(x: int, y: int) -> tuple:
        """Read one RGB triple out of the painter's flat RGBA buffer."""
        offset = (y * painter.width + x) * 4
        return tuple(painter.px[offset:offset + 3])

    title_band = [
        pixel(x, y)
        for y in range(int(y0) + 4, int(y0) + 16)
        for x in range(int(x0) + 6, int(x1) - 6)
    ]
    assert len(set(title_band)) > 1, (
        "the title bar is one flat colour: the body was painted over the text"
    )


# ---------------------------------------------------------------------------
# The title bar, and the two ways a drag lands
# ---------------------------------------------------------------------------


def test_the_title_bar_does_not_cover_the_first_body_row():
    """The body starts below the title bar, not underneath it.

    The bar is the title text expanded by the node padding, so its bottom edge
    is one padding below the text; the layout cursor, left alone, puts the next
    row one *item spacing* below the text, and spacing is smaller. The first
    control is then drawn half-buried under the bar -- the node still looks
    like a node, which is why nothing caught it.
    """
    ctx = nodes.EditorContext()
    first_row = {}

    def build():
        nodes.begin_node_editor(ctx, box=BOX)
        nodes.begin_node(1)
        nodes.begin_node_title_bar()
        im.text("Title")
        nodes.end_node_title_bar()
        nodes.begin_input_attribute(10)
        im.text("first row")
        nodes.end_input_attribute()
        nodes.end_node()
        nodes.end_node_editor()

    _frame(build)
    node = ctx._nodes[1]
    bar_bottom = node.title_rect[3] + ctx.style.node_padding[1] * ctx.canvas.zoom
    row_top = ctx._pins[10].rect[1]
    assert row_top >= bar_bottom, (
        f"the first body row starts at {row_top} but the title bar ends at "
        f"{bar_bottom}: it is drawn under the bar"
    )


def test_a_dragged_node_sticks_flush_against_its_neighbour():
    """Released near another node's edge, a node lands exactly against it."""
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    nodes.set_node_grid_space_pos(ctx, 2, (300.0, 40.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    left, right = ctx._nodes[1], ctx._nodes[2]
    width = (left.rect[2] - left.rect[0]) / ctx.canvas.zoom

    x0, y0, x1, y1 = left.rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)
    # Aim four pixels short of flush -- inside the stick distance, not on it.
    target_x = right.origin[0] - width - 4.0
    _move(io, (grab[0] + (target_x - 40.0), grab[1]))
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    assert abs(nodes.get_node_grid_space_pos(ctx, 1)[0]
               - (right.origin[0] - width)) < 1e-6
    assert ctx._stuck_to == {2}


def test_sticking_can_be_switched_off():
    """With ``stick_to_nodes`` off the node lands where it was dropped."""
    ctx = nodes.EditorContext()
    ctx.stick_to_nodes = False
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    nodes.set_node_grid_space_pos(ctx, 2, (300.0, 40.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    left, right = ctx._nodes[1], ctx._nodes[2]
    width = (left.rect[2] - left.rect[0]) / ctx.canvas.zoom
    x0, y0, x1, y1 = left.rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)
    target_x = right.origin[0] - width - 4.0
    _move(io, (grab[0] + (target_x - 40.0), grab[1]))
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    assert abs(nodes.get_node_grid_space_pos(ctx, 1)[0] - target_x) < 1e-6
    assert ctx._stuck_to == set()


def test_a_distant_node_does_not_stick():
    """Sticking needs overlap along the other axis, or nothing would line up.

    Without the overlap test a node in a distant row snaps to a column it is
    nowhere near, which is the jumpiness that makes people turn the feature
    off.
    """
    ctx = nodes.EditorContext()
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    nodes.set_node_grid_space_pos(ctx, 2, (300.0, 600.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    left, right = ctx._nodes[1], ctx._nodes[2]
    width = (left.rect[2] - left.rect[0]) / ctx.canvas.zoom
    x0, y0, x1, y1 = left.rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)
    target_x = right.origin[0] - width - 4.0
    _move(io, (grab[0] + (target_x - 40.0), grab[1]))
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    assert abs(nodes.get_node_grid_space_pos(ctx, 1)[0] - target_x) < 1e-6


def test_grid_snapping_rounds_to_the_grid():
    """With ``snap_to_grid`` on, a dropped node lands on a grid intersection."""
    ctx = nodes.EditorContext()
    ctx.snap_to_grid = True
    ctx.stick_to_nodes = False
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    x0, y0, x1, y1 = ctx._nodes[1].rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)
    _move(io, (grab[0] + 37.0, grab[1] + 19.0))
    _frame(lambda: _simple_graph(ctx, (1,)), io=io, storage=storage)

    spacing = ctx.style.grid_spacing
    x, y = nodes.get_node_grid_space_pos(ctx, 1)
    assert abs(x / spacing - round(x / spacing)) < 1e-6
    assert abs(y / spacing - round(y / spacing)) < 1e-6


def test_the_stick_distance_is_measured_in_screen_pixels():
    """Zooming out must not make everything stick to everything.

    A tolerance held in grid units reaches further across the screen the more
    you zoom out; at 0.2x a 8-pixel stick would span 40 grid units and every
    node in the graph would catch on its neighbours.
    """
    ctx = nodes.EditorContext()
    ctx.set_zoom(0.25)
    nodes.set_node_grid_space_pos(ctx, 1, (40.0, 40.0))
    nodes.set_node_grid_space_pos(ctx, 2, (300.0, 40.0))
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    left, right = ctx._nodes[1], ctx._nodes[2]
    width = (left.rect[2] - left.rect[0]) / ctx.canvas.zoom
    x0, y0, x1, y1 = left.rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)
    # 20 grid units short: 5 screen pixels at this zoom, so it sticks; the
    # same 20 units at zoom 1 would be 20 pixels and would not.
    target_x = right.origin[0] - width - 20.0
    _move(io, (grab[0] + (target_x - 40.0) * ctx.canvas.zoom, grab[1]))
    _frame(lambda: _simple_graph(ctx, (1, 2)), io=io, storage=storage)

    assert ctx._stuck_to == {2}


def test_a_multi_node_drag_keeps_its_shape():
    """Sticking one node of a group must not tear the group apart.

    Snapping each node separately makes two nodes that were level catch on
    different neighbours and end at different offsets -- the feature meant to
    tidy an arrangement destroying it instead.
    """
    ctx = nodes.EditorContext()
    for node_id, pos in ((1, (40.0, 40.0)), (2, (40.0, 200.0)), (3, (400.0, 40.0))):
        nodes.set_node_grid_space_pos(ctx, node_id, pos)
    io, storage = im.IO(), {}
    _frame(lambda: _simple_graph(ctx, (1, 2, 3)), io=io, storage=storage)

    nodes.select_node(ctx, 1)
    nodes.select_node(ctx, 2)
    before = (nodes.get_node_grid_space_pos(ctx, 1),
              nodes.get_node_grid_space_pos(ctx, 2))
    offset = (before[1][0] - before[0][0], before[1][1] - before[0][1])

    x0, y0, x1, y1 = ctx._nodes[1].rect
    grab = ((x0 + x1) * 0.5, (y0 + y1) * 0.5)
    _press(io, grab)
    _frame(lambda: _simple_graph(ctx, (1, 2, 3)), io=io, storage=storage)
    _move(io, (grab[0] + 250.0, grab[1] + 3.0))
    _frame(lambda: _simple_graph(ctx, (1, 2, 3)), io=io, storage=storage)

    after = (nodes.get_node_grid_space_pos(ctx, 1),
             nodes.get_node_grid_space_pos(ctx, 2))
    assert (after[1][0] - after[0][0], after[1][1] - after[0][1]) == offset


def test_a_plot_inside_a_node_is_not_painted_over_by_the_node():
    """An embedded plot survives the node body drawn after it.

    ``implot`` used to paint through ``ctx.p`` -- the real painter -- while
    every ``im_widgets`` control paints through the drawlist. The two are the
    same object until something splits the drawlist to draw out of order, which
    is exactly what a node editor does: the plot painted immediately, the node
    body replayed on top of it afterwards, and the plot was simply gone. No
    exception, no missing item, an empty rectangle where a curve should be.
    """
    from cmtk import implot

    ctx = nodes.EditorContext()
    xs = [float(i) for i in range(32)]
    ys = [float(i % 7) for i in range(32)]

    def build():
        nodes.begin_node_editor(ctx, box=BOX)
        nodes.set_node_grid_space_pos(ctx, 1, (20.0, 20.0))
        nodes.begin_node(1)
        nodes.begin_node_title_bar()
        im.text("Filter")
        nodes.end_node_title_bar()
        nodes.begin_static_attribute(99)
        if implot.begin_plot("##t", (160.0, 90.0), implot.ImPlotFlags_CanvasOnly):
            implot.plot_line("t", xs, ys)
            implot.end_plot()
        nodes.end_static_attribute()
        nodes.end_node()
        nodes.end_node_editor()

    painter = PixelPainter(BOX[2], BOX[3], background=(0, 0, 0, 255))
    _frame(build, painter=painter)

    def pixel(x: int, y: int) -> tuple:
        """Read one RGB triple out of the painter's flat RGBA buffer."""
        offset = (y * painter.width + x) * 4
        return tuple(painter.px[offset:offset + 3])

    x0, y0, x1, y1 = ctx._nodes[1].rect
    body = [
        pixel(x, y)
        for y in range(int(y0) + 30, int(y1) - 6)
        for x in range(int(x0) + 6, int(x1) - 6)
    ]
    assert len(set(body)) > 2, "the node body is flat: the plot was painted over"
