"""The compatibility surface does what its name says.

Resolving a name is half of a port working; the other half is that the thing
behind it behaves. A function added only to raise a coverage count is worse
than a missing one -- the port compiles and the picture is wrong -- so
everything added for compatibility is exercised here at least once.

Grouped the way ``imgui_widgets.cpp`` groups them.
"""
from __future__ import annotations

import math

import pytest

import emtk
from emtk.testing import RecordingPainter


@pytest.fixture
def ctx():
    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 400.0, 400.0)) as context:
        context.painter = painter
        yield context


# --------------------------------------------------------------------------- #
# Colour conversion -- checkable against arithmetic, so it is
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rgb", [
    (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
    (0.5, 0.25, 0.75), (0.2, 0.2, 0.2), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0),
])
def test_rgb_to_hsv_and_back_is_the_identity(rgb):
    h, s, v = emtk.color_convert_rgb_to_hsv(*rgb)
    back = emtk.color_convert_hsv_to_rgb(h, s, v)
    assert all(abs(a - b) < 1e-6 for a, b in zip(rgb, back)), (rgb, back)


def test_hue_lands_where_it_should():
    """Red at 0, green at a third, blue at two thirds."""
    assert emtk.color_convert_rgb_to_hsv(1.0, 0.0, 0.0)[0] == pytest.approx(0.0)
    assert emtk.color_convert_rgb_to_hsv(0.0, 1.0, 0.0)[0] == pytest.approx(1 / 3, abs=1e-6)
    assert emtk.color_convert_rgb_to_hsv(0.0, 0.0, 1.0)[0] == pytest.approx(2 / 3, abs=1e-6)


def test_u32_and_float4_round_trip():
    assert emtk.color_convert_float4_to_u32((1.0, 0.5, 0.0, 1.0)) == (255, 128, 0, 255)
    assert emtk.color_convert_u32_to_float4((255, 0, 0, 255)) == (1.0, 0.0, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# The N-component variants really edit N components
# --------------------------------------------------------------------------- #
def test_a_three_component_drag_returns_three(ctx):
    changed, out = emtk.drag_float3("xyz", (1.0, 2.0, 3.0))
    assert len(out) == 3 and not changed
    assert out == pytest.approx((1.0, 2.0, 3.0))


def test_each_component_gets_its_own_box(ctx):
    """Or they share an id, and only the first would ever be usable."""
    ids = []
    ctx.push_id("xyz")
    for index in range(3):
        ids.append(ctx.get_id(f"##{index}"))
    ctx.pop_id()
    assert len(set(ids)) == 3


def test_a_range_drag_keeps_its_ends_in_order(ctx):
    changed, low, high = emtk.drag_float_range2("range", 8.0, 2.0)
    assert low <= high


def test_the_scalar_forms_dispatch_on_the_value(ctx):
    _c, as_int = emtk.slider_scalar("i", 3, 0, 10)
    _c, as_float = emtk.slider_scalar("f", 0.5, 0.0, 1.0)
    assert isinstance(as_int, int) and isinstance(as_float, float)


def test_the_scalar_forms_also_take_the_references_leading_data_type(ctx):
    """``SliderScalar(label, data_type, p_data, p_min, p_max, fmt, flags)``.

    The reference passes an ``ImGuiDataType`` *second* and emtk infers the
    type from the value instead -- which is the right instinct in Python and
    the wrong signature, because a port hands its arguments over
    positionally. Without this the data type landed in the value slot and
    the value in the minimum: `TypeError: slider_scalar() takes from 4 to 5
    positional arguments but 7 were given` on a good day, and a silently
    wrong range on a bad one.
    """
    _c, v = emtk.slider_scalar("##a", emtk.im.DataType.DOUBLE, 0.5, 0.0, 1.0,
                               "%.5f", emtk.im.SliderFlags.LOGARITHMIC)
    assert v == pytest.approx(0.5)

    _c, d = emtk.drag_scalar("##d", emtk.im.DataType.FLOAT, 1.5, 0.1, 0.0, 10.0)
    assert d == pytest.approx(1.5)

    _c, i = emtk.input_scalar("##i", emtk.im.DataType.S32, 4, 1, 10)
    assert i == 4


def test_a_typed_scalar_keeps_the_value_out_of_the_bounds(ctx):
    """The bug this guards is the quiet one: with the arguments shifted by
    one, the value was read as a bound and the slider clamped to nonsense
    instead of raising."""
    # 5.0 with bounds 0..10 is mid-range, and stays there.
    _c, mid = emtk.slider_scalar("##m", emtk.im.DataType.DOUBLE, 5.0, 0.0, 10.0)
    assert mid == pytest.approx(5.0)
    # The same numbers untyped must agree -- one signature, two spellings.
    _c, same = emtk.slider_scalar("##n", 5.0, 0.0, 10.0)
    assert same == pytest.approx(mid)


def test_the_untyped_scalar_spelling_still_takes_keywords(ctx):
    """`slider_scalar_n` and emtk's own callers pass these by name."""
    _c, v = emtk.slider_scalar("##k", 0.25, v_min=0.0, v_max=1.0)
    assert v == pytest.approx(0.25)


def test_a_vertical_slider_reads_top_to_bottom(ctx):
    """Down is *less*: the reference's VSlider grows upward."""
    ctx.io.mouse_pos = (5.0, 5.0)
    ctx.io.mouse_down[0] = True
    ctx.io.mouse_clicked[0] = True
    changed, high = emtk.v_slider_float("##v", (20.0, 100.0), 0.5, 0.0, 1.0)
    assert high > 0.5, "grabbing near the top should raise the value"


# --------------------------------------------------------------------------- #
# Scroll, cursor, windows
# --------------------------------------------------------------------------- #
def test_scroll_is_remembered_on_the_window(ctx):
    ctx.begin("w", (0.0, 0.0, 100.0, 100.0))
    emtk.set_scroll_y(17.0)
    assert emtk.get_scroll_y() == 17.0
    ctx.end()


def test_scroll_max_follows_the_content(ctx):
    ctx.begin("w", (0.0, 0.0, 100.0, 100.0))
    ctx.current_window.content_size = (100.0, 260.0)
    assert emtk.get_scroll_max_y() == 160.0
    emtk.set_scroll_here_y(1.0)
    assert emtk.get_scroll_y() == 160.0
    ctx.end()


def test_a_window_can_be_moved_and_resized(ctx):
    ctx.begin("w", (0.0, 0.0, 100.0, 100.0))
    emtk.set_window_pos((10.0, 20.0))
    emtk.set_window_size((30.0, 40.0))
    assert emtk.get_window_pos() == (10.0, 20.0)
    assert emtk.get_window_size() == (30.0, 40.0)
    ctx.end()


def test_the_cursor_can_be_placed(ctx):
    emtk.set_cursor_pos_y(50.0)
    assert emtk.get_cursor_pos_y() == pytest.approx(50.0)


# --------------------------------------------------------------------------- #
# Plots draw the data they were given
# --------------------------------------------------------------------------- #
def test_a_line_plot_draws_a_polyline_over_the_values(ctx):
    before = len(ctx.painter.calls)
    emtk.plot_lines("##p", [0.0, 1.0, 0.0, 1.0], size=(100.0, 40.0))
    assert len(ctx.painter.calls) > before


def test_a_histogram_draws_one_bar_per_value(ctx):
    before = sum(1 for c in ctx.painter.calls if c[0] == "fill_rect")
    emtk.plot_histogram("##h", [1.0, 2.0, 3.0, 4.0, 5.0], size=(100.0, 40.0))
    after = sum(1 for c in ctx.painter.calls if c[0] == "fill_rect")
    assert after - before >= 6, "five bars and a frame"


# --------------------------------------------------------------------------- #
# The style
# --------------------------------------------------------------------------- #
def test_a_style_var_pushes_and_pops(ctx):
    before = ctx.style.frame_rounding
    emtk.push_style_var("frame_rounding", 7.0)
    assert ctx.style.frame_rounding == 7.0
    emtk.pop_style_var()
    assert ctx.style.frame_rounding == before


def test_the_light_theme_is_not_the_dark_one(ctx):
    dark = ctx.style.color(emtk.Col.WINDOW_BG)
    emtk.style_colors_light()
    light = ctx.style.color(emtk.Col.WINDOW_BG)
    assert light != dark
    emtk.style_colors_dark()
    assert ctx.style.color(emtk.Col.WINDOW_BG) == dark


def test_a_colour_has_a_name(ctx):
    assert "Button" in emtk.get_style_color_name(emtk.Col.BUTTON)


# --------------------------------------------------------------------------- #
# ImDrawList
# --------------------------------------------------------------------------- #
def test_an_ellipse_is_drawn_as_an_ellipse():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    dl.add_ellipse_filled((50.0, 50.0), (40.0, 10.0), (255, 0, 0, 255))
    xs = [pt[0] for call in painter.calls if call[0] == "fill_triangle"
          for pt in call[1:4]]
    ys = [pt[1] for call in painter.calls if call[0] == "fill_triangle"
          for pt in call[1:4]]
    assert max(xs) - min(xs) == pytest.approx(80.0, abs=2.0)
    assert max(ys) - min(ys) == pytest.approx(20.0, abs=2.0)


def test_a_concave_polygon_is_filled_without_spilling():
    """An arrowhead: the notch must not be filled in.

    A triangle fan from the centroid -- the easy wrong answer -- covers the
    notch, so the test is that the triangles stay inside the shape.
    """
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    arrow = [(0.0, 0.0), (100.0, 50.0), (0.0, 100.0), (30.0, 50.0)]
    dl.add_concave_poly_filled(arrow, (255, 255, 255, 255))
    triangles = [c for c in painter.calls if c[0] == "fill_triangle"]
    assert len(triangles) == 2, f"an ear-clipped quad is two triangles: {len(triangles)}"
    for call in triangles:
        centre = tuple(sum(pt[i] for pt in call[1:4]) / 3.0 for i in (0, 1))
        assert _inside(arrow, centre), f"a triangle spilled into the notch: {centre}"


def test_the_fast_arc_uses_twelfths_of_a_turn():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    dl.path_arc_to_fast((0.0, 0.0), 10.0, 0, 3)      # a quarter turn
    assert dl._path, "no points were produced"
    first, last = dl._path[0], dl._path[-1]
    assert first[0] == pytest.approx(10.0, abs=0.01)
    assert last[1] == pytest.approx(10.0, abs=0.01)


def test_the_axis_aligned_lines_are_one_rectangle_each():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    dl.add_line_h((0.0, 10.0), 50.0, (1, 2, 3, 255), 2.0)
    dl.add_line_v((0.0, 10.0), 50.0, (1, 2, 3, 255), 2.0)
    fills = [c for c in painter.calls if c[0] == "fill_rect"]
    assert len(fills) == 2
    assert fills[0][3] == 50.0 and fills[1][4] == 50.0


def _inside(polygon, point) -> bool:
    """Ray casting, for the concave test."""
    x, y = point
    inside = False
    for i in range(len(polygon)):
        x0, y0 = polygon[i - 1]
        x1, y1 = polygon[i]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
                inside = not inside
    return inside


# --------------------------------------------------------------------------- #
# The last of the surface: images, fonts, the platform, dnd, settings, logs
# --------------------------------------------------------------------------- #
def test_an_image_reaches_a_painter_that_can_blit():
    """A painter with `image` gets the call; one without gets a tinted box."""
    class Blitting(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.images = []

        def image(self, x, y, w, h, handle, uv0, uv1, tint):
            self.images.append((handle, x, y, w, h))

    painter = Blitting()
    with emtk.frame(painter, (0.0, 0.0, 200.0, 200.0)):
        emtk.image("texture-7", (64.0, 48.0))
    assert painter.images and painter.images[0][0] == "texture-7"
    assert painter.images[0][3:] == (64.0, 48.0)


def test_an_image_on_a_painter_without_one_still_occupies_its_box():
    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 200.0, 200.0)):
        emtk.image("texture", (64.0, 48.0), tint=(10, 20, 30, 255))
    box = [c for c in painter.calls if c[0] == "fill_rect" and c[5] == (10, 20, 30, 255)]
    assert box and (box[0][3], box[0][4]) == (64.0, 48.0)


def test_a_font_is_offered_to_the_painter():
    class Fonted(RecordingPainter):
        def __init__(self):
            super().__init__()
            self.fonts = []

        def set_font(self, font):
            self.fonts.append(font)

    painter = Fonted()
    with emtk.frame(painter, (0.0, 0.0, 200.0, 200.0)):
        emtk.push_font("big")
        assert emtk.get_font() == "big"
        emtk.pop_font()
        assert emtk.get_font() is None
    assert painter.fonts == ["big", None]


def test_the_viewport_is_the_box_the_context_was_given(ctx):
    viewport = emtk.get_main_viewport()
    assert viewport.pos == (0.0, 0.0)
    assert viewport.size == (400.0, 400.0)
    assert viewport.get_center() == (200.0, 200.0)


def test_the_clipboard_round_trips(ctx):
    emtk.set_clipboard_text("copied")
    assert emtk.get_clipboard_text() == "copied"


def test_a_payload_crosses_from_source_to_target():
    """Press on the source, drag, release on the target."""
    io, storage = emtk.IO(), {}

    def frame():
        painter = RecordingPainter()
        with emtk.frame(painter, (0.0, 0.0, 200.0, 200.0), io=io, storage=storage):
            emtk.button("source")
            if emtk.begin_drag_drop_source():
                emtk.set_drag_drop_payload("ATOM", {"serial": 42})
                emtk.end_drag_drop_source()
            source_box = emtk.get_item_rect()
            emtk.button("target")
            got = None
            if emtk.begin_drag_drop_target():
                got = emtk.accept_drag_drop_payload("ATOM")
                emtk.end_drag_drop_target()
            target_box = emtk.get_item_rect()
        return source_box, target_box, got

    source, target, _ = frame()
    io.mouse_pos = (source[0] + 2, source[1] + 2)          # press the source
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    frame()
    io.mouse_clicked[0] = False
    io.mouse_pos = (source[0] + 40, source[1] + 40)        # drag it
    frame()
    io.mouse_pos = (target[0] + 2, target[1] + 2)          # over the target
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    _s, _t, got = frame()
    assert got == {"serial": 42}


def test_the_windows_places_survive_a_round_trip_through_ini():
    io, storage = emtk.IO(), {}
    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 400.0, 400.0), io=io, storage=storage) as ctx:
        ctx.begin("left", (10.0, 20.0, 100.0, 50.0))
        ctx.end()
        ctx.begin("right", (200.0, 30.0, 120.0, 60.0))
        ctx.end()
        ini = emtk.save_ini_settings_to_memory()
    assert "[Window][left]" in ini and "Pos=10,20" in ini

    painter = RecordingPainter()
    with emtk.frame(painter, (0.0, 0.0, 400.0, 400.0)) as fresh:
        emtk.load_ini_settings_from_memory(ini)
        placed = {w.name: w.box for w in fresh.windows}
    assert placed["left"] == (10.0, 20.0, 100.0, 50.0)
    assert placed["right"] == (200.0, 30.0, 120.0, 60.0)


def test_the_log_collects_and_flushes(ctx):
    emtk.log_to_clipboard()
    emtk.log_text("one ")
    emtk.log_text("two")
    emtk.log_finish()
    assert emtk.get_clipboard_text() == "one two"


def test_a_log_that_was_never_opened_swallows_nothing(ctx):
    emtk.log_text("dropped")
    assert "dropped" not in emtk.get_clipboard_text()


def test_the_built_in_windows_draw(ctx):
    """`ShowDemoWindow` and friends are real, so they must survive being run."""
    for show in (emtk.show_demo_window, emtk.show_about_window, emtk.show_user_guide,
                 emtk.show_metrics_window, emtk.show_style_editor,
                 emtk.show_id_stack_tool_window, emtk.show_debug_log_window):
        before = len(ctx.painter.calls)
        show()
        assert len(ctx.painter.calls) > before, show.__name__


def test_the_channel_splitter_reorders_drawing():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    dl.channels_split(2)
    dl.channels_set_current(1)
    dl.add_rect_filled((0, 0), (10, 10), (255, 0, 0, 255))     # drawn second
    dl.channels_set_current(0)
    dl.add_rect_filled((0, 0), (20, 20), (0, 255, 0, 255))     # drawn first
    dl.channels_merge()
    order = [c[5] for c in painter.calls if c[0] == "fill_rect"]
    assert order == [(0, 255, 0, 255), (255, 0, 0, 255)]


def test_hand_written_vertices_become_triangles():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    dl.prim_reserve(3, 3)
    for point in ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0)):
        dl.prim_vtx(point, (0.0, 0.0), (1, 2, 3, 255))
    triangles = [c for c in painter.calls if c[0] == "fill_triangle"]
    assert len(triangles) == 1
    assert triangles[0][1:4] == ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0))


def test_a_draw_callback_runs_in_order():
    painter = RecordingPainter()
    dl = emtk.DrawList(painter)
    seen = []
    dl.add_rect_filled((0, 0), (1, 1), (0, 0, 0, 255))
    dl.add_callback(lambda _dl, data: seen.append(data), "payload")
    assert seen == ["payload"]


def test_the_function_keys_and_space_have_codes():
    """`None` is not "unbound", it is *wrong*: `io.key == Key.SPACE` is then
    false for every key including space, so a shortcut bound to one silently
    never fires. cmc toggles its acquisition on F2 and had no F2 to test."""
    import emtk.keys as keys

    assert emtk.im.Key.SPACE == keys.KEY_SPACE
    assert emtk.im.Key.INSERT == keys.KEY_INSERT
    codes = [getattr(emtk.im.Key, f"F{n}") for n in range(1, 13)]
    assert all(isinstance(c, int) for c in codes)
    # contiguous, in order, as Qt numbers them -- an off-by-one here binds
    # every shortcut to its neighbour
    assert codes == list(range(codes[0], codes[0] + 12))


def test_a_function_key_press_is_seen(ctx):
    ctx.io.key = emtk.im.Key.F2
    assert emtk.im.is_key_pressed(emtk.im.Key.F2)
    assert not emtk.im.is_key_pressed(emtk.im.Key.F3)
