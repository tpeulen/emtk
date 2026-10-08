"""Layout evidence follows aligned glyph bounds and nested clips, not viewport-sized text boxes."""

import pytest
from emtk.painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER
from emtk.testing import RecordingPainter

COLOUR = (240, 240, 240, 255)


def overlap(a, b):
    """Return the visible intersection area of two recorded text rectangles."""
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(width, 0) * max(height, 0)


def test_visible_bounds_preserve_the_original_recording_contract():
    """A caller can still inspect exact submitted boxes and operation tuples."""
    painter = RecordingPainter()
    painter.text(10, 20, 300, 60, 0, "Hello", COLOUR, True)
    original = (10, 20, 300, 60, 0, "Hello", COLOUR, True)
    assert painter.texts == [original]
    assert painter.strings == ["Hello"]
    assert painter.calls == [("text", *original)]
    assert painter.visible_texts == [(10, 20, 35, 16, 0, "Hello", COLOUR, True)]


def test_alignment_font_scale_and_nested_clip_are_recorded_at_draw_time():
    """Centered text is measured before intersecting every active clipping rectangle."""
    painter = RecordingPainter()
    painter.set_font_scale(1.5)
    painter.push_clip(0, 0, 90, 100)
    painter.push_clip(40, 25, 30, 20)
    alignment = ALIGN_HCENTER | ALIGN_VCENTER
    painter.text(10, 10, 100, 50, alignment, "Hello", COLOUR)
    # Five 10.5px glyph advances, 24px line height, center=(60,35).
    assert painter.visible_texts[0][:4] == (40, 25, 30, 20)
    info = painter.text_metadata[0]
    assert info["measured_bounds"] == (33.75, 23.0, 52.5, 24.0)
    assert info["font_scale"] == 1.5
    assert info["line_height"] == 24
    assert info["clips"] == ((0, 0, 90, 100), (40, 25, 30, 20))
    painter.pop_clip()
    painter.pop_clip()
    painter.text(10, 10, 100, 50, ALIGN_RIGHT, "Hello", COLOUR)
    assert painter.visible_texts[1][:4] == (57.5, 10, 52.5, 24)
    assert info["clips"] == ((0, 0, 90, 100), (40, 25, 30, 20))
    assert painter.clips == []


def test_all_active_parent_clips_bound_the_glyphs():
    """A wide nested clip cannot erase its parent's restriction; text boxes only align."""
    painter = RecordingPainter()
    painter.push_clip(20, 5, 30, 100)
    painter.push_clip(0, 0, 500, 500)
    painter.text(0, 0, 100, 40, 0, "A long label", COLOUR)
    assert painter.visible_texts[0][:4] == (20, 5, 30, 11)
    painter.pop_clip()
    painter.pop_clip()
    painter.text(0, 0, 30, 40, 0, "A long label", COLOUR)
    assert painter.visible_texts[1][:4] == (0, 0, 84, 16)


def test_alignment_box_does_not_hide_real_overflow_without_an_active_clip():
    """Pixel/Quad text can overflow its alignment box; the recorder must retain that collision."""
    painter = RecordingPainter()
    painter.text(0, 0, 14, 20, 0, "Overflow", COLOUR)
    painter.text(40, 0, 100, 20, 0, "Next", COLOUR)
    assert painter.visible_texts[0][:4] == (0, 0, 56, 16)
    assert painter.text_metadata[0]["text_box"] == (0, 0, 14, 20)
    assert overlap(*painter.visible_texts) > 0

    clipped = RecordingPainter()
    clipped.push_clip(0, 0, 14, 20)
    clipped.text(0, 0, 14, 20, 0, "Overflow", COLOUR)
    clipped.pop_clip()
    clipped.text(40, 0, 100, 20, 0, "Next", COLOUR)
    assert clipped.visible_texts[0][:4] == (0, 0, 14, 16)
    assert overlap(*clipped.visible_texts) == 0


def test_fully_clipped_and_blank_text_keep_parallel_zero_area_records():
    """Invisible text remains traceable without participating in overlap assertions."""
    painter = RecordingPainter()
    painter.push_clip(100, 100, 20, 20)
    painter.text(0, 0, 50, 20, 0, "Hidden", COLOUR)
    painter.pop_clip()
    painter.text(0, 0, 50, 20, 0, "   ", COLOUR)
    painter.text(0, 0, 50, 20, 0, "Transparent", (*COLOUR[:3], 0))
    assert len(painter.visible_texts) == len(painter.texts) == len(painter.text_metadata) == 3
    assert all(record[2] * record[3] == 0 for record in painter.visible_texts)


def test_current_font_size_and_scale_both_reach_visible_bounds():
    """Metadata reflects the same selected-font measurements used to lay out the text."""
    from emtk.font import DEFAULT_FONT_PT

    painter = RecordingPainter()
    painter.set_font({"family": "monospace", "size": DEFAULT_FONT_PT * 2})
    painter.set_font_scale(1.25)
    painter.text(10, 10, 100, 80, ALIGN_RIGHT | ALIGN_VCENTER, "XX", COLOUR)
    assert painter.visible_texts[0][:4] == (75, 30, 35, 40)
    assert painter.text_metadata[0]["font_size_ratio"] == 2
    painter.set_font(None)
    painter.set_font_scale(1)
    assert painter.text_metadata[0]["line_height"] == 40


def test_selected_font_and_bold_metrics_are_retained_after_font_changes():
    """A real selected face uses its bold advance rather than the recorder's round cell."""
    from emtk.font import available_fonts
    from emtk.font_render import FontSpec, _faces, line_height, text_width

    family = next(
        (
            name
            for name in available_fonts()
            if name != "monospace" and any(face.bold and not face.italic for face in _faces()[name])
        ),
        None,
    )
    if family is None:
        pytest.skip("No system font available")
    painter = RecordingPainter()
    painter.set_font({"family": family, "size": 14})
    painter.set_font_scale(1.25)
    painter.text(10, 20, 400, 100, ALIGN_RIGHT, "WWW iii", COLOUR, True)
    actual = FontSpec(family, 14, True, False)
    width = text_width(actual, "WWW iii", 1.25)
    height = line_height(actual, 1.25)
    assert painter.visible_texts[0][:4] == (410 - width, 20, width, height)
    assert painter.text_metadata[0]["font_spec"] == actual
    painter.set_font(None)
    assert painter.text_metadata[0]["font_spec"] == actual


def test_a_long_clipped_dock_tab_does_not_overlap_its_overflow_arrows():
    """The real dock renderer clips titles before the separately drawn arrow buttons."""
    from emtk.app import ImApp
    from emtk.docking import DockManager, Region

    docks = DockManager(Region("main"))
    titles = ["Coefficients", "Intensity scatter", "PCC vs intensity", "Object distances"]
    for title in titles:
        docks.add_window(title, title, lambda box: None, dock="main", closable=False)
    app = ImApp(lambda: docks.draw((0, 0, 240, 100)))
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 240, 100)
    arrows = [record for record in painter.visible_texts if record[5] in {"◀", "▶"}]
    labels = [record for record in painter.visible_texts if record[5] in titles and record[2] > 0]
    assert len(arrows) == 2 and labels
    assert any(record[2] == 0 for record in painter.visible_texts if record[5] in titles)
    assert all(overlap(label, arrow) == 0 for label in labels for arrow in arrows)


def test_syntax_editor_runs_use_glyph_spans_instead_of_remaining_viewport_width():
    """Adjacent colored tokens have large submitted text boxes but separate visible bounds."""
    from emtk.widgets.text_editor import Language, TextEditor

    painter = RecordingPainter()
    editor = TextEditor('def example():\n    return "value"', Language.python())
    editor.draw(painter, 0, 0, 500, 100)
    tokens = [
        (raw, visible)
        for raw, visible in zip(painter.texts, painter.visible_texts)
        if raw[5].strip() in {"def", "example", "return", '"value"'}
    ]
    assert len(tokens) >= 3
    assert any(raw[2] > visible[2] + 100 for raw, visible in tokens)
    for index, (_, a) in enumerate(tokens):
        for _, b in tokens[index + 1 :]:
            assert overlap(a, b) == 0


def test_real_overlap_is_still_reported_without_title_exclusions():
    """Clipping metadata cannot excuse two visible strings drawn on top of one another."""
    painter = RecordingPainter()
    painter.text(0, 0, 100, 20, 0, "First", COLOUR)
    painter.text(10, 0, 100, 20, 0, "Second", COLOUR)
    with pytest.raises(AssertionError, match="visible text overlaps"):
        assert overlap(*painter.visible_texts) == 0, "visible text overlaps"
