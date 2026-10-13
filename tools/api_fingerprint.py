"""emtk's public API as data, and the snapshot that ties it to ``__version__``.

Applications pin emtk by version (ChiSurf refuses to start on an emtk older
than the minimum it names). That only works when a change to the public API
also changes ``__version__``: emtk once grew ``DockWindow(workspace=...)``
while still saying ``0.1.8``, and an application that needed the new keyword
passed its version check and crashed with a ``TypeError``.

So the public API is fingerprinted and recorded in
``tests/api_fingerprint.json`` together with the version it belongs to;
``tests/test_api_fingerprint.py`` fails when the two drift apart.

The API is read from the *source* (``ast``), never by importing: an optional
backend (Qt, Tk, wgpu) that cannot import on one machine must not change the
fingerprint. What counts, per public module (no path component starting with
``_``):

* its exported names -- ``__all__`` when the module declares it literally,
  else every public top-level ``def``, ``class`` and assignment;
* for a function, its parameters: kind, name and default (annotations are
  left out -- they do not change what a caller may pass);
* for a class, its bases and every public method, property and class-level
  field (a dataclass field is a constructor parameter), nested classes too.

Usage::

    python tools/api_fingerprint.py --record   # after bumping __version__
    python tools/api_fingerprint.py --check    # what the test does
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "emtk"
SNAPSHOT = ROOT / "tests" / "api_fingerprint.json"


def _public(name: str) -> bool:
    return not name.startswith("_")


def public_modules() -> dict[str, Path]:
    """``{dotted name: source path}`` of every public module of the package."""
    found: dict[str, Path] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if all(_public(part) for part in parts):
            found[".".join(parts)] = path
    return found


def _arguments(args: ast.arguments) -> str:
    """A parameter list without annotations: ``(a, b=1, /, *c, d, e=None, **f)``."""
    out: list[str] = []
    positional = [*args.posonlyargs, *args.args]
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for index, (arg, default) in enumerate(zip(positional, defaults)):
        out.append(arg.arg if default is None else f"{arg.arg}={ast.unparse(default)}")
        if args.posonlyargs and index == len(args.posonlyargs) - 1:
            out.append("/")
    if args.vararg is not None:
        out.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        out.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        out.append(arg.arg if default is None else f"{arg.arg}={ast.unparse(default)}")
    if args.kwarg is not None:
        out.append(f"**{args.kwarg.arg}")
    return "(" + ", ".join(out) + ")"


def _decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    return sorted(ast.unparse(item) for item in node.decorator_list)


def _function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    marks = "".join(f"@{name} " for name in _decorators(node))
    return f"{marks}{kind}{_arguments(node.args)}"


#: Dunder methods that are part of how a class is used (construction, calling,
#: containers, context managers, comparison), so their signatures count.
_DUNDERS = {
    "__init__", "__new__", "__call__", "__enter__", "__exit__", "__iter__",
    "__len__", "__getitem__", "__setitem__", "__contains__", "__eq__",
}


def _class(node: ast.ClassDef) -> dict:
    members: dict[str, object] = {}
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _public(item.name) or item.name in _DUNDERS:
                # A property's setter shares the name; keep both, distinguished.
                key = item.name
                if key in members and any(
                    ast.unparse(d).endswith(".setter") for d in item.decorator_list
                ):
                    key = f"{item.name}.setter"
                members[key] = _function(item)
        elif isinstance(item, ast.ClassDef) and _public(item.name):
            members[item.name] = _class(item)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            if _public(item.target.id):
                members[item.target.id] = "field=" if item.value is not None else "field"
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and _public(target.id):
                    members[target.id] = "attribute"
    return {
        "bases": [ast.unparse(base) for base in node.bases]
        + [ast.unparse(keyword) for keyword in node.keywords],
        "decorators": _decorators(node),
        "members": dict(sorted(members.items())),
    }


def _literal_all(tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        targets = (
            node.targets if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            try:
                return [str(name) for name in ast.literal_eval(node.value)]
            except (ValueError, TypeError):
                return None
    return None


def module_api(path: Path) -> dict:
    """The public surface of one module: ``{name: signature}``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    defined: dict[str, object] = {}
    imported: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined[node.name] = _function(node)
        elif isinstance(node, ast.ClassDef):
            defined[node.name] = _class(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        defined.setdefault(name.id, "value")
        elif isinstance(node, ast.ImportFrom):
            source = "." * node.level + (node.module or "")
            for alias in node.names:
                imported[alias.asname or alias.name] = f"from {source} import {alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported[alias.asname or alias.name.split(".")[0]] = f"import {alias.name}"
    exported = _literal_all(tree)
    if exported is None:
        exported = [name for name in defined if _public(name)]
    api: dict[str, object] = {}
    for name in exported:
        if name in defined:
            api[name] = defined[name]
        elif name in imported:
            api[name] = imported[name]
        else:
            api[name] = "dynamic"  # in __all__, made at runtime (a module __getattr__)
    return dict(sorted(api.items()))


def current_api() -> dict:
    """``{module: {name: signature}}`` for every public module."""
    return {name: module_api(path) for name, path in public_modules().items()}


def digest(api: dict) -> str:
    """A stable hash of *api*."""
    text = json.dumps(api, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def package_version() -> str:
    """``__version__`` as written in ``emtk/__init__.py`` (read, not imported)."""
    tree = ast.parse((PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets
        ):
            return str(ast.literal_eval(node.value))
    raise LookupError("emtk/__init__.py declares no __version__")


def project_version() -> str:
    """``[project] version`` in ``pyproject.toml`` -- what pip records for an install."""
    import tomllib  # noqa: PLC0415

    with open(ROOT / "pyproject.toml", "rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def load_snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def changes(old: dict, new: dict) -> list[str]:
    """Human-readable differences between two API maps, one line each."""
    lines: list[str] = []
    for module in sorted(set(old) | set(new)):
        if module not in new:
            lines.append(f"- module {module}")
            continue
        if module not in old:
            lines.append(f"+ module {module}")
            continue
        before, after = old[module], new[module]
        for name in sorted(set(before) | set(after)):
            if name not in after:
                lines.append(f"- {module}.{name}")
            elif name not in before:
                lines.append(f"+ {module}.{name}")
            elif before[name] != after[name]:
                lines.append(f"~ {module}.{name}")
    return lines


def record() -> int:
    """Write the snapshot; refuse when the API changed but ``__version__`` did not."""
    api, version = current_api(), package_version()
    if SNAPSHOT.exists():
        old = load_snapshot()
        if old.get("sha256") != digest(api) and old.get("version") == version:
            sys.stderr.write(
                f"emtk's public API changed but __version__ is still {version}: bump "
                "__version__ in emtk/__init__.py (and [project] version in pyproject.toml) "
                "first, then record.\n" + "\n".join(changes(old.get("api", {}), api)[:40]) + "\n"
            )
            return 1
    payload = {"version": version, "sha256": digest(api), "api": api}
    SNAPSHOT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded emtk {version} API ({len(api)} modules) -> {SNAPSHOT.relative_to(ROOT)}")
    return 0


def check() -> list[str]:
    """Problems with the snapshot (empty when the API, the version and the snapshot agree)."""
    api, version = current_api(), package_version()
    problems: list[str] = []
    if project_version() != version:
        problems.append(
            f"pyproject.toml says version {project_version()} but emtk/__init__.py says "
            f"__version__ = {version!r}; they must name the same release."
        )
    snapshot = load_snapshot()
    if snapshot.get("sha256") == digest(api):
        if snapshot.get("version") != version:
            problems.append(
                f"__version__ is {version} but the snapshot was recorded for "
                f"{snapshot.get('version')} with the same API; re-record: "
                "python tools/api_fingerprint.py --record"
            )
        return problems
    diff = changes(snapshot.get("api", {}), api)
    shown = "\n".join(f"    {line}" for line in diff[:40])
    more = f"\n    ... and {len(diff) - 40} more" if len(diff) > 40 else ""
    if snapshot.get("version") == version:
        problems.append(
            f"emtk's public API changed but __version__ is still {version}.\n"
            "Applications pin emtk by version, so a changed API needs a new one: bump\n"
            "__version__ in emtk/__init__.py and [project] version in pyproject.toml, then\n"
            "re-record the snapshot: python tools/api_fingerprint.py --record\n"
            f"Changes:\n{shown}{more}"
        )
    else:
        problems.append(
            f"__version__ was bumped to {version} but the API snapshot is still the one of "
            f"{snapshot.get('version')}; re-record it: python tools/api_fingerprint.py --record\n"
            f"Changes:\n{shown}{more}"
        )
    return problems


if __name__ == "__main__":
    if "--record" in sys.argv[1:]:
        raise SystemExit(record())
    found = check()
    for problem in found:
        sys.stderr.write(problem + "\n")
    raise SystemExit(1 if found else 0)
