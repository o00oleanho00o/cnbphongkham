"""What a tool is: a name, a pydantic model for its arguments and an async handler."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel

from agentcore.harness.model.types import ToolSchema
from agentcore.tenancy import DEFAULT_TENANT

# The strictest name rule among the providers we target (OpenAI function names).
TOOL_NAME_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(frozen=True, slots=True)
class ToolContext:
    session_id: str
    tenant_id: str = DEFAULT_TENANT
    user_id: str | None = None
    """The person the session talks to, set by the caller; a tool never takes it from the model."""
    channel: str | None = None
    """The channel the turn came in on (``http``, ``cli``, a plugin's channel), set by the caller."""


class ToolOutput(BaseModel):
    text: str
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class ToolSpec[ArgsT: BaseModel]:
    name: str
    description: str
    args_model: type[ArgsT]
    handler: Callable[[ArgsT, ToolContext], Awaitable[ToolOutput]]
    timeout_s: float = 15.0
    max_result_chars: int = 8_000
    read_only: bool = False
    """Changes nothing, so it may run at the same time as other read-only calls."""
    prompt_args: tuple[str, ...] = ()
    """Arguments whose text is stored and later enters the system prompt; guards scan them before the call."""

    def __post_init__(self) -> None:
        if not TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"Invalid tool name {self.name!r}: use 1-64 letters, digits, '_' or '-'")
        if self.timeout_s <= 0:
            raise ValueError(f"Tool {self.name}: timeout_s must be positive")
        if self.max_result_chars <= 0:
            raise ValueError(f"Tool {self.name}: max_result_chars must be positive")
        unknown = [arg for arg in self.prompt_args if arg not in self.args_model.model_fields]
        if unknown:
            raise ValueError(f"Tool {self.name}: prompt_args not in its arguments: {', '.join(unknown)}")

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name, description=self.description, parameters=self.args_model.model_json_schema()
        )
