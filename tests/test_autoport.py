"""tests for tools/autoport.py -- the mechanical C++ -> cmtk porter.

Two layers:

* **Rules** -- small C++ statements and the exact Python a mechanical port
  must produce. These pin the tables down one line at a time.
* **Whole extensions** -- the Useful-Extensions fixtures port to modules that
  import, and the ones whose rules cover them render, with the screenshots
  compared against the committed goldens.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import autoport  # noqa: E402

from cmtk.testing import (  # noqa: E402
    PixelPainter, assert_images_equal, png_decode, png_encode, render,
)

FIXTURES = ROOT / "tests" / "fixtures" / "extensions"
PORTED = ROOT / "tests" / "fixtures" / "ported"
GOLDEN = ROOT / "tests" / "golden"

#: fixture -> sources: one or more C++ files that port into one module.
#: A single-file fixture is a one-tuple.
CASES = {
    "imgui_knobs": ("imgui_knobs.h", "imgui_knobs.cpp"),
    "imgui_toggle": ("imgui_toggle.h", "imgui_toggle.cpp"),
    "imgui_notify": (None, "imgui_notify.h"),
    "imgui_memory_editor": (None, "imgui_memory_editor.h"),
    # the second batch: a new category each, from the same wiki page
    "im_gradient": ("ImGradient.h", "ImGradient.cpp"),          # gradients
    "im_curve_edit": ("ImCurveEdit.h", "ImCurveEdit.cpp"),      # curves
    "imgui_markdown": (None, "imgui_markdown.h"),               # markdown
    "l2d_file_dialog": (None, "L2DFileDialog.h"),               # file dialog
    "imgui_hex": ("imgui_hex.h", "imgui_hex.cpp"),              # hex editor
    "arc_progress_bar": ("arc_progress_bar.hpp", "arc_progress_bar.cpp"),
    # the third batch: the wiki page's heavier internal-tooling side
    "im_sequencer": ("ImSequencer.h", "ImSequencer.cpp"),       # sequencer
    "im_zoom_slider": ("ImZoomSlider.h",),                      # zoom slider
    "graph_editor": ("GraphEditor.h", "GraphEditor.cpp"),       # graph editor
    "imnodes": ("imnodes.h", "imnodes.cpp"),                    # node editor
    "text_editor": ("TextEditor.h", "TextEditor.cpp"),          # text editor
    "imspinner": ("imspinner.h",),                              # spinner: macros
}


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def _stmt(cpp: str, out_name: str | None = None) -> list[str]:
    porter = autoport.Porter()
    porter.out_src_name = out_name
    lines = autoport.StatementPorter(porter).port([cpp])
    return [l.strip() for l in lines if l.strip()]


def _tmp_cpp(text: str) -> pathlib.Path:
    """A C++ source on disk: port_file() reads files, not strings."""
    import tempfile
    fh = tempfile.NamedTemporaryFile("w", suffix=".cpp", delete=False)
    fh.write(text)
    fh.close()
    return pathlib.Path(fh.name)

def test_the_naming_rule_is_shared_with_cmtk():
    assert autoport.mechanical_name("SliderFloat") == "slider_float"
    assert autoport.mechanical_name("BeginPopupModal") == "begin_popup_modal"


def test_a_button_call_changes_only_the_prefix():
    assert _stmt('ImGui::Button("Save");') == ['im.button("Save")']


def test_an_out_param_becomes_a_returned_tuple():
    assert _stmt("ImGui::SliderFloat(\"a\", &f, 0.0f, 1.0f);") == [
        '_changed, f = im.slider_float("a", f, 0.0, 1.0)']


def test_an_enum_constant_becomes_a_namespace_member():
    assert autoport.Porter().expr("ImGuiCol_Button") == "im.Col.BUTTON"


def test_imvec2_becomes_a_tuple_and_members_become_indexes():
    pr = autoport.Porter()
    assert pr.expr("ImVec2(x, y)") == "(x, y)"
    assert pr.expr("v.x + v.y") == "v[0] + v[1]"


def test_a_float_literal_loses_its_f_suffix():
    out = autoport.Porter().expr("0.5f")
    assert "0.5" in out and "0.5f" not in out


def test_printf_arguments_become_percent_formatting():
    assert _stmt('ImGui::Text("%d items", n);') == ['im.text("%d items" % n)']
    assert _stmt('ImGui::Text("%d/%d", a, b);') == ['im.text("%d/%d" % (a, b))']


def test_the_unsigned_format_spec_still_formats():
    assert autoport._fix_printf("%02u") == "%02d"
    assert autoport._fix_printf("%lld") == "%d"
    assert autoport._fix_printf("%5d") == "%5d"


def test_a_c_cast_binds_to_one_token():
    porter = autoport.Porter()
    assert porter.expr("(float) x / 2.0f") == "float(x) / 2.0"


def test_a_ternary_becomes_a_conditional_expression():
    porter = autoport.Porter()
    assert porter.expr("a ? b : c") == "(b if a else c)"
    nested = porter.expr("w ? x : (y ? z : q)")
    assert "x if w" in nested and "z if y" in nested


def test_an_address_of_argument_passes_the_value():
    porter = autoport.Porter()
    assert "&" not in porter.expr("foo(&x, 1)")


def test_pointer_reads_and_writes_become_the_value():
    porter = autoport.Porter()
    porter.out_src_name = "p_value"
    assert porter.expr("*p_value + 1.0") == "value + 1.0"


def test_bool_and_nullptr_literals_translate():
    porter = autoport.Porter()
    e = porter.expr("f = true && !g || false")
    assert "True" in e and "False" in e and "and" in e and "or" in e
    assert "!" not in e


def test_a_for_loop_becomes_a_range():
    lines = _stmt("for (int i = 0; i < n; i++) { x(i); }".replace("{ x(i); }", "{ draw(i); }"))
    assert any(l.startswith("for i in range(int(0), int(n))") for l in lines)


def test_a_range_for_becomes_a_python_for():
    porter = autoport.Porter()
    lines = autoport.StatementPorter(porter).port(
        ["for (auto& w : windows) { touch(w); }"])
    assert any(l.strip().startswith("for w in windows") for l in lines)


def test_declared_locals_lose_their_types():
    lines = _stmt("float f = 0.5f;")
    assert lines == ["f = 0.5"]


def test_imgui_io_fields_are_snake_cased():
    porter = autoport.Porter()
    assert porter.expr("io.MousePos.x") == "io.mouse_pos[0]"
    assert porter.expr("io.DeltaTime") == "io.mouse_delta_time".replace(
        "mouse_delta_time", "delta_time")


def test_knob_drag_behaviour_maps_to_the_scalar_widget():
    porter = autoport.Porter()
    out = porter._rewrite_call("ImGui::DragBehavior",
                               ["gid", "ImGuiDataType_Float", "p_value",
                                "speed", "v_min", "v_max", "format"])
    assert out.startswith("_changed, p_value = im.drag_scalar(")


# --------------------------------------------------------------------------- #
# Rules the second fixture batch forced out
# --------------------------------------------------------------------------- #
def test_a_ternary_hiding_in_parentheses_is_found():
    assert _stmt("return x + (c ? a : b);") == ["return x + ((a if c else b))"]


def test_a_ternary_inside_a_char_literal_is_opaque():
    out = _stmt("return half_byte <= 9 ? '0' + half_byte : (lower ? 'a' : 'A') + half_byte - 10;")
    assert any("'a' if lower else 'A'" in l for l in out), out
    assert not any("?" in l for l in out)


def test_out_params_with_the_extension_spelling_return_tuples():
    """*Every* write-through parameter rides the tuple, in declaration order.

    ``RangeRangeIntersection(a_min, a_max, b_min, b_max, int* out_min,
    int* out_max)`` writes through two, and carrying only the first was not
    just lossy: the definition returned ``out_min`` while the call site
    assigned it to ``out_max``, so a value landed in the wrong variable and
    nothing said so until it was used somewhere else entirely.
    """
    header = FIXTURES / "imgui_hex.h"
    impl = FIXTURES / "imgui_hex.cpp"
    out = autoport.port_file([header, impl], "m", "o")

    assert "def range_range_intersection(a_min, a_max, b_min, b_max, out_min, out_max):" in out
    # every exit carries them, including the early one and the fall-through
    assert "return False, out_min, out_max" in out
    assert "return True, out_min, out_max" in out
    assert "second out-parameter(s)" not in out

    # and the call site unpacks both, into the variables C++ took addresses of
    assert ("_ret, abs_min, abs_max = range_range_intersection("
            "row_offset, row_offset + row_bytes_count, range_min, range_max, "
            "abs_min, abs_max)") in out


def test_a_user_out_value_call_inside_an_if_is_hoisted():
    """``if (Intersect(a, b, &lo, &hi))`` cannot stay an ``if``: the call now
    returns a *tuple*, and a tuple is always true -- so the branch was taken
    every time. It runs, it draws, and it is wrong, which is the worst kind."""
    out = autoport.port_file([FIXTURES / "imgui_hex.h", FIXTURES / "imgui_hex.cpp"],
                             "m", "o")
    lines = [l.strip() for l in out.splitlines()]
    at = next(i for i, l in enumerate(lines)
              if l.startswith("_ret, abs_min, abs_max = range_range_intersection("))
    assert lines[at + 1] == "if _ret:", lines[at:at + 2]


def test_an_imvec2_typed_reference_param_rides_the_tuple():
    header = FIXTURES / "arc_progress_bar.hpp"
    impl = FIXTURES / "arc_progress_bar.cpp"
    out = autoport.port_file([header, impl], "arc_progress_bar", "o")
    assert "assert(" in out                      # IM_ASSERT -> assert
    assert "im.dummy(size, size)" in out         # ImVec2 argument splatted
    assert "ImColor" not in out                  # colours are tuples here


def test_destructor_and_operator_overloads_are_dropped_visibly():
    out = autoport.port_file([FIXTURES / "imgui_markdown.h"], "md", "o")
    assert "destructor ~TextRegion() dropped" in out
    assert "def ~" not in out


def test_a_named_enum_becomes_an_intflag_with_snake_members():
    out = autoport.port_file([FIXTURES / "L2DFileDialog.h"], "l2d", "o")
    assert "class FileDialogType(IntFlag):" in out
    assert "open_file = 0" in out
    assert "select_folder = 1" in out


def test_pointer_and_size_t_casts_vanish():
    porter = autoport.Porter()
    assert porter.expr("(char*)im.mem_alloc((size_t)n)") == "im.mem_alloc(int(n))"


def test_a_two_component_literal_add_is_component_wise():
    porter = autoport.Porter()
    assert porter.expr("pos + (3, 3)") == "(pos[0] + 3, pos[1] + 3)"
    # component order follows the variable, not the literal's position
    assert porter.expr("(3, 3) + pos") == "(pos[0] + 3, pos[1] + 3)"

def test_begin_child_takes_a_box_anchored_at_the_cursor():
    out = _stmt("ImGui::BeginChild(\"id\", size, false);")
    assert out == ["im.begin_child((*im.get_cursor_screen_pos(), size[0], size[1]))"]


def test_multi_declarator_lines_keep_every_name():
    out = _stmt("float a_min_factor, a_max_factor, a_max_factor_100percentage;")
    assert out == ["a_min_factor = 0.0", "a_max_factor = 0.0",
                   "a_max_factor_100percentage = 0.0"]


# --------------------------------------------------------------------------- #
# Rules, third batch: macros, casts, C++11 initialisation, C++ defaults
# --------------------------------------------------------------------------- #
def test_a_function_like_macro_invocation_is_flagged_not_expanded():
    """Macro expansion is the hand's job; the porter leaves a visible debt."""
    porter = autoport.Porter()
    porter.macros = {"SPINNER_HEADER"}
    joined = "\n".join(autoport.StatementPorter(porter).port(
        ["SPINNER_HEADER(pos, size, centre, num_segments);"]))
    assert "invocation dropped -- expand by hand" in joined
    assert "spinner_header(" not in joined   # never a fake renamed call


def test_a_cast_on_a_qualified_call_is_a_noop():
    """``(float)ImGui::GetTime()`` -- binding float() around it would tear
    the receiver apart; a numeric cast on an already-numeric value is a
    no-op. A named-type cast (``(ease_mode)mode``) is one too."""
    assert autoport.Porter().expr("(float)ImGui::GetTime()") == "im.get_time()"
    assert autoport.Porter().expr("(ease_mode)mode") == "mode"


def test_cxx11_brace_initialisation_is_a_ctor_call():
    assert _stmt("ImColor white{1.f, 1.f, 1.f, 1.f};") == \
        ["white = (1., 1., 1., 1.)"]
    assert _stmt("const ImVec2 p(centre[0] + 1.0, centre[1]);") == \
        ["p = (centre[0] + 1.0, centre[1])"]


def test_cxx_default_constructed_things_get_their_python_default():
    """C++ default-constructs these; so does the port."""
    assert _stmt("ImVec2 p;") == ["p = (0.0, 0.0)"]
    assert _stmt("std::string s;")[0].startswith('s = ""')


def test_a_static_local_declares_its_semantics_debt():
    porter = autoport.Porter()
    lines = autoport.StatementPorter(porter).port(["static int counter = 0;"])
    assert lines == ["    counter = 0"]
    assert any("across calls" in t for t in porter.todos)


def test_a_typed_loop_variable_is_untyped():
    porter = autoport.Porter()
    got = autoport.StatementPorter(porter)._for(
        "SlotIndex slotIndex = 0; slotIndex < slotCount; ++slotIndex")
    assert got == "for slotIndex in range(int(0), int(slotCount))"


# --------------------------------------------------------------------------- #
# Whole extensions
# --------------------------------------------------------------------------- #
def _load(module: str):
    spec = importlib.util.spec_from_file_location(module, PORTED / f"{module}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_ported_extension_imports_and_flags_what_a_hand_owes(name):
    """The output always imports; the hand's debts are explicit, counted."""
    mod = _load(name)
    text = (PORTED / f"{name}.py").read_text()
    assert "import cmtk.im as im" in text
    # the hand-pass debts are visible, never silent
    real = sum(1 for l in text.splitlines()
               if "TODO(autoport):" in l and "need a hand" not in l)
    assert real >= 0


def test_the_macro_boundary_now_ports_with_every_invocation_flagged():
    """imspinner.h *was* the documented boundary: function-like macros. The
    porter strips the definitions and flags every invocation as the hand's
    debt -- 60+ real spinner functions port beside them."""
    out = autoport.port_file([FIXTURES / "imspinner.h"], "imspinner", "o")
    assert out.count("invocation dropped -- expand by hand") >= 60
    assert "#define SPINNER_HEADER" not in out
    assert "IM_PI = math.pi" in out   # the imgui_internal constant is carried
    assert "white = (1." in out       # the brace-initialised constants, too


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_porter_is_deterministic(name):
    """Same C++ in, same Python out -- a port that drifts is not a port."""
    sources = [FIXTURES / f for f in CASES[name] if f]
    first = autoport.port_file(sources, "m", "o")
    again = autoport.port_file(sources, "m", "o")
    assert first == again


# --------------------------------------------------------------------------- #
# Screenshots: the ported extensions, rendered and compared to goldens
# --------------------------------------------------------------------------- #
def _gui_knobs(im, mod):
    def gui():
        im.begin("Knobs")
        mod.knob("vol", 0.7, 0.0, 1.0, 0.0, "%.2f", mod.KnobVariant.TICK,
                 60.0, mod.KnobFlags.NONE, 0, -1.0, 1.0)
        im.same_line()
        mod.knob("temp", 0.3, 0.0, 1.0, 0.0, "%.2f", mod.KnobVariant.WIPER_ONLY,
                 60.0, mod.KnobFlags.NONE, 0, -1.0, 1.0)
        im.end()
    return gui


def _gui_toggle(im, mod):
    def gui():
        im.begin("Toggles")
        mod.toggle("one", True, (40, 20))
        mod.toggle("two", False, (40, 20))
        im.end()
    return gui


def _gui_notify(im, mod):
    def gui():
        im.begin("Notifications")
        mod.render_notifications()
        im.end()
    return gui


def test_the_autoported_knob_draws_the_same_picture_every_time():
    mod = _load("imgui_knobs")
    painter = render(_gui_knobs(__import__("cmtk.im", fromlist=["im"]), mod),
                     (0, 0, 340, 140))
    png = png_encode(painter.width, painter.height, painter.px)
    golden = GOLDEN / "imgui_knobs.png"
    if not golden.exists():          # first run bakes the golden
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(png)
    assert_images_equal(png, golden)


def test_the_autoported_arc_progress_bar_draws_the_same_picture_every_time():
    """The cleanest port of the second batch: pure drawlist paths, straight
    from arc_progress_bar.cpp to pixels, byte-identical every run."""
    mod = _load("arc_progress_bar")

    def gui():
        mod.progress_bar_arc(64.0, 360.0, 75.0, 6.0)

    painter = render(gui, (0, 0, 100, 100))
    png = png_encode(painter.width, painter.height, painter.px)
    golden = GOLDEN / "arc_progress_bar.png"
    if not golden.exists():
        golden.write_bytes(png)
    assert_images_equal(png, golden)
    # the arc is really there, not a silently-empty picture
    w, h, px = png_decode(png)
    lit = sum(1 for i in range(0, len(px), 4) if px[i:i + 4] != b"\x00\x00\x00\xff")
    assert lit > 500, f"arc barely drew ({lit} lit pixels)"


def test_the_autoported_knob_reports_the_value_it_was_given():
    mod = _load("imgui_knobs")
    import cmtk.im as im
    from cmtk.testing import PixelPainter
    import cmtk as cmtk_pkg
    seen = {}

    def gui():
        im.begin("Knobs")
        changed, value = mod.knob("vol", 0.7, 0.0, 1.0, 0.0, "%.2f",
                                  mod.KnobVariant.TICK, 60.0,
                                  mod.KnobFlags.NONE, 0, -1.0, 1.0)
        seen["changed"] = changed
        seen["value"] = value
        im.end()

    painter = PixelPainter(340, 140)
    with cmtk_pkg.im.frame(painter, (0, 0, 340, 140)):
        gui()
    assert seen["changed"] is False
    assert seen["value"] == pytest.approx(0.7)


def test_the_autoported_toggle_and_notifier_expose_their_api():
    """Toggle and Notify port to importable modules with their public API
    present; their static-local renderers still need the documented hand
    pass, so their screenshots are not asserted yet."""
    toggle = _load("imgui_toggle")
    assert callable(toggle.toggle)
    assert callable(toggle.toggle_internal)
    notify = _load("imgui_notify")
    assert callable(notify.render_notifications)
    assert hasattr(notify.ImGuiToast, "set_content")


def test_the_second_batch_exposes_its_api():
    """The six new fixtures import with their entry points present -- the
    function the wiki page advertises is reachable under the naming rules."""
    gradient = _load("im_gradient")
    assert callable(gradient.edit)
    assert callable(gradient.draw_point)

    curve = _load("im_curve_edit")
    # the delegate-driven Edit() region resisted the mechanical port (it is
    # flagged, not faked); the delegate scaffold and math helpers survive
    assert hasattr(curve, "Delegate")
    assert callable(curve.smoothstep)
    assert callable(curve.distance)

    markdown = _load("imgui_markdown")
    # the top-level markdown() parser region resisted the port (flagged);
    # the region/enum scaffolding and per-line rendering survive
    assert hasattr(markdown, "MarkdownFormatFlags")
    assert hasattr(markdown, "TextRegion")
    assert callable(markdown.render_line)
    assert callable(markdown.is_char_inside_word)

    l2d = _load("l2d_file_dialog")
    assert callable(l2d.show_file_dialog_s) or callable(l2d.show_file_dialog)
    assert int(l2d.FileDialogType.open_file) == 0

    hexport = _load("imgui_hex")
    assert callable(hexport.calc_bytes_per_line)
    assert callable(hexport.range_range_intersection)
    assert callable(hexport.half_byte_to_printable)

    arc = _load("arc_progress_bar")
    assert callable(arc.progress_bar_arc)
    assert callable(arc._draw_arc)


def test_the_third_batch_exposes_its_api():
    """The six heavier wiki extensions import with their surviving entry
    points present; the internal-state regions are flagged, never faked."""
    seq = _load("im_sequencer")
    assert hasattr(seq, "SequenceInterface")
    assert callable(seq.sequencer_add_del_button)

    zoom = _load("im_zoom_slider")
    assert int(zoom.ZoomSliderFlags.NONE) == 0

    graph = _load("graph_editor")
    assert callable(graph.draw_grid)
    assert callable(graph.draw_node)
    assert callable(graph.edit_options)
    assert callable(graph.get_node_rect)

    imnodes = _load("imnodes")
    # begin_node_editor/begin_node use the internal editor context (flagged);
    # the symmetric ends and the context-free entry points survive
    assert callable(imnodes.end_node_editor)
    assert callable(imnodes.set_node_grid_space_pos)
    assert callable(imnodes.editor_context_create)

    editor = _load("text_editor")
    assert hasattr(editor, "TextEditor")
    assert hasattr(editor, "LanguageDefinition")

    sp = _load("imspinner")
    # the function-like macros are flagged, but the 60+ real spinner
    # functions port and the easing helpers survive
    assert sum(1 for n in dir(sp) if n.startswith("spinner_")) >= 60
    assert callable(sp.damped_spring)
    assert callable(sp.color_alpha)




# --------------------------------------------------------------------------- #
# Application code
#
# The fixtures above are Dear ImGui *extensions*: single-purpose widget files
# written against the ImGui headers and little else. An application's GUI is
# the same API embedded in ordinary C++ -- standard-library types, lambdas,
# its own structs -- and each construct below cost a whole panel before it was
# handled, because the repair loop cuts the enclosing function down to `pass`
# rather than emit a module that will not import.
# --------------------------------------------------------------------------- #
def test_a_comment_only_branch_does_not_eat_its_function():
    """``if (c) { /* nothing */ }`` is legal C++ and an IndentationError in
    Python; the empty body needs the ``pass`` C++ never asked for."""
    assert _stmt("if (done) { }") == ["if done:", "pass"]


def test_an_out_of_line_destructor_is_dropped_like_an_inline_one():
    """``X::~X()`` starts with ``X``, so a startswith("~") test misses it and
    emits ``def ~x():`` -- which takes the next function down with it."""
    out = autoport.port_file(
        [_tmp_cpp("class Plot { public: Plot(); ~Plot(); void draw(); };\n"
                  "Plot::Plot() {}\n"
                  "Plot::~Plot() { free(buf_); }\n"
                  "void Plot::draw() { ImGui::Text(\"hi\"); }\n")],
        "dtor", "o")
    assert "def ~" not in out
    assert "destructor" in out                    # dropped, and said so
    assert 'im.text("hi")' in out                 # the next function survived


def test_a_value_write_call_in_an_if_test_is_hoisted():
    """The commonest line in a settings panel. ``&v`` returns the value beside
    the flag, and Python has no assignment inside an ``if``."""
    assert _stmt('if (ImGui::Checkbox("On", &on)) { changed = true; }') == [
        '_changed, on = im.checkbox("On", on)',
        "if _changed:",
        "changed = True",
    ]


def test_a_lambda_bound_to_a_name_becomes_a_nested_def():
    """Ported as an expression the body leaks into the enclosing scope, and a
    stray ``return`` truncates the caller."""
    assert _stmt("auto half = [&](int n) -> int { return n / 2; };") == [
        "def half(n):", "return n / 2"]


def test_a_camel_case_lambda_is_defined_under_the_name_its_calls_use():
    """The def used to keep the C++ spelling while every call below it was
    spelled mechanically, so the def was never reached: ``NameError: name
    'param_control_safe' is not defined`` on the first draw of the panel."""
    assert _stmt("bool changed = false;"
                 "auto ParamControlSafe = [&](const char *label) {"
                 "  ImGui::PushID(label); };"
                 "ParamControlSafe(\"Fix Tau\");") == [
        "changed = False",
        "def param_control_safe(label):",
        "im.push_id(label)",
        'param_control_safe("Fix Tau")']
    # an already-lowercase name is left exactly as its calls leave it
    assert _stmt("auto do_it = [&]() { f(); }; do_it();") == [
        "def do_it():", "f()", "do_it()"]


def test_a_by_reference_lambda_declares_the_names_it_writes_nonlocal():
    """An assignment makes the name local to the def, so the enclosing
    variable was never written and reading it inside the def raised
    ``UnboundLocalError: cannot access local variable 'row_str'``."""
    assert _stmt('std::string row_str = "x";'
                 "auto append_val = [&](double val) {"
                 "  char buf[32];"
                 "  std::snprintf(buf, sizeof(buf), \"%g\", val);"
                 "  row_str += buf; };") == [
        'row_str = "x"',
        "def append_val(val):",
        "nonlocal row_str",
        "buf = [None] * (32)",
        'std.snprintf(buf, sizeof(buf), "%g", val)',
        "row_str = row_str + std.string(buf)"]


def test_a_name_the_lambda_declares_itself_is_not_nonlocal():
    """``nonlocal v`` on a variable the lambda *declares* would make the def
    write the enclosing ``v`` of the same name instead of its own."""
    out = _stmt("float v = 1.0f;"
                "auto f = [&](float x) { float v = x * 2.0f; use(v); };")
    assert "nonlocal v" not in out


def test_nonlocal_is_not_emitted_without_an_enclosing_binding():
    """A bare ``nonlocal`` for a name with no binding in an enclosing scope is
    itself a SyntaxError, which the repair loop answers by cutting the whole
    function -- worse than the bug it was meant to fix."""
    out = _stmt("auto f = [&]() { total = 1; };")
    assert "nonlocal total" not in out
    # ...and where it does emit one, the def it sits in still compiles
    porter = autoport.Porter()
    lines = autoport.StatementPorter(porter).port(
        ["int total = 0; auto f = [&]() { total = 1; };"])
    assert any(l.strip() == "nonlocal total" for l in lines)
    compile("def outer():\n" + "\n".join(lines), "<t>", "exec")


def test_only_by_reference_captures_become_nonlocal():
    """``[=]`` and ``[this]`` copy: writing through them changes nothing in
    the caller, so a ``nonlocal`` would give the port a behaviour the C++
    never had."""
    by_value = _stmt("int n = 0; auto f = [=]() { n = 1; };")
    assert "nonlocal n" not in by_value
    by_name = _stmt("int n = 0; int m = 0;"
                    "auto f = [&n, m]() { n = 1; m = 2; };")
    assert "nonlocal n" in by_name and "nonlocal n, m" not in by_name
    # `[&, x]` is by reference by default, with `x` the named exception
    mixed = _stmt("int n = 0; int x = 0; auto f = [&, x]() { n = 1; x = 2; };")
    assert "nonlocal n" in mixed and "nonlocal n, x" not in mixed


def test_a_parameter_of_the_lambda_is_never_nonlocal():
    """``nonlocal`` on a name that is also a parameter is a SyntaxError, and
    an out-value call rewritten to ``_changed, fix = ...`` binds parameters
    all the time."""
    out = _stmt("bool fix = false;"
                'auto f = [&](bool *fix) { ImGui::Checkbox("t", fix); };')
    assert "nonlocal fix" not in out


def test_a_structured_binding_is_tuple_unpacking():
    assert _stmt("auto [lo, hi] = range_of(x);") == ["lo, hi = range_of(x)"]


def test_a_cast_in_front_of_a_dereference_binds_to_the_value():
    """The cast's own ``)`` reads as a left operand, so the ``*`` was taken
    for a multiplication and ``(float)*val`` was left standing -- valid
    Python, which multiplies the *type* and raises ``TypeError: unsupported
    operand type(s) for *: 'type' and 'float'`` only when the panel draws."""
    p = autoport.Porter()
    assert p.expr("(float)*val") == "float(val)"
    assert p.expr("(int)*n") == "int(n)"
    assert p.expr("(uint8_t*)&data") == "data"
    # ...and a multiplication by something that is not a type still is one
    assert p.expr("(a) * b") == "(a) * b"
    assert p.expr("f(x) * y") == "f(x) * y"


def test_a_string_declared_from_a_char_buffer_is_converted():
    """``char buf[32]`` ports to 32 slots of which ``snprintf`` fills only the
    front, so an unconverted ``std::string s = buf;`` carried the trailing
    ``None``s to a text draw: ``TypeError: ord() expected string of length 1,
    but NoneType found``, a panel away from the declaration."""
    assert _stmt("char label[32]; std::string row = label;") == [
        "label = [None] * (32)", "row = std.string(label)"]
    # only a bare name: an expression initialiser is already a value
    assert _stmt('std::string row = a + b;') == ["row = a + b"]


def test_a_char_buffer_appended_to_a_string_is_converted():
    """``row += buf`` appends a C string in C++ and concatenates a padded
    list here -- either ``TypeError: can only concatenate str (not "list") to
    str``, or a silent success that carries the padding onward."""
    assert _stmt('std::string row = "a"; char buf[32]; row += buf;') == [
        'row = "a"', "buf = [None] * (32)",
        "row = row + std.string(buf)"]
    # the buffer passed as a buffer is left alone: converting it there would
    # throw the write away
    assert 'std.snprintf(buf, sizeof(buf)' in "\n".join(
        _stmt('char buf[32]; std::snprintf(buf, sizeof(buf), "%d", n);'))


def test_a_sized_vector_construction_makes_that_many_elements():
    """``std.vector(100)`` is a *one*-element vector holding 100, so the loop
    that fills it raised ``IndexError: list assignment index out of range`` on
    its first write."""
    assert _stmt("std::vector<float> xs(100);") == ["xs = std.vector([0.0] * (100))"]
    assert _stmt("std::vector<int> ns(8);") == ["ns = std.vector([0] * (8))"]
    # two arguments are unambiguous: a copy takes one
    assert _stmt("std::vector<double> bins(n, 0.0);") == [
        "bins = std.vector([0.0] * (n))"]
    # one *non-numeric* argument is a copy as readily as a count, and nothing
    # in the text settles it, so it is left as it was
    assert _stmt("std::vector<double> v(other);") == ["v = std.vector(other)"]
    assert _stmt("std::vector<double> v(a.begin(), a.end());") == [
        "v = std.vector(a.begin(), a.end())"]


def test_a_case_label_ends_a_statement():
    """Glued to the statement under it, ``case A:\\n idx = 0;`` arrived as one
    token and ``_switch`` matched the label and threw the body away -- an
    ``if`` with nothing under it, and the repair loop cut the function."""
    assert _stmt("switch (k) { case 1: idx = 0; break; case 2: idx = 1; break; }") == [
        "if k == 1:", "idx = 0", "elif k == 2:", "idx = 1"]


def test_labels_that_fall_through_share_one_branch():
    """C++ fallthrough is one Python branch, not two. Emitted as two, the
    first had no body at all and the port did not compile."""
    assert _stmt("switch (k) { case 1: case 2: a = 1; break; default: a = 9; break; }") == [
        "if k == 1 or k == 2:", "a = 1", "else:", "a = 9"]
    # `case X:` falling straight into `default:` is just the default
    assert _stmt("switch (k) { case 1: a = 1; break; case 2: default: a = 9; break; }") == [
        "if k == 1:", "a = 1", "else:", "a = 9"]
    # a switch that is nothing but a default still needs an `if` to hang on
    assert _stmt("switch (k) { default: a = 9; break; }") == ["if True:", "a = 9"]


def test_an_empty_method_body_ports_to_pass_not_a_cut():
    """A C++ body that is only a comment is common, and the ``pass`` used to
    be emitted two levels deep -- an ``IndentationError`` the repair loop
    could only answer by cutting the method, taking the window's render with
    it."""
    src = _tmp_cpp("class W { public: void update(); };\n"
                   "void W::update() {\n  // nothing to do\n}\n")
    out = autoport.port_file([src], "w", "test", embed_cpp="none")
    assert "resisted the mechanical port" not in out
    assert "    def update(self):" in out
    assert "        pass" in out


def test_a_declaration_of_a_type_the_table_never_heard_of():
    """CPP_TYPES can name the standard library, never the application's own
    types. Two identifier-shaped tokens before the ``=`` is a declaration."""
    assert _stmt("std::vector<double> old_q = config.q;") == ["old_q = config.q"]
    assert _stmt("uint64_t seen = 0;") == ["seen = 0"]
    assert _stmt("DeviceInfo info = probe(i);") == ["info = probe(i)"]
    # ...and a plain assignment is still a plain assignment
    assert _stmt("changed = true;") == ["changed = True"]


def test_a_declaration_in_a_while_test_becomes_a_guarded_break():
    assert _stmt("while (auto r = poll()) { use(r); }") == [
        "while True:", "r = poll()", "if not r:", "break", "use(r)"]


def test_a_dereference_is_dropped_but_a_multiplication_is_not():
    """The two are told apart by whether anything could be a *left operand*."""
    pr = autoport.Porter()
    assert pr.expr("*sample_rate_idx") == "sample_rate_idx"
    assert pr.expr("f(*res_opt)") == "f(res_opt)"
    assert pr.expr("a * b * c") == "a * b * c"
    assert pr.expr("v[3] * alpha * s.x") == "v[3] * alpha * s[0]"


def test_the_f_suffix_rule_stops_at_the_quote():
    """``%.2f`` is a format spec. Stripping its ``f`` is a syntax error the
    repair loop never sees -- it silently changes what the program prints."""
    pr = autoport.Porter()
    assert pr.expr('ImGui::Text("Total: %.2f k", total)') == \
        'im.text("Total: %.2f k" % total)'
    assert pr.expr('ImGui::Text("state: true/false")') == \
        'im.text("state: true/false")'


def test_an_exponent_literal_loses_its_suffix_too():
    """``-1e9f`` is not a Python literal at all."""
    assert autoport.Porter().expr("-1e9f") == "-1e9"


def test_a_compound_format_operand_keeps_its_parentheses():
    """``%`` binds no tighter than ``/``: ``"%.2f" % total / 1000`` formats
    first and divides after."""
    assert autoport.Porter().expr(
        'ImGui::Text("%.2f k", (float)total / 1000.0f)') == \
        'im.text("%.2f k" % (float(total) / 1000.0))'


def test_an_unbraced_else_keeps_its_body():
    """``else stmt;`` has no parentheses to end the header, so the statement
    rides on the same token -- and used to be dropped in silence, leaving an
    ``else:`` with nothing under it."""
    assert _stmt("if (a <= b) out.add(a, b); else out.add(b, a);") == [
        "if a <= b:", "out.add(a, b)", "else:", "out.add(b, a)"]


def test_a_hex_literal_loses_its_suffix():
    """``0xFFFFFFFFu`` is not matched by the decimal-suffix rule, and Python
    rejects the ``u``."""
    pr = autoport.Porter()
    assert pr.expr("0xFFFFFFFFu") == "0xFFFFFFFF"
    assert pr.expr("0xFFul") == "0xFF"


def test_a_non_type_template_argument_still_evaporates():
    """``std::array<uint64_t, 4>`` -- the ``4`` is a value, not a type, and
    the rule used to require every argument to be an identifier."""
    assert _stmt("std::array<uint64_t, 4> counts = backend_.counts();") == [
        "counts = backend_.counts()"]


def test_a_float_colour_becomes_the_bytes_cmtk_paints_in():
    """Dear ImGui spells a colour as four floats 0..1, cmtk's painters take
    bytes 0..255. The floats do not raise -- they draw (0, 0, 0), so the text
    is invisible, which is the worst kind of difference between the two."""
    pr = autoport.Porter()
    assert pr.expr('ImGui::TextColored(ImVec4(1.0f, 0.4f, 0.4f, 1.0f), "err")') == \
        'im.text_colored((255, 102, 102, 255), "err")'
    assert pr.expr("ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0.2f, 0.6f, 0.2f, 1.0f))") == \
        "im.push_style_color(im.Col.BUTTON, (51, 153, 51, 255))"


def test_a_colour_that_is_not_a_literal_is_converted_at_runtime():
    """Whether ``kAccent`` holds floats or bytes is not knowable here."""
    assert autoport.Porter().expr('ImGui::TextColored(kAccent, "hi")') == \
        'im.text_colored(im.floats_to_rgba(kAccent), "hi")'


def test_the_format_is_not_always_the_first_argument():
    """``TextColored(col, fmt, ...)``. Folding from argument 0 left the
    varargs unfolded, and cmtk's ``text_colored(col, s)`` takes two."""
    assert autoport.Porter().expr(
        'ImGui::TextColored(ImVec4(1,0,0,1), "%d/%d", a, b)') == \
        'im.text_colored((255, 0, 0, 255), "%d/%d" % (a, b))'


# --------------------------------------------------------------------------- #
# Embedded C++
#
# The repair loop has to cut something to keep the module importable. What it
# cut used to be the only copy in the file, leaving a reader a function name
# and a `pass`. The C++ goes in beside it instead.
# --------------------------------------------------------------------------- #
#: A body the rules genuinely cannot take: four assignments through a
#: ternary, which is an lvalue in C++ and never in Python. Four identical
#: errors is what tips the repair loop from marking single lines to cutting
#: the enclosing function -- which is the path this section is about.
_RESISTS = """
// Nudge whichever edge the drag grabbed. No rule covers this, and
// none should: a C++ ternary is an lvalue and a Python one is not.
void nudge_edge(bool from_left, float dx) {
  (from_left ? lo_ : hi_) = dx;
  (from_left ? lo2_ : hi2_) = dx;
  (from_left ? lo3_ : hi3_) = dx;
  (from_left ? lo4_ : hi4_) = dx;
}
void draw() { ImGui::Text("after"); }
"""


def _ported(text: str, **kw) -> str:
    return autoport.port_file([_tmp_cpp(text)], "embed", "o", **kw)


def test_a_cut_region_carries_the_cpp_it_came_from():
    out = _ported(_RESISTS)
    assert "resisted the mechanical port" in out, "fixture no longer resists"
    assert "# cpp| " in out
    assert "(from_left ? lo_ : hi_) = dx;" in out
    assert "(from_left ? lo4_ : hi4_) = dx;" in out


def test_the_embedded_cpp_keeps_the_comments_the_porter_strips():
    """The porter strips comments before translating, which is right for
    translating and wrong for reading: the comments are most of why the C++
    does what it does, and are the first thing a hand wants."""
    out = _ported(_RESISTS)
    assert "a C++ ternary is an lvalue" in out


def test_the_embedded_cpp_carries_the_signature_not_only_the_body():
    out = _ported(_RESISTS)
    assert "# cpp| void nudge_edge(bool from_left, float dx) {" in out


def test_embedding_does_not_stop_the_module_importing():
    """The whole point of the cut is that the module still compiles. A C++
    body full of braces, quotes and backslashes must not change that."""
    out = _ported(_RESISTS)
    compile(out, "embed", "exec")


def test_the_cut_still_happens_and_the_next_function_survives():
    out = _ported(_RESISTS)
    assert 'im.text("after")' in out


def test_none_gives_the_terse_output():
    for off in (False, "none"):
        out = _ported(_RESISTS, embed_cpp=off)
        assert "resisted the mechanical port" in out
        assert "# cpp| " not in out
        assert "# cpp: " not in out
        assert "from_left ? lo_" not in out


def test_ref_cross_references_instead_of_pasting():
    """The reference is cheaper to read than the paste, and it cannot fall
    out of step with the C++ the way a copy does."""
    out = _ported(_RESISTS, embed_cpp="ref")
    assert "# cpp: " in out
    assert "# cpp| " not in out, "ref mode should point, not paste"
    assert "from_left ? lo_" not in out
    compile(out, "embed", "exec")


def test_the_reference_names_the_file_and_the_lines():
    """``path:first-last``, which an editor's go-to-file and a grep both
    understand -- and the lines have to be the function's own."""
    src = _tmp_cpp("// pad\n" * 20 + _RESISTS)
    out = autoport.port_file([src], "embed", "o", embed_cpp="ref")
    m = re.search(r"# cpp: (\S+):(\d+)-(\d+)", out)
    assert m, "no reference emitted"
    path, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
    assert path == str(src)
    body = pathlib.Path(path).read_text().splitlines()
    assert "void nudge_edge" in body[lo - 1] or "//" in body[lo - 1]
    assert body[hi - 1].strip() == "}"


def test_full_carries_the_reference_too():
    """The truncation tail points at it, so it has to be there."""
    out = _ported(_RESISTS, embed_cpp="full")
    assert "# cpp: " in out
    assert "# cpp| " in out


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="embed_cpp must be one of"):
        _ported(_RESISTS, embed_cpp="verbose")


def test_a_dropped_destructor_leaves_what_it_released_behind():
    """Python has no deterministic destruction, so the body cannot port --
    but whether any of it matters is a judgement, and making it needs the
    code."""
    out = _ported("""
class Plot {
public:
  ~Plot();
};
Plot::~Plot() {
  // the ring buffer is the only thing that has to go back
  free(ring_);
}
""")
    assert "destructor" in out
    assert "# cpp| " in out
    assert "free(ring_);" in out
    assert "the ring buffer is the only thing" in out


def test_a_dropped_macro_invocation_keeps_its_arguments():
    """"Expand by hand" needs to know what was passed."""
    out = _ported("""
#define SPINNER_HEADER(pos, size, centre) do { } while (0)
void spin() {
  SPINNER_HEADER(pos, size, centre);
  ImGui::Text("x");
}
""")
    assert "expand by hand" in out
    assert "# cpp| SPINNER_HEADER(pos, size, centre)" in out


def test_an_overloaded_name_falls_back_rather_than_guessing():
    """Two definitions of a name give no single answer for which C++ a cut
    region came from. The stripped text is used instead of a coin toss."""
    import importlib
    pf = importlib.import_module("autoport.port_file")
    raw = [("a.cpp", "void f(int a) { g(); }\nvoid f(float a) { h(); }\n")]
    assert pf._original_cpp(raw, "f") == ("", ("", 0, 0))


def test_a_lambda_with_a_trailing_return_type_still_becomes_a_def():
    """`[&](int n) -> std::pair<double, double> {` ends in `>`, exactly like
    a braced construction of a templated type -- and the rule that swallows
    the latter swallowed the lambda's whole body with it, so no `def` was
    emitted and every call to the lambda was a NameError."""
    lines = _stmt("auto get_q = [&](int off) -> std::pair<double, double> "
                  "{ return std::make_pair(1.0, 2.0); };")
    assert lines[0] == "def get_q(off):", lines
    assert any("make_pair" in l for l in lines), lines


def test_a_braced_construction_of_a_templated_type_is_still_not_a_block():
    """The other half of the same test: yielding to the lambda must not undo
    the case it was written for."""
    lines = _stmt("cfg.set_colors(std::vector<std::array<int, 3>>{a, b, c});")
    assert lines == ["cfg.set_colors(std.vector(a, b, c))"], lines


def test_a_cast_takes_the_whole_postfix_expression():
    """`(float)q[0]` is a cast of the *element*. Binding to the name alone
    gave `float(q)[0]` -- a cast of the container, subscripted afterwards,
    which raises on the cast rather than anywhere near the mistake."""
    porter = autoport.Porter()
    assert porter.expr("(float)config.q_scatter[0]") == "float(config.q_scatter[0])"
    assert porter.expr("(int)v[i]") == "int(v[i])"
    assert porter.expr("(float)a.b[i][j]") == "float(a.b[i][j])"
    # the trailing-call case this shares its pattern with must keep working
    assert porter.expr("(float)cfg->width()") == "float(cfg.width())"


def test_an_out_parameter_does_not_leak_into_a_nested_lambda():
    """A `return` inside a lambda belongs to the lambda, not to the function
    around it. `RenderSimulationSettings` has four out-parameters, and its
    inner `get_q_species` came out returning `(qD, qA), brightness, idx,
    changed` -- which unpacked into `d, a = ...` as "too many values"."""
    porter = autoport.Porter()
    porter.out_names = ["changed"]
    porter.out_src_name = None
    lines = autoport.StatementPorter(porter).port(
        ["auto pick = [&](int i) -> std::pair<double, double> "
         "{ return std::make_pair(1.0, 2.0); };"])
    body = [l.strip() for l in lines if l.strip().startswith("return")]
    assert body == ["return std.make_pair(1.0, 2.0)"], lines


# --------------------------------------------------------------------------- #
# C++ identifiers that Python reserves
# --------------------------------------------------------------------------- #
def test_a_cpp_local_named_in_does_not_cost_its_function():
    """`std::ifstream in(path)` is ordinary C++ and `in = ...` is a Python
    *syntax error* -- so the repair loop cut the whole enclosing function.
    Two of cmc's panels were lost to one stream named `in`."""
    src = _tmp_cpp("""
static bool read_text_file(const std::string &path, std::string &out) {
  std::ifstream in(path, std::ios::binary);
  if (!in) { return false; }
  out.assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
  return true;
}
""")
    out = autoport.port_file([src], "m", "o")
    assert "resisted the mechanical port" not in out, out
    assert "def read_text_file(path, out):" in out
    assert "in_ = std.ifstream(path, std.ios.binary)" in out
    assert "if not in_:" in out


def test_only_the_keywords_cpp_leaves_free_are_renamed():
    """A Python keyword C++ *also* reserves is the C++ keyword itself, and
    renaming it would rewrite the language. That asymmetry is the whole
    reason the rename can be done blindly."""
    from autoport.lex import PY_ONLY_KEYWORDS, rename_reserved, safe_name

    for shared in ("class", "for", "return", "and", "or", "not", "while",
                   "else", "try", "break", "continue", "if"):
        assert shared not in PY_ONLY_KEYWORDS, shared
        assert safe_name(shared) == shared
    for free in ("in", "is", "from", "lambda", "del", "pass", "with"):
        assert free in PY_ONLY_KEYWORDS, free
        assert safe_name(free) == free + "_"

    # a control-flow line must come through untouched
    kept = "for (auto &x : v) { if (a and b) return not c; }"
    assert rename_reserved(kept) == kept


def test_a_reserved_word_inside_a_string_is_left_alone():
    """`"read from %s"` is a message, not an identifier."""
    from autoport.lex import rename_reserved

    out = rename_reserved('log("copied from %s to %s", from, to);')
    assert '"copied from %s to %s"' in out
    assert "from_," in out


def test_a_declaration_may_have_more_than_one_dimension():
    """`uint8_t palette[][3] = {{...}}` is a table. A pattern reading a
    single `[...]` did not match it *at all*, so the declaration was not a
    declaration and the whole enclosing function was cut."""
    assert _stmt("static const uint8_t palette[][3] = {{0,255,0},{255,0,0}};") \
        == ["palette = [[0,255,0],[255,0,0]]"]


def test_a_braced_initialiser_keeps_its_inner_braces():
    """`strip("{}")` strips *characters*, not one balanced pair, so a table
    lost its inner braces too and came out as `[0,255,0},{255,0,0]` -- which
    does not parse."""
    assert _stmt("float rows[][2] = {{1.0f, 2.0f}, {3.0f, 4.0f}};") \
        == ["rows = [[1.0, 2.0], [3.0, 4.0]]"]
    # the flat case must stay flat
    assert _stmt("float hist[4] = {1.0f, 2.0f};") == ["hist = [1.0, 2.0]"]


def test_an_anonymous_struct_local_becomes_a_namespace():
    """C++ has no name for the type and neither does Python, but the code
    goes on to read `c.r` -- so a namespace is what it needs, not a tuple."""
    assert _stmt("struct { uint8_t r, g, b; } c = {255, 255, 255};") \
        == ["c = std.record(r=255, g=255, b=255)"]
    # one field per declarator, across several declaration lines
    assert _stmt("struct { float x; float y; } p = {1.0f, 2.0f};") \
        == ["p = std.record(x=1.0, y=2.0)"]


def test_an_anonymous_struct_says_which_fields_were_not_initialised():
    """C++ value-initialises the rest; `None` says "not set" rather than
    inventing a zero for a type this was never told."""
    assert _stmt("struct { int a, b, c; } q = {1};") \
        == ["q = std.record(a=1, b=None, c=None)"]
