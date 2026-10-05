"""A window that appears comes to the front, as ``Begin`` does in the reference.

Windows are created in two places: by ``begin`` and by loading saved ini
settings. A window the settings file names is created *first*, long before it
is shown, so without this rule it sat behind every window submitted after it
and a press over the overlap went to the window underneath. ChiSurf's guided
tour card hit exactly that: once a layout file remembered the card, its Next
button was dead wherever the card lay over the project table.
"""
from __future__ import annotations

import emtk
from emtk.flags import WindowFlags
from emtk.testing import RecordingPainter

INI = "[Window][card]\nPos=40,40\nSize=80,40\n"


def _frame(ctx_windows):
    painter = RecordingPainter()
    io = emtk.IO()
    return emtk.frame(painter, (0.0, 0.0, 200.0, 200.0), io=io)


def test_a_window_named_in_the_settings_comes_to_the_front_when_it_appears():
    with _frame(None) as ctx:
        emtk.load_ini_settings_from_memory(INI)
        ctx.begin("browser", (0.0, 0.0, 200.0, 200.0))
        ctx.end()
        ctx.begin("card", (40.0, 40.0, 80.0, 40.0))
        ctx.end()
        assert [w.name for w in ctx.windows][-1] == "card"
        assert ctx.find_hovered_window(60.0, 60.0).name == "card"


def test_no_focus_on_appearing_keeps_its_place():
    with _frame(None) as ctx:
        emtk.load_ini_settings_from_memory(INI)
        ctx.begin("browser", (0.0, 0.0, 200.0, 200.0))
        ctx.end()
        ctx.begin("card", (40.0, 40.0, 80.0, 40.0), WindowFlags.NO_FOCUS_ON_APPEARING)
        ctx.end()
        assert ctx.find_hovered_window(60.0, 60.0).name == "browser"


def test_submission_order_is_display_order_for_new_windows():
    """Appearing in order brings each to the front in order: nothing changes."""
    with _frame(None) as ctx:
        for name in ("a", "b", "c"):
            ctx.begin(name, (0.0, 0.0, 100.0, 100.0))
            ctx.end()
        assert [w.name for w in ctx.windows] == ["a", "b", "c"]


def test_a_window_only_named_in_the_settings_takes_no_press():
    """Created by the loader, never submitted: not drawn, so not hit."""
    with _frame(None) as ctx:
        ctx.begin("browser", (0.0, 0.0, 200.0, 200.0))
        ctx.end()
        emtk.load_ini_settings_from_memory(INI)
        assert ctx.find_hovered_window(60.0, 60.0).name == "browser"
