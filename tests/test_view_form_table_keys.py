"""Every key a declarative table reads is a declared table key (the schema generators read TABLE_KEYS)."""

import re
from pathlib import Path

from emtk.view_form import TABLE_KEYS


def test_every_key_the_table_binding_reads_is_declared():
    source = (Path(__file__).resolve().parents[1] / "emtk" / "widgets" / "data_table.py").read_text(
        encoding="utf-8"
    )
    read = set(re.findall(r'merged\.get\("(\w+)"', source))
    assert {"fit_rows", "drag_call", "selection_attr"} <= read
    assert read <= TABLE_KEYS | {"type", "description", "label", "title", "visible", "key", "attr"}, (
        sorted(read - TABLE_KEYS)
    )
