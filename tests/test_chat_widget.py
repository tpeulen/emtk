"""Tests for the EMTK chat widget components."""

from __future__ import annotations

import emtk
from emtk import im
from emtk.testing import RecordingPainter
from emtk.widgets.chat import (
    ChatHistory,
    ChatMessage,
    draw_chat_input_bar,
    draw_chat_transcript,
    parse_code_blocks,
)


def test_parse_code_blocks():
    text = "Here is some code:\n```python\nx = 42\nprint(x)\n```\nAnd done."
    blocks = parse_code_blocks(text)
    assert len(blocks) == 3
    assert blocks[0] == ("text", "Here is some code:", "")
    assert blocks[1] == ("code", "x = 42\nprint(x)", "python")
    assert blocks[2] == ("text", "And done.", "")


def test_chat_history_streaming():
    history = ChatHistory()
    history.add_message("user", "Hello assistant!")
    assert len(history.messages) == 1
    assert history.messages[0].role == "user"

    history.append_chunk("Hello")
    assert len(history.messages) == 2
    assert history.messages[1].role == "assistant"
    assert history.messages[1].status == "streaming"
    assert history.messages[1].content == "Hello"

    history.append_chunk(" world!")
    assert len(history.messages) == 2
    assert history.messages[1].content == "Hello world!"

    history.finish_generation("complete")
    assert history.messages[1].status == "complete"


def test_chat_transcript_and_input_rendering():
    history = ChatHistory()
    history.add_message("user", "Can you show me python code?")
    history.add_message(
        "assistant",
        "Sure, here you go:\n```python\ndef test():\n    return True\n```\nLet me know!",
    )
    history.add_or_update_tool_call("tc_1", "calculate", {"x": 10}, "success", "20")

    p = RecordingPainter()
    inserted: list[str] = []

    with im.frame(p, (0, 0, 400, 500)):
        im.begin("Chat Panel")
        draw_chat_transcript(history, size=(380.0, 350.0), on_insert_code=lambda c: inserted.append(c))
        prompt, send = draw_chat_input_bar("Test prompt")
        im.end()

    assert prompt == "Test prompt"
    assert not send
    assert len(p.texts) > 0


def _transcript_frames(history, on_link, click_on=None, size=(480.0, 300.0)):
    """Draw a transcript twice; with ``click_on`` press and release on that drawn text."""
    io, storage = emtk.IO(), {}
    last = RecordingPainter()
    for frame in range(5):
        io.mouse_clicked[0] = io.mouse_released[0] = False
        io.mouse_down[0] = False
        if click_on is not None and frame >= 2:
            hit = next(t for t in last.texts if click_on in t[5])
            io.mouse_pos = (hit[0] + 12.0, hit[1] + 6.0)
            if frame == 3:
                io.mouse_clicked[0] = io.mouse_down[0] = True
            elif frame == 4:
                io.mouse_released[0] = True
        last = RecordingPainter()
        with emtk.frame(last, (0, 0, 500, 400), io=io, storage=storage):
            im.begin("Chat Panel")
            draw_chat_transcript(history, size=size, on_link=on_link)
            im.end()
    return last


def test_chat_transcript_renders_markdown_not_raw_text():
    """``**bold**`` and ``[title](target)`` must not reach the screen literally."""
    history = ChatHistory()
    history.add_message("assistant", "See **the page** and [Accurate FRET](docs/a.md).")
    painter = _transcript_frames(history, lambda url: None)
    drawn = " ".join(t[5] for t in painter.texts)
    assert "**" not in drawn
    assert "](" not in drawn
    assert "Accurate" in drawn and "FRET" in drawn
    assert drawn.count("Accurate") == 1


def test_chat_transcript_link_click_routes_to_on_link():
    history = ChatHistory()
    history.add_message(
        "assistant",
        "Answer.\n\n**Cited Documentation Pages:**\n- [Accurate FRET](docs/a.md#The four factors)",
    )
    clicked: list[str] = []
    _transcript_frames(history, clicked.append, click_on="FRET")
    assert clicked == ["docs/a.md#The four factors"]
