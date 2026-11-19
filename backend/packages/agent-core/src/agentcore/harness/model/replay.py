"""Record a live model once, replay it in tests without an API key.

A cassette is a JSONL file: a header, then the user turns and the model calls in the order they happened.
``RecordingModel`` wraps a real client and writes each call: the streamed deltas, then the result or the
error. ``ReplayModel`` plays the calls back in order, streams the same deltas, raises the same errors, and
fails loud when the turn asks something else than it did when recorded or calls the model more often. Only a
summary of each request is kept (tool names, the user's latest words, the reasoning effort): never the system
prompt, never a key. A line can be edited by hand, e.g. into an error, to test a failure path.

Same idea as deepseek-harness's ``llm-replay`` (MIT), in a format of our own.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, TypeAdapter

from agentcore.harness.model.errors import ModelError, ModelErrorKind
from agentcore.harness.model.types import (
    AssistantResult,
    LlmRequest,
    ModelClient,
    ReasoningEffort,
    StreamSink,
)
from agentcore.messages import Message, TextBlock
from agentcore.prompt.builder import CONTEXT_OPEN

CASSETTE_FORMAT: Final = 1
USER_TEXT_CHARS: Final = 300
RERECORD: Final = "record the scenario again (agent chat --record)"


class CassetteError(AssertionError):
    """The run does not match the cassette."""


class Header(BaseModel):
    type: Literal["header"] = "header"
    format: int = CASSETTE_FORMAT
    recorded_at: str = ""
    model: str = ""


class Turn(BaseModel):
    type: Literal["turn"] = "turn"
    user_text: str


class RequestSummary(BaseModel):
    tools: list[str] = Field(default_factory=list[str])
    user: str = ""
    """The start of the newest user message the person wrote (the context block left out)."""
    reasoning: ReasoningEffort | None = None

    @classmethod
    def of(cls, request: LlmRequest) -> RequestSummary:
        return cls(
            tools=[tool.name for tool in request.tools],
            user=_latest_user_text(request.messages)[:USER_TEXT_CHARS],
            reasoning=request.reasoning,
        )


class RecordedError(BaseModel):
    kind: ModelErrorKind
    message: str = ""
    retry_after_s: float | None = None


class Call(BaseModel):
    type: Literal["call"] = "call"
    request: RequestSummary = Field(default_factory=RequestSummary)
    stream: list[tuple[Literal["text", "thinking"], str]] = Field(
        default_factory=list[tuple[Literal["text", "thinking"], str]]
    )
    result: AssistantResult | None = None
    error: RecordedError | None = None


Line = Annotated[Header | Turn | Call, Field(discriminator="type")]
_LINE: Final[TypeAdapter[Header | Turn | Call]] = TypeAdapter(Line)


class Cassette(BaseModel):
    header: Header
    turns: list[str]
    calls: list[Call]

    @classmethod
    def load(cls, path: Path) -> Cassette:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise CassetteError(f"{path} is empty")
        parsed = [_LINE.validate_json(line) for line in lines]
        header = parsed[0]
        if not isinstance(header, Header):
            raise CassetteError(f"{path} does not start with a header line")
        if header.format != CASSETTE_FORMAT:
            raise CassetteError(f"{path} has format {header.format}; this code reads {CASSETTE_FORMAT}")
        turns = [line.user_text for line in parsed if isinstance(line, Turn)]
        calls = [line for line in parsed if isinstance(line, Call)]
        for index, call in enumerate(calls):
            if (call.result is None) == (call.error is None):
                raise CassetteError(f"{path}: call {index + 1} needs exactly one of result and error")
        return cls(header=header, turns=turns, calls=calls)


class CassetteWriter:
    """Writes a cassette line by line, so a run that stops half-way still leaves what happened."""

    def __init__(self, path: Path, *, model: str = "") -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        path.write_text("", encoding="utf-8", newline="\n")
        self._write(Header(recorded_at=stamp, model=model))

    def turn(self, user_text: str) -> None:
        self._write(Turn(user_text=user_text))

    def call(self, call: Call) -> None:
        self._write(call)

    def _write(self, line: BaseModel) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line.model_dump(mode="json", exclude_none=True), ensure_ascii=False))
            handle.write("\n")


class RecordingModel:
    def __init__(self, inner: ModelClient, writer: CassetteWriter) -> None:
        self._inner = inner
        self._writer = writer

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        tap = _Tap(sink)
        summary = RequestSummary.of(request)
        try:
            result = await self._inner.complete(request, sink=tap)
        except ModelError as err:
            error = RecordedError(kind=err.kind, message=str(err), retry_after_s=err.retry_after_s)
            self._writer.call(Call(request=summary, stream=tap.deltas, error=error))
            raise
        self._writer.call(Call(request=summary, stream=tap.deltas, result=result))
        return result


class ReplayModel:
    def __init__(self, cassette: Cassette, *, strict: bool = True) -> None:
        self._calls = list(cassette.calls)
        self._strict = strict
        self.used = 0

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        if self.used >= len(self._calls):
            raise CassetteError(
                f"the model was called {self.used + 1} times, the cassette has {len(self._calls)}; {RERECORD}"
            )
        call = self._calls[self.used]
        self.used += 1
        if self._strict:
            _check(self.used, call.request, RequestSummary.of(request))
        if sink is not None:
            for kind, delta in call.stream:
                (sink.text if kind == "text" else sink.thinking)(delta)
        if call.error is not None:
            raise ModelError(call.error.kind, call.error.message, retry_after_s=call.error.retry_after_s)
        if call.result is None:
            raise CassetteError(f"call {self.used} has neither a result nor an error")
        return call.result

    def assert_consumed(self) -> None:
        left = len(self._calls) - self.used
        if left:
            raise CassetteError(f"{left} recorded model call(s) were never made; {RERECORD}")


class _Tap:
    def __init__(self, sink: StreamSink | None) -> None:
        self._sink = sink
        self.deltas: list[tuple[Literal["text", "thinking"], str]] = []

    def text(self, delta: str) -> None:
        self.deltas.append(("text", delta))
        if self._sink is not None:
            self._sink.text(delta)

    def thinking(self, delta: str) -> None:
        self.deltas.append(("thinking", delta))
        if self._sink is not None:
            self._sink.thinking(delta)


def _check(number: int, recorded: RequestSummary, live: RequestSummary) -> None:
    for field in ("tools", "user", "reasoning"):
        then, now = getattr(recorded, field), getattr(live, field)
        if then != now:
            raise CassetteError(f"call {number}: {field} was {then!r} when recorded, now {now!r}; {RERECORD}")


def _latest_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.role != "user" or not message.blocks:
            continue
        first = message.blocks[0]
        if isinstance(first, TextBlock) and not first.text.lstrip().startswith(CONTEXT_OPEN):
            return first.text
    return ""
