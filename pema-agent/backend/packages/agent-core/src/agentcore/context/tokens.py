"""Token estimates from character counts.

No tokenizer: every provider counts differently and the estimate only decides when to compact. Three
characters per token is on the safe side for Vietnamese and other non-English text.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from agentcore.harness.model.types import LlmRequest, ToolSchema
from agentcore.messages import Block, Message, TextBlock, ThinkingBlock, ToolUseBlock

DEFAULT_CHARS_PER_TOKEN: Final = 3.0
MESSAGE_OVERHEAD_TOKENS: Final = 4
"""Role and framing tokens a provider adds to every message."""


@dataclass(frozen=True, slots=True)
class TokenEstimator:
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN

    def __post_init__(self) -> None:
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")

    def text(self, text: str) -> int:
        return math.ceil(len(text) / self.chars_per_token)

    def message(self, message: Message) -> int:
        return MESSAGE_OVERHEAD_TOKENS + sum(self.text(_block_text(block)) for block in message.blocks)

    def messages(self, messages: Iterable[Message]) -> int:
        return sum(self.message(message) for message in messages)

    def tools(self, tools: Iterable[ToolSchema]) -> int:
        return sum(
            self.text(f"{t.name} {t.description} {json.dumps(t.parameters, ensure_ascii=False)}")
            for t in tools
        )

    def request(self, request: LlmRequest) -> int:
        return self.text(request.system) + self.messages(request.messages) + self.tools(request.tools)


def _block_text(block: Block) -> str:
    if isinstance(block, TextBlock | ThinkingBlock):
        return block.text
    if isinstance(block, ToolUseBlock):
        args = block.raw_args if block.raw_args is not None else json.dumps(block.args, ensure_ascii=False)
        return f"{block.name} {args}"
    return f"{block.name} {block.content}"
