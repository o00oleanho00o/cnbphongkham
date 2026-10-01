"""Consent (``clinic.consent`` is an append-only history; the newest row of a kind is the current one).

New module. AGENT.md: "Keep consent for media and an audit shape for mutations"; PLAN-AI01:
``marketingOptOut``
blocks marketing. Revoking MARKETING consent therefore also sets ``patient.marketing_opt_out`` (a safety
choice: the rules engine of B2 reads that one flag). Granting it again does NOT clear the flag; staff do
that explicitly with ``PATCH /patients/{id}`` (open item for the product owner).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.actions._common import lost_race_is_conflict, now
from pema.clinic.actions._mappers import consent_out
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import Consent
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.patients import ConsentCreate, ConsentKind, ConsentOut
from pema_contracts.roles import Permission


async def list_consents(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> list[ConsentOut]:
    require(ctx, Permission.CONSENT_READ)
    async with db.session(ctx.clinic_id) as session:
        await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        rows = (
            await session.scalars(
                select(Consent)
                .where(Consent.clinic_id == ctx.clinic_id, Consent.patient_id == patient_id)
                .order_by(Consent.created_at.desc(), Consent.id.desc())
            )
        ).all()
        return [consent_out(row) for row in rows]


async def record_consent(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: ConsentCreate
) -> ConsentOut:
    require(ctx, Permission.CONSENT_WRITE)
    async with db.session(ctx.clinic_id) as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        stamp = now()
        row = Consent(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            kind=payload.kind.value,
            granted=payload.granted,
            granted_at=stamp if payload.granted else None,
            revoked_at=None if payload.granted else stamp,
            source=payload.source,
            recorded_by=ctx.actor_user_id,
        )
        session.add(row)
        opted_out = False
        if payload.kind is ConsentKind.MARKETING and not payload.granted and not patient.marketing_opt_out:
            patient.marketing_opt_out = True
            opted_out = True
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "consent.record",
            "consent",
            row.id,
            {
                "patient_id": str(patient_id),
                "kind": payload.kind.value,
                "granted": payload.granted,
                "marketing_opt_out_set": opted_out,
            },
        )
        return consent_out(row)
