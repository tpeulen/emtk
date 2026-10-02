from emtk.painter import ALIGN_VCENTER
from emtk.pil_painter import PilPainter


def test_centered_text_ink_stays_inside_its_control_after_atlas_padding():
    painter = PilPainter(120, 80)
    painter.text(10, 30, 100, 20, ALIGN_VCENTER, "Save", (255, 255, 255))
    pixels = painter.frame.load()
    rows = [y for y in range(80) if any(pixels[x, y] != (0, 0, 0) for x in range(120))]
    assert rows
    assert min(rows) >= 30
    assert max(rows) < 50
