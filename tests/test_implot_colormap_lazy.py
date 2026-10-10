"""Colormap lookup tables are interpolated on first use, not when ``emtk.implot`` is imported."""

from __future__ import annotations

from emtk import implot_internal as ipi


def test_tables_are_built_on_first_use_and_match_the_eager_build():
    data = ipi.ColormapData()
    data.append("two", [(0, 0, 0, 255), (255, 255, 255, 255)], False)
    data.append("qual", [(1, 2, 3, 255), (4, 5, 6, 255)], True)
    assert data.tables == [None, None]
    table = data.get_table(0)
    assert len(table) == 256 and table[0] == (0, 0, 0, 255) and table[-1] == (255, 255, 255, 255)
    assert table[128] == ipi.mix_u32((0, 0, 0, 255), (255, 255, 255, 255), 128)
    assert data.get_table_size(1) == 2
    assert data.lerp_table(0, 1.0) == (255, 255, 255, 255)


def test_editing_a_key_rebuilds_its_table():
    data = ipi.ColormapData()
    data.append("two", [(0, 0, 0, 255), (255, 255, 255, 255)], False)
    data.get_table(0)
    data.set_key_color(0, 1, (255, 0, 0, 255))
    assert data.get_table(0)[-1] == (255, 0, 0, 255)


def test_default_context_defers_every_table():
    assert all(table is None or isinstance(table, list) for table in ipi.PlotContext().colormap_data.tables)
    assert ipi.PlotContext().colormap_data.tables.count(None) == ipi.PlotContext().colormap_data.count
