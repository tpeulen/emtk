"""Sub- and superscripts drawn as smaller, shifted runs (``emtk.script_text``).

A parameter label such as ``w_{z} [nm]`` has no Unicode subscript ``z``, so the
glyph conversion left the markup on screen. These tests draw on the recording
painter and check where each run went and at what size; a table column with
``display: "script"`` draws its cells that way, and ``fit_rows`` sizes a table
to its rows.
"""

from __future__ import annotations

import pytest

from emtk.painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from emtk.script_text import (
    SCRIPT_SCALE,
    draw_script_text,
    has_scripts,
    plain_script_text,
    script_runs,
    script_width,
)
from emtk.testing import RecordingPainter
from emtk.widgets.data_table import TableBinding


def test_runs_split_base_sub_and_super():
    assert script_runs("w_{z} [nm]") == [("w", 0), ("z", -1), (" [nm]", 0)]
    assert script_runs("x^{2}_{i}") == [("x", 0), ("2", 1), ("i", -1)]
    assert script_runs(r"file\_{a}") == [("file_{a}", 0)]
    assert script_runs("a_b") == [("a_b", 0)], "a bare underscore is text"
    assert has_scripts("τ_{D}") and not has_scripts("plain") and not has_scripts(r"\_{x}")
    assert plain_script_text("d_{foci} [nm]") == "dfoci [nm]"


def test_a_subscript_is_smaller_and_below_the_base_line():
    painter = RecordingPainter()
    draw_script_text(painter, 10.0, 0.0, 200.0, 20.0, ALIGN_LEFT | ALIGN_VCENTER, "w_{z}[nm]",
                     (255, 255, 255, 255))
    runs = {t[5]: t for t in painter.texts}
    assert set(runs) == {"w", "z", "[nm]"}
    base, sub, unit = runs["w"], runs["z"], runs["[nm]"]
    assert sub[1] > base[1], "the subscript is set lower"
    assert sub[0] > base[0] and unit[0] > sub[0], "the runs follow each other"
    assert painter._font_scale == 1.0, "the base size is restored"
    width = script_width(painter, "w_{z}[nm]")
    assert width < painter.text_width("wz[nm]"), "the script run is narrower than base text"
    assert width == pytest.approx(painter.text_width("w[nm]") + painter.text_width("z") * SCRIPT_SCALE)


def test_a_superscript_is_above_and_right_alignment_ends_at_the_box():
    painter = RecordingPainter()
    draw_script_text(painter, 0.0, 0.0, 300.0, 20.0, ALIGN_RIGHT | ALIGN_VCENTER, "x^{-1}",
                     (255, 255, 255, 255))
    base, sup = painter.texts
    assert sup[1] < base[1]
    assert sup[0] + painter.text_width("-1") * SCRIPT_SCALE == pytest.approx(300.0, abs=0.01)


def test_text_without_scripts_is_one_ordinary_call():
    painter = RecordingPainter()
    draw_script_text(painter, 0.0, 0.0, 100.0, 20.0, ALIGN_LEFT, "N", (0, 0, 0, 255))
    assert painter.strings == ["N"]


class _Parameters:
    def __init__(self, n=3):
        self.rows = [{"uid": str(i), "label": f"w_{{{c}}} [nm]", "value": float(i)}
                     for i, c in zip(range(n), "rzx")]

    def records(self):
        return self.rows


def _section(**options):
    return {
        "type": "table",
        "source": "records",
        "row_key": "uid",
        "columns": [
            {"key": "label", "label": "Name", "display": "script"},
            {"key": "value", "label": "Value"},
        ],
        **options,
    }


def test_a_script_column_draws_its_cells_with_scripts():
    control = TableBinding(_section(), _Parameters()).control
    painter = RecordingPainter()
    control.draw(painter, 0.0, 0.0, 300.0, 200.0)
    assert "w_{z} [nm]" not in painter.strings, "the markup is not shown"
    assert painter.strings.count("w") == 3 and "z" in painter.strings
    assert " [nm]" in painter.strings


def test_fit_rows_sizes_the_table_to_its_rows():
    control = TableBinding(_section(fit_rows=True), _Parameters(3)).control
    line = RecordingPainter().line_height()
    three = control.natural_height(line)
    more = TableBinding(_section(fit_rows=True), _Parameters(3))
    more.model.rows = more.model.rows + [dict(r, uid=r["uid"] + "b") for r in more.model.rows]
    more.refresh()
    six = more.control.natural_height(line)
    assert six - three == pytest.approx(3 * line * control.row_scale)
    binding = TableBinding(_section(fit_rows=True, height=40), _Parameters(3))
    assert binding.fit_rows and binding.max_height == 40.0

