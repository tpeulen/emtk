from emtk import im
from emtk.app import ImApp
from emtk.offset_painter import OffsetPainter
from emtk.testing import RecordingPainter


def test_local_child_docks_draw_inside_parent_region():
    from emtk.docking import DockManager, Region

    docks = DockManager(Region("main"))
    docks.add_window("controls", "Controls", lambda box: im.button("Action"), dock="main")
    child = ImApp(lambda: docks.draw((0, 0, 300, 200)))
    parent = ImApp(lambda: None)
    painter = RecordingPainter()
    parent.draw_child(painter, child, 100, 80, 300, 200, local_coordinates=True)
    action = next(t for t in painter.texts if t[5] == "Action")
    assert action[0] >= 100 and action[1] >= 80
    assert painter.clips == []


def test_geometry_translation_preserves_metrics_and_optional_capabilities():
    painter = RecordingPainter()
    local = OffsetPainter(painter, 10, 20)
    local.fill_triangle((0, 0), (1, 0), (0, 1), (255, 0, 0))
    assert painter.triangles[0][:3] == ((10, 20), (11, 20), (10, 21))
    assert local.text_width("hello") == painter.text_width("hello")
    assert not hasattr(local, "image")


def test_rotated_text_capability_survives_an_offset_painter():
    class RotatedPainter:
        def __init__(self):
            self.args = None

        def text_rotated(self, x, y, w, h, align, string, colour, degrees=0.0):
            self.args = (x, y, w, h, align, string, colour, degrees)

        def text(self, *args):
            raise AssertionError("a painter with rotated text should keep using it")

    import inspect

    target = RotatedPainter()
    local = OffsetPainter(target, 17.0, 29.0)
    assert len(inspect.signature(local.text_rotated).parameters) == 8
    local.text_rotated(3.0, 5.0, 20.0, 10.0, 1, "Y label", (255, 0, 0, 255), -90.0)
    assert target.args == (20.0, 34.0, 20.0, 10.0, 1, "Y label", (255, 0, 0, 255), -90.0)
