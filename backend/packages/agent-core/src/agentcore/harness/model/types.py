"""Request and result of one model call, and the port a model adapter implements."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from agentcore.messages import Message

ReasoningEffort = Literal["off", "low", "medium", "high"]
"""How hard the model thinks before answering; ``off`` disables thinking where the provider allows it."""


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
    reasoning: ReasoningEffort | None = None
    """None leaves the provider's default."""


StopReason = Literal["end", "tool_use", "max_tokens", "other"]


class AssistantResult(BaseModel):
    message: Message
    stop_reason: StopReason


class StreamSink(Protocol):
    """Receives a reply while it is generated; the whole message still comes back from ``complete``."""

    def text(self, delta: str) -> None: ...

    def thinking(self, delta: str) -> None: ...


class ModelClient(Protocol):
    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult: ...
