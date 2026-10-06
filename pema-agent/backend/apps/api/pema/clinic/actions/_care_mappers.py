"""ORM rows of the Patient 360 tabs to wire DTOs (package U, step U3). New module; conversion only."""

from __future__ import annotations

from pema.clinic.models import ConsultNote, Media, TreatmentPlan, TreatmentSession
from pema.clinic.rbac import has_permission
from pema_contracts.actions import ActionContext
from pema_contracts.patient_care import (
    ConsultNoteOut,
    ConsultNoteStatus,
    MediaOut,
    MediaStage,
    MediaStatus,
    SessionDetailOut,
)
from pema_contracts.patients import TreatmentPlanOut, TreatmentSessionOut
from pema_contracts.roles import Permission


def plan_out(row: TreatmentPlan, *, money: bool = False) -> TreatmentPlanOut:
    """``money`` shows the price fixed on the plan; only a caller with a finance permission gets it
    (``plan_money_visible``), so care staff see the sessions and never the amounts."""
    return TreatmentPlanOut(
        id=row.id,
        episode_id=row.episode_id,
        service_code=row.service_code,
        title=row.title,
        total_sessions=row.total_sessions,
        completed_sessions=row.completed_sessions,
        status=row.status,
        goal=row.goal,
        doctor_id=row.doctor_id,
        version=row.version,
        unit_price_vnd=row.unit_price_vnd if money else None,
        discount_vnd=row.discount_vnd if money else None,
        agreed_price_vnd=row.agreed_price_vnd if money else None,
        service_terms_version=row.service_terms_version if money else None,
    )


def plan_money_visible(ctx: ActionContext) -> bool:
    """True for a caller who reads, collects or writes finance: owner, manager (and the accountant of U11)."""
    return any(
        has_permission(ctx, permission)
        for permission in (Permission.FINANCE_READ, Permission.FINANCE_COLLECT, Permission.FINANCE_WRITE)
    )


def session_out(row: TreatmentSession) -> TreatmentSessionOut:
    """The light form (Patient 360 lists): no clinical text."""
    return TreatmentSessionOut(
        id=row.id,
        plan_id=row.plan_id,
        performed_at=row.performed_at,
        doctor_id=row.doctor_id,
        protocol_id=row.protocol_id,
        title=row.title,
        status=row.status,
        session_type=row.session_type,
        region=row.region,
        view=row.view,
        next_visit_on=row.next_visit_on,
        reviewed=row.reviewed,
        version=row.version,
    )


def session_detail_out(row: TreatmentSession, doctor_name: str | None) -> SessionDetailOut:
    return SessionDetailOut(
        **session_out(row).model_dump(),
        patient_id=row.patient_id,
        doctor_name=doctor_name,
        note=row.note,
        aftercare=row.aftercare,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        consent_id=row.consent_id,
    )


def note_out(row: ConsultNote, created_by_name: str | None, approved_by_name: str | None) -> ConsultNoteOut:
    return ConsultNoteOut(
        id=row.id,
        patient_id=row.patient_id,
        status=ConsultNoteStatus(row.status),
        source_text=row.source_text,
        body=row.body,
        created_by=row.created_by,
        created_by_name=created_by_name,
        approved_by=row.approved_by,
        approved_by_name=approved_by_name,
        approved_at=row.approved_at,
        created_at=row.created_at,
        version=row.version,
    )


def media_out(row: Media, uploader_name: str | None, *, consent_active: bool) -> MediaOut:
    return MediaOut(
        id=row.id,
        patient_id=row.patient_id,
        session_id=row.session_id,
        stage=MediaStage(row.stage),
        region=row.region,
        view=row.view,
        mime=row.mime,
        size_bytes=row.size_bytes,
        status=MediaStatus(row.status),
        consent_id=row.consent_id,
        consent_active=consent_active,
        uploaded_by=row.uploaded_by,
        uploaded_by_name=uploader_name,
        created_at=row.created_at,
        confirmed_at=row.confirmed_at,
        content_path=f"/api/v1/media/{row.id}/content",
        version=row.version,
    )
