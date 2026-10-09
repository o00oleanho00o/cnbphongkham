"""Runs inbound messages from any channel: store first, then one turn at a time per session, in arrival order.

``accept`` stores the message (once per channel message id) and starts a drain of its session in the
background. A drain holds the session's run lock and runs every queued message of the session, oldest first;
a caller waits for its own message with ``wait``. The sweeper finds messages left ``processing`` by a crashed
process (their session lock is free) and queues them again, or gives up after ``max_attempts``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
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

    def close(self) -> None:
        self.events.put_nowait(None)


class Dispatcher:
    def __init__(
        self,
        agent: Agent,
        *,
        store: SessionStore,
        tracer: Tracer,
        ingress: IngressStore,
        conversations: ConversationStore,
        locks: SessionLocks,
        sessions: PostgresSessionStore | None = None,
        settings: DispatchSettings | None = None,
    ) -> None:
        self.agent = agent
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

    @property
    def tenant_id(self) -> str:
        return self.settings.tenant_id

    async def session_for(self, channel: str, conversation_id: str) -> str:
        epoch = await self._conversations.epoch(self.tenant_id, channel, conversation_id)
        return session_id_for(self.agent.profile.agent.name, channel, conversation_id, epoch)

    async def reset(self, channel: str, conversation_id: str) -> str:
        """Starts the conversation over; returns its new session id. The old session stays readable."""
        epoch = await self._conversations.reset(self.tenant_id, channel, conversation_id)
        return session_id_for(self.agent.profile.agent.name, channel, conversation_id, epoch)

    async def accept(
        self, inbound: InboundMessage, *, observer: StreamObserver | None = None
    ) -> tuple[IngressRecord, bool]:
        """Stores the message and starts its session's drain; returns the record and whether it is new."""
        session_id = await self.session_for(inbound.channel, inbound.conversation_id)
        record, created = await self.ingress.accept(self.tenant_id, inbound, session_id)
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
                        claimed = await self.ingress.claim(queued.id)
                        if claimed is not None:
                            await self._process(claimed)
        except Exception as err:  # the messages stay queued or processing; the sweeper picks them up
            logger.warning("drain of session %s stopped (%s)", session_id, type(err).__name__)
        finally:
            self._draining.discard(session_id)
            self._wanted.discard(session_id)

    async def _process(self, record: IngressRecord) -> None:
        observer = self._observers.pop(record.id, None)
        agent = self.agent
        try:
            if self._sessions is not None:
                await self._sessions.open_session(
                    self.tenant_id, record.session_id, channel=record.channel, user_id=record.user_id
                )
            result = await run_turn(
                session_id=record.session_id,
                user_text=record.text,
                prompt=agent.prompt,
                model=agent.model,
                tools=agent.tools,
                store=self.store,
                policy=agent.policy,
                tenant_id=self.tenant_id,
                user_id=record.user_id,
                channel=record.channel,
                context=agent.context,
                observer=observer,
                hooks=agent.hooks,
                tracer=self._tracer,
            )
        except ModelError as err:
            await self.ingress.fail(record.id, err.kind)
        except Exception as err:
            logger.warning("message %d failed (%s)", record.id, type(err).__name__)
            await self.ingress.fail(record.id, type(err).__name__)
        else:
            await self.ingress.finish(record.id, TurnReply.of(result))
        finally:
            if observer is not None:
                observer.close()
            event = self._finished.pop(record.id, None)
            if event is not None:
                event.set()

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
