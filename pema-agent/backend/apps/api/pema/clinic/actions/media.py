# ported from: prototype/shared/clinic.js (``photos``, ``session-photo``, ``session-consent``)
"""Clinical photos of the Ảnh trước / sau tab: upload intent, store, confirm, list, read (actions behind
``routers/patient_care.py``).

What the old web did: the doctor chose a file in the session form, the prototype checked type and size
(``Pema.imageData``), refused it without the consent checkbox ("Cần xác nhận đồng ý ảnh khi lưu ảnh mốc") and
kept a data URL in ``localStorage``. Forced deviation, after ``docs/ARCH-PB01.md``
("POST /media/upload-intent: signed URL, size/malware check"; "Chuyển media khỏi localStorage sang
object storage với consent/retention"):

1. ``upload_intent``: needs ``media.write`` for a patient the caller may open, a MIME type of
   ``MEDIA_MIME_TYPES``, a size up to ``MEDIA_MAX_BYTES`` and the patient's CURRENT media consent (newest
   ``consent`` row of kind ``media`` is a grant); answers with a signed, expiring path and a ``pending`` row;
2. ``store_content``: the bytes arrive at that path; size must equal the declared one, the first bytes must be
   the signature of the declared type, the consent is checked again; the bytes go to ``MediaStorage``, the row
   becomes ``uploaded``;
3. ``confirm_upload``: staff confirm; the object must exist and the consent still hold; the row becomes
   ``confirmed`` and the task "Thiếu ảnh mốc đánh giá" of the session, if open, is resolved;
4. ``list_media`` / ``read_content``: ``media.read``; care staff only for their patients and only while the
   media consent is granted; every read of the bytes is audited.

No code here opens, decodes, resizes or analyses an image (PLAN-AI01-U principle 6), and there is no
thumbnail: the browser scales the original. Audit details carry ids, the stage, the MIME type and the size,
never a file name.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._care_mappers import media_out
from pema.clinic.actions._clinical_scope import (
    CLINICIAN_ROLES,
    current_media_consent,
    names_of,
    require_clinical_scope,
)
from pema.clinic.actions._common import lost_race_is_conflict, not_found, now
from pema.clinic.actions.patients import load_patient
from pema.clinic.actions.sessions import missing_photo_task_key
from pema.clinic.media_signing import expiry_for, matches_signature, sign_upload, verify_upload
from pema.clinic.media_storage import MediaStorage, MediaStorageError
from pema.clinic.models import CrmTask, Media, TreatmentSession
from pema.clinic.rbac import is_role, require
from pema.core.db import ClinicDatabase
from pema.live import emit_live
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEventType
from pema_contracts.patient_care import (
    MEDIA_MAX_BYTES,
    MEDIA_MIME_TYPES,
    MediaOut,
    MediaStatus,
    MediaUploadIntent,
    MediaUploadTarget,
)
from pema_contracts.roles import Permission

CONSENT_REQUIRED_MESSAGE = "Cần ghi nhận đồng ý hình ảnh của người bệnh trước khi tải ảnh lên."
BAD_LINK_MESSAGE = "Liên kết tải ảnh không hợp lệ hoặc đã hết hạn. Hãy chọn ảnh lại."
OPEN_TASK_STATUSES = ("open", "rescheduled")


def _uploader_may_continue(ctx: ActionContext, row: Media) -> bool:
    """The person who asked for the upload, or a clinician, may continue it."""
    return row.uploaded_by == ctx.actor_user_id or is_role(ctx, *CLINICIAN_ROLES)


async def _load_media(session: AsyncSession, ctx: ActionContext, media_id: UUID) -> Media:
    row = await session.scalar(select(Media).where(Media.clinic_id == ctx.clinic_id, Media.id == media_id))
    if row is None:
        raise not_found("ảnh")
    return row


async def upload_intent(
    db: ClinicDatabase,
    ctx: ActionContext,
    patient_id: UUID,
    payload: MediaUploadIntent,
    *,
    secret: bytes,
) -> MediaUploadTarget:
    require(ctx, Permission.MEDIA_WRITE)
    if payload.mime not in MEDIA_MIME_TYPES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Chỉ nhận ảnh PNG, JPEG hoặc WebP.")
    if payload.size_bytes > MEDIA_MAX_BYTES:
        raise DomainError(
            ErrorCode.PAYLOAD_TOO_LARGE, f"Ảnh vượt quá {MEDIA_MAX_BYTES // (1024 * 1024)} MB.", details=None
        )
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        consent = await current_media_consent(session, ctx, patient_id)
        if consent is None:
            raise DomainError(ErrorCode.CONSENT_REQUIRED, CONSENT_REQUIRED_MESSAGE)
        if payload.session_id is not None:
            found = await session.scalar(
                select(TreatmentSession.id).where(
                    TreatmentSession.clinic_id == ctx.clinic_id,
                    TreatmentSession.id == payload.session_id,
                    TreatmentSession.patient_id == patient_id,
                )
            )
            if found is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "Buổi điều trị không thuộc người bệnh này.")
        media_id = uuid4()
        row = Media(
            id=media_id,
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            session_id=payload.session_id,
            stage=payload.stage.value,
            region=payload.region,
            view=payload.view,
            storage_key=f"patients/{patient_id}/{media_id}",
            mime=payload.mime,
            size_bytes=payload.size_bytes,
            consent_id=consent.id,
            status=MediaStatus.PENDING.value,
            uploaded_by=ctx.actor_user_id,
        )
        session.add(row)
        with lost_race_is_conflict():
            await session.flush()
        stamp = now()
        expires = expiry_for(stamp)
        signature = sign_upload(secret, str(media_id), expires, row.size_bytes, row.mime)
        await audit.record(
            session,
            ctx,
            "media.upload_intent",
            "media",
            media_id,
            {
                "patient_id": str(patient_id),
                "stage": row.stage,
                "mime": row.mime,
                "size_bytes": row.size_bytes,
                "consent_id": str(consent.id),
            },
        )
    return MediaUploadTarget(
        media_id=media_id,
        upload_path=f"/api/v1/media/{media_id}/content?exp={expires}&sig={signature}",
        mime=payload.mime,
        max_bytes=MEDIA_MAX_BYTES,
        expires_at=datetime.fromtimestamp(expires, tz=VN_TZ),
    )


async def store_content(
    db: ClinicDatabase,
    storage: MediaStorage,
    ctx: ActionContext,
    media_id: UUID,
    *,
    expires: int,
    signature: str,
    data: bytes,
    secret: bytes,
) -> MediaOut:
    require(ctx, Permission.MEDIA_WRITE)
    async with db.session() as session:
        row = await _load_media(session, ctx, media_id)
        patient = await load_patient(session, ctx, row.patient_id)
        await require_clinical_scope(session, ctx, patient)
        if not _uploader_may_continue(ctx, row):
            raise DomainError(ErrorCode.FORBIDDEN, BAD_LINK_MESSAGE)
        if not verify_upload(secret, str(row.id), expires, row.size_bytes, row.mime, signature, now()):
            raise DomainError(ErrorCode.FORBIDDEN, BAD_LINK_MESSAGE)
        if row.status != MediaStatus.PENDING.value:
            raise DomainError(ErrorCode.INVALID_STATE, "Ảnh này đã được tải lên.")
        if await current_media_consent(session, ctx, row.patient_id) is None:
            raise DomainError(ErrorCode.CONSENT_REQUIRED, CONSENT_REQUIRED_MESSAGE)
        if len(data) != row.size_bytes:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Dung lượng ảnh không khớp với khai báo.")
        if not matches_signature(row.mime, data[:16]):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Nội dung tệp không khớp định dạng ảnh đã chọn.")
        digest = hashlib.sha256(data).hexdigest()
        await storage.put(row.storage_key, data)
        row.sha256 = digest
        row.status = MediaStatus.UPLOADED.value
        row.uploaded_at = now()
        try:
            with lost_race_is_conflict():
                await session.flush()
            await audit.record(
                session,
                ctx,
                "media.upload",
                "media",
                row.id,
                {"patient_id": str(row.patient_id), "mime": row.mime, "size_bytes": row.size_bytes},
            )
        except Exception:
            await storage.delete(row.storage_key)
            raise
        names = await names_of(session, ctx, [row.uploaded_by])
        return media_out(row, names.get(row.uploaded_by) if row.uploaded_by else None, consent_active=True)


async def confirm_upload(
    db: ClinicDatabase, storage: MediaStorage, ctx: ActionContext, media_id: UUID
) -> MediaOut:
    require(ctx, Permission.MEDIA_WRITE)
    resolved = False
    async with db.session() as session:
        row = await _load_media(session, ctx, media_id)
        patient = await load_patient(session, ctx, row.patient_id)
        await require_clinical_scope(session, ctx, patient)
        if not _uploader_may_continue(ctx, row):
            raise DomainError(ErrorCode.FORBIDDEN, BAD_LINK_MESSAGE)
        consent = await current_media_consent(session, ctx, row.patient_id)
        if row.status == MediaStatus.CONFIRMED.value:
            names = await names_of(session, ctx, [row.uploaded_by])
            return media_out(
                row,
                names.get(row.uploaded_by) if row.uploaded_by else None,
                consent_active=consent is not None,
            )
        if row.status != MediaStatus.UPLOADED.value:
            raise DomainError(ErrorCode.INVALID_STATE, "Ảnh chưa được tải lên xong.")
        if consent is None:
            raise DomainError(ErrorCode.CONSENT_REQUIRED, CONSENT_REQUIRED_MESSAGE)
        if not await storage.exists(row.storage_key):
            raise DomainError(ErrorCode.INVALID_STATE, "Không tìm thấy tệp ảnh đã tải lên. Hãy tải lại.")
        row.status = MediaStatus.CONFIRMED.value
        row.confirmed_at = now()
        if row.session_id is not None:
            task = await session.scalar(
                select(CrmTask).where(
                    CrmTask.clinic_id == ctx.clinic_id,
                    CrmTask.task_key == missing_photo_task_key(row.session_id),
                    CrmTask.status.in_(OPEN_TASK_STATUSES),
                )
            )
            if task is not None:
                task.status = "resolved"
                task.resolved_at = now()
                task.resolution = "Đã bổ sung ảnh mốc."
                resolved = True
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "media.confirm",
            "media",
            row.id,
            {"patient_id": str(row.patient_id), "missing_photo_task_resolved": resolved},
        )
        names = await names_of(session, ctx, [row.uploaded_by])
        out = media_out(row, names.get(row.uploaded_by) if row.uploaded_by else None, consent_active=True)
    if resolved:
        emit_live(LiveEventType.TASKS_CHANGED)
    return out


async def list_media(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, *, session_id: UUID | None = None
) -> list[MediaOut]:
    require(ctx, Permission.MEDIA_READ)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_clinical_scope(session, ctx, patient)
        conditions = [
            Media.clinic_id == ctx.clinic_id,
            Media.patient_id == patient_id,
            Media.status != MediaStatus.PENDING.value,
        ]
        if session_id is not None:
            conditions.append(Media.session_id == session_id)
        rows = (
            await session.scalars(select(Media).where(*conditions).order_by(Media.created_at, Media.id))
        ).all()
        active = await current_media_consent(session, ctx, patient_id) is not None
        names = await names_of(session, ctx, [r.uploaded_by for r in rows])
        return [
            media_out(r, names.get(r.uploaded_by) if r.uploaded_by else None, consent_active=active)
            for r in rows
        ]


async def read_content(
    db: ClinicDatabase, storage: MediaStorage, ctx: ActionContext, media_id: UUID
) -> tuple[bytes, str]:
    """The bytes and the MIME type of a stored photo. Every call is audited."""
    require(ctx, Permission.MEDIA_READ)
    async with db.session() as session:
        row = await _load_media(session, ctx, media_id)
        if row.status == MediaStatus.PENDING.value:
            raise not_found("ảnh")
        patient = await load_patient(session, ctx, row.patient_id)
        await require_clinical_scope(session, ctx, patient)
        if (
            not is_role(ctx, *CLINICIAN_ROLES)
            and await current_media_consent(session, ctx, row.patient_id) is None
        ):
            raise DomainError(
                ErrorCode.CONSENT_REQUIRED, "Người bệnh chưa đồng ý hoặc đã rút đồng ý hình ảnh."
            )
        try:
            data = await storage.get(row.storage_key)
        except MediaStorageError as exc:
            raise not_found("tệp ảnh") from exc
        await audit.record(
            session,
            ctx,
            "media.read",
            "media",
            row.id,
            {"patient_id": str(row.patient_id)},
        )
        return data, row.mime
