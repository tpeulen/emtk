from emtk import im
from emtk.testing import RecordingPainter


def draw_tabs(storage, labels, selected=None):
    results = []
    with im.frame(RecordingPainter(), (0, 0, 600, 300), storage=storage):
        im.begin_tab_bar("documents")
        for index, label in enumerate(labels):
            flags = im.TabItemFlags.SET_SELECTED if index == selected else 0
            results.append(im.begin_tab_item(label, flags=flags))
            im.end_tab_item()
        im.end_tab_bar()
    return results


def test_requested_tab_stays_selected_after_title_changes():
    storage = {}
    draw_tabs(storage, ["main.py###first", "main.py###second"], selected=1)
    assert draw_tabs(storage, ["main.py###first", "main.py*###second"]) == [False, True]


def test_same_named_tabs_have_independent_identity():
    assert draw_tabs({}, ["main.py##first", "main.py##second"]) == [True, False]
