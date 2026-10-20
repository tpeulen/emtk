"""``emtk.widgets.<name>`` is the submodule when one exists, even if a control shares the name."""

import importlib
import subprocess
import sys


def test_from_widgets_import_calendar_is_the_module():
    """``calendar`` is a module and a control; the package attribute must stay the module.

    The lazy ``__getattr__`` once answered ``from emtk.widgets import calendar`` with the
    ``calendar`` function and cached it, so ``stylesheet`` / ``view_form`` failed with
    ``'function' object has no attribute 'stylesheet_part'``. Run in a fresh interpreter:
    the bug depends on which import reaches the package first.
    """
    code = (
        "import emtk.widgets as w, types\n"
        "from emtk.widgets import calendar\n"
        "assert isinstance(calendar, types.ModuleType), calendar\n"
        "assert isinstance(w.calendar, types.ModuleType), w.calendar\n"
        "assert callable(calendar.stylesheet_part)\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_controls_still_resolve_lazily():
    """A control name with no submodule of that name still comes from the map."""
    import importlib.util

    import emtk
    import emtk.widgets as w

    names = [
        name for name, module in emtk._NAME_TO_MODULE.items()
        if module.startswith("widgets.")
        and importlib.util.find_spec(f"emtk.widgets.{name}") is None
    ]
    assert names
    assert getattr(w, names[0]) is getattr(
        importlib.import_module(f"emtk.{emtk._NAME_TO_MODULE[names[0]]}"), names[0]
    )
