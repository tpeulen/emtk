"""Display preferences must change rendered editor colors, not just settings."""
from emtk import im
from emtk.testing import RecordingPainter
from emtk.widgets.text_editor import TextEditor, Pos, Language


def test_editor_display_colors_and_current_line_toggle():
    editor = TextEditor("value = 42")
    editor.config.background_color = (240, 241, 242, 255)
    editor.config.margin_color = (210, 211, 212, 255)
    editor.config.line_number_color = (30, 31, 32, 255)
    editor.config.selection_color = (100, 101, 102, 255)
    editor.config.caret_color = (70, 71, 72, 255)
    editor.config.current_line_color = (50, 51, 52, 255)
    editor.config.highlight_current_line = False
    editor.select_region(Pos(0, 0), Pos(0, 3))
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 600, 300)):
        im.text_editor("source", editor, (600, 300))
    colors = {tuple(fill[-1]) for fill in painter.fills}
    assert (240, 241, 242, 255) in colors
    assert (210, 211, 212, 255) in colors
    assert (100, 101, 102, 255) in colors
    assert (50, 51, 52, 255) not in colors
    assert any(tuple(text[6]) == (30, 31, 32, 255) for text in painter.texts if text[5] == "1")
    editor.config.highlight_current_line = True
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 600, 300)):
        im.text_editor("source", editor, (600, 300))
    assert any(tuple(fill[-1]) == (50, 51, 52, 255) for fill in painter.fills)


def test_yaml_language_supports_comments_strings_and_keywords():
    editor = TextEditor('enabled: true\nlabel: "sample" # note', language=Language.yaml())
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 500, 200)):
        im.text_editor("yaml", editor, (500, 200))
    assert editor.language_name == "YAML"
    from emtk.widgets.text_editor import Token
    assert Token.KEYWORD in editor.document.lines[0].colours
    assert Token.STRING in editor.document.lines[1].colours
    assert Token.COMMENT in editor.document.lines[1].colours
