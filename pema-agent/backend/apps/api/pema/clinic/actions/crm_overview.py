# ported from: prototype/shared/crm-automation.js (profile, metrics) and crm-ui.js (segment, protocol)
"""Read side of the CRM leftovers (package U, step U7): customer groups and the rule list.

The old CRM01 screens are covered elsewhere (queue and resolve sheet by ``/today``, KPI by ``/dashboard``,
the clinical and CRM panels by Patient 360, the activity log by ``crm_tasks.list_activities``). What had no
home were two cards of the CRM workspace: ``segment`` (the five lifecycle stages with the patients in each)
and ``protocol`` (the automation rules as read-only text). This module serves both. NOTHING here writes: the
marketing opt-out switch stays ``update_patient`` (audited as ``patient.update``) and the rules are tuned in
``crm_rules.admin`` by owner or manager.

Forced deviations: localStorage state becomes the SQL snapshot of ``SqlCrmRuleStore`` (one bulk read, no query
per patient); the fixed demo day becomes the clock of ``_common.now``. The stage of a patient is exactly
``compute_profile`` of package B2, so a card and the Patient 360 of the same person always agree. A doctor
sees the groups of the patients in their scope only (``patient_scope``).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import select

from pema.clinic.actions._common import now
from pema.clinic.actions._scope import patient_scope
from pema.clinic.crm_rules.engine import clinic_today
from pema.clinic.crm_rules.profile import compute_profile
from pema.clinic.crm_rules.records import ProfileView, RiskLevel
from pema.clinic.crm_rules.rules import DEFAULT_RULES
from pema.clinic.crm_rules.sql_store import SqlCrmRuleStore
from pema.clinic.models import CrmRule, Patient, UserAccount
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import Page
from pema_contracts.crm import (
    CrmRuleOut,
    CrmSegmentCount,
    CrmSegmentKey,
    CrmSegmentPatientOut,
    CrmSegmentsOut,
    RuleKey,
    RuleSendMode,
    TaskPriority,
)
from pema_contracts.roles import Permission

STAGE_KEYS: Final = (
    CrmSegmentKey.NEW,
    CrmSegmentKey.RETURNING,
    CrmSegmentKey.TREATING,
    CrmSegmentKey.DORMANT,
    CrmSegmentKey.REACTIVATED,
)


async def _profiles(db: ClinicDatabase, ctx: ActionContext) -> list[tuple[UUID, str, ProfileView]]:
    """``(patient id, code, profile)`` of every patient the caller may see, in code order."""
    current = now()
    data = await SqlCrmRuleStore(db).load(ctx.clinic_id, current)
    today = clinic_today(current)
    scope = patient_scope(ctx)
    allowed: set[UUID] | None = None
    if scope is not None:
        async with db.session() as session:
            allowed = set(
                await session.scalars(select(Patient.id).where(Patient.clinic_id == ctx.clinic_id, scope))
            )
    return [
        (p.id, p.code, compute_profile(p, today)) for p in data.patients if allowed is None or p.id in allowed
    ]


def _in_segment(profile: ProfileView, key: CrmSegmentKey) -> bool:
    if key is CrmSegmentKey.AT_RISK:
        return profile.risk_level is RiskLevel.HIGH
    return profile.lifecycle_stage.value == key.value


async def segments(db: ClinicDatabase, ctx: ActionContext) -> CrmSegmentsOut:
    require(ctx, Permission.CRM_TASK_READ)
    profiles = [profile for _, _, profile in await _profiles(db, ctx)]
    counts = [
        CrmSegmentCount(key=key, count=sum(1 for p in profiles if _in_segment(p, key)))
        for key in (*STAGE_KEYS, CrmSegmentKey.AT_RISK)
    ]
    return CrmSegmentsOut(
        total_patients=len(profiles),
        segments=counts,
        marketing_opt_out=sum(1 for p in profiles if p.marketing_opt_out),
    )


async def segment_patients(
    db: ClinicDatabase,
    ctx: ActionContext,
    key: CrmSegmentKey,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Page[CrmSegmentPatientOut]:
    """Patients of one group, the most overdue first, then by code."""
    require(ctx, Permission.CRM_TASK_READ)
    members = sorted(
        (
            (pid, code, profile)
            for pid, code, profile in await _profiles(db, ctx)
            if _in_segment(profile, key)
        ),
        key=lambda m: (-m[2].overdue_days, m[1]),
    )
    page = members[offset : offset + limit]
    rows: dict[UUID, tuple[Patient, str | None]] = {}
    if page:
        async with db.session() as session:
            result = await session.execute(
                select(Patient, UserAccount.display_name)
                .outerjoin(
                    UserAccount,
                    (UserAccount.id == Patient.cs_owner_id) & (UserAccount.clinic_id == Patient.clinic_id),
                )
                .where(Patient.clinic_id == ctx.clinic_id, Patient.id.in_([pid for pid, _, _ in page]))
            )
            rows = {patient.id: (patient, owner) for patient, owner in result.all()}
    items = [
        CrmSegmentPatientOut(
            patient_id=pid,
            patient_code=code,
            full_name=rows[pid][0].full_name,
            version=rows[pid][0].version,
            lifecycle_stage=CrmSegmentKey(profile.lifecycle_stage.value),
            last_visit_at=profile.last_visit_at,
            expected_next_visit_at=profile.expected_next_visit_at,
            overdue_days=profile.overdue_days,
            remaining_sessions=profile.remaining,
            risk_level=profile.risk_level.value,
            marketing_opt_out=profile.marketing_opt_out,
            cs_owner_name=rows[pid][1],
        )
        for pid, code, profile in page
        if pid in rows
    ]
    return Page[CrmSegmentPatientOut](items=items, total=len(members), limit=limit, offset=offset)


async def list_rules(db: ClinicDatabase, ctx: ActionContext) -> list[CrmRuleOut]:
    """The automation rules as text (``protocol`` card). Read only. A clinic that has never been seeded gets
    the ten defaults first (idempotent, same as ``crm_rules.admin.list_rules``), so the screen is never empty.
    Tuning is ``crm_rules.admin`` (owner or manager)."""
    require(ctx, Permission.CRM_TASK_READ)
    await SqlCrmRuleStore(db).ensure_rules(ctx.clinic_id)
    async with db.session() as session:
        rows = (await session.scalars(select(CrmRule).where(CrmRule.clinic_id == ctx.clinic_id))).all()
    by_key = {RuleKey(row.rule_key): row for row in rows}
    out: list[CrmRuleOut] = []
    for default in DEFAULT_RULES:
        row = by_key.get(default.key)
        if row is None:
            continue
        out.append(
            CrmRuleOut(
                id=row.id,
                rule_key=default.key,
                name=row.name,
                trigger=row.trigger,
                delay_days=row.delay_days,
                suggested_action=row.suggested_action,
                priority=TaskPriority(row.priority),
                active=row.active,
                send_mode=RuleSendMode(row.send_mode),
                conditions=dict(row.conditions),
                version=row.version,
            )
        )
    return out
