"""The font configuration (:mod:`emtk.fonts`): roles, zoom, oversampling, fallbacks, live apply.

What a settings page promises is checked against what is *measured*: a size or a
family change must change the widths a layout gets, consistently and at once (the
caches dropped), the zoom must scale the box and map the pointer back, a role's own
fallback chain must win over the system's, and the configuration must survive a
round trip through a plain dict -- including a hand-edited one.
"""

from __future__ import annotations

import pytest

from emtk import font_render, fonts, type_scale
from emtk.app import ControlSurface


@pytest.fixture(autouse=True)
def _defaults():
    fonts.reset()
    yield
    fonts.reset()


def _installed(*families):
    faces = font_render._faces()
    return next((f for f in families if f in faces), None)


# -- defaults are today's look ------------------------------------------------ #
def test_defaults_are_the_type_scale_as_it_was():
    cfg = fonts.config()
    assert cfg.ui.family == "monospace" and cfg.code.family == "monospace"
    assert cfg.prose.family == "prose" and cfg.heading.bold and cfg.zoom == 1.0
    body = type_scale.size_pt("body")
    assert body == pytest.approx(type_scale._baked_pt())
    assert type_scale.size_pt("h1") == pytest.approx(body * type_scale.STEP**4)
    assert type_scale.size_pt("caption") == pytest.approx(body / type_scale.STEP)
    assert type_scale.text_font("body")["family"] == type_scale.PROSE_FAMILY
    assert type_scale.text_font("code")["family"] == type_scale.CODE_FAMILY


# -- persistence ---------------------------------------------------------------- #
def test_round_trip_through_a_plain_dict():
    fonts.update(
        code={"family": "Courier New, monospace", "size": 11.0},
        prose={"size": 10.5},
        zoom=1.25,
        oversample=2.0,
        antialias=False,
        heading_step=1.2,
        fallbacks=("Apple Symbols",),
    )
    data = fonts.config().to_dict()
    assert all(isinstance(v, (dict, str, float, bool, list)) for v in data.values())
    assert fonts.FontConfig.from_dict(data) == fonts.config()


def test_a_hand_edited_dict_never_breaks():
    cfg = fonts.FontConfig.from_dict(
        {
            "ui": {"size": "big"},
            "code": 3,
            "prose": {"family": "", "size": 1000},
            "zoom": 99,
            "oversample": -1,
            "antialias": "yes",
            "unknown": 1,
            "heading_step": float("nan"),
            "fallbacks": "A, , B",
        }
    )
    assert cfg.ui == fonts.FontConfig().ui and cfg.code == fonts.FontConfig().code
    assert cfg.prose.family == "prose" and cfg.prose.size == fonts.MAX_PT
    assert cfg.zoom == fonts.MAX_ZOOM and cfg.oversample == fonts.MIN_OVERSAMPLE
    assert cfg.antialias is True and cfg.heading_step == 1.125
    assert cfg.fallbacks == ("A", "B")


def test_update_rejects_an_unknown_setting():
    with pytest.raises(ValueError):
        fonts.update(colour="red")


# -- sizes and families change measured widths --------------------------------- #
def test_interface_size_scales_every_width_linearly():
    text = "Fit the decay"
    ui, prose = fonts.measure("ui", text), fonts.measure("prose", text)
    fonts.update(ui={"size": 12.0})
    assert fonts.measure("ui", text) == pytest.approx(ui * 12.0 / 8.0)
    assert fonts.measure("prose", text) == pytest.approx(prose * 12.0 / 8.0)  # follows
    fonts.update(ui={"size": 6.0})
    assert fonts.measure("ui", text) == pytest.approx(ui * 6.0 / 8.0)


def test_a_role_with_its_own_size_leaves_the_others():
    text = "Fit the decay"
    ui, code = fonts.measure("ui", text), fonts.measure("code", text)
    fonts.update(prose={"size": 12.0})
    assert fonts.measure("ui", text) == pytest.approx(ui)
    assert fonts.measure("code", text) == pytest.approx(code)
    assert type_scale.role_pt("body") == pytest.approx(12.0)
    assert type_scale.role_pt("h2") == pytest.approx(12.0 * 1.125**3)
    fonts.update(heading_step=1.25)
    assert type_scale.role_pt("h2") == pytest.approx(12.0 * 1.25**3)


def test_a_family_change_changes_widths_and_drops_the_caches():
    family = _installed("Courier New", "Courier", "DejaVu Sans Mono", "Menlo")
    if family is None:
        pytest.skip("no second monospaced face installed")
    text = "def fit(x):"
    before = fonts.measure("code", text)
    generation = fonts.generation()
    font_render.text_width(font_render.font_spec("prose"), text, 1.0)
    assert font_render.text_width.cache_info().currsize > 0
    fonts.update(code=family)
    assert fonts.generation() == generation + 1
    assert font_render.text_width.cache_info().currsize == 0
    assert fonts.measure("code", text) != pytest.approx(before)
    fonts.update(code=family)  # no change, no invalidation
    assert fonts.generation() == generation + 1


def test_a_missing_family_falls_back_instead_of_failing():
    fonts.update(prose="No Such Face 12345", code="No Such Mono 12345")
    assert type_scale.text_font("body")["family"] == type_scale.PROSE_FAMILY
    assert type_scale.text_font("code")["family"] == type_scale.CODE_FAMILY
    fonts.update(ui="No Such Face 12345")
    assert font_render.font_spec(None).family == "monospace"


def test_system_families_lists_generics_and_monospaced_faces():
    every = fonts.system_families()
    mono = fonts.system_families(monospace=True)
    assert every[:4] == ("monospace", "prose", "sans-serif", "serif")
    assert mono[0] == "monospace" and "prose" not in mono
    assert set(mono) - {"monospace"} <= set(every)
    for name in mono[1:6]:
        assert font_render._face(font_render.FontSpec(name)).monospaced


# -- fallback chains ------------------------------------------------------------- #
def test_a_roles_own_fallback_chain_wins_over_the_system_list():
    primary = _installed("Verdana", "DejaVu Sans", "Arial", "Helvetica")
    if primary is None:
        pytest.skip("no proportional face installed")
    face = font_render._face(font_render.FontSpec(primary))
    covered = font_render._cmap(face.path, face.index)
    if covered is None:
        pytest.skip("cmap unreadable")
    for family in (
        "Apple Symbols",
        "STIXGeneral",
        "DejaVu Sans",
        "Symbola",
        "Arial Unicode MS",
    ):
        if family == primary or family not in font_render._faces():
            continue
        other = font_render._family_face(family, False, False)
        theirs = font_render._cmap(other.path, other.index) or frozenset()
        char = next(
            (c for c in "⨁∮⨀∴↯⌇⭍" if ord(c) in theirs and ord(c) not in covered), None
        )
        if char is not None:
            break
    else:
        pytest.skip("no fallback face with a glyph the primary lacks")
    spec = font_render.font_spec(f"{primary}, {family}")
    assert spec.family == primary and spec.fallback[0] == family
    runs = font_render._runs(spec, "a" + char)
    assert runs[-1][0] == other
    # The configured global fallbacks are appended to every chain.
    fonts.update(fallbacks=(family,))
    assert family in font_render.font_spec(primary).fallback


# -- rendering settings ------------------------------------------------------------ #
def test_oversampling_rasterises_finer_glyphs_of_the_same_size():
    spec = font_render.font_spec("prose")
    ((tex1, _, _, w1, h1),) = list(font_render.glyphs(spec, "M", 1.0))
    fonts.update(oversample=2.0)
    ((tex2, _, _, w2, h2),) = list(font_render.glyphs(spec, "M", 1.0))
    assert tex2.width > 1.6 * tex1.width
    # Same drawn size: only the texel padding round the ink (a texel each) shrinks.
    assert w2 == pytest.approx(w1, abs=2.0) and h2 == pytest.approx(h1, abs=2.0)


def test_antialias_off_draws_bilevel_glyphs():
    spec = font_render.font_spec("prose")
    fonts.update(antialias=False)
    ((tex, *_),) = list(font_render.glyphs(spec, "a", 1.0, origin=(0.0, 0.0)))
    alphas = set(bytes(tex.px)[3::4])
    assert alphas <= {0, 255} and 255 in alphas
    fonts.update(antialias=True)
    ((tex, *_),) = list(font_render.glyphs(spec, "a", 1.0, origin=(0.0, 0.0)))
    assert set(bytes(tex.px)[3::4]) - {0, 255}


# -- the interface face ---------------------------------------------------------------- #
def test_a_new_painter_adopts_the_interface_face():
    from emtk.quad_painter import QuadPainter

    family = _installed("Verdana", "DejaVu Sans", "Arial", "Helvetica")
    if family is None:
        pytest.skip("no proportional face installed")
    baked = QuadPainter().text_width("iiii")
    fonts.update(ui=family)
    assert QuadPainter().text_width("iiii") != pytest.approx(baked)
    fonts.reset()
    assert QuadPainter().text_width("iiii") == pytest.approx(baked)


def test_the_editor_draws_in_the_code_role_unless_its_host_pushed_a_font():
    from emtk.painter import current_font, set_font
    from emtk.quad_painter import QuadPainter
    from emtk.widgets.text_editor import TextEditor

    family = _installed("Courier New", "Courier", "DejaVu Sans Mono", "Andale Mono")
    if family is None:
        pytest.skip("no monospaced system face installed")

    def painter_with_atlas():
        painter = QuadPainter()
        painter.image_uv_resolver = lambda texture: ((0.0, 0.0), (1.0, 1.0))
        return painter

    editor = TextEditor("print('hello')\n")
    editor.draw(painter_with_atlas(), 0, 0, 400, 200)
    baked = editor._glyph_w
    fonts.update(code={"family": family, "size": 14.0})
    painter = painter_with_atlas()
    editor.draw(painter, 0, 0, 400, 200)
    assert editor._glyph_w > baked * 1.3
    assert current_font(painter) == (None, 0.0)  # the host's (default) font is back
    host_font = {"family": "monospace", "size": 8.0}
    set_font(painter, host_font)
    editor.draw(painter, 0, 0, 400, 200)
    assert editor._glyph_w == pytest.approx(baked)
    assert current_font(painter) == (host_font, 0.0)


# -- zoom ----------------------------------------------------------------------------------- #
class _Probe:
    def __init__(self):
        self.presses = []
        self.boxes = []

    def draw(self, painter, x, y, w, h):
        self.boxes.append((w, h))

    def pointer_press(self, x, y, button, modifiers, clicks):
        self.presses.append((x, y))


def test_zoom_shrinks_the_layout_box_and_maps_the_pointer_back():
    probe = _Probe()
    surface = ControlSurface(probe)
    surface.on_resize(1000, 800, 2.0)
    assert surface._box()[2:] == (500.0, 400.0)
    fonts.update(zoom=1.25)
    assert surface.scale == pytest.approx(2.5)
    assert surface._box()[2:] == pytest.approx((400.0, 320.0))
    surface.on_pointer_press(250.0, 125.0, 1, 0)
    assert probe.presses[-1] == pytest.approx((200.0, 100.0))
    pinned = ControlSurface(_Probe(), zoom=1.0)
    pinned.on_resize(1000, 800, 1.0)
    assert pinned._box()[2:] == (1000.0, 800.0)


def test_a_click_lands_on_its_button_at_zoom_125():
    from emtk import im
    from emtk.testing_realistic import RealisticDriver

    clicks = []

    def gui():
        im.begin("w")
        im.dummy((160.0, 120.0))  # far from the origin, where an unmapped click misses
        im.same_line()
        if im.button("Press me"):
            clicks.append(1)
        im.end()

    fonts.update(zoom=1.25)
    driver = RealisticDriver(gui, size=(400, 300), real_painter=False)
    driver.frame(2)
    assert driver.surface._box()[2:] == pytest.approx((320.0, 240.0))
    driver.click("Press me")
    assert clicks == [1]


def test_a_realistic_screenshot_is_what_the_person_sees_under_zoom():
    """Device-size GPU pixels with the zoom applied, not the app's box drawn at scale 1."""
    from emtk import im
    from emtk.testing import png_decode
    from emtk.testing_realistic import RealisticDriver

    def gui():
        im.begin("w")
        im.dummy((560.0, 400.0))
        im.button("Corner")
        im.end()

    fonts.update(zoom=1.25)
    driver = RealisticDriver(gui, size=(800, 600), scale=2.0)
    driver.frame(2)
    width, height, pixels = png_decode(driver.screenshot())
    assert (width, height) == (1600, 1200)
    x, y, w, h = driver.rect("Corner")
    # The button's bottom lies past 480 window pixels only because the zoom is applied.
    assert y + h < 480 < (y + h) * 1.25
    cx, cy = round((x + w / 2) * 1.25 * 2), round((y + h / 2) * 1.25 * 2)
    background = pixels[0:4]
    assert any(pixels[4 * (cy * width + cx + dx): 4 * (cy * width + cx + dx) + 4] != background
               for dx in range(-20, 20))
