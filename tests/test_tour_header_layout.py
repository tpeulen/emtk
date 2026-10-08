"""The shared tour title and drag affordance occupy distinct visible rows."""

import pytest
from emtk.app import ImApp
from emtk.help_guide import EmTkGuidedTour
from emtk.testing import Driver


@pytest.mark.parametrize("size", [(1400, 900), (400, 700)])
def test_long_title_has_no_overlap_with_drag_caption(size):
    """A real awaited card keeps the full prescribed title visible below its header."""
    tour = EmTkGuidedTour(
        [{"title": "Start with data whose answer you know", "text": "Load the scan.",
          "target": {"name": "load_example"}, "await": {"hint": "Press Load demo."}}, {"title": "Read the result"}],
        wait_for_controls=True,
    )
    app = ImApp(lambda: tour.draw(*size))
    tour.start()
    driver = Driver(app, size)
    painter = driver.frame(3)
    caption = next(t for t in painter.visible_texts if t[5] == "drag here to move")
    title_lines = [t for t in painter.visible_texts if "Step 1 of 2:" in t[5]
                   or "whose answer you know" in t[5] or "answer you know" in t[5]]
    assert title_lines
    assert all(line[1] >= caption[1] + caption[3] for line in title_lines)
    assert "Start with data whose answer you know" in " ".join(
        " ".join(painter.strings).split()
    )
    assert tour.awaiting
    driver.click("Next ▶")
    assert tour.active and tour.awaiting
