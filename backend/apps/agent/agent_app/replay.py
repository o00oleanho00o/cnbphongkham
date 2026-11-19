"""Replays a recorded cassette through the real agent and writes what happened as plain text.

The text lists each turn: the user's words, the assistant's words, every tool call with its arguments and
result, how the turn stopped, and the kinds of its trace events. Times, dates and ids change from run to run
and are masked, so the text can be compared with an expected file in a test that needs no API key.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from agent_app.profile import Profile
from agent_app.runtime import build_runtime
from agentcore import (
    InMemoryTracer,
    Message,
    ModelError,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    TurnResult,
    run_turn,
)
from agentcore.clock import WEEKDAYS
from agentcore.harness.model.replay import Cassette, ReplayModel

SESSION: Final = "replay"
USER: Final = "cli-user"
CHANNEL: Final = "cli"
MASKS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?"), "<datetime>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<date>"),
    (re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"), "<time>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<id>"),
    (re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b"), "<weekday>"),
)


@dataclass(frozen=True, slots=True)
class Replayed:
    transcript: str
    calls_used: int


async def replay(cassette_path: Path, profile: Profile) -> Replayed:
    """Runs the cassette's turns as ``agent chat`` ran them when recording; a retry pause takes no time."""
    cassette = Cassette.load(cassette_path)
    model = ReplayModel(cassette)
    runtime = build_runtime(profile, fake=True, env={}, db=None, model_wrapper=lambda _: model)
    tracer = runtime.tracer
    lines: list[str] = []

    async def no_wait(seconds: float) -> None:
        return None

    try:
        for number, text in enumerate(cassette.turns, start=1):
            agent = runtime.agent
            lines.append(f"== turn {number} ==")
            try:
                result = await run_turn(
                    session_id=SESSION,
                    user_text=text,
                    prompt=agent.prompt,
                    model=agent.model,
                    tools=agent.tools,
                    store=runtime.store,
                    policy=replace(agent.policy, max_turn_s=None),
                    user_id=USER,
                    channel=CHANNEL,
                    context=agent.context,
                    hooks=agent.hooks,
                    tracer=tracer,
                    sleep=no_wait,
                )
            except ModelError as err:
                lines.append(f"user: {text}")
                lines.append(f"error: {err.kind}")
            else:
                lines.extend(describe_turn(result))
            if isinstance(tracer, InMemoryTracer) and tracer.traces:
                lines.append("events: " + ", ".join(e.kind for e in tracer.traces[-1].events))
        model.assert_consumed()
    finally:
        runtime.close()
    return Replayed(mask("\n".join(lines) + "\n"), model.used)


def describe_turn(result: TurnResult) -> list[str]:
    lines: list[str] = []
    for message in result.new_messages:
        lines.extend(_describe(message))
    lines.append(f"stop: {result.stop}, steps {result.steps}, compactions {result.compactions}")
    return lines


def mask(text: str) -> str:
    for pattern, token in MASKS:
        text = pattern.sub(token, text)
    return text


def _describe(message: Message) -> list[str]:
    lines: list[str] = []
    for block in message.blocks:
        if isinstance(block, TextBlock) and block.text.strip():
            lines.append(f"{message.role}: {block.text.strip()}")
        elif isinstance(block, ToolUseBlock):
            shown = (
                block.raw_args if block.raw_args is not None else json.dumps(block.args, ensure_ascii=False)
            )
            lines.append(f"call {block.name} {shown}")
        elif isinstance(block, ToolResultBlock):
            status = "error" if block.is_error else "ok"
            lines.append(f"result {block.name} {status}: {block.content.strip()}")
    return lines
