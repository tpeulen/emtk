"""Text-bearing declarations cover the strings the actual form reader displays."""

import ast
from pathlib import Path
from types import SimpleNamespace

import emtk
import pytest
from emtk import im_widgets, view_form
from emtk.testing import RecordingPainter


def test_text_keys_are_exported_immutable_and_exclude_binding_identifiers():
    """Consumers can import the vocabulary without translating model identities."""
    assert "TEXT_KEYS" in view_form.__all__
    assert isinstance(view_form.TEXT_KEYS, frozenset)
    assert {
        "label",
        "title",
        "description",
        "text",
        "hint",
        "placeholder",
        "suffix",
        "tooltip",
        "units",
        "descriptions",
        "labels",
        "caption",
        "special_text",
        "options",
        "choices",
    } <= view_form.TEXT_KEYS
    assert (
        not {"attr", "target", "key", "source", "text_source", "call", "action"}
        & view_form.TEXT_KEYS
    )


def test_textual_renderer_reads_are_in_the_public_vocabulary():
    """Literal user-text reads in the renderer cannot escape the extraction contract."""
    tree = ast.parse(Path(view_form.__file__).read_text())
    reads = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"section", "item", "child"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            reads.add(node.args[0].value)
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"section", "item", "child"}
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            reads.add(node.slice.value)
    # These names describe displayed content; source/call/key names are bindings.
    textual = {
        key
        for key in reads
        if key
        in {
            "label",
            "title",
            "description",
            "text",
            "labels",
            "descriptions",
            "special_text",
            "options",
            "choices",
            "units",
            "suffix",
            "hint",
            "placeholder",
            "tooltip",
            "caption",
        }
        or key.endswith(("_label", "_title", "_description", "_caption", "_tooltip"))
    }
    assert {"special_text", "placeholder", "descriptions", "options", "choices"} <= textual
    assert textual <= view_form.TEXT_KEYS, (
        f"unextractable renderer text keys: {sorted(textual - view_form.TEXT_KEYS)}"
    )


@pytest.mark.parametrize("choice_key", ["options", "choices"])
def test_actual_displayed_strings_and_tooltips_are_collectable(choice_key, monkeypatch):
    """Labels, fallback choices and numeric sentinels remain discoverable by key."""
    tips = []
    real_tooltip = im_widgets.set_item_tooltip

    def record_tooltip(text):
        tips.append(text)
        real_tooltip(text)

    monkeypatch.setattr(im_widgets, "set_item_tooltip", record_tooltip)
    spec = {
        "sections": [
            {
                "type": "panel",
                "title": "Acquisition timing",
                "sections": [
                    {
                        "type": "value",
                        "attr": "clock",
                        "label": "Clock",
                        "kind": "float",
                        "minimum": 0,
                        "special_text": "Use measured header",
                        "suffix": " ns",
                        "description": "Choose a physical clock.",
                    },
                    {
                        "type": "choice",
                        "attr": "mode",
                        "label": "Analysis mode",
                        choice_key: ["Pooled photons", "Per burst"],
                        "style": "radio_list",
                        "descriptions": ["Combine all counts.", "Keep each burst separate."],
                    },
                    {
                        "type": "value",
                        "attr": "filename",
                        "label": "Measurement",
                        "placeholder": "Drop a photon file",
                        "description": "Read an existing measurement.",
                    },
                    {"type": "info", "text": "The clock comes from the measurement."},
                    {
                        "type": "button_row",
                        "buttons": [
                            {
                                "label": "Apply settings",
                                "action": "apply",
                                "description": "Use this definition.",
                            }
                        ],
                    },
                ],
            },
        ]
    }
    collected = set()

    def collect(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in view_form.TEXT_KEYS:
                    if isinstance(value, str):
                        collected.add(value)
                    elif isinstance(value, list):
                        collected.update(item for item in value if isinstance(item, str))
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(spec)
    model = SimpleNamespace(clock=0.0, mode="Pooled photons", filename="", apply=lambda: None)
    painter = RecordingPainter()
    with emtk.frame(painter, (0, 0, 640, 480)):
        emtk.begin("form", (0, 0, 640, 480))
        view_form.draw_form(spec, model, view_form.FormState())
        emtk.end()
    for expected in [
        "Acquisition timing",
        "Clock",
        "Analysis mode",
        "Pooled photons",
        "Per burst",
        "Use measured header",
        "Measurement",
        "Drop a photon file",
        "The clock comes from the measurement.",
        "Apply settings",
    ]:
        assert any(expected in text for text in painter.strings), expected
        assert expected in collected, expected
    assert set(tips) <= collected
    assert {"Combine all counts.", "Keep each burst separate.", "Use this definition."} <= set(tips)
    assert " ns" in collected
    assert view_form.format_value(2.5, {"kind": "float", "suffix": " ns"}).endswith(" ns")
