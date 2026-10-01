"""Patients, Patient 360, consent (package B1). Each route calls one action."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, Limit, Offset, cookie_scheme
from pema.clinic.actions import consents, patient_360, patients
from pema_contracts.common import Page
from pema_contracts.patients import (
    ConsentCreate,
    ConsentOut,
    Patient360,
    PatientCreate,
    PatientOut,
    PatientUpdate,
)

router = APIRouter(
    tags=["patients"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get("/patients", response_model=Page[PatientOut], summary="Search patients")
async def list_patients(
    db: Database,
    ctx: Ctx,
    q: Annotated[str | None, Query(max_length=120, description="Name, phone or code.")] = None,
    doctor_id: UUID | None = None,
    cs_owner_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> Page[PatientOut]:
    return await patients.list_patients(
        db, ctx, q=q, doctor_id=doctor_id, cs_owner_id=cs_owner_id, limit=limit, offset=offset
    )


@router.post(
    "/patients",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a patient",
)
async def create_patient(body: PatientCreate, db: Database, ctx: Ctx) -> PatientOut:
    return await patients.create_patient(db, ctx, body)


@router.get("/patients/{patient_id}", response_model=PatientOut, summary="Patient identity record")
async def get_patient(patient_id: UUID, db: Database, ctx: Ctx) -> PatientOut:
    return await patients.get_patient(db, ctx, patient_id)


@router.patch("/patients/{patient_id}", response_model=PatientOut, summary="Update a patient")
async def update_patient(patient_id: UUID, body: PatientUpdate, db: Database, ctx: Ctx) -> PatientOut:
    return await patients.update_patient(db, ctx, patient_id, body)


@router.get(
    "/patients/{patient_id}/360",
    response_model=Patient360,
    summary="Patient 360 read model (original records stay the source of truth)",
)
async def get_patient_360(patient_id: UUID, db: Database, ctx: Ctx) -> Patient360:
    return await patient_360.get_patient_360(db, ctx, patient_id)


@router.get(
    "/patients/{patient_id}/consents",
    response_model=list[ConsentOut],
    summary="Consents of a patient",
)
async def list_consents(patient_id: UUID, db: Database, ctx: Ctx) -> list[ConsentOut]:
    return await consents.list_consents(db, ctx, patient_id)


@router.post(
    "/patients/{patient_id}/consents",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a consent grant or revocation",
)
async def record_consent(patient_id: UUID, body: ConsentCreate, db: Database, ctx: Ctx) -> ConsentOut:
    return await consents.record_consent(db, ctx, patient_id, body)
