"""Request and result of one model call, and the port a model adapter implements."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from agentcore.messages import Message


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    """JSON Schema of the arguments object."""


class LlmRequest(BaseModel):
    system: str
    messages: list[Message]
    tools: list[ToolSchema] = Field(default_factory=list[ToolSchema])
    max_output_tokens: int = 2048


StopReason = Literal["end", "tool_use", "max_tokens", "other"]


class AssistantResult(BaseModel):
    message: Message
    stop_reason: StopReason


class ModelClient(Protocol):
    async def complete(self, request: LlmRequest) -> AssistantResult: ...
