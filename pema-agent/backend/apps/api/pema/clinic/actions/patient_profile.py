# ported from: prototype/shared/clinic.js (save-facts), crm-automation.js (clinical, expected)
"""The doctor's small records on Patient 360: "Thông tin cần nhớ", "Tiền sử & chẩn đoán" and "Ngày dự
kiến quay lại" (actions behind ``routers/patient_profile.py``).

Forced deviation: the prototype kept ``p.alerts``, ``p.clinical`` and ``p.crm.recommendationAt`` in
``localStorage`` and checked the ``clinical`` / ``crm`` capability of the demo role switch. Here they are
columns and a table of ``clinic.*`` and the permission is a real one:

* ``save_alerts`` and ``save_clinical_note`` need ``session.write`` (the old ``clinical`` capability: doctor,
  owner) and the doctor's own patient (``Hồ sơ này không thuộc bác sĩ phụ trách.``);
* ``save_expected_return`` needs ``crm.activity.write`` (the old ``crm`` capability: owner, doctor, CSKH;
  also the manager);
* reading the diagnosis needs ``session.read`` and the same scope as the other clinical tabs.

The diagnosis is typed by a doctor. Nothing here is computed, suggested or filled in by a model. Audit details
carry ids, counts and field names, never the text. The photo consent of "Thông tin cần nhớ" is NOT
stored here:
the dialog calls the consent action of U3 (``POST /patients/{id}/consents``), so there is one consent history.
"""

from __future__ import annotations

import re
from datetime import date
from uuid import UUID

from sqlalchemy import select

from pema.clinic import audit
from pema.clinic.actions._clinical_scope import names_of, require_clinical_scope
from pema.clinic.actions._common import lost_race_is_conflict, now
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import PatientClinicalNote
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patient_profile import (
    CLINICAL_NOTE_BLANK_MESSAGE,
    EXPECTED_RETURN_INVALID_MESSAGE,
    EXPECTED_SOURCES,
    MAX_ALERT_CHARS,
    MAX_ALERTS,
    AlertsOut,
    AlertsUpdate,
    ClinicalNoteOut,
    ClinicalNoteUpdate,
    ExpectedReturnOut,
    ExpectedReturnUpdate,
)
from pema_contracts.roles import Permission

ALERT_TOO_LONG_MESSAGE = f"Mỗi cảnh báo tối đa {MAX_ALERT_CHARS} ký tự."
ALERTS_TOO_MANY_MESSAGE = f"Tối đa {MAX_ALERTS} cảnh báo."
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalise_alerts(lines: list[str]) -> list[str]:
    """Old ``alerts-edit``: ``split('\\n').map(trim).filter(Boolean)``. An entry that itself holds line breaks
    is split too, so the BE gives the same list whichever way the client sends it."""
    cleaned = [part.strip() for line in lines for part in line.splitlines()]
    return [part for part in cleaned if part]


async def save_alerts(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: AlertsUpdate
) -> AlertsOut:
    require(ctx, Permission.SESSION_WRITE)
    alerts = normalise_alerts(payload.alerts)
    if len(alerts) > MAX_ALERTS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, ALERTS_TOO_MANY_MESSAGE)
    if any(len(line) > MAX_ALERT_CHARS for line in alerts):
        raise DomainError(ErrorCode.VALIDATION_FAILED, ALERT_TOO_LONG_MESSAGE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        before = len(patient.alerts or [])
        patient.alerts = alerts
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "patient.alerts_save",
            "patient",
            patient.id,
            {"count_before": before, "count_after": len(alerts)},
        )
        return AlertsOut(alerts=alerts)


async def get_clinical_note(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> ClinicalNoteOut:
    require(ctx, Permission.SESSION_READ)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        row = await session.scalar(
            select(PatientClinicalNote).where(
                PatientClinicalNote.clinic_id == ctx.clinic_id, PatientClinicalNote.patient_id == patient_id
            )
        )
        if row is None:
            return ClinicalNoteOut()
        names = await names_of(session, ctx, [row.reviewed_by])
        return ClinicalNoteOut(
            history=row.history,
            diagnosis=row.diagnosis,
            reviewed_by_name=names.get(row.reviewed_by) if row.reviewed_by else None,
            reviewed_at=row.reviewed_at,
        )


async def save_clinical_note(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: ClinicalNoteUpdate
) -> ClinicalNoteOut:
    """Old ``clinical``: both texts are required; the doctor who saved it and the day are kept."""
    require(ctx, Permission.SESSION_WRITE)
    history = payload.history.strip()
    diagnosis = payload.diagnosis.strip()
    if history == "" or diagnosis == "":
        raise DomainError(ErrorCode.VALIDATION_FAILED, CLINICAL_NOTE_BLANK_MESSAGE)
    async with db.session() as session:
        await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        row = await session.scalar(
            select(PatientClinicalNote)
            .where(
                PatientClinicalNote.clinic_id == ctx.clinic_id, PatientClinicalNote.patient_id == patient_id
            )
            .with_for_update()
        )
        stamp = now()
        created = row is None
        if row is None:
            row = PatientClinicalNote(
                clinic_id=ctx.clinic_id,
                patient_id=patient_id,
                history=history,
                diagnosis=diagnosis,
                reviewed_by=ctx.actor_user_id,
                reviewed_at=stamp,
            )
            session.add(row)
        else:
            row.history = history
            row.diagnosis = diagnosis
            row.reviewed_by = ctx.actor_user_id
            row.reviewed_at = stamp
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "patient.clinical_note_save",
            "patient_clinical_note",
            row.id,
            {"patient_id": str(patient_id), "created": created, "fields": ["history", "diagnosis"]},
        )
        names = await names_of(session, ctx, [row.reviewed_by])
        return ClinicalNoteOut(
            history=row.history,
            diagnosis=row.diagnosis,
            reviewed_by_name=names.get(row.reviewed_by) if row.reviewed_by else None,
            reviewed_at=row.reviewed_at,
        )


def parse_expected_return(payload: ExpectedReturnUpdate) -> tuple[date, str, str]:
    """Old ``expected()`` validation: a real calendar day written ``YYYY-MM-DD``, a reason that is not blank,
    and one of the sources a person may type (never ``appointment``). One sentence for every failure."""
    day: date | None = None
    if _ISO_DAY.match(payload.date):
        try:
            day = date.fromisoformat(payload.date)
        except ValueError:
            day = None
    reason = payload.reason.strip()
    if day is None or reason == "" or payload.source not in EXPECTED_SOURCES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, EXPECTED_RETURN_INVALID_MESSAGE)
    return day, reason, payload.source


async def save_expected_return(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: ExpectedReturnUpdate
) -> ExpectedReturnOut:
    """'Ngày dự kiến quay lại'. A real appointment still wins in Patient 360 and the recommendation is kept
    when the booking is cancelled (``compute_profile``); this only writes the recommendation."""
    require(ctx, Permission.CRM_ACTIVITY_WRITE)
    day, reason, source = parse_expected_return(payload)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        patient.recommendation_at = day
        patient.expected_visit_reason = reason
        patient.expected_visit_source = source
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "patient.expected_return_save",
            "patient",
            patient.id,
            {"recommendation_at": day.isoformat(), "source": source},
        )
        return ExpectedReturnOut(date=day.isoformat(), reason=reason, source=source)


__all__ = [
    "get_clinical_note",
    "normalise_alerts",
    "parse_expected_return",
    "save_alerts",
    "save_clinical_note",
    "save_expected_return",
]
