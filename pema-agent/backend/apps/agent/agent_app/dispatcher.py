"""Runs inbound messages from any channel: store first, then one turn at a time per session, in arrival order.

``accept`` stores the message (once per channel message id) and starts a drain of its session in the
background. A drain holds the session's run lock and runs every queued message of the session, oldest first;
a caller waits for its own message with ``wait``. The sweeper finds messages left ``processing`` by a crashed
process (their session lock is free) and queues them again, or gives up after ``max_attempts``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
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
    Message,
    ModelError,
    SessionStore,
    ToolResultBlock,
    ToolUseBlock,
    Tracer,
    run_turn,
)
from agentcore.channels import PROACTIVE, InboundMessage, in_group, session_id_for

CLOSE_GRACE_S: Final = 10.0
TYPING_KEEP: Final = 512
"""Conversations whose typing signal is remembered; past this the expired ones are dropped."""

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
    wait_by_prefix: Mapping[str, tuple[float, float]] = field(default_factory=dict[str, tuple[float, float]])
    """Channel name prefix -> (debounce_s, max_wait_s) for the channels that start with it (a chat platform
    where people send a message in pieces waits longer than a test console); the longest prefix wins."""
    typing_hold_s: float = 5.0
    """How long a typing signal from the person keeps the wait going (0 ignores the signals)."""
    typing_max_wait_s: float = 30.0
    """The longest a conversation waits when the person keeps typing."""

    def mode_for(self, channel: str) -> QueueMode:
        return self.queue_by_channel.get(channel, self.queue_mode)

    def wait_for(self, channel: str) -> tuple[float, float]:
        """(debounce_s, max_wait_s) of this channel."""
        matching = [prefix for prefix in self.wait_by_prefix if channel.startswith(prefix)]
        if not matching:
            return self.debounce_s, self.max_wait_s
        return self.wait_by_prefix[max(matching, key=len)]


@dataclass(frozen=True, slots=True)
class TokenBudget:
    """Tokens (prompt, cached ones included, and generated) turns may use in one local day. Checked before a
    turn, so the turn that crosses the line still ends; a turn refused fails with ``token_budget``."""

    per_session_per_day: int = 2_000_000
    per_day: int = 50_000_000
    """Every session of the agent together."""

    def spent(self, session: int, total: int) -> str | None:
        if session >= self.per_session_per_day:
            return "this conversation's daily token budget is spent"
        if total >= self.per_day:
            return "the agent's daily token budget is spent"
        return None


class BudgetSpentError(Exception):
    """The turn is not run: a daily token budget is spent."""


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
        over_budget: Callable[[str, str], Awaitable[str | None]] | None = None,
    ) -> None:
        """``over_budget(tenant_id, session_id)`` says why a turn of that session may not run now, or None."""
        self._agent = agent
        self._before_turn = before_turn
        self._over_budget = over_budget
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
        self._typing_until: dict[tuple[str, str], float] = {}

    def note_typing(self, channel: str, conversation_id: str) -> None:
        """The person of this conversation is typing: the wait for the rest of their burst goes on a little
        longer (``typing_hold_s`` from now, within ``typing_max_wait_s`` of when the wait began)."""
        hold = self.settings.typing_hold_s
        if hold <= 0:
            return
        now = time.monotonic()
        if len(self._typing_until) > TYPING_KEEP:
            self._typing_until = {key: until for key, until in self._typing_until.items() if until > now}
        self._typing_until[(channel, conversation_id)] = now + hold

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

    async def history(self, channel: str, conversation_id: str, limit: int) -> list[Message]:
        """The newest ``limit`` messages of the chat's current session, oldest first (what plugins read
        with ``ctx.chat_history``)."""
        session_id = await self.session_for(channel, conversation_id)
        return (await self.store.load(self.tenant_id, session_id))[-limit:]

    async def reset(self, channel: str, conversation_id: str) -> str:
        """Starts the conversation over; returns its new session id. The old session stays readable."""
        epoch = await self._conversations.reset(self.tenant_id, channel, conversation_id)
        return session_id_for(self.agent.profile.agent.name, channel, conversation_id, epoch)

    async def accept(
        self, inbound: InboundMessage, *, observer: StreamObserver | None = None, deliver: bool = False
    ) -> tuple[IngressRecord, bool]:
        """Stores the message and starts its session's drain; returns the record and whether it is new. With
        ``deliver`` the reply goes out through the message's channel once the turn is over."""
        inbound = _without_nul(inbound)
        session_id = await self.session_for(inbound.channel, inbound.conversation_id)
        self._typing_until.pop(
            (inbound.channel, inbound.conversation_id), None
        )  # the message is out of the box
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
                        if mode != "followup" and not _proactive(queued):  # nobody types a proactive one
                            await self._quiet(queued)
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

    async def _quiet(self, lead: IngressRecord) -> None:
        """Waits until no new message came for the channel's ``debounce_s`` (at most its ``max_wait_s``), so a
        burst of short messages becomes one turn. While the person is heard typing the wait goes on, up to
        ``typing_max_wait_s``."""
        settings = self.settings
        session_id = lead.session_id
        debounce_s, max_wait_s = settings.wait_for(lead.channel)
        key = (lead.channel, lead.conversation_id)
        started = time.monotonic()
        count = len(await self.ingress.queued_in_session(self.tenant_id, session_id, settings.max_batch + 1))
        while True:
            typed = self._typing_until.get(key, 0.0) > started
            cap = started + (max(max_wait_s, settings.typing_max_wait_s) if typed else max_wait_s)
            if (pause := min(debounce_s, cap - time.monotonic())) <= 0:
                return
            await asyncio.sleep(pause)
            now = len(
                await self.ingress.queued_in_session(self.tenant_id, session_id, settings.max_batch + 1)
            )
            if now == count and time.monotonic() >= self._typing_until.get(key, 0.0):
                return
            count = now

    async def _gather(self, lead: IngressRecord, limit: int) -> list[IngressRecord]:
        """Claims the next queued messages of the same person, in order, up to the first one from someone
        else: a reply never jumps ahead of another person's message. A proactive message (a reminder, a case's
        turn) carries the person's id but is the agent's own: it never joins a turn nor takes others into its
        own, since only the lead's answer is sent and a ``SKIP`` would swallow the person's reply."""
        if limit <= 0 or _proactive(lead):
            return []
        joined: list[IngressRecord] = []
        for record in await self.ingress.queued_in_session(self.tenant_id, lead.session_id, limit):
            if record.user_id != lead.user_id or _proactive(record):
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
            if self._over_budget is not None:
                # shortcut: turns of other sessions running now are not counted yet, so the agent budget
                # may be passed by up to max_concurrent_turns turns; reserve tokens first if that matters.
                spent = await self._over_budget(self.tenant_id, lead.session_id)
                if spent is not None:
                    raise BudgetSpentError(spent)
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
                conversation_id=lead.conversation_id,
                is_group=in_group(lead.metadata),
                message_id=lead.external_id,
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
        except BudgetSpentError as err:
            logger.warning("message %d not run: %s", lead.id, err)
            error_kind = "token_budget"
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


def _without_nul(inbound: InboundMessage) -> InboundMessage:
    """Postgres text and jsonb refuse NUL, so a message carrying one could never be stored nor answered."""

    def clean(value: str) -> str:
        return value.replace("\x00", "")

    return replace(
        inbound,
        conversation_id=clean(inbound.conversation_id),
        user_id=clean(inbound.user_id),
        message_id=clean(inbound.message_id),
        text=clean(inbound.text),
        metadata={clean(key): clean(value) for key, value in inbound.metadata.items()},
    )


def _proactive(record: IngressRecord) -> bool:
    return record.metadata.get(PROACTIVE) == "1"
