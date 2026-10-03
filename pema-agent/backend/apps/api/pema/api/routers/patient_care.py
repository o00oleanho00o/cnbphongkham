"""Plans, sessions, consult notes and clinical photos of a patient (package U, step U3). Each route calls one
action of ``pema.clinic.actions``; nothing is decided here.

The photo upload is the one route that is not JSON: ``PUT /media/{id}/content`` takes the raw bytes at the
signed path of ``POST /patients/{id}/media/upload-intent``. The global body ceiling (4 MB) does not apply to
it
(``body_limit.is_exempt``); the route cuts the stream itself at ``MEDIA_MAX_BYTES``, at the reading layer.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import consult_notes, media, plans, sessions
from pema.clinic.media_storage import LocalVolumeMediaStorage, MediaStorage
from pema.config.env import get_settings
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.patient_care import (
    MEDIA_MAX_BYTES,
    ConsultNoteApprove,
    ConsultNoteDraftCreate,
    ConsultNoteOut,
    MediaOut,
    MediaUploadIntent,
    MediaUploadTarget,
    PlanCreate,
    PlanUpdate,
    SessionComplete,
    SessionCreate,
    SessionDetailOut,
    SessionReview,
)
from pema_contracts.patients import TreatmentPlanOut

router = APIRouter(
    tags=["patient-care"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)

_STORAGE_STATE = "media_storage"


def get_media_storage(request: Request) -> MediaStorage:
    """The photo storage of the application: ``app.state.media_storage`` when the composition root set one,
    otherwise the local volume under ``<data_dir>/clinic-media`` (built once)."""
    configured: object = getattr(request.app.state, _STORAGE_STATE, None)
    if isinstance(configured, MediaStorage):
        return configured
    storage = LocalVolumeMediaStorage(get_settings().data_dir / "clinic-media")
    setattr(request.app.state, _STORAGE_STATE, storage)
    return storage


def _secret() -> bytes:
    """Key of the signed upload paths: the secret that signs dashboard sessions (deny when it is not set)."""
    configured = get_settings().jwt_secret
    if configured is None or not configured.get_secret_value():
        raise DomainError(ErrorCode.INTERNAL, "Máy chủ chưa được cấu hình khóa ký.")
    return configured.get_secret_value().encode()


async def _read_capped(request: Request, limit: int) -> bytes:
    """The request body, cut the moment it crosses ``limit`` (also when there is no ``Content-Length``)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise DomainError(ErrorCode.PAYLOAD_TOO_LARGE, "Ảnh vượt quá dung lượng cho phép.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise DomainError(ErrorCode.PAYLOAD_TOO_LARGE, "Ảnh vượt quá dung lượng cho phép.")
        chunks.append(chunk)
    return b"".join(chunks)


Storage = Annotated[MediaStorage, Depends(get_media_storage)]


# ----------------------------------------------------------------------------------------------- plans
@router.get(
    "/patients/{patient_id}/plans",
    response_model=list[TreatmentPlanOut],
    summary="Treatment plans of a patient",
)
async def list_plans(patient_id: UUID, db: Database, ctx: Ctx) -> list[TreatmentPlanOut]:
    return await plans.list_plans(db, ctx, patient_id)


@router.post(
    "/patients/{patient_id}/plans",
    response_model=TreatmentPlanOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a treatment plan",
)
async def create_plan(patient_id: UUID, body: PlanCreate, db: Database, ctx: Ctx) -> TreatmentPlanOut:
    return await plans.create_plan(db, ctx, patient_id, body)


@router.patch("/plans/{plan_id}", response_model=TreatmentPlanOut, summary="Edit a treatment plan")
async def update_plan(plan_id: UUID, body: PlanUpdate, db: Database, ctx: Ctx) -> TreatmentPlanOut:
    return await plans.update_plan(db, ctx, plan_id, body)


# -------------------------------------------------------------------------------------------- sessions
@router.get(
    "/patients/{patient_id}/sessions",
    response_model=list[SessionDetailOut],
    summary="Treatment sessions of a patient with their clinical text",
)
async def list_sessions(patient_id: UUID, db: Database, ctx: Ctx) -> list[SessionDetailOut]:
    return await sessions.list_sessions(db, ctx, patient_id)


@router.post(
    "/patients/{patient_id}/sessions",
    response_model=SessionDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a treatment session (complete=true finishes it: counters, recall, missing-photo task)",
)
async def create_session(patient_id: UUID, body: SessionCreate, db: Database, ctx: Ctx) -> SessionDetailOut:
    return await sessions.create_session(db, ctx, patient_id, body)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=SessionDetailOut,
    summary="Finish a recorded session",
)
async def complete_session(
    session_id: UUID, body: SessionComplete, db: Database, ctx: Ctx
) -> SessionDetailOut:
    return await sessions.complete_session(db, ctx, session_id, body)


@router.post(
    "/sessions/{session_id}/review",
    response_model=SessionDetailOut,
    summary="A clinician signs off a completed session",
)
async def review_session(session_id: UUID, body: SessionReview, db: Database, ctx: Ctx) -> SessionDetailOut:
    return await sessions.review_session(db, ctx, session_id, body)


# --------------------------------------------------------------------------------------- consult notes
@router.get(
    "/patients/{patient_id}/consult-notes",
    response_model=list[ConsultNoteOut],
    summary="Consultation notes of a patient (drafts and approved)",
)
async def list_consult_notes(patient_id: UUID, db: Database, ctx: Ctx) -> list[ConsultNoteOut]:
    return await consult_notes.list_notes(db, ctx, patient_id)


@router.post(
    "/patients/{patient_id}/consult-notes",
    response_model=ConsultNoteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Compose a draft from a few key points (replaces the open draft)",
)
async def create_consult_draft(
    patient_id: UUID, body: ConsultNoteDraftCreate, db: Database, ctx: Ctx
) -> ConsultNoteOut:
    return await consult_notes.create_draft(db, ctx, patient_id, body)


@router.post(
    "/consult-notes/{note_id}/approve",
    response_model=ConsultNoteOut,
    summary="Approve a draft into Patient 360 (the clinician may have edited the text)",
)
async def approve_consult_note(
    note_id: UUID, body: ConsultNoteApprove, db: Database, ctx: Ctx
) -> ConsultNoteOut:
    return await consult_notes.approve_note(db, ctx, note_id, body)


# -------------------------------------------------------------------------------------------- photos
@router.post(
    "/patients/{patient_id}/media/upload-intent",
    response_model=MediaUploadTarget,
    status_code=status.HTTP_201_CREATED,
    summary="Ask to upload a clinical photo (needs the patient's media consent)",
)
async def media_upload_intent(
    patient_id: UUID, body: MediaUploadIntent, db: Database, ctx: Ctx
) -> MediaUploadTarget:
    return await media.upload_intent(db, ctx, patient_id, body, secret=_secret())


@router.put(
    "/media/{media_id}/content",
    response_model=MediaOut,
    summary="Send the bytes of a photo to the signed path of its upload intent",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp")
            },
        }
    },
)
async def upload_media_content(
    media_id: UUID,
    request: Request,
    db: Database,
    ctx: Ctx,
    storage: Storage,
    exp: Annotated[int, Query(description="Expiry of the signed path (unix seconds).")],
    sig: Annotated[str, Query(max_length=128, description="Signature of the signed path.")],
) -> MediaOut:
    data = await _read_capped(request, MEDIA_MAX_BYTES)
    return await media.store_content(
        db, storage, ctx, media_id, expires=exp, signature=sig, data=data, secret=_secret()
    )


@router.post(
    "/media/{media_id}/confirm",
    response_model=MediaOut,
    summary="Confirm an uploaded photo (resolves the session's missing-photo task)",
)
async def confirm_media(media_id: UUID, db: Database, ctx: Ctx, storage: Storage) -> MediaOut:
    return await media.confirm_upload(db, storage, ctx, media_id)


@router.get(
    "/patients/{patient_id}/media",
    response_model=list[MediaOut],
    summary="Clinical photos of a patient",
)
async def list_media(
    patient_id: UUID, db: Database, ctx: Ctx, session_id: UUID | None = None
) -> list[MediaOut]:
    return await media.list_media(db, ctx, patient_id, session_id=session_id)


@router.get(
    "/media/{media_id}/content",
    summary="The bytes of a clinical photo (audited; needs media.read and the consent)",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}},
)
async def media_content(media_id: UUID, db: Database, ctx: Ctx, storage: Storage) -> Response:
    data, mime = await media.read_content(db, storage, ctx, media_id)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
