# ported from: src/middleware/message-batcher.ts
"""Merge messages that arrive close together FROM THE SAME PERSON into one agent turn.

"The same person", not "the same thread": see the ``pending`` notes below. In a group every person has their
own queue and their own turn.

It solves three problems:

1. Zalo splits an image and its caption into two messages; handling them apart makes the "what is this image"
  turn blind to the image.
2. Parallel handling races: the later turn reads history before the earlier one has written its reply, and the
  two answers contradict each other.
3. A message arriving WHILE a turn runs must not become a turn of its own.

A batch closes only when BOTH hold: (a) it has been quiet for ``debounce`` since the last message, AND (b)
nobody holds the thread lock (``thread_run_chain``). (b) is about the lock, not about "every agent turn": a
SCHEDULED agent turn deliberately runs outside the lock (the scheduler never wraps it, see its own docs:
deadlock), only its SEND step takes the lock. Do not read (b) as mutual exclusion between all agent turns.

Measured on a real log of 2026-08-04: a 249 s document turn; two user messages sent meanwhile became TWO
separate agent turns that each redid the whole web search and rebuilt an 18,000 character document; both died
by timeout and the sender received two identical error messages. That is why (b) exists.

Forced deviations (SQLite/one process -> Postgres/Redis, PLAN-AI01 section 3 and CONTRACTS section 4):

* The batcher lives in the API process; the turn runs in the worker. A closed batch is handed to ``handler``
  (default: build a ``TurnJob`` and enqueue it on the ``TurnQueue``) instead of running the turn in place.
* The pending messages live in a ``PendingBatchStore`` (``InMemoryPendingBatchStore`` here, Redis in
  ``pema.middleware.redis_backends``), so the worker can fold waiting messages into a running turn
  (``StorePendingInbox`` implements ``pema_contracts.agent_turn.PendingInbox`` over the same store).
* Only the TIMER stays process local. It is verified against the ``deadline_ms`` kept in the store when it
  fires, so a message pushed by another API process (which moved the deadline) is not cut early.
* The original woke parked batches from a hook fired by the in-process chain. With the lock in another process
  that fire may never be seen here, so a short poll (``PARKED_RECHECK_MS``) covers it while a batch is parked.
  The hook stays for the in-process mode.
* Everything that touches the store is ``async``; ``enqueue_message`` therefore is too.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.middleware.thread_run_chain import ThreadRef, ThreadRunner
from pema.shared.logger import create_logger
from pema_contracts.channel import InboundMessage

BatchHandler = Callable[[list[InboundMessage]], Awaitable[None]]
DefaultBatchHandler = Callable[[str, list[InboundMessage]], Awaitable[None]]

_log = create_logger("message-batcher")

TRAN_TIN_DON = 32
"""Cap on messages piled into ONE batch. The number of Hermes (``_BUSY_QUEUE_MAX_PENDING``,
``gateway/run.py``).

Why it exists: a turn hung until ``LLM_TURN_TIMEOUT_MS`` (default 15 minutes) plus a person typing nonstop
makes this list grow without bound.

It only bounds MEMORY, not runaway turns: however big, a batch is still EXACTLY ONE agent turn, and the input
sent to the model is already cut to the token budget. Unlike Hermes, where every piled message is its own turn
and the cap also bounds the number of model calls."""

PARKED_RECHECK_MS = 500
"""How often parked batches re-check the thread lock when the lock is held in another process."""

_DEADLINE_SLACK_MS = 1.0


def _wall_ms() -> float:
    return time.time() * 1000


@dataclass
class PendingBatch:
    thread_key: str
    """Key of the LOCK of the thread. Differs from the store key (which adds the sender): batching is per
    PERSON, but the history race guard is per THREAD."""
    sender_id: str
    messages: list[InboundMessage]
    deadline_ms: float | None
    """``None`` = the quiet period is over, only the thread lock is awaited ("parked"). This is the whole
    state machine: a deadline means condition (a) is not done and the timer handles it; a batch that is still
    here without a deadline is stuck on (b), and only then has ``_wake`` something to do."""
    dropped: int = 0
    """Messages dropped at the cap, reported ONCE when the batch closes."""


@dataclass(frozen=True)
class AppendOutcome:
    accepted: bool
    dropped: int


class PendingBatchStore(Protocol):
    """Where the pending batches live: ``(thread_key, sender_id)`` -> ``PendingBatch``."""

    async def append(
        self, thread_key: str, sender_id: str, message: InboundMessage, deadline_ms: float, cap: int
    ) -> AppendOutcome:
        """Atomic push with the cap. Accepted: the deadline moves to ``deadline_ms`` (a new message resets the
        quiet period, also of a parked batch). Over the cap: the NEW message is dropped (the old ones were
        sent first and the turn answers them in arrival order) and the deadline does not move."""
        ...

    async def get(self, thread_key: str, sender_id: str) -> PendingBatch | None: ...

    async def mark_parked(self, thread_key: str, sender_id: str) -> None: ...

    async def pop(
        self, thread_key: str, sender_id: str, *, only_if_parked: bool = False
    ) -> PendingBatch | None:
        """Atomic remove-and-return."""
        ...

    async def list_for_thread(self, thread_key: str) -> list[PendingBatch]: ...

    async def remove_thread(self, thread_key: str) -> list[PendingBatch]: ...

    async def list_parked_thread_keys(self) -> list[str]: ...

    async def list_all(self) -> list[PendingBatch]: ...

    async def count(self) -> int: ...

    async def clear(self) -> None: ...


class InMemoryPendingBatchStore:
    """Single process store: the faithful port of the module-level ``pending`` map."""

    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], PendingBatch] = {}

    async def append(
        self, thread_key: str, sender_id: str, message: InboundMessage, deadline_ms: float, cap: int
    ) -> AppendOutcome:
        key = (thread_key, sender_id)
        existing = self._pending.get(key)
        if existing is None:
            self._pending[key] = PendingBatch(thread_key, sender_id, [message], deadline_ms)
            return AppendOutcome(accepted=True, dropped=0)
        if len(existing.messages) >= cap:
            existing.dropped += 1
            return AppendOutcome(accepted=False, dropped=existing.dropped)
        existing.messages.append(message)
        existing.deadline_ms = deadline_ms
        return AppendOutcome(accepted=True, dropped=existing.dropped)

    async def get(self, thread_key: str, sender_id: str) -> PendingBatch | None:
        batch = self._pending.get((thread_key, sender_id))
        return None if batch is None else _copy(batch)

    async def mark_parked(self, thread_key: str, sender_id: str) -> None:
        batch = self._pending.get((thread_key, sender_id))
        if batch is not None:
            batch.deadline_ms = None

    async def pop(
        self, thread_key: str, sender_id: str, *, only_if_parked: bool = False
    ) -> PendingBatch | None:
        batch = self._pending.get((thread_key, sender_id))
        if batch is None or (only_if_parked and batch.deadline_ms is not None):
            return None
        del self._pending[(thread_key, sender_id)]
        return batch

    async def list_for_thread(self, thread_key: str) -> list[PendingBatch]:
        # Insertion order of the dict = order of the FIRST message of each person.
        return [_copy(b) for (tk, _), b in self._pending.items() if tk == thread_key]

    async def remove_thread(self, thread_key: str) -> list[PendingBatch]:
        keys = [k for k in self._pending if k[0] == thread_key]
        return [self._pending.pop(k) for k in keys]

    async def list_parked_thread_keys(self) -> list[str]:
        return sorted({b.thread_key for b in self._pending.values() if b.deadline_ms is None})

    async def list_all(self) -> list[PendingBatch]:
        return [_copy(b) for b in self._pending.values()]

    async def count(self) -> int:
        return len(self._pending)

    async def clear(self) -> None:
        self._pending.clear()


def _copy(batch: PendingBatch) -> PendingBatch:
    return PendingBatch(
        batch.thread_key, batch.sender_id, list(batch.messages), batch.deadline_ms, batch.dropped
    )


@dataclass
class _Timers:
    handles: dict[tuple[str, str], asyncio.TimerHandle] = field(
        default_factory=dict[tuple[str, str], asyncio.TimerHandle]
    )


class MessageBatcher:
    """One batcher per process. ``store`` and ``runner`` decide whether it runs single-process (in-memory
    store + ``InProcessThreadRunChain``) or split (Redis store + ``QueueThreadRunner``)."""

    def __init__(
        self,
        store: PendingBatchStore,
        runner: ThreadRunner,
        *,
        default_handler: DefaultBatchHandler | None = None,
        parked_recheck_ms: int = PARKED_RECHECK_MS,
        now_ms: Callable[[], float] = _wall_ms,
    ) -> None:
        self._store = store
        self._runner = runner
        self._default_handler = default_handler
        self._parked_recheck_ms = parked_recheck_ms
        self._now_ms = now_ms
        self._timers = _Timers()
        # Latest handler per key, NOT the handler of the first message of the batch: the router re-reads the
        # account for every message, so each call is a closure over fresh configuration. Keeping the old
        # closure runs the turn on stale settings (a policy edit on the dashboard would not apply).
        self._handlers: dict[tuple[str, str], BatchHandler] = {}
        self._flush_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._poll_task: asyncio.Task[None] | None = None
        runner.on_thread_free(self._on_thread_free)

    # ------------------------------------------------------------------ intake
    async def enqueue_message(
        self,
        thread_key: str,
        message: InboundMessage,
        handler: BatchHandler | None = None,
        debounce_ms: int | None = None,
    ) -> bool:
        """Take one message into the merge queue.

        Returns ``False`` when the message was DROPPED at the cap. It never reaches the turn, so the caller
        must do by itself what the turn would have done for it. Since a message is written to history AT
        RECEIPT (``record_incoming_message``), that shrinks to downloading the images: history already has it.
        """
        debounce = debounce_ms if debounce_ms is not None else get_tuning_int("MESSAGE_BATCH_DEBOUNCE_MS")
        key = (thread_key, message.sender_id)
        outcome = await self._store.append(
            thread_key, message.sender_id, message, self._now_ms() + debounce, TRAN_TIN_DON
        )
        if not outcome.accepted:
            # Log EXACTLY ONCE per hit of the cap, not per dropped message: a 15 minute hung turn plus a
            # lively group would produce hundreds of WARN lines for one event and push out the log being read.
            # The total is logged once when the batch closes.
            if outcome.dropped == 1:
                _log.warning(
                    "Hàng chờ gộp tin đã chạm trần - BỎ tin mới kể từ đây. "
                    "Lượt đang chạy nhiều khả năng bị treo.",
                    thread_key=thread_key,
                    cap=TRAN_TIN_DON,
                )
            return False
        if handler is not None:
            self._handlers[key] = handler
        self._arm(key, debounce)
        return True

    # ------------------------------------------------------------------ timers
    def _arm(self, key: tuple[str, str], delay_ms: float) -> None:
        old = self._timers.handles.pop(key, None)
        if old is not None:
            old.cancel()
        loop = asyncio.get_running_loop()
        self._timers.handles[key] = loop.call_later(max(delay_ms, 0) / 1000, self._fire, key)

    def _fire(self, key: tuple[str, str]) -> None:
        self._timers.handles.pop(key, None)
        self._spawn(self._flush(key))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def timer_count(self) -> int:
        """Live timers (a forgotten timer keeps the loop alive until it fires)."""
        return len(self._timers.handles)

    # ------------------------------------------------------------------ flush
    async def _flush(self, key: tuple[str, str]) -> None:
        """The quiet period is over (or the thread became free). Close the batch if the thread is idle, else
        PARK it.

        Park, do not queue behind the running turn: queuing freezes the list of messages now, so a message
        that arrives later has nowhere to merge and spawns one more turn, which is the very bug being cured.
        """
        thread_key, sender_id = key
        try:
            async with self._flush_lock:
                batch = await self._store.get(thread_key, sender_id)
                if batch is None:
                    self._handlers.pop(key, None)
                    return
                if batch.deadline_ms is not None:
                    remaining = batch.deadline_ms - self._now_ms()
                    if remaining > _DEADLINE_SLACK_MS and key not in self._timers.handles:
                        # The quiet period was extended (by another API process) after this timer was armed.
                        self._arm(key, remaining)
                        return
                    if key in self._timers.handles:
                        return  # a newer timer is already in charge
                await self._store.mark_parked(thread_key, sender_id)
                # The lock is per THREAD, not per merge key: two people of one group have two queues but share
                # one conversation, so their turns must follow each other and never read history overlapped.
                if await self._runner.is_busy(thread_key):
                    self._ensure_poll()
                    return  # ``_wake`` calls back when the thread is free
                popped = await self._store.pop(thread_key, sender_id)
                if popped is None:
                    return
                handler = self._handlers.pop(key, None)
                if popped.dropped > 0:
                    _log.warning(
                        "Chốt batch chạm trần - số tin bị bỏ khỏi lượt này (vẫn được ghi vào history)",
                        thread_key=thread_key,
                        dropped=popped.dropped,
                        run=len(popped.messages),
                    )
                await self._runner.run(thread_key, self._handler_job(handler, thread_key, popped.messages))
        except Exception as exc:
            _log.error("Chốt batch thất bại", err=exc, thread_key=thread_key)

    def _handler_job(
        self, handler: BatchHandler | None, thread_key: str, messages: list[InboundMessage]
    ) -> Callable[[], Awaitable[None]]:
        async def job() -> None:
            try:
                if handler is not None:
                    await handler(messages)
                elif self._default_handler is not None:
                    await self._default_handler(thread_key, messages)
                else:
                    _log.error(
                        "Batch đóng nhưng không có handler - tin không được chạy", thread_key=thread_key
                    )
            except Exception as exc:
                _log.error("Handler của batch ném lỗi", err=exc, thread_key=thread_key)

        return job

    # ------------------------------------------------------------------ waking parked batches
    def _on_thread_free(self, thread_key: str) -> None:
        self._spawn(self._wake(thread_key))

    async def _wake(self, thread_key: str) -> None:
        """The thread just became free: run EVERY parked batch of that thread (if any).

        Walk all of them rather than look one key up: a thread now has several queues, one per person. Three
        people writing while the bot is busy park three batches; missing one means that person is never
        answered.

        In practice only the FIRST can run: the hand-over marks the thread busy at once, so the next
        ``_flush`` sees it busy and parks again. The rest are woken one by one, each time by the release of
        the previous turn. The loop stays because it is not wrong and a future parallel mode will use it; do
        not read it as a fan-out.

        Order is the order of the FIRST message of each person. A batch still holding a deadline means a
        person is still typing: leave it to its timer, do not steal the trigger. That way "not quiet long
        enough, no turn" holds on the busy path and the idle path alike, as one rule."""
        parked = [b for b in await self._store.list_for_thread(thread_key) if b.deadline_ms is None]
        for batch in parked:
            await self._flush((batch.thread_key, batch.sender_id))

    def _ensure_poll(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            return
        self._poll_task = asyncio.ensure_future(self._poll_parked())

    async def _poll_parked(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._parked_recheck_ms / 1000)
                keys = await self._store.list_parked_thread_keys()
                if not keys:
                    return
                for thread_key in keys:
                    if not await self._runner.is_busy(thread_key):
                        await self._wake(thread_key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.error("Vòng kiểm tra batch đỗ thất bại", err=exc)

    # ------------------------------------------------------------------ mid-turn injection
    async def lay_tin_dang_do(self, thread_key: str, sender_id: str) -> list[InboundMessage]:
        """Take the parked messages of THE PERSON being answered and remove them from the queue.

        For the mid-turn injection path: the running turn pulls the new messages in instead of leaving them to
        become one more turn. By SENDER, not by thread: since each person has their own queue, someone else's
        messages get their own turn; pulling them in would steal that turn and mix two questions into one.

        Returns empty while the group is STILL BEING TYPED (the deadline has not passed). Same invariant as
        ``_wake``: not quiet long enough, nobody may touch the batch. Pulling early would cut the very burst
        the person is typing in half; the model would get half a sentence now and the rest at the next step.

        No need to check whether the thread is busy: only the running turn calls this, and it can run only
        because it holds the lock."""
        key = (thread_key, sender_id)
        batch = await self._store.pop(thread_key, sender_id, only_if_parked=True)
        if batch is None:
            return []
        self._handlers.pop(key, None)
        if batch.dropped > 0:
            _log.warning(
                "Tin chen giữa lượt lấy từ hàng chờ đã chạm trần - số tin bị bỏ (vẫn được ghi vào history)",
                thread_key=thread_key,
                dropped=batch.dropped,
                injected=len(batch.messages),
            )
        return batch.messages

    async def id_tin_dang_cho(self, thread_key: str) -> list[int]:
        """History row ids of the messages waiting from EVERY sender of the thread.

        The agent turn uses them to leave them out of its history window: a message is written to history AT
        RECEIPT, so a waiting one still shows in the recent messages although no turn handled it.

        THREAD scope, not sender: the argument "only exclude what THIS turn will re-insert" sounds solid and
        is wrong. Someone else's waiting message enters the prompt as an unanswered question, the model
        answers it, then that person's turn runs and answers again. Measured on turn 1 when two people
        @mention in one beat: the other's question slipped in as history and two replies repeated each other.

        The other person's message is absent only TEMPORARILY: once their batch closes it becomes real
        history.

        ``lay_tin_dang_do`` is the opposite on purpose: it TAKES messages away, and taking someone else's
        steals their turn. Read-only: it does not touch the queue."""
        ids: list[int] = []
        for batch in await self._store.list_for_thread(thread_key):
            ids.extend(m.history_row_id for m in batch.messages if m.history_row_id is not None)
        return ids

    # ------------------------------------------------------------------ cancel / teardown
    async def huy_batch_cua_thread(self, thread_key: str) -> int:
        """Drop the waiting messages of EXACTLY one thread. For when that thread's context is wiped.

        Without this the batch parked in the queue would still run after the wipe: the bot answers a question
        that belongs to the context just cleaned, and the answer is written back into the empty history; the
        user pressed delete and still sees messages reappear. (The USER's messages are already in history from
        receipt, so the wipe itself cleaned them.)

        Does NOT touch the running turn: cutting it mid-way would leave a tool half-sending a file or
        half-drawing an image, and the turn still writes its result at the end. The running turn ends by
        itself; this only stops what has not started.

        Walks every queue of the thread: one per person. Cancelling one key misses the others in the group,
        which would keep running on the context just wiped."""
        removed = await self._store.remove_thread(thread_key)
        count = 0
        for batch in removed:
            key = (batch.thread_key, batch.sender_id)
            handle = self._timers.handles.pop(key, None)
            if handle is not None:
                handle.cancel()
            self._handlers.pop(key, None)
            count += len(batch.messages)
        return count

    async def clear_pending_batches(self) -> None:
        """Cancel every waiting message; for shutdown so the process does not hang."""
        for handle in self._timers.handles.values():
            handle.cancel()
        self._timers.handles.clear()
        self._handlers.clear()
        await self._store.clear()
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def recover(self) -> int:
        """Re-arm the timers of batches left in a shared store by a process that died or was restarted, and
        start the parked-batch poll. Returns how many batches were found. (Not in the original: there the
        batches died with the process.)"""
        batches = await self._store.list_all()
        for batch in batches:
            if batch.deadline_ms is None:
                self._ensure_poll()
            else:
                self._arm((batch.thread_key, batch.sender_id), batch.deadline_ms - self._now_ms())
        return len(batches)

    async def active_thread_count(self) -> int:
        """Entries still alive in the queue and in the chain; for leak tests.

        NOT "number of threads": the queue is keyed by ``(thread, sender)``, so a group of three counts as
        three, and a thread that has a parked batch and a running turn is counted twice. That is fine for the
        real use (zero means everything was cleaned) but do not read it as the number of active conversations.
        """
        return await self._store.count() + self._runner.active_count()


class StorePendingInbox:
    """``pema_contracts.agent_turn.PendingInbox`` over a ``PendingBatchStore`` (Redis in production), bound to
    ONE clinic because the protocol methods carry no clinic id.

    ``sender_id`` is an extra optional argument (compatible with the Protocol): with it, only that person's
    parked batch is taken (the original ``layTinDangDo`` scope, so a group member's messages are not stolen).
    Without it every parked batch of the thread is taken, which is right for a direct thread (one sender)."""

    def __init__(self, store: PendingBatchStore, clinic_id: UUID) -> None:
        self._store = store
        self._clinic_id = clinic_id

    def _key(self, account_id: str, thread_id: str) -> str:
        return ThreadRef(self._clinic_id, account_id, thread_id).key

    async def take_injected(
        self, account_id: str, thread_id: str, sender_id: str | None = None
    ) -> Sequence[InboundMessage]:
        thread_key = self._key(account_id, thread_id)
        if sender_id is not None:
            batch = await self._store.pop(thread_key, sender_id, only_if_parked=True)
            return [] if batch is None else batch.messages
        taken: list[InboundMessage] = []
        for pending in await self._store.list_for_thread(thread_key):
            if pending.deadline_ms is not None:
                continue
            popped = await self._store.pop(thread_key, pending.sender_id, only_if_parked=True)
            if popped is not None:
                taken.extend(popped.messages)
        return taken

    async def pending_history_ids(self, account_id: str, thread_id: str) -> Sequence[int]:
        ids: list[int] = []
        for batch in await self._store.list_for_thread(self._key(account_id, thread_id)):
            ids.extend(m.history_row_id for m in batch.messages if m.history_row_id is not None)
        return ids
