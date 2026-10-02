"""emtk.help_guide: the help window and the guided tour draw and step."""
from emtk import im
from emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from emtk.im_core import IO, frame
from emtk.testing import RecordingPainter

HELP = "# Overview\n\nWhat it does.\n\n# Settings\n\n- one\n- two\n"
STEPS = [
    {"title": "Welcome", "text": "Hello.", "target": {}},
    {"title": "Press it", "text": "Press <b>Run</b>.", "target": {"action": "run"},
     "await": {"hint": "Press Run."}},
    {"title": "Done", "text": "That was it.", "target": {}},
]


def _frames(draw, n=2):
    storage, io, painter = {}, IO(), None
    for _ in range(n):
        painter = RecordingPainter()
        with frame(painter, (0.0, 0.0, 900.0, 700.0), io=io, storage=storage):
            draw()
    return painter


def test_help_sections_and_draw():
    h = EmTkHelpWindow(title="Help", text=HELP)
    assert [s[0] for s in h.sections][:2] == ["Overview", "Settings"]
    h.show()
    painter = _frames(lambda: h.draw((0.0, 0.0, 900.0, 700.0)))
    assert any("What it does" in s for s in painter.strings)


def test_tour_waits_for_the_awaited_control():
    rects = {"run": (100.0, 100.0, 80.0, 24.0)}
    t = EmTkGuidedTour(STEPS, get_target_rect=rects.get, wait_for_controls=True)
    t.start()
    t.next()
    assert t.step_idx == 1 and t.awaiting
    painter = _frames(lambda: t.draw(900.0, 700.0))
    assert any("Press it" in s for s in painter.strings)
    t.notify_used("other")
    assert t.awaiting
    t.notify_used("run")
    assert not t.awaiting
    t.next()
    assert t.step_idx == 2
    t.stop()
    assert not t.active
