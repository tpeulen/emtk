#!/usr/bin/env python
"""Regenerate ``_NAME_TO_MODULE`` in ``emtk/__init__.py`` from each family's ``__all__``.

    python tools/gen_names.py          # rewrite the block in place
    python tools/gen_names.py --check  # exit 1 if the block is stale

Reads the modules with ``ast`` (no import), so it runs anywhere.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
INIT = ROOT / "emtk" / "__init__.py"


def family_modules() -> tuple[str, ...]:
    tree = ast.parse(INIT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONTROL_MODULES" for t in node.targets):
            return tuple(e.value for e in node.value.elts)
    raise SystemExit("CONTROL_MODULES not found")


def exported(tree: ast.Module) -> list[str]:
    """The names in a module's ``__all__``.

    A literal list is read straight off. A module that *computes* it -- the
    `im` facade is ``list(_CORE) + list(_WIDGETS)``, because writing the two
    lists out again by hand is how they come to disagree -- has its
    ``from .x import __all__ as _y`` aliases followed to the modules they came
    from, which is the same answer without importing anything.
    """
    names: list[str] = []
    aliases: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "__all__" and alias.asname:
                    aliases[alias.asname] = node.module.lstrip(".")
    for node in tree.body:
        # `__all__ = [...]` and `__all__ += [...]` both. Only the first was
        # read, so every name a module appended -- which is how a file that
        # grows in sections declares them -- was silently left out of the map,
        # and `--check` agreed with itself because it regenerated the same
        # omission.
        if isinstance(node, ast.Assign):
            if not any(isinstance(t, ast.Name) and t.id == "__all__"
                       for t in node.targets):
                continue
        elif isinstance(node, ast.AugAssign):
            if not (isinstance(node.target, ast.Name)
                    and node.target.id == "__all__"):
                continue
        else:
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                names.append(sub.value)
            elif isinstance(sub, ast.Name) and sub.id in aliases:
                source = INIT.parent / (aliases[sub.id].replace(".", "/") + ".py")
                if source.exists():
                    names += exported(ast.parse(source.read_text(encoding="utf-8")))
    return names


def name_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for m in family_modules():
        tree = ast.parse((INIT.parent / (m.replace(".", "/") + ".py")).read_text(encoding="utf-8"))
        for name in exported(tree):
            out.setdefault(name, m)
    return out


def render(mapping: dict[str, str]) -> str:
    lines = ["_NAME_TO_MODULE: dict[str, str] = {"]
    lines += [f'    "{n}": "{mapping[n]}",' for n in sorted(mapping)]
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = INIT.read_text(encoding="utf-8")
    block = re.search(r"_NAME_TO_MODULE: dict\[str, str\] = \{\n(?:.*?\n)?\}\n", text, re.S)
    fresh = render(name_map())
    if block is None:
        raise SystemExit("no _NAME_TO_MODULE block in emtk/__init__.py")
    if "--check" in argv:
        if block.group(0) == fresh:
            print("emtk name map is current")
            return 0
        print("emtk name map is stale: run tools/gen_names.py")
        return 1
    INIT.write_text(text[: block.start()] + fresh + text[block.end():], encoding="utf-8")
    print(f"wrote {fresh.count(chr(10)) - 2} names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
