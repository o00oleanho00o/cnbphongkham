# ported from: prototype/shared/crm-automation.js (run)
"""The ten CRM rules as one pure function: patients + rules + existing tasks + ``now`` -> tasks.

``run()`` of the JavaScript, minus its side effects. What it did, in order, and where it is here:

1. ``refresh()``: D+30 recommendation after a Laser CO2 session -> ``profile.refresh_patient``.
2. For every patient and every rule, a ``candidate`` task when the rule's condition holds ->
``build_candidates``.
   Rule inactive, or a marketing rule for a patient with ``marketing_opt_out``, produces no candidate.
   Opt-out never removes a clinical follow-up (d1/d3/d7, due, overdue, no_show, abandoned).
3. Idempotency: the key is ``CRM:<rule>:<patient code>:<source event>`` (rule + patient + source). A key that
   already exists, whatever its status, is never created again: a resolved or superseded task stays closed,
   so a rerun cannot reopen what staff finished -> ``reconcile``.
4. An open or rescheduled task that is no longer a candidate (new booking, new milestone, opt-out, rule off)
   becomes ``superseded``; ``manual`` tasks are never touched -> ``reconcile``.

Deliberate differences from the JavaScript (all invisible at the test clock 2026-09-20T09:00+07:00):

* The clock is ``now`` (aware), not the constant 2026-09-20. The demo's fixed "09:00" of the 24 hour rule for
  cancellations is the real ``now`` here; at 09:00 they are identical.
* ``created_at`` is ``now`` (the JavaScript wrote the constant 08:00); ``due_at`` is still 09:00 +07:00 of the
  due day.
* A task has no synthetic plan id: the original wrote ``'LP-' + patient id`` when a patient had no service
plan;
  ``related_plan_id`` is None in that case (the column is a foreign key to ``clinic.treatment_plan``).
* ``d1/d3/d7`` read the protocol from the rule (``conditions.protocol``), defaulting to Laser CO2.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta

from pema.clinic.crm_rules.dates import add_days, days_between, next_birthday
from pema.clinic.crm_rules.profile import (
    DORMANT_AFTER_DAYS,
    compute_profile,
    latest_session,
    refresh_patient,
    upcoming,
)
from pema.clinic.crm_rules.records import (
    OPEN_STATUSES,
    AppointmentSnapshot,
    AppointmentStatus,
    ExistingTask,
    PatientCrmUpdate,
    PatientSnapshot,
    ProfileView,
    Reconciliation,
    RulesOutcome,
    TaskCandidate,
)
from pema.clinic.crm_rules.rules import LASER_PROTOCOL_ID, RuleConfig
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey

DUE_HOUR = 9
"""Every task is due at 09:00 +07:00 of its due day."""
PROTOCOL_WINDOW_DAYS = 45
"""d1/d3/d7 only look at a Laser CO2 session that is 0 to 45 days old."""
NO_SHOW_MIN_AGE = timedelta(hours=24)
"""A cancellation or no-show becomes a recall only when it is at least 24 hours old (real hours, not days)."""
LONG_DORMANT_AFTER_DAYS = 180
"""A patient of 180+ days leaves the 90-day group (dormant90 and dormant180 are exclusive)."""
SUPERSEDED_RESOLUTION = "Nguồn đã đổi: có lịch mới, mốc mới hoặc opt-out"


def clinic_today(now: datetime) -> date:
    """The clinic-local day of ``now`` (+07:00)."""
    return now.astimezone(VN_TZ).date()


def _due_at(day: date) -> datetime:
    return datetime.combine(day, time(DUE_HOUR, 0), tzinfo=VN_TZ)


def task_key(rule: RuleKey, patient_code: str, source: str) -> str:
    """The idempotency key: rule + patient + source event (``CRM:${rule.id}:${p.id}:${source}``)."""
    return f"CRM:{rule.value}:{patient_code}:{source}"


def _recall_reference(appointment: AppointmentSnapshot) -> datetime:
    """``a.cancelledAt || a.missedAt || a.date + 'T' + a.time``."""
    return appointment.cancelled_at or appointment.missed_at or appointment.starts_at


def _recall_due_day(appointment: AppointmentSnapshot) -> date:
    """``addDays((a.cancelledAt || a.date).slice(0, 10), 1)`` is built from this day."""
    moment = appointment.cancelled_at or appointment.starts_at
    return moment.astimezone(VN_TZ).date()


def _recall_appointment(patient: PatientSnapshot, now: datetime) -> AppointmentSnapshot | None:
    """Latest cancelled/missed appointment that is at least 24 h old (ties: the first listed)."""
    old_enough = [
        a
        for a in patient.appointments
        if a.status in (AppointmentStatus.MISSED, AppointmentStatus.CANCELLED)
        and now - _recall_reference(a) >= NO_SHOW_MIN_AGE
    ]
    if not old_enough:
        return None
    return sorted(old_enough, key=lambda a: a.day, reverse=True)[0]


def _candidate(
    rule: RuleConfig,
    patient: PatientSnapshot,
    source: str,
    due: date,
    now: datetime,
    *,
    related_appointment_id: str | None = None,
    related_plan_id: str | None = None,
) -> TaskCandidate | None:
    """``task(rule, p, source, due, related)``."""
    if not rule.active:
        return None
    if rule.marketing and patient.marketing_opt_out:
        return None
    return TaskCandidate(
        task_key=task_key(rule.key, patient.code, source),
        patient_id=patient.id,
        patient_code=patient.code,
        rule_key=rule.key,
        reason=rule.name,
        priority=rule.priority,
        created_at=now,
        due_at=_due_at(due),
        owner_user_id=patient.doctor_id if rule.key is RuleKey.D7 else patient.cs_owner_id,
        suggested_action=rule.suggested_action,
        source_event_id=source,
        related_appointment_id=related_appointment_id,
        related_plan_id=related_plan_id,
    )


def _candidates_for(
    patient: PatientSnapshot,
    rules: Sequence[RuleConfig],
    today: date,
    now: datetime,
    view: ProfileView,
) -> Iterable[TaskCandidate | None]:
    future = upcoming(patient, today)
    latest = latest_session(patient)
    for rule in rules:
        key = rule.key
        if key in (RuleKey.D1, RuleKey.D3, RuleKey.D7):
            protocol = rule.protocol or LASER_PROTOCOL_ID
            if (
                latest is not None
                and latest.protocol_id == protocol
                and 0 <= days_between(latest.day, today) <= PROTOCOL_WINDOW_DAYS
            ):
                yield _candidate(rule, patient, latest.id, add_days(latest.day, rule.delay_days), now)
        elif key is RuleKey.DUE:
            arrived_today = any(
                a.day == today and a.status in (AppointmentStatus.ARRIVED, AppointmentStatus.IN_PROGRESS)
                for a in future
            )
            if view.expected_next_visit_at == today and not arrived_today:
                yield _candidate(rule, patient, today.isoformat(), today, now)
        elif key is RuleKey.OVERDUE:
            expected = view.expected_next_visit_at
            if view.overdue_days > 0 and expected is not None:
                yield _candidate(rule, patient, expected.isoformat(), expected, now)
        elif key is RuleKey.NO_SHOW:
            if not future:
                appointment = _recall_appointment(patient, now)
                if appointment is not None:
                    yield _candidate(
                        rule,
                        patient,
                        appointment.id,
                        add_days(_recall_due_day(appointment), 1),
                        now,
                        related_appointment_id=appointment.id,
                    )
        elif key is RuleKey.ABANDONED:
            if (
                view.remaining > 0
                and view.age > rule.delay_days
                and not future
                and patient.last_visit is not None
            ):
                source = latest.id if latest is not None else patient.last_visit.isoformat()
                yield _candidate(
                    rule,
                    patient,
                    source,
                    add_days(patient.last_visit, rule.delay_days),
                    now,
                    related_plan_id=patient.first_plan_id,
                )
        elif key is RuleKey.DORMANT90:
            if (
                DORMANT_AFTER_DAYS <= view.age < LONG_DORMANT_AFTER_DAYS
                and not future
                and patient.last_visit is not None
            ):
                yield _candidate(
                    rule,
                    patient,
                    patient.last_visit.isoformat(),
                    add_days(patient.last_visit, rule.delay_days),
                    now,
                )
        elif key is RuleKey.DORMANT180:
            if view.age >= LONG_DORMANT_AFTER_DAYS and not future and patient.last_visit is not None:
                yield _candidate(
                    rule,
                    patient,
                    patient.last_visit.isoformat(),
                    add_days(patient.last_visit, rule.delay_days),
                    now,
                )
        elif key is RuleKey.BIRTHDAY and patient.birth_date is not None:
            birthday = next_birthday(patient.birth_date, today)
            if days_between(today, birthday) <= rule.delay_days:
                yield _candidate(rule, patient, birthday.isoformat(), birthday, now)


def build_candidates(
    patients: Sequence[PatientSnapshot], rules: Sequence[RuleConfig], now: datetime
) -> list[TaskCandidate]:
    """The ``candidates`` of ``run()``. ``patients`` must already be refreshed (see ``run_rules``)."""
    today = clinic_today(now)
    found: list[TaskCandidate] = []
    for patient in patients:
        view = compute_profile(patient, today)
        for candidate in _candidates_for(patient, rules, today, now, view):
            if candidate is not None:
                found.append(candidate)
    return found


def reconcile(candidates: Sequence[TaskCandidate], existing: Sequence[ExistingTask]) -> Reconciliation:
    """Idempotent merge of this run's candidates with the stored tasks (steps 3 and 4 above)."""
    known = {t.task_key for t in existing}
    eligible = {c.task_key for c in candidates}
    new_tasks: list[TaskCandidate] = []
    for candidate in candidates:
        if candidate.task_key not in known:
            new_tasks.append(candidate)
            known.add(candidate.task_key)
    superseded = [
        t.task_key
        for t in existing
        if t.status in OPEN_STATUSES and t.rule_key is not RuleKey.MANUAL and t.task_key not in eligible
    ]
    return Reconciliation(new_tasks=tuple(new_tasks), superseded_keys=tuple(superseded))


def run_rules(
    patients: Sequence[PatientSnapshot],
    rules: Sequence[RuleConfig],
    existing: Sequence[ExistingTask],
    now: datetime,
) -> RulesOutcome:
    """``run()`` as a pure function. Persisting the outcome is the caller's job (``runner``)."""
    today = clinic_today(now)
    refreshed: list[PatientSnapshot] = []
    updates: list[PatientCrmUpdate] = []
    for patient in patients:
        fresh, update = refresh_patient(patient)
        refreshed.append(fresh)
        if update is not None:
            updates.append(update)
    candidates = build_candidates(refreshed, rules, now)
    merged = reconcile(candidates, existing)
    return RulesOutcome(
        today=today,
        candidates=tuple(candidates),
        new_tasks=merged.new_tasks,
        superseded_keys=merged.superseded_keys,
        patient_updates=tuple(updates),
        refreshed=tuple(refreshed),
        profiles={p.id: compute_profile(p, today) for p in refreshed},
    )


__all__ = [
    "DUE_HOUR",
    "LONG_DORMANT_AFTER_DAYS",
    "NO_SHOW_MIN_AGE",
    "PROTOCOL_WINDOW_DAYS",
    "SUPERSEDED_RESOLUTION",
    "build_candidates",
    "clinic_today",
    "reconcile",
    "run_rules",
    "task_key",
]
