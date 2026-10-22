"""Icons are colour images of one size per class, fitted from their own ink.

The regression: every pictogram went through the text path as a tinted mask, so
a colour emoji drew grey, and each was the size its glyph happened to fill of a
monospace cell -- the 🪄 of the wizards a few pixels, the 🌐 a full cell.
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("PIL")

from emtk import icons  # noqa: E402
from emtk.testing import RecordingPainter  # noqa: E402

HAS_EMOJI_FONT = any(pathlib.Path(path).exists() for path, _sizes in icons.EMOJI_FONTS)
needs_emoji = pytest.mark.skipif(not HAS_EMOJI_FONT, reason="no colour-emoji font on this machine")

#: The icons of the reported ribbon (Tools tab), wand and globe among them.
TOOL_ICONS = ("🪄", "🌐", "🧮", "🔦", "📥", "🎮", "🗄️", "📝", "🔬", "⏱️")


def _pixels(texture):
    from PIL import Image

    return Image.frombytes("RGBA", (texture.width, texture.height), bytes(texture.px))


@needs_emoji
@pytest.mark.parametrize("icon", [i for i in TOOL_ICONS if i != "🗄️"])  # a grey cabinet by design
def test_an_emoji_icon_is_drawn_in_colour(icon):
    texture, colour = icons.icon_texture(icon, 32)
    assert texture is not None and colour
    image = _pixels(texture)
    hues = set()
    chromatic = 0
    for r, g, b, a in zip(*(band.tobytes() for band in image.split())):
        if a < 128:
            continue
        if max(r, g, b) - min(r, g, b) > 40:
            chromatic += 1
            hues.add((r // 64, g // 64, b // 64))
    # The source is the atlas's baked band now (pinned Noto), whose art is
    # less saturated at 32 px than the machine's own face was -- ⏱ carries
    # twelve chromatic texels where Apple's carried hundreds. The regression
    # this guards is the grey silhouette: chromatic ~0 and one hue.
    assert chromatic > 8, f"{icon} drew grey"
    assert len(hues) > 1, f"{icon} drew in one colour"


@needs_emoji
@pytest.mark.parametrize("icon", TOOL_ICONS)
def test_an_icon_fills_its_box_from_its_ink(icon):
    """Fitted from its bounds, not its advance: it reaches two opposite edges, centred."""
    texture, _colour = icons.icon_texture(icon, 40)
    assert (texture.width, texture.height) == (40, 40)
    left, top, right, bottom = _pixels(texture).getchannel("A").getbbox()
    assert right - left >= 38 or bottom - top >= 38, (icon, (left, top, right, bottom))
    assert abs(left - (40 - right)) <= 2 and abs(top - (40 - bottom)) <= 2, icon


def test_a_glyph_no_colour_font_has_is_a_mask_tinted_with_the_text():
    texture, colour = icons.icon_texture("◐", 24)
    if texture is None:
        pytest.skip("no font covers ◐")
    assert not colour
    painter = RecordingPainter()
    assert icons.draw_icon(painter, "◐", 0, 0, 12, (10, 20, 30, 255))
    assert painter.images[-1][5] == (10, 20, 30, 255)


@needs_emoji
def test_icons_are_rasterised_at_the_device_scale():
    class Device(RecordingPainter):
        def __init__(self, scale):
            super().__init__()
            self._scale = scale

    for scale in (1.0, 2.0):
        painter = Device(scale)
        icons.draw_icon(painter, "🔬", 5, 5, 16, (0, 0, 0, 255))
        _x, _y, w, h, handle, _tint = painter.images[-1]
        assert (w, h) == (16, 16)
        assert handle.width == handle.height == int(16 * scale)


@needs_emoji
def test_a_disabled_colour_icon_is_faded_not_tinted():
    painter = RecordingPainter()
    icons.draw_icon(painter, "🔬", 0, 0, 16, (40, 40, 40, 255), enabled=False)
    tint = painter.images[-1][5]
    assert tint[:3] == (255, 255, 255) and tint[3] < 255


def test_one_size_rule():
    assert icons.icon_box(16) == 16 * icons.SMALL_ICON
    assert icons.icon_box(16, large=True) == 16 * icons.LARGE_ICON
    assert icons.LARGE_ICON > icons.SMALL_ICON


@needs_emoji
def test_ribbon_icons_of_one_class_are_one_size():
    from emtk.ribbon import Ribbon, RibbonButton, RibbonGroup, RibbonTab
    from emtk.testing import Driver

    tools = [RibbonButton(f"t{i}", f"Tool {i}", icon=icon) for i, icon in enumerate(TOOL_ICONS)]
    tabs = [RibbonTab("Tools", [
        RibbonGroup("Big", [RibbonButton("tttr", "TTTR Tools", icon="📊", large=True),
                            RibbonButton("lab", "Lab", icon="🧪", large=True)]),
        RibbonGroup("Small", tools),
    ])]
    ribbon = Ribbon(tabs)

    from emtk import im
    from emtk.app import ImApp

    class App(ImApp):
        def __init__(self):
            self.item_rects = ribbon.item_rects
            super().__init__(self.gui)

        def gui(self):
            width, height = im.get_main_viewport().size
            im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
            im.set_next_window_size((width, height), im.Cond.ALWAYS)
            if im.begin("host", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
                ribbon.draw((0.0, 0.0, width, ribbon.height()))
            im.end()

    driver = Driver(App(), size=(1600, 300))
    driver.frame(2)
    painter = driver.frame()
    boxes = {icon: (w, h) for icon, _x, _y, w, h in painter.icons}
    assert set(TOOL_ICONS) <= set(boxes)
    small = {boxes[icon] for icon in TOOL_ICONS}
    assert len(small) == 1, small
    large_sizes = [entry[3:] for entry in painter.icons if entry[0] in ("📊", "🧪")]
    assert len(set(large_sizes)) == 1 and large_sizes[0][0] > next(iter(small))[0]
