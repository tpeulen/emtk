"""Generate ``emtk/implot3d_meshes.py`` from ImPlot3D's ``implot3d_meshes.cpp``.

The bundled meshes are data, and data is extracted rather than retyped: a cube,
an icosphere and the rubber duck are 2,700 numbers, and one mistyped index is a
hole in a mesh nobody would think to look for. Run::

    python tools/port_implot3d_meshes.py ~/dev/chisurf/junk/implot3d/implot3d_meshes.cpp

and the module is rewritten in place. ``tests/test_implot3d.py`` checks the
counts against the ``*_VTX_COUNT`` / ``*_IDX_COUNT`` constants of the header
and that every mesh is closed, so a regeneration that lost a row fails there.

The values are kept as the C++ spells them (``-0.525731f`` becomes
``-0.525731``): the reference stores them in ``double`` fields initialised from
``float`` literals, and the six decimal digits written in the source are what a
reader can check.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "emtk" / "implot3d_meshes.py"

HEADER = '''"""The meshes ImPlot3D bundles: a cube, an icosphere and a rubber duck.

Generated from ``implot3d_meshes.cpp`` by ``tools/port_implot3d_meshes.py`` --
do not edit by hand; regenerate. The names and counts are the reference's
(``ImPlot3D::cube_vtx``, ``CUBE_VTX_COUNT`` ...), so a ported call reads::

    implot3d.plot_mesh("Duck", DUCK_VTX, DUCK_IDX)

Vertices are ``(x, y, z)`` tuples; indices are a flat tuple, three per
triangle.

The duck is "Rubber Duck" by Poly by Google, CC-BY, via Poly Pizza -- the
attribution the reference carries, carried here with it.
"""
from __future__ import annotations

__all__ = [
    "CUBE_VTX_COUNT", "CUBE_IDX_COUNT", "CUBE_VTX", "CUBE_IDX",
    "SPHERE_VTX_COUNT", "SPHERE_IDX_COUNT", "SPHERE_VTX", "SPHERE_IDX",
    "DUCK_VTX_COUNT", "DUCK_IDX_COUNT", "DUCK_VTX", "DUCK_IDX",
    "cube_vtx", "cube_idx", "sphere_vtx", "sphere_idx", "duck_vtx", "duck_idx",
]
'''

_FLOAT = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?f?"


def _block(source: str, name: str) -> str:
    match = re.search(name + r"\[[A-Z_]+\]\s*=\s*\{(.*?)\};", source, re.S)
    if match is None:
        raise SystemExit(f"{name} not found")
    body = match.group(1)
    return re.sub(r"//[^\n]*", "", body)


def _vertices(source: str, name: str) -> list[tuple[float, float, float]]:
    out = []
    for triple in re.findall(r"\{([^{}]*)\}", _block(source, name)):
        vals = [float(v.rstrip("f")) for v in re.findall(_FLOAT, triple)]
        assert len(vals) == 3, triple
        out.append(tuple(vals))
    return out


def _indices(source: str, name: str) -> list[int]:
    return [int(v) for v in re.findall(r"\d+", _block(source, name))]


def _format_vertices(name: str, vtx) -> str:
    rows = ",\n".join(f"    ({x!r}, {y!r}, {z!r})" for x, y, z in vtx)
    return f"{name} = (\n{rows},\n)\n"


def _format_indices(name: str, idx) -> str:
    lines = []
    for at in range(0, len(idx), 24):
        lines.append("    " + ", ".join(str(i) for i in idx[at:at + 24]) + ",")
    return f"{name} = (\n" + "\n".join(lines) + "\n)\n"


def main(path: str) -> None:
    source = pathlib.Path(path).expanduser().read_text()
    parts = [HEADER]
    for mesh in ("cube", "sphere", "duck"):
        vtx = _vertices(source, f"{mesh}_vtx")
        idx = _indices(source, f"{mesh}_idx")
        upper = mesh.upper()
        parts.append(f"\n# {'-' * 75} #\n# {mesh}\n# {'-' * 75} #\n")
        parts.append(f"{upper}_VTX_COUNT = {len(vtx)}\n{upper}_IDX_COUNT = {len(idx)}\n\n")
        parts.append(_format_vertices(f"{upper}_VTX", vtx))
        parts.append("\n")
        parts.append(_format_indices(f"{upper}_IDX", idx))
    parts.append(
        "\n#: The reference's lower-case spellings, for a line-by-line port.\n"
        "cube_vtx, cube_idx = CUBE_VTX, CUBE_IDX\n"
        "sphere_vtx, sphere_idx = SPHERE_VTX, SPHERE_IDX\n"
        "duck_vtx, duck_idx = DUCK_VTX, DUCK_IDX\n"
    )
    OUT.write_text("".join(parts))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "~/dev/chisurf/junk/implot3d/implot3d_meshes.cpp")
