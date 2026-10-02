"""Tests for the HTML fragment -> Markdown conversion used by im.markdown."""

from emtk import html_to_markdown as to_md
from emtk import looks_like_html
from emtk.testing import RecordingPainter
from emtk.widgets.markdown import parse_markdown


def test_settings_status_table():
    """The boarding status page converts to a heading plus a pipe table."""
    html = (
        "<h3>Settings status</h3><table style='border-collapse:collapse'>"
        "<tr><td style='padding:4px 10px'>Users</td>"
        "<td style='color:#2e7d32;font-weight:600'>OK</td></tr>"
        "<tr><td>MMFDB</td><td>not defined</td></tr></table>"
    )
    md = to_md(html)
    assert "### Settings status" in md
    assert "| Users | OK |" in md
    assert "| MMFDB | not defined |" in md
    assert "<" not in md


def test_headings_bold_italic_code_entities():
    md = to_md(
        "<h1>Top</h1><p>TTTR: <b>ok</b>; pyqtgraph: <i>missing</i>; "
        "path <code>~/.chisurf</code> &amp; more.</p>"
    )
    assert "# Top" in md
    assert "**ok**" in md
    assert "*missing*" in md
    assert "`~/.chisurf`" in md
    assert "&" in md and "&amp;" not in md


def test_links_and_lists_and_breaks():
    md = to_md(
        "<p>See <a href='https://example.com'>the docs</a>.</p>"
        "<ul><li>one</li><li>two</li></ul>line1<br>line2"
    )
    assert "[the docs](https://example.com)" in md
    assert "- one" in md and "- two" in md
    assert "line1\nline2" in md


def test_unknown_html_degrades_to_text():
    md = to_md("<div style='color:red'><span>plain words remain</span></div>")
    assert "plain words remain" in md
    assert "<" not in md and "style" not in md


def test_plain_text_passes_through_untouched():
    text = "# Not HTML\n\njust markdown with | pipes |"
    assert to_md(text) == text


def test_looks_like_html():
    assert looks_like_html("<h3>x</h3>")
    assert not looks_like_html("a < b and c > d")
    assert not looks_like_html("")


def test_parse_markdown_consumes_html():
    """The markdown entry point converts HTML before parsing."""
    blocks = parse_markdown("<h3>Status</h3><p><b>OK</b></p>")
    kinds = [b.kind for b in blocks]
    assert "h3" in kinds
    assert any(b.text == "**OK**" for b in blocks)


def test_markdown_widget_draws_no_raw_tags():
    """Rendering an HTML status page draws converted text, never literal tags."""

    def gui():
        from emtk import im

        im.begin("html md", (0, 0, 460, 420))
        im.markdown(
            "<h3>Settings status</h3>"
            "<table><tr><td>Users</td><td>OK</td></tr>"
            "<tr><td>TTTR</td><td>connected</td></tr></table>"
            "<p><b>OK</b></p>"
        )
        im.end()

    painter = RecordingPainter()
    from emtk.im_core import frame

    with frame(painter, (0.0, 0.0, 460.0, 420.0)):
        gui()

    joined = " ".join(painter.strings)
    assert "<h3>" not in joined and "<table" not in joined and "<td" not in joined
    assert "Settings status" in joined
    assert "Users" in joined and "connected" in joined
