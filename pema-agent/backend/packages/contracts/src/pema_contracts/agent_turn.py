"""Agent turn contract (package D1 implements ``AgentEngine``; channels, scheduler and policy call it).

Port of ``AgentTurnParams`` / ``AgentTurnResult`` (src/agent/agent-loop.ts), ``StepTrace``
(agent-step-trace.ts) and the token accounting of usage-store.ts. Differences forced by the move to
Python/Postgres:

* the Vercel AI SDK is replaced by a hand-written tool loop on the ``openai`` SDK (D1), with the same
  step/``tool-loop-guard``/``maxRetries`` semantics;
* ``api: API | null`` (the zca-js handle) is replaced by ``channel`` inside ``ToolContext``;
* "one synchronous process" invariants (thread run chain, claim job) move to Redis: ``TurnQueue``
  carries inbound turns from the API process to the worker, ``ThreadLock`` serialises turns of one
  (account, thread) across workers (``thread-run-chain.ts``).

Policy: the engine receives a ``PolicyHooks`` at construction (default ``PermissivePolicyHooks``) and
calls ``before_llm`` / ``after_llm`` / ``filter_tool_keys`` where ``pema_contracts.policy`` says.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.channel import InboundMessage
from pema_contracts.common import ApiModel, JsonObject, VnDatetime


class TurnSource(StrEnum):
    """``AgentTurnSource``: 'message' = answering an incoming message, 'schedule' = a job fired."""

    MESSAGE = "message"
    SCHEDULE = "schedule"


class TokenUsage(ApiModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    steps: int = Field(default=0, ge=0)


class StepTrace(ApiModel):
    """One step of a turn: what the model said, which tools it called and what came back."""

    step_number: int
    attempt: int = 1
    text: str = ""
    reasoning: str = ""
    tool_calls: list[JsonObject] = Field(default_factory=list[JsonObject])
    tool_results: list[JsonObject] = Field(default_factory=list[JsonObject])
    tool_errors: list[JsonObject] = Field(default_factory=list[JsonObject])
    finish_reason: str = ""
    warnings: list[str] = Field(default_factory=list[str])
    input_tokens: int = 0
    output_tokens: int = 0


class AgentTurnRequest(ApiModel):
    clinic_id: UUID
    account_id: str
    batch: list[InboundMessage] = Field(
        min_length=1, description="Merged messages of the turn; the last one represents it."
    )
    isolated: bool = Field(
        default=False,
        description="Scheduled turn: ignore history, memory and summary, persona stays. Output history is "
        "written by the caller.",
    )
    source: TurnSource = TurnSource.MESSAGE
    scheduled_job_id: str | None = None
    request_id: str | None = None
    turn_id: int | None = Field(
        default=None,
        description="Row of ``agent.usage`` the caller ALREADY opened (``UsageStore.open_agent_turn``). "
        "None: the engine opens one itself and returns it in the result / the error. "
        "Additive, added by package D1.",
    )


class AgentTurnResult(ApiModel):
    text: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    turn_id: int | None = None
    handed_off: bool = Field(
        default=False,
        description="A policy hook stopped the turn before the model (red flag, unsupported media). "
        "``text`` is then empty and the caller owns the hand-off.",
    )
    hand_off_reason: str | None = None


@dataclass
class TurnCallbacks:
    """Optional seams, the three ``layTinChen`` / ``layIdDangCho`` / ``ghiNhanDaGui`` parameters."""

    fetch_injected_messages: Callable[[], Awaitable[Sequence[InboundMessage]]] | None = None
    """Messages the user sent while the turn was running; called at each step boundary."""
    pending_history_ids: Callable[[], Awaitable[Sequence[int]]] | None = None
    """History row ids of messages waiting in the batcher, to exclude them from the history window."""
    record_tool_sent: Callable[[str], None] | None = None
    trace: list[StepTrace] = field(default_factory=list[StepTrace])
    """Caller-owned: the engine only appends, so a failing turn keeps the diagnosis."""


class AgentEngine(Protocol):
    """Implemented by ``pema.agent.agent_loop`` (D1).

    ``run_turn`` raises ``pema_contracts.turn_errors.AgentTurnError`` (with the provider error kind already
    classified) for EVERY failure, so callers (the channel turn processor, the scheduler) never import an
    SDK exception type nor ``pema.agent``.
    """

    async def run_turn(
        self, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
    ) -> AgentTurnResult: ...


class GeneratedText(ApiModel):
    text: str
    truncated: bool = False


class TextGenerator(Protocol):
    """Single-shot text completion (no tools). Used by the thread summariser (D2) and the vision
    sidecar; D1 provides the real one over the configured provider; tests pass a fake."""

    async def generate_text(self, prompt: str, *, max_output_tokens: int | None = None) -> GeneratedText: ...


class TurnJob(ApiModel):
    """What the API process puts on the Redis queue for the worker, after the batcher closed a batch."""

    job_id: UUID
    clinic_id: UUID
    account_id: str
    thread_id: str
    messages: list[InboundMessage] = Field(min_length=1)
    enqueued_at: VnDatetime
    attempt: int = 1
    request_id: str | None = None


class TurnQueue(Protocol):
    """Redis-backed in production (Streams or list + visibility timeout), in-memory in tests."""

    async def enqueue(self, job: TurnJob) -> None: ...

    async def claim(self, block_seconds: float) -> TurnJob | None: ...

    async def ack(self, job_id: UUID) -> None: ...

    async def nack(self, job_id: UUID, *, retry: bool) -> None: ...


class PendingInbox(Protocol):
    """The batcher's view of messages that arrived while a turn is running (``message-batcher.ts``:
    ``layTinDangDo`` / ``idTinDangCho``). Implemented by package C1 over Redis (the batcher lives in the API
    process, the turn in the worker); consumed by package C2's turn processor, which builds the
    ``TurnCallbacks`` from it."""

    async def take_injected(
        self, account_id: str, thread_id: str, sender_id: str | None = None
    ) -> Sequence[InboundMessage]:
        """Remove and return the waiting messages so the running turn can fold them in at a step boundary.

        ``sender_id`` is the ``layTinDangDo(threadKey, senderId)`` scope of the original: the batcher keys its
        queues by (thread, sender) and a turn must never steal another person's message (that person has a
        turn of their own). The turn passes the sender of its latest message; ``None`` takes every parked
        batch of the thread, which is right only for a direct thread (one possible sender)."""
        ...

    async def pending_history_ids(self, account_id: str, thread_id: str) -> Sequence[int]:
        """History row ids of the waiting messages, to exclude them from the history window (they are
        already recorded at receipt)."""
        ...


class ThreadLock(Protocol):
    """Port of ``thread-run-chain.ts``: one turn at a time per (account, thread), across processes."""

    def hold(self, account_id: str, thread_id: str) -> ThreadLockHandle: ...


class ThreadLockHandle(Protocol):
    async def __aenter__(self) -> None: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...
