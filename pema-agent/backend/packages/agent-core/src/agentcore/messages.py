"""Conversation messages in one provider-neutral shape. Model adapters convert to and from each provider."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    text: str
    signature: str | None = None
    """Providers that sign their reasoning need the signature sent back unchanged on the next call."""


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict[str, Any])
    raw_args: str | None = None
    """The model's argument text when it was not a JSON object; ``args`` is then empty."""
    provider_meta: dict[str, Any] = Field(default_factory=dict[str, Any])


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    name: str
    content: str
    is_error: bool = False


Block = Annotated[TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock, Field(discriminator="type")]

Role = Literal["user", "assistant", "tool"]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class Message(BaseModel):
    role: Role
    blocks: list[Block]
    usage: Usage | None = None

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role="user", blocks=[TextBlock(text=text)])

    def text(self) -> str:
        return "".join(block.text for block in self.blocks if isinstance(block, TextBlock))

    def tool_uses(self) -> list[ToolUseBlock]:
        return [block for block in self.blocks if isinstance(block, ToolUseBlock)]
