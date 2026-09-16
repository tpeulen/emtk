"""Six operations really are enough, and the contract says which six.

This is emtk's whole claim to portability: a surface that can fill a rectangle,
outline one, gradient one, draw a string, clip, and fill a triangle can draw
every widget here -- so a new platform is a class with those methods on it
rather than a port. The README says so, `painter_capabilities` behaves as if it
were so, and until this file nothing checked it.

The check has to be a *host*, not a mock. `RecordingPainter` implements
everything, including the optional operations, so every test that draws through
it would pass on a toolkit that had them all -- which is not the population
this claim is about.

The contract was also stated three ways and only one of them was machine-
readable: prose promising six, a `Painter` protocol declaring eleven methods
with three marked optional in a docstring a type checker cannot read, and a
run-time probe asking for a fourth (`text_rotated`) the protocol never
mentioned at all. `REQUIRED_OPERATIONS` and `OPTIONAL_OPERATIONS` are that
statement in code now, and the first test keeps the three in step.
"""
from __future__ import annotations

import inspect

import pytest

import emtk
from emtk.painter import (
    ACCELERATIONS,
    OPTIONAL_OPERATIONS,
    REQUIRED_OPERATIONS,
    Painter,
)


class SixOperations:
    """A host with the required operations and nothing else.

    Deliberately not a subclass of anything: a new platform's author starts
    from an empty class and the protocol, which is exactly what this is.
    """

    GLYPH_W = 7.0
    LINE_H = 16.0

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fill_rect(self, x, y, w, h, colour) -> None:
        self.calls.append("fill_rect")

    def stroke_rect(self, x, y, w, h, colour, width=1.0) -> None:
        self.calls.append("stroke_rect")

    def gradient_rect(self, x, y, w, h, top, bottom, horizontal=False) -> None:
        self.calls.append("gradient_rect")

    def text(self, x, y, w, h, align, string, colour, bold=False) -> None:
        self.calls.append("text")

    def push_clip(self, x, y, w, h) -> None:
        self.calls.append("push_clip")

    def pop_clip(self) -> None:
        self.calls.append("pop_clip")

    def fill_triangle(self, p0, p1, p2, colour) -> None:
        self.calls.append("fill_triangle")

    def text_width(self, string: str) -> float:
        return len(string) * self.GLYPH_W

    def line_height(self) -> float:
        return self.LINE_H


def _draw_a_bit_of_everything(painter, io=None):
    """One frame touching a widget from each family."""
    io = io or emtk.IO()
    with emtk.frame(painter, (0.0, 0.0, 600.0, 500.0), io=io, storage={}):
        emtk.begin("Everything")
        emtk.text("a label")
        emtk.button("Press")
        emtk.checkbox("check", True)
        emtk.slider_float("alpha", 0.5, 0.0, 1.0)
        emtk.input_text("name", "abc")
        emtk.combo("pick", 0, ["a", "b"])
        emtk.color_edit4("col", (1.0, 0.0, 0.0, 1.0))
        emtk.progress_bar(0.4)
        emtk.separator()
        if emtk.begin_table("t", 2):
            emtk.table_next_column()
            emtk.text("x")
            emtk.table_next_column()
            emtk.text("y")
            emtk.end_table()
        if emtk.begin_tab_bar("tabs"):
            if emtk.begin_tab_item("one"):
                emtk.end_tab_item()
            emtk.end_tab_bar()
        emtk.plot_lines("plot", [0.0, 1.0, 0.5])
        # The optional operations, exercised through the API that uses them:
        # a host without `set_font` must ignore the push rather than raise.
        emtk.push_font(object())
        emtk.text("with a font pushed")
        emtk.pop_font()
        emtk.end()
    return io


def test_the_protocol_and_the_two_lists_say_the_same_thing():
    """Every declared method is classified, and every classified one declared."""
    declared = {
        name
        for name, _ in inspect.getmembers(Painter, inspect.isfunction)
        if not name.startswith("_")
    }
    classified = set(REQUIRED_OPERATIONS) | set(OPTIONAL_OPERATIONS)
    assert declared - classified == set(), "declared but neither required nor optional"
    assert classified - declared == set(), "classified but not declared on Painter"
    assert not set(REQUIRED_OPERATIONS) & set(OPTIONAL_OPERATIONS)


def test_a_host_with_only_the_required_operations_can_draw_everything():
    """The claim, asked directly: no optional method, no fallback path skipped."""
    painter = SixOperations()
    for name in OPTIONAL_OPERATIONS + ACCELERATIONS:
        assert not hasattr(painter, name), f"the fixture is not minimal: it has {name}"
    _draw_a_bit_of_everything(painter)
    assert painter.calls, "nothing was drawn at all"
    assert {"fill_rect", "text"} <= set(painter.calls)


def test_a_minimal_host_reports_no_optional_capabilities():
    """`io.backend_flags` is how a widget decides whether to fall back."""
    io = _draw_a_bit_of_everything(SixOperations())
    flags = io.backend_flags
    assert not flags & emtk.BackendFlags.RENDERER_HAS_IMAGES
    assert not flags & emtk.BackendFlags.RENDERER_HAS_FONTS
    assert not flags & emtk.BackendFlags.RENDERER_HAS_ROTATED_TEXT


@pytest.mark.parametrize(
    "operation, flag",
    [
        ("image", "RENDERER_HAS_IMAGES"),
        ("set_font", "RENDERER_HAS_FONTS"),
        ("text_rotated", "RENDERER_HAS_ROTATED_TEXT"),
    ],
)
def test_an_optional_operation_lights_its_own_flag(operation, flag):
    """Adding one method to a host must be all it takes to be believed."""
    painter = SixOperations()
    setattr(type(painter), operation, lambda self, *a, **k: None)
    try:
        io = _draw_a_bit_of_everything(painter)
        assert io.backend_flags & getattr(emtk.BackendFlags, flag)
    finally:
        delattr(type(painter), operation)


def test_the_helpers_decompose_onto_the_required_operations():
    """A polyline, a filled circle and an arc on a host that has none of them."""
    from emtk import painter as painter_module

    painter = SixOperations()
    painter_module.polyline(
        painter, [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)], 2.0, (1, 2, 3, 4)
    )
    painter_module.fill_circle(painter, 10.0, 10.0, 5.0, (1, 2, 3, 4))
    painter_module.stroke_arc(painter, 10.0, 10.0, 5.0, 0.0, 1.5, 1.0, (1, 2, 3, 4))
    painter_module.fill_convex(painter, [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)], (1, 2, 3, 4))
    assert painter.calls, "the helpers drew nothing"
    assert set(painter.calls) <= set(REQUIRED_OPERATIONS), painter.calls
