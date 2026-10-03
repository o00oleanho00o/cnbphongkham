"""Plans, sessions, consult notes and clinical photos of one patient (package U, step U3).

DTOs behind ``routers/patient_care.py``. Free text of a session or a note is clinical content: it travels in
these bodies only, never in audit details, logs or the agent's view. A photo is a record with a consent;
no DTO here describes the content of an image.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.patients import TreatmentSessionOut

MAX_PLAN_SESSIONS: Final = 20
"""Old ``plan-total`` input: ``max="20"``."""
MEDIA_MAX_BYTES: Final = 8 * 1024 * 1024
"""Largest photo the upload accepts (the BE's choice; the prototype only checked type and size)."""
MEDIA_MIME_TYPES: Final = ("image/jpeg", "image/png", "image/webp")
"""Old ``accept="image/png,image/jpeg,image/webp"`` of the photo inputs."""


class PlanStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


class PlanCreate(ApiModel):
    title: str = Field(min_length=1, max_length=120)
    service_code: str = Field(min_length=1, max_length=60)
    total_sessions: int = Field(ge=1, le=MAX_PLAN_SESSIONS)
    goal: str | None = Field(default=None, max_length=500)
    episode_id: UUID | None = None


class PlanUpdate(ApiModel):
    """Old ``plan-edit`` modal: the name and the total number of sessions (never below what is done)."""

    version: int
    title: str | None = Field(default=None, min_length=1, max_length=120)
    total_sessions: int | None = Field(default=None, ge=1, le=MAX_PLAN_SESSIONS)
    goal: str | None = Field(default=None, max_length=500)
    status: PlanStatus | None = None


class SessionCreate(ApiModel):
    """The ``session-*`` inputs of the old Ghi buổi điều trị form. ``complete=true`` is the old
    "Lưu buổi điều trị": the session is recorded and finished in one step."""

    performed_on: date
    plan_id: UUID | None = None
    session_type: str = Field(min_length=1, max_length=80)
    protocol_id: str | None = Field(default=None, max_length=60, description="E.g. 'laser-co2'.")
    region: str | None = Field(default=None, max_length=60)
    view: str | None = Field(default=None, max_length=60)
    note: str = Field(default="", max_length=2000, description="Đánh giá trước buổi.")
    aftercare: str = Field(default="", max_length=2000, description="Hướng dẫn chăm sóc gửi sau buổi.")
    next_visit_on: date | None = Field(default=None, description="Ngày dự kiến tái khám.")
    complete: bool = True
    with_photo: bool = Field(
        default=False,
        description="The form has a photo to upload next. When false a completed session raises the task "
        "'Thiếu ảnh mốc đánh giá' of the old web.",
    )


class SessionComplete(ApiModel):
    """Finish a recorded (``scheduled``) session. Fields left out keep what the session already holds."""

    version: int
    performed_on: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    aftercare: str | None = Field(default=None, max_length=2000)
    next_visit_on: date | None = None
    with_photo: bool = False


class SessionReview(ApiModel):
    version: int


class SessionDetailOut(TreatmentSessionOut):
    """A session with its clinical text. Read with ``session.read``."""

    patient_id: UUID
    doctor_name: str | None = None
    note: str | None = None
    aftercare: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: VnDatetime | None = None
    consent_id: UUID | None = None


class ConsultNoteStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class ConsultNoteDraftCreate(ApiModel):
    """Old ``generate-note``: a few key points typed by the clinician become a structured draft."""

    input_text: str = Field(min_length=1, max_length=2000)


class ConsultNoteApprove(ApiModel):
    """Old ``approve-note``: the clinician edits the draft, then approves it into Patient 360."""

    version: int
    body: str | None = Field(default=None, max_length=4000, description="The edited text; left out = as is.")


class ConsultNoteOut(ApiModel):
    id: UUID
    patient_id: UUID
    status: ConsultNoteStatus
    source_text: str
    body: str
    created_by: UUID | None = None
    created_by_name: str | None = None
    approved_by: UUID | None = None
    approved_by_name: str | None = None
    approved_at: VnDatetime | None = None
    created_at: VnDatetime
    version: int


class MediaStage(StrEnum):
    BEFORE = "before"
    AFTER = "after"


class MediaStatus(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    CONFIRMED = "confirmed"


class MediaUploadIntent(ApiModel):
    stage: MediaStage
    mime: str = Field(description="One of MEDIA_MIME_TYPES.")
    size_bytes: int = Field(gt=0, description="Exact size of the file the browser will send.")
    session_id: UUID | None = None
    region: str | None = Field(default=None, max_length=60)
    view: str | None = Field(default=None, max_length=60)


class MediaUploadTarget(ApiModel):
    """Where and how to send the bytes: ``PUT`` the raw file to ``upload_path`` (relative to the API origin)
    with ``Content-Type`` = ``mime``, before ``expires_at``; then call confirm."""

    media_id: UUID
    upload_path: str
    method: str = "PUT"
    mime: str
    max_bytes: int
    expires_at: VnDatetime


class MediaOut(ApiModel):
    id: UUID
    patient_id: UUID
    session_id: UUID | None = None
    stage: MediaStage
    region: str | None = None
    view: str | None = None
    mime: str
    size_bytes: int
    status: MediaStatus
    consent_id: UUID
    consent_active: bool = Field(description="The patient's current media consent is granted.")
    uploaded_by: UUID | None = None
    uploaded_by_name: str | None = None
    created_at: VnDatetime
    confirmed_at: VnDatetime | None = None
    content_path: str = Field(description="GET returns the bytes (needs media.read and the consent).")
    version: int
