"""Service catalog, rooms/doctors, protocols and the photo studio read model (package U, step U4).

Tables ``clinic.service``, ``clinic.service_version``, ``clinic.protocol``, ``clinic.room``,
``clinic.room_block``. JS source: ``operations-data.js`` (services, rooms, blocks), ``finance_server.py``
(rate, basis, version), ``crm-automation.js`` (laser-co2 chain), ``clinic.js`` ``studio()`` (before/after
studio).

Rules the DTOs keep:

* Money is an integer number of VND (``price_vnd``); a commission rate is an integer number of basis points of
  the base (``rate_bp``, 10000 = 100 %), as the finance prototype stores it. ``rate_bp`` and ``basis`` are the
  clinic's payroll terms: they are returned only to staff who may manage the catalog (``admin.rules``),
  ``null`` to everyone else.
* ``version`` is the optimistic lock of the row (send it back on PATCH). ``terms_version`` is the number of
  the CURRENT price/rate snapshot: a change of price, rate, basis, duration or buffer creates the next
  snapshot and the old ones stay readable in ``history``.
* A protocol's milestones are the day offsets of the CRM rules ``d1``, ``d3`` and ``d7``.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.crm import RuleKey

Hhmm = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class ShiftIntervalOut(ApiModel):
    start: Hhmm
    end: Hhmm = Field(description="An end earlier than the start means the shift ends the next morning.")


Code = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")]


class ServiceBasis(StrEnum):
    """What a commission rate is applied to (``finance_server.py``: ``net``, ``list``, ``collected``)."""

    NET = "net"
    LIST = "list"
    COLLECTED = "collected"


# ------------------------------------------------------------------------------------------------ services
class ServiceTermsOut(ApiModel):
    """One snapshot of the terms of a service."""

    version_no: int = Field(ge=1)
    price_vnd: int = Field(ge=0)
    rate_bp: int | None = Field(default=None, description="Null unless the caller holds admin.rules.")
    basis: ServiceBasis | None = Field(default=None, description="Null unless the caller holds admin.rules.")
    duration_min: int
    buffer_min: int
    changed_by: UUID | None = None
    created_at: VnDatetime


class ServiceOut(ApiModel):
    id: UUID
    code: str
    name: str
    active: bool
    protocol_code: str | None = None
    room_ids: list[UUID]
    price_vnd: int
    rate_bp: int | None = Field(default=None, description="Null unless the caller holds admin.rules.")
    basis: ServiceBasis | None = Field(default=None, description="Null unless the caller holds admin.rules.")
    duration_min: int
    buffer_min: int
    terms_version: int = Field(description="Number of the current price/rate snapshot.")
    version: int = Field(description="Optimistic lock counter; send it back on PATCH.")


class ServiceDetailOut(ServiceOut):
    history: list[ServiceTermsOut] = Field(description="Every snapshot, newest first.")


class ServiceCreate(ApiModel):
    code: Code
    name: str = Field(min_length=1, max_length=120)
    price_vnd: int = Field(ge=0, le=1_000_000_000)
    rate_bp: int = Field(default=0, ge=0, le=10000)
    basis: ServiceBasis = ServiceBasis.NET
    duration_min: int = Field(ge=5, le=480)
    buffer_min: int = Field(default=0, ge=0, le=120)
    protocol_code: Code | None = None
    room_ids: list[UUID] = Field(default_factory=list[UUID], max_length=50)
    active: bool = True


class ServiceUpdate(ApiModel):
    """Only the fields that are sent change. A change of ``price_vnd``, ``rate_bp``, ``basis``,
    ``duration_min`` or ``buffer_min`` creates a new snapshot. ``protocol_code: null`` detaches it."""

    version: int
    name: str | None = Field(default=None, min_length=1, max_length=120)
    active: bool | None = None
    protocol_code: Code | None = None
    room_ids: list[UUID] | None = Field(default=None, max_length=50)
    price_vnd: int | None = Field(default=None, ge=0, le=1_000_000_000)
    rate_bp: int | None = Field(default=None, ge=0, le=10000)
    basis: ServiceBasis | None = None
    duration_min: int | None = Field(default=None, ge=5, le=480)
    buffer_min: int | None = Field(default=None, ge=0, le=120)


# -------------------------------------------------------------------------------------------------- rooms
class RoomOut(ApiModel):
    id: UUID
    name: str
    capacity: int
    active: bool
    version: int


class RoomCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(default=1, ge=1, le=20)


class RoomUpdate(ApiModel):
    version: int
    name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=20)
    active: bool | None = None


class RoomBlockOut(ApiModel):
    id: UUID
    room_id: UUID
    day: date
    start: Hhmm
    end: Hhmm
    reason: str
    created_by: UUID | None = None


class RoomBlockCreate(ApiModel):
    room_id: UUID
    day: date
    start: Hhmm
    end: Hhmm
    reason: str = Field(min_length=1, max_length=200)


class DoctorResourceOut(ApiModel):
    """A doctor as the resources page shows them: the account and the shift of package M, plus the load of the
    day asked. Nothing here is stored twice: ``clinic.user_account`` and ``clinic.staff_profiles`` are the
    source."""

    user_id: UUID
    name: str
    active: bool
    has_shift: bool = Field(description="False when the doctor has no row in clinic.staff_profiles yet.")
    shift: list[ShiftIntervalOut] = Field(description="The intervals of the weekday of ``day``.")
    shift_minutes: int = Field(ge=0)
    booked_count: int = Field(ge=0, description="Active appointments of the doctor on ``day``.")
    booked_minutes: int = Field(ge=0)


class ResourcesOut(ApiModel):
    day: date
    doctors: list[DoctorResourceOut]
    rooms: list[RoomOut]
    blocks: list[RoomBlockOut] = Field(description="Room blocks from ``day`` on, soonest first.")


# --------------------------------------------------------------------------------------------- protocols
class ProtocolMilestone(ApiModel):
    rule_key: RuleKey = Field(description="One of d1, d3, d7.")
    day: int = Field(ge=0, le=365, description="Days after the session.")


class ProtocolOut(ApiModel):
    id: UUID
    code: str
    name: str
    milestones: list[ProtocolMilestone]
    followup_days: int | None = Field(description="Day of the review recommendation (D+30 for laser-co2).")
    window_days: int = Field(description="The chain applies to a session at most this old.")
    active: bool
    version: int


class ProtocolCreate(ApiModel):
    code: Code
    name: str = Field(min_length=1, max_length=120)
    milestones: list[ProtocolMilestone] = Field(default_factory=list[ProtocolMilestone], max_length=3)
    followup_days: int | None = Field(default=None, ge=1, le=365)
    window_days: int = Field(default=45, ge=1, le=365)
    active: bool = True


class ProtocolUpdate(ApiModel):
    """Only the fields that are sent change; ``followup_days: null`` removes the review recommendation."""

    version: int
    name: str | None = Field(default=None, min_length=1, max_length=120)
    milestones: list[ProtocolMilestone] | None = Field(default=None, max_length=3)
    followup_days: int | None = Field(default=None, ge=1, le=365)
    window_days: int | None = Field(default=None, ge=1, le=365)
    active: bool | None = None


# ----------------------------------------------------------------------------------------------- studio
class StudioPhotoOut(ApiModel):
    """A milestone photo. The photo store (``clinic.media``) belongs to the Patient 360 step; until it exists
    the list is empty and the screen shows the clinic's illustrative placeholders."""

    id: UUID
    taken_at: VnDatetime
    view: str
    region: str
    session_id: UUID | None = None


class StudioOut(ApiModel):
    patient_id: UUID
    patient_code: str
    patient_name: str
    concern: str | None = None
    view: str
    views: list[str]
    media_consent: bool = Field(description="The newest ``media`` consent of the patient is granted.")
    photos: list[StudioPhotoOut]
