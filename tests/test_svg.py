"""emtk.svg: an SVG document drawn into pixels (what a console shows for ``_repr_svg_``)."""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("PIL")

from emtk.svg import rasterize_svg, svg_to_png, svg_to_texture  # noqa: E402


def _svg(body: str, size: str = 'width="40" height="20"', extra: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'{size} {extra}>{body}</svg>')


def test_the_size_comes_from_width_and_height_in_their_units():
    assert rasterize_svg(_svg("")).shape == (20, 40, 4)
    assert rasterize_svg(_svg("", 'width="3in" height="1in"')).shape == (96, 288, 4)
    assert rasterize_svg(_svg("", 'viewBox="0 0 30 10"')).shape == (10, 30, 4)
    assert rasterize_svg(_svg(""), scale=2).shape == (40, 80, 4)


def test_a_filled_rect_covers_exactly_its_pixels():
    px = rasterize_svg(_svg('<rect x="10" y="5" width="20" height="10" fill="#ff0000"/>'))
    assert tuple(px[10, 20]) == (255, 0, 0, 255)
    assert px[2, 2, 3] == 0 and px[10, 35, 3] == 0
    assert (px[..., 3] > 0).sum() == 200


def test_the_viewbox_scales_the_drawing():
    px = rasterize_svg(_svg('<rect width="2" height="1" fill="blue"/>', extra='viewBox="0 0 4 2"'))
    assert (px[..., 3] == 255).sum() == 20 * 10


def test_paths_with_curves_and_the_even_odd_rule_leave_a_hole():
    ring = ('<path fill-rule="evenodd" fill="black" d="M 0 0 H 20 V 20 H 0 Z '
            'M 5 5 h 10 v 10 h -10 z"/>')
    px = rasterize_svg(_svg(ring, 'width="20" height="20"'))
    assert px[10, 10, 3] == 0 and px[2, 2, 3] == 255
    # Non-zero with the inner square wound the same way fills the hole.
    solid = rasterize_svg(_svg(ring.replace('fill-rule="evenodd" ', ""), 'width="20" height="20"'))
    assert solid[10, 10, 3] == 255
    disc = rasterize_svg(_svg('<path d="M 0 10 A 10 10 0 1 0 20 10 A 10 10 0 1 0 0 10 Z"/>',
                              'width="20" height="20"'))
    assert disc[10, 10, 3] == 255 and disc[0, 0, 3] == 0
    assert abs((disc[..., 3] / 255.0).sum() - np.pi * 100) < 12


def test_strokes_inherit_from_groups_and_transforms_compose():
    body = ('<g stroke="#00ff00" stroke-width="2" fill="none" transform="translate(10 0)">'
            '<line x1="0" y1="10" x2="20" y2="10" transform="scale(1)"/></g>')
    px = rasterize_svg(_svg(body))
    assert tuple(px[10, 20, :3]) == (0, 255, 0) and px[10, 20, 3] > 200
    assert px[10, 5, 3] == 0 and px[3, 20, 3] == 0


def test_use_draws_a_definition_and_clip_paths_clip_to_their_box():
    body = ('<defs><path id="dot" d="M -2 -2 h 4 v 4 h -4 z"/>'
            '<clipPath id="c"><rect x="0" y="0" width="20" height="20"/></clipPath></defs>'
            '<use xlink:href="#dot" x="5" y="5" fill="red"/>'
            '<rect x="0" y="0" width="40" height="20" fill="blue" fill-opacity="0.5" '
            'clip-path="url(#c)"/>')
    px = rasterize_svg(_svg(body))
    assert px[5, 5, 0] > 100 and px[5, 5, 3] == 255
    assert px[15, 10, 3] > 0 and px[15, 30, 3] == 0


def test_style_and_opacity_are_read():
    px = rasterize_svg(_svg('<rect width="40" height="20" style="fill: rgb(0,0,255); opacity: 0.5"/>'))
    assert abs(int(px[10, 10, 3]) - 128) <= 1


def test_text_draws_something_where_it_is_placed():
    px = rasterize_svg(_svg('<text x="2" y="16" font-size="14">Hi</text>'))
    assert (px[..., 3] > 0).sum() > 10


def test_png_and_texture_and_a_matplotlib_figure():
    png = svg_to_png(_svg('<circle cx="20" cy="10" r="8" fill="orange"/>'))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    texture = svg_to_texture(_svg('<circle cx="20" cy="10" r="8" fill="orange"/>'))
    assert texture.size == (40, 20)
    mpl = pytest.importorskip("matplotlib")
    mpl.use("agg")
    import io

    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(3, 2), dpi=72)
    ax.plot([0, 1, 2], [0, 1, 0], color="red")
    ax.set_title("T")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    plt.close(fig)
    px = rasterize_svg(buffer.getvalue())
    reds = (px[..., 0] > 200) & (px[..., 1] < 80) & (px[..., 2] < 80) & (px[..., 3] > 200)
    assert reds.sum() > 50, "the plotted line is drawn"
    dark = (px[..., :3].max(axis=2) < 80) & (px[..., 3] > 200)
    assert dark.sum() > 100, "axes, ticks and glyphs are drawn"


def test_not_svg_is_an_error():
    with pytest.raises(ValueError):
        rasterize_svg("<html/>")
