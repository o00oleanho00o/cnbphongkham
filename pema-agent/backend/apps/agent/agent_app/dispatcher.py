"""Runs inbound messages from any channel: store first, then one turn at a time per session, in arrival order.

``accept`` stores the message (once per channel message id) and starts a drain of its session in the
background. A drain holds the session's run lock and runs every queued message of the session, oldest first;
a caller waits for its own message with ``wait``. The sweeper finds messages left ``processing`` by a crashed
process (their session lock is free) and queues them again, or gives up after ``max_attempts``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from agent_app.assembly import Agent
from agent_app.ingress import (
    ConversationStore,
    IngressRecord,
    IngressStore,
    SessionBusyError,
    SessionLocks,
    TurnReply,
)
from agent_app.live import LiveAgent
from agent_app.profile import QueueMode
from agent_app.storage import PostgresSessionStore
from agentcore import (
    DEFAULT_TENANT,
    ModelError,
    SessionStore,
    ToolResultBlock,
    ToolUseBlock,
    Tracer,
    run_turn,
)
from agentcore.channels import InboundMessage, session_id_for

CLOSE_GRACE_S: Final = 10.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchSettings:
    tenant_id: str = DEFAULT_TENANT
    max_concurrent_turns: int = 4
    """Sessions that run at the same time in this process; each holds a database connection for its lock."""
    max_attempts: int = 3
    sweep_interval_s: float = 30.0
    poll_s: float = 1.0
    """How often a waiter re-reads its message, for runs finished by another process."""
    queue_mode: QueueMode = "followup"
    """followup: one turn per message. collect: after a quiet moment, the waiting messages of one person
    become one turn. steer: collect, and messages that come while the turn uses tools join it."""
    queue_by_channel: Mapping[str, QueueMode] = field(default_factory=dict[str, QueueMode])
    debounce_s: float = 0.8
    """collect/steer: a turn starts once no new message came for this long ..."""
    max_wait_s: float = 3.0
    """... or after this long at most."""
    max_batch: int = 20
    """Messages one turn takes at most."""

    def mode_for(self, channel: str) -> QueueMode:
        return self.queue_by_channel.get(channel, self.queue_mode)


class StreamObserver:
    """Turns one run into events for a live client. Only names reach the client: no reasoning, no tool
    arguments or results."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._thinking = False

    def text(self, delta: str) -> None:
        self.events.put_nowait({"event": "text", "delta": delta})

    def thinking(self, delta: str) -> None:
        if not self._thinking:
            self._thinking = True
            self.events.put_nowait({"event": "thinking"})

    def tool_call(self, use: ToolUseBlock) -> None:
        self._thinking = False
        self.events.put_nowait({"event": "tool_call", "name": use.name})

    def tool_result(self, result: ToolResultBlock) -> None:
        self.events.put_nowait({"event": "tool_result", "name": result.name, "is_error": result.is_error})

    def retry(self, error_kind: str) -> None:
        """The text streamed since the last tool result is void: the model call is made again."""
        self._thinking = False
        self.events.put_nowait({"event": "retry", "error_kind": error_kind})

    def close(self) -> None:
        self.events.put_nowait(None)


class Dispatcher:
    def __init__(
        self,
        agent: Agent | LiveAgent,
        *,
        store: SessionStore,
        tracer: Tracer,
        ingress: IngressStore,
        conversations: ConversationStore,
        locks: SessionLocks,
        sessions: PostgresSessionStore | None = None,
        settings: DispatchSettings | None = None,
        before_turn: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._agent = agent
        self._before_turn = before_turn
        self.store = store
        self.ingress = ingress
        self.settings = settings or DispatchSettings()
        self._tracer = tracer
        self._conversations = conversations
        self._locks = locks
        self._sessions = sessions
        self._slots = asyncio.Semaphore(self.settings.max_concurrent_turns)
        self._tasks: set[asyncio.Task[None]] = set()
        self._draining: set[str] = set()
        self._wanted: set[str] = set()
        self._finished: dict[int, asyncio.Event] = {}
        self._observers: dict[int, StreamObserver] = {}
        self._listeners: list[Callable[[IngressRecord], None]] = []

    @property
    def tenant_id(self) -> str:
        return self.settings.tenant_id

    @property
    def agent(self) -> Agent:
        """The agent for the next turn; with plugins switched on or off it is a new one."""
        return self._agent.current() if isinstance(self._agent, LiveAgent) else self._agent

    async def session_for(self, channel: str, conversation_id: str) -> str:
        epoch = await self._conversations.epoch(self.tenant_id, channel, conversation_id)
        return session_id_for(self.agent.profile.agent.name, channel, conversation_id, epoch)

    async def reset(self, channel: str, conversation_id: str) -> str:
        """Starts the conversation over; returns its new session id. The old session stays readable."""
        epoch = await self._conversations.reset(self.tenant_id, channel, conversation_id)
        return session_id_for(self.agent.profile.agent.name, channel, conversation_id, epoch)

    async def accept(
        self, inbound: InboundMessage, *, observer: StreamObserver | None = None, deliver: bool = False
    ) -> tuple[IngressRecord, bool]:
        """Stores the message and starts its session's drain; returns the record and whether it is new. With
        ``deliver`` the reply goes out through the message's channel once the turn is over."""
        session_id = await self.session_for(inbound.channel, inbound.conversation_id)
        record, created = await self.ingress.accept(self.tenant_id, inbound, session_id, deliver=deliver)
        if observer is not None and not record.finished:
            self._observers[record.id] = observer
        if record.status == "queued":
            self.schedule(record.session_id)
        return record, created

    def unwatch(self, ingress_id: int) -> None:
        self._observers.pop(ingress_id, None)

    async def wait(self, ingress_id: int, timeout_s: float) -> IngressRecord:
        """The message once finished, or as it stands after ``timeout_s``."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            record = await self.ingress.get(self.tenant_id, ingress_id)
            if record is None:
                raise KeyError(ingress_id)
            remaining = deadline - loop.time()
            if record.finished or remaining <= 0:
                return record
            event = self._finished.setdefault(ingress_id, asyncio.Event())
            try:
                await asyncio.wait_for(event.wait(), timeout=min(remaining, self.settings.poll_s))
            except TimeoutError:
                continue

    def schedule(self, session_id: str) -> None:
        self._wanted.add(session_id)
        if session_id in self._draining:
            return
        self._draining.add(session_id)
        task = asyncio.create_task(self._drain(session_id), name=f"drain {session_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _drain(self, session_id: str) -> None:
        try:
            async with self._slots, self._locks.hold(self.tenant_id, session_id, timeout_s=None):
                while session_id in self._wanted:
                    self._wanted.discard(session_id)
                    while (queued := await self.ingress.next_queued(self.tenant_id, session_id)) is not None:
                        mode = self.settings.mode_for(queued.channel)
                        if mode != "followup":
                            await self._quiet(session_id)
                        claimed = await self.ingress.claim(queued.id)
                        if claimed is None:
                            continue
                        limit = self.settings.max_batch - 1
                        joined = await self._gather(claimed, limit) if mode != "followup" else []
                        await self._process(claimed, joined, steer=mode == "steer")
        except Exception as err:  # the messages stay queued or processing; the sweeper picks them up
            logger.warning("drain of session %s stopped (%s)", session_id, type(err).__name__)
        finally:
            self._draining.discard(session_id)
            self._wanted.discard(session_id)

    async def _quiet(self, session_id: str) -> None:
        """Waits until no new message came for ``debounce_s`` (at most ``max_wait_s``), so a burst of short
        messages becomes one turn."""
        settings = self.settings
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.max_wait_s
        count = len(await self.ingress.queued_in_session(self.tenant_id, session_id, settings.max_batch + 1))
        while (pause := min(settings.debounce_s, deadline - loop.time())) > 0:
            await asyncio.sleep(pause)
            now = len(
                await self.ingress.queued_in_session(self.tenant_id, session_id, settings.max_batch + 1)
            )
            if now == count:
                return
            count = now

    async def _gather(self, lead: IngressRecord, limit: int) -> list[IngressRecord]:
        """Claims the next queued messages of the same person, in order, up to the first one from someone
        else: a reply never jumps ahead of another person's message."""
        if limit <= 0:
            return []
        joined: list[IngressRecord] = []
        for record in await self.ingress.queued_in_session(self.tenant_id, lead.session_id, limit):
            if record.user_id != lead.user_id:
                break
            claimed = await self.ingress.claim(record.id)
            if claimed is None:
                break
            joined.append(claimed)
        return joined

    async def _process(self, lead: IngressRecord, joined: list[IngressRecord], *, steer: bool) -> None:
        """Runs one turn for ``lead`` and the messages ``joined`` to it (more may join while it uses tools);
        they all end with its reply or its error. Only the lead's reply goes out through a channel."""
        observer = self._observers.pop(lead.id, None)
        if self._before_turn is not None:
            try:
                await self._before_turn()
            except Exception as err:  # the turn runs with the plugins as they were
                logger.warning("plugin refresh failed (%s)", type(err).__name__)
        agent = self.agent
        texts = [lead.text, *(record.text for record in joined)]

        async def steer_in() -> list[str]:
            more = await self._gather(lead, self.settings.max_batch - 1 - len(joined))
            joined.extend(more)
            return [record.text for record in more]

        reply: TurnReply | None = None
        error_kind = "unknown"
        try:
            if self._sessions is not None:
                await self._sessions.open_session(
                    self.tenant_id, lead.session_id, channel=lead.channel, user_id=lead.user_id
                )
            result = await run_turn(
                session_id=lead.session_id,
                user_text="\n\n".join(texts),
                prompt=agent.prompt,
                model=agent.model,
                tools=agent.tools,
                store=self.store,
                policy=agent.policy,
                tenant_id=self.tenant_id,
                user_id=lead.user_id,
                channel=lead.channel,
                context=agent.context,
                observer=observer,
                hooks=agent.hooks,
                tracer=self._tracer,
                steer=steer_in if steer else None,
                collected=len(texts),
            )
            reply = TurnReply.of(result)
        except ModelError as err:
            error_kind = err.kind
        except Exception as err:
            logger.warning("message %d failed (%s)", lead.id, type(err).__name__)
            error_kind = type(err).__name__
        try:
            for record in joined:
                if record.delivery is not None:
                    # Marked before it is finished, so the channel hub never sends this record a reply.
                    note = f"answered together with message {lead.id}"
                    await self.ingress.finish_delivery(record.id, "skipped", note)
                await self._end(record, reply, error_kind)
            await self._end(lead, reply, error_kind)
        finally:
            for record in [*joined, lead]:
                self._release(record.id)
            if observer is not None:
                observer.close()
            for listener in self._listeners:
                listener(lead)

    async def _end(self, record: IngressRecord, reply: TurnReply | None, error_kind: str) -> None:
        if reply is not None:
            await self.ingress.finish(record.id, reply)
        else:
            await self.ingress.fail(record.id, error_kind)

    def _release(self, ingress_id: int) -> None:
        watching = self._observers.pop(ingress_id, None)
        if watching is not None:
            watching.close()
        event = self._finished.pop(ingress_id, None)
        if event is not None:
            event.set()

    def on_finished(self, listener: Callable[[IngressRecord], None]) -> None:
        """Called with the record (as claimed) after each run, done or failed; must not block."""
        self._listeners.append(listener)

    async def sweep(self) -> None:
        """Re-queues messages a crashed run left behind and drains every session with queued messages."""
        for record in await self.ingress.processing():
            if record.session_id in self._draining:
                continue
            try:
                async with self._locks.hold(record.tenant_id, record.session_id, timeout_s=0):
                    status = await self.ingress.requeue(record.id, max_attempts=self.settings.max_attempts)
            except SessionBusyError:
                continue  # a live run in another process holds it
            if status is not None:
                logger.warning("message %d was left processing; now %s", record.id, status)
        for tenant_id, session_id in await self.ingress.queued_sessions():
            if tenant_id == self.tenant_id:
                self.schedule(session_id)

    async def run_sweeper(self) -> None:
        while True:
            try:
                await self.sweep()
            except Exception as err:  # the next sweep tries again
                logger.warning("sweep failed (%s)", type(err).__name__)
            await asyncio.sleep(self.settings.sweep_interval_s)

    async def close(self, grace_s: float = CLOSE_GRACE_S) -> None:
        """Lets running turns finish for ``grace_s``, then cancels them; cancelled messages stay processing
        and are queued again by the next sweep."""
        if not self._tasks:
            return
        _, pending = await asyncio.wait(set(self._tasks), timeout=grace_s)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
