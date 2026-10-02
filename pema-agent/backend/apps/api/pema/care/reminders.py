"""Scheduled reminders while a person handles the patient (PLAN-AI01-M section 8, decision 2 of section 15).
New module (not a port).

Rule: while the conversation is in ``HANDOFF_ROUTING`` or ``STAFF`` the agent sends NO reminder of any kind
to this patient.

* ``pause_event`` (the turn loop calls it when the state is not AUTO): a reminder event (milestone due,
  visit overdue, no-show, dormant, birthday, session completed) is recorded in ``agent.paused_reminders``
  with the doctor-approved prepared text, shown to the OWNING staff member (the person who has the
  conversation, else the CS owner) who may send it by hand (``mark_sent_by_staff``). It is never turned into
  a staff task and nothing reaches the patient. A repeat of the same event (same ``dedupe_key``) changes
  nothing.
* ``pause_for`` (``CareControl`` calls it when a round opens): reminders that are already queued for the
  patient in S or B2 (``DueReminderSource``) are recorded as paused the same way and S/B2 is told not to fire
  them again (``hold``).
* ``reconcile_on_release`` (``CareControl`` calls it after staff hand the conversation back to AUTO): every
  still-paused reminder is judged by ``ReminderRules``:
    - past its meaning (later than ``max_late_hours`` of its type, e.g. D+3 ten days late) -> dropped and
      logged (``reminder:dropped:past_meaning:<type>``);
    - superseded (a later reminder of the same series and anchor is already due: D+1 when D+3 has passed) ->
      dropped and logged (``reminder:dropped:superseded:<type>``);
    - otherwise it goes back into the normal turn pipeline as a ``CareEvent`` carrying
      ``late_original_at``; the loop then prefixes the text with S's label "(nhắc trễ, lịch gốc HH:MM)" and
      the usual send window, daily cap and autonomy level decide when and whether it leaves
      (``reminder:resumed:<type>``).
  A patient's reply during STAFF goes to the staff member; the agent does not act on it (M2b suggestions).

The "past its meaning" windows are TEMPORARY defaults (``pending_doctor_approval``); the doctor decides.
Logs and audit lines carry the reminder type and ids only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from pema.care.control import staff_user_id
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.models import ActionDisposition
from pema.care.oncall import ActionRecorder
from pema.care.ports import (
    CareAgentSnapshot,
    ControlStore,
    DueReminderSource,
    EventPublisher,
    ReminderStore,
    RoutingConfigSource,
    RoutingDirectory,
)
from pema.care.routing_types import (
    NewPausedReminder,
    PausedReminder,
    ReminderRules,
    ReminderStatus,
)
from pema_contracts.actions import ActionContext
from pema_contracts.common import JsonObject

logger = logging.getLogger(__name__)

LATE_ORIGINAL_AT = "late_original_at"
"""Payload key of a reconciled reminder: ISO time of the original schedule (the loop adds the late label)."""
RECONCILED = "reconciled"

REMINDER_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.MILESTONE_DUE,
        EventKind.VISIT_OVERDUE,
        EventKind.NO_SHOW,
        EventKind.DORMANT,
        EventKind.BIRTHDAY,
        EventKind.SESSION_COMPLETED,
    }
)
"""What counts as a "reminder" while a person has the conversation. The daily tick (its drafts are computed
again at the next 06:00), patient messages, staff commands and doctor edits are not."""

PAUSED = "reminder:paused"
DROPPED = "reminder:dropped"
RESUMED = "reminder:resumed"
RESUME_FAILED = "reminder:resume_failed"

type Clock = Callable[[], datetime]


def meaning_key_of(kind: EventKind, rule: str | None) -> str:
    return rule if rule is not None else kind.value


def _rank(rules: ReminderRules, key: str) -> int:
    return rules.series_order.index(key) if key in rules.series_order else -1


def drop_reason(
    reminder: PausedReminder, paused: list[PausedReminder], now: datetime, rules: ReminderRules
) -> str | None:
    """``past_meaning``, ``superseded`` or ``None`` (still useful)."""
    key = reminder.meaning_key
    if now - reminder.due_at > rules.max_late(key):
        return "past_meaning"
    rank = _rank(rules, key)
    if rank < 0:
        return None
    for other in paused:
        if (
            other.id != reminder.id
            and other.kind is reminder.kind
            and other.anchor == reminder.anchor
            and _rank(rules, other.meaning_key) > rank
            and other.due_at <= now
        ):
            return "superseded"
    return None


class ReminderService:
    """``ReminderPauser`` (the loop) and ``ReminderHooks`` (``CareControl``)."""

    def __init__(
        self,
        *,
        store: ReminderStore,
        config_source: RoutingConfigSource,
        directory: RoutingDirectory,
        controls: ControlStore,
        recorder: ActionRecorder,
        publisher: EventPublisher,
        clock: Clock,
        due_source: DueReminderSource | None = None,
    ) -> None:
        self._store = store
        self._config = config_source
        self._directory = directory
        self._controls = controls
        self._recorder = recorder
        self._publisher = publisher
        self._clock = clock
        self._due = due_source

    async def _log(self, agent: CareAgentSnapshot, action: str, now: datetime) -> None:
        await self._recorder.record_action(
            agent.id,
            action_type=action,
            disposition=ActionDisposition.PAUSED.value,
            depth=None,
            at=now,
        )

    async def _owner(self, agent: CareAgentSnapshot) -> UUID | None:
        control = await self._controls.get_control(agent.patient_id)
        if control.staff_owner is not None:
            return control.staff_owner
        return (await self._directory.ownership(agent.patient_id)).cs_owner

    # -------------------------------------------------------------------------------- pausing
    async def pause_event(self, agent: CareAgentSnapshot, event: CareEvent, now: datetime) -> bool:
        if event.kind not in REMINDER_KINDS:
            return False
        raw_rule = event.payload.get("rule")
        rule = raw_rule if isinstance(raw_rule, str) else None
        anchor = event.payload.get("anchor")
        key = f"{event.kind.value}:{rule}:{anchor}:{event.occurred_at.isoformat()}"
        added = await self._record(
            agent,
            kind=event.kind,
            rule=rule,
            due_at=event.occurred_at,
            dedupe_key=key,
            payload=dict(event.payload),
            patient_ref=event.patient_ref,
            now=now,
        )
        if added:
            await self._log(agent, f"{PAUSED}:{meaning_key_of(event.kind, rule)}", now)
        return True

    async def pause_for(self, agent: CareAgentSnapshot, now: datetime) -> int:
        """Pause what is already queued for this patient. Returns how many were newly paused."""
        if self._due is None:
            return 0
        due = await self._due.due_for(agent.patient_id, now)
        count = 0
        for item in due:
            added = await self._record(
                agent,
                kind=item.kind,
                rule=item.rule,
                due_at=item.due_at,
                dedupe_key=item.dedupe_key,
                payload=dict(item.payload),
                patient_ref=item.patient_ref,
                now=now,
            )
            if added:
                count += 1
                await self._log(agent, f"{PAUSED}:{meaning_key_of(item.kind, item.rule)}", now)
        if due:
            await self._due.hold(agent.patient_id, [item.dedupe_key for item in due])
        return count

    async def _record(
        self,
        agent: CareAgentSnapshot,
        *,
        kind: EventKind,
        rule: str | None,
        due_at: datetime,
        dedupe_key: str,
        payload: JsonObject,
        patient_ref: str,
        now: datetime,
    ) -> bool:
        config = await self._config.get(agent.clinic_id)
        key = meaning_key_of(kind, rule)
        added = await self._store.add(
            NewPausedReminder(
                clinic_id=agent.clinic_id,
                care_agent_id=agent.id,
                patient_id=agent.patient_id,
                patient_ref=patient_ref,
                kind=kind,
                rule=rule,
                due_at=due_at,
                dedupe_key=dedupe_key,
                prepared_text=config.reminders.prepared_texts.get(key),
                owner_user_id=await self._owner(agent),
                payload=payload,
                paused_at=now,
            )
        )
        logger.info("reminder paused", extra={"care_agent_id": str(agent.id), "type": key, "new": added})
        return added

    # ----------------------------------------------------------------------------- reconciling
    async def reconcile_on_release(self, agent: CareAgentSnapshot, now: datetime) -> None:
        paused = list(await self._store.list_paused(agent.id))
        if not paused:
            return
        rules = (await self._config.get(agent.clinic_id)).reminders
        for reminder in sorted(paused, key=lambda r: r.due_at):
            reason = drop_reason(reminder, paused, now, rules)
            key = reminder.meaning_key
            if reason is not None:
                if await self._store.resolve(reminder.id, ReminderStatus.DROPPED, reason, now):
                    await self._log(agent, f"{DROPPED}:{reason}:{key}", now)
                continue
            if not await self._store.resolve(reminder.id, ReminderStatus.RESUMED, "resumed", now):
                continue
            event = CareEvent(
                kind=reminder.kind,
                initiator=Initiator.SYSTEM,
                patient_ref=reminder.patient_ref,
                payload={
                    **reminder.payload,
                    **({"rule": reminder.rule} if reminder.rule is not None else {}),
                    LATE_ORIGINAL_AT: reminder.due_at.isoformat(),
                    RECONCILED: True,
                },
                occurred_at=now,
            )
            if await self._publisher.publish(event):
                await self._log(agent, f"{RESUMED}:{key}", now)
            else:
                logger.error("a reconciled reminder could not be queued", extra={"type": key})
                await self._log(agent, f"{RESUME_FAILED}:{key}", now)

    # ------------------------------------------------------------------------------ staff side
    async def mark_sent_by_staff(self, ctx: ActionContext, reminder_id: UUID) -> bool:
        """The staff member sent this paused reminder by hand: it is not resumed on release.
        ``PermissionError`` unless ``ctx`` is a signed-in staff member."""
        staff_id = staff_user_id(ctx)
        done = await self._store.resolve(
            reminder_id, ReminderStatus.SENT_BY_STAFF, f"staff:{staff_id}", self._clock()
        )
        logger.info("paused reminder sent by staff", extra={"done": done})
        return done
