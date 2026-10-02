from emtk.painter import ALIGN_VCENTER
from emtk.testing import PixelPainter


def test_pixel_painter_font_scale_changes_ink_as_well_as_metrics():
    widths = []
    for scale in (1, 2):
        painter = PixelPainter(200, 80)
        painter.set_font_scale(scale)
        painter.text(5, 10, 180, 50, ALIGN_VCENTER, "Hello", (255, 255, 255))
        xs = [x for y in range(80) for x in range(200)
              if any(painter.px[(y * 200 + x) * 4:(y * 200 + x) * 4 + 3])]
        widths.append(max(xs) - min(xs))
    assert widths[1] > widths[0] * 1.8
