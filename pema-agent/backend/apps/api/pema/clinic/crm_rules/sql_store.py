# new module (not a port): crm-automation.js read and wrote ``window.Pema.state`` in the browser
"""``CrmRuleStore`` over Postgres (schemas ``clinic`` and ``agent``) as role ``be_app``.

Forced deviation: localStorage state becomes SQL. Every read is one bulk query per table (no query inside a
loop), every write is one ``executemany``. ``async with db.session()`` opens the unit of work; each
statement filters ``clinic_id`` (the installation id).

What the snapshots are built from:

* sessions: ``clinic.treatment_session`` with ``status = 'completed'``; ``last_visit`` is the latest day;
* plans: ``clinic.treatment_plan`` in ``planned``/``active`` summed into ``total_sessions`` /
  ``completed_sessions`` (JavaScript ``p.total`` / ``p.completed``); ``first_plan_id`` is the earliest one;
* appointments: cancelled and missed ones of any age (recall) and every appointment from today on;
* channel target: a VERIFIED ``clinic.channel_identity`` of a ``zalo_bot`` / ``zalo_personal`` channel
joined to
  an enabled ``agent.accounts`` row of that channel (the most recently active identity wins; when a clinic has
  several enabled accounts of one channel the first by id is used: open item for package G). The profile is
  ``effective_profile_key(account, agent)``, the restrictive one;
* consent: the newest ``messaging`` row of ``clinic.consent`` is granted and not revoked;
* templates: ``clinic.message_template`` that is active AND approved.

Scale note: ``existing_tasks`` loads every task key of the clinic (three short text columns) because a closed
task must keep blocking its key forever; a clinic with 100 000 tasks is still one small read.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic.crm_rules.engine import SUPERSEDED_RESOLUTION, clinic_today
from pema.clinic.crm_rules.protocols import ProtocolConfig
from pema.clinic.crm_rules.records import (
    AppointmentSnapshot,
    AppointmentStatus,
    ChannelTarget,
    ClinicCrmData,
    ExistingTask,
    PatientSnapshot,
    SessionSnapshot,
    TemplateRef,
)
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig, conditions_of, json_object, rule_from_row
from pema.clinic.crm_rules.store import StoreChanges
from pema.core.db import ClinicDatabase
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey, RuleSendMode, TaskPriority, TaskStatus
from pema_contracts.policy import PolicyProfileKey, effective_profile_key

_Row = Mapping[str, Any]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=VN_TZ)


async def _rows(session: AsyncSession, sql: str, **params: object) -> list[_Row]:
    result = await session.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


async def seed_default_rules(session: AsyncSession, clinic_id: UUID) -> None:
    """Insert the ten rules of crm-data.js a clinic lacks (idempotent, never overwrites a tune)."""
    await session.execute(
        text(
            "INSERT INTO clinic.crm_rule (clinic_id, rule_key, name, trigger, delay_days, suggested_action, "
            "priority, active, send_mode, conditions) "
            "VALUES (:c, :key, :name, :trigger, :delay, :action, :priority, :active, :mode, "
            "CAST(:conditions AS jsonb)) ON CONFLICT (clinic_id, rule_key) DO NOTHING"
        ),
        [
            {
                "c": clinic_id,
                "key": r.key.value,
                "name": r.name,
                "trigger": r.trigger,
                "delay": r.delay_days,
                "action": r.suggested_action,
                "priority": r.priority.value,
                "active": r.active,
                "mode": r.send_mode.value,
                "conditions": json.dumps(conditions_of(r)),
            }
            for r in DEFAULT_RULES
        ],
    )


def _protocol_config(row: _Row) -> ProtocolConfig:
    milestones: dict[RuleKey, int] = {}
    raw = row["milestones"]
    for item in cast(list[Any], raw) if isinstance(raw, list) else []:
        entry = json_object(item)
        key = RuleKey(str(entry["rule_key"]))
        milestones[key] = int(entry["day"])
    followup = row["followup_days"]
    return ProtocolConfig(
        code=str(row["code"]),
        name=str(row["name"]),
        milestones=milestones,
        followup_days=int(followup) if followup is not None else None,
        window_days=int(row["window_days"]),
        active=bool(row["active"]),
    )


class SqlCrmRuleStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------ rules
    async def ensure_rules(self, clinic_id: UUID) -> None:
        async with self._db.session() as session:
            await seed_default_rules(session, clinic_id)

    # ------------------------------------------------------------------- load
    async def load(self, clinic_id: UUID, now: datetime) -> ClinicCrmData:
        today = clinic_today(now)
        day_start = datetime.combine(today, time.min, tzinfo=VN_TZ)
        async with self._db.session() as session:
            rules = await self._rules(session, clinic_id)
            patients = await self._patients(session, clinic_id, day_start)
            tasks = await _rows(
                session,
                "SELECT task_key, rule_key, status FROM clinic.crm_task WHERE clinic_id = :c",
                c=clinic_id,
            )
            templates = await _rows(
                session,
                "SELECT template_key, marketing FROM clinic.message_template "
                "WHERE clinic_id = :c AND active AND approved_at IS NOT NULL",
                c=clinic_id,
            )
            protocols = await self._protocols(session, clinic_id)
        return ClinicCrmData(
            rules=tuple(rules),
            patients=tuple(patients),
            existing_tasks=tuple(
                ExistingTask(str(t["task_key"]), RuleKey(str(t["rule_key"])), TaskStatus(str(t["status"])))
                for t in tasks
            ),
            templates={
                str(t["template_key"]): TemplateRef(str(t["template_key"]), bool(t["marketing"]))
                for t in templates
            },
            protocols=protocols,
        )

    async def _protocols(self, session: AsyncSession, clinic_id: UUID) -> dict[str, ProtocolConfig]:
        rows = await _rows(
            session,
            "SELECT code, name, milestones, followup_days, window_days, active "
            "FROM clinic.protocol WHERE clinic_id = :c",
            c=clinic_id,
        )
        return {str(r["code"]): _protocol_config(r) for r in rows}

    async def _rules(self, session: AsyncSession, clinic_id: UUID) -> list[RuleConfig]:
        rows = await _rows(
            session,
            "SELECT rule_key, name, trigger, delay_days, suggested_action, priority, active, send_mode, "
            "conditions FROM clinic.crm_rule WHERE clinic_id = :c",
            c=clinic_id,
        )
        by_key = {
            RuleKey(str(r["rule_key"])): rule_from_row(
                key=RuleKey(str(r["rule_key"])),
                name=str(r["name"]),
                trigger=str(r["trigger"]),
                delay_days=int(r["delay_days"]),
                suggested_action=str(r["suggested_action"]),
                priority=TaskPriority(str(r["priority"])),
                active=bool(r["active"]),
                send_mode=RuleSendMode(str(r["send_mode"])),
                conditions=json_object(r["conditions"]),
            )
            for r in rows
        }
        return [by_key[d.key] for d in DEFAULT_RULES if d.key in by_key]

    async def _patients(
        self, session: AsyncSession, clinic_id: UUID, day_start: datetime
    ) -> list[PatientSnapshot]:
        patient_rows = await _rows(
            session,
            "SELECT id, code, doctor_id, cs_owner_id, birth_date, marketing_opt_out, recommendation_at, "
            "expected_visit_source, expected_visit_reason, last_protocol_session_id, reactivated_at "
            "FROM clinic.patient WHERE clinic_id = :c ORDER BY code",
            c=clinic_id,
        )
        session_rows = await _rows(
            session,
            "SELECT id::text AS id, patient_id, (performed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS day, "
            "protocol_id FROM clinic.treatment_session WHERE clinic_id = :c AND status = 'completed'",
            c=clinic_id,
        )
        appointment_rows = await _rows(
            session,
            "SELECT id::text AS id, patient_id, starts_at, status, cancelled_at, missed_at "
            "FROM clinic.appointment WHERE clinic_id = :c "
            "AND (status IN ('cancelled', 'missed') OR starts_at >= :d)",
            c=clinic_id,
            d=day_start,
        )
        plan_rows = await _rows(
            session,
            "SELECT patient_id, sum(total_sessions)::int AS total, "
            "sum(completed_sessions)::int AS completed, "
            "(array_agg(id::text ORDER BY created_at, id))[1] AS first_plan_id "
            "FROM clinic.treatment_plan WHERE clinic_id = :c AND status IN ('planned', 'active') "
            "GROUP BY patient_id",
            c=clinic_id,
        )
        target_rows = await _rows(
            session,
            "SELECT DISTINCT ON (ci.patient_id) ci.patient_id, a.id AS account_id, ci.external_user_id, "
            "a.policy_profile AS account_profile, g.policy_profile AS agent_profile "
            "FROM clinic.channel_identity ci "
            "JOIN agent.accounts a ON a.clinic_id = ci.clinic_id AND a.channel = ci.channel AND a.enabled "
            "JOIN agent.agents g ON g.clinic_id = a.clinic_id AND g.id = a.agent_id "
            "WHERE ci.clinic_id = :c AND ci.verification_status = 'verified' AND ci.patient_id IS NOT NULL "
            "AND ci.channel IN ('zalo_bot', 'zalo_personal') "
            "ORDER BY ci.patient_id, ci.last_inbound_at DESC NULLS LAST, a.id",
            c=clinic_id,
        )
        consent_rows = await _rows(
            session,
            "SELECT DISTINCT ON (patient_id) patient_id, granted, revoked_at FROM clinic.consent "
            "WHERE clinic_id = :c AND kind = 'messaging' ORDER BY patient_id, created_at DESC",
            c=clinic_id,
        )

        sessions: dict[UUID, list[SessionSnapshot]] = defaultdict(list)
        for r in session_rows:
            protocol = r["protocol_id"]
            sessions[r["patient_id"]].append(
                SessionSnapshot(str(r["id"]), r["day"], str(protocol) if protocol is not None else None)
            )
        appointments: dict[UUID, list[AppointmentSnapshot]] = defaultdict(list)
        for r in appointment_rows:
            appointments[r["patient_id"]].append(
                AppointmentSnapshot(
                    id=str(r["id"]),
                    starts_at=_aware(r["starts_at"]),
                    status=AppointmentStatus(str(r["status"])),
                    cancelled_at=_aware(r["cancelled_at"]) if r["cancelled_at"] is not None else None,
                    missed_at=_aware(r["missed_at"]) if r["missed_at"] is not None else None,
                )
            )
        plans = {r["patient_id"]: r for r in plan_rows}
        targets = {
            r["patient_id"]: ChannelTarget(
                account_id=str(r["account_id"]),
                thread_id=str(r["external_user_id"]),
                thread_type=0,
                policy_profile=effective_profile_key(
                    PolicyProfileKey(str(r["account_profile"])), PolicyProfileKey(str(r["agent_profile"]))
                ),
            )
            for r in target_rows
        }
        consents = {r["patient_id"]: bool(r["granted"]) and r["revoked_at"] is None for r in consent_rows}

        snapshots: list[PatientSnapshot] = []
        for r in patient_rows:
            pid: UUID = r["id"]
            own_sessions = tuple(sorted(sessions.get(pid, []), key=lambda s: s.day))
            plan = plans.get(pid)
            birth: date | None = r["birth_date"]
            source = r["expected_visit_source"]
            reason = r["expected_visit_reason"]
            marker = r["last_protocol_session_id"]
            snapshots.append(
                PatientSnapshot(
                    id=pid,
                    code=str(r["code"]),
                    doctor_id=r["doctor_id"],
                    cs_owner_id=r["cs_owner_id"],
                    last_visit=own_sessions[-1].day if own_sessions else None,
                    total_sessions=int(plan["total"]) if plan is not None else 0,
                    completed_sessions=int(plan["completed"]) if plan is not None else 0,
                    sessions=own_sessions,
                    appointments=tuple(appointments.get(pid, [])),
                    birth_date=birth,
                    marketing_opt_out=bool(r["marketing_opt_out"]),
                    recommendation_at=r["recommendation_at"],
                    expected_visit_source=str(source) if source is not None else None,
                    expected_visit_reason=str(reason) if reason is not None else None,
                    last_protocol_session_id=str(marker) if marker is not None else None,
                    reactivated_at=_aware(r["reactivated_at"]) if r["reactivated_at"] is not None else None,
                    first_plan_id=str(plan["first_plan_id"]) if plan is not None else None,
                    channel_target=targets.get(pid),
                    messaging_consent=consents.get(pid, False),
                )
            )
        return snapshots

    # ------------------------------------------------------------------ apply
    async def apply(self, clinic_id: UUID, changes: StoreChanges) -> int:
        inserted = 0
        async with self._db.session() as session:
            if changes.new_tasks:
                inserted = await self._insert_tasks(session, clinic_id, changes)
            superseded = 0
            if changes.superseded_keys:
                result = await session.execute(
                    text(
                        "UPDATE clinic.crm_task SET status = 'superseded', resolution = :res, "
                        "resolved_at = :now, "
                        "version = version + 1 WHERE clinic_id = :c "
                        "AND task_key = ANY(CAST(:keys AS text[])) "
                        "AND status IN ('open', 'rescheduled') AND rule_key <> 'manual'"
                    ),
                    {
                        "c": clinic_id,
                        "keys": list(changes.superseded_keys),
                        "res": SUPERSEDED_RESOLUTION,
                        "now": changes.now,
                    },
                )
                superseded = int(getattr(result, "rowcount", 0) or 0)
            if changes.patient_updates:
                await session.execute(
                    text(
                        "UPDATE clinic.patient SET recommendation_at = :recommendation_at, "
                        "expected_visit_source = :source, expected_visit_reason = :reason, "
                        "last_protocol_session_id = :marker, version = version + 1 "
                        "WHERE clinic_id = :c AND id = :id"
                    ),
                    [
                        {
                            "c": clinic_id,
                            "id": u.patient_id,
                            "recommendation_at": u.recommendation_at,
                            "source": u.expected_visit_source,
                            "reason": u.expected_visit_reason,
                            "marker": u.last_protocol_session_id,
                        }
                        for u in changes.patient_updates
                    ],
                )
            if inserted or superseded or changes.patient_updates:
                await self._audit(
                    session,
                    clinic_id,
                    {
                        "new_tasks": inserted,
                        "superseded": superseded,
                        "patient_updates": len(changes.patient_updates),
                    },
                )
        return inserted

    async def _insert_tasks(self, session: AsyncSession, clinic_id: UUID, changes: StoreChanges) -> int:
        result = await session.execute(
            text(
                "INSERT INTO clinic.crm_task (clinic_id, task_key, patient_id, rule_key, reason, priority, "
                "status, "
                "owner_user_id, due_at, suggested_action, source_event_id, related_appointment_id, "
                "related_plan_id, created_at) "
                "VALUES (:c, :task_key, :patient_id, :rule_key, :reason, :priority, 'open', :owner, :due_at, "
                ":action, :source, CAST(:appointment AS uuid), CAST(:plan AS uuid), :created_at) "
                "ON CONFLICT (clinic_id, task_key) DO NOTHING"
            ),
            [
                {
                    "c": clinic_id,
                    "task_key": t.task_key,
                    "patient_id": t.patient_id,
                    "rule_key": t.rule_key.value,
                    "reason": t.reason,
                    "priority": t.priority.value,
                    "owner": t.owner_user_id,
                    "due_at": t.due_at,
                    "action": t.suggested_action,
                    "source": t.source_event_id,
                    "appointment": t.related_appointment_id,
                    "plan": t.related_plan_id,
                    "created_at": t.created_at,
                }
                for t in changes.new_tasks
            ],
        )
        rowcount = int(getattr(result, "rowcount", 0) or 0)
        return rowcount if rowcount >= 0 else len(changes.new_tasks)

    async def _audit(self, session: AsyncSession, clinic_id: UUID, details: Mapping[str, int]) -> None:
        """Field names and counts only, never patient data (AGENT.md)."""
        await session.execute(
            text(
                "INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, details) "
                "VALUES (:c, 'system', 'crm_rules.run', 'crm_rule', CAST(:details AS jsonb))"
            ),
            {"c": clinic_id, "details": json.dumps(dict(details))},
        )
