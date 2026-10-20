"""A window draws at about 60 frames a second however fast input arrives, never under 60.

Every pointer move asks for a frame; under the old 240 Hz ceiling a fast mouse drew 240
frames a second. Presentation is vsynced, so the ceiling is the slowest whole fraction of
the screen's refresh rate that still reaches 60, with a margin that keeps it from beating
against vsync (a ceiling exactly at a refresh rate halves it: 60 on 120 Hz gave 30).
"""

import math

import pytest

from emtk.native import DEFAULT_MAX_FPS
from emtk.native import _frame_ceiling as frame_ceiling


def presented_fps(ceiling: float, refresh: float) -> float:
    """What a vsynced window shows under *ceiling*: the first vsync after the interval."""
    slot = 1.0 / refresh
    return 1.0 / (math.ceil((1.0 / ceiling) / slot - 1e-9) * slot)


@pytest.mark.parametrize("refresh, shown", [(60, 60), (75, 75), (90, 90), (100, 100),
                                            (120, 60), (144, 72), (165, 82.5), (240, 60)])
def test_the_ceiling_shows_the_slowest_vsync_fraction_at_or_above_sixty(refresh, shown):
    assert presented_fps(frame_ceiling(refresh), refresh) == pytest.approx(shown)


def test_an_unknown_screen_gets_about_sixty():
    assert 60.0 < DEFAULT_MAX_FPS <= 66.0
    assert frame_ceiling(0) == DEFAULT_MAX_FPS
