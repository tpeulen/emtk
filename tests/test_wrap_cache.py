"""Wrapped text: the same lines as measuring every candidate whole, without its quadratic cost.

Found by chisurf's real-use QA matrix: the help browser's bibliography page re-wrapped about
400 paragraphs per frame, measuring every candidate line whole, and spent 4.5 s per frame.
"""
from __future__ import annotations

import random
import time
from types import SimpleNamespace

import pytest

from emtk import im_widgets
from emtk.testing import MetricPainter


def _reference(p, s, width):
    """The wrapping rules as they were: every candidate measured whole."""
    lines = []
    for paragraph in str(s).split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip() if line else word
            if line and p.text_width(candidate) > width:
                lines.append(line)
                line = ""
            if p.text_width(word) > width:
                for character in word:
                    if line and p.text_width(line + character) > width:
                        lines.append(line)
                        line = ""
                    line += character
            else:
                line = f"{line} {word}".strip() if line else word
        if line:
            lines.append(line)
    return lines


@pytest.mark.parametrize("font", [None, ("sans", 15.0), ("serif", 19.0)])
def test_wrapping_breaks_exactly_where_measuring_every_candidate_did(font):
    rng = random.Random(7)
    vocabulary = ["a", "of", "the", "Förster", "fluorescence", "W", "iiii", "doi:10.1021/jp057257+",
                  "https://example.org/a/very/long/path/that/never/fits/anywhere", "–", "κ²", "MMMM"]
    painter = MetricPainter()
    if font:
        painter.set_font(*font)
    ctx = SimpleNamespace(p=painter)
    for _ in range(200):
        text = " ".join(rng.choice(vocabulary) for _ in range(rng.randint(1, 60)))
        if rng.random() < 0.2:
            text += "\n\n" + text[::-1]
        width = rng.uniform(20.0, 400.0)
        assert im_widgets._wrap(ctx, text, width) == _reference(painter, text, width), (text, width)


def test_a_paragraph_rewrapped_every_frame_is_not_measured_again():
    painter = MetricPainter()
    painter.set_font("sans", 15.0)
    ctx = SimpleNamespace(p=painter)
    text = " ".join(["fluorescence lifetime of the donor in the presence of acceptor"] * 40)
    first = im_widgets._wrapped_lines(ctx, text, 300.0)
    start = time.perf_counter()
    for _ in range(200):
        again = im_widgets._wrapped_lines(ctx, text, 300.0)
    assert again == first
    assert time.perf_counter() - start < 0.05
    # another font is another key: wrapped afresh
    other = MetricPainter()
    other.set_font("sans", 30.0)
    assert im_widgets._wrapped_lines(SimpleNamespace(p=other), text, 300.0) != first
