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
