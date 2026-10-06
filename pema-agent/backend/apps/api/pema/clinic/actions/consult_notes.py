# ported from: prototype/shared/clinic.js (``consult``, ``generate-note``, ``approve-note``)
"""Consultation notes of the Tư vấn tab: list, draft, approve (actions behind ``routers/patient_care.py``).

The old tab took a few key points typed by the doctor, built a structured draft (``generate-note``: the points
plus a fixed closing sentence), let the doctor edit it, and ``approve-note`` turned the edited text into a
Patient 360 event "Ghi chú tư vấn đã được duyệt". Same here, minus the browser: the draft is a
``clinic.consult_note`` row in status ``draft`` (one open draft per patient: a new draft replaces the text of
the open one, like ``p.notes`` was overwritten), the approval makes it ``approved`` and part of the timeline.

The draft is composed from a template, not by a model; the screen text of the old web ("Bác sĩ cần xem, sửa và
xác nhận trước khi lưu vào hồ sơ") still holds: nothing is part of the record until a clinician approves it.

Rules: ``session.write`` (doctor, owner) drafts and approves; ``session.read`` reads (doctor, owner, and care
staff for the patients they look after). Audit details carry ids only, never the text.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._care_mappers import note_out
from pema.clinic.actions._clinical_scope import names_of, require_clinical_scope
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found, now
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import ConsultNote
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patient_care import (
    ConsultNoteApprove,
    ConsultNoteDraftCreate,
    ConsultNoteOut,
    ConsultNoteStatus,
)
from pema_contracts.roles import Permission

EMPTY_INPUT_MESSAGE = "Hãy nhập vài ý chính trước."
EMPTY_DRAFT_MESSAGE = "Bản nháp không được để trống."
DRAFT_CLOSING = (
    "Đáp ứng cần được đối chiếu với ảnh mốc và phản hồi của người bệnh. "
    "Kế hoạch tiếp theo cần bác sĩ xác nhận."
)
"""The fixed sentence the old ``generate-note`` appended to the typed points."""


def compose_draft(input_text: str, today_label: str) -> str:
    """``Bản nháp ghi chú · <date>: <points> <closing>`` (old ``p.notes`` template)."""
    return f"Bản nháp ghi chú · {today_label}: {input_text.strip()} {DRAFT_CLOSING}"


def _date_label() -> str:
    return now().astimezone(VN_TZ).strftime("%d/%m/%Y")


async def _out(session: AsyncSession, ctx: ActionContext, row: ConsultNote) -> ConsultNoteOut:
    names = await names_of(session, ctx, [row.created_by, row.approved_by])
    return note_out(
        row,
        names.get(row.created_by) if row.created_by else None,
        names.get(row.approved_by) if row.approved_by else None,
    )


async def list_notes(db: ClinicDatabase, ctx: ActionContext, patient_id: UUID) -> list[ConsultNoteOut]:
    require(ctx, Permission.SESSION_READ)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        rows = (
            await session.scalars(
                select(ConsultNote)
                .where(ConsultNote.clinic_id == ctx.clinic_id, ConsultNote.patient_id == patient_id)
                .order_by(ConsultNote.created_at.desc(), ConsultNote.id)
            )
        ).all()
        names = await names_of(session, ctx, [u for r in rows for u in (r.created_by, r.approved_by)])
        await audit.record(session, ctx, "consult_note.list", "patient", patient_id)
        return [
            note_out(
                r,
                names.get(r.created_by) if r.created_by else None,
                names.get(r.approved_by) if r.approved_by else None,
            )
            for r in rows
        ]


async def create_draft(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, payload: ConsultNoteDraftCreate
) -> ConsultNoteOut:
    require(ctx, Permission.SESSION_WRITE)
    points = payload.input_text.strip()
    if not points:
        raise DomainError(ErrorCode.VALIDATION_FAILED, EMPTY_INPUT_MESSAGE)
    async with db.session() as session:
        await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        body = compose_draft(points, _date_label())
        row = await session.scalar(
            select(ConsultNote).where(
                ConsultNote.clinic_id == ctx.clinic_id,
                ConsultNote.patient_id == patient_id,
                ConsultNote.status == ConsultNoteStatus.DRAFT.value,
            )
        )
        replaced = row is not None
        if row is None:
            row = ConsultNote(
                clinic_id=ctx.clinic_id,
                patient_id=patient_id,
                status=ConsultNoteStatus.DRAFT.value,
                source_text=points,
                body=body,
                created_by=ctx.actor_user_id,
            )
            session.add(row)
        else:
            row.source_text = points
            row.body = body
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "consult_note.draft",
            "consult_note",
            row.id,
            {"patient_id": str(patient_id), "replaced_draft": replaced},
        )
        return await _out(session, ctx, row)


async def approve_note(
    db: ClinicDatabase, ctx: ActionContext, note_id: UUID, payload: ConsultNoteApprove
) -> ConsultNoteOut:
    require(ctx, Permission.SESSION_WRITE)
    async with db.session() as session:
        row = await session.scalar(
            select(ConsultNote).where(ConsultNote.clinic_id == ctx.clinic_id, ConsultNote.id == note_id)
        )
        if row is None:
            raise not_found("ghi chú tư vấn")
        await require_patient_access(session, ctx, row.patient_id)
        check_version(row.version, payload.version)
        if row.status != ConsultNoteStatus.DRAFT.value:
            raise DomainError(ErrorCode.INVALID_STATE, "Ghi chú này đã được duyệt.")
        body = (payload.body if payload.body is not None else row.body).strip()
        if not body:
            raise DomainError(ErrorCode.VALIDATION_FAILED, EMPTY_DRAFT_MESSAGE)
        row.body = body
        row.status = ConsultNoteStatus.APPROVED.value
        row.approved_by = ctx.actor_user_id
        row.approved_at = now()
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "consult_note.approve",
            "consult_note",
            row.id,
            {"patient_id": str(row.patient_id)},
        )
        return await _out(session, ctx, row)
