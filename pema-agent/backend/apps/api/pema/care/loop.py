"""The event-driven turn of a care agent (PLAN-AI01-M sections 2, 3, 4, 5 and 11). New module (not a port).

``CareEventBus.publish`` is where the sources meet (the Zalo webhook of C1/C2, the CRM rule engine of B2,
the scheduler of S, the dashboard): it finds the care agent of ``event.patient_ref`` and pushes the event on
the priority queue. ``CareTurnWorker`` takes them one at a time (one GPU) and calls
``CareTurnRunner.run_turn``.

``run_turn(care_agent_id, event)`` in order:

1. the agent is paused (kill switch of this agent) -> nothing happens, ``paused`` row in ``actions_log``;
2. ``conversation_control.state`` is not ``AUTO`` (``HANDOFF_ROUTING`` or ``STAFF``, PLAN-M section 5) -> the
   agent is silent to the patient: the history is kept by the channel pipeline and, when a ``SuggestionSink``
   is wired (M2b), a PATIENT message gets a suggestion for the staff (``review_item`` kind
   ``suggestion``, never sent); everything else only writes a ``paused`` row. M2c: a scheduled REMINDER
   (milestone due, overdue, no-show, dormant, birthday, session completed) is recorded as paused with its
   prepared text for the owning staff member when a ``ReminderPauser`` is wired (``pema.care.reminders``);
   nothing is sent and no staff task is made. A reminder that comes back after the release (payload
   ``late_original_at``) carries S's label "(nhắc trễ, lịch gốc HH:MM)" in front of the text, draft or send;
3. the PII-masked context is loaded (``PatientContextLoader``), the skill ``handoff`` is asked (M2b). A
   ``handoff`` verdict stops the turn here: when a ``HandoffRequester`` is wired (``CareControl``) it
   moves the conversation to ``HANDOFF_ROUTING`` and sends the one holding message; without one (the stand-in
   ``AlwaysAnswer`` never hands off) the turn only logs it;
4. the shared pipeline is called with the care-agent persona (``Harness``) and returns a decision;
5. the decision is acted on by autonomy level (M3 ``AutonomyPolicy``; the stand-in is L0): a draft goes to a
   person as a ``review_item``. Always a draft, whatever the level: a birthday (PLAN-M section 11, rule 4:
   a birthday is never sent automatically) and a patient with no verified channel (a person sends it by hand,
   PLAN-M section 14). Nothing to the patient while ``marketing_opt_out`` and the decision is marketing;
6. an automatic send respects the send window (outside it the text is queued for the start of the next window
   through ``Scheduler``, no cap slot is taken yet) and, when it is proactive (the patient did not just
   write), the per-patient daily cap through S's atomic ``ProactiveSendGuard.reserve_slot`` (the key
   ``patient:<patient_id>:<account_id>`` is the one of ``PolicyHooks.proactive_cap`` for ``patient_channel``;
   the day is the day of ``BOT_TIMEZONE`` like S's counters). A cap that is full sends nothing and writes a
   ``paused`` row. A slot is given back when the send fails.

Every turn writes one row to ``agent.actions_log`` and sets ``care_agents.last_tick_at``. The reason of a
non-send is in ``action_type`` as ``<what>:<why>`` (the table has no reason column). The clock is read once at
the start of a turn: one turn is one instant (the invariant of S's ``proactive_send_guard``).

Logs carry the care agent id, the event kind and the outcome only; never a text, a name or a phone.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pema.care.events import CareEvent, EventKind, is_proactive
from pema.care.models import (
    PATIENT_CHANNEL_PROFILE,
    ActionDisposition,
    ControlState,
)
from pema.care.ports import (
    AlwaysAnswer,
    AutonomyPolicy,
    CareAgentSnapshot,
    CareStore,
    ChannelSend,
    ChannelTarget,
    DeferredSend,
    HandoffAction,
    HandoffDecider,
    HandoffRequester,
    HandoffVerdict,
    Harness,
    HarnessDecision,
    HarnessRequest,
    L0Autonomy,
    PatientContext,
    PatientContextLoader,
    PatientDirectory,
    ReminderPauser,
    ReviewSink,
    Scheduler,
    SendOutcome,
    SendWindowProvider,
    SuggestionSink,
)
from pema.care.priority import CarePriorityQueue
from pema.care.reminders import LATE_ORIGINAL_AT
from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_int
from pema.scheduler.scheduled_job_prompt import with_late_label
from pema.shared.zone_time import today_key
from pema_contracts.scheduler import ProactiveSendGuard

logger = logging.getLogger(__name__)

CARE_PERSONA = "care_agent"
"""Key of the persona the harness uses for a care turn (resolved by the wiring package)."""
CARE_SUGGEST_PERSONA = "care_agent_suggest"
"""Persona of a turn that writes a suggestion for staff (the conversation is with a person); never sent."""

# ``action_type`` vocabulary (``<what>:<why>``)
SKIPPED_AGENT_PAUSED = "turn:skipped_agent_paused"
SKIPPED_STATE_PREFIX = "turn:skipped_state_"
HANDOFF_REQUESTED = "turn:handoff_requested"
HANDOFF_FAILED = "turn:handoff_failed"
SUGGESTED_STATE_PREFIX = "suggestion:state_"
SUGGESTION_FAILED = "suggestion:failed"
NO_ACTION = "turn:no_action"
FAILED_HARNESS = "turn:failed_harness"
FAILED_CONTEXT = "turn:failed_context"
MARKETING_OPT_OUT = "send:paused_marketing_opt_out"
DEFERRED_TO_WINDOW = "send:deferred_to_window"
PAUSED_PROACTIVE_CAP = "send:paused_proactive_cap"
FAILED_SEND = "send:failed"
DRAFT_FAILED = "draft:failed"
DRAFT_PREFIX = "draft:"
"""``draft:<reason>``: ``autonomy``, ``birthday_never_auto`` or ``no_verified_channel``."""


class TurnStatus(StrEnum):
    UNKNOWN_AGENT = "unknown_agent"
    SKIPPED_PAUSED = "skipped_paused"
    SKIPPED_STATE = "skipped_state"
    HANDOFF = "handoff"
    SUGGESTED = "suggested"
    REMINDER_PAUSED = "reminder_paused"
    NO_ACTION = "no_action"
    FAILED = "failed"
    DRAFTED = "drafted"
    DEFERRED = "deferred"
    CAPPED = "capped"
    BLOCKED_OPT_OUT = "blocked_opt_out"
    SENT = "sent"


@dataclass(frozen=True)
class TurnOutcome:
    status: TurnStatus
    run_at: datetime | None = None
    """For ``DEFERRED``: when the queued message becomes sendable."""


type Clock = Callable[[], datetime]


class CareTurnRunner:
    def __init__(
        self,
        *,
        store: CareStore,
        context_loader: PatientContextLoader,
        harness: Harness,
        channel: ChannelSend,
        scheduler: Scheduler,
        review: ReviewSink,
        window: SendWindowProvider,
        guard: ProactiveSendGuard,
        clock: Clock,
        handoff: HandoffDecider | None = None,
        autonomy: AutonomyPolicy | None = None,
        cap_per_day: int | None = None,
        requester: HandoffRequester | None = None,
        suggestions: SuggestionSink | None = None,
        reminders: ReminderPauser | None = None,
    ) -> None:
        self._store = store
        self._context_loader = context_loader
        self._harness = harness
        self._channel = channel
        self._scheduler = scheduler
        self._review = review
        self._window = window
        self._guard = guard
        self._clock = clock
        self._handoff: HandoffDecider = handoff if handoff is not None else AlwaysAnswer()
        self._autonomy: AutonomyPolicy = autonomy if autonomy is not None else L0Autonomy()
        self._cap_per_day = cap_per_day
        self._requester = requester
        self._suggestions = suggestions
        self._reminders = reminders

    async def run_turn(self, care_agent_id: UUID, event: CareEvent) -> TurnOutcome:
        now = self._clock()
        agent = await self._store.get_care_agent(care_agent_id)
        if agent is None:
            logger.warning("care turn for an unknown care agent", extra={"care_agent_id": str(care_agent_id)})
            return TurnOutcome(TurnStatus.UNKNOWN_AGENT)
        outcome = await self._run(agent, event, now)
        await self._store.touch_last_tick([agent.id], now)
        logger.info(
            "care turn",
            extra={
                "care_agent_id": str(agent.id),
                "event_kind": event.kind.value,
                "outcome": outcome.status.value,
            },
        )
        return outcome

    # ------------------------------------------------------------------------------------ steps
    async def _log(
        self,
        agent: CareAgentSnapshot,
        action_type: str,
        disposition: ActionDisposition,
        now: datetime,
        depth: str | None = None,
    ) -> None:
        await self._store.record_action(
            agent.id, action_type=action_type, disposition=disposition.value, depth=depth, at=now
        )

    async def _run(self, agent: CareAgentSnapshot, event: CareEvent, now: datetime) -> TurnOutcome:
        if agent.paused:
            await self._log(agent, SKIPPED_AGENT_PAUSED, ActionDisposition.PAUSED, now)
            return TurnOutcome(TurnStatus.SKIPPED_PAUSED)

        state = await self._store.get_control_state(agent.patient_id)
        if state is not ControlState.AUTO:
            if self._reminders is not None and await self._reminders.pause_event(agent, event, now):
                return TurnOutcome(TurnStatus.REMINDER_PAUSED)
            if self._suggestions is not None and event.kind is EventKind.PATIENT_MESSAGE:
                return await self._suggest(agent, event, state, now)
            await self._log(agent, SKIPPED_STATE_PREFIX + state.value.lower(), ActionDisposition.PAUSED, now)
            return TurnOutcome(TurnStatus.SKIPPED_STATE)

        try:
            context = await self._context_loader.load(agent, event)
        except Exception as exc:
            logger.error(
                "care context failed", extra={"care_agent_id": str(agent.id), "error": type(exc).__name__}
            )
            await self._log(agent, FAILED_CONTEXT, ActionDisposition.PAUSED, now)
            return TurnOutcome(TurnStatus.FAILED)

        verdict = await self._handoff.decide(agent, event, context)
        if verdict.action is HandoffAction.HANDOFF:
            return await self._hand_off(agent, event, context, verdict, now)

        try:
            decision = await self._harness.process(
                HarnessRequest(
                    care_agent_id=agent.id,
                    profile=agent.profile or PATIENT_CHANNEL_PROFILE,
                    persona=CARE_PERSONA,
                    event=event,
                    context=context,
                )
            )
        except Exception as exc:
            logger.error(
                "care harness failed", extra={"care_agent_id": str(agent.id), "error": type(exc).__name__}
            )
            await self._log(agent, FAILED_HARNESS, ActionDisposition.PAUSED, now)
            return TurnOutcome(TurnStatus.FAILED)

        text = decision.text.strip() if decision.text is not None else ""
        if not text:
            await self._log(agent, NO_ACTION, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.NO_ACTION)
        late_from = event.payload.get(LATE_ORIGINAL_AT)
        if isinstance(late_from, str):
            text = with_late_label(text, late_from, bot_time_zone())
        return await self._act(agent, event, context, decision, text, now)

    async def _hand_off(
        self,
        agent: CareAgentSnapshot,
        event: CareEvent,
        context: PatientContext,
        verdict: HandoffVerdict,
        now: datetime,
    ) -> TurnOutcome:
        depth = verdict.decision.depth.value if verdict.decision is not None else None
        if self._requester is not None and verdict.decision is not None:
            try:
                await self._requester.request_handoff(agent, event, context, verdict.decision, now)
            except Exception as exc:  # the state did not change, so the next event decides again
                logger.error(
                    "care handoff failed", extra={"care_agent_id": str(agent.id), "error": type(exc).__name__}
                )
                await self._log(agent, HANDOFF_FAILED, ActionDisposition.PAUSED, now, depth)
                return TurnOutcome(TurnStatus.FAILED)
        await self._log(agent, HANDOFF_REQUESTED, ActionDisposition.PAUSED, now, depth)
        return TurnOutcome(TurnStatus.HANDOFF)

    async def _suggest(
        self, agent: CareAgentSnapshot, event: CareEvent, state: ControlState, now: datetime
    ) -> TurnOutcome:
        """The conversation is with a person: write what the agent WOULD say as a suggestion for staff. It is
        never sent and the skill ``handoff`` is not asked again (a person already has the patient)."""
        sink = self._suggestions
        if sink is None:
            return TurnOutcome(TurnStatus.SKIPPED_STATE)
        try:
            context = await self._context_loader.load(agent, event)
            decision = await self._harness.process(
                HarnessRequest(
                    care_agent_id=agent.id,
                    profile=agent.profile or PATIENT_CHANNEL_PROFILE,
                    persona=CARE_SUGGEST_PERSONA,
                    event=event,
                    context=context,
                )
            )
        except Exception as exc:
            logger.error(
                "care suggestion failed", extra={"care_agent_id": str(agent.id), "error": type(exc).__name__}
            )
            await self._log(agent, SUGGESTION_FAILED, ActionDisposition.PAUSED, now)
            return TurnOutcome(TurnStatus.FAILED)
        text = decision.text.strip() if decision.text is not None else ""
        if not text:
            await self._log(agent, NO_ACTION, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.NO_ACTION)
        item_id = await sink.create_suggestion(agent, context.patient_ref, text, state)
        if item_id is None:
            await self._log(agent, SUGGESTION_FAILED, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.FAILED)
        await self._log(
            agent, SUGGESTED_STATE_PREFIX + state.value.lower(), ActionDisposition.PAUSED, now, decision.depth
        )
        return TurnOutcome(TurnStatus.SUGGESTED)

    async def _act(
        self,
        agent: CareAgentSnapshot,
        event: CareEvent,
        context: PatientContext,
        decision: HarnessDecision,
        text: str,
        now: datetime,
    ) -> TurnOutcome:
        proactive = is_proactive(event)
        if proactive and decision.marketing and context.marketing_opt_out:
            await self._log(agent, MARKETING_OPT_OUT, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.BLOCKED_OPT_OUT)

        target = context.channel
        if event.kind is EventKind.BIRTHDAY:
            return await self._draft(agent, context, decision, text, "birthday_never_auto", now)
        if target is None:
            return await self._draft(agent, context, decision, text, "no_verified_channel", now)
        if not await self._autonomy.may_auto_send(agent, decision, now):
            return await self._draft(agent, context, decision, text, "autonomy", now)

        window = await self._window.get(agent.clinic_id)
        if not window.is_open(now):
            run_at = window.next_open(now)
            await self._scheduler.defer_send(
                DeferredSend(
                    care_agent_id=agent.id,
                    patient_id=agent.patient_id,
                    target=target,
                    text=text,
                    run_at=run_at,
                    dedupe_key=f"care:{agent.id}:{event.kind.value}:{event.occurred_at.isoformat()}",
                )
            )
            await self._log(agent, DEFERRED_TO_WINDOW, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.DEFERRED, run_at=run_at)

        scope_key = f"patient:{agent.patient_id}:{target.account_id}"
        day_key = today_key(bot_time_zone(), now)
        reserved = False
        if proactive:
            cap = (
                self._cap_per_day
                if self._cap_per_day is not None
                else get_tuning_int("SCHEDULER_MAX_PROACTIVE_PER_DAY")
            )
            slot = await self._guard.reserve_slot(scope_key, day_key, cap)
            if not slot.reserved:
                await self._log(agent, PAUSED_PROACTIVE_CAP, ActionDisposition.PAUSED, now, decision.depth)
                return TurnOutcome(TurnStatus.CAPPED)
            reserved = True

        outcome = await self._send(target, text, proactive)
        if not outcome.ok:
            if reserved:
                await self._guard.refund_slot(scope_key, day_key)
            await self._log(agent, FAILED_SEND, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.FAILED)
        await self._log(agent, decision.action_type, ActionDisposition.AUTO_SENT, now, decision.depth)
        return TurnOutcome(TurnStatus.SENT)

    async def _send(self, target: ChannelTarget, text: str, proactive: bool) -> SendOutcome:
        try:
            return await self._channel.send(target, text, proactive=proactive)
        except Exception as exc:
            logger.error("care send raised", extra={"error": type(exc).__name__})
            return SendOutcome(ok=False, error_code="exception")

    async def _draft(
        self,
        agent: CareAgentSnapshot,
        context: PatientContext,
        decision: HarnessDecision,
        text: str,
        reason: str,
        now: datetime,
    ) -> TurnOutcome:
        item_id = await self._review.create_draft(agent, context.patient_ref, text, reason)
        if item_id is None:
            await self._log(agent, DRAFT_FAILED, ActionDisposition.PAUSED, now, decision.depth)
            return TurnOutcome(TurnStatus.FAILED)
        await self._log(agent, DRAFT_PREFIX + reason, ActionDisposition.PAUSED, now, decision.depth)
        return TurnOutcome(TurnStatus.DRAFTED)


class CareEventBus:
    """Where the event sources meet: resolves the care agent of the patient and queues the turn."""

    def __init__(self, directory: PatientDirectory, queue: CarePriorityQueue) -> None:
        self._directory = directory
        self._queue = queue

    async def publish(self, event: CareEvent) -> bool:
        """``False`` when no care agent belongs to ``event.patient_ref`` (the event is dropped and logged)."""
        care_agent_id = await self._directory.care_agent_id_for(event.patient_ref)
        if care_agent_id is None:
            logger.warning(
                "care event for a patient without care agent", extra={"event_kind": event.kind.value}
            )
            return False
        self._queue.push(care_agent_id, event)
        return True


class CareTurnWorker:
    """Sequential consumer of the queue (a 12 GB GPU runs one turn at a time)."""

    def __init__(self, queue: CarePriorityQueue, runner: CareTurnRunner) -> None:
        self._queue = queue
        self._runner = runner

    async def _run(self, care_agent_id: UUID, event: CareEvent) -> TurnOutcome | None:
        try:
            return await self._runner.run_turn(care_agent_id, event)
        except Exception as exc:  # a broken turn must not stop the worker; the next event runs
            logger.error(
                "care turn crashed",
                extra={"care_agent_id": str(care_agent_id), "error": type(exc).__name__},
            )
            return None

    async def run_next(self) -> bool:
        """Run the next queued turn; ``False`` when the queue was empty."""
        item = self._queue.pop_nowait()
        if item is None:
            return False
        await self._run(item.care_agent_id, item.event)
        return True

    async def run_until_idle(self) -> int:
        count = 0
        while await self.run_next():
            count += 1
        return count

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            getter = asyncio.ensure_future(self._queue.pop())
            stopper = asyncio.ensure_future(stop.wait())
            done, _ = await asyncio.wait({getter, stopper}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                item = getter.result()
                stopper.cancel()
                await self._run(item.care_agent_id, item.event)
            else:
                getter.cancel()
