#!/usr/bin/env python3
"""python tools/autoport/__main__.py src.h [src.cpp] --module name --out DIR"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from autoport.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
