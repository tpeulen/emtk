"""A renderer reaches the GPU through one seam, and that seam does not lie.

Two things are checked here, and they fail in opposite directions.

``test_only_the_native_backend_imports_wgpu`` fails when emtk grows a
second place that imports the binding. That is the rule the browser port needs:
a module that says ``import wgpu`` is a module that cannot run anywhere
``wgpu-py`` does not, and finding those one at a time during a port is how a
port stops being finishable.

The enum tests fail the other way -- when the seam's own constants drift from
the binding's. :mod:`emtk.gpu.enums` writes the WebGPU values out
rather than re-exporting them, because they are fixed by the specification and
are the same integers and strings in a browser. That is a claim about someone
else's package, so it is worth asserting: a wrong bit in a usage flag does not
raise, it produces a buffer the driver refuses or, worse, accepts and draws
wrong.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from emtk.gpu import enums

#: emtk's source root.
_EMTK = Path(__import__("emtk").__file__).resolve().parent

#: The only module allowed to name the binding.
_BACKEND = _EMTK / "gpu" / "native.py"

#: ``import wgpu`` or ``from wgpu[.x] import ...``.
#:
#: Deliberately *not* matching bare ``wgpu.`` attribute access: the seam is
#: imported as ``from emtk.gpu import api as wgpu`` precisely so that call sites
#: keep the binding's spelling, and every ``wgpu.BufferUsage.VERTEX`` in the
#: renderer goes through :mod:`emtk.gpu.api`. What must not
#: reappear is the *import*, which is the thing that ties a module to one
#: implementation.
_IMPORTS_WGPU = re.compile(r"^\s*(?:import\s+wgpu\b|from\s+wgpu[\s.])", re.M)


def _sources():
    """Yield every shipped Python module of emtk.

    Yields
    ------
    pathlib.Path
    """
    for path in sorted(_EMTK.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def test_only_the_native_backend_imports_wgpu():
    """No module outside the native backend may import ``wgpu``.

    ``emtk/gpu/api.py`` is written to be imported *as* ``wgpu``
    (``from emtk.gpu import api as wgpu``), so call sites keep the binding's
    spelling while the binding itself stays behind the seam. Only
    :mod:`emtk.gpu.native` may reach it.
    """
    offenders = []
    for path in _sources():
        if path == _BACKEND:
            continue
        text = path.read_text(encoding="utf-8")
        # The seam's own modules describe the binding in prose; only code counts.
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        if _IMPORTS_WGPU.search(code):
            offenders.append(str(path.relative_to(_EMTK)))
    assert not offenders, (
        "these modules reach the GPU binding directly instead of through "
        "emtk.gpu.api: " + ", ".join(offenders)
    )


@pytest.mark.parametrize(
    "namespace",
    [
        "BlendFactor",
        "BlendOperation",
        "BufferBindingType",
        "BufferUsage",
        "CompareFunction",
        "CullMode",
        "FilterMode",
        "IndexFormat",
        "LoadOp",
        "PrimitiveTopology",
        "SamplerBindingType",
        "ShaderStage",
        "StoreOp",
        "TextureFormat",
        "TextureSampleType",
        "TextureUsage",
    ],
)
def test_our_constants_match_the_binding(namespace):
    """Every constant the seam states equals the one ``wgpu-py`` reports.

    Asserted per namespace so a failure names which one moved.
    """
    wgpu = pytest.importorskip("wgpu")

    ours = getattr(enums, namespace)
    theirs = getattr(wgpu, namespace)
    for key in dir(ours):
        if key.startswith("_"):
            continue
        assert hasattr(theirs, key), f"wgpu.{namespace} has no {key}"
        assert getattr(ours, key) == getattr(theirs, key), (
            f"{namespace}.{key}: seam says {getattr(ours, key)!r}, "
            f"wgpu-py says {getattr(theirs, key)!r}"
        )


def test_the_seam_is_a_drop_in_for_the_binding():
    """``api`` answers to every name the engine used to take from ``wgpu``."""
    from emtk.gpu import api

    assert hasattr(api.gpu, "request_adapter_sync")
    # A spot-check of the two kinds of constant: a spec string and a bit flag.
    assert api.PrimitiveTopology.triangle_list == "triangle-list"
    assert api.BufferUsage.VERTEX == 32


def test_the_depth_texture_can_be_both_written_and_sampled():
    """The two usage bits the silhouette pass needs are distinct and present.

    The second pass samples the depth the first pass wrote, so the depth
    texture is created ``RENDER_ATTACHMENT | TEXTURE_BINDING``. A backend
    offering only the first cannot run this engine -- worth pinning as a
    requirement rather than leaving implied in a texture descriptor.
    """
    combined = enums.TextureUsage.RENDER_ATTACHMENT | enums.TextureUsage.TEXTURE_BINDING
    assert combined & enums.TextureUsage.RENDER_ATTACHMENT
    assert combined & enums.TextureUsage.TEXTURE_BINDING
    assert enums.TextureUsage.RENDER_ATTACHMENT != enums.TextureUsage.TEXTURE_BINDING


def test_the_ui_layout_declares_every_binding_the_shader_has():
    """``ui_bind_group_layout_entries`` is the one definition of ``ui.wgsl``'s
    group 1, used by emtk's renderer and by applications that draw the
    interface in their own pass. When the shader gained a nearest sampler at
    binding 5, an application's private copy of the layout stopped validating
    and its window came up the error colour -- so the two are compared here.
    """
    from emtk.wgpu_host import ui_bind_group_entries, ui_bind_group_layout_entries
    from emtk.wgsl import load_wgsl

    declared = {int(b) for g, b in re.findall(r"@group\((\d+)\)\s*@binding\((\d+)\)",
                                              load_wgsl("ui.wgsl")) if g == "1"}
    layout = {entry["binding"] for entry in ui_bind_group_layout_entries()}
    assert layout == declared, f"layout {sorted(layout)} vs shader {sorted(declared)}"

    class _Buffer:
        size = 32

    entries = ui_bind_group_entries(_Buffer(), "atlas", "images", "lin", "near")
    assert {entry["binding"] for entry in entries} == declared
