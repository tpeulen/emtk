"""The controls: buttons, sliders, combos, inputs, drags, colour, selection, tabs, tables, menus, progress, text, editors, plots. Each is a retained object drawn through the Painter."""

from __future__ import annotations


def __getattr__(name: str):
    """Resolve a control lazily, exactly as :mod:`emtk` resolves its own.

    The families are independent modules; reaching one of them from here used
    to require importing it up front, which is the cost :mod:`emtk` removed
    for its own names. The same map answers for this package's.
    """
    import importlib
    import importlib.util

    # A submodule of this package wins over a control of the same name
    # (``calendar`` is both): ``from emtk.widgets import calendar`` asks this hook
    # before the import system looks for the submodule, so answering with the
    # function here would shadow the module for every later importer.
    if importlib.util.find_spec(f"{__name__}.{name}") is not None:
        return importlib.import_module(f".{name}", __name__)

    from .. import _NAME_TO_MODULE

    module_name = _NAME_TO_MODULE.get(name)
    if module_name is None or not module_name.startswith("widgets."):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f".{module_name.split('.', 1)[1]}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
