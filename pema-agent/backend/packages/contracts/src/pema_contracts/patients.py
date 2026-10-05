"""Patient and Patient 360 DTOs (tables ``clinic.patient``, ``episode``, ``treatment_plan``,
``treatment_session``, ``consent``). All data in the repo is synthetic."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.appointments import AppointmentOut
from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.conversations import ConversationSummary
from pema_contracts.crm import CrmActivityOut, CrmProfile, CrmTaskOut


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNKNOWN = "unknown"


class ConsentKind(StrEnum):
    MESSAGING = "messaging"
    MARKETING = "marketing"
    MEDIA = "media"
    DATA_PROCESSING = "data_processing"


class PatientOut(ApiModel):
    id: UUID
    code: str = Field(description="Pseudonymous patient code (patient_ref for the AI), e.g. 'P025'.")
    full_name: str
    phone: str | None = None
    birth_date: date | None = None
    gender: Gender = Gender.UNKNOWN
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    cs_owner_id: UUID | None = None
    cs_owner_name: str | None = None
    marketing_opt_out: bool = False
    first_contact_at: date | None = None
    source: str | None = None
    version: int


class PatientCreate(ApiModel):
    code: str | None = Field(default=None, max_length=32, description="Generated when omitted.")
    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    gender: Gender = Gender.UNKNOWN
    doctor_id: UUID | None = None
    cs_owner_id: UUID | None = None
    source: str | None = Field(default=None, max_length=60)


class PatientUpdate(ApiModel):
    version: int
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    gender: Gender | None = None
    doctor_id: UUID | None = None
    cs_owner_id: UUID | None = None
    marketing_opt_out: bool | None = None


class EpisodeOut(ApiModel):
    id: UUID
    title: str
    status: str
    started_on: date
    closed_on: date | None = None


class TreatmentPlanOut(ApiModel):
    id: UUID
    episode_id: UUID | None
    service_code: str
    title: str
    total_sessions: int
    completed_sessions: int
    status: str
    goal: str | None = None
    doctor_id: UUID | None = None
    version: int = 1
    unit_price_vnd: int | None = Field(
        default=None,
        description="Price of one session fixed when the service was added to the course (U9). Null for a "
        "plan made without a price and for a caller who holds no finance permission.",
    )
    discount_vnd: int | None = Field(default=None, description="Discount fixed with the price (same rules).")
    agreed_price_vnd: int | None = Field(
        default=None,
        description="Price after discount (sessions x unit price - discount), fixed when the service was "
        "added: a later change of the catalog never moves it (same rules).",
    )
    service_terms_version: int | None = Field(
        default=None, description="Number of the catalog price snapshot the price was taken from."
    )


class TreatmentSessionOut(ApiModel):
    id: UUID
    plan_id: UUID | None
    performed_at: VnDatetime
    doctor_id: UUID | None
    protocol_id: str | None = Field(default=None, description="E.g. 'laser-co2'; drives D+1/3/7 rules.")
    title: str
    status: str
    session_type: str | None = None
    region: str | None = None
    view: str | None = None
    next_visit_on: date | None = None
    reviewed: bool = False
    version: int = 1


class ConsentOut(ApiModel):
    id: UUID
    kind: ConsentKind
    granted: bool
    granted_at: VnDatetime | None = None
    revoked_at: VnDatetime | None = None
    source: str | None = None


class ConsentCreate(ApiModel):
    kind: ConsentKind
    granted: bool
    source: str | None = Field(default=None, max_length=60)


class TimelineEvent(ApiModel):
    """One row of the Patient 360 timeline (JS ``timeline``). ``source_id`` points at the original record."""

    id: str
    at: VnDatetime
    kind: str = Field(
        description="session, appointment, crm_activity, message, review, consent, consult, app_event"
    )
    title: str
    detail: str | None = None
    by: str | None = None
    source_id: str | None = None


class Patient360(ApiModel):
    """Read model joining context; the original records stay the source of truth."""

    patient: PatientOut
    profile: CrmProfile
    episodes: list[EpisodeOut] = Field(default_factory=list[EpisodeOut])
    plans: list[TreatmentPlanOut] = Field(default_factory=list[TreatmentPlanOut])
    recent_sessions: list[TreatmentSessionOut] = Field(default_factory=list[TreatmentSessionOut])
    appointments: list[AppointmentOut] = Field(default_factory=list[AppointmentOut])
    open_tasks: list[CrmTaskOut] = Field(default_factory=list[CrmTaskOut])
    recent_activities: list[CrmActivityOut] = Field(default_factory=list[CrmActivityOut])
    consents: list[ConsentOut] = Field(default_factory=list[ConsentOut])
    conversations: list[ConversationSummary] = Field(default_factory=list[ConversationSummary])
    timeline: list[TimelineEvent] = Field(default_factory=list[TimelineEvent])
    alerts: list[str] = Field(
        default_factory=list[str],
        description="The 'Thông tin cần nhớ' lines of the hero (U9), one warning per entry.",
    )
