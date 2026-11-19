"""The case engine: wakes cases, runs their nodes, keeps the hard limits and writes down what it did.

Plugins declare kinds of case (``ctx.register_case``) and open or wake cases (``ctx.cases``); the engine knows
none of them by name. Three things wake a case: the clock (``wake_at`` came), a message of the customer in its
chat (``on_inbound``), and an event a plugin reports (``wake``). Before every node the rules of
``agentcore.cases.blocked`` are asked; a ``TurnNode`` goes into the chat's queue like any proactive message
(``Proactive.send_to``), so the turn takes the chat's own lock and the usual way out. The two steering tools
(``case_done``, ``case_wait_until``) hand their decision to ``take``, which keeps it in the database for that
case and turn, found from the turn's message id; a turn of the customer cannot steer a case.

The engine holds no lock of the chat: the turn does, and holding it here would wait on itself. Two runs of
one case are kept apart by the record's ``version`` (the one that saves second drops its result) and by the
message id ``case:<id>:<turn>``, which the queue takes once. If the service stops during a turn, the case is
still at that turn: the next pass sends the same message id, the queue hands back the turn already there, and
its decision is read from the database.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from agent_app.cases.store import CaseStore
from agent_app.ingress import SessionBusyError
from agent_app.plugins.host import Proactive
from agentcore import ToolContext, ToolSpec
from agentcore.cases import (
    CaseRecord,
    CaseSpec,
    CodeNode,
    Decision,
    TurnNode,
    after_error,
    apply,
    blocked,
    decision_from_json,
    decision_to_json,
    make_case_tools,
    new_record,
    parse_turn_message_id,
    state_of,
    turn_message_id,
    turn_text,
)
from agentcore.channels import PROACTIVE, InboundMessage, in_group

NO_CASE: Final = "There is no case running in this chat: case tools work only during a case's turn."
MOVED_ON: Final = "This case has moved on since this turn began; nothing was changed."
TRY_PREFIX: Final = "case-try:"
"""Message id of an admin's test turn: not a case's turn id, so the steering tools refuse in it."""

logger = logging.getLogger(__name__)

SessionFor = Callable[[str, str], Awaitable[str]]
"""(channel, conversation_id) -> the chat's current session id."""


@dataclass(frozen=True, slots=True)
class CasesConfig:
    """What an admin chose (agent settings): every case is off until switched on."""

    enabled: bool = False
    per_person_per_day: int = 2


@dataclass(frozen=True, slots=True)
class EngineSettings:
    tick_s: float = 5.0
    per_pass: int = 20
    """Cases run in one pass."""
    max_nodes_per_pass: int = 10
    """Nodes one case may run in a row before the next pass (open after open: code nodes in a chain)."""
    error_retry: timedelta = timedelta(minutes=5)
    """A node that raised is tried again this much later (until the case's deadline)."""


@dataclass(frozen=True, slots=True)
class TryOutcome:
    """What an admin's "send a test now" did: written to, or why not."""

    sent: bool
    why: str = ""


class CaseEngine:
    def __init__(
        self,
        store: CaseStore,
        specs: Callable[[], Mapping[str, tuple[str, CaseSpec]]],
        *,
        config: Callable[[], CasesConfig],
        zone: Callable[[], ZoneInfo],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        settings: EngineSettings | None = None,
        lock: Callable[[str], contextlib.AbstractAsyncContextManager[None]] | None = None,
    ) -> None:
        """``lock(name)`` is tried before each pass (``SessionBusyError`` when another process holds it), so
        one process of the agent runs the passes; None (one process) runs every pass."""
        self._store = store
        self._specs = specs
        self._config = config
        self._zone = zone
        self._clock = clock
        self.settings = settings or EngineSettings()
        self._lock = lock
        self._proactive: Proactive | None = None
        self._session_for: SessionFor | None = None
        self._nudge = asyncio.Event()

    @property
    def store(self) -> CaseStore:
        return self._store

    def attach(self, proactive: Proactive, session_for: SessionFor) -> None:
        """How turns reach the chat; set once the service has its dispatcher (``agent serve``)."""
        self._proactive = proactive
        self._session_for = session_for

    def tools(self) -> list[ToolSpec[Any]]:
        return list(make_case_tools(self))

    # --- the steering tools ---

    async def take(self, ctx: ToolContext, decision: Decision) -> str | None:
        turn = parse_turn_message_id(ctx.message_id)
        if turn is None:
            return NO_CASE
        case_id, number = turn
        kept = await self._store.set_pending(
            case_id, number, ctx.channel or "", ctx.conversation_id or "", decision_to_json(decision)
        )
        return None if kept else MOVED_ON

    # --- what plugins do (ctx.cases) ---

    def _spec(self, plugin: str, kind: str) -> CaseSpec:
        found = self._specs().get(kind)
        if found is None or found[0] != plugin:
            raise ValueError(f"plugin {plugin} has no case {kind}")
        return found[1]

    async def open_for(
        self,
        plugin: str,
        kind: str,
        key: str,
        *,
        channel: str,
        conversation_id: str,
        user_id: str,
        state: BaseModel,
    ) -> CaseRecord:
        spec = self._spec(plugin, kind)
        if self._session_for is None:
            raise RuntimeError("the case engine is not attached to the service yet")
        now = self._clock()
        record = new_record(
            spec,
            key=key,
            channel=channel,
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=await self._session_for(channel, conversation_id),
            state=state,
            now=now,
        )
        stored, created = await self._store.open(plugin, record)
        if created:
            await self._store.log(stored.id, "opened", stored.node, {"goal": stored.goal}, now)
            self._nudge.set()
        return stored

    async def wake_for(self, plugin: str, kind: str, key: str, patch: Mapping[str, Any] | None) -> bool:
        spec = self._spec(plugin, kind)
        record = await self._store.live(kind, key)
        if record is None:
            return False
        return await self._wake(spec, record, dict(patch or {}), "event")

    async def get_for(self, plugin: str, kind: str, key: str) -> CaseRecord | None:
        self._spec(plugin, kind)
        return await self._store.live(kind, key)

    async def room_today(self, plugin: str, kind: str, channel: str, user_id: str) -> int:
        """Messages a case of ``kind`` may still send this person today: the cap ``blocked`` checks (the
        kind's budget, lowered by the setting) less what every case sent them since the local day began."""
        spec = self._spec(plugin, kind)
        cap = min(spec.budget.per_person_per_day, self._config().per_person_per_day)
        return max(0, cap - await self._sent_today(channel, user_id, self._clock()))

    # --- an admin ---

    async def wake_by_hand(self, case_id: int) -> bool:
        """An admin's "run now": the case runs at the next pass, every check before its nodes as usual. False
        when there is no such live case, or its plugin is off."""
        record = await self._store.get(case_id)
        found = None if record is None else self._specs().get(record.kind)
        if record is None or found is None or record.status not in ("open", "waiting"):
            return False
        return await self._wake(found[1], record, {}, "admin")

    async def try_now(self, case_id: int) -> TryOutcome | None:
        """An admin's "send a test now": runs a copy of the case from where it is on a clock that jumps over
        every wait, up to its first turn, and sends that turn once (its own message id, so it cannot steer the
        case). The case itself is left as it was. The shared limits (the switch, a closed case, the counters,
        the person's daily cap) are asked with the real clock; the plugin's own hours are not: an admin chose
        to write. None when there is no such live case or its plugin is off."""
        record = await self._store.get(case_id)
        found = None if record is None else self._specs().get(record.kind)
        if record is None or found is None or record.status not in ("open", "waiting"):
            return None
        spec, config, now = found[1], self._config(), self._clock()
        copy, at = record, max(now, record.wake_at or now)
        for _ in range(self.settings.max_nodes_per_pass):
            node = spec.graph.node(copy.node)
            turn = isinstance(node, TurnNode)
            today = await self._sent_today(record.channel, record.user_id, now) if turn else 0
            block = blocked(
                spec,
                replace(copy, status="open"),
                now,
                enabled=config.enabled,
                sent_to_person_today=today,
                per_person_per_day=config.per_person_per_day,
                next_day=self._next_day(now),
            )
            if block is not None or node is None:
                return await self._tried(record, node, block.reason if block else "no node")
            if isinstance(node, TurnNode):
                return await self._try_turn(spec, record, copy, node, now)
            try:
                copy = apply(spec, copy, await node.run(state_of(spec, copy), at), at)
            except Exception as err:  # a plugin's node failing ends the test, never the case
                return await self._tried(record, node, f"{node.id} failed ({type(err).__name__})")
            if copy.status not in ("open", "waiting"):
                return await self._tried(record, node, f"the case would end: {copy.end_reason}")
            if copy.status == "waiting" and copy.wake_at is None:
                return await self._tried(record, node, "the case waits for the customer")
            at = max(at, copy.wake_at or at)
        return await self._tried(record, None, f"no turn within {self.settings.max_nodes_per_pass} steps")

    async def _try_turn(
        self, spec: CaseSpec, record: CaseRecord, copy: CaseRecord, node: TurnNode, now: datetime
    ) -> TryOutcome:
        proactive = self._proactive
        if proactive is None:
            return await self._tried(record, node, "no way to reach the chat")
        result = await proactive.send_to(
            channel=record.channel,
            conversation_id=record.conversation_id,
            user_id=record.user_id,
            message_id=f"{TRY_PREFIX}{record.id}:{now.strftime('%Y%m%d%H%M%S')}",
            instruction=turn_text(spec, copy, node, now),
        )
        if not result.counted:
            return await self._tried(record, node, f"the agent chose not to write ({result.note or 'skip'})")
        await self._store.log(record.id, "sent", node.id, {"by": "admin_try", "note": result.note}, now)
        return TryOutcome(sent=True)

    async def _tried(self, record: CaseRecord, node: CodeNode | TurnNode | None, why: str) -> TryOutcome:
        at = self._clock()
        await self._store.log(
            record.id, "blocked", node.id if node else None, {"by": "admin_try", "why": why}, at
        )
        return TryOutcome(sent=False, why=why)

    async def _wake(self, spec: CaseSpec, record: CaseRecord, patch: dict[str, Any], why: str) -> bool:
        now = self._clock()
        try:
            state = spec.state_model.model_validate({**record.state, **patch}).model_dump(mode="json")
        except ValidationError as err:
            count = err.error_count()
            raise ValueError(f"case {spec.kind}: the patch does not fit its state ({count} errors)") from err
        woken = replace(record, state=state, updated_at=now)
        if record.status == "waiting":
            woken = replace(woken, wake_at=now)
        saved = await self._store.save(woken)
        if saved is None:
            return False
        await self._store.log(saved.id, "woken", saved.node, {"by": why, "patch": sorted(patch)}, now)
        self._nudge.set()
        return True

    # --- the customer wrote ---

    async def on_inbound(self, message: InboundMessage) -> None:
        """A message of a chat came in (the channel hub calls this for every new one). The cases waiting in
        that chat hear it: ``stop_if`` may end them, otherwise those woken by the customer run next."""
        if in_group(message.metadata) or message.metadata.get(PROACTIVE) == "1":
            return
        specs = self._specs()
        for record in await self._store.waiting_in_chat(message.channel, message.conversation_id):
            found = specs.get(record.kind)
            if found is None:
                continue
            spec = found[1]
            why = spec.stop_if(state_of(spec, record), message.text) if spec.stop_if is not None else None
            if why is not None:
                await self._close(record, "stopped", why, "the customer wrote")
            elif spec.wakes_on("customer_message"):
                await self._wake(spec, record, {}, "customer")

    # --- the loop ---

    async def run(self) -> None:
        while True:
            self._nudge.clear()
            try:
                await self.pass_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # the loop outlives any error of one pass
                logger.warning("case pass failed (%s)", type(err).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._nudge.wait(), timeout=self.settings.tick_s)

    async def pass_once(self) -> int:
        """Runs the cases that are due; how many it ran."""
        config = self._config()
        if not config.enabled or self._proactive is None:
            return 0
        try:
            async with self._lock("cases") if self._lock is not None else contextlib.nullcontext():
                return await self._run_due(config)
        except SessionBusyError:  # another process of the agent is running this pass
            return 0

    async def _run_due(self, config: CasesConfig) -> int:
        due = await self._store.due(self._clock(), self.settings.per_pass)
        # shortcut: one case after the other, so one turn at a time; run per chat in parallel if it is slow.
        for record in due:
            try:
                await self.step(record, config)
            except Exception:
                logger.exception("case %d failed", record.id)
        return len(due)

    async def step(self, record: CaseRecord, config: CasesConfig) -> CaseRecord:
        """Runs the case's nodes until it waits, ends, or ran ``max_nodes_per_pass``."""
        found = self._specs().get(record.kind)
        if found is None:  # its plugin is off: the case stays as it is until it comes back
            return record
        spec = found[1]
        for _ in range(self.settings.max_nodes_per_pass):
            now = self._clock()
            node = spec.graph.node(record.node)
            turn = isinstance(node, TurnNode)
            today = await self._sent_today(record.channel, record.user_id, now) if turn else 0
            block = blocked(
                spec,
                record,
                now,
                enabled=config.enabled,
                sent_to_person_today=today,
                per_person_per_day=config.per_person_per_day,
                next_day=self._next_day(now),
            )
            if block is not None:
                return await self._blocked(record, block.reason, block.retry_at, now)
            if node is None:  # ``blocked`` already refuses a pointer to no node
                return record
            try:
                record, decision = await self._run(spec, record, node, now)
            except Exception as err:  # a plugin's node failing costs this case one retry, not the loop
                logger.warning("case %d: node %s failed (%s)", record.id, node.id, type(err).__name__)
                return await self._retry_later(spec, record, node.id, type(err).__name__, now)
            try:
                after = apply(spec, record, decision, now)
            except ValueError as err:
                return await self._retry_later(spec, record, node.id, str(err), now)
            saved = await self._store.save(after)
            if saved is None:
                await self._store.log(record.id, "lost", node.id, {"why": "changed by another run"}, now)
                return record
            await self._store.log(saved.id, "decision", node.id, _described(decision, saved), now)
            record = saved
            if record.status != "open":
                return record
        return record

    async def _run(
        self, spec: CaseSpec, record: CaseRecord, node: CodeNode | TurnNode, now: datetime
    ) -> tuple[CaseRecord, Decision]:
        if isinstance(node, CodeNode):
            return record, await node.run(state_of(spec, record), now)
        proactive = self._proactive
        if proactive is None:
            raise RuntimeError("no way to reach the chat")
        result = await proactive.send_to(
            channel=record.channel,
            conversation_id=record.conversation_id,
            user_id=record.user_id,
            message_id=turn_message_id(record.id, record.turns),
            instruction=turn_text(spec, record, node, now),
        )
        kept = await self._store.pending(record.id, record.turns)
        decision = (decision_from_json(kept) if kept is not None else None) or Decision()
        sent = record.proactive_sent + result.counted
        record = replace(record, turns=record.turns + 1, proactive_sent=sent)
        if result.counted:
            # shortcut: a turn sent before the service stopped and sent again by id is logged twice, so the
            # daily cap may count it twice (it sends less, never more); count by (case, turn) if it matters.
            await self._store.log(record.id, "sent", node.id, {"note": result.note}, now)
        return record, decision

    async def _sent_today(self, channel: str, user_id: str, now: datetime) -> int:
        local = now.astimezone(self._zone())
        start = datetime.combine(local.date(), time(0), local.tzinfo)
        return await self._store.sent_since(channel, user_id, start)

    def _next_day(self, now: datetime) -> datetime:
        local = now.astimezone(self._zone())
        return datetime.combine(local.date() + timedelta(days=1), time(0), local.tzinfo)

    async def _blocked(
        self, record: CaseRecord, reason: str, retry_at: datetime | None, now: datetime
    ) -> CaseRecord:
        if reason == "disabled":  # the switch is off: cases keep their state, nothing runs
            return record
        if retry_at is not None:
            waiting = replace(record, status="waiting", wait_for="clock", wake_at=retry_at, updated_at=now)
            saved = await self._store.save(waiting)
            if saved is not None:
                detail = {"why": reason, "until": retry_at}
                await self._store.log(saved.id, "blocked", saved.node, detail, now)
            return saved or record
        return await self._close(record, "stopped", reason, "blocked")

    async def _retry_later(
        self, spec: CaseSpec, record: CaseRecord, node: str, why: str, now: datetime
    ) -> CaseRecord:
        """The node raised: the case waits, then runs the end of the node's error edge (or the node again)."""
        # shortcut: a turn that reached the queue before the error still runs, even if the node checked again
        # says no; withdraw the queued turn (ingress) when that matters.
        later = now + self.settings.error_retry
        after = after_error(spec, record, later, now)
        saved = await self._store.save(after)
        detail = {"why": why, "retry_at": after.wake_at, "next": after.node, "status": after.status}
        await self._store.log(record.id, "error", node, detail, now)
        return saved or record

    async def _close(self, record: CaseRecord, status: str, reason: str, kind: str) -> CaseRecord:
        now = self._clock()
        closed = replace(
            record,
            status="stopped" if status == "stopped" else "done",
            end_reason=reason[:300] or status,
            wait_for=None,
            wake_at=None,
            closed_at=now,
            updated_at=now,
        )
        saved = await self._store.save(closed)
        if saved is not None:
            await self._store.log(saved.id, "stopped", saved.node, {"why": reason, "by": kind}, now)
        return saved or record


def _described(decision: Decision, after: CaseRecord) -> dict[str, Any]:
    """What the log keeps of a decision: the outcome and why, never the state's values."""
    return {
        "status": after.status,
        "next": after.node,
        "wait_for": after.wait_for,
        "wake_at": after.wake_at,
        "end_reason": after.end_reason,
        "note": decision.note[:300],
        "patched": sorted(decision.patch),
    }
