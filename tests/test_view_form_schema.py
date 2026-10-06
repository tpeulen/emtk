"""The form dialect declares every section key its renderers consume."""

import ast
from pathlib import Path

from emtk import view_form


def test_every_literal_renderer_key_is_declared():
    """Adding a read without its dialect entry must fail close to the owner."""
    package = Path(view_form.__file__).parent
    declared = view_form.COMMON_KEYS | frozenset().union(*view_form.SECTION_KEYS.values())
    read = set()
    for file in ("view_form.py", "widgets/view_spec.py"):
        for node in ast.walk(ast.parse((package / file).read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (
                    isinstance(owner, ast.Name)
                    and owner.id == "section"
                    and node.func.attr == "get"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    read.add(node.args[0].value)
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == "section"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                read.add(node.slice.value)
    assert read <= declared, f"undeclared renderer keys: {sorted(read - declared)}"


def test_type_specific_controls_do_not_make_typos_universally_valid():
    """Declarations remain scoped to their reader rather than all section types."""
    assert "kind" in view_form.SECTION_KEYS["value"]
    assert "kind" not in view_form.COMMON_KEYS | view_form.SECTION_KEYS["choice"]
    assert "n_col" not in view_form.COMMON_KEYS | view_form.SECTION_KEYS["info"]
    assert "rebuild_on_change" not in view_form.COMMON_KEYS | view_form.SECTION_KEYS["value"]
    assert "special_text" in view_form.SECTION_KEYS["value"]
    assert "lines" in view_form.SECTION_KEYS["value"]
    assert "columns_source" in view_form.SECTION_KEYS["table"]
