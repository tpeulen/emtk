"""A table consumes a delivered wheel event once in an immediate-mode frame."""

from types import SimpleNamespace

from emtk.testing import Driver
from emtk.widgets.view_spec import ViewSpecPanel


def test_table_wheel_does_not_scroll_again_on_idle_frames():
    model = SimpleNamespace(rows=[{"value": str(i)} for i in range(100)])
    panel = ViewSpecPanel(
        {
            "sections": [
                {
                    "type": "table",
                    "source": "rows",
                    "columns": [{"key": "value", "label": "Value"}],
                    "height": 180,
                }
            ]
        },
        model,
    )
    drv = Driver(panel, (400, 240))
    drv.frame(2)
    table = panel.tables[0].control
    drv.wheel(-1, at=(100, 100))
    assert table.bar.top == 3
    drv.frame(3)
    assert table.bar.top == 3
    assert panel.io.mouse_wheel == 0
