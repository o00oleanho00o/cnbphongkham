"""Patient 360 dialogs of package U, step U9: warnings, history and diagnosis, expected return, notes on
the patient app timeline, the templated brief and "Thêm dịch vụ vào liệu trình". Each route calls one
action; nothing is decided here."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import patient_app, patient_profile, plans
from pema_contracts.patient_profile import (
    AlertsOut,
    AlertsUpdate,
    AppUpdateCreate,
    AppUpdateKind,
    AppUpdateOut,
    BriefApprove,
    BriefApprovedOut,
    BriefDraftOut,
    ClinicalNoteOut,
    ClinicalNoteUpdate,
    ExpectedReturnOut,
    ExpectedReturnUpdate,
    PatientFinanceTabOut,
    ServicePlanCreate,
)
from pema_contracts.patients import TreatmentPlanOut

router = APIRouter(
    tags=["patient-profile"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.put("/patients/{patient_id}/alerts", response_model=AlertsOut, summary="Save 'Thông tin cần nhớ'")
async def save_alerts(patient_id: UUID, body: AlertsUpdate, db: Database, ctx: Ctx) -> AlertsOut:
    return await patient_profile.save_alerts(db, ctx, patient_id, body)


@router.get(
    "/patients/{patient_id}/clinical-note",
    response_model=ClinicalNoteOut,
    summary="'Tiền sử & chẩn đoán' recorded by a doctor",
)
async def get_clinical_note(patient_id: UUID, db: Database, ctx: Ctx) -> ClinicalNoteOut:
    return await patient_profile.get_clinical_note(db, ctx, patient_id)


@router.put(
    "/patients/{patient_id}/clinical-note",
    response_model=ClinicalNoteOut,
    summary="A doctor saves 'Tiền sử & chẩn đoán' (both texts required)",
)
async def save_clinical_note(
    patient_id: UUID, body: ClinicalNoteUpdate, db: Database, ctx: Ctx
) -> ClinicalNoteOut:
    return await patient_profile.save_clinical_note(db, ctx, patient_id, body)


@router.put(
    "/patients/{patient_id}/expected-return",
    response_model=ExpectedReturnOut,
    summary="Save 'Ngày dự kiến quay lại' (date, reason, source)",
)
async def save_expected_return(
    patient_id: UUID, body: ExpectedReturnUpdate, db: Database, ctx: Ctx
) -> ExpectedReturnOut:
    return await patient_profile.save_expected_return(db, ctx, patient_id, body)


@router.get(
    "/patients/{patient_id}/app-updates",
    response_model=list[AppUpdateOut],
    summary="Notes on the patient app timeline, newest first",
)
async def list_app_updates(
    patient_id: UUID, db: Database, ctx: Ctx, kind: AppUpdateKind | None = None
) -> list[AppUpdateOut]:
    return await patient_app.list_updates(db, ctx, patient_id, kind)


@router.post(
    "/patients/{patient_id}/app-updates",
    response_model=AppUpdateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Put a note ('Nhắn tin' or 'Chăm sóc tại nhà') on the patient app timeline; no channel is used",
)
async def send_app_update(patient_id: UUID, body: AppUpdateCreate, db: Database, ctx: Ctx) -> AppUpdateOut:
    return await patient_app.send_update(db, ctx, patient_id, body)


@router.get(
    "/patients/{patient_id}/brief",
    response_model=BriefDraftOut,
    summary="The templated brief of a patient (built from records, no model); a doctor edits and approves it",
)
async def get_brief(patient_id: UUID, db: Database, ctx: Ctx) -> BriefDraftOut:
    return await patient_app.get_brief(db, ctx, patient_id)


@router.post(
    "/patients/{patient_id}/brief/approve",
    response_model=BriefApprovedOut,
    status_code=status.HTTP_201_CREATED,
    summary="A doctor approves the brief as edited",
)
async def approve_brief(patient_id: UUID, body: BriefApprove, db: Database, ctx: Ctx) -> BriefApprovedOut:
    return await patient_app.approve_brief(db, ctx, patient_id, body)


@router.post(
    "/patients/{patient_id}/service-plans",
    response_model=TreatmentPlanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a catalog service to the course; its price is fixed on the plan",
)
async def add_service_plan(
    patient_id: UUID, body: ServicePlanCreate, db: Database, ctx: Ctx
) -> TreatmentPlanOut:
    return await plans.add_service_plan(db, ctx, patient_id, body)


@router.get(
    "/patients/{patient_id}/finance-tab",
    response_model=PatientFinanceTabOut,
    summary="Courses and prices of a patient for the finance tab; no clinical record (finance.read)",
)
async def get_finance_tab(patient_id: UUID, db: Database, ctx: Ctx) -> PatientFinanceTabOut:
    return await plans.finance_tab(db, ctx, patient_id)
