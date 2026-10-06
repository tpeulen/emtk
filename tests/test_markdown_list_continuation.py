"""A list item wrapped over several source lines is one item, not an item plus a stray paragraph."""

from emtk.widgets.markdown import parse_markdown


def test_wrapped_numbered_item_is_one_block():
    blocks = parse_markdown("1. Files: drop your measurements, or press Load demo data for a\n   simulated measurement.\n2. Next step.\n")
    assert [b.kind for b in blocks] == ["list_item", "list_item"]
    assert blocks[0].text == "Files: drop your measurements, or press Load demo data for a simulated measurement."


def test_lazy_continuation_without_indent_joins_the_item():
    blocks = parse_markdown("- first part\nsecond part\n\nA paragraph.\n")
    assert [b.kind for b in blocks] == ["list_item", "p"]
    assert blocks[0].text == "first part second part"


def test_a_heading_or_table_ends_the_item():
    blocks = parse_markdown("- item\n## Heading\n- other\n| a | b |\n")
    assert [b.kind for b in blocks] == ["list_item", "h2", "list_item", "table"]
