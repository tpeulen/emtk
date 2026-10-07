"""Repeated responsive visibility policies preserve table state and horizontal access."""

import pytest
from emtk.widgets.data_table import DataTable, TableColumn


def _table(monkeypatch):
    """Observe real invalidation while retaining selection, filter and scroll state."""
    table = DataTable([TableColumn(key, key) for key in ("a", "b", "c")], row_key="id")
    table.set_records([{"id": "row", "a": 1, "b": 2, "c": 3}])
    assert table.select_key("row")
    calls = []
    original = table.changed

    def changed():
        """Count invalidation without replacing its actual revision behavior."""
        calls.append(table.revision)
        original()

    monkeypatch.setattr(table, "changed", changed)
    return table, calls


@pytest.mark.parametrize("hidden", [False, True])
def test_repeated_membership_preserves_scroll_selection_and_revision(monkeypatch, hidden):
    """A stable per-frame visibility policy cannot undo the user's horizontal scroll."""
    table, calls = _table(monkeypatch)
    table.set_column_hidden("b", hidden)
    table.scroll_columns(1)
    revision, calls_before = table.revision, list(calls)
    for _ in range(3):
        table.set_column_hidden("b", hidden)
    assert table.first_column == 1
    assert table.selected_key == "row"
    assert table.revision == revision
    assert calls == calls_before


def test_real_visibility_transitions_reset_scroll_and_invalidate_once(monkeypatch):
    """Both hiding and showing retain their actual transition notifications."""
    table, calls = _table(monkeypatch)
    for hidden in (True, False):
        table.scroll_columns(1)
        revision, count = table.revision, len(calls)
        table.set_column_hidden("b", hidden)
        assert table.first_column == 0
        assert table.revision == revision + 1
        assert len(calls) == count + 1
        assert ("b" in table.hidden) is hidden
        assert table.selected_key == "row"


def test_last_visible_column_cannot_be_hidden(monkeypatch):
    """The existing last-column validation is retained without spurious change."""
    table, calls = _table(monkeypatch)
    table.set_column_hidden("b", True)
    table.set_column_hidden("c", True)
    revision, count = table.revision, len(calls)
    table.set_column_hidden("a", True)
    assert [column.key for column in table.visible_columns()] == ["a"]
    assert table.revision == revision
    assert len(calls) == count
