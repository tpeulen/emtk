"""cmtk is a library: its lazy name map is current and its families import."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import cmtk

_ROOT = pathlib.Path(cmtk.__file__).resolve().parents[1]

_PROBE = r'''
import importlib, json, sys
import cmtk as cmtk
for name in cmtk.CONTROL_MODULES:
    importlib.import_module(f"cmtk.{name}")
for name in ("painter", "quad_painter", "style", "font", "atlas", "testing"):
    try:
        importlib.import_module(f"cmtk.{name}")
    except ImportError:
        pass
bad = sorted(m for m in sys.modules if m.startswith("chimol.") and not m.startswith("cmtk"))
print(json.dumps(bad))
'''


def test_importing_every_cmtk_family_pulls_in_no_engine_module():
    out = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, cwd=str(_ROOT), check=True)
    leaked = json.loads(out.stdout.strip().splitlines()[-1])
    assert leaked == [], f"cmtk imported engine modules: {leaked}"


def test_the_lazy_name_map_is_current():
    proc = subprocess.run([sys.executable, str(_ROOT / "tools" / "gen_names.py"), "--check"],
                          capture_output=True, text=True, cwd=str(_ROOT))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_mapped_name_resolves():
    import cmtk as cmtk

    for name, module in cmtk._NAME_TO_MODULE.items():
        assert getattr(cmtk, name) is not None, f"{name} from {module}"
