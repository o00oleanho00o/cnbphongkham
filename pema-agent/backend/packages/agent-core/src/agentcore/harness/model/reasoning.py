"""One reasoning-effort scale for every provider, mapped to each provider's own parameters.

DeepSeek (OpenAI format) thinks by default at effort ``high``; ``off`` sends ``thinking: disabled``, which is
much faster for simple turns. Anthropic uses adaptive thinking with an effort level (as zalo-agent does).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from agentcore.harness.model.types import ReasoningEffort

OpenAIDialect = Literal["openai", "deepseek"]
ThinkingEffort = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class OpenAIReasoning:
    effort: ThinkingEffort | None = None
    """``reasoning_effort``; None leaves it out."""
    extra_body: dict[str, Any] | None = None


def openai_reasoning(effort: ReasoningEffort | None, dialect: OpenAIDialect) -> OpenAIReasoning:
    if effort is None:
        return OpenAIReasoning()
    if dialect == "deepseek":
        if effort == "off":
            return OpenAIReasoning(extra_body={"thinking": {"type": "disabled"}})
        return OpenAIReasoning(effort=effort, extra_body={"thinking": {"type": "enabled"}})
    return OpenAIReasoning() if effort == "off" else OpenAIReasoning(effort=effort)


@dataclass(frozen=True, slots=True)
class AnthropicReasoning:
    thinking: Literal["adaptive", "disabled"] | None = None
    """None leaves thinking out of the request."""
    effort: ThinkingEffort | None = None


def anthropic_reasoning(effort: ReasoningEffort | None) -> AnthropicReasoning:
    if effort is None:
        return AnthropicReasoning()
    if effort == "off":
        return AnthropicReasoning(thinking="disabled")
    return AnthropicReasoning(thinking="adaptive", effort=effort)
