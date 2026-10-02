"""The conversation control state machine of one patient (PLAN-AI01-M section 5). New module (not a port).

Zalo-agent's per-thread ``bot_enabled`` flag is the channel's on/off switch; this module extends the idea to
three states per patient, stored in ``agent.conversation_control``:

    AUTO --agent senses a person is needed--> HANDOFF_ROUTING --staff accepts--> STAFF
     ^                                                                              |
     +----------------- staff "release to the agent" (note, optional lower level) --+

* ``request_handoff`` (the agent, through the skill ``handoff``): ``AUTO -> HANDOFF_ROUTING``. One row in
  ``handoff_requests`` (candidates empty: M2c fills them) and **one** template holding message to the patient,
  however many events arrive while the round is open (the second ``request_handoff`` finds the round open and
  changes nothing, and the loop does not even ask the skill again: the state is no longer AUTO). A PII-masked
  summary of the context is stored with the request for the staff who is asked.
* ``accept`` (staff): ``HANDOFF_ROUTING -> STAFF``, ``staff_owner`` is set.
* ``decline`` (staff): audited; the state stays ``HANDOFF_ROUTING``. Picking the next candidate is M2c
  (``RoutingAdvance``); until it is wired the request simply stays open.
* M2c hooks (all optional, none changes a rule above): ``routing_start`` builds the chain and asks the first
  candidate right after a round opens; ``notices`` may replace the text of the ONE message of the round
  (outside clinic hours: the D5 emergency template with the on-call number, the D3-D4 holding message with a
  response-time estimate); ``reminders`` pauses the patient's queued reminders when a round opens and
  reconciles them after staff release the conversation. A failing hook is logged and never undoes the
  transition (the sweeper of ``pema.care.routing`` finds a round whose routing did not start).
* ``release_to_auto`` (staff): the ONLY way back to AUTO. The release note goes to ``care_memory`` (source
  ``staff``, PII-masked); an ``override_level`` writes ``autonomy_override`` (M3 reads it) and may only LOWER
  the level of the agent, never raise it. A patient, the system or the agent calling it gets
  ``PermissionError``.
* There is no time-based way back. ``auto_release_after`` stays NULL; ``set_auto_release_after`` refuses to
  fill it unless the clinic turned ``allow_auto_release`` on, and nothing in the code reads it (a sweeper, if
  the clinic ever wants one, is a separate decision).

Every transition writes one line to ``agent.actions_log`` in the same transaction as the change, named
``control:<from>_to_<to>:<initiator>`` (``agent`` or ``staff:<user id>``; the table has no initiator column,
like it has no reason column, and its schema is final). The holding message is an automatic send and gets its
own ``auto_sent`` line.

While the state is not AUTO the loop only records history and writes suggestions for staff
(``pema.care.loop``).

Logs carry ids and codes only; never a name, a phone or any text of the patient or of the staff.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from pema.care.events import CareEvent, EventKind
from pema.care.handoff_types import (
    MAX_LEVEL,
    ControlConfigError,
    HandoffDecision,
    InvalidTransitionError,
    Urgency,
    db_urgency,
    level_number,
)
from pema.care.models import ActionDisposition, ControlState
from pema.care.ports import (
    AutonomyOverride,
    CareAgentSnapshot,
    ChannelSend,
    ControlSnapshot,
    ControlStore,
    HandoffConfigSource,
    HandoffRequestSnapshot,
    HandoffSpec,
    OpenedHandoff,
    PatientContext,
    PatientNoticeComposer,
    ReleaseSpec,
    ReminderHooks,
    RoutingAdvance,
    RoutingStart,
)
from pema.policy.pii import mask_pii
from pema_contracts.actions import ActionContext
from pema_contracts.roles import STAFF_ROLES, ActorType

logger = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 1000
NOTE_MAX_CHARS = 500
"""Length of ``care_memory.fact`` is limited to 500 by the table."""

# ``action_type`` of the audit lines
HOLDING_SENT = "control:holding_message"
HOLDING_FAILED = "control:holding_message_failed"


def transition_action(frm: ControlState, to: ControlState, initiator: str) -> str:
    return f"control:{frm.value.lower()}_to_{to.value.lower()}:{initiator}"


type Clock = Callable[[], datetime]


def staff_user_id(ctx: ActionContext) -> UUID:
    """The staff member behind ``ctx``; ``PermissionError`` for a patient, the system, an agent, a
    scheduler."""
    if (
        ctx.actor_type is not ActorType.USER
        or ctx.actor_role is None
        or ctx.actor_role not in STAFF_ROLES
        or ctx.actor_user_id is None
    ):
        raise PermissionError("only a signed-in staff member may do this")
    return ctx.actor_user_id


def build_summary(event: CareEvent, context: PatientContext, decision: HandoffDecision) -> str:
    """Summary for the staff who is asked: codes, the pseudonym patient code and scalar facts. The message
    text is NOT in it (staff opens the Inbox); the whole text still goes through the PII mask."""
    lines = [
        f"Khách: {context.patient_ref}",
        f"Sự kiện: {event.kind.value}",
        f"Độ sâu: {decision.depth.value} · mức: {decision.urgency.value} · "
        f"tin cậy: {decision.confidence:.2f}",
        f"Lý do: {', '.join(decision.signals) if decision.signals else decision.reason}",
        f"Kỹ năng cần: {decision.required_skill}",
    ]
    for key in sorted(context.facts):
        value = context.facts[key]
        if isinstance(value, bool | int | float | str):
            lines.append(f"{key}: {str(value)[:80]}")
    return mask_pii("\n".join(lines)).text[:SUMMARY_MAX_CHARS]


def _spec(event: CareEvent, context: PatientContext, decision: HandoffDecision) -> HandoffSpec:
    return HandoffSpec(
        reason=decision.reason,
        summary=build_summary(event, context, decision),
        depth=decision.depth.value,
        confidence=decision.confidence,
        required_skill=decision.required_skill,
        urgency=db_urgency(decision.urgency),
    )


def _baseline_level(agent: CareAgentSnapshot) -> int:
    """Highest level the agent has for any action type (L0 when it has none)."""
    levels = [n for n in map(level_number, agent.autonomy_levels.values()) if n is not None]
    return max(levels, default=0)


class CareControl:
    """``HandoffRequester`` plus the staff side of the state machine."""

    def __init__(
        self,
        *,
        store: ControlStore,
        config_source: HandoffConfigSource,
        channel: ChannelSend | None,
        clock: Clock,
        routing: RoutingAdvance | None = None,
        routing_start: RoutingStart | None = None,
        notices: PatientNoticeComposer | None = None,
        reminders: ReminderHooks | None = None,
    ) -> None:
        self._store = store
        self._config = config_source
        self._channel = channel
        self._clock = clock
        self._routing = routing
        self._routing_start = routing_start
        self._notices = notices
        self._reminders = reminders

    # ------------------------------------------------------------------------- the agent's side
    async def request_handoff(
        self,
        agent: CareAgentSnapshot,
        event: CareEvent,
        context: PatientContext,
        decision: HandoffDecision,
        now: datetime | None = None,
    ) -> OpenedHandoff:
        at = now if now is not None else self._clock()
        opened = await self._store.open_handoff(
            agent,
            _spec(event, context, decision),
            log_action=transition_action(ControlState.AUTO, ControlState.HANDOFF_ROUTING, "agent"),
            at=at,
        )
        logger.info(
            "handoff requested",
            extra={
                "care_agent_id": str(agent.id),
                "round_created": opened.created,
                "depth": decision.depth.value,
            },
        )
        if opened.created:
            await self._on_round_opened(agent, opened, at)
            await self._hold(agent, event, context, decision, at)
        return opened

    async def _on_round_opened(self, agent: CareAgentSnapshot, opened: OpenedHandoff, at: datetime) -> None:
        """M2c: pause the patient's reminders, then build the chain and ask the first candidate. Each hook
        is isolated: the round is already open and the patient must still get the holding message."""
        if self._reminders is not None:
            try:
                await self._reminders.pause_for(agent, at)
            except Exception as exc:
                logger.error("pausing reminders failed", extra={"error": type(exc).__name__})
        if self._routing_start is not None:
            try:
                await self._routing_start.on_opened(opened.request, at)
            except Exception as exc:
                logger.error("routing did not start", extra={"error": type(exc).__name__})

    async def _hold(
        self,
        agent: CareAgentSnapshot,
        event: CareEvent,
        context: PatientContext,
        decision: HandoffDecision,
        at: datetime,
    ) -> None:
        """The ONE holding message of this round. Only when the patient wrote and has a verified channel; a
        failed send is logged and not retried (a second message would break the "exactly one" rule)."""
        if event.kind is not EventKind.PATIENT_MESSAGE or context.channel is None or self._channel is None:
            return
        text = await self._notice_text(agent, decision, at)
        try:
            outcome = await self._channel.send(context.channel, text, proactive=False)
            sent = outcome.ok
        except Exception as exc:
            logger.error("holding message raised", extra={"error": type(exc).__name__})
            sent = False
        await self._store.record_action(
            agent.id,
            action_type=HOLDING_SENT if sent else HOLDING_FAILED,
            disposition=(ActionDisposition.AUTO_SENT if sent else ActionDisposition.PAUSED).value,
            depth=decision.depth.value,
            at=at,
        )

    async def _notice_text(self, agent: CareAgentSnapshot, decision: HandoffDecision, at: datetime) -> str:
        if self._notices is not None:
            try:
                composed = await self._notices.compose(agent, decision, at)
            except Exception as exc:
                logger.error("patient notice failed", extra={"error": type(exc).__name__})
                composed = None
            if composed:
                return composed
        settings = await self._config.get(agent.clinic_id)
        return (
            settings.config.holding_message
            if decision.urgency is Urgency.NORMAL
            else settings.config.holding_message_urgent
        )

    # -------------------------------------------------------------------------- the staff's side
    async def accept(self, ctx: ActionContext, patient_id: UUID) -> HandoffRequestSnapshot:
        staff_id = staff_user_id(ctx)
        request = await self._store.accept(
            patient_id,
            staff_id,
            log_action=transition_action(
                ControlState.HANDOFF_ROUTING, ControlState.STAFF, f"staff:{staff_id}"
            ),
            at=self._clock(),
        )
        logger.info("handoff accepted", extra={"care_agent_id": str(request.care_agent_id)})
        return request

    async def decline(
        self,
        ctx: ActionContext,
        patient_id: UUID,
        reason: str,
        suggest_user_id: UUID | None = None,
    ) -> HandoffRequestSnapshot:
        """The free-text ``reason`` is passed to M2c's ``RoutingAdvance`` and is not kept here."""
        staff_id = staff_user_id(ctx)
        request = await self._store.record_decline(
            patient_id,
            staff_id,
            log_action=f"control:handoff_routing_declined:staff:{staff_id}",
            at=self._clock(),
        )
        if self._routing is not None:
            await self._routing.on_declined(request, staff_id, reason, suggest_user_id)
        return request

    async def release_to_auto(
        self,
        ctx: ActionContext,
        patient_id: UUID,
        note: str,
        override_level: int | None = None,
        until: datetime | None = None,
    ) -> ControlSnapshot:
        """``STAFF -> AUTO``. Staff only (``PermissionError`` otherwise); ``InvalidTransitionError``
        unless the
        conversation is in ``STAFF``; ``ValueError`` for a level outside L0..L2, one above the agent's own,
        or an ``until`` in the past."""
        staff_id = staff_user_id(ctx)
        now = self._clock()
        override = await self._override(patient_id, override_level, until, now)
        masked = mask_pii(note.strip()).text.strip()
        snapshot = await self._store.release(
            patient_id,
            staff_id,
            ReleaseSpec(
                memory_fact=masked[:NOTE_MAX_CHARS] if masked else None,
                release_note=masked or None,
                override=override,
            ),
            log_action=transition_action(ControlState.STAFF, ControlState.AUTO, f"staff:{staff_id}"),
            at=now,
        )
        logger.info("conversation released to the agent", extra={"override": override is not None})
        await self._reconcile(patient_id, now)
        return snapshot

    async def _reconcile(self, patient_id: UUID, now: datetime) -> None:
        """M2c: judge the reminders that were paused while a person had the conversation."""
        if self._reminders is None:
            return
        try:
            agent = await self._store.agent_for_patient(patient_id)
            if agent is not None:
                await self._reminders.reconcile_on_release(agent, now)
        except Exception as exc:
            logger.error("reconciling reminders failed", extra={"error": type(exc).__name__})

    async def _override(
        self, patient_id: UUID, level: int | None, until: datetime | None, now: datetime
    ) -> AutonomyOverride | None:
        if level is None:
            if until is not None:
                raise ValueError("`until` needs an override level")
            return None
        if not 0 <= level <= MAX_LEVEL:
            raise ValueError("override level must be between 0 and 2")
        if until is not None and until <= now:
            raise ValueError("override must end in the future")
        agent = await self._store.agent_for_patient(patient_id)
        if agent is None:
            raise InvalidTransitionError("no care agent for this patient")
        if level > _baseline_level(agent):
            raise ValueError("a release may only lower the autonomy level")
        return AutonomyOverride(level=level, until=until)

    async def set_auto_release_after(
        self, ctx: ActionContext, patient_id: UUID, after: timedelta | None
    ) -> None:
        """Turn the OPTIONAL "back to AUTO after N hours of silence" on or off for one conversation. Refused
        (``ControlConfigError``) unless the clinic set ``allow_auto_release``; ``None`` always clears it."""
        staff_id = staff_user_id(ctx)
        if after is not None:
            agent = await self._store.agent_for_patient(patient_id)
            if agent is None:
                raise InvalidTransitionError("no care agent for this patient")
            settings = await self._config.get(agent.clinic_id)
            if not settings.config.allow_auto_release:
                raise ControlConfigError("auto release is off for this clinic")
            if after <= timedelta(0):
                raise ValueError("auto release needs a positive duration")
        await self._store.set_auto_release_after(
            patient_id,
            after,
            log_action=f"control:auto_release_after_set:staff:{staff_id}",
            at=self._clock(),
        )
