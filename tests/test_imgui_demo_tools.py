"""``imgui_demo.cpp``'s Configuration, Tools, Window options and Help sections.

The last groups: the style editor and its selector, the metrics and debug-log
windows, the id-stack tool, the about box and the user guide, window flags, and
the settings that persist between runs.

These are the reference's own *tools*, so porting them is a fair test of
whether cmtk can build the kind of thing Dear ImGui is used for -- a window
made out of the widgets themselves, reading the context back.
"""
from __future__ import annotations

import pytest

import cmtk
from cmtk.testing import RecordingPainter


def _run(gui, size=(0.0, 0.0, 500.0, 600.0), io=None, storage=None):
    painter = RecordingPainter()
    with cmtk.frame(painter, size, io=io or cmtk.IO(),
                    storage=storage if storage is not None else {}):
        gui()
    return painter


# --------------------------------------------------------------------------- #
# Tools/Style Editor  (imgui_demo.cpp: ShowStyleEditor)
# --------------------------------------------------------------------------- #
def test_the_style_editor_shows_the_metrics_and_the_palette():
    painter = _run(cmtk.show_style_editor)
    assert "frame_rounding" in painter.strings
    assert any("Button" in s for s in painter.strings)
    # A swatch per colour: the palette is drawn, not only named.
    assert sum(1 for c in painter.calls if c[0] == "fill_rect") > 20


def test_the_style_selector_switches_the_palette():
    state = {"box": None}

    def gui():
        cmtk.show_style_selector("Style")
        state["box"] = cmtk.get_item_rect()
        state["window_bg"] = cmtk.get_style().color(cmtk.Col.WINDOW_BG)

    io, storage = cmtk.IO(), {}
    _run(gui, io=io, storage=storage)
    dark = state["window_bg"]

    box = state["box"]
    io.mouse_pos = (box[0] + 2, box[1] + 2)
    io.mouse_down[0] = io.mouse_clicked[0] = True
    io.mouse_clicked_pos[0] = io.mouse_pos
    _run(gui, io=io, storage=storage)
    io.mouse_clicked[0] = False
    io.mouse_down[0] = False
    io.mouse_released[0] = True
    _run(gui, io=io, storage=storage)
    assert state["window_bg"] != dark, "the style selector changed nothing"


# --------------------------------------------------------------------------- #
# Tools/Metrics, Debug Log, ID Stack Tool
# --------------------------------------------------------------------------- #
def test_the_metrics_window_reports_the_frame_it_is_in():
    answers: dict = {}

    def gui():
        cmtk.show_metrics_window()
        answers["frame"] = cmtk.get_frame_count()

    painter = _run(gui)
    assert any(("frame %d" % answers["frame"]) in s for s in painter.strings), \
        painter.strings
    assert any("windows:" in s for s in painter.strings)
    assert any("mouse:" in s for s in painter.strings)


def test_the_debug_log_shows_what_was_logged():
    def gui():
        cmtk.debug_log("first entry")
        cmtk.debug_log("second entry")
        cmtk.show_debug_log_window()

    painter = _run(gui)
    assert "first entry" in painter.strings
    assert "second entry" in painter.strings


def test_the_id_stack_tool_reports_the_stack_it_is_inside():
    def gui():
        cmtk.push_id("outer")
        cmtk.push_id(7)
        cmtk.show_id_stack_tool_window()
        cmtk.pop_id()
        cmtk.pop_id()

    painter = _run(gui)
    assert any("outer" in s and "7" in s for s in painter.strings), painter.strings


def test_the_about_window_and_the_user_guide_draw():
    about = _run(cmtk.show_about_window)
    assert any("cmtk" in s for s in about.strings)
    guide = _run(cmtk.show_user_guide)
    assert any("collapse window" in s for s in guide.strings)


def test_the_demo_window_runs_and_shows_its_sections():
    painter = _run(cmtk.show_demo_window)
    for section in ("Basic", "Trees", "Plots"):
        assert any(section in s for s in painter.strings), section


# --------------------------------------------------------------------------- #
# Configuration/Style and the version
# --------------------------------------------------------------------------- #
def test_the_style_can_be_read_and_written_through_the_context():
    seen: dict = {}

    def gui():
        style = cmtk.get_style()
        seen["before"] = style.frame_rounding
        style.frame_rounding = 6.0
        seen["after"] = cmtk.get_style().frame_rounding

    _run(gui)
    assert seen["after"] == 6.0 and seen["before"] != 6.0


def test_the_version_is_reported():
    def gui():
        assert cmtk.get_version()

    _run(gui)
    assert cmtk.IMGUI_VERSION.startswith("1.")


def test_a_colour_can_be_named_and_read_as_floats():
    def gui():
        assert "Button" in cmtk.get_style_color_name(cmtk.Col.BUTTON)
        rgba = cmtk.get_style_color_vec4(cmtk.Col.BUTTON)
        assert len(rgba) == 4 and all(0.0 <= c <= 1.0 for c in rgba)

    _run(gui)


# --------------------------------------------------------------------------- #
# Window options  (imgui_demo.cpp: the demo window's own flags)
# --------------------------------------------------------------------------- #
def test_a_window_can_be_placed_sized_and_focused():
    answers: dict = {}

    def gui():
        cmtk.begin("first", (0.0, 0.0, 100.0, 100.0))
        cmtk.end()
        cmtk.begin("second", (10.0, 10.0, 120.0, 120.0))
        answers["pos"] = cmtk.get_window_pos()
        answers["size"] = cmtk.get_window_size()
        answers["focused"] = cmtk.is_window_focused()
        cmtk.end()

    _run(gui)
    assert answers["pos"] == (10.0, 10.0)
    assert answers["size"] == (120.0, 120.0)
    assert answers["focused"] is True, "the last window begun was not the front one"


def test_a_window_is_appearing_only_on_its_first_frame():
    seen = []

    def gui():
        cmtk.begin("appearing", (0.0, 0.0, 50.0, 50.0))
        seen.append(cmtk.is_window_appearing())
        cmtk.end()

    io, storage = cmtk.IO(), {}
    _run(gui, io=io, storage=storage)
    _run(gui, io=io, storage=storage)
    _run(gui, io=io, storage=storage)
    assert seen[0] is True, "a brand new window did not report itself appearing"
    assert seen[1:] == [False, False], seen


# --------------------------------------------------------------------------- #
# Configuration/Settings  (LoadIniSettings / SaveIniSettings)
# --------------------------------------------------------------------------- #
def test_the_settings_round_trip_through_a_file(tmp_path):
    ini = tmp_path / "imgui.ini"

    def save():
        cmtk.begin("left", (10.0, 20.0, 100.0, 50.0))
        cmtk.end()
        cmtk.save_ini_settings_to_disk(str(ini))

    _run(save)
    assert ini.exists() and "[Window][left]" in ini.read_text()

    placed: dict = {}

    def load():
        cmtk.load_ini_settings_from_disk(str(ini))
        cmtk.begin("left")
        placed["pos"] = cmtk.get_window_pos()
        placed["size"] = cmtk.get_window_size()
        cmtk.end()

    _run(load)
    assert placed["pos"] == (10.0, 20.0)
    assert placed["size"] == (100.0, 50.0)


def test_a_malformed_settings_file_is_skipped_not_half_read():
    placed: dict = {}

    def load():
        cmtk.load_ini_settings_from_memory(
            "[Window][bad]\nPos=1,2,3\nSize=4\n"
            "[Window][good]\nPos=5,6\nSize=7,8\n")
        cmtk.begin("good")
        placed["good"] = (cmtk.get_window_pos(), cmtk.get_window_size())
        cmtk.end()
        placed["names"] = [w.name for w in cmtk.get_current_context().windows]

    _run(load)
    assert placed["good"] == ((5.0, 6.0), (7.0, 8.0))
    assert "bad" not in placed["names"], "a malformed entry was let through"

# --------------------------------------------------------------------------- #
# ``IMGUI_DEMO_MARKER`` sections covered above, spelled as the reference
# spells them -- the manifest matches on these exact names.
#   Tools/Debug Log
