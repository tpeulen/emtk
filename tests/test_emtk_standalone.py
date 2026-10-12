"""emtk is a library: its lazy name map is current and its families import."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import emtk

_ROOT = pathlib.Path(emtk.__file__).resolve().parents[1]

_PROBE = r'''
import importlib, json, sys
import emtk as emtk
for name in emtk.CONTROL_MODULES:
    importlib.import_module(f"emtk.{name}")
for name in ("painter", "quad_painter", "style", "font", "atlas", "testing"):
    try:
        importlib.import_module(f"emtk.{name}")
    except ImportError:
        pass
bad = sorted(m for m in sys.modules if m.startswith("chimol.") and not m.startswith("emtk"))
print(json.dumps(bad))
'''


def test_importing_every_emtk_family_pulls_in_no_engine_module():
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, cwd=str(_ROOT), check=True)
    leaked = json.loads(out.stdout.strip().splitlines()[-1])
    assert leaked == [], f"emtk imported engine modules: {leaked}"


def test_the_lazy_name_map_is_current():
    proc = subprocess.run([sys.executable, str(_ROOT / "tools" / "gen_names.py"), "--check"],
                          capture_output=True, text=True, cwd=str(_ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_mapped_name_resolves():
    import emtk as emtk

    for name, module in emtk._NAME_TO_MODULE.items():
        assert getattr(emtk, name) is not None, f"{name} from {module}"


def test_importing_one_module_does_not_import_the_widget_set():
    """``import emtk.i18n`` is what a headless host does for translated text; it must stay light.

    ChiSurf's plugin-manifest loader calls it from core code with no GUI; the package
    ``__init__`` used to import the painter, layout and every widget family behind it.
    """
    code = (
        "import sys, emtk.i18n; "
        "heavy = [m for m in ('emtk.painter', 'emtk.im', 'emtk.layout', 'emtk.widgets.basic') "
        "if m in sys.modules]; "
        "assert not heavy, heavy; "
        "import emtk; assert emtk.Painter and emtk.Button and emtk.im and emtk.redraw "
        "and emtk.Plot and emtk.DEEP_PALETTE and emtk.nice_ticks"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          cwd=str(_ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr
