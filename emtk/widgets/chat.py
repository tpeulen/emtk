"""EMTK Chat and conversation widgets.

Provides immediate-mode and retained chat components for agentic AI interactions,
supporting streaming tokens, message bubbles, markdown code block extraction with
copy/insert actions, tool execution badges, and scrolling history.
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Callable
from typing import Any

from .. import im
from ..im_core import Col
from ..painter import Colour


@dataclasses.dataclass
class ChatMessage:
    """A single message in a conversation transcript."""

    role: str  # "user", "assistant", "system", "tool", "error"
    content: str
    timestamp: float = dataclasses.field(default_factory=time.time)
    tool_calls: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    status: str = "complete"  # "streaming", "complete", "error", "pending"
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": self.tool_calls,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            tool_calls=data.get("tool_calls", []),
            status=data.get("status", "complete"),
            metadata=data.get("metadata", {}),
        )


class ChatHistory:
    """Manages chat messages and provides streaming helpers."""

    def __init__(self, max_messages: int = 200) -> None:
        self.messages: list[ChatMessage] = []
        self.max_messages = max_messages
        self.auto_scroll: bool = True

    def add_message(
        self,
        role: str,
        content: str = "",
        status: str = "complete",
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            role=role,
            content=content,
            status=status,
            tool_calls=tool_calls or [],
            metadata=metadata or {},
        )
        self.messages.append(msg)
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        self.auto_scroll = True
        return msg

    def append_chunk(self, chunk: str) -> None:
        if not self.messages or self.messages[-1].role != "assistant":
            self.add_message("assistant", chunk, status="streaming")
        else:
            self.messages[-1].content += chunk
            self.messages[-1].status = "streaming"
        self.auto_scroll = True

    def add_or_update_tool_call(
        self,
        call_id: str,
        name: str,
        arguments: Any = None,
        status: str = "running",
        output: str = "",
    ) -> None:
        if not self.messages or self.messages[-1].role != "assistant":
            self.add_message("assistant", "", status="streaming")

        msg = self.messages[-1]
        for tc in msg.tool_calls:
            if tc.get("id") == call_id:
                if name:
                    tc["name"] = name
                if arguments is not None:
                    tc["arguments"] = arguments
                if status:
                    tc["status"] = status
                if output:
                    tc["output"] = output
                self.auto_scroll = True
                return

        msg.tool_calls.append(
            {
                "id": call_id,
                "name": name,
                "arguments": arguments or {},
                "status": status,
                "output": output,
            }
        )
        self.auto_scroll = True

    def finish_generation(self, status: str = "complete") -> None:
        if self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].status = status

    def clear(self) -> None:
        self.messages.clear()

    def to_list(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.messages]

    def load_list(self, data: list[dict[str, Any]]) -> None:
        self.messages = [ChatMessage.from_dict(d) for d in data if isinstance(d, dict)]
        self.auto_scroll = True


def parse_code_blocks(text: str) -> list[tuple[str, str, str]]:
    """Split markdown text into ('text', content, '') and ('code', content, lang)."""
    blocks: list[tuple[str, str, str]] = []
    pattern = re.compile(r"```([a-zA-Z0-9_\-+]*)\n?(.*?)```", re.DOTALL)
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            prose = text[last_idx:start].strip("\r\n")
            if prose:
                blocks.append(("text", prose, ""))
        lang = match.group(1).strip()
        code = match.group(2).rstrip("\r\n")
        blocks.append(("code", code, lang))
        last_idx = end
    if last_idx < len(text):
        remaining = text[last_idx:].strip("\r\n")
        if remaining:
            blocks.append(("text", remaining, ""))
    return blocks


def draw_chat_transcript(
    history: ChatHistory | list[ChatMessage],
    size: tuple[float, float] = (0.0, 0.0),
    on_insert_code: Callable[[str], None] | None = None,
    on_replace_code: Callable[[str], None] | None = None,
) -> None:
    """Draw the conversation transcript inside an immediate-mode child container."""
    messages = history.messages if isinstance(history, ChatHistory) else history
    avail_w, avail_h = im.get_content_region_avail()[:2]
    w = float(size[0]) if size and size[0] > 0.0 else float(avail_w)
    h = float(size[1]) if size and size[1] > 0.0 else max(100.0, float(avail_h))

    im.begin_child((*im.get_cursor_screen_pos(), w, h))

    if not messages:
        im.dummy(0.0, 16.0)
        im.text_colored((140, 170, 210, 255), "ChiSurf AI Assistant")
        im.dummy(0.0, 4.0)
        im.text_disabled("Ready to assist with scripting, burst analysis,")
        im.text_disabled("and ChiSurf algorithms.")
        im.dummy(0.0, 8.0)
        im.text_disabled("Type a message below and click Send.")
        im.end_child()
        return

    for idx, msg in enumerate(messages):
        im.push_id(f"msg_{idx}")

        # Sender header badge
        role = msg.role.lower()
        if role == "user":
            im.text_colored((110, 190, 255, 255), "> You")
        elif role == "assistant":
            im.text_colored((130, 220, 140, 255), "Assistant")
        elif role == "tool":
            im.text_colored((235, 185, 95, 255), "[Tool]")
        elif role == "error":
            im.text_colored((245, 110, 110, 255), "[Error]")
        else:
            im.text_colored((180, 180, 180, 255), f"[{msg.role.capitalize()}]")

        # Message body
        if msg.content:
            blocks = parse_code_blocks(msg.content)
            for b_idx, (b_type, b_content, b_lang) in enumerate(blocks):
                if b_type == "text":
                    im.text_wrapped(b_content)
                elif b_type == "code":
                    im.dummy(0.0, 3.0)
                    lang_tag = f" [{b_lang}]" if b_lang else ""
                    im.text_disabled(f"Code{lang_tag}")
                    im.same_line()
                    if im.small_button(f"Copy##c_{b_idx}"):
                        try:
                            from ..clipboard import set_clipboard_text
                            set_clipboard_text(b_content)
                        except Exception:
                            pass
                    im.set_item_tooltip("Copy this code block to the clipboard.")
                    if on_insert_code:
                        im.same_line()
                        if im.small_button(f"Insert##ins_{b_idx}"):
                            on_insert_code(b_content)
                        im.set_item_tooltip("Insert this code at the active editor cursor.")
                    if on_replace_code:
                        im.same_line()
                        if im.small_button(f"Replace##rep_{b_idx}"):
                            on_replace_code(b_content)
                        im.set_item_tooltip("Replace the selected editor text with this code.")

                    # Code box display
                    im.push_style_color(Col.FRAME_BG, (20, 22, 28, 255))
                    im.text_wrapped(b_content)
                    im.pop_style_color()
                    im.dummy(0.0, 3.0)

        # Tool calls attached to the message
        if msg.tool_calls:
            for t_idx, tc in enumerate(msg.tool_calls):
                im.push_id(f"tc_{t_idx}")
                t_name = tc.get("name", "tool")
                t_status = tc.get("status", "running")
                status_icon = "..." if t_status == "running" else ("[ok]" if t_status == "success" else "[x]")
                
                header_title = f"{status_icon} Tool: {t_name}"
                if im.collapsing_header(header_title):
                    args_str = str(tc.get("arguments", ""))
                    if args_str:
                        im.text_disabled("Arguments:")
                        im.text_wrapped(args_str)
                    output_str = str(tc.get("output", ""))
                    if output_str:
                        im.text_disabled("Output:")
                        im.text_wrapped(output_str)
                im.pop_id()

        if msg.status == "streaming":
            im.text_colored((130, 215, 140, 255), "... Thinking...")

        im.dummy(0.0, 4.0)
        im.separator()
        im.dummy(0.0, 4.0)
        im.pop_id()

    if isinstance(history, ChatHistory) and history.auto_scroll:
        im.set_scroll_here_y(1.0)
        history.auto_scroll = False

    im.end_child()


def draw_chat_input_bar(
    prompt_text: str,
    is_generating: bool = False,
    on_send: Callable[[str], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
    on_clear: Callable[[], None] | None = None,
    input_height: float = 56.0,
) -> tuple[str, bool]:
    """Draw the chat input box and Send / Stop / Clear buttons.

    Returns (new_prompt_text, send_requested).
    """
    avail_w = im.get_content_region_avail()[0]
    changed, new_prompt = im.input_text_multiline("##chat_input", prompt_text, size=(avail_w, input_height))
    im.set_item_tooltip("Write a message for the assistant.")
    
    send_requested = False
    
    im.dummy(0.0, 2.0)
    
    # Send / Stop button
    if is_generating:
        im.push_style_color(Col.BUTTON, (180, 50, 50, 255))
        im.push_style_color(Col.BUTTON_HOVERED, (210, 70, 70, 255))
        if im.button("■ Stop", (80.0, 26.0)):
            if on_cancel:
                on_cancel()
        im.set_item_tooltip("Stop the current assistant response.")
        im.pop_style_color(2)
    else:
        can_send = bool(new_prompt.strip())
        im.push_style_color(Col.BUTTON, (46, 140, 67, 255) if can_send else (60, 65, 75, 255))
        im.push_style_color(Col.BUTTON_HOVERED, (56, 160, 77, 255) if can_send else (60, 65, 75, 255))
        if im.button("▶ Send", (90.0, 26.0)) and can_send:
            send_requested = True
            if on_send:
                on_send(new_prompt)
            new_prompt = ""
        im.set_item_tooltip("Send this message to the assistant." if can_send else "Write a message before sending.")
        im.pop_style_color(2)

    im.same_line()
    if im.button("Clear", (70.0, 26.0)):
        if on_clear:
            on_clear()
    im.set_item_tooltip("Clear the conversation history.")

    return new_prompt, send_requested
