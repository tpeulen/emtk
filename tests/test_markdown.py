"""Tests for EMTK Markdown and Font typography capabilities."""

import pytest
from emtk import im
from emtk.testing import RecordingPainter, PixelPainter
from emtk.widgets.markdown import MarkdownBlock, parse_markdown, render_markdown


def test_parse_markdown():
    text = """# Header 1
A paragraph with **bold**, *italic*, `code`, and [link](docs/page.md).

## Header 2
- Bullet 1
- Bullet 2

$$
E = mc^2
$$

```python
x = 10
```
"""
    blocks = parse_markdown(text)
    kinds = [b.kind for b in blocks]
    assert "h1" in kinds
    assert "p" in kinds
    assert "h2" in kinds
    assert "list_item" in kinds
    assert "math" in kinds
    assert "code" in kinds


def test_font_scale_and_heading_in_frame():
    p = RecordingPainter()
    with im.frame(p, (0, 0, 800, 600)):
        im.begin("Font Test")

        # Headings
        im.heading("Main Title", level=1)
        im.heading("Section Subtitle", level=2)

        # Font scale stack
        im.push_font_scale(1.5)
        im.text("Scaled text")
        im.pop_font_scale()

        # Custom font
        im.push_font({"family": "sans-serif", "bold": True})
        im.text("Bold Sans Text")
        im.pop_font()

        # Render markdown directly
        im.markdown("# Sub Title\nThis is **bold** and *italic*.")

        im.end()


def test_markdown_on_pixel_painter():
    p = PixelPainter(200, 200, background=(0, 0, 0, 255))
    with im.frame(p, (0, 0, 200, 200)):
        im.begin("MD Win")
        clicked = []
        im.markdown(
            "# Hello World\nA paragraph with [link](target.md).\n- item 1\n",
            on_link=lambda url: clicked.append(url),
        )
        im.end()

    # Pixels should be drawn
    lit = sum(1 for i in range(0, len(p.px), 4) if p.px[i] > 20)
    assert lit > 0
