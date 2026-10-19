"""docs/data-model-and-api.md §6.2: a task's transcripts and one transcript's messages (030)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TranscriptOut(BaseModel):
    id: int
    run_id: int
    round: int | None
    agent_type: str | None
    name: str | None
    model: str | None
    turns: int
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    started_at: str | None
    ended_at: str | None


class TextBlock(BaseModel):
    type: Literal["text"]
    text_html: str  # rendered with raw HTML off (docs/MVP.md §4.5)


class ThinkingBlock(BaseModel):
    type: Literal["thinking"]
    text: str


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"]
    name: str
    input: str  # pretty-printed JSON


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"]
    text: str
    is_error: bool
    truncated: bool  # cut at 4096 characters; ?full=1 sends it whole


Block = Annotated[TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock, Field(discriminator="type")]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    at: str | None
    blocks: list[Block]


class TranscriptDetail(TranscriptOut):
    task_id: int
    messages: list[Message]
